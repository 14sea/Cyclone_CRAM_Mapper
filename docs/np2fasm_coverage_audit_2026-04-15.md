# np2fasm coverage audit — 2026-04-15

Audit of the Verilog → Yosys → nextpnr-generic → np2fasm → fasm2rbf
pipeline. Read-only; no code changes.

## Executive summary

The pipeline is **end-to-end ready for combinational + register designs
with carry chains** that fit on the SLICE/IOB grid. Everything required
to take a Verilog source through to a CRC-valid, hardware-bootable RBF
exists for that design class — and three reference designs
(`identity_led`, `simple_led`, `counter_led`) have been demonstrated
bit-perfect or HW-verified.

The frontier is **memory and clock-tree extension**: M9K BRAM is
chipdb-side wired but Yosys-techmap, np2fasm, and a fasm2rbf
end-to-end test are all stubs (`synth/np2fasm.py:70`,
`synth/ep4ce6_map.v:43-86`, `synth/prims.v:78-122`). PLLs and
DSP18×18 multipliers have no pipeline presence at all (no chipdb bels,
no techmap, no FASM). Self-loop routes (LE → same LE) are
permanently unmineable with the current sig-cache template.

**Top 3 gaps to close next, ranked by effort × impact:**

1. **M9K end-to-end** (~1-2 person-weeks). All four layers have
   stubs; chipdb already emits 40 `EP4CE6_M9K` bels with anchors;
   `fasm2rbf` already implements `M9K.INIT_{w}x{d}` (test `test_m9k_init_directive.py` passes round-trip at multiple anchors). The remaining work is the techmap unlock + np2fasm `_emit_m9k_init` cell-walker + a routable `tiny_ram` reference design. Unlocks NEORV32-class designs (~256 KiB usable BRAM).
2. **Carry chain-start CRAM bit** (~1 person-day mining + plumbing).
   `np2fasm.py:418` currently emits a bare `# CHAIN_START` comment.
   The arith blob already activates the chain; only the CI=0 vs
   CI=1 (add vs sub) discriminator bit remains unmined.
3. **`SRC` directive auto-emission** (~half-day). `fasm2rbf`
   recognizes `SRC X{x}Y{y}` (`fuzz/fasm2rbf.py:115`) but
   `synth/np2fasm.py` never emits one. End-to-end designs that need
   per-source overhead currently rely on the sig-cache shortcut +
   green-island fingerprint snapshots; an explicit emission would
   close the symmetry and let edge sources work outside the
   fingerprint set.

## Layer-by-layer matrix

