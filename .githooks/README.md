# Repo-local git hooks

This directory holds versioned git hooks. They are not active until you
point git at them in your clone:

```bash
git config core.hooksPath .githooks
```

The config lives in `.git/config`, so it is per-clone (not shared via the
repo) — every contributor opts in once.

## Hooks

### `pre-commit`

Runs `scripts/bit_workaround/zeta_selftest.py` before every commit. The
selftest takes well under a second (one ζ round-trip on a HW-validated
two-LAB gold); if it fails the commit is blocked.

- Bypass once: `ZETA_SKIP=1 git commit ...`
- Disable entirely: `git config --unset core.hooksPath`
- If the selftest fixture (`tmp/chipdb_test/quartus_two_lab/output_files/two_lab.rbf`)
  is missing locally, the hook skips with a rebuild hint — it never
  blocks commits purely because of missing gitignored fixtures.

The goal is to catch regressions in `quartus_gold_to_bit_fasm.py`,
`fuzz/fasm2rbf.py`, or `fuzz/bitstream.py` CRC handling at commit time
rather than at flash time.
