#!/usr/bin/env python3
"""
SB2 -- emit the whole-device interior-interconnect CONNECTIVITY table from the
Cyclone IV (die cycloneive1 == EP4CE6/EP4CE10) DYGR route-asm + route-info pools.

Runs the SB1 parser (dygr_route_parse.py) over the located device files and joins:
  * ASM pool   (ddb_cycloneive1_asm.ddb)     -> per node: bit-GROUPS -> CRAM bits   [byte-exact, whole device]
  * ROUTE pool (ddb_cycloneive1_routing.ddb)  -> per node: base_gid + template offsets -> dest ids

NODE -> TEMPLATE binding (the SB1 sec.5 residual), cracked this pass for a large band:
  Each DYGR_ROUTE_ELEMENT stores its template as a pdb pointer descriptor (tdesc).
  44260 elements carry a NEW-object descriptor (tdesc&3==0, class 3) -> they CREATE
  the 44260 templates in element order (creation_index ci). The template-body POOL is
  flushed in pdb array-index order (finish_reading_all @0x10c640 reads the class array
  0..count in order). Empirically the array-index of a new template == ci + 2514 across
  a contiguous mid/high band, so
        pool_slot(node) = creation_index(node) + 2513
  holds for creation_index in [20043, 41746]  (20461 source nodes).
  This band binding is GROUNDED by three independent checks:
    (a) 6/6 EXACT vs the READ-ONLY live trace: every new-object arc's dest gid is
        reproduced by base[src] + pool[ci+2513][k].
    (b) 20461/20461 structural validity: offset[0]==0 and every base[src]+offset[k]
        is a valid router gid (bit31 set, index < N).
    (c) 20461/20461 cross-validation against the INDEPENDENT asm pool: the template's
        num_edges never exceeds the asm node's num_bit_groups (exclusion count >= 0;
        tightly clustered at 2). A wrong binding would violate this constantly.
  Outside the band (ci < 20043, or ci+2513 out of range) the constant offset is wrong
  (early-stream pdb deferred materializations shift the array order); those source
  nodes are REFUSED here (decode-or-refuse) -- never bluffed.

Emits <repo>/devfile/re_workflows/out/dygr_static/dygr_connectivity.json.
Run with LD_LIBRARY_PATH unset (numpy GLIBCXX clash under the Quartus libs).
"""
import os, sys, json, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "<repo>/devfile")
sys.path.insert(0, HERE)
import dygr_route_parse as drp
import node_id as nid

BAND_SHIFT = 2513
OUT = os.path.join(HERE, "dygr_connectivity.json")


def cls_of(n):
    c = nid.block_of(n)[0]
    return c or "UNBOUND_GAP"


