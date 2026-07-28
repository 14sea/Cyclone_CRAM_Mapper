#!/usr/bin/env python3
"""
Companion to bitpos_to_rbf.py — the AUX/CFF plane.

T1 finding (2026-07-28, re_workflows/out/auxcff): the aux/CFF plane is NOT
"absent from the .rbf". It IS serialized — into the 25 LEADING frames (F 0..24)
that bitpos_to_rbf.flat_to_rbf deliberately excludes (`if F < HEADER_FRAMES: None`).

ROUTING (proven, libcomp_asmcc.so ASM_BITFIELD::set_bits @0x1b5a0, exact decompile):
Every DB_BIT_SETTING.first with bit31 set is a region-tagged virtual address, routed
to a SEPARATE in-RAM bitmap (not the main CRAM image at get_base_address):

    (first & 0xC0000000)==0xC0000000  -> DB_ILLEGAL_* virtual addr; NOT written anywhere
    (first & 0xA0000000)==0xA0000000  -> CFF   plane; offset = first & 0x5FFFFFFF
    (first & 0x90000000)==0x90000000  -> UNVM  plane; offset = first & 0x6FFFFFFF
    (first & 0x88000000)==0x88000000  -> Option Register; offset = first & 0x77FFFFFF
    else (bit31 clear)                -> main CRAM image (bitpos_to_rbf handles this)

For each plane, byte = offset>>3, bit = 1<<(offset&7), written to that plane's byte
array (CFF = get_cff_base_address, UNVM = get_unvm_base_address, OptReg =
get_option_reg_base_address + shadow). These byte arrays are then serialized by the
PGMIO scribe into the .rbf leading (header) frames.

EMPIRICAL SERIALIZATION EVIDENCE (differential compiles, EP4CE10 uncompressed .rbf,
re_workflows/out/auxcff):
  * pll_a(m4) vs pll_c(m8): 92 differing bits — 86 in header frames {0,5,6,7,8},
    6 in frame-CRC bytes, ZERO in the data region (F 25..1751). i.e. the entire
    PLL-multiply (CFF) delta lands in header frames.
  * clk carrier delta -> header frames {0,9,12,13,14,16}; M9K -> frame {0};
    base->pll -> frames {0,4..12}. General across PLL / clk / M9K / LE-LAB aux.

MAGNITUDE (honest): the WHOLE vendor header region (F 0..24, Y 0..207) holds only
5,918 set(=1) bits = 3.3% of the 179,174 programmed-bit gate denominator. Of those,
only ~125 land on positions that an 8-carrier PLL/M9K/clk corpus varies; the rest are
fixed config-header framing (idcode/options/CRC/USER signature) plus block-CFF bits the
corpus never exercised. This REFUTES the wf14 EXTRACT_VERDICT estimate that aux/CFF is
"~75k bits, the dominant lever": the dominant unowned mass (~109k) is DATA-region
routing, not aux/CFF. aux/CFF is a real but minor (~3.3pp ceiling) lever.

WHAT IS NOT YET SOLVED (so this module does NOT expose a bit map — decode-or-refuse):
the CFF-offset -> (header F,Y,bit) permutation. The plane is a device-file-driven
scramble, not a closed-form geometry we have derived. Solving it needs a DIVERSE
walking-ones CFF sweep (many orthogonal compiles, or a gdb direct-write of each CFF
offset); the available 8 carriers are mutually too correlated (54 CFF offsets share one
across-carrier signature -> 0 unique correlation solves). Until that sweep exists, aux
cells remain REFUSED — reproduced by no fabricated map.
"""

# region tags on DB_BIT_SETTING.first (bit31 set == region-tagged virtual address)
CFF_TAG      = 0xA0000000; CFF_MASK      = 0x5FFFFFFF
UNVM_TAG     = 0x90000000; UNVM_MASK     = 0x6FFFFFFF
OPTREG_TAG   = 0x88000000; OPTREG_MASK   = 0x77FFFFFF
ILLEGAL_TAG  = 0xC0000000

# header frames that carry the serialized aux planes (empirically F 0..24; the region
# bitpos_to_rbf.flat_to_rbf returns None for). block classes observed:
#   frame 0        : shared option / framing + M9K
#   frames 4..12   : PLL block
#   frames 9..16   : clkctrl / global-clock
AUX_HEADER_FRAMES = range(0, 25)


def classify_first(first):
    """Return (plane, offset) for a DB_BIT_SETTING.first, or ('main', first) if it is
    an ordinary CRAM flat index (bit31 clear)."""
    u = first & 0xFFFFFFFF
    if u < 0x80000000:
        return ("main", u)
    if (u & 0xC0000000) == 0xC0000000:
        return ("illegal", u)          # DB_ILLEGAL_* — never serialized
    if (u & 0xA0000000) == 0xA0000000:
        return ("cff",   u & CFF_MASK)
    if (u & 0x90000000) == 0x90000000:
        return ("unvm",  u & UNVM_MASK)
    if (u & 0x88000000) == 0x88000000:
        return ("optreg", u & OPTREG_MASK)
    return ("unknown", u)


if __name__ == "__main__":
    tests = [
        (0xA00004AB, ("cff", 0x4AB)),
        (0xA00017F1, ("cff", 0x17F1)),   # PLL clk0_multiply cell (offset 6129)
        (0xFFFFFFFD, ("illegal", 0xFFFFFFFD)),
        (1614373,    ("main", 1614373)),  # HW-verified LUT cell
    ]
    ok = True
    for f, exp in tests:
        got = classify_first(f)
        ok &= got == exp
        print(f"0x{f:08x} -> {got}  {'OK' if got==exp else 'FAIL expect '+str(exp)}")
    print("ALL PASS" if ok else "FAILURE")
