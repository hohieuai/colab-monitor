"""One test per dashboard feature, in a real browser."""

import json
import re

import pytest

from .conftest import expect, open_route

pytestmark = pytest.mark.e2e

ROUTES = ["overview", "sessions", "logs", "history", "settings"]


# ---------- Shell ----------


@pytest.mark.parametrize("route", ROUTES)
def test_navigation_shows_only_that_page(page, site, route):
    open_route(page, site, "overview")
    page.click(f'nav a[data-route="{route}"]')
    page.wait_for_selector(f"#page-{route}:not([hidden])")
    for other in ROUTES:
        assert page.is_visible(f"#page-{other}") == (other == route)
    assert page.get_attribute(f'nav a[data-route="{route}"]', "aria-current") == "page"
    assert page.title().lower().startswith(route)


def test_unknown_route_falls_back_to_overview(page, site):
    page.goto(f"{site}/#/nope")
    page.wait_for_selector("#page-overview:not([hidden])")


def test_sidebar_counts_and_connection(page, site):
    open_route(page, site, "overview")
    assert page.inner_text("#nav-sessions") == "5"
    assert "hot" in page.get_attribute("#nav-sessions", "class")  # orphans present
    assert page.inner_text("#nav-logs") == "2"
    assert page.inner_text("#conn-title") == "Connected"
    assert "every 60s" in page.inner_text("#conn-sub")


def test_theme_switch_persists_and_system_resets(page, site):
    open_route(page, site, "overview")
    page.click('.theme-seg [data-theme-choice="dark"]')
    assert page.get_attribute("html", "data-theme") == "dark"
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(0, 0, 0)"
    page.reload()
    page.wait_for_selector("#page-overview:not([hidden])")
    assert page.get_attribute("html", "data-theme") == "dark"
    page.click('.theme-seg [data-theme-choice="system"]')
    assert page.get_attribute("html", "data-theme") is None


def test_settings_theme_cards(page, site):
    open_route(page, site, "settings")
    page.click('.theme-card[data-theme-choice="light"]')
    assert page.get_attribute("html", "data-theme") == "light"
    assert page.get_attribute('.theme-card[data-theme-choice="light"]', "aria-pressed") == "true"


# ---------- Overview ----------


def test_overview_stats(page, site, data):
    open_route(page, site, "overview", "#s-balance:not(:empty)")
    balance = data["usage"].read()[-1]["balance"]
    assert page.inner_text("#s-balance") == f"{balance:,.2f}"
    assert page.inner_text("#s-rate").startswith("1.76")
    hours = balance / 1.76
    expected = f"{hours / 24:.1f}" if hours >= 48 else f"{hours:.1f}"
    assert page.inner_text("#s-runway").startswith(expected)
    assert page.inner_text("#s-machines") == "5"
    assert "1 running" in page.inner_text("#s-machines-foot") and "2 orphan" in page.inner_text(
        "#s-machines-foot"
    )


def test_orphan_banner_counts_orphans_not_stopping(page, site):
    open_route(page, site, "overview")
    assert page.is_visible("#orphan-alert")
    assert page.inner_text("#orphan-title").startswith("2 orphaned machines")


def test_active_machines_and_recent_activity(page, site):
    open_route(page, site, "overview", "#ov-activity li .title")
    machines = page.inner_text("#ov-sessions")
    for expected in ("train-gpu", "eval-cpu", "Running", "Idle", "Stopping", "Orphan"):
        assert expected in machines
    activity = page.inner_text("#ov-activity")
    assert "Session ended" in activity and "old-job" in activity
    assert "ValueError: bad split" in activity


def test_range_buttons_fetch_that_range(page, site):
    open_route(page, site, "overview", "#chart .chart-line")
    for rng in ("1h", "7d", "30d", "24h"):
        with page.expect_request(lambda r, rng=rng: f"/api/usage?range={rng}" in r.url):
            page.click(f'#range-seg [data-range="{rng}"]')
        assert page.get_attribute(f'#range-seg [data-range="{rng}"]', "aria-pressed") == "true"


