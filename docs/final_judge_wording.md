# Final Judge Wording & Positioning Guide — RuleBound

## A. Tagline
Deterministic spatial layout arbitration, constraint enforcement, and integer-exact pricing with zero-compromise financial and geometric integrity.

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
Azure deployment and Entra ID integration were intentionally excluded from this submission to keep the scored deterministic core 100% dependency-free, lightweight, and auditable on any standard Python runtime.

## I. One-Line Differentiator
RuleBound is the only spatial engine with hard furniture preservation preconditions and integer-exact pricing that guarantees zero hallucinated layouts and zero financial drift.

---

## J. 60-Second Spoken Opening (Demo)
"Welcome. In automated space planning, the biggest failure mode of generative systems is hallucination: deleting furniture to pass clearance checks, clipping egress corridors, or drifting in financial quotes. RuleBound was engineered to solve this through a dual-layer architecture: a generative brief parser coupled to an immutable, deterministic constraint, arbitration, and pricing core. 

On your screen is ROOM-02, a 16-person client workshop. RuleBound extracts 0 desks, 2 large collaboration tables, 16 chairs, and 4 storage units. The arbitration engine verifies spatial validity with zero violations, and the pricing engine computes an exact integer quote of ₹270,933 INR with complete rule provenance. 

Every run across every environment is byte-identical, schema-compliant, and auditable without external API dependencies."

---

## K. 20-Second Closing (Demo)
"In conclusion, RuleBound delivers what enterprise automated design demands: absolute mathematical determinism, rigorous spatial constraint enforcement, integer-exact commercial quotes, and standard AutoCAD DXF exports. Thank you."

---

## L. Tough Judge Q&A Guide

### Q1: "Why are four rooms unsatisfiable?"
**Answer:** In ROOM-01, ROOM-03, ROOM-04, and ROOM-05, the combination of marked diagonal egress corridors (1100mm width) and required workstation density creates physical area deficits. Rather than deleting desks or compromising walkways, RuleBound's safety contract honestly reports the spatial trade-off and blocks the quote under `RB-PRC-013`.

### Q2: "Why should we choose RuleBound over a project that solves more rooms?"
**Answer:** Because RuleBound's outputs are mathematically and commercially trustworthy. A system that claims 5 valid rooms by silently removing required desks, placing furniture outside walls, or ignoring rear clearances creates illegal floorplans and invalid quotes. RuleBound guarantees 100% furniture preservation, strict boundary safety, and byte-identical determinism.

### Q3: "Is unsatisfiable a formal proof of impossibility?"
**Answer:** No. Unsatisfiable means that no zero-violation arrangement was found within the evaluated deterministic repair space and macro-topological permutations while retaining all required items. It is an empirical guarantee that the engine refuses to fabricate a false solution.

### Q4: "Why don't you have Azure / Entra ID?"
**Answer:** We prioritized absolute core algorithmic integrity: 98 unit tests, pure integer arithmetic, standalone DXF export, and zero-dependency reproducibility. Adding cloud infrastructure wrapper layers would not improve the core spatial solver.

### Q5: "What is unique about RuleBound?"
**Answer:** Its failure-safety invariants. RuleBound mathematically prohibits furniture evaporation, prevents boundary escapes, eliminates floating-point pricing drift, and generates production-ready AutoCAD DXF files completely within the Python standard library.
