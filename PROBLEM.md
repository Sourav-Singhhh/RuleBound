# RuleBound — Round 1 Sealed Sprint

**Released:** 25 August 2026, 10:00 AM IST  
**Deadline:** 27 August 2026, 10:00 AM IST (hard close)  
**Participation:** Individual only

## The problem

A fictional commercial furniture manufacturer, **Northwind Furnishings**, sells configurable products into office fit-outs. A salesperson receives a floor plan and a one-paragraph brief. Turning that into a reliable quote currently takes days because layout judgement is creative while spatial and pricing rules must be exact.

Two systems must coexist:

1. A **generative layer** reads a brief and proposes a product layout.
2. A **deterministic layer** enforces spatial rules and creates a byte-identical, line-traceable price.

The generator proposes. The rule engine rejects part of it. **What happens next?**

Re-prompting and hoping is not a sufficient design. Show the typed contract at the seam, a bounded repair loop, the strictly decreasing measure that proves termination, and the escalation object produced when no valid layout exists.

## Build one command

```text
your-command --input <input-directory> --output <output-directory>
```

The input directory contains a room JSON file, its plain-English brief, the catalog, finishes and rule pack. For each released room, produce:

```text
OUTPUT/<room_id>/layout.json
OUTPUT/<room_id>/quote.json
```

### Required capabilities

- **Generate:** propose a 2D top-down layout using released catalog SKUs. Partial credit is acceptable.
- **Constrain:** validate every placement against the machine-readable rules. Invalid placements may never pass silently.
- **Arbitrate:** repair or escalate every violation through a structured, terminating loop. This is the scored core.
- **Price:** product, finish uplift, quantity break, labour and freight must be deterministic. Every amount requires a trace. An unpriced line blocks the quote.

### Optional bonus

- Explain any price line by retrieving its trace.
- PDF/PNG/DXF/DWG floor-plan ingest or DXF export.
- Azure deployment with Entra ID authentication.

### Out of scope

- Rendering or 3D; use 2D top-down geometry only.
- Authentication, billing, multi-tenancy or mobile.
- UI polish. A CLI and static plan score identically to a polished UI.

## Arbitration section

`ARCHITECTURE.md` must include a section titled **Arbitration** answering:

1. What object crosses the boundary in each direction? Show the contract.
2. What may the model decide, and when does control pass irreversibly to deterministic code?
3. How does the loop terminate? State the bound and what strictly decreases on each pass.
4. When no valid layout exists, what is produced and what does a human see?

## Scoring

- 35% Arbitration
- 25% Price integrity and determinism
- 15% Constraint enforcement
- 10% Generation quality
- 10% Engineering quality
- +5 bonus: DXF/DWG ingest or export
- +5 bonus: Azure with Entra ID

Automatic zero conditions include: the documented command does not run on a clean machine; repeat runs are not byte-identical; the repository is copied from another submission; or substantial work predates the reveal timestamp.
