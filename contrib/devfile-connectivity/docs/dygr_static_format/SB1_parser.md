# SB1 — DYGR route-asm connectivity parser

**Deliverable:** `<repo>/devfile/dygr_route_parse.py` — extends
`ddb_parse.py` (reuses its byte-exact container / PDB-segment reader + `DdbAsm`
verbatim; the container is **not** rewritten) into an in-memory **edge model** of the
Cyclone IV (`cycloneive1` = EP4CE6/EP4CE10 die) DYGR route assembler, plus the
routing-topology fanout that binds a group index to a dest node.

Run (numpy needs `LD_LIBRARY_PATH` unset — GLIBCXX clash under the Quartus libs):

```
LD_LIBRARY_PATH= python3 <repo>/devfile/dygr_route_parse.py
```

**Headline:** the asm-pool half reproduces the shipping resolver
`DYGR_ROUTE_ASM_INFO_BODY::get_bits_from_source_to_dest` **byte-exactly** — validated
21/23 (0 mismatched) against the READ-ONLY live trace. The routing half parses
`base_gid[]` (byte-exact, device-wide) and the fanout template-offset pool (byte-exact,
44260 templates); the one residual is the node→template pdb permutation (sec.5).

---

## 1. What it produces

```
for each SRC router node  (ordinal == gid & 0x7fffffff)
   -> its bit-GROUPS (mux select sub-fields + trailing exclusion groups)
        -> each group's DYGR_ROUTE_ASM_BIT list  { flat_address, value }
```

Bit value = `DB_BIT_SETTING`: `1 if use_encoded_setting()==0 else is_encoded_bit_high()`.
`flat_address` = `DYGR_ROUTE_ASM_BIT::get_flat_address()` (region tag `0xA0000000`
OR-ed when the cff flag is set; 0 occurrences on ce1). Feed to `bitpos_to_rbf.py` for
`flat <-> rbf` (proven elsewhere).

The full resolver is reproduced:

```
DYGR_ROUTE_ASM_INFO_BODY::get_bits_from_source_to_dest(src, dest)   @0x32ac80
    k    = get_destination_bit_group(src, dest)                     @0x32aa50
    bits = { src.bit_group[k] as PROGRAMMED }   (select field, from asm pool)
         U { dest.exclusion_group[*] forced to 0 }  (exclusion field, from asm pool)
```

API (see module docstring for the full list):

| call | returns |
|---|---|
| `RouteAsmModel().node_groups(n)` | `List[List[Bit]]` — every bit-group of node `n` |
| `.group_bits(n, g)` | the select field for group `g` (`[{flat,value,...}]`) |
| `.exclusion_bits(dest, fanout_size)` | dest's trailing exclusion groups, forced 0 |
| `get_bits(model, src, dest, oracle)` | the exact `{first: flat, value}` set the assembler emits, or `None` (refuse) |
| `RouteFanoutDdb().base_gid(n)` / `.pool` | routing.ddb `m_fanout_edge_base[n]` + template offset arrays |

`get_bits` takes a pluggable **FanoutOracle** supplying the two routing-derived facts
(`k` and `fanout_size`):

* `TraceFanoutOracle` — the READ-ONLY live trace (`routing_capture.jsonl`); used to
  **validate** the assembly model end-to-end.
* `RoutingDdbFanoutOracle` — the device-wide **static** oracle backed by
  `RouteFanoutDdb` (the `ddb_cycloneive1_routing.ddb` parse). base_gid[] is byte-exact
  and the template pool is byte-exact; the node→template bind is the one residual
  (sec.5), so it answers decode-or-refuse.

Decode-or-refuse throughout: `get_bits` returns `None` for any `(src,dest)` whose group
index or dest exclusion boundary the oracle cannot ground — it never guesses an edge.

---

## 2. ASM pool — BYTE-EXACT, whole device

`ddb_cycloneive1_asm.ddb` (SA3) → `DYGR_ROUTE_ASM_INFO_BODY`, decoded by `DdbAsm`:

```
num_asm_nodes = 135117 (== vector_size)   bytes_consumed == body_len == 31,441,834
sum_group_counts = 1,167,987   sum_bit_counts = 3,503,114   nonempty_nodes = 108,380
```

