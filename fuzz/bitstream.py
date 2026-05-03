# SPDX-License-Identifier: GPL-3.0-or-later
"""EP4CE6 bitstream read/write codec for LUT truth tables and routing.

Given calibrated minterm patterns at a position (X, Y, N), this module can:
1. Read the current LUT truth table from an RBF file
2. Write a new LUT truth table into an RBF file
3. Verify the XOR-linear encoding

Routing codec (RouteCodec) reads/writes switch states from/to RBF using CRAM address models:
- C4 column wires (I=0 formula + 24 per-(X,I) lookups for I≠0)
- R4 row wires (25 of 37 mapped I-indices)
- R24 long row wires (I=0, fixed byte offset)
- LOCAL_INTERCONNECT LAB input muxes

Usage:
    from bitstream import LutCodec, RouteCodec

    # LUT codec (requires calibration)
    codec = LutCodec.from_db(db, x=10, y=10, n=0)
    tt = codec.read_tt(rbf_data, zero_data)

    # Routing codec (model-based, no calibration needed)
    rc = RouteCodec()
    switches = rc.read_switches(rbf_data, zero_data)
"""

import os.path as _os_path
from collections import defaultdict

from config import (COLUMN_BASE, LAB_X, LAB_Y, PAIR_SPACING, SLOT_BASE,
                    cram_ctrl_addr, cram_ctrl_bit, cram_n_delta)


# --- C4 address model constants ---

# LAB column CRAM cluster ends (at Y=10) — from pairdiff analysis
_LAB_CRAM_END = {
    3: 0x07ccf, 4: 0x09985, 6: 0x0d2f1, 7: 0x0efa7, 8: 0x10c5d,
    10: 0x145c9, 11: 0x1627f, 12: 0x17f35, 13: 0x19beb,
    16: 0x2c5b1, 17: 0x2e267, 18: 0x30265, 19: 0x31f1b,
    21: 0x35053, 22: 0x36d09, 23: 0x389bf, 24: 0x3a675,
    25: 0x3c32b, 26: 0x3dfe1, 28: 0x4ecf1, 29: 0x509a7, 31: 0x54313,
}
_C4_SLOT_BASE = {0: 2405, 1: 2475, 2: 2338}

# C4 I≠0: per-(X, I) fixed byte offsets — no universal formula.
# Key: (wire_x, i_index) -> absolute RBF byte offset.
# The byte is FIXED for all Y values; only bp changes with Y (same formula as I=0).
# Mapped via baseline-diff method (c4_mapper.py, 2026-04-06).
# DEPRECATED 2026-04-08: CRC audit shows 44/44 entries land on frame CRC bytes
# (pos 208/209). Writes are overwritten by patch_rbf_crc → dead code.
# See memory/ff_arst_ena_crc_false_positive.md. Kept for read-path structure.
_C4_FIXED_OFFSETS = {
    (9, 1): 0x13633,    # 5/5 Y hit
    (9, 10): 0x15216,   # 5/6 Y hit
    (9, 12): 0x15217,   # 5/6 Y hit
    (9, 20): 0x15073,   # 2/2 Y hit
    (10, 9): 0x15217,   # 2/2 Y hit
    (10, 12): 0x14c59,  # 6/6 Y hit
    (13, 3): 0x1a695,   # 3/5 Y hit
    (13, 7): 0x1a767,   # 2/2 Y hit
    (13, 8): 0x1a838,   # 2/3 Y hit
    (15, 1): 0x2cf89,   # 5/6 Y hit
    (16, 1): 0x2dbd6,   # 5/6 Y hit
    (16, 15): 0x2d1fe,  # 2/2 Y hit
    (21, 2): 0x35958,   # 2/2 Y hit (2026-04-07)
    (22, 3): 0x37957,   # 2/2 Y hit (shares offset with I=12)
    (22, 12): 0x37957,  # 5/6 Y hit (shares offset with I=3)
    (22, 23): 0x36a92,  # 3/3 Y hit
    (25, 1): 0x3d950,   # 4/6 Y hit
    (25, 3): 0x3cdd4,   # 3/3 Y hit (shares offset with I=12)
    (25, 12): 0x3cdd4,  # 5/6 Y hit (shares offset with I=3)
    (25, 14): 0x3cf79,  # 2/2 Y hit
    (28, 9): 0x4f6c8,   # 2/2 Y hit
    (28, 10): 0x50317,  # 5/5 Y hit
    (29, 10): 0x512ad,  # 2/3 Y hit
    (29, 23): 0x50dc1,  # 2/2 Y hit
    (30, 9): 0x52f62,   # 3/3 Y hit
    # --- c4_inz_sweep batch (2026-04-07): 19 new mappings ---
    (3, 1):   0x092f5,  # 3/3 Y hit
    (7, 12):  0x105cd,  # 5/6 Y hit
    (10, 1):  0x15217,  # 2/2 Y hit
    (10, 10): 0x14c59,  # 2/2 Y hit (same byte as (10,12) I=12)
    (11, 1):  0x177d3,  # 4/5 Y hit
    (11, 12): 0x16c56,  # 5/6 Y hit
    (12, 12): 0x18ab1,  # 5/6 Y hit
    (13, 1):  0x1a694,  # 3/3 Y hit
    (16, 10): 0x2cd12,  # 3/3 Y hit
    (16, 12): 0x2d12c,  # 4/6 Y hit
    (17, 12): 0x2ef87,  # 5/6 Y hit
    (21, 1):  0x364d5,  # 6/6 Y hit
    (21, 10): 0x36679,  # 3/3 Y hit
    (21, 12): 0x35afc,  # 6/6 Y hit
    (24, 1):  0x3bc9a,  # 4/5 Y hit
    (24, 10): 0x3bc9b,  # 2/2 Y hit
    (24, 12): 0x3bbc8,  # 5/6 Y hit
    (28, 1):  0x50316,  # 2/2 Y hit
    (29, 12): 0x51036,  # 5/5 Y hit
}

# --- R4 address model constants ---

# R4 switches: most I-indices have bits in PREV column.
# R4_BASE_PREV[I-index] = (pair1_base, pair2_base), measured from prev_lab_x col start
# Verified via paired ctrl byte matching across 3+ columns
_R4_BASE_PREV = {
    0:  (3423, 3842),   # delta=419, verified X12,X19,X31
    1:  (3431, 3850),   # delta=419, verified X4,X18,X23
    2:  (3431, 3851),   # delta=420, verified prev=X4,X6,X10,X24,X28 (misses near M9K)
    3:  (3474, 3895),   # delta=421, cross-Y 3 cols (2026-04-06)
    4:  (3423, 3842),   # delta=419, verified X9,X14,X29 (same BASE as I=0)
    7:  (3414, 3835),   # delta=421, verified prev=X22 (same BASE as I=10)
    10: (3414, 3835),   # delta=421, verified X13,X18,X25
    11: (3378, 3585),   # delta=207, cross-Y 2 cols (2026-04-06)
    12: (3597, 3806),   # delta=209, cross-Y 2 cols (2026-04-06)
    13: (3577, 3786),   # delta=209, cross-Y 3 cols (same BASE as I=15, 2026-04-06)
    14: (3191, 3191),   # pair2 TBD — only pair1 confirmed across 3 Y positions
    15: (3577, 3786),   # delta=209, verified prev=X12,X16,X24 (misses at X10,X19,X28)
    16: (3629, 3835),   # delta=206, cross-Y 2 cols (2026-04-06)
    17: (2802, 3223),   # delta=421, verified prev=X13,X17,X21,X25 (64% — misses near M9K)
    18: (4057, 4267),   # delta=210, verified X4,X7
    20: (2791, 3001),   # delta=210, verified prev=X6,X11 (40% — some wires use diff scheme)
    22: (2783, 2993),   # delta=210, verified prev=X7 (small sample)
    # I=6 REMOVED 2026-04-08: Option-1 fingerprint recheck showed the (3612,3822)
    # base was blindly propagated from I=8 during 2026-04-06 mining with zero
    # independent evidence. 15 green-zone sources don't route through any I=6
    # wire, so no fingerprint data exists to validate it. I=6 routes must now
    # fall back to signature short-circuit until a fresh I=6 corpus is mined.
    # See memory/r4_i6_i8_base_collision.md for the validation run.
    8:  (3612, 3822),   # EDGE_CASE 2026-04-09: fingerprint recheck said 83.3% but
                        #   r4_full_audit.py vs absolute route_cells.json gives 6.7%
                        #   (same rate as I=6, which is known non-LAB CRAM). Two
                        #   methods disagree >70pp. Hypothesis: I=8 crosses the
                        #   LAB ↔ non-LAB (M9K/DSP) boundary and the prev_lab col
                        #   formula breaks. Keep base for sig-cache fallback only;
                        #   do NOT trust for new routes. See r4_full_audit_2026_04_09.md.
    19: (2794, 3215),   # delta=421, cross-Y 1 col prev=X11 (2026-04-06)
    21: (2786, 3207),   # delta=421, cross-Y 2 cols prev=X13(wide),X22 (2026-04-06)
    25: (2762, 2972),   # delta=210, verified X4,X8
    27: (2754, 2964),   # delta=210, cross-Y 1 col prev=X26 wide (2026-04-06)
    23: (3588, 3588),   # pair2 TBD, mapped 2026-04-07 via r4_mapper2
    26: (7210, 6791),   # delta=419, mapped 2026-04-07 via r4_mapper2
}
_R4_SLOT_OFFSET = {0: 67, 1: -70, 2: 0}

# Standard column width
_R4_STD_COL_WIDTH = 7350

# Column widths and next LAB column for each LAB column
_COL_WIDTH = {}
_NEXT_LAB = {}
for _i in range(len(LAB_X)):
    _x = LAB_X[_i]
    if _x not in COLUMN_BASE:
        continue
    if _i + 1 < len(LAB_X) and LAB_X[_i + 1] in COLUMN_BASE:
        _COL_WIDTH[_x] = COLUMN_BASE[LAB_X[_i + 1]] - COLUMN_BASE[_x]
        _NEXT_LAB[_x] = LAB_X[_i + 1]
    else:
        _COL_WIDTH[_x] = 7350
        _NEXT_LAB[_x] = _x + 2  # approximate

# Unmapped I-indices — need more routing data or non-standard column handling
# I=6,21,26: tentative (1 col only), I=8,9,23,28: insufficient data
# I=19,27: likely stored in non-LAB CRAM (M9K/DSP blocks)

# --- R24 address model constants ---