| Primitive / cell        | Yosys techmap                              | Chipdb bel/pip                                   | np2fasm emit                              | fasm2rbf directive               | Test                                    | HW |
|-------------------------|--------------------------------------------|--------------------------------------------------|-------------------------------------------|----------------------------------|-----------------------------------------|----|
| `$lut` (K=4 default)    | `synth/ep4ce6_map.v:6`                     | `GENERIC_SLICE` (`chipdb_gen.py:140`)            | `LUT = 0x{mask}` (`np2fasm.py:296`)       | `LUT` (`fasm2rbf.py:99`)         | `test_fasm2rbf.py`, `test_fasm_roundtrip.py` | ✓  |
| `$lut` width<4          | width-pad rep in techmap (line 11)         | same as $lut                                     | same                                      | same                             | covered                                 | ✓  |
| `$_DFF_P_`              | `ep4ce6_map.v:16`                          | SLICE CLK pin (`chipdb_gen.py:158`)              | `DFF` (`np2fasm.py:287,299`)              | `DFF` (parsed; no-op by design — Cyclone IV FF is silicon default) | `test_fasm2rbf.py`             | ✓ (negative-control proven 2026-04-13) |
| `$_DFFE_*_`, `$dffsr`   | NOT mapped; passes raw to nextpnr → fail   | —                                                | —                                         | —                                | —                                       | ✗  |
| `$alu` (`$add`/`$sub`)  | `ep4ce6_map.v:89` → `CE6_CARRY` per bit    | `CARRY` direct pips (`chipdb_gen.py:253-278`, 8126 pips) | `LUT_ARITH = 0x0000` (`np2fasm.py:281`); chain walker (lines 363-441) | `LUT_ARITH` (`fasm2rbf.py:105`)  | implicit via counter; `test_np2fasm_iob.py` peripheral | ✓ HW (counter_led 2026-04-13) |
| Carry chain-start bit   | (CI = `1'b0`/`1'b1` const)                 | —                                                | `# CHAIN_START` comment only (line 418)   | —                                | —                                       | ✗  |
| `$mul` / DSP            | NOT mapped                                 | no bel                                           | —                                         | —                                | —                                       | ✗  |
| `$mem_v2` (libmap M9K)  | `$__M9K_SP_` rule **gated** by `M9K_TECHMAP` ifdef (`ep4ce6_map.v:59`) | `EP4CE6_M9K` bel + 5 ports/site (`chipdb_gen.py:185-206`) | stub `_emit_m9k_init` (`np2fasm.py:70-151`); not called from `convert()` | `M9K.INIT_{w}x{d}` (`fasm2rbf.py:126-128`) | `test_m9k_init_directive.py` (round-trip OK at multiple anchors); `test_np2fasm_m9k.py` xfail | ✗ end-to-end |
| PLL primitives          | NOT mapped                                 | no bel                                           | —                                         | —                                | —                                       | ✗  |
| `GENERIC_IOB`           | n/a (instantiated direct in user RTL)      | per-pin from `ROUTE_FUZZ_PINS` (`chipdb_gen.py:212`) | `IOB_IN` / `IOB_OUT` per port direction (`np2fasm.py:332-343`) | `IOB_IN` / `IOB_OUT` (`fasm2rbf.py:172`) | `test_np2fasm_iob.py` (6/6); `iob_validate.py` 44/44 single-axis | ✓ HW (simple_led, iob_pair_E16) |
| `IOB_BASELINE_NV`       | n/a                                        | n/a                                              | **NOT emitted** by np2fasm — user must prepend manually when targeting `nv_zero_global` baseline | `IOB_BASELINE_NV` (`fasm2rbf.py:193`) | `test_iob_baseline_nv_directive.py` (9/9)        | ✓ (transitively via simple_led) |
| `IOB_CLK_INPUT`         | n/a                                        | n/a                                              | **NOT emitted** by np2fasm — relies on `GCLK_PIN` instead | `IOB_CLK_INPUT` (`fasm2rbf.py:203`, E1 only) | `test_iob_baseline_nv_directive.py:62` (E1/R8/N1 loaders) | ✗ HW pending |
| `IOB_ROUTE`             | n/a                                        | sig-cache pip (`route_cells_full.json`)          | **NOT emitted** by np2fasm — pin→LE arcs go through ROUTE path which has no IOB-aware lookup | `IOB_ROUTE` (`fasm2rbf.py:178`)  | `test_iob_route_directive.py` (15/15 single-LE sweep) | ✓ transitive (pair RBF flashed) |
| GCLK pin (E1/R8/N1)     | n/a                                        | `GCLK` wire + IOB→GCLK pip (`chipdb_gen.py:367-375`) | `GCLK_PIN` per resolved CLK→IOB walk (`np2fasm.py:518`) | `GCLK_PIN` (`fasm2rbf.py:136`)   | `test_gclk_pin_directive.py` (10/10); `test_np2fasm_gclk.py` (6/6) | ✓ HW 2026-04-14 |
| `LAB_CLK_SEL`           | n/a                                        | n/a                                              | per-LAB containing a clocked LE (`np2fasm.py:520`) | `LAB_CLK_SEL` (`fasm2rbf.py:142`) | `test_gclk_pin_directive.py`           | ✓ HW |
| `LAB_CLK_SEL_LE`        | n/a                                        | n/a                                              | per-LE clocked (`np2fasm.py:522`)         | `LAB_CLK_SEL_LE` (`fasm2rbf.py:149`) | `test_gclk_pin_directive.py:135-178`   | ✓ HW |
| Legacy `GCLK` (17-cell) | n/a                                        | n/a                                              | fallback when CLK net doesn't resolve to IOB (`np2fasm.py:528`) | `GCLK` (`fasm2rbf.py:130`)       | `test_fasm2rbf.py`                      | ✓ legacy |
| `SRC` overhead          | n/a                                        | n/a                                              | **NOT emitted** by np2fasm                | `SRC` (`fasm2rbf.py:115`)        | `test_fasm2rbf.py`                      | ✓ when hand-written |
| `BIT` raw flip          | n/a                                        | n/a                                              | not emitted (escape hatch)                | `BIT` (`fasm2rbf.py:112`)        | `test_fasm2rbf.py`                      | ✓ |
| `DFF.ARST` / `DFF.ENA`  | n/a                                        | n/a                                              | not emitted                               | parsed; **disabled** (`fasm2rbf.py:906` — header-band noise) | —                                       | ✗ |