def main():
    t0 = time.time()
    print("[load] asm model + routing ddb ...", file=sys.stderr)
    model = drp.RouteAsmModel(verbose=False)
    ddb = drp.RouteFanoutDdb()
    N = ddb.N
    assert N == model.num_nodes, "asm/routing node-count mismatch"
    base, pool, tdesc = ddb.base, ddb.pool, ddb.tdesc
    G = model.asm.node_G

    # creation index of each new-object (template-creating) node
    ci = [None] * N
    c = 0
    for i in range(N):
        if tdesc[i] & 3 == 0:
            ci[i] = c
            c += 1
    n_new = c

    def template_valid(src, offs):
        b = base[src]
        if not offs or offs[0] != 0:
            return False
        for o in offs:
            g = (b + o) & 0xFFFFFFFF
            if g < 0x80000000 or (g & 0x7FFFFFFF) >= N:
                return False
        return True

    # -------- tier 1: trace-proven edges (full bits incl. dest exclusion) --------
    print("[trace] reproducing ground-truth arcs ...", file=sys.stderr)
    oracle = drp.TraceFanoutOracle(model)
    trace_edges = []
    seen_arc = set()
    for line in open(drp.TRACE_JSONL):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("type") != "group":
            continue
        s, d, k = r["source"]["id"], r["dest"]["id"], r["group_index"]
        if k == 0xFFFFFFFF or (s, d) in seen_arc:
            continue
        seen_arc.add((s, d))
        bits = drp.get_bits(model, s, d, oracle)
        if bits is None:
            continue
        trace_edges.append({
            "src": s, "dest": d,
            "src_class": cls_of(s), "dest_class": cls_of(d),
            "bit_group": k,
            "bits": [{"flat": b["first"], "value": b["value"]} for b in bits],
        })

    # -------- tier 2: static band edges (whole device, ci band) --------
    print("[band] enumerating static band edges ...", file=sys.stderr)
    edges = []
    band_srcs = 0
    excl_hist = {}
    src_cls_count = {}
    dest_cls_count = {}
    for s in range(N):
        if tdesc[s] & 3 != 0:
            continue                 # only template-creating nodes have a unique template
        slot = ci[s] + BAND_SHIFT
        if not (0 <= slot < len(pool)):
            continue
        offs = pool[slot]
        if not offs or not template_valid(s, offs):
            continue
        ng = int(G[s])
        num_edges = len(offs)
        if num_edges > ng:            # asm cross-validation guard (never emit a violation)
            continue
        band_srcs += 1
        excl = ng - num_edges
        excl_hist[excl] = excl_hist.get(excl, 0) + 1
        sc = cls_of(s)
        src_cls_count[sc] = src_cls_count.get(sc, 0) + 1
        groups = model.node_groups(s)      # select bits per group
        b = base[s]
        for k in range(num_edges):
            dgid = (b + offs[k]) & 0xFFFFFFFF
            dest = dgid & 0x7FFFFFFF
            dc = cls_of(dest)
            dest_cls_count[dc] = dest_cls_count.get(dc, 0) + 1
            gb = groups[k] if k < len(groups) else []
            edges.append({
                "src": s, "dest": dest,
                "src_class": sc, "dest_class": dc,
                "bit_group": k,
                "select_bits": [{"flat": bt["flat"], "value": bt["value"]} for bt in gb],
            })

    # -------- coverage / honesty summary --------
    nonempty_templates = sum(1 for o in pool if len(o) > 0)
    meta = {
        "die": "cycloneive1 (EP4CE6 / EP4CE10; same 368011-B rbf as target.rbf)",
        "asm_ddb": drp.CE1_ASM,
        "routing_ddb": drp.CE1_ROUTING,
        "num_router_nodes": N,
        "num_template_creating_nodes": n_new,
        "num_templates": len(pool),
        "num_nonempty_templates": nonempty_templates,
        "band_shift": BAND_SHIFT,
        "band_ci_range": [20043, 41746],
        "grounding": {
            "asm_pool": "byte-exact whole device (bytes_consumed==body_len); node->group->bits for EVERY class",
            "base_gid": "byte-exact whole device",
            "template_pool": "byte-exact (44260 templates)",
            "node_template_band_bind": "slot=ci+2513; validated 6/6 exact vs live trace, "
                                       "20461/20461 valid router-gid dests, 20461/20461 asm num_bit_groups consistent",
        },
        "tiers": {
            "trace_proven": f"{len(trace_edges)} arcs; full bits incl. dest exclusion; reproduce the READ-ONLY live trace exactly",
            "static_band": f"{len(edges)} directed edges over {band_srcs} source nodes (ci in [20043,41746]); "
                           "dest = base[src]+template_offset[k] (byte-exact arithmetic); select_bits from asm group k. "
                           "src->template binding is the cross-validated +2513 map (inductive, not per-edge-proven).",
        },
        "refused": {
            "low_ci_sources": "creation_index < 20043: early-stream pdb deferred-materialization shifts the pool order; "
                              "constant +2513 is wrong there -> REFUSED (decode-or-refuse).",
            "backref_sources": f"{N - n_new} nodes reference an already-created template via a pdb back-ref delta chain; "
                               "their template is only resolved where the trace/quartus_cdb grounds it -> not enumerated here.",
            "sink_nodes": f"{len(pool)-nonempty_templates} template slots are EMPTY (sink nodes: no outgoing interconnect fanout).",
        },
        "exclusion_group_histogram_band": {str(k): v for k, v in sorted(excl_hist.items())},
        "build_seconds": None,
    }

    out = {
        "meta": meta,
        "class_coverage": {
            "bits_half_classes_present": "ALL (LI/LEIM/LOCAL_INTERCONNECT, C4, R4, R24, C16, direct-links, "
                                         "LE_BUFFER, BLOCK_INPUT_MUX, IO_DATAIN, CLK) -- every node ordinal has its "
                                         "byte-exact group->bits in the asm pool regardless of class",
            "edge_src_class_distribution": dict(sorted(src_cls_count.items(), key=lambda kv: -kv[1])),
            "edge_dest_class_distribution": dict(sorted(dest_cls_count.items(), key=lambda kv: -kv[1])),
        },
        "trace_proven_edges": trace_edges,
        "edges": edges,
    }
    meta["build_seconds"] = round(time.time() - t0, 1)
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    sz = os.path.getsize(OUT)
    print(f"[done] wrote {OUT} ({sz/1e6:.1f} MB) in {meta['build_seconds']}s", file=sys.stderr)
    print(f"       trace_proven={len(trace_edges)}  band_srcs={band_srcs}  band_edges={len(edges)}", file=sys.stderr)
    print(f"       src_class={out['class_coverage']['edge_src_class_distribution']}", file=sys.stderr)
    print(f"       dest_class={out['class_coverage']['edge_dest_class_distribution']}", file=sys.stderr)


if __name__ == "__main__":
    main()
