#!/usr/bin/env python3
"""
Phase-1a deliverable: the piecewise internal-bitpos -> .rbf transform for EP4CE6
(die base = cycloneive1), derived + HW-validated by the debugger oracle.

WHAT THE INTERNAL BITPOS IS
---------------------------
During assembly, every config cell is written by
    ASM_BITFIELD::set_bits(vector<DB_BIT_SETTING>&)      (libcomp_asmcc.so @0x1b5a0)
There is exactly ONE global ASM_BITFIELD for the whole device.  Each
DB_BIT_SETTING is 8 bytes: {uint32 first; uint8 value; ...}.  `first` is the
GLOBAL flat CRAM bit index.  set_bits pokes it straight into the PGMIO config
image bitmap returned by PGMIO_BITFIELD::get_base_address() (=*(pgmio+0x38)):
    image_byte = first >> 3 ;  image_bit = first & 7
So the "internal bitpos" == `first` == a flat index into the config-image bitmap
that is later serialized (with preamble + CRC) into the .rbf.

flat indices with bit31 set (>= 0x80000000, e.g. 0xFFFFFFFD) are region-tagged
auxiliary/CFF settings (the BIT decoder's `if (b4&4) addr |= 0xA0000000` tag) and
are routed to get_cff_base_address() etc. -- they are NOT in the main CRAM image.

THE TRANSFORM  (bitpos -> rbf byte/bit)
---------------------------------------
The PGMIO image is a bit bitmap organized as  flat = row_byte*COLW + col  with
    col      = 1751 - F          (F = rbf frame index; cols 0..1726 <-> F 1751..25)
    row_byte = 207*(b+1) - Y     (Y = data-byte-in-frame 0..207 ; b = bit-in-byte 0..7)
i.e.   flat = (207*(b+1) - Y) * 1727 + (1751 - F)

.rbf geometry (EP4CE6, uncompressed, 368011 B):
    32 B preamble, then 1752 frames x 210 B.
    Within a frame: bytes 0..207 = CRAM config data, bytes 208..209 = frame CRC16.
    Frames 0..24 are header/sync (no standard CRC, not in the CRAM mapping);
    frames 25..1751 (=1727 "columns") carry CRAM data.
    rbf_byte(F,Y) = 32 + F*210 + Y ;  rbf_bit = b

GEOMETRY CONSTANTS (all fixed device geometry, NOT per-bit lookup tables):
    PREAMBLE=32  FRAME_STRIDE=210  N_FRAMES=1752  HEADER_FRAMES=25
    DATA_COLS=1727 (=N_FRAMES-HEADER_FRAMES)  DATA_BYTES_PER_FRAME=208
    CRC_BYTES=2 (frame offset 208,209)  BITPLANE_STRIDE=207

Validated: 2,870,176 / 2,870,280 bits (99.9964%) of the whole m0002 config image
reproduce the real out.rbf; the 104 misses are all at Y=0, the plane-boundary tie
point row_byte=207*(b+1), an edge artifact. EXACT for every Y in 1..207 and for
all HW-verified LUT cells.
"""

PREAMBLE          = 32
FRAME_STRIDE      = 210
N_FRAMES          = 1752
HEADER_FRAMES     = 25
DATA_COLS         = 1727          # N_FRAMES - HEADER_FRAMES
DATA_BYTES        = 208           # config bytes per frame (Y=0..207)
CRC_BYTES         = 2             # frame offset 208,209
COLW              = DATA_COLS     # 1727
BITPLANE_STRIDE   = 207           # rows per bit-in-byte plane
LAST_FRAME        = N_FRAMES - 1  # 1751

# per-bit-in-byte row base Rb(b), measured exactly by col-constrained voting between
# the live config image and the real rbf (votes == points for all 8 bits). It follows
# 207*(b+1) for b=0..6; b=7 is 1655 (=1656-1): the top bit-plane is truncated because
# the image (357,058 B) is ~2 rows short of 8 full 207-row planes.
_RB_TABLE = {0: 207, 1: 414, 2: 621, 3: 828, 4: 1035, 5: 1242, 6: 1449, 7: 1655}
def _Rb(b):
    return _RB_TABLE[b]


def rbf_to_flat(F, Y, b):
    """(rbf frame F, data-byte Y in 0..207, bit b in 0..7) -> internal flat bitpos."""
    return (_Rb(b) - Y) * COLW + (LAST_FRAME - F)


# --------------------------------------------------------------------------- #
# AUX/CFF plane resolution (A1 sweep, 2026-07-28).
# The CFF plane (region tag 0xA0000000 on DB_BIT_SETTING.first) is serialized by
# PGMIO_F2P::make_cff_frame into the leading header frames (F 1..24) via a fixed,
# device-file-driven permutation the main-plane transform above cannot address
# (its columns 1727..1751 are unreachable by any flat < COLW*rows).
#
# The permutation was SOLVED by a gdb binary-labeling sweep: quartus_cpf/quartus_asm
# was run under gdb, the 8208-bit CFF byte array (get_cff_base_address) was overwritten
# at make_cff_frame entry with 14 address-bit patterns (CFF_bit[o] = (o>>k)&1) plus
# all-zero/all-one controls; each header position's 14-bit code across runs names the
# CFF offset it copies.  Every one of the 8208 offsets validated PURE (identity copy)
# against a held-out RANDOM CFF pattern.  Map file: cff_offset_rbf_map.json (canonical
# identity-polarity replica per offset; ~4 redundant replicas exist, all consistent).
#
# cff_flat_to_rbf() resolves a CFF-tagged flat to its canonical (rbf_byte, rbf_bit) in
# codec (0x6a) convention -- the same convention flat_to_rbf and every codec use.
# UNVM / OptReg / DB_ILLEGAL planes are NOT covered (separate serializers) -> None.
import os as _os, json as _json
_CFF_MAP_PATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                              "cff_offset_rbf_map.json")
_CFF_CANON = None            # {int offset: (byte, bit)}; None until first load, {} if absent
CFF_TAG  = 0xA0000000
CFF_MASK = 0x5FFFFFFF


