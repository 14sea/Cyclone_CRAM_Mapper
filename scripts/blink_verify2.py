import sys
from pathlib import Path
ROOT = Path("/home/test/EP4CE6")
sys.path.insert(0, str(ROOT/"fuzz"))
from m9k_init_basis import M9K_INIT_ANCHORS, init_cell
PRE, FRAME = 32, 210
nv = (ROOT/"results/rbf/nv_zero_global.rbf").read_bytes()
blink = (ROOT/"tmp/m9k_sdp_blink_4x2048_X15_Y16_N0/m9k_sdp_blink_4x2048_X15_Y16_N0.rbf").read_bytes()
RBF_LEN = len(nv)

def hits(rbf, fp):
    n = 0
    for off, bp in fp:
        if 0 <= off < RBF_LEN:
            if (rbf[off] >> bp) & 1 != (nv[off] >> bp) & 1:
                n += 1
    return n

# Try each SDP 4x2048 anchor on blink, see where M9K actually lives
print("Footprint hits per anchor across SDP 4x2048 sites (blink):")
hits_list = []
for k, info in M9K_INIT_ANCHORS.items():
    site, w, d = k
    if (w, d) != (4, 2048): continue
    anchor = info[0]
    bp_a = info[1] if len(info)>1 else 6
    fp = set()
    valid = True
    for word in range(2048):
        for b in range(4):
            try:
                c = init_cell(anchor, word, b, bp_a)
                if 0 <= c[0] < RBF_LEN:
                    fp.add(c)
            except:
                pass
    n = hits(blink, fp)
    hits_list.append((site, n, len(fp)))

hits_list.sort(key=lambda x: -x[1])
for site, n, fp_size in hits_list[:8]:
    print(f"  {site:14}: {n}/{fp_size} cells set ({100*n/fp_size:.1f}%)")
