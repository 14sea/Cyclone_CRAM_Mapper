#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.2 silicon hero — write a distinguishable M9K init pattern
via the Stage B codec, patch CRC, dump to results/rbf/m9k_hero.rbf
for AX301 flash.

Pattern: words[i] = i & 0x1FF (address-echo) for i in 0..511.
After flash, reading address `a` should return `a` on dout bus.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from m9k_init_basis import M9K_INIT_ANCHORS, write_init, read_init
from bitstream import patch_rbf_crc

ROOT = HERE.parent
BASE = ROOT / "results" / "rbf" / "m9k_wp_base.rbf"
OUT  = ROOT / "results" / "rbf" / "m9k_hero.rbf"

anchor, bp = M9K_INIT_ANCHORS[("X15_Y2_N0", 9, 512)]
base_bytes = BASE.read_bytes()
print(f"loaded base {BASE} ({len(base_bytes)} bytes)")

target_words = [i & 0x1FF for i in range(512)]
base_words   = [0] * 512

modified = write_init(base_bytes, anchor, base_words, target_words,
                      width=9, depth=512)
patched  = patch_rbf_crc(modified)
OUT.write_bytes(patched)
print(f"wrote {OUT} ({len(patched)} bytes)")

# Self-check: read back via codec and confirm address-echo.
readback = read_init(patched, anchor, width=9, depth=512)
mismatches = [(i, tw, rv) for i, (tw, rv) in
              enumerate(zip(target_words, readback)) if tw != rv]
if mismatches:
    print(f"FAIL: {len(mismatches)} word mismatches, first 5: "
          f"{mismatches[:5]}")
    sys.exit(1)
print(f"OK: codec round-trip 512/512 words match address-echo pattern")
print(f"\nflash cmd:")
print(f"  openFPGALoader -c usb-blaster {OUT}")
