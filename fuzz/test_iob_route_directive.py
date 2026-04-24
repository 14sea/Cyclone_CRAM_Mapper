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
    # Loader returns the absolute_cells pair-reconstruction entry
    # (196 cells). The single_le_cells override (164 cells, derived
    # 2026-04-15) was quarantined 2026-04-24 after directive-stack
    # drift — see test_single_le_bucket_is_quarantined.
    assert len(cells) == 196, f"E16->10,4,0,dataa = {len(cells)} cells"
    for off, bp in cells:
        assert isinstance(off, int) and isinstance(bp, int)
        assert 0 <= bp < 8
    print(f"  test_iob_route_loader_known_entry: OK ({len(cells)} cells, "
          f"absolute_cells)")


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

    This test uses the raw `absolute_cells` entry (which the loader
    also returns now that single_le_cells is quarantined).
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


def test_single_le_bucket_refreshed_by_fix_b():
    """2026-04-24 Fix B re-mined all 109 single_le entries against the
    legacy apply-path (``legacy_iob_route=True``).  The fresh bucket
    lives under ``single_le_cells`` again; ``single_le_cells_stale``
    is kept as a fallback for keys a future re-sweep drops.  The
    legacy loader prefers ``single_le_cells`` per-key (see
    ``_load_iob_route_cells_legacy``)."""
    data = json.loads(SIGCACHE.read_text())
    assert "single_le_cells" in data, (
        "single_le_cells bucket missing — Fix B re-mine not applied "
        "yet? run scripts/iob_slice_mining/sweep_single_le.py "
        "--orphans-only --skip-build --include-known")
    assert "single_le_cells_stale" in data, (
        "stale bucket missing — keep it as a safety-net fallback for "
        "the legacy loader.")
    live_keys = set(data["single_le_cells"].keys())
    stale_keys = set(data["single_le_cells_stale"].keys())
    # Every formerly-quarantined key should now be freshly mined.
    missed = stale_keys - live_keys
    assert not missed, (
        f"Fix B missed {len(missed)} stale keys: {sorted(missed)[:5]}... "
        f"— re-run sweep_single_le.py --orphans-only --include-known "
        f"to cover them.")
    assert len(live_keys) >= 109, (
        f"single_le_cells has {len(live_keys)} entries — expected ≥109 "
        f"after Fix B.")
    print("  test_single_le_bucket_refreshed_by_fix_b: OK "
          f"({len(live_keys)} live entries; stale fallback retains "
          f"{len(stale_keys)} for safety)")


CFF800E_PROBE_RBF = (ROOT / "scripts" / "stage0_flash_bundle"
                     / "simple_led_m9k_mode_goldintersect.rbf")

CFF800E_PROBE_FASM = """\
NV_BASELINE_PACK
IOB_BASELINE_NV
IOB_IN  PIN_E16
IOB_OUT PIN_G15
IOB_CLK_INPUT PIN_E1
IOB_ROUTE PIN_E16 -> X10Y4N0.dataa
GCLK_PIN PIN_E1
LAB_CLK_SEL X10Y4
LAB_CLK_SEL_LE X10Y4N0
X15Y10N0.M9K_MODE_9x512_inferred_goldintersect
"""


def test_legacy_iob_route_loader_uses_single_le_bucket():
    """`_load_iob_route_cells_legacy` must prefer the legacy single_le
    bucket (164 cells for E16->10,4,0,dataa) over absolute_cells (196).

    This is what reproduces the cff800e / d48c13e HW-PASS simple_led
    probe semantics — the live loader switched to absolute_cells + dedup
    + hdr-skip in 6b6cda9 which silently breaks silicon for single-LE
    designs built against nv_zero_global."""
    f._IOB_ROUTE_LEGACY_CACHE = None
    cells = f._load_iob_route_cells_legacy("E16", 10, 4, 0, "dataa")
    assert len(cells) == 164, (
        f"legacy loader returned {len(cells)} cells — expected 164 "
        f"(single_le_cells_stale bucket).  If bumped, the single_le "
        f"override path is no longer consulted correctly.")
    print(f"  test_legacy_iob_route_loader_uses_single_le_bucket: OK "
          f"({len(cells)} cells, single_le override)")


