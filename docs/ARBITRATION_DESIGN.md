# RuleBound Deterministic Arbitration Engine Design

## 1. Purpose

The **Arbitration Engine** (`src/arbitration.py`) is the core decision layer in RuleBound. It bridges the gap between the creative generative layer (which proposes floor plan product layouts from customer briefs) and the exact deterministic rule layer (which enforces spatial, geometry, and business constraints).

The arbitration engine ensures that:
- Every proposed layout is either repaired into a **100% valid state** or formally escalated as **unsatisfiable**.
- All repair decisions are **100% deterministic**, reproducible, and mathematically proven to terminate.
- Output JSON objects conform strictly to `schemas/layout.schema.json` and `schemas/violation.schema.json` with `additionalProperties: false`.
- Generative models never execute inside the pricing or repair loops.

---

## 2. Generative-to-Deterministic Seam

### 2.1 The One-Way Handoff

```
[ Generative Layer (Model / Brief Parser) ]
                     │
                     │ ProposedLayout (JSON / Object)
                     ▼  (Irreversible Boundary)
┌─────────────────────────────────────────────────────────┐
│               DETERMINISTIC ARBITRATION LOOP            │
│                                                         │
│   ┌──────────────────┐        ┌─────────────────────┐   │
│   │ constraints.py   │◄───────┤    arbitration.py   │   │
│   │ "What is wrong?" │        │ "What repair next?" │   │
│   └────────┬─────────┘        └──────────▲──────────┘   │
│            │                             │              │
│            └───────► Violations[] ───────┘              │
└────────────────────────────┬────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
   [ Final Valid Layout ]       [ Unsatisfiable Escalation ]
   (status: "valid")            (status: "unsatisfiable")
              │                             │
              ▼                             ▼
   [ src/pricing.py Engine ]    [ Quote Status: "blocked" ]
```

### 2.2 Boundary Invariants
1. **Irreversible Handoff**: Once `ProposedLayout` crosses into `arbitration.py`, no LLM, neural model, probabilistic call, network request, or timestamp query may execute.
2. **Deterministic Inputs**: The arbitration engine receives only the `AssetPack` data (catalog, finishes, rules, room spec) and the candidate layout.
3. **Downstream Pricing Isolation**: `src/pricing.py` is invoked only after arbitration completes. Pricing has zero influence over spatial repair decisions.

---

## 3. Typed Data Contracts & Schema Compatibility

### 3.1 Strict Output Schema Compatibility
`schemas/layout.schema.json` specifies `additionalProperties: false` and allows **only** four top-level properties:
- `room_id` (string)
- `placements` (array of placement objects)
- `violations` (array of violation objects)
- `status` (`enum: ["valid", "invalid", "unsatisfiable"]`)

Therefore:
- **No unsupported top-level fields** (`escalation`, `escalation_reason`, `trade_off`, `arbitration_summary`) may exist in `layout.json`.
- **No custom status values** (`"operational_limit_reached"`) may exist. Status for any unresolvable room must be `"unsatisfiable"`.
- **Customer-readable trade-off explanations** mandated by `RUNNER_CONTRACT.md` are represented inside permitted `violation` fields (`message`, `measured`, `required`, `repair_options`).
- **Violation Rule Provenance**: Every `violation` object in `layout.json` citing a spatial geometry error retains its legitimate released `rule_id` (`RB-GEO-001` through `RB-GEO-008`). Pure seating capacity trade-offs (when zero spatial violations exist) use implementation-owned `rule_id = "CAPACITY_FEASIBILITY"` (a schema-compliant string that avoids falsifying official spatial geometry rule provenance).

### 3.2 Internal Data Structure Dataclasses

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Literal


@dataclass(frozen=True)
class PlacementProposal:
    placement_id: str
    sku: str
    finish_id: str
    x_mm: int
    y_mm: int
    rotation_deg: int


@dataclass(frozen=True)
class ProposedLayout:
    room_id: str
    placements: Tuple[PlacementProposal, ...]

    def canonical_state_hash(self) -> str:
        """
        Returns SHA-256 hash of complete canonical layout state.
        Includes placement identity, SKU, finish, coordinates, and rotation.
        """
        import hashlib, json
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


