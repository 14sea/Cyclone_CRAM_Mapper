# Stage 0 HW Flash Bundle — 2026-04-17

Three codec-ready, HW-untested directives packaged as simple_led
overlay RBFs for silicon falsification.

## Contents

| Directive | RBF | Safety gate | Expected flash behavior |
|-----------|-----|-------------|-------------------------|
| `LUT_ARITH_MULTI_LAB WIDTH=17` | `simple_led_lut_arith_ml17.rbf` | CONDITIONAL (2 fabric overlaps in unused LAB cols 0/25) | LED0 follows KEY2 |
| `X15Y10N0.M9K_MODE_9x512_inferred_goldintersect` | `simple_led_m9k_mode_goldintersect.rbf` | SAFE (0 fabric overlap, 38 cells in block band) | LED0 follows KEY2 |
| `IOB_OE PIN_R5` (= sdram_dq S_DB[0]) | `simple_led_iob_oe_r5.rbf` | SAFE\* (2 block-band overlaps, 0 fabric) | LED0 follows KEY2 |
| DSPMULT_GLOBAL_ON bisect layer 1 — half A (cells 0..10) | `simple_led_dspmult_half_A.rbf` | SAFE\* (block-band only) | LED0 follows KEY2 (or narrows the 2026-04-16 FAIL) |
| DSPMULT_GLOBAL_ON bisect layer 1 — half B (cells 11..22) | `simple_led_dspmult_half_B.rbf` | SAFE\* (block-band only) | LED0 follows KEY2 (or narrows the 2026-04-16 FAIL) |

All three overlay the same `simple_led_pure` base (PURE_ZERO +
NV_BASELINE_PACK + IOB\_IN/OUT/CLK + IOB\_ROUTE + GCLK + LAB\_CLK\_SEL
+ LAB\_CLK\_SEL\_LE). simple_led routes KEY2 (PIN_E16) → LED0 (PIN_G15)
through LAB(10,4).N=0 with a CLK pin at PIN_E1.

## Flash procedure

For each RBF:

```bash
openFPGALoader -c usb-blaster scripts/stage0_flash_bundle/<rbf>
```

Then press and release KEY2. LED0 must toggle — same behavior as
`scripts/iob_slice_mining/work/simple_led_E16_to_G15/fasm_pure.rbf`.

## Acceptance criteria

- **PASS** — LED0 follows KEY2 exactly as simple_led_pure. Directive
  bits are silicon-inert on top of simple_led → codec is safe to
  consume from np2fasm (pending context-specific gating per
  directive, see notes below).
- **FAIL** — LED0 stuck on/off, flickers, or behaves non-deterministically.
  Same failure mode as DSPMULT_GLOBAL_ON on 2026-04-16: directive
  bits leak into LE / IOB / clock fabric → directive must stay gated
  in codec (do NOT wire np2fasm consumer) until bisection identifies
  the leaking cell(s).

## Per-directive notes

### `LUT_ARITH_MULTI_LAB WIDTH=17`

Activates the wide-carry chain at LAB(4,18) full + LAB(4,17) partial
(N=30→N=0 inter-LAB carry link). 207 data cells spanning block
band + LAB(4,17..18) data region. 2 fabric-band bit overlaps with
simple_led's baseline — both in columns simple_led does NOT route
through (col 0 = IOB, col 25 = unused LAB). Flash is likely
harmless but not strictly provable from bit-overlap alone.

If PASS, widths 17..32 are safe to emit. Yosys `$alu` techmap
currently caps at single-LAB (8 LE / width≤8); multi-LAB emission
requires a Yosys pass to break wide add into LAB-sized blocks.

### `X15Y10N0.M9K_MODE_9x512_inferred_goldintersect`

38-cell subset = `inferred` ∩ `smoke_gold` at block band frames
1716..1738. Codec ungate landed 2026-04-17 in commit 37489c1; HW
flash decides whether np2fasm should prefer the goldintersect
suffix (= functional → ungate on smoke gold) or stay gated (= even
the 38-cell safe subset leaks → different mining approach needed).

No fabric overlap with simple_led. Cleanest probe in the bundle.

### DSPMULT_GLOBAL_ON bisection (layers 1)

2026-04-16 flash FAILed with all 23 cells applied (LED0 stuck
constant-on). Layer-1 bisection splits the 23 cells roughly 50/50
and flashes each half independently to localize the leaky cell(s):

- half_A (cells 0..10, 11 cells, frames 1694..1708)
- half_B (cells 11..22, 12 cells, frames 1710..1729)

Outcomes:
- A PASS + B PASS → interaction bug (cells are individually
  safe but compose into a bad state)
- A FAIL + B PASS → leaky cell is in {0..10}; run layer 2 on half_A
- A PASS + B FAIL → leaky cell is in {11..22}; run layer 2 on half_B
- A FAIL + B FAIL → leaky cell in each half OR XOR masking;
  rebuild with smaller partitions

log2(23) ≈ 5 rounds to isolate a single cell.  Rebuild subsequent
layers with `scripts/stage0_flash_bundle/build_dspmult_bisect.py`
after editing the partition.

### `IOB_OE PIN_R5` (sdram_dq S_DB[0])

40-cell per-pin OE activate set for R5 (packaged SDRAM DQ0). 21-cell
universal core + 19 per-pin cells. 2 block-band bit overlaps with
simple_led's baseline (block-band = M9K/MULT/arith defaults, which
simple_led doesn't use).

Sdram_dq is physically disconnected on AX301 unless SDRAM is
populated — toggling R5's OE enable should be a silicon no-op on
fabric/LED. If LED breaks, OE cells leak into non-IOB routing
(equivalent to DSPMULT failure mode).

If PASS, np2fasm can wire Yosys `$tribuf` → IOB_OE for the 16 mined
sdram_dq pins.

## Reproducing the RBFs

```bash
python3 scripts/stage0_flash_bundle/build_simple_led_lut_arith_ml_probe.py
python3 scripts/stage0_flash_bundle/build_simple_led_m9k_mode_gi_probe.py
python3 scripts/stage0_flash_bundle/build_simple_led_iob_oe_probe.py
```

Each script: loads PURE_ZERO → applies simple_led FASM stack + one
directive → patches CRC → runs the bit-level safety gate → writes
the 368011-byte RBF alongside itself.

## Related bundles

- `scripts/iob_slice_mining/build_simple_led_pure.py` — the
  `simple_led_pure.rbf` reference build (no directive overlay).
- `scripts/iob_slice_mining/build_simple_led_dspmult_probe.py` —
  the DSPMULT_GLOBAL_ON probe that falsified on silicon
  2026-04-16 (LED stuck). Same pattern as this bundle; kept as
  a cautionary companion.
