# SPDX-License-Identifier: GPL-3.0-or-later
"""Stage 2(a).D — width-9 single-site M9K_MODE diagnostic probe.

The first re-mine attempt (`m9k_mode_remine.py`) mined width=18 sites and
tried to predict the smoke design's width=9 MODE bits. That's a hidden
second-axis change — width=9 and width=18 carry different physical MODE
cells. This probe drops to a width-matched comparison:

  Build (under specimen factory + shared harness):
    1) baseline_w9   — same pinout as smoke, NO altsyncram
    2) site_w9       — same pinout as smoke, altsyncram @ X15_Y10_N0,
                       width=9 depth=512

  Predicted MODE  = block-band(site_w9 ⊕ baseline_w9)
  Quartus gold    = block-band(tmp/m9k_smoke/ram_9x512.rbf
                              ⊕ results/rbf/nv_zero_global.rbf)

Acceptance: symmetric gap ≤ 5 cells.

PASS → specimen pattern works for M9K_MODE; proceed to (a).E (full
per-site re-mine across w∈{9,18}, Y=10..14).
FAIL → M9K_MODE is not per-site decomposable from a shared-harness
single-site specimen; route to (a).C fallback.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from specimen_base import Harness, Specimen


WIDTH = 9
DEPTH = 512
ADDR_BITS = 9
SITE_X = 15
SITE_Y = 10
BLOCK_FRAME_LO = 1692
BLOCK_FRAME_HI = 1738
PREAMBLE = 32
FRAME = 210


# Smoke design pinout — copied verbatim from tmp/m9k_smoke/ram_9x512.qsf
# so the specimen and the gold share the SAME IOB topology. Any pin
# substitution would re-introduce the harness-mismatch class of bugs that
# motivated this whole stage.
PIN_MAP = {
    "CLK":     "PIN_E1",
    "WE":      "PIN_M15",
    "ADDR0":   "PIN_E15",
    "ADDR1":   "PIN_E16",
    "ADDR2":   "PIN_M16",
    "ADDR3":   "PIN_A8",
    "ADDR4":   "PIN_A11",
    "ADDR5":   "PIN_A14",
    "ADDR6":   "PIN_B14",
    "ADDR7":   "PIN_T2",
    "ADDR8":   "PIN_T8",
    "DIN0":    "PIN_R1",
    "DIN1":    "PIN_R5",
    "DIN2":    "PIN_R9",
    "DIN3":    "PIN_R13",
    "DIN4":    "PIN_R16",
    "DIN5":    "PIN_P1",
    "DIN6":    "PIN_P9",
    "DIN7":    "PIN_P15",
    "DIN8":    "PIN_T13",
    "DOUT0":   "PIN_G15",
    "DOUT1":   "PIN_F15",
    "DOUT2":   "PIN_B16",
    "DOUT3":   "PIN_G16",
    "DOUT4":   "PIN_K15",
    "DOUT5":   "PIN_K16",
    "DOUT6":   "PIN_L15",
    "DOUT7":   "PIN_L16",
    "DOUT8":   "PIN_N16",
}


def _make_harness() -> Harness:
    return Harness(
        iob_pins=tuple(PIN_MAP.items()),
        clk_signal="CLK",
        seed=1,
        name="m9k_smoke_w9",
    )


def _port_decl() -> str:
    parts = ["input CLK", "input WE"]
    parts += [f"input ADDR{i}" for i in range(ADDR_BITS)]
    parts += [f"input DIN{i}" for i in range(WIDTH)]
    parts += [f"output DOUT{i}" for i in range(WIDTH)]
    return ",\n    ".join(parts)


def _verilog_with_m9k() -> str:
    """altsyncram with parameter set matched to what Quartus chooses for
    inferred RAM (per smoke build's map.rpt). Key extras: read_during_write
    OLD_DATA, port-B clocking defaults made explicit. This is what closed
    the 29-cell template diff seen in the first probe pass.
    """
    addr_bus = ", ".join(f"ADDR{i}" for i in range(ADDR_BITS - 1, -1, -1))
    din_bus = ", ".join(f"DIN{i}" for i in range(WIDTH - 1, -1, -1))
    dout_bus = ", ".join(f"DOUT{i}" for i in range(WIDTH - 1, -1, -1))
    return f"""\
module fuzz_top(
    {_port_decl()}
);
    wire [{ADDR_BITS-1}:0] addr = {{{addr_bus}}};
    wire [{WIDTH-1}:0]     din  = {{{din_bus}}};
    wire [{WIDTH-1}:0]     dout;
    assign {{{dout_bus}}} = dout;

    altsyncram #(
        .operation_mode("SINGLE_PORT"),
        .width_a({WIDTH}), .widthad_a({ADDR_BITS}), .numwords_a({DEPTH}),
        .lpm_type("altsyncram"),
        .ram_block_type("M9K"),
        .outdata_reg_a("UNREGISTERED"),
        .read_during_write_mode_port_a("OLD_DATA"),
        .read_during_write_mode_mixed_ports("DONT_CARE"),
        .indata_reg_b("CLOCK1"),
        .wrcontrol_wraddress_reg_b("CLOCK1"),
        .rdcontrol_reg_b("CLOCK1"),
        .address_reg_b("CLOCK1"),
        .outdata_reg_b("UNREGISTERED"),
        .byteena_reg_b("CLOCK1"),
        .clock_enable_input_a("NORMAL"),
        .clock_enable_output_a("NORMAL"),
        .init_file("probe_init.mif"),
        .intended_device_family("Cyclone IV E")
    ) u (
        .clock0(CLK), .address_a(addr), .data_a(din),
        .wren_a(WE), .q_a(dout),
        .aclr0(1'b0), .aclr1(1'b0),
        .addressstall_a(1'b0), .addressstall_b(1'b0),
        .byteena_a(1'b1), .byteena_b(1'b1),
        .address_b({{{ADDR_BITS}{{1'b0}}}}), .data_b({{{WIDTH}{{1'b0}}}}),
        .clock1(1'b1), .clocken0(1'b1), .clocken1(1'b1),
        .clocken2(1'b1), .clocken3(1'b1), .eccstatus(),
        .q_b(), .rden_a(1'b1), .rden_b(1'b1), .wren_b(1'b0)
    );
endmodule
"""


def _verilog_baseline_no_m9k() -> str:
    parts = []
    for i in range(WIDTH):
        parts.append(f"    assign DOUT{i} = DIN{i};")
    body = "\n".join(parts)
    return f"""\
module fuzz_top(
    {_port_decl()}
);
{body}
endmodule
"""


def _make_init_mif() -> str:
    """Match smoke's INIT pattern: mem[i] = i ^ 0x1A5 (9-bit)."""
    lines = [
        "DEPTH = 512;",
        "WIDTH = 9;",
        "ADDRESS_RADIX = HEX;",
        "DATA_RADIX = HEX;",
        "CONTENT BEGIN",
    ]
    for i in range(DEPTH):
        v = i ^ 0x1A5
        lines.append(f"  {i:03X} : {v & 0x1FF:03X};")
    lines.append("END;")
    return "\n".join(lines) + "\n"


class M9kSpecimen(Specimen):
    def __init__(self, m9k_loc: str | None, init_mif: bool = False, **kw):
        super().__init__(**kw)
        self._m9k_loc = m9k_loc
        self._init_mif = init_mif

    def render_qsf(self) -> str:
        qsf = super().render_qsf()
        if self._m9k_loc is not None:
            qsf += f'set_location_assignment {self._m9k_loc} -to "u"\n'
        return qsf

    def build(self, work_dir):
        # Specimen.build calls setup_project + compile_and_export internally.
        # We drop the MIF file into the project dir before the actual build
        # so the altsyncram .init_file("probe_init.mif") parameter resolves.
        from compile import setup_project, compile_full, generate_rbf
        from pathlib import Path
        work_dir = Path(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        proj = self.project_name()
        rbf_out = str(work_dir / f"{proj}.rbf")
        proj_dir = setup_project(proj, self.verilog, self.render_qsf(), str(work_dir))
        if self._init_mif:
            (Path(proj_dir) / "probe_init.mif").write_text(_make_init_mif())
        ok, _t, err = compile_full(proj, proj_dir)
        if not ok:
            raise RuntimeError(f"Specimen build failed for {self.name!r}: {err}")
        rbf = generate_rbf(proj, proj_dir, rbf_out)
        if rbf is None:
            raise RuntimeError(f"Specimen RBF generation failed for {self.name!r}")
        return Path(rbf)


def _block_band_cells(rbf_a: bytes, rbf_b: bytes) -> set[tuple[int, int]]:
    out: set[tuple[int, int]] = set()
    if len(rbf_a) != len(rbf_b):
        raise ValueError(f"length mismatch: {len(rbf_a)} vs {len(rbf_b)}")
    lo = PREAMBLE + BLOCK_FRAME_LO * FRAME
    hi = PREAMBLE + (BLOCK_FRAME_HI + 1) * FRAME
    for off in range(lo, hi):
        if (off - PREAMBLE) % FRAME >= 208:
            continue
        x = rbf_a[off] ^ rbf_b[off]
        if not x:
            continue
        for bit in range(8):
            if x & (1 << bit):
                out.add((off, bit))
    return out


def _block_band_cells_from_paths(path_a: Path, path_b: Path) -> set[tuple[int, int]]:
    return _block_band_cells(path_a.read_bytes(), path_b.read_bytes())


def main() -> int:
    work = ROOT / "tmp" / "m9k_mode_remine_w9"
    work.mkdir(parents=True, exist_ok=True)
    harness = _make_harness()

    print(f"[probe-D] M9K_MODE width=9 single-site probe @ X{SITE_X}_Y{SITE_Y}_N0")
    print(f"[probe-D] work_dir = {work}")
    print(f"[probe-D] harness pins = {len(PIN_MAP)} (matches smoke)\n")

    t0 = time.time()
    baseline = M9kSpecimen(
        m9k_loc=None,
        name="m9k_smoke_w9_baseline",
        harness=harness,
        verilog=_verilog_baseline_no_m9k(),
        placement={},
    )
    print("[probe-D] building no-M9K baseline …")
    bl_rbf = baseline.build(work)
    print(f"  -> {bl_rbf.name}  ({time.time()-t0:.1f}s)\n")

    t0 = time.time()
    site = M9kSpecimen(
        m9k_loc=f"M9K_X{SITE_X}_Y{SITE_Y}_N0",
        init_mif=True,
        name=f"m9k_smoke_w9_X{SITE_X}_Y{SITE_Y}",
        harness=harness,
        verilog=_verilog_with_m9k(),
        placement={},
    )
    print(f"[probe-D] building M9K@X{SITE_X}_Y{SITE_Y}_N0 width=9 …")
    site_rbf = site.build(work)
    print(f"  -> {site_rbf.name}  ({time.time()-t0:.1f}s)\n")

    bl_bytes = bl_rbf.read_bytes()
    site_bytes = site_rbf.read_bytes()
    predicted = _block_band_cells(bl_bytes, site_bytes)
    print(f"[probe-D] predicted MODE (site ⊕ baseline, block-band) = {len(predicted)} cells")

    # IMPORTANT: gold MUST use the SAME baseline as predicted, not nv_zero_global.
    # Mixing baselines smuggles harness IOB-block-band footprint into the diff,
    # which is what made the first probe attempt look like a 78-cell failure.
    gold = ROOT / "tmp" / "m9k_smoke" / "ram_9x512.rbf"
    gold_mode = _block_band_cells(bl_bytes, gold.read_bytes())
    print(f"[probe-D] Quartus smoke gold MODE (smoke ⊕ baseline) = {len(gold_mode)} cells")

    # Diagnostic: what does the old (mismatched-baseline) gold look like?
    nv = ROOT / "results" / "rbf" / "nv_zero_global.rbf"
    gold_legacy = _block_band_cells(nv.read_bytes(), gold.read_bytes())
    print(f"[probe-D]   (legacy gold smoke ⊕ nv_zero = {len(gold_legacy)} — for reference; do not use)")

    common = predicted & gold_mode
    only_pred = predicted - gold_mode
    only_gold = gold_mode - predicted
    gap = len(only_pred) + len(only_gold)
    print(f"[probe-D] match    = {len(common)}")
    print(f"[probe-D] false on = {len(only_pred)} (predicted has, gold doesn't)")
    print(f"[probe-D] missed   = {len(only_gold)} (gold has, predicted doesn't)")
    print(f"[probe-D] symmetric gap = {gap} cells (acceptance: ≤5)")

    if gap <= 5:
        print(f"\n[probe-D] PASS — proceed to Stage 2(a).E (full per-site re-mine).")
        return 0
    print(f"\n[probe-D] FAIL — route to Stage 2(a).C (document, keep emission gated).")
    if only_pred:
        sample = sorted(only_pred)[:8]
        print(f"  false-on sample: {sample}")
    if only_gold:
        sample = sorted(only_gold)[:8]
        print(f"  missed sample:   {sample}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
