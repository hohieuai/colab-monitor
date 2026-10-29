"""Machine details, job states, metric charts, commands to copy, and alert settings, in a real browser."""

import re
import time
import urllib.parse

import pytest

from .conftest import expect, open_route

pytestmark = pytest.mark.e2e

PHONE = {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True}


def _drawer(page):
    page.wait_for_selector("#drawer:not([hidden])")
    expect(page.locator("#drawer-title")).not_to_be_empty()
    return page.locator("#drawer")


def _hash(page):
    return urllib.parse.unquote(page.evaluate("location.hash"))


# ---------- Machine details ----------


def test_clicking_a_row_opens_its_details(page, site):
    open_route(page, site, "sessions", "#sessions-body tr")
    page.locator("#sessions-body tr", has_text="train-gpu").locator('td[data-label="Uptime"]').click()
    drawer = _drawer(page)
    assert _hash(page) == "#/sessions?session=gpu-t4-e2e"
    assert page.inner_text("#drawer-title") == "train-gpu"
    assert page.inner_text("#drawer-ep") == "gpu-t4-e2e"
    assert drawer.locator("#drawer-status .status.busy").count() == 1
    facts = dict(
        zip(
            drawer.locator(".d-facts dt").all_inner_texts(),
            drawer.locator(".d-facts dd").all_inner_texts(),
            strict=True,
        )
    )
    assert facts == {
        "Hardware": "T4",
        "Idle": "No, running a job",
        "Job": "run(train.py)",
        "Last run": facts["Last run"],
    }
    assert re.fullmatch(r"train\.py · \d+m ago", facts["Last run"])
    tiles = {t.get_attribute("data-tile"): t for t in drawer.locator(".d-tile").all()}
    assert re.fullmatch(r"1\.41\s*/ hr", tiles["Rate"].locator(".d-tile-value").inner_text())
    assert tiles["Rate"].locator(".d-tile-foot").inner_text() == "Estimated"
    assert re.fullmatch(r"1\.\d\d\s*units", tiles["Cost so far"].locator(".d-tile-value").inner_text())
    assert tiles["Cost so far"].locator(".d-tile-foot").inner_text() == "Estimated"
    assert "≈" not in drawer.inner_text()  # estimates are labelled in words, as everywhere else
    assert re.fullmatch(r"1 h( \d+ min)?", tiles["Uptime"].locator(".d-tile-value").inner_text())
    assert page.is_visible("#page-sessions")  # the page stays underneath


def test_details_show_the_job_its_chart_output_and_history(page, site):
    page.goto(f"{site}/#/sessions?session=gpu-t4-e2e")
    drawer = _drawer(page)
    job = drawer.locator('.d-job[data-job="train-gpu.log"]')
    expect(job.locator(".badge")).to_have_text("Failed")
    assert "bad" in job.locator(".bar").get_attribute("class")
    expect(job.locator(".d-chart svg .chart-line")).to_have_count(1)
    assert "loss" in job.locator(".d-chart svg").get_attribute("aria-label")
    expect(job.locator(".d-term .tl.err")).to_contain_text("schema mismatch in shard 40")
    assert job.locator(".d-term .tl").count() == 12
    history = drawer.locator(".d-history li .title")
    expect(history).to_have_count(2)
    assert history.all_inner_texts() == ["Code executed", "Session created"]  # newest first


def test_details_offer_the_stop_command_with_its_state_file(page, site, data):
    page.goto(f"{site}/#/sessions?session=cpu-e2e")
    drawer = _drawer(page)
    assert drawer.locator(".d-sec h3").first.text_content() == "Stop machine"
    code = drawer.locator(".d-sec .snippet code").inner_text()
    assert code == f"colab --config {data['sessions']} stop -s eval-cpu"
    drawer.locator(".d-sec .snippet .copy").click()
    page.wait_for_timeout(200)
    assert page.evaluate("navigator.clipboard.readText()") == code
    assert (
        "No log file belongs to this machine" in drawer.inner_text() and "eval-cpu.log" in drawer.inner_text()
    )


def test_an_unknown_orphan_offers_its_release_command(page, site):
    page.goto(f"{site}/#/sessions?session=cpu-anon-orphan")
    drawer = _drawer(page)
    assert page.inner_text("#drawer-title") == "Unknown machine"
    assert "unassign('cpu-anon-orphan')" in drawer.locator(".snippet code").inner_text()
    assert "uptime and cost are unknown" in drawer.inner_text()
    assert drawer.locator(".d-sec h3").first.text_content() == "Release machine"


