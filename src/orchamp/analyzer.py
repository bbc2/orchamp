"""
High-level analyzer for championship queries.
"""

from dataclasses import dataclass
from typing import Mapping

from orchamp.models import ChampionshipState, Match, MatchResult, Rules, Scenario
from orchamp.solver import (
    Constraint,
    NoForfeitConstraint,
    SolverProtocol,
    TeamPositionConstraint,
)


@dataclass(frozen=True)
class MatchWithResult:
    match: Match
    required_result: MatchResult


@dataclass(frozen=True)
class PositionAnalysis:
    """
    Analysis of a team's possible positions.
    """

    team_id: str
    best_position: int
    worst_position: int
    best_scenario: Scenario
    worst_scenario: Scenario


@dataclass(frozen=True)
class WinnerAnalysis:
    """
    Analysis of teams that can still win.
    """

    possible_winners: list[str]
    scenarios_by_winner: Mapping[str, Scenario]


@dataclass(frozen=True)
class Analyzer:
    """
    High-level query interface for championship analysis.
    """

    solver: SolverProtocol

    def analyze_team_position(
        self,
        rules: Rules,
        state: ChampionshipState,
        team_id: str,
        allow_forfeits: bool = True,
    ) -> PositionAnalysis | None:
        """
        Find the best and worst possible positions for a team.
        """

        constraints: list[Constraint] = (
            [] if allow_forfeits else [NoForfeitConstraint()]
        )

        # Find best position
        best_scenario = self.solver.find_scenario(
            rules=rules,
            state=state,
            team_id=team_id,
            optimize_position="best",
            constraints=constraints,
        )

        if not best_scenario:
            return None

        # Find worst position
        worst_scenario = self.solver.find_scenario(
            rules=rules,
            state=state,
            team_id=team_id,
            optimize_position="worst",
            constraints=constraints,
        )

        if not worst_scenario:
            return None

        return PositionAnalysis(
            team_id=team_id,
            best_position=best_scenario.position_of(team_id),
            worst_position=worst_scenario.position_of(team_id),
            best_scenario=best_scenario,
            worst_scenario=worst_scenario,
        )

    def find_possible_winners(
        self,
        rules: Rules,
        state: ChampionshipState,
        allow_forfeits: bool = True,
    ) -> WinnerAnalysis:
        """
        Find all teams that can still win the championship.
        """

        constraints = [] if allow_forfeits else [NoForfeitConstraint()]
        possible_winners = []
        scenarios_by_winner: dict[str, Scenario] = {}

        for team in state.teams:
            # Can this team finish first?
            team_constraints = [
                *constraints,
                TeamPositionConstraint(team_id=team.id, max_position=1),
            ]
            scenario = self.solver.find_scenario(
                rules=rules,
                state=state,
                constraints=team_constraints,
            )

            if scenario:
                possible_winners.append(team.id)
                scenarios_by_winner[team.id] = scenario

        return WinnerAnalysis(
            possible_winners=possible_winners,
            scenarios_by_winner=scenarios_by_winner,
        )

    def can_team_achieve_position(
        self,
        rules: Rules,
        state: ChampionshipState,
        team_id: str,
        position: int,
        allow_forfeits: bool = True,
    ) -> Scenario | None:
        """
        Check if a team can achieve a specific position.
        """

        constraints = [] if allow_forfeits else [NoForfeitConstraint()]
        all_constraints = [
            *constraints,
            TeamPositionConstraint(
                team_id=team_id, min_position=position, max_position=position
            ),
        ]
        return self.solver.find_scenario(
            rules=rules,
            state=state,
            constraints=all_constraints,
        )

    def what_must_happen(
        self,
        rules: Rules,
        state: ChampionshipState,
        team_id: str,
        target_position: int,
        allow_forfeits: bool = True,
    ) -> list[MatchWithResult]:
        """
        Describe what needs to happen for a team to achieve a position.

        Returns a list of required results (matches that must go a certain way
        in all scenarios achieving the target position).
        """

        constraints = [] if allow_forfeits else [NoForfeitConstraint()]
        # Find all scenarios where the team achieves the target position
        all_constraints = [
            *constraints,
            TeamPositionConstraint(
                team_id=team_id,
                min_position=target_position,
                max_position=target_position,
            ),
        ]
        scenarios = self.solver.find_all_scenarios(
            rules=rules,
            state=state,
            constraints=all_constraints,
            limit=100,
        )

        if not scenarios:
            return []

        # Find matches that have the same outcome in ALL scenarios
        if not state.remaining_matches:
            return []

        required_results = []
        for match in state.remaining_matches:
            results_in_scenarios = {s.match_results.get(match) for s in scenarios}

            if len(results_in_scenarios) != 1:
                continue

            completed = results_in_scenarios.pop()

            if not completed:
                continue

            required_results.append(
                MatchWithResult(
                    match=match,
                    required_result=completed.result,
                )
            )

        return required_results
