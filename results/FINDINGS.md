# EP4CE6 Bitstream Reverse Engineering — Phase 1 & 2 Findings

## RBF Format
- Fixed size: 368,011 bytes = 2,944,088 bits
- Preamble: 32 bytes 0xFF | Config: 367,920 bytes | Postamble: 59 bytes 0xFF

## CRAM Column Address Map (Verified 22/22 columns via pair-diff)

Standard LAB column step: **7,350 bytes (0x1CB6)**

Column base = Y=2, N=0 ctrl pair[0] address (bit-7):

| X | CRAM Base | Delta | Notes |
|---|-----------|-------|-------|
| 3 | 0x076E0 | - | Left edge |
| 4 | 0x09396 | +7,350 | |
| 6 | 0x0CD02 | +14,700 | Skip X=5 (M9K col) |
| 7 | 0x0E9B8 | +7,350 | |
| 8 | 0x1066E | +7,350 | |
| 10 | 0x13FDA | +14,700 | Skip X=9 (M9K col) |
| 11 | 0x15C90 | +7,350 | |
| 12 | 0x17946 | +7,350 | |
| 13 | 0x195FC | +7,350 | |
| 16 | 0x2BFC2 | +76,230 | Skip X=14-15 (DSP cols) |
| 17 | 0x2DC78 | +7,350 | |
| 18 | 0x2FC76 | +8,190 | Slightly wider (+840) |
| 19 | 0x3192C | +7,350 | |
| 21 | 0x34A64 | +12,600 | Skip X=20 (M9K col) |
| 22 | 0x3671A | +7,350 | |
| 23 | 0x383D0 | +7,350 | |
| 24 | 0x3A086 | +7,350 | |
| 25 | 0x3BD3C | +7,350 | |
| 26 | 0x3D9F2 | +7,350 | |
| 28 | 0x4E702 | +68,880 | Skip X=27 (M9K col + PLL?) |
| 29 | 0x503B8 | +7,350 | |
| 31 | 0x53D24 | +14,700 | Skip X=30, right edge |

Non-LAB column CRAM widths: M9K(5,9,30)=7,350; DSP(14+15)=68,880; M9K(20)=5,250; M9K(27)+PLL=61,530

## CRAM Address Model (Verified 376/376 positions, 100%)

### Overview
Each LAB column contains 8 LUT truth table pair positions spaced 210 bytes apart. Within each 210-byte period, ctrl bytes for ALL 18 Y rows are interleaved at fixed offsets, sharing the same data byte positions.

### Constants (uniform across ALL 22 columns)
- **Pair spacing**: 210 bytes
- **Ctrl→Data offset**: 48 bytes
- **Ctrl pair**: 2 consecutive bytes (addr, addr+1) with single-bit set
- **Data pair**: 2 consecutive bytes (addr, addr+1) with multi-bit set
- **8 pairs per LE**: spanning 7×210 + ~48 = ~1,518 bytes

### Y-Address Formula (Verified 18/18 Y × 22 X = 396 positions)
```
cram_row = Y - 2              (Y=2..21, physical coordinates)
slot = cram_row % 3           (0, 1, or 2)
group = cram_row // 3         (0..6)

slot_base = {0: 136, 1: 0, 2: 70}   (byte offset within 210-byte period)

ctrl_offset = slot_base[slot] + group * 3 + (1 if slot == 0 and group > 0 else 0)
ctrl_bit = 7 - group - (1 if slot > 0 else 0)

ctrl_addr = period_start + ctrl_offset + pair_index * 210
data_addr = ctrl_addr + 48
```

Where `period_start` = column_base - 136 (i.e., the Y=3 ctrl address).

### Y → (offset, ctrl_bit) Complete Mapping

