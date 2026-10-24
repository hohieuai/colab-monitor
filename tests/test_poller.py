import pytest

from colab_monitor.poller import ApiPoller


class MockClock:
    """A clock that moves only when a test sets ``now``."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_success_stores_snapshot():
    poller = ApiPoller(
        fetch_usage=lambda: {"balance": 199.7},
        fetch_assignments=lambda: [{"endpoint": "e1"}],
        interval=60,
        clock=MockClock(),
    )
    poller.poll_once()
    snap = poller.snapshot()
    assert snap["usage"] == {"balance": 199.7}
    assert snap["assignments"] == [{"endpoint": "e1"}]
    assert snap["error"] is None
    assert snap["interval"] == 60


def test_failure_keeps_last_good_data_and_backs_off():
    calls = {"n": 0}

    def flaky_usage():
        calls["n"] += 1
        if calls["n"] > 1:
            raise RuntimeError("HTTP 429")
        return {"balance": 1.0}

    poller = ApiPoller(
        fetch_usage=flaky_usage,
        fetch_assignments=list,
        interval=60,
        max_interval=200,
        clock=MockClock(),
    )
    poller.poll_once()
    poller.poll_once()
    snap = poller.snapshot()
    assert snap["usage"] == {"balance": 1.0}
    assert "HTTP 429" in snap["error"]
    assert snap["interval"] == 120

    poller.poll_once()
    assert poller.snapshot()["interval"] == 200  # capped


def test_recovery_resets_interval():
    state = {"fail": True}

    def usage():
        if state["fail"]:
            raise RuntimeError("boom")
        return {}

    poller = ApiPoller(usage, list, interval=60, clock=MockClock())
    poller.poll_once()
    assert poller.snapshot()["interval"] == 120
    state["fail"] = False
    poller.poll_once()
    snap = poller.snapshot()
    assert snap["interval"] == 60
    assert snap["error"] is None


def test_next_poll_countdown():
    clock = MockClock()
    poller = ApiPoller(dict, list, interval=60, clock=clock)
    poller.poll_once()
    clock.now += 15
    assert poller.snapshot()["next_poll_in"] == pytest.approx(45)


def test_on_sample_called_only_on_success():
    seen = []
    state = {"fail": False}

    def usage():
        if state["fail"]:
            raise RuntimeError("boom")
        return {"balance": 5.0}

    poller = ApiPoller(usage, list, interval=60, clock=MockClock(), on_sample=seen.append)
    poller.poll_once()
    state["fail"] = True
    poller.poll_once()
    assert seen == [{"balance": 5.0}]


def test_on_sample_errors_do_not_break_polling():
    def explode(_):
        raise OSError("disk full")

    poller = ApiPoller(dict, list, interval=60, clock=MockClock(), on_sample=explode)
    poller.poll_once()
    assert poller.snapshot()["error"] is None
    assert poller.snapshot()["usage"] == {}


def test_rejects_intervals_below_floor():
    with pytest.raises(ValueError):
        ApiPoller(dict, list, interval=5)
