#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Close the σ⁻¹ Group-4 gap — fb8∈{0,1,3,4,7} × Y∈{14,16}.

The original `sigma_inv_mine_existing_groups.py` hit Quartus fit failures
for the 16-LUT FACE probe at Y=14 for these fb8 values at their
narrow-column representatives (X=3/6/4/7/8). Y=16 was never attempted
for those fb8 values (existing_groups only sweeps Y∈{2..14}).

This miner tries alternate X columns (X=11/16/12/17/8 — the only fb8=7
option) in parallel, extracts σ⁻¹ using the wrapped-vs-non-wrapped
convention from bitstream.from_cram_model, and writes a patch JSON.
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
WORK = REPO / "tmp" / "sigma_group4"

sys.path.insert(0, str(REPO / "fuzz"))
from config import (COLUMN_BASE, SLOT_BASE, cram_ctrl_addr,  # noqa: E402
                    cram_ctrl_bit, cram_n_delta)

MASK = 0xFACE
N_VALS = list(range(0, 32, 2))

# Alternate reps for the fb8s that failed on their primary narrow columns
TARGETS = [
    (0, 11),   # fb8=0 was X=3 (narrow, fit failed); X=11 is wider
    (1, 16),   # fb8=1 was X=6; X=16 is wider
    (3, 12),   # fb8=3 was X=4; X=12 wider
    (4, 17),   # fb8=4 was X=7; X=17 wider
    (7, 8),    # fb8=7 only has X=8
]
Y_VALUES = [14, 16]


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
    for step in ("quartus_map", "quartus_fit", "quartus_asm"):
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


def extract_sigma_at(x, y, n, probe, nv):
    """Same wrap logic as bitstream.from_cram_model (post Y=3 patch)."""
    k = n // 2
    slot = (y - 2) % 3
    group = (y - 2) // 3
    nd = cram_n_delta(n)
    if slot == 1 and group == 0:
        wrapped = (24 + nd <= 0)
        bp_w, adj_w = 7 - group, 206
    else:
        wrapped = slot == 1 and (24 + group * 3 + nd < 0)
        bp_w, adj_w = 7 - group, 207
    if wrapped:
        bp, addr_adj = bp_w, adj_w
    else:
        bp = cram_ctrl_bit(y)
        addr_adj = 0

    base = cram_ctrl_addr(x, y, 0, n) + addr_adj
    foff = (base - 32) % 210
    fb8 = ((base - 32) // 210) % 8

    best_si, best_err = None, 17
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
    return foff, fb8, group, best_si, best_err


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    nv = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()
    assert len(nv) == 368011

    probes = [(x, y) for _, x in TARGETS for y in Y_VALUES]
    total = len(probes)
    print(f"Building {total} FACE probes (fb8∈{{0,1,3,4,7}} × Y∈{{14,16}}, "
          "4-way parallel)…")
    print(f"  TARGETS: {dict((f, x) for f, x in TARGETS)}")

    rbf_cache = {}
    t0 = time.time()
    errors = 0
    with ProcessPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(build_probe, x, y): (x, y) for x, y in probes}
        done = 0
        for fut in as_completed(futs):
            x, y, rbf, msg = fut.result()
            done += 1
            if rbf is None:
                print(f"  [{done}/{total}] X{x}Y{y}: FAIL ({msg})")
                errors += 1
            else:
                rbf_cache[(x, y)] = rbf
                print(f"  [{done}/{total}] X{x}Y{y}: OK")
    print(f"\nBuild: {total - errors}/{total} OK in {time.time()-t0:.0f}s")

    print("\nExtracting σ⁻¹…")
    entries = {}
    err_count = 0
    per_fb8_sig = defaultdict(set)
    for (fb8_expected, x) in TARGETS:
        for y in Y_VALUES:
            probe = rbf_cache.get((x, y))
            if probe is None:
                continue
            for n in N_VALS:
                foff, fb8, group, si, err = extract_sigma_at(x, y, n, probe, nv)
                if fb8 != fb8_expected:
                    print(f"  fb8 mismatch X{x}Y{y}N{n}: expected {fb8_expected}, "
                          f"got {fb8}")
                if err > 0:
                    print(f"  ERR X{x}Y{y}N{n} fb8={fb8} group={group} err={err}")
                    err_count += 1
                    continue
                key = f"{foff},{fb8},{group}"
                entries[key] = {
                    "foff": foff, "fb8": fb8, "group": group,
                    "sigma_inv": list(si),
                    "source": f"X{x}Y{y}N{n}",
                }
                per_fb8_sig[(fb8, group)].add(si)

    print(f"\n{len(entries)} entries extracted, {err_count} errors")
    for (fb8, group), sigs in sorted(per_fb8_sig.items()):
        print(f"  fb8={fb8} group={group}: {len(sigs)} distinct σ⁻¹: {sorted(sigs)}")

    out = {
        "description": "σ⁻¹ for fb8∈{0,1,3,4,7} × group=4 (Y∈{14,16}) "
                       "via alternate-X FACE probes (original narrow-column "
                       "reps failed to fit in Quartus).",
        "mining_date": "2026-04-24",
        "mask": f"0x{MASK:04X}",
        "targets": {str(f): x for f, x in TARGETS},
        "y_values": Y_VALUES,
        "entries": entries,
    }
    out_path = REPO / "results" / "sigma_inv_group4_patch.json"
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
