"""
Business logic for fetching pages and computing standings.
"""

import asyncio
import json

import httpx

from orchamp.models import ChampionshipState, Rules
from orchamp.ranking import RankedTeam, compute_rankings
from orchamp_get.parser import parse_html
from orchamp_web.cache import (
    ContentStore,
    RootStore,
    collect_garbage,
    compute_hash,
)
from orchamp_web.config import DEFAULT_RULES, AppConfig, LeagueConfig


class StandingsService:
    """
    Service for fetching and computing standings with caching.
    """

    def __init__(
        self,
        roots: RootStore,
        content: ContentStore,
        config: AppConfig,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._roots = roots
        self._content = content
        self._config = config
        self._http_client = http_client

    async def _fetch_page(self, url: str) -> bytes:
        """
        Fetch page from URL.
        """

        response = await self._http_client.get(url)
        response.raise_for_status()
        return response.content

    async def _get_or_fetch_page(
        self, league_key: str, league: LeagueConfig
    ) -> tuple[str, bytes]:
        """
        Get page from cache or fetch from URL.

        Returns (content_hash, page_bytes).
        """

        root_key = f"page:{league_key}"
        entry = self._roots.get(root_key)

        if entry is not None:
            obj = self._content.get(entry.content_hash)

            if obj is not None:
                return entry.content_hash, obj.value

        page_bytes = await self._fetch_page(league.url)
        page_hash = compute_hash(page_bytes)

        self._content.put(page_hash, page_bytes, refs=[])
        self._roots.set(root_key, page_hash, ttl=self._config.page_ttl_seconds)

        collect_garbage(self._roots, self._content)

        return page_hash, page_bytes

    async def _get_or_parse_state(
        self,
        page_hash: str,
        page_bytes: bytes,
    ) -> tuple[str, dict]:
        """
        Get parsed state from cache or compute from page.

        Returns (state_hash, state_dict).
        """

        state_key = f"state:{page_hash}".encode()
        state_hash = compute_hash(state_key)

        obj = self._content.get(state_hash)

        if obj is not None:
            return state_hash, json.loads(obj.value.decode("utf-8"))

        # CPU-bound: run in thread pool to not block event loop
        state_dict = await asyncio.to_thread(parse_html, page_bytes.decode("utf-8"))
        state_bytes = json.dumps(state_dict).encode("utf-8")

        self._content.put(hash=state_hash, value=state_bytes, refs=[page_hash])

        return state_hash, state_dict

    async def _get_or_compute_rankings(
        self,
        state_hash: str,
        state_dict: dict,
    ) -> list[RankedTeam]:
        """
        Get rankings from cache or compute from state.

        Returns list of RankedTeam.
        """

        rankings_key = f"rankings:{state_hash}".encode()
        rankings_hash = compute_hash(rankings_key)

        obj = self._content.get(rankings_hash)
        if obj is not None:
            data = json.loads(obj.value.decode("utf-8"))
            return [
                RankedTeam(
                    position=r["position"],
                    team_id=r["team_id"],
                    team_name=r["team_name"],
                    points=r["points"],
                )
                for r in data
            ]

        state = ChampionshipState.from_dict(state_dict)
        rules = Rules.from_dict(DEFAULT_RULES)
        # CPU-bound: run in thread pool to not block event loop
        rankings = await asyncio.to_thread(compute_rankings, state, rules)

        rankings_data = [
            {
                "position": r.position,
                "team_id": r.team_id,
                "team_name": r.team_name,
                "points": r.points,
            }
            for r in rankings
        ]
        rankings_bytes = json.dumps(rankings_data).encode("utf-8")

        self._content.put(rankings_hash, rankings_bytes, refs=[state_hash])

        return rankings

    async def get_standings(self, league_key: str) -> list[RankedTeam]:
        """
        Get standings for a league.

        Fetches page, parses state, and computes rankings with caching at each step.
        """

        league = self._config.leagues.get(league_key)
        if league is None:
            raise ValueError(f"Unknown league: {league_key}")

        page_hash, page_bytes = await self._get_or_fetch_page(league_key, league)
        state_hash, state_dict = await self._get_or_parse_state(page_hash, page_bytes)
        rankings = await self._get_or_compute_rankings(state_hash, state_dict)

        return rankings

    def get_league_info(self, league_key: str) -> LeagueConfig:
        """
        Get league configuration.
        """

        league = self._config.leagues.get(league_key)
        if league is None:
            raise ValueError(f"Unknown league: {league_key}")
        return league
