"""L3 step 2-4 — routing transplant surgery on lits_l3_base.rbf.

  2. Strip   — read every active C4/R4/R24/LI cell from the Quartus
               baseline and XOR-clear them via 'raw' ops, producing a
               logic-intact / routing-blank stripped RBF.
  3. Graft   — call synth_route() with the stripped RBF as its zero
               baseline so our 11 synthesized cells (9 LI envelope +
               2 src driver) get written into a still-functional logic
               surround.
  4. Diff    — cell-set compare grafted vs original Quartus baseline
               using the stripped RBF as the common reference, so LUT
               TT bits cancel and only routing differences show.

All offline; no hardware needed. Run before flashing AX301.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import re
from collections import defaultdict
from pathlib import Path

from bitstream import RouteCodec
from route_synth import synth_route

ROOT = Path(__file__).resolve().parent.parent
RBF_DIR = ROOT / "results" / "rbf"
BASE = RBF_DIR / "lits_l3_base.rbf"
STRIPPED = RBF_DIR / "lits_l3_stripped.rbf"
GRAFTED = RBF_DIR / "lits_l3_grafted.rbf"
ZERO = RBF_DIR / "lits_l3_zero.rbf"  # logic-matched zero — same skeleton, no signal

SRC = (10, 10)
DST = (12, 10)


def cells_of(codec, rbf, baseline):
    sw = codec.read_switches(rbf, baseline)
    out = set()
    for t, lst in sw.items():
        for e in lst:
            out.add((t, e[0], e[1], e[2]))
    return out


_NAME_RE = re.compile(r"_X(\d+)_Y(\d+)")


def in_corridor(name, src, dst, pad=1):
    m = _NAME_RE.search(name)
    if not m:
        return False
    x, y = int(m.group(1)), int(m.group(2))
    xlo, xhi = min(src[0], dst[0]) - pad, max(src[0], dst[0]) + pad
    ylo, yhi = min(src[1], dst[1]) - pad, max(src[1], dst[1]) + pad
    return xlo <= x <= xhi and ylo <= y <= yhi


def filter_corridor(cells, src, dst, pad=1):
    return {c for c in cells if in_corridor(c[1], src, dst, pad)}


def by_type(s):
    d = defaultdict(int)
    for t, *_ in s:
        d[t] += 1
    return dict(d)


def main():
    if not BASE.exists():
        print(f"missing {BASE} — run compile_l3_baseline.py first")
        return 1
    if not ZERO.exists():
        print(f"missing zero baseline {ZERO}")
        return 1

    codec = RouteCodec()
    base = BASE.read_bytes()
    zero = ZERO.read_bytes()

    # ---- step 2: strip routing from base ----
    sw = codec.read_switches(base, zero)
    strip_ops = []
    n_by_t = defaultdict(int)
    for t, lst in sw.items():
        for e in lst:
            off, bp = e[1], e[2]
            strip_ops.append({"type": "raw", "offset": off, "bp": bp, "value": False})
            n_by_t[t] += 1
    print(f"step 2 strip: {dict(n_by_t)}  total={len(strip_ops)} cells to clear")

    # apply_routing uses its first arg as BOTH the buffer and the zero
    # reference, so we have to strip by hand against the real zero baseline.
    buf = bytearray(base)
    for op in strip_ops:
        codec._set_bit(buf, zero, op["offset"], op["bp"], False)
    stripped = bytes(buf)
    STRIPPED.write_bytes(stripped)

    # sanity: stripped should report 0 routing cells vs zero
    sw_check = codec.read_switches(stripped, zero)
    n_check = {t: len(v) for t, v in sw_check.items()}
    print(f"  stripped read-back vs zero: {n_check}")

    # ---- step 3: graft synthesized routing ----
    grafted, dbg = synth_route(stripped, SRC, DST)
    GRAFTED.write_bytes(grafted)
    print(f"step 3 graft: {len(dbg['ops'])} ops, plan={[repr(h) for h in dbg['plan']]}")
    print(f"  li_mode={dbg['li_mode']}")

    # ---- step 4: diff vs original Quartus baseline ----
    # Use stripped as the common reference so non-routing CRAM cancels.
    g_cells = cells_of(codec, grafted, stripped)
    q_cells = cells_of(codec, base, stripped)

    inter = g_cells & q_cells
    g_only = g_cells - q_cells
    q_only = q_cells - g_cells

    # Apply corridor filter — strip the I/O-pin and constant-network noise
    g_cells = filter_corridor(g_cells, SRC, DST, pad=1)
    q_cells = filter_corridor(q_cells, SRC, DST, pad=1)
    inter = g_cells & q_cells
    g_only = g_cells - q_cells
    q_only = q_cells - g_cells
    print(f"\nstep 4 cell-set diff (relative to stripped, CORRIDOR-FILTERED):")
    print(f"  grafted total : {len(g_cells)}  by type {by_type(g_cells)}")
    print(f"  quartus total : {len(q_cells)}  by type {by_type(q_cells)}")
    print(f"  intersection  : {len(inter)}  by type {by_type(inter)}")
    print(f"  graft_only    : {len(g_only)}  by type {by_type(g_only)}")
    print(f"  quartus_only  : {len(q_only)}  by type {by_type(q_only)}")

    if g_only:
        print("\n  graft_only samples (first 8):")
        for c in sorted(g_only)[:8]:
            print(f"    {c}")
    if q_only:
        print("\n  quartus_only samples (first 8):")
        for c in sorted(q_only)[:8]:
            print(f"    {c}")

    print(f"\nwrote: {STRIPPED.name}, {GRAFTED.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
