from inline_snapshot import snapshot

from orchamp.models import (
    ChampionshipState,
    CompletedMatch,
    Match,
    MatchResult,
    Rules,
    Scenario,
    Standing,
    Team,
)
from orchamp.solver import (
    Constraint,
    MatchResultConstraint,
    TeamMinPointsConstraint,
    TeamPositionConstraint,
)
from orchamp.solvers.cpsat import CpSatSolver

from ..fixtures import (
    circular_three_way_tie_state,
    head_to_head_tiebreaker_state,
    multi_tie_state,
    standard_rules,
)


def make_solver() -> CpSatSolver:
    return CpSatSolver(random_seed=42, num_workers=1)


def create_minimal_state() -> ChampionshipState:
    """
    Create a minimal championship state with 2 teams and 1 remaining match.
    """

    teams = [
        Team(id="alpha", name="Alpha"),
        Team(id="beta", name="Beta"),
    ]
    return ChampionshipState(
        teams=teams,
        completed_matches={},
        remaining_matches=[Match(home="alpha", away="beta")],
    )


class TestCpSatSolver:
    def test_find_scenario_basic(self) -> None:
        """
        This finds one possible scenario, without extra constraints.
        """

        solver = make_solver()
        rules = standard_rules()
        state = create_minimal_state()

        scenario = solver.find_scenario(rules=rules, state=state)

        assert scenario is not None
        assert len(scenario.match_results) == 1

    def test_find_scenario_with_constraints(self) -> None:
        solver = make_solver()
        rules = standard_rules()
        state = create_minimal_state()

        # Force alpha to win
        match = state.remaining_matches[0]
        constraints = [
            MatchResultConstraint(match=match, result=MatchResult.HOME_WIN),
            TeamPositionConstraint(team_id="alpha", max_position=1),
        ]

        scenario = solver.find_scenario(
            rules=rules, state=state, constraints=constraints
        )

        assert scenario is not None
        assert scenario.match_results[match].result == MatchResult.HOME_WIN
        alpha_standing = next(s for s in scenario.standings if s.team_id == "alpha")
        assert alpha_standing.position == 1

    def test_find_scenario_no_solution(self) -> None:
        """
        Test with impossible constraints: alpha must win but be in last place.
        """

        solver = make_solver()
        rules = standard_rules()
        state = create_minimal_state()

        match = state.remaining_matches[0]
        constraints = [
            MatchResultConstraint(match=match, result=MatchResult.HOME_WIN),
            TeamPositionConstraint(team_id="alpha", min_position=2),
        ]

        scenario = solver.find_scenario(
            rules=rules, state=state, constraints=constraints
        )

        assert scenario is None

    def test_find_all_scenarios_no_limit(self) -> None:
        solver = make_solver()
        rules = standard_rules()
        state = create_minimal_state()

        scenarios = solver.find_all_scenarios(rules=rules, state=state)

        scenarios.sort(key=lambda s: str(s.match_results))  # sort for determinism
        assert scenarios == snapshot(
            [
                Scenario(
                    match_results={
                        Match(home="alpha", away="beta"): CompletedMatch(
                            result=MatchResult.AWAY_FORFEIT
                        )
                    },
                    standings=[
                        Standing(team_id="alpha", points=3, position=1),
                        Standing(team_id="beta", points=0, position=2),
                    ],
                ),
                Scenario(
                    match_results={
                        Match(home="alpha", away="beta"): CompletedMatch(
                            result=MatchResult.AWAY_WIN
                        )
                    },
                    standings=[
                        Standing(team_id="beta", points=3, position=1),
                        Standing(team_id="alpha", points=1, position=2),
                    ],
                ),
                Scenario(
                    match_results={
                        Match(home="alpha", away="beta"): CompletedMatch(
                            result=MatchResult.DRAW
                        )
                    },
                    standings=[
                        Standing(team_id="alpha", points=2, position=1),
                        Standing(team_id="beta", points=2, position=2),
                    ],
                ),
                Scenario(
                    match_results={
                        Match(home="alpha", away="beta"): CompletedMatch(
                            result=MatchResult.DRAW
                        )
                    },
                    standings=[
                        Standing(team_id="beta", points=2, position=1),
                        Standing(team_id="alpha", points=2, position=2),
                    ],
                ),
                Scenario(
                    match_results={
                        Match(home="alpha", away="beta"): CompletedMatch(
                            result=MatchResult.HOME_FORFEIT
                        )
                    },
                    standings=[
                        Standing(team_id="beta", points=3, position=1),
                        Standing(team_id="alpha", points=0, position=2),
                    ],
                ),
                Scenario(
                    match_results={
                        Match(home="alpha", away="beta"): CompletedMatch(
                            result=MatchResult.HOME_WIN
                        )
                    },
                    standings=[
                        Standing(team_id="alpha", points=3, position=1),
                        Standing(team_id="beta", points=1, position=2),
                    ],
                ),
            ]
        )

    def test_find_all_scenarios_limit(self) -> None:
        solver = make_solver()
        rules = standard_rules()
        state = create_minimal_state()

        scenarios = solver.find_all_scenarios(rules=rules, state=state, limit=2)

        assert len(scenarios) == 2

    def test_find_all_scenarios_includes_forfeits(self) -> None:
        """Test that the solver considers forfeit outcomes."""
        solver = make_solver()
        rules = standard_rules()
        state = create_minimal_state()
        match = Match(home="alpha", away="beta")

        scenarios = solver.find_all_scenarios(rules=rules, state=state)

        results = {s.match_results[match].result for s in scenarios}
        assert results == {
            MatchResult.HOME_WIN,
            MatchResult.DRAW,
            MatchResult.AWAY_WIN,
            MatchResult.HOME_FORFEIT,
            MatchResult.AWAY_FORFEIT,
        }

    def test_team_min_points_constraint(self) -> None:
        solver = make_solver()
        rules = Rules(
            win_points=3,
            draw_points=1,
            loss_points=0,
            forfeit_win_points=2,
            forfeit_loss_points=0,
        )
        state = create_minimal_state()
        constraints: list[Constraint] = [
            TeamMinPointsConstraint(team_id="beta", min_points=3)
        ]

        scenario = solver.find_scenario(
            rules=rules, state=state, constraints=constraints
        )

        assert scenario is not None
        beta_standing = next(s for s in scenario.standings if s.team_id == "beta")
        assert beta_standing.points >= 3


