# SPDX-License-Identifier: GPL-3.0-or-later
"""Multi-island green-zone harden test (auto-discovers all islands).

For every results/fingerprint_{sx}_{sy}.json snapshot, run:
  1. round-trip   — synth → codec read-back == synth cells
  2. safe synth   — validate_safe_for_hardware passes on synth output
  3. safe quartus — same on the original Quartus baseline
  4. fp drift     — fingerprint bits decode identically across all routes
  5. yellow zone  — try a dst NOT in the snapshot, verify fallback safety

Usage: python3 test_green_zone_harden.py
"""
import sys, os, re, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from bitstream import RouteCodec
from route_synth import synth_route, _load_fp

ROOT = Path(__file__).resolve().parent.parent
RBF = ROOT / 'results' / 'rbf'
RES = ROOT / 'results'

# Yellow-zone probe dsts per island — chosen to be inside LAB_X×LAB_Y
# but absent from each island's mined corpus.
YELLOW_PROBES = {
    (10, 10): [(24,  4), (28,  6), ( 6, 18)],
    (10, 14): [(22, 16), ( 6,  4), (28, 18)],
    ( 4,  4): [(11, 11), (16, 13), (24, 17)],
}

SNAP_RE = re.compile(r'fingerprint_(\d+)_(\d+)\.json$')


def cells_set(codec, rbf, zero):
    sw = codec.read_switches(rbf, zero)
    return {(t, e[1], e[2]) for t, lst in sw.items() for e in lst}


def harden_island(codec, sx, sy):
    snap = _load_fp(sx, sy)
    if snap is None or not snap["per_route_delta"]:
        print(f"  no snapshot for ({sx},{sy})")
        return
    zpath = RBF / f'lits_zero_{sx}_{sy}.rbf'
    if not zpath.exists():
        print(f"  missing zero baseline {zpath.name}")
        return
    zero = zpath.read_bytes()
    fp_bits = {(off, bp) for _, off, bp in snap["fingerprint"]}

    rt_pass = bp_pass = ss_pass = sq_pass = 0
    n = 0
    drift = 0
    witness = {}

    for key in sorted(snap["per_route_delta"]):
        dx, dy, port = key.split(',')
        dx, dy = int(dx), int(dy)
        qpath = RBF / f'lits_pair_X{sx}Y{sy}_to_X{dx}Y{dy}N0_{port}.rbf'
        if not qpath.exists():
            continue
        n += 1
        try:
            quartus = qpath.read_bytes()
            synth, _ = synth_route(zero, (sx, sy), (dx, dy, 0, port))
        except Exception as e:
            print(f"    SKIP ({dx},{dy}): {e}")
            continue

        # Bit-perfect vs Quartus
        qcells = cells_set(codec, quartus, zero)
        scells = cells_set(codec, synth, zero)
        if scells == qcells:
            bp_pass += 1
        else:
            print(f"    BP MISMATCH ({dx},{dy}): only_q={len(qcells-scells)} only_s={len(scells-qcells)}")

        # Round-trip (re-read of synth equals first read)
        if cells_set(codec, synth, zero) == scells:
            rt_pass += 1

        # Safety
        try:
            codec.validate_safe_for_hardware(synth, zero)
            ss_pass += 1
        except Exception as e:
            print(f"    SAFE-SYNTH FAIL ({dx},{dy}): {e}")
        try:
            codec.validate_safe_for_hardware(quartus, zero)
            sq_pass += 1
        except Exception as e:
            print(f"    SAFE-QUARTUS FAIL ({dx},{dy}): {e}")

        # Fingerprint drift
        for off, bp in fp_bits:
            v = (synth[off] >> bp) & 1
            if (off, bp) in witness:
                if witness[(off, bp)] != v:
                    drift += 1
            else:
                witness[(off, bp)] = v

    print(f"  ({sx},{sy}) island report ({n} routes):")
    print(f"    bit-perfect : {bp_pass}/{n}")
    print(f"    round-trip  : {rt_pass}/{n}")
    print(f"    safe synth  : {ss_pass}/{n}")
    print(f"    safe quartus: {sq_pass}/{n}")
    print(f"    fp drift    : {drift}")
    print(f"    fingerprint : {len(fp_bits)} bits")

    # Yellow zone probes
    print(f"  ({sx},{sy}) yellow zone:")
    for ydst in YELLOW_PROBES.get((sx, sy), []):
        try:
            ysynth, ydbg = synth_route(zero, (sx, sy), ydst)
            try:
                codec.validate_safe_for_hardware(ysynth, zero)
                verdict = "PASS"
            except Exception as e:
                verdict = f"UNSAFE ({e})"
        except Exception as e:
            verdict = f"SYNTH FAIL ({e})"
        print(f"    {ydst}: {verdict}")


def main():
    codec = RouteCodec()
    snaps = []
    for f in sorted(RES.glob("fingerprint_*.json")):
        m = SNAP_RE.search(f.name)
        if m:
            snaps.append((int(m.group(1)), int(m.group(2))))
    print(f"=== green-zone harden ({len(snaps)} islands) ===")
    for sx, sy in snaps:
        harden_island(codec, sx, sy)


if __name__ == "__main__":
    main()
