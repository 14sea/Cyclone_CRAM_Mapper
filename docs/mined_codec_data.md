<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# Mined codec data (device-general)

Notes on two mined result files under `results/` — facts about the EP4CE silicon
(no target design in them), produced with this repo's tooling.

## `results/rcf_wire_cells.json` — routing wire → CRAM cells (102 wires)
Maps a named routing wire to the exact CRAM `[offset, bitpos]` cells that encode it,
across **five** switch classes — `C4:` (24), `C16:` (4), `R4:` (38), `R24:` (4),
`LOCAL_INTERCONNECT:` (32) — e.g.

```json
"R24:X9Y12S0I23": [[225382, 3], [225786, 3]],
"LOCAL_INTERCONNECT:X13Y10S0I30": [[100508, 4], [100929, 4], [101773, 4]]
```

Produced by RCF back-annotation: compile pair designs that force a known route,
capture the exact wires Quartus used (`quartus_cdb --back_annotate=routing`) and the
CRAM diff, then signature-correlate wire ↔ cell. Solid positive data — a direct
contribution to the routing codec. **Note:** the producing miner is *not* included
here (it's coupled to the larger mining pipeline); the method above is the
reproduction recipe, and the `.json` stands on its own as consumable data.

## `results/iostd_specimens.jsonl` — raw IOB electrical specimens (a documented dead end)
25 raw `full_diff` specimens (per record: `{pin, label, cells}`) from building the
same buffer with a matrix of IOB settings (I/O standard / drive / slew / pull /
registered) on three anchor pins in different banks. Feed them to
`fuzz/iostd_codec_mine.py --analyze` to reproduce the (weak) codec.

**Honest negative — read before using.** The intended product was a per-setting
*position-invariant* electrical codec (variant-vs-ref diff cancels routing → only the
electrical bits remain, intersected across pins). It did **not** pan out: each setting
moves ~26–122 cells per pin, but the cross-pin invariant intersection is 0–3 cells
with pairwise Jaccard ~0.02–0.16 — and even those 1–3 cells are largely a
normalisation artifact (min-offset anchoring forces `[0,0]` into every non-empty
setting). `drive_max`/`slew_fast`/`fast_oreg` are no-ops (default LVTTL is already
max-drive/default-slew; a combinational buffer has no output register). So the
electrical bits are not cleanly position-invariant under min-offset normalisation.
The **raw specimens are committed on purpose** so the dead end is *re-analyzable* —
try a better alignment (per-bank, or anchoring to the IOB base rather than the delta
min) without re-spending the Quartus time. The regenerated summary
(`results/iostd_codec.json`) is intentionally not committed — it's content-free; run
`--analyze` to produce it.
