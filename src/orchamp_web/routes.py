"""
Route handlers for the web application.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from orchamp_web.cache import DiskContentStore, DiskRootStore
from orchamp_web.config import AppConfig
from orchamp_web.services import StandingsService

router = APIRouter()


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

    standings = await service.get_standings(league_key)
    league = service.get_league_info(league_key)

    return templates.TemplateResponse(
        request=request,
        name="standings.html",
        context={
            "league_key": league_key,
            "league": league,
            "standings": standings,
        },
    )


@router.get("/web/{league_key}/standings-table", response_class=HTMLResponse)
async def web_standings_table(
    request: Request,
    league_key: str,
    config: Annotated[AppConfig, Depends(get_config)],
    service: Annotated[StandingsService, Depends(get_service)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
) -> HTMLResponse:
    """
    Render just the standings table (for HTMX partial updates).
    """
    if league_key not in config.leagues:
        raise HTTPException(status_code=404, detail=f"Unknown league: {league_key}")

    standings = await service.get_standings(league_key)

    return templates.TemplateResponse(
        request=request,
        name="partials/standings_table.html",
        context={
            "league_key": league_key,
            "standings": standings,
        },
    )


@router.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    config: Annotated[AppConfig, Depends(get_config)],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
) -> HTMLResponse:
    """
    Home page with list of leagues.
    """
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"leagues": config.leagues},
    )
