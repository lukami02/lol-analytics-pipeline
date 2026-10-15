import json
import re
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import logging

from lol_analytics.bronze.store import BronzeStore
from lol_analytics.riot.models import PlayerMatches
from lol_analytics.riot.client import RiotAPIError, RiotClient

DATA_DIR = Path("data")
log = logging.getLogger("extract")

async def extract_player_matches(
    riot: RiotClient, game_name: str, tag_line: str, count: int = 20
) -> PlayerMatches:
    puuid = await riot.get_puuid(game_name, tag_line)
    match_ids = await riot.get_match_ids(puuid, count)
    matches = await riot.get_matches(match_ids)
    return PlayerMatches(
        riot_id=f"{game_name}#{tag_line}",
        puuid=puuid,
        match_ids=match_ids,
        matches=matches,
    )


def save_json(
    data: dict | list | Any,
    name: str,
    data_dir: Path = DATA_DIR,
) -> Path:
    """Save extracted data to a timestamped JSON file."""
    data_dir.mkdir(parents=True, exist_ok=True)

    if hasattr(data, "model_dump"):
        data = data.model_dump()

    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    file_path = data_dir / f"{safe_name}_{timestamp}.json"

    file_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return file_path


async def extract_bronze(
    riot: RiotClient,
    store: BronzeStore,
    top_n: int = 200,
    matches_per_player: int = 20,
    queue: int | None = 420,
    batch_size: int = 100,
) -> dict:
    now = datetime.now(timezone.utc)
    dt = now.date()

    top = await riot.get_top_players(top_n)
    store.save_top_players(dt, now, [e.model_dump() for e in top])

    async def ids_for(entry) -> list[str]:
        try:
            return await riot.get_match_ids(entry.puuid, count=matches_per_player, queue=queue)
        except RiotAPIError as e:
            log.warning("Could not fetch match IDs for %s: %s", entry.puuid[:8], e)
            return []

    id_lists = await asyncio.gather(*(ids_for(e) for e in top))
    all_ids = {i for ids in id_lists for i in ids}
    new_ids = sorted(all_ids - store.existing_match_ids())
    log.info("Players: %d, unique matches: %d, new: %d", len(top), len(all_ids), len(new_ids))

    saved = 0
    for i in range(0, len(new_ids), batch_size):
        matches = await riot.get_matches(new_ids[i : i + batch_size])
        for mid, raw in matches.items():
            store.save_match(dt, mid, raw)
        saved += len(matches)
        log.info("Saved %d / %d", saved, len(new_ids))

    return {"dt": str(dt), "players": len(top), "candidate_ids": len(all_ids), "new_matches": len(new_ids), "saved": saved}