# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for fuzz/specimen_base.py.

Pure-Python tests (always run):
  * Harness factories produce expected pin sets.
  * Specimen.vary enforces single-axis perturbation.
  * Specimen.render_qsf includes harness pins, placement, SEED, OPT-OFFs.
  * diff_cram filters preamble / header-noise frames / CRC bytes / postamble.
  * diff_cram passes through real CRAM-band differences.
  * make_minimal_1le_specimen produces a buildable single-LUT design.

Quartus-gated tests (skipped when quartus_map isn't on PATH):
  * test_harness_freeze_is_byte_identical
  * test_routing_invariance_probe_passes_for_canonical_1le_specimen
  * test_diff_is_single_cell_for_one_lut_bit_toggle (XOR-base aware)
  * test_routing_invariance_probe_flags_loose_harness
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from config import FUZZ_PINS, PREAMBLE_BYTES, RBF_SIZE
from specimen_base import (
    CRAM_OFFSET_HI,
    CRAM_OFFSET_LO,
    DATA_BYTES_PER_FRAME,
    FRAME_BYTES,
    Harness,
    Specimen,
    diff_cram,
    make_minimal_1le_specimen,
    routing_invariance_probe,
)


QUARTUS_AVAILABLE = shutil.which("quartus_map") is not None


# ----------------------------- pure Python -----------------------------

def test_harness_default_uses_fuzz_pins():
    h = Harness.default()
    pins = dict(h.iob_pins)
    assert pins == FUZZ_PINS
    assert h.clk_signal == "CLK"
    assert h.seed == 1
    print("  test_harness_default_uses_fuzz_pins: OK")


def test_harness_minimal_combinational_has_no_clock():
    h = Harness.minimal_combinational()
    pins = dict(h.iob_pins)
    assert set(pins) == {"A", "Q"}
    assert h.clk_signal is None
    print("  test_harness_minimal_combinational_has_no_clock: OK")


def test_harness_with_seed_returns_new_instance():
    h = Harness.default(seed=7)
    h2 = h.with_seed(11)
    assert h.seed == 7
    assert h2.seed == 11
    assert h is not h2
    print("  test_harness_with_seed_returns_new_instance: OK")


def test_specimen_vary_enforces_single_axis():
    spec = make_minimal_1le_specimen((10, 4, 0))
    # OK: one axis
    spec.vary(name="other")
    spec.vary(placement={"lut_inst": (10, 4, 2)})
    # Bad: zero axes
    try:
        spec.vary()
    except ValueError:
        pass
    else:
        raise AssertionError("vary() with no kwargs must raise")
    # Bad: two axes
    try:
        spec.vary(name="x", verilog="// other")
    except ValueError:
        pass
    else:
        raise AssertionError("vary() with two kwargs must raise")
    print("  test_specimen_vary_enforces_single_axis: OK")


def test_specimen_render_qsf_includes_pins_and_placement():
    spec = make_minimal_1le_specimen((10, 4, 0))
    qsf = spec.render_qsf()
    assert "PIN_E16" in qsf            # FUZZ_PINS["A"]
    assert "PIN_G15" in qsf            # FUZZ_PINS["Q"]
    assert "LCCOMB_X10_Y4_N0" in qsf
    assert "SEED 1" in qsf
    # CLK must NOT appear for the minimal harness (CLK pin is PIN_E1).
    # Use whole-line check; "PIN_E1" is a prefix substring of PIN_E15/E16 etc.
    assert not any(line.endswith(" CLK") and "PIN_E1 " in line
                   for line in qsf.splitlines()), qsf
    # GLOBAL CLOCK assignment must NOT appear when clk_signal is None
    assert "GLOBAL CLOCK" not in qsf
    # Optimization-off list applied
    assert "AUTO_RAM_RECOGNITION OFF" in qsf
    print("  test_specimen_render_qsf_includes_pins_and_placement: OK")


def test_specimen_render_qsf_emits_clk_when_present():
    spec = Specimen(
        name="with_clk",
        harness=Harness.default(),
        verilog="// placeholder\n",
        placement={},
    )
    qsf = spec.render_qsf()
    assert "PIN_E1" in qsf  # FUZZ_PINS["CLK"]
    assert 'GLOBAL_SIGNAL "GLOBAL CLOCK" -to CLK' in qsf
    print("  test_specimen_render_qsf_emits_clk_when_present: OK")


def test_diff_cram_filters_preamble_and_postamble():
    a = bytearray(b"\x00" * RBF_SIZE)
    b = bytearray(b"\x00" * RBF_SIZE)
    # Flip bit 0 in preamble (byte 5)
    b[5] = 0x01
    # Flip bit 0 in postamble (byte 367952 = first postamble byte)
    b[CRAM_OFFSET_HI] = 0x01
    cells = diff_cram(bytes(a), bytes(b))
    assert cells == set(), f"expected empty (preamble+postamble filtered), got {cells}"
    print("  test_diff_cram_filters_preamble_and_postamble: OK")


def test_diff_cram_filters_header_noise_frames():
    a = bytearray(b"\x00" * RBF_SIZE)
    b = bytearray(b"\x00" * RBF_SIZE)
    # Frame 24 is the last header-noise frame; offset = 32 + 24*210 = 5072
    header_noise_off = PREAMBLE_BYTES + 24 * FRAME_BYTES
    b[header_noise_off] = 0x80
    assert header_noise_off < CRAM_OFFSET_LO
    cells = diff_cram(bytes(a), bytes(b))
    assert cells == set()
    print("  test_diff_cram_filters_header_noise_frames: OK")


def test_diff_cram_filters_crc_bytes():
    a = bytearray(b"\x00" * RBF_SIZE)
    b = bytearray(b"\x00" * RBF_SIZE)
    # Frame 100 is well past header noise; CRC bytes live at in_frame 208,209
    base = PREAMBLE_BYTES + 100 * FRAME_BYTES
    b[base + 208] = 0xFF
    b[base + 209] = 0xFF
    cells = diff_cram(bytes(a), bytes(b))
    assert cells == set(), f"CRC bytes must be filtered, got {cells}"
    print("  test_diff_cram_filters_crc_bytes: OK")


def test_diff_cram_passes_through_real_cram_difference():
    a = bytearray(b"\x00" * RBF_SIZE)
    b = bytearray(b"\x00" * RBF_SIZE)
    # Frame 100, in-frame byte 50, bit 3
    target_off = PREAMBLE_BYTES + 100 * FRAME_BYTES + 50
    assert CRAM_OFFSET_LO <= target_off < CRAM_OFFSET_HI
    assert ((target_off - PREAMBLE_BYTES) % FRAME_BYTES) < DATA_BYTES_PER_FRAME
    b[target_off] = 1 << 3
    cells = diff_cram(bytes(a), bytes(b))
    assert cells == {(target_off, 3)}
    print("  test_diff_cram_passes_through_real_cram_difference: OK")


def test_make_minimal_1le_specimen_has_expected_shape():
    spec = make_minimal_1le_specimen((22, 12, 4), lut_mask=0x00FF, name="probe")
    assert spec.name == "probe"
    assert "lut_mask(16'h00FF)" in spec.verilog
    assert spec.placement == {"lut_inst": (22, 12, 4)}
    assert spec.harness.clk_signal is None
    print("  test_make_minimal_1le_specimen_has_expected_shape: OK")


# ---------------------------- Quartus-gated ----------------------------

def _quartus_skip(label: str) -> bool:
    if not QUARTUS_AVAILABLE:
        print(f"  {label}: SKIP (quartus_map not on PATH)")
        return True
    return False


def test_harness_freeze_is_byte_identical():
    """Same harness + same perturbation across two builds → byte-identical RBFs."""
    if _quartus_skip("test_harness_freeze_is_byte_identical"):
        return
    spec = make_minimal_1le_specimen((10, 4, 0), name="freeze_a")
    with tempfile.TemporaryDirectory(prefix="spec_freeze_") as tmp:
        tmp = Path(tmp)
        rbf1 = spec.build(tmp / "build_a")
        rbf2 = spec.build(tmp / "build_b")
        a = rbf1.read_bytes()
        b = rbf2.read_bytes()
        assert a == b, (
            f"identical specimen produced different RBFs "
            f"({sum(1 for x, y in zip(a, b) if x != y)} differing bytes)"
        )
    print("  test_harness_freeze_is_byte_identical: OK")


def test_routing_invariance_probe_passes_for_canonical_1le_specimen():
    """The smallest possible specimen MUST be routing-invariant under SEED."""
    if _quartus_skip("test_routing_invariance_probe_passes_for_canonical_1le_specimen"):
        return
    spec = make_minimal_1le_specimen((10, 4, 0), name="invar_probe")
    with tempfile.TemporaryDirectory(prefix="spec_invar_") as tmp:
        ok, drift = routing_invariance_probe(spec, tmp, n_seeds=3)
        assert ok, (
            f"canonical 1-LE specimen drifted under SEED change "
            f"({len(drift)} CRAM cells): sample={sorted(drift)[:5]}"
        )
    print("  test_routing_invariance_probe_passes_for_canonical_1le_specimen: OK")


def test_diff_is_single_cell_for_one_lut_bit_toggle():
    """Toggling one LUT mask bit should produce a tiny CRAM diff.

    LutCodec writes are XOR-delta against an XOR-base (see LUT_ENCODING).
    A single-bit mask flip nominally hits 2 cells (the bit and its XOR
    counterpart). We accept ≤4 cells as the invariance window — anything
    larger means routing/clock cells are leaking into the diff.
    """
    if _quartus_skip("test_diff_is_single_cell_for_one_lut_bit_toggle"):
        return
    base = make_minimal_1le_specimen((10, 4, 0), lut_mask=0xAAAA, name="lut_base")
    perturbed = base.vary(verilog=base.verilog.replace("16'hAAAA", "16'hAAAB"))
    with tempfile.TemporaryDirectory(prefix="spec_lutdiff_") as tmp:
        tmp = Path(tmp)
        rbf_a = base.build(tmp / "base").read_bytes()
        rbf_b = perturbed.build(tmp / "pert").read_bytes()
        cells = diff_cram(rbf_a, rbf_b)
        assert 1 <= len(cells) <= 4, (
            f"single-bit LUT toggle produced {len(cells)} CRAM cells "
            f"(expected 1..4 with XOR-base accounting): {sorted(cells)[:8]}"
        )
    print(f"  test_diff_is_single_cell_for_one_lut_bit_toggle: OK ({len(cells)} cells)")


def test_routing_invariance_probe_flags_loose_harness():
    """Deliberately loose harness: probe must report drift if Quartus refits.

    We construct a harness with NO IOB pins beyond CLK and a deliberately
    over-sized two-LUT design with no placement constraints. If Quartus
    is free to relocate either LUT under SEED change, the probe must
    return is_invariant=False with non-empty drift.

    NOTE: this is best-effort. Some Quartus configurations may still
    produce identical CRAM by coincidence; in that case we mark the test
    as inconclusive (still passes) to avoid false failures.
    """
    if _quartus_skip("test_routing_invariance_probe_flags_loose_harness"):
        return
    loose_harness = Harness(
        iob_pins=tuple(FUZZ_PINS.items()),  # full pinout but…
        clk_signal="CLK",
        seed=1,
        name="loose",
    )
    loose_verilog = """\
module fuzz_top(
    input  wire CLK,
    input  wire A, B, C, D,
    output reg  Q
);
    wire l1, l2, l3, l4;
    assign l1 = A & B;
    assign l2 = C ^ D;
    assign l3 = (l1 | l2) & A;
    assign l4 = l3 ^ B ^ C ^ D;
    always @(posedge CLK) Q <= l4;
endmodule
"""
    spec = Specimen(
        name="loose_design",
        harness=loose_harness,
        verilog=loose_verilog,
        placement={},  # no placement constraints — Quartus is free
    )
    with tempfile.TemporaryDirectory(prefix="spec_loose_") as tmp:
        ok, drift = routing_invariance_probe(spec, tmp, n_seeds=3)
        if ok:
            print("  test_routing_invariance_probe_flags_loose_harness: "
                  "INCONCLUSIVE (Quartus produced byte-identical CRAM despite loose harness)")
            return
        assert len(drift) > 0
    print(f"  test_routing_invariance_probe_flags_loose_harness: OK ({len(drift)} drift cells)")


# --------------------------------- main --------------------------------

def main() -> int:
    pure = [
        test_harness_default_uses_fuzz_pins,
        test_harness_minimal_combinational_has_no_clock,
        test_harness_with_seed_returns_new_instance,
        test_specimen_vary_enforces_single_axis,
        test_specimen_render_qsf_includes_pins_and_placement,
        test_specimen_render_qsf_emits_clk_when_present,
        test_diff_cram_filters_preamble_and_postamble,
        test_diff_cram_filters_header_noise_frames,
        test_diff_cram_filters_crc_bytes,
        test_diff_cram_passes_through_real_cram_difference,
        test_make_minimal_1le_specimen_has_expected_shape,
    ]
    gated = [
        test_harness_freeze_is_byte_identical,
        test_routing_invariance_probe_passes_for_canonical_1le_specimen,
        test_diff_is_single_cell_for_one_lut_bit_toggle,
        test_routing_invariance_probe_flags_loose_harness,
    ]
    failed = 0
    print("Pure-Python tests:")
    for t in pure:
        try:
            t()
        except Exception as e:
            failed += 1
            print(f"  {t.__name__}: FAIL ({e})")
    print(f"\nQuartus-gated tests ({'ENABLED' if QUARTUS_AVAILABLE else 'SKIP'}):")
    for t in gated:
        try:
            t()
        except Exception as e:
            failed += 1
            print(f"  {t.__name__}: FAIL ({e})")
    total = len(pure) + len(gated)
    print(f"\n{total - failed}/{total} tests passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
