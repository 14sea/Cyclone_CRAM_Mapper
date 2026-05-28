#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""LI-MUX composition-conflict pre-flash gate (Track D, 2026-05-28).

Closes the false-green hole that let P5d reach silicon.  The existing
LI-MUX safety validator (`validate_safe_for_hardware`) checks envelope
caps but is BLIND to the case where, at a LAB whose LE carries a LUT/canon
directive, a ROUTING directive (ROUTE / IOB_ROUTE / SRC) ALSO toggles that
LAB's LI-MUX cells, so XOR composition lands the LE input MUX on the wrong
value (under-driving the LE — the P5d / Track D failure class).

KEY FINDING (Track D, why this gate is GOLD-ANCHORED, not authority-based):
There is NO gold-free local authority for these cells.  The canon LUT in
isolation reproduces Quartus's LE_A input MUX for the cross-LAB design
(9/9) but NOT for the single-LE design — the SAME (off,bp) has different
correct values in the two designs (e.g. 0x9354 bp6 = 1 cross-LAB, 0 single-
LE).  So "LUT-only" over-claims, "LUT+inbound" mis-claims, and any locally
recomputed authority either false-positives on silicon-good builds or
misses the real corruption.  The cell semantics are design-context-
dependent (Pitfall #14).  The only sound check is byte-identity against a
Quartus gold of the EXACT design at the co-determined LI cells.

THE GATE:
1. Find every LAB that carries a LUT/canon directive AND whose LI-MUX cells
   are also toggled by >=1 routing directive (co-determined input MUX).
2. Those cells CANNOT be certified by local analysis.
   - If a Quartus gold is provided: FAIL on any co-determined LI cell where
     the composed build != gold (precise conflict detection).
   - If no gold: REFUSE to certify (this is exactly the silent-flash that
     killed P5d — local gates green, no gold byte-identity, silicon red).

This encodes the path_alpha / P5d lesson as enforcement: a build with
routing-co-determined LE input-MUX cells must pass gold byte-identity at
those cells before flash; `validate_safe_for_hardware` returning 0 is
necessary-not-sufficient.

Usage:
    from li_mux_conflict_gate import li_mux_gate, LiMuxConflictError
    rep = li_mux_gate(fasm_text, base_rbf, composed_rbf=rbf, gold_rbf=gold)
    li_mux_gate(fasm_text, base_rbf, composed_rbf=rbf, gold_rbf=gold,
                raise_on_fail=True)            # raises LiMuxConflictError

CLI:
    python3 fuzz/li_mux_conflict_gate.py FASM BASE_RBF COMPOSED_RBF [GOLD_RBF]
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict

from bitstream import _LI_CELL_TO_LAB
from fasm2rbf import bitgen, parse_pragmas

_LUT_RE = re.compile(r"^\s*X(\d+)Y(\d+)N(\d+)\.LUT(_ARITH)?\b")
# Routing-class directives that can spuriously reach a LAB's LI-MUX cells.
_ROUTE_KEYWORDS = ("ROUTE ", "IOB_ROUTE ", "SRC ", "OUTROUTE_G15 ")


class LiMuxConflictError(RuntimeError):
    """Raised when co-determined LE input-MUX cells fail gold byte-identity
    (or cannot be verified because no gold was supplied)."""


def _li_cells_by_lab():
    out = defaultdict(list)
    for (off, bp), lab in _LI_CELL_TO_LAB.items():
        out[lab].append((off, bp))
    return out


_LI_BY_LAB = _li_cells_by_lab()


def _bit(buf, off, bp):
    return (buf[off] >> bp) & 1


def _directive_lines(fasm_text):
    return [ln.strip() for ln in fasm_text.splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


def _lut_labs(fasm_text):
    labs = set()
    for ln in fasm_text.splitlines():
        m = _LUT_RE.match(ln)
        if m:
            labs.add((int(m.group(1)), int(m.group(2))))
    return labs


def codetermined_li_cells(fasm_text, base_rbf, *, pragmas=None):
    """Return {(lx,ly): [(off,bp), ...]} of LI-MUX cells at LABs that carry a
    LUT directive AND are also toggled by >=1 routing directive — i.e. cells
    whose value is co-determined by LUT + routing and therefore not locally
    certifiable.
    """
    if pragmas is None:
        pragmas = parse_pragmas(fasm_text)
    pragma_lines = [ln for ln in fasm_text.splitlines()
                    if ln.strip().startswith("#")]
    lut_labs = _lut_labs(fasm_text)
    if not lut_labs:
        return {}

    # Per-directive isolated LI footprint, restricted to LUT-bearing LABs.
    route_li_hits = defaultdict(set)  # lab -> set of (off,bp) routing touches
    for d in _directive_lines(fasm_text):
        if not any(d.startswith(k) for k in _ROUTE_KEYWORDS):
            continue
        only = bitgen("\n".join(pragma_lines + [d]) + "\n", base_rbf, **pragmas)
        for lab in lut_labs:
            for off, bp in _LI_BY_LAB.get(lab, ()):
                if (only[off] ^ base_rbf[off]) >> bp & 1:
                    route_li_hits[lab].add((off, bp))

    return {lab: sorted(cells) for lab, cells in route_li_hits.items() if cells}


def li_mux_gate(fasm_text, base_rbf, *, composed_rbf=None, gold_rbf=None,
                pragmas=None, raise_on_fail=False):
    """Gold-anchored LI-MUX composition gate.

    Returns a report dict:
      {ok, codetermined: {lab:[cells]}, mismatches:[...], unverified:[labs],
       summary}
    `mismatches` are co-determined LI cells where composed != gold (only when
    gold supplied).  `unverified` lists LABs whose co-determined cells could
    not be checked because no gold was given.
    ok is False if there are mismatches OR unverified co-determined cells.
    """
    if pragmas is None:
        pragmas = parse_pragmas(fasm_text)
    if composed_rbf is None:
        composed_rbf = bitgen(fasm_text, base_rbf, **pragmas)

    codet = codetermined_li_cells(fasm_text, base_rbf, pragmas=pragmas)
    mismatches, unverified = [], []
    if codet and gold_rbf is None:
        unverified = sorted(codet.keys())
    elif codet:
        for lab, cells in codet.items():
            for off, bp in cells:
                c, g = _bit(composed_rbf, off, bp), _bit(gold_rbf, off, bp)
                if c != g:
                    mismatches.append({
                        "lab": lab, "off_hex": f"0x{off:X}", "bp": bp,
                        "composed_bit": c, "gold_bit": g,
                        "direction": ("under_drive" if (g == 1 and c == 0)
                                      else "wrong_byte" if (g == 0 and c == 1)
                                      else "mismatch"),
                    })
    mismatches.sort(key=lambda m: (m["off_hex"], m["bp"]))
    ok = not mismatches and not unverified
    n_codet = sum(len(v) for v in codet.values())
    summary = (f"co-determined LI cells: {n_codet} across LABs "
               f"{sorted(codet.keys())}; mismatches-vs-gold: {len(mismatches)}; "
               f"unverified-LABs: {len(unverified)}")
    rep = {"ok": ok, "codetermined": codet, "mismatches": mismatches,
           "unverified": unverified, "summary": summary}
    if raise_on_fail and not ok:
        if mismatches:
            ud = sum(1 for m in mismatches if m["direction"] == "under_drive")
            raise LiMuxConflictError(
                f"LI-MUX gold mismatch: {len(mismatches)} co-determined LE "
                f"input-MUX cells diverge from Quartus gold ({ud} under-drive)"
                f" — silicon will mis-drive the LE (P5d class). "
                f"First 6: {[(m['off_hex'], m['bp'], m['direction']) for m in mismatches[:6]]}")
        raise LiMuxConflictError(
            f"LI-MUX UNVERIFIED: {n_codet} LE input-MUX cells at LABs "
            f"{unverified} are co-determined by LUT + routing directives and "
            f"no Quartus gold was supplied to verify them. Local safety gates "
            f"are necessary-not-sufficient (P5d precedent). Provide a gold or "
            f"do not flash.")
    return rep


def main(argv):
    if len(argv) < 4:
        print(__doc__)
        return 2
    fasm_text = open(argv[1]).read()
    base = open(argv[2], "rb").read()
    composed = open(argv[3], "rb").read()
    gold = open(argv[4], "rb").read() if len(argv) > 4 else None
    rep = li_mux_gate(fasm_text, base, composed_rbf=composed, gold_rbf=gold)
    print(rep["summary"])
    if rep["ok"]:
        print("[OK] LI-MUX composition verified")
        return 0
    for m in rep["mismatches"]:
        print(f"  MISMATCH LAB{m['lab']} {m['off_hex']} bp{m['bp']}  "
              f"composed={m['composed_bit']} gold={m['gold_bit']} {m['direction']}")
    if rep["unverified"]:
        print(f"  UNVERIFIED LABs (no gold): {rep['unverified']}")
    print("[FAIL] LI-MUX composition gate")
    return 1


if __name__ == "__main__":
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    sys.exit(main(sys.argv))
