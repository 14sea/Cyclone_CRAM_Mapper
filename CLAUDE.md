# CLAUDE.md — EP4CE6 Bitstream Reverse Engineering

## Overview

Automated black-box fuzzing pipeline for reverse-engineering the Altera Cyclone IV EP4CE6F17C8 bitstream format (.rbf). Goal: build a complete bit dictionary mapping every configuration SRAM cell, enabling open-source toolchain support.

## Quick Start

```bash
export PATH=$PATH:$HOME/intelFPGA_lite/21.1/quartus/bin
cd fuzz

# Generate baseline
python3 runner.py baseline

# Fuzz LUT truth table at a specific LE
python3 runner.py --node lut_inst lut_single 10 10 0

# Analyze results
python3 analyze.py summary
python3 analyze.py lut_table 10 10 0

# Route synth regression: 15 green-zone islands, 686/686 bit-perfect
python3 fuzz/test_green_zone_harden.py
```

## Directory Structure

```
EP4CE6/
├── fuzz/                    # Fuzzing pipeline (Python, 96 modules)
│   ├── config.py            # EP4CE6 constants, coordinates, pins
│   ├── verilog_gen.py       # Verilog generators (LUT4 primitive, FF, empty)
│   ├── qsf_gen.py           # QSF + placement constraint generator
│   ├── compile.py           # Quartus headless compilation driver
│   ├── rbf_diff.py          # Bit-level binary diff engine
│   ├── database.py          # SQLite bit mapping storage
│   ├── runner.py            # Fuzzing campaign orchestrator
│   ├── analyze.py           # Result analysis and visualization
│   ├── bitstream.py         # LutCodec, RouteCodec, CRC patcher
│   ├── route_synth.py       # Green-island route synthesis engine
│   ├── c4_mapper.py / c4_inz_sweep.py      # C4 I=0 + I≠0 address mining
│   ├── r4_mapper.py / r4_iindex_mine.py    # R4 address model + I-index sweep
│   ├── r24_mapper.py        # R24 fixed-byte model
│   ├── li_mode_*.py         # LI mode analysis (T9+T10 corpus + tree)
│   ├── test_green_zone_harden.py  # 15 islands / 686 routes bit-perfect regression
│   ├── pin_probe.py / demo_keys2leds.py / demo_y15_keys2led.py  # HW pin probe + X10/Y10 + Y15 demos
│   ├── m9k_probe_mine.py / m9k_probe_clean.py  # Phase 3.27 M9K CRAM probes
│   ├── r4_iindex_mine.py    # mines results/r4_iindex_table.json (route_synth dep)
│   ├── cross_device_diff.py # EP4CE6 ≡ EP4CE10 proof
│   ├── fasm2rbf.py / rbf2fasm.py          # Phase 4 FASM writer + reverse tool
│   ├── route_signatures.py / route_decompose.py  # sig backend + set-cover
│   ├── source_overhead_build.py           # per-source overhead vs baseline
│   ├── test_fasm_*.py / test_cross_source.py / test_multiroute_decompose.py
│   └── bitstream-re.SKILL.md # Methodology playbook (also at .claude/skills/)
├── jailbreak/               # CE10 fitter probes (X=32/33, Y=15 dead-cell scans)
├── results/
│   ├── rbf/                 # Collected .rbf files (~2,500 files)
│   ├── fingerprint_{sx}_{sy}.json  # Green-zone island corpora (15)
│   ├── r4_iindex_table.json # 942-entry route_synth I-index hint table
│   ├── ep4ce6_bitdb.sqlite  # Bit mapping database
│   └── FINDINGS.md          # Detailed findings report
├── templates/               # Verilog templates (unused, generated in-memory)
└── work/                    # Quartus temporary build directory
```

## Key Findings

### RBF Format
- Fixed size: **368,011 bytes** (all EP4CE6 designs)
- Preamble: 32 bytes 0xFF | Config: 367,920 bytes | Postamble: 59 bytes 0xFF

### CRAM Structure (verified 376/376 positions)
- **Standard LAB column step: 7,350 bytes (0x1CB6)**
- 28 LAB columns mapped post-jailbreak; true non-LAB columns are X=15,27 (M9K) and X=20 (mult) only
- **Pair spacing: 210 bytes** (uniform across ALL columns)
- **Ctrl→Data offset: 48 bytes** (uniform)
- Y-address formula: `slot = (Y-2)%3, group = (Y-2)//3, ctrl_bit = 7-group-(1 if slot>0 else 0)`

### LUT Truth Table
- Encoded via **XOR-linear algebra**: any 16-bit mask = XOR of single-bit patterns
- Each LE: 64-96 SRAM bits across ~1,518 byte span
- 8 paired entries per LE: ctrl bytes (unique per Y) + data bytes (shared across Y rows)
- Verified with masks 0xFFFF, 0x8888, 0x6996

### DFF Configuration
- 4 FF pairs per LE (same ctrl+data structure as LUT TT)
- Split into 2 regions: below and above LUT TT in CRAM column
- Adding FF changes ~362 bits total (~90% routing, ~10% LE config)
- **LCFF placement rejected** by Quartus Lite — FF auto-placed near output pin

### FF ctrl bits — three-layer model (2026-04-08 re-mine)
- **Layer 1 (device-global, DONE — but header-band cells are suspect)**: 61 arst + 61 ena absolute-offset bits mined via `fuzz/ff_remine.py` (8 SEEDs) ∩ `fuzz/ff_remine_r2.py` (10 Q pins), CRC-normalized. Stored in `results/ff_remine_final.json`, loaded by `FFCodec` at import. arst ∩ ena = 48 "any-FF-with-ctrl" enables; 13 mode-specific per side. **Caveat**: most cells sit in the header band (off<5282) around byte 44 + 73-74 + 710-729 + 1074-1081, which Phase 5.0's 5-seed null test (`fuzz/mult_header_noise.py`) proved has a 4-5 bit per-SEED noise floor shared across FF, M9K, and DSPMULT writers. Re-audit with CRAM-only filter (off≥5282) is pending; in the meantime the FASM `DFF.ARST`/`DFF.ENA` directives remain disabled.
- **Layer 2 (per-LE mode, INVESTIGATED NEGATIVE 2026-04-08)**: byte 73 showed a per-(X,N) bit pattern under forced-placement mining at Y=4 and looked promising as a 2D header-band signal. Companion sweep at Y=10 (`fuzz/ff_y10_sweep.py`, 448 placements) joint-solved against Y=4 and found **only 7/448 (X,N) pairs have matching byte-73 bit sets** — essentially noise floor. Layer 2 is either 3D (X,Y,N) or still fitter-noise dominated at header granularity; the "layer 2 in byte 73" model is NOT a 2D lookup. Snapshots frozen at `results/ff_y4_sweep.json` / `ff_y10_sweep.json` for future work. See `memory/ff_byte73_y_dependent.md`.
- **Layer 3 (per-LE FF presence)**: partly already in LutCodec minterm cells.
- Fitter-noise wall from earlier session is specific to loaded designs with routing competition — trivial D FF base-vs-base diff is 0 bytes across 8 seeds.
- Old `_FF_ARST_CELLS` / `_FF_ENA_CELLS` column-relative tables are **deprecated** (94-100% CRC byte artifacts) but kept as stubs for read-path structure.
- `FFCodec.write_arst` / `write_ena` now flip the 61 absolute offsets; `read_arst_active` / `read_ena_active` return bool against a 50% threshold. FASM `DFF.ARST` / `DFF.ENA` directives remain **disabled** (FasmError) pending layer 2.

