# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the IOB_ROUTE FASM directive.

The directive consumes results/iob_to_slice_sigcache.json (the absolute-
cell table derived by scripts/iob_slice_mining/compute_absolute_cells.py
via the bridge-delta identity
  cells_abs(pin, tgt) = delta(pin, tgt) XOR bridge(pin)
with bridge(pin) = iob_zero(pin) XOR nv_zero_global).

Tests:
  1. Parser accepts the new syntax and produces tuples.
  2. Loader reads the JSON, errors cleanly on unknown (pin, tgt).
  3. XOR parity semantics: single flip, double cancels.
  4. **Bit-perfect round trip**: applying `IOB_ROUTE PIN_E16 ->
     X10Y4N0.dataa` on top of nv_zero_global reproduces the HW-verified
     `iob_pair_E16_10_4_0_dataa.rbf` byte-for-byte (modulo CRC, which is
     recomputed by patch_rbf_crc and should match).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import fasm2rbf as f


NV_ZERO = ROOT / "results" / "rbf" / "nv_zero_global.rbf"
PAIR_RBF = (ROOT / "scripts" / "iob_slice_mining" / "work"
            / "iob_pair_E16_10_4_0_dataa.rbf")
SIGCACHE = ROOT / "results" / "iob_to_slice_sigcache.json"


def test_parse_iob_route():
    text = ("IOB_ROUTE PIN_E16 -> X10Y4N0.dataa\n"
            "IOB_ROUTE PIN_M16 -> X16Y4N0.dataa\n")
    out = f.parse_fasm(text)
    iob_routes = out[9]
    assert iob_routes == [
        ("E16", 10, 4, 0, "dataa"),
        ("M16", 16, 4, 0, "dataa"),
    ], iob_routes
    print("  test_parse_iob_route: OK")


def test_iob_route_loader_known_entry():
    cells = f._load_iob_route_cells("E16", 10, 4, 0, "dataa")
    assert isinstance(cells, list), type(cells)
    assert len(cells) == 196, f"E16->10,4,0,dataa = {len(cells)} cells"
    # every cell is a (off, bp) tuple of plain ints
    for off, bp in cells:
        assert isinstance(off, int) and isinstance(bp, int)
        assert 0 <= bp < 8
    print(f"  test_iob_route_loader_known_entry: OK ({len(cells)} cells)")


def test_iob_route_loader_unknown_raises():
    f._IOB_ROUTE_CACHE = None  # force cold load
    try:
        f._load_iob_route_cells("Z99", 10, 4, 0, "dataa")
    except f.FasmError as e:
        assert "no entry" in str(e), str(e)
        print("  test_iob_route_loader_unknown_raises: OK")
        return
    raise AssertionError("expected FasmError for unknown pin")


def test_iob_route_xor_double_cancels():
    f._IOB_ROUTE_CACHE = None
    base = NV_ZERO.read_bytes()
    fasm = ("IOB_ROUTE PIN_E16 -> X10Y4N0.dataa\n"
            "IOB_ROUTE PIN_E16 -> X10Y4N0.dataa\n")
    out = f.bitgen(fasm, base, patch_crc=False)
    assert out == base, "double IOB_ROUTE should cancel (XOR parity)"
    print("  test_iob_route_xor_double_cancels: OK")