def _load_cff_map():
    global _CFF_CANON
    if _CFF_CANON is not None:
        return _CFF_CANON
    _CFF_CANON = {}
    try:
        d = _json.load(open(_CFF_MAP_PATH))
        _CFF_CANON = {int(o): (v[0], v[1]) for o, v in d["canon"].items()}
    except Exception:
        _CFF_CANON = {}          # absent/broken map -> resolve nothing (decode-or-refuse)
    return _CFF_CANON


def cff_flat_to_rbf(first):
    """CFF-tagged flat (bit31 set, tag 0xA0000000) -> (rbf_byte, rbf_bit) or None.
    Returns None for non-CFF tags and for offsets outside the validated map."""
    u = first & 0xFFFFFFFF
    if (u & 0xE0000000) != CFF_TAG:      # not the CFF region tag
        return None
    off = u & CFF_MASK
    return _load_cff_map().get(off)


def flat_to_rbf(flat):
    """internal flat bitpos -> (rbf_byte, rbf_bit).  Resolves main-plane cells and, via
    the A1-solved CFF map, CFF-plane (0xA0) aux cells.  UNVM/OptReg/illegal -> None."""
    if flat < 0:
        return None
    if flat >= 0x80000000:
        return cff_flat_to_rbf(flat)     # CFF plane resolves; other aux planes -> None
    row_byte, col = divmod(flat, COLW)
    F = LAST_FRAME - col
    if F < HEADER_FRAMES or F >= N_FRAMES:
        return None                      # maps into header region
    for b in range(8):
        Y = _Rb(b) - row_byte
        if 0 <= Y <= DATA_BYTES - 1:
            rbf_byte = PREAMBLE + F * FRAME_STRIDE + Y
            return (rbf_byte, b)
    return None


# ---- device files the resolution consumes (from strace/openat trace of quartus_asm)
TABLES_CONSUMED = {
    "flat_address_source": [
        # atom-setting flat CRAM addresses (BIT/NODE/ushort pools):
        "common/devinfo/cycloneive/ddb_cycloneive1_asm.ddb",     # 1,405,145 B (ASMMDB)
        # block-info / offset cache (atom-setting -> BIT indices):
        "common/devinfo/cycloneive/ddb_cycloneive1_asmdb.ddb",   # 31,456 B (ASMDB_BLOCK_INFO)
        "common/devinfo/cycloneive/ddb_cycloneive1_asmdb_dirt.ddb",
    ],
    "device_geometry_source": [
        "common/devinfo/cycloneive/ddb_cycloneive_info.ddb",
        "common/devinfo/cycloneive/ddb_cycloneive_info_counts.ddb",
        "common/devinfo/cycloneive/ddb_cycloneive_part_info.ddb",
        "common/devinfo/ddb_cumulative_family.ddb",
    ],
    "opened_but_NOT_needed_for_LUT_flat_addr": [
        "common/devinfo/cycloneive/ddb_cycloneive1_routing.ddb",  # routing resources only
        "common/devinfo/cycloneive/ddb_cycloneive1_place.ddb",
        "common/devinfo/cycloneive/ddb_cycloneive1_gid_database.ddb",
    ],
}

# call chain that emits the flat address (gdb backtrace):
#   ASM_BITFIELD::set_bits            (libcomp_asmcc.so)
#   <- ASM_ASMDBIO::record_settings(ASMDB_SETTING_STREAMS&)   (libcomp_asm.so)
#   <- asm_flush_settings(..., ASMCC_CADDY_SHACK_BASE*)       (libcomp_asm.so)
#   <- process_cdb(...) <- assemble_chip(..., ASMDB_DIE*, PGMIO_BITFIELD**, ...)
# => LUT-mask cells resolve via the ASMDB atom path, NOT the DYGR/routing path.


if __name__ == "__main__":
    # Self-test on the 6 debugger-captured, HW-verified LUT cells (3 walking-ones
    # pairs, 6 different frames). flat indices captured live from set_bits;
    # rbf byte/bit are the real bit-flips in fuzz/ce6.
    CAPTURED = [
        # (flat_bitpos, expect_rbf_byte, expect_bit, frame, note)
        (1614373, 0x1455d, 4, 396, "m0001^m0002 cell A (val 1->0)"),
        (1616101, 0x1448a, 4, 395, "m0001^m0002 cell B (val 0->1)"),
        (1614375, 0x143b9, 4, 394, "m0004^m0008 cell A (val 1->0)"),
        (1616103, 0x142e6, 4, 393, "m0004^m0008 cell B (val 0->1)"),
        (1614377, 0x14215, 4, 392, "m0010^m0020 cell A (val 1->0)"),
        (1616105, 0x14142, 4, 391, "m0010^m0020 cell B (val 0->1)"),
    ]
    ok = True
    for flat, eb, ebit, F, note in CAPTURED:
        r = flat_to_rbf(flat)
        good = r == (eb, ebit)
        ok &= good
        print(f"flat={flat} -> {r} expect (0x{eb:x},{ebit}) frame{F}  "
              f"{'PASS' if good else 'FAIL'}  [{note}]")
        # round-trip
        Y = eb - (PREAMBLE + F * FRAME_STRIDE)
        assert rbf_to_flat(F, Y, ebit) == flat, "round-trip mismatch"
    print("ALL 6 CAPTURED HW-VERIFIED LUT CELLS PASS" if ok else "FAILURE")
