"""
Abstract solver protocol for championship analysis.
"""

from abc import ABC
from dataclasses import dataclass
from typing import Protocol

from orchamp.models import ChampionshipState, Match, MatchResult, Rules, Scenario


class Constraint(ABC):
    """
    Base class for solver constraints.
    """


@dataclass(frozen=True)
class TeamPositionConstraint(Constraint):
    """
    Constrain a team's final position.
    """

    team_id: str
    min_position: int | None = None  # 1 = first place
    max_position: int | None = None


@dataclass(frozen=True)
class MatchResultConstraint(Constraint):
    """
    Force a specific match result.
    """

    match: Match
    result: MatchResult


@dataclass(frozen=True)
class TeamMinPointsConstraint(Constraint):
    """
    Constrain a team's minimum points.
    """

    team_id: str
    min_points: int


@dataclass(frozen=True)
class NoForfeitConstraint(Constraint):
    """
    Exclude forfeit outcomes from consideration.
    """


class SolverProtocol(Protocol):
    """Protocol defining the interface for championship solvers.

    Any solver backend (OR-Tools, Z3, custom) must implement this interface.
    """

    def find_scenario(
        self,
        rules: Rules,
        state: ChampionshipState,
        team_id: str | None = None,
        optimize_position: str | None = None,  # "best" or "worst"
        constraints: list["Constraint"] | None = None,
    ) -> Scenario | None:
        """Find a scenario matching the given constraints.

        Args:
            rules: Championship rules (points system)
            state: Current championship state
            team_id: Team to optimize for (if optimizing)
            optimize_position: "best" for highest position, "worst" for lowest
            constraints: Additional constraints to apply

        Returns:
            A Scenario satisfying all constraints, or None if impossible
        """
        ...

    def find_all_scenarios(
        self,
        rules: Rules,
        state: ChampionshipState,
        constraints: list["Constraint"] | None = None,
        limit: int | None = None,
    ) -> list[Scenario]:
        """Find all scenarios matching constraints (up to limit).

        Args:
            rules: Championship rules
            state: Current championship state
            constraints: Additional constraints to apply
            limit: Maximum number of scenarios to return

        Returns:
            List of scenarios satisfying all constraints
        """
        ...
