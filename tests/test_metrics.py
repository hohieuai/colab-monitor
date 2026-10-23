"""Metrics derived from sessions, history, usage samples, and logs. All pure: time is passed in."""

import pytest

from colab_monitor import metrics
from colab_monitor.metrics import Thresholds

H = 3600.0
NOW = 1_800_000_000.0  # a fixed "now" for every test


def sample(hours_ago, balance, rate):
    return {"t": NOW - hours_ago * H, "balance": balance, "rate": rate}


# ---------- Spend ----------


class TestSpend:
    def test_sums_balance_drops(self):
        samples = [sample(3, 100, 2), sample(2, 98, 2), sample(1, 96, 2), sample(0, 94, 2)]
        assert metrics.spend(samples, since=NOW - 3 * H) == pytest.approx(6)

    def test_ignores_top_ups(self):
        samples = [sample(3, 100, 2), sample(2, 98, 2), sample(1, 198, 2), sample(0, 196, 2)]
        assert metrics.spend(samples, since=NOW - 3 * H) == pytest.approx(4)

    def test_counts_the_drop_across_a_gap_from_a_recent_baseline(self):
        # the dashboard was off between the last sample before `since` and the first after it
        samples = [sample(4.5, 100, 2), sample(1, 93, 2), sample(0, 91, 2)]
        assert metrics.spend(samples, since=NOW - 4 * H) == pytest.approx(9)

    def test_ignores_a_baseline_older_than_an_hour_before_the_window(self):
        samples = [sample(30, 500, 2), sample(1, 93, 2), sample(0, 91, 2)]
        assert metrics.spend(samples, since=NOW - 4 * H) == pytest.approx(2)

    def test_unknown_without_two_samples(self):
        assert metrics.spend([], since=NOW - H) is None
        assert metrics.spend([sample(0.5, 10, 1)], since=NOW - H) is None


# ---------- Runway ----------


class TestRunway:
    def test_hours_and_empty_time(self):
        r = metrics.runway({"balance": 120.0, "rate_per_hour": 10.0}, NOW)
        assert r["hours"] == pytest.approx(12)
        assert r["empty_at"] == pytest.approx(NOW + 12 * H)

    @pytest.mark.parametrize("usage", [None, {"balance": 50.0, "rate_per_hour": 0.0}])
    def test_unknown_when_nothing_bills(self, usage):
        assert metrics.runway(usage, NOW) == {"hours": None, "empty_at": None}


# ---------- Per-machine rates ----------


def live(endpoint, status="busy", name=None, accelerator="T4"):
    return {"endpoint": endpoint, "status": status, "name": name or endpoint, "accelerator": accelerator}


def timeline(
    created_hours_ago,
    *,
    name="x",
    accelerator="T4",
    ended_hours_ago=None,
    activity_hours_ago=None,
    executions=(),
):
    return {
        "name": name,
        "accelerator": accelerator,
        "created": NOW - created_hours_ago * H,
        "ended": None if ended_hours_ago is None else NOW - ended_hours_ago * H,
        "last_activity": NOW
        - (activity_hours_ago if activity_hours_ago is not None else created_hours_ago) * H,
        "executions": [(NOW - h * H, failed) for h, failed in executions],
    }


class TestRateEstimates:
    def test_rate_jump_at_creation_is_the_machines_rate(self):
        samples = [sample(3.02, 50, 0.08), sample(2.98, 50, 11.85)]
        timelines = {"a100": timeline(3, accelerator="A100")}
        rates = metrics.estimate_rates(
            [live("a100", accelerator="A100"), live("cpu")], timelines, samples, current_rate=13.6
        )
        assert rates["a100"] == (pytest.approx(11.77), True)

    def test_the_last_unknown_machine_gets_the_remaining_rate(self):
        samples = [sample(3.02, 50, 0.08), sample(2.98, 50, 11.85)]
        timelines = {"a100": timeline(3, accelerator="A100")}
        rates = metrics.estimate_rates([live("a100"), live("cpu")], timelines, samples, current_rate=11.85)
        assert rates["cpu"] == (pytest.approx(0.08), True)

    def test_a_single_machine_gets_the_whole_rate_exactly(self):
        rates = metrics.estimate_rates([live("t4")], {}, [], current_rate=1.76)
        assert rates["t4"] == (pytest.approx(1.76), False)

    def test_two_machines_started_between_the_same_samples_are_unknown(self):
        samples = [sample(2.1, 50, 0), sample(1.9, 50, 3.5)]
        timelines = {"a": timeline(2), "b": timeline(2)}
        rates = metrics.estimate_rates([live("a"), live("b"), live("c")], timelines, samples, current_rate=5)
        assert rates["a"] == (None, True) and rates["b"] == (None, True)

    def test_no_estimate_across_a_long_gap(self):
        samples = [sample(9, 50, 0), sample(1, 50, 11.8)]  # dashboard was off for 8 hours
        timelines = {"a": timeline(5)}
        rates = metrics.estimate_rates([live("a"), live("b")], timelines, samples, current_rate=13)
        assert rates["a"] == (None, True)


