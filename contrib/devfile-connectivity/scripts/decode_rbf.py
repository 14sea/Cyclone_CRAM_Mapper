#!/usr/bin/env python3
"""
decode_rbf.py -- UNIFIED Cyclone IV E (EP4CE6 / EP4CE10-die) .rbf bitstream decoder.

    DECODE-OR-HONESTLY-REFUSE.

This module ASSEMBLES the already-locked codecs (committed under devfile/) behind a
single interface.  It does NOT re-derive anything.  Every decoded feature traces to
real config bits; every region a codec cannot prove is reported as UNKNOWN/REFUSED,
never guessed.

--------------------------------------------------------------------------------
(a) FRAME / CRC
    EP4CE6-die uncompressed .rbf = 368011 B: 32 B preamble (0xFF*32), then
    1752 frames x 210 B.  Per frame bytes 0..207 = CRAM config, 208..209 = CRC16.
    Frames 0..24 = header/sync band (holds the IO ring + PLL header cells);
    frames 25..1751 = the 1727 CRAM data columns.  We frame the image and mask the
    per-frame CRC bytes for all diffing (rbf_lib.crc_masked_copy); we do NOT need
    the CRC polynomial to decode.

(b) BIT-ORDER FRONT END  (THE load-bearing normalization)
    The locked codecs were ALL built in ONE byte-bit order -- the order a
    Quartus-produced .rbf stores bits in, whose 9-byte header magic at offset 32 is
        0x6a f7 f7 f7 f7 f7 f7 f3 fb          ("codec/quartus convention")
    rbf_lib.py documents the OTHER convention (its declared header magic)
        0x56 ef ef ef ef ef ef cf df          ("rbf_lib-header convention")
    and 0x6a == bitreverse(0x56), 0xf7 == bitreverse(0xef), ... i.e. the two
    conventions differ by a per-byte bit reversal (byte positions unchanged).

    Empirically (this repo):
      * every Quartus-built specimen (fuzz/ce6, experiment1, phase2 c16/r24/...,
        the io/pll/m9k specimens) carries magic 0x6a  -> codec convention.
      * a vendor-shipped bin may instead carry magic 0x56 -> rbf_lib-header
        convention, and MUST be per-byte bit-reversed to be fed to the codecs
        (bitrev=True decodes cleanly; bitrev=False = garbage). The front end
        detects the convention from the magic anchor and normalizes automatically.

    So the front end NORMALIZES ONCE to the single codec convention (0x6a) and
    VERIFIES the result against the preamble+magic anchor before any codec runs.
    Because all codecs share one convention, one normalization suffices; a codec
    built in one order is never fed the other.

(c/d) DISPATCH + SAFE-REJECT
    Each codec is wrapped as a CodecRegion with a fixed CRAM frame band and its OWN
    safe-reject.  A codec only claims cells for features it can PROVE (a recorded
    routing arc, a used LUT, a used-pin field with an exact recorded codeword, a
    recorded PLL class, a grounded M9K INIT).  Anything else -> UNKNOWN.

      routing  c4/r4/r24/c16 + li + clk + direct-links   LOCKED  (C4Codec class)
      lut      atom_first physical LUT-mask cells          LOCKED  (function<->sigma partial)
      io       sram/io_codec (dir/used) + phase2/io full   LOCKED  (iostd/drive/slew partial)
      pll      phase2/pll recorded-class recognizer        PARTIAL (novel counters -> None)
      m9k INIT phase2/m9k 9x512 word-width INIT            PARTIAL
      m9k MODE width x depth                                OPEN -> reported UNKNOWN (refuse-gap)

(e) OUTPUT: structured dict (JSON-able) + human summary.
(f) INVERSE: encode(decoded, base) re-emits the exact cells of every DECODED feature
    for bit-for-bit round-trip on decoded regions (CRC-masked).

Self-test (`python3 decode_rbf.py selftest`) PROVES the bit-order front end:
  it normalizes a specimen presented in BOTH conventions to the identical internal
  image, injects+recovers one feature per codec, and round-trips decode->encode.
"""

import os
import sys
import json
import argparse
from collections import Counter, defaultdict

# ---- repo layout -----------------------------------------------------------
DEC_DIR   = os.path.dirname(os.path.abspath(__file__))
DEVFILE   = os.path.dirname(DEC_DIR)                       # devfile/
PHASE2    = os.path.join(DEVFILE, "phase2")
SRAM      = os.path.join(DEVFILE, "sram")
for p in (DEVFILE, PHASE2, SRAM,
          os.path.join(PHASE2, "r24"),
          os.path.join(PHASE2, "directlinks"),
          os.path.join(PHASE2, "pll"),
          os.path.join(PHASE2, "m9k"),
          os.path.join(PHASE2, "io")):
    if p not in sys.path:
        sys.path.insert(0, p)

import rbf_lib as R                                        # geometry + crc mask
from bitpos_to_rbf import flat_to_rbf, rbf_to_flat         # proven flat<->rbf
from cff_to_rbf import classify_first                       # T1 aux/CFF plane router
import atom_first as AF                                    # LUT-mask cells
from c4_codec import C4Codec                               # uniform routing codec
from pll_codec import PLLCodec
from m9k_codec import M9KCodec
import io_codec as IOC                                     # direction/used (locked)
from io_full_codec import IoFullCodec
from connectivity_codec import ConnectivityCodec           # node-keyed intercept layer (dynamic trace)
from static_connectivity import StaticConnectivityCodec     # whole-device DYGR route-asm table
from ioring_config_codec import IoRingConfigCodec           # R1 IO-ring/clock/global enum-dict (main_cram)

# le/lab-secondary INVERTED decode codec (harvested forward table -> decode-or-refuse).
# Hyphenated deliverable filename -> load by path.  Optional: absent table/module ->
# the decoder runs exactly as before (claims nothing).
import importlib.util as _ilu
_LLS_PATH = os.path.join(DEVFILE, "re_workflows", "out", "extract",
                         "codec_le-lab-secondary.py")
LeLabSecondaryCodec = None
if os.path.exists(_LLS_PATH):
    _spec = _ilu.spec_from_file_location("codec_le_lab_secondary", _LLS_PATH)
    _mod = _ilu.module_from_spec(_spec)
    try:
        _spec.loader.exec_module(_mod)
        LeLabSecondaryCodec = _mod.LeLabSecondaryCodec
    except Exception:
        LeLabSecondaryCodec = None

# pll-m9k-clock INVERTED decode codec (harvested forward table -> decode-or-refuse).
# Same optional-load pattern: absent module/table -> the decoder runs exactly as before.
_PMC_PATH = os.path.join(DEVFILE, "re_workflows", "out", "extract",
                         "codec_pll-m9k-clock.py")
PllM9kClockCodec = None
if os.path.exists(_PMC_PATH):
    _spec2 = _ilu.spec_from_file_location("codec_pll_m9k_clock", _PMC_PATH)
    _mod2 = _ilu.module_from_spec(_spec2)
    try:
        _spec2.loader.exec_module(_mod2)
        PllM9kClockCodec = _mod2.PllM9kClockCodec
    except Exception:
        PllM9kClockCodec = None

# ioe-reg-and-inputmux INVERTED decode codec (harvested forward table -> decode-or-refuse):
# IOE input-mux (arch 252) full device table + IOE output/OE register muxes.
# Same optional-load pattern: absent module/table -> the decoder runs exactly as before.
_IRM_PATH = os.path.join(DEVFILE, "re_workflows", "out", "extract",
                         "codec_ioe-reg-and-inputmux.py")
IoeRegInputMuxCodec = None
if os.path.exists(_IRM_PATH):
    _spec3 = _ilu.spec_from_file_location("codec_ioe_reg_inputmux", _IRM_PATH)
    _mod3 = _ilu.module_from_spec(_spec3)
    try:
        _spec3.loader.exec_module(_mod3)
        IoeRegInputMuxCodec = _mod3.IoeRegInputMuxCodec
    except Exception:
        IoeRegInputMuxCodec = None

# A1 OE-SOURCE io-direction fix (replaces the slew-presence direction heuristic).
# Binds the IOE OE-source (output-buffer-enable) cell so direction = f(OE-source,
# input-buffer) instead of a slew guess.  Same optional-load pattern: absent module/
# table -> the decoder falls back to the marker-vote direction exactly as before.
_OES_PATH = os.path.join(DEVFILE, "re_workflows", "out", "finish",
                         "codec_oe_source_direction.py")
OeSourceDirection = None
if os.path.exists(_OES_PATH):
    _spec4 = _ilu.spec_from_file_location("codec_oe_source_direction", _OES_PATH)
    _mod4 = _ilu.module_from_spec(_spec4)
    try:
        _spec4.loader.exec_module(_mod4)
        OeSourceDirection = _mod4.OeSourceDirection
    except Exception:
        OeSourceDirection = None

