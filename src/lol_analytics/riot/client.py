import asyncio
from urllib.parse import quote
from pydantic import ValidationError
from lol_analytics.riot.models import Account, Match
import httpx


class RiotAPIError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"{status_code}: {message}")


class NotFoundError(RiotAPIError):
    pass


class RateLimitError(RiotAPIError):
    pass


ERROR_MESSAGES = {
    400: "Invalid request",
    401: "Missing or invalid API key",
    403: "API key expired or access denied",
    404: "Requested resource not found",
    429: "Rate limit exceeded",
}


class RiotClient:
    def __init__(
        self,
        api_key: str,
        region: str = "europe",
        client: httpx.AsyncClient | None = None,
        max_retries: int = 3,
        concurrency: int = 5,
    ):
        self.max_retries = max_retries
        self._sem = asyncio.Semaphore(concurrency)
        self._client = client or httpx.AsyncClient(
            base_url=f"https://{region}.api.riotgames.com",
            headers={"X-Riot-Token": api_key},
            timeout=10.0,
        )

    async def close(self):
        await self._client.aclose()

    async def _get(self, path: str, params: dict | None = None):
        for attempt in range(self.max_retries + 1):
            try:
                resp = await self._client.get(path, params=params)
            except httpx.RequestError as e:
                raise RiotAPIError(503, f"Network error: {e}") from e

            if resp.status_code == 200:
                return resp.json()

            # Respect Riot's rate-limit retry instructions.
            if resp.status_code == 429:
                if attempt < self.max_retries:
                    retry_after = int(
                        resp.headers.get("Retry-After", 1)
                    )
                    await asyncio.sleep(retry_after)
                    continue

                raise RateLimitError(
                    429, ERROR_MESSAGES[429]
                )

            # Retry temporary server errors with exponential backoff.
            if resp.status_code >= 500 and attempt < self.max_retries:
                await asyncio.sleep(2**attempt)
                continue

            message = ERROR_MESSAGES.get(resp.status_code, "Unknown error")

            if resp.status_code == 404:
                raise NotFoundError(404, message)

            raise RiotAPIError(resp.status_code, message)

        raise RiotAPIError(
            500, "Request failed after all retries")

    @staticmethod
    def _parse(model, data):
        try:
            return model.model_validate(data)
        except ValidationError as e:
            raise RiotAPIError(502, f"Unexpected response format: {e.error_count()} errors") from e

    # Riot ID -> account information
    async def get_account(self, game_name: str, tag_line: str) -> Account:
        path = (
            "/riot/account/v1/accounts/by-riot-id/"
            f"{quote(game_name, safe='')}/"
            f"{quote(tag_line, safe='')}"
        )
        return self._parse(Account, await self._get(path))

    async def get_puuid(self, game_name: str, tag_line: str) -> str:
        return (await self.get_account(game_name, tag_line)).puuid

    # Retrieve match IDs for a player
    async def get_match_ids(self, puuid: str, count: int = 20) -> list[str]:
        count = max(1, min(count, 20))

        return await self._get(
            f"/lol/match/v5/matches/by-puuid/{puuid}/ids",
            params={"start": 0, "count": count},
        )

    # Retrieve a single match
    async def get_match(self, match_id: str) -> Match:
        async with self._sem:
            data = await self._get(f"/lol/match/v5/matches/{match_id}")
        return self._parse(Match, data)

    # Retrieve multiple matches concurrently
    async def get_matches(self, match_ids: list[str]) -> list[Match]:
        return list(await asyncio.gather(*(self.get_match(m) for m in match_ids)))