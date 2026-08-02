# SPDX-License-Identifier: GPL-3.0-or-later
#!/usr/bin/env python3
"""ledger.py -- two-background ternary-ownership completeness oracle.

Harden the from-blank ownership oracle: replace the SET-bit count with a TERNARY
LEDGER over EVERY serialized RBF position (all 2,944,088 bits on the die
`cycloneive1` 368011-byte image), under the strict no-implicit-zero-as-owned
discipline. Device-general: the metric and the write-mask are design-independent;
only the model it measures is the device-file-grounded encoder.

CORE METHOD -- the honest write-mask via a TWO-BACKGROUND diff:
  The from-blank encoder is run onto TWO backgrounds -- all-zero (0x00) and all-one
  (0xFF). A position is OWNED by the model only if the encoder asserts the SAME
  value on BOTH backgrounds (i.e. it deterministically WRITES that bit, set OR
  clear). A position whose value depends on the background (0 under bg0, 1 under
  bgF) is NOT written by any codec -- it is a background passthrough, and a bit we
  merely LEFT at zero is UNKNOWN, never owned. This operationalises the rule: "a
  position written 0 by an UNKNOWN source is UNKNOWN, not owned. No
  implicit-zero-as-owned." (A codec that only-sets and never-clears a decoded-0 bit
  shows as unwritten -> conservative: we under-claim owned-zeros, never over-claim.)
  Invented bits (written 1 where real is 0) MUST be 0 by the decode-or-refuse gate;
  the ledger asserts it.

TERNARY LEDGER STATES (every position -> exactly one):
  KNOWN             written, value == real, source = a device-file TABLE or a format
                    CONSTANT (fabric CLOSED_TABLE cells + preamble/tail/sync).
  DERIVED           value COMPUTED from other owned positions:
                      DERIVED (emitted)  -- frame CRC written from blank, matches real.
                      DERIVED_PENDING    -- frame CRC provably generable but GATED on
                                            an upstream UNKNOWN payload (closes free).
  OPAQUE_PRESERVED  raw-copied without semantic understanding. 0 here (passthrough OFF).
  DONTCARE_PROVEN   value PROVEN irrelevant to the netlist. 0 here (no don't-care
                    oracle yet; hook left for phase-2 inactive-resource proofs).
  UNKNOWN           model does not determine the value:
                      UNKNOWN_SET    real=1, unwritten -- the true residual set bits (EU).
                      UNKNOWN_CLEAR  real=0, unwritten -- implicit-zero, honestly NOT owned.
                      INVALID_REFUSE real=1, refused codeword (header-frame integrity field).

TWO REPRESENTATIONS:
  physical_config_ir  -- the exact per-position bit assignment the model asserts (the
                         write-mask + values); bit-exact where written, refuses elsewhere.
  lifted_netlist      -- the structured feature model (routing arcs, LUTs, IOE, LEIM,
                         asmdb block-mux, calc-reloc, cfgres ...) that PROJECTS onto the IR.

This is the ORCHESTRATION PATTERN: it drives the campaign's device-file-grounded
`unified_model` encoder (harvested tables under $QUARTUS_ROOTDIR device files) and
the classifier/routing-cell overlays that live outside this contribution. Wire your
own from-blank encoder into `encode_bg`; the load-bearing, portable part is the
two-background write-mask and the ternary census. Commit nothing.
"""
import os, sys, json, gzip, collections

