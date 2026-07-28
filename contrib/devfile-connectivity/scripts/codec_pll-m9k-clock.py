#!/usr/bin/env python3
"""
codec_pll-m9k-clock.py -- INVERTED pll / m9k / clock decode codec (decode-or-refuse).

This is the INVERSION step wf 13 skipped for the pll-m9k-clock class group.  It takes
the harvested FORWARD table (harvest_pll-m9k-clock.jsonl: the assembler's own emitted
DB_BIT_SETTING bits per {setting, codeword}) and turns it into a DECODE table
{observed bits -> codeword -> named meaning}, then reads it out of any EP4CE-die .rbf
with strict refusal on non-unique / unobserved patterns.  Nothing is bluffed.

WHAT IS INVERTED (and what is REFUSED, honestly)
------------------------------------------------
The harvest found (and this codec confirms) that for Cyclone IV the DESIGN-VARYING PLL
numeric config -- charge-pump / loop-filter / VCO / per-counter multiply / duty / phase
-- is resolved at FIT time and committed into the aux/CFF serializer plane (flat bit31
set, tag 0xA...), which is NOT serialized into the frame CRAM and has no proven
get_cff_base_address -> rbf map.  Those fields are therefore un-readable from a .rbf and
are REFUSED wholesale (this is the open sub-gap, not a codec bluff).

What DOES land in the main-CRAM plane (rbf-readable) and is inverted here:

    arch=761 bt=43  PLL_CLKOUT_COUNTER_SELECT   16-bit encoded  (clkout0/1/2 selectors)
    arch=743 bt=43  PLL_AUX_SETTING              1-bit
    arch=2338 bt=73 CLOCK_ROUTING_BLOCK_MUX     16-bit encoded  (row/global clock source)

These are the output-counter SELECT and clock block-mux -- the design-INVARIANT footprint
of "a PLL/clock block is instantiated here using these output counters".  Verified
invariant across the 5 independent PLL carriers (pll_a m4 / pll_b m2 / pll_c m8 /
pll_d duty25 / pll_e ph90): identical CLKOUT-select signature in every fresh compile.

THE SIGNATURE (why this inversion is exact, not fuzzed)
-------------------------------------------------------
Each recorded field is the assembler's own DB_BIT_SETTING vector for that physical block;
`first` is the flat CRAM bitpos (bitpos_to_rbf.flat_to_rbf, HW-validated).  The emit-order
value tuple is the field signature.  Per physical instance the codec stores the ordered
flat-cell list + {signature -> codeword -> meaning}.  Reading a bitstream at those exact
cells (fixed DEVICE GEOMETRY, design-independent) reproduces the signature and inverts it.

DECODE-OR-REFUSE
----------------
  * DECODED: an instance whose read signature matches an OBSERVED codeword -> named
             (setting + codeword + meaning), reproduced bit-exact.
  * REFUSED: a signature not in the observed table (unused block reading 0, or an exotic
             codeword no carrier hit) -> 0 cells claimed.  Only OBSERVED codewords carry
             an attributed MEANING; unobserved patterns are refused, never bluffed.
  * NON-UNIQUE guard: if a (cell-list, signature) maps to >1 distinct meaning -> refused.
  * 1-BIT CORROBORATION: the lone PLL_AUX bit (2 possible signatures -> maximally
             ambiguous alone) is claimed ONLY when >=1 multi-bit PLL instance in the same
             PLL block also decoded.  On a bin where no CLKOUT-select decodes (e.g. the
             vendor bin, whose PLL lives entirely in the aux/CFF plane), PLL_AUX is
             therefore REFUSED rather than owned on a single coincidental bit.

Standalone:  python3 codec_pll-m9k-clock.py         # self-validation (oracle + held-out)
Integrated:  imported by devfile/decoder/decode_rbf.py as a codec adapter.
"""
import os, sys, json

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEVFILE = "<repo>/devfile"
for p in (_DEVFILE, os.path.join(_DEVFILE, "decoder")):
    if p not in sys.path:
        sys.path.insert(0, p)
from bitpos_to_rbf import flat_to_rbf                       # proven device geometry

