# ζ corpus

Golden Quartus RBFs used by `scripts/bit_workaround/zeta_regression.py` to
guard the ζ → fasm2rbf round-trip.

`manifest.json` pins each fixture by SHA256 + expected region-cell counts
(derived from `zeta_rbf_diff.py` vs the ζ baseline). The fixture RBFs
themselves are gitignored (produced by Quartus, 368 011 B each), so the
regression runner is expected to:

- **skip** with a warning when a fixture is missing locally,
- **fail loud** when a fixture is present but its SHA256 no longer matches
  the manifest (the gold has drifted — decide whether to re-anchor or
  investigate),
- **fail loud** when ζ → fasm2rbf does not reproduce the gold byte-for-byte,
- **fail loud** when the region-cell counts diverge from `region_bits` /
  `region_bytes` (catches ζ or baseline drift even when the round-trip
  still succeeds).

## Re-anchoring after an intentional change

If you intentionally change the baseline or add a new design, run

```bash
python3 scripts/bit_workaround/zeta_regression.py --reanchor
```

to overwrite the manifest with the current SHA256s and region counts. The
re-anchor flag is the only supported way to update this file — hand edits
defeat the point.

## Fixture sources

- `two_lab` — built locally by Quartus at
  `tmp/chipdb_test/quartus_two_lab/` (run `quartus_sh --flow compile two_lab`
  in that dir if missing).
- `lits_pair_y11_*` — produced by the sig-cache mining factory under
  `results/rbf/` (regenerable via `fuzz/route_synth.py` mining).
- `neorv32_demo` — NEORV32 bootloader gold; external source is
  `~/see_neorv32_run_linux/output/neorv32_demo.rbf`. Copy it into
  `tmp/zeta_fixtures/neorv32_demo.rbf` (the path pinned by
  `manifest.json`) to activate this entry in the regression. The
  external repo is read-only by house rule — do not modify
  `~/see_neorv32_run_linux/` directly.
- `nv_zero_global_self` — the ζ baseline at `results/rbf/nv_zero_global.rbf`,
  used against itself as the empty round-trip edge case.

## Adding a fixture

1. Produce a Quartus gold RBF under `tmp/` or `results/rbf/`.
2. Add an entry to `manifest.json` with `sha256: "TBD"` and
   `zeta_bits_total: 0`, then run
   `python3 scripts/bit_workaround/zeta_regression.py --reanchor` — this
   fills in the SHA256 and region counts for any entry whose SHA starts
   with `TBD`.
3. Commit both the manifest change and a memory / CLAUDE.md pointer if
   the fixture exercises a novel directive path.
