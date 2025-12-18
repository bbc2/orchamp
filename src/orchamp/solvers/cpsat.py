"""
OR-Tools CP-SAT solver implementation.
"""

from ortools.sat.python import cp_model

from orchamp.models import (
    ChampionshipState,
    CompletedMatch,
    Match,
    MatchResult,
    Rules,
    Scenario,
    Standing,
    calculate_points_from_completed_matches,
)
from orchamp.solver import (
    Constraint,
    MatchResultConstraint,
    NoForfeitConstraint,
    TeamMinPointsConstraint,
    TeamPositionConstraint,
)


class _SolutionCollector(cp_model.CpSolverSolutionCallback):
    """
    Collects multiple solutions.
    """

    def __init__(
        self,
        match_vars: dict[Match, dict[MatchResult, cp_model.IntVar]],
        team_points: dict[str, cp_model.IntVar],
        team_positions: dict[str, cp_model.IntVar],
        state: ChampionshipState,
        limit: int | None,
    ):
        super().__init__()
        self._match_vars = match_vars
        self._team_points = team_points
        self._team_positions = team_positions
        self._state = state
        self._limit = limit
        self.scenarios: list[Scenario] = []

    def on_solution_callback(self):
        if self._limit and len(self.scenarios) >= self._limit:
            self.StopSearch()
            return

        results = {}
        for match, outcome_vars in self._match_vars.items():
            for result, var in outcome_vars.items():
                if self.Value(var) == 1:
                    results[match] = CompletedMatch(result=result)
                    break

        standings = []
        for team in self._state.teams:
            standings.append(
                Standing(
                    team_id=team.id,
                    points=self.Value(self._team_points[team.id]),
                    position=self.Value(self._team_positions[team.id]),
                )
            )

        standings.sort(key=lambda s: s.position)
        self.scenarios.append(Scenario(match_results=results, standings=standings))


