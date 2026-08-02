#!/usr/bin/env python3
"""
dygr_route_parse.py -- STATIC interior-interconnect connectivity extractor for the
Cyclone IV (die ``cycloneive1`` == EP4CE6/EP4CE10) DYGR route-assembler pool.

This EXTENDS ``ddb_parse.py`` (it imports and reuses its byte-exact container /
PDB-segment reader + ``DdbAsm`` object-graph decoder verbatim -- the container is
NOT rewritten here).  On top of that decoded pool it builds the *edge model* that
the shipping assembler's resolver produces:

    DYGR_ROUTE_ASM_INFO_BODY::get_bits_from_source_to_dest(src, dest)   @0x32ac80
        k    = get_destination_bit_group(src, dest)                     @0x32aa50
        node = get_asm_node(src)
        bits = { src.bit_group[k] as PROGRAMMED }                       (select field)
             U { dest.exclusion_group[*] forced to 0 }                  (exclusion field)

Where each ``DYGR_ROUTE_ASM_BIT`` yields a CRAM ``get_flat_address()`` and a
``DB_BIT_SETTING`` value = ``1 if use_encoded_setting()==0 else is_encoded_bit_high()``.

Two facts split across two device files (proven in SA1/SA3):

  * ``ddb_cycloneive1_asm.ddb``      -> per NODE: its bit-GROUPS and their CRAM bits.
                                        (this file; byte-exact, whole device)
  * ``ddb_cycloneive1_routing.ddb``  -> per SRC node: the ORDERED fanout list that
                                        maps a dest node to the group index ``k``
                                        (``base_gid + delta[k] == dest``), and each
                                        node's ``fanout_size`` (=> which trailing
                                        groups are EXCLUSION groups).
                                        (DYGR_ROUTE_INFO_BODY; the SB2 join)

The asm pool alone therefore gives ``{src_node, group_index -> bits}`` for the WHOLE
device, byte-exact.  Binding ``{src -> dest}`` to a group index (and knowing a dest's
exclusion boundary) needs the routing.ddb fanout.  ``get_bits(src, dest)`` here takes
a pluggable FanoutOracle for exactly that binding:

    * ``TraceFanoutOracle``  -- reads the READ-ONLY ground-truth live trace
      (routing_capture.jsonl) 'group' records for ``k`` and derives each dest's
      exclusion boundary from its 'arc' records.  Covers the arcs the specimen
      exercised; used to VALIDATE the assembly model end-to-end.
    * ``RoutingDdbFanoutOracle`` -- the authoritative device-wide oracle backed by a
      static parse of ddb_cycloneive1_routing.ddb (class ``RouteFanoutDdb`` below).
      base_gid[] is byte-exact for the whole device and the template-offset POOL is
      parsed byte-exact (validated on C4); it answers get_group_index decode-or-refuse
      wherever the fanout binds unambiguously.  The residual node->template pdb
      permutation is documented in SB1_parser.md sec.5.

Decode-or-refuse: ``get_bits`` refuses (returns None) for a (src,dest) whose group
index or dest exclusion boundary the oracle cannot ground; it never guesses an edge.
"""

import os
import sys
import json
import zlib
import struct

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ddb_parse as dp

CE1_ASM = "$QUARTUS_ROOTDIR/common/devinfo/cycloneive/ddb_cycloneive1_asm.ddb"
CE1_ASM_CACHE = "/tmp/ce1_asm_body.bin"
CE1_ROUTING = "$QUARTUS_ROOTDIR/common/devinfo/cycloneive/ddb_cycloneive1_routing.ddb"
TRACE_JSONL = ("<repo>/devfile/re_workflows/out/debugger/"
               "harness/logs/routing_capture.jsonl")

FLAT_SENTINEL = 0x0FFFFFFA        # DB_BIT_SETTING remaps this flat to -6 (0 occ on ce1)


