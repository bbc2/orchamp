"""
Shared helpers for tests.
"""

import time
from collections.abc import Callable
from pathlib import Path

from argon2 import PasswordHasher
from fastapi import Depends, FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

import orchamp_web
from orchamp_web.auth import (
    Authenticator,
    AuthRequired,
    LoginThrottle,
    auth_exception_handler,
    require_auth,
)
from orchamp_web.routes import auth_router, router

TEMPLATES_DIR = Path(orchamp_web.__file__).parent / "templates"


def build_authenticator(
    password: str | None = "secret",
    max_failures: int = 10,
    window_seconds: float = 300,
    now: Callable[[], float] = time.monotonic,
) -> Authenticator:
    """
    Build an :class:`Authenticator` for tests with cheap Argon2 params.

    Pass ``password=None`` for the auth-disabled case. Everything that the
    production code reads from the environment or module globals is a plain
    constructor argument here, so tests never patch anything.
    """

    hasher = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    return Authenticator(
        password_hash=hasher.hash(password) if password is not None else None,
        hasher=hasher,
        throttle=LoginThrottle(max_failures, window_seconds, now=now),
    )


def build_app(authenticator: Authenticator) -> TestClient:
    """
    Build an app wired with the real routes and session handling.

    Lets tests drive whole flows over HTTP (`POST /login`, the session cookie,
    `/set-lang`, the protected route).
    """

    # The login template is rendered with a trivial i18n stub so no compiled
    # catalog or nav/config wiring is needed.

    app = FastAPI()
    app.state.authenticator = authenticator
    app.state.templates = Jinja2Templates(
        directory=TEMPLATES_DIR,
        context_processors=[lambda request: {"_": str, "locale": "en"}],
    )
    app.add_exception_handler(AuthRequired, auth_exception_handler)
    app.add_middleware(
        SessionMiddleware,
        secret_key="test-signing-key",
        session_cookie="orchamp_session",
        https_only=False,
    )
    app.include_router(auth_router)
    app.include_router(router)

    @app.get("/protected", dependencies=[Depends(require_auth)])
    def protected() -> dict:
        return {"ok": True}

    return TestClient(app, follow_redirects=False)
