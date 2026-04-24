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

## Adding a fixture

1. Produce a Quartus gold RBF under `tmp/` or `results/rbf/`.
2. Add an entry to `manifest.json` with `sha256: "TBD"` and
   `zeta_bits_total: 0`, then run
   `python3 scripts/bit_workaround/zeta_regression.py --reanchor` — this
   fills in the SHA256 and region counts for any entry whose SHA starts
   with `TBD`.
3. Commit both the manifest change and a memory / CLAUDE.md pointer if
   the fixture exercises a novel directive path.
