# CFF / flat-offset → .rbf serialization map and method

Device-general (die `cycloneive1`, EP4CE6 == EP4CE10, 368011-B uncompressed
`.rbf`). Code: `scripts/bitpos_to_rbf.py` (main CRAM plane),
`scripts/cff_to_rbf.py` (aux/CFF planes). Data: `results/cff_offset_rbf_map.json`.

## The internal bit position

During assembly every config cell is written by
`ASM_BITFIELD::set_bits(vector<DB_BIT_SETTING>)` (`libcomp_asmcc.so` @0x1b5a0).
There is exactly one global `ASM_BITFIELD` for the whole device; each
`DB_BIT_SETTING.first` is the **global flat CRAM bit index**. `set_bits` pokes it
straight into the PGMIO config-image bitmap, so the "internal bitpos" is a flat
index into the image that is later serialized (preamble + per-frame CRC) into the
`.rbf`. Flat indices with bit31 set are region-tagged aux settings, routed to
separate planes (below), not the main CRAM image.

## Main-plane transform (closed form, no per-bit table)

The PGMIO image is a bit bitmap organized as `flat = row_byte*COLW + col`, which
inverts to fixed device geometry:

```
col      = 1751 - F          (F = rbf frame index; data cols F 25..1751)
row_byte = 207*(b+1) - Y     (Y = data-byte-in-frame 0..207 ; b = bit-in-byte 0..7)
flat     = (207*(b+1) - Y) * 1727 + (1751 - F)
rbf_byte(F,Y) = 32 + F*210 + Y ;  rbf_bit = b

PREAMBLE=32  FRAME_STRIDE=210  N_FRAMES=1752  HEADER_FRAMES=25
DATA_COLS=1727  DATA_BYTES_PER_FRAME=208  CRC_BYTES=2  BITPLANE_STRIDE=207
```

These are fixed geometry constants, not lookups. Validated: 99.9964% of a whole
config image reproduces the real `.rbf` (the 104 misses are all at the `Y=0`
plane-boundary tie point); exact for every `Y` in 1..207 and for all HW-verified
LUT cells. Method of derivation: a gdb log-space sweep of
`PGMIO_F2P::make_cff_frame` (`libpgm_pgmio.so` @0x387f00), inverted to the closed
form above and wired in `bitpos_to_rbf.py`.

## Aux-plane routing (proven, exact decompile)

Every `DB_BIT_SETTING.first` with bit31 set is a region-tagged virtual address
routed to a separate in-RAM bitmap, then serialized into the **leading** frames
(F 0..24) that the main transform deliberately excludes:

```
(first & 0xC0000000)==0xC0000000 -> DB_ILLEGAL_* ; NOT written anywhere
(first & 0xA0000000)==0xA0000000 -> CFF   plane ; offset = first & 0x5FFFFFFF
(first & 0x90000000)==0x90000000 -> UNVM  plane ; offset = first & 0x6FFFFFFF
(first & 0x88000000)==0x88000000 -> Option Register ; offset = first & 0x77FFFFFF
else (bit31 clear)               -> main CRAM image (closed form above)
```

Empirical serialization evidence (differential compiles, uncompressed `.rbf`):
the entire PLL-multiply (CFF) delta between two PLL carriers lands in header
frames `{0,5,6,7,8}` with zero bits in the data region; clk / M9K / LE-LAB aux
deltas likewise land in header frames only. So the aux/CFF plane **is** in the
`.rbf`, in the header band — not absent.

## Honest open gap (decode-or-refuse)

The CFF-offset → (header F, Y, bit) **permutation** is a device-file-driven
scramble we have not reduced to closed form; `cff_offset_rbf_map.json` records
the partial map recovered so far. Until a diverse walking-ones CFF sweep resolves
the full permutation, `cff_to_rbf.py` exposes no complete aux bit map and
**refuses** rather than guess. The aux/CFF band is a real but minor lever (the
whole vendor header region F 0..24 holds only ~3.3% of programmed bits); the
dominant unowned mass is data-region routing, not aux/CFF.
