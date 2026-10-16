import io
import json
from datetime import date, datetime, timezone

from google.cloud import bigquery
from google.oauth2 import service_account

from lol_analytics.bronze.store import BronzeStore
from lol_analytics.warehouse.transforms import TRANSFORMS
from lol_analytics.warehouse.schemas import SCHEMAS

DATASETS = ("bronze", "silver", "gold")


class BigQueryLoader:
    def __init__(self, project_id: str, location: str = "EU", credentials_json: str = "", client=None):
        if client is None:
            credentials = service_account.Credentials.from_service_account_info(json.loads(credentials_json))
            client = bigquery.Client(project=project_id, credentials=credentials)
        self.client = client
        self.project = project_id
        self.location = location
        self.bronze = f"{project_id}.bronze"
        self.silver = f"{project_id}.silver"
        self.gold = f"{project_id}.gold"

    def ensure_tables(self) -> None:
        for ds in DATASETS:
            dataset = bigquery.Dataset(f"{self.project}.{ds}")
            dataset.location = self.location
            self.client.create_dataset(dataset, exists_ok=True)
        for name, schema in SCHEMAS.items():
            self.client.create_table(
                bigquery.Table(f"{self.bronze}.{name}", schema=schema), exists_ok=True
            )

    def _existing_match_ids(self, ids: list[str]) -> set[str]:
        if not ids:
            return set()
        cfg = bigquery.QueryJobConfig(query_parameters=[bigquery.ArrayQueryParameter("ids", "STRING", ids)])
        q = f"SELECT DISTINCT match_id FROM `{self.bronze}.matches` WHERE match_id IN UNNEST(@ids)"
        return {r.match_id for r in self.client.query(q, job_config=cfg).result()}

    def _top_players_exist(self, dt: date) -> bool:
        cfg = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("d", "DATE", dt)])
        q = f"SELECT COUNT(*) AS n FROM `{self.bronze}.top_players` WHERE snapshot_date = @d"
        return next(iter(self.client.query(q, job_config=cfg).result())).n > 0

    def _load_dicts(self, table: str, rows: list[dict]) -> None:
        if not rows:
            return
        payload = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
        job = self.client.load_table_from_file(
            io.BytesIO(payload.encode("utf-8")),
            f"{self.bronze}.{table}",
            job_config=bigquery.LoadJobConfig(
                schema=SCHEMAS[table],
                source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
                write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            ),
        )
        job.result()

    def load_bronze_partition(self, store: BronzeStore, dt: date, chunk=500) -> dict:
        now = datetime.now(timezone.utc).isoformat()

        top_loaded = 0
        snap = store.read_top_players(dt)
        if snap and not self._top_players_exist(dt):
            rows = [
                {"snapshot_date": str(dt), "rank_position": i, "ingested_at": now, "raw": json.dumps(e)}
                for i, e in enumerate(snap["entries"], start=1)
            ]
            self._load_dicts("top_players", rows)
            top_loaded = len(rows)

        ids = store.match_ids(dt)

        existing = self._existing_match_ids(ids)
        missing = [m for m in ids if m not in existing]

        for i in range(0, len(missing), chunk):
            rows = [
                {"match_id": mid, "ingested_at": now, "raw": store.read_match(dt, mid)}
                for mid in missing[i : i + chunk]
            ]
            self._load_dicts("matches", rows)

        return {"dt": str(dt), "top_players": top_loaded, "matches": len(missing)}

    def load_bronze(self, store: BronzeStore, dt: date | None = None, last_n: int | None = None) -> list[dict]:
        if dt:
            dts = [dt]
        else:
            dts = store.partitions()
            if last_n:
                dts = dts[-last_n:]
        return [self.load_bronze_partition(store, d) for d in dts]

    def run_transforms(self) -> None:
        for name, sql in TRANSFORMS.items():
            sql = (
                sql.replace("{bronze}", self.bronze)
                .replace("{silver}", self.silver)
                .replace("{gold}", self.gold)
            )
            self.client.query(sql).result()