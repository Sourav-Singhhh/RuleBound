"""
Minimal Isolated Azure HTTP Wrapper for RuleBound Engine.
Pure Python 3 standard library with zero external dependencies.
Fronted by Azure App Service Authentication (Easy Auth) with Microsoft Entra ID.

Endpoints:
- GET  /health           -> {"status": "healthy", "service": "rulebound-azure-api"}
- POST /api/v1/solve     -> Receives {"room_id": "ROOM-02"} or raw room specification,
                            executes generator -> constraints -> arbitration -> pricing,
                            and returns schema-valid layout and quote JSON.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from starter.python.rulebound_loader import load_asset_pack
from src.arbitration import ArbitrationEngine
from src.constraints import ConstraintEngine
from src.generator import GeneratorEngine
from src.pricing import PricingEngine


def solve_room_payload(data_dir: Path, room_id: str, custom_room_spec: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Executes the deterministic RuleBound pipeline for a given room.
    """
    pack = load_asset_pack(str(data_dir))
    rules_list = pack.rules.get("rules", []) if isinstance(pack.rules, dict) else pack.rules

    room_spec = custom_room_spec or next((r for r in pack.rooms if r.get("room_id") == room_id), None)
    if not room_spec:
        raise ValueError(f"Room {room_id} not found in data pack.")

    brief_text = pack.briefs.get(room_id, "")

    gen = GeneratorEngine(pack.catalog, pack.finishes, rules_list, pack.historical_jobs)
    ce = ConstraintEngine(pack.catalog, pack.finishes, rules_list)
    arb = ArbitrationEngine(pack.catalog, pack.finishes, rules_list, ce)
    pricing = PricingEngine(pack.catalog, pack.finishes)

    # 1. Generate proposal
    proposal_dict = gen.generate_proposal(room_spec, brief_text)

    # 2. Arbitrate violations with brief metadata
    room_with_meta = dict(room_spec)
    item_counts = gen.parse_furniture_counts(brief_text, room_spec.get("capacity", 1))
    room_with_meta["required_workstations"] = item_counts.get("desk", 0)
    room_with_meta["required_storage"] = item_counts.get("storage", 0)
    room_with_meta["required_collaboration"] = item_counts.get("collaboration", 0)
    room_with_meta["required_accessory"] = item_counts.get("accessory", 0)
    room_with_meta["brief_text"] = brief_text

    arbitrated_layout = arb.arbitrate(proposal_dict, room_with_meta)

    # 3. Final revalidation
    if arbitrated_layout.get("status") == "valid":
        final_layout = ce.validate_layout(arbitrated_layout, room_spec)
    else:
        final_layout = arbitrated_layout

    status = final_layout.get("status", "invalid")
    violations = final_layout.get("violations", [])
    final_placements = final_layout.get("placements", [])

    layout_json = {
        "room_id": room_id,
        "status": status,
        "placements": final_placements,
        "violations": violations
    }

    # 3. Deterministic pricing
    if status == "valid":
        groups = {}
        for p in final_placements:
            k = (p["sku"], p["finish_id"])
            groups[k] = groups.get(k, 0) + 1
        lines = [
            {"line_id": f"L{idx+1:03d}", "sku": sku, "finish_id": fid, "quantity": qty}
            for idx, ((sku, fid), qty) in enumerate(sorted(groups.items()))
        ]
        quote_json = pricing.calculate_quote(f"Q-{room_id}", room_id, lines)
    else:
        blocking = [f"Unresolved spatial violations ({len(violations)} remaining)."]
        quote_json = {
            "quote_id": f"Q-{room_id}",
            "room_id": room_id,
            "status": "blocked",
            "currency": "INR",
            "lines": [],
            "summary": {
                "total_goods_inr": 0,
                "total_labour_inr": 0,
                "total_freight_inr": 0,
                "grand_total_inr": 0,
                "discount_bps": 0,
                "freight_distance_band": "standard",
                "total_items": 0,
                "priced_items": 0
            },
            "summary_trace": [],
            "blocking_reasons": blocking
        }

    return {
        "room_id": room_id,
        "layout": layout_json,
        "quote": quote_json
    }


class RuleBoundHTTPHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, data: Dict[str, Any]) -> None:
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path in ("/", "/health"):
            # When Azure Easy Auth is active, user claims appear in X-MS-CLIENT-PRINCIPAL-NAME
            user_principal = self.headers.get("X-MS-CLIENT-PRINCIPAL-NAME", "anonymous")
            self._send_json(200, {
                "status": "healthy",
                "service": "RuleBound Azure Service",
                "authenticated_user": user_principal,
                "auth_provider": "Microsoft Entra ID (Easy Auth)"
            })
        else:
            self._send_json(404, {"error": "Not Found", "path": self.path})

    def do_POST(self) -> None:
        if self.path == "/api/v1/solve":
            content_len = int(self.headers.get("Content-Length", 0))
            if content_len == 0:
                self._send_json(400, {"error": "Empty request body"})
                return

            raw_body = self.rfile.read(content_len).decode("utf-8")
            try:
                payload = json.loads(raw_body)
            except json.JSONDecodeError as exc:
                self._send_json(400, {"error": "Malformed JSON", "details": str(exc)})
                return

            room_id = payload.get("room_id", "ROOM-02")
            custom_room_spec = payload.get("room_spec")
            data_dir = REPO_ROOT / "data"

            try:
                result = solve_room_payload(data_dir, room_id, custom_room_spec)
                self._send_json(200, result)
            except Exception as exc:
                self._send_json(500, {"error": "Internal Solver Error", "details": str(exc)})
        else:
            self._send_json(404, {"error": "Endpoint Not Found", "path": self.path})


def run_server(port: int = 8000) -> None:
    server_addr = ("0.0.0.0", port)
    httpd = HTTPServer(server_addr, RuleBoundHTTPHandler)
    print(f"RuleBound Azure Service listening on port {port}...")
    httpd.serve_forever()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    run_server(port)
