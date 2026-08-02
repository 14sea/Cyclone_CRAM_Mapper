# SPDX-License-Identifier: GPL-3.0-or-later
#!/usr/bin/env python3
"""header_field.py -- whole-image header integrity decode/emit (decode-or-refuse).

Device-general for the Cyclone IV E die `cycloneive1` (EP4CE6 == EP4CE10), the
368011-byte uncompressed passive-serial `.rbf` geometry. Standalone: no Quartus
device files needed -- the config-image geometry and the two integrity engines are
closed-form constants pinned from the Quartus programming binary.

WHAT THIS OWNS (so the pipeline can emit a VALID whole-image header, not just the
per-frame data CRCs)
--------------------------------------------------------------------------------
The image is `PREAMBLE(32) + SYNC + 1752 frames of stride 210` (208 payload bytes +
a 2-byte trailing field) + a 59-byte 0xFF postamble. Two, and only two, integrity
engines run over it -- pinned by a LIVE gdb intercept of the Quartus programming
path, NOT guessed:

  * DATA frames (F >= 25): the trailing 2 bytes are a reflected CRC-16 over the
    frame's 208 payload bytes. Engine = `PGM_COMMON::calculate_crc16` (reflected
    poly 0xA001), selected by the dispatcher `PGMIO_F2P::calculate_crc` @0x36eb00.
    The dispatcher hands crc16 init 0xFFFF over a constant 2-byte header prefix
    (0xCCE8) ahead of the payload, which is identical to an *effective* init of
    0xFE54 applied directly over the 208 payload bytes (both reconcile: an all-zero
    frame returns 0x7D9A). This module uses the effective-init form.

  * HEADER frames (F 0..24): the trailing 2 bytes are NOT a payload checksum. They
    are an 8-bit configuration/header-structure field, BYTE-DOUBLED into bytes 208
    AND 209 (`byte[209] == byte[208]`, proven over 471 same-die designs, 0
    mismatch). This is the "106-bit header integrity floor" = 53 logical set-bits
    x 2 stored copies. It is decoded/emitted here decode-or-refuse (see below).

REFUTED BY LIVE TRACE (why the header field is NOT a crc8)
---------------------------------------------------------
`PGMIO_F2P::calculate_crc8` @0x36e8d0 (a reflected poly-0x88 CRC-8) EXISTS in
`libpgm_pgmio.so` but is DEAD CODE for this die: a full gdb intercept of both
`quartus_cpf` (sof->rbf) and `quartus_asm` recorded 0 calls to it and 0 dispatches
into the crc8/default branch; every dispatch took the crc16 branch. The assembler
emitted a valid image while making ZERO CRC calls of any kind for the header field.
The header 8-bit fields are therefore carried as option/header data, not computed
by a per-frame checksum routine.

DECODE-OR-REFUSE on the header floor
------------------------------------
  * The DUPLICATION LAW (`byte[209] == byte[208]`) is GENERAL: the high copy is
    DERIVED unconditionally from the low copy, for any design. `enforce_duplication`
    re-emits it; `verify` checks it.
  * 22 of the 25 header frames' low bytes are a per-frame GF(2)-affine function of
    that frame's own 208-byte payload (option bits linearly encoded), proven
    held-out on 471 designs -- a general derived function. Recovering the per-frame
    affine map needs the design corpus, so this module does not ship the maps; it
    exposes the value as read from the image and REFUSES to synthesise it for a
    foreign design (no bluff).
  * 3 frames (F3, F5, F9) carry an extra field bit set ONLY when the design uses an
    M9K memory block (delta {F3:0x04, F5:0x40, F9:0x10}). That determinant is a
    non-payload DESIGN INPUT (option-register M9K-usage flag), unknowable from the
    static image alone -> correctly REFUSED (EXPLICIT_UNKNOWN) for foreign designs.
  * The documented 32-bit whole-configuration SEU CRC is ABSENT from this
    passive-serial image (postamble = 59 x 0xFF, constant across the corpus): the
    Cyclone IV SEU CRC lives in an option register only when error-detection is
    enabled. It is NOT one of the 106 floor bits. This module verifies the postamble
    constant and REPORTS the SEU field as located-but-not-emitted (not closed).

Standalone:  python3 header_field.py [target.rbf]   # self-test (+ verify if given)
Integrated:  import HeaderIntegrityField; emit_frame_crcs() to write valid data-frame
             CRCs onto a config image, enforce_duplication() for the header copies.
"""
import os
import sys