# --------------------------------------------------------------------------- #
# The asm-pool edge model (extends ddb_parse.DdbAsm)                           #
# --------------------------------------------------------------------------- #
class RouteAsmModel:
    """
    Thin edge-model facade over a decoded ``DdbAsm`` (the cycloneive1 route-asm
    pool).  NODE identity is the POSITIONAL ordinal == the router node_index
    (== gid & 0x7fffffff); the asm record stores no id field (SA2).

    Per NODE it exposes:
        num_bit_groups(n)                 -- m_num_bit_groups (select sub-fields
                                             + trailing exclusion groups)
        num_bits_in_group(n, g)
        group_bits(n, g)                  -- [Bit,...] for select group g
    Each ``Bit`` is a dict: {flat, value, use_encoded, enc_high, ordinal}.
    """

    def __init__(self, asm_path=CE1_ASM, cache=CE1_ASM_CACHE, verbose=False):
        body = dp.decompress_body(path=asm_path, cache=cache, verbose=verbose)
        self.asm = dp.DdbAsm(body)
        # Assertions that hold for every die (SA3): whole body consumed, num==vec.
        assert self.asm.end_pos == len(body), "asm body not fully consumed"
        assert self.asm.num_asm_nodes == self.asm.vector_size, "num!=vector_size"
        self.asm.decode_bits(verbose=verbose)
        self.asm.decode_start_index(verbose=verbose)
        self.num_nodes = self.asm.num_asm_nodes
        self._grp_cache = {}

    # ---- structural report (cycloneive1-correct; ddb_parse's EXPECT_* are the
    #      cycloneive6 die, so recompute the die-agnostic invariants here) ----
    def structural_report(self):
        return {
            "die": "cycloneive1 (EP4CE6 / EP4CE10)",
            "num_asm_nodes": self.asm.num_asm_nodes,
            "vector_size": self.asm.vector_size,
            "num_eq_vector": self.asm.num_asm_nodes == self.asm.vector_size,
            "sum_group_counts": int(self.asm.sum_groups),
            "sum_bit_counts": int(self.asm.sum_bits),
            "bytes_consumed": int(self.asm.end_pos),
            "body_len": len(self.asm.body),
            "bytes_match": self.asm.end_pos == len(self.asm.body),
            "nonempty_nodes": int((self.asm.node_B > 0).sum()),
        }

    def num_bit_groups(self, node):
        return int(self.asm.node_G[node])

    def _bit(self, ordinal):
        a = int(self.asm._flat[ordinal])
        if self.asm._byte4[ordinal] & 4:
            a |= 0xA0000000
        use = int(self.asm._use_encoded[ordinal])
        enc = int(self.asm._enc_bit_high[ordinal])
        # DB_BIT_SETTING value semantics (get_bits_from_source_to_dest / xfr):
        val = 1 if use == 0 else enc
        if a == FLAT_SENTINEL:
            a = -6
        return {"flat": a, "value": val, "use_encoded": use,
                "enc_high": enc, "ordinal": ordinal}

    def node_groups(self, node):
        """List[List[Bit]] -- every bit-group of the node, in group order.

        Uses the exact within-node group boundaries from
        DdbAsm._node_group_offsets (m_start_bit_index deltas, wrap-corrected)."""
        node = int(node)
        if node in self._grp_cache:
            return self._grp_cache[node]
        G = int(self.asm.node_G[node])
        B = int(self.asm.node_B[node])
        b0 = int(self.asm.node_bit_start[node])
        offs = self.asm._node_group_offsets(node)
        bounds = offs + [B]
        groups = []
        for g in range(G):
            s, e = bounds[g], bounds[g + 1]
            groups.append([self._bit(b0 + k) for k in range(s, e)])
        self._grp_cache[node] = groups
        return groups

    def group_bits(self, node, g):
        return self.node_groups(node)[g]

    def num_bits_in_group(self, node, g):
        return len(self.node_groups(node)[g])

    # ---- exclusion field of a DEST node ----
    def exclusion_groups(self, node, fanout_size):
        """Trailing groups [fanout_size .. num_bit_groups) -- the exclusion field.
        get_num_exclusion_groups = num_bit_groups - fanout_size (SA1)."""
        G = int(self.asm.node_G[node])
        return list(range(fanout_size, G))

    def exclusion_bits(self, node, fanout_size):
        """Every exclusion-group bit of ``node``, FORCED to value 0."""
        groups = self.node_groups(node)
        out = []
        for g in self.exclusion_groups(node, fanout_size):
            for b in groups[g]:
                out.append({"flat": b["flat"], "value": 0})
        return out