# R24 switches: in PREV LAB column, FIXED byte offset (no slot/group byte adjustment)
# Only bp changes with Y: bp = (6-group) if slot==2 else (7-group)
# Each entry is a list of fixed offsets from col_start (= COLUMN_BASE[prev_x] - 136)
# DEPRECATED 2026-04-08: 56/56 CRC bytes. Dead code. See ff_arst_ena_crc_false_positive.md.
_R24_FIXED_OFFSETS = {
    0: [3124, 2705],  # pair-diff 66%/61%, 5-6 wx columns (2026-04-06)
}

# --- FF ctrl-signal mode bit constants (mined 2026-04-08) ------------------
# Async reset (arst) and clock enable (ena) mode bits broadcast across every
# LAB column on the FF control-signal R24 row. See memory:
# ff_ctrl_r24_broadcast.md. Each (rel, bp) is applied per-column at
# `COLUMN_BASE[x] - 136 + rel`, for every LAB column in the ctrl net span.
#
# Validation: the arst table was extracted from ff2 corpus (B->C diff) and
# cross-validated on dff_async_reset (69 hits across 8 independent columns).
# The ena table overlaps R24 I=0 at rel 3124/3125 (same bytes as the I=0
# long-row broadcast), confirming ctrl signals ride R24 infrastructure.
# DEPRECATED 2026-04-08: 448/476 CRC bytes (94%), only rel=3291 is real data.
# Needs re-mining against CRC-normalized baselines. See ff_arst_ena_crc_false_positive.md.
_FF_ARST_CELLS = [
    (2914, 0), (2914, 2), (2914, 3),
    (2915, 2), (2915, 3), (2915, 4), (2915, 6),
    (3291, 4),
    (3334, 0), (3334, 1), (3334, 2), (3334, 3), (3334, 5),
    (3335, 2), (3335, 3), (3335, 4), (3335, 6),
]
# DEPRECATED 2026-04-08: 168/168 CRC bytes (100%). Dead code. Needs re-mining.
_FF_ENA_CELLS = [
    (2914, 7), (2915, 1),
    (3124, 3), (3124, 7), (3125, 1), (3125, 7),  # matches _R24_FIXED_OFFSETS[0]
]


# --- LOCAL_INTERCONNECT address model constants ---

# Pair activation patterns by I-index
_LI_ALL9 = {2, 15, 16, 18, 22, 33, 34, 35, 36, 37}
_LI_SKIP37 = {0, 30, 31}
_LI_EVEN = {24, 26, 28, 29, 32}
_LI_FIRST2 = {4, 17, 27}
_LI_SLOT_OFFSET = {0: 67, 1: -70, 2: 0}


# === EP4CE6 RBF CRC-16 (reverse-engineered 2026-04-07) =====================
# Reflected CRC-16-IBM (poly 0x8005 → right-shift 0xA001), init 0xFE54.
# Each 210-byte frame: 208 data bytes + 2 CRC bytes (LE: low at +208, high +209).
# Frames 0..24 are bitstream header (no CRC). Frames 25..1751 are CRAM.
# Without CRC patching the FPGA rejects loaded RBFs and falls back to EPCS.

CRC_FRAME_SIZE = 210
CRC_DATA_SIZE = 208
CRC_FIRST_CRAM_FRAME = 25
CRC_LAST_FRAME = 1751
CRC_PREAMBLE = 32
CRC_INIT = 0xFE54
CRC_POLY_REFLECTED = 0xA001  # bitrev(0x8005)


def crc16_rbf_frame(data: bytes) -> int:
    """CRC of one 208-byte RBF frame. Returns 16-bit int (low byte stored first)."""
    crc = CRC_INIT
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ CRC_POLY_REFLECTED if (crc & 1) else (crc >> 1)
    return crc


def patch_rbf_crc(rbf: bytes) -> bytes:
    """Recompute CRC for every CRAM frame (25..1751). No-op on Quartus output."""
    buf = bytearray(rbf)
    for n in range(CRC_FIRST_CRAM_FRAME, CRC_LAST_FRAME + 1):
        s = CRC_PREAMBLE + n * CRC_FRAME_SIZE
        c = crc16_rbf_frame(bytes(buf[s:s + CRC_DATA_SIZE]))
        buf[s + CRC_DATA_SIZE] = c & 0xFF
        buf[s + CRC_DATA_SIZE + 1] = (c >> 8) & 0xFF
    return bytes(buf)


class FlashGateError(RuntimeError):
    """Raised by validate_no_header_miss when header MISS cells exist."""


def validate_no_header_miss(rbf: bytes, gold_rbf: bytes,
                            *, header_end: int = 5282) -> None:
    """Raise FlashGateError if `rbf` is MISSING any cell that `gold_rbf`
    has set in the header band (off < header_end, default 5282).

    Header-band cells encode config-controller words (IO bank standards,
    weak pull-up control, CONF_DONE handshake hints).  Empirical
    discovery 2026-05-03: silicon flash test #1 of cross_lab_open_x33
    RESET because 29 header MISS cells were treated as "silent" under
    a MISS-only direction policy.  They were NOT silent — FPGA refused
    to enter user mode.

    Encodes the discipline: even at TOTAL <100 MISS-only, header MISS
    must be 0 before flash.

    Raises FlashGateError if any header bit is 1 in `gold_rbf` but 0 in
    `rbf` (the MISSING-from-rbf direction).  Excess bits in rbf vs gold
    are not flagged here (that's the OVER direction, which is silicon-
    safe to set extra in header band — usually).
    """
    miss_offsets = []
    for off in range(header_end):
        diff = (~rbf[off]) & gold_rbf[off]
        if diff:
            for bp in range(8):
                if diff & (1 << bp):
                    miss_offsets.append((off, bp))
    if miss_offsets:
        raise FlashGateError(
            f"Header-band MISS gate FAIL: {len(miss_offsets)} cells set "
            f"in gold but missing in rbf (header band off<{header_end}). "
            f"Silicon will RESET on flash (config-controller bits). "
            f"First 5: {miss_offsets[:5]}"
        )


def mask_rbf_crc_bytes(rbf: bytes, ref: bytes) -> bytes:
    """Return a copy of `rbf` with every CRAM-frame CRC byte overwritten by
    `ref`'s value at the same position.

    Used to neutralize CRC noise before feeding routing diffs to the codec
    readers — the CRC byte offsets (+208/+209 of every 210-byte frame) collide
    with positions the C4/R4/R24/LI readers scan, so a CRC update would be
    misread as a routing-cell change.
    """
    buf = bytearray(rbf)
    for n in range(CRC_FIRST_CRAM_FRAME, CRC_LAST_FRAME + 1):
        s = CRC_PREAMBLE + n * CRC_FRAME_SIZE
        buf[s + CRC_DATA_SIZE] = ref[s + CRC_DATA_SIZE]
        buf[s + CRC_DATA_SIZE + 1] = ref[s + CRC_DATA_SIZE + 1]
    return bytes(buf)


def _li_active_pairs(i_idx):
    """Return list of active 210-byte pair indices for a LOCAL_INTERCONNECT I-index."""
    if i_idx in _LI_ALL9:
        return list(range(9))
    elif i_idx in _LI_SKIP37:
        return [p for p in range(9) if p not in (3, 7)]
    elif i_idx in _LI_EVEN:
        return [0, 2, 4, 6, 8]
    elif i_idx in _LI_FIRST2:
        return [0, 1, 4, 5, 8]
    else:
        # Unknown pattern — use universal pairs only
        return [0, 4]


def _cram_group_bit(y):
    """Compute (group, slot, bit_position) for a Y coordinate.

    Used by C4 model. For R4, use _r4_addr() instead.
    """
    cram_row = y - 2
    group = cram_row // 3
    slot = cram_row % 3
    bp = (6 - group) if slot == 2 else (7 - group)
    return group, slot, bp


def _r4_addr(base_val, y):
    """Compute (byte_offset_within_col, bit_position) for an R4 switch.

    R4 has slot-dependent formulas:
    - slot 0: byte = base + 66 + 3*group + (1 if group>0 else 0), bp = 7 - group
    - slot 1: byte = base + (-70) + 3*group,                      bp = 6 - group
    - slot 2: byte = base + 0 + 3*group,                          bp = 6 - group
    """
    cram_row = y - 2
    group = cram_row // 3
    slot = cram_row % 3
    if slot == 0:
        byte_off = base_val + 66 + 3 * group + (1 if group > 0 else 0)
        bp = 7 - group
    elif slot == 1:
        byte_off = base_val + (-70) + 3 * group
        bp = 6 - group
    else:
        byte_off = base_val + 3 * group
        bp = 6 - group
    return byte_off, bp