# ---------- Machine metrics ----------


class TestMachineMetrics:
    def test_uptime_idle_and_costs(self):
        timelines = {"t4": timeline(3, activity_hours_ago=0.5)}
        m = metrics.machine_metrics(live("t4", status="idle"), timelines, rate=(2.0, True), now=NOW)
        assert m["uptime_s"] == pytest.approx(3 * H)
        assert m["idle_s"] == pytest.approx(0.5 * H)
        assert m["rate"] == pytest.approx(2.0) and m["rate_estimated"] is True
        assert m["cost"] == pytest.approx(6.0)
        assert m["idle_cost"] == pytest.approx(1.0)

    def test_busy_machines_are_not_idle(self):
        m = metrics.machine_metrics(
            live("t4", status="busy"), {"t4": timeline(1)}, rate=(None, True), now=NOW
        )
        assert m["idle_s"] == 0 and m["idle_cost"] is None and m["cost"] is None

    def test_unknown_machine_has_no_uptime(self):
        m = metrics.machine_metrics(live("anon", status="orphan"), {}, rate=(None, True), now=NOW)
        assert m["uptime_s"] is None and m["idle_s"] is None


# ---------- History aggregates ----------


class TestHistoryAggregates:
    def test_machine_hours_in_the_last_7_days_by_accelerator(self):
        timelines = {
            "a": timeline(2, accelerator="A100"),  # still running: 2 h
            "b": timeline(10, accelerator="T4", ended_hours_ago=7),  # 3 h
            "c": timeline(24 * 9, accelerator="T4", ended_hours_ago=24 * 6),  # 1 day inside the window
            "d": timeline(24 * 20, accelerator="NONE", ended_hours_ago=24 * 19),  # outside
        }
        hours = metrics.machine_hours(timelines, NOW, days=7)
        assert hours == {"A100": pytest.approx(2), "T4": pytest.approx(27)}

    def test_cpu_time_is_reported_as_cpu(self):
        hours = metrics.machine_hours({"a": timeline(1, accelerator="NONE")}, NOW, days=7)
        assert hours == {"CPU": pytest.approx(1)}

    def test_run_counts(self):
        timelines = {
            "a": timeline(30, executions=[(0.5, False), (2, True), (30, False)]),
            "b": timeline(200, executions=[(100, True), (199, False)]),
        }
        counts = metrics.run_counts(timelines, NOW)
        assert counts == {"24h": {"ok": 1, "failed": 1}, "7d": {"ok": 2, "failed": 2}}


# ---------- Logs ----------


class TestJobLogs:
    def test_tqdm_progress_eta_and_speed(self):
        lines = ["epoch 2/5:  45%|####5     | 27/60 [00:24<00:30,  1.09it/s, loss=0.4973]"]
        job = metrics.parse_log(lines)
        assert job["progress"] == pytest.approx(27 / 60)
        assert job["eta_s"] == 30
        assert job["speed"] == "1.09 it/s"
        assert job["metrics"] == {"loss": 0.4973}

    def test_step_progress_with_speed_gives_an_eta(self):
        lines = ["epoch 2/3 | step 1200/1800 | loss 0.6290 | lr 2.0e-4 | 3.0 it/s"]
        job = metrics.parse_log(lines)
        assert job["progress"] == pytest.approx(1200 / 1800)
        assert job["eta_s"] == pytest.approx(200)
        assert job["metrics"] == {"loss": 0.629, "lr": 2.0e-4}

    def test_latest_values_win_and_progress_words_are_not_metrics(self):
        lines = [
            "step 10/100 loss=1.5 acc=0.20",
            "eval | val_loss: 1.1 | perplexity 3.0",
            "step 20/100 loss=1.2",
        ]
        job = metrics.parse_log(lines)
        assert job["metrics"] == {"acc": 0.2, "val_loss": 1.1, "perplexity": 3.0, "loss": 1.2}
        assert "step" not in job["metrics"]

    def test_numbers_with_thousands_separators_are_not_misread(self):
        assert metrics.parse_log(["shard 03/40  rows=44,402  total=103,053"])["metrics"] == {}

    def test_tracebacks_and_table_columns_are_not_metrics(self):
        # Seen in real logs: an IPython traceback header and a pandas summary.
        lines = [
            "ValueError    Traceback (most recent call last) /tmp/266127174.py in <cell line: 0>()",
            "rows: 1000 | mean y: -10.873",
            "seed=42 loss=0.5",
            "train:   8%|#    | 10/120 [00:20<03:40, 0.50it/s]",
        ]
        assert metrics.parse_log(lines)["metrics"] == {"loss": 0.5}

    def test_last_error(self):
        lines = ["step 1/2", "ValueError: schema mismatch in shard 40", "[colab] Session terminated."]
        assert metrics.parse_log(lines)["last_error"] == "ValueError: schema mismatch in shard 40"

    def test_plain_output_has_no_progress(self):
        job = metrics.parse_log(["hello", "world"])
        assert job["progress"] is None and job["eta_s"] is None and job["last_error"] is None

    @pytest.mark.parametrize(
        ("log", "expected"),
        [
            ("train.log", "train"),
            ("train-step2.log", "train"),
            ("llama3-finetune.err", "llama3-finetune"),
            ("other.log", None),
        ],
    )
    def test_matches_a_log_to_its_session_by_name(self, log, expected):
        assert metrics.match_session(log, ["train", "llama3-finetune", "llama3"]) == expected


