import re

from lol_analytics.warehouse.transforms import TRANSFORMS


def test_only_known_placeholders():
    for name, sql in TRANSFORMS.items():
        placeholders = set(re.findall(r"\{(\w+)\}", sql))
        assert placeholders <= {"bronze", "silver", "gold"}, name


def test_silver_matches_comes_before_participants():
    names = list(TRANSFORMS)

    assert names.index("silver_matches") < names.index("silver_participants")


def test_gold_is_built_after_silver():
    names = list(TRANSFORMS)
    last_silver = max(i for i, n in enumerate(names) if n.startswith("silver_"))
    first_gold = min(i for i, n in enumerate(names) if n.startswith("gold_"))

    assert last_silver < first_gold


def test_gold_does_not_read_bronze():
    for name, sql in TRANSFORMS.items():
        if name.startswith("gold_"):
            assert "{bronze}" not in sql, name