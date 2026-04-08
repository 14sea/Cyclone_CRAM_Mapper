# SPDX-License-Identifier: GPL-3.0-or-later
"""Full Phase 4 round-trip: rbf → fasm → rbf for every lits_pair RBF.

For each mined island + each of its route RBFs, dump with rbf2fasm, rebuild
with fasm2rbf against the same zero baseline, and compare CRAM bytes (CRC
trailers excluded). Expect 0 diffs.
"""
import os
import re
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from bitstream import (
    CRC_PREAMBLE,
    CRC_FRAME_SIZE,
    CRC_DATA_SIZE,
    CRC_FIRST_CRAM_FRAME,
    CRC_LAST_FRAME,
)
from fasm2rbf import bitgen
from rbf2fasm import emit

ROOT = Path(HERE).parent
RBF = ROOT / "results" / "rbf"

NAME_RE = re.compile(r"lits_pair_X(\d+)Y(\d+)_to_X(\d+)Y(\d+)N(\d+)_(\w+)\.rbf$")


def cram_bytes(rbf):
    """Concatenate all CRAM data bytes (no header, no CRC trailers)."""
    out = bytearray()
    for n in range(CRC_FIRST_CRAM_FRAME, CRC_LAST_FRAME + 1):
        s = CRC_PREAMBLE + n * CRC_FRAME_SIZE
        out += rbf[s:s + CRC_DATA_SIZE]
    return bytes(out)


def main():
    islands = {}
    for p in RBF.glob("lits_pair_*.rbf"):
        m = NAME_RE.match(p.name)
        if not m:
            continue
        sx, sy = int(m[1]), int(m[2])
        islands.setdefault((sx, sy), []).append(p)

    total = ok = fail = skip = 0
    per_island = {}
    for (sx, sy), rbfs in sorted(islands.items()):
        zpath = RBF / f"lits_zero_{sx}_{sy}.rbf"
        if not zpath.exists():
            skip += len(rbfs)
            continue
        zero = zpath.read_bytes()
        i_ok = i_fail = 0
        for p in sorted(rbfs):
            total += 1
            target = p.read_bytes()
            fasm = emit(target, zero)
            try:
                reconstructed = bitgen(fasm, zero, patch_crc=False)
            except Exception as e:
                fail += 1
                i_fail += 1
                print(f"  FAIL parse ({sx},{sy}) {p.name}: {e}")
                continue
            if cram_bytes(reconstructed) == cram_bytes(target):
                ok += 1
                i_ok += 1
            else:
                fail += 1
                i_fail += 1
                diff = sum(
                    a != b
                    for a, b in zip(
                        cram_bytes(reconstructed), cram_bytes(target)
                    )
                )
                print(f"  DIFF ({sx},{sy}) {p.name}: {diff} bytes")
        per_island[(sx, sy)] = (i_ok, i_fail)

    for k in sorted(per_island):
        io, ifl = per_island[k]
        tag = "OK" if ifl == 0 else "FAIL"
        print(f"  ({k[0]:2d},{k[1]:2d})  {io:3d}/{io+ifl:3d}  {tag}")
    print(f"\n{ok} ok / {fail} fail / {skip} skip out of {total + skip} rbfs")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
