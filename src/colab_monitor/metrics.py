"""Metrics that Colab and the colab CLI don't report, derived from data Colab Monitor already has.

Every function here is pure: inputs in, numbers out, with the current time passed in. That keeps
each metric exactly testable. The inputs are:

- sessions: the merged session list from `sources.merge_sessions`, each with a `status`.
- timelines: `sources.session_timelines`, one entry per endpoint from the CLI's history.
- samples: usage samples `{"t", "balance", "rate"}` from the usage log, oldest first.
- logs: `{"name", "path", "mtime", "lines"}` for each job log.

Colab does not report what each machine costs, so per-machine rates are estimates. They are
returned with `rate_estimated: True`, and every display marks them as approximate.
"""

import datetime
import itertools
import re
from dataclasses import dataclass

SCHEMA = 1
LIVE_STATUSES = frozenset({"busy", "idle", "stopping", "orphan"})

# A sample this close before a period still measures its first drop; an older one is ignored.
MAX_BASELINE_GAP = 3600.0
# A rate change is attributed to a new machine only if the samples around its start are this close.
MAX_ATTRIBUTION_GAP = 15 * 60.0
FAILED_RUN_WINDOW = 3600.0
MAX_METRICS = 8


@dataclass(frozen=True)
class Thresholds:
    """When a machine or job needs attention."""

    idle_minutes: float = 30
    stall_minutes: float = 15
    runway_hours: float = 12


# ---------- Spend and runway ----------


def spend(samples: list[dict], since: float) -> float | None:
    """Compute units spent since `since`: the sum of balance drops. Top-ups don't count.

    Returns None when fewer than two samples cover the period.
    """
    ordered = sorted(samples, key=lambda s: s["t"])
    window = [s for s in ordered if s["t"] >= since]
    before = [s for s in ordered if s["t"] < since]
    if before and since - before[-1]["t"] <= MAX_BASELINE_GAP:
        window = [before[-1], *window]
    if len(window) < 2:
        return None
    return sum(max(0.0, a["balance"] - b["balance"]) for a, b in itertools.pairwise(window))


def runway(usage: dict | None, now: float) -> dict:
    """Hours until the balance reaches zero at the current rate, and when that is (epoch seconds)."""
    rate = (usage or {}).get("rate_per_hour") or 0.0
    if rate <= 0:
        return {"hours": None, "empty_at": None}
    hours = usage["balance"] / rate
    return {"hours": hours, "empty_at": now + hours * 3600}


# ---------- Per-machine metrics ----------


def _around(samples: list[dict], t: float) -> tuple[dict | None, dict | None]:
    before = after = None
    for s in samples:
        if s["t"] <= t:
            before = s
        elif after is None:
            after = s
    return before, after


def estimate_rates(
    sessions: list[dict], timelines: dict, samples: list[dict], current_rate: float | None
) -> dict[str, tuple[float | None, bool]]:
    """Each live machine's compute units per hour, as `(rate or None, estimated)`.

    A single live machine uses the whole rate. Otherwise a machine's rate is the jump in the total
    rate when it started, and the last unknown machine gets what remains of the current rate.
    """
    live = [s for s in sessions if s.get("status") in LIVE_STATUSES]
    if len(live) == 1 and current_rate is not None:
        return {live[0]["endpoint"]: (current_rate, False)}

    ordered = sorted(samples, key=lambda s: s["t"])
    groups: dict[tuple[float, float], list[tuple[str, float]]] = {}
    for s in live:
        tl = timelines.get(s["endpoint"])
        if not tl:
            continue
        before, after = _around(ordered, tl["created"])
        if before is None or after is None or after["t"] - before["t"] > MAX_ATTRIBUTION_GAP:
            continue
        groups.setdefault((before["t"], after["t"]), []).append(
            (s["endpoint"], after["rate"] - before["rate"])
        )

    rates: dict[str, tuple[float | None, bool]] = {s["endpoint"]: (None, True) for s in live}
    for members in groups.values():
        if len(members) == 1 and members[0][1] > 0:  # several starts in one step can't be split
            endpoint, delta = members[0]
            rates[endpoint] = (delta, True)

    unknown = [e for e, (r, _) in rates.items() if r is None]
    if current_rate is not None and len(unknown) == 1:
        rest = current_rate - sum(r for r, _ in rates.values() if r is not None)
        if rest > 0:
            rates[unknown[0]] = (rest, True)
    return rates


