import json
from types import SimpleNamespace

import pytest

from lol_analytics.bronze.store import BronzeStore

@pytest.fixture
def make_match():
    def _make(match_id: str) -> dict:
        return {
            "metadata": {"matchId": match_id},
            "info": {"queueId": 420, "gameDuration": 1800, "participants": []},
        }

    return _make

@pytest.fixture
def store(tmp_path):
    return BronzeStore(tmp_path / "bronze")


class FakeJob:
    def __init__(self, rows):
        self._rows = rows

    def result(self):
        return self._rows


class FakeBigQuery:
    def __init__(self):
        self.datasets = []
        self.tables = []
        self.loaded = {}   
        self.queries = []

    def rows(self, table: str) -> list[dict]:
        return self.loaded.get(f"proj.bronze.{table}", [])

    def create_dataset(self, dataset, exists_ok=False):
        self.datasets.append(dataset.dataset_id)

    def create_table(self, table, exists_ok=False):
        self.tables.append(f"{table.dataset_id}.{table.table_id}")

    def load_table_from_file(self, file_obj, destination, job_config=None):
        text = file_obj.read().decode("utf-8")
        rows = [json.loads(line) for line in text.splitlines() if line]
        self.loaded.setdefault(destination, []).extend(rows)
        return FakeJob([])

    def query(self, sql, job_config=None):
        self.queries.append(sql)
        if "SELECT DISTINCT match_id" in sql:
            ids = job_config.query_parameters[0].values
            have = {r["match_id"] for r in self.rows("matches")}
            return FakeJob([SimpleNamespace(match_id=i) for i in ids if i in have])
        if "COUNT(*) AS n" in sql:
            day = str(job_config.query_parameters[0].value)
            n = sum(1 for r in self.rows("top_players") if r["snapshot_date"] == day)
            return FakeJob([SimpleNamespace(n=n)])
        return FakeJob([])


@pytest.fixture
def fake_bq():
    return FakeBigQuery()