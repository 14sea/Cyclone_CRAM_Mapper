# SPDX-License-Identifier: GPL-3.0-or-later
"""Subtract IOB-incidental cells from the 6-cell Gap A intersection.

When we change CLK from PIN_E1 to PIN_R8 in a forced-GCLK build, the
intersection (across sinks) of the diff captures TWO things:
  1. The GCLK_IN MUX bits that select source pin → GCLK index.
  2. The IOB cells that turn E1 OFF as a clock-input pad and turn R8
     ON as a clock-input pad.

This probe builds the same design WITHOUT forcing GCLK (CLK stays
local), once with CLK=E1 and once with CLK=R8.  The diff is purely
the IOB-incidental delta — no GCLK_IN MUX involvement (since neither
build promotes the clock to global).

Result = forced-Gap-A-intersection MINUS unforced-Gap-A-intersection
= pure GCLK_IN MUX bits.
"""
from __future__ import annotations

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
WORK = REPO / "tmp" / "force_gclk"
OUT = REPO / "results" / "clk_iob_subtract_probe.json"
GAPA = REPO / "results" / "clk_pin_gclk_idx_probe.json"

HDR = 32 + 25 * 210
CRC_SLOT = 208

SRC = (10, 10, 0)
SINKS = [
    (10, 4, 0),
    (10, 16, 0),
    (22, 10, 0),
]
ALT_PIN = "PIN_R8"


def gen_qsf(placement: dict, *, clk_pin: str, seed: int = 1) -> str:
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
    # NO global-clock force — that's the whole point
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


def build(tag: str, sx, sy, sn, dx, dy, dn, *, clk_pin: str):
    out_path = RBF / f"{tag}.rbf"
    if out_path.exists():
        return out_path.read_bytes(), "cached"
    verilog = gen_two_luts_single_input_clocked(0x8888, 0xAAAA, "datab")
    placement = {
        "lut1": make_lccomb(sx, sy, sn),
        "lut2": make_lccomb(dx, dy, dn),
    }
    qsf = gen_qsf(placement, clk_pin=clk_pin)
    rbf, t, err = compile_and_export(
        tag, verilog, qsf,
        rbf_output=str(out_path),
        work_dir=str(WORK),
    )
    if not rbf:
        return None, f"FAIL: {(err or '')[:120]}"
    return out_path.read_bytes(), f"{t:.1f}s"


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    print("=== IOB-incidental subtract probe ===")

    per_sink = {}
    for dx, dy, dn in SINKS:
        sx, sy, sn = SRC
        key = f"{dx},{dy},{dn}"
        print(f"\n[{key}]")
        # E1 unforced (matches clk_force_gclk_probe AUTO build, cached)
        e_tag = f"fgclk_AUTO_X{sx}Y{sy}N{sn}_to_X{dx}Y{dy}N{dn}"
        rbf_e, msg = build(e_tag, sx, sy, sn, dx, dy, dn, clk_pin="PIN_E1")
        print(f"  E1-AUTO build: {msg}")
        if rbf_e is None:
            continue
        # R8 unforced (new)
        a_tag = f"fgclk_AUTO_R8_X{sx}Y{sy}N{sn}_to_X{dx}Y{dy}N{dn}"
        rbf_a, msg = build(a_tag, sx, sy, sn, dx, dy, dn, clk_pin=ALT_PIN)
        print(f"  R8-AUTO build: {msg}")
        if rbf_a is None:
            continue
        diff = cram_diff(rbf_e, rbf_a)
        print(f"  E1-AUTO vs R8-AUTO: {len(diff)} cells (IOB-incidental)")
        per_sink[key] = sorted([list(c) for c in diff])

    if not per_sink:
        print("no data")
        return

    sets = [set(tuple(c) for c in v) for v in per_sink.values()]
    iob_inter = set.intersection(*sets) if sets else set()
    print(f"\n  IOB-incidental intersection: {len(iob_inter)} cells")
    for off, bp in sorted(iob_inter):
        frame = (off - 32) // 210
        print(f"    off={off:6d} bp={bp}  frame={frame}")

    # Compare against forced-GCLK Gap A intersection
    gapa = json.loads(GAPA.read_text())
    forced_inter = set(tuple(c) for c in gapa["intersection"])
    pure_mux = forced_inter - iob_inter
    iob_overlap = forced_inter & iob_inter
    print(f"\n=== Pure GCLK source-MUX bits ===")
    print(f"  forced-Gap-A intersection : {len(forced_inter)} cells")
    print(f"  IOB-incidental subset     : {len(iob_overlap)} cells")
    print(f"  pure GCLK source-MUX      : {len(pure_mux)} cells")
    for off, bp in sorted(pure_mux):
        frame = (off - 32) // 210
        print(f"    off={off:6d} bp={bp}  frame={frame}")

    OUT.write_text(json.dumps({
        "src": list(SRC),
        "sinks": [list(s) for s in SINKS],
        "baseline_pin": "PIN_E1",
        "alt_pin": ALT_PIN,
        "per_sink_iob_diff": per_sink,
        "iob_incidental_intersection": sorted([list(c) for c in iob_inter]),
        "forced_gap_a_intersection": sorted([list(c) for c in forced_inter]),
        "pure_gclk_source_mux": sorted([list(c) for c in pure_mux]),
    }, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
