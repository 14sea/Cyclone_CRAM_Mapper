# SPDX-License-Identifier: GPL-3.0-or-later
"""Verilog + QSF generators for paired IOB->SLICE route mining.

For each (src_pin, target_LE, target_port) combination the mining
pass builds two RBFs:

  "zero" — IOB_<src_pin> -> LUT@ZERO_LAB.dataa -> DFF -> IOB_<sink>
           LUT@target_LE exists with mask=0x0000, driven by the OTHER
           secondary IOB <src2_pin>; its DFF.Q drives <sec_sink>.

  "pair" — IOB_<src_pin> -> LUT@target_LE.<port> -> DFF -> IOB_<sink>
           LUT@ZERO_LAB exists with mask=0x0000, driven by <src2_pin>;
           its DFF.Q drives <sec_sink>.

Both designs place the SAME set of IOBs (src_pin, src2_pin, sink,
sec_sink, CLK=E1) and the SAME pair of LEs. Only which LE is fed by
src_pin fabric changes. XOR-diffing the two RBFs cancels:
  * Pad buffers for all 4 IOBs (unchanged pin assignments)
  * LE infrastructure at both sites (placement identical)
  * Clock tree (GCLK_PIN E1 + per-LAB CLK_SEL on both)
  * Secondary IOB fabric (src2_pin drives both zero and pair)

Leaving (approximately):
  * Delta of src_pin fabric: zero_lab_route XOR target_lab_route
  * Delta of dataa vs target_port mux-select at both LEs (LUT-level
    mask change 0xAAAA <-> 0x0000, etc.)

Calling convention: make_verilog/make_qsf take an explicit `variant`
argument ("zero" or "pair") so a single config tuple drives both builds.

Pin notes (CE6/AX301, see CLAUDE.md):
  * CLK = E1 (dedicated clock input, GLOBAL_SIGNAL forced)
  * Default primary sink = G15 (LED0)
  * Default secondary sink = F15 (LED1 / unused IO)
  * Default secondary source = A11 (arbitrary bank-A input, far from E16/E15/M16)
  * ZERO_LAB = (28, 16, 0) — far-corner CE6 LAB, maximizes geometric
    separation from typical target_LABs like (10, 4) so the zero-route
    fabric path is unambiguously different.
"""
from __future__ import annotations

from dataclasses import dataclass


PORT_TO_MASK = {
    "dataa": 0xAAAA,
    "datab": 0xCCCC,
    "datac": 0xF0F0,
    "datad": 0xFF00,
}

# Defaults — caller may override per build
DEFAULT_ZERO_LAB = (28, 16, 0)
DEFAULT_SEC_SRC = "A11"        # secondary source (drives the OTHER LE)
DEFAULT_PRIMARY_SINK = "G15"   # LE-under-test Q output pin
DEFAULT_SEC_SINK = "F15"       # secondary LE Q output pin
CLK_PIN = "E1"


@dataclass(frozen=True)
class PairConfig:
    """Single (src_pin, target, port) mining task."""
    src_pin: str
    target_lab: tuple[int, int, int]  # (dx, dy, dn)
    target_port: str                  # "dataa" / "datab" / "datac" / "datad"
    zero_lab: tuple[int, int, int] = DEFAULT_ZERO_LAB
    sec_src_pin: str = DEFAULT_SEC_SRC
    primary_sink: str = DEFAULT_PRIMARY_SINK
    sec_sink: str = DEFAULT_SEC_SINK

    def tag(self, variant: str) -> str:
        dx, dy, dn = self.target_lab
        if variant == "zero":
            return f"iob_zero_{self.src_pin}"
        return (
            f"iob_pair_{self.src_pin}_"
            f"{dx}_{dy}_{dn}_{self.target_port}"
        )


_VERILOG_TMPL = """\
module fuzz_top(
    input  wire CLK,
    input  wire K_PRIM,
    input  wire K_SEC,
    output reg  LED_PRIM,
    output reg  LED_SEC
);
    wire lut_prim_out;
    wire lut_sec_out;

    // Primary LE — the one whose fabric route we want to mine.
    // In "zero" variant this LE exists with mask=0x0000, unused inputs.
    // In "pair" variant it has mask={PRIM_MASK:#06x} with K_PRIM driving
    // its <target_port>.
    cycloneive_lcell_comb #(
        .lut_mask(16'h{PRIM_MASK:04X}),
        .sum_lutc_input("datac"),
        .dont_touch("on")
    ) lut_prim (
        .dataa({PRIM_DATAA}),
        .datab({PRIM_DATAB}),
        .datac({PRIM_DATAC}),
        .datad({PRIM_DATAD}),
        .combout(lut_prim_out)
    );

    // Secondary LE — always driven by K_SEC, mask swapped with primary.
    // Keeps K_PRIM-distinct IOB structure present in both variants.
    cycloneive_lcell_comb #(
        .lut_mask(16'h{SEC_MASK:04X}),
        .sum_lutc_input("datac"),
        .dont_touch("on")
    ) lut_sec (
        .dataa({SEC_DATAA}),
        .datab({SEC_DATAB}),
        .datac({SEC_DATAC}),
        .datad({SEC_DATAD}),
        .combout(lut_sec_out)
    );

    always @(posedge CLK) begin
        LED_PRIM <= lut_prim_out;
        LED_SEC  <= lut_sec_out;
    end
endmodule
"""


