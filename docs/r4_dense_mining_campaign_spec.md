<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# R4 dense-design per-net mining — campaign spec (draft)

**Status:** NOT started. Written 2026-07-06 as the entry gate for the next
R4 segment, so the campaign begins with a design + a pass bar instead of
re-running the exhausted two-LUT chain method.

**Target:** the 6 R4 I-indices still not in `_R4_BASE_PREV`:
`{5, 9, 28, 30, 32, 33}`. These are ~29% of NEORV32's R4 demand
(see `step0b_route_demand_2026_05_31`). Everything else (27 of 37 indices)
is emittable.

## Why the cheap methods are exhausted (do not repeat)

1. **Green-zone corpus free-mine** — the targets are absent (only rightward
   wires were ever driven). Falsified 2026-05-31.
2. **Single-design STA base recovery** — a design's active set saturates the
   candidate window; no base separates. Falsified 2026-05-31.
3. **Two-LUT leftward chains** (this session) — long chains DO produce the
   targets at labeled `(wire_x, I)`, but:
   - deep-chain hops co-occur in FIXED bundles, so per-hop isolation
     (intersect-with minus union-without) cannot separate a hop from its
     neighbours;
   - incremental-reach XOR does not isolate one hop either — changing the
     reach relocates the endpoint LUT (~16 SRAM cells swamp the ~2 R4 cells);
   - a "driver-end (rel+3)" anchoring looked right but was a
     **co-occurrence trap** — rel+3 cells are the neighbour hop's prev-cell.
   Evidence: `results/r4_chain_calibration.json`.

## The one idea not yet tried: dense per-net differencing

Break co-occurrence by making the target hop the ONLY thing that changes
between two otherwise-identical DENSE designs.

- Take a dense base design that routes a target index I at wire_x (NEORV32
  itself, or a synthetic congested filler that forces I onto that reach).
- Produce a sibling that is **byte-identical in placement and all other
  nets**, differing in exactly ONE net that uses the target R4 wire — e.g.
  by `dont_touch` + a one-net logic edit, or LogicLock region reuse.
- `XOR(base, sibling)` then isolates that ONE net's routing delta. If the
  net is a single R4 hop, the delta is the target's cells (plus its two
  endpoints — keep endpoints fixed across the pair so they cancel).

Congestion-forcing variant: place many `dont_touch` filler LUTs to force the
router onto a *specific* R4 reach, holding endpoints fixed, and toggle only
the one net.

## PASS BAR (mandatory — this is the co-occurrence guard)

A base pair lands in `_R4_BASE_PREV` only if ALL hold:

1. **Anchoring proven by DOC recovery first.** On the same corpus/harness,
   the method must recover the documented pairs of >=3 already-mapped
   indices (e.g. I=17 2802/3223, I=20 2791/3001, I=21 2786/3207) under
   `prev_col(wire_x)` before any unmapped result is trusted. (This is the
   check that caught the driver-end trap.)
2. **Single-net isolation, not co-occurrence.** The target's cells must come
   from a pair of designs differing in ONE net — NOT from
   intersect/union over designs where the target always appears bundled with
   the same neighbours. State explicitly which net differs.
3. **>=3 distinct wire_x (or prev-columns)** vote the same pair, negatives
   (designs without that hop) under 8%.
4. **Proper 210-delta pair** at the slot's bit-position, both cells present.
5. **No index-shift alias:** confirm the landed pair is NOT equal to a
   mapped index's pair at a neighbouring column (the trap signature).

Failing any -> do not land; record the negative.

## After landing

- `pip_prediction_gate.py` for read-side holdout, then a `write_r4()`
  prototype + ζ-style byte-identity gate on a Quartus gold. No flash until
  a gold-anchored byte check passes (flash budget 2/3; standing protocol in
  `flash_budget_state`).

## Also flagged (separate small audit)

`_R4_BASE_PREV[18] = (4057,4267)` and `[26] = (7210,6791)` look like
wide-column/+7350 artifacts; the chain campaign votes in-family values
(2799/3009 and 2759/3178). Worth a targeted re-derivation, independent of
the 6-index campaign.
