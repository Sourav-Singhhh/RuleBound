# RuleBound

A deterministic room-layout, constraint-validation, arbitration, and pricing engine for the RuleBound Sealed Build Challenge.

## Final Demonstration Video

- **Walkthrough Video (approx. 6–7 minutes)**: [Watch the Final Demonstration Video](https://drive.google.com/drive/folders/1D_fuR9CQA3gmWXxntB5tKH4uqOZlc8x4?usp=sharing)
  *The walkthrough video provides a complete end-to-end demonstration covering:*
  - **Core RuleBound Pipeline**: Layout generation, heuristic placement, and pipeline CLI execution
  - **Constraint Validation**: Authoritative geometric validation across all 8 spatial rules
  - **Unsatisfiable-Case Handling**: Universal furniture preservation and failure-safe escalation
  - **Byte-Identical Determinism**: Multi-run and multi-seed byte-identical output verification
  - **Exact Integer Pricing**: Integer INR arithmetic, basis-point discounts, labor, freight, and rule provenance
  - **DXF Floorplan Export**: Standalone AutoCAD R12 ASCII DXF generation with semantic layers
  - **Azure Cloud Deployment**: Azure App Service Linux hosting with zero external dependencies
  - **Microsoft Entra ID Authentication**: Live Easy Auth v2 gateway verification (unauthenticated challenge & authenticated execution)

## Overview

RuleBound integrates an initial proposal generator with an exact, deterministic spatial constraint validator, a bounded arbitration search engine, and a precise pricing engine. Given plain-English briefs and 2D room specifications, the system extracts furniture requirements, constructs valid starting proposals, and deterministically repairs constraint violations using bounded local search with strict lexicographic objective gating and tabu memory. Valid layout proposals are priced into exact integer-INR quotes with full rule execution traces, while unresolvable layouts honestly escalate into schema-valid `unsatisfiable` layout and `blocked` quote outputs. All spatial validation, arbitration, and pricing operations run 100% deterministically without external LLM calls or network dependencies.

## Quick Start

### 1. Run Pipeline
Execute the full layout generation, arbitration, and pricing pipeline across all room specifications:

```bash
python starter/python/runner.py --input data --output OUTPUT
```

### 2. Validate Output Schemas
Verify that all generated layout and quote JSON files conform strictly to official JSON schemas:

```bash
python tools/validate_output.py OUTPUT
```

### 3. Check Determinism
Verify that pipeline execution is byte-identical across multiple runs:

```bash
python tools/check_determinism.py --command "python starter/python/runner.py --input {input} --output {output}" --input data --work-dir det_work
```

### 4. Interactive Pipeline Demo
Run the step-by-step end-to-end trace script demonstrating constraint detection, atomic pod arbitration, workstation preservation, and exact pricing:

```bash
python demo_trace.py
```

## Architecture

```
Brief + Room Spec
        ↓
    Generator
        ↓
 ProposedLayout
        ↓
Constraint Engine
        ↓
Bounded Arbitration (Strict Lexicographic Gate & Tabu Memory)
        ↓
 Final Validation
        ↓
Deterministic Pricing (Integer-Exact INR & Basis Points)
        ↓
layout.json + quote.json
```

- **Generator**: Parses customer briefs and room specifications to extract quantitative requirements and finish preferences, placing catalog items on a 100mm grid inside room boundaries while using deterministic spacing, door, and egress heuristics to construct sensible starting proposals.
- **ProposedLayout**: Typed internal handoff object carrying the generator's deterministic placement proposal into arbitration.
- **Constraint Engine**: Authoritatively evaluates layouts against official spatial rules (`RB-GEO-001` through `RB-GEO-008`), returning exact violation payloads.
- **Bounded Arbitration**: Implements local candidate repair search (`ROW_GROUP_SHIFT`, `MOVE_WORKSTATION_POD`, `NUDGE`, `ROTATE`, `SUBSTITUTE_SKU`, `REMOVE_PLACEMENT`) under strict lexicographic acceptance gates, hard workstation preservation preconditions, and tabu memory.
- **Final Validation**: Confirms spatial validity (`status: "valid"`) and requirement feasibility before passing to pricing.
- **Deterministic Pricing**: Computes exact integer INR line items, finish uplifts, quantity discounts, labour, and freight, writing output quotes.

## Arbitration & Semantic Highlights

- **Ground-Truth Brief Semantics**: Parses precise furniture semantics from plain-English briefs without blind fallback:
  - `ROOM-01`: "paired desks" + 12-person capacity $\to$ 6 paired 1600mm desks (`NW-DES-003`) with 12 chairs, 2 storage, and 1 compact collaboration table.
  - `ROOM-02`: flexible client workshop $\to$ 0 desks, 2 large collaboration tables (`NW-COL-008`/`003`) with 16 task chairs, and 4 accessible storage units.
  - `ROOM-03`: 8 fixed work positions $\to$ 8 desks, 10 chairs, 1 four-person touchdown table, and 2 acoustic accessories.
  - `ROOM-04`: 14 individual desks $\to$ 14 desks, 14 chairs, and 2 distributed storage units.
  - `ROOM-05`: 12 desk positions $\to$ 12 desks, 18 chairs, 2 storage units, 2 collaboration tables, and 2 writable accessories.
- **Universal Furniture Preservation Preconditions**: Hard semantic invariants prevent `REMOVE_PLACEMENT` from deleting ANY required furniture family (desks, chairs, storage, collaboration tables, accessories) below brief requirements.
- **Clean Geometric Placement**: The generator strictly places furniture within room polygons and valid non-overlapping bounds without dumping artificial overlapping boxes to satisfy numeric counters.
- **Lexicographic Objective**: Evaluates candidates on `(capacity_shortfall, spatial_violation_count, distinct_placements_touched, total_displacement, operation_rank, target_placement_id, canonical_parameters)`.
- **Strict Improvement Gate**: A candidate is accepted if and only if its lexicographic objective strictly improves upon the current objective. This strictly prevents cyclic state loops under monotonic objective descent.
- **Pure Integer Displacement**: Uses integer-square-root (`math.isqrt`) for displacement tie-breaking, ensuring 100% platform-independent integer calculations.
- **Atomic Composite Operators**:
  - `MOVE_WORKSTATION_POD`: Translates paired desk and chair together by $(\Delta x, \Delta y)$, preserving coupled geometry.
  - `ROW_GROUP_SHIFT`: Translates an entire contiguous row of desks and chairs simultaneously, resolving aisle clearances.
- **Tabu Action Memory**: Session-local tabu memory prevents retrying failed repair moves.
- **Honest Unsatisfiable Escalation**: When no compliant zero-violation arrangement is found within the bounded repair space while preserving all required furniture and clearance constraints, RuleBound terminates with `status: "unsatisfiable"` and customer-readable trade-offs rather than silently deleting requested furniture.

## Pricing Engine

- **Integer INR Arithmetic**: All monetary calculations use integer Rupee arithmetic; percentage adjustments use integer basis points ($1\text{ bps} = 0.01\%$).
- **Half-Up Rounding**: Exact integer division with halves rounded toward $+\infty$ (`round_half_up(n, d)`).
- **Rule Code Traceability**: Every line item and summary cites its governing rule (`CATALOG`, `RB-PRC-009`, `RB-PRC-010`, `RB-PRC-011`, `RB-PRC-012`). Unpriced SKUs and incompatible finishes explicitly cite `RB-PRC-013`.
- **Deterministic Line Aggregation**: Placements are grouped by SKU and finish ID, sorted deterministically by line ID.

## Verification & Status

- **Unittest Suite**: 105/105 tests passing (`python -m unittest discover tests`).
- **Pack Verification**: Official asset pack verified (`python tools/verify_pack.py data`).
- **Output Validation**: 100% schema compliant (`python tools/validate_output.py OUTPUT`).
- **Determinism**: 10 output files are 100% byte-identical across runs.
- **Furniture Preservation**: **100%** of required chairs, workstations, storage units, collaboration tables, and accessories are preserved across all five released rooms without furniture loss.
- **DXF Floor Plan Exporter**: Standalone AutoCAD R12 ASCII DXF exporter implemented and verified across all 5 official rooms (`tools/export_dxf.py`, potential +5 bonus).

### Released Room Status

| Room | Layout Status | Achieved / Req Seating | Achieved / Req Desks | Achieved / Req Secondary Furniture | Spatial Violations | Quote Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **ROOM-01** | `unsatisfiable` | **12 / 12** | **6 / 6** (paired) | 2 / 2 storage, 1 / 1 collab | 3 | `blocked` |
| **ROOM-02** | `valid` | **16 / 16** | **0 / 0** (workshop) | 2 / 2 collab tables, 4 / 4 storage | 0 | `priced` (INR 2,70,933) |
| **ROOM-03** | `unsatisfiable` | **10 / 10** | **8 / 8** (fixed) | 1 / 1 touchdown, 2 / 2 accessories | 2 | `blocked` |
| **ROOM-04** | `unsatisfiable` | **14 / 14** | **14 / 14** (individual) | 2 / 2 storage | 6 | `blocked` |
| **ROOM-05** | `unsatisfiable` | **18 / 18** | **12 / 12** (desk pos) | 2 / 2 storage, 2 / 2 collab, 2 / 2 accessories | 6 | `blocked` |

> **Engineering Integrity Note**: RuleBound preserves all requested furniture and authoritative spatial constraints. When extensive deterministic feasibility search finds no zero-violation arrangement within the evaluated placement and repair search space while retaining all required furniture (such as in ROOM-01, ROOM-03, ROOM-04, and ROOM-05), RuleBound honestly escalates to `status: "unsatisfiable"` with structured violations and customer-readable trade-offs, writing a schema-compliant `blocked` quote under `RB-PRC-013`. The hard boundary safety gate guarantees that no candidate layout placing furniture outside the room polygon is ever accepted. Additionally, while the arbitration engine includes regression-tested targeted `RB-GEO-004` repair capability to resolve rear-clearance shortfall displacements, the final room outputs contain zero `RB-GEO-004` violations because the generator enforces rear clearance upstream.

## Output Structure

```
OUTPUT/
├── ROOM-01/
│   ├── layout.json
│   └── quote.json
├── ROOM-02/
│   ├── layout.json
│   └── quote.json
├── ROOM-03/
│   ├── layout.json
│   └── quote.json
├── ROOM-04/
│   ├── layout.json
│   └── quote.json
└── ROOM-05/
    ├── layout.json
    └── quote.json
```

## Design & System Boundaries

- **Official Assets Preserved**: `data/*`, `schemas/*`, and `tools/*` remain 100% untouched and preserved.
- **Zero LLM in Execution Engine**: Generative text parsing is isolated to initial proposal generation. Constraint validation, arbitration, and pricing contain zero LLM calls, external API dependencies, or non-deterministic operations.
- **Constraint Authority**: Generator heuristics serve strictly for candidate placement ranking; `src/constraints.py` holds sole authoritative rule validation.
- **Schema & Determinism Invariant**: Output layout and quote JSONs conform strictly to official schemas with `additionalProperties: false` and render byte-identically across environments.
## Cloud Deployment (Azure + Microsoft Entra ID Bonus)

RuleBound provides a verified, zero-dependency cloud deployment layer on **Azure App Service** fronted by **Microsoft Entra ID Authentication (Easy Auth)**:

- **Live Endpoint**: `https://app-rulebound-api-demo.azurewebsites.net/api/v1/solve`
- **Authentication**: Protected by Microsoft Entra ID (App Service Authentication v2).
  - Unauthenticated / browser access triggers the Microsoft Entra authentication flow (redirecting unauthenticated users to Microsoft login or returning a 401/302 challenge).
  - Authenticated POST requests bearing a valid Microsoft Entra OAuth2 bearer token execute the live RuleBound pipeline and return schema-valid JSON.
- **Verified Execution**: Verified end-to-end against `ROOM-02` resulting in status `valid`, 0 spatial violations, and exact quote `₹270,933`.
- **Deployment Artifacts**: Self-contained Bicep infrastructure-as-code and pure Python WSGI service wrapper reside under `deploy/azure/`.
- **Architecture Isolation**: The cloud layer is a strictly isolated wrapper around the deterministic local core, adding zero dependencies to the root execution path.

> **Access & Verification Note**: The live endpoint is an Entra-protected backend API endpoint, not a public browser demo page. Opening the URL in a browser or calling without authorization triggers the Microsoft Entra ID authentication flow. Authenticated API execution requires a valid OAuth2 bearer token issued for the tenant. For frictionless independent evaluation, judges should use the local CLI runner and test suite (`python starter/python/runner.py --input data --output OUTPUT`), while the Azure deployment demonstrates the deployed authenticated service for the Azure + Entra ID bonus track.

## Judge Entry Point

Judges can quickly evaluate the implementation using these key touchpoints:
1. **One-Command Runner**: `python starter/python/runner.py --input data --output OUTPUT`
2. **Schema Validator**: `python tools/validate_output.py OUTPUT`
3. **Determinism Checker**: `python tools/check_determinism.py --command "python starter/python/runner.py --input {input} --output {output}" --input data --work-dir det_work`
4. **Interactive Trace Demo**: `python demo_trace.py`
5. **Standalone DXF Exporter (Bonus Track)**: `python tools/export_dxf.py --input data --output OUTPUT --dxf-dir DXF_OUTPUT`
6. **Azure + Entra ID Deployment (Bonus Track)**: [deploy/azure/README.md](deploy/azure/README.md) (Live protected endpoint: `https://app-rulebound-api-demo.azurewebsites.net/api/v1/solve`)
7. **Detailed Architecture Document**: [ARCHITECTURE.md](ARCHITECTURE.md)
8. **Project Changelog**: [CHANGELOG.md](CHANGELOG.md)
9. **Committed Output Artifacts**: [OUTPUT/](OUTPUT/)

