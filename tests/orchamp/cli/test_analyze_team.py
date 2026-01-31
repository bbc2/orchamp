from inline_snapshot import snapshot

from .util import RULES_PATH, SMALL_LEAGUE_PATH, run_analyze_team


class TestAnalyzeTeam:
    def test_analyze_delta(self):
        result = run_analyze_team(
            team_id="delta", rules=RULES_PATH, state=SMALL_LEAGUE_PATH
        )

        assert result == snapshot(
            {
                "team_id": "delta",
                "team_name": "Delta Spin",
                "best_position": 1,
                "worst_position": 4,
                "best_scenario": {
                    "standings": [
                        {
                            "position": 1,
                            "team_id": "delta",
                            "team_name": "Delta Spin",
                            "points": 6,
                        },
                        {
                            "position": 2,
                            "team_id": "gamma",
                            "team_name": "Gamma Smash",
                            "points": 6,
                        },
                        {
                            "position": 3,
                            "team_id": "alpha",
                            "team_name": "Alpha TTC",
                            "points": 5,
                        },
                        {
                            "position": 4,
                            "team_id": "beta",
                            "team_name": "Beta Ping",
                            "points": 5,
                        },
                    ],
                    "match_results": [
                        {"home": "alpha", "away": "delta", "result": "home_forfeit"},
                        {"home": "beta", "away": "delta", "result": "home_win"},
                        {"home": "gamma", "away": "delta", "result": "away_win"},
                    ],
                },
                "worst_scenario": {
                    "standings": [
                        {
                            "position": 1,
                            "team_id": "alpha",
                            "team_name": "Alpha TTC",
                            "points": 8,
                        },
                        {
                            "position": 2,
                            "team_id": "gamma",
                            "team_name": "Gamma Smash",
                            "points": 7,
                        },
                        {
                            "position": 3,
                            "team_id": "beta",
                            "team_name": "Beta Ping",
                            "points": 4,
                        },
                        {
                            "position": 4,
                            "team_id": "delta",
                            "team_name": "Delta Spin",
                            "points": 3,
                        },
                    ],
                    "match_results": [
                        {"home": "alpha", "away": "delta", "result": "home_win"},
                        {"home": "beta", "away": "delta", "result": "away_forfeit"},
                        {"home": "gamma", "away": "delta", "result": "draw"},
                    ],
                },
            }
        )
