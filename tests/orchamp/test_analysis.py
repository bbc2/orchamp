from inline_snapshot import snapshot

from orchamp.analyzer import Analyzer
from orchamp.models import (
    ChampionshipState,
    Match,
    MatchResult,
    Rules,
    Team,
)
from orchamp.solvers.cpsat import CpSatSolver

from .fixtures import C, small_league_state, standard_rules


def make_analyzer() -> Analyzer:
    return Analyzer(solver=CpSatSolver(random_seed=42, num_workers=1))


class TestStandings:
    def test_current_standings(self):
        """Test current standings calculation from completed matches."""
        state = small_league_state()
        rules = standard_rules()

        # Calculate points manually (same logic as CLI)
        points: dict[str, int] = {t.id: 0 for t in state.teams}
        for match, completed in state.completed_matches.items():
            if completed.result.value == "home_win":
                points[match.home] += rules.win_points
                points[match.away] += rules.loss_points
            elif completed.result.value == "away_win":
                points[match.away] += rules.win_points
                points[match.home] += rules.loss_points
            else:
                points[match.home] += rules.draw_points
                points[match.away] += rules.draw_points

        sorted_teams = sorted(state.teams, key=lambda t: points[t.id], reverse=True)
        standings = [
            {"position": i, "team_id": t.id, "points": points[t.id]}
            for i, t in enumerate(sorted_teams, 1)
        ]

        assert standings == snapshot(
            [
                {"position": 1, "team_id": "alpha", "points": 5},
                {"position": 2, "team_id": "gamma", "points": 5},
                {"position": 3, "team_id": "beta", "points": 2},
                {"position": 4, "team_id": "delta", "points": 0},
            ]
        )


class TestAnalyzeTeam:
    def test_delta_best_and_worst_positions(self):
        """Test that Delta can finish anywhere from 1st to 4th."""
        analyzer = make_analyzer()

        analysis = analyzer.analyze_team_position(
            rules=standard_rules(), state=small_league_state(), team_id="delta"
        )

        assert analysis is not None
        assert analysis.best_position == snapshot(1)
        assert analysis.worst_position == snapshot(4)

    def test_alpha_best_and_worst_positions(self):
        """Test Alpha's position range (currently leading)."""
        analyzer = make_analyzer()

        analysis = analyzer.analyze_team_position(
            rules=standard_rules(), state=small_league_state(), team_id="alpha"
        )

        assert analysis is not None
        assert analysis.best_position == snapshot(1)
        assert analysis.worst_position == snapshot(4)

    def test_best_scenario_is_valid(self):
        """Test that best scenario standings are consistent."""
        analyzer = make_analyzer()

        analysis = analyzer.analyze_team_position(
            rules=standard_rules(), state=small_league_state(), team_id="delta"
        )

        assert analysis is not None
        assert analysis.best_scenario.position_of("delta") == 1
        positions = [s.position for s in analysis.best_scenario.standings]
        assert sorted(positions) == [1, 2, 3, 4]


class TestWhoCanWin:
    def test_possible_winners(self):
        """Test which teams can still win."""
        analyzer = make_analyzer()

        analysis = analyzer.find_possible_winners(
            rules=standard_rules(), state=small_league_state()
        )

        winners = sorted(analysis.possible_winners)
        assert winners == snapshot(["alpha", "delta", "gamma"])

    def test_beta_cannot_win(self):
        """Beta is too far behind to win even with forfeits."""
        analyzer = make_analyzer()
        rules = Rules(
            win_points=3,
            draw_points=2,
            loss_points=1,
            forfeit_win_points=2,
            forfeit_loss_points=0,
        )

        teams = [Team(id="A", name="A"), Team(id="B", name="B"), Team(id="C", name="C")]
        # A has 12 points, B has 2 points. 1 match left for B.
        state = ChampionshipState(
            teams=teams,
            completed_matches={
                Match(home="A", away="B"): C(MatchResult.HOME_WIN),
                Match(home="B", away="A"): C(MatchResult.AWAY_WIN),
                Match(home="A", away="C"): C(MatchResult.HOME_WIN),
                Match(home="C", away="A"): C(MatchResult.AWAY_WIN),
            },
            remaining_matches=[Match(home="B", away="C")],
        )

        analysis = analyzer.find_possible_winners(rules=rules, state=state)

        assert "B" not in analysis.possible_winners