def test_measure_toggle_and_step_drawing(page, site):
    open_route(page, site, "overview", "#chart .chart-line")
    rate_path = page.get_attribute("#chart .chart-line", "d")
    assert "H" in rate_path and "V" in rate_path  # usage rate is a step line
    page.click('#measure-seg [data-measure="balance"]')
    assert "balance" in page.get_attribute("#chart", "aria-label").lower()
    assert "L" in page.get_attribute("#chart .chart-line", "d")


def test_chart_breaks_line_where_dashboard_was_off(page, site):
    open_route(page, site, "overview", "#chart .chart-line")
    assert page.locator("#chart .chart-line").count() == 2


def test_chart_tooltip(page, site):
    open_route(page, site, "overview", "#chart .chart-hit")
    hit = page.locator("#chart .chart-hit").bounding_box()
    card = page.locator("#chart-wrap").bounding_box()
    for frac in (0.0, 0.02, 0.5, 0.99, 1.0):
        for dy in (2, hit["height"] - 2):
            page.mouse.move(hit["x"] + hit["width"] * frac, hit["y"] + dy)
            assert page.is_visible("#tooltip")
            assert "/ hr" in page.inner_text("#tooltip")
            tip = page.locator("#tooltip").bounding_box()
            assert tip["x"] >= card["x"] and tip["x"] + tip["width"] <= card["x"] + card["width"], (
                frac,
                tip,
                card,
            )
            assert tip["y"] >= card["y"] and tip["y"] + tip["height"] <= card["y"] + card["height"], (
                frac,
                tip,
                card,
            )
    page.mouse.move(5, 5)
    assert not page.is_visible("#tooltip")


def test_chart_table_view(page, site):
    open_route(page, site, "overview", "#chart .chart-line")
    page.click("#table-toggle")
    assert page.is_visible("#chart-table")
    assert page.locator("#chart-table-body tr").count() == 60
    assert page.inner_text("#table-toggle") == "Hide table"
    page.click("#table-toggle")
    assert not page.is_visible("#chart-table")


def test_chart_redraws_on_resize(page, site):
    open_route(page, site, "overview", "#chart .chart-line")
    page.set_viewport_size({"width": 1000, "height": 900})
    page.wait_for_timeout(400)
    assert page.evaluate("document.querySelector('#chart').viewBox.baseVal.width") < 800


# ---------- Sessions ----------


def test_sessions_rows_statuses_and_script_name(page, site):
    open_route(page, site, "sessions", "#sessions-body tr")
    rows = page.locator("#sessions-body tr")
    assert rows.count() == 5
    text = page.inner_text("#sessions-body")
    for expected in ("train-gpu", "eval-cpu", "old-job", "side-run", "Unknown", "Stopping", "Orphan"):
        assert expected in text
    assert "train.py · 5m ago" in text and "/home/me" not in text
    assert "SECRET" not in page.content()


@pytest.mark.parametrize(
    ("status", "count"), [("all", 5), ("busy", 1), ("idle", 1), ("orphan", 2), ("gone", 0)]
)
def test_status_filters(page, site, status, count):
    open_route(page, site, "sessions", "#sessions-body tr")
    page.click(f'#status-seg [data-status="{status}"]')
    assert page.inner_text(f'#status-seg [data-n="{status}"]') == str(count)
    if count:
        assert page.locator("#sessions-body tr").count() == count
    else:
        assert page.is_visible("#sessions-empty") and "No matching" in page.inner_text(
            "#sessions-empty-title"
        )


def test_search_and_slash_shortcut(page, site):
    open_route(page, site, "sessions", "#sessions-body tr")
    page.click("#page-sessions h1")
    page.keyboard.press("/")
    assert page.evaluate("document.activeElement.id") == "session-search"
    page.keyboard.type("t4")
    assert page.locator("#sessions-body tr").count() == 1
    page.fill("#session-search", "named-orphan")
    assert "side-run" in page.inner_text("#sessions-body")
    page.fill("#session-search", "zzz")
    assert page.is_visible("#sessions-empty")
    page.fill("#session-search", "")
    assert page.locator("#sessions-body tr").count() == 5


# ---------- Logs ----------


def _open_log(page, site, name):
    open_route(page, site, "logs", "#log-list button")
    page.locator("#log-list button", has_text=name).click()
    expect(page.locator("#term-file")).to_have_text(re.compile(re.escape(name) + "$"))
    page.wait_for_selector("#log-view .tl")  # switching clears the view, so these lines are the new file's


