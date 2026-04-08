# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.0-B: extract routing wire names at every mult_loc site via
post-fit STA (no recompile). Uses existing work/mult_loc_*/ dirs.

Runs quartus_sta -t on a tiny TCL that reports timing from every input
pin to the output pin with show_routing. Parses wire/location names
out of the "Data Arrival Path" table.

Parallel via ProcessPoolExecutor.
"""
import os, re, sys, glob, json, subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed

QUARTUS_STA = os.path.expanduser("~/intelFPGA_lite/21.1/quartus/bin/quartus_sta")

TCL = r'''project_open {PROJ}
load_package sta
create_timing_netlist
create_clock -name vclk -period 100 [get_ports clk]
set_input_delay  -clock vclk 0 [get_ports {a0 a1 b0 b1}]
set_output_delay -clock vclk 0 [get_ports p0]
report_timing -from [get_ports a0] -to [get_ports p0] -detail full_path -show_routing -npaths 1 -file _route_a0.txt
report_timing -from [get_ports a1] -to [get_ports p0] -detail full_path -show_routing -npaths 1 -file _route_a1.txt
report_timing -from [get_ports b0] -to [get_ports p0] -detail full_path -show_routing -npaths 1 -file _route_b0.txt
report_timing -from [get_ports b1] -to [get_ports p0] -detail full_path -show_routing -npaths 1 -file _route_b1.txt
delete_timing_netlist
project_close
'''

WIRE_RE = re.compile(r'[A-Z]+_X\d+_Y\d+(?:_N\d+)?(?:_I\d+)?|[CR]\d+:X\d+Y\d+S\d+I\d+')


def run_site(d):
    name = os.path.basename(d)
    tcl_path = os.path.join(d, "_extract_route.tcl")
    with open(tcl_path, "w") as f:
        f.write(TCL.replace("{PROJ}", name))
    try:
        subprocess.run(
            [QUARTUS_STA, "-t", "_extract_route.tcl"],
            cwd=d, capture_output=True, text=True, timeout=120,
        )
    except Exception as e:
        return name, None, str(e)[:200]
    wires = set()
    for tag in ("a0", "a1", "b0", "b1"):
        rpath = os.path.join(d, f"_route_{tag}.txt")
        if not os.path.exists(rpath):
            continue
        txt = open(rpath, errors="replace").read()
        # Only wires inside data-arrival section
        in_data = False
        for line in txt.splitlines():
            if "Data Arrival Path" in line: in_data = True; continue
            if "Data Required" in line: in_data = False
            if in_data:
                for m in WIRE_RE.findall(line):
                    wires.add(m)
    return name, sorted(wires), None


def main():
    dirs = sorted(glob.glob("work/mult_loc_DSPMULT_X20_Y*_N*"))
    print(f"STA wire extraction on {len(dirs)} sites")
    results = {}
    with ProcessPoolExecutor(max_workers=min(6, os.cpu_count() or 4)) as ex:
        futs = {ex.submit(run_site, d): d for d in dirs}
        for f in as_completed(futs):
            name, wires, err = f.result()
            if err:
                print(f"  {name}: ERR {err}")
                continue
            results[name] = wires
            print(f"  {name}: {len(wires)} wires")

    os.makedirs("results", exist_ok=True)
    with open("results/mult_sta_wires.json", "w") as f:
        json.dump(results, f, indent=1)
    print(f"\nArchived results/mult_sta_wires.json ({len(results)} sites)")

    if len(results) > 1:
        sets = [set(v) for v in results.values() if v]
        if sets:
            univ = set.intersection(*sets)
            print(f"Universal wires across all sites: {len(univ)}")
            for w in sorted(univ)[:25]:
                print(f"  {w}")


if __name__ == "__main__":
    main()
