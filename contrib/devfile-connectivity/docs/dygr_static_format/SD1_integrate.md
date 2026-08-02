# SD1 — INTEGRATE the whole-device static connectivity table into the decoder

Target: `target.rbf` (EP4CE10-die, 368011 B).
Decoder: `devfile/decoder/decode_rbf.py` (unified). New layer:
`devfile/decoder/static_connectivity.py` consuming
`re_workflows/out/dygr_static/dygr_connectivity.json` (64.5 MB, SB2; validated bit-exact
in SC1/SC2 against specimenA/B/C + the READ-ONLY live gdb intercept oracle).

This is the WHOLE-device interior-interconnect layer. Unlike the dynamic
`connectivity_codec.py` (which only knows the ~40 arcs a specimen exercised), the static
table enumerates every DYGR route-asm edge parsed out of the device file
(352,674 directed arcs, 20,461 source nodes).

---

## 1. What was wired in (decode-or-refuse preserved)

- New codec `StaticConnectivityCodec` groups the table's arcs by destination MUX =
  `(dest_node, bit_group)`. For a target image it reads each mux's select-bit cells and
  classifies **UNUSED** (all bits 0), **DECODED** (read pattern equals exactly ONE
  enumerated arc's full select pattern, 1s *and* 0/exclusion bits → that arc's source is
  bound), **AMBIG** (matches >1 arc → refuse), **REFUSED** (non-zero pattern matching no
  enumerated arc → winning source is an out-of-band class; honest gap, never guessed). Any
  select bit that fails `flat_to_rbf` → the whole mux is refused.
- Wired into `Decoder.decode()` as an additive region + `encode()` round-trip path +
  `summarize()` line. The dynamic layer, all routing/LUT/IO/PLL/M9K codecs, and the bit-order
  front end are untouched.
- **`decode_rbf.py selftest` = ALL PASS** (front-end bit-order proof + per-codec round-trip
  + full decode→encode, mismatches 0). The container parser `ddb_parse.py` was extended, not
  rewritten; nothing was re-derived.

## 2. Decode-or-refuse INTEGRITY on the real target (re-measured this pass)

Full unified decode of `target.rbf` (magic 0x56 → per-byte bit-reversed to 0x6a, anchor
verified):

- **Round-trip on ALL decoded regions: checked 107,302 cells, mismatch 0.** The static layer
  contributes **23,731** proven select-bit cells (all round-trip bit-exact).
- Static layer over the table's **285,332 dest muxes**: **210,902 UNUSED / 66,443 REFUSED /
  7,987 DECODED**, **0 AMBIG, 0 unmapped** over 1,040,983 candidate select bits.
- Every one of the 7,987 bound arcs reproduces its select bits bit-exact against the vendor
  bitstream (23,731/23,731, 0 mismatch). This is live routing recovered from an independent
  vendor bin the table never saw.
- Overall decoded CRAM fraction **2.87% → 3.68%** (the +23,731 static-connectivity bits; the
  bit fraction is small because routing select fields are only a few cells each — the value is
  in the *edges*, not the bit count).

## 3. The three re-measured netlist metrics vs the pure-static baseline

| metric | baseline (netlist_recovery_report) | **after static table** |
|---|---:|---:|
| interior arcs **source-bound** | **2 / 213** | **7,987** (+2 legacy LE-out C4 PIPs) — ~**3,900×** |
| **LI/LEIM wall taps** bound (dest-side) | **0** | **2,523** distinct LOCAL_INTERCONNECT wires |
| **isolated LUTs** | **4,751 / 4,781** | **4,751 / 4,781 (UNCHANGED)** |
| wire→wire chaining (junction nodes) | **0** | **1,917** |
| router-graph components | 213, all 2-node fragments | **3,925 nets, largest 65 nodes** |

Bound-arc source classes: C4 4,438 · UNBOUND_GAP 2,924 · R24 283 · C16 205 · R4 137.
Bound-arc dest classes: UNBOUND_GAP 3,243 · **LOCAL_INTERCONNECT 2,523** · C4 1,180 · R4 887 · C16 93 · R24 61.

## 4. Connected-component structure now assembling

From the 7,987 bound arcs: **11,912 router-wire nodes, 3,925 weakly-connected nets** (was 213
isolated 2-node fragments). Size histogram tail: `{65:1, 58:1, 51:1, 43:1, 34:1, 33:1, 31:1,
25:2, 23:1, …, 3:730, 2:2401}`. **1,524 nets span ≥3 nodes; 65 span ≥10 nodes.** Multi-hop is
now real: **1,917 nodes are junctions** (a bound dest re-appears as a bound source), max
observed forward depth **7 hops** from a root, fan-out up to **15**. These are genuine
multi-fan-out interior signal trees — the "routing-demand heat-map" of the old campaign is now
an actual interconnect graph over C4/R4/R24/C16 wires reaching the LAB local interconnect.

## 5. How close to a fully readable netlist — HONEST verdict

**The interior is now connected; the LUT endpoints are not.** A LUT-to-LUT edge is
`LUT_A → LE_BUFFER → [C4/R4/… wires] → LOCAL_INTERCONNECT → [blockmux/LEIM] → LUT_B`. The static
table binds the **middle** (routing wires → LOCAL_INTERCONNECT, 2,523 taps that were 0 before)
but binds **0** of the two LUT-adjacent hops:

- **LUT output first hop** (LE_BUFFER as source): **0 bound** — LE_BUFFER is an out-of-band
  low-ci class the static +2513 pool map refuses (needs the pdb deferred-materialization
  allocator sim, §6.1). Same DYGR pool; highest-leverage next task.
- **LUT input port** (BLOCK_INPUT_MUX/LEIM as dest): **0 bound** — a DIFFERENT "blockmux"
  resolver (`ASMDB_ARCH_GROUP_STD::select`, sel = local ordinal not a node id), in the ASMDB
  arch/atom pool, not `libddb_dygr.so`. Out of scope for this table.

Because both LUT-touching classes are refused, the **isolated-LUT count does not move
(4,751/4,781)** — the honest, decode-or-refuse-correct outcome (SC2 predicted exactly this).
The 30 non-isolated LUTs are still only the LEs sharing the 2 legacy LE-output C4 LABs, at LAB
granularity.

**Net position:** we went from a routing-demand map (213 disconnected fragments, sources
abstract, LUTs a bag of isolated gates) to a **partial interior netlist** — 3,925 multi-node
router-wire nets, source-bound bit-exact, reaching 2,523 LAB local-interconnect inputs (one
blockmux hop from named LUT inputs). That is **~11% of the target's active interior muxes**
source-bound (7,987 DECODED of 74,430 the table sees; 66,443 refused). The remaining ~89% and
the two LUT hops gate on one unit of work each: the **§6.1 allocator simulation** (unlocks
LE_BUFFER sources + most R4 + the back-ref chain — the LUT-output hop and the bulk of coverage)
and the **blockmux/ASMDB resolver** (the LUT-input hop). Until both land, nets stay attached to
the fabric only at the LAB boundary, not at individual LUT pins. **Every bit emitted is real and
round-trips (0 mismatch); nothing on the coverage gap was bluffed.**

---

### Files
- `devfile/decoder/static_connectivity.py` — new whole-device layer (decode-or-refuse).
- `devfile/decoder/decode_rbf.py` — wired in (`import`, `Decoder.sconn`, decode/encode/summary).
- `re_workflows/out/dygr_static/sd1_measure.py`, `sd1_measure_result.json` — this pass's numbers.
- Table: `re_workflows/out/dygr_static/dygr_connectivity.json` (SB2, unchanged).
