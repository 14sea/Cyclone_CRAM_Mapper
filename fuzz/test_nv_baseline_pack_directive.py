# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 3/4 tests for the NV_BASELINE_PACK FASM directive family.

The meta `NV_BASELINE_PACK` + PURE_ZERO is the *byte-exact reconstruction
gate* for the nv_zero_global retirement: if this fails, the mined pack is
incomplete or decomposed into the wrong buckets.

Individual sub-directives are also exercised so callers can opt into the
subset they need (e.g. `IOB_BANK_DEFAULT_PACK` alone when they already
have a non-E15 IOB configuration).
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fasm2rbf as f
from bitstream import (
    CRC_DATA_SIZE,
    CRC_FIRST_CRAM_FRAME,
    CRC_FRAME_SIZE,
    CRC_LAST_FRAME,
    CRC_PREAMBLE,
)
from pure_zero_rbf import make_pure_zero_rbf

ROOT = HERE.parent
NV_ZERO = ROOT / "results" / "rbf" / "nv_zero_global.rbf"
PACK_JSON = ROOT / "results" / "nv_baseline_pack.json"
CRAM_START = CRC_PREAMBLE + CRC_FIRST_CRAM_FRAME * CRC_FRAME_SIZE  # 5282


def _reset_caches():
    f._NV_BASELINE_CACHE = None


def test_parse_nv_directive_family():
    """Every directive in the family parses into the expected bucket key."""
    _reset_caches()
    text = (
        "NV_BASELINE_PACK\n"
        "IOB_BANK_DEFAULT_PACK\n"
        "LOCAL_CLK_E1_BASELINE\n"
        "LOCAL_CLK_PATH_A\n"
        "LAB_LOCAL_CLK X10\n"
        "LAB_LOCAL_CLK X33\n"
        "NV_BLOCK_COL_INFRA\n"
    )
    out = f.parse_fasm(text)
    assert len(out) == 17, f"parse_fasm arity {len(out)} != 17"
    nv_buckets = out[16]
    assert nv_buckets == [
        "nv_all",
        "iob_bank_default_pack",
        "local_clk_e1_baseline",
        "local_clk_path_a",
        "lab_col_X10",
        "lab_col_X33",
        "nv_block_col_infra",
    ], nv_buckets
    print("  test_parse_nv_directive_family: OK")


def test_nv_pack_loader_shape():
    """JSON loader returns the expected bucket layout."""
    _reset_caches()
    data = f._load_nv_baseline_pack()
    assert "meta" in data
    assert "iob_bank_default_pack" in data
    assert "local_clk_e1_baseline" in data
    assert "local_clk_path_a" in data
    assert "low_frame_infra" in data
    assert "high_frame_infra" in data
    assert "residue" in data
    assert "lab_columns" in data
    # Union count matches the mining summary.
    total = (len(data["iob_bank_default_pack"])
             + len(data["local_clk_e1_baseline"])
             + len(data["local_clk_path_a"])
             + len(data["low_frame_infra"])
             + len(data["high_frame_infra"])
             + len(data["residue"])
             + sum(len(v) for v in data["lab_columns"].values()))
    assert total == data["meta"]["total_cells"], (
        f"bucket sum {total} != meta.total_cells {data['meta']['total_cells']}")
    print(f"  test_nv_pack_loader_shape: OK ({total} cells across buckets)")


def test_nv_bucket_cells_lookup():
    """Named sub-buckets + lab_col_X<n> + aggregates all resolve."""
    _reset_caches()
    data = f._load_nv_baseline_pack()
    # single named bucket
    iob = f._nv_bucket_cells("iob_bank_default_pack")
    assert len(iob) == len(data["iob_bank_default_pack"])
    assert all(isinstance(c, tuple) and len(c) == 2 for c in iob)
    # lab column lookup
    any_x = next(iter(data["lab_columns"]))
    lab = f._nv_bucket_cells(f"lab_col_X{any_x}")
    assert len(lab) == len(data["lab_columns"][any_x])
    # block-col aggregate
    blk = f._nv_bucket_cells("nv_block_col_infra")
    assert len(blk) == (len(data["low_frame_infra"])
                        + len(data["high_frame_infra"])
                        + len(data["residue"]))
    # nv_all = sum of everything
    allc = f._nv_bucket_cells("nv_all")
    assert len(allc) == data["meta"]["total_cells"]
    # Unknown X raises
    try:
        f._nv_bucket_cells("lab_col_X999")
    except f.FasmError as e:
        assert "999" in str(e)
    else:
        raise AssertionError("expected FasmError for unmined LAB column")
    print("  test_nv_bucket_cells_lookup: OK")


