import os
import secrets
from urllib.parse import urlencode

from fastapi import Request, Response
from fastapi.responses import RedirectResponse

LOGIN_PATH = "/login"

# Key under which the "signed in" flag lives in the session.
SESSION_AUTH_KEY = "authenticated"

# How long a session stays valid without re-authenticating.
SESSION_MAX_AGE = 30 * 24 * 3600


class AuthRequired(Exception):
    """
    Raised by :func:`require_auth` when a request lacks a valid session.

    Carries the path the visitor was trying to reach so the login flow can send
    them back there afterwards. Handled by :func:`auth_exception_handler`.
    """

    def __init__(self, next_path: str) -> None:
        self.next_path = next_path


def _configured_password() -> str | None:
    """
    Return the configured beta password, or ``None`` when auth is disabled.
    """

    return os.environ.get("ORCHAMP_BETA_PASSWORD") or None


def auth_enabled() -> bool:
    """
    Whether authentication is enforced (i.e. a password is configured).
    """

    return _configured_password() is not None


def session_secret_key() -> str:
    """
    Secret key used by ``SessionMiddleware`` to sign the session cookie.
    """

    return os.environ["ORCHAMP_SECRET_KEY"]


def https_only() -> bool:
    """
    Whether the session cookie should carry the `Secure` attribute.

    Secure by default: Set `ORCHAMP_HTTPS_ONLY` to `false` to allow sending the
    session cookie over plain HTTP (local development or testing).
    """

    value = os.environ.get("ORCHAMP_HTTPS_ONLY", "true").strip().lower()
    return value == "true"


def verify_password(candidate: str) -> bool:
    """
    Check a submitted password against the configured one in constant time.

    Returns `True` when authentication is disabled, so the login form still
    works in development.
    """

    expected = _configured_password()
    if expected is None:
        return True

    return secrets.compare_digest(candidate.encode(), expected.encode())


def start_session(request: Request) -> None:
    """
    Mark the current session as authenticated (called after a valid login).
    """

    request.session[SESSION_AUTH_KEY] = True


def end_session(request: Request) -> None:
    """
    Clear the session (called on logout).
    """

    request.session.clear()


def is_authenticated(request: Request) -> bool:
    """
    Whether `request` carries a valid session (or auth is disabled).
    """

    if not auth_enabled():
        return True

    return request.session.get(SESSION_AUTH_KEY) is True


def require_auth(request: Request) -> None:
    """
    FastAPI dependency that rejects unauthenticated requests.

    Raises :class:`AuthRequired` (turned into a redirect to the login page by
    :func:`auth_exception_handler`) rather than returning a response, so it can
    be attached as a router-level dependency.
    """

    if is_authenticated(request):
        return

    next_path = request.url.path

    if request.url.query:
        next_path += "?" + request.url.query

    raise AuthRequired(next_path=next_path)


def auth_exception_handler(request: Request, exc: Exception) -> Response:
    """
    Send unauthenticated visitors to the login page, preserving their target.

    For HTMX requests a normal 3xx redirect would be swapped into the target
    element, so we return `HX-Redirect` instead to trigger a full-page
    navigation to the login screen.

    Typed as a generic Starlette exception handler. In practice it only ever
    receives :class:`AuthRequired`.
    """

    next_path = exc.next_path if isinstance(exc, AuthRequired) else "/"

    login_url = LOGIN_PATH

    if next_path and next_path != "/":
        login_url += "?" + urlencode({"next": next_path})

    if request.headers.get("HX-Request") == "true":
        return Response(status_code=401, headers={"HX-Redirect": login_url})

    return RedirectResponse(url=login_url, status_code=303)