def machine_metrics(session: dict, timelines: dict, rate: tuple[float | None, bool], now: float) -> dict:
    """Uptime, idle time, rate, and the cost of both for one live machine."""
    tl = timelines.get(session["endpoint"])
    uptime = now - tl["created"] if tl else None
    status = session.get("status")
    if status == "busy":
        idle = 0.0
    elif status == "idle" and tl:
        idle = max(0.0, now - tl["last_activity"])
    else:
        idle = None
    r, estimated = rate
    return {
        "uptime_s": uptime,
        "idle_s": idle,
        "rate": r,
        "rate_estimated": estimated,
        "cost": r * uptime / 3600 if r is not None and uptime is not None else None,
        "idle_cost": r * idle / 3600 if r is not None and idle else None,
    }


# ---------- History aggregates ----------


def _accelerator_label(accelerator: str | None) -> str:
    return "CPU" if accelerator in (None, "", "NONE") else accelerator


def machine_hours(
    timelines: dict, now: float, days: int = 7, live_endpoints: set | None = None
) -> dict[str, float]:
    """Machine hours per accelerator over the last `days` days.

    A session with no end in history counts until now if it is still live. Pass `live_endpoints`
    so a session that vanished without an end event stops counting at its last activity.
    """
    start = now - days * 86400
    hours: dict[str, float] = {}
    for endpoint, tl in timelines.items():
        end = tl["ended"]
        if end is None:
            alive = live_endpoints is None or endpoint in live_endpoints
            end = now if alive else tl["last_activity"]
        overlap = min(end, now) - max(tl["created"], start)
        if overlap > 0:
            label = _accelerator_label(tl.get("accelerator"))
            hours[label] = hours.get(label, 0.0) + overlap / 3600
    return hours


def run_counts(timelines: dict, now: float) -> dict:
    """Finished and failed runs (code executions) over the last 24 hours and 7 days."""
    counts = {"24h": {"ok": 0, "failed": 0}, "7d": {"ok": 0, "failed": 0}}
    for tl in timelines.values():
        for t, failed in tl["executions"]:
            key = "failed" if failed else "ok"
            if now - t <= 86400:
                counts["24h"][key] += 1
            if now - t <= 7 * 86400:
                counts["7d"][key] += 1
    return counts


# ---------- Job logs ----------

_NUMBER = r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
# So "44,402", "8%", "8/120", "15.2GB", and "3.2s" are not read as the numbers 44, 8, 8, 15.2, and 3.2.
_NUMBER_END = r"(?![\d.%/A-Za-z]|,\d)"
_CLOCK = r"\d+(?::\d+){0,2}"
_TQDM = re.compile(
    rf"(\d+)/(\d+)\s*\[(?P<elapsed>{_CLOCK})<(?P<remaining>{_CLOCK}|\?)(?=[,\]])"
    r"(?:,\s*(?P<speed>[\d.]+\s*(?:it/s|s/it)|\?it/s))?"
)
_STEP = re.compile(r"\bstep\s*[:=]?\s*(\d+)\s*/\s*(\d+)", re.IGNORECASE)
_EPOCH = re.compile(r"\bepoch\s*[:=]?\s*(\d+)\s*/\s*(\d+)", re.IGNORECASE)
_SPEED = re.compile(r"(\d+(?:\.\d+)?)\s*(it/s|s/it)")
# `name=1`, `name: 1`, and quoted keys as in Hugging Face's `{'loss': 0.41}` or JSON. A name right
# after "/" or "." is part of a path or address, such as `localhost:8888`.
_KEY_VALUE = re.compile(
    rf"(?<![\w./])['\"]?([A-Za-z][A-Za-z0-9_.]*?)['\"]?\s*[=:]\s*({_NUMBER}){_NUMBER_END}"
)
_KNOWN_METRICS = (
    "loss|train_loss|val_loss|eval_loss|test_loss|acc|accuracy|val_acc|val_accuracy|"
    "f1|auc|bleu|perplexity|ppl|reward|lr|learning_rate"
)
_KNOWN_SPACED = re.compile(rf"(?<![\w.])({_KNOWN_METRICS})\s+({_NUMBER}){_NUMBER_END}", re.IGNORECASE)
_NOT_METRICS = frozenset(
    {
        "step",
        "epoch",
        "eta",
        "elapsed",
        "it",
        "shard",
        "rows",
        "total",
        "batch",
        "iter",
        "line",
        "pid",
        "port",
        "seed",
    }
)
# A line that reports a failure: a Python exception or traceback, running out of memory, or a line
# that starts with "error", "fatal", or "failed". Metric names such as "val_error" are not failures.
_ERROR = re.compile(
    r"Traceback \(most recent call last\)|\b[A-Z]\w*(?:Error|Exception)\b"
    r"|(?i:\bout of memory\b|^\s*(?:error|fatal|failed)\b)"
)
# Only this much of a line is parsed, which keeps the regular expressions fast on huge lines.
MAX_LINE_CHARS = 2_000
_SUFFIXES = (".log", ".out", ".err")


