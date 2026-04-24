# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression test for the σ⁻¹ 3-key (foff, fb8, group) lookup.

Covers two invariants:

1. **Write-then-read round-trip.** For a set of (x, y, n) positions that
   spans every wrap branch exercised by `LutCodec.from_cram_model`
   (non-wrapped, slot=1 group=0 wrap @ addr_adj=206 incl. N=12, slot=1
   group≥1 wrap @ addr_adj=207 strict <), `write_tt(nv, mask)` followed
   by `read_tt(result, nv)` must return the same mask for several
   pseudo-random masks. Catches any codec-side regression in the wrap
   formula or the σ⁻¹ inversion logic — independent of the table
   contents, as long as the table gives a self-consistent permutation.

2. **FACE-probe consistency.** For every cached FACE (mask=0xFACE) probe
   under `tmp/sigma_{existing_groups,fb8_mine,group4}/`, the codec's
   predicted cells for each minterm must match the probe's actual CRAM
   diff. The mask has symmetries — for some positions, multiple σ⁻¹
   give zero error — so the check is "table entry ∈ FACE-consistent
   set", not "table entry == one specific permutation". This catches
   table drift (e.g. σ⁻¹ flipped to a FACE-inconsistent perm, or entry
   deleted) without breaking on HW-driven fixes like X6Y4N0 (which
   pinned σ⁻¹ to a non-FACE-symmetric perm based on AND-gate gold).

Skips when baseline RBF or probe trees are absent.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from itertools import permutations
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "fuzz"))
from bitstream import LutCodec  # noqa: E402
from config import cram_ctrl_addr, cram_ctrl_bit, cram_n_delta  # noqa: E402

FACE = 0xFACE
N_VALS = list(range(0, 32, 2))
PROBE_DIRS = ("sigma_existing_groups", "sigma_fb8_mine", "sigma_group4")
NAME_RE = re.compile(r"face_X(\d+)_Y(\d+)$")

# HW-pinned positions where the 3-key table holds a σ⁻¹ that is NOT
# FACE-probe-consistent because it was fixed against a stronger ground
# truth (Quartus AND-gate gold at X16Y4N0 on 2026-04-21; siblings
# X6/16/26/28 Y=4 N=0 share the (94,1,0) entry). The FACE mask's
# symmetry admits (1,3,2,0) and (3,1,0,2); the HW-correct answer is
# (1,2,3,0). Do NOT lift this allowlist without re-verifying on silicon.
FACE_HW_OVERRIDE = {(6, 4, 0), (16, 4, 0), (26, 4, 0), (28, 4, 0)}

# Representative (x, y, n) positions covering each wrap branch.
ROUND_TRIP_POSITIONS = [
    # non-wrapped (slot ∈ {0, 2})
    (10, 10, 0), (10, 10, 2), (10, 10, 14), (10, 10, 30),
    (4, 4, 0), (16, 8, 6), (22, 12, 16), (28, 10, 30),
    # slot=1 group=0 wrap (addr_adj=206, includes boundary N=12)
    (3, 3, 0), (3, 3, 10), (3, 3, 12), (3, 3, 14), (3, 3, 30),
    (10, 3, 0), (10, 3, 12), (10, 3, 30),
    # slot=1 group≥1 wrap (addr_adj=207, strict <)
    (6, 6, 0), (6, 6, 14), (6, 6, 16), (6, 6, 30),
    (13, 9, 18), (13, 9, 30),
    (22, 12, 20), (22, 12, 30),
    # Group-4 freshly closed (fb8∈{0,1,3,4})
    (11, 14, 0), (11, 14, 16), (16, 16, 8), (12, 14, 24), (17, 16, 30),
    # HW-pinned (non-FACE-symmetric fix point)
    (6, 4, 0), (16, 4, 0),
]
ROUND_TRIP_MASKS = [0x0000, 0x0001, 0x8000, 0xAAAA, 0xCCCC, 0xFACE,
                    0x1234, 0xABCD, 0xFFFF]


def _face_consistent_sigmas(x, y, n, probe, nv):
    """Enumerate σ⁻¹ permutations that give zero FACE error at (x,y,n).
    Uses the same wrap logic as LutCodec.from_cram_model."""
    slot = (y - 2) % 3
    group = (y - 2) // 3
    nd = cram_n_delta(n)
    if slot == 1 and group == 0:
        wrapped = (24 + nd <= 0)
        bp_w, adj_w = 7 - group, 206
    else:
        wrapped = slot == 1 and (24 + group * 3 + nd < 0)
        bp_w, adj_w = 7 - group, 207
    if wrapped:
        bp, addr_adj = bp_w, adj_w
    else:
        bp = cram_ctrl_bit(y)
        addr_adj = 0
    k = n // 2
    accepted = []
    for si in permutations(range(4)):
        sigma = [0] * 4
        for i, j in enumerate(si):
            sigma[j] = i
        ok = True
        for b in range(16):
            f0 = (b >> sigma[0]) & 1
            f1 = (b >> sigma[1]) & 1
            f2 = (b >> sigma[2]) & 1
            f3 = (b >> sigma[3]) & 1
            pair = ((1 - f0) << 2) | ((1 - f1) << 1) | (1 - f2)
            da = f3 ^ (1 - f2)
            delta = da if k % 2 == 0 else 1 - da
            addr = cram_ctrl_addr(x, y, pair, n) + delta + addr_adj
            diff = ((probe[addr] ^ nv[addr]) >> bp) & 1
            expected = (FACE >> b) & 1
            if diff != expected:
                ok = False
                break
        if ok:
            accepted.append(si)
    return accepted


