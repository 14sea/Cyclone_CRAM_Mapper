# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.2 T2.0 — ROM-vs-RAM falsification probe.

Question: is M9K ROM mode a distinct physical feature in the
bitstream, or just syntactic sugar for "SINGLE_PORT RAM with wren
tied low"? Answer determines whether T2 mode sweep needs 3 axes
(ram + width + depth) or 4 (add rom axis), and whether the FASM
directive should be ``MODE = ROM`` or ``WREN = 0``.

Three compiles, identical LOC / DEVICE / altsyncram shape, only
varying what is claimed here:

  A: SINGLE_PORT RAM, wren driven by a real input pin
  B: SINGLE_PORT RAM, wren tied to 1'b0 (synthesizer should kill
     the write path at fitter time)
  C: altsyncram operation_mode="ROM" (no wren/data_a ports)

Pair-diffs (CRAM-only, block-band 1692-1738):
  diff(A,B) = write-path cells (how many cells the wren signal
              owns — useful baseline for T2 proper)
  diff(B,C) = the answer. 0 = pure sugar, 1-5 = optimization
              tag bit, >20 = structural ROM mode

Outputs a one-line verdict so the tomorrow-morning launch sequence
can just grep the stdout.
"""
import os, sys, json, time
from concurrent.futures import ProcessPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compile import setup_project, compile_full, generate_rbf
from m9k_init_harness import (
    FAMILY, DEVICE, M9K_LOC, M9K_NODE, WIDTH, DEPTH, ADDR_BITS, PINS,
)
from m9k_init_null import cram_cells, block_band_cells
from config import RBF_DIR

# ----------------------------------------------------------------------
# Three variants. Identical everywhere except altsyncram instantiation
# and the wren port binding.
# ----------------------------------------------------------------------

def _port_decl(include_wren: bool):
    ports_in = ["input clk"]
    if include_wren:
        ports_in.append("input wren")
    ports_in += [f"input addr{i}" for i in range(ADDR_BITS)]
    ports_in += [f"input din{i}"  for i in range(WIDTH)]
    ports_out = [f"output dout{i}" for i in range(WIDTH)]
    return ",\n    ".join(ports_in + ports_out)


def _buses():
    addr_bus = ", ".join(f"addr{i}" for i in range(ADDR_BITS - 1, -1, -1))
    din_bus  = ", ".join(f"din{i}"  for i in range(WIDTH - 1, -1, -1))
    dout_bus = ", ".join(f"dout{i}" for i in range(WIDTH - 1, -1, -1))
    return addr_bus, din_bus, dout_bus


def verilog_ram(wren_tied_low: bool) -> str:
    """Variants A (wren driven) and B (wren tied to 1'b0).
    Both are SINGLE_PORT altsyncram with identical shape."""
    addr_bus, din_bus, dout_bus = _buses()
    include_wren_port = not wren_tied_low
    port_decl = _port_decl(include_wren_port)
    wren_expr = "1'b0" if wren_tied_low else "wren"
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
        .wren_a({wren_expr}), .q_a(dout),
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


def verilog_rom() -> str:
    """Variant C: altsyncram operation_mode="ROM". No wren/data_a
    ports exist in ROM mode. Same shape, same LOC, same init file."""
    addr_bus, _, dout_bus = _buses()
    ports_in = ["input clk"] + [f"input addr{i}" for i in range(ADDR_BITS)]
    ports_out = [f"output dout{i}" for i in range(WIDTH)]
    port_decl = ",\n    ".join(ports_in + ports_out)
    return f"""\
module fuzz_top(
    {port_decl}
);
    wire [{ADDR_BITS-1}:0] addr = {{{addr_bus}}};
    wire [{WIDTH-1}:0]     dout;
    assign {{{dout_bus}}} = dout;

    altsyncram #(
        .operation_mode("ROM"),
        .width_a({WIDTH}), .widthad_a({ADDR_BITS}), .numwords_a({DEPTH}),
        .lpm_type("altsyncram"),
        .ram_block_type("M9K"),
        .outdata_reg_a("UNREGISTERED"),
        .init_file("m9k_init.mif"),
        .intended_device_family("{FAMILY}")
    ) u (
        .clock0(clk), .address_a(addr),
        .q_a(dout),
        .aclr0(1'b0), .aclr1(1'b0),
        .addressstall_a(1'b0), .addressstall_b(1'b0),
        .clock1(1'b1), .clocken0(1'b1), .clocken1(1'b1),
        .clocken2(1'b1), .clocken3(1'b1), .eccstatus(),
        .q_b(), .rden_a(1'b1), .rden_b(1'b1)
    );
endmodule
"""


# ----------------------------------------------------------------------
# QSF — same pin bank for all three. Variant C has no `wren` port,
# so we only emit the wren pin assignment when the signal exists.
# ----------------------------------------------------------------------

def gen_qsf(has_wren: bool) -> str:
    lines = [
        f'set_global_assignment -name FAMILY "{FAMILY}"',
        f'set_global_assignment -name DEVICE {DEVICE}',
        'set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top',
        'set_global_assignment -name VERILOG_FILE fuzz_top.v',
        'set_global_assignment -name MIF_FILE m9k_init.mif',
        'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files',
    ]
    for sig, pin in PINS.items():
        if sig == "wren" and not has_wren:
            continue
        lines.append(f'set_location_assignment {pin} -to {sig}')
    lines.append(f'set_location_assignment {M9K_LOC} -to "{M9K_NODE}"')
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------
# Minimal zero-init MIF (same content for all three — ROM is
# stored SRAM too, it just lacks a write port).
# ----------------------------------------------------------------------

def gen_zero_mif() -> str:
    lines = [
        f"WIDTH = {WIDTH};",
        f"DEPTH = {DEPTH};",
        "ADDRESS_RADIX = HEX;",
        "DATA_RADIX = HEX;",
        "CONTENT BEGIN",
    ]
    hex_w = (WIDTH + 3) // 4
    hex_a = (ADDR_BITS + 3) // 4
    for w in range(DEPTH):
        lines.append(f"  {w:0{hex_a}X} : {0:0{hex_w}X};")
    lines.append("END;")
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------
# Build one variant
# ----------------------------------------------------------------------

def build_variant(spec):
    tag, verilog, qsf = spec
    proj_dir = setup_project(tag, verilog, qsf)
    with open(os.path.join(proj_dir, "m9k_init.mif"), "w") as f:
        f.write(gen_zero_mif())
    with open(os.path.join(proj_dir, f"{tag}.qpf"), "w") as f:
        f.write(f'PROJECT_REVISION = "{tag}"\n')
    out = os.path.join(RBF_DIR, f"{tag}.rbf")
    ok, elapsed, err = compile_full(tag, proj_dir)
    if not ok:
        return tag, None, elapsed, err
    rbf = generate_rbf(tag, proj_dir, out)
    return tag, rbf, elapsed, ""


def main():
    variants = [
        ("m9k_t20_A_ram_wren", verilog_ram(wren_tied_low=False), gen_qsf(has_wren=True)),
        ("m9k_t20_B_ram_tied", verilog_ram(wren_tied_low=True),  gen_qsf(has_wren=False)),
        ("m9k_t20_C_rom",      verilog_rom(),                    gen_qsf(has_wren=False)),
    ]

    print(f"dispatching 3 compiles (A/B/C) at {M9K_LOC}...")
    paths = {}
    timings = {}
    t_start = time.time()
    with ProcessPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(build_variant, v): v[0] for v in variants}
        for f in as_completed(futs):
            tag, rbf, t, err = f.result()
            timings[tag] = t
            if rbf is None:
                print(f"  {tag:24s} FAIL ({t:.1f}s): {err[:200]}")
            else:
                print(f"  {tag:24s} OK   ({t:.1f}s)")
                paths[tag] = rbf
    print(f"total wall: {time.time()-t_start:.1f}s\n")

    required = ["m9k_t20_A_ram_wren", "m9k_t20_B_ram_tied", "m9k_t20_C_rom"]
    missing = [t for t in required if t not in paths]
    if missing:
        print(f"missing compiles: {missing} — abort")
        return

    blobs = {t: open(paths[t], "rb").read() for t in required}

    def diff(a, b):
        c = cram_cells(blobs[a], blobs[b])
        return c, block_band_cells(c)

    ab_all, ab_block = diff("m9k_t20_A_ram_wren", "m9k_t20_B_ram_tied")
    bc_all, bc_block = diff("m9k_t20_B_ram_tied", "m9k_t20_C_rom")
    ac_all, ac_block = diff("m9k_t20_A_ram_wren", "m9k_t20_C_rom")

    print("=== pair-diff (CRAM-only / block-band 1692-1738) ===")
    print(f"  diff(A,B) = write-path cells    : {len(ab_all):5d} all  /  {len(ab_block):3d} block-band")
    print(f"  diff(B,C) = ROM-vs-tied-wren    : {len(bc_all):5d} all  /  {len(bc_block):3d} block-band")
    print(f"  diff(A,C) = ROM-vs-driven-wren  : {len(ac_all):5d} all  /  {len(ac_block):3d} block-band")

    # Verdict on diff(B,C) in the block band
    n = len(bc_block)
    if n == 0:
        verdict = "PURE_SUGAR"
        summary = ("ROM is pure RAM-sugar (wren=0). T2 sweep stays 3-axis "
                   "(op_mode × width × depth). FASM directive: WREN = 0.")
    elif 1 <= n <= 5:
        verdict = "OPTIMIZATION_TAG"
        summary = (f"ROM carries a {n}-cell optimization tag. T2 sweep "
                   "stays 3-axis; expose ROM as an optional ROM_FLAG in "
                   "addition to WREN = 0. Record tag cells in M9K_ROM_TAG.")
    elif n <= 20:
        verdict = "YELLOW"
        summary = (f"{n} cells differ — between tag and structural. "
                   "Investigate cell locations before committing T2 shape.")
    else:
        verdict = "STRUCTURAL_ROM"
        summary = (f"{n} cells in block band — ROM is a structurally "
                   "distinct mode. T2 sweep upgrades to 4 axes with ROM "
                   "as an independent operation_mode. FASM directive: "
                   "MODE = ROM.")

    print()
    print(f"=== VERDICT: {verdict} ===")
    print(f"Conclusion: {summary}")

    os.makedirs("results", exist_ok=True)
    with open("results/m9k_mode_t20_probe.json", "w") as f:
        json.dump({
            "timings": timings,
            "diff_AB": {"all": ab_all, "block_band": ab_block},
            "diff_BC": {"all": bc_all, "block_band": bc_block},
            "diff_AC": {"all": ac_all, "block_band": ac_block},
            "verdict": verdict,
            "summary": summary,
        }, f, indent=1, default=list)
    print("\narchived results/m9k_mode_t20_probe.json")


if __name__ == "__main__":
    main()
