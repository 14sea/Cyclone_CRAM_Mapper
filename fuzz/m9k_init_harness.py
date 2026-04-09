# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.2 Stage A — M9K init-content harness.

Reusable builder that compiles one altsyncram with a user-supplied
init pattern and returns the resulting .rbf path. Used by
``m9k_init_null.py`` (noise floor) and ``m9k_init_sweep.py``
(single-bit walking-1 sweep at word=0).

Design rules (non-LAB blocks, learned the hard way):
- Real I/O pins only. No VIRTUAL_PIN on the M9K data/address ports.
  (see memory/feedback_virtual_pin_mining_is_fiction.md)
- LOC pins on AX301: reuse the same pin bank as ``mult_reg_sweep.py``
  so Quartus has a fixed escape path and we don't pay router roulette.
- DEVICE = EP4CE10F17C8 (jailbreak target — M9K_X15_Y2_N0 is on the
  physical die; fits in CE6 silicon per 2026-04-07 cross-device proof).
- CRAM-only analysis (off >= 5282) — do NOT interpret header-band
  diffs (see memory/feedback_header_band_noise_floor.md).

Shape of the harness:
  fuzz_top = altsyncram 9x512, SINGLE_PORT, UNREGISTERED output,
             init_file = "m9k_init.mif"
  Real pin LOC: 9b addr + 9b data_in + wren + clock + 9b data_out
  Addr/data bits mostly go through LAB routing to the M9K — that
  creates noise in LAB CRAM. We filter it by restricting diff analysis
  to the 1692-1738 frame band (Phase 5.0 non-LAB block band) OR by
  using per-bit SYMMETRIC diff (both baseline and target share the
  same harness, so routing cells cancel).
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compile import setup_project, compile_full, generate_rbf
from config import RBF_DIR

FAMILY = "Cyclone IV E"
DEVICE = "EP4CE10F17C8"

# Stage A fixed point: smallest real M9K shape, X=15 column.
M9K_LOC = "M9K_X15_Y2_N0"
M9K_NODE = "altsyncram:u|altsyncram_3ov:auto_generated|ALTSYNCRAM"

# 9x512 = 4608 init bits. 9 is the native M9K word width (8 data + 1 parity).
WIDTH = 9
DEPTH = 512
ADDR_BITS = 9   # log2(DEPTH)

# Real pin map — same bank as mult_reg_sweep (AX301-friendly).
# We need 9 addr + 9 din + 9 dout + wren + clock = 29 pins. Use
# plentiful side of the package; any free pin works because we
# never drive them from hardware — we just need LOC to be real.
PINS = {
    "clk":  "PIN_E1",
    "wren": "PIN_E15",
}
# Assign addr[0..8] and din[0..8] and dout[0..8] to an arbitrary
# contiguous pin block. Quartus only needs legal pins, not a sane
# bank assignment, for headless CRAM mining.
# AX301 SDRAM data+addr bus pins from ~/fpga/AX301_ref/AX301.tcl — 16
# S_DB + 13 S_A = exactly 29 pins, all board-validated. Earlier drafts
# picked PIN_B1/B2/C1/C2/D1/D2/E2/... which are EPCS config dual-use
# (DCLK/DATA0/SCE/SDO in AX301.tcl) and Quartus rejects them with
# fitter error 171016. SDRAM bus pins are safe because we never drive
# the SDRAM chip in this harness — headless mining only needs legal
# LOC.
_FREE_PINS = [
    # S_DB[0..15] — SDRAM data bus
    "PIN_R5","PIN_T4","PIN_T3","PIN_R3","PIN_T2","PIN_R1","PIN_P2","PIN_P1",
    "PIN_R13","PIN_T13","PIN_R12","PIN_T12","PIN_T10","PIN_R10","PIN_T11","PIN_R11",
    # S_A[0..12] — SDRAM addr bus
    "PIN_T8","PIN_P9","PIN_T9","PIN_R9","PIN_L16","PIN_L15","PIN_N16","PIN_N15",
    "PIN_P16","PIN_P15","PIN_R8","PIN_R16","PIN_T15",
]
for i in range(ADDR_BITS):
    PINS[f"addr{i}"] = _FREE_PINS[i]
for i in range(WIDTH):
    PINS[f"din{i}"]  = _FREE_PINS[ADDR_BITS + i]
for i in range(WIDTH):
    PINS[f"dout{i}"] = _FREE_PINS[ADDR_BITS + WIDTH + i]


