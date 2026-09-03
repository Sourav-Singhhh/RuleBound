# Demo Asset Checklist & Script — RuleBound

## 1. Recording Information
- **Repository URL**: `https://github.com/Sourav-Singhhh/RuleBound.git`
- **Release Branch**: `main`
- **Target Video Duration**: 3.5 – 4.0 minutes (max 5 minutes)
- **README Link Placeholder**: Line 7 in `README.md` (`- **Walkthrough Video**: [Demo video — replace with final hosted URL]`)

---

## 2. Pre-Recording Verification Checklist

- [x] Runner command tested (`python starter/python/runner.py --input data --output OUTPUT`)
- [x] ROOM-02 output exists (`OUTPUT/ROOM-02/layout.json`)
- [x] ROOM-02 quote.json exists (`OUTPUT/ROOM-02/quote.json`)
- [x] Exact ₹270,933 price visible in quote.json
- [x] Unsatisfiable failure-safety example ready (`OUTPUT/ROOM-04/layout.json` & `quote.json`)
- [x] Subprocess determinism checker ready (`python tools/check_determinism.py ...`)
- [x] Standalone DXF export ready (`python tools/export_dxf.py ...`)
- [x] README.md open to key architecture and touchpoint sections
- [ ] No private information or local path leaks visible
- [ ] Terminal font and screen resolution clean and legible
- [ ] No extraneous background apps or notifications visible
- [ ] Video duration strictly within 3.5–4.0 minutes

---

## 3. Fast CLI Command Sequence for Recording

```bash
# 1. Pipeline Execution
python starter/python/runner.py --input data --output OUTPUT

# 2. Output Schema Validation
python tools/validate_output.py OUTPUT

# 3. Determinism Verification
python tools/check_determinism.py --command "python starter/python/runner.py --input {input} --output {output}" --input data --work-dir det_work

# 4. Standalone DXF Floorplan Exporter
python tools/export_dxf.py --input data --output OUTPUT --dxf-dir DXF_OUTPUT

# 5. Full 105-Test Regression Suite
python -m unittest discover tests
```

---

## 4. Timed Storyboard & Screen Touchpoints

| Timestamp | Visual Focus | Spoken Narrative Key Points |
| :--- | :--- | :--- |
| **0:00 – 0:20** | `README.md` / Architecture | Plain-English brief $\to$ layout $\to$ constraint validation $\to$ exact quote. |
| **0:20 – 0:45** | `ARCHITECTURE.md` diagram | Generator proposes; deterministic constraints decide; arbitration accepts only strict improvements. |
| **0:45 – 1:25** | `OUTPUT/ROOM-02/layout.json` | ROOM-02 resolves cleanly: 0 violations, `status: "valid"`, all 22 furniture targets preserved. |
| **1:25 – 2:00** | `OUTPUT/ROOM-02/quote.json` | Pure integer-exact arithmetic: catalog $\to$ finish $\to$ discount $\to$ labor $\to$ freight $\to$ ₹270,933. |
| **2:00 – 2:35** | `OUTPUT/ROOM-04/layout.json` | Failure safety: 100% furniture preserved; honest escalation to unsatisfiable; quote blocked under `RB-PRC-013`. |
| **2:35 – 3:10** | Terminal (`check_determinism.py`) | Multi-process determinism run showing 100% byte-identical output across runs. |
| **3:10 – 3:35** | `DXF_OUTPUT/ROOM-02.dxf` | Standard AutoCAD R12 ASCII DXF with color-coded semantic layers (`WALLS`, `DOORS`, `EGRESS`, `SEATING`, `DESKS`). |
| **3:35 – 4:00** | Architecture & Closing | "Generate. Verify. Repair only valid improvements. Price exactly. Escalate honestly when unresolved." |
