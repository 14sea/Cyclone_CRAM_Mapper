#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate / derive the SP 36×256 INIT formula at X15_Y10_N0.

The current `M9K_INIT_ANCHORS[("X15_Y10_N0", 36, 256)] = (120028, 4)` is
extrapolated from 9×512.  9×1024 calibration showed the formula does
NOT extend across depth changes (9×1024 is 4 words/frame, not 2).
36-bit width is structurally different again — 4× wider words, ¼× depth.

Probes (SP mode, XOR-fold to keep all 36 bits):
  - allzero baseline
  - w=0 bit=0/35   → frame layout, bit-stride
  - w=1 bit=0      → word-stride
  - w=255 bit=0    → boundary check
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
WIDTH, DEPTH = 36, 256

PINS = {
    "CLK":  "PIN_E1",
    "KEY2": "PIN_E16",
    "KEY3": "PIN_M16",
    "LED0": "PIN_G15",
}


def _verilog() -> str:
    return """\
module m9k_sp(
    input  wire CLK,
    input  wire KEY2,
    input  wire KEY3,
    output wire LED0
);
    reg [27:0] counter = 28'd0;
    always @(posedge CLK) counter <= counter + 1'b1;
    wire [7:0]  addr = counter[27 -: 8];
    wire [35:0] din  = {36{KEY3}};
    wire        we   = ~KEY2;
    wire [35:0] dout;
    reg  [35:0] dout_r;
    always @(posedge CLK) dout_r <= dout;
    assign LED0 = ^dout_r;
    altsyncram #(
        .operation_mode("SINGLE_PORT"),
        .width_a(36), .widthad_a(8), .numwords_a(256),
        .width_byteena_a(1),
        .lpm_type("altsyncram"),
        .ram_block_type("M9K"),
        .outdata_reg_a("UNREGISTERED"),
        .read_during_write_mode_port_a("DONT_CARE"),
        .clock_enable_input_a("NORMAL"),
        .clock_enable_output_a("NORMAL"),
        .init_file("mem_init.mif"),
        .intended_device_family("Cyclone IV E")
    ) u (
        .clock0(CLK),
        .address_a(addr), .data_a(din), .wren_a(we),
        .q_a(dout),
        .aclr0(1'b0), .aclr1(1'b0),
        .addressstall_a(1'b0),
        .byteena_a(1'b1),
        .clock1(1'b1), .clocken0(1'b1), .clocken1(1'b1),
        .clocken2(1'b1), .clocken3(1'b1), .eccstatus(),
        .address_b(8'b0), .data_b(36'b0),
        .rden_a(1'b1), .rden_b(1'b0), .wren_b(1'b0),
        .q_b(), .addressstall_b(1'b0), .byteena_b(1'b1)
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
        lines.append(f"  {i:02X} : {v:09X};")  # 36 bits = 9 hex chars
    lines.append("END;")
    return "\n".join(lines) + "\n"


def _qsf() -> str:
    lines = [
        'set_global_assignment -name FAMILY "Cyclone IV E"',
        "set_global_assignment -name DEVICE EP4CE6F17C8",
        "set_global_assignment -name TOP_LEVEL_ENTITY m9k_sp",
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
        mif = _mif(hot_word=-1, hot_value=0)
    else:
        mif = _mif(hot_word=hot_word, hot_value=hot_value)
    (Path(proj_dir) / "mem_init.mif").write_text(mif)

    rbf_path = work / f"{tag}.rbf"
    if rbf_path.exists():
        print(f"  [{tag}] RBF exists, skipping")
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
    base_rbf = build(f"sp_36x256_allzero_{suffix}", hot_word=None, hot_value=0)

    probes = [(0, 0), (0, 35), (1, 0), (255, 0),
              (0, 1), (0, 18),
              # Full bit-order mapping at w=0 (need all 36 to be sure)
              *[(0, b) for b in range(2, 18)],
              *[(0, b) for b in range(19, 35)]]
    results: dict = {"site": suffix, "probes": {}}

    for w, bit in probes:
        tag   = f"sp_36x256_w{w}_b{bit}_{suffix}"
        probe = build(tag, hot_word=w, hot_value=(1 << bit))
        cells = diff_cells(probe, base_rbf)
        print(f"\n[w={w}, bit={bit}] {len(cells)} cells:")
        for off, fi, bif, bp in cells:
            print(f"    off={off:6d}  frame={fi:4d}  bif={bif:3d}  bp={bp}")
        results["probes"][f"w{w}_b{bit}"] = [
            {"offset": o, "frame": f, "bif": b, "bp": p} for o, f, b, p in cells
        ]

    # Full-bit probe at w=0: all 36 bits set → reveals all bit positions at once.
    full_tag = f"sp_36x256_w0_full_{suffix}"
    full = build(full_tag, hot_word=0, hot_value=0xFFFFFFFFF)
    cells = diff_cells(full, base_rbf)
    print(f"\n[w=0, all 36 bits] {len(cells)} cells:")
    for off, fi, bif, bp in sorted(cells, key=lambda c: (c[1], c[2])):
        print(f"    off={off:6d}  frame={fi:4d}  bif={bif:3d}  bp={bp}")
    results["probes"]["w0_full"] = [
        {"offset": o, "frame": f, "bif": b, "bp": p} for o, f, b, p in cells
    ]

    out = ROOT / "results" / "sp_36x256_init_map.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
