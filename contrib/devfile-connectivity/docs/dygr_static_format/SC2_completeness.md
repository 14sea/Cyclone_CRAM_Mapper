# SC2 — Completeness / Coverage Critic (independent re-measure)

**Role:** adversarial completeness audit of the static DYGR connectivity table
(`dygr_connectivity.json`, SB2) against the real target
`target.rbf` (EP4CE10, die `cycloneive1`).
Everything below was **re-measured from the raw device files and the raw rbf**, not copied
from the SB2/SC1 self-reports. Numbers I reproduced independently are marked ✓.

---

## 0. One-paragraph verdict

The table is **bit-exact where it commits and honestly refuses the rest** — the decode-or-refuse
contract holds under independent re-measure (0 mismatches on specimenA/specimenB/the foreign target). But it
is **partial by source coverage, and the partition is structural, not incidental.** The genuine
breakthrough is real: the **LI ("wall") class is bound as a routing DESTINATION for the first time**
(was 0; now **2,523 LI-dest arcs decoded bit-exact from the real the foreign target bitstream**, 88,498
enumerated device-wide). But three whole endpoint classes remain unbound — **LUT outputs
(LE_BUFFER as source), the LEIM/BLOCK_INPUT_MUX final port select, and all 90,857 pdb back-ref
sources** — so full LUT-to-LUT net reconstruction is *not* yet possible from the static table alone.
On the real target the table source-binds **7,987 interior muxes** vs a **2/213** baseline, but that
is **~11 % of the active interior muxes it can even see**, and a smaller fraction of all active
interior routing.

---

## 1. What "coverage" means here — two independent halves

The resolver factors as `get_bits_from_source_to_dest(src,dest)` = **(a)** pick destination
bit-group `k = get_destination_bit_group(src,dest)` (needs the **fanout/topology** = which src
reaches which dest), then **(b)** emit that group's CRAM bits (the **asm** pool). The two halves
have *very different* coverage and must be reported separately:

| Half | What it maps | Coverage | Grounding |
|---|---|---|---|
| **Bits half** (asm pool) | node ordinal → bit-group → flat CRAM address + value | **byte-exact, WHOLE DEVICE, ALL classes** ✓ | `bytes_consumed==body_len`; 0 unmapped flat addrs over 1,040,983 select bits on the foreign target ✓ |
| **Topology half** (src→dest binding) | which src node drives which dest mux | **PARTIAL — ~18 % of source nodes** | +2513 band map; inductive, refuses outside band |

**The bits half is done. The topology half is the whole coverage story.** Every gap below is a
topology (source-binding) gap; none is a bits gap.

---

## 2. Device-wide source-binding budget (re-measured ✓)

From `ddb_cycloneive1_asm.ddb` + `ddb_cycloneive1_routing.ddb`:

```
router nodes total ...................... 135,117
  pure sinks (0 asm bit-groups) .........  21,937   (no outgoing fanout — nothing to bind)
  real SOURCES (>0 asm groups) .......... 113,180   <- the honest source denominator
    template-creating (new-obj) .........  43,566 non-sink
    back-ref (share a template) .........  69,614 non-sink
```

Directed interior arcs device-wide ≈ **941,627** (Σ asm bit-groups 1,167,987 − ~2 exclusion
groups/dest). The table enumerates **352,674** = **~37 %** of device-wide arcs — but concentrated
where sources are bindable.

**Source nodes actually bound: 20,461 / 113,180 = 18.1 %.** The other 81.9 % are refused:

| Refused source bucket | count | why |
|---|---|---|
| back-ref sources (all) | 69,614 | share a template via pdb back-ref delta chain; template only resolvable where trace/cdb grounds it — **not enumerated** |
| new-obj out-of-band (ci<20043 / low-ci) | 23,105 | `+2513` pool-slot offset is wrong there (early-stream pdb deferred-materialization shifts array order) |
| **bound (band, ci∈[20043,41746])** | **20,461** | the +2513 map, cross-validated 3 ways |

This is the correct, sobering denominator. "20,461 sources" is **18 %**, not "most of the device."

---

## 3. Coverage by routing CLASS (source-bind side)

Which classes can appear as a **bound SOURCE** in an enumerated arc (re-measured from the table ✓):

