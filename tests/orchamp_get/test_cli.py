from .util import STANDINGS_PATH, run_cli_raw, run_parse


class TestParse:
    def test_parse_d3_ph1_2025_26(self) -> None:
        result = run_parse(STANDINGS_PATH)

        assert len(result["teams"]) == 7
        assert len(result["completed_matches"]) == 15
        assert len(result["remaining_matches"]) == 6

    def test_parse_nonexistent_file(self) -> None:
        result = run_cli_raw("parse", "/nonexistent/file.html")

        assert result.returncode != 0
        assert "error" in result.stderr


class TestInvalidSubcommand:
    def test_nonexistent_subcommand(self) -> None:
        result = run_cli_raw("nonexistent")

        assert result.returncode != 0
        assert "invalid choice" in result.stderr
