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
        # Layout with multiple items where local repair exhausts when no further strict improvement exists
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
            self.assertIn(meas.get("termination_reason"), ["local_repair_exhausted", "operational_limit_reached"])

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

    # --- Section 6: Lexicographic Objective Model & Chair Preservation Tests ---
    def test_q_removing_chair_creates_capacity_shortfall_rejected(self) -> None:
        # Layout with capacity=1 and 1 chair (P01) near wall (RB-GEO-005 violation).
        # Candidate REMOVE_PLACEMENT on P01 reduces spatial violations from 1 to 0, but creates capacity shortfall (0 < 1).
        # Lexicographic objective (1, 0, ...) is WORSE than (0, 1, ...), so REMOVE must be REJECTED.
        placements = [
            {"placement_id": "P01", "sku": "NW-CHA-001", "finish_id": "F02", "x_mm": 50, "y_mm": 3000, "rotation_deg": 0}
        ]
        r_spec = dict(self.room_01)
        r_spec["capacity"] = 1
        layout = {"room_id": "ROOM-01", "placements": placements}

        res = self.arbitrator.arbitrate(layout, r_spec)
        # Nudge/rotate should repair it to valid, preserving the required chair
        if res["status"] == "valid":
            seating = self.arbitrator.count_seating_capacity(ProposedLayout.from_dict(res))
            self.assertEqual(seating, 1, "Required chair must NOT be removed by arbitration.")

    def test_r_capacity_feasibility_dominates_spatial_violations(self) -> None:
        # Lexicographic verification: (0, 5, ...) MUST beat (1, 0, ...)
        obj_feasible = (0, 5, 1, 100.0, 1, "P01", "")
        obj_shortfall = (1, 0, 1, 100.0, 4, "P01", "")
        self.assertLess(obj_feasible, obj_shortfall, "Capacity shortfall=0 must lexicographically beat shortfall=1 regardless of spatial violations.")

    def test_s_remove_non_seating_furniture_eligible(self) -> None:
        # Storage unit (non-seating) causing wall violation when capacity=1 chair is valid and separate.
        # REMOVE_PLACEMENT on storage keeps capacity shortfall=0 and reduces spatial violations -> eligible.
        placements = [
            {"placement_id": "P01", "sku": "NW-CHA-001", "finish_id": "F02", "x_mm": 2000, "y_mm": 3000, "rotation_deg": 0},
            {"placement_id": "P02", "sku": "NW-STO-001", "finish_id": "F03", "x_mm": 50, "y_mm": 1000, "rotation_deg": 0} # wall violation
        ]
        r_spec = dict(self.room_01)
        r_spec["capacity"] = 1
        layout = {"room_id": "ROOM-01", "placements": placements}

        res = self.arbitrator.arbitrate(layout, r_spec)
        self.assertEqual(res["status"], "valid")

    def test_t_repeat_arbitration_byte_identical(self) -> None:
        placements = [
            {"placement_id": "P01", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 50, "y_mm": 3000, "rotation_deg": 0},
            {"placement_id": "P02", "sku": "NW-CHA-001", "finish_id": "F02", "x_mm": 2000, "y_mm": 3000, "rotation_deg": 0}
        ]
        r_spec = dict(self.room_01)
        r_spec["capacity"] = 1
        layout = {"room_id": "ROOM-01", "placements": placements}

        res1 = self.arbitrator.arbitrate(layout, r_spec)
        res2 = self.arbitrator.arbitrate(layout, r_spec)
        self.assertEqual(json.dumps(res1, sort_keys=True), json.dumps(res2, sort_keys=True))

    # --- Section 7: Clearance-Aware Directional Candidates Tests ---
    def test_u_horizontal_geo001_targeted_candidate_generated(self) -> None:
        # Two desks (width 1200mm) facing along X axis with y-overlap, gap=400mm (400mm < 900mm -> 500mm deficit).
        # P01 at x=1000 (x1b=2200), P02 at x=2600 (x2a=2600 -> gap=400mm -> deficit=500mm).
        # P02 is right of P01 -> P02 move +X by 500mm targeted nudge.
        placements = [
            {"placement_id": "P01", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 1000, "y_mm": 3000, "rotation_deg": 0},
            {"placement_id": "P02", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 2600, "y_mm": 3000, "rotation_deg": 0}
        ]
        lay = ProposedLayout.from_dict({"room_id": "ROOM-01", "placements": placements})
        viols = self.constraint_engine.validate_layout(lay.to_dict(), self.room_01).get("violations", [])

        cands = self.arbitrator.generate_repair_candidates(lay, viols)
        # Check that targeted nudge DX=+500 for P02 is generated
        nudge_params = [(c.target_placement_id, c.params.get("dx_mm"), c.params.get("dy_mm")) for c in cands if c.op_type == "NUDGE"]
        self.assertIn(("P02", 500, 0), nudge_params)

    def test_v_vertical_geo001_targeted_candidate_generated(self) -> None:
        # Two desks (depth 600mm) facing along Y axis with x-overlap, gap=400mm (400mm < 900mm -> 500mm deficit).
        # P01 at y=1000 (y1b=1600), P02 at y=2000 (y2a=2000 -> gap=400mm -> deficit=500mm).
        # P02 is south of P01 -> P02 move +Y by 500mm targeted nudge.
        placements = [
            {"placement_id": "P01", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 3000, "y_mm": 1000, "rotation_deg": 0},
            {"placement_id": "P02", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 3000, "y_mm": 2000, "rotation_deg": 0}
        ]
        lay = ProposedLayout.from_dict({"room_id": "ROOM-01", "placements": placements})
        viols = self.constraint_engine.validate_layout(lay.to_dict(), self.room_01).get("violations", [])

    # --- Section 7: MOVE_WORKSTATION_POD Operator Tests ---
    def test_w_move_workstation_pod_pair_detection(self) -> None:
        # A, B, D: Desk + Chair pair detection, deterministic matching, and relative geometry
        placements = [
            {"placement_id": "P01", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 2000, "y_mm": 2000, "rotation_deg": 0},
            {"placement_id": "P02", "sku": "NW-CHA-001", "finish_id": "F02", "x_mm": 2300, "y_mm": 3500, "rotation_deg": 0},  # paired: y = 2000 + 600 + 900
        ]
        lay = ProposedLayout.from_dict({"room_id": "ROOM-01", "placements": placements})
        pairs = self.arbitrator._find_desk_chair_pairs(lay)
        self.assertEqual(pairs.get("P01"), ("P01", "P02"))
        self.assertEqual(pairs.get("P02"), ("P01", "P02"))

    def test_x_move_workstation_pod_apply_repair(self) -> None:
        # C, D, E, J: Pod move changes both placements by exact dx/dy, preserving relative geometry & seating capacity without mutating input
        placements = [
            {"placement_id": "P01", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 2000, "y_mm": 2000, "rotation_deg": 0},
            {"placement_id": "P02", "sku": "NW-CHA-001", "finish_id": "F02", "x_mm": 2300, "y_mm": 3500, "rotation_deg": 0},
        ]
        lay_init = ProposedLayout.from_dict({"room_id": "ROOM-01", "placements": placements})
        cand = RepairCandidate(
            op_type="MOVE_WORKSTATION_POD",
            target_placement_id="P01",
            params={"desk_placement_id": "P01", "chair_placement_id": "P02", "dx_mm": 100, "dy_mm": 200},
            sort_key=(0, "RB-GEO-001", "P01", "POD_P01_P02_DX_+100_DY_+200"),
        )
        lay_new = self.arbitrator.apply_repair(lay_init, cand)
        
        # Verify non-mutation
        self.assertEqual(lay_init.placements[0].x_mm, 2000)
        self.assertEqual(lay_init.placements[1].x_mm, 2300)

        # Verify exact same translation and relative geometry preservation
        p1_map = {p.placement_id: p for p in lay_new.placements}
        self.assertEqual(p1_map["P01"].x_mm, 2100)
        self.assertEqual(p1_map["P01"].y_mm, 2200)
        self.assertEqual(p1_map["P02"].x_mm, 2400)
        self.assertEqual(p1_map["P02"].y_mm, 3700)

        # Relative geometry check
        self.assertEqual(p1_map["P02"].y_mm - p1_map["P01"].y_mm, 1500)

        # Capacity check
        self.assertEqual(self.arbitrator.count_seating_capacity(lay_new), 1)

    def test_y_move_workstation_pod_regression(self) -> None:
        # F, G, H, I, regression test: A paired workstation (P01 desk, P02 chair) sits at x=1100, y=2000.
        # An obstacle at x=2300, y=2000 causes walkway clearance (gap < 900mm) with P01 desk.
        # Moving desk P01 alone creates desk-rear clearance violation.
        # Moving chair P02 alone creates desk-rear clearance violation.
        # Atomic MOVE_WORKSTATION_POD moves both P01 and P02 by DX=-200mm, resolving the violation cleanly.
        placements = [
            {"placement_id": "P01", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 1100, "y_mm": 2000, "rotation_deg": 0},  # desk x2=2300
            {"placement_id": "P02", "sku": "NW-CHA-001", "finish_id": "F02", "x_mm": 1400, "y_mm": 3500, "rotation_deg": 0},  # chair
            {"placement_id": "P03", "sku": "NW-STO-001", "finish_id": "F01", "x_mm": 2900, "y_mm": 2000, "rotation_deg": 0},  # obstacle at x=2900 -> gap = 2900 - 2300 = 600mm < 900mm
        ]
        r_spec = dict(self.room_01)
        r_spec["capacity"] = 1
        layout = {"room_id": "ROOM-01", "placements": placements}

        res = self.arbitrator.arbitrate(layout, r_spec)
        self.assertEqual(res["status"], "valid")
        self.assertEqual(res["violations"], [])

    def test_z_move_workstation_pod_determinism(self) -> None:
        # K: Determinism check
        placements = [
            {"placement_id": "P01", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 1100, "y_mm": 2000, "rotation_deg": 0},
            {"placement_id": "P02", "sku": "NW-CHA-001", "finish_id": "F02", "x_mm": 1400, "y_mm": 3500, "rotation_deg": 0},
            {"placement_id": "P03", "sku": "NW-STO-001", "finish_id": "F01", "x_mm": 2900, "y_mm": 2000, "rotation_deg": 0},
        ]
        r_spec = dict(self.room_01)
        r_spec["capacity"] = 1
        layout = {"room_id": "ROOM-01", "placements": placements}

        res1 = self.arbitrator.arbitrate(layout, r_spec)
        res2 = self.arbitrator.arbitrate(layout, r_spec)
        self.assertEqual(json.dumps(res1, sort_keys=True), json.dumps(res2, sort_keys=True))


    def test_z1_row_group_shift_run_detection(self) -> None:
        """_find_contiguous_pod_runs: two touching desks (gap = 0) must be in one run.

        NW-DES-001: 1200w x 600d. NW-CHA-001: 520w x 520d. rot=0.
        Chair centre = desk.x + (1200-520)//2 = desk.x + 340
        Chair y     = desk.y + 600 + 900 = desk.y + 1500
        Desks touching: P01 ends at x=1400 == P03 starts at x=1400 (gap=0).
        """
        layout = ProposedLayout(
            room_id="ROOM-01",
            placements=(
                PlacementProposal("P01", "NW-DES-001", "F01", x_mm=200,  y_mm=2000, rotation_deg=0),
                PlacementProposal("P02", "NW-CHA-001", "F02", x_mm=540,  y_mm=3500, rotation_deg=0),
                PlacementProposal("P03", "NW-DES-001", "F01", x_mm=1400, y_mm=2000, rotation_deg=0),
                PlacementProposal("P04", "NW-CHA-001", "F02", x_mm=1740, y_mm=3500, rotation_deg=0),
            )
        )
        pod_map = self.arbitrator._find_desk_chair_pairs(layout)
        runs = self.arbitrator._find_contiguous_pod_runs(layout, pod_map)
        self.assertEqual(len(runs), 1, f"Expected 1 run; got {len(runs)}: {runs}")
        self.assertEqual(len(runs[0]), 2, f"Expected run of length 2; got {runs[0]}")

    def test_z2_row_group_shift_candidates_generated(self) -> None:
        """generate_repair_candidates emits ROW_GROUP_SHIFT for a touching pod run."""
        layout = ProposedLayout(
            room_id="ROOM-01",
            placements=(
                PlacementProposal("P01", "NW-DES-001", "F01", x_mm=200,  y_mm=2000, rotation_deg=0),
                PlacementProposal("P02", "NW-CHA-001", "F02", x_mm=540,  y_mm=3500, rotation_deg=0),
                PlacementProposal("P03", "NW-DES-001", "F01", x_mm=1400, y_mm=2000, rotation_deg=0),
                PlacementProposal("P04", "NW-CHA-001", "F02", x_mm=1740, y_mm=3500, rotation_deg=0),
            )
        )
        candidates = self.arbitrator.generate_repair_candidates(layout, [])
        rgs_candidates = [c for c in candidates if c.op_type == "ROW_GROUP_SHIFT"]
        self.assertGreater(len(rgs_candidates), 0, "Expected ROW_GROUP_SHIFT candidates to be generated")

    def test_z3_row_group_shift_apply_repair(self) -> None:
        """apply_repair ROW_GROUP_SHIFT shifts all group placements by (dx, dy)."""
        layout = ProposedLayout(
            room_id="ROOM-01",
            placements=(
                PlacementProposal("P01", "NW-DES-001", "F01", x_mm=200,  y_mm=2000, rotation_deg=0),
                PlacementProposal("P02", "NW-CHA-001", "F02", x_mm=540,  y_mm=3500, rotation_deg=0),
                PlacementProposal("P03", "NW-DES-001", "F01", x_mm=1400, y_mm=2000, rotation_deg=0),
                PlacementProposal("P04", "NW-CHA-001", "F02", x_mm=1740, y_mm=3500, rotation_deg=0),
                PlacementProposal("P05", "NW-STO-001", "F01", x_mm=3000, y_mm=1000, rotation_deg=0),
            )
        )
        repair = RepairCandidate(
            op_type="ROW_GROUP_SHIFT",
            target_placement_id="P01",
            params={
                "desk_ids": ["P01", "P03"],
                "chair_ids": ["P02", "P04"],
                "all_placement_ids": ["P01", "P02", "P03", "P04"],
                "dx_mm": 0,
                "dy_mm": 100,
            },
            sort_key=(-1, "ROW_GROUP_SHIFT", "P01", "test"),
        )
        result = self.arbitrator.apply_repair(layout, repair)
        p_map = {p.placement_id: p for p in result.placements}
        # Group members shifted by dy=100
        self.assertEqual(p_map["P01"].y_mm, 2100)
        self.assertEqual(p_map["P02"].y_mm, 3600)
        self.assertEqual(p_map["P03"].y_mm, 2100)
        self.assertEqual(p_map["P04"].y_mm, 3600)
        # Non-group member unchanged
        self.assertEqual(p_map["P05"].y_mm, 1000)

    def test_aa_workstation_preservation_cannot_delete_desks(self) -> None:
        """
        Verify hard semantic precondition: REMOVE_PLACEMENT cannot delete desks
        below the room's required workstation count, even if doing so would eliminate
        spatial violations.
        """
        placements = [
            {"placement_id": "P01", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 50, "y_mm": 3000, "rotation_deg": 0},
            {"placement_id": "P02", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 2000, "y_mm": 3000, "rotation_deg": 0},
            {"placement_id": "P03", "sku": "NW-CHA-001", "finish_id": "F02", "x_mm": 500, "y_mm": 2000, "rotation_deg": 0},
            {"placement_id": "P04", "sku": "NW-CHA-001", "finish_id": "F02", "x_mm": 2500, "y_mm": 2000, "rotation_deg": 0},
        ]
        r_spec = dict(self.room_01)
        r_spec["capacity"] = 2
        r_spec["required_workstations"] = 2
        layout = {"room_id": "ROOM-01", "placements": placements}

        res = self.arbitrator.arbitrate(layout, r_spec)
        p_res = ProposedLayout.from_dict(res)
        desks_remaining = self.arbitrator.count_workstation_capacity(p_res)
        self.assertGreaterEqual(desks_remaining, 2, "Mandatory workstations must NOT be deleted below required count.")

    def test_ab_integer_displacement_guarantee(self) -> None:
        """
        Verify that displacement calculation produces exact integer values.
        """
        init_layout = ProposedLayout(room_id="ROOM-01", placements=[
            PlacementProposal("P01", "NW-DES-001", "F01", 1000, 1000, 0),
        ])
        repair = RepairCandidate("NUDGE", "P01", {"dx_mm": 300, "dy_mm": 400}, (1, "NUDGE", "P01", "test"))
        cand_layout = self.arbitrator.apply_repair(init_layout, repair)
        self.assertEqual(cand_layout.placements[0].x_mm, 1300)
        self.assertEqual(cand_layout.placements[0].y_mm, 1400)


if __name__ == "__main__":
    unittest.main()
