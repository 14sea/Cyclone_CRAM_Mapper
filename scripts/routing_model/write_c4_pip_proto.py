#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""NON-PRODUCTION write-path prototype for C4 I!=0 pip cells (Step 3).

Turns the read-side pip law (c4_pip_pattern_mine.py + pip_prediction_gate)
into an experimental EMITTER, and gates it byte-for-byte against fresh
Quartus golds that no mining or scoring stage has ever seen.

This is deliberately NOT wired into RouteCodec / fasm2rbf: Pitfall #12
(cross-LAB formula emission is silicon-hostile when wrong) and Pitfall #14
(driver-context dependence) both say a formula write path must clear a
byte-identity gate on unseen golds first.  DO NOT FLASH anything built
from this file.

Emission policy (write whitelist), data-driven from
results/c4_pip_gate_scores.json (merged cross-dataset holdout):
  - family A cells only (family B empty; family C is HOLDOUT-FALSIFIED)
  - class not 'ambiguous_geom' (instances spanned >=2 Y-groups at mining)
  - merged holdout cell_rate >= CELL_RATE_MIN with cell_tot >= CELL_TOT_MIN

Modes:
  python3 write_c4_pip_proto.py build    # ~12 fresh VERTICAL two-LUT
      # Quartus compiles (same column, dy 3..8 -> C4-heavy routes) into
      # tmp/c4_fresh/ (cached; ~15 s each).  Positions chosen to avoid
      # X=4 (Pitfall #16 country) and all tmp/r4_leftward pairs.
  python3 write_c4_pip_proto.py verify   # for each fresh gold:
      # 1. emit cells for every whitelisted C4 I!=0 pip in its STA route
      # 2. XOR-apply onto nv_zero_global and compare the emitted cells
      #    byte-for-byte against the gold (base bytes elsewhere untouched,
      #    so PASS == every emitted bit is set in gold AND no emitted bit
      #    is clear in gold: zero write-side false positives)
      # 3. score the FULL pattern table on the fresh builds as an
      #    evidence table (fresh data is held out from ALL mining), to
      #    justify future whitelist growth — esp. the src=LE_BUFFER dx=0
      #    classes that have no instances in the older holdout sets.

Verdict semantics: per-build PASS means the C4 pip cells this prototype
would write are exactly Quartus's bits at those addresses.  It does NOT
mean the emitted set is COMPLETE (other cells of the route — C4 I=0, LI,
LUT, R4 — are out of scope here), and it is NOT silicon evidence.

=========== FRESH-GATE HISTORY (both runs on the same 12 golds) ==========
Run 1 (2026-07-07 AM, dy-LESS key (I,src,dx,slot)): NOT CLEARED.
  Whitelist (2 classes) never fired (vacuous); full-table evidence 0/22;
  forensic showed same-key-same-geometry pips with DISJOINT cells and
  zero-cell pips.  Verdict: key lacks context dimension(s).
Run 2 (2026-07-07 PM, dy IN KEY after c4_mux_default_probe.py): FIRST
  POSITIVE CLOSURE — whitelist grew to 5 classes; cf_X19Y17_to_X19Y9's
  chain pip C4_X19_Y13_I1 -> C4_X19_Y16_I1 (class I=1,C4,dx=0,dy=-3,
  slot=2, R=4482) emitted 1 cell, byte-identical to the fresh Quartus
  gold: TP=1 FP=0 PASS.  Existence proof for the full loop
  (mine -> cross-dataset holdout -> emit -> unseen-gold byte identity),
  NOT coverage: 11/12 golds had no whitelisted pip, and the downward
  family (dy=+3/+4, I=12/15...) is still 0-for-all (window/anchor open
  question — see MULTI_DEFAULT-at-X33 caveat in the probe memo).
