#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Derive padnv-bucket IOB_ROUTE entries for X4Y4N0 (2-pin AND gate).

STATUS 2026-05-21 (Track B1): σ⁻¹ TT contamination unblocked via P1/P2
pragmas — `# fasm2rbf: bypass_aware=1` on the single-pin (mask=0xAAAA)
stack and `# fasm2rbf: canon_2input_aware=1` on the two-pin (mask=0x8888,
canonical label 'a&b') stack.  Both paths are silicon-validated since
2026-05-13 (memos `p1_bypass_aware_silicon_validated_2026_05_13`,
`p2_canon_2input_silicon_validated_2026_05_13`); the codec now emits
byte-identical LUT TT cells via the absolute / bypass path, so the diff
`gold ⊕ base` is pure routing — no σ⁻¹ TT noise to subtract.

Historical context (pre-Track-B1, kept for forensic reference):
the 2026-05-11 attempt failed Step 5 verification (99 byte diffs) because
σ⁻¹ at X4Y4N0 LE_0 mis-encodes both 0x8888 (read=0xC0C0) and 0xAAAA
(read=0xF0F0) when using the legacy predict_sram path.  The mining diff
therefore contained σ⁻¹-misencoding cells alongside the actual routing
cells.  We worked around it by subtracting `LutCodec.all_cells` from the
diff, which removed contamination but also removed legitimately-coincident
routing cells (LI MUX aliases LUT TT coordinates per the predict_sram
audit in `p5d_per_lab_li_filter_2026_05_21`).  The P1/P2 pragma path
sidesteps both problems.

Bug #2 closure per memo `gamma_bug1_strip_fix_landed_2026_05_11`: the
sigcache for `4,4,0->4,21,0,dataa` (and `4,4,0->4,7,0,dataa`) contains
NO header cells, leaving IOB_E16/M16 → X4Y4N0 routing unowned in the
header band.  build_test residuals at Y=21 (13 header) and Y=7 (5
header) trace to this gap.

Approach mirrors the 2026-04-21 derivation of the X=16 padnv entries
(commit 6d462b3) but in script form:

  Step 1 — Quartus gold A (E16 only → X4Y4N0 dataa, dataa-passthrough
           LUT).  Yields `IOB_E16->4,4,0,dataa` via padnv algebra:
             primary = gold_A_delta ⊕ (all other directives in stack)
                      ⊕ LUT_dataa_passthrough_cells

  Step 2 — Quartus gold B (E16+M16 → X4Y4N0 AND gate, 0x8888).
           Yields combined cells for E16->dataa + M16->datab.

  Step 3 — Split:
             M16->datab_cells = (combined_xor ⊕ E16->dataa_cells)

  Step 4 — Verify by reconstructing each gold from FASM with the
           newly-mined sigcache entries.

Output: in-place patch of `results/iob_to_slice_sigcache.json`
`padnv_cells` bucket with two new keys.  Re-runnable (idempotent).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "fuzz"))

import fasm2rbf as f  # noqa: E402
from bitstream import LutCodec  # noqa: E402

QUARTUS = Path.home() / "intelFPGA_lite" / "21.1" / "quartus" / "bin"

PRE = 32
FRAME = 210
FIRST = 25
LAST = 1751
CRAM_END = PRE + (LAST + 1) * FRAME

TARGET = (4, 4, 0)  # X, Y, N
DX, DY, DN = TARGET


def is_crc(off: int) -> bool:
    """True iff `off` is a per-frame CRC byte (frame[208] or frame[209])
    of a CRC-validated frame (25..1751).  Header frames 0..24 carry no
    CRC — their last two bytes are real data and must NOT be filtered
    (Pitfall #11)."""
    if off < PRE or off >= CRAM_END:
        return False
    frame = (off - PRE) // FRAME
    if frame < FIRST or frame > LAST:
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


def reset_caches():
    f._IOB_BASELINE_HDR_CACHE = None
    f._IOB_MAP_CACHE = None
    f._IOB_ROUTE_CACHE = None
    f._IOB_ROUTE_NODEDUP_KEYS = None
    f._IOB_ROUTE_LEGACY_CACHE = None
    f._GCLK_PIN_CACHE = None
    f._LAB_CLK_SEL_CACHE.clear()
    f._LAB_CLK_SEL_LE_CACHE = None
    f._IOB_CLK_INPUT_CACHE = None
    f._IOB_PAD_NV_CACHE = None
    f._OUTROUTE_SIGCACHE = None


