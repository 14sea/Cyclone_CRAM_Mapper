# EP4CE6 Bitstream Reverse Engineering: Automated Black-Box Fuzzing — Feasibility Analysis and Implementation Plan

## Context

**Goal**: Fully reverse-engineer the bitstream (.rbf) format of the Altera Cyclone IV EP4CE6F17C8, building a complete bit-mapping dictionary from logic configuration through the routing matrix, ultimately enabling integration with the open-source toolchain (Yosys + NextPNR).

### Available Infrastructure
- **Quartus 21.1 Lite**: `$HOME/intelFPGA_lite/21.1/` (quartus_map/fit/asm/cpf all available)
- **Hardware**: Heijin AX301 dev board, EP4CE6F17C8 (6,272 LEs, 392 LABs, 30 DSP multipliers)
- **Existing RBF files**: riscv_tpu_demo (368,011 bytes), bitcoin_miner, led_funcmod — all identical size
- **openFPGALoader**: compiled from source, supports EP4CE6
- **Python environment**: pyusb, pyserial, numpy
- **Cyclone IV Handbook**: `docs/cyclone4-handbook.pdf` (Cyclone IV Handbook)
- **Working directory**: project root (created, initially empty)

### Known RBF Format Facts
- Fixed size: **368,011 bytes = 2,944,088 bits**
- Preamble: 32 bytes 0xFF | Config data: 367,920 bytes | Postamble: 59 bytes 0xFF
- Two completely different designs (TPU vs Bitcoin) differ by ~212,556 bits (~7.2%)
- Must be generated with `quartus_cpf -c -o bitstream_compression=off`; do NOT use sof2rbf.py

### EP4CE6 Chip Geometry
- **392 LABs**, each containing **16 LEs**
- LAB X coordinates: 22 values [3,4,6,7,8,10,11,12,13,16,17,18,19,21,22,23,24,25,26,28,29,31]
- LAB Y coordinates: 18 values [2-14, 16-19, 21]
- LE N indices: even numbers [0,2,4,...,30]
- Node naming: `LCCOMB_X<col>_Y<row>_N<le_idx>` (combinational logic), `LCFF_X<col>_Y<row>_N<le_idx>` (registers)
- Routing resources: Block 32,401 / Local 10,320 / C4 21,816 / C16 1,326 / R4 28,186 / R24 1,289

---

## Feasibility Summary

| Phase | Feasibility | Risk | Estimated Compilations |
|-------|-------------|------|----------------------|
| Phase 1: Fuzzing pipeline | **High** ✓ | Low — all tools verified headless | ~50 (infrastructure) |
| Phase 2: Logic configuration | **High** ✓ | Low — pure diff analysis | ~7,500 (~24 hr) |
| Phase 3: Routing matrix | **Medium-High** | Medium — no direct routing control API | ~50,000–100,000 |
| Phase 4: Open-source integration | **Medium** | Medium — depends on Phase 2+3 completeness | Primarily software engineering |

**Estimated compilation time**: minimal designs ~8–12 sec (map+fit+asm+cpf), ~300–450 per hour.

---

## Phase 1: Automated Black-Box Fuzzing Pipeline

### Directory Structure
```
./
├── fuzz/
│   ├── config.py          # EP4CE6 constants (LAB coordinates, paths, pins)
│   ├── verilog_gen.py     # Minimal Verilog generator
│   ├── qsf_gen.py         # QSF + placement constraint generator
│   ├── compile.py         # Quartus headless compilation driver
│   ├── rbf_diff.py        # Binary diff engine
│   ├── database.py        # SQLite bit-mapping database
│   ├── runner.py          # Fuzzing campaign orchestrator
│   └── analyze.py         # Result analysis and visualization
├── templates/
│   └── fuzz_top.v         # Verilog template
├── results/
│   ├── rbf/               # Collected .rbf files
│   └── ep4ce6_bitdb.sqlite
└── work/                  # Quartus temporary build directory
```

### Core Components

#### 1. Verilog Generator (`verilog_gen.py`)
Generates a minimal design containing only a single LUT4, controlling logic behavior through parameterized truth-table expressions:

