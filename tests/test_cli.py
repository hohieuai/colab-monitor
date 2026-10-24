"""The colab-monitor command: subcommands, the status report, its rendering, and exit codes."""

import json
import pathlib
import re
import threading
import time

import pytest

from colab_monitor import cli
from colab_monitor.server import make_server

from .e2e.fixtures import build_data, sample_dashboard

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


@pytest.fixture(scope="module")
def fixture_state(tmp_path_factory):
    data = build_data(tmp_path_factory.mktemp("cli"))
    app = sample_dashboard(data)
    _, state = app.handle("/api/state", {})
    return state, app


@pytest.fixture
def running_dashboard(fixture_state):
    _, app = fixture_state
    server = make_server(app, "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


# ---------- Dispatch ----------


class TestDispatch:
    @pytest.mark.parametrize(
        ("argv", "command", "rest"),
        [
            ([], "serve", []),
            (["--port", "9"], "serve", ["--port", "9"]),
            (["serve", "--open"], "serve", ["--open"]),
            (["status", "--json"], "status", ["--json"]),
            (["watch"], "watch", []),
        ],
    )
    def test_routes_to_the_command(self, monkeypatch, argv, command, rest):
        called = {}

        def mock_command(name):
            def run(args):
                called[name] = args
                return 0

            return run

        for name in ("serve", "status", "watch"):
            monkeypatch.setitem(cli.COMMANDS, name, mock_command(name))
        assert cli.main(argv) == 0
        assert called == {command: rest}

    def test_top_level_help_lists_the_commands(self, capsys):
        assert cli.main(["--help"]) == 0
        out = capsys.readouterr().out
        for command in ("serve", "status", "watch"):
            assert command in out
        assert "colab-monitor COMMAND -h" in out

    def test_version(self, capsys):
        with pytest.raises(SystemExit) as exit_info:
            cli.main(["--version"])
        assert exit_info.value.code == 0 and "colab-monitor" in capsys.readouterr().out


# ---------- The report (the --json contract) ----------


class TestReport:
    def test_report_shape(self, fixture_state):
        state, _ = fixture_state
        report = cli.build_report(state, source="dashboard")
        assert report["schema"] == 1 and report["source"] == "dashboard"
        assert set(report) == {
            "schema",
            "source",
            "generated_at",
            "colab",
            "compute_units",
            "runway",
            "spend",
            "machines",
            "jobs",
            "runs",
            "machine_hours_7d",
            "attention",
            "thresholds",
        }
        assert report["compute_units"]["rate_per_hour"] == pytest.approx(1.76)
        names = {m["name"] for m in report["machines"]}
        assert {"train-gpu", "eval-cpu", "old-job", "side-run"} <= names
        assert all("token" not in json.dumps(m).lower() for m in report["machines"])
        machine = next(m for m in report["machines"] if m["name"] == "train-gpu")
        assert set(machine) >= {
            "name",
            "endpoint",
            "status",
            "hardware",
            "job",
            "uptime_s",
            "idle_s",
            "rate",
            "rate_estimated",
            "cost",
        }
        assert machine["hardware"] == "T4"

    def test_released_machines_are_left_out(self, fixture_state):
        state, _ = fixture_state
        state = json.loads(json.dumps(state))
        state["sessions"].append(
            {"endpoint": "x", "status": "gone", "name": "old", "accelerator": "T4", "metrics": None}
        )
        assert "x" not in {m["endpoint"] for m in cli.build_report(state, source="direct")["machines"]}

    def test_report_is_json_serialisable(self, fixture_state):
        state, _ = fixture_state
        json.dumps(cli.build_report(state, source="direct"))


# ---------- Rendering ----------


class TestRender:
    def test_sections_and_values(self, fixture_state):
        state, _ = fixture_state
        text = cli.render(cli.build_report(state, source="dashboard"), width=120, color=False)
        for expected in (
            "Compute units",
            "Usage",
            "Runway",
            "Spent",
            "MACHINE",
            "train-gpu",
            "running",
            "JOBS",
            "NEEDS ATTENTION",
        ):
            assert expected in text, expected
        assert "\x1b[" not in text

    @pytest.mark.parametrize("width", [60, 80, 120, 200])
    def test_no_line_is_wider_than_the_terminal(self, fixture_state, width):
        state, _ = fixture_state
        text = cli.render(cli.build_report(state, source="dashboard"), width=width, color=True)
        widest = max(len(ANSI.sub("", line)) for line in text.splitlines())
        assert widest <= width

    def test_colour_marks_status_and_attention(self, fixture_state):
        state, _ = fixture_state
        text = cli.render(cli.build_report(state, source="dashboard"), width=120, color=True)
        assert "\x1b[31m" in text  # red for the orphan
        assert "\x1b[32m" in text  # green for running

    def test_estimated_rates_are_marked(self):
        report = _minimal_report(
            machines=[_machine(rate=11.77, estimated=True), _machine(name="b", rate=1.76, estimated=False)]
        )
        text = cli.render(report, width=120, color=False)
        assert "≈11.77/h" in text and " 1.76/h" in text

    def test_runway_time_and_quiet_state(self, monkeypatch):
        monkeypatch.setenv("TZ", "UTC")
        time.tzset()
        report = _minimal_report(runway={"hours": 60.0, "empty_at": 1_800_000_000.0})
        text = cli.render(report, width=100, color=False, now=1_800_000_000.0 - 60 * 3600)
        assert "2.5 days" in text and "Fri 08:00" in text
        assert "Nothing needs attention." in text
        assert "No machines are running." in text

    def test_colab_problems_are_explained(self):
        failing = _minimal_report(
            colab={"enabled": True, "ok": False, "error": "HTTP 429", "checked_at": None}
        )
        assert "Colab check failed: HTTP 429" in cli.render(failing, width=100, color=False)
        local = _minimal_report(colab={"enabled": False, "ok": False, "error": None, "checked_at": None})
        assert "Local files only" in cli.render(local, width=100, color=False)


def _machine(name="a", rate=1.0, estimated=True, status="busy"):
    return {
        "name": name,
        "endpoint": f"ep-{name}",
        "status": status,
        "hardware": "T4",
        "job": "run(x.py)",
        "uptime_s": 3600.0,
        "idle_s": 0.0,
        "rate": rate,
        "rate_estimated": estimated,
        "cost": rate,
        "idle_cost": None,
    }


def _minimal_report(**overrides):
    report = {
        "schema": 1,
        "source": "direct",
        "generated_at": "2026-10-24T00:00:00+00:00",
        "colab": {"enabled": True, "ok": True, "error": None, "checked_at": "2026-10-24T00:00:00+00:00"},
        "compute_units": {"balance": 100.0, "rate_per_hour": 0.0},
        "runway": {"hours": None, "empty_at": None},
        "spend": {"today": 1.0, "7d": 2.0, "30d": 3.0, "measured_since": None},
        "machines": [],
        "jobs": [],
        "runs": {"24h": {"ok": 0, "failed": 0}, "7d": {"ok": 0, "failed": 0}},
        "machine_hours_7d": {},
        "attention": [],
        "thresholds": {"idle_minutes": 30, "stall_minutes": 15, "runway_hours": 12},
    }
    report.update(overrides)
    return report


# ---------- The status command ----------


class TestStatusCommand:
    def test_reads_a_running_dashboard(self, running_dashboard, capsys):
        assert cli.main(["status", "--port", str(running_dashboard), "--json"]) == 0
        report = json.loads(capsys.readouterr().out)
        assert report["source"] == "dashboard" and report["schema"] == 1

    def test_exit_code_reports_attention(self, running_dashboard, capsys):
        assert cli.main(["status", "--port", str(running_dashboard), "--exit-code"]) == 3
        assert "NEEDS ATTENTION" in capsys.readouterr().out

    def test_thresholds_are_passed_to_the_dashboard(self, running_dashboard, capsys):
        cli.main(["status", "--port", str(running_dashboard), "--json", "--idle-alert", "999"])
        assert json.loads(capsys.readouterr().out)["thresholds"]["idle_minutes"] == 999

    def test_works_without_a_dashboard(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / "runs").mkdir()
        argv = [
            "status",
            "--port",
            "1",
            "--no-api",
            "--json",
            "--history-dir",
            str(tmp_path / "h"),
            "--log-dir",
            str(tmp_path / "runs"),
            "--usage-log",
            str(tmp_path / "u.jsonl"),
        ]
        assert cli.main(argv) == 0
        report = json.loads(capsys.readouterr().out)
        assert (
            report["source"] == "direct" and report["colab"]["enabled"] is False and report["machines"] == []
        )

    def test_quiet_account_exits_zero_with_exit_code(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        argv = [
            "status",
            "--port",
            "1",
            "--no-api",
            "--exit-code",
            "--history-dir",
            str(tmp_path / "h"),
            "--log-dir",
            str(tmp_path),
            "--usage-log",
            str(tmp_path / "u.jsonl"),
        ]
        assert cli.main(argv) == 0

    def test_not_signed_in_falls_back_to_local_files(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))  # no ~/.config/colab-cli/token.json
        argv = [
            "status",
            "--port",
            "1",
            "--json",
            "--history-dir",
            str(tmp_path / "h"),
            "--log-dir",
            str(tmp_path),
            "--usage-log",
            str(tmp_path / "u.jsonl"),
        ]
        assert cli.main(argv) == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out)["colab"]["enabled"] is False
        assert "not signed in" in captured.err.lower() and "colab sessions" in captured.err

    def test_no_color_when_piped_or_asked(self, running_dashboard, capsys, monkeypatch):
        cli.main(["status", "--port", str(running_dashboard)])
        assert "\x1b[" not in capsys.readouterr().out  # capsys is not a terminal
        monkeypatch.setattr(cli, "_stdout_is_tty", lambda: True)
        monkeypatch.setenv("NO_COLOR", "1")
        cli.main(["status", "--port", str(running_dashboard)])
        assert "\x1b[" not in capsys.readouterr().out


