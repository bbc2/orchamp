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
                "rounds": [
                    {
                        "name": "R01",
                        "date": "2025-10-01",
                        "matches": [
                            {
                                "home": "alpha",
                                "home_name": "Alpha TTC",
                                "away": "beta",
                                "away_name": "Beta Ping",
                                "completed": True,
                            },
                            {
                                "home": "beta",
                                "home_name": "Beta Ping",
                                "away": "gamma",
                                "away_name": "Gamma Smash",
                                "completed": True,
                            },
                        ],
                    },
                    {
                        "name": "R02",
                        "date": "2025-11-01",
                        "matches": [
                            {
                                "home": "alpha",
                                "home_name": "Alpha TTC",
                                "away": "gamma",
                                "away_name": "Gamma Smash",
                                "completed": True,
                            },
                            {
                                "home": "gamma",
                                "home_name": "Gamma Smash",
                                "away": "delta",
                                "away_name": "Delta Spin",
                                "completed": False,
                            },
                        ],
                    },
                    {
                        "name": "R03",
                        "date": "2025-12-01",
                        "matches": [
                            {
                                "home": "alpha",
                                "home_name": "Alpha TTC",
                                "away": "delta",
                                "away_name": "Delta Spin",
                                "completed": False,
                            },
                            {
                                "home": "beta",
                                "home_name": "Beta Ping",
                                "away": "delta",
                                "away_name": "Delta Spin",
                                "completed": False,
                            },
                        ],
                    },
                ],
            }
        )
