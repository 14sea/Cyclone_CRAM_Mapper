#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase A / STEP A1 — classify the live NEORV32 bitstream by routing class.

Runs the codec's routing read-models against the real NEORV32 Quartus gold
(diffed vs nv_zero_global) and classifies every cell each model CLAIMS as
CRC-byte (dead — overwritten by patch_rbf_crc) vs real CRAM (emittable).

Purpose (read-only, no Quartus, no flash):
  * Empirically confirm STEP 0 on a REAL dense design — the dead classes
    (C4 I≠0, R24) should claim only CRC bytes; the REAL classes (C4 I=0,
    R4, LI) should claim real CRAM.
  * Bound how much routing the existing models detect in NEORV32, and how
    much active fabric is left UNCLAIMED by every routing model (the
    "Block-interconnect" + logic mass that A2 must resolve).

Note: the gold's active fabric is dominated by LOGIC (LUT TTs / FF / M9K),
not routing — so "unclaimed" here is an upper bound on the unmodeled mass;
A2 (Quartus wire-name census) is the authoritative route-class source.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "fuzz"))

from bitstream import RouteCodec  # noqa: E402

GOLD = Path("/home/test/see_neorv32_run_linux/output/neorv32_demo.rbf")
ZERO = REPO / "results" / "rbf" / "nv_zero_global.rbf"

PRE = 32
FRAME = 210
FDATA = 208
HDR_END = 5282


def classify(off: int) -> str:
    if off < HDR_END:
        return "HEADER"
    if (off - PRE) % FRAME >= FDATA:
        return "CRC"
    return "CRAM"


def main() -> int:
    if not GOLD.exists():
        print(f"SKIP: NEORV32 gold {GOLD} not present")
        return 0
    gold = GOLD.read_bytes()
    zero = ZERO.read_bytes()
    rc = RouteCodec()

    # active fabric-CRAM set (off>=5282, non-CRC) — what real routing+logic touches
    active_cram = set()
    for off in range(len(gold)):
        x = gold[off] ^ zero[off]
        if not x:
            continue
        for bp in range(8):
            if x & (1 << bp) and classify(off) == "CRAM":
                active_cram.add((off, bp))
    print(f"NEORV32 gold vs nv_zero: {len(active_cram)} active fabric-CRAM cells "
          f"(LOGIC + routing combined)\n")

    # Each read-model's claimed cells, split CRC vs CRAM, and overlap w/ active.
    models = {
        "read_c4 (I=0 + I≠0)": rc.read_c4,
        "read_r4": rc.read_r4,
        "read_r24": rc.read_r24,
        "read_local_interconnect": rc.read_local_interconnect,
    }
    print(f"{'model':<26} {'claims':>7} {'CRAM':>7} {'CRC':>7} {'CRAM∩active':>12}")
    print("-" * 64)
    all_cram_claims = set()
    for name, fn in models.items():
        try:
            sw = fn(gold, zero)
        except Exception as e:  # noqa: BLE001
            print(f"  {name}: ERROR {e}")
            continue
        # entries are (wire, off, bp[, candidates]) — position-based unpack
        claims = {(e[1], e[2]) for e in sw}
        cram = {c for c in claims if classify(c[0]) == "CRAM"}
        crc = {c for c in claims if classify(c[0]) == "CRC"}
        hit = cram & active_cram
        all_cram_claims |= hit
        print(f"{name:<26} {len(claims):>7} {len(cram):>7} {len(crc):>7} "
              f"{len(hit):>12}")

    print("-" * 64)
    unclaimed = active_cram - all_cram_claims
    print(f"\nactive fabric-CRAM cells claimed by ANY routing model (CRAM): "
          f"{len(all_cram_claims)} ({100*len(all_cram_claims)/len(active_cram):.1f}%)")
    print(f"UNCLAIMED by every routing model: {len(unclaimed)} "
          f"({100*len(unclaimed)/len(active_cram):.1f}%) "
          f"— = LOGIC (LUT/FF/M9K) + clock + IOB + unmodeled 'Block' routing")

    print("\n=== A1 verdict ===")
    print("  - Dead-class confirmation: read_c4's I≠0 + read_r24 claims should be")
    print("    CRC-classified (the DEAD tables); see CRC column above.")
    print("  - The huge UNCLAIMED fraction is mostly LOGIC (placement unknown here),")
    print("    so it does NOT directly equal 'Block-interconnect' routing — A2")
    print("    (Quartus wire-name census) is required to isolate routing classes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