def _round_trip_check(x, y, n, nv, failures):
    try:
        codec = LutCodec.from_cram_model(x, y, n)
    except Exception as exc:
        failures.append((x, y, n, f"codec construction: {exc}"))
        return False
    ok = True
    for mask in ROUND_TRIP_MASKS:
        rbf = codec.write_tt(nv, mask)
        got = codec.read_tt(rbf, nv)
        if got != mask:
            failures.append((x, y, n, f"round-trip mask=0x{mask:04X}: got 0x{got:04X}"))
            ok = False
    return ok


def _codec_sigma_tuple(codec):
    """Recover the σ⁻¹ tuple the codec is effectively using by inspecting
    its patterns — mirror of the sigma_inv_fb8_groups entry."""
    # patterns[b] has one cell; we can reverse-engineer σ from the
    # (pair, delta) the codec picked for each minterm. But the test
    # itself doesn't need the tuple — passing _face_consistent_sigmas
    # set suffices. Kept for diagnostic reporting.
    return tuple(sorted(next(iter(codec.patterns[b])) for b in range(16))[:2])


def main():
    nv_path = REPO / "results" / "rbf" / "nv_zero_global.rbf"
    if not nv_path.is_file():
        print(f"SKIP: baseline RBF missing ({nv_path})")
        return 0
    nv = nv_path.read_bytes()

    # ---- 1. write/read round-trip across wrap branches ----
    rt_failures = []
    rt_ok = 0
    for (x, y, n) in ROUND_TRIP_POSITIONS:
        if _round_trip_check(x, y, n, nv, rt_failures):
            rt_ok += 1
    print(f"round-trip: {rt_ok}/{len(ROUND_TRIP_POSITIONS)} positions "
          f"× {len(ROUND_TRIP_MASKS)} masks OK")
    for x, y, n, err in rt_failures[:10]:
        print(f"  X{x}Y{y}N{n}: {err}")

    # ---- 2. FACE-consistency (codec cells ∈ zero-err set) ----
    probes = []
    for d in PROBE_DIRS:
        base = REPO / "tmp" / d
        if not base.is_dir():
            continue
        for entry in base.iterdir():
            m = NAME_RE.match(entry.name)
            if not m:
                continue
            rbf = entry / "output_files" / "probe.rbf"
            if rbf.is_file() and rbf.stat().st_size == 368011:
                probes.append((int(m.group(1)), int(m.group(2)), rbf))
    probes.sort()
    if not probes:
        print("SKIP FACE: no cached probes")
        return 0 if not rt_failures else 1

    face_ok = 0
    face_total = 0
    face_failures = []
    by_slice = defaultdict(lambda: [0, 0])
    for (x, y, rbf_path) in probes:
        probe = rbf_path.read_bytes()
        for n in N_VALS:
            if (x, y, n) in FACE_HW_OVERRIDE:
                continue
            face_total += 1
            consistent = _face_consistent_sigmas(x, y, n, probe, nv)
            if not consistent:
                face_failures.append((x, y, n, "no FACE-consistent σ⁻¹ exists"))
                continue
            codec = LutCodec.from_cram_model(x, y, n)
            # Reproduce the codec's own cell layout and check it matches
            # one of the FACE-consistent σ⁻¹ choices.
            slot = (y - 2) % 3
            group = (y - 2) // 3
            nd = cram_n_delta(n)
            if slot == 1 and group == 0:
                wrapped = (24 + nd <= 0)
                bp_w, adj_w = 7 - group, 206
            else:
                wrapped = slot == 1 and (24 + group * 3 + nd < 0)
                bp_w, adj_w = 7 - group, 207
            if wrapped:
                bp, addr_adj = bp_w, adj_w
            else:
                bp = cram_ctrl_bit(y)
                addr_adj = 0
            k = n // 2
            match = False
            for si in consistent:
                sigma = [0] * 4
                for i, j in enumerate(si):
                    sigma[j] = i
                # Build expected cell-per-minterm for this σ⁻¹ and
                # compare to the codec's patterns.
                ok = True
                for b in range(16):
                    f0 = (b >> sigma[0]) & 1
                    f1 = (b >> sigma[1]) & 1
                    f2 = (b >> sigma[2]) & 1
                    f3 = (b >> sigma[3]) & 1
                    pair = ((1 - f0) << 2) | ((1 - f1) << 1) | (1 - f2)
                    da = f3 ^ (1 - f2)
                    delta = da if k % 2 == 0 else 1 - da
                    addr = cram_ctrl_addr(x, y, pair, n) + delta + addr_adj
                    if codec.patterns[b] != {(addr, bp)}:
                        ok = False
                        break
                if ok:
                    match = True
                    break
            if match:
                face_ok += 1
                by_slice[(y, slot, group)][0] += 1
            else:
                face_failures.append((x, y, n,
                                      f"codec σ⁻¹ not in FACE-consistent set "
                                      f"{consistent}"))
                by_slice[(y, slot, group)][1] += 1

    print(f"FACE-consistency: {face_ok}/{face_total} positions OK "
          f"({len(probes)} probes × {len(N_VALS)} N)")
    fails = [(y, s, g) for (y, s, g), c in by_slice.items() if c[1] > 0]
    if fails:
        print("  slices with failures:")
        for (y, s, g) in sorted(fails):
            c = by_slice[(y, s, g)]
            print(f"    Y={y} slot={s} group={g}: {c[0]} OK / {c[1]} FAIL")
    for x, y, n, err in face_failures[:10]:
        print(f"  X{x}Y{y}N{n}: {err}")
    if len(face_failures) > 10:
        print(f"  … and {len(face_failures) - 10} more")

    failed = bool(rt_failures) or bool(face_failures)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
