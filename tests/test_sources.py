import json
import os

import pytest

from colab_monitor import sources


def _write_sessions(path, sessions):
    path.write_text(json.dumps(sessions))


def _session(name, endpoint, running=None, last_execution=None):
    return {
        "name": name,
        "token": "SECRET-TOKEN",
        "url": "https://proxy.example/secret",
        "endpoint": endpoint,
        "variant": "GPU",
        "accelerator": "T4",
        "machine_shape": "STANDARD",
        "kernel_id": "k-1",
        "running": running,
        "last_execution": last_execution,
    }


class TestLocalSessions:
    def test_missing_file_is_empty(self, tmp_path):
        assert sources.local_sessions(str(tmp_path / "nope.json")) == []

    def test_strips_secrets(self, tmp_path):
        path = tmp_path / "sessions.json"
        _write_sessions(
            path,
            {
                "job": _session(
                    "job",
                    "gpu-t4-abc",
                    running="run(train.py)",
                    last_execution=["train.py", None, "2026-10-23 17:00:00"],
                )
            },
        )
        [s] = sources.local_sessions(str(path))
        assert s["name"] == "job"
        assert s["endpoint"] == "gpu-t4-abc"
        assert s["accelerator"] == "T4"
        assert s["running"] == "run(train.py)"
        assert s["last_execution"] == {
            "source": "train.py",
            "time": "2026-10-23 17:00:00",
        }
        dumped = json.dumps(s)
        assert "SECRET-TOKEN" not in dumped
        assert "proxy.example" not in dumped


class TestMergeSessions:
    def test_matched_sessions_are_busy_or_idle(self):
        local = [
            {"name": "a", "endpoint": "e1", "running": "run(x.py)"},
            {"name": "b", "endpoint": "e2", "running": None},
        ]
        server = [
            {"endpoint": "e1", "accelerator": "T4"},
            {"endpoint": "e2", "accelerator": "NONE"},
        ]
        merged = {s["name"]: s for s in sources.merge_sessions(local, server)}
        assert merged["a"]["status"] == "busy"
        assert merged["b"]["status"] == "idle"
        assert merged["b"]["accelerator"] == "NONE"

    def test_server_only_assignment_is_orphan(self):
        merged = sources.merge_sessions([], [{"endpoint": "e9", "accelerator": "A100"}])
        assert merged == [
            {
                "name": None,
                "endpoint": "e9",
                "accelerator": "A100",
                "status": "orphan",
            }
        ]

    def test_local_only_session_is_gone(self):
        [s] = sources.merge_sessions([{"name": "a", "endpoint": "e1"}], [])
        assert s["status"] == "gone"

    def test_unknown_server_state_keeps_local_view(self):
        [s] = sources.merge_sessions([{"name": "a", "endpoint": "e1", "running": None}], None)
        assert s["status"] == "unknown"


class TestTailLines:
    def test_returns_last_lines(self, tmp_path):
        path = tmp_path / "train.log"
        path.write_text("".join(f"line {i}\n" for i in range(500)))
        lines = sources.tail_lines(str(path), max_lines=3)
        assert lines == ["line 497", "line 498", "line 499"]

    def test_carriage_return_keeps_final_progress_state(self, tmp_path):
        path = tmp_path / "train.log"
        path.write_text("epoch 1\n 10%|#\r 50%|#####\r100%|##########\ndone\n")
        assert sources.tail_lines(str(path)) == [
            "epoch 1",
            "100%|##########",
            "done",
        ]

    def test_reads_only_last_bytes_of_big_file(self, tmp_path):
        path = tmp_path / "big.log"
        path.write_text("x" * 1000 + "\n" + "tail\n")
        assert sources.tail_lines(str(path), max_bytes=10) == ["tail"]

    def test_missing_file_is_empty(self, tmp_path):
        assert sources.tail_lines(str(tmp_path / "missing.log")) == []


