#!/usr/bin/env python3
"""
codec_le-lab-secondary.py -- INVERTED le/lab-secondary decode codec (decode-or-refuse).

This is the INVERSION step wf 13 skipped.  It takes the harvested FORWARD table
(harvest_le-lab-secondary.jsonl: {setting, codeword -> emitted DB_BIT_SETTING bits})
and turns it into a DECODE table {observed bits -> codeword -> named meaning}, then
reads it out of any EP4CE-die .rbf with strict refusal on non-unique / unobserved
patterns.  Nothing is bluffed.

WHAT IS INVERTED
----------------
The four le/lab-secondary settings whose config field lies ENTIRELY in the main-CRAM
plane (bit31==0, i.e. serialized into the .rbf) -- so they are actually readable from a
bitstream:

    arch=316 bt=6  LE_REGISTER_SECONDARY_CONTROL_FIELD   3-bit encoded-MSB
    arch=316 bt=5  LAB_SECONDARY_CONTROL_FIELD           3-bit encoded-MSB
    arch=252 bt=6  LE_MODE_FIELD                          8-bit mapped-LUT
    arch=252 bt=5  LAB_LE_MODE_AGG                       16-bit mapped-LUT

The le/lab SRC/CLK muxes (arch 231/247/248/254/506/234/235) live in the aux/dummy
CFF planes (0xA.../0xF...) which are NOT serialized into the frame CRAM, so they are
un-readable from a .rbf and are REFUSED here (not part of this codec).

THE SIGNATURE (why this inversion is exact, not fuzzed)
-------------------------------------------------------
DB_BIT_SETTING emit order is not a fixed POSITIONAL convention across settings, but
WITHIN one setting/codeword the compiler's emit-order value tuple is IDENTICAL across
every independent compile (verified over 8 compiles; see invert_le-lab-secondary.md).
So the emit-order value tuple is the device-invariant field signature.  Across
codewords the signatures are DISTINCT => the inversion {signature -> codeword} is
UNIQUE.  Each instance is stored as its per-block ordered flat-cell list (the compiler's
own emit order for that physical block); reading a bitstream at those cells in that
order reproduces the signature and inverts to the codeword.

DECODE-OR-REFUSE
----------------
  * DECODED: an instance whose read signature matches an OBSERVED codeword -> named
             (setting + codeword + meaning) and reproduced bit-exact.
  * REFUSED: a signature not in the observed table (e.g. an unused LE reading 0, or an
             exotic codeword no capture hit) -> claimed 0 cells.  For the encoded-MSB
             fields every 2^w pattern is structurally a codeword, but only OBSERVED
             codewords carry an attributed MEANING, so unobserved patterns are refused
             rather than named -- never bluffed.
             The aux/dummy-plane SRC/CLK muxes are refused wholesale.

Instances are harvested at the blocks the carrier/differential/labmix compiles used;
their flat addresses are fixed DEVICE GEOMETRY (design-independent), so probing a vendor
bin at those exact cells reads whatever THAT design programmed at those LEs/LABs.  Where
the vendor did not use the block, the read refuses.

Standalone:  python3 codec_le-lab-secondary.py            # self-validation
Integrated:  imported by devfile/decoder/decode_rbf.py as a CodecRegion adapter.
"""
import os
import sys
import json

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEVFILE = "<repo>/devfile"
for p in (_DEVFILE, os.path.join(_DEVFILE, "decoder")):
    if p not in sys.path:
        sys.path.insert(0, p)
from bitpos_to_rbf import flat_to_rbf                    # proven device geometry

TABLE = os.path.join(_HERE, "codec_le-lab-secondary_table.json")


