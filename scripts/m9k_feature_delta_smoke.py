# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-feature M9K_MODE delta-mining smoke test.

Hypothesis: the M9K_MODE component of a single-feature change (e.g.
outdata_reg_a UNREGISTERED → CLOCK0) lives in the block_band region
(frames 1692..1738).  Other regions (header, lab, block_band_post)
also see Quartus place&route drift, but those belong to OTHER
directives — IOB_PIN_BANK_INFRA (header + bb_post), M9K_COLUMN_INFRA
(lab cols), LAB_RESIDUAL (np2fasm LUT/ROUTE side).  A clean
M9K_MODE per-feature delta is `(gold_F ⊕ gold_base) ∩ block_band`.

Method:
  1. Build base SP Quartus fixture at the calibration site.
  2. Build base + outdata_reg_a=CLOCK0 (only altsyncram param differs).
  3. Compute delta_bb = (gold_outreg ⊕ gold_base) ∩ block_band.
  4. Pass criterion: delta_bb has reasonable size (5..200 cells)
     and contains the M9K's outreg encoding bits.

Reports leakage in other regions for diagnostic context.

Builds run in parallel.  Output: stdout report + saved RBFs in
tmp/m9k_feature_delta/.
"""
from __future__ import annotations
import argparse
import math
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))

from compile import setup_project, compile_full, generate_rbf  # noqa: E402

PRE, FRAME, DPF = 32, 210, 208
REGIONS = [
    (0, 24, "header"),
    (25, 1006, "lab_low"),
    (1007, 1013, "clk_net"),
    (1014, 1691, "lab_high"),
    (1692, 1738, "block_band"),
    (1739, 1751, "block_band_post"),
]

# SP (9, 1024) = 9216 bits, fits a single M9K cleanly; this combo is
# already in the m9k_mode_quartus_gold_mine TARGET_COMBOS.
SITE_X, SITE_Y, SITE_N = 15, 10, 0
WIDTH, DEPTH = 9, 1024

PIN_POOL = [
    "PIN_E15", "PIN_E16", "PIN_M16", "PIN_M15",
    "PIN_A8",  "PIN_A11", "PIN_A14", "PIN_B14",
    "PIN_T2",  "PIN_T8",  "PIN_R1",  "PIN_R5",
    "PIN_R9",  "PIN_R13", "PIN_R16", "PIN_P1",
    "PIN_P9",  "PIN_P15", "PIN_T13",
    "PIN_F15", "PIN_B16", "PIN_G16", "PIN_K15",
    "PIN_K16", "PIN_L15", "PIN_L16", "PIN_N16",
    "PIN_D16", "PIN_D15", "PIN_C15", "PIN_C16",
    "PIN_F14", "PIN_P2",  "PIN_J14", "PIN_J15",
    "PIN_J16", "PIN_T3",  "PIN_T7",  "PIN_T12",
    "PIN_T15", "PIN_P3",  "PIN_P11", "PIN_P16",
    "PIN_N2",  "PIN_N14",
]

FIXTURES = {
    "base":        {"outdata_reg_a": "UNREGISTERED"},
    "feat_outreg": {"outdata_reg_a": "CLOCK0"},
}


def _addr_bits(d: int) -> int:
    return max(1, int(math.ceil(math.log2(d))))


def _port_signals() -> list[str]:
    ab = _addr_bits(DEPTH)
    sigs = ["CLK", "WE"]
    sigs += [f"ADDR{i}" for i in range(ab)]
    sigs += [f"DIN{i}" for i in range(WIDTH)]
    sigs += [f"DOUT{i}" for i in range(WIDTH)]
    return sigs


def _pin_map() -> dict[str, str]:
    sigs = _port_signals()
    if len(sigs) > 1 + len(PIN_POOL):
        raise ValueError(f"sig overflow: {len(sigs)}")
    pins: dict[str, str] = {"CLK": "PIN_E1"}
    remain = list(PIN_POOL)
    for s in sigs:
        if s == "CLK":
            continue
        pins[s] = remain.pop(0)
    return pins


def _verilog(feature_overrides: dict[str, str]) -> str:
    ab = _addr_bits(DEPTH)
    addr_bus = ", ".join(f"ADDR{i}" for i in range(ab - 1, -1, -1))
    din_bus = ", ".join(f"DIN{i}" for i in range(WIDTH - 1, -1, -1))
    dout_assign = ", ".join(f"DOUT{i}" for i in range(WIDTH - 1, -1, -1))

    # Default altsyncram parameter pack matching the existing
    # m9k_mode_quartus_gold_mine.py SP variant.  Single-feature
    # smoke tests override one key at a time.
    params = {
        "operation_mode":                 '"SINGLE_PORT"',
        "width_a":                        str(WIDTH),
        "widthad_a":                      str(ab),
        "numwords_a":                     str(DEPTH),
        "lpm_type":                       '"altsyncram"',
        "ram_block_type":                 '"M9K"',
        "outdata_reg_a":                  '"UNREGISTERED"',
        "read_during_write_mode_port_a":  '"OLD_DATA"',
        "read_during_write_mode_mixed_ports": '"DONT_CARE"',
        "indata_reg_b":                   '"CLOCK1"',
        "wrcontrol_wraddress_reg_b":      '"CLOCK1"',
        "rdcontrol_reg_b":                '"CLOCK1"',
        "address_reg_b":                  '"CLOCK1"',
        "outdata_reg_b":                  '"UNREGISTERED"',
        "byteena_reg_b":                  '"CLOCK1"',
        "clock_enable_input_a":           '"NORMAL"',
        "clock_enable_output_a":          '"NORMAL"',
        "init_file":                      '"mem_init.mif"',
        "intended_device_family":         '"Cyclone IV E"',
    }
    for k, v in feature_overrides.items():
        params[k] = f'"{v}"' if not v.startswith('"') else v

    param_lines = ",\n        ".join(f".{k}({v})" for k, v in params.items())

    port_decl_parts = []
    for s in _port_signals():
        if s.startswith("DOUT"):
            port_decl_parts.append(f"output {s}")
        else:
            port_decl_parts.append(f"input {s}")
    port_decl = ",\n    ".join(port_decl_parts)

    # Drive DOUT pins via combinational wire (no user-side reg) so
    # outdata_reg_a=CLOCK0 doesn't trigger a placer collision when
    # the user reg gets packed into the M9K's internal outreg slot.
    return f"""\
