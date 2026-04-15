# SPDX-License-Identifier: GPL-3.0-or-later
"""Multi-input LUT template for probing Quartus port canonicalization.

Hypothesis under test (from memory `iob_slice_mining_port_invariance.md`):
  The single-input LUT template in `template_pairs.py` produces byte-
  identical CRAM deltas for dataa/datab/datac/datad variants because
  Quartus canonicalizes single-input designs to `lut_mask=0xAAAA` routed
  to dataa.  A multi-input template — where TWO distinct IOB pins each
  drive a distinct LE port with an ASYMMETRIC `lut_mask` that depends
  functionally on both inputs — should force Quartus to honor the port
  binding physically, producing byte-DIFFERENT deltas per binding.

This module is VALIDATION-ONLY: mine 4 variants at ONE LE to see whether
the per-port bit difference exceeds a threshold (≥15 cells).  Helpers
mirror the calling convention of `template_pairs.py` so the mining
driver can reuse `compile_and_export` and `make_lccomb`.

Variants (all drive a single LE `lut_dut` at `target_lab`):

  V1  — pin_under_test -> dataa , control -> datab ,
        lut_mask = 0x2222  (A & ~B)
  V2  — pin_under_test -> datab , control -> dataa ,
        lut_mask = 0x4444  (B & ~A)
  V3  — pin_under_test -> datac , control -> dataa ,
        lut_mask = 0x0A0A  (C & ~A)
  V4  — pin_under_test -> datad , control -> dataa ,
        lut_mask = 0x00AA  (D & ~A)

All four functions are logically equivalent (pin_under_test AND NOT
control).  Only the LE port carrying the pin_under_test wire differs.
If Quartus refuses to canonicalize (because both inputs are live with
an asymmetric mask), the CRAM port-MUX layer should record a different
port per variant and the XOR deltas should differ by ≥15 cells.
"""
from __future__ import annotations

from dataclasses import dataclass


# --- 2-input variants (Round 1) ------------------------------------
# Each entry: (pin_under_test_port, control_port, lut_mask)
# Tied-off ports go to 1'b0.  lut_mask implements f = put AND NOT ctrl.
# Round 1 of the validation (see VALIDATION_multi_port.md) showed Quartus
# canonicalizes A<->B and C<->D swaps here (0 diff within {V1,V2} and
# within {V3,V4}; 8 cells between the pairs).  Kept for reference.
VARIANTS = {
    "V1_putA_ctrlB": ("dataa", "datab", 0x2222),
    "V2_putB_ctrlA": ("datab", "dataa", 0x4444),
    "V3_putC_ctrlA": ("datac", "dataa", 0x0A0A),
    "V4_putD_ctrlA": ("datad", "dataa", 0x00AA),
}


# --- 4-input variants (Round 2) ------------------------------------
# All four LUT ports are live and bound to distinct physical pins.
# The pin-under-test rotates through {A, B, C, D}; the three control
# pins fill the remaining ports.  The LUT implements the SAME semantic
# function across all 4 variants:
#     g(put, c1, c2, c3) = put AND NOT c1 AND (c2 OR NOT c3)
# so the lut_mask differs per variant (the 16-bit truth table is a
# permutation of input coordinates).  This forces Quartus to pick a
# unique port-MUX encoding per variant — if the port binding is
# physically encoded in CRAM, we expect >=15 cells of pairwise
# difference between any two variants.
#
# Entry: (put_port, c1_port, c2_port, c3_port, lut_mask)
VARIANTS_4IN = {
    "V1_putA": ("dataa", "datab", "datac", "datad", 0),
    "V2_putB": ("datab", "dataa", "datac", "datad", 0),
    "V3_putC": ("datac", "dataa", "datab", "datad", 0),
    "V4_putD": ("datad", "dataa", "datab", "datac", 0),
}


