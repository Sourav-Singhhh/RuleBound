"""
Unit tests for Deterministic Generator Engine (src/generator.py).
Tests capacity extraction, finish selection, SKU ranking, placement grid, and determinism across all 5 released rooms.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from src.generator import GeneratorEngine

ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class TestGeneratorEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = read_json(ROOT / "data" / "catalog.json")
        cls.finishes = read_json(ROOT / "data" / "finishes.json")
        cls.rules = read_json(ROOT / "data" / "rules.json")["rules"]
        cls.hist_jobs = read_json(ROOT / "data" / "historical_jobs.json")

        cls.rooms = {
            f"ROOM-0{i}": read_json(ROOT / "data" / "rooms" / f"ROOM-0{i}.json")
            for i in range(1, 6)
        }
        cls.briefs = {
            f"ROOM-0{i}": (ROOT / "data" / "briefs" / f"ROOM-0{i}.txt").read_text(encoding="utf-8")
            for i in range(1, 6)
        }

        cls.generator = GeneratorEngine(cls.catalog, cls.finishes, cls.rules, cls.hist_jobs)

    def test_1_byte_identical_determinism(self) -> None:
        p1 = self.generator.generate_proposal(self.rooms["ROOM-01"], self.briefs["ROOM-01"])
        p2 = self.generator.generate_proposal(self.rooms["ROOM-01"], self.briefs["ROOM-01"])
        self.assertEqual(json.dumps(p1, sort_keys=True), json.dumps(p2, sort_keys=True))

    def test_2_five_brief_requirement_extraction(self) -> None:
        # ROOM-01: 12 chairs, 12 desks, 2 storage, 1 collaboration
        c01 = self.generator.parse_capacity(self.rooms["ROOM-01"], self.briefs["ROOM-01"])
        f01 = self.generator.parse_furniture_counts(self.briefs["ROOM-01"], c01)
        self.assertEqual(c01, 12)
        self.assertEqual(f01["desk"], 12)
        self.assertEqual(f01["storage"], 2)
        self.assertEqual(f01["collaboration"], 1)

        # ROOM-02: 16 chairs, 16 desks, 0 storage (unquantified), 2 collaboration ("two collaboration tables")
        c02 = self.generator.parse_capacity(self.rooms["ROOM-02"], self.briefs["ROOM-02"])
        f02 = self.generator.parse_furniture_counts(self.briefs["ROOM-02"], c02)
        self.assertEqual(c02, 16)
        self.assertEqual(f02["desk"], 16)
        self.assertEqual(f02["storage"], 0)
        self.assertEqual(f02["collaboration"], 2)

        # ROOM-03: 10 chairs, 8 desks ("eight fixed work positions"), 0 storage, 1 collaboration ("a four-person touchdown table")
        c03 = self.generator.parse_capacity(self.rooms["ROOM-03"], self.briefs["ROOM-03"])
        f03 = self.generator.parse_furniture_counts(self.briefs["ROOM-03"], c03)
        self.assertEqual(c03, 10)
        self.assertEqual(f03["desk"], 8)
        self.assertEqual(f03["storage"], 0)
        self.assertEqual(f03["collaboration"], 1)

        # ROOM-04: 14 chairs, 14 desks, 0 storage ("distributed storage" is unquantified), 0 collaboration
        c04 = self.generator.parse_capacity(self.rooms["ROOM-04"], self.briefs["ROOM-04"])
        f04 = self.generator.parse_furniture_counts(self.briefs["ROOM-04"], c04)
        self.assertEqual(c04, 14)
        self.assertEqual(f04["desk"], 14)
        self.assertEqual(f04["storage"], 0)
        self.assertEqual(f04["collaboration"], 0)

        # ROOM-05: 18 chairs, 12 desks ("twelve desk positions"), 0 storage (unquantified), 0 collaboration ("two collaboration zones" is qualitative)
        c05 = self.generator.parse_capacity(self.rooms["ROOM-05"], self.briefs["ROOM-05"])
        f05 = self.generator.parse_furniture_counts(self.briefs["ROOM-05"], c05)
        self.assertEqual(c05, 18)
        self.assertEqual(f05["desk"], 12)
        self.assertEqual(f05["storage"], 0)
        self.assertEqual(f05["collaboration"], 0)

    def test_3_parser_grammar_cases(self) -> None:
        # Singular vs Plural tables
        f_sing = self.generator.parse_furniture_counts("Provide one collaboration table.", 10)
        self.assertEqual(f_sing["collaboration"], 1)

        f_plur = self.generator.parse_furniture_counts("Provide two collaboration tables.", 10)
        self.assertEqual(f_plur["collaboration"], 2)

        # Indefinite articles "a" / "an"
        f_art = self.generator.parse_furniture_counts("Include a four-person touchdown table.", 10)
        self.assertEqual(f_art["collaboration"], 1)

        # Workstation position phrases
        f_pos8 = self.generator.parse_furniture_counts("Include eight fixed work positions.", 10)
        self.assertEqual(f_pos8["desk"], 8)

        f_pos12 = self.generator.parse_furniture_counts("Provide twelve desk positions for the hub.", 18)
        self.assertEqual(f_pos12["desk"], 12)

        # Unquantified qualitative phrases do NOT invent quantities
        f_qual = self.generator.parse_furniture_counts("Provide accessible storage and distributed storage.", 10)
        self.assertEqual(f_qual["storage"], 0)

    def test_4_explicit_finish_selection(self) -> None:
        f_desk = self.generator.select_finish("desk", self.briefs["ROOM-01"])
        self.assertEqual(f_desk, "F01")
        f_chair = self.generator.select_finish("chair", self.briefs["ROOM-01"])
        self.assertEqual(f_chair, "F02")

    def test_5_cheapest_compatible_fallback_finish(self) -> None:
        f_chair = self.generator.select_finish("chair", "Simple workspace for 5 people.")
        f_obj = self.generator.finishes_by_id[f_chair]
        self.assertIn("chair", f_obj["compatible_families"])

    def test_6_incompatible_finish_never_selected(self) -> None:
        f_desk = self.generator.select_finish("desk", "Use acoustic felt gray for desks.")
        f_obj = self.generator.finishes_by_id[f_desk]
        self.assertIn("desk", f_obj["compatible_families"])

    def test_7_deterministic_sku_ranking(self) -> None:
        sku = self.generator.select_sku("desk", "F01")
        self.assertIsNotNone(sku)
        cat_item = self.generator.catalog_by_sku[sku]
        self.assertEqual(cat_item["family"], "desk")
        self.assertIn("F01", cat_item["compatible_finish_ids"])

    def test_8_deterministic_placement_ids(self) -> None:
        proposal = self.generator.generate_proposal(self.rooms["ROOM-01"], self.briefs["ROOM-01"])
        pids = [p["placement_id"] for p in proposal["placements"]]
        self.assertEqual(pids[0], "P001")
        self.assertEqual(pids[1], "P002")

    def test_9_grid_behavior_100mm(self) -> None:
        proposal = self.generator.generate_proposal(self.rooms["ROOM-01"], self.briefs["ROOM-01"])
        for p in proposal["placements"]:
            self.assertEqual(p["x_mm"] % 100, 0)
            self.assertEqual(p["y_mm"] % 100, 0)

    def test_10_l_shaped_room_03_boundary(self) -> None:
        proposal = self.generator.generate_proposal(self.rooms["ROOM-03"], self.briefs["ROOM-03"])
        for p in proposal["placements"]:
            self.assertFalse(p["x_mm"] > 4200 and p["y_mm"] > 4800)

    def test_11_no_random_timestamp_behavior(self) -> None:
        gen1 = GeneratorEngine(self.catalog, self.finishes, self.rules)
        gen2 = GeneratorEngine(self.catalog, self.finishes, self.rules)
        p1 = gen1.generate_proposal(self.rooms["ROOM-01"], self.briefs["ROOM-01"])
        p2 = gen2.generate_proposal(self.rooms["ROOM-01"], self.briefs["ROOM-01"])
        self.assertEqual(json.dumps(p1, sort_keys=True), json.dumps(p2, sort_keys=True))

    def test_12_historical_jobs_do_not_override_brief(self) -> None:
        proposal = self.generator.generate_proposal(self.rooms["ROOM-01"], self.briefs["ROOM-01"])
        chairs = [p for p in proposal["placements"] if self.generator.catalog_by_sku[p["sku"]]["family"] == "chair"]
        self.assertGreaterEqual(len(chairs), 12)

    def test_13_qualitative_language_no_numeric_constraints(self) -> None:
        brief_qual = "Create a visually open quiet focus library for 10 people."
        proposal = self.generator.generate_proposal(self.rooms["ROOM-01"], brief_qual)
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal["room_id"], "ROOM-01")

    def test_14_contract_conformance(self) -> None:
        proposal = self.generator.generate_proposal(self.rooms["ROOM-01"], self.briefs["ROOM-01"])
        self.assertEqual(set(proposal.keys()), {"room_id", "placements"})
        for p in proposal["placements"]:
            self.assertEqual(set(p.keys()), {"placement_id", "sku", "finish_id", "x_mm", "y_mm", "rotation_deg"})


if __name__ == "__main__":
    unittest.main()
