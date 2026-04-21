# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate that IOB→SLICE datab route uses the same CRAM cells as dataa.

Builds a 2-input AND gate (KEY2=E16 & KEY3=M16 → DFF → LED=G15) in
Quartus with explicit cycloneive_lcell_comb port binding at X16Y4N0, then
reconstructs the design using FASM with the dataa sig-cache entry aliased
for the datab route.

If reconstruction matches gold byte-for-byte (0 data diffs), port aliasing
(datab → dataa) is safe and the E2E pipeline can proceed.

Evidence: Round 1 multi-port validation showed A↔B = 0 CRAM diff.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "fuzz"))

import fasm2rbf as f  # noqa: E402

PRE = 32
FRAME = 210
FIRST = 25
LAST = 1751
CRAM_END = PRE + (LAST + 1) * FRAME

TARGET = (16, 4, 0)
PIN_A = "E16"   # KEY2 → dataa
PIN_B = "M16"   # KEY3 → datab
CLK_PIN = "E1"
LED_PIN = "G15"
LUT_MASK = 0x8888  # A & B


def is_crc(off: int) -> bool:
    if off < PRE or off >= CRAM_END:
        return False
    return (off - PRE) % FRAME >= 208


def bit_cells(data: bytes) -> set[tuple[int, int]]:
    out = set()
    for i, b in enumerate(data):
        if not b:
            continue
        for bp in range(8):
            if b & (1 << bp):
                out.add((i, bp))
    return out


def write_project(work_dir: Path) -> tuple[Path, str]:
    work_dir.mkdir(parents=True, exist_ok=True)
    name = "and_gate_gold"
    dx, dy, dn = TARGET

    vtext = """\
// SPDX-License-Identifier: GPL-3.0-or-later
module fuzz_top(
    input  wire CLK,
    input  wire KEY2,
    input  wire KEY3,
    output reg  LED
);
    wire lut_out;
    cycloneive_lcell_comb #(
        .lut_mask(16'h8888),
        .sum_lutc_input("datac"),
        .dont_touch("on")
    ) lut_prim (
        .dataa(KEY2),
        .datab(KEY3),
        .datac(1'b0),
        .datad(1'b0),
        .combout(lut_out)
    );
    always @(posedge CLK) begin
        LED <= lut_out;
    end
endmodule
"""
    (work_dir / "fuzz_top.v").write_text(vtext)

    qsf = (
        'set_global_assignment -name FAMILY "Cyclone IV E"\n'
        'set_global_assignment -name DEVICE EP4CE6F17C8\n'
        'set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top\n'
        'set_global_assignment -name VERILOG_FILE fuzz_top.v\n'
        'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files\n'
        'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"\n'
        'set_global_assignment -name SEED 1\n'
        f'set_location_assignment PIN_{CLK_PIN} -to CLK\n'
        f'set_location_assignment PIN_{PIN_A} -to KEY2\n'
        f'set_location_assignment PIN_{PIN_B} -to KEY3\n'
        f'set_location_assignment PIN_{LED_PIN} -to LED\n'
        f'set_location_assignment LCCOMB_X{dx}_Y{dy}_N{dn} -to "lut_prim"\n'
        'set_instance_assignment -name GLOBAL_SIGNAL "GLOBAL CLOCK" -to CLK\n'
    )
    (work_dir / f"{name}.qsf").write_text(qsf)

    qpf = (
        'QUARTUS_VERSION = "21.1"\n'
        f'PROJECT_REVISION = "{name}"\n'
    )
    (work_dir / f"{name}.qpf").write_text(qpf)
    return work_dir, name


def build(work_dir: Path, name: str) -> Path | None:
    rbf = work_dir / "output_files" / f"{name}.rbf"
    sof = work_dir / "output_files" / f"{name}.sof"
    if rbf.exists():
        print(f"  [cached] {rbf}")
        return rbf

    for step in ("quartus_map", "quartus_fit", "quartus_asm"):
        r = subprocess.run(
            [step, name], cwd=work_dir,
            capture_output=True, text=True, errors="replace",
        )
        if r.returncode != 0:
            print(f"  [{step}] FAIL rc={r.returncode}")
            print(r.stderr[-1000:])
            return None

    r = subprocess.run(
        ["quartus_cpf", "-c", "-o", "bitstream_compression=off",
         str(sof), str(rbf)],
        cwd=work_dir,
        capture_output=True, text=True, errors="replace",
    )
    if r.returncode != 0 or not rbf.exists():
        print("  [cpf] FAIL")
        return None
    print(f"  [build] OK → {rbf} ({rbf.stat().st_size} bytes)")
    return rbf


def check_fit_report(work_dir: Path, name: str):
    """Parse fit report to verify Quartus honored the port binding."""
    fit_rpt = work_dir / "output_files" / f"{name}.fit.rpt"
    if not fit_rpt.exists():
        print("  [fit.rpt] not found")
        return
    text = fit_rpt.read_text(errors="replace")
    dx, dy, dn = TARGET
    target_str = f"LCCOMB_X{dx}_Y{dy}_N{dn}"
    found = False
    for line in text.splitlines():
        if target_str in line or "lut_prim" in line.lower():
            print(f"  [fit] {line.strip()}")
            found = True
    if not found:
        # Try searching for KEY2/KEY3 pin assignments
        for line in text.splitlines():
            if "KEY2" in line or "KEY3" in line:
                print(f"  [fit] {line.strip()}")


