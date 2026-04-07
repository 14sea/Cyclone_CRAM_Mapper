# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 3.25 — discover COLUMN_BASE for the 6 jailbreak LAB columns.

For each X in {5, 9, 14, 30, 32, 33}, compile two designs at LCCOMB_X{x}_Y10_N0:
  - lut_mask = 0x0000
  - lut_mask = 0xFFFF
under DEVICE=EP4CE10F17C8 (X=32,33 are CE6-illegal; the die is identical).

Pair-diff cancels routing noise; remaining bits are the LUT TT cells. The lowest
data byte (positions ending in 184/185 within a 210-byte period) gives:

    COLUMN_BASE[x] = lowest_data_byte - 48

(period_start = COLUMN_BASE - 136, data_byte = period_start + 184 + pair*210)

Cross-validates against the existing CE6 columns (e.g. X=10 → 0x13FDA) before
trusting the new ones.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from compile import compile_and_export
from verilog_gen import gen_lut4_primitive
from config import RBF_DIR, COLUMN_BASE as CE6_COLUMN_BASE

CE10_DEVICE = "EP4CE10F17C8"
FAMILY = "Cyclone IV E"

# Pin labels are package-position so they exist on both CE6 and CE10 (F17 BGA).
PINS = {
    "A": "PIN_E16", "B": "PIN_M16", "C": "PIN_M15", "D": "PIN_E15",
    "Q": "PIN_G15",
}

NEW_COLUMNS = [5, 9, 14, 30, 32, 33]
VERIFY_COLUMNS = [10]  # known CE6 column for sanity check
PROBE_Y, PROBE_N = 10, 0


def gen_qsf_ce10(placement_node: str, x: int, y: int, n: int) -> str:
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
        'set_global_assignment -name AUTO_RESTART_CONFIGURATION OFF',
        'set_global_assignment -name OPTIMIZATION_MODE "HIGH PERFORMANCE EFFORT"',
    ]
    for sig, pin in PINS.items():
        lines.append(f'set_location_assignment {pin} -to {sig}')
    lines.append(f'set_location_assignment LCCOMB_X{x}_Y{y}_N{n} -to "{placement_node}"')
    return '\n'.join(lines) + '\n'


def compile_one(x: int, mask: int) -> str | None:
    tag = f"jb_colbase_X{x}_Y{PROBE_Y}_N{PROBE_N}_m{mask:04X}"
    out = os.path.join(RBF_DIR, f"{tag}.rbf")
    if os.path.exists(out):
        return out
    verilog = gen_lut4_primitive(mask)
    qsf = gen_qsf_ce10("lut_inst", x, PROBE_Y, PROBE_N)
    rbf, t, err = compile_and_export(tag, verilog, qsf, rbf_output=out)
    if rbf is None:
        print(f"  X={x} mask={mask:04X} FAIL ({t:.1f}s) {err[:80]}", flush=True)
        return None
    print(f"  X={x} mask={mask:04X} OK ({t:.1f}s)", flush=True)
    return rbf


def diff_bytes(rbf_a: str, rbf_b: str) -> list[int]:
    a = open(rbf_a, "rb").read()
    b = open(rbf_b, "rb").read()
    return [i for i in range(len(a)) if a[i] != b[i]]


def analyze(x: int, offsets: list[int]):
    if not offsets:
        print(f"  X={x}: NO DIFF — column not located")
        return None
    lo = min(offsets)
    hi = max(offsets)
    inferred = lo - 48
    span = hi - lo
    expected_pairs = sorted(set((o - lo) // 210 for o in offsets))
    print(f"  X={x}: {len(offsets)} cells, span 0x{span:X}, "
          f"lo=0x{lo:X}, COLUMN_BASE≈0x{inferred:X}, pairs={expected_pairs}")
    if x in CE6_COLUMN_BASE:
        match = "OK" if inferred == CE6_COLUMN_BASE[x] else f"MISMATCH (expected 0x{CE6_COLUMN_BASE[x]:X})"
        print(f"      cross-check vs CE6 known: {match}")
    return inferred


def main():
    targets = VERIFY_COLUMNS + NEW_COLUMNS
    print(f"=== Phase 3.25 column-base mine ({len(targets)} cols × 2 compiles) ===")
    rbfs = {}
    for x in targets:
        for mask in (0x0000, 0xFFFF):
            r = compile_one(x, mask)
            rbfs[(x, mask)] = r

    print("\n=== analysis ===")
    found = {}
    for x in targets:
        ra, rb = rbfs[(x, 0x0000)], rbfs[(x, 0xFFFF)]
        if ra is None or rb is None:
            print(f"  X={x}: skipped (compile failed)")
            continue
        offs = diff_bytes(ra, rb)
        base = analyze(x, offs)
        if base is not None and x in NEW_COLUMNS:
            found[x] = base

    if found:
        print("\n=== NEW COLUMN_BASE entries ===")
        for x in sorted(found):
            print(f"    {x}: 0x{found[x]:X},")


if __name__ == "__main__":
    main()
