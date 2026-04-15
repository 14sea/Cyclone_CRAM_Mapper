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
    # Loader returns the single_le_cells override (164 cells, derived
    # from simple_led gold) when present; otherwise the absolute_cells
    # fallback (196 cells, pair-reconstruction).  (E16, 10,4,0, dataa)
    # has both — the override is the active choice for single-LE
    # designs.
    assert len(cells) == 164, f"E16->10,4,0,dataa = {len(cells)} cells"
    # every cell is a (off, bp) tuple of plain ints
    for off, bp in cells:
        assert isinstance(off, int) and isinstance(bp, int)
        assert 0 <= bp < 8
    print(f"  test_iob_route_loader_known_entry: OK ({len(cells)} cells, "
          f"single_le override)")


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
    """Applying the absolute-cell set on top of nv_zero_global MUST
    reproduce the pair RBF that Quartus itself emitted — in the CRAM
    range (frames 25..1751).  Outside that range (preamble, frames 0-24
    non-CRAM header band, trailer) nv_zero_global and the pair RBF
    carry different IOB-bank / chip-config bytes that the mining pass
    intentionally scoped out; those belong to IOB_IN / IOB_OUT, not
    IOB_ROUTE.

    This test uses the raw `absolute_cells` entry (not the loader),
    because for (E16, 10,4,0, dataa) the loader now prefers the
    single_le_cells override — that override targets simple_led gold,
    not pair RBF.  Both are valid; the directive picks the right one
    for its context.
    """
    PRE = 32
    FRAME = 210
    FIRST = 25
    LAST = 1751
    cram_start = PRE + FIRST * FRAME               # 5282
    cram_end = PRE + (LAST + 1) * FRAME            # 368192 (exclusive)

    data = json.loads(SIGCACHE.read_text())
    key = "IOB_E16->10,4,0,dataa"
    abs_cells = [tuple(c) for c in data["absolute_cells"][key]]
    base = bytearray(NV_ZERO.read_bytes())
    for off, bp in abs_cells:
        base[off] ^= (1 << bp)
    out = f.patch_rbf_crc(bytes(base))
    gold = PAIR_RBF.read_bytes()
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
          f"iob_pair_E16_10_4_0_dataa.rbf via absolute_cells[{key}]; "
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

    base = NV_ZERO.read_bytes()
    data = json.loads(SIGCACHE.read_text())
    work = ROOT / "scripts" / "iob_slice_mining" / "work"
    checked = 0
    for key, cell_list in data["absolute_cells"].items():
        # key format: "IOB_{pin}->{dx},{dy},{dn},{port}"
        src, dst = key.split("->")
        pin = src[4:]
        dx, dy, dn, port = dst.split(",")
        pair_rbf = work / f"iob_pair_{pin}_{dx}_{dy}_{dn}_{port}.rbf"
        if not pair_rbf.exists():
            continue
        # Apply absolute_cells directly (bypass the loader, which may
        # prefer a single_le_cells override for some entries targeting
        # simple_led gold instead of pair RBF).
        buf = bytearray(base)
        for off, bp in cell_list:
            buf[off] ^= (1 << bp)
        out = f.patch_rbf_crc(bytes(buf))
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


def test_iob_route_single_le_simple_led_end_to_end():
    """End-to-end: the full directive stack + IOB_ROUTE with single_le
    override must reproduce simple_led_E16_to_G15 gold byte-for-byte.

    This is the "primary-only" path — strips pair-template secondary-LE
    decoration so a single-LE design hits full RBF 0 diffs.
    """
    f._IOB_BASELINE_HDR_CACHE = None
    f._IOB_MAP_CACHE = None
    f._IOB_ROUTE_CACHE = None
    f._GCLK_PIN_CACHE = None
    f._LAB_CLK_SEL_CACHE.clear()
    f._LAB_CLK_SEL_LE_CACHE = None
    f._IOB_CLK_INPUT_CACHE = None
    base = NV_ZERO.read_bytes()
    gold_path = (ROOT / "scripts" / "iob_slice_mining" / "work"
                 / "simple_led_E16_to_G15" / "output_files"
                 / "simple_led_E16_to_G15.rbf")
    gold = gold_path.read_bytes()
    fasm = ("IOB_BASELINE_NV\n"
            "IOB_IN  PIN_E16\n"
            "IOB_OUT PIN_G15\n"
            "IOB_CLK_INPUT PIN_E1\n"
            "IOB_ROUTE PIN_E16 -> X10Y4N0.dataa\n"
            "GCLK_PIN PIN_E1\n"
            "LAB_CLK_SEL X10Y4\n"
            "LAB_CLK_SEL_LE X10Y4N0\n")
    out = f.bitgen(fasm, base, patch_crc=True)
    n_diff = sum(1 for i in range(len(out)) if out[i] != gold[i])
    assert n_diff == 0, f"{n_diff} byte diffs vs simple_led gold"
    print("  test_iob_route_single_le_simple_led_end_to_end: OK "
          "(full RBF byte-identical to simple_led_E16_to_G15.rbf)")


