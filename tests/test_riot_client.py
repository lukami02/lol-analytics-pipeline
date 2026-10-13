import os
from pathlib import Path
import pytest
import respx
from httpx import AsyncClient, Response
from fastapi.testclient import TestClient

from lol_analytics.riot.client import RiotClient, RiotAPIError, NotFoundError, RateLimitError
from lol_analytics.api import app

BASE = "https://europe.api.riotgames.com"

#########
# Fixture
#########
@pytest.fixture()
def riot_client():
    return RiotClient("fake-key", max_retries=2)

@pytest.fixture
def client():
    """FastAPI TestClient fixture."""
    with TestClient(app) as c:
        yield c

#######################
# Tests for RiotClient 
#######################

@respx.mock
@pytest.mark.asyncio
async def test_get_account_success(riot_client):
    respx.get("https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/Faker/KR1").mock(
        return_value=Response(200, json={
            "puuid": "test-puuid-123",
            "gameName": "Faker",
            "tagLine": "KR1"
        })
    )

    account = await riot_client.get_account("Faker", "KR1")
    assert account.puuid == "test-puuid-123"
    assert account.gameName == "Faker"
    assert account.tagLine == "KR1"


@respx.mock
@pytest.mark.asyncio
async def test_get_account_not_found(riot_client):
    respx.get("https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/Unknown/000").mock(
        return_value=Response(404, json={"status": {"message": "Not Found", "status_code": 404}})
    )

    with pytest.raises(NotFoundError):
        await riot_client.get_account("Unknown", "000")


@respx.mock
@pytest.mark.asyncio
async def test_get_account_rate_limit(riot_client):
    respx.get("https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/Rate/Limit").mock(
        return_value=Response(429, headers={"Retry-After": "1"})
    )

    riot_client.max_retries = 0

    with pytest.raises(RateLimitError):
        await riot_client.get_account("Rate", "Limit")


@respx.mock
@pytest.mark.asyncio
async def test_forbidden_key(riot_client):
    respx.get(f"{BASE}/riot/account/v1/accounts/by-riot-id/X/Y").mock(
        return_value=Response(403, json={"status": {"message": "Not Found"}})
    )
    with pytest.raises(RiotAPIError) as e:
        await riot_client.get_puuid("X", "Y")
    assert e.value.status_code == 403


@respx.mock
@pytest.mark.asyncio
async def test_retry_on_429_then_success(riot_client):
    route = respx.get(f"{BASE}/lol/match/v5/matches/EUW1_1").mock(
        side_effect=[
            Response(429, headers={"Retry-After": "0"}),
            Response(200, json={
                "metadata": {
                    "matchId": "EUW1_1",
                    "participants": ["puuid1"]
                },
                "info": {
                    "gameId": 12345,
                    "gameCreation": 1700000000000,
                    "gameDuration": 1500,
                    "gameMode": "CLASSIC",
                    "queueId": 420,
                    "gameVersion": "14.1.1",
                    "participants": []
                }
            }),
        ]
    )
    data = await riot_client.get_match("EUW1_1")
    assert data.metadata.matchId == "EUW1_1"
    assert route.call_count == 2


#############################
# Tests for FastAPI Endpoints 
#############################

@respx.mock
def test_api_get_player_success(client):
    respx.get("https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/TestUser/EUW").mock(
        return_value=Response(200, json={
            "puuid": "puuid-abc",
            "gameName": "TestUser",
            "tagLine": "EUW"
        })
    )

    response = client.get("/players/TestUser/EUW")
    assert response.status_code == 200
    data = response.json()
    assert data["puuid"] == "puuid-abc"
    assert data["gameName"] == "TestUser"


@respx.mock
def test_api_get_player_not_found(client):
    respx.get("https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/Missing/User").mock(
        return_value=Response(404)
    )

    response = client.get("/players/Missing/User")
    assert response.status_code == 404
    assert "detail" in response.json()