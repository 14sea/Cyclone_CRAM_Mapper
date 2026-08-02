#!/usr/bin/env python3
"""
ddb_parse.py -- OFFLINE parser for Quartus Cyclone IV ``ddb_cycloneive6_asm.ddb``.

Phase 0 of the device-file plan of attack.  Reads the DYGR route-assembler
object graph (NODE / ushort-start-index / BIT pools) with NO live Quartus,
straight from the compressed .ddb, and implements ``get_flat_address`` and
``get_single_bit`` exactly as the shipping reader does.

Everything here is transcribed from the real decompiled bodies:

  libddb_dygr.so  (the DYGR classes + their operator<< serializers)
      DYGR_ROUTE_ASM_INFO_BODY::operator<<   @ 0x3bab70   (root)
      DYGR_ROUTE_ASM_NODE::operator<<        @ 0x3ba800
      DYGR_ROUTE_ASM_BIT::operator<<         @ 0x3ba940
      DYGR_ROUTE_ASM_NODE::get_single_bit    @ 0x328e90
      DYGR_ROUTE_ASM_BIT::get_flat_address   @ 0x329510
      PDB_STL_CLASS_THUNK<unsigned short>::serializer_fn @ 0x3c9b40  (-> xfr_short_delta)

  libdb_pdb.so    (the PDB_SEGMENT_READER byte codec)
      vtable PDB_SEGMENT_READER @ 0x1a9e0 :
        +0x20 xfr_new_array   +0x40 xfr_short_delta  +0x48 xfr_int_delta
        +0x80 xfr_short       +0x88 xfr_int          +0xd0 xfr_field_v
        +0xe0 serialize_begin +0xe8 serialize_end
      xfr_int_delta   @ 0x10ccd0 : read int32,  value = raw + prev_instance_field
      xfr_short_delta @ 0x10d4e0 : read int16,  value = raw + prev_instance_field
      xfr_field_v     @ 0x10d130 : nbits<=8 -> +1 signed byte, 9..16 -> +2, >16 -> +4
      xfr_new_array   @ 0x10d2c0 : count==0 -> read nothing; else loop count elem serializers
      serialize_begin/end        : bookkeeping only, consume NO stream bytes

Container framing (verified against the real file bytes):
  * 111-byte outer header; bytes[12:14] little-endian = 0x6f = 111 = offset of the
    zlib stream.  Header also carries the 56-byte "Version 21.1.0 Build 842 ..." string
    and the total file size (0x0089c7df) near offset 100.
  * one raw zlib stream (CMF/FLG = 0x78 0x01) from offset 111.  It is NOT terminated
    with a BFINAL block -- it ends on a Z_SYNC_FLUSH, then 123 trailer bytes follow.
    So we decompress the maximal prefix that inflates cleanly.

On-disk stream layout (little-endian, one linear cursor, deltas chain globally
across arrays / initialised to 0 for the first element of each class):

  [u32  root_ptr_descriptor        == 4          ]   # from pdb_read's xfr_ptr
  [i32d m_num_asm_nodes            ]   # xfr_int_delta, ref 0
  [u32  vector_size (== num_nodes) ]   # xfr_int
  for each of num_asm_nodes NODEs:               # DYGR_ROUTE_ASM_NODE::operator<<
      [i16d m_num_bit_groups ]                   # xfr_short_delta, ref prev node
      [i16d m_num_bits       ]                   # xfr_short_delta, ref prev node
      [u16  G = group count  ]                   # xfr_short  (== m_num_bit_groups)
      G  x [i16d start_index ]                    # xfr_short_delta, global chain
      [u16  B = bit count    ]                   # xfr_short  (== m_num_bits)
      B  x BIT:                                   # DYGR_ROUTE_ASM_BIT::operator<<
              [i32d d_flat_address]              # xfr_field_v nbits=31 -> 4 bytes, global chain
              [i8   d_use_encoded ]              # xfr_field_v nbits=1  -> 1 byte,  global chain
              [i8   d_enc_bit_high]              # ...
              [i8   d_strange_enc ]
              [i8   d_cff_bit     ]              # -> the 0xA0000000 region tag

The five in-memory BIT bytes are reconstructed exactly as the writer stores them:
      byte0..2 = flat_address[0..23]
      byte3    = (use_encoded<<7) | flat_address[24..30]
      byte4    = (cff<<2) | (strange<<1) | enc_bit_high        (bits 0..2)

get_flat_address(bit)  = (flat & 0x7fffffff) | (0xA0000000 if byte4&4 else 0)
get_single_bit(node,igroup,ibit) = BIT[ start_index[igroup] + ibit - 1 ]   (1-based within group)
"""

