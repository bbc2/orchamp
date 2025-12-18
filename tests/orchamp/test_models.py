import pytest

from orchamp.models import (
    ChampionshipState,
    Match,
    MatchResult,
    Rules,
    Team,
    calculate_points_from_completed_matches,
)

from .fixtures import C


class TestCalculatePoints:
    def test_away_forfeit_gives_home_team_forfeit_win_points(self) -> None:
        rules = Rules(
            win_points=3,
            draw_points=2,
            loss_points=1,
            forfeit_win_points=2,
            forfeit_loss_points=0,
        )
        match = Match(home="A", away="B")
        completed = {match: C(MatchResult.AWAY_FORFEIT)}

        result = calculate_points_from_completed_matches("A", completed, rules)

        assert result == 2

    def test_away_forfeit_gives_away_team_forfeit_loss_points(self) -> None:
        rules = Rules(
            win_points=3,
            draw_points=2,
            loss_points=1,
            forfeit_win_points=2,
            forfeit_loss_points=0,
        )
        match = Match(home="A", away="B")
        completed = {match: C(MatchResult.AWAY_FORFEIT)}

        result = calculate_points_from_completed_matches("B", completed, rules)

        assert result == 0

    def test_home_forfeit_gives_home_team_forfeit_loss_points(self) -> None:
        rules = Rules(
            win_points=3,
            draw_points=2,
            loss_points=1,
            forfeit_win_points=2,
            forfeit_loss_points=0,
        )
        match = Match(home="A", away="B")
        completed = {match: C(MatchResult.HOME_FORFEIT)}

        result = calculate_points_from_completed_matches("A", completed, rules)

        assert result == 0

    def test_home_forfeit_gives_away_team_forfeit_win_points(self) -> None:
        rules = Rules(
            win_points=3,
            draw_points=2,
            loss_points=1,
            forfeit_win_points=2,
            forfeit_loss_points=0,
        )
        match = Match(home="A", away="B")
        completed = {match: C(MatchResult.HOME_FORFEIT)}

        result = calculate_points_from_completed_matches("B", completed, rules)

        assert result == 2


class TestChampionshipState:
    def test_team_by_id_returns_team(self) -> None:
        state = ChampionshipState(
            teams=[Team(id="alpha", name="Alpha"), Team(id="beta", name="Beta")]
        )

        result = state.team_by_id("beta")

        assert result == Team(id="beta", name="Beta")

    def test_team_by_id_raises_for_unknown_team(self) -> None:
        state = ChampionshipState(
            teams=[Team(id="alpha", name="Alpha"), Team(id="beta", name="Beta")]
        )

        with pytest.raises(ValueError, match="unknown"):
            state.team_by_id("unknown")
