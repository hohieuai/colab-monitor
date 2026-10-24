"""The colab-monitor command: `serve` (the web dashboard), `status`, and `watch`."""

import argparse
import contextlib
import datetime
import http.client
import json
import os
import re
import select
import shutil
import signal
import sys
import textwrap
import threading
import time
import urllib.parse
import urllib.request

from colab_monitor import __version__, metrics, server
from colab_monitor.poller import ApiPoller
from colab_monitor.usage_log import UsageLog

EXIT_ATTENTION = 3  # `status --exit-code`: something needs attention
# A running dashboard answers from its caches, but its first answer reads every history file and log.
DASHBOARD_TIMEOUT = 5.0
# Ways a dashboard probe fails: nothing listening, another service, or a broken or partial reply.
_DASHBOARD_ERRORS = (OSError, ValueError, http.client.HTTPException)
# Terminal control characters, which a job's output must not send to the user's terminal.
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
WATCH_POLL_INTERVAL = 60.0
MAX_JOBS_SHOWN = 8  # the text view; --json lists every log
TOKEN_PATH = "~/.config/colab-cli/token.json"

STATUS_WORDS = {"busy": "running", "gone": "released"}
STATUS_COLORS = {"busy": "green", "idle": "yellow", "stopping": "dim", "orphan": "red", "unknown": "dim"}
ANSI = {"bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33"}

TOP_LEVEL_HELP = f"""\
usage: colab-monitor [COMMAND] [OPTIONS]

Monitor your Colab sessions, compute units, and job logs.

commands:
  serve    start the web dashboard (the default when no command is given)
  status   print what is running, what it costs, and what needs attention
  watch    keep that summary on screen, refreshed every few seconds

Run `colab-monitor COMMAND -h` for a command's options.
colab-monitor {__version__}
"""


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-h", "--help", "help"):
        print(TOP_LEVEL_HELP, end="")
        return 0
    if not argv or argv[0].startswith("-"):
        return COMMANDS["serve"](argv)  # `colab-monitor --port 9` still starts the dashboard
    command, rest = argv[0], argv[1:]
    if command not in COMMANDS:
        known = ", ".join(COMMANDS)
        print(f"colab-monitor: unknown command '{command}'. Commands: {known}.", file=sys.stderr)
        return 2
    return COMMANDS[command](rest)


# ---------- Options ----------


def _parser(command: str, description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=f"colab-monitor {command}", description=description)
    p.add_argument(
        "--host", default="127.0.0.1", help="where to look for a running dashboard (default: 127.0.0.1)"
    )
    p.add_argument(
        "--port",
        type=int,
        default=server.DEFAULT_PORT,
        help=f"port of a running dashboard (default: {server.DEFAULT_PORT})",
    )
    server.add_data_options(p)
    server.add_threshold_options(p)
    p.add_argument("--no-color", action="store_true", help="print without colour (also: NO_COLOR=1)")
    return p


# Options that choose what to read. --auth and -c only say how to reach Colab, so they don't count.
DATA_OPTIONS = ("log", "log_dir", "config", "history_dir", "usage_log", "no_api")


def _uses_data_options(p: argparse.ArgumentParser, args: argparse.Namespace) -> bool:
    """True if the user chose what to read. A running dashboard reads its own files, so skip it."""
    return any(getattr(args, name) != p.get_default(name) for name in DATA_OPTIONS)


def _parse(p: argparse.ArgumentParser, argv: list[str]) -> argparse.Namespace:
    args = p.parse_args(argv)
    args.use_dashboard = not _uses_data_options(p, args)
    return server.finish_args(p, args)


# ---------- Getting the state ----------


class Source:
    """Where the numbers come from: a running dashboard, or the files and Colab directly."""

    name = ""

    def state(self) -> dict:
        raise NotImplementedError

    def close(self) -> None:
        pass


class OlderDashboard(ValueError):
    """The dashboard on the port predates the status report."""


