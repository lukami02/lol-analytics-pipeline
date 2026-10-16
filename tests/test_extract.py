import asyncio
from types import SimpleNamespace

from lol_analytics.bronze.store import BronzeStore
from lol_analytics.riot.extract import extract_bronze
from lol_analytics.riot.models import LeagueEntry
from lol_analytics.riot.client import RiotAPIError

NAMES = {"p1": ("Faker", "KR1"), "p2": ("Chovy", "KR2")}

class FakeRiot:
    def __init__(self, make_match, failing_names=()):
        self.make_match = make_match
        self.failing_names = set(failing_names)
        self.fetched = [] 
        self.name_calls = []

    async def get_top_players(self, n):
        return [
            LeagueEntry(puuid="p1", leaguePoints=900),
            LeagueEntry(puuid="p2", leaguePoints=800),
        ]

    async def get_match_ids(self, puuid, count=20, start_time=None, queue=None):
        return {"p1": ["EUW1_1", "EUW1_2"], "p2": ["EUW1_2", "EUW1_3"]}[puuid]

    async def get_matches(self, match_ids, skip_errors=True):
        self.fetched.extend(match_ids)
        return {m: self.make_match(m) for m in match_ids}

    async def get_account_by_puuid(self, puuid):
        self.name_calls.append(puuid)
        if puuid in self.failing_names:
            raise RiotAPIError(404, "Requested resource not found")
        game_name, tag_line = NAMES[puuid]
        return SimpleNamespace(gameName=game_name, tagLine=tag_line)

def test_first_run_saves_all_matches(store, make_match):
    riot = FakeRiot(make_match)

    asyncio.run(extract_bronze(riot, store, top_n=2))

    assert store.existing_match_ids() == {"EUW1_1", "EUW1_2", "EUW1_3"} 

def test_shared_match_is_fetched_only_once(store, make_match):
    riot = FakeRiot(make_match)

    asyncio.run(extract_bronze(riot, store, top_n=2))

    assert riot.fetched.count("EUW1_2") == 1

def test_second_run_fetches_nothing(store, make_match):
    asyncio.run(extract_bronze(FakeRiot(make_match), store, top_n=2))
    second = FakeRiot(make_match)
    asyncio.run(extract_bronze(second, store, top_n=2))

    assert second.fetched == []

def test_top_players_snapshot_is_saved(tmp_path, make_match):
    store = BronzeStore(tmp_path / "bronze")

    asyncio.run(extract_bronze(FakeRiot(make_match), store, top_n=2))

    snapshot = store.read_top_players(store.partitions()[0])
    assert [e["puuid"] for e in snapshot["entries"]] == ["p1", "p2"]

def test_names_are_cached_between_runs(store, make_match):
    asyncio.run(extract_bronze(FakeRiot(make_match), store, top_n=2))
    second = FakeRiot(make_match)

    asyncio.run(extract_bronze(second, store, top_n=2))

    assert second.name_calls == []
    assert store.read_names() == {"p1": "Faker#KR1", "p2": "Chovy#KR2"}


def test_only_unknown_players_are_looked_up(store, make_match):
    store.save_names({"p1": "Faker#KR1"})
    riot = FakeRiot(make_match)

    asyncio.run(extract_bronze(riot, store, top_n=2))

    assert riot.name_calls == ["p2"]


def test_failed_name_lookup_does_not_break_extract(store, make_match):
    riot = FakeRiot(make_match, failing_names={"p2"})

    asyncio.run(extract_bronze(riot, store, top_n=2))

    snapshot = store.read_top_players(store.partitions()[0])
    assert [e["riot_id"] for e in snapshot["entries"]] == ["Faker#KR1", None]
    assert "p2" not in store.read_names()
    assert store.existing_match_ids() == {"EUW1_1", "EUW1_2", "EUW1_3"}