"""HTTP server and command-line entry point for colab-monitor."""

import argparse
import dataclasses
import datetime
import importlib.resources
import ipaddress
import json
import os
import sys
import threading
import time
import webbrowser
from collections.abc import Iterable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from colab_monitor import __version__, metrics, sources
from colab_monitor.poller import MIN_INTERVAL, ApiPoller
from colab_monitor.usage_log import DEFAULT_PATH as DEFAULT_USAGE_LOG
from colab_monitor.usage_log import RETENTION_SECONDS, UsageLog, downsample

DEFAULT_PORT = 26522  # "COLAB" on a phone keypad; clear of common dev ports and ephemeral ranges
DEFAULT_LOG_DIR = "~/colab-runs"
USAGE_RANGES = {"1h": 3600, "24h": 86400, "7d": 7 * 86400, "30d": 30 * 86400}
MAX_CHART_POINTS = 360


def _clamp_int(value: str | None, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


class Dashboard:
    """Routes API requests; independent of the HTTP plumbing so it's easy to test."""

    def __init__(
        self,
        poller: ApiPoller | None,
        sessions_path: str | Iterable[str] | None = None,
        history_dir: str = sources.DEFAULT_HISTORY_DIR,
        log_files: Iterable[str] = (),
        log_dirs: Iterable[str] = (),
        usage_log: UsageLog | None = None,
        auth: str | None = None,
        thresholds: metrics.Thresholds = metrics.Thresholds(),  # noqa: B008 - frozen dataclass
    ):
        self.poller = poller
        self.usage_log = usage_log
        self.auth = auth
        # One state file or several: agents isolate runs with `colab --config FILE`.
        if sessions_path is None:
            self.sessions_paths = [os.path.expanduser(sources.DEFAULT_SESSIONS_PATH)]
        elif isinstance(sessions_path, str):
            self.sessions_paths = [sessions_path]
        else:
            self.sessions_paths = list(sessions_path)
        self.history_dir = history_dir
        self.log_files = list(log_files)
        self.log_dirs = list(log_dirs)
        self.thresholds = thresholds

    def handle(self, path: str, query: dict) -> tuple[int, dict]:
        if path == "/api/state":
            try:
                thresholds = self._thresholds(query)
            except ValueError as e:
                return 400, {"error": str(e)}
            return 200, self._state(thresholds)
        if path == "/api/log":
            return self._log(query)
        if path == "/api/history":
            return self._history(query)
        if path == "/api/usage":
            return self._usage(query)
        if path == "/api/activity":
            limit = _clamp_int(query.get("limit"), 20, 1, 200)
            return 200, {"events": sources.recent_activity(self.history_dir, limit=limit)}
        return 404, {"error": "not found"}

    def _thresholds(self, query: dict) -> metrics.Thresholds:
        """Alert thresholds: the dashboard's defaults, overridden per request by the query."""
        values = {}
        for param, field in (
            ("idle_alert", "idle_minutes"),
            ("stall_alert", "stall_minutes"),
            ("runway_alert", "runway_hours"),
        ):
            if param in query:
                try:
                    value = float(query[param])
                except ValueError:
                    value = -1.0
                if not value > 0:
                    raise ValueError(f"{param} must be a positive number")
                values[field] = value
        return dataclasses.replace(self.thresholds, **values)

    def _state(self, thresholds: metrics.Thresholds | None = None) -> dict:
        thresholds = thresholds or self.thresholds
        if self.poller is None:
            api = {"enabled": False, "usage": None, "assignments": None, "error": None}
        else:
            api = {"enabled": True, **self.poller.snapshot()}
        local = sources.local_sessions(self.sessions_paths)
        sessions = sources.merge_sessions(
            local, api["assignments"], sources.history_endpoints(self.history_dir)
        )
        api.pop("assignments")
        logs = sources.discover_logs(self.log_files, self.log_dirs)
        now = time.time()
        samples = self.usage_log.read(since=now - 30 * 86400) if self.usage_log else []
        insights = metrics.compute_insights(
            sessions,
            sources.session_timelines(self.history_dir),
            samples,
            sources.log_tails(logs),
            api.get("usage"),
            now=now,
            thresholds=thresholds,
        )
        machines = insights.pop("machines")
        for s in sessions:
            s["metrics"] = machines.get(s["endpoint"])
        return {
            "version": __version__,
            "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
            "api": api,
            "sessions": sessions,
            "logs": logs,
            "insights": insights,
            "log_dirs": self.log_dirs,
            "history": sources.history_names(self.history_dir),
            "config": {
                "api_enabled": self.poller is not None,
                "interval": self.poller.base_interval if self.poller else None,
                "auth": self.auth,
                "log_files": self.log_files,
                "log_dirs": self.log_dirs,
                "history_dir": self.history_dir,
                "sessions_paths": self.sessions_paths,
                "usage_log": self.usage_log.path if self.usage_log else None,
            },
        }

    def _usage(self, query: dict) -> tuple[int, dict]:
        key = query.get("range", "24h")
        if key not in USAGE_RANGES:
            return 400, {"error": f"range must be one of {', '.join(USAGE_RANGES)}"}
        if self.usage_log is None:
            return 200, {"range": key, "points": []}
        since = time.time() - USAGE_RANGES[key]
        points = downsample(self.usage_log.read(since=since), MAX_CHART_POINTS)
        return 200, {"range": key, "points": points}

    def _log(self, query: dict) -> tuple[int, dict]:
        path = query.get("path")
        if not path:
            return 400, {"error": "missing path"}
        if not sources.is_allowed_log(path, self.log_files, self.log_dirs):
            return 403, {"error": "not a configured log file"}
        lines = _clamp_int(query.get("lines"), 300, 1, 5000)
        return 200, {"path": path, "lines": sources.tail_lines(path, max_lines=lines)}

    def _history(self, query: dict) -> tuple[int, dict]:
        name = query.get("session", "")
        limit = _clamp_int(query.get("limit"), 50, 1, 500)
        try:
            events = sources.read_history(self.history_dir, name, limit=limit)
        except ValueError as e:
            return 400, {"error": str(e)}
        return 200, {"session": name, "events": events}


# Only these files are served; anything else under static/ stays private.
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/theme.js": ("theme.js", "text/javascript; charset=utf-8"),
    "/icon.svg": ("icon.svg", "image/svg+xml"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
    "/apple-touch-icon.png": ("apple-touch-icon.png", "image/png"),
    "/fonts/Geist-Variable.woff2": ("fonts/Geist-Variable.woff2", "font/woff2"),
    "/fonts/GeistMono-Variable.woff2": ("fonts/GeistMono-Variable.woff2", "font/woff2"),
}
# The page loads nothing from other origins and runs no inline scripts.
CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",  # style="" attributes in the markup
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'none'",
    ]
)


