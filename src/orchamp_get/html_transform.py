"""
HTML transformation functions for cleaning and anonymizing league pages.
"""

import re
import string

from bs4 import BeautifulSoup, Comment

_TAGS_TO_REMOVE = [
    {"class_": "champun"},
    {"class_": "email"},
    {"class_": "noprint"},
    {"name": "caption"},
    {"name": "footer"},
    {"name": "header"},
    {"name": "hr"},
    {"name": "link"},
    {"name": "menu"},
    {"name": "nav"},
    {"name": "noscript"},
    {"name": "script"},
    {"name": "span", "class_": "access"},
    {"name": "style"},
    {"name": "tfoot"},
    {"name": "thead", "class_": "access"},
    {"name": "title"},
]

_ATTRS_TO_REMOVE = ["href", "title", "style"]


def _remove_attributes(soup: BeautifulSoup, attrs: list[str]) -> None:
    for attr in attrs:
        for tag in soup.find_all(attrs={attr: True}):
            del tag[attr]


def _remove_tags(soup: BeautifulSoup, selectors: list[dict]) -> None:
    for selector in selectors:
        for elem in soup.find_all(**selector):
            elem.decompose()


def _remove_comments(soup: BeautifulSoup) -> None:
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()


def _strip_soup(soup: BeautifulSoup) -> None:
    _remove_tags(soup=soup, selectors=_TAGS_TO_REMOVE)
    _remove_comments(soup=soup)
    _remove_attributes(soup=soup, attrs=_ATTRS_TO_REMOVE)


def _soup_to_html(soup: BeautifulSoup) -> str:
    html = str(soup)
    return re.sub(r"\n\s*\n", "\n", html)  # Remove excessive blank lines.


class _Anonymizer:
    """l
    Generates anonymized team IDs and names on demand.
    """

    def __init__(self) -> None:
        self.ids: dict[str, str] = {}
        self.names: dict[str, str] = {}

    def _next_letter(self, index: int) -> str:
        if index < 26:
            return string.ascii_uppercase[index]

        return f"Z{index - 25}"

    def get_id(self, original: str) -> str:
        if original not in self.ids:
            letter = self._next_letter(len(self.ids))
            self.ids[original] = f"team_{letter.lower()}"

        return self.ids[original]

    def get_name(self, original: str) -> str:
        if original not in self.names:
            letter = self._next_letter(len(self.names))
            self.names[original] = f"Team {letter}"

        return self.names[original]


def _anonymize_soup(soup: BeautifulSoup) -> None:
    anon = _Anonymizer()

    for cell in soup.find_all("td", class_="club"):
        label = cell.find("label")

        if label:
            for_attr = label.get("for")

            if for_attr and isinstance(for_attr, str):
                label["for"] = anon.get_id(for_attr)

            if label.string:
                label.string = anon.get_name(label.string.strip())

        classes = cell.get("class") or []
        cell["class"] = [  # type: ignore
            anon.get_id(cls)
            if isinstance(cls, str) and cls not in ("club", "v", "d", "n")
            else cls
            for cls in classes
            if isinstance(cls, str)
        ]


def strip_and_anonymize_html(html: str, anonymize: bool) -> str:
    """
    Strip useless elements and anonymize team names in an HTML page.

    More efficient than calling strip_html then anonymize_html separately.
    """

    soup = BeautifulSoup(html, "html.parser")
    _strip_soup(soup)

    if anonymize:
        _anonymize_soup(soup)

    return _soup_to_html(soup)
