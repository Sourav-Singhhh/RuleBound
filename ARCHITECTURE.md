# Architecture & Design Document — RuleBound

## 1. System Architecture Overview

RuleBound couples a generative floor plan layout layer with an exact, deterministic constraint, arbitration, and pricing engine.

```
[ Generative Brief Parser ]
            │
            ▼ ProposedLayout
┌───────────────────────────────────────┐
│     DETERMINISTIC ARBITRATION LOOP    │
│                                       │
│  src/constraints.py ◄─► arbitration.py│
│  (Strict Lexicographic Gate & Tabu)   │
└───────────────────┬───────────────────┘
                    │
                    ▼ Valid / Unsatisfiable Layout
┌───────────────────────────────────────┐
│      DETERMINISTIC PRICING ENGINE     │
│              src/pricing.py           │
│  (Integer-Exact INR & Basis Points)   │
└───────────────────────────────────────┘
```

---

## 2. Arbitration & Deterministic Core

### 2.1 Boundary Contract & Output Schema Compliance
Control passes irreversibly from the generative layer to deterministic enforcement via explicit, typed data objects:
- **Generative to Deterministic Handoff Object**: `ProposedLayout`
  - `room_id`: String
  - `placements`: Array of `{ placement_id, sku, finish_id, x_mm, y_mm, rotation_deg }`
- **Canonical State Representation & Verification**:
  - State $s$: Canonical tuple of all placement fields (`placement_id`, `sku`, `finish_id`, `x_mm`, `y_mm`, `rotation_deg`).
  - `canonical_state_hash(layout)`: Pure canonical serialization helper computing SHA-256 over deterministically ordered placement records.
- **Deterministic Output Object (`layout.json`)**:
  - Conforms strictly to `schemas/layout.schema.json` with `additionalProperties: false`.
  - Top-level keys: `room_id`, `placements`, `violations`, `status` (`"valid"` | `"invalid"` | `"unsatisfiable"`).
  - No unsupported top-level fields (`escalation`, `trade_off`). Customer-readable trade-off narratives are embedded inside `violations[].message` and `violations[].repair_options`.

### 2.2 Rule Provenance Convention
- **Spatial Geometry Violations**: Retain their actual official rule ID from `constraints.py` (`RB-GEO-001` through `RB-GEO-008`).
- **Capacity & Workstation Feasibility**: When zero spatial geometry violations exist but achieved seating or workstation capacity falls below requirements, the violation uses `rule_id = "CAPACITY_FEASIBILITY"`. This is a schema-compliant string (`"type": "string"`) that identifies an implementation-owned requirement feasibility check without falsifying official geometry rule IDs.

### 2.3 Model Decision vs. Deterministic Control Transition
- **Model Decision Space**: The model reads plain-English briefs and room geometry to propose candidate SKU placements and initial 2D coordinates on the $100\text{ mm}$ grid.
- **Irreversible Control Pass**: Once `ProposedLayout` enters arbitration, control passes **100% irreversibly** to deterministic python code (`arbitration.py` and `constraints.py`). No LLM, probabilistic model, network API, or timestamp call executes inside arbitration or pricing.

### 2.4 Lexicographic Objective Model & Acceptance Policy
Mandatory requirement feasibility is the primary lexicographic objective. Spatial optimization occurs strictly among capacity-feasible candidates.

Arbitration evaluates candidate moves using a deterministic **Lexicographic Objective Model**:
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
- `capacity_shortfall = max(0, required_capacity - achieved_seating_capacity) + max(0, required_workstations - achieved_workstation_capacity)`
- `spatial_violation_count = len(spatial_violations)` (violations returned by `constraints.py`)
- `distinct_placements_touched`: number of placements modified relative to initial proposal
- `total_displacement`: total integer displacement in mm computed via `math.isqrt(dx*dx + dy*dy)`
- `operation_rank`: integer rank of repair operation:
  - `ROW_GROUP_SHIFT`: -1 (highest priority composite pod shift)
  - `MOVE_WORKSTATION_POD`: 0 (atomic paired desk+chair translation)
  - `NUDGE`: 1 (single placement translation)
  - `ROTATE`: 2 (90-degree rotation)
  - `SUBSTITUTE_SKU`: 3 (catalog SKU substitution)
  - `REMOVE_PLACEMENT`: 4 (removal of non-mandatory furniture)
- `target_placement_id`: placement ID string (e.g. `"P001"`)
- `canonical_parameters`: deterministic parameter string (e.g. `"POD_P001_P002_DX_-200_DY_0"`)

### 2.5 Workstation Preservation & Semantic Preconditions
To prevent **furniture evaporation** (where an algorithm deletes required desks to artificially satisfy spatial clearance rules):
1. **Hard Semantic Precondition on Candidate Generation**:
   - For `family == 'chair'`: `REMOVE_PLACEMENT` is strictly barred if `active_chairs <= required_capacity`.
   - For `family == 'desk'`: `REMOVE_PLACEMENT` is strictly barred if `active_desks <= required_workstations`.
2. **Hard Candidate Acceptance Gate**:
   - Even if a candidate is generated, arbitration unconditionally rejects any candidate whose execution would leave `achieved_seating < required_capacity` or `achieved_workstations < required_workstations`.
