# SC1 — Oracle Validation of the DYGR static connectivity table

**Table under test:** `<repo>/devfile/re_workflows/out/dygr_static/dygr_connectivity.json`
(21 `trace_proven_edges` + 352,674 `edges` band, meta die `cycloneive1`).

**Verdict: REAL / bit-exact on every grounded arc. 0 mismatches.**
Every arc the live oracle observed is reproduced by the static table with the
**same dest bit-group and the same flat bits**; encoding the table's bits back
into three independent real bitstreams reproduces them bit-for-bit; and a genuine
holdout specimen (specimenB, never used to build the table) is predicted correctly
from the device file alone. The table is **partial by source-coverage** (the band
binds ~20.5k of the ~135k router sources) and it **refuses**, never bluffs, the
rest — the refusals are honest coverage gaps, not format bugs.

Scripts (all under `.../out/dygr_static/`): `sc1_validate.py`,
`sc1_roundtrip.py`, `sc1_sds_decode.py`, `sc1_holdout_B.py`. Raw JSON results:
`sc1_oracle_result.json`, `sc1_roundtrip_result.json`, `sc1_sds_decode_result.json`,
`sc1_holdout_B_result.json`.

---

## 1. Oracle match — static table vs the READ-ONLY live trace (specimenA)

Ground truth: `.../out/debugger/harness/logs/routing_capture.jsonl` (also
`traceA.json`). It holds **23 router→router interior arcs** (+590 blockmux records,
which are a separate resolver path and out of scope for a router node→node table).
Of the 23, **2 are hardwired** (`group_index = 0xFFFFFFFF`, `n_bits = 0`:
`84783→123131`, `91368→122603`) — nothing to encode, trivially consistent. The
remaining **21 resolvable arcs** are the oracle set.

| Tier | arcs | bit_group EXACT | flat bits EXACT | mismatch |
|------|------|-----------------|-----------------|----------|
| **Tier 1** `trace_proven_edges` (full select+exclusion bits) | 21/21 present | **21/21** | **21/21** | 0 |
| **Tier 2** `edges` band (independent +2513 derivation, select bits only) | 6 of the 21 fall in the band | **6/6** | **6/6** (select bits are the exact trace subset) | 0 |

Tier 1 is the hand-bound tier and is expected to match. **Tier 2 is the load-bearing
result**: those 6 arcs were derived purely from the static device file (asm pool +
template pool + the `slot = creation_index + 2513` band map) with **no trace input**,
and every one returns the correct bit-group and the exact select bits the live
assembler emitted.

---

## 2. Round-trip — table bits → rbf position → real bitstream

`bitpos_to_rbf.flat_to_rbf()` maps each flat CRAM index to `(rbf_byte, rbf_bit)`.
specimenA/B carry Quartus convention (magic `0x6a`) and are read directly; the vendor
target `target.rbf` carries rbf_lib convention (magic `0x56`) and is per-byte
bit-reversed first (after bitrev its magic is `0x6a f7 f7 …`, confirming the
normalization). A round-trip is a match iff the bit actually present in the bitstream
equals the value the table predicts.

**specimenA** (the design the trace came from):

```
TPE full-bits (incl. value-0 exclusion bits): arcs 21/21  bits 158/158  unmapped 0  MISMATCH 0
band select-bits (6 trace-overlap arcs):       arcs  6/6   bits  18/18   unmapped 0  MISMATCH 0
```

Every one of the 158 table bits — the value-1 select bits **and** the value-0
in-group exclusion bits — is exactly the bit Quartus wrote into `specimenA.rbf`.

**target.rbf — device-wide address validity + live decode of the actual target.**
Grouping the 352,674 band edges into **285,332 dest muxes** and reading each mux's
select bits out of the real target:

```
total band select bits read device-wide: 1,040,983   UNMAPPED flat addresses: 0
mux classification:  UNUSED 210,902   DECODED 7,987   REFUSED 66,443
```

- **0 unmapped** — every flat address the table emits lands on a valid CRAM cell of
  the target under the frame geometry. The address half of the format is correct
  device-wide.
- **7,987 muxes DECODED** — the read select pattern exactly equals exactly one
  enumerated arc, i.e. **7,987 live routing arcs recovered bit-exact from an
  independent vendor bitstream the table was never built from** (top classes:
  C4→LOCAL_INTERCONNECT 1763, C4→C4/R4, R24→C4, C16→…). Zero of these are ambiguous.
- **66,443 REFUSED** — a non-zero mux whose winning source is **outside the bound
  band** (LE_BUFFER / low-`ci` / pdb back-ref sources the table deliberately did not
  enumerate). These are honest coverage gaps, **not** contradictions: no refused mux
  produced a bit that disagrees with a table arc.

---

## 3. Holdout — specimenB (a compile the table never saw)

specimenB is a second Quartus compile, **not** used to build the table. Its capture
(`captureB.jsonl`, `specimenB.rbf` magic `0x6a`) has 28 arcs: 8 shared with
specimenA, **20 new (holdout)**, 2 hardwired.

```
resolvable arcs (26):  in trace_proven 7   in band 7   NOT in table (refused src) 12
HOLDOUT arcs (not in specimenA) present in table: 7   bit_group EXACT 7/7   bits EXACT 7/7
ROUND-TRIP vs specimenB.rbf:  bits 69/69  unmapped 0  MISMATCH 0
```

**This is the strongest generalization result.** 7 arcs that appear in specimenB but
**never in specimenA's trace** were predicted from the static device file alone
(band tier), and every one matches specimenB's real bitstream on bit-group and all
flat bits — "predict the bits for an arc no specimen-A run used, then confirm by an
independent compile." The 12 not-in-table arcs are the same class of honest
out-of-band-source refusals seen in the foreign target.

---

## 4. Coverage honesty — which routing classes the static table covers

Bound (enumerated) **source** classes in the band: mostly C4, plus R24/C16/R4 and
UNBOUND_GAP source ids. Bound **dest** classes seen in decoded/enumerated arcs:
`LOCAL_INTERCONNECT` (the LI wall taps that were 0 before), `C4`, `R4`, `C16`,
`R24`, plus arithmetic-exact ids in node-id GAP ranges (class label pending block
bind). The **bits half** (node→group→CRAM flat address) is byte-exact whole-device
for **every** class from the asm pool.

**Refused (never bluffed):** low-`ci` sources (LE_BUFFER, ~85% of R4, IO/CLK) whose
`+2513` band offset does not hold; 90,857 pdb back-ref sources that share a template
resolved only where grounded; and block-level muxes (the 590 `blockmux` records —
separate resolver, not router node→node arcs). These are exactly why 12/26 specimenB
arcs and 66,443 the foreign target muxes are REFUSED rather than decoded.

## 5. Bottom line for the schema

- Oracle arcs checked (specimenA resolvable): **21**, exact match **21**, mismatches **0**
  (plus 2 hardwired correctly carrying no bits).
- RBF round-trip exact on used arcs: **true** — specimenA 158/158, specimenB 69/69,
  the foreign target 0 unmapped over 1.04 M bits with 7,987 arcs decoded bit-exact. **0 mismatch anywhere.**
- Holdout: **7/7** device-file-only predictions confirmed against an independent
  compile (specimenB), 0 mismatch.
- Real: **yes**, device-wide for every arc it does not refuse. Format (both the
  node→group→bit resolution and the flat→rbf address transform) verified correct on
  three independent real bitstreams. Partial by source coverage, honest about the gap.