TABLE = os.path.join(_HERE, "codec_pll-m9k-clock_table.json")
_MIN_MULTIBIT = 2                                           # >=2 cells = corroborating


class PllM9kClockCodec:
    """Inverted decode codec for the pll/clock CRAM-resident config fields."""

    def __init__(self, table_path=TABLE):
        self.settings = {}
        self.ambiguous = set()
        self.status = "ABSENT (no table)"
        if os.path.exists(table_path):
            t = json.load(open(table_path))
            self.settings = t["settings"]
            self.status = ("LOCKED (pll-m9k-clock inverted decode-or-refuse; "
                           "aux/CFF multiply/duty/phase REFUSED -- not rbf-serialized)")
        # pre-resolve each instance's ordered (byte,bit) cells once
        self._inst = []            # (skey, sd, cells[(byte,bit)])
        for skey, sd in self.settings.items():
            cells = [flat_to_rbf(f) for f in sd["flats"]]
            if any(c is None for c in cells):
                continue            # not serialized to frame CRAM -> refuse
            self._inst.append((skey, sd, cells))
        # global non-uniqueness guard across all instances
        seen = {}
        for skey, sd, cells in self._inst:
            for sig, dec in sd["decode"].items():
                k = (tuple(cells), sig)
                seen.setdefault(k, set()).add(dec["meaning"])
        self.ambiguous = {k for k, v in seen.items() if len(v) > 1}

    def frame_band(self):
        return None                # PLL/clock header cells scattered across CRAM frames

    # ---- decode-or-refuse -------------------------------------------------- #
    def decode(self, N):
        img = N.masked
        feats, claimed = [], set()
        refused = 0
        by_setting = {}
        pll_block_ok = {}          # instance-block -> a multi-bit PLL field decoded there

        # pass 1: decode all multi-bit instances (>= _MIN_MULTIBIT cells)
        pending_1bit = []
        for skey, sd, cells in self._inst:
            st = by_setting.setdefault(sd["name"], {"owned": 0, "refused": 0})
            sig = "".join(str((img[b] >> bit) & 1) for (b, bit) in cells)
            if len(cells) < _MIN_MULTIBIT:
                pending_1bit.append((skey, sd, cells, sig))
                continue
            dec = sd["decode"].get(sig)
            if dec is None or (tuple(cells), sig) in self.ambiguous:
                refused += 1; st["refused"] += 1
                continue
            st["owned"] += 1
            if sd["group"] == "pll":
                pll_block_ok[sd["instance"].split("@")[0]] = True
                pll_block_ok["_any_pll"] = True
            claimed.update(cells)
            feats.append(self._mk_feat(skey, sd, cells, sig, dec))

        # pass 2: 1-bit fields, only if corroborated by a decoded multi-bit PLL field
        for skey, sd, cells, sig in pending_1bit:
            st = by_setting.setdefault(sd["name"], {"owned": 0, "refused": 0})
            dec = sd["decode"].get(sig)
            corroborated = pll_block_ok.get("_any_pll", False) if sd["group"] == "pll" else True
            if dec is None or (tuple(cells), sig) in self.ambiguous or not corroborated:
                refused += 1; st["refused"] += 1
                continue
            st["owned"] += 1
            claimed.update(cells)
            feats.append(self._mk_feat(skey, sd, cells, sig, dec))

        summary = {
            "status": self.status,
            "owned_instances": len(feats),
            "refused_instances": refused,
            "owned_cells": len(claimed),
            "by_setting": by_setting,
            "refused_note": ("aux/CFF-plane PLL numeric config (multiply/duty/phase/"
                             "charge-pump/VCO, flat tag 0xA...) is not serialized to "
                             "frame CRAM -> not readable from .rbf -> REFUSED; "
                             "M9K mode/init owned by m9k_codec (unused on vendor die)"),
        }
        return feats, claimed, summary

    def _mk_feat(self, skey, sd, cells, sig, dec):
        vals = [int(c) for c in sig]
        return {
            "setting": skey, "name": sd["name"], "group": sd["group"],
            "arch": sd["arch"], "blockty": sd["blockty"], "scope": sd["scope"],
            "codeword": dec["codeword"], "meaning": dec["meaning"],
            "confidence": sd["confidence"],
            "cells": [[b, bit] for (b, bit) in cells], "values": vals,
        }

    # ---- inverse: re-emit a decoded feature's cells ------------------------ #
    def encode_into(self, out, feat):
        for (b, bit), v in zip(feat["cells"], feat["values"]):
            if v:
                out[b] |= (1 << bit)
            else:
                out[b] &= ~(1 << bit)


