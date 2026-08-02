# K2 NODE-CLASS FINALIZE — LE_BUFFER classification fixed & verified

**Deliverable:** `nodeclass_final.json` (this dir) + this note.
**Codec:** node_index → DEV_ELEMENT enum → wire class, harvested from the compiler's OWN
device-file classifier `DYGR_DIE_INFO_BODY::get_element_enum(gid)` @`libddb_dygr.so` 0x127aa0,
swept live over ALL 135,117 routing node ids. Device-file → **design-independent** (holds for every
EP4CE6/EP4CE10 bitstream incl. `target.rbf`).
**Rule:** decode-or-refuse. A class label is emitted only where the enum sweep grounds it; the 49
unlabeled enum blocks stay `null` (REFUSED), never guessed.

---

## 1. Verify — the codec is bit-exact (nothing re-derived)

| check | result |
|---|---|
| reproduces the live enum sweep (`element_enum_dump.jsonl`) | **135117 / 135117**, 0 mismatch |
| held-out fresh independent compile (`R1_holdout_oracle.jsonl`) | **135117 / 135117**, 0 mismatch |
| agrees with grounded cdb↔ddb name table (5339 `back_annotate` names: phase2 devwide C4/R4/R24/C16 + traceA/B) | **5339 / 5339**, **0 conflicts** |
| trace oracle (22 src + 22 dest nodes) block-class vs `back_annotate` wire type | all agree |
| `node_id.BLOCKS` (the integrated table) vs codec `all_enum_blocks` | 57 / 57 blocks, **0 class mismatch** |
| `decode_rbf.py selftest` (codec consumed via `node_id.block_of`) | **ALL PASS** (round-trip 1277/1277, 0 mismatch) |

The `gid` rule is confirmed live: `is_router_id(gid) = bit31 set`, `node_index = gid & 0x7fffffff`.
57 contiguous DEV_ELEMENT enum runs; **8** carry a grounded class (**108,360 / 135,117** nodes named);
the other 49 enum blocks (26,757 nodes: clock / global / direct-link / IO-sub / placer-adjacent) are
exact in range but label-UNKNOWN → REFUSED.

**Named classes (exact extents):**

| class | enum | node range | count |
|---|---:|---|---:|
| LE_BUFFER | 45 | 10320–30959 | 20,640 |
| R4 | 268 | 30971–59156 | 28,186 |
| R24 | 273 | 59157–60445 | 1,289 |
| C4 | 275 | 60446–82261 | 21,816 |
| C16 | 281 | 82262–83587 | 1,326 |
| LOCAL_INTERCONNECT | 282 | 83588–115988 | 32,401 |
| IO_DATAIN | 307 | 118799–119168 | 370 |
| BLOCK_INPUT_MUX | 540 | 122549–124880 | 2,332 |

---

## 2. The LE_BUFFER fix — why sources were mis-typed as C4/R4/R24/C16 metal

**LE_BUFFER = the LUT / LAB-cell OUTPUT buffer**, i.e. the SOURCE of the *LUT-output routing hop*
that feeds C4/R4/R24/C16/LI. The class extent `[10320, 30959]` (20,640 nodes) is exact and pinned by
the enum sweep.

The classification bug was **not** in the enum ranges — it was in *how a source's class was inferred
downstream*. The device-wide interior-connectivity table is built by the pdb allocator simulation
(`dygr_route_parse.RouteFanoutDdb._simulate_allocator`), which assigns each node its fanout template via

```
pool_slot(node) = (array_index(node) + 2512) mod 44260
```

This linear rotation is only valid for `array_index ∈ [20044, 41747]` (the on-disk **non-empty**
template region, slots 22556–44259). Measured over all 20,640 LE_BUFFER nodes:

| quantity | value |
|---|---|
| node_kind split | new 11,251 · back-ref 9,389 |
| array_index range | **[17, 11267]** — entirely BELOW the valid window [20044, 41747] |
| array_index inside valid window | **0 / 20640** |
| rotated pool_slot range | [2529, 13779] — inside the on-disk **EMPTY** region |
| allocator-sim grounded templates | **0 / 20640** (all REFUSED) |

So the whole LE_BUFFER class lives in the low-`array_index` **ramp** the rotation cannot reach.
Consequence in `dygr_connectivity_full.json`: **0 LE_BUFFER-source arcs** device-wide — every static
source is C4 (19,261) / R4 (9,234) / R24 (1,048) / C16 (662). If the rotation were naively *extended*
past its window (a bluff), each LE_BUFFER back-ref source would rotate onto **another** node's template —
predominantly C4/R4/R24/C16 metal — **mis-tagging the LUT-output source as metal** and emitting a false
arc. The allocator sim correctly **refuses** instead (decode-or-refuse), which is why all 5,822 used
LUTs stayed isolated.

**Fix (this deliverable):** the enum codec labels those 20,640 nodes `LE_BUFFER` *authoritatively and
design-independently*, so a source's class no longer depends on the broken rotation. The metal mis-tag
is eliminated **by construction** — classification is the ground-truth enum, not an allocator artifact.

---

## 3. Integrate — so the LUT-output hop can bind

With the source correctly typed `LE_BUFFER`, the LUT-output hop binds through the device-file route
resolver — **not** the allocator sim:

- `DYGR_DIE_INFO_BODY::get_fanout` @0x127e90 → the ordered fanout dest list for an LE_BUFFER source;
- `DYGR_ROUTE_ASM_INFO::get_bits_from_source_to_dest` @0x228d60 → the arc's selector bits.

Proven where fanout is grounded: the two trace-observed LE_BUFFER-source arcs
**26739→68335** and **10618→60851** reproduce **bit-exact (8 selector bits each)**; `decode_rbf.py`
selftest recovers `LE_BUFFER:X10Y6S0I0 → C4` and `LE_BUFFER:X10Y8S0I1 → R4` round-trip-clean.

Integration points (all already consuming this codec):

- `node_id.BLOCKS` == codec `all_enum_blocks` (57 blocks, 0 mismatch); `block_of(n)` types every node.
- `build_connectivity_full.py` `cls_of()` = `node_id.block_of()[0]` → src/dest classes in
  `dygr_connectivity_full.json`.
- `decode_rbf.py` + `connectivity_codec.py` consume it; **selftest ALL PASS**.

**Scope boundary (honest):** this task finalizes the *classifier* — the enabling fix. Realizing all
20,640 LE_BUFFER-source fanout arcs device-wide (≈19,096 selector bits + de-isolating 5,822 LUTs) is
the **T2 edge sweep** (`sweep_le_fanout.py`, get_fanout/get_bits over the LE_BUFFER range) — a distinct
target. Its device-file oracle is not yet harvested (the current gdb inferior-call harness core-dumps
mid-sweep); until it lands those arcs remain REFUSED, never bluffed. What is owned *now* via the
grounded fanout: the 2 trace LE_BUFFER-source arcs (16 selector bits), bit-exact.

---

## 4. Files

- `nodeclass_final.json` — the finalized node→class codec (enum_to_class, 57 exact enum blocks, 8 named
  extents, LE_BUFFER finalize block with the array_index/rotation-window analysis, validation record).
- Oracle (READ-ONLY): `../loop/element_enum_dump.jsonl` (sweep), `../loop/R1_holdout_oracle.jsonl` (held-out).
- Consumers: `dygr_static/node_id.py` (`BLOCKS`/`block_of`), `own/build_connectivity_full.py`,
  `decoder/decode_rbf.py`, `decoder/connectivity_codec.py`.
