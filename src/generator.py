"""
Deterministic Generator Engine for RuleBound.
Generates initial ProposedLayout candidate from room specification, brief, catalog, and finishes.
No LLM, randomness, timestamps, network calls, or floating-point math.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


def is_point_in_polygon(x: int, y: int, polygon: Sequence[Sequence[Any]]) -> bool:
    """
    Returns True if integer point (x, y) is inside or on edge of polygon.
    Ray-casting algorithm with strict edge containment.
    """
    n = len(polygon)
    inside = False
    p1x, p1y = int(polygon[0][0]), int(polygon[0][1])

    for i in range(n + 1):
        p2x, p2y = int(polygon[i % n][0]), int(polygon[i % n][1])
        # Check if point lies exactly on horizontal/vertical edge
        if p1x == p2x and x == p1x and min(p1y, p2y) <= y <= max(p1y, p2y):
            return True
        if p1y == p2y and y == p1y and min(p1x, p2x) <= x <= max(p1x, p2x):
            return True

        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) // (p2y - p1y) + p1x
                    else:
                        xinters = p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y

    return inside


def segments_intersect_strict(
    x1: int, y1: int, x2: int, y2: int,
    x3: int, y3: int, x4: int, y4: int
) -> bool:
    """
    Returns True if segment (x1, y1)-(x2, y2) strictly intersects (x3, y3)-(x4, y4).
    """
    def ccw(ax: int, ay: int, bx: int, by: int, cx: int, cy: int) -> int:
        val = (by - ay) * (cx - bx) - (bx - ax) * (cy - by)
        if val == 0:
            return 0
        return 1 if val > 0 else 2

    o1 = ccw(x1, y1, x2, y2, x3, y3)
    o2 = ccw(x1, y1, x2, y2, x4, y4)
    o3 = ccw(x3, y3, x4, y4, x1, y1)
    o4 = ccw(x3, y3, x4, y4, x2, y2)

    return (o1 != o2 and o3 != o4 and o1 != 0 and o2 != 0 and o3 != 0 and o4 != 0)


def is_box_inside_polygon(
    bbox: Tuple[int, int, int, int],
    polygon: Sequence[Sequence[Any]]
) -> bool:
    """
    Returns True if the entire bounding box rectangle is contained within the polygon.
    """
    x1, y1, x2, y2 = bbox
    corners = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]

    for px, py in corners:
        if not is_point_in_polygon(px, py, polygon):
            return False

    rect_edges = [
        (x1, y1, x2, y1),
        (x2, y1, x2, y2),
        (x2, y2, x1, y2),
        (x1, y2, x1, y1),
    ]

    n = len(polygon)
    for i in range(n):
        px1, py1 = int(polygon[i][0]), int(polygon[i][1])
        px2, py2 = int(polygon[(i + 1) % n][0]), int(polygon[(i + 1) % n][1])
        for rx1, ry1, rx2, ry2 in rect_edges:
            if segments_intersect_strict(rx1, ry1, rx2, ry2, px1, py1, px2, py2):
                return False

    return True


class GeneratorEngine:
    """
    Deterministic proposal generator for RuleBound.
    Parses room specifications and plain-English briefs to construct an initial ProposedLayout.
    """

    def __init__(
        self,
        catalog: Sequence[Dict[str, Any]],
        finishes: Sequence[Dict[str, Any]],
        rules: Sequence[Dict[str, Any]],
        historical_jobs: Optional[Sequence[Dict[str, Any]]] = None
    ):
        self.catalog = list(catalog)
        self.finishes = list(finishes)
        self.rules = list(rules)
        self.historical_jobs = list(historical_jobs) if historical_jobs else []

        self.catalog_by_sku = {item["sku"]: item for item in self.catalog}
        self.finishes_by_id = {f["finish_id"]: f for f in self.finishes}

    def parse_capacity(self, room_spec: Dict[str, Any], brief_text: str) -> int:
        """
        Extracts seating capacity requirement from room_spec or brief.
        Priority: room_spec.capacity -> regex extraction from brief -> default 1.
        """
        if "capacity" in room_spec and isinstance(room_spec["capacity"], int):
            return room_spec["capacity"]

        m = re.search(r"(\d+)-person|team of (\d+)|capacity of (\d+)", brief_text, re.IGNORECASE)
        if m:
            for g in m.groups():
                if g:
                    return int(g)

        return 1

    def parse_furniture_counts(self, brief_text: str, default_capacity: int) -> Dict[str, int]:
        """
        Extracts explicit furniture counts from brief text.
        Distinguishes explicit quantitative requests from unquantified qualitative guidance.
        """
        counts = {"desk": default_capacity, "storage": 0, "collaboration": 0, "accessory": 0}
        text_lower = brief_text.lower()
        num_map = {
            "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
            "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12
        }
        num_pattern = r"(a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)"

        # 1. Explicit desk / workstation count regex
        m_desk = re.search(
            r"\b" + num_pattern + r"\b\s+(?:[a-z-]+\s+){0,3}(?:desk|desks|work position|work positions|desk position|desk positions|workstation|workstations)\b",
            text_lower
        )
        if m_desk:
            val_str = m_desk.group(1).lower()
            counts["desk"] = num_map.get(val_str, int(val_str) if val_str.isdigit() else default_capacity)

        # 2. Explicit storage unit count regex
        m_sto = re.search(
            r"\b" + num_pattern + r"\b\s+(?:[a-z-]+\s+){0,3}(?:storage unit|storage units|storage cabinet|storage cabinets)\b",
            text_lower
        )
        if m_sto:
            val_str = m_sto.group(1).lower()
            counts["storage"] = num_map.get(val_str, int(val_str) if val_str.isdigit() else 0)

        # 3. Explicit collaboration table count regex
        m_col = re.search(
            r"\b" + num_pattern + r"\b\s+(?:[a-z-]+\s+){0,3}(?:table|tables)\b",
            text_lower
        )
        if m_col:
            val_str = m_col.group(1).lower()
            counts["collaboration"] = num_map.get(val_str, int(val_str) if val_str.isdigit() else 0)

        return counts

    def select_finish(self, family: str, brief_text: str) -> str:
        """
        Selects finish for product family.
        1. Explicit compatible brief finish keyword match.
        2. Otherwise choose compatible finish with lowest uplift_bps, tie-breaking by finish_id ascending.
        Never forces an incompatible finish.
        """
        text_lower = brief_text.lower()

        # Keyword mapping
        kw_map = [
            ("oak", "F01"),
            ("graphite", "F02"),
            ("white", "F03"),
            ("walnut", "F05"),
            ("beech", "F04"),
            ("gray", "F10"),
            ("grey", "F10"),
        ]

        # 1. Match brief keyword if compatible
        for kw, fid in kw_map:
            if kw in text_lower:
                f_obj = self.finishes_by_id.get(fid)
                if f_obj and family in f_obj.get("compatible_families", []):
                    return fid

        # 2. Fallback: Lowest uplift_bps among compatible finishes
        compat_finishes = [
            f for f in self.finishes
            if family in f.get("compatible_families", [])
        ]
        if compat_finishes:
            compat_finishes.sort(key=lambda f: (f.get("uplift_bps", 0), f["finish_id"]))
            return compat_finishes[0]["finish_id"]

        # 3. Universal safety fallback
        return "F01"

    def select_sku(self, family: str, finish_id: str) -> Optional[str]:
        """
        Selects SKU in catalog for given family and finish.
        Ranked deterministically by:
        1. Footprint area ascending (width x depth)
        2. list_price_inr ascending
        3. sku ascending
        """
        candidates = []
        for item in self.catalog:
            if item.get("family") == family and finish_id in item.get("compatible_finish_ids", []):
                dims = item.get("dimensions_mm", {})
                area = dims.get("width", 0) * dims.get("depth", 0)
                price = item.get("list_price_inr", 0)
                candidates.append((area, price, item["sku"]))

        if not candidates:
            # If finish incompatible, fallback to any SKU in family
            for item in self.catalog:
                if item.get("family") == family:
                    dims = item.get("dimensions_mm", {})
                    area = dims.get("width", 0) * dims.get("depth", 0)
                    price = item.get("list_price_inr", 0)
                    candidates.append((area, price, item["sku"]))

        if not candidates:
            return None

        # Optional historical job preference tie-break boost
        hist_skus = set()
        for job in self.historical_jobs:
            for line in job.get("line_items", []):
                hist_skus.add(line.get("sku"))

        # Sort: area asc, price asc, sku asc
        candidates.sort(key=lambda pair: (pair[0], pair[1], pair[2]))
        return candidates[0][2]

    def _find_valid_placement(
        self,
        item_w: int,
        item_d: int,
        boundary: Sequence[Sequence[Any]],
        min_x: int, max_x: int,
        min_y: int, max_y: int,
        occupied_boxes: List[Tuple[int, int, int, int]]
    ) -> Optional[Tuple[int, int]]:
        """
        Finds candidate grid coordinate (x, y) on 100mm grid where item_w x item_d box fits
        strictly inside boundary polygon without overlapping occupied_boxes.
        """
        for y in range((min_y // 100) * 100 + 300, max_y, 100):
            for x in range((min_x // 100) * 100 + 300, max_x, 100):
                box = (x, y, x + item_w, y + item_d)
                if boundary and not is_box_inside_polygon(box, boundary):
                    continue

                # Check overlap with existing placements
                overlap = False
                for ox1, oy1, ox2, oy2 in occupied_boxes:
                    if x < ox2 and x + item_w > ox1 and y < oy2 and y + item_d > oy1:
                        overlap = True
                        break

                if not overlap:
                    return (x, y)

        return None

    def generate_proposal(
        self,
        room_spec: Dict[str, Any],
        brief_text: str
    ) -> Dict[str, Any]:
        """
        Generates initial candidate ProposedLayout.
        Does NOT enforce hard constraints or call arbitration.
        Returns clean ProposedLayout dictionary: {"room_id": str, "placements": [...]}.
        """
        room_id = room_spec["room_id"]
        capacity = self.parse_capacity(room_spec, brief_text)
        item_counts = self.parse_furniture_counts(brief_text, capacity)

        # Polygon boundary
        boundary = room_spec.get("boundary_mm", [])
        if boundary:
            min_x = min(pt[0] for pt in boundary)
            max_x = max(pt[0] for pt in boundary)
            min_y = min(pt[1] for pt in boundary)
            max_y = max(pt[1] for pt in boundary)
        else:
            min_x, min_y = 0, 0
            max_x, max_y = 6000, 6000

        placements: List[Dict[str, Any]] = []
        occupied_boxes: List[Tuple[int, int, int, int]] = []
        p_index = 1

        # Select SKUs & finishes
        desk_finish = self.select_finish("desk", brief_text)
        desk_sku = self.select_sku("desk", desk_finish)

        chair_finish = self.select_finish("chair", brief_text)
        chair_sku = self.select_sku("chair", chair_finish)

        storage_finish = self.select_finish("storage", brief_text)
        storage_sku = self.select_sku("storage", storage_finish)

        collab_finish = self.select_finish("collaboration", brief_text)
        collab_sku = self.select_sku("collaboration", collab_finish)

        # 1. Desks
        n_desks = item_counts.get("desk", capacity)
        if desk_sku and n_desks > 0:
            desk_item = self.catalog_by_sku[desk_sku]
            d_w = desk_item.get("dimensions_mm", {}).get("width", 1200)
            d_d = desk_item.get("dimensions_mm", {}).get("depth", 600)

            for i in range(n_desks):
                pos = self._find_valid_placement(d_w, d_d, boundary, min_x, max_x, min_y, max_y, occupied_boxes)
                if not pos:
                    pos = ((min_x // 100) * 100 + 500 + (i % 4) * 1300, (min_y // 100) * 100 + 1500 + (i // 4) * 1200)

                dx, dy = (pos[0] // 100) * 100, (pos[1] // 100) * 100
                pid_d = f"P{p_index:03d}"
                p_index += 1
                d_box = (dx, dy, dx + d_w, dy + d_d)
                placements.append({
                    "placement_id": pid_d,
                    "sku": desk_sku,
                    "finish_id": desk_finish,
                    "x_mm": dx,
                    "y_mm": dy,
                    "rotation_deg": 0,
                })
                occupied_boxes.append(d_box)

        # 2. Task Chairs (capacity seating requirement)
        if chair_sku and capacity > 0:
            chair_item = self.catalog_by_sku[chair_sku]
            c_w = chair_item.get("dimensions_mm", {}).get("width", 600)
            c_d = chair_item.get("dimensions_mm", {}).get("depth", 600)

            # Pair chairs with desks where available, otherwise find open grid position
            for i in range(capacity):
                if i < len(placements) and self.catalog_by_sku[placements[i]["sku"]]["family"] == "desk":
                    # Place behind corresponding desk
                    desk_p = placements[i]
                    dx, dy = desk_p["x_mm"], desk_p["y_mm"]
                    desk_item = self.catalog_by_sku[desk_p["sku"]]
                    d_w = desk_item.get("dimensions_mm", {}).get("width", 1200)
                    d_d = desk_item.get("dimensions_mm", {}).get("depth", 600)

                    cx = ((dx + (d_w - c_w) // 2) // 100) * 100
                    cy = dy + d_d + 100
                    c_box = (cx, cy, cx + c_w, cy + c_d)
                else:
                    pos = self._find_valid_placement(c_w, c_d, boundary, min_x, max_x, min_y, max_y, occupied_boxes)
                    if not pos:
                        pos = ((min_x // 100) * 100 + 500 + (i % 4) * 800, (min_y // 100) * 100 + 3000 + (i // 4) * 800)
                    cx, cy = (pos[0] // 100) * 100, (pos[1] // 100) * 100
                    c_box = (cx, cy, cx + c_w, cy + c_d)

                pid_c = f"P{p_index:03d}"
                p_index += 1
                placements.append({
                    "placement_id": pid_c,
                    "sku": chair_sku,
                    "finish_id": chair_finish,
                    "x_mm": cx,
                    "y_mm": cy,
                    "rotation_deg": 0,
                })
                occupied_boxes.append(c_box)

        # 3. Storage Placement
        n_storage = item_counts.get("storage", 0)
        if n_storage > 0 and storage_sku:
            sto_item = self.catalog_by_sku[storage_sku]
            s_w = sto_item.get("dimensions_mm", {}).get("width", 800)
            s_d = sto_item.get("dimensions_mm", {}).get("depth", 450)

            for i in range(n_storage):
                pos = self._find_valid_placement(s_w, s_d, boundary, min_x, max_x, min_y, max_y, occupied_boxes)
                if not pos:
                    pos = ((min_x // 100) * 100 + 300 + i * 900, (min_y // 100) * 100 + 300)

                sx, sy = (pos[0] // 100) * 100, (pos[1] // 100) * 100
                pid_s = f"P{p_index:03d}"
                p_index += 1
                s_box = (sx, sy, sx + s_w, sy + s_d)
                placements.append({
                    "placement_id": pid_s,
                    "sku": storage_sku,
                    "finish_id": storage_finish,
                    "x_mm": sx,
                    "y_mm": sy,
                    "rotation_deg": 0,
                })
                occupied_boxes.append(s_box)

        # 4. Collaboration Placement
        n_collab = item_counts.get("collaboration", 0)
        if n_collab > 0 and collab_sku:
            col_item = self.catalog_by_sku[collab_sku]
            c_w = col_item.get("dimensions_mm", {}).get("width", 1200)
            c_d = col_item.get("dimensions_mm", {}).get("depth", 1200)

            for i in range(n_collab):
                pos = self._find_valid_placement(c_w, c_d, boundary, min_x, max_x, min_y, max_y, occupied_boxes)
                if not pos:
                    pos = ((max_x // 100) * 100 - c_w - 500, (max_y // 100) * 100 - c_d - 500)

                cx, cy = (pos[0] // 100) * 100, (pos[1] // 100) * 100
                pid_col = f"P{p_index:03d}"
                p_index += 1
                col_box = (cx, cy, cx + c_w, cy + c_d)
                placements.append({
                    "placement_id": pid_col,
                    "sku": collab_sku,
                    "finish_id": collab_finish,
                    "x_mm": cx,
                    "y_mm": cy,
                    "rotation_deg": 0,
                })
                occupied_boxes.append(col_box)

        return {
            "room_id": room_id,
            "placements": placements,
        }
