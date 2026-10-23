"""Compute-unit samples kept on disk so the usage chart survives restarts.

One JSON line per successful Colab check: {"t": epoch seconds, "balance", "rate"}.
At the default 60s interval that's about 100 KB a day; old samples are pruned
at startup.
"""

import json
import math
import os
import threading
import time

DEFAULT_PATH = os.path.expanduser("~/.config/colab-monitor/usage.jsonl")
RETENTION_SECONDS = 30 * 86400


class UsageLog:
    def __init__(self, path: str = DEFAULT_PATH):
        self.path = path
        self._lock = threading.Lock()
        # (mtime_ns, size, samples): the dashboard reads every few seconds, the file changes each minute.
        self._cache: tuple[int, int, list[dict]] | None = None

    def append(self, usage: dict, now: float | None = None) -> None:
        sample = {
            "t": time.time() if now is None else now,
            "balance": usage.get("balance"),
            "rate": usage.get("rate_per_hour"),
        }
        with self._lock:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(sample) + "\n")

    def read(self, since: float | None = None) -> list[dict]:
        try:
            st = os.stat(self.path)
        except OSError:
            return []
        if self._cache is None or self._cache[:2] != (st.st_mtime_ns, st.st_size):
            self._cache = (st.st_mtime_ns, st.st_size, self._read_all())
        samples = self._cache[2]
        return samples if since is None else [p for p in samples if p["t"] >= since]

    def _read_all(self) -> list[dict]:
        points = []
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    try:
                        p = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(p, dict) or not {"t", "balance", "rate"} <= p.keys():
                        continue
                    points.append(p)
        except OSError:
            return []
        return points

    def prune(self, before: float) -> None:
        with self._lock:
            keep = [p for p in self.read() if p["t"] >= before]
            if not os.path.exists(self.path):
                return
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.writelines(json.dumps(p) + "\n" for p in keep)
            os.replace(tmp, self.path)


def downsample(points: list[dict], max_points: int) -> list[dict]:
    """Evenly thin a time-ordered series, always keeping the latest sample."""
    if len(points) <= max_points:
        return points
    step = math.ceil(len(points) / (max_points - 1))
    out = points[::step]
    if out[-1] is not points[-1]:
        out.append(points[-1])
    return out