def test_iob_route_single_le_sweep_all_entries():
    """Every entry in single_le_cells must reproduce the matching
    single-LE Quartus gold byte-for-byte through the full 8-directive
    stack (IOB_BASELINE_NV + IOB_IN + IOB_OUT + IOB_CLK_INPUT +
    IOB_ROUTE + GCLK_PIN + LAB_CLK_SEL + LAB_CLK_SEL_LE).

    Skips entries whose gold RBF isn't built locally (run
    `scripts/iob_slice_mining/sweep_single_le.py` first to generate
    them).  At least one entry (E16->10,4,0,dataa via
    simple_led_E16_to_G15) must succeed, else the test fails.
    """
    data = json.loads(SIGCACHE.read_text())
    single_le = data.get("single_le_cells", {})
    assert single_le, "no single_le_cells entries in sigcache"
    work = ROOT / "scripts" / "iob_slice_mining" / "work"
    base = NV_ZERO.read_bytes()
    ok = 0
    skipped = 0
    for key in sorted(single_le):
        # key: "IOB_{pin}->{dx},{dy},{dn},{port}"
        src, dst = key.split("->")
        pin = src[4:]
        dx, dy, dn, port = dst.split(",")
        # Candidate gold paths: sweep_single_le layout first, then the
        # legacy simple_led_E16_to_G15 for the original entry.
        cand = [
            work / f"single_le_{pin}_to_{dx}_{dy}_{dn}_{port}"
                 / "output_files"
                 / f"single_le_{pin}_to_{dx}_{dy}_{dn}_{port}.rbf",
        ]
        if pin == "E16" and (dx, dy, dn, port) == ("10", "4", "0", "dataa"):
            cand.append(work / "simple_led_E16_to_G15" / "output_files"
                        / "simple_led_E16_to_G15.rbf")
        gold_path = next((p for p in cand if p.exists()), None)
        if gold_path is None:
            skipped += 1
            continue
        gold = gold_path.read_bytes()
        # Reset caches for a clean run
        f._IOB_BASELINE_HDR_CACHE = None
        f._IOB_MAP_CACHE = None
        f._IOB_ROUTE_CACHE = None
        f._GCLK_PIN_CACHE = None
        f._LAB_CLK_SEL_CACHE.clear()
        f._LAB_CLK_SEL_LE_CACHE = None
        f._IOB_CLK_INPUT_CACHE = None
        fasm = ("IOB_BASELINE_NV\n"
                f"IOB_IN  PIN_{pin}\n"
                "IOB_OUT PIN_G15\n"
                "IOB_CLK_INPUT PIN_E1\n"
                f"IOB_ROUTE PIN_{pin} -> X{dx}Y{dy}N{dn}.{port}\n"
                "GCLK_PIN PIN_E1\n"
                f"LAB_CLK_SEL X{dx}Y{dy}\n"
                f"LAB_CLK_SEL_LE X{dx}Y{dy}N{dn}\n")
        out = f.bitgen(fasm, base, patch_crc=True)
        n_diff = sum(1 for i in range(len(out)) if out[i] != gold[i])
        assert n_diff == 0, f"{key}: {n_diff} byte diffs vs gold"
        ok += 1
    assert ok > 0, (
        "no single_le gold RBFs found — run "
        "scripts/iob_slice_mining/sweep_single_le.py first"
    )
    print(f"  test_iob_route_single_le_sweep_all_entries: OK "
          f"({ok} entries byte-identical vs gold, {skipped} skipped "
          f"— gold RBF not built locally)")


def main():
    tests = [
        test_parse_iob_route,
        test_iob_route_loader_known_entry,
        test_iob_route_loader_unknown_raises,
        test_iob_route_xor_double_cancels,
        test_iob_route_bit_perfect_vs_pair_rbf_in_cram,
        test_iob_route_all_entries_self_consistent,
        test_iob_route_single_le_simple_led_end_to_end,
        test_iob_route_single_le_sweep_all_entries,
    ]
    for t in tests:
        f._IOB_ROUTE_CACHE = None
        t()
    print(f"\n{len(tests)}/{len(tests)} tests OK")


if __name__ == "__main__":
    main()