@dataclass(frozen=True)
class Violation:
    violation_id: str
    rule_id: str
    message: str
    affected_placement_ids: Tuple[str, ...]
    measured: Dict[str, Any] = field(default_factory=dict)
    required: Dict[str, Any] = field(default_factory=dict)
    repair_options: Tuple[Dict[str, Any], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RepairCandidate:
    op_type: Literal["NUDGE", "ROTATE", "SUBSTITUTE_SKU", "REMOVE_PLACEMENT"]
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
    status: Literal["valid", "invalid", "unsatisfiable"]
    final_placements: Tuple[PlacementProposal, ...]
    violations: Tuple[Violation, ...]
    history: Tuple[ArbitrationDecision, ...]
```

---

## 4. Seating Requirement Semantics & Acceptance Definition

### 4.1 Seating Capacity Semantics
Based on the released room briefs and schemas:
- `ROOM-01`: 12-person product-design studio (`capacity: 12`)
- `ROOM-02`: 16-person client workshop (`capacity: 16`)
- `ROOM-03`: 10-person hybrid team room (`capacity: 10`)
- `ROOM-04`: 14-person quiet focus library (`capacity: 14`)
- `ROOM-05`: 18-person project hub (`capacity: 18`)

The `room_spec.capacity` integer represents the mandatory required people/seating capacity of the room, **not** raw placement count.

### 4.2 Deterministic Seating Mechanism
In `catalog.json`, items with `family == "chair"` represent user task seating. Items with `family == "desk"`, `"storage"`, `"collaboration"`, or `"accessory"` are equipment/tables.

The deterministic seating calculation derived from the catalog:
- **Target Capacity**: $C = \text{room\_spec.capacity}$.
- **Achieved Seating Count**: $S = \text{count}\big(\text{placements where catalog\_family}(p.\text{sku}) == \text{"chair"}\big)$.
- **Mandatory Seating Constraint**: $S \ge C$.

No unstated rule (such as "one desk equals one seat") is invented.

### 4.3 Precise Candidate Acceptance Definition
A repaired layout candidate is accepted as **valid** if and only if:
1. **Spatial Validity**: All applicable spatial constraints in `src/constraints.py` return 0 violations (`status == "valid"`).
2. **Mandatory Requirement Feasibility**: All explicitly modeled mandatory brief requirements (e.g. seating count $S \ge \text{room\_spec.capacity}$) are satisfied.

Unmodeled qualitative brief requests (such as "visually open" or "durable finishes") remain part of human/generative scope and are not claimed as machine-validated.

### 4.4 Rules for `REMOVE_PLACEMENT`
- `REMOVE_PLACEMENT` is evaluated against both Spatial Validity and Seating Feasibility.
- If removing a chair placement causes $S < \text{room\_spec.capacity}$, the layout cannot be accepted as valid.
- If resolving spatial clearance requires dropping seating below target capacity, the layout is escalated as `"unsatisfiable"` with an explicit trade-off narrative inside `violations`.

---

## 5. Bounded Local Repair Semantics & Constraint Separation

### 5.1 Architecture B: Bounded Local Repair
Arbitration follows **Architecture B (Bounded Local Repair)**:
1. **Single Trajectory**: Arbitration follows a single deterministic repair trajectory per proposed layout.
2. **Violation-Derived Candidates**: Candidates are generated strictly from the active violation set at each step.
3. **Visited State Set**: A SHA-256 visited-state hash set $H$ prevents loop cycling and duplicate state evaluation.
4. **Operational Bound**: $K_{\max} = \min(50, \max(10, 10 \times N))$ serves as an operational execution cap.
5. **No Global UNSAT Claim**: Exhausting candidates on the local repair trajectory signifies local repair exhaustion—it does **not** constitute a mathematical proof that no valid layout exists globally across all possible state space permutations.

### 5.2 Separation of Concerns
- **`constraints.py` (Oracle)**:
  - Answers: *"What spatial rules are currently broken in this layout state?"*
  - Stateless function: `validate_layout(layout, room_spec) -> Dict`.
  - Does NOT decide how to fix violations or evaluate seating capacity.

- **`arbitration.py` (Decision Engine)**:
  - Answers: *"Given these violations and capacity rules, what deterministic repair should we try next on the current repair trajectory?"*
  - Generates repair candidates, ranks them deterministically, applies the top candidate, and re-invokes `constraints.py` and capacity checks.

---

## 6. Deterministic Candidate Ranking & Rule Precedence

### 6.1 Policy Statement on Rule Precedence
The released RuleBound challenge files (`rules.json` / `rules.yaml`) define individual constraints but do **not** specify official precedence or priority rankings among simultaneous violations.

Therefore:
- Rule precedence in arbitration is an **implementation-level deterministic tie-break policy**.
- It is transparent, fully reproducible, and **never presented as an official LV8 rule**.

### 6.1 Deterministic Lexicographic Objective Model

Arbitration uses a deterministic **Lexicographic Objective Model** for candidate evaluation, state transitions, and candidate ranking.

Mandatory requirement feasibility is the primary lexicographic objective. Spatial optimization occurs only among capacity-feasible candidates.

The candidate objective is defined by the tuple:
```python
candidate_objective = (
    capacity_shortfall,
    spatial_violation_count,
    distinct_placements_touched,
    total_displacement,
    operation_rank,
    target_placement_id,
    canonical_parameters
)
```

where:
- `capacity_shortfall = max(0, required_capacity - achieved_seating_capacity)`
- `spatial_violation_count = len(spatial_violations)` (violations returned by `constraints.py`)
- `distinct_placements_touched`: number of placements modified relative to initial proposal
- `total_displacement`: total displacement in mm of modified placements relative to initial proposal
- `operation_rank`: integer rank of repair operation (MOVE_WORKSTATION_POD=0, NUDGE=1, ROTATE=2, SUBSTITUTE_SKU=3, REMOVE_PLACEMENT=4)
- `target_placement_id`: placement ID string (e.g. `"P001"`)
- `canonical_parameters`: parameter string (e.g. `"POD_P001_P002_DX_100_DY_100"`)

### 6.2 Rationale for Lexicographic Ordering vs. Weighted Sums
- **Mandatory Requirements vs. Optimization**: Seating capacity is a mandatory brief requirement (`room_spec.capacity`). Spatial violations represent layout defects.
- **No Arbitrary Trade-offs**: Arbitrary weighted sums (such as `score = 10 * spatial + 5 * capacity`) risk allowing a large capacity violation (e.g. deleting a required chair) to trade off against several spatial improvements.
- **No Invented Weights**: Lexicographic ordering establishes a strict requirement hierarchy (`capacity_shortfall` $\to$ `spatial_violation_count` $\to$ tie-breakers) without inventing subjective numerical weights.
- **Implementation Acceptance Policy**: This is an implementation acceptance policy derived from the distinction between mandatory requirements and spatial optimization (not an official LV8 priority rule).

### 6.2.1 Atomic `MOVE_WORKSTATION_POD` Operator
Single-placement repairs can become trapped when a workstation is governed by coupled desk/chair geometry. `MOVE_WORKSTATION_POD` provides a bounded atomic repair that preserves the mandatory workstation relationship while remaining deterministic and fully revalidated.

- **Operator Details**:
  - Translates a paired desk and task-chair together by identical $(\Delta x, \Delta y)$ on the $100\text{ mm}$ grid.
  - Preserves exact relative geometry, rotation, SKUs, finishes, and seating capacity.
  - Formatted canonically as `POD_P001_P002_DX_+100_DY_+0`.
  - Assigned implementation-level operation rank `0` to prioritize atomic pod moves before single-placement breakdown.
  - Note: `MOVE_WORKSTATION_POD` is an implementation-level arbitration operator, not an official LV8 rule.

### 6.2.2 Targeted Exact-Distance RB-GEO-004 Rear-Clearance Repair
For `RB-GEO-004` (occupied desk 900 mm rear clearance), arbitration computes the exact geometric shortfall to 900 mm and generates deterministic exact-deficit and grid-aligned displacements for the desk, paired pod (`MOVE_WORKSTATION_POD`), and rear obstacle.

- **Shortfall Calculation**: $\Delta_{\text{clearance}} = 900\text{ mm} - \text{measured\_clearance}$.
- **Candidate Displacements**: Evaluates exact shortfall $\Delta_{\text{clearance}}$ and integer grid-aligned ceil $\lceil\Delta_{\text{clearance}} / 100\rceil \times 100\text{ mm}$ along the desk orientation axis.
- **Obstacle & Pod Shifts**: Generates targeted nudges for conflicting rear placements and paired pod shifts to relieve rear clearance bottlenecks without de-synchronizing desk-chair relationships.

### 6.2.3 Hard Polygon Boundary Safety Invariant
`is_layout_inside_boundary(cand_layout, room_spec)` guarantees that invalid geometry is never an accepted repair state:
- Any candidate repair shifting a furniture placement footprint outside the authoritative room polygon is strictly rejected and marked tabu.
- Bounding box checks `is_box_inside_polygon(bbox, boundary_coords)` ensure 100% boundary containment for all rotated furniture envelopes.

### 6.3 Strict Improvement Gate
A candidate operation is eligible ONLY if:
$$\text{candidate\_objective} < \text{current\_objective}$$
using standard Python lexicographic tuple comparison.

Candidates that produce $\text{candidate\_objective} \ge \text{current\_objective}$ fail strict improvement and are recorded in the session-local tabu memory set (`tabu_candidates`), preventing non-improving repetitions.

---

## 7. Rigorous Termination Proof & Bounded State Space

### 7.1 Canonical Repair State Space ($S$)
Let a complete repair state $s$ be defined as the canonical tuple of all fields describing a candidate layout:
$$s = \Big( \text{room\_id},\; \big\{ (\text{placement\_id}_i, \text{sku}_i, \text{finish\_id}_i, x_i, y_i, \theta_i) \big\}_{i=1}^M \Big)$$
where $M \le N$ ($N$ being the initial placement count).

Let $S$ be the set of all canonical states reachable by applying any finite sequence of permitted repair operators (`NUDGE`, `ROTATE`, `SUBSTITUTE_SKU`, `REMOVE_PLACEMENT`) to the initial proposed layout.

### 7.2 Proof of Finiteness of $S$
The state space $S$ is strictly finite because:
1. **Bounded Coordinates**: $x_i \in [0, R_w]$ and $y_i \in [0, R_h]$, bounded by room boundary.
2. **Finite Candidate Grid**: $x_i, y_i$ values generated by repair operators belong to a discrete integer grid.
3. **Finite Rotations**: $\theta_i \in \{0, 90, 180, 270\}$.
4. **Finite Catalog**: SKUs belong to the fixed 120-SKU catalog.
5. **Finite Placement Subsets**: $M \le N$, giving at most $2^N$ placement subsets.
6. **Bounded Initial Placements**: Initial placement count $N$ is finite.

Since $S$ is the product of finite sets, $|S| < \infty$.

### 7.3 Strict Decreasing Metric Proof on Trajectory
Let $H_k$ be the set of canonical state hashes evaluated up to step $k$ ($|H_k| = k$).
Let $U_k = |S \setminus H_k|$ be the count of unvisited states in $S$.

When evaluating a new candidate state $s_{k+1} \notin H_k$:
$$H_{k+1} = H_k \cup \{s_{k+1}\} \implies U_{k+1} = U_k - 1$$

$U_k$ is a non-negative integer measure that strictly decreases by at least 1 on every step ($U_{k+1} \le U_k - 1$). Since $|S| < \infty$, $U_k$ must reach 0 in at most $|S|$ steps. Hence, loop cycling is impossible and trajectory termination is mathematically proven.

### 7.4 Output Termination Reason Categories

Arbitration distinguishes two distinct termination conditions stored inside `violations[].measured.termination_reason`:

1. **`local_repair_exhausted`**:
   - The current deterministic repair candidate frontier contains no unvisited candidate.
   - Represents local repair trajectory exhaustion (not global mathematical UNSAT).

2. **`operational_limit_reached`**:
   - The operational execution cap $K_{\max} = \min(50, \max(10, 10 \times N))$ is reached while unvisited candidates remain.
   - Represents an operational safety boundary halt.

Both conditions produce a schema-valid `layout.json` output with `status: "unsatisfiable"`.

---

## 8. Revalidation Loop State Machine

```mermaid
stateDiagram-v2
    [*] --> ProposedLayout: Receive Handoff
    ProposedLayout --> FullRevalidation: Run constraints.py & check seating capacity
    
    state FullRevalidation {
        [*] --> EvaluateState
        EvaluateState --> ValidAndFeasible: spatial_violations == 0 AND seats >= capacity
        EvaluateState --> ViolationsExist: spatial_violations > 0 OR seats < capacity
    }

    ValidAndFeasible --> AcceptLayout: status = "valid"
    AcceptLayout --> [*]

    state ViolationsExist {
        [*] --> CheckOperationalCap
        CheckOperationalCap --> OperationalLimitReached: step >= K_max
        CheckOperationalCap --> GenerateCandidates: step < K_max
        
        GenerateCandidates --> RankCandidates: Apply SortKey
        RankCandidates --> FilterVisited: Filter hashes in H
        
        FilterVisited --> CandidateFound: Unvisited state s exists
        FilterVisited --> SpaceExhausted: All local candidates in H
        
        CandidateFound --> ApplyRepair: Execute top candidate
        ApplyRepair --> AddToH: Add hash(s) to H
        AddToH --> FullRevalidation
    }

    SpaceExhausted --> EscalateUnsat: status = "unsatisfiable" (local_repair_exhausted)
    OperationalLimitReached --> EscalateOpCap: status = "unsatisfiable" (operational_limit_reached)

    EscalateUnsat --> [*]
    EscalateOpCap --> [*]
```

---

## 9. Unsatisfiable Escalation & Schema Compliance

When a layout cannot be resolved into a valid, feasible state:

1. **`layout.json` Output**:
   - `status`: `"unsatisfiable"`
   - `placements`: Best candidate layout state achieved during repair search.
   - `violations`: Array of structured violation objects containing unresolved spatial violations (with legitimate `rule_id`s like `RB-GEO-002`, `RB-GEO-003`) or pure capacity trade-offs (with `rule_id = "CAPACITY_FEASIBILITY"`).

2. **`quote.json` Output**:
   - `status`: `"blocked"`
   - `blocking_reasons`: `["Layout is unsatisfiable: local repair exhausted with unresolved spatial violations."]`

---

## 10. Determinism Guarantees

1. **Zero Randomness**: No `random`, `uuid`, or time-based identifiers.
2. **Canonical JSON Ordering**: Keys sorted alphabetically, 2-space indentation, UTF-8.
3. **Sorted Iteration**: Placements, violations, and repair candidates are sorted prior to evaluation.
4. **Environment Independent**: Runs byte-identically on Linux, macOS, and Windows.

---

## 11. Revised Arbitration Walkthrough Examples

### Example 1: Multi-Stage Repair & Cascading Revalidation
- **Initial State**: Desk `P01` placed at `x=600, y=100` in `ROOM-01` (inside door swing of `D1`).
- **Pass 1 (`constraints.py`)**: Returns `RB-GEO-003` (Door D1 swing violation for `P01`).
- **Arbitration Action**: Nudge `P01` (`dy = +500`). New pos: `x=600, y=600`.
- **Pass 2 (Full Revalidation)**: Fixes `RB-GEO-003`, but `constraints.py` returns a new `RB-GEO-005` (Wall clearance violation for `P01` at `x=600, y=600`).
- **Arbitration Action**: Nudge `P01` (`dx = +1400, dy = +2400`). New pos: `x=2000, y=3000`.
- **Pass 3 (Full Revalidation)**: Returns 0 spatial violations; seating feasibility met ($S=12 \ge 12$).
- **Final Result**: ACCEPTED (`status = "valid"`, 0 violations).

### Example 2: Removal Rejected by Capacity Requirement
- **Initial State**: `ROOM-01` spec requires `capacity: 12`. Layout contains 12 chairs and 12 desks, but chairs `P11` and `P12` overlap (`RB-GEO-006`).
- **Arbitration Action**: Repositioning fails due to tight room dimensions. Arbitration evaluates `REMOVE_PLACEMENT` for `P12` (chair).
- **Pass (Full Revalidation)**:
  1. Spatial check: `constraints.py` returns 0 spatial violations.
  2. Seating check: `S = 11 < capacity (12)`.
  3. Acceptance check: FAILED. Candidate rejected due to capacity violation.
- **Final Result**: `REMOVE_PLACEMENT` discarded; arbitration continues searching or escalates trade-off.

### Example 3: Local Repair Exhaustion (UNSAT Status)
- **Initial State**: `ROOM-03` with 18 desks placed in a tight $4200 \times 4800$ footprint.
- **Arbitration Search**: Evaluates local `NUDGE`, `ROTATE`, `SUBSTITUTE_SKU`, and `REMOVE_PLACEMENT` candidates until no unvisited local candidate state remains.
- **Final Result**: Local repair frontier exhausted without finding a valid configuration meeting seating capacity.
- **Output**: `status = "unsatisfiable"`, schema-valid `layout.json` with `"termination_reason": "local_repair_exhausted"`.

### Example 4: Operational Limit Reached (Operational Escalation)
- **Initial State**: Dense layout where $K_{\max} = 50$ iterations are reached while unvisited local candidates remain.
- **Final Result**: Search halted by safety bound $K_{\max}$.
- **Output**: `status = "unsatisfiable"`, schema-valid `layout.json` recording `"termination_reason": "operational_limit_reached"` inside `violations[].measured`.

---

## 12. Schema-Valid Unsatisfiable `layout.json` Example

The following example demonstrates a 100% internally consistent, schema-valid `layout.json` for an unsatisfiable room (`ROOM-03`, `capacity: 10`). It contains **8 actual chair placements** (`P01` through `P08`) matching `achieved_seating_capacity: 8`, cites **legitimate released rule IDs** (`RB-GEO-003` and `RB-GEO-002`), and uses `"termination_reason": "local_repair_exhausted"`:

```json
{
  "room_id": "ROOM-03",
  "placements": [
    { "finish_id": "F02", "placement_id": "P01", "rotation_deg": 0, "sku": "NW-CHA-001", "x_mm": 500, "y_mm": 5000 },
    { "finish_id": "F02", "placement_id": "P02", "rotation_deg": 0, "sku": "NW-CHA-001", "x_mm": 1200, "y_mm": 5000 },
    { "finish_id": "F02", "placement_id": "P03", "rotation_deg": 0, "sku": "NW-CHA-001", "x_mm": 1900, "y_mm": 5000 },
    { "finish_id": "F02", "placement_id": "P04", "rotation_deg": 0, "sku": "NW-CHA-001", "x_mm": 2600, "y_mm": 5000 },
    { "finish_id": "F02", "placement_id": "P05", "rotation_deg": 0, "sku": "NW-CHA-001", "x_mm": 500, "y_mm": 4000 },
    { "finish_id": "F02", "placement_id": "P06", "rotation_deg": 0, "sku": "NW-CHA-001", "x_mm": 1200, "y_mm": 4000 },
    { "finish_id": "F02", "placement_id": "P07", "rotation_deg": 0, "sku": "NW-CHA-001", "x_mm": 1900, "y_mm": 4000 },
    { "finish_id": "F02", "placement_id": "P08", "rotation_deg": 0, "sku": "NW-CHA-001", "x_mm": 2600, "y_mm": 4000 },
    { "finish_id": "F01", "placement_id": "P09", "rotation_deg": 0, "sku": "NW-DES-001", "x_mm": 2600, "y_mm": 100 },
    { "finish_id": "F01", "placement_id": "P10", "rotation_deg": 0, "sku": "NW-STO-001", "x_mm": 500, "y_mm": 5300 }
  ],
  "status": "unsatisfiable",
  "violations": [
    {
      "affected_placement_ids": [
        "P09"
      ],
      "measured": {
        "achieved_seating_capacity": 8,
        "door_id": "D1",
        "intersects_swing_zone": true,
        "termination_reason": "local_repair_exhausted"
      },
      "message": "No furniture may enter the door-swing clearance zone. Placement P09 enters door D1 swing zone.",
      "repair_options": [
        {
          "action": "human_escalation",
          "trade_off": "Repositioning P09 causes collision with egress path RB-GEO-002. Removing chairs to make space drops seating below required capacity 10."
        }
      ],
      "required": {
        "clearance_mm": 850,
        "required_seating_capacity": 10
      },
      "rule_id": "RB-GEO-003",
      "violation_id": "V001"
    },
    {
      "affected_placement_ids": [
        "P10"
      ],
      "measured": {
        "achieved_seating_capacity": 8,
        "egress_clearance_mm": 300,
        "termination_reason": "local_repair_exhausted"
      },
      "message": "The marked egress path requires 1100 mm clear width. Placement P10 intersects egress path from door D1.",
      "repair_options": [
        {
          "action": "human_escalation",
          "trade_off": "Moving P10 violates wall clearance RB-GEO-005."
        }
      ],
      "required": {
        "min_egress_width_mm": 1100,
        "required_seating_capacity": 10
      },
      "rule_id": "RB-GEO-002",
      "violation_id": "V002"
    }
  ]
}
```
