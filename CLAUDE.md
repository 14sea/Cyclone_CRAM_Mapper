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
```

## Directory Structure

```
EP4CE6/
├── fuzz/                    # Fuzzing pipeline (Python)
│   ├── config.py            # EP4CE6 constants, coordinates, pins
│   ├── verilog_gen.py       # Verilog generators (LUT4 primitive, FF, empty)
│   ├── qsf_gen.py           # QSF + placement constraint generator
│   ├── compile.py           # Quartus headless compilation driver
│   ├── rbf_diff.py          # Bit-level binary diff engine
│   ├── database.py          # SQLite bit mapping storage
│   ├── runner.py            # Fuzzing campaign orchestrator
│   └── analyze.py           # Result analysis and visualization
├── results/
│   ├── rbf/                 # Collected .rbf files (~190 files)
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
- 22 LAB columns mapped; non-LAB columns (M9K/DSP/PLL) at X=5,9,14,15,20,27,30
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
- FF mode bits (arst/ena): 82 shared mode bits + feature-specific routing
- **LCFF placement rejected** by Quartus Lite — FF auto-placed near output pin

### Routing Matrix (Phase 3 — In Progress)
- **Fully deterministic** routing with MINIMUM optimization level
- **STA routing extraction**: `report_timing -show_routing` gives exact wire names per path
- Wire naming: `{TYPE}_X{x}_Y{y}_N{n}_I{index}` (C4, R4, C16, R24, LOCAL_INTERCONNECT, LE_BUFFER)
- 232 paths collected, 607+ unique wire instances from 12 source positions
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

**I≠0 (per-(X,I) fixed-byte lookup — 24 mappings, 11 I-indices):**
- C4 I≠0 uses **fixed byte offsets** (like R24) — byte is the same for all Y, only bp varies
- Pair/position within column **varies per column** — no universal formula
- 24 per-(X,I) mappings found via baseline-diff (c4_mapper.py, 2026-04-06):
  - I=1: X=9,15,16,25 | I=3: X=13,22,25 | I=7: X=13 | I=8: X=13
  - I=9: X=10,28,30 | I=10: X=9,28,29 | I=12: X=9,10,22,25
  - I=14: X=25 | I=15: X=16 | I=20: X=9 | I=23: X=22,29
- I=3 and I=12 **share the same byte** at X=22 and X=25 (indistinguishable)
- pos is always 184 or 185 (data byte positions within 210-byte period)
- Non-LAB columns (X=9,15,30) have large pair numbers (58-382) due to wider CRAM
- RouteCodec reads both I=0 (formula) and I≠0 (lookup) in read_c4()

### R4 Switch CRAM Address Model (18 I-indices mapped)
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
- 37 unique R4 I-indices observed in STA data; ~19 still unmapped
- 774 routing paths collected, parallel compilation at ~4s/target

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
- **`validate_safe_for_hardware(rbf, zero)`**: counts LI pairs activated per LAB, raises if >`LI_MAX_PAIRS_PER_LAB` (default 5). Use as a flash-time guard against LI MUX over-activation contention
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

### Open: mode selection rule
Which mode (paired vs alternating) Quartus picks for a given LAB is not yet derivable from the routing key. Mode "paired" dominates column moves; mode "alternating" dominates row moves and LABs near non-LAB columns (M9K/DSP at X5,9,14,15,20,27,30). Need a richer routing_paths corpus (multi-LE designs) to mine the rule.

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

Codec-generated RBFs are bit-identical to Quartus in CRAM cells (header/CRC differ).

### End-to-End Hardware Verification (2026-04-06)
- Codec `write_tt` → openFPGALoader flash → AX301 hardware behavior confirmed
- AND (0x8888): LED ON default, any key → OFF (active-low keys on AX301)
- XOR (0x6996): LED OFF default, single key → ON, both → OFF
- Codec vs Quartus: **0 CRAM diffs**, 14 header/CRC diffs (harmless)
- Pin mapping: A=KEY2 (PIN_E16), B=KEY3 (PIN_M16), Q=LED0 (PIN_G15)

## Tools

- **Quartus 21.1 Lite**: `$HOME/intelFPGA_lite/21.1/quartus/bin/`
- **RBF generation**: `quartus_cpf -c -o bitstream_compression=off` (NEVER use sof2rbf.py)
- **Programming**: `$HOME/see_neorv32_run_linux/tools/openFPGALoader/build/openFPGALoader -c usb-blaster`
- **Hardware**: 黑金 AX301, EP4CE6F17C8, USB-Blaster JTAG

## EP4CE6 Chip Geometry

- 392 LABs, 16 LEs per LAB = 6,272 total LEs
- LAB X: [3,4,6,7,8,10,11,12,13,16,17,18,19,21,22,23,24,25,26,28,29,31]
- LAB Y: [2,3,4,5,6,7,8,9,10,11,12,13,14,16,17,18,19,21]
- LE N: [0,2,4,6,8,10,12,14,16,18,20,22,24,26,28,30]
- Routing: Block 32,401 / Local 10,320 / C4 21,816 / R4 28,186

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
