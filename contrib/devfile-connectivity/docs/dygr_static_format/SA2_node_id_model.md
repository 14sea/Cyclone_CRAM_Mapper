# SA2 — Node-ID Model (global gid ↔ pool index ↔ (class, I, X, Y, S))

Goal: given a node_id from the DYGR route-asm connectivity table, output its
`(class, I, X, Y)` and vice-versa, so the static table is fully node-resolved and
joinable to `quartus_cdb` names. Everything below is grounded in the decompiled
`libddb_dygr.so`, the phase2 device-file-grounded codec tables, and the READ-ONLY
live routing trace. Decode-or-refuse: no edge/coord is claimed that cannot be grounded.

Device note: the routing-graph **node ordinal space is per-die**, keyed on die base
`cycloneive1`. EP4CE6 and the EP4CE10 target share this die base and the same
368011-B rbf geometry, so the node model transfers.

> **REVISION (this pass).** An earlier revision of this model mis-ranged the class
> blocks and declared low-I nodes "UNMAPPED" (and even claimed node `68335` was
> "provably not C4"). That was an artifact: the phase2 tables it fit are a **HIGH-I
> subset** of each class (C4 I=12..17, R4 I=17..22, R24 I=0). The live-trace ground
> truth (`traceA/B.json`) names those same "UNMAPPED" nodes — `68335` **is**
> `C4:X16Y19S0I9`, `93801` **is** `LOCAL_INTERCONNECT:X16Y22S0I12`, etc. Folding the
> trace in extends the domains DOWN and the model is now exact over all grounded
> points. All corrections below are grounded, not guessed.

---

## TL;DR — the model in one box

```
gid  (32-bit global id, what the resolver takes for src AND dest)
 ├─ bit31 = 1  → ROUTER node  (interconnect wire)   ← the connectivity-table ids
 ├─ bit31 = 0  → PLACER node  (atom: LE/IO/RAM/PLL cell)
 └─ 0xFFFFFFFF = DEV_ILLEGAL_GLOBAL_ID

node_index = gid & 0x7fffffff          # get_node_index_of_id  (the POOL INDEX)
router_gid = node_index | 0x80000000   # inverse

node_index is the POSITIONAL ordinal into the routing-graph node vector — the SAME
ordinal ddb_parse.py uses (the ASM node record stores no id field). The vector is a
concatenation of per-element (per-class) CONTIGUOUS blocks. Inside a block the
(I,X,Y)→ordinal enumeration is (piecewise) AFFINE — the validated lattices:

  C4  : node = 60444 + 832*I + 24*X + Y      for I ∈ [0, 9]     ┐ both sX=24; sY=1
        node = 60836 + 798*I + 24*X + Y      for I ∈ [10,22]    ┘ 3153/3153 EXACT
  R4  : node = 30925 + 760*I + 23*X + Y      (I 5..22)  1779/1782 (left-edge)
  R24 : node = 59111 +   0*I + 23*X + Y (I=0)           361/363   (X8 edge)

Runtime truth-source (device-file lookup, not a formula):
  get_location(gid,&loc)   → X,Y,S,I    get_element_enum(gid) → class
```

Helper implementing all of this + a validated classifier: **`node_id.py`** (same dir).

---

## 1. The gid encoding — proven from decompile + trace

All in `libddb_dygr.so.c` (`decompiled/.../libddb_dygr.so/libddb_dygr.so.c`):

| fn @ addr | line | body | meaning |
|---|---|---|---|
| `DYGR_DIE_INFO_BODY::is_router_id` @ 0x227920 | 29504 | `return param_1 + 0x80000000 < 0x7fffffff;` | true iff bit31 set AND != 0xffffffff |
| `DYGR_DIE_INFO_BODY::is_placer_id` @ 0x227910 | 29492 | `return ~param_1 >> 0x1f;` | true iff bit31 clear |
| `DYGR_DIE_INFO_BODY::get_node_index_of_id` @ 0x228120 | 29873 | `return param_1 & 0x7fffffff;` | strips the router flag → **pool index** |

The two id spaces are split purely by bit 31; the low 31 bits are the pool index in
both spaces (router pool vs placer/atom pool).

**Trace confirmation** (`routing_capture.jsonl`): every record has `raw = id |
0x80000000` exactly (e.g. `raw 2147510387 = 26739 | 0x80000000`), all `is_router:
true`. So the trace's `source.id`/`dest.id` are already the **node_index**. The
resolver `get_destination_bit_group(src_gid, dest_gid)` takes router gids for both
endpoints (asserted `dygr_is_router_id(src_gid) && dygr_is_router_id(target_gid)`,
`libddb_dygr.so.c` line 98804). The DOT-dumper names a node `"RE_NODE_%u"` of this
ordinal (`ASM_RE_DOT_DUMPER::get_routing_element_id`, `libcomp_asm.so.c` line 38561).