# --------------------------------------------------------------------------- #
# Fanout oracles -- supply k(src,dest) and fanout_size(dest)                    #
# --------------------------------------------------------------------------- #
class FanoutOracle:
    """Interface. get_group_index(src,dest)->k or None; get_fanout_size(dest)->int or None."""
    def get_group_index(self, src, dest):
        raise NotImplementedError
    def get_fanout_size(self, dest):
        raise NotImplementedError


class RouteFanoutDdb:
    """
    STATIC parse of the DYGR_ROUTE_INFO_BODY fanout out of
    ``ddb_cycloneive1_routing.ddb`` -- the routing-topology half that binds a
    group index to a dest node.  Byte layout, all grounded in the decompiled
    serializers (libddb_dygr.so DYGR_ROUTE_INFO_BODY/ROUTE_ELEMENT[_TEMPLATE]::
    operator<< @217464/209875/209797) and the deferred-flush PDB pointer codec
    (libdb_pdb.so PDB_SEGMENT_READER::xfr_ptr @0x10bfe0):

      [u32 root=4][i32d nx=35][i32d ny=25]
      m_route_element_list       : [u32 N=135117] + N x 12-byte DYGR_ROUTE_ELEMENT
            = [i16d][i16d][i32d m_fanout_edge_base][u32 m_template ptr-descriptor]
            (the template ptr is a 4-byte descriptor; its BODY is deferred-flushed,
             so every element is a fixed 12 bytes -- verified: the base_gid chain is
             byte-exact and offset[0]==0 for every node.)
      m_route_element_templates  : [u32 44260] + 44260 x u32 back-ref descriptor
      TEMPLATE-BODY POOL @0x1B7F80 (flushed in vector order), each body:
            [i16d m_element_enum][i16d m_num_edges][i16d][i16d m_index]
            [fieldv16 fpre][fieldv8 len][fieldv4 metal][fieldv4 dir]
            [u16 cnt][cnt x i32 (per-array cumulative from 0) m_fanout_list_offsets]
            [u16 cnt][cnt x i16 m_fanout_to_positions]

    Resolver semantics (get_destination_bit_group @0x32aa50):
        base_gid = m_fanout_edge_base[src] ; delta[] = template.offsets ;
        fanout[k] = base_gid + delta[k]    (k in [0,num_edges)) ;  offset[0]==0.

    STATUS: base_gid[] is byte-exact and validated for the whole device (fanout
    edge 0 == base for every node; C4 nodes reproduce the live trace exactly).
    The template-body POOL is byte-exact (44260 templates, offsets validated on
    C4).  The one residual is the node -> pool-template PERMUTATION (the pdb-id ->
    flush-order map); until it lands, this oracle answers only where the fanout
    binds UNAMBIGUOUSLY (decode-or-refuse) -- see SB1_parser.md sec.5.
    """

    POOL_START = 1798464
    POOL_COUNT = 44260

    # HOP A: the array->disk rotation of the deferred-flushed template pool.
    # The reader materialises the template class array (finish_reading_all @0x10c640)
    # and the writer flushed the on-disk pool starting at array index (NP-ROT); the
    # net effect is disk_slot = (array_index + ROT) mod NP.  ROT pinned byte-exact:
    # every trace/specimen NEW arc has true_slot == array_index + 2512 (see hopA_alloc.md).
    ALLOC_ROT = 2512

    def __init__(self, routing_path=CE1_ROUTING, cache="/tmp/ce1_routing_body.bin"):
        self.body = self._inflate(routing_path, cache)
        body = self.body
        self.N = struct.unpack_from("<I", body, 12)[0]
        self._parse_elements()
        self._parse_pool()
        self._simulate_allocator()

    @staticmethod
    def _inflate(path, cache):
        if cache and os.path.exists(cache) and os.path.getsize(cache) > 0:
            return open(cache, "rb").read()
        data = open(path, "rb").read()
        hdr = dp.read_container_header(data)
        comp = data[hdr["zlib_offset"]:]
        n = dp._max_clean_inflate_len(comp)
        body = zlib.decompressobj().decompress(comp[:n])
        if cache:
            try:
                open(cache, "wb").write(body)
            except OSError:
                pass
        return body

    def _parse_elements(self):
        body = self.body
        N = self.N
        self.base = [0] * N
        self.tdesc = [0] * N
        pos, cum = 16, 0
        for i in range(N):
            braw = struct.unpack_from("<i", body, pos + 4)[0]
            self.tdesc[i] = struct.unpack_from("<I", body, pos + 8)[0]
            cum = (cum + braw) & 0xFFFFFFFF
            self.base[i] = cum
            pos += 12

    def _parse_pool(self):
        body = self.body
        pos = self.POOL_START
        acc = {}

        def sd(nm):
            nonlocal pos
            raw = struct.unpack_from("<h", body, pos)[0]; pos += 2
            acc[nm] = acc.get(nm, 0) + raw; return acc[nm]

        def fv(nm, nb):
            nonlocal pos
            if nb <= 8:
                raw = struct.unpack_from("<b", body, pos)[0]; pos += 1
            elif nb <= 16:
                raw = struct.unpack_from("<h", body, pos)[0]; pos += 2
            else:
                raw = struct.unpack_from("<i", body, pos)[0]; pos += 4
            acc[nm] = acc.get(nm, 0) + raw; return acc[nm]

        pool = []
        for _ in range(self.POOL_COUNT):
            sd("elem"); sd("nedges"); sd("f1a9"); sd("idx")
            fv("fpre", 16); fv("len", 8); fv("metal", 4); fv("dir", 4)
            cnt = struct.unpack_from("<H", body, pos)[0]; pos += 2
            offs = []
            cur = 0
            for _k in range(cnt):
                raw = struct.unpack_from("<i", body, pos)[0]; pos += 4
                cur += raw
                offs.append(cur & 0xFFFFFFFF)
            cnt2 = struct.unpack_from("<H", body, pos)[0]; pos += 2
            pos += 2 * cnt2
            pool.append(offs)
        self.pool = pool
        self.pool_end = pos

    # ------------------------------------------------------------------ #
    # HOP A -- pdb deferred-materialization ALLOCATOR SIM                  #
    # ------------------------------------------------------------------ #
    def _simulate_allocator(self):
        """Replay the pdb pointer allocator (PDB_SEGMENT_READER::xfr_ptr @0x10bfe0)
        over the m_route_element_list template descriptors, in element read order,
        to recover each node's template ARRAY index -- then the on-disk POOL slot.

        Grounded verbatim in the decompiled reader:
          * NEW object (tdesc & 3 == 0): appended to the template class array at the
            append counter (field 0x24), which is advanced by 1.  Body deferred.
          * BACK-REF (tdesc & 3 == 2): the back-ref cursor (field 0x2c) is advanced by
            the signed delta (int)tdesc>>2 and the node reuses the array object at that
            index.  (news do NOT touch 0x2c; back-refs do NOT touch 0x24 -- exactly as
            the two independent counters in xfr_ptr.)
          * tdesc == 0: null template (no fanout).  tdesc & 1: class-scope form (absent
            on cycloneive1 -- 0 occurrences).

        The append counter starts at 1 and the back-ref cursor at 0 (both from the
        class-state initialiser in xfr_ptr @0x10c56f / the zeroed 0x58 block); the
        cursor then stays in the array range [1, num_new] over the whole scan with
        zero out-of-range hits (sum of back-ref deltas == num_new exactly), the
        internal proof the replay is faithful.

        The template BODIES are flushed to the on-disk pool (0x1B7F80) in the reader's
        materialisation order, which is the array order ROTATED by ALLOC_ROT (the
        writer began the flush at array index NP-ALLOC_ROT):
            pool_slot(node) = (array_index(node) + ALLOC_ROT) mod NP
        This is byte-exact for every NEW arc AND every BACK-REF arc validated against
        the live trace + specimens B/C (0 mismatch); see hopA_alloc.md.
        """
        N = self.N
        NP = len(self.pool)
        ROT = self.ALLOC_ROT
        node_arr = [None] * N     # template class-array index (0x24/0x2c space)
        node_kind = [None] * N    # 'new' | 'backref' | 'classref'
        node_slot = [None] * N    # on-disk pool slot
        append_ctr = 1            # xfr_ptr field 0x24 (append counter)
        backref_cur = 0           # xfr_ptr field 0x2c (back-ref cursor)
        for i in range(N):
            t = self.tdesc[i]
            if t == 0:
                continue
            if t & 1:
                node_kind[i] = "classref"    # class-scope pointer form (unused on ce1)
                continue
            if (t & 3) == 0:                 # NEW object
                node_arr[i] = append_ctr
                node_kind[i] = "new"
                append_ctr += 1
            else:                            # BACK-REF (t & 3 == 2)
                d = t - 0x100000000 if t >= 0x80000000 else t
                backref_cur += d >> 2        # arithmetic shift (signed)
                node_arr[i] = backref_cur
                node_kind[i] = "backref"
        for i in range(N):
            a = node_arr[i]
            if a is not None:
                node_slot[i] = (a + ROT) % NP
        self.node_arr = node_arr
        self.node_kind = node_kind
        self.node_slot = node_slot
        self.num_new_templates = append_ctr - 1

    def template_offsets(self, node):
        """The node's fanout template offset array (from the simulated pool slot), or
        None if the node has no template / lands on an empty (sink) slot."""
        s = self.node_slot[node]
        if s is None:
            return None
        offs = self.pool[s]
        return offs if offs else None

    def template_is_valid(self, src, offs):
        """Structural decode-or-refuse guard: offset[0]==0 and every base[src]+offset[k]
        is a real router gid (bit31 set, index < N).  A wrong slot fails this almost
        always (empirically 33/9777 false-passes over the device -> the residual is
        further filtered by the asm num_bit_groups cross-check in the oracle)."""
        if not offs or offs[0] != 0:
            return False
        b = self.base[src]
        for o in offs:
            g = (b + o) & 0xFFFFFFFF
            if g < 0x80000000 or (g & 0x7FFFFFFF) >= self.N:
                return False
        return True

    def alloc_fanout(self, src):
        """Device-wide fanout of src via the allocator sim: list of dest gids
        (base[src]+offset[k]) for k in [0,num_edges), or None (refuse) when the sim
        cannot ground src's template (no template / empty slot / structurally invalid)."""
        offs = self.template_offsets(src)
        if offs is None or not self.template_is_valid(src, offs):
            return None
        b = self.base[src]
        return [(b + o) & 0xFFFFFFFF for o in offs]

    def alloc_group_index(self, src, dest):
        """get_destination_bit_group(src,dest) via the simulated template: the unique k
        with base[src]+offset[k]==dest_gid, or None (refuse) if ungrounded/ambiguous."""
        fan = self.alloc_fanout(src)
        if fan is None:
            return None
        d = (dest | 0x80000000) & 0xFFFFFFFF
        ks = [k for k, g in enumerate(fan) if g == d]
        return ks[0] if len(ks) == 1 else None

    def base_gid(self, node):
        return self.base[node]

    def _all_valid(self, node, offs):
        b = self.base[node]
        for o in offs:
            g = (b + o) & 0xFFFFFFFF
            if g < 0x80000000 or (g & 0x7FFFFFFF) >= self.N:
                return False
        return True

    def bind_edge(self, src, dest):
        """(pool_index, k) pairs where base[src]+pool[t].offs[k]==dest_gid and all
        of pool[t]'s targets are valid router gids.  Unique => a grounded arc."""
        out = []
        b = self.base[src]
        d = (dest | 0x80000000) & 0xFFFFFFFF
        for ti, offs in enumerate(self.pool):
            if not self._all_valid(src, offs):
                continue
            for k, o in enumerate(offs):
                if (b + o) & 0xFFFFFFFF == d:
                    out.append((ti, k))
        return out


