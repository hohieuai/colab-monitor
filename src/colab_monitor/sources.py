"""Read-only views of the colab CLI's local files.

Nothing here talks to Colab, so these can be called on every page refresh.
Session tokens and runtime proxy URLs never leave this module.
"""

import collections
import json
import os
import re
from collections.abc import Iterable

from colab_cli.state import StateStore

DEFAULT_HISTORY_DIR = os.path.expanduser("~/.config/colab-cli/history")
LOG_SUFFIXES = (".log", ".out", ".err")
MAX_CODE_CHARS = 2_000
MAX_OUTPUT_CHARS = 4_000

_SESSION_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
# Terminal colour and cursor codes (Python tracebacks from Colab are full of them).
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07")


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def local_sessions(config_path: str | None = None) -> list[dict]:
    """Sessions the CLI knows about, from sessions.json, without secrets."""
    path = config_path or os.path.expanduser("~/.config/colab-cli/sessions.json")
    # Check first: StateStore creates its lock file and folders, and fails if the folder is
    # missing. Colab Monitor is read-only, so a machine without CLI state just has no sessions.
    if not os.path.exists(path):
        return []
    result = []
    for s in StateStore(path).list().values():
        last = None
        if s.last_execution:
            source, _, when = s.last_execution
            last = {"source": source, "time": when}
        result.append(
            {
                "name": s.name,
                "endpoint": s.endpoint,
                "variant": s.variant,
                "accelerator": s.accelerator,
                "machine_shape": s.machine_shape,
                "running": s.running,
                "last_execution": last,
            }
        )
    return result


def merge_sessions(
    local: list[dict], assignments: list[dict] | None, known: dict | None = None
) -> list[dict]:
    """Join local sessions with server assignments by endpoint.

    Status is one of: busy, idle (on the server and known locally), stopping
    (stopped by the CLI, but the cached server list still has it), orphan (on
    the server but unknown locally, still billing), gone (known locally but no
    longer on the server), unknown (server state not fetched yet).

    `known` maps endpoints from session history to {"name", "ended"}; it names
    orphans and stops a just-stopped machine from looking like one.
    """
    known = known or {}
    if assignments is None:
        return [{**s, "status": "unknown"} for s in local]

    by_endpoint = {a["endpoint"]: a for a in assignments}
    merged = []
    for s in local:
        server = by_endpoint.pop(s["endpoint"], None)
        if server is None:
            merged.append({**s, "status": "gone"})
        else:
            status = "busy" if s.get("running") else "idle"
            merged.append({**s, **server, "status": status})
    for server in by_endpoint.values():
        hist = known.get(server["endpoint"])
        status = "stopping" if hist and hist["ended"] else "orphan"
        merged.append({"name": hist["name"] if hist else None, **server, "status": status})
    return merged


def tail_lines(path: str, max_lines: int = 200, max_bytes: int = 256 * 1024) -> list[str]:
    """Last lines of a text file, reading at most max_bytes from its end.

    Carriage returns (tqdm-style progress bars) collapse to their final state.
    """
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            start = max(0, size - max_bytes)
            f.seek(start)
            data = f.read()
    except OSError:
        return []

    text = strip_ansi(data.decode("utf-8", errors="replace"))
    lines = text.split("\n")
    if start > 0:
        lines = lines[1:]  # first line is probably cut in half
    if lines and lines[-1] == "":
        lines = lines[:-1]
    lines = [line.rstrip("\r").split("\r")[-1] for line in lines]
    return lines[-max_lines:]


def _log_entry(path: str) -> dict:
    try:
        st = os.stat(path)
        return {
            "path": path,
            "name": os.path.basename(path),
            "exists": True,
            "size": st.st_size,
            "mtime": st.st_mtime,
        }
    except OSError:
        return {
            "path": path,
            "name": os.path.basename(path),
            "exists": False,
            "size": 0,
            "mtime": None,
        }


def discover_logs(files: Iterable[str], dirs: Iterable[str]) -> list[dict]:
    """Explicit log files plus *.log/*.out/*.err directly inside log dirs."""
    paths = [os.path.abspath(os.path.expanduser(p)) for p in files]
    for d in dirs:
        d = os.path.abspath(os.path.expanduser(d))
        try:
            names = os.listdir(d)
        except OSError:
            continue
        paths.extend(os.path.join(d, n) for n in names if n.endswith(LOG_SUFFIXES))

    seen = set()
    entries = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            entries.append(_log_entry(p))
    entries.sort(key=lambda e: e["name"].lower())  # stable, so the list never jumps while jobs write
    return entries