```verilog
module fuzz_top(
    input  wire A, B, C, D,
    output wire Q
);
    wire lut_out /* synthesis keep */;
    assign lut_out = {EXPRESSION};  // e.g. A & B, A | B, A ^ B
    assign Q = lut_out;
endmodule
```

Expressions for the 16 basic truth-table bits:
- Bit 0: `~A & ~B & ~C & ~D`
- Bit 1: `~A & ~B & ~C & D`
- ... (one expression per minterm)
- Bit 15: `A & B & C & D`

#### 2. QSF Generator (`qsf_gen.py`)
Key QSF settings:
```tcl
# Device settings
set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top

# Disable all optimization (prevent Quartus from altering our logic)
set_global_assignment -name AUTO_RAM_RECOGNITION OFF
set_global_assignment -name AUTO_DSP_RECOGNITION OFF
set_global_assignment -name AUTO_SHIFT_REGISTER_RECOGNITION OFF
set_global_assignment -name ALLOW_REGISTER_RETIMING OFF
set_global_assignment -name SYNTH_TIMING_DRIVEN_SYNTHESIS OFF

# Force placement to specified LE
set_location_assignment LCCOMB_X{x}_Y{y}_N{n} -to "lut_out"

# I/O pins (using available GPIO on AX301)
set_location_assignment PIN_E1 -to CLK
set_location_assignment PIN_M2 -to A
...
```

#### 3. Compilation Driver (`compile.py`)
```bash
quartus_map --read_settings_files=on --write_settings_files=off fuzz_proj -c fuzz_proj
quartus_fit --read_settings_files=on --write_settings_files=off fuzz_proj -c fuzz_proj
quartus_asm --read_settings_files=on --write_settings_files=off fuzz_proj -c fuzz_proj
quartus_cpf -c -o bitstream_compression=off output_files/fuzz_proj.sof fuzz_proj.rbf
```

**Key optimization**: When only the QSF placement constraint changes (Verilog unchanged), skip `quartus_map` and run only `quartus_fit` + `quartus_asm` + `quartus_cpf`.

#### 4. Node Name Discovery (Two-Step Method)
1. First compilation without placement constraints — let Quartus place freely
2. Use `quartus_cdb` Tcl API: `get_names -filter * -node_type comb` to find the actual LUT node name
3. All subsequent compilations use the discovered node name in `set_location_assignment`

#### 5. Diff Engine (`rbf_diff.py`)
Compares two RBF files bit by bit, outputting all flipped bits as (byte_offset, bit_position, direction).

#### 6. SQLite Database (`database.py`)
Schema:
```sql
CREATE TABLE bit_mapping (
    x INTEGER, y INTEGER, n INTEGER,
    feature TEXT,  -- 'lut_bit_0', 'lut_bit_1', ..., 'ff_enable', 'route_c4_xxx'
    byte_offset INTEGER,
    bit_position INTEGER,
    PRIMARY KEY (x, y, n, feature, byte_offset, bit_position)
);
```

---

## Phase 2: Cracking Logic Configuration

### Step 2.1: LUT Truth-Table Bits (First Results)
1. Compile empty design → `baseline.rbf`
2. Place 16 different minterm designs at a fixed location (e.g. X=10, Y=10, N=0)
3. Diff each against baseline → find bitstream positions that control each truth-table bit
4. Verify: compile `A & B` (mask=0x8888), confirm diff equals union of bits 3, 7, 11, 15

**Expected result**: 16 bits per LE directly encoding the truth table.

### Step 2.2: LAB Grid Mapping
1. Fix a single function (`A & B`)
2. Place it sequentially at all 6,272 LE positions
3. Truth-table bits appear at different bitstream offsets
4. Plot offset vs (X, Y, N) → discover the address-mapping formula

**Expected structure**: Bitstream organized by column; each LAB column maps to a contiguous region.

### Step 2.3: LE Mode Bits
- Normal mode (combinational LUT4)
- Arithmetic mode (carry chain)
- Register modes (synchronous/asynchronous clear/load)
- Compile each mode once at a known location; diff to find mode-control bits