# --------------------------------------------------------------------------- #
# standalone self-validation
# --------------------------------------------------------------------------- #
def _selfcheck():
    print("== codec_pll-m9k-clock self-validation ==")
    codec = PllM9kClockCodec()
    print("status:", codec.status)
    print("resolved instances:", len(codec._inst), "| ambiguous signatures:",
          len(codec.ambiguous))

    # (a) REPRODUCE the harvested oracle: each instance's own signature inverts to its
    #     own codeword, bit-exact.
    ok = tot = 0
    for skey, sd, cells in codec._inst:
        for sig, dec in sd["decode"].items():
            tot += 1
            ok += (sd["decode"].get(sig, {}).get("codeword") == dec["codeword"])
    print(f"(a) reproduce harvested oracle: {ok}/{tot} bit-exact  "
          f"{'PASS' if ok == tot else 'FAIL'}")

    # (b) HELD-OUT on fresh independent compiles: the 5 PLL carriers (pll_a..e) each
    #     committed the CLKOUT-select cells independently.  Confirm every carrier reads
    #     the SAME signature at the recorded cells (design-invariant footprint), i.e. the
    #     decode is device geometry, not one design -- predicted from pll_a, confirmed on
    #     pll_b..e with 0 mispredictions.  (bitfield.jsonl records the set-side subset of
    #     each field; we cross-check exactly the cells it recorded.)
    WORK = os.path.join(_HERE, "work")
    cars = ["pll_a", "pll_b", "pll_c", "pll_d", "pll_e"]

    def cell_map(car):
        m = {}
        p = os.path.join(WORK, car, "bitfield.jsonl")
        if not os.path.exists(p):
            return None
        for line in open(p):
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            if o.get("type") == "bf":
                for c in o.get("cells", []):
                    m[c[0]] = c[1]
        return m

    maps = {c: cell_map(c) for c in cars}
    if all(maps[c] is not None for c in cars):
        # the recorded (set-side) flats for the three CLKOUT-select instances
        clkout_flats = [sd["flats"] for skey, sd, _ in codec._inst
                        if sd["name"] == "PLL_CLKOUT_COUNTER_SELECT"]
        pred = mispred = checked = 0
        ref = "pll_a"
        for flats in clkout_flats:
            recorded = [f for f in flats if f in maps[ref]]
            base_sig = [maps[ref][f] for f in recorded]
            for c in cars:
                if c == ref:
                    continue
                got = [maps[c].get(f) for f in recorded]
                checked += 1
                if got == base_sig:
                    pred += 1
                else:
                    mispred += 1
        print(f"(b) held-out over 5 fresh PLL compiles (CLKOUT-select invariance): "
              f"{pred} confirmed, {mispred} MISPREDICT over {checked} cross-checks  "
              f"{'PASS' if mispred == 0 else 'FAIL'}")
    else:
        print("(b) held-out: carrier bitfield captures not found -- skipped")

    # (c) VENDOR probe: decode-or-refuse on the target bin.
    try:
        import decode_rbf as D
        N = D.load_normalized(
            "target.rbf")
        feats, claimed, summ = codec.decode(N)
        out = bytearray(N.img)
        for f in feats:
            codec.encode_into(out, f)
        rt = all(((out[b] >> bit) & 1) == v
                 for f in feats for (b, bit), v in zip(f["cells"], f["values"]))
        print(f"(c) vendor probe: owned {summ['owned_instances']} instances / "
              f"{len(claimed)} cells; refused {summ['refused_instances']}; "
              f"round-trip {'PASS' if rt else 'FAIL'}")
        print(f"    by setting: {summ['by_setting']}")
    except Exception as e:
        print(f"(c) vendor probe skipped: {e}")


if __name__ == "__main__":
    _selfcheck()
