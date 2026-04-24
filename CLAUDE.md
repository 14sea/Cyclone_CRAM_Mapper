# CLAUDE.md — EP4CE6 Bitstream Reverse Engineering

Black-box fuzzing pipeline for Altera Cyclone IV EP4CE6F17C8 bitstream (.rbf) reverse engineering. Goal: complete CRAM bit dictionary + open-source toolchain (Yosys → nextpnr → FASM → RBF).

## Quick Start

```bash
export PATH=$PATH:$HOME/intelFPGA_lite/21.1/quartus/bin
cd fuzz
python3 runner.py baseline                        # generate zero baseline
python3 runner.py --node lut_inst lut_single 10 10 0  # fuzz LUT at (10,10,0)
python3 runner.py n_sweep 10 10                   # calibrate 16 minterms
python3 analyze.py read_tt design.rbf zero.rbf 10 10 0
python3 analyze.py write_tt zero.rbf 0x8888 output.rbf 10 10 0
python3 fuzz/test_green_zone_harden.py            # 24 islands, 731/731 bit-perfect
# ζ production pipeline (one-shot; preferred entry point):
python3 scripts/bit_workaround/zeta_pipeline.py gold.rbf                    # round-trip + byte-identity gate
python3 scripts/bit_workaround/zeta_pipeline.py design.qpf --flash \
    --uart-seconds 10 --baud 19200 --expect "NEORV32"                        # end-to-end w/ HW
python3 scripts/bit_workaround/zeta_selftest.py                              # sub-second CI smoke test
python3 scripts/bit_workaround/zeta_regression.py                            # full corpus regression (~1.5s)
python3 scripts/bit_workaround/zeta_rbf_diff.py A.rbf B.rbf --top-frames 10  # region-aware diff
python3 scripts/bit_workaround/zeta_manifest_diff.py A.manifest.json B.manifest.json  # build-vs-build drift
# Pre-commit hook (opt-in per clone): git config core.hooksPath .githooks
# Raw two-step form (use when you want the BIT FASM as an inspectable intermediate):
python3 scripts/bit_workaround/quartus_gold_to_bit_fasm.py gold.rbf design.bit.fasm
python3 fuzz/fasm2rbf.py design.bit.fasm results/rbf/nv_zero_global.rbf rebuilt.rbf
python3 scripts/uart_observe.py --baud 19200 --seconds 30  # --baud required, no default
```

## Directory Layout