class RouteCodec:
    """Read routing switch states from RBF using CRAM address models.

    Supports four wire types:
    - C4: column wires — I=0 via formula, I≠0 via per-(X,I) lookup
    - R4: row wires (25 of 37 mapped I-indices), CRAM bits in previous LAB column
    - R24: long row wires (I=0), CRAM bits in prev column, fixed byte offset
    - LOCAL_INTERCONNECT: LAB input muxes, CRAM bits in self column

    Each read method returns a list of (wire_name, byte_offset, bit_pos) tuples
    for switches that differ between the design RBF and the zero baseline.
    """

    # Y positions where C4 wires can exist (valid LAB Y + boundary positions)
    C4_Y_RANGE = LAB_Y

    def read_c4(self, rbf_data, zero_data):
        """Read active C4 switches (I=0 via formula, I≠0 via lookup).

        Returns list of (wire_name, byte_offset, bit_pos) for active switches.
        """
        active = []

        # C4 I=0: universal formula
        for x in LAB_X:
            if x not in _LAB_CRAM_END:
                continue
            for y in self.C4_Y_RANGE:
                group, slot, bp = _cram_group_bit(y)
                offset = _LAB_CRAM_END[x] + _C4_SLOT_BASE[slot] + 3 * group
                if offset >= len(rbf_data) or offset >= len(zero_data):
                    continue
                if (rbf_data[offset] >> bp) & 1 != (zero_data[offset] >> bp) & 1:
                    active.append((f"C4_X{x}_Y{y}_N0_I0", offset, bp))

        # C4 I≠0: per-(X, I) fixed byte offsets
        for (wx, ii), byte_off in _C4_FIXED_OFFSETS.items():
            if byte_off >= len(rbf_data) or byte_off >= len(zero_data):
                continue
            for y in self.C4_Y_RANGE:
                _, _, bp = _cram_group_bit(y)
                if (rbf_data[byte_off] >> bp) & 1 != (zero_data[byte_off] >> bp) & 1:
                    active.append((f"C4_X{wx}_Y{y}_N0_I{ii}", byte_off, bp))

        return active

    # R4 wire X range: includes non-LAB positions (gaps between LAB columns)
    R4_X_RANGE = list(range(3, 34))

    @staticmethod
    def _prev_lab_x(wx):
        """Find the LAB column just before wire X coordinate."""
        for j in range(len(LAB_X) - 1, -1, -1):
            if LAB_X[j] < wx:
                return LAB_X[j]
        return None

    def read_r4(self, rbf_data, zero_data):
        """Read active R4 switches for PREV-column I-indices.

        Scans all wire X positions (3-33), not just LAB columns.
        For non-standard columns (>7350 bytes), checks both sub-regions:
        - First sub-region: standard BASE (for wires near prev_lab_x)
        - Second sub-region: BASE + 7350 (for wires near next_lab_x)
        Returns list of (wire_name, byte_offset, bit_pos) for active switches.
        """
        active = []

        for i_idx, (base1_std, base2_std) in _R4_BASE_PREV.items():
            for wx in self.R4_X_RANGE:
                prev_x = self._prev_lab_x(wx)
                if prev_x is None or prev_x not in COLUMN_BASE:
                    continue
                col_start = COLUMN_BASE[prev_x] - 136
                cw = _COL_WIDTH.get(prev_x, _R4_STD_COL_WIDTH)

                if cw < 2 * _R4_STD_COL_WIDTH:
                    # Standard or slightly wider column: use standard BASE
                    base_sets = [(base1_std, base2_std)]
                else:
                    # Wide column (2× or more): use sub-region model
                    next_x = _NEXT_LAB.get(prev_x, prev_x + 2)
                    mid = (prev_x + next_x) / 2
                    if wx > mid:
                        # Right side: second sub-region (+7350)
                        base_sets = [(base1_std + 7350, base2_std + 7350)]
                    else:
                        # Left side: first sub-region (standard BASE)
                        base_sets = [(base1_std, base2_std)]

                for y in LAB_Y:
                    for bases in base_sets:
                        for base in bases:
                            byte_off, bp = _r4_addr(base, y)
                            offset = col_start + byte_off
                            if offset < 0 or offset >= len(rbf_data):
                                continue
                            if (rbf_data[offset] >> bp) & 1 != (zero_data[offset] >> bp) & 1:
                                active.append((f"R4_X{wx}_Y{y}_N0_I{i_idx}", offset, bp))
        return active

    # R24 wire X range (same as R4 plus wider)
    R24_X_RANGE = list(range(3, 34))

    # ------------------------------------------------------------------
    # R24 (Y_block, prev_x) → offset table  (2026-04-07)
    # Built from r24_cardinality_mine.py over 118 routed RBFs
    # (5217+ wire-groups). Schema:
    #   1. exact (block, prev_x) lookup
    #   2. fall back to column-stable verdict (blocks aggregated)
    #   3. fall back to global default 'pri' (most common single-cell choice)
    # See results/r24_offset_table.json for confidence + sample counts.
    #
    # Physical pattern: blocks A (Y2-3), F (Y16-18), G (Y19-21) — the chip
    # top edge, mid M9K boundary (Y15 missing), and bottom edge — flip
    # several columns from PRI to SEC. Interior blocks B/C/D/E are
    # PRI-dominant. The two columns that hold SEC across all blocks are
    # prev_x ∈ {8, 29} (97-98% confidence, 800+ samples each).
    # ------------------------------------------------------------------
    R24_Y_BLOCK = {
        2: "A", 3: "A",
        4: "B", 5: "B", 6: "B",
        7: "C", 8: "C", 9: "C",
        10: "D", 11: "D", 12: "D",
        13: "E", 14: "E",
        16: "F", 17: "F", 18: "F",
        19: "G", 21: "G",
    }

    # offsets: 'pri' = 3124, 'sec' = 2705 (relative to prev col_start)
    R24_OFFSET_TABLE = {
        ('A',  3): 'pri', ('A',  4): 'sec', ('A',  6): 'pri', ('A',  7): 'pri',
        ('A',  8): 'sec', ('A', 10): 'pri', ('A', 11): 'sec', ('A', 12): 'pri',
        ('A', 13): 'sec', ('A', 17): 'pri', ('A', 18): 'pri', ('A', 19): 'pri',
        ('A', 21): 'pri', ('A', 22): 'pri', ('A', 23): 'pri', ('A', 25): 'sec',
        ('A', 26): 'sec', ('A', 28): 'pri', ('A', 29): 'sec', ('A', 31): 'pri',
        ('B',  3): 'pri', ('B',  6): 'pri', ('B',  7): 'pri', ('B',  8): 'sec',
        ('B', 10): 'pri', ('B', 11): 'pri', ('B', 12): 'sec', ('B', 13): 'pri',
        ('B', 17): 'pri', ('B', 18): 'pri', ('B', 19): 'pri', ('B', 21): 'pri',
        ('B', 23): 'pri', ('B', 24): 'pri', ('B', 25): 'sec', ('B', 28): 'pri',
        ('B', 29): 'sec', ('B', 31): 'pri',
        ('C',  3): 'pri', ('C',  4): 'pri', ('C',  6): 'pri', ('C',  7): 'sec',
        ('C', 10): 'pri', ('C', 11): 'sec', ('C', 12): 'pri', ('C', 13): 'pri',
        ('C', 16): 'pri', ('C', 17): 'pri', ('C', 18): 'sec', ('C', 19): 'pri',
        ('C', 21): 'pri', ('C', 22): 'sec', ('C', 23): 'pri', ('C', 24): 'pri',
        ('C', 26): 'sec', ('C', 28): 'pri', ('C', 29): 'sec',
        ('D',  3): 'pri', ('D',  4): 'pri', ('D',  6): 'pri', ('D',  7): 'pri',
        ('D', 10): 'pri', ('D', 11): 'pri', ('D', 12): 'pri', ('D', 13): 'pri',
        ('D', 17): 'pri', ('D', 18): 'pri', ('D', 19): 'pri', ('D', 22): 'sec',
        ('D', 23): 'pri', ('D', 25): 'sec', ('D', 26): 'pri', ('D', 28): 'pri',
        ('D', 29): 'sec', ('D', 31): 'pri',
        ('E',  3): 'pri', ('E',  4): 'pri', ('E',  7): 'pri', ('E', 10): 'pri',
        ('E', 11): 'pri', ('E', 16): 'pri', ('E', 18): 'pri', ('E', 19): 'sec',
        ('E', 21): 'pri', ('E', 22): 'sec', ('E', 24): 'pri', ('E', 25): 'sec',
        ('E', 26): 'sec', ('E', 28): 'pri', ('E', 29): 'sec', ('E', 31): 'pri',
        ('F',  4): 'pri', ('F',  6): 'pri', ('F',  7): 'pri', ('F', 10): 'pri',
        ('F', 11): 'pri', ('F', 12): 'pri', ('F', 13): 'sec', ('F', 16): 'pri',
        ('F', 17): 'sec', ('F', 18): 'pri', ('F', 19): 'sec', ('F', 22): 'pri',
        ('F', 23): 'sec', ('F', 24): 'pri', ('F', 25): 'pri', ('F', 26): 'sec',
        ('F', 28): 'pri', ('F', 29): 'sec', ('F', 31): 'pri',
        ('G',  3): 'pri', ('G',  4): 'sec', ('G',  6): 'pri', ('G',  7): 'pri',
        ('G',  8): 'sec', ('G', 10): 'pri', ('G', 11): 'sec', ('G', 12): 'pri',
        ('G', 13): 'pri', ('G', 16): 'pri', ('G', 17): 'sec', ('G', 18): 'pri',
        ('G', 19): 'sec', ('G', 21): 'sec', ('G', 22): 'sec', ('G', 23): 'pri',
        ('G', 26): 'pri', ('G', 28): 'pri', ('G', 29): 'sec',
    }
    R24_OFFSET_STABLE = {
        3: 'pri', 4: 'pri', 6: 'pri', 7: 'pri', 8: 'sec', 10: 'pri',
        11: 'pri', 12: 'pri', 13: 'pri', 16: 'pri', 17: 'pri', 18: 'pri',
        19: 'pri', 21: 'pri', 22: 'sec', 23: 'pri', 24: 'pri', 28: 'pri',
        29: 'sec', 31: 'pri',
    }

    def get_r24_offset(self, wx, y, i_idx=0):
        """Return absolute (byte_offset, bp) for an R24 I=0 wire at (wx, y).

        Uses the 3-tier fallback chain:
          1. exact (Y_block, prev_x) lookup
          2. column-stable verdict
          3. global default 'pri'

        Returns (offset, bp) suitable for write_r24's `cells=` whitelist.
        """
        if i_idx != 0:
            raise NotImplementedError("get_r24_offset only supports I=0 today")
        prev_x = self._prev_lab_x(wx)
        if prev_x is None or prev_x not in COLUMN_BASE:
            raise ValueError(f"no valid prev LAB column for wx={wx}")
        col_start = COLUMN_BASE[prev_x] - 136
        block = self.R24_Y_BLOCK.get(y)
        if block is None:
            raise ValueError(f"Y={y} not a valid LAB Y")

        choice = (self.R24_OFFSET_TABLE.get((block, prev_x))
                  or self.R24_OFFSET_STABLE.get(prev_x)
                  or 'pri')
        rel = 3124 if choice == 'pri' else 2705
        _, _, bp = _cram_group_bit(y)
        return col_start + rel, bp

    def read_r24(self, rbf_data, zero_data):
        """Read active R24 switches.

        R24 uses FIXED byte offsets in prev column (no slot/group byte adjustment).
        Only bp changes with Y: bp = (6-group) if slot==2 else (7-group).

        Returns list of (wire_name, byte_offset, bit_pos) for active switches.
        """
        active = []
        seen = set()  # dedupe: pri+sec offsets both reading active = same wire
        for i_idx, offsets in _R24_FIXED_OFFSETS.items():
            for wx in self.R24_X_RANGE:
                prev_x = self._prev_lab_x(wx)
                if prev_x is None or prev_x not in COLUMN_BASE:
                    continue
                col_start = COLUMN_BASE[prev_x] - 136

                for y in LAB_Y:
                    group, slot, bp = _cram_group_bit(y)
                    for fixed_off in offsets:
                        offset = col_start + fixed_off
                        if offset < 0 or offset >= len(rbf_data):
                            continue
                        if (rbf_data[offset] >> bp) & 1 != (zero_data[offset] >> bp) & 1:
                            key = (wx, y, i_idx)
                            if key in seen:
                                continue
                            seen.add(key)
                            active.append((f"R24_X{wx}_Y{y}_N0_I{i_idx}", offset, bp))
        return active

    def write_r24(self, rbf_data, zero_data, wx, y, i_idx=0, value=True,
                  cells=None):
        """Set/clear an R24 switch.

        By default ('shotgun' mode) sets ALL fixed-offset bits for the given
        I-index — this matches read_r24's full envelope but over-activates
        compared to Quartus, which usually flips only ONE of the two
        primary/secondary offsets per wire.

        For bit-perfect replay (e.g. transplanting Quartus routing), pass
        `cells=[(off, bp), ...]` to constrain the write to a specific subset
        of the candidate (offset, bp) pairs. Only candidates that appear in
        `cells` are actually flipped; the rest are left untouched. This lets
        callers feed in the exact set returned by read_r24.

        Args:
            rbf_data: bytes of the RBF to modify
            zero_data: bytes of the zero-mask baseline RBF
            wx: wire X coordinate (3-33)
            y: LAB Y coordinate
            i_idx: I-index (default 0, must be in _R24_FIXED_OFFSETS)
            value: True to activate, False to deactivate
            cells: optional iterable of (byte_offset, bit_pos) — sniper mode

        Returns:
            Modified RBF as bytes
        """
        if i_idx not in _R24_FIXED_OFFSETS:
            raise ValueError(f"R24 I-index {i_idx} not mapped")
        if y not in LAB_Y:
            raise ValueError(f"Y={y} not a valid LAB Y coordinate")

        prev_x = self._prev_lab_x(wx)
        if prev_x is None or prev_x not in COLUMN_BASE:
            raise ValueError(f"No valid prev LAB column for wx={wx}")

        col_start = COLUMN_BASE[prev_x] - 136
        group, slot, bp = _cram_group_bit(y)
        whitelist = set(cells) if cells is not None else None

        result = bytearray(rbf_data)
        for fixed_off in _R24_FIXED_OFFSETS[i_idx]:
            offset = col_start + fixed_off
            if whitelist is not None and (offset, bp) not in whitelist:
                continue
            self._set_bit(result, zero_data, offset, bp, value)
        return bytes(result)

    def read_local_interconnect(self, rbf_data, zero_data):
        """Read active LOCAL_INTERCONNECT switches at FULL (pair, base) granularity.

        Each active CRAM cell is reported as a separate entry — both base=70
        and base=71 are surfaced when both are flipped (no `break`). This is
        critical: empirically, two distinct LI encoding modes coexist in the
        same byte range:

          * "paired" mode: both base 70 and base 71 of the same pair are
            flipped together → 5 pairs × 2 bytes = 10 bit flips
          * "alternating" mode: only one of {70, 71} is flipped per pair,
            alternating across pair indices → 9 pairs × 1 byte = 9 bit flips

        Wire name format: LI_X{x}_Y{y}_P{pair}B{0|1}
          where B0 = base offset 70, B1 = base offset 71

        Returns list of (wire_name, byte_offset, bit_pos, candidates).
        """
        active = []
        # All known I-indices (kept only for the disambiguation `candidates` field)
        all_i = sorted(_LI_ALL9 | _LI_SKIP37 | _LI_EVEN | _LI_FIRST2)

        for lx in LAB_X:
            if lx not in COLUMN_BASE:
                continue
            col_start = COLUMN_BASE[lx] - 136

            for ly in LAB_Y:
                group, slot, bp = _cram_group_bit(ly)
                slot_off = _LI_SLOT_OFFSET[slot]

                for pair in range(9):
                    for base_idx, base in enumerate((70, 71)):
                        offset = col_start + base + pair * PAIR_SPACING + slot_off + 3 * group
                        if offset < 0 or offset >= len(rbf_data):
                            continue
                        if (rbf_data[offset] >> bp) & 1 != (zero_data[offset] >> bp) & 1:
                            candidates = [i for i in all_i if pair in _li_active_pairs(i)]
                            active.append(
                                (f"LI_X{lx}_Y{ly}_P{pair}B{base_idx}", offset, bp, candidates)
                            )
        return active

    @staticmethod
    def _parse_li_name(name):
        """Parse LI_X{x}_Y{y}_P{pair}B{base_idx} → (lx, ly, pair, base_idx)."""
        parts = name.split('_')
        lx = int(parts[1][1:])
        ly = int(parts[2][1:])
        pb = parts[3]  # P{pair}B{base_idx}
        bsplit = pb.index('B')
        pair = int(pb[1:bsplit])
        base_idx = int(pb[bsplit + 1:])
        return lx, ly, pair, base_idx

    # --- Write methods ---

    def _set_bit(self, result, zero_data, offset, bp, value):
        """Set or clear a single CRAM bit relative to zero baseline.

        value=True: make bit differ from zero_data (active)
        value=False: make bit match zero_data (inactive)
        """
        if offset < 0 or offset >= len(result):
            raise ValueError(f"offset {offset:#x} out of range (RBF size {len(result)})")
        zero_bit = (zero_data[offset] >> bp) & 1
        if value:
            # Active: flip relative to zero
            if zero_bit:
                result[offset] &= ~(1 << bp)
            else:
                result[offset] |= (1 << bp)
        else:
            # Inactive: match zero
            if zero_bit:
                result[offset] |= (1 << bp)
            else:
                result[offset] &= ~(1 << bp)

    def write_c4(self, rbf_data, zero_data, x, y, value=True):
        """Set/clear a C4 I=0 switch.

        Args:
            rbf_data: bytes of the RBF to modify
            zero_data: bytes of the zero-mask baseline RBF
            x: LAB X coordinate
            y: Y coordinate (1-21)
            value: True to activate, False to deactivate

        Returns:
            Modified RBF as bytes
        """
        if x not in _LAB_CRAM_END:
            raise ValueError(f"X={x} not in LAB_CRAM_END (valid: {sorted(_LAB_CRAM_END.keys())})")
        if y not in self.C4_Y_RANGE:
            raise ValueError(f"Y={y} out of C4 range (valid: 1-21)")

        group, slot, bp = _cram_group_bit(y)
        offset = _LAB_CRAM_END[x] + _C4_SLOT_BASE[slot] + 3 * group

        result = bytearray(rbf_data)
        self._set_bit(result, zero_data, offset, bp, value)
        return bytes(result)

    def write_c4_inz(self, rbf_data, zero_data, x, i_idx, y, value=True):
        """Set/clear a C4 I≠0 switch via per-(X,I) lookup table.

        The byte offset is fixed for all Y values; only bp varies with Y
        (same bp formula as I=0).
        """
        if i_idx == 0:
            return self.write_c4(rbf_data, zero_data, x, y, value)
        key = (x, i_idx)
        if key not in _C4_FIXED_OFFSETS:
            raise ValueError(
                f"C4 (X={x}, I={i_idx}) not in fixed-offset lookup "
                f"(mapped: {sorted(_C4_FIXED_OFFSETS.keys())})"
            )
        if y not in self.C4_Y_RANGE:
            raise ValueError(f"Y={y} out of C4 range")
        offset = _C4_FIXED_OFFSETS[key]
        _, _, bp = _cram_group_bit(y)
        result = bytearray(rbf_data)
        self._set_bit(result, zero_data, offset, bp, value)
        return bytes(result)

    def write_r4(self, rbf_data, zero_data, wx, y, i_idx, value=True):
        """Set/clear an R4 switch for a mapped I-index.

        Sets BOTH pair1 and pair2 bits for the given I-index.

        Args:
            rbf_data: bytes of the RBF to modify
            zero_data: bytes of the zero-mask baseline RBF
            wx: wire X coordinate (3-33)
            y: LAB Y coordinate
            i_idx: I-index (must be in _R4_BASE_PREV)
            value: True to activate, False to deactivate

        Returns:
            Modified RBF as bytes
        """
        if i_idx not in _R4_BASE_PREV:
            raise ValueError(
                f"I-index {i_idx} not mapped (valid: {sorted(_R4_BASE_PREV.keys())})"
            )
        if y not in LAB_Y:
            raise ValueError(f"Y={y} not a valid LAB Y coordinate")

        prev_x = self._prev_lab_x(wx)
        if prev_x is None or prev_x not in COLUMN_BASE:
            raise ValueError(f"No valid prev LAB column for wx={wx}")

        col_start = COLUMN_BASE[prev_x] - 136
        cw = _COL_WIDTH.get(prev_x, _R4_STD_COL_WIDTH)
        base1_std, base2_std = _R4_BASE_PREV[i_idx]

        if cw < 2 * _R4_STD_COL_WIDTH:
            bases = (base1_std, base2_std)
        else:
            # Wide column: sub-region model
            next_x = _NEXT_LAB.get(prev_x, prev_x + 2)
            mid = (prev_x + next_x) / 2
            if wx > mid:
                bases = (base1_std + 7350, base2_std + 7350)
            else:
                bases = (base1_std, base2_std)

        result = bytearray(rbf_data)
        for base in bases:
            byte_off, bp = _r4_addr(base, y)
            offset = col_start + byte_off
            self._set_bit(result, zero_data, offset, bp, value)
        return bytes(result)

    def write_local_interconnect(self, rbf_data, zero_data, lx, ly, pair_bases, value=True):
        """Set/clear LOCAL_INTERCONNECT cells for an EXPLICIT (pair, base_idx) list.

        SAFETY: this method no longer accepts an I-index. Callers must pass
        the exact list of (pair, base_idx) tuples to flip, where:
            pair      ∈ 0..8
            base_idx  ∈ 0 (base offset 70) | 1 (base offset 71)

        For backwards convenience, bare ints are accepted and treated as
        (pair, 0) — i.e. base 70 only — but this is discouraged for new code.

        Args:
            pair_bases: iterable of (pair, base_idx) tuples (or bare pair ints)
        """
        if lx not in COLUMN_BASE:
            raise ValueError(f"X={lx} not in COLUMN_BASE (valid: {sorted(COLUMN_BASE.keys())})")
        if ly not in LAB_Y:
            raise ValueError(f"Y={ly} not a valid LAB Y coordinate")

        norm = []
        for item in pair_bases:
            if isinstance(item, int):
                pair, base_idx = item, 0
            else:
                pair, base_idx = item
            if not (0 <= pair <= 8):
                raise ValueError(f"pair {pair} out of range 0-8")
            if base_idx not in (0, 1):
                raise ValueError(f"base_idx {base_idx} must be 0 or 1")
            norm.append((pair, base_idx))
        if not norm:
            raise ValueError("pair_bases must be non-empty (no implicit I-index expansion)")

        col_start = COLUMN_BASE[lx] - 136
        group, slot, bp = _cram_group_bit(ly)
        slot_off = _LI_SLOT_OFFSET[slot]

        result = bytearray(rbf_data)
        for pair, base_idx in norm:
            base = 70 + base_idx
            offset = col_start + base + pair * PAIR_SPACING + slot_off + 3 * group
            self._set_bit(result, zero_data, offset, bp, value)
        return bytes(result)

    def apply_routing(self, zero_data, switches):
        """Batch apply multiple routing switches to a zero baseline.

        Args:
            zero_data: bytes of the zero-mask baseline RBF
            switches: list of dicts, each with 'type' key ('c4', 'r4', 'li')
                      plus type-specific params:
                      - c4: x, y
                      - r4: wx, y, i_idx
                      - li: lx, ly, pairs (explicit list — no I-index expansion)

        Returns:
            Modified RBF as bytes
        """
        result = bytearray(zero_data)
        data = bytes(result)  # immutable snapshot for read

        for sw in switches:
            sw_type = sw.get('type')
            if sw_type == 'c4':
                ii = sw.get('i_idx', 0)
                if ii == 0:
                    data = self.write_c4(data, zero_data, sw['x'], sw['y'],
                                         sw.get('value', True))
                else:
                    data = self.write_c4_inz(data, zero_data, sw['x'], ii,
                                             sw['y'], sw.get('value', True))
            elif sw_type == 'r4':
                data = self.write_r4(data, zero_data, sw['wx'], sw['y'],
                                     sw['i_idx'], sw.get('value', True))
            elif sw_type == 'r24':
                data = self.write_r24(data, zero_data, sw['wx'], sw['y'],
                                      sw.get('i_idx', 0), sw.get('value', True),
                                      cells=sw.get('cells'))
            elif sw_type == 'raw':
                # Single-bit flip: used by round-trip to faithfully replay
                # reads of types whose write path is wire-level (R24, LI).
                buf = bytearray(data)
                self._set_bit(buf, zero_data, sw['offset'], sw['bp'],
                              sw.get('value', True))
                data = bytes(buf)
            elif sw_type == 'li':
                pb = sw.get('pair_bases', sw.get('pairs'))
                if pb is None:
                    raise ValueError(
                        "li switch requires explicit 'pair_bases' list of "
                        "(pair, base_idx) tuples — implicit I-index expansion "
                        "removed for hardware safety"
                    )
                data = self.write_local_interconnect(data, zero_data, sw['lx'],
                                                     sw['ly'], pb,
                                                     sw.get('value', True))
            else:
                raise ValueError(f"Unknown switch type: {sw_type!r}")
        return data

    # Empirically observed envelope (single-input lut2 sweep, 21 valid LABs):
    #   * always exactly 9 active cells per LAB
    #   * P8 always present with exactly one base
    #   * Mode "paired":  P0 has both bases; 4 middle pairs have both bases; +P8 single
    #   * Mode "alternating": P0..P7 each single base alternating B1/B0/B1/.../B0; +P8 single
    LI_MAX_CELLS_PER_LAB = 9
    LI_MAX_PAIRED_PAIRS = 4    # middle paired pairs (excluding P8) — paired mode
    LI_MAX_PAIRS_PER_LAB = 5   # legacy alias (kept for callers)

    # ------------------------------------------------------------------
    # LI mode-by-column consensus table (2026-04-07)
    # Built from a 22-LAB × 3-src sweep (66 compiles) — see
    # results/li_mode_column_table.json and fuzz/li_mode_column_table.py
    #
    # 16/22 columns are unanimous across all 3 srcs ('✓'); 6/22 are mixed
    # ('△') — for those we record the majority vote and keep the raw
    # per-src observation in the comment for future debugging. Both modes
    # are physically legal Quartus outputs, so a wrong guess on a mixed
    # column should still produce a hardware-safe bitstream — pending
    # roundtrip verification on AX301.
    # ------------------------------------------------------------------
    LI_MODE_BY_X = {
        3:  "alternating",   # ✓
        4:  "paired",        # ✓
        # Jailbreak edge column (memory hero_edge_x5_fasm_silicon).
        # LI mode UNMINED — default "alternating" lets plan_hops continue
        # without raising; resulting cells go through safety validator
        # before any flash, so a wrong default fails closed.
        5:  "alternating",   # ⚠ UNMINED jailbreak
        6:  "alternating",   # △ AMBIGUOUS — majority 2/3 (src(25,15)→paired)
        7:  "alternating",   # ✓
        8:  "alternating",   # △ AMBIGUOUS — majority 2/3 (src(25,15)→paired)
        9:  "alternating",   # ⚠ UNMINED jailbreak
        10: "paired",        # ✓
        11: "paired",        # △ AMBIGUOUS — majority 2/3 (src(25,15)→alternating)
        12: "paired",        # ✓
        13: "alternating",   # ✓
        14: "alternating",   # ⚠ UNMINED jailbreak
        16: "paired",        # ✓
        17: "alternating",   # ✓
        18: "paired",        # ✓
        19: "alternating",   # ✓
        21: "paired",        # ✓
        22: "alternating",   # △ AMBIGUOUS — majority 2/3 (src(17,8)→paired)
        23: "paired",        # ✓
        24: "paired",        # ✓
        25: "paired",        # ✓
        26: "paired",        # △ AMBIGUOUS — majority 2/3 (src(3,5)→alternating)
        28: "alternating",   # △ AMBIGUOUS — majority 2/3 (src(25,15)→paired)
        29: "alternating",   # ✓
        30: "alternating",   # ⚠ UNMINED jailbreak
        31: "paired",        # ✓
        32: "alternating",   # ⚠ UNMINED jailbreak
        33: "alternating",   # ⚠ UNMINED jailbreak
    }
    LI_MODE_AMBIGUOUS_X = {6, 8, 11, 22, 26, 28}

    # ------------------------------------------------------------------
    # Typical LI 9-cell envelopes per mode (2026-04-07)
    # Extracted from results/li_envelope_typical.json — see
    # fuzz/extract_li_envelopes.py for the histogram source.
    #
    # paired: 5 distinct envelopes observed across 38 samples; the most
    #   common one ({P0,P2,P4,P6} fully paired + P8B0) covers 52.6%.
    # alternating: 2 distinct envelopes across 27 samples; the most common
    #   (strict P0..P7 B1/B0 alternation + P8B0) covers 55.6%. Both
    #   variants only differ in the P8 tail base.
    #
    # These are MVP defaults — the routing synthesizer emits them as the
    # first-choice envelope. If hardware roundtrip fails on a specific
    # column, fall back to the second-most-common variant for that mode.
    # ------------------------------------------------------------------
    LI_TYPICAL_ENVELOPE = {
        "paired": [
            (0, 0), (0, 1),
            (2, 0), (2, 1),
            (4, 0), (4, 1),
            (6, 0), (6, 1),
            (8, 0),
        ],
        "alternating": [
            (0, 1),
            (1, 0),
            (2, 1),
            (3, 0),
            (4, 1),
            (5, 0),
            (6, 1),
            (7, 0),
            (8, 0),
        ],
    }

    @staticmethod
    def select_li_mode(dst_x):
        """Return the preferred LI activation mode for a destination LAB column.

        For 16/22 LAB columns this is the unanimous Quartus choice across all
        observed source LABs. For the 6 ambiguous columns it is the majority
        vote — both modes are hardware-legal. Raises KeyError for non-LAB X.
        """
        return RouteCodec.LI_MODE_BY_X[dst_x]

    @staticmethod
    def _classify_li_lab(pair_map):
        """Classify a single LAB's {pair: set(base_idx)} → (mode, reason).

        Returns (mode, reason) where mode ∈ {"empty","paired","alternating","invalid"}.
        Empirically validated against 21 single-input lut2 destination LABs.
        """
        if not pair_map:
            return "empty", None

        n_cells = sum(len(bs) for bs in pair_map.values())

        # Source-side LE driver mode: exactly {(8,0), (8,1)} and nothing else.
        # Discovered via L2 diff (2026-04-07): every routed signal in a real
        # Quartus RBF activates these two cells at the source LAB. They are
        # the LE→routing-network output driver MUX, NOT a destination LI
        # envelope. Recognized as a third valid mode so writers can emit it.
        if set(pair_map.keys()) == {8} and pair_map[8] == {0, 1}:
            return "driver", None

        # Single-P8 driver mode: exactly {(8, single_base)} — the
        # post-Path-X residual after collision suppression, AND the
        # ground-truth Quartus pattern at certain green-zone fingerprint
        # source LABs (e.g. pipeline_test (10,10) / (10,11) reached via
        # snapshot mode). Confirmed silicon-safe by byte-identity vs
        # Quartus gold. Memory step_3_jailbreak_x_cram_gap_2026_05_02.
        if set(pair_map.keys()) == {8} and len(pair_map[8]) == 1:
            return "driver_single", None

        # paired_carry_input: EP4CE6 multi-LAB carry-chain LI MUX pattern.
        # Checked BEFORE the global LI_MAX_CELLS_PER_LAB cap because
        # Quartus emits up to 11 cells in this topology (W=19..28 even
        # widths) — strictly above the 9-cell cap that bounds standard
        # LUT-routing modes. Discovered 2026-05-03 night via Quartus
        # c{W}_ml gold mining (W∈[17,32] counters at LAB(4,18)+(4,17)).
        # Two observed Quartus sub-shapes:
        #   * narrow (W∈{17,31,32}):  no P8, e.g. {0:[0,1], 1:[0,1], 4:[0,1], 5:[0,1]}
        #   * with P8 tail:           P8=[0] single, e.g. {1:[0,1], 2:[0,1], 5:[0,1], 6:[0,1], 7:[0,1], 8:[0]}
        # P8 bases up to {0,1} also accepted: hand-FASM at LAB(4,17)
        # picks up an extra P8[1] cell from `LAB_CLK_SEL_LE X4Y17N0`'s
        # codec (per-LE clock-select cell that aliases onto LI MUX P8
        # base 1 in the LI codec's interpretation, but isn't a routing
        # short-circuit). W=17 silicon flash 2026-05-02 with this exact
        # extra cell → LED solid-on, no hazard. Silicon-safe by both
        # Quartus emission AND HW validation. See memory
        # `multi_lab_carry_silicon_validated_2026_05_03.md`.
        non_p8_pairs = {p: bs for p, bs in pair_map.items() if p != 8}
        if (non_p8_pairs and
            all(bs == {0, 1} for bs in non_p8_pairs.values()) and
            (8 not in pair_map or pair_map[8] <= {0, 1})):
            return "paired_carry_input", None

        if n_cells > RouteCodec.LI_MAX_CELLS_PER_LAB:
            return "invalid", f"{n_cells} cells > {RouteCodec.LI_MAX_CELLS_PER_LAB}"

        # Edge mode: even pairs only (P0,P2,P4,P6 or subset), all base 0,
        # no P8. Observed at top/bottom-row LABs (Y2, Y21) where the LI
        # MUX has fewer routing options. Calibrated against Quartus's
        # own (10,10)→(10,2) baseline (2026-04-07).
        if 8 not in pair_map and all(p % 2 == 0 and bs == {0}
                                      for p, bs in pair_map.items()):
            return "edge_even_b0", None

        # edge_even_b0 variant WITH P8 tail (also base 0). Observed at
        # top-row destinations like (22,2) reached from interior (22,12)
        # source — δ green island. Strict subset of edge_even_b0 cells
        # plus a base-0 P8 anchor; classified separately so the envelope
        # remains explicit and the writer doesn't emit a paired-mode P0.
        if all(p % 2 == 0 and bs == {0} for p, bs in pair_map.items()):
            return "edge_even_b0_p8", None

        # edge_pair_groups_b0: subset of {(P0,P1),(P2,P3),(P4,P5),(P6,P7)}
        # consecutive-pair groups, all base 0, optional P8B0 tail. Observed
        # at Y=2 top-row destinations across γ (4,4) and (28,10) corpora.
        # 4 distinct envelopes silicon-emitted by Quartus (2026-04-07):
        #   {0,1,4,5} / {0,1,2,3} / {0,1,2,3,8} / {0,1,4,5,8}
        # Hardware-safe by construction (all four came from real Quartus
        # RBFs). Less restrictive than edge_even_b0 — allows odd pairs as
        # long as they pair with the preceding even pair.
        non_p8 = {p: bs for p, bs in pair_map.items() if p != 8}
        if (all(bs == {0} for bs in pair_map.values()) and
            (8 not in pair_map or pair_map[8] == {0})):
            # Each non-P8 pair must be paired with its consecutive sibling
            # forming a (2k, 2k+1) group. I.e. for each odd p, p-1 is also
            # active; for each even p, p+1 is also active.
            valid_groups = True
            for p in non_p8:
                sibling = p + 1 if p % 2 == 0 else p - 1
                if sibling not in non_p8:
                    valid_groups = False
                    break
            if valid_groups and non_p8:
                return "edge_pair_groups_b0", None

        # P8 anchor: must be present with exactly one base
        if 8 not in pair_map:
            return "invalid", "missing P8 tail anchor"
        if len(pair_map[8]) != 1:
            return "invalid", "P8 tail must have exactly one base"

        # P0 must be present
        if 0 not in pair_map:
            return "invalid", "missing P0 anchor"

        middle = {p: bs for p, bs in pair_map.items() if p not in (0, 8)}
        p0_bases = pair_map[0]

        # Paired mode: P0 fully paired
        if p0_bases == {0, 1}:
            paired_pairs_incl_p0 = [p for p, bs in pair_map.items()
                                     if p != 8 and bs == {0, 1}]
            single_middle = [p for p, bs in middle.items() if len(bs) == 1]
            if single_middle:
                return "invalid", f"paired mode but middle pairs {single_middle} are single-base"
            n_middle_paired = len(paired_pairs_incl_p0) - 1   # exclude P0
            if n_middle_paired > RouteCodec.LI_MAX_PAIRED_PAIRS:
                return "invalid", f"{n_middle_paired} middle paired pairs > {RouteCodec.LI_MAX_PAIRED_PAIRS}"
            return "paired", None

        # Alternating mode: P0 has only B1
        if p0_bases == {1}:
            doubled = [p for p, bs in middle.items() if bs == {0, 1}]
            if doubled:
                return "invalid", f"alternating mode but middle pairs {doubled} have both bases"
            # Expect contiguous P0..P7 with alternating pattern P0=B1, P1=B0, P2=B1, ...
            for p in range(8):
                if p not in pair_map:
                    return "invalid", f"alternating mode missing pair P{p}"
                expected = {1} if p % 2 == 0 else {0}
                if pair_map[p] != expected:
                    return "invalid", (f"alternating mode P{p} expected base "
                                       f"{1 if p%2==0 else 0}, got {sorted(pair_map[p])}")
            return "alternating", None

        return "invalid", f"P0 bases {sorted(p0_bases)} match neither paired nor alternating mode"

    def validate_safe_for_hardware(self, rbf_data, zero_data,
                                    li_max_pairs=None, raise_on_fail=True):
        """Pre-flash safety check for LI cell activation (V2 — signature aware).

        Empirically, Quartus emits LI activations in two distinct encoding
        modes that coexist across the chip but never (so far) within the
        same LAB:

          * "paired" mode: every active pair has BOTH base 70 and base 71
            set together. ≤5 such pairs per LAB observed.
          * "alternating" mode: every active pair has EXACTLY ONE of
            {base 70, base 71} set, alternating across pair indices.
            ≤9 active bytes per LAB observed.

        Three rules:
          1. paired mode → number of paired pairs ≤ LI_MAX_PAIRED_PAIRS
          2. alternating mode → total active bytes ≤ LI_MAX_ALT_BYTES,
             AND no pair has both bases set
          3. mixed mode (some pairs paired, some alternating in the same
             LAB) → PANIC; never observed from Quartus, so refuse to flash

        Returns the list of violations as
        (lx, ly, mode, detail_dict). Empty list = safe.
        """
        li_entries = self.read_local_interconnect(rbf_data, zero_data)

        # Group by (lx, ly) → {pair: set(base_idx)}
        per_lab = {}
        for name, _off, _bp, _cands in li_entries:
            lx, ly, pair, base_idx = self._parse_li_name(name)
            per_lab.setdefault((lx, ly), {}).setdefault(pair, set()).add(base_idx)

        violations = []
        for (lx, ly), pair_map in per_lab.items():
            mode, reason = self._classify_li_lab(pair_map)
            if mode == "invalid":
                violations.append((lx, ly, mode, {
                    "reason": reason,
                    "pair_map": {p: sorted(bs) for p, bs in sorted(pair_map.items())},
                }))

        if violations and raise_on_fail:
            lines = [
                f"  LAB X{lx} Y{ly}: {info['reason']} | {info['pair_map']}"
                for lx, ly, _, info in sorted(violations, key=lambda v: (v[0], v[1]))
            ]
            raise RuntimeError(
                "UNSAFE FOR HARDWARE: LOCAL_INTERCONNECT activation outside known-safe envelope\n"
                + "\n".join(lines)
                + "\n  Flashing this RBF may cause input MUX short circuits."
            )
        return violations

    def read_switches(self, rbf_data, zero_data, wire_types=None):
        """Read all active routing switches from RBF.

        Args:
            rbf_data: bytes of the design RBF
            zero_data: bytes of the zero-mask baseline RBF
            wire_types: optional set of types to read, e.g. {'c4', 'r4', 'li'}
                        None means read all types

        Returns:
            dict mapping wire type to list of (wire_name, byte_offset, bit_pos)
        """
        if wire_types is None:
            wire_types = {'c4', 'r4', 'r24', 'li'}

        # Mask CRC bytes so a CRC patch doesn't leak into the routing diff.
        rbf_data = mask_rbf_crc_bytes(rbf_data, zero_data)

        result = {}
        if 'c4' in wire_types:
            result['c4'] = self.read_c4(rbf_data, zero_data)
        if 'r4' in wire_types:
            result['r4'] = self.read_r4(rbf_data, zero_data)
        if 'r24' in wire_types:
            result['r24'] = self.read_r24(rbf_data, zero_data)
        if 'li' in wire_types:
            result['li'] = self.read_local_interconnect(rbf_data, zero_data)
        return result