class DashboardSource(Source):
    name = "dashboard"

    def __init__(self, host: str, port: int, query: dict):
        probe = "127.0.0.1" if host in ("0.0.0.0", "::") else host
        if ":" in probe:
            probe = f"[{probe}]"
        self.url = f"http://{probe}:{port}/api/state"
        if query:
            self.url += "?" + urllib.parse.urlencode(query)

    def state(self) -> dict:
        with urllib.request.urlopen(self.url, timeout=DASHBOARD_TIMEOUT) as resp:
            if not (resp.headers.get("Server") or "").startswith("colab-monitor/"):
                raise OSError("not a Colab Monitor server")
            state = json.load(resp)
        if "insights" not in state:
            raise OlderDashboard(f"Colab Monitor {state.get('version', '')} on this port is too old")
        return state


class DirectSource(Source):
    name = "direct"

    def __init__(self, app: server.Dashboard, stop: threading.Event | None = None):
        self.app = app
        self._stop = stop

    def state(self) -> dict:
        code, state = self.app.handle("/api/state", {})
        if code != 200:
            raise ValueError(state.get("error"))
        return state

    def close(self) -> None:
        if self._stop is not None:
            self._stop.set()


def _threshold_query(args: argparse.Namespace) -> dict:
    return {
        param: getattr(args, param)
        for param in ("idle_alert", "stall_alert", "runway_alert")
        if getattr(args, param) is not None
    }


def _find_dashboard(args: argparse.Namespace) -> tuple[DashboardSource, dict] | None:
    if not args.use_dashboard:
        return None
    source = DashboardSource(args.host, args.port, _threshold_query(args))
    try:
        return source, source.state()
    except OlderDashboard:
        server._err(f"The dashboard on port {args.port} is an older version; reading the files instead.")
        server._err("Stop it and start `colab-monitor` again to update it.")
        return None
    except _DASHBOARD_ERRORS:
        return None


def _quiet_session(auth: str):
    """Sign in with saved credentials only. Returns None instead of starting a sign-in."""
    import warnings

    from colab_cli.auth import PUBLIC_SCOPES
    from google.auth.transport.requests import AuthorizedSession, Request

    if auth == "adc":
        import google.auth
        from google.auth.exceptions import DefaultCredentialsError

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            try:
                creds, _ = google.auth.default(scopes=list(PUBLIC_SCOPES))
            except DefaultCredentialsError:
                return None
    else:
        from google.oauth2.credentials import Credentials

        path = os.path.expanduser(TOKEN_PATH)
        if not os.path.exists(path):
            return None
        creds = Credentials.from_authorized_user_file(path, PUBLIC_SCOPES)
    if not creds.valid:
        creds.refresh(Request())  # raises if the saved sign-in no longer works
    return AuthorizedSession(creds)


def _connect(args: argparse.Namespace, usage_log: UsageLog) -> ApiPoller | None:
    """A poller with one fresh result, or None (with the reason on stderr) to use local files only."""
    from colab_cli.client import Client, Prod

    try:
        session = _quiet_session(args.auth)
    except Exception as e:  # noqa: BLE001 - any sign-in problem means local files only
        server._err(f"Couldn't sign in to Colab ({e}); showing local files only.")
        server._err("Run `colab sessions` once to sign in again.")
        return None
    if session is None:
        server._err("Not signed in to Colab; showing local files only.")
        server._err("Run `colab sessions` once to sign in, or pass --no-api to hide this message.")
        return None
    fetch_usage, fetch_assignments = server._colab_fetchers(Client(Prod(), session))
    poller = ApiPoller(
        fetch_usage, fetch_assignments, interval=WATCH_POLL_INTERVAL, on_sample=usage_log.append
    )
    poller.poll_once()
    return poller


