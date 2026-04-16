# SPDX-License-Identifier: GPL-3.0-or-later
"""Gap B probe — per-LAB CLK_SEL at a single target LAB.

Isolates "this LAB uses GCLK instead of local clock" bits for one LAB
by varying the LE index within that LAB.  Forced-vs-auto diff at two
different N slots in the same LAB share CLK_SEL cells (LAB-scoped)
but not LE-specific routing / LUT cells (N-scoped).

Strategy:
  sink1 = (X, Y, 0)   sink2 = (X, Y, 4)    (same LAB, different LE)
  diff1 = forced(sink1) ^ auto(sink1)
  diff2 = forced(sink2) ^ auto(sink2)
  CLK_SEL + spine  = diff1 ∩ diff2
  CLK_SEL alone    = (diff1 ∩ diff2) minus E1_activate_spine

E1_activate_spine is loaded from results/clk_cross_pin_spine_check.json
(3 cells at frames 34-35).

This is a single-LAB probe.  Run at multiple LABs (10,4 / 10,16 / 22,10)
to look for a per-LAB formula (e.g. "bit X of the LAB's column CRAM").
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from compile import compile_and_export
from verilog_gen import gen_two_luts_single_input_clocked
from runner import make_lccomb
from config import ROUTE_FUZZ_PINS

REPO = Path(__file__).resolve().parent.parent
RBF = REPO / "results" / "rbf"
DEFAULT_WORK = REPO / "tmp" / "force_gclk"
WORK = DEFAULT_WORK
SPINE_JSON = REPO / "results" / "clk_cross_pin_spine_check.json"

HDR = 32 + 25 * 210
CRC_SLOT = 208

SRC = (10, 10, 0)
SRC_ALT = (22, 10, 0)   # fallback source when target LAB == SRC LAB
                        # (avoids "multiple nodes assigned at LCCOMB_..."
                        # placement collision in Quartus).
N_SLOTS = (0, 2, 4, 6, 8)   # five LEs within the same LAB; N=6/8 added
                        # so clk_lab_sel_per_le.py can derive N6_specific
                        # and N8_specific cells.  Build cache keys on
                        # (sx, sy, sn, dx, dy, dn) so re-running a LAB
                        # already mined at N ∈ {0,2,4} only triggers
                        # the four new builds (forced/auto × N6/N8).
                        # Existing probe JSONs mined at any subset still
                        # work (per_le.py handles arbitrary N slots).
CLK_PIN = "PIN_E1"


def pick_src(target_lab: tuple[int, int]) -> tuple[int, int, int]:
    """Return a source LE that doesn't collide with the target LAB."""
    sx, sy, sn = SRC
    if (sx, sy) == tuple(target_lab):
        return SRC_ALT
    return SRC


def gen_qsf(placement: dict, *, clk_pin: str, forced: bool, seed: int = 1) -> str:
    lines = [
        'set_global_assignment -name FAMILY "Cyclone IV E"',
        "set_global_assignment -name DEVICE EP4CE6F17C8",
        "set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top",
        "set_global_assignment -name VERILOG_FILE fuzz_top.v",
        'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files',
        'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"',
        f"set_global_assignment -name SEED {seed}",
    ]
    for sig, pin in ROUTE_FUZZ_PINS.items():
        if sig == "CLK":
            pin = clk_pin
        lines.append(f'set_location_assignment {pin} -to {sig}')
    for inst, loc in placement.items():
        lines.append(f'set_location_assignment {loc} -to "{inst}"')
    if forced:
        lines.append(
            'set_instance_assignment -name GLOBAL_SIGNAL "GLOBAL CLOCK" -to CLK')
    return "\n".join(lines) + "\n"


def cram_diff(a: bytes, b: bytes) -> set:
    out = set()
    for i in range(HDR, min(len(a), len(b))):
        if (i - 32) % 210 >= CRC_SLOT:
            continue
        x = a[i] ^ b[i]
        if x:
            for bp in range(8):
                if (x >> bp) & 1:
                    out.add((i, bp))
    return out


