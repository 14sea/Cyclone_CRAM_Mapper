#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""方案 B: Re-mine IOB + output routing cells from nv_zero_global baseline.

Builds 4 LOC-constrained Quartus designs at LCCOMB_X16_Y4_N0 and extracts
pair-deltas against nv_zero_global.rbf.  Every cell set is relative to nv_zero
— no IOB_BASELINE_NV bridge needed.

Designs:
  full:     E16+M16 -> LUT(AND) @ LOC -> G15   (everything)
  nop:      E16+M16 -> LUT(AND) @ LOC -> LED=0 (LUT + input route, no output)
  bare_out: LED0=0  (G15 pad only)
  bare_in:  E16+M16 inputs only

Pair-deltas:
  full  - nv_zero = ALL cells
  nop   - nv_zero = IOB_IN + LUT + input route
  full  - nop     = output routing + IOB_OUT active delta
  bare_out - nv_zero = IOB_OUT G15 pad (constant driver)
  bare_in  - nv_zero = IOB_IN E16+M16 pad
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
WORK = REPO / "tmp" / "mine_outroute_nv"
QUARTUS = Path.home() / "intelFPGA_lite" / "21.1" / "quartus" / "bin"

sys.path.insert(0, str(REPO / "fuzz"))

LOC_X, LOC_Y, LOC_N = 16, 4, 0
QUARTUS_LOC = f"LCCOMB_X{LOC_X}_Y{LOC_Y}_N{LOC_N}"
OUR_N = LOC_N * 2


def run(cmd, cwd=None):
    print(f"  $ {' '.join(str(c) for c in cmd)}", flush=True)
    r = subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                       capture_output=True, text=True, errors="replace",
                       timeout=300)
    if r.returncode != 0:
        print(f"FAIL (rc={r.returncode})")
        if r.stdout:
            print(r.stdout[-3000:])
        if r.stderr:
            print(r.stderr[-3000:])
        sys.exit(1)
    return r


def build(name, verilog, qsf_extra):
    bdir = WORK / name
    bdir.mkdir(parents=True, exist_ok=True)

    vf = bdir / f"{name}.v"
    vf.write_text(verilog)

    qsf = bdir / f"{name}.qsf"
    qsf.write_text(f"""
set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY {name}
set_global_assignment -name VERILOG_FILE {vf}
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_global_assignment -name SEED 1
set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"
set_global_assignment -name RESERVE_ALL_UNUSED_PINS_WEAK_PULLUP "AS INPUT TRI-STATED WITH WEAK PULL-UP"
set_global_assignment -name CYCLONEII_RESERVE_NCEO_AFTER_CONFIGURATION "USE AS REGULAR IO"
{qsf_extra}
""")
    (bdir / f"{name}.qpf").write_text(f'PROJECT_REVISION = "{name}"\n')

    print(f"\n--- Building {name} ---")
    run([str(QUARTUS / "quartus_map"), "--read_settings_files=on",
         "--write_settings_files=off", name], cwd=bdir)
    run([str(QUARTUS / "quartus_fit"), "--read_settings_files=on",
         "--write_settings_files=off", name], cwd=bdir)

    fit_rpt = bdir / "output_files" / f"{name}.fit.rpt"
    if fit_rpt.exists():
        text = fit_rpt.read_text(errors="replace")
        for line in text.splitlines():
            ll = line.lower()
            if "lccomb" in ll or "total logic elements" in ll:
                print(f"  fit: {line.strip()}")

    run([str(QUARTUS / "quartus_asm"), "--read_settings_files=on",
         "--write_settings_files=off", name], cwd=bdir)
    sof = bdir / "output_files" / f"{name}.sof"
    rbf = bdir / f"{name}.rbf"
    run([str(QUARTUS / "quartus_cpf"), "-c", "-o", "bitstream_compression=off",
         str(sof), str(rbf)], cwd=bdir)
    print(f"  -> {rbf} ({rbf.stat().st_size} bytes)")
    return rbf


def extract_cells(a: bytes, b: bytes) -> list[list[int]]:
    cells = []
    for off in range(32, min(len(a), len(b))):
        if off >= 367952:
            break
        if (off - 32) % 210 >= 208:
            continue
        xor = a[off] ^ b[off]
        for bp in range(8):
            if xor & (1 << bp):
                cells.append([off, bp])
    return cells


def classify(cells):
    hdr = [c for c in cells if c[0] < 32 + 25 * 210]
    data = [c for c in cells if 32 + 25 * 210 <= c[0] < 32 + 1692 * 210]
    block = [c for c in cells if 32 + 1692 * 210 <= c[0]]
    return hdr, data, block


