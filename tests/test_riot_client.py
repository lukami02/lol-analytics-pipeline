import asyncio

import httpx
import pytest

from lol_analytics.riot.client import NotFoundError, RiotClient, RiotAPIError


def make_client(handler) -> RiotClient:
    transport = httpx.MockTransport(handler)
    return RiotClient(
        api_key="test",
        client=httpx.AsyncClient(transport=transport, base_url="https://europe.api.riotgames.com"),
        platform_client=httpx.AsyncClient(transport=transport, base_url="https://euw1.api.riotgames.com"),
    )


def run(handler, method_name, *args, **kwargs):
    async def go():
        riot = make_client(handler)
        try:
            return await asyncio.wait_for(getattr(riot, method_name)(*args, **kwargs), timeout=10)
        finally:
            await riot.close()

    return asyncio.run(go())


def test_get_match_ids():
    handler = lambda request: httpx.Response(200, json=["EUW1_1", "EUW1_2"])
    assert run(handler, "get_match_ids", "some-puuid") == ["EUW1_1", "EUW1_2"]

def test_404_raises_not_found():
    handler = lambda request: httpx.Response(404)

    with pytest.raises(NotFoundError):
        run(handler, "get_match_ids", "some-puuid")

def test_429_is_retried_until_success():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:  
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json=["EUW1_1"])

    assert run(handler, "get_match_ids", "some-puuid") == ["EUW1_1"]
    assert len(calls) == 3

def test_500_is_retried_with_backoff():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(500)
        return httpx.Response(200, json=["EUW1_1"])

    assert run(handler, "get_match_ids", "some-puuid") == ["EUW1_1"]
    assert len(calls) == 3

def test_get_matches(make_match):
    def handler(request):
        match_id = request.url.path.split("/")[-1]
        return httpx.Response(200, json=make_match(match_id))

    ids = [f"EUW1_{i}" for i in range(20)] 

    result = run(handler, "get_matches", ids)

    assert set(result) == set(ids)
    assert result["EUW1_3"]["metadata"]["matchId"] == "EUW1_3"

def test_invalid_model_format_raises_502():
    handler = lambda request: httpx.Response(200, json={})

    with pytest.raises(RiotAPIError) as exc_info:
        run(handler, "get_account", "Faker", "KR1")

    assert exc_info.value.status_code == 502

def test_get_matches_skips_failed_match(make_match):
    def handler(request):
        match_id = request.url.path.split("/")[-1]
        if match_id == "EUW1_BAD":
            return httpx.Response(404)
        return httpx.Response(200, json=make_match(match_id))

    result = run(handler, "get_matches", ["EUW1_1", "EUW1_BAD"])

    assert set(result) == {"EUW1_1"}