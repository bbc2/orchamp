import pytest
from fastapi.testclient import TestClient

from orchamp_web.routes import _safe_next, _safe_referer

from .util import build_app, build_authenticator


def build_client() -> TestClient:
    """
    Client with authentication disabled.
    """

    return build_app(build_authenticator(password=None))


class TestSafeNext:
    @pytest.mark.parametrize(
        ("next_path", "expected"),
        [
            ("/web/foo/?a=1", "/web/foo/?a=1"),
            ("https://evil.example.net/", "/"),
            ("//evil.example.net", "/"),
            ("/\\evil.example.net", "/"),
            ("", "/"),
        ],
    )
    def test_safe_next(self, next_path: str, expected: str) -> None:
        assert _safe_next(next_path) == expected


class TestSafeReferer:
    @pytest.mark.parametrize(
        ("referer", "expected"),
        [
            ("https://example.com/web/foo/?lang=fr", "/web/foo/?lang=fr"),
            ("https://evil.example.net/phish", "/phish"),
            ("", "/"),
            ("https://evil.example.net", "/"),
            ("https://[evil", "/"),
        ],
    )
    def test_safe_referer(self, referer: str, expected: str) -> None:
        assert _safe_referer(referer) == expected


class TestSetLang:
    def test_sets_cookie_and_redirects_to_referer_path(self) -> None:
        client = build_client()

        response = client.get(
            "/set-lang?lang=fr",
            headers={"referer": "http://testserver/web/foo/"},
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/web/foo/"
        assert response.cookies["lang"] == "fr"

    def test_cross_site_referer_is_not_followed(self) -> None:
        client = build_client()

        response = client.get(
            "/set-lang?lang=fr",
            headers={"referer": "https://evil.example.net"},
        )

        assert response.headers["location"] == "/"

    def test_missing_referer_redirects_home(self) -> None:
        client = build_client()

        response = client.get("/set-lang?lang=fr")

        assert response.headers["location"] == "/"

    def test_unsupported_lang_falls_back_to_english(self) -> None:
        client = build_client()

        response = client.get("/set-lang?lang=xx")

        assert response.cookies["lang"] == "en"
