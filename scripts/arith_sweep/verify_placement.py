#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check: did Quartus actually honor the LOC constraints for c8_lo vs c8_up?
If yes, the identical cellsets mean arith blob is N-slot-agnostic.
If no (Quartus rearranged), we were fooled."""
import json

def parse_fit_panel(path):
    """Extract the 'Fitter Resource Usage Summary' and LE locations."""
    import re
    out = []
    try:
        txt = open(path, errors="replace").read()
    except FileNotFoundError:
        return None
    # Find location reports
    for m in re.finditer(r'(X\d+_Y\d+_N\d+)', txt):
        out.append(m.group(1))
    return out[:40]

for tag in ["c2_lo", "c2_up", "c4_lo", "c4_up", "c8_lo", "c8_up"]:
    log = f"tmp/arith_sweep/{tag}/fit.log"
    locs = parse_fit_panel(log)
    print(f"{tag}: found {len(locs) if locs else 0} refs; first 10: {locs[:10] if locs else 'N/A'}")

# Also check the fit.rpt for actual placement
import os
for tag in ["c8_lo", "c8_up"]:
    rpt = f"tmp/arith_sweep/{tag}/output_files/top.fit.rpt"
    if not os.path.exists(rpt):
        print(f"{tag}: no fit.rpt")
        continue
    print(f"\n=== {tag} fit.rpt resource placement ===")
    txt = open(rpt, errors="replace").read()
    # Find "Logic cells" or "Fitter Resource Utilization" or LE table
    import re
    # Look for X4_Y18 references
    matches = re.findall(r'X4_Y18_N\d+', txt)
    uniq = sorted(set(matches), key=lambda s: int(s.split("N")[1]))
    print(f"Unique X4_Y18_N* refs in fit.rpt: {uniq[:20]}")
