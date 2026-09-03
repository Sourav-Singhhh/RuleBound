"""
Standalone DXF Exporter for RuleBound (Bonus Feature: +5 points).
Generates standard AutoCAD ASCII DXF (Release 12 / 2000 compatible) floor plan drawings from
validated layout.json and room specification files.

Pure Python 3 standard library with zero external dependencies.
Does NOT modify core generator, constraints, arbitration, or pricing engines.
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple


# Standard AutoCAD Color Index (ACI)
COLOR_WALLS = 7        # White / Black
COLOR_DOORS = 1        # Red
COLOR_EGRESS = 4       # Cyan
COLOR_DESKS = 3        # Green
COLOR_CHAIRS = 2       # Yellow
COLOR_STORAGE = 6      # Magenta
COLOR_COLLAB = 5       # Blue
COLOR_ACCESSORIES = 8  # Gray
COLOR_DEFAULT = 7


def create_dxf_header() -> str:
    """Creates minimum standard DXF header section."""
    return (
        "0\nSECTION\n"
        "2\nHEADER\n"
        "9\n$ACADVER\n1\nAC1009\n"  # AutoCAD R12 ASCII DXF
        "0\nENDSEC\n"
    )


def create_dxf_tables() -> str:
    """Defines color-coded standard CAD layers."""
    layers = [
        ("WALLS", COLOR_WALLS),
        ("DOORS", COLOR_DOORS),
        ("EGRESS", COLOR_EGRESS),
        ("DESKS", COLOR_DESKS),
        ("CHAIRS", COLOR_CHAIRS),
        ("STORAGE", COLOR_STORAGE),
        ("COLLABORATION", COLOR_COLLAB),
        ("ACCESSORIES", COLOR_ACCESSORIES),
    ]
    lines = [
        "0\nSECTION\n",
        "2\nTABLES\n",
        "0\nTABLE\n",
        "2\nLAYER\n",
        f"70\n{len(layers)}\n",
    ]
    for name, col in layers:
        lines.append(
            f"0\nLAYER\n"
            f"2\n{name}\n"
            f"70\n0\n"
            f"62\n{col}\n"
            f"6\nCONTINUOUS\n"
        )
    lines.append("0\nENDTAB\n0\nENDSEC\n")
    return "".join(lines)


def dxf_polyline_2d(pts: Sequence[Tuple[int, int]], layer: str, closed: bool = True) -> str:
    """Generates 2D POLYLINE / VERTEX entities."""
    lines = [
        "0\nPOLYLINE\n",
        f"8\n{layer}\n",
        "66\n1\n",
        f"70\n{1 if closed else 0}\n",
    ]
    for x, y in pts:
        lines.append(
            f"0\nVERTEX\n"
            f"8\n{layer}\n"
            f"10\n{float(x):.2f}\n"
            f"20\n{float(y):.2f}\n"
            f"30\n0.0\n"
        )
    lines.append("0\nSEQEND\n")
    return "".join(lines)


def dxf_line_2d(x1: int, y1: int, x2: int, y2: int, layer: str) -> str:
    """Generates standard LINE entity."""
    return (
        "0\nLINE\n"
        f"8\n{layer}\n"
        f"10\n{float(x1):.2f}\n"
        f"20\n{float(y1):.2f}\n"
        f"30\n0.0\n"
        f"11\n{float(x2):.2f}\n"
        f"21\n{float(y2):.2f}\n"
        f"31\n0.0\n"
    )


def dxf_text_2d(x: int, y: int, height: int, text: str, layer: str) -> str:
    """Generates standard TEXT entity."""
    return (
        "0\nTEXT\n"
        f"8\n{layer}\n"
        f"10\n{float(x):.2f}\n"
        f"20\n{float(y):.2f}\n"
        f"30\n0.0\n"
        f"40\n{float(height):.2f}\n"
        f"1\n{text}\n"
    )


def export_room_to_dxf(
    layout_data: Dict[str, Any],
    room_spec: Dict[str, Any],
    catalog_map: Dict[str, Any]
) -> str:
    """Converts a room spec and layout into a complete ASCII DXF document."""
    dxf_parts = [
        create_dxf_header(),
        create_dxf_tables(),
        "0\nSECTION\n2\nENTITIES\n",
    ]

    # 1. Room Boundary Polygon (WALLS layer)
    boundary = room_spec.get("boundary_mm", [])
    if boundary:
        pts = [(int(p[0]), int(p[1])) for p in boundary]
        dxf_parts.append(dxf_polyline_2d(pts, "WALLS", closed=True))

    # 2. Doors (DOORS layer)
    doors = room_spec.get("doors", [])
    max_x = max(p[0] for p in boundary) if boundary else 6000
    max_y = max(p[1] for p in boundary) if boundary else 6000
    for d in doors:
        wall = d.get("wall")
        off = d.get("offset_mm", 0)
        dw = d.get("width_mm", 900)
        if wall == "south":
            x1, y1, x2, y2 = off, 0, off + dw, 0
        elif wall == "north":
            x1, y1, x2, y2 = off, max_y, off + dw, max_y
        elif wall == "west":
            x1, y1, x2, y2 = 0, off, 0, off + dw
        else:
            x1, y1, x2, y2 = max_x, off, max_x, off + dw
        dxf_parts.append(dxf_line_2d(x1, y1, x2, y2, "DOORS"))
        dxf_parts.append(dxf_text_2d((x1 + x2) // 2, (y1 + y2) // 2 + 50, 150, d.get("door_id", "DOOR"), "DOORS"))

    # 3. Egress Path (EGRESS layer)
    egress = room_spec.get("egress", {})
    if egress and egress.get("to_point_mm"):
        from_door_id = egress.get("from_door_id")
        door_obj = next((d for d in doors if d.get("door_id") == from_door_id), doors[0] if doors else None)
        if door_obj:
            wall = door_obj.get("wall")
            off = door_obj.get("offset_mm", 0)
            dw = door_obj.get("width_mm", 900)
            if wall == "south":
                dc = (off + dw // 2, 0)
            elif wall == "north":
                dc = (off + dw // 2, max_y)
            elif wall == "west":
                dc = (0, off + dw // 2)
            else:
                dc = (max_x, off + dw // 2)
            tx, ty = egress["to_point_mm"]
            dxf_parts.append(dxf_line_2d(dc[0], dc[1], tx, ty, "EGRESS"))

    # 4. Furniture Placements
    for p in layout_data.get("placements", []):
        sku = p.get("sku", "")
        cat_item = catalog_map.get(sku, {})
        fam = cat_item.get("family", "desk").lower()
        dims = cat_item.get("dimensions_mm", {"width": 1000, "depth": 600})
        w = dims.get("width", 1000)
        d = dims.get("depth", 600)
        x = p.get("x_mm", 0)
        y = p.get("y_mm", 0)
        rot = p.get("rotation_deg", 0) % 360

        if rot in (90, 270):
            eff_w, eff_d = d, w
        else:
            eff_w, eff_d = w, d

        # Layer assignment based on family
        if fam == "desk":
            layer = "DESKS"
        elif fam == "chair":
            layer = "CHAIRS"
        elif fam == "storage":
            layer = "STORAGE"
        elif fam == "collaboration":
            layer = "COLLABORATION"
        elif fam == "accessory":
            layer = "ACCESSORIES"
        else:
            layer = "DESKS"

        # Bounding box polygon
        box_pts = [
            (x, y),
            (x + eff_w, y),
            (x + eff_w, y + eff_d),
            (x, y + eff_d),
        ]
        dxf_parts.append(dxf_polyline_2d(box_pts, layer, closed=True))
        label = p.get("placement_id", sku)
        dxf_parts.append(dxf_text_2d(x + 50, y + eff_d // 2, min(100, eff_d // 3), label, layer))

    dxf_parts.append("0\nENDSEC\n0\nEOF\n")
    return "".join(dxf_parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="RuleBound DXF Floor Plan Exporter (+5 Bonus)")
    parser.add_argument("--input", default="data", help="Path to data pack directory")
    parser.add_argument("--output", default="OUTPUT", help="Path to OUTPUT directory with layout.json files")
    parser.add_argument("--dxf-dir", default="DXF_OUTPUT", help="Output directory for generated .dxf files")
    args = parser.parse_args()

    data_dir = Path(args.input)
    output_dir = Path(args.output)
    dxf_out = Path(args.dxf_dir)
    dxf_out.mkdir(parents=True, exist_ok=True)

    catalog_file = data_dir / "catalog.json"
    if not catalog_file.exists():
        print(f"Error: Catalog not found at {catalog_file}")
        sys.exit(1)

    catalog_data = json.loads(catalog_file.read_text(encoding="utf-8"))
    catalog_map = {item["sku"]: item for item in catalog_data}

    exported_count = 0
    for r_dir in sorted(output_dir.glob("ROOM-*")):
        layout_file = r_dir / "layout.json"
        rid = r_dir.name
        room_file = data_dir / "rooms" / f"{rid}.json"

        if layout_file.exists() and room_file.exists():
            layout_data = json.loads(layout_file.read_text(encoding="utf-8"))
            room_spec = json.loads(room_file.read_text(encoding="utf-8"))

            dxf_content = export_room_to_dxf(layout_data, room_spec, catalog_map)
            out_file = dxf_out / f"{rid}.dxf"
            out_file.write_text(dxf_content, encoding="utf-8")
            print(f"Exported DXF: {out_file} (Status: {layout_data.get('status')}, Placements: {len(layout_data.get('placements', []))})")
            exported_count += 1

    print(f"\nSuccessfully exported {exported_count} DXF drawings to {dxf_out}/")


if __name__ == "__main__":
    main()
