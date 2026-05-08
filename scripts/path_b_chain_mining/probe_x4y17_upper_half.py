#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""β' probe — check which upper-half N positions in LAB(4,17) accept
1-LE standalone placement (LCCOMB_X4_Y17_N{8..15}).

Q_N=7 (our_n=14) is chain-only; W=23/W=24 mining established N=0,12 as
working.  This probe tests Q_N=8..15 (our_n=16,18,...,30) — the upper
half of the LAB, which is unused when a W=24 chain occupies Q_N=0..7.
The first accepting Q_N becomes the buffer-LE candidate for β'.

For each Q_N:
  - Minimal Verilog: trivial pass-through LUT, LED to G15
  - Pin LCCOMB to LCCOMB_X4_Y17_N{Q_N}
  - Run quartus_map + quartus_fit
  - Pass = Fitter completed AND the LCCOMB resource_placements line shows
    LCCOMB_X4_Y17_N{Q_N} (verbatim)

Pure software: no flash, no sigcache mutation.  Output: per-Q_N
pass/fail summary printed to stdout + sidecar JSON.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORK = REPO / "tmp" / "probe_x4y17_upper"
QUARTUS = Path.home() / "intelFPGA_lite" / "21.1" / "quartus" / "bin"
SIDECAR = REPO / "results" / "probe_x4y17_upper_half.json"

LAB_X, LAB_Y = 4, 17
# Quartus LCCOMB N is the our_n convention directly: N ∈ {0,2,4,...,30}.
# Upper half = N ∈ {16,18,...,30} (8 LE positions above the W=24 chain).
Q_N_RANGE = list(range(16, 32, 2))


def run(cmd, cwd, timeout=180):
    env = os.environ.copy()
    env["PATH"] = str(QUARTUS) + ":" + env["PATH"]
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                          errors="replace", timeout=timeout, env=env)


def probe_one(qn: int) -> dict:
    name = f"probe_n{qn}"
    bdir = WORK / name
    for sub in ("db", "incremental_db", "output_files"):
        p = bdir / sub
        if p.exists():
            shutil.rmtree(p)
    bdir.mkdir(parents=True, exist_ok=True)

    # Trivial 1-LUT: LED = A & B (uses 2 inputs, leaves room for fitter)
    verilog = """\
module probe (input A, input B, output LED);
    (* keep = "true" *) wire q;
    assign q   = A & B;
    assign LED = q;
endmodule
"""
    qsf = f"""\
set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY probe
set_global_assignment -name VERILOG_FILE probe.v
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_global_assignment -name SEED 1
set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"
set_global_assignment -name RESERVE_ALL_UNUSED_PINS_WEAK_PULLUP "AS INPUT TRI-STATED WITH WEAK PULL-UP"
set_global_assignment -name CYCLONEII_RESERVE_NCEO_AFTER_CONFIGURATION "USE AS REGULAR IO"
set_location_assignment PIN_E15 -to A
set_location_assignment PIN_E16 -to B
set_location_assignment PIN_G15 -to LED
set_location_assignment LCCOMB_X{LAB_X}_Y{LAB_Y}_N{qn} -to "q"
"""
    (bdir / "probe.v").write_text(verilog)
    (bdir / "probe.qsf").write_text(qsf)
    (bdir / "probe.qpf").write_text('PROJECT_REVISION = "probe"\n')

    result = {"q_n": qn, "our_n": qn * 2, "fit_ok": False,
              "placement_match": False, "placement_actual": None,
              "fit_messages": []}

    r = run(["quartus_map", "--read_settings_files=on",
             "--write_settings_files=off", "probe"], cwd=bdir)
    if r.returncode != 0:
        result["fit_messages"].append(f"map FAIL rc={r.returncode}")
        result["fit_messages"].append(r.stdout[-1500:])
        return result

    r = run(["quartus_fit", "--read_settings_files=on",
             "--write_settings_files=off", "probe"], cwd=bdir)
    fit_ok = (r.returncode == 0)
    result["fit_ok"] = fit_ok

    fit_rpt = bdir / "output_files" / "probe.fit.rpt"
    flow_rpt = bdir / "output_files" / "probe.flow.rpt"
    target_loc = f"LCCOMB_X{LAB_X}_Y{LAB_Y}_N{qn}"

    # Look for the requested placement
    if fit_rpt.exists():
        text = fit_rpt.read_text(errors="replace")
        # Find resource_placements / Logic Cell mentions
        for line in text.splitlines():
            if target_loc in line:
                result["placement_actual"] = line.strip()[:200]
                result["placement_match"] = True
                break
            ll = line.lower()
            if "illegal location" in ll or "could not place" in ll:
                result["fit_messages"].append(line.strip()[:300])
            if "lccomb_x4_y17" in ll and "->" in line:
                # Actual placement of the user's logic
                result["placement_actual"] = line.strip()[:200]
        # Sometimes Quartus writes "Fitter Status : Successful" only on flow_rpt
    if flow_rpt.exists():
        text = flow_rpt.read_text(errors="replace")
        m = re.search(r"Fitter Status\s*:\s*(\S+)", text)
        if m:
            result["fitter_status"] = m.group(1)

    # Capture last lines of fit stdout if it failed
    if not fit_ok:
        result["fit_messages"].append(f"fit rc={r.returncode}")
        result["fit_messages"].append(r.stdout[-2000:])

    return result


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    print(f"=== Probe LAB({LAB_X},{LAB_Y}) upper-half Q_N=8..15 1-LE placement ===\n")

    results = []
    for qn in Q_N_RANGE:
        target = f"LCCOMB_X{LAB_X}_Y{LAB_Y}_N{qn}"
        print(f"--- Q_N={qn:2d} (our_n={qn*2:2d})  target={target} ---", flush=True)
        try:
            r = probe_one(qn)
        except subprocess.TimeoutExpired:
            r = {"q_n": qn, "our_n": qn * 2, "fit_ok": False,
                 "placement_match": False, "placement_actual": None,
                 "fit_messages": ["TIMEOUT"]}
        results.append(r)
        status = ("OK" if r.get("placement_match") else
                  ("FIT-OK BUT NO MATCH" if r["fit_ok"] else "FAIL"))
        print(f"  result: {status}")
        if r.get("placement_actual"):
            print(f"  placement: {r['placement_actual']}")
        for msg in r.get("fit_messages", [])[:3]:
            for line in msg.splitlines()[-5:]:
                if line.strip():
                    print(f"    | {line.strip()[:150]}")
        print()

    # Sidecar
    SIDECAR.parent.mkdir(parents=True, exist_ok=True)
    SIDECAR.write_text(json.dumps({
        "lab": [LAB_X, LAB_Y],
        "tested": Q_N_RANGE,
        "results": results,
    }, indent=2))
    print(f"Sidecar written: {SIDECAR}")

    # Summary
    print("\n=== Summary ===")
    accepted = [r for r in results if r.get("placement_match")]
    print(f"Accepted positions: {[r['q_n'] for r in accepted]}")
    if accepted:
        first = accepted[0]
        print(f"\nRecommended buffer-LE candidate: Q_N={first['q_n']} "
              f"(our_n={first['our_n']}) = LCCOMB_X{LAB_X}_Y{LAB_Y}_N{first['q_n']}")


if __name__ == "__main__":
    main()
