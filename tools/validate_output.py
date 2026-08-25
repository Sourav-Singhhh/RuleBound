from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_LAYOUT = {"room_id", "placements", "violations", "status"}
REQUIRED_QUOTE = {"quote_id", "room_id", "currency", "lines", "summary", "status"}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate(output_root: Path) -> list[str]:
    errors: list[str] = []
    room_dirs = sorted(path for path in output_root.iterdir() if path.is_dir()) if output_root.exists() else []
    if not room_dirs:
        return [f"No room output directories found under {output_root}"]
    for room_dir in room_dirs:
        for filename, required in [("layout.json", REQUIRED_LAYOUT), ("quote.json", REQUIRED_QUOTE)]:
            path = room_dir / filename
            if not path.exists():
                errors.append(f"Missing {path}")
                continue
            try:
                value = load(path)
            except Exception as exc:
                errors.append(f"Invalid JSON {path}: {exc}")
                continue
            missing = required - set(value)
            if missing:
                errors.append(f"{path} missing keys: {sorted(missing)}")
        quote_path = room_dir / "quote.json"
        if quote_path.exists():
            quote = load(quote_path)
            if quote.get("currency") != "INR":
                errors.append(f"{quote_path}: currency must be INR")
            if quote.get("status") == "priced":
                for line in quote.get("lines", []):
                    if not line.get("trace"):
                        errors.append(f"{quote_path}: priced line {line.get('line_id')} has no trace")
                if "grand_total_inr" not in quote.get("summary", {}):
                    errors.append(f"{quote_path}: priced quote has no grand_total_inr")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    errors = validate(args.output)
    if errors:
        print("OUTPUT INVALID")
        print("\n".join(f"- {error}" for error in errors))
        raise SystemExit(1)
    print("OUTPUT VALID")


if __name__ == "__main__":
    main()
