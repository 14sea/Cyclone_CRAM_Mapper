#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Derive SDP 4×2048 INIT bit-1/2/3 CRAM positions at X15_Y10_N0.

The original calibration (`m9k_sdp_init_word_probe.py`) used
LED0=dout_r[0], so Quartus optimized away bits 1-3 — only bit 0 cells
were visible in CRAM.  This probe uses LED0=^dout_r (XOR-fold of all 4
bits), forcing Quartus to keep every bit.

Probes at X15_Y10_N0:
  - allzero_xor: MIF=allzero (new baseline for the XOR design)
  - probe_w1024_b{0,1,2,3}: MIF has only word 1024 set to (1<<bit), all else 0
  - probe_w1029_b1: stride sanity probe (w%8=5; bif should follow same w-formula
    as bit 0, just at the bit-1 byte position)

Output: results/sdp_4x2048_init_bit_map.json mapping (word, bit) → cell.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))
from compile import setup_project, compile_full, generate_rbf

WORK_ROOT  = ROOT / "tmp"
FRAME_SIZE = 210
PREAMBLE   = 32

SITE_X, SITE_Y, SITE_N = 15, 10, 0
WIDTH, DEPTH = 4, 2048

PINS = {
    "CLK":  "PIN_E1",
    "KEY2": "PIN_E16",
    "KEY3": "PIN_M16",
    "LED0": "PIN_G15",
}


def _verilog() -> str:
    # XOR-fold all 4 dout bits → Quartus must keep them in CRAM.
    return """\
module m9k_sdp_blink(
    input  wire CLK,
    input  wire KEY2,
    input  wire KEY3,
    output wire LED0
);
    reg [27:0] counter = 28'd0;
    always @(posedge CLK) counter <= counter + 1'b1;
    wire [10:0] addrr = counter[27 -: 11];
    wire [10:0] addrw = counter[10:0];
    wire [3:0]  din_w = {4{KEY3}};
    wire        we_w  = ~KEY2;
    wire [3:0] dout_b;
    reg  [3:0] dout_r;
    always @(posedge CLK) dout_r <= dout_b;
    assign LED0 = ^dout_r;
    altsyncram #(
        .operation_mode("DUAL_PORT"),
        .width_a(4), .widthad_a(11), .numwords_a(2048),
        .width_b(4), .widthad_b(11), .numwords_b(2048),
        .lpm_type("altsyncram"),
        .ram_block_type("M9K"),
        .address_reg_b("CLOCK0"),
        .outdata_reg_b("UNREGISTERED"),
        .read_during_write_mode_mixed_ports("OLD_DATA"),
        .clock_enable_input_a("NORMAL"),
        .clock_enable_input_b("NORMAL"),
        .clock_enable_output_a("NORMAL"),
        .clock_enable_output_b("NORMAL"),
        .init_file("mem_init.mif"),
        .intended_device_family("Cyclone IV E")
    ) u (
        .clock0(CLK),
        .address_a(addrw), .data_a(din_w), .wren_a(we_w),
        .address_b(addrr), .q_b(dout_b),
        .aclr0(1'b0), .aclr1(1'b0),
        .addressstall_a(1'b0), .addressstall_b(1'b0),
        .byteena_a(1'b1), .byteena_b(1'b1),
        .clock1(1'b1), .clocken0(1'b1), .clocken1(1'b1),
        .clocken2(1'b1), .clocken3(1'b1), .eccstatus(),
        .data_b(4'b0), .q_a(),
        .rden_a(1'b1), .rden_b(1'b1), .wren_b(1'b0)
    );
endmodule
"""


def _mif(hot_word: int, hot_value: int) -> str:
    lines = [
        f"DEPTH = {DEPTH};", f"WIDTH = {WIDTH};",
        "ADDRESS_RADIX = HEX;", "DATA_RADIX = HEX;",
        "CONTENT BEGIN",
    ]
    for i in range(DEPTH):
        v = hot_value if i == hot_word else 0
        lines.append(f"  {i:03X} : {v:X};")
    lines.append("END;")
    return "\n".join(lines) + "\n"


def _qsf() -> str:
    lines = [
        'set_global_assignment -name FAMILY "Cyclone IV E"',
        "set_global_assignment -name DEVICE EP4CE6F17C8",
        "set_global_assignment -name TOP_LEVEL_ENTITY m9k_sdp_blink",
        "set_global_assignment -name VERILOG_FILE fuzz_top.v",
        "set_global_assignment -name MIF_FILE mem_init.mif",
        "set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files",
        'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"',
        "set_global_assignment -name SEED 1",
    ]
    for sig, pin in PINS.items():
        lines.append(f"set_location_assignment {pin} -to {sig}")
    lines.append(
        f'set_location_assignment M9K_X{SITE_X}_Y{SITE_Y}_N{SITE_N} -to "u"'
    )
    return "\n".join(lines) + "\n"


