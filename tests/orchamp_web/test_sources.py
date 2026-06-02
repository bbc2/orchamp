"""
Tests for data sources.
"""

from pathlib import Path

import httpx2
import pytest

from orchamp.models import ChampionshipState, Rules
from orchamp.ranking import compute_rankings
from orchamp_web.config import DEFAULT_RULES, SourceType
from orchamp_web.sources import (
    ClassementDataSource,
    JsonDataSource,
    get_data_source,
)

TESTS_DIR = Path(__file__).parent.parent


def _make_client(
    content: bytes, content_type: str = "application/octet-stream"
) -> httpx2.AsyncClient:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200, content=content, headers={"content-type": content_type}
        )

    return httpx2.AsyncClient(transport=httpx2.MockTransport(handler))


class TestJsonDataSource:
    @pytest.mark.asyncio
    async def test_fetch_and_parse_fixture(self) -> None:
        """End-to-end test: JSON fixture → state dict → rankings."""

        fixture_path = TESTS_DIR / "orchamp" / "cli" / "data" / "small_league.json"
        content = fixture_path.read_bytes()
        client = _make_client(content, content_type="application/json")

        source = JsonDataSource()
        state_dict = await source.fetch_state(
            url="http://example.com/data.json",
            http_client=client,
        )

        # Verify we can parse the state
        state = ChampionshipState.from_dict(state_dict)
        assert len(state.teams) == 4
        assert len(state.completed_matches) == 3
        assert len(state.remaining_matches) == 3

        # Verify we can compute rankings
        rules = Rules.from_dict(DEFAULT_RULES)
        rankings = compute_rankings(state, rules)
        assert len(rankings) == 4

        # Alpha has 5 points (win=3 + draw=2), should be first
        alpha = next(r for r in rankings if r.team_id == "alpha")
        assert alpha.points == 5
        assert alpha.position == 1


class TestClassementDataSource:
    @pytest.mark.asyncio
    async def test_fetch_and_parse_fixture(self) -> None:
        """End-to-end test: HTML fixture → state dict → rankings."""

        fixture_path = TESTS_DIR / "orchamp_get" / "data" / "standings.html"
        content = fixture_path.read_bytes()
        client = _make_client(content, content_type="text/html")

        source = ClassementDataSource()
        state_dict = await source.fetch_state(
            url="http://example.com/page",
            http_client=client,
        )

        # Verify we can parse the state
        state = ChampionshipState.from_dict(state_dict)
        assert len(state.teams) == 7
        assert len(state.completed_matches) == 15
        assert len(state.remaining_matches) == 6

        # Verify we can compute rankings
        rules = Rules.from_dict(DEFAULT_RULES)
        rankings = compute_rankings(state, rules)
        assert len(rankings) == 7

        # Team A has 14 points, should be first
        team_a = next(r for r in rankings if r.team_id == "team_a")
        assert team_a.points == 14
        assert team_a.position == 1


class TestGetDataSource:
    def test_get_classement_source(self) -> None:
        source = get_data_source(SourceType.CLASSEMENT)

        assert isinstance(source, ClassementDataSource)

    def test_get_json_source(self) -> None:
        source = get_data_source(SourceType.JSON)

        assert isinstance(source, JsonDataSource)
