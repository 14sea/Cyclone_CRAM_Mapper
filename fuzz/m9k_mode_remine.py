# SPDX-License-Identifier: GPL-3.0-or-later
"""Stage 2(a): clean per-site M9K_MODE_18x512 re-mine via specimen factory.

Background
----------
The original `m9k_mode_mine.py` analyzer diffed per-site
`m9k_calib18b_*_base.rbf` against `nv_zero_global.rbf` — but those two
RBFs use *different* harnesses (calib18b has 47 SDRAM-bus pins; nv_zero
has none). Every harness-induced cell that lands in the block band
(frames 1692-1738) leaks into the "per-site MODE" set, and emitting
the polluted bits on the smoke design worsens its m9k-band byte diff
from 43 → 86.

This script uses the X-Ray specimen pattern via fuzz/specimen_base:
  * one harness-only baseline (same 47 pins, NO altsyncram instance)
  * five per-site specimens (M9K@X15_Y{10..14} width=18) sharing the
    same harness
  * per-site MODE = block-band(per-site ⊕ baseline) — harness cells
    cancel because both builds carry them identically

Output: results/m9k_mode_bits.json (overwritten with clean entries
for the 5 width=18 sites; width=9 entries left untouched).

Acceptance gate (printed):
  XOR-union of the 5 clean per-site MODE sets vs the actual Quartus
  smoke gold (tmp/m9k_smoke/ram_9x512.rbf vs nv_zero_global, restricted
  to block band) — gap should be ≤ 5 cells. If wider, the per-site
  decomposition is leaky and emission must stay gated.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from rbf_diff import diff_rbf_files
from specimen_base import Harness, Specimen


WIDTH = 18
DEPTH = 512
ADDR_BITS = 9
SITES_Y = (10, 11, 12, 13, 14)
M9K_X = 15
BLOCK_FRAME_LO = 1692
BLOCK_FRAME_HI = 1738
PREAMBLE = 32
FRAME = 210


# Same EXTRA_PINS layout as scripts/m9k_calib/calibrate_18x512_batch.py.
# Sized for ADDR(9) + DIN(18) + DOUT(18) + clk + wren = 47 pins.
_FREE_PINS = [
    # SDRAM data bus (16)
    "PIN_R5", "PIN_T4", "PIN_T3", "PIN_R3", "PIN_T2", "PIN_R1", "PIN_P2", "PIN_P1",
    "PIN_R13", "PIN_T13", "PIN_R12", "PIN_T12", "PIN_T10", "PIN_R10", "PIN_T11", "PIN_R11",
    # SDRAM addr bus (13)
    "PIN_T8", "PIN_P9", "PIN_T9", "PIN_R9", "PIN_L16", "PIN_L15", "PIN_N16", "PIN_N15",
    "PIN_P16", "PIN_P15", "PIN_R8", "PIN_R16", "PIN_T15",
    # AX301 left bank misc (16)
    "PIN_C15", "PIN_B16", "PIN_A15", "PIN_B14", "PIN_A14", "PIN_B13", "PIN_A13", "PIN_B12",
    "PIN_A12", "PIN_B11", "PIN_A11", "PIN_B10", "PIN_A10", "PIN_B9", "PIN_A9", "PIN_B8",
    # spillover
    "PIN_A8",
    "PIN_M16", "PIN_F15", "PIN_G15", "PIN_F16", "PIN_G16",
]


def _build_pin_map() -> dict[str, str]:
    pins = {"clk": "PIN_E1", "wren": "PIN_E15"}
    for i in range(ADDR_BITS):
        pins[f"addr{i}"] = _FREE_PINS[i]
    for i in range(WIDTH):
        pins[f"din{i}"] = _FREE_PINS[ADDR_BITS + i]
    for i in range(WIDTH):
        pins[f"dout{i}"] = _FREE_PINS[ADDR_BITS + WIDTH + i]
    return pins


PIN_MAP = _build_pin_map()


def _make_harness() -> Harness:
    return Harness(
        iob_pins=tuple(PIN_MAP.items()),
        clk_signal="clk",
        seed=1,
        name="m9k_calib18b",
    )


def _port_decl() -> str:
    parts = ["input clk", "input wren"]
    parts += [f"input addr{i}" for i in range(ADDR_BITS)]
    parts += [f"input din{i}" for i in range(WIDTH)]
    parts += [f"output dout{i}" for i in range(WIDTH)]
    return ",\n    ".join(parts)


def _verilog_with_m9k(width: int = WIDTH, depth: int = DEPTH) -> str:
    """A real altsyncram instance — to be LOC'd via Specimen.extra_pins."""
    addr_bus = ", ".join(f"addr{i}" for i in range(ADDR_BITS - 1, -1, -1))
    din_bus = ", ".join(f"din{i}" for i in range(width - 1, -1, -1))
    dout_bus = ", ".join(f"dout{i}" for i in range(width - 1, -1, -1))
    return f"""\
module fuzz_top(
    {_port_decl()}
);
    wire [{ADDR_BITS-1}:0] addr = {{{addr_bus}}};
    wire [{width-1}:0]     din  = {{{din_bus}}};
    wire [{width-1}:0]     dout;
    assign {{{dout_bus}}} = dout;

    altsyncram #(
        .operation_mode("SINGLE_PORT"),
        .width_a({width}), .widthad_a({ADDR_BITS}), .numwords_a({depth}),
        .lpm_type("altsyncram"),
        .ram_block_type("M9K"),
        .outdata_reg_a("UNREGISTERED"),
        .intended_device_family("Cyclone IV E")
    ) u (
        .clock0(clk), .address_a(addr), .data_a(din),
        .wren_a(wren), .q_a(dout),
        .aclr0(1'b0), .aclr1(1'b0),
        .addressstall_a(1'b0), .addressstall_b(1'b0),
        .byteena_a(1'b1), .byteena_b(1'b1),
        .address_b({{{ADDR_BITS}{{1'b0}}}}), .data_b({{{width}{{1'b0}}}}),
        .clock1(1'b1), .clocken0(1'b1), .clocken1(1'b1),
        .clocken2(1'b1), .clocken3(1'b1), .eccstatus(),
        .q_b(), .rden_a(1'b1), .rden_b(1'b1), .wren_b(1'b0)
    );
endmodule
"""