# Minterm-to-cell permutation lookup table.  Keyed by (foff, fb%8) where
# foff = in-frame byte offset of the pair-0/delta-0 cell (24+SLOT_BASE+grp*3+nd)%210
# and fb%8 = frame byte index mod 8.
# Each entry is (foff, s0, s1, s2, s3) giving σ⁻¹.
# Mined 2026-04-21 from Quartus 4-input FACE probes at 233 pipeline positions.
# 9 distinct permutations.  Nearest-foff fallback for uncovered positions.
_SIGMA_INV_BY_FB8 = {
    0: [(1,0,2,1,3),(13,0,2,1,3),(16,0,2,1,3),(23,0,2,1,3),(24,0,2,1,3),(26,0,2,1,3),(31,0,2,1,3),
        (32,0,2,1,3),(37,0,2,1,3),(39,0,2,1,3),(40,0,2,1,3),(45,0,1,2,3),(47,0,1,2,3),(53,0,1,2,3),
        (55,0,1,2,3),(61,0,1,2,3),(63,0,1,2,3),(69,0,1,2,3),(71,0,1,2,3),(83,0,1,2,3),(85,0,1,2,3),
        (91,0,1,2,3),(93,0,1,2,3),(99,0,1,2,3),(101,0,1,2,3),(109,0,1,2,3),(112,0,3,1,2),(114,0,3,1,2),
        (120,0,3,1,2),(122,0,3,1,2),(128,0,3,1,2),(130,0,3,1,2),(136,0,3,1,2),(138,0,3,1,2),(150,0,3,1,2),
        (152,0,3,1,2),(158,0,3,1,2),(160,0,3,1,2),(166,0,3,1,2),(174,0,3,1,2),(176,0,3,1,2),(184,0,2,1,3),
        (185,0,2,1,3),(187,0,2,1,3),(192,0,2,1,3),(200,0,2,1,3),(206,0,2,1,3)],
    1: [(1,0,2,1,3),(2,0,2,3,1),(4,0,2,3,1),(13,0,2,1,3),(15,0,2,1,3),(18,0,2,3,1),(21,0,2,1,3),
        (23,0,2,1,3),(31,0,2,1,3),(32,0,2,3,1),(34,0,2,3,1),(37,0,2,1,3),(40,0,2,3,1),(45,1,3,0,2),
        (47,1,3,0,2),(55,1,3,0,2),(61,1,3,0,2),(63,1,3,0,2),(71,1,3,0,2),(83,1,3,0,2),(91,1,3,0,2),
        (93,1,3,0,2),(99,1,3,0,2),(101,1,3,0,2),(107,1,3,0,2),(109,1,3,0,2),(112,0,1,2,3),(114,0,1,2,3),
        (120,0,1,2,3),(130,0,1,2,3),(136,0,1,2,3),(138,0,1,2,3),(150,0,1,2,3),(152,0,1,2,3),(158,0,1,2,3),
        (160,0,1,2,3),(168,0,1,2,3),(174,0,1,2,3),(176,0,1,2,3),(184,0,2,1,3),(185,0,2,3,1),(190,0,2,1,3),
        (192,0,2,1,3),(195,0,2,3,1),(198,0,2,1,3),(201,0,2,3,1),(203,0,2,3,1),(206,0,2,1,3)],
    3: [(13,0,2,1,3),(18,0,1,2,3),(21,0,2,1,3),(24,0,1,2,3),(26,0,1,2,3),(31,0,2,1,3),(39,0,2,1,3),
        (45,1,3,0,2),(47,1,3,0,2),(53,1,3,0,2),(55,1,3,0,2),(61,1,3,0,2),(63,1,3,0,2),(69,1,3,0,2),
        (71,1,3,0,2),(83,1,3,0,2),(85,1,3,0,2),(91,1,3,0,2),(93,1,3,0,2),(99,1,3,0,2),(101,1,3,0,2),
        (107,1,3,0,2),(109,1,3,0,2),(112,0,2,1,3),(114,0,2,1,3),(120,0,2,1,3),(122,0,2,1,3),(128,0,2,1,3),
        (130,0,2,1,3),(138,0,2,1,3),(150,0,2,1,3),(158,0,2,1,3),(166,0,2,1,3),(168,0,2,1,3),(174,0,2,1,3),
        (176,0,2,1,3),(184,0,2,1,3),(185,0,1,2,3),(190,0,2,1,3),(193,0,1,2,3),(195,0,1,2,3),(198,0,2,1,3),
        (200,0,2,1,3),(201,0,1,2,3),(203,0,1,2,3)],
    4: [(1,0,1,3,2),(13,0,1,3,2),(15,0,1,3,2),(16,0,1,3,2),(18,0,1,3,2),(21,0,1,3,2),(23,0,1,3,2),
        (24,0,1,3,2),(29,0,1,3,2),(31,0,1,3,2),(34,0,1,3,2),(37,0,1,3,2),(39,0,1,3,2),(40,0,1,3,2),
        (45,1,3,0,2),(47,1,3,0,2),(55,1,3,0,2),(61,1,3,0,2),(69,1,3,0,2),(71,1,3,0,2),(83,1,3,0,2),
        (85,1,3,0,2),(91,1,3,0,2),(93,1,3,0,2),(99,1,3,0,2),(101,1,3,0,2),(107,1,3,0,2),(109,1,3,0,2),
        (112,1,3,0,2),(114,1,3,0,2),(120,1,3,0,2),(130,1,3,0,2),(138,1,3,0,2),(150,1,3,0,2),(152,1,3,0,2),
        (166,1,3,0,2),(182,0,1,3,2),(184,0,1,3,2),(185,0,1,3,2),(187,0,1,3,2),(192,0,1,3,2),(195,0,1,3,2),
        (198,0,1,3,2),(200,0,1,3,2),(203,0,1,3,2),(206,0,1,3,2)],
    7: [(1,1,2,0,3),(4,0,1,3,2),(13,1,2,0,3),(15,1,2,0,3),(16,0,1,3,2),(21,1,2,0,3),(29,1,2,0,3),
        (31,1,2,0,3),(37,1,2,0,3),(39,1,2,0,3),(45,0,3,2,1),(47,0,3,2,1),(53,0,3,2,1),(55,0,3,2,1),
        (61,0,3,2,1),(63,0,3,2,1),(69,0,3,2,1),(71,0,3,2,1),(83,0,3,2,1),(85,0,3,2,1),(91,0,3,2,1),
        (93,0,3,2,1),(99,0,3,2,1),(101,0,3,2,1),(107,0,3,2,1),(109,0,3,2,1),(112,1,3,2,0),(114,1,3,2,0),
        (120,1,3,2,0),(130,1,3,2,0),(136,1,3,2,0),(138,1,3,2,0),(150,1,3,2,0),(152,1,3,2,0),(158,1,3,2,0),
        (160,1,3,2,0),(166,1,3,2,0),(168,1,3,2,0),(174,1,3,2,0),(176,1,3,2,0),(182,1,2,0,3),(187,0,1,3,2),
        (190,1,2,0,3),(192,1,2,0,3),(198,1,2,0,3),(200,1,2,0,3),(206,1,2,0,3)],
}
# Parse into {(foff, fb8): (s0, s1, s2, s3)} dict at import time
# Legacy 2-key cache (fb8-only groups from the original 233-position mining).
_SIGMA_INV_CACHE = {}
_SIGMA_INV_SORTED = {}  # fb8 -> sorted list of (foff, sigma_inv) for interpolation
for _fb8, _entries in _SIGMA_INV_BY_FB8.items():
    _sorted = []
    for _e in _entries:
        _foff, _s0, _s1, _s2, _s3 = _e
        _si = (_s0, _s1, _s2, _s3)
        _SIGMA_INV_CACHE[(_foff, _fb8)] = _si
        _sorted.append((_foff, _si))
    _SIGMA_INV_SORTED[_fb8] = _sorted

