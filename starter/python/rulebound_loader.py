from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AssetPack:
    catalog: list[dict[str, Any]]
    finishes: list[dict[str, Any]]
    rules: dict[str, Any]
    rooms: list[dict[str, Any]]
    briefs: dict[str, str]
    historical_jobs: list[dict[str, Any]]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_asset_pack(input_dir: str | Path) -> AssetPack:
    root = Path(input_dir)
    rooms = [read_json(path) for path in sorted((root / "rooms").glob("ROOM-*.json"))]
    briefs = {path.stem: path.read_text(encoding="utf-8").strip() for path in sorted((root / "briefs").glob("ROOM-*.txt"))}
    return AssetPack(
        catalog=read_json(root / "catalog.json"),
        finishes=read_json(root / "finishes.json"),
        rules=read_json(root / "rules.json"),
        rooms=rooms,
        briefs=briefs,
        historical_jobs=read_json(root / "historical_jobs.json"),
    )
