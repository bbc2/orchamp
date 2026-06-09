import anyio
import pytest
from fastapi import Request
from starlette.datastructures import Headers

from orchamp_web.auth import (
    Authenticator,
    LoginThrottle,
    client_ip,
)
from .util import build_app, build_authenticator


def build_request(
    headers: dict[str, str] | None = None,
    client: tuple[str, int] | None = ("1.2.3.4", 1234),
) -> Request:
    scope = {
        "type": "http",
        "headers": Headers(headers or {}).raw,
        "client": client,
    }
    return Request(scope)


class TestLoginFlow:
    """
    End-to-end login behaviour over HTTP.
    """

    def test_protected_redirects_when_anonymous(self) -> None:
        client = build_app(build_authenticator())

        response = client.get("/protected")

        assert response.status_code == 303
        assert response.headers["location"] == "/login?next=%2Fprotected"

    def test_correct_password_redirects_to_next(self) -> None:
        client = build_app(build_authenticator("hunter2"))

        response = client.post("/login", data={"password": "hunter2", "next": "/"})

        assert response.status_code == 303
        assert response.headers["location"] == "/"

    def test_correct_password_grants_access(self) -> None:
        client = build_app(build_authenticator("hunter2"))
        client.post("/login", data={"password": "hunter2"})

        response = client.get("/protected")

        assert response.status_code == 200

    def test_wrong_password_shows_error(self) -> None:
        client = build_app(build_authenticator("hunter2"))

        response = client.post("/login", data={"password": "nope"})

        assert response.status_code == 401
        assert "Incorrect password." in response.text

    def test_wrong_password_does_not_grant_access(self) -> None:
        client = build_app(build_authenticator("hunter2"))
        client.post("/login", data={"password": "nope"})

        response = client.get("/protected")

        assert response.status_code == 303

    def test_logout_redirects_to_login(self) -> None:
        client = build_app(build_authenticator("hunter2"))
        client.post("/login", data={"password": "hunter2"})

        response = client.post("/logout")

        assert response.status_code == 303
        assert response.headers["location"] == "/login"

    def test_logout_ends_session(self) -> None:
        client = build_app(build_authenticator("hunter2"))
        client.post("/login", data={"password": "hunter2"})

        client.post("/logout")

        assert client.get("/protected").status_code == 303

    def test_session_cookie_is_signed(self) -> None:
        client = build_app(build_authenticator("hunter2"))

        response = client.post("/login", data={"password": "hunter2"})

        cookie = response.headers["set-cookie"]
        assert "orchamp_session=" in cookie
        assert "httponly" in cookie.lower()
        assert "samesite=lax" in cookie.lower()
        # The flag is signed, not stored in plaintext.
        assert "authenticated" not in cookie

    def test_disabled_auth_leaves_routes_open(self) -> None:
        client = build_app(build_authenticator(password=None))

        response = client.get("/protected")

        assert response.status_code == 200

    def test_disabled_auth_login_form_still_works(self) -> None:
        # The login form still signs you in during development.
        client = build_app(build_authenticator(password=None))

        response = client.post("/login", data={"password": "anything"})

        assert response.status_code == 303

    def test_safe_next_is_honoured(self) -> None:
        client = build_app(build_authenticator("hunter2"))

        response = client.post(
            "/login", data={"password": "hunter2", "next": "/web/foo/"}
        )

        assert response.headers["location"] == "/web/foo/"

    def test_open_redirect_next_falls_back_home(self) -> None:
        client = build_app(build_authenticator("hunter2"))

        response = client.post(
            "/login", data={"password": "hunter2", "next": "//evil.com"}
        )

        assert response.headers["location"] == "/"

    def test_rate_limited_after_repeated_failures(self) -> None:
        client = build_app(build_authenticator("hunter2", max_failures=3))
        for _ in range(3):
            client.post("/login", data={"password": "nope"})

        response = client.post("/login", data={"password": "nope"})

        assert response.status_code == 429

    def test_rate_limiting_blocks_the_correct_password_too(self) -> None:
        client = build_app(build_authenticator("hunter2", max_failures=3))
        for _ in range(3):
            client.post("/login", data={"password": "nope"})

        response = client.post("/login", data={"password": "hunter2"})

        assert response.status_code == 429


class TestAuthenticatorVerify:
    def test_correct_password(self) -> None:
        authenticator = build_authenticator("hunter2")

        assert authenticator.verify("hunter2") is True

    def test_wrong_password(self) -> None:
        authenticator = build_authenticator("hunter2")

        assert authenticator.verify("wrong") is False


