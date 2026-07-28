#!/usr/bin/env python3
"""static_connectivity.py -- WHOLE-DEVICE interior-interconnect layer.

Source of truth: the STATIC DYGR route-asm connectivity table parsed directly out
of the Cyclone IV device file (ddb_cycloneive1_asm.ddb), emitted as
    re_workflows/out/dygr_static/dygr_connectivity.json
by the static device-file RE campaign (SB2) and validated bit-exact against three
independent Quartus compiles + the READ-ONLY live gdb intercept oracle (SC1/SC2:
0 mismatch on specimenA/B/C + the foreign target, 0 unmapped over 1.04M select bits).

Unlike connectivity_codec.py (which consumes the DYNAMIC per-arc trace, only the
handful of arcs a specimen exercised), this table enumerates EVERY device-wide
{src_node -> dest_node : bit_group : select_bits} interior edge the assembler can
resolve from the static pool -- 352,674 directed arcs over 20,461 source nodes.

DECODE-OR-REFUSE (never bluff an active arc):
  The table groups arcs by their destination MUX = (dest_node, bit_group).  For a
  target image, a mux is resolved by reading its select-bit cells and matching them
  against the enumerated arcs:
      UNUSED  -- every select bit reads 0            (mux carries no signal)
      DECODED -- the read pattern EXACTLY equals ONE enumerated arc's full select
                 pattern (all 1s AND all 0/exclusion bits) -> that arc is BOUND,
                 its source node is identified, bits round-trip bit-exact.
      AMBIG   -- matches >1 arc (patterns not distinct) -> refuse (never happens
                 on the validated targets; guarded anyway).
      REFUSED -- a non-zero pattern matching NO enumerated arc: the winning source
                 is out-of-band (a class the static +2513 map refuses -- LE_BUFFER,
                 low-ci C4/R4 channel-entry, pdb back-ref).  Honest coverage gap,
                 NOT a contradiction: no refused mux ever contradicts a bound bit.
  Any select bit that fails to map through flat_to_rbf -> the whole mux is refused.

COVERAGE (honest, declared): source-bind is partial.  Bound source classes are C4
(primary), R24/C16 (partial), R4 (poor).  LE_BUFFER (LUT output first hop),
LEIM/BLOCK_INPUT_MUX (LUT input port -- a DIFFERENT "blockmux" resolver), IO/CLK,
and pdb back-ref sources are REFUSED device-wide, so the LUT endpoints of a net
stay unbound.  The bits half (node->group->CRAM address) is byte-exact whole-device
for ALL classes.  Dest classes bound include LOCAL_INTERCONNECT (the LI wall taps
that were 0 in the pure-static campaign), C4, R4, C16, R24, and node-id GAP dests.
"""
import os
import json
import collections

_HERE = os.path.dirname(os.path.abspath(__file__))
# W3a: prefer the HOP-A-folded whole-device table (dygr_connectivity_full.json --
# NEW + pdb BACK-REF sources, 30,205 sources / 517,039 edges) when present; fall
# back to the band-only table otherwise.  Both share the same schema, so the codec
# consumes either unchanged.  Override with $DYGR_CONNECTIVITY_TABLE.
_FULL_TABLE = os.path.join(_HERE, "..", "re_workflows", "out", "own",
                           "dygr_connectivity_full.json")
_BAND_TABLE = os.path.join(_HERE, "..", "re_workflows", "out", "dygr_static",
                           "dygr_connectivity.json")
_DEFAULT_TABLE = (os.environ.get("DYGR_CONNECTIVITY_TABLE")
                  or (_FULL_TABLE if os.path.exists(_FULL_TABLE) else _BAND_TABLE))

# classes that terminate ON a LUT (the two hops this table refuses):
_LUT_OUTPUT_SRC = {"LE_BUFFER"}                     # a LUT drives a wire
_LUT_INPUT_DST = {"BLOCK_INPUT_MUX", "LEIM"}        # a wire feeds a LUT input
# dest that lands on a LAB's local interconnect (one blockmux hop from a LUT input):
_LAB_BOUNDARY_DST = {"LOCAL_INTERCONNECT"}


