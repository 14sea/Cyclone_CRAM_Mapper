# LUT codec — validation against the golden pair-diff sweep (42/42)

Device-general (die `cycloneive1`, EP4CE6 == EP4CE10). Code: `scripts/lut_sigma.py`
(logical-function recovery), `scripts/lut_fullgrid.py` (device-wide physical-mask
extraction + invertibility proof). Result: `results/lut_fullgrid_result.json`.

This codec's physical cell geometry is validated **against this repo's own golden
LUT-mask sweep** (`results/golden_rbf_modeH/`) — the pair-diff corpus that places
one LUT at a known LAB `(X,Y,N=0)` with a known 16-bit mask and diffs it against
the same-LAB `mask0000` build. Ground truth used: raw `.rbf` bytes, `.diff`/
`.cells` flip lists, and `mask+X+Y+N` from the filename only. No conclusion or
summary text was consulted; every number is re-derived from raw bits.

## Method (per golden design)

1. Compute the 16 predicted **physical** mask cells `le_cells(X,Y,0)` →
   `{phys_bit : (rbf_byte, bit)}` and read those 16 cells straight out of the
   target `.rbf`.
2. Require all four criteria: (a) all 16 predicted cells resolve through
   `flat_to_rbf` (no `None`); (b) every LUT-band flip in the `.diff` lands on one
   of the 16 predicted cells (no stray LUT cell); (c) the number of predicted
   cells reading `1` equals `popcount(mask)`; (d) the 16-bit value read back is an
   input-axis permutation of the intended mask (the only physical degree of
   freedom).

## Result: 42/42

Every one of **14 LABs × {0x4444, 0x6996, 0xDEAD} = 42 designs** passes all four
criteria.

| mask | popcount | LUT-band flips matched | read-back |
|------|----------|------------------------|-----------|
| 0x4444 | 4 | 4/4 on predicted cells, 0 stray | input-perm of 0x4444 at all 14 LABs |
| 0x6996 | 8 | 8/8 on predicted cells, 0 stray | exactly 0x6996 at all 14 LABs (parity mask is perm-invariant) |
| 0xDEAD | 11 | 11/11 on predicted cells, 0 stray | input-perm of 0xDEAD at all 14 LABs |

LABs covered (all four device columns): `X ∈ {10,16,22,28}`,
`Y ∈ {2,8,14,17,21}`. The read-back being an *exact permutation* of the mask —
not merely popcount-matching, with zero stray bits, at 14 independent LABs — is a
strong test: a wrong cell-location table would have to yield a clean 4-input
permutation of the intended value at every LAB by chance. **The physical-cell
geometry is bit-exact.**

Degenerate masks confirm decode-or-refuse: `mask0000` baseline and
`mask0000→maskFFFF` show 0 LUT-band cells — constant-0/1 LUTs are optimized to
GND/VCC (no LUT placed) and the codec correctly claims nothing.

## Input permutation (`sigma`) is per-build, not a codec constant

The recovered input permutation differs between `0x4444` and `0xDEAD` at the same
LAB (disjoint sigma candidate-sets) — expected, since each mask is a separate
compile and Quartus freely re-orders the 4 LUT inputs. `le_cells` localizes the 16
physical cells independent of routing; only the design-bit→physical-bit relabel is
routing-dependent. `lut_sigma.py` resolves the logical truth table over the LE's
four **physical** ports by a single constant axis reversal (swap port bit0↔bit3,
bit1↔bit2 — the endianness gap between the pair/delta index and Quartus's
dataa-LSB minterm order); this reversal is position- and routing-independent
(proven on 11 mined sigma classes × 19 distinct routings, 19/19 recovered). Naming
each function to its input nets then needs the per-design LEIM-resolved driver per
port, supplied by the connectivity layer.

## Device-wide extraction (EP4CE10)

`lut_fullgrid.py` extends the extraction to the full 28-column × 18-row CE10 grid
(the CE6 22 columns plus the 6 jailbreak columns `{5,9,14,30,32,33}`), proves the
mask cells are pairwise disjoint across all LEs, and proves a
zero→write→read cycle reproduces every recovered mask. `lut_fullgrid_result.json`
records the per-target used-LE counts and confirms zero cell-disjoint violations
and zero round-trip failures.
