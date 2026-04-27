#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate the extrapolated SP 9×1024 INIT formula at X15_Y10_N0.

The current `M9K_INIT_ANCHORS[("X15_Y10_N0", 9, 1024)] = (120028, 4)` was
copied from the 9×512 calibration without independent probing.  The 9×512
formula is `byte = anchor + (w//2)*210 - (w%2) - 2*bit`; this script
checks whether the same formula extends to 1024 words.

Probes (SP mode, XOR-fold to keep all 9 bits):
  - allzero baseline
  - w=2,    bit=0  → predicted byte = anchor + 210 = 120238
  - w=512,  bit=0  → predicted byte = anchor + 256*210 = 173788
  - w=1023, bit=0  → predicted byte = anchor + 511*210 - 1 = 227337

If all three probes produce a single-cell diff at the predicted offset,
the formula extends to depth=1024 and the ⚠️ in m9k_init_basis.py can
be removed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))
from compile import setup_project, compile_full, generate_rbf
from m9k_init_basis import M9K_INIT_ANCHORS, init_cell

WORK_ROOT  = ROOT / "tmp"
FRAME_SIZE = 210
PREAMBLE   = 32

SITE_X, SITE_Y, SITE_N = 15, 10, 0
WIDTH, DEPTH = 9, 1024

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
    wire [9:0] addr_r = counter[27 -: 10];
    wire [9:0] addr_w = counter[9:0];
    wire [8:0] din    = {9{KEY3}};
    wire       we     = ~KEY2;
    wire [8:0] dout;
    reg  [8:0] dout_r;
    always @(posedge CLK) dout_r <= dout;
    assign LED0 = ^dout_r;
    altsyncram #(
        .operation_mode("SINGLE_PORT"),
        .width_a(9), .widthad_a(10), .numwords_a(1024),
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
        .address_a(addr_r), .data_a(din), .wren_a(we),
        .q_a(dout),
        .aclr0(1'b0), .aclr1(1'b0),
        .addressstall_a(1'b0),
        .byteena_a(1'b1),
        .clock1(1'b1), .clocken0(1'b1), .clocken1(1'b1),
        .clocken2(1'b1), .clocken3(1'b1), .eccstatus(),
        .address_b(10'b0), .data_b(9'b0),
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
        lines.append(f"  {i:03X} : {v:03X};")
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
    suffix  = f"X{SITE_X}_Y{SITE_Y}_N{SITE_N}"
    site    = suffix
    anchor, bp_expected = M9K_INIT_ANCHORS[(site, WIDTH, DEPTH)]
    print(f"Anchor (extrapolated): {anchor}, bp={bp_expected}")

    base_rbf = build(f"sp_9x1024_allzero_{suffix}", hot_word=None, hot_value=0)

    # Hypothesis: 4 words/frame (vs 9×512's 2 words/frame). Probe w%4=0,1,2,3
    # within frame 571 (base) plus boundary checks.
    probes = [(0, 0), (1, 0), (2, 0), (3, 0),  # w%4 in-frame mapping
              (4, 0),                            # next frame, w%4=0
              (1023, 0),                         # boundary
              (0, 8), (1, 4), (3, 8)]            # bit-stride verification
    results: dict = {"site": site, "anchor": anchor, "bp": bp_expected, "probes": {}}

    for w, bit in probes:
        tag   = f"sp_9x1024_w{w}_b{bit}_{suffix}"
        probe = build(tag, hot_word=w, hot_value=(1 << bit))
        cells = diff_cells(probe, base_rbf)
        pred_byte, pred_bp = init_cell(anchor, w, bit, bp=bp_expected)
        pred_frame = (pred_byte - PREAMBLE) // FRAME_SIZE
        pred_bif   = (pred_byte - PREAMBLE) % FRAME_SIZE
        print(f"\n[w={w}, bit={bit}] predicted: off={pred_byte} frame={pred_frame} bif={pred_bif} bp={pred_bp}")
        print(f"  observed: {len(cells)} cells")
        for off, fi, bif, bp in cells:
            tag2 = "MATCH" if (off == pred_byte and bp == pred_bp) else "MISMATCH"
            print(f"    off={off:6d}  frame={fi:4d}  bif={bif:3d}  bp={bp}  [{tag2}]")
        results["probes"][f"w{w}_b{bit}"] = {
            "predicted": {"offset": pred_byte, "frame": pred_frame, "bif": pred_bif, "bp": pred_bp},
            "observed": [{"offset": o, "frame": f, "bif": b, "bp": p} for o, f, b, p in cells],
        }

    out = ROOT / "results" / "sp_9x1024_init_validation.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
