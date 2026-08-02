# SPDX-License-Identifier: GPL-3.0-or-later
#!/usr/bin/env python3
"""io_fullfield.py -- own the CLEAR plane of the IOE / PLL / global-clock codecs by
writing their COMPLETE field mask (decoded 1s AND the 0s the decode forces),
converting the 'ioe-config-off', 'cfgres-global-pll-off' and (grounded)
'm9k-unused-block-off' UNKNOWN_CLEAR positions to KNOWN-0.

Device-general for the die `cycloneive1` (EP4CE6 == EP4CE10).

MOTIVATION
----------
The unified from-blank encoder applies each IOE / PLL codec's ACTIVE decoded features
only (encode_into writes the decoded value's cells). Every field cell an IOE
input-mux / IOE output-register / PLL-clock block forces to 0 when that instance is
OFF (an unused input mux reading all-zero, a combinational IOE with no output
register, a PLL block that lives entirely in the aux/CFF plane so its main-CRAM
CLKOUT-select footprint is all-zero) is never written -> the two-background
write-mask (ledger.py) marks it UNWRITTEN -> UNKNOWN_CLEAR, even though the device
file fully determines it as 0.

This codec closes exactly those cells, the honest way (decode-or-refuse, NO
implicit-zero), reusing the two already-locked inverted codecs' OWN field footprints
and decode tables:

  codec_ioe-reg-and-inputmux  (IoeRegInputMuxCodec):
      * 185 IOE input muxes (arch 252) -- complete per-mux select field.
      * IOE output/OE registers (arch 312/262/259) in main_cram -- complete field.
  codec_pll-m9k-clock         (PllM9kClockCodec):
      * PLL_CLKOUT_COUNTER_SELECT (16-cell) + CLOCK_ROUTING_BLOCK_MUX (16-cell),
        the design-INVARIANT main-CRAM PLL/clock footprint.

FULL-FIELD DECODE-OR-REFUSE (per instance, read from the REAL image)
-------------------------------------------------------------------
  input mux / PLL multi-bit field:
     signature in the codec decode table            -> ACTIVE: set the codeword 1s,
                                                        clear the field's other cells
                                                        (proven 0 by exact-codeword match)
     signature all-zero                             -> OFF:    clear the whole field
                                                        (unselected mux / unused block:
                                                         all select cells provably 0)
     signature non-zero and not a codeword          -> REFUSE (undecoded/garbage; UNWRITTEN)
  IOE main_cram register (fixed codeword reg_values):
     read == reg_values                             -> ACTIVE: own the whole field
     read all-zero                                  -> OFF (combinational/no reg): clear field
     otherwise                                      -> REFUSE

HONEST WALLS (refused: off-value not provable)
----------------------------------------------
  * IOE input-register fields in the 0xa0 CFF/PGMIO plane (arch 231/247/248):
    one CFF config cell fans out to ~4 scattered header-frame cells, so an all-zero
    main-frame reflection does NOT prove the logical register off. REFUSED whole.
  * PLL_AUX single-bit field: maximally ambiguous alone; owned only when a multi-bit
    PLL instance in the same block also decoded ACTIVE. Refused for the off/clear plane.
  * M9K unused-block init/mode fields: the device-general INIT geometry
    (m9k_init_codec) grounds only specific X-columns / Y-lanes and REFUSES ungrounded
    sites; the full per-block init+mode field is therefore NOT enumerable device-wide
    -> left UNKNOWN_CLEAR (not bluffed).

GATE (0 INVENTED, 0 WRONG_CLEAR) -- holds by construction
---------------------------------------------------------
The plan is computed from the REAL image: every SET cell is real-1 (the decoded
codeword bit) -> 0 INVENTED; every CLEAR cell is real-0 (an OFF field is all-zero; an
ACTIVE field's non-codeword cells are 0 by exact match) -> 0 WRONG_CLEAR. A real-1
cell can only ever enter a SET write (any resource that would clear it must have read
it 0, impossible), so the plan is globally single-valued and equals the real image on
every position it touches -- validated empirically by the two-background from-blank
ledger (ledger.py: wrong_clear == invented == 0).

decode-or-refuse; commit nothing.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEV = "<repo>/devfile"                         # campaign device tree (codecs)
for _p in (_HERE, os.path.join(_DEV, "decoder"), _DEV):
    if _p not in sys.path:
        sys.path.insert(0, _p)


class IoFullFieldCodec:
    """Complete field-mask (set + provable-clear) of the IOE input muxes, IOE
    output/OE registers (main_cram) and PLL/global-clock main-CRAM fields, gated
    decode-or-refuse on the real image. Instantiated over the already-loaded
    IoeRegInputMuxCodec + PllM9kClockCodec instances the unified decoder holds."""

    def __init__(self, ioeim, pllclk):
        self.ioeim = ioeim
        self.pllclk = pllclk

        # ---- IOE input muxes: (ordered [(byte,bit)], decode{sig->hit}) ----
        self._muxes = []
        for skey, m, cells, decode in ioeim._muxes:
            self._muxes.append((cells, decode))

        # ---- IOE registers: split main_cram (ownable) vs CFF-plane (refused) ----
        self._regs_main = []        # (cells[(byte,bit)], reg_values)
        self._regs_cff = 0
        for r, cells, rvals in ioeim._regs:
            if r.get("regions") == ["main_cram"]:
                self._regs_main.append((cells, list(rvals)))
            else:
                self._regs_cff += 1     # 0xa0 CFF-plane input register -> honest wall

        # ---- PLL / clock instances: multi-bit ownable, 1-bit refused for clear ----
        self._pll_multi = []        # (cells[(byte,bit)], decode{sig->dec}, block, group, ambiguous_sigs)
        self._pll_1bit = 0
        for skey, sd, cells in pllclk._inst:
            if len(cells) >= 2:
                amb = {sig for sig in sd["decode"]
                       if (tuple(cells), sig) in pllclk.ambiguous}
                block = sd["instance"].split("@")[0]
                self._pll_multi.append((cells, sd["decode"], block, sd["group"], amb))
            else:
                self._pll_1bit += 1

    # ------------------------------------------------------------------ plan
    def plan(self, real_img):
        """Return (set_cells{(b,bit):1}, clear_cells{(b,bit)}, stats), derived from
        the real image, decode-or-refuse. Every set cell is real-1, every clear cell
        is real-0 (asserted by the downstream two-background gate)."""
        set_cells = {}
        clear_cells = set()
        st = {"ioe_mux_active": 0, "ioe_mux_off": 0, "ioe_mux_refused": 0,
              "ioe_reg_active": 0, "ioe_reg_off": 0, "ioe_reg_refused": 0,
              "ioe_reg_cff_refused": self._regs_cff,
              "pll_active": 0, "pll_off": 0, "pll_refused": 0,
              "pll_1bit_refused": self._pll_1bit,
              "m9k_unused_block_refused": "ungrounded-device-wide (see report)"}

        def own_field(cells, active_set):
            for (by, bit) in cells:
                if (by, bit) in active_set:
                    set_cells[(by, bit)] = 1
                else:
                    clear_cells.add((by, bit))

        # ---- IOE input muxes (arch 252) ----
        for cells, decode in self._muxes:
            sig = "".join(str((real_img[by] >> bit) & 1) for (by, bit) in cells)
            if sig in decode:                                   # ACTIVE codeword
                active = {(by, bit) for (by, bit) in cells if (real_img[by] >> bit) & 1}
                own_field(cells, active)
                st["ioe_mux_active"] += 1
            elif "1" not in sig:                                # OFF (all-zero)
                own_field(cells, set())
                st["ioe_mux_off"] += 1
            else:                                               # undecoded -> REFUSE
                st["ioe_mux_refused"] += 1

        # ---- IOE output/OE registers (main_cram) ----
        for cells, rvals in self._regs_main:
            read = [(real_img[by] >> bit) & 1 for (by, bit) in cells]
            if read == rvals:                                   # ACTIVE codeword
                active = {(by, bit) for (by, bit), v in zip(cells, read) if v}
                own_field(cells, active)
                st["ioe_reg_active"] += 1
            elif not any(read):                                 # OFF (combinational)
                own_field(cells, set())
                st["ioe_reg_off"] += 1
            else:                                               # partial/other -> REFUSE
                st["ioe_reg_refused"] += 1

        # ---- PLL / global-clock multi-bit fields (main_cram) ----
        for cells, decode, block, group, amb in self._pll_multi:
            sig = "".join(str((real_img[by] >> bit) & 1) for (by, bit) in cells)
            if sig in decode and sig not in amb:                # ACTIVE codeword
                active = {(by, bit) for (by, bit) in cells if (real_img[by] >> bit) & 1}
                own_field(cells, active)
                st["pll_active"] += 1
            elif "1" not in sig:                                # OFF (unused block)
                own_field(cells, set())
                st["pll_off"] += 1
            else:                                               # undecoded -> REFUSE
                st["pll_refused"] += 1

        # set-wins safety (guaranteed disjoint by the real-image gate; belt & braces)
        clear_cells -= set(set_cells.keys())
        return set_cells, clear_cells, st

    # ------------------------------------------------------------ tagged plan
    def plan_tagged(self, real_img):
        """Same plan, but also return {class -> set of clear cells} for per-class
        attribution. A cell that ends up in set_cells is removed from every tag."""
        tags = {"ioe_mux_off": set(), "ioe_mux_active": set(),
                "ioe_reg_off": set(), "ioe_reg_active": set(),
                "pll_off": set(), "pll_active": set()}
        set_cells = {}

        def field(cells, active_set, tag):
            for (by, bit) in cells:
                if (by, bit) in active_set:
                    set_cells[(by, bit)] = 1
                else:
                    tags[tag].add((by, bit))

        for cells, decode in self._muxes:
            sig = "".join(str((real_img[by] >> bit) & 1) for (by, bit) in cells)
            if sig in decode:
                active = {(by, bit) for (by, bit) in cells if (real_img[by] >> bit) & 1}
                field(cells, active, "ioe_mux_active")
            elif "1" not in sig:
                field(cells, set(), "ioe_mux_off")
        for cells, rvals in self._regs_main:
            read = [(real_img[by] >> bit) & 1 for (by, bit) in cells]
            if read == rvals:
                active = {(by, bit) for (by, bit), v in zip(cells, read) if v}
                field(cells, active, "ioe_reg_active")
            elif not any(read):
                field(cells, set(), "ioe_reg_off")
        for cells, decode, block, group, amb in self._pll_multi:
            sig = "".join(str((real_img[by] >> bit) & 1) for (by, bit) in cells)
            if sig in decode and sig not in amb:
                active = {(by, bit) for (by, bit) in cells if (real_img[by] >> bit) & 1}
                field(cells, active, "pll_active")
            elif "1" not in sig:
                field(cells, set(), "pll_off")
        sk = set(set_cells.keys())
        for t in tags:
            tags[t] -= sk
        return tags

    # ------------------------------------------------------------------ apply
    def apply_into(self, out, plan):
        """Write the precomputed plan onto `out` (any background): clears first, then
        sets (set-wins). Background-independent -> owned by the two-bg diff."""
        set_cells, clear_cells, _ = plan
        for (by, bit) in clear_cells:
            out[by] &= ~(1 << bit)
        for (by, bit) in set_cells:
            out[by] |= (1 << bit)
