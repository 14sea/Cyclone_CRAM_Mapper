#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""SP 9×512 cross-site silicon stripe-pattern audit.

The SP 9×512 codec (`write_init` with anchor + bp from M9K_INIT_ANCHORS)
covers 33 sites via per-site Quartus-probed anchors.  Only X15_Y10_N0
has been silicon-validated with a stripe-pattern flash (the rest are
Quartus-probe only).

This script builds a Quartus allzero SP 9×512 design at the requested
site, applies a codec stripe-pattern, and flashes to AX301 to confirm
silicon correctness via blink rate.

Usage:
  python3 scripts/m9k_sp_9x512_silicon_test.py X15_Y16_N0          # build only
  python3 scripts/m9k_sp_9x512_silicon_test.py X15_Y16_N0 --flash  # build + flash
  python3 scripts/m9k_sp_9x512_silicon_test.py X15_Y16_N0 --stripe 32 --flash

Design: addr_r = counter[27:18] sweeps 0..1023 wrapping into 512 words at
~5.24 ms/word ⇒ each address held for double the time relative to 1024
(actually counter[27:18] has range 1024 but addr is 9 bits, so we use
addr = counter[27:19] for proper 512 sweep, ~10.49 ms/word).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))

from bitstream import patch_rbf_crc
from compile import setup_project, compile_full, generate_rbf
from m9k_init_basis import M9K_INIT_ANCHORS, write_init, read_init

WIDTH, DEPTH = 9, 512
WORD_MS = 10.485   # counter[27:19] / 50 MHz: 2^28 / 512 cycles per word
HIGH_VAL = 0x1FF

PINS = {"CLK": "PIN_E1", "KEY2": "PIN_E16", "KEY3": "PIN_M16", "LED0": "PIN_G15"}
LOADER = (
    Path.home() / "see_neorv32_run_linux" / "tools" /
    "openFPGALoader" / "build" / "openFPGALoader"
)


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
    wire [8:0] addr_r = counter[27 -: 9];
    wire [8:0] addr_w = counter[8:0];
    wire [8:0] din    = {9{KEY3}};
    wire       we     = ~KEY2;
    wire [8:0] dout;
    reg  [8:0] dout_r;
    always @(posedge CLK) dout_r <= dout;
    assign LED0 = ^dout_r;
    altsyncram #(
        .operation_mode("SINGLE_PORT"),
        .width_a(9), .widthad_a(9), .numwords_a(512),
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
        .address_b(9'b0), .data_b(9'b0),
        .rden_a(1'b1), .rden_b(1'b0), .wren_b(1'b0),
        .q_b(), .addressstall_b(1'b0), .byteena_b(1'b1)
    );
endmodule
"""


def _allzero_mif() -> str:
    lines = [
        f"DEPTH = {DEPTH};", f"WIDTH = {WIDTH};",
        "ADDRESS_RADIX = HEX;", "DATA_RADIX = HEX;",
        "CONTENT BEGIN",
    ]
    for i in range(DEPTH):
        lines.append(f"  {i:03X} : 0;")
    lines.append("END;")
    return "\n".join(lines) + "\n"


def _qsf(site: str) -> str:
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
    lines.append(f'set_location_assignment M9K_{site} -to "u"')
    return "\n".join(lines) + "\n"


def _build_allzero(site: str) -> Path:
    tag = f"sp_9x512_allzero_{site}"
    work = ROOT / "tmp" / tag
    work.mkdir(parents=True, exist_ok=True)
    rbf_path = work / f"{tag}.rbf"
    if rbf_path.exists():
        print(f"[{tag}] cached RBF exists")
        return rbf_path
    proj_dir = setup_project(tag, _verilog(), _qsf(site), str(work))
    (Path(proj_dir) / "mem_init.mif").write_text(_allzero_mif())
    print(f"[{tag}] building Quartus allzero base ...", flush=True)
    ok, el, err = compile_full(tag, proj_dir, timeout=300)
    if not ok:
        sys.exit(f"build FAIL ({el:.1f}s): {err}")
    rbf = generate_rbf(tag, proj_dir, str(rbf_path))
    if rbf is None:
        sys.exit("RBF gen FAIL")
    print(f"[{tag}] built in {el:.1f}s")
    return Path(rbf)


def _flash(rbf: Path) -> None:
    cmd = [str(LOADER), "-c", "usb-blaster", str(rbf)]
    print(f"flashing: {' '.join(cmd)}")
    rc = subprocess.run(cmd).returncode
    if rc != 0:
        sys.exit(f"flash FAIL (rc={rc})")
    print("flash OK")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("site", help='e.g. "X15_Y16_N0"')
    ap.add_argument("--stripe", type=int, default=16,
                    help="stripe width in words (default 16 → ~2.98 Hz)")
    ap.add_argument("--flash", action="store_true")
    args = ap.parse_args()

    key = (args.site, WIDTH, DEPTH)
    if key not in M9K_INIT_ANCHORS:
        sys.exit(f"no anchor for {key}")
    anchor, bp = M9K_INIT_ANCHORS[key]
    print(f"[{args.site}] anchor={anchor} bp={bp}")

    base_rbf = _build_allzero(args.site)
    base = base_rbf.read_bytes()

    current = read_init(base, anchor, width=WIDTH, depth=DEPTH, bp=bp)
    if any(w != 0 for w in current):
        sys.exit("base RBF is not all-zero — pattern reasoning would be invalid")

    target = [HIGH_VAL if ((i // args.stripe) & 1) else 0 for i in range(DEPTH)]
    modified = write_init(base, anchor, current, target,
                          width=WIDTH, depth=DEPTH, bp=bp)
    modified = patch_rbf_crc(modified)

    check = read_init(modified, anchor, width=WIDTH, depth=DEPTH, bp=bp)
    mismatch = sum(a != b for a, b in zip(check, target))
    if mismatch:
        sys.exit(f"FAIL: round-trip {mismatch} mismatches")

    out = ROOT / "tmp" / f"sp_9x512_silicon_test_{args.site}_stripe{args.stripe}.rbf"
    out.write_bytes(modified)

    diff_base = sum(1 for x, y in zip(modified, base) if x != y)
    transitions = sum(1 for i in range(1, DEPTH)
                      if target[i] != target[i-1])
    sweep_s = DEPTH * WORD_MS / 1000
    blink_hz = transitions / sweep_s / 2

    print(f"[{args.site} stripe={args.stripe}] wrote {out}")
    print(f"[{args.site} stripe={args.stripe}] round-trip OK ({DEPTH} words)")
    print(f"[{args.site} stripe={args.stripe}] diff vs allzero: {diff_base} bytes")
    print(f"[{args.site} stripe={args.stripe}] transitions={transitions} → ~{blink_hz:.2f} Hz")

    if args.flash:
        _flash(out)


if __name__ == "__main__":
    main()