## 2. node_index → (class, X, Y, S, I): the per-node array (runtime truth)

The authoritative map is a **device-file LOOKUP TABLE**, not a closed form, read from
`DYGR_ROUTE_INFO_BODY` (loaded from `ddb_cycloneive1_routing.ddb`). Two accessors
index a per-node 0x10-byte record at `rec = base + node_index*0x10`:

`DYGR_DIE_INFO_BODY::get_location(gid, DEV_LOCATION&)` @ 0x227930 (line 29516), router
branch:

| rec offset | reads into DEV_LOCATION slot | meaning |
|---|---|---|
| `+0x00` (short) | slot `0xd` | **X** |
| `+0x02` (short) | slot `0xe` | **Y** |
| `+0x08` (ptr) → `[+4]` (short) | slot = `get_third_dimension_enum()` | **S** (third dim) |
| `+0x08` (ptr) → `[+6]` (short) | slot `1` | **I** (wire index in bundle) |

`DYGR_DIE_INFO_BODY::get_element_enum(gid)` @ 0x227aa0 (line 29579), router branch:
`element_enum = *ushort at *(rec+0x08)` — the **class** (a `DEV_ELEMENT` enum). The
`+0x08` pointer is a shared per-(class,S,I) element descriptor; the per-node record
only individuates X,Y.

So the authoritative resolution of ANY node id is: `get_element_enum` → class,
`get_location` → (X,Y,S,I). No fuzzing, no lattice — pure table read. The lattices in
§4 reconstruct this map statically for the classes we have grounded.

## 3. The per-element partition (why the space is blocked)

`get_global_id_of_element(elem_desc, i)` @ 0x2276f0 and `get_num_element(elem_desc)` @
0x227540 delegate to `DYGR_ROUTE_INFO::get_global_id(element_enum, index)` /
`get_num_element(element_enum)`. Each routing element (class) owns a **contiguous
block** of node indices:

```
get_global_id_of_element(elem, i) = base[elem] + i      # bit31 OR-ed in for the gid
node_index ∈ [ base[elem] , base[elem] + count[elem] )
```

The node vector is the concatenation of these blocks. The lattices are the
within-block `(I,X,Y) → (index - base[elem])` raster enumerations.

## 4. The validated affine lattices — reconciled, fit, validated

Fit against **all** grounded points (phase2 devwide codec tables **plus** the live
trace), where each dest/src node is named `TYPE:XxYySsIi` by `quartus_cdb
--back_annotate=routing` and bound to its ddb node ordinal. All coefficients are
**exact integers**. `node_id.py __main__` reproduces:

| class | affine `node_index =` | I dom (seen) | X dom | Y dom | encode exact | decode unique-correct |
|---|---|---|---|---|---|---|
| **C4** (I≤9)  | `60444 + 832·I + 24·X + Y` | 0..9  | 8..36 | 0..23 | ┐ **3153/3153** | ┐ **3153/3153** |
| **C4** (I≥10) | `60836 + 798·I + 24·X + Y` | 10..22| 8..36 | 0..23 | ┘ (both regimes)| ┘ |
| **R4**  | `30925 + 760·I + 23·X + Y` | 5..22 | 6..25 | 2..21 | 1779/1782 | 1779/1782 |
| **R24** | `59111 + 23·X + Y` (I=0)   | 0     | 3..31 | 2..21 | 361/363   | 361/363   |

- **C4 is piecewise in I** — two affine regimes, both `sX=24, sY=1`. The residual of
  the single-798 fit is exactly `−392 + 34·I` for I≤9 (⇒ the `+832` low regime) and
  `0` for I∈[10,22]. This is a real, clean discontinuity between I9 and I10 (I10/I11
  unsampled but bracketed). The **mission's C4 formula**
  `70654+798·(I−12)+24·(X−10)+(Y−2) ≡ 60836+798·I+24·X+Y` is exactly the **I≥10
  regime**; the I≤9 regime is the new grounding this pass adds.
- **R4** single regime; the 3 misses are left-edge X6/X7 (off by 10..15). The
  mission's `44198+760·(I−17)+23·(X−15)+(Y−8) ≡ 30925+760·I+23·X+Y` — same lattice,
  I-domain now extended down to 5.
- **R24** 2 misses at the X8 left edge (off by 5). Matches mission `59111+23·X+Y`.
- **Inversion is NOT a plain divmod.** Because X starts at 8 (C4)/6 (R4), the per-I
  offset (`24·X+Y`) exceeds the I-stride, so I-bands overlap in raw offset space.
  `decode_lattice` iterates the small I domain (both C4 regimes) and keeps in-domain
  candidates — 0 ambiguities over the enumerated device.

## 5. Corrected grounded block partition

