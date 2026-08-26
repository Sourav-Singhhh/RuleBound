# RuleBound

A deterministic room-layout, constraint-validation, arbitration, and pricing engine for the RuleBound Sealed Build Challenge.

## Overview

RuleBound integrates an initial proposal generator with an exact, deterministic spatial constraint validator, a bounded arbitration search engine, and a precise pricing engine. Given plain-English briefs and 2D room specifications, the system extracts furniture requirements, constructs valid starting proposals, and deterministically repairs constraint violations using bounded local search with tabu state hashing. Valid layout proposals are priced into exact integer-INR quotes with full rule execution traces, while unresolvable layouts escalate into schema-valid `unsatisfiable` layout and `blocked` quote outputs. All spatial validation, arbitration, and pricing operations run 100% deterministically without external LLM calls or network dependencies.

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
Bounded Arbitration
        ↓
 Final Validation
        ↓
Deterministic Pricing
        ↓
layout.json + quote.json
```

- **Generator**: Parses customer briefs and room specifications to extract quantitative requirements and finish preferences, placing catalog items on a 100mm grid inside room boundaries while using deterministic spacing, door, and egress heuristics to construct sensible starting proposals.
- **ProposedLayout**: Typed internal handoff object carrying the generator's deterministic placement proposal into arbitration.
- **Constraint Engine**: Authoritatively evaluates layouts against official spatial rules (`RB-GEO-001` through `RB-GEO-008`), returning exact violation payloads.
- **Bounded Arbitration**: Implements local candidate repair search (`ROW_GROUP_SHIFT`, `MOVE_WORKSTATION_POD`, `NUDGE`, `ROTATE`, `SUBSTITUTE_SKU`, `REMOVE_PLACEMENT`) under strict lexicographic acceptance gates and tabu memory.
- **Final Validation**: Confirms spatial validity (`status: "valid"`) and seating capacity feasibility.
- **Deterministic Pricing**: Computes exact integer INR line items, finish uplifts, quantity discounts, labour, and freight, writing output quotes.

## Arbitration Highlights

- **Lexicographic Objective**: Prioritizes seating capacity feasibility over spatial violation reduction, ensuring mandatory seating requirement is primary.
- **Capacity Shortfall First**: Prevents trading off required task chairs to resolve spatial defects.
- **Strict Improvement Gate**: Rejects candidate moves that do not strictly improve the lexicographic objective tuple.
- **Deterministic Candidate Ranking**: Sorts repair candidates using a deterministic key `(SortKey, target_placement_id, parameter_string)`.
- **Tabu Memory & State Hashing**: Uses SHA-256 state hashes ($H$) to prevent trajectory cycling.
- **Bounded Local Repair**: Operates under an execution cap $K_{\max} = \min(50, \max(10, 10N))$. Search exhaustion (`local_repair_exhausted`) indicates local frontier termination, not a global mathematical infeasibility proof.

## Pricing Engine

- **Integer INR Arithmetic**: All monetary calculations use integer Rupee arithmetic, with percentage adjustments represented using integer basis points.
- **Finish Uplifts**: Evaluates `RB-PRC-010` basis-point uplifts per product family and finish combination.
- **Quantity Discounts**: Applies `RB-PRC-009` volume discount tiers deterministically.
- **Labour & Freight**: Calculates assembly labour minutes (`RB-PRC-011`) and tier-based freight bands (`RB-PRC-012`).
- **Summary Traces**: Includes itemized step-by-step price rule execution traces in line items and quote summaries.
- **Deterministic Line Aggregation**: Groups placements by SKU and finish ID, sorted deterministically by line ID.

## Verification & Status

- **Unittest Suite**: 80/80 tests passing (`python -m unittest discover tests`).
- **Pack Verification**: Official asset pack verified (`python tools/verify_pack.py`).
- **Output Validation**: 100% schema compliant (`tools/validate_output.py OUTPUT`).
- **Determinism**: 10 output files are 100% byte-identical across runs.
- **Seating Preservation**: **70 / 70** required seats preserved across all five released rooms.

### Released Room Status

| Room | Layout Status | Spatial Violations | Seating Count / Required | Quote Status |
| :--- | :--- | :---: | :---: | :--- |
| **ROOM-01** | **`valid`** | **0** | **12 / 12** | `priced` |
| **ROOM-02** | `unsatisfiable` | **4** | **16 / 16** | `blocked` |
| **ROOM-03** | **`valid`** | **0** | **10 / 10** | `priced` |
| **ROOM-04** | `unsatisfiable` | **1** | **14 / 14** | `blocked` |
| **ROOM-05** | `unsatisfiable` | **2** | **18 / 18** | `blocked` |

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

## Judge Entry Point

Judges can quickly evaluate the implementation using these key touchpoints:
1. **One-Command Runner**: `python starter/python/runner.py --input data --output OUTPUT`
2. **Schema Validator**: `python tools/validate_output.py OUTPUT`
3. **Determinism Checker**: `python tools/check_determinism.py --command "python starter/python/runner.py --input {input} --output {output}" --input data --work-dir det_work`
4. **Detailed Architecture & Design Document**: [`ARCHITECTURE.md`](file:///c:/Users/rajpu/Desktop/RuleBound/RuleBound-Round1/ARCHITECTURE.md)
5. **Committed Output Artifacts**: [`OUTPUT/`](file:///c:/Users/rajpu/Desktop/RuleBound/RuleBound-Round1/OUTPUT)
