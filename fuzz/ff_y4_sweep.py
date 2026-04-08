# SPDX-License-Identifier: GPL-3.0-or-later
"""Y=4 full-row LE placement sweep for per-LE arst header bitfield mining.

Reuses ff_per_le_placed's builder but targets LAB_X x N grid at Y=4 only,
where earlier experiments showed clean diffs (~8-12 per-LE cells).

Goal: build a (lab_X, n) -> header (off, bp) table that derives the
per-LE arst bit position.

Output: results/ff_y4_sweep.json
"""
import os, sys
from pathlib import Path
HERE = Path(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(HERE))
import ff_per_le_placed as base  # noqa: E402

LAB_X = [3,4,5,6,7,8,9,10,11,12,13,14,16,17,18,19,21,22,23,24,25,26,28,29,30,31,32,33]
NS = list(range(0, 32, 2))  # 0,2,..,30

TARGETS = [(x, 4, n) for x in LAB_X for n in NS]

# Override
base.TARGETS = TARGETS
base.RBF_DIR = base.REPO / "results" / "rbf" / "ff_y4_sweep"
base.WORK_ROOT = base.REPO / "work_ff_y4_sweep"
base.OUT_JSON = base.REPO / "results" / "ff_y4_sweep.json"

def custom_analyze():
    """Y=4 post-sweep analysis with two invariant checks."""
    import json
    from bitstream import patch_rbf_crc
    diffs = {}
    for (x, y, n) in TARGETS:
        pt = base.RBF_DIR / f"x{x}_y{y}_n{n}_plain.rbf"
        at = base.RBF_DIR / f"x{x}_y{y}_n{n}_arst.rbf"
        if not (pt.exists() and at.exists()):
            continue
        p = patch_rbf_crc(open(pt, "rb").read())
        a = patch_rbf_crc(open(at, "rb").read())
        cells = set()
        for i in range(len(p)):
            xd = p[i] ^ a[i]
            if xd:
                for bp in range(8):
                    if xd & (1 << bp):
                        cells.add((i, bp))
        diffs[(x, n)] = cells
    if not diffs:
        print("no diffs — mining failed?")
        return
    print(f"mined {len(diffs)} placements")
    sizes = sorted((len(v), k) for k, v in diffs.items())
    print("smallest 5:", sizes[:5])
    print("largest 5:", sizes[-5:])

    # globals = intersection of the quietest half
    clean = sorted(diffs.items(), key=lambda kv: len(kv[1]))[:len(diffs)//2]
    globals_ = set.intersection(*(v for _, v in clean))
    print(f"\nglobal cells (∩ of quietest {len(clean)}): {len(globals_)}")

    per_le = {k: v - globals_ for k, v in diffs.items()}

    # CHECK 1: cross-column alignment at N=0
    print("\n=== CHECK 1: cross-column alignment (N=0) ===")
    n0 = {x: per_le[(x, 0)] for x in LAB_X if (x, 0) in per_le}
    ref_x = 10 if 10 in n0 else next(iter(n0))
    ref = n0.get(ref_x, set())
    print(f"ref ({ref_x},0): {len(ref)} cells: {sorted(ref)[:10]}")
    for x in (10, 30):
        if x in n0:
            d = n0[x]
            shared = d & ref
            print(f"  X={x} N=0: {len(d)} cells, shared_with_X{ref_x}={len(shared)}, unique={len(d-ref)}")

    # CHECK 2: isolation — per-LE cells at N=k should not overlap N=k+2
    print("\n=== CHECK 2: adjacent-N isolation (same X) ===")
    leaks = 0
    checks = 0
    for x in LAB_X:
        for n in NS[:-1]:
            k1, k2 = (x, n), (x, n + 2)
            if k1 in per_le and k2 in per_le:
                checks += 1
                inter = per_le[k1] & per_le[k2]
                if inter:
                    leaks += 1
                    if leaks <= 5:
                        print(f"  LEAK X={x} N={n} ∩ N={n+2}: {len(inter)} shared: {sorted(inter)[:5]}")
    print(f"adjacent-N checks: {checks}, leaks: {leaks} ({100*leaks/max(1,checks):.1f}%)")

    # Byte 73 bit pattern per LE (the expected carrier)
    print("\n=== Byte 73 bit pattern per (X, N) ===")
    for x in sorted({k[0] for k in per_le}):
        row = []
        for n in NS:
            if (x, n) in per_le:
                bits = sorted(bp for off, bp in per_le[(x, n)] if off == 73)
                row.append(f"n{n}:{bits}")
        if row:
            print(f"  X={x}: {' '.join(row[:8])}")

    out = {
        "globals": sorted(globals_),
        "per_le": {f"{x},{n}": sorted(v) for (x, n), v in per_le.items()},
        "adjacent_n_leaks": leaks,
        "adjacent_n_checks": checks,
    }
    base.OUT_JSON.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {base.OUT_JSON}")


if __name__ == "__main__":
    base.RBF_DIR.mkdir(parents=True, exist_ok=True)
    base.WORK_ROOT.mkdir(parents=True, exist_ok=True)
    if len(sys.argv) > 1 and sys.argv[1] == "analyze":
        custom_analyze()
    else:
        # run compiles first, then custom analysis
        import ff_per_le_placed as _b
        jobs = [(x, y, n, False) for (x, y, n) in TARGETS] + \
               [(x, y, n, True) for (x, y, n) in TARGETS]
        print(f"queueing {len(jobs)} compiles ({len(TARGETS)} placements)")
        from concurrent.futures import ProcessPoolExecutor, as_completed
        with ProcessPoolExecutor(max_workers=min(6, os.cpu_count() or 4)) as ex:
            futs = {ex.submit(_b.build_one, j): j for j in jobs}
            for f in as_completed(futs):
                tag, status = f.result()
                print(f"  {tag:30s} {status}", flush=True)
        custom_analyze()