| Y | cram_row | slot | group | offset | ctrl_bit |
|----|----------|------|-------|--------|----------|
| 2 | 0 | 0 | 0 | +136 | bit-7 |
| 3 | 1 | 1 | 0 | +0 | bit-6 |
| 4 | 2 | 2 | 0 | +70 | bit-6 |
| 5 | 3 | 0 | 1 | +140 | bit-6 |
| 6 | 4 | 1 | 1 | +3 | bit-5 |
| 7 | 5 | 2 | 1 | +73 | bit-5 |
| 8 | 6 | 0 | 2 | +143 | bit-5 |
| 9 | 7 | 1 | 2 | +6 | bit-4 |
| 10 | 8 | 2 | 2 | +76 | bit-4 |
| 11 | 9 | 0 | 3 | +146 | bit-4 |
| 12 | 10 | 1 | 3 | +9 | bit-3 |
| 13 | 11 | 2 | 3 | +79 | bit-3 |
| 14 | 12 | 0 | 4 | +149 | bit-3 |
| (15) | 13 | 1 | 4 | +12 | bit-2 |
| 16 | 14 | 2 | 4 | +82 | bit-2 |
| 17 | 15 | 0 | 5 | +152 | bit-2 |
| 18 | 16 | 1 | 5 | +15 | bit-1 |
| 19 | 17 | 2 | 5 | +85 | bit-1 |
| (20) | 18 | 0 | 6 | +155 | bit-1 |
| 21 | 19 | 1 | 6 | +18 | bit-0 |

Rows Y=15 and Y=20 (in parentheses) are phantom CRAM rows with no LAB.

### Data Byte Sharing
Data bytes at each pair position are **shared across all Y rows** in the column. Different Y values use different bit positions within the same data bytes. The ctrl bytes (unique per Y) select which LE row is being configured.

Total bits per LUT TT (mask 0x0000 vs 0xFFFF pair-diff):
- Y=2 (edge): 64 bits (16 ctrl + 48 data)
- Y%3=0 (non-edge): ~96 bits (uses 2 data bytes per pair)
- Other Y values: 64-112 bits (varies by position)

### CRAM N (LE Index) Address Formula (Verified 32/32: 16 N × 2 columns)
Within a LAB, LE N addresses decrease from N=0 with alternating -2/-6 steps and a -12 gap at the mid-LAB boundary (N=14→16):
```
For N = 2k (k = 0..15):
  half = k // 8              (0 for first 8 LEs, 1 for last 8)
  kh = k % 8                 (position within half)
  delta = -(half * 38) - (kh // 2) * 8 - (kh % 2) * 2

Steps: -2, -6, -2, -6, -2, -6, -2, -12, -2, -6, -2, -6, -2, -6, -2
```
N=30 (last LE) address = N=0 address − 64 bytes.
Verified identical pattern at X=3 and X=10 — N formula is column-independent.

## LUT4 Truth Table Encoding

### Key Discovery
The LUT4 truth table is encoded in the bitstream using **XOR-linear algebra**:
- Each of the 16 truth table bits maps to 8-10 SRAM cells
- Any arbitrary 16-bit mask can be predicted by XOR-combining the single-bit patterns
- Verified with mask 0xFFFF (64 bits, perfect match) and 0x8888 (16 bits, perfect match)

### Truth Table Pair Structure (LE at X=10, Y=10, N=0)
The 16 TT bits are organized as 8 pairs: (TT_i, TT_{i+8})

| Pair | Ctrl_lo | Ctrl_hi | Data_0 | Data_1 | Ctrl→Data |
|------|---------|---------|--------|--------|-----------|
| 0/8 | 0x1455D | 0x1455C | 0x145C8 | 0x145C9 | +107 |
| 1/9 | 0x1448A | 0x1448B | 0x144F6 | 0x144F7 | +108 |
| 2/10 | 0x143B9 | 0x143B8 | 0x14424 | 0x14425 | +107 |
| 3/11 | 0x142E6 | 0x142E7 | 0x14352 | 0x14353 | +108 |
| 4/12 | 0x14215 | 0x14214 | 0x14280 | 0x14281 | +107 |
| 5/13 | 0x14142 | 0x14143 | 0x141AE | 0x141AF | +108 |
| 6/14 | 0x14071 | 0x14070 | 0x140DC | 0x140DD | +107 |
| 7/15 | 0x13F9E | 0x13F9F | 0x1400A | 0x1400B | +108 |

