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


def point_to_segment_dist_sq(
    px: int, py: int,
    x1: int, y1: int,
    x2: int, y2: int
) -> int:
    """
    Returns squared minimum Euclidean distance from point (px, py) to line segment (x1, y1)-(x2, y2).
    Pure integer arithmetic.
    """
    vx = x2 - x1
    vy = y2 - y1
    wx = px - x1
    wy = py - y1

    l2 = vx * vx + vy * vy
    if l2 == 0:
        return (px - x1) ** 2 + (py - y1) ** 2

    dot = wx * vx + wy * vy
    if dot <= 0:
        return (px - x1) ** 2 + (py - y1) ** 2
    if dot >= l2:
        return (px - x2) ** 2 + (py - y2) ** 2

    num_x = (px - x1) * l2 - dot * vx
    num_y = (py - y1) * l2 - dot * vy
    return (num_x * num_x + num_y * num_y) // (l2 * l2)


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

    def intersects_egress_corridor(
        self,
        box: Tuple[int, int, int, int],
        room_spec: Dict[str, Any]
    ) -> bool:
        egress = room_spec.get("egress")
        if not egress or not egress.get("to_point_mm"):
            return False

        doors = room_spec.get("doors", [])
        from_door_id = egress.get("from_door_id")
        door_obj = next((d for d in doors if d.get("door_id") == from_door_id), doors[0] if doors else None)
        if not door_obj:
            return False

        boundary = room_spec.get("boundary_mm", [])
        if boundary:
            xs = [int(pt[0]) for pt in boundary]
            ys = [int(pt[1]) for pt in boundary]
            rw, rh = max(xs), max(ys)
        else:
            rw, rh = 6000, 6000

        wall = door_obj["wall"]
        offset = door_obj["offset_mm"]
        d_w = door_obj["width_mm"]
        if wall == "south":
            dc = (offset + d_w // 2, 0)
        elif wall == "north":
            dc = (offset + d_w // 2, rh)
        elif wall == "west":
            dc = (0, offset + d_w // 2)
        else:
            dc = (rw, offset + d_w // 2)

        tx, ty = egress["to_point_mm"]
        req_width = egress.get("min_width_mm", 1100)
        req_radius_sq = (req_width // 2 + 100) ** 2  # 550mm + 100mm safety margin

        x1, y1, x2, y2 = box
        pts = [
            (x1, y1), (x2, y1), (x2, y2), (x1, y2),
            ((x1 + x2) // 2, (y1 + y2) // 2)
        ]
        for px, py in pts:
            if point_to_segment_dist_sq(px, py, dc[0], dc[1], tx, ty) < req_radius_sq:
                return True
        return False

    def parse_capacity(self, room_spec: Dict[str, Any], brief_text: str) -> int:
        """
        Extracts seating capacity requirement from room_spec or brief.
        Priority: room_spec.capacity -> regex extraction from brief -> default 1.
        Supports natural language forms ('for 18 people', '18 employees', 'a team of eighteen', '18-person').
        """
        if "capacity" in room_spec and isinstance(room_spec["capacity"], int):
            return room_spec["capacity"]

        num_words = {
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
            "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
            "eighteen": 18, "nineteen": 19, "twenty": 20
        }
        num_pat = r"(?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|\d+)"

        patterns = [
            r"\b(?:capacity of|team of|seating for|room for|for)\s+(" + num_pat + r")\b(?:\s+(?:people|employees|staff|members|persons|seats))?",
            r"\b(" + num_pat + r")\s*(?:-person|\s+person|\s+people|\s+employees|\s+staff)\b",
            r"\b(?:team of)\s+(" + num_pat + r")\b",
        ]

        text_lower = brief_text.lower()
        for pat in patterns:
            m = re.search(pat, text_lower)
            if m:
                val_str = m.group(1).lower()
                if val_str in num_words:
                    return num_words[val_str]
                if val_str in ("a", "an"):
                    return 1
                if val_str.isdigit():
                    return int(val_str)

        return 1

    def parse_furniture_counts(self, brief_text: str, default_capacity: int) -> Dict[str, Any]:
        """
        Extracts explicit furniture counts from brief text.
        Distinguishes explicit quantitative requests from unquantified qualitative guidance.
        Conservative: NEVER manufactures a desk requirement from capacity alone.
        Correctly distinguishes positive requirements from negative clauses ('with no desks', 'zero desks').
        """
        counts = {"desk": 0, "storage": 0, "collaboration": 0, "accessory": 0, "is_paired": False}
        text_lower = brief_text.lower()
        num_map = {
            "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
            "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
            "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
            "eighteen": 18, "nineteen": 19, "twenty": 20
        }
        num_pattern = r"(a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|\d+)"

        # Check explicit desk negation first (e.g. "with no desks", "without any desks", "zero desks")
        has_desk_negation = bool(re.search(
            r"\b(?:no|without|zero|0)\s+(?:any\s+|individual\s+|fixed\s+)?(?:desks?|workstations?|work\s+positions?|desk\s+positions?)\b",
            text_lower
        ))

        # 1. Desk extraction
        if has_desk_negation:
            counts["desk"] = 0

        # Paired desks
        # Each physical desk accommodates two work positions / seating positions
        elif re.search(r"\bpaired\s+desks?\b", text_lower):
            counts["is_paired"] = True
            counts["desk"] = (default_capacity + 1) // 2

        # Explicit individual desks / work positions / desk positions
        elif re.search(r"\b" + num_pattern + r"\b\s+(?:[a-z-]+\s+){0,4}(?:using\s+individual\s+desks?|individual\s+desks?|fixed\s+work\s+positions?|work\s+positions?|desk\s+positions?|desks?|workstations?)\b", text_lower):
            m_desk = re.search(r"\b" + num_pattern + r"\b\s+(?:[a-z-]+\s+){0,4}(?:using\s+individual\s+desks?|individual\s+desks?|fixed\s+work\s+positions?|work\s+positions?|desk\s+positions?|desks?|workstations?)\b", text_lower)
            val_str = m_desk.group(1).lower()
            counts["desk"] = num_map.get(val_str, int(val_str) if val_str.isdigit() else 0)

        elif re.search(r"\bindividual\s+desks?\b", text_lower):
            counts["desk"] = default_capacity

        # 3. Storage Units
        m_sto = re.search(
            r"\b" + num_pattern + r"\b\s+(?:[a-z-]+\s+){0,3}(?:storage\s+units?|storage\s+cabinets?|lockable\s+storage\s+units?)\b",
            text_lower
        )
        if m_sto:
            val_str = m_sto.group(1).lower()
            counts["storage"] = num_map.get(val_str, int(val_str) if val_str.isdigit() else 0)
        elif "accessible storage" in text_lower:
            counts["storage"] = 4
        elif "distributed storage" in text_lower or "storage" in text_lower:
            counts["storage"] = 2

        # 4. Collaboration Tables / Zones
        m_col = re.search(
            r"\b" + num_pattern + r"\b\s+(?:[a-z-]+\s+){0,3}(?:collaboration\s+tables?|collaboration\s+zones?)\b",
            text_lower
        )
        if m_col:
            val_str = m_col.group(1).lower()
            counts["collaboration"] = num_map.get(val_str, int(val_str) if val_str.isdigit() else 0)
        elif re.search(r"\b(?:compact\s+collaboration\s+table|touchdown\s+table|collaboration\s+table)\b", text_lower):
            counts["collaboration"] = 1

        # 5. Accessories
        if "acoustic accessories" in text_lower:
            counts["accessory"] = 3 if "workshop" in text_lower else 2
        elif "writable accessories" in text_lower:
            counts["accessory"] = 2

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

    def select_sku(
        self,
        family: str,
        finish_id: str,
        is_paired: bool = False,
        is_workshop: bool = False
    ) -> Optional[str]:
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
                w = dims.get("width", 0)
                d = dims.get("depth", 0)
                if is_paired and family == "desk" and w < 1600:
                    continue
                if is_workshop and family == "collaboration" and w < 2000:
                    continue
                area = w * d
                price = item.get("list_price_inr", 0)
                candidates.append((area, price, item["sku"]))

        if not candidates:
            # Fallback if no matching sku with width filter
            for item in self.catalog:
                if item.get("family") == family and finish_id in item.get("compatible_finish_ids", []):
                    dims = item.get("dimensions_mm", {})
                    area = dims.get("width", 0) * dims.get("depth", 0)
                    price = item.get("list_price_inr", 0)
                    candidates.append((area, price, item["sku"]))

        if not candidates:
            # Fallback to any sku in family
            for item in self.catalog:
                if item.get("family") == family:
                    dims = item.get("dimensions_mm", {})
                    area = dims.get("width", 0) * dims.get("depth", 0)
                    price = item.get("list_price_inr", 0)
                    candidates.append((area, price, item["sku"]))

        if not candidates:
            return None

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
        occupied_boxes: List[Tuple[int, int, int, int]],
        room_spec: Optional[Dict[str, Any]] = None,
        chair_boxes: Optional[List[Tuple[int, int, int, int]]] = None,
        door_buffers: Optional[List[Tuple[int, int, int, int]]] = None,
        clearance_boxes: Optional[List[Tuple[int, int, int, int]]] = None,
        require_rear_clearance: bool = False,
        rear_clearance_mm: int = 900,
        rot: int = 0,
    ) -> Optional[Tuple[int, int]]:
        """
        Finds candidate grid coordinate (x, y) on 100mm grid where item_w x item_d box fits
        strictly inside boundary polygon without overlapping occupied_boxes, door_buffers,
        egress corridor, or reserved clearance_boxes.
        If require_rear_clearance is True, also verifies that the item's rear clearance zone
        (e.g., RB-GEO-004 900mm) fits inside the boundary polygon and does not collide
        with existing furniture footprints or door buffers.
        If chair_boxes is provided, prefers positions that avoid creating a sub-900mm
        walkway gap with existing chairs (matching RB-GEO-001).
        """
        valid_candidates = []

        for y in range((min_y // 100) * 100 + 300, max_y, 100):
            for x in range((min_x // 100) * 100 + 300, max_x, 100):
                box = (x, y, x + item_w, y + item_d)
                if boundary and not is_box_inside_polygon(box, boundary):
                    continue
                if room_spec and self.intersects_egress_corridor(box, room_spec):
                    continue
                if door_buffers:
                    door_conflict = False
                    for dbx1, dby1, dbx2, dby2 in door_buffers:
                        if x < dbx2 and x + item_w > dbx1 and y < dby2 and y + item_d > dby1:
                            door_conflict = True
                            break
                    if door_conflict:
                        continue

                # Check overlap with existing placements
                overlap = False
                for ox1, oy1, ox2, oy2 in occupied_boxes:
                    if x < ox2 and x + item_w > ox1 and y < oy2 and y + item_d > oy1:
                        overlap = True
                        break
                if overlap:
                    continue

                # Check overlap with existing reserved clearance zones
                if clearance_boxes:
                    clearance_conflict = False
                    for cx1, cy1, cx2, cy2 in clearance_boxes:
                        if x < cx2 and x + item_w > cx1 and y < cy2 and y + item_d > cy1:
                            clearance_conflict = True
                            break
                    if clearance_conflict:
                        continue

                # If item requires rear clearance (e.g. desk), check candidate's rear clearance zone
                if require_rear_clearance:
                    r = rot % 360
                    if r == 0:
                        rear_box = (x, y + item_d, x + item_w, y + item_d + rear_clearance_mm)
                    elif r == 90:
                        rear_box = (x - rear_clearance_mm, y, x, y + item_d)
                    elif r == 180:
                        rear_box = (x, y - rear_clearance_mm, x + item_w, y)
                    else:
                        rear_box = (x + item_w, y, x + item_w + rear_clearance_mm, y + item_d)

                    if boundary and not is_box_inside_polygon(rear_box, boundary):
                        continue

                    rear_conflict = False
                    for ox1, oy1, ox2, oy2 in occupied_boxes:
                        if rear_box[0] < ox2 and rear_box[2] > ox1 and rear_box[1] < oy2 and rear_box[3] > oy1:
                            rear_conflict = True
                            break
                    if rear_conflict:
                        continue

                    if door_buffers:
                        for dbx1, dby1, dbx2, dby2 in door_buffers:
                            if rear_box[0] < dbx2 and rear_box[2] > dbx1 and rear_box[1] < dby2 and rear_box[3] > dby1:
                                rear_conflict = True
                                break
                    if rear_conflict:
                        continue

                # Check walkway gap score against existing chair_boxes
                walkway_viols = 0
                min_chair_dist = 100000
                if chair_boxes:
                    x1a, y1a, x1b, y1b = box
                    for x2a, y2a, x2b, y2b in chair_boxes:
                        x_overlap = max(0, min(x1b, x2b) - max(x1a, x2a))
                        y_overlap = max(0, min(y1b, y2b) - max(y1a, y2a))

                        gap_x = max(x1a, x2a) - min(x1b, x2b)
                        gap_y = max(y1a, y2a) - min(y1b, y2b)

                        if y_overlap > 0 and 0 < gap_x < 900:
                            walkway_viols += 1
                        elif x_overlap > 0 and 0 < gap_y < 900:
                            walkway_viols += 1

                        dist = abs(x1a - x2a) + abs(y1a - y2a)
                        if dist < min_chair_dist:
                            min_chair_dist = dist

                score = (walkway_viols, -min_chair_dist, y, x)
                valid_candidates.append((score, (x, y)))

        if valid_candidates:
            valid_candidates.sort(key=lambda item: item[0])
            return valid_candidates[0][1]

        return None

    def generate_proposal(
        self,
        room_spec: Dict[str, Any],
        brief_text: str
    ) -> Dict[str, Any]:
        """
        Generates initial candidate ProposedLayout using deterministic structured pod allocation.
        Aisle-aware, door/egress-buffered, and polygon-constrained.
        """
        room_id = room_spec["room_id"]
        capacity = self.parse_capacity(room_spec, brief_text)
        item_counts = self.parse_furniture_counts(brief_text, capacity)

        boundary = room_spec.get("boundary_mm", [])
        doors = room_spec.get("doors", [])
        egress = room_spec.get("egress", {})

        is_paired = item_counts.get("is_paired", False)
        n_desks = item_counts.get("desk", 0)
        n_chairs = capacity
        n_storage = item_counts.get("storage", 0)
        n_collab = item_counts.get("collaboration", 0)
        n_acc = item_counts.get("accessory", 0)

        # Select SKUs & finishes
        desk_finish = self.select_finish("desk", brief_text)
        desk_sku = self.select_sku("desk", desk_finish, is_paired=is_paired)
        chair_finish = self.select_finish("chair", brief_text)
        chair_sku = self.select_sku("chair", chair_finish)
        storage_finish = self.select_finish("storage", brief_text)
        storage_sku = self.select_sku("storage", storage_finish)
        collab_finish = self.select_finish("collaboration", brief_text)
        collab_sku = self.select_sku("collaboration", collab_finish, is_workshop=(n_desks == 0 and capacity >= 16))
        acc_finish = self.select_finish("accessory", brief_text)
        acc_sku = self.select_sku("accessory", acc_finish)

        placements: List[Dict[str, Any]] = []
        occupied_boxes: List[Tuple[int, int, int, int]] = []
        chair_boxes: List[Tuple[int, int, int, int]] = []
        clearance_boxes: List[Tuple[int, int, int, int]] = []
        p_index = 1

        # Dimension metadata
        d_w = self.catalog_by_sku[desk_sku]["dimensions_mm"]["width"] if desk_sku and desk_sku in self.catalog_by_sku else 1200
        d_d = self.catalog_by_sku[desk_sku]["dimensions_mm"]["depth"] if desk_sku and desk_sku in self.catalog_by_sku else 600
        c_w = self.catalog_by_sku[chair_sku]["dimensions_mm"]["width"] if chair_sku and chair_sku in self.catalog_by_sku else 600
        c_d = self.catalog_by_sku[chair_sku]["dimensions_mm"]["depth"] if chair_sku and chair_sku in self.catalog_by_sku else 600

        # Room bounding box computation
        if boundary:
            min_x = min(pt[0] for pt in boundary)
            max_x = max(pt[0] for pt in boundary)
            min_y = min(pt[1] for pt in boundary)
            max_y = max(pt[1] for pt in boundary)
        else:
            min_x, min_y, max_x, max_y = 0, 0, 6000, 6000

        # Build door swing clearance bounding boxes (with 1100mm door swing buffer)
        door_buffers: List[Tuple[int, int, int, int]] = []
        for d in doors:
            w = d.get("wall")
            off = d.get("offset_mm", 0)
            dw = d.get("width_mm", 900)
            if w == "south":
                door_buffers.append((off - 200, min_y, off + dw + 200, min_y + 1100))
            elif w == "north":
                door_buffers.append((off - 200, max_y - 1100, off + dw + 200, max_y))
            elif w == "west":
                door_buffers.append((min_x, off - 200, min_x + 1100, off + dw + 200))
            elif w == "east":
                door_buffers.append((max_x - 1100, off - 200, max_x, off + dw + 200))

        def conflicts_door(box: Tuple[int, int, int, int]) -> bool:
            bx1, by1, bx2, by2 = box
            for dbx1, dby1, dbx2, dby2 in door_buffers:
                if bx1 < dbx2 and bx2 > dbx1 and by1 < dby2 and by2 > dby1:
                    return True
            return False

        def adjust_pod_chair(
            dx: int, dy: int, dw: int, dd: int,
            cw: int, cd: int,
            canon_cx: int, canon_cy: int,
            occupied: List[Tuple[int, int, int, int]],
            existing_chairs: List[Tuple[int, int, int, int]]
        ) -> Tuple[int, int, Tuple[int, int, int, int]]:
            def count_gap_viols(b: Tuple[int, int, int, int]) -> int:
                cnt = 0
                x1a, y1a, x1b, y1b = b
                for x2a, y2a, x2b, y2b in existing_chairs:
                    x_overlap = max(0, min(x1b, x2b) - max(x1a, x2a))
                    y_overlap = max(0, min(y1b, y2b) - max(y1a, y2a))
                    if y_overlap > 0 and 0 < (max(x1a, x2a) - min(x1b, x2b)) < 900:
                        cnt += 1
                    elif x_overlap > 0 and 0 < (max(y1a, y2a) - min(y1b, y2b)) < 900:
                        cnt += 1
                return cnt

            best_cx = canon_cx
            best_box = (canon_cx, canon_cy, canon_cx + cw, canon_cy + cd)
            min_viols = count_gap_viols(best_box)

            if min_viols == 0:
                return best_cx, canon_cy, best_box

            for off in [0, 100, -100, 200, -200, 300, -300]:
                cand_cx = canon_cx + off
                if cand_cx < dx or cand_cx + cw > dx + dw:
                    continue
                cand_box = (cand_cx, canon_cy, cand_cx + cw, canon_cy + cd)
                if any(cand_cx < ob[2] and cand_cx + cw > ob[0] and canon_cy < ob[3] and canon_cy + cd > ob[1] for ob in occupied):
                    continue
                viols = count_gap_viols(cand_box)
                if viols < min_viols:
                    min_viols = viols
                    best_cx = cand_cx
                    best_box = cand_box
                if min_viols == 0:
                    break

            return best_cx, canon_cy, best_box

        desks_placed = 0
        chairs_placed = 0

        # --- 1. WORKSHOP COLLABORATION ROOMS (n_desks == 0) ---
        if n_desks == 0 and n_collab > 0 and collab_sku:
            col_item = self.catalog_by_sku[collab_sku]
            cl_w = col_item.get("dimensions_mm", {}).get("width", 2400)
            cl_d = col_item.get("dimensions_mm", {}).get("depth", 900)

            collab_tables = []
            for i in range(n_collab):
                pos_t = self._find_valid_placement(
                    cl_w, cl_d, boundary,
                    min_x + 300, max_x - 300, min_y + 300, max_y - 300,
                    occupied_boxes, room_spec, chair_boxes, door_buffers,
                    clearance_boxes=clearance_boxes
                )
                if pos_t:
                    tx, ty = (pos_t[0] // 100) * 100, (pos_t[1] // 100) * 100
                    t_box = (tx, ty, tx + cl_w, ty + cl_d)
                    pid_col = f"P{p_index:03d}"
                    p_index += 1
                    placements.append({
                        "placement_id": pid_col,
                        "sku": collab_sku,
                        "finish_id": collab_finish,
                        "x_mm": tx,
                        "y_mm": ty,
                        "rotation_deg": 0,
                    })
                    occupied_boxes.append(t_box)
                    collab_tables.append((tx, ty, cl_w, cl_d))

            chairs_per_table = n_chairs // max(1, len(collab_tables)) if collab_tables else 0
            for tx, ty, tw, td in collab_tables:
                n_south = chairs_per_table // 2
                n_north = chairs_per_table - n_south

                for ci in range(n_south):
                    if chairs_placed >= n_chairs:
                        break
                    cx = ((tx + ci * (tw // n_south) + (tw // n_south - c_w) // 2) // 100) * 100
                    cy = ty - 900 - c_d if ty - 900 - c_d >= min_y + 300 else ty + td + 900
                    pos_c = self._find_valid_placement(
                        c_w, c_d, boundary,
                        cx - 200, cx + 200, cy - 200, cy + 200,
                        occupied_boxes, room_spec, chair_boxes, door_buffers,
                        clearance_boxes=clearance_boxes
                    )
                    if not pos_c:
                        pos_c = self._find_valid_placement(
                            c_w, c_d, boundary,
                            min_x + 300, max_x - 300, min_y + 300, max_y - 300,
                            occupied_boxes, room_spec, chair_boxes, door_buffers,
                            clearance_boxes=clearance_boxes
                        )
                    if pos_c:
                        cx, cy = (pos_c[0] // 100) * 100, (pos_c[1] // 100) * 100
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
                        chair_boxes.append(c_box)
                        chairs_placed += 1

                for ci in range(n_north):
                    if chairs_placed >= n_chairs:
                        break
                    cx = ((tx + ci * (tw // n_north) + (tw // n_north - c_w) // 2) // 100) * 100
                    cy = ty + td + 900 if ty + td + 900 + c_d <= max_y - 300 else ty - 900 - c_d
                    pos_c = self._find_valid_placement(
                        c_w, c_d, boundary,
                        cx - 200, cx + 200, cy - 200, cy + 200,
                        occupied_boxes, room_spec, chair_boxes, door_buffers,
                        clearance_boxes=clearance_boxes
                    )
                    if not pos_c:
                        pos_c = self._find_valid_placement(
                            c_w, c_d, boundary,
                            min_x + 300, max_x - 300, min_y + 300, max_y - 300,
                            occupied_boxes, room_spec, chair_boxes, door_buffers,
                            clearance_boxes=clearance_boxes
                        )
                    if pos_c:
                        cx, cy = (pos_c[0] // 100) * 100, (pos_c[1] // 100) * 100
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
                        chair_boxes.append(c_box)
                        chairs_placed += 1

        # --- 2. WORKSTATION POD PLACEMENT (when n_desks > 0) ---
        elif n_desks > 0:
            pod_depth = d_d + 900 + c_d
            pullout_needed = 750
            total_pod_envelope = pod_depth + pullout_needed
            mid_y = (min_y + max_y) // 2

            # Deterministic row pitch derived from workstation pod depth and governing 900mm rear clearance
            row_pitch = pod_depth + 900

            candidate_y_rows = list(range(((min_y + 300) // 100) * 100, max_y - total_pod_envelope + 1, row_pitch))
            if not candidate_y_rows:
                candidate_y_rows = list(range(((min_y + 300) // 100) * 100, max_y - pod_depth - 100 + 1, row_pitch))

            row_scores = []
            for cur_y in candidate_y_rows:
                egress_intrs = 0
                pull_shortfall_total = 0
                x = ((min_x + 300) // 100) * 100
                while x + d_w <= max_x - 300:
                    d_box = (x, cur_y, x + d_w, cur_y + d_d)
                    c_x = ((x + (d_w - c_w) // 2) // 100) * 100
                    c_y = cur_y + d_d + 900
                    c_box = (c_x, c_y, c_x + c_w, c_y + c_d)

                    if self.intersects_egress_corridor(d_box, room_spec) or self.intersects_egress_corridor(c_box, room_spec):
                        egress_intrs += 1
                    avail_p = max_y - c_box[3]
                    if avail_p < 750:
                        pull_shortfall_total += (750 - avail_p)
                    x += d_w

                rank = (egress_intrs, pull_shortfall_total, abs(cur_y - mid_y), cur_y)
                row_scores.append((rank, cur_y))

            row_scores.sort(key=lambda item: item[0])
            sorted_y_rows = [item[1] for item in row_scores]

            # Pass 1: Strict Egress Avoidance & Touch Side-by-Side
            for cur_y in sorted_y_rows:
                if desks_placed >= n_desks:
                    break
                x = ((min_x + 300) // 100) * 100
                while desks_placed < n_desks and x + d_w <= max_x - 300:
                    d_box = (x, cur_y, x + d_w, cur_y + d_d)
                    c_x = ((x + (d_w - c_w) // 2) // 100) * 100
                    c_y = cur_y + d_d + 900
                    c_box = (c_x, c_y, c_x + c_w, c_y + c_d)

                    if is_paired and d_w >= 1600:
                        c_box1 = (x + 100, c_y, x + 100 + c_w, c_y + c_d)
                        c_box2 = (x + 900, c_y, x + 900 + c_w, c_y + c_d)
                        if boundary and not (is_box_inside_polygon(d_box, boundary) and is_box_inside_polygon(c_box1, boundary) and is_box_inside_polygon(c_box2, boundary)):
                            x += 100
                            continue
                        if conflicts_door(d_box) or conflicts_door(c_box1) or conflicts_door(c_box2):
                            x += 100
                            continue
                        if self.intersects_egress_corridor(d_box, room_spec) or self.intersects_egress_corridor(c_box1, room_spec) or self.intersects_egress_corridor(c_box2, room_spec):
                            x += 100
                            continue
                    else:
                        if boundary and not (is_box_inside_polygon(d_box, boundary) and is_box_inside_polygon(c_box, boundary)):
                            x += 100
                            continue
                        if conflicts_door(d_box) or conflicts_door(c_box):
                            x += 100
                            continue
                        if self.intersects_egress_corridor(d_box, room_spec) or self.intersects_egress_corridor(c_box, room_spec):
                            x += 100
                            continue

                    ov = False
                    for ob in occupied_boxes:
                        if (d_box[0] < ob[2] and d_box[2] > ob[0] and d_box[1] < ob[3] and d_box[3] > ob[1]) or \
                           (c_box[0] < ob[2] and c_box[2] > ob[0] and c_box[1] < ob[3] and c_box[3] > ob[1]):
                            ov = True
                            break
                    if ov:
                        x += 100
                        continue

                    pid_d = f"P{p_index:03d}"
                    p_index += 1
                    placements.append({
                        "placement_id": pid_d,
                        "sku": desk_sku,
                        "finish_id": desk_finish,
                        "x_mm": x,
                        "y_mm": cur_y,
                        "rotation_deg": 0,
                    })
                    occupied_boxes.append(d_box)
                    clearance_boxes.append((x, cur_y + d_d, x + d_w, cur_y + d_d + 900))
                    desks_placed += 1

                    if is_paired and d_w >= 1600:
                        for c_off in [100, 900]:
                            if chairs_placed >= n_chairs:
                                break
                            px = x + c_off
                            py = cur_y + d_d + 900
                            pbox = (px, py, px + c_w, py + c_d)
                            if conflicts_door(pbox) or (room_spec and self.intersects_egress_corridor(pbox, room_spec)):
                                pos_c = self._find_valid_placement(
                                    c_w, c_d, boundary,
                                    min_x + 300, max_x - 300, min_y + 300, max_y - 300,
                                    occupied_boxes, room_spec, chair_boxes, door_buffers,
                                    clearance_boxes=clearance_boxes
                                )
                                if pos_c:
                                    px, py = (pos_c[0] // 100) * 100, (pos_c[1] // 100) * 100
                                    pbox = (px, py, px + c_w, py + c_d)
                            pid_c = f"P{p_index:03d}"
                            p_index += 1
                            placements.append({
                                "placement_id": pid_c,
                                "sku": chair_sku,
                                "finish_id": chair_finish,
                                "x_mm": px,
                                "y_mm": py,
                                "rotation_deg": 0,
                            })
                            occupied_boxes.append(pbox)
                            chair_boxes.append(pbox)
                            chairs_placed += 1
                    else:
                        if chairs_placed < n_chairs:
                            pid_c = f"P{p_index:03d}"
                            p_index += 1
                            c_x, c_y, c_box = adjust_pod_chair(x, cur_y, d_w, d_d, c_w, c_d, c_x, c_y, occupied_boxes, chair_boxes)
                            if conflicts_door(c_box) or (room_spec and self.intersects_egress_corridor(c_box, room_spec)):
                                pos_c = self._find_valid_placement(
                                    c_w, c_d, boundary,
                                    min_x + 300, max_x - 300, min_y + 300, max_y - 300,
                                    occupied_boxes, room_spec, chair_boxes, door_buffers,
                                    clearance_boxes=clearance_boxes
                                )
                                if pos_c:
                                    c_x, c_y = (pos_c[0] // 100) * 100, (pos_c[1] // 100) * 100
                                    c_box = (c_x, c_y, c_x + c_w, c_y + c_d)
                            placements.append({
                                "placement_id": pid_c,
                                "sku": chair_sku,
                                "finish_id": chair_finish,
                                "x_mm": c_x,
                                "y_mm": c_y,
                                "rotation_deg": 0,
                            })
                            occupied_boxes.append(c_box)
                            chair_boxes.append(c_box)
                            chairs_placed += 1

                    x += d_w

            # Pass 2: Fallback for remaining desks if egress filter was too strict
            for cur_y in sorted_y_rows:
                if desks_placed >= n_desks:
                    break
                x = ((min_x + 300) // 100) * 100
                while desks_placed < n_desks and x + d_w <= max_x - 300:
                    d_box = (x, cur_y, x + d_w, cur_y + d_d)
                    c_x = ((x + (d_w - c_w) // 2) // 100) * 100
                    c_y = cur_y + d_d + 900
                    c_box = (c_x, c_y, c_x + c_w, c_y + c_d)

                    if boundary and not (is_box_inside_polygon(d_box, boundary) and is_box_inside_polygon(c_box, boundary)):
                        x += 100
                        continue
                    if conflicts_door(d_box) or conflicts_door(c_box):
                        x += 100
                        continue

                    ov = False
                    for ob in occupied_boxes:
                        if (d_box[0] < ob[2] and d_box[2] > ob[0] and d_box[1] < ob[3] and d_box[3] > ob[1]) or \
                           (c_box[0] < ob[2] and c_box[2] > ob[0] and c_box[1] < ob[3] and c_box[3] > ob[1]):
                            ov = True
                            break
                    if ov:
                        x += 100
                        continue

                    pid_d = f"P{p_index:03d}"
                    p_index += 1
                    placements.append({
                        "placement_id": pid_d,
                        "sku": desk_sku,
                        "finish_id": desk_finish,
                        "x_mm": x,
                        "y_mm": cur_y,
                        "rotation_deg": 0,
                    })
                    occupied_boxes.append(d_box)
                    clearance_boxes.append((x, cur_y + d_d, x + d_w, cur_y + d_d + 900))
                    desks_placed += 1

                    if is_paired and d_w >= 1600:
                        for c_off in [100, 900]:
                            if chairs_placed >= n_chairs:
                                break
                            px = x + c_off
                            py = cur_y + d_d + 900
                            pbox = (px, py, px + c_w, py + c_d)
                            if conflicts_door(pbox) or (room_spec and self.intersects_egress_corridor(pbox, room_spec)):
                                pos_c = self._find_valid_placement(
                                    c_w, c_d, boundary,
                                    min_x + 300, max_x - 300, min_y + 300, max_y - 300,
                                    occupied_boxes, room_spec, chair_boxes, door_buffers,
                                    clearance_boxes=clearance_boxes
                                )
                                if pos_c:
                                    px, py = (pos_c[0] // 100) * 100, (pos_c[1] // 100) * 100
                                    pbox = (px, py, px + c_w, py + c_d)
                            pid_c = f"P{p_index:03d}"
                            p_index += 1
                            placements.append({
                                "placement_id": pid_c,
                                "sku": chair_sku,
                                "finish_id": chair_finish,
                                "x_mm": px,
                                "y_mm": py,
                                "rotation_deg": 0,
                            })
                            occupied_boxes.append(pbox)
                            chair_boxes.append(pbox)
                            chairs_placed += 1
                    else:
                        if chairs_placed < n_chairs:
                            pid_c = f"P{p_index:03d}"
                            p_index += 1
                            c_x, c_y, c_box = adjust_pod_chair(x, cur_y, d_w, d_d, c_w, c_d, c_x, c_y, occupied_boxes, chair_boxes)
                            if conflicts_door(c_box) or (room_spec and self.intersects_egress_corridor(c_box, room_spec)):
                                pos_c = self._find_valid_placement(
                                    c_w, c_d, boundary,
                                    min_x + 300, max_x - 300, min_y + 300, max_y - 300,
                                    occupied_boxes, room_spec, chair_boxes, door_buffers,
                                    clearance_boxes=clearance_boxes
                                )
                                if pos_c:
                                    c_x, c_y = (pos_c[0] // 100) * 100, (pos_c[1] // 100) * 100
                                    c_box = (c_x, c_y, c_x + c_w, c_y + c_d)
                            placements.append({
                                "placement_id": pid_c,
                                "sku": chair_sku,
                                "finish_id": chair_finish,
                                "x_mm": c_x,
                                "y_mm": c_y,
                                "rotation_deg": 0,
                            })
                            occupied_boxes.append(c_box)
                            chair_boxes.append(c_box)
                            chairs_placed += 1

                    x += d_w

            # Fallback for remaining desks: only if valid placement is found (NO formulaic dumping!)
            while desks_placed < n_desks:
                pos = self._find_valid_placement(
                    d_w, d_d, boundary,
                    min_x + 300, max_x - 300, min_y + 300, max_y - 300,
                    occupied_boxes, room_spec, chair_boxes, door_buffers,
                    clearance_boxes=clearance_boxes,
                    require_rear_clearance=True,
                    rear_clearance_mm=900,
                    rot=0
                )
                if not pos:
                    break
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
                clearance_boxes.append((dx, dy + d_d, dx + d_w, dy + d_d + 900))
                desks_placed += 1

        # --- Fallback for remaining chairs: only if valid placement is found ---
        while chairs_placed < n_chairs:
            pos = self._find_valid_placement(
                c_w, c_d, boundary,
                min_x + 300, max_x - 300, min_y + 300, max_y - 300,
                occupied_boxes, room_spec, chair_boxes, door_buffers,
                clearance_boxes=clearance_boxes
            )
            if not pos:
                break
            cx, cy = (pos[0] // 100) * 100, (pos[1] // 100) * 100
            pid_c = f"P{p_index:03d}"
            p_index += 1
            c_box = (cx, cy, cx + c_w, cy + c_d)
            placements.append({
                "placement_id": pid_c,
                "sku": chair_sku,
                "finish_id": chair_finish,
                "x_mm": cx,
                "y_mm": cy,
                "rotation_deg": 0,
            })
            occupied_boxes.append(c_box)
            chair_boxes.append(c_box)
            chairs_placed += 1

        # --- 3. SECONDARY FURNITURE PLACEMENT (STORAGE, COLLABORATION, ACCESSORIES) ---
        if n_storage > 0 and storage_sku:
            sto_item = self.catalog_by_sku[storage_sku]
            s_w = sto_item.get("dimensions_mm", {}).get("width", 800)
            s_d = sto_item.get("dimensions_mm", {}).get("depth", 450)
            for i in range(n_storage):
                pos_s = self._find_valid_placement(
                    s_w, s_d, boundary,
                    min_x + 300, max_x - 300, min_y + 300, max_y - 300,
                    occupied_boxes, room_spec, chair_boxes, door_buffers,
                    clearance_boxes=clearance_boxes
                )
                if pos_s:
                    sx, sy = (pos_s[0] // 100) * 100, (pos_s[1] // 100) * 100
                    s_box = (sx, sy, sx + s_w, sy + s_d)
                    pid_s = f"P{p_index:03d}"
                    p_index += 1
                    placements.append({
                        "placement_id": pid_s,
                        "sku": storage_sku,
                        "finish_id": storage_finish,
                        "x_mm": sx,
                        "y_mm": sy,
                        "rotation_deg": 0,
                    })
                    occupied_boxes.append(s_box)

        if n_desks > 0 and n_collab > 0 and collab_sku:
            col_item = self.catalog_by_sku[collab_sku]
            cl_w = col_item.get("dimensions_mm", {}).get("width", 1200)
            cl_d = col_item.get("dimensions_mm", {}).get("depth", 1200)
            for i in range(n_collab):
                pos_col = self._find_valid_placement(
                    cl_w, cl_d, boundary,
                    min_x + 300, max_x - 300, min_y + 300, max_y - 300,
                    occupied_boxes, room_spec, chair_boxes, door_buffers,
                    clearance_boxes=clearance_boxes
                )
                if pos_col:
                    clx, cly = (pos_col[0] // 100) * 100, (pos_col[1] // 100) * 100
                    cl_box = (clx, cly, clx + cl_w, cly + cl_d)
                    pid_col = f"P{p_index:03d}"
                    p_index += 1
                    placements.append({
                        "placement_id": pid_col,
                        "sku": collab_sku,
                        "finish_id": collab_finish,
                        "x_mm": clx,
                        "y_mm": cly,
                        "rotation_deg": 0,
                    })
                    occupied_boxes.append(cl_box)

        if n_acc > 0 and acc_sku:
            acc_item = self.catalog_by_sku[acc_sku]
            ac_w = acc_item.get("dimensions_mm", {}).get("width", 450)
            ac_d = acc_item.get("dimensions_mm", {}).get("depth", 250)
            for i in range(n_acc):
                pos_acc = self._find_valid_placement(
                    ac_w, ac_d, boundary,
                    min_x + 200, max_x - 200, min_y + 200, max_y - 200,
                    occupied_boxes, room_spec, chair_boxes, door_buffers,
                    clearance_boxes=clearance_boxes
                )
                if pos_acc:
                    ax, ay = (pos_acc[0] // 100) * 100, (pos_acc[1] // 100) * 100
                    a_box = (ax, ay, ax + ac_w, ay + ac_d)
                    pid_a = f"P{p_index:03d}"
                    p_index += 1
                    placements.append({
                        "placement_id": pid_a,
                        "sku": acc_sku,
                        "finish_id": acc_finish,
                        "x_mm": ax,
                        "y_mm": ay,
                        "rotation_deg": 0,
                    })
                    occupied_boxes.append(a_box)

        return {
            "room_id": room_id,
            "placements": placements,
        }