class CpSatSolver:
    """
    Championship solver using Google OR-Tools CP-SAT.
    """

    def __init__(
        self,
        random_seed: int | None = None,
        num_workers: int | None = None,
    ):
        self._random_seed = random_seed
        self._num_workers = num_workers

    def _create_solver(self) -> cp_model.CpSolver:
        solver = cp_model.CpSolver()

        if self._random_seed is not None:
            solver.parameters.random_seed = self._random_seed

        if self._num_workers is not None:
            solver.parameters.num_workers = self._num_workers

        return solver

    def _calculate_base_points(
        self, team_id: str, state: ChampionshipState, rules: Rules
    ) -> int:
        """
        Calculate points from completed matches.
        """

        return calculate_points_from_completed_matches(
            team_id=team_id,
            completed_matches=state.completed_matches,
            rules=rules,
        )

    def _build_model(
        self,
        model: cp_model.CpModel,
        rules: Rules,
        state: ChampionshipState,
    ) -> tuple[
        dict[Match, dict[MatchResult, cp_model.IntVar]], dict[str, cp_model.IntVar]
    ]:
        """
        Build the core CP model.
        """

        # Variables: for each remaining match, boolean vars for each outcome
        match_vars: dict[Match, dict[MatchResult, cp_model.IntVar]] = {}

        for match in state.remaining_matches:
            match_vars[match] = {
                MatchResult.HOME_WIN: model.NewBoolVar(
                    f"{match.home}_vs_{match.away}_home"
                ),
                MatchResult.DRAW: model.NewBoolVar(
                    f"{match.home}_vs_{match.away}_draw"
                ),
                MatchResult.AWAY_WIN: model.NewBoolVar(
                    f"{match.home}_vs_{match.away}_away"
                ),
                MatchResult.HOME_FORFEIT: model.NewBoolVar(
                    f"{match.home}_vs_{match.away}_home_forfeit"
                ),
                MatchResult.AWAY_FORFEIT: model.NewBoolVar(
                    f"{match.home}_vs_{match.away}_away_forfeit"
                ),
            }
            # Exactly one outcome per match
            model.AddExactlyOne(list(match_vars[match].values()))

        # Team points calculation
        max_matches = len(state.teams) - 1  # Max matches per team in round-robin
        max_points = max_matches * max(
            rules.win_points,
            rules.draw_points,
            rules.loss_points,
            rules.forfeit_win_points,
            rules.forfeit_loss_points,
        )

        team_points: dict[str, cp_model.IntVar] = {}

        for team in state.teams:
            # Base points from completed matches
            base_points = self._calculate_base_points(
                team_id=team.id, state=state, rules=rules
            )

            # Points from remaining matches
            point_contributions = []
            for match in state.remaining_matches:
                if match.home == team.id:
                    # Team is home
                    point_contributions.append(
                        (match_vars[match][MatchResult.HOME_WIN], rules.win_points)
                    )
                    point_contributions.append(
                        (match_vars[match][MatchResult.DRAW], rules.draw_points)
                    )
                    point_contributions.append(
                        (match_vars[match][MatchResult.AWAY_WIN], rules.loss_points)
                    )
                    point_contributions.append(
                        (
                            match_vars[match][MatchResult.AWAY_FORFEIT],
                            rules.forfeit_win_points,
                        )
                    )
                    point_contributions.append(
                        (
                            match_vars[match][MatchResult.HOME_FORFEIT],
                            rules.forfeit_loss_points,
                        )
                    )
                elif match.away == team.id:
                    # Team is away
                    point_contributions.append(
                        (match_vars[match][MatchResult.AWAY_WIN], rules.win_points)
                    )
                    point_contributions.append(
                        (match_vars[match][MatchResult.DRAW], rules.draw_points)
                    )
                    point_contributions.append(
                        (match_vars[match][MatchResult.HOME_WIN], rules.loss_points)
                    )
                    point_contributions.append(
                        (
                            match_vars[match][MatchResult.HOME_FORFEIT],
                            rules.forfeit_win_points,
                        )
                    )
                    point_contributions.append(
                        (
                            match_vars[match][MatchResult.AWAY_FORFEIT],
                            rules.forfeit_loss_points,
                        )
                    )

            team_points[team.id] = model.NewIntVar(
                0, base_points + max_points, f"points_{team.id}"
            )

            if point_contributions:
                model.Add(
                    team_points[team.id]
                    == base_points
                    + sum(var * coef for var, coef in point_contributions)
                )
            else:
                model.Add(team_points[team.id] == base_points)

        return match_vars, team_points

    def _points_for_team_in_match(
        self, is_home: bool, result: MatchResult, rules: Rules
    ) -> int:
        """
        Get points earned by a team given match result and whether they're home.
        """

        if is_home:
            if result == MatchResult.HOME_WIN:
                return rules.win_points
            elif result == MatchResult.DRAW:
                return rules.draw_points
            elif result == MatchResult.AWAY_WIN:
                return rules.loss_points
            elif result == MatchResult.AWAY_FORFEIT:
                return rules.forfeit_win_points
            elif result == MatchResult.HOME_FORFEIT:
                return rules.forfeit_loss_points
        else:
            if result == MatchResult.AWAY_WIN:
                return rules.win_points
            elif result == MatchResult.DRAW:
                return rules.draw_points
            elif result == MatchResult.HOME_WIN:
                return rules.loss_points
            elif result == MatchResult.HOME_FORFEIT:
                return rules.forfeit_win_points
            elif result == MatchResult.AWAY_FORFEIT:
                return rules.forfeit_loss_points

        return 0

    def _find_match_between(
        self, t1_id: str, t2_id: str, state: ChampionshipState
    ) -> tuple[Match | None, bool]:
        """
        Find the match between two teams.

        Returns (match, t1_is_home) or (None, False) if no match exists.
        """

        for m in state.completed_matches:
            if m.home == t1_id and m.away == t2_id:
                return (m, True)
            elif m.home == t2_id and m.away == t1_id:
                return (m, False)

        for m in state.remaining_matches:
            if m.home == t1_id and m.away == t2_id:
                return (m, True)
            elif m.home == t2_id and m.away == t1_id:
                return (m, False)

        return (None, False)

    def _game_points_for_team_in_match(
        self, team_id: str, match: Match, state: ChampionshipState
    ) -> tuple[int, int]:
        """
        Get game points won and lost by a team in a completed match.

        Returns (points_won, points_lost) or (0, 0) if match has no score.
        """

        completed = state.completed_matches.get(match)
        if completed is None or completed.score is None:
            return (0, 0)

        score = completed.score
        if match.home == team_id:
            return (score.home_points, score.away_points)
        else:
            return (score.away_points, score.home_points)

    def _add_position_variables(
        self,
        model: cp_model.CpModel,
        state: ChampionshipState,
        team_points: dict[str, cp_model.IntVar],
        match_vars: dict[Match, dict[MatchResult, cp_model.IntVar]],
        rules: Rules,
    ) -> dict[str, cp_model.IntVar]:
        """
        Add position variables based on points and mini-league tiebreaker.

        Position is determined by:
        1. Total points (more points = better position)
        2. Mini-league points among teams with equal total points
        3. Game point quotient in mini-league
        4. Random tiebreaker if still tied on game point quotient
        """

        n_teams = len(state.teams)
        team_ids = [t.id for t in state.teams]

        # Position variables
        team_positions: dict[str, cp_model.IntVar] = {}
        for team in state.teams:
            team_positions[team.id] = model.NewIntVar(1, n_teams, f"position_{team.id}")
        model.AddAllDifferent(list(team_positions.values()))

        max_match_points = max(
            rules.win_points,
            rules.draw_points,
            rules.loss_points,
            rules.forfeit_win_points,
            rules.forfeit_loss_points,
        )

        # Step 1: Compute h2h_points[t1][t2] = points t1 earns from match against t2
        h2h_points: dict[str, dict[str, cp_model.IntVar | int]] = {
            t: {} for t in team_ids
        }

        for t1 in team_ids:
            for t2 in team_ids:
                if t1 == t2:
                    continue

                match, t1_is_home = self._find_match_between(
                    t1_id=t1, t2_id=t2, state=state
                )

                if match is None:
                    # Teams don't play each other
                    h2h_points[t1][t2] = 0
                    continue

                if match in state.completed_matches:
                    # Fixed points based on completed result
                    result = state.completed_matches[match].result
                    pts = self._points_for_team_in_match(
                        is_home=t1_is_home, result=result, rules=rules
                    )
                    h2h_points[t1][t2] = pts
                else:
                    # Variable based on remaining match outcome
                    pts_var = model.NewIntVar(0, max_match_points, f"h2h_{t1}_vs_{t2}")
                    contributions = []
                    for result, var in match_vars[match].items():
                        pts = self._points_for_team_in_match(
                            is_home=t1_is_home, result=result, rules=rules
                        )
                        contributions.append((var, pts))
                    model.Add(pts_var == sum(var * coef for var, coef in contributions))
                    h2h_points[t1][t2] = pts_var

        # Step 2: For each pair, compute is_tied (equal total points)
        is_tied: dict[str, dict[str, cp_model.IntVar]] = {t: {} for t in team_ids}
        for i, t1 in enumerate(team_ids):
            for t2 in team_ids[i + 1 :]:
                b = model.NewBoolVar(f"tied_{t1}_{t2}")
                model.Add(team_points[t1] == team_points[t2]).OnlyEnforceIf(b)
                model.Add(team_points[t1] != team_points[t2]).OnlyEnforceIf(b.Not())
                is_tied[t1][t2] = b
                is_tied[t2][t1] = b

        # Step 3: For each team, compute mini_league_points
        # mini_league_points[t1] = sum over T: h2h_points[t1][T] * is_tied[t1][T]
        # This counts only points from matches against teams with the same total points
        mini_league_points: dict[str, cp_model.IntVar] = {}
        max_mini = (n_teams - 1) * max_match_points

        for t1 in team_ids:
            contributions: list[tuple[cp_model.IntVar, int]] = []
            for t2 in team_ids:
                if t1 == t2:
                    continue

                h2h = h2h_points[t1][t2]
                tied = is_tied[t1][t2]

                if isinstance(h2h, int):
                    # Constant h2h * BoolVar tied
                    contributions.append((tied, h2h))
                else:
                    # Variable h2h * BoolVar tied - need intermediate variable
                    prod = model.NewIntVar(0, max_match_points, f"prod_{t1}_{t2}")
                    model.AddMultiplicationEquality(prod, [h2h, tied])
                    contributions.append((prod, 1))

            mini = model.NewIntVar(0, max_mini, f"mini_league_{t1}")
            model.Add(mini == sum(var * coef for var, coef in contributions))
            mini_league_points[t1] = mini

        # Step 3b: Compute game points won/lost in mini-league for each pair
        # gpq_won[t1][t2] = game points won by t1 against t2 (if tied on total pts)
        # gpq_lost[t1][t2] = game points lost by t1 against t2 (if tied on total pts)
        # For game point quotient: sum(gpq_won) / sum(gpq_lost)
        h2h_game_won: dict[str, dict[str, int]] = {t: {} for t in team_ids}
        h2h_game_lost: dict[str, dict[str, int]] = {t: {} for t in team_ids}

        for t1 in team_ids:
            for t2 in team_ids:
                if t1 == t2:
                    h2h_game_won[t1][t2] = 0
                    h2h_game_lost[t1][t2] = 0
                    continue

                match, _ = self._find_match_between(t1_id=t1, t2_id=t2, state=state)
                if match is None:
                    h2h_game_won[t1][t2] = 0
                    h2h_game_lost[t1][t2] = 0
                else:
                    won, lost = self._game_points_for_team_in_match(
                        team_id=t1, match=match, state=state
                    )
                    h2h_game_won[t1][t2] = won
                    h2h_game_lost[t1][t2] = lost

        # Compute mini-league game points for each team
        # Only count matches against teams with equal total points
        max_game_points_per_match = 20  # Maximum game points in one match
        max_mini_game = (n_teams - 1) * max_game_points_per_match

        mini_game_won: dict[str, cp_model.IntVar] = {}
        mini_game_lost: dict[str, cp_model.IntVar] = {}

        for t1 in team_ids:
            won_contributions: list[tuple[cp_model.IntVar, int]] = []
            lost_contributions: list[tuple[cp_model.IntVar, int]] = []

            for t2 in team_ids:
                if t1 == t2:
                    continue

                tied = is_tied[t1][t2]
                gw = h2h_game_won[t1][t2]
                gl = h2h_game_lost[t1][t2]

                # Only count if tied on total points
                won_contributions.append((tied, gw))
                lost_contributions.append((tied, gl))

            mini_won = model.NewIntVar(0, max_mini_game, f"mini_game_won_{t1}")
            mini_lost = model.NewIntVar(0, max_mini_game, f"mini_game_lost_{t1}")

            model.Add(mini_won == sum(var * coef for var, coef in won_contributions))
            model.Add(mini_lost == sum(var * coef for var, coef in lost_contributions))

            mini_game_won[t1] = mini_won
            mini_game_lost[t1] = mini_lost

        # Step 4: Position constraints
        # We use recursive mini-leagues to break ties:
        # Level 0: Total points
        # Level 1: Mini-league points among teams tied on total points
        # Level 1 quotient: Game point quotient in mini-league
        # Level 2: Sub-mini-league points among teams tied through level 1 quotient
        # Level 2 quotient: Game point quotient in sub-mini-league
        # ... and so on until no more ties or recursion stops

        # Track which pairs are tied at each level
        # is_tied_level[level][t1][t2] = True iff t1 and t2 are tied through that level
        is_tied_level: list[dict[str, dict[str, cp_model.IntVar]]] = []

        # Level 0: tied on total points
        is_tied_level.append(is_tied)

        # We'll compute 2 levels of recursion (should handle most practical cases)
        # Each level computes: mini-league points, then quotient, then next level tied set
        num_tiebreaker_levels = 2

        # Store mini-league points and quotients for each level
        level_mini_points: list[dict[str, cp_model.IntVar]] = [mini_league_points]
        level_game_won: list[dict[str, cp_model.IntVar]] = [mini_game_won]
        level_game_lost: list[dict[str, cp_model.IntVar]] = [mini_game_lost]

        for level in range(1, num_tiebreaker_levels + 1):
            prev_tied = is_tied_level[level - 1]
            prev_mini = level_mini_points[level - 1]
            prev_won = level_game_won[level - 1]
            prev_lost = level_game_lost[level - 1]

            # Compute is_tied_mini for this level (tied on prev level AND same mini points)
            is_tied_mini_level: dict[str, dict[str, cp_model.IntVar]] = {
                t: {} for t in team_ids
            }
            for idx, t1 in enumerate(team_ids):
                for t2 in team_ids[idx + 1 :]:
                    b_same_mini = model.NewBoolVar(f"same_mini_L{level}_{t1}_{t2}")
                    model.Add(prev_mini[t1] == prev_mini[t2]).OnlyEnforceIf(b_same_mini)
                    model.Add(prev_mini[t1] != prev_mini[t2]).OnlyEnforceIf(
                        b_same_mini.Not()
                    )

                    b_tied_mini = model.NewBoolVar(f"tied_mini_L{level}_{t1}_{t2}")
                    model.AddBoolAnd([prev_tied[t1][t2], b_same_mini]).OnlyEnforceIf(
                        b_tied_mini
                    )
                    model.AddBoolOr(
                        [prev_tied[t1][t2].Not(), b_same_mini.Not()]
                    ).OnlyEnforceIf(b_tied_mini.Not())

                    is_tied_mini_level[t1][t2] = b_tied_mini
                    is_tied_mini_level[t2][t1] = b_tied_mini

            # Compute is_tied_quotient for this level (tied on mini AND same quotient)
            # Quotient comparison: won1/lost1 == won2/lost2 iff won1*lost2 == won2*lost1
            is_tied_quotient_level: dict[str, dict[str, cp_model.IntVar]] = {
                t: {} for t in team_ids
            }
            for idx, t1 in enumerate(team_ids):
                for t2 in team_ids[idx + 1 :]:
                    cross_t1 = model.NewIntVar(
                        0, max_mini_game * max_mini_game, f"cross_L{level}_{t1}_{t2}"
                    )
                    model.AddMultiplicationEquality(
                        cross_t1, [prev_won[t1], prev_lost[t2]]
                    )

                    cross_t2 = model.NewIntVar(
                        0, max_mini_game * max_mini_game, f"cross_L{level}_{t2}_{t1}"
                    )
                    model.AddMultiplicationEquality(
                        cross_t2, [prev_won[t2], prev_lost[t1]]
                    )

                    b_same_quotient = model.NewBoolVar(f"same_gpq_L{level}_{t1}_{t2}")
                    model.Add(cross_t1 == cross_t2).OnlyEnforceIf(b_same_quotient)
                    model.Add(cross_t1 != cross_t2).OnlyEnforceIf(b_same_quotient.Not())

                    b_tied_quotient = model.NewBoolVar(f"tied_gpq_L{level}_{t1}_{t2}")
                    model.AddBoolAnd(
                        [is_tied_mini_level[t1][t2], b_same_quotient]
                    ).OnlyEnforceIf(b_tied_quotient)
                    model.AddBoolOr(
                        [is_tied_mini_level[t1][t2].Not(), b_same_quotient.Not()]
                    ).OnlyEnforceIf(b_tied_quotient.Not())

                    is_tied_quotient_level[t1][t2] = b_tied_quotient
                    is_tied_quotient_level[t2][t1] = b_tied_quotient

            is_tied_level.append(is_tied_quotient_level)

            # Compute sub-mini-league points for this level
            # Points only from matches against teams tied through quotient
            sub_mini_points: dict[str, cp_model.IntVar] = {}
            for t1 in team_ids:
                contributions: list[tuple[cp_model.IntVar, int]] = []
                for t2 in team_ids:
                    if t1 == t2:
                        continue
                    h2h = h2h_points[t1][t2]
                    tied_q = is_tied_quotient_level[t1][t2]
                    if isinstance(h2h, int):
                        contributions.append((tied_q, h2h))
                    else:
                        prod = model.NewIntVar(
                            0, max_match_points, f"prod_L{level}_{t1}_{t2}"
                        )
                        model.AddMultiplicationEquality(prod, [h2h, tied_q])
                        contributions.append((prod, 1))

                sub_mini = model.NewIntVar(0, max_mini, f"sub_mini_L{level}_{t1}")
                model.Add(sub_mini == sum(var * coef for var, coef in contributions))
                sub_mini_points[t1] = sub_mini

            level_mini_points.append(sub_mini_points)

            # Compute sub-mini-league game points for this level
            sub_game_won: dict[str, cp_model.IntVar] = {}
            sub_game_lost: dict[str, cp_model.IntVar] = {}
            for t1 in team_ids:
                won_contributions: list[tuple[cp_model.IntVar, int]] = []
                lost_contributions: list[tuple[cp_model.IntVar, int]] = []
                for t2 in team_ids:
                    if t1 == t2:
                        continue
                    tied_q = is_tied_quotient_level[t1][t2]
                    gw = h2h_game_won[t1][t2]
                    gl = h2h_game_lost[t1][t2]
                    won_contributions.append((tied_q, gw))
                    lost_contributions.append((tied_q, gl))

                sub_won = model.NewIntVar(0, max_mini_game, f"sub_won_L{level}_{t1}")
                sub_lost = model.NewIntVar(0, max_mini_game, f"sub_lost_L{level}_{t1}")
                model.Add(sub_won == sum(var * coef for var, coef in won_contributions))
                model.Add(
                    sub_lost == sum(var * coef for var, coef in lost_contributions)
                )
                sub_game_won[t1] = sub_won
                sub_game_lost[t1] = sub_lost

            level_game_won.append(sub_game_won)
            level_game_lost.append(sub_game_lost)

        # Now add position constraints using all levels
        for i, t1 in enumerate(team_ids):
            for t2 in team_ids[i + 1 :]:
                # If t1 has more total points, t1 ranks higher
                b_t1_better_pts = model.NewBoolVar(f"{t1}_more_pts_{t2}")
                model.Add(team_points[t1] > team_points[t2]).OnlyEnforceIf(
                    b_t1_better_pts
                )
                model.Add(team_points[t1] <= team_points[t2]).OnlyEnforceIf(
                    b_t1_better_pts.Not()
                )
                model.Add(team_positions[t1] < team_positions[t2]).OnlyEnforceIf(
                    b_t1_better_pts
                )

                b_t2_better_pts = model.NewBoolVar(f"{t2}_more_pts_{t1}")
                model.Add(team_points[t2] > team_points[t1]).OnlyEnforceIf(
                    b_t2_better_pts
                )
                model.Add(team_points[t2] <= team_points[t1]).OnlyEnforceIf(
                    b_t2_better_pts.Not()
                )
                model.Add(team_positions[t2] < team_positions[t1]).OnlyEnforceIf(
                    b_t2_better_pts
                )

                # For each tiebreaker level, add constraints
                prev_tied_cond = is_tied[t1][t2]

                for level in range(num_tiebreaker_levels + 1):
                    mini_pts = level_mini_points[level]
                    game_won = level_game_won[level]
                    game_lost = level_game_lost[level]

                    # t1 has more mini-league points at this level
                    b_t1_better_mini = model.NewBoolVar(f"{t1}_more_mini_L{level}_{t2}")
                    model.Add(mini_pts[t1] > mini_pts[t2]).OnlyEnforceIf(
                        b_t1_better_mini
                    )
                    model.Add(mini_pts[t1] <= mini_pts[t2]).OnlyEnforceIf(
                        b_t1_better_mini.Not()
                    )

                    b_tied_and_t1_better = model.NewBoolVar(
                        f"tied_and_{t1}_better_mini_L{level}_{t2}"
                    )
                    model.AddBoolAnd([prev_tied_cond, b_t1_better_mini]).OnlyEnforceIf(
                        b_tied_and_t1_better
                    )
                    model.AddBoolOr(
                        [prev_tied_cond.Not(), b_t1_better_mini.Not()]
                    ).OnlyEnforceIf(b_tied_and_t1_better.Not())
                    model.Add(team_positions[t1] < team_positions[t2]).OnlyEnforceIf(
                        b_tied_and_t1_better
                    )

                    # t2 has more mini-league points at this level
                    b_t2_better_mini = model.NewBoolVar(f"{t2}_more_mini_L{level}_{t1}")
                    model.Add(mini_pts[t2] > mini_pts[t1]).OnlyEnforceIf(
                        b_t2_better_mini
                    )
                    model.Add(mini_pts[t2] <= mini_pts[t1]).OnlyEnforceIf(
                        b_t2_better_mini.Not()
                    )

                    b_tied_and_t2_better = model.NewBoolVar(
                        f"tied_and_{t2}_better_mini_L{level}_{t1}"
                    )
                    model.AddBoolAnd([prev_tied_cond, b_t2_better_mini]).OnlyEnforceIf(
                        b_tied_and_t2_better
                    )
                    model.AddBoolOr(
                        [prev_tied_cond.Not(), b_t2_better_mini.Not()]
                    ).OnlyEnforceIf(b_tied_and_t2_better.Not())
                    model.Add(team_positions[t2] < team_positions[t1]).OnlyEnforceIf(
                        b_tied_and_t2_better
                    )

                    # Tied on mini-league points, check quotient
                    b_tied_mini = model.NewBoolVar(f"tied_mini_L{level}_{t1}_{t2}_cmp")
                    model.Add(mini_pts[t1] == mini_pts[t2]).OnlyEnforceIf(b_tied_mini)
                    model.Add(mini_pts[t1] != mini_pts[t2]).OnlyEnforceIf(
                        b_tied_mini.Not()
                    )

                    b_tied_through_mini = model.NewBoolVar(
                        f"tied_through_mini_L{level}_{t1}_{t2}"
                    )
                    model.AddBoolAnd([prev_tied_cond, b_tied_mini]).OnlyEnforceIf(
                        b_tied_through_mini
                    )
                    model.AddBoolOr(
                        [prev_tied_cond.Not(), b_tied_mini.Not()]
                    ).OnlyEnforceIf(b_tied_through_mini.Not())

                    # Cross-products for game point quotient
                    cross_t1 = model.NewIntVar(
                        0,
                        max_mini_game * max_mini_game,
                        f"cross_cmp_L{level}_{t1}_{t2}",
                    )
                    model.AddMultiplicationEquality(
                        cross_t1, [game_won[t1], game_lost[t2]]
                    )

                    cross_t2 = model.NewIntVar(
                        0,
                        max_mini_game * max_mini_game,
                        f"cross_cmp_L{level}_{t2}_{t1}",
                    )
                    model.AddMultiplicationEquality(
                        cross_t2, [game_won[t2], game_lost[t1]]
                    )

                    # t1 has better quotient
                    b_t1_better_gpq = model.NewBoolVar(f"{t1}_better_gpq_L{level}_{t2}")
                    model.Add(cross_t1 > cross_t2).OnlyEnforceIf(b_t1_better_gpq)
                    model.Add(cross_t1 <= cross_t2).OnlyEnforceIf(b_t1_better_gpq.Not())

                    b_tied_mini_and_t1_gpq = model.NewBoolVar(
                        f"tied_mini_and_{t1}_gpq_L{level}_{t2}"
                    )
                    model.AddBoolAnd(
                        [b_tied_through_mini, b_t1_better_gpq]
                    ).OnlyEnforceIf(b_tied_mini_and_t1_gpq)
                    model.AddBoolOr(
                        [b_tied_through_mini.Not(), b_t1_better_gpq.Not()]
                    ).OnlyEnforceIf(b_tied_mini_and_t1_gpq.Not())
                    model.Add(team_positions[t1] < team_positions[t2]).OnlyEnforceIf(
                        b_tied_mini_and_t1_gpq
                    )

                    # t2 has better quotient
                    b_t2_better_gpq = model.NewBoolVar(f"{t2}_better_gpq_L{level}_{t1}")
                    model.Add(cross_t2 > cross_t1).OnlyEnforceIf(b_t2_better_gpq)
                    model.Add(cross_t2 <= cross_t1).OnlyEnforceIf(b_t2_better_gpq.Not())

                    b_tied_mini_and_t2_gpq = model.NewBoolVar(
                        f"tied_mini_and_{t2}_gpq_L{level}_{t1}"
                    )
                    model.AddBoolAnd(
                        [b_tied_through_mini, b_t2_better_gpq]
                    ).OnlyEnforceIf(b_tied_mini_and_t2_gpq)
                    model.AddBoolOr(
                        [b_tied_through_mini.Not(), b_t2_better_gpq.Not()]
                    ).OnlyEnforceIf(b_tied_mini_and_t2_gpq.Not())
                    model.Add(team_positions[t2] < team_positions[t1]).OnlyEnforceIf(
                        b_tied_mini_and_t2_gpq
                    )

                    # Update prev_tied_cond for next level
                    if level < num_tiebreaker_levels:
                        prev_tied_cond = is_tied_level[level + 1][t1][t2]

        return team_positions

    def _apply_constraints(
        self,
        model: cp_model.CpModel,
        constraints: list[Constraint],
        match_vars: dict[Match, dict[MatchResult, cp_model.IntVar]],
        team_points: dict[str, cp_model.IntVar],
        team_positions: dict[str, cp_model.IntVar],
        state: ChampionshipState,
    ) -> None:
        """
        Apply user-specified constraints to the model.
        """

        for constraint in constraints:
            if isinstance(constraint, TeamPositionConstraint):
                pos = team_positions[constraint.team_id]
                if constraint.min_position:
                    model.Add(pos >= constraint.min_position)
                if constraint.max_position:
                    model.Add(pos <= constraint.max_position)

            elif isinstance(constraint, MatchResultConstraint):
                if constraint.match in match_vars:
                    model.Add(match_vars[constraint.match][constraint.result] == 1)

            elif isinstance(constraint, TeamMinPointsConstraint):
                model.Add(team_points[constraint.team_id] >= constraint.min_points)

            elif isinstance(constraint, NoForfeitConstraint):
                for outcomes in match_vars.values():
                    model.Add(outcomes[MatchResult.HOME_FORFEIT] == 0)
                    model.Add(outcomes[MatchResult.AWAY_FORFEIT] == 0)

            else:
                raise ValueError(f"Unknown constraint type: {type(constraint)}")

    def _extract_scenario(
        self,
        solver: cp_model.CpSolver,
        match_vars: dict[Match, dict[MatchResult, cp_model.IntVar]],
        team_points: dict[str, cp_model.IntVar],
        team_positions: dict[str, cp_model.IntVar],
        state: ChampionshipState,
    ) -> Scenario:
        """
        Extract a scenario from a solved model.
        """

        # Get match results
        results = {}
        for match, outcome_vars in match_vars.items():
            for result, var in outcome_vars.items():
                if solver.Value(var) == 1:
                    results[match] = CompletedMatch(result=result)
                    break

        # Get standings
        standings = []
        for team in state.teams:
            standings.append(
                Standing(
                    team_id=team.id,
                    points=solver.Value(team_points[team.id]),
                    position=solver.Value(team_positions[team.id]),
                )
            )

        standings.sort(key=lambda s: s.position)
        return Scenario(match_results=results, standings=standings)

    def find_scenario(
        self,
        rules: Rules,
        state: ChampionshipState,
        team_id: str | None = None,
        optimize_position: str | None = None,
        constraints: list[Constraint] | None = None,
    ) -> Scenario | None:
        """
        Find a scenario matching the given constraints.

        Returns `None` if no scenario is possible.
        """

        model = cp_model.CpModel()
        constraints = constraints or []

        # Build the model
        match_vars, team_points = self._build_model(
            model=model, rules=rules, state=state
        )

        # Position variables for each team
        team_positions = self._add_position_variables(
            model=model,
            state=state,
            team_points=team_points,
            match_vars=match_vars,
            rules=rules,
        )

        # Apply user constraints
        self._apply_constraints(
            model=model,
            constraints=constraints,
            match_vars=match_vars,
            team_points=team_points,
            team_positions=team_positions,
            state=state,
        )

        # Optimization objective
        if team_id and optimize_position:
            if optimize_position == "best":
                # Minimize position (1 is best)
                model.Minimize(team_positions[team_id])
            elif optimize_position == "worst":
                # Maximize position
                model.Maximize(team_positions[team_id])

        # Solve
        solver = self._create_solver()
        status = solver.Solve(model)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return self._extract_scenario(
                solver=solver,
                match_vars=match_vars,
                team_points=team_points,
                team_positions=team_positions,
                state=state,
            )
        return None

    def find_all_scenarios(
        self,
        rules: Rules,
        state: ChampionshipState,
        constraints: list[Constraint] | None = None,
        limit: int | None = None,
    ) -> list[Scenario]:
        model = cp_model.CpModel()
        constraints = constraints or []

        match_vars, team_points = self._build_model(
            model=model, rules=rules, state=state
        )
        team_positions = self._add_position_variables(
            model=model,
            state=state,
            team_points=team_points,
            match_vars=match_vars,
            rules=rules,
        )
        self._apply_constraints(
            model=model,
            constraints=constraints,
            match_vars=match_vars,
            team_points=team_points,
            team_positions=team_positions,
            state=state,
        )

        solver = self._create_solver()
        collector = _SolutionCollector(
            match_vars=match_vars,
            team_points=team_points,
            team_positions=team_positions,
            state=state,
            limit=limit,
        )
        solver.parameters.enumerate_all_solutions = True
        solver.Solve(model, collector)

        return collector.scenarios