# Extended 3-key cache: (foff, fb8, group) → σ⁻¹.
# σ⁻¹ depends on group (= (y-2)//3), not just (foff, fb8).
# Loaded from results/sigma_inv_fb8_groups.json at import time.
_SIGMA_INV_3KEY = {}  # (foff, fb8, group) -> (s0,s1,s2,s3)
_SIGMA_INV_3KEY_SORTED = {}  # (fb8, group) -> sorted [(foff, si)]
_sigma_inv_3key_path = _os_path.join(
    _os_path.dirname(_os_path.dirname(_os_path.abspath(__file__))),
    "results", "sigma_inv_fb8_groups.json")
if _os_path.exists(_sigma_inv_3key_path):
    import json as _json_loader
    with open(_sigma_inv_3key_path) as _f3:
        _data3 = _json_loader.load(_f3)
    for _k3, _v3 in _data3.get("entries", {}).items():
        _foff3 = _v3["foff"]
        _fb83 = _v3["fb8"]
        _grp3 = _v3["group"]
        _si3 = tuple(_v3["sigma_inv"])
        _SIGMA_INV_3KEY[(_foff3, _fb83, _grp3)] = _si3
        _bg_key = (_fb83, _grp3)
        if _bg_key not in _SIGMA_INV_3KEY_SORTED:
            _SIGMA_INV_3KEY_SORTED[_bg_key] = []
        _SIGMA_INV_3KEY_SORTED[_bg_key].append((_foff3, _si3))
    for _bg_key in _SIGMA_INV_3KEY_SORTED:
        _SIGMA_INV_3KEY_SORTED[_bg_key].sort()
    del _json_loader, _f3, _data3


