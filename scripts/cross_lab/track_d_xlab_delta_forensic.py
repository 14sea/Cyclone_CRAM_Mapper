#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Track D — cross-LAB codec-vs-Quartus delta forensic.

Classifies the (off, bp) cell delta between:
  * codec   = build_test --le-a-mask 0x4444 --canon-2input absolute
              (tmp/sigcache_test/test_4_4_0_to_4_21_0_dataa.rbf, md5 5a23fb65)
  * quartus = build_quartus_xlab --le-a-mask 0x4444 gold
              (tmp/quartus_xlab/output_files/xlab_X4Y4_to_X4Y21_mask4444.rbf,
               md5 d9d1ce61)
both referenced to the nv_zero_global baseline the codec built on top of.

Primary delta uses the ABSOLUTE set-bit convention (matches the brief's
207/39 split) over the fabric region only (frame >= 25, non-CRC):
    codec_extra     = { (off,bp) : codec bit==1 AND quartus bit==0 }   (207)
    quartus_missing = { (off,bp) : quartus bit==1 AND codec bit==0 }   ( 39)

Each cell is then split by its BASELINE bit value — the decisive axis:
    codec_extra,  base==0  -> a codec DIRECTIVE set this bit (true over-emit)
    codec_extra,  base==1  -> inherited from nv_zero_global; Quartus design
                              clears it, no codec directive does (baseline residue)
    quartus_missing, base==0 -> Quartus sets a bit no codec directive sets (under-emit)
    quartus_missing, base==1 -> codec CLEARED a baseline bit Quartus keeps
                              (a directive toggled it off erroneously)

Directive attribution uses the XOR-from-baseline toggle sets C / Q
(a directive XOR-toggles bits relative to baseline):
    C  = { (off,bp) : bit set in codec   ^ baseline }
    Q  = { (off,bp) : bit set in quartus ^ baseline }

Three classification axes, per the Track D brief:
  1. region        — preamble / header / lab_cram / block_band / crc / postamble
  2. LI-lab        — li_lab_for_offset(off,bp): is this a Local-Interconnect
                     MUX cell, and which LAB does it belong to?  (+ generic
                     LAB-column attribution via COLUMN_BASE)
  3. directive set — intersection with each FASM directive's cell set, measured
                     two ways that cross-check each other:
                       LOO   (leave-one-out): C  symmetric-diff  C_without_D
                              = the marginal in-context contribution of D
                       ADD1  (add-one): cells D toggles in isolation vs baseline
                              = D's raw table footprint, interactions stripped

CRC bytes (frames 25..1751, pos 208/209) are derived, not directive cells;
they are split into their own region and excluded from the primary 207/39.

Usage:
    python3 scripts/cross_lab/track_d_xlab_delta_forensic.py
    python3 scripts/cross_lab/track_d_xlab_delta_forensic.py --json OUT.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "fuzz"))

from config import COLUMN_BASE, LAB_X, JAILBREAK_LAB_X, PAIR_SPACING  # noqa: E402
from fasm2rbf import bitgen, parse_pragmas  # noqa: E402
from bitstream import li_lab_for_offset  # noqa: E402

BASE_RBF = REPO / "results" / "rbf" / "nv_zero_global.rbf"
CODEC_RBF = REPO / "tmp" / "sigcache_test" / "test_4_4_0_to_4_21_0_dataa.rbf"
QUARTUS_RBF = (REPO / "tmp" / "quartus_xlab" / "output_files"
               / "xlab_X4Y4_to_X4Y21_mask4444.rbf")
FASM = REPO / "tmp" / "sigcache_test" / "test.fasm"

RBF_SIZE = 368011
PREAMBLE = 32
FRAME = 210
FRAME_DATA = 208
N_FRAMES = 1752
HDR_FRAMES = 25
BLOCK_BAND = range(1692, 1739)  # frames 1692..1738 inclusive
COL_WIDTH = 7350  # 35 pairs * 210


# ----------------------------------------------------------------------------
# cell-set helpers
# ----------------------------------------------------------------------------
def cells_vs_base(rbf: bytes, base: bytes) -> set[tuple[int, int]]:
    """Set of (off, bp) bits that differ between rbf and base."""
    out = set()
    for off in range(RBF_SIZE):
        x = rbf[off] ^ base[off]
        if not x:
            continue
        for bp in range(8):
            if x & (1 << bp):
                out.add((off, bp))
    return out


def region_of(off: int) -> str:
    if off < PREAMBLE:
        return "preamble"
    post_start = PREAMBLE + N_FRAMES * FRAME
    if off >= post_start:
        return "postamble"
    rel = off - PREAMBLE
    frame = rel // FRAME
    pos = rel % FRAME
    if pos >= FRAME_DATA:
        return "crc_header" if frame < HDR_FRAMES else "crc_fabric"
    if frame < HDR_FRAMES:
        return "header"
    if frame in BLOCK_BAND:
        return "block_band"
    return "lab_cram"