def _clock_seconds(text: str) -> int:
    seconds = 0
    for part in text.split(":"):
        seconds = seconds * 60 + int(part)
    return seconds


def _progress(line: str) -> tuple[float, float | None, str | None] | None:
    m = _TQDM.search(line)
    if m and int(m.group(2)) > 0:
        done, total = int(m.group(1)), int(m.group(2))
        speed = m.group("speed")
        speed = None if not speed or speed.startswith("?") else re.sub(r"\s*(it/s|s/it)", r" \1", speed)
        eta = None if m.group("remaining") == "?" else _clock_seconds(m.group("remaining"))
        return done / total, eta, speed
    for pattern in (_STEP, _EPOCH):
        m = pattern.search(line)
        if m and int(m.group(2)) > 0:
            done, total = int(m.group(1)), int(m.group(2))
            eta = speed = None
            sm = _SPEED.search(line)
            if sm:
                value, unit = float(sm.group(1)), sm.group(2)
                speed = f"{sm.group(1)} {unit}"
                if value > 0:
                    eta = (total - done) / value if unit == "it/s" else (total - done) * value
            return done / total, eta, speed
    return None


def parse_log(lines: list[str]) -> dict:
    """Progress, ETA, speed, latest training numbers, and the last error from a log's last lines."""
    lines = [line[:MAX_LINE_CHARS] for line in lines]
    progress = eta = speed = None
    for line in reversed(lines):
        found = _progress(line)
        if found:
            progress, eta, speed = found
            break

    values: dict[str, float] = {}
    for line in lines[-30:]:
        if _ERROR.search(line):  # "<cell line: 0>" in a traceback is not a metric
            continue
        for pattern in (_KEY_VALUE, _KNOWN_SPACED):
            for key, number in pattern.findall(line):
                # One-letter names, as in "mean y: -10.8", name a column, not a metric.
                if len(key) < 2 or key.lower() in _NOT_METRICS:
                    continue
                values.pop(key, None)  # re-insert so the latest values come last
                values[key] = float(number)
    metrics = dict(list(values.items())[-MAX_METRICS:])

    last_error = next((line.strip() for line in reversed(lines) if _ERROR.search(line)), None)
    return {"progress": progress, "eta_s": eta, "speed": speed, "metrics": metrics, "last_error": last_error}


def match_session(log_name: str, session_names: list[str]) -> str | None:
    """The session a log belongs to: `NAME.log`, or `NAME-anything.log`. The longest name wins."""
    stem = log_name
    for suffix in _SUFFIXES:
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    matches = [n for n in session_names if n and (stem == n or stem.startswith((f"{n}-", f"{n}_", f"{n}.")))]
    return max(matches, key=len) if matches else None


# ---------- Formatting for messages ----------


