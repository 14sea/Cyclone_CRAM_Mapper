#!/usr/bin/env python3
"""connectivity_codec.py -- node-resolved LI/LEIM + arc-source CONNECTIVITY layer.

Source of truth: the quartus_asm live gdb intercept (DYGR_ROUTE_ASM_INFO::
get_bits_from_source_to_dest) captured under re_workflows/out/debugger/ and
VERIFIED bit-exact (>=2/3 refutation lenses real; T1 proved the table is a device
table keyed by the assembler's global node ids, byte-identical across independent
compiles). This layer consumes the resulting connectivity_table.json.

It fills the exact gap the static routing codec leaves empty: binding a routing
arc's SOURCE (211/213 static arcs are select-only, source unbound) and the LI/LEIM
LUT-input taps (0 bound device-wide statically), so LUTs can be chained into nets.

DECODE-OR-REFUSE (never bluff an unbound edge):
  An edge (source_node -> dest_node) is BOUND on a target rbf ONLY when its FULL
  recorded codeword -- every {flat_addr, value} bit the assembler emitted for it --
  is present, bit-for-bit, in the target image (all bits must map through
  flat_to_rbf and match). Any mismatch, or any bit that fails to map, -> the arc is
  NOT bound (left UNKNOWN). This is the same exact-match reject guard the static
  codecs use; a coincidental partial hit can never bind an edge.

  Hardwired LEIM arcs (BLOCK_INPUT_MUX, select_code=0xffffffff) emit ZERO CRAM bits
  -- they carry no config-bit evidence -- so they are NOT bit-decodable and are
  reported as connectivity-only records, never asserted from an arbitrary bitstream.
"""
import os
import json

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_TABLE = os.path.join(_HERE, "..", "re_workflows", "out", "debugger",
                              "connectivity_table.json")

# LE-output / IO driver source classes = the roots a net can be traced back to.
_ROOT_SRC_CLASSES = {"LE_out", "IO_in"}
# dest classes that terminate on a LUT input (the wall taps).
_LUT_INPUT_DEST = {"LI", "LEIM"}