class TestLogs:
    def test_discovers_explicit_files_and_dir_entries(self, tmp_path):
        logdir = tmp_path / "runs"
        logdir.mkdir()
        (logdir / "a.log").write_text("a\n")
        (logdir / "b.out").write_text("b\n")
        (logdir / "notes.md").write_text("ignored\n")
        explicit = tmp_path / "train.log"
        explicit.write_text("t\n")

        logs = sources.discover_logs([str(explicit)], [str(logdir)])
        names = sorted(entry["name"] for entry in logs)
        assert names == ["a.log", "b.out", "train.log"]
        assert all(entry["exists"] for entry in logs)

    def test_resolves_only_configured_paths(self, tmp_path):
        logdir = tmp_path / "runs"
        logdir.mkdir()
        (logdir / "a.log").write_text("a\n")
        secret = tmp_path / "secret.log"
        secret.write_text("no\n")

        assert sources.resolve_log(str(logdir / "a.log"), [], [str(logdir)]) == str(
            (logdir / "a.log").resolve()
        )
        assert sources.resolve_log(str(secret), [], [str(logdir)]) is None
        assert sources.resolve_log(str(logdir / ".." / "secret.log"), [], [str(logdir)]) is None
        assert sources.resolve_log(str(secret), [str(secret)], []) == str(secret.resolve())

    def test_a_path_the_os_cannot_hold_is_refused(self, tmp_path):
        assert sources.resolve_log(str(tmp_path / "a.log\x00"), [], [str(tmp_path)]) is None

    def test_resolves_to_the_file_it_checked(self, tmp_path, monkeypatch):
        logdir = tmp_path / "runs"
        logdir.mkdir()
        (logdir / "a.log").write_text("a\n")
        monkeypatch.setenv("HOME", str(tmp_path))
        real = str((logdir / "a.log").resolve())
        assert sources.resolve_log("~/runs/a.log", [], [str(logdir)]) == real
        assert sources.resolve_log(str(logdir / "a.log") + "/", [], [str(logdir)]) == real

    def test_symlinks_that_leave_the_folder_are_not_listed(self, tmp_path):
        logdir = tmp_path / "runs"
        logdir.mkdir()
        (logdir / "a.log").write_text("a\n")
        (tmp_path / "secret.log").write_text("no\n")
        (logdir / "link-in.log").symlink_to("a.log")
        (logdir / "link-out.log").symlink_to("../secret.log")
        names = sorted(e["name"] for e in sources.discover_logs([], [str(logdir)]))
        assert names == ["a.log", "link-in.log"]


class TestHistory:
    def _write(self, history_dir, name, events):
        with open(os.path.join(history_dir, f"{name}.jsonl"), "w") as f:
            f.writelines(json.dumps(e) + "\n" for e in events)

    def test_names_sorted_newest_first(self, tmp_path):
        self._write(tmp_path, "old", [])
        self._write(tmp_path, "new", [])
        os.utime(tmp_path / "old.jsonl", (1, 1))
        assert sources.history_names(str(tmp_path)) == ["new", "old"]

    def test_rejects_path_traversal(self, tmp_path):
        with pytest.raises(ValueError):
            sources.read_history(str(tmp_path), "../sessions")

    def test_summarises_execution_outputs(self, tmp_path):
        self._write(
            tmp_path,
            "job",
            [
                {
                    "timestamp": "t0",
                    "event_type": "session_created",
                    "accelerator": "T4",
                },
                {
                    "timestamp": "t1",
                    "event_type": "execution",
                    "code": "print('hi')",
                    "outputs": [
                        {"output_type": "stream", "name": "stdout", "text": "hi\n"},
                        {
                            "output_type": "display_data",
                            "data": {"image/png": "AAAA" * 1000},
                        },
                        {
                            "output_type": "error",
                            "ename": "ValueError",
                            "evalue": "bad",
                            "traceback": [],
                        },
                    ],
                },
            ],
        )
        events = sources.read_history(str(tmp_path), "job")
        assert [e["type"] for e in events] == ["session_created", "execution"]
        execution = events[1]
        assert execution["code"] == "print('hi')"
        assert execution["output"] == "hi\n"
        assert execution["images"] == 1
        assert execution["error"] == "ValueError: bad"
        assert "AAAA" not in json.dumps(events)

    def test_limit_keeps_latest_events(self, tmp_path):
        self._write(
            tmp_path,
            "job",
            [{"timestamp": f"t{i}", "event_type": "ls"} for i in range(10)],
        )
        events = sources.read_history(str(tmp_path), "job", limit=2)
        assert [e["timestamp"] for e in events] == ["t8", "t9"]


