import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    riot_api_key: str
    riot_region: str
    data_dir: Path


def get_settings() -> Settings:
    key = os.getenv("RIOT_API_KEY")
    if not key:
        raise RuntimeError("RIOT_API_KEY is not set (check .env)")
    return Settings(
        riot_api_key=key,
        riot_region=os.getenv("RIOT_REGION", "europe"),
        data_dir=Path(os.getenv("DATA_DIR", ROOT / "data")),
    )