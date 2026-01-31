from inline_snapshot import snapshot

from .util import DATA_DIR, RULES_PATH, SMALL_LEAGUE_PATH, run_what_must_happen


class TestWhatMustHappen:
    def test_achievable_position(self):
        result = run_what_must_happen(
            team_id="delta", position=1, rules=RULES_PATH, state=SMALL_LEAGUE_PATH
        )

        assert result == snapshot(
            {
                "team_id": "delta",
                "team_name": "Delta Spin",
                "target_position": 1,
                "achievable": True,
                "required_results": [],
                "example_scenario": {
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
                        {"home": "alpha", "away": "delta", "result": "draw"},
                        {"home": "beta", "away": "delta", "result": "draw"},
                        {"home": "gamma", "away": "delta", "result": "away_win"},
                    ],
                },
            }
        )

    def test_impossible_position(self):
        """Test what-must-happen for impossible outcome."""
        state = str(DATA_DIR / "impossible_league.json")

        result = run_what_must_happen(
            team_id="B", position=1, rules=RULES_PATH, state=state
        )

        assert result["team_id"] == "B"
        assert result["target_position"] == 1
        assert result["achievable"] is False
        assert "example_scenario" not in result
