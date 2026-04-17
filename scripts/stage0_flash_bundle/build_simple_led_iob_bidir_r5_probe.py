# SPDX-License-Identifier: GPL-3.0-or-later
"""HW probe: simple_led + IOB_IN + IOB_OUT + IOB_OE on PIN_R5 (bidir composition).

Closes the open gate in `iob_oe_r5_bisection_silicon.md`:

    "Full composition with IOB_IN/IOB_OUT on silicon is still untested
     — nothing in this session exercised a combined tristate+input
     design; only the bare OE overlay on simple_led was HW-verified."

The prior R5 bisection (`build_iob_oe_r5_bisect.py`, 2026-04-17) proved
that the CLEAN38 IOB_OE set composes with simple_led_pure's fabric
without any LED regression.  But that test only flipped the 38 OE
config cells; R5 was still a passive pin — no fabric signal was being
routed to it, and its input/output buffer cells were untouched.

This probe adds the next layer: overlay all three pin directives
(`IOB_IN PIN_R5` + `IOB_OUT PIN_R5` + `IOB_OE PIN_R5`) on top of
simple_led_pure.  The directives were mined independently against an
iob_in_E15 anchor, so XOR-parity composition may cancel shared bits
that both directives need set — this probe surfaces that at the CRAM
level and, if safety-gated OK, produces an RBF whose flash decides
whether `$tribuf` np2fasm emission can safely bundle all three lines.

Per-pin cell counts (after loader masks):

    IOB_IN  PIN_R5  : 125 cells (input_delta)
    IOB_OUT PIN_R5  : 180 cells (output_delta)
    IOB_OE  PIN_R5  :  38 cells (oe_cells, silicon-clean)
    XOR-union       : 213 cells (65 cancelled by overlap-parity)
    set-union       : 278 cells

Expected HW behavior if composition is safe:

  * LED0 still follows KEY2 exactly as simple_led_pure (because R5 has
    no actual fabric route in this design — only its pad config cells
    flip, and simple_led's LED path on E16→X10Y4→G15 is untouched).
  * If LED behavior changes, IOB_IN/IOB_OUT cells for R5 leak into
    the LED path despite their physical distance from E16/G15 (same
    failure mode as the original IOB_OE_PIN_R5 FAIL pre-CLEAN38).
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "fuzz"))

import fasm2rbf as f
from pure_zero_rbf import make_pure_zero_rbf


PRE = 32
FRAME = 210
FIRST = 25
LAST = 1751
CRAM_START = PRE + FIRST * FRAME
CRAM_END = PRE + (LAST + 1) * FRAME
SAFE_FRAME_LO, SAFE_FRAME_HI = 1692, 1738


FASM = """\
NV_BASELINE_PACK
IOB_BASELINE_NV
IOB_IN  PIN_E16
IOB_OUT PIN_G15
IOB_CLK_INPUT PIN_E1
IOB_ROUTE PIN_E16 -> X10Y4N0.dataa
GCLK_PIN PIN_E1
LAB_CLK_SEL X10Y4
LAB_CLK_SEL_LE X10Y4N0
IOB_IN_BIDIR  PIN_R5
IOB_OUT_BIDIR PIN_R5
IOB_OE        PIN_R5
"""


def _bit_diff_set(a: bytes, b: bytes) -> set[tuple[int, int]]:
    out = set()
    for off in range(len(a)):
        x = a[off] ^ b[off]
        if not x:
            continue
        for bp in range(8):
            if x & (1 << bp):
                out.add((off, bp))
    return out


def _reset_caches():
    f._IOB_BASELINE_HDR_CACHE = None
    f._IOB_MAP_CACHE = None
    f._IOB_ROUTE_CACHE = None
    f._GCLK_PIN_CACHE = None
    f._LAB_CLK_SEL_CACHE.clear()
    f._LAB_CLK_SEL_LE_CACHE = None
    f._IOB_OE_CACHE = None


def main() -> int:
    pure = make_pure_zero_rbf()
    base_path = (REPO / "scripts" / "iob_slice_mining" / "work"
                 / "simple_led_E16_to_G15" / "fasm_pure.rbf")
    base_rbf = base_path.read_bytes() if base_path.exists() else None

    _reset_caches()
    out = f.bitgen(FASM, pure, patch_crc=True)

    out_path = HERE / "simple_led_iob_bidir_r5.rbf"
    out_path.write_bytes(out)
    print(f"[wrote] {out_path}  ({len(out)} bytes)")

    if not base_rbf:
        print("[skip] base simple_led_pure.rbf not found — cannot run safety gate")
        return 1

    diffs = [i for i in range(len(out)) if out[i] != base_rbf[i]]
    cram = [i for i in diffs if CRAM_START <= i < CRAM_END]
    hdr = [i for i in diffs if i < CRAM_START]
    trl = [i for i in diffs if i >= CRAM_END]
    data_cells = [i for i in cram if (i - PRE) % FRAME < 208]
    crc_diffs = [i for i in cram if (i - PRE) % FRAME >= 208]

    print(f"\n vs simple_led_pure: {len(diffs)} byte diffs")
    print(f"   hdr   : {len(hdr):4d}")
    print(f"   CRAM  : {len(cram):4d}")
    print(f"     data : {len(data_cells):4d} (expect net XOR of three R5 deltas)")
    print(f"     CRC  : {len(crc_diffs):4d}")
    print(f"   trl   : {len(trl):4d}")

    if data_cells:
        fc = Counter((i - PRE) // FRAME for i in data_cells)
        print(f"   data frame range: {min(fc)}..{max(fc)}")

    # STRICT SAFETY GATE (same as build_simple_led_iob_oe_probe).
    sl_bits = _bit_diff_set(pure, base_rbf)
    di_bits = _bit_diff_set(base_rbf, out)
    overlap = sl_bits & di_bits
    crc_ov   = [(o,bp) for o,bp in overlap if (o-PRE)%FRAME >= 208]
    hdr_ov   = [(o,bp) for o,bp in overlap
                if (o-PRE)%FRAME < 208 and (o-PRE)//FRAME < 25]
    block_ov = [(o,bp) for o,bp in overlap
                if (o-PRE)%FRAME < 208
                and SAFE_FRAME_LO <= (o-PRE)//FRAME <= SAFE_FRAME_HI]
    fabric_ov = [(o,bp) for o,bp in overlap
                 if (o-PRE)%FRAME < 208
                 and 25 <= (o-PRE)//FRAME < SAFE_FRAME_LO]
    print(f"\n bit-level overlap with simple_led: total={len(overlap)}  "
          f"CRC={len(crc_ov)}  hdr_band={len(hdr_ov)}  "
          f"block_band={len(block_ov)}  fabric={len(fabric_ov)}")
    print(f"   (simple_led={len(sl_bits)} bits, triple-dir={len(di_bits)} bits)")

    if fabric_ov or hdr_ov:
        print(f"\n  [UNSAFE] {len(fabric_ov)} fabric + {len(hdr_ov)} hdr "
              f"overlap bits cancel simple_led_pure's active cells — "
              f"DO NOT FLASH.")
        if fabric_ov:
            print(f"  fabric_ov (first 20):")
            for off, bp in sorted(fabric_ov)[:20]:
                frame = (off - PRE) // FRAME
                print(f"    off={off} bp={bp} frame={frame}")
        if hdr_ov:
            from collections import Counter as _C
            fc = _C((o-PRE)//FRAME for o,_ in hdr_ov)
            print(f"  hdr_ov frame histogram: {dict(sorted(fc.items()))}")
        return 1

    # Cross-check: directive bits should be explicable by combining the
    # three per-pin R5 cell sets under XOR parity.
    with open(REPO / "results" / "iob_cell_map.json") as fh:
        iob = json.load(fh)
    with open(REPO / "results" / "iob_oe_cell_map.json") as fh:
        _ = json.load(fh)  # loaded elsewhere via _load_iob_oe_cells

    in_R5 = {tuple(c) for c in iob["input_delta"].get("R5", [])}
    out_R5 = {tuple(c) for c in iob["output_delta"].get("R5", [])}
    _reset_caches()
    oe_R5 = {tuple(c) for c in f._load_iob_oe_cells("R5")}

    predicted_xor = in_R5 ^ out_R5 ^ oe_R5
    # di_bits also includes the simple_led fixture (IOB_IN E16, IOB_OUT G15,
    # IOB_CLK_INPUT E1, IOB_BASELINE_NV, IOB_ROUTE, GCLK_PIN, etc.) — to
    # isolate the R5 delta we subtract a reference build with the same
    # fixture minus the 3 R5 lines. That reference IS the existing
    # simple_led_iob_oe_r5 path minus the IOB_OE line — but we already
    # have simple_led_iob_oe_r5.rbf (IOB_OE only) from the prior probe,
    # so compute:  R5_triple_delta = out ^ simple_led_iob_oe_r5
    # This isolates IN+OUT contribution beyond the verified OE layer.
    prior = HERE / "simple_led_iob_oe_r5.rbf"
    if prior.exists():
        prior_rbf = prior.read_bytes()
        in_out_layer = _bit_diff_set(prior_rbf, out)
        in_out_fabric = [(o,bp) for o,bp in in_out_layer
                         if (o-PRE)%FRAME < 208
                         and not (SAFE_FRAME_LO <= (o-PRE)//FRAME <= SAFE_FRAME_HI)]
        print(f"\n IN+OUT layer delta vs prior IOB_OE-only build: "
              f"{len(in_out_layer)} bits (fabric={len(in_out_fabric)})")

    print(f"\n expected R5 XOR-union: {len(predicted_xor)} cells "
          f"(in={len(in_R5)}, out={len(out_R5)}, oe={len(oe_R5)})")

    if block_ov:
        print(f"\n  [SAFE*] {len(block_ov)} overlap bits are all in block "
              f"band (frames {SAFE_FRAME_LO}..{SAFE_FRAME_HI}). simple_led "
              f"uses no block feature, so XOR-flipping these cannot affect "
              f"LED behavior — safe to flash.")
    else:
        print(f"\n  [SAFE] directive bits are disjoint from simple_led's "
              f"active cells — safe to flash.")

    print("\nExpected HW behavior: LED0 still follows KEY2 (identical to "
          "simple_led_pure). If LED stuck, IOB_IN/IOB_OUT cells for R5 "
          "leak into functional fabric despite the CLEAN38 OE result.")
    print("If PASS: $tribuf np2fasm emission can safely bundle "
          "IOB_IN + IOB_OUT + IOB_OE for the same pin.")
    print("If FAIL: IN/OUT layer needs its own bisection (the CLEAN38 "
          "mask covered OE only).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