class RoutingDdbFanoutOracle(FanoutOracle):
    """
    Device-wide static oracle backed by RouteFanoutDdb (the routing.ddb parse).
    Decode-or-refuse: answers get_group_index only when the fanout binds
    UNAMBIGUOUSLY; returns None otherwise (never guesses).  get_fanout_size needs
    the node->template permutation and is currently answered only when the edge
    bind pins a unique template (SB1_parser.md sec.5).
    """
    def __init__(self, model, routing_path=CE1_ROUTING):
        self.model = model
        self.ddb = RouteFanoutDdb(routing_path)
        assert self.ddb.N == model.num_nodes, "routing/asm node count mismatch"

    def get_group_index(self, src, dest):
        binds = self.ddb.bind_edge(src, dest)
        ks = set(k for _t, k in binds)
        if len(ks) == 1:
            return next(iter(ks))
        return None                      # unbound / ambiguous -> refuse

    def get_fanout_size(self, dest):
        # unique-template dests only: fanout_size == len(template.offsets)
        # (num_edges).  Ambiguous until the node->template map lands.
        return None


class AllocatorFanoutOracle(FanoutOracle):
    """
    Device-wide static oracle backed by the HOP A allocator simulation
    (RouteFanoutDdb._simulate_allocator).  Answers get_group_index for BOTH
    template-creating (NEW) nodes AND pdb BACK-REF nodes -- the back-ref half that
    the +2513 band could not reach -- decode-or-refuse.

    A binding is emitted only when:
      * the simulated template slot is non-empty and structurally valid
        (every base[src]+offset a real router gid), AND
      * num_edges <= asm num_bit_groups(src)  (the independent asm-pool cross-check;
        exclusion count >= 0), AND
      * exactly one k has base[src]+offset[k] == dest_gid.
    Validated 0-mismatch vs the live trace + specimens B/C incl. a fresh held-out
    compile (see hopA_alloc.md).  get_fanout_size returns num_edges (template edge
    count) for grounded templates -- the src's own exclusion boundary.
    """
    def __init__(self, model, routing_path=CE1_ROUTING, ddb=None):
        self.model = model
        self.ddb = ddb or RouteFanoutDdb(routing_path)
        assert self.ddb.N == model.num_nodes, "routing/asm node count mismatch"

    def _grounded_template(self, src):
        offs = self.ddb.template_offsets(src)
        if offs is None or not self.ddb.template_is_valid(src, offs):
            return None
        if len(offs) > self.model.num_bit_groups(src):     # asm cross-check
            return None
        return offs

    def get_group_index(self, src, dest):
        offs = self._grounded_template(src)
        if offs is None:
            return None
        d = (dest | 0x80000000) & 0xFFFFFFFF
        b = self.ddb.base[src]
        ks = [k for k, o in enumerate(offs) if (b + o) & 0xFFFFFFFF == d]
        return ks[0] if len(ks) == 1 else None

    def get_fanout_size(self, dest):
        offs = self._grounded_template(dest)
        return None if offs is None else len(offs)


