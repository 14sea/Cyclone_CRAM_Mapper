# SPDX-License-Identifier: GPL-3.0-or-later
"""CRC byte audit for every mapping in bitstream.py.

Check: for every (offset, bp) a codec write path emits, does the offset
fall on a frame CRC byte?  A frame is 210 bytes starting at byte 32;
the last 2 bytes of each frame (positions 208, 209) are CRC-16 LE.

Rule: `is_crc = (offset - 32) % 210 >= 208` for CRAM frames 25..1751
(offset must also be inside byte 5282 .. 367952).

Any mapping where writes land on CRC bytes is suspect — `patch_rbf_crc`
will overwrite those bytes and make the writes no-ops.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bitstream import (
    _C4_FIXED_OFFSETS, _C4_SLOT_BASE, _LAB_CRAM_END,
    _R4_BASE_PREV, _r4_addr, _R4_STD_COL_WIDTH,
    _R24_FIXED_OFFSETS, _COL_WIDTH, _NEXT_LAB,
    _FF_ARST_CELLS, _FF_ENA_CELLS,
    _LI_SLOT_OFFSET,
    _cram_group_bit, PAIR_SPACING,
)
from config import LAB_X, LAB_Y, COLUMN_BASE

CRAM_LO = 32 + 25 * 210    # first CRAM byte 5282
CRAM_HI = 32 + 1752 * 210  # last CRAM byte (exclusive) 367952


def is_crc(off):
    if off < CRAM_LO or off >= CRAM_HI:
        return False
    return (off - 32) % 210 >= 208


def audit(name, cell_iter):
    total = 0
    crc = 0
    bad_samples = []
    for label, off, bp in cell_iter:
        total += 1
        if is_crc(off):
            crc += 1
            if len(bad_samples) < 3:
                bad_samples.append((label, off, bp))
    pct = 100.0 * crc / total if total else 0
    flag = "🔴" if pct > 30 else "🟡" if pct > 0 else "✅"
    print(f"{flag} {name:30s}  {crc:5d}/{total:5d} CRC ({pct:5.1f}%)")
    for label, off, bp in bad_samples:
        fp = (off - 32) % 210
        print(f"     sample: {label}  off=0x{off:05x} bp={bp} frame_pos={fp}")


def main():
    print("=== CRC byte audit for bitstream.py mappings ===\n")

    # 1. C4 I=0 — formula: _LAB_CRAM_END[x] + _C4_SLOT_BASE[slot] + 3*group
    def c4_i0():
        for x in sorted(_LAB_CRAM_END):
            for y in LAB_Y:
                group, slot, bp = _cram_group_bit(y)
                off = _LAB_CRAM_END[x] + _C4_SLOT_BASE[slot] + 3 * group
                yield (f"C4 I=0 X={x} Y={y}", off, bp)
    audit("C4 I=0 (formula)", c4_i0())

    # 2. C4 I≠0 — lookup table × all Y values
    def c4_inz():
        for (x, i), off in _C4_FIXED_OFFSETS.items():
            for y in LAB_Y:
                _, _, bp = _cram_group_bit(y)
                yield (f"C4 I={i} X={x} Y={y}", off, bp)
    audit("C4 I≠0 (44 × |Y|)", c4_inz())

    # 3. R4 — per-I pair1+pair2 formula across all prev columns × all Y
    def r4_all():
        for i_idx, (b1, b2) in _R4_BASE_PREV.items():
            for prev_x in LAB_X:
                if prev_x not in COLUMN_BASE:
                    continue
                col_start = COLUMN_BASE[prev_x] - 136
                for base in (b1, b2):
                    for y in LAB_Y:
                        byte_off, bp = _r4_addr(base, y)
                        off = col_start + byte_off
                        if 0 <= off < CRAM_HI:
                            yield (f"R4 I={i_idx} prev=X{prev_x} Y={y} base={base}", off, bp)
    audit("R4 (all I × prev × Y)", r4_all())

    # 4. R24 I=0 — fixed offsets × all prev columns × all Y
    def r24_i0():
        for off_rel in _R24_FIXED_OFFSETS[0]:
            for prev_x in LAB_X:
                if prev_x not in COLUMN_BASE:
                    continue
                col_start = COLUMN_BASE[prev_x] - 136
                for y in LAB_Y:
                    group, slot, _ = _cram_group_bit(y)
                    bp = (6 - group) if slot == 2 else (7 - group)
                    off = col_start + off_rel
                    yield (f"R24 I=0 prev=X{prev_x} Y={y}", off, bp)
    audit("R24 I=0 (fixed offsets)", r24_i0())

    # 5. FF arst
    def ff_arst():
        for x in LAB_X:
            if x not in COLUMN_BASE:
                continue
            col_start = COLUMN_BASE[x] - 136
            for rel, bp in _FF_ARST_CELLS:
                yield (f"FF arst X={x}", col_start + rel, bp)
    audit("FF arst", ff_arst())

    # 6. FF ena
    def ff_ena():
        for x in LAB_X:
            if x not in COLUMN_BASE:
                continue
            col_start = COLUMN_BASE[x] - 136
            for rel, bp in _FF_ENA_CELLS:
                yield (f"FF ena X={x}", col_start + rel, bp)
    audit("FF ena", ff_ena())

    # 7. LOCAL_INTERCONNECT — base 70/71 + pair*210 + slot_off + 3*group
    #    across 0..8 pairs × 2 base_idx × all LAB columns × all Y
    def li_all():
        for lx in LAB_X:
            if lx not in COLUMN_BASE:
                continue
            col_start = COLUMN_BASE[lx] - 136
            for ly in LAB_Y:
                group, slot, bp = _cram_group_bit(ly)
                slot_off = _LI_SLOT_OFFSET[slot]
                for pair in range(9):
                    for base_idx in (0, 1):
                        base = 70 + base_idx
                        off = col_start + base + pair * PAIR_SPACING + slot_off + 3 * group
                        yield (f"LI X={lx} Y={ly} P{pair} B{base_idx}", off, bp)
    audit("LI (9 pairs × 2 bases)", li_all())

    # 8. LutCodec minterm cells (per-LE, sourced from sqlite)
    #    Check the SQLite features table for every (x,y,n) and count CRC hits.
    import sqlite3
    from pathlib import Path
    REPO = Path(os.path.dirname(os.path.abspath(__file__))).parent
    db = REPO / "results" / "ep4ce6_bitdb.sqlite"
    if db.exists():
        conn = sqlite3.connect(db)
        try:
            rows = conn.execute(
                "SELECT feature, offset, bit_pos FROM bit_mappings "
                "WHERE feature LIKE 'minterm_%'"
            ).fetchall()
        except sqlite3.OperationalError:
            try:
                rows = conn.execute(
                    "SELECT feature_name, offset, bit_pos FROM features "
                    "WHERE feature_name LIKE 'minterm_%'"
                ).fetchall()
            except sqlite3.OperationalError:
                # discover table
                tables = [r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")]
                print(f"  (sqlite tables: {tables})")
                rows = []
        conn.close()
        def lut_cells():
            for feat, off, bp in rows:
                yield (feat, off, bp)
        audit(f"LutCodec minterms ({len(rows)} db rows)", lut_cells())
    else:
        print(f"  (no sqlite db at {db}, skip LutCodec audit)")


if __name__ == "__main__":
    main()