3. **Honest Unsatisfiable Escalation**:
   - If a room cannot physically accommodate all required workstations and chairs without violating spatial rules (e.g., tight egress or door swing clearances), the engine terminates and escalates with `status: "unsatisfiable"` and customer-readable trade-offs. It never silently deletes required furniture.

### 2.6 Atomic Composite Operators
Single-placement repairs frequently become trapped when a workstation is governed by coupled desk/chair clearance geometry:
- **`MOVE_WORKSTATION_POD`**: Translates paired desk and chair together by $(\Delta x, \Delta y)$ on the $100\text{ mm}$ grid, resolving aisle clearances without geometric de-synchronization.
- **`ROW_GROUP_SHIFT`**: Translates an entire contiguous row of desks and chairs simultaneously along row or corridor axes, eliminating multi-unit walkway bottlenecks in a single atomic step.

### 2.7 Termination & Cycle-Prevention Guarantees
Arbitration guarantees deterministic termination and strictly prohibits infinite looping:
1. **Strict Monotonic Lexicographic Improvement Gate**:
   - A candidate state $s'$ is accepted if and only if `candidate_objective < current_objective`.
   - Because the lexicographic objective strictly decreases at every accepted step, the state trajectory can never revisit any previously visited state or cycle.
2. **Session-Local Action Tabu Memory**:
   - Failed candidate operations `(target_placement_id, op_type, canonical_param_str)` are recorded in `tabu_candidates` and never re-evaluated within the session.
3. **Finite Operational Cap ($K_{\max}$)**:
   - Total steps are bounded by $K_{\max} = \min(50, \max(10, 10 \times N))$ where $N$ is the number of placements.
4. **Termination Reason Categories**:
   - `local_repair_exhausted`: No candidate repair produces a strict lexicographic improvement.
   - `operational_limit_reached`: Execution reaches $K_{\max}$.

### 2.8 State Machine Diagram

```mermaid
stateDiagram-v2
    [*] --> ProposedLayout: Receive Initial Proposal
    ProposedLayout --> EvaluateState: Initial Full Revalidation
    
    state EvaluateState {
        [*] --> CheckFeasibility
        CheckFeasibility --> ValidAndFeasible: spatial_viols == 0 AND capacity_shortfall == 0
        CheckFeasibility --> NeedsRepair: spatial_viols > 0 OR capacity_shortfall > 0
    }

    ValidAndFeasible --> AcceptLayout: status = "valid"
    AcceptLayout --> [*]

    state NeedsRepair {
        [*] --> CheckStepLimit
        CheckStepLimit --> OperationalCapExhausted: step >= K_max
        CheckStepLimit --> GenerateCandidates: step < K_max
        
        GenerateCandidates --> FilterSemanticPreconditions: Bar removal of mandatory desks/chairs
        FilterSemanticPreconditions --> EvaluateCandidates: Apply candidate & revalidate
        
        EvaluateCandidates --> StrictImprovementGate: candidate_obj < current_obj?
        StrictImprovementGate --> RecordTabu: False (Record in tabu_candidates)
        StrictImprovementGate --> CollectImproving: True (Add to candidate pool)
        
        CollectImproving --> SelectBest: Sort by Lexicographic Objective Tuple
        SelectBest --> ApplyBestRepair: Take lowest tuple
        ApplyBestRepair --> EvaluateState: step += 1
        
        RecordTabu --> FrontierCheck
        FrontierCheck --> NoImprovingLeft: No candidate strictly improved objective
    }

    NoImprovingLeft --> EscalateUnsat: status = "unsatisfiable" (local_repair_exhausted)
    OperationalCapExhausted --> EscalateOpCap: status = "unsatisfiable" (operational_limit_reached)

    EscalateUnsat --> [*]
    EscalateOpCap --> [*]
```

---

## 3. Deterministic Pricing Engine

### 3.1 Integer-Exact INR Arithmetic
`src/pricing.py` implements pure integer arithmetic without floating-point drift:
- All monetary outputs are integer INR.
- Percentage adjustments (discounts, uplifts, freight) use integer basis points ($1\text{ bps} = 0.01\%$).
- Division uses deterministic half-up rounding (`round_half_up(n, d)`: halves round toward $+\infty$).

### 3.2 Pricing Specification Traceability
Every pricing calculation line and summary element includes an explicit audit trace:
- `CATALOG`: List price lookups from `data/catalog.json`.
- `RB-PRC-009`: Finish uplift based on `uplift_bps` from `data/finishes.json`.
- `RB-PRC-010`: Tiered quantity discount (1–4: 0 bps, 5–9: 300 bps, 10–19: 700 bps, 20+: 1000 bps).
- `RB-PRC-011`: Tiered assembly labour rate per item based on room capacity (1–8: ₹1,500, 9–16: ₹1,200, 17+: ₹1,000).
- `RB-PRC-012`: Tiered freight band based on radial distance from factory.
- `RB-PRC-013`: Absent pricing or finish incompatibility blocking rule. When an SKU is unpriced or a finish is incompatible, quote saving is blocked with explicit rule identifier `RB-PRC-013` recorded in `blocking_reasons`.