def test_escape_closes_and_returns_focus_to_the_row(page, site):
    open_route(page, site, "sessions", "#sessions-body tr")
    link = page.locator("#sessions-body tr", has_text="eval-cpu").locator(".row-link")
    link.focus()
    page.keyboard.press("Enter")
    _drawer(page)
    assert page.evaluate("document.activeElement.id") == "drawer"  # the dialog, then Tab reaches its controls
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.id") == "drawer-close"
    page.keyboard.press("Escape")
    page.wait_for_selector("#drawer", state="hidden")
    assert _hash(page) == "#/sessions"
    assert page.evaluate("document.activeElement.textContent") == "eval-cpu"


def test_close_button_and_backdrop_close_it(page, site):
    page.goto(f"{site}/#/sessions?session=gpu-t4-e2e")
    _drawer(page)
    page.click("#drawer-close")
    page.wait_for_selector("#drawer", state="hidden")
    page.goto(f"{site}/#/sessions?session=gpu-t4-e2e")
    _drawer(page)
    page.mouse.click(40, 450)  # on the backdrop, left of the drawer
    page.wait_for_selector("#drawer", state="hidden")
    assert not page.evaluate("document.body.classList.contains('drawer-open')")


def test_tab_stays_inside_the_open_details(page, site):
    page.goto(f"{site}/#/sessions?session=gpu-t4-e2e")
    _drawer(page)
    page.wait_for_selector("#drawer .d-history li")
    for _ in range(12):
        page.keyboard.press("Tab")
        assert page.evaluate("document.getElementById('drawer').contains(document.activeElement)")
    for _ in range(4):
        page.keyboard.press("Shift+Tab")
        assert page.evaluate("document.getElementById('drawer').contains(document.activeElement)")


def test_overview_machines_open_details_over_the_overview(page, site):
    open_route(page, site, "overview", "#ov-sessions li")
    page.locator("#ov-sessions li", has_text="side-run").locator(".meta").click()
    _drawer(page)
    assert _hash(page) == "#/overview?session=cpu-named-orphan"
    assert page.is_visible("#page-overview") and page.inner_text("#drawer-title") == "side-run"


def test_a_link_to_a_machine_that_is_gone(page, site):
    page.goto(f"{site}/#/sessions?session=no-such-machine")
    drawer = _drawer(page)
    assert page.inner_text("#drawer-title") == "Machine not found"
    assert "No machine with this endpoint" in drawer.inner_text()


def test_details_keep_their_scroll_and_focus_while_data_refreshes(page_factory, site):
    page = page_factory(viewport={"width": 1440, "height": 600})
    page.goto(f"{site}/#/sessions?session=gpu-t4-e2e")
    _drawer(page)
    page.wait_for_selector("#drawer .d-history li")
    page.locator("#drawer .d-links .link").first.focus()  # scrolls the details to the link
    scroll = page.evaluate("document.getElementById('drawer-body').scrollTop")
    assert scroll > 0
    page.wait_for_timeout(6500)  # two refreshes
    assert page.evaluate("document.getElementById('drawer-body').scrollTop") == scroll
    assert page.evaluate("document.activeElement.textContent") == "Open log"


def test_phone_details_fill_the_screen(page_factory, site):
    page = page_factory(**PHONE)
    open_route(page, site, "sessions", "#sessions-body tr")
    page.locator("#sessions-body tr", has_text="train-gpu").locator("td.st").tap()
    _drawer(page)
    box = page.locator("#drawer").bounding_box()
    assert box["x"] == 0 and box["width"] == 390
    page.wait_for_selector("#drawer .d-chart svg")
    assert page.evaluate(
        "(() => { const b = document.getElementById('drawer-body'); return b.scrollWidth <= b.clientWidth + 1; })()"
    )


@pytest.mark.parametrize("width", [390, 768, 1440])
def test_open_details_never_scroll_sideways(page_factory, site, width):
    page = page_factory(viewport={"width": width, "height": 900})
    page.goto(f"{site}/#/sessions?session=gpu-t4-e2e")
    _drawer(page)
    page.wait_for_selector("#drawer .d-chart svg")
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
    assert page.evaluate(
        "(() => { const b = document.getElementById('drawer-body'); return b.scrollWidth <= b.clientWidth + 1; })()"
    )


# ---------- Jobs, errors and metric charts ----------


def test_jobs_card_shows_state_and_trend(page, site):
    open_route(page, site, "overview", "#ov-jobs li")
    job = page.locator('#ov-jobs li[data-job="train-gpu.log"]')
    assert job.get_attribute("data-state") == "failed"
    expect(job.locator(".badge")).to_have_text("Failed")
    assert "bad" in job.locator(".bar").get_attribute("class")
    expect(job.locator(".spark svg path")).to_have_count(1)
    assert job.locator(".spark").get_attribute("title") == "loss 1 → 0.0198 over 100 readings"
    expect(page.locator('#ov-jobs li[data-job="etl.err"] .badge')).to_have_text("Running")


