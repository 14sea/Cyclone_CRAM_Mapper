# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 3.25 hardware validation — light a LUT at LCCOMB_X32_Y10_N0.

First-stage HW test: prove Quartus-pristine logic compiled at the
jailbreak column X=32 actually runs on real CE6 silicon. This is
deliberately the simpler test (Quartus baseline, not codec output) so
that any failure can be cleanly attributed to silicon (edge-clock / GBUF
contention) rather than codec bit math.

Pre-flash assertions enforce the 4-point checklist:
  1. RBF length == 368011 bytes (frame count invariant)
  2. Touched-byte band scan: all flipped bytes lie inside X=32's column
     window — none in unmapped right-edge / edge-clock territory
  3. Pin discipline: input pins are KEYx (PIN_E15/E16/M15/M16), NOT
     PIN_E1 (50 MHz GCLK0). A KEY-only design rules out GBUF as a
     confound on first flash
  4. Manual current-monitor reminder printed at the end

If LED is dark after flash → triage in this order:
  - GBUF / GCLK pin assignment
  - edge-clock band overlap (re-run band scan with stricter bounds)
  - re-flash Quartus baseline for sanity
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from compile import compile_and_export
from verilog_gen import gen_lut4_primitive
from config import RBF_DIR, RBF_SIZE, COLUMN_BASE

# --- Target ---
TX, TY, TN = 32, 10, 0
MASK = 0x8888  # A AND B (active-low keys: LED ON unless any key pressed)
TAG = f"jb_hwval_X{TX}_Y{TY}_N{TN}_m{MASK:04X}"
ZERO_TAG = f"jb_colbase_X{TX}_Y{TY}_N{TN}_m0000"  # cached from Phase 3.25 mine

CE10_DEVICE = "EP4CE10F17C8"
FAMILY = "Cyclone IV E"

# Pin map: KEYx + LED, NO clock (rules out GBUF/GCLK)
PINS = {
    "A": "PIN_E16",  # KEY2
    "B": "PIN_M16",  # KEY3
    "C": "PIN_M15",  # KEY4 (unused — pulled high by board)
    "D": "PIN_E15",  # KEY1 (unused — pulled high by board)
    "Q": "PIN_G15",  # LED0 active-high
}
GCLK_PINS = {"PIN_E1"}  # forbidden for first HW validation

# X=32 column window — primary expected location of LUT TT writes
PERIOD_START = COLUMN_BASE[TX] - 136
COL_END = PERIOD_START + 7350  # one full LAB column step
COL_WINDOW = (PERIOD_START, COL_END)

