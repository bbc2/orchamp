"""
Utility functions for CLI tests.
"""

import importlib.resources
import json
import subprocess
import sys
from typing import Any

DATA_DIR = importlib.resources.files("tests.orchamp.cli.data")
RULES_PATH = str(DATA_DIR / "rules.json")
SMALL_LEAGUE_PATH = str(DATA_DIR / "small_league.json")


def _run_cli(*args: str, rules: str, state: str) -> dict[str, Any]:
    """
    Run orchamp CLI with given arguments and return parsed JSON output.
    """

    cmd = [
        sys.executable,
        "-m",
        "orchamp.cli",
        "--rules",
        rules,
        "--state",
        state,
        "--cpsat-random-seed",
        "42",
        "--cpsat-num-workers",
        "1",
        *args,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    return json.loads(result.stdout)


def run_standings(rules: str, state: str) -> dict[str, Any]:
    return _run_cli("standings", rules=rules, state=state)


def run_analyze_team(team_id: str, rules: str, state: str) -> dict[str, Any]:
    return _run_cli("analyze-team", "--team", team_id, rules=rules, state=state)


def run_who_can_win(rules: str, state: str) -> dict[str, Any]:
    return _run_cli("who-can-win", rules=rules, state=state)


def run_what_must_happen(
    team_id: str, position: int, rules: str, state: str
) -> dict[str, Any]:
    return _run_cli(
        "what-must-happen",
        "--team",
        team_id,
        "--position",
        str(position),
        rules=rules,
        state=state,
    )