def test_bitgen_nv_baseline_pack_reproduces_nv_zero_global():
    """THE Phase 4 reconstruction gate.

    bitgen("NV_BASELINE_PACK", PURE_ZERO) must equal nv_zero_global.rbf
    byte-for-byte. Any deviation means the mining step left cells behind
    in a bucket that the meta directive doesn't reach.
    """
    if not NV_ZERO.exists():
        print("  test_bitgen_nv_baseline_pack_reproduces_nv_zero_global: "
              "SKIP (nv_zero_global.rbf not present)")
        return
    _reset_caches()
    pz = make_pure_zero_rbf()
    gold = NV_ZERO.read_bytes()
    out = f.bitgen("NV_BASELINE_PACK\n", pz)
    assert len(out) == len(gold), f"len {len(out)} vs {len(gold)}"
    # Full-file byte match.  Any diff is a bug.
    if out != gold:
        # Localise the diff for diagnostic output
        diffs = [i for i in range(len(out)) if out[i] != gold[i]]
        head = diffs[:8]
        raise AssertionError(
            f"NV_BASELINE_PACK + PURE_ZERO != nv_zero_global: "
            f"{len(diffs)} byte diffs, first {head}")
    print("  test_bitgen_nv_baseline_pack_reproduces_nv_zero_global: OK "
          f"({len(gold)} bytes byte-identical)")


def test_bitgen_nv_baseline_pack_double_cancels():
    """Double-emit of the meta directive cancels (XOR parity)."""
    _reset_caches()
    pz = make_pure_zero_rbf()
    out = f.bitgen("NV_BASELINE_PACK\nNV_BASELINE_PACK\n", pz)
    # CRC patch runs at the end of bitgen, so the CRC bytes of out and pz
    # will match (both are idempotent patches on the same data payload).
    assert out == pz, (
        f"double-emit of NV_BASELINE_PACK should be a no-op, got "
        f"{sum(1 for i in range(len(out)) if out[i] != pz[i])} byte diffs")
    print("  test_bitgen_nv_baseline_pack_double_cancels: OK")


def test_bitgen_iob_bank_default_pack_scope():
    """IOB_BANK_DEFAULT_PACK only touches bytes in the hdr band."""
    _reset_caches()
    pz = make_pure_zero_rbf()
    out = f.bitgen("IOB_BANK_DEFAULT_PACK\n", pz)
    # Everything outside hdr band (except CRC) must match pz exactly.
    # CRC patching is idempotent on identical CRAM data so CRAM bytes
    # should all match too.
    assert out[CRAM_START:] == pz[CRAM_START:], (
        "IOB_BANK_DEFAULT_PACK modified CRAM bytes outside hdr band")
    # Hdr band must contain bits from the bucket.
    data = f._load_nv_baseline_pack()
    for off, bp in data["iob_bank_default_pack"]:
        assert off < CRAM_START, f"bucket cell ({off},{bp}) outside hdr band"
        out_bit = (out[off] >> bp) & 1
        pz_bit = (pz[off] >> bp) & 1
        assert out_bit != pz_bit, (
            f"bucket cell ({off},{bp}) not flipped by IOB_BANK_DEFAULT_PACK")
    print(f"  test_bitgen_iob_bank_default_pack_scope: OK "
          f"({len(data['iob_bank_default_pack'])} hdr cells flipped, "
          f"CRAM unchanged)")


