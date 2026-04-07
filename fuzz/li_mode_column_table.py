"""Build the 22-entry X→mode consensus table.

For each LAB_X, compile from 3 different src LABs to dst=(X, 10) and read
the LI mode at the dst LAB. Take majority vote.
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))

from bitstream import RouteCodec
from runner import compile_route_pair_single_input, compile_route_baseline_abcd
from config import LAB_X

RBF_DIR = ROOT / "results" / "rbf"
SRCS = [(3, 5), (17, 8), (25, 15)]
DST_Y = 10


def read_mode(codec, design, zero, dx, dy):
    li = codec.read_local_interconnect(design, zero)
    by_pair = {}
    for e in li:
        lx, ly, p, b = codec._parse_li_name(e[0])
        if (lx, ly) == (dx, dy):
            by_pair.setdefault(p, set()).add(b)
    if not by_pair:
        return "empty"
    mode, _ = RouteCodec._classify_li_lab(by_pair)
    return mode


def main():
    codec = RouteCodec()

    # Ensure all 3 baselines exist
    zeros = {}
    for sx, sy in SRCS:
        tag = f"litdec_zero_{sx}_{sy}"
        p = RBF_DIR / f"{tag}.rbf"
        if not p.exists():
            print(f"baseline {tag} ...", flush=True)
            rbf, t, err = compile_route_baseline_abcd(tag, sx, sy, 0)
            if not rbf:
                print(f"  FAIL: {err}"); return
            print(f"  OK ({t:.1f}s)")
        zeros[(sx, sy)] = p.read_bytes()

    table = {}      # X -> consensus mode
    raw = {}        # X -> {src: mode}

    for dx in LAB_X:
        if dx in (3,):  # avoid src==dst with src=(3,5)
            srcs_use = [(17, 8), (25, 15)]
        else:
            srcs_use = SRCS
        per_src = {}
        for sx, sy in srcs_use:
            if (sx, sy) == (dx, DST_Y):
                continue
            tag = f"litcol_{sx}_{sy}_to_X{dx}Y{DST_Y}"
            p = RBF_DIR / f"{tag}.rbf"
            if not p.exists():
                print(f"compile ({sx},{sy})->({dx},{DST_Y}) ...", flush=True)
                rbf, t, err = compile_route_pair_single_input(
                    tag, sx, sy, 0, dx, DST_Y, 0, connect_port="datab")
                if not rbf:
                    print(f"  FAIL: {err}"); continue
                print(f"  OK ({t:.1f}s)")
            design = p.read_bytes()
            mode = read_mode(codec, design, zeros[(sx, sy)], dx, DST_Y)
            per_src[(sx, sy)] = mode
        raw[dx] = per_src
        votes = Counter(m for m in per_src.values() if m != "empty")
        consensus = votes.most_common(1)[0][0] if votes else "empty"
        unanimous = len(set(per_src.values()) - {"empty"}) == 1
        table[dx] = consensus
        marker = "✓" if unanimous else "△"
        print(f"  X={dx:2d} {marker} {consensus:11s}  raw={per_src}")

    print(f"\n=== Consensus table ===")
    for x in LAB_X:
        print(f"  X={x:2d}: {table[x]}")

    # Group
    paired = [x for x in LAB_X if table[x] == "paired"]
    alt    = [x for x in LAB_X if table[x] == "alternating"]
    print(f"\npaired ({len(paired)}): {paired}")
    print(f"alternating ({len(alt)}): {alt}")

    out = ROOT / "results" / "li_mode_column_table.json"
    out.write_text(json.dumps({
        "srcs_used": SRCS,
        "dst_y": DST_Y,
        "consensus": {str(k): v for k, v in table.items()},
        "raw": {str(k): {f"{s[0]},{s[1]}": m for s, m in v.items()} for k, v in raw.items()},
        "paired_columns": paired,
        "alternating_columns": alt,
    }, indent=2))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
