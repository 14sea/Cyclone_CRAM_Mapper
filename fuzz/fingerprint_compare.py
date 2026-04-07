"""β step 2 — extract (10,14) source fingerprint and compare to (10,10)."""
import sys, os, re, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from collections import Counter
from pathlib import Path
from bitstream import RouteCodec

ROOT = Path('/home/test/EP4CE6')
RBF = ROOT / 'results' / 'rbf'
codec = RouteCodec()


def cells(rbf, zero):
    sw = codec.read_switches(rbf, zero)
    out = set()
    for t, lst in sw.items():
        for e in lst:
            out.add((t, e[1], e[2]))
    return out


def mine_source(sx, sy):
    zero = (RBF / f'lits_zero_{sx}_{sy}.rbf').read_bytes()
    pat = re.compile(rf'lits_pair_X{sx}Y{sy}_to_X(\d+)Y(\d+)N(\d+)_(\w+)\.rbf')
    routes = {}
    for path in sorted(RBF.glob(f'lits_pair_X{sx}Y{sy}_to_*.rbf')):
        m = pat.match(path.name)
        if not m:
            continue
        dx, dy, dn, port = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
        try:
            routes[(dx, dy, port)] = cells(path.read_bytes(), zero)
        except Exception as e:
            print(f"  skip ({dx},{dy}): {e}")
    if not routes:
        return None, {}
    fp = set(next(iter(routes.values())))
    for s in routes.values():
        fp &= s
    return fp, routes


def main():
    print("=== mining (10,14) ===")
    fp14, routes14 = mine_source(10, 14)
    print(f"  {len(routes14)} routes, fingerprint {len(fp14)} bits")
    by_t = Counter(t for t, _, _ in fp14)
    print(f"  by type: {dict(by_t)}")
    for t, off, bp in sorted(fp14):
        print(f"    {t:6s} off={off:#08x} bp={bp}")

    print("\n=== mining (10,10) for comparison ===")
    fp10, routes10 = mine_source(10, 10)
    print(f"  {len(routes10)} routes, fingerprint {len(fp10)} bits")

    print("\n=== fingerprint diff ===")
    common = fp10 & fp14
    only10 = fp10 - fp14
    only14 = fp14 - fp10
    print(f"  shared:    {len(common)}")
    print(f"  only (10,10): {len(only10)}")
    for c in sorted(only10):
        print(f"    {c}")
    print(f"  only (10,14): {len(only14)}")
    for c in sorted(only14):
        print(f"    {c}")

    # Save the (10,14) snapshot
    out = {
        "n_routes": len(routes14),
        "fingerprint": sorted([list(c) for c in fp14]),
        "per_route_delta": {
            f"{k[0]},{k[1]},{k[2]}": sorted([list(c) for c in (cells - fp14)])
            for k, cells in routes14.items()
        },
    }
    p = ROOT / 'results' / 'fingerprint_10_14.json'
    p.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {p}")


if __name__ == "__main__":
    main()