def _sigma_inv_lookup(foff, fb8, group=None):
    """Look up σ⁻¹ for a given (foff, fb%8) and optionally group.

    Lookup order:
    1. Exact (foff, fb8, group) in 3-key cache
    2. Nearest-foff in same (fb8, group) bucket
    3. Exact (foff, fb8) in legacy 2-key cache
    4. Nearest-foff in same fb8 bucket
    5. Identity fallback (0, 1, 2, 3)
    """
    if group is not None:
        key3 = (foff, fb8, group)
        if key3 in _SIGMA_INV_3KEY:
            return _SIGMA_INV_3KEY[key3]
        entries3 = _SIGMA_INV_3KEY_SORTED.get((fb8, group))
        if entries3:
            best_dist = 999
            best_si = entries3[0][1]
            for ef, si in entries3:
                d = abs(ef - foff)
                if d < best_dist:
                    best_dist = d
                    best_si = si
            return best_si
    key = (foff, fb8)
    if key in _SIGMA_INV_CACHE:
        return _SIGMA_INV_CACHE[key]
    entries = _SIGMA_INV_SORTED.get(fb8)
    if not entries:
        return (0, 1, 2, 3)
    best_dist = 999
    best_si = entries[0][1]
    for ef, si in entries:
        d = abs(ef - foff)
        if d < best_dist:
            best_dist = d
            best_si = si
    return best_si