# ---------- Insights and attention ----------


def state_for_insights():
    sessions = [
        live("a100", status="busy", name="finetune", accelerator="A100"),
        live("t4", status="idle", name="eval", accelerator="T4"),
        live("anon", status="orphan", name=None, accelerator="NONE"),
        {"endpoint": "gone", "status": "gone", "name": "old", "accelerator": "T4"},
    ]
    timelines = {
        "a100": timeline(3, name="finetune", accelerator="A100", executions=[(0.2, True)]),
        "t4": timeline(6, name="eval", accelerator="T4", activity_hours_ago=1),
    }
    samples = [
        sample(6.02, 300, 0.0),
        sample(5.98, 300, 1.76),
        sample(3.02, 295, 1.76),
        sample(2.98, 295, 13.53),
        sample(0, 255, 13.53),
    ]
    logs = [
        {
            "name": "finetune.log",
            "path": "/runs/finetune.log",
            "mtime": NOW - 20 * 60,
            "lines": ["step 900/1800 | loss 0.65 | 3.0 it/s"],
        },
        {"name": "eval.log", "path": "/runs/eval.log", "mtime": NOW - 5 * H, "lines": ["accuracy 0.871"]},
    ]
    return sessions, timelines, samples, logs


class TestInsights:
    def test_full_snapshot(self):
        sessions, timelines, samples, logs = state_for_insights()
        usage = {"balance": 255.0, "rate_per_hour": 13.53}
        ins = metrics.compute_insights(
            sessions, timelines, samples, logs, usage, now=NOW, today_start=NOW - 8 * H
        )
        assert ins["schema"] == 1
        assert ins["spend"]["today"] == pytest.approx(45)
        assert ins["runway"]["hours"] == pytest.approx(255 / 13.53)
        assert ins["machines"]["a100"]["rate"] == pytest.approx(11.77)
        assert ins["machines"]["t4"]["rate"] == pytest.approx(1.76)
        assert ins["machines"]["t4"]["idle_s"] == pytest.approx(H)
        jobs = {j["name"]: j for j in ins["jobs"]}
        assert jobs["finetune.log"]["session"] == "finetune" and jobs["finetune.log"]["stalled"] is True
        assert jobs["eval.log"]["stalled"] is False  # its session is idle, so a quiet log is expected

    def test_attention_items_and_order(self):
        sessions, timelines, samples, logs = state_for_insights()
        usage = {"balance": 100.0, "rate_per_hour": 13.53}  # about 7.4 hours left
        ins = metrics.compute_insights(
            sessions, timelines, samples, logs, usage, now=NOW, today_start=NOW - 8 * H
        )
        kinds = [(a["severity"], a["kind"]) for a in ins["attention"]]
        assert kinds == [
            ("critical", "orphan"),
            ("critical", "runway"),
            ("warning", "idle"),
            ("warning", "stalled"),
            ("warning", "failed"),
        ]
        messages = " ".join(a["message"] for a in ins["attention"])
        assert "—" not in messages and "eval" in messages and "finetune.log" in messages

    def test_thresholds_are_respected(self):
        sessions, timelines, samples, logs = state_for_insights()
        usage = {"balance": 100.0, "rate_per_hour": 13.53}
        relaxed = Thresholds(idle_minutes=120, stall_minutes=60, runway_hours=2)
        ins = metrics.compute_insights(
            sessions, timelines, samples, logs, usage, now=NOW, today_start=NOW - 8 * H, thresholds=relaxed
        )
        assert [a["kind"] for a in ins["attention"]] == ["orphan", "failed"]

    def test_quiet_when_nothing_runs(self):
        ins = metrics.compute_insights(
            [], {}, [], [], {"balance": 99.0, "rate_per_hour": 0.0}, now=NOW, today_start=NOW - H
        )
        assert ins["attention"] == [] and ins["jobs"] == [] and ins["runway"]["hours"] is None


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (0, "0 s"),
        (45, "45 s"),
        (60, "1 min"),
        (42 * 60, "42 min"),
        (2 * H, "2 h"),
        (2 * H + 600, "2 h 10 min"),
        (3 * 86400, "3 days"),
    ],
)
def test_human_duration(seconds, text):
    assert metrics.human_duration(seconds) == text


def test_failed_run_message_without_error_text_is_a_sentence():
    tl = timeline(1, name="job", executions=[(0.1, True)])
    ins = metrics.compute_insights([], {"e": tl}, [], [], None, now=NOW, today_start=NOW - H)
    assert ins["attention"][0]["message"] == "A run in job failed 6 min ago."
