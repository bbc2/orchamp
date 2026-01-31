"""
Data sources for fetching championship state from various formats.
"""

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

from orchamp_get.parser import parse_html
from orchamp_web.config import SourceType

logger = logging.getLogger(__name__)


class DataSource(ABC):
    """
    Abstract base class for fetching championship state from a URL.
    """

    @abstractmethod
    async def fetch_state(self, url: str, http_client: "httpx.AsyncClient") -> dict:
        """
        Fetch and parse championship state from the given URL.

        Returns the championship state as a dictionary suitable for
        `ChampionshipState.from_dict()`.
        """

        ...


class ClassementDataSource(DataSource):
    """
    Data source for HTML pages from the "classement" website.
    """

    async def fetch_state(self, url: str, http_client: "httpx.AsyncClient") -> dict:
        response = await http_client.get(url)
        logger.debug(f"External request to {url} (status: {response.status_code})")
        response.raise_for_status()
        html = response.content.decode("utf-8")
        return parse_html(html)


class JsonDataSource(DataSource):
    """
    Data source for JSON files containing championship state directly.

    The JSON should have the same structure as `ChampionshipState.from_dict()` expects.
    """

    async def fetch_state(self, url: str, http_client: "httpx.AsyncClient") -> dict:
        response = await http_client.get(url)
        logger.debug(f"External request to {url} (status: {response.status_code})")
        response.raise_for_status()
        return response.json()


_DATA_SOURCES: dict[SourceType, type[DataSource]] = {
    SourceType.CLASSEMENT: ClassementDataSource,
    SourceType.JSON: JsonDataSource,
}


def get_data_source(source_type: SourceType) -> DataSource:
    """
    Get a data source instance by type.
    """

    return _DATA_SOURCES[source_type]()
