# SC2 — Adversarial held-out refutation of the DYGR static connectivity table

**Charge:** *Try to REFUTE that the static table predicts UNSEEN arcs. Pick src→dest edges
that appear in NO prior specimen/trace, predict their bits purely from the static table,
compile a design that forces those arcs, and confirm the real rbf matches bit-exact. If any
held-out prediction fails, `real=false`.*

**Verdict: REFUTATION FAILED. `real` stands TRUE.** A fresh independent compile
(`specimenC`) produced **69 held-out interior arcs** (0 overlap with any prior
specimen/trace). The static table enumerates **31** of them and predicts **every one
bit-exact** — 31/31 correct bit-group, 31/31 correct select bits versus the assembler's own
live computation, and **91/91 table-predicted CRAM bits match the real `specimenC.rbf`, 0
mismatch.** The other 38 held-out arcs are honestly **refused** (out-of-band sources), never
bluffed. **Zero mispredictions.**

Files (all under `.../out/dygr_static/`): design `specimenC/specimenC.{v,qsf,qpf}`, bitstream
`specimenC/specimenC.rbf`, back-annotation `specimenC/specimenC.rcf`, ground-truth oracle
`specimenC/routing_captureC.jsonl`, validator `sc2_holdout.py`, raw result
`sc2_holdout_result.json`.

---

## 1. The adversarial specimen

`specimenA` and `specimenB` lived **entirely in LAB column X16**. `specimenC` places five
LUT→C4→LUT chains, pinned 4 LAB-rows apart, into **columns X24 and X10** (both confirmed
legal LAB columns; X20 was rejected by the fitter as a RAM/DSP column and dropped). Every
forced (X,Y) — hence every forced routing-graph node id — is new versus both prior
specimens. LUT masks make `combout` depend on both used inputs so the fitter cannot drop a
routed pin. Fresh SEED (3), independent I/O placement.

Forced C4→LOCAL_INTERCONNECT taps (from `specimenC.rcf`), e.g.:
`C4:X9Y9S0I1 → LOCAL_INTERCONNECT:X10Y12S0I16`,
`C4:X9Y11S0I1 → LOCAL_INTERCONNECT:X10Y14S0I16`, plus X24 taps and R24/C16 feeders.

## 2. Ground-truth oracle for specimenC

The same **gdb intercept harness** that produced the READ-ONLY `traceA/traceB`
(`DYGR_ROUTE_ASM_INFO::get_bits_from_source_to_dest` → `{src id, dest id, group, bits}`) was
run on `specimenC` → `routing_captureC.jsonl`: **74 router→router arcs** (+607 blockmux,
separate resolver, out of scope). This is the assembler's own live connectivity computation
— independent of, and never used to build, the static table.

- Sanity: all **509** emitted oracle bits verify bit-for-bit against `specimenC.rbf` (0 bad).
- **0 of 74** arcs overlap the 43 distinct arcs of `traceA/B` + `specimenA/B` captures →
  every resolvable arc is genuinely held-out.

## 3. Result — table prediction vs oracle vs real bitstream

```
oracle arcs: 74   hardwired: 5   shared-with-prior: 0   HELD-OUT: 69
held-out coverage:   in static band 31    REFUSED (out-of-band src) 38
PREDICTION (static table vs oracle):   bit_group 31/31 OK, 0 BAD    select bits 31/31 OK, 0 BAD
ROUND-TRIP table-predicted bits vs real specimenC.rbf:   91/91 match, 0 unmapped, 0 MISMATCH
REFUTED: False
```

The 31 confirmed held-out arcs span the full interior menu the table claims to cover:
**C4→LOCAL_INTERCONNECT** (the LI wall taps that were 0 in the pure-static campaign — e.g.
`61504→96923`, `61494→96913`, `61496→96915`, `61033→84145`, the forced taps),
**C4→C4** column continuations (`60668→60672→60676`), **C4→R4**, **R24→C4**, **R24→C16**,
**C16→C4**, and several into node-id **GAP** ranges (arithmetic-exact dest ids). Each was
predicted from the static device file alone and matches the live assembler + the real rbf.

## 4. Honesty — what was refused, not bluffed

38 held-out arcs have a **source the static band does not enumerate** (LE_BUFFER drivers,
low-`ci` C4/R4 channel-entry nodes, and pdb back-ref sources). The table **refuses** these
(decode-or-refuse) rather than guessing — exactly the coverage gap documented in SB2/SC1.
A refusal is not a failed prediction; not one refused arc produced a bit that contradicts
the table. The 5 hardwired arcs (`group_index=0xFFFFFFFF`, 0 bits) carry nothing to encode.

## 5. Bottom line

- Held-out arcs checked against the oracle (table-enumerated): **31**, exact match **31**,
  **mismatches 0**.
- RBF round-trip of the table's predictions on used held-out arcs: **91/91, exact = true.**
- Held-out prediction confirmed by an independent forced compile the table never saw: **yes,
  bit-exact** (31 arcs, incl. the specifically-forced C4→LI taps).
- **No held-out prediction failed ⇒ refutation failed ⇒ `real = true`.** The table remains
  bit-exact for every arc it does not refuse, and partial-by-source-coverage as declared.
