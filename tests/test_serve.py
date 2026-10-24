"""The serve command: its options, startup errors, and reuse of a running dashboard."""

import os

import pytest

from colab_monitor import server


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


@pytest.mark.parametrize("value", ["inf", "nan", "0"])
def test_alert_options_must_be_finite_positive_numbers(value, capsys):
    with pytest.raises(SystemExit) as exit_info:
        server._parse_args(["--idle-alert", value])
    assert exit_info.value.code == 2 and "positive number" in capsys.readouterr().err


def test_history_dir_expands_the_home_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    args = server._parse_args(["--history-dir=~/.config/colab-cli/history"])
    assert args.history_dir == str(tmp_path / ".config" / "colab-cli" / "history")
