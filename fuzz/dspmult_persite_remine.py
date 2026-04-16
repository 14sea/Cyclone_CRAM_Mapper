# SPDX-License-Identifier: GPL-3.0-or-later
"""Stage 2(b) — DSPMULT per-site clean re-mine via specimen factory.

Background: the original per-site RBFs at
`results/rbf/mult_loc_DSPMULT_X20_Y{y}_N{n}.rbf` and
`results/rbf/mult_empty_baseline.rbf` were built with `mult_loc_test.py`
+ `mult_empty_baseline.py`, which call `compile_and_export` directly
without `QSF_OPTIMIZATIONS_OFF` or a fixed `SEED`. Quartus then refits
freely between baseline and per-site builds, leaking ~223 cells of
routing churn into the data band of every diff (per
`fuzz/dspmult_persite_analyze.py` 2026-04-16). The 29-cell intersection
across all 42 sites is the only directly-trustable subset; per-site MODE
cells are contaminated.

This probe rebuilds via `specimen_base.Specimen`/`Harness`, which
applies `QSF_OPTIMIZATIONS_OFF` and pins SEED. Same 6-pin layout as
the legacy mult_loc_test.py harness so analyzer code keeps working.

Run modes:
  --probe         (default) 1 baseline + 1 site (Y=10,N=0). ~30s.
                  Acceptance: data-band leak ≤ 10 cells. If the probe
                  passes, the harness is tight enough to do the full
                  42-site sweep.
  --full          1 baseline + 42 sites (Y∈[1..21], N∈{0,1}). ~7-8 min
                  serial. Writes to results/rbf/ over the existing
                  contaminated files.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from specimen_base import Harness, Specimen, diff_cram_files


# 6-pin layout — copied verbatim from fuzz/mult_loc_test.py so the
# baseline IOB topology matches what the original mining used (and so
# the analyzer's data-band semantics line up).
PIN_MAP = {
    "clk": "PIN_E1",
    "a0":  "PIN_E16",
    "a1":  "PIN_M16",
    "b0":  "PIN_M15",
    "b1":  "PIN_E15",
    "p0":  "PIN_G15",
}

NODE = "lpm_mult:u|mult_qpl:auto_generated|mac_mult1"

HDR = 32
FRAME = 210
BLOCK_LO, BLOCK_HI = 1692, 1738


def _harness() -> Harness:
    return Harness(
        iob_pins=tuple(PIN_MAP.items()),
        clk_signal="clk",
        seed=1,
        name="dspmult_remine",
    )


def _verilog_with_mult() -> str:
    return """\