def human_duration(seconds: float) -> str:
    """'45 s', '42 min', '2 h 10 min', '3 days'."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min"
    if seconds < 2 * 86400:
        h, m = divmod(seconds // 60, 60)
        return f"{h} h {m} min" if m else f"{h} h"
    return f"{seconds // 86400} days"


# ---------- Everything together ----------


def compute_insights(
    sessions: list[dict],
    timelines: dict,
    samples: list[dict],
    logs: list[dict],
    usage: dict | None,
    now: float,
    today_start: float | None = None,
    thresholds: Thresholds = Thresholds(),  # noqa: B008 - frozen dataclass, safe as a default
) -> dict:
    """All insights for one moment. The `schema` number changes only when fields change meaning."""
    if today_start is None:
        local = datetime.datetime.fromtimestamp(now)
        today_start = local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    ordered = sorted(samples, key=lambda s: s["t"])

    live = [s for s in sessions if s.get("status") in LIVE_STATUSES]
    current_rate = (usage or {}).get("rate_per_hour")
    rates = estimate_rates(live, timelines, ordered, current_rate)
    machines = {s["endpoint"]: machine_metrics(s, timelines, rates[s["endpoint"]], now) for s in live}

    names = [s["name"] for s in sessions if s.get("name")]
    status_by_name = {s["name"]: s.get("status") for s in sessions if s.get("name")}
    sessions_of_logs = {log["path"]: match_session(log["name"], names) for log in logs}
    # A session name can be reused, so only its newest log belongs to the run in progress.
    newest: dict[str, float] = {}
    for log in logs:
        session = sessions_of_logs[log["path"]]
        if session and log.get("mtime"):
            newest[session] = max(newest.get(session, 0.0), log["mtime"])
    jobs = []
    for log in logs:
        parsed = parse_log(log.get("lines") or [])
        session = sessions_of_logs[log["path"]]
        silent = now - log["mtime"] if log.get("mtime") else None
        stalled = bool(
            session
            and status_by_name.get(session) == "busy"
            and log.get("mtime") == newest.get(session)
            and silent is not None
            and silent > thresholds.stall_minutes * 60
        )
        jobs.append(
            {
                "name": log["name"],
                "path": log["path"],
                "session": session,
                "silent_s": silent,
                "stalled": stalled,
                **parsed,
            }
        )

    run = runway(usage, now)
    idle_cost = sum(
        m["idle_cost"] for s in live if s["status"] == "idle" and (m := machines[s["endpoint"]])["idle_cost"]
    )
    return {
        "schema": SCHEMA,
        "spend": {
            "today": spend(ordered, today_start),
            "7d": spend(ordered, now - 7 * 86400),
            "30d": spend(ordered, now - 30 * 86400),
            "measured_since": ordered[0]["t"] if ordered else None,
        },
        "runway": run,
        "machines": machines,
        "idle_cost": idle_cost,
        "machine_hours_7d": machine_hours(
            timelines, now, days=7, live_endpoints={s["endpoint"] for s in live}
        ),
        "runs": run_counts(timelines, now),
        "jobs": jobs,
        "attention": _attention(sessions, timelines, machines, jobs, run, now, thresholds),
        "thresholds": {
            "idle_minutes": thresholds.idle_minutes,
            "stall_minutes": thresholds.stall_minutes,
            "runway_hours": thresholds.runway_hours,
        },
    }


def _attention(sessions, timelines, machines, jobs, run, now, thresholds) -> list[dict]:
    """What needs a look, most serious first."""
    items = []

    def add(severity, kind, subject, message):
        items.append({"severity": severity, "kind": kind, "subject": subject, "message": message})

    for s in sessions:
        if s.get("status") == "orphan":
            label = s.get("name") or s["endpoint"]
            add(
                "critical",
                "orphan",
                label,
                f"{label} is an orphan: Colab bills it, and the colab CLI has no record of it.",
            )
    if run["hours"] is not None and run["hours"] < thresholds.runway_hours:
        add(
            "critical",
            "runway",
            "compute units",
            f"Compute units run out in about {human_duration(run['hours'] * 3600)}.",
        )
    for s in sessions:
        m = machines.get(s["endpoint"])
        if (
            s.get("status") == "idle"
            and m
            and m["idle_s"] is not None
            and m["idle_s"] >= thresholds.idle_minutes * 60
        ):
            label = s.get("name") or s["endpoint"]
            cost = f" (about {m['idle_cost']:.2f} units)" if m["idle_cost"] else ""
            add("warning", "idle", label, f"{label} has been idle for {human_duration(m['idle_s'])}{cost}.")
    for job in jobs:
        if job["stalled"]:
            add(
                "warning",
                "stalled",
                job["name"],
                f"{job['name']} has printed nothing for {human_duration(job['silent_s'])} "
                f"while {job['session']} runs.",
            )
    for tl in timelines.values():
        recent = [t for t, failed in tl["executions"] if failed and now - t <= FAILED_RUN_WINDOW]
        if recent:
            error = f": {tl['last_error']}" if tl.get("last_error") else "."
            add(
                "warning",
                "failed",
                tl["name"],
                f"A run in {tl['name']} failed {human_duration(now - max(recent))} ago{error}",
            )

    order = {"critical": 0, "warning": 1}
    return sorted(items, key=lambda a: order[a["severity"]])
