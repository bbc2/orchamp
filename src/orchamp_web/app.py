"""
FastAPI web application for standings.
"""

import logging
import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import httpx2
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from orchamp_web.auth import (
    SESSION_MAX_AGE,
    AuthRequired,
    auth_enabled,
    auth_exception_handler,
    https_only,
    session_secret_key,
)
from orchamp_web.config import AppConfig, sorted_nav_leagues
from orchamp_web.i18n import SUPPORTED_LOCALES, load_translations, make_locale_context
from orchamp_web.logs import configure_logging
from orchamp_web.routes import auth_router, router

logger = logging.getLogger(__name__)


def make_nav_context(config: AppConfig) -> Callable[[Request], dict[str, Any]]:
    nav_leagues = sorted_nav_leagues(config.leagues)

    def nav_context(request: Request) -> dict[str, Any]:
        current_league_key = request.path_params.get("league_key", None)
        return {
            "nav_leagues": nav_leagues,
            "current_league_key": current_league_key,
            "auth_enabled": auth_enabled(),
        }

    return nav_context


LOG_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}


def _parse_log_level(level_str: str) -> int | None:
    """
    Parse log level string to logging level.

    Returns `None` if the string is not a valid log level.

    Allowed values:

    - "CRITICAL"
    - "ERROR"
    - "WARNING"
    - "INFO"
    - "DEBUG"
    """

    return LOG_LEVELS.get(level_str.upper())


def _load_config() -> AppConfig:
    config_path = os.environ.get("ORCHAMP_CONFIG")

    if config_path is None:
        logger.error("ORCHAMP_CONFIG environment variable is not set")
        exit(1)

    assert (
        config_path is not None
    )  # Remove when https://github.com/astral-sh/ty/issues/690 is fixed.
    return AppConfig.from_file(Path(config_path))


def create() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Can be used with `uvicorn --factory`:

        uvicorn orchamp_web.app:create --factory
    """

    log_level = _parse_log_level(os.environ.get("ORCHAMP_LOG_LEVEL", "INFO"))

    if log_level is None:
        logger.error("Invalid `ORCHAMP_LOG_LEVEL` value")
        exit(1)

    assert (
        log_level is not None
    )  # Remove when https://github.com/astral-sh/ty/issues/690 is fixed.
    configure_logging(log_level=log_level)
    config = _load_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with httpx2.AsyncClient() as client:
            app.state.http_client = client
            yield

    app = FastAPI(
        title="Orchamp",
        description="Championship standings",
        lifespan=lifespan,
    )
    app.state.config = config

    translations_by_locale = {
        locale: load_translations(locale) for locale in SUPPORTED_LOCALES
    }
    app.state.templates = Jinja2Templates(
        directory=Path(__file__).parent / "templates",
        context_processors=[
            make_locale_context(translations_by_locale),
            make_nav_context(config),
        ],
    )

    app.add_exception_handler(AuthRequired, auth_exception_handler)

    # Signed, cookie-backed session that carries the "authenticated" flag.
    # Secure by default; ORCHAMP_HTTPS_ONLY=false relaxes it for HTTP dev/e2e.
    app.add_middleware(
        SessionMiddleware,
        secret_key=session_secret_key(),
        session_cookie="orchamp_session",
        max_age=SESSION_MAX_AGE,
        same_site="lax",
        https_only=https_only(),
    )

    app.mount(
        path="/static",
        app=StaticFiles(directory=Path(__file__).parent / "static"),
        name="static",
    )
    app.include_router(auth_router)
    app.include_router(router)
    return app