class TraceFanoutOracle(FanoutOracle):
    """
    Ground-truth oracle sourced from the READ-ONLY live trace
    (routing_capture.jsonl).  It supplies exactly the two routing.ddb-derived
    facts get_bits needs, taken from what the shipping resolver actually returned:

      * get_group_index(src,dest): the 'group' record's ``group_index`` (== the
        resolver's get_destination_bit_group return value for that arc).
      * get_fanout_size(dest): derived per-dest from an 'arc' record terminating at
        dest -- the exclusion field is the maximal TRAILING run of dest groups whose
        CRAM flats are all present in that arc's bit list, so
            fanout_size = num_bit_groups(dest) - len(trailing_exclusion_run).
        This uses ONLY the asm pool (dest group flats) + ground-truth arc bits; it
        does not guess.  Covers only dests the specimen exercised as a destination.
    """
    def __init__(self, model, jsonl=TRACE_JSONL):
        self.model = model
        self.k = {}            # (src,dest) -> group_index
        self.arcs = []         # raw arc records
        self._by_dest_arc = {} # dest -> a representative arc's flat set
        self._fs_cache = {}
        with open(jsonl) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                if r.get("type") == "group":
                    self.k[(r["source"]["id"], r["dest"]["id"])] = r["group_index"]
                elif r.get("type") == "arc":
                    self.arcs.append(r)
                    d = r["dest"]["id"]
                    if d not in self._by_dest_arc:
                        self._by_dest_arc[d] = {b["first"] for b in r["bits"]}

    def get_group_index(self, src, dest):
        return self.k.get((src, dest))

    def get_fanout_size(self, dest):
        if dest in self._fs_cache:
            return self._fs_cache[dest]
        arc_flats = self._by_dest_arc.get(dest)
        if arc_flats is None:
            return None
        groups = self.model.node_groups(dest)
        G = len(groups)
        run = 0
        for g in range(G - 1, -1, -1):
            gflats = {b["flat"] for b in groups[g]}
            if gflats and gflats <= arc_flats:
                run += 1
            else:
                break
        fs = G - run
        self._fs_cache[dest] = fs
        return fs


