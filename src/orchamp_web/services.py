"""
Business logic for fetching pages and computing standings.
"""

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

import httpx

from orchamp.analyzer import Analyzer
from orchamp.models import (
    ChampionshipState,
    CompletedMatch,
    Match,
    MatchScore,
    Rules,
    Scenario,
)
from orchamp.ranking import RankedTeam, compute_rankings
from orchamp.solvers.cpsat import CpSatSolver
from orchamp_web.assumptions import AssumptionDisplay, AssumptionEntry
from orchamp_web.cache import (
    ContentStore,
    RootStore,
    collect_garbage,
    compute_hash,
)
from orchamp_web.config import DEFAULT_RULES, AppConfig, LeagueConfig
from orchamp_web.sources import get_data_source

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _hash_assumptions(assumptions: tuple[tuple[str, str, int, int], ...]) -> str:
    data = json.dumps(sorted(assumptions)).encode()
    return hashlib.sha256(data).hexdigest()[:16]


def _augment_state(
    state: ChampionshipState,
    assumptions: tuple[tuple[str, str, int, int], ...],
) -> ChampionshipState:
    """
    Return a new state with assumed results moved from remaining to completed.

    Assumptions that do not match a remaining match are silently ignored.
    """

    remaining_set = set(state.remaining_matches)
    extra_completed: dict[Match, CompletedMatch] = {}
    for home_id, away_id, home_score, away_score in assumptions:
        match = Match(home=home_id, away=away_id)
        if match in remaining_set:
            score = MatchScore(home_score=home_score, away_score=away_score)
            extra_completed[match] = CompletedMatch(result=score.result(), score=score)

    if not extra_completed:
        return state

    return ChampionshipState(
        teams=state.teams,
        completed_matches={**state.completed_matches, **extra_completed},
        remaining_matches=[
            m for m in state.remaining_matches if m not in extra_completed
        ],
        rounds=state.rounds,
    )


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
class RoundMatchDisplay:
    """
    A match within a round, enriched with team names and score info.
    """

    home_id: str
    home_name: str
    away_id: str
    away_name: str
    home_score: int | None
    away_score: int | None
    result: str | None  # "home_win", "draw", "away_win", etc., or None if not played


@dataclass(frozen=True)
class RoundDisplay:
    """
    A round with enriched match data for display.
    """

    name: str  # e.g. "R01"
    date: str | None  # ISO date, e.g. "2025-10-16"
    matches: list[RoundMatchDisplay]


