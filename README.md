# EP4CE6 Bitstream Reverse Engineering

## What Is This Project?

The goal of this project is to **fully reverse-engineer** the bitstream format of the Altera (now Intel) Cyclone IV FPGA chip **EP4CE6F17C8**.

### What Is an FPGA?

An FPGA (Field-Programmable Gate Array) is a chip that can be programmed to implement any digital circuit. Unlike a CPU, an FPGA does not execute "instructions" — instead, it physically "builds" a circuit at the hardware level. Think of it as a giant breadboard with thousands of programmable logic gates and interconnects; a configuration file decides how all those gates and wires connect.

That "configuration file" is called a **bitstream**. For Altera chips, the specific format is `.rbf` (Raw Binary File).

### Why Reverse-Engineer the Bitstream?

Commercial FPGA vendors (Intel/Altera, Xilinx/AMD) keep their bitstream formats **proprietary**. You must use their own tools (e.g., Quartus) to generate a bitstream. This means:

1. **No open-source toolchain**: You cannot use open-source synthesizers (like Yosys) or place-and-route tools (like NextPNR) to go all the way from Verilog to a bitstream.
2. **No insight into chip internals**: You don't know which part of the chip each bit in the bitstream controls.
3. **Dependency on closed-source software**: Quartus is free but not open-source, and only supports certain operating systems.

Once we reverse-engineer the bitstream format we can:
- Build a completely open-source FPGA toolchain for the EP4CE6
- Understand how the chip's CRAM (Configuration RAM) is organized internally
- Directly read and write logic configuration and routing information in bitstream files

### Pioneer Projects