def is_allowed_log(path: str, files: Iterable[str], dirs: Iterable[str]) -> bool:
    """Only configured files, or log files directly inside configured dirs."""
    real = os.path.realpath(os.path.expanduser(path))
    if real in {os.path.realpath(os.path.expanduser(f)) for f in files}:
        return True
    if not real.endswith(LOG_SUFFIXES):
        return False
    parent = os.path.dirname(real)
    return parent in {os.path.realpath(os.path.expanduser(d)) for d in dirs}


def history_names(history_dir: str = DEFAULT_HISTORY_DIR) -> list[str]:
    """Session names with a history file, most recently written first."""
    try:
        names = [n for n in os.listdir(history_dir) if n.endswith(".jsonl")]
    except OSError:
        return []
    names.sort(key=lambda n: os.path.getmtime(os.path.join(history_dir, n)), reverse=True)
    return [n[: -len(".jsonl")] for n in names]


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + f"… [{len(text) - limit} more chars]"


def summarize_event(event: dict) -> dict:
    """Small, display-ready form of one history event (images are counted, not sent)."""
    summary = {
        "timestamp": event.get("timestamp"),
        "type": event.get("event_type"),
    }
    if "code" in event:
        summary["code"] = _truncate(strip_ansi(str(event["code"])), MAX_CODE_CHARS)

    outputs = event.get("outputs")
    if isinstance(outputs, list):
        text = []
        images = 0
        error = None
        for out in outputs:
            kind = out.get("output_type")
            if kind == "stream":
                text.append(out.get("text", ""))
            elif kind in ("execute_result", "display_data"):
                data = out.get("data", {})
                if any(k.startswith("image/") for k in data):
                    images += 1
                elif "text/plain" in data:
                    text.append(str(data["text/plain"]) + "\n")
            elif kind == "error":
                error = strip_ansi(f"{out.get('ename', 'Error')}: {out.get('evalue', '')}")
        summary["output"] = _truncate(strip_ansi("".join(text)), MAX_OUTPUT_CHARS)
        summary["images"] = images
        summary["error"] = error

    details = {
        k: v
        for k, v in event.items()
        if k not in ("timestamp", "event_type", "code", "outputs") and isinstance(v, (str, int, float, bool))
    }
    if details:
        summary["details"] = details
    return summary


def read_history(history_dir: str, name: str, limit: int = 50) -> list[dict]:
    """Latest `limit` events of one session's history, summarised."""
    if not _SESSION_NAME.match(name):
        raise ValueError(f"invalid session name: {name!r}")
    path = os.path.join(history_dir, f"{name}.jsonl")
    events = collections.deque(maxlen=limit)
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError:
        return []
    return [summarize_event(e) for e in events]


def recent_activity(history_dir: str = DEFAULT_HISTORY_DIR, limit: int = 20) -> list[dict]:
    """Latest events across every session's history, newest first."""
    events = []
    for name in history_names(history_dir):
        for event in read_history(history_dir, name, limit=limit):
            events.append({"session": name, **event})
    events.sort(key=lambda e: e.get("timestamp") or "", reverse=True)
    return events[:limit]


# (path) -> (mtime, size, result); history files only grow, so this skips re-reading unchanged ones.
_endpoint_cache: dict[str, tuple[float, int, dict]] = {}


def _endpoints_in_file(path: str, name: str) -> dict:
    found: dict = {}
    current = None
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if '"session_' not in line:
                    continue  # skip big execution events without parsing them
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = event.get("event_type")
                if kind == "session_created" and event.get("endpoint"):
                    current = event["endpoint"]
                    found[current] = {"name": name, "ended": False}
                elif kind == "session_terminated" and current:
                    found[current]["ended"] = True
    except OSError:
        return {}
    return found


def history_endpoints(history_dir: str = DEFAULT_HISTORY_DIR) -> dict:
    """Endpoint -> {"name", "ended"} for every session recorded in history."""
    result: dict = {}
    for name in history_names(history_dir):
        path = os.path.join(history_dir, f"{name}.jsonl")
        try:
            st = os.stat(path)
        except OSError:
            continue
        cached = _endpoint_cache.get(path)
        if cached and cached[0] == st.st_mtime and cached[1] == st.st_size:
            found = cached[2]
        else:
            found = _endpoints_in_file(path, name)
            _endpoint_cache[path] = (st.st_mtime, st.st_size, found)
        for endpoint, info in found.items():
            result.setdefault(endpoint, info)
    return result
