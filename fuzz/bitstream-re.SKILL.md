---
name: bitstream-re
description: Black-box reverse engineering of FPGA configuration bitstreams (Altera Cyclone IV proven; method generalizes). Use when the user wants to map CRAM bits, build a codec, jailbreak a fitter whitelist, or hardware-verify a codec-generated bitstream on real silicon.
---

# FPGA Bitstream Reverse Engineering — Playbook

Distilled from the EP4CE6 project (6,272→10,320 LE jailbreak, 58/58 bit-perfect route synthesis, HW-verified on AX301). Every step in here has been silicon-validated at least once; don't skip the verification steps just because the math looks clean.

## Core principles

1. **Pair-diff beats absolute analysis.** Compile two designs that differ in exactly one thing (one LUT mask bit, one placement, one routing port) and XOR the RBFs. The diff isolates the bits you care about from the vendor's routing noise. Never try to parse an RBF from first principles when a diff will do.
2. **Trust silicon, not datasheets.** Pin maps, LAB grids, "non-LAB" column lists, and device LE counts in vendor docs are frequently wrong or intentionally misleading. Verify with a hardware probe before you build a model on top of them.
3. **The vendor's fitter is a whitelist, not a hardware lock.** If the same package ships as multiple SKUs, the cheaper SKU almost always has all of the expensive SKU's silicon, disabled only in the fitter. This is testable in minutes (see "Jailbreak probe").
4. **Codec round-trip ≠ hardware safety.** A codec that reads a cell and writes it back faithfully can still produce a bitstream that shorts a MUX on real silicon. Maintain a separate `validate_safe_for_hardware()` that classifies every touched structure against known-safe Quartus envelopes, and run it before every flash.
5. **Negative results are deliverables.** If a feature isn't in the input space (we spent two rounds proving the paired/alternating LI mode isn't a function of the routing key), document it and stop — don't quietly keep mining.

## Stage 1 — Infrastructure (build once, reuse forever)

