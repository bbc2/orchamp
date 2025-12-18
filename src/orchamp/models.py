"""
Data models for the championship analyzer.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Self


class MatchResult(Enum):
    """
    Possible outcomes of a match.
    """

    HOME_WIN = "home_win"
    DRAW = "draw"
    AWAY_WIN = "away_win"
    HOME_FORFEIT = "home_forfeit"
    AWAY_FORFEIT = "away_forfeit"


@dataclass(frozen=True)
class Team:
    """
    A team in the championship.
    """

    id: str
    name: str


@dataclass(frozen=True)
class Match:
    """
    A match between two teams.
    """

    home: str  # Team ID
    away: str  # Team ID


@dataclass(frozen=True)
class MatchScore:
    """
    Score of a match in terms of individual player match points.

    Each team earns points from the ten player matches (0-20 range).
    The sum is typically 30 but can be less in case of forfeits.
    """

    home_points: int  # 0-20
    away_points: int  # 0-20

    def __post_init__(self) -> None:
        if not (0 <= self.home_points <= 20):
            raise ValueError(f"home_points must be 0-20, got {self.home_points}")
        if not (0 <= self.away_points <= 20):
            raise ValueError(f"away_points must be 0-20, got {self.away_points}")

    def result(self) -> MatchResult:
        """
        Derive the match result from the score.

        Note: This returns HOME_WIN/DRAW/AWAY_WIN only.
        Forfeit detection would require additional context.
        """

        if self.home_points > self.away_points:
            return MatchResult.HOME_WIN
        elif self.home_points < self.away_points:
            return MatchResult.AWAY_WIN
        else:
            return MatchResult.DRAW


@dataclass(frozen=True)
class CompletedMatch:
    """
    A completed match with its result and optional score.
    """

    result: MatchResult
    score: MatchScore | None = None


@dataclass(frozen=True)
class Rules:
    """
    Championship rules defining the point system.
    """

    win_points: int
    draw_points: int
    loss_points: int
    forfeit_win_points: int
    forfeit_loss_points: int

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(
            win_points=data["win_points"],
            draw_points=data["draw_points"],
            loss_points=data["loss_points"],
            forfeit_win_points=data["forfeit_win_points"],
            forfeit_loss_points=data["forfeit_loss_points"],
        )


@dataclass(frozen=True)
class ChampionshipState:
    """
    Current state of a championship phase.
    """

    teams: list[Team]
    completed_matches: dict[Match, CompletedMatch] = field(default_factory=dict)
    remaining_matches: list[Match] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        teams = [Team(id=t["id"], name=t["name"]) for t in data["teams"]]

        completed = {}
        for m in data.get("completed_matches", []):
            match = Match(home=m["home"], away=m["away"])
            result = MatchResult(m["result"])
            score = None
            if "home_points" in m and "away_points" in m:
                score = MatchScore(
                    home_points=m["home_points"],
                    away_points=m["away_points"],
                )
            completed[match] = CompletedMatch(result=result, score=score)

        remaining = []
        for m in data.get("remaining_matches", []):
            remaining.append(Match(home=m["home"], away=m["away"]))

        return cls(
            teams=teams,
            completed_matches=completed,
            remaining_matches=remaining,
        )

    def team_by_id(self, team_id: str) -> Team:
        for t in self.teams:
            if t.id == team_id:
                return t

        raise ValueError(f"Team with ID {team_id} not found")


def calculate_points_from_completed_matches(
    team_id: str,
    completed_matches: dict["Match", "CompletedMatch"],
    rules: "Rules",
) -> int:
    """
    Calculate points earned by a team from completed matches.
    """

    points = 0
    for match, completed in completed_matches.items():
        result = completed.result
        if match.home == team_id:
            if result == MatchResult.HOME_WIN:
                points += rules.win_points
            elif result == MatchResult.DRAW:
                points += rules.draw_points
            elif result == MatchResult.AWAY_FORFEIT:
                points += rules.forfeit_win_points
            elif result == MatchResult.HOME_FORFEIT:
                points += rules.forfeit_loss_points
            else:
                points += rules.loss_points
        elif match.away == team_id:
            if result == MatchResult.AWAY_WIN:
                points += rules.win_points
            elif result == MatchResult.DRAW:
                points += rules.draw_points
            elif result == MatchResult.HOME_FORFEIT:
                points += rules.forfeit_win_points
            elif result == MatchResult.AWAY_FORFEIT:
                points += rules.forfeit_loss_points
            else:
                points += rules.loss_points
    return points


@dataclass(frozen=True)
class Standing:
    """
    A team's standing in a scenario.
    """

    team_id: str
    points: int
    position: int  # 1-indexed


@dataclass(frozen=True)
class Scenario:
    """
    A complete scenario with all match results resolved.
    """

    match_results: Mapping[Match, CompletedMatch]
    standings: list[Standing]

    def position_of(self, team_id: str) -> int:
        for s in self.standings:
            if s.team_id == team_id:
                return s.position
        raise ValueError(f"Team {team_id} not found in standings")