## Gap list

### G1 — M9K end-to-end (BRAM)
**Missing**: (a) Yosys techmap rule un-gating + INIT serialization,
(b) np2fasm `_emit_m9k_init` plumbed into `convert()` and routable
clock/addr/data nets through M9K bel ports, (c) end-to-end smoke
test (`tiny_ram`).
**Closes**: NEORV32-class designs requiring instruction/data
memory.
**Effort**: 1-2 person-weeks (techmap mapping is the hardest piece;
codec already proven via `test_m9k_init_directive.py` round-trip).

### G2 — Carry chain-start CRAM bit ($add vs $sub discriminator)
**Missing**: a single CRAM bit (or small bit set) that distinguishes
adders from subtractors when `CI=1'b1`.
**Closes**: `$sub`, `$lt`, `$le` arith operations.
**Effort**: ~1 person-day. Mining template: build identical 4-bit
$add and $sub designs at LAB(4,18); diff. Probably one block-band
cell adjacent to the existing 100 SETs.

### G3 — `SRC` directive auto-emission
**Missing**: np2fasm should emit `SRC X{x}Y{y}` for every used LAB
that doesn't hit a sig-cache fingerprint snapshot.
**Closes**: edge LABs (Y=15, X∈{5,9,14,30,32,33}) without
fingerprint coverage; future jailbreak designs.
**Effort**: ~half-day. Iterate over `cell_bel`, dedupe by (x,y),
emit before ROUTEs.

### G4 — `IOB_ROUTE` auto-emission
**Missing**: np2fasm currently emits `ROUTE` for IOB→SLICE arcs and
relies on `route_cells_full.json` containing the IOB pin as a
"source LAB". The IOB_ROUTE directive (`fasm2rbf.py:178`) has its
own JSON (`iob_to_slice_sigcache.json`) but no caller in np2fasm.
**Closes**: clean composition with `IOB_BASELINE_NV` for
single-LE-on-`nv_zero_global` synthesis.
**Effort**: ~1 day. Detect `GENERIC_IOB → SLICE` arcs in the
ROUTE pass (`np2fasm.py:543`), emit `IOB_ROUTE PIN_X -> X{dx}Y{dy}N{dn}.{port}`
instead of `ROUTE`.

### G5 — `IOB_BASELINE_NV` / `IOB_CLK_INPUT` auto-prepend
**Missing**: np2fasm doesn't know which baseline RBF the FASM will
be applied to. Today the user must hand-prepend
`IOB_BASELINE_NV` when targeting `nv_zero_global.rbf`, and
`IOB_CLK_INPUT PIN_E1` when using E1 as a clock pad.
**Closes**: removes the manual prepend step from end-to-end builds.
**Effort**: ~half-day, plus a CLI flag (`--baseline nv|iob_in_E15`)
to declare baseline intent. Without the flag np2fasm can't safely
infer.

