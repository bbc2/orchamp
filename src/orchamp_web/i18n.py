import gettext
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import Request

SUPPORTED_LOCALES: frozenset[str] = frozenset({"en", "fr"})

_LOCALES_DIR = Path(__file__).parent / "locales"


def load_translations(locale: str) -> gettext.NullTranslations:
    if locale == "en":
        return gettext.NullTranslations()
    return gettext.translation(
        domain="messages",
        localedir=_LOCALES_DIR,
        languages=[locale],
    )


def make_locale_context(
    translations_by_locale: dict[str, gettext.NullTranslations],
) -> Callable[[Request], dict[str, Any]]:
    def locale_context(request: Request) -> dict[str, Any]:
        locale = request.cookies.get("lang", "en")
        if locale not in SUPPORTED_LOCALES:
            locale = "en"
        return {
            "locale": locale,
            "_": translations_by_locale[locale].gettext,
        }

    return locale_context
