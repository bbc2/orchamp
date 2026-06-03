import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlencode

from anyio import to_thread
from argon2 import PasswordHasher, extract_parameters
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Request, Response
from fastapi.responses import RedirectResponse

LOGIN_PATH = "/login"

# Key under which the "signed in" flag lives in the session.
SESSION_AUTH_KEY = "authenticated"

# How long a session stays valid without re-authenticating.
SESSION_MAX_AGE_SECONDS = 30 * 24 * 3600  # 30 days


class AuthError(Exception):
    """Base class for login failures that aren't a simple wrong password."""


class LoginRateLimited(AuthError):
    """Raised when a client has exceeded the failed-attempt throttle."""


class AuthRequired(Exception):
    """
    Raised by :func:`require_auth` when a request lacks a valid session.

    Carries the path the visitor was trying to reach so the login flow can send
    them back there afterwards. Handled by :func:`auth_exception_handler`.
    """

    def __init__(self, next_path: str) -> None:
        self.next_path = next_path


class LoginThrottle:
    """
    Sliding-window throttle keyed by client IP, counting failed attempts.

    In-memory and per-process. ``now`` is injectable so tests can advance time
    without sleeping.
    """

    def __init__(
        self,
        max_failures: int,
        window_seconds: float,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_failures
        self._window = window_seconds
        self._now = now
        self._failures: dict[str, list[float]] = {}

    def _recent(self, ip: str, now: float) -> list[float]:
        return [t for t in self._failures.get(ip, []) if now - t < self._window]

    def is_blocked(self, ip: str) -> bool:
        return len(self._recent(ip, self._now())) >= self._max

    def record_failure(self, ip: str) -> None:
        now = self._now()
        # Opportunistically drop fully-expired entries to bound memory growth.
        if len(self._failures) > 4096:
            self._failures = {
                k: fresh
                for k, v in self._failures.items()
                if (fresh := [t for t in v if now - t < self._window])
            }
        recent = self._recent(ip, now)
        recent.append(now)
        self._failures[ip] = recent

    def reset(self, ip: str) -> None:
        self._failures.pop(ip, None)


def make_password_hasher() -> PasswordHasher:
    """
    The Argon2 hasher used both to verify logins and to generate hashes
    (`orchamp-hash-password`), so the parameters stay in sync.
    """

    return PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=1)


@dataclass
class Authenticator:
    """
    Verifies the shared beta password and guards the (expensive) check.
    """

    # Stored Argon2 hash, or `None` when auth is disabled (dev). Produced by
    # `orchamp-hash-password`; the plaintext never reaches the running app.
    password_hash: str | None

    hasher: PasswordHasher
    throttle: LoginThrottle

    @classmethod
    def from_env(cls) -> "Authenticator":
        """
        Build an authenticator from environment configuration.

        Authentication is mandatory unless explicitly turned off with
        ``ORCHAMP_AUTH_DISABLED=true``. Otherwise a missing or empty
        ``ORCHAMP_BETA_PASSWORD_HASH`` — or a malformed one — raises, so a bad
        deploy fails at startup instead of silently serving the app without a
        password.
        """

        disabled = os.environ.get("ORCHAMP_AUTH_DISABLED", "").strip().lower() == "true"
        password_hash = os.environ.get("ORCHAMP_BETA_PASSWORD_HASH") or None

        if disabled and password_hash is not None:
            raise ValueError(
                "Both ORCHAMP_AUTH_DISABLED and ORCHAMP_BETA_PASSWORD_HASH are "
                "set; unset one of them to make the intent explicit"
            )

        if not disabled and password_hash is None:
            raise ValueError(
                "ORCHAMP_BETA_PASSWORD_HASH is not set (run `orchamp-hash-password` or"
                " set ORCHAMP_AUTH_DISABLED=true to run without authentication)"
            )

        if password_hash is not None:
            try:
                extract_parameters(password_hash)
            except InvalidHashError as exc:
                raise ValueError(
                    "ORCHAMP_BETA_PASSWORD_HASH is not a valid hash"
                    " (run `orchamp-hash-password`)"
                ) from exc

        return cls(
            password_hash=password_hash,
            hasher=make_password_hasher(),
            throttle=LoginThrottle(max_failures=10, window_seconds=300),
        )

    @property
    def enabled(self) -> bool:
        """
        Whether authentication is enforced.
        """

        return self.password_hash is not None

    def verify(self, candidate: str) -> bool:
        """
        Check a submitted password against the stored hash.

        Returns `True` when the password matches or auth is disabled (so the
        login form still works in development), `False` on a wrong password.
        """

        if not self.enabled:
            return True

        assert self.password_hash is not None

        try:
            self.hasher.verify(self.password_hash, candidate)
            return True
        except VerifyMismatchError:
            return False

    async def authenticate(self, client_ip: str, candidate: str) -> bool:
        """
        Return whether the submitted password is correct.

        Raises :class:`LoginRateLimited` if the client is throttled.
        """

        if not self.enabled:
            return True

        if self.throttle.is_blocked(client_ip):
            raise LoginRateLimited

        ok = await to_thread.run_sync(self.verify, candidate)

        if ok:
            self.throttle.reset(client_ip)
        else:
            self.throttle.record_failure(client_ip)

        return ok


def session_secret_key() -> str:
    """
    Secret key used by `SessionMiddleware` to sign the session cookie.
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


def client_ip(request: Request) -> str:
    """
    Return the client IP for throttling (best-effort) or "unknown".
    """

    # Behind Fly's proxy the real client IP is in `Fly-Client-IP` (which Fly
    # sets and clients cannot override); `request.client` is the proxy's
    # internal address. Fall back to the socket peer for local/dev runs —
    # there the header is spoofable, which is acceptable since throttling is
    # best-effort.

    fly_ip = request.headers.get("fly-client-ip")

    if fly_ip:
        return fly_ip

    if request.client is not None:
        return request.client.host

    return "unknown"


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

    if not request.app.state.authenticator.enabled:
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
    """

    # For HTMX requests a normal 3xx redirect would be swapped into the target
    # element, so we return `HX-Redirect` instead to trigger a full-page
    # navigation to the login screen.

    next_path = exc.next_path if isinstance(exc, AuthRequired) else "/"
    login_url = LOGIN_PATH

    if next_path and next_path != "/":
        login_url += "?" + urlencode({"next": next_path})

    if request.headers.get("HX-Request") == "true":
        return Response(status_code=401, headers={"HX-Redirect": login_url})

    return RedirectResponse(url=login_url, status_code=303)