def test_log_list_and_selection(page, site):
    open_route(page, site, "logs", "#log-list button")
    assert page.locator("#log-list button").count() == 2
    _open_log(page, site, "etl.err")
    assert page.get_attribute('#log-list button[aria-current="true"]', "aria-current") == "true"
    assert "etl starting" in page.inner_text("#log-view")


def test_log_lines_are_clean_and_highlighted(page, site):
    _open_log(page, site, "train.log")
    text = page.inner_text("#log-view")
    assert "\x1b" not in text and "[0;31m" not in text
    assert "ValueError: schema mismatch" in text
    assert "epoch 6/10: 100%|##########" in text and "10%|#" not in text  # progress bar collapsed
    assert page.locator("#log-view .tl.err").count() >= 1
    assert page.locator("#log-view .tl.warn").count() >= 1
    assert page.locator("#log-view .tl").count() == page.locator("#log-view .tl .ln").count()
    assert "1 error line" in page.inner_text("#term-left")


def test_log_filter(page, site):
    _open_log(page, site, "train.log")
    page.fill("#log-filter", "epoch 3")
    assert page.locator("#log-view .tl").count() == 20
    assert page.locator("#log-view mark").count() == 20
    assert "20 shown" in page.inner_text("#term-left")
    page.fill("#log-filter", "nothing-like-this")
    assert "No lines match" in page.inner_text("#log-view")


def test_follow_toggle(page, site):
    _open_log(page, site, "train.log")
    at_bottom = "(() => { const v = document.getElementById('log-view'); return v.scrollTop + v.clientHeight >= v.scrollHeight - 10; })()"
    assert page.evaluate(at_bottom)
    page.click("label.switch")
    assert not page.is_checked("#follow")
    page.evaluate("document.getElementById('log-view').scrollTop = 0")
    page.wait_for_timeout(2500)
    assert page.evaluate("document.getElementById('log-view').scrollTop") < 50
    page.click("label.switch")
    assert page.evaluate(at_bottom)


def test_new_log_lines_appear_live(page, site, data):
    _open_log(page, site, "etl.err")
    with open(data["runs"] / "etl.err", "a") as f:
        f.write("shard 01/40 rows=44,402\n")
    expect(page.locator("#log-view")).to_contain_text("shard 01/40", timeout=8000)


def test_copy_and_download(page, site):
    _open_log(page, site, "train.log")
    page.click("#log-copy")
    page.wait_for_timeout(200)
    assert "Tesla T4" in page.evaluate("navigator.clipboard.readText()")
    with page.expect_download() as download:
        page.click("#log-download")
    assert download.value.suggested_filename == "train.log"


# ---------- History ----------


def test_history_selection_and_timeline(page, site):
    open_route(page, site, "history", "#history-list-pane button")
    names = page.locator("#history-list-pane .pl-title").all_inner_texts()
    assert set(names) == {"train-gpu", "eval-cpu", "old-job", "side-run"}
    page.locator("#history-list-pane button", has_text="train-gpu").click()
    page.wait_for_selector("#timeline .tli")
    assert page.locator('#history-list-pane button[aria-current="true"]').inner_text().startswith("train-gpu")
    titles = page.locator("#timeline .tli-title").all_inner_texts()
    assert titles == ["Code executed", "Session created"]  # newest first
    assert "1 image output" in page.inner_text("#timeline")


def test_history_expands_code_and_output(page, site):
    open_route(page, site, "history", "#history-list-pane button")
    page.locator("#history-list-pane button", has_text="train-gpu").click()
    page.wait_for_selector("#timeline details")
    details = page.locator("#timeline details").first
    details.locator("summary").click()
    assert details.evaluate("d => d.open")
    assert "hello gpu" in page.inner_text("#timeline")


def test_history_error_is_clean(page, site):
    open_route(page, site, "history", "#history-list-pane button")
    page.locator("#history-list-pane button", has_text="eval-cpu").click()
    page.wait_for_selector("#timeline .tli-err")
    assert page.inner_text("#timeline .tli-err") == "ValueError: bad split"


