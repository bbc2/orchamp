"""
FastAPI web application for standings.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from orchamp_web.cache import DiskContentStore, DiskRootStore
from orchamp_web.config import AppConfig
from orchamp_web.services import StandingsService


def _load_config() -> AppConfig:
    config_path = os.environ.get("ORCHAMP_CONFIG")
    if not config_path:
        raise RuntimeError("ORCHAMP_CONFIG environment variable is not set")
    return AppConfig.from_file(Path(config_path))


_config = _load_config()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient() as client:
        app.state.http_client = client
        yield


app = FastAPI(
    title="Orchamp Web",
    description="Table tennis standings",
    lifespan=lifespan,
)

app.mount(
    "/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static"
)

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def get_config() -> AppConfig:
    return _config


def get_service(
    request: Request,
    config: Annotated[AppConfig, Depends(get_config)],
) -> StandingsService:
    roots = DiskRootStore(config.cache_dir / "roots.json")
    content = DiskContentStore(config.cache_dir / "objects")
    return StandingsService(
        roots=roots,
        content=content,
        config=config,
        http_client=request.app.state.http_client,
    )


@app.get("/api/{league_key}/standings")
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


@app.get("/web/{league_key}/", response_class=HTMLResponse)
async def web_standings(
    request: Request,
    league_key: str,
    config: Annotated[AppConfig, Depends(get_config)],
    service: Annotated[StandingsService, Depends(get_service)],
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


@app.get("/web/{league_key}/standings-table", response_class=HTMLResponse)
async def web_standings_table(
    request: Request,
    league_key: str,
    config: Annotated[AppConfig, Depends(get_config)],
    service: Annotated[StandingsService, Depends(get_service)],
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


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    config: Annotated[AppConfig, Depends(get_config)],
) -> HTMLResponse:
    """
    Home page with list of leagues.
    """

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"leagues": config.leagues},
    )
