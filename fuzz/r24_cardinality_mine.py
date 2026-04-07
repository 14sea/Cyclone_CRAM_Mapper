# SPDX-License-Identifier: GPL-3.0-or-later
"""Mine R24 (wx, y) → fixed-offset cardinality across the RBF corpus.

Walks every routed RBF in results/rbf/ and groups its R24 cells by
(wx, y, i_idx). For each group records which of the candidate fixed
offsets (primary 3124, secondary 2705 for I=0) are flipped. Builds two
distributions:

  1. cardinality(y)  — how many R24 wires at this Y use 1 vs 2 offsets
  2. offset_choice(y) — for the 1-offset case, which one (primary/sec)

Result tells the planner which offset to emit for each Y row.
"""
import sys, os, re, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from collections import defaultdict, Counter
from pathlib import Path

from bitstream import RouteCodec, _R24_FIXED_OFFSETS, COLUMN_BASE
from config import LAB_X

ROOT = Path(__file__).resolve().parent.parent
RBF_DIR = ROOT / "results" / "rbf"

# Pick the right zero baseline for each RBF prefix
ZEROS = {
    "lits_": "lits_zero_10_10.rbf",
    "lit_":  "lit_zero_10_10.rbf",
    "litcol_3_5_":   "litdec_zero_3_5.rbf",
    "litcol_17_8_":  "litdec_zero_17_8.rbf",
    "litcol_25_15_": "litdec_zero_25_15.rbf",
    "litdec_":       None,  # individual baselines, skip
}

R24_NAME_RE = re.compile(r"R24_X(\d+)_Y(\d+)_N0_I(\d+)")


def pick_zero(name):
    for prefix, zname in ZEROS.items():
        if name.startswith(prefix) and zname is not None:
            return zname
    return None