def main():
    WORK.mkdir(parents=True, exist_ok=True)

    nv = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()
    assert len(nv) == 368011, f"nv_zero_global wrong size: {len(nv)}"

    # --- Design 1: full (E16+M16 -> LUT@LOC -> G15) ---
    v_full = """\
module nv_full (input KEY2, input KEY3, output LED0);
    wire lut_out /* synthesis keep */;
    assign lut_out = KEY2 & KEY3;
    assign LED0 = lut_out;
endmodule
"""
    qsf_full = f"""\
set_location_assignment PIN_E16 -to KEY2
set_location_assignment PIN_M16 -to KEY3
set_location_assignment PIN_G15 -to LED0
set_location_assignment {QUARTUS_LOC} -to "lut_out"
"""
    rbf_full = build("nv_full", v_full, qsf_full).read_bytes()

    # --- Design 2: nop (E16+M16 -> LUT@LOC -> LED=0) ---
    v_nop = """\
module nv_nop (input KEY2, input KEY3, output LED0);
    wire lut_out /* synthesis keep */;
    assign lut_out = KEY2 & KEY3;
    assign LED0 = 1'b0;
endmodule
"""
    qsf_nop = f"""\
set_location_assignment PIN_E16 -to KEY2
set_location_assignment PIN_M16 -to KEY3
set_location_assignment PIN_G15 -to LED0
set_location_assignment {QUARTUS_LOC} -to "lut_out"
"""
    rbf_nop = build("nv_nop", v_nop, qsf_nop).read_bytes()

    # --- Design 3: bare_out (G15 output at constant 0, no inputs, no LUT) ---
    v_bare_out = """\
module nv_bare_out (output LED0);
    assign LED0 = 1'b0;
endmodule
"""
    qsf_bare_out = """\
set_location_assignment PIN_G15 -to LED0
"""
    rbf_bare_out = build("nv_bare_out", v_bare_out, qsf_bare_out).read_bytes()

    # --- Design 4: bare_in (E16+M16 inputs only, no output) ---
    v_bare_in = """\
module nv_bare_in (input KEY2, input KEY3);
endmodule
"""
    qsf_bare_in = """\
set_location_assignment PIN_E16 -to KEY2
set_location_assignment PIN_M16 -to KEY3
"""
    rbf_bare_in = build("nv_bare_in", v_bare_in, qsf_bare_in).read_bytes()

    # --- Design 5: bare_both (E16+M16 inputs + G15=0 output) ---
    v_bare_both = """\
module nv_bare_both (input KEY2, input KEY3, output LED0);
    assign LED0 = 1'b0;
endmodule
"""
    qsf_bare_both = """\
set_location_assignment PIN_E16 -to KEY2
set_location_assignment PIN_M16 -to KEY3
set_location_assignment PIN_G15 -to LED0
"""
    rbf_bare_both = build("nv_bare_both", v_bare_both, qsf_bare_both).read_bytes()

    # ============================
    # Analysis
    # ============================
    print("\n" + "=" * 60)
    print("PAIR-DELTA ANALYSIS (all vs nv_zero_global)")
    print("=" * 60)

    # vs nv_zero
    c_full_nv = extract_cells(rbf_full, nv)
    c_nop_nv = extract_cells(rbf_nop, nv)
    c_bare_out_nv = extract_cells(rbf_bare_out, nv)
    c_bare_in_nv = extract_cells(rbf_bare_in, nv)
    c_bare_both_nv = extract_cells(rbf_bare_both, nv)

    # pair deltas
    c_full_nop = extract_cells(rbf_full, rbf_nop)
    c_full_bare_both = extract_cells(rbf_full, rbf_bare_both)

    for name, cells in [
        ("full - nv_zero (ALL)", c_full_nv),
        ("nop - nv_zero (LUT+input+IOB_IN+IOB_OUT_const)", c_nop_nv),
        ("bare_out - nv_zero (IOB_OUT G15 pad)", c_bare_out_nv),
        ("bare_in - nv_zero (IOB_IN E16+M16 pad)", c_bare_in_nv),
        ("bare_both - nv_zero (IOB_IN+IOB_OUT pads)", c_bare_both_nv),
        ("full - nop (output route + IOB_OUT active delta)", c_full_nop),
        ("full - bare_both (LUT + input route + output route)", c_full_bare_both),
    ]:
        hdr, data, block = classify(cells)
        print(f"\n  {name}:")
        print(f"    total={len(cells)}  hdr={len(hdr)}  data={len(data)}  block={len(block)}")

    # --- Decompose output routing ---
    print("\n" + "=" * 60)
    print("OUTPUT ROUTING DECOMPOSITION")
    print("=" * 60)

    # full - nop = output routing + IOB output active bits
    # bare_both - bare_in = IOB_OUT G15 pad (driven constant, vs no output)
    c_bare_both_in = extract_cells(rbf_bare_both, rbf_bare_in)
    print(f"\n  bare_both - bare_in (IOB_OUT G15 constant-driven):")
    hdr, data, block = classify(c_bare_both_in)
    print(f"    total={len(c_bare_both_in)}  hdr={len(hdr)}  data={len(data)}  block={len(block)}")

    # The "pure output routing" = (full - nop) minus (bare_both - bare_in)?
    # Not exactly — IOB_OUT may differ between active (LUT-driven) and constant-driven.
    # But (full - nop) is the cleanest: same LUT, same inputs, only output routing differs.

    # --- Set operations for decomposition ---
    set_full_nv = set(tuple(c) for c in c_full_nv)
    set_nop_nv = set(tuple(c) for c in c_nop_nv)
    set_bare_out_nv = set(tuple(c) for c in c_bare_out_nv)
    set_bare_in_nv = set(tuple(c) for c in c_bare_in_nv)
    set_bare_both_nv = set(tuple(c) for c in c_bare_both_nv)
    set_full_nop = set(tuple(c) for c in c_full_nop)

    # Cells unique to full (not in nop) relative to nv_zero
    # = cells in full_nv but not in nop_nv
    output_cells_via_set = set_full_nv - set_nop_nv
    print(f"\n  full_nv - nop_nv (set difference):")
    print(f"    = {len(output_cells_via_set)} cells unique to full design")

    # Cells that nop flipped from nv but full didn't
    nop_only = set_nop_nv - set_full_nv
    print(f"  nop_nv - full_nv:")
    print(f"    = {len(nop_only)} cells unique to nop design")

    # Intersection
    shared = set_full_nv & set_nop_nv
    print(f"  full_nv & nop_nv:")
    print(f"    = {len(shared)} shared cells (LUT + input route + IOB common)")

    # Compare bare_out and bare_both IOB overlap
    iob_out_overlap = set_bare_out_nv & set_bare_both_nv
    print(f"\n  bare_out_nv & bare_both_nv:")
    print(f"    = {len(iob_out_overlap)} / {len(set_bare_out_nv)} bare_out cells also in bare_both")

    # --- Save results ---
    result = {
        "method": "方案B: 4-design pair-delta from nv_zero_global",
        "loc": f"X{LOC_X}Y{LOC_Y}N{OUR_N} (Quartus {QUARTUS_LOC})",
        "pin_in": ["E16", "M16"],
        "pin_out": "G15",

        "full_vs_nv": c_full_nv,
        "nop_vs_nv": c_nop_nv,
        "bare_out_vs_nv": c_bare_out_nv,
        "bare_in_vs_nv": c_bare_in_nv,
        "bare_both_vs_nv": c_bare_both_nv,

        "output_route_cells": c_full_nop,
        "output_route_cells_note": "full - nop pair delta = output routing + IOB active delta",

        "full_only_vs_nv": sorted(list(output_cells_via_set)),
        "nop_only_vs_nv": sorted(list(nop_only)),
        "shared_full_nop": sorted(list(shared)),
    }
    out_json = WORK / "outroute_nv_result.json"
    out_json.write_text(json.dumps(result, indent=2))
    print(f"\nSaved to {out_json}")

    # --- Dump output route cells for inspection ---
    print(f"\n=== Output route cells (full - nop): {len(c_full_nop)} ===")
    for off, bp in c_full_nop:
        frame = (off - 32) // 210
        pos = (off - 32) % 210
        band = "hdr" if frame < 25 else ("data" if frame < 1692 else "block")
        print(f"  ({off}, {bp})  frame={frame} pos={pos} band={band}")

    # --- Build flashable gold for hardware validation ---
    print(f"\n=== Flash commands ===")
    loader = Path.home() / "see_neorv32_run_linux" / "tools" / "openFPGALoader" / "build" / "openFPGALoader"
    print(f"  Full (gold):  {loader} -c usb-blaster {WORK / 'nv_full' / 'nv_full.rbf'}")
    print(f"  nv_zero:      {loader} -c usb-blaster {REPO / 'results' / 'rbf' / 'nv_zero_global.rbf'}")


if __name__ == "__main__":
    main()
