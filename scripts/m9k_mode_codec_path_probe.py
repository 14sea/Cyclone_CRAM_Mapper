# SPDX-License-Identifier: GPL-3.0-or-later
"""Codec-path silicon probe: SDP X15_Y16_N0.

Question: does np2fasm's M9K_MODE bucket emission (XOR onto nv_zero_global)
configure live silicon at a non-calibration site, given the bucket was
mined against a different baseline (matched_baseline-no-M9K)?

Method: take the Quartus gold blink RBF (proven to blink), patch every
bucket cell to the value the codec would have produced if emitting onto
nv_zero_global (target_bit = nv_zero_global[off][bp] XOR 1, since the
bucket bit flips zero's bit), recompute CRC, flash.

  PASS  → codec emission path is silicon-functional at this site.
  FAIL  → bucket-vs-baseline mismatch breaks silicon; production np2fasm
          path needs a baseline reconciliation step.
"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))
from bitstream import patch_rbf_crc

ZERO = ROOT / "results/rbf/nv_zero_global.rbf"
GOLD = ROOT / "tmp/m9k_sdp_blink_4x2048_X15_Y16_N0/m9k_sdp_blink_4x2048_X15_Y16_N0.rbf"
JSON = ROOT / "results/m9k_mode_bits.json"
OUT = ROOT / "tmp/codec_path_probe_sdp_X15_Y16.rbf"

zero = ZERO.read_bytes()
gold = GOLD.read_bytes()
bucket = json.loads(JSON.read_text())["X15_Y16_N0_4x2048"]["cells_by_template"]["quartus_gold_sdp"]

patched = bytearray(gold)
flips = 0
for off, bp in bucket:
    target = ((zero[off] >> bp) & 1) ^ 1
    cur = (patched[off] >> bp) & 1
    if target != cur:
        patched[off] ^= (1 << bp)
        flips += 1
print(f"bucket size = {len(bucket)} cells")
print(f"bytes flipped relative to gold = {flips}")
patch_rbf_crc(patched)
OUT.write_bytes(bytes(patched))
print(f"-> {OUT}")