import os
import sys
import json
import time
import zlib
import struct

import numpy as np

DDB_PATH = "$QUARTUS_ROOTDIR/common/devinfo/cycloneive/ddb_cycloneive6_asm.ddb"
BODY_CACHE = "/tmp/asm_body.bin"

# Footer-TOC facts (derived, not stored as u32 in the body) -- used as structural anchors.
EXPECT_NUM_NODES = 1402672
EXPECT_NUM_USHORT = 13196014
EXPECT_NUM_BIT = 39692821
EXPECT_BODY_LEN = 355155984


# --------------------------------------------------------------------------- #
# Container: locate + decompress the zlib body                                 #
# --------------------------------------------------------------------------- #
def read_container_header(data):
    """Return dict describing the 111-byte outer header (all verified fields)."""
    hdr = {
        "field00": struct.unpack_from("<I", data, 0)[0],       # 0x14 = 20
        "field04": struct.unpack_from("<I", data, 4)[0],       # 0x10bad
        "zlib_offset": struct.unpack_from("<H", data, 12)[0],  # 0x6f = 111
        "version_len": struct.unpack_from("<I", data, 16)[0],  # 56
        "version": data[20:20 + struct.unpack_from("<I", data, 16)[0]].split(b"\x10")[0].decode("latin1"),
        "file_size_field": struct.unpack_from("<I", data, 100)[0] & 0x00FFFFFF,
        "total_file_size": len(data),
    }
    return hdr


def _max_clean_inflate_len(comp):
    """
    The zlib stream has no BFINAL terminator (ends on a Z_SYNC_FLUSH) and is
    followed by trailer bytes, so feeding the whole thing raises
    'invalid stored block lengths' once the decoder walks into the trailer.
    Binary-search the largest input prefix that inflates without raising.
    A prefix at/under the true stream end never raises (inflate just waits for
    more input); a longer prefix decodes trailer bytes as deflate and raises.
    """
    def ok(n):
        try:
            zlib.decompressobj().decompress(comp[:n])
            return True
        except zlib.error:
            return False

    lo, hi = 1, len(comp)
    # hi is known to fail; ensure lo passes
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if ok(mid):
            lo = mid
        else:
            hi = mid
    return lo


def decompress_body(path=DDB_PATH, cache=BODY_CACHE, verbose=True):
    """Decompress the .ddb container to the raw ~355 MB object-graph body."""
    if cache and os.path.exists(cache) and os.path.getsize(cache) == EXPECT_BODY_LEN:
        if verbose:
            print(f"[body] using cache {cache}", file=sys.stderr)
        return open(cache, "rb").read()

    data = open(path, "rb").read()
    hdr = read_container_header(data)
    zoff = hdr["zlib_offset"]
    if verbose:
        print(f"[body] container hdr: zlib@{zoff} ver={hdr['version']!r}", file=sys.stderr)
    comp = data[zoff:]
    n = _max_clean_inflate_len(comp)
    body = zlib.decompressobj().decompress(comp[:n])
    if verbose:
        print(f"[body] inflated {len(body)} bytes from {n} compressed "
              f"(stream ends at file offset {zoff + n})", file=sys.stderr)
    if cache:
        try:
            open(cache, "wb").write(body)
        except OSError:
            pass
    return body


