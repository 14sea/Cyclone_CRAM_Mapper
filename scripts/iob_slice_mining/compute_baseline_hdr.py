# SPDX-License-Identifier: GPL-3.0-or-later
"""Extract the header-band bit cells of nv_zero_global ^ iob_in_E15.

Those cells form the `IOB_BASELINE_NV` FASM directive: applying them
on top of nv_zero_global produces the iob_in_E15 header-band config
(pin E15 as K input + pin G15 as LED output) without touching CRAM.
This bridges the frame gap between IOB_IN/IOB_OUT (iob_in_E15 frame)
and IOB_ROUTE (nv_zero_global frame) so both families can be composed
on a single nv_zero_global base.

Algebra (verified in baseline_frame_probe.py):
  nv_zero_global ^ iob_in_E15 = 74 hdr bytes + 212 CRAM bytes
  The 74 hdr bytes = baseline IOB bank config (E15/G15).
  The 212 CRAM bytes = iob_in_E15's test design fabric (NOT wanted).

We scope the emitted cells to header band only (off < 5282).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

PRE = 32
FRAME = 210
FIRST = 25
CRAM_START = PRE + FIRST * FRAME  # 5282


def main() -> int:
    nv = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()
    iob_in_E15 = (REPO / "results" / "rbf" / "iob_in_E15.rbf").read_bytes()
    assert len(nv) == len(iob_in_E15)

    cells: list[tuple[int, int]] = []
    n_bytes_touched = 0
    for off in range(CRAM_START):
        x = nv[off] ^ iob_in_E15[off]
        if x == 0:
            continue
        n_bytes_touched += 1
        for bp in range(8):
            if x & (1 << bp):
                cells.append((off, bp))

    out = {
        "meta": {
            "source": "nv_zero_global.rbf ^ iob_in_E15.rbf, header "
                      "band only (off < 5282)",
            "frame": "nv_zero_global",
            "scope": "header_band",
            "bytes_touched": n_bytes_touched,
            "cells": len(cells),
        },
        "cells": sorted(cells),
    }
    out_path = REPO / "results" / "iob_baseline_hdr_cells.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"[ok] wrote {out_path}  ({n_bytes_touched} bytes, "
          f"{len(cells)} bit cells)")

    # Round-trip self-check: applying cells XOR nv at hdr band equals
    # iob_in_E15 at hdr band.
    buf = bytearray(nv[:CRAM_START])
    for off, bp in cells:
        buf[off] ^= (1 << bp)
    if bytes(buf) == iob_in_E15[:CRAM_START]:
        print("[verified] nv ^ baseline_hdr_cells == iob_in_E15 (hdr band)")
        return 0
    print("[FAIL] round-trip mismatch at hdr band")
    return 1


if __name__ == "__main__":
    sys.exit(main())
