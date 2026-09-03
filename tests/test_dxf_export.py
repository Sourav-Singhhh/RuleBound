"""
Unit tests for tools/export_dxf.py (Bonus +5 points).
"""
import json
import unittest
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.export_dxf import export_room_to_dxf


class TestDXFExport(unittest.TestCase):
    def setUp(self):
        catalog_path = REPO / "data" / "catalog.json"
        self.catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        self.catalog_map = {item["sku"]: item for item in self.catalog}

    def test_dxf_export_structure(self):
        sample_room = {
            "room_id": "TEST-ROOM",
            "boundary_mm": [[0, 0], [5000, 0], [5000, 4000], [0, 4000]],
            "doors": [{"door_id": "D1", "wall": "south", "offset_mm": 1000, "width_mm": 900}],
            "egress": {"from_door_id": "D1", "to_point_mm": [2500, 3500], "min_width_mm": 1100}
        }
        sample_layout = {
            "room_id": "TEST-ROOM",
            "status": "valid",
            "placements": [
                {"placement_id": "P001", "sku": "NW-DES-001", "finish_id": "F01", "x_mm": 1000, "y_mm": 1000, "rotation_deg": 0},
                {"placement_id": "P002", "sku": "NW-CHA-001", "finish_id": "F01", "x_mm": 1000, "y_mm": 2000, "rotation_deg": 0},
            ]
        }
        dxf_str = export_room_to_dxf(sample_layout, sample_room, self.catalog_map)
        self.assertIn("HEADER", dxf_str)
        self.assertIn("TABLES", dxf_str)
        self.assertIn("ENTITIES", dxf_str)
        self.assertIn("WALLS", dxf_str)
        self.assertIn("DOORS", dxf_str)
        self.assertIn("EGRESS", dxf_str)
        self.assertIn("DESKS", dxf_str)
        self.assertIn("CHAIRS", dxf_str)
        self.assertIn("EOF", dxf_str)

    def test_all_official_rooms_export_to_dxf(self):
        for rid in ["ROOM-01", "ROOM-02", "ROOM-03", "ROOM-04", "ROOM-05"]:
            layout_path = REPO / "OUTPUT" / rid / "layout.json"
            room_path = REPO / "data" / "rooms" / f"{rid}.json"
            if layout_path.exists() and room_path.exists():
                l_data = json.loads(layout_path.read_text(encoding="utf-8"))
                r_data = json.loads(room_path.read_text(encoding="utf-8"))
                dxf_str = export_room_to_dxf(l_data, r_data, self.catalog_map)
                self.assertGreater(len(dxf_str), 1000)
                self.assertTrue(dxf_str.endswith("0\nEOF\n"))


if __name__ == "__main__":
    unittest.main()
