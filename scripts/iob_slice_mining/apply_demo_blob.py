# SPDX-License-Identifier: GPL-3.0-or-later
"""Apply a demo-only IOB<->SLICE byte-level patch blob to an RBF.

This is a post-processing escape-hatch for the Phase 5.3 HW-flash
demo while absolute IOB<->SLICE sig-cache entries are being mined.
The blob is `golden.rbf XOR open_toolchain_output.rbf` captured once
per specific (design, LE placement, pin map) tuple. It is NOT
generalizable — a different pin or LE needs its own blob.

After XOR application, CRC is recomputed by bitstream.patch_rbf_crc.

Usage:
    python3 apply_demo_blob.py <input_rbf> <blob_json> <output_rbf>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "fuzz"))

from bitstream import patch_rbf_crc  # noqa: E402


def apply_blob(rbf: bytes, delta: list[list[int]]) -> bytes:
    buf = bytearray(rbf)
    for off, xor_byte in delta:
        buf[off] ^= xor_byte
    return bytes(buf)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input_rbf")
    ap.add_argument("blob_json")
    ap.add_argument("output_rbf")
    ap.add_argument("--no-crc-patch", action="store_true",
                    help="Skip CRC recomputation (debugging only)")
    args = ap.parse_args()

    rbf = Path(args.input_rbf).read_bytes()
    blob = json.loads(Path(args.blob_json).read_text())
    print(f"[blob] {blob.get('description', '')[:80]}...")
    print(f"[blob] {len(blob['delta'])} byte patches")

    patched = apply_blob(rbf, blob["delta"])
    if not args.no_crc_patch:
        patched = patch_rbf_crc(patched)

    Path(args.output_rbf).write_bytes(patched)
    print(f"[ok ] wrote {args.output_rbf} ({len(patched)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
