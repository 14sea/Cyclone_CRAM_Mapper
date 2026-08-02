# SA1 — DYGR route-asm pool: exact serialized format spec

Reverse-engineered from the decompiled `libddb_dygr.so` serializers (`operator<<`
transfer functions = the on-disk format), cross-checked against the existing
container parser `<repo>/devfile/ddb_parse.py`, and validated by a
byte-exact full sequential decode of the concrete device file
`ddb_cycloneive1_asm.ddb` (the EP4CE10 / Cyclone IV E "1" variant).

Decode/refuse rule honored: every field below is grounded in a decompiled body or
in a full-file byte-exact reparse. Nothing is guessed.

---

## 0. Where the route-asm segment lives

- File: `$QUARTUS_ROOTDIR/common/devinfo/cycloneive/ddb_cycloneive1_asm.ddb`
  (1,405,145 bytes on disk). `_asm.ddb` is the DYGR **route-asm** pool. The
  `_routing.ddb` sibling holds the **route graph / fanout** (needed to bind
  edge_number -> dest, see §6). `_fdi`/`_dmf` are timing, not routing.
- Segment class = `DYGR_ROUTE_ASM_INFO_BODY`, PDB class-thunk id `0xd2ef53e1`,
  in-memory size `0x20`. Registered at libddb_dygr.so decompile line ~25177.
  Child classes: `DYGR_ROUTE_ASM_NODE` id `0xc43cc2b8` size `0x18`;
  `DYGR_ROUTE_ASM_BIT` id `0xb3b09795` size `5`.
- The segment is written to the PDB by
  `DYGR_ROUTE_ASM_INFO_BODY::write_data_to_pdb` (@0x3295e0) via
  `pdb_write_ptr(..., pdb_xfr_ptr_func<PDB_SEGMENT_TEMPLATE<PDB_DDB_SEG_BASE>,
  DYGR_ROUTE_ASM_INFO_BODY>, ...)` and read back by
  `DYGR_ROUTE_ASM_INFO_BODY::load_data` -> `load_data_from_pdb` (@0x3299b0).
  The field-by-field codec is `DYGR_ROUTE_ASM_INFO_BODY::operator<<` (@0x3bab70)
  and the two child `operator<<`s.

Concrete decode of `ddb_cycloneive1_asm.ddb`:
```
root_desc            = 4
num_asm_nodes        = 135117  (== vector_size)
inflated body length = 31,441,834 bytes
sequential parse consumed EXACTLY 31,441,834 bytes (0 tail) -> byte-exact
non-empty nodes      = 113,180
total bit-groups     = 1,167,987
total bits           = 3,503,114
flat-addr range      = 0x1b1c .. 0x2b7aef  (all < 0x7fffffff = DYGR_MAX_CRAM_FLAT_ADDRESS)
encoded-setting bits = 2,086,482 ; cff/0xA0000000 bits = 0
```

---

## 1. Container framing (already solved in ddb_parse.py)

- 111-byte (0x6f) outer header. `u16 @ offset 12` = 0x6f = start of the zlib
  stream. `u32 @ 16` = version-string length (56); version string follows at 20.
- One raw zlib stream (`0x78 0x01`) from offset 111, **not** BFINAL-terminated
  (ends on a Z_SYNC_FLUSH) with trailer bytes after it. Recover by inflating the
  largest clean prefix (binary search — see `_max_clean_inflate_len`).
- The inflated bytes are the object-graph "body": one linear little-endian cursor.

---

## 2. PDB codec primitives (the `PDB_SEGMENT_TEMPLATE<PDB_DDB_SEG_BASE>` vtable)

The `operator<<` bodies call the transfer object through fixed vtable slots. The
concrete reader is in `libdb_pdb.so` (`PDB_SEGMENT_READER` vtable @0x1a9e0);
slot -> codec (transcribed in ddb_parse.py, confirmed by the full reparse):

| slot   | codec name        | on-wire                                            |
|--------|-------------------|----------------------------------------------------|
| +0x40  | `xfr_short_delta` | int16 signed delta; value = raw + running(field)   |
| +0x48  | `xfr_int_delta`   | int32 signed delta; value = raw + running(field)   |
| +0x80  | `xfr_short`       | plain u16 (array length prefix; redundant w/ count) |
| +0x88  | `xfr_int`         | plain u32 (array length prefix)                    |
| +0x20  | `xfr_new_array`   | if count==0 read nothing; else loop count elems    |
| +0xd0  | `xfr_field_v`     | width-bucketed signed delta (see below)            |
| +0xe0  | serialize_begin   | bookkeeping, **consumes 0 stream bytes**           |
| +0xe8  | serialize_end     | bookkeeping, **consumes 0 stream bytes**           |