### Address Pattern (Updated via pair-diff grid scan)
- Inter-pair spacing: **210 bytes** (uniform across ALL 22 columns — previous "211/209 alternating" was measurement artifact from noisy baseline diffs)
- Ctrl→Data offset: **48 bytes** (uniform across ALL columns — previous "108/76" values were from noisy baseline measurements)
- Each pair has 2 ctrl bytes (single-bit, identifies Y row) + 2 data bytes (multi-bit, shared across Y rows)
- LUT SRAM span per LE: 7×210 + 48 ≈ 1,518 bytes, 64-96 SRAM bits per LUT TT

## DFF / Flip-Flop Configuration

### Challenge
Quartus Lite rejects `LCFF_Xx_Yy_Nn` placement constraints for registers. The FF (`dffeas` primitive) is always auto-placed near the output pin's IO buffer, typically in a peripheral column (X=1 or X=3), **not** co-located with the LUT.

### Methodology
1. Place LUT at X=10,Y=10,N=0 with `cycloneive_lcell_comb` primitive
2. Add `dffeas` FF without placement constraint
3. Use output pin PIN_T15 to attract FF to LAB column X=3 (FF lands at X=3,Y=11,N=17)
4. Pair-diff: zero-mask LUT-only vs zero-mask LUT+FF → isolates FF changes
5. Compare with LUT TT pair-diff at same column to remove LUT overlap

### Results
Adding a basic DFF changes **362 bits** vs LUT-only baseline:
- Global/peripheral (0x00xxx): 20 bits
- Routing switches (0x02xxx-0x04xxx): 132 bits
- FF CRAM at X=3 column: 34 bits (LE-local configuration)
- Other routing columns: 176 bits

### FF CRAM Pair Structure (X=3 column, LE at Y=11, N=17)
FF configuration uses the same ctrl(bit-4) + data(byte-pair) structure as LUT truth tables.
4 FF pairs per LE (vs 8 LUT TT pairs), split into two regions around the LUT TT area:

**Region A** (below LUT TT, ~5220 bytes below center):

| Pair | Ctrl | Data_0 | Data_1 | Ctrl→Data |
|------|------|--------|--------|-----------|
| 1 | 0x064A8:4 | 0x06504 | 0x06505 | +92 |
| 2 | 0x0657A:4 | 0x065D6 | 0x065D7 | +92 |

**Region B** (above LUT TT, ~9394 bytes above center):

| Pair | Ctrl | Data_0 | Data_1 | Extra |
|------|------|--------|--------|-------|
| 3 | 0x09D68:4 | 0x09D9E | 0x09D9F | +flag 0x09D9B:7 |
| 4 | 0x09EFA:4 | 0x09F42 | 0x09F43 | +flag 0x09F3B:7 |

### FF Mode Bits
Comparing FF variants (all at same position):
- FF vs FF+async_reset: 174 bit diffs (92 arst-only, 82 shared mode bits)
- FF vs FF+sync_enable: 154 bit diffs (72 ena-only, 82 shared mode bits)
- 82 common mode bits include 0x01272-0x01285 (16 consecutive bit-4 bytes)

### Known Limitations
- Cannot place FF at arbitrary LAB positions in Quartus Lite
- ~90% of FF-related bit changes are routing, not configuration
- FF at IO/peripheral columns (X=1,2) have different CRAM structure than LAB columns

## Arithmetic Mode (Phase 2.3)

### Methodology
1. Compile 5 normal-mode LUTs at (10,10,N=6,8,10,12,14) with mask 0x8888
2. Compile 4 arithmetic + 1 normal adder at same positions (behavioral `a[3:0]+b[3:0]`)
3. Both designs vs baseline → set subtraction → arithmetic-only bits
4. Remove known LUT TT bits (from per-N pair-diffs) → pure mode configuration

### LUT TT Structure per N
Each LE at a different N has 16 unique ctrl bytes (8 pairs) but **shares data byte addresses** with other LEs at same (X,Y). The ctrl bytes select which LE is targeted; data bytes are column-wide.

| N | Ctrl range | Data range (shared) |
|---|-----------|---------------------|
| 6 | 0x13F94..0x14553 | 0x1400A..0x145C9 |
| 8 | 0x13F8E..0x145C9 | 0x1400A..0x145C9 |
| 10 | 0x13F8C..0x145C9 | 0x1400A..0x145C9 |
| 12 | 0x13F86..0x145C8 | 0x1400A..0x145C9 |
| 14 | 0x13F84..0x145C9 | 0x1400A..0x145C9 |

