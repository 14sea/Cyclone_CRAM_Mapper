"""EP4CE6F17C8 constants and fuzzing pipeline configuration."""

import os

# --- Paths ---
QUARTUS_BIN = os.path.expanduser("~/intelFPGA_lite/21.1/quartus/bin")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK_DIR = os.path.join(PROJECT_ROOT, "work")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")
RBF_DIR = os.path.join(RESULTS_DIR, "rbf")
TEMPLATE_DIR = os.path.join(PROJECT_ROOT, "templates")
DB_PATH = os.path.join(RESULTS_DIR, "ep4ce6_bitdb.sqlite")

# --- Device ---
FAMILY = "Cyclone IV E"
DEVICE = "EP4CE6F17C8"
RBF_SIZE = 368011  # bytes, fixed for all EP4CE6 designs
RBF_BITS = RBF_SIZE * 8  # 2,944,088
PREAMBLE_BYTES = 32  # 0xFF preamble
CONFIG_BYTES = 367920  # actual configuration data
POSTAMBLE_BYTES = 59  # 0xFF postamble

# --- Chip Geometry ---
# LAB X coordinates (22 values, from fitter report)
LAB_X = [3, 4, 6, 7, 8, 10, 11, 12, 13, 16, 17, 18, 19, 21, 22, 23, 24, 25, 26, 28, 29, 31]

# LAB Y coordinates (18 values)
LAB_Y = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 21]

# LE N indices within a LAB (16 values, even numbers)
LE_N = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30]

TOTAL_LABS = 392  # per handbook; 376 verified via fuzzing
TOTAL_LES = 6272  # 392 * 16
LES_PER_LAB = 16

# Invalid LAB positions (Quartus rejects placement at these coordinates)
INVALID_LABS = {(x, y) for x in [3, 4, 6, 7, 8] for y in [12, 13, 14, 16]}

# --- CRAM Address Model (verified 376/376 positions) ---
COLUMN_BASE = {
    3: 0x076E0, 4: 0x09396, 6: 0x0CD02, 7: 0x0E9B8, 8: 0x1066E,
    10: 0x13FDA, 11: 0x15C90, 12: 0x17946, 13: 0x195FC,
    16: 0x2BFC2, 17: 0x2DC78, 18: 0x2FC76, 19: 0x3192C,
    21: 0x34A64, 22: 0x3671A, 23: 0x383D0, 24: 0x3A086,
    25: 0x3BD3C, 26: 0x3D9F2,
    28: 0x4E702, 29: 0x503B8, 31: 0x53D24,
}
PAIR_SPACING = 210
DATA_OFFSET = 184   # Fixed position of data bytes within 210-byte period (from period_start)
SLOT_BASE = {0: 136, 1: 0, 2: 70}