# configpins-global-iostd INVERTED decode codec (harvested forward table -> decode-or-refuse):
# per-IOE IO_STANDARD / CURRENT_STRENGTH / SLEW_RATE / WEAK_PULL_UP config, decoded on a
# seed-invariant CORE by nearest-fingerprint with a per-group refuse threshold.
# Same optional-load pattern: absent module/table -> the decoder runs exactly as before.
_CPI_PATH = os.path.join(DEVFILE, "re_workflows", "out", "extract",
                         "codec_configpins-global-iostd.py")
ConfigPinsIostdCodec = None
if os.path.exists(_CPI_PATH):
    _spec4 = _ilu.spec_from_file_location("codec_configpins_global_iostd", _CPI_PATH)
    _mod4 = _ilu.module_from_spec(_spec4)
    try:
        _spec4.loader.exec_module(_mod4)
        ConfigPinsIostdCodec = _mod4.ConfigPinsIostdCodec
    except Exception:
        ConfigPinsIostdCodec = None

# T1 APPLY: aux/CFF plane classifier wiring.  cff_to_rbf.classify_first routes a
# DB_BIT_SETTING.first to its serializer plane (main / cff / unvm / optreg / illegal).
# The already-inverted config codecs already REFUSE their aux-plane settings (their
# flats are bit31-set -> flat_to_rbf returns None -> instance skipped).  This inventory
# (built by auxcff/build_config_aux_inventory.py from the harvest) lets the decoder emit
# a PRECISE, ownership-NEUTRAL "aux-plane deferred" diagnostic per config class: how many
# cff/optreg cells each class defers pending a SOLVED CFF offset->(F,Y,bit) permutation.
# classify_first gives plane+offset but NOT an rbf position, so NO aux cell can be owned
# until that permutation is reversed -> net-new ownable bits = 0, decode-or-refuse intact.
_AUX_INV_PATH = os.path.join(DEVFILE, "re_workflows", "out", "auxcff",
                             "config_aux_inventory.json")
CONFIG_AUX_INVENTORY = None
if os.path.exists(_AUX_INV_PATH):
    try:
        with open(_AUX_INV_PATH) as _f:
            CONFIG_AUX_INVENTORY = json.load(_f)
    except Exception:
        CONFIG_AUX_INVENTORY = None

PRE, FS, DB = R.PREAMBLE, R.FRAME_STRIDE, R.DATA_BYTES
NF, HF, RBF_SIZE = R.N_FRAMES, R.HEADER_FRAMES, R.RBF_SIZE

# per-byte bit-reverse LUT
_REV = [int(f"{x:08b}"[::-1], 2) for x in range(256)]

# 9-byte header anchors
MAGIC_CODEC     = bytes.fromhex("6af7f7f7f7f7f7f3fb")      # 0x6a -- codec convention
MAGIC_RBFLIB    = bytes.fromhex("56efefefefefefcfdf")      # 0x56 -- rbf_lib-header

# LE-site geometry (Cyclone_CRAM_Mapper fuzz/config.py, cross-checked; HW 376/376)
# W3a: EP4CE10 has 28 LAB columns = the 22 CE6-legal columns PLUS the 6 "jailbreak"
# columns {5,9,14,30,32,33} (CE6-fitter-illegal but CE10-legal, silicon-verified in
# Cyclone_CRAM_Mapper Phase 3.25; COLUMN_BASE already on the uniform 7350-B stride in
# atom_first.BLOCK_ORIGIN).  Folding the LUT-sigma close (W2, decoded=true) lifts used
# LEs 4781->5822 (+1041) on the target, all round-trip bit-exact.  See cfg_lut_sigma.md.
_LAB_X = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 21, 22, 23, 24, 25,
          26, 28, 29, 30, 31, 32, 33]
_LAB_Y = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 21]
_LE_N  = list(range(0, 32, 2))
_INVALID = ({(x, y) for x in [3, 4, 5, 6, 7, 8] for y in [12, 13, 14, 16]}
            | {(9, y) for y in [12, 13, 14, 16]}
            | {(x, 15) for x in _LAB_X})


# --------------------------------------------------------------------------- #
# geometry helpers
# --------------------------------------------------------------------------- #
def byte_bit_to_FYb(byte, bit):
    """absolute rbf byte + bit -> (F, Y, bit)."""
    rel = byte - PRE
    F, Y = divmod(rel, FS)
    return F, Y, bit


def flat_addr(flat):
    """flat CRAM index -> (byte, bit) or None (header/aux)."""
    return flat_to_rbf(flat)


def cram_cell_universe():
    """Every addressable config-data cell (byte,bit): frames 0..1751, Y 0..207.
    (Header frames 0..24 included -- they hold the IO ring + PLL header cells.)
    CRC bytes 208,209 excluded.  This is the honest coverage denominator."""
    n = 0
    for F in range(NF):
        base = PRE + F * FS
        if base + DB > RBF_SIZE:
            break
        n += DB * 8
    return n


TOTAL_CRAM_BITS = cram_cell_universe()


# --------------------------------------------------------------------------- #
# FRONT END: load, detect convention, normalize to codec convention, verify.
# --------------------------------------------------------------------------- #
class BitOrderError(Exception):
    pass


class NormalizedImage:
    """A .rbf normalized to the single codec (0x6a) convention, anchor-verified.

    .img        -- normalized bytes (codec convention), CRC bytes intact
    .masked     -- CRC-masked copy (for diffs / codec reads)
    .convention -- detected input convention label
    .reversed   -- True iff a per-byte bit-reversal was applied to normalize
    """

    def __init__(self, raw, source="<mem>"):
        self.source = source
        self.size = len(raw)
        if self.size != RBF_SIZE:
            # not fatal for framing, but flag it
            pass
        if not all(b == 0xFF for b in raw[:PRE]):
            raise BitOrderError("preamble is not 32x0xFF -- not an EP4CE6-die rbf")
        magic = bytes(raw[PRE:PRE + 9])
        if magic == MAGIC_CODEC:
            self.convention = "quartus_codec_0x6a"
            self.reversed = False
            img = bytearray(raw)
        elif magic == MAGIC_RBFLIB:
            self.convention = "rbf_lib_header_0x56"
            self.reversed = True
            img = bytearray(_REV[b] for b in raw)          # ONE normalization
        else:
            rev_magic = bytes(_REV[b] for b in magic)
            raise BitOrderError(
                f"unrecognized header magic {magic.hex()} "
                f"(rev={rev_magic.hex()}); expected 0x6a... or 0x56... -- REFUSE")
        # ANCHOR VERIFY: after normalization the magic MUST be the codec anchor.
        got = bytes(img[PRE:PRE + 9])
        if got != MAGIC_CODEC:
            raise BitOrderError(
                f"anchor check failed: normalized magic {got.hex()} != "
                f"{MAGIC_CODEC.hex()} -- refusing to feed codecs the wrong order")
        self.img = bytes(img)
        self.masked = R.crc_masked_copy(self.img)

    def bit(self, byte, bit):
        return (self.img[byte] >> bit) & 1


def load_normalized(path):
    with open(path, "rb") as f:
        return NormalizedImage(bytearray(f.read()), source=path)


