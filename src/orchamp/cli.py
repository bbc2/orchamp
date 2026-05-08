import argparse
import json
import sys
from pathlib import Path
from typing import Any

from orchamp.analyzer import Analyzer
from orchamp.models import (
    ChampionshipState,
    Rules,
    Scenario,
)
from orchamp.ranking import compute_rankings
from orchamp.solvers.cpsat import CpSatSolver


def _scenario_to_dict(scenario: Scenario, state: ChampionshipState) -> dict[str, Any]:
    """
    Convert a Scenario to a JSON-serializable dict.
    """

    return {
        "standings": [
            {
                "position": s.position,
                "team_id": s.team_id,
                "team_name": state.team_by_id(s.team_id).name
                if state.team_by_id(s.team_id)
                else s.team_id,
                "points": s.points,
            }
            for s in scenario.standings
        ],
        "match_results": [
            {"home": m.home, "away": m.away, "result": c.result.value}
            for m, c in scenario.match_results.items()
        ],
    }


def cmd_analyze_team(
    analyzer: Analyzer,
    rules: Rules,
    state: ChampionshipState,
    team_id: str,
    allow_forfeits: bool = True,
) -> int:
    team = state.team_by_id(team_id)
    analysis = analyzer.analyze_team_position(
        rules=rules,
        state=state,
        team_id=team_id,
        allow_forfeits=allow_forfeits,
    )

    if not analysis:
        print(json.dumps({"error": "No valid scenarios found"}, ensure_ascii=False))
        return 1

    result = {
        "team_id": team_id,
        "team_name": team.name,
        "best_position": analysis.best_position,
        "worst_position": analysis.worst_position,
        "best_scenario": _scenario_to_dict(analysis.best_scenario, state),
        "worst_scenario": _scenario_to_dict(analysis.worst_scenario, state),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_who_can_win(
    analyzer: Analyzer,
    rules: Rules,
    state: ChampionshipState,
    allow_forfeits: bool = True,
) -> int:
    analysis = analyzer.find_possible_winners(
        rules=rules, state=state, allow_forfeits=allow_forfeits
    )

    result = {
        "possible_winners": analysis.possible_winners,
        "example_scenarios": {
            team_id: _scenario_to_dict(scenario, state)
            for team_id, scenario in analysis.scenarios_by_winner.items()
        },
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_what_must_happen(
    analyzer: Analyzer,
    rules: Rules,
    state: ChampionshipState,
    team_id: str,
    position: int,
    allow_forfeits: bool = True,
) -> int:
    team = state.team_by_id(team_id)
    if not team:
        print(json.dumps({"error": f"Team '{team_id}' not found"}, ensure_ascii=False))
        return 1

    # First check if it's possible
    scenario = analyzer.can_team_achieve_position(
        rules=rules,
        state=state,
        team_id=team_id,
        position=position,
        allow_forfeits=allow_forfeits,
    )
    required = (
        analyzer.what_must_happen(
            rules=rules,
            state=state,
            team_id=team_id,
            target_position=position,
            allow_forfeits=allow_forfeits,
        )
        if scenario
        else []
    )

    result: dict[str, Any] = {
        "team_id": team_id,
        "team_name": team.name,
        "target_position": position,
        "achievable": scenario is not None,
        "required_results": [
            {
                "home": r.match.home,
                "away": r.match.away,
                "result": r.required_result.value,
            }
            for r in required
        ],
    }
    if scenario:
        result["example_scenario"] = _scenario_to_dict(scenario, state)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_standings(rules: Rules, state: ChampionshipState) -> int:
    """
    Show current standings based on completed matches with tiebreakers applied.
    """

    rankings = compute_rankings(state, rules)
    result_data = {
        "standings": [
            {
                "position": r.position,
                "team_id": r.team_id,
                "team_name": r.team_name,
                "points": r.points,
            }
            for r in rankings
        ],
        "completed_matches": len(state.completed_matches),
        "remaining_matches": len(state.remaining_matches),
        "rounds": [
            {
                "name": round_.name,
                "date": round_.date,
                "matches": [
                    {
                        "home": match.home,
                        "home_name": state.team_by_id(match.home).name,
                        "away": match.away,
                        "away_name": state.team_by_id(match.away).name,
                        "completed": match in state.completed_matches,
                    }
                    for match in round_.matches
                ],
            }
            for round_ in state.rounds
        ],
    }
    print(json.dumps(result_data, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="orchamp",
        description="Analyze table tennis championship possibilities",
    )
    parser.add_argument(
        "--rules",
        type=Path,
        required=True,
        help="Path to JSON file with championship rules",
    )
    parser.add_argument(
        "--state",
        type=Path,
        required=True,
        help="Path to JSON file with current championship state",
    )
    parser.add_argument(
        "--cpsat-random-seed",
        type=int,
        help="Random seed for CP-SAT solver (for reproducibility)",
    )
    parser.add_argument(
        "--cpsat-num-workers",
        type=int,
        help="Number of workers for CP-SAT solver (default: all cores)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # analyze-team command
    team_parser = subparsers.add_parser(
        "analyze-team",
        help="Analyze a team's possible positions",
    )
    team_parser.add_argument("--team", required=True, help="Team ID to analyze")
    team_parser.add_argument(
        "--no-forfeit",
        action="store_true",
        help="Exclude forfeit outcomes from analysis",
    )

    # who-can-win command
    wcw_parser = subparsers.add_parser(
        "who-can-win",
        help="Find all teams that can still win",
    )
    wcw_parser.add_argument(
        "--no-forfeit",
        action="store_true",
        help="Exclude forfeit outcomes from analysis",
    )

    # what-must-happen command
    wmh_parser = subparsers.add_parser(
        "what-must-happen",
        help="Find what must happen for a team to achieve a position",
    )
    wmh_parser.add_argument("--team", required=True, help="Team ID")
    wmh_parser.add_argument(
        "--position", type=int, required=True, help="Target position (1=first)"
    )
    wmh_parser.add_argument(
        "--no-forfeit",
        action="store_true",
        help="Exclude forfeit outcomes from analysis",
    )

    # standings command
    subparsers.add_parser(
        "standings",
        help="Show current standings based on completed matches",
    )

    args = parser.parse_args()

    # Load rules
    with open(args.rules) as f:
        rules = Rules.from_dict(json.load(f))

    # Load state
    with open(args.state) as f:
        state = ChampionshipState.from_dict(json.load(f))

    analyzer = Analyzer(
        solver=CpSatSolver(
            random_seed=args.cpsat_random_seed,
            num_workers=args.cpsat_num_workers,
        )
    )

    # Determine allow_forfeits from CLI flag
    allow_forfeits = not (hasattr(args, "no_forfeit") and args.no_forfeit)

    if args.command == "analyze-team":
        return cmd_analyze_team(
            analyzer=analyzer,
            rules=rules,
            state=state,
            team_id=args.team,
            allow_forfeits=allow_forfeits,
        )
    elif args.command == "who-can-win":
        return cmd_who_can_win(
            analyzer=analyzer,
            rules=rules,
            state=state,
            allow_forfeits=allow_forfeits,
        )
    elif args.command == "what-must-happen":
        return cmd_what_must_happen(
            analyzer=analyzer,
            rules=rules,
            state=state,
            team_id=args.team,
            position=args.position,
            allow_forfeits=allow_forfeits,
        )
    elif args.command == "standings":
        return cmd_standings(rules=rules, state=state)

    return 0


if __name__ == "__main__":
    sys.exit(main())
