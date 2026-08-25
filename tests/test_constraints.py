"""
Unit tests for Deterministic Constraint Engine (src/constraints.py).
Tests spatial GEO rules, boundary cases, violation schemas, and deterministic ordering.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from src.constraints import ConstraintEngine, get_placement_bbox

ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class TestConstraintEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = read_json(ROOT / "data" / "catalog.json")
        cls.finishes = read_json(ROOT / "data" / "finishes.json")
        cls.rules = read_json(ROOT / "data" / "rules.json")["rules"]
        cls.room_01 = read_json(ROOT / "data" / "rooms" / "ROOM-01.json")
        cls.room_03 = read_json(ROOT / "data" / "rooms" / "ROOM-03.json")
        cls.engine = ConstraintEngine(cls.catalog, cls.finishes, cls.rules)

    def test_valid_layout(self) -> None:
        layout = {
            "room_id": "ROOM-01",
            "placements": [
                {
                    "placement_id": "P01",
                    "sku": "NW-DES-001",  # 1200x600 desk
                    "finish_id": "F01",
                    "x_mm": 500,
                    "y_mm": 3000,
                    "rotation_deg": 0
                }
            ]
        }
        res = self.engine.validate_layout(layout, self.room_01)
        self.assertEqual(res["status"], "valid")
        self.assertEqual(res["violations"], [])

    def test_geo_007_out_of_room_boundary(self) -> None:
        layout = {
            "room_id": "ROOM-01",
            "placements": [
                {
                    "placement_id": "P01",
                    "sku": "NW-DES-001",
                    "finish_id": "F01",
                    "x_mm": 6800,  # 6800 + 1200 = 8000 > 7200 room width
                    "y_mm": 500,
                    "rotation_deg": 0
                }
            ]
        }
        res = self.engine.validate_layout(layout, self.room_01)
        self.assertEqual(res["status"], "invalid")
        rule_ids = [v["rule_id"] for v in res["violations"]]
        self.assertIn("RB-GEO-007", rule_ids)

    def test_room_03_l_shape_valid_footprint(self) -> None:
        # ROOM-03 is L-shaped. Valid footprint inside upper-left leg (x: 500-1700, y: 5000-5600)
        layout = {
            "room_id": "ROOM-03",
            "placements": [
                {
                    "placement_id": "P01",
                    "sku": "NW-DES-001",
                    "finish_id": "F01",
                    "x_mm": 500,
                    "y_mm": 5000,
                    "rotation_deg": 0
                }
            ]
        }
        res = self.engine.validate_layout(layout, self.room_03)
        rule_ids = [v["rule_id"] for v in res["violations"]]
        self.assertNotIn("RB-GEO-007", rule_ids)

    def test_room_03_l_shape_crosses_reentrant_corner(self) -> None:
        # Placement at x=4000, y=4500 (size 1200x600) spans x from 4000 to 5200 and y from 4500 to 5100.
        # It crosses the re-entrant corner at (4200, 4800) into the cutout area -> triggers RB-GEO-007
        layout = {
            "room_id": "ROOM-03",
            "placements": [
                {
                    "placement_id": "P01",
                    "sku": "NW-DES-001",
                    "finish_id": "F01",
                    "x_mm": 4000,
                    "y_mm": 4500,
                    "rotation_deg": 0
                }
            ]
        }
        res = self.engine.validate_layout(layout, self.room_03)
        self.assertEqual(res["status"], "invalid")
        rule_ids = [v["rule_id"] for v in res["violations"]]
        self.assertIn("RB-GEO-007", rule_ids)

    def test_room_03_l_shape_completely_in_cutout(self) -> None:
        # Placement at x=4500, y=5000 is completely inside the cutout area (x > 4200 and y > 4800)
        # Even though x < 6600 and y < 6200 outer bounding box -> triggers RB-GEO-007
        layout = {
            "room_id": "ROOM-03",
            "placements": [
                {
                    "placement_id": "P01",
                    "sku": "NW-DES-001",
                    "finish_id": "F01",
                    "x_mm": 4500,
                    "y_mm": 5000,
                    "rotation_deg": 0
                }
            ]
        }
        res = self.engine.validate_layout(layout, self.room_03)
        self.assertEqual(res["status"], "invalid")
        rule_ids = [v["rule_id"] for v in res["violations"]]
        self.assertIn("RB-GEO-007", rule_ids)

    def test_geo_005_wall_clearance_boundary(self) -> None:
        # Exactly 100 mm wall offset -> valid for RB-GEO-005
        layout_exact = {
            "room_id": "ROOM-01",
            "placements": [
                {
                    "placement_id": "P01",
                    "sku": "NW-DES-001",
                    "finish_id": "F01",
                    "x_mm": 100,
                    "y_mm": 100,
                    "rotation_deg": 0
                }
            ]
        }
        res_exact = self.engine.validate_layout(layout_exact, self.room_01)
        rule_ids_exact = [v["rule_id"] for v in res_exact["violations"]]
        self.assertNotIn("RB-GEO-005", rule_ids_exact)

        # 99 mm wall offset -> just below boundary -> triggers RB-GEO-005
        layout_below = {
            "room_id": "ROOM-01",
            "placements": [
                {
                    "placement_id": "P01",
                    "sku": "NW-DES-001",
                    "finish_id": "F01",
                    "x_mm": 99,
                    "y_mm": 500,
                    "rotation_deg": 0
                }
            ]
        }
        res_below = self.engine.validate_layout(layout_below, self.room_01)
        rule_ids_below = [v["rule_id"] for v in res_below["violations"]]
        self.assertIn("RB-GEO-005", rule_ids_below)

    def test_geo_006_overlap(self) -> None:
        layout = {
            "room_id": "ROOM-01",
            "placements": [
                {
                    "placement_id": "P01",
                    "sku": "NW-DES-001",  # [500, 500, 1700, 1100]
                    "finish_id": "F01",
                    "x_mm": 500,
                    "y_mm": 500,
                    "rotation_deg": 0
                },
                {
                    "placement_id": "P02",
                    "sku": "NW-CHA-001",  # [1000, 500, 1600, 1100] -> overlaps P01
                    "finish_id": "F02",
                    "x_mm": 1000,
                    "y_mm": 500,
                    "rotation_deg": 0
                }
            ]
        }
        res = self.engine.validate_layout(layout, self.room_01)
        self.assertEqual(res["status"], "invalid")
        rule_ids = [v["rule_id"] for v in res["violations"]]
        self.assertIn("RB-GEO-006", rule_ids)
        # Verify affected placements sorted
        v_overlap = next(v for v in res["violations"] if v["rule_id"] == "RB-GEO-006")
        self.assertEqual(v_overlap["affected_placement_ids"], ["P01", "P02"])

    def test_geo_003_door_swing(self) -> None:
        # ROOM-01 door D1 is on south wall (y=0), offset 500 mm, width 1000 mm
        # Placement right inside door swing zone
        layout = {
            "room_id": "ROOM-01",
            "placements": [
                {
                    "placement_id": "P01",
                    "sku": "NW-CHA-001",
                    "finish_id": "F02",
                    "x_mm": 600,
                    "y_mm": 100,
                    "rotation_deg": 0
                }
            ]
        }
        res = self.engine.validate_layout(layout, self.room_01)
        rule_ids = [v["rule_id"] for v in res["violations"]]
        self.assertIn("RB-GEO-003", rule_ids)

    def test_geo_002_egress_path(self) -> None:
        # ROOM-01 egress goes from door D1 (x=1000, y=0) to point (6600, 4800)
        # Placing furniture right on egress line
        layout = {
            "room_id": "ROOM-01",
            "placements": [
                {
                    "placement_id": "P01",
                    "sku": "NW-STO-001",
                    "finish_id": "F01",
                    "x_mm": 3800,
                    "y_mm": 2400,
                    "rotation_deg": 0
                }
            ]
        }
        res = self.engine.validate_layout(layout, self.room_01)
        rule_ids = [v["rule_id"] for v in res["violations"]]
        self.assertIn("RB-GEO-002", rule_ids)

    def test_geo_004_desk_rear_clearance(self) -> None:
        # Desk placed near north wall such that 900 mm rear clearance extends past room wall
        layout = {
            "room_id": "ROOM-01",
            "placements": [
                {
                    "placement_id": "P01",
                    "sku": "NW-DES-001",  # 1200x600
                    "finish_id": "F01",
                    "x_mm": 2000,
                    "y_mm": 4700,  # 4700 + 600 = 5300. Rear zone extends to 5300 + 900 = 6200 > 5400
                    "rotation_deg": 0
                }
            ]
        }
        res = self.engine.validate_layout(layout, self.room_01)
        rule_ids = [v["rule_id"] for v in res["violations"]]
        self.assertIn("RB-GEO-004", rule_ids)

    def test_geo_008_chair_rear_clearance(self) -> None:
        # Chair placed near north wall such that 750 mm pull-out extends past room wall
        layout = {
            "room_id": "ROOM-01",
            "placements": [
                {
                    "placement_id": "P01",
                    "sku": "NW-CHA-001",  # 600x600
                    "finish_id": "F02",
                    "x_mm": 2000,
                    "y_mm": 4500,  # 4500 + 600 = 5100. Rear zone 5100 + 750 = 5850 > 5400
                    "rotation_deg": 0
                }
            ]
        }
        res = self.engine.validate_layout(layout, self.room_01)
        rule_ids = [v["rule_id"] for v in res["violations"]]
        self.assertIn("RB-GEO-008", rule_ids)

    def test_geo_001_walkway_gap(self) -> None:
        # Two desks placed 400 mm apart (gap < 900 mm walkway)
        layout = {
            "room_id": "ROOM-01",
            "placements": [
                {
                    "placement_id": "P01",
                    "sku": "NW-DES-001",
                    "finish_id": "F01",
                    "x_mm": 500,
                    "y_mm": 500,
                    "rotation_deg": 0
                },
                {
                    "placement_id": "P02",
                    "sku": "NW-DES-002",
                    "finish_id": "F01",
                    "x_mm": 2100,  # P01 x2 is 500+1200=1700. Gap = 2100 - 1700 = 400 mm
                    "y_mm": 500,
                    "rotation_deg": 0
                }
            ]
        }
        res = self.engine.validate_layout(layout, self.room_01)
        rule_ids = [v["rule_id"] for v in res["violations"]]
        self.assertIn("RB-GEO-001", rule_ids)

    def test_deterministic_violation_ordering(self) -> None:
        # Layout with multiple violations
        layout = {
            "room_id": "ROOM-01",
            "placements": [
                {
                    "placement_id": "P02",
                    "sku": "NW-DES-001",
                    "finish_id": "F01",
                    "x_mm": 50,  # Wall clearance violation
                    "y_mm": 50,
                    "rotation_deg": 0
                },
                {
                    "placement_id": "P01",
                    "sku": "NW-CHA-001",
                    "finish_id": "F02",
                    "x_mm": 600,  # Door swing violation
                    "y_mm": 100,
                    "rotation_deg": 0
                }
            ]
        }
        res1 = self.engine.validate_layout(layout, self.room_01)
        res2 = self.engine.validate_layout(layout, self.room_01)

        self.assertEqual(res1, res2)
        # Check sequential IDs
        v_ids = [v["violation_id"] for v in res1["violations"]]
        self.assertEqual(v_ids, [f"V{i+1:03d}" for i in range(len(v_ids))])

        # Check sorted order of rule_ids
        rule_ids = [v["rule_id"] for v in res1["violations"]]
        self.assertEqual(rule_ids, sorted(rule_ids))

    def test_unmutated_input_layout(self) -> None:
        layout = {
            "room_id": "ROOM-01",
            "placements": [
                {
                    "placement_id": "P01",
                    "sku": "NW-DES-001",
                    "finish_id": "F01",
                    "x_mm": 50,
                    "y_mm": 50,
                    "rotation_deg": 0
                }
            ]
        }
        layout_json_before = json.dumps(layout, sort_keys=True)
        self.engine.validate_layout(layout, self.room_01)
        layout_json_after = json.dumps(layout, sort_keys=True)

        self.assertEqual(layout_json_before, layout_json_after)

    # --- Focused RB-GEO-001 Parallel Projection Clearance Tests ---
    def test_geo_001_parallel_corridor_under_900_triggers_violation(self) -> None:
        # Two desks placed in parallel facing Y channel at y=1000 and y=2200 (desk depth 600mm -> gap 600mm < 900mm)
        layout = {
            "room_id": "ROOM-01",
            "placements": [
                {"placement_id": "P01", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 1000, "y_mm": 1000, "rotation_deg": 0}, # size 1200x600 -> y ends at 1600
                {"placement_id": "P02", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 1000, "y_mm": 2200, "rotation_deg": 0}, # y starts at 2200 -> gap 600mm
            ]
        }
        res = self.engine.validate_layout(layout, self.room_01)
        rule_ids = [v["rule_id"] for v in res["violations"]]
        self.assertIn("RB-GEO-001", rule_ids)

    def test_geo_001_parallel_corridor_over_900_no_violation(self) -> None:
        # Two desks placed in parallel facing Y channel at y=1000 and y=3000 (gap 1000mm >= 900mm)
        layout = {
            "room_id": "ROOM-01",
            "placements": [
                {"placement_id": "P01", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 1000, "y_mm": 1000, "rotation_deg": 0}, # y ends at 2000
                {"placement_id": "P02", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 1000, "y_mm": 3000, "rotation_deg": 0}, # y starts at 3000 -> gap 1000mm
            ]
        }
        res = self.engine.validate_layout(layout, self.room_01)
        rule_ids = [v["rule_id"] for v in res["violations"]]
        self.assertNotIn("RB-GEO-001", rule_ids)

    def test_geo_001_diagonal_corner_neighbor_no_false_violation(self) -> None:
        # Desk at (1000, 1000) ending at (2200, 2000). Second desk at (2500, 2300) ending at (3700, 3300).
        # Diagonal bounding-box distance is ~424mm (< 900mm), but projections along X and Y do NOT overlap!
        layout = {
            "room_id": "ROOM-01",
            "placements": [
                {"placement_id": "P01", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 1000, "y_mm": 1000, "rotation_deg": 0},
                {"placement_id": "P02", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 2500, "y_mm": 2300, "rotation_deg": 0},
            ]
        }
        res = self.engine.validate_layout(layout, self.room_01)
        rule_ids = [v["rule_id"] for v in res["violations"]]
        self.assertNotIn("RB-GEO-001", rule_ids)

    def test_geo_001_workstation_desk_chair_relationship(self) -> None:
        # Desk at (1000, 1000) and paired task chair at (1300, 2000) behind desk.
        # Governed by RB-GEO-004/RB-GEO-008, must NOT trigger RB-GEO-001 walkway violation.
        layout = {
            "room_id": "ROOM-01",
            "placements": [
                {"placement_id": "P01", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 1000, "y_mm": 1000, "rotation_deg": 0},
                {"placement_id": "P02", "sku": "NW-CHA-001", "finish_id": "F02", "x_mm": 1300, "y_mm": 2000, "rotation_deg": 0},
            ]
        }
        res = self.engine.validate_layout(layout, self.room_01)
        rule_ids = [v["rule_id"] for v in res["violations"]]
        self.assertNotIn("RB-GEO-001", rule_ids)

    def test_geo_001_touching_furniture_preserved_semantics(self) -> None:
        # Two desks placed side-by-side touching with 0mm gap (x=1000 and x=2200).
        # Gap == 0mm does NOT trigger RB-GEO-001 walkway violation.
        layout = {
            "room_id": "ROOM-01",
            "placements": [
                {"placement_id": "P01", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 1000, "y_mm": 1000, "rotation_deg": 0},
                {"placement_id": "P02", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 2200, "y_mm": 1000, "rotation_deg": 0},
            ]
        }
        res = self.engine.validate_layout(layout, self.room_01)
        rule_ids = [v["rule_id"] for v in res["violations"]]
        self.assertNotIn("RB-GEO-001", rule_ids)

    def test_geo_001_unrelated_separate_zones_no_false_violation(self) -> None:
        # Furniture in separate room zones (storage at north-west, desk at south-east, gap > 900mm)
        layout = {
            "room_id": "ROOM-01",
            "placements": [
                {"placement_id": "P01", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 4000, "y_mm": 4000, "rotation_deg": 0},
                {"placement_id": "P02", "sku": "NW-STO-001", "finish_id": "F03", "x_mm": 1000, "y_mm": 1000, "rotation_deg": 0},
            ]
        }
        res = self.engine.validate_layout(layout, self.room_01)
        rule_ids = [v["rule_id"] for v in res["violations"]]
        self.assertNotIn("RB-GEO-001", rule_ids)


if __name__ == "__main__":
    unittest.main()