def _compute_mask_4in(put_port: str, c1_port: str, c2_port: str,
                      c3_port: str) -> int:
    """Compute the 16-bit lut_mask for semantic function
        g(put, c1, c2, c3) = put & ~c1 & (c2 | ~c3)
    given which of {dataa, datab, datac, datad} carries each role.
    LUT index i encodes (D=i3, C=i2, B=i1, A=i0)."""
    port_bit = {"dataa": 0, "datab": 1, "datac": 2, "datad": 3}
    b_put = port_bit[put_port]
    b_c1 = port_bit[c1_port]
    b_c2 = port_bit[c2_port]
    b_c3 = port_bit[c3_port]
    mask = 0
    for i in range(16):
        put = (i >> b_put) & 1
        c1 = (i >> b_c1) & 1
        c2 = (i >> b_c2) & 1
        c3 = (i >> b_c3) & 1
        if put and (not c1) and (c2 or (not c3)):
            mask |= 1 << i
    return mask


# Patch VARIANTS_4IN with computed masks so each is unique per binding.
VARIANTS_4IN = {
    name: (pu, c1, c2, c3, _compute_mask_4in(pu, c1, c2, c3))
    for name, (pu, c1, c2, c3, _) in VARIANTS_4IN.items()
}

CLK_PIN = "E1"
DEFAULT_LED = "G15"
DEFAULT_TARGET_LAB = (10, 4, 0)


@dataclass(frozen=True)
class MultiPortConfig:
    variant: str              # one of VARIANTS keys
    pin_under_test: str       # e.g. "E16"
    control_pin: str          # e.g. "E15" (for 2-input variants)
    target_lab: tuple[int, int, int] = DEFAULT_TARGET_LAB
    led_pin: str = DEFAULT_LED

    def tag(self) -> str:
        dx, dy, dn = self.target_lab
        return (
            f"iobmp_{self.pin_under_test}_{self.control_pin}_"
            f"{dx}_{dy}_{dn}_{self.variant}"
        )


@dataclass(frozen=True)
class MultiPort4InConfig:
    """Round-2 4-input config: all four LUT ports live on distinct pins."""
    variant: str              # one of VARIANTS_4IN keys
    pin_under_test: str
    ctrl1_pin: str
    ctrl2_pin: str
    ctrl3_pin: str
    target_lab: tuple[int, int, int] = DEFAULT_TARGET_LAB
    led_pin: str = DEFAULT_LED

    def tag(self) -> str:
        dx, dy, dn = self.target_lab
        return (
            f"iobmp4_{self.pin_under_test}_{self.ctrl1_pin}_"
            f"{self.ctrl2_pin}_{self.ctrl3_pin}_"
            f"{dx}_{dy}_{dn}_{self.variant}"
        )


_VERILOG_TMPL = """\
module fuzz_top(
    input  wire CLK,
    input  wire PUT,
    input  wire CTRL,
    output reg  LED
);
    wire lut_out;

    // Single LUT with two live inputs bound to physical pins via QSF.
    // lut_mask is asymmetric (put AND NOT ctrl) so Quartus cannot freely
    // rename port bindings without changing the truth-table.
    cycloneive_lcell_comb #(
        .lut_mask(16'h{LUT_MASK:04X}),
        .sum_lutc_input("datac"),
        .dont_touch("on")
    ) lut_dut (
        .dataa({DATAA}),
        .datab({DATAB}),
        .datac({DATAC}),
        .datad({DATAD}),
        .combout(lut_out)
    );

    always @(posedge CLK) begin
        LED <= lut_out;
    end
endmodule
"""


def make_verilog(cfg: MultiPortConfig) -> str:
    put_port, ctrl_port, lut_mask = VARIANTS[cfg.variant]
    bindings = {p: "1'b0" for p in ("dataa", "datab", "datac", "datad")}
    bindings[put_port] = "PUT"
    bindings[ctrl_port] = "CTRL"
    return _VERILOG_TMPL.format(
        LUT_MASK=lut_mask,
        DATAA=bindings["dataa"],
        DATAB=bindings["datab"],
        DATAC=bindings["datac"],
        DATAD=bindings["datad"],
    )