# ---------- The watch command ----------


def test_watch_needs_a_terminal(capsys):
    assert cli.main(["watch", "--port", "1", "--no-api"]) == 2
    assert "needs a terminal" in capsys.readouterr().err


def test_package_entry_point_is_the_cli():
    pyproject = (pathlib.Path(__file__).parent.parent / "pyproject.toml").read_text()
    assert 'colab-monitor = "colab_monitor.cli:main"' in pyproject


# ---------- Edge cases ----------


def test_unknown_command_is_an_error(capsys):
    assert cli.main(["stauts"]) == 2
    assert "unknown command 'stauts'" in capsys.readouterr().err


def test_bad_threshold_is_rejected(capsys):
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["status", "--idle-alert", "0"])
    assert exit_info.value.code == 2 and "--idle-alert must be a positive number" in capsys.readouterr().err


def test_data_options_read_files_directly(running_dashboard, tmp_path, capsys, monkeypatch):
    # A running dashboard reads its own files, so asking for other files skips it.
    monkeypatch.setenv("HOME", str(tmp_path))
    argv = ["status", "--port", str(running_dashboard), "--json", "--no-api", "--history-dir", str(tmp_path)]
    assert cli.main(argv) == 0
    assert json.loads(capsys.readouterr().out)["source"] == "direct"


