# SD2 — FINAL VERDICT: does static DYGR route-asm parsing give a whole-device interior-connectivity map?

Date: 2026-07-28
Target for all foreign-bin numbers: `target.rbf`
(EP4CE10-die, 368,011 B). Table: `re_workflows/out/dygr_static/dygr_connectivity.json` (SB2).
Decoder: `devfile/decoder/decode_rbf.py` + `devfile/decoder/static_connectivity.py` (SD1).

---

## TOP LINE

**Parsing the DYGR route-asm table statically turned the partial decoder from a routing-*demand*
map into a real, source-bound, bit-exact *partial interior netlist* — but NOT yet a full bin-RE
backend.** The hard cap moved from "no interior connectivity at all" to "interior wire graph is
connected and bit-exact, but the two LUT-adjacent hops are unbound," so the *isolated-LUT* count
did not move. The static parse is a decisive, honest advance and it **supersedes the lattice-fit
and single-specimen approaches for everything it covers**, but "arbitrary design → connected
netlist → readable logic, bit-exact" is met only for the *middle* of each net, not end-to-end.

Bottom line by claim:
- **Whole-device map?** The BITS half (node → bit-group → flat CRAM address) is byte-exact
  **whole-device for ALL classes**. The TOPOLOGY half (which source drives each mux) is
  **partial: 18.1 % of source nodes bound**, C4-dominant.
- **Full bin-RE backend?** **No.** ~11 % of the target's active interior muxes are source-bound;
  both LUT-touching hops bind 0; LUTs stay isolated.
- **Bit-exact where it speaks?** **Yes, provably** — 0 mismatches across specimenA/B/C + the
  READ-ONLY live oracle + the real target; every gap is a refuse, never a bluff.

---

## 1. EDGES RECOVERED

| quantity | value |
|---|---:|
| directed interior arcs enumerated device-wide (static table) | **352,674** over **20,461** source nodes |
| trace-proven tier (exact live-oracle reproduction) | 21 arcs, 21/21 bit-exact |
| dest muxes the table sees on the real target | 285,332 |
| — UNUSED (all select bits 0) | 210,902 |
| — **DECODED** (read pattern == exactly one enumerated arc, source bound) | **7,987** |
| — REFUSED (winning source is out-of-band; honest gap) | 66,443 |
| — AMBIG / unmapped | **0 / 0** |
| select-bit cells the static layer proves + round-trips on the target | **23,731 / 23,731, 0 mismatch** |

**Interior arcs source-bound on the real bin: 2 → 7,987 (~3,900×)** vs the pure-static/lattice
baseline (`netlist_recovery_report`, 211/213 arcs were select-only, only 2 had a concrete source).

Router-wire graph on the target: **11,912 nodes, 3,925 weakly-connected nets** (was 213 two-node
fragments). Largest net 65 nodes; 1,524 nets ≥3 nodes; **1,917 junction nodes** (a bound dest
re-appears as a bound source → real multi-hop); max forward depth 7 hops, fan-out to 15.

---

## 2. CLASSES COVERED (honest, source-bind vs dest-bind separated)

**BITS half — byte-exact whole-device for ALL classes** (from the asm pool, SB1): C4, R4, R24,
C16, LOCAL_INTERCONNECT/LI, LEIM, direct-links, LE_BUFFER, BLOCK_INPUT_MUX, IO_DATAIN, CLK. Every
node → group → flat address is correct device-wide; this is NOT the bottleneck.

**TOPOLOGY half — which source drives a mux — is partial and class-skewed:**

| class | as SOURCE (bind) | as DEST (bind, on target) |
|---|---|---|
| **C4** | PRIMARY — 10,549 device srcs; 4,438 target arcs | 1,180 |
| **R24** | partial — 283 target arcs | 61 |
| **C16** | partial — 205 target arcs | 93 |
| **R4** | POOR — 137 target arcs (~85 % refused) | 887 |
| **LOCAL_INTERCONNECT / LI** | **0** as source | **2,523** ← the "LI wall" taps, were 0 |
| **LEIM / BLOCK_INPUT_MUX** | 0 | 0 (separate blockmux resolver) |
| **LE_BUFFER (LUT output)** | **0** | — |
| **IO / CLK / direct-links** | 0 | — |
| **node-id GAP** (dest id exact, label pending) | 2,924 src | 3,243 |

**LI wall (dest-side): 0 → 2,523 distinct LOCAL_INTERCONNECT wires** decoded bit-exact from the
real vendor bitstream (88,498 enumerated device-wide). This is the single class that was flat 0 in
the entire prior campaign and is now real.

---

## 3. ISOLATED-LUT REDUCTION ON target.rbf

**4,751 / 4,781 → 4,751 / 4,781 — UNCHANGED.** This is the honest, decode-or-refuse-correct
outcome (SC2 predicted it exactly). A LUT→LUT edge is
`LUT_A → LE_BUFFER → [C4/R4/R24/C16 wires] → LOCAL_INTERCONNECT → [blockmux/LEIM] → LUT_B`.
The static table binds the **middle** bit-exact (2,523 LI taps that were 0) but binds **0** of the
two LUT-adjacent hops:

1. **LUT-output first hop** (LE_BUFFER as source): 0 — LE_BUFFER is a low-ci out-of-band class the
   static +2513 pool map refuses. Blocked by the §6.1 pdb deferred-materialization allocator sim.
   Same DYGR pool — the highest-leverage remaining task.
