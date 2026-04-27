# SPDX-License-Identifier: GPL-3.0-or-later
"""Derive the SDP 4×2048 INIT word→cell mapping.

Builds 8 Quartus probes at X15_Y10_N0 SDP 4×2048, each with exactly
one word set to 0xF (all others 0), diffed against the allzero build.
The single changed cell per probe reveals which (frame, byte_in_frame, bp)
encodes that word's bit 0.

Words probed: 1024..1031 (the first 8 high-half words; they cover all 8
byte positions within the base frame, one per probe).

Output: prints the formula and optionally writes results to
results/sdp_4x2048_init_word_map.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))
from compile import setup_project, compile_full, generate_rbf

WORK_ROOT = ROOT / "tmp"
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

ALLZERO_RBF = (ROOT / "tmp" /
               "m9k_sdp_blink_4x2048_allzero_X15_Y10_N0" /
               "m9k_sdp_blink_4x2048_allzero_X15_Y10_N0.rbf")


def _verilog() -> str:
    # Same SDP blink as m9k_sdp_blink_build.py — MIF drives LED via port B.
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
    assign LED0 = dout_r[0];
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


def _mif_single(hot_word: int) -> str:
    lines = [
        f"DEPTH = {DEPTH};", f"WIDTH = {WIDTH};",
        "ADDRESS_RADIX = HEX;", "DATA_RADIX = HEX;",
        "CONTENT BEGIN",
    ]
    for i in range(DEPTH):
        v = 0xF if i == hot_word else 0x0
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


def build_probe(hot_word: int) -> Path:
    tag   = f"sdp_init_probe_w{hot_word}_X{SITE_X}_Y{SITE_Y}_N{SITE_N}"
    work  = WORK_ROOT / tag
    work.mkdir(parents=True, exist_ok=True)
    proj_dir = setup_project(tag, _verilog(), _qsf(), str(work))
    (Path(proj_dir) / "mem_init.mif").write_text(_mif_single(hot_word))
    ok, el, err = compile_full(tag, proj_dir, timeout=300)
    if not ok:
        raise RuntimeError(f"probe w{hot_word} FAIL ({el:.1f}s): {err}")
    rbf = generate_rbf(tag, proj_dir, str(work / f"{tag}.rbf"))
    if rbf is None:
        raise RuntimeError(f"RBF generation failed for w{hot_word}")
    return Path(rbf)


def analyse(probe_rbf: Path, zero_rbf: Path) -> list[tuple[int, int, int]]:
    """Return list of (offset, byte_in_frame, bp) cells that differ."""
    probe = probe_rbf.read_bytes()
    zero  = zero_rbf.read_bytes()
    cells = []
    for i, (a, b) in enumerate(zip(probe, zero)):
        x = a ^ b
        for bp in range(8):
            if x & (1 << bp):
                fi  = (i - PREAMBLE) // FRAME_SIZE
                bif = (i - PREAMBLE) % FRAME_SIZE
                if fi >= 25 and bif not in (208, 209):  # skip header + CRC
                    cells.append((i, bif, bp))
    return cells


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true",
                    help="Run Quartus for all 8 probes (skips if RBF exists)")
    ap.add_argument("--words", default="1024-1031",
                    help="Word range to probe, e.g. 1024-1031")
    args = ap.parse_args()

    lo, hi = (int(v) for v in args.words.split("-"))
    probe_words = list(range(lo, hi + 1))

    if not ALLZERO_RBF.exists():
        sys.exit(f"all-zero RBF not found: {ALLZERO_RBF}\n"
                 "Run: python3 scripts/m9k_sdp_init_calib.py --build")

    results = {}  # word → {offset, frame, bif, bp}

    for w in probe_words:
        tag = f"sdp_init_probe_w{w}_X{SITE_X}_Y{SITE_Y}_N{SITE_N}"
        rbf = WORK_ROOT / tag / f"{tag}.rbf"

        if not rbf.exists():
            if not args.build:
                print(f"  w{w}: RBF not found, skipping (use --build)")
                continue
            print(f"  building probe for w={w} ...", flush=True)
            try:
                rbf = build_probe(w)
            except Exception as e:
                print(f"  w{w}: BUILD FAIL: {e}")
                continue

        cells = analyse(rbf, ALLZERO_RBF)
        if len(cells) != 1:
            print(f"  w{w}: WARNING — expected 1 INIT cell, got {len(cells)}: {cells}")
            if cells:
                results[w] = {"offset": cells[0][0], "bif": cells[0][1], "bp": cells[0][2],
                              "ambiguous": True}
        else:
            off, bif, bp = cells[0]
            fi = (off - PREAMBLE) // FRAME_SIZE
            print(f"  w{w}: offset={off} frame={fi} bif={bif} bp={bp}")
            results[w] = {"offset": off, "frame": fi, "bif": bif, "bp": bp}

    if not results:
        print("No results — run with --build")
        return

    # Derive the formula
    print("\n--- Formula derivation ---")
    # Expected: frame = BASE_FRAME + w // 8 for all probed words
    frames = {w: d["frame"] for w, d in results.items() if "frame" in d}
    bifs   = {w: d["bif"]   for w, d in results.items() if "frame" in d}

    if frames:
        base_frames = {w: f - w // 8 for w, f in frames.items()}
        base_frame_vals = set(base_frames.values())
        print(f"BASE_FRAME candidates: {base_frame_vals}")

        bif_order = [bifs[w] for w in sorted(bifs.keys())]
        print(f"SDP_4x2048_BYTES order (w%8=0..7): {bif_order}")
        print(f"bp values: {set(d['bp'] for d in results.values())}")

    # Save
    out = ROOT / "results" / "sdp_4x2048_init_word_map.json"
    out.write_text(json.dumps({str(w): d for w, d in results.items()}, indent=2))
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