### Routing Matrix (Phase 3 — In Progress)
- **Fully deterministic** routing with MINIMUM optimization level
- **STA routing extraction**: `report_timing -show_routing` gives exact wire names per path
- Wire naming: `{TYPE}_X{x}_Y{y}_N{n}_I{index}` (C4, R4, C16, R24, LOCAL_INTERCONNECT, LE_BUFFER)
- 980 routing paths collected (SQLite), ~2,500 RBFs across multi-source corpora (15 green-zone source LABs)
- Column routing: dy=1 direct link, dy=2-4 1×C4, dy=5-8 2×C4, dy=9+ 3×C4

### C4 Switch CRAM Address Model
**I=0 (VERIFIED — 63 wires, 0 false predictions):**
```python
group = (y - 2) // 3
slot = (y - 2) % 3
byte_offset = LAB_CRAM_END(x) + SLOT_BASE[slot] + 3 * group
bit_position = (6 - group) if slot == 2 else (7 - group)
SLOT_BASE = {0: 2405, 1: 2475, 2: 2338}
```
- Universal formula across all 22 LAB columns
- Applies to C4_X{x}_Y{y}_N0_I0 where x ∈ LAB_X

**I≠0 (per-(X,I) fixed-byte lookup — 44 mappings):**
- C4 I≠0 uses **fixed byte offsets** (like R24) — byte is the same for all Y, only bp varies
- Pair/position within column **varies per column** — no universal formula
- 44 per-(X,I) mappings found via baseline-diff (`c4_mapper.py` + `c4_inz_sweep.py`, 2026-04-06..07):
  - 25 original + 19 from c4_inz_sweep 2026-04-07 batch (I=1 at X=3,10,11,13,21,24,28; I=10 at X=16,21,24; I=12 at X=7,11,12,16,17,21,24,29)
- I=3 and I=12 **share the same byte** at X=22 and X=25 (indistinguishable)
- pos is always 184 or 185 (data byte positions within 210-byte period)
- Non-LAB columns (X=9,15,30) have large pair numbers (58-382) due to wider CRAM
- RouteCodec reads both I=0 (formula) and I≠0 (lookup) in read_c4()

### R4 Switch CRAM Address Model (24 of 37 I-indices mapped — table unreliable for synthesis)
```python
# prev_lab_x = largest LAB_X value < wx (works for non-LAB wire X too)
prev_col_start = COLUMN_BASE[prev_lab_x] - 136
group = (y - 2) // 3
slot = (y - 2) % 3

# Slot-dependent address formulas:
if slot == 0:
    byte = prev_col_start + R4_BASE + 66 + 3*group + (1 if group > 0 else 0)
    bp = 7 - group
elif slot == 1:
    byte = prev_col_start + R4_BASE + (-70) + 3*group
    bp = 6 - group
else:  # slot == 2
    byte = prev_col_start + R4_BASE + 3*group
    bp = 6 - group

# R4_BASE_PREV lookup (pair1, pair2) — ALL in PREV column:
R4_BASE_PREV = {
    0: (3423, 3842),   # delta=419, verified X12,X19,X31
    1: (3431, 3850),   # delta=419, verified X4,X18,X23
    2: (3431, 3851),   # delta=420, verified prev=X4,X6,X10,X24,X28
    # I=6 REMOVED 2026-04-08 (propagation error from I=8, zero independent evidence)
    8:  (3612, 3822),   # delta=210, VALIDATED 83.3% (10/12) via fingerprint recheck 2026-04-08
    4: (3423, 3842),   # delta=419, verified X9,X14,X29 (same BASE as I=0)
    7: (3414, 3835),   # delta=421, verified prev=X22 (same BASE as I=10)
   10: (3414, 3835),   # delta=421, verified X13,X18,X25
   14: (3191, 3191),   # pair2 TBD, pair1 verified at 3 Y positions
   15: (3577, 3786),   # delta=209, verified prev=X12,X16,X24
   17: (2802, 3223),   # delta=421, verified prev=X6,X13,X17,X21,X25 (58%)
   18: (4057, 4267),   # delta=210, verified X4,X7
   20: (2791, 3001),   # delta=210, verified prev=X6,X11 (40%)
   22: (2783, 2993),   # delta=210, verified prev=X7
   25: (2762, 2972),   # delta=210, verified X4,X8
}
```
- **Slot 1 bp = 6-group** (NOT 7-group) — critical fix, 0%→78%
- **Slot 0 offset = 66** (not 67), with +1 for group>0
- **ALL mapped I-indices use PREV column** (original "OWN column" hypothesis disproved)
- R4 wires exist at non-LAB X coordinates (X=5,9,14,15,20,27,30,32,33) — 31% of all R4 wires
- **Sub-region model for 2× columns**: columns ≥14700 bytes split into two 7350-byte halves; right-side wires use BASE+7350
- I=3,6,19,21,23,27 stored in **non-LAB CRAM** (M9K/DSP blocks)
- **RouteCodec**: read/write for C4, R4, R24, LOCAL_INTERCONNECT, apply_routing()
- Huge columns (X13=76230, X26=68880) need M9K/DSP sub-region mapping
- 37 unique R4 I-indices observed in STA data; **24 mapped, 13 unmapped** (5,6,9,24,28,29,30,31,32,33,104,116,125 — all blocked on insufficient route corpus, not mining method)
- **I=6 removed 2026-04-08**: Option-1 fingerprint recheck proved the `(3612,3822)` base was blindly propagated from I=8 during 2026-04-06 mining; 15 green-zone sources don't route through any I=6 wire, so no independent evidence exists. I=8 validated at 83.3% (10/12) and kept. See `memory/r4_i6_i8_base_collision.md`.
- **Table re-audit via `r4_remine.py` (2026-04-08, reversal)**: an earlier same-day audit using per_route_delta (differential) flagged 11/16 entries SUSPECT and called the formula "dead code for synthesis". `fuzz/r4_remine.py` re-ran the audit against `route_cells.json` absolute cell sets (942-route STA corpus, zero differential bias) and **reversed the verdict for at least 8 entries**: I=0 85%, I=1 80%, I=2 75%, I=4 86%, I=7 97%, I=10 97%, I=13 79%, I=15 79%, I=16 83%, I=17 61%, I=18 87%, I=20 94%. **The R4 table is healthy at 60-97% for most LAB-CRAM entries** — the "dead code" label was a methodology artifact of the differential audit. Confirmed problem entries left: I=12 (29% n=210), I=14 ((3191,3191) obviously broken), I=6/I=8 (both 6.67%, non-LAB CRAM needing a different column model). I=6/I=8 Option-1 vs STA result still contradicts (83% vs 6.67%) — unresolved. See `memory/r4_base_prev_audit_2026_04_08.md`. The formula is still unused by `route_synth` because the signature backend short-circuits before it gets called, not because it's broken.
- I=23 and I=26 added 2026-04-07 via `r4_mapper2.py`; 15-island green-zone harden showed no regression
- 980 routing paths collected, parallel compilation at ~4s/target

