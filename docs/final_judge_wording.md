# Final Judge Wording & Positioning Guide — RuleBound

## A. Tagline
Deterministic spatial layout arbitration, constraint enforcement, and integer-exact pricing with verified mathematical integrity.

## B. 30-Second Overview
RuleBound bridges generative natural-language space planning with an immutable, deterministic constraint, arbitration, and pricing engine. Given brief requirements and room boundaries, it extracts exact furniture demands, evaluates authoritative spatial clearances, and performs monotonic lexicographic repair with atomic pod operators and tabu memory. Feasible layouts produce integer-exact INR quotes with full rule audit trails, while unresolvable constraints honestly escalate to schema-compliant unsatisfiable outputs and blocked quotes rather than deleting required furniture or fabricating false clearances.

## C. Arbitration Explanation
Arbitration operates as a bounded deterministic state machine. It evaluates candidate geometric shifts against a lexicographic objective tuple `(capacity_shortfall, spatial_violations, distinct_placements, total_displacement, op_rank)`. Monotonic descent strictly prevents cyclic loops. Atomic composite operators (`MOVE_WORKSTATION_POD`, `ROW_GROUP_SHIFT`) resolve coupled desk-chair aisle clearances without geometric desynchronization, while hard boundary invariants guarantee that no candidate placing furniture outside the room polygon is ever accepted.

## D. Pricing Explanation
All pricing calculations execute in pure integer INR arithmetic without floating-point drift. Percentage adjustments (discounts, uplifts, freight) use integer basis points ($1\text{ bps} = 0.01\%$) with exact half-up rounding (`round_half_up`). Every line item cites its governing rule (`CATALOG`, `RB-PRC-009` through `RB-PRC-012`). Unresolvable spatial layouts or unpriced SKUs strictly block quote emission under `RB-PRC-013`.

## E. Constraint Explanation
`src/constraints.py` holds sole authoritative validation. Spatial rules `RB-GEO-001` through `RB-GEO-008` rigorously enforce 900mm primary walkway widths, boundary polygon containment, non-overlapping footprints, door swing clearances, and occupied desk rear clearances without heuristic relaxations.

## F. Unsatisfiable Explanation
Unsatisfiable means the bounded deterministic repair process found no compliant arrangement within its evaluated search space while strictly preserving 100% of requested furniture and clearance rules. RuleBound deliberately prefers an honest, customer-readable trade-off escalation over fabricating a falsely valid layout by silently deleting required desks or clipping egress lines.

## G. DXF Explanation
A standalone, pure-standard-library CAD generator (`tools/export_dxf.py`) exports color-coded AutoCAD R12 ASCII DXF floorplans across all benchmark rooms, mapping architectural boundaries, door swings, egress corridors, and furniture families to dedicated CAD layers.

## H. Azure Scope Statement
Azure deployment and Entra ID integration were intentionally left out of this submission to keep the scored deterministic core dependency-free and fully auditable on standard runtime environments.

## I. One-Line Differentiator
RuleBound separates proposing from deciding: it prevents an unvalidated generated layout from being accepted as valid and ensures every monetary figure is integer-exact.

---

## J. Final Spoken Demo Narrative (3.5–4.0 Minutes)

### 0:00–0:20 — Problem & Value Proposition
"RuleBound takes a plain-English facilities brief and a room specification, produces a furniture layout, verifies it against authoritative spatial constraints, and generates an exact quote — or reports honestly when the layout cannot be resolved within its evaluated search space."

### 0:20–0:45 — System Architecture
"The generator proposes. The deterministic constraint engine is the authority. Arbitration can only accept strict improvements that preserve all required furniture and boundaries. Pricing is completely deterministic."

### 0:45–1:25 — Success Case (ROOM-02)
"ROOM-02 resolves cleanly with zero violations while preserving every required semantic furniture target: 16 seating units, 2 collaboration tables, and 4 storage units."

### 1:25–2:00 — Exact Pricing Trace (ROOM-02)
"Every monetary operation is integer-exact and traceable. This run produces ₹270,933 with no floating-point pricing path."

### 2:00–2:35 — Failure Safety & Unsatisfiable Escalation (ROOM-04 / ROOM-01)
"When no compliant zero-violation arrangement is found within the evaluated bounded search space, RuleBound does not silently delete required furniture or relax constraints. It reports the unresolved state honestly and blocks the quote."

### 2:35–3:10 — Determinism Verification
"Now we run the same pipeline again under independent subprocesses. The layout and quote outputs are byte-identical across all executions."

### 3:10–3:35 — Standalone DXF Floorplan Export
"The validated layout can also be exported as a standard AutoCAD R12 ASCII DXF floor plan with semantic CAD layers for walls, doors, egress, desks, seating, and collaboration zones."

### 3:35–4:00 — Conclusion & Summary
"RuleBound separates proposing from deciding. A generated layout never becomes valid just because it looks plausible. The result must pass the deterministic constraints, preserve the requested furniture, and produce a reproducible quote. Generate. Verify. Repair only valid improvements. Price exactly. Escalate honestly when unresolved."

---

## K. Judge Q&A Guide

### Q1: "Why are four rooms unsatisfiable?"
**Answer:** Those rooms did not yield a compliant zero-violation arrangement within our evaluated bounded placement and repair search space while preserving the required furniture and clearance rules. We report that honestly rather than deleting furniture or relaxing constraints to manufacture a pass.

### Q2: "Is that a mathematical proof that no solution exists?"
**Answer:** No. It is a bounded-search result, not a proof over the full continuous combinatorial space. We deliberately distinguish search exhaustion from global mathematical infeasibility.

### Q3: "Why should we choose RuleBound over a system that solves more rooms?"
**Answer:** Because the validity decision is authoritative and deterministic. The system cannot silently turn an invalid layout into a valid quote by dropping required furniture or relaxing a constraint.

### Q4: "Why no Azure / Entra ID?"
**Answer:** Azure and Entra ID were intentionally outside this submission's scope so the scored deterministic core remained dependency-free and fully auditable.

### Q5: "What's unique about RuleBound?"
**Answer:** The key design boundary is that generation proposes, but deterministic constraints decide. No generated layout or price becomes authoritative without passing the verification path.