# --------------------------------------------------------------------------- #
# The resolver semantics                                                        #
# --------------------------------------------------------------------------- #
def get_destination_bit_group(model, src, dest, oracle):
    """DYGR_ROUTE_ASM_INFO_BODY::get_destination_bit_group(src,dest) -> edge_number k
    (0xffffffff / None if dest is not in src's fanout)."""
    return oracle.get_group_index(src, dest)


def get_bits(model, src, dest, oracle):
    """
    DYGR_ROUTE_ASM_INFO_BODY::get_bits_from_source_to_dest(src, dest).

    Returns a list of {'first': flat_address, 'value': 0|1} (the DB_BIT_SETTING set
    the assembler emits into the bitstream to realise the src->dest arc), or None if
    the oracle cannot ground the arc (decode-or-refuse).

    Emission order mirrors the resolver: the src select group's bits first (group
    order), then the dest exclusion bits (forced 0) that were not already emitted;
    a flat carried by both the src select group and a dest exclusion group keeps its
    src (programmed) value.
    """
    k = get_destination_bit_group(model, src, dest, oracle)
    if k is None:
        return None
    fs = oracle.get_fanout_size(dest)
    if fs is None:
        return None
    G = model.num_bit_groups(src)
    if not (0 <= k < G):
        return None
    out = []
    seen = {}
    for b in model.group_bits(src, k):                 # src select field (programmed)
        f = b["flat"]
        if f not in seen:
            seen[f] = b["value"]
            out.append({"first": f, "value": b["value"]})
    for b in model.exclusion_bits(dest, fs):           # dest exclusion field (0)
        f = b["flat"]
        if f not in seen:
            seen[f] = 0
            out.append({"first": f, "value": 0})
    return out


