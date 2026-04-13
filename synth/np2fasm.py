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
    # Skip primitive blackbox modules that prims.v contributes — pick
    # the first module that actually contains placed cells (i.e. the
    # design top). When none is present, fall back to the first
    # module so empty-input error handling downstream still works.
    BLACKBOX_MODULES = {
        "CE6_CARRY", "DFF", "LUT", "GENERIC_SLICE", "GENERIC_IOB",
    }
    mod_name = next(
        (m for m in modules if m not in BLACKBOX_MODULES),
        next(iter(modules)),
    )
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

    # Pre-compute CE6_CARRY cell set for chain analysis.
    carry_cells = {n: c for n, c in cells.items()
                   if c.get("type") == "CE6_CARRY"}

    # --- LUT / LUT_ARITH / DFF directives from cells ---
    has_dff = False
    dff_les: set[tuple[int, int, int]] = set()
    for cell_name, cell in cells.items():
        bel = cell_bel.get(cell_name)
        if bel is None:
            continue
        kind, x, y, n = bel
        ctype = cell.get("type", "")
        params = cell.get("parameters", {})

        if kind == "SLICE" and ctype == "CE6_CARRY":
            # Arith-mode LUT SRAM = 0x0000 for standard carry-chain
            # operations (+1, +, -). The block-band cells configure
            # dedicated XOR/AND circuitry that implements the adder
            # function independently of LUT SRAM content. Quartus
            # uses 0x0000 for all arith LEs (HW-verified 2026-04-13).
            fasm.append(f"X{x}Y{y}N{n}.LUT_ARITH = 0x0000")
        elif kind == "SLICE" and ctype in ("DFF", "$_DFF_P_"):
            # Yosys-level DFF cell placed on its own SLICE bel. In
            # Cyclone IV the FF lives inside the LE alongside the
            # LCCOMB/arith combinational part, so the DFF bel and the
            # matching LUT/CE6_CARRY bel should share the same (x,y,n).
            fasm.append(f"X{x}Y{y}N{n}.DFF")
            has_dff = True
            dff_les.add((x, y, n))
        elif kind == "SLICE":
            # Plain LUT (packed GENERIC_SLICE with INIT + FF_USED).
            init_bin = params.get("INIT", "")
            if init_bin:
                mask = int(init_bin, 2)
                if mask != 0:
                    fasm.append(f"X{x}Y{y}N{n}.LUT = 0x{mask:04x}")
            ff_bin = params.get("FF_USED", "0")
            if int(ff_bin, 2):
                fasm.append(f"X{x}Y{y}N{n}.DFF")
                has_dff = True
                dff_les.add((x, y, n))
        elif kind == "IOB":
            fasm.append(
                f"# IOB {cell.get('attributes',{}).get('NEXTPNR_BEL','?')}"
                f" (no FASM IO cell map yet)")

    # --- Carry chain analysis ---
    # Walk every CE6_CARRY whose CI is a Verilog constant — that's a
    # chain start. For each start, follow CO→CI until the chain ends
    # (either last cell or CO unconsumed), verify the bels are on
    # contiguous N slots (intra-LAB N→N+2 or N30→next LAB N0), and
    # emit a placeholder FASM comment for the chain-start CRAM bit
    # (the bit itself is a separate mining campaign — a $add vs
    # $sub diff is the planned experiment).
    #
    # Mid-chain CI connections use the dedicated silicon carry pip
    # in nextpnr's chipdb — no LI-MUX routing needed, and explicitly
    # skipped from the ROUTE pass below.
    if carry_cells:
        # bit_id -> cell_name whose CO drives it
        co_driver: dict[int, str] = {}
        for name, cell in carry_cells.items():
            co = cell.get("connections", {}).get("CO", [])
            if len(co) == 1 and not isinstance(co[0], str):
                co_driver[co[0]] = name

        def _ci_info(cell: dict) -> tuple[str, int | None]:
            ci = cell.get("connections", {}).get("CI", [])
            if len(ci) != 1:
                return ("unknown", None)
            v = ci[0]
            if isinstance(v, str):
                return ("const", int(v) if v in ("0", "1") else None)
            return ("net", v)

        # Find chain starts (constant CI)
        visited: set[str] = set()
        for start_name, start_cell in carry_cells.items():
            kind, val = _ci_info(start_cell)
            if kind != "const" or val is None:
                continue
            # Walk the chain from this start
            chain: list[str] = []
            cur = start_name
            while cur and cur not in visited:
                visited.add(cur)
                chain.append(cur)
                cell = carry_cells[cur]
                co = cell.get("connections", {}).get("CO", [])
                if len(co) != 1 or isinstance(co[0], str):
                    break
                co_net = co[0]
                # Next cell is the one whose CI == co_net
                nxt = None
                for n2, c2 in carry_cells.items():
                    if n2 in visited:
                        continue
                    k2, v2 = _ci_info(c2)
                    if k2 == "net" and v2 == co_net:
                        nxt = n2
                        break
                cur = nxt
            # Report the chain
            start_bel = cell_bel.get(chain[0])
            end_bel = cell_bel.get(chain[-1])
            warnings.append(
                f"chain: {len(chain)} cells, CI={val}, "
                f"start={start_bel}, end={end_bel}")
            if start_bel:
                _, sx, sy, sn = start_bel
                fasm.append(
                    f"# CHAIN_START X{sx}Y{sy}N{sn} CI={val}"
                    f"  (chain length {len(chain)}; "
                    f"chain-start CRAM bit not yet mined)")
            # Verify N-contiguity on the chain's placed bels
            placed = [cell_bel.get(c) for c in chain]
            if all(b and b[0] == "SLICE" for b in placed):
                for i in range(len(placed) - 1):
                    _, ax, ay, an = placed[i]
                    _, bx, by, bn = placed[i + 1]
                    ok = False
                    if (ax, ay) == (bx, by) and bn == an + 2:
                        ok = True            # within-LAB chain step
                    elif ax == bx and ay == by + 1 and an == 30 and bn == 0:
                        ok = True            # between-LAB N30→N0
                    if not ok:
                        warnings.append(
                            f"chain discontinuity: "
                            f"{chain[i]}@{placed[i]} → "
                            f"{chain[i + 1]}@{placed[i + 1]}")

        # Any CE6_CARRY not touched by a forward walk: orphan / cascaded
        for name in carry_cells:
            if name not in visited:
                warnings.append(
                    f"carry cell {name} not reached from any chain start "
                    f"(cascaded CI not supported)")

    # --- GCLK if any DFF is present ---
    if has_dff:
        fasm.append("GCLK")

    # --- ROUTE directives from logical connectivity ---
    # For each net, find driver bel and all sink bels+ports, then look up
    # the sig-cache for each (src→dst.port) arc.
    #
    # Build bit→cell mapping first.
    bit_driver: dict[int, tuple[str, str]] = {}   # bit_id → (cell_name, port)
    bit_sinks: dict[int, list[tuple[str, str, int]]] = {}  # bit_id → [(cell, port, idx)]

    # Blackbox cells (CE6_CARRY, LUT) from prims.v don't carry
    # port_directions in the JSON. Hardcode them so the net walker
    # can distinguish drivers from sinks.
    _BLACKBOX_DIRS = {
        "CE6_CARRY": {"A": "input", "B": "input", "CI": "input",
                       "S": "output", "CO": "output"},
        "LUT":       {"I": "input", "Q": "output"},
    }

    for cell_name, cell in cells.items():
        ctype = cell.get("type", "")
        conns = cell.get("connections", {})
        dirs = cell.get("port_directions", {})
        if not dirs and ctype in _BLACKBOX_DIRS:
            dirs = _BLACKBOX_DIRS[ctype]
        for port, port_bits in conns.items():
            # CE6_CARRY's CI/CO are routed via the dedicated silicon
            # carry pip, not LI MUX — skip from the sig-cache routing
            # pass entirely.
            if ctype == "CE6_CARRY" and port in ("CI", "CO"):
                continue
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

            # Intra-LE path: any connection within the same (x,y,n)
            # is LE-internal and needs no ROUTE. This covers:
            #   - LUT/CARRY → DFF (combinational output to register)
            #   - DFF.Q → CARRY input (LE-internal feedback in arith
            #     mode — Quartus carry counters have 0 external routes)
            if (sx, sy, sn) == (dx, dy, dn):
                continue

            # Map sink port to Cyclone IV input name. CE6_CARRY uses
            # named single-bit ports (A→dataa, B→datab); plain SLICE
            # LUT uses a 4-bit I[] vector indexed 0..3.
            sink_ctype = cells[sink_cell].get("type", "")
            if sink_ctype == "CE6_CARRY":
                port_name = {"A": "dataa", "B": "datab"}.get(sink_port)
                if port_name is None:
                    n_skip += 1
                    continue
            else:
                port_name = _IDX_TO_PORT.get(sink_idx)
                if port_name is None:
                    n_skip += 1
                    continue

            # Sig-cache lookup
            key = f"{sx},{sy},{sn}->{dx},{dy},{dn},{port_name}"
            if key in seen_routes:
                continue  # dedup
            seen_routes.add(key)

            fasm.append(
                f"ROUTE X{sx}Y{sy}N{sn} -> "
                f"X{dx}Y{dy}N{dn}.{port_name}")
            if _SIG_CACHE and key in _SIG_CACHE:
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
