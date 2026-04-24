#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""fb8=7 group=4 fallback — X=8 is the only column for fb8=7, but the
16-LUT FACE template does not fit at Y=14/16. Split the probe into two
halves (N=0..14 and N=16..30, 8 LEs each) so the fitter has slack.
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
WORK = REPO / "tmp" / "sigma_group4_fb7"

sys.path.insert(0, str(REPO / "fuzz"))
from config import cram_ctrl_addr, cram_ctrl_bit, cram_n_delta  # noqa: E402

MASK = 0xFACE
X = 8
Y_VALUES = [14, 16]
HALVES = {
    "lo": list(range(0, 16, 2)),   # N=0,2,4,6,8,10,12,14
    "hi": list(range(16, 32, 2)),  # N=16..30
}


def gen_verilog(n_count):
    lines = ["module probe(input wire a, b, c, d, output wire q);"]
    wires = []
    for i in range(n_count):
        lines.append(f"  wire w{i};")
        lines.append(f'  cycloneive_lcell_comb #(.lut_mask("FACE")) lut{i} (')
        lines.append(f"    .dataa(a), .datab(b), .datac(c), .datad(d), .combout(w{i}));")
        wires.append(f"w{i}")
    lines.append(f"  assign q = {' | '.join(wires)};")
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def gen_qsf(x, y, ns):
    lines = [
        'set_global_assignment -name FAMILY "Cyclone IV E"',
        # CE10 device: CE6=CE10 same die; unlocks X=8 at Y=14/16 where the
        # CE6 fitter refuses LCCOMB placement (X=8 Y≤11 is the CE6 ceiling).
        "set_global_assignment -name DEVICE EP4CE10F17C8",
        "set_global_assignment -name TOP_LEVEL_ENTITY probe",
        "set_global_assignment -name VERILOG_FILE probe.v",
        "set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files",
        "set_location_assignment PIN_E16 -to a",
        "set_location_assignment PIN_M16 -to b",
        "set_location_assignment PIN_M15 -to c",
        "set_location_assignment PIN_E15 -to d",
        "set_location_assignment PIN_G15 -to q",
    ]
    for i, n in enumerate(ns):
        lines.append(f'set_location_assignment LCCOMB_X{x}_Y{y}_N{n} -to "lut{i}"')
    return "\n".join(lines) + "\n"


def build(x, y, half):
    ns = HALVES[half]
    tag = f"face_X{x}_Y{y}_{half}"
    work = WORK / tag
    work.mkdir(parents=True, exist_ok=True)
    (work / "probe.v").write_text(gen_verilog(len(ns)))
    (work / "probe.qsf").write_text(gen_qsf(x, y, ns))
    (work / "probe.qpf").write_text('PROJECT_REVISION = "probe"\n')
    env = os.environ.copy()
    env["PATH"] = str(QUARTUS_BIN) + ":" + env["PATH"]
    for step in ("quartus_map", "quartus_fit", "quartus_asm"):
        r = subprocess.run(
            [step, "--read_settings_files=on", "--write_settings_files=off", "probe"],
            cwd=str(work), capture_output=True, env=env, timeout=180,
        )
        if r.returncode != 0:
            return y, half, None, f"{step} failed"
    r = subprocess.run(
        ["quartus_cpf", "-c", "-o", "bitstream_compression=off",
         "output_files/probe.sof", "output_files/probe.rbf"],
        cwd=str(work), capture_output=True, env=env, timeout=60,
    )
    if r.returncode != 0:
        return y, half, None, "cpf failed"
    return y, half, (work / "output_files" / "probe.rbf").read_bytes(), "OK"


def extract(x, y, n, probe, nv):
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
    probes = [(y, h) for y in Y_VALUES for h in HALVES]
    total = len(probes)
    print(f"Building {total} 8-LUT probes (X={X}, Y∈{Y_VALUES}, halves=lo/hi)…")
    rbf_cache = {}
    errors = 0
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(build, X, y, h): (y, h) for y, h in probes}
        done = 0
        for fut in as_completed(futs):
            y, h, rbf, msg = fut.result()
            done += 1
            if rbf is None:
                print(f"  [{done}/{total}] X{X}Y{y}_{h}: FAIL ({msg})")
                errors += 1
            else:
                rbf_cache[(y, h)] = rbf
                print(f"  [{done}/{total}] X{X}Y{y}_{h}: OK")
    print(f"\nBuild: {total - errors}/{total} OK in {time.time()-t0:.0f}s")

    entries = {}
    err_count = 0
    for (y, h), probe in sorted(rbf_cache.items()):
        for n in HALVES[h]:
            foff, fb8, group, si, err = extract(X, y, n, probe, nv)
            if err > 0:
                print(f"  ERR X{X}Y{y}N{n} fb8={fb8} group={group} err={err}")
                err_count += 1
                continue
            key = f"{foff},{fb8},{group}"
            entries[key] = {"foff": foff, "fb8": fb8, "group": group,
                            "sigma_inv": list(si),
                            "source": f"X{X}Y{y}N{n} ({h}-half)"}

    print(f"\n{len(entries)} entries, {err_count} errors")
    out = {
        "description": "σ⁻¹ fb8=7 group=4 closure via 8-LUT half-LAB probes "
                       "(X=8 is the only fb8=7 column; 16-LUT template did not "
                       "fit at Y=14/16).",
        "mining_date": "2026-04-24",
        "mask": f"0x{MASK:04X}",
        "entries": entries,
    }
    out_path = REPO / "results" / "sigma_inv_group4_fb8_7_patch.json"
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