class TestRecentActivity:
    def _write(self, history_dir, name, events):
        with open(os.path.join(history_dir, f"{name}.jsonl"), "w") as f:
            f.writelines(json.dumps(e) + "\n" for e in events)

    def test_merges_sessions_newest_first(self, tmp_path):
        self._write(
            tmp_path,
            "a",
            [
                {"timestamp": "2026-10-23T01:00:00+00:00", "event_type": "session_created"},
                {"timestamp": "2026-10-23T03:00:00+00:00", "event_type": "session_terminated"},
            ],
        )
        self._write(
            tmp_path,
            "b",
            [{"timestamp": "2026-10-23T02:00:00+00:00", "event_type": "execution", "code": "x"}],
        )
        events = sources.recent_activity(str(tmp_path), limit=10)
        assert [(e["session"], e["type"]) for e in events] == [
            ("a", "session_terminated"),
            ("b", "execution"),
            ("a", "session_created"),
        ]

    def test_limit(self, tmp_path):
        self._write(
            tmp_path,
            "a",
            [{"timestamp": f"2026-10-23T0{i}:00:00+00:00", "event_type": "ls"} for i in range(5)],
        )
        events = sources.recent_activity(str(tmp_path), limit=2)
        assert [e["timestamp"][11:13] for e in events] == ["04", "03"]

    def test_missing_dir_is_empty(self, tmp_path):
        assert sources.recent_activity(str(tmp_path / "nope")) == []


class TestAnsi:
    def test_tail_strips_terminal_colour_codes(self, tmp_path):
        path = tmp_path / "job.log"
        path.write_text("\x1b[0;31mValueError\x1b[0m: bad\n\x1b[1mbold\x1b[22m line\n")
        assert sources.tail_lines(str(path)) == ["ValueError: bad", "bold line"]

    def test_history_errors_and_output_are_clean(self, tmp_path):
        with open(tmp_path / "job.jsonl", "w") as f:
            f.write(
                json.dumps(
                    {
                        "timestamp": "t1",
                        "event_type": "execution",
                        "outputs": [
                            {"output_type": "stream", "name": "stderr", "text": "\x1b[33mwarn\x1b[0m\n"},
                            {
                                "output_type": "error",
                                "ename": "\x1b[0;31mValueError\x1b[0m",
                                "evalue": "x",
                                "traceback": [],
                            },
                        ],
                    }
                )
                + "\n"
            )
        [event] = sources.read_history(str(tmp_path), "job")
        assert event["output"] == "warn\n"
        assert event["error"] == "ValueError: x"


