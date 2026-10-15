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