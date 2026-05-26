"""
Configuration for leagues and app settings.
"""

import re
import tomllib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class SourceType(Enum):
    """
    Type of data source for fetching championship state.
    """

    CLASSEMENT = "classement"
    JSON = "json"


@dataclass(frozen=True)
class LeagueConfig:
    """
    Configuration for a league.
    """

    source: SourceType
    url: str
    name: str


@dataclass(frozen=True)
class AppConfig:
    """
    Application configuration.
    """

    cache_dir: Path
    page_ttl_seconds: int
    leagues: dict[str, LeagueConfig]

    @classmethod
    def from_file(cls, config_path: Path) -> "AppConfig":
        with config_path.open("rb") as f:
            data = tomllib.load(f)

        leagues = {
            key: LeagueConfig(
                url=value["url"],
                name=value["name"],
                source=SourceType(value["source"]),
            )
            for key, value in data["leagues"].items()
        }

        return cls(
            cache_dir=Path.home() / ".cache" / "orchamp_web",
            page_ttl_seconds=(24 * 3600),
            leagues=leagues,
        )


_KEY_RE = re.compile(r"^(\d{4})-\d{4}-d(\d+)-ph(\d+)$")


def league_short_name(key: str) -> str:
    match = _KEY_RE.match(key)
    if match is None:
        return key
    year, div, phase = match.groups()
    return f"{year}: D{div} P{phase}"


def sorted_nav_leagues(leagues: dict[str, LeagueConfig]) -> list[tuple[str, str]]:
    def sort_key(item: tuple[str, LeagueConfig]) -> tuple[int, int, int]:
        match = _KEY_RE.match(item[0])

        if match is None:
            return (0, 999, 999)

        year, div, phase = (int(x) for x in match.groups())
        return (-year, div, phase)

    return [
        (key, league_short_name(key))
        for key, _ in sorted(leagues.items(), key=sort_key)
    ]


DEFAULT_RULES = {
    "win_points": 3,
    "draw_points": 2,
    "loss_points": 1,
    "forfeit_win_points": 3,
    "forfeit_loss_points": 0,
}
