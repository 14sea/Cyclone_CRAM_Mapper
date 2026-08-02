# Clear-plane full-field-mask resource enumeration (KNOWN-0 via decode-or-refuse)

Device-general (die `cycloneive1`, EP4CE6 == EP4CE10). Code:
`scripts/routing_fullfield_codec.py` (device-wide off-mux), `scripts/logic_fullfield.py`
(LE/LAB-secondary + LUT off-fields), `scripts/io_fullfield.py` (IOE + PLL off-fields).
Validated with the two-background ledger (`ownership_completeness_oracle.md`).
Provenance: transcribed from an EP4CE6/EP4CE10 device-file RE campaign; validation image
`<target>.rbf`.

## What

The ownership oracle's dominant gap is **UNKNOWN_CLEAR** — the vast off-state (clear)
plane a from-blank encoder never writes because it only ever emits cells for
DECODED-ACTIVE features. To **own** that plane, each enumerated resource's codec writes
its **complete field mask**: the decoded value where set **and** an explicit 0 for every
unselected / unused cell in that resource's device-file footprint. An off resource then
becomes **provably KNOWN-0**, not merely left-at-blank. Applied to three resource
families:

1. **Routing off-muxes** (`routing_fullfield_codec.py`). Uses the routing.ddb
   node→template load-order permutation (a facade over the item-1 DYGR parser) to bind
   **every** routing element to its byte-exact asm footprint. For each mux: entire
   footprint observed 0 → OFF → clear the whole footprint (KNOWN-0); any footprint cell
   observed 1 → ACTIVE → **REFUSE** (leave the set cells to the connectivity codecs).
   This needs no per-group select-vs-fanout tagging, because a fully-off element's every
   field cell is 0 regardless.
2. **LE/LAB-secondary + LUT off-fields** (`logic_fullfield.py`). For each enumerated
   LE/LAB-secondary instance: DECODED (signature is an observed codeword) → set real-1,
   clear real-0; OFF (all-zero signature) → clear the whole footprint; REFUSED (non-zero
   unobserved) → clear only the real-0 cells, **refuse the real-1 cells**. LUT: the 16
   physical truth-table cells are the value, so set mask-1 / clear mask-0.
3. **IOE + PLL off-fields** (`io_fullfield.py`). IOE input muxes, IOE output/OE
   registers (main-CRAM), and PLL/global-clock main-CRAM fields: ACTIVE codeword → set
   codeword, clear the rest; all-zero → OFF, clear whole field; non-codeword non-zero →
   REFUSE.

**The gate (0 INVENTED, 0 WRONG_CLEAR) holds by construction:** the only SET cells
written are real-1 (a decoded codeword / physical-mask bit); a cell is CLEARED only
where the decode proves 0 (an off footprint, an active field's non-codeword cells, a
LUT mask-0 bit). A real-1 cell can never enter a clear set — any resource that would
clear it must have observed it as 0, which is impossible — so plan writes are globally
single-valued and equal the real image on every touched position.

## Why device-general

Every footprint is fixed device geometry: the routing permutation is disasm-pinned (not
oracle-fit) from the vendor reader (`DYGR_ROUTE_INFO_BODY::operator<<` @`0x3c6900`,
`PDB_SEGMENT_READER::xfr_ptr` @`0x10bfe0`, `finish_reading_all` @`0x10c640`); the LE/LAB,
LUT, IOE and PLL field footprints are the assembler's resolved device-file tables. The
"is this resource off?" test reads the real image, but the footprints it reads are the
same on every design on the die.

## How validated

Each codec's clear-plane delta is measured bit-exact by the two-background ledger over
all 2,944,088 positions, with `wrong_clear == invented == 0` asserted in every measure
harness:

| codec | stacking point | newly-owned clears (UNKNOWN_CLEAR → KNOWN-0) | ownership move |
|---|---|--:|---|
| routing off-mux + LUT off-field (baseline pass) | bare ledger baseline | **+51,885** (LUT off 28,592 + routing off-mux 23,293) | 9.5346 % → 11.2969 % |
| device-wide routing off-mux (permutation) | prior routing/LUT overlay | **+68,476** (72,403 footprint cells cleared) | 12.6877 % → 15.0135 % |
| IOE + PLL off-field | routing/LUT clear baseline | **+1,368** (ioe-mux-off 1,328 + ioe-reg-off 8 + pll-off 32) | 11.2969 % → 11.3434 % |
| LE/LAB-secondary off-field | routing/LUT clear baseline | **+240** (35 fully-off LE/LAB blocks; standalone over baseline +28,832 incl. LUT) | +0.0082 pp |

Plan stats confirm decode-or-refuse rather than blanket zeroing: routing (baseline)
213 active / 3,275 off / **1,822 refused**; device-wide permutation binds **30,205** of
135,117 nodes as routing muxes (26,771 active refused, 3,434 off cleared); IOE input
muxes 64 active / 121 off / **0 refused**; LE/LAB-secondary 11 decoded / 35 off / **19
refused** (56 real-1 bits left UNKNOWN_SET, not bluffed).

## Honest limits — declared, not bluffed

Some clear classes remain **un-enumerated** and are left UNKNOWN_CLEAR rather than
guessed:

- **Interior LE_BUFFER / local-interconnect geometry.** Of the 135,117 DYGR nodes, only
  30,205 are routing muxes; the other **104,817 `no_template`** nodes are the LE_BUFFER
  geometric-CALC / local-interconnect interior — provably **not** routing elements, so
  correctly not claimed here (they need intercept-gated per-design compile geometry).
- **Device-wide per-site LE/LAB secondary + mode geometry.** The LE/LAB-secondary codec
  is a harvested-block codec knowing only the enumerated blocks; an EP4CE10 has ~7,616
  LE sites across 476 LABs, so the vast majority of per-site
  `LE_REGISTER_SECONDARY_CONTROL` / `LE_MODE_FIELD` (and LAB-granularity) off-fields are
  not enumerated — closing them needs the per-site field-cell geometry harvested
  device-wide from the asm/routing device file.
- **256 routing source-ungrounded set cells** sit inside permutation-bound footprints
  but match no select codeword the device file enumerates → REFUSED (0 closed here);
  they need a mux-region codeword codec, not the load-order permutation.
- **Aux/dummy-plane LE/LAB SRC/CLK muxes** (arch 231/247/248/254/506/234/235) and the
  **IOE 0xa0 CFF input register** and **single-bit PLL_AUX** live in planes not
  serialized to frame CRAM (or are maximally ambiguous alone) → un-ownable from a `.rbf`,
  refused wholesale.
- **M9K unused-block init/mode fields** are grounded only at specific columns/lanes; the
  full per-block field is not enumerable device-wide → left UNKNOWN_CLEAR (M9K is unused
  on the validation image).

Net: full-field-mask enumeration is the resource-by-resource path that moves
all-position ownership up from the set-bit floor, with every un-enumerated class
declared and refused rather than counted.
