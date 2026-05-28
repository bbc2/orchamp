"""
Pytest configuration for E2E tests.

Requires the following environment variables to be set:
  E2E_BASE_URL  — base URL of the running app (e.g. http://localhost:18080)
  E2E_PASSWORD  — HTTP Basic Auth password
"""

import os
from collections.abc import Generator

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
def context(
    browser: Browser, e2e_base_url: str, e2e_password: str
) -> Generator[BrowserContext, None, None]:
    ctx = browser.new_context(
        base_url=e2e_base_url,
        http_credentials={"username": "", "password": e2e_password},
    )
    yield ctx
    ctx.close()


@pytest.fixture
def page(context: BrowserContext) -> Generator[Page, None, None]:
    page = context.new_page()
    yield page
    page.close()
