from inline_snapshot import snapshot

from .util import RULES_PATH, SMALL_LEAGUE_PATH, run_standings


class TestStandings:
    def test_standings(self):
        result = run_standings(rules=RULES_PATH, state=SMALL_LEAGUE_PATH)

        assert result == snapshot(
            {
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
                        "points": 2,
                    },
                    {
                        "position": 4,
                        "team_id": "delta",
                        "team_name": "Delta Spin",
                        "points": 0,
                    },
                ],
                "completed_matches": 3,
                "remaining_matches": 3,
            }
        )