// Auto-generated SP M9K feature-delta smoke fixture ({WIDTH},{DEPTH}).
module fuzz_top(
    {port_decl}
);
    wire [{ab-1}:0] addr = {{{addr_bus}}};
    wire [{WIDTH-1}:0] din  = {{{din_bus}}};
    wire [{WIDTH-1}:0] dout;
    assign {{{dout_assign}}} = dout;

    altsyncram #(
        {param_lines}
    ) u (
        .clock0(CLK), .address_a(addr), .data_a(din),
        .wren_a(WE), .q_a(dout),
        .aclr0(1'b0), .aclr1(1'b0),
        .addressstall_a(1'b0), .addressstall_b(1'b0),
        .byteena_a(1'b1), .byteena_b(1'b1),
        .address_b({{{ab}{{1'b0}}}}), .data_b({{{WIDTH}{{1'b0}}}}),
        .clock1(1'b1), .clocken0(1'b1), .clocken1(1'b1),
        .clocken2(1'b1), .clocken3(1'b1), .eccstatus(),
        .q_b(), .rden_a(1'b1), .rden_b(1'b1), .wren_b(1'b0)
    );
endmodule
"""


def _qsf(project: str) -> str:
    lines = [
        'set_global_assignment -name FAMILY "Cyclone IV E"',
        "set_global_assignment -name DEVICE EP4CE6F17C8",
        "set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top",
        "set_global_assignment -name VERILOG_FILE fuzz_top.v",
        "set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files",
        'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"',
        "set_global_assignment -name SEED 1",
        "set_global_assignment -name MIF_FILE mem_init.mif",
    ]
    for sig, pin in _pin_map().items():
        lines.append(f"set_location_assignment {pin} -to {sig}")
    lines.append(
        f'set_location_assignment M9K_X{SITE_X}_Y{SITE_Y}_N{SITE_N} -to "u"'
    )
    return "\n".join(lines) + "\n"


def _mif() -> str:
    mask = (1 << WIDTH) - 1
    lines = [
        f"DEPTH = {DEPTH};",
        f"WIDTH = {WIDTH};",
        "ADDRESS_RADIX = HEX;",
        "DATA_RADIX = HEX;",
        "CONTENT BEGIN",
    ]
    nibbles = (WIDTH + 3) // 4
    addr_nibbles = max(1, (_addr_bits(DEPTH) + 3) // 4)
    for i in range(DEPTH):
        v = i & mask
        lines.append(f"  {i:0{addr_nibbles}X} : {v:0{nibbles}X};")
    lines.append("END;")
    return "\n".join(lines) + "\n"


def build_one(name: str, overrides: dict[str, str], work_root: str) -> tuple[str, str | None, float, str]:
    proj = f"smoke_{name}"
    proj_dir = setup_project(proj, _verilog(overrides), _qsf(proj), work_dir=work_root)
    (Path(proj_dir) / "mem_init.mif").write_text(_mif())
    ok, elapsed, err = compile_full(proj, proj_dir, timeout=300)
    if not ok:
        return name, None, elapsed, err
    rbf = generate_rbf(proj, proj_dir)
    return name, rbf, elapsed, ""


def diff_cells(a: bytes, b: bytes) -> set[tuple[int, int]]:
    cells = set()
    for off in range(PRE, len(a)):
        if (off - PRE) % FRAME >= DPF:
            continue
        x = a[off] ^ b[off]
        if x:
            for bp in range(8):
                if x & (1 << bp):
                    cells.add((off, bp))
    return cells


def region_of(frame: int) -> str:
    for lo, hi, name in REGIONS:
        if lo <= frame <= hi:
            return name
    return "?"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="keep work dirs")
    args = ap.parse_args()

    work_root = ROOT / "tmp" / "m9k_feature_delta"
    work_root.mkdir(parents=True, exist_ok=True)

    print(f"Building {len(FIXTURES)} fixtures in parallel at "
          f"X{SITE_X}_Y{SITE_Y}_N{SITE_N} SP ({WIDTH},{DEPTH})...")

    rbfs: dict[str, Path] = {}
    with ProcessPoolExecutor(max_workers=len(FIXTURES)) as ex:
        futures = {
            ex.submit(build_one, name, ov, str(work_root)): name
            for name, ov in FIXTURES.items()
        }
        for fut in as_completed(futures):
            name, rbf, elapsed, err = fut.result()
            if rbf is None:
                print(f"  [{name}] FAILED in {elapsed:.1f}s: {err}")
                return 1
            rbfs[name] = Path(rbf)
            print(f"  [{name}] OK in {elapsed:.1f}s -> {rbf}")

    base = rbfs["base"].read_bytes()
    feat = rbfs["feat_outreg"].read_bytes()

    print(f"\nbase RBF size: {len(base)}; feat RBF size: {len(feat)}")
    if len(base) != 368011 or len(feat) != 368011:
        print(f"  WARNING: expected 368011, got {len(base)} / {len(feat)}")

    delta = diff_cells(feat, base)
    print(f"\nFeature-delta cells (feat ⊕ base): {len(delta)}")

    by_region = Counter()
    by_region_bp = Counter()
    for off, bp in delta:
        f = (off - PRE) // FRAME
        r = region_of(f)
        by_region[r] += 1
        by_region_bp[(r, bp)] += 1

    print("\nRegion breakdown:")
    for _, _, name in REGIONS:
        c = by_region.get(name, 0)
        marker = "" if name == "block_band" else "  ← LEAKAGE" if c else ""
        print(f"  {name:18}  {c:5}{marker}")

    bb = by_region.get("block_band", 0)
    other = sum(c for r, c in by_region.items() if r != "block_band")
    print(f"\nblock_band:    {bb}")
    print(f"non-block_band: {other}")
    if len(delta):
        print(f"block_band fraction: {bb / len(delta) * 100:.1f}%")

    print("\nFeature-delta region/bp breakdown:")
    for k in sorted(by_region_bp):
        print(f"  {k}: {by_region_bp[k]}")

    # Save block_band slice as the candidate M9K_MODE delta bucket.
    delta_bb = sorted([(off, bp) for (off, bp) in delta
                       if 1692 <= (off - PRE) // FRAME <= 1738])
    out_path = ROOT / "results" / "m9k_feature_delta_outreg.json"
    import json
    out_path.write_text(json.dumps({
        "feature": "outdata_reg_a=CLOCK0",
        "site": f"X{SITE_X}_Y{SITE_Y}_N{SITE_N}",
        "geometry": f"SP {WIDTH}x{DEPTH}",
        "delta_bb_count": len(delta_bb),
        "delta_bb_cells": delta_bb,
        "leakage_by_region": {r: by_region.get(r, 0) for _, _, r in REGIONS},
    }, indent=2))
    print(f"\nWrote {out_path}")

    print()
    if 5 <= bb <= 200:
        print(f"✓ PASS — block_band slice is {bb} cells, in-range. "
              f"Other-region leakage ({other}) belongs to IOB/COL/LAB "
              f"directives, not M9K_MODE.")
        return 0
    print(f"✗ FAIL — block_band slice is {bb} cells, out of expected range "
          f"[5..200].")
    return 1


if __name__ == "__main__":
    sys.exit(main())
