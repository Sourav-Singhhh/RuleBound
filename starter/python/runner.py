"""
Main Orchestration Pipeline Runner for RuleBound.
Accepts --input and --output flags according to RUNNER_CONTRACT.md.
Executes Generator -> Arbitration -> Final Revalidation -> Pricing / Blocked Quote.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root and starter directory to sys.path for robust import resolution
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
STARTER_DIR = Path(__file__).resolve().parent
if str(STARTER_DIR) not in sys.path:
    sys.path.insert(0, str(STARTER_DIR))

from rulebound_loader import load_asset_pack
from src.arbitration import ArbitrationEngine
from src.constraints import ConstraintEngine
from src.generator import GeneratorEngine
from src.output import create_blocked_quote, write_json
from src.pricing import PricingEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="RuleBound Pipeline Runner")
    parser.add_argument("--input", required=True, help="Input directory containing data pack")
    parser.add_argument("--output", required=True, help="Output directory for generated quotes and layouts")
    args = parser.parse_args()

    pack = load_asset_pack(args.input)
    output_root = Path(args.output)

    # Extract rules list adapter
    rules_list = pack.rules.get("rules", []) if isinstance(pack.rules, dict) else pack.rules

    # Instantiate engines
    constraint_engine = ConstraintEngine(pack.catalog, pack.finishes, rules_list)
    generator_engine = GeneratorEngine(pack.catalog, pack.finishes, rules_list, pack.historical_jobs)
    arbitration_engine = ArbitrationEngine(pack.catalog, pack.finishes, rules_list, constraint_engine)
    pricing_engine = PricingEngine(pack.catalog, pack.finishes)

    # Sort room objects deterministically by room_id
    sorted_rooms = sorted(pack.rooms, key=lambda item: item["room_id"])

    for room in sorted_rooms:
        room_id = room["room_id"]
        brief_text = pack.briefs.get(room_id, "")

        # 1. Proposal Generation
        proposal = generator_engine.generate_proposal(room, brief_text)

        # 2. Bounded Local Repair Arbitration
        room_with_meta = dict(room)
        item_counts = generator_engine.parse_furniture_counts(brief_text, room.get("capacity", 1))
        room_with_meta["required_workstations"] = item_counts.get("desk", 0)
        room_with_meta["required_storage"] = item_counts.get("storage", 0)
        room_with_meta["required_collaboration"] = item_counts.get("collaboration", 0)
        room_with_meta["required_accessory"] = item_counts.get("accessory", 0)
        room_with_meta["brief_text"] = brief_text
        arbitrated_layout = arbitration_engine.arbitrate(proposal, room_with_meta)

        # 3. Final Authoritative Revalidation Safety Gate
        if arbitrated_layout.get("status") == "valid":
            final_layout = constraint_engine.validate_layout(arbitrated_layout, room)
        else:
            final_layout = arbitrated_layout

        # 4. Pricing / Blocked Quote Path
        if final_layout.get("status") == "valid" and len(final_layout.get("violations", [])) == 0:
            # Group placements by (sku, finish_id)
            groups = {}
            for p in final_layout.get("placements", []):
                key = (p["sku"], p["finish_id"])
                groups[key] = groups.get(key, 0) + 1

            line_inputs = [
                {"line_id": f"L{idx+1:03d}", "sku": sku, "finish_id": fid, "quantity": qty}
                for idx, ((sku, fid), qty) in enumerate(sorted(groups.items()))
            ]

            quote = pricing_engine.calculate_quote(
                quote_id=f"QUOTE-{room_id}",
                room_id=room_id,
                line_inputs=line_inputs
            )
        else:
            # Layout is non-priceable / unsatisfiable
            reasons = []
            if final_layout.get("violations"):
                for v in final_layout["violations"]:
                    msg = v.get("message", "Violation detected")
                    rule_id = v.get("rule_id", "")
                    meas = v.get("measured", {})
                    term_reason = meas.get("termination_reason")
                    if term_reason:
                        reasons.append(f"Layout unsatisfiable due to {term_reason}.")
                    elif rule_id:
                        reasons.append(f"Unresolved violation {rule_id}: {msg}")
                    else:
                        reasons.append(msg)
            if not reasons:
                reasons = ["Layout status is not valid."]

            quote = create_blocked_quote(
                quote_id=f"QUOTE-{room_id}",
                room_id=room_id,
                blocking_reasons=reasons
            )

        # 5. Serialization
        write_json(output_root / room_id / "layout.json", final_layout)
        write_json(output_root / room_id / "quote.json", quote)


if __name__ == "__main__":
    main()
