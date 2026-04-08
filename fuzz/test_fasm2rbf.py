# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 4 regression: FASM round-trip against the green zone.

For each mined fingerprint island, pick one route that green_zone_harden
is known to synth bit-perfect, express it as FASM, run fasm2rbf.bitgen,
and compare the routing cells against Quartus's own RBF. Expect zero
diff in CRAM cells.
"""
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from bitstream import RouteCodec
from fasm2rbf import bitgen
from route_synth import _load_fp

ROOT = Path(HERE).parent
RBF = ROOT / "results" / "rbf"


def cells(codec, rbf, zero):
    sw = codec.read_switches(rbf, zero)
    return {(t, e[1], e[2]) for t, lst in sw.items() for e in lst}


def one_island(codec, sx, sy):
    snap = _load_fp(sx, sy)
    if snap is None or not snap["per_route_delta"]:
        return None
    zpath = RBF / f"lits_zero_{sx}_{sy}.rbf"
    if not zpath.exists():
        return None
    zero = zpath.read_bytes()

    # Pick the first route that has a Quartus baseline on disk.
    for key in sorted(snap["per_route_delta"]):
        dx, dy, port = key.split(",")
        dx, dy = int(dx), int(dy)
        qpath = RBF / f"lits_pair_X{sx}Y{sy}_to_X{dx}Y{dy}N0_{port}.rbf"
        if not qpath.exists():
            continue
        fasm = f"ROUTE X{sx}Y{sy} -> X{dx}Y{dy}N0.{port}\n"
        synth = bitgen(fasm, zero, patch_crc=False)
        quartus = qpath.read_bytes()
        qcells = cells(codec, quartus, zero)
        scells = cells(codec, synth, zero)
        diff_q = qcells - scells
        diff_s = scells - qcells
        return (sx, sy, dx, dy, port, len(qcells), len(diff_q), len(diff_s))
    return None


def main():
    codec = RouteCodec()
    results_dir = ROOT / "results"
    islands = []
    for p in sorted(results_dir.glob("fingerprint_*.json")):
        stem = p.stem  # fingerprint_SX_SY
        parts = stem.split("_")
        if len(parts) != 3:
            continue
        try:
            sx, sy = int(parts[1]), int(parts[2])
        except ValueError:
            continue
        islands.append((sx, sy))

    ok = fail = skip = 0
    for sx, sy in islands:
        r = one_island(codec, sx, sy)
        if r is None:
            print(f"  ({sx:2d},{sy:2d}) SKIP (no route/baseline)")
            skip += 1
            continue
        _, _, dx, dy, port, ncells, dq, ds = r
        tag = "OK  " if dq == 0 and ds == 0 else "FAIL"
        if dq == 0 and ds == 0:
            ok += 1
        else:
            fail += 1
        print(
            f"  ({sx:2d},{sy:2d}) -> ({dx:2d},{dy:2d}).{port:<6s}  "
            f"cells={ncells:3d}  only_q={dq}  only_s={ds}  {tag}"
        )

    print(f"\n{ok} ok / {fail} fail / {skip} skip out of {len(islands)} islands")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
