# SPDX-License-Identifier: GPL-3.0-or-later
import sys, json
from pathlib import Path
ROOT = Path("/home/test/EP4CE6")
sys.path.insert(0, str(ROOT/"fuzz"))
from m9k_init_basis import M9K_INIT_ANCHORS, init_cell
PRE, FRAME, DPF = 32, 210, 208
nv = (ROOT/"results/rbf/nv_zero_global.rbf").read_bytes()
blink = (ROOT/"tmp/m9k_sdp_blink_4x2048_X15_Y16_N0/m9k_sdp_blink_4x2048_X15_Y16_N0.rbf").read_bytes()
passive = (ROOT/"tmp/m9k_mode_quartus_gold/4x2048/sdp/X15_Y16_N0/m9k_mode_gold_4x2048_sdp_v0.rbf").read_bytes()

# M9K_INIT footprint at X15_Y16_N0 SDP 4x2048
key = ("X15_Y16_N0", 4, 2048)
anchor_info = M9K_INIT_ANCHORS[key]
anchor = anchor_info[0]
init_bp = anchor_info[1] if len(anchor_info)>1 else 6
footprint = set()
for w in range(2048):
    for b in range(4):
        try:
            footprint.add(init_cell(anchor, w, b, init_bp))
        except: pass
print(f"M9K_INIT footprint at X15_Y16: {len(footprint)} cells")

# How many footprint cells are set in blink vs passive (vs nv)
def diff_at(rbf, footprint):
    on = 0
    for off, bp in footprint:
        if (rbf[off] >> bp) & 1 != (nv[off] >> bp) & 1:
            on += 1
    return on

print(f"Footprint cells SET (vs nv) in blink:   {diff_at(blink, footprint)}  (expect ~4096 if M9K at this site)")
print(f"Footprint cells SET (vs nv) in passive: {diff_at(passive, footprint)}")

# Check if blink M9K could be at a different site
# Look at M9K_INIT anchors for ALL SDP 4x2048 sites and see which has the most diff cells
print("\nFootprint hits per anchor across all SDP 4x2048 sites in blink:")
hits = []
for k, info in M9K_INIT_ANCHORS.items():
    site, w, d = k
    if (w, d) != (4, 2048): continue
    anchor = info[0]
    bp_a = info[1] if len(info)>1 else 6
    fp = set()
    for word in range(2048):
        for b in range(4):
            try:
                fp.add(init_cell(anchor, word, b, bp_a))
            except: pass
    n = diff_at(blink, fp)
    hits.append((site, n))
hits.sort(key=lambda x: -x[1])
for site, n in hits[:6]:
    print(f"  {site}: {n}")
