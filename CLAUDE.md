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
```

## Directory Layout

- `fuzz/` — fuzzing pipeline (~96 Python modules): `config.py` (constants), `bitstream.py` (LutCodec/RouteCodec/FFCodec/CRC), `fasm2rbf.py`/`rbf2fasm.py` (FASM toolchain), `route_synth.py` (green-island synthesis), `route_signatures.py` (sig-cache backend), `chipdb_gen.py` (nextpnr chipdb), `runner.py`/`compile.py`/`analyze.py` (orchestration)
- `synth/` — open-source toolchain: `ep4ce6_map.v` + `prims.v` (Yosys techmap), `synth_ep4ce6.ys` + `synth_ep4ce6.sh` (run the `.sh` wrapper, not `.ys` directly — it envsubst's `$HOME` / `$NEORV32_ROOT` so the VHDL paths travel), `np2fasm.py` (nextpnr JSON → FASM)
- `scripts/` — one-off investigation scripts kept for reproducibility (e.g. `scripts/arith_sweep/` — Phase 1 per-width arith blob sweep harness)
- `tmp/` — **local scratch only, gitignored**. House rule: do NOT drop experimental work under `/tmp/`; use this dir instead. The moment a script is cited from docs or memory, move it out of `tmp/` into `scripts/` (or another proper location) so it survives reboots and is reachable from a clone.
- `jailbreak/` — CE10 fitter probes (CE6≡CE10 same die, +65% fabric unlocked)
- `results/` — `rbf/` (~2500 files), `route_cells_full.json` (13,487 sig-cache), `r4_iindex_table.json`, `ep4ce6_bitdb.sqlite`, `fingerprint_*.json` (15 green islands)

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
| `LutCodec` | `write_tt(base_rbf, mask)` → RBF, `read_tt(rbf, zero)` | **XOR-delta, not absolute!** `mask = target ^ base_tt` |
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
| `GCLK` | `GCLK` | OK — 17 position-independent cells |
| `DFF` | `X10Y10N0.DFF` | **NO-OP** — DFF is silicon default (no CRAM cells) |
| `BIT` | `BIT offset bp` | OK — raw cell flip |
| `SRC` | `SRC X10Y10` | OK — per-source overhead |
| `LUT_ARITH` | `X4Y18N0.LUT_ARITH = 0x0000` | OK — v4 universal blob (100 SETs + 4 CLEARs) for 8-LE half-LAB chains at ANY LAB. Other widths see per-width table below. |
| `IOB_IN`/`IOB_OUT` | `IOB_IN PIN_M16` / `IOB_OUT PIN_F15` | OK single-axis (44/44 bit-perfect) — XOR delta from `iob_in_E15.rbf` baseline (K=E15, LED=G15). Cross-axis combos leak ~50-60 joint-placement bytes; needs 2D K×LED sweep to close. |
| `DFF.ARST/ENA` | — | **DISABLED** — header-band noise unresolved |
| `M9K.INIT` | — | **NOT YET** — anchor table incomplete |

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

Sig-cache (`route_cells_full.json`, 13,762 entries) **short-circuits all formula paths** for production routing. Formulas are fallback only.

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

## Phase 5.3 — Open-Source Toolchain (PARTIALLY OPEN)

Target: `Verilog → Yosys → nextpnr-generic → np2fasm → fasm2rbf → openFPGALoader`

**Completed**: chipdb_gen.py (8,241 bels, 59,611 wires, 1.38M pips), techmap (LUT4+DFF), np2fasm.py (logical connectivity → sig-cache lookup; emits `IOB_IN`/`IOB_OUT` per direction of each placed GENERIC_IOB cell), `fasm2rbf` GCLK/DFF/LUT/ROUTE/SRC/BIT directives.

**Status**: pipeline runs end-to-end on combinational designs. Arithmetic designs work via the `LUT_ARITH` FASM directive (see Phase 5.4), **hardware-verified on AX301** (2026-04-13). Full Yosys→prepack→np2fasm→fasm2rbf path produces CRC-valid RBFs; the identity_led + arith-overlay path achieves zero data-region diffs vs Quartus.

**Real fixes earned chasing the M5 counter (2026-04-11)**:
- LutCodec high-density LAB workaround (`predict_sram(0xFFFF)` → 16 true TT cells, XOR-cancels LAB-shared cells from sloppy minterm calibration). Required when >2 LEs share a LAB. See `lutcodec_high_density_lab_bug.md`.
- Sig-cache mining template pitfall: must use `gen_two_luts_single_input_clocked` from `verilog_gen.py` + `gen_qsf_ce10` from `plan_d_prime_factory.py`. Custom templates produce ~1000-cell bloated entries or wrong-port routing. See `sigcache_mining_template_pitfall.md`.
- Per-LAB CLK SET must run AFTER the LUT phase reset (some clock cells overlap with LUT TT cells in high-density LABs).
- Post-bitgen, strip 1-3 LI cells in non-design LABs (sig-cache mining infrastructure leakage from baseline lut1/lut2 LABs).
- 160 cleanly re-mined (4,18)/(4,19) inter-LE pair entries now in `route_cells_full.json`.
- Working multi-LE-per-LAB build template: `tmp/m5_counter/build_counter_sigcache.py` (workspace from the M5 session, regenerate locally if needed).

**M5 counter blocker (NOT a codec bug — a missing primitive)**: Quartus compiles a 24-bit counter to 367 cells in CRAM cols 47-48 using **LE carry-chain wires** (`cout→cin` direct, 1 LE per bit). nextpnr-generic does not model these wires, so Yosys emulates `+1` as a 4-LE-per-bit ripple producing 24 self-feedback routes (LE → same LE.dataX). Self-feedback routes cannot be cleanly mined: the two-LUT pair template can't represent `src==dst`, and the diff-based selfloop_factory gets refit by Quartus producing 110-754-cell noise. Working ground truth: `tmp/m5_counter/quartus_ref/counter_top.rbf` (Quartus build, blinks on AX301; rebuild under the repo-local scratch dir). Diagnostic memory: `m5_counter_root_cause_carry_chain.md`.

**Not yet implemented**: GCLK clock-pin routing — partially mapped. GCLK source encoding is **per-pin one-hot** (no universal spine): each dedicated CLK pin has its own cell set that must be flipped to activate it as a global clock source. Triangulation across E1/R8/N1 (2026-04-14) gave 0-cell all-pair intersection; cross-pin forced-vs-auto overlap is 0 cells. Mapped so far: `PIN_E1` → 3 cells at frames 34-35, `PIN_R8` → 5 cells at frames 58/61/834/837/846. `PIN_N1`-specific cells identified (7 cells) but not yet recorded as a per-pin activate set. Probes: `fuzz/clk_force_gclk_probe.py`, `fuzz/clk_pin_gclk_idx_probe.py`, `fuzz/clk_pin_triangulate_probe.py`, `fuzz/clk_iob_subtract_probe.py`, `fuzz/clk_cross_pin_spine_check.py`. FASM directive split (per-pin `GCLK_PIN_X` activation + per-LAB CLK_SEL) not yet wired — currently the bitgen still depends on `nv_zero_global.rbf` baseline. Carry chain (Phase 5.4) and 2D IOB K×LED sweep also pending. The legacy 17-cell `GCLK` directive is **local-clock distribution**, not GCLK source — Quartus' Auto Global Clock heuristic refuses to promote tiny test designs.

**Partially landed (2026-04-14)**: IOB FASM cell map — `IOB_IN PIN_X` / `IOB_OUT PIN_X` directives reproduce all 44 single-axis ground-truth RBFs bit-perfect via XOR delta from `iob_in_E15.rbf` baseline. Mining: `fuzz/iob_sweep.py` (parallel Quartus builds) + `fuzz/iob_analyze.py` (pair-delta vs anchor) → `results/iob_cell_map.json`. Validator: `fuzz/iob_validate.py`. `np2fasm` passes each placed GENERIC_IOB through as `IOB_IN`/`IOB_OUT` using the BEL's fabric-facing port direction (unit-tested in `fuzz/test_np2fasm_iob.py`, 6/6).

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

**Remaining gaps**: IOB FASM cell map, GCLK cells may conflict with some bases (17 cells mined from nv_zero; Quartus counter doesn't use all of them).

**nextpnr**: `source $HOME/opt/oss-cad-suite/environment` first; `--router router2` (router1 can't multi-hop); `--pre-pack` not `--run`.

## Tools

- **Quartus 21.1 Lite**: `$HOME/intelFPGA_lite/21.1/quartus/bin/`
- **RBF generation**: `quartus_cpf -c -o bitstream_compression=off` (**NEVER** `sof2rbf.py`)
- **Programming**: `$HOME/see_neorv32_run_linux/tools/openFPGALoader/build/openFPGALoader -c usb-blaster`
- **Hardware**: AX301 board, EP4CE6F17C8, USB-Blaster JTAG
- **Pin map**: KEY1=E15, KEY2=E16, KEY3=M16, KEY4=M15, LED0=G15 (active-high; keys active-low)

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