- **Headless compile driver**. Shell out to the vendor's CLI (`quartus_map` → `quartus_fit` → `quartus_asm` → `quartus_cpf` for Altera). Parse the fit report for errors, clean the work dir between runs. ~4s per compile on Cyclone IV Lite.
- **Binary diff engine**. Byte-level diff of two RBFs of the same size, emit a list of (offset, old_byte, new_byte) tuples. Store in SQLite keyed on design metadata.
- **Parameterized Verilog generator**. Emit placements via `set_location_assignment` in QSF, primitives via `cycloneive_lcell_comb` (or the vendor's equivalent low-level cell). **Do not rely on behavioral synthesis** — it will optimize away your probe. Use `(* keep = 1, preserve = 1 *)` plus primitive instantiation.
- **Known-good baseline**. Compile an empty / minimal design once per (family, device, source-location). All diffs are against this `zero.rbf`. Cache it — it never changes as long as the placement anchor is stable.

## Stage 2 — CRAM geometry (find the grid)

Goal: given a cell at logical `(X, Y, N, feature)`, compute its byte offset and bit position.

1. **Pick a feature that's easy to toggle from Verilog** (LUT truth table is ideal — 16 bits of direct user control via `lut_mask`).
2. **Pair-diff a single bit**. Compile `lut_mask=0x0000` vs `lut_mask=0x8000`. The diff tells you where minterm 15 lives.
3. **Sweep the feature**. Do all 16 minterms. XOR-linearity emerges: any mask is the XOR of its single-bit patterns.
4. **Sweep X, then Y, then N**. Look for invariant strides. Cyclone IV gave us: 7,350 bytes per LAB column, 210 bytes per Y pair, 48 bytes ctrl→data, slot/group encoding via `(Y-2)%3` and `(Y-2)//3`.
5. **Cross-validate** at least one cell per column. If step 4's formula misses, you haven't found the right stride — go back to pair-diffing more X values.
6. **Edge columns matter**. Left-edge (X<8) and right-edge columns often use different base addresses; build a `COLUMN_BASE[x]` lookup table instead of assuming a uniform stride.

## Stage 3 — Routing matrix (the hard part)

Routing wires are named by the vendor's STA tool. For Cyclone IV:
- Extract with `report_timing -show_routing` in a TCL script
- Wire names look like `C4_X{x}_Y{y}_N{n}_I{i}`, `R4_...`, `LOCAL_INTERCONNECT_...`
- Store every (src, dst, wire path) triple in SQLite as your routing corpus

For each wire type:
1. **Collect multiple routes that share the wire** — mine SQLite for every path using `C4_X10_Y10_N0_I0`, for example
2. **Pair-diff two routes that differ only in that wire's presence**. The common bits = the wire's CRAM cells
3. **Baseline-diff mapper**: for a candidate (X, I) combo, find which (byte, bit) positions are uniquely correlated with Y across the corpus. This is how the 44 C4 I≠0 mappings and 18 R4 I-index models were found.
4. **Expect per-wire-type address styles**: C4/R4 have slot/group/group-indexed formulas; R24 has fixed per-wire bytes (no Y offset); LOCAL_INTERCONNECT lives in the *self* column not the prev column. Don't assume uniformity.

## Stage 4 — Codec + safety envelope

- **RouteCodec.apply_switch(rbf, wire_name, state)** — writes one wire on/off using the Stage 3 models
- **LutCodec.write_tt(rbf, mask)** — writes a LUT truth table. **XOR-delta semantics**: if your base already has bits set, compensate with `mask = target ^ base_tt`. This is a real footgun.
- **validate_safe_for_hardware(rbf, zero)** — classifies every touched LAB's local-interconnect pair pattern against the known-safe envelopes observed from real Quartus output. Raises on anything unknown. Must run before every flash.
- **Round-trip test** — read a Quartus RBF, replay every switch, re-read, compare. Zero dropped/hallucinated cells is table stakes.

## Stage 5 — Bitstream finalization

The vendor almost certainly CRC-checks the configuration memory per frame. Check for frame CRC before flashing any codec-modified RBF or the FPGA will reject the load. Cyclone IV uses CRC-16/IBM (poly 0x8005, init 0xFE54, per-210-byte frame, frames 25..1751).

- Locate the CRC: flip one data bit in a known frame, flash, observe failure; then brute-force the algorithm over standard CRC-16 variants (~15 candidates) against known-good Quartus output.
- Implement a `patch_rbf_crc()` that recomputes all frame CRCs after codec writes.
- Mask CRC bytes in your `read_switches()` diff or they'll pollute the routing signal.

## Stage 6 — Hardware verification (mandatory, not optional)

Every model, codec change, or bit discovery must be validated end-to-end on silicon before you trust it:

1. Build a minimal Verilog that exercises the feature (e.g. `LED = LUT(K1,K2,K3,K4)` with a known truth table)
2. Compile with Quartus → get `quartus_rbf`
3. Run your codec to reproduce the same bitstream → get `codec_rbf`
4. Diff: `quartus_rbf` vs `codec_rbf` should be zero in CRAM, differ only in CRC (which `patch_rbf_crc` then fixes)
5. Flash `codec_rbf` with `openFPGALoader -c usb-blaster` (or vendor equivalent)
6. Press keys, observe LED, match against expected truth table

If step 4 fails, your Stage 3/4 model is wrong. If step 6 fails but step 4 passed, your safety envelope is wrong (you wrote a physically unsafe bitstream) — do NOT retry, diagnose first.

## Stage 7 — Jailbreak probe (when you suspect SKU rebinning)

If the same die ships as multiple SKUs in the same package, test whether the smaller SKU is just a software whitelist:

1. **Byte-compare baseline RBFs** across SKUs. Same Verilog, same pin constraints, different `DEVICE=`. If the RBFs are byte-identical → same physical die, pure fitter whitelist.
2. **Coordinate legality probe**. For each (X, Y) your small SKU claims doesn't exist, write a tiny `jb.qsf` with `DEVICE = <big SKU>` and `set_location_assignment LCCOMB_X{x}_Y{y}_N0 -to "q"`, run `quartus_fit`, grep for "illegal location assignment" vs "Fitter was successful". Minutes per probe.
3. **Block-column identity**. Instantiate many `altsyncram` (M9K hint) + `lpm_mult` instances with `VIRTUAL_PIN` on all ports; let the fitter natural-place them; read `M9K_X*_Y*` / `DSPMULT_X*_Y*` placements from the fit report. That tells you which columns are RAM vs multiplier vs true non-fabric.
4. **Dead-cell scan via XOR chain**. Before trusting any newly-discovered LE, prove it's physically alive:

   ```verilog
   chain[0] = K1 ^ K2;
   for each forbidden LE i:
       (* keep, preserve *) wire w_i;
       cycloneive_lcell_comb #(.lut_mask(16'hAAAA)) u_i (
           .dataa(chain[i]), .datab(0), .datac(0), .datad(0),
           .cin(0), .combout(w_i));
       assign chain[i+1] = w_i;
   LED = chain[N];
   ```

   Lock every `u_i` to its target `LCCOMB_X{x}_Y{y}_N{n}` in QSF. Healthy chain → `LED = K1^K2`. Any stuck-at, broken LUT, or dead routing breaks parity on at least one of the four key combinations. One bitstream validates up to ~1,800 cells in a single flash; bisect on failure.

5. **Do NOT auto-enable the extended fabric in your codec** until you've done Stage 3 for at least one new column and run a green-zone regression on a source in the jailbroken region. The model might hold, but "probably" isn't good enough for something that flashes to real silicon.

## When to stop

Chase a signal if a decision tree can pick it up at >70% from a balanced corpus. Drop it if two rounds of corpus expansion leave the middle leaf at ~50%: the signal probably isn't in the input space at all (it's in the vendor's placement seed or internal cost-function ties you can't observe). Mark it NEGATIVE in the project log and move on. Don't sink compute into un-mineable phenomena.

