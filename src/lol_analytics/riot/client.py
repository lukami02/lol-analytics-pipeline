import asyncio
import time
from collections import deque
from urllib.parse import quote
from pydantic import ValidationError
from lol_analytics.riot.models import Account, LeagueEntry, Match
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


class RiotRateLimiter:
    """
    Proactive rate limiter supporting dual windows:
    - Short term: e.g., 20 requests / 1 second
    - Long term: e.g., 100 requests / 120 seconds
    """
    def __init__(self, short_limit: int = 20, short_window: float = 1.0, long_limit: int = 100, long_window: float = 120.0):
        self.short_limit = short_limit
        self.short_window = short_window
        self.short_times = deque()

        self.long_limit = long_limit
        self.long_window = long_window
        self.long_times = deque()

        self.lock = asyncio.Lock()

    async def acquire(self):
        while True:
            async with self.lock:
                now = time.monotonic()

                # Remove timestamps outside the sliding windows
                while self.short_times and now - self.short_times[0] >= self.short_window:
                    self.short_times.popleft()
                while self.long_times and now - self.long_times[0] >= self.long_window:
                    self.long_times.popleft()

                # Check if the request can proceed
                can_pass = (
                    len(self.short_times) < self.short_limit and
                    len(self.long_times) < self.long_limit
                )

                if can_pass:
                    self.short_times.append(now)
                    self.long_times.append(now)
                    return

                # Calculate required delay before retrying
                wait_short = (self.short_window - (now - self.short_times[0])) if len(self.short_times) >= self.short_limit else 0
                wait_long = (self.long_window - (now - self.long_times[0])) if len(self.long_times) >= self.long_limit else 0
                
                sleep_time = max(wait_short, wait_long, 0.05)

            # Sleep outside the lock so other coroutines can check or queue up
            await asyncio.sleep(sleep_time)


class RiotClient:
    def __init__(
        self,
        api_key: str,
        region: str = "europe",
        platform: str = "euw1",
        client: httpx.AsyncClient | None = None,
        platform_client: httpx.AsyncClient | None = None,
        max_retries: int = 3,
        concurrency: int = 5,
        short_limit=20, 
        short_window=1.0, 
        long_limit=100, 
        long_window=120.0,
        rate_limiter: RiotRateLimiter | None = None,
    ):
        self.max_retries = max_retries
        self._sem = asyncio.Semaphore(concurrency)
        
        # Initialize rate limiter with default Riot Development Key limits
        self.rate_limiter = rate_limiter or RiotRateLimiter(
            short_limit=short_limit, short_window=short_window, 
            long_limit=long_limit, long_window=long_window
        )

        self._client = client or httpx.AsyncClient(
            base_url=f"https://{region}.api.riotgames.com",
            headers={"X-Riot-Token": api_key},
            timeout=10.0,
        )

        self._platform_client = platform_client or httpx.AsyncClient(
            base_url=f"https://{platform}.api.riotgames.com", 
            headers={"X-Riot-Token": api_key},
            timeout=10.0,
        )

    async def close(self):
        await self._client.aclose()
        await self._platform_client.aclose()

    async def _get(self, path: str, params: dict | None = None, client: httpx.AsyncClient | None = None):
        client = client or self._client
        
        async with self._sem:
            for attempt in range(self.max_retries + 1):
                # Proactively wait for rate limiter clearance before sending request
                await self.rate_limiter.acquire()

                try:
                    resp = await client.get(path, params=params)
                except httpx.RequestError as e:
                    raise RiotAPIError(503, f"Network error: {e}") from e

                if resp.status_code == 200:
                    return resp.json()

                # Respect Riot's rate-limit retry instructions if 429 occurs
                if resp.status_code == 429:
                    if attempt < self.max_retries:
                        retry_after = float(resp.headers.get("Retry-After", 1))
                        await asyncio.sleep(retry_after)
                        continue

                    raise RateLimitError(429, ERROR_MESSAGES[429])

                # Retry temporary server errors with exponential backoff
                if resp.status_code >= 500 and attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue

                message = ERROR_MESSAGES.get(resp.status_code, "Unknown error")

                if resp.status_code == 404:
                    raise NotFoundError(404, message)

                raise RiotAPIError(resp.status_code, message)

        raise RiotAPIError(500, "Request failed after all retries")

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

    async def get_top_players(self, n: int = 200) -> list[LeagueEntry]:
        data = await self._get(
            "/lol/league/v4/challengerleagues/by-queue/RANKED_SOLO_5x5",
            client=self._platform_client,
        )
        entries = [self._parse(LeagueEntry, e) for e in data["entries"]]
        entries.sort(key=lambda e: e.leaguePoints, reverse=True)
        entries = entries[:n]
        await asyncio.gather(*(self._ensure_puuid(e) for e in entries))
        return entries
    
    async def _ensure_puuid(self, entry: LeagueEntry) -> None:
        if entry.puuid:
            return
        if not entry.summonerId:
            raise RiotAPIError(502, "There is no summoners id")
        data = await self._get(
            f"/lol/summoner/v4/summoners/{entry.summonerId}", client=self._platform_client
        )
        entry.puuid = data["puuid"]

    # Retrieve match IDs for a player
    async def get_match_ids(
        self, puuid: str, count: int = 20, start_time: int | None = None, queue: int | None = None
    ) -> list[str]:
        params: dict = {"start": 0, "count": max(1, min(count, 100))}
        if start_time:
            params["startTime"] = start_time
        if queue:
            params["queue"] = queue 
        return await self._get(f"/lol/match/v5/matches/by-puuid/{puuid}/ids", params=params)

    # Retrieve a single match
    async def get_match(self, match_id: str) -> dict:
        return await self._get(f"/lol/match/v5/matches/{match_id}")

    async def get_matches(self, match_ids: list[str], skip_errors: bool = True) -> dict[str, dict]:
        async def one(mid: str):
            try:
                return mid, await self.get_match(mid)
            except RiotAPIError as e:
                if not skip_errors:
                    raise
                return mid, None

        results = await asyncio.gather(*(one(m) for m in match_ids))
        return {mid: data for mid, data in results if data is not None}