### R24 Switch CRAM Address Model (I=0 mapped — 66% pair-diff accuracy)
```python
# R24 uses FIXED byte offsets — NO slot/group byte adjustment
# Only bp changes with Y (same formula as C4/R4)
prev_col_start = COLUMN_BASE[prev_lab_x] - 136
group = (y - 2) // 3
slot = (y - 2) % 3
bp = (6 - group) if slot == 2 else (7 - group)

# Fixed offsets from col_start:
R24_I0_OFFSETS = [3124, 2705]  # primary, secondary (delta=419)
byte = prev_col_start + offset  # no +3*group or slot adjustment!
```
- R24 switches in **PREV LAB column** (same as R4)
- **No slot/group byte offset** — simpler than R4/C4 (only bp varies with Y)
- Multiple Y values sharing the same bp produce ambiguous reads
- Primary offset: rel=3124 (pair 14, pos 184), 5-6 wx columns verified
- Secondary offset: rel=2705 (pair 12, pos 185), delta=419
- 7 unique R24 I-indices observed; only I=0 (73% of wires) mapped

### LOCAL_INTERCONNECT CRAM Address Model (VERIFIED — 70% cross-validation, 22 columns)
```python
# LOCAL_INTERCONNECT_X{lx}_Y{ly}_N{ln}_I{li}
col_start = COLUMN_BASE[lx] - 136     # SELF column (not prev!)
group = (ly - 2) // 3
slot = (ly - 2) % 3
byte = col_start + 70 + pair * 210 + SLOT_OFFSET[slot] + 3 * group
bp = (6 - group) if slot == 2 else (7 - group)
SLOT_OFFSET = {0: 67, 1: -70, 2: 0}   # same as R4
# Active pairs: 0-8 (base 70-1750), I-index dependent
```
- LOCAL_INTERCONNECT bits in **self column** (X=lx), NOT prev column like R4
- **Base ≡ 70 (mod 210)** within 210-byte periods — same position as LUT TT slot=2
- Same SLOT_OFFSET as R4: {0: 67, 1: -70, 2: 0}; same bp formula
- **Pairs 0 and 4** (base 70, 910) are universal across all I-indices
- 4 pair activation patterns depending on I-index:
  - All pairs 0-8: I=2,15,16,18,22,33,34,35,36,37
  - Skip pair 3,7: I=0,30,31
  - Alternate even pairs: I=24,26,28,29,32
  - First 2 per block: I=4,17,27
- ±1 byte noise in base (70 vs 71) due to slot model precision
- 70% cross-validation hit rate (consistent with ~30% baseline cancellation)
- CRAM layout: LI at pairs 0-8, LUT TT at pairs ~16-23, R4 in prev column

### RouteCodec round-trip + hardware safety (2026-04-07)
- **Self-consistency PASS**: `route_roundtrip.py` reads switches from real Quartus RBFs, replays them with `apply_routing()`, re-reads → 0 dropped, 0 hallucinated cells (column + row routes)
- New methods: `write_c4_inz()` for I≠0 fixed-byte writes; `'raw'` switch type for single-bit replay (R24/LI/R4 wire-level writes are coarser than per-bit reads)
- **`validate_safe_for_hardware(rbf, zero)` V2**: classifies each LAB's LI pair_map via `_classify_li_lab()` against the 5 known-safe envelopes (`paired` / `alternating` / `edge_even_b0` / ...). Raises on unknown / broken / over-activated LI patterns. Use as a flash-time guard against LI MUX contention
- **SAFETY: `write_local_interconnect()` signature changed** from `(lx, ly, i_idx)` to `(lx, ly, pairs)`. The old auto-expansion of an I-index into ALL pairs from `_LI_ALL9 / _SKIP37 / _EVEN / _FIRST2` is **physically dangerous** — those pattern tables were inferred from CRAM reads but real Quartus only activates 1-5 pairs per LI MUX, never 9. Auto-expansion would drive multiple routing channels into the same LE input → input MUX short circuit on real silicon
- The pattern constants are kept only for `read_local_interconnect()` I-index disambiguation, never used by writes

### LI encoding modes (RESOLVED 2026-04-07 via base-granularity reads)
After dropping the `break` in `read_local_interconnect()` and emitting one entry per (pair, base) cell, the "9-pair vs 5-pair mystery" resolved into **two well-defined modes** with a uniform 9-cell envelope:

- **Mode "paired"** (13/21 LABs in single-input lut2 sweep, datab port):
  - P0 fully paired (B0+B1) + 4 middle pairs fully paired + P8 single-base tail = 9 cells
  - 3 middle-pair variants observed: `{2,4,6}` (most common), `{1,2,3}`, `{1,4,5}`
  - P8 tail base flips between B0/B1 across LABs
- **Mode "alternating"** (8/21 LABs):
  - Strict P0..P7 with alternating bases (P0=B1, P1=B0, P2=B1, ..., P7=B0) + P8 single-base tail = 9 cells
  - P8 tail base flips B0/B1 across LABs
- **Universal anchors**: P0 and P8 always present; cell `(P0, B1)` is in every observed class
- Total cells per LAB is **always exactly 9** — what looked like "5-pair vs 9-pair" was paired-cardinality vs cell-cardinality conflation in the old reader