`xfr_field_v(value, nbits, ref)` storage width is chosen by `nbits`:
`nbits <= 8 -> 1 signed byte`; `9..16 -> 2 bytes`; `>16 -> 4 bytes`. Value is a
signed delta off the running accumulator for that field.

### Delta-chain model (the single most important gotcha)

Every `*_delta` / `xfr_field_v` field keeps **one running accumulator per
(class, field), global across the whole segment, initialised to 0**. The decoded
value is the cumulative sum of the stored signed deltas in stream order. Two
consequences you MUST respect when writing a parser:

- **Absolute-meaning fields** (one instance per node, writer stored the true
  value): `m_num_bit_groups`, `m_num_bits`, and — importantly — the per-BIT
  `m_flat_address`. Their cumulative-sum value IS the semantic value directly.
  (Proven: cumsum of the int32 addr deltas over all 3.5M bits lands every address
  in the tight valid window `0x1b1c..0x2b7aef`.)
- **Difference-only field**: `m_start_bit_index`. Many instances per node; the
  cumulative value carries a running base (e.g. group 0 of the 500th non-empty
  node decodes to 7459, not 1). Only the **within-node differences** are
  semantic. Recover per-group bit boundaries from
  `local(g) = start_index[g] - start_index[node.group0]` with 16-bit wrap
  correction (add 0x10000 to any negative step; the in-memory field is a `ushort`
  so the running value wraps at 65536, and one node spans < 65536 bits so a single
  wrap fix is unambiguous). Validated: the differences tile each node's `B` bits
  exactly (ddb_parse verified against real C4 cell node 70654, G=23 B=71).

---

## 3. Stream layout — `DYGR_ROUTE_ASM_INFO_BODY` (root; `operator<<` @0x3bab70)

```
offset 0:  u32  root_ptr_descriptor          == 4        (from pdb_read xfr_ptr; not a field)
           i32d m_num_asm_nodes   [field 0x345]          # +0x48 xfr_int_delta, ref 0
           u32  vector_size                               # +0x88 xfr_int  (== m_num_asm_nodes)
           m_num_asm_nodes x NODE  [field 0x347]          # +0x20 xfr_new_array, DYGR_ROUTE_ASM_NODE::s_thunk
```
In-memory `DYGR_ROUTE_ASM_INFO_BODY` (size 0x20):
`+0x00 DYGR_DIE_INFO* m_die_info` (transient, set at load), `+0x08 bool
m_is_data_loaded`, `+0x0c u32 m_num_asm_nodes`, `+0x18 DYGR_ROUTE_ASM_NODE*
m_route_asm_nodes` (array, node i at `base + i*0x18`).

## 4. Stream layout — `DYGR_ROUTE_ASM_NODE` (per node; `operator<<` @0x3ba800)

```
i16d m_num_bit_groups (=G) [field 0x324]   # +0x40 xfr_short_delta  -> true per-node count
i16d m_num_bits       (=B) [field 0x325]   # +0x40 xfr_short_delta  -> true per-node count
u16  G_prefix              [field 0x326]   # +0x80 xfr_short   (== G)
G  x i16d start_index      [field 0x326]   # +0x20 xfr_new_array, PDB_STL_CLASS_THUNK<unsigned short> (xfr_short_delta)
u16  B_prefix              [field 0x327]   # +0x80 xfr_short   (== B)
B  x BIT                   [field 0x327]   # +0x20 xfr_new_array, DYGR_ROUTE_ASM_BIT::s_thunk
```
Empty node (G=0,B=0) is exactly 8 bytes: `i16d 0, i16d 0, u16 0, u16 0`
(confirmed: first 4000 nodes are empty -> 12 + 4000*8 = 32012 cursor, exact).

In-memory `DYGR_ROUTE_ASM_NODE` (size 0x18):
`+0x00 u16 m_num_bit_groups`, `+0x02 u16 m_num_bits`,
`+0x08 u16* m_start_bit_index` (G entries, 1-based per-node start; see §2 recovery),
`+0x10 DYGR_ROUTE_ASM_BIT* m_asm_bits` (B entries, 5 bytes each).

