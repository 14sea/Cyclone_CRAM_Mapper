"""Mine LI mode-selection rule via RBF spatial traceback.

For each lits_pair_X10Y10_to_X{dst_x}Y{dst_y}N0_datab.rbf:
  1. Read all active C4/R4/R24 switches (diff vs zero baseline).
  2. Find the wire that lands at (dst_x, dst_y) — the "last hop".
     - C4 (vertical): wx == dst_x and |wy - dst_y| <= 4
     - R4 (horizontal): wy == dst_y and |wx - dst_x| <= 4
     - R24: wy == dst_y and |wx - dst_x| <= 24
  3. Sanity: exactly one candidate per type-axis. Otherwise mark ambiguous.
  4. Cross-tab last_hop.(type, I) vs mode label from li_lab_classification.json.

Caveats:
  - C4/R4 wire (wx,wy) is an anchor, not the endpoint. Direction (up/down,
    left/right) is unknown per I-index, so we accept either side within 4.
  - We use de-duplicated diff lists from RouteCodec.read_switches() — multiple
    Y-rows of the same byte get one wire entry per Y, which is fine here
    because we filter by spatial proximity to dst.
"""
import json
import sys
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))

from bitstream import RouteCodec

RBF_DIR = ROOT / "results" / "rbf"
ZERO_RBF = RBF_DIR / "lits_zero_10_10.rbf"
CLASSIFICATION = ROOT / "results" / "li_lab_classification.json"
OUT = ROOT / "results" / "li_mode_rbf_mine.json"

WIRE_RE = re.compile(r"^(C4|R4|R24)_X(\d+)_Y(\d+)_N0_I(\d+)$")


def parse_wire(name):
    m = WIRE_RE.match(name)
    if not m:
        return None
    return m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))


SRC_X, SRC_Y = 10, 10


def find_last_hop(switches, dst_x, dst_y):
    """Return list of (type, wx, wy, i) candidates whose anchor is adjacent to dst.

    Heuristic: a wire's anchor (wx,wy) sits at one end. The "last hop" landing
    at dst should have anchor within 1 of dst on the wire's free axis, and
    NOT also be at the source. We additionally require dst is closer than src.
    """
    cand = set()
    for wtype in ("c4", "r4", "r24"):
        for entry in switches.get(wtype, []):
            p = parse_wire(entry[0])
            if p is None:
                continue
            t, wx, wy, i = p
            d_dst = abs(wx - dst_x) + abs(wy - dst_y)
            d_src = abs(wx - SRC_X) + abs(wy - SRC_Y)
            if d_dst >= d_src:
                continue  # anchor on src side, not last hop
            if t == "C4":
                if wx == dst_x and abs(wy - dst_y) <= 1:
                    cand.add((t, wx, wy, i))
            elif t == "R4":
                if wy == dst_y and abs(wx - dst_x) <= 1:
                    cand.add((t, wx, wy, i))
            elif t == "R24":
                if wy == dst_y and abs(wx - dst_x) <= 4:
                    cand.add((t, wx, wy, i))
    return sorted(cand)


def main():
    classification = json.loads(CLASSIFICATION.read_text())
    samples = [s for s in classification["samples"] if s["mode"] in ("paired", "alternating")]
    print(f"Loaded {len(samples)} non-empty samples")

    if not ZERO_RBF.exists():
        print(f"FATAL: zero baseline missing: {ZERO_RBF}")
        return 1
    zero = ZERO_RBF.read_bytes()
    codec = RouteCodec()

    results = []
    type_i_counter = defaultdict(Counter)  # mode -> Counter[(type, i)]
    ambiguous = 0
    no_hop = 0

    for s in samples:
        dst_x, dst_y, mode = s["dst_x"], s["dst_y"], s["mode"]
        rbf_path = RBF_DIR / f"lits_pair_X10Y10_to_X{dst_x}Y{dst_y}N0_datab.rbf"
        rec = {"dst_x": dst_x, "dst_y": dst_y, "mode": mode, "rbf": rbf_path.name}
        if not rbf_path.exists():
            rec["status"] = "missing_rbf"
            results.append(rec)
            continue
        rbf = rbf_path.read_bytes()
        sw = codec.read_switches(rbf, zero, wire_types={"c4", "r4", "r24"})
        cand = find_last_hop(sw, dst_x, dst_y)
        rec["candidates"] = [{"type": c[0], "wx": c[1], "wy": c[2], "i": c[3]} for c in cand]
        if not cand:
            rec["status"] = "no_hop"
            no_hop += 1
        elif len(cand) > 1:
            rec["status"] = "ambiguous"
            ambiguous += 1
        else:
            rec["status"] = "ok"
            t, wx, wy, i = cand[0]
            rec["last_hop"] = {"type": t, "i": i, "wx": wx, "wy": wy}
            type_i_counter[mode][(t, i)] += 1
        results.append(rec)
        print(f"  ({dst_x:2d},{dst_y:2d}) {mode:11s} cand={len(cand)} {rec.get('last_hop','-')}")

    print(f"\nAmbiguous: {ambiguous}  No-hop: {no_hop}  OK: {len(samples)-ambiguous-no_hop}")
    print("\nCross-tab (mode -> last_hop (type,I)):")
    for mode, ctr in type_i_counter.items():
        print(f"  {mode}:")
        for k, v in ctr.most_common():
            print(f"    {k}: {v}")

    OUT.write_text(json.dumps({
        "source": "fuzz/li_mode_rbf_mine.py",
        "n_samples": len(samples),
        "ambiguous": ambiguous,
        "no_hop": no_hop,
        "cross_tab": {m: {f"{t}_I{i}": v for (t, i), v in c.items()} for m, c in type_i_counter.items()},
        "samples": results,
    }, indent=2))
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