| Class | bound as SOURCE? | bound as DEST? | note |
|---|---|---|---|
| **C4** | ✅ 10,549 srcs (primary) | ✅ 65,124 | the well-covered class |
| **R24** | ✅ 562 | ✅ 2,579 | partial |
| **C16** | ✅ 479 | ✅ 6,623 | partial |
| **R4** | ⚠️ 393 (~part) | ✅ 46,709 | **~85 % of R4 sources refused** (low-ci) |
| **LOCAL_INTERCONNECT / LI** ("wall") | ❌ **0 as source** | ✅ **88,498** | **the breakthrough — but DEST-side only** |
| **LE_BUFFER** (LUT output) | ❌ **0** | (n/a, it's a source) | **entire LUT-output first hop refused** |
| **LEIM / BLOCK_INPUT_MUX** (LUT-input port) | ❌ 0 | ❌ 0 | separate resolver (§5) |
| **IO_DATAIN / CLK / direct-links** | ❌ 0 | ❌ 0 | low-ci / hardwired / separate |
| **UNBOUND_GAP** (unclassed ids) | 8,478 | 143,141 | ids exact, class label pending die-info bind |

Read carefully: **"classes_covered" in the SB2 header conflates the bits half with the topology
half.** For the *bits* half all classes are present (true). For *source-binding* the honest list is
**C4 (good), R24/C16 (partial), R4 (poor), everything else 0.** LI is bound **only as a destination.**

---

## 4. Coverage on the REAL target `target.rbf` (re-measured ✓)

Device-wide mux inversion (group table arcs by (dest,bit_group), read the actual select bits from
the real bitstream, decode-or-refuse). My independent re-run reproduces SC1 exactly:

```
dest muxes the table can see .............. 285,332   (muxes with ≥1 BAND source)
  UNUSED (all select bits 0) .............. 210,902   (mux carries no signal in this design)
  ACTIVE ................................... 74,430
    DECODED (bit-exact to one arc) .........  7,987   <- source-bound on the real target ✓
    REFUSED (active, winning src out-of-band) 66,443
  AMBIGUOUS ...............................       0
unmapped flat addresses ..................       0    (bits half correct device-wide) ✓
```

**Honest coverage on the real bitstream: 7,987 / 74,430 = 10.7 % of the active interior muxes the
table can see.** And that 74,430 is itself a *floor on the denominator*: muxes driven **only** by
refused sources (LE_BUFFER outputs, back-ref, low-ci, LEIM ports) never enter the visible set at
all, so the true fraction of active interior routing that is source-bound is **below 11 %.**

DECODED-arc class breakdown on the foreign target (re-measured ✓):

- **by dest:** LOCAL_INTERCONNECT **2,523**, UNBOUND_GAP 3,243, C4 1,180, R4 887, C16 93, R24 61.
- **by src:** C4 4,438, UNBOUND_GAP 2,924, R24 283, C16 205, R4 137. (**0 LE_BUFFER, 0 LI, 0 LEIM**.)
- top pairs: C4→LI 1,763 · C4→gap 1,660 · gap→gap 1,439 · gap→LI 708 · C4→R4 585.

The **2,523 C4/gap → LOCAL_INTERCONNECT** taps are the concrete proof the LI wall is broken as a
dest on real vendor silicon-config data. Of the LI-dest muxes that are active in the foreign target
(2,523 decoded + 16,399 refused = 18,922), we bind **13.3 %** — cracked, but mostly still refused
because the *winning* driver is often a refused source.

---

## 5. Baseline delta (the mission's yardstick)

| Metric | Prior static baseline | This table on the foreign target | delta |
|---|---|---|---|
| interior arcs source-bound | **2 / 213** (211 unbound) | **7,987** bit-exact | ~+3,900× arcs, still partial by mux |
| LI / LEIM taps bound | **0** | **2,523** LI-dest decoded (88,498 enumerated) | wall broken (DEST side) |
| isolated LUTs (4,751 / 4,781) | LUT pins unbindable | **not resolved** — see §6 | LI *fabric* now decodes; LUT *pins* do not |

The arc count and the LI-wall zero are genuinely and dramatically improved. **The isolated-LUT
metric is NOT yet moved**, because a LUT is connected only when *both* its endpoints bind, and both
LUT endpoints are still refused (§6.1, §6.2).

---

## 6. What is still MISSING, and where it lives

### 6.1 LUT OUTPUT first hop — LE_BUFFER as source *(same segment; allocator sim)*
Every LUT drives the fabric through an `LE_BUFFER` source node (ids 10604–26739). These are
**low-ci → refused** (0 LE_BUFFER in the bound-source set, confirmed ✓). So the `LE_BUFFER → C4/R4`
first hop out of every logic cell is unbound. **Lives in the SAME DYGR route-asm pool**, blocked
only by the pdb **deferred-materialization allocator simulation** (`xfr_ptr @0x10bfe0`, counters
`0x24/0x2c`) that fixes the pool-slot order below ci 20043. This is the single highest-value
remaining task: it would lift source-binding from 18 % toward ~100 % of the 43,566 template-creating
sources **and** is a prerequisite for the isolated-LUT metric.

### 6.2 LUT INPUT final hop — LEIM / BLOCK_INPUT_MUX port select *(DIFFERENT resolver)*
The terminal `LI → LUT-input` hop is **not** a router node→node arc. In the live trace it appears as
(a) a **hardwired** `LI → BLOCK_INPUT_MUX` edge (`group_index=0xFFFFFFFF`, 0 bits — oracle arcs
84783→123131, 91368→122603) plus (b) the separate **`blockmux` stream**
(`ASMDB_ARCH_GROUP_STD::select`, 590 non-default hits on specimenA) whose `sel` is a **local ordinal,
not a router node id**. `BLOCK_INPUT_MUX` never appears as a decoded dest class (confirmed ✓). **This
lives in a different atom model — the ASMDB arch/atom pool, not `libddb_dygr.so`'s route-asm pool.**
It is out of scope for this segment and is the real LEIM final-tap into the LUT.

### 6.3 Back-ref sources — 90,857 nodes *(same segment; template de-dup)*
Nodes that reuse an already-created template via a pdb back-ref delta chain. 69,614 of them have
fanout. **Zero enumerated.** Resolving them needs the back-ref delta decode (which prior template
each points at) — same DYGR loader, downstream of the §6.1 allocator sim.

### 6.4 Class labels for GAP dest ids — 143,141 GAP-dest edges *(die-info pool)*
The dest **ids are arithmetically exact** (base+offset, byte-exact), but 143k land in unclassed
node-id GAP ranges, so their class tag is `UNBOUND_GAP`. This is a *labeling* gap, not a routing
gap. **Lives in the die-info pool** (`DYGR_DIE_INFO_BODY::get_element_enum @0x227aa0`; SA2 block
bind pending) — affects human-readable class only, never the bits.

---

## 7. Bottom line

- **Decode-or-refuse integrity: intact.** 0 mismatches across specimenA / specimenB (independent
  compile) / the foreign target; every committed arc is bit-exact; refusals are honest, not silent errors.
- **Bits half: whole-device, all classes, byte-exact.** Not the bottleneck.
- **Topology half — the real coverage — is ~18 % of source nodes, ~11 % of active interior muxes on
  the real target.** Dominated by C4; partial R24/C16/R4; LI bound **as dest only**.
- **The LI wall (0 → 2,523 bit-exact on real silicon config) is genuinely broken. The isolated-LUT
  problem is NOT solved:** both LUT endpoints (LE_BUFFER output source, LEIM/BIM input port) remain
  unbound — §6.1 in this same ddb (allocator sim), §6.2 in a different atom model (ASMDB arch pool).
- **Next unit of work with the highest leverage: the pdb deferred-materialization allocator
  simulation (§6.1).** All its other inputs (base_gid, offset pool, asm bits, +2513 band) are
  already parsed and validated; it alone unlocks LE_BUFFER sources, most R4, and the back-ref chain,
  and is the only route-pool-internal blocker left.

_Re-measure scripts/data: `sc1_sds_decode.py`, `sc1_oracle_result.json`, `dygr_connectivity.json`,
`dygr_route_parse.py`; all §2/§4 counts recomputed live this pass from the ddb files and the target
rbf._