def test_bitgen_meta_plus_sub_cancels_bucket():
    """Emitting meta + sub cancels the sub's bucket (XOR parity).

    bitgen("NV_BASELINE_PACK\nIOB_BANK_DEFAULT_PACK\n", PURE_ZERO) should
    equal nv_zero_global XOR'd with the IOB_BANK_DEFAULT_PACK set — i.e.
    the hdr band reverts to PURE_ZERO while CRAM matches nv_zero_global.
    """
    if not NV_ZERO.exists():
        print("  test_bitgen_meta_plus_sub_cancels_bucket: SKIP "
              "(nv_zero_global.rbf not present)")
        return
    _reset_caches()
    pz = make_pure_zero_rbf()
    gold = NV_ZERO.read_bytes()
    out = f.bitgen("NV_BASELINE_PACK\nIOB_BANK_DEFAULT_PACK\n", pz)
    # CRAM must match nv_zero_global (meta applied, no sub flip in CRAM).
    assert out[CRAM_START:] == gold[CRAM_START:], (
        "CRAM diverges from nv_zero_global after meta + sub cancel")
    # Hdr must match PURE_ZERO (meta's hdr bits cancelled by sub).
    assert out[:CRAM_START] == pz[:CRAM_START], (
        "hdr band did not revert to PURE_ZERO under meta + sub cancel")
    print("  test_bitgen_meta_plus_sub_cancels_bucket: OK "
          "(hdr reverts to pure-zero; CRAM stays at nv_zero_global)")


def test_bitgen_lab_local_clk_scope():
    """LAB_LOCAL_CLK X{x} only touches cells inside that X's column range."""
    if not NV_ZERO.exists():
        print("  test_bitgen_lab_local_clk_scope: SKIP")
        return
    _reset_caches()
    import json
    from config import COLUMN_BASE
    COLUMN_STRIDE = 7350
    COLUMN_ACTIVE_LOW = 136

    data = f._load_nv_baseline_pack()
    # Pick a representative column that exists
    any_x = 10  # well-known LAB column
    assert str(any_x) in data["lab_columns"], "X=10 should be in lab_columns"
    pz = make_pure_zero_rbf()
    out = f.bitgen(f"LAB_LOCAL_CLK X{any_x}\n", pz)

    base = COLUMN_BASE[any_x]
    lo = base - COLUMN_ACTIVE_LOW
    hi = lo + COLUMN_STRIDE

    # CRC bytes live at the tail of every CRAM frame and are rewritten by
    # patch_rbf_crc whenever that frame's data changes.  A LAB column
    # boundary can sit mid-frame (e.g. X=10 lo=81746, hi=89096 straddles
    # frame 424 at [89072, 89282)) — so if the bucket flips a data byte
    # in the in-column half, the CRC bytes in the out-of-column half
    # will also flip.  That is not "scope leakage", just CRC propagation.
    def _is_crc_byte(i):
        if i < CRAM_START:
            return False
        frame = (i - CRC_PREAMBLE) // CRC_FRAME_SIZE
        if frame > CRC_LAST_FRAME:
            return False
        s = CRC_PREAMBLE + frame * CRC_FRAME_SIZE
        return i in (s + CRC_DATA_SIZE, s + CRC_DATA_SIZE + 1)

    # Every non-CRC diff byte must land inside [lo, hi).
    out_of_range = [
        i for i in range(len(out))
        if out[i] != pz[i] and not (lo <= i < hi) and not _is_crc_byte(i)
    ]
    assert not out_of_range, (
        f"LAB_LOCAL_CLK X{any_x} leaked to {len(out_of_range)} non-CRC "
        f"bytes outside column [{lo},{hi}); first: {out_of_range[:5]}")
    print(f"  test_bitgen_lab_local_clk_scope: OK "
          f"(X={any_x} scoped to [{lo},{hi}))")


def _main():
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
        except Exception:
            traceback.print_exc()
            print(f"FAIL {name}")
            failed += 1
        else:
            passed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