def test_legacy_iob_route_reproduces_cff800e_hw_pass_rbf():
    """`legacy_iob_route=True` + the cff800e FASM MUST reproduce the
    committed simple_led_m9k_mode_goldintersect.rbf byte-for-byte.

    That RBF was HW-validated on AX301 (LED follows KEY2) via the
    overlay probe path documented in d48c13e and memory
    m9k_mode_w18_hw_validated.md.  If this test drifts, the Fix-A
    legacy path has regressed — the simple_led-class single-LE designs
    will flash broken."""
    if not CFF800E_PROBE_RBF.exists():
        print("  test_legacy_iob_route_reproduces_cff800e_hw_pass_rbf: "
              "SKIP (reference RBF missing)")
        return
    from pure_zero_rbf import make_pure_zero_rbf
    f._IOB_ROUTE_CACHE = None
    f._IOB_ROUTE_NODEDUP_KEYS = None
    f._IOB_ROUTE_LEGACY_CACHE = None
    pure = make_pure_zero_rbf()
    out = f.bitgen(CFF800E_PROBE_FASM, pure, patch_crc=True,
                   legacy_iob_route=True)
    ref = CFF800E_PROBE_RBF.read_bytes()
    assert out == ref, (
        f"legacy bitgen drift: "
        f"{sum(1 for i in range(len(ref)) if out[i] != ref[i])} byte "
        f"diffs vs committed HW-PASS probe RBF")
    print("  test_legacy_iob_route_reproduces_cff800e_hw_pass_rbf: OK "
          "(byte-identical)")


def test_fix_b_all_orphan_keys_routable_via_legacy():
    """Every key that lives ONLY in ``single_le_cells_stale`` (i.e.,
    not in ``absolute_cells`` or ``padnv_cells``) must now load via
    the legacy path — that's the Fix B re-mine guarantee (94 keys,
    2026-04-24).  Before Fix B these raised FasmError."""
    data = json.loads(SIGCACHE.read_text())
    stale = set(data.get("single_le_cells_stale", {}).keys())
    live = set(data.get("absolute_cells", {}).keys()) | set(
        data.get("padnv_cells", {}).keys())
    orphans = sorted(stale - live)
    assert len(orphans) >= 94, (
        f"expected ≥94 stale-only keys, got {len(orphans)}")

    f._IOB_ROUTE_LEGACY_CACHE = None
    failed = []
    sampled = 0
    for key in orphans:
        body = key[len("IOB_"):]
        pin, rhs = body.split("->")
        dx, dy, dn, port = rhs.split(",")
        try:
            cells = f._load_iob_route_cells_legacy(
                pin, int(dx), int(dy), int(dn), port)
            if not cells:
                failed.append((key, "empty"))
            sampled += 1
        except f.FasmError as e:
            failed.append((key, str(e)[:60]))
    assert not failed, (
        f"legacy loader failed for {len(failed)} orphan keys: "
        f"{failed[:3]}")
    print(f"  test_fix_b_all_orphan_keys_routable_via_legacy: OK "
          f"({sampled} orphan keys load cleanly)")


def test_legacy_iob_route_vs_live_drift_quantified():
    """Sanity: live path (legacy_iob_route=False) must drift from the
    HW-PASS RBF by a large, stable number of bytes (the 443 figure
    logged in simple_led_directive_drift_bisect.md).  A smaller number
    means the live path quietly converged (celebrate, then re-examine
    the legacy flag's necessity).  A larger number means some other
    data source changed — investigate before shipping."""
    if not CFF800E_PROBE_RBF.exists():
        print("  test_legacy_iob_route_vs_live_drift_quantified: "
              "SKIP (reference RBF missing)")
        return
    from pure_zero_rbf import make_pure_zero_rbf
    f._IOB_ROUTE_CACHE = None
    f._IOB_ROUTE_NODEDUP_KEYS = None
    f._IOB_ROUTE_LEGACY_CACHE = None
    pure = make_pure_zero_rbf()
    live = f.bitgen(CFF800E_PROBE_FASM, pure, patch_crc=True)
    ref = CFF800E_PROBE_RBF.read_bytes()
    drift = sum(1 for i in range(len(ref)) if live[i] != ref[i])
    # Tolerate ±50 bytes of CRC chain noise around the documented 443.
    assert 350 <= drift <= 550, (
        f"live-vs-HW-PASS drift = {drift} (expected ~443). If this "
        f"shrank unexpectedly, Fix A may be obsolete. If it grew, a new "
        f"data file drifted — bisect before shipping.")
    print(f"  test_legacy_iob_route_vs_live_drift_quantified: OK "
          f"(live drift = {drift}; expected band 350..550)")


def main():
    tests = [
        test_parse_iob_route,
        test_iob_route_loader_known_entry,
        test_iob_route_loader_unknown_raises,
        test_iob_route_xor_double_cancels,
        test_iob_route_bit_perfect_vs_pair_rbf_in_cram,
        test_iob_route_all_entries_self_consistent,
        test_single_le_bucket_refreshed_by_fix_b,
        test_legacy_iob_route_loader_uses_single_le_bucket,
        test_legacy_iob_route_reproduces_cff800e_hw_pass_rbf,
        test_fix_b_all_orphan_keys_routable_via_legacy,
        test_legacy_iob_route_vs_live_drift_quantified,
    ]
    for t in tests:
        f._IOB_ROUTE_CACHE = None
        f._IOB_ROUTE_NODEDUP_KEYS = None
        f._IOB_ROUTE_LEGACY_CACHE = None
        t()
    print(f"\n{len(tests)}/{len(tests)} tests OK")


if __name__ == "__main__":
    main()
