"""Read-only views of the colab CLI's local files.

Nothing here talks to Colab, so these can be called on every page refresh.
Session tokens and runtime proxy URLs never leave this module.
"""

import collections
import datetime
import json
import os
import re
import time
from collections.abc import Iterable

from colab_cli.state import StateStore

DEFAULT_HISTORY_DIR = os.path.expanduser("~/.config/colab-cli/history")
LOG_SUFFIXES = (".log", ".out", ".err")
MAX_CODE_CHARS = 2_000
MAX_OUTPUT_CHARS = 4_000

# The colab CLI accepts any session name, and names its history file after it. Refuse only names
# that are not a plain file name in the history folder.
_UNSAFE_NAME = re.compile(r"[/\\\x00]|^\.")


def _is_session_name(name: str) -> bool:
    return bool(name) and not _UNSAFE_NAME.search(name)


# Terminal escape codes: colours and cursor moves (Python tracebacks from Colab are full of them),
# window titles and links ended by BEL or ESC \, and two-character codes such as a reset (ESC c).
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-~]")


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def _json_objects(lines):
    """The JSON objects among `lines`. Blank lines, broken JSON, and other JSON values are skipped."""
    for line in lines:
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            yield value


# Expanded when used, not at import, so a changed HOME (tests, sandboxes) is respected.
DEFAULT_SESSIONS_PATH = "~/.config/colab-cli/sessions.json"


def local_sessions(config_paths: str | Iterable[str] | None = None) -> list[dict]:
    """Sessions the CLI knows about, without secrets.

    Agents often isolate their runs with `colab --config FILE`, so this reads several state files
    and lists each machine once, from the first file that has it.
    """
    if config_paths is None:
        config_paths = [DEFAULT_SESSIONS_PATH]
    elif isinstance(config_paths, str):
        config_paths = [config_paths]
    result: list[dict] = []
    seen: set[str] = set()
    for path in config_paths:
        for session in _sessions_in(os.path.expanduser(path)):
            if session["endpoint"] not in seen:
                seen.add(session["endpoint"])
                result.append(session)
    return result


def _sessions_in(path: str) -> list[dict]:
    # Check first: StateStore creates its lock file and folders, and fails if the folder is
    # missing. Colab Monitor is read-only, so a missing file just has no sessions.
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


# How long Colab may keep listing a machine that the CLI stopped before it counts as an orphan.
# The CLI records the stop even when its unassign request fails, and Colab then keeps billing.
STOPPING_GRACE_SECONDS = 10 * 60


def merge_sessions(
    local: list[dict], assignments: list[dict] | None, known: dict | None = None, now: float | None = None
) -> list[dict]:
    """Join local sessions with server assignments by endpoint.

    Status is one of: busy, idle (on the server and known locally), stopping
    (stopped by the CLI, but the cached server list still has it), orphan (on
    the server but unknown locally, still billing), gone (known locally but no
    longer on the server), unknown (server state not fetched yet).

    `known` maps endpoints from session history to {"name", "ended"}, where `ended` is when the CLI
    stopped the machine, or None. It names orphans and stops a just-stopped machine from looking
    like one. A machine still listed STOPPING_GRACE_SECONDS after it was stopped is an orphan.
    """
    known = known or {}
    now = time.time() if now is None else now
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
        ended = hist["ended"] if hist else None
        status = "stopping" if ended and now - ended <= STOPPING_GRACE_SECONDS else "orphan"
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
    if start > 0 and len(lines) > 1:
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
    dirs = list(dirs)
    paths = [os.path.abspath(os.path.expanduser(p)) for p in files]
    for d in dirs:
        d = os.path.abspath(os.path.expanduser(d))
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for name in names:
            path = os.path.join(d, name)
            # List only what /api/log serves, so a symlink that leads out of the folder is left out.
            if name.endswith(LOG_SUFFIXES) and resolve_log(path, [], dirs):
                paths.append(path)

    seen = set()
    entries = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            entries.append(_log_entry(p))
    entries.sort(key=lambda e: e["name"].lower())  # stable, so the list never jumps while jobs write
    return entries


def resolve_log(path: str, files: Iterable[str], dirs: Iterable[str]) -> str | None:
    """The real path to read for `path`, or None unless it is a configured log file.

    A configured file is one passed with --log, or a .log/.out/.err file directly inside a --log-dir
    folder, judged by where symlinks lead. Callers read the returned path, so the file checked is the
    file read.
    """
    try:
        real = os.path.realpath(os.path.expanduser(path))
        if real in {os.path.realpath(os.path.expanduser(f)) for f in files}:
            return real
        if not real.endswith(LOG_SUFFIXES):
            return None
        dirs_real = {os.path.realpath(os.path.expanduser(d)) for d in dirs}
    except ValueError:  # a path the OS can't hold, such as one with a NUL byte
        return None
    return real if os.path.dirname(real) in dirs_real else None


def history_names(history_dir: str = DEFAULT_HISTORY_DIR) -> list[str]:
    """Session names with a history file, most recently written first."""
    try:
        names = [n for n in os.listdir(history_dir) if n.endswith(".jsonl") and _is_session_name(n)]
    except OSError:
        return []
    names.sort(key=lambda n: os.path.getmtime(os.path.join(history_dir, n)), reverse=True)
    return [n[: -len(".jsonl")] for n in names]


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + f"… [{len(text) - limit} more chars]"


