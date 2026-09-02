"""
Deterministic Arbitration Engine for RuleBound.
Implements spatial repair, candidate ranking, canonical state hashing,
and strict termination bounds according to docs/ARBITRATION_DESIGN.md.
No randomness, timestamps, network calls, LLMs, or floating-point arithmetic.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


@dataclass(frozen=True)
class PlacementProposal:
    placement_id: str
    sku: str
    finish_id: str
    x_mm: int
    y_mm: int
    rotation_deg: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "placement_id": self.placement_id,
            "sku": self.sku,
            "finish_id": self.finish_id,
            "x_mm": self.x_mm,
            "y_mm": self.y_mm,
            "rotation_deg": self.rotation_deg,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PlacementProposal:
        return cls(
            placement_id=data["placement_id"],
            sku=data["sku"],
            finish_id=data["finish_id"],
            x_mm=int(data["x_mm"]),
            y_mm=int(data["y_mm"]),
            rotation_deg=int(data.get("rotation_deg", 0)),
        )


@dataclass(frozen=True)
class ProposedLayout:
    room_id: str
    placements: Tuple[PlacementProposal, ...]

    def canonical_state_hash(self) -> str:
        """
        Returns SHA-256 hash of complete canonical layout state.
        Includes placement identity, SKU, finish, coordinates, and rotation.
        """
        serialized = json.dumps([
            {
                "placement_id": p.placement_id,
                "sku": p.sku,
                "finish_id": p.finish_id,
                "x_mm": p.x_mm,
                "y_mm": p.y_mm,
                "rotation_deg": p.rotation_deg,
            }
            for p in sorted(self.placements, key=lambda item: item.placement_id)
        ], sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "room_id": self.room_id,
            "placements": [p.to_dict() for p in self.placements],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ProposedLayout:
        placements = tuple(PlacementProposal.from_dict(p) for p in data.get("placements", []))
        return cls(room_id=data["room_id"], placements=placements)


@dataclass(frozen=True)
class RepairCandidate:
    op_type: str  # "NUDGE", "ROTATE", "SUBSTITUTE_SKU", "REMOVE_PLACEMENT"
    target_placement_id: str
    params: Dict[str, Any]
    sort_key: Tuple[int, str, str, str]


@dataclass(frozen=True)
class ArbitrationDecision:
    step_number: int
    chosen_repair: RepairCandidate
    resulting_layout_hash: str
    violation_count_before: int
    violation_count_after: int


@dataclass(frozen=True)
class ArbitrationResult:
    room_id: str
    status: str  # "valid", "invalid", "unsatisfiable"
    final_layout: ProposedLayout
    violations: Tuple[Dict[str, Any], ...]
    history: Tuple[ArbitrationDecision, ...]


class ArbitrationEngine:
    """
    Stateful deterministic arbitration decision engine.
    Applies spatial repair operators, deterministic candidate ranking,
    and canonical state tracking to resolve violations or escalate.
    """

    def __init__(
        self,
        catalog: Sequence[Dict[str, Any]],
        finishes: Sequence[Dict[str, Any]],
        rules: Sequence[Dict[str, Any]],
        constraint_engine: Any
    ):
        self.catalog = list(catalog)
        self.catalog_by_sku = {item["sku"]: item for item in catalog}
        self.finishes_by_id = {f["finish_id"]: f for f in finishes}
        self.rules_by_id = {r["rule_id"]: r for r in rules}
        self.constraint_engine = constraint_engine

    def _get_smaller_skus_in_family(self, sku: str) -> List[str]:
        """
        Returns list of SKUs in same catalog family with smaller footprint area (W x D),
        sorted deterministically by footprint area ascending, then SKU ascending.
        """
        cat_item = self.catalog_by_sku.get(sku)
        if not cat_item:
            return []

        family = cat_item.get("family")
        dims = cat_item.get("dimensions_mm", {})
        curr_area = dims.get("width", 0) * dims.get("depth", 0)

        candidates = []
        for item in self.catalog:
            if item.get("family") == family and item["sku"] != sku:
                c_dims = item.get("dimensions_mm", {})
                c_area = c_dims.get("width", 0) * c_dims.get("depth", 0)
                if c_area < curr_area:
                    candidates.append((c_area, item["sku"]))

        candidates.sort(key=lambda pair: (pair[0], pair[1]))
        return [pair[1] for pair in candidates]

    def count_seating_capacity(self, layout: ProposedLayout) -> int:
        """
        Returns the number of active placements whose catalog family is 'chair'.
        """
        count = 0
        for p in layout.placements:
            cat_item = self.catalog_by_sku.get(p.sku, {})
            if cat_item.get("family") == "chair":
                count += 1
        return count

    def count_workstation_capacity(self, layout: ProposedLayout) -> int:
        """
        Returns the number of active placements whose catalog family is 'desk'.
        """
        count = 0
        for p in layout.placements:
            cat_item = self.catalog_by_sku.get(p.sku, {})
            if cat_item.get("family") == "desk":
                count += 1
        return count

    def _get_placement_dims(self, placement: PlacementProposal) -> Tuple[int, int]:
        cat_item = self.catalog_by_sku.get(placement.sku, {})
        dims = cat_item.get("dimensions_mm", {})
        w = int(dims.get("width", cat_item.get("width_mm", 1000)))
        d = int(dims.get("depth", cat_item.get("depth_mm", 1000)))
        if placement.rotation_deg in (90, 270):
            w, d = d, w
        return w, d

    def _find_desk_chair_pairs(self, layout: ProposedLayout) -> Dict[str, Tuple[str, str]]:
        """
        Identifies paired desk and task-chair placements in layout based on
        actual placement geometry and catalog dimensions.
        Returns dict mapping placement_id -> (desk_placement_id, chair_placement_id).
        """
        desks = [p for p in layout.placements if self.catalog_by_sku.get(p.sku, {}).get("family") == "desk"]
        chairs = [p for p in layout.placements if self.catalog_by_sku.get(p.sku, {}).get("family") == "chair"]

        pairs: Dict[str, Tuple[str, str]] = {}
        used_chairs: Set[str] = set()

        for d in sorted(desks, key=lambda item: item.placement_id):
            d_w, d_d = self._get_placement_dims(d)
            rot = d.rotation_deg % 360

            matching_chairs = []
            for c in chairs:
                if c.placement_id in used_chairs:
                    continue
                if (c.rotation_deg % 360) != rot:
                    continue

                c_w, c_d = self._get_placement_dims(c)
                matched = False
                dist = 0

                if rot == 0:
                    if abs((d.x_mm + (d_w - c_w) // 2) - c.x_mm) <= 200 and c.y_mm == d.y_mm + d_d + 900:
                        matched = True
                        dist = abs((d.x_mm + (d_w - c_w) // 2) - c.x_mm)
                elif rot == 90:
                    if abs((d.y_mm + (d_d - c_d) // 2) - c.y_mm) <= 200 and c.x_mm == d.x_mm - c_w - 900:
                        matched = True
                        dist = abs((d.y_mm + (d_d - c_d) // 2) - c.y_mm)
                elif rot == 180:
                    if abs((d.x_mm + (d_w - c_w) // 2) - c.x_mm) <= 200 and c.y_mm == d.y_mm - c_d - 900:
                        matched = True
                        dist = abs((d.x_mm + (d_w - c_w) // 2) - c.x_mm)
                elif rot == 270:
                    if abs((d.y_mm + (d_d - c_d) // 2) - c.y_mm) <= 200 and c.x_mm == d.x_mm + d_w + 900:
                        matched = True
                        dist = abs((d.y_mm + (d_d - c_d) // 2) - c.y_mm)

                if matched:
                    matching_chairs.append((dist, c.placement_id))

            if matching_chairs:
                matching_chairs.sort(key=lambda item: (item[0], item[1]))
                best_c_id = matching_chairs[0][1]
                used_chairs.add(best_c_id)
                pair_tuple = (d.placement_id, best_c_id)
                pairs[d.placement_id] = pair_tuple
                pairs[best_c_id] = pair_tuple

        return pairs

    def _find_contiguous_pod_runs(
        self,
        layout: ProposedLayout,
        pod_map: Dict[str, Tuple[str, str]]
    ) -> List[List[Tuple[str, str]]]:
        """
        Groups paired desk-chair pods into contiguous touching runs.

        Two pods are considered adjacent (in the same row/run) when their desk
        footprints share the same row coordinate AND are directly touching or
        overlap by at most ADJACENCY_TOLERANCE_MM (10mm to absorb integer-grid
        rounding). Only pods with identical desk rotation are merged.

        Pods are sorted by column coordinate (x_mm for rot=0/180, y_mm for
        rot=90/270) so runs are in deterministic left-to-right / bottom-to-top
        order. Each run is returned as a sorted list of (desk_pid, chair_pid)
        tuples.

        This tolerance is documentation-calibrated: the generator places desks
        at exactly touching positions (gap = 0mm). The 10mm tolerance absorbs
        any rounding artefacts from integer coordinate arithmetic.
        """
        ADJACENCY_TOLERANCE_MM = 10

        # Collect unique (desk_pid, chair_pid) pairs, sorted for determinism
        unique_pairs = sorted(
            set(pod_map.values()),
            key=lambda pair: pair[0]
        )

        p_map = {p.placement_id: p for p in layout.placements}
        visited: Set[str] = set()
        runs: List[List[Tuple[str, str]]] = []

        for d_id, c_id in unique_pairs:
            if d_id in visited:
                continue

            d_prop = p_map[d_id]
            rot = d_prop.rotation_deg % 360
            d_w, d_d = self._get_placement_dims(d_prop)

            # BFS / flood-fill over touching pods
            run_set: Set[str] = {d_id}
            queue = [(d_id, c_id)]
            visited.add(d_id)

            qi = 0
            while qi < len(queue):
                cur_d_id, cur_c_id = queue[qi]
                qi += 1
                cur_prop = p_map[cur_d_id]
                cur_w, cur_d = self._get_placement_dims(cur_prop)

                for od_id, oc_id in unique_pairs:
                    if od_id in run_set:
                        continue
                    od_prop = p_map[od_id]
                    if (od_prop.rotation_deg % 360) != rot:
                        continue
                    od_w, od_d = self._get_placement_dims(od_prop)

                    is_adj = False
                    if rot in (0, 180):
                        # Pods share same Y anchor, touch in X dimension
                        same_row = cur_prop.y_mm == od_prop.y_mm
                        gap_right = od_prop.x_mm - (cur_prop.x_mm + cur_w)
                        gap_left = cur_prop.x_mm - (od_prop.x_mm + od_w)
                        if same_row and (abs(gap_right) <= ADJACENCY_TOLERANCE_MM or abs(gap_left) <= ADJACENCY_TOLERANCE_MM):
                            is_adj = True
                    elif rot in (90, 270):
                        # Pods share same X anchor, touch in Y dimension
                        same_col = cur_prop.x_mm == od_prop.x_mm
                        gap_top = od_prop.y_mm - (cur_prop.y_mm + cur_d)
                        gap_bot = cur_prop.y_mm - (od_prop.y_mm + od_d)
                        if same_col and (abs(gap_top) <= ADJACENCY_TOLERANCE_MM or abs(gap_bot) <= ADJACENCY_TOLERANCE_MM):
                            is_adj = True

                    if is_adj:
                        run_set.add(od_id)
                        visited.add(od_id)
                        queue.append((od_id, oc_id))

            # Sort run by column coordinate for deterministic ordering
            run_pods: List[Tuple[str, str]] = []
            for od_id, oc_id in unique_pairs:
                if od_id in run_set:
                    run_pods.append((od_id, oc_id))

            if rot in (0, 180):
                run_pods.sort(key=lambda pr: (p_map[pr[0]].x_mm, pr[0]))
            else:
                run_pods.sort(key=lambda pr: (p_map[pr[0]].y_mm, pr[0]))

            runs.append(run_pods)

        return runs

    def generate_repair_candidates(
        self,
        layout: ProposedLayout,
        violations: Sequence[Dict[str, Any]]
    ) -> List[RepairCandidate]:
        """
        Generates candidate repair operations for active violations,
        including atomic MOVE_WORKSTATION_POD and targeted nudges.
        Returns candidates sorted deterministically by SortKey.
        """
        candidates: List[RepairCandidate] = []
        seen_keys: Set[Tuple[int, str, str, str]] = set()

        p_map = {p.placement_id: p for p in layout.placements}
        pod_map = self._find_desk_chair_pairs(layout)

        for v in violations:
            rule_id = v.get("rule_id", "UNKNOWN")
            affected_pids = v.get("affected_placement_ids", [])

            for pid in affected_pids:
                target_prop = p_map.get(pid)
                if not target_prop:
                    continue

                w1, d1 = self._get_placement_dims(target_prop)
                b1 = (target_prop.x_mm, target_prop.y_mm, target_prop.x_mm + w1, target_prop.y_mm + d1)

                # 0. MOVE_WORKSTATION_POD candidates (op_type_rank = 0)
                if pid in pod_map:
                    d_pid, c_pid = pod_map[pid]
                    p_min, p_max = sorted([d_pid, c_pid])
                    pod_translations = [
                        (-100, 0), (100, 0), (0, -100), (0, 100),
                        (-200, 0), (200, 0), (0, -200), (0, 200),
                        (0, -300), (0, 300)
                    ]
                    for dx, dy in pod_translations:
                        param_str = f"POD_{p_min}_{p_max}_DX_{dx:+d}_DY_{dy:+d}"
                        key = (0, rule_id, d_pid, param_str)
                        if key not in seen_keys:
                            seen_keys.add(key)
                            candidates.append(RepairCandidate(
                                op_type="MOVE_WORKSTATION_POD",
                                target_placement_id=d_pid,
                                params={
                                    "desk_placement_id": d_pid,
                                    "chair_placement_id": c_pid,
                                    "dx_mm": dx,
                                    "dy_mm": dy,
                                },
                                sort_key=key
                            ))

                # Standard nudge candidates (±100mm, ±200mm)
                standard_nudges = [(-200, 0), (-100, 0), (100, 0), (200, 0), (0, -200), (0, -100), (0, 100), (0, 200)]
                targeted_nudges: List[Tuple[int, int]] = []

                if rule_id == "RB-GEO-001" and len(affected_pids) >= 2:
                    other_pid = affected_pids[1] if affected_pids[0] == pid else affected_pids[0]
                    other_prop = p_map.get(other_pid)
                    if other_prop:
                        w2, d2 = self._get_placement_dims(other_prop)
                        b2 = (other_prop.x_mm, other_prop.y_mm, other_prop.x_mm + w2, other_prop.y_mm + d2)

                        x_ov = min(b1[2], b2[2]) - max(b1[0], b2[0])
                        y_ov = min(b1[3], b2[3]) - max(b1[1], b2[1])

                        if x_ov > 0:  # Facing along Y axis (X channels overlap)
                            gap_y = max(b1[1] - b2[3], b2[1] - b1[3])
                            dist = 900 - gap_y
                            if dist > 0:
                                disp = ((dist + 99) // 100) * 100
                                if b1[1] >= b2[3]:  # target is south/above other -> move +Y
                                    targeted_nudges.extend([(0, disp), (0, disp + 100)])
                                elif b1[3] <= b2[1]:  # target is north/below other -> move -Y
                                    targeted_nudges.extend([(0, -disp), (0, -(disp + 100))])
                        elif y_ov > 0:  # Facing along X axis (Y channels overlap)
                            gap_x = max(b1[0] - b2[2], b2[0] - b1[2])
                            dist = 900 - gap_x
                            if dist > 0:
                                disp = ((dist + 99) // 100) * 100
                                if b1[0] >= b2[2]:  # target is right/east of other -> move +X
                                    targeted_nudges.extend([(disp, 0), (disp + 100, 0)])
                                elif b1[2] <= b2[0]:  # target is left/west of other -> move -X
                                    targeted_nudges.extend([(-disp, 0), (-(disp + 100), 0)])

                elif rule_id == "RB-GEO-002":
                    meas = v.get("measured", {})
                    clearance = meas.get("clearance_mm", 500)
                    dist = max(100, 1100 - clearance)
                    disp = ((dist + 99) // 100) * 100
                    targeted_nudges.extend([(disp, 0), (-disp, 0), (0, disp), (0, -disp)])

                # 1. NUDGE candidates (standard + targeted)
                all_nudges = standard_nudges + targeted_nudges
                for dx, dy in all_nudges:
                    param_str = f"DX_{dx:+d}_DY_{dy:+d}"
                    key = (1, rule_id, pid, param_str)
                    if key not in seen_keys:
                        seen_keys.add(key)
                        candidates.append(RepairCandidate(
                            op_type="NUDGE",
                            target_placement_id=pid,
                            params={"dx_mm": dx, "dy_mm": dy},
                            sort_key=key
                        ))

                # 2. ROTATE candidates (op_type_rank = 2)
                for delta in [90, 180, 270]:
                    param_str = f"ROT_{delta}"
                    key = (2, rule_id, pid, param_str)
                    if key not in seen_keys:
                        seen_keys.add(key)
                        candidates.append(RepairCandidate(
                            op_type="ROTATE",
                            target_placement_id=pid,
                            params={"delta_deg": delta},
                            sort_key=key
                        ))

                # 3. SUBSTITUTE_SKU candidates (op_type_rank = 3)
                smaller_skus = self._get_smaller_skus_in_family(target_prop.sku)
                for sub_sku in smaller_skus:
                    param_str = f"SUB_{sub_sku}"
                    key = (3, rule_id, pid, param_str)
                    if key not in seen_keys:
                        seen_keys.add(key)
                        candidates.append(RepairCandidate(
                            op_type="SUBSTITUTE_SKU",
                            target_placement_id=pid,
                            params={"substitute_sku": sub_sku},
                            sort_key=key
                        ))

                # 4. REMOVE_PLACEMENT candidates (op_type_rank = 4)
                # Hard semantic precondition: mandatory seating and workstations cannot be deleted below required minimums
                target_fam = self.catalog_by_sku.get(target_prop.sku, {}).get("family", "")
                if target_fam == "chair":
                    if self.count_seating_capacity(layout) <= getattr(self, "_active_required_capacity", 0):
                        continue
                elif target_fam == "desk":
                    if self.count_workstation_capacity(layout) <= getattr(self, "_active_required_workstations", 0):
                        continue

                param_str = "REMOVE"
                key = (4, rule_id, pid, param_str)
                if key not in seen_keys:
                    seen_keys.add(key)
                    candidates.append(RepairCandidate(
                        op_type="REMOVE_PLACEMENT",
                        target_placement_id=pid,
                        params={},
                        sort_key=key
                    ))

        # ── ROW_GROUP_SHIFT candidates (op_type_rank = -1, highest priority) ──
        # Generate run-shift and suffix-split candidates unconditionally
        # (not gated on a specific violation pid). These are deduplicated via
        # seen_keys so they are only emitted once per (run, suffix, delta).
        runs = self._find_contiguous_pod_runs(layout, pod_map)
        row_translations = [
            (0, -100), (0, 100), (0, -200), (0, 200),
            (-100, 0), (100, 0), (-200, 0), (200, 0),
            (0, -300), (0, 300), (0, -400), (0, 400),
        ]
        for run in runs:
            if len(run) < 2:
                # Single pod: MOVE_WORKSTATION_POD already covers it
                continue
            # Whole-run shift and all suffix splits (split at index 1..len-1)
            splits: List[List[Tuple[str, str]]] = [run]
            for split_at in range(1, len(run)):
                splits.append(run[split_at:])
            for group in splits:
                # Canonical group identifier: sorted desk IDs joined
                group_key_str = "_".join(sorted(d for d, _ in group))
                all_pids_in_group = [pid for d, c in group for pid in (d, c)]
                for dx, dy in row_translations:
                    param_str = f"RGS_{group_key_str}_DX_{dx:+d}_DY_{dy:+d}"
                    # Use -1 rank so ROW_GROUP_SHIFT is tried first
                    key = (-1, "ROW_GROUP_SHIFT", group[0][0], param_str)
                    if key not in seen_keys:
                        seen_keys.add(key)
                        candidates.append(RepairCandidate(
                            op_type="ROW_GROUP_SHIFT",
                            target_placement_id=group[0][0],
                            params={
                                "desk_ids": [d for d, _ in group],
                                "chair_ids": [c for _, c in group],
                                "all_placement_ids": all_pids_in_group,
                                "dx_mm": dx,
                                "dy_mm": dy,
                            },
                            sort_key=key
                        ))

        # Sort candidates deterministically by sort_key
        candidates.sort(key=lambda c: c.sort_key)
        return candidates

    def apply_repair(
        self,
        layout: ProposedLayout,
        repair: RepairCandidate
    ) -> ProposedLayout:
        """
        Applies repair candidate to layout, returning a new ProposedLayout.
        Does NOT mutate input layout.
        """
        if repair.op_type == "MOVE_WORKSTATION_POD":
            d_pid = repair.params.get("desk_placement_id", "")
            c_pid = repair.params.get("chair_placement_id", "")
            dx = repair.params.get("dx_mm", 0)
            dy = repair.params.get("dy_mm", 0)

            new_placements = []
            for p in layout.placements:
                if p.placement_id in (d_pid, c_pid):
                    new_p = PlacementProposal(
                        placement_id=p.placement_id,
                        sku=p.sku,
                        finish_id=p.finish_id,
                        x_mm=p.x_mm + dx,
                        y_mm=p.y_mm + dy,
                        rotation_deg=p.rotation_deg,
                    )
                    new_placements.append(new_p)
                else:
                    new_placements.append(p)
            return ProposedLayout(room_id=layout.room_id, placements=tuple(new_placements))

        if repair.op_type == "ROW_GROUP_SHIFT":
            all_pids = set(repair.params.get("all_placement_ids", []))
            dx = repair.params.get("dx_mm", 0)
            dy = repair.params.get("dy_mm", 0)
            new_placements = []
            for p in layout.placements:
                if p.placement_id in all_pids:
                    new_placements.append(PlacementProposal(
                        placement_id=p.placement_id,
                        sku=p.sku,
                        finish_id=p.finish_id,
                        x_mm=p.x_mm + dx,
                        y_mm=p.y_mm + dy,
                        rotation_deg=p.rotation_deg,
                    ))
                else:
                    new_placements.append(p)
            return ProposedLayout(room_id=layout.room_id, placements=tuple(new_placements))

        pid = repair.target_placement_id
        new_placements = []

        for p in layout.placements:
            if p.placement_id == pid:
                if repair.op_type == "NUDGE":
                    dx = repair.params.get("dx_mm", 0)
                    dy = repair.params.get("dy_mm", 0)
                    new_p = PlacementProposal(
                        placement_id=p.placement_id,
                        sku=p.sku,
                        finish_id=p.finish_id,
                        x_mm=p.x_mm + dx,
                        y_mm=p.y_mm + dy,
                        rotation_deg=p.rotation_deg,
                    )
                    new_placements.append(new_p)

                elif repair.op_type == "ROTATE":
                    delta = repair.params.get("delta_deg", 90)
                    new_rot = (p.rotation_deg + delta) % 360
                    new_p = PlacementProposal(
                        placement_id=p.placement_id,
                        sku=p.sku,
                        finish_id=p.finish_id,
                        x_mm=p.x_mm,
                        y_mm=p.y_mm,
                        rotation_deg=new_rot,
                    )
                    new_placements.append(new_p)

                elif repair.op_type == "SUBSTITUTE_SKU":
                    sub_sku = repair.params.get("substitute_sku", p.sku)
                    new_p = PlacementProposal(
                        placement_id=p.placement_id,
                        sku=sub_sku,
                        finish_id=p.finish_id,
                        x_mm=p.x_mm,
                        y_mm=p.y_mm,
                        rotation_deg=p.rotation_deg,
                    )
                    new_placements.append(new_p)

                elif repair.op_type == "REMOVE_PLACEMENT":
                    # Omit placement p from new_placements
                    pass
            else:
                new_placements.append(p)

        return ProposedLayout(room_id=layout.room_id, placements=tuple(new_placements))

    def arbitrate(
        self,
        initial_layout_dict: Dict[str, Any],
        room_spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Executes the deterministic arbitration state machine for candidate layout.
        Uses a deterministic lexicographic objective model:
            candidate_objective = (
                capacity_shortfall,
                spatial_violation_count,
                distinct_placements_touched,
                total_displacement,
                operation_rank,
                target_placement_id,
                canonical_parameters
            )
        Returns a schema-compliant layout output dictionary matching schemas/layout.schema.json.
        """
        initial_layout = ProposedLayout.from_dict(initial_layout_dict)
        current_layout = initial_layout
        required_capacity = int(room_spec.get("capacity", 1))
        required_workstations = room_spec.get("required_workstations")
        if required_workstations is None:
            required_workstations = room_spec.get("required_desks")
        if required_workstations is None:
            required_workstations = self.count_workstation_capacity(initial_layout)
        required_workstations = int(required_workstations)

        self._active_required_capacity = required_capacity
        self._active_required_workstations = required_workstations
        n_placements = len(current_layout.placements)
        k_max = min(50, max(10, 10 * n_placements))

        # Initial full revalidation
        validation_res = self.constraint_engine.validate_layout(current_layout.to_dict(), room_spec)
        current_violations = validation_res.get("violations", [])
        current_seating = self.count_seating_capacity(current_layout)
        current_desks = self.count_workstation_capacity(current_layout)
        current_seating_shortfall = max(0, required_capacity - current_seating)
        current_workstation_shortfall = max(0, required_workstations - current_desks)
        current_shortfall = current_seating_shortfall + current_workstation_shortfall
        current_spatial_count = len(current_violations)

        if current_shortfall == 0 and current_spatial_count == 0:
            return {
                "room_id": current_layout.room_id,
                "placements": [p.to_dict() for p in current_layout.placements],
                "violations": [],
                "status": "valid",
            }

        # Map operation type to integer rank
        op_ranks = {"ROW_GROUP_SHIFT": -1, "MOVE_WORKSTATION_POD": 0, "NUDGE": 1, "ROTATE": 2, "SUBSTITUTE_SKU": 3, "REMOVE_PLACEMENT": 4}

        def get_canonical_param_str(cand: RepairCandidate) -> str:
            if cand.op_type == "ROW_GROUP_SHIFT":
                desk_ids = sorted(cand.params.get("desk_ids", []))
                dx = cand.params.get("dx_mm", 0)
                dy = cand.params.get("dy_mm", 0)
                group_key_str = "_".join(desk_ids)
                return f"RGS_{group_key_str}_DX_{dx:+d}_DY_{dy:+d}"
            elif cand.op_type == "MOVE_WORKSTATION_POD":
                d_pid = cand.params.get("desk_placement_id", "")
                c_pid = cand.params.get("chair_placement_id", "")
                dx = cand.params.get("dx_mm", 0)
                dy = cand.params.get("dy_mm", 0)
                p_min, p_max = sorted([d_pid, c_pid])
                return f"POD_{p_min}_{p_max}_DX_{dx:+d}_DY_{dy:+d}"
            elif cand.op_type == "NUDGE":
                dx = cand.params.get("dx_mm", 0)
                dy = cand.params.get("dy_mm", 0)
                return f"DX_{dx:+d}_DY_{dy:+d}"
            elif cand.op_type == "ROTATE":
                rot = cand.params.get("delta_deg", 90)
                return f"ROT_{rot}"
            elif cand.op_type == "SUBSTITUTE_SKU":
                sub_sku = cand.params.get("substitute_sku", "")
                return f"SUB_{sub_sku}"
            elif cand.op_type == "REMOVE_PLACEMENT":
                return "REMOVE"
            return ""

        def calc_displacement(init_lay: ProposedLayout, cand_lay: ProposedLayout) -> int:
            init_map = {p.placement_id: (p.x_mm, p.y_mm) for p in init_lay.placements}
            tot_disp = 0
            for p in cand_lay.placements:
                if p.placement_id in init_map:
                    ix, iy = init_map[p.placement_id]
                    dx = p.x_mm - ix
                    dy = p.y_mm - iy
                    tot_disp += int(math.isqrt(dx * dx + dy * dy))
            return tot_disp

        def calc_distinct_placements(init_lay: ProposedLayout, cand_lay: ProposedLayout) -> int:
            init_map = {p.placement_id: (p.x_mm, p.y_mm, p.sku, p.rotation_deg) for p in init_lay.placements}
            cand_map = {p.placement_id: (p.x_mm, p.y_mm, p.sku, p.rotation_deg) for p in cand_lay.placements}
            touched = set()
            for pid, val in init_map.items():
                if pid not in cand_map or cand_map[pid] != val:
                    touched.add(pid)
            for pid in cand_map:
                if pid not in init_map:
                    touched.add(pid)
            return len(touched)

        current_objective = (
            current_shortfall,
            current_spatial_count,
            0,
            0,
            0,
            "",
            ""
        )

        # Session-local failed candidate memory (tabu set)
        tabu_candidates: Set[Tuple[str, str, str]] = set()

        step = 0
        best_layout = current_layout
        best_violations = list(current_violations)
        best_objective = current_objective
        termination_reason = ""

        while step < k_max:
            candidates = self.generate_repair_candidates(current_layout, current_violations)

            # Collect and rank all candidate repairs that produce STRICT LEXICOGRAPHIC IMPROVEMENT
            improving_candidates = []

            for cand in candidates:
                param_str = get_canonical_param_str(cand)
                tabu_key = (cand.target_placement_id, cand.op_type, param_str)

                # Skip candidate if recorded in session tabu memory
                if tabu_key in tabu_candidates:
                    continue

                # Hard semantic precondition gate: reject any removal that violates seating or workstation requirements
                cand_layout = self.apply_repair(current_layout, cand)
                if cand.op_type == "REMOVE_PLACEMENT":
                    cand_seating = self.count_seating_capacity(cand_layout)
                    cand_desks = self.count_workstation_capacity(cand_layout)
                    if cand_seating < required_capacity or cand_desks < required_workstations:
                        tabu_candidates.add(tabu_key)
                        continue

                cand_val_res = self.constraint_engine.validate_layout(cand_layout.to_dict(), room_spec)
                cand_violations = cand_val_res.get("violations", [])
                cand_seating = self.count_seating_capacity(cand_layout)
                cand_desks = self.count_workstation_capacity(cand_layout)

                cand_shortfall = max(0, required_capacity - cand_seating) + max(0, required_workstations - cand_desks)
                cand_spatial_count = len(cand_violations)
                cand_disp = calc_displacement(initial_layout, cand_layout)
                cand_touched = calc_distinct_placements(initial_layout, cand_layout)
                op_r = op_ranks.get(cand.op_type, 99)

                candidate_objective = (
                    cand_shortfall,
                    cand_spatial_count,
                    cand_touched,
                    cand_disp,
                    op_r,
                    cand.target_placement_id,
                    param_str
                )

                # STRICT IMPROVEMENT GATE: candidate_objective < current_objective (Lexicographic)
                if candidate_objective < current_objective:
                    improving_candidates.append((candidate_objective, cand, cand_layout, cand_violations))
                else:
                    # Failed to strictly improve layout objective -> add to session tabu memory
                    tabu_candidates.add(tabu_key)

            if not improving_candidates:
                # Local repair trajectory exhausted
                termination_reason = "local_repair_exhausted"
                break

            # Select candidate with lowest lexicographic objective tuple
            improving_candidates.sort(key=lambda item: item[0])
            best_obj, chosen_repair, next_layout, next_violations = improving_candidates[0]

            step += 1
            current_layout = next_layout
            current_violations = next_violations
            current_objective = best_obj

            if best_obj < best_objective:
                best_objective = best_obj
                best_layout = next_layout
                best_violations = list(next_violations)

            # Check final acceptance criteria (0 capacity shortfall, 0 spatial violations)
            if best_obj[0] == 0 and best_obj[1] == 0:
                return {
                    "room_id": next_layout.room_id,
                    "placements": [p.to_dict() for p in next_layout.placements],
                    "violations": [],
                    "status": "valid",
                }

        if step >= k_max and not termination_reason:
            termination_reason = "operational_limit_reached"

        # Construct schema-valid unsatisfiable output
        final_violations = []
        achieved_seating = self.count_seating_capacity(best_layout)
        achieved_desks = self.count_workstation_capacity(best_layout)

        if best_violations:
            for idx, v in enumerate(best_violations):
                v_copy = dict(v)
                m = dict(v_copy.get("measured", {}))
                m["achieved_seating_capacity"] = achieved_seating
                m["achieved_workstation_capacity"] = achieved_desks
                m["termination_reason"] = termination_reason
                m["unresolved_spatial_violations"] = len(best_violations)
                v_copy["measured"] = m

                req = dict(v_copy.get("required", {}))
                req["required_seating_capacity"] = required_capacity
                req["required_workstation_capacity"] = required_workstations
                v_copy["required"] = req

                opts = list(v_copy.get("repair_options", []))
                opts.append({
                    "action": "human_escalation",
                    "trade_off": f"Unresolvable room requirements: achieved {achieved_seating}/{required_capacity} seats, {achieved_desks}/{required_workstations} workstations with {len(best_violations)} unresolved spatial violations."
                })
                v_copy["repair_options"] = opts
                final_violations.append(v_copy)
        else:
            # Seating or workstation requirement unsatisfied despite 0 spatial violations
            final_violations.append({
                "violation_id": "V001",
                "rule_id": "CAPACITY_FEASIBILITY",
                "message": f"Unsatisfiable layout: Requirements achieved ({achieved_seating} seats, {achieved_desks} workstations) do not satisfy required ({required_capacity} seats, {required_workstations} workstations). Termination reason: {termination_reason}.",
                "affected_placement_ids": [p.placement_id for p in best_layout.placements[:1]],
                "measured": {
                    "achieved_seating_capacity": achieved_seating,
                    "achieved_workstation_capacity": achieved_desks,
                    "termination_reason": termination_reason,
                    "unresolved_spatial_violations": 0,
                },
                "required": {
                    "required_seating_capacity": required_capacity,
                    "required_workstation_capacity": required_workstations,
                },
                "repair_options": [
                    {
                        "action": "human_escalation",
                        "trade_off": f"Reconcile room requirements: requested {required_capacity} seats and {required_workstations} workstations."
                    }
                ]
            })

        return {
            "room_id": best_layout.room_id,
            "placements": [p.to_dict() for p in best_layout.placements],
            "violations": final_violations,
            "status": "unsatisfiable",
        }
