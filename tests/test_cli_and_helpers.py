"""Server-side helpers: command-line options, the Colab adapter, input limits."""

import json
import os
from types import SimpleNamespace

import pytest

from colab_monitor import server, sources
from colab_monitor.poller import ApiPoller
from colab_monitor.usage_log import UsageLog


class TestParseArgs:
    def test_defaults(self):
        args = server._parse_args([])
        assert args.host == "127.0.0.1"
        assert args.port == server.DEFAULT_PORT
        assert args.interval == 60.0
        assert args.auth == "oauth2"
        assert args.log_dir == [os.path.expanduser("~/colab-runs")]
        assert not args.no_api

    def test_interval_below_floor_is_rejected(self):
        with pytest.raises(SystemExit):
            server._parse_args(["--interval", "5"])

    def test_repeatable_log_options(self):
        args = server._parse_args(["--log", "a.log", "--log", "b.log", "--log-dir", "~/x", "--log-dir", "/y"])
        assert args.log == ["a.log", "b.log"]
        assert args.log_dir == [os.path.expanduser("~/x"), "/y"]

    def test_bad_auth_is_rejected(self):
        with pytest.raises(SystemExit):
            server._parse_args(["--auth", "password"])


class TestColabAdapter:
    def _client(self):
        def enum(name):
            return SimpleNamespace(name=name)

        assignment = SimpleNamespace(
            endpoint="gpu-t4-abc",
            accelerator=enum("T4"),
            variant=enum("GPU"),
            machine_shape=enum("STANDARD"),
            runtime_proxy_info=SimpleNamespace(token="SECRET-TOKEN", url="https://proxy/secret"),
        )
        info = SimpleNamespace(
            paid_compute_units_balance=12.5, consumption_rate_hourly=1.76, assignments_count=1
        )
        return SimpleNamespace(get_consumption_user_info=lambda: info, list_assignments=lambda: [assignment])

    def test_usage_fields(self):
        usage, _ = server._colab_fetchers(self._client())
        assert usage() == {"balance": 12.5, "rate_per_hour": 1.76, "assignments_count": 1}

    def test_assignments_drop_the_vm_token(self):
        _, assignments = server._colab_fetchers(self._client())
        result = assignments()
        assert result == [
            {"endpoint": "gpu-t4-abc", "accelerator": "T4", "variant": "GPU", "machine_shape": "STANDARD"}
        ]
        assert "SECRET" not in json.dumps(result)


class TestSmallHelpers:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(None, 7), ("abc", 7), ("3", 3), ("-5", 1), ("99999", 10)],
    )
    def test_clamp_int(self, value, expected):
        assert server._clamp_int(value, 7, 1, 10) == expected

    @pytest.mark.parametrize(
        ("host", "expected"),
        [
            ("127.0.0.1", True),
            ("::1", True),
            ("localhost", True),
            ("0.0.0.0", False),
            ("192.168.1.4", False),
            ("evil.example", False),
        ],
    )
    def test_is_loopback(self, host, expected):
        assert server._is_loopback(host) is expected


@pytest.fixture
def app(tmp_path):
    history = tmp_path / "history"
    history.mkdir()
    runs = tmp_path / "runs"
    runs.mkdir()
    poller = ApiPoller(lambda: {"balance": 1.0, "rate_per_hour": 0.0}, list, interval=60)
    poller.poll_once()
    return server.Dashboard(
        poller, sessions_path=str(tmp_path / "sessions.json"), history_dir=str(history), log_dirs=[str(runs)]
    )


