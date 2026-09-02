"""
Deterministic Constraint Engine for RuleBound.
Validates spatial and business constraints according to rules.json / rules.yaml.
Does NOT mutate input layout. No LLM, randomness, timestamps, or floating-point math.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple


def get_placement_bbox(
    x_mm: int,
    y_mm: int,
    width_mm: int,
    depth_mm: int,
    rotation_deg: int
) -> Tuple[int, int, int, int]:
    """
    Returns axis-aligned bounding box (x_min, y_min, x_max, y_max) for placement.
    Rotations supported: 0, 90, 180, 270 degrees.
    """
    rot = rotation_deg % 360
    if rot in (90, 270):
        eff_w, eff_d = depth_mm, width_mm
    else:
        eff_w, eff_d = width_mm, depth_mm

    return (x_mm, y_mm, x_mm + eff_w, y_mm + eff_d)


def check_bbox_overlap(
    box1: Tuple[int, int, int, int],
    box2: Tuple[int, int, int, int]
) -> bool:
    """
    Returns True if box1 and box2 overlap (interior intersection area > 0).
    """
    x1_min, y1_min, x1_max, y1_max = box1
    x2_min, y2_min, x2_max, y2_max = box2

    return (x1_min < x2_max and x1_max > x2_min and y1_min < y2_max and y1_max > y2_min)


def get_bbox_distance(
    box1: Tuple[int, int, int, int],
    box2: Tuple[int, int, int, int]
) -> int:
    """
    Calculates Manhattan/orthogonal gap distance between two non-overlapping bounding boxes.
    Returns 0 if boxes overlap or touch.
    """
    x1_min, y1_min, x1_max, y1_max = box1
    x2_min, y2_min, x2_max, y2_max = box2

    dx = max(0, max(x1_min - x2_max, x2_min - x1_max))
    dy = max(0, max(y1_min - y2_max, y2_min - y1_max))

    if dx > 0 and dy > 0:
        # Diagonal distance integer approximation via pythagoras (round half up)
        return int(math.isqrt(dx * dx + dy * dy))
    return max(dx, dy)


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

    # Clamp t = (w . v) / l2 to [0, 1]
    dot = wx * vx + wy * vy
    if dot <= 0:
        return (px - x1) ** 2 + (py - y1) ** 2
    if dot >= l2:
        return (px - x2) ** 2 + (py - y2) ** 2

    # Projection point: (x1 + dot*vx/l2, y1 + dot*vy/l2)
    # Scaled distance squared: ((px - x1)*l2 - dot*vx)^2 + ((py - y1)*l2 - dot*vy)^2 / l2^2
    num_x = (px - x1) * l2 - dot * vx
    num_y = (py - y1) * l2 - dot * vy
    return (num_x * num_x + num_y * num_y) // (l2 * l2)


def get_door_swing_box(
    door: Dict[str, Any],
    room_bounds: Tuple[int, int],
    swing_clearance_mm: int = 850
) -> Tuple[int, int, int, int]:
    """
    Returns door swing clearance bounding box for a door on a room wall.
    """
    wall = door["wall"]
    offset = door["offset_mm"]
    width = door["width_mm"]
    depth = max(width, swing_clearance_mm)
    room_w, room_h = room_bounds

    if wall == "south":
        return (offset, 0, offset + width, depth)
    elif wall == "north":
        return (offset, room_h - depth, offset + width, room_h)
    elif wall == "west":
        return (0, offset, depth, offset + width)
    elif wall == "east":
        return (room_w - depth, offset, room_w, offset + width)
    else:
        return (offset, 0, offset + width, depth)


def is_point_on_segment(px: int, py: int, x1: int, y1: int, x2: int, y2: int) -> bool:
    """Returns True if point (px, py) lies on line segment (x1, y1)-(x2, y2)."""
    if not (min(x1, x2) <= px <= max(x1, x2) and min(y1, y2) <= py <= max(y1, y2)):
        return False
    return (px - x1) * (y2 - y1) == (py - y1) * (x2 - x1)


def is_point_in_polygon(px: int, py: int, polygon: Sequence[Sequence[Any]]) -> bool:
    """
    Returns True if point (px, py) is inside or on the boundary of the polygon.
    Pure integer arithmetic.
    """
    n = len(polygon)
    if n < 3:
        return False

    for i in range(n):
        x1, y1 = int(polygon[i][0]), int(polygon[i][1])
        x2, y2 = int(polygon[(i + 1) % n][0]), int(polygon[(i + 1) % n][1])
        if is_point_on_segment(px, py, x1, y1, x2, y2):
            return True

    inside = False
    for i in range(n):
        x1, y1 = int(polygon[i][0]), int(polygon[i][1])
        x2, y2 = int(polygon[(i + 1) % n][0]), int(polygon[(i + 1) % n][1])

        if (y1 > py) != (y2 > py):
            dy = y2 - y1
            dx = x2 - x1
            if dy > 0:
                if (py - y1) * dx > (px - x1) * dy:
                    inside = not inside
            else:
                if (py - y1) * dx < (px - x1) * dy:
                    inside = not inside

    return inside


def ccw(ax: int, ay: int, bx: int, by: int, cx: int, cy: int) -> int:
    """Orientation cross product (b-a) x (c-a)."""
    val = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
    if val > 0:
        return 1
    elif val < 0:
        return -1
    return 0


def segments_intersect_strict(
    x1: int, y1: int, x2: int, y2: int,
    x3: int, y3: int, x4: int, y4: int
) -> bool:
    """
    Returns True if line segment (x1,y1)-(x2,y2) strictly intersects (x3,y3)-(x4,y4) in their interior.
    """
    o1 = ccw(x1, y1, x2, y2, x3, y3)
    o2 = ccw(x1, y1, x2, y2, x4, y4)
    o3 = ccw(x3, y3, x4, y4, x1, y1)
    o4 = ccw(x3, y3, x4, y4, x2, y2)

    return (o1 * o2 < 0) and (o3 * o4 < 0)


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


class ConstraintEngine:
    """
    Deterministic constraint engine evaluating Spatial (RB-GEO-*) rules.
    """

    def __init__(
        self,
        catalog: Sequence[Dict[str, Any]],
        finishes: Sequence[Dict[str, Any]],
        rules: Sequence[Dict[str, Any]]
    ):
        self.catalog_by_sku = {item["sku"]: item for item in catalog}
        self.finishes_by_id = {f["finish_id"]: f for f in finishes}
        self.rules_by_id = {r["rule_id"]: r for r in rules}

    def validate_layout(
        self,
        layout: Dict[str, Any],
        room_spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validates layout against spatial and catalog constraints.
        Returns a new layout dictionary with populated violations and status.
        Does NOT mutate input layout.
        """
        room_id = layout["room_id"]
        placements = layout.get("placements", [])

        raw_violations: List[Dict[str, Any]] = []

        # Room boundary bounds
        boundary_coords = room_spec.get("boundary_mm", [])
        if boundary_coords:
            max_x = max(pt[0] for pt in boundary_coords)
            max_y = max(pt[1] for pt in boundary_coords)
        else:
            max_x, max_y = 100000, 100000

        room_w, room_h = int(max_x), int(max_y)

        # Prepared placement info
        prep_placements = []
        for p in placements:
            pid = p["placement_id"]
            sku = p["sku"]
            cat_item = self.catalog_by_sku.get(sku, {})
            dims = cat_item.get("dimensions_mm", {"width": 1000, "depth": 600})
            w_mm = dims.get("width", 1000)
            d_mm = dims.get("depth", 600)
            rot = p.get("rotation_deg", 0)
            bbox = get_placement_bbox(p["x_mm"], p["y_mm"], w_mm, d_mm, rot)

            prep_placements.append({
                "placement_id": pid,
                "sku": sku,
                "family": cat_item.get("family", ""),
                "is_wall_mounted": cat_item.get("wall_mounted", False),
                "bbox": bbox,
                "rot": rot,
                "w_mm": w_mm,
                "d_mm": d_mm,
            })

        # Rule 1: RB-GEO-007 (Inside Room Boundary)
        rule_007 = self.rules_by_id.get("RB-GEO-007", {})
        msg_007 = rule_007.get("message", "Every placement footprint must remain inside the room polygon.")
        for item in prep_placements:
            x1, y1, x2, y2 = item["bbox"]
            is_inside = True

            if boundary_coords:
                is_inside = is_box_inside_polygon(item["bbox"], boundary_coords)
            else:
                if x1 < 0 or y1 < 0 or x2 > room_w or y2 > room_h:
                    is_inside = False

            if not is_inside:
                raw_violations.append({
                    "rule_id": "RB-GEO-007",
                    "message": msg_007,
                    "affected_placement_ids": [item["placement_id"]],
                    "measured": {"x_min": x1, "y_min": y1, "x_max": x2, "y_max": y2},
                    "required": {"room_width": room_w, "room_height": room_h},
                    "repair_options": [],
                })

        # Rule 2: RB-GEO-005 (Min Wall Offset: 100 mm)
        rule_005 = self.rules_by_id.get("RB-GEO-005", {})
        val_005 = rule_005.get("value_mm", 100)
        msg_005 = rule_005.get("message", "Furniture must remain at least 100 mm from a wall unless wall-mounted.")
        for item in prep_placements:
            if item["is_wall_mounted"]:
                continue
            x1, y1, x2, y2 = item["bbox"]
            dist_west = x1
            dist_south = y1
            dist_east = room_w - x2
            dist_north = room_h - y2
            min_dist = min(dist_west, dist_south, dist_east, dist_north)

            if min_dist < val_005:
                raw_violations.append({
                    "rule_id": "RB-GEO-005",
                    "message": msg_005,
                    "affected_placement_ids": [item["placement_id"]],
                    "measured": {"wall_offset_mm": min_dist},
                    "required": {"min_wall_offset_mm": val_005},
                    "repair_options": [],
                })

        # Rule 3: RB-GEO-006 (No Overlap)
        rule_006 = self.rules_by_id.get("RB-GEO-006", {})
        msg_006 = rule_006.get("message", "Furniture footprints may not overlap.")
        n = len(prep_placements)
        for i in range(n):
            for j in range(i + 1, n):
                p1 = prep_placements[i]
                p2 = prep_placements[j]
                if check_bbox_overlap(p1["bbox"], p2["bbox"]):
                    aff = sorted([p1["placement_id"], p2["placement_id"]])
                    raw_violations.append({
                        "rule_id": "RB-GEO-006",
                        "message": msg_006,
                        "affected_placement_ids": aff,
                        "measured": {"overlap": True},
                        "required": {"overlap": False},
                        "repair_options": [],
                    })

        # Rule 4: RB-GEO-003 (Door Swing Clearance: 850 mm)
        rule_003 = self.rules_by_id.get("RB-GEO-003", {})
        val_003 = rule_003.get("value_mm", 850)
        msg_003 = rule_003.get("message", "No furniture may enter the door-swing clearance zone.")
        doors = room_spec.get("doors", [])
        for door in doors:
            door_box = get_door_swing_box(door, (room_w, room_h), val_003)
            for item in prep_placements:
                if check_bbox_overlap(item["bbox"], door_box):
                    raw_violations.append({
                        "rule_id": "RB-GEO-003",
                        "message": msg_003,
                        "affected_placement_ids": [item["placement_id"]],
                        "measured": {"door_id": door.get("door_id", ""), "intersects_swing_zone": True},
                        "required": {"clearance_mm": val_003},
                        "repair_options": [],
                    })

        # Rule 5: RB-GEO-002 (Egress Path Clearance: 1100 mm)
        rule_002 = self.rules_by_id.get("RB-GEO-002", {})
        val_002 = rule_002.get("value_mm", 1100)
        msg_002 = rule_002.get("message", "The marked egress path requires 1100 mm clear width.")
        egress = room_spec.get("egress")
        if egress and egress.get("to_point_mm"):
            from_door_id = egress.get("from_door_id")
            door_obj = next((d for d in doors if d.get("door_id") == from_door_id), doors[0] if doors else None)
            if door_obj:
                wall = door_obj["wall"]
                offset = door_obj["offset_mm"]
                d_w = door_obj["width_mm"]
                if wall == "south":
                    dx_center, dy_center = offset + d_w // 2, 0
                elif wall == "north":
                    dx_center, dy_center = offset + d_w // 2, room_h
                elif wall == "west":
                    dx_center, dy_center = 0, offset + d_w // 2
                else:
                    dx_center, dy_center = room_w, offset + d_w // 2

                tx, ty = egress["to_point_mm"]
                req_radius_sq = (val_002 // 2) ** 2

                for item in prep_placements:
                    x1, y1, x2, y2 = item["bbox"]
                    # Test corners and center of placement against egress line segment
                    pts_to_check = [
                        (x1, y1), (x2, y1), (x2, y2), (x1, y2),
                        ((x1 + x2) // 2, (y1 + y2) // 2)
                    ]
                    violates_egress = False
                    for px, py in pts_to_check:
                        if point_to_segment_dist_sq(px, py, dx_center, dy_center, tx, ty) < req_radius_sq:
                            violates_egress = True
                            break

                    if violates_egress:
                        raw_violations.append({
                            "rule_id": "RB-GEO-002",
                            "message": msg_002,
                            "affected_placement_ids": [item["placement_id"]],
                            "measured": {"egress_clearance_mm": val_002 // 2},
                            "required": {"min_egress_width_mm": val_002},
                            "repair_options": [],
                        })

        # Rule 6: RB-GEO-004 (Desk Rear Clearance: 900 mm)
        rule_004 = self.rules_by_id.get("RB-GEO-004", {})
        val_004 = rule_004.get("value_mm", 900)
        msg_004 = rule_004.get("message", "Occupied desks require 900 mm rear clearance.")
        for item in prep_placements:
            if item["family"] == "desk":
                x1, y1, x2, y2 = item["bbox"]
                # Rear clearance zone extends behind desk (y2 to y2 + 900 for rot 0)
                rot = item["rot"] % 360
                if rot == 0:
                    rear_box = (x1, y2, x2, y2 + val_004)
                elif rot == 90:
                    rear_box = (x1 - val_004, y1, x1, y2)
                elif rot == 180:
                    rear_box = (x1, y1 - val_004, x2, y1)
                else:
                    rear_box = (x2, y1, x2 + val_004, y2)

                # Check if rear clearance box goes outside room or overlaps other furniture
                rear_violates = False
                rx1, ry1, rx2, ry2 = rear_box
                if rx1 < 0 or ry1 < 0 or rx2 > room_w or ry2 > room_h:
                    rear_violates = True
                else:
                    for other in prep_placements:
                        if other["placement_id"] != item["placement_id"]:
                            if check_bbox_overlap(rear_box, other["bbox"]):
                                rear_violates = True
                                break

                if rear_violates:
                    raw_violations.append({
                        "rule_id": "RB-GEO-004",
                        "message": msg_004,
                        "affected_placement_ids": [item["placement_id"]],
                        "measured": {"rear_clearance_mm": 0},
                        "required": {"rear_clearance_mm": val_004},
                        "repair_options": [],
                    })

        # Rule 7: RB-GEO-008 (Chair Rear Clearance: 750 mm)
        rule_008 = self.rules_by_id.get("RB-GEO-008", {})
        val_008 = rule_008.get("value_mm", 750)
        msg_008 = rule_008.get("message", "Task chairs require a 750 mm pull-out zone.")
        for item in prep_placements:
            if item["family"] == "chair":
                x1, y1, x2, y2 = item["bbox"]
                rot = item["rot"] % 360
                if rot == 0:
                    rear_box = (x1, y2, x2, y2 + val_008)
                elif rot == 90:
                    rear_box = (x1 - val_008, y1, x1, y2)
                elif rot == 180:
                    rear_box = (x1, y1 - val_008, x2, y1)
                else:
                    rear_box = (x2, y1, x2 + val_008, y2)

                rear_violates = False
                rx1, ry1, rx2, ry2 = rear_box
                if rx1 < 0 or ry1 < 0 or rx2 > room_w or ry2 > room_h:
                    rear_violates = True
                else:
                    for other in prep_placements:
                        if other["placement_id"] != item["placement_id"]:
                            if check_bbox_overlap(rear_box, other["bbox"]):
                                rear_violates = True
                                break

                if rear_violates:
                    raw_violations.append({
                        "rule_id": "RB-GEO-008",
                        "message": msg_008,
                        "affected_placement_ids": [item["placement_id"]],
                        "measured": {"pull_out_zone_mm": 0},
                        "required": {"pull_out_zone_mm": val_008},
                        "repair_options": [],
                    })

        # Rule 8: RB-GEO-001 (Walkway Clearance: 900 mm)
        rule_001 = self.rules_by_id.get("RB-GEO-001", {})
        val_001 = rule_001.get("value_mm", 900)
        msg_001 = rule_001.get("message", "Primary walkways require 900 mm clear width.")
        for i in range(n):
            for j in range(i + 1, n):
                p1 = prep_placements[i]
                p2 = prep_placements[j]

                # Exclude paired desk + chair workstation relationship (governed by GEO-004 / GEO-008)
                f1, f2 = p1["family"], p2["family"]
                if (f1 == "desk" and f2 == "chair") or (f1 == "chair" and f2 == "desk"):
                    desk_p = p1 if f1 == "desk" else p2
                    chair_p = p2 if f1 == "desk" else p1

                    dx1, dy1, dx2, dy2 = desk_p["bbox"]
                    cx1, cy1, cx2, cy2 = chair_p["bbox"]

                    # Check if chair is aligned horizontally with desk and located in rear/front zone
                    x_over = max(0, min(dx2, cx2) - max(dx1, cx1))
                    if x_over > 0:
                        if (dy2 <= cy1 <= dy2 + 1500) or (cy2 <= dy1 <= cy2 + 1500):
                            continue

                x1a, y1a, x1b, y1b = p1["bbox"]
                x2a, y2a, x2b, y2b = p2["bbox"]

                # Calculate axis-parallel projection overlaps
                x_overlap = max(0, min(x1b, x2b) - max(x1a, x2a))
                y_overlap = max(0, min(y1b, y2b) - max(y1a, y2a))

                gap = 0
                is_walkway_violation = False

                # Facing parallel channel in X (if Y overlaps > 0)
                if y_overlap > 0 and x_overlap == 0:
                    gap_x = max(x1a, x2a) - min(x1b, x2b)
                    if 0 < gap_x < val_001:
                        is_walkway_violation = True
                        gap = gap_x

                # Facing parallel channel in Y (if X overlaps > 0)
                elif x_overlap > 0 and y_overlap == 0:
                    gap_y = max(y1a, y2a) - min(y1b, y2b)
                    if 0 < gap_y < val_001:
                        is_walkway_violation = True
                        gap = gap_y

                if is_walkway_violation:
                    aff = sorted([p1["placement_id"], p2["placement_id"]])
                    raw_violations.append({
                        "rule_id": "RB-GEO-001",
                        "message": msg_001,
                        "affected_placement_ids": aff,
                        "measured": {"walkway_gap_mm": gap},
                        "required": {"min_walkway_gap_mm": val_001},
                        "repair_options": [],
                    })

        # Sort violations deterministically by (rule_id, affected_placement_ids)
        sorted_raw = sorted(
            raw_violations,
            key=lambda v: (v["rule_id"], ",".join(v["affected_placement_ids"]))
        )

        # Assign sequential violation_id (V001, V002, ...)
        final_violations = []
        for idx, v in enumerate(sorted_raw):
            v_copy = dict(v)
            v_copy["violation_id"] = f"V{idx + 1:03d}"
            final_violations.append(v_copy)

        status = "valid" if len(final_violations) == 0 else "invalid"

        return {
            "room_id": room_id,
            "placements": list(placements),
            "violations": final_violations,
            "status": status,
        }
