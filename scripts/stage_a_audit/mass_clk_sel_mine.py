# SPDX-License-Identifier: GPL-3.0-or-later
"""Mass-parallel CLK_SEL mining for all design LABs.

Mines LAB_CLK_SEL + LAB_CLK_SEL_LE data for every LAB that has a DFF
in the NEORV32 design.  Parallelizes Quartus builds across LABs.

Optimization: only mines the N-slots each LAB actually uses in the
design (plus 1-2 extras for robust intersection), reducing builds
from ~14k to ~4k for the NEORV32 design.

For each target LAB (dx, dy):
  - Builds 2 variants (FORCE GCLK vs AUTO) at needed N-slots
  - Diffs forced-vs-auto to get per-N CLK_SEL cells
  - Intersects all N-slots to get N-invariant LAB_CLK_SEL
  - Writes probe JSON to results/clk_lab_sel_probe_X{x}Y{y}.json

Usage:
    python3 scripts/stage_a_audit/mass_clk_sel_mine.py --workers 8
    python3 scripts/stage_a_audit/mass_clk_sel_mine.py --workers 8 --fasm tmp/ax301_v2.fasm
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "fuzz"))

from compile import compile_and_export
from verilog_gen import gen_two_luts_single_input_clocked
from runner import make_lccomb
from config import ROUTE_FUZZ_PINS

RBF_DIR = REPO / "results" / "rbf"
RESULTS = REPO / "results"
SPINE_JSON = RESULTS / "clk_cross_pin_spine_check.json"

HDR = 32 + 25 * 210
CRC_SLOT = 208

SRC = (10, 10, 0)
SRC_ALT = (22, 10, 0)
ALL_N_SLOTS = list(range(0, 32, 2))  # 0,2,4,...,30
CLK_PIN = "PIN_E1"


def pick_src(target_lab):
    sx, sy, sn = SRC
    if (sx, sy) == tuple(target_lab[:2]):
        return SRC_ALT
    return SRC


def gen_qsf(placement, *, clk_pin, forced, seed=1):
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


def cram_diff(a, b):
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


def build_one(sx, sy, sn, dx, dy, dn, forced, work_dir):
    """Build a single Quartus variant. Returns (tag, rbf_bytes_or_None, msg)."""
    variant = "FORCE" if forced else "AUTO"
    tag = f"fgclk_{variant}_X{sx}Y{sy}N{sn}_to_X{dx}Y{dy}N{dn}"
    out_path = RBF_DIR / f"{tag}.rbf"

    if out_path.exists():
        return tag, out_path.read_bytes(), "cached"

    verilog = gen_two_luts_single_input_clocked(0x8888, 0xAAAA, "datab")
    placement = {
        "lut1": make_lccomb(sx, sy, sn),
        "lut2": make_lccomb(dx, dy, dn),
    }
    qsf = gen_qsf(placement, clk_pin=CLK_PIN, forced=forced)
    rbf, t, err = compile_and_export(
        tag, verilog, qsf,
        rbf_output=str(out_path),
        work_dir=str(work_dir),
    )
    if not rbf:
        return tag, None, f"FAIL: {(err or '')[:120]}"
    return tag, out_path.read_bytes(), f"{t:.1f}s"


def process_lab(dx, dy, work_base, n_slots=None):
    """Mine CLK_SEL for one LAB. Returns (dx, dy, result_dict_or_None, msg)."""
    out_path = RESULTS / f"clk_lab_sel_probe_X{dx}Y{dy}.json"
    if out_path.exists():
        return dx, dy, None, "cached"

    if n_slots is None:
        n_slots = ALL_N_SLOTS

    sx, sy, sn = pick_src((dx, dy))
    work_dir = Path(work_base) / f"clk_X{dx}Y{dy}"
    work_dir.mkdir(parents=True, exist_ok=True)

    per_n = {}
    for n in n_slots:
        # Build forced variant
        _, rbf_f, msg_f = build_one(sx, sy, sn, dx, dy, n, True, work_dir)
        if rbf_f is None:
            return dx, dy, None, f"FAIL N={n} forced: {msg_f}"

        # Build auto variant
        _, rbf_a, msg_a = build_one(sx, sy, sn, dx, dy, n, False, work_dir)
        if rbf_a is None:
            return dx, dy, None, f"FAIL N={n} auto: {msg_a}"

        diff = cram_diff(rbf_a, rbf_f)
        per_n[n] = diff

    if len(per_n) < 2:
        return dx, dy, None, "need >=2 N slots"

    # Load E1 spine to subtract
    spine_data = json.loads(SPINE_JSON.read_text())
    e1_spine = set(tuple(c) for c in
                   spine_data["per_pin_forced_vs_auto_intersection"]["PIN_E1"])

    shared = set.intersection(*per_n.values())
    clk_sel = shared - e1_spine

    result = {
        "src": [sx, sy, sn],
        "target_lab": [dx, dy],
        "n_slots": list(n_slots),
        "clk_pin": CLK_PIN,
        "e1_spine_subtracted": sorted([list(c) for c in e1_spine]),
        "per_n_forced_vs_auto": {
            str(n): sorted([list(c) for c in cells])
            for n, cells in per_n.items()
        },
        "n_invariant_shared": sorted([list(c) for c in shared]),
        "lab_clk_sel": sorted([list(c) for c in clk_sel]),
    }
    out_path.write_text(json.dumps(result, indent=2))
    return dx, dy, result, f"OK {len(clk_sel)} cells"


def get_design_labs(fasm_path):
    """Extract LABs and per-LAB N-slots from the FASM file."""
    from collections import defaultdict
    labs = set()
    lab_n_slots = defaultdict(set)
    with open(fasm_path) as f:
        for line in f:
            m = re.match(r'LAB_CLK_SEL\s+X(\d+)Y(\d+)\s*$', line)
            if m:
                labs.add((int(m.group(1)), int(m.group(2))))
            m = re.match(r'LAB_CLK_SEL_LE\s+X(\d+)Y(\d+)N(\d+)', line)
            if m:
                x, y, n = int(m.group(1)), int(m.group(2)), int(m.group(3))
                lab_n_slots[(x, y)].add(n)
    return sorted(labs), lab_n_slots


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4,
                    help="max parallel LAB probes")
    ap.add_argument("--fasm", default="tmp/ax301_v2.fasm",
                    help="FASM file to extract design LABs from")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--work-base", default="tmp/mass_clk_sel",
                    help="base work directory for Quartus builds")
    args = ap.parse_args()

    labs, lab_n_slots = get_design_labs(args.fasm)

    # For each LAB, compute the minimum N-slot set:
    # design-needed N-slots + extras for robust intersection (min 3 total)
    lab_mine_slots = {}
    for dx, dy in labs:
        needed = lab_n_slots.get((dx, dy), set())
        slots = set(needed)
        # Add extras for robust intersection (need at least 3 distinct slots)
        extras = sorted(set(ALL_N_SLOTS) - slots)
        while len(slots) < 3 and extras:
            slots.add(extras.pop(0))
        lab_mine_slots[(dx, dy)] = sorted(slots)

    # Filter out already-mined LABs
    todo = []
    cached = 0
    for dx, dy in labs:
        probe = RESULTS / f"clk_lab_sel_probe_X{dx}Y{dy}.json"
        if probe.exists():
            cached += 1
        else:
            todo.append((dx, dy))

    # Count how many RBFs are already cached
    n_cached_rbf = 0
    n_total_rbf = 0
    for dx, dy in todo:
        sx, sy, sn = pick_src((dx, dy))
        slots = lab_mine_slots.get((dx, dy), ALL_N_SLOTS)
        for n in slots:
            n_total_rbf += 2
            for variant in ("FORCE", "AUTO"):
                tag = f"fgclk_{variant}_X{sx}Y{sy}N{sn}_to_X{dx}Y{dy}N{n}"
                if (RBF_DIR / f"{tag}.rbf").exists():
                    n_cached_rbf += 1

    print(f"Design LABs needing CLK_SEL: {len(labs)}")
    print(f"  Already mined: {cached}")
    print(f"  To mine: {len(todo)}")
    print(f"  Total builds needed: {n_total_rbf}")
    print(f"  Already cached RBFs: {n_cached_rbf}")
    print(f"  New builds: {n_total_rbf - n_cached_rbf}")
    print(f"  Workers: {args.workers}")
    avg_slots = sum(len(lab_mine_slots.get((dx,dy), ALL_N_SLOTS))
                    for dx,dy in todo) / max(len(todo), 1)
    print(f"  Avg N-slots per LAB: {avg_slots:.1f} (vs 16 full)")

    if args.dry_run:
        return

    if not todo:
        print("Nothing to do.")
        return

    work_base = Path(args.work_base)
    work_base.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    done = 0
    failed = []

    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futures = {
            ex.submit(process_lab, dx, dy, str(work_base),
                      lab_mine_slots.get((dx, dy), ALL_N_SLOTS)): (dx, dy)
            for dx, dy in todo
        }
        for fut in as_completed(futures):
            dx, dy = futures[fut]
            done += 1
            try:
                _, _, result, msg = fut.result()
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed > 0 else 0
                eta = (len(todo) - done) / rate if rate > 0 else 0
                print(f"[{done}/{len(todo)}] LAB({dx:2d},{dy:2d}): {msg}"
                      f"  ({elapsed:.0f}s elapsed, ETA {eta:.0f}s)",
                      flush=True)
                if "FAIL" in msg:
                    failed.append((dx, dy, msg))
            except Exception as e:
                done_str = f"[{done}/{len(todo)}]"
                print(f"{done_str} LAB({dx},{dy}): EXCEPTION {e}", flush=True)
                failed.append((dx, dy, str(e)))

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.0f}s. Mined {done - len(failed)}/{len(todo)} LABs.")
    if failed:
        print(f"Failed: {len(failed)}")
        for dx, dy, msg in failed:
            print(f"  LAB({dx},{dy}): {msg}")


if __name__ == "__main__":
    main()
