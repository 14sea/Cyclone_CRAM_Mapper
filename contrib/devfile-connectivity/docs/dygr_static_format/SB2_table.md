# SB2 — whole-device DYGR connectivity table

**Deliverables**
- `dygr_connectivity.json` (64.5 MB) — node-resolved `{src → [{dest, class, bit_group, bits}]}`.
- `build_connectivity.py` — the emitter (runs the SB1 parser over the located device files).

Run (numpy needs `LD_LIBRARY_PATH` unset — GLIBCXX clash under the Quartus libs):

```
LD_LIBRARY_PATH= python3 re_workflows/out/dygr_static/build_connectivity.py
```

Die `cycloneive1` = EP4CE6/EP4CE10 — the same 368011-B rbf as the coverage target
`target.rbf`, so the table applies directly to it.

---

## 1. What the table contains

Two tiers, both decode-or-refuse (no edge is bluffed):

| tier | key | count | bits | grounding |
|---|---|---|---|---|
| **trace-proven** | `trace_proven_edges` | 21 arcs | full (select + dest exclusion, forced-0) | reproduce the READ-ONLY live trace **exactly** (SB1: 21/23, 0 mismatched) |
| **static band** | `edges` | **352,674 directed edges** over **20,461 source nodes** | select field of the src mux (from the asm pool group `k`) | byte-exact `dest = base[src] + template.offset[k]`; src→template = cross-validated `+2513` map |

`select_bits` is the source mux's one-hot select sub-field for that arc — SB1 proved
this field alone carries **every value-1 selection bit** byte-exact (verified again
here: band edge `68339→84783` select `{11243:1, 12969:1, 12970:0}` is exactly the
select subset of the trace-proven full bit set). The trace-proven tier additionally
carries the dest's exclusion bits (forced 0); those need the dest's own fanout_size,
which is only in-band for some dests, so the band tier emits the select field and the
`trace_proven_edges` tier shows the full form.

Every `bits`/`select_bits` `flat` is a `DYGR_ROUTE_ASM_BIT::get_flat_address()` CRAM
address — feed to `bitpos_to_rbf.py` for `flat↔rbf` (proven elsewhere).

---

## 2. The node→template bind (SB1 sec.5 residual — cracked for a large band)

The residual that blocked device-wide edge binding was: *which of the 44,260 templates
does each node use?* Cracked this pass:

- Each `DYGR_ROUTE_ELEMENT` stores its template as a pdb pointer descriptor (`tdesc`).
  **44,260** elements carry a NEW-object descriptor (`tdesc & 3 == 0`, class 3) — these
  **create** the 44,260 templates, in element order (`creation_index`, `ci`). The other
  **90,857** are pdb back-references (`tdesc & 3 == 2`) that reuse an existing template.
