"""
Route handlers for the web application.
"""

import asyncio
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from orchamp_web.assumptions import (
    AssumptionDisplay,
    parse_assumptions,
    serialize_assumption,
)
from orchamp_web.auth import require_basic_auth
from orchamp_web.cache import DiskContentStore, DiskRootStore
from orchamp_web.config import AppConfig
from orchamp_web.i18n import SUPPORTED_LOCALES
from orchamp_web.services import StandingsService

router = APIRouter(dependencies=[Depends(require_basic_auth)])


@router.get("/set-lang", response_class=RedirectResponse, include_in_schema=False)
def set_lang(
    request: Request,
    lang: str,
) -> RedirectResponse:
    """
    Set the language cookie and redirect back to the referring page.
    """
    if lang not in SUPPORTED_LOCALES:
        lang = "en"
    redirect_to = request.headers.get("referer", "/")
    response = RedirectResponse(url=redirect_to, status_code=303)
    response.set_cookie(
        key="lang",
        value=lang,
        max_age=365 * 24 * 3600,
        samesite="lax",
        httponly=False,
    )
    return response


def get_config(request: Request) -> AppConfig:
    """
    Get configuration from app state.
    """
    return request.app.state.config


def get_templates(request: Request) -> Jinja2Templates:
    """
    Get templates from app state.
    """
    return request.app.state.templates


def get_service(
    request: Request,
    config: Annotated[AppConfig, Depends(get_config)],
) -> StandingsService:
    """
    Create StandingsService instance.
    """
    roots = DiskRootStore(config.cache_dir / "roots.json")
    content = DiskContentStore(config.cache_dir / "objects")
    return StandingsService(
        roots=roots,
        content=content,
        config=config,
        http_client=request.app.state.http_client,
    )


@router.get("/api/{league_key}/standings")
async def api_standings(
    league_key: str,
    config: Annotated[AppConfig, Depends(get_config)],
    service: Annotated[StandingsService, Depends(get_service)],
) -> dict:
    """
    Get standings as JSON.
    """
    if league_key not in config.leagues:
        raise HTTPException(status_code=404, detail=f"Unknown league: {league_key}")

    standings = await service.get_standings(league_key)
    league = service.get_league_info(league_key)

    return {
        "league": {
            "key": league_key,
            "name": league.name,
            "url": league.url,
        },
        "standings": [
            {
                "position": r.position,
                "team_id": r.team_id,
                "team_name": r.team_name,
                "points": r.points,
            }
            for r in standings
        ],
    }


@router.get("/web/{league_key}/", response_class=HTMLResponse)
async def web_standings(
    request: Request,
    league_key: str,
    config: Annotated[AppConfig, Depends(get_config)],
    service: Annotated[StandingsService, Depends(get_service)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
) -> HTMLResponse:
    """
    Render standings as HTML.
    """
    if league_key not in config.leagues:
        raise HTTPException(status_code=404, detail=f"Unknown league: {league_key}")

    standings, rounds, projected_positions = await asyncio.gather(
        service.get_standings(league_key),
        service.get_rounds(league_key),
        service.get_projected_positions(league_key, []),
    )
    league = service.get_league_info(league_key)

    return templates.TemplateResponse(
        request=request,
        name="standings.html",
        context={
            "league_key": league_key,
            "league": league,
            "standings": standings,
            "rounds": rounds,
            "projected_positions": projected_positions,
        },
    )


@router.get("/web/{league_key}/standings-table", response_class=HTMLResponse)
async def web_standings_table(
    request: Request,
    league_key: str,
    config: Annotated[AppConfig, Depends(get_config)],
    service: Annotated[StandingsService, Depends(get_service)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    a: Annotated[list[str], Query()] = [],
) -> HTMLResponse:
    """
    Render just the standings table (for HTMX partial updates).
    """
    if league_key not in config.leagues:
        raise HTTPException(status_code=404, detail=f"Unknown league: {league_key}")

    standings = await service.get_standings(league_key)
    assumptions = parse_assumptions(a)
    projected_positions = await service.get_projected_positions(league_key, assumptions)

    return templates.TemplateResponse(
        request=request,
        name="partials/standings_table.html",
        context={
            "league_key": league_key,
            "standings": standings,
            "projected_positions": projected_positions,
        },
    )


@router.get("/web/{league_key}/assumptions-panel", response_class=HTMLResponse)
async def web_assumptions_panel(
    request: Request,
    league_key: str,
    config: Annotated[AppConfig, Depends(get_config)],
    service: Annotated[StandingsService, Depends(get_service)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    a: Annotated[list[str], Query()] = [],
) -> HTMLResponse:
    """
    Render the assumptions panel partial (HTMX target).
    """
    if league_key not in config.leagues:
        raise HTTPException(status_code=404, detail=f"Unknown league: {league_key}")

    assumptions = parse_assumptions(a)
    displays = await service.get_assumption_displays(league_key, assumptions)

    return templates.TemplateResponse(
        request=request,
        name="partials/assumptions_panel.html",
        context={
            "assumptions": displays,
        },
    )


@router.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
) -> HTMLResponse:
    """
    Home page with list of leagues.
    """
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )


@router.get("/web/{league_key}/team/{team_id}/", response_class=HTMLResponse)
async def web_team_analysis(
    request: Request,
    league_key: str,
    team_id: str,
    config: Annotated[AppConfig, Depends(get_config)],
    service: Annotated[StandingsService, Depends(get_service)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    a: Annotated[list[str], Query()] = [],
) -> HTMLResponse:
    """
    Render team analysis page.
    """

    if league_key not in config.leagues:
        raise HTTPException(status_code=404, detail=f"Unknown league: {league_key}")

    assumptions = parse_assumptions(a)
    analysis = await service.get_team_analysis(
        league_key, team_id, assumptions=assumptions
    )
    league = service.get_league_info(league_key)
    standings = await service.get_standings(league_key)

    if analysis is None:
        raise HTTPException(status_code=404, detail=f"Unknown team: {team_id}")

    team_names = {r.team_id: r.team_name for r in standings}
    assumption_displays = [
        AssumptionDisplay(
            home_id=asmp.home_id,
            home_name=team_names.get(asmp.home_id, asmp.home_id),
            away_id=asmp.away_id,
            away_name=team_names.get(asmp.away_id, asmp.away_id),
            home_score=asmp.home_score,
            away_score=asmp.away_score,
        )
        for asmp in assumptions
        if asmp.home_id in team_names and asmp.away_id in team_names
    ]
    assumption_qs = urlencode(
        [("a", serialize_assumption(asmp)) for asmp in assumptions]
    )

    return templates.TemplateResponse(
        request=request,
        name="team_analysis.html",
        context={
            "league_key": league_key,
            "league": league,
            "team_id": team_id,
            "analysis": analysis,
            "standings": standings,
            "assumption_displays": assumption_displays,
            "assumption_qs": assumption_qs,
        },
    )
