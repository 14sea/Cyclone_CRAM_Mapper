# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the IOB_OE FASM directive (Stage B-narrow tristate).

Mirrors the 6-test pattern from test_iob_directive / test_iob_route_directive:

  1. Parser registers IOB_OE PIN_X as the iob_oes list (slot 19 of
     parse_fasm's 20-tuple).
  2. Cell loader reads results/iob_oe_cell_map.json keyed by package
     pin name (stripped of "PIN_").
  3. Unknown pin raises FasmError (only the 16 sdram_dq pins are valid).
  4. Hex-length / format guard: parser rejects malformed IOB_OE lines.
  5. XOR double-emit cancels (boolean parity) — IOB_OE PIN_R5 twice is
     a no-op.
  6. Round-trip / convert integration: applying IOB_OE PIN_R5 to
     nv_zero_global flips exactly the cell set recorded for that pin.

The tests are robust to a partial sweep: any pin whose entry has
empty oe_cells (build failed or skipped) is omitted from the
loader/round-trip checks but the parser tests still run.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import fasm2rbf as f


CELL_MAP = ROOT / "results" / "iob_oe_cell_map.json"
NV_ZERO  = ROOT / "results" / "rbf" / "nv_zero_global.rbf"


def _reset_caches():
    f._IOB_OE_CACHE = None


def _first_mined_pin():
    """Return (S_DB_name, package_pin) for the first invariant pin
    with non-empty cells, or (None, None) if no entries yet exist."""
    if not CELL_MAP.exists():
        return None, None
    data = json.loads(CELL_MAP.read_text())
    for entry in data.get("entries", []):
        if (entry.get("invariant") and entry.get("oe_cells")
                and entry.get("loc", "").startswith("PIN_")):
            return entry["pin"], entry["loc"][len("PIN_"):]
    return None, None


def test_parse_iob_oe_arity_and_default_empty():
    _reset_caches()
    out = f.parse_fasm("")
    assert len(out) == 21, f"parse_fasm arity {len(out)} != 21"
    assert out[19] == [], (
        f"iob_oes default should be empty list, got {out[19]!r}"
    )
    print("  test_parse_iob_oe_arity_and_default_empty: OK")


def test_parse_iob_oe_single_and_multi():
    _reset_caches()
    out = f.parse_fasm("IOB_OE PIN_R5\n")
    assert out[19] == ["R5"], out[19]
    out = f.parse_fasm("IOB_OE PIN_R5\nIOB_OE PIN_T4\n")
    assert out[19] == ["R5", "T4"], out[19]
    print("  test_parse_iob_oe_single_and_multi: OK")


def test_parse_iob_oe_malformed_rejected():
    """Malformed IOB_OE lines must raise FasmError, not silently drop."""
    bad_lines = [
        "IOB_OE",                # missing pin
        "IOB_OE R5",             # missing PIN_ prefix
        "IOB_OE PIN_",           # empty pin id
        "IOB_OE PIN_lowercase",  # lowercase rejected by [A-Z]\d+
    ]
    for line in bad_lines:
        try:
            f.parse_fasm(line + "\n")
        except f.FasmError as e:
            continue
        raise AssertionError(
            f"expected FasmError for malformed IOB_OE: {line!r}"
        )
    print("  test_parse_iob_oe_malformed_rejected: OK "
          f"({len(bad_lines)} bad inputs)")


def test_iob_oe_loader_known_entry():
    pin_name, pkg_pin = _first_mined_pin()
    if pin_name is None:
        print("  test_iob_oe_loader_known_entry: SKIP "
              "(no invariant pin with cells in iob_oe_cell_map.json yet)")
        return
    _reset_caches()
    cells = f._load_iob_oe_cells(pkg_pin)
    assert cells, f"PIN_{pkg_pin} loader returned empty"
    for off, bp in cells:
        assert isinstance(off, int) and isinstance(bp, int)
        assert 0 <= bp < 8
        # All OE cells should land in the CRAM band (off >= 5282).
        assert off >= 32 + 25 * 210, (
            f"PIN_{pkg_pin} cell ({off},{bp}) below CRAM start"
        )
    print(f"  test_iob_oe_loader_known_entry: OK "
          f"({pin_name} -> PIN_{pkg_pin}, {len(cells)} OE cells)")


def test_iob_oe_loader_unknown_raises():
    _reset_caches()
    try:
        f._load_iob_oe_cells("Z99")
    except f.FasmError as e:
        assert "no entry" in str(e), str(e)
        print("  test_iob_oe_loader_unknown_raises: OK")
        return
    raise AssertionError(
        "expected FasmError for non-sdram_dq pin"
    )


def test_iob_oe_xor_double_cancels():
    pin_name, pkg_pin = _first_mined_pin()
    if pin_name is None:
        print("  test_iob_oe_xor_double_cancels: SKIP "
              "(no mined entries)")
        return
    _reset_caches()
    base = NV_ZERO.read_bytes()
    fasm = f"IOB_OE PIN_{pkg_pin}\nIOB_OE PIN_{pkg_pin}\n"
    out = f.bitgen(fasm, base, patch_crc=False)
    assert out == base, "double IOB_OE should cancel via XOR parity"
    print(f"  test_iob_oe_xor_double_cancels: OK "
          f"(PIN_{pkg_pin} double-emit is a no-op)")


def test_iob_oe_all_16_sdram_dq_pins_loadable():
    """Once the full 16-pin sweep has run, every S_DB[*] pin must
    be loadable.  Skips with a partial-sweep notice if fewer than
    16 entries exist (allows the test to pass during incremental
    mining runs)."""
    if not CELL_MAP.exists():
        print("  test_iob_oe_all_16_sdram_dq_pins_loadable: SKIP "
              "(no cell map yet)")
        return
    data = json.loads(CELL_MAP.read_text())
    invariant_pins = data.get("routing_invariant_pins", [])
    if len(invariant_pins) < 16:
        print(f"  test_iob_oe_all_16_sdram_dq_pins_loadable: SKIP "
              f"(only {len(invariant_pins)}/16 pins invariant; "
              f"sweep partial)")
        return
    _reset_caches()
    counts = {}
    for entry in data["entries"]:
        if not entry.get("invariant"):
            continue
        loc = entry["loc"]
        if not loc.startswith("PIN_"):
            continue
        pkg = loc[len("PIN_"):]
        cells = f._load_iob_oe_cells(pkg)
        assert cells, f"PIN_{pkg} loader returned empty"
        counts[entry["pin"]] = len(cells)
    assert len(counts) == 16, (
        f"expected 16 sdram_dq pins, got {len(counts)}: "
        f"{sorted(counts)}"
    )
    print(f"  test_iob_oe_all_16_sdram_dq_pins_loadable: OK "
          f"({len(counts)} pins, "
          f"min={min(counts.values())} max={max(counts.values())} "
          f"mean={sum(counts.values())/len(counts):.1f} cells/pin)")


def test_iob_oe_universal_subset_of_each_pin():
    """The summary's `universal_oe_cells` must be a subset of every
    invariant pin's `per_pin_oe` cell set.  Validates the intersection
    semantics of `summarize`."""
    if not CELL_MAP.exists():
        print("  test_iob_oe_universal_subset_of_each_pin: SKIP "
              "(no cell map)")
        return
    data = json.loads(CELL_MAP.read_text())
    universal = {tuple(c) for c in data.get("universal_oe_cells", [])}
    invariant = set(data.get("routing_invariant_pins", []))
    if not universal or not invariant:
        print("  test_iob_oe_universal_subset_of_each_pin: SKIP "
              "(empty universal or no invariant pins)")
        return
    for pin, cells in data["per_pin_oe"].items():
        if pin not in invariant:
            continue
        pin_set = {tuple(c) for c in cells}
        missing = universal - pin_set
        assert not missing, (
            f"pin {pin}: universal cells missing from per_pin_oe: "
            f"{sorted(missing)[:5]}"
        )
    print(f"  test_iob_oe_universal_subset_of_each_pin: OK "
          f"(universal {len(universal)} cells ⊆ every "
          f"{len(invariant)}-pin per_pin_oe set)")


def test_iob_oe_single_emit_flips_exact_cells():
    """Applying IOB_OE PIN_X once must flip exactly the cell set
    recorded for that pin, no more and no less."""
    pin_name, pkg_pin = _first_mined_pin()
    if pin_name is None:
        print("  test_iob_oe_single_emit_flips_exact_cells: SKIP "
              "(no mined entries)")
        return
    _reset_caches()
    base = NV_ZERO.read_bytes()
    expected_cells = set(tuple(c) for c in f._load_iob_oe_cells(pkg_pin))
    fasm = f"IOB_OE PIN_{pkg_pin}\n"
    out = f.bitgen(fasm, base, patch_crc=False)
    diffs = set()
    for i, (a, b) in enumerate(zip(base, out)):
        x = a ^ b
        if not x:
            continue
        for bp in range(8):
            if (x >> bp) & 1:
                diffs.add((i, bp))
    assert diffs == expected_cells, (
        f"PIN_{pkg_pin}: flipped {len(diffs)} cells but expected "
        f"{len(expected_cells)}; symmetric diff = "
        f"{len(diffs ^ expected_cells)}"
    )
    print(f"  test_iob_oe_single_emit_flips_exact_cells: OK "
          f"(PIN_{pkg_pin}: {len(diffs)} cells flipped, exact match)")


def test_iob_oe_silicon_falsified_mask():
    """HW 2026-04-17: PIN_R5 bisection isolated two leaky cells —
    (363236, 2) frame=1729 shared with DSPMULT_GLOBAL_ON and
    (363672, 2) frame=1731 R5-unique.  Loader must strip both from
    every pin's emitted set; no pin's cells may include either."""
    if not CELL_MAP.exists():
        print("  test_iob_oe_silicon_falsified_mask: SKIP "
              "(no cell map yet)")
        return
    data = json.loads(CELL_MAP.read_text())
    MASK = {(363236, 2), (363672, 2)}
    _reset_caches()
    # Verify at least one pin originally carries each leaky cell in
    # the raw JSON (so the mask is load-bearing).
    raw_hits = {c: 0 for c in MASK}
    for pin, cells in data["per_pin_oe"].items():
        pin_set = {tuple(x) for x in cells}
        for c in MASK:
            if c in pin_set:
                raw_hits[c] += 1
    assert all(raw_hits[c] > 0 for c in MASK), (
        f"mask would be inert — raw JSON hit counts: {raw_hits}"
    )
    # Every pin in the loader must be clean of MASK.
    checked = 0
    for pin in data.get("routing_invariant_pins", []):
        for entry in data["entries"]:
            if entry["pin"] != pin or not entry["loc"].startswith("PIN_"):
                continue
            pkg = entry["loc"][len("PIN_"):]
            cells = set(tuple(c) for c in f._load_iob_oe_cells(pkg))
            hit = cells & MASK
            assert not hit, (
                f"PIN_{pkg} still carries silicon-falsified cell(s) "
                f"{hit} — loader mask broken"
            )
            checked += 1
    print(f"  test_iob_oe_silicon_falsified_mask: OK "
          f"({checked} pins, raw hits {raw_hits}, loader clean)")


def main():
    tests = [
        test_parse_iob_oe_arity_and_default_empty,
        test_parse_iob_oe_single_and_multi,
        test_parse_iob_oe_malformed_rejected,
        test_iob_oe_loader_known_entry,
        test_iob_oe_loader_unknown_raises,
        test_iob_oe_xor_double_cancels,
        test_iob_oe_single_emit_flips_exact_cells,
        test_iob_oe_all_16_sdram_dq_pins_loadable,
        test_iob_oe_universal_subset_of_each_pin,
        test_iob_oe_silicon_falsified_mask,
    ]
    n_ok = 0
    for t in tests:
        _reset_caches()
        try:
            t()
            n_ok += 1
        except AssertionError as e:
            print(f"  {t.__name__}: FAIL — {e}")
    print(f"\n{n_ok}/{len(tests)} tests OK")
    return 0 if n_ok == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
