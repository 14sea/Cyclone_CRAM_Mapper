# SPDX-License-Identifier: GPL-3.0-or-later
"""3rd-CLK-pin triangulation probe — isolate pure source-MUX bits.

Builds forced-GCLK designs at 3 sinks for a 3rd candidate CLK pin, diffs
against the cached E1 and R8 forced builds, and intersects pair-diffs.

Triangulation logic:
  E1→GCLK2, R8→GCLK3, PIN_C→GCLK_x (x != 2,3)
  inter_AB = sink-indep cells that differ between A and B pin
           = IOB(A) ⊕ IOB(B) + source-MUX(2,3)
  inter_AC = IOB(A) ⊕ IOB(C) + source-MUX(2,x)
  inter_BC = IOB(B) ⊕ IOB(C) + source-MUX(3,x)
  inter_ABC = cells that differ in all 3 pairs
            = cells that depend on the specific GCLK index chosen
            = pure source-MUX bits (pin-specific IOB cells cancel from the
              pair not involving their pin)

Candidate 3rd pins (try in order, take first one Quartus accepts AND
maps to a NEW GCLK index):
  PIN_M1, PIN_N1, PIN_T13, PIN_G16, PIN_L1, PIN_H2
"""
from __future__ import annotations

import json
import os
import re
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
OUT = REPO / "results" / "clk_pin_triangulate_probe.json"

HDR = 32 + 25 * 210
CRC_SLOT = 208

SRC = (10, 10, 0)
SINKS = [(10, 4, 0), (10, 16, 0), (22, 10, 0)]
CANDIDATES = ["PIN_M1", "PIN_N1", "PIN_T13", "PIN_G16", "PIN_L1", "PIN_H2"]


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
        return out_path.read_bytes(), "cached", None
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
        return None, f"FAIL: {(err or '')[:120]}", None
    # parse fit.rpt for GCLK index
    gclk_idx = None
    fit = (WORK / tag / "output_files" / f"{tag}.fit.rpt")
    if fit.exists():
        text = fit.read_text(errors="replace")
        m = re.search(r"CLK\s*;\s*PIN_\w+\s*;\s*\d+\s*;\s*Clock\s*;\s*yes\s*;\s*Global Clock\s*;\s*GCLK(\d+)", text)
        if m:
            gclk_idx = int(m.group(1))
    return out_path.read_bytes(), f"{t:.1f}s", gclk_idx