def test_history_list_shows_live_status(page, site):
    open_route(page, site, "history", "#history-list-pane button")
    meta = {
        page.locator("#history-list-pane .pl-title").nth(i).inner_text(): page.locator(
            "#history-list-pane .pl-meta"
        )
        .nth(i)
        .inner_text()
        for i in range(page.locator("#history-list-pane button").count())
    }
    assert meta["train-gpu"].startswith("Running")
    assert meta["side-run"].startswith("Orphan")
    assert meta["old-job"].startswith("Stopping")


# ---------- Settings ----------


def test_settings_values(page, site):
    open_route(page, site, "settings", "#set-api .v")
    values = page.locator("#set-api .v").all_inner_texts() + page.locator("#set-sources .v").all_inner_texts()
    assert len(values) == 9 and all(v.strip() for v in values)
    assert "Every 60s" in values[0] and "--auth=oauth2" in values[1]
    assert page.inner_text("#set-api-status").strip() == "Connected"
    assert page.inner_text(".app-version-only").startswith("Version")


# ---------- States ----------


def test_colab_failing_shows_notice_and_keeps_data(page, site):
    def failing(route):
        response = route.fetch()
        body = response.json()
        body["api"]["error"] = "ColabRequestError: Too Many Requests"
        body["api"]["next_poll_in"] = 118
        route.fulfill(response=response, body=json.dumps(body))

    page.route("**/api/state", failing)
    for route in ("overview", "sessions"):
        open_route(page, site, route)
        notice = page.locator(f"#page-{route} .api-notice")
        notice.wait_for(state="visible")
        assert "Can't reach Colab" in notice.inner_text() and "Retrying in 118s" in notice.inner_text()
    assert page.inner_text("#conn-title") == "Colab unreachable"
    open_route(page, site, "overview")
    assert page.inner_text("#s-balance") not in ("", "\u2013")  # en dash = no value


def test_dashboard_server_offline(page, site):
    open_route(page, site, "overview")
    page.route("**/api/**", lambda route: route.abort())
    expect(page.locator("#conn-title")).to_have_text("Dashboard offline", timeout=8000)


def test_empty_dashboard(page, empty_site):
    open_route(page, empty_site, "overview")
    assert page.inner_text("#conn-title") == "Local only"
    assert page.is_visible("#chart-empty") and "--no-api" in page.inner_text("#chart-empty-desc")
    icon, box = (
        page.locator("#chart-empty .empty-icon svg").bounding_box(),
        page.locator("#chart-empty .empty-icon").bounding_box(),
    )
    assert box["x"] <= icon["x"] and icon["x"] + icon["width"] <= box["x"] + box["width"]
    assert "No machines running" in page.inner_text("#ov-sessions")
    assert "No activity yet" in page.inner_text("#ov-activity")
    open_route(page, empty_site, "sessions")
    assert page.is_visible("#sessions-snippet")
    open_route(page, empty_site, "logs")
    assert "No log files" in page.inner_text("#log-list")
    open_route(page, empty_site, "history")
    assert "No sessions yet" in page.inner_text("#history-list-pane")


def test_long_names_truncate(page, site):
    def long_names(route):
        response = route.fetch()
        body = response.json()
        body["sessions"][0]["name"] = "experiment-llama3-8b-instruct-lora-rank64-lr3e-4-seed1234-final-v2"
        body["sessions"][0]["running"] = "run(train_with_a_really_long_script_name_for_testing.py)"
        route.fulfill(response=response, body=json.dumps(body))

    page.route("**/api/state", long_names)
    open_route(page, site, "sessions", "#sessions-body tr")
    truncated = page.evaluate(
        "(() => { const d = document.querySelector('#sessions-body td.name > div'); return d.scrollWidth > d.clientWidth; })()"
    )
    fits = page.evaluate(
        "(() => { const w = document.querySelector('#sessions-table'); return w.scrollWidth <= w.clientWidth + 1; })()"
    )
    assert truncated and fits


# ---------- Phone ----------

PHONE = {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True}


def test_phone_navigation_drawer(page_factory, site):
    page = page_factory(**PHONE)
    open_route(page, site, "overview")

    def x():
        return page.locator("#sidebar").bounding_box()["x"]

    assert x() < -100
    page.click("#menu-btn")
    page.wait_for_timeout(350)
    assert abs(x()) < 2
    page.mouse.click(370, 400)
    page.wait_for_timeout(350)
    assert x() < -100
    page.click("#menu-btn")
    page.wait_for_timeout(350)
    page.click('nav a[data-route="logs"]')
    page.wait_for_timeout(350)
    assert x() < -100 and page.is_visible("#page-logs")


