# SPDX-License-Identifier: GPL-3.0-or-later
"""Non-tautological M9K_INIT codec silicon test.

Takes the Quartus-gold SP 9×512 blink RBF (at X15_Y10_N0, blinks LED0 at
~0.186 Hz) and rewrites only the M9K INIT data via codec to produce two
variants:

  allzero: all 512 words = 0x000  → LED permanently OFF
  allone:  all 512 words = 0x1FF  → LED permanently ON  (bit 0 = 1)

Neither variant was built by Quartus. MODE, COLUMN_INFRA, and all other CRAM
regions come from Quartus's original build (silicon-correct). Only the INIT
cells change. This is the first non-tautological M9K_INIT silicon test.

Background: the 4×2048 SDP INIT formula is uncalibrated for non-zero content
(discovered this session — actual cells at frames 699+, byte range 59-86, vs
formula's frames 1083+). SP 9×512 is independently calibrated at X15_Y10_N0.

Flashing:
  python3 scripts/m9k_init_codec_silicon_test.py --flash allzero  # LED OFF
  python3 scripts/m9k_init_codec_silicon_test.py --flash allone   # LED ON
  python3 scripts/m9k_init_codec_silicon_test.py --flash restore  # original blink

PASS criteria:
  allzero: LED0 stays dark regardless of time elapsed
  allone:  LED0 stays lit  regardless of time elapsed
  restore: LED0 blinks ~0.186 Hz (2.68 s on / 2.68 s off)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))

from bitstream import patch_rbf_crc
from m9k_init_basis import M9K_INIT_ANCHORS, write_init, read_init

SITE     = "X15_Y10_N0"
WIDTH    = 9
DEPTH    = 512
GOLD_RBF = ROOT / "tmp" / "m9k_blink_9x512" / "m9k_blink_9x512.rbf"
OUT_DIR  = ROOT / "tmp"

LOADER   = (
    Path.home() / "see_neorv32_run_linux" / "tools" /
    "openFPGALoader" / "build" / "openFPGALoader"
)

_ALLZERO_WORDS  = [0x000] * DEPTH
_ALLONE_WORDS   = [0x1FF] * DEPTH


def _read_gold_words() -> list[int]:
    """Read the actual INIT words from the gold RBF (Quartus-optimized content)."""
    key = (SITE, WIDTH, DEPTH)
    anchor, bp = M9K_INIT_ANCHORS[key]
    return read_init(GOLD_RBF.read_bytes(), anchor, width=WIDTH, depth=DEPTH, bp=bp)


def _build(tag: str, target_words: list[int]) -> Path:
    key = (SITE, WIDTH, DEPTH)
    if key not in M9K_INIT_ANCHORS:
        sys.exit(f"anchor not found for {key}")
    anchor, bp = M9K_INIT_ANCHORS[key]

    gold = GOLD_RBF.read_bytes()

    # Read current INIT from the gold RBF so we have the correct XOR base.
    current = read_init(gold, anchor, width=WIDTH, depth=DEPTH, bp=bp)
    print(f"[{tag}] read_init: first 8 words = {[hex(w) for w in current[:8]]}, "
          f"last 8 = {[hex(w) for w in current[-8:]]}")

    modified = write_init(gold, anchor, current, target_words,
                          width=WIDTH, depth=DEPTH, bp=bp)
    modified = patch_rbf_crc(modified)

    out = OUT_DIR / f"m9k_init_silicon_test_{tag}.rbf"
    out.write_bytes(modified)
    print(f"[{tag}] wrote {out} ({len(modified)} bytes)")

    # Verify round-trip
    check = read_init(modified, anchor, width=WIDTH, depth=DEPTH, bp=bp)
    mismatches = sum(a != b for a, b in zip(check, target_words))
    print(f"[{tag}] round-trip: first 8 = {[hex(w) for w in check[:8]]}, "
          f"last 8 = {[hex(w) for w in check[-8:]]}, mismatches = {mismatches}")
    if mismatches:
        sys.exit(f"FAIL: round-trip has {mismatches} mismatches — aborting")
    print(f"[{tag}] round-trip PASS ({DEPTH} words match)")

    return out


def _flash(rbf: Path) -> None:
    import subprocess
    if not LOADER.exists():
        sys.exit(f"openFPGALoader not found at {LOADER}")
    cmd = [str(LOADER), "-c", "usb-blaster", str(rbf)]
    print(f"flashing: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        sys.exit(f"flash FAIL (rc={result.returncode})")
    print("flash OK")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--flash", choices=["allzero", "allone", "restore", "none"],
                    default="none",
                    help="build + flash a variant (none = build only)")
    ap.add_argument("--build-all", action="store_true",
                    help="build all three variants without flashing")
    args = ap.parse_args()

    tag_map = {
        "allzero": _ALLZERO_WORDS,
        "allone":  _ALLONE_WORDS,
        "restore": _read_gold_words(),   # exact current CRAM state → zero delta → identical to gold
    }

    if args.build_all or args.flash == "none":
        for tag, words in tag_map.items():
            _build(tag, words)
        return

    out = _build(args.flash, tag_map[args.flash])
    _flash(out)
    print(f"\nExpected silicon behavior:")
    if args.flash == "allzero":
        print("  LED0 = permanently OFF  (M9K always outputs 0x000, bit0=0)")
    elif args.flash == "allone":
        print("  LED0 = permanently ON   (M9K always outputs 0x1FF, bit0=1)")
    else:
        print("  LED0 = blinks ~0.186 Hz (2.68 s on / 2.68 s off)")


if __name__ == "__main__":
    main()