def main():
    codec = RouteCodec()
    zero_cache = {}

    # offset → label for I=0
    pri, sec = _R24_FIXED_OFFSETS[0]   # (3124, 2705)
    label = {pri: "primary(3124)", sec: "secondary(2705)"}

    # (wx, y, i) -> set of relative offsets actually flipped in this RBF
    # We aggregate ACROSS rbfs into y -> Counter(frozenset(rel_offs))
    by_y_card = defaultdict(Counter)        # y -> Counter[cardinality]
    by_y_choice = defaultdict(Counter)      # y -> Counter[which single offset]
    # (y, prev_x) -> Counter[which single offset]  — for wx-conditioned rule
    by_yprev_choice = defaultdict(Counter)
    # (y, wx) -> Counter[which single offset]      — finer (raw wx)
    by_ywx_choice = defaultdict(Counter)
    total_wires = 0
    n_files = 0

    for path in sorted(RBF_DIR.iterdir()):
        if not path.suffix == ".rbf":
            continue
        if "zero" in path.name:
            continue
        zname = pick_zero(path.name)
        if zname is None:
            continue
        zero_path = RBF_DIR / zname
        if not zero_path.exists():
            continue
        if zname not in zero_cache:
            zero_cache[zname] = zero_path.read_bytes()
        zero = zero_cache[zname]

        try:
            data = path.read_bytes()
            cells = codec.read_r24(data, zero)
        except Exception:
            continue
        if not cells:
            continue
        n_files += 1

        # group: (wx, y, i) -> set of (offset, bp) cells
        groups = defaultdict(list)
        for name, off, bp in cells:
            m = R24_NAME_RE.match(name)
            if not m:
                continue
            wx, y, i = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if i != 0:
                continue
            groups[(wx, y)].append((off, bp))

        for (wx, y), gcells in groups.items():
            total_wires += 1
            # Compute relative offsets vs prev_lab col_start
            prev_x = codec._prev_lab_x(wx)
            if prev_x is None or prev_x not in COLUMN_BASE:
                continue
            col_start = COLUMN_BASE[prev_x] - 136
            rel_offs = sorted({off - col_start for off, _ in gcells})
            card = len(rel_offs)
            by_y_card[y][card] += 1
            if card == 1:
                lab = label.get(rel_offs[0], f"unknown({rel_offs[0]})")
                by_y_choice[y][lab] += 1
                by_yprev_choice[(y, prev_x)][lab] += 1
                by_ywx_choice[(y, wx)][lab] += 1

    print(f"scanned {n_files} routed RBFs, {total_wires} (wx,y,I=0) wire-groups\n")
    print(f"primary={pri}  secondary={sec}\n")

    print(f"{'Y':>3} | {'1-cell':>8} {'2-cell':>8} | choice when 1-cell")
    print("-" * 70)
    for y in sorted(by_y_card.keys()):
        c1 = by_y_card[y][1]
        c2 = by_y_card[y][2]
        ch = by_y_choice[y]
        ch_str = "  ".join(f"{k}={v}" for k, v in ch.most_common())
        print(f"{y:>3} | {c1:>8} {c2:>8} | {ch_str}")

    # Verdict per Y
    print("\nVerdict per Y (rule for the planner):")
    rules = {}
    for y in sorted(by_y_card.keys()):
        c1 = by_y_card[y][1]
        c2 = by_y_card[y][2]
        if c2 > c1:
            rules[y] = "BOTH"
        elif by_y_choice[y]:
            top = by_y_choice[y].most_common(1)[0][0]
            rules[y] = f"SINGLE {top}"
        else:
            rules[y] = "?"
        print(f"  Y={y:>2}: {rules[y]}")
    # ---- full (Y, prev_x) matrix across ALL Y blocks ----
    print("\n\n=== full (Y, prev_x) majority matrix (single-cell wires) ===")
    all_prev = sorted({px for (_, px) in by_yprev_choice})
    all_y = sorted({y for (y, _) in by_yprev_choice})
    header = "  Y |" + "".join(f"{px:>5}" for px in all_prev)
    print(header)
    print("-" * len(header))
    for y in all_y:
        row = f"{y:>3} |"
        for px in all_prev:
            ctr = by_yprev_choice.get((y, px))
            if not ctr:
                row += "    ."
                continue
            p = ctr.get("primary(3124)", 0)
            s = ctr.get("secondary(2705)", 0)
            tot = p + s
            if tot == 0:
                row += "    ."
            elif p == s:
                row += f"  ={tot:>2}"
            elif p > s:
                row += f"  P{int(round(p*10/tot)):>1}"  # P0..P9 strength
            else:
                row += f"  S{int(round(s*10/tot)):>1}"
        print(row)

    # Per-prev_x verdict aggregated across ALL Y
    print("\n=== per-prev_x verdict (all Y combined, single-cell only) ===")
    print(f"{'prev_x':>7} {'pri':>6} {'sec':>6}  verdict   stability")
    print("-" * 60)
    by_prev = defaultdict(lambda: [0, 0])
    by_prev_y_winners = defaultdict(set)  # which winners seen across Y
    for (y, px), ctr in by_yprev_choice.items():
        p = ctr.get("primary(3124)", 0)
        s = ctr.get("secondary(2705)", 0)
        by_prev[px][0] += p
        by_prev[px][1] += s
        if p > s: by_prev_y_winners[px].add("PRI")
        elif s > p: by_prev_y_winners[px].add("SEC")
    for px in sorted(by_prev):
        p, s = by_prev[px]
        tot = p + s
        verdict = "PRI" if p > s else ("SEC" if s > p else "tie")
        pct = max(p, s) * 100 / tot if tot else 0
        winners = by_prev_y_winners[px]
        stability = "stable" if len(winners) <= 1 else f"flips:{winners}"
        print(f"{px:>7} {p:>6} {s:>6}  {verdict:>3} ({pct:>3.0f}%)  {stability}")

    # ---- wx-conditioned breakdown for the ambiguous Y=10/11/12 block ----
    print("\n\n=== wx-conditioned breakdown (Y=10/11/12, single-cell wires) ===")
    print("by prev_lab_x:")
    print(f"{'Y':>3} {'prev_x':>7} | {'pri':>6} {'sec':>6}  verdict")
    print("-" * 60)
    prev_xs = sorted({px for (y, px) in by_yprev_choice if y in (10, 11, 12)})
    for y in (10, 11, 12):
        for px in prev_xs:
            ctr = by_yprev_choice.get((y, px))
            if not ctr:
                continue
            p = ctr.get("primary(3124)", 0)
            s = ctr.get("secondary(2705)", 0)
            tot = p + s
            verdict = "PRI" if p > s else ("SEC" if s > p else "tie")
            pct = max(p, s) * 100 / tot if tot else 0
            print(f"{y:>3} {px:>7} | {p:>6} {s:>6}  {verdict} ({pct:.0f}%)")

    # Even/odd test on prev_x
    print("\nparity test on prev_x (Y=10/11/12 combined):")
    even_p = even_s = odd_p = odd_s = 0
    for (y, px), ctr in by_yprev_choice.items():
        if y not in (10, 11, 12):
            continue
        p = ctr.get("primary(3124)", 0)
        s = ctr.get("secondary(2705)", 0)
        if px % 2 == 0:
            even_p += p; even_s += s
        else:
            odd_p += p; odd_s += s
    print(f"  even prev_x: pri={even_p}  sec={even_s}")
    print(f"  odd  prev_x: pri={odd_p}  sec={odd_s}")

    # mod-4 test
    print("\nmod-4 test on prev_x (Y=10/11/12 combined):")
    mod4 = defaultdict(lambda: [0, 0])
    for (y, px), ctr in by_yprev_choice.items():
        if y not in (10, 11, 12):
            continue
        mod4[px % 4][0] += ctr.get("primary(3124)", 0)
        mod4[px % 4][1] += ctr.get("secondary(2705)", 0)
    for m in sorted(mod4):
        p, s = mod4[m]
        print(f"  prev_x %% 4 == {m}: pri={p}  sec={s}")

    # raw wx test
    print("\nraw wx breakdown (Y=10/11/12, top entries):")
    wx_rows = []
    for (y, wx), ctr in by_ywx_choice.items():
        if y != 10:
            continue
        p = ctr.get("primary(3124)", 0)
        s = ctr.get("secondary(2705)", 0)
        wx_rows.append((wx, p, s))
    for wx, p, s in sorted(wx_rows):
        verdict = "PRI" if p > s else ("SEC" if s > p else "tie")
        print(f"  Y=10 wx={wx:>2}: pri={p:>3}  sec={s:>3}  {verdict}")

    # ---- dump (block, prev_x) → offset table with confidence ----
    Y_BLOCK = {
        2: "A", 3: "A",
        4: "B", 5: "B", 6: "B",
        7: "C", 8: "C", 9: "C",
        10: "D", 11: "D", 12: "D",
        13: "E", 14: "E",
        16: "F", 17: "F", 18: "F",
        19: "G", 21: "G",
    }

    by_block_prev = defaultdict(lambda: [0, 0])  # (block, prev_x) → [pri, sec]
    for (y, px), ctr in by_yprev_choice.items():
        block = Y_BLOCK.get(y)
        if not block:
            continue
        by_block_prev[(block, px)][0] += ctr.get("primary(3124)", 0)
        by_block_prev[(block, px)][1] += ctr.get("secondary(2705)", 0)

    table_entries = {}
    for (block, px), (p, s) in sorted(by_block_prev.items()):
        tot = p + s
        if tot == 0:
            continue
        choice = "pri" if p >= s else "sec"
        conf = max(p, s) / tot
        table_entries[f"{block},{px}"] = {
            "offset": choice,
            "confidence": round(conf, 3),
            "n_pri": p,
            "n_sec": s,
            "n_total": tot,
        }

    stable = {}  # column-global stable verdicts
    for px in sorted(by_prev):
        p, s = by_prev[px]
        tot = p + s
        if tot < 8:
            continue
        choice = "pri" if p > s else ("sec" if s > p else None)
        if choice is None:
            continue
        conf = max(p, s) / tot
        stable[px] = {
            "offset": choice,
            "confidence": round(conf, 3),
            "n_total": tot,
        }

    out = {
        "schema": "(block, prev_x) → offset; fallback to STABLE column verdict; "
                  "fallback to global default 'pri'",
        "y_blocks": Y_BLOCK,
        "fixed_offsets_i0": {"pri": 3124, "sec": 2705},
        "table": table_entries,
        "stable": stable,
        "n_files_scanned": n_files,
        "n_wire_groups": total_wires,
    }
    out_path = ROOT / "results" / "r24_offset_table.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {out_path}  ({len(table_entries)} (block,prev_x) cells, "
          f"{len(stable)} stable columns)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
