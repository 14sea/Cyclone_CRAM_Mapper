<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->
# EP4CE6 Native-NEORV32 Routing — Model Scoping (2026-05-28)

Scopes the chipdb routing-model options for the open-toolchain native-NEORV32
blocker: **Option 1** (sig-cache-aware placement) vs **Option 2** (real
C4/R4/R24/LI wire classes on nextpnr-generic) vs **Option 3** (custom
`nextpnr-cyclone4` arch). Produced by a 6-agent design workflow
(`chipdb-routing-model-scoping`); load-bearing numbers spot-verified against
code/data on 2026-05-28 (see §0).

## 0. Premise corrections — VERIFIED against code/data (supersede older memories + CLAUDE.md)

- **Sig-cache = 13,562 entries** (the 38,683 in `chipdb_gen.py` comments + memories is STALE).
- **Pitfall #9 self-loop "90–754 cell bloat" is FALSE/STALE** — measured max self-loop 156 cells, median 131 (cross-entries max 159). Self-loops are topologically irrelevant (src==dst), not noisy. 2,760 of 13,562 are self-loops.
- **R24 write model is DEAD** — `bitstream.py` `_R24_FIXED_OFFSETS`: code comment "DEPRECATED 2026-04-08: 56/56 CRC bytes. Dead code." (CLAUDE.md "R24 66%" is READ-path only.)
- **C4 I≠0 write model is DEAD** — `_C4_FIXED_OFFSETS`: "44/44 entries land on frame CRC bytes (pos 208/209) … overwritten by patch_rbf_crc → dead code." (CLAUDE.md "44 mappings" is read-path only.)
- **FF ENA/ARST tables DEAD** — `_FF_ENA_CELLS`: "168/168 CRC bytes (100%). Dead code. Needs re-mining."
- **R4 = 26/37 I-indices** emittable. **np2fasm is path-blind** (`np2fasm.py:13`).
- Sig-cache LAB-pair coverage **2.7%** (3,921/156,420 ordered pairs); **~96.5% of mined sinks have exactly one legal source** (using a mined arc PINS both endpoints).

## 1. Current State

Target: `Verilog → Yosys → nextpnr-generic → np2fasm → fasm2rbf → flash` for
NEORV32 (~6628 LUT / 2048 DFF / 21 M9K) — the sole remaining *native* blocker
(ζ already ships NEORV32+Linux via Quartus gold). `fuzz/chipdb_gen.py` is a
**hybrid synthetic model** (~8.3k–12.1k bels, ~90k wires, 1.79M–3.66M pips,
rebuilt every nextpnr startup): point-to-point SIG pips from the sig-cache, an
INTRA_LAB direct layer, a synthetic `NUM_LOCAL_TRACKS=26`/LAB LOCAL fabric +
hop chains, a rev-7 per-bank IOB↔fabric gateway, GCLK + M9K + GND_BUS overlays.
**Pack + place PASS** (51 IOB + 21 M9K pinned); **route FAILS** — router2
negotiated-congestion *divergence* (plateaus ~2040 overused wires, never
converges) per `tmp/rev{5,6}_probe.log` (2026-04-17, **41 days stale**).

Two structural facts dominate: (a) the sig-cache is a fixed sparse
point-to-point graph (2.7% LAB-pairs, 96.5% single-source) — a demo set, not a
fabric; (b) all 51 IOBs funnel through 7 single-LAB 26-track gateways — a
model-independent chokepoint, unsolved for 41 days, and the *actual* current
blocker.

## 2. Option Comparison

| | Option 1 (sig-cache-aware placement) | Option 2 (real wire classes / generic) | Option 3 (custom `nextpnr-cyclone4`, Himbächel) |
|---|---|---|---|
| Effort (pw / tshirt) | 8–16 partial; **unbounded** full / XL | **30–60+** / XL | Option-2 data cost + 12–20 pw migration / XL–XXL |
| Risk | very-high | very-high | very-high |
| Routes NEORV32? | **No** (structural) | Unlikely | Unlikely until same data mined |
| Coverage ceiling | 0.0085% of LE→LE.port arcs; 96.5% single-source → fixed-topology embedding (infeasible) | weakest per-switch model: C4 I≠0 + R24 **dead**, R4 26/37, inter-class turn MUXes **unmodeled** | same data ceiling as Opt 2 |
| np2fasm impact | minimal (harden miss → REFUSE) | **decisive**: full path-aware rewrite + union-before-XOR + gate | same rewrite |
| nextpnr fit | poor & unimprovable (router2 escapes SIG→LOCAL) | loadable but no native span/switchbox; router2 scaling unbounded | best long-term fit; generic's scaling wall is what Himbächel fixes |

## 3. Implementation Paths (abridged — see §5 for the recommended order)