## Common footguns

- **XOR-delta codec** mistaken for absolute: if `base` has bits set, compensate `mask = target ^ base_tt`.
- **Quartus optimizes away trivial probes** (`assign led = ~key` becomes a direct pin-to-pin wire, 0 LCELLs). Always use primitive cells + `(* keep, preserve *)`.
- **Vendor pin labels are wrong**. The board we probed had "RESET" labeled on what turned out to be KEY1. Hardware-probe every pin you depend on.
- **Background shells self-deadlock** if you write `while pgrep -f quartus; do sleep; done` and the waiter itself matches `quartus` in its command line. Use a more specific pattern or a PID file.
- **CRC isn't optional** on most modern FPGAs. If your codec RBF doesn't load but diffs clean against Quartus, it's almost certainly CRC.
- **Non-LAB columns have different CRAM widths**. Don't apply your LAB stride model to M9K/DSP columns — they're a different format.

## Reference constants (EP4CE6 / Cyclone IV E, silicon-verified)

Keep these in your project's `config.py` / `CLAUDE.md` but treat them as the CE6 *whitelist*, not ground truth:

```
LAB column step:  7,350 bytes
Pair spacing:     210 bytes
Ctrl→Data:        48 bytes
Y encoding:       slot = (Y-2)%3, group = (Y-2)//3
Frame CRC:        CRC-16/IBM poly 0x8005, init 0xFE54, reflected
Frame layout:     1752 × 210 bytes from byte 32, frames 25..1751 CRC-enforced
True LAB_X:       [3..33] minus {15,20,27}  (28 cols, not the 22 CE6 advertises)
True LAB_Y:       [2..21]                   (20 rows, not 19 — Y=15 is real)
True non-LAB:     X ∈ {15, 27} = M9K, X = 20 = embedded multiplier
```