def _direct(args: argparse.Namespace, keep_polling: bool) -> DirectSource:
    usage_log = UsageLog(os.path.expanduser(args.usage_log))
    poller = None if args.no_api else _connect(args, usage_log)
    app = server.Dashboard(
        poller=poller,
        sessions_path=args.config,
        history_dir=os.path.expanduser(args.history_dir),
        log_files=args.log,
        log_dirs=args.log_dir,
        usage_log=usage_log,
        auth=None if poller is None else args.auth,
        thresholds=server.thresholds_from(args),
    )
    stop = None
    if poller is not None and keep_polling:
        stop = threading.Event()
        first_wait = poller.base_interval  # _connect just checked
        threading.Thread(target=lambda: (stop.wait(first_wait), poller.run(stop)), daemon=True).start()
    return DirectSource(app, stop)


def _open_source(args: argparse.Namespace, keep_polling: bool = False) -> tuple[Source, dict]:
    found = _find_dashboard(args)
    if found is not None:
        return found
    source = _direct(args, keep_polling)
    return source, source.state()


# ---------- The report ----------


def _hardware(session: dict) -> str:
    accelerator = session.get("accelerator") or "?"
    hardware = "CPU" if accelerator == "NONE" else accelerator
    if session.get("machine_shape") == "HIGH_RAM":
        hardware += " High-RAM"
    return hardware


def build_report(state: dict, source: str) -> dict:
    """The `status --json` document (schema 1). Only add fields; never rename or remove one."""
    api = state.get("api") or {}
    usage = api.get("usage")
    insights = state["insights"]
    machines = []
    for s in state.get("sessions", []):
        if s.get("status") == "gone":
            continue
        m = s.get("metrics") or {}
        machines.append(
            {
                "name": s.get("name"),
                "endpoint": s["endpoint"],
                "status": s.get("status"),
                "hardware": _hardware(s),
                "job": s.get("running"),
                "uptime_s": m.get("uptime_s"),
                "idle_s": m.get("idle_s"),
                "rate": m.get("rate"),
                "rate_estimated": m.get("rate_estimated", False),
                "cost": m.get("cost"),
                "idle_cost": m.get("idle_cost"),
            }
        )
    enabled = bool(api.get("enabled"))
    return {
        "schema": metrics.SCHEMA,
        "source": source,
        "generated_at": state.get("generated_at") or datetime.datetime.now(datetime.UTC).isoformat(),
        "colab": {
            "enabled": enabled,
            "ok": enabled and usage is not None and not api.get("error"),
            "error": api.get("error"),
            "checked_at": api.get("updated_at"),
        },
        "compute_units": {
            "balance": usage.get("balance") if usage else None,
            "rate_per_hour": usage.get("rate_per_hour") if usage else None,
        },
        "runway": insights["runway"],
        "spend": insights["spend"],
        "machines": machines,
        "jobs": insights["jobs"],
        "runs": insights["runs"],
        "machine_hours_7d": insights["machine_hours_7d"],
        "attention": insights["attention"],
        "thresholds": insights["thresholds"],
    }


# ---------- Rendering ----------

# A line is a list of (text, style) pieces, so it can be cut to the terminal width before colouring.
Line = list[tuple[str, str | None]]


def _fit(line: Line, width: int) -> Line:
    out, used = [], 0
    for text, style in line:
        text = _CONTROL.sub("", text)
        room = width - used
        if room <= 0:
            break
        if len(text) > room:
            text = text[: room - 1] + "…" if room > 1 else "…"
        out.append((text, style))
        used += len(text)
    return out


def _paint(line: Line, color: bool) -> str:
    if not color:
        return "".join(text for text, _ in line).rstrip()
    parts = [f"\x1b[{ANSI[style]}m{text}\x1b[0m" if style and text.strip() else text for text, style in line]
    return "".join(parts).rstrip()


def _units(value: float | None) -> str:
    return "-" if value is None else f"{value:,.2f}"


def _duration(seconds: float | None) -> str:
    return "-" if seconds is None else metrics.human_duration(seconds)


def _long_duration(hours: float) -> str:
    if hours >= 48:
        return f"{hours / 24:.1f} days"
    return metrics.human_duration(hours * 3600)


def _clock(epoch: float, now: float) -> str:
    if epoch - now > 6 * 86400:
        return time.strftime("%a %d %b %H:%M", time.localtime(epoch))
    return time.strftime("%a %H:%M", time.localtime(epoch))


