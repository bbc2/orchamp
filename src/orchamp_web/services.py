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

from orchamp.analyzer import Analyzer
from orchamp.models import ChampionshipState, Rules, Scenario
from orchamp.ranking import RankedTeam, compute_rankings
from orchamp.solvers.cpsat import CpSatSolver
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


@dataclass(frozen=True)
class ScenarioMatch:
    """
    A match result in a scenario for display purposes.
    """

    home_id: str
    home_name: str
    away_id: str
    away_name: str
    result: str  # "home_win", "draw", "away_win"


@dataclass(frozen=True)
class ScenarioStanding:
    """
    A standing in a scenario for display purposes.
    """

    position: int
    team_id: str
    team_name: str
    points: int


@dataclass(frozen=True)
class ScenarioData:
    """
    Full scenario data for display.
    """

    matches: list[ScenarioMatch]
    standings: list[ScenarioStanding]


@dataclass(frozen=True)
class TeamAnalysisResult:
    """
    Full analysis result for a team.
    """

    team_id: str
    team_name: str
    best_position: int
    worst_position: int
    best_scenario: ScenarioData
    worst_scenario: ScenarioData


@dataclass(frozen=True)
class AnalyzeTeamComputation:
    """
    Computation for analyzing a team's possible positions.
    """

    _state: Cached[dict]
    _team_id: str

    def cache_key(self) -> str:
        return f"analysis:v2:{self._state.hash}:{self._team_id}"

    def refs(self) -> list[str]:
        return [self._state.hash]

    def _scenario_to_data(
        self, scenario: Scenario, state: ChampionshipState
    ) -> ScenarioData:
        matches = []
        for match, completed in scenario.match_results.items():
            # Only include remaining matches (the simulated ones)
            if match not in state.completed_matches:
                matches.append(
                    ScenarioMatch(
                        home_id=match.home,
                        home_name=state.team_by_id(match.home).name,
                        away_id=match.away,
                        away_name=state.team_by_id(match.away).name,
                        result=completed.result.value,
                    )
                )

        standings = [
            ScenarioStanding(
                position=s.position,
                team_id=s.team_id,
                team_name=state.team_by_id(s.team_id).name,
                points=s.points,
            )
            for s in scenario.standings
        ]

        return ScenarioData(matches=matches, standings=standings)

    async def compute(self) -> TeamAnalysisResult | None:
        state = ChampionshipState.from_dict(self._state.value)
        rules = Rules.from_dict(DEFAULT_RULES)
        solver = CpSatSolver(random_seed=42, num_workers=1)
        analyzer = Analyzer(solver=solver)
        analysis = await asyncio.to_thread(
            analyzer.analyze_team_position,
            rules,
            state,
            self._team_id,
            False,
        )

        if analysis is None:
            return None

        return TeamAnalysisResult(
            team_id=analysis.team_id,
            team_name=state.team_by_id(analysis.team_id).name,
            best_position=analysis.best_position,
            worst_position=analysis.worst_position,
            best_scenario=self._scenario_to_data(analysis.best_scenario, state),
            worst_scenario=self._scenario_to_data(analysis.worst_scenario, state),
        )

    def serialize(self, value: TeamAnalysisResult | None) -> bytes:
        if value is None:
            return json.dumps(None).encode("utf-8")

        data = {
            "team_id": value.team_id,
            "team_name": value.team_name,
            "best_position": value.best_position,
            "worst_position": value.worst_position,
            "best_scenario": {
                "matches": [
                    {
                        "home_id": m.home_id,
                        "home_name": m.home_name,
                        "away_id": m.away_id,
                        "away_name": m.away_name,
                        "result": m.result,
                    }
                    for m in value.best_scenario.matches
                ],
                "standings": [
                    {
                        "position": s.position,
                        "team_id": s.team_id,
                        "team_name": s.team_name,
                        "points": s.points,
                    }
                    for s in value.best_scenario.standings
                ],
            },
            "worst_scenario": {
                "matches": [
                    {
                        "home_id": m.home_id,
                        "home_name": m.home_name,
                        "away_id": m.away_id,
                        "away_name": m.away_name,
                        "result": m.result,
                    }
                    for m in value.worst_scenario.matches
                ],
                "standings": [
                    {
                        "position": s.position,
                        "team_id": s.team_id,
                        "team_name": s.team_name,
                        "points": s.points,
                    }
                    for s in value.worst_scenario.standings
                ],
            },
        }
        return json.dumps(data).encode("utf-8")

    def _deserialize_scenario(self, data: dict) -> ScenarioData:
        matches = [
            ScenarioMatch(
                home_id=m["home_id"],
                home_name=m["home_name"],
                away_id=m["away_id"],
                away_name=m["away_name"],
                result=m["result"],
            )
            for m in data["matches"]
        ]
        standings = [
            ScenarioStanding(
                position=s["position"],
                team_id=s["team_id"],
                team_name=s["team_name"],
                points=s["points"],
            )
            for s in data["standings"]
        ]
        return ScenarioData(matches=matches, standings=standings)

    def deserialize(self, data: bytes) -> TeamAnalysisResult | None:
        parsed = json.loads(data.decode("utf-8"))
        if parsed is None:
            return None

        return TeamAnalysisResult(
            team_id=parsed["team_id"],
            team_name=parsed["team_name"],
            best_position=parsed["best_position"],
            worst_position=parsed["worst_position"],
            best_scenario=self._deserialize_scenario(parsed["best_scenario"]),
            worst_scenario=self._deserialize_scenario(parsed["worst_scenario"]),
        )


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

    async def get_team_analysis(
        self, league_key: str, team_id: str
    ) -> TeamAnalysisResult | None:
        """
        Get position analysis for a team.
        """

        league = self._config.leagues.get(league_key)

        if league is None:
            raise ValueError(f"Unknown league: {league_key}")

        page = await self._get_or_fetch_page(league_key, league)
        state = await self._resolve(ParseStateComputation(page))
        analysis = await self._resolve(AnalyzeTeamComputation(state, team_id))

        return analysis.value

    async def get_team_name(self, league_key: str, team_id: str) -> str | None:
        """
        Get the name of a team by ID.
        """

        standings = await self.get_standings(league_key)

        for team in standings:
            if team.team_id == team_id:
                return team.team_name

        return None