---

## Phase 3: Routing Matrix (Biggest Challenge)

### Core Difficulty
Quartus Lite has **no** direct routing-path control API. You cannot specify "signal X must use C4 wire #37."

### Indirect Control Strategies

**Strategy A: Distance-Based Inference**
- Place driver LUT at (X1,Y1) and load LUT at (X2,Y2)
- Control distance to force specific routing resource types:
  - Adjacent LAB → direct links
  - Same column, 1–4 rows → C4 wires
  - Same column, 5–16 rows → C16 wires
  - Same row, 1–4 columns → R4 wires
  - Same row, 5–24 columns → R24 wires

**Strategy B: Multi-Fanout**
- One driver + multiple strategically placed loads → force specific switch box
- Diff against single-load design → isolate extra routing bits

**Strategy C: `ROUTE_REGION` Constraints**
- Restrict routing to a specific area, indirectly forcing specific resources

**Strategy D: Post-Fit Tcl Analysis**
- After compilation, use `quartus_cdb` to read actual routing from fitter database
- Correlate routing report with bitstream diff

### Risk: Routing Non-Determinism
- Identical placement may produce different routing paths
- Mitigation: `quartus_fit --seed=N` controls the random seed
- Mitigation: `ROUTER_TIMING_OPTIMIZATION_LEVEL MINIMUM`
- Statistical analysis needed to resolve ambiguous bits

---

## Phase 4: Open-Source Tool Integration (Long-Term)

### FASM/Bitgen Tool
- Input: FASM text file (listing all enabled features)
- Lookup: find corresponding bits from SQLite dictionary
- Output: 368,011-byte RBF file

### NextPNR Backend
- Requires: Cyclone IV architecture description (C++), packer, place-and-route adapter
- Reference: NextPNR's iCE40 and ECP5 backends, each several thousand lines of C++

---

## Prior Art

| Project | Target | Method | Relevance |
|---------|--------|--------|-----------|
| Project IceStorm | Lattice iCE40 | icecube2 + fuzzing | High — identical methodology |
| Project X-Ray | Xilinx 7-series | Vivado + specimen fuzzing | High — FASM format reference |
| Project Mistral | Altera Cyclone V | quartus_cdb + Tcl | **Very High** — same chip family |
| Project Trellis | Lattice ECP5 | Diamond + fuzzing | Medium — routing strategy reference |

**Mistral (Cyclone V)** is the most relevant: same Altera family, similar CRAM organization, and the author also uses the `quartus_cdb` Tcl API for post-fit analysis.

---

## Recommended Immediate Actions (Phase 1 Implementation Order)

1. **Create project skeleton**: `./fuzz/` directory structure
2. **Write `config.py`**: hard-code all LAB coordinates and device constants
3. **Write `verilog_gen.py`**: parameterized LUT4 Verilog generation
4. **Write `qsf_gen.py`**: generate QSF with placement constraints
5. **Write `compile.py`**: drive Quartus headless compilation
6. **First experiment**: empty baseline + 16 single-bit truth-table designs → verify we can find 16 LUT TT bits
7. **Write `rbf_diff.py` + `database.py`**: store results in SQLite
8. **Expand to full LAB**: 16 LE × 16 functions = 256 compilations
9. **Expand to full chip**: 392 LAB × 1 function = 6,272 compilations → build complete grid map

### Key Reference Files
- `riscv_tpu_demo.qsf` (external) — QSF reference
- `AX301.tcl` (external) — AX301 pin assignments
- `docs/cyclone4-handbook.pdf` (Cyclone IV Handbook) — Cyclone IV architecture handbook

### Verification Milestones
1. **Milestone 1**: Successfully place a LUT at a specified coordinate and compile to RBF
2. **Milestone 2**: Two different LUT functions differ by only a small number of bits
3. **Milestone 3**: Each of the 16 minterms maps to an independent set of truth-table bits
4. **Milestone 4**: Same function at different LE positions → truth-table bits at different offsets
5. **Final validation**: Manually edit truth-table bits in RBF → flash to hardware → observe changed logic behavior