def test_a_failed_jobs_error_opens_the_log_at_that_line(page, site):
    open_route(page, site, "overview", "#ov-jobs li")
    page.locator('#ov-jobs li[data-job="train-gpu.log"] a.job-err').click()
    page.wait_for_selector("#page-logs:not([hidden])")
    flash = page.locator("#log-view .tl.flash")
    expect(flash).to_contain_text("schema mismatch in shard 40")
    assert not page.is_checked("#follow")
    view, row = page.locator("#log-view").bounding_box(), flash.bounding_box()
    assert view["y"] <= row["y"] and row["y"] + row["height"] <= view["y"] + view["height"]


def test_go_to_error_cycles_through_error_lines(fresh, page):
    site, data = fresh
    with open(data["runs"] / "etl.err", "a") as f:
        f.write("error: shard 1 timed out, retrying\nshard 2 ok\nRuntimeError: gave up\n")
    open_route(page, site, "logs", "#log-list button")
    page.locator("#log-list button", has_text="etl.err").click()
    expect(page.locator("#err-jump")).to_be_visible()
    page.click("#err-jump")
    expect(page.locator("#log-view .tl.flash")).to_contain_text("RuntimeError: gave up")
    expect(page.locator("#err-jump")).to_have_text("Go to error (2 of 2)")
    page.click("#err-jump")
    expect(page.locator("#log-view .tl.flash")).to_contain_text("error: shard 1 timed out")
    page.click("#err-jump")
    expect(page.locator("#log-view .tl.flash")).to_contain_text("RuntimeError: gave up")


def test_log_list_shows_job_state_and_machine(page, site):
    open_route(page, site, "logs", "#log-list button")
    train = page.locator("#log-list button", has_text="train-gpu.log")
    expect(train.locator(".badge")).to_have_text("Failed")
    assert "busy" in train.locator(".pl-dot").get_attribute("class")
    assert re.match(r"60% · on train-gpu · 3\.\d KB", train.locator(".pl-meta").inner_text())
    etl = page.locator("#log-list button", has_text="etl.err")
    assert etl.locator(".badge").count() == 0 and etl.locator(".pl-dot").count() == 0


def test_log_metric_chart_with_hover(page, site):
    open_route(page, site, "logs", "#log-list button")
    page.locator("#log-list button", has_text="train-gpu.log").click()
    expect(page.locator("#log-metrics")).to_be_visible()
    expect(page.locator("#metric-caption")).to_have_text("loss 1 → 0.0198 over 100 readings")
    assert page.is_hidden("#metric-seg")  # one metric needs no chooser
    hit = page.locator("#log-metric-chart .chart-hit").bounding_box()
    page.mouse.move(hit["x"] + hit["width"] - 2, hit["y"] + hit["height"] / 2)
    tip = page.locator("#log-metric-chart .tooltip")
    expect(tip).to_be_visible()
    assert "loss 0.0198" in tip.inner_text() and "step 100 · line 102" in tip.inner_text()
    page.locator("#log-list button", has_text="etl.err").click()
    expect(page.locator("#log-metrics")).to_be_hidden()


def test_metric_chips_switch_and_remember_the_metric(fresh, page):
    site, data = fresh
    (data["runs"] / "fit.log").write_text(
        "".join(f"step {i}/20 loss={1 / i:.3f} acc={i / 20:.2f}\n" for i in range(1, 21))
    )
    open_route(page, site, "logs", "#log-list button")
    page.locator("#log-list button", has_text="fit.log").click()
    expect(page.locator("#metric-seg button")).to_have_text(["loss", "acc"])
    page.click('#metric-seg [data-metric="acc"]')
    expect(page.locator("#metric-caption")).to_have_text("acc 0.05 → 1 over 20 readings")
    page.reload()
    page.wait_for_selector("#log-metrics:not([hidden])")
    expect(page.locator('#metric-seg [aria-pressed="true"]')).to_have_text("acc")


def test_a_finished_job(fresh, page):
    site, data = fresh
    # eval-cpu's machine is idle: the CLI has finished running its job.
    (data["runs"] / "eval-cpu.log").write_text("".join(f"step {i}/4 loss={1 / i}\n" for i in range(1, 5)))
    open_route(page, site, "overview", '#ov-jobs li[data-job="eval-cpu.log"]')
    job = page.locator('#ov-jobs li[data-job="eval-cpu.log"]')
    expect(job.locator(".badge")).to_have_text("Finished")
    assert "ok" in job.locator(".bar").get_attribute("class")


