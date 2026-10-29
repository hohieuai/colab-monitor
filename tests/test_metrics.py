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


class TestJobState:
    def parsed(self, lines):
        return metrics.parse_log(lines)

    def test_a_log_that_ends_in_an_error_failed(self):
        lines = [
            "step 50/100 loss 0.3",
            "Traceback (most recent call last):",
            '  File "train.py"',
            "ValueError: bad shard",
        ]
        assert metrics.job_state(self.parsed(lines), "busy", False, 10, matched=True) == "failed"

    def test_an_error_the_job_survived_is_not_a_failure(self):
        lines = ["WARNING retry failed once", "step 51/100 loss 0.3", "step 52/100 loss 0.29"]
        assert metrics.job_state(self.parsed(lines), "busy", False, 10, matched=True) == "running"

    def test_an_old_error_far_from_the_end_is_not_a_failure(self):
        lines = ["ValueError: shard 3 skipped", *[f"line {i}" for i in range(10)]]
        assert self.parsed(lines)["ended_with_error"] is False

    def test_a_trailing_message_after_the_error_still_counts(self):
        lines = ["step 1/2", "ValueError: schema mismatch", "[colab] Session terminated."]
        assert self.parsed(lines)["ended_with_error"] is True

    @pytest.mark.parametrize(
        ("status", "stalled", "state"),
        [
            ("busy", False, "running"),
            ("busy", True, "stalled"),
            ("idle", False, "finished"),
            ("gone", False, "finished"),
        ],
    )
    def test_the_machine_decides_for_a_matched_log(self, status, stalled, state):
        assert metrics.job_state(self.parsed(["step 5/10"]), status, stalled, 900, matched=True) == state

    @pytest.mark.parametrize(
        ("lines", "silent", "state"),
        [
            (["step 5/10"], 30, "running"),
            (["step 10/10"], 900, "finished"),
            (["step 5/10"], 900, "quiet"),
            (["hello"], None, "quiet"),
        ],
    )
    def test_an_unmatched_log_is_judged_by_itself(self, lines, silent, state):
        assert metrics.job_state(self.parsed(lines), None, False, silent, matched=False) == state


class TestEndingsSeenInRealLogs:
    """Endings of real kernel-benchmark and sweep logs, which must not read as failures."""

    def test_a_measured_error_is_not_an_error(self):
        lines = [
            "[verify 32] {'batch': 32}: pass (relative L2 error 2.560e-03 (worst row 2.758e-03))",
            "    median 195.6 µs  min 195.6  max 204.8",
            "done: 12/12 passed",
        ]
        parsed = metrics.parse_log(lines)
        assert parsed["ended_with_error"] is False and parsed["last_error"] is None

    def test_a_sweep_that_logs_a_failed_case_and_finishes_did_not_die(self):
        lines = [
            "t64_s16  ERR AcceleratorError: CUDA error: invalid argument",
            "t128_s16  168.9 / 9.3 ok",
            "ALLDONE",
        ]
        parsed = metrics.parse_log(lines)
        assert parsed["ended_with_error"] is False
        assert parsed["last_error"].startswith(
            "t64_s16  ERR AcceleratorError"
        )  # still shown as an earlier error

    @pytest.mark.parametrize(
        "last",
        [
            "[colab] Session 'okc' not found.",
            "S ERR AcceleratorError: CUDA error: invalid argument",
            "torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.00 GiB",
            "KeyboardInterrupt",
            "Killed",
        ],
    )
    def test_a_last_line_that_ends_the_job(self, last):
        parsed = metrics.parse_log(["step 3/10 loss=0.4", last])
        assert parsed["ended_with_error"] is True
        assert parsed["last_error"] == last  # a failed job always says why

    def test_a_server_log_that_went_quiet_did_not_fail(self):
        lines = [
            'INFO:     127.0.0.1:42640 - "POST /v1/chat/completions HTTP/1.1" 200 OK',
            "INFO Engine 000: Running: 0 reqs",
        ]
        assert metrics.parse_log(lines)["ended_with_error"] is False