def _verilog_baseline_no_m9k() -> str:
    """Same pin signature, no altsyncram — combinational passthrough.

    Quartus still routes IOB-to-IOB combinational paths, so the harness
    cells (IOB pads, local clock for E1) are present identically to the
    per-site builds. Block band stays empty (no M9K → no MODE bits).
    """
    parts = []
    for i in range(WIDTH):
        parts.append(f"    assign dout{i} = din{i};")
    body = "\n".join(parts)
    # `clk`, `wren`, addr0..8 are unused in the passthrough but must remain
    # declared so the pin assignments still apply.
    return f"""\
module fuzz_top(
    {_port_decl()}
);
{body}
endmodule
"""


class M9kSpecimen(Specimen):
    """Specimen subclass that emits the M9K LOC line in render_qsf."""

    def __init__(self, m9k_loc: str | None, **kw):
        super().__init__(**kw)
        self._m9k_loc = m9k_loc

    def render_qsf(self) -> str:
        qsf = super().render_qsf()
        if self._m9k_loc is not None:
            qsf += f'set_location_assignment {self._m9k_loc} -to "u"\n'
        return qsf


def _make_baseline_specimen(harness: Harness) -> M9kSpecimen:
    return M9kSpecimen(
        m9k_loc=None,
        name="m9k_remine_baseline",
        harness=harness,
        verilog=_verilog_baseline_no_m9k(),
        placement={},
    )


def _make_site_specimen(harness: Harness, site_y: int) -> M9kSpecimen:
    return M9kSpecimen(
        m9k_loc=f"M9K_X{M9K_X}_Y{site_y}_N0",
        name=f"m9k_remine_X{M9K_X}_Y{site_y}",
        harness=harness,
        verilog=_verilog_with_m9k(),
        placement={},
    )