**Option 1:** extend `sig_routing_only` to skip LOCAL_IN/OUT; write
`prepack_sig.py` solving cell→mined-LE assignment (NEXTPNR_BEL via `--pre-place`);
recognise it as exact-cover into a degree-1.12 graph → infeasible for 4,712 LEs;
harden np2fasm cross-LAB miss into REFUSE-TO-BUILD. **Reject for NEORV32.**

**Option 2:** (0) coverage gate — measure locatable-vs-CRC-dead per class
[R24/C4-I≠0 currently dead → go/no-go]; (2) wire model from `config.COLUMN_BASE`
+ span constants (~63k wires); (3) switch-box pips incl. **inter-class turn
MUXes (no model — fresh fuzzing campaign, uncosted)**; (4) delays/congestion;
(5) **path-aware np2fasm rewrite (true critical path, 5–8 pw)**; (6) per-placement
Quartus-gold byte-diff gate (P5d passed analytical+safety and bricked — necessary
not sufficient).

**Option 3:** reject standalone Mistral-style ArchAPI (person-years); optionally
lift the existing uarch to Viaduct (mux-exclusivity as constraints) to relieve
IOB/router2 thrash; build the real graph as a Himbächel uarch (ideal for the
uniform 7350-stride columns) — **but it needs exactly Option 2's STEP 0–6 data**.

## 4. Shared Prerequisites (all options, regardless of model)

- **IOB↔fabric bridge dispersion** — the actual 41-day blocker; 51 IOBs through
  7 single-LAB gateways is a chokepoint in every model. Widening (rev5/6)
  thrashed; dispersion (more gateway LABs/bank, IOB-side input MUXes) is the
  untested fix. **The single most under-priced item — none of the options costs it.**
- **M9K data-port routing** — 21 M9K wide ports through the same gateways
  (GND_BUS hack signals constant-net LOCAL saturation); never routed end-to-end.
- **Sig-cache hygiene** — drop the 2,760 self-loops from the routing graph.
- **Per-placement Quartus-gold byte-identity gate** — the only trustworthy
  silicon gate (Pitfall #8), interacts badly with router2 non-determinism ×
  flash budget 0/3.

## 5. Recommendation — measure before you build

**Do not commit to Option 1/2/3 yet.** All three reasoned from a 41-day-old
route log and *assumed* the failure is fabric density — untested, and it
determines which option (if any) is even right.

- **Reject Option 1 for NEORV32** unconditionally (96.5% single-source pinning ⇒
  provably-infeasible fixed-topology embedding). Keep it for small/medium
  hand-pinned single/dual-LAB designs (the green-zone flow already does this).
- **Option 2 ≡ Option 3 on the gating dependency**: dead C4 I≠0 / R24 models,
  unmodeled inter-class turn MUXes, path-blind np2fasm. **Representation
  (Himbächel/Viaduct) is the wrong axis to optimise first — data correctness is
  the bottleneck.** If undertaken, target Himbächel (correct long-term home),
  but the dominant cost is a second turn-MUX RE campaign + Pitfall #14
  context-dependence that may make per-switch composition *silicon-impossible* at
  NEORV32 density — uncosted, unbounded, competing against a shipping ζ.

### Cheapest de-risking experiment — DO THIS FIRST (an afternoon; no Quartus, no flash, no new RE)
Re-run the existing rev-7 chipdb route on NEORV32, perturbing **only** the
IOB-bridge dispersion knobs already in the code: bump `NUM_LOCAL_TRACKS`
(`config.py:94`) for gateway LABs and/or assign 2–3 gateway LABs per bank
instead of one (`chipdb_gen.py:634–712`). Then read **where** router2's ~2040
overused wires concentrate (logs already emit per-iteration overuse):
- **Overuse drops / concentrates at the 7 gateway LABs** ⇒ blocker is IOB
  dispersion — a localized fix in the *existing* model. Both rewrites are
  premature; fix the bridge, re-baseline, re-scope. **Invalidates all three options' framing.**
- **Overuse stays ~2040, spread across *interior* LAB LOCAL tracks** ⇒ genuine
  fabric density; Option 2's real-span thesis (housed in Himbächel) is the only
  path with a ceiling above NEORV32 — *then* the 30–60+ pw is justified.

**The overuse distribution (gateway vs interior) has never been measured — only
its magnitude. That one measurement is the gate.**

## Key files
`fuzz/chipdb_gen.py` (IOB bridge L634–712; LOCAL L428–578; SIG pips L858–899),
`fuzz/config.py` (`NUM_LOCAL_TRACKS=26` L94), `fuzz/bitstream.py` (dead models
L50–52/L172/L196; R4 26/37; `apply_routing` L894–935; `write_*` L627–850),
`synth/np2fasm.py` (path-blind L13; cross-LAB warn L1299–1300),
`results/route_cells_full.json` (13,562 entries; max 159 cells/entry),
`tmp/rev5_probe.log`, `tmp/rev6_probe.log` (2026-04-17; diverge ~2040).
