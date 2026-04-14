# SPDX-License-Identifier: GPL-3.0-or-later
"""Find real GCLK_BUS bits by forcing global-clock promotion.

The default `clk_gclk_probe.py` showed `Global clocks: 0/10` in every
fit report — Quartus' Auto Global Clock heuristic refuses to burn a
GCLK on a tiny 1-FF design.  So the 16 cells the probe extracted are
NOT the GCLK_IN MUX or the global clock spine; they are per-LAB local
clock distribution / IOB clock-input config.

This probe forces the issue with::

    set_instance_assignment -name GLOBAL_SIGNAL "GLOBAL CLOCK" -to CLK

and diffs the forced-GCLK build against the Auto-only build of the
same design.  Cells that flip ONLY when GCLK is forced = real
GCLK_IN-MUX + GCLK_BUS spine bits.

Same lut1→lut2→DFF design as clk_gclk_probe.py.  Two sinks for
spine-vs-LAB cross-check.

Output: results/clk_force_gclk_probe.json
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
OUT = REPO / "results" / "clk_force_gclk_probe.json"

HDR = 32 + 25 * 210  # 5282
CRC_SLOT = 208

SRC = (10, 10, 0)
SINKS = [
    (10, 4, 0),
    (10, 16, 0),
    (22, 10, 0),
]


def gen_qsf(placement: dict, *, force_global: bool, seed: int = 1) -> str:
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
        lines.append(f'set_location_assignment {pin} -to {sig}')
    for inst, loc in placement.items():
        lines.append(f'set_location_assignment {loc} -to "{inst}"')
    if force_global:
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


def build(tag: str, sx, sy, sn, dx, dy, dn, *, force_global: bool):
    out_path = RBF / f"{tag}.rbf"
    if out_path.exists():
        return out_path.read_bytes(), "cached"
    verilog = gen_two_luts_single_input_clocked(0x8888, 0xAAAA, "datab")
    placement = {
        "lut1": make_lccomb(sx, sy, sn),
        "lut2": make_lccomb(dx, dy, dn),
    }
    qsf = gen_qsf(placement, force_global=force_global)
    rbf, t, err = compile_and_export(
        tag, verilog, qsf,
        rbf_output=str(out_path),
        work_dir=str(WORK),
    )
    if not rbf:
        return None, f"FAIL: {(err or '')[:120]}"
    return out_path.read_bytes(), f"{t:.1f}s"


def check_gclk_used(tag: str) -> str:
    rpt = WORK / tag / "output_files" / f"{tag}.fit.rpt"
    if not rpt.exists():
        return "no rpt"
    text = rpt.read_text(errors="replace")
    for line in text.splitlines():
        if "Global clocks" in line and "/" in line and "%" in line:
            parts = line.split(";")
            if len(parts) >= 3:
                return parts[2].strip()
    return "?"


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    print(f"=== Forced-GCLK probe ===")

    per_force = {}   # sink -> set of cells that flip only with forced GCLK
    fit_reports = {}

    for dx, dy, dn in SINKS:
        sx, sy, sn = SRC
        key = f"{dx},{dy},{dn}"
        print(f"\n[{key}]")
        # Auto baseline (matches clk_gclk_probe's clocked variant)
        utag = f"fgclk_AUTO_X{sx}Y{sy}N{sn}_to_X{dx}Y{dy}N{dn}"
        rbf_auto, msg = build(utag, sx, sy, sn, dx, dy, dn,
                              force_global=False)
        print(f"  AUTO   build: {msg}")
        if rbf_auto is None:
            continue
        gauto = check_gclk_used(utag)
        # Forced
        ftag = f"fgclk_FORCE_X{sx}Y{sy}N{sn}_to_X{dx}Y{dy}N{dn}"
        rbf_forced, msg = build(ftag, sx, sy, sn, dx, dy, dn,
                                force_global=True)
        print(f"  FORCE  build: {msg}")
        if rbf_forced is None:
            continue
        gforce = check_gclk_used(ftag)
        fit_reports[key] = {"auto": gauto, "forced": gforce}
        diff = cram_diff(rbf_auto, rbf_forced)
        print(f"  diff: {len(diff)} cells   "
              f"(GCLK auto={gauto!r}  forced={gforce!r})")
        per_force[key] = sorted([list(c) for c in diff])

    if not per_force:
        print("no data")
        return

    # Intersection across sinks: cells flipped on every forced build
    sets = [set(tuple(c) for c in v) for v in per_force.values()]
    inter = set.intersection(*sets) if sets else set()
    union = set.union(*sets) if sets else set()
    print(f"\n=== Summary ===")
    print(f"  per-sink diffs: {[len(v) for v in per_force.values()]}")
    print(f"  union         : {len(union)}")
    print(f"  intersection  : {len(inter)}  <-- candidate GCLK_BUS spine")

    OUT.write_text(json.dumps({
        "src": list(SRC),
        "sinks": [list(s) for s in SINKS],
        "per_sink_force_diff": per_force,
        "union": sorted([list(c) for c in union]),
        "intersection": sorted([list(c) for c in inter]),
        "fit_reports": fit_reports,
    }, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
