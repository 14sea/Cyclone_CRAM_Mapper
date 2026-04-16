# SPDX-License-Identifier: GPL-3.0-or-later
"""Stage 3 diagnostic — can the X-Ray specimen factory mine clean self-loop
sig-cache entries?

Background (CLAUDE.md pitfall #9): the 61 self-loop entries in
`results/route_cells_full.json` are bloated noise (90-754 cells vs corpus
median 131). The original two-LUT mining template can't represent
src==dst, and a diff-based selfloop_factory got refit by Quartus between
baseline and perturbed builds.

This probe asks: with `specimen_base.Specimen` (frozen placement, fixed
SEED, OPT_OFF), can a single-LE registered design produce a clean
diff between (a) external-input-driven FF and (b) self-feedback FF?

Single-axis perturbation: the source wire driving the LCCOMB's `datab`
input.

  * Baseline: `datab = A` (external IOB), so the route is
    "IOB(PIN_E16) → LE(x,y,n).datab".
  * Perturbed: `datab = q_reg` (self-feedback), so the route is
    "LE(x,y,n).regout → LE(x,y,n).datab" — exactly the self-loop arc
    keyed in route_cells_full.json as "x,y,n->x,y,n,datab".

Acceptance:
  * `routing_invariance_probe` returns True on both specimens.
  * `diff_cram(baseline, perturbed)` produces ≤ ~150 CRAM cells (corpus
    median for clean entries) once IOB-fanout cells are subtracted.
  * The diff is concentrated in the LAB column of the target LE (NOT
    spread across multiple LAB columns, which would indicate Quartus
    routing churn).

If those hold, the same template can be applied to all 61 entries.
If not, the result documents *why* self-loops are fundamentally hard.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from config import PREAMBLE_BYTES
from specimen_base import (
    Harness,
    Specimen,
    diff_cram,
    routing_invariance_probe,
)


_VERILOG_TMPL = """\
module fuzz_top(
    input  wire CLK,
    output wire Q
);
    wire combout;
    reg  q_reg /* synthesis preserve */;

    cycloneive_lcell_comb #(
        .lut_mask(16'hCCCC),
        .dont_touch("on")
    ) lut_inst (
        .dataa(1'b0),
        .datab({datab_src}),
        .datac(1'b0),
        .datad(1'b0),
        .combout(combout)
    );

    always @(posedge CLK) q_reg <= combout;
    assign Q = q_reg;
endmodule
"""

# Baseline uses a constant on the target port — no fabric route at all,
# so the perturbed-vs-baseline diff is the *absolute* set of cells the
# self-loop arc activates (not a delta against another route).
_BASELINE_DATAB = "1'b0"
_FEEDBACK_DATAB = "q_reg"


def _harness() -> Harness:
    """Minimal: CLK in, Q out only. No data IOBs — eliminates the
    IOB-route-source drift that otherwise dominates the per-seed CRAM
    diff (the unused A pin has multiple SEED-equivalent fabric paths)."""
    return Harness(
        iob_pins=(("CLK", "PIN_E1"), ("Q", "PIN_G15")),
        clk_signal="CLK",
        seed=1,
        name="selfloop_probe_minimal",
    )


def baseline_spec(target_le: tuple[int, int, int]) -> Specimen:
    return Specimen(
        name=f"sl_base_X{target_le[0]}Y{target_le[1]}N{target_le[2]}",
        harness=_harness(),
        verilog=_VERILOG_TMPL.format(datab_src=_BASELINE_DATAB),
        placement={"lut_inst": target_le},
    )


def feedback_spec(target_le: tuple[int, int, int]) -> Specimen:
    return Specimen(
        name=f"sl_fb_X{target_le[0]}Y{target_le[1]}N{target_le[2]}",
        harness=_harness(),
        verilog=_VERILOG_TMPL.format(datab_src=_FEEDBACK_DATAB),
        placement={"lut_inst": target_le},
    )


def _column_histogram(cells: set[tuple[int, int]]) -> dict[int, int]:
    """Bucket CRAM cells by frame (off - PREAMBLE_BYTES) // 210."""
    hist: dict[int, int] = {}
    for off, _bp in cells:
        frame = (off - PREAMBLE_BYTES) // 210
        hist[frame] = hist.get(frame, 0) + 1
    return hist


def _frame_span_summary(cells: set[tuple[int, int]]) -> str:
    if not cells:
        return "(empty)"
    frames = sorted(set((off - PREAMBLE_BYTES) // 210 for off, _ in cells))
    return f"frames {frames[0]}..{frames[-1]} (span {frames[-1] - frames[0]}, {len(frames)} unique)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--le", default="10,4,0",
                    help="target LE as X,Y,N (default 10,4,0)")
    ap.add_argument("--work", default=None,
                    help="work dir (default: tmp/selfloop_probe)")
    ap.add_argument("--skip-invariance", action="store_true",
                    help="skip routing-invariance probes (faster smoke)")
    args = ap.parse_args()

    x, y, n = (int(v) for v in args.le.split(","))
    target = (x, y, n)
    if args.work:
        work = Path(args.work)
    else:
        work = HERE.parent / "tmp" / "selfloop_probe"
    work.mkdir(parents=True, exist_ok=True)
    print(f"target LE: X{x}Y{y}N{n}")
    print(f"work dir : {work}")

    base = baseline_spec(target)
    fb = feedback_spec(target)

    if not args.skip_invariance:
        print("\n--- baseline routing-invariance probe (3 seeds) ---")
        ok_b, drift_b = routing_invariance_probe(base, work / "invar_base", n_seeds=3)
        print(f"  invariant: {ok_b}, drift cells: {len(drift_b)}")
        if drift_b:
            print(f"  drift {_frame_span_summary(drift_b)}")
        print("\n--- feedback routing-invariance probe (3 seeds) ---")
        ok_f, drift_f = routing_invariance_probe(fb, work / "invar_fb", n_seeds=3)
        print(f"  invariant: {ok_f}, drift cells: {len(drift_f)}")
        if drift_f:
            print(f"  drift {_frame_span_summary(drift_f)}")
    else:
        print("\n(invariance probes skipped)")

    print("\n--- single-axis diff (baseline ⊕ feedback, seed=1) ---")
    base_rbf = base.build(work / "base").read_bytes()
    fb_rbf = fb.build(work / "fb").read_bytes()
    cells = diff_cram(base_rbf, fb_rbf)
    print(f"  diff CRAM cells: {len(cells)}")
    print(f"  {_frame_span_summary(cells)}")
    hist = _column_histogram(cells)
    top5 = sorted(hist.items(), key=lambda kv: -kv[1])[:5]
    print(f"  top frames by cell count: {top5}")

    # Multi-seed intersection: cells that consistently flip across N seeds
    # filter out the IOB-route SEED noise. Real self-loop bits should
    # appear in every (base_seed_i ⊕ fb_seed_i) pair.
    print("\n--- multi-seed intersection diff (3 seeds) ---")
    from dataclasses import replace
    diffs = [cells]
    for s in (2, 3):
        base_s = replace(base, harness=base.harness.with_seed(s))
        fb_s = replace(fb, harness=fb.harness.with_seed(s))
        b_rbf = base_s.build(work / f"base_s{s}").read_bytes()
        f_rbf = fb_s.build(work / f"fb_s{s}").read_bytes()
        d = diff_cram(b_rbf, f_rbf)
        diffs.append(d)
        print(f"  seed={s}: {len(d)} cells, "
              f"intersection so far = {len(set.intersection(*diffs))}")
    clean = set.intersection(*diffs)
    print(f"  clean (∩ over 3 seeds): {len(clean)} cells")
    print(f"  {_frame_span_summary(clean)}")
    hist_clean = _column_histogram(clean)
    print(f"  top frames: {sorted(hist_clean.items(), key=lambda kv: -kv[1])[:5]}")

    # Compare to existing route_cells_full.json self-loop entry for context
    import json
    rcf = json.loads((HERE.parent / "results" / "route_cells_full.json").read_text())
    key_b = f"{x},{y},{n}->{x},{y},{n},datab"
    if key_b in rcf:
        legacy = rcf[key_b]
        n_legacy = len(legacy) if isinstance(legacy, list) else len(legacy.get("cells", []))
        print(f"\n  legacy {key_b}: {n_legacy} cells")
        # Convert legacy to set for overlap check
        legacy_set = set()
        for entry in (legacy if isinstance(legacy, list) else legacy.get("cells", [])):
            if isinstance(entry, list) and len(entry) == 2:
                legacy_set.add(tuple(entry))
        if legacy_set:
            shared_raw = cells & legacy_set
            shared_clean = clean & legacy_set
            print(f"  raw   ∩ legacy: {len(shared_raw):4d} "
                  f"({100 * len(shared_raw) / max(len(cells), 1):.1f}% of raw, "
                  f"{100 * len(shared_raw) / len(legacy_set):.1f}% of legacy)")
            print(f"  clean ∩ legacy: {len(shared_clean):4d} "
                  f"({100 * len(shared_clean) / max(len(clean), 1):.1f}% of clean, "
                  f"{100 * len(shared_clean) / len(legacy_set):.1f}% of legacy)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
