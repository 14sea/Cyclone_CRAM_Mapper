#!/usr/bin/env python3
"""LI topology equivalence-class validation.

Refined hypothesis (2026-04-07):
  For a fixed (src_type, src_I, dst_N, dst_port) key, the set of CRAM pair
  activations at the destination LAB belongs to a FINITE EQUIVALENCE CLASS:
  Quartus' placer picks one of several legal physical MUX entries, all of
  which route the same source to the same LE input port.

What we test:
  - Sweep many destination LABs with identical compile shape
  - Read the pair set at each destination
  - Group by observed pair set; check if equivalence class is bounded
  - Look for structural features: common backbone, fixed cardinality,
    structured "selection" subset

Output is a feasibility report, not a hard verdict.
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bitstream import RouteCodec
from runner import (compile_route_pair, compile_route_single,
                    compile_route_pair_single_input,
                    compile_route_baseline_abcd)

# Wide sweep across the chip — column moves, row moves, both directions,
# both near-source and far-source. Source is fixed at (10,10,0).
TARGETS = [
    # column moves (same X=10)
    (10, 4),  (10, 5),  (10, 6),  (10, 7),  (10, 8),
    (10, 11), (10, 12), (10, 13), (10, 14),
    # row moves (same Y=10)
    (3, 10),  (4, 10),  (6, 10),  (7, 10),  (8, 10),
    (11, 10), (12, 10), (13, 10), (16, 10),
    (21, 10), (22, 10), (24, 10), (28, 10), (31, 10),
]

ZERO_TAG = "lits_zero_10_10"   # single-input variant baseline
TAG_PREFIX = "lits_pair"
CONNECT_PORT = "datab"
RBF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "results", "rbf")


def load(path):
    with open(path, "rb") as f:
        return f.read()


def read_pair_base_set_at(codec, design, zero, dx, dy):
    """Return frozenset of (pair, base_idx) cells active at LAB(dx,dy)."""
    li_entries = codec.read_local_interconnect(design, zero)
    cells = set()
    for name, off, bp, cands in li_entries:
        lx, ly, pair, base_idx = codec._parse_li_name(name)
        if (lx, ly) == (dx, dy):
            cells.add((pair, base_idx))
    return frozenset(cells)


def classify_mode(cells):
    """Classify via the canonical RouteCodec V2 classifier."""
    if not cells:
        return "empty"
    by_pair = {}
    for p, b in cells:
        by_pair.setdefault(p, set()).add(b)
    mode, _reason = RouteCodec._classify_li_lab(by_pair)
    return mode


def main():
    codec = RouteCodec()

    # Baseline
    zero_path = os.path.join(RBF_DIR, ZERO_TAG + ".rbf")
    if not os.path.exists(zero_path):
        print(f"Compiling baseline {ZERO_TAG} ...", flush=True)
        rbf, t, err = compile_route_baseline_abcd(ZERO_TAG, 10, 10, 0)
        if not rbf:
            print(f"FAIL: {err}")
            return
        print(f"  OK ({t:.1f}s)")
    zero = load(zero_path)

    # Compile (or reuse) every target
    results = []   # (dx, dy, frozenset((pair, base_idx)))
    for dx, dy in TARGETS:
        tag = f"{TAG_PREFIX}_X10Y10_to_X{dx}Y{dy}N0_{CONNECT_PORT}"
        rbf_path = os.path.join(RBF_DIR, tag + ".rbf")
        if not os.path.exists(rbf_path):
            print(f"Compiling {tag} ...", flush=True)
            rbf, t, err = compile_route_pair_single_input(
                tag, 10, 10, 0, dx, dy, 0, connect_port=CONNECT_PORT)
            if not rbf:
                print(f"  FAIL: {err}")
                continue
            print(f"  OK ({t:.1f}s)")
        design = load(rbf_path)
        ps = read_pair_base_set_at(codec, design, zero, dx, dy)
        results.append((dx, dy, ps))

    # === Analysis ===
    print(f"\n{'='*64}")
    print(f"  Per-LAB pair sets ({len(results)} samples)")
    print(f"{'='*64}")
    for dx, dy, ps in results:
        mode = classify_mode(ps)
        marker = "  " if ps else "??"
        if ps:
            cells_str = " ".join(f"P{p}B{b}" for p, b in sorted(ps))
            print(f"  {marker} LAB(X{dx:2d},Y{dy:2d}) [{mode:11s}] n={len(ps):2d}: {cells_str}")
        else:
            print(f"  {marker} LAB(X{dx:2d},Y{dy:2d}) [empty]      (baseline aliasing)")

    # Filter empties for the equivalence-class analysis
    valid = [(dx, dy, ps) for dx, dy, ps in results if ps]
    empties = [(dx, dy) for dx, dy, ps in results if not ps]

    print(f"\n{'='*64}")
    print("  Equivalence class structure")
    print(f"{'='*64}")
    print(f"  Valid samples: {len(valid)} / {len(results)} "
          f"({len(empties)} empty, excluded)")
    if empties:
        print(f"  Empty LABs: {empties}")

    # Group by pair set
    classes = defaultdict(list)
    for dx, dy, ps in valid:
        classes[ps].append((dx, dy))

    print(f"\n  Distinct equivalence classes: {len(classes)}")
    for i, (ps, labs) in enumerate(sorted(classes.items(),
                                          key=lambda kv: -len(kv[1]))):
        mode = classify_mode(ps)
        cells_str = " ".join(f"P{p}B{b}" for p, b in sorted(ps))
        print(f"\n  Class {i+1} [{mode}] n={len(ps)}: {cells_str}")
        print(f"           used at {len(labs)} LABs:")
        for lab in labs:
            print(f"             X{lab[0]:2d},Y{lab[1]:2d}")

    # Mode tally
    from collections import Counter
    mode_tally = Counter(classify_mode(ps) for _, _, ps in valid)
    print(f"\n  Mode tally across {len(valid)} valid LABs: {dict(mode_tally)}")

    # Structural analysis
    if len(classes) > 1:
        all_sets = list(classes.keys())
        backbone = set.intersection(*(set(s) for s in all_sets))
        union = set().union(*(set(s) for s in all_sets))
        cards = set(len(s) for s in all_sets)

        print(f"\n  Structural features:")
        print(f"    Cardinality across all classes: {sorted(cards)}"
              f"  {'(uniform)' if len(cards)==1 else '(VARIES — suspicious)'}")
        print(f"    Backbone (pairs in EVERY class): {sorted(backbone)}")
        print(f"    Union of all pairs ever seen:    {sorted(union)}")
        variable = union - backbone
        print(f"    Variable selection pool:         {sorted(variable)}")

        # Per-class "selection bits" (variable part only)
        print(f"\n  Per-class variable subsets:")
        for ps, labs in sorted(classes.items(), key=lambda kv: -len(kv[1])):
            sel = sorted(set(ps) - backbone)
            print(f"    {sorted(ps)} → variable={sel}")

    # Verdict heuristics
    print(f"\n{'='*64}")
    print("  Verdict")
    print(f"{'='*64}")
    if len(classes) == 1:
        print(f"  ✅ STRICT topology replication: 1 class for {len(valid)} LABs.")
    elif len(classes) <= 5 and len(valid) >= 10:
        if len(set(len(s) for s in classes.keys())) == 1:
            print(f"  ✅ EQUIVALENCE-CLASS topology replication likely:")
            print(f"     {len(classes)} bounded classes covering {len(valid)} LABs,")
            print(f"     all with uniform cardinality. NextPNR can pick any class.")
        else:
            print(f"  ⚠ Equivalence classes exist but cardinality varies — investigate.")
    else:
        print(f"  ❌ {len(classes)} classes for {len(valid)} LABs — equivalence set "
              f"not yet bounded; need more samples or extra key dimension.")


if __name__ == "__main__":
    main()