class ConnectivityCodec:
    """Binds source->dest routing edges by exact dest-mux codeword match, then
    chains bound edges into nets. Pure decode-or-refuse; emits only proven cells."""

    def __init__(self, table_path=None, flat_to_rbf=None):
        self.path = os.path.abspath(table_path or _DEFAULT_TABLE)
        self.available = os.path.exists(self.path)
        self.flat_to_rbf = flat_to_rbf
        self.table = None
        self._detectable = []      # arcs with n_bits>0 (bit-decodable)
        self._hardwired = []       # 0-bit connectivity-only records
        if self.available:
            self.table = json.load(open(self.path))
            for a in self.table["arcs"]:
                (self._detectable if a["n_bits"] > 0 else self._hardwired).append(a)

    # ------------------------------------------------------------------ #
    def _codeword_cells(self, arc):
        """[(byte,bit,value)] for every codeword bit that maps; None if any bit
        fails to map (then the arc is not verifiable -> refuse)."""
        out = []
        for flat, val in arc["codeword"]:
            rb = self.flat_to_rbf(flat)
            if rb is None:
                return None
            out.append((rb[0], rb[1], val))
        return out

    def _arc_matches(self, img, arc):
        """True iff every codeword bit is present bit-exact in img."""
        cells = self._codeword_cells(arc)
        if cells is None:
            return False, None
        for (byte, bit, val) in cells:
            if ((img[byte] >> bit) & 1) != val:
                return False, cells
        return True, cells

    # ------------------------------------------------------------------ #
    def decode(self, N):
        """Return (feats, claimed_cells, summary).
        feats: list of bound edges {source, dest, class, cells,...}.
        claimed_cells: set((byte,bit)) proven (the codeword cells of bound arcs)."""
        feats, claimed = [], set()
        if not self.available:
            return feats, claimed, {"status": "no connectivity_table.json", "bound": 0}
        img = N.img
        n_checked = n_bound = 0
        for arc in self._detectable:
            n_checked += 1
            ok, cells = self._arc_matches(img, arc)
            if not ok:
                continue
            n_bound += 1
            cellset = [(b, bt) for (b, bt, _v) in cells]
            claimed.update(cellset)
            feats.append({
                "dest_node": arc["dest_node"], "dest_wire": arc["dest_wire"],
                "dest_class": arc["dest_class"], "is_wall": arc["is_wall"],
                "source_node": arc["source_node"], "source_wire": arc["source_wire"],
                "source_class": arc["source_class"],
                "select_code": arc["select_code"], "n_bits": arc["n_bits"],
                "cells": [list(c) for c in cellset],
                "specimens": arc["specimens"],
            })
        summary = {
            "status": "LOCKED (node-keyed intercept table; exact-codeword bind, "
                      "decode-or-refuse)",
            "table": os.path.basename(self.path),
            "detectable_arcs_in_table": len(self._detectable),
            "hardwired_connectivity_only_arcs": len(self._hardwired),
            "arcs_checked": n_checked,
            "arcs_source_bound": n_bound,
            "li_leim_taps_bound": sum(1 for f in feats
                                      if f["dest_class"] in _LUT_INPUT_DEST),
        }
        return feats, claimed, summary

    def encode_into(self, out, feat):
        """Re-emit the bound edge's codeword cells (round-trip)."""
        # feat carries only cells+value via the arc; look the arc up by (src,dst).
        for arc in self._detectable:
            if (arc["source_node"] == feat["source_node"]
                    and arc["dest_node"] == feat["dest_node"]):
                for flat, val in arc["codeword"]:
                    rb = self.flat_to_rbf(flat)
                    if rb is None:
                        continue
                    byte, bit = rb
                    if val:
                        out[byte] |= (1 << bit)
                    else:
                        out[byte] &= ~(1 << bit)
                return

    # ------------------------------------------------------------------ #
    @staticmethod
    def assemble_nets(bound_feats):
        """Chain bound edges into nets. An edge is source_node -> dest_node.
        A net = a weakly-connected chain rooted at an LE_BUFFER / IO_DATAIN driver.
        Returns {"nets":[...], "n_nets", "n_lut_input_taps", "roots"...}."""
        # adjacency source_node -> [edges]
        fwd = {}
        nodes = {}
        for f in bound_feats:
            fwd.setdefault(f["source_node"], []).append(f)
            nodes[f["source_node"]] = f["source_wire"]
            nodes[f["dest_node"]] = f["dest_wire"]
        dest_set = {f["dest_node"] for f in bound_feats}
        # roots = a source that is never a dest (the driver end of a net)
        roots = [n for n in fwd if n not in dest_set]
        nets = []
        for root in roots:
            # DFS forward from root
            chain, seen, stack = [], set(), [root]
            taps = []
            while stack:
                nd = stack.pop()
                for e in fwd.get(nd, []):
                    ek = (e["source_node"], e["dest_node"])
                    if ek in seen:
                        continue
                    seen.add(ek)
                    chain.append(e)
                    if e["dest_class"] in _LUT_INPUT_DEST:
                        taps.append(e["dest_wire"])
                    stack.append(e["dest_node"])
            nets.append({
                "root_node": root, "root_wire": nodes.get(root),
                "root_class": (chain[0]["source_class"] if chain else None),
                "n_edges": len(chain),
                "lut_input_taps": taps,
                "n_lut_input_taps": len(taps),
                "edges": [f'{e["source_wire"]} -> {e["dest_wire"]}' for e in chain],
            })
        return {
            "n_nets": len(nets),
            "n_lut_input_taps": sum(nt["n_lut_input_taps"] for nt in nets),
            "nets": nets,
        }
