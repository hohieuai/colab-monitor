import json
import threading
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from colab_monitor import server
from colab_monitor.poller import ApiPoller
from colab_monitor.server import Dashboard, make_server
from colab_monitor.usage_log import UsageLog


@pytest.fixture
def dashboard(tmp_path):
    sessions = tmp_path / "sessions.json"
    sessions.write_text(
        json.dumps(
            {
                "job": {
                    "name": "job",
                    "token": "SECRET-TOKEN",
                    "url": "https://proxy.example/secret",
                    "endpoint": "e1",
                    "accelerator": "T4",
                    "running": "run(train.py)",
                }
            }
        )
    )
    history = tmp_path / "history"
    history.mkdir()
    (history / "job.jsonl").write_text(
        json.dumps({"timestamp": "t0", "event_type": "session_created"}) + "\n"
    )
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "train.log").write_text("epoch 1 loss 0.5\n")
    (tmp_path / "secret.log").write_text("private\n")

    poller = ApiPoller(
        fetch_usage=lambda: {"balance": 199.7, "rate_per_hour": 1.8},
        fetch_assignments=lambda: [
            {"endpoint": "e1", "accelerator": "T4"},
            {"endpoint": "e2", "accelerator": "A100"},
        ],
        interval=60,
    )
    poller.poll_once()
    return Dashboard(
        poller=poller,
        sessions_path=str(sessions),
        history_dir=str(history),
        log_files=[],
        log_dirs=[str(runs)],
    ), tmp_path


def test_state_merges_server_and_local(dashboard):
    app, _ = dashboard
    status, body = app.handle("/api/state", {})
    assert status == 200
    by_endpoint = {s["endpoint"]: s for s in body["sessions"]}
    assert by_endpoint["e1"]["status"] == "busy"
    assert by_endpoint["e2"]["status"] == "orphan"
    assert body["api"]["usage"]["balance"] == 199.7
    assert [entry["name"] for entry in body["logs"]] == ["train.log"]
    assert body["history"] == ["job"]
    assert "SECRET-TOKEN" not in json.dumps(body)


def test_log_endpoint_only_serves_configured_logs(dashboard):
    app, tmp_path = dashboard
    status, body = app.handle("/api/log", {"path": str(tmp_path / "runs/train.log")})
    assert status == 200
    assert body["lines"] == ["epoch 1 loss 0.5"]

    status, _ = app.handle("/api/log", {"path": str(tmp_path / "secret.log")})
    assert status == 403


def test_history_endpoint(dashboard):
    app, _ = dashboard
    status, body = app.handle("/api/history", {"session": "job"})
    assert status == 200
    assert body["events"][0]["type"] == "session_created"

    status, _ = app.handle("/api/history", {"session": "../sessions"})
    assert status == 400


def test_unknown_route_is_404(dashboard):
    app, _ = dashboard
    status, _ = app.handle("/api/nope", {})
    assert status == 404