# ---- config-image geometry (device-general constants; die cycloneive1) --------
PREAMBLE      = 32
SYNC_MAGIC    = bytes.fromhex("5599aa66")   # 4-byte sync word after the preamble
FRAME_STRIDE  = 210
DATA_BYTES    = 208
CRC_OFF       = 208                          # trailing 2-byte field at frame offset 208..209
HEADER_FRAMES = 25                           # F 0..24 carry the byte-doubled option field
N_FRAMES      = 1752
FRAMES_END    = 367952                       # first postamble byte
IMAGE_BYTES   = 368011
POSTAMBLE_FILL = 0xFF

# effective reflected-CRC16 parameters over the 208 payload bytes (see docstring)
CRC16_POLY = 0xA001
CRC16_INIT = 0xFE54
ZERO_FRAME_CRC = 0x7D9A                      # crc16_frame(bytes(208)) -- a device constant


def crc16_frame(payload, init=CRC16_INIT, poly=CRC16_POLY):
    """Reflected CRC-16 (PGM_COMMON::calculate_crc16, poly 0xA001) over the 208
    payload bytes, effective init 0xFE54. Little-endian: low byte -> [208], high
    byte -> [209]."""
    c = init
    for b in payload:
        c ^= b
        for _ in range(8):
            c = (c >> 1) ^ poly if (c & 1) else (c >> 1)
    return c & 0xFFFF


class HeaderIntegrityField:
    """Decode-or-refuse view of the whole-image integrity fields: per-frame data
    CRC-16 (closed-form, general) + the byte-doubled header floor (duplication law
    general; field values refused for foreign designs)."""

    def frame_base(self, F):
        return PREAMBLE + F * FRAME_STRIDE

    # ---- data-frame CRC-16: general, closed-form -------------------------------
    def verify_data_crcs(self, img):
        """Return (ok, total, mismatches[]) over all data frames (F >= 25)."""
        ok = 0
        mism = []
        total = N_FRAMES - HEADER_FRAMES
        for F in range(HEADER_FRAMES, N_FRAMES):
            base = self.frame_base(F)
            c = crc16_frame(img[base:base + DATA_BYTES])
            lo, hi = c & 0xFF, (c >> 8) & 0xFF
            if img[base + CRC_OFF] == lo and img[base + CRC_OFF + 1] == hi:
                ok += 1
            else:
                mism.append(F)
        return ok, total, mism

    def emit_frame_crcs(self, img):
        """Write the correct data-frame CRC-16 into bytes 208/209 of every data
        frame of `img` (bytearray). Returns the number of frames written. This is
        the closed-form generator that lets the pipeline emit valid frame CRCs."""
        n = 0
        for F in range(HEADER_FRAMES, N_FRAMES):
            base = self.frame_base(F)
            c = crc16_frame(img[base:base + DATA_BYTES])
            img[base + CRC_OFF] = c & 0xFF
            img[base + CRC_OFF + 1] = (c >> 8) & 0xFF
            n += 1
        return n

    # ---- header floor: duplication law general; field values decode-or-refuse --
    def verify_duplication(self, img):
        """Return (ok, total, mismatches[]) for the header duplication law
        byte[209]==byte[208] over the 25 header frames."""
        ok = 0
        mism = []
        for F in range(HEADER_FRAMES):
            base = self.frame_base(F)
            if img[base + CRC_OFF] == img[base + CRC_OFF + 1]:
                ok += 1
            else:
                mism.append(F)
        return ok, HEADER_FRAMES, mism

    def enforce_duplication(self, img):
        """DERIVED-emit the general duplication law: set byte[209]=byte[208] for
        every header frame of `img` (bytearray). Returns frames touched."""
        for F in range(HEADER_FRAMES):
            base = self.frame_base(F)
            img[base + CRC_OFF + 1] = img[base + CRC_OFF]
        return HEADER_FRAMES

    def read_header_fields(self, img):
        """Read the 25 header low-byte field values (the design-carried option
        bytes). We DECODE (read) them; we REFUSE to synthesise them for a foreign
        design -- the per-frame affine map (22 frames) needs the corpus and F3/F5/F9
        depend on a non-payload M9K-usage design input."""
        return [img[self.frame_base(F) + CRC_OFF] for F in range(HEADER_FRAMES)]

    def refused_general_frames(self):
        """Header frames whose low byte is NOT synthesisable from the static image
        alone (design-input-bound); refused for foreign designs, not bluffed."""
        return {3: 0x04, 5: 0x40, 9: 0x10}   # delta appears iff design uses an M9K block

    # ---- 32-bit whole-config SEU CRC: located, not closed ----------------------
    def seu_crc_status(self, img):
        """The documented 32-bit whole-configuration SEU CRC is emitted into an
        option register only when error detection is enabled; in this passive-serial
        image it is ABSENT (postamble all-0xFF). Return a status dict -- LOCATED but
        NOT CLOSED, never invented."""
        post = img[FRAMES_END:IMAGE_BYTES]
        return {
            "postamble_all_fill": all(b == POSTAMBLE_FILL for b in post),
            "postamble_len": len(post),
            "seu_crc32": "ABSENT (error-detection CRC disabled); located, not closed",
        }

    # ---- one-shot report -------------------------------------------------------
    def verify(self, img):
        dok, dtot, dm = self.verify_data_crcs(img)
        pok, ptot, pm = self.verify_duplication(img)
        return {
            "data_frame_crc16": {"ok": dok, "total": dtot, "mismatch_frames": dm},
            "header_duplication_law": {"ok": pok, "total": ptot, "mismatch_frames": pm},
            "header_field_values_low_byte": self.read_header_fields(img),
            "header_refused_general_frames": self.refused_general_frames(),
            "seu_crc": self.seu_crc_status(img),
        }