def _rate(rate: float | None, estimated: bool) -> str:
    if rate is None:
        return "-"
    return f"{'≈' if estimated else ' '}{rate:.2f}/h"


def _summary_lines(report: dict, now: float) -> list[Line]:
    colab = report["colab"]
    units = report["compute_units"]
    lines: list[Line] = []
    if not colab["enabled"]:
        lines.append([("Local files only: ", "yellow"), ("Colab is not checked, so no balance.", None)])
    elif colab["error"]:
        lines.append([(f"Colab check failed: {colab['error']}", "red")])

    def row(label: str, value: str, note: str = "") -> Line:
        return [(f"{label:<15}", "dim"), (value, "bold"), (note, "dim")]

    lines.append(row("Compute units", _units(units["balance"])))
    rate = units["rate_per_hour"]
    lines.append(row("Usage", "-" if rate is None else f"{rate:.2f}/h"))
    runway = report["runway"]
    if runway.get("hours") is None:
        lines.append(row("Runway", "-", "  (nothing is using compute units)" if rate == 0 else ""))
    else:
        until = f"  until {_clock(runway['empty_at'], now)}" if runway.get("empty_at") else ""
        lines.append(row("Runway", _long_duration(runway["hours"]), until))
    spend = report["spend"]
    lines.append(
        row(
            "Spent",
            f"{_units(spend['today'])} today",
            f" · {_units(spend['7d'])} in 7 days · {_units(spend['30d'])} in 30 days",
        )
    )
    return lines


MACHINE_COLUMNS = [  # (heading, key, minimum width at which to keep it, right-aligned)
    ("MACHINE", "name", 0, False),
    ("STATUS", "status", 0, False),
    ("HARDWARE", "hardware", 70, False),
    ("UPTIME", "uptime", 0, False),
    ("IDLE", "idle", 80, False),
    ("RATE", "rate", 90, True),
    ("JOB", "job", 0, False),
]


def _machine_lines(report: dict, width: int) -> list[Line]:
    machines = report["machines"]
    if not machines:
        return [[("No machines are running.", "dim")]]
    rows = []
    for m in machines:
        rows.append(
            {
                "name": m["name"] or m["endpoint"],
                "status": STATUS_WORDS.get(m["status"], m["status"] or "unknown"),
                "status_key": m["status"],
                "hardware": m["hardware"],
                "uptime": _duration(m["uptime_s"]),
                "idle": _duration(m["idle_s"]) if m["idle_s"] else "-",
                "rate": _rate(m["rate"], m["rate_estimated"]),
                "job": m["job"] or "-",
            }
        )
    columns = [c for c in MACHINE_COLUMNS if width >= c[2]]
    widths = {key: max(len(heading), *(len(r[key]) for r in rows)) for heading, key, _, _ in columns}
    widths["name"] = min(widths["name"], 24)
    lines: list[Line] = []

    def cell(key: str, text: str, right: bool, last: bool) -> str:
        if len(text) > widths[key] and not last:
            text = text[: widths[key] - 1] + "…"
        if last:
            return text
        return (text.rjust(widths[key]) if right else text.ljust(widths[key])) + "  "

    last = len(columns) - 1
    lines.append(
        [(cell(key, heading, right, i == last), "dim") for i, (heading, key, _, right) in enumerate(columns)]
    )
    for r in rows:
        line: Line = []
        for i, (_, key, _, right) in enumerate(columns):
            style = STATUS_COLORS.get(r["status_key"]) if key == "status" else None
            line.append((cell(key, r[key], right, i == last), style))
        lines.append(line)
    return lines


def _ago(seconds: float) -> str:
    return "just now" if seconds < 5 else f"{metrics.human_duration(seconds)} ago"