STANDING RULES: R24/R4 write paths stay untouched until C4 coverage is
real; this file stays a gated experiment; nothing here may feed
fasm2rbf/RouteCodec; DO NOT FLASH.
==========================================================================
"""
import sys, os, json, glob, re, shutil, subprocess, collections

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, 'fuzz'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402
import pip_prediction_gate as gate  # noqa: E402

CB = config.COLUMN_BASE
OUTD = os.path.join(REPO, 'tmp', 'c4_fresh')
WORK = os.path.join(OUTD, 'work')
ZERO = os.path.join(REPO, 'results/rbf/nv_zero_global.rbf')
REPORT = os.path.join(REPO, 'results/c4_write_proto_fresh_gate.json')
CELL_RATE_MIN, CELL_TOT_MIN = 0.90, 4
WRE = re.compile(r'\b((?:C4|R24|C16|R4|LOCAL_INTERCONNECT|LE_BUFFER|LOCAL_LINE)'
                 r'_X\d+_Y\d+_N\d+(?:_I\d+)?)\b')
TCL = """project_open {tag}
load_package sta
create_timing_netlist
create_clock -name vclk -period 100 [get_ports CLK]
set_input_delay -clock vclk 0 [get_ports {{A B C D}}]
set_output_delay -clock vclk 0 [get_ports Q]
update_timing_netlist
report_timing -setup -npaths 8 -detail full_path -show_routing -file _route_out.txt
delete_timing_netlist
project_close
"""
# same-column vertical pairs (C4 wires are vertical); green-zone columns,
# X=4 avoided; none of these (src,dst) pairs exists in tmp/r4_leftward
FRESH_PAIRS = [
    (10, 4, 10, 10), (10, 14, 10, 8), (13, 5, 13, 12), (16, 12, 16, 6),
    (16, 4, 16, 11), (19, 17, 19, 9), (22, 8, 22, 14), (25, 16, 25, 10),
    (28, 6, 28, 12), (31, 14, 31, 8), (7, 4, 7, 11), (11, 18, 11, 11),
]


def load_whitelist():
    scores = json.load(open(gate.SCORES_PATH))['merged']
    table, src = gate.load_c4_table()
    wl = {}
    for key, ent in table.items():
        s = scores.get(gate.class_name(key))
        if (s and not ent['ambiguous'] and ent['A']
                and s['cell_rate'] >= CELL_RATE_MIN
                and s['cell_tot'] >= CELL_TOT_MIN):
            wl[key] = ent['A']
    return wl, table


def emit_c4_pips(whitelist, seq):
    """(cells, covered_pips) this prototype would WRITE for a route.

    Family-A law only: off = CB[x] + R + 3*group, bp = Y-address bp of
    the target wire.  Cells are XOR cells over nv_zero_global.
    """
    cells, covered = set(), []
    seen = set()
    wtab = {k: {'A': v, 'B': [], 'C': []} for k, v in whitelist.items()}
    for a, b in zip(seq, seq[1:]):
        p = gate.predict_c4_pip(wtab, a, b)
        if not p or p[1] is None:
            continue
        key, pred = p
        if (key, b) in seen:
            continue
        seen.add((key, b))
        cells.update(pred)
        covered.append((gate.class_name(key), b, sorted(pred)))
    return cells, covered


def apply_cells(base_bytes, cells):
    data = bytearray(base_bytes)
    for off, bp in cells:
        data[off] ^= 1 << bp
    return bytes(data)


def build_one(sx, sy, dx, dy):
    from verilog_gen import gen_two_luts_single_input_clocked
    from plan_d_prime_factory import gen_qsf_ce10
    import compile as qc
    tag = f"cf_X{sx}Y{sy}_to_X{dx}Y{dy}"
    rbf_out = os.path.join(OUTD, tag + '.rbf')
    wires_out = os.path.join(OUTD, tag + '.wires.json')
    if os.path.exists(rbf_out) and os.path.exists(wires_out):
        print(tag, "cached")
        return
    v = gen_two_luts_single_input_clocked(0x8888, 0xAAAA, connect_port='dataa')
    qsf = gen_qsf_ce10({'lut1': f'LCCOMB_X{sx}_Y{sy}_N0',
                        'lut2': f'LCCOMB_X{dx}_Y{dy}_N0'}, seed=1)
    ws = os.path.join(WORK, tag)
    shutil.rmtree(ws, ignore_errors=True)
    rbf, el, err = qc.compile_and_export(tag, v, qsf, rbf_output=rbf_out,
                                         work_dir=WORK)
    if not rbf:
        print(tag, "COMPILE FAIL:", err[:300])
        return
    with open(os.path.join(ws, '_rt.tcl'), 'w') as f:
        f.write(TCL.format(tag=tag))
    subprocess.run([os.path.expanduser(
        '~/intelFPGA_lite/21.1/quartus/bin/quartus_sta'),
        '-t', '_rt.tcl'], cwd=ws, capture_output=True, timeout=120)
    seq = []
    with open(os.path.join(ws, '_route_out.txt'), errors='replace') as f:
        for line in f:
            for m in WRE.finditer(line):
                if not seq or seq[-1] != m.group(1):
                    seq.append(m.group(1))
    json.dump(seq, open(wires_out, 'w'), indent=1)
    c4s = sorted({w for w in seq if w.startswith('C4_')})
    print(f"{tag}: {el:.0f}s C4={c4s}")
    shutil.rmtree(ws, ignore_errors=True)


def fresh_builds():
    out = {}
    for fn in sorted(glob.glob(os.path.join(OUTD, '*.wires.json'))):
        tag = os.path.basename(fn)[:-11]
        rbf = fn.replace('.wires.json', '.rbf')
        if os.path.exists(rbf):
            out[tag] = (json.load(open(fn)), open(rbf, 'rb').read())
    return out
def mode_build():
    os.makedirs(OUTD, exist_ok=True)
    for sx, sy, dx, dy in FRESH_PAIRS:
        build_one(sx, sy, dx, dy)


def mode_verify():
    whitelist, table = load_whitelist()
    print(f"write whitelist ({len(whitelist)} classes, family A, "
          f"cell_rate>={CELL_RATE_MIN}, cell_tot>={CELL_TOT_MIN}):")
    for k, rs in sorted(whitelist.items()):
        print(f"  {gate.class_name(k)}: A={rs}")
    builds = fresh_builds()
    if not builds:
        sys.exit("no fresh builds — run 'build' mode first")
    zero = open(ZERO, 'rb').read()

    # --- leg 1: byte-identity gate at emitted cells ---
    print(f"\n=== byte-identity gate on {len(builds)} FRESH golds ===")
    report = {}
    tp = fp = 0
    for tag, (seq, gold) in sorted(builds.items()):
        cells, covered = emit_c4_pips(whitelist, seq)
        rebuilt = apply_cells(zero, cells)
        bad = [(off, bp) for off, bp in cells
               if (rebuilt[off] ^ gold[off]) >> bp & 1]
        tp += len(cells) - len(bad)
        fp += len(bad)
        verdict = ('PASS' if not bad else 'FAIL') if cells else 'NO-COVERED-PIP'
        report[tag] = {'emitted': len(cells), 'fp': len(bad),
                       'covered_pips': [c[:2] for c in covered],
                       'verdict': verdict}
        print(f"{tag}: emitted={len(cells)} FP={len(bad)} {verdict}"
              + (f"  bad={bad}" if bad else ""))
    print(f"emitted-cell totals: TP={tp} FP={fp}")

    # --- leg 2: full-table evidence on fresh builds (all held out) ---
    acc = gate.C4Acc('fresh')
    for tag, (seq, gold) in builds.items():
        cells = set()
        for off in range(5282, 367952):
            if (off - 32) % 210 >= 208:
                continue
            d = gold[off] ^ zero[off]
            for bp in range(8):
                if d >> bp & 1:
                    cells.add((off, bp))
        acc.score_seq(table, seq, cells)
    acc.report(table, "full-table evidence on fresh builds (whitelist growth)")

    json.dump({'whitelist': {gate.class_name(k): v
                             for k, v in whitelist.items()},
               'criteria': {'cell_rate_min': CELL_RATE_MIN,
                            'cell_tot_min': CELL_TOT_MIN,
                            'families': ['A']},
               'builds': report,
               'evidence': acc.as_dict(table)},
              open(REPORT, 'w'), indent=1)
    print(f"-> {REPORT}")


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'verify'
    {'build': mode_build, 'verify': mode_verify}[mode]()