def summarize_event(event: dict) -> dict:
    """Small, display-ready form of one history event (images are counted, not sent)."""
    summary = {
        "timestamp": event.get("timestamp") if isinstance(event.get("timestamp"), str) else None,
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
            if not isinstance(out, dict):
                continue
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
    if summary["type"] == "input_reply" and "value" in details:
        details["value"] = "(hidden)"  # may be a password typed at a getpass() prompt
    if details:
        summary["details"] = details
    return summary


def read_history(history_dir: str, name: str, limit: int = 50) -> list[dict]:
    """Latest `limit` events of one session's history, summarised."""
    if not _is_session_name(name):
        raise ValueError(f"invalid session name: {name!r}")
    path = os.path.join(history_dir, f"{name}.jsonl")
    events = collections.deque(maxlen=limit)
    try:
        with open(path, encoding="utf-8") as f:
            events.extend(_json_objects(f))
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
            # Only session events matter here, so big execution events are skipped unparsed.
            for event in _json_objects(line for line in f if '"session_' in line):
                kind = event.get("event_type")
                if kind == "session_created" and event.get("endpoint"):
                    current = event["endpoint"]
                    found[current] = {"name": name, "ended": None}
                elif kind == "session_terminated" and current:
                    found[current]["ended"] = _epoch(event.get("timestamp")) or time.time()
    except OSError:
        return {}
    return found


def history_endpoints(history_dir: str = DEFAULT_HISTORY_DIR) -> dict:
    """Endpoint -> {"name", "ended"} for every session recorded in history; `ended` is epoch seconds."""
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


def _epoch(timestamp) -> float | None:
    if not isinstance(timestamp, str):
        return None
    try:
        return datetime.datetime.fromisoformat(timestamp).timestamp()
    except ValueError:
        return None


# sys.exit(), sys.exit(None) and sys.exit(0) end a run successfully, as the colab CLI treats them.
_CLEAN_EXITS = frozenset({"", "None", "0"})


def _error_text(outputs) -> str | None:
    for out in outputs if isinstance(outputs, list) else []:
        if isinstance(out, dict) and out.get("output_type") == "error":
            ename = strip_ansi(str(out.get("ename", "Error")))
            evalue = strip_ansi(str(out.get("evalue", "")))
            if ename == "SystemExit" and evalue in _CLEAN_EXITS:
                continue
            return f"{ename}: {evalue}"
    return None


def _timelines_in_file(path: str, name: str) -> dict:
    """Per-machine timelines from one history file. A name can be reused, so key by endpoint."""
    found: dict = {}
    current = None
    try:
        with open(path, encoding="utf-8") as f:
            for event in _json_objects(f):
                t = _epoch(event.get("timestamp"))
                kind = event.get("event_type")
                if t is None:
                    continue
                if kind == "session_created" and event.get("endpoint"):
                    current = {
                        "name": name,
                        "accelerator": event.get("accelerator"),
                        "created": t,
                        "ended": None,
                        "last_activity": t,
                        "executions": [],
                        "last_error": None,
                    }
                    found[event["endpoint"]] = current
                elif current is None:
                    continue
                elif kind == "execution":
                    error = _error_text(event.get("outputs"))
                    current["executions"].append((t, error is not None))
                    current["last_activity"] = max(current["last_activity"], t)
                    if error:
                        current["last_error"] = error
                elif kind == "session_terminated":
                    current["ended"] = t
                    current["last_activity"] = max(current["last_activity"], t)
    except OSError:
        return {}
    return found


# (path) -> (mtime, size, timelines); history files only grow, so unchanged files are not re-read.
_timeline_cache: dict[str, tuple[float, int, dict]] = {}


def session_timelines(history_dir: str = DEFAULT_HISTORY_DIR) -> dict:
    """Endpoint -> timeline (name, accelerator, created, ended, last_activity, executions, last_error).

    Times are epoch seconds. `executions` lists `(time, failed)` for each run of code.
    """
    result: dict = {}
    for name in history_names(history_dir):
        path = os.path.join(history_dir, f"{name}.jsonl")
        try:
            st = os.stat(path)
        except OSError:
            continue
        cached = _timeline_cache.get(path)
        if cached and cached[0] == st.st_mtime and cached[1] == st.st_size:
            found = cached[2]
        else:
            found = _timelines_in_file(path, name)
            _timeline_cache[path] = (st.st_mtime, st.st_size, found)
        result.update(found)
    return result


# (path) -> (mtime, size, lines)
_tail_cache: dict[str, tuple[float, int, list[str]]] = {}


def log_tails(logs: Iterable[dict], lines: int = 200) -> list[dict]:
    """The last lines of each existing log from `discover_logs`, reusing reads of unchanged files."""
    tails = []
    for log in logs:
        if not log.get("exists"):
            continue
        key = (log["mtime"], log["size"])
        cached = _tail_cache.get(log["path"])
        if cached and cached[:2] == key:
            text = cached[2]
        else:
            text = tail_lines(log["path"], max_lines=lines)
            _tail_cache[log["path"]] = (*key, text)
        tails.append(
            {"name": log["name"], "path": log["path"], "mtime": log["mtime"], "lines": text[-lines:]}
        )
    return tails
