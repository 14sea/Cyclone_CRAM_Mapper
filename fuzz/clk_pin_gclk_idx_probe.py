# SPDX-License-Identifier: GPL-3.0-or-later
"""Gap A probe — CLK_pin → GCLK_index encoding.

Builds the same forced-GCLK design with CLK on two different dedicated
clock pins (PIN_E1 vs PIN_R8) and diffs the resulting RBFs.  Cells that
differ between the two = the GCLK_IN MUX bits that select which
dedicated CLK pin drives the global signal.

PIN_R8 was confirmed accepted as a dedicated clock pin by Quartus
2026-04-14 (manual probe).  E1 is the AX301 default 50 MHz clock.

Both builds force GCLK promotion via
``set_instance_assignment GLOBAL_SIGNAL "GLOBAL CLOCK" -to CLK``
so we are comparing apples to apples.
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
OUT = REPO / "results" / "clk_pin_gclk_idx_probe.json"

HDR = 32 + 25 * 210
CRC_SLOT = 208

SRC = (10, 10, 0)
SINKS = [
    (10, 4, 0),
    (10, 16, 0),
    (22, 10, 0),
]
ALT_PIN = "PIN_R8"   # alt dedicated clock pin (E1 is the default)


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
        # Override CLK with the alt pin if requested
        if sig == "CLK":
            pin = clk_pin
        lines.append(f'set_location_assignment {pin} -to {sig}')
    for inst, loc in placement.items():
        lines.append(f'set_location_assignment {loc} -to "{inst}"')
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
    print(f"=== Gap A probe: CLK_pin → GCLK_index encoding ===")
    print(f"baseline pin = PIN_E1, alt pin = {ALT_PIN}")

    per_sink = {}
    for dx, dy, dn in SINKS:
        sx, sy, sn = SRC
        key = f"{dx},{dy},{dn}"
        print(f"\n[{key}]")
        # PIN_E1 (this is the same as fgclk_FORCE_*; will be cached)
        e_tag = f"fgclk_FORCE_X{sx}Y{sy}N{sn}_to_X{dx}Y{dy}N{dn}"
        rbf_e, msg = build(e_tag, sx, sy, sn, dx, dy, dn, clk_pin="PIN_E1")
        print(f"  E1 build: {msg}")
        if rbf_e is None:
            continue
        # ALT
        a_tag = f"fgclk_R8_X{sx}Y{sy}N{sn}_to_X{dx}Y{dy}N{dn}"
        rbf_a, msg = build(a_tag, sx, sy, sn, dx, dy, dn, clk_pin=ALT_PIN)
        print(f"  {ALT_PIN[4:]} build: {msg}")
        if rbf_a is None:
            continue
        diff = cram_diff(rbf_e, rbf_a)
        print(f"  E1 vs {ALT_PIN[4:]}: {len(diff)} cells")
        per_sink[key] = sorted([list(c) for c in diff])

    if not per_sink:
        print("no data")
        return

    sets = [set(tuple(c) for c in v) for v in per_sink.values()]
    inter = set.intersection(*sets) if sets else set()
    union = set.union(*sets) if sets else set()
    print(f"\n=== Summary ===")
    print(f"  per-sink diffs : {[len(v) for v in per_sink.values()]}")
    print(f"  union          : {len(union)}")
    print(f"  intersection   : {len(inter)}  <-- candidate CLK_pin → GCLK_idx MUX bits")
    if inter:
        print(f"\n  intersection cells (sink-independent CLK_pin selector):")
        for off, bp in sorted(inter):
            frame = (off - 32) // 210
            print(f"    off={off:6d} bp={bp}  frame={frame}")

    OUT.write_text(json.dumps({
        "src": list(SRC),
        "sinks": [list(s) for s in SINKS],
        "baseline_pin": "PIN_E1",
        "alt_pin": ALT_PIN,
        "per_sink_diff": per_sink,
        "union": sorted([list(c) for c in union]),
        "intersection": sorted([list(c) for c in inter]),
    }, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
