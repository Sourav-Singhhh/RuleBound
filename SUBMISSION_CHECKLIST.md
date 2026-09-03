# Round 3 Final Submission Checklist

- [x] Repository shared with the judging account and accessible throughout judging.
- [x] One documented runner command accepts `--input` and `--output` directories (`python starter/python/runner.py --input data --output OUTPUT`).
- [x] `ARCHITECTURE.md` includes system diagram, state machine, objective function, and arbitration section.
- [x] `OUTPUT/` committed for all five released room specifications.
- [x] Standalone DXF floorplan exporter committed and verified (`python tools/export_dxf.py --input data --output OUTPUT --dxf-dir DXF_OUTPUT`).
- [x] `tools/validate_output.py OUTPUT` reports `OUTPUT VALID` across all layout and quote files.
- [x] `tools/check_determinism.py` confirms 100% byte-identical outputs across runs.
- [x] Full unit test suite passes: 98/98 tests passing (`python -m unittest discover tests`).
- [x] Verified in isolated clean-checkout sandbox with zero external package dependencies.
- [ ] Final demo video (3.5–4 minutes) recorded and URL added to README.md.
- [x] Every dependency, asset, and code fragment is original, self-contained, or properly licensed.

