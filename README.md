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
├── fuzz/                   ← Fuzzing pipeline (Python source)
│   ├── config.py           ← EP4CE6 constants, coordinates, pin definitions
│   ├── verilog_gen.py      ← Verilog code generator
│   ├── qsf_gen.py          ← Quartus project config file generator
│   ├── compile.py          ← Quartus headless compilation driver
│   ├── rbf_diff.py         ← Bit-level binary diff engine
│   ├── database.py         ← SQLite database interface
│   ├── runner.py           ← Fuzzing experiment orchestrator (main entry)
│   ├── analyze.py          ← Result analysis and visualization
│   └── bitstream.py        ← Bitstream codec (read/write LUT + routing switches)
├── results/
│   ├── rbf/                ← Collected .rbf files (~850 files, 368 KB each)
│   ├── ep4ce6_bitdb.sqlite ← Bit-mapping database (609K+ records)
│   └── FINDINGS.md         ← Detailed findings report
├── work/                   ← Quartus temporary build directory (can be cleaned)
├── work_route/             ← Routing experiment build directory
└── work_verify/            ← Verification experiment build directory
```

### Source Code Statistics

| File | Lines | Function |
|------|-------|----------|
| `config.py` | 160 | Chip constants, CRAM address formulas, pin definitions |
| `verilog_gen.py` | 193 | 8 Verilog generation functions |
| `qsf_gen.py` | 80 | QSF project configuration generation |
| `compile.py` | 269 | Quartus compilation driver + STA routing extraction |
| `rbf_diff.py` | 110 | Binary comparison engine |
| `database.py` | 192 | SQLite database operations |
| `runner.py` | 1,226 | Experiment orchestrator (largest file) |
| `analyze.py` | 569 | Analysis, visualization, and codec commands |
| `bitstream.py` | 614 | **Bitstream codec (LUT + routing read/write)** |
| **Total** | **~3,413** | |

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
- **1,755** experiments
- **609,835** bit-mapping records
- **774** routing paths (including complete wire paths from STA extraction)
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

#### R4 Switch CRAM Address Model (18 I-indices Mapped)

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

#### C4 I≠0 Switches (No Universal Formula)

Unlike C4 I=0, the other 24 C4 I-indices have **no** unified formula for their CRAM positions. The same I-index maps to different pair positions in different columns, and even the polarity differs (some bits are 1=on, others 0=on).

For now these can only be handled via per-wire lookup tables. 24 distinct C4 I-indices have been observed across 774 routing paths.

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

codec = RouteCodec("design.rbf", "zero_baseline.rbf")

# ========== Read switch states ==========

# Read a C4 (column direction, ~4 rows) switch
state = codec.read_c4(x=10, y=5, i=0)
# Returns True (switch closed) or False (switch open)

# Read an R4 (row direction, ~4 columns) switch
state = codec.read_r4(wx=22, wy=5, idx=1)

# Read a LOCAL_INTERCONNECT (LAB input mux) switch
state = codec.read_local_interconnect(lx=10, ly=5, li=2)

# Read all known switch types in bulk
switches = codec.read_switches()
# Returns dict: {"C4_X10_Y5_N0_I0": True, "R4_X22_Y5_N0_I1": False, ...}

# ========== Write switch states ==========

# Write a single C4 switch
codec.write_c4(x=10, y=5, i=0, value=True)

# Write a single R4 switch
codec.write_r4(wx=22, wy=5, idx=1, value=True)

# Write a single LOCAL_INTERCONNECT switch
codec.write_local_interconnect(lx=10, ly=5, li=2, value=True)

# Write multiple switches, then save to file
codec.write_c4(x=10, y=5, i=0, value=True)
codec.write_r4(wx=22, wy=8, idx=17, value=True)
codec.apply_routing("output.rbf")  # save modified RBF
```

**Current coverage**:
- C4 I=0: 100% (all 63 wires correct)
- R4: 18/37 I-indices mapped (~90.5% wire coverage, ~77% direct-verification accuracy)
- R24 I=0: mapped with fixed-byte model (~66% pair-diff accuracy), 73% of R24 wires
- LOCAL_INTERCONNECT: ~70% cross-validation accuracy
- C4 I≠0: no universal formula, per-wire lookup only
- C16: not yet mapped (fundamentally different multi-bit encoding)

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
- [x] Phase 3.4: R4 I-index mapping — 13/37 mapped (I=0,1,2,4,7,10,14,15,17,18,20,22,25)
- [x] Phase 3.5: LOCAL_INTERCONNECT switch modeling (70% cross-validation, 22 columns, 4 pair activation patterns)
- [x] Phase 3.6: Routing codec (RouteCodec read/write methods: C4/R4/LOCAL_INTERCONNECT)

### In Progress

- [ ] Phase 3.7: C4 I≠0 switch modeling (24 I-indices observed, no universal formula, need per-wire lookup table)
- [ ] Phase 3.8: Map remaining ~24 R4 I-indices (I=3,6,8,9,11,12,13,16,19,21,23,26,27,28, etc.)
- [ ] Phase 3.9: M9K/DSP boundary column fix (X=13/26 large columns need sub-region address model)
- [ ] Phase 3.10: C16/R24 long-distance wire modeling (not yet started)

### Future Work

- [ ] Phase 4: Complete routing codec coverage (target: all wire types >90%)
- [ ] Phase 5: FASM format adaptation (integration with Yosys/NextPNR)
- [ ] Phase 6: NextPNR EP4CE6 backend development

### Overall Progress Estimate

| Domain | Progress | Notes |
|--------|----------|-------|
| Logic configuration (LUT/FF/Arithmetic) | **~95%** | All LE positions' LUT TT decoded; FF and arithmetic mode mapped |
| CRAM address mapping | **100%** | 22 cols × 18 rows × 16 LEs = 376/376 positions fully verified |
| C4 routing switches | **~30%** | I=0 100% complete; I≠0 (24 types) need per-wire lookup table |
| R4 routing switches | **~35%** | 13/37 I-indices mapped; ~78% accuracy at standard-width columns |
| LOCAL_INTERCONNECT | **~70%** | Model verified, pair activation patterns classified |
| C16/R24 long-distance wires | **0%** | Not yet started |
| Bitstream codec | **~40%** | LUT TT read/write complete; routing read/write framework done but limited coverage |

---

## References

- [Cyclone IV Device Handbook](https://www.intel.com/content/www/us/en/docs/programmable/683853/current/cyclone-iv-device-handbook.html)
- [Project IceStorm](http://www.clifford.at/icestorm/) — iCE40 reverse engineering, methodology reference
- [Project Mistral](https://github.com/Ravenslofty/mistral) — Cyclone V reverse engineering, same chip family
- [Quartus Prime Lite](https://www.intel.com/content/www/us/en/products/details/fpga/development-tools/quartus-prime/resource.html) — Free FPGA development tool

---

## License

This project is for educational and research purposes only. The reverse-engineering results are intended for building an open-source FPGA toolchain.