class LutCodec:
    """XOR-linear LUT truth table codec for one LE position."""

    def __init__(self, x, y, n, minterm_patterns):
        """
        Args:
            x, y, n: LE coordinates
            minterm_patterns: dict mapping TT bit (0-15) to set of (byte_offset, bit_position)
        """
        self.x = x
        self.y = y
        self.n = n
        self.patterns = minterm_patterns  # {bit: set((addr, bitpos), ...)}

        # Build reverse map: (addr, bitpos) -> set of TT bits that flip it
        self.reverse = defaultdict(set)
        for bit, cells in self.patterns.items():
            for cell in cells:
                self.reverse[cell].add(bit)

        # All SRAM cells involved in this LE's TT
        self.all_cells = set()
        for cells in self.patterns.values():
            self.all_cells |= cells

        # Identify ctrl cells: cells that appear in exactly ONE minterm pattern
        # These are unique discriminators for each TT bit
        self.ctrl_cells = {}  # bit -> (addr, bitpos)
        cell_count = defaultdict(int)
        cell_owner = {}
        for bit, cells in self.patterns.items():
            for cell in cells:
                cell_count[cell] += 1
                cell_owner[cell] = bit

        for cell, count in cell_count.items():
            if count == 1:
                bit = cell_owner[cell]
                if bit not in self.ctrl_cells:
                    self.ctrl_cells[bit] = cell

    @classmethod
    def from_db(cls, db, x, y, n):
        """Load calibrated minterm patterns from SQLite database."""
        patterns = {}
        for bit in range(16):
            feature = f"minterm_{bit}"
            rows = db.execute(
                """SELECT byte_offset, bit_position
                   FROM bit_mapping
                   WHERE feature=? AND x=? AND y=? AND n=?
                   AND byte_offset > 256""",
                (feature, x, y, n),
            ).fetchall()
            if not rows:
                raise ValueError(
                    f"No minterm_{bit} data for ({x},{y},{n}). "
                    f"Run: python runner.py n_sweep {x} {y} first."
                )
            # Filter CRC bytes (last 2 bytes of each 210-byte CRAM frame,
            # frames 25..1751). These are frame-CRC false positives from
            # pre-CRC-normalized mining — they flip because the preceding
            # data bytes changed, not because they encode the minterm.
            patterns[bit] = set(
                (bo, bp) for bo, bp in rows
                if not (5282 <= bo < 367952 and (bo - 32) % 210 >= 208)
            )
        return cls(x, y, n, patterns)

    @classmethod
    def from_cram_model(cls, x, y, n):
        """Build LutCodec from the CRAM address formula (no database needed).

        Uses a permutation σ⁻¹ (looked up by in-frame offset and frame
        index mod 8) to correctly assign minterms to physical cells.
        The 16 cell ADDRESSES are computed from the CRAM model; σ⁻¹
        determines which minterm maps to which (pair, delta) cell.

        Slot-1 Y rows (Y=3,6,9,12,15,18,21) have low SLOT_BASE (0), so
        high-N LEs can push the in-frame offset below zero.  The real
        CRAM layout wraps these into the upper data region of the same
        frame (foff ~182-207) with a different bitpos.
        """
        slot = (y - 2) % 3
        group = (y - 2) // 3
        nd = cram_n_delta(n)
        # Slot-1 wrap: Y=3 (group=0) admits the boundary N=12 (nd=-24) and
        # shifts by 206; Y=6/9/12 shift by 207 and exclude the boundary.
        if slot == 1 and group == 0:
            wrapped = (24 + nd <= 0)
            if wrapped:
                bp = 7 - group
                addr_adj = 206
            else:
                bp = cram_ctrl_bit(y)
                addr_adj = 0
        else:
            wrapped = slot == 1 and (24 + group * 3 + nd < 0)
            if wrapped:
                bp = 7 - group
                addr_adj = 207
            else:
                bp = cram_ctrl_bit(y)
                addr_adj = 0
        offset = SLOT_BASE[slot] + group * 3 + (1 if slot == 0 and group > 0 else 0)
        val = COLUMN_BASE[x] - 168 + offset + nd + addr_adj
        foff = val % 210
        fb8 = (val // 210) % 8
        sigma_inv = _sigma_inv_lookup(foff, fb8, group)
        sigma = [0] * 4
        for i, j in enumerate(sigma_inv):
            sigma[j] = i
        k = n // 2
        patterns = {}
        for b in range(16):
            f0_tgt = (b >> sigma[0]) & 1
            f1_tgt = (b >> sigma[1]) & 1
            f2_tgt = (b >> sigma[2]) & 1
            f3_tgt = (b >> sigma[3]) & 1
            pair = ((1 - f0_tgt) << 2) | ((1 - f1_tgt) << 1) | (1 - f2_tgt)
            da = f3_tgt ^ (1 - f2_tgt)
            delta = da if k % 2 == 0 else 1 - da
            addr = cram_ctrl_addr(x, y, pair, n) + delta + addr_adj
            patterns[b] = {(addr, bp)}
        return cls(x, y, n, patterns)

    def predict_sram(self, mask):
        """Predict which SRAM cells differ from zero for a given 16-bit mask.

        Returns set of (byte_offset, bit_position) that should be flipped
        relative to the zero-mask (0x0000) baseline.
        """
        result = set()
        for bit in range(16):
            if mask & (1 << bit):
                result ^= self.patterns[bit]
        return result

    def read_tt(self, rbf_data, zero_data):
        """Read the current LUT truth table from RBF data.

        Uses ctrl bytes as discriminators: each TT bit has a unique ctrl byte
        that is only set when that TT bit is active. By checking ctrl bytes,
        we can directly determine each TT bit's state.

        Args:
            rbf_data: bytes of the RBF to read from
            zero_data: bytes of the zero-mask (0x0000) baseline RBF

        Returns:
            16-bit integer truth table mask
        """
        if not self.ctrl_cells:
            # Fall back to exhaustive search if ctrl cells not identified
            return self._read_tt_bruteforce(rbf_data, zero_data)

        mask = 0
        for bit, (addr, bitpos) in self.ctrl_cells.items():
            rbf_bit = (rbf_data[addr] >> bitpos) & 1
            zero_bit = (zero_data[addr] >> bitpos) & 1
            if rbf_bit != zero_bit:
                mask |= (1 << bit)
        return mask

    def _read_tt_bruteforce(self, rbf_data, zero_data):
        """Fallback reader using exhaustive XOR search."""
        active_cells = set()
        for addr, bitpos in self.all_cells:
            rbf_bit = (rbf_data[addr] >> bitpos) & 1
            zero_bit = (zero_data[addr] >> bitpos) & 1
            if rbf_bit != zero_bit:
                active_cells.add((addr, bitpos))

        # Try all 65536 masks (fast for 16-bit)
        for mask in range(65536):
            if self.predict_sram(mask) == active_cells:
                return mask
        return -1  # Should never happen

    def write_tt(self, zero_data, mask):
        """Write a truth table mask into an RBF, starting from zero baseline.

        Args:
            zero_data: bytes of the zero-mask baseline RBF
            mask: 16-bit truth table mask to write

        Returns:
            Modified RBF as bytearray
        """
        result = bytearray(zero_data)
        sram_cells = self.predict_sram(mask)

        for addr, bitpos in sram_cells:
            result[addr] ^= (1 << bitpos)

        return bytes(result)

    def modify_tt(self, rbf_data, zero_data, new_mask):
        """Modify an existing RBF to change one LE's truth table.

        First reads the current TT, then applies the delta to get new_mask.

        Args:
            rbf_data: bytes of the current RBF
            zero_data: bytes of the zero-mask baseline RBF
            new_mask: desired 16-bit truth table mask

        Returns:
            Modified RBF as bytearray
        """
        current_mask = self.read_tt(rbf_data, zero_data)
        current_sram = self.predict_sram(current_mask)
        new_sram = self.predict_sram(new_mask)

        # Delta = XOR of current and new
        delta = current_sram ^ new_sram

        result = bytearray(rbf_data)
        for addr, bitpos in delta:
            result[addr] ^= (1 << bitpos)

        return bytes(result)


def _load_ff_globals():
    """Load the 61-cell arst/ena global bit sets from ff_remine_final.json.

    Mined 2026-04-08 via ff_remine.py + ff_remine_r2.py (8-seed × 10-pin
    cross-validation, CRC-normalized). Each set has 61 cells = 48 header
    bitfield + 13 CRAM global clock/reset network. Falls back to empty
    sets if the file is missing (e.g. fresh clone before mining).
    """
    import json, os
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(os.path.dirname(here), "results", "ff_remine_final.json")
    try:
        d = json.load(open(path))
        return (
            [tuple(c) for c in d.get("arst_true_global", [])],
            [tuple(c) for c in d.get("ena_true_global", [])],
        )
    except FileNotFoundError:
        return [], []


_FF_ARST_GLOBAL, _FF_ENA_GLOBAL = _load_ff_globals()


class FFCodec:
    """FF control-signal mode bit codec (arst, ena) — device-global bits.

    Current (2026-04-08) status: encodes the 61 device-level FF ctrl bits
    found via seed × pin cross-validation (48 header + 13 CRAM each for
    arst/ena). These bits tell the FPGA "this design contains FFs that
    use arst/ena" at the device-feature-enable level.

    Per-LE FF mode bits ("which specific LE's FF uses arst") are NOT in
    this codec yet — they require multi-FF mining experiments.

    The old column-relative `_FF_ARST_CELLS` / `_FF_ENA_CELLS` tables are
    deprecated (94-100% of their entries were CRC byte artifacts that
    patch_rbf_crc silently cleaned up).
    """

    def _set_global(self, rbf_data, zero_data, cells, enable):
        """Idempotent absolute set: for each (off,bp), force the bit to its
        active polarity (enable=True) or zero-baseline polarity (enable=False).

        The active polarity is (zero_bit ^ 1) — i.e. the complement of the
        baseline byte's bit value — since the globals were mined as XOR diffs
        vs the zero-mask baseline.

        Calling repeatedly is safe: N concurrent FFs using arst share the
        same global bits, and each write clamps to the same target state
        (no XOR double-flip, no OR with stale state).
        """
        result = bytearray(rbf_data)
        for off, bp in cells:
            if not (0 <= off < len(result) and off < len(zero_data)):
                continue
            zero_bit = (zero_data[off] >> bp) & 1
            target_bit = (zero_bit ^ 1) if enable else zero_bit
            mask = 1 << bp
            result[off] = (result[off] & ~mask) | (target_bit << bp)
        return bytes(result)

    # Fuse: the 61 "globals" in ff_remine_final.json were mined from a 1-FF
    # design and conflate layer 1 (device feature enable) with layer 2
    # (per-LE arst bit). See memory: ff_per_le_layer2_header_band.md.
    # Clamping those cells on a real multi-FF design (e.g. reset-counter)
    # would corrupt header bits that should depend on LE placement. Keep
    # the _set_global engine healthy, but refuse to fire until Y=4 sweep
    # derives the layer-2 address model.
    _LAYER2_READY = False

    def write_arst(self, rbf_data, zero_data, enable=True):
        """Set the device-global arst feature bits. Idempotent.

        DISABLED: raises NotImplementedError until layer 2 (per-LE arst
        bit in header byte 73 + 44-52) is mapped. See
        memory/ff_per_le_layer2_header_band.md.
        """
        if not self._LAYER2_READY:
            raise NotImplementedError(
                "FFCodec.write_arst: layer 2 address model pending — "
                "the 61 'globals' are 1-FF-corpus artifacts and clamping "
                "them on a multi-FF design is unsafe. Run the Y=4 sweep "
                "and derive header_byte73_bp=f(lab_X,n) before enabling.")
        return self._set_global(rbf_data, zero_data, _FF_ARST_GLOBAL, enable)

    def write_ena(self, rbf_data, zero_data, enable=True):
        """Set the device-global ena feature bits. Idempotent.

        DISABLED: raises NotImplementedError until layer 2 is mapped.
        """
        if not self._LAYER2_READY:
            raise NotImplementedError(
                "FFCodec.write_ena: layer 2 address model pending — "
                "same caveat as write_arst.")
        return self._set_global(rbf_data, zero_data, _FF_ENA_GLOBAL, enable)

    def _read_global(self, rbf_data, zero_data, cells):
        hits = 0
        for off, bp in cells:
            if off < len(rbf_data) and off < len(zero_data):
                if (rbf_data[off] ^ zero_data[off]) & (1 << bp):
                    hits += 1
        return hits

    def read_arst_active(self, rbf_data, zero_data, threshold=0.5):
        """Return True if ≥threshold of arst global bits differ from zero."""
        hits = self._read_global(rbf_data, zero_data, _FF_ARST_GLOBAL)
        need = max(1, int(len(_FF_ARST_GLOBAL) * threshold))
        return hits >= need

    def read_ena_active(self, rbf_data, zero_data, threshold=0.5):
        """Return True if ≥threshold of ena global bits differ from zero."""
        hits = self._read_global(rbf_data, zero_data, _FF_ENA_GLOBAL)
        need = max(1, int(len(_FF_ENA_GLOBAL) * threshold))
        return hits >= need

    # Backward-compat shims (return empty / no-op for deprecated column-span API)
    def read_arst_span(self, rbf_data, zero_data):
        return []

    def read_ena_span(self, rbf_data, zero_data):
        return []