# --------------------------------------------------------------------------- #
# Node-header pass (fast, sequential) -- validates structure & finds arrays    #
# --------------------------------------------------------------------------- #
class DdbAsm:
    """Parsed DYGR_ROUTE_ASM_INFO_BODY."""

    def __init__(self, body):
        self.body = body
        mv = memoryview(body)

        # --- root + INFO_BODY header (12 bytes) ---
        self.root_desc = struct.unpack_from("<I", body, 0)[0]
        self.num_asm_nodes = struct.unpack_from("<i", body, 4)[0]
        self.vector_size = struct.unpack_from("<I", body, 8)[0]
        assert self.root_desc == 4, f"unexpected root descriptor {self.root_desc}"
        assert self.num_asm_nodes == self.vector_size, "node count mismatch"

        n = self.num_asm_nodes
        # Per-node parsed fields
        self.node_G = np.empty(n, np.int32)   # group count (== m_num_bit_groups)
        self.node_B = np.empty(n, np.int32)   # bit count   (== m_num_bits)
        self.node_us_base = np.empty(n, np.int64)  # byte offset of start_index[] block
        self.node_bit_base = np.empty(n, np.int64)  # byte offset of BIT[] block

        upk_4h = struct.Struct("<4h").unpack_from
        pos = 12
        blen = len(body)
        sum_g = 0
        sum_b = 0
        node_G = self.node_G
        node_B = self.node_B
        us_base = self.node_us_base
        bit_base = self.node_bit_base
        for i in range(n):
            # 4 shorts: num_bit_groups(delta), num_bits(delta), G(plain), then us array
            ng_d, nb_d, G = struct.unpack_from("<3h", body, pos)
            G &= 0xFFFF
            pos += 6
            us_base[i] = pos
            pos += 2 * G
            B = struct.unpack_from("<H", body, pos)[0]
            pos += 2
            bit_base[i] = pos
            pos += 8 * B
            node_G[i] = G
            node_B[i] = B
            sum_g += G
            sum_b += B
        self.end_pos = pos
        self.sum_groups = sum_g
        self.sum_bits = sum_b

        # start_index[igroup] for get_single_bit needs the *flat* group index.
        # Global group ordinal at which each node's groups begin:
        self.node_group_start = np.concatenate(([0], np.cumsum(node_G, dtype=np.int64)[:-1]))
        self.node_bit_start = np.concatenate(([0], np.cumsum(node_B, dtype=np.int64)[:-1]))

        self._flat = None       # lazily decoded global BIT flat-address array
        self._byte4 = None      # lazily decoded global BIT byte[4] (flags) array
        self._start_index = None  # lazily decoded global ushort start-index array

    # ---- structural self-check ----
    def structural_report(self):
        return {
            "root_descriptor": self.root_desc,
            "num_asm_nodes": self.num_asm_nodes,
            "sum_group_counts": int(self.sum_groups),
            "sum_bit_counts": int(self.sum_bits),
            "bytes_consumed": int(self.end_pos),
            "body_len": len(self.body),
            "bytes_match": self.end_pos == len(self.body),
            "nodes_match": self.num_asm_nodes == EXPECT_NUM_NODES,
            "ushort_match": int(self.sum_groups) == EXPECT_NUM_USHORT,
            "bit_match": int(self.sum_bits) == EXPECT_NUM_BIT,
        }

    # ---- global delta-chain decode (numpy, one-time, ~heavy) ----
    def _gather_offsets(self, base_arr, count_arr, stride):
        """Vector of every element byte offset, in stream order."""
        nz = count_arr > 0
        bases = base_arr[nz]
        counts = count_arr[nz].astype(np.int64)
        if len(bases) == 0:
            return np.empty(0, np.int64)
        total = int(counts.sum())
        out = np.empty(total, np.int64)
        # ranges per node: base + stride*arange(count)
        ends = np.cumsum(counts)
        starts = ends - counts
        # per-element within-node ordinal via repeat trick
        seg = np.arange(total, dtype=np.int64) - np.repeat(starts, counts)
        out[:] = np.repeat(bases, counts) + seg * stride
        return out

    def decode_bits(self, verbose=True):
        """Decode the global BIT chain -> flat_address[] (31-bit) and byte4[] flags."""
        if self._flat is not None:
            return self._flat, self._byte4
        t = time.time()
        arr = np.frombuffer(self.body, dtype=np.uint8)
        offs = self._gather_offsets(self.node_bit_base, self.node_B, 8)  # 8-byte records
        # addr delta = little-endian int32 at record+0
        d0 = arr[offs + 0].astype(np.uint32)
        d1 = arr[offs + 1].astype(np.uint32)
        d2 = arr[offs + 2].astype(np.uint32)
        d3 = arr[offs + 3].astype(np.uint32)
        delta = (d0 | (d1 << 8) | (d2 << 16) | (d3 << 24)).astype(np.int32)
        flat = np.cumsum(delta.astype(np.int64)).astype(np.uint32) & 0x7FFFFFFF
        # flag bytes at +4.. : each is a signed-byte delta, 1-bit field -> cumsum & 1.
        # Field order (DYGR_ROUTE_ASM_BIT::operator<< @0x3ba940):
        #   +4 m_use_encoded_setting  -> in-memory byte3 bit7
        #   +5 m_is_encoded_bit_high  -> in-memory byte4 bit0
        #   +6 m_is_strangely_encoded -> in-memory byte4 bit1
        #   +7 m_is_cff_bit           -> in-memory byte4 bit2  (the 0xA0000000 region tag)
        f_use = (np.cumsum(arr[offs + 4].astype(np.int8).astype(np.int64)) & 1).astype(np.uint8)
        f_enc_high = (np.cumsum(arr[offs + 5].astype(np.int8).astype(np.int64)) & 1).astype(np.uint8)
        f_strange = (np.cumsum(arr[offs + 6].astype(np.int8).astype(np.int64)) & 1).astype(np.uint8)
        f_cff = (np.cumsum(arr[offs + 7].astype(np.int8).astype(np.int64)) & 1).astype(np.uint8)
        # Faithful 5-byte in-memory reconstruction:
        byte3 = ((f_use << 7) | ((flat >> 24) & 0x7F).astype(np.uint8)).astype(np.uint8)
        byte4 = ((f_cff << 2) | (f_strange << 1) | f_enc_high).astype(np.uint8)
        self._flat = flat
        self._byte3 = byte3
        self._byte4 = byte4
        self._use_encoded = f_use          # byte3 bit7
        self._enc_bit_high = f_enc_high     # byte4 bit0
        self._strange = f_strange           # byte4 bit1
        self._cff = f_cff                   # byte4 bit2
        if verbose:
            print(f"[bits] decoded {len(flat)} BIT flat addresses in {time.time()-t:.1f}s",
                  file=sys.stderr)
        return self._flat, self._byte4

    def decode_start_index(self, verbose=True):
        """Decode the global ushort start-index chain."""
        if self._start_index is not None:
            return self._start_index
        t = time.time()
        arr = np.frombuffer(self.body, dtype=np.uint8)
        offs = self._gather_offsets(self.node_us_base, self.node_G, 2)  # 2-byte records
        lo = arr[offs + 0].astype(np.uint16)
        hi = arr[offs + 1].astype(np.uint16)
        d = (lo | (hi << 8)).astype(np.int16)
        si = np.cumsum(d.astype(np.int64)).astype(np.int64) & 0xFFFF  # in-memory ushort
        self._start_index = si.astype(np.uint16)
        if verbose:
            print(f"[us] decoded {len(si)} start-index ushorts in {time.time()-t:.1f}s",
                  file=sys.stderr)
        return self._start_index

    def _node_group_offsets(self, node_index):
        """Unwrapped 0-based within-node local bit offset of each of the node's G
        groups. m_start_bit_index is an in-memory ushort, so its running (global)
        value wraps at 65536; within a node the true offsets are strictly the
        accumulated deltas, recovered by adding 65536 whenever a within-node step
        goes negative (a wrap). offs[0]==0 always; offs is nondecreasing."""
        G = int(self.node_G[node_index])
        g0 = int(self.node_group_start[node_index])
        si = self.decode_start_index(verbose=False)
        offs = [0]
        cum = 0
        for k in range(1, G):
            d = int(si[g0 + k]) - int(si[g0 + k - 1])
            if d < 0:
                d += 0x10000
            cum += d
            offs.append(cum)
        return offs

    # ---- accessors matching the shipping reader semantics ----
    def get_flat_address(self, global_bit_ordinal):
        """DYGR_ROUTE_ASM_BIT::get_flat_address() on the N-th BIT (stream order)."""
        flat, byte4 = self.decode_bits(verbose=False)
        a = int(flat[global_bit_ordinal])
        if byte4[global_bit_ordinal] & 4:
            a |= 0xA0000000
        return a

    def get_single_bit(self, node_index, igroup, ibit):
        """
        DYGR_ROUTE_ASM_NODE::get_single_bit(igroup, ibit) -> global BIT ordinal.

        m_start_bit_index[] is decoded by decode_start_index() as a xfr_short_delta
        chain that accumulates GLOBALLY (the delta ref is the previous stream
        instance, not reset per node), so the absolute decoded value of a node's
        group 0 is a large running base -- NOT 1. Only the WITHIN-NODE differences
        are meaningful. The per-node local bit offset of group g is therefore
            local(g) = start_index[g] - start_index[0]
        (0-based, group 0 anchored at the node's first BIT). Verified: the per-group
        slices tile the node's B bits exactly and their union reproduces
        iter_node_cell_records()'s flat cell set (e.g. C4 node 70654, G=23, B=71).
        Returns the global BIT ordinal (index into decode_bits()).
        """
        G = int(self.node_G[node_index])
        B = int(self.node_B[node_index])
        assert 0 <= igroup < G, f"igroup {igroup} out of range [0,{G})"
        offs = self._node_group_offsets(node_index)   # unwrapped 0-based local offsets
        start = offs[igroup]
        # number of bits in this group:
        if igroup + 1 < G:
            nxt = offs[igroup + 1]
        else:
            nxt = B
        num_in_group = nxt - start
        assert 0 <= ibit < num_in_group, f"ibit {ibit} out of range [0,{num_in_group})"
        local = start + ibit                          # 0-based within node's bit block
        return int(self.node_bit_start[node_index]) + local

    def node_flat_addresses(self, node_index):
        """List of get_flat_address() for every BIT of a node, in order."""
        flat, byte4 = self.decode_bits(verbose=False)
        b0 = int(self.node_bit_start[node_index])
        B = int(self.node_B[node_index])
        out = []
        for k in range(b0, b0 + B):
            a = int(flat[k])
            if byte4[k] & 4:
                a |= 0xA0000000
            out.append(a)
        return out

    # ---- Phase 2 TASK 1: invert the pool into per-NODE CRAM cell records ---- #
    def iter_node_cell_records(self, colw=1727, last_frame=1751):
        """
        Yield (node_index, record) for every NON-EMPTY DYGR_ROUTE_ASM_NODE.

        Each record inverts the BIT chain back onto its owning mux NODE:
            cells        distinct full flat addresses (region tag OR-ed in) of
                         this node's BIT[] block, sorted ascending
            count        len(cells)
            num_groups   m_num_bit_groups (mux select-group count)
            columns      sorted distinct CRAM columns (flat % colw) the cells occupy
            frame_range  [min_frame, max_frame] with frame = last_frame - column
            record_off   byte offset of this node's BIT[] block in the decompressed
                         body -- the concrete on-disk "record" locator
        Only main-plane cells (flat < 0x80000000) contribute to columns/frame_range;
        region-tagged aux cells (>=0x80000000) are still listed in `cells`.

        NODE IDENTITY is purely POSITIONAL: node_index is the ordinal in the
        DYGR_ROUTE_ASM node vector (0..num_asm_nodes-1). The ASM node record stores
        NO id field (operator<< reads only num_bit_groups / num_bits / arrays), so
        the ordinal is the sole join key to the routing-graph node order that the
        .rcf back-annotation names (R4/C4/R24/LOCAL_INTERCONNECT/BLOCK_INPUT_MUX...).
        """
        flat, byte4 = self.decode_bits(verbose=False)
        full = flat.astype(np.int64)
        tag = (byte4 & 4) != 0
        nb = self.node_B
        bstart = self.node_bit_start
        bbase = self.node_bit_base
        ng = self.node_G
        for ni in range(self.num_asm_nodes):
            B = int(nb[ni])
            if B == 0:
                continue
            b0 = int(bstart[ni])
            sl = slice(b0, b0 + B)
            vals = full[sl].copy()
            vals[tag[sl]] |= 0xA0000000
            cells = np.unique(vals)
            main = cells[cells < 0x80000000]
            if len(main):
                cols = np.unique(main % colw)
                fr = [int(last_frame - cols.max()), int(last_frame - cols.min())]
            else:
                cols = np.empty(0, np.int64)
                fr = None
            yield ni, {
                "cells": [int(x) for x in cells],
                "count": int(len(cells)),
                "num_groups": int(ng[ni]),
                "columns": [int(c) for c in cols],
                "frame_range": fr,
                "record_off": int(bbase[ni]),
            }

    # ---- Phase 2 TASK A: per-NODE SUB-FIELD (bit-group) cell membership ----- #
    def iter_node_grouped_records(self, colw=1727, last_frame=1751):
        """
        Yield (node_index, record) for every NON-EMPTY DYGR_ROUTE_ASM_NODE with the
        node's BIT[] block SPLIT INTO ITS num_bit_groups SELECT SUB-FIELDS.

        This is the grouped counterpart of iter_node_cell_records: instead of
        flattening every BIT into one cell set, it uses m_start_bit_index[] to
        recover the per-group (per-sub-field) cell sets -- the COMPLETE multi-level
        one-hot structure of a routing mux. num_groups (== m_num_bit_groups) gives
        the exact sub-field count straight from the device file, so sub-fields that
        an under-swept fuzz corpus would miss are present here by construction.

        m_start_bit_index is a xfr_short_delta chain that accumulates GLOBALLY (the
        delta ref is the previous stream instance, not reset per node), so group 0's
        decoded absolute value is a large running base, not 1. The WITHIN-NODE group
        boundaries are recovered by anchoring group 0 at local bit 0:
            local_off(g) = start_index[g] - start_index[0]
        The resulting per-group slices tile the node's B bits exactly; their union
        reproduces iter_node_cell_records()'s flat cell set (verified on C4 nodes).

        record:
            num_groups   G (== m_num_bit_groups) -- the mux select sub-field count
            groups       list of G sorted-distinct flat-cell lists (region tag
                         OR-ed in), one per one-hot select sub-field, in group order
            column       anchor (minimum) main-plane CRAM column (flat % colw)
            columns      sorted distinct main-plane CRAM columns the node occupies
            frame_range  [min_frame, max_frame], frame = last_frame - column
            count        distinct-cell count of the whole node (union of groups)
            record_off   byte offset of the node's BIT[] block
            monotone     True iff start_index[] is nondecreasing within the node and
                         the group boundaries tile [0,B] (structural sanity flag)
        """
        flat, byte4 = self.decode_bits(verbose=False)
        self.decode_start_index(verbose=False)   # populate cache for _node_group_offsets
        full = flat.astype(np.int64)
        tag = (byte4 & 4) != 0
        nb = self.node_B
        ng = self.node_G
        bstart = self.node_bit_start
        bbase = self.node_bit_base
        for ni in range(self.num_asm_nodes):
            B = int(nb[ni])
            if B == 0:
                continue
            G = int(ng[ni])
            b0 = int(bstart[ni])
            offs = self._node_group_offsets(ni)   # unwrapped 0-based local offsets
            bounds = offs + [B]
            monotone = (all(bounds[k] <= bounds[k + 1] for k in range(G))
                        and bounds[-1] == B)
            groups = []
            union = set()
            for g in range(G):
                s = bounds[g]
                e = bounds[g + 1]
                if e < s:                      # non-monotone guard (never on C4)
                    e = s
                s = max(0, min(s, B))
                e = max(0, min(e, B))
                sl = slice(b0 + s, b0 + e)
                vals = full[sl].copy()
                vals[tag[sl]] |= 0xA0000000
                cells = sorted(int(x) for x in set(vals.tolist()))
                groups.append(cells)
                union.update(cells)
            allc = np.fromiter(union, np.int64) if union else np.empty(0, np.int64)
            main = allc[allc < 0x80000000]
            if len(main):
                cols = np.unique(main % colw)
                col0 = int(cols.min())
                collist = [int(c) for c in cols]
                fr = [int(last_frame - cols.max()), int(last_frame - cols.min())]
            else:
                col0 = None
                collist = []
                fr = None
            yield ni, {
                "num_groups": G,
                "groups": groups,
                "column": col0,
                "columns": collist,
                "frame_range": fr,
                "count": int(len(union)),
                "record_off": int(bbase[ni]),
                "monotone": bool(monotone),
            }


