# SA3 — LOCATE the DYGR route-asm segment

**Goal:** enumerate the PDB segments of the candidate `cycloneive` `.ddb` files and locate the
one holding the DYGR route-asm pool; confirm the exact file + offset the parser should target,
whether it is zlib-wrapped, and cross-check its size against the C4/R4/C16/R24 wire counts.

**Verdict (one line):** for the mission target **EP4CE10**, the route-asm pool is
**`$QUARTUS_ROOTDIR/common/devinfo/cycloneive/ddb_cycloneive1_asm.ddb`**,
a **single** PDB segment whose entire zlib body (offset **111**, `78 01`) deserializes to
`DYGR_ROUTE_ASM_INFO_BODY`. The current `ddb_parse.py` points at the **wrong die**
(`cycloneive6_asm`, = EP4CE115); it must be repointed to `cycloneive1_asm`. **Byte-exact parse
confirmed:** `bytes_consumed == body_len == 31,441,834`.

---

## 1. Die mapping — EP4CE10 → `cycloneive1`

The `cycloneive{1,2,2_5,3,4,5,6}` suffixes are **die** ids, not device names; several devices
share a die. From `ddb_cycloneive.ref` (`nx`,`ny` per part):

| device   | nx × ny  | die       | `_asm.ddb`                         |
|----------|----------|-----------|------------------------------------|
| EP4CE6   | 35 × 25  | **cycloneive1**  | `ddb_cycloneive1_asm.ddb`   |
| **EP4CE10** | **35 × 25** | **cycloneive1** | **`ddb_cycloneive1_asm.ddb`** ← target |
| EP4CE15  | 42 × 30  | cycloneive2      | `ddb_cycloneive2_asm.ddb`   |
| EP4CE22  | 54 × 35  | cycloneive2_5    | `ddb_cycloneive2_5_asm.ddb` |
| EP4CE30/40 | 68 × 44 | cycloneive3     | `ddb_cycloneive3_asm.ddb`   |
| EP4CE55  | 78 × 54  | cycloneive4      | `ddb_cycloneive4_asm.ddb`   |
| EP4CE75  | 95 × 63  | cycloneive5      | `ddb_cycloneive5_asm.ddb`   |
| EP4CE115 | 116 × 74 | cycloneive6      | `ddb_cycloneive6_asm.ddb`   |

EP4CE6 and EP4CE10 are the **same silicon die** (35 × 25) ⇒ **cycloneive1**. The A2 node-id
lattices (`C4 70654+…`, `R4 44198+…`, `R24 59111+…`) were fit on EP4CE6/EP4CE22; their bases fall
inside cycloneive1's `num_asm_nodes = 135117`, i.e. they are cycloneive1 ordinals — consistent
with EP4CE10.

---

## 2. Container / segment enumeration of the candidate files

Every `.ddb` is a **single-segment PDB archive**: `111`-byte outer header (carries the
`"Version 21.1.0 Build 842 10/21/2021 SJ Standard Edition"` string; `bytes[12:14] LE = 0x6f = 111`
= start of the payload) → **one** raw zlib stream → short trailer. There is **no multi-segment
directory inside a file**; one `.ddb` = one PDB pointer-segment = one root object. Different DYGR
bodies live in **different files**, distinguished by a filename **suffix** (see §4).

