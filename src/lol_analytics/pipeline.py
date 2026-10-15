import argparse
import asyncio
import logging

from lol_analytics.settings import Settings

from lol_analytics.bronze.store import BronzeStore
from lol_analytics.riot.client import RiotClient
from lol_analytics.riot.extract import extract_bronze
from lol_analytics.settings import get_settings

log = logging.getLogger("pipeline")

async def do_extract(s: Settings, args) -> None:
    riot = RiotClient(api_key=s.riot_api_key, region=s.riot_region, platform=s.riot_platform)
    try:
        stats = await extract_bronze(
            riot, BronzeStore(s.data_dir / "bronze"), top_n=args.top, matches_per_player=args.matches
        )
        log.info("Extract done: %s", stats)
    finally:
        await riot.close()


def do_load(s, args) -> None:
    pass

def do_transform(s: Settings, args) -> None:
    pass


def main() -> None:
    parser = argparse.ArgumentParser(description="LoL analytics pipeline")
    parser.add_argument("step", choices=["extract", "load", "transform", "all"])
    parser.add_argument("--top", type=int, default=200)
    parser.add_argument("--matches", type=int, default=20)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    s = get_settings()
    if args.step in ("extract", "all"):
        asyncio.run(do_extract(s, args))
    if args.step in ("load", "all"):
        do_load(s, args)
    if args.step in ("transform", "all"):
        do_transform(s, args)


if __name__ == "__main__":
    main()