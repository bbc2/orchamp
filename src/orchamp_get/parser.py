"""
Parser for extracting championship state from HTML pages.
"""

from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup, Tag


@dataclass(frozen=True)
class ParsedTeam:
    """
    Team extracted from standings table.
    """

    id: str
    name: str


@dataclass(frozen=True)
class ParsedMatch:
    """
    Match extracted from the match results table.
    """

    home: str  # Team ID
    away: str  # Team ID
    home_score: int | None = None
    away_score: int | None = None
    round_name: str | None = None
    date: str | None = None


@dataclass(frozen=True)
class ParsedRound:
    """
    A round with its matches.
    """

    name: str  # e.g. "R01"
    date: str | None  # ISO date, e.g. "2025-10-16"
    matches: list[ParsedMatch]


def _extract_team_id(cell: Tag) -> str | None:
    """
    Extract team ID from a table cell.

    The ID is typically in the label's 'for' attribute or in a class on the cell.
    """

    label = cell.find("label")
    if label and label.get("for"):
        return str(label.get("for"))

    # Fallback: look for class that looks like a team ID
    classes = cell.get("class")
    if classes:
        for cls in classes:
            if cls not in ("club", "v", "d", "n", "point", "champ"):
                return str(cls)

    return None


def _extract_team_name(cell: Tag) -> str | None:
    """
    Extract team name from a table cell.
    """

    label = cell.find("label")
    if label:
        return label.get_text(strip=True)

    return cell.get_text(strip=True) or None


def _parse_score(text: str) -> int | None:
    """
    Parse a score value, returning None for empty/invalid values.
    """

    text = text.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def parse_teams(soup: BeautifulSoup) -> list[ParsedTeam]:
    """
    Parse teams from the standings table.

    Looks for the standings table (class "tablesorter") and extracts team info.
    """

    teams: list[ParsedTeam] = []
    seen_ids: set[str] = set()

    # Find the standings table (usually has class 'tablesorter')
    standings_table = soup.find("table", class_="tablesorter")
    if not standings_table:
        return teams

    # Look in tbody for team rows
    tbody = standings_table.find("tbody")
    if not tbody:
        return teams

    for row in tbody.find_all("tr"):
        # Find the club cell
        club_cell = row.find("td", class_="club")
        if not club_cell:
            continue

        team_id = _extract_team_id(club_cell)
        team_name = _extract_team_name(club_cell)

        if team_id and team_name and team_id not in seen_ids:
            teams.append(ParsedTeam(id=team_id, name=team_name))
            seen_ids.add(team_id)

    return teams


def parse_rounds(soup: BeautifulSoup) -> list[ParsedRound]:
    """
    Parse matches grouped by round from the results table.

    Tracks the current round name and date as rows are iterated, assigning
    them to each match. Exempt matches (no opponent) are excluded.
    """

    rounds: list[ParsedRound] = []
    current_round_name: str | None = None
    current_round_date: str | None = None  # date when the current round started
    current_date: str | None = None  # most recently seen date_m value
    current_round_matches: list[ParsedMatch] = []

    match_tables = soup.find_all("table", class_="champ")

    for table in match_tables:
        table_classes = table.get("class")
        if table_classes and "tablesorter" in table_classes:
            continue

        for tbody in table.find_all("tbody"):
            for row in tbody.find_all("tr"):
                date_th = row.find("th", class_="date_m")
                if date_th:
                    time_el = date_th.find("time")
                    if time_el and time_el.get("datetime"):
                        current_date = str(time_el.get("datetime"))
                    continue

                jours_th = row.find("th", class_="jours")
                if jours_th:
                    if current_round_name is not None and current_round_matches:
                        rounds.append(
                            ParsedRound(
                                name=current_round_name,
                                date=current_round_date,
                                matches=current_round_matches,
                            )
                        )
                    current_round_name = jours_th.get_text(strip=True)
                    current_round_date = current_date  # date from preceding date_m row
                    current_round_matches = []

                club_cells = row.find_all("td", class_="club")
                if len(club_cells) != 2:
                    continue

                home_cell, away_cell = club_cells[0], club_cells[1]
                home_id = _extract_team_id(home_cell)
                away_id = _extract_team_id(away_cell)

                if not home_id or not away_id:
                    continue

                all_cells = row.find_all("td")
                home_score: int | None = None
                away_score: int | None = None

                for cell in all_cells:
                    classes = cell.get("class")
                    if classes and "club" in classes:
                        continue
                    text = cell.get_text(strip=True)
                    score = _parse_score(text)
                    if score is not None:
                        if home_score is None:
                            home_score = score
                        elif away_score is None:
                            away_score = score

                match = ParsedMatch(
                    home=home_id,
                    away=away_id,
                    home_score=home_score,
                    away_score=away_score,
                    round_name=current_round_name,
                    date=current_round_date,
                )
                current_round_matches.append(match)

    if current_round_name is not None and current_round_matches:
        rounds.append(
            ParsedRound(
                name=current_round_name,
                date=current_round_date,
                matches=current_round_matches,
            )
        )

    return rounds


def parse_matches(soup: BeautifulSoup) -> tuple[list[ParsedMatch], list[ParsedMatch]]:
    """
    Parse matches from the results table.

    Returns a tuple of (completed_matches, remaining_matches).
    A match is completed if it has scores for both teams.
    """

    completed: list[ParsedMatch] = []
    remaining: list[ParsedMatch] = []

    for round_ in parse_rounds(soup):
        for match in round_.matches:
            if match.home_score is not None and match.away_score is not None:
                completed.append(match)
            else:
                remaining.append(match)

    return completed, remaining


def _result_from_score(home_score: int, away_score: int) -> str:
    """Determine match result from scores."""

    if home_score > away_score:
        return "home_win"
    elif home_score < away_score:
        return "away_win"
    else:
        return "draw"


def parse_html(html: str) -> dict[str, Any]:
    """
    Parse HTML from a standings page and return championship state as a dict.

    The returned dict matches the format expected by the orchamp package.
    """

    soup = BeautifulSoup(html, "html.parser")

    teams = parse_teams(soup)
    rounds = parse_rounds(soup)

    all_matches = [m for r in rounds for m in r.matches]
    completed = [
        m for m in all_matches if m.home_score is not None and m.away_score is not None
    ]
    remaining = [m for m in all_matches if m.home_score is None or m.away_score is None]

    return {
        "teams": [{"id": t.id, "name": t.name} for t in teams],
        "completed_matches": [
            {
                "home": m.home,
                "away": m.away,
                "home_score": m.home_score,
                "away_score": m.away_score,
                "result": _result_from_score(m.home_score, m.away_score),  # type: ignore
            }
            for m in completed
        ],
        "remaining_matches": [{"home": m.home, "away": m.away} for m in remaining],
        "rounds": [
            {
                "name": r.name,
                "date": r.date,
                "matches": [
                    {
                        "home": m.home,
                        "away": m.away,
                        "home_score": m.home_score,
                        "away_score": m.away_score,
                        **(
                            {"result": _result_from_score(m.home_score, m.away_score)}
                            if m.home_score is not None and m.away_score is not None
                            else {}
                        ),
                    }
                    for m in r.matches
                ],
            }
            for r in rounds
        ],
    }
