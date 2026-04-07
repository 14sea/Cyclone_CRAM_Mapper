# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 3.25 hardware validation #3 — light a LUT at LCCOMB_X10_Y15_N0.

Orthogonal axis to X=32/X=33: Y=15 is the "ghost row" the CE6 fitter
deletes from LAB_Y. CRAM-stride math says Y=15 maps to slot=1, group=4
(group=4 is past the CE6-observed 0..3 range — exactly what makes it
"ghost"). This test validates that the row exists in physical fabric
under any X column, not just at the edge.

Picks X=10 deliberately: a well-known CE6 column with the most-mined
LE positions. If Y=15 lights at X=10, the ghost row is real fabric
chip-wide; if it fails here, X column choice is unlikely to be the
cause and we instead suspect a missing CRAM model entry.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from compile import compile_and_export
from verilog_gen import gen_lut4_primitive
from config import RBF_DIR, RBF_SIZE, COLUMN_BASE

TX, TY, TN = 10, 15, 0
MASK = 0x8888
TAG = f"jb_hwval_X{TX}_Y{TY}_N{TN}_m{MASK:04X}"
ZERO_TAG = f"jb_hwval_X{TX}_Y{TY}_N{TN}_m0000"

CE10_DEVICE = "EP4CE10F17C8"
FAMILY = "Cyclone IV E"

PINS = {
    "A": "PIN_E16", "B": "PIN_M16", "C": "PIN_M15", "D": "PIN_E15",
    "Q": "PIN_G15",
}
GCLK_PINS = {"PIN_E1"}

PERIOD_START = COLUMN_BASE[TX] - 136
COL_END = PERIOD_START + 7350
COL_WINDOW = (PERIOD_START, COL_END)

KNOWN_BANDS = sorted((b - 136, b - 136 + 7350) for b in COLUMN_BASE.values())


def in_any_band(off):
    for lo, hi in KNOWN_BANDS:
        if lo <= off < hi:
            return True
    return False


def gen_qsf_ce10() -> str:
    lines = [
        f'set_global_assignment -name FAMILY "{FAMILY}"',
        f'set_global_assignment -name DEVICE {CE10_DEVICE}',
        'set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top',
        'set_global_assignment -name VERILOG_FILE fuzz_top.v',
        'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files',
        'set_global_assignment -name MIN_CORE_JUNCTION_TEMP 0',
        'set_global_assignment -name MAX_CORE_JUNCTION_TEMP 85',
        'set_global_assignment -name ERROR_CHECK_FREQUENCY_DIVISOR 1',
        'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"',
        'set_global_assignment -name SEED 1',
    ]
    for sig, pin in PINS.items():
        lines.append(f'set_location_assignment {pin} -to {sig}')
    lines.append(f'set_location_assignment LCCOMB_X{TX}_Y{TY}_N{TN} -to "lut_inst"')
    return '\n'.join(lines) + '\n'


def fail(msg):
    print(f"\n!!! ABORT !!! {msg}")
    sys.exit(1)


def compile_one(tag, mask):
    out = os.path.join(RBF_DIR, f"{tag}.rbf")
    if os.path.exists(out):
        return out
    print(f"compiling {tag} (mask 0x{mask:04X})...")
    verilog = gen_lut4_primitive(mask)
    qsf = gen_qsf_ce10()
    rbf, t, err = compile_and_export(tag, verilog, qsf, rbf_output=out)
    if rbf is None:
        fail(f"compile failed ({t:.1f}s): {err}")
    print(f"  OK ({t:.1f}s)")
    return out


def main():
    print("=" * 60)
    print(f"Y={TY} ghost-row jailbreak HW validation @ LCCOMB_X{TX}_Y{TY}_N{TN}")
    print("=" * 60)

    print("\n[check 3/4] pin discipline")
    if set(PINS.values()) & GCLK_PINS:
        fail("GCLK pin in use")
    print(f"  pins: {PINS}  — no GCLK, OK")

    # Compile both baseline and target — neither was cached from
    # Phase 3.25 because that mine only swept X, fixed Y=10.
    zero_path = compile_one(ZERO_TAG, 0x0000)
    target_path = compile_one(TAG, MASK)
    zero = open(zero_path, "rb").read()
    target = open(target_path, "rb").read()

    print(f"\n[check 1/4] bitstream length invariant")
    print(f"  expected: {RBF_SIZE} / actual: {len(target)}")
    if len(target) != RBF_SIZE or len(zero) != RBF_SIZE:
        fail("length mismatch")
    print(f"  OK")

    print(f"\n[check 2/4] touched-byte band scan")
    diffs = [i for i in range(RBF_SIZE) if target[i] != zero[i]]
    print(f"  diff cells: {len(diffs)}")
    print(f"  X={TX} primary window: 0x{COL_WINDOW[0]:X} .. 0x{COL_WINDOW[1]:X}")

    HEADER_END = 32 + 25 * 210
    in_primary = [d for d in diffs if COL_WINDOW[0] <= d < COL_WINDOW[1]]
    in_header  = [d for d in diffs if d < HEADER_END]
    other      = [d for d in diffs if d not in set(in_primary) and d >= HEADER_END]
    in_other_lab = [d for d in other if in_any_band(d)]
    unmapped     = [d for d in other if not in_any_band(d)]

    print(f"  in X={TX} primary column:           {len(in_primary)}")
    print(f"  in header (frames 0..24):          {len(in_header)}")
    print(f"  in OTHER known LAB column band:    {len(in_other_lab)}  (Quartus routing)")
    print(f"  UNMAPPED (edge-clock / postamble): {len(unmapped)}")

    if unmapped:
        print(f"  first 10 unmapped offsets: {[hex(d) for d in unmapped[:10]]}")
        fail(f"{len(unmapped)} bytes outside any known LAB column — refuse to flash")

    if in_other_lab:
        from collections import Counter
        col_of = {}
        for x, base in COLUMN_BASE.items():
            for off in in_other_lab:
                lo = base - 136
                if lo <= off < lo + 7350:
                    col_of[off] = x
        by_col = Counter(col_of.values())
        print(f"  other-LAB breakdown: {dict(by_col)}")
    print(f"  OK")

    # Bonus: where in the X=10 column do the in-primary diffs land?
    # Y=2..14,16..21 each have known offsets within the column. If Y=15
    # lands in a never-before-touched sub-region of the column, that's
    # the visible signature of the ghost row.
    if in_primary:
        rels = sorted(set(d - PERIOD_START for d in in_primary))
        print(f"  in-primary offsets relative to period_start: {[hex(r) for r in rels[:16]]}")

    print(f"\n[check 4/4] current monitoring — skipped (multimeter offsite)")

    print(f"\n=== READY TO FLASH ===")
    print(f"  RBF: {target_path}")
    print(f"  Truth table: mask 0x8888 (A AND B), active-low keys")
    print(f"    no keys → LED ON ; press K2 or K3 → LED OFF")


if __name__ == "__main__":
    main()