def _port_binding(port: str, signal: str) -> dict[str, str]:
    """Return a {dataa, datab, datac, datad} map where only <port>
    is driven by <signal>; others tie to 1'b0."""
    out = {p: "1'b0" for p in PORT_TO_MASK}
    out[port] = signal
    return out


def make_verilog(cfg: PairConfig, variant: str) -> str:
    if variant not in ("zero", "pair"):
        raise ValueError(f"variant must be 'zero' or 'pair', got {variant!r}")

    if variant == "pair":
        # K_PRIM drives target LE's <target_port> with mask matched to port.
        # Secondary LE has mask=0x0000 (constant-0), K_SEC drives its dataa
        # (so the sec IOB still has a real fabric destination).
        prim_mask = PORT_TO_MASK[cfg.target_port]
        prim_bindings = _port_binding(cfg.target_port, "K_PRIM")
        sec_mask = 0x0000
        sec_bindings = _port_binding("dataa", "K_SEC")
    else:
        # "zero": K_PRIM drives zero_lab's dataa (mask 0xAAAA passthrough).
        # Target LE has mask=0x0000, K_SEC drives its dataa.
        # From the diff's perspective, primary LE plays the role of
        # target_LE at *this* location in the "zero" variant.
        prim_mask = 0xAAAA
        prim_bindings = _port_binding("dataa", "K_PRIM")
        sec_mask = 0x0000
        sec_bindings = _port_binding("dataa", "K_SEC")

    vals = {
        "PRIM_MASK": prim_mask,
        "SEC_MASK": sec_mask,
        "PRIM_DATAA": prim_bindings["dataa"],
        "PRIM_DATAB": prim_bindings["datab"],
        "PRIM_DATAC": prim_bindings["datac"],
        "PRIM_DATAD": prim_bindings["datad"],
        "SEC_DATAA": sec_bindings["dataa"],
        "SEC_DATAB": sec_bindings["datab"],
        "SEC_DATAC": sec_bindings["datac"],
        "SEC_DATAD": sec_bindings["datad"],
    }
    return _VERILOG_TMPL.format(**vals)


def make_qsf(cfg: PairConfig, variant: str, make_lccomb) -> str:
    """Build QSF string.

    Key point — which LUT instance gets pinned where SWAPS between
    variants, because `lut_prim` plays the role of:
       pair : the target LE (gets target_lab pinning)
       zero : the zero_lab LE (gets zero_lab pinning)
    This ensures K_PRIM always drives the "primary" LUT instance in
    Verilog, and the LE location moves between variants.
    """
    if variant == "pair":
        prim_loc = cfg.target_lab
        sec_loc = cfg.zero_lab
    else:
        prim_loc = cfg.zero_lab
        sec_loc = cfg.target_lab

    lines = [
        'set_global_assignment -name FAMILY "Cyclone IV E"',
        'set_global_assignment -name DEVICE EP4CE6F17C8',
        'set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top',
        'set_global_assignment -name VERILOG_FILE fuzz_top.v',
        'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files',
        'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"',
        'set_global_assignment -name SEED 1',
        f'set_location_assignment PIN_{CLK_PIN} -to CLK',
        f'set_location_assignment PIN_{cfg.src_pin}       -to K_PRIM',
        f'set_location_assignment PIN_{cfg.sec_src_pin}   -to K_SEC',
        f'set_location_assignment PIN_{cfg.primary_sink}  -to LED_PRIM',
        f'set_location_assignment PIN_{cfg.sec_sink}      -to LED_SEC',
        f'set_location_assignment {make_lccomb(*prim_loc)} -to "lut_prim"',
        f'set_location_assignment {make_lccomb(*sec_loc)}  -to "lut_sec"',
        'set_instance_assignment -name GLOBAL_SIGNAL "GLOBAL CLOCK" -to CLK',
    ]
    return "\n".join(lines) + "\n"