N-to-N ctrl spacing: ~2-6 bytes (not uniform), decreasing N → lower addresses.

### Arithmetic Mode Bits
After removing all LUT TT bits: **92 pure arithmetic/carry-chain bits** for 4-LE adder.

Split into two regions around the LUT TT area (same pattern as FF configuration):
- **Below LUT TT** (0x1323C-0x13F39): 51 bits
- **Above LUT TT** (0x14615-0x15216): 41 bits

Data byte pair spacing follows multiples of 210 bytes (matching LUT TT pair period):
420, 210, 630, 420, 210, 210, 420, 420 (below region).

These bits are NOT at known routing switch positions (LUT_ctrl+70/71) and do NOT follow the ctrl+data offset pattern (107/108 bytes). They represent a distinct CRAM structure for arithmetic mode select and carry chain configuration.

### Known Limitations
- Cannot instantiate cin from constant — must come from another LE's cout
- Behavioral synthesis required (not WYSIWYG primitive) for carry chains
- 92 bits includes both mode select and carry routing; not yet separated

## Routing Matrix (Phase 3 — Initial Findings)

### Methodology
Two connected `cycloneive_lcell_comb` primitives placed at controlled distances.
Pair-diff: two-LUT design vs single-LUT baseline at same lut1 position.
- Intra-LAB: lut1(x,y,0) → lut2(x,y,N) for N=2..30
- Intra-column: lut1(10,10,0) → lut2(10,Y,0) for all Y ≠ 10
- Intra-row: lut1(10,10,0) → lut2(X,10,0) for all X ≠ 10

### Routing Determinism
**Fully deterministic**: 5 different fitter seeds produce identical bitstreams for the same placement. The MINIMUM routing optimization level eliminates routing randomness.

### Bit Budget per Route
| Route type | Total bits vs baseline | LUT2 config | Routing |
|-----------|----------------------|-------------|---------|
| Intra-LAB (same LAB, different N) | 470-542 | ~200 | ~300 |
| Intra-column (C4, dy=1..11) | 472-630 | ~200 | ~300-430 |
| Intra-row (R4/R24, dx=1..21) | 464-608 | ~200 | ~264-408 |

### Common vs Destination-Specific Bits
From (10,10,0) as source:

| Category | Column routes | Row routes | Overlap |
|----------|--------------|------------|---------|
| Common to ALL routes | 85 | 84 | 61 |
| Column-only common | 24 | — | — |
| Row-only common | — | 23 | — |
| Per-destination unique | 36-103 | 155-292 | — |

**61 shared bits** (common to every two-LUT design from this source): lut2 LE-enable + lut1 output driver + IO path routing. Located at:
- 0x11xxx (near X=8 CRAM): 21 bits
- 0x2Axxx (near X=16 CRAM): 13 bits
- 0x56xxx-0x59xxx (right edge IO): 27 bits

**24 column-only** bits: C4/C16 column routing entry mux
**23 row-only** bits: R4/R24 row routing entry mux

### CRAM Routing Switch Structure
Routing switches use the **same CRAM column layout** as LUT truth tables, interleaved at fixed offsets.

**Routing bit-4 positions** sit at LUT_pair_ctrl + 70/71 bytes, between consecutive LUT TT pairs:
```
LUT pair 7/15 ctrl @ base+0
  Route bits @ base+70, base+71 (bit-4)
LUT pair 6/14 ctrl @ base+211
LUT pair 5/13 ctrl @ base+420
  Route bits @ base+490, base+491 (bit-4)
...repeating with 420-byte period
```

**Bit position encodes physical destination Y region** (NOT routing distance).
Verified with two source positions (Y=5 and Y=10) — 100% match for same destination:

| Bit position | Destination Y | Physical rows |
|-------------|--------------|---------------|
| bit-0 | Y=21 | Row group 7 (far top) |
| bit-1 | Y=18..19 | Row group 6 |
| bit-2 | Y=16..17 | Row group 5 |
| bit-3 | Y=12..14 | Row group 4 |
| bit-4 | Y=9..11 | Row group 3 (center) |
| bit-5 | Y=6..8 | Row group 2 |
| bit-6 | Y=3..5 | Row group 1 |
| bit-7 | Y=2 | Row group 0 (far bottom) |