Accessor semantics (from decompiled bodies):
- `get_num_bit_groups()` = `m_num_bit_groups`.
- `get_num_bits_in_group(g)`: non-last group = `start[g+1]-start[g]`; last group =
  `m_num_bits - start[g] + 1` (uses differences -> base-independent).
- `get_single_bit(g, ibit)` -> `m_asm_bits[ start[g] + ibit - 1 ]` (start is
  1-based within the group). Equivalent global BIT ordinal for a static join =
  `node_bit_start + (start[g]-start[group0]) + ibit`, where `node_bit_start =
  sum of B over prior nodes` (each node's bits are a contiguous slice of the
  global BIT stream).

## 5. Stream layout — `DYGR_ROUTE_ASM_BIT` (per bit; `operator<<` @0x3ba940)

Five fields via `xfr_field_v` (+0xd0), so the on-disk record is 4+1+1+1+1 = **8
bytes** (delta-coded):

```
i32d m_flat_address        [field 0x333]  nbits=31 -> 4 bytes  # ABSOLUTE via global cumsum
i8d  m_use_encoded_setting [field 0x334]  nbits=1  -> 1 byte
i8d  m_is_encoded_bit_high [field 0x335]  nbits=1  -> 1 byte
i8d  m_is_strangely_encoded[field 0x336]  nbits=1  -> 1 byte
i8d  m_is_cff_bit          [field 0x337]  nbits=1  -> 1 byte
```
Each field is its own global cumsum; the 1-bit flags are `cumsum & 1`.

In-memory `DYGR_ROUTE_ASM_BIT` (5 bytes), reconstructed by the writer as:
```
byte0..2 = flat_address[0..23]
byte3    = (m_use_encoded_setting << 7) | flat_address[24..30]
byte4    = (m_is_cff_bit << 2) | (m_is_strangely_encoded << 1) | m_is_encoded_bit_high   (bits 0..2)
```
`get_flat_address()` (@0x329510) = `(byte0..2 | ((byte3 & 0x7f)<<24))`, then
`| 0xA0000000` iff `byte4 & 4` (the cff/virtual-CRAM tag; 0 occurrences in the
cycloneive1 pool). Value asserted `< 0x7fffffff`.
`use_encoded_setting()` (@0x329550): 0 if `byte3 bit7`==0; else 2 if
`m_is_strangely_encoded` (byte4 bit1) set, else 1.
`is_encoded_bit_high()` = `byte4 bit0` (valid only when use_encoded_setting != 0).

The pair `(flat_address, encoded/value)` a BIT contributes to a `DB_BIT_SETTING`:
if `use_encoded_setting()==0` the bit is forced high (value 1); otherwise the bit
value is `is_encoded_bit_high()`. `get_bits_from_source_to_dest` (@0x32ac80) emits
one `{first=flat_address, value}` per bit of the selected group, plus the dest's
exclusion-group bits at value 0 (see §6). Note the special sentinel:
`flat_address == 0x0ffffffa` is remapped to `-6` in that emitter.

---

## 6. Edge model — how `get_destination_bit_group(src_id, dest_id)` -> bit-group

`DYGR_ROUTE_ASM_INFO_BODY::get_destination_bit_group` (@0x32aa50) takes GLOBAL
router node ids for both endpoints and returns an `edge_number` that is directly
the **bit-group index** into `src`'s `DYGR_ROUTE_ASM_NODE`:

```
route_info   = die_info->get_route_info()               # the DYGR_ROUTE_INFO (routing.ddb)
node_rec     = route_node_base + (src_id & 0x7fffffff) * 0x10   # 16-byte route node record
base_gid     = *(int32*)(node_rec + 4)                  # per-src base gid
route_elem   = *(ptr*)(node_rec + 8)                    # fanout descriptor (transient/compiled)
fanout_size  = *(u16*)(route_elem + 8)                  # num destination edges of src
delta[]      = *(int32**)(route_elem + 0x10)            # fanout delta array, length fanout_size
# find k in [0, fanout_size):  dest_id == base_gid + delta[k]   -> return k (else 0xffffffff)
```

So `edge_number == index of dest in src's ordered fanout`, and
`src_asm_node.bit_group[edge_number]` is the destination bit-group. Then
`get_num_bits_in_group(edge_number)` + `get_single_bit(edge_number, i)` yield the
BITs (§4/§5). Bit-groups `[fanout_size .. m_num_bit_groups)` of a node are
**exclusion groups**: `get_num_exclusion_groups(id) = node.num_bit_groups -
fanout_size(id)`; `get_exclusion_bit_group(id, i) = fanout_size(id) + i`
(@0x32a8e0 / @0x32a9a0). A full arc's bits = src's `bit_group[edge_number]`
(as programmed bits) UNION dest's exclusion-group bits (forced to 0).

