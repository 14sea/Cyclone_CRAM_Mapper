#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase A / STEP A3 — single-route mine + high-density composition byte-probe.

THE make-or-break Pitfall #14 / P5d test, in software (no flash):
Do per-route mined CRAM cells COMPOSE byte-identically with other routing in a
DENSE contended region, or does Quartus reroute (context-dependence)?

Design: 4 LEs LOC-pinned so two routes contend MAXIMALLY — both run
X10Y10 -> X13Y10 (N0 and N2), forcing them to share the R4/local resources
between the same two LABs:
    src0 @ LCCOMB_X10_Y10_N0   dst0 @ LCCOMB_X13_Y10_N0   (route s0)
    src1 @ LCCOMB_X10_Y10_N2   dst1 @ LCCOMB_X13_Y10_N2   (route s1)
All 4 LEs are instantiated + LOC'd + dont_touch in EVERY variant; the only
difference is whether dst_i.dataa is driven by src_i (route ON) or by a
primary input (route OFF). So gold_X ^ gold_base isolates exactly route X.

Variants built (4 Quartus compiles):
    base : both routes OFF (dst0<-C, dst1<-D)        — placement baseline
    s0   : s0 ON, s1 OFF                             — mine route s0
    s1   : s0 OFF, s1 ON                             — mine route s1
    both : both ON                                   — the dense gold

Test: composed = base XOR (cells(s0) UNION cells(s1)) [union-before-XOR];
patch CRC; byte-diff vs `both` gold (zeta_rbf_diff fabric diffs); LI-MUX gate.
  0 fabric diffs -> GO-A3 (routes compose; Pitfall #14 does NOT fire here)
  >0 diffs       -> NO-GO-A3 (context-dependent reroute; native path blocked)
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "fuzz"))
QUARTUS = Path.home() / "intelFPGA_lite" / "21.1" / "quartus" / "bin"
WORK = REPO / "tmp" / "a3_composition"
ZERO = REPO / "results" / "rbf" / "nv_zero_global.rbf"

from bitstream import patch_rbf_crc, li_lab_for_offset  # noqa: E402

RBF = 368011
PRE = 32
FRAME = 210
FDATA = 208
HDR_END = 5282


def is_fabric(off):
    return HDR_END <= off < PRE + 1752 * FRAME and (off - PRE) % FRAME < FDATA


def cells_diff(a, b):
    """fabric-CRAM (off,bp) where a,b differ."""
    out = set()
    for off in range(RBF):
        x = a[off] ^ b[off]
        if x and is_fabric(off):
            for bp in range(8):
                if x & (1 << bp):
                    out.add((off, bp))
    return out


def gen_verilog(s0_on: bool, s1_on: bool) -> str:
    d0 = "s0" if s0_on else "C"
    d1 = "s1" if s1_on else "D"
    return f"""\
// SPDX-License-Identifier: GPL-3.0-or-later
// A3 composition probe: two routes X10Y10 -> X13Y10 (N0,N2).
module fuzz_top(input wire CLK, input wire A, input wire B,
                input wire C, input wire D, output reg Q0, output reg Q1);
    wire s0, s1, o0, o1;
    cycloneive_lcell_comb #(.lut_mask(16'h8888), .sum_lutc_input("datac"),
        .dont_touch("on")) src0 (.dataa(A), .datab(B), .combout(s0));
    cycloneive_lcell_comb #(.lut_mask(16'h8888), .sum_lutc_input("datac"),
        .dont_touch("on")) src1 (.dataa(A), .datab(B), .combout(s1));
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac"),
        .dont_touch("on")) dst0 (.dataa({d0}), .combout(o0));
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac"),
        .dont_touch("on")) dst1 (.dataa({d1}), .combout(o1));
    always @(posedge CLK) begin Q0 <= o0; Q1 <= o1; end
endmodule
"""


def gen_qsf(name: str) -> str:
    L = [
        'set_global_assignment -name FAMILY "Cyclone IV E"',
        'set_global_assignment -name DEVICE EP4CE6F17C8',
        'set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top',
        'set_global_assignment -name VERILOG_FILE fuzz_top.v',
        'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files',
        'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"',
        'set_global_assignment -name SEED 1',
        'set_global_assignment -name RESERVE_ALL_UNUSED_PINS_WEAK_PULLUP '
        '"AS INPUT TRI-STATED WITH WEAK PULL-UP"',
        'set_global_assignment -name CYCLONEII_RESERVE_NCEO_AFTER_CONFIGURATION '
        '"USE AS REGULAR IO"',
        'set_location_assignment PIN_E1 -to CLK',
        'set_location_assignment PIN_E16 -to A',
        'set_location_assignment PIN_M16 -to B',
        'set_location_assignment PIN_M15 -to C',
        'set_location_assignment PIN_E15 -to D',
        'set_location_assignment PIN_G15 -to Q0',
        'set_location_assignment PIN_F16 -to Q1',
        'set_location_assignment LCCOMB_X10_Y10_N0 -to "src0"',
        'set_location_assignment LCCOMB_X10_Y10_N2 -to "src1"',
        'set_location_assignment LCCOMB_X13_Y10_N0 -to "dst0"',
        'set_location_assignment LCCOMB_X13_Y10_N2 -to "dst1"',
        'set_instance_assignment -name GLOBAL_SIGNAL "GLOBAL CLOCK" -to CLK',
    ]
    return "\n".join(L) + "\n"


