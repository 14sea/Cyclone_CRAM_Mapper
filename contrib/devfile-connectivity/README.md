# contrib/devfile-connectivity — device-file-derived connectivity, codecs, and a decode-or-refuse decoder

This is an external contribution to the EP4CE6 Cyclone IV bitstream RE project.
It adds a **device-file (`.ddb`) driven** path to complement this repo's pair-diff
fuzzing: instead of inferring bits from bitstream diffs, the artifacts here read
the routing/config model straight out of the Quartus device files and the
assembler's own resolved tables, then decode a `.rbf` **bit-exact or refuse**.

Everything here is **device-general** for the Cyclone IV E die `cycloneive1`
(EP4CE6 and EP4CE10 share this die, the same 368011-B `.rbf` geometry, and the
same routing-graph node space). None of it is specific to any one design or board.
Coordinates use this repo's `(X,Y)` convention (see `docs/coordinate_reconciliation.md`).

- **Provenance & environment.** The scripts were lifted from an EP4CE6/EP4CE10
  device-file RE campaign. Several are decompile transcriptions (function
  addresses are cited in each file's docstring) and require the Quartus 21.1 Lite
  device files under `QUARTUS_ROOTDIR` to *regenerate* their tables; the tables
  they produce are committed here as data so consumers do not need Quartus to
  *use* them. Scripts import each other by sibling filename within `scripts/`;
  a few (notably `decode_rbf.py`) retain absolute paths back into the original
  campaign tree and are shipped as the **orchestration pattern** — see
  "Integration notes" below.
- **License.** Follows the repo dual license: code under `GPL-3.0-or-later`,
  prose/docs under `CC BY-SA 4.0`.

---

## Contribution catalogue

### 1. DYGR static connectivity parser + device-wide edge table
`scripts/ddb_parse.py`, `scripts/dygr_route_parse.py`, `scripts/build_connectivity.py`,
`scripts/node_id.py`, `docs/dygr_static_format/*.md`.

- **What.** An offline parser for the Cyclone IV DYGR route-assembler pool.
  `ddb_parse.py` reads the container/PDB byte codec and object graph exactly as
  the shipping reader does (`get_flat_address`, `get_single_bit`).
  `dygr_route_parse.py` builds the assembler's edge model on top —
  `get_bits_from_source_to_dest(src,dest)` → the CRAM select/exclusion bits — for
  the **whole device**. `build_connectivity.py` materializes the device-wide
  `{src_node → dest_node : bit_group : select_bits}` table (≈352k directed arcs
  over ~20k source nodes; the fuller HOP-A-folded table reaches the ~517k-edge
  figure). This large table is **regenerable**, so it is not committed here (see
  the repo's convention of gitignoring large regenerable JSONs); regenerate with
  `build_connectivity.py`.
- **Why device-general.** The pool is the silicon device file's routing model;
  the arcs and their bits are a property of the die, identical across every design
  on `cycloneive1`.
- **How validated.** Bit-exact and held-out: 0 mismatch on three independent
  Quartus compiles plus a read-only gdb intercept oracle, 0 unmapped over ~1.04M
  select bits (`docs/dygr_static_format/SC1_oracle_validate.md`,
  `SC2_completeness.md`, `SC2_holdout.md`). The `{node → group → CRAM address}`
  half is byte-exact whole-device for all classes; source-bind is partial and the
  unbound classes are declared and REFUSED, never bluffed.

### 2. Routing-node lattices (C4/R4/R24/C16) and node → class map
`scripts/node_id.py`, `results/nodeclass_final.json`, `docs/nodeclass.md`,
`docs/routing_lattices_and_nodeclass.md`,
`results/routing_tables/{c4,r4,r24,c16}_codec_table_devwide.json`.

- **What.** Closed-form `node_index → (I,X,Y)` lattices for the metal classes
  (`C4 = 60836 + 798*I + 24*X + Y`, `R4 = 30925 + 760*I + 23*X + Y`,
  `R24 = 59111 + 23*X + Y`, C16 contiguous block), plus the authoritative
  `node → class` map harvested from the compiler's own
  `DYGR_DIE_INFO_BODY::get_element_enum`. The device-wide routing bit tables per
  class are in `results/routing_tables/`.
- **Why device-general.** Lattices and enum extents are die geometry / device-file
  classification, design-independent by construction.
- **How validated.** The enum codec reproduces the live sweep 135117/135117
  (0 mismatch), a held-out fresh compile 135117/135117, and agrees with 5339
  back-annotated wire names (0 conflicts). Decode-or-refuse: 49 unlabeled enum
  blocks stay `null`.

### 3. CFF / flat-offset → `.rbf` serialization map + method
`scripts/bitpos_to_rbf.py`, `scripts/cff_to_rbf.py`, `results/cff_offset_rbf_map.json`,
`docs/cff_serialization.md`.

- **What.** The closed-form main-plane transform `flat_bitpos ↔ (rbf_byte, bit)`
  (fixed device geometry, no per-bit table), plus the proven aux-plane routing
  (CFF / UNVM / Option-Register region tags) and the partial CFF-offset map.
- **Why device-general.** Pure `.rbf` frame geometry + the assembler's fixed
  region-tag routing.
- **How validated.** 99.9964% of a whole config image reproduces the real `.rbf`
  (misses only at the `Y=0` plane-boundary tie point); exact for all `Y∈1..207`
  and all HW-verified LUT cells. The CFF-offset permutation is an honest open gap
  — `cff_to_rbf.py` refuses rather than guess it.

### 4. Coordinate reconciliation
`docs/coordinate_reconciliation.md`.

- **What / why / validation.** Routing `(X,Y)` and IOE/LUT `(X,Y)` are the same
  system and origin (no offset/flip/scale), which is what lets a net be chained
  LUT-out → routing → LUT-in with no translation. Confirmed by the clean
  round-trips in items 2 and 6.

### 5. Compiler-model-extraction method + config codecs
`docs/compiler_model_extraction.md`; codecs
`scripts/codec_le-lab-secondary.py`, `scripts/codec_pll-m9k-clock.py`,
`scripts/codec_ioe-reg-and-inputmux.py` with tables
`results/codec_*_table.json`.

- **What.** Harvest the assembler's resolved `{setting/codeword → CRAM bits}`
  tables (gdb emit intercept over `quartus_asm`), **invert** to
  `{bits → setting}`, decode-or-refuse. The three config codecs cover
  le/lab-secondary control fields, PLL/M9K/clock CRAM-resident selectors, and the
  IOE register + interconnect→IOE input mux (185 muxes / 4806 codewords).
- **Why device-general.** The harvested tables are the device file's resolved
  model, shared by every design on the die.
- **How validated.** Each codec is bit-exact on its oracle and clean on held-out
  fresh compiles (le-lab: leave-one-out over 8 compiles; ioe: 2 fresh seeds +
  held-out sel16/17; pll: 5 fresh PLL carriers). Unique-signature guarantee →
  unused/unobserved reads REFUSE.

### 6. LUT codec (validated vs the golden pair-diff sweep)
`scripts/lut_sigma.py`, `scripts/lut_fullgrid.py`, `results/lut_fullgrid_result.json`,
`docs/lut_codec_validation.md`.

- **What.** Physical LUT-mask cell geometry + logical-function recovery
  (constant port-axis reversal), extended to the full EP4CE10 grid with an
  invertibility proof.
- **Why device-general.** LAB/LE geometry on the shared die.
- **How validated.** **42/42** against this repo's own `results/golden_rbf_modeH/`
  pair-diff sweep (14 LABs × 3 non-degenerate masks), read straight from raw
  bits: all predicted cells resolve, zero stray LUT cells, popcount matches,
  read-back is an exact input-permutation of the intended mask. Device-wide
  extraction: 0 cell-disjoint violations, 0 round-trip failures.

### 7. Decode-or-refuse decoder + connectivity layers
`scripts/decode_rbf.py`, `scripts/static_connectivity.py`,
`scripts/connectivity_codec.py`, `results/connectivity_table.json`.

- **What.** The unified decoder that assembles the locked codecs behind one
  interface, normalizes bit-order once (`0x6a` codec convention; auto-detects and
  bit-reverses a `0x56`-convention bin), dispatches per-region, and reports every
  unprovable region as UNKNOWN/REFUSED. `static_connectivity.py` is the
  whole-device static edge layer (decode-or-refuse mux resolution);
  `connectivity_codec.py` binds routing-arc sources / LI-LEIM taps from the
  dynamic-arc table (a small example table is committed as
  `results/connectivity_table.json`).
- **Why device-general.** Frame geometry, bit-order normalization, and the codec
  dispatch are all die-level; the connectivity tables are device-file derived.
- **How validated.** `decode_rbf.py selftest` round-trips 1277/1277 cells,
  0 mismatch, ALL PASS; each region encode→decode is bit-for-bit on decoded cells.

### 8. Header integrity field — byte-doubled option floor + data-frame CRC-16
`scripts/header_field.py`, `docs/header_integrity_field.md`,
`results/header_integrity_decomp.json`.

- **What.** Decodes the config-image header region the fork treats as an opaque
  "no CRC" band (frames 0..24) and pins the two integrity engines over the whole
  368011-byte image: the **data-frame CRC-16** (reflected poly `0xA001`, effective
  init `0xFE54` over the 208 payload bytes; `PGM_COMMON::calculate_crc16` via the
  dispatcher `PGMIO_F2P::calculate_crc` @`0x36eb00`) and the **106-bit header
  integrity floor** — 25 header frames each carrying an 8-bit option field
  **byte-doubled** into bytes 208/209 (`byte[209]==byte[208]`), of which 22 frames'
  low bytes are a per-frame GF(2)-affine function of their own payload. `header_field.py`
  is a standalone decoder/emitter (no Quartus needed): `emit_frame_crcs` +
  `enforce_duplication` write a valid whole-image header.
- **Why device-general.** Frame geometry + the two engine parameterisations are
  die/binary constants; the duplication law and 22 affine maps are proven across a
  471-design same-die corpus.
- **How validated.** Data-frame CRC-16 **1727/1727 bit-exact** (all-zero frame →
  `0x7D9A`, a device constant asserted in the self-test); duplication law 471/471
  designs, 0 mismatch; 22 affine frames held-out bit-exact on 471 designs → the
  validation image's whole 106-bit floor DERIVED. `calculate_crc8` @`0x36e8d0` is
  **refuted as dead code** by a live gdb trace (3470 cpf dispatches, all crc16, 0 crc8
  calls; asm run 0 CRC calls). **Honest limits:** the F3/F5/F9-class low bytes are
  **design-input-bound** (an M9K-memory-block option feature) and correctly **REFUSED**
  for foreign designs; the documented 32-bit whole-config SEU CRC is **located but not
  closed** (absent from this passive-serial image — postamble 59×`0xFF`).

### 9. Two-background ternary-ownership completeness oracle
`scripts/ledger.py`, `docs/ownership_completeness_oracle.md`,
`results/ownership_ledger_report.json`.

- **What.** A rigorous from-blank ownership metric over **all 2,944,088** serialized
  positions. The from-blank encoder is run onto BOTH a `0x00` and a `0xFF` background;
  a position is **OWNED only where it is written the SAME value on both** (deterministic
  set OR clear). A position merely left at blank-0 is **UNKNOWN**, never owned. Every
  position is classified `KNOWN / DERIVED / DONTCARE_PROVEN / UNKNOWN` with an explicit
  write-mask, and the all-position ownership is reported (not the set-bit-only count,
  which over-counts by treating implicit zeros as owned).
- **Why device-general.** The metric, the two-background write-mask, and the ternary
  census are design/target-independent by construction; the only device-file content is
  the encoder being measured.
- **How validated.** On the validation image: KNOWN 272,590 + DERIVED-emitted 8,117 =
  **280,707 owned = 9.5346 %** strict all-position, **INVENTED 0 / WRONG_CLEAR 0**
  (asserted), all census invariants pass; the set-bit view reconciles at 180,077/194,948
  = 92.3718 %. It is a **stricter completeness gate** than set-bit counting and separates
  the two real gaps: un-enumerated clear-plane resources (UNKNOWN_CLEAR 2,648,510) vs
  genuinely-unknown set bits (UNKNOWN_SET 7,942).

### 10. Clear-plane full-field-mask resource enumeration
`scripts/routing_fullfield_codec.py`, `scripts/logic_fullfield.py`,
`scripts/io_fullfield.py`, `docs/full_field_mask_enumeration.md`.

- **What.** To OWN the vast off-state (clear) plane, each enumerated resource's codec
  writes its **complete field mask** — the decoded value where set AND 0 for every
  unselected/unused cell in that resource's device-file footprint — so off-resources
  become provably KNOWN-0. Applied to routing off-muxes (device-wide via the routing.ddb
  load-order permutation), LE/LAB-secondary + LUT off-fields, and IOE/PLL off-fields.
- **Why device-general.** Every footprint is fixed device geometry (the permutation is
  disasm-pinned, not oracle-fit; the LE/LAB/LUT/IOE/PLL fields are the assembler's
  resolved tables); the off-test reads the real image but the footprints are die-level.
- **How validated.** Two-background ledger deltas, each with `wrong_clear == invented ==
  0` asserted: routing+LUT off-fields **+51,885** clears (9.5346 %→11.2969 %),
  device-wide routing off-mux **+68,476** via the permutation (binding 30,205 of 135,117
  nodes; 12.6877 %→15.0135 %), IOE+PLL **+1,368**, LE/LAB-secondary **+240**. Plan stats
  confirm decode-or-refuse (routing 1,822 refused; LE/LAB-secondary 19 refused, 56 set
  bits left UNKNOWN). **Honest limit:** interior LE_BUFFER / local-interconnect geometry
  (104,817 `no_template` nodes) and device-wide per-site LE secondary/mode geometry
  remain **un-enumerated and declared, not bluffed**.

---

## How this composes with the existing pipeline

- **CRAM codec (`fuzz/bitstream.py` LUT + RouteCodec + CRC).** Item 3's
  `flat_bitpos ↔ (rbf_byte,bit)` transform and item 6's `le_cells` geometry are an
  independent, device-file-grounded cross-check of the pair-diff CRAM codec; the
  LUT geometry matches the golden sweep 42/42. The bit-order front end in item 7
  documents the `0x6a` vs `0x56` convention so mixed-provenance bins normalize
  cleanly before any codec runs.
- **Route synthesis / `route_synth.py` / chipdb (`fuzz/chipdb_gen.py`).** Items 1
  and 2 provide a device-wide `{src→dest : select-bits}` routing table and the
  node lattices/classes to key it — a static, bit-exact alternative source for the
  routing graph and pip bits that the fuzz-mined sig-cache approximates. Because
  coordinates reconcile (item 4), these drop into the repo's `(X,Y)` chipdb model
  without translation.
- **FASM ↔ RBF (`fuzz/fasm2rbf.py` / `rbf2fasm.py` / `synth/np2fasm.py`).** Item 7's
  decode-or-refuse decoder is a read path (`.rbf → structured features + REFUSED
  regions`) that can back a stricter `rbf2fasm`, and its per-feature `encode()`
  re-emits exact cells for a FASM→RBF write path. The config codecs (item 5) add
  named le/lab/IOE/PLL fields to that FASM vocabulary where they are CRAM-resident.
- **Whole-image header for `fasm2rbf` (item 8).** The data-frame CRC-16 generator and
  the header duplication law give the fork a **valid whole-image header** emit path —
  not just frame CRCs — so a synthesized `.rbf` passes configuration integrity; the
  design-input-bound header bits are refused, never invented.
- **Stricter completeness gate for the codecs (item 9).** The two-background ternary
  ledger is a harder ownership oracle than the set-bit count for the whole pipeline: it
  never credits an implicit zero, and its INVENTED/WRONG_CLEAR invariants guarantee a
  newly-merged codec can only raise proven ownership, never silently corrupt a claim.
- **Resource-enumeration path toward a complete chipdb (item 10).** The full-field-mask
  codecs convert the off-state plane of routing / LE-LAB / LUT / IOE / PLL resources to
  provable KNOWN-0, which is the device-wide resource-footprint enumeration the chipdb
  needs to reach all-position coverage; un-enumerated classes are declared, not bluffed.
- **Decode-or-refuse discipline.** Every layer here reports proven cells only and
  refuses the rest, so merging it can never silently corrupt an existing codec's
  claims — a REFUSED region is an explicit gap, not a wrong bit.

## Integration notes (paths & dependencies)

- `scripts/` files import each other by sibling name; run them from `scripts/` or
  add it to `sys.path`.
- The parsers in items 1–2 need the Quartus 21.1 device files
  (`ddb_cycloneive1_asm.ddb`, `ddb_cycloneive1_routing.ddb`) under
  `QUARTUS_ROOTDIR` to *regenerate* tables; the committed `results/` tables let
  you *use* them without Quartus.
- `decode_rbf.py` is shipped as the orchestration pattern and still references the
  original campaign layout (a `phase2/` tree for routing/IO/PLL/M9K sub-codecs and
  an IO direction/used sub-codec that lives outside this contribution). Wire your
  own region sources — or the repo's existing codecs — into the `CodecRegion`
  dispatch; the load-bearing, portable parts are the bit-order front end, the
  per-region safe-reject contract, and the round-trip selftest.

Deliberately **out of scope** (kept out of this contribution): any board/target-
specific pinout or peripheral role assignment, vendor-bitstream ownership figures,
and target-specific register/programming protocols. Only device-general Cyclone IV
E findings are included here.