def _block_band_cells(rbf_a: bytes, rbf_b: bytes) -> set[tuple[int, int]]:
    """XOR-diff restricted to block band frames AND non-CRC bytes."""
    out: set[tuple[int, int]] = set()
    a, b = rbf_a, rbf_b
    if len(a) != len(b):
        raise ValueError(f"length mismatch: {len(a)} vs {len(b)}")
    # Walk only the block-band byte range.
    lo = PREAMBLE + BLOCK_FRAME_LO * FRAME
    hi = PREAMBLE + (BLOCK_FRAME_HI + 1) * FRAME
    for off in range(lo, hi):
        if (off - PREAMBLE) % FRAME >= 208:
            continue
        x = a[off] ^ b[off]
        if not x:
            continue
        for bit in range(8):
            if x & (1 << bit):
                out.add((off, bit))
    return out


def _block_band_cells_from_paths(path_a: Path, path_b: Path) -> set[tuple[int, int]]:
    return _block_band_cells(path_a.read_bytes(), path_b.read_bytes())


def main() -> int:
    work = ROOT / "tmp" / "m9k_mode_remine"
    work.mkdir(parents=True, exist_ok=True)
    harness = _make_harness()

    print(f"[remine] M9K_MODE 18x512 clean re-mine via specimen factory")
    print(f"[remine] work_dir = {work}")
    print(f"[remine] sites    = {[f'X{M9K_X}_Y{y}_N0' for y in SITES_Y]}\n")

    # 1. baseline build
    t0 = time.time()
    baseline = _make_baseline_specimen(harness)
    print(f"[remine] building no-M9K baseline …")
    bl_rbf = baseline.build(work)
    print(f"  -> {bl_rbf.name}  ({time.time()-t0:.1f}s)\n")

    # 2. five per-site builds
    site_rbfs: dict[int, Path] = {}
    for y in SITES_Y:
        t0 = time.time()
        spec = _make_site_specimen(harness, y)
        print(f"[remine] building M9K@X{M9K_X}_Y{y}_N0 …")
        rbf = spec.build(work)
        site_rbfs[y] = rbf
        print(f"  -> {rbf.name}  ({time.time()-t0:.1f}s)")

    # 3. derive per-site MODE
    bl_bytes = bl_rbf.read_bytes()
    per_site: dict[int, set[tuple[int, int]]] = {}
    for y in SITES_Y:
        cells = _block_band_cells(bl_bytes, site_rbfs[y].read_bytes())
        per_site[y] = cells
        print(f"  Y{y}: {len(cells)} block-band cells")

    # 4. compose XOR-union and compare against Quartus smoke gold.
    union: set[tuple[int, int]] = set()
    for s in per_site.values():
        union ^= s
    print(f"\n[remine] XOR-union over 5 sites = {len(union)} cells")

    nv = (ROOT / "results" / "rbf" / "nv_zero_global.rbf")
    gold = (ROOT / "tmp" / "m9k_smoke" / "ram_9x512.rbf")
    gold_mode = _block_band_cells_from_paths(nv, gold)
    print(f"[remine] Quartus smoke gold MODE  = {len(gold_mode)} cells")

    common = union & gold_mode
    only_union = union - gold_mode
    only_gold = gold_mode - union
    print(f"[remine] match    = {len(common)}")
    print(f"[remine] false on = {len(only_union)} (open will set, gold doesn't)")
    print(f"[remine] missed   = {len(only_gold)} (gold has, open won't set)")
    gap = len(only_union) + len(only_gold)
    print(f"[remine] symmetric gap = {gap} cells (acceptance: ≤5)")

    # 5. write the new mode-bits JSON, but only for these 5 sites.
    out_path = ROOT / "results" / "m9k_mode_bits.json"
    if out_path.exists():
        existing = json.loads(out_path.read_text())
    else:
        existing = {}
    for y in SITES_Y:
        key = f"X{M9K_X}_Y{y}_N0_18x512"
        existing[key] = {
            "site": f"X{M9K_X}_Y{y}_N0",
            "width": WIDTH,
            "depth": DEPTH,
            "cells": sorted([list(c) for c in per_site[y]]),
            "source": site_rbfs[y].name,
            "method": "specimen_factory_2026_04_16",
            "baseline": bl_rbf.name,
        }
    out_path.write_text(json.dumps(existing, indent=1) + "\n")
    print(f"\n[remine] wrote {out_path}")

    return 0 if gap <= 5 else 1


if __name__ == "__main__":
    sys.exit(main())