def write_quartus_project(work_dir: Path, name: str, verilog: str, qsf: str):
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "fuzz_top.v").write_text(verilog)
    (work_dir / f"{name}.qsf").write_text(qsf)
    (work_dir / f"{name}.qpf").write_text(
        f'QUARTUS_VERSION = "21.1"\nPROJECT_REVISION = "{name}"\n'
    )


def build_quartus(work_dir: Path, name: str) -> Path | None:
    rbf = work_dir / "output_files" / f"{name}.rbf"
    sof = work_dir / "output_files" / f"{name}.sof"
    if rbf.exists() and rbf.stat().st_size == 368011:
        print(f"  [cached] {rbf.relative_to(REPO)}")
        return rbf

    env = os.environ.copy()
    env["PATH"] = str(QUARTUS) + ":" + env.get("PATH", "")

    for step in ("quartus_map", "quartus_fit", "quartus_asm"):
        r = subprocess.run(
            [step, name], cwd=str(work_dir), env=env,
            capture_output=True, text=True, errors="replace", timeout=300,
        )
        if r.returncode != 0:
            print(f"  [{step}] FAIL rc={r.returncode}")
            print(r.stderr[-1500:])
            return None
    r = subprocess.run(
        [str(QUARTUS / "quartus_cpf"), "-c", "-o", "bitstream_compression=off",
         str(sof), str(rbf)],
        cwd=str(work_dir), env=env,
        capture_output=True, text=True, errors="replace", timeout=60,
    )
    if r.returncode != 0 or not rbf.exists():
        print("  [cpf] FAIL")
        return None
    print(f"  [build] OK → {rbf.relative_to(REPO)}")
    return rbf


def gen_qsf(name: str, pins: dict[str, str], lut_loc: str) -> str:
    """Generate QSF with the given pin assignments and a single LCCOMB
    location.  pins maps signal name → PIN_xx code."""
    lines = [
        'set_global_assignment -name FAMILY "Cyclone IV E"',
        'set_global_assignment -name DEVICE EP4CE6F17C8',
        'set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top',
        'set_global_assignment -name VERILOG_FILE fuzz_top.v',
        'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files',
        'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"',
        'set_global_assignment -name SEED 1',
        'set_global_assignment -name RESERVE_ALL_UNUSED_PINS_WEAK_PULLUP '
        '"AS INPUT TRI-STATED WITH WEAK PULL-UP"',
        'set_global_assignment -name CYCLONEII_RESERVE_NCEO_AFTER_CONFIGURATION '
        '"USE AS REGULAR IO"',
    ]
    for sig, pin in pins.items():
        lines.append(f'set_location_assignment {pin} -to {sig}')
    lines.append(f'set_location_assignment {lut_loc} -to "lut_prim"')
    lines.append('set_instance_assignment -name GLOBAL_SIGNAL '
                 '"GLOBAL CLOCK" -to CLK')
    return "\n".join(lines) + "\n"


def derive_via_padnv_algebra(gold: bytes, fasm_text: str) -> tuple[
        set[tuple[int, int]], int, int]:
    """Compute padnv route cells = gold ⊕ base.

    With P1 bypass_aware / P2 canon_2input_aware pragmas in `fasm_text`,
    `bitgen` emits byte-identical LUT TT cells to Quartus (no σ⁻¹
    contamination), so the diff is pure routing — no subtraction needed.

    Returns (route_cells, data_diff, crc_diff).
    """
    nv = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()
    reset_caches()

    pragmas = f.parse_pragmas(fasm_text)
    base = f.bitgen(fasm_text, nv, patch_crc=True, **pragmas)
    assert len(base) == 368011

    route_xor = bytes(a ^ b for a, b in zip(gold, base))
    route_cells = {c for c in bit_cells(route_xor)
                   if not is_crc(c[0]) and c[0] < CRAM_END}

    return route_cells, len(route_cells), 0


VERILOG_SINGLE_PIN = """\
// SPDX-License-Identifier: GPL-3.0-or-later
module fuzz_top(
    input  wire CLK,
    input  wire KEY,
    output reg  LED
);
    wire lut_out;
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
"""