def test_phone_sessions_are_cards(page_factory, site):
    page = page_factory(**PHONE)
    open_route(page, site, "sessions", "#sessions-body tr")
    assert (
        page.evaluate("getComputedStyle(document.querySelector('#sessions-table thead')).display") == "none"
    )
    assert page.evaluate("getComputedStyle(document.querySelector('#sessions-body tr')).display") == "grid"
    assert page.evaluate(
        "(() => { const w = document.querySelector('#sessions-table'); return w.scrollWidth <= w.clientWidth + 1; })()"
    )


def test_phone_log_scrolls_inside_its_box(page_factory, site):
    page = page_factory(**PHONE)
    open_route(page, site, "logs", "#log-view .tl")
    assert page.evaluate("document.documentElement.scrollHeight") < 1600


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [390, 768, 1440])
def test_no_sideways_overflow(page_factory, site, scheme, width):
    page = page_factory(viewport={"width": width, "height": 900}, color_scheme=scheme)
    for route in ROUTES:
        open_route(page, site, route)
        page.wait_for_timeout(300)
        assert page.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"
        ), (route, width, scheme)


def test_monospace_text_has_no_ligatures(page, site):
    # Geist Mono turns "==" and "###" into ligatures, which misprints code and progress bars.
    def features(selector):
        return page.evaluate(f"getComputedStyle(document.querySelector('{selector}')).fontFeatureSettings")

    _open_log(page, site, "train.log")
    assert '"calt" 0' in features("#log-view .tl"), features("#log-view .tl")
    open_route(page, site, "sessions", "#sessions-body tr")
    for selector in ("#page-sessions .tag", "#page-sessions td.name .ep"):
        assert '"calt" 0' in features(selector), selector
    open_route(page, site, "history", "#history-list-pane button")
    page.locator("#history-list-pane button", has_text="train-gpu").click()
    page.wait_for_selector("#timeline details")
    assert '"calt" 0' in features("#timeline details pre")


def _at_bottom(page):
    return page.evaluate(
        "(() => { const v = document.getElementById('log-view');"
        " return v.scrollTop + v.clientHeight >= v.scrollHeight - 10; })()"
    )


def test_follow_stays_pinned_as_lines_arrive(page, site, data):
    _open_log(page, site, "train.log")
    page.wait_for_timeout(1500)  # let fonts settle; taller lines must not unpin the view
    with open(data["runs"] / "train.log", "a") as f:
        f.writelines(f"[epoch 7] step {i}/100 loss 0.01\n" for i in range(30))
    expect(page.locator("#log-view")).to_contain_text("[epoch 7] step 29/100", timeout=8000)
    page.wait_for_timeout(200)
    assert page.is_checked("#follow")
    assert _at_bottom(page)


def test_scrolling_up_turns_follow_off(page, site):
    _open_log(page, site, "train.log")
    page.hover("#log-view")
    page.mouse.wheel(0, -2000)
    page.wait_for_timeout(300)
    assert not page.is_checked("#follow")
    page.click("label.switch")
    assert page.is_checked("#follow") and _at_bottom(page)


def test_history_tags_use_friendly_names(page, site):
    open_route(page, site, "history", "#history-list-pane button")
    page.locator("#history-list-pane button", has_text="train-gpu").click()
    page.wait_for_selector("#timeline .tli-meta .tag")
    tags = page.locator("#timeline .tli-meta .tag").all_inner_texts()
    assert "T4" in tags and "Standard" in tags
    assert "STANDARD" not in tags and "GPU" not in tags


def test_log_list_order_is_stable(page, site, data):
    open_route(page, site, "logs", "#log-list button")
    before = page.locator("#log-list .pl-title").all_inner_texts()
    assert before == sorted(before, key=str.lower)
    with open(data["runs"] / "train.log", "a") as f:  # newest activity must not move it to the top
        f.write("one more line\n")
    page.wait_for_timeout(3500)
    assert page.locator("#log-list .pl-title").all_inner_texts() == before
