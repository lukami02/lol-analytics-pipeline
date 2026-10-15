import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Iterator


class BronzeStore:
    def __init__(self, root: Path):
        self.root = root

    @staticmethod
    def _write(path: Path, obj) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path) 

    # top players 
    def save_top_players(self, dt: date, fetched_at: datetime, entries: list[dict]) -> Path:
        path = self.root / "top_players" / f"dt={dt}" / "top_players.json"
        self._write(path, {"snapshot_date": str(dt), "fetched_at": fetched_at.isoformat(), "entries": entries})
        return path

    def read_top_players(self, dt: date) -> dict | None:
        path = self.root / "top_players" / f"dt={dt}" / "top_players.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    # matches 
    def save_match(self, dt: date, match_id: str, raw: dict) -> None:
        self._write(self.root / "matches" / f"dt={dt}" / f"{match_id}.json", raw)

    def existing_match_ids(self) -> set[str]:
        return {p.stem for p in (self.root / "matches").glob("dt=*/*.json")}

    def iter_matches(self, dt: date) -> Iterator[tuple[str, str]]:
        for p in sorted((self.root / "matches" / f"dt={dt}").glob("*.json")):
            yield p.stem, p.read_text(encoding="utf-8")

    def partitions(self) -> list[date]:
        dirs = list((self.root / "matches").glob("dt=*")) + list((self.root / "top_players").glob("dt=*"))
        return sorted({date.fromisoformat(p.name[3:]) for p in dirs})

    def match_ids(self, dt: date) -> list[str]:
        return sorted(p.stem for p in (self.root / "matches" / f"dt={dt}").glob("*.json"))

    def read_match(self, dt: date, match_id: str) -> str:
        return (self.root / "matches" / f"dt={dt}" / f"{match_id}.json").read_text(encoding="utf-8")