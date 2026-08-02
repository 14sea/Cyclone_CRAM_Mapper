# SPDX-License-Identifier: GPL-3.0-or-later
#!/usr/bin/env python3
"""logic_fullfield.py -- own the CLEAR plane of the LAB/LE-secondary + LUT logic
resources as full-field KNOWN-0 masks (decode-or-refuse, no implicit-zero).

Device-general for the die `cycloneive1` (EP4CE6 == EP4CE10).

MOTIVATION
----------
The from-blank encoder writes le/lab-secondary cells only for DECODED instances (the
vendor instances whose signature matched an OBSERVED codeword). Every enumerated
instance the codec REFUSED (an unused LE reading its field empty, or an exotic
unobserved pattern) claimed ZERO cells -> its whole field footprint stayed at the
background -> the two-background write-mask (ledger.py) marked it UNWRITTEN ->
UNKNOWN_CLEAR. Those clears are the 'lab-le-secondary-off' class: the device file
fully determines them (the footprint is fixed device geometry), yet they were not
owned.

This codec closes that gap for the two LOGIC resources the fabric decoder already
models -- le/lab-secondary and LUT -- with the SAME full-field gate the routing
clear pass uses (own the complete field of an enumerated resource, but only on cells
the decode PROVES, never implicit-zero):

  le/lab-secondary instance (fixed ordered flat-cell footprint, device geometry):
      signature classified on N.masked exactly as the codec's decode() does:
        - OBSERVED codeword (DECODED)     -> set the real-1 cells, clear the real-0
              cells of the footprint (this reproduces the baseline encode_into and
              additionally owns the field's forced 0s).
        - all-zero signature (OFF)        -> clear the whole footprint: an unused
              LE/LAB, every field cell provably 0 in the real image.
        - non-zero unobserved (REFUSED)   -> clear ONLY the real-0 cells of the
              footprint (physically forced 0); REFUSE the real-1 cells (leave them
              UNWRITTEN -> they stay UNKNOWN_SET). We do NOT invent a meaning for an
              undecoded le/lab-secondary pattern -> no bluff on the SET plane, while
              its forced 0s are still owned.

  LUT (LE site, 16 physical truth-table cells, exact bijection):
      the physical mask IS the value -> own the complete field for every site
      (set the mask-1 cells, clear the mask-0 cells).

HONEST LIMIT (un-enumerated, declared not bluffed)
--------------------------------------------------
The le/lab-secondary codec is a HARVESTED-BLOCK codec, not a device-wide geometry
model: it knows only the LE/LAB secondary blocks exercised by the harvest compiles.
Device-wide an EP4CE10 has ~7,616 LE sites across 476 LABs, so the vast majority of
per-site LE_REGISTER_SECONDARY_CONTROL / LE_MODE_FIELD (and LAB granularity) field
footprints are NOT enumerated and their off-cells remain honestly UNKNOWN_CLEAR;
closing them needs the per-site field-cell geometry enumerated device-wide from the
asm/routing device file. The aux/dummy-plane le/lab SRC/CLK muxes live in the
0xA.../0xF... planes that are NOT serialized to frame CRAM -> un-ownable from a .rbf
-> refused wholesale.

SAFETY (0 INVENTED, 0 WRONG_CLEAR):
  * every SET cell written is real-1 (the physical mask / signature bit)   -> 0 INVENTED
  * every CLEAR cell written is real-0 (an off footprint, the field's forced 0s, or a
    LUT mask-0 bit)                                                        -> 0 WRONG_CLEAR
  * writes are computed from the real image and are background-independent, so the
    two-background diff marks every touched position OWNED and equal to real -> KNOWN.
  * a cell shared across footprints cannot receive contradictory writes: a real-1 cell
    only ever lands in a SET write (any resource that would clear it must have read it
    as 0, impossible); a real-0 cell only ever lands in CLEAR writes -> globally
    single-valued, verified by the two-background ledger downstream.

decode-or-refuse; commit nothing.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEV = "<repo>/devfile"                        # campaign device tree (decoder + geometry)
for p in (_HERE, os.path.join(_DEV, "decoder"), _DEV,
          os.path.join(_DEV, "re_workflows", "out", "extract")):
    if p not in sys.path:
        sys.path.insert(0, p)

import bitpos_to_rbf as B                       # proven device geometry (contrib sibling)
import atom_first as AF                         # LUT physical-cell geometry


class LogicFullFieldCodec:
    """Complete field-mask (set + provable-clear) of every enumerated le/lab-secondary
    instance and LUT site, gated decode-or-refuse on the real image."""

    def __init__(self, decoder):
        self.dec = decoder
        # ---- le/lab-secondary instances (ordered (byte,bit) cells already resolved) ----
        self._lelab = []            # (skey, sd, cells[(byte,bit)...])
        lelab = getattr(decoder, "lelab", None)
        if lelab is not None:
            for (skey, sd, cells) in lelab._inst:
                self._lelab.append((skey, sd, [tuple(c) for c in cells]))
        self._lelab_codec = lelab
        # ---- LUT sites (16 physical truth-table cells) ----
        self._lut_sites = []
        for (x, y, n) in decoder.lut.sites:
            cells = []
            ok = True
            for pb in range(16):
                rb = B.flat_to_rbf(AF.atom_first_phys(x, y, n, pb))
                if rb is None:
                    ok = False
                    break
                cells.append((pb, rb[0], rb[1]))
            if ok:
                self._lut_sites.append(cells)

    # ------------------------------------------------------------------ classify
    def _lelab_class(self, masked, sd, cells):
        """Return 'decoded' | 'off' | 'refused' for an le/lab instance signature,
        matching codec.decode()'s gate (reads N.masked, codec convention)."""
        sig = "".join(str((masked[b] >> bit) & 1) for (b, bit) in cells)
        if sd["decode"].get(sig) is not None:
            return "decoded"
        if sig.count("1") == 0:
            return "off"
        return "refused"

    # ------------------------------------------------------------------ plan
    def plan(self, N):
        """Return (set_cells, clear_cells, stats). set_cells: dict[(b,bit)]=1;
        clear_cells: set[(b,bit)]. Derived from the real image, decode-or-refuse.
        Every set cell is real-1; every clear cell is real-0."""
        img = N.img
        masked = N.masked
        set_cells = {}
        clear_cells = set()
        st = {"lelab_decoded": 0, "lelab_off": 0, "lelab_refused": 0,
              "lelab_refused_setbits_left_unknown": 0,
              "lut_off": 0, "lut_used": 0, "lut_allone": 0}

        # ---- le/lab-secondary ----
        for (skey, sd, cells) in self._lelab:
            cls = self._lelab_class(masked, sd, cells)
            if cls == "decoded":
                st["lelab_decoded"] += 1
                for (b, bit) in cells:
                    if (img[b] >> bit) & 1:
                        set_cells[(b, bit)] = 1
                    else:
                        clear_cells.add((b, bit))
            elif cls == "off":
                st["lelab_off"] += 1
                for (b, bit) in cells:                 # every cell provably 0
                    clear_cells.add((b, bit))
            else:                                       # refused non-zero: clear 0s, refuse 1s
                st["lelab_refused"] += 1
                for (b, bit) in cells:
                    if (img[b] >> bit) & 1:
                        st["lelab_refused_setbits_left_unknown"] += 1  # REFUSED, unwritten
                    else:
                        clear_cells.add((b, bit))       # forced 0, provable

        # ---- LUT (physical mask IS the value) ----
        for cells in self._lut_sites:
            mask = 0
            for (pb, b, bit) in cells:
                if (img[b] >> bit) & 1:
                    mask |= (1 << pb)
            for (pb, b, bit) in cells:
                if (mask >> pb) & 1:
                    set_cells[(b, bit)] = 1
                else:
                    clear_cells.add((b, bit))
            if mask == 0:
                st["lut_off"] += 1
            elif mask == 0xFFFF:
                st["lut_allone"] += 1
            else:
                st["lut_used"] += 1

        clear_cells -= set(set_cells.keys())            # set-wins on any real-1 overlap
        return set_cells, clear_cells, st

    # ------------------------------------------------------------------ apply
    def apply_into(self, out, plan):
        """Write the precomputed plan onto `out` (any background). Clears first,
        then sets (set-wins). Background-independent -> owned by the two-bg diff."""
        set_cells, clear_cells, _ = plan
        for (b, bit) in clear_cells:
            out[b] &= ~(1 << bit)
        for (b, bit) in set_cells:
            out[b] |= (1 << bit)
