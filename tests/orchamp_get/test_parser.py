from inline_snapshot import snapshot

from orchamp_get.parser import parse_html

from .util import STANDINGS_PATH


class TestParseHtml:
    def test_parse_d3_ph1_2025_26_teams(self) -> None:
        with open(STANDINGS_PATH, encoding="utf-8") as f:
            html = f.read()

        result = parse_html(html)

        assert result["teams"] == snapshot(
            [
                {"id": "team_a", "name": "Team A"},
                {"id": "team_b", "name": "Team B"},
                {"id": "team_c", "name": "Team C"},
                {"id": "team_d", "name": "Team D"},
                {"id": "team_e", "name": "Team E"},
                {"id": "team_f", "name": "Team F"},
                {"id": "team_g", "name": "Team G"},
            ]
        )

    def test_parse_d3_ph1_2025_26_completed_matches(self) -> None:
        with open(STANDINGS_PATH, encoding="utf-8") as f:
            html = f.read()

        result = parse_html(html)

        assert result["completed_matches"] == snapshot(
            [
                {
                    "home": "team_f",
                    "away": "team_d",
                    "home_score": 16,
                    "away_score": 14,
                    "result": "home_win",
                },
                {
                    "home": "team_c",
                    "away": "team_e",
                    "home_score": 11,
                    "away_score": 16,
                    "result": "away_win",
                },
                {
                    "home": "team_a",
                    "away": "team_g",
                    "home_score": 19,
                    "away_score": 11,
                    "result": "home_win",
                },
                {
                    "home": "team_e",
                    "away": "team_b",
                    "home_score": 11,
                    "away_score": 19,
                    "result": "away_win",
                },
                {
                    "home": "team_g",
                    "away": "team_c",
                    "home_score": 14,
                    "away_score": 16,
                    "result": "away_win",
                },
                {
                    "home": "team_d",
                    "away": "team_a",
                    "home_score": 11,
                    "away_score": 19,
                    "result": "away_win",
                },
                {
                    "home": "team_f",
                    "away": "team_e",
                    "home_score": 11,
                    "away_score": 19,
                    "result": "away_win",
                },
                {
                    "home": "team_b",
                    "away": "team_g",
                    "home_score": 20,
                    "away_score": 10,
                    "result": "home_win",
                },
                {
                    "home": "team_c",
                    "away": "team_a",
                    "home_score": 13,
                    "away_score": 17,
                    "result": "away_win",
                },
                {
                    "home": "team_g",
                    "away": "team_f",
                    "home_score": 19,
                    "away_score": 11,
                    "result": "home_win",
                },
                {
                    "home": "team_a",
                    "away": "team_b",
                    "home_score": 15,
                    "away_score": 15,
                    "result": "draw",
                },
                {
                    "home": "team_c",
                    "away": "team_d",
                    "home_score": 11,
                    "away_score": 19,
                    "result": "away_win",
                },
                {
                    "home": "team_f",
                    "away": "team_a",
                    "home_score": 14,
                    "away_score": 16,
                    "result": "away_win",
                },
                {
                    "home": "team_b",
                    "away": "team_c",
                    "home_score": 15,
                    "away_score": 15,
                    "result": "draw",
                },
                {
                    "home": "team_d",
                    "away": "team_e",
                    "home_score": 17,
                    "away_score": 13,
                    "result": "home_win",
                },
            ]
        )

    def test_parse_d3_ph1_2025_26_remaining_matches(self) -> None:
        with open(STANDINGS_PATH, encoding="utf-8") as f:
            html = f.read()

        result = parse_html(html)

        assert result["remaining_matches"] == snapshot(
            [
                {"home": "team_c", "away": "team_f"},
                {"home": "team_b", "away": "team_d"},
                {"home": "team_g", "away": "team_e"},
                {"home": "team_f", "away": "team_b"},
                {"home": "team_e", "away": "team_a"},
                {"home": "team_d", "away": "team_g"},
            ]
        )