# --------------------------------------------------------------------------- #
# CODEC ADAPTERS
# Each returns (features, claimed_cells, refused_note).  claimed_cells is a set of
# (byte,bit) the codec PROVED and can regenerate via encode_into().
# --------------------------------------------------------------------------- #
class RoutingCodec:
    """Wraps one C4Codec table (c4/r4/r24/c16/li/clk/direct-links). Uniform class."""

    TABLES = [
        ("c4",          os.path.join(PHASE2, "c4_codec_table_devwide.json")),
        ("r4",          os.path.join(PHASE2, "r4", "r4_codec_table_devwide.json")),
        ("r24",         os.path.join(PHASE2, "r24", "r24_codec_table_devwide.json")),
        ("c16",         os.path.join(PHASE2, "c16", "c16_codec_table.json")),
        ("li",          os.path.join(PHASE2, "li", "li_codec_table.json")),
        ("clk",         os.path.join(PHASE2, "clk", "clk_codec_table.json")),
        ("directlinks", os.path.join(PHASE2, "directlinks", "directlinks_codec_table.json")),
    ]

    def __init__(self, cls, path):
        self.cls = cls
        self.codec = C4Codec(path)

    def frame_band(self):
        fr = set()
        for n in self.codec.table["nodes"]:
            for f in n.get("_sig_cells", []):
                rb = flat_addr(f)
                if rb:
                    fr.add((rb[0] - PRE) // FS)
        return (min(fr), max(fr)) if fr else None

    def decode(self, N):
        feats, claimed = [], set()
        for dst, src, pat in self.codec.read_c4(N.img):
            cells = [(byte, bit) for _, byte, bit in pat]
            claimed.update(cells)
            feats.append({"class": self.cls, "dst": dst, "src": src,
                          "cells": [list(c) for c in cells]})
        return feats, claimed

    def encode_into(self, out, feat):
        out2 = self.codec.write_c4_pip(bytes(out), feat["dst"], feat["src"])
        out[:] = out2


class LutCodec:
    """atom_first physical LUT-mask reader/writer over enumerated CE6 LE sites.

    Reads the 16 PHYSICAL truth-table cells of each LE.  A LE is reported as a used
    LUT iff its 16-bit physical mask is non-constant (not 0x0000/0xFFFF).  The
    physical 16-bit mask traces exactly to real bits and round-trips bit-exact.
    Logical function<-signal mapping needs the atom input permutation sigma (design
    routing, not a static per-LE constant) -> reported partial (sigma unknown)."""

    def __init__(self):
        self.sites = [(x, y, n) for x in _LAB_X if x in AF.BLOCK_ORIGIN
                      for y in _LAB_Y for n in _LE_N if (x, y) not in _INVALID]

    def frame_band(self):
        return (HF, NF - 1)     # LUT masks live in the CRAM data band

    def _le_cells(self, x, y, n):
        out = []
        for pb in range(16):
            rb = flat_addr(AF.atom_first_phys(x, y, n, pb))
            out.append((pb, rb))          # rb may be None (edge)
        return out

    def decode(self, N):
        feats, claimed = [], set()
        for (x, y, n) in self.sites:
            cells = self._le_cells(x, y, n)
            if any(rb is None for _, rb in cells):
                continue
            mask = 0
            for pb, (byte, bit) in ((pb, rb) for pb, rb in cells):
                if (N.img[byte] >> bit) & 1:
                    mask |= (1 << pb)
            if mask in (0x0000, 0xFFFF):
                continue                  # unused / constant LE -> not a LUT feature
            cellset = [(rb[0], rb[1]) for _, rb in cells]
            claimed.update(cellset)
            feats.append({"site": f"X{x}Y{y}N{n}", "x": x, "y": y, "n": n,
                          "phys_mask": mask, "phys_mask_hex": f"0x{mask:04x}",
                          "cells": [list(c) for c in cellset],
                          "logical_function": None,        # needs sigma
                          "note": "physical 16-bit mask; logical map needs sigma"})
        return feats, claimed

    def encode_into(self, out, feat):
        x, y, n, mask = feat["x"], feat["y"], feat["n"], feat["phys_mask"]
        cells = self._le_cells(x, y, n)
        for pb, rb in cells:
            if rb is None:
                continue
            byte, bit = rb
            if (mask >> pb) & 1:
                out[byte] |= (1 << bit)
            else:
                out[byte] &= ~(1 << bit)


class IoCodecAdapter:
    """Direction/used (locked sram/io_codec) + full IOE config (phase2/io).
    All addressing already codec-convention; we feed the normalized image."""

    def __init__(self):
        self.full = IoFullCodec()
        self.dirtab = self.full.dirtab
        # A1: OE-source direction fix.  Optional -- absent module/table -> the marker-
        # vote direction is used unchanged (decode-or-refuse fallback).
        self.oedir = OeSourceDirection(self.full) if OeSourceDirection else None

    def frame_band(self):
        lo, hi = self.dirtab["low_band"]
        return (lo, hi)

    def _marker_cells(self, ball, kinds):
        cells = []
        for kind in kinds:
            for cell, active in self.dirtab.get(kind, {}).get(ball, []):
                F, Y, bit = cell
                cells.append(((PRE + F * FS + Y, bit), active))
        return cells

    def decode(self, N):
        feats, claimed = [], set()
        masked = N.masked
        for ball in self.dirtab["balls"]:
            r = self.full.decode_ball(masked, ball)
            if not r["used"]:
                continue
            # A1 OE-SOURCE FIX: recompute io-direction from the bound OE-source
            # (output-buffer-enable) cell + input-buffer cell instead of the slew-
            # presence marker vote.  Decode-or-refuse: a ball whose OE-source cell is
            # refused/unreadable keeps r["direction"] (the marker-vote label) unchanged.
            # The corrected label then drives BOTH which markers are claimed below and
            # the re-encode (encode_into reads feat["direction"]), so ownership and the
            # bit-exact round-trip stay consistent.
            if self.oedir is not None:
                r["direction"] = self.oedir.direction(masked, ball, r["direction"],
                                                      r["used"])
            # Claim direction/used marker cells.  These markers are scored by a
            # FRACTIONAL majority vote (io_codec.decode_ball, thresh 0.5), so an
            # individual marker cell is NOT a deterministically-owned bit: some
            # cells in the set can legitimately hold the non-`active` value in a
            # given design (e.g. an IOE cell that is also part of an unmodeled
            # drive/iostd field).  To stay misdecode-safe and round-trip-exact we
            # claim ONLY the marker cells whose actual bit equals the model's
            # `active` value -- i.e. the cells this decode positively asserts.
            # Outvoted cells are left UNKNOWN rather than force-written.
            kinds = ["used_markers"]
            if r["direction"] in ("input", "bidir"):
                kinds.append("input_markers")
            if r["direction"] in ("output", "bidir"):
                kinds.append("output_markers")
            for ((byte, bit), active) in self._marker_cells(ball, kinds):
                if ((masked[byte] >> bit) & 1) == active:
                    claimed.add((byte, bit))
            # claim full-config field cells that decoded (non-None, exact codeword)
            fields = {}
            for name, dY in (("slew_rate", self.full.bin_fields["slew_fast"]["dY"]),
                             ("bus_hold", self.full.bin_fields["bus_hold"]["dY"]),
                             ("weak_pullup", self.full.bin_fields["weak_pullup"]["dY"]),
                             ("oe_source", self.full.bin_fields["oe_source"]["dY"])):
                val = r.get(name)
                if val is not None:
                    # _field_cells -> [(abs_off, bit, is_crc)]; claim the readable
                    # (non-CRC) replicates only.  CRC replicates are masked.
                    cells = self.full._field_cells(ball, dY)
                    if cells:
                        for (off, b, is_crc) in cells:
                            if not is_crc:
                                claimed.add((off, b))
                fields[name] = val
            if r.get("iostd_codeword"):
                # _iostd_cells -> [(abs_off, bit)] (already guaranteed non-CRC,
                # single-frame by the codec's reject guard).
                cells = self.full._iostd_cells(ball)
                if cells:
                    for (off, b) in cells:
                        claimed.add((off, b))
            feats.append({"ball": ball, "direction": r["direction"], "used": True,
                          "io_standard": r["io_standard"], "drive": r["drive"],
                          "slew_rate": r["slew_rate"], "bus_hold": r["bus_hold"],
                          "weak_pullup": r["weak_pullup"], "oe_source": r["oe_source"],
                          "iostd_codeword": r["iostd_codeword"]})
        return feats, claimed

    def encode_into(self, out, feat):
        ball = feat["ball"]
        # direction/used markers
        kinds = ["used_markers"]
        if feat["direction"] in ("input", "bidir"):
            kinds.append("input_markers")
        if feat["direction"] in ("output", "bidir"):
            kinds.append("output_markers")
        for ((byte, bit), active) in self._marker_cells(ball, kinds):
            if active:
                out[byte] |= (1 << bit)
            else:
                out[byte] &= ~(1 << bit)
        # full-config fields (semantic re-encode via locked encoders)
        img = bytes(out)
        if feat["slew_rate"] is not None:
            img = self.full.encode_bin(img, ball, "slew_fast", feat["slew_rate"] == "fast")
        for name in ("bus_hold", "weak_pullup"):
            if feat[name] is not None:
                img = self.full.encode_bin(img, ball, name, feat[name])
        if feat["oe_source"] is not None:
            img = self.full.encode_bin(img, ball, "oe_source", feat["oe_source"] == "fabric")
        if feat["iostd_codeword"]:
            img = self.full.encode_iostd(img, ball, feat["iostd_codeword"])
        out[:] = bytearray(img)


class PllCodecAdapter:
    """Recorded-class PLL recognizer (phase2/pll). Recorded classes round-trip;
    a novel/absent config -> None (refuse)."""

    def __init__(self):
        self.codec = PLLCodec()

    def frame_band(self):
        fr = sorted(set(c[2] for c in self.codec.universe))
        return (min(fr), max(fr))

    def decode(self, N):
        v = self.codec.decode_verbose(N.masked)
        settings = v["decoded"]
        if settings is None:
            return [], set(), "no recorded PLL class matches (novel/absent) -> UNKNOWN"
        claimed = set()
        for i in self.codec._read_universe(N.masked):
            byte, bit, F, Y = self.codec.universe[i]
            claimed.add((byte, bit))
        feat = {"settings": settings, "aliases": v["aliases"],
                "specimen": v["specimen"],
                "n_active_universe_cells": v["n_active_universe_cells"]}
        return [feat], claimed, None

    def encode_into(self, out, feat):
        img = self.codec.apply(bytes(out), feat["settings"])
        out[:] = bytearray(img)


class M9kCodecAdapter:
    """M9K: INIT (9x512 word-width, grounded) LOCKED-partial; MODE via the localized
    PHYSICAL-ASPECT mode field (fixed).

    Width x depth MODE is decoded from 8 discriminating CRAM cells in the M9K per-column
    config band, design-INVARIANT across >=5 independent training designs per mode. The
    field encodes the block's PHYSICAL ASPECT / data-width mode, NOT logical width x
    depth: logical modes sharing a physical realization are byte-identical here, so decode
    returns the physical class (P512x16 <- {9x512,18x512,16x512,8x256,4x512}; P1024x8 <-
    {9x1024}; P256x36 <- {36x256}) plus its logical alias set, guarded by an M9K-presence
    check. Held-out re-validation: 0 misdecodes; every specimen's true logical mode is in
    its decoded class's alias set. Any signature not matching a known class, or an
    M9K-absent site, -> UNKNOWN (refuse, never guessed). This replaces the old whole-CRAM
    invariant-core, which returned None even on held-out same-mode designs. When the class
    is P512x16 (contains the grounded 9x512), INIT contents are decoded under the
    grounded 9x512 word-width (flagged; width 9 vs 18 is not CRAM-confirmable)."""

    GROUNDED_SITE = "X15_Y2_N0"

    def __init__(self):
        self.codec = M9KCodec()

    def frame_band(self):
        return tuple(self.codec.t["geometry"]["block_mode_band_frames"])

    def decode(self, N):
        full = self.codec.decode_mode_full(N.masked, self.GROUNDED_SITE)  # guarded
        feats, claimed = [], set()
        note = None
        init_ok = False
        pclass = full["physical_class"] if full else None
        if pclass == "P512x16":
            try:
                words = self.codec.read_init(N.masked, self.GROUNDED_SITE, 9, 512)
                for w, val in words.items():
                    for b in range(9):
                        if (val >> b) & 1:
                            byte, bp = self.codec.init_cell(self.GROUNDED_SITE, 9, 512, w, b)
                            claimed.add((byte, bp))
                feats.append({"site": self.GROUNDED_SITE, "width": 9, "depth": 512,
                              "init_words": {str(k): v for k, v in words.items()},
                              "mode_source": "physical-class P512x16 exact-match "
                                             "(INIT read under grounded 9x512 word-width)"})
                init_ok = True
            except Exception as e:
                note = f"INIT decode failed: {e}"
        # claim the localized mode-field cells whenever a class exact-matches
        if full is not None:
            mf = self.codec.t["mode_field"]
            for o, b in mf["presence_cells"] + mf["disc_cells"]:
                claimed.add((o, b))
        feat_summary = {
            "mode": (full["physical_class"] if full is not None else "UNKNOWN"),
            "logical_aliases": (full["logical_aliases"] if full is not None else None),
            "mode_status": ("LOCKED (localized physical-aspect field, exact-match + "
                            "presence guard)" if full is not None
                            else "no physical-aspect class matches at grounded site "
                                 "(unused / no M9K / other config) -> UNKNOWN, not guessed"),
            "mode_field_cells": (len(self.codec.t["mode_field"]["presence_cells"])
                                 + len(self.codec.t["mode_field"]["disc_cells"])),
            "init_decoded": init_ok,
        }
        if note:
            feat_summary["note"] = note
        # 'feats' carries decoded INIT words (if any); summary carries MODE=UNKNOWN
        return feats, claimed, feat_summary

    def encode_into(self, out, feat):
        words = {int(k): v for k, v in feat["init_words"].items()}
        img = self.codec.write_init(bytes(out), feat["site"],
                                    feat["width"], feat["depth"], words)
        out[:] = bytearray(img)


# --------------------------------------------------------------------------- #
# THE UNIFIED DECODER
# --------------------------------------------------------------------------- #
class Decoder:
    def __init__(self):
        self.routing = [RoutingCodec(cls, p) for cls, p in RoutingCodec.TABLES]
        self.lut = LutCodec()
        self.io = IoCodecAdapter()
        self.pll = PllCodecAdapter()
        self.m9k = M9kCodecAdapter()
        # node-keyed connectivity layer (quartus_asm intercept). Optional: if the
        # table is absent the decoder runs exactly as before (static-only).
        self.conn = ConnectivityCodec(flat_to_rbf=flat_addr)
        # WHOLE-DEVICE interior-connectivity layer (static DYGR route-asm table,
        # SB2/SC1/SC2-validated). Optional: absent table -> decoder runs unchanged.
        self.sconn = StaticConnectivityCodec(flat_to_rbf=flat_addr)
        # R1 IO-ring-config enum-dict layer (block-mux/clock/global setting-enum ->
        # named main_cram cell). Optional: absent table -> claims nothing.
        self.ioring_cfg = IoRingConfigCodec()
        # le/lab-secondary inverted decode codec (LE/LAB register mode + secondary-
        # control fields). Optional: absent module/table -> claims nothing.
        self.lelab = LeLabSecondaryCodec() if LeLabSecondaryCodec else None
        # pll-m9k-clock inverted decode codec (CRAM-resident PLL clkout-select / clock
        # block-mux). Optional: absent module/table -> claims nothing.
        self.pllclk = PllM9kClockCodec() if PllM9kClockCodec else None
        # ioe-reg-and-inputmux inverted decode codec (IOE input-mux arch252 full device
        # table + IOE output/OE register muxes). Optional: absent module/table -> claims
        # nothing.
        self.ioeim = IoeRegInputMuxCodec() if IoeRegInputMuxCodec else None
        # configpins-global-iostd inverted decode codec (per-IOE IO_STANDARD / drive /
        # slew / weak-pull-up at the harvested placements). Optional: absent -> claims
        # nothing.
        self.cpi = ConfigPinsIostdCodec() if ConfigPinsIostdCodec else None

    # ---- decode ----------------------------------------------------------- #
    def decode(self, path_or_norm):
        N = (path_or_norm if isinstance(path_or_norm, NormalizedImage)
             else load_normalized(path_or_norm))

        result = {
            "input": N.source,
            "size": N.size,
            "input_convention": N.convention,
            "normalized_convention": "quartus_codec_0x6a",
            "normalization_applied": ("per-byte bit-reverse" if N.reversed else "none"),
            "anchor_verified": True,
            "geometry": {"preamble": PRE, "frame_stride": FS, "n_frames": NF,
                         "header_frames": HF, "data_bytes": DB,
                         "total_cram_bits": TOTAL_CRAM_BITS},
            "features": {}, "regions": [], "refused": [], "coverage": {},
        }
        claimed_by_class = {}          # class -> set((byte,bit))
        all_claimed = set()

        # routing (all classes + LI + CLK + direct-links)
        routing_feats = {}
        for rc in self.routing:
            feats, claimed = rc.decode(N)
            routing_feats[rc.cls] = feats
            claimed_by_class[f"routing.{rc.cls}"] = claimed
            all_claimed |= claimed
            result["regions"].append(
                {"codec": f"routing.{rc.cls}", "status": "LOCKED",
                 "frame_band": rc.frame_band(),
                 "n_features": len(feats), "n_cells": len(claimed)})
        result["features"]["routing"] = routing_feats

        # LUT
        lfeats, lclaimed = self.lut.decode(N)
        claimed_by_class["lut"] = lclaimed
        all_claimed |= lclaimed
        result["features"]["lut"] = lfeats
        result["regions"].append(
            {"codec": "lut", "status": "LOCKED (physical mask; logical=sigma partial)",
             "frame_band": self.lut.frame_band(),
             "n_features": len(lfeats), "n_cells": len(lclaimed)})

        # IO
        iofeats, ioclaimed = self.io.decode(N)
        claimed_by_class["io"] = ioclaimed
        all_claimed |= ioclaimed
        result["features"]["io"] = iofeats
        result["regions"].append(
            {"codec": "io", "status": "LOCKED (dir/used/buffer); iostd/drive/slew partial",
             "frame_band": self.io.frame_band(),
             "n_features": len(iofeats), "n_cells": len(ioclaimed)})

        # PLL
        pfeats, pclaimed, pnote = self.pll.decode(N)
        claimed_by_class["pll"] = pclaimed
        all_claimed |= pclaimed
        result["features"]["pll"] = pfeats
        result["regions"].append(
            {"codec": "pll", "status": "PARTIAL (recorded classes; novel counters -> None)",
             "frame_band": self.pll.frame_band(),
             "n_features": len(pfeats), "n_cells": len(pclaimed)})
        if pnote:
            result["refused"].append({"codec": "pll", "reason": pnote,
                                       "frame_band": self.pll.frame_band()})

        # M9K
        mfeats, mclaimed, msummary = self.m9k.decode(N)
        claimed_by_class["m9k"] = mclaimed
        all_claimed |= mclaimed
        result["features"]["m9k"] = {"init": mfeats, "mode": msummary}
        result["regions"].append(
            {"codec": "m9k.init", "status": "PARTIAL (9x512 word-width INIT)",
             "frame_band": [self.m9k.codec.t["geometry"]["init_anchor_frame"],
                            self.m9k.codec.t["geometry"]["init_anchor_frame"]],
             "n_features": len(mfeats), "n_cells": len(mclaimed)})
        if msummary["mode"] == "UNKNOWN":
            result["refused"].append(
                {"codec": "m9k.mode", "reason": msummary["mode_status"],
                 "frame_band": self.m9k.frame_band()})
        else:
            result.setdefault("decoded_extra", []).append(
                {"codec": "m9k.mode", "mode": msummary["mode"],
                 "status": msummary["mode_status"],
                 "mode_field_cells": msummary["mode_field_cells"]})

        # CONNECTIVITY (node-keyed intercept layer) -- binds arc SOURCES + LI/LEIM
        # taps the static routing codec leaves select-only/empty. Decode-or-refuse:
        # an edge is bound only if its full recorded codeword is present bit-exact.
        cfeats, cclaimed, csummary = self.conn.decode(N)
        claimed_by_class["connectivity"] = cclaimed
        all_claimed |= cclaimed
        nets = ConnectivityCodec.assemble_nets(cfeats)
        result["features"]["connectivity"] = {"bound_edges": cfeats, "nets": nets}
        result["regions"].append(
            {"codec": "connectivity", "status": csummary["status"],
             "frame_band": None,
             "n_features": len(cfeats), "n_cells": len(cclaimed)})
        result["connectivity_summary"] = dict(csummary, n_nets=nets["n_nets"],
                                              n_lut_input_taps=nets["n_lut_input_taps"])
        if csummary.get("arcs_source_bound", 0) == 0 and csummary["status"].startswith("LOCKED"):
            result["refused"].append(
                {"codec": "connectivity",
                 "reason": "no recorded intercept arc's full codeword is present in "
                           "this image (table covers specimenA/B muxes; this design "
                           "exercises different muxes) -> 0 edges bound, none guessed"})

        # WHOLE-DEVICE INTERIOR CONNECTIVITY (static DYGR route-asm table) --
        # binds arc SOURCES device-wide + the LOCAL_INTERCONNECT/LI wall taps the
        # static routing codec leaves select-only. Decode-or-refuse per dest mux.
        sfeats, sclaimed, ssummary = self.sconn.decode(N)
        claimed_by_class["static_connectivity"] = sclaimed
        all_claimed |= sclaimed
        snets = StaticConnectivityCodec.assemble_nets(sfeats)
        result["features"]["static_connectivity"] = {
            "bound_arcs": sfeats, "nets": snets}
        result["regions"].append(
            {"codec": "static_connectivity", "status": ssummary["status"],
             "frame_band": None,
             "n_features": len(sfeats), "n_cells": len(sclaimed)})
        result["static_connectivity_summary"] = dict(ssummary, nets=snets)
        if ssummary.get("arcs_source_bound", 0) == 0 and ssummary["status"].startswith("LOCKED"):
            result["refused"].append(
                {"codec": "static_connectivity",
                 "reason": "no enumerated dest mux resolves to a single arc in this "
                           "image (all muxes UNUSED or source out-of-band) -> 0 arcs "
                           "bound, none guessed"})

        # IO-RING CONFIG enum-dict (R1) -- names block-mux/clock/global main_cram
        # setting cells. Decode-or-refuse: only the oracle-validated addresses are
        # claimed; the PGMIO CFF regions (0xa0/0x88/0xff) are REFUSED.
        icfeats, icclaimed, icsummary = self.ioring_cfg.decode(N)
        claimed_by_class["ioring_config"] = icclaimed
        all_claimed |= icclaimed
        result["features"]["ioring_config"] = icfeats
        result["regions"].append(
            {"codec": "ioring_config", "status": icsummary["status"],
             "frame_band": None,
             "n_features": len(icfeats), "n_cells": len(icclaimed)})
        result["ioring_config_summary"] = icsummary
        if icsummary.get("named_cells", 0) == 0:
            result["refused"].append(
                {"codec": "ioring_config",
                 "reason": "no IO-ring enum-dict table present -> 0 cells named"})
        else:
            result["refused"].append(
                {"codec": "ioring_config.cff",
                 "reason": "PGMIO CFF regions 0xa0 (io-config) / 0x88 (clock-pll) / "
                           "0xff (global-option, sentinel addrs -3/-5) not serialized "
                           "to frame-CRAM -> refused; 0xa0 IO semantics owned by io codec",
                 "frame_band": None})

        # LE/LAB SECONDARY-CONTROL + MODE (inverted forward table) -- names the
        # LE_MODE / LE&LAB register-secondary-control config fields. Decode-or-refuse:
        # an instance is claimed only if its emit-order signature matches an OBSERVED
        # codeword; unobserved signatures + aux-plane SRC/CLK muxes are REFUSED.
        if self.lelab is not None:
            llfeats, llclaimed, llsummary = self.lelab.decode(N)
            claimed_by_class["le_lab_secondary"] = llclaimed
            all_claimed |= llclaimed
            result["features"]["le_lab_secondary"] = llfeats
            result["regions"].append(
                {"codec": "le_lab_secondary", "status": llsummary["status"],
                 "frame_band": None,
                 "n_features": len(llfeats), "n_cells": len(llclaimed)})
            result["le_lab_secondary_summary"] = llsummary
            if llsummary["refused_instances"]:
                result["refused"].append(
                    {"codec": "le_lab_secondary",
                     "reason": (f"{llsummary['refused_instances']} le/lab field instances "
                                "read a signature not in the observed-codeword table "
                                "(unused block / exotic codeword) -> refused, none guessed; "
                                + llsummary["refused_note"]),
                     "frame_band": None})

        # PLL / CLOCK CRAM-resident settings (inverted forward table) -- names the
        # PLL clkout output-counter SELECT / clock block-mux config fields. Decode-or-
        # refuse: an instance is claimed only if its emit-order signature matches an
        # OBSERVED codeword AND (for the 1-bit PLL aux) a multi-bit PLL field in the same
        # block also decoded; the design-varying PLL numeric config lives in the aux/CFF
        # plane (not rbf-serialized) and is REFUSED wholesale.
        if self.pllclk is not None:
            pcfeats, pcclaimed, pcsummary = self.pllclk.decode(N)
            claimed_by_class["pll_m9k_clock"] = pcclaimed
            all_claimed |= pcclaimed
            result["features"]["pll_m9k_clock"] = pcfeats
            result["regions"].append(
                {"codec": "pll_m9k_clock", "status": pcsummary["status"],
                 "frame_band": None,
                 "n_features": len(pcfeats), "n_cells": len(pcclaimed)})
            result["pll_m9k_clock_summary"] = pcsummary
            result["refused"].append(
                {"codec": "pll_m9k_clock",
                 "reason": (f"{pcsummary['refused_instances']} pll/clock field instances "
                            "read no observed codeword (unused block / vendor PLL resides "
                            "in the aux/CFF plane) -> refused, none guessed; "
                            + pcsummary["refused_note"]),
                 "frame_band": None})

        # IOE INPUT-MUX (arch 252) full device table + IOE output/OE REGISTER muxes
        # (inverted forward table) -- names the interconnect->IOE input select
        # (source LOCAL_INTERCONNECT I-index) and the output/OE register config. Decode-
        # or-refuse: a mux is claimed only if its read signature matches an OBSERVED
        # codeword (unused/all-zero or unmatched -> refused); IOE input-register (arch
        # 231/247/248) in the 0xa0 PGMIO-CFF plane is not frame-CRAM-serialized -> REFUSED.
        if self.ioeim is not None:
            imfeats, imclaimed, imsummary = self.ioeim.decode(N)
            claimed_by_class["ioe_reg_inputmux"] = imclaimed
            all_claimed |= imclaimed
            result["features"]["ioe_reg_inputmux"] = imfeats
            result["regions"].append(
                {"codec": "ioe_reg_inputmux", "status": imsummary["status"],
                 "frame_band": None,
                 "n_features": len(imfeats), "n_cells": len(imclaimed)})
            result["ioe_reg_inputmux_summary"] = imsummary
            result["refused"].append(
                {"codec": "ioe_reg_inputmux",
                 "reason": (f"{imsummary['refused_input_muxes']} IOE-input muxes read no "
                            "observed codeword (unused/all-zero or unmatched) and "
                            f"{imsummary['refused_registers']} input-register instances "
                            "live in the 0xa0 PGMIO-CFF plane -> refused, none guessed; "
                            + imsummary["refused_note"]),
                 "frame_band": None})

        # CONFIGPINS / IOSTD (inverted forward table) -- names per-IOE IO_STANDARD /
        # CURRENT_STRENGTH / SLEW_RATE / WEAK_PULL_UP at the three harvested IOE
        # placements. Decode-or-refuse: nearest-fingerprint on a seed-invariant core with
        # a per-group refuse threshold T<minsep/2 (unique-in-radius or refuse; never a
        # guess between two settings). Default/refused scopes claim 0 cells; the
        # device-global option settings live in the 0x88/0xa0/0xff CFF planes -> REFUSED.
        if self.cpi is not None:
            cifeats, ciclaimed, cisummary = self.cpi.decode(N)
            claimed_by_class["configpins_iostd"] = ciclaimed
            all_claimed |= ciclaimed
            result["features"]["configpins_iostd"] = cifeats
            result["regions"].append(
                {"codec": "configpins_iostd", "status": cisummary["status"],
                 "frame_band": None,
                 "n_features": len(cifeats), "n_cells": len(ciclaimed)})
            result["configpins_iostd_summary"] = cisummary
            result["refused"].append(
                {"codec": "configpins_iostd",
                 "reason": (f"{cisummary['refused_scopes']} IOE scope(s) nearest-fingerprint "
                            "outside refuse radius (design uses other pads / unmodeled "
                            "combo) -> refused, none guessed; "
                            + cisummary["refused_note"]),
                 "frame_band": None})

        # AUX/CFF PLANE DEFERRED (T1 APPLY) -- ownership-NEUTRAL diagnostic.
        # For each already-inverted config class, cff_to_rbf.classify_first routes its
        # settings' flats to the serializer plane.  The aux planes (cff 0xA / unvm 0x9 /
        # optreg 0x88) and header-frame main cells have NO validated rbf position (the
        # CFF offset->(F,Y,bit) permutation is unsolved, T1 harvest), so these settings
        # stay REFUSED and contribute 0 net-new owned bits.  This surfaces exactly how
        # many cells each class defers, and asserts (self-check below) that wiring
        # cff_to_rbf added ZERO cells to any codec's claim.
        if CONFIG_AUX_INVENTORY is not None:
            defer = {}
            total_deferred = 0
            for cls, info in CONFIG_AUX_INVENTORY.get("classes", {}).items():
                n = info.get("aux_or_header_deferred_cells", 0)
                defer[cls] = {
                    "aux_or_header_deferred_cells": n,
                    "net_new_ownable_bits": info.get("net_new_ownable_bits", 0),
                    "planes": {k: v for k, v in
                               info.get("distinct_cells_by_plane", {}).items()
                               if k in ("cff", "unvm", "optreg", "main_header_or_oob",
                                        "illegal")},
                }
                total_deferred += n
            result["aux_plane_deferred"] = {
                "classifier": "cff_to_rbf.classify_first (T1 mechanism, self-test PASS)",
                "by_class": defer,
                "total_deferred_cells": total_deferred,
                "net_new_ownable_bits": 0,
                "note": ("aux/CFF plane IS serialized (into header frames 0..24) but the "
                         "CFF offset->(F,Y,bit) permutation is unsolved -> no bit-exact "
                         "rbf position -> every aux setting REFUSED, 0 net-new owned. "
                         "Unlocks additively the instant a validated CFF sweep supplies "
                         "the offset->rbf map."),
            }
            result["refused"].append(
                {"codec": "aux_cff_plane",
                 "reason": (f"{total_deferred} config-class aux/CFF cells "
                            "(le/lab SRC-CLK, PLL numeric, IOE input-regs, global option) "
                            "classified by cff_to_rbf to cff/optreg planes but the "
                            "offset->rbf permutation is unsolved -> REFUSED, 0 owned"),
                 "frame_band": [0, HF - 1]})

        # coverage + UNKNOWN
        result["coverage"] = self._coverage(claimed_by_class, all_claimed)
        result["unknown_regions"] = self._unknown_regions(all_claimed)
        result["_claimed_cells"] = all_claimed        # internal (not for JSON dump)
        return result

    # ---- coverage --------------------------------------------------------- #
    def _coverage(self, by_class, all_claimed):
        cov = {"total_cram_bits": TOTAL_CRAM_BITS,
               "decoded_bits": len(all_claimed),
               "decoded_fraction": round(len(all_claimed) / TOTAL_CRAM_BITS, 8),
               "by_class": {}}
        for k, cells in by_class.items():
            cov["by_class"][k] = len(cells)
        return cov

    def _unknown_regions(self, all_claimed):
        """Per-frame: decoded-cell count vs UNKNOWN count. Report contiguous frame
        bands that are entirely UNKNOWN (0 decoded cells)."""
        claimed_frames = Counter()
        for (byte, bit) in all_claimed:
            F = (byte - PRE) // FS
            claimed_frames[F] += 1
        bands, start = [], None
        for F in range(NF):
            base = PRE + F * FS
            if base + DB > RBF_SIZE:
                break
            unknown = (claimed_frames.get(F, 0) == 0)
            if unknown and start is None:
                start = F
            elif not unknown and start is not None:
                bands.append([start, F - 1]); start = None
        if start is not None:
            bands.append([start, F])
        return {"fully_unknown_frame_bands": bands,
                "n_frames_with_some_decode": len(claimed_frames),
                "n_frames_total": NF}

    # ---- inverse: encode decoded features back into an rbf ---------------- #
    def encode(self, decoded, base_norm):
        """Re-emit every DECODED feature into a copy of base_norm.img (codec
        convention).  Returns bytes (codec convention).  Round-trip target: matches
        the original on all decoded cells (CRC-masked)."""
        out = bytearray(base_norm.img)
        # routing
        for rc in self.routing:
            for feat in decoded["features"]["routing"].get(rc.cls, []):
                rc.encode_into(out, feat)
        # lut
        for feat in decoded["features"]["lut"]:
            self.lut.encode_into(out, feat)
        # io
        for feat in decoded["features"]["io"]:
            self.io.encode_into(out, feat)
        # pll
        for feat in decoded["features"]["pll"]:
            self.pll.encode_into(out, feat)
        # m9k init
        for feat in decoded["features"]["m9k"]["init"]:
            self.m9k.encode_into(out, feat)
        # connectivity (bound-edge codewords)
        for feat in decoded["features"].get("connectivity", {}).get("bound_edges", []):
            self.conn.encode_into(out, feat)
        # static connectivity (bound-arc select bits)
        for feat in decoded["features"].get("static_connectivity", {}).get("bound_arcs", []):
            self.sconn.encode_into(out, feat)
        # io-ring config enum-dict (named main_cram cells)
        for feat in decoded["features"].get("ioring_config", []):
            self.ioring_cfg.encode_into(out, feat)
        # le/lab-secondary inverted decode codec (named field cells)
        if self.lelab is not None:
            for feat in decoded["features"].get("le_lab_secondary", []):
                self.lelab.encode_into(out, feat)
        # pll-m9k-clock inverted decode codec (named field cells)
        if self.pllclk is not None:
            for feat in decoded["features"].get("pll_m9k_clock", []):
                self.pllclk.encode_into(out, feat)
        # ioe-reg-and-inputmux inverted decode codec (named input-mux + register cells)
        if self.ioeim is not None:
            for feat in decoded["features"].get("ioe_reg_inputmux", []):
                self.ioeim.encode_into(out, feat)
        # configpins-global-iostd inverted decode codec (named per-IOE IO setting cells)
        if self.cpi is not None:
            for feat in decoded["features"].get("configpins_iostd", []):
                self.cpi.encode_into(out, feat)
        return bytes(out)

    def roundtrip_check(self, decoded, base_norm):
        """Bit-for-bit compare re-encoded vs original on the DECODED cells only
        (CRC-masked).  Returns (ok, n_checked, mismatches[])."""
        re_img = self.encode(decoded, base_norm)
        orig = base_norm.masked
        re_masked = R.crc_masked_copy(re_img)
        mism = []
        for (byte, bit) in sorted(decoded["_claimed_cells"]):
            if ((orig[byte] >> bit) & 1) != ((re_masked[byte] >> bit) & 1):
                mism.append([byte, bit])
        return (len(mism) == 0, len(decoded["_claimed_cells"]), mism)


# --------------------------------------------------------------------------- #
# human-readable summary
# --------------------------------------------------------------------------- #
def summarize(decoded):
    L = []
    L.append(f"# UNIFIED Cyclone IV E .rbf decode -- {decoded['input']}")
    L.append(f"size={decoded['size']}  input convention={decoded['input_convention']}"
             f"  normalized={decoded['normalized_convention']}"
             f"  (norm: {decoded['normalization_applied']}; anchor OK)")
    cov = decoded["coverage"]
    L.append(f"\n## Coverage (HONEST)")
    L.append(f"decoded config bits: {cov['decoded_bits']} / {cov['total_cram_bits']} "
             f"= {cov['decoded_fraction']*100:.4f}%")
    L.append("by codec (proven cells):")
    for k, v in sorted(cov["by_class"].items()):
        L.append(f"    {k:22s} {v}")
    L.append(f"\n## Features")
    rt = {c: len(f) for c, f in decoded["features"]["routing"].items()}
    L.append(f"routing PIPs: {rt}  (total {sum(rt.values())})")
    L.append(f"LUTs (used, physical mask): {len(decoded['features']['lut'])}")
    io_used = decoded["features"]["io"]
    dircnt = Counter(f["direction"] for f in io_used)
    L.append(f"IO used pins: {len(io_used)}  {dict(dircnt)}")
    pll = decoded["features"]["pll"]
    L.append(f"PLL: {'decoded '+str(pll[0]['settings']) if pll else 'UNKNOWN (refused)'}")
    m9k = decoded["features"]["m9k"]
    L.append(f"M9K INIT decoded sites: {len(m9k['init'])}   "
             f"M9K MODE: {m9k['mode']['mode']} ({m9k['mode']['mode_status']})")
    cs = decoded.get("connectivity_summary")
    if cs:
        L.append(f"connectivity (intercept): arcs source-bound {cs.get('arcs_source_bound')}"
                 f"/{cs.get('detectable_arcs_in_table')} recorded; "
                 f"LI/LEIM taps bound {cs.get('li_leim_taps_bound')}; "
                 f"nets assembled {cs.get('n_nets')} "
                 f"(LUT-input taps {cs.get('n_lut_input_taps')})")
    scs = decoded.get("static_connectivity_summary")
    if scs:
        nets = scs.get("nets", {})
        L.append(f"static connectivity (whole-device DYGR): arcs source-bound "
                 f"{scs.get('arcs_source_bound')} (muxes: {scs.get('muxes_unused')} unused, "
                 f"{scs.get('muxes_refused')} refused); LI/LEIM wall taps bound "
                 f"{scs.get('li_leim_taps_bound')}; router nets {nets.get('n_components')} "
                 f"(largest {nets.get('largest_components', [None])[0]}, "
                 f">=3 nodes {nets.get('n_components_ge3')}, junction nodes "
                 f"{nets.get('n_junction_nodes')}); LUT-endpoint arcs bound "
                 f"{scs.get('lut_output_src_arcs')} out / {scs.get('lut_input_dst_arcs')} in "
                 f"(both refused classes -> LUTs stay isolated)")
    lls = decoded.get("le_lab_secondary_summary")
    if lls:
        bys = lls.get("by_setting", {})
        L.append(f"le/lab-secondary (inverted): owned {lls['owned_instances']} field "
                 f"instances / {lls['owned_cells']} cells (refused {lls['refused_instances']}); "
                 f"by setting {bys}")
    L.append(f"\n## Refused / UNKNOWN")
    for r in decoded["refused"]:
        L.append(f"    REFUSE {r['codec']}: {r['reason']}  frames {r.get('frame_band')}")
    ur = decoded["unknown_regions"]
    L.append(f"fully-UNKNOWN frame bands: {len(ur['fully_unknown_frame_bands'])} bands; "
             f"{ur['n_frames_with_some_decode']}/{ur['n_frames_total']} frames have >=1 decode")
    return "\n".join(L)


def _jsonable(decoded):
    d = dict(decoded)
    d.pop("_claimed_cells", None)
    return d


# --------------------------------------------------------------------------- #
# SELF-TEST -- proves the bit-order front end + per-codec round-trip.
# --------------------------------------------------------------------------- #
def selftest():
    import copy
    print("== decode_rbf.py SELF-TEST (EP4CE6-die) ==\n")
    dec = Decoder()
    ok_all = True

    # --- pick a known compiled EP4CE6 specimen (codec convention, 0x6a) -------
    base_path = os.path.join(DEVFILE, "experiment1", "specimen_A", "out.rbf")
    Nbase = load_normalized(base_path)
    assert Nbase.convention == "quartus_codec_0x6a" and not Nbase.reversed
    print(f"[base] {base_path}\n       convention={Nbase.convention} reversed={Nbase.reversed}")

    # ================= (1) FRONT-END BIT-ORDER PROOF =========================
    # Present the SAME specimen in the OTHER convention (per-byte bit-reversed,
    # simulating an rbf_lib-header / vendor-order bin) and confirm the front end
    # normalizes BOTH to the byte-identical internal (codec) image.
    raw = R.load(base_path)
    raw56 = bytearray(_REV[b] for b in raw)                 # -> 0x56 order
    assert bytes(raw56[PRE:PRE + 9]) == MAGIC_RBFLIB, "reversal did not yield 0x56 magic"
    N56 = NormalizedImage(raw56, source="<reversed base>")
    fe1 = (N56.convention == "rbf_lib_header_0x56" and N56.reversed is True)
    fe2 = (N56.img == Nbase.img)                            # normalized identical
    print(f"\n(1) FRONT-END BIT-ORDER PROOF")
    print(f"    reversed input detected as {N56.convention} (reversed={N56.reversed}): "
          f"{'PASS' if fe1 else 'FAIL'}")
    print(f"    both conventions normalize to identical internal image: "
          f"{'PASS' if fe2 else 'FAIL'}")
    # decode invariance
    d_native = dec.decode(Nbase)
    d_rev = dec.decode(N56)
    fe3 = (d_native["_claimed_cells"] == d_rev["_claimed_cells"])
    print(f"    decode(native) == decode(reversed) claimed-cell set: "
          f"{'PASS' if fe3 else 'FAIL'}")
    # a wrong-order feed (skip normalization) must NOT anchor-verify
    fe4 = False
    try:
        NormalizedImage(bytearray(b"\x00" * RBF_SIZE))
    except BitOrderError:
        fe4 = True
    print(f"    non-anchor image REFUSED: {'PASS' if fe4 else 'FAIL'}")
    ok_all &= (fe1 and fe2 and fe3 and fe4)

    # ================= (2) PER-CODEC INJECT -> RECOVER -> ENCODE =============
    print(f"\n(2) PER-CODEC ROUND-TRIP (inject a recorded feature, recover, re-encode)")

    # 2a. routing: for every table with >=1 arc, write one arc and recover it.
    for rc in dec.routing:
        arc_node = next((n for n in rc.codec.table["nodes"] if n["arcs"]), None)
        if arc_node is None:
            print(f"    routing.{rc.cls:12s}: (no arcs) skip"); continue
        dst = arc_node["dest"]; src = arc_node["arcs"][0]["src"]
        img = rc.codec.write_c4_pip(Nbase.img, dst, src)
        got, _ = rc.codec.read_active_selection(img, dst)
        enc = rc.codec.encode(dst, src)
        # re-read enc cells
        rt = all(((img[flat_addr(f)[0]] >> flat_addr(f)[1]) & 1) for f in enc if flat_addr(f))
        good = (got == src and rt)
        ok_all &= good
        print(f"    routing.{rc.cls:12s}: {src} -> {dst}  recover={'ok' if got==src else got}"
              f"  encode-bits-set={'ok' if rt else 'FAIL'}  {'PASS' if good else 'FAIL'}")

    # 2b. LUT: write a physical mask, read it back, round-trip.
    x, y, n = 10, 10, 0
    testmask = 0xA53C
    img = bytearray(Nbase.img)
    lfeat = {"x": x, "y": y, "n": n, "phys_mask": testmask}
    dec.lut.encode_into(img, lfeat)
    Nlut = NormalizedImage(_reassemble(img))  # via helper preserving header
    # read back mask directly
    rb = [flat_addr(AF.atom_first_phys(x, y, n, pb)) for pb in range(16)]
    got_mask = 0
    for pb, r in enumerate(rb):
        if r and (img[r[0]] >> r[1]) & 1:
            got_mask |= (1 << pb)
    good = (got_mask == testmask)
    ok_all &= good
    print(f"    lut X{x}Y{y}N{n}      : wrote 0x{testmask:04x} read 0x{got_mask:04x}  "
          f"{'PASS' if good else 'FAIL'}")

    # 2c. IO full: encode a bin field + iostd on an anchored ball; recover.
    ball = next((b for b in dec.io.dirtab["balls"]
                 if b in dec.io.full.anchors
                 and dec.io.full._field_cells(b, dec.io.full.bin_fields["bus_hold"]["dY"])), None)
    if ball:
        img = dec.io.full.encode_bin(Nbase.img, ball, "bus_hold", True)
        got = dec.io.full._read_bin(R.crc_masked_copy(img), ball, "bus_hold")
        good = (got is True)
        ok_all &= good
        print(f"    io {ball:6s}         : bus_hold set->read {got}  {'PASS' if good else 'FAIL'}")
        # iostd
        lbl = next(iter(dec.io.full.codewords))
        if dec.io.full._iostd_cells(ball):
            img = dec.io.full.encode_iostd(Nbase.img, ball, lbl)
            got = dec.io.full.decode_iostd(R.crc_masked_copy(img), ball)
            good = (got == lbl)
            ok_all &= good
            print(f"    io {ball:6s}         : iostd {lbl} -> read {got}  {'PASS' if good else 'FAIL'}")
    else:
        print("    io: no anchored ball with a decodable field -- skip")

    # 2d. PLL: apply a recorded class, decode it back.
    rec = dec.pll.codec.records[0]
    img = dec.pll.codec.apply(Nbase.img, rec["settings"])
    got = dec.pll.codec.decode(R.crc_masked_copy(img))
    good = (got is not None and dec.pll.codec.same_config(got, rec["settings"]))
    ok_all &= good
    print(f"    pll               : apply {rec['specimen']} -> decode "
          f"{'match' if good else got}  {'PASS' if good else 'FAIL'}")

    # 2e. M9K: force 9x512 mode core + INIT contents, recover both.
    m = dec.m9k.codec
    img = m.write_mode(Nbase.img, "9x512_SP")
    contents = {0: 0x1A5, 1: 0x0FF, 7: 0x03C, 100: 0x155, 511: 0x1FE}
    img = m.write_init(img, "X15_Y2_N0", 9, 512, contents)
    imgm = R.crc_masked_copy(img)
    mode = m.decode_mode(imgm, site="X15_Y2_N0")
    words = m.read_init(imgm, "X15_Y2_N0", 9, 512, nwords=512)
    good = (mode == m.physical_class_of("9x512_SP") and all(words.get(k) == v for k, v in contents.items()))
    ok_all &= good
    print(f"    m9k               : mode-core->{mode}  INIT recover="
          f"{'ok' if all(words.get(k)==v for k,v in contents.items()) else words}  "
          f"{'PASS' if good else 'FAIL'}")

    # 2f. PLL/CLOCK inverted codec: inject every harvested field signature into the
    #     base image at its device cells, decode-or-refuse, and confirm each instance is
    #     owned + bit-exact (positive control that the inversion decodes, not only refuses).
    if dec.pllclk is not None and dec.pllclk._inst:
        img = bytearray(Nbase.img)
        for skey, sd, cells in dec.pllclk._inst:
            sig = next(iter(sd["decode"]))                 # the harvested signature
            for (b, bit), v in zip(cells, [int(c) for c in sig]):
                if v:
                    img[b] |= (1 << bit)
                else:
                    img[b] &= ~(1 << bit)
        Npc = NormalizedImage(_reassemble(img))
        pcf, pcc, pcs = dec.pllclk.decode(Npc)
        # every harvested instance should now decode to its own codeword
        want = len(dec.pllclk._inst)
        got_ok = (len(pcf) == want)
        # re-encode + read back
        out = bytearray(Npc.img)
        for f in pcf:
            dec.pllclk.encode_into(out, f)
        rt = all(((out[b] >> bit) & 1) == v
                 for f in pcf for (b, bit), v in zip(f["cells"], f["values"]))
        good = got_ok and rt
        ok_all &= good
        print(f"    pll_m9k_clock     : inject {want} harvested fields -> owned "
              f"{len(pcf)}/{want}, round-trip {'ok' if rt else 'FAIL'}  "
              f"{'PASS' if good else 'FAIL'}")

    # ================= (3) FULL DECODE -> RE-ENCODE -> MATCH =================
    print(f"\n(3) FULL decode -> encode round-trip on DECODED regions (CRC-masked)")
    # Build a specimen that actually exercises multiple codecs, then prove the
    # unified decode->encode reproduces every decoded cell bit-for-bit.
    inj = bytearray(Nbase.img)
    # inject one routing arc per class
    for rc in dec.routing:
        node = next((n for n in rc.codec.table["nodes"] if n["arcs"]), None)
        if node:
            inj[:] = bytearray(rc.codec.write_c4_pip(bytes(inj),
                                                     node["dest"], node["arcs"][0]["src"]))
    # inject a LUT
    dec.lut.encode_into(inj, {"x": 11, "y": 8, "n": 4, "phys_mask": 0x6C9A})
    # inject PLL + M9K
    inj[:] = bytearray(dec.pll.codec.apply(bytes(inj), dec.pll.codec.records[0]["settings"]))
    inj[:] = bytearray(dec.m9k.codec.write_mode(bytes(inj), "9x512_SP"))
    inj[:] = bytearray(dec.m9k.codec.write_init(bytes(inj), "X15_Y2_N0", 9, 512,
                                                {0: 0x1FF, 5: 0x0AA}))
    Ninj = NormalizedImage(_reassemble(inj))
    dfull = dec.decode(Ninj)
    ok, nchecked, mism = dec.roundtrip_check(dfull, Ninj)
    print(f"    decoded {dfull['coverage']['decoded_bits']} cells; "
          f"round-trip checked {nchecked}; mismatches={len(mism)}  "
          f"{'PASS' if ok else 'FAIL'}")
    if mism[:5]:
        print(f"      first mismatches: {mism[:5]}")
    ok_all &= ok

    # also prove round-trip is convention-agnostic: same via reversed input
    Ninj56 = NormalizedImage(bytearray(_REV[b] for b in _reassemble(inj)))
    dfull56 = dec.decode(Ninj56)
    ok2, _, mism2 = dec.roundtrip_check(dfull56, Ninj56)
    same = (dfull["_claimed_cells"] == dfull56["_claimed_cells"])
    print(f"    same design via 0x56 input: round-trip {'PASS' if ok2 else 'FAIL'}, "
          f"identical decode {'PASS' if same else 'FAIL'}")
    ok_all &= (ok2 and same)

    print(f"\nRESULT: {'ALL SELF-TESTS PASS' if ok_all else 'FAILURE'}")
    return ok_all


def _reassemble(img_bytes):
    """Return a bytearray that NormalizedImage will accept (preamble+anchor intact).
    img_bytes is already codec-convention; just ensure it's a bytearray copy."""
    return bytearray(img_bytes)


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Unified Cyclone IV E .rbf decoder")
    sub = ap.add_subparsers(dest="cmd")
    p_dec = sub.add_parser("decode")
    p_dec.add_argument("rbf")
    p_dec.add_argument("--json", help="write structured JSON here")
    p_dec.add_argument("--md", help="write human summary here")
    sub.add_parser("selftest")
    args = ap.parse_args()

    if args.cmd == "selftest" or args.cmd is None:
        sys.exit(0 if selftest() else 1)
    if args.cmd == "decode":
        dec = Decoder()
        N = load_normalized(args.rbf)
        d = dec.decode(N)
        # round-trip on the very same bin (self-consistency of decoded regions)
        ok, nchk, mism = dec.roundtrip_check(d, N)
        d["roundtrip"] = {"ok": ok, "n_cells_checked": nchk, "n_mismatch": len(mism)}
        summary = summarize(d)
        print(summary)
        print(f"\nround-trip on decoded regions: ok={ok} "
              f"checked={nchk} mismatch={len(mism)}")
        if args.json:
            with open(args.json, "w") as f:
                json.dump(_jsonable(d), f, indent=1)
            print(f"[wrote {args.json}]")
        if args.md:
            with open(args.md, "w") as f:
                f.write(summary + "\n")
            print(f"[wrote {args.md}]")


if __name__ == "__main__":
    main()
