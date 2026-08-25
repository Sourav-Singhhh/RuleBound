# Deterministic Pricing Specification

All calculations use integer INR. Percentages are basis points (`100 bps = 1%`). When division creates a fractional rupee, use **round half up**.

For each quote line:

1. `base_amount = unit_list_price × quantity`
2. `finish_uplift = round_half_up(base_amount × uplift_bps / 10000)`
3. Quantity discount is calculated on `base_amount` only:
   - quantity 1–4: 0 bps
   - quantity 5–9: 300 bps
   - quantity 10–19: 700 bps
   - quantity 20+: 1000 bps
4. `net_goods = base_amount + finish_uplift - quantity_discount`

Across the complete quote:

5. Sum catalog `labour_minutes × quantity`.
6. Labour rate: up to 240 minutes = ₹900/hour; 241–480 = ₹800/hour; above 480 = ₹750/hour. Apply one band to all minutes and round half up.
7. Freight on total net goods: up to ₹100,000 = ₹5,000; ₹100,001–₹250,000 = ₹9,000; above ₹250,000 = 4% of net goods, round half up.
8. `grand_total = net_goods + labour + freight`.

Every component must cite `CATALOG`, `RB-PRC-009`, `RB-PRC-010`, `RB-PRC-011` or `RB-PRC-012` with the exact inputs. An absent price or incompatible finish must block quote saving under `RB-PRC-013`.
