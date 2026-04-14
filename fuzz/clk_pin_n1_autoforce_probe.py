# SPDX-License-Identifier: GPL-3.0-or-later
"""PIN_N1 direct forced-vs-auto spine probe.

Fills the gap in clk_cross_pin_spine_check.json: currently only PIN_E1
and PIN_R8 have direct forced-vs-auto intersections.  PIN_N1's cell
set was inferred from triangulation (7 cells).  This probe measures
it directly.

For each sink (same 3 used by the triangulation probe):
  build AUTO baseline with CLK=PIN_N1 (unassigned GLOBAL_SIGNAL)
  build FORCED  with CLK=PIN_N1 (set_instance_assignment GLOBAL_SIGNAL)
  diff[i] = forced^auto at sink i

Sink-independent PIN_N1 spine = intersection over all sinks.
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

HDR = 32
FRAME = 210
CRC_SLOT = 208

SRC = (10, 10, 0)
SINKS = [(10, 4, 0), (10, 16, 0), (22, 10, 0)]
CLK_PIN = "PIN_N1"


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
        if (i - HDR) % FRAME >= CRC_SLOT:
            continue
        x = a[i] ^ b[i]
        if x:
            for bp in range(8):
                if (x >> bp) & 1:
                    out.add((i, bp))
    return out


def build(tag: str, sink, *, forced: bool):
    sx, sy, sn = SRC
    dx, dy, dn = sink
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
    WORK.mkdir(parents=True, exist_ok=True)
    print(f"=== PIN_N1 direct forced-vs-auto spine probe ===")
    diffs = []
    for sink in SINKS:
        sx, sy, sn = SRC
        dx, dy, dn = sink
        print(f"\n[sink {sink}]")
        # AUTO (no GLOBAL_SIGNAL assertion)
        a_tag = f"fgclk_AUTO_N1_X{sx}Y{sy}N{sn}_to_X{dx}Y{dy}N{dn}"
        rbf_a, msg = build(a_tag, sink, forced=False)
        print(f"  auto  : {msg}")
        # FORCED
        f_tag = f"fgclk_N1_X{sx}Y{sy}N{sn}_to_X{dx}Y{dy}N{dn}"
        rbf_f, msg = build(f_tag, sink, forced=True)
        print(f"  forced: {msg}")
        if None in (rbf_a, rbf_f):
            continue
        d = cram_diff(rbf_a, rbf_f)
        print(f"  forced-vs-auto: {len(d)} cells")
        diffs.append(d)

    if len(diffs) < 2:
        print("\nneed ≥2 sinks; aborting")
        return

    spine = set.intersection(*diffs)
    print(f"\n=== Result PIN_N1 ===")
    print(f"  sink-independent intersection: {len(spine)} cells")
    for off, bp in sorted(spine):
        frame = (off - HDR) // FRAME
        print(f"    off={off:6d} bp={bp}  frame={frame}")

    # Update the cross-pin spine JSON
    spine_json = REPO / "results" / "clk_cross_pin_spine_check.json"
    data = json.loads(spine_json.read_text())
    data["per_pin_forced_vs_auto_intersection"]["PIN_N1"] = sorted(
        [list(c) for c in spine])
    # refresh overlap count
    e1 = set(tuple(c) for c in
             data["per_pin_forced_vs_auto_intersection"].get("PIN_E1", []))
    r8 = set(tuple(c) for c in
             data["per_pin_forced_vs_auto_intersection"].get("PIN_R8", []))
    n1 = spine
    data["cross_pin_overlap"] = {
        "E1_vs_R8": len(e1 & r8),
        "E1_vs_N1": len(e1 & n1),
        "R8_vs_N1": len(r8 & n1),
        "all_three": len(e1 & r8 & n1),
    }
    spine_json.write_text(json.dumps(data, indent=2))
    print(f"\nupdated {spine_json}")
    print(f"  cross-pin overlap: {data['cross_pin_overlap']}")


if __name__ == "__main__":
    main()
