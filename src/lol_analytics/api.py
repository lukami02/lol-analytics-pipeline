import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse

from lol_analytics.riot.models import Account, PlayerMatches
from .riot.client import RiotAPIError, RiotClient
from .riot.extract import save_json, extract_player_matches
from lol_analytics.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings

    app.state.riot = RiotClient(
        api_key=settings.riot_api_key,
        region=settings.riot_region,
    )
    yield
    await app.state.riot.close()


app = FastAPI(title="Riot Match Collector", lifespan=lifespan)


def get_riot(request: Request) -> RiotClient:
    return request.app.state.riot


@app.exception_handler(RiotAPIError)
async def riot_error_handler(request: Request, exc: RiotAPIError):
    status = 502 if exc.status_code in (401, 403) else exc.status_code
    return JSONResponse(status_code=status, content={"detail": exc.message})


@app.get(
    "/players/{game_name}/{tag_line}",
    response_model=Account,
    responses={404: {"description": "Player not found"},
               429: {"description": "Riot rate limit"}},
)
async def get_player(game_name: str, tag_line: str, riot: RiotClient = Depends(get_riot)):
    return await riot.get_account(game_name, tag_line)


@app.get("/players/{game_name}/{tag_line}/matches", response_model=PlayerMatches)
async def get_player_matches(
    request: Request,
    game_name: str,
    tag_line: str,
    count: int = Query(20, ge=1, le=20),
    save: bool = True,
    riot: RiotClient = Depends(get_riot),
):
    result = await extract_player_matches(riot, game_name, tag_line, count)
    if save:
        out_dir = request.app.state.settings.data_dir / "raw"
        result.saved_to = str(save_json(result, f"{game_name}_{tag_line}", out_dir))
    return result