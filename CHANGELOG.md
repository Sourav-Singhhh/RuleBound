# Changelog

All notable changes to the RuleBound project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.5.0] - 2026-09-04 (Final Round 3 Submission Release: Workstation Spacing & Fallback Clearance Hardening)

### Added
- **Dynamic Workstation Row-Pitch Calculation (`src/generator.py`)**: Workstation row pitch is dynamically derived from physical pod depth plus the mandatory 900 mm rear clearance (`RB-GEO-004`), preventing desk rows from compressing below legal clearance bounds (`tests/test_row_pitch.py`).
- **Fallback Desk Rear-Clearance Enforcement (`src/generator.py`)**: Enforced `RB-GEO-004` rear-clearance reservations across fallback desk placement and secondary furniture searches via `clearance_boxes`, preventing uncoupled fallback desks from stacking into unreserved rear clearances (`tests/test_fallback_clearance.py`).
- **Regression Suite Expansion (`tests/test_row_pitch.py`, `tests/test_fallback_clearance.py`)**: Added test coverage verifying dynamic row pitch, fallback clearance bounds, multi-room validation, and deterministic regression (expanding suite from 98 to 105/105 passing).

### Changed
- **Total Spatial Violations Reduced by 60.5%**: Total spatial violations across the 5 benchmark rooms dropped from 43 to 17, completely eliminating all `RB-GEO-004` violations across the entire room set:
  - `ROOM-01`: 3 violations (down from 8)
  - `ROOM-02`: 0 violations (`valid`, priced at ₹2,70,933 INR)
  - `ROOM-03`: 2 violations (down from 7)
  - `ROOM-04`: 6 violations (down from 21)
  - `ROOM-05`: 6 violations (down from 7)
- **Submission Metric Alignment**: Synchronized `README.md`, `SUBMISSION_CHECKLIST.md`, and demo documentation to reflect 105/105 unit tests, verified 10-file byte-identical determinism, verified DXF floor plan assets (`DXF_OUTPUT/`), and 100% semantic furniture retention.

---

## [3.4.0] - 2026-09-03 (Standalone DXF Floorplan Exporter & Claim Hardening)

### Added
- **Standalone AutoCAD ASCII DXF Exporter (`tools/export_dxf.py`)**: Implemented clean, dependency-free floor plan generator exporting color-coded CAD layers (`WALLS`, `DOORS`, `EGRESS`, `DESKS`, `CHAIRS`, `STORAGE`, `COLLABORATION`, `ACCESSORIES`) matching official AutoCAD R12 ASCII specifications (potential +5 bonus).
- **DXF Unit & Regression Suite (`tests/test_dxf_export.py`)**: Added test coverage verifying DXF headers, entity syntax, layer mappings, and all official room exports (expanding suite to 98/98 passing).

### Changed
- **Defensible Feasibility & Escalation Language**: Refined documentation across `README.md`, `ARCHITECTURE.md`, and `CHANGELOG.md` to precisely describe bounded deterministic local repair and extensive empirical search without overclaiming unproven global mathematical theorems.

---

## [3.3.0] - 2026-09-03 (RB-GEO-004 Targeted Repair, Boundary Safety Gate & Truthful Documentation)

### Added
- **Targeted Clearance Repair (`ArbitrationEngine`)**: Calculates exact geometric shortfall displacements for `RB-GEO-004` rear-clearance conflicts to directly translate offending items into clear space.
- **Hard Boundary Safety Gate (`ArbitrationEngine`)**: Rejects any candidate repair placement whose bounding box extends outside the room boundary polygon.

### Changed
- **Boundary & Clearance Preconditions**: Strengthened candidate evaluation preconditions to enforce boundary containment before testing clearance improvements.

---

## [3.2.0] - 2026-09-03 (Targeted Correctness Fix: RB-GEO-001 Walkway Scope & Parser Hardening)

### Added
- **Focused RB-GEO-001 & Parser Unit Tests**:
  - `test_geo_001_chair_chair_at_same_workstation_does_not_trigger`: Intra-pod chair spacing is not a public walkway.
  - `test_geo_001_chairs_around_collaboration_table_do_not_trigger`: Conference seating around shared meeting tables does not trigger false corridor violations.
  - `test_geo_001_accessory_accessory_does_not_trigger`: Movable whiteboard/acoustic screens standing near each other do not trigger walkway violations.
  - `test_geo_001_chair_desk_gap_governed_by_other_rules_does_not_trigger`: Orthogonal chair-to-desk gaps are governed by dedicated rules (`RB-GEO-004`/`RB-GEO-008`).
  - `test_geo_001_genuine_pod_primary_walkway_still_triggers`: Genuine pod-to-pod corridor bottlenecks (< 900 mm) remain strictly enforced.
  - `test_21_capacity_parser_natural_phrasing`: Supports natural phrases ("for 18 people", "18 employees", "a team of eighteen").
  - `test_22_desk_negation_parsing`: Distinguishes negative clauses ("with no desks", "without any desks", "zero desks") to prevent false desk counts.

### Changed
- **RB-GEO-001 Primary Circulation Scope**:
  - Corrected `RB-GEO-001` in `src/constraints.py` to evaluate circulation clear width across major structural furniture arrangements (`desk`, `storage`, `collaboration`).
  - Decoupled task seating ergonomics and mobile accessories from architectural corridor checks, eliminating 18 false-positive violations across official challenge rooms.
  - Allowed `ArbitrationEngine` to naturally discover a **0-violation valid layout for ROOM-02** in 2 iterations, generating a fully priced quote of **₹2,70,933 INR**.
