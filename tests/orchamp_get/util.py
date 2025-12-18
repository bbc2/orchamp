"""
Utility functions for orchamp_get tests.
"""

import importlib.resources
import json
import subprocess
import sys
from typing import Any

DATA_DIR = importlib.resources.files("tests.orchamp_get.data")
STANDINGS_PATH = str(DATA_DIR / "standings.html")


def _run_cli(*args: str) -> dict[str, Any]:
    """
    Run orchamp-get CLI with given arguments and return parsed JSON output.
    """

    cmd = [sys.executable, "-m", "orchamp_get.cli", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"CLI failed: {result.stderr}")
    return json.loads(result.stdout)


def run_parse(file: str) -> dict[str, Any]:
    """
    Run orchamp-get parse command.
    """

    return _run_cli("parse", file)


def run_cli_raw(*args: str) -> subprocess.CompletedProcess[str]:
    """
    Run orchamp-get CLI and return the raw result.
    """

    cmd = [sys.executable, "-m", "orchamp_get.cli", *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)