### On-disk source of the fanout (cross-file — routing.ddb)

The ordered fanout that defines `edge_number -> dest_gid` is serialized in the
route graph, class `DYGR_ROUTE_ELEMENT_TEMPLATE::operator<<` (@0x3b9ac0) inside
`DYGR_ROUTE_INFO_BODY` (in `ddb_cycloneive1_routing.ddb`). Relevant fields:
```
i16d m_element_enum                  [0x1a7]  # +0x40
i16d m_num_edges (= fanout_size)     [0x1a8]  # +0x40
i16d  ...                            [0x1a9]  # +0x40
i16d m_index                         [0x1aa]  # +0x40
xfr_field_v m_first_purely_redundant_edge [0x1ab] nbits=16
xfr_field_v m_length [0x1ac] n=8 ; m_metal_layer [0x1ad] n=4 ; m_direction [0x1ae] n=4
m_num_edges x i32  m_fanout_list_offsets  [0x1af]  # +0x80 prefix + +0x20 array, PDB_STL_CLASS_THUNK<int>
m_num_edges x u16  m_fanout_to_positions  [0x1b0]  # +0x80 prefix + +0x20 array, <unsigned short>
```
`m_fanout_list_offsets[k]` is the per-edge delta; `dest_gid(k) = base_gid +
m_fanout_list_offsets[k]`. The `base_gid` and per-node record come from
`DYGR_ROUTE_INFO_BODY::operator<<` (@0x3c6900) — the `m_route_element_list`
vector plus the node-index table. That parse is the SA2 task; it is NOT in the
_asm_ pool.

---

## 7. What a parser can produce, and the honest coverage boundary

**From `ddb_cycloneive1_asm.ddb` ALONE:** `{ src_node_index, bit_group_index ->
[ {flat_address, use_encoded, is_encoded_bit_high, is_strangely_encoded,
is_cff} ] }` for every node/group/bit — byte-exact, whole device (135117 nodes,
1.17M groups, 3.5M bits). `flat_address` -> rbf via the proven `bitpos_to_rbf.py`.

**To label a bit-group as a concrete `src_gid -> dest_gid` edge** you MUST join
with the route graph (`ddb_cycloneive1_routing.ddb`, §6) to get, per src node, the
`base_gid` and the ordered `m_fanout_list_offsets` (edge k -> dest_gid). Without
it, the asm pool gives bits-per-edge-slot but not which dest each slot is. This
join is required for LI/LEIM/C4/R4/R24/C16/direct-link binding alike — the asm
pool is class-agnostic; the routing pool supplies the class-specific fanout.

**Node id <-> (I,X,Y)** via the proven lattices in the mission brief; node index
in the asm array = `get_node_index_of_id(id)` on router ids (`is_router_id` gate).
`get_asm_node(id)` maps a global id -> node record; the asm array is indexed by
node *index*, not raw id, so the id->index map (from the die-info / gid pool) is a
further dependency for id-keyed lookup (index-keyed enumeration needs nothing
extra).

---

## 8. Blockers / open items

1. **Fanout join (routing.ddb).** Binding `edge_number -> dest_gid` needs
   `DYGR_ROUTE_INFO_BODY` parsed (base_gid + `m_fanout_list_offsets`). Separate
   segment/file; SA2. Until then, edges are src+slot, not src->dest.
2. **id -> node-index map.** Enumerating by node index is self-contained; keying by
   global router id needs `is_router_id` / `get_node_index_of_id` (die-info/gid
   pool). Index order in the asm array is assumed to equal `get_node_index_of_id`
   order — must be confirmed against the gid pool.
3. **start_index absolute base.** On-disk start indices decode to a global running
   base (§2); per-node group boundaries are correct via within-node differences,
   which is all §4/§6 need. If any consumer needs the literal in-memory 1-based
   value, subtract the node's group-0 base.
4. **cff / 0xA0000000 bits.** Zero occurrences in cycloneive1; the sentinel path
   (`flat==0x0ffffffa -> -6`) and `0xA0000000` OR are implemented but untested on
   this device — flag if they appear on other variants.
5. **Ground-truth validation** (reproduce every arc in `routing_capture.jsonl` /
   `traceA.json`) is the next step; not yet run here (SA1 is format-only). The
   asm-side decode is already byte-exact against the whole file.