# ---------- Needs attention ----------


def test_attention_items_link_to_details_logs_and_history(page, site):
    open_route(page, site, "overview", "#attention-list li")
    orphan = page.locator('#attention-list li[data-subject="side-run"]')
    orphan.locator(".copy-cmd").click()
    expect(orphan.locator(".copy-cmd")).to_have_text("Copied")
    assert "unassign('cpu-named-orphan')" in page.evaluate("navigator.clipboard.readText()")
    expect(orphan.locator(".copy-cmd")).to_have_text("Copy release command", timeout=4000)
    orphan.get_by_role("link", name="Details").click()
    _drawer(page)
    assert page.inner_text("#drawer-title") == "side-run"
    page.keyboard.press("Escape")

    page.locator('#attention-list li[data-subject="eval-cpu"]').get_by_role(
        "link", name="View history"
    ).click()
    page.wait_for_selector("#page-history:not([hidden])")
    expect(page.locator('#history-list-pane button[aria-current="true"] .pl-title')).to_have_text("eval-cpu")

    open_route(page, site, "overview", "#attention-list li")
    page.locator('#attention-list li[data-subject="train-gpu.log"]').get_by_role(
        "link", name="Show error"
    ).click()
    expect(page.locator("#log-view .tl.flash")).to_contain_text("schema mismatch")


def test_tab_title_and_icon_show_attention(page, site):
    open_route(page, site, "overview", "#attention-list li")
    assert page.title() == "(4) Overview · Colab Monitor"
    expect(page.locator('link[rel="icon"]')).to_have_attribute("href", re.compile(r"^data:image/svg\+xml,"))
    icon = urllib.parse.unquote(page.get_attribute('link[rel="icon"]', "href"))
    assert '<circle cx="52" cy="12" r="12" fill="#e5484d"' in icon  # red: an orphan is critical


def test_focus_stays_on_a_row_link_across_refreshes(page, site):
    open_route(page, site, "sessions", "#sessions-body tr")
    page.locator("#sessions-body tr", has_text="old-job").locator(".row-link").focus()
    page.wait_for_timeout(3500)
    assert page.evaluate("document.activeElement.textContent") == "old-job"


# ---------- Usage chart marks ----------


def test_usage_chart_marks_machine_starts_and_stops(page, site):
    open_route(page, site, "overview", "#chart .chart-line")
    marks = page.locator("#chart .chart-mark")
    expect(marks).to_have_count(5)
    assert page.locator("#chart .chart-mark.start").count() == 4
    assert page.locator("#chart .chart-mark.stop").count() == 1
    titles = page.locator("#chart .chart-mark title").all_text_contents()
    assert any(t.startswith("train-gpu started (T4)") for t in titles)
    assert any(t.startswith("old-job stopped (CPU)") for t in titles)

    page.click('#range-seg [data-range="1h"]')  # spread out, so the hover reaches one mark
    page.wait_for_timeout(500)
    page.locator("#chart-wrap").scroll_into_view_if_needed()
    mark = page.locator("#chart .chart-mark.start").first
    name, hardware = re.match(r"(\S+) started \((\w+)\)", mark.locator("title").text_content()).groups()
    first = mark.locator("line").bounding_box()
    hit = page.locator("#chart .chart-hit").bounding_box()
    page.mouse.move(first["x"], hit["y"] + hit["height"] / 2)
    expect(page.locator("#tooltip .tip-event")).to_have_count(1)
    assert f"{name} started · {hardware}" in page.inner_text("#tooltip .tip-event")


# ---------- Alert settings and notifications ----------


def test_alert_thresholds_change_what_needs_attention(page, site, data):
    open_route(page, site, "settings", "#alert-idle")
    expect(page.locator("#alert-idle")).to_have_value("30")
    assert page.input_value("#alert-stall") == "15" and page.input_value("#alert-runway") == "12"
    page.fill("#alert-idle", "10")
    page.click('#alerts-form button[type="submit"]')
    expect(page.locator('#alerts-form button[type="submit"]')).to_have_text("Saved")
    open_route(page, site, "overview", "#attention-list li")
    idle = page.locator('#attention-list li[data-kind="idle"]')
    expect(idle).to_have_count(1)
    assert "eval-cpu has been idle" in idle.inner_text()
    assert (
        idle.locator(".copy-cmd").get_attribute("title")
        == f"colab --config {data['sessions']} stop -s eval-cpu"
    )
    assert idle.locator(".copy-cmd").inner_text() == "Copy stop command"
    assert page.title().startswith("(5)")

    page.reload()  # kept in this browser
    page.wait_for_selector('#attention-list li[data-kind="idle"]')
    open_route(page, site, "settings", "#alert-idle")
    expect(page.locator("#alert-idle")).to_have_value("10")
    page.click("#alerts-reset")
    expect(page.locator("#alert-idle")).to_have_value("30")
    open_route(page, site, "overview", "#attention-list li")
    expect(page.locator('#attention-list li[data-kind="idle"]')).to_have_count(0)


