#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.3 M4 — nextpnr-generic routed JSON to FASM converter.

Reads the placed-and-routed JSON emitted by nextpnr-generic (via
``chipdb_ep4ce6.py``) and emits FASM directives that ``fasm2rbf.py``
can consume to produce a CRC-valid EP4CE6 RBF.

Supported directive output
--------------------------
* ``X{x}Y{y}N{n}.LUT = 0x{mask}`` — LUT truth table from cell INIT.
* ``ROUTE X{sx}Y{sy}N{sn} -> X{dx}Y{dy}N{dn}.{port}`` — inter-LAB
  routes backed by the Plan D' sig-cache. Only emitted when the pip
  used by nextpnr matches a sig-cache entry.

Unsupported (reported as warnings)
-----------------------------------
* LOCAL/INTRA_LAB/GCLK/IOB pips — overlay infrastructure with no CRAM
  backing. These require either placement into sig-cache-covered LABs
  or a future ``route_synth`` integration.
* M9K INIT — not yet wired (needs M9K bel usage + anchor table).
* IO pin configuration — ``fasm2rbf`` doesn't have IO cell CRAM maps.

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

# Try to load sig-cache for ROUTE pip validation
_SIG_CACHE: dict | None = None
_CACHE_PATH = HERE.parent / "results" / "route_cells_full.json"
if _CACHE_PATH.exists():
    _SIG_CACHE = json.loads(_CACHE_PATH.read_text())


def _parse_bel(bel_name: str) -> tuple[str, int, int, int] | None:
    """Parse 'SLICE_X3_Y19_N24' -> ('SLICE', 3, 19, 24)."""
    m = re.match(r"(SLICE|IOB|M9K)_X(\d+)_Y(\d+)_N(\d+)", bel_name)
    if not m:
        # IOB format: IOB_D_PIN_E15
        if bel_name.startswith("IOB_"):
            return ("IOB", 0, 0, 0)
        return None
    return (m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)))


def _parse_pip(pip_name: str) -> dict | None:
    """Try to extract (sx,sy,sn,dx,dy,dn,port) from a SIG pip name.

    SIG pips are named: pip_{sx}_{sy}_{sn}__{dx}_{dy}_{dn}_{port}
    """
    m = re.match(
        r"pip_(\d+)_(\d+)_(\d+)__(\d+)_(\d+)_(\d+)_(\w+)", pip_name
    )
    if not m:
        return None
    return {
        "sx": int(m.group(1)), "sy": int(m.group(2)), "sn": int(m.group(3)),
        "dx": int(m.group(4)), "dy": int(m.group(5)), "dn": int(m.group(6)),
        "port": m.group(7),
    }


def convert(routed_json: dict) -> tuple[list[str], list[str]]:
    """Convert routed JSON to (fasm_lines, warnings)."""
    fasm: list[str] = []
    warnings: list[str] = []

    # Find the single module
    modules = routed_json.get("modules", {})
    if not modules:
        warnings.append("ERROR: no modules in JSON")
        return fasm, warnings
    mod_name = next(iter(modules))
    mod = modules[mod_name]
    cells = mod.get("cells", {})
    nets = mod.get("netnames", {})

    # --- LUT / DFF directives from cells ---
    for cell_name, cell in cells.items():
        attrs = cell.get("attributes", {})
        params = cell.get("parameters", {})
        bel_str = attrs.get("NEXTPNR_BEL", "")
        bel = _parse_bel(bel_str)
        if bel is None:
            continue

        kind, x, y, n = bel

        if kind == "SLICE":
            init_bin = params.get("INIT", "")
            if init_bin:
                mask = int(init_bin, 2)
                if mask != 0:  # skip zero-init LUTs (GND driver etc.)
                    fasm.append(f"X{x}Y{y}N{n}.LUT = 0x{mask:04x}")
            ff_bin = params.get("FF_USED", "0")
            if int(ff_bin, 2):
                fasm.append(f"# DFF at X{x}Y{y}N{n} (no FASM directive yet)")

        elif kind == "IOB":
            fasm.append(f"# IOB {bel_str} (no FASM IO cell map yet)")

    # --- ROUTE directives from net routing ---
    n_sig = 0
    n_local = 0
    for net_name, net in nets.items():
        attrs = net.get("attributes", {})
        routing = attrs.get("ROUTING", "")
        if not routing:
            continue

        segs = routing.split(";")
        for seg in segs:
            if not seg.startswith("pip_"):
                continue

            sig = _parse_pip(seg)
            if sig is not None:
                # Check sig-cache
                key = (f"{sig['sx']},{sig['sy']},{sig['sn']}"
                       f"->{sig['dx']},{sig['dy']},{sig['dn']},"
                       f"{sig['port']}")
                if _SIG_CACHE and key in _SIG_CACHE:
                    sn_part = (f"N{sig['sn']}" if sig['sn'] != 0
                               else "")
                    fasm.append(
                        f"ROUTE X{sig['sx']}Y{sig['sy']}{sn_part} -> "
                        f"X{sig['dx']}Y{sig['dy']}N{sig['dn']}."
                        f"{sig['port']}"
                    )
                    n_sig += 1
                else:
                    warnings.append(
                        f"SIG pip not in cache: {key} (net {net_name})"
                    )
            else:
                n_local += 1

    # Summary
    warnings.insert(0,
        f"# {n_sig} SIG pips (FASM-backed), "
        f"{n_local} local/overlay pips (no FASM backing)")

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

    # Write FASM
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
