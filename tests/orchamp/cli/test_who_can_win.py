from inline_snapshot import snapshot

from .util import RULES_PATH, SMALL_LEAGUE_PATH, run_who_can_win


class TestWhoCanWin:
    def test_who_can_win(self):
        result = run_who_can_win(rules=RULES_PATH, state=SMALL_LEAGUE_PATH)

        assert result == snapshot(
            {
                "possible_winners": ["alpha", "beta", "gamma", "delta"],
                "example_scenarios": {
                    "alpha": {
                        "standings": [
                            {
                                "position": 1,
                                "team_id": "alpha",
                                "team_name": "Alpha TTC",
                                "points": 5,
                            },
                            {
                                "position": 2,
                                "team_id": "gamma",
                                "team_name": "Gamma Smash",
                                "points": 5,
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
                                "points": 4,
                            },
                        ],
                        "match_results": [
                            {
                                "home": "alpha",
                                "away": "delta",
                                "result": "home_forfeit",
                            },
                            {"home": "beta", "away": "delta", "result": "away_forfeit"},
                            {
                                "home": "gamma",
                                "away": "delta",
                                "result": "home_forfeit",
                            },
                        ],
                    },
                    "beta": {
                        "standings": [
                            {
                                "position": 1,
                                "team_id": "beta",
                                "team_name": "Beta Ping",
                                "points": 5,
                            },
                            {
                                "position": 2,
                                "team_id": "gamma",
                                "team_name": "Gamma Smash",
                                "points": 5,
                            },
                            {
                                "position": 3,
                                "team_id": "alpha",
                                "team_name": "Alpha TTC",
                                "points": 5,
                            },
                            {
                                "position": 4,
                                "team_id": "delta",
                                "team_name": "Delta Spin",
                                "points": 5,
                            },
                        ],
                        "match_results": [
                            {
                                "home": "alpha",
                                "away": "delta",
                                "result": "home_forfeit",
                            },
                            {"home": "beta", "away": "delta", "result": "home_win"},
                            {
                                "home": "gamma",
                                "away": "delta",
                                "result": "home_forfeit",
                            },
                        ],
                    },
                    "gamma": {
                        "standings": [
                            {
                                "position": 1,
                                "team_id": "gamma",
                                "team_name": "Gamma Smash",
                                "points": 8,
                            },
                            {
                                "position": 2,
                                "team_id": "alpha",
                                "team_name": "Alpha TTC",
                                "points": 6,
                            },
                            {
                                "position": 3,
                                "team_id": "beta",
                                "team_name": "Beta Ping",
                                "points": 5,
                            },
                            {
                                "position": 4,
                                "team_id": "delta",
                                "team_name": "Delta Spin",
                                "points": 5,
                            },
                        ],
                        "match_results": [
                            {
                                "home": "alpha",
                                "away": "delta",
                                "result": "away_win",
                            },
                            {"home": "beta", "away": "delta", "result": "home_win"},
                            {"home": "gamma", "away": "delta", "result": "home_win"},
                        ],
                    },
                    "delta": {
                        "standings": [
                            {
                                "position": 1,
                                "team_id": "delta",
                                "team_name": "Delta Spin",
                                "points": 7,
                            },
                            {
                                "position": 2,
                                "team_id": "alpha",
                                "team_name": "Alpha TTC",
                                "points": 7,
                            },
                            {
                                "position": 3,
                                "team_id": "gamma",
                                "team_name": "Gamma Smash",
                                "points": 6,
                            },
                            {
                                "position": 4,
                                "team_id": "beta",
                                "team_name": "Beta Ping",
                                "points": 4,
                            },
                        ],
                        "match_results": [
                            {
                                "home": "alpha",
                                "away": "delta",
                                "result": "draw",
                            },
                            {"home": "beta", "away": "delta", "result": "draw"},
                            {
                                "home": "gamma",
                                "away": "delta",
                                "result": "away_win",
                            },
                        ],
                    },
                },
            }
        )