- The template-body **pool is flushed in pdb array-index order** (`finish_reading_all`
  @0x10c640 reads each class's object array `0..count` in order). Empirically the
  array-index of a new template `== ci + 2514` across a contiguous band, so

  ```
  pool_slot(node) = creation_index(node) + 2513      for ci ∈ [20043, 41746]
  ```

  binds **20,461** source nodes to their template.

**Grounding (three independent checks, all pass):**
1. **6/6 EXACT vs the live trace** — every new-object arc's dest gid equals
   `base[src] + pool[ci+2513][k]` (`68339→84783 k2`, `82931→70813 k6`, `60851→91368 k1`,
   `70813→83957 k12`, `82373→34950 k2`, `82372→40270 k1`).
2. **20,461 / 20,461 structural validity** — `offset[0]==0` and every
   `base[src]+offset[k]` is a valid router gid (bit31 set, index < N=135117).
3. **20,461 / 20,461 cross-validation vs the INDEPENDENT asm pool** — the template's
   `num_edges` never exceeds the asm node's `num_bit_groups` (exclusion count ≥ 0), and
   the exclusion count is tightly clustered: **18,546 nodes have exactly 2**, 1,022 have
   1, 891 have 0 (2 outliers). A wrong binding would violate `num_edges ≤ num_bit_groups`
   constantly; it never does.

**Why it's a band, not the whole device.** Outside `ci ∈ [20043, 41746]` the constant
`+2513` is wrong: early in the stream the pdb reader interleaves *deferred
materialization* appends into the class array, so the array-index → creation-index
offset ramps up (it is not constant `2513` for low `ci`), and `ci+2513` there lands on
empty/wrong slots. Those sources are **REFUSED**, not guessed. Fully closing the map
needs an exact simulation of the pdb deferred-materialization allocator (the append
order in `xfr_ptr` @0x10bfe0 + `finish_reading_all`) — the single remaining task.

---

## 3. Coverage — honest, by class

**Bits half (node → group → CRAM bits): COMPLETE, byte-exact, whole device, ALL classes.**
Every one of the 135,117 node ordinals (108,380 non-empty) has its groups→bits in the
asm pool regardless of class — LI/LEIM/LOCAL_INTERCONNECT, C4, R4, R24, C16,
direct-links, LE_BUFFER, BLOCK_INPUT_MUX, IO_DATAIN, CLK. This half is unaffected by the
residual.

**Edge (src→dest) binding — by SOURCE class** (the band captures the ci window, which
maps unevenly across classes):

| src class | bound (in-band) | refused (out-of-band) | note |
|---|---|---|---|
| C4  | 10,680 | ~0 | nearly all C4 sources bound |
| R24 | 569 | ~0 | nearly all bound |
| C16 | 492 | 608 | ~45% |
| R4  | 1,122 | 6,515 | ~15% (most R4 sources are low-ci → refused) |
| LE_BUFFER | 0 | 8,720 | all refused (low-ci) |
| IO_DATAIN / CLK / BLOCK_INPUT_MUX | 0 | 343 | refused |
| LOCAL_INTERCONNECT (as source) | 0 | 25 | LI is overwhelmingly a *destination* / sink class |
| GAP (unbound node-id blocks) | 8,841 | 6,345 | class label pending SA2 block bind |

**Edges by DEST class** (from the 352,674 band edges): LOCAL_INTERCONNECT 88,498,
C4 65,124, R4 46,709, C16 6,623, R24 2,579, plus 143,141 into node-id GAP ranges
(class label pending, arithmetic dest id is exact). So the interior mesh the table
captures is dominated by **C4/R4/R24 mux → LOCAL_INTERCONNECT (LI wall)** taps and
inter-wire (C4/R4) hand-offs — exactly the interior-interconnect arcs the campaign
could not previously bind (LI/LEIM taps were 0).

**Classes NOT in these two ddb segments:** the block-level muxes (`blockmux` in the
trace — 590 records: LAB/LE/IO block input muxes selected by `sel`, not by router
node→node arcs) are a **separate** resolver path and are **not** interior-interconnect
edges; they are not in `DYGR_ROUTE_ASM_INFO` / `DYGR_ROUTE_INFO`. The per-node
(class, X, Y) location table (`get_location`/`get_element_enum`) lives in the die-info
pool, not here (SA2); this table uses node ordinals + the SA2 lattices for class labels.

---

## 4. Edge / wire-count context

- **Directed interior arcs in the table: 352,674** (band) + 21 (trace) — every one has a
  byte-exact CRAM select field.
- Device fanout budget for context: the 20,515 non-empty templates carry **879,374**
  distinct fanout offsets in total (mean fanout ≈ 43, excluding one 65535-edge
  global-net outlier the asm guard rejects). Summed over all 135,117 nodes (templates
  are shared by the 90,857 back-ref nodes) the true device directed-arc total is larger;
  it cannot be totalled exactly until the back-ref/low-ci binding lands.
- This already dwarfs the prior static decoder's interior coverage (211/213 arcs
  source-unbound, LI/LEIM taps = 0): the band alone binds **352,674** interior arcs
  with byte-exact bits, LI-wall destinations included.

---

## 5. Residual (single remaining task)

The low-ci / back-ref node→template binding needs the exact pdb deferred-materialization
append order (`xfr_ptr` @0x10bfe0 counter `0x24`/`0x2c` advanced by both new-markers and
materializations, drained by `finish_reading_all` @0x10c640). Everything else it needs —
`base_gid[]`, the byte-exact template offset pool, the asm group→bit half, and the
`+2513` mechanism — is parsed and validated. Until then those sources answer
decode-or-refuse; grounded group indices for them come from the live trace or
`quartus_cdb --back_annotate=routing` (both READ-ONLY, no fuzzing).

## 6. Files
- `dygr_connectivity.json` — the table (this deliverable).
- `build_connectivity.py` — emitter.
- `dygr_route_parse.py`, `ddb_parse.py` — SB1 parser + container reader (reused).
- `node_id.py` — node-ordinal → class/coords classifier (SA2).
- Ground truth (READ-ONLY): `re_workflows/out/debugger/harness/logs/routing_capture.jsonl`.
