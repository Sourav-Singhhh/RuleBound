# Changelog

All notable changes to the RuleBound project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