`RouteCodec._classify_li_lab()` validates a LAB's pair_map against this taxonomy; `validate_safe_for_hardware()` V2 uses it as the safe-envelope check (rejects mixed/broken modes, accepts all 6 observed Quartus classes).

### Route Synthesis — Island Hopping (15 green-zone sources, 686 routes)
- `fuzz/route_synth.py` — `synth_route(zero, src, dst)` returns a bit-perfect-vs-Quartus RBF when `(sx,sy)` has a fingerprint snapshot AND `(dx,dy,port)` is in its `per_route_delta`. Otherwise falls back to formula-based plan_hops + LI envelope, gated by `validate_safe_for_hardware()`.
- **Major insight**: Cyclone IV CRAM is interleaved, NOT topologically isomorphic to chip layout. **Cross-source fingerprint intersection = 0 across 15 mined sources** → no universal source-entry formula exists at the cell level; route_synth must mine per-source corpora.
- **Per-source raw fingerprint mining**: `fuzz/fingerprint_raw_mine.py` is the codec-blind XOR-diff miner with header filter (frames 0..24 / bytes 32..5281 excluded). Replaces the older codec-aware mine which missed cells in unmapped R4 I-indices.
- **15 green islands** (`results/fingerprint_{sx}_{sy}.json`): (4,4), (10,4), (10,10), (10,14), (13,10), (16,4), (16,8), (16,14), (19,14), (22,12), (22,16), (25,6), (28,10), (28,18), (31,12). Fingerprint sizes range 0–41 cells; corner sources tend to be small, mid-die can be large.
- All 686/686 routes pass: bit-perfect vs Quartus, codec round-trip, safe-synth, safe-quartus, fingerprint drift = 0.
- **Source-tie hypothesis falsified (2026-04-07)**: cross-source analytic on 13 fingerprints found **0 cells appear in ≥2 sources**. The earlier "eastern-edge X=29/31/32/33 universal ties" reading was a byte-band coincidence, not real cell sharing. Static-dict and analytic-formula approaches are both dead.
- `fuzz/r4_iindex_mine.py` produces `results/r4_iindex_table.json` (942 entries), a silent dependency of `route_synth.py:206`. Auto-loaded; tells `synth_route()` which R4 I-index to pick per (src,dst,port) geometry.
- `fuzz/test_green_zone_harden.py` auto-discovers all `fingerprint_*.json` and runs the 5 checks + yellow probes per island.
- **Universal "always-on" structures** mined as 100% across `lits_pair_*` corpus, emitted unconditionally by `emit_ops()` for any inter-LAB route from a known source:
  - Source-side R4 launch driver: `R4_X{sx+1}_Y{sy}` at I=1 + I=2
  - Source-column R24 broadcast hold: 5 raw bits (currently hard-coded for sx=10,sy=10; needs multi-source generalization)
  - LI source-driver MUX: `(P8,B0)+(P8,B1)` at source LAB, skipped only for adjacent ±1 horizontal hops
- **Falsified hypothesis**: GND-tie noise was NOT the cause of (10,14)'s 11-bit fingerprint. `purify_fingerprint.py` recompiled with all 4 lut2 inputs routed (no GND ties) → fingerprint slightly grew, not shrank.
- New LI mode `edge_even_b0` added to `_classify_li_lab()` for top/bottom-row LABs (Y2/Y21): even pairs only, all base 0, no P8.

### LI mode selection rule — CLOSED NEGATIVE (T9+T10, 2026-04-07)
T9+T10 ran 12-source orthogonal-grid corpus (374 new compiles, 414 mappable rows). Decision-tree analysis in `fuzz/li_mode_tree.py`:
- **Deployable rules** (100%-ish): `dy∈{2,3,21}` → `edge_even_b0`; `adx==0` (pure column) → `paired` (79%); `dx>30 ∧ dy>7.5` → `paired` (small n)
- **Middle leaf stuck at 52%**: `dy>3 ∧ dx≤24.5 ∧ adx>0.5` (n=247, 60% of corpus) — 128 alt / 119 paired, unchanged by 2× corpus growth and sx/dx decorrelation
- **Conclusion**: paired vs alternating is NOT a function of static (sx,sy,dx,dy). Likely driven by Quartus placement seed / LI channel occupancy / cost-function ties. **Stop mining this rule.** Yellow-zone fallback keeps `paired` as weak prior (both modes are hardware-safe).

