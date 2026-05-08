"""
Ranking logic with tiebreaker rules.

Tiebreaker order:
1. Total points (more = better)
2. Mini-league points among tied teams
3. Game point quotient in mini-league (won/lost ratio)
4. Recursive mini-league among still-tied teams
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from orchamp.models import (
    Match,
    MatchResult,
    calculate_points_from_completed_matches,
)

if TYPE_CHECKING:
    from orchamp.models import ChampionshipState, CompletedMatch, Rules


@dataclass
class RankedTeam:
    """A team with its ranking information."""

    position: int
    team_id: str
    team_name: str
    points: int


def _get_match_between(
    t1: str,
    t2: str,
    completed_matches: dict["Match", "CompletedMatch"],
) -> tuple["Match", "CompletedMatch"] | None:
    """Find a completed match between two teams."""

    for match, completed in completed_matches.items():
        if (match.home == t1 and match.away == t2) or (
            match.home == t2 and match.away == t1
        ):
            return match, completed
    return None


def _get_points_for_team_in_match(
    team_id: str,
    match: "Match",
    completed: "CompletedMatch",
    rules: "Rules",
) -> int:
    """Get points earned by a team in a specific match."""

    result = completed.result
    is_home = match.home == team_id

    if is_home:
        if result == MatchResult.HOME_WIN:
            return rules.win_points
        elif result == MatchResult.DRAW:
            return rules.draw_points
        elif result == MatchResult.AWAY_FORFEIT:
            return rules.forfeit_win_points
        elif result == MatchResult.HOME_FORFEIT:
            return rules.forfeit_loss_points
        else:
            return rules.loss_points
    else:
        if result == MatchResult.AWAY_WIN:
            return rules.win_points
        elif result == MatchResult.DRAW:
            return rules.draw_points
        elif result == MatchResult.HOME_FORFEIT:
            return rules.forfeit_win_points
        elif result == MatchResult.AWAY_FORFEIT:
            return rules.forfeit_loss_points
        else:
            return rules.loss_points


def _get_game_points_for_team_in_match(
    team_id: str,
    match: "Match",
    completed: "CompletedMatch",
) -> tuple[int, int]:
    """
    Get game points (won, lost) for a team in a match.

    Returns (0, 0) if no score is available.
    """

    if completed.score is None:
        return 0, 0

    if match.home == team_id:
        return completed.score.home_score, completed.score.away_score
    else:
        return completed.score.away_score, completed.score.home_score


def _compute_mini_league_stats(
    team_ids: list[str],
    completed_matches: dict["Match", "CompletedMatch"],
    rules: "Rules",
) -> dict[str, tuple[int, int, int]]:
    """
    Compute mini-league stats for a group of tied teams.

    Returns dict mapping team_id to (mini_points, game_won, game_lost).
    """

    stats: dict[str, tuple[int, int, int]] = {t: (0, 0, 0) for t in team_ids}

    for i, t1 in enumerate(team_ids):
        for t2 in team_ids[i + 1 :]:
            result = _get_match_between(t1, t2, completed_matches)
            if result is None:
                continue

            match, completed = result

            # Match points
            t1_pts = _get_points_for_team_in_match(t1, match, completed, rules)
            t2_pts = _get_points_for_team_in_match(t2, match, completed, rules)

            # Game points
            t1_won, t1_lost = _get_game_points_for_team_in_match(t1, match, completed)
            t2_won, t2_lost = _get_game_points_for_team_in_match(t2, match, completed)

            old1 = stats[t1]
            old2 = stats[t2]
            stats[t1] = (old1[0] + t1_pts, old1[1] + t1_won, old1[2] + t1_lost)
            stats[t2] = (old2[0] + t2_pts, old2[1] + t2_won, old2[2] + t2_lost)

    return stats


def _game_point_quotient(won: int, lost: int) -> float:
    """Compute game point quotient, handling division by zero."""

    if lost == 0:
        return float("inf") if won > 0 else 1.0
    return won / lost


def _rank_tied_group(
    team_ids: list[str],
    completed_matches: dict["Match", "CompletedMatch"],
    rules: "Rules",
    depth: int = 0,
) -> list[str]:
    """
    Rank a group of teams tied on total points using tiebreakers.

    Returns team IDs in order from best to worst.
    """

    if len(team_ids) <= 1:
        return team_ids

    # Prevent infinite recursion
    if depth > 3:
        return team_ids

    # Compute mini-league stats
    stats = _compute_mini_league_stats(team_ids, completed_matches, rules)

    # Group by mini-league points
    by_mini_points: dict[int, list[str]] = {}
    for t in team_ids:
        mini_pts = stats[t][0]
        if mini_pts not in by_mini_points:
            by_mini_points[mini_pts] = []
        by_mini_points[mini_pts].append(t)

    result: list[str] = []
    for mini_pts in sorted(by_mini_points.keys(), reverse=True):
        group = by_mini_points[mini_pts]

        if len(group) == 1:
            result.extend(group)
        else:
            # Tied on mini-league points, use quotient
            group_with_quotient = [
                (t, _game_point_quotient(stats[t][1], stats[t][2])) for t in group
            ]
            group_with_quotient.sort(key=lambda x: x[1], reverse=True)

            # Group by quotient
            by_quotient: dict[float, list[str]] = {}
            for t, q in group_with_quotient:
                if q not in by_quotient:
                    by_quotient[q] = []
                by_quotient[q].append(t)

            for q in sorted(by_quotient.keys(), reverse=True):
                sub_group = by_quotient[q]
                if len(sub_group) == 1:
                    result.extend(sub_group)
                else:
                    # Still tied, recurse with sub-mini-league
                    result.extend(
                        _rank_tied_group(sub_group, completed_matches, rules, depth + 1)
                    )

    return result


def compute_rankings(
    state: "ChampionshipState",
    rules: "Rules",
) -> list[RankedTeam]:
    """
    Compute full rankings with tiebreakers applied.

    Returns list of RankedTeam objects ordered by position.
    """

    # Calculate total points for each team
    points = {
        t.id: calculate_points_from_completed_matches(
            team_id=t.id,
            completed_matches=state.completed_matches,
            rules=rules,
        )
        for t in state.teams
    }

    # Group teams by total points
    by_points: dict[int, list[str]] = {}
    for team in state.teams:
        p = points[team.id]
        if p not in by_points:
            by_points[p] = []
        by_points[p].append(team.id)

    # Rank each group and build final ordering
    ordered_ids: list[str] = []
    for p in sorted(by_points.keys(), reverse=True):
        group = by_points[p]
        if len(group) == 1:
            ordered_ids.extend(group)
        else:
            ordered_ids.extend(_rank_tied_group(group, state.completed_matches, rules))

    # Build result
    return [
        RankedTeam(
            position=i,
            team_id=team_id,
            team_name=state.team_by_id(team_id).name,
            points=points[team_id],
        )
        for i, team_id in enumerate(ordered_ids, 1)
    ]
