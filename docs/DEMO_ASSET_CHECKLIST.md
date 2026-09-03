# Demo Asset Checklist & Script — RuleBound

## 1. Quick Recording Information
- **Repository URL**: `https://github.com/Sourav-Singhhh/RuleBound.git`
- **Release Commit**: `515214ac70ba0fb957add628362ca4e7ff8de1a5`
- **Target Video Duration**: 3.5 – 4.0 minutes (max 5 minutes)
- **README Link Placeholder**: Line 7 in `README.md` (`- **Walkthrough Video**: [Demo video — replace with final hosted URL]`)

---

## 2. Fast Demo Command Sequence

```bash
# 1. Pipeline Execution
python starter/python/runner.py --input data --output OUTPUT

# 2. Output Schema Validation
python tools/validate_output.py OUTPUT

# 3. Determinism Verification
python tools/check_determinism.py --command "python starter/python/runner.py --input {input} --output {output}" --input data --work-dir det_work

# 4. Standalone DXF Floorplan Exporter
python tools/export_dxf.py --input data --output OUTPUT --dxf-dir DXF_OUTPUT

# 5. Full 98-Test Regression Suite
python -m unittest discover tests
```

---

## 3. Demo Screen & File Touchpoints

| Timestamp | Visual Focus | Key Narrative Points |
| :--- | :--- | :--- |
| **0:00 – 0:20** | `README.md` & Terminal | Dual-layer architecture; zero hallucination; deterministic core. |
| **0:20 – 0:45** | `ARCHITECTURE.md` | Handoff object `ProposedLayout`, strict lexicographic gate, tabu memory, integer pricing. |
| **0:45 – 1:25** | `OUTPUT/ROOM-02/layout.json` | ROOM-02 workshop: 16 chairs, 2 collab tables, 4 storage; 0 violations, `status: "valid"`. |
| **1:25 – 2:00** | `OUTPUT/ROOM-02/quote.json` | Exact ₹270,933 INR; integer arithmetic, basis points, line item rule citations. |
| **2:00 – 2:35** | `OUTPUT/ROOM-01/layout.json` & `quote.json` | Unsatisfiable failure-safety contract: 100% furniture preserved, structured trade-offs, quote blocked under `RB-PRC-013`. |
| **2:35 – 3:10** | Terminal (`check_determinism.py`) | Subprocess byte-identical determinism across random PYTHONHASHSEED. |
| **3:10 – 3:35** | `DXF_OUTPUT/ROOM-02.dxf` | Color-coded CAD layers (`WALLS`, `DOORS`, `EGRESS`, `SEATING`, `TABLES`), standard AutoCAD R12 ASCII. |
| **3:35 – 4:00** | Terminal & Summary | 98/98 unit tests passing; clean, dependency-free, enterprise-ready submission. |