def pick_third_pin() -> tuple[str, int] | None:
    """Try candidates at the first sink; return (pin, gclk_idx) for the
    first one that Quartus accepts AND maps to a GCLK index != 2, 3."""
    dx, dy, dn = SINKS[0]
    sx, sy, sn = SRC
    for pin in CANDIDATES:
        tag = f"fgclk_{pin[4:]}_X{sx}Y{sy}N{sn}_to_X{dx}Y{dy}N{dn}"
        rbf, msg, gclk = build(tag, sx, sy, sn, dx, dy, dn, clk_pin=pin)
        print(f"  probe {pin}: {msg} (GCLK={gclk})")
        if rbf is None:
            continue
        if gclk is None:
            print(f"    fit.rpt parse failed, skip")
            continue
        if gclk in (2, 3):
            print(f"    same GCLK index as E1/R8; skip")
            continue
        return pin, gclk
    return None


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    print("=== 3rd-CLK-pin triangulation probe ===")
    print("  searching for candidate pin with new GCLK index...")

    picked = pick_third_pin()
    if picked is None:
        print("\nno acceptable 3rd pin found among candidates")
        return
    pin_c, gclk_c = picked
    print(f"\n==> using {pin_c} → GCLK{gclk_c}")

    per_sink = {}
    for dx, dy, dn in SINKS:
        sx, sy, sn = SRC
        key = f"{dx},{dy},{dn}"
        print(f"\n[{key}]")
        # cached E1 (fgclk_FORCE_*)
        e_tag = f"fgclk_FORCE_X{sx}Y{sy}N{sn}_to_X{dx}Y{dy}N{dn}"
        rbf_e, msg, _ = build(e_tag, sx, sy, sn, dx, dy, dn, clk_pin="PIN_E1")
        print(f"  E1 : {msg}")
        # cached R8 (fgclk_R8_*)
        r_tag = f"fgclk_R8_X{sx}Y{sy}N{sn}_to_X{dx}Y{dy}N{dn}"
        rbf_r, msg, _ = build(r_tag, sx, sy, sn, dx, dy, dn, clk_pin="PIN_R8")
        print(f"  R8 : {msg}")
        # new pin C
        c_tag = f"fgclk_{pin_c[4:]}_X{sx}Y{sy}N{sn}_to_X{dx}Y{dy}N{dn}"
        rbf_c, msg, _ = build(c_tag, sx, sy, sn, dx, dy, dn, clk_pin=pin_c)
        print(f"  {pin_c[4:]:4s}: {msg}")
        if None in (rbf_e, rbf_r, rbf_c):
            continue
        diff_ab = cram_diff(rbf_e, rbf_r)
        diff_ac = cram_diff(rbf_e, rbf_c)
        diff_bc = cram_diff(rbf_r, rbf_c)
        print(f"  E1 vs R8 : {len(diff_ab)} cells")
        print(f"  E1 vs {pin_c[4:]}: {len(diff_ac)} cells")
        print(f"  R8 vs {pin_c[4:]}: {len(diff_bc)} cells")
        per_sink[key] = {
            "E1_R8": sorted([list(c) for c in diff_ab]),
            "E1_C":  sorted([list(c) for c in diff_ac]),
            "R8_C":  sorted([list(c) for c in diff_bc]),
        }

    if not per_sink:
        print("no data")
        return

    # Sink-independent intersection per pair
    def inter_pair(k):
        sets = [set(tuple(c) for c in v[k]) for v in per_sink.values()]
        return set.intersection(*sets) if sets else set()

    inter_ab = inter_pair("E1_R8")
    inter_ac = inter_pair("E1_C")
    inter_bc = inter_pair("R8_C")
    triangulated = inter_ab & inter_ac & inter_bc
    # Pin-A-specific IOB: in (AB) and (AC) but NOT in (BC)
    iob_a = (inter_ab & inter_ac) - inter_bc
    iob_b = (inter_ab & inter_bc) - inter_ac
    iob_c = (inter_ac & inter_bc) - inter_ab

    print(f"\n=== Sink-indep pair-intersections ===")
    print(f"  E1-R8  : {len(inter_ab)} cells")
    print(f"  E1-{pin_c[4:]:3s}: {len(inter_ac)} cells")
    print(f"  R8-{pin_c[4:]:3s}: {len(inter_bc)} cells")
    print(f"\n=== Triangulation ===")
    print(f"  pure source-MUX (all 3 pairs) : {len(triangulated)} cells")
    for off, bp in sorted(triangulated):
        frame = (off - 32) // 210
        print(f"    off={off:6d} bp={bp}  frame={frame}")
    print(f"  IOB(E1) specific               : {len(iob_a)} cells")
    for off, bp in sorted(iob_a):
        frame = (off - 32) // 210
        print(f"    off={off:6d} bp={bp}  frame={frame}")
    print(f"  IOB(R8) specific               : {len(iob_b)} cells")
    for off, bp in sorted(iob_b):
        frame = (off - 32) // 210
        print(f"    off={off:6d} bp={bp}  frame={frame}")
    print(f"  IOB({pin_c[4:]}) specific              : {len(iob_c)} cells")
    for off, bp in sorted(iob_c):
        frame = (off - 32) // 210
        print(f"    off={off:6d} bp={bp}  frame={frame}")

    OUT.write_text(json.dumps({
        "src": list(SRC),
        "sinks": [list(s) for s in SINKS],
        "pins": {"A": "PIN_E1", "B": "PIN_R8", "C": pin_c},
        "gclk_index": {"A": 2, "B": 3, "C": gclk_c},
        "per_sink_pair_diffs": per_sink,
        "inter_E1_R8":          sorted([list(c) for c in inter_ab]),
        "inter_E1_C":           sorted([list(c) for c in inter_ac]),
        "inter_R8_C":           sorted([list(c) for c in inter_bc]),
        "triangulated_source_mux": sorted([list(c) for c in triangulated]),
        "iob_E1_specific":      sorted([list(c) for c in iob_a]),
        "iob_R8_specific":      sorted([list(c) for c in iob_b]),
        "iob_C_specific":       sorted([list(c) for c in iob_c]),
    }, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
