"""
Deterministic Arbitration Engine for RuleBound.
Implements spatial repair, candidate ranking, canonical state hashing,
and strict termination bounds according to docs/ARBITRATION_DESIGN.md.
No randomness, timestamps, network calls, LLMs, or floating-point arithmetic.
"""
from __future__ import annotations

import hashlib
import json
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

    def generate_repair_candidates(
        self,
        layout: ProposedLayout,
        violations: Sequence[Dict[str, Any]]
    ) -> List[RepairCandidate]:
        """
        Generates candidate repair operations for active violations.
        Returns candidates sorted deterministically by SortKey.
        """
        candidates: List[RepairCandidate] = []
        seen_keys: Set[Tuple[int, str, str, str]] = set()

        for v in violations:
            rule_id = v.get("rule_id", "UNKNOWN")
            affected_pids = v.get("affected_placement_ids", [])

            for pid in affected_pids:
                # Find target placement
                target_prop = next((p for p in layout.placements if p.placement_id == pid), None)
                if not target_prop:
                    continue

                # 1. NUDGE candidates (op_type_rank = 1)
                for dx in [-200, -100, 100, 200]:
                    for dy in [-200, -100, 100, 200]:
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
        Returns a schema-compliant layout output dictionary matching schemas/layout.schema.json.
        """
        current_layout = ProposedLayout.from_dict(initial_layout_dict)
        required_capacity = int(room_spec.get("capacity", 1))
        n_placements = len(current_layout.placements)
        k_max = min(50, max(10, 10 * n_placements))

        visited_hashes: Set[str] = set()
        initial_hash = current_layout.canonical_state_hash()
        visited_hashes.add(initial_hash)

        history: List[ArbitrationDecision] = []

        # Step 0: Initial full revalidation
        validation_res = self.constraint_engine.validate_layout(current_layout.to_dict(), room_spec)
        current_violations = validation_res.get("violations", [])
        current_seating = self.count_seating_capacity(current_layout)

        if len(current_violations) == 0 and current_seating >= required_capacity:
            return {
                "room_id": current_layout.room_id,
                "placements": [p.to_dict() for p in current_layout.placements],
                "violations": [],
                "status": "valid",
            }

        step = 0
        best_layout = current_layout
        best_violations = list(current_violations)
        best_violation_count = len(current_violations)
        termination_reason = ""

        while step < k_max:
            candidates = self.generate_repair_candidates(current_layout, current_violations)

            # Find first unvisited candidate
            chosen_repair: Optional[RepairCandidate] = None
            next_layout: Optional[ProposedLayout] = None
            next_hash: Optional[str] = None

            for cand in candidates:
                cand_layout = self.apply_repair(current_layout, cand)
                cand_hash = cand_layout.canonical_state_hash()
                if cand_hash not in visited_hashes:
                    chosen_repair = cand
                    next_layout = cand_layout
                    next_hash = cand_hash
                    break

            if not chosen_repair or not next_layout or not next_hash:
                # Local deterministic repair frontier exhausted
                termination_reason = "local_repair_exhausted"
                break

            # Mark state visited
            visited_hashes.add(next_hash)
            step += 1

            # FULL Revalidation of candidate state
            next_val_res = self.constraint_engine.validate_layout(next_layout.to_dict(), room_spec)
            next_violations = next_val_res.get("violations", [])
            next_seating = self.count_seating_capacity(next_layout)

            decision = ArbitrationDecision(
                step_number=step,
                chosen_repair=chosen_repair,
                resulting_layout_hash=next_hash,
                violation_count_before=len(current_violations),
                violation_count_after=len(next_violations),
            )
            history.append(decision)

            # Update best state tracking
            if len(next_violations) < best_violation_count:
                best_violation_count = len(next_violations)
                best_layout = next_layout
                best_violations = list(next_violations)

            # Check three acceptance criteria:
            # 1. Spatial validity (0 spatial violations)
            # 2. Seating feasibility (seating count >= capacity)
            # 3. Final acceptance
            if len(next_violations) == 0 and next_seating >= required_capacity:
                return {
                    "room_id": next_layout.room_id,
                    "placements": [p.to_dict() for p in next_layout.placements],
                    "violations": [],
                    "status": "valid",
                }

            # State transition to candidate state for next iteration
            current_layout = next_layout
            current_violations = next_violations

        if step >= k_max and not termination_reason:
            termination_reason = "operational_limit_reached"

        # Construct schema-valid unsatisfiable output
        final_violations = []
        achieved_seating = self.count_seating_capacity(best_layout)

        if best_violations:
            for idx, v in enumerate(best_violations):
                v_copy = dict(v)
                m = dict(v_copy.get("measured", {}))
                m["achieved_seating_capacity"] = achieved_seating
                m["termination_reason"] = termination_reason
                m["unresolved_spatial_violations"] = len(best_violations)
                v_copy["measured"] = m

                req = dict(v_copy.get("required", {}))
                req["required_seating_capacity"] = required_capacity
                v_copy["required"] = req

                opts = list(v_copy.get("repair_options", []))
                opts.append({
                    "action": "human_escalation",
                    "trade_off": f"Unresolvable room requirements: achieved {achieved_seating} seats vs required {required_capacity}."
                })
                v_copy["repair_options"] = opts
                final_violations.append(v_copy)
        else:
            # Seating capacity unsatisfied despite 0 spatial violations (e.g. via REMOVE_PLACEMENT)
            final_violations.append({
                "violation_id": "V001",
                "rule_id": "CAPACITY_FEASIBILITY",
                "message": f"Unsatisfiable layout: Seating capacity achieved ({achieved_seating}) is less than required ({required_capacity}). Termination reason: {termination_reason}.",
                "affected_placement_ids": [p.placement_id for p in best_layout.placements[:1]],
                "measured": {
                    "achieved_seating_capacity": achieved_seating,
                    "termination_reason": termination_reason,
                    "unresolved_spatial_violations": 0,
                },
                "required": {
                    "required_seating_capacity": required_capacity,
                },
                "repair_options": [
                    {
                        "action": "human_escalation",
                        "trade_off": f"Reduce required seating capacity from {required_capacity} to {achieved_seating} seats."
                    }
                ]
            })

        return {
            "room_id": best_layout.room_id,
            "placements": [p.to_dict() for p in best_layout.placements],
            "violations": final_violations,
            "status": "unsatisfiable",
        }