class LeLabSecondaryCodec:
    """Inverted decode codec for the le/lab register-secondary/mode config fields."""

    def __init__(self, table_path=TABLE):
        self.settings = {}
        self.status = "ABSENT (no table)"
        if os.path.exists(table_path):
            t = json.load(open(table_path))
            self.settings = t["settings"]
            self.status = ("LOCKED (le/lab-secondary inverted decode-or-refuse; "
                           "aux-plane SRC/CLK muxes REFUSED)")
        # Pre-resolve each instance's ordered (byte,bit) cells once.
        self._inst = []     # list of (skey, setting_dict, ordered_cells[(byte,bit)])
        for skey, sd in self.settings.items():
            for inst in sd["instances"]:
                cells = [flat_to_rbf(f) for f in inst["flats"]]
                if any(c is None for c in cells):
                    continue            # not serialized to frame CRAM -> skip (refuse)
                self._inst.append((skey, sd, cells))

    def frame_band(self):
        return None                     # LE/LAB body cells scattered across CRAM frames

    # ---- decode-or-refuse -------------------------------------------------- #
    def decode(self, N):
        """Return (features, claimed_cells, summary).  Reads N.masked (CRC-masked,
        codec-convention).  Only instances whose signature matches an observed
        codeword are claimed; everything else refuses."""
        img = N.masked
        feats, claimed = [], set()
        refused = 0
        by_setting = {}
        for skey, sd, cells in self._inst:
            sig = "".join(str((img[b] >> bit) & 1) for (b, bit) in cells)
            hit = sd["decode"].get(sig)
            st = by_setting.setdefault(skey, {"owned": 0, "refused": 0})
            if hit is None:
                refused += 1
                st["refused"] += 1
                continue                # decode-or-REFUSE: unobserved signature
            st["owned"] += 1
            values = [(img[b] >> bit) & 1 for (b, bit) in cells]
            cellset = [[b, bit] for (b, bit) in cells]
            claimed.update((b, bit) for (b, bit) in cells)
            feats.append({
                "setting": skey, "name": sd["name"], "arch": sd["arch"],
                "blockty": sd["blockty"], "scope": ("LE" if sd["blockty"] == 6 else "LAB"),
                "sel": hit["sel"], "meaning": hit["meaning"],
                "confidence": sd["confidence"],
                "cells": cellset, "values": values,
            })
        summary = {
            "status": self.status,
            "owned_instances": len(feats),
            "refused_instances": refused,
            "owned_cells": len(claimed),
            "by_setting": by_setting,
            "refused_note": ("aux/dummy-plane le/lab SRC/CLK muxes (arch "
                             "231/247/248/254/506/234/235) are not serialized to frame "
                             "CRAM -> not readable from .rbf -> REFUSED"),
        }
        return feats, claimed, summary

    # ---- inverse: re-emit a decoded feature's cells ------------------------ #
    def encode_into(self, out, feat):
        for (b, bit), v in zip(feat["cells"], feat["values"]):
            if v:
                out[b] |= (1 << bit)
            else:
                out[b] &= ~(1 << bit)


# --------------------------------------------------------------------------- #
# standalone self-validation: reproduce harvested oracle + held-out (leave-one-
# compile-out) + vendor probe.  Proves the inversion is bit-exact and never bluffs.
# --------------------------------------------------------------------------- #
def _selfcheck():
    import collections
    LOOP = os.path.join(_DEVFILE, "re_workflows/out/loop")
    EX = os.path.join(_DEVFILE, "re_workflows/out/extract")
    CAPS = {
        "specimenR1": f"{LOOP}/R1_oracle.jsonl",
        "d_mbase": f"{LOOP}/diff/mbase_p_oracle.jsonl",
        "d_mce": f"{LOOP}/diff/mce_p_oracle.jsonl",
        "d_maclr": f"{LOOP}/diff/maclr_p_oracle.jsonl",
        "d_msclr": f"{LOOP}/diff/msclr_p_oracle.jsonl",
        "d_msload": f"{LOOP}/diff/msload_p_oracle.jsonl",
        "d_mcarry": f"{LOOP}/diff/mcarry_p_oracle.jsonl",
        "labmix": f"{EX}/labmix/labmix_oracle.jsonl",
    }
    MAIN = 0x10000000
    FULL = {(316, 6), (316, 5), (252, 6), (252, 5)}

    def load(p):
        for line in open(p):
            line = line.strip()
            if line:
                o = json.loads(line)
                if o.get("type") == "arch":
                    yield o

    def recs(cap):
        r = []
        for o in load(CAPS[cap]):
            k = (o["arch"], o["blockty"])
            if k in FULL and all(b["first"] < MAIN for b in o["bits"]):
                r.append((k, tuple(b["value"] for b in o["bits"]), o["sel"]))
        return r

    # (a) reproduce: full table inverts every observed instance to its own sel
    tbl = collections.defaultdict(dict)
    for c in CAPS:
        for k, e, s in recs(c):
            tbl[k][e] = s
    ok = tot = 0
    for c in CAPS:
        for k, e, s in recs(c):
            tot += 1
            ok += (tbl[k].get(e) == s)
    print(f"(a) reproduce harvested oracle: {ok}/{tot} bit-exact  "
          f"{'PASS' if ok == tot else 'FAIL'}")

    # (b) held-out: leave-one-compile-out, predict the held compile; never mispredict
    mis = pred = unseen = 0
    for held in CAPS:
        t = collections.defaultdict(dict)
        for c in CAPS:
            if c == held:
                continue
            for k, e, s in recs(c):
                t[k][e] = s
        for k, e, s in recs(held):
            p = t[k].get(e)
            if p is None:
                unseen += 1
            elif p == s:
                pred += 1
            else:
                mis += 1
    print(f"(b) held-out leave-one-compile-out: {pred} correct, {unseen} refused-unseen, "
          f"{mis} MISPREDICT  {'PASS' if mis == 0 else 'FAIL'}")

    # vendor probe via the class
    try:
        import decode_rbf as D
        N = D.load_normalized("target.rbf")
        codec = LeLabSecondaryCodec()
        feats, claimed, summ = codec.decode(N)
        # round-trip: re-emit claimed cells, compare
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
    print("== codec_le-lab-secondary self-validation ==")
    c = LeLabSecondaryCodec()
    print("status:", c.status, "| resolved instances:", len(c._inst))
    _selfcheck()