def make_qsf(cfg: MultiPortConfig, make_lccomb) -> str:
    dx, dy, dn = cfg.target_lab
    lines = [
        'set_global_assignment -name FAMILY "Cyclone IV E"',
        'set_global_assignment -name DEVICE EP4CE6F17C8',
        'set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top',
        'set_global_assignment -name VERILOG_FILE fuzz_top.v',
        'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files',
        'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"',
        'set_global_assignment -name SEED 1',
        f'set_location_assignment PIN_{CLK_PIN} -to CLK',
        f'set_location_assignment PIN_{cfg.pin_under_test} -to PUT',
        f'set_location_assignment PIN_{cfg.control_pin}    -to CTRL',
        f'set_location_assignment PIN_{cfg.led_pin}        -to LED',
        f'set_location_assignment {make_lccomb(dx, dy, dn)} -to "lut_dut"',
        'set_instance_assignment -name GLOBAL_SIGNAL "GLOBAL CLOCK" -to CLK',
    ]
    return "\n".join(lines) + "\n"


# --- 4-input variant helpers ---------------------------------------

_VERILOG_4IN_TMPL = """\
module fuzz_top(
    input  wire CLK,
    input  wire PUT,
    input  wire C1,
    input  wire C2,
    input  wire C3,
    output reg  LED
);
    wire lut_out;

    // All four LUT ports live on distinct physical pins.  Each variant
    // permutes the (put, c1, c2, c3) -> (dataa..datad) binding while
    // implementing the SAME semantic function:
    //     g = put & ~c1 & (c2 | ~c3)
    // so lut_mask varies per variant.  If Quartus honors the port
    // binding physically, CRAM deltas should differ between variants.
    cycloneive_lcell_comb #(
        .lut_mask(16'h{LUT_MASK:04X}),
        .sum_lutc_input("datac"),
        .dont_touch("on")
    ) lut_dut (
        .dataa({DATAA}),
        .datab({DATAB}),
        .datac({DATAC}),
        .datad({DATAD}),
        .combout(lut_out)
    );

    always @(posedge CLK) begin
        LED <= lut_out;
    end
endmodule
"""


def make_verilog_4in(cfg: MultiPort4InConfig) -> str:
    put_port, c1_port, c2_port, c3_port, lut_mask = VARIANTS_4IN[cfg.variant]
    signal_for_port = {
        put_port: "PUT",
        c1_port: "C1",
        c2_port: "C2",
        c3_port: "C3",
    }
    return _VERILOG_4IN_TMPL.format(
        LUT_MASK=lut_mask,
        DATAA=signal_for_port["dataa"],
        DATAB=signal_for_port["datab"],
        DATAC=signal_for_port["datac"],
        DATAD=signal_for_port["datad"],
    )


def make_qsf_4in(cfg: MultiPort4InConfig, make_lccomb) -> str:
    dx, dy, dn = cfg.target_lab
    lines = [
        'set_global_assignment -name FAMILY "Cyclone IV E"',
        'set_global_assignment -name DEVICE EP4CE6F17C8',
        'set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top',
        'set_global_assignment -name VERILOG_FILE fuzz_top.v',
        'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files',
        'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"',
        'set_global_assignment -name SEED 1',
        f'set_location_assignment PIN_{CLK_PIN} -to CLK',
        f'set_location_assignment PIN_{cfg.pin_under_test} -to PUT',
        f'set_location_assignment PIN_{cfg.ctrl1_pin}      -to C1',
        f'set_location_assignment PIN_{cfg.ctrl2_pin}      -to C2',
        f'set_location_assignment PIN_{cfg.ctrl3_pin}      -to C3',
        f'set_location_assignment PIN_{cfg.led_pin}        -to LED',
        f'set_location_assignment {make_lccomb(dx, dy, dn)} -to "lut_dut"',
        'set_instance_assignment -name GLOBAL_SIGNAL "GLOBAL CLOCK" -to CLK',
    ]
    return "\n".join(lines) + "\n"
