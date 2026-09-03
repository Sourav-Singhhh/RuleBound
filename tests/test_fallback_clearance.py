"""
Unit and regression tests for fallback desk placement RB-GEO-004 rear clearance preservation.
"""
import json
import unittest
from pathlib import Path
from starter.python.rulebound_loader import load_asset_pack
from src.generator import GeneratorEngine
from src.constraints import ConstraintEngine
from src.arbitration import ArbitrationEngine

class TestFallbackClearance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Path(__file__).resolve().parent.parent
        cls.pack = load_asset_pack(cls.repo / "data")
        rules_list = cls.pack.rules["rules"] if isinstance(cls.pack.rules, dict) else cls.pack.rules
        cls.generator = GeneratorEngine(cls.pack.catalog, cls.pack.finishes, rules_list, cls.pack.historical_jobs)
        cls.constraints = ConstraintEngine(cls.pack.catalog, cls.pack.finishes, rules_list)
        cls.arbitration = ArbitrationEngine(cls.pack.catalog, cls.pack.finishes, rules_list, cls.constraints)
        cls.rooms_by_id = {r["room_id"]: r for r in cls.pack.rooms}

    def test_fallback_cannot_intrude_into_desk_rear_clearance(self):
        """
        Requirement A: Proves that fallback placement cannot place any furniture
        or secondary desk inside a placed desk's 900mm rear-clearance zone.
        """
        room_spec = {
            "room_id": "TEST-CLEARANCE-INTERFERENCE",
            "capacity": 2,
            "boundary_mm": [[0, 0], [4000, 0], [4000, 3000], [0, 3000]],
            "doors": [{"door_id": "D1", "wall": "south", "offset_mm": 200, "width_mm": 900}],
            "egress": None
        }
        # Force single desk placement then test candidate placement searching with reserved zone
        occupied_boxes = [(500, 500, 2100, 1100)] # Desk NW-DES-003 at (500, 500)
        clearance_boxes = [(500, 1100, 2100, 2000)] # 900mm rear clearance [1100..2000]

        # Attempt to find placement for another desk (width=1600, depth=600)
        pos = self.generator._find_valid_placement(
            1600, 600, room_spec["boundary_mm"],
            300, 3700, 300, 2700,
            occupied_boxes,
            room_spec=room_spec,
            clearance_boxes=clearance_boxes,
            require_rear_clearance=True,
            rear_clearance_mm=900,
            rot=0
        )
        self.assertIsNotNone(pos)
        cx, cy = pos
        cand_box = (cx, cy, cx + 1600, cy + 600)
        
        # Verify candidate desk box does NOT overlap the rear clearance zone [500..2100] x [1100..2000]
        rx1, ry1, rx2, ry2 = clearance_boxes[0]
        overlap_x = max(0, min(cand_box[2], rx2) - max(cand_box[0], rx1))
        overlap_y = max(0, min(cand_box[3], ry2) - max(cand_box[1], ry1))
        self.assertTrue(overlap_x == 0 or overlap_y == 0, f"Candidate desk {cand_box} overlapped clearance zone {clearance_boxes[0]}")

    def test_room01_fallback_no_600mm_stacking(self):
        """
        Requirement B: Proves that ROOM-01 proposal desks no longer exhibit the 600mm
        desk-depth stacking pattern (y = 4800, 4200, 3600, 3000).
        """
        room_spec = self.rooms_by_id["ROOM-01"]
        brief = self.pack.briefs["ROOM-01"]
        proposal = self.generator.generate_proposal(room_spec, brief)
        desks = [p for p in proposal["placements"] if "DES" in p["sku"]]
        
        # Check all pairs of desks: if they overlap in X, their Y distance must be >= desk_depth + 900
        for i, d1 in enumerate(desks):
            w1 = self.generator.catalog_by_sku[d1["sku"]]["dimensions_mm"]["width"]
            d1_depth = self.generator.catalog_by_sku[d1["sku"]]["dimensions_mm"]["depth"]
            box1 = (d1["x_mm"], d1["y_mm"], d1["x_mm"] + w1, d1["y_mm"] + d1_depth)
            
            for j, d2 in enumerate(desks):
                if i == j:
                    continue
                w2 = self.generator.catalog_by_sku[d2["sku"]]["dimensions_mm"]["width"]
                d2_depth = self.generator.catalog_by_sku[d2["sku"]]["dimensions_mm"]["depth"]
                box2 = (d2["x_mm"], d2["y_mm"], d2["x_mm"] + w2, d2["y_mm"] + d2_depth)
                
                # Check if x intervals overlap
                x_overlap = max(0, min(box1[2], box2[2]) - max(box1[0], box2[0]))
                if x_overlap > 0 and box2[1] >= box1[3]:
                    # d2 is to the north of d1 and shares x span -> gap must be >= 900mm
                    y_gap = box2[1] - box1[3]
                    self.assertGreaterEqual(y_gap, 900, f"Desks {d1['placement_id']} and {d2['placement_id']} have only {y_gap}mm rear gap (< 900mm)")

    def test_constraint_engine_validates_zero_geo004_violations_on_room01(self):
        """
        Requirement C: Proves authoritative ConstraintEngine validation detects 0 RB-GEO-004 violations
        in ROOM-01 after applying arbitration.
        """
        room_spec = self.rooms_by_id["ROOM-01"]
        brief = self.pack.briefs["ROOM-01"]
        proposal = self.generator.generate_proposal(room_spec, brief)
        arb_res = self.arbitration.arbitrate(proposal, room_spec)
        val = self.constraints.validate_layout(arb_res, room_spec)
        
        geo004_viols = [v for v in val.get("violations", []) if v["rule_id"] == "RB-GEO-004"]
        self.assertEqual(len(geo004_viols), 0, f"Expected 0 RB-GEO-004 violations, got: {geo004_viols}")

    def test_determinism_byte_identical_across_runs(self):
        """
        Requirement D: Proves proposal generation and arbitration are 100% deterministic across multiple runs.
        """
        for r_id in ["ROOM-01", "ROOM-02", "ROOM-03", "ROOM-04", "ROOM-05"]:
            room_spec = self.rooms_by_id[r_id]
            brief = self.pack.briefs[r_id]
            
            run1_prop = self.generator.generate_proposal(room_spec, brief)
            run2_prop = self.generator.generate_proposal(room_spec, brief)
            self.assertEqual(json.dumps(run1_prop, sort_keys=True), json.dumps(run2_prop, sort_keys=True))
            
            run1_arb = self.arbitration.arbitrate(run1_prop, room_spec)
            run2_arb = self.arbitration.arbitrate(run2_prop, room_spec)
            self.assertEqual(json.dumps(run1_arb, sort_keys=True), json.dumps(run2_arb, sort_keys=True))

if __name__ == "__main__":
    unittest.main()
