#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Non-tautological silicon stripe-pattern test for SP 9×1024 and SP 36×256
INIT codecs at X15_Y10_N0.

Mirrors the SDP 4×2048 stripe64 methodology (`m9k_sdp_init_codec_silicon_test.py`):
write a spatial pattern Quartus would never produce, then watch LED0 to confirm
the codec's word→CRAM-cell mapping is silicon-correct.

Both designs read addr at counter[27:N] over the full depth and XOR-fold the
data port into LED0:
  9×1024  : addr=counter[27:18], 1024 words ⇒ ~5.24 ms/word, 5.37 s sweep
  36×256  : addr=counter[27:20],  256 words ⇒ ~21.0 ms/word, 5.37 s sweep

stripe=N alternating high/low words → LED phase = N × per-word time.

For stripe=32 on 9×1024 → 168 ms phase → ~3 Hz blink (16 high + 16 low stripes).
For stripe= 8 on 36×256 → 168 ms phase → ~3 Hz blink (16 high + 16 low stripes).

High word = any odd-parity value (^bits = 1).  Low word = 0 (^bits = 0).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))

from bitstream import patch_rbf_crc
from m9k_init_basis import (
    SP_9X1024_BASE_FRAMES,
    SP_36X256_BASE_FRAMES,
    read_init_sp9x1024,
    write_init_sp9x1024,
    read_init_sp36x256,
    write_init_sp36x256,
)

SITE = "X15_Y10_N0"
OUT_DIR = ROOT / "tmp"
LOADER = (
    Path.home() / "see_neorv32_run_linux" / "tools" /
    "openFPGALoader" / "build" / "openFPGALoader"
)

# 9×1024 setup ───────────────────────────────────────────────────────────────
BASE_9X1024 = (ROOT / "tmp" /
               "sp_9x1024_allzero_X15_Y10_N0" /
               "sp_9x1024_allzero_X15_Y10_N0.rbf")
HIGH_VAL_9 = 0x1FF        # all 9 bits set, ^=1
DEPTH_9    = 1024
WORD_MS_9  = 5.24         # counter[27:18] / 50 MHz

# 36×256 setup ───────────────────────────────────────────────────────────────
BASE_36X256 = (ROOT / "tmp" /
               "sp_36x256_allzero_X15_Y10_N0" /
               "sp_36x256_allzero_X15_Y10_N0.rbf")
HIGH_VAL_36 = 0x1          # bit-0 set, ^=1 (avoids parity-zero 36'hF...F)
DEPTH_36    = 256
WORD_MS_36  = 20.97        # counter[27:20] / 50 MHz


def _stripe(depth: int, stripe_words: int, hi: int) -> list[int]:
    return [hi if ((i // stripe_words) & 1) else 0 for i in range(depth)]


def _flash(rbf: Path) -> None:
    if not LOADER.exists():
        sys.exit(f"openFPGALoader not found at {LOADER}")
    cmd = [str(LOADER), "-c", "usb-blaster", str(rbf)]
    print(f"flashing: {' '.join(cmd)}")
    rc = subprocess.run(cmd).returncode
    if rc != 0:
        sys.exit(f"flash FAIL (rc={rc})")
    print("flash OK")


def _build_9x1024(stripe_words: int) -> Path:
    if not BASE_9X1024.exists():
        sys.exit(f"base RBF not found: {BASE_9X1024}")
    bf   = SP_9X1024_BASE_FRAMES[SITE]
    base = BASE_9X1024.read_bytes()

    current = read_init_sp9x1024(base, bf, depth=DEPTH_9)
    if any(w != 0 for w in current):
        sys.exit("base RBF is not all-zero — pattern reasoning would be invalid")

    target = _stripe(DEPTH_9, stripe_words, HIGH_VAL_9)
    modified = write_init_sp9x1024(base, bf, current, target, depth=DEPTH_9)
    modified = patch_rbf_crc(modified)

    check = read_init_sp9x1024(modified, bf, depth=DEPTH_9)
    mismatch = sum(a != b for a, b in zip(check, target))
    if mismatch:
        sys.exit(f"FAIL: round-trip {mismatch} mismatches")

    out = OUT_DIR / f"sp_9x1024_silicon_test_stripe{stripe_words}.rbf"
    out.write_bytes(modified)

    diff_base = sum(1 for x, y in zip(modified, base) if x != y)
    transitions = sum(1 for i in range(1, DEPTH_9)
                      if target[i] != target[i-1])
    sweep_s = DEPTH_9 * WORD_MS_9 / 1000
    blink_hz = transitions / sweep_s / 2

    print(f"[9x1024 stripe={stripe_words}] wrote {out} ({len(modified)} bytes)")
    print(f"[9x1024 stripe={stripe_words}] round-trip OK ({DEPTH_9} words)")
    print(f"[9x1024 stripe={stripe_words}] diff vs allzero base: {diff_base} bytes")
    print(f"[9x1024 stripe={stripe_words}] stripe transitions: {transitions} → ~{blink_hz:.2f} Hz blink")
    return out


def _build_36x256(stripe_words: int) -> Path:
    if not BASE_36X256.exists():
        sys.exit(f"base RBF not found: {BASE_36X256}")
    bf   = SP_36X256_BASE_FRAMES[SITE]
    base = BASE_36X256.read_bytes()

    current = read_init_sp36x256(base, bf, depth=DEPTH_36)
    if any(w != 0 for w in current):
        sys.exit("base RBF is not all-zero — pattern reasoning would be invalid")

    target = _stripe(DEPTH_36, stripe_words, HIGH_VAL_36)
    modified = write_init_sp36x256(base, bf, current, target, depth=DEPTH_36)
    modified = patch_rbf_crc(modified)

    check = read_init_sp36x256(modified, bf, depth=DEPTH_36)
    mismatch = sum(a != b for a, b in zip(check, target))
    if mismatch:
        sys.exit(f"FAIL: round-trip {mismatch} mismatches")

    out = OUT_DIR / f"sp_36x256_silicon_test_stripe{stripe_words}.rbf"
    out.write_bytes(modified)

    diff_base = sum(1 for x, y in zip(modified, base) if x != y)
    transitions = sum(1 for i in range(1, DEPTH_36)
                      if target[i] != target[i-1])
    sweep_s = DEPTH_36 * WORD_MS_36 / 1000
    blink_hz = transitions / sweep_s / 2

    print(f"[36x256 stripe={stripe_words}] wrote {out} ({len(modified)} bytes)")
    print(f"[36x256 stripe={stripe_words}] round-trip OK ({DEPTH_36} words)")
    print(f"[36x256 stripe={stripe_words}] diff vs allzero base: {diff_base} bytes")
    print(f"[36x256 stripe={stripe_words}] stripe transitions: {transitions} → ~{blink_hz:.2f} Hz blink")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("design", choices=["9x1024", "36x256"],
                    help="which SP codec to test")
    ap.add_argument("--stripe", type=int,
                    help="stripe width in words (default: 32 for 9x1024, 8 for 36x256)")
    ap.add_argument("--flash", action="store_true",
                    help="flash the resulting RBF")
    args = ap.parse_args()

    if args.design == "9x1024":
        sw = args.stripe if args.stripe else 32
        out = _build_9x1024(sw)
    else:
        sw = args.stripe if args.stripe else 8
        out = _build_36x256(sw)

    if args.flash:
        _flash(out)


if __name__ == "__main__":
    main()
