"""The app shell: command menu, collapsible sidebar, toasts, tooltips, placeholders, and field errors."""

import pytest

from .conftest import expect, open_route

pytestmark = pytest.mark.e2e


def _options(page):
    return page.locator("#cmdk-list [role=option]")


def _sidebar_right(page):
    return page.evaluate("document.getElementById('sidebar').getBoundingClientRect().right")


# ---------- Command menu ----------


def test_command_menu_opens_with_the_shortcut_and_finds_a_machine(page, site):
    open_route(page, site, "logs", "#log-list button")
    page.keyboard.press("Control+k")
    expect(page.locator("#cmdk")).to_be_visible()
    assert page.evaluate("document.activeElement.id") == "cmdk-input"
    page.keyboard.type("eval")
    expect(_options(page).first).to_contain_text("eval-cpu")
    page.keyboard.press("Enter")
    expect(page.locator("#cmdk")).to_be_hidden()
    page.wait_for_selector("#drawer:not([hidden])")
    expect(page.locator("#drawer-title")).to_have_text("eval-cpu")


def test_command_menu_arrow_keys_pick_a_log(page, site):
    open_route(page, site, "overview")
    page.click("#cmdk-open")
    page.keyboard.type("train")
    expect(_options(page).first).to_have_attribute("aria-selected", "true")
    page.keyboard.press("ArrowDown")
    picked = page.locator("#cmdk-list [role=option][aria-selected=true]")
    expect(picked).to_contain_text("train-gpu.log")
    assert page.get_attribute("#cmdk-input", "aria-activedescendant") == picked.get_attribute("id")
    page.keyboard.press("Enter")
    page.wait_for_selector("#page-logs:not([hidden])")
    expect(page.locator('#log-list button[aria-current="true"] .pl-title')).to_have_text("train-gpu.log")


def test_command_menu_goes_to_pages_and_switches_theme(page, site):
    open_route(page, site, "overview")
    page.keyboard.press("Control+k")
    page.keyboard.type("settings")
    page.keyboard.press("Enter")
    page.wait_for_selector("#page-settings:not([hidden])")
    page.keyboard.press("Control+k")
    page.keyboard.type("dark")
    expect(_options(page).first).to_contain_text("Dark theme")
    page.keyboard.press("Enter")
    assert page.get_attribute("html", "data-theme") == "dark"


def test_command_menu_says_when_nothing_matches_and_closes_with_escape(page, site):
    open_route(page, site, "overview")
    page.click("#cmdk-open")
    page.keyboard.type("zzzz")
    expect(_options(page)).to_have_count(0)
    expect(page.locator("#cmdk-empty")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("#cmdk")).to_be_hidden()
    assert page.evaluate("document.activeElement.id") == "cmdk-open"


# ---------- Sidebar ----------


def test_sidebar_collapses_with_the_shortcut_and_stays_collapsed(page, site):
    open_route(page, site, "overview")
    assert _sidebar_right(page) > 200
    page.keyboard.press("Control+b")
    page.wait_for_timeout(350)
    assert _sidebar_right(page) <= 0
    assert page.get_attribute("#menu-btn", "aria-expanded") == "false"
    assert page.locator(".content").bounding_box()["x"] < 40  # the page takes the room
    page.reload()
    page.wait_for_selector("#page-overview:not([hidden])")
    assert _sidebar_right(page) <= 0
    page.click("#menu-btn")
    page.wait_for_timeout(350)
    assert _sidebar_right(page) > 200
    assert page.get_attribute("#menu-btn", "aria-expanded") == "true"


# ---------- Toasts ----------


def test_saving_alert_settings_shows_a_toast_that_goes_away(page, site):
    open_route(page, site, "settings", "#alert-idle")
    page.fill("#alert-idle", "25")
    page.click('#alerts-form button[type="submit"]')
    toast = page.locator("#toaster .toast")
    expect(toast).to_contain_text("Alert settings saved")
    expect(toast).to_have_count(0, timeout=8000)


def test_copying_a_command_shows_what_was_copied(page, site):
    open_route(page, site, "overview", "#attention-list li")
    page.locator('#attention-list li[data-subject="side-run"] .copy-cmd').click()
    toast = page.locator("#toaster .toast")
    expect(toast).to_contain_text("Copied to clipboard")
    assert "unassign('cpu-named-orphan')" in toast.inner_text()


def test_a_blocked_clipboard_says_so(page, site):
    page.add_init_script("navigator.clipboard.writeText = () => Promise.reject(new Error('blocked'))")
    open_route(page, site, "overview", "#attention-list li")
    button = page.locator('#attention-list li[data-subject="side-run"] .copy-cmd')
    button.click()
    expect(page.locator("#toaster .toast")).to_contain_text("Couldn't copy")
    expect(button).to_have_text("Copy release command")


def test_a_job_that_fails_while_the_page_is_open_shows_a_toast(fresh, page):
    site, data = fresh
    open_route(page, site, "sessions", "#sessions-body tr")
    page.wait_for_timeout(3500)  # a refresh after load: what was already wrong is not news
    expect(page.locator("#toaster .toast")).to_have_count(0)
    with open(data["runs"] / "etl.err", "a") as f:
        f.write("Traceback (most recent call last):\nKeyError: 'shard'\n")
    toast = page.locator("#toaster .toast", has_text="etl.err failed")
    expect(toast).to_be_visible(timeout=10000)
    assert "KeyError: 'shard'" in toast.inner_text()
    toast.get_by_role("button", name="Show error").click()
    page.wait_for_selector("#page-logs:not([hidden])")
    expect(page.locator('#log-list button[aria-current="true"] .pl-title')).to_have_text("etl.err")
    page.wait_for_selector("#log-view .tl.flash")


# ---------- Tooltips ----------


def test_icon_buttons_show_a_tooltip_on_hover(page, site):
    open_route(page, site, "logs", "#log-view .tl")
    page.hover("#log-download")
    tip = page.locator("#tip")
    expect(tip).to_be_visible()
    expect(tip).to_have_text("Download the lines shown")
    page.mouse.move(5, 600)
    expect(tip).to_be_hidden()


# ---------- Loading placeholders ----------


def test_placeholders_show_until_the_dashboard_answers(page, site):
    held = []
    page.route("**/api/state*", lambda route: held.append(route))
    page.goto(f"{site}/#/overview")
    expect(page.locator("#s-balance .skeleton")).to_be_visible()
    expect(page.locator("#ov-sessions .skeleton").first).to_be_visible()
    for route in held:
        route.continue_()
    page.unroute("**/api/state*")
    expect(page.locator("#conn-title")).to_have_text("Connected")
    expect(page.locator("#page-overview .skeleton")).to_have_count(0)


# ---------- Field errors ----------


def test_an_invalid_threshold_is_marked_on_its_own_field(page, site):
    open_route(page, site, "settings", "#alert-idle")
    page.fill("#alert-runway", "0")
    page.click('#alerts-form button[type="submit"]')
    expect(page.locator("#alert-runway")).to_have_attribute("aria-invalid", "true")
    assert page.get_attribute("#alert-idle", "aria-invalid") != "true"
    page.fill("#alert-runway", "6")
    assert page.get_attribute("#alert-runway", "aria-invalid") != "true"  # typing clears it
    page.click('#alerts-form button[type="submit"]')
    expect(page.locator('#alerts-form button[type="submit"]')).to_have_text("Saved")