def test_something_else_on_the_port_is_ignored(tmp_path, capsys, monkeypatch):
    import http.server

    class NotUs(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    other = http.server.ThreadingHTTPServer(("127.0.0.1", 0), NotUs)
    threading.Thread(target=other.serve_forever, daemon=True).start()
    monkeypatch.setenv("HOME", str(tmp_path))
    try:
        assert cli.main(["status", "--port", str(other.server_address[1]), "--json"]) == 0
    finally:
        other.shutdown()
        other.server_close()
    assert json.loads(capsys.readouterr().out)["source"] == "direct"


def _job(name, silent_s, **fields):
    return {
        "name": name,
        "path": f"/runs/{name}",
        "session": None,
        "silent_s": silent_s,
        "stalled": False,
        "progress": None,
        "eta_s": None,
        "speed": None,
        "metrics": {},
        "last_error": None,
        **fields,
    }


class TestJobs:
    def test_progress_eta_speed_and_metrics(self):
        job = _job(
            "train-gpu.log",
            3.0,
            session="train-gpu",
            progress=0.42,
            eta_s=1500,
            speed="3.1it/s",
            metrics={"loss": 0.25, "acc": 0.9},
        )
        text = cli.render(_minimal_report(jobs=[job]), width=120, color=False)
        line = next(line for line in text.splitlines() if line.startswith("train-gpu.log"))
        for expected in (
            "42%",
            "ETA 25 min",
            "3.1it/s",
            "loss 0.25",
            "acc 0.9",
            "on train-gpu",
            "updated just now",
        ):
            assert expected in line, expected

    def test_stalled_jobs_and_errors_stand_out(self):
        job = _job("a.log", 1200.0, session="a", stalled=True, last_error="CUDA out of memory")
        text = cli.render(_minimal_report(jobs=[job]), width=120, color=True)
        assert "\x1b[33mstalled 20 min" in text
        assert "\x1b[31mCUDA out of memory" in text

    def test_newest_logs_first_and_the_rest_counted(self):
        jobs = [_job(f"run{i}.log", float(i * 60)) for i in range(12)]
        text = cli.render(_minimal_report(jobs=list(reversed(jobs))), width=120, color=False)
        names = [line.split()[0] for line in text.splitlines() if line.startswith("run")]
        assert names == [f"run{i}.log" for i in range(cli.MAX_JOBS_SHOWN)]
        assert "and 4 older logs" in text


def test_an_older_dashboard_is_skipped(tmp_path, capsys, monkeypatch):
    import http.server

    class Older(http.server.BaseHTTPRequestHandler):
        server_version = "colab-monitor/0.1.0"

        def do_GET(self):
            body = json.dumps({"version": "0.1.0", "api": {}, "sessions": []}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    older = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Older)
    threading.Thread(target=older.serve_forever, daemon=True).start()
    monkeypatch.setenv("HOME", str(tmp_path))
    try:
        assert cli.main(["status", "--port", str(older.server_address[1]), "--json"]) == 0
    finally:
        older.shutdown()
        older.server_close()
    captured = capsys.readouterr()
    assert json.loads(captured.out)["source"] == "direct"
    assert "older version" in captured.err


class TestReviewFindings:
    """Edge cases from the review of the insights feature."""

    def test_a_non_http_service_on_the_port_is_skipped(self, tmp_path, capsys, monkeypatch):
        import socketserver

        class Banner(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.sendall(b"SSH-2.0-OpenSSH_9.6\r\n")

        service = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Banner)
        threading.Thread(target=service.serve_forever, daemon=True).start()
        monkeypatch.setenv("HOME", str(tmp_path))
        try:
            assert cli.main(["status", "--port", str(service.server_address[1]), "--json"]) == 0
        finally:
            service.shutdown()
            service.server_close()
        assert json.loads(capsys.readouterr().out)["source"] == "direct"

    def test_a_slow_dashboard_is_still_used(self, fixture_state, capsys):
        _, app = fixture_state

        class Slow:
            def handle(self, path, query):
                time.sleep(1.0)
                return app.handle(path, query)

        server = make_server(Slow(), "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            assert cli.main(["status", "--port", str(server.server_address[1]), "--json"]) == 0
        finally:
            server.shutdown()
            server.server_close()
        assert json.loads(capsys.readouterr().out)["source"] == "dashboard"

    def test_unknown_usage_is_not_reported_as_idle(self):
        text = cli.render(_minimal_report(compute_units={"balance": None, "rate_per_hour": None}), width=100)
        assert "nothing is using" not in text
        idle = _minimal_report(compute_units={"balance": 5.0, "rate_per_hour": 0.0})
        assert "nothing is using compute units" in cli.render(idle, width=100)

    def test_terminal_control_codes_in_logs_are_not_printed(self):
        job = _job("x.log", 3.0, last_error="\x1b]0;pwned\x07boom\x1bc")
        text = cli.render(_minimal_report(jobs=[job]), width=120, color=True)
        assert "\x1b]" not in text and "\x1bc" not in text and "\x07" not in text
        assert "boom" in text