def build(tag: str, s0_on: bool, s1_on: bool):
    wd = WORK / tag
    wd.mkdir(parents=True, exist_ok=True)
    (wd / "fuzz_top.v").write_text(gen_verilog(s0_on, s1_on))
    (wd / "fuzz_top.qsf").write_text(gen_qsf("fuzz_top"))
    (wd / "fuzz_top.qpf").write_text(
        'QUARTUS_VERSION = "21.1"\nPROJECT_REVISION = "fuzz_top"\n')
    env = os.environ.copy()
    env["PATH"] = str(QUARTUS) + ":" + env.get("PATH", "")
    for step in ("quartus_map", "quartus_fit", "quartus_asm"):
        r = subprocess.run([step, "fuzz_top"], cwd=str(wd), env=env,
                           capture_output=True, text=True, errors="replace",
                           timeout=400)
        if r.returncode != 0:
            print(f"  [{tag}/{step}] FAIL\n{r.stderr[-1500:]}")
            return None
    sof = wd / "output_files" / "fuzz_top.sof"
    rbf = wd / "output_files" / "fuzz_top.rbf"
    r = subprocess.run([str(QUARTUS / "quartus_cpf"), "-c", "-o",
                        "bitstream_compression=off", str(sof), str(rbf)],
                       cwd=str(wd), env=env, capture_output=True, text=True,
                       errors="replace", timeout=120)
    if r.returncode != 0 or not rbf.exists():
        print(f"  [{tag}/cpf] FAIL\n{r.stderr[-800:]}")
        return None
    print(f"  [{tag}] built")
    return rbf.read_bytes()


def main():
    import hashlib
    print("=== A3 composition probe (4 Quartus builds, no flash) ===")
    base = build("base", False, False)
    g_s0 = build("s0", True, False)
    g_s1 = build("s1", False, True)
    both = build("both", True, True)
    if not all((base, g_s0, both, g_s1)):
        print("BUILD FAILED — abort")
        return 1
    for nm, r in [("base", base), ("s0", g_s0), ("s1", g_s1), ("both", both)]:
        print(f"  md5 {nm}: {hashlib.md5(r).hexdigest()[:10]}")

    s0_cells = cells_diff(g_s0, base)
    s1_cells = cells_diff(g_s1, base)
    union = s0_cells | s1_cells
    shared = s0_cells & s1_cells
    print(f"\nroute s0 cells: {len(s0_cells)}   route s1 cells: {len(s1_cells)}   "
          f"shared: {len(shared)}   union: {len(union)}")

    # union-before-XOR compose onto base
    composed = bytearray(base)
    for off, bp in union:
        composed[off] ^= (1 << bp)
    composed = bytearray(patch_rbf_crc(bytes(composed)))

    # byte-diff composed vs the dense `both` gold (fabric only)
    diff = cells_diff(bytes(composed), both)
    # also the Quartus 'both' delta vs base, for context
    both_cells = cells_diff(both, base)
    print(f"Quartus 'both' delta vs base: {len(both_cells)} cells   "
          f"(union-of-individual: {len(union)})")
    print(f"\n>>> composed XOR-union  vs  Quartus dense gold: "
          f"{len(diff)} fabric byte-cell diffs")

    if diff:
        # classify the diffs (LI-MUX gate-style)
        li = [c for c in diff if li_lab_for_offset(*c)]
        print(f"    of which LI-MUX cells (li_lab_for_offset): {len(li)}")
        for off, bp in sorted(diff)[:12]:
            lab = li_lab_for_offset(off, bp)
            print(f"      0x{off:X} bp{bp}  li={lab}")
        print("\n=== A3 VERDICT: NO-GO-A3 — routes do NOT compose byte-identically.")
        print("    Quartus rerouted in the dense context (Pitfall #14 FIRES at density).")
        print("    Per-route mined cells are context-dependent -> native path blocked at data layer.")
    else:
        print("\n=== A3 VERDICT: GO-A3 — union-of-individual-routes is BYTE-IDENTICAL")
        print("    to the Quartus dense gold. Mined cells COMPOSE; Pitfall #14 does")
        print("    NOT fire at this density. Mass per-pip mining is justified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
