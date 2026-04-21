#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mine σ⁻¹ for fb8 ∈ {2, 5, 6} using multi-LUT FACE probes.

Builds 16-LUT Quartus probes at representative X columns:
  fb8=2: X=21   fb8=5: X=10   fb8=6: X=13
across all 18 CE6 LAB_Y values. Uses the same extraction convention
as tmp/analyze_sigma.py (verified against the existing 233-entry table).

Output: results/sigma_inv_fb8_gaps.json → then integrates into bitstream.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from itertools import permutations
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
QUARTUS_BIN = Path.home() / "intelFPGA_lite" / "21.1" / "quartus" / "bin"
WORK = REPO / "tmp" / "sigma_fb8_mine"

sys.path.insert(0, str(REPO / "fuzz"))
from config import COLUMN_BASE, LAB_Y, SLOT_BASE, cram_ctrl_addr, cram_ctrl_bit, cram_n_delta

MASK = 0xFACE
N_VALS = list(range(0, 32, 2))  # 16 N values per probe

TARGETS = {
    2: 21,  # representative X for fb8=2
    5: 10,  # representative X for fb8=5
    6: 13,  # representative X for fb8=6
}


def gen_probe_verilog():
    lines = ["module probe(input wire a, b, c, d, output wire q);"]
    wires = []
    for i in range(16):
        lines.append(f"  wire w{i};")
        lines.append(f'  cycloneive_lcell_comb #(.lut_mask("FACE")) lut{i} (')
        lines.append(f"    .dataa(a), .datab(b), .datac(c), .datad(d), .combout(w{i}));")
        wires.append(f"w{i}")
    lines.append(f"  assign q = {' | '.join(wires)};")
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def gen_probe_qsf(x, y):
    lines = [
        'set_global_assignment -name FAMILY "Cyclone IV E"',
        "set_global_assignment -name DEVICE EP4CE6F17C8",
        "set_global_assignment -name TOP_LEVEL_ENTITY probe",
        "set_global_assignment -name VERILOG_FILE probe.v",
        "set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files",
        "set_location_assignment PIN_E16 -to a",
        "set_location_assignment PIN_M16 -to b",
        "set_location_assignment PIN_M15 -to c",
        "set_location_assignment PIN_E15 -to d",
        "set_location_assignment PIN_G15 -to q",
    ]
    for i, n in enumerate(N_VALS):
        # Quartus LCCOMB uses N directly (not N//2)
        lines.append(f'set_location_assignment LCCOMB_X{x}_Y{y}_N{n} -to "lut{i}"')
    return "\n".join(lines) + "\n"


def build_probe(x, y):
    tag = f"face_X{x}_Y{y}"
    work = WORK / tag
    work.mkdir(parents=True, exist_ok=True)

    (work / "probe.v").write_text(gen_probe_verilog())
    (work / "probe.qsf").write_text(gen_probe_qsf(x, y))
    (work / "probe.qpf").write_text('PROJECT_REVISION = "probe"\n')

    env = os.environ.copy()
    env["PATH"] = str(QUARTUS_BIN) + ":" + env["PATH"]

    for step in ["quartus_map", "quartus_fit", "quartus_asm"]:
        r = subprocess.run(
            [step, "--read_settings_files=on", "--write_settings_files=off", "probe"],
            cwd=str(work), capture_output=True, env=env, timeout=180,
        )
        if r.returncode != 0:
            return x, y, None, f"{step} failed"

    r = subprocess.run(
        ["quartus_cpf", "-c", "-o", "bitstream_compression=off",
         "output_files/probe.sof", "output_files/probe.rbf"],
        cwd=str(work), capture_output=True, env=env, timeout=60,
    )
    if r.returncode != 0:
        return x, y, None, "cpf failed"

    rbf = (work / "output_files" / "probe.rbf").read_bytes()
    return x, y, rbf, "OK"


