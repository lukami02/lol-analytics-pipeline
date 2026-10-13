import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lol_analytics.riot.models import PlayerMatches
from lol_analytics.riot.client import RiotClient

DATA_DIR = Path("data")

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