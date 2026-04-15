# SPDX-License-Identifier: GPL-3.0-or-later
"""Programmatic all-zero RBF baseline for EP4CE6F17C8.

Phase 1 of the `nv_zero_global.rbf` retirement plan (see
`/tmp/bidir_mine/nv_zero_global_retirement_plan.md`).

`make_pure_zero_rbf()` returns a 368011-byte RBF whose configuration
payload is entirely zero:

  * 32-byte 0xFF preamble  (unchanged from any CE6 bitstream)
  * 1752 frames × 210 bytes of zeros (0..24 header + 25..1751 CRAM)
  * 59-byte 0xFF postamble (unchanged)
  * Frames 25..1751 have CRC-16/IBM patched by ``patch_rbf_crc``
    (frames 0..24 are header — CRC-less by construction).

This is the "most empty" well-formed RBF this toolchain can produce
without running Quartus.  It is *not* claimed to be HW-loadable on its
own: Cyclone IV's configuration engine likely requires non-zero header
frames carrying device-ID / decompression-disable / clock-source config.
Those bytes live in ``nv_zero_global`` and will be re-expressed as an
additive FASM directive pack (``NV_BASELINE_PACK``) in Phase 3 so that
``PURE_ZERO ^ NV_BASELINE_PACK == nv_zero_global`` byte-for-byte.

Until that pack exists, use PURE_ZERO strictly as:
  * a reference frame for XOR decomposition math
  * a test-vector for Phase 3 reconstruction checks

Do **not** flash PURE_ZERO to silicon — it almost certainly will not
configure the chip.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bitstream import (
    CRC_FIRST_CRAM_FRAME,
    CRC_FRAME_SIZE,
    CRC_LAST_FRAME,
    CRC_PREAMBLE,
    patch_rbf_crc,
)

RBF_SIZE = 368011
POSTAMBLE = 59
# Sanity: 32 + 1752 * 210 + 59 = 368011
assert CRC_PREAMBLE + (CRC_LAST_FRAME + 1) * CRC_FRAME_SIZE + POSTAMBLE == RBF_SIZE


def make_pure_zero_rbf() -> bytes:
    """Return a 368011-byte pure-zero baseline RBF with valid CRAM CRCs.

    Layout:
      [0 : 32]        = 0xFF preamble
      [32 : 367952]   = 1752 frames × 210 bytes of zeros
      [367952 : 368011] = 0xFF postamble (59 bytes)
    Then ``patch_rbf_crc`` fills the 2 CRC bytes at the tail of each
    CRAM frame (25..1751).  Header frames (0..24) keep their zero CRC
    slots untouched — the RBF loader does not validate those.

    The CRC of an all-zero 208-byte frame under this polynomial+init is
    a fixed 16-bit constant (determinism follows from ``crc16_rbf_frame``);
    every CRAM frame in the output therefore carries that same value.
    """
    buf = bytearray(RBF_SIZE)
    # Preamble 32B 0xFF
    for i in range(CRC_PREAMBLE):
        buf[i] = 0xFF
    # Postamble 59B 0xFF
    for i in range(RBF_SIZE - POSTAMBLE, RBF_SIZE):
        buf[i] = 0xFF
    # Frames 32..367952 already zero by bytearray() init
    return patch_rbf_crc(bytes(buf))


if __name__ == "__main__":
    rbf = make_pure_zero_rbf()
    assert len(rbf) == RBF_SIZE
    # Round-trip patch: re-patching is idempotent
    assert patch_rbf_crc(rbf) == rbf
    # Spot-check: CRAM frame 25 carries the all-zero-data CRC
    from bitstream import crc16_rbf_frame, CRC_DATA_SIZE
    s = CRC_PREAMBLE + CRC_FIRST_CRAM_FRAME * CRC_FRAME_SIZE
    assert rbf[s:s + CRC_DATA_SIZE] == bytes(CRC_DATA_SIZE)
    expected_crc = crc16_rbf_frame(bytes(CRC_DATA_SIZE))
    got_crc = rbf[s + CRC_DATA_SIZE] | (rbf[s + CRC_DATA_SIZE + 1] << 8)
    assert got_crc == expected_crc, f"CRAM frame 25 CRC {got_crc:#06x} != {expected_crc:#06x}"
    print(f"PURE_ZERO OK: {len(rbf)} bytes, all-zero-frame CRC = {expected_crc:#06x}")
