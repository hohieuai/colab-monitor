"""The only part of the dashboard that calls Colab.

One poller fetches usage and assignments on a fixed interval and caches the
result, so the number of Colab requests doesn't depend on how many browser
tabs are open. Failures (including HTTP 429) double the interval up to a cap
and keep the last good data on screen.
"""

import datetime
import logging
import threading
import time
from collections.abc import Callable

MIN_INTERVAL = 30.0


class ApiPoller:
    def __init__(
        self,
        fetch_usage: Callable[[], dict],
        fetch_assignments: Callable[[], list[dict]],
        interval: float = 60.0,
        max_interval: float = 600.0,
        clock: Callable[[], float] = time.monotonic,
        on_sample: Callable[[dict], None] | None = None,
    ):
        if interval < MIN_INTERVAL:
            raise ValueError(f"interval must be at least {MIN_INTERVAL:.0f}s")
        self._fetch_usage = fetch_usage
        self._fetch_assignments = fetch_assignments
        self._base_interval = interval
        self._max_interval = max(max_interval, interval)
        self._clock = clock
        self._on_sample = on_sample
        self._lock = threading.Lock()
        self._interval = interval
        self._usage: dict | None = None
        self._assignments: list[dict] | None = None
        self._error: str | None = None
        self._updated_at: str | None = None
        self._last_poll: float | None = None

    def poll_once(self) -> None:
        try:
            usage = self._fetch_usage()
            assignments = self._fetch_assignments()
        except Exception as e:  # noqa: BLE001 - keep serving the last good data
            with self._lock:
                self._error = f"{type(e).__name__}: {e}"
                self._interval = min(self._interval * 2, self._max_interval)
                self._last_poll = self._clock()
            return

        with self._lock:
            self._usage = usage
            self._assignments = assignments
            self._error = None
            self._interval = self._base_interval
            self._updated_at = datetime.datetime.now(datetime.UTC).isoformat()
            self._last_poll = self._clock()

        if self._on_sample is not None:
            try:
                self._on_sample(usage)
            except Exception:  # recording history must never stop polling
                logging.getLogger(__name__).warning("Could not record usage sample", exc_info=True)

    @property
    def base_interval(self) -> float:
        return self._base_interval

    def snapshot(self) -> dict:
        with self._lock:
            next_in = None
            if self._last_poll is not None:
                next_in = max(0.0, self._last_poll + self._interval - self._clock())
            return {
                "usage": self._usage,
                "assignments": self._assignments,
                "error": self._error,
                "updated_at": self._updated_at,
                "interval": self._interval,
                "next_poll_in": next_in,
            }

    def run(self, stop: threading.Event) -> None:
        """Poll until `stop` is set. Meant for a daemon thread."""
        while not stop.is_set():
            self.poll_once()
            with self._lock:
                wait = self._interval
            stop.wait(wait)
