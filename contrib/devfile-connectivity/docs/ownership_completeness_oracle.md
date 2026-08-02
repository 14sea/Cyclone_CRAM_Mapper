# Ownership completeness oracle — two-background ternary ledger over every position

Device-general (die `cycloneive1`, EP4CE6 == EP4CE10). Code: `scripts/ledger.py`.
Result: `results/ownership_ledger_report.json`. Provenance: transcribed from an
EP4CE6/EP4CE10 device-file RE campaign; the validation image is `<target>.rbf`.

A rigorous **from-blank ownership metric** over all 2,944,088 serialized positions of
the 368011-byte image, replacing the set-bit count (which over-counts by treating
implicit zeros as owned) with a per-position ternary census under a strict
**no-implicit-zero-as-owned** discipline.

## What

The honest core is a **two-background write-mask**. The from-blank encoder is run
twice — onto an all-zero (`0x00`) background and onto an all-one (`0xFF`) background. A
position is **WRITTEN (owned)** *iff the encoder emits the same value on both
backgrounds* — i.e. some codec actively drives that bit, set **or** clear. A position
whose value follows the background (0 under bg0, 1 under bgF) is a **passthrough** — no
codec touches it — and is **UNKNOWN**, never owned. A bit merely left at blank-0 is
therefore never counted as owned.

Every position is then assigned exactly one ternary state, with the explicit
write-mask deciding membership:

| state | meaning |
|---|---|
| **KNOWN** | written, value == real, from a device-file table or a format constant |
| **DERIVED (emitted)** | frame CRC written from blank, matches real (generator proven) |
| DERIVED (pending) | frame CRC provably generable but gated on an upstream UNKNOWN payload — closes for free |
| **DONTCARE_PROVEN** | value proven irrelevant to the netlist (hook for inactive-resource proofs) |
| **UNKNOWN_SET** | real=1, unwritten — the true residual set bits |
| **UNKNOWN_CLEAR** | real=0, unwritten — implicit-zero, honestly NOT owned |
| INVALID_REFUSE | real=1 refused codeword (the header integrity floor) |
| **INVENTED / WRONG_CLEAR** | written ≠ real — MUST both be 0 |

The oracle emits two representations: `physical_config_ir` (the exact per-position bit
assignment the model asserts — write-mask + values) and `lifted_netlist` (the
structured feature model that projects onto it).

## Why device-general

The metric, the two-background write-mask, and the ternary census are design- and
target-independent by construction — they measure any from-blank encoder against any
real image on the die. Nothing target-specific enters; the only device-file content is
the encoder being measured (harvested tables under `$QUARTUS_ROOTDIR`).

## How validated

On the validation image, over all **2,944,088** positions (`ownership_ledger_report.json`):

- **KNOWN 272,590 + DERIVED-emitted 8,117 = 280,707 owned** →
  **STRICT all-position ownership 9.5346 %**, `reachable_if_derived_pending_closes`
  9.7664 %.
- **INVENTED 0, WRONG_CLEAR 0** (asserted invariants) — the decode-or-refuse gate holds:
  the model never writes a wrong bit.
- All invariants pass: `ternary_sum == 2,944,088` (every position classified once);
  `owned_set_bits + residual_set_bits == total_set_bits`;
  `written == KNOWN + DERIVED_emitted + INVENTED + WRONG_CLEAR`;
  `Σ residual-class cells == UNKNOWN_SET`.
- **Set-bit continuity** reconciles the old metric: `owned 180,077 / 194,948 =
  92.3718 %`; the residual `14,871 = 7,942 UNKNOWN_SET + 6,823 CRC-pending + 106
  refuse`. Both are true statements over different denominators; the 9.53 % all-position
  figure is the honest one under no-implicit-zero.

## The two real gaps it separates

The dominant honest gap is **UNKNOWN_CLEAR = 2,648,510 (89.96 % of the image)** — the
clear config plane not yet *proven* default — which is closed by resource enumeration +
proof-of-default (see `full_field_mask_enumeration.md`), **not** by more set-bit
closure. Orthogonally, **UNKNOWN_SET = 7,942** genuinely-unknown set bits are attributed
by device-file footprint to five ranked residual classes (dominated by
`unmodeled-arch-residual`, 5,292). Conflating the two — as a set-bit-only count does —
hides the clear plane entirely.

## Value

A strictly stronger completeness gate than set-bit counting: a resource can raise the
set-bit percentage while leaving the vast clear plane unproven. The ternary ledger makes
that gap explicit and un-gameable (implicit zeros are never credited), and its
INVENTED/WRONG_CLEAR invariants guarantee that adding a codec can only ever *raise*
proven ownership, never silently corrupt an existing claim.

## Honest limits

`DONTCARE_PROVEN` and `OPAQUE_PRESERVED` are 0 here — there is no don't-care oracle yet
and raw passthrough is off; both are declared hooks, not claimed ownership. The
INVALID_REFUSE floor (106 header-integrity bits) is the irreducible refuse floor
(`header_integrity_field.md`). `ledger.py` is shipped as the **orchestration pattern**:
it drives the campaign's device-file-grounded encoder and overlay tables that live
outside this contribution — wire your own from-blank encoder into `encode_bg`; the
portable, load-bearing parts are the two-background write-mask and the ternary census.