def cram_n_delta(n):
    """Compute address delta from N=0 for a given LE index N (0,2,4,...,30)."""
    k = n // 2  # k = 0..15
    half = k // 8
    kh = k % 8
    return -(half * 38) - (kh // 2) * 8 - (kh % 2) * 2


def cram_ctrl_addr(x, y, pair, n=0):
    """Compute CRAM ctrl byte address for LUT TT pair at (X, Y, N)."""
    cram_row = y - 2
    slot = cram_row % 3
    group = cram_row // 3
    offset = SLOT_BASE[slot] + group * 3 + (1 if slot == 0 and group > 0 else 0)
    period_start = COLUMN_BASE[x] - 136
    return period_start + offset + pair * PAIR_SPACING + cram_n_delta(n)


def cram_data_addr(x, pair):
    """Compute CRAM data byte address for a LUT TT pair (Y/N independent)."""
    period_start = COLUMN_BASE[x] - 136
    return period_start + DATA_OFFSET + pair * PAIR_SPACING


def cram_ctrl_bit(y):
    """Compute which bit position identifies this Y row in ctrl bytes."""
    cram_row = y - 2
    slot = cram_row % 3
    group = cram_row // 3
    return 7 - group - (1 if slot > 0 else 0)

# --- Pin Assignments for Fuzzing ---
# Using LED and KEY pins from AX301 that won't conflict
# These are minimal I/O for a 4-input LUT + output
FUZZ_PINS = {
    "A": "PIN_E16",   # KEY2
    "B": "PIN_M16",   # KEY3
    "C": "PIN_M15",   # KEY4
    "D": "PIN_E15",   # RESET (used as input for fuzzing)
    "Q": "PIN_G15",   # LED[0]
    "CLK": "PIN_E1",  # 50 MHz clock
}

# Extra pins for routing designs (7-input, 1-output)
ROUTE_FUZZ_PINS = {
    "A": "PIN_E16",   # KEY2
    "B": "PIN_M16",   # KEY3
    "C": "PIN_M15",   # KEY4
    "D": "PIN_E15",   # RESET
    "E": "PIN_N13",   # SRAM addr
    "F": "PIN_L16",   # SRAM addr
    "G": "PIN_K16",   # SRAM addr (adjacent)
    "Q": "PIN_G15",   # LED[0]
    "CLK": "PIN_E1",  # 50 MHz clock
}

# --- LUT4 Truth Table ---
# 16 minterm expressions for isolating individual truth table bits
MINTERM_EXPRESSIONS = {
    0:  "~A & ~B & ~C & ~D",  # 0000
    1:  "~A & ~B & ~C &  D",  # 0001
    2:  "~A & ~B &  C & ~D",  # 0010
    3:  "~A & ~B &  C &  D",  # 0011
    4:  "~A &  B & ~C & ~D",  # 0100
    5:  "~A &  B & ~C &  D",  # 0101
    6:  "~A &  B &  C & ~D",  # 0110
    7:  "~A &  B &  C &  D",  # 0111
    8:  " A & ~B & ~C & ~D",  # 1000
    9:  " A & ~B & ~C &  D",  # 1001
    10: " A & ~B &  C & ~D",  # 1010
    11: " A & ~B &  C &  D",  # 1011
    12: " A &  B & ~C & ~D",  # 1100
    13: " A &  B & ~C &  D",  # 1101
    14: " A &  B &  C & ~D",  # 1110
    15: " A &  B &  C &  D",  # 1111
}

# Common logic functions for verification
LOGIC_FUNCTIONS = {
    "and":  "A & B",
    "or":   "A | B",
    "xor":  "A ^ B",
    "nand": "~(A & B)",
    "nor":  "~(A | B)",
    "xnor": "~(A ^ B)",
    "buf_a": "A",
    "not_a": "~A",
    "zero": "1'b0",
    "one":  "1'b1",
}

# --- Quartus Optimization Overrides ---
# These prevent Quartus from altering our carefully crafted designs
QSF_OPTIMIZATIONS_OFF = [
    ('AUTO_RAM_RECOGNITION', 'OFF'),
    ('AUTO_DSP_RECOGNITION', 'OFF'),
    ('AUTO_SHIFT_REGISTER_RECOGNITION', 'OFF'),
    ('ALLOW_REGISTER_RETIMING', 'OFF'),
    ('SYNTH_TIMING_DRIVEN_SYNTHESIS', 'OFF'),
    ('PHYSICAL_SYNTHESIS_COMBO_LOGIC', 'OFF'),
    ('PHYSICAL_SYNTHESIS_REGISTER_DUPLICATION', 'OFF'),
    ('PHYSICAL_SYNTHESIS_REGISTER_RETIMING', 'OFF'),
    ('FITTER_EFFORT', 'STANDARD FIT'),
    ('OPTIMIZE_HOLD_TIMING', 'OFF'),
    ('OPTIMIZE_MULTI_CORNER_TIMING', 'OFF'),
    ('ROUTER_TIMING_OPTIMIZATION_LEVEL', 'MINIMUM'),
]