module fuzz_top(
    input clk, input a0, input a1, input b0, input b1,
    output p0
);
    wire [8:0] a = {7'b0, a1, a0};
    wire [8:0] b = {7'b0, b1, b0};
    wire [17:0] p;
    lpm_mult #(
        .lpm_widtha(9), .lpm_widthb(9), .lpm_widthp(18),
        .lpm_representation("UNSIGNED"),
        .lpm_type("LPM_MULT")
    ) u (.dataa(a), .datab(b), .result(p));
    assign p0 = ^p;
endmodule
"""


def _verilog_baseline() -> str:
    """No-mult baseline. Same 6 pins; trivial combinational logic so
    Quartus has something to drive p0 with."""
    return """\
module fuzz_top(
    input clk, input a0, input a1, input b0, input b1, output p0
);
    assign p0 = (a0 & b0) ^ (a1 & b1);
endmodule
"""


class DspmultSpecimen(Specimen):
    """Specimen that adds a `set_location_assignment` for the lpm_mult
    instance into the QSF (analogous to M9kSpecimen in m9k_mode_remine_w9)."""

    def __init__(self, mult_loc: str | None, **kw):
        super().__init__(**kw)
        self._mult_loc = mult_loc

    def render_qsf(self) -> str:
        qsf = super().render_qsf()
        if self._mult_loc is not None:
            qsf += f'set_location_assignment {self._mult_loc} -to "{NODE}"\n'
        return qsf


def _block_data_split(cells: set[tuple[int, int]]) -> tuple[set, set]:
    """Split CRAM cells into (block_band, data_band) buckets."""
    block, data = set(), set()
    for off, bit in cells:
        fr = (off - HDR) // FRAME
        c = (off, bit)
        if BLOCK_LO <= fr <= BLOCK_HI:
            block.add(c)
        elif 25 <= fr < BLOCK_LO or BLOCK_HI < fr <= 1751:
            data.add(c)
    return block, data


def _build_baseline(work: Path) -> Path:
    """Build the no-mult baseline; copy to results/rbf/mult_empty_baseline.rbf."""
    spec = DspmultSpecimen(
        mult_loc=None,
        name="dspmult_empty_baseline",
        harness=_harness(),
        verilog=_verilog_baseline(),
        placement={},
    )
    print("[remine] building no-mult baseline …")
    t0 = time.time()
    rbf = spec.build(work)
    print(f"  -> {rbf.name}  ({time.time()-t0:.1f}s)")
    out = ROOT / "results" / "rbf" / "mult_empty_baseline.rbf"
    out.write_bytes(rbf.read_bytes())
    print(f"  -> copied to {out}")
    return out


def _build_site(work: Path, y: int, n: int) -> Path:
    loc = f"DSPMULT_X20_Y{y}_N{n}"
    spec = DspmultSpecimen(
        mult_loc=loc,
        name=f"dspmult_X20_Y{y}_N{n}",
        harness=_harness(),
        verilog=_verilog_with_mult(),
        placement={},
    )
    t0 = time.time()
    rbf = spec.build(work)
    print(f"  Y={y:>2} N={n}  -> {rbf.name}  ({time.time()-t0:.1f}s)")
    out = ROOT / "results" / "rbf" / f"mult_loc_{loc}.rbf"
    out.write_bytes(rbf.read_bytes())
    return out


def cmd_probe() -> int:
    """Two probes back-to-back:

      Probe-A: baseline = no-mult     vs site = mult@Y=10,N=0
              (legacy approach; expects ~200 cell data leak from `^p`
              reduction not present in baseline).
      Probe-B: baseline = mult@Y=1,N=0 vs site = mult@Y=10,N=0
              (site-vs-site; `^p` reduction LE topology identical, only
              mult position varies → diff isolates MODE migration).

    Acceptance: probe-B data band ≤ 10 cells.
    """
    work = ROOT / "tmp" / "dspmult_remine_probe"
    work.mkdir(parents=True, exist_ok=True)
    print("[remine] PROBE — A:no-mult-vs-site + B:site-vs-site")
    print(f"[remine] work_dir = {work}\n")

    bl_path = _build_baseline(work)
    print()
    print("[remine] building site Y=10 N=0 …")
    site_path = _build_site(work, 10, 0)
    print("[remine] building site Y=1 N=0 (probe-B baseline) …")
    siteY1_path = _build_site(work, 1, 0)

    print()
    print("=== probe-A: baseline(no-mult) vs site(Y=10,N=0) ===")
    cells_a = diff_cram_files(bl_path, site_path)
    block_a, data_a = _block_data_split(cells_a)
    print(f"  CRAM total: {len(cells_a)}, block: {len(block_a)}, data: {len(data_a)}")

    print()
    print("=== probe-B: site(Y=1,N=0) vs site(Y=10,N=0) ===")
    cells_b = diff_cram_files(siteY1_path, site_path)
    block_b, data_b = _block_data_split(cells_b)
    print(f"  CRAM total: {len(cells_b)}, block: {len(block_b)}, data: {len(data_b)}")
    print(f"  acceptance: probe-B data band ≤ 10 cells")

    if len(data_b) <= 10:
        print(f"\n[remine] PROBE-B PASS — site-vs-site diff is clean.")
        print(f"[remine] Recommend: change analyzer baseline to a fixed mult site,")
        print(f"         or skip per-site mining and land 29-cell DSPMULT_GLOBAL_ON only.")
        return 0
    print(f"\n[remine] PROBE-B FAIL — data leak {len(data_b)} > 10.")
    print(f"[remine] Per-site MODE mining structurally hard. Recommend: land")
    print(f"         DSPMULT_GLOBAL_ON 29-cell template only; gate per-site.")
    return 1


def cmd_full() -> int:
    work = ROOT / "tmp" / "dspmult_remine_full"
    work.mkdir(parents=True, exist_ok=True)
    print("[remine] FULL — 1 baseline + 42 sites")
    print(f"[remine] work_dir = {work}\n")

    t_total = time.time()
    _build_baseline(work)
    print()
    print("[remine] building 42 sites …")
    for y in range(1, 22):
        for n in (0, 1):
            try:
                _build_site(work, y, n)
            except Exception as e:
                print(f"  Y={y:>2} N={n}  FAIL: {e!s:.120}")
    print()
    print(f"[remine] DONE in {(time.time()-t_total)/60:.1f} min")
    print(f"[remine] re-run `python3 fuzz/dspmult_persite_analyze.py` to score the new diff")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--probe", action="store_true", default=True,
                   help="(default) 1 baseline + 1 site, ≈30s")
    g.add_argument("--full", action="store_true",
                   help="1 baseline + 42 sites, ≈7-8 min serial")
    args = ap.parse_args()

    if args.full:
        return cmd_full()
    return cmd_probe()


if __name__ == "__main__":
    sys.exit(main())
