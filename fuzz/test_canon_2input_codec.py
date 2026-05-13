#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression for the 2-input canonicalization-cell codec extension (P2 of
plan ``imperative-crafting-pumpkin``).

What this validates
-------------------

  * Module-level loading: CANON_2INPUT_ABSOLUTE has X4Y4N0 entry with
    18 perm + 6 neg = 24 labels of expected size range.
  * canon_2input_label_for_mask: 24 canonical masks map; non-canonical
    masks return None.
  * canon_2input_cells: returns frozenset; KeyError on bad position /
    bad label.
  * canon_2input_apply: XOR-applies the cells; round-trip (twice == id).
  * LutCodec.write_tt(... canon_2input=label) byte-identical to cached
    Quartus canon_{label}_X4Y4N0.rbf for all 24 labels (after CRC patch).
  * write_tt mutual exclusion: canon_2input + canon_to raises ValueError.
  * Legacy default unchanged: write_tt(... canon_2input=None) emits
    predict_sram(M) only.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "fuzz"))

from bitstream import (  # noqa: E402
    CANON_2INPUT_ABSOLUTE,
    LutCodec,
    canon_2input_apply,
    canon_2input_cells,
    canon_2input_label_for_mask,
)
from fasm2rbf import patch_rbf_crc  # noqa: E402


ZERO_RBF_PATH = REPO / "results" / "rbf" / "nv_zero_global.rbf"
CACHE = REPO / "tmp" / "real_tt_mining"

# (label, mask, safe-name).  Mirror probe_canonicalization_cells.py.
LABELS = [
    ("a&b", 0x8888, "aandb"), ("a&c", 0xA0A0, "aandc"),
    ("a&d", 0xAA00, "aandd"), ("b&c", 0xC0C0, "bandc"),
    ("b&d", 0xCC00, "bandd"), ("c&d", 0xF000, "candd"),
    ("a|b", 0xEEEE, "aorb"),  ("a|c", 0xFAFA, "aorc"),
    ("a|d", 0xAAFF, "aord"),  ("b|c", 0xFCFC, "borc"),
    ("b|d", 0xCCFF, "bord"),  ("c|d", 0xFFF0, "cord"),
    ("a^b", 0x6666, "axorb"), ("a^c", 0x5A5A, "axorc"),
    ("a^d", 0x55AA, "axord"), ("b^c", 0x3C3C, "bxorc"),
    ("b^d", 0x33CC, "bxord"), ("c^d", 0x0FF0, "cxord"),
    ("!a&b", 0x4444, "naandb"), ("a&!b", 0x2222, "aandnb"),
    ("!a&!b", 0x1111, "naandnb"),
    ("!a|b", 0xDDDD, "naorb"), ("a|!b", 0xBBBB, "aornb"),
    ("!a|!b", 0x7777, "naornb"),
]


def _load(p):
    return Path(p).read_bytes()


def t_table_loaded():
    assert (4, 4, 0) in CANON_2INPUT_ABSOLUTE, \
        f"X4Y4N0 missing from CANON_2INPUT_ABSOLUTE; loaded: " \
        f"{sorted(CANON_2INPUT_ABSOLUTE)}"
    labels = CANON_2INPUT_ABSOLUTE[(4, 4, 0)]
    assert len(labels) == 24, f"want 24 labels, got {len(labels)}"
    # Spot-check size range.
    sizes = sorted(len(v) for v in labels.values())
    assert sizes[0] >= 230, f"smallest label too small: {sizes[0]}"
    assert sizes[-1] <= 260, f"largest label too big: {sizes[-1]}"


def t_label_for_mask():
    # Canonical 24 → label
    for lbl, mask, _ in LABELS:
        got = canon_2input_label_for_mask(mask)
        assert got == lbl, f"0x{mask:04X}: want {lbl}, got {got}"
    # Non-canonical → None
    for non_canon in (0x0000, 0xFFFF, 0xAAAA, 0xCCCC,
                      0x6996, 0x9669, 0x1234):
        assert canon_2input_label_for_mask(non_canon) is None, \
            f"0x{non_canon:04X} unexpectedly classified as 2-input"


def t_cells_lookup():
    # Returns frozenset
    cells = canon_2input_cells(4, 4, 0, "a&b")
    assert isinstance(cells, frozenset)
    assert len(cells) > 200
    # Missing position
    try:
        canon_2input_cells(99, 99, 0, "a&b")
    except KeyError:
        pass
    else:
        assert False, "missing position should raise KeyError"
    # Bad label
    try:
        canon_2input_cells(4, 4, 0, "nope&nope")
    except KeyError:
        pass
    else:
        assert False, "bad label should raise KeyError"


def t_apply_round_trip():
    zero = _load(ZERO_RBF_PATH)
    once = canon_2input_apply(zero, 4, 4, 0, "a&b")
    twice = canon_2input_apply(once, 4, 4, 0, "a&b")
    assert twice == zero, "apply twice should be identity"


