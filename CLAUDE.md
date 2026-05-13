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
| `LutCodec` | `write_tt(base_rbf, mask, *, canon_from='a', canon_to=None, neg_from=False, neg_to=None, bypass=False)` → RBF, `read_tt(rbf, zero, *, bypass_aware=False)`, `from_cram_model(x,y,n)` | **XOR-delta, not absolute** (`mask = target ^ base_tt`). σ⁻¹ permutation lookup via `(foff, fb8, group)` 3-key, 5-level fallback (`results/sigma_inv_fb8_groups.json`, 2112 entries). σ⁻¹ valid for symmetric masks at LE_0; **broken for asymmetric masks at X=4 LE_0** — see Pitfall #16. Phase 3 canon-cell layer landed 2026-05-13 (35-cell global table, shared config, 0 lab_cram) + Phase 4 `bypass=True` skips SRAM emit for 8 `BYPASS_1INPUT_MASKS` ∪ {0x0000, 0xFFFF}. Helpers: `lut_input_dependence`, `is_bypass_mask`, `canon_axis_diff`, `canon_apply_transition`, `canon_classify_transition`. Silicon-validated 2026-05-13 via both direct `canon_apply_transition` (canon_na, mask=0x5555) and `bitgen(... bypass_aware=True)` (canon_b, mask=0xCCCC). Legacy defaults byte-identical. Memos: `phase3_canon_cell_codec_landed_2026_05_13`, `phase4_bypass_tt_model_2026_05_13`, `p1_bypass_aware_silicon_validated_2026_05_13`. |
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
| `LUT_ARITH` | `X4Y18N0.LUT_ARITH = 0x0000` | v4 position-independent blob (100 SETs + 4 CLEARs); per-width table `results/arith_blockband_by_width.json` (widths 2..16). |
| `LUT_ARITH_MULTI_LAB` | `LUT_ARITH_MULTI_LAB WIDTH=17` | Widths 17..32 multi-LAB chain. Silicon-validated W=17/W=23 at LAB(4,18)+(4,17). Each entry has `set` (XOR) + `clear` (AND-clear, dedup-override). np2fasm not wired (Yosys `$alu` caps at single-LAB). Memory: `multi_lab_carry_silicon_validated_2026_05_03`. |
| `IOB_IN`/`IOB_OUT` | `IOB_IN PIN_M16` | Single-axis 44/44 bit-perfect. For G15-output use `IOB_PAD_NV` + `OUTROUTE_G15`. |
| `IOB_ROUTE` | `IOB_ROUTE PIN_E16 -> X16Y4N0.dataa` | Two apply-paths: default live (padnv_cells > absolute_cells; absolute_cells get dedup + `off<5282` hdr-skip, padnv_cells skip both); legacy (`bitgen(legacy_iob_route=True)` for simple_led single-LE). np2fasm pragma `# fasm2rbf: legacy_iob_route=1`. Re-derive padnv: `mine_padnv_x4y4n0.py` (verify pending σ⁻¹ — Pitfall #16). Memory: `iob_route_hdr_skip_pivot_2026_05_11`. |
| `IOB_BASELINE_NV` | `IOB_BASELINE_NV` | 129-cell hdr-band bridge. SUPERSEDED by IOB_PAD_NV. |
| `IOB_PAD_NV` | `IOB_PAD_NV` | 139-cell E16+M16-in + G15-out infra (delta vs nv_zero_global). + 74-cell `iob_pad_arith_ext_cells` when `LUT_ARITH*` present (carry G15 designs, W=17/W=23 silicon-validated). np2fasm auto-emits for SLICE→G15. Data: `results/output_route_nv_mining.json`. |
| `OUTROUTE_G15` | `OUTROUTE_G15 X10Y10N0` | Position-specific SLICE→G15 (38-67 cells, 33 positions mined). Data: `results/output_route_sigcache.json`. |
| `IOB_CLK_INPUT` | `IOB_CLK_INPUT PIN_E1` | 12 pins F17. Extensible: `scripts/iob_slice_mining/compute_clk_pin_hdr.py --build --pin X`. **Calibrated vs IOB_BASELINE_NV** — overlap with IOB_PAD_NV double-flips; PIN_E1 corrected by IOB_RESERVE_PIN_M16 Group B; other 11 pins latent mismatch (runtime warning emitted). Audit: `audit_clk_pin_pad_nv_overlap.py`. |
| `IOB_RESERVE_PIN_M16` | `IOB_RESERVE_PIN_M16` | 66-cell XOR for Quartus default RESERVE_ALL_UNUSED=tri-state+pull-up when M16 unused. Groups A/B/C hdr (24+9+9) + D fabric (24). np2fasm auto-emit: `use_pad_nv AND PIN_M16∉IOBs AND not has_carry`. Memory: `probe2_open_software_bisect_2026_05_03`. |
| `X33Y4_PROBE2_INFRA` (auto) | implicit shim | Auto-applied at 1-LE @ SLICE_X33_Y4_N4. 37-cell override (33 ADD + 4 OVER-CANCEL). Disjoint from cl_and 2-LE shim. Data: `results/x33y4_probe2_infra.json` + decomposition sidecar. Memory: `probe2_open_software_bisect_2026_05_03`. |
| `NV_BASELINE_PACK` | `NV_BASELINE_PACK` | Meta directive (21,640 XOR cells) reproducing `nv_zero_global.rbf` on top of `make_pure_zero_rbf()`. np2fasm `--base pure`. HW equivalence not confirmed — keep `nv_zero_global.rbf` as default. |
| `DFF.ARST/ENA` | — | DISABLED — header-band noise unresolved. |
| `M9K.INIT_{w}x{d}` | `X15Y10N0.INIT_9x512 = ...` | **9×512** (33 sites) + **18×512** (5 sites) via linear formula in `m9k_init_basis.write_init`. **SDP 4×2048 / SP 9×1024 / SP 36×256** use dedicated codecs at X15_Y10_N0 only (linear formula WRONG, flagged). SP 9×512 cross-site silicon-validated at 8 sites. Memory: `sp_9x512_cross_site_silicon_hw_validated_2026_04_28`, `sp_9x1024_36x256_codec_silicon_hw_validated_2026_04_28`. |
| `M9K_MODE_{w}x{d}[_template]` | `X15Y10N0.M9K_MODE_9x512_m9k_blink_diff_nv` | Per-site M9K mode bits. Template `_m9k_blink_diff_nv` silicon-validated (solo/blink-class). For multi-M9K NEORV32-class, use `DESIGN_BLOCK_BAND_PACK` instead. Memory: `option_3_residual_silicon_validated_2026_05_01`. |
| `DESIGN_BLOCK_BAND_PACK` | `DESIGN_BLOCK_BAND_PACK neorv32` | Silicon-validated 2026-05-01. XOR-applies full block-band cell set per-design tag. Mine: `mine_design_block_band.py --tag X --rbf X.rbf`. Tags mined: `neorv32` (417), `m9k_23_clone` (16), `arbiter_2m9k` (11), `visible_2m9k` (12). |

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

**Completed**: `chipdb_gen.py` (12,131 bels, 90,261 wires, 3.66M pips), Yosys techmap (LUT4+DFF+`$alu`→CE6_CARRY via alumacc), `np2fasm.py` (emits IOB_PAD_NV / IOB_ROUTE / OUTROUTE_G15 / GCLK_PIN / LAB_CLK_SEL{_LE} / IOB_CLK_INPUT / M9K.INIT / M9K_MODE / DESIGN_BLOCK_BAND_PACK / LUT_ARITH), `fasm2rbf` all directives.

**HW-validated**: registered AND @X16Y4N0, 5-bit carry @LAB(16,4), 2-LAB cross-LAB AND→DFF, 2-M9K visible-blink (`DESIGN_BLOCK_BAND_PACK visible_2m9k`). W=23 byte-identical zero-Quartus (`build_open23.py`, md5 905dfc85, 5.96 Hz blink). Memory: `pipeline_test_e2e_status`, `two_lab_gold_validated`, `option_3_residual_silicon_validated_2026_05_01`, `zero_quartus_arith_byte_identity_2026_05_04`.

**nextpnr**: `source $HOME/opt/oss-cad-suite/environment`, `--router router2` (router1 can't multi-hop), `--pre-pack` via chipdb guard.

**Step 3 SAFETY closure** (2026-05-02): 22→0 LI MUX UNSAFE via LI-snapshot lockdown (defeats σ⁻¹ over-claim) + `driver_single` validator mode + nojb sidecar. Memory: `step_3_substantially_closed_2026_05_02`.

**Step 4 gap (pending)**: pipeline_test/led_blink open builds flash clean but LED stuck — 494 OPEN-only OTHER (NV_BASELINE_PACK over-emit), 64 GOLD-only HEADER, 270 GOLD-only BLOCK_BAND (GCLK column distribution unmined). Memory: `path_alpha_led_blink_silicon_failed_2026_05_02`.

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
13. **Phase 3 LI MUX std_lut TT collision — FIXED 2026-05-05** (silicon-validated for LE_0 symmetric masks). Phase 3 restored 18 LI MUX cells; only 2/18 are LI MUX, the other 16 are real TT. Fix: Phase 3 builds `std_lut_tt_cells` and skips those `(off, bp)` keys in `li_locked_state`. Closure scope: LE_0 symmetric masks (0x6996/0x9669); asymmetric masks at X=4 remain broken (Pitfall #16). Regression: `fuzz/test_phase3_li_mux_lut_tt.py`. Memory: `phase3_fix_silicon_validated_2026_05_05`.
14. **Mined cross-LAB R4 sig-cache entries are context-dependent** (silicon-validated 2026-05-04). Diff-vs-nv_zero mining captures Quartus router decision; in dense runtime context (24-LE chain) chain consumes resources the mined route assumed free. Codec-level evidence does NOT prove silicon function. Memory: `d_i_silicon_two_failures_2026_05_04`.
15. **Mining script `n // 2` convention bug** (audit 2026-05-08, ext 2026-05-10). Runtime convention: `n = chipdb SLICE_N = Quartus LCCOMB N = 2 × LE_index`. Buggy scripts (`mine_intralab_route_x4y17n14_to_n16.py`, `mine_real_tt.py`, sweep_outroute_nv.py) used `loc=LCCOMB_X{x}_Y{y}_N{n//2}`. Fixed; σ⁻¹ analysis scripts use `k = n // 2` as LE_idx array index — not buggy. Audit before any new mining. Memory: `conv_bug_discovery_2026_05_08`, `gamma_x4_crosslab_batch1_2026_05_10`.
16. **γ X=4 cross-LAB — 1-input bypass CLOSED 2026-05-13; 2-input asymmetric pending P2.**
    - **Bug #1 (`df335d8`)** — IOB+CLK infra baked into ROUTE diff; double-XOR with runtime IOB_PAD_NV/LAB_CLK_SEL_LE. Fix: `scripts/sigcache_remine/strip_iob_overlap.py --apply --column X` (idempotent; re-run after `nv_sig_cache_merge.py`). 96/109 X=4 entries; same class at X=10/16/22/25/28/31.
    - **Bug #2/#3 (FIXED, `03b91c6`+`93f9cb9`)** — Phase 3 IOB_PAD_NV/OUTROUTE_G15 skip (X33Y4 exempt); padnv-bucket IOB_ROUTE hdr-skip gating. Silicon md5s preserved (W=23 `905dfc85`, probe2 `d4073d2e`, cross_lab_x33 `47ad9ed9`).
    - **σ⁻¹ canon-cell layer** — 1-input CLOSED Phase 3+4 (`583baa6`/`c819a61`/`5905643`/`b28554b`): codec `canon_axis_diff` / `canon_apply_transition` / `canon_classify_transition` + `write_tt(canon_from, canon_to, neg_from, neg_to, bypass)` + `lut_input_dependence` / `is_bypass_mask` / `BYPASS_1INPUT_MASKS`. np2fasm `--bypass-aware` + fasm2rbf `bypass_aware=True` pragma → byte-identical to Quartus `canon_*_X4Y4N0.rbf` for all 8 1-input + 2 constants. Silicon-validated canon_b (mask=0xCCCC). Phase 2 verdict: GLOBAL POSITION-INVARIANT (12 positions, shared config). Regression `fuzz/test_canon_cells_codec.py` 16/16 + `fuzz/test_bypass_byte_identity.py` 5/5; pre-commit gate. **Pending P2**: 2-input canon model (data ready: `canon_cells_X4Y4N0_2input{,_neg}.json`, multi-position mining + codec extension). **N>0 invariance (P4)** silicon spot-check pending.
    - **OUTROUTE_G15 X4Y7N0 quarantined** 2026-05-13 to `results/quarantine/` after silicon-reset; codec hard-fails on missing.
    - **Pivot guidance**: use symmetric masks (0x6996 XOR4) at X=4 src-LE until P2 lands. **Do not flash X=4 cross-LAB asymmetric until P2.**
    Test fixture: `scripts/sigcache_validation/build_test.py`. Memos: `gamma_*`, `iob_route_hdr_skip_pivot_2026_05_11`, `sigma_inv_x4y4n0_not_a_4perm_2026_05_12`, `phase3_canon_cell_codec_landed_2026_05_13`, `phase4_bypass_tt_model_2026_05_13`, `p1_bypass_aware_silicon_validated_2026_05_13`, `phase4_p1_p5_landed_2026_05_13`.
