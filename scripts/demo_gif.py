"""Record docs/images/demo.gif, the README tour, from a realistic sample workday.

    uv run python scripts/demo_gif.py

No Colab account is needed. Uses your installed Chrome, or Playwright's Chromium.
"""

import datetime
import io
import json
import pathlib
import sys
import tempfile
import threading
import time

from PIL import Image
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from colab_monitor import metrics  # noqa: E402
from colab_monitor.poller import ApiPoller  # noqa: E402
from colab_monitor.server import Dashboard, make_server  # noqa: E402
from colab_monitor.usage_log import UsageLog  # noqa: E402

OUT = ROOT / "docs" / "images" / "demo.gif"
WIDTH, HEIGHT = 1280, 800
REFRESH = 3.2  # seconds; the page refreshes logs every 3 s
REST = (760, 40)  # an empty spot beside the page title, so no hover highlight shows in the frames
NOW = time.time()
HOUR = 3600

# Three healthy machines, started through the day. Rates are compute units per hour.
MACHINES = [
    # name, endpoint, accelerator, shape, rate, started (hours ago), job
    ("data-prep", "m-s-use1c2-4f8a2c91d0", "NONE", "STANDARD", 0.08, 9.0, "run(tokenize.py)"),
    ("eval-sweep", "gpu-t4-s-euw4b1-7c21e5a3f4", "T4", "STANDARD", 1.76, 6.0, "run(eval.py)"),
    ("llama3-finetune", "gpu-a100-s-usc1a1-9d4b0e72c8", "A100", "HIGH_RAM", 11.77, 3.0, "run(train.py)"),
]
START_BALANCE = 860.0


def iso(hours_ago: float) -> str:
    return datetime.datetime.fromtimestamp(NOW - hours_ago * HOUR, datetime.UTC).isoformat()


def local(hours_ago: float) -> str:
    return datetime.datetime.fromtimestamp(NOW - hours_ago * HOUR).strftime("%Y-%m-%d %H:%M:%S")


def write_jsonl(path: pathlib.Path, events: list[dict]) -> None:
    path.write_text("".join(json.dumps(e) + "\n" for e in events))