- **Brief Parser Negation Handling**:
  - Distinguishes positive workstation requests from negative clauses in `src/generator.py`, preventing false desk allocation when briefs explicitly state "with no desks" or "zero desks".
- **Canonical Outputs Updated**:
  - ROOM-02 is now verified `valid` and `priced` (`quote.json`).
  - ROOM-01, ROOM-03, ROOM-04, and ROOM-05 remain honestly `unsatisfiable` due to physical boundary geometry and egress constraints.

---

## [3.1.0] - 2026-09-03 (Semantic Hardening: Brief Semantics & Universal Furniture Preservation)

### Added
- **Universal Furniture Preservation Invariant**: Extended `ArbitrationEngine` invariants and candidate preconditions to all 5 catalog families (`chair`, `desk`, `storage`, `collaboration`, `accessory`). `REMOVE_PLACEMENT` is strictly barred from deleting any required furniture below the brief's targets.
- **Targeted Semantic Tests**:
  - `test_2_five_brief_requirement_extraction`: Validates ground-truth parsing across all 5 rooms (6 paired desks for ROOM-01, 0 desks for ROOM-02 workshop, 8 desks for ROOM-03, 14 for ROOM-04, 12 for ROOM-05).
  - `test_ac_secondary_furniture_preservation_storage_and_collab`: Confirms arbitration cannot delete required storage or collaboration tables.

### Changed
- **Ground-Truth Brief Semantics (No Blind Fallback)**:
  - Eliminated the blind fallback assumption that unmentioned desks equal room capacity.
  - Correctly parses "paired desks" in ROOM-01 into 6 physical 1600mm desks (`NW-DES-003`) seating 12 chairs.
  - Correctly parses flexible client workshop in ROOM-02 into 0 desks, 2 collaboration tables (`NW-COL-003`), and 16 task chairs.
- **Clean Geometric Initial Placement**: Removed formulaic coordinate dumping in `GeneratorEngine`. Items are only placed when valid, non-overlapping geometric locations within boundary and egress corridors exist.
- **Regenerated Canonical Outputs**: Re-executed `runner.py` across all 5 test rooms with 100% semantic furniture retention and byte-identical determinism.

---

## [3.0.0] - 2026-09-03 (Round 3 Final Hardening & Winner Selection)

### Added
- **Hard Semantic Precondition for Workstation Preservation**: Added `count_workstation_capacity` to `ArbitrationEngine` and enforced a strict invariant preventing `REMOVE_PLACEMENT` from deleting mandatory desks below the room's required workstation count. Workstations can no longer evaporate to artificially pass spatial validation.
- **Pure Integer Displacement & Geometry**: Hardened displacement tie-breaking in `ArbitrationEngine` using exact integer integer-square-root (`math.isqrt`), and unified `point_to_segment_dist_sq` in `GeneratorEngine` to pure integer arithmetic matching `ConstraintEngine`.
- **Pricing Rule Code Traceability (`RB-PRC-013`)**: Blocked quotes caused by unpriced SKUs or finish incompatibility now explicitly cite `RB-PRC-013` in `blocking_reasons` as specified in `PRICING_SPEC.md`.
- **Targeted Regression Tests**:
  - `test_aa_workstation_preservation_cannot_delete_desks`: Verifies that required desks cannot be removed even if removal would resolve spatial violations.
  - `test_ab_integer_displacement_guarantee`: Verifies integer-exact displacement calculations.
  - `test_unpriced_sku_blocks_quote` and `test_incompatible_finish_blocks_quote`: Verified to explicitly assert `RB-PRC-013`.
- **End-to-End Pipeline Demo**: Enhanced `demo_trace.py` demonstrating room proposal, constraint detection, atomic pod arbitration, workstation preservation, exact pricing trace, and byte-identical determinism.

### Changed
- **Honest Escalation Over False Validity**: Updated `ArbitrationEngine` escalation logic to report both achieved seating and achieved workstation capacity against required targets, ensuring genuine spatial limits are transparently escalated with customer-readable trade-offs.
- **Architectural Documentation Precision**: Updated `ARCHITECTURE.md` and `README.md` to accurately document termination and cycle-prevention guarantees (strict monotonic lexicographic improvement, finite execution cap $K_{\max}$, and action-tabu memory) without claiming an active visited-hash set.
- **Regenerated Canonical Outputs**: Re-executed `runner.py` across all test rooms (`ROOM-01` through `ROOM-05`), producing validated `layout.json` and `quote.json` outputs with full workstation integrity.

### Removed
- **Duplicate Class Stub**: Removed shadowed partial `ConstraintEngine` class declaration from `src/constraints.py` (lines 123–185), ensuring clean and unambiguous class resolution.

---

## [2.0.0] - 2026-09-02 (Round 2 Architecture & Determinism Pass)

### Added
- **Deterministic Arbitration Engine**: Implemented bounded local repair arbitration state machine with lexicographical objective model.
- **Atomic Composite Operators**: Introduced `MOVE_WORKSTATION_POD` (atomic desk+chair translation) and `ROW_GROUP_SHIFT` (contiguous desk row translation) to resolve tight pod walkway clearances without geometric de-synchronization.
- **Integer-Exact Pricing Engine**: Implemented `PricingEngine` supporting quantity discount tiers, room-capacity labour tiers, distance-band freight, and round-half-up basis-point calculations.
- **Deterministic Test Suite**: Comprehensive test coverage across generation, constraints, arbitration, and pricing.

---

## [1.0.0] - 2026-09-01 (Round 1 Baseline)

### Added
- Initial implementation of RuleBound pipeline meeting official challenge runner contract.
- Proposal generator for structured office layouts.
- Constraint validation for spatial rules `RB-GEO-001` through `RB-GEO-008`.