def build(tag: str, sx, sy, sn, dx, dy, dn, *, forced: bool):
    out_path = RBF / f"{tag}.rbf"
    if out_path.exists():
        return out_path.read_bytes(), "cached"
    verilog = gen_two_luts_single_input_clocked(0x8888, 0xAAAA, "datab")
    placement = {
        "lut1": make_lccomb(sx, sy, sn),
        "lut2": make_lccomb(dx, dy, dn),
    }
    qsf = gen_qsf(placement, clk_pin=CLK_PIN, forced=forced)
    rbf, t, err = compile_and_export(
        tag, verilog, qsf,
        rbf_output=str(out_path),
        work_dir=str(WORK),
    )
    if not rbf:
        return None, f"FAIL: {(err or '')[:120]}"
    return out_path.read_bytes(), f"{t:.1f}s"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lab", default="10,4",
                    help='target LAB "X,Y" (default 10,4)')
    ap.add_argument("--out", default=None,
                    help="output JSON path (default results/clk_lab_sel_probe_X{x}Y{y}.json)")
    ap.add_argument("--work", default=None,
                    help="override WORK dir for parallel runs (default tmp/force_gclk)")
    args = ap.parse_args()
    if args.work:
        global WORK
        WORK = Path(args.work)
    target_lab = tuple(int(x) for x in args.lab.split(","))
    assert len(target_lab) == 2
    out_path = Path(args.out) if args.out else (
        REPO / "results" / f"clk_lab_sel_probe_X{target_lab[0]}Y{target_lab[1]}.json")

    WORK.mkdir(parents=True, exist_ok=True)
    print(f"=== Gap B probe — per-LAB CLK_SEL at LAB{target_lab} ===")
    spine_data = json.loads(SPINE_JSON.read_text())
    e1_spine = set(tuple(c) for c in
                   spine_data["per_pin_forced_vs_auto_intersection"]["PIN_E1"])
    print(f"  E1 spine (to subtract): {len(e1_spine)} cells")

    per_n = {}
    sx, sy, sn = pick_src(target_lab)
    dx, dy = target_lab
    if (sx, sy, sn) != SRC:
        print(f"  (target LAB coincides with default SRC; using alt "
              f"source X{sx}Y{sy}N{sn})")
    for n in N_SLOTS:
        print(f"\n[N={n}]")
        # forced
        f_tag = f"fgclk_FORCE_X{sx}Y{sy}N{sn}_to_X{dx}Y{dy}N{n}"
        rbf_f, msg = build(f_tag, sx, sy, sn, dx, dy, n, forced=True)
        print(f"  forced: {msg}")
        # auto
        a_tag = f"fgclk_AUTO_X{sx}Y{sy}N{sn}_to_X{dx}Y{dy}N{n}"
        rbf_a, msg = build(a_tag, sx, sy, sn, dx, dy, n, forced=False)
        print(f"  auto  : {msg}")
        if None in (rbf_f, rbf_a):
            continue
        diff = cram_diff(rbf_a, rbf_f)
        print(f"  forced-vs-auto: {len(diff)} cells")
        per_n[n] = diff

    if len(per_n) < 2:
        print("\nneed ≥2 N slots; aborting")
        return

    shared = set.intersection(*per_n.values())
    clk_sel = shared - e1_spine
    print(f"\n=== Result for LAB{target_lab} ===")
    print(f"  shared (N-invariant) : {len(shared)} cells")
    print(f"  minus E1 spine       : {len(clk_sel)} cells = LAB CLK_SEL")
    for off, bp in sorted(clk_sel):
        frame = (off - 32) // 210
        print(f"    off={off:6d} bp={bp}  frame={frame}")

    out_path.write_text(json.dumps({
        "src": [sx, sy, sn],
        "target_lab": list(target_lab),
        "n_slots": list(N_SLOTS),
        "clk_pin": CLK_PIN,
        "e1_spine_subtracted": sorted([list(c) for c in e1_spine]),
        "per_n_forced_vs_auto": {
            str(n): sorted([list(c) for c in cells])
            for n, cells in per_n.items()
        },
        "n_invariant_shared":    sorted([list(c) for c in shared]),
        "lab_clk_sel":           sorted([list(c) for c in clk_sel]),
    }, indent=2))
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