def tqdm_line(done: int, total: int, seconds_each: int) -> str:
    """One line of a tqdm progress bar, as a tokenizer would print it."""

    def clock(seconds: int) -> str:
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    bar = "#" * (done * 10 // total)
    return (
        f"tokenize: {done * 100 // total:3d}%|{bar:<10}| {done}/{total} "
        f"[{clock(done * seconds_each)}<{clock((total - done) * seconds_each)}, {seconds_each:.2f}s/shard]"
    )


def training_log(steps: int) -> str:
    lines = [
        "torch 2.5.1 | device: NVIDIA A100-SXM4-40GB",
        "loading meta-llama/Meta-Llama-3-8B (bf16) with LoRA r=64, alpha=16",
        "trainable params: 167,772,160 || all params: 8,198,033,408 || trainable%: 2.05",
        "dataset: 48,000 train / 2,000 eval examples",
    ]
    for step in range(25, steps + 1, 25):
        epoch = step // 600 + 1
        loss = 0.62 + 1.1 * (0.996**step)
        lines.append(f"epoch {epoch}/3 | step {step:>4}/1800 | loss {loss:.4f} | lr 2.0e-4 | 3.1 it/s")
        if step % 300 == 0:
            val = loss - 0.04
            lines.append(f"eval  | step {step:>4} | val_loss {val:.4f} | perplexity {2.718**val:.2f}")
            lines.append(f"saved checkpoint runs/llama3/ckpt-{step}")
    return "\n".join(lines) + "\n"


def build(root: pathlib.Path) -> dict:
    sessions = {
        name: {
            "name": name,
            "token": "x",
            "url": "x",
            "endpoint": endpoint,
            "variant": "DEFAULT" if acc == "NONE" else "GPU",
            "accelerator": acc,
            "machine_shape": shape,
            "running": job,
            "last_execution": [job[4:-1], None, local(started - 0.1)],
        }
        for name, endpoint, acc, shape, _, started, job in MACHINES
    }
    (root / "sessions.json").write_text(json.dumps(sessions))

    history = root / "history"
    history.mkdir()
    for name, endpoint, acc, shape, _, started, _job in MACHINES:
        events = [
            {
                "timestamp": iso(started),
                "event_type": "session_created",
                "endpoint": endpoint,
                "accelerator": acc,
                "variant": sessions[name]["variant"],
                "machine_shape": shape,
            },
        ]
        if name == "llama3-finetune":
            events += [
                {
                    "timestamp": iso(started - 0.05),
                    "event_type": "execution",
                    "via": "exec",
                    "code": "import torch\nprint(torch.cuda.get_device_name())",
                    "outputs": [
                        {"output_type": "stream", "name": "stdout", "text": "NVIDIA A100-SXM4-40GB\n"}
                    ],
                },
                {
                    "timestamp": iso(started - 0.08),
                    "event_type": "execution",
                    "via": "exec",
                    "code": "!pip install -q peft==0.13.2 bitsandbytes==0.44.1",
                    "outputs": [
                        {
                            "output_type": "stream",
                            "name": "stdout",
                            "text": "Successfully installed bitsandbytes-0.44.1 peft-0.13.2\n",
                        }
                    ],
                },
            ]
        if name == "eval-sweep":
            events.append(
                {
                    "timestamp": iso(started - 1.2),
                    "event_type": "execution",
                    "via": "exec",
                    "code": "!python eval.py --checkpoint runs/llama3/ckpt-1200 --split test",
                    "outputs": [
                        {
                            "output_type": "stream",
                            "name": "stdout",
                            "text": "accuracy 0.871 | f1 0.864 | 2,000 examples\n",
                        }
                    ],
                }
            )
        write_jsonl(history / f"{name}.jsonl", events)

    runs = root / "runs"
    runs.mkdir()
    (runs / "llama3-finetune.log").write_text(training_log(900))
    (runs / "eval-sweep.log").write_text(
        "loading runs/llama3/ckpt-1200\naccuracy 0.871 | f1 0.864 | 2,000 examples\n"
    )
    (runs / "data-prep.log").write_text("".join(tqdm_line(i, 64, 13) + "\n" for i in range(1, 41)))

    usage = UsageLog(str(root / "usage.jsonl"))
    # Every 5 minutes from 2 minutes past the hour, so no sample lands on a machine's start time
    # and each machine's rate can be told apart.
    balance, t = START_BALANCE, NOW - 24 * HOUR + 120
    while t <= NOW:
        hours_ago = (NOW - t) / HOUR
        rate = sum(r for *_, r, started, _job in MACHINES if hours_ago <= started)
        usage.append({"balance": round(balance, 2), "rate_per_hour": round(rate, 2)}, now=t)
        balance -= rate * 300 / HOUR
        t += 300
    return {"root": root, "runs": runs, "history": history, "usage": usage}


def dashboard(data: dict) -> Dashboard:
    last = data["usage"].read()[-1]
    assignments = [
        {"endpoint": e, "accelerator": acc, "variant": "DEFAULT", "machine_shape": shape}
        for _, e, acc, shape, *_ in MACHINES
    ]
    poller = ApiPoller(
        lambda: {
            "balance": last["balance"],
            "rate_per_hour": last["rate"],
            "assignments_count": len(MACHINES),
        },
        lambda: assignments,
        interval=60,
    )
    poller.poll_once()
    return Dashboard(
        poller,
        sessions_path=str(data["root"] / "sessions.json"),
        history_dir=str(data["history"]),
        log_dirs=[str(data["runs"])],
        usage_log=data["usage"],
        auth="oauth2",
    )


def launch(p):
    try:
        return p.chromium.launch(channel="chrome")
    except PlaywrightError:
        return p.chromium.launch()


def main() -> None:
    frames: list[tuple[Image.Image, int]] = []

    def capture(page, ms: int) -> None:
        frames.append((Image.open(io.BytesIO(page.screenshot())).convert("RGB"), ms))

    with tempfile.TemporaryDirectory() as tmp:
        data = build(pathlib.Path(tmp))
        # The demo's state file stands in for the colab CLI's default one, so the commands on screen
        # read as a user sees them: `colab stop -s NAME`, without a temporary --config path.
        metrics.DEFAULT_SESSIONS_PATH = str(data["root"] / "sessions.json")
        log = data["runs"] / "llama3-finetune.log"
        server = make_server(dashboard(data), "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        with sync_playwright() as p:
            browser = launch(p)
            page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, color_scheme="light")

            page.goto(f"{base}/#/overview")
            page.wait_for_selector("#chart .chart-hit", state="attached")
            page.wait_for_timeout(1500)
            capture(page, 2800)

            # Hover where the A100 started: the readout names the machine behind the step in the rate.
            hit = page.locator("#chart .chart-hit").bounding_box()
            start = page.locator(
                "#chart .chart-mark.start", has=page.locator("title", has_text="llama3-finetune")
            )
            mark = start.locator("line").bounding_box()
            page.mouse.move(mark["x"] + 1, hit["y"] + hit["height"] * 0.45)
            page.wait_for_timeout(300)
            capture(page, 2400)
            page.mouse.move(*REST)

            page.locator("#ov-jobs").scroll_into_view_if_needed()
            page.mouse.wheel(0, 400)
            page.wait_for_timeout(500)
            capture(page, 2800)
            page.evaluate("window.scrollTo(0, 0)")

            page.click('nav a[data-route="sessions"]')
            page.mouse.move(*REST)
            page.wait_for_selector("#sessions-body tr")
            page.wait_for_timeout(600)
            capture(page, 2000)

            # A machine's details: cost so far, its job's loss curve, and its latest output.
            page.locator("#sessions-body tr", has_text="llama3-finetune").locator("td.st").click()
            page.wait_for_selector("#drawer .d-chart svg")
            page.wait_for_selector("#drawer .d-term .tl")
            page.mouse.move(*REST)
            page.wait_for_timeout(600)
            capture(page, 3000)
            page.locator("#drawer-body").evaluate(
                "b => b.scrollTo(0, b.querySelector('.d-job').offsetTop - 12)"
            )
            page.wait_for_timeout(400)
            capture(page, 2800)
            page.keyboard.press("Escape")

            page.click('nav a[data-route="logs"]')
            page.locator("#log-list button", has_text="llama3-finetune.log").click()
            page.mouse.move(*REST)
            page.wait_for_selector("#log-view .tl")
            page.wait_for_selector("#log-metric-chart svg")  # the loss curve above the log
            page.wait_for_timeout(800)
            capture(page, 1600)
            for steps in (975, 1050, 1125, 1200):  # the run keeps logging
                log.write_text(training_log(steps))
                time.sleep(REFRESH)
                capture(page, 900)

            page.click('nav a[data-route="history"]')
            page.locator("#history-list-pane button", has_text="llama3-finetune").click()
            page.wait_for_selector("#timeline details")
            page.locator("#timeline details summary").first.click()
            page.mouse.move(*REST)
            page.wait_for_timeout(500)
            capture(page, 2600)

            # The same overview in dark mode, one click away in the sidebar.
            page.click('.theme-seg [data-theme-choice="dark"]')
            page.click('nav a[data-route="overview"]')
            page.mouse.move(*REST)
            page.wait_for_selector("#chart .chart-line", state="attached")
            page.wait_for_timeout(800)
            capture(page, 3000)
            browser.close()
        server.shutdown()

    # 256-colour frames without dithering keep UI text and lines crisp.
    images = [
        img.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        for img, _ in frames
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(
        OUT,
        save_all=True,
        append_images=images[1:],
        duration=[ms for _, ms in frames],
        loop=0,
        optimize=True,
        disposal=1,
    )
    print(f"wrote {OUT.relative_to(ROOT)}: {len(frames)} frames, {OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
