# Architecture & Design Document — RuleBound

## 1. System Architecture Overview

RuleBound couples a generative floor plan layout layer with an exact, deterministic constraint and pricing engine.

```
[ Generative Brief Parser ]
            │
            ▼ ProposedLayout
┌───────────────────────────────────────┐
│     DETERMINISTIC ARBITRATION LOOP    │
│                                       │
│  src/constraints.py ◄─► arbitration.py│
└───────────────────┬───────────────────┘
                    │
                    ▼ Valid / Unsatisfiable Layout
┌───────────────────────────────────────┐
│      DETERMINISTIC PRICING ENGINE     │
│              src/pricing.py           │
└───────────────────────────────────────┘
```

---

## 2. Arbitration

### 2.1 Boundary Contract & Output Schema Compliance
Control passes irreversibly from the generative layer to deterministic enforcement via explicit, typed data objects:
- **Generative to Deterministic Handoff Object**: `ProposedLayout`
  - `room_id`: String
  - `placements`: Array of `{ placement_id, sku, finish_id, x_mm, y_mm, rotation_deg }`
- **Canonical State Representation & Hash**:
  - State $s$: Canonical tuple of all placement fields (`placement_id`, `sku`, `finish_id`, `x_mm`, `y_mm`, `rotation_deg`).
  - `StateHash(s)`: SHA-256 hash of JSON-serialized sorted placements.
- **Deterministic Output Object (`layout.json`)**:
  - Conforms strictly to `schemas/layout.schema.json` with `additionalProperties: false`.
  - Top-level keys: `room_id`, `placements`, `violations`, `status` (`"valid"` | `"invalid"` | `"unsatisfiable"`).
  - No unsupported top-level fields (`escalation`, `trade_off`). Customer-readable trade-off narratives are embedded inside `violations[].message` and `violations[].repair_options`.

### 2.2 Rule Provenance Convention
- **Spatial Geometry Violations**: Retain their actual official rule ID from `constraints.py` (`RB-GEO-001` through `RB-GEO-008`).
- **Seating Capacity Shortfall**: When zero spatial geometry violations exist but seating capacity $S < \text{room\_spec.capacity}$ (e.g. via `REMOVE_PLACEMENT`), the violation uses `rule_id = "CAPACITY_FEASIBILITY"`. This is a schema-compliant string (`"type": "string"`) that identifies an implementation-owned requirement feasibility check without falsifying official geometry rule IDs.

### 2.3 Model Decision vs. Deterministic Control Transition
- **Model Decision Space**: The model reads plain-English briefs and room geometry to propose candidate SKU placements and initial 2D top-down coordinates.
- **Irreversible Control Pass**: Once `ProposedLayout` enters arbitration, control passes **100% irreversibly** to deterministic python code (`arbitration.py` and `constraints.py`). No LLM, probabilistic model, network API, or timestamp call executes inside arbitration or pricing.

### 2.4 Rule Precedence Policy Statement
The released RuleBound challenge files (`rules.json` / `rules.yaml`) define individual constraints but do **not** specify official precedence or priority rankings among simultaneous violations. 
- Rule precedence in arbitration is an **implementation-level deterministic tie-break policy**.
- It is transparent, fully reproducible, and **never presented as an official LV8 rule**.
- Deterministic candidate selection ranks candidates by:
  $$\text{SortKey} = (\text{OpTypeRank}, \text{rule\_id}, \text{target\_placement\_id}, \text{CanonicalParams})$$

### 2.5 Three Evaluation Levels & Capacity Model
Every repaired candidate layout must be evaluated against three distinct criteria:
1. **Spatial Validity**: `constraints.py` returns 0 violations (`status: "valid"`).
2. **Seating Capacity Feasibility**: Seating count $S = \text{count}(\text{family == 'chair'}) \ge \text{room\_spec.capacity}$. Non-seating equipment (storage, tables, accessories) is not counted as seating.
3. **Final Acceptance**: Both Spatial Validity AND Seating Capacity Feasibility are satisfied.

If a repair operation (`REMOVE_PLACEMENT`) resolves all spatial violations but causes seating count $S < \text{room\_spec.capacity}$, it cannot be accepted as valid and is escalated to trade-off accounting.

### 2.6 Bounded Local Repair Semantics & Termination
- **Architecture B (Bounded Local Repair)**: Arbitration follows a single deterministic repair trajectory. Candidates are generated from the active violation set.
- **Visited State Set ($H$)**: SHA-256 hash set prevents trajectory cycling.
- **Operational Execution Cap**: $K_{\max} = \min(50, \max(10, 10 \times N))$ prevents runaway execution.
- **Termination Reason Categories**:
  - `local_repair_exhausted`: The active repair candidate frontier contains no unvisited state.
  - `operational_limit_reached`: $K_{\max}$ reached while unvisited states remain.
  - Neither condition constitutes a mathematical proof of global layout unsatisfiability across unvisited permutations.

### 2.7 State Machine Diagram

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

### 2.8 Unsatisfiable Layout Escalation & Human View
When no valid layout can be produced:
- **`layout.json`**: Written with `status: "unsatisfiable"`, structured unresolved violations, and trade-off narratives embedded inside `violations[].message`. Conforms 100% to `schemas/layout.schema.json` with `additionalProperties: false`.
- **Human/Customer View**: Embedded trade-off message explains why room constraints cannot be satisfied (e.g. *"No furniture may enter door-swing clearance zone. Placement P09 enters door D1 swing zone. Repositioning P09 causes collision with egress path RB-GEO-002. Removing chairs drops seating below required capacity 10"*).
- **`quote.json`**: Written with `status: "blocked"` and `blocking_reasons` citing the unsatisfiable layout.