class TestAuthenticatorFromEnv:
    @pytest.fixture(autouse=True)
    def clean_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ORCHAMP_BETA_PASSWORD_HASH", raising=False)
        monkeypatch.delenv("ORCHAMP_AUTH_DISABLED", raising=False)

    def test_valid_hash_is_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        hash = build_authenticator("hunter2").password_hash
        assert hash is not None
        monkeypatch.setenv("ORCHAMP_BETA_PASSWORD_HASH", hash)

        authenticator = Authenticator.from_env()

        assert authenticator.enabled

    def test_malformed_hash_fails_at_startup(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ORCHAMP_BETA_PASSWORD_HASH", "hunter2")

        with pytest.raises(ValueError, match="ORCHAMP_BETA_PASSWORD_HASH"):
            Authenticator.from_env()

    def test_missing_hash_fails_at_startup(self) -> None:
        with pytest.raises(ValueError, match="ORCHAMP_BETA_PASSWORD_HASH is not set"):
            Authenticator.from_env()

    def test_empty_hash_fails_at_startup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ORCHAMP_BETA_PASSWORD_HASH", "")

        with pytest.raises(ValueError, match="ORCHAMP_BETA_PASSWORD_HASH is not set"):
            Authenticator.from_env()

    def test_explicit_disable_turns_auth_off(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ORCHAMP_AUTH_DISABLED", "true")

        authenticator = Authenticator.from_env()

        assert not authenticator.enabled

    def test_disable_requires_exact_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A typo must not disable authentication; without a hash it fails.
        monkeypatch.setenv("ORCHAMP_AUTH_DISABLED", "yes")

        with pytest.raises(ValueError, match="ORCHAMP_BETA_PASSWORD_HASH is not set"):
            Authenticator.from_env()

    def test_disable_conflicts_with_hash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        hash = build_authenticator("hunter2").password_hash
        assert hash is not None
        monkeypatch.setenv("ORCHAMP_BETA_PASSWORD_HASH", hash)
        monkeypatch.setenv("ORCHAMP_AUTH_DISABLED", "true")

        with pytest.raises(ValueError, match="unset one of them"):
            Authenticator.from_env()


class TestAuthenticate:
    def test_success_clears_prior_failures(self) -> None:
        authenticator = build_authenticator("hunter2", max_failures=5)
        for _ in range(4):
            anyio.run(authenticator.authenticate, "ip", "nope")

        # A correct login resets the counter so the client isn't locked out.
        ok = anyio.run(authenticator.authenticate, "ip", "hunter2")

        assert ok is True
        assert not authenticator.throttle.is_blocked("ip")


class TestClientIp:
    def test_prefers_fly_header(self) -> None:
        request = build_request(
            headers={"fly-client-ip": "9.9.9.9"}, client=("10.0.0.1", 1)
        )

        assert client_ip(request) == "9.9.9.9"

    def test_falls_back_to_socket_peer(self) -> None:
        request = build_request(client=("10.0.0.1", 1))

        assert client_ip(request) == "10.0.0.1"

    def test_unknown_when_no_client(self) -> None:
        request = build_request(client=None)

        assert client_ip(request) == "unknown"


class TestLoginThrottle:
    def test_not_blocked_below_max_failures(self) -> None:
        throttle = LoginThrottle(max_failures=3, window_seconds=300)

        for _ in range(2):
            throttle.record_failure("ip")

        assert not throttle.is_blocked("ip")

    def test_blocks_after_max_failures(self) -> None:
        throttle = LoginThrottle(max_failures=3, window_seconds=300)

        for _ in range(3):
            throttle.record_failure("ip")

        assert throttle.is_blocked("ip")

    def test_reset_unblocks(self) -> None:
        throttle = LoginThrottle(max_failures=3, window_seconds=300)
        for _ in range(3):
            throttle.record_failure("ip")

        throttle.reset("ip")

        assert not throttle.is_blocked("ip")

    def test_window_expiry(self) -> None:
        clock = {"now": 1000.0}
        throttle = LoginThrottle(
            max_failures=2, window_seconds=60, now=lambda: clock["now"]
        )
        throttle.record_failure("ip")
        throttle.record_failure("ip")

        assert throttle.is_blocked("ip")

        clock["now"] += 61  # all failures now outside the window

        assert not throttle.is_blocked("ip")

    def test_per_ip_isolation(self) -> None:
        throttle = LoginThrottle(max_failures=1, window_seconds=300)

        throttle.record_failure("attacker")

        assert throttle.is_blocked("attacker")
        assert not throttle.is_blocked("innocent")
