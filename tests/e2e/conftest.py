"""
Pytest configuration for E2E tests.

Requires the following environment variables to be set:
  E2E_BASE_URL  — base URL of the running app (e.g. http://localhost:18080)
  E2E_PASSWORD  — login password (ORCHAMP_BETA_PASSWORD of the running app)
"""

import os
from collections.abc import Callable, Generator
from typing import Any

import pytest
from playwright.sync_api import Browser, BrowserContext, Page


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.exit(
            f"E2E environment variable {name!r} is not set. "
            "Run `just test-e2e-docker` or set it manually before `just test-e2e`.",
            returncode=1,
        )
    assert value  # help type checkers: pytest.exit() is NoReturn
    return value


@pytest.fixture(scope="session")
def e2e_base_url() -> str:
    return _require_env("E2E_BASE_URL")


@pytest.fixture(scope="session")
def e2e_password() -> str:
    return _require_env("E2E_PASSWORD")


@pytest.fixture
def new_context(
    browser: Browser, e2e_base_url: str, e2e_password: str
) -> Generator[Callable[..., BrowserContext], None, None]:
    """
    Factory for browser contexts wired to the app's base URL and a live session.

    Each call yields a fresh, isolated context (separate cookies/localStorage)
    that has already been signed in by POSTing the password to the login form.
    The resulting session cookie is shared with every page opened in the
    context. Starting authenticated lets a test verify behaviour that must work
    without prior client state (e.g. assumptions shared purely via the URL).
    All created contexts are closed at teardown.
    """

    created: list[BrowserContext] = []

    def _make(**kwargs: Any) -> BrowserContext:
        ctx = browser.new_context(base_url=e2e_base_url, **kwargs)
        # context.request shares cookie storage with the context, so logging in
        # here authenticates every page subsequently opened in it.
        response = ctx.request.post(
            f"{e2e_base_url}/login",
            form={"password": e2e_password, "next": "/"},
        )
        assert response.ok, f"E2E login failed: {response.status}"
        created.append(ctx)
        return ctx

    yield _make
    for ctx in created:
        ctx.close()


@pytest.fixture
def context(
    new_context: Callable[..., BrowserContext],
) -> BrowserContext:
    return new_context()


@pytest.fixture
def page(context: BrowserContext) -> Generator[Page, None, None]:
    page = context.new_page()
    yield page
    page.close()
