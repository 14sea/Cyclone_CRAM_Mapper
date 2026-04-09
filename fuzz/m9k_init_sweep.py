# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.2 Stage A — M9K init walking-1 sweep at word=0.

Compile one zero-init baseline + WIDTH targets, each with a single
init bit set at word=0. Pair-diff vs baseline, report per-bit cell
count, check that the per-bit cell sets are disjoint (pure SRAM
should give non-overlapping cells per bit).

Stage A go/no-go on the output:
  - 1..4 cells per bit, disjoint across bits, inside block band
    -> Stage B (XOR-linear basis synthesis) is unblocked
  - >50 cells per bit or heavy overlap -> init is not stored as
    flat SRAM; Quartus is doing interleaving/scramble. Switch to
    Stage A' (structured-pattern inverse solve).

Timings are logged per compile so we can project Stage B cost
(4608-bit basis). If a compile is ~90s here, Stage B needs
walking-1 only for the basis (~10 compiles per mode class), not
all 4608.
"""
import os, sys, json, time
from concurrent.futures import ProcessPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m9k_init_harness import build, WIDTH, DEPTH
from m9k_init_null import cram_cells, block_band_cells, BLOCK_FRAMES
from config import RBF_DIR

MAX_WORKERS = 4


def job(task):
    tag, overrides = task
    out = os.path.join(RBF_DIR, f"{tag}.rbf")
    rbf, t, err = build(tag, overrides=overrides, rbf_output=out)
    return tag, rbf, t, err


def main():
    tasks = [("m9k_init_base", None)]
    for bit in range(WIDTH):
        tasks.append((f"m9k_init_w0_b{bit}", {0: (1 << bit)}))

    timings = {}
    print(f"dispatching {len(tasks)} compiles "
          f"(1 baseline + {WIDTH} walking-1) across "
          f"{MAX_WORKERS} workers...")
    t_start = time.time()
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(job, tk): tk for tk in tasks}
        for f in as_completed(futs):
            tag, rbf, t, err = f.result()
            timings[tag] = t
            if rbf is None:
                print(f"  {tag:22s} FAIL ({t:.1f}s): {err[:200]}")
            else:
                print(f"  {tag:22s} OK   ({t:.1f}s)")
    print(f"total wall: {time.time()-t_start:.1f}s")

    base_path = os.path.join(RBF_DIR, "m9k_init_base.rbf")
    if not os.path.exists(base_path):
        print("baseline failed — abort")
        return
    base = open(base_path, "rb").read()

    per_bit = {}
    for bit in range(WIDTH):
        p = os.path.join(RBF_DIR, f"m9k_init_w0_b{bit}.rbf")
        if not os.path.exists(p):
            per_bit[bit] = None
            continue
        other = open(p, "rb").read()
        cells = cram_cells(base, other)
        block = block_band_cells(cells)
        per_bit[bit] = {
            "all_cram": sorted(cells),
            "block_band": sorted(block),
        }

    print("\n=== per-bit delta (word=0 walking-1) ===")
    print(f"{'bit':>4} | {'all_cram':>9} | {'block_band':>11} | block-band cells")
    print("-" * 74)
    for bit in range(WIDTH):
        r = per_bit[bit]
        if r is None:
            print(f"  {bit:2d}  |    FAIL   |     FAIL    |")
            continue
        bb = r["block_band"]
        preview = ", ".join(f"({c[0]},{c[1]})" for c in bb[:4])
        if len(bb) > 4:
            preview += f", ... (+{len(bb)-4})"
        print(f"  {bit:2d}  | {len(r['all_cram']):>9} | {len(bb):>11} | {preview}")

    # Disjointness check inside block band.
    print("\n=== disjointness check (block band) ===")
    seen = {}
    overlaps = []
    for bit in range(WIDTH):
        r = per_bit[bit]
        if r is None:
            continue
        for c in r["block_band"]:
            key = tuple(c)
            if key in seen:
                overlaps.append((key, seen[key], bit))
            else:
                seen[key] = bit
    if not overlaps:
        print("  clean — every block-band cell appears in at most one bit")
    else:
        print(f"  OVERLAPS: {len(overlaps)} cells shared across bits")
        for c, a, b in overlaps[:10]:
            print(f"    {c} shared by bit {a} and bit {b}")

    # Go/no-go summary
    print("\n=== Stage A verdict ===")
    bb_counts = [len(per_bit[b]["block_band"]) for b in range(WIDTH)
                 if per_bit[b] is not None]
    if not bb_counts:
        verdict = "ABORT (all compiles failed)"
    elif all(1 <= c <= 4 for c in bb_counts) and not overlaps:
        verdict = "GREEN — proceed to Stage B (basis synthesis)"
    elif all(c <= 16 for c in bb_counts):
        verdict = "YELLOW — block band reacts but scrambled; investigate"
    elif all(c == 0 for c in bb_counts):
        verdict = "RED — init bits are NOT in frames 1692-1738; widen band search"
    else:
        verdict = "RED — heavy noise or overlap; switch to Stage A' structured patterns"
    print(f"  {verdict}")

    os.makedirs("results", exist_ok=True)
    with open("results/m9k_init_sweep.json", "w") as f:
        json.dump({
            "width": WIDTH,
            "depth": DEPTH,
            "timings": timings,
            "per_bit": {
                str(b): {
                    "all_cram": per_bit[b]["all_cram"] if per_bit[b] else None,
                    "block_band": per_bit[b]["block_band"] if per_bit[b] else None,
                } for b in range(WIDTH)
            },
            "overlaps": [{"cell": list(c), "bits": [a, b]}
                         for c, a, b in overlaps],
            "verdict": verdict,
        }, f, indent=1)
    print("\narchived results/m9k_init_sweep.json")


if __name__ == "__main__":
    main()
