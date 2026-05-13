# CLAUDE.md — EP4CE6 Bitstream Reverse Engineering

Black-box fuzzing pipeline for Altera Cyclone IV EP4CE6F17C8 bitstream (.rbf) reverse engineering. Goal: complete CRAM bit dictionary + open-source toolchain (Yosys → nextpnr → FASM → RBF).

Historical narrative (dated mining events, HW-flash results, closed experiments) lives in `~/.claude/projects/-home-test-EP4CE6/memory/`. This file is the operational reference only — if you want "when / why / how did this land", consult MEMORY.md.

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
# Sig-cache + audit / decomposition tooling (2026-05-04 session):
python3 scripts/sigcache_remine/mine_x4_cross_lab_route.py --src 4,17,14 --dst 4,4,0 --port dataa
    # Single-edge sig-cache miner (Plan D' factory pipeline); writes
    # nv_route_cells.json + route_cells_full.json.  --dry-run to preview.
bash scripts/sigcache_remine/batch_x4_crosslab_multiport.sh
    # Batch driver: 72 X=4 cross-LAB R4 entries (Y4 multi-port + Y17
    # multi-N). ~13 min Quartus wall.  Re-runnable; cached pair RBFs
    # reused.  Clone for other X columns by editing the spec loops.
python3 scripts/iob_slice_mining/audit_clk_pin_pad_nv_overlap.py --save
    # Per-pin IOB_CLK_INPUT × IOB_PAD_NV overlap audit (12 pins).
python3 scripts/cross_lab/probe2_shim_decompose.py --save --verify
    # Decompose 37-cell X33Y4_PROBE2_INFRA shim into ADD/OVER buckets.
python3 scripts/cross_lab/analyze_pl_corpus.py --save
    # 7-variant 1-LE TT corpus intersection vs probe2 shim ADDITIVE.
python3 fuzz/nv_sig_cache_merge.py
    # Merge nv_route_cells.json + legacy → route_cells_full.json.