class TestWhatMustHappen:
    def test_impossible_position(self):
        """Test querying an impossible outcome."""
        analyzer = make_analyzer()
        rules = Rules(
            win_points=3,
            draw_points=2,
            loss_points=1,
            forfeit_win_points=2,
            forfeit_loss_points=0,
        )
        teams = [Team(id="A", name="A"), Team(id="B", name="B"), Team(id="C", name="C")]
        state = ChampionshipState(
            teams=teams,
            completed_matches={
                Match(home="A", away="B"): C(MatchResult.HOME_WIN),
                Match(home="B", away="A"): C(MatchResult.AWAY_WIN),
                Match(home="A", away="C"): C(MatchResult.HOME_WIN),
                Match(home="C", away="A"): C(MatchResult.AWAY_WIN),
            },
            remaining_matches=[Match(home="B", away="C")],
        )

        # B cannot be 1st
        scenario = analyzer.can_team_achieve_position(
            rules=rules, state=state, team_id="B", position=1
        )

        assert scenario is None

    def test_achievable_position(self):
        """Test querying an achievable outcome."""
        analyzer = make_analyzer()

        scenario = analyzer.can_team_achieve_position(
            rules=standard_rules(),
            state=small_league_state(),
            team_id="delta",
            position=1,
        )

        assert scenario is not None
        assert scenario.position_of("delta") == 1

    def test_what_must_happen_required_win(self):
        """
        Test what_must_happen when a win is strictly required.
        """

        analyzer = make_analyzer()
        rules = Rules(
            win_points=3,
            draw_points=1,
            loss_points=0,
            forfeit_win_points=2,
            forfeit_loss_points=0,
        )

        # Team A has 3 points, Team B has 0 points.
        # One match left: A vs B.
        # For B to be 1st, B must win.
        teams = [
            Team(id="A", name="Team A"),
            Team(id="B", name="Team B"),
            Team(id="C", name="Team C"),
        ]
        # A beat C
        completed = {
            Match(home="A", away="C"): C(MatchResult.HOME_WIN),
        }
        # B vs A remaining
        remaining = [
            Match(home="A", away="B"),
        ]
        state = ChampionshipState(
            teams=teams,
            completed_matches=completed,
            remaining_matches=remaining,
        )

        # For B to be 1st:
        # If B wins: B=3, A=3, C=0. B can be 1st.
        # If B draws: B=1, A=4, C=0. B is 2nd.
        # If B loses: B=0, A=6, C=0. B is 2nd.
        results = analyzer.what_must_happen(
            rules=rules, state=state, team_id="B", target_position=1
        )

        assert len(results) == 1
        assert results[0].match == Match(home="A", away="B")
        assert results[0].required_result == MatchResult.AWAY_WIN

    def test_what_must_happen_impossible(self):
        """
        Test what_must_happen for an impossible position.
        """

        analyzer = make_analyzer()
        rules = Rules(
            win_points=3,
            draw_points=2,
            loss_points=1,
            forfeit_win_points=2,
            forfeit_loss_points=0,
        )
        teams = [Team(id="A", name="A"), Team(id="B", name="B"), Team(id="C", name="C")]
        state = ChampionshipState(
            teams=teams,
            completed_matches={
                Match(home="A", away="B"): C(MatchResult.HOME_WIN),
                Match(home="B", away="A"): C(MatchResult.AWAY_WIN),
                Match(home="A", away="C"): C(MatchResult.HOME_WIN),
                Match(home="C", away="A"): C(MatchResult.AWAY_WIN),
            },
            remaining_matches=[Match(home="B", away="C")],
        )

        # B cannot be 1st
        results = analyzer.what_must_happen(
            rules=rules,
            state=state,
            team_id="B",
            target_position=1,
        )

        assert results == []

    def test_what_must_happen_no_remaining_matches(self):
        """
        Test what_must_happen when the championship is over.
        """

        analyzer = make_analyzer()
        teams = [Team(id="A", name="Team A"), Team(id="B", name="Team B")]
        state = ChampionshipState(
            teams=teams,
            completed_matches={
                Match(home="A", away="B"): C(MatchResult.HOME_WIN),
            },
            remaining_matches=[],
        )

        # A is 1st, B is 2nd.
        results = analyzer.what_must_happen(
            rules=standard_rules(),
            state=state,
            team_id="A",
            target_position=1,
        )

        assert results == []


class TestScenarioConsistency:
    def test_scenario_points_match_standings(self):
        """
        Verify that scenario standings have correct point ordering.
        """
        analyzer = make_analyzer()

        analysis = analyzer.analyze_team_position(
            rules=standard_rules(), state=small_league_state(), team_id="alpha"
        )

        assert analysis is not None
        for scenario in [analysis.best_scenario, analysis.worst_scenario]:
            for i, standing in enumerate(scenario.standings[:-1]):
                next_standing = scenario.standings[i + 1]
                assert standing.points >= next_standing.points, (
                    f"Position {standing.position} has {standing.points} pts, "
                    f"but position {next_standing.position} has {next_standing.points} pts"
                )