class TestHistoryEndpoints:
    def _write(self, history_dir, name, events):
        with open(os.path.join(history_dir, f"{name}.jsonl"), "w") as f:
            f.writelines(json.dumps(e) + "\n" for e in events)

    def test_maps_endpoints_to_names_and_ended_state(self, tmp_path):
        self._write(
            tmp_path,
            "done",
            [
                {"timestamp": "t0", "event_type": "session_created", "endpoint": "e1"},
                {"timestamp": "t1", "event_type": "session_terminated", "reason": "user_requested"},
            ],
        )
        self._write(
            tmp_path,
            "live",
            [
                {"timestamp": "t0", "event_type": "session_created", "endpoint": "e2"},
                {"timestamp": "t1", "event_type": "execution", "code": "x"},
            ],
        )
        found = sources.history_endpoints(str(tmp_path))
        assert {e: v["name"] for e, v in found.items()} == {"e1": "done", "e2": "live"}
        assert isinstance(found["e1"]["ended"], float) and found["e2"]["ended"] is None

    def test_reused_name_tracks_latest_session(self, tmp_path):
        self._write(
            tmp_path,
            "job",
            [
                {"timestamp": "t0", "event_type": "session_created", "endpoint": "old"},
                {"timestamp": "t1", "event_type": "session_terminated"},
                {"timestamp": "t2", "event_type": "session_created", "endpoint": "new"},
            ],
        )
        found = sources.history_endpoints(str(tmp_path))
        assert found["old"]["ended"] is not None
        assert found["new"]["ended"] is None


class TestMergeWithHistory:
    def test_just_stopped_machine_is_stopping_not_orphan(self):
        [s] = sources.merge_sessions(
            [],
            [{"endpoint": "e1", "accelerator": "NONE"}],
            {"e1": {"name": "nb", "ended": 990.0}},
            now=1000.0,
        )
        assert s["status"] == "stopping"
        assert s["name"] == "nb"

    def test_orphan_known_from_history_keeps_its_name(self):
        [s] = sources.merge_sessions(
            [], [{"endpoint": "e1", "accelerator": "NONE"}], {"e1": {"name": "other", "ended": None}}
        )
        assert s["status"] == "orphan"
        assert s["name"] == "other"