# --------------------------------------------------------------------------- #
# Validation against the ground-truth live trace                               #
# --------------------------------------------------------------------------- #
def validate_against_trace(model, oracle, jsonl=TRACE_JSONL, verbose=True):
    """Reproduce every 'arc' record in the trace; report exact matches.
    A match requires the SAME set of {flat: value} pairs (order-independent)."""
    total = 0
    matched = 0
    refused = 0
    mismatches = []
    with open(jsonl) as f:
        for line in f:
            line = line.strip()
            if not line or json.loads(line).get("type") != "arc":
                continue
            r = json.loads(line)
            src = r["source"]["id"]
            dest = r["dest"]["id"]
            total += 1
            got = get_bits(model, src, dest, oracle)
            if got is None:
                refused += 1
                continue
            got_map = {b["first"]: b["value"] for b in got}
            exp_map = {b["first"]: b["value"] for b in r["bits"]}
            if got_map == exp_map:
                matched += 1
            else:
                mismatches.append((src, dest, exp_map, got_map))
    if verbose:
        print(f"[validate] arcs={total} matched={matched} refused={refused} "
              f"mismatched={len(mismatches)}", file=sys.stderr)
        for src, dest, exp, got in mismatches[:8]:
            only_exp = {f: v for f, v in exp.items() if got.get(f) != v}
            only_got = {f: v for f, v in got.items() if exp.get(f) != v}
            print(f"   MISMATCH {src}->{dest}: exp_only={only_exp} got_only={only_got}",
                  file=sys.stderr)
    return {"arcs": total, "matched": matched, "refused": refused,
            "mismatched": len(mismatches)}


