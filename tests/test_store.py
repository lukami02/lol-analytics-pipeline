import json
from datetime import date

DAY1 = date(2026, 10, 13)
DAY2 = date(2026, 10, 14)


def test_new_store_is_empty(store):
    assert store.existing_match_ids() == set()
    assert store.partitions() == []


def test_saved_match_is_unchanged(store, make_match):
    match = make_match("EUW1_1")

    store.save_match(DAY1, "EUW1_1", match)

    assert json.loads(store.read_match(DAY1, "EUW1_1")) == match


def test_existing_ids_look_at_all_days(store, make_match):
    store.save_match(DAY1, "EUW1_1", make_match("EUW1_1"))
    store.save_match(DAY2, "EUW1_2", make_match("EUW1_2"))

    assert store.existing_match_ids() == {"EUW1_1", "EUW1_2"}


def test_partitions_are_sorted(store, make_match):
    store.save_match(DAY2, "EUW1_2", make_match("EUW1_2"))
    store.save_match(DAY1, "EUW1_1", make_match("EUW1_1"))

    assert store.partitions() == [DAY1, DAY2]