# SPDX-License-Identifier: GPL-3.0-or-later
"""Demand-driven route mining: compile missing sig-cache entries from np2fasm.

Reads np2fasm's FASM output to identify missing ROUTE entries, groups by
unique (src_LAB, dst_LAB) pairs, and mines each via the standard two-LUT
pair template (gen_two_luts_single_input_clocked + gen_qsf_ce10).

Usage:
    python3 scripts/route_mining/mine_missing_routes.py \
        --fasm tmp/ax301.fasm \
        --parallel 4 \
        [--limit 100]        # mine first N routes only (for testing)
        [--dry-run]          # just print what would be mined
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))

from verilog_gen import gen_two_luts_single_input_clocked
from plan_d_prime_factory import gen_qsf_ce10
from compile import compile_and_export
NV_ZERO_PATH = ROOT / "results" / "rbf" / "nv_zero_global.rbf"


def read_rbf(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


CELLS_FULL_PATH = ROOT / "results" / "route_cells_full.json"
WORK_BASE = ROOT / "tmp" / "route_mine"


def parse_missing_routes(fasm_path: str) -> list[tuple[int, int, int, int, int, int, str]]:
    """Extract (sx, sy, sn, dx, dy, dn, port) from ROUTE FASM lines."""
    routes = []
    pat = re.compile(
        r"^ROUTE\s+X(\d+)Y(\d+)N(\d+)\s+->\s+X(\d+)Y(\d+)N(\d+)\.(data[a-d])"
    )
    with open(fasm_path) as f:
        for line in f:
            m = pat.match(line.strip())
            if m:
                sx, sy, sn = int(m.group(1)), int(m.group(2)), int(m.group(3))
                dx, dy, dn = int(m.group(4)), int(m.group(5)), int(m.group(6))
                port = m.group(7)
                routes.append((sx, sy, sn, dx, dy, dn, port))
    return routes


def load_existing_cache() -> dict:
    if CELLS_FULL_PATH.exists():
        with open(CELLS_FULL_PATH) as f:
            return json.load(f)
    return {}


def route_key(sx, sy, sn, dx, dy, dn, port) -> str:
    return f"{sx},{sy},{sn}->{dx},{dy},{dn},{port}"


def mine_single_route(
    sx: int, sy: int, sn: int,
    dx: int, dy: int, dn: int,
    port: str,
    zero_rbf: bytes,
    work_dir: Path,
) -> tuple[str, list[list[int]] | None, str]:
    """Mine a single route. Returns (key, cells_or_None, error_msg)."""
    key = route_key(sx, sy, sn, dx, dy, dn, port)

    verilog = gen_two_luts_single_input_clocked(0x8888, 0xAAAA,
                                                 connect_port=port)
    placement = {
        "lut1": f"LCCOMB_X{sx}_Y{sy}_N{sn}",
        "lut2": f"LCCOMB_X{dx}_Y{dy}_N{dn}",
    }
    qsf = gen_qsf_ce10(placement, seed=1)

    tag = f"mine_X{sx}Y{sy}N{sn}__X{dx}Y{dy}N{dn}_{port}"
    rbf_out = str(work_dir / f"{tag}.rbf")

    try:
        rbf_path, elapsed, err = compile_and_export(
            tag, verilog, qsf, rbf_output=rbf_out,
            work_dir=str(work_dir),
        )
        if not rbf_path or not os.path.exists(rbf_path):
            return key, None, f"compile failed: {err}"

        target_rbf = read_rbf(rbf_path)
        if len(target_rbf) != len(zero_rbf):
            return key, None, f"rbf size mismatch: {len(target_rbf)} vs {len(zero_rbf)}"

        cells = []
        for off in range(len(zero_rbf)):
            diff = target_rbf[off] ^ zero_rbf[off]
            if diff:
                for bp in range(8):
                    if diff & (1 << bp):
                        cells.append([off, bp])

        # Filter to CRAM-only (offset >= 5282, skip header band noise)
        cells = [c for c in cells if c[0] >= 5282]

        return key, cells, ""

    except Exception as e:
        return key, None, str(e)
    finally:
        proj_dir = work_dir / tag
        if proj_dir.exists():
            shutil.rmtree(proj_dir, ignore_errors=True)
        if os.path.exists(rbf_out):
            os.unlink(rbf_out)


def main():
    parser = argparse.ArgumentParser(description="Mine missing sig-cache routes")
    parser.add_argument("--fasm", required=True, help="FASM file from np2fasm")
    parser.add_argument("--parallel", type=int, default=4,
                        help="Number of parallel Quartus jobs")
    parser.add_argument("--limit", type=int, default=0,
                        help="Mine only first N missing routes (0=all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Just print what would be mined")
    args = parser.parse_args()

    # Load zero baseline
    zero_path = str(NV_ZERO_PATH)
    if not os.path.exists(zero_path):
        print(f"ERROR: zero baseline not found at {zero_path}")
        sys.exit(1)
    zero_rbf = read_rbf(zero_path)

    # Parse all ROUTE lines from FASM
    all_routes = parse_missing_routes(args.fasm)
    print(f"Total ROUTE lines in FASM: {len(all_routes)}")

    # Filter to missing (not in sig-cache), deduplicate
    cache = load_existing_cache()
    seen_keys = set()
    missing = []
    for r in all_routes:
        key = route_key(*r)
        if key not in cache and key not in seen_keys:
            missing.append(r)
            seen_keys.add(key)
    print(f"Missing from sig-cache: {len(missing)} (deduplicated)")

    if args.limit > 0:
        missing = missing[:args.limit]
        print(f"Limited to first {args.limit}")

    if args.dry_run:
        for r in missing[:20]:
            print(f"  would mine: {route_key(*r)}")
        if len(missing) > 20:
            print(f"  ... and {len(missing) - 20} more")
        return

    # Create work directory
    WORK_BASE.mkdir(parents=True, exist_ok=True)

    # Mine routes
    t0 = time.time()
    n_ok = 0
    n_fail = 0
    new_entries = {}

    if args.parallel <= 1:
        for i, r in enumerate(missing):
            key, cells, err = mine_single_route(*r, zero_rbf, WORK_BASE)
            if cells is not None:
                new_entries[key] = cells
                n_ok += 1
            else:
                n_fail += 1
                print(f"  FAIL {key}: {err}")
            if (i + 1) % 10 == 0:
                print(f"  [{i+1}/{len(missing)}] ok={n_ok} fail={n_fail} "
                      f"({time.time()-t0:.0f}s)")
    else:
        save_interval = 500
        with ProcessPoolExecutor(max_workers=args.parallel) as pool:
            futures = {}
            for r in missing:
                f = pool.submit(mine_single_route, *r, zero_rbf, WORK_BASE)
                futures[f] = r

            for i, f in enumerate(as_completed(futures)):
                key, cells, err = f.result()
                if cells is not None:
                    new_entries[key] = cells
                    n_ok += 1
                else:
                    n_fail += 1
                    if err:
                        print(f"  FAIL {key}: {err}")
                if (i + 1) % 50 == 0:
                    print(f"  [{i+1}/{len(missing)}] ok={n_ok} fail={n_fail} "
                          f"({time.time()-t0:.0f}s)")
                if (i + 1) % save_interval == 0 and new_entries:
                    cache.update(new_entries)
                    _tmp = str(CELLS_FULL_PATH) + ".tmp"
                    with open(_tmp, "w") as _f:
                        json.dump(cache, _f, separators=(",", ":"))
                    os.replace(_tmp, str(CELLS_FULL_PATH))
                    print(f"  [checkpoint] saved {len(cache)} entries "
                          f"(+{len(new_entries)} new)")
                    new_entries = {}

    elapsed = time.time() - t0
    print(f"\nDone: {n_ok} mined, {n_fail} failed in {elapsed:.0f}s")
    print(f"  ({elapsed/max(len(missing),1):.1f}s per route)")

    # Merge into sig-cache
    if new_entries:
        cache.update(new_entries)
        tmp = str(CELLS_FULL_PATH) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(cache, f, separators=(",", ":"))
        os.replace(tmp, str(CELLS_FULL_PATH))
        print(f"Updated {CELLS_FULL_PATH}: {len(cache)} total entries "
              f"(+{len(new_entries)} new)")


if __name__ == "__main__":
    main()
