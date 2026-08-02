# Compiler-model-extraction method (harvest → invert → decode-or-refuse)

**What it is.** A general technique for building bit-exact CRAM codecs for a
Cyclone IV E family part *without* re-deriving the opaque enum-keyed device
file (`.ddb`) and *without* pair-diff fuzzing. Instead of guessing the encoding,
you let Quartus resolve it and read the answer out of the assembler's own memory.

**Why device-general.** The tables harvested are the assembler's *resolved
device model* — `{block / mux / setting / codeword → DB_BIT_SETTING flat-CRAM
bits}` — which is a property of the silicon device file, not of any one design.
The same `quartus_asm` binary and the same `cycloneive1` die database serve every
EP4CE6/EP4CE10 design, so the harvested setting↔bit tables hold for any target on
that die. Nothing here is specific to a particular bitstream.

## The four steps

1. **Harvest.** `quartus_asm`'s ASMDB reader parses the device file and
   materializes the complete setting↔bit tables in RAM (every enum, mux, IOE
   codeword, config bit already resolved). Break on the emit boundary
   (`ASM_BITFIELD::set_bits`, `libcomp_asmcc.so`, and the per-class
   `get_bits_*` resolvers) with a read-only gdb intercept and log every
   `{setting, codeword → DB_BIT_SETTING bits}` the compiler emits, over a small
   set of carrier compiles that walk the codewords of each block/mux.

2. **Invert.** Turn the forward table `{codeword → bits}` into a decode table
   `{observed bits → codeword → named meaning}`. The inversion is *exact*, not
   fuzzed, because within one setting/codeword the compiler's emit-order value
   tuple over its cell set is identical across every independent compile, and the
   per-mux signatures are provably unique (no two codewords of a mux share a
   signature, and no codeword has an all-zero signature) — so an unused (all-zero)
   or unobserved read naturally **refuses** rather than mislabels.

3. **Validate.** Confirm each codec reproduces its oracle bit-exact, then confirm
   it decodes **held-out fresh compiles** (seeds/designs never in the harvest)
   back to the intent the fitter chose, with zero mispredictions and zero
   ambiguous refusals. Per-codec held-out results (all clean):
   - `codec_le-lab-secondary` — leave-one-compile-out over 8 independent compiles.
   - `codec_ioe-reg-and-inputmux` — 2 fresh seeds; the blockty6 input range was
     independently re-probed to its true 18-input extent (sel16/17 held-out
     round-trip bit-exact).
   - `codec_pll-m9k-clock` — 5 fresh PLL carriers (varying multiply / duty /
     phase); identical CLKOUT-select and clock block-mux signature every time.

4. **Integrate, decode-or-refuse.** Wire each inverted codec behind the unified
   decoder (`decode_rbf.py`) with its own safe-reject. A codec claims cells only
   for a setting whose full recorded signature is present bit-for-bit in the
   target image; any mismatch, non-unique match, or unmappable bit → REFUSED.

## Honest scope of what is readable from a `.rbf`

Harvesting reveals *which plane* each resolved setting lands in. Only settings
whose config field lies in the main-CRAM plane (flat bit31 == 0) are serialized
into the frame data and therefore decodable from a shipped `.rbf`. Settings that
the fitter commits to the aux/CFF serializer planes (flat bit31 set, tag
`0xA…`/`0x9…`/`0x88…`) — e.g. the design-varying PLL numeric config
(charge-pump / loop-filter / VCO / per-counter multiply / duty / phase) — are
**not** in the frame CRAM and are refused wholesale, not bluffed. This is a real
open gap (the CFF offset→rbf permutation, see `cff_serialization.md`), not a
codec weakness: the encoding tables are exact and decode the moment their plane
becomes readable.

## Relation to this repo's pair-diff method

Pair-diff and model-extraction are complementary. Pair-diff proves a bit's
*location* from two real bitstreams; model-extraction proves the *whole encoding
table* (every codeword, every named field) from the compiler's own resolution.
Where both cover a feature they agree bit-exact (see `lut_codec_validation.md`,
where the model-extracted LUT geometry matches the golden pair-diff sweep 42/42).
Model-extraction supersedes re-deriving the enum format for the config classes;
pair-diff remains the ground-truth cross-check and the route/CRAM discovery path.
