"""R24 mirror experiment — replay Quartus's R24 cells via RouteCodec.

Reads every active R24 cell from lits_l3_base.rbf, asks the codec to write
the SAME (wx, y, i_idx) wires onto a stripped baseline, and compares the
result against the original Quartus RBF byte-by-byte in routing space.

If R24 replay is bit-perfect → our prev-column / fixed-offset CRAM model
is sound, and the (10,10)→(12,10) R4 mismatch is Quartus choosing a
different physical resource, not a codec addressing bug.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from collections import defaultdict
from pathlib import Path

from bitstream import RouteCodec

ROOT = Path(__file__).resolve().parent.parent
RBF_DIR = ROOT / "results" / "rbf"
BASE = RBF_DIR / "lits_l3_base.rbf"
STRIPPED = RBF_DIR / "lits_l3_stripped.rbf"
ZERO = RBF_DIR / "lits_zero_10_10.rbf"


def parse_r24_name(n):
    # R24_X{x}_Y{y}_N0_I{i}
    parts = n.split("_")
    return int(parts[1][1:]), int(parts[2][1:]), int(parts[4][1:])


def main():
    if not (BASE.exists() and STRIPPED.exists() and ZERO.exists()):
        print("missing inputs — run compile_l3_baseline.py + synth_route_l3.py first")
        return 1

    codec = RouteCodec()
    base = BASE.read_bytes()
    stripped = STRIPPED.read_bytes()
    zero = ZERO.read_bytes()

    # 1. Pull Quartus's R24 cells from base
    r24_cells = codec.read_r24(base, zero)
    print(f"quartus R24 cells: {len(r24_cells)}")

    # 2. Group by unique wire identity
    wires = defaultdict(list)
    for name, off, bp in r24_cells:
        wx, y, i = parse_r24_name(name)
        wires[(wx, y, i)].append((off, bp))
    print(f"unique R24 wires: {len(wires)}")
    for (wx, y, i), cells in sorted(wires.items()):
        print(f"  R24 X={wx} Y={y} I={i}  ({len(cells)} cells)")

    # 3. Replay each wire onto stripped via codec — sniper mode
    buf = stripped
    for (wx, y, i), cells in wires.items():
        try:
            buf = codec.write_r24(buf, zero, wx, y, i_idx=i, value=True,
                                  cells=cells)
        except ValueError as e:
            print(f"  ✗ write_r24 X={wx} Y={y} I={i}: {e}")

    # 4. Compare buf vs base in the union of touched bytes
    touched_bytes = sorted({off for cells in wires.values() for off, _ in cells})
    n_match = n_diff = 0
    diffs = []
    for off in touched_bytes:
        if buf[off] == base[off]:
            n_match += 1
        else:
            n_diff += 1
            if len(diffs) < 16:
                diffs.append((off, base[off], buf[off]))
    print(f"\nbyte-level (in union of R24 cell bytes, {len(touched_bytes)} bytes):")
    print(f"  match : {n_match}")
    print(f"  diff  : {n_diff}")
    if diffs:
        print("  first diffs (offset, quartus, replay):")
        for off, q, r in diffs:
            print(f"    {off:6d}  q={q:#04x}  r={r:#04x}  xor={q^r:#04x}")

    # 5. Per-cell bit match
    bit_match = bit_miss = 0
    miss_samples = []
    for name, off, bp in r24_cells:
        q_bit = (base[off] >> bp) & 1
        r_bit = (buf[off] >> bp) & 1
        if q_bit == r_bit:
            bit_match += 1
        else:
            bit_miss += 1
            if len(miss_samples) < 8:
                miss_samples.append((name, off, bp, q_bit, r_bit))
    print(f"\nper-cell bit match (against Quartus's {len(r24_cells)} R24 cells):")
    print(f"  match : {bit_match}")
    print(f"  miss  : {bit_miss}")
    for s in miss_samples:
        print(f"    {s}")

    # 6. Did the replay write any cells Quartus did NOT have?
    # Read R24 from buf vs zero — anything in buf-set but not quartus-set is extra.
    replay_cells = set((n, o, b) for n, o, b in codec.read_r24(buf, zero))
    quartus_set = set((n, o, b) for n, o, b in r24_cells)
    extra = replay_cells - quartus_set
    missing = quartus_set - replay_cells
    print(f"\nset diff via read_r24:")
    print(f"  intersection : {len(replay_cells & quartus_set)}")
    print(f"  replay-only  : {len(extra)}")
    print(f"  quartus-only : {len(missing)}")
    if extra:
        for c in sorted(extra)[:8]:
            print(f"    extra:   {c}")
    if missing:
        for c in sorted(missing)[:8]:
            print(f"    missing: {c}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
