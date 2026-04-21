#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mine σ⁻¹ for fb8 ∈ {0,1,3,4,7} at groups 0-4 (Y=2..14).

The existing table only covered groups 5-6 (Y=17-21).
Now that we know σ⁻¹ depends on group, we need all 7 groups.

Representative X columns:
  fb8=0: X=3   fb8=1: X=6   fb8=3: X=4   fb8=4: X=7   fb8=7: X=8
Y values for groups 0-4: Y=2..14 (12 values, excluding Y=15 jailbreak)
Total: 5 × 12 = 60 probes.
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
WORK = REPO / "tmp" / "sigma_existing_groups"

sys.path.insert(0, str(REPO / "fuzz"))
from config import COLUMN_BASE, SLOT_BASE, cram_ctrl_addr, cram_ctrl_bit, cram_n_delta

MASK = 0xFACE
N_VALS = list(range(0, 32, 2))

TARGETS = {
    0: 3,   # X=3  for fb8=0
    1: 6,   # X=6  for fb8=1
    3: 4,   # X=4  for fb8=3
    4: 7,   # X=7  for fb8=4
    7: 8,   # X=8  for fb8=7
}

# Groups 0-4: Y values 2..14
Y_VALUES = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]


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


def extract_all(nv, rbf_cache):
    """Extract σ⁻¹ from all probes with (foff, fb8, group) key."""
    table = {}
    errs = 0

    for (x, y), probe in sorted(rbf_cache.items()):
        slot = (y - 2) % 3
        group = (y - 2) // 3

        for n in N_VALS:
            k = n // 2
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
                    nv_bit = (nv[addr] >> bp) & 1
                    p_bit = (probe[addr] >> bp) & 1
                    d = nv_bit ^ p_bit
                    m = (MASK >> b) & 1
                    if d != m:
                        err += 1
                if err < best_err:
                    best_err = err
                    best_si = si

            key = (foff, fb8, group)
            if best_err > 0:
                errs += 1
            else:
                table[key] = best_si

    return table, errs


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    nv = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()
    assert len(nv) == 368011

    probes = []
    for fb8, x in sorted(TARGETS.items()):
        for y in Y_VALUES:
            probes.append((x, y))

    total = len(probes)
    print(f"Building {total} probes for fb8={{0,1,3,4,7}} at groups 0-4...")

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
                    print(f"  [{done}/{total}] {elapsed:.0f}s, {done - errors} OK")

    print(f"\nBuild: {done - errors}/{total} OK in {time.time() - t0:.0f}s")

    table, errs = extract_all(nv, rbf_cache)

    by_fb8_group = defaultdict(int)
    for (foff, fb8, group) in table:
        by_fb8_group[(fb8, group)] += 1
    print(f"\nExtracted {len(table)} entries ({errs} errors)")
    for (fb8, group), cnt in sorted(by_fb8_group.items()):
        print(f"  fb8={fb8}, group={group}: {cnt} entries")

    out = {
        "description": "σ⁻¹ for fb8={0,1,3,4,7} at groups 0-4",
        "entries": {}
    }
    for (foff, fb8, group), si in sorted(table.items()):
        out["entries"][f"{foff},{fb8},{group}"] = {
            "foff": foff, "fb8": fb8, "group": group, "sigma_inv": list(si)
        }
    out_path = REPO / "results" / "sigma_inv_existing_groups.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
