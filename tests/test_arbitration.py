"""
Unit tests for Deterministic Arbitration Engine (src/arbitration.py).
Tests repair operators, ranking, state hashing, schema compliance, and termination.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from src.arbitration import (
    ArbitrationEngine,
    PlacementProposal,
    ProposedLayout,
    RepairCandidate,
)
from src.constraints import ConstraintEngine

ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class TestArbitrationEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = read_json(ROOT / "data" / "catalog.json")
        cls.finishes = read_json(ROOT / "data" / "finishes.json")
        cls.rules = read_json(ROOT / "data" / "rules.json")["rules"]
        cls.room_01 = read_json(ROOT / "data" / "rooms" / "ROOM-01.json")
        cls.room_03 = read_json(ROOT / "data" / "rooms" / "ROOM-03.json")
        cls.layout_schema = read_json(ROOT / "schemas" / "layout.schema.json")
        cls.violation_schema = read_json(ROOT / "schemas" / "violation.schema.json")

        cls.constraint_engine = ConstraintEngine(cls.catalog, cls.finishes, cls.rules)
        cls.arbitrator = ArbitrationEngine(cls.catalog, cls.finishes, cls.rules, cls.constraint_engine)

    def test_a_already_valid_layout(self) -> None:
        # Placement far away from doors/walls (ROOM-01 capacity = 1)
        r_spec = dict(self.room_01)
        r_spec["capacity"] = 1

        placements = [
            {"placement_id": "P01", "sku": "NW-CHA-001", "finish_id": "F02", "x_mm": 2000, "y_mm": 3000, "rotation_deg": 0}
        ]
        layout = {"room_id": "ROOM-01", "placements": placements}
        res = self.arbitrator.arbitrate(layout, r_spec)
        self.assertEqual(res["status"], "valid")
        self.assertEqual(res["violations"], [])

    def test_b_single_nudge_repair(self) -> None:
        # Placement at x=50, y=3000 triggers wall clearance RB-GEO-005 (x_min < 100). Nudge moves it to x=150.
        placements = [
            {"placement_id": "P01", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 50, "y_mm": 3000, "rotation_deg": 0}
        ]
        r_spec = dict(self.room_01)
        r_spec["capacity"] = 0

        layout = {"room_id": "ROOM-01", "placements": placements}
        res = self.arbitrator.arbitrate(layout, r_spec)
        self.assertEqual(res["status"], "valid")

    def test_c_cascading_repair(self) -> None:
        # P01 at x=50, y=3000 (triggers RB-GEO-005 wall clearance).
        # P02 at x=1350, y=3000 (P01 nudge to x=150 causes overlap with P02).
        # Subsequent revalidation nudges P02 to x=1550, resolving all violations.
        placements = [
            {"placement_id": "P01", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 50, "y_mm": 3000, "rotation_deg": 0},
            {"placement_id": "P02", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 1350, "y_mm": 3000, "rotation_deg": 0}
        ]
        r_spec = dict(self.room_01)
        r_spec["capacity"] = 0

        layout = {"room_id": "ROOM-01", "placements": placements}
        res = self.arbitrator.arbitrate(layout, r_spec)
        self.assertEqual(res["status"], "valid")
        self.assertEqual(res["violations"], [])

    def test_d_rotation_repair(self) -> None:
        # Chair P01 at x=100, y=3000, rot 90 (rear is west -x, extending to 100 - 750 = -650 < 0, violating RB-GEO-008).
        # Rotation to rot 270 or rot 0 shifts rear pullout away from west wall.
        placements = [
            {"placement_id": "P01", "sku": "NW-CHA-001", "finish_id": "F02", "x_mm": 100, "y_mm": 3000, "rotation_deg": 90}
        ]
        r_spec = dict(self.room_01)
        r_spec["capacity"] = 0

        layout = {"room_id": "ROOM-01", "placements": placements}
        res = self.arbitrator.arbitrate(layout, r_spec)
        self.assertEqual(res["status"], "valid")

    def test_e_sku_substitution_repair(self) -> None:
        # Desk NW-DES-003 (1600x600) near room wall boundary. Substitution to smaller SKU NW-DES-001 (1200x600).
        smaller = self.arbitrator._get_smaller_skus_in_family("NW-DES-003")
        self.assertTrue(len(smaller) > 0)
        self.assertIn("NW-DES-001", smaller)

    def test_f_removal_rejected_for_capacity(self) -> None:
        # Layout with capacity 12 chairs. One chair P12 overlaps P11.
        # Removal of P12 fixes spatial overlap but drops chair count to 11 < 12.
        placements = [
            {"placement_id": f"P{i+1:02d}", "sku": "NW-CHA-001", "finish_id": "F02", "x_mm": 500 + (i % 6) * 700, "y_mm": 2000 + (i // 6) * 800, "rotation_deg": 0}
            for i in range(11)
        ]
        # P12 overlaps P11
        placements.append({"placement_id": "P12", "sku": "NW-CHA-001", "finish_id": "F02", "x_mm": 500 + 5 * 700, "y_mm": 2000 + 1 * 800, "rotation_deg": 0})

        layout = {"room_id": "ROOM-01", "placements": placements}
        res = self.arbitrator.arbitrate(layout, self.room_01)
        # Should NOT silently accept removal if seating falls below 12
        if res["status"] == "valid":
            seating = self.arbitrator.count_seating_capacity(ProposedLayout.from_dict(res))
            self.assertGreaterEqual(seating, 12)

    def test_g_canonical_state_hash_stability(self) -> None:
        l1 = ProposedLayout.from_dict({
            "room_id": "ROOM-01",
            "placements": [
                {"placement_id": "P01", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 500, "y_mm": 500, "rotation_deg": 0},
                {"placement_id": "P02", "sku": "NW-CHA-001", "finish_id": "F02", "x_mm": 1000, "y_mm": 1000, "rotation_deg": 90},
            ]
        })
        l2 = ProposedLayout.from_dict({
            "room_id": "ROOM-01",
            "placements": [
                {"placement_id": "P02", "sku": "NW-CHA-001", "finish_id": "F02", "x_mm": 1000, "y_mm": 1000, "rotation_deg": 90},
                {"placement_id": "P01", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 500, "y_mm": 500, "rotation_deg": 0},
            ]
        })
        self.assertEqual(l1.canonical_state_hash(), l2.canonical_state_hash())

    def test_h_deterministic_candidate_ordering(self) -> None:
        placements = [
            {"placement_id": "P01", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 50, "y_mm": 3000, "rotation_deg": 0}
        ]
        r_spec = dict(self.room_01)
        r_spec["capacity"] = 0
        layout = {"room_id": "ROOM-01", "placements": placements}

        res1 = self.arbitrator.arbitrate(layout, r_spec)
        res2 = self.arbitrator.arbitrate(layout, r_spec)
        self.assertEqual(json.dumps(res1, sort_keys=True), json.dumps(res2, sort_keys=True))

    def test_i_search_space_exhaustion(self) -> None:
        # Desk at x=50, y=3000 (triggers RB-GEO-005). Step 1 nudges to x=150 (spatial violations become 0).
        # In step 2, spatial violations are 0, so candidate frontier is empty -> local_repair_exhausted!
        placements = [
            {"placement_id": "P01", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 50, "y_mm": 3000, "rotation_deg": 0}
        ]
        r_spec = dict(self.room_01)
        r_spec["capacity"] = 10

        layout = {"room_id": "ROOM-01", "placements": placements}
        res = self.arbitrator.arbitrate(layout, r_spec)
        self.assertEqual(res["status"], "unsatisfiable")

        # Verify termination reason is local_repair_exhausted
        if res["violations"]:
            meas = res["violations"][0].get("measured", {})
            self.assertEqual(meas.get("termination_reason"), "local_repair_exhausted")

        # Verify schema compliance
        req_keys = set(self.layout_schema["required"])
        self.assertTrue(req_keys.issubset(set(res.keys())))
        extra_keys = set(res.keys()) - set(self.layout_schema["properties"].keys())
        self.assertEqual(extra_keys, set())

    def test_j_operational_limit_reached(self) -> None:
        # Layout with multiple items requiring > k_max steps to resolve
        placements = [
            {"placement_id": f"P{i+1:02d}", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 600, "y_mm": 100 + i * 50, "rotation_deg": 0}
            for i in range(5)
        ]
        r_spec = dict(self.room_01)
        r_spec["capacity"] = 10
        layout = {"room_id": "ROOM-01", "placements": placements}
        res = self.arbitrator.arbitrate(layout, r_spec)
        self.assertEqual(res["status"], "unsatisfiable")
        if res["violations"]:
            meas = res["violations"][0].get("measured", {})
            self.assertEqual(meas.get("termination_reason"), "operational_limit_reached")

    def test_k_capacity_only_escalation_provenance(self) -> None:
        # Single placement far away from walls/doors (0 spatial violations), but capacity=10 chairs required
        placements = [
            {"placement_id": "P01", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 2000, "y_mm": 3000, "rotation_deg": 0}
        ]
        r_spec = dict(self.room_01)
        r_spec["capacity"] = 10

        layout = {"room_id": "ROOM-01", "placements": placements}
        res = self.arbitrator.arbitrate(layout, r_spec)
        self.assertEqual(res["status"], "unsatisfiable")
        self.assertEqual(len(res["violations"]), 1)
        v = res["violations"][0]
        # Must NOT use RB-GEO-007; must use implementation-owned CAPACITY_FEASIBILITY
        self.assertEqual(v["rule_id"], "CAPACITY_FEASIBILITY")
        self.assertNotEqual(v["rule_id"], "RB-GEO-007")

    def test_l_no_input_mutation(self) -> None:
        layout = {
            "room_id": "ROOM-01",
            "placements": [
                {"placement_id": "P01", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 50, "y_mm": 3000, "rotation_deg": 0}
            ]
        }
        json_before = json.dumps(layout, sort_keys=True)
        self.arbitrator.arbitrate(layout, self.room_01)
        json_after = json.dumps(layout, sort_keys=True)
        self.assertEqual(json_before, json_after)

    def test_m_rule_id_provenance(self) -> None:
        placements = [
            {"placement_id": "P01", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 6800, "y_mm": 500, "rotation_deg": 0}
        ]
        r_spec = dict(self.room_01)
        r_spec["capacity"] = 10
        layout = {"room_id": "ROOM-01", "placements": placements}
        res = self.arbitrator.arbitrate(layout, r_spec)

        if res["violations"]:
            for v in res["violations"]:
                rule_id = v["rule_id"]
                # Must be a valid rule_id from rules.json or implementation CAPACITY_FEASIBILITY
                valid_ids = [r["rule_id"] for r in self.rules] + ["CAPACITY_FEASIBILITY"]
                self.assertIn(rule_id, valid_ids)


if __name__ == "__main__":
    unittest.main()
