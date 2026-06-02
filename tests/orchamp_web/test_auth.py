import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from orchamp_web.auth import (
    AuthRequired,
    auth_exception_handler,
    end_session,
    require_auth,
    session_secret_key,
    start_session,
)


class TestAuthentication:
    """
    End-to-end test with a dummy app
    """

    @pytest.fixture
    def client(self, monkeypatch: pytest.MonkeyPatch) -> TestClient:
        monkeypatch.setenv("ORCHAMP_BETA_PASSWORD", "secret")
        monkeypatch.setenv("ORCHAMP_SECRET_KEY", "test-signing-key")

        app = FastAPI()
        app.add_exception_handler(AuthRequired, auth_exception_handler)
        app.add_middleware(
            SessionMiddleware,
            secret_key=session_secret_key(),
            session_cookie="orchamp_session",
            https_only=False,
        )

        @app.get("/protected", dependencies=[Depends(require_auth)])
        def protected() -> dict:
            return {"ok": True}

        @app.post("/test-login")
        def test_login(request: Request) -> dict:
            start_session(request)
            return {"ok": True}

        @app.post("/test-logout")
        def test_logout(request: Request) -> dict:
            end_session(request)
            return {"ok": True}

        return TestClient(app, follow_redirects=False)

    def test_protected_redirects_when_anonymous(self, client: TestClient) -> None:
        response = client.get("/protected")
        assert response.status_code == 303
        assert response.headers["location"] == "/login?next=%2Fprotected"

    def test_login_then_access_then_logout(self, client: TestClient) -> None:
        client.post("/test-login")
        assert "orchamp_session" in client.cookies

        assert client.get("/protected").status_code == 200

        client.post("/test-logout")
        assert client.get("/protected").status_code == 303

    def test_session_cookie_is_signed(self, client: TestClient) -> None:
        response = client.post("/test-login")
        cookie = response.headers["set-cookie"]
        assert "orchamp_session=" in cookie
        assert "httponly" in cookie.lower()
        assert "samesite=lax" in cookie.lower()
        # The flag is signed, not stored in plaintext.
        assert "authenticated" not in cookie