def main():
    work_dir = HERE / "work" / "and_gate_gold"

    print("=== Phase 1: Build Quartus gold (2-input AND gate) ===")
    work_dir_p, name = write_project(work_dir)
    rbf_path = build(work_dir_p, name)
    if rbf_path is None:
        return 1
    check_fit_report(work_dir_p, name)

    nv = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()
    gold = rbf_path.read_bytes()
    assert len(gold) == 368011, f"unexpected RBF size: {len(gold)}"

    gold_xor = bytes(a ^ b for a, b in zip(gold, nv))
    gold_cells = {c for c in bit_cells(gold_xor)
                  if not is_crc(c[0]) and c[0] < CRAM_END}
    print(f"  gold delta vs nv_zero_global: {len(gold_cells)} cells (excl CRC)")

    print("\n=== Phase 2: FASM reconstruction (datab aliased to dataa) ===")
    dx, dy, dn = TARGET

    # Reset all caches for a clean run
    f._IOB_BASELINE_HDR_CACHE = None
    f._IOB_MAP_CACHE = None
    f._IOB_ROUTE_CACHE = None
    f._GCLK_PIN_CACHE = None
    f._LAB_CLK_SEL_CACHE.clear()
    f._LAB_CLK_SEL_LE_CACHE = None
    f._IOB_CLK_INPUT_CACHE = None
    f._IOB_PAD_NV_CACHE = None
    f._OUTROUTE_G15_CACHE = None

    # Reconstruct using IOB_PAD_NV (covers E16+M16 input + G15 output)
    # and IOB_ROUTE with dataa for BOTH routes (the alias hypothesis)
    fasm_text = (
        f"IOB_PAD_NV\n"
        f"IOB_CLK_INPUT PIN_{CLK_PIN}\n"
        f"IOB_ROUTE PIN_{PIN_A} -> X{dx}Y{dy}N{dn}.dataa\n"
        f"IOB_ROUTE PIN_{PIN_B} -> X{dx}Y{dy}N{dn}.dataa\n"
        f"OUTROUTE_G15 X{dx}Y{dy}N{dn}\n"
        f"X{dx}Y{dy}N{dn}.LUT = 0x{LUT_MASK:04X}\n"
        f"GCLK_PIN PIN_{CLK_PIN}\n"
        f"LAB_CLK_SEL X{dx}Y{dy}\n"
        f"LAB_CLK_SEL_LE X{dx}Y{dy}N{dn}\n"
    )
    print(f"  FASM:\n{fasm_text}")

    try:
        recon = f.bitgen(fasm_text, nv, patch_crc=True)
    except Exception as e:
        print(f"  [FAIL] bitgen error: {e}")
        return 1

    data_diffs = 0
    crc_diffs = 0
    diff_cells = []
    for i in range(len(recon)):
        if recon[i] != gold[i]:
            if is_crc(i):
                crc_diffs += 1
            else:
                data_diffs += 1
                x = recon[i] ^ gold[i]
                for bp in range(8):
                    if x & (1 << bp):
                        frame = (i - PRE) // FRAME if i >= PRE else -1
                        diff_cells.append((i, bp, frame))

    print(f"  reconstruction vs gold: {data_diffs} data diffs, {crc_diffs} CRC diffs")

    if data_diffs == 0:
        print("\n  *** PASS: datab ≡ dataa — port aliasing is SAFE ***")
        print("  The sig-cache dataa entry reproduces the 2-input AND gate")
        print("  byte-perfectly when used for both dataa and datab routes.")
        return 0
    else:
        print(f"\n  *** FAIL: {data_diffs} data diffs ({len(diff_cells)} diff cells) ***")
        for off, bp, frame in diff_cells[:30]:
            in_gold = "gold" if (gold[off] >> bp) & 1 else "recon"
            print(f"    off={off:6d} bp={bp} frame={frame:4d}  set_in={in_gold}")
        if len(diff_cells) > 30:
            print(f"    ... and {len(diff_cells) - 30} more")

        # Diagnostic: compare the sig-cache dataa entry for M16 directly
        print("\n=== Diagnostic: M16 dataa sig-cache cells ===")
        m16_dataa = f._load_iob_route_cells(PIN_B, dx, dy, dn, "dataa")
        print(f"  IOB_M16->{dx},{dy},{dn},dataa: {len(m16_dataa)} cells")

        # Check which diff cells overlap with the M16 route
        m16_set = {tuple(c) for c in m16_dataa}
        diff_set = {(off, bp) for off, bp, _ in diff_cells}
        overlap = diff_set & m16_set
        print(f"  diff cells in M16 dataa entry: {len(overlap)}")
        print(f"  diff cells NOT in M16 dataa:   {len(diff_set - m16_set)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
