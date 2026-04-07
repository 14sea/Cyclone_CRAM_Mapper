# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 3.25 hardware validation #2 — light a LUT at LCCOMB_X33_Y10_N0.

X=33 is the rightmost LAB column on the die — symmetric to X=32 but one
step further into the previously-forbidden zone. If X=32 silicon-validated
cleanly (it did, 2026-04-07), X=33 should too. Same 4-point pre-flash
checklist; same KEY-only pin map; same A-AND-B truth table.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from compile import compile_and_export
from verilog_gen import gen_lut4_primitive
from config import RBF_DIR, RBF_SIZE, COLUMN_BASE

TX, TY, TN = 33, 10, 0
MASK = 0x8888
TAG = f"jb_hwval_X{TX}_Y{TY}_N{TN}_m{MASK:04X}"
ZERO_TAG = f"jb_colbase_X{TX}_Y{TY}_N{TN}_m0000"

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


def main():
    print("=" * 60)
    print(f"X={TX} Y={TY} N={TN} jailbreak HW validation (rightmost edge)")
    print("=" * 60)

    print("\n[check 3/4] pin discipline")
    bad = set(PINS.values()) & GCLK_PINS
    if bad:
        fail(f"GCLK pin in use: {bad}")
    print(f"  pins: {PINS}")
    print(f"  no GCLK pins — OK")

    zero_path = os.path.join(RBF_DIR, f"{ZERO_TAG}.rbf")
    if not os.path.exists(zero_path):
        fail(f"missing baseline {zero_path} — run jb_column_base_mine.py")
    zero = open(zero_path, "rb").read()
    print(f"\nbaseline: {zero_path} ({len(zero)} bytes)")

    target_path = os.path.join(RBF_DIR, f"{TAG}.rbf")
    if not os.path.exists(target_path):
        print(f"\ncompiling {TAG} (mask 0x{MASK:04X} at X={TX})...")
        verilog = gen_lut4_primitive(MASK)
        qsf = gen_qsf_ce10()
        rbf, t, err = compile_and_export(TAG, verilog, qsf, rbf_output=target_path)
        if rbf is None:
            fail(f"compile failed ({t:.1f}s): {err}")
        print(f"  OK ({t:.1f}s)")
    else:
        print(f"\nusing cached {target_path}")
    target = open(target_path, "rb").read()

    print(f"\n[check 1/4] bitstream length invariant")
    print(f"  expected: {RBF_SIZE} / actual: {len(target)}")
    if len(target) != RBF_SIZE:
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

    print(f"\n[check 4/4] current monitoring (manual / skipped — multimeter offsite)")

    print(f"\n=== READY TO FLASH ===")
    print(f"  RBF: {target_path}")
    print(f"  Truth table: same as X=32 test (mask 0x8888, A AND B)")
    print(f"    no keys → LED ON ; press K2 or K3 → LED OFF")
    print(f"\n  Flash command:")
    print(f"    $HOME/see_neorv32_run_linux/tools/openFPGALoader/build/openFPGALoader -c usb-blaster {target_path}")


if __name__ == "__main__":
    main()