### Jailbreak — CE6 fabric map falsified (2026-04-07)
- **EP4CE6 ≡ EP4CE10 same physical die** (byte-identical RBF incl. device ID, `fuzz/cross_device_diff.py`)
- Probed `LCCOMB_Xx_Yy_N0` legality under DEVICE=EP4CE10F17C8 via `jailbreak/`. Result: **CE6 whitelist deletes ~40% of the die**.
- **True LAB_X = [3,4,5,6,7,8,9,10,11,12,13,14,16,17,18,19,21,22,23,24,25,26,28,29,30,31,32,33]** (28 cols, +6 vs CE6's 22)
- **True NON_LAB_X = {15, 20, 27}** only (not the old {5,9,14,15,20,27,30})
- **True LAB_Y = [2..21]** (20 rows, +Y=15 vs CE6's 19)
- **Non-LAB column identity** (via `jailbreak/probe_blocks.v` with 12× altsyncram + 8× lpm_mult):
  - X=15, X=27 → **M9K RAM columns**
  - X=20 → **embedded 9×9 multiplier column**
  - PLLs are off-fabric (die periphery, not any X column)
- **Dead-cell scan**: 3-phase XOR identity chain (`jailbreak/scan_gen.py` / `scanC_gen.py`) — 2,480 forbidden LEs hardware-verified healthy (Phase A=40, Phase B=640 full N, Phase C=1840 all hidden cols + Y=15 row). K1^K2 truth table matched bit-for-bit every time.
- **Effective fabric**: 392 → ~520+ LABs, 6,272 → 10,320 LEs (+65%)
- **Phase 3.25 CLOSED 2026-04-07**: both axes silicon-validated end-to-end through the codec.
  - **X=32 column** silicon-verified on the same day (LCCOMB_X32_Y10_N0 mask 0x8888); X=33 codec-verified via same column model. `COLUMN_BASE` extended to 28 LAB columns with standard 7350-byte stride.
  - **Y=15 ghost row** silicon-verified 2026-04-07 (`fuzz/demo_y15_keys2led.py` → `results/rbf/demo_y15_keys_to_led0.rbf`, LCCOMB_X10_Y15_N0 mask 0x0357 = `(K1&K2)|(K3&K4)`). Calibrated via `lut_single 10 15 0`, 48 minterm bits promoted, codec round-trip OK.
  - +65% fabric is production-ready on real CE6 silicon.

### Phase 4 — FASM toolchain (CLOSED on silicon 2026-04-08)
- `fuzz/fasm2rbf.py` / `fuzz/rbf2fasm.py`: human-readable FASM ⇄ CRC-valid RBF. Directives: `LUT`, `ROUTE`, `BIT`, `SRC` (per-source overhead vs baseline).
- **Signature backend** (`fuzz/route_signatures.py`): 1725 route cell-sets mined into `results/route_cells.json`; `build_route_ops()` short-circuits `synth_route` for any (src,dst,port) in the table, unlocking yellow-zone sources + the Y=15 jailbreak row.
- **Port-MUX consolidated loader (2026-04-08)**: every `(src,dst,dn)` group in `route_cells.json` consolidates into a `common` preamble + per-port `delta` of exactly 4 cells (2 adjacent byte pairs at 840-byte = LI-pair×4 spacing). 225/225 full 4-port groups match the "3+1" equivalence class with datab always the odd port. `route_signatures.load_cells()` now prefers `results/route_cells_consolidated.json` (34% file / 37% cell savings) and expands to the legacy flat dict in memory — zero behavior change, semantic invariant `common ∪ port_delta[p] == route_cells.json[key+",p"]` self-tested 1725/1725. See `memory/port_mux_4cell_structure.md`.
- **Semantic decomposer** (`fuzz/route_decompose.py`): greedy set-cover over route sigs + source-overhead chunks with strict containment; decomposes multi-route / cross-source CRAM diffs into clean ROUTE/SRC directives.
- **LUT absolute-mask compensation**: `fasm2rbf.bitgen()` auto-loads `minterm_0_X{x}_Y{y}_N{n}.rbf` to compute `base_tt` and convert FASM's absolute mask into the XOR delta `LutCodec.write_tt` actually expects.
- **Double-flip safety**: SRC overhead cells are unioned with route sig cells in `build_route_ops()` before emission, so cells shared between a source overhead and a route are XORed exactly once. Regression guard: `test_cross_source.py` (3/3 bit-perfect).
- **Regressions**: `test_fasm_roundtrip.py` 1725/1725, `test_fasm_semantic.py` 1725/1725, `test_multiroute_decompose.py` 41/42 (1 pre-existing), `test_cross_source.py` 3/3, `test_green_zone_harden.py` 15/15 islands 686/686 — all bit-perfect.
- **Hardware closure (2026-04-08)**: `X10Y10N0.LUT = 0x8888` (AND(K1,K2)) written as a one-line FASM → `fasm2rbf` → `patch_rbf_crc` → openFPGALoader flash → AX301 behavior matched (LED idle ON, K2 or K3 → OFF). FASM path is silicon-accepted end-to-end.

### Phase 4.5 — Plan D' sig-cache + NEORV32 coverage (2026-04-09)

The green-zone `route_cells.json` (1725 6-tuple entries, all sn=0) gave `test_green_zone_harden.py` 686/686 bit-perfect on its training corpus, but its real-world scope was exactly the 15 green islands it was mined from. To scale the FASM chain to real designs (NEORV32 being the hero target), a broader corpus was needed that covers arbitrary sources with arbitrary sn.

- **Plan D' factory** (`fuzz/plan_d_prime_factory.py`): 12-worker parallel compile loop that processes the 12,259 N-normed dedup edges extracted from `/tmp/neorv32_timing_big.txt` (STA dump of a real NEORV32 build). Each edge produces one `nv_pair_X{sx}Y{sy}N{sn}_to_X{dx}Y{dy}N{dn}_{port}.rbf` via `gen_two_luts_single_input_clocked(0x8888,0xAAAA)` at forced LCCOMB placements, under `DEVICE=EP4CE10F17C8` (jailbreak override). Self-loop filter, odd-N→even-N normalization, checkpoint atomic write, SIGINT handler, ×2 auto-retry with 5s backoff, 20GB work-dir cap, 5GB disk guard. Steady-state ~0.28–0.29 compiles/s, **final run: 11,715 ok / 0 fail / 676.5 min** (11h16m).
- **7-tuple sig-cache** (`fuzz/nv_sig_cache_merge.py`, `route_signatures.load_cells_full()`): the merged cache key is now `"sx,sy,sn->dx,dy,dn,port"`. Legacy 6-tuple entries are auto-lifted with `sn=0` so `test_green_zone_harden.py` keeps passing. Output file `results/route_cells_full.json` (**13,487 merged entries** after factory finalize). Format decision (explicit per-source): sn is *not* folded into dn because NEORV32 FF-driven feedback paths, FF-vs-LCCOMB driver ambiguity, and jailbreak-row sources at non-(N=0) slots all need unambiguous addressing.
- **`fasm2rbf` ROUTE syntax extended** for sn>0: `_ROUTE_RE` now optionally matches `N{sn}` on the source side; `parse_fasm()` emits a 7-tuple when sn is present, legacy 6-tuple otherwise; `build_route_ops()` already handled both forms. Enables single-line FASM like `ROUTE X5Y3N4 -> X4Y3N6.datad`.
- **Background Tasks A–C** (ran concurrently with factory):
  - `fuzz/nv_fingerprint_stream.py` — streaming per-source intersection miner against `nv_zero_global.rbf`, writes `results/nv_fingerprints/nv_fp_{sx}_{sy}_{sn}.json` when a source has ≥3 routes
  - `fuzz/nv_global_baseline_extract.py` — compiles a single `nv_zero_global.rbf` and XOR-diffs every `nv_pair_*.rbf` against it to populate `results/nv_route_cells.json` (the raw input to the merger)
  - `fuzz/nv_watchdog.py` — stall detection, disk cap enforcement, factory liveness ping
- **NEORV32 edge coverage** (`fuzz/nv_edge_coverage.py`): cross-references all 12,259 strict-dedup edges against `route_cells_full.json`. **Final: 11,762 / 12,259 edges covered (95.9%)**. The 497-edge (4.1%) gap is **not** a factory miss — it is the LAB+self-loop filter: odd-N self-mappings, IO-ring coordinates (X∈{0,1,2}, Y∈{0,1,22}), and non-LAB columns (X∈{15,20,27}) that the two-LUT compile template cannot place. **100% of placeable edges are covered.** Sources fully covered: 0 / 4,291 — expected, because NEORV32 sources typically fan out to non-placeable dsts (FF slots, IO, non-LAB) that land in the 497-edge filter set, so no source is 100% dst-covered even at 100% placeable-coverage.
- **Legacy green-zone contribution = 0 hits against NEORV32** — all coverage comes from Plan D' factory entries. The 1725 legacy entries are dead weight for NEORV32 but remain load-bearing for green-zone regression; they stay in the merged file. See memory `legacy_cache_zero_nv32_hits.md`.

### Phase 4.5 hero test — X=5 jailbreak FASM silicon validation (2026-04-09)

First silicon proof of the full Phase 4.5 stack on a CE6-forbidden column:

- **Edge**: `ROUTE X5Y3N4 -> X4Y3N6.datad` (single-line FASM, picked by `fuzz/pick_hero_edge.py` from the sig-cache with priority: jailbreak-column × sn>0 × nv_pair-on-disk)
- **X=5 is NOT in the CE6 LAB_X whitelist** — it's one of the jailbreak columns unlocked by the 2026-04-07 CE10 fitter probe. First hero test there.
- **sn=4 > 0** — exercises the 7-tuple lookup path, not the sn=0 legacy lift fallback. Distinguishes "code correct" from "lucky alignment with legacy green-zone".
- **144 sig cells** from the Plan D' factory's `nv_pair_X5Y3N4_to_X4Y3N6_datad.rbf` isolated 2-LUT compile.
- **Byte-level equivalence** (pre-flash): `fasm2rbf /tmp/hero.fasm nv_zero_global.rbf /tmp/hero.rbf` → **CRAM band ≥5282 is 0 diffs vs factory nv_pair**, only 6 header-band diffs in bytes 43–74 (Quartus device-id/seed fields, not CRC-protected, silicon-ignored). All 1727/1727 CRAM frames pass CRC check.
- **Silicon** (AX301, openFPGALoader): full SRAM load to 100%, clean `Done`, no CRC error, no EPCS fallback. FPGA drives LED pins to a stable pattern with lut1/lut2 constants (0x8888/0xAAAA) via Quartus-auto-assigned pin bank — not a functional signal path, but definitive proof that configuration completed and internal logic is running.
- **Three axes validated in one flash**: (a) `fasm2rbf` faithfully reproduces Plan D' factory CRAM output, (b) Plan D' sig-cache cells are silicon-accepted, (c) CE6-forbidden column X=5 survives the full FASM → CE10-override → CRC-patch chain.
- **Observability caveat**: nv_pair RBFs have NO KEY/LED wiring (factory used auto-routing of floating LUTs with a CLK register). Hero tests on nv_pair can only observe "did it boot" + default LED pattern, never functional response to inputs. For functional behavior tests use the `demo_*_keys2led` baseline path.

See memory `hero_edge_x5_fasm_silicon.md`.

### Phase 4.5 negative results (2026-04-09)

Two dead ends from this session, both archived as they shape future work:

- **R4 dark I-index passive mining DEAD** (`fuzz/nv_r4_dark_mine.py`, memory `r4_dark_passive_mining_dead.md`): attempted to recover `_R4_BASE_PREV` entries for 13 dark I-indices by XOR-diffing the full NEORV32 RBF vs `nv_zero_global.rbf` and sweeping BASE candidates against STA wire geometry. Null test (`/tmp/r4_dark_null.py`) showed the diff set is too dense (93k dirty bytes, 113k set cells ≈ 4% CRAM) — any BASE in [7185..7263] scores 55-61% hit across wires regardless of I-index, and the method cannot recover known BASEs for I=0/1/2/10 (returns 1789, 68, 76, 47 — all wrong). Per-I "winners" have lift only 1.1-1.5× over the density floor, indistinguishable from noise. Conclusion: passive observation needs sparse signals; full NEORV32 builds are too dense. Any future dark-I mining must use active per-I pair-diff compiles, OR accept that the sig-cache supersedes formula completion for production use (route_synth's signature short-circuit already makes `_R4_BASE_PREV` dead code for green-zone regression).
- **Fanout-first scheduling intuition WRONG** (`fuzz/nv_schedule_sim.py`, memory `fanout_first_scheduling_worse.md`): the "main roads before alleys" intuition — reordering remaining factory edges by source-fanout DESC to finish high-fanout hubs first — actually **delays the `sources_fully_covered` milestones by 1-4 hours** vs the current lex order. Reason: spending 12 minutes on one 203-edge hub source before marking it +1 done is strictly worse than finishing ~60 small sources in the same window. Lex order accidentally clusters small sources at the head of the sorted edge list, producing a near-optimal source-completion curve. Rule: **never propose scheduling intervention without a simulator saying the delta is strictly positive on the target metric**. Fanout-weighted coverage is ~identical between strategies (<4 min delta), confirming lex isn't just incidentally good — it's near-globally optimal for this workload.

### Phase 5.2 — M9K init content codec (Stage A+B CLOSED 2026-04-09)

Stage A at `M9K_X15_Y2_N0` (9b×512 altsyncram, real-pin AX301 SDRAM bus harness, `fuzz/m9k_init_harness.py`) partitioned M9K CRAM into three physically decoupled bands — inverse of the going-in "everything lives in the block band" assumption:

1. **Data content** → column-local frame ~1243, XOR-linear GREEN (`m9k_init_sweep.py` walking-1)
2. **Mode / operation_mode / ROM** → block band 1692-1738 (`m9k_mode_t20_probe.py`) — **STRUCTURAL_ROM verdict**: ROM is an independent operation_mode, not degenerate RAM(wren=0); 41 block-band cells differentiate ROM from tied-wren RAM. T2 mode sweep upgrades to 4 axes.
3. **Output-register clock enable** → frames 1007/1009 bp=6 offset 85 (`m9k_clock_probe.py`); cken0/rden are smaller, scattered, NOT in the Phase 5.0 1005-1015 band as previously assumed.

**Harness pin fix**: initial `_FREE_PINS` guessed B1/B2/C1/C2/D1/D2/E2/... which are EPCS config dual-use (fitter error 171016). Replaced with 16 S_DB + 13 S_A = 29 SDRAM bus pins from `~/fpga/AX301_ref/AX301.tcl` (board-validated). Memory `ax301_board_docs.md`.

**Sweep verdict bug**: `m9k_init_sweep.py` prints YELLOW whenever the block band is empty, but the data band lives at frame 1243 (outside). A clean walking-1 GREEN result is mis-classified as YELLOW. Always inspect `per_bit.all_cram` manually until the verdict logic is patched. Memory `feedback_m9k_sweep_verdict_bug.md`.

**Stage B 2D linear formula** (`fuzz/m9k_init_basis.py`, validated 10/10 probe points + full 512-word round-trip):

```python
byte(word, bit) = anchor + (word // 2) * 210 - (word % 2) - 2 * bit
bp              = 6
M9K_INIT_ANCHORS[("X15_Y2_N0", 9, 512)] = 261142
```

- Words pair two-per-frame (odd word one byte below even word), then advance 210 bytes per pair.
- Codec flips ONLY primary cells; the "secondary" cells that showed up in the word probe at +128/+129 were **frame CRC bytes** at per-frame offsets 208/209, auto-handled downstream by `bitstream.patch_rbf_crc()`.
- **READ** validation: 512/512 words decoded correctly from a Quartus-compiled RBF with 74 random non-zero MIF entries.
- **WRITE** validation: `base → write_init → patch_rbf_crc` produces **0 CRAM diffs** vs Quartus (only 6 expected header-band seed/timestamp bytes differ).
- `_assert_cell_safe()` guards against the formula landing on a CRC slot (never does for the validated site; catches broken anchors on future calibrations).

**Scope**: anchor 261142 is calibrated only for `(X15_Y2_N0, 9, 512)`. Other sites/modes need per-(X, Y, N, WIDTH, DEPTH) calibration sweeps analogous to LUT TT `n_sweep`. Formula structure is expected to generalize — verify at one more site before extrapolating.

**Unblocks Phase 5.3**: NEORV32 boot ROM can be written as FASM `M9K.INIT = <hex>` once the anchor table covers the used M9K sites — self-contained RISC-V bitstream synthesis without Quartus MIF recompiles.

See memories `m9k_stage_a_complete.md` and `m9k_stage_b_complete.md`.

### Phase 3.27 — M9K CRAM probe (superseded by Phase 5.0 real-pin re-mine)
- `fuzz/m9k_probe_mine.py` (locked-PIN) and `fuzz/m9k_probe_clean.py` (VIRTUAL_PIN, worse).
- **Legacy archive**: the `m9k_cells` table originally carried 237 `M9K_GLOBAL_ON` + 299 `M9K_COL15_ON` rows. Phase 5.0 showed **76-81% were CRC byte ghosts** (bytes at col 208/209 of each 210-byte frame). Both tags were CRC-stripped in place to **58 cells each**, and the two are byte-identical → the "GLOBAL vs COL15" distinction was fiction. Current bitdb state: `M9K_GLOBAL_ON=58`, `M9K_COL15_ON=58`. Use the CRC-stripped rows; the 237/299 values only exist in git history.
- Position model (Y sweep at X=15) abandoned 2026-04-07: auto-router churn dominates and the per-Y signal cannot be separated from fitter noise without manual routing for every feeder.
- **Mult X=20 probe** originally failed with `MULT_X20_Y*_N0` (wrong LOC); Phase 5.0 cracked the real syntax — see next section.

### Phase 5.0 — Non-LAB blocks (DSPMULT + M9K re-mine, 2026-04-08)
- **LOC syntax cracked** (`fuzz/mult_loc_discover.py`, `m9k_loc_discover.py`): LOC takes the hierarchical MegaFunction node path, not a coordinate alias.
  - DSPMULT: `set_location_assignment DSPMULT_X20_Y{y}_N{n} -to "lpm_mult:u|mult_qpl:auto_generated|mac_mult1"`, 42 legal sites (Y1..21 × N{0,1}, N=2 illegal)
  - M9K: `set_location_assignment M9K_X{x}_Y{y}_N{n} -to "altsyncram:u|altsyncram_3ov:auto_generated|ALTSYNCRAM"`, X∈{15,27}, 126 legal sites
- **RULE: never mine non-LAB blocks with VIRTUAL_PIN** (`fuzz/mult_noise_test.py` proof). A first-attempt 62-cell `MULT_GLOBAL_ON` under VIRTUAL_PIN had 0 overlap with a real-pin recompile — Quartus routes to a fake pin bank and the resulting CRAM diff is 100% ghost-routing artifact. Retagged `MULT_VIRTUAL_PIN_ARTIFACT`, memory `feedback_virtual_pin_mining_is_fiction.md`.
- **RULE: non-LAB mining must filter CRAM-only (off >= 5282)** (`fuzz/mult_header_noise.py` 5-seed null test). Bytes 44 and 73 have a 4-5 bit per-SEED noise floor on identical designs — any "header band finding" without this filter is fiction. This also explains the earlier FF layer-2 @ byte 73 dead end (same noise). Memory `feedback_header_band_noise_floor.md`.
- **Two non-LAB config bands found** (both CRAM-only, CRC-stripped):

| band | frames | role | cells mined |
|---|---|---|---|
| Block enable/mode | 1692-1738 | block presence + mode | DSPMULT 29, M9K 58, mult∩M9K=0 (disjoint) |
| Block clock-net | ~1007-1013 | per-block clock-enable register | DSPMULT clock 8, M9K clock 4, 1-3 byte adjacency in same frames/bp |

- **Signatures archived** in `results/ep4ce6_bitdb.sqlite` table `m9k_cells` / `results/mult_global_on_real.json`:
  - `MULT_GLOBAL_ON_REAL` = **29 cells** (42-site real-pin sweep, CRAM-only)
  - `M9K_GLOBAL_ON` = **58 cells** (CRC-stripped from legacy 237, cross-validated 55/58 against 126-site real-pin sweep)
  - `M9K_COL15_ON` ≡ `M9K_GLOBAL_ON` (no column-specific signature)
  - `DSPMULT_CLOCK_ENABLE = (209891, bp 4)` — first single-bit semantic field extracted from a non-LAB block (`fuzz/mult_reg_sweep.py`, pipe1∩pipe2∩pipe3)
- **Dead ends**:
  - STA wire extraction (`fuzz/mult_sta_wires.py`) on DSPMULT returns only chip-edge IOBUF/IOPAD — Quartus treats DSPMULT as a black-box cell, internal routing not exposed via `report_timing`. Same wall that killed the M9K per-site model.
  - Parameter decoding beyond CLOCK_ENABLE: width bits are multi-bit continuous, signed bits hide in the header noise floor, pipeline stages don't encode incrementally (pipe2 vs pipe1 and pipe3 vs pipe2 share 0 cells).
  - `altpll` has no `PLL_Xx_Yy_N{n}` LOC (`fuzz/altpll_loc_discover.py`) — PLLs are off-fabric and use singleton `PLL_1`/`PLL_2` names; deferred.

## Methodology

### Best Practice: Pair-Diff
1. Compile `cycloneive_lcell_comb` with `lut_mask=16'h0000` at target location
2. Compile same with `lut_mask=16'hFFFF`
3. Diff the two → only LUT SRAM cells, no routing noise

### Placement Control
```tcl
set_location_assignment LCCOMB_X10_Y10_N0 -to "lut_inst"
```

### Node Names
- Primitive designs (`gen_lut4_primitive`): node = `lut_inst`
- Behavioral designs (`gen_lut4`): node = `lut_out`

## Bitstream Codec

```bash
# Calibrate a position (16 minterm pair-diffs, ~2.5 min)
python3 runner.py n_sweep 10 10   # generates minterm_0..15 features

# Read LUT TT from RBF
python3 analyze.py read_tt design.rbf zero.rbf 10 10 0

# Write LUT TT to RBF
python3 analyze.py write_tt zero.rbf 0x8888 output.rbf 10 10 0
```

Codec-generated RBFs are bit-identical to Quartus in CRAM cells. Header/CRC bytes differ but the codec's `patch_rbf_crc()` (see RBF CRC section below) recomputes them so the bitstream loads cleanly on real silicon.

### End-to-End Hardware Verification (2026-04-06 / 2026-04-07)
- Codec `write_tt` → `patch_rbf_crc` → openFPGALoader flash → AX301 hardware behavior confirmed
- AND (0x8888): LED ON default, K2/K3 → OFF (active-low keys)
- XOR (0x6996): LED OFF default, single key → ON, both → OFF
- **0xFFFF / 0x0000 control test**: opposite LED states confirm LutCodec.write_tt reaches silicon
- **4-input functional demo (2026-04-07)**: `Q = (¬K1∧¬K2) ∨ (¬K3∧¬K4)`, mask 0x0357 (XOR-compensated to 0x0356 against minterm_0 base) — full truth table validated by physical key presses (`fuzz/demo_keys2leds.py`)
- Codec vs Quartus: **0 CRAM diffs** in core, CRC bytes patched to valid values

### RBF CRC (2026-04-07)
- Cyclone IV configuration state machine validates CRC per frame; no QSF disables it
- Algorithm: CRC-16/IBM, poly **0x8005** (reflected 0xA001), init **0xFE54**, refin/refout=True, xorout=0
- Frame layout: 1752 frames × 210 bytes (208 data + 2 CRC LE) starting at byte 32
- Frames **0..24** = bitstream header (no CRC; do NOT touch)
- Frames **25..1751** = CRAM (CRC enforced); 1727/1727 verified
- `bitstream.patch_rbf_crc(rbf)` recomputes all CRAM frame CRCs; called automatically by `route_synth()` and the recommended last step before flashing any codec-modified RBF
- `read_switches()` masks CRC bytes against the zero baseline so a CRC patch doesn't pollute the routing diff

### AX301 Pin Map (silicon-verified 2026-04-07 via `pin_probe.py`)
| PIN     | Key  | Notes |
|---------|------|-------|
| PIN_E15 | KEY1 | Was mislabeled "RESET" in old config.py |
| PIN_E16 | KEY2 | A in FUZZ_PINS |
| PIN_M16 | KEY3 | B |
| PIN_M15 | KEY4 | C |
| PIN_G15 | LED0 | Active-high; keys are active-low |

### LutCodec semantics — IMPORTANT footgun
`LutCodec.write_tt(base, mask)` is **XOR-delta**, not absolute. The result is `base_tt XOR mask`. When `base` is not a true 0x0000 baseline (e.g. `minterm_i` has TT bit i set), compensate with `mask = target ^ base_tt`. `read_tt` is symmetric (returns delta vs base).

## Tools

- **Quartus 21.1 Lite**: `$HOME/intelFPGA_lite/21.1/quartus/bin/`
- **RBF generation**: `quartus_cpf -c -o bitstream_compression=off` (NEVER use sof2rbf.py)
- **Programming**: `$HOME/see_neorv32_run_linux/tools/openFPGALoader/build/openFPGALoader -c usb-blaster`
- **Hardware**: 黑金 AX301, EP4CE6F17C8, USB-Blaster JTAG

## EP4CE6 Chip Geometry

**CE6 software whitelist (default, used throughout the codec)**:
- 392 LABs, 16 LEs per LAB = 6,272 total LEs
- LAB X: [3,4,6,7,8,10,11,12,13,16,17,18,19,21,22,23,24,25,26,28,29,31]
- LAB Y: [2,3,4,5,6,7,8,9,10,11,12,13,14,16,17,18,19,21]
- LE N: [0,2,4,6,8,10,12,14,16,18,20,22,24,26,28,30]
- Routing: Block 32,401 / Local 10,320 / C4 21,816 / R4 28,186

**True silicon (CE10 fitter probe, 2026-04-07)**: see Jailbreak section above.
520+ LABs, 10,320 LEs, true LAB_X adds {5,9,14,30,32,33}, true LAB_Y adds {15}, true non-LAB = {15,20,27} only.

## Licensing

**Dual license (2026-04-07 onward, replaced the previous MIT):**
- Code (`fuzz/**/*.py`, `*.v`, `*.tcl`): **GPL-3.0-or-later**. All source files carry `SPDX-License-Identifier: GPL-3.0-or-later`.
- Documentation, findings, memory files, READMEs, CLAUDE.md: **CC BY-SA 4.0**.
- Full texts: `LICENSES/GPL-3.0-or-later.txt`, `LICENSES/CC-BY-SA-4.0.txt`. See top-level `LICENSE` for rationale (trigger was the CE6→CE10 jailbreak — stakes shifted from "neat hack on a cheap board" to "unlock +65% fabric on every CE6 in the wild"; MIT would have let Altera absorb the method silently).

## Disk Space (~200 GB available)

| Phase | Compiles | RBF storage | Work dir (peak) |
|-------|----------|-------------|-----------------|
| 1+2 | ~7,500 | ~2.7 GB | ~50 GB (cleanable) |
| 3 | ~100,000 | ~36 GB | ~500 GB (**must clean**) |

Phase 1+2 fit easily. Phase 3 requires either:
- Clean `work/` after each compile (keep only .rbf, ~36 GB)
- Or skip .rbf entirely — diff in-memory, store only results to SQLite (~few hundred MB)

`compile.py` has `clean_work_dir()` for this. For Phase 3, strongly prefer in-memory diff + SQLite-only storage.

## Known Pitfalls

1. Left-edge columns (X=3,4,6,7) have CRAM addresses below 0x10000
2. Quartus fit reports contain non-UTF8 bytes — use `errors="replace"`
3. Don't run parallel campaigns sharing the same `work/` directory
4. `sof2rbf.py` produces invalid bitstreams — always use `quartus_cpf`
