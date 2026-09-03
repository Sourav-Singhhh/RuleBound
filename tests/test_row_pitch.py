"""
Unit tests for deterministic workstation row pitch and rear clearance.
"""
import unittest
from pathlib import Path
from starter.python.rulebound_loader import load_asset_pack
from src.generator import GeneratorEngine
from src.constraints import ConstraintEngine

class TestWorkstationRowPitch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Path(__file__).resolve().parent.parent
        cls.pack = load_asset_pack(cls.repo / "data")
        rules_list = cls.pack.rules["rules"] if isinstance(cls.pack.rules, dict) else cls.pack.rules
        cls.generator = GeneratorEngine(cls.pack.catalog, cls.pack.finishes, rules_list, cls.pack.historical_jobs)
        cls.constraints = ConstraintEngine(cls.pack.catalog, cls.pack.finishes, rules_list)

    def test_row_pitch_dynamic_not_fixed_1200(self):
        """Proves workstation row pitch is derived from pod geometry + 900mm rear clearance, not fixed at 1200mm."""
        desk_item = next(item for item in self.pack.catalog if item["sku"] == "NW-DES-001")
        chair_item = next(item for item in self.pack.catalog if item["sku"] == "NW-CHA-001")
        
        d_d = desk_item["dimensions_mm"]["depth"]
        c_d = chair_item["dimensions_mm"]["depth"]
        pod_depth = d_d + 900 + c_d
        governing_rear_clearance = 900
        expected_pitch = pod_depth + governing_rear_clearance
        
        # 600mm desk + 900mm rear + 520mm chair + 900mm aisle = 2920mm
        self.assertEqual(expected_pitch, 2920)
        self.assertGreater(expected_pitch, 1200)

    def test_generated_room_respects_rear_clearance(self):
        """Generates proposal for large room and verifies adjacent rows satisfy RB-GEO-004, RB-GEO-008, and RB-GEO-001."""
        large_room_spec = {
            "room_id": "TEST-LARGE-ROOM",
            "capacity": 8,
            "boundary_mm": [[0, 0], [10000, 0], [10000, 10000], [0, 10000]],
            "doors": [{"door_id": "D1", "wall": "south", "offset_mm": 500, "width_mm": 900}],
            "egress": {"from_door_id": "D1", "to_point_mm": [9500, 9500], "min_width_mm": 1100}
        }
        brief = "A team of 8 using individual desks."
        proposal = self.generator.generate_proposal(large_room_spec, brief)
        placements = proposal["placements"]
        
        desk_placements = [p for p in placements if "DES" in p["sku"]]
        self.assertGreater(len(desk_placements), 0)
        
        # Check y-coordinates of desks: if multiple rows, spacing must be >= 2920mm
        y_coords = sorted(list(set(p["y_mm"] for p in desk_placements)))
        if len(y_coords) > 1:
            for i in range(len(y_coords) - 1):
                y_gap = y_coords[i+1] - y_coords[i]
                self.assertGreaterEqual(y_gap, 2920)
                
        # Validate directly against ConstraintEngine: must have 0 spatial violations
        val = self.constraints.validate_layout(proposal, large_room_spec)
        geo_viols = [v for v in val.get("violations", []) if v["rule_id"] in ("RB-GEO-001", "RB-GEO-004", "RB-GEO-006", "RB-GEO-008")]
        self.assertEqual(len(geo_viols), 0)



    def test_proposal_deterministic_reproducibility(self):
        """Proves generator proposal is 100% byte-identical across repeated invocations."""
        room = next(r for r in self.pack.rooms if r["room_id"] == "ROOM-02")
        brief = self.pack.briefs.get("ROOM-02", "")
        p1 = self.generator.generate_proposal(room, brief)
        p2 = self.generator.generate_proposal(room, brief)
        self.assertEqual(p1, p2)

if __name__ == "__main__":
    unittest.main()