### G6 — `$dffe`, `$dffsr`, `$dffsre` (DFF with enable / async reset)
**Missing**: techmap rules. CLAUDE.md notes DFF.ARST/ENA are
disabled because of header-band noise; until that's resolved, the
techmap rule would have to lower these to plain DFF + LUT-mux for
the enable, paying area.
**Effort**: ~3 days for lowering rules; full activate awaits FF
control bit re-mining (~1 person-week).

### G7 — DSP18 multipliers, PLL primitives
**Missing**: everything (chipdb bels, techmap rules, np2fasm,
fasm2rbf directives, mining campaign for CRAM cells).
**Closes**: signal-processing class designs; pin-to-pin clock
ratios beyond what GCLK can do.
**Effort**: ~1-2 person-months each. Out of scope for next
quarter.

### G8 — Self-loop routes (LE → same LE)
**Permanently unmineable** with the current two-LUT pair template
(see `Known Pitfall #9`). The LE-internal carry feedback path
solved the carry-chain self-loop class; general self-loops still
require either a single-LE differential mining strategy or a
synthesis-level avoidance pass.

## Recommended next primitive to land

**M9K BRAM (G1)** — the single highest-impact primitive remaining.

Concrete plan:

1. **Day 1-2**: write `tiny_ram.v` (256 × 9, single-port,
   read-then-write) and verify Quartus produces a 1-M9K placement.
   `quartus_cpf` to get a gold RBF; diff vs `nv_zero_global.rbf`
   to extract block-band/clock-band cells.
2. **Day 3-4**: un-gate the `M9K_TECHMAP` ifdef in
   `synth/ep4ce6_map.v` and verify `synth_ep4ce6.sh` produces a
   placeable JSON with one `EP4CE6_M9K` cell on the
   `M9K_X15_Y4_N0` (or similar mined-anchor) bel.
3. **Day 5**: extend `np2fasm.convert()` to detect
   `cell.type == "EP4CE6_M9K"`, call `_emit_m9k_init` (already
   written, line 121), and fold its output into the FASM stream.
4. **Day 6-7**: end-to-end build of `tiny_ram` →
   `tiny_ram.fasm` → `tiny_ram.rbf`; diff vs Quartus gold; flash
   on AX301 with a simple read-loop driving LEDs.
5. **Day 8-10**: extend to dual-port and SDP modes; add
   `test_np2fasm_m9k.py` xfail flip; document in CLAUDE.md.

Risk: the M9K block-band may need additional CRAM cells beyond
the 33 anchors already calibrated (`m9k_init_basis.py`). If so,
extend Stage A mining (`m9k_stage_a_complete.md`) to cover the
clock-band selector when CLK_A ≠ GCLK.

---

**Files referenced** (all paths absolute under `/home/test/EP4CE6/`):
`synth/np2fasm.py`, `synth/ep4ce6_map.v`, `synth/prims.v`,
`synth/m9k.lib`, `fuzz/fasm2rbf.py`, `fuzz/chipdb_gen.py`,
`fuzz/m9k_init_basis.py`, `fuzz/test_fasm2rbf.py`,
`fuzz/test_fasm_roundtrip.py`, `fuzz/test_iob_baseline_nv_directive.py`,
`fuzz/test_iob_route_directive.py`, `fuzz/test_m9k_init_directive.py`,
`fuzz/test_gclk_pin_directive.py`, `fuzz/test_np2fasm_iob.py`,
`fuzz/test_np2fasm_gclk.py`, `fuzz/test_np2fasm_m9k.py`,
`results/route_cells_full.json`, `results/iob_cell_map.json`,
`results/iob_to_slice_sigcache.json`, `results/arith_blockband_v3.json`.
