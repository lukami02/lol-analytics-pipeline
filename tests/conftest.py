import pytest

@pytest.fixture
def make_match():
    def _make(match_id: str) -> dict:
        return {
            "metadata": {"matchId": match_id},
            "info": {"queueId": 420, "gameDuration": 1800, "participants": []},
        }

    return _make
