#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pip-conditioned column-relative voting miner for CRC-dead route classes.

Recovers driver-MUX cell offsets for the classes whose legacy write tables
were 100% CRC-junk (C4 I!=0, R24, C16 — see STEP 0 coverage gate) WITHOUT
any new Quartus compile, by voting over the NEORV32 gold bitstream.

Method (validated 2026-07-06):
  1. XOR(neorv32_demo.rbf, nv_zero_global.rbf) -> CRAM cell set
     (off >= 5282, CRC bytes excluded).
  2. Parse a 40k-path STA -show_routing census into per-path wire
     SEQUENCES; a pip = (prev_wire -> wire).  Conditioning on the pip is
     load-bearing: MUX config is DRIVER-conditioned, not wire-conditioned
     (per-wire voting fails calibration; this is also why the 2026-05-31
     Method-2 single-design recovery saturated).
  3. Pool instances column-relatively: candidate cell = COLUMN_BASE[x] +
     R + 3*group, bit = universal Y-address bp.  Pooling across all X
     multiplies Y-diversity (the corpus blocker for per-X fitting).
  4. Discriminated score: positive coverage over the pip-class instances
     AND negative rate over same-slot other-I wire instances.  The
     negative term rejects "LAB activity" confounds that score 100%
     positive (e.g. slot2 R=1653).

Calibration gate (must pass before trusting an unknown class): C4 I=0 <-
LE_BUFFER dx=0 must recover the production formula R = 1519 + _C4_SLOT_BASE
(slot2 R=3857 pos .86 / neg .035; slot1 R=3993(+-1) pos .83 / neg .125;
companion cells at +419/+630 = same byte 2/3 frames over).

Cross-validation (independent data): the 982-route green-zone corpus
(bitdb routing_paths + bit_mapping pip attribution) yields the SAME R for
C4 I=1 <- LE_BUFFER slot=2: corpus x=16 base 184224 and x=25 base 249114
== CB[x]+4062; this scan: R=4062 (pos 1.00 / neg .041).

Prereqs (regenerate if /tmp cleared; ~2.5 min):
  cd ~/see_neorv32_run_linux/quartus && quartus_sta -t <(cat <<'TCL'
  project_open neorv32_demo -revision neorv32_demo
  create_timing_netlist
  catch {read_sdc}
  update_timing_netlist
  report_timing -setup -npaths 20000 -detail full_path -show_routing \
      -file /tmp/step0b_sta_setup20k.rpt
  report_timing -hold -npaths 20000 -detail full_path -show_routing \
      -file /tmp/step0b_sta_hold20k.rpt
  project_close
  TCL
  )

Output: results/c4_inz_pip_voting_candidates.json