def build(tag: str, hot_word: int | None, hot_value: int) -> Path:
    work = WORK_ROOT / tag
    work.mkdir(parents=True, exist_ok=True)
    proj_dir = setup_project(tag, _verilog(), _qsf(), str(work))

    if hot_word is None:
        # allzero baseline
        mif = _mif(hot_word=-1, hot_value=0)
    else:
        mif = _mif(hot_word=hot_word, hot_value=hot_value)
    (Path(proj_dir) / "mem_init.mif").write_text(mif)

    rbf_path = work / f"{tag}.rbf"
    if rbf_path.exists():
        print(f"  [{tag}] RBF exists, skipping build")
        return rbf_path

    print(f"  [{tag}] building Quartus probe ...", flush=True)
    ok, el, err = compile_full(tag, proj_dir, timeout=300)
    if not ok:
        raise RuntimeError(f"{tag} FAIL ({el:.1f}s): {err}")
    rbf = generate_rbf(tag, proj_dir, str(rbf_path))
    if rbf is None:
        raise RuntimeError(f"RBF gen FAIL for {tag}")
    return Path(rbf)


def diff_cells(probe_rbf: Path, base_rbf: Path) -> list[tuple[int, int, int, int]]:
    """Return list of (offset, frame, bif, bp) cells that differ."""
    probe = probe_rbf.read_bytes()
    base  = base_rbf.read_bytes()
    cells = []
    for i, (a, b) in enumerate(zip(probe, base)):
        x = a ^ b
        for bp in range(8):
            if x & (1 << bp):
                fi  = (i - PREAMBLE) // FRAME_SIZE
                bif = (i - PREAMBLE) % FRAME_SIZE
                if fi >= 25 and bif not in (208, 209):
                    cells.append((i, fi, bif, bp))
    return cells


def main() -> None:
    suffix = f"X{SITE_X}_Y{SITE_Y}_N{SITE_N}"

    # Build allzero baseline for the XOR design.
    base_tag = f"sdp_init_xor_allzero_{suffix}"
    base_rbf = build(base_tag, hot_word=None, hot_value=0)

    # Probe each bit at w=1024.
    results: dict = {"site": suffix, "design": "LED0=^dout_r", "probes": {}}
    for bit in range(4):
        tag = f"sdp_init_xor_w1024_b{bit}_{suffix}"
        probe = build(tag, hot_word=1024, hot_value=(1 << bit))
        cells = diff_cells(probe, base_rbf)
        print(f"\n[w=1024, bit={bit}] {len(cells)} differing cells:")
        for off, fi, bif, bp in cells:
            print(f"    off={off:6d}  frame={fi:4d}  bif={bif:3d}  bp={bp}")
        results["probes"][f"w1024_b{bit}"] = [
            {"offset": off, "frame": fi, "bif": bif, "bp": bp}
            for off, fi, bif, bp in cells
        ]

    # Stride sanity probe: w=1029, bit=1.  Should land at frame=699, same as
    # bit-1 of w=1024 (since 1024 and 1029 share frame 699 — w//8=128 for both).
    stride_tag = f"sdp_init_xor_w1029_b1_{suffix}"
    stride = build(stride_tag, hot_word=1029, hot_value=0x2)
    cells = diff_cells(stride, base_rbf)
    print(f"\n[w=1029, bit=1] {len(cells)} differing cells:")
    for off, fi, bif, bp in cells:
        print(f"    off={off:6d}  frame={fi:4d}  bif={bif:3d}  bp={bp}")
    results["probes"]["w1029_b1"] = [
        {"offset": off, "frame": fi, "bif": bif, "bp": bp}
        for off, fi, bif, bp in cells
    ]

    out = ROOT / "results" / "sdp_4x2048_init_bit_map.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nSaved: {out}")

    # Summary
    print("\n--- Bit→bif at w=1024 ---")
    for bit in range(4):
        cells = results["probes"][f"w1024_b{bit}"]
        if len(cells) == 1:
            c = cells[0]
            print(f"  bit{bit}: bif={c['bif']:3d}  bp={c['bp']}  frame={c['frame']}")
        else:
            print(f"  bit{bit}: {len(cells)} cells (UNEXPECTED)")


if __name__ == "__main__":
    main()