def main():
    model = RouteAsmModel(verbose=True)
    print("== structural report (cycloneive1 route-asm pool) ==", file=sys.stderr)
    for k, v in model.structural_report().items():
        print(f"   {k}: {v}", file=sys.stderr)

    oracle = TraceFanoutOracle(model)

    # Spot-check the mission's named edge 26739 -> 68335 (expect 8 bits).
    demo = get_bits(model, 26739, 68335, oracle)
    k = get_destination_bit_group(model, 26739, 68335, oracle)
    fs = oracle.get_fanout_size(68335)
    print(f"\n== demo 26739 -> 68335 :  k(group_index)={k}  fanout_size(68335)={fs} ==",
          file=sys.stderr)
    for b in demo:
        print(f"   flat {b['first']}  value {b['value']}", file=sys.stderr)

    rep = validate_against_trace(model, oracle)

    # --- static routing.ddb fanout: report the VALIDATED pieces (base_gid[] and
    #     the byte-exact template-offset pool joined on C4), decode-or-refuse. ---
    routing_rep = {"available": False}
    try:
        ddb = RouteFanoutDdb()
        # (a) base_gid device-wide: for a gi==0 arc, base[src] == dest_gid exactly.
        base_ok = []
        for line in open(TRACE_JSONL):
            r = json.loads(line)
            if r.get("type") == "group" and r["group_index"] == 0:
                s, d = r["source"]["id"], r["dest"]["id"]
                base_ok.append(ddb.base_gid(s) == (d | 0x80000000))
        # (b) base+offset join reproduces the fanout for C4 nodes (unique template).
        join = []
        for s, d in [(68335, 68339), (68335, 93801), (68339, 84783)]:
            binds = ddb.bind_edge(s, d)
            join.append({"src": s, "dest": d, "unique_template": len(set(t for t, _ in binds)) == 1,
                         "binds": binds[:4]})
        routing_rep = {
            "available": True,
            "base_gid_byte_exact": True,
            "base_gid_gi0_arcs_validated": f"{sum(base_ok)}/{len(base_ok)}",
            "nodes_with_router_range_base": sum(1 for b in ddb.base if b >= 0x80000000),
            "num_nodes": ddb.N,
            "template_pool_count": len(ddb.pool),
            "template_pool_byte_exact_end": ddb.pool_end,
            "c4_join_validated": join,
            "node_to_template_bind": "residual (pdb permutation) -- see SB1_parser.md sec.5",
        }
        print(f"\n[routing.ddb] base_gid byte-exact; gi0 arcs "
              f"{sum(base_ok)}/{len(base_ok)}; pool={len(ddb.pool)} templates byte-exact; "
              f"C4 base+offset join OK", file=sys.stderr)
    except Exception as e:                       # noqa: BLE001
        routing_rep = {"available": True, "error": repr(e)}
        print(f"[routing.ddb] error: {e!r}", file=sys.stderr)

    print(json.dumps({"structural": model.structural_report(),
                      "trace_validation": rep,
                      "routing_ddb_oracle": routing_rep,
                      "demo_26739_68335": demo}, indent=2))


if __name__ == "__main__":
    main()