class TestMetricSeries:
    def test_series_follow_the_log_with_line_and_step(self):
        lines = [
            "start",
            "step 1/3 loss=0.9 acc=0.1",
            "step 2/3 loss=0.5 acc=0.4",
            "eval val_loss: 0.7",
            "step 3/3 loss=0.2 acc=0.8",
        ]
        series = {s["name"]: s for s in metrics.metric_series(lines)}
        assert series["loss"]["points"] == [[2, 1, 0.9], [3, 2, 0.5], [5, 3, 0.2]]
        assert series["acc"]["count"] == 3
        assert "val_loss" not in series  # one reading is not a line

    def test_a_value_that_never_changes_is_not_a_series(self):
        lines = [f"step {i}/5 lr=0.0002 sms: 108 loss={1 / i}" for i in range(1, 6)]
        assert [s["name"] for s in metrics.metric_series(lines)] == ["loss"]

    def test_loss_comes_first_then_the_most_common(self):
        lines = [f"step {i}/9 acc={i / 10} lr=0.1 loss={1 / i}" for i in range(1, 10)] + ["acc=0.95"]
        assert [s["name"] for s in metrics.metric_series(lines)][:2] == ["loss", "acc"]

    def test_long_series_are_thinned_but_keep_the_latest_value(self):
        lines = [f"loss={i}" for i in range(1000)]
        [loss] = metrics.metric_series(lines, max_points=50)
        assert len(loss["points"]) == 50 and loss["count"] == 1000
        assert loss["points"][0][2] == 0 and loss["points"][-1][2] == 999

    def test_error_lines_and_tqdm_steps(self):
        lines = [
            "10/100 [00:10<01:30, 1.0it/s, loss=0.5]",
            "Error at <cell line: 0>",
            "20/100 [00:20<01:20, 1.0it/s, loss=0.4]",
        ]
        [loss] = metrics.metric_series(lines)
        assert loss["points"] == [[1, 10, 0.5], [3, 20, 0.4]]


class TestCommands:
    def test_release_command_names_the_endpoint(self):
        cmd = metrics.release_command("gpu-t4-s-abc123")
        assert (
            cmd.startswith("uvx --from google-colab-cli python -c") and "unassign('gpu-t4-s-abc123')" in cmd
        )

    @pytest.mark.parametrize("bad", ["", "a b", "x';rm -rf ~;'", None])
    def test_no_command_for_an_unsafe_name(self, bad):
        assert metrics.release_command(bad) is None
        assert metrics.stop_command(bad) is None

    def test_stop_command_passes_a_non_default_state_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        assert (
            metrics.stop_command("train", str(tmp_path / ".config/colab-cli/sessions.json"))
            == "colab stop -s train"
        )
        assert metrics.stop_command("train", "~/.config/colab-cli/sessions.json") == "colab stop -s train"
        assert (
            metrics.stop_command("train", "/my state/agent.json")
            == "colab --config '/my state/agent.json' stop -s train"
        )

    def test_with_adc_the_commands_sign_in_the_same_way(self):
        # Without it, the colab CLI signs in with OAuth and waits for a code that never comes.
        release = metrics.release_command("gpu-abc", adc=True)
        assert release == (
            'uvx --from google-colab-cli python -c "from colab_cli.auth import AuthProvider; '
            "from colab_cli.common import state; state.auth_provider = AuthProvider.ADC; "
            "state.client.unassign('gpu-abc')\""
        )
        assert metrics.stop_command("train", adc=True) == "colab --auth adc stop -s train"
        assert (
            metrics.stop_command("train", "/s/agent.json", adc=True)
            == "colab --auth adc --config /s/agent.json stop -s train"
        )

    def test_attention_items_carry_commands_and_what_they_are_about(self):
        sessions, timelines, samples, logs = state_for_insights()
        sessions[1]["config"] = "/state/agent.json"
        ins = metrics.compute_insights(
            sessions,
            timelines,
            samples,
            logs,
            {"balance": 100.0, "rate_per_hour": 13.53},
            now=NOW,
            today_start=NOW - 8 * H,
        )
        items = {a["kind"]: a for a in ins["attention"]}
        assert items["orphan"]["endpoint"] == "anon" and "unassign('anon')" in items["orphan"]["command"]
        assert items["idle"]["command"] == "colab --config /state/agent.json stop -s eval"
        assert (
            items["stalled"]["path"] == "/runs/finetune.log"
            and items["stalled"]["command"] == "tail -n 50 /runs/finetune.log"
        )
        assert items["runway"]["command"] is None and items["failed"]["session"] == "finetune"


