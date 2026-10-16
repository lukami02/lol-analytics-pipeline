import json
import re
import threading
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from google.cloud import bigquery
from google.oauth2 import service_account

from lol_analytics.settings import get_settings

CACHE_TTL = 3600
CACHE_MAX_ENTRIES = 256

Position = Literal["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
ChampionSort = Literal[
    "win_rate", "pick_rate", "games", "kda", "cs_per_min", "avg_damage"
]


class TTLCache:
    """Simple thread-safe cache with a TTL and a bounded size."""

    def __init__(self, ttl: float, max_entries: int):
        self._ttl = ttl
        self._max_entries = max_entries
        self._data: OrderedDict[Any, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            hit = self._data.get(key)
            if hit is None:
                return None
            created_at, value = hit
            if time.monotonic() - created_at >= self._ttl:
                del self._data[key]
                return None
            return value

    def set(self, key, value) -> None:
        with self._lock:
            self._data[key] = (time.monotonic(), value)
            self._data.move_to_end(key)
            while len(self._data) > self._max_entries:
                self._data.popitem(last=False) 


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    credentials = service_account.Credentials.from_service_account_info(json.loads(s.google_credentials_json))

    app.state.bq = bigquery.Client(project=s.gcp_project_id, credentials=credentials)
    app.state.gold = f"{s.gcp_project_id}.gold"
    app.state.cache = TTLCache(CACHE_TTL, CACHE_MAX_ENTRIES)

    try:
        yield
    finally:
        app.state.bq.close()


app = FastAPI(
    title="LoL Analytics API",
    description="League of Legends champion and ranked-player statistics.",
    version="1.0.0",
    lifespan=lifespan
)


def run(
    request: Request,
    sql: str,
    params: list[bigquery.ScalarQueryParameter] | None = None,
) -> list[dict]:
    params = params or []

    key = (sql, tuple((p.name, p.value) for p in params))

    cache: TTLCache = request.app.state.cache
    cached = cache.get(key)
    if cached is not None:
        return cached

    config = bigquery.QueryJobConfig(query_parameters=params)
    job = request.app.state.bq.query(sql, job_config=config)
    rows = [dict(row) for row in job.result()]

    cache.set(key, rows)
    return rows


def patch_key(patch: str) -> tuple[int, ...]:
    if not re.fullmatch(r"\d+(?:\.\d+)*", patch):
        return (0,)
    return tuple(int(part) for part in patch.split("."))


def patches(request: Request) -> list[str]:
    sql = f"""
        SELECT DISTINCT patch
        FROM `{request.app.state.gold}.champion_stats`
        WHERE patch IS NOT NULL
    """
    rows = run(request, sql)
    return sorted({row["patch"] for row in rows if row["patch"]}, key=patch_key)


def latest_patch(request: Request) -> str:
    available = patches(request)
    if not available:
        raise HTTPException(status_code=404, detail="No champion statistics available")
    return available[-1]


# Health

@app.get("/health")
def health():
    """Liveness check: the API process is running."""
    return {"status": "ok"}


@app.get("/ready")
def readiness(request: Request):
    """Readiness check: BigQuery is reachable."""
    try:
        request.app.state.bq.query("SELECT 1").result()
    except Exception:
        raise HTTPException(status_code=503, detail="BigQuery is unavailable")
    return {"status": "ready", "bigquery": "ok"}


@app.get("/patches")
def list_patches(request: Request):
    return {"patches": patches(request)}


# Champions


@app.get("/champions")
def champions(
    request: Request,
    patch: str | None = None,
    position: Position | None = None,
    min_games: int = Query(30, ge=1),
    sort: ChampionSort = "games",
    limit: int = Query(50, ge=1, le=200),
):
    patch = patch or latest_patch(request)

    sql = f"""
        SELECT * EXCEPT (patch_major, patch_minor)
        FROM `{request.app.state.gold}.champion_stats`
        WHERE patch = @patch
          AND games >= @min_games
          AND (@position IS NULL OR position = @position)
        ORDER BY {sort} DESC
        LIMIT @limit
    """
    params = [
        bigquery.ScalarQueryParameter("patch", "STRING", patch),
        bigquery.ScalarQueryParameter("min_games", "INT64", min_games),
        bigquery.ScalarQueryParameter("position", "STRING", position),
        bigquery.ScalarQueryParameter("limit", "INT64", limit),
    ]
    rows = run(request, sql, params)

    return {
        "patch": patch,
        "position": position,
        "count": len(rows),
        "results": rows,
    }


@app.get("/champions/{name}")
def champion_history(request: Request, name: str):
    sql = f"""
        SELECT * EXCEPT (patch_major, patch_minor)
        FROM `{request.app.state.gold}.champion_stats`
        WHERE LOWER(champion_name) = LOWER(@name)
        ORDER BY patch_major, patch_minor, position
    """
    params = [bigquery.ScalarQueryParameter("name", "STRING", name)]
    rows = run(request, sql, params)

    if not rows:
        raise HTTPException(status_code=404, detail=f"Champion '{name}' not found")

    return {"champion": name, "count": len(rows), "history": rows}


# Players

@app.get("/top-players")
def top_players(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
):
    sql = f"""
        SELECT *
        FROM `{request.app.state.gold}.top_player_stats`
        ORDER BY rank_position
        LIMIT @limit
    """
    params = [bigquery.ScalarQueryParameter("limit", "INT64", limit)]
    rows = run(request, sql, params)

    return {"count": len(rows), "results": rows}