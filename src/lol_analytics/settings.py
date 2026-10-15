import os
import json
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    riot_api_key: str
    riot_region: str
    riot_platform: str
    data_dir: Path
    gcp_project_id: str
    bq_dataset: str
    bq_location: str
    google_credentials_json: str | None


def get_settings() -> Settings:
    key = os.getenv("RIOT_API_KEY")
    if not key:
        raise RuntimeError("RIOT_API_KEY is not set (check .env)")

    credentials_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    try:
        creds_info = json.loads(credentials_json)
        project_id = creds_info["project_id"]
    except (json.JSONDecodeError, KeyError) as e:
        raise RuntimeError(f"Invalid GOOGLE_CREDENTIALS_JSON format or missing 'project_id': {e}")


    return Settings(
        riot_api_key=key,
        riot_region=os.getenv("RIOT_REGION", "europe"),
        riot_platform=os.getenv("RIOT_PLATFORM", "euw1"),
        data_dir=Path(os.getenv("DATA_DIR", ROOT / "data")),
        gcp_project_id=project_id,
        bq_dataset=os.getenv("BIGQUERY_DATASET_ID", "lol_analytics"),
        bq_location=os.getenv("BIGQUERY_LOCATION", "EU"),
        google_credentials_json=credentials_json,
    )