2. **LUT-input port** (BLOCK_INPUT_MUX/LEIM as dest): 0 — a DIFFERENT resolver
   (`ASMDB_ARCH_GROUP_STD::select`, sel = local ordinal, ASMDB arch/atom pool), not in
   libddb_dygr.so. Out of scope for this table.

So the interior wire graph now reaches the LAB local-interconnect boundary (one blockmux hop from
named LUT pins) but does not cross into individual LUTs. Nets attach to the fabric at the LAB
boundary, not at LUT ports.

---

## 4. WHAT REMAINS UNKNOWN

| # | region | status | unlocks |
|---|---|---|---|
| K1 | **§6.1 pdb deferred-materialization allocator sim** (xfr_ptr @0x10bfe0, counters 0x24/0x2c) | the one open mechanism; all other inputs (base_gid, offset pool, asm half, +2513 map) parsed/validated | LE_BUFFER sources (LUT-output hop), most R4, and the 69,614 pdb back-ref sources → the bulk of the 81.9 % refused sources |
| K2 | **blockmux / ASMDB resolver** (LUT-input hop) | separate pool, out of this segment's scope | LEIM/BLOCK_INPUT_MUX dest binding → the second LUT hop |
| K3 | **node-id GAP class labels** (die-info pool, get_element_enum @0x227aa0) | ids arithmetically exact; only the class *label* is pending | naming, not bits — 143,141 GAP-dest edges |
| K4 | **LUT input-permutation σ, PLL numeric, M9K MODE** | unchanged from baseline (U4/U5/U6) | physical-mask → logical function; sequential readout |

Source-binding reality: **20,461 / 113,180 real source nodes = 18.1 % bound**; the other 81.9 %
refused = 69,614 pdb back-ref (all) + 23,105 low-ci/out-of-band new-obj. On the target, of 74,430
active muxes the table can see, **7,987 DECODED (10.7 %)**; muxes driven only by refused sources
are invisible, so true source-coverage is below 11 %.

---

## 5. DOES THE STATIC PARSE SUPERSEDE THE LATTICE-FIT AND SPECIMEN-DRIVEN APPROACHES?

**Partially — it strictly dominates both for everything it covers, and it removes their two worst
failure modes, but it does not yet make either fully obsolete.**

- **vs lattice-fitting (device-wide arithmetic tables): SUPERSEDED for the bits half.** The lattice
  tables were sample-sized and produced **0 device-wide** for C16/LI/LEIM/direct-links. The static
  parse gives byte-exact node→group→flat addresses for **every** class device-wide, and it needs no
  per-class specimen mining. Node-id grounding lattices (C4/R4/R24 arithmetic) are retained only as
  a naming/cross-check aid, not as the address source. **The static asm pool replaces the fitted
  bit tables outright.**

- **vs single-specimen / debugger-intercept: SUPERSEDED on a *foreign* bin, complementary on an
  *intercepted* one.** On the foreign target the debugger table (2 specimens) intersected the foreign target in
  only 2–4 muxes; the static table binds **7,987** with no build access — a ~2,000× coverage gain,
  and validated bit-exact against an independent-compile holdout (specimenC, 31/31 held-out arcs,
  0 overlap with any prior specimen). So for "read a foreign .rbf you don't have the project for,"
  **static supersedes specimen-driven.** BUT the debugger-intercept path still uniquely binds the
  two LUT hops (LE_BUFFER source + LEIM dest) for a design whose *own* compile is intercepted —
  exactly the classes the static table refuses today. Until K1+K2 land, intercept remains the only
  route to end-to-end LUT→LUT closure on any single design.

**Net:** static DYGR parse is now the primary interior-connectivity backend; lattice-fit is
demoted to node-naming; specimen-intercept is demoted to a targeted tool for the two refused LUT
hops on designs you can rebuild.

---

## 6. VERDICT

The static DYGR route-asm parse **cracked the interior-interconnect wall as a whole-device
mechanism**: 352,674 enumerated arcs, byte-exact bits for all classes, 7,987 source-bound arcs on
a foreign vendor bin the table never saw, LI-wall taps 0 → 2,523, router graph 213 fragments →
3,925 multi-node nets — all bit-exact, 0 mismatch, 0 bluff. It is a genuine partial interior
netlist and it supersedes the prior campaign's interior-bits tables.

It is **not** a full bin-RE backend: source-binding is C4-dominant and ~18 % device-wide, both
LUT-adjacent hops bind 0, and the isolated-LUT count is unchanged. One well-scoped unit of work —
the §6.1 pdb deferred-materialization allocator simulation (K1) — is the gate that unlocks
LE_BUFFER sources, most R4, and the entire back-ref chain, i.e. the LUT-output hop and the bulk of
the remaining 82 % of sources; a second, out-of-pool resolver (K2) is needed for the LUT-input hop.
Until those land, the backend delivers a connected, bit-exact interior wire graph reaching the LAB
boundary — a large, honest step past the old bag-of-isolated-gates, but still one hop short of a
readable LUT-to-LUT netlist.

---

### Artifacts
- Table: `re_workflows/out/dygr_static/dygr_connectivity.json` (SB2, 352,674 arcs)
- Decoder layer: `devfile/decoder/static_connectivity.py`; wired in `devfile/decoder/decode_rbf.py`
- Measurements: `re_workflows/out/dygr_static/sd1_measure_result.json`, `sd1_measure.py`
- Validation trail: `SB2_table.md`, `SC1_oracle_validate.md`, `SC2_holdout.md`, `SC2_completeness.md`, `SD1_integrate.md`
- Ground-truth oracle (READ-ONLY): `re_workflows/out/debugger/harness/logs/routing_capture.jsonl`, `traceA.json`