Grounded node spans (min..max seen) per class, ordered by ordinal. `class = —` marks
a **gap between grounded blocks**: real element block(s) whose class is not yet bound
(NOT relabelled — decode-or-refuse). Block edges within a grounded class are the
observed extent; true edges may be a little wider.

| node_index span | class | how grounded / note |
|---|---|---|
| `0 – 10603` | — | below LE_BUFFER; LI/LEIM/LOCAL_INTERCONNECT-input / other, unbound |
| `10604 – 26739` | **LE_BUFFER** | 4 named (I0..25) |
| `26740 – 34949` | — | gap LE_BUFFER..R4; unbound (LOCAL_LINE/LEIM candidates); R4 I<5 may reach up |
| `34950 – 48241` | **R4** | affine, I5..22 grounded (was mis-ranged 43985.. = the I≥17 subset) |
| `48242 – 59181` | — | gap R4..R24; unbound |
| `59182 – 59843` | **R24** | affine, I=0 |
| `59844 – 60635` | — | small gap R24..C4 |
| `60636 – 78793` | **C4** | two-regime affine, I0..22 (was mis-ranged 70606..75289 = the I12..17 subset; the old "UNMAPPED_B" is C4 low-I) |
| `78794 – 82371` | — | gap C4..C16; unbound |
| `82372 – 83581` | **C16** | 13 named (I0..8); per-coord affine not yet fully fit |
| `83582 – 83938` | — | small gap |
| `83939 – 103953` | **LOCAL_INTERCONNECT** | 13 named (I0..25); the LI **wall class**, now node-ranged (was "UNMAPPED_D") |
| `103954 – 118744` | — | gap; unbound. `118745 = SCLK_TO_ROWCLK_BUF` grounded |
| `118745 – 118895` | **CLK_ROWCLK** | `SCLK_TO_ROWCLK_BUF:X17Y5` grounded |
| `118896 – 119145` | **IO_DATAIN** | 8 named (I0..1) |
| `119146 – 122602` | — | gap; unbound |
| `122603 – 123968` | **BLOCK_INPUT_MUX** | 3 named (I0..13) |

## 6. Classification of the observed live-trace node ids (corrected)

Verbatim `node_id.py` output — **all 29 now resolve to an exact grounded name**
(previously only 5 resolved; the rest were wrongly "UNMAPPED/none"):

```
    10618  LE_BUFFER           exact   LE_BUFFER:X16Y22S0I0
    26739  LE_BUFFER           exact   LE_BUFFER:X16Y18S0I25     ← was "LOCAL/none"
    34950  R4                  exact   R4:X9Y18S0I5              ← was "LOCAL/none"
    38082  R4                  exact   R4:X13Y18S0I9
    39602  R4                  exact   R4:X13Y18S0I11
    40270  R4                  exact   R4:X9Y18S0I12
    60851  C4                  exact   C4:X16Y23S0I0             ← was "UNMAPPED_B/none"
    68335  C4                  exact   C4:X16Y19S0I9             ← was "provably not C4" (WRONG)
    68339  C4                  exact   C4:X16Y23S0I9
    70813  C4                  exact   C4:X16Y17S0I12
    71614  C4                  exact   C4:X16Y20S0I13
    82372  C16                 exact   C16:X8Y3S0I0
    82373  C16                 exact   C16:X8Y5S0I0
    82931  C16                 exact   C16:X16Y21S0I1
    83384  C16                 exact   C16:X8Y1S0I5
    83520  C16                 exact   C16:X8Y1S0I7
    83957  LOCAL_INTERCONNECT  exact   LOCAL_INTERCONNECT:X16Y18S0I0   ← was "UNMAPPED_D/none"
    84783  LOCAL_INTERCONNECT  exact   LOCAL_INTERCONNECT:X16Y24S0I1
    91337  LOCAL_INTERCONNECT  exact   LOCAL_INTERCONNECT:X16Y18S0I9
    91368  LOCAL_INTERCONNECT  exact   LOCAL_INTERCONNECT:X17Y24S0I9
    93801  LOCAL_INTERCONNECT  exact   LOCAL_INTERCONNECT:X16Y22S0I12  ← was "UNMAPPED_D/none"
    94621  LOCAL_INTERCONNECT  exact   LOCAL_INTERCONNECT:X16Y22S0I13
   103953  LOCAL_INTERCONNECT  exact   LOCAL_INTERCONNECT:X16Y18S0I25
   118896  IO_DATAIN           exact   IO_DATAIN:X9Y0S1I0        ← was "CLK/class-only"
   118902  IO_DATAIN           exact   IO_DATAIN:X16Y24S1I0
   119088  IO_DATAIN           exact   IO_DATAIN:X9Y0S3I0
   119145  IO_DATAIN           exact   IO_DATAIN:X16Y24S3I1
   122603  BLOCK_INPUT_MUX     exact   BLOCK_INPUT_MUX:X17Y24S0I0
   123131  BLOCK_INPUT_MUX     exact   BLOCK_INPUT_MUX:X16Y24S0I5
```

