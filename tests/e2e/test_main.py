from playwright.sync_api import Page, expect


def test_not_found(page: Page) -> None:
    response = page.goto("/nx")

    assert response is not None
    assert response.status == 404
    expect(page.get_by_text("Not Found")).to_be_visible()


def test_can_browse_to_standings_and_team_analysis(page: Page) -> None:
    page.goto("/")

    page.locator(".nav-league").first.click()

    expect(page.locator("#standings-table").get_by_text("Alpha TTC")).to_be_visible()

    page.locator("#standings-table .team-link").first.click()

    expect(page.get_by_role("heading", name="Alpha TTC", level=1)).to_be_visible()
    expect(page.locator(".analysis-summary")).to_be_visible()