`bytes_match == True` (whole body consumed, 0 tail) is the proof the on-disk layout
matches. Per-node group boundaries come from `m_start_bit_index` deltas
(`DdbAsm._node_group_offsets`, ushort-wrap corrected). This spans **every** mux class —
LI/LEIM, C4, R4, R24, C16, direct-links, LE/LUT-input muxes — because each is just a
node with bit-groups (SA3 §5).

### Validation vs the live trace (ground truth)

`get_bits(model, src, dest, TraceFanoutOracle)` reproduced the trace's `arc` bit sets:

```
arcs = 23   matched = 21   refused = 2   mismatched = 0
```

- **matched = 21**: identical `{flat: value}` set (select + exclusion), order-independent.
- **refused = 2**: dests never seen as an *arc destination* in the trace, so the trace
  oracle cannot derive their `fanout_size` — decode-or-refuse, not an error.
- **mismatched = 0**.

Named-edge check `26739 -> 68335` (k=4): asm node 26739 group 4 gives the select
`{740029:1, 740031:0, 741758:1}`; dest 68335's exclusion groups (fanout_size=19, groups
19–20) contribute `{740028:0, 740030:0, 741755:0, 741756:0, 741757:0}` — together the
**exact 8-bit** trace arc. (Note: 68335's exclusion cells live in the 740xxx region —
the SOURCE-side LAB cells that must be cleared — not in 68335's own 25xxxx select
region; the asm pool carries them as that node's trailing groups, so no cross-node data
is needed.)

The select field alone (from `group_bits(src, k)`) already captures **every value-1
(selection) bit** and the group's own value-0 bits, byte-exact, for all checked arcs.

---

## 3. ROUTING.DDB fanout format (the src→dest bind)

`ddb_cycloneive1_routing.ddb` → `DYGR_ROUTE_INFO_BODY`. On-disk layout, grounded in
`DYGR_ROUTE_INFO_BODY::operator<<` @217464, `DYGR_ROUTE_ELEMENT::operator<<` @209875,
`DYGR_ROUTE_ELEMENT_TEMPLATE::operator<<` @209797, and the PDB pointer codec
`PDB_SEGMENT_READER::xfr_ptr` @0x10bfe0 (libdb_pdb):

```
[u32 root=4][i32d nx=35][i32d ny=25]
m_route_element_list      : [u32 N=135117] + N x 12-byte DYGR_ROUTE_ELEMENT
      DYGR_ROUTE_ELEMENT   = [i16d][i16d][i32d m_fanout_edge_base][u32 m_template desc]
m_route_element_templates : [u32 44260] + 44260 x u32 back-ref descriptor
TEMPLATE-BODY POOL @0x1B7F80 (byte 1,798,464; the 44260 deferred-flushed bodies):
      [i16d m_element_enum][i16d m_num_edges][i16d][i16d m_index]
      [fieldv16 fpre][fieldv8 len][fieldv4 metal][fieldv4 dir]
      [u16 cnt][cnt x i32 (per-array cumulative from 0)  m_fanout_list_offsets]
      [u16 cnt][cnt x i16  m_fanout_to_positions]
```

**Key finding — deferred-flush pointers.** `xfr_ptr` for a "new object" descriptor
(`desc & 3 == 0`, e.g. `12` = class 3) does **not** serialize the body inline; it pushes
the object onto a pending list (`this+0x158`, libdb_pdb line 11810) that is **flushed as
a batch later**. That is why every `DYGR_ROUTE_ELEMENT` is a fixed 12 bytes (proven: the
`m_fanout_edge_base` cumulative chain is byte-exact and `offset[0]==0` for every node)
while the 44260 template bodies form one contiguous pool at 0x1B7F80. Element
`m_template` descriptors and the `m_route_element_templates` vector are back-ref/new
descriptors into the pdb pointer registry.

**Resolver** (`get_destination_bit_group` @0x32aa50, confirmed at line 98811):

```
rec       = route_node_base + (src & 0x7fffffff)*0x10
base_gid  = *(i32*)(rec+4)                     = m_fanout_edge_base[src]
template  = *(ptr*)(rec+8)                      = m_template[src]
fanout[k] = base_gid + template.offsets[k]      k in [0, num_edges) ;  offset[0] == 0
return the k with fanout[k] == dest_gid (0xffffffff if absent)
```

`k` is directly the SRC asm-node group index; `num_edges` is the SRC `fanout_size`, and
`get_num_exclusion_groups(dest) = dest.num_bit_groups − num_edges(dest)`.

