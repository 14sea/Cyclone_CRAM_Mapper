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
```

## Directory Layout

- `fuzz/` — fuzzing pipeline (~96 Python modules): `config.py` (constants), `bitstream.py` (LutCodec/RouteCodec/FFCodec/CRC), `fasm2rbf.py`/`rbf2fasm.py` (FASM toolchain), `route_synth.py` (green-island synthesis), `route_signatures.py` (sig-cache backend), `chipdb_gen.py` (nextpnr chipdb), `runner.py`/`compile.py`/`analyze.py` (orchestration)
- `synth/` — open-source toolchain: `ep4ce6_map.v` + `prims.v` (Yosys techmap), `synth_ep4ce6.ys` + `synth_ep4ce6.sh` (run the `.sh` wrapper — it envsubst's `$HOME` / `$NEORV32_ROOT`), `np2fasm.py` (nextpnr JSON → FASM)
- `scripts/` — one-off investigation scripts kept for reproducibility
- `tmp/` — **local scratch only, gitignored**. Do NOT use `/tmp/`; use this dir instead. Promote scripts out of `tmp/` to `scripts/` the moment they're cited from docs or memory.
- `jailbreak/` — CE10 fitter probes (CE6≡CE10 same die, +65% fabric unlocked)
- `results/` — `rbf/` (~2500 files), `route_cells_full.json` (sig-cache; gitignored, regenerate via `route_signatures.build()`; legacy fallback `route_cells.json` = 1,725 entries), `r4_iindex_table.json`, `ep4ce6_bitdb.sqlite`, `fingerprint_*.json`, `sigma_inv_fb8_groups.json` (2,112-entry σ⁻¹ 3-key table), `nv_baseline_pack.json`, `m9k_mode_bits.json`

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
| `LutCodec` | `write_tt(base_rbf, mask)` → RBF, `read_tt(rbf, zero)`, `from_cram_model(x,y,n)` | **XOR-delta, not absolute!** `mask = target ^ base_tt`. `from_cram_model` uses σ⁻¹ permutation lookup keyed by `(foff, fb8, group)` — 2112 entries, 5-level fallback: exact 3-key → nearest-foff 3-key → exact 2-key → nearest 2-key → identity. Data: `results/sigma_inv_fb8_groups.json`. Residual: fb8=7 × group=4 is silicon-geometry blocked (X=8 has no LAB at Y≥12). See memory `sigma_inv_3key_discovery.md`. |
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
| `GCLK_PIN` | `GCLK_PIN PIN_E1` | OK — per-pin XOR activate set. **12 pins mined** on F17 (E1/R8/N1 + 9 dedicated clock pins). Mining: `fuzz/clk_pin_autoforce_probe.py --pin {PIN}`. Data: `results/clk_cross_pin_spine_check.json`. See memory `clk_pins_full_f17_coverage.md`. |
| `LAB_CLK_SEL` | `LAB_CLK_SEL X10Y4` | OK — per-LAB CLK_SEL N-invariant layer (XOR). 13 LABs mined. Re-mine: `fuzz/clk_lab_sel_probe.py --lab X,Y`. |
| `LAB_CLK_SEL_LE` | `LAB_CLK_SEL_LE X10Y4N0` | OK — per-LE CLK_SEL layer (XOR, disjoint from `LAB_CLK_SEL`). **Functionally required** (N-invariant alone = LED-always-off). N∈{0,2,4,6,8} mined for all 14 LABs. Data: `results/clk_lab_sel_per_le.json`. Extend via `clk_lab_sel_n2_batch.py` after editing `N_SLOTS` in `clk_lab_sel_probe.py`. |
| `DFF` | `X10Y10N0.DFF` | **NO-OP** — DFF is silicon default (no CRAM cells) |
| `BIT` | `BIT offset bp` | OK — raw cell flip |
| `SRC` | `SRC X10Y10` | OK — per-source overhead |
| `LUT_ARITH` | `X4Y18N0.LUT_ARITH = 0x0000` | OK — v4 position-independent blob (100 SETs + 4 CLEARs) for 8-LE half-LAB chains at ANY LAB. Per-width table at `results/arith_blockband_by_width.json` (widths 2..16). |
| `LUT_ARITH_MULTI_LAB` | `LUT_ARITH_MULTI_LAB WIDTH=17` | OK codec — widths 17..32 multi-LAB chain activation. np2fasm consumer NOT wired (Yosys `$alu` techmap caps at single-LAB); multi-LAB position-independence not proven. See memory `arith_width_17_32_landed.md`. |
| `IOB_IN`/`IOB_OUT` | `IOB_IN PIN_M16` / `IOB_OUT PIN_F15` | OK single-axis (44/44 bit-perfect) — XOR delta from `iob_in_E15.rbf` baseline. For G15-output designs use `IOB_PAD_NV` + `OUTROUTE_G15` instead. |
| `IOB_ROUTE` | `IOB_ROUTE PIN_E16 -> X16Y4N0.dataa` | OK — pin→LE-port sig lookup. **Two apply-paths**: default live path (padnv_cells > absolute_cells, dedup + `off<5282` hdr-skip) for IOB_PAD_NV-derived designs; legacy path (`bitgen(legacy_iob_route=True)` — single_le_cells > stale > absolute, pure XOR, no dedup) for simple_led single-LE designs. **np2fasm pragma channel**: `np2fasm --legacy-iob-route` emits `# fasm2rbf: legacy_iob_route=1`; callers parse with `fasm2rbf.parse_pragmas(text)` and forward to `bitgen(**pragmas)`. See memory `fix_a_legacy_iob_route_flag_landed.md`, `fix_b_single_le_remine_landed.md`, `np2fasm_legacy_iob_route_pragma.md`. Re-derive single_le: `python3 scripts/iob_slice_mining/sweep_single_le.py --orphans-only --include-known --skip-build`. |
| `IOB_BASELINE_NV` | `IOB_BASELINE_NV` | OK — 132-cell hdr-band bridge. **SUPERSEDED by IOB_PAD_NV** for G15-output designs. |
| `IOB_PAD_NV` | `IOB_PAD_NV` | OK — 241-cell IOB pad infra (E16+M16 input + G15 output), direct delta from `nv_zero_global`. Data: `results/output_route_nv_mining.json` → `iob_pad_cells`. np2fasm emits automatically when SLICE→G15 output routing detected. |
| `OUTROUTE_G15` | `OUTROUTE_G15 X10Y10N0` | OK — position-specific SLICE→G15 output routing (38-67 cells). 33 positions mined. Data: `results/output_route_sigcache.json`. |
| `IOB_CLK_INPUT` | `IOB_CLK_INPUT PIN_E1` | OK for 12 pins on F17 — hdr delta activating a clock-bank pin as GCLK driver. Extensible via `scripts/iob_slice_mining/compute_clk_pin_hdr.py --build --pin {PIN}` → `results/iob_clk_pin_hdr_cells.json`. |
| `NV_BASELINE_PACK` | `NV_BASELINE_PACK` | OK — meta directive (21 640 XOR cells) that reproduces `nv_zero_global.rbf` on top of `make_pure_zero_rbf()` byte-for-byte. Subs: `IOB_BANK_DEFAULT_PACK`, `LOCAL_CLK_E1_BASELINE`, `LOCAL_CLK_PATH_A`, `LAB_LOCAL_CLK X{x}`, `M9K_BLOCK_DEFAULT_PACK`, `MULT_BLOCK_DEFAULT_PACK`, `NV_BLOCK_COL_INFRA`. Data: `results/nv_baseline_pack.json`. np2fasm emits with `--base pure`. HW flash equivalence not yet confirmed — keep `nv_zero_global.rbf` as HW-default. |
| `DFF.ARST/ENA` | — | **DISABLED** — header-band noise unresolved |
| `M9K.INIT_{w}x{d}` | `X15Y10N0.INIT_9x512 = 0x...` | **9×512** (33 sites) and **18×512** (5 sites) calibrated; codec `fuzz/m9k_init_basis.write_init`. np2fasm emits via `_emit_m9k_init`. Byte-identical vs Quartus at X15_Y10_N0 18x512 via `scripts/m9k_e2e_smoke.py`. **SDP 4×2048** (bit 0 only): dedicated `write_init_sdp4x2048` / `read_init_sdp4x2048` codec — formula independent (8 words/frame, `_SDP_4X2048_BIF` byte table, bp=4); X15_Y10_N0 silicon-validated 2026-04-27 via stripe-pattern flash. The 4×2048 entries in `M9K_INIT_ANCHORS` use the wrong (extrapolated) formula — flagged in-source with ⚠️, do NOT use `write_init` for 4×2048. **9×1024 / 36×256**: extrapolated anchors flagged with ⚠️ — non-zero INIT needs per-depth calibration. |
| `M9K_MODE_{w}x{d}[_template]` | `X15Y10N0.M9K_MODE_9x512_quartus_gold` | ⚠️ **Codec emission silicon-broken** for the `_quartus_gold*` + `--base nv` path (production np2fasm). Bucket mined relative to `matched_baseline` but applied as XOR onto `nv_zero_global` → ~85% bit inversion + 3-variant intersection over-filters silicon-required cells. Every codec-emission flash silicon-resets. Quartus-gold flashes still work (5-width SP sweep, SDP/TDP triad, per-site SP, (8,64) cache 5/5). See memory `m9k_mode_codec_silicon_broken_2026_04_25` + `m9k_mode_d2_falsified_2026_04_26` (D2 single-variant fix falsified across 5 silicon probes). The separate `_inferred_goldintersect` + `--base pure` path remains HW-validated (w=9/w=18). `quartus_gold` buckets mined via `scripts/m9k_mode_quartus_gold_mine.py` (single) or `scripts/m9k_mode_quartus_gold_batch.py --neorv32` (sweep). Per-(w,d,site) = intersection of 3 Quartus altsyncram variants vs matched no-M9K baseline, block-band only. **np2fasm gate** (`_M9K_MODE_FUNCTIONAL_VALIDATED_{SP,SDP,TDP}` × lazy-loaded site set from `results/m9k_mode_bits.json`) covers all 27 NEORV32 M9K sites + X15 Y10..Y14 SP (8,64) cache — gates allow emission, but silicon validity requires the fix paths in the silicon-broken memo (D3 alone insufficient — needs companion-infra directives). SDP/TDP modes via `--mode sdp|tdp`; `np2fasm._emit_m9k_mode` dispatches on techmap MODE param. Site-specificity is real — reusing a bucket across sites leaks ~20+ wrong cells. Full history: memory `m9k_mode_*` entries. |

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

**Completed**: `chipdb_gen.py` (15,331 bels, 87,878 wires, 2.12M pips), techmap (LUT4+DFF), `np2fasm.py` (emits IOB_PAD_NV / IOB_ROUTE / OUTROUTE_G15 / GCLK_PIN / LAB_CLK_SEL / LAB_CLK_SEL_LE / IOB_CLK_INPUT / M9K.INIT / M9K_MODE), `fasm2rbf` all directives.

**HW-validated end-to-end designs**: registered AND gate at X16Y4N0 (0 fabric diffs vs Quartus gold), 5-bit carry chain counter at LAB(16,4), two-LAB cross-LAB AND→DFF (BIT reconstruction). Details in memory `pipeline_test_e2e_status.md`, `two_lab_gold_validated.md`.

**nextpnr invocation**: `source $HOME/opt/oss-cad-suite/environment` first; `--router router2` (router1 can't multi-hop); `--pre-pack` not `--run`.

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
