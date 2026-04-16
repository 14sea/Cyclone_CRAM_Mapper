# SPDX-License-Identifier: GPL-3.0-or-later
"""Stage C.1 — M9K_MODE template-style 3-way probe.

Goal: determine whether the 29-cell M9K_MODE block-band residual that
Stage 2(a).D found between altsyncram-direct mining and Quartus
inferred-RAM smoke gold is closed by switching the mining specimen to
Quartus's inferred-RAM idiom (the construct Yosys's
`memory_libmap` → `$__M9K_SP_` → `EP4CE6_M9K` techmap targets).

Three specimens, ALL on the same harness as `m9k_mode_remine_w9.py`:

  1) baseline_w9    — no M9K (existing RBF reused if present)
  2) altsyncram_w9  — altsyncram direct instantiation @ X15_Y10_N0,
                       width=9 depth=512   (= Stage 2(a).D probe)
  3) inferred_w9    — `reg [8:0] mem[0:511]` + (* ramstyle="M9K" *)
                       inferred RAM @ X15_Y10_N0, width=9 depth=512
                       (= Quartus smoke gold construct)

For each pair we report:

  * altsyncram_mode = block_band(altsyncram_w9 ⊕ baseline_w9)
  * inferred_mode   = block_band(inferred_w9   ⊕ baseline_w9)
  * gold_mode       = block_band(smoke_gold    ⊕ baseline_w9)

Outcomes:

  A. inferred_mode ≡ gold_mode (gap ≤5):
     The smoke-build Verilog and the inferred specimen produce
     byte-identical block-band cells (placement, optimizations off, and
     same Verilog idiom yield Quartus-determinism). The 29-cell
     residual is exactly altsyncram-vs-inferred → land sub-flag
     `M9K_MODE_{w}x{d}_inferred` (Yosys path default) vs
     `_altsyncram` (legacy mining). Update m9k_mode_bits.json with
     the inferred set; ungate np2fasm emission against the inferred
     bucket.

  B. inferred_mode ≠ gold_mode but each is close to its own template:
     Two clean buckets exist, just not byte-identical to one specific
     legacy gold. Same sub-flag plan as (A) — np2fasm emits the
     `_inferred` variant since that's what Yosys outputs.

  C. inferred_mode and altsyncram_mode both ≈ same set, neither matches
     gold_mode:
     The 29-cell residual is harness-dependent (something in the smoke
     QSF beyond what we replicate). Stay gated; document and stop.

Hard constraints (`feedback_persite_mining_shared_harness`):

  * Single shared harness across all three specimens.
  * Single axis varies: Verilog idiom (altsyncram direct vs inferred).
  * IOB pinout lifted verbatim from the smoke gold's QSF (same as
    `m9k_mode_remine_w9.py`'s PIN_MAP).

This probe does NOT mutate `results/m9k_mode_bits.json` — it only
reports the diff. The follow-up update (sub-flag wiring, JSON
schema bump) is gated on the probe outcome and lives in
`fasm2rbf.py` + `np2fasm.py`.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

# Reuse harness, smoke-pin map, init MIF, and width-9 verbatim from
# the Stage 2(a).D probe — varying anything else would re-introduce
# the cross-axis contamination class that motivated the rebuild.
from m9k_mode_remine_w9 import (
    PIN_MAP,
    WIDTH,
    DEPTH,
    ADDR_BITS,
    SITE_X,
    SITE_Y,
    BLOCK_FRAME_LO,
    BLOCK_FRAME_HI,
    PREAMBLE,
    FRAME,
    M9kSpecimen,
    _make_harness,
    _make_init_mif,
    _port_decl,
    _verilog_baseline_no_m9k,
    _verilog_with_m9k as _verilog_with_altsyncram,
    _block_band_cells,
)
from specimen_base import Harness
from config import QSF_OPTIMIZATIONS_OFF


def _make_harness_ram_inference() -> Harness:
    """Same harness as `_make_harness()` but with NO QSF optimizations
    disabled — matches the smoke gold's QSF exactly.

    The default `QSF_OPTIMIZATIONS_OFF` list (in `fuzz/config.py`) sets
    `AUTO_RAM_RECOGNITION = OFF` (blocks M9K inference) plus 11 other
    flags (timing-driven synth, register retiming, fitter effort, etc.)
    that the smoke gold leaves at their defaults.

    Empirically (probe v1, 2026-04-16): stripping ONLY
    `AUTO_RAM_RECOGNITION` while keeping the other 11 flags off
    produces 85 MODE cells vs 76 in the smoke gold (gap=83, 46
    inferred-only + 37 gold-only). So the residual is dominated by
    other QSF flags or downstream Quartus heuristics, not the inference
    path itself.

    Probe v2 (this version): drop ALL `QSF_OPTIMIZATIONS_OFF` to match
    the smoke gold's QSF byte-for-byte (modulo SEED + the
    `set_global_assignment ... LAST_QUARTUS_VERSION` line).
    """
    return Harness(
        iob_pins=tuple(PIN_MAP.items()),
        clk_signal="CLK",
        seed=1,
        name="m9k_smoke_w9_no_opts_off",
        optimizations_off=(),
    )


def _verilog_inferred_ram() -> str:
    """Inferred-RAM Verilog targeting Quartus's M9K inference path.

    Two structural variants for the read path are compared in this
    probe (driven by INFERRED_DOUT_REG below):

      "registered"   — `DOUT_r <= mem[addr]; DOUT = DOUT_r;`
                       (matches the smoke gold's exact construct)
      "combinational" — `addr_r <= addr; DOUT = mem[addr_r];`
                        (matches altsyncram's outdata_reg_a("UNREGISTERED"))

    Both are valid M9K inference patterns in Quartus, but the read-
    path register choice is part of the MODE configuration (it lights
    up different block-band bits). We default to "registered" to
    mirror the smoke gold; if Quartus falls back to distributed RAM
    (LAB overflow), we'd retry the comb variant — both fit when
    AUTO_RAM_RECOGNITION is ON.

    INIT pattern matches the smoke design (`mem[i] = i ^ 0x1A5`)
    for data-band consistency.
    """
    # `_port_decl()` declares 29 scalar ports (matches Specimen
    # PIN_MAP convention). The smoke gold declares a single vector
    # `[8:0] ADDR` etc — equivalent at the netlist level, but if
    # Quartus's M9K placer is sensitive to source declarations the
    # block-band cells could move.
    addr_bus = ", ".join(f"ADDR{i}" for i in range(ADDR_BITS - 1, -1, -1))
    din_bus = ", ".join(f"DIN{i}" for i in range(WIDTH - 1, -1, -1))
    dout_bus = ", ".join(f"DOUT{i}" for i in range(WIDTH - 1, -1, -1))
    return f"""\
module fuzz_top(
    {_port_decl()}
);
    wire [{ADDR_BITS-1}:0] addr = {{{addr_bus}}};
    wire [{WIDTH-1}:0]     din  = {{{din_bus}}};
    reg  [{WIDTH-1}:0]     dout_r;
    assign {{{dout_bus}}} = dout_r;

    (* ramstyle = "M9K" *) reg [{WIDTH-1}:0] mem [0:{DEPTH-1}];
    integer i;
    initial begin
        for (i = 0; i < {DEPTH}; i = i + 1)
            mem[i] = i[{WIDTH-1}:0] ^ {WIDTH}'h1A5;
    end
    always @(posedge CLK) begin
        if (WE) mem[addr] <= din;
        dout_r <= mem[addr];
    end
endmodule
"""


def _verilog_inferred_ram_smoke_exact() -> str:
    """**Verbatim** copy of the smoke gold's RAM body
    (`tmp/m9k_smoke/ram_9x512.v`), only the module name changes from
    `ram_9x512` to `fuzz_top` and ports are scalarized to match the
    Specimen factory's PIN_MAP convention.

    Used to test whether the 38-cell inferred-vs-gold residual we see
    with the constructed inferred Verilog (`_verilog_inferred_ram`)
    closes when the Verilog matches the smoke gold byte-for-byte. If
    yes → the residual was Verilog-style noise (Quartus's elaboration
    of `output reg [8:0] DOUT` differs subtly from `wire [8:0] dout`
    + `reg dout_r`). If no → the residual is a structural CE6 / harness
    issue we can't close with Verilog edits.
    """
    addr_bits = ", ".join(f"ADDR{i}" for i in range(ADDR_BITS - 1, -1, -1))
    din_bits = ", ".join(f"DIN{i}" for i in range(WIDTH - 1, -1, -1))
    dout_bits = ", ".join(f"DOUT{i}" for i in range(WIDTH - 1, -1, -1))
    return f"""\
module fuzz_top(
    input  wire        CLK,
    input  wire        WE,
    input  wire        ADDR0, ADDR1, ADDR2, ADDR3, ADDR4, ADDR5, ADDR6, ADDR7, ADDR8,
    input  wire        DIN0,  DIN1,  DIN2,  DIN3,  DIN4,  DIN5,  DIN6,  DIN7,  DIN8,
    output wire        DOUT0, DOUT1, DOUT2, DOUT3, DOUT4, DOUT5, DOUT6, DOUT7, DOUT8
);
    wire [8:0] ADDR = {{{addr_bits}}};
    wire [8:0] DIN  = {{{din_bits}}};
    reg  [8:0] DOUT;
    assign {{{dout_bits}}} = DOUT;

    (* ramstyle = "M9K" *) reg [8:0] mem [0:511];
    integer i;
    initial begin
        for (i = 0; i < 512; i = i + 1)
            mem[i] = i[8:0] ^ 9'h1A5;
    end
    always @(posedge CLK) begin
        if (WE) mem[ADDR] <= DIN;
        DOUT <= mem[ADDR];
    end
endmodule
"""


def _build_or_reuse(specimen: M9kSpecimen, work: Path) -> Path:
    """Reuse an existing RBF if present; otherwise build it."""
    rbf_path = work / f"{specimen.project_name()}.rbf"
    if rbf_path.exists():
        return rbf_path
    t0 = time.time()
    print(f"[probe] building {specimen.name} …")
    out = specimen.build(work)
    print(f"  -> {out.name}  ({time.time()-t0:.1f}s)")
    return out


def main() -> int:
    work = ROOT / "tmp" / "m9k_mode_template_probe"
    work.mkdir(parents=True, exist_ok=True)
    harness = _make_harness()

    print(f"[probe] M9K_MODE template 3-way probe @ X{SITE_X}_Y{SITE_Y}_N0")
    print(f"[probe] work_dir = {work}")
    print(f"[probe] harness pins = {len(PIN_MAP)} (matches smoke)\n")

    baseline = M9kSpecimen(
        m9k_loc=None,
        name="m9k_template_w9_baseline",
        harness=harness,
        verilog=_verilog_baseline_no_m9k(),
        placement={},
    )
    bl_rbf = _build_or_reuse(baseline, work)

    altsyncram = M9kSpecimen(
        m9k_loc=f"M9K_X{SITE_X}_Y{SITE_Y}_N0",
        init_mif=True,
        name=f"m9k_template_w9_altsyncram_X{SITE_X}_Y{SITE_Y}",
        harness=harness,
        verilog=_verilog_with_altsyncram(),
        placement={},
    )
    alt_rbf = _build_or_reuse(altsyncram, work)

    # Inferred specimen needs AUTO_RAM_RECOGNITION enabled — see
    # _make_harness_ram_inference() docstring. Build a paired baseline
    # under the same harness so the same-baseline diff cancels the
    # auto-recognition harness's own footprint (if any).
    harness_ri = _make_harness_ram_inference()
    baseline_ri = M9kSpecimen(
        m9k_loc=None,
        name="m9k_template_w9_baseline_ri",
        harness=harness_ri,
        verilog=_verilog_baseline_no_m9k(),
        placement={},
    )
    bl_ri_rbf = _build_or_reuse(baseline_ri, work)

    # The inferred specimen does NOT use a MIF — the initial block lives
    # inside the Verilog source (matches smoke gold's idiom). init_mif=False
    # so M9kSpecimen.build() doesn't drop a probe_init.mif file.
    inferred = M9kSpecimen(
        m9k_loc=f"M9K_X{SITE_X}_Y{SITE_Y}_N0",
        init_mif=False,
        name=f"m9k_template_w9_inferred_X{SITE_X}_Y{SITE_Y}",
        harness=harness_ri,
        verilog=_verilog_inferred_ram(),
        placement={},
    )
    inf_rbf = _build_or_reuse(inferred, work)

    # Fourth specimen: smoke-gold-exact Verilog (verbatim, just port
    # scalarized). Diagnostic — if this lands at gap≤5 vs gold while
    # the constructed inferred lands at 77, then style alone is the
    # delta.
    inferred_exact = M9kSpecimen(
        m9k_loc=f"M9K_X{SITE_X}_Y{SITE_Y}_N0",
        init_mif=False,
        name=f"m9k_template_w9_inferred_exact_X{SITE_X}_Y{SITE_Y}",
        harness=harness_ri,
        verilog=_verilog_inferred_ram_smoke_exact(),
        placement={},
    )
    inf_exact_rbf = _build_or_reuse(inferred_exact, work)

    # Smoke gold is the existing reference build (Quartus inferred RAM,
    # different harness — but we only diff against ITS gold pair, which
    # is a separate axis from our probe baseline).
    gold = ROOT / "tmp" / "m9k_smoke" / "ram_9x512.rbf"

    bl = bl_rbf.read_bytes()
    bl_ri = bl_ri_rbf.read_bytes()
    al = alt_rbf.read_bytes()
    inf = inf_rbf.read_bytes()
    inf_exact = inf_exact_rbf.read_bytes()
    g = gold.read_bytes()

    # Each MODE diff uses the baseline that was built under its OWN
    # harness — same-baseline diff cancels per-harness footprint.
    alt_mode = _block_band_cells(bl, al)
    inf_mode = _block_band_cells(bl_ri, inf)
    inf_exact_mode = _block_band_cells(bl_ri, inf_exact)
    gold_mode = _block_band_cells(bl, g)

    # Diagnostic: are the two baselines themselves block-band-different?
    # If so, the harness change alone is moving block-band cells, which
    # we'd want to know before drawing conclusions.
    bl_drift = _block_band_cells(bl, bl_ri)
    print(f"\n[probe] baseline drift (RAM-infer harness vs default) = {len(bl_drift)} cells in block band")

    print(f"\n[probe] altsyncram     MODE (alt^baseline)   = {len(alt_mode)} cells")
    print(f"[probe] inferred       MODE (inf^baseline)   = {len(inf_mode)} cells")
    print(f"[probe] inferred-exact MODE (infx^baseline)  = {len(inf_exact_mode)} cells")
    print(f"[probe] smoke-gold     MODE (gold^baseline)  = {len(gold_mode)} cells")

    def _gap(a, b, la, lb):
        inter = a & b
        oa = a - b
        ob = b - a
        gap = len(oa) + len(ob)
        print(f"  {la} vs {lb}: match={len(inter)} {la}-only={len(oa)} "
              f"{lb}-only={len(ob)} sym_gap={gap}")
        return gap, oa, ob

    print("\n[probe] pairwise gaps:")
    gap_ai, _, _ = _gap(alt_mode, inf_mode, "alt", "inf")
    gap_ig, ig_only_inf, ig_only_gold = _gap(inf_mode, gold_mode, "inf", "gold")
    gap_ag, _, _ = _gap(alt_mode, gold_mode, "alt", "gold")
    gap_xg, xg_only_x, xg_only_gold = _gap(inf_exact_mode, gold_mode, "infx", "gold")
    gap_ax, _, _ = _gap(alt_mode, inf_exact_mode, "alt", "infx")
    gap_xi, _, _ = _gap(inf_exact_mode, inf_mode, "infx", "inf")

    universal = alt_mode & inf_mode & gold_mode
    print(f"\n[probe] all-3 universal: {len(universal)} cells")
    print(f"[probe] gold-only (vs alt+inf): {len(gold_mode - alt_mode - inf_mode)}")
    print(f"[probe] alt-only  (vs gold+inf): {len(alt_mode - gold_mode - inf_mode)}")
    print(f"[probe] inf-only  (vs gold+alt): {len(inf_mode - gold_mode - alt_mode)}")

    # Persist the structured findings under results/ — same naming
    # convention as other Stage 2 probes (m9k_mode_t20_probe.json).
    out_path = ROOT / "results" / "m9k_mode_template_probe.json"
    payload = {
        "site": f"X{SITE_X}_Y{SITE_Y}_N0",
        "width": WIDTH,
        "depth": DEPTH,
        "harness": "m9k_smoke_w9 / m9k_smoke_w9_no_opts_off",
        "alt_mode_count": len(alt_mode),
        "inf_mode_count": len(inf_mode),
        "inf_exact_mode_count": len(inf_exact_mode),
        "gold_mode_count": len(gold_mode),
        "alt_vs_inf_sym_gap": gap_ai,
        "inf_vs_gold_sym_gap": gap_ig,
        "alt_vs_gold_sym_gap": gap_ag,
        "infx_vs_gold_sym_gap": gap_xg,
        "alt_vs_infx_sym_gap": gap_ax,
        "infx_vs_inf_sym_gap": gap_xi,
        "universal_count": len(universal),
        "alt_mode_cells": sorted(list(alt_mode)),
        "inf_mode_cells": sorted(list(inf_mode)),
        "inf_exact_mode_cells": sorted(list(inf_exact_mode)),
        "gold_mode_cells": sorted(list(gold_mode)),
        "inf_only_vs_gold": sorted(list(ig_only_inf)),
        "gold_only_vs_inf": sorted(list(ig_only_gold)),
        "infx_only_vs_gold": sorted(list(xg_only_x)),
        "gold_only_vs_infx": sorted(list(xg_only_gold)),
    }
    out_path.write_text(json.dumps(payload, indent=2, default=list))
    print(f"\n[probe] wrote {out_path}")

    # Acceptance: best-of-three ↔ gold ≤5 cells.
    best = min(gap_ig, gap_ag, gap_xg)
    if best <= 5:
        print(f"\n[probe] PASS — best gap = {best} ≤ 5.")
        print("[probe] Closure path: re-mine MODE bits via the matching specimen,")
        print("[probe] update results/m9k_mode_bits.json, ungate np2fasm emission.")
        return 0
    print(f"\n[probe] best gap-vs-gold = {best} > 5 across all 3 specimens.")
    print(f"[probe]   alt-vs-gold  = {gap_ag}")
    print(f"[probe]   inf-vs-gold  = {gap_ig}")
    print(f"[probe]   infx-vs-gold = {gap_xg}")
    print("[probe] Sub-flag path: parameterize directive as")
    print("[probe]   M9K_MODE_{w}x{d}_inferred / _altsyncram (per-template buckets).")
    print("[probe] Or: residual is harness-dependent (placement / pin sensitivity);")
    print("[probe] keep emission gated until a self-consistent template emerges.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