class TestHeadToHeadTiebreaker:
    def test_head_to_head_tiebreaker_produces_unique_ranking(self) -> None:
        """
        With head-to-head tiebreaking, only one ranking is valid.

        The fixture has:
        - Alpha and Gamma tied at 7 points
        - Beta and Delta tied at 5 points

        Head-to-head results:
        - Gamma beat Alpha → Gamma ranks above Alpha
        - Delta beat Beta → Delta ranks above Beta

        Expected ranking: Gamma (1st) > Alpha (2nd) > Delta (3rd) > Beta (4th)
        """

        solver = make_solver()
        rules = standard_rules()
        state = head_to_head_tiebreaker_state()

        scenarios = solver.find_all_scenarios(rules=rules, state=state)

        assert len(scenarios) == 1

        ranking = tuple(s.team_id for s in scenarios[0].standings)
        assert ranking == ("gamma", "alpha", "delta", "beta")

    def test_circular_three_way_tie_allows_all_permutations(self) -> None:
        """
        With a circular 3-way tie, all 6 ranking permutations are valid.

        A beat B, B beat C, C beat A.
        All three have equal total points (4) and equal mini-league points (4).
        """

        solver = make_solver()
        rules = standard_rules()
        state = circular_three_way_tie_state()

        scenarios = solver.find_all_scenarios(rules=rules, state=state)

        assert len(scenarios) == 6

        rankings = {
            tuple(s.team_id for s in scenario.standings) for scenario in scenarios
        }
        assert rankings == {
            ("A", "B", "C"),
            ("A", "C", "B"),
            ("B", "A", "C"),
            ("B", "C", "A"),
            ("C", "A", "B"),
            ("C", "B", "A"),
        }

    def test_multi_tie_state_rankings(self) -> None:
        """
        Test ranking resolution in a 7-team league with multiple ties.

        Points:
        - Trantor: 14 (4W, 0D, 2L)
        - Terminus: 13 (3W, 1D, 2L)
        - Kalgan: 12 (3W, 0D, 3L)
        - Tazenda: 12 (2W, 2D, 2L)
        - Santanni, Stars' End, Aurora: 11 each (2W, 1D, 3L)

        Kalgan vs Tazenda: Kalgan won, so Kalgan should rank above Tazenda.

        Bottom three (Santanni, Stars' End, Aurora) have a circular tie on match points:
        - Santanni beat Aurora
        - Stars' End beat Santanni
        - Aurora beat Stars' End
        All have 4 mini-league match points (1W, 1L each).

        Game point quotient tiebreaker (from mini-league scores):
        - Santanni: 5 won / 4 lost → quotient 1.25
        - Stars' End: 5 won / 4 lost → quotient 1.25
        - Aurora: 4 won / 6 lost → quotient 0.67

        Aurora is 7th (worst quotient). Santanni/Stars' End tied on quotient.

        Sub-mini-league for Santanni vs Stars' End (h2h points):
        - Santanni beat Stars' End 3-1
        - Santanni: 3 match points, Stars' End: 1 match point

        Final ranking: Santanni 5th, Stars' End 6th, Aurora 7th (only 1 valid ordering)
        """

        solver = make_solver()
        rules = standard_rules()
        state = multi_tie_state()

        scenarios = solver.find_all_scenarios(rules=rules, state=state)

        assert len(scenarios) == 1

        # The only valid ranking
        scenario = scenarios[0]
        ranking = [s.team_id for s in scenario.standings]
        assert ranking == [
            "trantor",
            "terminus",
            "kalgan",
            "tazenda",
            "santanni",
            "stars_end",
            "aurora",
        ]
