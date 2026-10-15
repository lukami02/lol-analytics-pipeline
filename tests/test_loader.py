from datetime import date, datetime, timezone

import pytest

from lol_analytics.warehouse.bigquery_loader import BigQueryLoader

DAY = date(2026, 10, 14)


@pytest.fixture
def loader(fake_bq):
    return BigQueryLoader("proj", "EU", client=fake_bq)


def test_ensure_tables_creates_three_datasets(loader, fake_bq):
    loader.ensure_tables()

    assert set(fake_bq.datasets) == {"bronze", "silver", "gold"}
    assert set(fake_bq.tables) == {"bronze.matches", "bronze.top_players"}


def test_loads_only_new_matches(loader, fake_bq, store, make_match):
    store.save_match(DAY, "EUW1_1", make_match("EUW1_1"))
    store.save_match(DAY, "EUW1_2", make_match("EUW1_2"))

    first = loader.load_bronze_partition(store, DAY)
    second = loader.load_bronze_partition(store, DAY) 

    assert first["matches"] == 2
    assert second["matches"] == 0
    assert len(fake_bq.rows("matches")) == 2 


def test_new_match_is_added_on_next_load(loader, fake_bq, store, make_match):
    store.save_match(DAY, "EUW1_1", make_match("EUW1_1"))
    loader.load_bronze_partition(store, DAY)

    store.save_match(DAY, "EUW1_2", make_match("EUW1_2"))
    result = loader.load_bronze_partition(store, DAY)

    assert result["matches"] == 1
    assert len(fake_bq.rows("matches")) == 2


def test_top_players_loaded_once_per_day(loader, fake_bq, store):
    entries = [{"puuid": "p1", "leaguePoints": 900}, {"puuid": "p2", "leaguePoints": 800}]
    store.save_top_players(DAY, datetime.now(timezone.utc), entries)

    first = loader.load_bronze_partition(store, DAY)
    second = loader.load_bronze_partition(store, DAY)

    assert first["top_players"] == 2
    assert second["top_players"] == 0
    assert [r["rank_position"] for r in fake_bq.rows("top_players")] == [1, 2]


def test_load_without_date_loads_all_days(loader, fake_bq, store, make_match):
    store.save_match(date(2026, 10, 13), "EUW1_1", make_match("EUW1_1"))
    store.save_match(date(2026, 10, 14), "EUW1_2", make_match("EUW1_2"))

    loader.load_bronze(store)

    assert {r["match_id"] for r in fake_bq.rows("matches")} == {"EUW1_1", "EUW1_2"}