@dataclass(frozen=True)
class ScenarioMatch:
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
    _assumptions: tuple[tuple[str, str, int, int], ...] = ()

    def cache_key(self) -> str:
        return f"analysis:v3:{self._state.hash}:{_hash_assumptions(self._assumptions)}:{self._team_id}"

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
        if self._assumptions:
            state = _augment_state(state, self._assumptions)
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

    async def _get_or_fetch_state(
        self, league_key: str, league: LeagueConfig
    ) -> Cached[dict]:
        """
        Fetch championship state using the appropriate data source.

        Caches the state dict with TTL-based expiration.
        """

        root_key = f"state:v2:{league_key}"
        entry = self._roots.get(root_key)

        if entry is not None:
            obj = self._content.get(entry.content_hash)
            if obj is not None:
                state_dict = json.loads(obj.value.decode("utf-8"))
                return Cached(hash=entry.content_hash, value=state_dict)

        # Fetch fresh state using the configured data source
        source = get_data_source(league.source)
        state_dict = await source.fetch_state(league.url, self._http_client)

        # Cache the state
        serialized = json.dumps(state_dict).encode("utf-8")
        state_hash = compute_hash(serialized)
        self._content.put(state_hash, serialized, refs=[])
        self._roots.set(root_key, state_hash, ttl=self._config.page_ttl_seconds)

        collect_garbage(self._roots, self._content)

        return Cached(hash=state_hash, value=state_dict)

    async def get_standings(self, league_key: str) -> list[RankedTeam]:
        """
        Get standings for a league.
        """

        league = self._config.leagues.get(league_key)

        if league is None:
            raise ValueError(f"Unknown league: {league_key}")

        state = await self._get_or_fetch_state(league_key, league)
        rankings = await self._resolve(ComputeRankingsComputation(state))

        return rankings.value

    async def get_rounds(self, league_key: str) -> list[RoundDisplay]:
        """
        Get rounds with enriched match data for a league.
        """

        league = self._config.leagues.get(league_key)

        if league is None:
            raise ValueError(f"Unknown league: {league_key}")

        cached_state = await self._get_or_fetch_state(league_key, league)
        state = ChampionshipState.from_dict(cached_state.value)

        # Build a lookup from (home, away) -> raw match dict so we can read scores
        # directly from the parsed data (models only store home_score/away_score,
        # but the parser emits home_score/away_score for each round match).
        raw_match_scores: dict[tuple[str, str], tuple[int | None, int | None]] = {}
        for raw_round in cached_state.value.get("rounds", []):
            for m in raw_round["matches"]:
                raw_match_scores[(m["home"], m["away"])] = (
                    m.get("home_score"),
                    m.get("away_score"),
                )

        result = []
        for round_ in state.rounds:
            matches = []
            for match in round_.matches:
                home_team = state.team_by_id(match.home)
                away_team = state.team_by_id(match.away)
                completed = state.completed_matches.get(match)
                home_score, away_score = raw_match_scores.get(
                    (match.home, match.away), (None, None)
                )
                result_str = completed.result.value if completed is not None else None
                matches.append(
                    RoundMatchDisplay(
                        home_id=match.home,
                        home_name=home_team.name,
                        away_id=match.away,
                        away_name=away_team.name,
                        home_score=home_score,
                        away_score=away_score,
                        result=result_str,
                    )
                )
            result.append(
                RoundDisplay(name=round_.name, date=round_.date, matches=matches)
            )

        return result

    def is_state_cached(self, league_key: str) -> bool:
        """
        Return True if the championship state for this league is on disk and not expired.
        """

        entry = self._roots.get(f"state:v2:{league_key}")
        return entry is not None and self._content.get(entry.content_hash) is not None

    def get_league_info(self, league_key: str) -> LeagueConfig:
        """
        Get league configuration.
        """

        league = self._config.leagues.get(league_key)

        if league is None:
            raise ValueError(f"Unknown league: {league_key}")

        return league

    async def get_assumption_displays(
        self,
        league_key: str,
        assumptions: list[AssumptionEntry],
    ) -> list[AssumptionDisplay]:
        """
        Return display objects for assumptions that match a remaining match.
        """

        league = self._config.leagues.get(league_key)

        if league is None:
            raise ValueError(f"Unknown league: {league_key}")

        cached_state = await self._get_or_fetch_state(league_key, league)
        state = ChampionshipState.from_dict(cached_state.value)
        remaining_set = set(state.remaining_matches)

        return [
            AssumptionDisplay(
                home_id=a.home_id,
                home_name=state.team_by_id(a.home_id).name,
                away_id=a.away_id,
                away_name=state.team_by_id(a.away_id).name,
                home_score=a.home_score,
                away_score=a.away_score,
            )
            for a in assumptions
            if Match(home=a.home_id, away=a.away_id) in remaining_set
        ]

    async def get_projected_positions(
        self,
        league_key: str,
        assumptions: list[AssumptionEntry],
    ) -> dict[str, tuple[int, int]]:
        """
        Compute best/worst achievable position for every team with the given
        assumptions pre-applied.  Runs the solver for all teams in parallel.
        """

        league = self._config.leagues.get(league_key)

        if league is None:
            raise ValueError(f"Unknown league: {league_key}")

        cached_state = await self._get_or_fetch_state(league_key, league)
        state = ChampionshipState.from_dict(cached_state.value)
        remaining_set = set(state.remaining_matches)

        valid_assumptions = [
            a
            for a in assumptions
            if Match(home=a.home_id, away=a.away_id) in remaining_set
        ]
        assumption_tuples = tuple(
            (a.home_id, a.away_id, a.home_score, a.away_score)
            for a in valid_assumptions
        )

        team_ids = [t.id for t in state.teams]
        results = await asyncio.gather(
            *[
                self._resolve(
                    AnalyzeTeamComputation(cached_state, team_id, assumption_tuples)
                )
                for team_id in team_ids
            ]
        )

        positions: dict[str, tuple[int, int]] = {}
        for team_id, result in zip(team_ids, results):
            if result.value is not None:
                positions[team_id] = (
                    result.value.best_position,
                    result.value.worst_position,
                )

        return positions

    async def get_team_analysis(
        self,
        league_key: str,
        team_id: str,
        assumptions: list[AssumptionEntry] | None = None,
    ) -> TeamAnalysisResult | None:
        """
        Get position analysis for a team, optionally with assumed match results.
        """

        league = self._config.leagues.get(league_key)

        if league is None:
            raise ValueError(f"Unknown league: {league_key}")

        state = await self._get_or_fetch_state(league_key, league)

        assumption_tuples: tuple[tuple[str, str, int, int], ...] = ()
        if assumptions:
            state_model = ChampionshipState.from_dict(state.value)
            remaining_set = set(state_model.remaining_matches)
            assumption_tuples = tuple(
                (a.home_id, a.away_id, a.home_score, a.away_score)
                for a in assumptions
                if Match(home=a.home_id, away=a.away_id) in remaining_set
            )

        analysis = await self._resolve(
            AnalyzeTeamComputation(state, team_id, assumption_tuples)
        )

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