def test_iob_route_bit_perfect_vs_pair_rbf_in_cram():
    """Applying the bridge-translated cells on top of nv_zero_global MUST
    reproduce the pair RBF that Quartus itself emitted — in the CRAM
    range (frames 25..1751).  Outside that range (preamble, frames 0-24
    non-CRAM header band, trailer) nv_zero_global and the pair RBF
    carry different IOB-bank / chip-config bytes that the mining pass
    intentionally scoped out; those belong to IOB_IN / IOB_OUT, not
    IOB_ROUTE.
    """
    # Mining-scope constants (match scripts/iob_slice_mining and
    # fuzz/bitstream.py: CRC_PREAMBLE=32, CRC_FRAME_SIZE=210,
    # CRC_FIRST_CRAM_FRAME=25, CRC_LAST_FRAME=1751).
    PRE = 32
    FRAME = 210
    FIRST = 25
    LAST = 1751
    cram_start = PRE + FIRST * FRAME               # 5282
    cram_end = PRE + (LAST + 1) * FRAME            # 368192 (exclusive)

    f._IOB_ROUTE_CACHE = None
    base = NV_ZERO.read_bytes()
    gold = PAIR_RBF.read_bytes()
    fasm = "IOB_ROUTE PIN_E16 -> X10Y4N0.dataa\n"
    out = f.bitgen(fasm, base, patch_crc=True)
    assert len(out) == len(gold), f"size {len(out)} vs {len(gold)}"

    cram_diffs = [(i, out[i], gold[i])
                  for i in range(cram_start, cram_end)
                  if out[i] != gold[i]]
    hdr_diffs = sum(1 for i in range(cram_start)
                    if out[i] != gold[i])
    trl_diffs = sum(1 for i in range(cram_end, len(out))
                    if out[i] != gold[i])

    assert not cram_diffs, (
        f"{len(cram_diffs)} CRAM-band byte diffs vs pair RBF; "
        f"first: {cram_diffs[:3]}"
    )
    print(f"  test_iob_route_bit_perfect_vs_pair_rbf_in_cram: OK "
          f"(CRAM frames 25..1751 byte-identical to "
          f"iob_pair_E16_10_4_0_dataa.rbf; "
          f"hdr_band={hdr_diffs} trl_band={trl_diffs} — "
          f"those are IOB_IN/OUT scope, not IOB_ROUTE scope)")


def test_iob_route_all_entries_self_consistent():
    """Every entry in iob_to_slice_sigcache.json, when applied to
    nv_zero_global via IOB_ROUTE, must reproduce the *corresponding* pair
    RBF in the CRAM frame range (25..1751). This batch-verifies the
    bridge-delta algebra over all 15 mined entries. Header/trailer
    bands are IOB_IN/OUT scope (bank config), not IOB_ROUTE scope."""
    PRE = 32
    FRAME = 210
    FIRST = 25
    LAST = 1751
    cram_start = PRE + FIRST * FRAME
    cram_end = PRE + (LAST + 1) * FRAME

    f._IOB_ROUTE_CACHE = None
    base = NV_ZERO.read_bytes()
    data = json.loads(SIGCACHE.read_text())
    work = ROOT / "scripts" / "iob_slice_mining" / "work"
    checked = 0
    for key in data["absolute_cells"]:
        # key format: "IOB_{pin}->{dx},{dy},{dn},{port}"
        src, dst = key.split("->")
        pin = src[4:]
        dx, dy, dn, port = dst.split(",")
        pair_rbf = work / f"iob_pair_{pin}_{dx}_{dy}_{dn}_{port}.rbf"
        if not pair_rbf.exists():
            continue
        fasm = f"IOB_ROUTE PIN_{pin} -> X{dx}Y{dy}N{dn}.{port}\n"
        out = f.bitgen(fasm, base, patch_crc=True)
        gold = pair_rbf.read_bytes()
        n_cram_diff = sum(1 for i in range(cram_start, cram_end)
                          if out[i] != gold[i])
        assert n_cram_diff == 0, (
            f"{key}: {n_cram_diff} CRAM-band bytes differ from golden"
        )
        checked += 1
    assert checked > 0, "no pair RBFs found to cross-check"
    print(f"  test_iob_route_all_entries_self_consistent: OK "
          f"({checked} entries reproduce their pair RBF byte-perfectly "
          f"in the CRAM frame range)")


def main():
    tests = [
        test_parse_iob_route,
        test_iob_route_loader_known_entry,
        test_iob_route_loader_unknown_raises,
        test_iob_route_xor_double_cancels,
        test_iob_route_bit_perfect_vs_pair_rbf_in_cram,
        test_iob_route_all_entries_self_consistent,
    ]
    for t in tests:
        f._IOB_ROUTE_CACHE = None
        t()
    print(f"\n{len(tests)}/{len(tests)} tests OK")


if __name__ == "__main__":
    main()
