from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


catalog = read_json(ROOT / "data/catalog.json")
finishes = read_json(ROOT / "data/finishes.json")
rules = read_json(ROOT / "data/rules.json")
rooms = sorted((ROOT / "data/rooms").glob("ROOM-*.json"))
briefs = sorted((ROOT / "data/briefs").glob("ROOM-*.txt"))
jobs = read_json(ROOT / "data/historical_jobs.json")
quotes = sorted((ROOT / "data/reference_quotes").glob("REF-QUOTE-*.json"))

assert len(catalog) == 120, len(catalog)
assert len({item["sku"] for item in catalog}) == 120
assert len(finishes) == 18, len(finishes)
assert len(rules["rules"]) == 14, len(rules["rules"])
assert len(rooms) == 5 and len(briefs) == 5
assert len(jobs) == 6 and len(quotes) == 2
for path in quotes:
    quote = read_json(path)
    expected = sum(line["net_goods_inr"] for line in quote["lines"]) + quote["summary"]["labour_inr"] + quote["summary"]["freight_inr"]
    assert expected == quote["summary"]["grand_total_inr"], path
print("PACK VERIFIED: 120 SKUs, 18 finishes, 14 rules, 5 rooms, 6 jobs, 2 reconciled quotes")