VERILOG_TWO_PIN = """\
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


def fasm_stack_single_pin(pin: str) -> str:
    """FASM directives for the single-pin design, EXCLUDING IOB_ROUTE.

    mask=0xAAAA is in BYPASS_1INPUT_MASKS — Quartus encodes it as LUT-
    bypass (no SRAM TT cells, 1 block_band canon cell), and P1
    `bypass_aware=1` makes bitgen do the same byte-identically.
    """
    return (
        "# fasm2rbf: bypass_aware=1\n"
        "IOB_PAD_NV\n"
        f"IOB_CLK_INPUT PIN_E1\n"
        f"OUTROUTE_G15 X{DX}Y{DY}N{DN}\n"
        f"X{DX}Y{DY}N{DN}.LUT = 0xAAAA\n"
        f"GCLK_PIN PIN_E1\n"
        f"LAB_CLK_SEL X{DX}Y{DY}\n"
        f"LAB_CLK_SEL_LE X{DX}Y{DY}N{DN}\n"
    )


def fasm_stack_two_pin() -> str:
    """FASM directives for the 2-pin AND design, EXCLUDING IOB_ROUTE.

    mask=0x8888 is canonical label 'a&b' — P2 canon_2input_aware applies
    CANON_2INPUT_ABSOLUTE[(4,4,0)]['a&b'] for byte-identical LUT TT.
    """
    return (
        "# fasm2rbf: canon_2input_aware=1\n"
        "IOB_PAD_NV\n"
        f"IOB_CLK_INPUT PIN_E1\n"
        f"OUTROUTE_G15 X{DX}Y{DY}N{DN}\n"
        f"X{DX}Y{DY}N{DN}.LUT = 0x8888\n"
        f"GCLK_PIN PIN_E1\n"
        f"LAB_CLK_SEL X{DX}Y{DY}\n"
        f"LAB_CLK_SEL_LE X{DX}Y{DY}N{DN}\n"
    )


def main():
    work_root = HERE / "work"

    # Step 1: build single-pin (E16) Quartus design at X4Y4N0
    print("=== Step 1: Quartus single-pin gold (E16 → X4Y4N0 dataa) ===")
    e16_dir = work_root / "padnv_single_E16_X4Y4N0"
    qsf_e16 = gen_qsf(
        name="single_E16_X4Y4N0",
        pins={"CLK": "PIN_E1", "KEY": "PIN_E16", "LED": "PIN_G15"},
        lut_loc=f"LCCOMB_X{DX}_Y{DY}_N{DN}",
    )
    write_quartus_project(e16_dir, "single_E16_X4Y4N0",
                          VERILOG_SINGLE_PIN, qsf_e16)
    gold_e16_path = build_quartus(e16_dir, "single_E16_X4Y4N0")
    if gold_e16_path is None:
        print("Build FAILED for E16 single-pin")
        return 1
    gold_e16 = gold_e16_path.read_bytes()

    # Step 2: derive E16->dataa cells via padnv algebra
    print("\n=== Step 2: derive E16->4,4,0,dataa via padnv algebra ===")
    cells_e16, n_data, n_crc = derive_via_padnv_algebra(
        gold_e16, fasm_stack_single_pin("E16"))
    print(f"  E16 padnv cells: {len(cells_e16)}")

    # Step 3: build 2-pin AND gate Quartus design
    print("\n=== Step 3: Quartus two-pin AND gold (E16+M16 → X4Y4N0) ===")
    and_dir = work_root / "padnv_two_pin_X4Y4N0"
    qsf_and = gen_qsf(
        name="two_pin_X4Y4N0",
        pins={"CLK": "PIN_E1", "KEY2": "PIN_E16", "KEY3": "PIN_M16",
              "LED": "PIN_G15"},
        lut_loc=f"LCCOMB_X{DX}_Y{DY}_N{DN}",
    )
    write_quartus_project(and_dir, "two_pin_X4Y4N0",
                          VERILOG_TWO_PIN, qsf_and)
    gold_and_path = build_quartus(and_dir, "two_pin_X4Y4N0")
    if gold_and_path is None:
        print("Build FAILED for 2-pin AND")
        return 1
    gold_and = gold_and_path.read_bytes()

    # Step 4: derive combined cells, split out M16->datab
    print("\n=== Step 4: derive combined cells, split M16->4,4,0,datab ===")
    cells_combined, _, _ = derive_via_padnv_algebra(
        gold_and, fasm_stack_two_pin())
    print(f"  combined padnv cells: {len(cells_combined)}")

    # M16->datab cells = combined ⊕ E16->dataa (XOR semantics: which cells
    # need to be flipped IN ADDITION to E16->dataa to produce the 2-pin
    # result).
    cells_m16 = cells_combined ^ cells_e16
    print(f"  M16->datab (= combined ⊕ E16): {len(cells_m16)}")

    # Step 5: verify by injecting into sigcache and rebuilding both gold
    print("\n=== Step 5: verify reconstruction ===")
    cells_e16_sorted = sorted(list(c) for c in cells_e16)
    cells_m16_sorted = sorted(list(c) for c in cells_m16)

    sig_path = REPO / "results" / "iob_to_slice_sigcache.json"
    sig = json.loads(sig_path.read_text())
    padnv = sig.setdefault("padnv_cells", {})

    backup_e16 = padnv.get(f"IOB_E16->{DX},{DY},{DN},dataa")
    backup_m16 = padnv.get(f"IOB_M16->{DX},{DY},{DN},datab")

    padnv[f"IOB_E16->{DX},{DY},{DN},dataa"] = cells_e16_sorted
    padnv[f"IOB_M16->{DX},{DY},{DN},datab"] = cells_m16_sorted

    # Persist; downstream reconstructs read the file
    sig_path.write_text(json.dumps(sig, indent=2) + "\n")
    print(f"  injected provisional entries into {sig_path.relative_to(REPO)}")
    print(f"    IOB_E16->{DX},{DY},{DN},dataa: {len(cells_e16_sorted)} cells")
    print(f"    IOB_M16->{DX},{DY},{DN},datab: {len(cells_m16_sorted)} cells")

    # Rebuild E16 gold from FASM and diff
    reset_caches()
    fasm_e16_with_route = (
        f"IOB_ROUTE PIN_E16 -> X{DX}Y{DY}N{DN}.dataa\n"
        + fasm_stack_single_pin("E16")
    )
    nv = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()
    pragmas_e16 = f.parse_pragmas(fasm_e16_with_route)
    recon_e16 = f.bitgen(fasm_e16_with_route, nv, patch_crc=True, **pragmas_e16)
    d_e16 = sum(1 for a, b in zip(recon_e16, gold_e16) if a != b)
    print(f"  E16 reconstruction vs gold_A: {d_e16} byte diffs")

    # Rebuild AND gold from FASM and diff
    reset_caches()
    fasm_and_with_routes = (
        f"IOB_ROUTE PIN_E16 -> X{DX}Y{DY}N{DN}.dataa\n"
        f"IOB_ROUTE PIN_M16 -> X{DX}Y{DY}N{DN}.datab\n"
        + fasm_stack_two_pin()
    )
    pragmas_and = f.parse_pragmas(fasm_and_with_routes)
    recon_and = f.bitgen(fasm_and_with_routes, nv, patch_crc=True, **pragmas_and)
    d_and = sum(1 for a, b in zip(recon_and, gold_and) if a != b)
    print(f"  AND reconstruction vs gold_B: {d_and} byte diffs")

    if d_e16 == 0 and d_and == 0:
        print("\n  *** PASS: padnv-bucket entries reproduce both golds ***")
        print("     E16->4,4,0,dataa and M16->4,4,0,datab are live and")
        print("     can be consumed by build_test / np2fasm.")
        return 0
    else:
        # Roll back on failure
        if backup_e16 is None:
            del padnv[f"IOB_E16->{DX},{DY},{DN},dataa"]
        else:
            padnv[f"IOB_E16->{DX},{DY},{DN},dataa"] = backup_e16
        if backup_m16 is None:
            del padnv[f"IOB_M16->{DX},{DY},{DN},datab"]
        else:
            padnv[f"IOB_M16->{DX},{DY},{DN},datab"] = backup_m16
        sig_path.write_text(json.dumps(sig, indent=2) + "\n")
        print(f"\n  *** FAIL: rebuild diffs nonzero — rolled back sigcache ***")
        return 1


if __name__ == "__main__":
    sys.exit(main())