def _job_lines(report: dict, width: int) -> list[Line]:
    jobs = sorted(
        report["jobs"], key=lambda j: j["silent_s"] if j.get("silent_s") is not None else float("inf")
    )
    if not jobs:
        return [[("No job logs found.", "dim")]]
    shown = jobs[:MAX_JOBS_SHOWN]
    lines: list[Line] = []
    name_width = min(28, max(len(j["name"]) for j in shown))
    for job in shown:
        facts = []
        if job.get("progress") is not None:
            facts.append(f"{int(job['progress'] * 100)}%")  # rounded down, like tqdm
        if job.get("eta_s"):
            facts.append(f"ETA {metrics.human_duration(job['eta_s'])}")
        if job.get("speed"):
            facts.append(job["speed"])
        facts += [f"{k} {v:g}" for k, v in list((job.get("metrics") or {}).items())[:3]]
        name = job["name"] if len(job["name"]) <= name_width else job["name"][: name_width - 1] + "…"
        line: Line = [(name.ljust(name_width) + "  ", None)]
        if job.get("stalled"):
            line.append((f"stalled {_duration(job['silent_s'])}  ", "yellow"))
        line.append(("  ".join(facts) or "no progress printed", None if facts else "dim"))
        notes = []
        if job.get("session"):
            notes.append(f"on {job['session']}")
        if not job.get("stalled") and job.get("silent_s") is not None:
            notes.append(f"updated {_ago(job['silent_s'])}")
        if notes:
            line.append(("  · " + ", ".join(notes), "dim"))
        lines.append(line)
        if job.get("last_error"):
            lines.append([(" " * (name_width + 2), None), (job["last_error"], "red")])
    if len(jobs) > len(shown):
        lines.append(
            [(f"and {len(jobs) - len(shown)} older log{'s' if len(jobs) - len(shown) > 1 else ''}", "dim")]
        )
    return lines


def _attention_lines(report: dict, width: int) -> list[Line]:
    items = report["attention"]
    if not items:
        return [[("Nothing needs attention.", "green")]]
    lines: list[Line] = [[(f"NEEDS ATTENTION ({len(items)})", "bold")]]
    for item in items:
        critical = item["severity"] == "critical"
        mark, style = ("✕ ", "red") if critical else ("! ", "yellow")
        wrapped = textwrap.wrap(item["message"], width=max(10, width - 4)) or [""]
        lines.append([("  ", None), (mark, style), (wrapped[0], None)])
        lines += [[("    " + rest, None)] for rest in wrapped[1:]]
    return lines


def _footer_lines(report: dict) -> list[Line]:
    runs = report["runs"]
    parts = []
    day, week = runs["24h"], runs["7d"]
    parts.append(
        f"Runs: {day['ok']} ok, {day['failed']} failed in 24 h; "
        f"{week['ok']} ok, {week['failed']} failed in 7 days"
    )
    hours = report["machine_hours_7d"]
    if hours:
        parts.append("Machine hours (7 days): " + ", ".join(f"{k} {v:.1f}" for k, v in sorted(hours.items())))
    return [[(p, "dim")] for p in parts]


def render(report: dict, width: int = 80, color: bool = False, now: float | None = None) -> str:
    """The `status` and `watch` text. No line is wider than `width` columns."""
    now = time.time() if now is None else now
    width = max(20, width)
    blank: Line = [("", None)]
    sections = [
        _summary_lines(report, now),
        _machine_lines(report, width),
        [[("JOBS", "bold")], *_job_lines(report, width)],
        _footer_lines(report),
        _attention_lines(report, width),
    ]
    lines: list[Line] = []
    for section in sections:
        if lines:
            lines.append(blank)
        lines += section
    return "\n".join(_paint(_fit(line, width), color) for line in lines) + "\n"


def _stdout_is_tty() -> bool:
    return sys.stdout.isatty()


def _use_color(args: argparse.Namespace) -> bool:
    if args.no_color or os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    return _stdout_is_tty()


def _width() -> int:
    return shutil.get_terminal_size((100, 24)).columns


# ---------- status ----------