Scope caveats (honest): software-only, no silicon; candidates are 1-2
cells of a possibly wider multi-cell MUX pattern; pos<1.0 residuals
unexplained (edge/X33 column quirks untested); NOT yet a write path.
"""
import sys, os, re, json, collections

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, 'fuzz'))
import bitstream, config  # noqa: E402

CB = config.COLUMN_BASE
SB = bitstream._C4_SLOT_BASE
GOLD = os.path.expanduser('~/see_neorv32_run_linux/output/neorv32_demo.rbf')
ZERO = os.path.join(REPO, 'results/rbf/nv_zero_global.rbf')
STA = ['/tmp/step0b_sta_setup20k.rpt', '/tmp/step0b_sta_hold20k.rpt']
OUT = os.path.join(REPO, 'results/c4_inz_pip_voting_candidates.json')

WSEQ = re.compile(r'\b((?:C4|R24|C16|R4|LOCAL_INTERCONNECT|LE_BUFFER|LOCAL_LINE'
                  r'|BLOCK_INPUT_MUX)_X\d+_Y\d+_N\d+(?:_I\d+)?)\b')
WPARSE = re.compile(r'(\w+?)_X(\d+)_Y(\d+)_N(\d+)(?:_I(\d+))?$')


def yaddr(y):
    cr = y - 2
    g, s = cr // 3, cr % 3
    return g, s, (6 - g) if s == 2 else (7 - g)


def xor_cells():
    gold = open(GOLD, 'rb').read()
    zero = open(ZERO, 'rb').read()
    assert len(gold) == len(zero) == 368011
    cells = set()
    for off in range(5282, 367952):
        if (off - 32) % 210 >= 208:
            continue
        d = gold[off] ^ zero[off]
        for bp in range(8):
            if d >> bp & 1:
                cells.add((off, bp))
    return cells


def parse_pips():
    pips = set()
    for fn in STA:
        if not os.path.exists(fn):
            sys.exit(f"missing {fn} — regenerate the 40k STA census (see docstring)")
        cur = []
        with open(fn, errors='replace') as f:
            for line in f:
                if 'Path #' in line:
                    pips.update(zip(cur, cur[1:]))
                    cur = []
                for m in WSEQ.finditer(line):
                    w = m.group(1)
                    if not cur or cur[-1] != w:
                        cur.append(w)
        pips.update(zip(cur, cur[1:]))
    return pips


def build_instances(pips):
    """(t, I, src_t, dx, slot) -> {(x, group, bp)}; plus per-(t,I,slot) wire sets."""
    inst, winst = collections.defaultdict(set), collections.defaultdict(set)
    for a, b in pips:
        ma, mb = WPARSE.match(a), WPARSE.match(b)
        tb, xb, yb = mb.group(1), int(mb.group(2)), int(mb.group(3))
        ib = int(mb.group(5)) if mb.group(5) else None
        if tb not in ('C4', 'R24', 'C16') or xb not in CB or not 2 <= yb <= 21:
            continue
        ta, xa = ma.group(1), int(ma.group(2))
        g, s, bp = yaddr(yb)
        inst[(tb, ib, ta, xa - xb, s)].add((xb, g, bp))
        winst[(tb, ib, s)].add((xb, g, bp))
    return inst, winst


def discriminated(cells, inst, winst, key, pos_min=0.84, neg_max=0.08, min_n=7):
    t, i, pt, dx, s = key
    pos = inst.get(key, set())
    if len(pos) < min_n:
        return None
    neg = set()
    for (tt, ii, ss), ws in winst.items():
        if tt == t and ss == s and ii != i:
            neg |= ws
    neg -= pos
    out = []
    for R in range(-7350, 14700):
        ph = sum(1 for x, g, bp in pos if (CB[x] + R + 3 * g, bp) in cells)
        if ph / len(pos) < pos_min:
            continue
        nh = sum(1 for x, g, bp in neg if (CB[x] + R + 3 * g, bp) in cells)
        if nh / max(1, len(neg)) <= neg_max:
            out.append((R, round(ph / len(pos), 3), round(nh / max(1, len(neg)), 3)))
    return len(pos), len(neg), out


def main():
    cells = xor_cells()
    print(f"XOR CRAM cells: {len(cells)}")
    inst, winst = build_instances(parse_pips())

    # --- calibration gate: C4 I=0 <- LE_BUFFER dx=0 must recover 1519+SB ---
    ok = 0
    for s in (1, 2):  # slot0 has too few instances in this gold to gate on
        r = discriminated(cells, inst, winst, ('C4', 0, 'LE_BUFFER', 0, s),
                          pos_min=0.80, neg_max=0.15, min_n=6)
        if not r:
            continue
        true_r = 1519 + SB[s]
        if any(abs(R - true_r) <= 1 for R, _, _ in r[2]):
            ok += 1
            print(f"calibration slot {s}: true R={true_r} recovered OK")
    if ok < 2:
        sys.exit("CALIBRATION FAILED — do not trust unknown-class output")

    # --- production scan: C4 I!=0 ---
    results = {}
    for k in sorted((k for k in inst if k[0] == 'C4' and k[1] != 0
                     and len(inst[k]) >= 7), key=lambda k: -len(inst[k])):
        r = discriminated(cells, inst, winst, k)
        if r and r[2]:
            t, i, pt, dx, s = k
            results[f"C4,I={i},src={pt},dx={dx},slot={s}"] = {
                'pos_n': r[0], 'neg_n': r[1], 'candidates': r[2]}
            print(f"C4 I={i} <- {pt} dx={dx} slot={s}: pos={r[0]} " +
                  ", ".join(f"R={R}({p}/{q})" for R, p, q in r[2][:5]))
    with open(OUT, 'w') as f:
        json.dump({'method': 'pip-conditioned column-relative discriminated voting',
                   'model': 'cell = (COLUMN_BASE[x] + R + 3*group, bp(y)); universal Y-address',
                   'calibration': 'C4 I=0 <- LE_BUFFER dx=0 slots 1+2 recovered 1519+_C4_SLOT_BASE',
                   'classes': results}, f, indent=1)
    print(f"\n{len(results)} classes -> {OUT}")


if __name__ == '__main__':
    main()