def is_crc(off: int) -> bool:
    return region_of(off).startswith("crc")


def col_of(off: int):
    """Return (lab_x, pair, rel_in_pair) for the LAB column containing off.

    CE6 whitelist columns take precedence over jailbreak columns where the
    physical 7350-byte windows overlap (jailbreak X=5/9/... interleave).
    """
    for group in (LAB_X, JAILBREAK_LAB_X):
        for x in group:
            base = COLUMN_BASE.get(x)
            if base is None:
                continue
            ps = base - 136
            if ps <= off < ps + COL_WIDTH:
                d = off - ps
                return x, d // PAIR_SPACING, d % PAIR_SPACING
    return None


def classify_cell(off: int, bp: int, base_bit: int = None) -> dict:
    rec = {"off": off, "bp": bp, "off_hex": f"0x{off:X}", "region": region_of(off)}
    if base_bit is not None:
        rec["base_bit"] = base_bit
    li = li_lab_for_offset(off, bp)
    rec["li_lab"] = list(li) if li else None
    col = col_of(off)
    if col:
        rec["col_lab_x"], rec["pair"], rec["rel_in_pair"] = col
    else:
        rec["col_lab_x"] = rec["pair"] = rec["rel_in_pair"] = None
    return rec


# ----------------------------------------------------------------------------
# FASM directive enumeration
# ----------------------------------------------------------------------------
def directive_lines(fasm_text: str) -> list[tuple[int, str]]:
    """Return [(line_index, stripped_directive)] for real directive lines
    (skip blanks and comments — comments incl. pragmas are preserved)."""
    out = []
    for i, line in enumerate(fasm_text.splitlines()):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append((i, s))
    return out


def rebuild_without(fasm_text: str, drop_line_idx: int, pragmas: dict) -> bytes:
    lines = fasm_text.splitlines()
    kept = [ln for j, ln in enumerate(lines) if j != drop_line_idx]
    return bitgen("\n".join(kept) + "\n", BASE, **pragmas)


def rebuild_only(directive: str, pragmas: dict) -> bytes:
    """Add-one: just this directive (+ pragmas) against baseline."""
    return bitgen(directive + "\n", BASE, **pragmas)