class TestFailedJobs:
    def run(self, lines, mtime_ago, executions=()):
        sessions = [live("t4", status="busy", name="train", accelerator="T4")]
        timelines = {"t4": timeline(2, name="train", accelerator="T4", executions=list(executions))}
        logs = [{"name": "train.log", "path": "/runs/train.log", "mtime": NOW - mtime_ago, "lines": lines}]
        return metrics.compute_insights(sessions, timelines, [], logs, None, now=NOW, today_start=NOW - H)

    def test_a_job_that_died_is_failed_not_stalled_and_needs_attention(self):
        ins = self.run(["step 3/10 loss 0.5", "RuntimeError: CUDA out of memory"], mtime_ago=40 * 60)
        [job] = ins["jobs"]
        assert job["state"] == "failed" and job["stalled"] is False and "ended_with_error" not in job
        [item] = ins["attention"]
        assert item["kind"] == "failed" and item["path"] == "/runs/train.log"
        assert item["message"] == "train.log ended with an error 40 min ago: RuntimeError: CUDA out of memory"

    def test_an_older_log_of_a_reused_name_is_not_running(self):
        sessions = [live("t4", status="busy", name="train", accelerator="T4")]
        timelines = {"t4": timeline(2, name="train", accelerator="T4")}
        logs = [
            {
                "name": "train-run1.log",
                "path": "/runs/train-run1.log",
                "mtime": NOW - 5 * H,
                "lines": ["step 10/10"],
            },
            {
                "name": "train-run2.log",
                "path": "/runs/train-run2.log",
                "mtime": NOW - 30,
                "lines": ["step 3/10"],
            },
        ]
        ins = metrics.compute_insights(sessions, timelines, [], logs, None, now=NOW, today_start=NOW - H)
        assert {j["name"]: j["state"] for j in ins["jobs"]} == {
            "train-run1.log": "finished",
            "train-run2.log": "running",
        }

    def test_an_old_failure_is_no_longer_news(self):
        ins = self.run(["RuntimeError: boom"], mtime_ago=3 * H)
        assert ins["jobs"][0]["state"] == "failed" and ins["attention"] == []

    def test_one_item_when_the_history_already_reported_the_run(self):
        ins = self.run(["RuntimeError: boom"], mtime_ago=60, executions=[(0.01, True)])
        assert [a["message"].startswith("A run in train failed") for a in ins["attention"]] == [True]


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


class TestReviewFindings:
    """Edge cases from the review of the insights feature."""

    def test_metric_names_that_contain_error_are_metrics(self):
        job = metrics.parse_log(["Epoch 3/10 - loss: 0.07 - mean_absolute_error: 0.20 - val_error=0.08"])
        assert job["metrics"]["mean_absolute_error"] == 0.20 and job["metrics"]["val_error"] == 0.08
        assert job["last_error"] is None

    @pytest.mark.parametrize(
        "line",
        [
            "ValueError: schema mismatch",
            "Traceback (most recent call last):",
            "torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.00 GiB",
            "ERROR: Could not find a version that satisfies the requirement torch==9",
            "Failed to connect to the data server",
        ],
    )
    def test_error_lines_are_errors(self, line):
        assert metrics.parse_log(["ok", line])["last_error"] == line

    @pytest.mark.parametrize("line", ["errors=0", "3 passed, 0 failed", "no error here", "error_rate: 0.1"])
    def test_lines_that_only_mention_errors_are_not_errors(self, line):
        assert metrics.parse_log([line])["last_error"] is None

    def test_hugging_face_and_json_metrics(self):
        hf = metrics.parse_log(["{'loss': 0.41, 'grad_norm': 1.2, 'learning_rate': 4.5e-05, 'epoch': 0.25}"])
        assert hf["metrics"] == {"loss": 0.41, "grad_norm": 1.2, "learning_rate": 4.5e-05}
        assert metrics.parse_log(['{"eval_loss": 0.38, "eval_accuracy": 0.91}'])["metrics"] == {
            "eval_loss": 0.38,
            "eval_accuracy": 0.91,
        }

    @pytest.mark.parametrize(
        "line", ["GPU mem: 15.2GB / 16GB, temp: 71C", "serving at http://localhost:8888", "took 3.2s"]
    )
    def test_numbers_with_units_and_addresses_are_not_metrics(self, line):
        assert metrics.parse_log([line])["metrics"] == {}

    def test_a_malformed_progress_clock_is_ignored(self):
        assert metrics.parse_log(["1/2 [1:2<3::4]"])["eta_s"] is None

    def test_long_digit_runs_parse_quickly(self):
        import time

        start = time.perf_counter()
        metrics.parse_log(["1" * 50_000, "/".join(["9" * 5_000] * 4)])
        assert time.perf_counter() - start < 0.5

    def test_only_the_newest_log_of_a_session_can_stall(self):
        session = {"name": "train", "endpoint": "e1", "status": "busy", "running": "run(x.py)"}
        logs = [
            {"name": "train-run1.log", "path": "/r/train-run1.log", "mtime": NOW - 86400, "lines": ["old"]},
            {"name": "train-run2.log", "path": "/r/train-run2.log", "mtime": NOW - 3600, "lines": ["new"]},
        ]
        jobs = metrics.compute_insights([session], {}, [], logs, None, now=NOW)["jobs"]
        stalled = {j["name"]: j["stalled"] for j in jobs}
        assert stalled == {"train-run1.log": False, "train-run2.log": True}