### What is validated in `RouteFanoutDdb`

- **`base_gid[]` — byte-exact, whole device.** `offset[0]==0` ⇒ fanout edge 0 == base;
  both trace `gi==0` arcs confirm `base_gid[src] == dest_gid` exactly
  (`34950→38082`, `40270→39602`). 80,625 / 135,117 nodes have a router-range base (the
  rest are sinks / no-fanout nodes).
- **Template-offset POOL — byte-exact.** 44,260 templates parse cleanly from 0x1B7F80
  to byte 10,682,308 (per-array-cumulative offsets, `offset[0]==0`). The C4 join is
  exact: `base[68335] + pool[35037][7] = gid(68339)` and `… + pool[35037][9] =
  gid(93801)`; `base[68339] + pool[35043][2] = gid(84783)`.

---

## 4. Coverage — honest statement

| routing class | node → {group → bits} (asm) | src→dest group bind (routing) |
|---|---|---|
| **all classes** (LI/LEIM, C4, R4, R24, C16, direct-links, LE/LUT muxes) | **YES — byte-exact, whole device** | base_gid byte-exact for all; group index: see below |
| **C4 / R4 (high-fanout)** | yes | base+offset join reproduces the trace exactly |
| **low-fanout / LI taps** | yes (bits) | node→template **pdb permutation residual** (sec.5) — decode-or-refuse |

- The **bits half is complete for the entire device** and byte-exact (sec.2). Given a
  group index (from any oracle — trace or the eventual full routing bind) `get_bits`
  emits the exact bitstream setting, validated 21/23 against ground truth.
- The **routing half** delivers byte-exact `base_gid[]` and a byte-exact template
  offset pool. The remaining piece is the node→pool-template map (sec.5).

Against the final coverage target `target.rbf` (EP4CE10, same `cycloneive1` die):
the asm pool + base_gid + pool apply directly (same node-id space, same 368011-B rbf
geometry). Every node's `{group → flat bits}` decodes today; arcs decode wherever a
group index is grounded.

---

## 5. Residual — the node → template pdb permutation

`get_destination_bit_group(src,dest)` needs `src`'s template (its ordered offset array).
Each `DYGR_ROUTE_ELEMENT` stores its template as a 4-byte pdb pointer descriptor; the
44260 bodies are deferred-flushed to the pool in **pdb-id / vector order**, which is a
permutation of element creation order. Concretely:

```
pool_index(node) = pdb_id(node.m_template) − p0
     pdb_id(·)  : resolve the element/vector descriptor through the xfr_ptr registry
                  (new: id = per-class counter++ ; back-ref: last_ref += desc>>2 ; ...)
     p0         : the first pdb-id the m_route_element_templates vector references
                  (its descriptors are 0xfffd4c76 then +1 each ⇒ a contiguous run)
```

Two solid ground-truth pins exist (`68335 → pool 35037`, `68339 → pool 35043`, from
unique offset signatures), and the model lands **within ±1** of them but is not yet
bit-exact — the exact `0x24` (creation counter) vs `0x2c` (back-ref last-ref) update
rule in `xfr_ptr` (libdb_pdb @0x10bfe0) needs pinning. Until then the static oracle
answers only where a unique-and-corroborated bind exists; the offset-search shortcut
(`RouteFanoutDdb.bind_edge`) is **diagnostic only** — it is unreliable for low-fanout
nodes (e.g. `26739→68335` binds a spurious template at k=11) and must **not** be trusted
as the group index. This is the single remaining task to make the routing oracle
device-wide; everything it needs (`base_gid[]`, the offset pool, the resolver semantics)
is already parsed and validated.

Interim device-wide group indices are available with full integrity from the
`TraceFanoutOracle` (for exercised arcs) or `quartus_cdb --back_annotate=routing`
(SA2 §7) — both READ-ONLY, no fuzzing.

---

## 6. Files

- `dygr_route_parse.py` — the parser (this deliverable).
- `ddb_parse.py` — reused container/PDB reader + `DdbAsm` (unchanged).
- Body caches (regenerated on demand): `/tmp/ce1_asm_body.bin`,
  `/tmp/ce1_routing_body.bin`.
- Ground truth (READ-ONLY): `re_workflows/out/debugger/harness/logs/routing_capture.jsonl`.