- `fuzz/` — fuzzing pipeline (~96 Python modules): `config.py` (constants), `bitstream.py` (LutCodec/RouteCodec/FFCodec/CRC), `fasm2rbf.py`/`rbf2fasm.py` (FASM toolchain), `route_synth.py` (green-island synthesis), `route_signatures.py` (sig-cache backend), `chipdb_gen.py` (nextpnr chipdb), `runner.py`/`compile.py`/`analyze.py` (orchestration)
- `synth/` — open-source toolchain: `ep4ce6_map.v` + `prims.v` (Yosys techmap), `synth_ep4ce6.ys` + `synth_ep4ce6.sh` (run the `.sh` wrapper, not `.ys` directly — it envsubst's `$HOME` / `$NEORV32_ROOT` so the VHDL paths travel), `np2fasm.py` (nextpnr JSON → FASM)
- `scripts/` — one-off investigation scripts kept for reproducibility (e.g. `scripts/arith_sweep/` — Phase 1 per-width arith blob sweep harness)
- `tmp/` — **local scratch only, gitignored**. House rule: do NOT drop experimental work under `/tmp/`; use this dir instead. The moment a script is cited from docs or memory, move it out of `tmp/` into `scripts/` (or another proper location) so it survives reboots and is reachable from a clone.
- `jailbreak/` — CE10 fitter probes (CE6≡CE10 same die, +65% fabric unlocked)
- `results/` — `rbf/` (~2500 files), `route_cells_full.json` (sig-cache; gitignored, regenerate via `route_signatures.build()`; legacy fallback loads `route_cells.json` = 1,725 entries), `r4_iindex_table.json`, `ep4ce6_bitdb.sqlite`, `fingerprint_*.json` (15 green islands), `sigma_inv_fb8_groups.json` (2,112-entry σ⁻¹ 3-key table), `nv_baseline_pack.json` (NV baseline sub-buckets)

## Chip Constants

**RBF**: 368,011 bytes fixed. Preamble 32B 0xFF | Config 367,920B (1752 frames × 210B) | Postamble 59B 0xFF.

**CRAM geometry**: LAB column step = 7,350 bytes. Pair spacing = 210 bytes. Ctrl→Data offset = 48 bytes. CRC bytes at offset 208/209 per frame.

**Y-address** (universal across all switch types):
```python
slot = (y - 2) % 3;  group = (y - 2) // 3
bp = (6 - group) if slot == 2 else (7 - group)
```

**CE6 whitelist**: LAB_X=[3,4,6,7,8,10,11,12,13,16,17,18,19,21,22,23,24,25,26,28,29,31], LAB_Y=[2..14,16..19,21], N=[0,2,4,...,30]. 392 LABs / 6,272 LEs.

**True silicon** (CE10 jailbreak, HW-verified): LAB_X adds {5,9,14,30,32,33} → 28 cols. LAB_Y adds {15} → 20 rows. NON_LAB_X = {15,27} (M9K), {20} (mult). 520+ LABs / 10,320 LEs (+65%).

## Codec API (`fuzz/bitstream.py`)

| Codec | Key methods | Notes |
|-------|-------------|-------|
| `LutCodec` | `write_tt(base_rbf, mask)` → RBF, `read_tt(rbf, zero)`, `from_cram_model(x,y,n)` | **XOR-delta, not absolute!** `mask = target ^ base_tt`. `from_cram_model` uses σ⁻¹ permutation lookup keyed by `(foff, fb8, group)` — **2112 entries** (3-key table, 0% identity fallback), 5-level fallback: exact 3-key → nearest-foff 3-key → exact 2-key → nearest 2-key → identity. Data: `results/sigma_inv_fb8_groups.json`. Y=3 wrap gap closed 2026-04-24 (80 new entries at slot=1 group=0; wrap uses `addr_adj=206` and includes boundary N=12 — Y≥6 slot=1 groups still use 207 and strict `<`). Group-4 gap for fb8∈{0,1,3,4} × Y∈{14,16} closed 2026-04-24 (+128 entries via alternate-X FACE probes at X=11/16/12/17 — the primary narrow-column reps X=3/6/4/7 don't fit the 16-LUT template). **Residual**: fb8=7 × group=4 is silicon-geometry blocked — X=8 is the sole fb8=7 column and has no LAB at Y≥12 (Quartus rejects `LCCOMB_X8_Y{14,16}_N*` on both CE6 and CE10); those 32 positions fall back to nearest-group (group=3 fb8=7). Entry (94,1,0) fixed 2026-04-21: [1,3,2,0]→[1,2,3,0] (proved by Quartus AND gate gold at X16Y4N0; affects X6/16/26/28 Y4 N0). |
| `RouteCodec` | `read_c4/r4/r24/local_interconnect()`, `apply_routing(ops)` | Round-trip verified. LI writes take explicit `pairs`, NOT i_idx |
| `FFCodec` | `write_arst/write_ena()` — 61 absolute offsets each | FASM `DFF.ARST`/`DFF.ENA` **disabled** (header-band noise) |
| `patch_rbf_crc(rbf)` | Recomputes CRC-16 for frames 25..1751 | **Mandatory** before flashing any modified RBF |

**CRC spec**: CRC-16/IBM, poly 0x8005 (reflected 0xA001), init 0xFE54, frames 25..1751 (208 data + 2 CRC per frame). Frames 0..24 = header, do NOT touch.

**SAFETY**: `validate_safe_for_hardware(rbf, zero)` checks LI MUX envelopes. Always call before flashing.

## FASM Directives (`fuzz/fasm2rbf.py`)

| Directive | Example | Status |
|-----------|---------|--------|
| `LUT` | `X10Y10N0.LUT = 0x8888` | OK — auto-compensates XOR base via minterm_0 |
| `ROUTE` | `ROUTE X10Y10 -> X10Y12N4.datab` | OK — sig-cache lookup (6 or 7-tuple) |
| `ROUTE` (sn>0) | `ROUTE X5Y3N4 -> X4Y3N6.datad` | OK — 7-tuple key |
| `GCLK` | `GCLK` | OK — 17 position-independent cells (legacy local-clock, not real GCLK_BUS) |
| `GCLK_PIN` | `GCLK_PIN PIN_E1` | OK — per-pin XOR activate set. **12 pins mined** on F17 (E1/R8/N1 + 9 dedicated clock pins): E1=3, R8=5, N1=38, M1=7, M2=4, T4=9, R4=7, M16=22, M15=21, E15=22, A14=13, B14=16. Disjoint within the legacy E1/R8/N1 triad; same-bank dedicated pins (E15/M15/M16; A14/B14) share spine cells (XOR composes correctly under double-emit). Mining: `fuzz/clk_pin_autoforce_probe.py --pin {PIN}`. Data: `results/clk_cross_pin_spine_check.json`. |
| `LAB_CLK_SEL` | `LAB_CLK_SEL X10Y4` | OK — per-LAB CLK_SEL N-invariant layer (XOR). 13 LABs mined (cell counts 21..53). Re-mine with `fuzz/clk_lab_sel_probe.py --lab X,Y`. Cross-LAB audit: `fuzz/clk_lab_sel_full_audit.py`. |
| `LAB_CLK_SEL_LE` | `LAB_CLK_SEL_LE X10Y4N0` | OK — per-LE CLK_SEL layer (XOR, disjoint from `LAB_CLK_SEL`). **Functionally required** (HW verified 2026-04-14 at LAB(10,4).N=0: N-invariant alone = LED-always-off). Data: `results/clk_lab_sel_per_le.json` derived by `fuzz/clk_lab_sel_per_le.py`. N ∈ {0, 2, 4, 6, 8} mined for **all 14 LABs** as of 2026-04-16 (N=6/8 extended via `fuzz/clk_lab_sel_n2_batch.py`, 4-way parallel; LAB(10,16) invariant tightened 53→49 with the 4 migrated cells now in n6/n8 buckets). `clk_lab_sel_per_le.py` is now N-agnostic and emits an `n{N}_specific` bucket per probed slot. To extend N further, edit `N_SLOTS` in `fuzz/clk_lab_sel_probe.py`, run `python3 fuzz/clk_lab_sel_n2_batch.py --n 10,12,...`, then `python3 fuzz/clk_lab_sel_per_le.py`. |
| `DFF` | `X10Y10N0.DFF` | **NO-OP** — DFF is silicon default (no CRAM cells) |
| `BIT` | `BIT offset bp` | OK — raw cell flip |
| `SRC` | `SRC X10Y10` | OK — per-source overhead |
| `LUT_ARITH` | `X4Y18N0.LUT_ARITH = 0x0000` | OK — v4 universal blob (100 SETs + 4 CLEARs) for 8-LE half-LAB chains at ANY LAB. Other widths see per-width table below. |
| `LUT_ARITH_MULTI_LAB` | `LUT_ARITH_MULTI_LAB WIDTH=17` | OK codec — widths 17..32 multi-LAB carry chain activation (LAB(4,18) full + LAB(4,17) partial, N=30→N=0 inter-LAB link). Consumes `results/arith_blockband_by_width.json`'s `multi_lab["16+N"]` entries (N=1..16). XOR-parity composition; double-emit of the same width cancels. 10/10 tests in `fuzz/test_lut_arith_multi_lab_directive.py`. np2fasm consumer NOT yet wired — Yosys `$alu` techmap today caps at single-LAB chains. Position-independence for multi-LAB blobs is NOT yet proven (single-LAB v4 triangle test only covers widths ≤16); placing the wide chain at a different LAB-pair may leak residual cells. |
| `IOB_IN`/`IOB_OUT` | `IOB_IN PIN_M16` / `IOB_OUT PIN_F15` | OK single-axis (44/44 bit-perfect) — XOR delta from `iob_in_E15.rbf` baseline (K=E15, LED=G15). Cross-axis combos leak ~50-60 joint-placement bytes; 2D K×LED sweep falsified (pair-specific, 421-sample survey — memory `iob_cross_axis_2d_sweep_falsified.md`). For G15-output designs use `IOB_PAD_NV` + `OUTROUTE_G15` instead. |
| `IOB_ROUTE` | `IOB_ROUTE PIN_E16 -> X16Y4N0.dataa` | OK — pin→LE-port sig lookup. **Two apply-paths**: (a) default live path (`_load_iob_route_cells`) consults `padnv_cells` > `absolute_cells`, dedup + `off<5282` hdr-skip; correct for pair-derived / IOB_PAD_NV designs (two_lab, NEORV32 ζ, multi-LE). (b) legacy path (`_load_iob_route_cells_legacy`, enabled by `bitgen(..., legacy_iob_route=True)`) consults `single_le_cells` > `single_le_cells_stale` > `absolute_cells` per-key, pure XOR parity with no dedup / no hdr-skip; required for simple_led-class single-LE designs (see Fix A 2026-04-24 commit 8c660ef). **np2fasm pragma channel**: `np2fasm --legacy-iob-route` or `convert(..., legacy_iob_route=True)` prepends a `# fasm2rbf: legacy_iob_route=1` comment; callers parse with `fasm2rbf.parse_pragmas(text)` and forward to `bitgen(**pragmas)`. No magic auto-override inside bitgen — the caller explicitly wires pragmas into kwargs (see `fuzz/test_np2fasm_legacy_iob_route.py` 6/6). `padnv_cells`: E16→X16Y4N0.dataa (105) + M16→X16Y4N0.datab (13) derived from Quartus AND gold. `absolute_cells`: 15 entries at X∈{10,16} Y∈{4,10} pair-reconstruction. `single_le_cells`: 109 entries Fix-B re-mined 2026-04-24 against the legacy path (commit af22c9f) — covers X∈{3,4,6,7,8,10,16} Y∈{4,10,17,18,19,21} targets, every entry byte-identical to cached Quartus gold. `single_le_cells_stale` retained as safety-net fallback. Re-derive: `python3 scripts/iob_slice_mining/sweep_single_le.py --orphans-only --include-known --skip-build`. |
| `IOB_BASELINE_NV` | `IOB_BASELINE_NV` | OK — 132-cell / 74-byte hdr-band bridge (`nv_zero_global` ^ `iob_in_E15`). Emit once to let `IOB_IN`/`IOB_OUT` pair-deltas apply on `nv_zero_global`. Boolean (idempotent under double-emit). Data: `results/iob_baseline_hdr_cells.json`. **SUPERSEDED by IOB_PAD_NV for G15-output designs** (方案B). |
| `IOB_PAD_NV` | `IOB_PAD_NV` | OK — 241-cell IOB pad infrastructure (E16+M16 input + G15 output), direct delta from `nv_zero_global`. Replaces `IOB_BASELINE_NV` + `IOB_IN`/`IOB_OUT` for the standard AX301 pin set. XOR-parity (double-emit cancels). Data: `results/output_route_nv_mining.json` → `iob_pad_cells`. np2fasm emits automatically when SLICE→G15 output routing detected. |
| `OUTROUTE_G15` | `OUTROUTE_G15 X10Y10N0` | OK — position-specific SLICE→G15 output routing cells (38-67 per position). 33 positions mined. Data: `results/output_route_sigcache.json`. np2fasm emits when SLICE output drives IOB_G15 and position is in sigcache. |
| `IOB_CLK_INPUT` | `IOB_CLK_INPUT PIN_E1` | OK for **12 pins** on F17 — hdr delta activating a clock-bank pin as GCLK driver. Mined pair-delta `simple_led_E16_to_G15_clk{PIN}.rbf` ^ `iob_in_E16.rbf` (E1=40, R8=64, N1=70, M1=72, M2=48, T4=66, R4=52, M16=46, M15=58, E15=62, A14=60, B14=52 cells). 11 of 13 dedicated F17 clock pins covered (E2 fails — Quartus refuses LVDSCLK_00P side; H1 reserved as ALTERA_DCLK config pin) plus R8/N1 (general IO accepted as GCLK source) and E16 skipped (template anchor pin). Extensible via `scripts/iob_slice_mining/compute_clk_pin_hdr.py --build --pin {PIN}` → `results/iob_clk_pin_hdr_cells.json`. |
| `NV_BASELINE_PACK` | `NV_BASELINE_PACK` | OK — meta directive (21 640 XOR cells) that reproduces `nv_zero_global.rbf` on top of `make_pure_zero_rbf()` byte-for-byte (368 011-byte gate verified). Enables open-toolchain callers to pass PURE_ZERO as `base_rbf` instead of the Quartus-produced `nv_zero_global.rbf`. Data: `results/nv_baseline_pack.json` (Phase 2 of nv_zero_global retirement; mining script `scripts/baseline/mine_nv_baseline_pack.py`). Sub-directives for selective application: `IOB_BANK_DEFAULT_PACK` (hdr band, 5 068 cells), `LOCAL_CLK_E1_BASELINE` (2 anchor cells), `LOCAL_CLK_PATH_A` (2 spine-hit cells), `LAB_LOCAL_CLK X{x}` (per LAB column, X=3..33 live), `M9K_BLOCK_DEFAULT_PACK` (X=15,27 block columns, 848 cells), `MULT_BLOCK_DEFAULT_PACK` (X=20, 17 cells), `NV_BLOCK_COL_INFRA` (low+high+residue ≈ 1 116 cells). XOR-parity composition — emitting the meta plus a sub cancels that sub's bucket. np2fasm emits the meta automatically with `--base pure`. HW flash equivalence not yet confirmed; keep `nv_zero_global.rbf` as the HW-default until flashed. |
| `DFF.ARST/ENA` | — | **DISABLED** — header-band noise unresolved |
| `M9K.INIT_{w}x{d}` | `X15Y10N0.INIT_9x512 = 0x...` | OK for codec + fasm2rbf at 33 calibrated 9x512 anchors (X∈{15,27}, Y∈[4..23]) — parser extracts `(x, y, n, width, depth, words)`, bitgen applies via `fuzz/m9k_init_basis.write_init` (XOR-delta, CRC-safe). FASM round-trip + parse + unknown-site + hex-length tests in `fuzz/test_m9k_init_directive.py` (5/5). **np2fasm emission wired** (`_emit_m9k_init` in `synth/np2fasm.py` dispatched from the M9K branch of `convert()`; 5/5 tests in `fuzz/test_np2fasm_m9k.py` including the full convert() integration); Yosys `$__M9K_SP_` / `$__M9K_SDP_` / `$__M9K_TDP_` → `EP4CE6_M9K` techmap rules live in `synth/ep4ce6_map.v` (no ifdef gate — always active). chipdb M9K pips emitted by `fuzz/chipdb_gen.py` (LOCAL-gateway bridge + GCLK→CLK_A/CLK_B + GND_BUS→DIN/ADDR; see §689–751). **M9K codec layer byte-identical vs Quartus** at X15_Y10_N0 18x512 via `scripts/m9k_e2e_smoke.py` (INIT 0/9 216, MODE 26/9 776 within documented INIT-dependent tolerance). Full `Verilog → Yosys → nextpnr → np2fasm → fasm2rbf` for `m9k_blink.v` is still blocked on (a) 28-bit counter chain exceeds `prepack_carry.ALL_NS=16` single-LAB budget, (b) no IOB prepack helper yet for CLK/KEY2/KEY3/LED0 bel binding. |
| `M9K_MODE_{w}x{d}[_template]` | `X15Y10N0.M9K_MODE_9x512_quartus_gold` | **HW-validated functional at X15_Y10_N0 (all 5 widths, 2026-04-24d) and at X15_Y11_N0 9x512 (2026-04-24). Per-site mining covers all 27 NEORV32 M9K sites as of 2026-04-25.** `quartus_gold` buckets mined via `scripts/m9k_mode_quartus_gold_mine.py` (single site) or `scripts/m9k_mode_quartus_gold_batch.py --neorv32` (sweep) — per (w,d,site) the intersection of 3 Quartus altsyncram variants (different INIT + read-pipe) vs a pinout-matched no-M9K baseline, block-band only. Default-site sizes at X15_Y10_N0: (4,2048)=19, (9,512)=52, (18,512)=59, (9,1024)=43, (36,256)=68. Per-width HW sweep 2026-04-24d: each (w,d) blink design at X15_Y10_N0 (`scripts/m9k_blink_build.py`) flashed on AX301 and LED0 blinks stably at the expected ~0.186 Hz cadence. Per-site spot-check 2026-04-24: X15_Y11_N0 9x512 (`scripts/m9k_blink_build.py --site 15,11,0 --width 9 --depth 512`) passes the same cadence check — site-specificity (Y10 vs Y11 bucket overlap 45/59) doesn't regress functionality. Cross-column spot-check 2026-04-25: X27_Y7_N0 9x512 also blinks stably on AX301 — first silicon proof that the methodology generalizes across column (previously only X15 validated). np2fasm gate: `_M9K_MODE_FUNCTIONAL_VALIDATED = {(4,2048),(9,512),(18,512),(9,1024),(36,256)}` × lazy-loaded site set from `results/m9k_mode_bits.json` — 27 NEORV32 M9K sites (X15 Y=2..16 + X27 Y=2..13) + 2 legacy X27 sites now carry `quartus_gold` buckets across 4 widths (w=18 still X15_Y10..14 only), 113 buckets total. Site-specificity is real: reusing Y10's bucket at Y11 would flip ~23 cells wrong, confirmed by the `_mined_quartus_gold_triples()` JSON-driven gate + `test_emit_m9k_mode_gate_reads_mined_triples_from_json`. Legacy `_M9K_MODE_HW_VALIDATED` retained only for manual callers still asking for `_inferred_goldintersect`. SDP/TDP variant mining not yet implemented (ζ remains NEORV32's production path). Memory: `m9k_persite_mining_batch.md`, `m9k_persite_hw_validated_y11.md`, `m9k_mode_quartus_gold_hw_validated_2026_04_24d.md`, `m9k_mode_gi_bucket_not_quartus_encoding.md`.

Prior (fabric-safety-only) characterization retained for history: 2026-04-24 data-path probe revealed the gi buckets are **not** real Quartus mode cells — a Quartus gold build of `m9k_blink` (4×2048 M9K at X15_Y10_N0, `tmp/m9k_dpath_w4x2048/m9k_blink.rbf`) compared against `results/rbf/m9k_baseline_empty.rbf` had **0% overlap** with the 24-cell (4,2048) gi bucket; a similar check of the committed `tmp/m9k_smoke/ram_9x512.rbf` vs the 38-cell (9,512) gi bucket also yielded 0% overlap. The "HW validation" we had only confirmed that the overlay is silicon-fabric-survivable on the simple_led baseline (KEY2→LED0 still responds), not that it configures the M9K to the requested mode. (4,2048) was briefly ungated 2026-04-24 after a CLEAN23 bisection masked a leaky pair `(364092,2)+(364093,2)` at frame 1733; the data-path finding reverted that ungate — `_M9K_MODE_HW_VALIDATED = {(9,512),(18,512),(9,1024),(36,256)}` again. Parser/loader/bitgen + `_emit_m9k_mode` helper (`fuzz/fasm2rbf.py`, `synth/np2fasm.py`). Template suffixes: `_altsyncram`, `_inferred`, `_inferred_goldintersect` (site-invariant, 38/74/79/11/24 cells at w=9/w=18/(9,1024)/(36,256)/(4,2048) raw). Fabric-safety mining pattern: XOR-overlay on `cff800e` HW-PASS w=9 RBF at `scripts/stage0_flash_bundle/simple_led_m9k_mode_goldintersect.rbf`; per-width overlay builders at `build_simple_led_m9k_mode_{w}x{d}_gi_probe_overlay.py`. (4,2048) bisection harness + CLEAN23 loader mask retained (`scripts/stage0_flash_bundle/build_m9k_mode_w4x2048_bisect.py`, `_M9K_MODE_SILICON_FALSIFIED`), but (4,2048) is not emitted by np2fasm because the bucket does not encode that mode. Real Quartus mode-cell mining is tracked as a separate effort. Tests: `fuzz/test_m9k_init_directive.py` + `fuzz/test_np2fasm_m9k.py` (17+15). Memory: `m9k_mode_gi_bucket_not_quartus_encoding.md` (primary), `m9k_mode_w4x2048_bisect_clean23.md`, `m9k_mode_widths_hw_validation_2026_04_24d.md`, `m9k_mode_template_residual.md`. |

**FASM footgun**: SRC overhead + ROUTE sig cells MUST union before XOR-flip (double-flip cancels shared cells).

## Routing Switch Models (formulas in `bitstream.py`)

All switch types use the same Y-address (slot/group/bp). Key differences:

| Type | Column | Byte model | Coverage |
|------|--------|------------|----------|
| C4 I=0 | self (LAB_CRAM_END) | slot-dependent SLOT_BASE + 3×group | 63 wires, 0 false pred |
| C4 I≠0 | self | fixed-byte per (X,I), 44 mappings | lookup table |
| R4 | **prev** LAB col | R4_BASE_PREV[I] + slot offset | 24/37 I-indices, 60-97% |
| R24 I=0 | **prev** LAB col | fixed byte (no slot/group adj) | 66% accuracy |
| LOCAL_INTERCONNECT | **self** col | base 70 + pair×210 + SLOT_OFFSET | 70% cross-val, 22 cols |

Sig-cache (`route_cells_full.json`) **short-circuits all formula paths** for production routing. Formulas are fallback only.

## Route Synthesis (`fuzz/route_synth.py`)

`synth_route(zero, src, dst)` → bit-perfect RBF. Sig-cache path serves all CE6-standard green-zone + Plan D' factory routes. CRAM is interleaved (NOT topologically isomorphic to layout) — cross-source fingerprint intersection = 0 → no universal source-entry formula at cell level.

Current harness score: **731/731 bit-perfect across all 24 islands** (CE6 standard 686/686 + jailbreak/edge 45/45) — closed 2026-04-14. `synth_route` does a snapshot lookup (`_snapshot_ops_if_present`) BEFORE `parse_need`, so jailbreak/edge LABs (Y=15, Y=5, X=5/9/14/30/32/33) hit the exact Quartus cell set directly from the fingerprint snapshot without needing a formula/geometry model. The edge-island fingerprint snapshots were re-mined from on-disk pair RBFs via `fuzz/fingerprint_edge_remine.py` (the original snapshots were stale — produced by an older classifier that disagreed with current `RouteCodec.read_switches`, so `per_route_delta` was missing ~14 switch cells per route).

15 CE6 green islands: (4,4), (10,4), (10,10), (10,14), (13,10), (16,4), (16,8), (16,14), (19,14), (22,12), (22,16), (25,6), (28,10), (28,18), (31,12).
9 jailbreak/edge islands: Y=15 × {10,11,12,13,14,17,18}, Y=5 × {18,19}.

## Non-LAB Blocks (Phase 5.0)

**LOC syntax** (hierarchical MegaFunction path, NOT coordinate alias):
- DSPMULT: `-to "lpm_mult:u|mult_qpl:auto_generated|mac_mult1"`, 42 sites (Y1..21 × N{0,1})
- M9K: `-to "u"` (short form), X∈{15,27}, 126 sites

**Two CRAM bands**: block enable/mode (frames 1692-1738, DSPMULT 29 cells, M9K 58 cells, disjoint) + clock-net (~1007-1013).

**M9K init codec** (Phase 5.2): `byte(word,bit) = anchor + (word//2)*210 - (word%2) - 2*bit`, bp=6. 33 anchors calibrated. READ/WRITE 0-diff vs Quartus.

**Rules**: NEVER mine non-LAB with VIRTUAL_PIN. Always filter CRAM-only (off ≥ 5282) — header band has 4-5 bit/seed noise floor.

## Phase 5.3 — Open-Source Toolchain (HW-VALIDATED E2E)

Target: `Verilog → Yosys → nextpnr-generic → np2fasm → fasm2rbf → openFPGALoader`

**Completed**: chipdb_gen.py (15,331 bels, 87,878 wires, 2.12M pips), techmap (LUT4+DFF), np2fasm.py (logical connectivity → sig-cache lookup; emits IOB_PAD_NV / IOB_ROUTE / OUTROUTE_G15 / GCLK_PIN / LAB_CLK_SEL / LAB_CLK_SEL_LE / IOB_CLK_INPUT), `fasm2rbf` all directives.

**Status — HW-VALIDATED (2026-04-22)**: Three designs proven end-to-end on AX301 silicon:
1. **Registered AND gate** (KEY2 & KEY3 → DFF → LED0) at X16Y4N0: **0 fabric diffs** vs Quartus gold, 10 FASM lines incl. multi-port IOB_ROUTE. RBF: `tmp/e2e_test/and_gate_reg_open.rbf`.
2. **5-bit carry chain counter** (+1 counter, MSB→LED0) at LAB(16,4) N=0..8: 18 FASM lines, **0 ROUTE directives** (carry chain is LE-internal), identical behavior to Quartus gold (LED constantly on). RBF: `tmp/e2e_carry/counter5_open.rbf`. Pipeline: `counter5.v → Yosys (alumacc→CE6_CARRY) → prepack_counter.py → np2fasm → fasm2rbf`. This is the first **multi-LE carry-chain** design through the open toolchain. np2fasm dedup fix (2026-04-21): removed double-emission of LUT_ARITH+DFF from carry chain walker vs main cell loop.
3. **Two-LAB Quartus gold + BIT reconstruction** (AND@X16Y4 → inter-LAB route → DFF@X16Y14 → LED0): Quartus gold (1053 cells, 2 LABs, 5×C4 + 5×R4 + 3×R24 + 1×C16 routing) HW-verified on AX301. BIT-only reconstruction (1053 BIT directives → fasm2rbf) is **byte-perfect** vs gold and HW-verified. This is the first **cross-LAB fabric route** confirmed on silicon. Open-toolchain FASM with ROUTE directive does NOT work — sig-cache entry captures a different routing path than Quartus uses (only 3/66 cells match gold). RBFs: `tmp/chipdb_test/quartus_two_lab/output_files/two_lab.rbf` (gold), `tmp/chipdb_test/two_lab_gold_bits3.rbf` (BIT reconstruction).

**M5 counter historical fixes (2026-04-11)**: LutCodec high-density LAB workaround (`predict_sram(0xFFFF)`, memory `lutcodec_high_density_lab_bug.md`); sig-cache template must use `gen_two_luts_single_input_clocked` + `gen_qsf_ce10` (memory `sigcache_mining_template_pitfall.md`); per-LAB CLK SET must run after LUT phase reset; post-bitgen strip 1-3 stray LI cells; 160 re-mined (4,18)/(4,19) inter-LE pair entries in sig-cache. Root-cause blocker documented in pitfall #9 and memory `m5_counter_root_cause_carry_chain.md` — self-feedback routes are unmineable with the two-LUT pair template.

**IOB→SLICE route mining (2026-04-14, HW-verified template; datab closed 2026-04-21)**: `scripts/iob_slice_mining/` — paired two-LE mining template (`template_pairs.py` + `mine_iob_routes.py`) compiles `iob_pair_{PIN}_{TGT}_{PORT}` and `iob_zero_{PIN}` variants, diffs CRAM cells 25..1751 to extract pair-vs-zero deltas (~200 cells per entry). **Port canonicalization**: single-input templates all produce dataa (Quartus canonicalizes). Multi-input datab route at X16Y4N0 derived from Quartus AND gate gold via IOB_PAD_NV path algebra: `gold_fab ⊕ base_fab - LUT_cells - E16_dataa_cells = M16_datab` (13 cells). datab ≠ dataa — alias hypothesis **falsified** (174 diffs). `padnv_cells` entries bypass `_iob_route_dedup` because they're derived against the IOB_PAD_NV base path (cells compose via XOR parity directly). Multi-port validation (`scripts/iob_slice_mining/validate_multi_port.py`) with WYSIWYG `cycloneive_lcell_comb` templates confirmed Quartus honors explicit port binding with asymmetric LUT masks. **3-layer decomposition**: `universal_infra` (98) ∪ `pin_footprint` (10-12) ∪ `pure_common` (77-106) ∪ ≤2 residual across 15 entries. Outputs: `results/iob_to_slice_sigcache.json` (absolute_cells 15, padnv_cells 2, single_le_cells 109 Fix-B re-mined 2026-04-24 against legacy path, single_le_cells_stale 109 fallback; see IOB_ROUTE directive row).

## Phase 5.4 — Carry Chain (HW VERIFIED at LAB(4,18))

Arithmetic mode activation lives in the **block band** (frames 1692-1738, bp=2), NOT in LAB CRAM columns. The `LUT_ARITH` FASM directive applies a per-LAB blob of ~100 cells. All prior v1/v2 arith mining was VIRTUAL_PIN routing contamination.

**Pieces landed**:
1. `chipdb_gen.py` — 8,126 `cout→cin` direct pips between adjacent LE bels
2. `synth/ep4ce6_map.v` + `synth/prims.v` — `$alu` → per-bit CE6_CARRY chain (LE-internal feedback, no Route-A buffers)
3. `synth/np2fasm.py` — CE6_CARRY chain walker, emits `LUT_ARITH = 0x0000` + `DFF`, skips intra-LE ROUTE
4. `fuzz/fasm2rbf.py` — `LUT_ARITH` directive loads `results/arith_blockband_v3.json` (v3 block-band blob)
5. `fuzz/prepack_carry.py` — BEL pinning for up to 16-bit chain at LAB(4,18), skips nextpnr

**Hardware verified (2026-04-13 on AX301)**: identity_led + 8×LUT_ARITH=0x0000 overlay → LED constant-on, identical to Quartus counter_led.rbf. Identity Q<=Q negative control → LED off.

**LE-internal feedback (2026-04-13, Route-A eliminated)**: Quartus carry counters have ZERO external route cells — DFF.Q → carry input feedback is LE-internal on Cyclone IV silicon. The techmap connects `B_used` directly to `CE6_CARRY.B` (no LUT1 buffer), and np2fasm skips ROUTE emission for same-LE arcs. 8-bit counter: 8 LEs (was 16 with Route-A), 0 ROUTE directives, 0 sig-cache dependency.

**Key facts**:
- Arith blob is per-LAB, not per-LE (same 100 cells regardless of which LEs use arith)
- LUT SRAM = 0x0000 for standard +1 counter (function encoded in block-band, not LUT SRAM)
- Quartus carry counter has ZERO external route cells — DFF→carry feedback is LE-internal
- **Arith blob is POSITION-INDEPENDENT (v4, 2026-04-14)**: triangle test at (4,18)/(10,18)/(4,10) proved the 100 SETs + 4 CLEARs are byte-identical across LABs. The same `arith_blockband_v4.json` activates carry chain at ANY LAB — no per-LAB mining needed.
- **Arith blob is per-WIDTH, NOT per-N-slot (Phase 1 sweep 2026-04-14)**: 42-build offline sweep at LAB(4,18) verified `c{w}_lo` and `c{w}_up` produce byte-identical cell sets for all widths 2..8 (Quartus honored LOC; fit.rpt-verified). The arith blob depends on chain length, not which specific N slots are used. Table at `results/arith_blockband_by_width.json` covers widths 2..16 single-LAB + 16+8 multi-LAB. Round-trip 0 data + 0 block_band diffs for every width. 4 CLEAR cells are constant across all single-LAB widths (universal LAB arith-enable reset). v4 blob superseded for non-8-LE widths.

**DFF resolved (2026-04-13)**: DFF is the silicon default — no per-LE enable CRAM cell exists. The FF is intrinsic to every LE; registered vs combinational output is selected by downstream routing. The former `dff_cells_mined.json` contained routing infrastructure noise (zero overlap with any real RBF). FASM `DFF` directive is now a parsed no-op.

**GCLK pipeline HW-verified (2026-04-14)**: `GCLK_PIN` + `LAB_CLK_SEL` + `LAB_CLK_SEL_LE` compose as XOR-delta on an AUTO-mode baseline. Per-pin one-hot activate sets (E1=3, R8=5, N1=38; zero cross-pin overlap, proved by triangulation). Per-LAB CLK_SEL for 13 LABs; per-LE layer in `results/clk_lab_sel_per_le.json`. HW flash at LAB(10,4).N=0 proved per-LE `LAB_CLK_SEL_LE` is functionally required (N-invariant `LAB_CLK_SEL` alone = LED-always-off). 26 (LAB, N) combos round-trip bit-perfect. Tests: `fuzz/test_gclk_pin_directive.py` (11/11) + `fuzz/test_np2fasm_gclk.py` (7/7). N∈{0,2,4,6,8} mined for all 14 LABs; extend via `clk_lab_sel_n2_batch.py` after editing `N_SLOTS`. Legacy 17-cell `GCLK` fallback kept for designs whose CLK net doesn't trace to an IOB.

**nv_zero_global retirement (codec path landed 2026-04-15)**: the opaque Quartus-built `nv_zero_global.rbf` is no longer a required input for the open toolchain. `fuzz/pure_zero_rbf.py` produces a 368 011-byte PURE_ZERO baseline programmatically (32B preamble + zero CRAM + 59B postamble + CRC-patched). `scripts/baseline/mine_nv_baseline_pack.py` decomposes `nv_zero_global ^ PURE_ZERO` (21 640 cells) into 8 named buckets + per-X LAB columns (0.06% residue after M9K/MULT block-column split, was 4.05%). `fuzz/fasm2rbf.py` exposes this as the `NV_BASELINE_PACK` meta directive (plus `IOB_BANK_DEFAULT_PACK`, `LOCAL_CLK_E1_BASELINE`, `LOCAL_CLK_PATH_A`, `LAB_LOCAL_CLK X{x}`, `M9K_BLOCK_DEFAULT_PACK`, `MULT_BLOCK_DEFAULT_PACK`, `NV_BLOCK_COL_INFRA` subs; all XOR-parity composed). `np2fasm.py --base pure` prepends `NV_BASELINE_PACK` so callers can pass `make_pure_zero_rbf()` as `base_rbf` and get byte-exact `nv_zero_global` equivalence (Phase 4 reconstruction gate verified on full 368 011 bytes). Tests: `fuzz/test_pure_zero_rbf.py` (8/8) + `fuzz/test_nv_baseline_pack_directive.py` (10/10) + `fuzz/test_np2fasm_nv_baseline_pack.py` (4/4) + `fuzz/test_np2fasm_emission_audit.py` (16/16). `nv_zero_global.rbf` stays checked in as a test-vector and remains the HW-default until a directive-synthesised build is flashed (silicon-semantic equivalence is untested).

**DSPMULT_GLOBAL_ON FALSIFIED on silicon (2026-04-16)**: per-site re-mine (`fuzz/dspmult_persite_remine.py`) produced a clean 23-cell universal bucket (block band 1692-1738) with perfect N-invariance 21/21; directive landed in `fuzz/fasm2rbf.py` with 6/6 unit tests. HW flash later showed the 23-cell set leaks on silicon — the `(363236,2)` + `(363672,2)` leaky-cell mask is now applied by the loader. np2fasm does NOT emit the directive. Memory: `dspmult_global_on_clean_remine.md`. Cross-cutting rule still applies: per-site mining MUST use a shared `specimen_base.Specimen` harness; gate any new per-site directive on a clean re-mine before enabling np2fasm emission.

**nextpnr**: `source $HOME/opt/oss-cad-suite/environment` first; `--router router2` (router1 can't multi-hop); `--pre-pack` not `--run`.

## Phase 7 — ζ Escape Hatch (HW-validated on NEORV32, 2026-04-23)

Two reachable paths from Verilog/VHDL to AX301 silicon:

1. **Native**: `.v → Yosys → nextpnr-generic → np2fasm → fasm2rbf → flash`. HW-verified for small/medium designs (AND gate, 5-bit carry counter, M9K smoke, all 12 F17 clock pins). Blocked on chipdb routing-model density at NEORV32 scale.
2. **ζ escape hatch**: `.v → Quartus → scripts/bit_workaround/quartus_gold_to_bit_fasm.py → fasm2rbf → flash`. Diffs Quartus gold RBF against `results/rbf/nv_zero_global.rbf`, emits one `BIT` directive per differing bit (no filtering — hdr + fab + CRC all included so `patch_rbf_crc` re-computes correctly on round-trip). Rebuilt RBF is byte-identical to Quartus gold; total ζ + fasm2rbf wall time ≈ 0.5 s regardless of design density.

**ζ production pipeline (2026-04-24, CI-friendly)**: `scripts/bit_workaround/zeta_pipeline.py` is the canonical entry point — wraps the raw ζ + fasm2rbf + byte-identity gate + optional flash + optional UART verify into one command with exit-code + JSON semantics. Emits a sidecar `<stem>.manifest.json` next to every rebuilt RBF (SHA256 gold/rebuilt/base, region cell counts, git HEAD, timestamp) that feeds `zeta_manifest_diff.py`. Supports `--rebuild-check` for `.qpf` input, which re-runs Quartus and byte-compares both RBFs to catch non-deterministic builds. `zeta_selftest.py` is a sub-second regression gate (1710-bit two_lab invariant) suitable as a pre-commit hook — install via `git config core.hooksPath .githooks`. `zeta_regression.py` is the corpus sibling: walks `tests/zeta_corpus/manifest.json` (each entry pinned by SHA256 + per-region cell counts), asserts every fixture still round-trips byte-identical AND that its region footprint still matches — catches drift even when the round-trip still succeeds; `--reanchor` / `--reanchor-all` update the manifest. `zeta_rbf_diff.py` is a region-aware RBF diff (preamble / header-data / header-crc / fabric-data / fabric-crc / postamble) — use it instead of `cmp -l` when comparing two bitstream builds (raw cmp is dominated by CRC chain churn the moment any data bit flips). `zeta_manifest_diff.py` diffs two pipeline manifests without reading the RBFs — right tool for bootloader v1↔v2 comparisons. All six documented in README §"ζ production pipeline".

**HW-validated designs via ζ**: two_lab AND→DFF cross-LAB (2026-04-22), lits_pair route-family (2026-04-23), **full NEORV32 bootloader** (4712 LE / 2367 DFF / 19 M9K / 51 pins; 127 728 BIT = 2634 hdr + 113 573 fab + 11 521 crc) on AX301 at 19200-8N1 UART (2026-04-23). Linux 6.6.83 extended test (2026-04-24): kernel + DTB + initramfs transferred via xmodem, Linux ran ~150 s on RISC-V (devtmpfs, ttyNEO0, exec'd /sbin/init) before a kernel-level `kernel/cred.c:103` BUG_ON panic unrelated to the bitstream (RBF SHA256 = Quartus gold).

**UART observation**: `scripts/uart_observe.py --port /dev/ttyUSB0 --baud 19200 --seconds 30` — timestamped chunk log + raw capture. NEORV32 bootloader runs at 19200-8N1 (not 115200 — that's PL2303 Linux-runtime capability only).

**When to use which**: native for small/medium single/cross-LAB; ζ for NEORV32-class (>1000 LE) or any design Quartus can build but nextpnr can't route.

## Tools

- **Quartus 21.1 Lite**: `$HOME/intelFPGA_lite/21.1/quartus/bin/`
- **RBF generation**: `quartus_cpf -c -o bitstream_compression=off` (**NEVER** `sof2rbf.py`)
- **Programming**: `$HOME/see_neorv32_run_linux/tools/openFPGALoader/build/openFPGALoader -c usb-blaster`
- **Hardware**: AX301 board, EP4CE6F17C8, USB-Blaster JTAG
- **Pin map**: KEY1=E15, KEY2=E16, KEY3=M16, KEY4=M15, LED0=G15 (active-high; keys active-low)
- **UART capture**: `scripts/uart_observe.py` (pyserial; default `/dev/ttyUSB0`, specify `--baud` — no default)
- **NEORV32 Linux host flow**: `~/see_neorv32_run_linux/host/boot_linux.py --rbf <file.rbf>` drives stage2 upload + xmodem of kernel/DTB/initramfs (works against ζ-rebuilt RBFs byte-identical to Quartus gold)

## Licensing

Code: **GPL-3.0-or-later** (all .py/.v/.tcl must have SPDX header). Docs: **CC BY-SA 4.0**.

## Known Pitfalls

1. Left-edge columns (X=3,4,6,7) have CRAM addresses below 0x10000
2. Quartus fit reports: non-UTF8 bytes — use `errors="replace"`
3. Don't share `work/` across parallel campaigns
4. `sof2rbf.py` produces invalid bitstreams — always `quartus_cpf`
5. `LutCodec.write_tt` is XOR-delta, not absolute mask
6. LI `write_local_interconnect()` takes explicit pairs — auto-expansion is physically dangerous
7. Disk: Phase 3 needs work-dir cleanup (`compile.clean_work_dir()`) or in-memory diff
8. **Always cross-check codec output against Quartus's own build of the same Verilog before chasing low-level bugs.** The M5 counter session burned two days on real-but-not-blocking bugs (LutCodec, sig-cache mining, phase ordering) before someone flashed `quartus_ref/counter_top.rbf` and discovered Quartus places the design in completely different columns using carry-chain wires that nextpnr-generic doesn't model. A 30-second `quartus_map → fit → asm → cpf` and a flash would have nailed the root cause on day one. Rule: if your open-toolchain build of design D doesn't behave as expected, build D in Quartus, flash it, and diff the two RBFs *before* you start patching the codec.
9. **Self-loop sig-cache entries are unmineable with the two-LUT pair template.** The 61 self-loop entries in `route_cells_full.json` are bloated noise (90-754 cells vs corpus median 135) and cannot be repaired by re-running `selfloop_factory.py` (Quartus refits the design between baseline and feedback compiles, so the diff includes pin reassignments and routing churn unrelated to the LI MUX). If your design needs self-feedback (LE → same LE.dataX), the toolchain currently has no clean route. Avoid self-loops at the synthesis level, or wait for a single-LE differential mining strategy.
10. **DFF has no per-LE CRAM enable cell.** Cyclone IV's flip-flop is intrinsic — always present in every LE. `dff_cells_mined.json` is confirmed bogus (routing infrastructure noise). The FASM `DFF` directive is a parsed no-op. Registered output is selected by downstream routing, not a dedicated FF enable bit.
11. **Preamble-offset bug in CRC detection**: RBF has a 32-byte preamble before CRAM data. CRC position detection must use `(off - 32) % 210 >= 208`, NOT `off % 210 >= 208`. The wrong formula classifies real data at frame_pos 176-177 as CRC (skips them) and real CRC at frame_pos 208-209 as data (includes them), inflating cell counts by ~40-70%. The sig-cache mining pipeline is unaffected (includes ALL byte diffs, no CRC filtering). Header CRC cells (frames 0-24) are mandatory in directive sets — excluding them causes board reset on flash.