def status(argv: list[str]) -> int:
    p = _parser("status", "Print what is running, what it costs, and what needs attention, then exit.")
    p.add_argument("--json", action="store_true", help="print the report as JSON (schema 1)")
    p.add_argument(
        "--exit-code",
        action="store_true",
        help=f"exit with {EXIT_ATTENTION} if something needs attention, so scripts can act on it",
    )
    p.add_argument("--version", action="version", version=f"colab-monitor {__version__}")
    args = _parse(p, argv)
    source, state = _open_source(args)
    source.close()
    report = build_report(state, source.name)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render(report, width=_width(), color=_use_color(args)), end="")
    return EXIT_ATTENTION if args.exit_code and report["attention"] else 0


# ---------- watch ----------


@contextlib.contextmanager
def _screen():
    """Alternate screen, hidden cursor, no echo. Everything is put back on the way out."""
    import termios
    import tty

    saved = None
    if sys.stdin.isatty():
        saved = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin)  # keys arrive one at a time without echo; Ctrl-C still works
    sys.stdout.write("\x1b[?1049h\x1b[?25l")
    sys.stdout.flush()
    try:
        yield
    finally:
        sys.stdout.write("\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()
        if saved is not None:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, saved)


def _frame(text: str, footer: str, height: int) -> str:
    lines = text.rstrip("\n").split("\n")
    lines = [*lines[: max(1, height - 2)], "", footer]
    return "\x1b[H" + "".join(line + "\x1b[K\n" for line in lines[:-1]) + lines[-1] + "\x1b[K\x1b[J"


def watch(argv: list[str]) -> int:
    p = _parser("watch", "Keep the status summary on screen. Press q or Ctrl-C to quit.")
    p.add_argument(
        "--refresh",
        type=float,
        default=5.0,
        metavar="SECONDS",
        help="seconds between redraws, at least 1 (default: 5)",
    )
    p.add_argument("--version", action="version", version=f"colab-monitor {__version__}")
    args = _parse(p, argv)
    if args.refresh < 1:
        p.error("--refresh must be at least 1 second")
    if not _stdout_is_tty():
        print("colab-monitor watch needs a terminal. Use `colab-monitor status` in scripts.", file=sys.stderr)
        return 2

    source, state = _open_source(args, keep_polling=True)
    color = _use_color(args)
    wake_r, wake_w = os.pipe()  # a resize or SIGTERM writes here, so the wait below ends at once
    os.set_blocking(wake_w, False)
    quit_now = threading.Event()

    def on_signal(signum, _frame):
        if signum == signal.SIGTERM:
            quit_now.set()
        with contextlib.suppress(OSError):
            os.write(wake_w, b"x")

    previous = {sig: signal.signal(sig, on_signal) for sig in (signal.SIGWINCH, signal.SIGTERM)}
    error = None
    try:
        with _screen():
            while not quit_now.is_set():
                size = shutil.get_terminal_size((100, 24))
                text = render(build_report(state, source.name), width=size.columns, color=color)
                where = "the dashboard" if source.name == "dashboard" else "local files and Colab"
                footer = f"Updated {time.strftime('%H:%M:%S')} from {where} · q to quit"
                if error:
                    footer = f"Can't refresh: {error} · q to quit"
                sys.stdout.write(_frame(text, footer[: size.columns], size.lines))
                sys.stdout.flush()
                if _wait_for_key(wake_r, args.refresh) == "q":
                    break
                try:
                    state, error = source.state(), None
                except _DASHBOARD_ERRORS as e:
                    error = str(e)
    except KeyboardInterrupt:
        pass
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        os.close(wake_r)
        os.close(wake_w)
        source.close()
    return 0


def _wait_for_key(wake_fd: int, timeout: float) -> str | None:
    """Wait up to `timeout` seconds. Returns a key pressed, or None."""
    fds = [wake_fd] + ([sys.stdin] if sys.stdin.isatty() else [])
    ready, _, _ = select.select(fds, [], [], timeout)
    if wake_fd in ready:
        os.read(wake_fd, 64)
    if sys.stdin in ready:
        return os.read(sys.stdin.fileno(), 32).decode(errors="replace")[-1:].lower()
    return None


COMMANDS = {"serve": server.main, "status": status, "watch": watch}
