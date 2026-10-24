"""Browser tests: a real dashboard server with fixture data, driven by Playwright.

Run with `uv run pytest tests/e2e`. Uses the installed Chrome, or Playwright's own
Chromium if that was installed with `uv run playwright install chromium`; skipped otherwise.
"""

import os
import threading
import time

import pytest

from colab_monitor.server import Dashboard, make_server
from colab_monitor.usage_log import UsageLog

from .fixtures import build_data, sample_dashboard

playwright_api = pytest.importorskip("playwright.sync_api")
expect = playwright_api.expect


def serve(app):
    server = make_server(app, "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


@pytest.fixture(scope="session")
def data(tmp_path_factory):
    return build_data(tmp_path_factory.mktemp("e2e"))


@pytest.fixture(scope="session")
def site(data):
    server, url = serve(sample_dashboard(data))
    yield url
    server.shutdown()


@pytest.fixture(scope="session")
def stalled_site(tmp_path_factory):
    """The running job's log went quiet 20 minutes ago."""
    data = build_data(tmp_path_factory.mktemp("stalled"))
    quiet = time.time() - 20 * 60
    os.utime(data["runs"] / "train-gpu.log", (quiet, quiet))
    server, url = serve(sample_dashboard(data))
    yield url
    server.shutdown()


@pytest.fixture(scope="session")
def adc_site(tmp_path_factory):
    """A dashboard signed in with Application Default Credentials."""
    app = sample_dashboard(build_data(tmp_path_factory.mktemp("adc")))
    app.auth = "adc"
    server, url = serve(app)
    yield url
    server.shutdown()


@pytest.fixture(scope="session")
def empty_site(tmp_path_factory):
    root = tmp_path_factory.mktemp("empty")
    (root / "history").mkdir()
    (root / "runs").mkdir()
    app = Dashboard(
        None,
        sessions_path=str(root / "sessions.json"),
        history_dir=str(root / "history"),
        log_dirs=[str(root / "runs")],
        usage_log=UsageLog(str(root / "usage.jsonl")),
    )
    server, url = serve(app)
    yield url
    server.shutdown()


@pytest.fixture(scope="session")
def browser():
    with playwright_api.sync_playwright() as p:
        b = None
        for launch in (lambda: p.chromium.launch(channel="chrome"), lambda: p.chromium.launch()):
            try:
                b = launch()
                break
            except playwright_api.Error:  # try the next browser
                continue
        if b is None:
            pytest.skip("No Chrome or Playwright Chromium available")
        yield b
        b.close()


def _context(browser, **overrides):
    opts = {
        "viewport": {"width": 1440, "height": 900},
        "color_scheme": "light",
        "permissions": ["clipboard-read", "clipboard-write"],
        "accept_downloads": True,
    }
    opts.update(overrides)
    return browser.new_context(**opts)


@pytest.fixture
def page_factory(browser):
    """Make pages; every page fails the test if it logs a JavaScript error."""
    made = []

    def make(**overrides):
        ctx = _context(browser, **overrides)
        page = ctx.new_page()
        page.js_errors = []
        page.on("pageerror", lambda e: page.js_errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and page.js_errors.append(m.text))
        made.append((ctx, page))
        return page

    yield make
    for ctx, page in made:
        errors = [e for e in page.js_errors if "net::ERR_FAILED" not in e and "Failed to fetch" not in e]
        ctx.close()
        assert not errors, errors


@pytest.fixture
def page(page_factory):
    return page_factory()


def open_route(page, base, route, wait_for=None):
    page.goto(f"{base}/#/{route}")
    page.wait_for_selector(f"#page-{route}:not([hidden])")
    # expect() instead of wait_for_function: the page's CSP forbids the eval that the latter uses.
    expect(page.locator("#conn-title")).not_to_have_text("Connecting…")
    if wait_for:
        page.wait_for_selector(wait_for, state="attached")  # a flat chart line has no height
    return page
