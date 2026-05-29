import re

from collections.abc import Callable

from playwright.sync_api import BrowserContext, Page, expect


def _open_first_pending_match(page: Page) -> tuple[str, str]:
    """
    Navigate to the league page and return the (home_id, away_id) of the first
    upcoming match, once its row is rendered.
    """

    page.goto("/")
    page.locator(".nav-league").first.click()

    row = page.locator("tr.match-pending[data-home-id]").first
    expect(row).to_be_visible()

    home_id = row.get_attribute("data-home-id")
    away_id = row.get_attribute("data-away-id")
    assert home_id and away_id
    return home_id, away_id


def _enter_score(page: Page, home_id: str, away_id: str, home: str, away: str) -> None:
    row = page.locator(
        f'tr.match-pending[data-home-id="{home_id}"][data-away-id="{away_id}"]'
    )
    row.locator('input.score-input[data-role="home"]').fill(home)
    row.locator('input.score-input[data-role="away"]').fill(away)


def _expect_assumption_visible(page: Page, home_id: str, away_id: str) -> None:
    row = page.locator(
        f'tr.match-pending[data-home-id="{home_id}"][data-away-id="{away_id}"]'
    )
    expect(row.locator('input.score-input[data-role="home"]')).to_have_value("3")
    expect(row.locator('input.score-input[data-role="away"]')).to_have_value("1")
    expect(
        page.locator(
            f'.assumptions-panel .remove-btn[data-home-id="{home_id}"][data-away-id="{away_id}"]'
        )
    ).to_be_visible()


def test_assumption_entry_and_removal(page: Page) -> None:
    home_id, away_id = _open_first_pending_match(page)

    _enter_score(page, home_id, away_id, "3", "1")

    # The assumption shows up in the panel and is encoded into the URL so the
    # state is shareable.
    remove_btn = page.locator(
        f'.assumptions-panel .remove-btn[data-home-id="{home_id}"][data-away-id="{away_id}"]'
    )
    expect(remove_btn).to_be_visible()
    expect(page).to_have_url(re.compile(r"[?&]a="))

    # The delegated click handler clears the assumption.
    remove_btn.click()

    expect(page.locator(".no-assumptions")).to_be_visible()
    row = page.locator(
        f'tr.match-pending[data-home-id="{home_id}"][data-away-id="{away_id}"]'
    )
    expect(row.locator('input.score-input[data-role="home"]')).to_have_value("")
    expect(row.locator('input.score-input[data-role="away"]')).to_have_value("")
    expect(page).not_to_have_url(re.compile(r"[?&]a="))


def test_assumptions_persist_across_reload_and_url(
    page: Page, new_context: Callable[..., BrowserContext]
) -> None:
    home_id, away_id = _open_first_pending_match(page)

    _enter_score(page, home_id, away_id, "3", "1")
    expect(
        page.locator(
            f'.assumptions-panel .remove-btn[data-home-id="{home_id}"][data-away-id="{away_id}"]'
        )
    ).to_be_visible()
    expect(page).to_have_url(re.compile(r"[?&]a="))
    shared_url = page.url

    # Survives a reload in the same context (restored from `localStorage` or
    # URL).
    page.reload()
    _expect_assumption_visible(page, home_id, away_id)

    # Shareable: a fresh context with no prior `localStorage`` restores the same
    # state purely from the URL.
    fresh_page = new_context().new_page()
    fresh_page.goto(shared_url)
    _expect_assumption_visible(fresh_page, home_id, away_id)