class TestEndpointLimits:
    def test_chart_points_are_capped(self, app, tmp_path):
        import time

        log = UsageLog(str(tmp_path / "usage.jsonl"))
        now = time.time()
        for i in range(2000):
            log.append({"balance": 100 - i * 0.01, "rate_per_hour": 1.0}, now=now - 3600 + i)
        app.usage_log = log
        _, body = app.handle("/api/usage", {"range": "1h"})
        assert len(body["points"]) <= server.MAX_CHART_POINTS
        assert body["points"][-1]["balance"] == pytest.approx(100 - 1999 * 0.01)

    def test_log_lines_param_is_clamped(self, app, tmp_path):
        path = tmp_path / "runs" / "big.log"
        path.write_text("".join(f"{i}\n" for i in range(10)))
        _, body = app.handle("/api/log", {"path": str(path), "lines": "0"})
        assert body["lines"] == ["9"]
        _, body = app.handle("/api/log", {"path": str(path), "lines": "nonsense"})
        assert len(body["lines"]) == 10

    def test_log_without_path_is_400(self, app):
        status, _ = app.handle("/api/log", {})
        assert status == 400

    def test_history_limit_is_clamped(self, app, tmp_path):
        with open(tmp_path / "history" / "job.jsonl", "w") as f:
            f.writelines(json.dumps({"timestamp": f"t{i}", "event_type": "ls"}) + "\n" for i in range(700))
        _, body = app.handle("/api/history", {"session": "job", "limit": "100000"})
        assert len(body["events"]) == 500

    def test_no_api_state(self, tmp_path):
        app = server.Dashboard(None, sessions_path=str(tmp_path / "s.json"), history_dir=str(tmp_path))
        _, body = app.handle("/api/state", {})
        assert body["api"]["enabled"] is False
        assert body["config"]["api_enabled"] is False
        assert body["config"]["interval"] is None


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
        assert sources.history_endpoints(str(tmp_path))["e1"]["ended"] is False
        with open(path, "a") as f:
            f.write(json.dumps({"timestamp": "t1", "event_type": "session_terminated"}) + "\n")
        assert sources.history_endpoints(str(tmp_path))["e1"]["ended"] is True

    def test_strip_ansi_handles_cursor_and_title_codes(self):
        assert sources.strip_ansi("\x1b[2K\x1b[1Gdone\x1b]0;title\x07!") == "done!"


class TestMainErrors:
    def test_version_flag(self, capsys):
        with pytest.raises(SystemExit) as exit_info:
            server._parse_args(["--version"])
        assert exit_info.value.code == 0
        assert server.__version__ in capsys.readouterr().out

    def test_port_in_use_is_a_clear_error(self, tmp_path, capsys):
        import socket

        busy = socket.socket()
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]
        try:
            code = server.main(["--no-api", "--port", str(port), "--usage-log", str(tmp_path / "u.jsonl")])
        finally:
            busy.close()
        err = capsys.readouterr().err
        assert code == 1
        assert f"Port {port} is used by another program" in err and "--port" in err
        assert "Traceback" not in err

    def test_sign_in_failure_is_a_clear_error(self, tmp_path, capsys, monkeypatch):
        import colab_cli.auth

        def broken(*args, **kwargs):
            raise RuntimeError("invalid_grant: token expired")

        monkeypatch.setattr(colab_cli.auth, "get_credentials", broken)
        code = server.main(["--port", "0", "--usage-log", str(tmp_path / "u.jsonl")])
        err = capsys.readouterr().err
        assert code == 1
        assert "Couldn't sign in to Colab" in err and "token expired" in err
        assert "colab sessions" in err and "--no-api" in err


class TestAlreadyRunning:
    def test_reuses_a_running_colab_monitor_instead_of_failing(self, tmp_path, capsys, monkeypatch):
        import threading

        running = server.make_server(server.Dashboard(None, history_dir=str(tmp_path)), "127.0.0.1", 0)
        threading.Thread(target=running.serve_forever, daemon=True).start()
        port = running.server_address[1]
        opened = []
        monkeypatch.setattr(server.webbrowser, "open", opened.append)
        try:
            code = server.main(
                ["--no-api", "--open", "--port", str(port), "--usage-log", str(tmp_path / "u.jsonl")]
            )
        finally:
            running.shutdown()
            running.server_close()
        err = capsys.readouterr().err
        assert code == 0
        assert f"Colab Monitor is already running at http://localhost:{port}/" in err
        assert opened == [f"http://localhost:{port}/"]

    def test_port_used_by_something_else_suggests_the_next_port(self, tmp_path, capsys):
        import socket

        busy = socket.socket()
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]
        try:
            code = server.main(["--no-api", "--port", str(port), "--usage-log", str(tmp_path / "u.jsonl")])
        finally:
            busy.close()
        assert code == 1
        assert f"--port {port + 1}" in capsys.readouterr().err


class TestSeveralConfigs:
    def test_config_is_repeatable(self):
        args = server._parse_args(["--config", "/tmp/a.json", "--config", "~/b.json"])
        assert args.config == ["/tmp/a.json", os.path.expanduser("~/b.json")]

    def test_config_defaults_to_the_cli_state_file(self):
        assert server._parse_args([]).config == [os.path.expanduser("~/.config/colab-cli/sessions.json")]

    def test_state_lists_every_config(self, tmp_path):
        a, b = tmp_path / "a.json", tmp_path / "b.json"
        app = server.Dashboard(None, sessions_path=[str(a), str(b)], history_dir=str(tmp_path))
        _, body = app.handle("/api/state", {})
        assert body["config"]["sessions_paths"] == [str(a), str(b)]