@pytest.mark.parametrize("value", ["0", "-3", ""])
def test_invalid_thresholds_are_not_saved(page, site, value):
    open_route(page, site, "settings", "#alert-idle")
    expect(page.locator("#alert-idle")).to_have_value("30")
    page.fill("#alert-runway", value)
    page.click('#alerts-form button[type="submit"]')
    expect(page.locator("#alerts-error")).to_have_text("Each value must be a number above 0.")
    assert page.evaluate("document.activeElement.id") == "alert-runway"
    assert page.evaluate("localStorage.getItem('alerts')") is None


FAKE_NOTIFICATIONS = """
window.__notes = [];
class FakeNotification {
  constructor(title, options) { window.__notes.push([title, (options || {}).body || ""]); }
  static requestPermission() {
    FakeNotification.permission = "granted";
    sessionStorage.setItem("fake-permission", "granted");  // a browser remembers the answer
    return Promise.resolve("granted");
  }
}
FakeNotification.permission = sessionStorage.getItem("fake-permission") || "default";
window.Notification = FakeNotification;
"""


def test_notifications_for_new_problems_only(fresh, page):
    site, data = fresh
    page.add_init_script(FAKE_NOTIFICATIONS)
    open_route(page, site, "settings", "#alert-idle")
    assert not page.is_checked("#notify-toggle")
    page.click(".notify-row label.switch")
    expect(page.locator("#notify-toggle")).to_be_checked()
    page.wait_for_timeout(3500)
    assert page.evaluate("window.__notes") == []  # what was already wrong on load is not news
    with open(data["runs"] / "etl.err", "a") as f:
        f.write("Traceback (most recent call last):\nKeyError: 'shard'\n")
    expect(page.locator("#nav-logs")).to_be_visible()
    deadline = time.time() + 10
    while time.time() < deadline and not page.evaluate("window.__notes.length"):
        page.wait_for_timeout(500)
    notes = page.evaluate("window.__notes")
    assert ["etl.err failed", "KeyError: 'shard'"] in notes
    assert any(title == "Colab Monitor" and "etl.err ended with an error" in body for title, body in notes)
    page.reload()  # the choice is remembered
    open_route(page, site, "settings", "#alert-idle")
    expect(page.locator("#notify-toggle")).to_be_checked()


def test_blocked_notifications_explain_how_to_allow_them(page, site):
    page.add_init_script(FAKE_NOTIFICATIONS.replace('|| "default"', '|| "denied"'))
    open_route(page, site, "settings", "#alert-idle")
    page.click(".notify-row label.switch")
    expect(page.locator("#notify-toggle")).not_to_be_checked()
    assert "blocked" in page.inner_text("#notify-help")


# ---------- Layout ----------


@pytest.mark.parametrize("width", [800, 1100, 1280, 1600])
def test_sessions_fit_without_sideways_scrolling(page_factory, site, width):
    page = page_factory(viewport={"width": width, "height": 900})
    open_route(page, site, "sessions", "#sessions-body tr")
    assert page.evaluate(
        "(() => { const w = document.querySelector('#sessions-table'); return w.scrollWidth <= w.clientWidth + 1; })()"
    )
    cards = (
        page.evaluate("getComputedStyle(document.querySelector('#sessions-table thead')).display") == "none"
    )
    assert cards == (width < 1280)


def test_follow_keeps_the_end_in_view_when_the_chart_opens_late(page, site):
    # On a slow machine the chart arrives after the log is pinned and pushes the log's end out of view.
    def slow_metrics(route):
        time.sleep(1.0)
        route.continue_()

    page.route("**/api/metrics?*", slow_metrics)
    open_route(page, site, "logs", "#log-list button")
    page.locator("#log-list button", has_text="train-gpu.log").click()
    expect(page.locator("#log-metrics")).to_be_visible(timeout=8000)
    page.wait_for_timeout(300)
    assert page.is_checked("#follow")
    assert page.evaluate(
        "(() => { const v = document.getElementById('log-view'); return v.scrollTop + v.clientHeight >= v.scrollHeight - 10; })()"
    )
