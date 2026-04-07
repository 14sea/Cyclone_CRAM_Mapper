"""EP4CE6 bitstream read/write codec for LUT truth tables and routing.

Given calibrated minterm patterns at a position (X, Y, N), this module can:
1. Read the current LUT truth table from an RBF file
2. Write a new LUT truth table into an RBF file
3. Verify the XOR-linear encoding

Routing codec (RouteCodec) reads/writes switch states from/to RBF using CRAM address models:
- C4 column wires (I=0 formula + 24 per-(X,I) lookups for I≠0)
- R4 row wires (18 mapped I-indices)
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

from collections import defaultdict

from config import COLUMN_BASE, LAB_X, LAB_Y, PAIR_SPACING


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
    6:  (3612, 3822),   # delta=210, cross-Y 1 col prev=X31 (same BASE as I=8, 2026-04-06)
    8:  (3612, 3822),   # delta=210, cross-Y 1 col prev=X26 wide (same BASE as I=6, 2026-04-06)
    19: (2794, 3215),   # delta=421, cross-Y 1 col prev=X11 (2026-04-06)
    21: (2786, 3207),   # delta=421, cross-Y 2 cols prev=X13(wide),X22 (2026-04-06)
    25: (2762, 2972),   # delta=210, verified X4,X8
    27: (2754, 2964),   # delta=210, cross-Y 1 col prev=X26 wide (2026-04-06)
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
_R24_FIXED_OFFSETS = {
    0: [3124, 2705],  # pair-diff 66%/61%, 5-6 wx columns (2026-04-06)
}

# --- LOCAL_INTERCONNECT address model constants ---

# Pair activation patterns by I-index
_LI_ALL9 = {2, 15, 16, 18, 22, 33, 34, 35, 36, 37}
_LI_SKIP37 = {0, 30, 31}
_LI_EVEN = {24, 26, 28, 29, 32}
_LI_FIRST2 = {4, 17, 27}
_LI_SLOT_OFFSET = {0: 67, 1: -70, 2: 0}


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
    - R4: row wires (18 mapped I-indices), CRAM bits in previous LAB column
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

    def read_r24(self, rbf_data, zero_data):
        """Read active R24 switches.

        R24 uses FIXED byte offsets in prev column (no slot/group byte adjustment).
        Only bp changes with Y: bp = (6-group) if slot==2 else (7-group).

        Returns list of (wire_name, byte_offset, bit_pos) for active switches.
        """
        active = []
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
                            active.append((f"R24_X{wx}_Y{y}_N0_I{i_idx}", offset, bp))
        return active

    def write_r24(self, rbf_data, zero_data, wx, y, i_idx=0, value=True):
        """Set/clear an R24 switch.

        Sets ALL fixed-offset bits for the given I-index.

        Args:
            rbf_data: bytes of the RBF to modify
            zero_data: bytes of the zero-mask baseline RBF
            wx: wire X coordinate (3-33)
            y: LAB Y coordinate
            i_idx: I-index (default 0, must be in _R24_FIXED_OFFSETS)
            value: True to activate, False to deactivate

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

        result = bytearray(rbf_data)
        for fixed_off in _R24_FIXED_OFFSETS[i_idx]:
            offset = col_start + fixed_off
            self._set_bit(result, zero_data, offset, bp, value)
        return bytes(result)

    def read_local_interconnect(self, rbf_data, zero_data):
        """Read active LOCAL_INTERCONNECT switches.

        Returns list of (wire_name, byte_offset, bit_pos) for active switches.
        Since multiple I-indices share overlapping pair sets, each active CRAM
        cell is reported once with the list of candidate I-indices.
        Wire name format: LI_X{x}_Y{y}_P{pair} (pair index disambiguates).
        """
        active = []
        # All known I-indices
        all_i = sorted(_LI_ALL9 | _LI_SKIP37 | _LI_EVEN | _LI_FIRST2)

        for lx in LAB_X:
            if lx not in COLUMN_BASE:
                continue
            col_start = COLUMN_BASE[lx] - 136

            for ly in LAB_Y:
                group, slot, bp = _cram_group_bit(ly)
                slot_off = _LI_SLOT_OFFSET[slot]

                for pair in range(9):
                    for base in (70, 71):
                        offset = col_start + base + pair * PAIR_SPACING + slot_off + 3 * group
                        if offset < 0 or offset >= len(rbf_data):
                            continue
                        if (rbf_data[offset] >> bp) & 1 != (zero_data[offset] >> bp) & 1:
                            # Find which I-indices include this pair
                            candidates = [i for i in all_i if pair in _li_active_pairs(i)]
                            active.append((f"LI_X{lx}_Y{ly}_P{pair}", offset, bp, candidates))
                            break  # don't double-count base=70 vs 71
        return active

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

    def write_local_interconnect(self, rbf_data, zero_data, lx, ly, pairs, value=True):
        """Set/clear LOCAL_INTERCONNECT switches for an EXPLICIT pair list.

        SAFETY: this method no longer accepts an I-index. Empirically, real
        Quartus RBFs activate 1-5 LI pairs per LAB — never the 9-pair I-index
        "pattern" the read-side disambiguation table suggests. Auto-expanding
        from an I-index would over-activate input MUXes and risk physical
        contention on real silicon. Callers must pass the exact pair list.

        Args:
            rbf_data: bytes of the RBF to modify
            zero_data: bytes of the zero-mask baseline RBF
            lx: LAB X coordinate
            ly: LAB Y coordinate
            pairs: iterable of pair indices (0-8) to flip; must be non-empty
            value: True to activate, False to deactivate

        Returns:
            Modified RBF as bytes
        """
        if lx not in COLUMN_BASE:
            raise ValueError(f"X={lx} not in COLUMN_BASE (valid: {sorted(COLUMN_BASE.keys())})")
        if ly not in LAB_Y:
            raise ValueError(f"Y={ly} not a valid LAB Y coordinate")
        pairs = list(pairs)
        if not pairs:
            raise ValueError("pairs must be non-empty (no implicit I-index expansion)")
        for p in pairs:
            if not (0 <= p <= 8):
                raise ValueError(f"pair {p} out of range 0-8")

        col_start = COLUMN_BASE[lx] - 136
        group, slot, bp = _cram_group_bit(ly)
        slot_off = _LI_SLOT_OFFSET[slot]

        result = bytearray(rbf_data)
        for pair in pairs:
            offset = col_start + 70 + pair * PAIR_SPACING + slot_off + 3 * group
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
                                      sw.get('i_idx', 0), sw.get('value', True))
            elif sw_type == 'raw':
                # Single-bit flip: used by round-trip to faithfully replay
                # reads of types whose write path is wire-level (R24, LI).
                buf = bytearray(data)
                self._set_bit(buf, zero_data, sw['offset'], sw['bp'],
                              sw.get('value', True))
                data = bytes(buf)
            elif sw_type == 'li':
                if 'pairs' not in sw:
                    raise ValueError(
                        "li switch requires explicit 'pairs' list — "
                        "implicit I-index expansion removed for hardware safety"
                    )
                data = self.write_local_interconnect(data, zero_data, sw['lx'],
                                                     sw['ly'], sw['pairs'],
                                                     sw.get('value', True))
            else:
                raise ValueError(f"Unknown switch type: {sw_type!r}")
        return data

    # Empirically observed maximum LI pairs activated by Quartus per LAB
    # (5 pairs in column/row routes; raise only after confirming on more designs).
    LI_MAX_PAIRS_PER_LAB = 5

    def validate_safe_for_hardware(self, rbf_data, zero_data,
                                    li_max_pairs=None, raise_on_fail=True):
        """Pre-flash safety check for LOCAL_INTERCONNECT pair contention.

        LAB input MUXes are physically driven by routing channels. Activating
        too many LI pairs at the same (lx, ly) can cause multiple channels to
        drive the same LE input simultaneously — that's a short circuit on
        real silicon and can damage the device.

        This method scans the RBF for each LAB and counts how many distinct
        LI pairs are flipped relative to zero_data. It fails if any LAB
        exceeds li_max_pairs (default: empirically observed max from Quartus).

        Args:
            rbf_data: candidate RBF about to be flashed
            zero_data: zero-baseline RBF
            li_max_pairs: per-LAB limit (default LI_MAX_PAIRS_PER_LAB)
            raise_on_fail: if True, raise RuntimeError on violation; otherwise
                           return the list of violators

        Returns:
            list of (lx, ly, n_pairs, pair_list) for any LAB that exceeds the
            limit. Empty list = safe.
        """
        if li_max_pairs is None:
            li_max_pairs = self.LI_MAX_PAIRS_PER_LAB

        li_entries = self.read_local_interconnect(rbf_data, zero_data)
        # Group by (lx, ly) → set of pair indices
        per_lab = {}
        for name, _off, _bp, _cands in li_entries:
            parts = name.split('_')
            lx = int(parts[1][1:])
            ly = int(parts[2][1:])
            pair = int(parts[3][1:])
            per_lab.setdefault((lx, ly), set()).add(pair)

        violations = []
        for (lx, ly), pairs in per_lab.items():
            if len(pairs) > li_max_pairs:
                violations.append((lx, ly, len(pairs), sorted(pairs)))

        if violations and raise_on_fail:
            lines = [
                f"  LAB X{lx} Y{ly}: {n} pairs active {pl} (limit {li_max_pairs})"
                for lx, ly, n, pl in sorted(violations)
            ]
            raise RuntimeError(
                "UNSAFE FOR HARDWARE: LOCAL_INTERCONNECT pair contention risk\n"
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
            patterns[bit] = set((bo, bp) for bo, bp in rows)
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