# All known LAB column bands. Quartus may legitimately write into any of
# these (e.g. routing the input signal through neighboring columns); only
# bytes that fall in NONE of them are suspicious.
KNOWN_BANDS = sorted(
    (base - 136, base - 136 + 7350) for base in COLUMN_BASE.values()
)


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
    print(f"X={TX} Y={TY} N={TN} jailbreak HW validation")
    print("=" * 60)

    # --- Pin discipline check (#3) — fail before even compiling ---
    print("\n[check 3/4] pin discipline")
    used_pins = set(PINS.values())
    bad = used_pins & GCLK_PINS
    if bad:
        fail(f"GCLK pin in use: {bad}. Move input to a non-clock pin first.")
    print(f"  pins: {PINS}")
    print(f"  no GCLK pins (PIN_E1 is reserved for 50 MHz clock) — OK")

    # --- Baseline (cached) ---
    zero_path = os.path.join(RBF_DIR, f"{ZERO_TAG}.rbf")
    if not os.path.exists(zero_path):
        fail(f"missing baseline {zero_path} — run jb_column_base_mine.py first")
    zero = open(zero_path, "rb").read()
    print(f"\nbaseline: {zero_path} ({len(zero)} bytes)")

    # --- Compile mask 0x8888 at X=32 ---
    target_path = os.path.join(RBF_DIR, f"{TAG}.rbf")
    if not os.path.exists(target_path):
        print(f"\ncompiling {TAG} (mask 0x{MASK:04X} at X={TX} Y={TY} N={TN})...")
        verilog = gen_lut4_primitive(MASK)
        qsf = gen_qsf_ce10()
        rbf, t, err = compile_and_export(TAG, verilog, qsf, rbf_output=target_path)
        if rbf is None:
            fail(f"compile failed ({t:.1f}s): {err}")
        print(f"  OK ({t:.1f}s)")
    else:
        print(f"\nusing cached {target_path}")
    target = open(target_path, "rb").read()

    # --- check 1: length invariant ---
    print(f"\n[check 1/4] bitstream length invariant")
    print(f"  expected: {RBF_SIZE} bytes")
    print(f"  actual:   {len(target)} bytes")
    if len(target) != RBF_SIZE:
        fail(f"length mismatch — frame count broken")
    if len(zero) != RBF_SIZE:
        fail(f"baseline length wrong — {len(zero)}")
    print(f"  OK")

    # --- check 2: touched-byte band scan ---
    print(f"\n[check 2/4] touched-byte band scan")
    diffs = [i for i in range(RBF_SIZE) if target[i] != zero[i]]
    print(f"  diff cells: {len(diffs)}")
    print(f"  X={TX} primary window: 0x{COL_WINDOW[0]:X} .. 0x{COL_WINDOW[1]:X}")

    HEADER_END = 32 + 25 * 210  # frame 25 starts here; frames 0..24 are header
    in_primary = [d for d in diffs if COL_WINDOW[0] <= d < COL_WINDOW[1]]
    in_header = [d for d in diffs if d < HEADER_END]
    # Anything else: must lie inside SOME known LAB column band, otherwise
    # it touches unmapped territory (edge-clock spine, postamble, etc.).
    other = [d for d in diffs if d not in set(in_primary) and d >= HEADER_END]
    in_other_lab = [d for d in other if in_any_band(d)]
    unmapped = [d for d in other if not in_any_band(d)]

    print(f"  in X={TX} primary column:           {len(in_primary)}")
    print(f"  in header (frames 0..24):          {len(in_header)}")
    print(f"  in OTHER known LAB column band:    {len(in_other_lab)}  (Quartus routing)")
    print(f"  UNMAPPED (edge-clock / postamble): {len(unmapped)}")

    if unmapped:
        print(f"  first 10 unmapped offsets: {[hex(d) for d in unmapped[:10]]}")
        fail(f"{len(unmapped)} bytes outside ANY known LAB column — refuse to flash")

    # Cross-tag the 'other LAB' diffs by which column they belong to, for
    # auditability.
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

    # --- check 4: current monitor reminder ---
    print(f"\n[check 4/4] current monitoring (manual)")
    print(f"  Before flash: note the board's idle current draw.")
    print(f"  After flash:  watch for sudden ΔI > 20 mA vs Quartus baseline.")
    print(f"  ΔI > 20 mA = possible internal routing contention — STOP and triage.")

    # --- Flash instructions ---
    print(f"\n=== READY TO FLASH ===")
    print(f"  RBF: {target_path}")
    print(f"  Truth table (mask 0x{MASK:04X}, active-low keys):")
    print(f"    no keys pressed → A=B=1 → LED ON")
    print(f"    K2 OR K3 pressed → A=0 or B=0 → LED OFF")
    print(f"\n  Flash command:")
    print(f"    $HOME/see_neorv32_run_linux/tools/openFPGALoader/build/openFPGALoader -c usb-blaster {target_path}")
    print(f"\n  Failure triage if LED dark:")
    print(f"    1. GBUF / GCLK — re-check pin map (KEYx only, no PIN_E1)")
    print(f"    2. Edge-clock band overlap — narrow band scan to LAB-only bytes")
    print(f"    3. Re-flash Quartus baseline {zero_path} for sanity")


if __name__ == "__main__":
    main()