def t_write_tt_byte_identity_to_quartus():
    """24/24 byte-identical to cached Quartus canon_{label}_X4Y4N0.rbf."""
    zero = _load(ZERO_RBF_PATH)
    codec = LutCodec.from_cram_model(4, 4, 0)
    skipped = 0
    failed = []
    for lbl, mask, safe in LABELS:
        ref_path = CACHE / f"canon_{safe}_X4Y4N0" / f"canon_{safe}_X4Y4N0.rbf"
        if not ref_path.exists():
            skipped += 1
            print(f"  [skip] no Quartus reference for {lbl}")
            continue
        ref = _load(ref_path)
        out = codec.write_tt(zero, mask, canon_2input=lbl)
        out_crc = patch_rbf_crc(out)
        bydiff = sum(1 for i in range(len(out_crc)) if out_crc[i] != ref[i])
        if bydiff:
            failed.append((lbl, mask, bydiff))
            print(f"  FAIL  {lbl:>6} (0x{mask:04X}): {bydiff} byte diffs")
    assert not failed, f"{len(failed)} byte-identity failures"
    n = len(LABELS) - skipped
    print(f"  {n}/{len(LABELS)} 2-input canon labels byte-identical to Quartus")


def t_write_tt_mutual_exclusion():
    zero = _load(ZERO_RBF_PATH)
    codec = LutCodec.from_cram_model(4, 4, 0)
    try:
        codec.write_tt(zero, 0x8888, canon_to="b", canon_2input="a&b")
    except ValueError:
        pass
    else:
        assert False, "canon_to + canon_2input should raise ValueError"


def t_legacy_default_unchanged():
    """write_tt(... canon_2input=None) emits predict_sram(M) only."""
    zero = _load(ZERO_RBF_PATH)
    codec = LutCodec.from_cram_model(4, 4, 0)
    for mask in (0x8888, 0xA0A0, 0x6666, 0xEEEE):
        out_default = codec.write_tt(zero, mask)
        expected = bytearray(zero)
        for addr, bp in codec.predict_sram(mask):
            expected[addr] ^= 1 << bp
        assert out_default == bytes(expected), \
            f"legacy default broken at 0x{mask:04X}"


def t_bitgen_canon_2input_aware_byte_identity():
    """End-to-end bitgen path: ``# fasm2rbf: canon_2input_aware=1`` +
    ``X4Y4N0.LUT = 0x{mask}`` against nv_zero_global produces byte-identical
    to cached Quartus canon_{label}_X4Y4N0.rbf for the 24 canonical masks.
    """
    from fasm2rbf import bitgen, parse_pragmas
    nv_zero = _load(ZERO_RBF_PATH)
    failed = []
    skipped = 0
    for lbl, mask, safe in LABELS:
        ref_path = CACHE / f"canon_{safe}_X4Y4N0" / f"canon_{safe}_X4Y4N0.rbf"
        if not ref_path.exists():
            skipped += 1
            continue
        fasm = (f"# fasm2rbf: canon_2input_aware=1\n"
                f"X4Y4N0.LUT = 0x{mask:04X}\n")
        pragmas = parse_pragmas(fasm)
        out = bitgen(fasm, nv_zero, **pragmas)
        ref = _load(ref_path)
        bydiff = sum(1 for i in range(len(out)) if out[i] != ref[i])
        if bydiff:
            failed.append((lbl, mask, bydiff))
            print(f"  FAIL bitgen {lbl:>6} (0x{mask:04X}): {bydiff} diffs")
    assert not failed, f"{len(failed)} bitgen byte-identity failures"
    n = len(LABELS) - skipped
    print(f"  bitgen path: {n}/{len(LABELS)} byte-identical")


def t_bitgen_canon_2input_aware_missing_position_raises():
    """Bitgen at an unmined position with canon_2input_aware must raise."""
    from fasm2rbf import bitgen, parse_pragmas, FasmError
    nv_zero = _load(ZERO_RBF_PATH)
    # X10Y17N0 has 2-input perm probes but no codec table entry yet.
    fasm = (f"# fasm2rbf: canon_2input_aware=1\n"
            f"X10Y17N0.LUT = 0x8888\n")
    pragmas = parse_pragmas(fasm)
    try:
        bitgen(fasm, nv_zero, **pragmas)
    except FasmError as e:
        msg = str(e)
        assert "canon_2input_aware" in msg and "not mined" in msg, msg
    else:
        assert False, "expected FasmError on unmined position"


def main():
    tests = [
        ("table_loaded",                t_table_loaded),
        ("label_for_mask",              t_label_for_mask),
        ("cells_lookup",                t_cells_lookup),
        ("apply_round_trip",            t_apply_round_trip),
        ("write_tt_byte_identity",      t_write_tt_byte_identity_to_quartus),
        ("write_tt_mutual_exclusion",   t_write_tt_mutual_exclusion),
        ("legacy_default_unchanged",    t_legacy_default_unchanged),
        ("bitgen_2input_aware_byte_id", t_bitgen_canon_2input_aware_byte_identity),
        ("bitgen_2input_missing_pos",   t_bitgen_canon_2input_aware_missing_position_raises),
    ]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed.append((name, str(e)))
            print(f"  FAIL  {name}: {e}")
        except Exception as e:
            failed.append((name, f"{type(e).__name__}: {e}"))
            print(f"  ERR   {name}: {type(e).__name__}: {e}")
    print()
    if failed:
        print(f"FAILED: {len(failed)}/{len(tests)}")
        return 1
    print(f"PASS: {len(tests)}/{len(tests)} canon-2input-codec tests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
