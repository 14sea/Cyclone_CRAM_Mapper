#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Option 2 STEP 0 — routing-model coverage gate (go/no-go).

Software-only (no Quartus, no flash).  For each routing switch class
(C4 I=0, C4 I≠0, R4, R24, LI), enumerate the (off, bp) cells the codec's
read/write model TARGETS across the whole chip and classify each:

    CRC      — (off-32) % 210 >= 208  → overwritten by patch_rbf_crc, DEAD
    HEADER   — off < 5282 (header band, off-32 frame < 25)
    CRAM     — real fabric config cell (off >= 5282, non-CRC)  → emittable

Go/no-go for Option 2 (real wire classes): a class whose model targets only
CRC/HEADER bytes has NO real CRAM model — it must be re-mined from scratch
before it can be represented in a routing graph.  A class targeting real
CRAM has a foundation to build on.

This operationalises the scoping-doc finding (verified vs bitstream.py
DEPRECATED comments): R24 / C4 I≠0 / FF write tables are 100% CRC.  Here we
quantify every class uniformly and emit the gate verdict.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "fuzz"))

import bitstream as bs  # noqa: E402
from bitstream import RouteCodec, _LI_CELL_TO_LAB  # noqa: E402
from config import LAB_X, LAB_Y, COLUMN_BASE  # noqa: E402

PRE = 32
FRAME = 210
FDATA = 208
HDR_END = 5282  # off < 5282 == header frames 0..24


def classify(off: int) -> str:
    if off < HDR_END:
        return "HEADER"
    if (off - PRE) % FRAME >= FDATA:
        return "CRC"
    return "CRAM"


def enumerate_class_offsets():
    """Return {class_name: set((off,bp))} that each model targets chip-wide."""
    rc = RouteCodec()
    out = {k: set() for k in
           ("C4_I0", "C4_Inz", "R4", "R24", "LI")}

    # --- C4 I=0: _LAB_CRAM_END[x] + _C4_SLOT_BASE[slot] + 3*group ---
    for x in LAB_X:
        if x not in bs._LAB_CRAM_END:
            continue
        for y in rc.C4_Y_RANGE:
            group, slot, bp = bs._cram_group_bit(y)
            off = bs._LAB_CRAM_END[x] + bs._C4_SLOT_BASE[slot] + 3 * group
            out["C4_I0"].add((off, bp))

    # --- C4 I≠0: _C4_FIXED_OFFSETS[(wx,ii)] ---
    for (wx, ii), byte_off in bs._C4_FIXED_OFFSETS.items():
        for y in rc.C4_Y_RANGE:
            _, _, bp = bs._cram_group_bit(y)
            out["C4_Inz"].add((byte_off, bp))

    # --- R4: col_start(prev) + base (base1/base2 per i_idx) ---
    for i_idx, (b1, b2) in bs._R4_BASE_PREV.items():
        for wx in rc.R4_X_RANGE:
            prev_x = rc._prev_lab_x(wx)
            if prev_x is None or prev_x not in COLUMN_BASE:
                continue
            col_start = COLUMN_BASE[prev_x] - 136
            for y in LAB_Y:
                _, _, bp = bs._cram_group_bit(y)
                for base in (b1, b2):
                    out["R4"].add((col_start + base, bp))

    # --- R24: col_start(prev) + fixed_off ---
    for i_idx, offsets in bs._R24_FIXED_OFFSETS.items():
        for wx in rc.R24_X_RANGE:
            prev_x = rc._prev_lab_x(wx)
            if prev_x is None or prev_x not in COLUMN_BASE:
                continue
            col_start = COLUMN_BASE[prev_x] - 136
            for y in LAB_Y:
                _, _, bp = bs._cram_group_bit(y)
                for fo in offsets:
                    out["R24"].add((col_start + fo, bp))

    # --- LI: reverse map already enumerated chip-wide ---
    for (off, bp) in _LI_CELL_TO_LAB:
        out["LI"].add((off, bp))

    return out


def main():
    print("=== Option 2 STEP 0 — routing-model coverage gate ===\n")
    cls = enumerate_class_offsets()
    print(f"{'class':<8} {'targets':>8} {'CRAM':>8} {'CRC':>8} {'HEADER':>8}   verdict")
    print("-" * 64)
    verdicts = {}
    for name in ("C4_I0", "C4_Inz", "R4", "R24", "LI"):
        cells = cls[name]
        n = len(cells)
        if n == 0:
            print(f"{name:<8} {0:>8}   (no targets)")
            verdicts[name] = "EMPTY"
            continue
        c = {"CRAM": 0, "CRC": 0, "HEADER": 0}
        for off, bp in cells:
            c[classify(off)] += 1
        cram_pct = 100 * c["CRAM"] / n
        if c["CRAM"] == 0:
            v = "DEAD (no CRAM — re-mine from scratch)"
        elif cram_pct >= 90:
            v = "REAL (CRAM-targeting)"
        else:
            v = f"MIXED ({cram_pct:.0f}% CRAM)"
        verdicts[name] = v
        print(f"{name:<8} {n:>8} {c['CRAM']:>8} {c['CRC']:>8} {c['HEADER']:>8}   {v}")

    print("\n=== GO/NO-GO ===")
    real = [k for k, v in verdicts.items() if v.startswith("REAL")]
    mixed = [k for k, v in verdicts.items() if v.startswith("MIXED")]
    dead = [k for k, v in verdicts.items() if v.startswith("DEAD")]
    print(f"  REAL  (foundation exists):    {real}")
    print(f"  MIXED (partial, needs work):  {mixed}")
    print(f"  DEAD  (re-mine from scratch): {dead}")
    print("\n  Option 2 needs ALL inter-LAB classes (C4, R4, R24) emittable to "
          "route NEORV32.")
    print(f"  Classes with NO real model: {dead} -> these gate Option 2 "
          "feasibility and require a fresh Quartus mining campaign.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
