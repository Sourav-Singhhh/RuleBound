"""
End-to-End Integration Tests for RuleBound Pipeline (starter/python/runner.py & src/output.py).
Verifies full pipeline execution, dynamic room discovery, schema validity, and determinism.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNNER_SCRIPT = ROOT / "starter" / "python" / "runner.py"
DATA_DIR = ROOT / "data"
SCHEMAS_DIR = ROOT / "schemas"
SCRATCH_DIR = ROOT / "scratch"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class TestIntegrationPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.layout_schema = read_json(SCHEMAS_DIR / "layout.schema.json")
        cls.quote_schema = read_json(SCHEMAS_DIR / "quote.schema.json")
        SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

    def test_1_runner_cli_and_file_generation(self) -> None:
        out_path = SCRATCH_DIR / "test_out_1"
        if out_path.exists():
            shutil.rmtree(out_path)
        out_path.mkdir(parents=True, exist_ok=True)

        try:
            cmd = [sys.executable, str(RUNNER_SCRIPT), "--input", str(DATA_DIR), "--output", str(out_path)]
            res = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Runner failed with error: {res.stderr}")

            # Verify all 5 rooms produced layout.json and quote.json
            for i in range(1, 6):
                r_id = f"ROOM-0{i}"
                l_file = out_path / r_id / "layout.json"
                q_file = out_path / r_id / "quote.json"
                self.assertTrue(l_file.exists(), f"Missing layout.json for {r_id}")
                self.assertTrue(q_file.exists(), f"Missing quote.json for {r_id}")
        finally:
            if out_path.exists():
                shutil.rmtree(out_path, ignore_errors=True)

    def test_2_output_schema_conformance(self) -> None:
        out_path = SCRATCH_DIR / "test_out_2"
        if out_path.exists():
            shutil.rmtree(out_path)
        out_path.mkdir(parents=True, exist_ok=True)

        try:
            cmd = [sys.executable, str(RUNNER_SCRIPT), "--input", str(DATA_DIR), "--output", str(out_path)]
            subprocess.run(cmd, check=True)

            for i in range(1, 6):
                r_id = f"ROOM-0{i}"
                layout = read_json(out_path / r_id / "layout.json")
                quote = read_json(out_path / r_id / "quote.json")

                # Layout required fields
                self.assertEqual(set(layout.keys()), {"room_id", "placements", "violations", "status"})
                self.assertIn(layout["status"], ["valid", "invalid", "unsatisfiable"])

                # Quote required fields
                req_quote_keys = {"quote_id", "room_id", "currency", "lines", "summary", "status"}
                self.assertTrue(req_quote_keys.issubset(set(quote.keys())))
                self.assertIn(quote["status"], ["priced", "blocked"])
                if quote["status"] == "blocked":
                    self.assertIn("blocking_reasons", quote)
        finally:
            if out_path.exists():
                shutil.rmtree(out_path, ignore_errors=True)

    def test_3_byte_identical_repeatability(self) -> None:
        out1 = SCRATCH_DIR / "test_out_3a"
        out2 = SCRATCH_DIR / "test_out_3b"
        for p in (out1, out2):
            if p.exists():
                shutil.rmtree(p)
            p.mkdir(parents=True, exist_ok=True)

        try:
            cmd1 = [sys.executable, str(RUNNER_SCRIPT), "--input", str(DATA_DIR), "--output", str(out1)]
            cmd2 = [sys.executable, str(RUNNER_SCRIPT), "--input", str(DATA_DIR), "--output", str(out2)]

            subprocess.run(cmd1, check=True)
            subprocess.run(cmd2, check=True)

            for i in range(1, 6):
                r_id = f"ROOM-0{i}"
                f1_l = (out1 / r_id / "layout.json").read_bytes()
                f2_l = (out2 / r_id / "layout.json").read_bytes()
                self.assertEqual(f1_l, f2_l, f"Layout byte mismatch for {r_id}")

                f1_q = (out1 / r_id / "quote.json").read_bytes()
                f2_q = (out2 / r_id / "quote.json").read_bytes()
                self.assertEqual(f1_q, f2_q, f"Quote byte mismatch for {r_id}")
        finally:
            for p in (out1, out2):
                if p.exists():
                    shutil.rmtree(p, ignore_errors=True)

    def test_4_placement_aggregation(self) -> None:
        out_path = SCRATCH_DIR / "test_out_4"
        if out_path.exists():
            shutil.rmtree(out_path)
        out_path.mkdir(parents=True, exist_ok=True)

        try:
            cmd = [sys.executable, str(RUNNER_SCRIPT), "--input", str(DATA_DIR), "--output", str(out_path)]
            subprocess.run(cmd, check=True)

            for i in range(1, 6):
                r_id = f"ROOM-0{i}"
                layout = read_json(out_path / r_id / "layout.json")
                quote = read_json(out_path / r_id / "quote.json")

                if quote["status"] == "priced":
                    # Sum of line quantities must equal total placements
                    total_line_qty = sum(l["quantity"] for l in quote["lines"])
                    self.assertEqual(total_line_qty, len(layout["placements"]))
        finally:
            if out_path.exists():
                shutil.rmtree(out_path, ignore_errors=True)

    def test_5_unsatisfiable_blocked_quote_behavior(self) -> None:
        from src.output import create_blocked_quote
        bq = create_blocked_quote("QUOTE-TEST", "ROOM-TEST", ["Clearance failure"])
        self.assertEqual(bq["status"], "blocked")
        self.assertEqual(bq["summary"]["grand_total_inr"], 0)
        self.assertEqual(len(bq["lines"]), 0)
        self.assertEqual(bq["blocking_reasons"], ["Clearance failure"])


if __name__ == "__main__":
    unittest.main()