**The seq1/seq2 arc `26739 → 68335 → 93801`** is fully node-resolved:
`LE_BUFFER:X16Y18S0I25 → C4:X16Y19S0I9 → LOCAL_INTERCONNECT:X16Y22S0I12` — an LE
output driving a C4 wire that feeds a local-interconnect tap. Every node classifies.

Beyond the exact table, the lattices resolve **any** in-domain C4/R4/R24 node not
present in the grounded set (e.g. `classify(65094, use_table=False) →
C4:X20Y10S0I5`, confidence `lattice`).

## 7. Authoritative completion path (for the still-UNBOUND gaps)

Any node id resolves exactly via the runtime table (§2). To bind the remaining gap
blocks (§5, `class = —`) and give C16/LI exact per-coord affine, two device-file
(non-fuzz) dumps:

1. **`get_element_enum` + `get_location` sweep.** In a `quartus_asm`/`quartus_cdb`
   process holding a `DYGR_DIE_INFO_BODY*`, loop `idx = 0 … num_asm_nodes-1` calling
   `get_element_enum(idx|0x80000000)` (class) and `get_location(...)` (X,Y,S,I). Where
   `element_enum` changes = a block boundary → yields `base[elem]`/`count[elem]` for
   every class and (class,X,Y,S,I) for every id — the complete partition, superseding
   §5. (gdb `call` or a small dlopen harness.) Equivalent: statically parse the
   `DYGR_ROUTE_INFO_BODY` node vector out of `ddb_cycloneive1_routing.ddb` (same 0x10
   record layout as §2) — an SB2-adjacent parse.
2. **`quartus_cdb --back_annotate=routing`** on a design exercising the unbound
   classes → `.rcf` names every wire `TYPE:XxYySsIi`; join to node ordinals via shared
   emitted config bits (A2/decode_rbf path) to bind the gap blocks and fit their
   affine maps exactly as C4/R4/R24 were done.

(`DUMP_ASMRE`/`asm_dump_re_network` do not emit files for the cycloneive
`assemble_dev_device` path — not a shortcut here.)

## 8. Coverage — honest statement

| routing class | node-id → (class,I,X,Y)? | basis |
|---|---|---|
| **C4** | **yes, exact bijection** (I 0..22, two regimes) | affine + devwide + trace, 3153/3153 |
| **R4** | **yes** (±≤15 at 2 left-edge cols), I 5..22 | affine + devwide + trace, 1779/1782 |
| **R24** | **yes** (±5 at X8 col), I=0 | affine + devwide, 361/363 |
| **C16** | class + node-range yes; per-coord affine partial | 13 named (I0..8) |
| **LOCAL_INTERCONNECT** (LI wall class) | **node-range yes**; exact for the 13 named | trace-grounded span 83939..103953 |
| **LE_BUFFER / IO_DATAIN / BLOCK_INPUT_MUX / CLK_ROWCLK** | node-range + named points | trace-grounded |
| gap blocks (§5 `—`) | **no** (block exists, class unbound) | needs §7 |

The gid↔node_index↔pool-index mechanism (§1–§3) is **complete and proven** for every
class. The node_index→(I,X,Y) *closed form* is now exact for C4/R4/R24 across their
full I-domain, node-ranged (and exact at named points) for C16/LI/LE_BUFFER/IO/BIM/
clk, and pending only for the between-block gaps — all obtainable exactly via §7.

## 9. Deliverables & usage

- **`node_id.py`** (this dir) — `is_router_id/is_placer_id/node_index/router_gid`;
  `encode(cls,I,X,Y)` (C4 two-regime) / `decode_lattice(cls,n)`; `block_of(n)`;
  `classify(gid_or_index)` → `{node_index, block, class, coords, name, confidence,
  note}`. Order: (1) exact device-file table (phase2 devwide + traceA/B), (2) affine
  lattice inverse, (3) grounded block bucket, else **refuse** (`confidence='none'`).
  `python3 node_id.py` runs the validation + trace classification above.
- Join key to `quartus_cdb`: the `name` field (`TYPE:XxYySsIi`) or the raw ordinal
  (`RE_NODE_<node_index>`).

```
>>> import node_id
>>> node_id.classify(2147551983)          # raw router gid from the trace (68335)
{'class':'C4','name':'C4:X16Y19S0I9','coords':{'X':16,'Y':19,'S':0,'I':9},'confidence':'exact', ...}
>>> node_id.encode('C4', 9, 16, 19)
68335
>>> node_id.classify(65094, use_table=False)   # not in table → lattice
{'class':'C4','name':'C4:X20Y10S0I5','confidence':'lattice', ...}
```
