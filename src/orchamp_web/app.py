"""
FastAPI web application for standings.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from orchamp_web.config import AppConfig
from orchamp_web.logs import configure_logging
from orchamp_web.routes import router

logger = logging.getLogger(__name__)

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
        async with httpx.AsyncClient() as client:
            app.state.http_client = client
            yield

    app = FastAPI(
        title="Orchamp",
        description="Championship standings",
        lifespan=lifespan,
    )
    app.state.config = config
    app.state.templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
    app.mount(
        path="/static",
        app=StaticFiles(directory=Path(__file__).parent / "static"),
        name="static",
    )
    app.include_router(router)
    return app
