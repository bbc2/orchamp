"""
Business logic for fetching pages and computing standings.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

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

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class Cached(Generic[T]):
    """
    A value with its content-addressed identity.

    This is the output type of all cacheable computations, allowing downstream
    computations to use the hash as part of their input identity.
    """

    hash: str
    value: T


class CacheableComputation(Protocol[T]):
    """
    Protocol for computations that can be cached.

    - Input type: determined by the dataclass fields.
    - Output type: `T` (wrapped in `Cached[T]` by the engine).
    """

    def cache_key(self) -> str:
        """
        Generate the cache key for this computation.

        This should uniquely identify the computation based on its inputs.
        The computation is responsible for hashing its inputs as needed.
        """
        ...

    def refs(self) -> list[str]:
        """
        Return the list of content hashes this computation depends on.
        """

        ...

    async def compute(self) -> T:
        """
        Perform the computation.
        """

        ...

    def serialize(self, value: T) -> bytes:
        """
        Serialize the computed value for storage.
        """

        ...

    def deserialize(self, data: bytes) -> T:
        """
        Deserialize the stored value.
        """

        ...


@dataclass(frozen=True)
class ParseStateComputation:
    """
    Computation for parsing HTML into championship state.
    """

    _page: Cached[bytes]

    def cache_key(self) -> str:
        return f"state:{self._page.hash}"

    def refs(self) -> list[str]:
        return [self._page.hash]

    async def compute(self) -> dict:
        return await asyncio.to_thread(parse_html, self._page.value.decode("utf-8"))

    def serialize(self, value: dict) -> bytes:
        return json.dumps(value).encode("utf-8")

    def deserialize(self, data: bytes) -> dict:
        return json.loads(data.decode("utf-8"))


@dataclass(frozen=True)
class ComputeRankingsComputation:
    """
    Computation for computing rankings from championship state.
    """

    _state: Cached[dict]

    def cache_key(self) -> str:
        return f"rankings:{self._state.hash}"

    def refs(self) -> list[str]:
        return [self._state.hash]

    async def compute(self) -> list[RankedTeam]:
        state = ChampionshipState.from_dict(self._state.value)
        rules = Rules.from_dict(DEFAULT_RULES)
        return await asyncio.to_thread(compute_rankings, state, rules)

    def serialize(self, value: list[RankedTeam]) -> bytes:
        data = [
            {
                "position": r.position,
                "team_id": r.team_id,
                "team_name": r.team_name,
                "points": r.points,
            }
            for r in value
        ]
        return json.dumps(data).encode("utf-8")

    def deserialize(self, data: bytes) -> list[RankedTeam]:
        parsed = json.loads(data.decode("utf-8"))
        return [
            RankedTeam(
                position=r["position"],
                team_id=r["team_id"],
                team_name=r["team_name"],
                points=r["points"],
            )
            for r in parsed
        ]


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

    async def _resolve(self, computation: CacheableComputation[T]) -> Cached[T]:
        """
        Resolve a computation: return cached result, or compute and cache it.
        """

        cache_hash = compute_hash(computation.cache_key().encode())
        obj = self._content.get(cache_hash)

        if obj is not None:
            logger.debug(
                f"Cache hit (type: {type(computation).__name__}, hash: {cache_hash})"
            )
            return Cached(hash=cache_hash, value=computation.deserialize(obj.value))

        # Perform the computation
        start_time = time.perf_counter()
        value = await computation.compute()
        end_time = time.perf_counter()
        duration = end_time - start_time

        serialized = computation.serialize(value)
        self._content.put(hash=cache_hash, value=serialized, refs=computation.refs())
        logger.debug(
            f"Cache miss (type: {type(computation).__name__},"
            f" hash: {cache_hash}, duration: {duration:.4f}s)"
        )
        return Cached(hash=cache_hash, value=value)

    async def _fetch_page(self, url: str) -> bytes:
        response = await self._http_client.get(url)
        logger.debug(f"External request to {url} (status: {response.status_code})")
        response.raise_for_status()  # Issue: We need better error handling.
        return response.content

    async def _get_or_fetch_page(
        self, league_key: str, league: LeagueConfig
    ) -> Cached[bytes]:
        root_key = f"page:{league_key}"
        entry = self._roots.get(root_key)

        if entry is not None:
            obj = self._content.get(entry.content_hash)

            if obj is not None:
                return Cached(hash=entry.content_hash, value=obj.value)

        page_bytes = await self._fetch_page(league.url)
        page_hash = compute_hash(page_bytes)

        self._content.put(page_hash, page_bytes, refs=[])
        self._roots.set(root_key, page_hash, ttl=self._config.page_ttl_seconds)

        collect_garbage(self._roots, self._content)

        return Cached(hash=page_hash, value=page_bytes)

    async def get_standings(self, league_key: str) -> list[RankedTeam]:
        """
        Get standings for a league.
        """

        league = self._config.leagues.get(league_key)

        if league is None:
            raise ValueError(f"Unknown league: {league_key}")

        page = await self._get_or_fetch_page(league_key, league)
        state = await self._resolve(ParseStateComputation(page))
        rankings = await self._resolve(ComputeRankingsComputation(state))

        return rankings.value

    def get_league_info(self, league_key: str) -> LeagueConfig:
        """
        Get league configuration.
        """

        league = self._config.leagues.get(league_key)

        if league is None:
            raise ValueError(f"Unknown league: {league_key}")

        return league