def extract_sigma_at(x, y, n, probe_rbf, nv_rbf):
    """Extract σ⁻¹ at (x,y,n) using the analyze_sigma.py convention."""
    k = n // 2
    slot = (y - 2) % 3
    group = (y - 2) // 3
    nd = cram_n_delta(n)

    wrapped = slot == 1 and (24 + group * 3 + nd < 0)
    if wrapped:
        bp = 7 - group
        addr_adj = 207
    else:
        bp = cram_ctrl_bit(y)
        addr_adj = 0

    base = cram_ctrl_addr(x, y, 0, n) + addr_adj
    foff = (base - 32) % 210
    fb8 = ((base - 32) // 210) % 8

    best_si = None
    best_err = 17
    for si in permutations(range(4)):
        sigma = [0] * 4
        for i, j in enumerate(si):
            sigma[j] = i
        err = 0
        for b in range(16):
            f0 = (b >> sigma[0]) & 1
            f1 = (b >> sigma[1]) & 1
            f2 = (b >> sigma[2]) & 1
            f3 = (b >> sigma[3]) & 1
            pair = ((1 - f0) << 2) | ((1 - f1) << 1) | (1 - f2)
            da = f3 ^ (1 - f2)
            delta = da if k % 2 == 0 else 1 - da
            addr = cram_ctrl_addr(x, y, pair, n) + delta + addr_adj
            nv_bit = (nv_rbf[addr] >> bp) & 1
            p_bit = (probe_rbf[addr] >> bp) & 1
            d = nv_bit ^ p_bit
            m = (MASK >> b) & 1
            if d != m:
                err += 1
        if err < best_err:
            best_err = err
            best_si = si

    return foff, fb8, best_si, best_err


def main():
    WORK.mkdir(parents=True, exist_ok=True)

    nv_path = REPO / "results" / "rbf" / "nv_zero_global.rbf"
    nv = nv_path.read_bytes()
    assert len(nv) == 368011

    # Build probe list
    probes = []
    for fb8, x in sorted(TARGETS.items()):
        for y in LAB_Y:
            probes.append((x, y))
    total = len(probes)
    print(f"Building {total} multi-LUT FACE probes (4-way parallel)...")
    print(f"  fb8=2 → X=21, fb8=5 → X=10, fb8=6 → X=13")

    # Build in parallel
    rbf_cache = {}
    t0 = time.time()
    done = 0
    errors = 0

    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(build_probe, x, y): (x, y) for x, y in probes}
        for fut in as_completed(futures):
            x, y, rbf, msg = fut.result()
            done += 1
            if rbf is None:
                print(f"  [{done}/{total}] X{x}Y{y}: FAIL ({msg})")
                errors += 1
            else:
                rbf_cache[(x, y)] = rbf
                if done % 10 == 0 or done == total:
                    elapsed = time.time() - t0
                    print(f"  [{done}/{total}] {elapsed:.0f}s elapsed, "
                          f"{done - errors} OK / {errors} fail")

    build_time = time.time() - t0
    print(f"\nBuild phase: {done - errors}/{total} OK in {build_time:.0f}s")

    # Extract σ⁻¹
    print("\nExtracting σ⁻¹ from FACE probes...")
    results = {}  # (foff, fb8) -> sigma_inv
    err_count = 0

    for (x, y), rbf in sorted(rbf_cache.items()):
        for n in N_VALS:
            foff, fb8, si, err = extract_sigma_at(x, y, n, rbf, nv)
            if err > 0:
                print(f"  WARNING: X{x}Y{y}N{n} foff={foff} fb8={fb8} "
                      f"best σ⁻¹={si} err={err}")
                err_count += 1
            else:
                key = (foff, fb8)
                if key in results and results[key] != si:
                    print(f"  CONFLICT: foff={foff} fb8={fb8} "
                          f"was {results[key]}, now {si} at X{x}Y{y}N{n}")
                results[key] = si

    # Summary
    by_fb8 = defaultdict(list)
    for (foff, fb8), si in results.items():
        by_fb8[fb8].append((foff, si))
    for fb8 in sorted(by_fb8.keys()):
        entries = by_fb8[fb8]
        perms = set(si for _, si in entries)
        print(f"  fb8={fb8}: {len(entries)} entries, {len(perms)} distinct permutations")
        for p in sorted(perms):
            cnt = sum(1 for _, si in entries if si == p)
            print(f"    {p}: {cnt}x")

    # Save
    out = {
        "description": "σ⁻¹ for fb8={2,5,6} mined via multi-LUT FACE probes",
        "mining_date": "2026-04-21",
        "mask": f"0x{MASK:04X}",
        "errors": err_count,
        "entries": {},
    }
    for (foff, fb8), si in sorted(results.items()):
        out["entries"][f"{foff},{fb8}"] = {
            "foff": foff, "fb8": fb8, "sigma_inv": list(si)
        }

    out_path = REPO / "results" / "sigma_inv_fb8_gaps.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nSaved {len(results)} entries to {out_path}")
    print(f"Errors: {err_count}")

    # Generate Python code for integration
    print("\n" + "=" * 60)
    print("INTEGRATION CODE (add to _SIGMA_INV_BY_FB8 in bitstream.py):")
    print("=" * 60)
    for fb8 in sorted(by_fb8.keys()):
        entries = sorted(by_fb8[fb8])
        parts = []
        for foff, si in entries:
            parts.append(f"({foff},{si[0]},{si[1]},{si[2]},{si[3]})")
        line = f"    {fb8}: [{','.join(parts)}],"
        print(line)


if __name__ == "__main__":
    main()
