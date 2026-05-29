"""
Pytest configuration for E2E tests.

Requires the following environment variables to be set:
  E2E_BASE_URL  — base URL of the running app (e.g. http://localhost:18080)
  E2E_PASSWORD  — HTTP Basic Auth password
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
    Factory for browser contexts wired to the app's base URL and Basic Auth.

    Each call yields a fresh, isolated context (separate cookies/localStorage),
    which lets a test verify behaviour that must work without prior client
    state (e.g. assumptions shared purely via the URL). All created contexts
    are closed at teardown.
    """

    created: list[BrowserContext] = []

    def _make(**kwargs: Any) -> BrowserContext:
        ctx = browser.new_context(
            base_url=e2e_base_url,
            http_credentials={"username": "", "password": e2e_password},
            **kwargs,
        )
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
