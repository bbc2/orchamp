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

    # Whether the assumption is actually applied to the computations, or was
    # dropped by the `max_assumptions` cap (shown so the user can remove it).
    applied: bool = True


@dataclass(frozen=True)
class ParsedAssumptions:
    """
    Result of parsing the raw ``?a=`` query-parameter values.

    All valid entries are kept so the UI can list them, but only the first
    `max_assumptions` may feed the solver.
    """

    entries: list[AssumptionEntry]
    max_assumptions: int

    @property
    def applied(self) -> list[AssumptionEntry]:
        """
        The entries that computations may use (capped at `max_assumptions`).
        """

        return self.entries[: self.max_assumptions]

    @property
    def excess(self) -> bool:
        """
        Whether some valid entries are beyond the cap, so the UI can warn.
        """

        return len(self.entries) > self.max_assumptions


def _parse_assumption(s: str) -> AssumptionEntry | None:
    parts = s.split(":")
    if len(parts) != 4:
        return None
    try:
        home_score = int(parts[2])
        away_score = int(parts[3])
    except ValueError:
        return None
    if not (0 <= home_score <= 20) or not (0 <= away_score <= 20):
        return None
    return AssumptionEntry(
        home_id=parts[0],
        away_id=parts[1],
        home_score=home_score,
        away_score=away_score,
    )


def parse_assumptions(raw: list[str], max_assumptions: int) -> ParsedAssumptions:
    """
    Parse and validate a list of raw ``?a=`` query-parameter values.

    Each value must be ``"home_id:away_id:home_score:away_score"``.
    Malformed or out-of-range entries are silently dropped.
    """

    entries = [e for s in raw if (e := _parse_assumption(s)) is not None]
    return ParsedAssumptions(entries=entries, max_assumptions=max_assumptions)


def serialize_assumption(entry: AssumptionEntry) -> str:
    """
    Serialize an assumption to a ``?a=`` query-parameter value.
    """

    return f"{entry.home_id}:{entry.away_id}:{entry.home_score}:{entry.away_score}"