Empirical enumeration of the cycloneive1 candidates (`zlib@111`, inflate the max clean prefix,
then read the body's 12-byte `DYGR_ROUTE_ASM_INFO_BODY` header `root_desc | m_num_asm_nodes | vector_size`):

| file | size | zlib | body head `root / num / vec` | is route-asm pool? |
|------|------|------|------------------------------|--------------------|
| **`ddb_cycloneive1_asm.ddb`** | 1,405,145 | `78 01` @111 | **`4 / 135117 / 135117`** (num==vec) | **YES — `DYGR_ROUTE_ASM_INFO_BODY`** |
| `ddb_cycloneive1_routing.ddb` | 1,794,438 | `78 01` @111 | `4 / 35 / 25` (num≠vec; = nx,ny) | No — `DYGR_ROUTE_INFO_BODY` (topology) |
| `ddb_cycloneive1_asmdb.ddb`   | 31,456    | `78 da` @111 | `4 / 731253248 / 2101248` (num≠vec) | No — ASMDB config (`asmdb`) |

Only `*_asm.ddb` has the defining signature **`root_descriptor == 4` AND `m_num_asm_nodes == vector_size`**,
which is exactly what `DYGR_ROUTE_ASM_INFO_BODY::operator<<` writes. `_routing`/`_asmdb` fail it and
are different classes.

### Container facts for `ddb_cycloneive1_asm.ddb` (the target)
- **zlib-wrapped: YES.** Raw zlib at file offset **111**, header `78 01` (32 KB window, FLEVEL=fastest,
  no preset dict). The stream ends on a `Z_SYNC_FLUSH` (no BFINAL); binary-search the largest
  cleanly-inflating prefix (already implemented in `decompress_body`).
- Inflated body = **31,441,834 bytes** from 1,404,912 compressed bytes; stream ends at file offset
  1,405,023; a **122-byte trailer** follows (`…00 00 00 00 ff ff`, a deflate sync-flush terminator —
  a PDB segment end-cap, not independently inflatable and **not needed**: all structural counts come
  from the body itself, not the trailer).
- **Segment offset the parser must target = byte 0 of the *decompressed* body** (`root ptr desc u32 = 4`,
  then `m_num_asm_nodes`, then `vector_size`, then the NODE array). i.e. the parser reads the whole
  zlib body as the one segment — same model already used for cycloneive6, no per-segment offset needed.

---

## 3. Byte-exact structural confirmation + wire-count cross-check

Ran the existing `ddb_parse.DdbAsm` on the cycloneive1 body (repointed path/cache only):

```
root_descriptor : 4
num_asm_nodes   : 135117            (== vector_size)
sum_group_counts: 1,167,987
sum_bit_counts  : 3,503,114
bytes_consumed  : 31,441,834
body_len        : 31,441,834        →  bytes_match = TRUE   (whole body consumed, no slack)
nonempty nodes (B>0)     : 108,380
nodes with groups (G>0)  : 113,180
parse time      : ~0.7 s
```

`bytes_match=TRUE` on an independent re-derivation of the `operator<<` layout is the strongest
possible proof this segment is the route-asm pool and that the on-disk format matches the parser.

**Wire-count cross-check (C4 21816 / R4 28186 / C16 1326 / R24 1289).** These four long-line
classes sum to **52,617**, a subset of the **108,380** non-empty mux nodes; the remaining ~55,763
are LI/LEIM local interconnect, LE_BUFFER/direct links, BLOCK_INPUT_MUX, LE/LUT-input muxes, IO,
clock, etc. — the correct order of magnitude for a 35×25 die. The A2 lattice **bases land on dense,
non-empty, multi-group routing muxes**, exactly as required:

| class | lattice base node | (G, B) at base | non-empty in a naïve contiguous block of `count` |
|-------|-------------------|----------------|--------------------------------------------------|
| R4  | 44198 | (20, 58) | 24,605 / 28,186 |
| R24 | 59111 | (11, 33) |  1,065 / 1,289  |
| C4  | 70654 | (23, 71) | 19,565 / 21,816 |

The blocks are **interleaved, not contiguous** (R24's base 59111 and C4's base 70654 both fall
inside R4's naïve span 44198…72384), so an exact per-class count needs the real (I,X,Y) domains from
the RCF, not a bounding box — a naïve grid over-generates (e.g. C4 grid → 28,115 non-empty ids over
[70654,101019]). **This exact-count reconciliation is a downstream SA task, not a blocker for
locating the segment.** The magnitudes and the base-node structure are consistent with the pool
being the routing route-asm table.

---

## 4. Decompiled-loader evidence (`libddb_dygr.so.c`) — class/thunk match

Serializer / loader entry points that pin the identity (line numbers in the 245k-line decomp):

- **Segment writer (the on-disk spec):** `DYGR_ROUTE_ASM_INFO_BODY::write_data_to_pdb` @147201
  emits the segment with (line **147264**):
  ```
  pdb_write_ptr(base, "_asm"(_LC10), ".ddb"(_LC35),
      pdb_xfr_ptr_func<PDB_SEGMENT_TEMPLATE<PDB_DDB_SEG_BASE>, DYGR_ROUTE_ASM_INFO_BODY>, …)
  ```
  → **filename = `<base>_asm.ddb`**, **one** `PDB_SEGMENT_TEMPLATE<PDB_DDB_SEG_BASE>` segment,
  **root object `DYGR_ROUTE_ASM_INFO_BODY`**, via `DYGR_ROUTE_ASM_INFO_BODY::s_thunk`. (Siblings use
  the same call with `"_routing"`@136730, `"_place"`@110532, `"_timing"`@175496, `"_icname"`@181066.)
- **Root serializer (matches the parser byte-for-byte):** `DYGR_ROUTE_ASM_INFO_BODY::operator<<` @210434
  reads `m_num_asm_nodes` (field 0x345, `xfr_int_delta`), then `m_route_asm_nodes` vector size
  (field 0x347, `xfr_int`), then `num_asm_nodes` × `DYGR_ROUTE_ASM_NODE::s_thunk` (`xfr_new_array`).
- **Loader:** `DYGR_ROUTE_ASM_INFO::load_data` @146565 → `DYGR_ROUTE_ASM_INFO_BODY::load_data` @148363
  → `load_data_from_pdb` @147371 (`PDB_ARCHIVE::open`) → `pdb_xfr_ptr_func<…, DYGR_ROUTE_ASM_INFO_BODY>`
  @148399 (segment tag `0x97`). Gated by die-info section flag **6**
  (`DYGR_DIE_INFO_BODY::load_data` @32996). Source file:
  `quartus/ddb/dygr/dygr_route_asm_info_body.cpp`.

---

## 5. HONEST scope — what this segment covers, and what it does NOT

**Covers (per node, for ALL routing-mux classes):** the ASM pool has one `DYGR_ROUTE_ASM_NODE` per
router node (positional ordinal = the A2 node id). Each non-empty node carries its `m_num_bit_groups`
select sub-fields and, per group, the CRAM `DYGR_ROUTE_ASM_BIT`s (flat address + encoding flags).
This spans **every** mux class — LI/LEIM, C4, R4, R24, C16, direct-links, LE/LUT-input muxes — because
every one is just a node with bit-groups. So SA3 delivers **node → {bit-groups} → bits** for the whole
device.

**Does NOT cover (critical for the mission):** the ASM pool **cannot, by itself, bind a
`{src_node → dest_node}` arc to a specific bit-group.** The resolver proves this:

```
DYGR_ROUTE_ASM_INFO_BODY::get_bits_from_source_to_dest(A, B, out)   @147728
    group = get_destination_bit_group(A, B)     @147601   ← reads DYGR_DIE_INFO::get_route_info()
    node  = get_asm_node(A)                                ← the ASM pool (this segment)
    for k in 0..get_num_bits_in_group(node, group):
        out += { get_flat_address(get_single_bit(node, group, k)), value }
```

`get_destination_bit_group` does **not** touch the ASM pool for the *index* — it indexes
`get_route_info()` (the **route topology**) by node id (0x10-byte records) and finds the other
endpoint's position in that node's **ordered fanin/source array**; that position **is** the group
index. Only then does it read the group's bits from the ASM node.

⇒ **The full static `{src → dest : bits}` connectivity table is a JOIN of two PDB segments:**

| segment | file (EP4CE10) | class | supplies |
|---------|----------------|-------|----------|
| **route-asm pool** (SA3) | `ddb_cycloneive1_asm.ddb` | `DYGR_ROUTE_ASM_INFO_BODY` | per-node bit-**groups** → CRAM bits |
| **route topology** (next SA) | `ddb_cycloneive1_routing.ddb` | `DYGR_ROUTE_INFO_BODY` | per-node **ordered fanin/source list** → the group **index** for each incident source (the `route_element` fanout, 89 refs) |

The dynamic trace only ever observes arcs a specimen exercises; parsing **both** static segments
yields every `{src → group → bits}` edge at once. SA3 nails the *bits half*; a follow-up SA must
parse `DYGR_ROUTE_INFO_BODY` (routing.ddb) for the *fanin-order half* to make arcs, then validate
against `routing_capture.jsonl` / `traceA.json`.

---

## 6. Concrete instructions for extending `ddb_parse.py`

1. **Repoint the die** (do not rewrite the container codec — it is correct):
   - `DDB_PATH = ".../cycloneive/ddb_cycloneive1_asm.ddb"` and a distinct `BODY_CACHE`
     (e.g. `/tmp/ce1_asm_body.bin`).
2. **Update the structural anchors** (the `EXPECT_*` are cycloneive6/EP4CE115 values). For
   cycloneive1/EP4CE10 they are:
   - `EXPECT_NUM_NODES  = 135117`
   - `EXPECT_NUM_USHORT = 1167987`   (sum of `m_num_bit_groups`)
   - `EXPECT_NUM_BIT    = 3503114`   (sum of `m_num_bits`)
   - `EXPECT_BODY_LEN   = 31441834`
   (Or better: drop the hard-coded expectations and just assert `bytes_consumed == body_len` and
   `num_asm_nodes == vector_size`, which hold for every die.)
3. Everything else (`decompress_body`, `DdbAsm`, `iter_node_grouped_records`,
   `get_single_bit`/`get_flat_address`) works unchanged — verified `bytes_match=True` on cycloneive1.
4. **Next SA (not SA3):** add a `DYGR_ROUTE_INFO_BODY` parser for `ddb_cycloneive1_routing.ddb` to
   recover per-node fanin order, then implement `get_destination_bit_group` / `get_bits_from_source_to_dest`
   as the JOIN, and validate against the ground-truth trace.

---

## 7. Independent re-verification (2026-07-27, second run)

Re-derived every load-bearing fact from raw bytes via `verify_sa3.py` (same dir), using only
`ddb_parse`'s container codec + `DdbAsm` — no cached body, no Quartus libs. All reproduced:

| candidate | file_size | zlib | body head `root/f4/f8` | num==vec | verdict |
|-----------|-----------|------|------------------------|----------|---------|
| **`ddb_cycloneive1_asm.ddb`** | 1,405,145 | `7801`@111 | **`4 / 135117 / 135117`** | **True** | **route-asm pool** |
| `ddb_cycloneive1_routing.ddb` | 1,794,438 | `7801`@111 | `4 / 35 / 25` | False | topology (`f4,f8`=`nx,ny`) |
| `ddb_cycloneive1_asmdb.ddb`   | 31,456    | `78da`@111 | `4 / 731253248 / 2101248` | False | asmdb config |

Full byte-exact parse of `ddb_cycloneive1_asm.ddb`: `num_asm_nodes=135117==vector_size`,
`sum_groups=1,167,987`, `sum_bits=3,503,114`, `bytes_consumed==body_len==31,441,834`,
**`bytes_match=True`**; nonempty(B>0)=108,380; G>0=113,180. Lattice bases land on dense multi-group
muxes: R4 44198→(G20,B58), R24 59111→(G11,B33), C4 70654→(G23,B71).

**Die mapping grounded in `ddb_cycloneive.ref`** (not just geometry): `EP4CE10-6` and `EP4CE6-6`
both carry `nx=35, ny=25`; `EP4CE15-6` carries `nx=42, ny=30`. The `routing.ddb` body header
`(f4,f8)=(35,25)` matches `(nx,ny)` for the 35×25 die exactly — direct confirmation that EP4CE10 ⇒
`cycloneive1` **and** that `routing.ddb` is `DYGR_ROUTE_INFO_BODY` (dimensioned by grid), distinct
from the `asm.ddb` pool (dimensioned by node count). **SA3 verdict stands, fully reproduced.**
