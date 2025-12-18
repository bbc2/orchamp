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


def parse_matches(soup: BeautifulSoup) -> tuple[list[ParsedMatch], list[ParsedMatch]]:
    """
    Parse matches from the results table.

    Returns a tuple of (completed_matches, remaining_matches).
    A match is completed if it has scores for both teams.
    """

    completed: list[ParsedMatch] = []
    remaining: list[ParsedMatch] = []

    # Find the match results table (the one with class 'champ' but not 'tablesorter')
    match_tables = soup.find_all("table", class_="champ")

    for table in match_tables:
        # Skip the standings table
        table_classes = table.get("class")
        if table_classes and "tablesorter" in table_classes:
            continue

        for tbody in table.find_all("tbody"):
            for row in tbody.find_all("tr"):
                # Skip header rows (date rows have th elements spanning all columns)
                if row.find("th", class_="date_m"):
                    continue
                if row.find("th", class_="jours"):
                    # This is a match row with day indicator
                    pass

                # Find the two club cells
                club_cells = row.find_all("td", class_="club")
                if len(club_cells) != 2:
                    continue

                home_cell, away_cell = club_cells[0], club_cells[1]
                home_id = _extract_team_id(home_cell)
                away_id = _extract_team_id(away_cell)

                # Skip exempt matches (no opponent)
                if not home_id or not away_id:
                    continue

                # Get all td cells to find scores
                all_cells = row.find_all("td")

                # Scores are typically in cells between the two club cells
                home_score: int | None = None
                away_score: int | None = None

                # Find cells with score classes or positioned between club cells
                for i, cell in enumerate(all_cells):
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
                )

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
    completed, remaining = parse_matches(soup)

    return {
        "teams": [{"id": t.id, "name": t.name} for t in teams],
        "completed_matches": [
            {
                "home": m.home,
                "away": m.away,
                "home_score": m.home_score,
                "away_score": m.away_score,
                "result": _result_from_score(m.home_score, m.away_score),  # type: ignore[arg-type]
            }
            for m in completed
        ],
        "remaining_matches": [{"home": m.home, "away": m.away} for m in remaining],
    }
