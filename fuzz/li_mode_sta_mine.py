#!/usr/bin/env python3
"""Mine LI mode-selection rule by extracting STA paths from existing
lits_pair_* work directories and correlating the last R4/C4 hop's I-index
with the paired/alternating mode label.

Hypothesis: the LI input mux tier (paired vs alternating) is selected by
the I-index of the last R4/C4/R24 hop before the LI activation.

Run this from EP4CE6/fuzz/. Requires that work/lits_pair_*/ directories
still exist (they hold the fitted designs needed by quartus_sta).
"""
import json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from collections import Counter, defaultdict
from li_topology_validate import (TARGETS, TAG_PREFIX, CONNECT_PORT)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "work")
QUARTUS_STA = os.path.expanduser("~/intelFPGA_lite/21.1/quartus/bin/quartus_sta")
SNAPSHOT = os.path.join(ROOT, "results", "li_lab_classification.json")

TCL = '''project_open {proj}
load_package sta
create_timing_netlist
create_clock -name vclk -period 100
set_input_delay -clock vclk 0 [get_ports {{A B C D}}]
set_output_delay -clock vclk 0 [get_ports Q]
report_timing -setup -detail full_path -show_routing -npaths 4 -file _route_out.txt
delete_timing_netlist
project_close
'''

ROW_RE = re.compile(
    r';\s*([\d.\-]+)\s*;\s*([\d.\-]+)\s*;\s*(\S*)\s*;\s*(\S*)\s*;\s*(\d*)\s*;\s*(\S*)\s*;\s*(.*?)\s*;'
)


def parse_route(path):
    segs = []
    in_data = False
    with open(path, "r", errors="replace") as f:
        for line in f:
            if "Data Arrival Path" in line:
                in_data = True
                continue
            if in_data and "Data Required Path" in line:
                break
            if not in_data:
                continue
            m = ROW_RE.match(line.rstrip())
            if m:
                segs.append({
                    "type": m.group(4),
                    "location": m.group(6),
                    "element": m.group(7).strip(),
                })
    return segs


def run_sta(proj_dir, proj_name):
    tcl_path = os.path.join(proj_dir, "_extract_route.tcl")
    with open(tcl_path, "w") as f:
        f.write(TCL.format(proj=proj_name))
    r = subprocess.run([QUARTUS_STA, "-t", "_extract_route.tcl"],
                        cwd=proj_dir, capture_output=True, text=True, timeout=120)
    out = os.path.join(proj_dir, "_route_out.txt")
    if not os.path.exists(out):
        return None, r.stderr[-500:]
    return parse_route(out), None


def find_li_dst(segs, dx, dy):
    """Find index of the LOCAL_INTERCONNECT segment at (dx,dy), if any."""
    for i, s in enumerate(segs):
        loc = s["location"]
        if loc.startswith("LOCAL_INTERCONNECT_"):
            m = re.match(r"LOCAL_INTERCONNECT_X(\d+)_Y(\d+)_N(\d+)_I(\d+)", loc)
            if m and int(m.group(1)) == dx and int(m.group(2)) == dy:
                return i
    return None


def hop_info(loc):
    """Return (wire_type, x, y, n, i) or None if not a routing wire."""
    m = re.match(r"(C4|R4|R24|C16)_X(\d+)_Y(\d+)_N(\d+)_I(\d+)", loc)
    if not m:
        return None
    return (m.group(1), int(m.group(2)), int(m.group(3)),
            int(m.group(4)), int(m.group(5)))


def main():
    with open(SNAPSHOT) as f:
        snap = json.load(f)
    mode_by_dst = {(s["dst_x"], s["dst_y"]): s["mode"]
                   for s in snap["samples"] if "mode" in s}

    rows = []
    for dx, dy in TARGETS:
        if (dx, dy) not in mode_by_dst:
            continue
        mode = mode_by_dst[(dx, dy)]
        if mode not in ("paired", "alternating"):
            continue

        proj_name = f"{TAG_PREFIX}_X10Y10_to_X{dx}Y{dy}N0_{CONNECT_PORT}"
        proj_dir = os.path.join(WORK, proj_name)
        if not os.path.isdir(proj_dir):
            print(f"  SKIP {proj_name}: no work dir")
            continue

        print(f"  STA {proj_name} ...", flush=True)
        segs, err = run_sta(proj_dir, proj_name)
        if segs is None:
            print(f"    FAIL: {err}")
            continue

        idx = find_li_dst(segs, dx, dy)
        if idx is None:
            print(f"    no LI segment at dst LAB ({dx},{dy})")
            continue

        # walk backwards from LI to find last routing hop (C4/R4/R24/C16)
        last_hop = None
        for j in range(idx - 1, -1, -1):
            h = hop_info(segs[j]["location"])
            if h:
                last_hop = h
                break

        # Also grab the LI's own I index (which input port mux entry)
        li_match = re.match(r"LOCAL_INTERCONNECT_X\d+_Y\d+_N\d+_I(\d+)",
                            segs[idx]["location"])
        li_i = int(li_match.group(1)) if li_match else None

        rows.append({
            "dst_x": dx, "dst_y": dy, "mode": mode,
            "li_i": li_i,
            "last_hop_type": last_hop[0] if last_hop else None,
            "last_hop_i":    last_hop[4] if last_hop else None,
            "last_hop_loc":  segs[idx-1]["location"] if idx > 0 else None,
        })

    # Print + analyze
    print("\n=== samples ===")
    print(f"{'dst':>10} {'mode':12} {'li_I':>5} {'lastHop':>4} {'I':>3}  loc")
    for r in rows:
        print(f"  X{r['dst_x']:2d}Y{r['dst_y']:2d}  {r['mode']:12} "
              f"{r['li_i']!s:>5} {r['last_hop_type'] or '-':>4} "
              f"{r['last_hop_i']!s:>3}  {r['last_hop_loc']}")

    print("\n=== mode by last_hop_i ===")
    by = defaultdict(Counter)
    for r in rows:
        by[r["last_hop_i"]][r["mode"]] += 1
    for k in sorted(by.keys(), key=lambda v: (v is None, v)):
        print(f"  last_hop_i={k}: {dict(by[k])}")

    print("\n=== mode by (last_hop_type, last_hop_i) ===")
    by2 = defaultdict(Counter)
    for r in rows:
        by2[(r["last_hop_type"], r["last_hop_i"])][r["mode"]] += 1
    for k in sorted(by2.keys(), key=lambda v: (str(v[0]), v[1] if v[1] is not None else -1)):
        print(f"  {k}: {dict(by2[k])}")

    print("\n=== mode by li_i ===")
    by3 = defaultdict(Counter)
    for r in rows:
        by3[r["li_i"]][r["mode"]] += 1
    for k in sorted(by3.keys(), key=lambda v: (v is None, v)):
        print(f"  li_I={k}: {dict(by3[k])}")

    out = os.path.join(ROOT, "results", "li_mode_sta_mine.json")
    with open(out, "w") as f:
        json.dump(rows, f, indent=2)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
