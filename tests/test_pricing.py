"""
Unit tests for Deterministic Pricing Engine (src/pricing.py).
Tests against PRICING_SPEC.md, reference quotes, boundary conditions, and determinism.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any, Dict

from src.pricing import (
    PricingEngine,
    calculate_freight,
    get_labour_rate_inr,
    get_quantity_discount_bps,
    round_half_up,
)

ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class TestPricingEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = read_json(ROOT / "data" / "catalog.json")
        cls.finishes = read_json(ROOT / "data" / "finishes.json")
        cls.engine = PricingEngine(cls.catalog, cls.finishes)
        cls.ref_quote_1 = read_json(ROOT / "data" / "reference_quotes" / "REF-QUOTE-01.json")
        cls.ref_quote_2 = read_json(ROOT / "data" / "reference_quotes" / "REF-QUOTE-02.json")

    def test_round_half_up(self) -> None:
        # Standard positive rounding
        self.assertEqual(round_half_up(1, 2), 1)     # 0.5 -> 1
        self.assertEqual(round_half_up(3, 2), 2)     # 1.5 -> 2
        self.assertEqual(round_half_up(1, 4), 0)     # 0.25 -> 0
        self.assertEqual(round_half_up(3, 4), 1)     # 0.75 -> 1
        self.assertEqual(round_half_up(54, 10), 5)   # 5.4 -> 5
        self.assertEqual(round_half_up(55, 10), 6)   # 5.5 -> 6
        self.assertEqual(round_half_up(56, 10), 6)   # 5.6 -> 6

    def test_quantity_discount_tiers(self) -> None:
        # 1-4: 0 bps
        self.assertEqual(get_quantity_discount_bps(1), 0)
        self.assertEqual(get_quantity_discount_bps(4), 0)
        # 5-9: 300 bps
        self.assertEqual(get_quantity_discount_bps(5), 300)
        self.assertEqual(get_quantity_discount_bps(9), 300)
        # 10-19: 700 bps
        self.assertEqual(get_quantity_discount_bps(10), 700)
        self.assertEqual(get_quantity_discount_bps(19), 700)
        # 20+: 1000 bps
        self.assertEqual(get_quantity_discount_bps(20), 1000)
        self.assertEqual(get_quantity_discount_bps(100), 1000)

    def test_labour_rate_tiers(self) -> None:
        # Up to 240 mins: 900 INR/hr
        self.assertEqual(get_labour_rate_inr(0), 900)
        self.assertEqual(get_labour_rate_inr(240), 900)
        # 241 to 480 mins: 800 INR/hr
        self.assertEqual(get_labour_rate_inr(241), 800)
        self.assertEqual(get_labour_rate_inr(480), 800)
        # Above 480 mins: 750 INR/hr
        self.assertEqual(get_labour_rate_inr(481), 750)
        self.assertEqual(get_labour_rate_inr(600), 750)

    def test_freight_tiers(self) -> None:
        # Up to 100,000 INR -> 5,000 INR flat
        amt1, inputs1 = calculate_freight(50000)
        self.assertEqual(amt1, 5000)
        self.assertEqual(inputs1["band"], "up_to_100000")

        amt2, inputs2 = calculate_freight(100000)
        self.assertEqual(amt2, 5000)
        self.assertEqual(inputs2["band"], "up_to_100000")

        # 100,001 to 250,000 INR -> 9,000 INR flat
        amt3, inputs3 = calculate_freight(100001)
        self.assertEqual(amt3, 9000)
        self.assertEqual(inputs3["band"], "100001_to_250000")

        amt4, inputs4 = calculate_freight(250000)
        self.assertEqual(amt4, 9000)
        self.assertEqual(inputs4["band"], "100001_to_250000")

        # Above 250,000 INR -> 4% (400 bps)
        amt5, inputs5 = calculate_freight(250001)
        self.assertEqual(amt5, round_half_up(250001 * 400, 10000))
        self.assertEqual(inputs5["band"], "above_250000")

    def test_reference_quote_01(self) -> None:
        line_inputs = [
            {"line_id": line["line_id"], "sku": line["sku"], "finish_id": line["finish_id"], "quantity": line["quantity"]}
            for line in self.ref_quote_1["lines"]
        ]
        calculated = self.engine.calculate_quote("REF-QUOTE-01", "ROOM-01", line_inputs)
        self.assertEqual(calculated, self.ref_quote_1)

    def test_reference_quote_02(self) -> None:
        line_inputs = [
            {"line_id": line["line_id"], "sku": line["sku"], "finish_id": line["finish_id"], "quantity": line["quantity"]}
            for line in self.ref_quote_2["lines"]
        ]
        calculated = self.engine.calculate_quote("REF-QUOTE-02", "ROOM-02", line_inputs)
        self.assertEqual(calculated, self.ref_quote_2)

    def test_unpriced_sku_blocks_quote(self) -> None:
        line_inputs = [
            {"line_id": "L001", "sku": "INVALID-SKU-999", "finish_id": "F01", "quantity": 1}
        ]
        result = self.engine.calculate_quote("Q-BLOCK-1", "ROOM-01", line_inputs)
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(len(result["blocking_reasons"]) > 0)
        self.assertTrue(any("RB-PRC-013" in r for r in result["blocking_reasons"]))
        self.assertEqual(result["lines"], [])

    def test_incompatible_finish_blocks_quote(self) -> None:
        # F18 is Premium Leather Black, compatible ONLY with 'chair'. Trying it with a 'desk' SKU.
        line_inputs = [
            {"line_id": "L001", "sku": "NW-DES-001", "finish_id": "F18", "quantity": 1}
        ]
        result = self.engine.calculate_quote("Q-BLOCK-2", "ROOM-01", line_inputs)
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(len(result["blocking_reasons"]) > 0)
        self.assertTrue(any("RB-PRC-013" in r for r in result["blocking_reasons"]))

    def test_deterministic_repeatability(self) -> None:
        line_inputs = [
            {"line_id": "L001", "sku": "NW-DES-003", "finish_id": "F03", "quantity": 6},
            {"line_id": "L002", "sku": "NW-CHA-004", "finish_id": "F15", "quantity": 12},
        ]
        res1 = self.engine.calculate_quote("Q-DET", "ROOM-01", line_inputs)
        res2 = self.engine.calculate_quote("Q-DET", "ROOM-01", line_inputs)
        self.assertEqual(json.dumps(res1, sort_keys=True), json.dumps(res2, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