# --------------------------------------------------------------------------- #
# CLI / sample dump                                                            #
# --------------------------------------------------------------------------- #
def main():
    t0 = time.time()
    data = open(DDB_PATH, "rb").read()
    hdr = read_container_header(data)
    body = decompress_body()
    asm = DdbAsm(body)
    rep = asm.structural_report()
    print("== container header ==", file=sys.stderr)
    for k, v in hdr.items():
        print(f"   {k}: {v}", file=sys.stderr)
    print("== structural report ==", file=sys.stderr)
    for k, v in rep.items():
        print(f"   {k}: {v}", file=sys.stderr)

    # Decode global chains (validates the delta model end to end).
    asm.decode_bits()
    asm.decode_start_index()
    flat, byte4 = asm._flat, asm._byte4

    # Stats on decoded flat addresses.
    tagged = int((byte4 & 4).sum())
    stats = {
        "num_bits": int(len(flat)),
        "flat_min": int(flat.min()),
        "flat_max": int(flat.max()),
        "num_region_tagged_A0000000": tagged,
        "num_use_encoded": int(asm._use_encoded.sum()),
        "num_enc_bit_high": int(asm._enc_bit_high.sum()),
    }
    print("== bit stats ==", file=sys.stderr)
    for k, v in stats.items():
        print(f"   {k}: {v}", file=sys.stderr)

    # Find first few NON-empty nodes and dump them.
    nz_nodes = np.nonzero(asm.node_B > 0)[0]
    samples = []
    for ni in nz_nodes[:6]:
        ni = int(ni)
        G = int(asm.node_G[ni])
        B = int(asm.node_B[ni])
        g0 = int(asm.node_group_start[ni])
        si = asm._start_index[g0:g0 + G].tolist()
        addrs = asm.node_flat_addresses(ni)
        samples.append({
            "node_index": ni,
            "num_bit_groups": G,
            "num_bits": B,
            "start_index_per_group": si,
            "flat_addresses_hex": [f"0x{a:08x}" for a in addrs[:16]],
            "flat_addresses_total": len(addrs),
        })

    # Exercise get_single_bit on the first non-empty node with >=1 group.
    gsb_demo = None
    for ni in nz_nodes:
        ni = int(ni)
        if asm.node_G[ni] >= 1 and asm.node_B[ni] >= 1:
            gord = asm.get_single_bit(ni, 0, 0)
            gsb_demo = {
                "node_index": ni,
                "igroup": 0, "ibit": 0,
                "global_bit_ordinal": int(gord),
                "flat_address_hex": f"0x{asm.get_flat_address(gord):08x}",
            }
            break

    out = {
        "source_ddb": DDB_PATH,
        "container_header": hdr,
        "structural_report": rep,
        "bit_stats": stats,
        "sample_nonempty_nodes": samples,
        "get_single_bit_demo": gsb_demo,
        "parse_seconds": round(time.time() - t0, 1),
    }
    outpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ddb_sample_dump.json")
    with open(outpath, "w") as f:
        json.dump(out, f, indent=2)
    print(f"[done] wrote {outpath} in {out['parse_seconds']}s", file=sys.stderr)
    # Emit the JSON on stdout too.
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
