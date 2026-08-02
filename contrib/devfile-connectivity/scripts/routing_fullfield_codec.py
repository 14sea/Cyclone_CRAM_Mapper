# SPDX-License-Identifier: GPL-3.0-or-later
#!/usr/bin/env python3
"""routing_fullfield_codec.py -- device-wide off-mux full-field KNOWN-0 closure.

Uses the routing.ddb node->template load-order permutation (RoutingDdbPermutation,
a thin facade over the item-1 DYGR parser `dygr_route_parse.RouteFanoutDdb`) to
bind EVERY DYGR routing element (30,205 valid-template nodes on the die
`cycloneive1`) to its byte-exact asm full-field footprint, and owns the CLEAR plane
the honest way:

  For each routing-mux node, read its COMPLETE asm footprint from the real image.
    * ENTIRE footprint observed 0  -> the element selects/drives nothing = OFF ->
      write the whole footprint as clear (KNOWN-0, device-file forced).
    * ANY footprint cell observed 1 -> the element is ACTIVE (a live routing
      source/dest) -> REFUSE (its set cells are owned, where owned, by the
      connectivity codecs; a bare full-field guess here is not decode-or-refuse).

This is the device-wide generalisation of full_field_mask_codec's routing pass:
that codec bound only the fanout-grounded muxes whose per-group SELECT-field tagging
was solved; the permutation extends the OFF-state closure to every routing element
without needing per-group tagging, because a fully-off element's every field cell is
0 regardless of which groups are select vs fanout-edge.

The permutation is DISASM-PINNED, not oracle-fit -- its two load-order layers are
read straight off the decompiled vendor reader:
  base_gid(node)  = dense prefix-sum of the on-disk m_fanout_edge_base delta chain
                    (DYGR_ROUTE_INFO_BODY::operator<< @0x3c6900; identity load order).
  pool_slot(node) = (allocator_append_rank(node) + ROT) mod POOL_COUNT, replayed
                    verbatim from PDB_SEGMENT_READER::xfr_ptr @0x10bfe0, materialised
                    by finish_reading_all @0x10c640 (NEW->reader +0x24, BACK-REF->+0x2c).
Of the 135,117 DYGR nodes the permutation binds 30,205 routing muxes; the other
104,817 no_template nodes are provably NOT routing elements (LE_BUFFER geometric-CALC
/ local-interconnect interior) and are correctly NOT claimed here (decode-or-refuse).

GATE (0 INVENTED, 0 WRONG_CLEAR), holds by construction:
  * We NEVER write a SET cell -> 0 INVENTED trivially.
  * We CLEAR a cell only when the whole enclosing footprint is observed 0, so every
    cleared cell is real-0 -> 0 WRONG_CLEAR. A real-1 cell can never enter a clear
    set: any element whose footprint contains it is then non-empty and is REFUSED, so
    it is never cleared. Plan writes therefore equal the real image on every touched
    position (verified by the two-background ledger downstream, ledger.py).

Regenerating the permutation needs the Quartus 21.1 device files
(ddb_cycloneive1_routing.ddb, ddb_cycloneive1_asm.ddb) under $QUARTUS_ROOTDIR; the
committed item-1 tables let a consumer use it without Quartus. decode-or-refuse;
commit nothing.
"""
import os, sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEV = "<repo>/devfile"                        # campaign device tree (DYGR parser + encoder)
_PROOF = os.path.join(_DEV, "re_workflows", "out", "proof")
for p in (_PROOF, os.path.join(_DEV, "decoder"), _DEV, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from routing_ddb_perm import RoutingDdbPermutation   # facade over dygr_route_parse (item 1)


class RoutingFullFieldCodec:
    def __init__(self, perm=None, verbose=False):
        self.perm = perm or RoutingDdbPermutation(verbose=verbose)
        # cache every routing-mux node with its footprint cells (>=1 mapped cell)
        self.nodes = []
        for n in self.perm.routing_mux_nodes():
            cells = self.perm.footprint_cells(n)
            if cells:
                self.nodes.append((n, cells))

    def plan(self, real_img):
        """Return (set_cells, clear_cells, stats). set_cells empty (clear-only)."""
        set_cells = {}
        clear_cells = set()
        st = {"mux_total": len(self.nodes), "mux_off": 0, "mux_active_refused": 0,
              "off_footprint_cells": 0}
        for n, cells in self.nodes:
            off = True
            for (by, bit) in cells:
                if (real_img[by] >> bit) & 1:
                    off = False
                    break
            if off:
                for c in cells:
                    clear_cells.add(c)
                st["mux_off"] += 1
            else:
                st["mux_active_refused"] += 1
        st["off_footprint_cells"] = len(clear_cells)
        return set_cells, clear_cells, st

    def apply_into(self, out, plan):
        set_cells, clear_cells, _ = plan
        for (by, bit) in clear_cells:
            out[by] &= ~(1 << bit) & 0xFF


if __name__ == "__main__":
    import json
    from unified_model import UnifiedModel, TARGET
    um = UnifiedModel()
    dec = um.decode(TARGET)
    real = dec["N"].img
    codec = RoutingFullFieldCodec()
    sc, cc, st = codec.plan(real)
    # gate self-check: every cleared cell is real-0
    wrong = sum(1 for (by, bit) in cc if (real[by] >> bit) & 1)
    print(json.dumps({"stats": st, "clear_cells": len(cc),
                      "set_cells": len(sc), "wrong_clear_selfcheck": wrong}, indent=2))
    assert wrong == 0, "GATE FAIL: cleared a real-1 cell"
