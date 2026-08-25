"""
Deterministic Pricing Engine for RuleBound.
Implements PRICING_SPEC.md using integer INR and basis points.
No floating-point arithmetic, no external APIs, no non-determinism.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple


def round_half_up(numerator: int, denominator: int) -> int:
    """
    Rounds numerator / denominator half up using exact integer arithmetic.
    For non-negative numbers: (2 * numerator + denominator) // (2 * denominator)
    """
    if denominator <= 0:
        raise ValueError("Denominator must be positive")
    if numerator < 0:
        return -round_half_up(-numerator, denominator)
    return (2 * numerator + denominator) // (2 * denominator)


def get_quantity_discount_bps(quantity: int) -> int:
    """
    RB-PRC-009: Quantity discount tiers based on base_amount:
    - 1-4: 0 bps
    - 5-9: 300 bps
    - 10-19: 700 bps
    - 20+: 1000 bps
    """
    if quantity >= 20:
        return 1000
    elif quantity >= 10:
        return 700
    elif quantity >= 5:
        return 300
    else:
        return 0


def get_labour_rate_inr(total_minutes: int) -> int:
    """
    RB-PRC-011: Labour rate tiers:
    - up to 240 minutes: 900 INR/hour
    - 241 to 480 minutes: 800 INR/hour
    - above 480 minutes: 750 INR/hour
    """
    if total_minutes <= 240:
        return 900
    elif total_minutes <= 480:
        return 800
    else:
        return 750


def calculate_freight(net_goods_inr: int) -> Tuple[int, Dict[str, Any]]:
    """
    RB-PRC-012: Freight calculation based on total net goods:
    - up to 100,000 INR: 5,000 INR flat
    - 100,001 to 250,000 INR: 9,000 INR flat
    - above 250,000 INR: 4% of net goods (400 bps), round half up
    Returns (freight_inr, trace_inputs).
    """
    if net_goods_inr <= 100000:
        freight_inr = 5000
        inputs = {
            "band": "up_to_100000",
            "flat_inr": 5000,
            "goods_inr": net_goods_inr,
        }
    elif net_goods_inr <= 250000:
        freight_inr = 9000
        inputs = {
            "band": "100001_to_250000",
            "flat_inr": 9000,
            "goods_inr": net_goods_inr,
        }
    else:
        freight_inr = round_half_up(net_goods_inr * 400, 10000)
        inputs = {
            "band": "above_250000",
            "percent_bps": 400,
            "goods_inr": net_goods_inr,
        }
    return freight_inr, inputs


class PricingEngine:
    """
    Pricing Engine initialized with catalog and finishes lookup tables.
    """

    def __init__(self, catalog: Sequence[Dict[str, Any]], finishes: Sequence[Dict[str, Any]]):
        self.catalog_by_sku = {item["sku"]: item for item in catalog}
        self.finishes_by_id = {f["finish_id"]: f for f in finishes}

    def calculate_line_item(
        self,
        line_id: str,
        sku: str,
        finish_id: str,
        quantity: int
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Calculates line item pricing.
        Returns (line_dict, None) if successful, or (None, error_message) if unpriced/incompatible.
        """
        if sku not in self.catalog_by_sku:
            return None, f"SKU '{sku}' not found in catalog"

        if finish_id not in self.finishes_by_id:
            return None, f"Finish '{finish_id}' not found in finishes"

        catalog_item = self.catalog_by_sku[sku]
        finish_item = self.finishes_by_id[finish_id]

        family = catalog_item.get("family", "")
        compatible_finish_ids = catalog_item.get("compatible_finish_ids", [])
        compatible_families = finish_item.get("compatible_families", [])

        if finish_id not in compatible_finish_ids or family not in compatible_families:
            return None, f"Finish '{finish_id}' is incompatible with catalog SKU '{sku}'"

        unit_list_price = catalog_item["list_price_inr"]
        uplift_bps = finish_item["uplift_bps"]

        base_amount_inr = unit_list_price * quantity
        finish_uplift_inr = round_half_up(base_amount_inr * uplift_bps, 10000)

        discount_bps = get_quantity_discount_bps(quantity)
        quantity_discount_inr = round_half_up(base_amount_inr * discount_bps, 10000)

        net_goods_inr = base_amount_inr + finish_uplift_inr - quantity_discount_inr

        trace = [
            {
                "rule_id": "CATALOG",
                "inputs": {
                    "unit_price": unit_list_price,
                    "quantity": quantity,
                },
                "amount_inr": base_amount_inr,
            },
            {
                "rule_id": "RB-PRC-010",
                "inputs": {
                    "uplift_bps": uplift_bps,
                    "base_amount_inr": base_amount_inr,
                },
                "amount_inr": finish_uplift_inr,
            },
            {
                "rule_id": "RB-PRC-009",
                "inputs": {
                    "discount_bps": discount_bps,
                    "base_amount_inr": base_amount_inr,
                },
                "amount_inr": -quantity_discount_inr,
            },
        ]

        line_dict = {
            "line_id": line_id,
            "sku": sku,
            "finish_id": finish_id,
            "quantity": quantity,
            "unit_list_price_inr": unit_list_price,
            "base_amount_inr": base_amount_inr,
            "finish_uplift_inr": finish_uplift_inr,
            "quantity_discount_inr": quantity_discount_inr,
            "net_goods_inr": net_goods_inr,
            "trace": trace,
        }

        return line_dict, None

    def calculate_quote(
        self,
        quote_id: str,
        room_id: str,
        line_inputs: Sequence[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calculates complete quote for given room and line item inputs.
        line_inputs: list of dicts with keys ('line_id', 'sku', 'finish_id', 'quantity').
        Returns quote dictionary strictly adhering to quote.schema.json.
        """
        priced_lines = []
        blocking_reasons = []

        total_labour_minutes = 0

        for idx, item in enumerate(line_inputs):
            line_id = item.get("line_id", f"L{idx + 1:03d}")
            sku = item["sku"]
            finish_id = item["finish_id"]
            quantity = item["quantity"]

            line_dict, err = self.calculate_line_item(line_id, sku, finish_id, quantity)
            if err:
                blocking_reasons.append(f"Line {line_id}: {err}")
            else:
                priced_lines.append(line_dict)
                catalog_item = self.catalog_by_sku[sku]
                total_labour_minutes += catalog_item.get("labour_minutes", 0) * quantity

        if blocking_reasons:
            return {
                "quote_id": quote_id,
                "room_id": room_id,
                "currency": "INR",
                "lines": [],
                "summary": {
                    "grand_total_inr": 0
                },
                "summary_trace": [],
                "status": "blocked",
                "blocking_reasons": blocking_reasons,
            }

        goods_after_adjustments_inr = sum(line["net_goods_inr"] for line in priced_lines)

        labour_rate = get_labour_rate_inr(total_labour_minutes)
        labour_inr = round_half_up(total_labour_minutes * labour_rate, 60)

        freight_inr, freight_trace_inputs = calculate_freight(goods_after_adjustments_inr)

        grand_total_inr = goods_after_adjustments_inr + labour_inr + freight_inr

        summary = {
            "goods_after_adjustments_inr": goods_after_adjustments_inr,
            "labour_minutes": total_labour_minutes,
            "labour_rate_inr_per_hour": labour_rate,
            "labour_inr": labour_inr,
            "freight_inr": freight_inr,
            "grand_total_inr": grand_total_inr,
        }

        summary_trace = [
            {
                "rule_id": "RB-PRC-011",
                "inputs": {
                    "total_labour_minutes": total_labour_minutes,
                    "rate_inr_per_hour": labour_rate,
                },
                "amount_inr": labour_inr,
            },
            {
                "rule_id": "RB-PRC-012",
                "inputs": freight_trace_inputs,
                "amount_inr": freight_inr,
            },
        ]

        return {
            "quote_id": quote_id,
            "room_id": room_id,
            "currency": "INR",
            "lines": priced_lines,
            "summary": summary,
            "summary_trace": summary_trace,
            "status": "priced",
        }