class StaticConnectivityCodec:
    """Whole-device DYGR route-asm connectivity, decode-or-refuse by dest mux."""

    def __init__(self, table_path=None, flat_to_rbf=None):
        self.path = os.path.abspath(table_path or _DEFAULT_TABLE)
        self.available = os.path.exists(self.path)
        self.flat_to_rbf = flat_to_rbf
        self.table = None
        self.mux = collections.defaultdict(list)   # (dest,bit_group) -> [edge...]
        self.n_edges = 0
        if self.available:
            self.table = json.load(open(self.path))
            for e in self.table["edges"]:
                self.mux[(e["dest"], e["bit_group"])].append(e)
            self.n_edges = len(self.table["edges"])

    # ------------------------------------------------------------------ #
    def _read(self, img, flat):
        rb = self.flat_to_rbf(flat)
        if rb is None:
            return None
        return (img[rb[0]] >> rb[1]) & 1

    def decode(self, N):
        """Return (bound_edges, claimed_cells, summary).  Decode-or-refuse per mux."""
        img = N.img
        bound, claimed = [], set()
        cls = collections.Counter()
        if not self.available:
            return bound, claimed, {"status": "no dygr_connectivity.json (static-only)",
                                    "arcs_source_bound": 0}
        for arcs in self.mux.values():
            flats = {b["flat"]: None for e in arcs for b in e["select_bits"]}
            read = {f: self._read(img, f) for f in flats}
            if any(v is None for v in read.values()):
                cls["HAS_UNMAPPED"] += 1
                continue
            if all(v == 0 for v in read.values()):
                cls["UNUSED"] += 1
                continue
            matches = [e for e in arcs
                       if all(read[b["flat"]] == b["value"] for b in e["select_bits"])]
            if len(matches) == 1:
                cls["DECODED"] += 1
                e = matches[0]
                cells = []
                for b in e["select_bits"]:
                    rb = self.flat_to_rbf(b["flat"])
                    cells.append((rb[0], rb[1]))
                claimed.update(cells)
                bound.append({
                    "src": e["src"], "dest": e["dest"],
                    "src_class": e["src_class"], "dest_class": e["dest_class"],
                    "bit_group": e["bit_group"],
                    "select_bits": e["select_bits"],
                    "cells": [list(c) for c in cells],
                })
            elif len(matches) > 1:
                cls["AMBIG"] += 1
            else:
                cls["REFUSED"] += 1
        summary = {
            "status": "LOCKED (whole-device DYGR route-asm table; per-mux "
                      "exact-codeword bind, decode-or-refuse)",
            "table": os.path.basename(self.path),
            "table_edges": self.n_edges,
            "table_muxes": len(self.mux),
            "mux_classification": dict(cls),
            "arcs_source_bound": cls["DECODED"],
            "muxes_unused": cls["UNUSED"],
            "muxes_refused": cls["REFUSED"] + cls["HAS_UNMAPPED"],
            "muxes_ambiguous": cls["AMBIG"],
            "li_leim_taps_bound": sum(1 for f in bound
                                      if f["dest_class"] in _LAB_BOUNDARY_DST),
            "lut_output_src_arcs": sum(1 for f in bound
                                       if f["src_class"] in _LUT_OUTPUT_SRC),
            "lut_input_dst_arcs": sum(1 for f in bound
                                      if f["dest_class"] in _LUT_INPUT_DST),
        }
        return bound, claimed, summary

    def encode_into(self, out, feat):
        """Re-emit a bound arc's select bits (round-trip)."""
        for b in feat["select_bits"]:
            rb = self.flat_to_rbf(b["flat"])
            if rb is None:
                continue
            byte, bit = rb
            if b["value"]:
                out[byte] |= (1 << bit)
            else:
                out[byte] &= ~(1 << bit)

    # ------------------------------------------------------------------ #
    @staticmethod
    def assemble_nets(bound):
        """Chain bound arcs (src_node -> dest_node) into weakly-connected router
        nets, and report where they reach the LUT fabric.

        Honest caveat: because LE_BUFFER (LUT output) sources and BLOCK_INPUT_MUX/
        LEIM (LUT input) dests are refused device-wide, these nets are INTERIOR
        router-wire nets; a net's LUT endpoints are the two unbound hops.  Nets that
        terminate on LOCAL_INTERCONNECT reach a LAB's local interconnect -- one
        blockmux hop short of a named LUT input."""
        fwd = collections.defaultdict(list)
        undirected = collections.defaultdict(set)
        nodes = set()
        srcset, dstset = set(), set()
        for f in bound:
            a, b = f["src"], f["dest"]
            fwd[a].append(f)
            undirected[a].add(b)
            undirected[b].add(a)
            nodes.add(a)
            nodes.add(b)
            srcset.add(a)
            dstset.add(b)
        # weakly-connected components
        seen, comps = set(), []
        for n in nodes:
            if n in seen:
                continue
            stack, comp = [n], []
            seen.add(n)
            while stack:
                x = stack.pop()
                comp.append(x)
                for y in undirected[x]:
                    if y not in seen:
                        seen.add(y)
                        stack.append(y)
            comps.append(comp)
        sizes = sorted((len(c) for c in comps), reverse=True)
        lab_taps = sorted({f["dest"] for f in bound
                           if f["dest_class"] in _LAB_BOUNDARY_DST})
        return {
            "n_router_nodes": len(nodes),
            "n_edges": len(bound),
            "n_components": len(comps),
            "component_size_hist": dict(collections.Counter(sizes)),
            "largest_components": sizes[:15],
            "n_components_ge3": sum(1 for s in sizes if s >= 3),
            "n_components_ge10": sum(1 for s in sizes if s >= 10),
            "n_junction_nodes": len(srcset & dstset),   # dest reappears as src (multi-hop)
            "n_root_nodes": len(srcset - dstset),
            "n_sink_nodes": len(dstset - srcset),
            "n_lab_boundary_taps": len(lab_taps),
        }