class TestFreshMachine:
    """A machine where the colab CLI has never run: no ~/.config/colab-cli at all."""

    def test_no_cli_state_means_no_sessions_and_no_files_created(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        assert sources.local_sessions() == []
        assert not (tmp_path / ".config").exists()  # read-only: never create the CLI's folders


class TestSeveralStateFiles:
    """Agents isolate runs with `colab --config FILE`; the dashboard must read those files too."""

    def test_merges_sessions_from_every_file(self, tmp_path):
        a, b = tmp_path / "default.json", tmp_path / "agent.json"
        _write_sessions(a, {"main": _session("main", "e1")})
        _write_sessions(b, {"job": _session("job", "e2", running="run(train.py)")})
        names = sorted(s["name"] for s in sources.local_sessions([str(a), str(b)]))
        assert names == ["job", "main"]

    def test_same_machine_in_two_files_is_listed_once(self, tmp_path):
        a, b = tmp_path / "a.json", tmp_path / "b.json"
        _write_sessions(a, {"job": _session("job", "e1")})
        _write_sessions(b, {"job-copy": _session("job-copy", "e1")})
        assert [s["name"] for s in sources.local_sessions([str(a), str(b)])] == ["job"]

    def test_missing_files_are_skipped(self, tmp_path):
        a = tmp_path / "a.json"
        _write_sessions(a, {"main": _session("main", "e1")})
        assert [s["name"] for s in sources.local_sessions([str(tmp_path / "nope.json"), str(a)])] == ["main"]

    def test_isolated_agent_session_is_not_an_orphan(self, tmp_path):
        a, b = tmp_path / "default.json", tmp_path / "agent.json"
        _write_sessions(a, {})
        _write_sessions(b, {"job": _session("job", "e2")})
        merged = sources.merge_sessions(sources.local_sessions([str(a), str(b)]), [{"endpoint": "e2"}])
        assert merged[0]["status"] == "idle"


class TestSessionTimelines:
    def _write(self, history_dir, name, events):
        with open(os.path.join(history_dir, f"{name}.jsonl"), "w") as f:
            f.writelines(json.dumps(e) + "\n" for e in events)

    def test_builds_one_timeline_per_machine(self, tmp_path):
        self._write(
            tmp_path,
            "train",
            [
                {
                    "timestamp": "2026-10-23T10:00:00+00:00",
                    "event_type": "session_created",
                    "endpoint": "e1",
                    "accelerator": "T4",
                },
                {
                    "timestamp": "2026-10-23T10:05:00+00:00",
                    "event_type": "execution",
                    "outputs": [{"output_type": "stream", "text": "ok"}],
                },
                {
                    "timestamp": "2026-10-23T10:09:00+00:00",
                    "event_type": "execution",
                    "outputs": [
                        {"output_type": "error", "ename": "\x1b[31mValueError\x1b[0m", "evalue": "bad"}
                    ],
                },
                {
                    "timestamp": "2026-10-23T10:10:00+00:00",
                    "event_type": "session_terminated",
                    "reason": "run_failed",
                },
                {
                    "timestamp": "2026-10-23T11:00:00+00:00",
                    "event_type": "session_created",
                    "endpoint": "e2",
                    "accelerator": "NONE",
                },
            ],
        )
        t = sources.session_timelines(str(tmp_path))
        base = 1792749600.0  # 2026-10-23T10:00:00Z
        assert t["e1"] == {
            "name": "train",
            "accelerator": "T4",
            "created": base,
            "ended": base + 600,
            "last_activity": base + 600,
            "executions": [(base + 300, False), (base + 540, True)],
            "last_error": "ValueError: bad",
        }
        assert t["e2"]["ended"] is None and t["e2"]["accelerator"] == "NONE" and t["e2"]["executions"] == []

    def test_ignores_events_before_any_creation_and_bad_lines(self, tmp_path):
        (tmp_path / "x.jsonl").write_text(
            '{"timestamp": "2026-10-23T10:00:00+00:00", "event_type": "execution"}\nnot json\n'
        )
        assert sources.session_timelines(str(tmp_path)) == {}

    def test_rereads_a_file_only_when_it_changes(self, tmp_path, monkeypatch):
        self._write(
            tmp_path,
            "a",
            [{"timestamp": "2026-10-23T10:00:00+00:00", "event_type": "session_created", "endpoint": "e1"}],
        )
        first = sources.session_timelines(str(tmp_path))
        calls = []
        real = sources._timelines_in_file
        monkeypatch.setattr(sources, "_timelines_in_file", lambda *a: calls.append(a) or real(*a))
        assert sources.session_timelines(str(tmp_path)) == first and calls == []
        with open(tmp_path / "a.jsonl", "a") as f:
            f.write(
                json.dumps({"timestamp": "2026-10-23T10:30:00+00:00", "event_type": "session_terminated"})
                + "\n"
            )
        assert sources.session_timelines(str(tmp_path))["e1"]["ended"] is not None and len(calls) == 1


class TestLogTails:
    def test_tails_every_log_with_its_mtime(self, tmp_path):
        p = tmp_path / "train.log"
        p.write_text("a\nb\nc\n")
        [tail] = sources.log_tails(
            [{"name": "train.log", "path": str(p), "exists": True, "mtime": 5.0, "size": 6}], lines=2
        )
        assert tail == {"name": "train.log", "path": str(p), "mtime": 5.0, "lines": ["b", "c"]}

    def test_skips_missing_files(self):
        assert (
            sources.log_tails(
                [{"name": "x.log", "path": "/nope/x.log", "exists": False, "mtime": None, "size": 0}]
            )
            == []
        )


class TestSourcesEdgeCases:
    def test_tail_tolerates_invalid_utf8(self, tmp_path):
        path = tmp_path / "x.log"
        path.write_bytes(b"ok\n\xff\xfe broken\n")
        lines = sources.tail_lines(str(path))
        assert lines[0] == "ok" and "broken" in lines[1]

    def test_discover_logs_ignores_missing_dirs_and_duplicates(self, tmp_path):
        d = tmp_path / "runs"
        d.mkdir()
        (d / "a.log").write_text("a\n")
        logs = sources.discover_logs([str(d / "a.log")], [str(d), str(tmp_path / "missing")])
        assert [entry["name"] for entry in logs] == ["a.log"]

    def test_read_history_skips_corrupt_lines(self, tmp_path):
        (tmp_path / "job.jsonl").write_text('{"timestamp": "t0", "event_type": "ls"}\nnot json\n')
        assert [e["type"] for e in sources.read_history(str(tmp_path), "job")] == ["ls"]

    def test_history_endpoints_refresh_when_file_changes(self, tmp_path):
        path = tmp_path / "job.jsonl"
        path.write_text(
            json.dumps({"timestamp": "t0", "event_type": "session_created", "endpoint": "e1"}) + "\n"
        )
        assert sources.history_endpoints(str(tmp_path))["e1"]["ended"] is None
        with open(path, "a") as f:
            f.write(json.dumps({"timestamp": "t1", "event_type": "session_terminated"}) + "\n")
        assert sources.history_endpoints(str(tmp_path))["e1"]["ended"] is not None

    def test_strip_ansi_handles_cursor_and_title_codes(self):
        assert sources.strip_ansi("\x1b[2K\x1b[1Gdone\x1b]0;title\x07!") == "done!"


class TestReviewFindings:
    """Edge cases from the review of the insights feature."""

    @staticmethod
    def _history(path, events):
        path.write_text("".join(e if isinstance(e, str) else json.dumps(e) + "\n" for e in events))

    def _run(self, tmp_path, outputs):
        history = tmp_path / "history"
        history.mkdir(exist_ok=True)
        self._history(
            history / "job.jsonl",
            [
                {"timestamp": "2026-10-24T10:00:00+00:00", "event_type": "session_created", "endpoint": "e1"},
                {"timestamp": "2026-10-24T10:05:00+00:00", "event_type": "execution", "outputs": outputs},
            ],
        )
        sources._timeline_cache.clear()
        return sources.session_timelines(str(history))["e1"]

    @pytest.mark.parametrize("evalue", ["", "None", "0"])
    def test_a_clean_sys_exit_is_not_a_failed_run(self, tmp_path, evalue):
        ename = "\x1b[0;31mSystemExit\x1b[0m"  # Colab colours exception names
        tl = self._run(tmp_path, [{"output_type": "error", "ename": ename, "evalue": evalue}])
        assert tl["executions"][0][1] is False and tl["last_error"] is None

    @pytest.mark.parametrize("evalue", ["1", "3", "'bad input'"])
    def test_sys_exit_with_a_failure_code_is_a_failed_run(self, tmp_path, evalue):
        tl = self._run(tmp_path, [{"output_type": "error", "ename": "SystemExit", "evalue": evalue}])
        assert tl["executions"][0][1] is True and tl["last_error"] == f"SystemExit: {evalue}"

    def test_history_readers_skip_lines_that_are_not_objects(self, tmp_path):
        history = tmp_path / "history"
        history.mkdir()
        self._history(
            history / "job.jsonl",
            [
                "null\n",
                "[1, 2]\n",
                '"text"\n',
                {"timestamp": 12345, "event_type": "execution"},
                {"timestamp": "2026-10-24T10:00:00+00:00", "event_type": "session_created", "endpoint": "e1"},
            ],
        )
        sources._timeline_cache.clear()
        sources._endpoint_cache.clear()
        events = sources.read_history(str(history), "job")
        assert [e["type"] for e in events] == ["execution", "session_created"]
        assert events[0]["timestamp"] is None
        assert sources.recent_activity(str(history))
        assert "e1" in sources.session_timelines(str(history))
        assert "e1" in sources.history_endpoints(str(history))

    def test_strip_ansi_removes_titles_links_and_resets(self):
        line = "\x1b]0;TITLE\x1b\\Error: \x1b]8;;https://x\x1b\\boom\x1b]8;;\x1b\\\x1bc"
        assert sources.strip_ansi(line) == "Error: boom"


class TestSecondReviewFindings:
    """Edge cases from the review of the dashboard, server, and data readers."""

    def test_a_progress_bar_longer_than_the_read_window_shows_its_last_state(self, tmp_path):
        path = tmp_path / "train.log"
        bar = "".join(f"\rtrain: {i % 100:3d}%|{'#' * (i % 10):<10}| {i}/10000" for i in range(10000))
        path.write_text(bar + "\rtrain: 100%|##########| 10000/10000")
        assert len(path.read_bytes()) > 256 * 1024
        assert sources.tail_lines(str(path)) == ["train: 100%|##########| 10000/10000"]

    @pytest.mark.parametrize("name", ["my run", "lr=3e-4", "exp+1", "thí nghiệm"])
    def test_any_session_name_the_cli_accepts_has_history(self, tmp_path, name):
        (tmp_path / f"{name}.jsonl").write_text(
            json.dumps({"timestamp": "2026-10-24T10:00:00+00:00", "event_type": "session_created"}) + "\n"
        )
        assert name in sources.history_names(str(tmp_path))
        assert [e["type"] for e in sources.read_history(str(tmp_path), name)] == ["session_created"]
        assert sources.recent_activity(str(tmp_path))[0]["session"] == name

    @pytest.mark.parametrize("name", ["", ".", "..", "../secret", "a/b", "a\\b", ".hidden", "a\x00b"])
    def test_names_that_could_leave_the_history_folder_are_refused(self, tmp_path, name):
        with pytest.raises(ValueError):
            sources.read_history(str(tmp_path), name)

    def test_hidden_files_are_not_listed_as_sessions(self, tmp_path):
        (tmp_path / ".hidden.jsonl").write_text("")
        (tmp_path / "job.jsonl").write_text("")
        assert sources.history_names(str(tmp_path)) == ["job"]

    def test_text_typed_at_input_prompts_is_not_shown(self):
        event = {"timestamp": "2026-10-24T10:00:00+00:00", "event_type": "input_reply", "value": "hf_secret"}
        summary = sources.summarize_event(event)
        assert "hf_secret" not in json.dumps(summary)
        assert summary["details"]["value"] == "(hidden)"

    def test_outputs_that_are_not_objects_are_skipped(self):
        event = {
            "event_type": "execution",
            "outputs": ["text", None, {"output_type": "stream", "text": "ok"}],
        }
        assert sources.summarize_event(event)["output"] == "ok"

    def test_a_machine_colab_still_lists_long_after_stopping_is_an_orphan(self):
        now = 1_800_000_000.0
        assignment = [{"endpoint": "e1", "accelerator": "T4"}]
        recent = {"e1": {"name": "job", "ended": now - 60}}
        old = {"e1": {"name": "job", "ended": now - 3600}}
        assert sources.merge_sessions([], assignment, recent, now=now)[0]["status"] == "stopping"
        merged = sources.merge_sessions([], assignment, old, now=now)[0]
        assert merged["status"] == "orphan" and merged["name"] == "job"

    def test_history_records_when_a_machine_was_stopped(self, tmp_path):
        (tmp_path / "job.jsonl").write_text(
            json.dumps(
                {"timestamp": "2026-10-24T10:00:00+00:00", "event_type": "session_created", "endpoint": "e1"}
            )
            + "\n"
            + json.dumps({"timestamp": "2026-10-24T11:00:00+00:00", "event_type": "session_terminated"})
            + "\n"
        )
        sources._endpoint_cache.clear()
        ended = sources.history_endpoints(str(tmp_path))["e1"]["ended"]
        assert ended == pytest.approx(sources._epoch("2026-10-24T11:00:00+00:00"))
