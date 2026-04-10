#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.3 M4 — nextpnr-generic routed JSON to FASM converter.

Reads the placed-and-routed JSON emitted by nextpnr-generic (via
``chipdb_ep4ce6.py``) and emits FASM directives that ``fasm2rbf.py``
can consume to produce a CRC-valid EP4CE6 RBF.

The converter extracts **logical connectivity** from the placed netlist
(which source bel drives which sink bel input) and looks up each
(src→dst.port) pair in the Plan D' sig-cache.  This decouples FASM
generation from nextpnr's abstract routing topology — the chipdb's
LOCAL/INTRA_LAB overlay pips are invisible to this tool.

Supported directive output
--------------------------
* ``X{x}Y{y}N{n}.LUT = 0x{mask}`` — LUT truth table from cell INIT.
* ``ROUTE X{sx}Y{sy}N{sn} -> X{dx}Y{dy}N{dn}.{port}`` — physical
  route from sig-cache, emitted for every placed (src→dst) arc that
  has a sig-cache entry.

Usage
-----
::

    python3 synth/np2fasm.py routed.json > design.fasm
    python3 fuzz/fasm2rbf.py design.fasm base.rbf out.rbf
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FUZZ = HERE.parent / "fuzz"
sys.path.insert(0, str(FUZZ))

# Load sig-cache for ROUTE lookup
_SIG_CACHE: dict | None = None
_CACHE_PATH = HERE.parent / "results" / "route_cells_full.json"
if _CACHE_PATH.exists():
    _SIG_CACHE = json.loads(_CACHE_PATH.read_text())

# I[n] index → Cyclone IV port name
_IDX_TO_PORT = {0: "dataa", 1: "datab", 2: "datac", 3: "datad"}


def _parse_bel(bel_name: str) -> tuple[str, int, int, int] | None:
    """Parse 'SLICE_X3_Y19_N24' -> ('SLICE', 3, 19, 24)."""
    m = re.match(r"(SLICE|IOB|M9K)_X(\d+)_Y(\d+)_N(\d+)", bel_name)
    if not m:
        if bel_name.startswith("IOB_"):
            return ("IOB", 0, 0, 0)
        return None
    return (m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)))


def convert(routed_json: dict) -> tuple[list[str], list[str]]:
    """Convert routed JSON to (fasm_lines, warnings)."""
    fasm: list[str] = []
    warnings: list[str] = []

    modules = routed_json.get("modules", {})
    if not modules:
        warnings.append("ERROR: no modules in JSON")
        return fasm, warnings
    mod_name = next(iter(modules))
    mod = modules[mod_name]
    cells = mod.get("cells", {})
    nets = mod.get("netnames", {})

    # Build bel placement map: cell_name -> (kind, x, y, n)
    cell_bel: dict[str, tuple[str, int, int, int]] = {}
    for cell_name, cell in cells.items():
        bel_str = cell.get("attributes", {}).get("NEXTPNR_BEL", "")
        bel = _parse_bel(bel_str)
        if bel:
            cell_bel[cell_name] = bel

    # --- LUT / DFF directives from cells ---
    for cell_name, cell in cells.items():
        bel = cell_bel.get(cell_name)
        if bel is None:
            continue
        kind, x, y, n = bel
        params = cell.get("parameters", {})

        if kind == "SLICE":
            init_bin = params.get("INIT", "")
            if init_bin:
                mask = int(init_bin, 2)
                if mask != 0:
                    fasm.append(f"X{x}Y{y}N{n}.LUT = 0x{mask:04x}")
            ff_bin = params.get("FF_USED", "0")
            if int(ff_bin, 2):
                fasm.append(f"# DFF at X{x}Y{y}N{n} (no FASM directive yet)")
        elif kind == "IOB":
            fasm.append(
                f"# IOB {cell.get('attributes',{}).get('NEXTPNR_BEL','?')}"
                f" (no FASM IO cell map yet)")

    # --- ROUTE directives from logical connectivity ---
    # For each net, find driver bel and all sink bels+ports, then look up
    # the sig-cache for each (src→dst.port) arc.
    #
    # Build bit→cell mapping first.
    bit_driver: dict[int, tuple[str, str]] = {}   # bit_id → (cell_name, port)
    bit_sinks: dict[int, list[tuple[str, str, int]]] = {}  # bit_id → [(cell, port, idx)]

    for cell_name, cell in cells.items():
        conns = cell.get("connections", {})
        dirs = cell.get("port_directions", {})
        for port, port_bits in conns.items():
            d = dirs.get(port, "")
            for idx, bit_id in enumerate(port_bits):
                if isinstance(bit_id, str):  # constant "0"/"1"
                    continue
                if d == "output":
                    bit_driver[bit_id] = (cell_name, port)
                elif d == "input":
                    bit_sinks.setdefault(bit_id, []).append(
                        (cell_name, port, idx))

    n_sig = 0
    n_miss = 0
    n_skip = 0
    seen_routes: set[str] = set()

    for bit_id, (drv_cell, drv_port) in bit_driver.items():
        drv_bel = cell_bel.get(drv_cell)
        if drv_bel is None or drv_bel[0] != "SLICE":
            continue
        _, sx, sy, sn = drv_bel

        for sink_cell, sink_port, sink_idx in bit_sinks.get(bit_id, []):
            sink_bel = cell_bel.get(sink_cell)
            if sink_bel is None or sink_bel[0] != "SLICE":
                n_skip += 1
                continue
            _, dx, dy, dn = sink_bel

            # Map I[n] index to port name
            port_name = _IDX_TO_PORT.get(sink_idx)
            if port_name is None:
                n_skip += 1
                continue

            # Sig-cache lookup
            key = f"{sx},{sy},{sn}->{dx},{dy},{dn},{port_name}"
            if key in seen_routes:
                continue  # dedup
            seen_routes.add(key)

            if _SIG_CACHE and key in _SIG_CACHE:
                sn_part = f"N{sn}" if sn != 0 else ""
                fasm.append(
                    f"ROUTE X{sx}Y{sy}{sn_part} -> "
                    f"X{dx}Y{dy}N{dn}.{port_name}")
                n_sig += 1
            else:
                n_miss += 1
                warnings.append(f"no sig-cache: {key}")

    warnings.insert(0,
        f"# {n_sig} ROUTE (FASM-backed), {n_miss} missing, "
        f"{n_skip} skipped (non-slice/CLK)")

    return fasm, warnings


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <routed.json> [output.fasm]",
              file=sys.stderr)
        sys.exit(1)

    routed = json.loads(Path(sys.argv[1]).read_text())
    fasm_lines, warnings = convert(routed)

    out = sys.stdout
    if len(sys.argv) >= 3:
        out = open(sys.argv[2], "w")

    out.write("# Auto-generated by np2fasm.py\n")
    for w in warnings:
        out.write(f"# WARN: {w}\n")
    out.write("\n")
    for line in fasm_lines:
        out.write(line + "\n")

    if out is not sys.stdout:
        out.close()
        print(f"Wrote {len(fasm_lines)} FASM lines to {sys.argv[2]}",
              file=sys.stderr)
        for w in warnings:
            print(f"  {w}", file=sys.stderr)


if __name__ == "__main__":
    main()
