# SPDX-License-Identifier: GPL-3.0-or-later
"""Extract clock-input-pin hdr cells.

Dedicated clock bank pins (E1, R8, N1, ...) are not covered by
fuzz/iob_sweep.py (only 44 regular IO pins).  When a design uses such a
pin as CLK (driving the GCLK network), Quartus emits ~26-40 header-band
bytes configuring the pin's IOB + the pin->GCLK path.

Algebra:
  cells_{CLK}_clk = simple_led_E16_to_G15_clk{CLK}.rbf ^ iob_in_E16.rbf
                    [hdr band only, off < 5282]

  (gold design has {CLK}=CLK + E16=IN + G15=OUT; iob_in_E16 has only
  E16=IN + G15=OUT -- the CLK-bank pin is undriven.)

Applying `cells_{CLK}_clk` on top of `nv + IOB_BASELINE_NV + IOB_IN E16
+ IOB_OUT G15` reproduces the simple_led hdr band byte-for-byte.

Usage (build + mine a given clock pin):
    python3 compute_clk_pin_hdr.py --build --pin E1
    python3 compute_clk_pin_hdr.py --build --pin R8
    python3 compute_clk_pin_hdr.py --build --pin N1

If --build is omitted, the script assumes the gold RBF already exists
under work/simple_led_E16_to_G15_clk{PIN}/output_files/.  By default it
mines all pins whose gold RBF is present and writes them into
results/iob_clk_pin_hdr_cells.json (preserving any previously-mined
entries).

Note on E1 legacy: the original mining re-used the *un-suffixed*
`simple_led_E16_to_G15` project (CLK=E1 baked in).  This script still
recognises the legacy path if `--pin E1` is requested without `--build`
and the suffixed project is absent.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

PRE = 32
FRAME = 210
FIRST = 25
CRAM_START = PRE + FIRST * FRAME  # 5282

QUARTUS_BIN = Path(os.environ.get(
    "QUARTUS_BIN",
    f"{os.environ.get('HOME', '/home/test')}"
    "/intelFPGA_lite/21.1/quartus/bin"
))


FUZZ_TOP_V = '''// SPDX-License-Identifier: GPL-3.0-or-later
// Simple end-to-end test: KEY (E16) through LUT@X10Y4N0 -> DFF -> LED (G15)
// Used as the Quartus gold for the baseline-integration probe.
module fuzz_top(
    input  wire CLK,
    input  wire KEY,
    output reg  LED
);
    wire lut_out;
    // Dataa-passthrough LUT, mask=0xAAAA.  dont_touch keeps it pinned
    // to LCCOMB_X10_Y4_N0.
    cycloneive_lcell_comb #(
        .lut_mask(16'hAAAA),
        .sum_lutc_input("datac"),
        .dont_touch("on")
    ) lut_prim (
        .dataa(KEY),
        .datab(1'b0),
        .datac(1'b0),
        .datad(1'b0),
        .combout(lut_out)
    );

    always @(posedge CLK) begin
        LED <= lut_out;
    end
endmodule
'''


QSF_TEMPLATE = '''set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top
set_global_assignment -name VERILOG_FILE fuzz_top.v
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"
set_global_assignment -name SEED 1
set_location_assignment PIN_{clk_pin}  -to CLK
set_location_assignment PIN_E16 -to KEY
set_location_assignment PIN_G15 -to LED
set_location_assignment LCCOMB_X10_Y4_N0 -to "lut_prim"
set_instance_assignment -name GLOBAL_SIGNAL "GLOBAL CLOCK" -to CLK
'''


def project_dir(pin: str) -> Path:
    """Return the work-dir for the CLK={pin} project."""
    return HERE / "work" / f"simple_led_E16_to_G15_clk{pin}"


def legacy_project_dir() -> Path:
    """Legacy CLK=E1 project uses the un-suffixed name."""
    return HERE / "work" / "simple_led_E16_to_G15"


def gold_rbf_path(pin: str) -> Path:
    """Return the expected gold RBF for CLK={pin}.

    Falls back to the legacy un-suffixed project for PIN_E1 so the first
    landing doesn't need a rebuild.
    """
    new = (project_dir(pin) / "output_files"
           / f"simple_led_E16_to_G15_clk{pin}.rbf")
    if new.exists():
        return new
    if pin == "E1":
        legacy = (legacy_project_dir() / "output_files"
                  / "simple_led_E16_to_G15.rbf")
        if legacy.exists():
            return legacy
    return new  # path that does not exist -- caller will raise


def run(cmd, cwd):
    """Run a Quartus command and dump its log tail on failure."""
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    r = subprocess.run(cmd, cwd=cwd, check=False,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = r.stdout.decode("utf-8", errors="replace")
    if r.returncode != 0:
        print(out[-2000:])
        raise RuntimeError(f"{cmd[0]} failed rc={r.returncode}")
    return out


def build_pin(pin: str) -> Path:
    """Compile simple_led_E16_to_G15_clk{pin}.rbf under work/."""
    pdir = project_dir(pin)
    if pdir.exists():
        shutil.rmtree(pdir)
    pdir.mkdir(parents=True)
    proj = f"simple_led_E16_to_G15_clk{pin}"
    (pdir / "fuzz_top.v").write_text(FUZZ_TOP_V)
    (pdir / f"{proj}.qsf").write_text(QSF_TEMPLATE.format(clk_pin=pin))
    (pdir / f"{proj}.qpf").write_text(
        'PROJECT_REVISION = "' + proj + '"\n'
    )
    run([str(QUARTUS_BIN / "quartus_map"), proj], cwd=pdir)
    run([str(QUARTUS_BIN / "quartus_fit"), proj], cwd=pdir)
    run([str(QUARTUS_BIN / "quartus_asm"), proj], cwd=pdir)
    sof = pdir / "output_files" / f"{proj}.sof"
    rbf = pdir / "output_files" / f"{proj}.rbf"
    run([str(QUARTUS_BIN / "quartus_cpf"),
         "-c", "-o", "bitstream_compression=off",
         str(sof), str(rbf)], cwd=pdir)
    if not rbf.exists():
        raise RuntimeError(f"build succeeded but RBF missing: {rbf}")
    return rbf


def extract_pin_delta(gold_path: Path, anchor_path: Path) -> list:
    gold = gold_path.read_bytes()
    anchor = anchor_path.read_bytes()
    assert len(gold) == len(anchor), (
        f"size mismatch {len(gold)} vs {len(anchor)}")
    cells: list = []
    for off in range(CRAM_START):
        x = gold[off] ^ anchor[off]
        if x == 0:
            continue
        for bp in range(8):
            if x & (1 << bp):
                cells.append((off, bp))
    return sorted(cells)


def mine_pin(pin: str) -> list:
    """Mine header-band cells for CLK={pin}.  Self-checks before returning."""
    gold = gold_rbf_path(pin)
    anchor = REPO / "results" / "rbf" / "iob_in_E16.rbf"
    if not gold.exists():
        raise RuntimeError(
            f"[{pin}] gold RBF missing: {gold}\n"
            f"      re-run with --build --pin {pin}"
        )
    if not anchor.exists():
        raise RuntimeError(f"anchor missing: {anchor}")
    cells = extract_pin_delta(gold, anchor)
    # Self-check: apply the delta on top of anchor, confirm it reproduces
    # the gold hdr band.
    anchor_b = anchor.read_bytes()
    gold_b = gold.read_bytes()
    buf = bytearray(anchor_b[:CRAM_START])
    for off, bp in cells:
        buf[off] ^= (1 << bp)
    if bytes(buf) != gold_b[:CRAM_START]:
        raise RuntimeError(f"[{pin}] self-check FAILED")
    print(f"[{pin}] {len(cells)} bit cells "
          f"({len({o for o, _ in cells})} distinct bytes) -- verified")
    return cells


def load_existing() -> dict:
    path = REPO / "results" / "iob_clk_pin_hdr_cells.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text()).get("cells", {})


def write_output(entries: dict) -> None:
    data = {
        "meta": {
            "source": "simple_led_E16_to_G15_clk{CLK}.rbf ^ "
                      "iob_in_E16.rbf, hdr band only (off < 5282).  "
                      "Extracts the clock-input pin activation delta "
                      "(IOB bank config + GCLK mux).",
            "frame": "nv_zero_global",
            "scope": "header_band",
            "note": "Apply on top of nv + IOB_BASELINE_NV + IOB_IN "
                    "PIN_E16 + IOB_OUT PIN_G15 to activate the "
                    "clock-bank pin as a GCLK driver.",
        },
        "cells": {pin: [list(c) for c in entries[pin]]
                  for pin in sorted(entries)},
    }
    out_path = REPO / "results" / "iob_clk_pin_hdr_cells.json"
    out_path.write_text(json.dumps(data, indent=2))
    print(f"[ok] wrote {out_path} "
          f"(pins: {', '.join(sorted(entries))})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true",
                    help="compile the Quartus gold RBF before mining")
    ap.add_argument("--pin", action="append", default=None,
                    help="clock pin (e.g. E1, R8, N1); repeatable. "
                         "If omitted, mines every pin whose gold RBF "
                         "exists.")
    args = ap.parse_args()

    target_pins = args.pin or ["E1", "R8", "N1"]

    if args.build:
        for pin in target_pins:
            print(f"\n=== build CLK=PIN_{pin} ===")
            build_pin(pin)

    existing = load_existing()
    entries = dict(existing)
    mined_now = []
    for pin in target_pins:
        gold = gold_rbf_path(pin)
        if not gold.exists():
            print(f"[skip] {pin}: no gold RBF at {gold}")
            continue
        cells = mine_pin(pin)
        entries[pin] = cells
        mined_now.append(pin)

    write_output(entries)
    print(f"\n[done] mined {len(mined_now)} pins this run: "
          f"{', '.join(mined_now) or '(none)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
