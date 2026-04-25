# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure codec-emission probe for SDP X15_Y16_N0.

Build the RBF that np2fasm + fasm2rbf would emit if asked for ONLY:

    X15Y16N0.M9K_MODE_4x2048_quartus_gold_sdp

with `--base nv` (i.e., base_rbf = nv_zero_global).  Result =
nv_zero_global with the NEW 21-cell bucket XOR'd, CRC repatched.

  * If it flashes without silicon reset → codec emission is
    silicon-compatible (the 21 bucket cells form a valid
    M9K-MODE-on-at-X15_Y16_N0 configuration on top of zero baseline).
  * If it resets → bucket polarity / cell-set is still wrong and the
    fix is incomplete.
"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))
from bitstream import patch_rbf_crc

zero = (ROOT / "results/rbf/nv_zero_global.rbf").read_bytes()
bucket = json.loads((ROOT / "results/m9k_mode_bits.json").read_text())[
    "X15_Y16_N0_4x2048"]["cells_by_template"]["quartus_gold_sdp"]

emit = bytearray(zero)
for off, bp in bucket:
    emit[off] ^= (1 << bp)
patch_rbf_crc(emit)
out = ROOT / "tmp/codec_emission_pure_sdp_X15_Y16.rbf"
out.write_bytes(bytes(emit))
print(f"bucket = {len(bucket)} cells; wrote {out}")