def _static(name: str) -> bytes:
    return importlib.resources.files("colab_monitor").joinpath(f"static/{name}").read_bytes()


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def make_server(app: Dashboard, host: str, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        server_version = f"colab-monitor/{__version__}"

        def _host_ok(self) -> bool:
            # Blocks DNS-rebinding pages from reading your logs while bound to loopback.
            if not _is_loopback(host):
                return True
            header = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
            return _is_loopback(header)

        def _send(self, status: int, body: bytes, content_type: str, cache: str = "no-store"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            if content_type.startswith("text/html"):
                self.send_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self._host_ok():
                self._send(403, b"forbidden host\n", "text/plain; charset=utf-8")
                return
            url = urlparse(self.path)
            if url.path in STATIC_FILES:
                name, content_type = STATIC_FILES[url.path]
                # Fonts never change between releases; everything else is re-read so edits show up on reload.
                cache = "public, max-age=604800" if name.startswith("fonts/") else "no-store"
                self._send(200, _static(name), content_type, cache)
                return
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            status, payload = app.handle(url.path, query)
            self._send(status, json.dumps(payload).encode(), "application/json")

        def log_message(self, format, *args):
            pass  # the page polls every few seconds; keep the terminal quiet

    return ThreadingHTTPServer((host, port), Handler)


def _enum_name(value) -> str:
    return getattr(value, "name", None) or str(value)


def _colab_fetchers(client):
    def usage():
        info = client.get_consumption_user_info()
        return {
            "balance": info.paid_compute_units_balance,
            "rate_per_hour": info.consumption_rate_hourly,
            "assignments_count": info.assignments_count,
        }

    def assignments():
        # Deliberately drops runtime_proxy_info: it holds the VM access token.
        return [
            {
                "endpoint": a.endpoint,
                "accelerator": _enum_name(a.accelerator),
                "variant": _enum_name(a.variant),
                "machine_shape": _enum_name(a.machine_shape),
            }
            for a in client.list_assignments()
        ]

    return usage, assignments


def add_data_options(p: argparse.ArgumentParser) -> None:
    """Options that say where Colab Monitor reads from. Shared by every command."""
    p.add_argument(
        "--log",
        action="append",
        default=[],
        metavar="FILE",
        help="a job output file to show (repeatable)",
    )
    p.add_argument(
        "--log-dir",
        action="append",
        default=None,
        metavar="DIR",
        help=f"show every *.log/*.out/*.err in DIR (repeatable, default: {DEFAULT_LOG_DIR})",
    )
    p.add_argument(
        "--config",
        action="append",
        default=None,
        metavar="FILE",
        help="colab CLI session state file, repeatable to match `colab --config` "
        "(default: ~/.config/colab-cli/sessions.json)",
    )
    p.add_argument(
        "--history-dir",
        default=sources.DEFAULT_HISTORY_DIR,
        help="colab CLI history directory (default: ~/.config/colab-cli/history)",
    )
    p.add_argument(
        "--auth", choices=["oauth2", "adc"], default="oauth2", help="same as colab --auth (default: oauth2)"
    )
    p.add_argument(
        "-c",
        "--client-oauth-config",
        default=os.path.expanduser("~/.colab-cli-oauth-config.json"),
        help="same as colab -c",
    )
    p.add_argument(
        "--usage-log",
        default=DEFAULT_USAGE_LOG,
        help="where chart samples are kept (default: ~/.config/colab-monitor/usage.jsonl)",
    )
    p.add_argument("--no-api", action="store_true", help="never call Colab; show local files only")


def add_threshold_options(p: argparse.ArgumentParser) -> None:
    """When a machine, job, or the balance needs attention. Unset means the default."""
    d = metrics.Thresholds()
    p.add_argument(
        "--idle-alert",
        type=float,
        metavar="MINUTES",
        help=f"flag machines idle for this long (default: {d.idle_minutes:g})",
    )
    p.add_argument(
        "--stall-alert",
        type=float,
        metavar="MINUTES",
        help=f"flag running jobs whose log is silent for this long (default: {d.stall_minutes:g})",
    )
    p.add_argument(
        "--runway-alert",
        type=float,
        metavar="HOURS",
        help=f"flag when compute units run out within this time (default: {d.runway_hours:g})",
    )


def finish_args(p: argparse.ArgumentParser, args: argparse.Namespace) -> argparse.Namespace:
    """Validate and normalise the shared options."""
    for name in ("idle_alert", "stall_alert", "runway_alert"):
        value = getattr(args, name, None)
        if value is not None and not value > 0:
            p.error(f"--{name.replace('_', '-')} must be a positive number")
    if args.log_dir is None:
        args.log_dir = [DEFAULT_LOG_DIR]
    args.config = [os.path.expanduser(c) for c in (args.config or [sources.DEFAULT_SESSIONS_PATH])]
    args.log_dir = [os.path.expanduser(d) for d in args.log_dir]
    return args


def thresholds_from(args: argparse.Namespace) -> metrics.Thresholds:
    d = metrics.Thresholds()
    return metrics.Thresholds(
        idle_minutes=args.idle_alert or d.idle_minutes,
        stall_minutes=args.stall_alert or d.stall_minutes,
        runway_hours=args.runway_alert or d.runway_hours,
    )


def _parse_args(argv):
    p = argparse.ArgumentParser(
        prog="colab-monitor serve",
        description="Start the web dashboard. This is the default when no command is given.",
    )
    p.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port (default: {DEFAULT_PORT})")
    p.add_argument(
        "--interval",
        type=float,
        default=60.0,
        help=f"seconds between Colab API checks, min {MIN_INTERVAL:.0f} (default: 60)",
    )
    add_data_options(p)
    add_threshold_options(p)
    p.add_argument("--open", action="store_true", help="open the dashboard in a browser")
    p.add_argument("--version", action="version", version=f"colab-monitor {__version__}")
    args = p.parse_args(argv)
    if args.interval < MIN_INTERVAL:
        p.error(f"--interval must be at least {MIN_INTERVAL:.0f} seconds")
    return finish_args(p, args)


def _err(message: str) -> None:
    print(f"[colab-monitor] {message}", file=sys.stderr)


def _is_colab_monitor(host: str, port: int) -> bool:
    """True if whatever is listening on host:port is a Colab Monitor server."""
    import urllib.request

    probe = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    try:
        with urllib.request.urlopen(f"http://{probe}:{port}/api/state", timeout=2) as resp:
            return (resp.headers.get("Server") or "").startswith("colab-monitor/")
    except OSError:
        return False


def _connect_to_colab(args, usage_log: UsageLog) -> ApiPoller:
    from colab_cli.auth import AuthProvider, get_credentials
    from colab_cli.client import Client, Prod

    # Signs in here, in the foreground, so any sign-in prompt shows in this terminal.
    session = get_credentials(args.client_oauth_config, provider=AuthProvider(args.auth))
    fetch_usage, fetch_assignments = _colab_fetchers(Client(Prod(), session))
    poller = ApiPoller(fetch_usage, fetch_assignments, interval=args.interval, on_sample=usage_log.append)
    poller.poll_once()
    if poller.snapshot()["error"]:
        _err(f"First Colab check failed, retrying in the background: {poller.snapshot()['error']}")
    return poller


def main(argv=None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    usage_log = UsageLog(os.path.expanduser(args.usage_log))
    usage_log.prune(before=time.time() - RETENTION_SECONDS)
    app = Dashboard(
        poller=None,
        sessions_path=args.config,
        history_dir=args.history_dir,
        log_files=args.log,
        log_dirs=args.log_dir,
        usage_log=usage_log,
        auth=None if args.no_api else args.auth,
        thresholds=thresholds_from(args),
    )

    # Claim the port before signing in, so a clash is reported straight away.
    try:
        server = make_server(app, args.host, args.port)
    except OSError as e:
        if e.errno in (48, 98) and _is_colab_monitor(args.host, args.port):  # EADDRINUSE on macOS / Linux
            url = f"http://{'localhost' if _is_loopback(args.host) else args.host}:{args.port}/"
            _err(f"Colab Monitor is already running at {url}")
            if args.open:
                webbrowser.open(url)
            return 0
        if e.errno in (48, 98):
            _err(f"Port {args.port} is used by another program.")
            _err(f"Try another port, for example --port {args.port + 1}")
        else:
            _err(f"Can't listen on {args.host}:{args.port}: {e.strerror or e}")
        return 1

    stop = threading.Event()
    if not args.no_api:
        try:
            app.poller = _connect_to_colab(args, usage_log)
        except (Exception, SystemExit) as e:  # noqa: BLE001 - any sign-in failure gets the same advice; colab_cli exits on some
            server.server_close()
            _err(f"Couldn't sign in to Colab: {e}")
            _err("Run `colab sessions` once to sign in, or start with --no-api to show local files only.")
            return 1
        poller = app.poller
        threading.Thread(target=lambda: (stop.wait(args.interval), poller.run(stop)), daemon=True).start()

    shown_host = "localhost" if _is_loopback(args.host) else args.host
    url = f"http://{shown_host}:{server.server_address[1]}/"
    _err(f"Serving {url}  (Ctrl-C to stop)")
    if not _is_loopback(args.host):
        _err("Warning: not bound to localhost; anyone who can reach this port can read your logs.")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _err("Stopped.")
    finally:
        stop.set()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