HERE = os.path.dirname(os.path.abspath(__file__))
DEV  = "<repo>/devfile"                       # campaign device tree (encoder + overlays)
PROOF= os.path.join(DEV, "re_workflows", "out", "proof")
OWN  = os.path.join(DEV, "re_workflows", "out", "ownership")
CENSUS = os.path.join(DEV, "re_workflows", "out", "census")
RESID = os.path.join(HERE, "residual")
os.makedirs(RESID, exist_ok=True)
for p in (PROOF, os.path.join(DEV, "decoder"), CENSUS, OWN, DEV, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import unified_model as UM
import bitpos_to_rbf as B                      # proven device geometry (contrib sibling)
import A_config_classifier as AC

PRE, FS, END = UM.PREAMBLE, UM.FRAME_STRIDE, UM.FRAMES_END
CO, HF, NF = UM.CRC_OFF, UM.HEADER_FRAMES, UM.N_FRAMES
DB = UM.DATA_BYTES
SYNC_END = PRE + len(UM.SYNC_MAGIC)
_POP = [bin(b).count("1") for b in range(256)]


# ------------------------------------------------------------ two-background encode
def encode_bg(um, decoded, bg):
    """Replicate UnifiedModel.encode_from_blank (gated CRC) but onto a `bg`-filled
    background instead of hardcoded all-zero. Identical layer order & CRC gate."""
    N = decoded["N"]; size = N.size; real = N.img
    out = bytearray([bg]) * size
    for i in range(PRE):            out[i] = 0xFF
    for i in range(END, size):      out[i] = 0xFF
    out[PRE:PRE + len(UM.SYNC_MAGIC)] = UM.SYNC_MAGIC
    um._fabric_encode_into(out, decoded["fabric"])
    for F in range(HF, NF):
        base = PRE + F * FS
        payload = out[base:base + DB]
        if bytes(payload) != bytes(real[base:base + DB]):
            continue                                   # gated refuse
        c = UM.CRC.crc16_frame(bytes(payload))
        out[base + CO]     = c & 0xFF
        out[base + CO + 1] = (c >> 8) & 0xFF
    return out


# --------------------------------------------------------------------- region tag
def region_of_byte(byte):
    if byte < PRE:            return "preamble"          # RESERVED_CONSTANT
    if byte >= END:           return "tail"              # RESERVED_CONSTANT
    F  = (byte - PRE) // FS
    off = (byte - PRE) % FS
    if off >= CO:
        return "crc.header" if F < HF else "crc.data"
    if byte < SYNC_END:       return "sync"              # RESERVED_CONSTANT
    return "cram.header" if F < HF else "cram.data"


def main():
    um = UM.UnifiedModel()
    decoded = um.decode(UM.TARGET)
    N = decoded["N"]; img = N.img; size = N.size
    fab_claimed = decoded["fab_claimed"]

    o0 = encode_bg(um, decoded, 0x00)      # from-blank (the deliverable image)
    oF = encode_bg(um, decoded, 0xFF)      # from-all-ones (probes the write-mask)

    # ---- ternary ledger accumulation, byte-wise with popcount masks ----
    L = collections.defaultdict(collections.Counter)
    total_set = 0
    invented = []            # written 1 where real 0  (MUST be empty)
    wrong_clear = []         # written 0 where real 1  (model clears an owned-real bit)
    eu_cram = []             # UNKNOWN_SET in CRAM payload  (the residual to attribute)
    crc_pending = []         # DERIVED_PENDING (crc.data, gated)
    refuse = []              # INVALID_REFUSE (crc.header)
    written_positions = 0

    for byte in range(size):
        R  = img[byte]
        v  = o0[byte]
        wmask = (~(o0[byte] ^ oF[byte])) & 0xFF          # 1 = written (deterministic)
        reg = region_of_byte(byte)
        total_set += _POP[R]
        written_positions += _POP[wmask]

        agree   = wmask & ~(v ^ R) & 0xFF                # written & value matches real
        owned1  = agree & R                              # owned SET
        owned0  = agree & ~R & 0xFF                      # owned CLEAR (actively forced 0)
        inv     = wmask & v & ~R & 0xFF                  # INVENTED (write 1, real 0)
        wclr    = wmask & ~v & R & 0xFF                  # wrong clear (write 0, real 1)
        un      = (~wmask) & 0xFF                         # unwritten
        un_set  = un & R                                  # unwritten, real 1
        un_clr  = un & ~R & 0xFF                          # unwritten, real 0

        L[reg]["owned_set"]     += _POP[owned1]
        L[reg]["owned_clear"]   += _POP[owned0]
        L[reg]["invented"]      += _POP[inv]
        L[reg]["wrong_clear"]   += _POP[wclr]
        L[reg]["unwritten_set"] += _POP[un_set]
        L[reg]["unwritten_clr"] += _POP[un_clr]

        # collect concrete cells for the residual manifests / invariants
        if inv or wclr or un_set:
            F = (byte - PRE) // FS if PRE <= byte < END else None
            off = (byte - PRE) % FS if PRE <= byte < END else None
            for bit in range(8):
                m = 1 << bit
                if inv & m:   invented.append([byte, bit, reg])
                if wclr & m:  wrong_clear.append([byte, bit, reg])
                if un_set & m:
                    if reg == "cram.data" or reg == "cram.header":
                        eu_cram.append((byte, bit, F, off, reg))
                    elif reg == "crc.data":
                        crc_pending.append([byte, bit, F])
                    elif reg == "crc.header":
                        refuse.append([byte, bit, F])

    # ---- fold regions into the canonical ternary states ----
    def s(reg, k): return L[reg][k]
    KNOWN = (s("preamble","owned_set")+s("preamble","owned_clear")
             +s("tail","owned_set")+s("tail","owned_clear")
             +s("sync","owned_set")+s("sync","owned_clear")
             +s("cram.header","owned_set")+s("cram.header","owned_clear")
             +s("cram.data","owned_set")+s("cram.data","owned_clear"))
    DERIVED_EMIT = s("crc.data","owned_set")+s("crc.data","owned_clear")
    DERIVED_PENDING = len(crc_pending)
    UNKNOWN_SET = len(eu_cram)
    INVALID = len(refuse)
    UNKNOWN_CLEAR = sum(L[r]["unwritten_clr"] for r in L)
    OPAQUE_PRESERVED = 0
    DONTCARE_PROVEN  = 0
    INVENTED = len(invented)
    WRONG_CLEAR = len(wrong_clear)

    owned_positions = KNOWN + DERIVED_EMIT           # actively determined & correct
    total_positions = size * 8

    # ---- SET-bit continuity view (reconcile with the prior set-bit metric) ----
    owned_set_bits = (s("preamble","owned_set")+s("tail","owned_set")+s("sync","owned_set")
                      +s("cram.header","owned_set")+s("cram.data","owned_set")
                      +s("crc.data","owned_set"))
    setbit_residual = UNKNOWN_SET + DERIVED_PENDING + INVALID

    # =====================================================================
    #  RESIDUAL ATTRIBUTION -- assign each EU (UNKNOWN_SET CRAM) cell to one
    #  of the named classes, by device-file physical footprint.
    # =====================================================================
    leim_fp = set()
    lc = um.fab.leim
    if lc is not None:
        for mux in lc._hopa_muxes:
            for fl in mux["flats"]:
                r = B.flat_to_rbf(fl)
                if r is not None: leim_fp.add((r[0], r[1]))
        for fd in lc._hopc_fields:
            for fl in fd["flats"]:
                r = B.flat_to_rbf(fl)
                if r is not None: leim_fp.add((r[0], r[1]))
    route = {}
    with gzip.open(os.path.join(OWN, "A_routing_cells.jsonl.gz"), "rt") as f:
        for line in f:
            by, bt, val, cls, _o = json.loads(line)
            route[(by, bt)] = cls
    ROUTE_SEM = {"SEMANTIC_ROUTING", "SEMANTIC_ROUTING_ORACLE"}
    ROUTE_EU  = {"EXPLICIT_UNKNOWN_UNRESOLVED", "EXPLICIT_UNKNOWN_AMBIG"}
    cfg = AC.classify_config(N)
    config_sem = set(cfg["semantic_bits"].keys())
    config_unk = set(cfg["unknown_bits"].keys())
    _lf, lut_claimed = um.fab.lut.decode(N)
    _if, io_claimed  = um.fab.io.decode(N)
    lut_cells = set(lut_claimed); io_cells = set(io_claimed)
    config_unk = config_unk - config_sem - lut_cells - io_cells
    cff = {}
    for off_s, (by, bt) in json.load(open(os.path.join(DEV, "cff_offset_rbf_map.json")))["canon"].items():
        cff[(by, bt)] = int(off_s)

    def cause_of(key):
        if key in fab_claimed:                 return "config-decoder-grounded-encoder-gap"
        if key in route and route[key] in ROUTE_EU:  return "routing-source-ungrounded"
        if key in leim_fp:                     return "leim-interior-unbound"
        if key in config_unk:                  return "unmodeled-arch-residual"   # calc field
        if key in cff:                         return "cff-aux-control-CALC-unvalued"
        if (key in route and route[key] in ROUTE_SEM) or key in config_sem \
                or key in lut_cells or key in io_cells:
            return "codec-disagreement-unreproduced"
        return "unmodeled-arch-residual"

    by_cause = collections.Counter()
    by_cause_region = collections.defaultdict(collections.Counter)
    cause_cells = collections.defaultdict(list)
    for (byte, bit, F, off, reg) in eu_cram:
        c = cause_of((byte, bit))
        by_cause[c] += 1
        by_cause_region[c][reg] += 1
        cause_cells[c].append([byte, bit, F, off])

    # ---- write per-class residual manifests ----
    CLASS_META = {
        "unmodeled-arch-residual": "ASMDB calculate_bits per-instance relocation replay + undecoded config field value-tables + word/M9K RAM-init generation. No located per-cell footprint.",
        "leim-interior-unbound": "interior muxes the LEIM hop-A/hop-C codec governs but left UNBOUND; closes via the cross-hop sel<->LI wire-node CALC.",
        "routing-source-ungrounded": "mux located + select code present, SOURCE node ungrounded; extend the reconstructed pdb load-order source-binding.",
        "cff-aux-control-CALC-unvalued": "aux/CFF cells located by the offset map but unvalued; gated on calculate_bits + per-field decode over the CFF offset->(F,Y,bit) permutation.",
        "codec-disagreement-unreproduced": "a sibling codec calls it semantic but the device-file-autonomous decoder does not itself ground it (oracle->autonomous promotion).",
        "config-decoder-grounded-encoder-gap": "decoder grounds the cell but the from-blank encoder never re-emitted it (pure encoder-wiring gap).",
    }
    for c in list(by_cause) + ["crc.data-DERIVED_PENDING", "crc.header-INVALID_REFUSE"]:
        if c == "crc.data-DERIVED_PENDING":
            cells = [{"rbf_byte": b, "bit": bt, "frame": F} for (b, bt, F) in crc_pending]
            meta = ("DERIVED (generator proven bit-exact on all data frames) but GATED on "
                    "an upstream UNKNOWN CRAM payload; emits for free as the payload closes.")
        elif c == "crc.header-INVALID_REFUSE":
            cells = [{"rbf_byte": b, "bit": bt, "frame": F} for (b, bt, F) in refuse]
            meta = ("header-frame integrity field proven NOT a standard CRC16 (byte-doubled "
                    "option/header-structure field); the model refuses rather than invent a "
                    "codeword. The 106-bit floor -- see header_field.py.")
        else:
            cells = [{"rbf_byte": b, "bit": bt, "frame": F, "frame_off": off}
                     for (b, bt, F, off) in cause_cells[c]]
            meta = CLASS_META.get(c, "")
        manifest = {
            "class": c,
            "count": len(cells),
            "closing_mechanism": meta,
            "cell_key": "(rbf_byte,bit) serialized position; frame/frame_off give (F,off)",
            "cells": cells,
        }
        fn = os.path.join(RESID, c.replace("/", "_") + ".json")
        json.dump(manifest, open(fn, "w"), indent=1)

    # ---- two representations ----
    ir = {
        "representation": "physical_config_ir",
        "desc": "exact per-position bit assignment the model deterministically asserts (write-mask + values); bit-exact where written, refuses elsewhere.",
        "total_positions": total_positions,
        "written_positions": written_positions,
        "owned_positions": owned_positions,
        "invented_positions": INVENTED,
        "write_mask_source": "two-background diff (bg0x00 vs bg0xFF); a position is written iff the encoder asserts the same value on both.",
        "written_by_region": {r: (L[r]["owned_set"]+L[r]["owned_clear"]+L[r]["invented"]+L[r]["wrong_clear"]) for r in L},
    }
    json.dump(ir, open(os.path.join(RESID, "physical_config_ir.json"), "w"), indent=1)
    feats = decoded["fabric"]["features"]
    def flen(v): return {k:(len(x) if hasattr(x,"__len__") else x) for k,x in v.items()} if isinstance(v,dict) else len(v)
    netlist = {
        "representation": "lifted_netlist",
        "desc": "structured feature model that PROJECTS onto the physical_config_ir; aliased/dead/default settings preserved in the IR carry no unique netlist meaning.",
        "feature_counts": {k: flen(v) for k, v in feats.items()},
    }
    json.dump(netlist, open(os.path.join(RESID, "lifted_netlist.json"), "w"), indent=1)

    # ===================================================================== report
    report = {
        "step": "[0-LEDGER]",
        "target": UM.TARGET,
        "device": "EP4CE10 / cycloneive1 / Quartus 21.1.0 Build 842",
        "policy": "from-blank, decode-or-refuse, no-implicit-zero-as-owned; two-background write-mask.",
        "note_supersedes": ("An earlier set-bit snapshot predates the asmdb_calc_reloc "
                            "(calculate_bits relocation) + cfgres wiring now live in the "
                            "encoder; this ledger measures the CURRENT model."),
        "geometry": {"image_bytes": size, "total_positions": total_positions,
                     "total_set_bits": total_set},

        "TERNARY_LEDGER_all_positions": {
            "KNOWN":            KNOWN,
            "DERIVED_emitted":  DERIVED_EMIT,
            "DERIVED_pending":  DERIVED_PENDING,
            "OPAQUE_PRESERVED": OPAQUE_PRESERVED,
            "DONTCARE_PROVEN":  DONTCARE_PROVEN,
            "UNKNOWN_SET":      UNKNOWN_SET,
            "UNKNOWN_CLEAR":    UNKNOWN_CLEAR,
            "INVALID_REFUSE":   INVALID,
            "INVENTED":         INVENTED,
            "WRONG_CLEAR":      WRONG_CLEAR,
            "_sum":             (KNOWN+DERIVED_EMIT+DERIVED_PENDING+OPAQUE_PRESERVED
                                 +DONTCARE_PROVEN+UNKNOWN_SET+UNKNOWN_CLEAR+INVALID
                                 +INVENTED+WRONG_CLEAR),
        },
        "OWNERSHIP": {
            "owned_positions": owned_positions,
            "total_positions": total_positions,
            "ownership_pct_all_positions_STRICT": round(100.0*owned_positions/total_positions, 4),
            "reachable_if_derived_pending_closes": round(100.0*(owned_positions+DERIVED_PENDING)/total_positions, 4),
            "invented_positions": INVENTED,
            "invented_must_be_zero": True,
        },
        "SET_BIT_CONTINUITY_VIEW": {
            "note": "prior campaign metric (SET bits only), for reconciliation.",
            "total_set_bits": total_set,
            "owned_set_bits": owned_set_bits,
            "residual_set_bits": setbit_residual,
            "ownership_pct_set_bits": round(100.0*owned_set_bits/total_set, 4),
            "breakdown": {"UNKNOWN_SET(EU)": UNKNOWN_SET,
                          "DERIVED_pending(crc.data)": DERIVED_PENDING,
                          "INVALID_REFUSE(crc.header)": INVALID},
        },
        "residual_by_class": {
            "explicit_unknown_cram_set_bits": UNKNOWN_SET,
            "by_region": dict(collections.Counter(e[4] for e in eu_cram)),
            "classes_ranked": [
                {"class": c, "cells": n,
                 "share_pct": round(100.0*n/max(UNKNOWN_SET,1), 2),
                 "by_region": dict(by_cause_region[c]),
                 "manifest": os.path.join("residual", c.replace("/","_")+".json")}
                for c, n in by_cause.most_common()
            ],
            "crc.data_DERIVED_PENDING": DERIVED_PENDING,
            "crc.header_INVALID_REFUSE": INVALID,
        },
        "per_region_detail": {r: dict(L[r]) for r in sorted(L)},
        "invariants": {
            "ternary_sum_eq_total_positions":
                (KNOWN+DERIVED_EMIT+DERIVED_PENDING+OPAQUE_PRESERVED+DONTCARE_PROVEN
                 +UNKNOWN_SET+UNKNOWN_CLEAR+INVALID+INVENTED+WRONG_CLEAR) == total_positions,
            "invented_is_zero": INVENTED == 0,
            "wrong_clear_is_zero": WRONG_CLEAR == 0,
            "setbit_owned_plus_residual_eq_total_set":
                (owned_set_bits + setbit_residual) == total_set,
            "class_sum_eq_eu": sum(by_cause.values()) == UNKNOWN_SET,
            "written_eq_owned_plus_invented_plus_wrongclear":
                written_positions == (KNOWN + DERIVED_EMIT + INVENTED + WRONG_CLEAR),
        },
        "artifacts": {
            "per_class_manifests": sorted(os.path.join("residual", f) for f in os.listdir(RESID)),
        },
    }
    json.dump(report, open(os.path.join(HERE, "ledger_report.json"), "w"), indent=2, default=str)
    print(json.dumps({k: report[k] for k in
          ("TERNARY_LEDGER_all_positions","OWNERSHIP","SET_BIT_CONTINUITY_VIEW",
           "residual_by_class","invariants")}, indent=2, default=str))
    return report


if __name__ == "__main__":
    main()
