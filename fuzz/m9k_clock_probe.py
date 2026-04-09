# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.2 T4 — M9K clock-net configuration probe.

Phase 5.0 locked DSPMULT_CLOCK_ENABLE = (209891, bp 4) and noted
that M9K has 4 clock-config cells adjacent to it in frames
~1007-1013 (1-3 byte gap, same bp). This probe varies the M9K
clock-net wiring at the altsyncram parameter level and diffs
against a fully-enabled baseline, targeting those frames.

Variants (4-6 compiles, parallel):
  base:     clocken0=1, clocken1=1, rden_a=1, single-clock
  no_cken0: clocken0=1'b0 (disables M9K input clock enable)
  no_cken1: clocken1=1'b0 (disables output-register clock enable)
  no_rden:  rden_a=1'b0  (disables read port)
  dual_clk: clock1 bound to a separate pin (dual-clock mode)
  no_out:   outdata_reg_a="CLOCK0" instead of "UNREGISTERED"
            (enables output register, should light the clock-net
             bit for the output register clock)

Each variant shares the same LOC, init file, width/depth with the
harness baseline so only the clock-config axis varies. CRAM-only
diff, focused on the Phase 5.0 clock-net band frames 1005..1015.
"""
import os, sys, json, time
from concurrent.futures import ProcessPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compile import setup_project, compile_full, generate_rbf
from m9k_init_harness import (
    FAMILY, DEVICE, M9K_LOC, M9K_NODE, WIDTH, DEPTH, ADDR_BITS, PINS,
    gen_mif,
)
from m9k_init_null import cram_cells, block_band_cells, FRAME_SIZE
from config import RBF_DIR

# Phase 5.0 clock-net band (discovered via mult_reg_sweep).
CLOCK_FRAMES = range(1005, 1016)


# A second clock pin for dual-clock variant. Pick one that is not
# already in m9k_init_harness.PINS.
CLOCK1_PIN = "PIN_F15"


def verilog(variant: str) -> str:
    cken0 = "1'b1"
    cken1 = "1'b1"
    rden  = "1'b1"
    outreg = "UNREGISTERED"
    clock1_port = "1'b1"
    extra_in = ""

    if variant == "no_cken0":
        cken0 = "1'b0"
    elif variant == "no_cken1":
        cken1 = "1'b0"
    elif variant == "no_rden":
        rden = "1'b0"
    elif variant == "dual_clk":
        clock1_port = "clk1"
        extra_in = ", input clk1"
    elif variant == "out_reg":
        outreg = "CLOCK0"

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
    {port_decl}{extra_in}
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
        .outdata_reg_a("{outreg}"),
        .init_file("m9k_init.mif"),
        .intended_device_family("{FAMILY}")
    ) u (
        .clock0(clk), .address_a(addr), .data_a(din),
        .wren_a(wren), .q_a(dout),
        .aclr0(1'b0), .aclr1(1'b0),
        .addressstall_a(1'b0), .addressstall_b(1'b0),
        .byteena_a(1'b1), .byteena_b(1'b1),
        .address_b({{{ADDR_BITS}{{1'b0}}}}), .data_b({{{WIDTH}{{1'b0}}}}),
        .clock1({clock1_port}), .clocken0({cken0}), .clocken1({cken1}),
        .clocken2(1'b1), .clocken3(1'b1), .eccstatus(),
        .q_b(), .rden_a({rden}), .rden_b(1'b1), .wren_b(1'b0)
    );
endmodule
"""


def gen_qsf(variant: str) -> str:
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
    if variant == "dual_clk":
        lines.append(f'set_location_assignment {CLOCK1_PIN} -to clk1')
    lines.append(f'set_location_assignment {M9K_LOC} -to "{M9K_NODE}"')
    return "\n".join(lines) + "\n"


def build(variant: str):
    tag = f"m9k_clk_{variant}"
    proj_dir = setup_project(tag, verilog(variant), gen_qsf(variant))
    with open(os.path.join(proj_dir, "m9k_init.mif"), "w") as f:
        f.write(gen_mif(None))
    with open(os.path.join(proj_dir, f"{tag}.qpf"), "w") as f:
        f.write(f'PROJECT_REVISION = "{tag}"\n')
    out = os.path.join(RBF_DIR, f"{tag}.rbf")
    ok, elapsed, err = compile_full(tag, proj_dir)
    if not ok:
        return variant, None, elapsed, err
    rbf = generate_rbf(tag, proj_dir, out)
    return variant, rbf, elapsed, ""


def clock_band_cells(cells):
    return [c for c in cells
            if ((c[0] - 32) // FRAME_SIZE) in CLOCK_FRAMES]


def main():
    variants = ["base", "no_cken0", "no_cken1", "no_rden", "dual_clk", "out_reg"]
    timings = {}
    print(f"dispatching {len(variants)} clock-config compiles...")
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(build, v): v for v in variants}
        for f in as_completed(futs):
            v, rbf, t, err = f.result()
            timings[v] = t
            if rbf is None:
                print(f"  {v:10s} FAIL ({t:.1f}s): {err[:200]}")
            else:
                print(f"  {v:10s} OK   ({t:.1f}s)")
    print(f"total wall: {time.time()-t0:.1f}s\n")

    base_p = os.path.join(RBF_DIR, "m9k_clk_base.rbf")
    if not os.path.exists(base_p):
        print("base failed — abort")
        return
    base = open(base_p, "rb").read()

    print("=== diffs vs base (CRAM-only / clock band 1005-1015 / block band 1692-1738) ===")
    results = {}
    for v in variants:
        if v == "base":
            continue
        p = os.path.join(RBF_DIR, f"m9k_clk_{v}.rbf")
        if not os.path.exists(p):
            continue
        other = open(p, "rb").read()
        all_cells = cram_cells(base, other)
        clk = clock_band_cells(all_cells)
        blk = block_band_cells(all_cells)
        print(f"  {v:10s}: {len(all_cells):5} cram  /  "
              f"{len(clk):3} clock-band  /  {len(blk):3} block-band")
        if clk:
            for c in clk[:6]:
                print(f"      clk cell: ({c[0]},{c[1]})  "
                      f"frame={((c[0]-32)//FRAME_SIZE)} "
                      f"offset_in_frame={(c[0]-32)%FRAME_SIZE}")
        results[v] = {
            "all_cram": all_cells,
            "clock_band": clk,
            "block_band": blk,
        }

    os.makedirs("results", exist_ok=True)
    with open("results/m9k_clock_probe.json", "w") as f:
        json.dump({
            "timings": timings,
            "clock_frames": list(CLOCK_FRAMES),
            "results": {
                k: {"all_cram": v["all_cram"],
                    "clock_band": v["clock_band"],
                    "block_band": v["block_band"]}
                for k, v in results.items()
            },
        }, f, indent=1, default=list)
    print("\narchived results/m9k_clock_probe.json")


if __name__ == "__main__":
    main()
