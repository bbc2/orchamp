import pytest
from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials

from orchamp_web.auth import require_basic_auth


def _credentials(password: str) -> HTTPBasicCredentials:
    return HTTPBasicCredentials(username="user", password=password)


class TestRequireBasicAuth:
    def test_no_env_var_no_credentials_passes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ORCHAMP_BETA_PASSWORD", raising=False)

        require_basic_auth(credentials=None)

    def test_no_env_var_with_credentials_passes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ORCHAMP_BETA_PASSWORD", raising=False)

        require_basic_auth(credentials=_credentials("anything"))

    def test_correct_password_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ORCHAMP_BETA_PASSWORD", "secret")

        require_basic_auth(credentials=_credentials("secret"))

    def test_wrong_password_raises_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ORCHAMP_BETA_PASSWORD", "secret")

        with pytest.raises(HTTPException) as exc_info:
            require_basic_auth(credentials=_credentials("wrong"))

        assert exc_info.value.status_code == 401

    def test_missing_credentials_raises_401(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ORCHAMP_BETA_PASSWORD", "secret")

        with pytest.raises(HTTPException) as exc_info:
            require_basic_auth(credentials=None)

        assert exc_info.value.status_code == 401

    def test_missing_credentials_sends_www_authenticate_header(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ORCHAMP_BETA_PASSWORD", "secret")

        with pytest.raises(HTTPException) as exc_info:
            require_basic_auth(credentials=None)

        assert exc_info.value.headers is not None
        assert exc_info.value.headers.get("WWW-Authenticate") == "Basic"

    def test_empty_env_var_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ORCHAMP_BETA_PASSWORD", "")

        require_basic_auth(credentials=None)