def test_real_http_server_serves_page_and_json(dashboard):
    app, _ = dashboard
    server = make_server(app, "127.0.0.1", 0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as resp:
            assert resp.status == 200
            assert "text/html" in resp.headers["Content-Type"]
            assert b"<title>" in resp.read()
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state") as resp:
            assert json.loads(resp.read())["api"]["usage"]["balance"] == 199.7
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/nope")
        assert err.value.code == 404
    finally:
        server.shutdown()
        server.server_close()


def test_rejects_foreign_host_header_on_loopback(dashboard):
    import http.client

    app, _ = dashboard
    server = make_server(app, "127.0.0.1", 0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port)
        conn.request("GET", "/api/state", headers={"Host": "evil.example:80"})
        assert conn.getresponse().status == 403
        conn.close()
    finally:
        server.shutdown()
        server.server_close()


def test_state_exposes_config(dashboard):
    app, _ = dashboard
    _, body = app.handle("/api/state", {})
    config = body["config"]
    assert config["api_enabled"] is True
    assert config["interval"] == 60
    assert config["log_dirs"] and config["history_dir"]


def test_usage_endpoint_filters_by_range(dashboard, tmp_path):
    import time

    from colab_monitor.usage_log import UsageLog

    app, _ = dashboard
    log = UsageLog(str(tmp_path / "usage.jsonl"))
    now = time.time()
    log.append({"balance": 10.0, "rate_per_hour": 1.0}, now=now - 3 * 86400)
    log.append({"balance": 9.0, "rate_per_hour": 2.0}, now=now - 600)
    app.usage_log = log

    status, body = app.handle("/api/usage", {"range": "24h"})
    assert status == 200
    assert [p["balance"] for p in body["points"]] == [9.0]

    status, body = app.handle("/api/usage", {"range": "7d"})
    assert [p["balance"] for p in body["points"]] == [10.0, 9.0]

    status, _ = app.handle("/api/usage", {"range": "1y"})
    assert status == 400


def test_usage_endpoint_without_log_is_empty(dashboard):
    app, _ = dashboard
    status, body = app.handle("/api/usage", {"range": "24h"})
    assert status == 200
    assert body["points"] == []


def test_activity_endpoint(dashboard):
    app, _ = dashboard
    status, body = app.handle("/api/activity", {"limit": "5"})
    assert status == 200
    assert body["events"][0]["session"] == "job"


def test_serves_icons_and_nothing_else_from_static(dashboard):
    app, _ = dashboard
    server = make_server(app, "127.0.0.1", 0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        for path, ctype in [
            ("/icon.svg", "image/svg+xml"),
            ("/favicon.svg", "image/svg+xml"),
            ("/apple-touch-icon.png", "image/png"),
            ("/app.css", "text/css; charset=utf-8"),
            ("/app.js", "text/javascript; charset=utf-8"),
            ("/theme.js", "text/javascript; charset=utf-8"),
            ("/fonts/Geist-Variable.woff2", "font/woff2"),
            ("/fonts/GeistMono-Variable.woff2", "font/woff2"),
        ]:
            with urllib.request.urlopen(base + path) as resp:
                assert resp.status == 200
                assert resp.headers["Content-Type"] == ctype
                assert resp.read()
        for path in (
            "/static/index.html",
            "/../server.py",
            "/server.py",
            "/fonts/OFL.txt",
            "/fonts/../app.js",
        ):
            with pytest.raises(urllib.error.HTTPError) as err:
                urllib.request.urlopen(base + path)
            assert err.value.code == 404
    finally:
        server.shutdown()
        server.server_close()


def test_state_marks_recently_stopped_machine_as_stopping(dashboard, tmp_path):
    app, _ = dashboard
    (tmp_path / "history" / "gone.jsonl").write_text(
        json.dumps({"timestamp": "t0", "event_type": "session_created", "endpoint": "e2"})
        + "\n"
        + json.dumps({"timestamp": "t1", "event_type": "session_terminated"})
        + "\n"
    )
    _, body = app.handle("/api/state", {})
    by_endpoint = {s["endpoint"]: s for s in body["sessions"]}
    assert by_endpoint["e2"]["status"] == "stopping"
    assert by_endpoint["e2"]["name"] == "gone"


def test_security_headers(dashboard):
    app, _ = dashboard
    server = make_server(app, "127.0.0.1", 0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as resp:
            csp = resp.headers["Content-Security-Policy"]
            assert "default-src 'self'" in csp
            assert (
                "script-src 'self'" in csp and "unsafe-inline" not in csp.split("script-src")[1].split(";")[0]
            )
            assert "frame-ancestors 'none'" in csp
            assert resp.headers["X-Content-Type-Options"] == "nosniff"
            assert resp.headers["Referrer-Policy"] == "no-referrer"
            assert resp.headers["Cache-Control"] == "no-store"
            html = resp.read().decode()
            assert "<script>" not in html  # no inline scripts, so the policy can forbid them
            assert "googleapis" not in html
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/fonts/Geist-Variable.woff2") as resp:
            assert "max-age" in resp.headers["Cache-Control"]
    finally:
        server.shutdown()
        server.server_close()


def test_state_on_a_machine_without_cli_state(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    app = Dashboard(None, history_dir=str(tmp_path / "history"))
    status, body = app.handle("/api/state", {})
    assert status == 200
    assert body["sessions"] == []


class TestInsightsApi:
    def test_state_includes_insights_and_per_session_metrics(self, dashboard):
        app, _ = dashboard
        _, body = app.handle("/api/state", {})
        ins = body["insights"]
        assert ins["schema"] == 1
        assert set(ins) >= {
            "spend",
            "runway",
            "idle_cost",
            "machine_hours_7d",
            "runs",
            "jobs",
            "attention",
            "thresholds",
        }
        assert "machines" not in ins  # merged into each session instead
        by_endpoint = {s["endpoint"]: s for s in body["sessions"]}
        assert set(by_endpoint["e1"]["metrics"]) == {
            "uptime_s",
            "idle_s",
            "rate",
            "rate_estimated",
            "cost",
            "idle_cost",
        }
        assert [a["kind"] for a in ins["attention"]][:1] == ["orphan"]  # e2 is an orphan in the fixture

    def test_thresholds_from_the_query(self, dashboard):
        app, _ = dashboard
        _, body = app.handle("/api/state", {"idle_alert": "90", "stall_alert": "5", "runway_alert": "24"})
        assert body["insights"]["thresholds"] == {
            "idle_minutes": 90.0,
            "stall_minutes": 5.0,
            "runway_hours": 24.0,
        }

    @pytest.mark.parametrize("query", [{"idle_alert": "-1"}, {"stall_alert": "abc"}, {"runway_alert": "0"}])
    def test_invalid_thresholds_are_rejected(self, dashboard, query):
        app, _ = dashboard
        status, body = app.handle("/api/state", query)
        assert status == 400 and "must be a positive number" in body["error"]

    def test_default_thresholds_come_from_the_dashboard(self, tmp_path):
        from colab_monitor.metrics import Thresholds

        app = Dashboard(
            None,
            history_dir=str(tmp_path),
            thresholds=Thresholds(idle_minutes=10, stall_minutes=3, runway_hours=6),
        )
        _, body = app.handle("/api/state", {})
        assert body["insights"]["thresholds"] == {"idle_minutes": 10, "stall_minutes": 3, "runway_hours": 6}


def test_log_api_reads_the_checked_file_and_refuses_bad_paths(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "train.log").write_text("epoch 1\n")
    monkeypatch.setenv("HOME", str(tmp_path))
    app = Dashboard(
        None, sessions_path=str(tmp_path / "none.json"), history_dir=str(tmp_path), log_dirs=[str(runs)]
    )
    assert app.handle("/api/log", {"path": "~/runs/train.log"}) == (
        200,
        {"path": "~/runs/train.log", "lines": ["epoch 1"]},
    )
    assert app.handle("/api/log", {"path": str(runs / "train.log") + "/"})[1]["lines"] == ["epoch 1"]
    assert app.handle("/api/log", {"path": str(runs / "train.log\x00")})[0] == 403


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


@pytest.mark.parametrize("value", ["inf", "-inf", "nan", "0", "-1", "x"])
def test_thresholds_must_be_finite_positive_numbers(dashboard, value):
    app, _ = dashboard
    status, body = app.handle("/api/state", {"idle_alert": value})
    assert status == 400 and "positive number" in body["error"]
