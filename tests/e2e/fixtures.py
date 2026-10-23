"""Sample data that puts every Colab Monitor state on screen at once.

Shared by the browser tests and `scripts/screenshots.py`. Plain Python, no pytest.
"""

import datetime
import json
import time

from colab_monitor.poller import ApiPoller
from colab_monitor.server import Dashboard
from colab_monitor.usage_log import UsageLog

NOW = time.time()


def _iso(seconds_ago):
    return datetime.datetime.fromtimestamp(NOW - seconds_ago, datetime.UTC).isoformat()


def _local(seconds_ago):
    return datetime.datetime.fromtimestamp(NOW - seconds_ago).strftime("%Y-%m-%d %H:%M:%S")


def _write_jsonl(path, events):
    path.write_text("".join(json.dumps(e) + "\n" for e in events))


# The account's usage rate steps up as each machine starts, so per-machine rates can be estimated.
MACHINE_RATES = [  # (started this many seconds ago, compute units per hour)
    (3600, 1.41),  # train-gpu (T4)
    (2000, 0.08),  # eval-cpu
    (700, 0.08),  # side-run
    (500, 0.08),  # old-job
    (250, 0.11),  # the unnamed orphan, which no history file mentions
]
RATE = round(sum(r for _, r in MACHINE_RATES), 2)


def _rate_at(seconds_ago):
    earlier_run = 1.76 if 5400 < seconds_ago <= 6 * 3600 else 0.0
    return round(earlier_run + sum(r for started, r in MACHINE_RATES if seconds_ago < started), 2)


def build_data(root):
    """Fixture data that puts every UI state on screen at once."""
    sessions = {
        "train-gpu": {
            "name": "train-gpu",
            "token": "SECRET-TOKEN",
            "url": "https://proxy.example/secret",
            "endpoint": "gpu-t4-e2e",
            "variant": "GPU",
            "accelerator": "T4",
            "machine_shape": "STANDARD",
            "running": "run(train.py)",
            "last_execution": ["/home/me/project/train.py", None, _local(300)],
        },
        "eval-cpu": {
            "name": "eval-cpu",
            "token": "SECRET-TOKEN",
            "url": "https://proxy.example/secret",
            "endpoint": "cpu-e2e",
            "variant": "DEFAULT",
            "accelerator": "NONE",
            "machine_shape": "STANDARD",
            "running": None,
            "last_execution": ["stdin", None, _local(900)],
        },
    }
    (root / "sessions.json").write_text(json.dumps(sessions))

    history = root / "history"
    history.mkdir()
    _write_jsonl(
        history / "train-gpu.jsonl",
        [
            {
                "timestamp": _iso(3600),
                "event_type": "session_created",
                "endpoint": "gpu-t4-e2e",
                "accelerator": "T4",
                "variant": "GPU",
                "machine_shape": "STANDARD",
            },
            {
                "timestamp": _iso(3000),
                "event_type": "execution",
                "code": "print('hello gpu')",
                "via": "exec",
                "outputs": [
                    {"output_type": "stream", "name": "stdout", "text": "hello gpu\n"},
                    {"output_type": "display_data", "data": {"image/png": "iVBORw0KGgo" * 50}},
                ],
            },
        ],
    )
    _write_jsonl(
        history / "eval-cpu.jsonl",
        [
            {
                "timestamp": _iso(2000),
                "event_type": "session_created",
                "endpoint": "cpu-e2e",
                "accelerator": "NONE",
            },
            {
                "timestamp": _iso(1000),
                "event_type": "execution",
                "code": "evaluate()",
                "outputs": [
                    {
                        "output_type": "error",
                        "ename": "\x1b[0;31mValueError\x1b[0m",
                        "evalue": "bad split",
                        "traceback": [],
                    }
                ],
            },
        ],
    )
    _write_jsonl(
        history / "old-job.jsonl",
        [
            {"timestamp": _iso(500), "event_type": "session_created", "endpoint": "cpu-stopping"},
            {"timestamp": _iso(20), "event_type": "session_terminated", "reason": "user_requested"},
        ],
    )
    _write_jsonl(
        history / "side-run.jsonl",
        [
            {"timestamp": _iso(700), "event_type": "session_created", "endpoint": "cpu-named-orphan"},
        ],
    )

    runs = root / "runs"
    runs.mkdir()
    lines = ["torch 2.11 | device: Tesla T4", "UserWarning: GradScaler is deprecated"]
    lines += [f"[epoch {i // 20 + 1}] step {i}/100 loss {2.0 / (i + 1):.4f}" for i in range(1, 101)]
    lines += [
        "epoch 6/10:  10%|#   \r epoch 6/10:  90%|######### \r epoch 6/10: 100%|##########",
        "\x1b[0;31mValueError\x1b[0m: schema mismatch in shard 40",
    ]
    (runs / "train-gpu.log").write_text("\n".join(lines) + "\n")
    (runs / "etl.err").write_text("etl starting\n")

    usage = UsageLog(str(root / "usage.jsonl"))
    balance = 120.0
    t = NOW - 86400 + 240  # samples every 5 minutes, the last one a minute ago, none at a machine's start
    while t <= NOW:
        hours_ago = (NOW - t) / 3600
        if not 10 < hours_ago < 12:  # dashboard was off for two hours
            rate = _rate_at(NOW - t)
            usage.append({"balance": round(balance, 3), "rate_per_hour": rate}, now=t)
            balance -= rate * 300 / 3600
        t += 300
    return {
        "sessions": root / "sessions.json",
        "history": history,
        "runs": runs,
        "usage": usage,
        "balance": balance,
    }


def sample_dashboard(data) -> Dashboard:
    """A Dashboard over `build_data` output, with a stub Colab poller (no network)."""
    last = data["usage"].read()[-1]
    assignments = [
        {"endpoint": e, "accelerator": acc, "variant": "DEFAULT", "machine_shape": "STANDARD"}
        for e, acc in [
            ("gpu-t4-e2e", "T4"),
            ("cpu-e2e", "NONE"),
            ("cpu-stopping", "NONE"),
            ("cpu-named-orphan", "NONE"),
            ("cpu-anon-orphan", "NONE"),
        ]
    ]
    poller = ApiPoller(
        lambda: {"balance": last["balance"], "rate_per_hour": RATE, "assignments_count": 5},
        lambda: assignments,
        interval=60,
    )
    poller.poll_once()
    app = Dashboard(
        poller,
        sessions_path=str(data["sessions"]),
        history_dir=str(data["history"]),
        log_dirs=[str(data["runs"])],
        usage_log=data["usage"],
        auth="oauth2",
    )
    return app