**Key insight**: Bit position maps to the physical C4/C16 wire group, not the routing distance.
Same destination Y always uses the same bit position regardless of source Y. The earlier
interpretation as "distance-dependent" was an artifact of testing from a single source.

### Global Header Region (0x00020-0x0004F)
```
0x20-0x28: Device header (constant: 6A F7 F7 F7 F7 F7 F7 F3 FB)
0x29-0x34: Design-dependent (12 bytes, likely resource usage encoding)
0x35-0x48: Mostly constant (some variation in specific bytes)
0x49-0x4A: CRC/checksum (2 bytes, changes with every design modification)
0x4B-0x4F: Padding (always FF)
```
These 14 variable bytes (0x29-0x34, 0x49-0x4A) must be excluded from routing/logic analysis.

### Routing Resource Counts (from Fitter Reports)
Two-LUT designs always use exactly 9 block interconnects (IO pin routing).
C4 increases with column distance, C16 appears at dy≥4.
R4 increases with row distance.
Local interconnects = 0 even for intra-LAB — fitter uses block+C4 instead.

### Row Routing Bit Distribution (X=10 → X=dst)
Routing bits are distributed across multiple CRAM columns:
- Source column (X=10): 0-54 bits
- Destination column: 150-254 bits
- Inter-column routing channels: 150-400 bits (increases with distance)

## Bitstream Codec (Phase 2 Complete)

### LUT Truth Table Read/Write
A working bitstream codec can read and write LUT truth tables directly in RBF files:

```python
from bitstream import LutCodec
codec = LutCodec.from_db(db, x=10, y=10, n=0)

# Read TT from any RBF
mask = codec.read_tt(rbf_data, zero_data)  # → 0x8888

# Write TT into RBF (from zero baseline)
new_rbf = codec.write_tt(zero_data, 0x6996)  # XOR gate
```

**Verified 10/10 masks** including 0x8888, 0x6996, 0xFFFF, 0xAAAA, 0x5555, 0xDEAD.
Codec-generated RBFs are **bit-identical** to Quartus-compiled RBFs in all CRAM cells
(16 header/CRC differences only).

### XOR-Linear Per-Minterm Encoding
Each TT bit has:
- **1 ctrl cell**: unique discriminator (only appears in that minterm's pattern)
- **7-9 data cells**: shared with other minterms via XOR-linear algebra

Two data patterns alternate between paired TT bits:
- Type A (lo ctrl byte): data[0] bits {0,1,3,4}, data[1] bits {1,2,3}
- Type B (hi ctrl byte): data[0] bits {0,1,2,4}, data[1] bits {0,1,3,4,6}

**Note**: data byte bit assignments are Y-dependent (since data bytes are shared across Y rows). Each position requires calibration via 16 single-minterm pair-diffs (~2.5 min).

### Pair → TT Bit Mapping
```
Pair 0: TT_7 (lo byte), TT_15 (hi byte)
Pair 1: TT_6 (hi byte), TT_14 (lo byte)
Pair 2: TT_5 (lo byte), TT_13 (hi byte)
Pair 3: TT_4 (hi byte), TT_12 (lo byte)
Pair 4: TT_3 (lo byte), TT_11 (hi byte)
Pair 5: TT_2 (hi byte), TT_10 (lo byte)
Pair 6: TT_1 (lo byte), TT_9 (hi byte)
Pair 7: TT_0 (hi byte), TT_8 (lo byte)
```
Formula: `pair = 7 - (bit % 8)`, byte side alternates.

## Pipeline Performance
- Single compile (map+fit+asm+cpf): ~9-10 seconds for minimal LUT design
- Throughput: ~360-400 designs/hour
- Database: SQLite with indexed bit mappings

## Methodology
1. `cycloneive_lcell_comb` primitive with explicit `lut_mask` parameter
2. `set_location_assignment LCCOMB_Xx_Yy_Nn -to "lut_inst"` for precise placement
3. Compare mask=0x0000 vs mask=0xFFFF at each position (pair-diff method)
4. XOR-linear model verified with multi-bit masks (0x8888, 0x6996)