```

## Directory Layout

- `fuzz/` — fuzzing pipeline (~96 Python modules): `config.py` (constants), `bitstream.py` (LutCodec/RouteCodec/FFCodec/CRC), `fasm2rbf.py`/`rbf2fasm.py` (FASM toolchain), `route_synth.py` (green-island synthesis), `route_signatures.py` (sig-cache backend), `chipdb_gen.py` (nextpnr chipdb), `runner.py`/`compile.py`/`analyze.py` (orchestration)
- `synth/` — open-source toolchain: `ep4ce6_map.v` + `prims.v` (Yosys techmap), `synth_ep4ce6.ys` + `synth_ep4ce6.sh` (run the `.sh` wrapper — it envsubst's `$HOME` / `$NEORV32_ROOT`), `np2fasm.py` (nextpnr JSON → FASM)
- `scripts/` — one-off investigation scripts kept for reproducibility
- `tmp/` — **local scratch only, gitignored**. Do NOT use `/tmp/`; use this dir instead. Promote scripts out of `tmp/` to `scripts/` the moment they're cited from docs or memory.
- `jailbreak/` — CE10 fitter probes (CE6≡CE10 same die, +65% fabric unlocked)
- `results/` — `rbf/` (~2500 files), `route_cells_full.json` (sig-cache; gitignored, regenerate via `route_signatures.build()`; legacy fallback `route_cells.json` = 1,725 entries), `nv_route_cells.json` (canonical Plan D' source for the merger; survives `nv_sig_cache_merge.py` re-runs), `r4_iindex_table.json`, `ep4ce6_bitdb.sqlite`, `fingerprint_*.json`, `sigma_inv_fb8_groups.json` (2,112-entry σ⁻¹ 3-key table), `nv_baseline_pack.json`, `m9k_mode_bits.json`, `iob_clk_input_pad_nv_audit.json` (per-pin overlap risk for IOB_CLK_INPUT × IOB_PAD_NV combination), `x33y4_probe2_shim_decomposition.json` (sidecar for the 37-cell 1-LE shim), `x33y4_pl_corpus_analysis.json` (7-variant 1-LE TT corpus analysis)

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
| `LutCodec` | `write_tt(base_rbf, mask)` → RBF, `read_tt(rbf, zero)`, `from_cram_model(x,y,n)` | **XOR-delta, not absolute!** `mask = target ^ base_tt`. `from_cram_model` uses σ⁻¹ permutation lookup keyed by `(foff, fb8, group)` — 2112 entries, 5-level fallback: exact 3-key → nearest-foff 3-key → exact 2-key → nearest 2-key → identity. Data: `results/sigma_inv_fb8_groups.json`. Residual: fb8=7 × group=4 silicon-geometry blocked (X=8 has no LAB at Y≥12). σ⁻¹'s 16 claimed TT cells per LE are real TT (mining-verified 2026-05-05, `results/real_tt_classification.json`) for **symmetric masks at LE_0**. **X=4 LE_0 σ⁻¹ permutation BROKEN for asymmetric masks** (0x8888→reads 0xC0C0, 0xAAAA→reads 0xF0F0) — see Pitfall #16. Phase 2 verdict 2026-05-13: canonicalization cells are **globally position-invariant** within N=0 LAB columns — codec extension is a single global table (3 sets: 25 axis_a_b + 16 axis_a_c + 7 neg, 35 cells total in shared config, 0 lab_cram). Memory: `sigma_inv_3key_discovery.md`, `phase3_fix_silicon_validated_2026_05_05.md`, `sigma_inv_extension_unneeded_2026_05_07.md`, `sigma_inv_x4y4n0_not_a_4perm_2026_05_12.md`, `canon_cells_phase2_global_invariant_2026_05_13.md`, `sigma_inv_codec_extension_scoping_2026_05_13.md`. |
| `RouteCodec` | `read_c4/r4/r24/local_interconnect()`, `apply_routing(ops)` | Round-trip verified. LI writes take explicit `pairs`, NOT i_idx |
| `FFCodec` | `write_arst/write_ena()` — 61 absolute offsets each | FASM `DFF.ARST`/`DFF.ENA` **disabled** (header-band noise) |
| `patch_rbf_crc(rbf)` | Recomputes CRC-16 for frames 25..1751 | **Mandatory** before flashing any modified RBF |

**CRC spec**: CRC-16/IBM, poly 0x8005 (reflected 0xA001), init 0xFE54, frames 25..1751 (208 data + 2 CRC per frame). Frames 0..24 = header, do NOT touch.

**SAFETY**: `validate_safe_for_hardware(rbf, zero)` checks LI MUX envelopes (P0 anchor / P8 tail / mode = paired/alternating/driver*/edge_*).  Recognized modes include `driver_single` (`{8: [single_base]}`) silicon-validated against Quartus gold (memory `step_3_substantially_closed_2026_05_02`).  Always call before flashing — but validator scope is LI MUX class only; it does NOT check header band consistency, non-LAB-column writes, GCLK distribution completeness, or output-buffer drive contention (memory `path_alpha_led_blink_silicon_failed_2026_05_02`).  For silicon-functional validation, also cross-check vs Quartus gold cell set or use ζ pipeline.

## FASM Directives (`fuzz/fasm2rbf.py`)

| Directive | Example | Status |
|-----------|---------|--------|
| `LUT` | `X10Y10N0.LUT = 0x8888` | OK — auto-compensates XOR base via minterm_0 |
| `ROUTE` | `ROUTE X10Y10 -> X10Y12N4.datab` | OK — sig-cache lookup (6 or 7-tuple) |
| `ROUTE` (sn>0) | `ROUTE X5Y3N4 -> X4Y3N6.datad` | OK — 7-tuple key |
| `GCLK` | `GCLK` | OK — 17 position-independent cells (legacy local-clock, not real GCLK_BUS) |
| `GCLK_PIN` | `GCLK_PIN PIN_E1` | OK — per-pin XOR activate set. **12 pins mined** on F17 (E1/R8/N1 + 9 dedicated clock pins). Mining: `fuzz/clk_pin_autoforce_probe.py --pin {PIN}`. Data: `results/clk_cross_pin_spine_check.json`. See memory `clk_pins_full_f17_coverage.md`. |
| `LAB_CLK_SEL` | `LAB_CLK_SEL X10Y4` | OK — per-LAB CLK_SEL N-invariant layer (XOR). 13 LABs mined. Re-mine: `fuzz/clk_lab_sel_probe.py --lab X,Y`. |
| `LAB_CLK_SEL_LE` | `LAB_CLK_SEL_LE X10Y4N0` | OK — per-LE CLK_SEL layer (XOR, disjoint from `LAB_CLK_SEL`). **Functionally required** (N-invariant alone = LED-always-off). N∈{0,2,4,6,8} mined for all 14 LABs. Data: `results/clk_lab_sel_per_le.json`. Extend via `clk_lab_sel_n2_batch.py` after editing `N_SLOTS` in `clk_lab_sel_probe.py`. |
| `DFF` | `X10Y10N0.DFF` | **NO-OP** — DFF is silicon default (no CRAM cells) |
| `BIT` | `BIT offset bp` | OK — raw cell flip |
| `SRC` | `SRC X10Y10` | OK — per-source overhead |
| `LUT_ARITH` | `X4Y18N0.LUT_ARITH = 0x0000` | OK — v4 position-independent blob (100 SETs + 4 CLEARs) for 8-LE half-LAB chains at ANY LAB. Per-width table at `results/arith_blockband_by_width.json` (widths 2..16). |
| `LUT_ARITH_MULTI_LAB` | `LUT_ARITH_MULTI_LAB WIDTH=17` | OK — widths 17..32 multi-LAB chain activation **SILICON-VALIDATED at W=17 + W=23** (W=17 LED solid-on at 763 Hz; W=23 5.96 Hz visible blink, both at LAB(4,18)+(4,17), 2026-05-03 night).  Codec asset: `results/arith_blockband_by_width.json` `multi_lab["16+1..16+16"]`.  Each entry has `set` (XOR-flip) and `clear` (AND-clear, force 0) — `clear` cells target v4-universal-blob OR-in overflow that other phases (LAB_CLK_SEL etc.) may also pre-set + dedup-lock.  Carry-input LI MUX cells at LAB(4,17) (pairs varying per width) live in `set`.  **Consumer dedup contract**: LUT_ARITH_MULTI_LAB SET-class cells skip cells in `_iob_route_dedup` (defeats OUTROUTE_G15 XOR cancellation); CLEAR-class cells AND-clear unconditionally (must override dedup pre-sets).  Validator extended with `paired_carry_input` mode for Quartus-emitted multi-LAB carry-receiver LI patterns.  np2fasm consumer NOT wired (Yosys `$alu` techmap caps at single-LAB; CE6_CARRY techmap extension + nextpnr cout→cin pip routing for multi-LAB needed).  See memory `multi_lab_carry_silicon_validated_2026_05_03.md`. |
| `IOB_IN`/`IOB_OUT` | `IOB_IN PIN_M16` / `IOB_OUT PIN_F15` | OK single-axis (44/44 bit-perfect) — XOR delta from `iob_in_E15.rbf` baseline. For G15-output designs use `IOB_PAD_NV` + `OUTROUTE_G15` instead. |
| `IOB_ROUTE` | `IOB_ROUTE PIN_E16 -> X16Y4N0.dataa` | OK — pin→LE-port sig lookup. **Two apply-paths**: default live path (padnv_cells > absolute_cells; absolute_cells get dedup + `off<5282` hdr-skip — padnv_cells get NEITHER as of 2026-05-11 `93f9cb9`) for IOB_PAD_NV-derived designs; legacy path (`bitgen(legacy_iob_route=True)` — single_le_cells > stale > absolute, pure XOR, no dedup) for simple_led single-LE designs. **np2fasm pragma channel**: `np2fasm --legacy-iob-route` emits `# fasm2rbf: legacy_iob_route=1`; callers parse with `fasm2rbf.parse_pragmas(text)` and forward to `bitgen(**pragmas)`. See memory `fix_a_legacy_iob_route_flag_landed.md`, `fix_b_single_le_remine_landed.md`, `np2fasm_legacy_iob_route_pragma.md`, `iob_route_hdr_skip_pivot_2026_05_11.md`. Re-derive single_le: `python3 scripts/iob_slice_mining/sweep_single_le.py --orphans-only --include-known --skip-build`.  Re-derive padnv at new (X,Y,N): `python3 scripts/iob_slice_mining/mine_padnv_x4y4n0.py` (template; verify-step currently fails pending σ⁻¹ permutation re-mining — Pitfall #16). |
| `IOB_BASELINE_NV` | `IOB_BASELINE_NV` | OK — 129-cell hdr-band bridge (was 132 before the 2026-05-03 c430c4f 3-cell strip). **SUPERSEDED by IOB_PAD_NV** for G15-output designs. |
| `IOB_PAD_NV` | `IOB_PAD_NV` | OK — 139-cell IOB pad infra (was 241 before the 2026-05-04 a5e4a0e cleanup) for E16+M16 input + G15 output, direct delta from `nv_zero_global`.  **Carry-chain extension**: when both `IOB_PAD_NV` and any `LUT_ARITH`/`LUT_ARITH_MULTI_LAB` directive are present, fasm2rbf additionally XOR-applies 74 cells from `iob_pad_arith_ext_cells` in the same data file (silicon-required for multi-LE carry-chain G15 designs; W=17 + W=23 silicon-validated; commit c430c4f).  Data: `results/output_route_nv_mining.json` → `iob_pad_cells` + `iob_pad_arith_ext_cells`.  np2fasm emits IOB_PAD_NV automatically when SLICE→G15 output routing detected. |
| `OUTROUTE_G15` | `OUTROUTE_G15 X10Y10N0` | OK — position-specific SLICE→G15 output routing (38-67 cells). 33 positions mined. Data: `results/output_route_sigcache.json`. |
| `IOB_CLK_INPUT` | `IOB_CLK_INPUT PIN_E1` | OK for 12 pins on F17 — hdr delta activating a clock-bank pin as GCLK driver. Extensible via `scripts/iob_slice_mining/compute_clk_pin_hdr.py --build --pin {PIN}` → `results/iob_clk_pin_hdr_cells.json`. **PIN_E1 entry is legacy 16-cell mining**; 2026-05-03 re-mining attempt produced 40 cells but those were anchor (`iob_in_E16.rbf`) artifacts — reverted. Caveat for callers: data is calibrated against `IOB_BASELINE_NV` (129-cell) baseline; when used together with `IOB_PAD_NV` (139-cell, M16-active assumed), 11 cells overlap and double-flip — corrected by `IOB_RESERVE_PIN_M16` Group B when M16 is reserved. **All other 11 pins have the same latent calibration mismatch with IOB_PAD_NV** (M16=8 cells, R8=5, M15=2, others 1; per-pin counts at `results/iob_clk_input_pad_nv_audit.json`).  fasm2rbf emits a warning at runtime when IOB_PAD_NV + IOB_CLK_INPUT PIN_X are both present for X ≠ E1 — until that pin's correction is mined, those cells silently miscalibrate to nv state.  Audit tool: `scripts/iob_slice_mining/audit_clk_pin_pad_nv_overlap.py --save`. |
| `IOB_RESERVE_PIN_M16` | `IOB_RESERVE_PIN_M16` | OK — **66-cell XOR delta** modeling Quartus default `RESERVE_ALL_UNUSED_PINS=As input tri-stated with weak pull-up` when M16 is unused.  Group A 24 hdr (M16-bank-default) + Group B 9 hdr (IOB_PAD_NV/IOB_CLK_INPUT_E1 calibration mismatch correction) + Group C 9 hdr (frame-0 residuals) + Group D 24 fabric (LAB-column-default at X<10 + GCLK_PIN_E1 calibration + X33Y4_INFRA region cells).  Data: `results/iob_reserve_pin_m16_cells.json`.  np2fasm auto-emit gate: `use_pad_nv AND PIN_M16 not in design IOBs AND not has_carry` (carry exclusion preserves W=23 silicon-validated 905dfc85 byte-identity since hand-FASM never set those bits).  Calibrated against probe2 silicon-validated reference (md5 d4073d2e..) + 9 simple_led_E16_to_G15_clk{PIN}.rbf discriminators + cl_and gold (47ad9ed9). See memory `probe2_open_software_bisect_2026_05_03.md`. |
| `X33Y4_PROBE2_INFRA` (auto) | implicit shim | Auto-applied by fasm2rbf when 1-LE @ SLICE_X33_Y4_N4 topology detected (gate: `iob_pad_nv AND x33_luts == {(4,4)} AND LAB_CLK_SEL X33Y4 AND M16 ∉ IOBs`).  37-cell override covering IOB_E16→X33Y4N4.dataa routing + per-LE infra unique to 1-LE 33Y4 placement.  Disjoint from cl_and 2-LE shim (which gates on both N=4+N=6 occupied).  Data: `results/x33y4_probe2_infra.json`.  **Decomposition** (sidecar `results/x33y4_probe2_shim_decomposition.json`, tool `scripts/cross_lab/probe2_shim_decompose.py`): 33 ADDITIVE (Quartus has bit, no current directive emits it — pure 1-LE-class infra; 24 block-band + 4 X=8 + 4 X=32 + 1 hdr; cross-checked against 13 cl_*/rcl_* 2-LE variants → 0/33 fire = truly 1-LE-only, NOT migratable to a generic shared directive) + 4 OVER-CANCEL (open over-emits, gold doesn't have them — all 4 attributable to X33_LUT_CODEC `nibble_classes[(4,4)][1]` over-emit when only 1 LE present at X33Y4; same 4 cells fire correctly in cl_andn/cl_or/cl_xor 2-LE gold).  Verified probe2_open byte-identical to Quartus probe2 (md5 d4073d2e..) for the calibration design.  See `_x33y4_probe2_shim_should_apply` + memory `probe2_open_software_bisect_2026_05_03.md`. |
| `NV_BASELINE_PACK` | `NV_BASELINE_PACK` | OK — meta directive (21 640 XOR cells) that reproduces `nv_zero_global.rbf` on top of `make_pure_zero_rbf()` byte-for-byte. Subs: `IOB_BANK_DEFAULT_PACK`, `LOCAL_CLK_E1_BASELINE`, `LOCAL_CLK_PATH_A`, `LAB_LOCAL_CLK X{x}`, `M9K_BLOCK_DEFAULT_PACK`, `MULT_BLOCK_DEFAULT_PACK`, `NV_BLOCK_COL_INFRA`. Data: `results/nv_baseline_pack.json`. np2fasm emits with `--base pure`. HW flash equivalence not yet confirmed — keep `nv_zero_global.rbf` as HW-default. |
| `DFF.ARST/ENA` | — | **DISABLED** — header-band noise unresolved |
| `M9K.INIT_{w}x{d}` | `X15Y10N0.INIT_9x512 = 0x...` | **9×512** (33 sites) and **18×512** (5 sites): codec `fuzz/m9k_init_basis.write_init` (2-words/frame linear formula). np2fasm emits via `_emit_m9k_init`. Byte-identical vs Quartus at X15_Y10_N0 18x512 via `scripts/m9k_e2e_smoke.py`. **SDP 4×2048** (full 4-bit, X15_Y10_N0 calibrated 2026-04-27): `write_init_sdp4x2048` / `read_init_sdp4x2048` — 8 words/frame, `_SDP_4X2048_BIF` table, bit-stride -2; bit 0 silicon-validated via stripe64 flash. **SP 9×1024** (X15_Y10_N0 calibrated 2026-04-27): `write_init_sp9x1024` / `read_init_sp9x1024` — 4 words/frame, `_SP_9X1024_BIF=[86,68,85,67]`, bit-stride -2. **SP 36×256** (X15_Y10_N0 calibrated 2026-04-27): `write_init_sp36x256` / `read_init_sp36x256` — 2 words/frame split across two frame regions (lower base+0 for bits 0..15/32..33; upper base+128 for bits 16..31/34..35). All four widths use the dedicated codec; the linear formula in `M9K_INIT_ANCHORS` for 4×2048/9×1024/36×256 is WRONG (flagged in-source with ⚠️) and must NOT be used with `write_init`. **Cross-site coverage**: `SDP_4X2048_BASE_FRAMES` / `SP_9X1024_BASE_FRAMES` / `SP_36X256_BASE_FRAMES` each contain only `X15_Y10_N0` — non-Y10 sites raise KeyError. SDP extrapolation was audited 2026-04-28 (Quartus gold-vs-allzero diff at X15_Y16/X27_Y7 produced TP=0/4096 vs the formula → emission diverges from Quartus ground truth; no SDP silicon flash performed at non-Y10). SP 9×1024 and SP 36×256 silicon-validated only at X15_Y10. **SP 9×512 cross-site is silicon-validated at 8 sites** (X15 Y=2,4,10,12,16,18,21 + X27_Y7) covering 8/8 bp values via the per-site `(anchor, bp)` mechanism in `M9K_INIT_ANCHORS`; differential stripe-rate test passed in both M9K columns. See memory `sp_9x512_cross_site_silicon_hw_validated_2026_04_28.md` and `sp_9x1024_36x256_codec_silicon_hw_validated_2026_04_28.md`. |
| `M9K_MODE_{w}x{d}[_template]` | `X15Y10N0.M9K_MODE_9x512_m9k_blink_diff_nv` | Per-site M9K mode bits.  Templates: `_m9k_blink_diff_nv` (silicon-validated at SP 9×512 X15_Y10; covers SP 8×64 / SDP 8×1024 / TDP 16×32 / ROM 32×256 / SP 36×256 byte-id at X15_Y10; mined cross-site for all 23 NEORV32 placements via `scripts/m9k_diff_nv_neorv32_mine_verify.py`) is the **silicon-correct path for solo / blink-class designs**.  Other templates (`_quartus_gold*`, `_inferred_goldintersect`) are silicon-broken and gated off in np2fasm — kept in code for archival only. **For multi-M9K designs (NEORV32-class), per-site `m9k_blink_diff_nv` covers only ~3% of NEORV32's 417 block-band cells** (memory `m9k_solo_mining_insufficient_for_neorv32_2026_05_01`); use the new `DESIGN_BLOCK_BAND_PACK` directive (below) instead.  Mining: `scripts/m9k_blink_{sp,sdp,tdp,rom}_build.py` → `scripts/m9k_blink_diff_nv_mine.py`. Multi-M9K reference builder: `scripts/m9k_blink_multi_build.py`.  Full history: memory `option_3_residual_silicon_validated_2026_05_01` + `m9k_blink_diff_nv_landed_2026_04_30`. |
| `DESIGN_BLOCK_BAND_PACK` | `DESIGN_BLOCK_BAND_PACK neorv32` | OK — silicon-validated 2026-05-01 on AX301 (memory `option_3_residual_silicon_validated_2026_05_01`).  XOR-applies the full block-band cell set (frames 1692-1738, byte<208) for a per-design tag mined from that design's own Quartus reference.  Replaces the silicon-broken `quartus_gold + --base nv` path for multi-M9K NEORV32-class designs where per-site `M9K_MODE` covers <10% of cells.  Codec build: `python3 scripts/mine_design_block_band.py --tag X --rbf X.rbf` (one-time, needs Quartus).  Runtime: np2fasm `--design-pack TAG` flag emits the directive and suppresses per-site M9K_MODE (no double-flip).  Storage: `results/design_block_band.json`.  Tags currently mined: `neorv32` (417 cells), `m9k_23_clone` (16), `arbiter_2m9k` (11), `visible_2m9k` (12 silicon-validated). Regression: `scripts/design_block_band_pack_test.py`. |

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

`synth_route(zero, src, dst)` → bit-perfect RBF. Sig-cache path serves all CE6-standard green-zone + Plan D' factory routes. CRAM is interleaved (NOT topologically isomorphic to layout).

Current harness score: **731/731 bit-perfect across all 24 islands** (CE6 standard 686/686 + jailbreak/edge 45/45). `synth_route` does a snapshot lookup (`_snapshot_ops_if_present`) BEFORE `parse_need`, so jailbreak/edge LABs hit the exact Quartus cell set from the fingerprint snapshot. See memory `harness_731_closure.md`.

15 CE6 green islands: (4,4), (10,4), (10,10), (10,14), (13,10), (16,4), (16,8), (16,14), (19,14), (22,12), (22,16), (25,6), (28,10), (28,18), (31,12).
9 jailbreak/edge islands: Y=15 × {10,11,12,13,14,17,18}, Y=5 × {18,19}.

## Non-LAB Blocks (Phase 5.0)

**LOC syntax** (hierarchical MegaFunction path, NOT coordinate alias):
- DSPMULT: `-to "lpm_mult:u|mult_qpl:auto_generated|mac_mult1"`, 42 sites (Y1..21 × N{0,1})
- M9K: `-to "u"` (short form), X∈{15,27}, 126 sites

**Two CRAM bands**: block enable/mode (frames 1692-1738) + clock-net (~1007-1013).

**M9K init codec**: `byte(word,bit) = anchor + (word//2)*210 - (word%2) - 2*bit`, bp=6. 33 anchors calibrated.

**Rules**: NEVER mine non-LAB with VIRTUAL_PIN. Always filter CRAM-only (off ≥ 5282) — header band has 4-5 bit/seed noise floor.

## Phase 5.3 — Open-Source Toolchain

Target: `Verilog → Yosys → nextpnr-generic → np2fasm → fasm2rbf → openFPGALoader`

**Completed**: `chipdb_gen.py` (12,131 bels, 90,261 wires, 3.66M pips after 2026-05-04 carry_A/B / LE_INTERNAL / GND→CIN extension), techmap (LUT4+DFF+`$alu`→CE6_CARRY chain via `alumacc`), `np2fasm.py` (emits IOB_PAD_NV / IOB_ROUTE / OUTROUTE_G15 / GCLK_PIN / LAB_CLK_SEL / LAB_CLK_SEL_LE / IOB_CLK_INPUT / M9K.INIT / M9K_MODE / DESIGN_BLOCK_BAND_PACK / LUT_ARITH per-LE), `fasm2rbf` all directives.

**HW-validated end-to-end designs**: registered AND gate at X16Y4N0 (0 fabric diffs vs Quartus gold), 5-bit carry chain counter at LAB(16,4), two-LAB cross-LAB AND→DFF (BIT reconstruction), 2-M9K visible-blink @ X15_Y4+X15_Y10 via `DESIGN_BLOCK_BAND_PACK visible_2m9k` (silicon-validated 2026-05-01).  Details in memory `pipeline_test_e2e_status.md`, `two_lab_gold_validated.md`, `option_3_residual_silicon_validated_2026_05_01.md`.

**Pipeline-validated (RBF-SAFE, silicon flash blocked on sig-cache mining)**: 8-bit and 24-bit `led_blink.v` (`scripts/led_blink/build_open.py` + `build_open8.py`) build through alumacc-powered Yosys → `nextpnr-generic --router router2` → `np2fasm` → `fasm2rbf`.  Memory `path_alpha_arith_routing_unblocked_2026_05_04.md`.

**Silicon-validated zero-Quartus open toolchain (2026-05-04)**: `scripts/led_blink/build_open23.py` produces an RBF byte-identical (md5 905dfc85ad37c44da9966dfbd9cf3a16) to the silicon-validated W=23 hand-FASM.  AX301-flashed 5.96 Hz visible blink confirmed.  Verilog → CRAM zero-Quartus path is silicon-correct for arith-mode LUT+DFF chains widths 17..32 at LAB(4,18)+(4,17).  Memory `zero_quartus_arith_byte_identity_2026_05_04.md`.

**nextpnr invocation**: `source $HOME/opt/oss-cad-suite/environment` first; `--router router2` (router1 can't multi-hop); `--pre-pack` works (chipdb_ep4ce6.py guards the flow-driver block via `_invoked_as("--run")` since 2026-05-01 commit d52d5d6).

**Open-toolchain Step 3 SAFETY status (2026-05-02)**: pipeline_test 22→0 LI MUX UNSAFE.  6 commits c218e24..731a424 landed: wx=3 boundary fix, lenient=False on 4 build_open scripts, chipdb `--no-jailbreak --out-tag nojb` sidecar (22-col-only at `results/chipdb_ep4ce6_nojb.{py,_data.json.gz}`), li-op union merge, Path X src_driver suppression, **LI MUX snapshot-restore lockdown** (defeats σ⁻¹ over-claim of ~160 TT cells per dense multi-LE design), `driver_single` validator mode.  build_open scripts use the nojb sidecar.  Memory `step_3_substantially_closed_2026_05_02.md`.

**Open-toolchain functional gap (Step 4 pending)**: pipeline_test_open.rbf and led_blink_open.rbf flash clean but LED stuck — three deeper gaps validator can't see: 494 OPEN-only OTHER region cells (NV_BASELINE_PACK over-emission suspect), 64 GOLD-only HEADER_FRAMES cells (config-controller-reset trigger), 270 GOLD-only BLOCK_BAND cells (GCLK column distribution, never mined).  Memory `path_alpha_led_blink_silicon_failed_2026_05_02.md` + `next_session_entry_2026_05_03.md`.

## Phase 5.4 — Carry Chain (HW-verified)

Arithmetic mode activation lives in the **block band** (frames 1692-1738, bp=2), NOT in LAB CRAM columns. The `LUT_ARITH` FASM directive applies a per-LAB blob of ~100 cells.

**Pieces landed**:
1. `chipdb_gen.py` — 8,126 `cout→cin` direct pips between adjacent LE bels
2. `synth/ep4ce6_map.v` + `synth/prims.v` — `$alu` → per-bit CE6_CARRY chain (LE-internal feedback, no Route-A buffers)
3. `synth/np2fasm.py` — CE6_CARRY chain walker, emits `LUT_ARITH = 0x0000` + `DFF`, skips intra-LE ROUTE
4. `fuzz/fasm2rbf.py` — `LUT_ARITH` directive loads arith block-band blob
5. `fuzz/prepack_carry.py` — BEL pinning up to 16-bit chain (`ALL_NS=16`), skips nextpnr

**Key facts**:
- Arith blob is per-LAB, not per-LE (100 cells regardless of which LEs use arith)
- Arith blob is position-independent (v4 triangle test) and per-WIDTH, not per-N-slot
- LUT SRAM = 0x0000 for standard +1 counter (function encoded in block-band)
- Quartus carry counter has ZERO external route cells — DFF→carry feedback is LE-internal
- 4 CLEAR cells are constant across all single-LAB widths (universal LAB arith-enable reset)

History: memory `phase54_first_flash_lab418.md`, `carry_chain_synth_landed.md`.

## Phase 7 — ζ Escape Hatch

Two reachable paths from Verilog/VHDL to AX301 silicon:

1. **Native**: `.v → Yosys → nextpnr-generic → np2fasm → fasm2rbf → flash`. HW-verified for small/medium designs. Blocked on chipdb routing-model density at NEORV32 scale.
2. **ζ escape hatch**: `.v → Quartus → scripts/bit_workaround/quartus_gold_to_bit_fasm.py → fasm2rbf → flash`. Diffs Quartus gold RBF against `results/rbf/nv_zero_global.rbf`, emits one `BIT` directive per differing bit. Rebuilt RBF is byte-identical to Quartus gold; total wall time ≈ 0.5 s regardless of design density.

**ζ production pipeline** (canonical entry point): `scripts/bit_workaround/zeta_pipeline.py` wraps raw ζ + fasm2rbf + byte-identity gate + optional flash + optional UART verify. Emits sidecar `<stem>.manifest.json` (SHA256 + region cell counts + git HEAD) consumed by `zeta_manifest_diff.py`. Supports `--rebuild-check` on `.qpf` input to catch non-deterministic Quartus builds. Companions: `zeta_selftest.py` (sub-second pre-commit gate, `git config core.hooksPath .githooks`), `zeta_regression.py` (corpus walker over `tests/zeta_corpus/manifest.json`, `--reanchor[-all]` to update), `zeta_rbf_diff.py` (region-aware diff — use instead of `cmp -l`), `zeta_manifest_diff.py` (manifest-only build-vs-build drift).

**HW-validated designs via ζ**: NEORV32 bootloader (full 4712 LE / 19 M9K) on AX301 at 19200-8N1 UART; Linux 6.6.83 RISC-V boot via xmodem. See memory `neorv32_zeta_hw_validated.md`, `path1_bit_workaround_validated.md`.

**When to use which**: native for small/medium single/cross-LAB; ζ for NEORV32-class (>1000 LE) or anything Quartus can build but nextpnr can't route.

## Tools

- **Quartus 21.1 Lite**: `$HOME/intelFPGA_lite/21.1/quartus/bin/`
- **RBF generation**: `quartus_cpf -c -o bitstream_compression=off` (**NEVER** `sof2rbf.py`)
- **Programming**: `$HOME/see_neorv32_run_linux/tools/openFPGALoader/build/openFPGALoader -c usb-blaster`
- **Hardware**: AX301 board, EP4CE6F17C8, USB-Blaster JTAG
- **Pin map**: KEY1=E15, KEY2=E16, KEY3=M16, KEY4=M15, LED0=G15 (active-high; keys active-low)
- **UART capture**: `scripts/uart_observe.py` (pyserial; default `/dev/ttyUSB0`, specify `--baud` — no default)
- **NEORV32 Linux host flow**: `~/see_neorv32_run_linux/host/boot_linux.py --rbf <file.rbf>` drives stage2 upload + xmodem of kernel/DTB/initramfs

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
8. **Always cross-check codec output against Quartus's own build of the same Verilog before chasing low-level bugs.** If your open-toolchain build of design D doesn't behave as expected, build D in Quartus, flash it, and diff the two RBFs *before* patching the codec.
9. **Self-loop sig-cache entries are unmineable with the two-LUT pair template.** The 61 self-loop entries in `route_cells_full.json` are bloated noise (90-754 cells vs corpus median 135). Avoid self-loops at synthesis level, or wait for a single-LE differential mining strategy.
10. **DFF has no per-LE CRAM enable cell.** Cyclone IV's flip-flop is intrinsic. `dff_cells_mined.json` is bogus. The FASM `DFF` directive is a parsed no-op.
11. **Preamble-offset bug in CRC detection**: RBF has a 32-byte preamble before CRAM data. CRC position detection must use `(off - 32) % 210 >= 208`, NOT `off % 210 >= 208`. Header CRC cells (frames 0-24) are mandatory in directive sets — excluding them causes board reset on flash.
12. **Cross-LAB ROUTE without sig-cache is silicon-hostile** (silicon-validated 2026-05-04). When np2fasm warns `no sig-cache (cross-LAB): ...`, the formula path emits cells at structurally wrong CRAM offsets → corrupts config-controller-validated cells → FPGA reset on flash (NOT just functional incorrectness). `validate_safe_for_hardware` does NOT detect this class. `scripts/led_blink/build_open.py` has a REFUSE-TO-BUILD guard scanning np2fasm warnings; future build_open scripts should follow the same pattern. Mining tool: `scripts/sigcache_remine/mine_x4_cross_lab_route.py` (single-edge sig-cache miner via Plan D' factory pipeline). Memory: `d_i_silicon_failed_2026_05_04.md`.
13. **Phase 3 LI MUX std_lut TT collision — FIXED 2026-05-05 (silicon-validated for LE_0 symmetric masks).** Phase 3 unconditionally restored 18 LI MUX cells per LAB at `(group, slot)`-derived bp via `_cram_group_bit(y)`. For Y where Phase 3 bp == LE's LUT TT bp (Y ∈ {2,4,5,7,10,14,17} hit; Y ∈ {3,6,18,21} safe), restoration overwrote Phase 1+2 LUT TT writes — `X4Y4N0.LUT = 0xaaaa` decoded as 0xF0F0 → output stuck. Real bug: only 2 of the 18 Phase 3 cells are LI MUX; the other 16 are real TT (mining-verified per LE_0). **Fix**: `fuzz/fasm2rbf.py` Phase 3 builds `std_lut_tt_cells` (union of `tt_cells_cache[(x,y,n)]` for non-arith std_luts) and skips those `(off, bp)` keys in `li_locked_state` restoration. LUT_ARITH LEs unaffected (Phase 1 skips arith). Silicon-validated 2026-05-05 via hybrid RBF (Quartus gold + 12 σ⁻¹ TT flips). **Closure scope: LE_0 at symmetric masks ONLY** (XOR4/XNOR4 0x6996/0x9669) — empirically confirmed 2026-05-12 by 24-perm σ⁻¹ probe at X4Y4N0: 0/24 permutations fit asymmetric-mask silicon, codec gap is ~16 cells of input-permutation choice OUTSIDE per-minterm TT model (Pitfall #16, memo `sigma_inv_x4y4n0_not_a_4perm_2026_05_12`). N>0 expected to generalize by symmetry but not directly mined. Mining: `scripts/sigma_inv_real_tt_mining/mine_real_tt.py` (had `n // 2` conv bug; fixed 2026-05-10). Regression: `fuzz/test_phase3_li_mux_lut_tt.py`. Memory: `phase3_fix_silicon_validated_2026_05_05.md`, `phase3_li_mux_lut_tt_collision_2026_05_04.md`.
14. **Mined cross-LAB R4 sig-cache entries are context-dependent** (silicon-validated 2026-05-04). Mining diff-vs-nv_zero captures the CRAM cells for a specific Quartus router decision in the bare 2-LUT mining design. When applied in dense runtime context (e.g., 24-LE carry chain in same column), the chain consumes routing resources the mined route assumed free → silicon route doesn't form → input floats / output stuck. Codec-level evidence (RBF passes validate, LUT TT decodes correctly) does NOT prove silicon function. For arbitrary chain widths in open-toolchain builds, prefer placing LE driver at a chain-end slice with mined OUTROUTE_G15 (intra-LAB) rather than buffer LE + cross-LAB R4. Memory: `d_i_silicon_two_failures_2026_05_04.md`.
15. **Mining script `n // 2` convention bug** (audit 2026-05-08, extended 2026-05-10). Mining scripts (`scripts/minimal_1lut/sweep_outroute_nv.py:107`, `scripts/minimal_1lut/mine_one_outroute.py:84`, `scripts/path_b_chain_mining/mine_intralab_route_x4y17n14_to_n16.py:162` pre-fix, **`scripts/sigma_inv_real_tt_mining/mine_real_tt.py:76` pre-fix found in 2026-05-10 audit extension**) used `loc = LCCOMB_X{x}_Y{y}_N{n // 2}` to place the mining LE.  But the runtime convention (chipdb `LE_N=[0,2,...,30]`, np2fasm SLICE bel n, fasm2rbf sigcache key) is `n = chipdb SLICE_N = Quartus LCCOMB N = 2 × LE_index`.  So target sigcache key `X{x}Y{y}N{n}` should mine at `LCCOMB_X{x}_Y{y}_N{n}` — NOT `n//2`.  Effect: tag `X4Y17N16` was mined at `LCCOMB_N8` (= LE_4), but np2fasm runtime expected LE_8.  By accident, tags with `n=0` mined correctly (0//2=0=LE_0).  Verified via `scripts/path_b_chain_mining/conv_verify_x4y17.py` (3-anchor probe set: `cells_n0` byte-identical to `sc_N0` 54/54; distinct RBFs/cells at `LCCOMB_N0/N12/N16`; 90/105/115 byte pairwise diffs prove placements are honored).  Likely co-cause of β' Path B v1/v6 silicon failures (buffer mined at LE_4 but runtime emitted OUTROUTE_G15 X4Y17N16 expecting LE_8 → 33 LE-specific cells missing, 23 wrong cells emitted).  W=23 silicon-validated `X4Y17N12` survived because that entry was hand-filtered post-mining (commit `b5cbe49` 2026-05-02) to keep only silicon-working cells.  Always audit any new mining script for this `//2` antipattern.  Mining scripts now fixed (commit b962722 + audit follow-up + 2026-05-10 mine_real_tt.py fix).  σ⁻¹ analysis scripts (`sigma_inv_mine.py`, `sigma_inv_mine_y3_*.py`, `sigma_inv_mine_group4*.py`, `sigma_inv_mine_existing_groups.py`) all use `k = n // 2` correctly — that `k` is an LE_idx array index, NOT Quartus placement; audited 2026-05-10 NOT a Pitfall #15 bug.  Memo: `conv_bug_discovery_2026_05_08`, audit extension in `gamma_x4_crosslab_batch1_2026_05_10`.
16. **γ X=4 cross-LAB cluster — Bug #1 strip + Bug #2/#3 codec fixes landed; σ⁻¹ permutation re-mining is the long pole.** Three compounding bugs surfaced 2026-05-10..11:
    - **Bug #1 (PARTIAL, `df335d8`)** — Plan D' factory mining bakes IOB+CLK infra into cross-LAB ROUTE diff; runtime `IOB_PAD_NV` + `LAB_CLK_SEL_LE` re-emit those cells → double XOR → silently absent → silicon failure. Affects 96/109 X=4 entries; same class expected at X=10/16/22/25/28/31. Fix: `scripts/sigcache_remine/strip_iob_overlap.py --apply --column X` subtracts `IOB_PAD_NV ∪ LAB_CLK_SEL_LE(s/d) ∪ LAB_CLK_SEL(s/d)` per-entry, idempotent, patches `nv_route_cells.json` + `route_cells_full.json` in lockstep. **Re-run after every `fuzz/nv_sig_cache_merge.py`.**
    - **Bug #2/#3 (codec-only, FIXED)** — `03b91c6` extends Phase 3 std_lut TT skip to IOB_PAD_NV / OUTROUTE_G15 (with X33Y4 shim exemption) + strip ROUTE×OUTROUTE_G15 overlap-at-emit. `93f9cb9` gates `off<5282` hdr-skip on `needs_dedup` so padnv-bucket IOB_ROUTE entries can carry header cells. Silicon md5s preserved (W=23 `905dfc85`, probe2 `d4073d2e`, cross_lab_x33 `47ad9ed9`); ζ 7/7, test_phase3 11/11, green_zone 731/731, roundtrip 2035/2035.
    - **σ⁻¹ codec gap (BLOCKER, scope reduced 2026-05-13 Phase 2)** — Probe at X4Y4N0 found NO 4-permutation σ⁻¹ fits silicon (24/24 perms ruled out via {0x8888, 0xAAAA, 0xF0F0} mask combo). Direct 0xAAAA-vs-0xF0F0 diff = 16 cells, 0 in TT region: silicon encodes input-permutation choice in ~16 cells **outside** the codec's per-minterm TT model (header band offsets 41-74 + block-band 361605-365142). 0x8888 also uses 12 TT cells vs codec's 8. Implication: σ⁻¹ "re-mining" is a codec-model-extension problem (extract the canonicalization cells per input choice), not a per-position 4-perm table patch. **Phase 2 probe (2026-05-13, commit `4eadf8c`) verdict: GLOBAL POSITION-INVARIANCE for 1-input passthrough canon-cells** — 12 positions covering X∈{4,10,16,22,28}×Y∈{2,17}+extras×N=0 are byte-identical across every diff label (5 axis_*, 4 neg_*). 35-cell layer lives entirely in shared config (header+block_band, 0 lab_cram); negation is axis-independent (single 7-cell flip). Codec extension can be a **single global table**, not per-LE sigcache. Data: `results/canon_cells_phase2_summary.json`. Tools: `scripts/sigma_inv_real_tt_mining/probe_canonicalization_cells.py` (probe), `scripts/sigma_inv_real_tt_mining/analyze_canon_phase2.py` (aggregator + verdict). **Phase 3 codec wiring LANDED 2026-05-13** (commits `583baa6`+`c819a61`): `fuzz/bitstream.py` exposes `canon_axis_diff` / `canon_apply_transition` / `canon_classify_transition` + `LutCodec.write_tt(... canon_from, canon_to, neg_from, neg_to)` (legacy-default byte-identical); regression `fuzz/test_canon_cells_codec.py` 8/8. Memo `phase3_canon_cell_codec_landed_2026_05_13`. Scope still open: 2-input masks (Phase 4), N>0 invariance (Phase 5), and the lab_cram TT-frame gap (codec emits 8 ctrl cells for 0xAAAA via TT model; Quartus emits 0 lab_cram via LUT-bypass routing — closes byte-identity in Phase 4). **Pivot for build_test**: use symmetric masks (0x6996 XOR4) at X=4 src-LE, or bypass via single_le sweep for Bug #2. **Do not flash X=4 cross-LAB / src-LE builds with asymmetric masks until Phase 4 closes the lab_cram TT-frame byte-identity gap.** Y=7 flash 2026-05-11 PM triggered config-controller self-protection reset (flash budget 1/3 used); freshly-mined OUTROUTE_G15 X4Y7N0 (silicon-hostile suspect) **quarantined** 2026-05-13 to `results/quarantine/outroute_g15_X4Y7N0_silicon_reset_2026_05_11.json` — active sigcache now has 38 OUTROUTE_G15 routes; codec hard-fails on missing entry (no silent substitution). Scoping memo `sigma_inv_codec_extension_scoping_2026_05_13`; Phase 2 memo `canon_cells_phase2_global_invariant_2026_05_13`.

    Test fixture: `scripts/sigcache_validation/build_test.py`. Memos: `gamma_silicon_validation_codec_bug_2026_05_10`, `gamma_bug1_strip_fix_landed_2026_05_11`, `gamma_blockers_2_3_fixed_2026_05_11`, `gamma_y7_silicon_reset_2026_05_11`, `iob_route_hdr_skip_pivot_2026_05_11`, `sigma_inv_x4y4n0_not_a_4perm_2026_05_12`. Pitfall #14 reframe: context dependency applies in every design where both directives emit.