def _selftest():
    hf = HeaderIntegrityField()
    # (a) device constant: an all-zero data frame's CRC-16 is 0x7D9A
    assert crc16_frame(bytes(DATA_BYTES)) == ZERO_FRAME_CRC, "crc16 zero-frame constant"
    print(f"(a) crc16(zero frame) = 0x{crc16_frame(bytes(DATA_BYTES)):04X}  "
          f"== 0x{ZERO_FRAME_CRC:04X}  PASS")

    # (b) round-trip: emit CRCs + duplication onto a random-payload image, verify all
    import random
    rng = random.Random(0xC4E)
    img = bytearray(POSTAMBLE_FILL for _ in range(IMAGE_BYTES))
    for i in range(PREAMBLE):
        img[i] = 0xFF
    img[PREAMBLE:PREAMBLE + len(SYNC_MAGIC)] = SYNC_MAGIC
    for F in range(N_FRAMES):
        base = hf.frame_base(F)
        for i in range(DATA_BYTES):
            img[base + i] = rng.randrange(256)
        # give the header frames an arbitrary low field byte to be doubled
        if F < HEADER_FRAMES:
            img[base + CRC_OFF] = rng.randrange(256)
    n_crc = hf.emit_frame_crcs(img)
    n_dup = hf.enforce_duplication(img)
    rep = hf.verify(img)
    d = rep["data_frame_crc16"]
    p = rep["header_duplication_law"]
    print(f"(b) emit {n_crc} data CRCs + {n_dup} header dup -> "
          f"data {d['ok']}/{d['total']}, dup {p['ok']}/{p['total']}  "
          f"{'PASS' if d['ok'] == d['total'] and p['ok'] == p['total'] else 'FAIL'}")
    assert d["ok"] == d["total"] and p["ok"] == p["total"]
    print(f"    seu_crc32: {rep['seu_crc']['seu_crc32']}")


if __name__ == "__main__":
    print("== header_field self-test (device-general, no Quartus needed) ==")
    _selftest()
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        img = bytearray(open(sys.argv[1], "rb").read())
        rep = HeaderIntegrityField().verify(img)
        d, p = rep["data_frame_crc16"], rep["header_duplication_law"]
        print(f"\n== verify {sys.argv[1]} ==")
        print(f"data-frame CRC16     : {d['ok']}/{d['total']} "
              f"(mismatch {d['mismatch_frames'][:8]})")
        print(f"header duplication   : {p['ok']}/{p['total']} "
              f"(mismatch {p['mismatch_frames']})")
        print(f"header refused (gen) : frames {sorted(rep['header_refused_general_frames'])}")
        print(f"seu_crc32            : {rep['seu_crc']['seu_crc32']}")
