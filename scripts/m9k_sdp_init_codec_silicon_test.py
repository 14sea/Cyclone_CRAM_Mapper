#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Non-tautological SDP 4×2048 INIT codec silicon test.

Audit 2026-04-27: the original SDP "blink" silicon test was a near-tautology —
codec wrote pattern [0]*1024+[1]*1024 onto the Quartus allzero base, producing
an RBF that differs from the Quartus gold blink by only 6 header bytes (the
SDP design reads only dout[0], so Quartus optimized away bits 1-3, leaving
only bit-0 cells set in the high half — exactly what the codec also writes).

This script writes a SPATIAL pattern Quartus would never produce: stripes of
64 words alternating 0/1.  At the design's read rate (~2.62 ms/word), this
gives 32 stripes of 168 ms each → LED blinks at ~3 Hz (16× faster than the
gold 0.186 Hz).  If silicon shows the predicted fast blink, the codec's
word→CRAM-cell mapping is silicon-validated for spatial patterns (32 distinct
word positions across the high half, not just "high vs low").

Base RBF: tmp/m9k_sdp_blink_4x2048_allzero_X15_Y10_N0/...rbf  (Quartus build
with MIF=allzero — known cell baseline; codec writes are pure 0→1 flips).

Predicted silicon behavior: LED0 fast-blinks at ~3 Hz (336 ms full period).
Gold reference: LED0 slow-blinks at ~0.186 Hz (5.37 s full period).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))

from bitstream import patch_rbf_crc
from m9k_init_basis import (
    SDP_4X2048_BASE_FRAMES,
    read_init_sdp4x2048,
    write_init_sdp4x2048,
)

SITE = "X15_Y10_N0"
BASE_RBF = (ROOT / "tmp" /
            "m9k_sdp_blink_4x2048_allzero_X15_Y10_N0" /
            "m9k_sdp_blink_4x2048_allzero_X15_Y10_N0.rbf")
GOLD_RBF = ROOT / "tmp" / "m9k_sdp_blink_4x2048" / "m9k_sdp_blink_4x2048.rbf"
OUT_DIR = ROOT / "tmp"

LOADER = (
    Path.home() / "see_neorv32_run_linux" / "tools" /
    "openFPGALoader" / "build" / "openFPGALoader"
)


def _striped_pattern(stripe_words: int = 64) -> list[int]:
    return [(i // stripe_words) & 1 for i in range(2048)]


def _build(tag: str, target_words: list[int]) -> Path:
    if not BASE_RBF.exists():
        sys.exit(f"base RBF not found: {BASE_RBF}")

    bf = SDP_4X2048_BASE_FRAMES[SITE]
    base = BASE_RBF.read_bytes()
    current = read_init_sdp4x2048(base, bf)
    if any(w != 0 for w in current):
        sys.exit("base RBF is not all-zero — pattern reasoning would be invalid")

    modified = write_init_sdp4x2048(base, bf, current, target_words)
    modified = patch_rbf_crc(modified)

    out = OUT_DIR / f"sdp_silicon_test_{tag}.rbf"
    out.write_bytes(modified)

    # Round-trip + audit: count diff vs base AND vs gold
    check = read_init_sdp4x2048(modified, bf)
    mismatch = sum(a != b for a, b in zip(check, target_words))
    if mismatch:
        sys.exit(f"FAIL: round-trip has {mismatch} mismatches")

    diff_base = sum(1 for x, y in zip(modified, base) if x != y)
    diff_gold = (sum(1 for x, y in zip(modified, GOLD_RBF.read_bytes()) if x != y)
                 if GOLD_RBF.exists() else None)

    print(f"[{tag}] wrote {out} ({len(modified)} bytes)")
    print(f"[{tag}] round-trip OK ({len(target_words)} words)")
    print(f"[{tag}] diff vs Quartus allzero base: {diff_base} bytes")
    if diff_gold is not None:
        print(f"[{tag}] diff vs Quartus gold blink:   {diff_gold} bytes")
        if diff_gold < 100:
            print(f"[{tag}] WARNING: near-tautology with gold (diff < 100)")

    # Stripe count for sanity
    transitions = sum(1 for i in range(1, len(target_words))
                      if target_words[i] != target_words[i-1])
    print(f"[{tag}] pattern stripe transitions: {transitions} "
          f"(expected blink frequency ~{transitions / 5.37 / 2:.2f} Hz)")
    return out


def _flash(rbf: Path) -> None:
    import subprocess
    if not LOADER.exists():
        sys.exit(f"openFPGALoader not found at {LOADER}")
    cmd = [str(LOADER), "-c", "usb-blaster", str(rbf)]
    print(f"flashing: {' '.join(cmd)}")
    rc = subprocess.run(cmd).returncode
    if rc != 0:
        sys.exit(f"flash FAIL (rc={rc})")
    print("flash OK")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stripe", type=int, default=64,
                    help="stripe width in words (default 64 → ~3 Hz blink)")
    ap.add_argument("--flash", action="store_true",
                    help="flash the resulting RBF after build")
    args = ap.parse_args()

    pattern = _striped_pattern(args.stripe)
    tag = f"stripe{args.stripe}"
    out = _build(tag, pattern)

    print(f"\nExpected silicon behavior:")
    print(f"  LED0 fast-blinks at ~{2048 // args.stripe / 5.37 / 2:.2f} Hz "
          f"(stripes={args.stripe} words = {args.stripe * 2.62:.0f} ms each)")
    print(f"  Gold reference: ~0.186 Hz (5.37 s full period)")

    if args.flash:
        _flash(out)


if __name__ == "__main__":
    main()