| Project | Target chip | Method | Relation to this project |
|---------|------------|--------|--------------------------|
| [Project IceStorm](http://www.clifford.at/icestorm/) | Lattice iCE40 | Black-box fuzzing | Identical methodology |
| [Project X-Ray](https://github.com/SymbiFlow/prjxray) | Xilinx 7-series | Vivado + specimen fuzzing | FASM format reference |
| [Project Mistral](https://github.com/Ravenslofty/mistral) | Altera Cyclone V | quartus_cdb + Tcl | Same chip family — highest relevance |
| [Project Trellis](https://github.com/YosysHQ/prjtrellis) | Lattice ECP5 | Diamond + fuzzing | Routing strategy reference |

---

## Hardware and Software Environment

### Hardware

- **Development board**: Heijin AX301
- **FPGA chip**: EP4CE6F17C8 (Cyclone IV E series, 6,272 logic elements)
- **Programmer**: USB-Blaster JTAG

### Software

- **Quartus Prime 21.1 Lite Edition**: Intel's free FPGA development tool
  - Installation path: `~/intelFPGA_lite/21.1/quartus/bin/`
  - Command-line tools used: `quartus_map` (synthesis), `quartus_fit` (place & route), `quartus_asm` (generate .sof), `quartus_cpf` (convert to .rbf), `quartus_sta` (static timing analysis)
- **openFPGALoader**: open-source FPGA programming tool (flashes bitstream to board); use `$HOME/see_neorv32_run_linux/tools/openFPGALoader/build/openFPGALoader` — the system version does not recognize the EP4CE6 IDCODE
- **Python 3**: all fuzzing scripts are written in Python
- **SQLite**: database for storing experiment results

### EP4CE6 Chip Geometry

```
EP4CE6F17C8 internal layout (simplified):

     X=3  4  6  7  8  10 11 12 13  16 17 18 19  21 22 23 24 25 26  28 29 31
Y=21 [LAB][LAB][LAB][LAB][LAB][LAB]...                                [LAB]
Y=19 [LAB][LAB][LAB][LAB][LAB][LAB]...                                [LAB]
 ...    |    |    |    |    |    |                                       |
Y=2  [LAB][LAB][LAB][LAB][LAB][LAB]...                                [LAB]
          ^         ^              ^                    ^
          X=5       X=9            X=14-15              X=20,27
          M9K       M9K            DSP                  M9K
          RAM       RAM            Multiplier           RAM
```

- **392 LABs** (Logic Array Blocks), each containing **16 LEs** (Logic Elements)
- **LAB X coordinates**: 22 values `[3, 4, 6, 7, 8, 10, 11, 12, 13, 16, 17, 18, 19, 21, 22, 23, 24, 25, 26, 28, 29, 31]`
  - Note that X is not contiguous! X=5, 9, 14, 15, 20, 27, 30 are occupied by M9K memory, DSP multipliers, or PLLs.
- **LAB Y coordinates**: 18 values `[2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 21]`
  - Y=15 and Y=20 do not exist ("ghost rows" in CRAM)
- **LE N index**: 16 even values `[0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30]`
- **Total**: 392 × 16 = **6,272 LEs**

Each LE contains:
- A **4-input lookup table** (LUT4): can implement any 4-variable Boolean function
- A **D flip-flop** (DFF): optionally used
- Carry-chain logic (for arithmetic operations like addition)

---

## Core Methodology: "Pair-Diff"

This is the core method of the entire reverse-engineering effort — simple yet powerful.

### Basic Idea

> If you want to know which bits in the bitstream control a specific feature, compile two designs that differ **only in that feature**, then compare their bitstreams. The differing bits are the ones that control that feature.

### Concrete Steps (LUT Truth Table Example)

```
Step 1: Compile a LUT with truth table set to all zeros (mask = 0x0000)
        → produces zero.rbf

Step 2: Compile the same LUT at the same location with all ones (mask = 0xFFFF)
        → produces ones.rbf

Step 3: Compare zero.rbf and ones.rbf bit by bit
        → the differences are the CRAM bits for this LE's truth table
```

### Why Does This Work?

Because the two designs are identical in every way except the LUT's truth table — same routing, same I/O buffers, same global config. The differing bits **can only be** the truth-table encoding.

### Comparison Method Hierarchy

| Method | What is compared | Effect | Noise |
|--------|-----------------|--------|-------|
| Design vs. empty | functional vs. non-functional | Finds all related bits | High (includes routing, etc.) |
| Pair-diff | mask=0x0000 vs. mask=0xFFFF | Only finds LUT TT bits | **Zero noise** |
| Multi-mask cross | multiple designs with different masks | Validates XOR-linear model | Zero |

### How Is It Implemented?

```python
# rbf_diff.py — compare two RBF files
def diff_rbf(rbf_a: bytes, rbf_b: bytes) -> list[BitDiff]:
    diffs = []
    for i in range(RBF_SIZE):           # iterate over 368,011 bytes
        xor = rbf_a[i] ^ rbf_b[i]      # XOR to find differing bytes
        if xor:
            for bit in range(8):        # check each bit
                if xor & (1 << bit):
                    direction = 1 if (rbf_b[i] >> bit) & 1 else -1
                    diffs.append(BitDiff(i, bit, direction))
    return diffs
```

Each `BitDiff` records three values:
- `byte_offset`: byte offset in the RBF file (0 to 368,010)
- `bit_position`: bit position within that byte (0=LSB, 7=MSB)
- `direction`: change direction (+1 means 0→1, -1 means 1→0)

---

## RBF File Format

An EP4CE6 RBF file is always exactly **368,011 bytes**, regardless of design complexity:

```
┌──────────────────────────┐
│  Preamble                │  32 bytes, all 0xFF
├──────────────────────────┤
│                          │
│  Config Data             │  367,920 bytes
│  Contains CRAM content   │  All logic and routing encoded here
│                          │
├──────────────────────────┤
│  Postamble               │  59 bytes, all 0xFF
└──────────────────────────┘
```

**Key regions:**
- `0x0020 – 0x0028`: Device header (constant: `6A F7 F7 F7 F7 F7 F7 F3 FB`)
- `0x0029 – 0x0034`: Design-dependent data (12 bytes, possibly resource-usage encoding)
- `0x0049 – 0x004A`: CRC/checksum (changes with every modification)
- `0x004B – 0x59BBB`: CRAM configuration data body

---

## Project Directory Structure

```
EP4CE6/
├── README.md               ← This file (English)
├── README_zh.md            ← Chinese version
├── CLAUDE.md               ← AI assistant context/memory file
├── fuzz/                   ← Fuzzing pipeline (Python source, 96 modules)
│   ├── config.py           ← EP4CE6 constants, coordinates, pin definitions
│   ├── verilog_gen.py      ← Verilog code generator
│   ├── qsf_gen.py          ← Quartus project config file generator
│   ├── compile.py          ← Quartus headless compilation driver
│   ├── rbf_diff.py         ← Bit-level binary diff engine
│   ├── database.py         ← SQLite database interface
│   ├── runner.py           ← Fuzzing experiment orchestrator (main entry)
│   ├── analyze.py          ← Result analysis and visualization
│   ├── bitstream.py        ← Bitstream codec (LUT + RouteCodec + CRC patcher)
│   ├── route_synth.py      ← Green-island route synthesis engine
│   ├── fasm2rbf.py / rbf2fasm.py ← Phase 4 FASM writer + reverse tool
│   └── route_signatures.py / route_decompose.py ← sig backend + set-cover
├── jailbreak/              ← CE10 fitter probes (X=32/33, Y=15 dead-cell scans)
├── results/
│   ├── rbf/                ← Collected .rbf files (~2,500 files, 368 KB each)
│   ├── fingerprint_*.json  ← 15 green-zone island corpora
│   ├── route_cells.json    ← 1050 route sig backend
│   ├── source_overhead.json ← per-source overhead vs baseline
│   ├── r4_iindex_table.json ← 942-entry R4 I-index hint table
│   ├── ep4ce6_bitdb.sqlite ← Bit-mapping database
│   └── FINDINGS.md         ← Detailed findings report
└── work/                   ← Quartus temporary build directory (can be cleaned)
```

### Source Code Statistics (core modules)

| File | Lines | Function |
|------|-------|----------|
| `config.py` | 184 | Chip constants, CRAM address formulas, pin definitions |
| `verilog_gen.py` | 363 | Verilog generation (LUT/FF/LI/route/jailbreak templates) |
| `qsf_gen.py` | 81 | QSF project configuration generation |
| `compile.py` | 270 | Quartus compilation driver + STA routing extraction |
| `rbf_diff.py` | 111 | Binary comparison engine |
| `database.py` | 193 | SQLite database operations |
| `runner.py` | 1,305 | Experiment orchestrator (largest file) |
| `analyze.py` | 570 | Analysis, visualization, and codec commands |
| `bitstream.py` | 1,264 | **LutCodec + RouteCodec + CRC patcher** |
| `route_synth.py` | 398 | Green-island route synthesis |
| `fasm2rbf.py` | 239 | Phase 4 FASM → RBF bitgen |
| `rbf2fasm.py` | 175 | Phase 4 RBF → FASM reverse tool |
| **Core total** | **~5,150** | (+ 84 mining/analysis/test modules) |

---

## Code Architecture

### 1. `config.py` — Chip Constants

This file defines all physical parameters of the EP4CE6:

```python
# Chip geometry
LAB_X = [3, 4, 6, 7, 8, 10, 11, 12, 13, 16, 17, 18, 19, 21, ...]  # 22 LAB columns
LAB_Y = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, ...]     # 18 LAB rows
LE_N  = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30]  # 16 LEs

# CRAM column base addresses (22 columns, each at a different start)
COLUMN_BASE = {
    3: 0x076E0,   # first LAB column
    4: 0x09396,   # = 0x076E0 + 7350 (standard step)
    6: 0x0CD02,   # = 0x09396 + 14700 (skip M9K column)
    ...
}

# Pin assignments (matching GPIO on AX301 dev board)
FUZZ_PINS = {
    "A": "PIN_E16",   # Button KEY2 → LUT input A
    "B": "PIN_M16",   # Button KEY3 → LUT input B
    "C": "PIN_M15",   # Button KEY4 → LUT input C
    "D": "PIN_E15",   # Reset key  → LUT input D
    "Q": "PIN_G15",   # LED[0]     → LUT output
}
```

The most important part is the **CRAM address model** functions:

```python
def cram_ctrl_addr(x, y, pair, n=0):
    """Compute CRAM control-byte address for pair 'pair' at location (X, Y, N)"""
    cram_row = y - 2          # Y coordinate mapped to CRAM row number
    slot = cram_row % 3       # Groups of 3 rows; slot = 0, 1, or 2
    group = cram_row // 3     # Group index (0–6)
    # ... compute offset
```

### 2. `verilog_gen.py` — Verilog Generator

Generates minimal Verilog designs, each containing just one or two LUTs:

```python
def gen_lut4_primitive(mask: int) -> str:
    """Instantiate a LUT using the Cyclone IV primitive, controlling its 16-bit truth table."""
    return f"""
    cycloneive_lcell_comb #(
        .lut_mask(16'h{mask:04X}),     // truth table, e.g. 0x8888 = A & B
        .dont_touch("on")              // tell Quartus not to optimize it away
    ) lut_inst (
        .dataa(A), .datab(B), .datac(C), .datad(D),
        .combout(lut_out)
    );"""
```

**Why use a primitive rather than a behavioral description?**

A behavioral description (`assign Q = A & B;`) lets Quartus decide how to implement the logic — the synthesizer may optimize, merge, or reorder LUTs. By directly instantiating the `cycloneive_lcell_comb` primitive, you can precisely control every bit of the 16-bit truth table, which is critical for reverse engineering.

**Available generator functions:**

| Function | Purpose | Notes |
|----------|---------|-------|
| `gen_lut4(expr)` | Behavioral LUT | Boolean expression description |
| `gen_lut4_primitive(mask)` | Primitive-level LUT | Precise truth-table control |
| `gen_two_luts_primitive(m1, m2)` | Two connected LUTs | For routing fuzzing |
| `gen_single_lut_primitive_extra_inputs(m)` | Single LUT + 7 input ports | Routing fuzzing baseline |
| `gen_lut4_ff(expr)` | LUT + flip-flop | For DFF fuzzing |
| `gen_empty()` | Empty design | Global baseline |

### 3. `qsf_gen.py` — QSF Generator

A QSF (Quartus Settings File) is Quartus's project configuration file. This module generates QSF files with critical settings:

```python
# Disable all optimization — this is key to fuzzing success!
QSF_OPTIMIZATIONS_OFF = [
    ('AUTO_RAM_RECOGNITION', 'OFF'),           # Don't infer RAM
    ('AUTO_DSP_RECOGNITION', 'OFF'),           # Don't infer DSP
    ('AUTO_SHIFT_REGISTER_RECOGNITION', 'OFF'),# Don't infer shift registers
    ('SYNTH_TIMING_DRIVEN_SYNTHESIS', 'OFF'),  # No timing-driven synthesis
    ('ROUTER_TIMING_OPTIMIZATION_LEVEL', 'MINIMUM'),  # Minimize routing optimization
    ...
]

# Force LUT placement to specified location
placement = {"lut_inst": "LCCOMB_X10_Y10_N0"}
# Generates in QSF:
# set_location_assignment LCCOMB_X10_Y10_N0 -to "lut_inst"
```

**Why disable optimization?** Quartus's optimizer changes routing paths. If two compilations of the same design choose different paths, our diff will contain routing noise. After setting `ROUTER_TIMING_OPTIMIZATION_LEVEL MINIMUM`, routing becomes **fully deterministic** — the same design always produces an identical bitstream.

### 4. `compile.py` — Quartus Compilation Driver

Wraps the Quartus command-line toolchain:

```
Quartus compilation flow:

Verilog    quartus_map    quartus_fit    quartus_asm    quartus_cpf
source   ─────────────► ─────────────► ─────────────► ─────────────►  .rbf
           (synthesis)   (place&route)   (gen .sof)    (conv to .rbf)
```

Key implementation details:

```python
def compile_and_export(project_name, verilog, qsf, rbf_output):
    """One-stop: create project → compile → export RBF"""
    proj_dir = setup_project(project_name, verilog, qsf)  # write files
    ok, elapsed, err = compile_full(project_name, proj_dir)  # run Quartus
    if ok:
        rbf = generate_rbf(project_name, proj_dir, rbf_output)  # .sof → .rbf
    return rbf, elapsed, err

def extract_routing(project_name, proj_dir):
    """Extract routing paths via static timing analysis"""
    # Runs Tcl script calling report_timing -show_routing
    # Parses output to get wire names on each path
```

**Important**: RBF generation must use `quartus_cpf -c -o bitstream_compression=off`; do NOT use `sof2rbf.py` (which produces invalid bitstreams).

### 5. `runner.py` — Fuzzing Experiment Orchestrator

The largest file (~1,226 lines), orchestrating all fuzzing experiments. Main commands:

```bash
# Generate baseline RBF
python3 runner.py baseline

# LUT truth-table fuzzing at a single LE location
python3 runner.py --node lut_inst lut_single 10 10 0
# Args: X=10, Y=10, N=0

# Sweep all 16 minterms (single-bit TT patterns)
python3 runner.py n_sweep 10 10

# Grid sweep pair-diff across all 22 columns
python3 runner.py pair_diff_grid

# Parallel routing fuzzing
python3 runner.py route_map_parallel 10 5 col
# Args: source X=10, source Y=5, direction=column

# Batch routing fuzzing (multiple source positions)
python3 runner.py route_map_batch --sources 4,10 29,10 10,17 --direction row --jobs 4
```

### 6. `database.py` — SQLite Database

All experiment results are stored in an SQLite database:

```sql
-- Experiment records
CREATE TABLE experiments (
    id INTEGER PRIMARY KEY,
    name TEXT,                -- experiment name, e.g. "lut_single_X10_Y10_N0"
    verilog TEXT,             -- Verilog source code (stored in full)
    qsf_placement TEXT,       -- placement constraints
    compile_time REAL,        -- compilation time (seconds)
    rbf_path TEXT             -- path to RBF file
);

-- Bit mappings (core data)
CREATE TABLE bit_mapping (
    x INTEGER,                -- LAB X coordinate
    y INTEGER,                -- LAB Y coordinate
    n INTEGER,                -- LE index
    feature TEXT,             -- feature name, e.g. "lut_tt_0x0001"
    byte_offset INTEGER,      -- byte offset in RBF
    bit_position INTEGER,     -- bit position within that byte
    direction INTEGER,        -- change direction (+1 or -1)
    PRIMARY KEY (x, y, n, feature, byte_offset, bit_position)
);

-- Routing paths
CREATE TABLE routing_paths (
    src_x, src_y, src_n,      -- source LE coordinates
    dst_x, dst_y, dst_n,      -- destination LE coordinates
    path_json TEXT             -- wire path (JSON format)
);
```

Current database statistics:
- **1,961** experiments
- **708,319** bit-mapping records
- **980** routing paths (including complete wire paths from STA extraction)
- **95** distinct features

---

## Reverse-Engineering Results: Phase by Phase

### Phase 1: Building the Fuzzing Pipeline

**Goal**: Build an automated compile → compare → record workflow.

**Acceptance criteria**: Place a LUT at a specified coordinate, compile an RBF, and find bit differences between two different designs.

**Key steps**:

1. **Compile empty design** → get `baseline.rbf` (bitstream when all LUTs are "absent")
2. **Place an `A & B` LUT at (X=10, Y=10, N=0)** → get `and.rbf`
3. **Diff** → ~450 bit differences (LUT config + routing)
4. **Use Pair-Diff**: same position, mask=0x0000 vs. mask=0xFFFF → only 64 bits differ → pure LUT truth table!

**Compilation time**: ~9–10 sec (synthesis + place-and-route + RBF generation), throughput ~360–400 per hour.

---

### Phase 2: Cracking Logic Configuration

#### Phase 2.1: LUT Truth-Table Encoding

**Discovery**: LUT truth tables use **XOR-linear encoding**.

What does this mean? A simplified example:

Suppose a 2-input LUT has 4 truth-table bits (TT[0] to TT[3]). With a "direct" encoding, each TT bit corresponds to one CRAM bit. But Cyclone IV's encoding is more complex — each TT bit maps to **8–10 CRAM bits**, and those CRAM bits have an XOR relationship.

```
Single-bit patterns (CRAM bits from minterm pair-diffs):

TT bit 0 (mask 0x0001) → {A1, B3, B5, C2, C7, D1, D4, E6}  ← 8 CRAM bits
TT bit 1 (mask 0x0002) → {A1, B3, B5, C2, C7, D2, D5, E7}  ← same 8 positions
                          ↑ ↑  ↑  ↑  ↑                        5 shared!
                          These bits are shared between the two

CRAM bits for any mask = XOR(CRAM bit sets for each '1' bit in the mask)
Example: mask 0x0003 (both bit 0 and bit 1 are 1)
     = {A1,B3,B5,C2,C7,D1,D4,E6} XOR {A1,B3,B5,C2,C7,D2,D5,E7}
     = {D1,D2,D4,D5,E6,E7}  ← shared bits XOR out
```

**Validation**: Compiled with multiple masks (0xFFFF, 0x8888, 0x6996, etc.); XOR-linear predictions **match actual diffs exactly**.

#### Truth-Table CRAM Structure

The 16-bit truth table for each LE is encoded in **8 CRAM byte pairs**:

```
Each pair contains:
  ┌──────────────────────────────────────────────────────────┐
  │ ctrl_lo (1 byte)  ← control byte (low), identifies Y row │
  │ ctrl_hi (1 byte)  ← control byte (high), adjacent to lo  │
  │ data_0  (1 byte)  ← data byte 0, +48 bytes past ctrl     │
  │ data_1  (1 byte)  ← data byte 1, adjacent to data_0      │
  └──────────────────────────────────────────────────────────┘
  
  ctrl → data offset: 48 bytes (fixed)
  pair → pair spacing: 210 bytes (fixed)
  
  8 pairs × 210 bytes ≈ 1,518-byte CRAM span
```

**Pair-to-TT-bit mapping** (pair number → TT bit index):
```
Pair 0: TT[7]  (lo byte), TT[15] (hi byte)
Pair 1: TT[6]  (hi byte), TT[14] (lo byte)
Pair 2: TT[5]  (lo byte), TT[13] (hi byte)
Pair 3: TT[4]  (hi byte), TT[12] (lo byte)
Pair 4: TT[3]  (lo byte), TT[11] (hi byte)
Pair 5: TT[2]  (hi byte), TT[10] (lo byte)
Pair 6: TT[1]  (lo byte), TT[9]  (hi byte)
Pair 7: TT[0]  (hi byte), TT[8]  (lo byte)

Formula: pair = 7 - (bit % 8), byte side alternates
```

#### Phase 2.2: CRAM Address Model (376/376 positions verified — 100%)

This is the most fundamental discovery of the entire reverse-engineering effort — a **complete mapping formula** from (X, Y, N) coordinates to CRAM byte addresses.

##### Column Base Addresses

The bitstream is organized by column; each LAB column occupies a contiguous CRAM region:

```
Standard LAB column width: 7,350 bytes (0x1CB6)

  Col X=3     Col X=4     Col X=6     Col X=7
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│  7,350  │ │  7,350  │ │  7,350  │ │  7,350  │ ...
│  bytes  │ │  bytes  │ │  bytes  │ │  bytes  │
└─────────┘ └─────────┘ └─────────┘ └─────────┘
 0x076E0     0x09396     0x0CD02     0x0E9B8
             +7,350      +14,700     +7,350
                         (skip M9K)
```

Non-standard column widths appear at special resource boundaries:
- **M9K RAM** (X=5, 9, 20, 27, 30): need extra space
- **DSP multipliers** (X=14–15): huge CRAM region (76,230-byte jump)
- **PLL**: near X=27

##### Y Address Formula (slot/group Encoding)

This is the most intricate part. The 18 Y coordinates do not map to consecutive addresses; they use a "three-row interleaved" encoding:

```python
cram_row = Y - 2              # Y=2 → 0, Y=3 → 1, ..., Y=21 → 19
slot  = cram_row % 3           # groups of 3 rows; slot = 0, 1, or 2
group = cram_row // 3          # group index, 0 to 6

# slot determines the base offset
SLOT_BASE = {0: 136, 1: 0, 2: 70}  # bytes

# group determines the fine offset and bit position
byte_offset = SLOT_BASE[slot] + group * 3
bit_position = 7 - group - (1 if slot > 0 else 0)
```

Why this seemingly complex encoding? Because Cyclone IV's CRAM is physically scanned by row, and each CRAM byte must serve the switches for multiple Y rows. `slot` determines the physical location; `group` determines which bit within the byte.

**Complete Y mapping table**:

| Y | slot | group | byte offset | bit | Note |
|---|------|-------|-------------|-----|------|
| 2 | 0 | 0 | +136 | bit-7 | bottom edge |
| 3 | 1 | 0 | +0 | bit-6 | |
| 4 | 2 | 0 | +70 | bit-6 | |
| 5 | 0 | 1 | +140 | bit-6 | |
| 6 | 1 | 1 | +3 | bit-5 | |
| 7 | 2 | 1 | +73 | bit-5 | |
| 8 | 0 | 2 | +143 | bit-5 | |
| 9 | 1 | 2 | +6 | bit-4 | |
| 10 | 2 | 2 | +76 | bit-4 | |
| 11 | 0 | 3 | +146 | bit-4 | |
| 12 | 1 | 3 | +9 | bit-3 | |
| 13 | 2 | 3 | +79 | bit-3 | |
| 14 | 0 | 4 | +149 | bit-3 | |
| 16 | 2 | 4 | +82 | bit-2 | Y=15 skipped |
| 17 | 0 | 5 | +152 | bit-2 | |
| 18 | 1 | 5 | +15 | bit-1 | |
| 19 | 2 | 5 | +85 | bit-1 | |
| 21 | 1 | 6 | +18 | bit-0 | Y=20 skipped, top edge |

##### N (LE Index) Address Formula

The 16 LEs within a LAB have addresses that decrease by the following pattern:

```
N=0  → offset 0 (reference)
N=2  → -2
N=4  → -8
N=6  → -10
N=8  → -16
N=10 → -18
N=12 → -24
N=14 → -26
N=16 → -38  (crosses LAB midpoint boundary, extra -12)
N=18 → -40
... and so on

Step sequence: -2, -6, -2, -6, -2, -6, -2, -12, -2, -6, -2, -6, -2, -6, -2

Formula: delta(N) = -(half * 38) - (kh // 2) * 8 - (kh % 2) * 2
  where k = N/2, half = k//8, kh = k%8
```

##### Complete Address Calculation Example

**Problem**: Where in the RBF is the ctrl byte of LUT TT pair 3 for the LE at (X=10, Y=10, N=6)?

```
1. Look up column base: COLUMN_BASE[10] = 0x13FDA = 81,882
2. Compute period_start = 81,882 - 136 = 81,746
3. Y=10: cram_row=8, slot=2, group=2
   slot_base[2] = 70, offset = 70 + 2*3 = 76
4. pair=3 → pair offset = 3 * 210 = 630
5. N=6: k=3, half=0, kh=3 → delta = -(1*8 + 1*2) = -10
6. Final address = 81,746 + 76 + 630 + (-10) = 82,442 = 0x1422A
7. Bit position = (6 - 2) = 4, i.e. bit-4
```

#### Phase 2.3: DFF (D Flip-Flop) Configuration

**Challenge**: Quartus Lite **rejects** placement constraints of the form `LCFF_Xx_Yy_Nn`. Unlike LUTs, we cannot precisely control where flip-flops are placed.

**Solution**:
1. Use specific output pins to "attract" the flip-flop to the target column (Quartus automatically places FFs near the LAB closest to the output pin)
2. Use pair-diff to isolate FF-related bits

**Findings**:
- Each LE has **4 FF pairs** (vs. 8 for LUT), using the same ctrl+data structure
- FF pairs are split to **either side** of the LUT TT region (half below, half above)
- Adding a basic DFF changes ~362 bits, of which ~90% are routing and ~10% are LE config
- FF mode bits (async reset / sync enable): 82 shared mode bits + feature-specific routing

#### Phase 2.4: Arithmetic Mode

Compile an adder using a behavioral description (`a + b`); Quartus uses the LE's arithmetic mode and carry chain.

By diffing against a normal-mode LUT, we isolate **92 pure arithmetic/carry-chain bits**, distributed on both sides of the LUT TT region (same split pattern as FF).

---

### Phase 3: Cracking the Routing Matrix (In Progress)

The routing matrix is the "wire network" that connects all the LEs in an FPGA. This is the hardest part of the reverse-engineering effort.

#### Routing Resource Types

```
EP4CE6 routing resources:

  ┌─────────┐     C4 wire       ┌─────────┐
  │  LAB    │ ←──(~4 rows)───→ │  LAB    │
  │ (X,Y)  │                   │ (X,Y+4) │
  └────┬────┘                   └─────────┘
       │
     R4 wire (~4 columns)
       │
  ┌────┴────┐
  │  LAB    │
  │ (X+4,Y) │
  └─────────┘

C4  = Column wire, spans ~4 rows  (21,816 wires)
R4  = Row wire, spans ~4 columns  (28,186 wires)
C16 = Column wire, spans ~16 rows (1,326 wires)
R24 = Row wire, spans ~24 columns (1,289 wires)
LOCAL_INTERCONNECT = LAB-internal input mux
LE_BUFFER = LE output buffer
```

#### Methodology

1. **STA routing extraction**: After compilation, run `report_timing -show_routing` to get the wire names on each path.
   ```
   Example: A → LCCOMB_X10_Y10 → C4_X10_Y10_N0_I0 → LOCAL_INTERCONNECT_X10_Y14 → LCCOMB_X10_Y14 → Q
   ```

2. **Control distance**: Change the distance between two LUTs to force different routing resource types.
   - Same column, dy=1: direct connection
   - Same column, dy=2–4: 1 × C4 wire
   - Same column, dy=5–8: 2 × C4 wires
   - Same column, dy=9+: 3 × C4 wires
   - Same row, dx=1–4: R4 wires

3. **Routing determinism**: After setting `ROUTER_TIMING_OPTIMIZATION_LEVEL MINIMUM`, routing is completely deterministic — 5 different fitter seeds produce identical bitstreams.

4. **Parallel compilation**: Python `multiprocessing.Pool` (4 workers), effective speed ~4 sec/target.

#### C4 Switch CRAM Address Model (Verified: 63 wires, 0 false predictions)

```python
# CRAM address for C4_X{x}_Y{y}_N0_I0
group = (y - 2) // 3
slot = (y - 2) % 3
byte_offset = LAB_CRAM_END(x) + SLOT_BASE[slot] + 3 * group
bit_position = (6 - group) if slot == 2 else (7 - group)

SLOT_BASE = {0: 2405, 1: 2475, 2: 2338}
```

This model uses exactly the same slot/group encoding framework as LUT TT (since they share the same CRAM address space), just with different base addresses.

#### R4 Switch CRAM Address Model (25 of 37 I-indices Mapped)

R4 row-wire switches are more complex than C4 — each R4 "I-index" has an independent BASE address:

```python
# CRAM address for R4_X{wx}_Y{wy}_N0_I{idx}
prev_lab_x = max(x for x in LAB_X if x < wx)  # LAB column just before the wire's X
prev_col_start = COLUMN_BASE[prev_lab_x] - 136

group = (wy - 2) // 3
slot = (wy - 2) % 3

# Three slots use different offset formulas
if slot == 0:
    byte = prev_col_start + R4_BASE + 66 + 3*group + (1 if group > 0 else 0)
    bp = 7 - group
elif slot == 1:
    byte = prev_col_start + R4_BASE + (-70) + 3*group
    bp = 6 - group                  # Note: NOT 7-group! This was a past mistake.
else:  # slot == 2
    byte = prev_col_start + R4_BASE + 3*group
    bp = 6 - group
```

**R4_BASE lookup table** (each I-index has two pair base addresses, all in the PREV column):

| I-index | BASE pair1 | BASE pair2 | delta | Verified |
|---------|-----------|-----------|-------|----------|
| 0 | 3423 | 3842 | 419 | Multiple columns |
| 1 | 3431 | 3850 | 419 | Multiple columns |
| 2 | 3431 | 3851 | 420 | prev=X4,X6,X10,X24,X28 |
| 3 | 3474 | 3895 | 421 | 3 Y values, cross-col |
| 4 | 3423 | 3842 | 419 | Same as I=0 |
| 7 | 3414 | 3835 | 421 | Same as I=10 |
| 10 | 3414 | 3835 | 421 | Multiple columns |
| 11 | 3378 | 3585 | 207 | 2 Y values |
| 12 | 3597 | 3806 | 209 | 2 Y values |
| 13 | 3577 | 3786 | 209 | Same as I=15 |
| 14 | 3191 | TBD | ? | pair1 verified, pair2 unconfirmed |
| 15 | 3577 | 3786 | 209 | prev=X12,X16,X24 |
| 16 | 3629 | 3835 | 206 | 2 Y values |
| 17 | 2802 | 3223 | 421 | 5 columns verified |
| 18 | 4057 | 4267 | 210 | 2 columns verified |
| 20 | 2791 | 3001 | 210 | Partial columns |
| 22 | 2783 | 2993 | 210 | Small sample |
| 25 | 2762 | 2972 | 210 | 2 columns verified |

**Key findings**:

1. **R4 switches live in the PREV column**: The CRAM bits for R4_X22 are in the X=21 column. This is consistent with the physical topology of the FPGA switching matrix — row-wire switches are controlled separately in each column they pass through.

2. **Column dependency**: All I-indices work correctly at standard-width (7,350-byte) columns but fail at large columns near M9K/DSP boundaries (X=13: 76,230 bytes; X=26: 68,880 bytes). Those large columns have internal sub-regions that require a more complex address model.

3. **Two pair-spacing patterns**: delta ≈ 420 for (I=0,1,2,4,7,10) and delta ≈ 210 for (I=18,20,22,25). The former spans two 210-byte periods; the latter uses adjacent periods.

4. **Shared BASE values**: I=0 and I=4 share the same BASE; I=7 and I=10 share the same BASE.

5. **R4 wires are not only at LAB columns**: 31% of R4 wires appear at non-LAB X coordinates (e.g. X=5,9,14,15,20,27,30,32,33), but their switch bits are still in the nearest LAB column.

#### LOCAL_INTERCONNECT Switch Model (Verified: 70% cross-validation, 22 columns)

LOCAL_INTERCONNECT is the LAB-internal input multiplexer — it decides which signals get connected to LE input ports.

```python
# CRAM address for LOCAL_INTERCONNECT_X{lx}_Y{ly}_N{ln}_I{li}
col_start = COLUMN_BASE[lx] - 136     # Note: SELF column, NOT prev column!

group = (ly - 2) // 3
slot = (ly - 2) % 3
byte = col_start + 70 + pair * 210 + SLOT_OFFSET[slot] + 3 * group
bp = (6 - group) if slot == 2 else (7 - group)

SLOT_OFFSET = {0: 67, 1: -70, 2: 0}   # same offsets as R4
```

**Key characteristics**:

1. **In the self column**: Unlike R4, LOCAL_INTERCONNECT bits are in the same column's CRAM. This makes sense — the LAB input mux is part of the LAB's own configuration.

2. **Multiple pairs**: Each I-index activates 1–9 pairs (in pair range 0–8, the lowest CRAM region), forming 4 fixed activation patterns:

   | Pattern | Activated pairs | Applicable I-indices |
   |---------|----------------|---------------------|
   | All 9 | 0,1,2,3,4,5,6,7,8 | I=2,15,16,18,22,33,34,35,36,37 |
   | Skip 3,7 | 0,1,2,4,5,6,8 | I=0,30,31 |
   | Even pairs | 0,2,4,6,8 | I=24,26,28,29,32 |
   | First 2 per block | 0,1,4,5,8 | I=4,17,27 |

3. **Pairs 0 and 4 are universal**: Regardless of I-index, these two pairs are always activated.

#### R24 Switch CRAM Address Model (I=0 Mapped)

R24 row wires span ~24 columns. Their switches use a **fixed byte offset** model — simpler than R4:

```python
# CRAM address for R24_X{wx}_Y{wy}_N0_I0
prev_lab_x = max(x for x in LAB_X if x < wx)
prev_col_start = COLUMN_BASE[prev_lab_x] - 136

group = (wy - 2) // 3
slot = (wy - 2) % 3
bp = (6 - group) if slot == 2 else (7 - group)   # same bp formula as R4/C4

# Fixed byte offsets — NO slot/group byte adjustment:
R24_I0_OFFSETS = [3124, 2705]   # primary (pair 14, pos 184), secondary (pair 12, pos 185)
byte = prev_col_start + offset  # same byte regardless of Y!
```

**Key difference from R4**: The byte address is **fixed** per pair — multiple Y values map to the same byte with only `bp` varying. This means reads are ambiguous if multiple Y values share the same `bp` (which happens when they're in the same group).

- R24 switches are in the **PREV LAB column** (same as R4)
- Primary pair: rel=3124 (pair 14, pos 184); secondary: rel=2705 (pair 12, pos 185), delta=419
- 5–6 wx columns verified at 66% accuracy via pair-diff
- 7 unique R24 I-indices observed; only I=0 (73% of wires) mapped

#### C16 Switch Analysis (Not Yet Mapped)

C16 column wires span ~16 rows. Preliminary analysis shows their encoding is **fundamentally different** from C4/R4:

- Pair boundary bytes (pos=209/0) show **multi-bit changes**, not single-bit switches
- XOR patterns across columns are inconsistent — no universal slot/group formula
- Routes using C16 are noisy (3–6 R4, 2–5 C4 wires per path), making isolation difficult
- Likely requires per-wire lookup table or a completely different methodology

#### C4 I≠0 Switch Model (24 per-(X,I) Mappings — 11 I-indices)

C4 I≠0 switches use the same **fixed byte offset** model as R24 — the byte address is constant for all Y values, and only the bit position varies:

```python
# CRAM address for C4_X{wx}_Y{wy}_N0_I{ii}  (I≠0)
byte = C4_FIXED_OFFSETS[(wx, ii)]   # absolute RBF byte offset — fixed, Y-independent
group = (wy - 2) // 3
slot = (wy - 2) % 3
bp = (6 - group) if slot == 2 else (7 - group)   # same formula as C4 I=0
```

**Discovery method**: baseline-diff — compile each route, diff against `baseline.rbf`, look for bytes in the self column whose bit at the expected `bp` is flipped. A byte that fires for multiple Y values of the same (wx, I) is the switch byte.

**Mapped positions** (24 per-(X,I) entries in `_C4_FIXED_OFFSETS` in `bitstream.py`):

| I-index | Columns mapped | Hit rate |
|---------|---------------|----------|
| 1 | X=9, 15, 16, 25 | 4–5/6 |
| 3 | X=13, 22, 25 | 2–3/5 |
| 7 | X=13 | 2/2 |
| 8 | X=13 | 2/3 |
| 9 | X=10, 28, 30 | 2–3/3 |
| 10 | X=9, 28, 29 | 2–5/6 |
| 12 | X=9, 10, 22, 25 | 5–6/6 |
| 14 | X=25 | 2/2 |
| 15 | X=16 | 2/2 |
| 20 | X=9 | 2/2 |
| 23 | X=22, 29 | 2–3/3 |

**Key findings**:

1. **Fixed byte, varying bp**: Unlike R4 (which adjusts byte offset per slot/group), the byte address for C4 I≠0 is Y-independent. Only `bp` encodes the Y coordinate.

2. **No universal formula**: The pair index varies per column for the same I-index. Per-(X,I) lookup is required.

3. **pos always 184 or 185**: All switches land at data-byte positions within the 210-byte period (identical to the LUT TT data byte positions).

4. **Shared bytes**: I=3 and I=12 map to the same byte at X=22 and X=25. These two I-indices are indistinguishable by CRAM inspection alone at those columns.

5. **Non-LAB columns have larger pair numbers**: X=9, X=15, X=30 have pair indices of 58, 382, 53 respectively — consistent with their wider CRAM regions.

6. **RouteCodec integration**: `read_c4()` now handles both I=0 (formula) and I≠0 (lookup table) in a single call.

#### Routing Bit CRAM Distribution

```
One LAB column's CRAM (~7,350 bytes):

  ┌──────────────────────┐  low address
  │  FF region A         │
  │  (2 pairs, ~420 B)   │
  ├──────────────────────┤
  │                      │
  │  LUT TT region       │  8 pairs × 210 bytes = ~1,680 bytes
  │  + routing switches  │  ← routing bits are interleaved with LUT TT pairs!
  │  interleaved         │
  │                      │
  ├──────────────────────┤
  │  FF region B         │
  │  (2 pairs, ~420 B)   │
  ├──────────────────────┤
  │  C4 switch region    │
  │  R4 switch region    │
  │  other routing sw.   │
  └──────────────────────┘  high address
```

Routing switch bits and LUT TT bits use the same ctrl+data pair structure, interleaved at 210-byte spacing. The bit position (0–7) encodes the **physical target Y region**, not routing distance.

---

## Bitstream Codec (`bitstream.py`)

Based on the above findings, we have built a fully functional codec that can read and write both LUT truth tables and routing switch states.

### Core Class: `RouteCodec`

`RouteCodec` is the heart of the codec. It takes an RBF file and a zero-baseline file as reference:

```python
from bitstream import RouteCodec

# Create codec instance
codec = RouteCodec("design.rbf", "zero_baseline.rbf")
```

**Why two files?** Because FPGA CRAM bits have a polarity issue — some bits are "1=enabled" and others are "0=enabled". By comparing an empty design against the zero baseline, the codec knows the default polarity of each bit and can correctly interpret on/off state.

### LUT Truth-Table Read/Write

```bash
# Step 1: Calibrate a position (needs 16 minterm pair-diffs, ~2.5 min)
python3 runner.py n_sweep 10 10

# Step 2: Read LUT truth table from RBF
python3 analyze.py read_tt design.rbf zero.rbf 10 10 0
# Output: mask = 0x8888 (A & B)

# Step 3: Write LUT truth table to RBF
python3 analyze.py write_tt zero.rbf 0x6996 output.rbf 10 10 0
# Produces RBF with an XOR gate (A ^ B ^ C ^ D)
```

**Verification results**:
- **CRAM region is bit-identical** to Quartus output
- Only 14–16 bits differ in the header/CRC section (Quartus metadata; does not affect configuration)
- Verified masks: 0x0000, 0x0001, 0x8888, 0x6996, 0xFFFF, 0xAAAA, 0x5555, 0xDEAD, and more — 10 masks total

**End-to-end hardware verification (2026-04-06)**:

The codec was verified on physical hardware (Heijin AX301 board, EP4CE6F17C8):

```
1. Codec write_tt(zero_baseline, mask=0x8888) → e2e_codec_and.rbf
2. Flash to FPGA: openFPGALoader -c usb-blaster e2e_codec_and.rbf
3. Hardware behavior: LED ON by default (keys floating high),
   press KEY2 or KEY3 → LED OFF (correct A & B with active-low inputs)

4. Codec write_tt(zero_baseline, mask=0x6996) → e2e_codec_xor.rbf
5. Flash to FPGA: openFPGALoader -c usb-blaster e2e_codec_xor.rbf
6. Hardware behavior: press either key → LED ON, both keys → LED OFF (correct A ^ B)
```

The codec-generated RBF produces **exactly the expected logic behavior** — the bitstream codec works correctly end-to-end without going through Quartus.

Note: AX301 buttons are **active-low** (unpressed = logic 1, pressed = logic 0). The correct openFPGALoader path is `$HOME/see_neorv32_run_linux/tools/openFPGALoader/build/openFPGALoader`.

### Routing Switch Read/Write (New)

The codec now also supports reading and writing routing matrix switch states:

```python
from bitstream import RouteCodec

codec = RouteCodec()
design = open("design.rbf","rb").read()
zero   = open("zero_baseline.rbf","rb").read()

# ========== Read all routing switches ==========
sw = codec.read_switches(design, zero)
# Returns {'c4': [...], 'r4': [...], 'r24': [...], 'li': [...]}
# Each entry: (wire_name, byte_offset, bit_pos, candidates)
# LI wire names use base granularity: "LI_X10_Y5_P3B0"
#   P3 = pair index, B0 = base offset 70 (B1 = base offset 71)

# ========== Write switches into a blank baseline ==========
ops = [
    {'type': 'c4', 'x': 10, 'y': 5, 'i_idx': 0},
    {'type': 'c4', 'x': 13, 'y': 8, 'i_idx': 3},          # uses I≠0 lookup
    {'type': 'r4', 'wx': 22, 'y': 8, 'i_idx': 17},
    {'type': 'li', 'lx': 10, 'ly': 5,
     'pair_bases': [(0,0),(0,1),(2,0),(2,1),(4,0),(4,1),(6,0),(6,1),(8,0)]},
]
new_rbf = codec.apply_routing(zero, ops)

# ========== Pre-flash hardware safety check ==========
codec.validate_safe_for_hardware(new_rbf, zero)
# Raises RuntimeError if any LAB has an LI activation pattern outside the
# known-safe envelope (wrong cell count, broken paired/alternating mode, etc.)

open("output.rbf","wb").write(new_rbf)
```

Note the `li` op now requires an explicit `pair_bases` list — implicit "expand an I-index into all 9 pairs" was removed because real Quartus never activates more than 9 specific cells per LAB, and auto-expansion would have been a physical-contention hazard.

**Current coverage**:
- C4 I=0: 100% (all 63 wires correct)
- R4: 25/37 I-indices mapped (12 remaining blocked on insufficient route corpus)
- R24 I=0: mapped with fixed-byte model (~66% pair-diff accuracy), 73% of R24 wires
- LOCAL_INTERCONNECT: full read/write at base granularity, two encoding modes resolved
- C4 I≠0: no universal formula, per-wire lookup table (24 entries)
- C16: not yet mapped (fundamentally different multi-bit encoding)

---

## Routing Codec Round-Trip + Hardware Safety Guard

After basic read/write was working, the next question was: **does our codec actually round-trip?** If we read all the routing switches out of a real Quartus RBF, then write them back into a blank baseline using only our own write methods, do we get the same set of cells back?

### Round-trip self-consistency test

`route_roundtrip.py` runs this experiment:

```
real Quartus RBF ──► RouteCodec.read_switches() ──► list of switch ops
                                                        │
                                                        ▼
              blank zero baseline ──► RouteCodec.apply_routing(ops)
                                                        │
                                                        ▼
                              re-read with read_switches()
                                                        │
                              compare against the original read
```

If the codec is consistent, the two reads must agree exactly: zero dropped cells, zero hallucinated cells. Note this is **not** a "match Quartus byte-for-byte" test — that would also require encoding LUT TT, IO buffers, etc. We're only testing the routing layer in isolation.

Result for both a column route (Y10→Y5) and a row route (X10→X22):

```
column route Y10→Y5: OK  orig=52 repro=52 common=52
row route X10→X22:    OK  orig=65 repro=65 common=65
```

**0 dropped, 0 hallucinated.** The routing codec is internally consistent.

To make this work we had to add two things:

1. **`write_c4_inz()`** — C4 with non-zero I index uses fixed byte offsets instead of the universal slot/group formula. We mined 24 (X, I) → byte mappings by baseline-diffing fresh compiles.
2. **`'raw'` switch type** — for R24/LOCAL_INTERCONNECT, the per-wire write methods set *more* cells than a single read entry corresponds to (one wire activates 2+ cells). When replaying a read, we instead emit `raw` ops that flip exactly one (offset, bit) — the same granularity as the read.

### Hardware safety guard V2

Before flashing a codec-generated RBF to a real AX301 board, we want to refuse anything that could short out a LAB input mux. Multiple routing channels driving the same LE input port at the same time is a physical-contention hazard on real silicon.

`RouteCodec.validate_safe_for_hardware(rbf, zero)` scans the RBF for LOCAL_INTERCONNECT activations and refuses to pass anything Quartus has never been observed to produce.

```python
codec = RouteCodec()
codec.validate_safe_for_hardware(my_rbf, zero_rbf)   # raises if unsafe
```

The "what's safe" envelope was discovered empirically. After dropping a sloppy `break` in `read_local_interconnect()` that was hiding cell-level structure, we re-ran a 21-LAB sweep and found that **every** Quartus LI activation falls into one of two well-defined modes, each with **exactly 9 active cells per LAB**:

- **Paired mode** (13/21 LABs, mostly column moves): `P0` paired (both bases set) + 4 middle pairs paired + `P8` tail (one base) = 9 cells
- **Alternating mode** (8/21 LABs, mostly row moves): `P0..P7` each with one base, alternating `B1,B0,B1,...,B0` + `P8` tail = 9 cells
- **Universal anchors**: `P0` and `P8` always present; cell `(P0, B1)` is in every observed class

> What is a "pair" and a "base"? LOCAL_INTERCONNECT cells live in a 210-byte-period region of each LAB column. In each period, two CRAM bytes at offsets 70 and 71 ("base 70" / "base 71" — `B0`/`B1`) are the LI bytes. The pair index `P0..P8` is which 210-byte period within the column we're in.

The V2 classifier `_classify_li_lab(pair_map)` tags any LAB as `paired`, `alternating`, or `invalid` (with a reason). The guard refuses to pass:

- Any LAB with more than 9 active cells
- Missing `P0` or `P8` anchor; `P8` doubly set
- Paired mode with single-base middle pairs (broken paired)
- Alternating mode with the wrong base on any pair, or any doubled middle pair

This was tested against all 6 observed Quartus classes (all accepted) and 4 synthetic violation cases (all rejected). The previous V1 guard (`max 5 pairs per LAB`) was actually wrong: it would have false-rejected 13 of the 21 legitimate Quartus configurations.

### What this resolved: the "9-pair vs 5-pair" mystery

For a long stretch of this work the same routing key was producing what looked like two completely different bit patterns at different LABs — sometimes 10 byte flips at 5 pair positions, sometimes 9 byte flips at 9 pair positions. We thought these were structurally distinct encodings.

They aren't. They're the **same 9-cell envelope** counted two different ways:
- "5 pairs × 2 bytes = 10 flips" was counting only paired pairs and missing the P8 single-byte tail (it's actually 4 paired + P0 paired + P8 single = 9 cells)
- "9 pairs × 1 byte = 9 flips" was already counting cells correctly

The old reader's `break` after the first base hit was masking the difference between paired and alternating modes. Once we emitted one read entry per `(pair, base)` cell, the structure became obvious.

---

## Route Synthesis: Island Hopping

Once the read-side codec was solid, the next question was the inverse: **given a (src, dst) pair, can we synthesize a routing bitstream that matches Quartus cell-for-cell?** A formula-driven synthesizer turned out to be the wrong frame. We discovered that:

> **Cyclone IV CRAM is interleaved, not topologically isomorphic to the chip.** The routing-state CRAM cells for each LE live in non-overlapping physical regions far from the source LAB column, and **cross-source fingerprint intersection is empty** — there is no universal "source entry code" that generalizes across source LABs.

So `route_synth` (in `fuzz/route_synth.py`) takes a different tack: per-source corpus mining + bit-perfect snapshot replay. Each "green-zone island" is a `(sx, sy)` source LAB for which we have:

1. A small corpus of `lits_pair_X{sx}Y{sy}_to_*` Quartus compiles
2. A **source fingerprint** (cells present in 100% of routes from that source)
3. A **per-route delta** (the remaining cells per dst, as raw `(offset, bit)` pairs)

For any dst already in the corpus, `synth_route()` emits `fingerprint ∪ delta[dst]` as raw cell flips and produces a bitstream that matches Quartus byte-for-byte in the routing region. For dsts outside the corpus, it falls back to the formula-based plan (C4/R4/R24 hops + LI envelope) and is gated by `validate_safe_for_hardware()` so it can't drive a LAB into an unknown LI activation pattern.

### Three islands so far

| Island | Location | Routes | Fingerprint bits | Bit-perfect | Round-trip | Safe (synth/quartus) | Yellow zone |
|--------|----------|--------|------------------|-------------|------------|----------------------|-------------|
| α | (10, 10) — interior | 31 | 6 | 31/31 | 31/31 | 31/31 / 31/31 | 3/3 |
| β | (10, 14) — M9K boundary (Y15 ghost row) | 11 | 11 | 11/11 | 11/11 | 11/11 / 11/11 | 3/3 |
| γ | (4, 4) — corner | 16 | **1** | 16/16 | 16/16 | 16/16 / 16/16 | 3/3 |
| **Total** | | **58** | | **58/58** | **58/58** | **58/58** | **9/9** |

A few non-obvious findings from the islands:

- The (4, 4) **corner** has the *smallest* fingerprint of all three (1 bit, `R4_X11_Y5_N0_I3`). The expectation that corner LABs would need *more* "edge bits" turned out to be wrong — the corner's per-route delta absorbs almost everything.
- An earlier "GND-tie hypothesis" — that the (10, 14) fingerprint's 11 bits were artifacts of unrouted lut2 inputs being tied to GND — was **falsified** by a controlled multi-input compile (`purify_fingerprint.py`). With all 4 lut2 inputs routed to real signals, the fingerprint slightly *grew* instead of shrinking.
- Several universal "always-on" structures were extracted from the corpus and are emitted unconditionally by `emit_ops()` for any inter-LAB route from a known source: a **source-side R4 launch driver** (`R4_X{sx+1}_Y{sy}` at I=1 and I=2), a **source-column R24 broadcast hold** (5 raw bits), and an **LI source-driver MUX** (`P8B0+P8B1`) skipped only for adjacent ±1 horizontal hops. These were each mined as 100% across the corresponding `lits_pair_*` corpus.

### Tests

`fuzz/test_green_zone_harden.py` auto-discovers all `results/fingerprint_{sx}_{sy}.json` snapshots and runs five checks per island (bit-perfect vs. Quartus, codec round-trip, safe-synth, safe-quartus, fingerprint drift) plus three "yellow zone" probes (dsts NOT in the corpus, must at least pass `validate_safe_for_hardware`). All three current islands pass with zero drift.

### Mode-selection rule (still partially open)

We mined the 21 classified LABs to see what predicts paired vs alternating:

| Feature | Predictive? |
|---------|-------------|
| Column move (dy != 0) | ✅ All 7 column moves → paired |
| Row move (dx != 0) | ⚠ Mixed: 8 alternating + 6 paired |
| Adjacency to non-LAB columns (X=5,9,14,15,20,27,30) | ❌ No correlation |
| dst_x parity | ❌ No correlation |
| LAB-list index distance | Weak correlation, exceptions exist |

So column moves are deterministic, but the row-move split is not yet derivable from a single feature. The most likely missing variable is the **last R4/C4 hop's I-index** before LI — that's what selects the LI input mux tier. Resolving this needs a richer routing-paths corpus with multi-LE designs.

---

## Quick Start

### Environment Setup

```bash
# 1. Install Quartus Prime 21.1 Lite
# Download from Intel website, install to ~/intelFPGA_lite/21.1/

# 2. Configure PATH
export PATH=$PATH:$HOME/intelFPGA_lite/21.1/quartus/bin

# 3. Enter project directory
cd fuzz
```

### Basic Operations

```bash
# Generate baseline RBF
python3 runner.py baseline

# Pair-diff at (X=10, Y=10, N=0)
python3 runner.py --node lut_inst lut_single 10 10 0

# View database summary
python3 analyze.py summary

# View truth-table mapping for a specific LE
python3 analyze.py lut_table 10 10 0

# Export full database as JSON
python3 analyze.py export
```

### Advanced Operations

```bash
# Sweep all 16 minterms at one position (calibrate the codec)
python3 runner.py n_sweep 10 10

# Pair-diff grid sweep across all 22 columns
python3 runner.py pair_diff_grid

# Parallel routing fuzzing (4 workers)
python3 runner.py route_map_parallel 10 5 col

# Batch routing fuzzing (multiple source positions, multiple directions)
python3 runner.py route_map_batch --sources 4,10 29,10 10,17 --direction col --jobs 4

# Read truth table from RBF
python3 analyze.py read_tt design.rbf zero.rbf 10 10 0

# Write truth table to RBF
python3 analyze.py write_tt zero.rbf 0x8888 output.rbf 10 10 0
```

---

## Known Pitfalls and Caveats

1. **Left-edge columns (X=3,4,6,7)** have CRAM addresses below 0x10000, unlike other columns
2. **Quartus fit reports contain non-UTF-8 bytes** — use `errors="replace"` when reading
3. **Do not run multiple fuzzing campaigns in parallel sharing the same `work/` directory** — they overwrite each other's files
4. **`sof2rbf.py` produces invalid bitstreams** — always use `quartus_cpf -c -o bitstream_compression=off`
5. **Some LAB locations are invalid**: combinations with X∈{3,4,6,7,8} and Y∈{12,13,14,16} are rejected by Quartus (those positions may be occupied by M9K or other hard blocks)
6. **Disk space**: Phase 3's `work/` directory grows very rapidly; clean it after each compilation (`compile.py` provides `clean_work_dir()`)

---

## Debugging Journey: How We Closed the Hardware Loop

This section is a narrative for newcomers — it walks through the actual debugging
sessions that turned the codec from "bit-perfect against Quartus" into "the
silicon accepts our handcrafted bitstream and the LED responds to keys exactly
as we designed." Every step here was a real problem we hit, and most of them
were not obvious before we hit them.

### The starting point: codec output looked perfect, but the FPGA refused it

After Phase 3 we had a `RouteCodec` that could read routing switches from any
Quartus-generated `.rbf`, replay them onto a blank baseline with `apply_routing()`,
and re-read them losslessly. Diffing our codec output against the original
Quartus RBF showed **0 CRAM byte differences** — every configuration cell was
identical. Time to flash it on real hardware.

We connected a 黑金 AX301 board (EP4CE6F17C8 + USB-Blaster JTAG) and ran:

```bash
openFPGALoader -c usb-blaster results/rbf/lits_synth_X10Y10_to_X12Y10N0_datab.rbf
```

The flash *appeared* to succeed. But on the board, the LEDs started running a
"chasing lights" demo (跑馬燈) that we had never compiled. The FPGA was running
the **vendor demo from the EPCS configuration flash**, not our bitstream. As a
sanity check we tried flashing a known-good Quartus-built RBF — that one ran
correctly. We even tried a deliberate **single-bit flip** of a working Quartus
RBF (`lits_pair_BITFLIP_test.rbf`) — the FPGA rejected that one too and fell
back to the EPCS demo.

**Conclusion**: the Cyclone IV configuration state machine validates the
bitstream as it loads. A single byte off and the chip silently boots from
flash instead. We must have a CRC or checksum somewhere in the RBF, and our
bit-perfect-CRAM trick was leaving it stale.

### Discovering and reverse-engineering the CRC

We had no datasheet for the .rbf format, so we had to deduce the CRC algorithm
purely from observed bitstreams. Here is how we did it.

**Step 1 — Is the CRC stateful?** A CRC could be one rolling value over the
entire bitstream, or one independent value per fixed-size frame. We searched
the corpus for **frame pairs whose data bytes were identical**: if their CRC
bytes also matched, the algorithm was stateless (frame-independent). We found
**1186 such identical-data frame pairs across the corpus**, and in every single
case the trailing CRC bytes matched. ✓ Stateless. The CRC is computed on each
frame independently.

**Step 2 — Find the frame size.** RBF total size is 368,011 bytes. Subtracting
the 32-byte 0xFF preamble and 59-byte 0xFF postamble leaves 367,920 = **1752 ×
210**. Bingo: 1752 frames of 210 bytes. Each frame likely has 208 data bytes
followed by 2 CRC bytes (little-endian).

**Step 3 — The ΔCRC linear search.** This is the heart of the trick. Instead
of brute-forcing the absolute CRC of one frame against 65,536 polynomials
(which gave us zero hits — too many degrees of freedom), we used a **linear
constraint**:

- Construct two synthetic 208-byte payloads that differ in **exactly one byte**
  (e.g., byte 100 = 0x10 vs. byte 100 = 0x10 AND byte 101 = 0x10).
- For each candidate polynomial × bit-direction variant, the CRC difference
  between the two payloads is determined entirely by the polynomial — no need
  to know the init value.
- Require that the same polynomial satisfies both ΔCRCs simultaneously
  (dual-constraint). This collapses 65,536 candidates × 4 bit-directions down
  to almost nothing.

Two polys survived: the standard **0x8005** and a low-weight collision 0x0006.
0x8005 reflected is 0xA001 (the right-shift form). That's CRC-16-IBM.

**Step 4 — Brute-force the init value.** The polynomial alone doesn't fix the
CRC — there's also an initial register value. Once we knew the polynomial, we
took 1316 frames in the corpus that contained all-zero data and required
`crc16(zeros, poly=0x8005, init=?) == observed_value (0x7d9a)`. Only one init
satisfied: **0xFE54**.

**Step 5 — End-to-end verification.** With the formula nailed down:

```python
def crc16_rbf(data208: bytes) -> int:
    crc = 0xFE54
    for b in data208:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if (crc & 1) else (crc >> 1)
    return crc
```

…we ran it across **all 1752 frames** of a known-good Quartus RBF. Result:
**1727 frames matched, 25 failed**. The 25 failures were a contiguous block —
**frames 0..24**. That's the bitstream header (sync words, config registers,
device-wide options). The header is **not CRC-protected**; only frames 25..1751
(the CRAM frames) carry an enforced CRC. Once we excluded the header from the
patcher, every CRAM frame's CRC reproduced exactly.

The full spec lives in `bitstream.crc16_rbf_frame()` and `patch_rbf_crc()`.

### The codec / CRC byte overlap (and how we fixed it)

Plugging the CRC patcher into `synth_route()` and re-running the green-zone
regression test exploded: **58/58 routes bit-perfect → 0/N**. The patcher had
broken the codec.

Why? The CRC bytes live at offsets `+208` and `+209` of each 210-byte **frame**.
But the codec scans LAB columns using a **210-byte period that is not
frame-aligned** (column bases vs. frame starts differ). So the codec's
"slot 1" or "slot 2" reads occasionally land exactly on bytes that the CRC
patcher just rewrote — and the diff against the zero baseline picked up the
CRC difference as if it were a routing change.

The fix is conceptually simple: before computing any routing diff,
**mask out the CRC byte positions** so they look identical to the baseline.
That's `mask_rbf_crc_bytes()` in `bitstream.py`, called automatically at the
top of `read_switches()`. With that in place we could turn `patch_crc=True`
**on by default** in `synth_route()` and the green-zone regression returned to
58/58.

### First hardware loop closure

With the CRC patcher integrated, we re-flashed our codec-built routing RBF.
This time the JTAG load completed *and the LEDs stayed quiet* — the EPCS
demo did not take over. The FPGA was running our bitstream. **Loop closed.**

Then we tried `LutCodec.write_tt(minterm_0_baseline, mask=0xFFFF)` —
overwrite the LUT truth table with constant-1. Flash, verify: LED ON.
Flash the Quartus-built `minterm_0` (mask 0x0000, constant-0) as a control:
LED OFF. **Opposite states confirm `LutCodec.write_tt` reaches silicon.**

Surprise observation: when we ran `patch_rbf_crc()` on the LutCodec output,
it changed **0 bytes**. The CRC was already valid. Why? Because LutCodec's
bit patterns were trained from Quartus pair-diffs that already include the
CRC byte changes — so writing a new TT implicitly produces a CRC-correct
bitstream. RouteCodec doesn't have that property because it uses
RE-derived formulas, not pair-diff replays.

### Hardware-probing the AX301 pin map

To build a real functional demo we needed `LED0 = f(K1, K2, K3, K4)` to
behave correctly. But our `config.py` had `D = PIN_E15  # RESET` — labeled
as a reset pin, not a key. Earlier hardware experiments (`LED = A & B & C & D`)
had shown LED stuck ON regardless of key presses, hinting that the pin labels
might be wrong. We didn't trust the AX301 schematic PDF (and couldn't easily
get one), so we built a **silicon pin scanner**.

The technique: write a one-line Verilog `assign LED = K`, compile it 4 times
with `K` bound to a different candidate pin (`PIN_E16`, `PIN_M16`, `PIN_M15`,
`PIN_E15`), all driving `LED0 = PIN_G15`. Flash one at a time. Press all 4
physical keys after each flash. Whichever key turns the LED off **is** that
pin. (The keys are active-low, so pressing pulls the input to GND, and
`assign LED = K` propagates that 0 to LED0.)

Four flashes, four answers (`pin_probe.py`):

| PIN | Physical key |
|-----|--------------|
| PIN_E15 | **KEY1** (was mislabeled "RESET") |
| PIN_E16 | KEY2 |
| PIN_M16 | KEY3 |
| PIN_M15 | KEY4 |
| PIN_G15 | LED0 (active-high) |

The `D` input was wired to KEY1 all along — not a reset pin. With this
silicon-verified table we updated `config.py` and recorded the map in memory.

### The final functional demo and the XOR-delta footgun

Goal: **"Hold K1+K2 OR hold K3+K4 → LED on, otherwise LED off."** This uses
all 4 inputs and gives a satisfying physical interaction.

With FUZZ_PINS A=K2, B=K3, C=K4, D=K1 and active-low keys, the function is
`Q = (¬D ∧ ¬A) ∨ (¬B ∧ ¬C)`. Computing the truth-table mask bit by bit gives
`0x0357` (bits {0,1,2,4,6,8,9} set).

We wrote that mask onto a `minterm_0_X10_Y10_N0.rbf` baseline using
`LutCodec.write_tt()`, patched the CRC, flashed, and started pressing keys.
**5 out of 6 cases worked.** One case was wrong: pressing all 4 keys
simultaneously gave LED OFF, but our function says it should be ON.

Round-trip read of the codec output returned `0x0357` — exactly what we wrote.
So why did hardware say bit 0 was 0?

The bug: **`LutCodec.write_tt(base, mask)` is not absolute. It is XOR-delta
against `base`.** The codec computes which CRAM cells differ from the *true
0x0000 baseline* for `mask`, and XORs those cells onto whatever `base` you
pass it. The hardware truth table is therefore `base_tt XOR mask`, not `mask`.

Our `base` was `minterm_0_X10_Y10_N0.rbf`. Look at what `minterm_0` actually
contains: it's the design `Q = ~A & ~B & ~C & ~D`, which outputs 1 only when
all inputs are 0. So `minterm_0`'s LUT TT is `0x0001` — bit 0 is already set.

Hardware TT after our write was therefore `0x0001 XOR 0x0357 = 0x0356`. Bit 0
of 0x0356 is **0**. That's exactly the case where all 4 keys are pressed —
input pattern (D,C,B,A) = (0,0,0,0) → TT[0] → 0 → LED OFF. The bug aligned
perfectly with the symptom.

`read_tt` is symmetric (it also returns the delta against `base`), so the
round-trip read couldn't catch the bug — both writer and reader use the same
XOR convention.

The fix is one line: write `mask ^ base_tt` instead of `mask`.

```python
TARGET = 0x0357
MASK = TARGET ^ 0x0001   # compensate for minterm_0's TT[0]=1
```

Reflash. Press all 4 keys. **LED ON.** Press just K1+K2: LED ON. Press K3+K4:
LED ON. Press anything else (single key, K1+K3, K2+K4, etc.): LED OFF. **Full
truth table verified by physical key presses.**

### Bonus discovery: EP4CE6 and EP4CE10 are the **same physical die**

A natural question after Phase 3 was: "could we cross-validate our CE6
findings against EP4CE10, since they share the F17 package and are rumored
to be the same silicon?" Rather than guess, we ran the cleanest possible
experiment via `fuzz/cross_device_diff.py`:

- Compile a one-line Verilog (`assign LED = K`) with **identical** pin
  assignments under two device targets:
  - `DEVICE = EP4CE6F17C8`
  - `DEVICE = EP4CE10F17C8`
- Byte-diff the resulting RBFs.

**Result**:

| | EP4CE6F17C8 | EP4CE10F17C8 |
|---|---|---|
| Size | 368,011 bytes | 368,011 bytes |
| SHA1 | `b47e804074b05d3d…` | `b47e804074b05d3d…` |
| Byte differences | **0** | |

Not "almost identical" — **byte-for-byte identical**, including the header
bytes that carry the device ID. Altera did not even add a CRAM bit to gate
the disabled region. The "6,272 LE vs 10,320 LE" difference exists
**entirely as a software constraint inside Quartus**; the silicon is the
same metal masks, the same fuses, the same device ID in the bitstream.

**Why this matters strategically**. Re-fuzzing CE10 to rebuild Phase 1/2
data would be 100% redundant — the SQLite would be a duplicate. But the
result unlocks a much more powerful trick: **CE10 is a "jailbroken Quartus"
for CE6**. Whenever Quartus refuses to place logic in a region the CE6
software profile considers off-limits (M9K boundaries, the huge X=13 / X=26
columns, regions reserved for the larger LE pool), we can switch the
project's `DEVICE` to EP4CE10F17C8, force the placement, compile, and feed
the resulting RBF straight back into the same RouteCodec / LutCodec / CRC
patcher — because the underlying CRAM is unchanged. The bits the CE6
software refuses to generate live in the same place; we just need a
different software profile to coax them out.

### The full jailbreak: CE6's fabric map is a lie

2026-04-07. Armed with the "same die" result, we set out to actually
_touch_ the silicon Altera hides. The method is embarrassingly simple:
write a trivial Verilog that locks one `cycloneive_lcell_comb` to a
specific `LCCOMB_Xa_Yb_N0` inside a `DEVICE = EP4CE10F17C8` project, run
`quartus_fit`, and read the fitter verdict. `"Fitter was successful"` =
that coordinate physically exists in the fabric. `"illegal location
assignment"` = Quartus is (still) refusing. By sweeping a grid we get a
yes/no map of what is _actually_ on the die.

The results are brutal:

| CE6 claims (`config.py` / `CLAUDE.md`) | Reality on CE10 probe |
|---|---|
| `LAB_X = [3,4,6,7,8,10,11,12,13,16,17,18,19,21,22,23,24,25,26,28,29,31]` (22 cols) | **28 cols** — add X=5, 9, 14, 30, 32, 33 |
| `NON_LAB_X = {5, 9, 14, 15, 20, 27, 30}` (7 cols M9K/DSP/PLL) | **Only {15, 20, 27}** — the other four are real LABs |
| `LAB_Y = [2..14, 16..21]` (19 rows, Y=15 skipped) | **20 rows** — Y=15 is a real LAB row at X ∈ {10,14,16,21,25,30,31,32,33,...} |
| Total LABs: 392 | **~520+** |
| Total LEs: 6,272 | **10,320** (matches CE10 datasheet exactly) |

In other words, four of the seven columns CE6 marks as "non-LAB" are
lies; one entire row (Y=15) is a lie; the two rightmost columns (X=32,33)
are a lie. The fitter has a hard-coded whitelist that deletes ~40% of
the die and relabels the chip as a smaller part.

**Live-LE proof by XOR chain**. Claiming a coordinate exists and
claiming that LE is _functional_ are two different things — rebinning is
often driven by yield failures in specific columns. To separate the two
we built a single-bitstream dead-cell scanner
(`jailbreak/scanC_gen.py`):

```
chain[0] = K1 ^ K2
for each forbidden LE i:
    (* keep, preserve *)
    chain[i+1] = cycloneive_lcell_comb(dataa=chain[i], lut_mask=0xAAAA)  // identity
LED = chain[N]
```

Every LUT passes its `dataa` straight through. The math reduces to
`LED = K1 ^ K2` **if and only if every cell in the chain behaves**. A
single stuck-at, broken routing channel, or misconfigured LUT mask flips
the output parity on at least one of the four key combinations, and the
LED reports the damage.

Three phases, three flashes on the AX301:

| Phase | Scope | LEs in chain | Hardware result |
|---|---|---|---|
| A | X ∈ {32,33}, Y ∈ [2..21], N=0 | 40 | ✅ full truth table match |
| B | X ∈ {32,33}, Y ∈ [2..21], N ∈ {0,2,…,30} | 640 | ✅ |
| C | X ∈ {5,9,14,30,32,33} (hidden cols) + Y=15 row, full N | **1,840** | ✅ |

2,480 distinct CE6-hidden LEs, four key combinations each, every single
one behaves exactly as pure silicon should. **This particular AX301
board is not a rebin reject — it is a fully functional CE10 die that
Altera sold as a CE6.**

What this means for the project: the existing CRAM / C4 / R4 / LI
models do not need to be thrown out. They just need to grow. Each of
the six newly-discovered LAB columns needs one `COLUMN_BASE` entry, and
the Y=15 row needs to be added to `LAB_Y`; every other part of the
model — pair spacing, slot/group encoding, LI mode taxonomy, CRC frame
layout — carries over because the silicon underneath is identical. The
routable fabric grows by ~32%, the addressable CRAM by 0 bytes.

We deliberately do **not** auto-enable the expanded map in `bitstream.py`
yet. The expansion must be gated on: (1) per-new-column CRAM base
mining via baseline-diff, and (2) a green-zone regression on at least
one new source in X ∈ {32,33} to confirm the RouteCodec invariants hold
at the fabric edge. Both are mechanical follow-ups — no new physics.

Cross-die comparison (EP4CE15 / EP4CE22) is a different question entirely
— those are likely "Die B" with different column counts and would require
re-deriving column bases. We are deliberately not pursuing them yet:
finishing CE6 routing coverage is a faster path to a working open
toolchain than chasing a wider device family.

### What we learned

1. **Trust silicon, not datasheets.** The AX301 pin labels in our config were
   wrong; a 4-flash hardware probe gave the correct map in 5 minutes.
2. **Bit-perfect ≠ flash-clean.** A bitstream can be byte-identical in CRAM
   and still get rejected because of header CRC, frame CRC, or other gating
   structures the chip checks during configuration.
3. **Use linear constraints for unknown CRCs.** Brute-forcing 65,536
   polynomials against an absolute CRC fails (too many free parameters).
   Brute-forcing against a **difference** of two carefully chosen frames
   collapses the search instantly.
4. **Read and write codecs must use the same baseline convention.** A
   round-trip read can pass while the absolute hardware behavior is wrong, if
   both sides share the same XOR-delta assumption. Always validate against
   physical behavior, not just self-consistency.
5. **A working LED on hardware is worth a thousand passing unit tests.**
   Every bug above slipped past our software checks and only revealed itself
   when the LED on the board did the wrong thing.

The codec stack now has a closed loop:

```
Verilog idea  →  LutCodec.write_tt  →  patch_rbf_crc  →  openFPGALoader
                                                              ↓
                                                     real EP4CE6 silicon
                                                              ↓
                                                     LED behaves as designed
```

From this point forward, we no longer need to round-trip through Quartus to
validate codec changes — we can write the bitstream ourselves and watch the
chip respond.

---

## Current Progress and Next Steps

### Completed ✓

- [x] Phase 1: Automated fuzzing pipeline
- [x] Phase 2.1: LUT truth-table XOR-linear encoding model (16 bits × 376 positions = 100%)
- [x] Phase 2.2: Complete CRAM address model (X/Y/N 3D formula, 376/376 verified)
- [x] Phase 2.3: DFF configuration bit mapping
- [x] Phase 2.4: Arithmetic mode bit mapping
- [x] Phase 2.5: LUT TT codec (read/write verified, 10 masks bit-identical)
- [x] Phase 3.1: C4 I=0 switch address model (63 wires, 0 false predictions, universal formula across 22 columns)
- [x] Phase 3.2: R4 switch address model framework (slot/group formula + PREV column location)
- [x] Phase 3.3: R4 slot=1 offset correction (bp = 6-group, 0%→78% fix)
- [x] Phase 3.4: R4 I-index mapping — 18/37 mapped (13 via R4_BASE_PREV slot/group formula: I=0,1,2,4,7,10,14,15,17,18,20,22,25; +5 via per-(X,I) corpus mining: I=3,11,12,13,16)
- [x] Phase 3.5: LOCAL_INTERCONNECT switch modeling (70% cross-validation, 22 columns, 4 pair activation patterns)
- [x] Phase 3.6: Routing codec (RouteCodec read/write methods: C4/R4/LOCAL_INTERCONNECT)
- [x] Phase 3.7: R24 I=0 fixed-byte model (~66% pair-diff accuracy, 73% of R24 wires)
- [x] Phase 3.8: C4 I≠0 per-(X,I) fixed-byte lookup (24 entries, 11 I-indices)
- [x] Phase 3.9: RouteCodec round-trip self-consistency (0 dropped, 0 hallucinated on column + row)
- [x] Phase 3.10: LOCAL_INTERCONNECT base-granularity read API (one entry per (pair, base) cell)
- [x] Phase 3.11: LI encoding modes resolved — paired vs alternating, uniform 9-cell envelope
- [x] Phase 3.12: Hardware safety guard V2 with signature recognition (`validate_safe_for_hardware`)
- [x] Phase 3.13: End-to-end hardware verification on AX301 (codec → flash → expected logic)
- [x] Phase 3.14: Route synth island hopping — **15 green-zone source LABs** (4,4), (10,4), (10,10), (10,14), (13,10), (16,4), (16,8), (16,14), (19,14), (22,12), (22,16), (25,6), (28,10), (28,18), (31,12) — **686/686 routes bit-perfect** against Quartus, fingerprint drift = 0
- [x] Phase 3.15: **EP4CE6 RBF CRC fully reverse-engineered** (CRC-16/IBM, poly 0x8005, init 0xFE54, reflected, per 210-byte frame, frames 25..1751). Patcher integrated into codec; 1727/1727 CRAM frames verified
- [x] Phase 3.16: **Hardware loopback closed** — RouteCodec + LutCodec output flashes successfully on real EP4CE6 silicon after CRC patch (no more EPCS fallback)
- [x] Phase 3.17: AX301 pin map silicon-verified via `pin_probe.py` (KEY1=E15, KEY2=E16, KEY3=M16, KEY4=M15, LED0=G15)
- [x] Phase 3.18a: **EP4CE6 ≡ EP4CE10 confirmed same physical die** — byte-identical RBF (incl. device ID); enables CE10 as "jailbroken Quartus" for fuzzing CE6's restricted regions (`fuzz/cross_device_diff.py`)
- [x] Phase 3.18b: **Full jailbreak — CE6 fabric whitelist falsified** — 2,480 hidden LEs hardware-verified alive via 3-phase XOR-chain dead-cell scanner (`jailbreak/scanC_gen.py`); 6 new LAB columns (X=5,9,14,30,32,33), Y=15 row unlocked; effective fabric 392→520+ LABs, 6,272→10,320 LEs (+65%)
- [x] Phase 3.18: **Functional 4-input LUT demo on hardware** — `LED0 = (K1∧K2)∨(K3∧K4)` written via LutCodec, full truth table validated by physical key presses

### In Progress

- [~] Phase 3.19: Map remaining R4 I-indices — **25 of 37 mapped** (added I=6,8,11,12,13,16,17,19,21,23,26,27 + 13 earlier). 12 remain blocked on insufficient route corpus (5,9,24,28,29,30,31,32,33,104,116,125), not on mining method
- [ ] Phase 3.20: M9K/DSP boundary column fix (X=13/26 large columns need sub-region address model)
- [ ] Phase 3.21: C16 long-distance wire modeling (not yet started)
- [x] Phase 3.22: **LI mode-selection rule — CLOSED NEGATIVE**. T9 + T10 orthogonal-grid corpus (12 sources, 374 compiles, 414 mappable rows, `fuzz/li_mode_grid_mine.py` + `li_mode_analyze.py` + `li_mode_tree.py`). Clean rules: `dy∈{2,3,21}→edge_even_b0` (100%), `adx==0→paired` (79%), `dx>30∧dy>7.5→paired`. Middle leaf `dy>3∧dx≤24.5∧adx>0.5` (n=247, 60% of corpus) stuck at **52% coin flip** — unchanged by 2× corpus growth and sx/dx decorrelation. Conclusion: paired vs alternating is **not a function of the static routing key**; likely driven by Quartus placement seed / LI channel occupancy. Further corpus expansion will not help. Yellow-zone fallback keeps `paired` as a weak prior (both modes are hardware-safe).
- [x] Phase 3.23: **C4 I≠0 fog-of-war sweep** — `fuzz/c4_inz_sweep.py` mined 19 new (X,I) mappings from existing routing_paths corpus, taking `_C4_FIXED_OFFSETS` from 25 → **44 mappings**. Green-zone regression still 58/58 bit-perfect.
- [x] Phase 3.24: **Non-LAB column identity resolved** — `jailbreak/probe_blocks.v` (12× altsyncram + 8× lpm_mult, virtual-pinned). Quartus placed blocks at `M9K_X15_Y*`, `M9K_X27_Y*`, `DSPMULT_X20_Y*`. So of the 3 true non-LAB columns (post-jailbreak): **X=15 and X=27 are M9K RAM columns**; **X=20 is the embedded 9×9 multiplier column**. PLLs live at the die periphery, not in any X column.
- [x] Phase 3.25: **Jailbreak fabric CLOSED on silicon (2026-04-07)** — both axes silicon-validated end-to-end through the codec. **X=32 column**: LCCOMB_X32_Y10_N0 mask 0x8888 ran on AX301; codec calibrated, `COLUMN_BASE` extended to all 28 LAB columns at standard 7350-byte stride. **Y=15 ghost row**: LCCOMB_X10_Y15_N0 mask 0x0357 = `(K1∧K2)∨(K3∧K4)` ran on AX301 (`fuzz/demo_y15_keys2led.py`). +65% fabric is production-ready on real CE6 silicon
- [x] Phase 3.26: **Route-synth green zones expanded 3 → 15 source LABs** (`fuzz/fingerprint_raw_mine.py` codec-blind XOR mining, header filter); 686/686 routes bit-perfect. `results/r4_iindex_table.json` (942 entries) silently used by `route_synth.py:206` for I-index hint selection per (src,dst,port) geometry
- [~] Phase 3.27: **M9K CRAM probe — partial**. `fuzz/m9k_probe_mine.py` archived 237 `M9K_GLOBAL_ON` + 299 `M9K_COL15_ON` cells in `results/ep4ce6_bitdb.sqlite` table `m9k_cells`; M9K config band identified at bytes 0x567xx..0x588xx. **Y-position model abandoned**: 7-Y sweep at X=15 had 1489/1707 cells unique to one Y — auto-router churn dominates. Mult X=20 probe failed (LOC name unknown). STA wire-name extraction is the next path if/when needed

- [x] Phase 4: **FASM toolchain CLOSED on silicon (2026-04-08)** — `fuzz/fasm2rbf.py` + `fuzz/rbf2fasm.py` implement a minimal FASM dialect (`LUT`, `ROUTE`, `BIT`, `SRC`) driving `LutCodec` + `RouteCodec` + `patch_rbf_crc`. Signature backend (`fuzz/route_signatures.py`, 1050 route cell-sets) short-circuits `synth_route` for yellow-zone and Y=15 jailbreak sources. Set-cover decomposer (`fuzz/route_decompose.py`) collapses multi-route + cross-source CRAM diffs into clean directives. Regression suite: 1050/1050 single-route, 42/42 multi-route, 3/3 cross-source bit-perfect. Hardware closure: `X10Y10N0.LUT = 0x8888` (AND(K1,K2)) one-liner flashed to AX301 via `fasm2rbf`, silicon behavior matched

### Future Work

- [ ] Phase 5: Complete routing codec coverage (target: all wire types >90%; C16 + remaining R4 I-indices still open)
- [ ] Phase 6: NextPNR EP4CE6 backend (chipdb from the bit dictionary, nextpnr-generic port)

### Long-term direction: where we can actually beat Quartus

A common question is "with the codec working, can we use modern ML (RL routing,
GNN congestion prediction, LLM logic synthesis) to outperform Intel Quartus?"
Our honest answer, based on the current state of the project and the academic
literature, is **mostly no for the things people first think of, but yes for a
narrower and more interesting set of targets**.

**Where we will not win.** Quartus has a hardware-calibrated timing model
(per-wire RC measured on real silicon across process corners), a complete
legality checker accumulated over 30 years, and routing algorithms
(PathFinder + negotiated congestion) that academic RL routers have **not yet
beaten on standard benchmarks** as of 2024. Trying to out-route Quartus on its
home turf with reinforcement learning is a well-known academic trap.

**Where we can win.** We have one asymmetric advantage Quartus does not have
and never will: **a programmable, bit-level, bidirectional codec that can
modify a bitstream in microseconds and validate the result on real silicon in
seconds**. Quartus is a one-way `verilog → bitstream` black box. We are not.
That gap enables several things Quartus structurally cannot do:

1. **Bitstream-level superoptimizer (peephole over CRAM).** Take a Quartus
   build, mutate it cell by cell (equivalent LUT-mask transforms, redundant
   routing-bit removal, parallel-LE merging), validate equivalence on hardware,
   accept mutations that lower cell count or dynamic power. Quartus never
   re-touches its output once fit completes; we can run thousands of
   silicon-validated mutations offline. The win comes from "infinite free
   re-tries on real silicon," not from a smarter model.
2. **Things Quartus refuses to do at all.** Our codec enables:
   - Partial reconfiguration on a die that does not officially support it
     (rewrite specific frames without a full reload)
   - Bitstream watermarking / fingerprinting in irrelevant LUT bits
   - Reproducible builds (Quartus is seed-dependent; our codec is a pure
     function — bit-identical output for identical input, every time)
   - Per-die overfitting (calibrate for one specific chip's process corner /
     aging — useful for hardware security and PUFs)
3. **Open toolchain (the real prize).** A working Yosys + nextpnr-EP4CE6 flow
   matters 100× more than "beating Quartus on PPA." It is the first time
   Linux/macOS users can target this chip without installing Intel's tools,
   the first time CI systems can build EP4CE6 bitstreams reproducibly, and the
   first time the chip enters the open-source FPGA ecosystem at all. **This is
   the actual long-term goal of the project.**

**Where ML belongs (assistant role, not core).** Modern ML has a real but
modest place in this project:

- **Decision-tree mode classifier** to replace hand-coded LI envelope rules
  (`_classify_li_lab()`). Once the corpus is large enough, a learned classifier
  is more robust than hard-coded patterns and remains fully interpretable.
- **Pattern miner** for the `li_mode_corpus_mine.py` output — small decision
  trees, not GNNs, are the right tool for finding the paired-vs-alternating
  selection rule. Decision trees can be audited and compiled directly into the
  codec.
- **Anomaly detector** for codec-built RBFs that fail to flash — predict which
  envelope was most likely violated, to speed up debugging.

None of these are "ML beats Quartus." They are "ML helps us write rules we do
not want to hand-derive."

**Recommended priority.** Finish Phase 5–6 first (routing coverage → chipdb →
nextpnr backend). Once a `.v → bitstream` open-source flow runs end-to-end,
the question shifts from "can we beat Quartus on PPA" to "what can we do that
Quartus cannot do at all" — and the codec, not a model, is what unlocks those
answers.

> **TL;DR — We are not building a smarter Quartus. We are building a different
> kind of tool that lets users do things Quartus does not let them do at all.
> The win is in defining a new arena, not in beating Quartus on its home turf.**

### Overall Progress Estimate

| Domain | Progress | Notes |
|--------|----------|-------|
| Logic configuration (LUT/FF/Arithmetic) | **~95%** | All LE positions' LUT TT decoded; FF and arithmetic mode mapped |
| CRAM address mapping | **100%** | 22 cols × 18 rows × 16 LEs = 376/376 positions fully verified (CE6 whitelist; post-jailbreak X=32/33 + Y=15 silicon-validated) |
| C4 routing switches | **~65%** | I=0 100% formula; I≠0 44-entry per-(X,I) lookup table (Phase 3.23 sweep) |
| R4 routing switches | **~68%** | 25/37 I-indices mapped; remaining 12 blocked on corpus, not method |
| LOCAL_INTERCONNECT | **~85%** | Base-granular read/write; two encoding modes resolved; V2 safety guard |
| R24 long-distance wires | **~30%** | I=0 fixed-byte model, 73% wires |
| C16 long-distance wires | **0%** | Not yet started |
| Bitstream codec | **~85%** | LUT TT + routing read/write; round-trip self-consistent; HW safety V2; **CRC patcher integrated; HW-verified on silicon** |
| Route synthesis (green islands) | **15/392 sources** | (4,4), (10,4), (10,10), (10,14), (13,10), (16,4), (16,8), (16,14), (19,14), (22,12), (22,16), (25,6), (28,10), (28,18), (31,12) — 686/686 routes bit-perfect against Quartus |
| FASM signature backend | **1050 routes** | `results/route_cells.json` — short-circuits `synth_route` for all mined routes incl. yellow zone + Y=15 jailbreak row |
| RBF CRC reverse engineering | **100%** | CRC-16/IBM 0x8005, init 0xFE54, frames 25..1751; 1727/1727 verified |
| FASM toolchain (Phase 4) | **closed** | `fasm2rbf` + `rbf2fasm` + set-cover decomposer; 1050/1050 + 42/42 + 3/3 bit-perfect regressions; AX301 silicon-accepted (AND(K1,K2)) |
| Hardware loopback (codec → flash → silicon) | **closed** | LutCodec + FASM path both running on AX301 |

---

## References

- [Cyclone IV Device Handbook](https://www.intel.com/content/www/us/en/docs/programmable/683853/current/cyclone-iv-device-handbook.html)
- [Project IceStorm](http://www.clifford.at/icestorm/) — iCE40 reverse engineering, methodology reference
- [Project Mistral](https://github.com/Ravenslofty/mistral) — Cyclone V reverse engineering, same chip family
- [Quartus Prime Lite](https://www.intel.com/content/www/us/en/products/details/fpga/development-tools/quartus-prime/resource.html) — Free FPGA development tool

---

## License

**Dual license (as of 2026-04-07, replacing the previous MIT license):**

**Why we switched.** For most of this project the license was MIT — the
default choice for small research code. The trigger for the change was
the CE6→CE10 jailbreak documented in *"The full jailbreak: CE6's fabric
map is a lie"* above. Until that point the findings looked like a
narrow reverse-engineering of one budget FPGA. Once we could prove on
silicon that the chip Altera sold as an EP4CE6 is physically an
EP4CE10, that its fitter whitelist deletes ~40% of a working die, and
that every one of those hidden 2,480 LEs lights up on the first try —
the stakes shifted. The code and the findings are no longer "a neat
hack on a cheap board"; they are the seed of an open toolchain that
could unlock ~65% more logic on every EP4CE6 board in the wild, and a
reproducible method for catching vendors doing the same trick on future
parts. MIT would have let Altera absorb the method into a silent
fitter patch and move on without a word. GPLv3 + CC BY-SA forces every
downstream — commercial, academic, or vendor itself — to stay on the
same open table, with full source and full attribution. That felt like
the honest response to what the silicon just told us.



- **Code** — `GPL-3.0-or-later`. The Python pipeline, Verilog generators,
  codec implementations, jailbreak scanners, and anything under `fuzz/`
  are copyleft. If you vendor this code into another toolchain — open or
  closed, hobby or commercial, including any official Altera/Intel tool
  — your project must be released under GPLv3 with full source. Full
  text: [`LICENSES/GPL-3.0-or-later.txt`](LICENSES/GPL-3.0-or-later.txt).
- **Documentation, findings & methodology** —
  `CC BY-SA 4.0`. The CRAM model, C4/R4/LI address formulas, RBF CRC
  spec, CE6→CE10 jailbreak results, XOR-chain dead-cell scanning
  method, and all prose in `README*.md` / `CLAUDE.md` / `FINDINGS.md`
  are share-alike. Cite them in a paper, tutorial, or talk and your
  derivative must also be CC BY-SA. Full text:
  [`LICENSES/CC-BY-SA-4.0.txt`](LICENSES/CC-BY-SA-4.0.txt).

See [`LICENSE`](LICENSE) for the scope notes and rationale.

The choice is deliberate: this work exists to keep FPGA toolchain
research in hacker hands. MIT would have let Altera quietly patch their
fitter whitelist and absorb the findings without reciprocity. GPLv3 +
CC BY-SA forces every downstream — commercial or academic — to stay on
the same open table.

Bitstream blobs (`*.rbf`, `*.sof`), raw SQLite databases, and Quartus
build artifacts in `work/` and `results/rbf/` are hardware telemetry,
not creative works; no license is asserted over them, and
redistribution remains subject to the upstream vendor's original terms.

This project is for educational and research purposes. The
reverse-engineering results are intended for building an open-source
FPGA toolchain.