def gen_mif(overrides: dict[int, int] | None = None) -> str:
    """Generate a DEPTH x WIDTH Intel MIF file.

    overrides: {word_index: raw_int_value} — words not listed default
    to 0. Raw value is the WIDTH-bit word (0..2**WIDTH-1).
    """
    overrides = overrides or {}
    lines = [
        f"WIDTH = {WIDTH};",
        f"DEPTH = {DEPTH};",
        "ADDRESS_RADIX = HEX;",
        "DATA_RADIX = HEX;",
        "CONTENT BEGIN",
    ]
    hex_width = (WIDTH + 3) // 4
    hex_addr = (ADDR_BITS + 3) // 4
    for w in range(DEPTH):
        v = overrides.get(w, 0) & ((1 << WIDTH) - 1)
        lines.append(f"  {w:0{hex_addr}X} : {v:0{hex_width}X};")
    lines.append("END;")
    return "\n".join(lines) + "\n"


def gen_verilog() -> str:
    addr_bus = ", ".join(f"addr{i}" for i in range(ADDR_BITS - 1, -1, -1))
    din_bus  = ", ".join(f"din{i}"  for i in range(WIDTH - 1, -1, -1))
    dout_bus = ", ".join(f"dout{i}" for i in range(WIDTH - 1, -1, -1))
    ports_in = (
        ["input clk", "input wren"]
        + [f"input addr{i}" for i in range(ADDR_BITS)]
        + [f"input din{i}"  for i in range(WIDTH)]
    )
    ports_out = [f"output dout{i}" for i in range(WIDTH)]
    port_decl = ",\n    ".join(ports_in + ports_out)
    return f"""\
module fuzz_top(
    {port_decl}
);
    wire [{ADDR_BITS-1}:0] addr = {{{addr_bus}}};
    wire [{WIDTH-1}:0]     din  = {{{din_bus}}};
    wire [{WIDTH-1}:0]     dout;
    assign {{{dout_bus}}} = dout;

    altsyncram #(
        .operation_mode("SINGLE_PORT"),
        .width_a({WIDTH}), .widthad_a({ADDR_BITS}), .numwords_a({DEPTH}),
        .lpm_type("altsyncram"),
        .ram_block_type("M9K"),
        .outdata_reg_a("UNREGISTERED"),
        .init_file("m9k_init.mif"),
        .intended_device_family("{FAMILY}")
    ) u (
        .clock0(clk), .address_a(addr), .data_a(din),
        .wren_a(wren), .q_a(dout),
        .aclr0(1'b0), .aclr1(1'b0),
        .addressstall_a(1'b0), .addressstall_b(1'b0),
        .byteena_a(1'b1), .byteena_b(1'b1),
        .address_b({{{ADDR_BITS}{{1'b0}}}}), .data_b({{{WIDTH}{{1'b0}}}}),
        .clock1(1'b1), .clocken0(1'b1), .clocken1(1'b1),
        .clocken2(1'b1), .clocken3(1'b1), .eccstatus(),
        .q_b(), .rden_a(1'b1), .rden_b(1'b1), .wren_b(1'b0)
    );
endmodule
"""


def gen_qsf() -> str:
    lines = [
        f'set_global_assignment -name FAMILY "{FAMILY}"',
        f'set_global_assignment -name DEVICE {DEVICE}',
        'set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top',
        'set_global_assignment -name VERILOG_FILE fuzz_top.v',
        'set_global_assignment -name MIF_FILE m9k_init.mif',
        'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files',
    ]
    for sig, pin in PINS.items():
        lines.append(f'set_location_assignment {pin} -to {sig}')
    lines.append(f'set_location_assignment {M9K_LOC} -to "{M9K_NODE}"')
    return "\n".join(lines) + "\n"


def build(tag: str, overrides: dict[int, int] | None = None,
          rbf_output: str | None = None) -> tuple[str | None, float, str]:
    """Compile one M9K with the given init overrides. Returns
    (rbf_path, elapsed_seconds, error_message)."""
    verilog = gen_verilog()
    qsf     = gen_qsf()
    mif     = gen_mif(overrides)

    proj_dir = setup_project(tag, verilog, qsf)
    with open(os.path.join(proj_dir, "m9k_init.mif"), "w") as f:
        f.write(mif)
    with open(os.path.join(proj_dir, f"{tag}.qpf"), "w") as f:
        f.write(f'PROJECT_REVISION = "{tag}"\n')

    t0 = time.time()
    ok, elapsed, err = compile_full(tag, proj_dir)
    if not ok:
        return None, elapsed, err

    rbf = generate_rbf(tag, proj_dir, rbf_output)
    if rbf is None:
        return None, elapsed, "RBF generation failed"
    return rbf, elapsed, ""


if __name__ == "__main__":
    # Smoke test: one zero-init compile, report cell count in the
    # 1692-1738 non-LAB band + total CRAM band, and elapsed time.
    tag = "m9k_init_smoke"
    out = os.path.join(RBF_DIR, f"{tag}.rbf")
    rbf, t, err = build(tag, overrides=None, rbf_output=out)
    if rbf is None:
        print(f"compile FAIL ({t:.1f}s): {err[:400]}")
        sys.exit(1)
    print(f"compile OK ({t:.1f}s) -> {out}")
    size = os.path.getsize(rbf)
    print(f"rbf size: {size} bytes (expect 368,011)")
