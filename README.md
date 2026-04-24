# EP4CE6 Bitstream Reverse Engineering

## What Is This Project?

The goal of this project is to **fully reverse-engineer** the bitstream format of the Altera (now Intel) Cyclone IV FPGA chip **EP4CE6F17C8**.

### What Is an FPGA?

For readers new to FPGAs: a bitstream is the file that configures the
chip's programmable logic — for Altera parts, a `.rbf` (Raw Binary File).
Background: [Cyclone IV device handbook](https://www.intel.com/content/www/us/en/docs/programmable/683853/current/cyclone-iv-device-handbook.html).

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

| Project | Target chip | Core contribution | Relation to this project |
|---------|------------|------|--------------------------|
| [Project IceStorm](http://www.clifford.at/icestorm/) | Lattice iCE40 | End-to-end open toolchain: fuzzer → `icebox` chip database → `icepack`/`icetime` bitstream tools | Original methodology template (black-box pair-diff fuzzing) |
| [Project X-Ray](https://github.com/SymbiFlow/prjxray) | Xilinx 7-series | Defined the **FASM** intermediate format and the specimen-fuzzer harness pattern | FASM format adopted here |
| [Project Mistral](https://github.com/Ravenslofty/mistral) | Altera Cyclone V | Derived the Routing Bit Mask (RBM) model from `quartus_cdb` + custom Tcl passes | Same chip family; our LI MUX model descends from Mistral's RBM work |
| [Project Trellis](https://github.com/YosysHQ/prjtrellis) | Lattice ECP5 | Diamond-driven fuzzing with routing-bit decomposition; integrates with nextpnr-ecp5 | Routing decomposition strategy reference |

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
├── synth/                  ← Open-source toolchain (Yosys + nextpnr-generic)
│   ├── ep4ce6_map.v        ← Cyclone IV techmap (LUT4/DFF primitives)
│   ├── prims.v             ← nextpnr-generic primitive library
│   ├── m9k.lib             ← M9K BRAM library stub
│   ├── synth_ep4ce6.ys     ← Yosys synthesis script (NEORV32 source paths use $HOME)
│   ├── synth_ep4ce6.sh     ← wrapper — run this instead of the .ys; envsubst's $HOME / $NEORV32_ROOT
│   └── np2fasm.py          ← nextpnr routed JSON → FASM converter
├── jailbreak/              ← CE10 fitter probes (X=32/33, Y=15 dead-cell scans)
├── results/
│   ├── rbf/                ← Collected .rbf files (~2,500 files, 368 KB each)
│   ├── fingerprint_*.json  ← 15 green-zone island corpora
│   ├── route_cells_full.json ← 13,487 sig-cache (7-tuple, Plan D' + legacy)
│   ├── route_cells_consolidated.json ← port-MUX consolidated loader
│   ├── nv_fingerprints/    ← NEORV32 per-source fingerprints
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

#### Phase 2.4: Arithmetic Mode (initial claim — later revised)

Early mining compiled an adder using `a + b` with VIRTUAL_PIN and, by diffing against a normal-mode LUT, reported "~92 arithmetic/carry-chain bits per LE" distributed on both sides of the LUT TT region. That claim turned out to be wrong: VIRTUAL_PIN produces ghost routing bits that vanish on real-pin recompiles (same lesson as Phase 5.0 for M9K/DSP). The real arithmetic activation is a **LAB-level mode switch in the block band** (frames 1692-1738), not a per-LE cell region — see the Phase 5.4 follow-up narrative for details.

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
7. **Cross-check against Quartus before chasing codec bugs** — if a design doesn't work through the open-source toolchain, first build the exact same Verilog through Quartus and flash that reference RBF. If Quartus's version blinks and yours doesn't, *then* do the cell diff to see whether the difference is where you expected. In the M5 counter episode we spent a substantial stretch chasing five "real but irrelevant" low-level bugs because we skipped this 30-second experiment — the real problem wasn't in the codec at all, it was that nextpnr-generic has no carry-chain primitive
8. **Self-loop sig-cache entries are unmineable with current templates** — for routes where src LE == dst LE (an LE feeding back into one of its own dataX inputs), the two-LUT pair mining template cannot structurally represent `src==dst`, and the diff-vs-baseline strategy fails because Quartus re-fits between compiles (including pin reassignment). Any design that relies on self-feedback (canonical example: a ripple adder that doesn't use the carry chain) cannot produce a valid bitstream through the open-source toolchain until Phase 5.4 lands — use the Quartus reference RBF in the meantime

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

### The CRC ghost: how a "working" mapping turned out to be fake (2026-04-08)

Late in the project we caught ourselves celebrating a mapping that
wasn't real. Here's what happened, in plain terms.

The bitstream is laid out as 1727 "frames" of 210 bytes each. Inside
every frame, the last 2 bytes are a CRC-16 checksum — the chip uses
them to detect flipped bits during loading. We knew that.

The chip's configuration RAM is also organized in a per-column grid.
Each column repeats every 210 bytes too (coincidence driven by the
same hardware geometry). It was tempting to assume "column position
184" inside a pair was the same as "frame position 184". It isn't —
the column grid and the frame grid **start at different bytes**, so
they are shifted relative to each other. A cell that looks like "pair
13, position 184" in column coordinates can physically be **position
208 of some frame** — which is a CRC byte.

For a while we'd been mining "R24 switch bits" and "flip-flop control
bits" by XOR-diffing two Quartus-compiled .rbf files. Any single
logic change causes Quartus to recompute the CRC for the affected
frames, so the XOR diff picks up both the real bit that changed AND
the two CRC bytes of that frame. We never noticed, and kept
cataloguing the CRC bytes as if they were real configuration cells.
The "pair delta of 419-420 bytes" we had celebrated as the spacing of
the R24 switch structure was actually 2 × 210 = 420 — the distance
between two consecutive frames' CRCs.

The smoking gun came from a one-line check: take every "mapped" cell
in the codec and ask `(offset - 32) % 210 >= 208`. If that's true,
the cell is physically a CRC byte, not a configuration byte. The
results were devastating:

- `R24 I=0` fixed offsets: **56 of 56 cells** (100%) were CRC bytes
- `FF async-reset` control cells: **448 of 476 cells** (94%) were CRC
- `FF enable` control cells: **168 of 168 cells** (100%) were CRC

The route synthesizer still passed all 1725 regression tests anyway.
At the very end of generating any .rbf we call `patch_rbf_crc()`,
which recomputes every frame CRC from the frame data. So the R24
writes flipped CRC bytes, and then `patch_rbf_crc` immediately
overwrote those same bytes with the correct values. The writes were
effectively no-ops. The real R24 bits were being emitted through
other paths (probably buried inside the LI and C4 envelopes we also
mine), which is why routes still worked on silicon. The tests looked
bit-perfect, but only because `patch_rbf_crc` was idempotently
cleaning up after a broken write path.

We disabled the affected FASM directives with a hard error, wrote the
finding into project memory as a critical warning, and queued a
re-audit of every other mapping in the codec using the same
`(off-32) % 210 >= 208` filter.

### The fix: re-mining FF control bits through a CRC-normalized diff (2026-04-08)

A few hours after the CRC ghost finding, we re-ran the FF mining with
two changes: every .rbf was passed through `patch_rbf_crc` **before**
the XOR diff (so CRC bytes cancel out cleanly), and we compiled each
variant multiple times to average over Quartus's placement choices.

Round 1 compiled {base, arst, ena} with 8 different `SEED` values at a
fixed output pin. A pleasant surprise: for a trivial D flip-flop design
the base-vs-base diff was **zero bytes** across all 8 seeds. The
"fitter noise wall" that had blocked earlier FF mining was specific to
loaded designs with routing competition — not an inherent property of
Quartus. After subtracting CRC bytes, arst and ena each produced ~75-95
cells that flipped in every single seed.

Round 2 repeated the experiment with a fixed seed but **10 different
output pins**, scattering the FF to 10 different LABs across the die.
Intersecting the round-1 and round-2 universal sets gave cells that
are both seed-deterministic AND placement-independent — i.e. truly
device-global FF control bits.

The final count was **61 arst + 61 ena** cells, with arst ∩ ena = 48
shared "any-FF-with-ctrl" enables and 13 mode-specific bits on each
side. Most live in the bitstream header band (offsets below 5282, which
`patch_rbf_crc` never touches), arranged as a compact bitfield:

- offsets 73-74 hold the main FF mode byte; arst uses bits {1,5,7} and
  {0,1,3,4,6}, ena uses a different subset of the same two bytes
- offsets 42-52, 710-729, and 1074-1081 contain supporting bitfields

The 13 CRAM-band cells per mode stayed at the same absolute offsets
across all 10 placements, which means Quartus always routes the FF
control-signal tree through the same fixed global clock/reset network
— those cells configure that network, not any specific LAB.

This gives us a three-layer picture of how FF features are encoded:

1. **Device-global ctrl feature bits** — now mined (61 per mode)
2. **Per-LE mode bit** ("*this* LE's FF uses arst") — still open
3. **Per-LE FF presence bit** — partly captured in the LUT codec

`FFCodec` in `fuzz/bitstream.py` was rewritten to load
`results/ff_remine_final.json` at import time and flip the 61 absolute
offsets directly. A round-trip test confirmed that
`FFCodec.write_arst(base)` produces a byte-identical match against a
real Quartus-compiled arst .rbf on all 61 global bits. FASM's `DFF.ARST`
and `DFF.ENA` directives are still disabled pending per-LE mining.

The old column-relative `_FF_ARST_CELLS` and `_FF_ENA_CELLS` tables are
kept in the file as deprecated stubs, with comments pointing at the
CRC-ghost memory note, so anyone reading the history can see both the
wrong and the right answer side by side.

---

### Phase 4.5 — Scaling the FASM chain to real designs (2026-04-09)

Up to Phase 4 we had proven that a FASM source file like
`X10Y10N0.LUT = 0x8888` could be compiled, flashed, and run on real
AX301 silicon. That was a huge milestone, but it had a hidden limit:
our signature cache `route_cells.json` (1725 entries) was mined from
only **15 "green-zone" LAB positions**, all with source-N = 0. A real
CPU design like NEORV32 has thousands of logic cells scattered across
the whole chip, with flip-flops at every even N slot, with feedback
paths and routing hubs that never look anything like our 15 training
islands. How do we know the chain generalises?

Phase 4.5 is the scaling experiment. Its goal: **can the FASM chain
reproduce an edge from a real NEORV32 compile, byte-for-byte, on silicon,
including in the "jailbreak" columns that Quartus officially forbids?**

#### What is a "signature cache"?

Before we answer that, it's worth explaining what our cache actually
is. It is **not** an analytic formula. When we say "the bits for route
`X5Y3N4 → X4Y3N6.datad` are the following 144 CRAM cells", we don't
compute those 144 cells from geometry — we **observed them** in a real
RBF that Quartus produced for exactly that route, and we stored the
observation in a giant JSON dictionary. The cache key is the route
tuple; the value is the list of `(byte_offset, bit_position)` pairs
that Quartus flipped.

This is the same idea as IceStorm's fuzzing approach, but applied to
**individual routing edges** rather than chip-wide features: instead
of asking "what bits does this feature control?", we ask "what bits
does this specific source-to-destination wire require?". At flash
time we don't need to know *why* those bits are what they are — we
just copy them out of the cache and XOR them into the baseline.

The catch: the cache only knows routes it has seen. If you want it to
cover NEORV32, you have to compile every edge NEORV32 uses at least
once.

#### Plan D' — a 12,000-compile factory

Step 1 was a dry-run: we parsed NEORV32's static-timing report
(`quartus_sta`-generated 3.6 GB text dump) and extracted every routing
edge the compiler actually used. After dedup and self-loop removal we
ended up with **12,259 unique edges**, each one a 7-tuple
`(sx, sy, sn, dx, dy, dn, port)`. This is the "order list".

Step 2 was the factory itself: `fuzz/plan_d_prime_factory.py`. It
spawns 12 parallel Quartus worker processes, each one assigned one
edge at a time. The worker writes a minimal two-LUT Verilog design
(`lut1 → lut2` with a clock register to keep Quartus from optimizing
it away), forces both LUTs into the exact coordinates the edge
describes, runs a full Quartus compile, and saves the resulting RBF
as `nv_pair_X{sx}Y{sy}N{sn}_to_X{dx}Y{dy}N{dn}_{port}.rbf`. Before it
starts, the factory filters out edges that its two-LUT compile
template physically cannot place: odd-N self-mappings collapsed by
the N-normalizer, IO-ring coordinates, and non-LAB columns
(X ∈ {15, 20, 27}, the M9K / multiplier blocks). 12,259 raw edges
come down to **11,762 placeable edges**; the remaining 497 are
unrepresentable in this strategy, not lost. At a steady-state rate of
~0.28–0.29 compiles per second, the final run walked the whole list
in **11 hours 16 minutes with zero failures** (11,715 ok / 0 fail on
this run, plus 47 placeable edges already on disk from an earlier
partial run).

Every finished RBF is XOR-diffed against a neutral
`nv_zero_global.rbf` baseline, and the diff cells are stored in
`results/nv_route_cells.json` keyed by the edge 7-tuple. That file is
then merged with the legacy green-zone cache into
`results/route_cells_full.json` — a unified 7-tuple sig-cache keyed
`"sx,sy,sn->dx,dy,dn,port"`, **13,487 merged entries**. The legacy
entries get lifted with `sn = 0` so the old green-zone regression
tests still pass unchanged. Cross-referenced against the full 12,259-
edge NEORV32 order list, the merged cache covers **11,762 / 12,259
(95.9%) — i.e. 100% of every edge the factory could place**. The 4.1%
gap is exactly the filter set described above, not a factory miss.
Interestingly, **zero of the 1725 legacy green-zone entries are hit
by NEORV32** — all coverage comes from Plan D' factory entries. The
legacy cache stays in the merged file because it is still load-
bearing for the green-zone regression suite, but it is dead weight
for real-world designs. See `memory/legacy_cache_zero_nv32_hits.md`.

#### Why the source-N dimension matters

A common question: why do we need `sn` in the key? Can't we just use
`(sx, sy, dx, dy, dn, port)` like the old cache?

The answer is that in a real CPU each LAB (logic array block) has 16
LE slots, and different slots have different downstream routing
envelopes. A flip-flop driving out of `N=14` does not use the same
switch-boxes as a combinational cell driving out of `N=4`, even when
both live at `X=5, Y=3` and target the same destination port.
Collapsing those two into one key would make the cache give the wrong
answer for one of them. Keeping `sn` explicit costs us a few MB of
JSON and buys correctness for every source that isn't at `N=0`.

#### The hero test: X=5, sn=4, on silicon

With the factory warmed up we picked the first edge that satisfied
three criteria: **(a)** its source column was outside the CE6
whitelist (a "jailbreak" column we only unlocked by lying to Quartus
and claiming the chip is an EP4CE10); **(b)** its source-N was
non-zero (so the 7-tuple path was actually exercised, not the legacy
`sn=0` fallback); **(c)** the factory had already produced the
corresponding `nv_pair` RBF on disk so we had ground truth to diff
against.

The edge was `ROUTE X5Y3N4 -> X4Y3N6.datad`. Source X=5 is a column
the Quartus CE6 software whitelist forbids — it simply refuses to
place a LUT there. But we already knew (from the 2026-04-07 jailbreak
probe) that X=5 is perfectly functional on silicon, the restriction
is pure software. Plan D' deliberately routes through X=5 by lying
about the device.

We wrote the hero test as a **single line of FASM**:

```
ROUTE X5Y3N4 -> X4Y3N6.datad
```

That file went into `fasm2rbf.py`, which looked the 7-tuple key up in
the merged cache, copied the 144 cells it found, XOR'd them into
`nv_zero_global.rbf`, patched the CRAM CRCs frame by frame, and wrote
a 368,011-byte RBF. We then compared this file byte-for-byte against
the factory's ground-truth `nv_pair_X5Y3N4_to_X4Y3N6_datad.rbf`:

```
CRAM band (bytes ≥ 5282):     0 differing bytes  ← exact match
Header band (bytes < 5282):   6 differing bytes  ← Quartus device-id / seed
bad CRC frames:               0 / 1727            ← all pass
```

The CRAM is the part of the RBF that the FPGA's configuration state
machine actually validates. **Zero CRAM differences** means our
FASM-generated RBF is functionally identical to Quartus's own output.
The six header-band differences sit in bytes 43–74, which carry
Quartus's compile timestamp and seed hash — the configuration state
machine never looks at them.

We flashed the FASM-generated RBF to the AX301 via `openFPGALoader`.
It loaded cleanly, `Done`, no CRC error, no EPCS fallback, the FPGA
drove its LED pins with the expected constant outputs from the two
LUTs. **First silicon proof** that:

1. `fasm2rbf` reproduces factory-grade CRAM from a 7-tuple cache hit
2. Plan D' cells are silicon-accepted even outside the training corpus
3. The CE6-forbidden column X=5 configures and runs under FASM control

The hero test validated the whole stack in one flash.

#### Two negative results worth remembering

**Negative result 1 — passive R4 dark-index mining is impossible.**
Our routing bit model `_R4_BASE_PREV` has 24 of 37 theoretical R4
switch I-indices mapped; the 13 "dark" indices never appeared in the
green-zone corpus because Quartus never picked them under low routing
pressure. We hoped that a full NEORV32 RBF, compiled under real
congestion, would light up the dark indices and let us recover their
BASE addresses by XOR-diffing against a neutral baseline. It did not
work. The NEORV32 diff set turned out to be so dense (113k cells, ~4%
of all CRAM bits) that *any* candidate BASE address scores a 55-61%
hit rate across tested wires by pure chance. A null test confirmed
the method cannot even recover the BASEs we already know to be
correct for I=0, I=1, I=2, I=10. **Lesson**: passive observation
needs a sparse signal. Dense diffs drown out the pattern you are
looking for. We marked Task G closed-negative and moved on — the
24/37 coverage turned out to be unnecessary anyway because the
signature cache short-circuits the formula path for every route it
has seen.

**Negative result 2 — "schedule the biggest hubs first" is wrong.**
When the factory was 22% through its 12k edges, we asked: could we
finish the hero-test-relevant coverage faster by reordering the
remaining 9,500 compiles to do the highest-fanout sources first?
The intuition was "main roads before alleys" — finish the big
architectural hubs early, let the small leaf sources wait. We wrote
a pure simulator (no side effects on the live factory) and ran it.
The result was the opposite of the intuition: fanout-first order
**delays** the "sources fully covered" metric by up to 4.2 hours
compared to the current lexicographic order. The reason is that
while the factory is spending 12 minutes grinding through a single
203-edge hub, the current lex order would be finishing ~60 small
sources in the same window. Lex order accidentally clusters small
sources at the head of the sorted list and is near-globally optimal
for this metric. **Lesson**: never propose a scheduling change
without a simulator proving it is strictly better on the target
metric; "obvious" hub-first heuristics can be wrong.

Both negative results are archived in `memory/r4_dark_passive_mining_dead.md`
and `memory/fanout_first_scheduling_worse.md` for the benefit of
anyone who considers the same approaches in the future.

#### A postscript: what "stuck at 96%" actually meant

A small debugging story from the day the factory finished, because it
teaches a lesson that is almost more useful than the Phase 4.5 result
itself. The factory had been running in the background all day. At
the end of the afternoon we checked in and the progress counter read
`11,762 / 12,259` — 95.9%, apparently stuck with nothing happening,
and an hour later it read exactly the same number. The knee-jerk
reading was "the factory crashed at 96% and left 497 edges unfinished,
we need to restart it and investigate".

We almost did exactly that. What stopped us was checking the actual
log file (`tmp/nvfac.log`) before touching anything. The log showed
a perfectly clean final line:

```
== done ==  ok=11715  fail=0  jb_fail=0  elapsed=676.5min
```

The factory hadn't crashed — it had finished normally, 11 hours and
16 minutes after launch, with zero failures. So where did the "497
missing edges" come from?

It came from reading two different denominators and assuming they
were the same number. The progress counter we were watching reports
`len(done)` out of `12,259` (the raw edge count from the STA dump).
But the factory, before it starts, filters `12,259` down to `11,762`
by removing edges its two-LUT compile template cannot place — odd-N
self-mappings, IO-ring coordinates, non-LAB columns. The filtered
edges never enter the work queue, so they never get marked done, so
`len(done)` asymptotically approaches `11,762`, not `12,259`. Once
the factory hits `11,762 / 12,259` it is **complete**, not stuck.

The lesson: when a long-running pipeline "freezes" near the end,
read the actual log before you restart anything. A progress counter
whose denominator is wrong looks identical to a crashed process
whose numerator got stuck — both produce the same flat number on
your status check. The difference is exactly one grep of the log.
Restarting a pipeline that has already finished is at best wasteful
(you spawn 12 Quartus workers for no reason) and at worst destructive
(if the "fix" touches the checkpoint file you can lose the work the
pipeline already did). The reflex "something looks wrong, let me
restart it" is one of the most expensive reflexes in long-running
computing, and almost every time the right first move is instead
"something looks wrong, let me read the log".

This also explains why our README Phase 4.5 section quotes coverage
as "11,762 / 12,259 (95.9%) — 100% of placeable edges". Both numbers
are true simultaneously: the factory achieved 100% of what it could,
and that 100% is 95.9% of the original edge list. Stating only the
95.9% makes the result look worse than it is; stating only the 100%
hides the 4.1% of NEORV32 structure that our current compile
template cannot reach. Both numbers are worth writing down.


### The 24-bit counter that wouldn't blink: a missing primitive, not a codec bug (2026-04-11)

This is the most expensive lesson in the project so far, and it's worth
telling at university-textbook level because the same trap is going to
catch every open-source FPGA toolchain that bolts an old vendor chip
onto a generic place-and-route engine.

**Setup.** Phase 5.3 finally had the whole open flow assembled: Yosys
synthesizes the Verilog into LUT4+DFF cells; nextpnr-generic places
them on the EP4CE6 with our hand-written `chipdb_gen.py`; `np2fasm.py`
walks the routed JSON and converts each LE+arc into FASM directives;
`fasm2rbf.py` consumes the FASM, looks up our 13,487-entry sig-cache
for each route, and writes a CRC-valid 368,011-byte `.rbf`. The smoke
test was the simplest sequential design we could think of:

```verilog
module counter_top(input CLK, output LED);
    reg [23:0] cnt;
    always @(posedge CLK) cnt <= cnt + 1;
    assign LED = cnt[23];
endmodule
```

24-bit counter. With a 50 MHz clock the top bit toggles roughly 3
times a second — the LED should be visibly blinking. The build
ran end-to-end in about 5 seconds: 31 LUT directives, 24 DFF
directives, 97 ROUTE directives, all CRC frames clean, all LI MUX
safety checks green. We flashed it.

The LED was constantly on. We tried again. Constantly off. We
tried 10 different rebuilds with various phase-ordering and stripping
fixes; the LED stayed in one state or the other but never blinked.

**The stretch of red herrings.** Each time we flashed and saw a
constant LED, we assumed the codec was *almost* right and one more
small fix would make it run. We chased — and actually fixed — five
real bugs in `fasm2rbf.py` and the sig-cache:

1. The `LutCodec` was using a "union of all minterm patterns" set
   to figure out which CRAM cells belonged to a LUT. That works on a
   sparsely-populated LAB (one or two LEs in use), but the counter
   needed 30 LEs in two adjacent LABs, and the 50+ LAB-shared bits
   in each LE's calibration started cross-contaminating each other.
   Workaround: use `predict_sram(0xFFFF)`, which XOR-cancels every cell
   that appears in an even number of minterm patterns and leaves
   exactly the 16 true truth-table cells per LE.

2. 160 sig-cache entries for routes inside the (X=4, Y=18) and
   (X=4, Y=19) LABs were missing. We re-mined them with a clean
   two-LUT pair template and got beautiful 135-cell-per-entry results.

3. A "self-loop mining template" we found in an earlier session had
   actually been mining the wrong port — its Verilog put a flip-flop
   *between* the two LUTs and hard-coded `lut2.dataa(reg)` regardless
   of which port the caller asked for. The 160 entries it produced
   were unusable. (We threw them out and re-mined cleanly.)

4. Per-LAB clock-distribution cells overlapped, in two cases, with
   the truth-table cells of one specific LE (X4Y19N4). The build
   was clearing the clock cells when it reset the LUT region.
   Fix: SET the per-LAB CLK *after* the LUT phase, not before.

5. The sig-cache mining baseline was `nv_zero_global.rbf`, which
   itself contains a small lut1+lut2 stub at (X10Y10/X10Y11). Routes
   mined against it leak 1-3 LI MUX cells in those baseline LABs.
   Fix: post-bitgen, walk the LI structure and toggle any cells in
   non-design LABs back to baseline.

Every one of those fixes was real. None of them was the actual
problem. After applying all five, the LED was still constant.

**The thirty-second test we should have run on day one.** Eventually,
out of frustration, we did the obvious thing: take the same Verilog
above, hand it to Quartus directly, and flash whatever Quartus
produced. The Quartus build was a 368,011-byte `.rbf`, just like
ours. We flashed it.

It blinked. Visibly, at about 3 Hz, exactly as expected.

So the silicon worked. The clock worked. The pin map (CLK on E1,
LED on G15) was right. The `openFPGALoader` was right. The board
was right. The Verilog was right. **The only thing wrong was our
bitstream.**

That meant we could now compare two `.rbf` files for the same
Verilog: ours and Quartus's. We diffed each against the empty
baseline `nv_zero_global.rbf` and counted cells:

```
Quartus reference (blinks):    367 cells, mostly in CRAM cols 47-48
Our codec build (constant):  1,185 cells, mostly in CRAM cols  4-7
Cells in common:                55
```

The two builds barely overlapped at all. They weren't fighting over
the same region of the chip — they were placing the design in
**completely different physical locations** using **completely
different LE primitives**.

**The actual root cause.** Cyclone IV LEs have a special direct
wire called the "carry chain": each LE's `cout` output goes
straight into the next LE's `cin` input as a dedicated wire that
**does not pass through the local interconnect MUX at all**.
Hardware adders use this to propagate the carry bit at the speed
of a wire, instead of the speed of a routing decision.

Quartus, when it sees `cnt + 1`, recognizes that this is an
arithmetic operation, switches the LE into "arithmetic mode," and
chains 24 LEs in a column with `cout → cin` direct wires. **One
LE per counter bit**, no LI MUX at all for the carry signal.

Yosys + nextpnr-generic don't know any of this. Our `chipdb_gen.py`
declares the LEs and the LI MUX wires and the C4/R4/R24 routing
tracks, but it does **not** declare the carry-chain `cout → cin`
direct wires, because we never modeled them. So when Yosys saw
`cnt + 1`, it had no carry primitive to map to, and it expanded the
addition the only way it knew how — into ordinary 4-input LUTs.
A ripple adder where each output bit is computed as something like
`A ⊕ B ⊕ Cin`, and the carry-out is `(A ∧ B) ∨ (Cin ∧ (A ⊕ B))`.
Each counter bit needed about 4 LEs to express that, so the 24-bit
counter exploded into 30+ LEs. And each bit needed its own *previous
value* as an input — which means a wire from the LE's flip-flop
output back into one of its own LUT input ports. **A self-loop**.

That's where our toolchain hit a wall it couldn't get over with any
amount of patching. The sig-cache mining template is built on
"compile two LUTs at two different locations and diff the resulting
bitstreams against the empty baseline." It cannot represent a
self-loop, because you can't put two distinct LUTs at the *same*
LE coordinate. We tried a different template that swaps the same
LUT between an external input and a self-feedback input — but
between the two compiles Quartus was free to re-pick I/O pins,
re-route everything, and the diff included so much unrelated noise
that the resulting "self-loop entries" were 100-700 cells of random
junk instead of the small handful of LI MUX bits we actually needed.

Without clean self-loop sig-cache entries, the 24 self-feedback
routes the design needed delivered no signal. Without those signals,
every counter bit's flip-flop saw a constant input. The flip-flops
latched their power-up value and never changed. The LED stayed on
the power-up state of bit 23 — which happened to be 1 with one
build and 0 with the next.

**The lesson, in three sentences.**

> When an open-source toolchain produces a bitstream that "should"
> work but doesn't, **always cross-check against the vendor's own
> build of the same Verilog as ground truth before patching the
> codec.** A 30-second compile of the test design in Quartus,
> followed by a flash and a byte-diff, will tell you immediately
> whether you're hunting a codec bug (cells in the right column,
> wrong values) or a missing-primitive bug (cells in the wrong
> column entirely, because the front-end emitted a different
> topology). The two cases need very different fixes, and treating
> them the same wastes days.

**For students reading this** — there's a subtler lesson underneath.
A modern FPGA is not "a sea of LUTs and a routing fabric." It's a
*deliberately heterogeneous* collection of primitives: LUTs, FFs,
carry chains, BRAMs, DSP multipliers, PLLs, IOBs, GCLK trees. The
vendor's tools know every one of those primitives exists and treat
them as first-class citizens. A generic place-and-route tool only
sees what your chipdb tells it about. **Anything you forgot to put
in the chipdb, the vendor will quietly out-perform you on by 3-10×
in cell count and infinity-times in performance.** The whole point
of the next phase of this project (Phase 5.4) is to teach the chipdb
about the carry chain so that `cnt + 1` becomes 24 LEs in a column
again, the way it physically wants to be.

This is also why open-source FPGA toolchains have historically
focused on the smallest possible devices first. iCE40 has almost no
heterogeneous primitives — it's mostly LUTs, FFs, and BRAMs — and
that's why Project IceStorm could land a complete open flow first.
Cyclone IV is one or two device generations richer (it has carry
chains, DSP multipliers, M9K BRAMs, PLLs, soft I/O standards), and
each one of those richer features is a separate cliff that the
generic flow falls off until someone teaches the chipdb about it.
The good news is that each cliff is climbed exactly once: once you
have a carry primitive in your chipdb, *every* future design that
does arithmetic gets it for free.

The fixes we earned during the wild-goose chase are still valuable
for any future design that needs to share a LAB between many LEs —
the LutCodec workaround, the cleanly re-mined inter-LE pair entries,
the per-LAB clock ordering rule, the post-bitgen LI cleanup.
None of them fix the counter, but together they form a working
template (`tmp/m5_counter/build_counter_sigcache.py`) for
high-density combinational and FF-only designs. Phase 5.4 will turn
the carry chain into the next cliff we climb.


### Phase 5.4 follow-up: the carry chain cliff, climbed (2026-04-13 → 04-14)

The counter forensics story above ends at the edge of a cliff. This
section is what happened on the climb. It is written for students and
tries to stay concrete.

**Where the arithmetic bits actually live.** Phase 2.4 once claimed
"92 arithmetic/carry-chain bits per LE" inside each LE's CRAM region.
That finding turned out to be **wrong** — it had been mined with
`VIRTUAL_PIN`, which (as Phase 5.0 later discovered for M9K/DSP) makes
Quartus emit ghost routing cells that disappear the moment you
recompile with real pins. When we re-mined with real pins, the
per-LE arithmetic cells vanished; they had never been there.

What is actually there: arithmetic mode is a **LAB-level mode
switch**, not a per-LE setting. When *any* LE in LAB (X, Y) turns on
arith mode, a specific pattern of ~100 bits lights up in the
**block band** (frames 1692-1738) — the same region of the bitstream
that enables M9K RAM blocks and DSP multipliers. There are **no
per-LE arithmetic CRAM cells**. The mental model: a LAB has 16 LEs
all sharing the same arith-mode configuration, so the bits that
configure it are stored once per LAB, not 16 times. This mirrors how
a CPU works — you don't have a separate ALU for every register pair,
you have one ALU with a mode field.

**The blob is position-independent across LABs.** Once we had the
~100 cells that activate arith mode in LAB (4,18), we asked: does
LAB (10,18) use a different 100 cells? LAB (4,10)? The "triangle
test" (2026-04-14) built the same 8-bit counter at all three LABs and
diffed each against its own identity twin. All three diffs produced
**byte-identical cell sets** — the same 100 offsets in the block band
light up regardless of which LAB hosts the counter. We named this the
**v4 universal blob** and shipped it as
`results/arith_blockband_v4.json` (100 SETs + 4 CLEARs). Teach the
FASM codec one table and it works everywhere on the chip.

**The blob is per-WIDTH, not per-N-slot.** A 16-bit counter needs
197 block-band cells, not 100. A 24-bit counter crossing two LABs
needs 295. So the blob depends on how many LEs are in the carry chain
— but does it also depend on *which* N-slots within a LAB you use?
A Cyclone IV LAB has 16 LEs at N slots 0, 2, 4, …, 30; placing eight
of them in the lower half (N=0..14) versus the upper half
(N=16..30) is two physically distinct placements.

Phase 1 sweep (2026-04-14, 42 Quartus builds, no hardware): for each
width `w ∈ {2, 3, …, 16}`, build a `w`-bit counter at LAB (4,18)
twice — once lower-half, once upper-half. The fitter report confirmed
both placements were honored. Then diff each counter against a
matching identity design. Result: at every width, the lower-half
diff and the upper-half diff were **byte-identical** — same offsets,
same bit positions. Placing the same eight LEs in a different half
of the same LAB does not change a single arith bit in CRAM. We had
feared needing to mine `2^16` N-slot combinations; it turns out a
per-width table (one entry per chain length) is enough. That table
now lives at `results/arith_blockband_by_width.json` and covers
widths 2..16 single-LAB plus the 16+8 cross-LAB case; round-trip
verification (apply blob to identity, diff against counter) gives
zero data and zero block-band differences for every entry.

**Two myths debunked on the way.**

*Myth 1 — "every LE has a FF-enable CRAM bit."* We tried to mine
that bit three different ways and always got noise. Cross-checking
against Quartus: every Cyclone IV LE has a flip-flop that is
**always physically present**. Whether you *use* the flip-flop or
the combinational output is selected by downstream routing, not by a
CRAM bit. Our old `dff_cells_mined.json` was routing infrastructure
noise. The FASM `DFF` directive is now a parsed no-op.

*Myth 2 — "carry chain needs external feedback routes."* An `N`-bit
counter is `Q <= Q + 1`, so each FF's `Q` output feeds back into the
ALU's B input. Our early Yosys techmap inserted a "Route-A buffer"
LUT to carry that feedback through the local interconnect. Doing so
doubled the LE count and created self-feedback routes that the
sig-cache cannot mine cleanly. When we looked at Quartus's own
counter: **zero external route cells for the feedback.** Cyclone IV
has an internal wire from the FF output directly into the ALU's B
input; no LI MUX is involved. The fix in `synth/ep4ce6_map.v` was to
bind the FF's `Q` directly to `CE6_CARRY.B` with no intermediate
buffer. An 8-bit counter now uses 8 LEs and 0 route cells, same as
Quartus.

**What's on silicon right now.** On 2026-04-13 we flashed an 8-bit
counter assembled entirely from FASM (identity baseline + eight
`LUT_ARITH = 0x0000` directives) onto an AX301 board. The LED
blinked at the expected rate, behavior bit-identical to Quartus's
own compile of the same Verilog. An identity `Q <= Q` negative
control produced a dark LED. That is the full proof: the block-band
arith blob is the real activation, the universal blob works at the
chosen LAB, LE-internal feedback is sufficient, and the FASM
`LUT_ARITH` directive is end-to-end wired up correctly. Widths 9..16
and the 24-bit cross-LAB pattern are shown byte-identical to Quartus
output under `diff`, but await hardware re-verification when the
board is next on the desk.

**One sentence take-away.** The carry chain was not a second set of
cells per LE (as we had guessed); it is a single LAB-wide mode switch
stored in the same block band that holds M9K and DSP activation, and
its bit pattern depends on the chain's *length* but not on *which*
LEs in the LAB are part of it.


## Open Toolchain End-to-End: Native Path and ζ Escape Hatch

Two separate paths reach silicon from the open bitstream codec — a
**native** path (Yosys → nextpnr → FASM) and an **escape hatch** (take
a Quartus RBF, diff against a baseline, emit pure `BIT` directives).
Both produce valid flashable bitstreams via the same `fuzz/fasm2rbf.py`.
The native path is the long-term goal; the escape hatch is the
guaranteed-to-work fallback for any design Quartus can build.

### Native path

```text
.v / .vhd
   │
   ├── Yosys techmap (synth/ep4ce6_map.v, synth/prims.v)
   │     → LUT4, DFF, CE6_CARRY, EP4CE6_M9K, GENERIC_IOB
   │
   ├── nextpnr-generic (chipdb from fuzz/chipdb_gen.py)
   │     → placed + routed JSON
   │
   ├── synth/np2fasm.py
   │     → FASM (LUT, ROUTE, LUT_ARITH, M9K_MODE, IOB_*, GCLK_PIN,
   │            LAB_CLK_SEL, LAB_CLK_SEL_LE, OUTROUTE_G15, IOB_PAD_NV)
   │
   ├── fuzz/fasm2rbf.py  (+ patch_rbf_crc)
   │     → .rbf (368 011 B, CRC-patched)
   │
   └── openFPGALoader -c usb-blaster
```

HW-validated designs along this path: registered AND gate
(KEY2&KEY3→DFF→LED0) at LAB(16,4), 5-bit carry counter, M9K smoke
9×512 RAM, clock-pin pipeline on all 12 F17-reachable pins.

### ζ escape hatch (Quartus gold → BIT FASM)

For any design that is too dense for the current chipdb routing model
(NEORV32-scale, ~6000+ LEs), `scripts/bit_workaround/quartus_gold_to_bit_fasm.py`
provides a **deterministic** bypass:

```text
design.v / .vhd
   │
   ├── Quartus compile → design.rbf (gold)
   │
   ├── scripts/bit_workaround/quartus_gold_to_bit_fasm.py
   │     → BIT-only FASM (one BIT directive per differing bit vs
   │       results/rbf/nv_zero_global.rbf baseline)
   │
   ├── fuzz/fasm2rbf.py  (+ patch_rbf_crc)
   │     → .rbf byte-identical to Quartus gold (cmp confirms)
   │
   └── openFPGALoader -c usb-blaster
```

This is useful because:
1. It **proves** the codec round-trip is correct at SoC scale — the
   rebuilt RBF is literally the same bytes Quartus produced.
2. It is a real escape hatch. Users who hit the chipdb routing wall
   have a bounded workflow: compile in Quartus once, everything
   downstream stays open-toolchain.
3. The BIT FASM is an inspectable intermediate — auditable line-by-line
   against the codec's CRAM geometry, usable as a substrate for
   bitstream mutation experiments (see "Long-term direction" below).

HW-validated: two_lab AND→DFF cross-LAB route (2026-04-22), lits_pair
route-family reconstruction (2026-04-23), and the **full NEORV32
bootloader** (4712 LE / 2367 DFF / 19 M9K) on AX301 silicon at
19200-8N1 UART (2026-04-23). ζ + fasm2rbf total wall time ≈ 0.5 s
regardless of design density; it scales with RBF size (fixed
368 011 B), not LE count.

**Linux extended test (2026-04-24)**: `boot_linux.py --rbf` drove the
full Quartus-flow host script against the ζ-rebuilt RBF — stage2
upload, baud switch, kernel xmodem (1.5 MB, CRC match), DTB +
initramfs all OK, **Linux 6.6.83 booted on RISC-V** and ran for
~150 s (devtmpfs mounted, ttyNEO0 console attached, exec'd /sbin/init)
before a kernel panic at `kernel/cred.c:103`. The panic is **not a
ζ regression** — the RBF is SHA256-identical to Quartus gold; the
panic is a RISC-V nommu kernel edge case. The ζ validation objective
(open toolchain produces a silicon-functional NEORV32 bitstream)
is met.

### ζ production pipeline (CI-friendly)

The three-step ζ conversion (Quartus → BIT FASM → rebuilt RBF → flash →
UART verify) is wrapped by `scripts/bit_workaround/zeta_pipeline.py`
into a single command with machine-readable gates:

```bash
# RBF input, round-trip + byte-identity only (no hardware):
python3 scripts/bit_workaround/zeta_pipeline.py gold.rbf

# Quartus project input (runs map/fit/asm/cpf first):
python3 scripts/bit_workaround/zeta_pipeline.py path/to/design.qpf

# Full end-to-end with board:
python3 scripts/bit_workaround/zeta_pipeline.py gold.rbf \
    --flash --uart-seconds 10 --baud 19200 --expect "NEORV32"
```

Exit 0 iff every requested gate passed; `--json` emits a machine-readable
report. The pipeline hard-gates on `cmp -s rebuilt gold` after fasm2rbf —
a regression anywhere downstream in the codec surfaces immediately and
before any flash cycle is wasted.

Two companion tools:

- `scripts/bit_workaround/zeta_rbf_diff.py A.rbf B.rbf` — region-aware
  diff that splits the 368 011 B RBF into preamble / header-data /
  header-crc / fabric-data / fabric-crc / postamble and reports
  per-region byte/bit differences plus a frame histogram. Avoids the
  "any data bit flipped → CRC chain churn → raw `cmp` unreadable"
  failure mode.
- `scripts/bit_workaround/zeta_selftest.py` — sub-second CI-style smoke
  test of all three no-hardware gates against the HW-validated
  `two_lab.rbf` gold (1710-bit invariant). Suitable as a pre-commit
  hook. Exit 0 iff the full ζ → fasm2rbf → byte-identity chain is
  green.

### When to use which

| Design size / routing | Native path | ζ escape hatch |
|-----------------------|-------------|----------------|
| Small (≤ 50 LE), single LAB | ✅ primary | (redundant) |
| Medium (50–500 LE), cross-LAB | ✅ if sig-cache covers routes | ✅ fallback |
| Dense (> 1000 LE) / NEORV32-class | ❌ chipdb routing model blocks | ✅ primary |
| Carry chains, M9K, clock pins | ✅ HW-validated primitives | ✅ works by construction |

The native path is still the frontier — the chipdb routing model is
the sole remaining blocker for Verilog-to-silicon without Quartus. ζ
closes the practical gap in the meantime.


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

- [~] Phase 3.19: Map remaining R4 I-indices — **24 of 37 mapped** (I=6 removed 2026-04-08 after Option-1 fingerprint recheck; later re-audit shows I=6 and I=8 are non-LAB CRAM needing a different column model). Same-day `fuzz/r4_remine.py` analytic re-audit (942-route STA corpus vs `route_cells.json` absolute cells, zero differential bias) **reversed** the earlier per_route_delta audit: I=0/1/2/4/7/10/13/15/16/17/18/20 hit 60-97%, table is **healthy for most LAB-CRAM entries**. Confirmed bad entries: I=12 (29%), I=14 ((3191,3191) broken), I=6/I=8 (non-LAB CRAM). The formula is unused by `route_synth` because the signature backend short-circuits before it runs, not because it's broken. 13 remain unmapped (5,9,24,28,29,30,31,32,33,104,116,125) — STA-corpus blocked
- [ ] Phase 3.20: M9K/DSP boundary column fix (X=13/26 large columns need sub-region address model)
- [ ] Phase 3.21: C16 long-distance wire modeling (not yet started)
- [x] Phase 3.22: **LI mode-selection rule — CLOSED NEGATIVE**. T9 + T10 orthogonal-grid corpus (12 sources, 374 compiles, 414 mappable rows, `fuzz/li_mode_grid_mine.py` + `li_mode_analyze.py` + `li_mode_tree.py`). Clean rules: `dy∈{2,3,21}→edge_even_b0` (100%), `adx==0→paired` (79%), `dx>30∧dy>7.5→paired`. Middle leaf `dy>3∧dx≤24.5∧adx>0.5` (n=247, 60% of corpus) stuck at **52% coin flip** — unchanged by 2× corpus growth and sx/dx decorrelation. Conclusion: paired vs alternating is **not a function of the static routing key**; likely driven by Quartus placement seed / LI channel occupancy. Further corpus expansion will not help. Yellow-zone fallback keeps `paired` as a weak prior (both modes are hardware-safe).
- [x] Phase 3.23: **C4 I≠0 fog-of-war sweep** — `fuzz/c4_inz_sweep.py` mined 19 new (X,I) mappings from existing routing_paths corpus, taking `_C4_FIXED_OFFSETS` from 25 → **44 mappings**. Green-zone regression still 58/58 bit-perfect.
- [x] Phase 3.24: **Non-LAB column identity resolved** — `jailbreak/probe_blocks.v` (12× altsyncram + 8× lpm_mult, virtual-pinned). Quartus placed blocks at `M9K_X15_Y*`, `M9K_X27_Y*`, `DSPMULT_X20_Y*`. So of the 3 true non-LAB columns (post-jailbreak): **X=15 and X=27 are M9K RAM columns**; **X=20 is the embedded 9×9 multiplier column**. PLLs live at the die periphery, not in any X column.
- [x] Phase 3.25: **Jailbreak fabric CLOSED on silicon (2026-04-07)** — both axes silicon-validated end-to-end through the codec. **X=32 column**: LCCOMB_X32_Y10_N0 mask 0x8888 ran on AX301; codec calibrated, `COLUMN_BASE` extended to all 28 LAB columns at standard 7350-byte stride. **Y=15 ghost row**: LCCOMB_X10_Y15_N0 mask 0x0357 = `(K1∧K2)∨(K3∧K4)` ran on AX301 (`fuzz/demo_y15_keys2led.py`). +65% fabric is production-ready on real CE6 silicon
- [x] Phase 3.26: **Route-synth green zones expanded 3 → 15 source LABs** (`fuzz/fingerprint_raw_mine.py` codec-blind XOR mining, header filter); 686/686 routes bit-perfect. `results/r4_iindex_table.json` (942 entries) silently used by `route_synth.py:206` for I-index hint selection per (src,dst,port) geometry
- [~] Phase 3.27: **M9K CRAM probe — superseded by Phase 5.0**. Legacy `m9k_probe_mine.py` archived 237/299 cells; Phase 5.0 proved 76-81% were CRC byte ghosts and CRC-stripped them to 58 (identical for `GLOBAL_ON` and `COL15_ON` — no column-specific signature actually exists). Y-position model still abandoned; STA wire path also proved a dead end (see Phase 5.0)

- [x] Phase 5.0: **Non-LAB blocks (DSPMULT + M9K) — real-pin re-mine, 2026-04-08**. LOC syntax cracked (`fuzz/{mult,m9k}_loc_discover.py`): hierarchical MegaFunction node path, not coordinate alias — DSPMULT uses `lpm_mult:u|mult_qpl:auto_generated|mac_mult1`, M9K uses `altsyncram:u|altsyncram_3ov:auto_generated|ALTSYNCRAM`, 42 legal DSPMULT sites (Y1..21 × N{0,1}) + 126 legal M9K sites (X∈{15,27}). **Two new rules** established:
  - *Never mine non-LAB blocks with VIRTUAL_PIN* — the first-pass 62-cell `MULT_GLOBAL_ON` under VIRTUAL_PIN was a Quartus ghost-routing hallucination with 0 overlap vs a real-pin recompile. Retagged `MULT_VIRTUAL_PIN_ARTIFACT` (`fuzz/mult_noise_test.py`, memory `feedback_virtual_pin_mining_is_fiction.md`).
  - *Non-LAB mining must filter CRAM-only (off≥5282)* — 5-seed null-hypothesis test (`fuzz/mult_header_noise.py`) on identical lpm_mult designs proved bytes 44 and 73 have a **4-5 bit per-SEED noise floor** touched by every non-LAB block **and** by FF arst/ena. Any "header-band finding" without CRAM-only filter is fiction. Killed the earlier `SIGNED_CORE = 4 cells` result from `fuzz/mult_param_sweep.py` and puts the FF layer-1 byte 44/73 claim under re-audit (memory `feedback_header_band_noise_floor.md`).
  - **Results** (CRAM-only, CRC-stripped): `MULT_GLOBAL_ON_REAL` = **29 cells** universally toggled by any DSPMULT (42-site sweep); `M9K_GLOBAL_ON` = **58 cells** CRC-stripped, cross-validated 55/58 against the fresh 126-site real-pin sweep; `MULT ∩ M9K = 0` (per-block disjoint); X=15 and X=27 universals are byte-identical (confirming no column-specific M9K signature).
  - **Two non-LAB config bands** discovered: (1) **block enable/mode band, frames 1692-1738** hosts mult 29 + M9K 58 in disjoint positions; (2) **block clock-net band, frames ~1007-1013** — `fuzz/mult_reg_sweep.py` (`lpm_pipeline` ∈ {1,2,3}) isolated the first single-bit semantic field `DSPMULT_CLOCK_ENABLE = (209891, bp 4)`, and M9K's 4 per-site clock bits sit **1-3 bytes away** from the mult clock bits in frames 1010/1013 at the same bp=4 — slot-reserved per-block clock register.
  - **Dead ends**: STA wire extraction (`fuzz/mult_sta_wires.py`) returns only chip-edge IOBUF — Quartus treats DSPMULT as a black-box cell; width/signed/pipeline decoding beyond CLOCK_ENABLE is buried in header noise; `altpll` has no X/Y LOC (off-fabric, needs `PLL_1`/`PLL_2` singleton names), deferred

- [x] Phase 4: **FASM toolchain CLOSED on silicon (2026-04-08)** — `fuzz/fasm2rbf.py` + `fuzz/rbf2fasm.py` implement a minimal FASM dialect (`LUT`, `ROUTE`, `BIT`, `SRC`) driving `LutCodec` + `RouteCodec` + `patch_rbf_crc`. Signature backend (`fuzz/route_signatures.py`, **1725** route cell-sets) short-circuits `synth_route` for yellow-zone and Y=15 jailbreak sources. **Port-MUX consolidated loader (2026-04-08)**: every `(src,dst,dn)` group resolves into a shared `common` preamble + per-port `delta` of exactly 4 cells (2 adjacent byte pairs at 840-byte LI-pair×4 spacing); 225/225 full 4-port groups match a "3+1" equivalence class with datab always the odd port. `route_signatures.load_cells()` now prefers `results/route_cells_consolidated.json` (34% file / 37% cell savings) with invariant `common ∪ port_delta[p] == route_cells[key+",p"]` self-tested 1725/1725. Set-cover decomposer (`fuzz/route_decompose.py`) collapses multi-route + cross-source CRAM diffs into clean directives. Regression suite: **1725/1725** single-route, 41/42 multi-route (1 pre-existing), 3/3 cross-source, 15/15 green-zone islands (686/686) — all bit-perfect. Hardware closure: `X10Y10N0.LUT = 0x8888` (AND(K1,K2)) one-liner flashed to AX301 via `fasm2rbf`, silicon behavior matched

- [x] Phase 4.5: **Plan D' sig-cache — NEORV32 coverage (2026-04-09)** — 12-worker parallel factory (`fuzz/plan_d_prime_factory.py`) compiled 11,715 placement-forced 2-LUT pairs from NEORV32 STA edges. 7-tuple sig-cache `results/route_cells_full.json` = **13,487 entries** (legacy 1725 lifted to sn=0 + 11,762 factory). Coverage: **95.9% of NEORV32 edges** (100% of placeable). Hero test X=5 jailbreak column FASM → AX301 silicon-accepted.
- [x] Phase 5.0: **Non-LAB blocks (DSPMULT + M9K) — real-pin re-mine (2026-04-08)** — see In Progress section above for full detail
- [x] Phase 5.2: **M9K init content codec — Stage A+B CLOSED (2026-04-09)** — 3-band partition (data/mode/clock); 2D linear formula `byte(w,bit) = anchor + (w//2)*210 - (w%2) - 2*bit, bp=6`; 31 NEORV32 M9K sites calibrated (`M9K_INIT_ANCHORS` = 33 entries); LOC fix (use instance name `-to "u"`); READ 512/512, WRITE 0 CRAM diffs vs Quartus. `fuzz/m9k_init_basis.py`

- [x] Phase 5.4: **LE carry chain in open flow — HARDWARE-VERIFIED on AX301 (2026-04-13)** — arith activation is a LAB-level mode switch in the block band (frames 1692-1738), not a per-LE cell region; position-independent across LABs (v4 universal blob, `arith_blockband_v4.json`); per-width table covers widths 2..16 single-LAB + 16+8 cross-LAB (`arith_blockband_by_width.json`, all entries round-trip zero-diff vs Quartus). Four pieces landed: chipdb `cout→cin` pips (8,126), CE6_CARRY techmap primitive (LE-internal FF→ALU feedback, no Route-A buffer), np2fasm `LUT_ARITH` emission, fasm2rbf `LUT_ARITH` directive. Identity + 8× `LUT_ARITH=0x0000` blinks on AX301 bit-identically to Quartus counter RBF; identity `Q<=Q` negative control stays dark. DFF confirmed silicon-default (no per-LE CRAM enable cell — FASM `DFF` is now a parsed no-op). Pedagogical narrative at "Phase 5.4 follow-up" section above.

### Future Work

- [ ] Phase 5.1: Complete routing codec coverage (target: all wire types >90%; C16 + remaining R4 I-indices still open) — distinct from the already-done Phase 5.0 non-LAB work
- [ ] Phase 5.2b: Non-LAB block parameter decoding beyond CLOCK_ENABLE and M9K INIT — need an intra-block differential probe that bypasses the header noise floor, STA opacity, and the lack of observable per-site configuration; PLL probe via `PLL_1`/`PLL_2` singleton LOCs deferred here
- [~] Phase 5.3: **Open-source toolchain — Yosys + nextpnr-generic + FASM (PARTIALLY OPEN, arithmetic designs now hardware-verified via Phase 5.4)**. Target: replace Quartus with `Verilog → Yosys → nextpnr-generic → np2fasm → fasm2rbf → openFPGALoader`. Current state:
  - `fuzz/chipdb_gen.py`: generates nextpnr-generic Python chipdb (8,241 bels, 59,611 wires, 1.38M pips) with GCLK broadcast, intra-LAB direct pips, 4-level pip cost hierarchy (SIG=1 < INTRA=2 < LOCAL=5 < HOP=20), plus **8,126 `cout→cin` direct pips** for carry chain (Phase 5.4).
  - `synth/ep4ce6_map.v` + `synth/prims.v` + `synth/synth_ep4ce6.ys`: Yosys techmap chain (LUT4 + DFF + CE6_CARRY for `$alu`). Run via `synth/synth_ep4ce6.sh` — the wrapper envsubst's `$HOME` / `$NEORV32_ROOT` so the VHDL paths travel.
  - `synth/np2fasm.py`: extracts logical connectivity from nextpnr routed JSON, looks up sig-cache for FASM ROUTE directives, walks the carry chain and emits `LUT_ARITH`
  - `fuzz/fasm2rbf.py` directives that work end-to-end: `LUT`, `ROUTE` (6/7-tuple), `GCLK`, `DFF` (parsed no-op — FF is silicon default), `BIT`, `SRC`, `LUT_ARITH`, `M9K.INIT_{w}x{d}` (for 33 calibrated 9x512 anchors; FASM round-trip verified in `fuzz/test_m9k_init_directive.py`, 5/5). CRC patcher integrated. np2fasm M9K emission is a stub (`_emit_m9k_init` + xfail test `fuzz/test_np2fasm_m9k.py`) — Yosys `$__M9K_SP_` techmap rule drafted in `synth/ep4ce6_map.v` behind `M9K_TECHMAP` ifdef, chipdb M9K wire pips still TODO.
  - **M5 counter — 8-bit counter now hardware-verified via the open flow (2026-04-13).** The FASM path (identity baseline + 8× `LUT_ARITH = 0x0000`) blinks on AX301 with bit-identical behavior to Quartus's own compile. Widths 2..16 single-LAB and the 16+8 cross-LAB case are byte-identical to Quartus output under `diff`; hardware re-verification pending. See Phase 5.4 follow-up section above for the climb.
  - **Real fixes earned chasing M5 (still useful for future multi-LE-per-LAB designs)**: LutCodec high-density LAB workaround (`predict_sram(0xFFFF)` filters LAB-shared cells); sig-cache mining template pitfall documented (must use `gen_two_luts_single_input_clocked` from `verilog_gen.py`); 160 cleanly re-mined (4,18)/(4,19) inter-LE pair entries added to `route_cells_full.json`; per-LAB CLK ordering fix (must run after the LUT phase reset); post-bitgen LI cleanup for sig-cache infrastructure leakage. Working multi-LE-per-LAB build template at `tmp/m5_counter/build_counter_sigcache.py`.
  - **IOB FASM cell map landed (2026-04-14)**: `IOB_IN PIN_X` / `IOB_OUT PIN_X` directives reproduce all 44 single-axis ground-truth RBFs bit-perfect via XOR delta from `iob_in_E15.rbf` baseline. `np2fasm` emits one directive per placed GENERIC_IOB. Cross-axis pin combos still leak ~57 joint-placement bytes (needs 2D K×LED sweep).
  - **GCLK pipeline landed + HW verified (2026-04-14)**: `GCLK_PIN` + `LAB_CLK_SEL` + `LAB_CLK_SEL_LE` FASM directives compose as XOR-delta on an AUTO-mode baseline; source encoding is per-pin (E1=3 cells, R8=5, N1=38; zero cross-pin overlap within the legacy E1/R8/N1 triad). 26 (LAB, N) combinations round-trip bit-perfect; `fasm2rbf` 11/11 + `np2fasm` 7/7 tests. Retiring the legacy `nv_zero_global.rbf` baseline is pending the next HW flash pass.
  - **GCLK + IOB_CLK_INPUT extended to all F17 dedicated clock pins (2026-04-15)**: `GCLK_PIN` and `IOB_CLK_INPUT` now cover **12 clock pins each** — E1, R8, N1 plus 9 newly mined dedicated clock pins (M1, M2, T4, R4, M16, M15, E15, A14, B14). Two of the 13 dedicated F17 pins are unfittable: PIN_E2 (the LVDSCLK_00P side of the E1 diff pair — Quartus refuses placement) and PIN_H1 (reserved as `ALTERA_DCLK` JTAG config). Generalised mining tools: `scripts/iob_slice_mining/compute_clk_pin_hdr.py --build --pin {PIN}` (IOB_CLK_INPUT, parallelisable, ~16 s/pin) and `fuzz/clk_pin_autoforce_probe.py --pin {PIN}` (GCLK_PIN, 6 builds × ~16 s/pin). Tests: `fuzz/test_iob_baseline_nv_directive.py` 15/15 (per-pin loader + per-pin gold-RBF round-trip across all 12 mined pins) + `fuzz/test_gclk_pin_directive.py` 11/11 (per-pin loader sanity). Notable: same-bank dedicated clock pins (E15/M15/M16; A14/B14) share spine cells (12-22 cells overlap), unlike the disjoint legacy triad — XOR semantics still compose cleanly under double-emit, but a multi-GCLK_PIN design will see partial cancellation rather than a clean union.
  - **IOB→SLICE route mining, HW-verified template (2026-04-14)**: `scripts/iob_slice_mining/` — paired two-LE mining template (`template_pairs.py` + `mine_iob_routes.py`) produces diff-able pair-vs-zero deltas (~200 cells/entry) AND functional silicon (paired RBF `iob_pair_E16_10_4_0_dataa.rbf` flashed on AX301 drives KEY2→LED0 correctly). 3-layer decomposition (`decompose_deltas.py`) splits every raw delta into universal_infra (98 cells) ∪ pin_footprint(pin) ∪ pure_common(target) ∪ ≤2-cell residual, verified across 15 entries. Port MUX is Quartus-canonicalized (all 4 ports → byte-identical delta). Sig-cache injection pending (pure_common is relative to `iob_zero`, not `nv_zero_global`).
  - **IOB_ROUTE FASM directive + frame-split bridge + single_le sweep (2026-04-15)**: `IOB_ROUTE PIN_X -> XaYbNc.port` wired into `fasm2rbf` (8/8 tests); CRAM band bit-perfect vs the HW-verified pair RBF via `absolute_cells`. `IOB_BASELINE_NV` (132-bit-cell / 74-byte hdr bridge from `nv_zero_global` to `iob_in_E15`) and `IOB_CLK_INPUT PIN_{E1,R8,N1}` (40 / 64 / 70-cell clock-bank pin activate, mined per-pin via `scripts/iob_slice_mining/compute_clk_pin_hdr.py --build --pin {PIN}`) close the frame-split so end-to-end FASM designs can build on a single `nv_zero_global` base. An opt-in `single_le_cells` section in `results/iob_to_slice_sigcache.json` overrides `absolute_cells` when present and strips pair-template secondary-LE decoration for single-LE designs — derived by solving `IOB_ROUTE_primary = gold_delta ^ (all other directives)` against the Quartus gold RBF. `scripts/iob_slice_mining/sweep_single_le.py` parallelises this derivation across every supported (pin, target) combination: **15/15 entries now landed** (3 pins E16/E15/M16 × 5 targets 10,4,0 / 10,4,2 / 10,4,4 / 10,10,0 / 16,4,0), each byte-identical to Quartus gold through the full 8-directive stack. Unlocked the last six entries via two probe-infrastructure fixes: `clk_lab_sel_probe.py` now falls back to `SRC_ALT=(22,10,0)` when `target_lab` matches the default SRC LAB (was colliding at `LCCOMB_X10_Y10_N0`), and `N_SLOTS` now includes N=2 so `LAB_CLK_SEL_LE X{x}Y{y}N2` becomes available. Tests: `fuzz/test_iob_baseline_nv_directive.py` 13/13 (3 clock-input pins covered: E1, R8, N1, each round-tripping bit-perfect against its own Quartus gold) + `fuzz/test_iob_route_directive.py` 8/8.
  - **Stage 0 HW flash session (2026-04-16)**: 24 RBFs flashed on AX301 — **23 PASS, 1 FAIL** (DSPMULT_GLOBAL_ON falsified on silicon). Key results: `NV_BASELINE_PACK` silicon-equivalent to nv_zero_global (Phase 7 retirement unblocked); 14/14 IOB_ROUTE pairs silicon-correct; 7 new GCLK_PIN clock pins programming-verified (M15 full-PASS with hold-KEY2 + pulse-KEY4 protocol; M1/M2/T4/R4/A14/B14 programming-clean); M9K smoke design accepted by chip (codec pipeline silicon-clean); DSPMULT 23-cell set leaks on silicon → bisection roadmap opened.
  - **Stage 0 round-2 flash (2026-04-17)**: M9K_MODE `_inferred_goldintersect` **PASS** — np2fasm emission ungated for all w=9 sites. IOB_OE PIN_R5 **FAIL** (LED stuck-on) — bisected to 2 leaky cells `(363236,2)+(363672,2)`, cleaned 38-cell set PASS, loader masks both. LUT_ARITH_MULTI_LAB WIDTH=17 **FAIL** (LED stuck-off) — multi-LAB carry stays gated. DSPMULT_GLOBAL_ON bisected in 4 layers (23→12→6→3→1): leaky cell = `(363236, 2)` at frame 1729; cleaned 22-cell set PASS.
  - **LAB_CLK_SEL_LE extended to N=6/8 for all 14 LABs (2026-04-16)**: `N_SLOTS` now `(0, 2, 4, 6, 8)`. 56 new Quartus builds. LAB(10,16) invariant tightened 53→49 (4 cells migrated to per-LE buckets). `clk_lab_sel_per_le.py` refactored N-agnostic. 49/49 tests green.
  - **IOB_IN_BIDIR / IOB_OUT_BIDIR directives landed (2026-04-17)**: `per_pin_input`/`per_pin_output` cell dispatch for bidirectional IOB pads (cells UNIQUE to each pin across the 33-pin sweep, no anchor double-flip). 16 sdram_dq pin coverage. `_IOB_BIDIR_FALSIFIED` per-pin mask table (R5 OUT: 2 fabric-band cells stripped). np2fasm emits BIDIR variants for bidir pads automatically. Tests: 5/5 directive + 6/6 np2fasm.
  - **IOB_OE FASM directive landed (2026-04-16)**: `IOB_OE PIN_X` for 16 NEORV32 sdram_dq pins. Specimen-factory mining (oe_on vs oe_off per pin, 3-seed routing-invariance probe, 0-drift across all 16). Cell counts 37..55 per pin, 21-cell universal intersection. HW bisection at R5 isolated 2 leaky cells; loader masks them. 9/9 tests. np2fasm emission not yet wired (needs Yosys `$tribuf` techmap).
  - **Formula-based LutCodec landed (2026-04-17)**: `LutCodec.from_cram_model(x, y, n)` eliminates per-LAB SQLite calibration. Uses CRAM address model to generate synthetic minterm patterns. `fasm2rbf.py` bitgen falls back automatically when `from_db()` raises ValueError. All 65536 masks match DB-backed codec at (10,10,0). **Known limitation**: pair mapping is WRONG for positions other than (10,10,0) — 192/233 LUTs produce incorrect truth tables. Root cause: bit-to-cell pair ordering varies by (x,y) in ways the formula doesn't capture. This is the primary blocker for the pipeline test.
  - **Sig-cache demand mining expanded to 38,683 entries (2026-04-18→19)**: Route mining from NEORV32 STA edges brought the 7-tuple sig-cache from 13,487 to 38,683 entries. 0 route sig-cache misses for NEORV32 v2 build. 8 IOB→SLICE misses remain (J16/M2/E16 → Y=21 targets).
  - **M9K pipeline closed end-to-end (2026-04-16)**: Full Yosys → `memory_libmap` → prepack_m9k → np2fasm → fasm2rbf path produces CRC-valid RBFs. Smoke design (9×512 RAM) round-trips user data pattern correctly. Three np2fasm fixes landed (blackbox module selection, Yosys binary int parsing, x/z char handling). M9K_MODE `_inferred_goldintersect` emission ungated for all w=9 sites (HW-validated).
  - **NEORV32 open-toolchain RBF auto-reset on flash (2026-04-18)**: Both v2 and v3 RBFs cause FPGA auto-reset to factory config. Root cause: chipdb LOCAL bus has only 4 tracks (~2080 wires total) vs real silicon's O(100k) routing resources. At 6500+ LEs, nearly every LOCAL wire is overused → driver conflicts → protective reset. All structural safety checks PASS; the problem is routing model capacity, not directives. Fix requires either SIG-cache-aware placement or hierarchical routing model.
  - **Pipeline test E2E design (134-LE, 2026-04-18→19)**: 28-bit counter → LED heartbeat + UART TX "Hi!\r\n" + KEY3/KEY4 passthrough. Quartus gold PASS on silicon. Open-toolchain build: 0 route misses, but **FPGA RESET on flash**. Root cause: `from_cram_model()` pair mapping bug — 192/233 LUTs use wrong bit-to-cell mapping, corrupting LUT functions. K2→LED3 and K4→LED2 work (partial pipeline success), but F16/G15 outputs fail. F16 output routing mined differentially (40 data cells: 38 header + 2 block band), but adding them triggers reset due to cumulative LUT layer damage.
  - **Carry chain disabled for NEORV32 (2026-04-17)**: `alumacc` removed from Yosys flow — 684 chain discontinuities → LUT4 arithmetic instead. Reduces to 6533 LEs (292 fewer). CE6_CARRY infrastructure retained for future arch work.

- [x] Phase 5.4: **LE carry chain in the open flow (HARDWARE-VERIFIED 2026-04-13)** — arith mode activation lives in the block band (frames 1692-1738, bp=2), not in LAB CRAM columns, and is a per-LAB mode switch, not a per-LE cell. Four pieces landed: (1) `chipdb_gen.py` declares 8,126 `cout→cin` direct pips between adjacent LE bels; (2) `synth/ep4ce6_map.v` + `synth/prims.v` add the CE6_CARRY primitive so Yosys lands `$alu` on chained LEs with the FF's `Q` wired directly into `CE6_CARRY.B` (no external "Route-A" buffer); (3) `synth/np2fasm.py` walks the carry chain and emits `LUT_ARITH` directives; (4) `fuzz/fasm2rbf.py` applies the arith blob from `results/arith_blockband_v4.json` (universal, position-independent at any LAB) for 8-LE half-LAB chains, or from `results/arith_blockband_by_width.json` (widths 2..16 single-LAB + 16+8 cross-LAB) for other chain lengths. AX301 silicon-accepted: identity + 8× `LUT_ARITH=0x0000` blinks bit-identically to Quartus's counter RBF; identity `Q<=Q` negative control stays dark.

- [x] Phase 6: **σ⁻¹ 3-key LutCodec discovery (2026-04-21)** — the long-outstanding "pair mapping wrong" bug in `LutCodec.from_cram_model()` closed by adding a third discriminator axis: the previous `(foff, fb8)` 2-key table lookup was ambiguous across Y-groups, and adding `group = (y-2)//3` as the third key resolves it. New σ⁻¹ table `results/sigma_inv_fb8_groups.json` has **1,904 entries** (96% verified, 0% identity fallback), 5-level fallback chain (exact 3-key → nearest-foff 3-key → exact 2-key → nearest 2-key → identity). Known residue: Y=3 row (80 positions, wrapped addresses). Formula-based LutCodec is now silicon-reliable at all positions except Y=3.

- [x] Phase 6b: **End-to-end HW validation on AX301 (2026-04-21 → 2026-04-22)** — three designs proven silicon-functional through the full open toolchain: (1) registered AND gate (KEY2&KEY3→DFF→LED0) at LAB(16,4), 10 FASM lines incl. multi-port IOB_ROUTE, 0 fabric diffs vs Quartus gold; (2) 5-bit carry counter at LAB(16,4) N=0..8, 18 FASM lines, 0 ROUTE directives (LE-internal carry feedback); (3) two-LAB cross-LAB AND→DFF→LED with BIT-only reconstruction from Quartus gold (byte-perfect vs gold, HW-verified). This is the first cross-LAB fabric route proven on silicon via the codec path.

- [x] Phase 6c: **chipdb 26-track upgrade (2026-04-22)** — LOCAL bus widened from 8 to 26 synthetic tracks, total pips grew to 3.6M; routing graph is now closer to real Cyclone IV's ~40-LI-wire-per-LAB topology. Runner drives P&R end-to-end on the upgraded chipdb. Small-design HW validation passed; dense-design (NEORV32) routing is still blocked — the model is denser but still simpler than the real C4/R4/R24/LI switch matrices.

- [x] Phase 7: **ζ BIT-workaround — open-toolchain escape hatch HW-validated end-to-end on NEORV32 (2026-04-23)** — `scripts/bit_workaround/quartus_gold_to_bit_fasm.py` + `fasm2rbf.py` round-trip takes any Quartus-produced RBF and rebuilds it byte-identically (emits one `BIT` directive per differing bit vs `nv_zero_global.rbf` baseline, CRC-patched). HW-validated at NEORV32 scale: 4712 LE / 2367 DFF / 19 M9K / 51 pins → 127 728 BIT directives (2634 hdr + 113 573 fab + 11 521 crc), ζ + fasm2rbf wall time ≈ 0.5 s. The rebuilt RBF boots the NEORV32 bootloader cleanly on AX301 at 19200-8N1 UART (banner + auto-boot countdown + SPI-flash probe + CMD prompt). Linux extended test (2026-04-24): kernel + DTB + initramfs transferred via xmodem, **Linux 6.6.83 ran ~150 s on RISC-V** (devtmpfs mounted, ttyNEO0 console attached, exec'd /sbin/init) before a kernel-level `kernel/cred.c:103` BUG_ON panic unrelated to the bitstream (RBF SHA256 matches Quartus gold). This is the first SoC-class validation of the escape hatch; users blocked by the chipdb routing model have a proven bounded workaround.

### Long-term direction: what this enables, and what it won't

A common question: with the codec working, can modern ML (RL routing, GNN
congestion prediction) outperform Quartus? The honest answer has three
layers.

**PPA is out of reach.** Quartus has a 30-year-old hardware-calibrated
timing model, a complete legality checker, and routing algorithms
(PathFinder + negotiated congestion) that have proven hard to beat on
industry benchmarks — whether academic RL routers can close the gap remains
an open research problem. Trying to out-route Quartus on its home turf is a
known dead end.

**What the codec does uniquely enable** is bit-level bidirectional
modification of a shipped bitstream — microseconds to mutate, seconds to
validate on silicon. Quartus is a one-way `verilog → bitstream` pipeline;
we are not. That gap enables:

1. **Bitstream-level mutation and equivalence framework.** Take a Quartus
   build, apply cell-level equivalent transforms (LUT-mask rewrites,
   redundant routing-bit removal), verify equivalence on hardware, keep
   mutations that reduce cell count or power. Expected PPA wins from
   cell-level peepholing are small (Quartus output is already near-locally
   optimal); the real value is as a research substrate for post-fit
   optimization and differential equivalence testing that Quartus cannot
   expose.
2. **Workflows Quartus does not expose.** Offline bitstream mutation and
   replay: modify specific frames in a known-good RBF and re-flash on next
   power cycle. This is *not* partial reconfiguration (Cyclone IV lacks
   ICAP), but it enables things Quartus's single-shot flow rules out —
   applying ECO patches without re-running fit, reproducible bit-identical
   builds (Quartus is seed-dependent; the codec is a pure function), and
   bitstream watermarking in don't-care LUT bits.
3. **Open toolchain (the actual prize).** A working Yosys + nextpnr-EP4CE6
   flow matters an order of magnitude more than any PPA play. It is the
   first time Linux/macOS users can target this chip without Intel's tools,
   the first time CI can build EP4CE6 bitstreams reproducibly, and the
   first time the **Cyclone IV E family** enters the open-source FPGA
   ecosystem (Project Mistral brought Cyclone V partway there before us).

**Where ML fits.** A modest supporting role: a decision-tree classifier to
replace hand-coded LI envelope rules once the corpus is big enough; a
small-tree pattern miner (not GNNs) for the paired-vs-alternating selection
rule so the result compiles directly into the codec; an anomaly detector
for codec-built RBFs that fail to flash. None of this is "ML beats
Quartus" — it is "ML helps write rules we do not want to hand-derive."

**Priority.** Finish Phase 5.3. The `.v → bitstream` open flow is already
most of the way there (chipdb + techmap + np2fasm working, counter
routing, 8-bit counter HW-verified). Once it runs end-to-end, the question
shifts from "can we beat Quartus on PPA" to "what can we do that Quartus
won't do at all" — and the codec is what answers that.

### Overall Progress Estimate

Percentages across different domains are not comparable (denominators
differ wildly — bits, cell types, route count, design size). This
table reports **coverage** (what's concretely counted) and **status**
(HW-verified / round-trip-clean / partial / not started) rather than a
single headline number.

| Domain | Coverage | Status |
|--------|----------|--------|
| CRAM address mapping | 22 cols × 18 rows × 16 LEs = 376/376 (CE6 whitelist) + X=32/33 and Y=15 post-jailbreak | HW-verified |
| RBF CRC | Spec fully derived (CRC-16/IBM, 0x8005, init 0xFE54, frames 25..1751); 1727/1727 verified | HW-verified |
| Logic configuration (LUT/FF/arithmetic) | LUT TT decoded at all LE positions; FF is silicon-default (no CRAM); arith mode = block-band blob | HW-verified |
| LE carry chain in open flow | chipdb `cout→cin` pips (8,126), CE6_CARRY techmap, `LUT_ARITH` FASM directive, per-width table (2..16 + 16+8 cross-LAB), v4 position-independent blob | HW-verified (8-bit counter, 2026-04-13) |
| FASM toolchain (Phase 4) | `fasm2rbf` + `rbf2fasm` + set-cover decomposer; 1725/1725 + 41/42 + 3/3 + CE6 686/686 round-trip | HW-verified (AND(K1,K2) on AX301) |
| Hardware loopback (codec → flash → silicon) | LutCodec + FASM path both running on AX301 | HW-verified |
| C4 routing switches | I=0 closed-form formula; I≠0 covered by 44-entry per-(X,I) lookup + sig-cache | Closed-form partial, sig-cache production |
| LOCAL_INTERCONNECT | Base-granular read/write; two encoding modes resolved; V2 safety guard | Round-trip clean |
| R4 routing switches | 25/37 I-indices mapped; remaining 12 blocked on corpus, not method | Partial |
| R24 long-distance wires | I=0 fixed-byte model, ~73% of wires | Partial |
| C16 long-distance wires | — | Not started |
| Bitstream codec | LUT TT + routing read/write; round-trip self-consistent; HW safety V2; CRC patcher integrated | HW-verified |
| Route synthesis (green islands) | CE6 standard 15 islands 686/686 bit-perfect; jailbreak/edge 9 islands 45/45 via snapshot fallback. Total harness 731/731 | Closed (2026-04-14) |
| FASM sig-cache (Phase 4.5) | **38,683 entries** (expanded 2026-04-19); 7-tuple (sn>0 supported); 0 route misses for NEORV32 v2 | Production |
| M9K init codec (Phase 5.2) | 2D linear formula; 33+5 anchor entries (incl. 18×512); M9K pipeline closed end-to-end (Yosys→prepack→np2fasm→fasm2rbf) | HW-validated (chip accepts open-toolchain M9K RBF, 2026-04-16) |
| M9K_MODE (Phase 5.2) | `_inferred_goldintersect` 38-cell site-invariant set; np2fasm emission ungated for w=9 | HW-validated (2026-04-17) |
| GCLK pipeline (Phase 5.4) | `GCLK_PIN` (12 pins on F17) + `LAB_CLK_SEL` + `LAB_CLK_SEL_LE` N∈{0,2,4,6,8}; XOR-composed on AUTO baseline | HW-verified (14 LABs × 5 N-slots; Stage 0 flash 2026-04-16) |
| IOB FASM (Phase 5.4) | `IOB_IN`/`IOB_OUT` 44/44; `IOB_IN_BIDIR`/`IOB_OUT_BIDIR` 16 sdram_dq pins; `IOB_ROUTE` 15/15; `IOB_OE` 16 pins | IOB_ROUTE HW-verified; BIDIR/OE codec-verified + bisected on silicon |
| DSPMULT (Phase 5.0) | 22-cell silicon-clean set (23 mined − 1 falsified via bisection at frame 1729) | HW-bisected; np2fasm not wired (0 DSPMULTs in NEORV32) |
| `nv_zero_global` retirement | `NV_BASELINE_PACK` directive + sub-directives reproduce the Quartus baseline byte-exact from PURE_ZERO | **HW silicon-equivalent confirmed** (Stage 0 flash 2026-04-16) |
| Formula-based LutCodec (σ⁻¹ 3-key) | `from_cram_model(x, y, n)` with 3-key σ⁻¹ table (`(foff, fb8, group)`), 1,904 entries, 5-level fallback | Fixed 2026-04-21 (96% verified); known Y=3 gap (80 positions) |
| Open-source toolchain — native path (Phase 5.3) | Yosys → nextpnr-generic (chipdb 26 LOCAL tracks, 3.6M pips) → np2fasm → fasm2rbf. AND gate + 5-bit carry counter + M9K smoke HW-validated at single/cross-LAB scale | HW-verified for small/medium; chipdb routing model still too sparse for NEORV32-class density |
| ζ BIT-workaround — escape hatch (Phase 7) | `scripts/bit_workaround/quartus_gold_to_bit_fasm.py` + fasm2rbf rebuilds any Quartus RBF byte-identically. 127k BIT directives for NEORV32; 0.5 s wall time | HW-validated end-to-end on NEORV32 bootloader (4712 LE / 19 M9K) on AX301, 2026-04-23 |

---

## References

- [Cyclone IV Device Handbook](https://www.intel.com/content/www/us/en/docs/programmable/683853/current/cyclone-iv-device-handbook.html)
- [Project IceStorm](http://www.clifford.at/icestorm/) — iCE40 reverse engineering, methodology reference
- [Project Mistral](https://github.com/Ravenslofty/mistral) — Cyclone V reverse engineering, same chip family
- [Quartus Prime Lite](https://www.intel.com/content/www/us/en/products/details/fpga/development-tools/quartus-prime/resource.html) — Free FPGA development tool

---

## Dead Ends Worth Remembering

Reverse engineering is mostly finding out which attractive hypothesis is
wrong. The ones that cost real time, recorded so the next person does
not repeat them:

- **M5 counter carry-chain detour.** Built a 24-bit counter through the
  open toolchain, could not get it to match Quartus's RBF. Spent a
  stretch of the project patching `LutCodec`, re-mining sig-cache
  entries, and chasing phase-ordering bugs in `fasm2rbf`. Root cause was none of
  those — Quartus places the design using LE-internal carry-chain
  wires that nextpnr-generic does not model, so Yosys emulates `+1`
  as a 4-LE ripple with 24 self-feedback routes. The codec fixes we
  landed along the way were real improvements, but the real blocker
  was an unmodelled primitive, not a codec bug. Lesson: when your open
  build of design D misbehaves, flash Quartus's RBF for the same D
  *first* and diff the two bitstreams before patching anything.
- **IOB cross-axis linear superposition.** Plausible hypothesis: a
  design driving (KEY_X, LED_Y) should factor as (KEY_X-only) ⊕
  (LED_Y-only) ⊕ baseline. Falsified — bank-pair lookup also failed.
  The residue is ~50-60 bytes of joint-placement state that neither
  model captures. Closing it requires a full 2D K×LED sweep (~480
  pair builds), currently in progress. Derived models are not coming
  back; do not retry them.
- **R4 dark passive mining.** Tried to recover R4 `BASE` constants by
  counting bit density in a full NV32 RBF. RBF is too dense —
  signal-to-noise is below the mining floor. Dead end.
- **T9 LI paired-vs-alternating as a function of the routing key.**
  Mined, structurally audited, falsified — the choice is not a
  function of `(src_type, src_I, dst_N, dst_port)`. Stop mining this
  axis; the missing variable is elsewhere.
- **DFF per-LE enable CRAM bit.** Chased for a long stretch before
  realising the flip-flop is intrinsic to every Cyclone IV LE and has no
  per-LE enable cell. The original `dff_cells_mined.json` was
  routing-infrastructure noise with zero overlap against any real
  design. The FASM `DFF` directive is now a parsed no-op.
- **Self-loop sig-cache entries via the two-LUT pair template.** The
  template cannot represent `src == dst`, and Quartus refits between
  baseline and feedback compiles, so the diff includes pin
  reassignments unrelated to the LI MUX. The 61 self-loop entries in
  `route_cells_full.json` are bloated noise (90-754 cells vs corpus
  median 135) and cannot be repaired by re-running the factory.
  Needs a single-LE differential strategy.

- **DSPMULT_GLOBAL_ON 23-cell set — falsified on silicon (2026-04-16).**
  The re-mined 23-cell "universal block enable" looked clean: CRAM-only,
  CRC-stripped, 21/21 N-invariant, zero routing drift. Stage 0 flash
  on AX301 → LED stuck constant-on. Bisected in 4 layers down to a
  single cell `(363236, 2)` at frame 1729. The 22-cell cleaned set
  PASSes silicon. The leaky cell sits inside the DSPMULT block-band
  region but its exact semantic is unknown. Lesson: even a "clean"
  mining campaign with stable intersections can harbour a single
  load-bearing cell that interacts with unrelated fabric paths. Always
  silicon-validate before ungating np2fasm emission.
- **IOB_OE PIN_R5 — failed on silicon, bisected (2026-04-17).**
  The 40-cell per-pin OE set for sdram_dq S_DB[0] passed all codec
  safety gates (0 fabric/hdr/block overlap with simple_led_pure). Flash
  → LED stuck constant-on. Bisected to 2 cells `(363236,2)+(363672,2)`;
  cleaned 38-cell set PASSes. Same `(363236,2)` cell as the DSPMULT
  leak — it appears to be a shared block-band hazard.
- **LUT_ARITH_MULTI_LAB WIDTH=17 — failed on silicon (2026-04-17).**
  The multi-LAB carry chain blob for widths 17..32 is byte-identical to
  Quartus output under `diff` (10/10 codec tests), but flashing → LED
  stuck constant-off. Different failure mode from IOB_OE (stuck-on).
  Position-independence for multi-LAB blobs was never proven (triangle
  test only covered single-LAB widths ≤16). Stays gated.
- **F16 output routing — mined but not integrable (2026-04-19).**
  Differential mining (f16_loc vs f15_loc at same X7Y21N14) cleanly
  isolated 40 F16-specific data cells (38 header + 2 block band).
  The LOC-constrained f16_loc.rbf HW-verified on AX301 (LED1 responds
  correctly to K3∧K4). However, adding even the 16 new cells to the
  pipeline test RBF triggers FPGA reset — the cumulative LUT layer
  damage from `from_cram_model()` pair mapping (192/233 LUTs wrong)
  means infrastructure is already in a bad state. The F16 cells
  themselves are correct; they cannot be applied until the LUT layer
  is fixed.

Individual post-mortems with cell-level detail live in memory files under
`~/.claude/projects/-home-test-EP4CE6/memory/` — search for
`m5_counter_root_cause_carry_chain`, `iob_cross_axis_not_decomposable`,
`r4_dark_passive_mining_dead`, `t9_li_mode_negative_result`,
`dff_perle_formula`, `sigcache_mining_template_pitfall`,
`dspmult_global_on_clean_remine`, `iob_oe_r5_bisection_silicon`, and
`f16_output_routing_mined`.

## Limitations and What This Is Not

So the README is honest about scope, not just progress:

- **C16 long-distance wires — untouched.** Zero coverage. All current
  routing work is C4 / R4 / R24 / LI. Designs that would route
  through C16 are not supported.
- **Non-E-series Cyclone IV parts — unvalidated.** Every silicon
  result in this repo is on an EP4CE6F17C8 (AX301 board). The codec
  formulas have not been tested on EP4CE15/22/30/40/55/75/115, nor on
  Cyclone IV GX. Die topology should be similar within the E family,
  but "similar" is not a checked claim.
- **Large designs — untested end-to-end.** The hardware-verified
  open-flow designs are small (8-bit counter, AND gate,
  identity-LED). NEORV32 has been synthesised and mapped, but no
  NEORV32 bitstream built by the open flow has been flashed and
  proven to boot on silicon. Larger designs may expose codec or
  chipdb gaps that small tests do not.
- **Temperature and voltage corners — not characterised.** All silicon
  validation is at room temperature, nominal Vccint. Behaviour under
  industrial temperature range or voltage droop is not measured.
- **M9K BRAM in the open flow — not hardware-validated yet.** Codec
  and `np2fasm` emission are green (5/5 tests each), chipdb has M9K
  bels and bridge pips, but the Yosys `memory_libmap` front-end
  currently rejects the mapping with "can't share write port 0:
  incompatible enable" — a lib/memory-shape mismatch that blocks the
  smoke build on `tmp/m9k_smoke/ram_9x512.v`. No RAM-using design has
  been flashed through the open flow.
- **PLLs — off-fabric, out of scope.** Cyclone IV PLLs live outside
  the CRAM region this project maps. Designs that require configured
  PLLs (as opposed to the dedicated clock pins the `GCLK_PIN`
  directive covers) are not supported.
- **LutCodec `from_cram_model()` pair mapping — broken.** The formula
  produces correct minterms at (10,10,0) but wrong bit-to-cell pair
  ordering at other positions. 192 out of 233 LUTs in the pipeline
  test produce incorrect truth tables. This is the primary blocker
  for flashing any non-trivial open-toolchain design. The pair
  ordering varies by (x,y) in ways the current formula doesn't capture;
  fixing it requires reverse-engineering the pair permutation.
- **chipdb LOCAL bus — undersized for dense designs.** The routing
  model provides 4 LOCAL tracks per LAB (~2080 wires total). Real
  Cyclone IV silicon has O(100k) routing resources (C4/R4/R24/LI
  crossbar). At 6500+ LEs (NEORV32 scale), nearly every LOCAL wire
  is overused, causing driver conflicts and FPGA protective reset.
  This is a fundamental routing model limitation, not a directive bug.
  Fix options: SIG-cache-aware placement, hierarchical routing model,
  or a dedicated nextpnr-cyclone4 architecture port.
- **Not a Quartus replacement.** The codec is not a timing-driven
  place-and-route tool. Its unique capabilities are bit-level
  bidirectional modification of a shipped bitstream and offline
  mutation/replay — see *"Long-term direction"* above. If you need
  PPA-competitive synthesis, use Quartus.

---

## License

Dual license, effective 2026-04-07 (replacing the previous MIT license):

- **Code** (`fuzz/`, `synth/`, `scripts/`, everything that executes) —
  `GPL-3.0-or-later`. Full text:
  [`LICENSES/GPL-3.0-or-later.txt`](LICENSES/GPL-3.0-or-later.txt).
- **Documentation and prose** (`README*.md`, `CLAUDE.md`, `FINDINGS.md`,
  `docs/`) — `CC BY-SA 4.0`. Full text:
  [`LICENSES/CC-BY-SA-4.0.txt`](LICENSES/CC-BY-SA-4.0.txt).

**What copyleft covers, and what it doesn't.** GPL attaches to the code
as software, and CC BY-SA attaches to the prose as a written work. Both
require downstream forks of these artifacts to stay under the same
terms. Neither license covers the *methodology* itself — reverse-engineering
techniques, CRAM formulas, bit offsets, and the CE10 jailbreak result
are facts, not expression, and copyright does not fence them off. We
chose copyleft anyway because it keeps the reference implementation and
the written record open, which is the part downstream users actually
rely on. If you want the methodology attached to a more durable claim,
cite the repo and the relevant `FINDINGS.md` entry — that is what a
defensive publication looks like.

Bitstream blobs (`*.rbf`, `*.sof`), SQLite corpora, and Quartus build
artifacts under `work/` and `results/rbf/` are hardware telemetry, not
creative works; no license is asserted over them, and redistribution
remains subject to Altera/Intel's original terms on their tools and
outputs.

This project is for educational and research purposes.