# ----------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()

    global BASE
    BASE = BASE_RBF.read_bytes()
    codec = CODEC_RBF.read_bytes()
    quartus = QUARTUS_RBF.read_bytes()
    fasm_text = FASM.read_text()
    pragmas = parse_pragmas(fasm_text)

    import hashlib
    print("=== Track D cross-LAB codec-vs-Quartus delta forensic ===")
    print(f"baseline  : {BASE_RBF.name}  md5 {hashlib.md5(BASE).hexdigest()[:8]}")
    print(f"codec     : {CODEC_RBF.name}  md5 {hashlib.md5(codec).hexdigest()[:8]}")
    print(f"quartus   : {QUARTUS_RBF.name}  md5 {hashlib.md5(quartus).hexdigest()[:8]}")
    print(f"pragmas   : {pragmas}")

    # sanity: bitgen reproduces codec
    repro = bitgen(fasm_text, BASE, **pragmas)
    assert hashlib.md5(repro).hexdigest() == hashlib.md5(codec).hexdigest(), \
        "bitgen does not reproduce codec RBF — abort"

    # Toggle-from-baseline sets (for directive attribution).
    C = cells_vs_base(codec, BASE)
    Q = cells_vs_base(quartus, BASE)

    def bit(buf, off, bp):
        return (buf[off] >> bp) & 1

    # Absolute set-bit delta over the FABRIC region (matches brief 207/39).
    def is_fabric(off):
        return region_of(off) in ("lab_cram", "block_band")

    ce_data = set()  # codec=1, quartus=0  (codec_extra)
    qm_data = set()  # quartus=1, codec=0  (quartus_missing)
    for off in range(RBF_SIZE):
        if not is_fabric(off):
            continue
        cx = codec[off] & ~quartus[off] & 0xFF
        qx = quartus[off] & ~codec[off] & 0xFF
        if cx:
            for bp in range(8):
                if cx & (1 << bp):
                    ce_data.add((off, bp))
        if qx:
            for bp in range(8):
                if qx & (1 << bp):
                    qm_data.add((off, bp))

    # base-value split
    ce_dir = {c for c in ce_data if bit(BASE, *c) == 0}   # directive set it
    ce_res = {c for c in ce_data if bit(BASE, *c) == 1}   # baseline residue
    qm_und = {c for c in qm_data if bit(BASE, *c) == 0}   # codec under-emit
    qm_clr = {c for c in qm_data if bit(BASE, *c) == 1}   # codec cleared baseline

    print(f"\n-- ABSOLUTE set-bit delta, fabric region (brief convention) --")
    print(f"  codec   toggle cells C (vs base): {len(C)}")
    print(f"  quartus toggle cells Q (vs base): {len(Q)}")
    print(f"  codec_extra     (codec=1,quar=0): {len(ce_data)}  (brief 207)")
    print(f"      base==0 directive-set : {len(ce_dir)}")
    print(f"      base==1 baseline-residue: {len(ce_res)}")
    print(f"  quartus_missing (quar=1,codec=0): {len(qm_data)}  (brief 39)")
    print(f"      base==0 codec under-emit : {len(qm_und)}")
    print(f"      base==1 codec cleared-baseline: {len(qm_clr)}")
    print(f"  delta total: {len(ce_data) + len(qm_data)}  (brief 246)")

    # ---- region breakdown ----
    def region_hist(cells):
        h = {}
        for off, bp in cells:
            r = region_of(off)
            h[r] = h.get(r, 0) + 1
        return dict(sorted(h.items(), key=lambda kv: -kv[1]))

    print(f"\n-- codec_extra (non-CRC) by region --")
    for r, n in region_hist(ce_data).items():
        print(f"  {r:<12} {n}")
    print(f"-- quartus_missing (non-CRC) by region --")
    for r, n in region_hist(qm_data).items():
        print(f"  {r:<12} {n}")

    # ---- LI-lab breakdown ----
    def li_hist(cells):
        h = {}
        for off, bp in cells:
            li = li_lab_for_offset(off, bp)
            key = f"LAB({li[0]},{li[1]})" if li else "(not LI)"
            h[key] = h.get(key, 0) + 1
        return dict(sorted(h.items(), key=lambda kv: -kv[1]))

    print(f"\n-- codec_extra (non-CRC) LI-lab --")
    for k, n in li_hist(ce_data).items():
        print(f"  {k:<14} {n}")
    print(f"-- quartus_missing (non-CRC) LI-lab --")
    for k, n in li_hist(qm_data).items():
        print(f"  {k:<14} {n}")

    # ---- LAB column breakdown ----
    def col_hist(cells):
        h = {}
        for off, bp in cells:
            c = col_of(off)
            key = f"X={c[0]}" if c else "(no col)"
            h[key] = h.get(key, 0) + 1
        return dict(sorted(h.items(), key=lambda kv: -kv[1]))

    print(f"\n-- codec_extra (non-CRC) LAB column --")
    for k, n in col_hist(ce_data).items():
        print(f"  {k:<10} {n}")
    print(f"-- quartus_missing (non-CRC) LAB column --")
    for k, n in col_hist(qm_data).items():
        print(f"  {k:<10} {n}")

    # ---- directive attribution: leave-one-out ----
    dirs = directive_lines(fasm_text)
    print(f"\n-- directives ({len(dirs)}) --")
    for _, s in dirs:
        print(f"  {s}")

    print(f"\n-- leave-one-out marginals (C symmetric-diff C_without_D) --")
    loo = {}  # directive -> set of cells whose toggled-state changed
    for idx, s in dirs:
        rbf_wo = rebuild_without(fasm_text, idx, pragmas)
        C_wo = cells_vs_base(rbf_wo, BASE)
        marg = C ^ C_wo
        loo[s] = marg
        marg_nc = {c for c in marg if not is_crc(c[0])}
        ce_hit = len(marg & ce_data)
        print(f"  {s:<34} marginal={len(marg):>4} (non-CRC {len(marg_nc):>4})  "
              f"∩codec_extra={ce_hit}")

    # ---- directive attribution: add-one footprints ----
    print(f"\n-- add-one footprints (directive in isolation vs baseline) --")
    add1 = {}
    for _, s in dirs:
        rbf_only = rebuild_only(s, pragmas)
        cells = cells_vs_base(rbf_only, BASE)
        add1[s] = cells
        nc = {c for c in cells if not is_crc(c[0])}
        print(f"  {s:<34} footprint={len(cells):>4} (non-CRC {len(nc):>4})")

    # split the canon_2input LUT into TT vs canon sub-layers
    lut_canon = "X4Y4N0.LUT = 0x4444"
    if lut_canon in add1:
        only_tt = cells_vs_base(bitgen(lut_canon + "\n", BASE), BASE)  # no pragma
        canon_only = add1[lut_canon] ^ only_tt
        add1["[X4Y4N0.LUT 0x4444 TT-only]"] = only_tt
        add1["[X4Y4N0.LUT 0x4444 canon-only]"] = canon_only
        print(f"  [decompose {lut_canon}] TT-only={len(only_tt)}  "
              f"canon-only={len(canon_only)}")

    # ---- per codec_extra cell: owners ----
    def owners_loo(cell):
        return [s for s, m in loo.items() if cell in m]

    def owners_add1(cell):
        return [s for s, c in add1.items()
                if cell in c and not s.startswith("[")]

    ce_records = []
    unowned = []
    for cell in sorted(ce_data):
        rec = classify_cell(*cell, base_bit=bit(BASE, *cell))
        rec["loo_owners"] = owners_loo(cell)
        rec["add1_owners"] = owners_add1(cell)
        ce_records.append(rec)
        if rec["base_bit"] == 0 and not rec["loo_owners"]:
            unowned.append(cell)

    qm_records = []
    for cell in sorted(qm_data):
        rec = classify_cell(*cell, base_bit=bit(BASE, *cell))
        # which codec directive footprints WOULD have produced this (but it
        # got cancelled / Phase-3-skipped in the full build)?
        rec["add1_owners"] = owners_add1(cell)
        rec["loo_owners"] = owners_loo(cell)
        qm_records.append(rec)

    # ---- over-emit attribution: codec_extra base==0 (directive-set) by LOO ----
    print(f"\n-- codec_extra base==0 (directive-set, {len(ce_dir)}) "
          f"attribution by LOO owner --")
    owner_tally = {}
    multi = 0
    for rec in ce_records:
        if rec["base_bit"] != 0:
            continue
        ow = rec["loo_owners"]
        if len(ow) == 0:
            owner_tally["(unowned/interaction)"] = \
                owner_tally.get("(unowned/interaction)", 0) + 1
        elif len(ow) == 1:
            owner_tally[ow[0]] = owner_tally.get(ow[0], 0) + 1
        else:
            multi += 1
            key = " & ".join(sorted(ow))
            owner_tally[f"[multi] {key}"] = owner_tally.get(f"[multi] {key}", 0) + 1
    for k, n in sorted(owner_tally.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>4}  {k}")
    print(f"  (cells with >1 LOO owner: {multi}; unowned: {len(unowned)})")

    # codec_extra base==1 (baseline residue) — region/col breakdown
    print(f"\n-- codec_extra base==1 (baseline residue, {len(ce_res)}) "
          f"region/col --")
    for r, n in region_hist(ce_res).items():
        print(f"  region {r:<12} {n}")
    for k, n in col_hist(ce_res).items():
        print(f"  col    {k:<10} {n}")

    print(f"\n-- quartus_missing (39): base==0 under-emit ({len(qm_und)}), "
          f"base==1 codec-cleared ({len(qm_clr)}) --")
    print(f"   codec directive that WOULD emit each (add1 footprint):")
    qm_tally = {}
    for rec in qm_records:
        ow = rec["add1_owners"]
        tag = "base0" if rec["base_bit"] == 0 else "base1"
        key = (" & ".join(sorted(ow)) if ow else "(NO codec directive — unmodeled)")
        key = f"[{tag}] {key}"
        qm_tally[key] = qm_tally.get(key, 0) + 1
    for k, n in sorted(qm_tally.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>4}  {k}")

    if args.json:
        out = {
            "inputs": {
                "baseline": str(BASE_RBF.relative_to(REPO)),
                "codec": str(CODEC_RBF.relative_to(REPO)),
                "quartus": str(QUARTUS_RBF.relative_to(REPO)),
                "codec_md5": hashlib.md5(codec).hexdigest(),
                "quartus_md5": hashlib.md5(quartus).hexdigest(),
            },
            "convention": "absolute set-bit, fabric region (lab_cram+block_band), "
                          "non-CRC; codec_extra=codec1&quar0, quartus_missing=quar1&codec0",
            "totals": {
                "codec_toggle_cells_vs_base": len(C),
                "quartus_toggle_cells_vs_base": len(Q),
                "codec_extra": len(ce_data),
                "codec_extra_base0_directive_set": len(ce_dir),
                "codec_extra_base1_baseline_residue": len(ce_res),
                "quartus_missing": len(qm_data),
                "quartus_missing_base0_under_emit": len(qm_und),
                "quartus_missing_base1_codec_cleared": len(qm_clr),
            },
            "region_codec_extra": region_hist(ce_data),
            "region_quartus_missing": region_hist(qm_data),
            "li_codec_extra": li_hist(ce_data),
            "li_quartus_missing": li_hist(qm_data),
            "col_codec_extra": col_hist(ce_data),
            "col_quartus_missing": col_hist(qm_data),
            "loo_marginal_sizes": {s: len(m) for s, m in loo.items()},
            "add1_footprint_sizes": {s: len(c) for s, c in add1.items()},
            "codec_extra_owner_tally": owner_tally,
            "quartus_missing_owner_tally": qm_tally,
            "codec_extra_cells": ce_records,
            "quartus_missing_cells": qm_records,
        }
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(out, indent=2) + "\n")
        print(f"\nwrote {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
