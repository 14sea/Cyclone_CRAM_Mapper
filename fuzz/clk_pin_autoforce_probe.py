# SPDX-License-Identifier: GPL-3.0-or-later
"""Generic forced-vs-auto GCLK_PIN spine probe.

Generalized from `clk_pin_n1_autoforce_probe.py` to mine the sink-
independent per-pin one-hot activate set for any clock-capable pin
(E1, R8, N1, E2, M1, M2, H1, T4, R4, M16, M15, E15, A14, B14, ...).

For each sink, build:
  AUTO   baseline (CLK=PIN, no GLOBAL_SIGNAL)
  FORCED (CLK=PIN, set_instance_assignment GLOBAL_SIGNAL "GLOBAL CLOCK")
  diff[i] = forced ^ auto at sink i   (CRAM-band only)

Sink-independent PIN_X spine = intersection over all sinks.  Appended
to results/clk_cross_pin_spine_check.json under
`per_pin_forced_vs_auto_intersection[PIN_X]`, and cross-pin overlap
counts refreshed for the E1/R8/N1 triad (legacy sanity) plus the new
pin.

Usage:
    python3 fuzz/clk_pin_autoforce_probe.py --pin M1
    python3 fuzz/clk_pin_autoforce_probe.py --pin M1 --pin T4
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
WORK = REPO / "tmp" / "force_gclk"

HDR = 32
FRAME = 210
CRC_SLOT = 208

SRC = (10, 10, 0)
SINKS = [(10, 4, 0), (10, 16, 0), (22, 10, 0)]


def gen_qsf(placement: dict, *, clk_pin: str, forced: bool,
            seed: int = 1) -> str:
    """Build a QSF for the probe design.

    Handles pin collisions: if ROUTE_FUZZ_PINS already maps some signal
    to `clk_pin`, that signal is reassigned to a free pin.  This is
    necessary for CLK candidates like PIN_M16/PIN_M15 that overlap with
    KEY3/KEY4 in the default harness.
    """
    lines = [
        'set_global_assignment -name FAMILY "Cyclone IV E"',
        "set_global_assignment -name DEVICE EP4CE6F17C8",
        "set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top",
        "set_global_assignment -name VERILOG_FILE fuzz_top.v",
        'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files',
        'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"',
        f"set_global_assignment -name SEED {seed}",
    ]

    # Safe free user IO pins we can use as substitutes (none of these
    # are dedicated clock pins on F17 and none collide with the
    # lut_prim LAB(10,10).
    SAFE_SUBS = ["PIN_T15", "PIN_T12", "PIN_R14", "PIN_T13", "PIN_N13",
                 "PIN_L16", "PIN_K16", "PIN_N14", "PIN_P16", "PIN_R16"]

    used = {clk_pin}
    assigned = {}
    for sig, pin in ROUTE_FUZZ_PINS.items():
        if sig == "CLK":
            target = clk_pin
        elif pin == clk_pin:
            # collision — pick a free SAFE pin
            target = next(p for p in SAFE_SUBS if p not in used)
        else:
            target = pin
        assigned[sig] = target
        used.add(target)

    for sig, pin in assigned.items():
        lines.append(f'set_location_assignment {pin} -to {sig}')
    for inst, loc in placement.items():
        lines.append(f'set_location_assignment {loc} -to "{inst}"')
    if forced:
        lines.append(
            'set_instance_assignment -name GLOBAL_SIGNAL '
            '"GLOBAL CLOCK" -to CLK')
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


def build(tag: str, sink, *, clk_pin: str, forced: bool):
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
    qsf = gen_qsf(placement, clk_pin=f"PIN_{clk_pin}", forced=forced)
    rbf, t, err = compile_and_export(
        tag, verilog, qsf,
        rbf_output=str(out_path),
        work_dir=str(WORK),
    )
    if not rbf:
        return None, f"FAIL: {(err or '')[:160]}"
    return out_path.read_bytes(), f"{t:.1f}s"


def mine_pin(pin: str) -> set | None:
    """Run 3-sink forced-vs-auto probe, return sink-independent spine.

    Returns None if any build failed or <2 sinks produced diffs.
    """
    WORK.mkdir(parents=True, exist_ok=True)
    print(f"\n=== forced-vs-auto probe: PIN_{pin} ===")
    diffs = []
    sx, sy, sn = SRC
    for sink in SINKS:
        dx, dy, dn = sink
        print(f"[sink {sink}]")
        a_tag = (f"fgclk_AUTO_{pin}_X{sx}Y{sy}N{sn}"
                 f"_to_X{dx}Y{dy}N{dn}")
        f_tag = (f"fgclk_{pin}_X{sx}Y{sy}N{sn}"
                 f"_to_X{dx}Y{dy}N{dn}")
        rbf_a, msg = build(a_tag, sink, clk_pin=pin, forced=False)
        print(f"  auto  : {msg}")
        if rbf_a is None:
            print(f"  [{pin}] auto build FAILED at sink {sink}")
            return None
        rbf_f, msg = build(f_tag, sink, clk_pin=pin, forced=True)
        print(f"  forced: {msg}")
        if rbf_f is None:
            print(f"  [{pin}] forced build FAILED at sink {sink}")
            return None
        d = cram_diff(rbf_a, rbf_f)
        print(f"  forced-vs-auto: {len(d)} cells")
        diffs.append(d)

    if len(diffs) < 2:
        print(f"[{pin}] need ≥2 sinks; aborting")
        return None

    spine = set.intersection(*diffs)
    print(f"[{pin}] sink-independent spine: {len(spine)} cells")
    return spine


def update_spine_json(pin: str, spine: set) -> None:
    """Append pin to clk_cross_pin_spine_check.json and refresh overlaps."""
    # Allow override for parallel-worker slice files (see
    # tmp/mine_gclk_pins_batch.py).
    override = os.environ.get("CLK_SPINE_JSON_OVERRIDE")
    if override:
        spine_json = Path(override)
    else:
        spine_json = REPO / "results" / "clk_cross_pin_spine_check.json"
    data = json.loads(spine_json.read_text())
    sect = data["per_pin_forced_vs_auto_intersection"]
    sect[f"PIN_{pin}"] = sorted([list(c) for c in spine])

    # Refresh pairwise overlap counts across ALL mined pins (drop
    # legacy 3-pin schema, replace with a dict of all pairs + per-pin
    # cell counts, while preserving the legacy E1/R8/N1 keys for
    # backward-compat).
    all_sets = {k: set(tuple(c) for c in v) for k, v in sect.items()}
    pairs = {}
    keys = sorted(all_sets)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            inter = all_sets[a] & all_sets[b]
            if len(inter):
                pairs[f"{a}_vs_{b}"] = len(inter)
    # Keep the three historical keys visible (zero if absent).
    legacy = {
        "E1_vs_R8": len(all_sets.get("PIN_E1", set())
                        & all_sets.get("PIN_R8", set())),
        "E1_vs_N1": len(all_sets.get("PIN_E1", set())
                        & all_sets.get("PIN_N1", set())),
        "R8_vs_N1": len(all_sets.get("PIN_R8", set())
                        & all_sets.get("PIN_N1", set())),
        "all_three": len(all_sets.get("PIN_E1", set())
                         & all_sets.get("PIN_R8", set())
                         & all_sets.get("PIN_N1", set())),
    }
    data["cross_pin_overlap"] = {**legacy, **pairs}
    data["per_pin_cell_counts"] = {
        k: len(v) for k, v in sorted(all_sets.items())
    }
    spine_json.write_text(json.dumps(data, indent=2))
    print(f"[{pin}] wrote {spine_json}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pin", action="append", required=True,
                    help="clock pin name without PIN_ prefix "
                         "(e.g. E1, R8, M1); repeatable")
    args = ap.parse_args()

    rc = 0
    for pin in args.pin:
        spine = mine_pin(pin)
        if spine is None:
            print(f"[{pin}] FAILED; skipping update")
            rc = 1
            continue
        update_spine_json(pin, spine)

    return rc


if __name__ == "__main__":
    sys.exit(main())
