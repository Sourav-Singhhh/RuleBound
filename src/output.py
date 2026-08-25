"""
Deterministic Output Serializer for RuleBound.
Handles layout and quote JSON writing conforming strictly to RUNNER_CONTRACT.md.
No mutation, no non-determinism, UTF-8, 2-space indent, sorted keys, trailing newline.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Sequence


def write_json(path: Path | str, payload: Any) -> None:
    """
    Writes payload to path as UTF-8 JSON with 2-space indentation, sorted keys, and trailing newline.
    Automatically creates parent directories.
    Does NOT mutate payload.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    target.write_text(content, encoding="utf-8")


def create_blocked_quote(
    quote_id: str,
    room_id: str,
    blocking_reasons: Sequence[str]
) -> Dict[str, Any]:
    """
    Constructs a schema-compliant blocked quote dictionary matching schemas/quote.schema.json.
    """
    reasons = list(blocking_reasons) if blocking_reasons else ["Layout is unsatisfiable."]
    return {
        "quote_id": quote_id,
        "room_id": room_id,
        "currency": "INR",
        "lines": [],
        "summary": {
            "grand_total_inr": 0
        },
        "status": "blocked",
        "blocking_reasons": reasons,
    }
