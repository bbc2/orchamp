"""
Assumption parsing, serialization, and display types for the standings pages.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AssumptionEntry:
    """
    A single user-supplied assumption: a pending match with an assumed score.
    """

    home_id: str
    away_id: str
    home_score: int
    away_score: int


@dataclass(frozen=True)
class AssumptionDisplay:
    """
    An assumption enriched with team names for display.
    """

    home_id: str
    home_name: str
    away_id: str
    away_name: str
    home_score: int
    away_score: int


def parse_assumptions(raw: list[str]) -> list[AssumptionEntry]:
    """
    Parse and validate a list of raw ``?a=`` query-parameter values.

    Each value must be ``"home_id:away_id:home_score:away_score"``.
    Malformed or out-of-range entries are silently dropped.
    """

    result = []
    for s in raw:
        parts = s.split(":")
        if len(parts) != 4:
            continue
        try:
            home_score = int(parts[2])
            away_score = int(parts[3])
        except ValueError:
            continue
        if not (0 <= home_score <= 20) or not (0 <= away_score <= 20):
            continue
        result.append(
            AssumptionEntry(
                home_id=parts[0],
                away_id=parts[1],
                home_score=home_score,
                away_score=away_score,
            )
        )
    return result


def serialize_assumption(entry: AssumptionEntry) -> str:
    """
    Serialize an assumption to a ``?a=`` query-parameter value.
    """

    return f"{entry.home_id}:{entry.away_id}:{entry.home_score}:{entry.away_score}"
