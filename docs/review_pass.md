# README editorial pass — 2026-04-15/16

Archive of the editorial rationale for the 13-point critique that led to
this pass over `README.md` and `README_zh.md`. Written so that half a
year from now the motivation is still recoverable, and so that anyone
who disagrees with a specific call can see what was being traded off.

The peer LLM raised 13 items. Some were factual errors (objectively
wrong), some were structural tics (rhetoric that felt good at the time
but did not survive a cold read), and some were missing pieces (content
the README should have had but didn't). We accepted most, rejected two
nuances, and added two sections not on the list.

---

## #1 — Mirror rhetoric in "Long-term direction"

**Critique:** "Where we will win / where we will lose" as parallel
headers reads as a move that has been practised, not a conclusion being
reported. The binary framing flattens what is really a three-layer
answer.

**Accepted.** Replaced with three named layers: *PPA is out of reach*,
*What the codec uniquely enables*, *Where ML fits*, then *Priority*.
Each answers a different question. Removed the closing blockquote "one
sentence summary" — if the three layers work, the summary is redundant;
if they don't, the summary is just sloganeering.

**Why this matters.** The "win / lose" framing implicitly positions the
project against Quartus. The codec's value is not about winning; it is
about doing things Quartus structurally cannot. Saying that directly is
more useful than saying it in the shape of a rhetorical reveal.

## #2 — TL;DR blockquote at the end

**Critique:** The closing blockquote ("we are not building a smarter
Quartus…") is the thing the LLM-written prose most obviously *wants* to
end on. A tell.

**Accepted.** Removed. The three layers above it say the same thing
without asking the reader to clap.

## #3 — License rationale is factually wrong

**Critique:** GPL attaches to code as software; CC BY-SA attaches to
prose as a written work. Neither of them binds the **methodology** (the
reverse-engineering techniques, CRAM formulas, bit offsets, jailbreak
result). Those are facts, and copyright does not fence off facts. So
the old rationale — "GPLv3 + CC BY-SA forces every downstream to stay
on the same open table" — overstates what the licenses actually do.

**Accepted.** Rewrote the License section to:

1. State scope cleanly (code → GPL, prose → CC BY-SA) without implying
   the licenses bind methodology.
2. Acknowledge that methodology is facts, and explain that we chose
   copyleft anyway because it keeps the reference implementation and
   the written record open — which is the part downstream users
   actually depend on.
3. Point at defensive publication (cite the repo + `FINDINGS.md`
   entry) as the honest answer for anyone who wants methodology tied
   to a durable claim.

Killed the two "choice is deliberate" paragraphs at the bottom —
they were restating the same point twice in different emotional
registers.

**Why this matters.** The whole section used to read like a manifesto.
Licensing is a boring technical topic that should be explained
accurately. If a reader ever needs to cite this rationale in a dispute,
the earlier version would not have held up.

## #4 — "RL routers have not beaten VPR as of 2024"

**Critique:** Dated-sounding empirical claim inside a long-term-vision
section. Will rot fast. Also not strictly true as an unqualified
statement.

**Accepted.** Softened to "whether academic RL routers can close the
gap remains an open research problem." Keeps the correct conclusion
(don't try to out-route Quartus) without betting the sentence on a
specific benchmark year.

## #5 — "Partial reconfiguration on Cyclone IV"

**Critique:** Cyclone IV has no ICAP. What we have is offline bitstream
modification and re-flashing on the next power cycle. That is not PR in
any vendor-recognised sense.

**Accepted.** Replaced with:

> Offline bitstream mutation and replay: modify specific frames in a
> known-good RBF and re-flash on next power cycle. This is *not*
> partial reconfiguration (Cyclone IV lacks ICAP), but it enables
> things Quartus's single-shot flow rules out — applying ECO patches
> without re-running fit, reproducible bit-identical builds (Quartus
> is seed-dependent; the codec is a pure function), and bitstream
> watermarking in don't-care LUT bits.

Honest about the capability, names the real primitives it enables, does
not reach for vendor terminology that doesn't fit.

## #6 — PUF / hardware fingerprinting bullet

**Critique:** PUF requires a silicon-physical measurement (timing
variation, Vdd noise, ring-oscillator frequency). A bitstream codec
does not expose any of that. Listing PUF under "what this enables" is a
buzzword reach.

**Accepted.** Removed the PUF / single-chip overfit bullet entirely.
Kept watermarking (which *is* within codec scope: hide an ID in
don't-care LUT bits is a real, demonstrable capability).

## #7 — Pioneer Projects table

**Critique:** The old "relationship to this project" column was vague
("方法论完全相同" / "FASM 格式可参考"). The projects deserve a
substantive "what they actually contributed" column so a reader can
decide what's worth digging into.

**Accepted.** Rewrote to two columns:

- **Core Contribution** — the thing that project is historically known
  for. IceStorm = full open pipeline + fuzzing methodology; X-Ray =
  defined FASM; Mistral = derived RBM from `quartus_cdb` + Tcl;
  Trellis = routing-bit decomposition + nextpnr-ecp5 integration.
- **Relationship to this project** — what specifically we borrowed or
  inherited from them.

Makes the references load-bearing instead of aesthetic.

## #8 — "What Is an FPGA?" paragraph

**Critique:** Three paragraphs explaining FPGAs to readers who picked
up a reverse-engineering repo is the wrong audience. Readers who need
the definition can follow one link; everyone else skips those
paragraphs.

**Accepted.** Shrunk to one line + a handbook link. Respects reader
time, and correctly scopes the README to people who already know what
an FPGA is.

## #9 — "First time Cyclone IV enters the OSS ecosystem"

**Critique:** Cyclone V has been partially open via Project Mistral
for years. Claiming to be the first Cyclone IV work in the OSS
ecosystem is fine, but claiming to be the first Cyclone at all would
be wrong.

**Accepted.** Narrowed to "the first time the **Cyclone IV E family**
enters the open-source FPGA ecosystem (Project Mistral brought Cyclone
V partway there before us)." Credit where due, narrower scope, still
accurate.

## #10 — Progress Estimate table

**Critique:** Percentages like "~85%" across rows whose denominators
are totally different (bits, wire types, routes, whole designs) is a
fiction. Summing mental arithmetic across the column does not produce
a meaningful number. A column that looks quantitative but isn't is
worse than no column.

**Accepted.** Reformatted to **Coverage / Status**:

- *Coverage* — what is concretely counted (e.g., "25/37 I-indices
  mapped", "44/44 single-axis bit-perfect", "13,487 entries").
- *Status* — a small vocabulary: HW-verified / Round-trip clean /
  Partial / Not started / Closed / Production.

Added a preamble explicitly saying the percentages were not
comparable. Reordered so HW-verified rows appear together at the top
— it is the most useful cut for a reader trying to trust what's real.

## #11 — Superoptimizer phrasing

**Critique:** "Superoptimizer" is a loaded term. What the codec
actually enables is a mutation-and-equivalence framework — the
expected cell-level PPA wins from post-fit peepholing are small, and
the real value is the research substrate.

**Accepted.** Softened to "bitstream-level mutation and equivalence
framework", and explicitly marked the expected PPA gains as small.
Honest framing beats a punchier wrong one.

## #12 — Missing "Dead Ends" section

**Critique:** The README tracks successes in loving detail but has no
place where failed hypotheses are collected. Readers who want to learn
from the project's mistakes have to reconstruct them from the memory
system. That's the wrong default.

**Accepted and added.** New section *Dead Ends Worth Remembering*
before the License, with six entries:

- M5 counter (carry-chain detour; lesson: flash Quartus's RBF
  first and diff before patching codec)
- IOB cross-axis linear superposition + bank-pair lookup (both
  falsified; needs full 2D sweep)
- R4 dark passive mining (RBF too dense; S/N below mining floor)
- T9 LI paired-vs-alternating as a function of the routing key
  (falsified; missing variable is elsewhere)
- DFF per-LE CRAM enable bit (does not exist — FF is silicon default)
- Self-loop sig-cache via two-LUT pair template (template cannot
  represent `src == dst`; Quartus refits between compiles)

Each entry names the memory file where the full post-mortem lives.

## #13 — Missing "Limitations / Not a Quartus replacement" section

**Critique:** Readers need a single place that says cleanly what the
project does **not** cover. Individual caveats are scattered across the
phase write-ups and the progress table.

**Accepted and added.** New section *Limitations and What This Is Not*
before the License, covering:

- C16 untouched
- Non-E-series Cyclone IV parts unvalidated
- Large designs (NEORV32) not end-to-end flashed
- Temperature / voltage corners uncharacterised
- M9K BRAM in open flow not HW-validated (blocked on Yosys
  `memory_libmap`)
- PLLs out of scope (off-fabric, not in mapped CRAM region)
- Not a Quartus replacement (no timing-driven P&R)

---

## Mirroring to Chinese

Every edit landed on `README.md` was mirrored to `README_zh.md` in the
same pass. Chinese prose was rewritten, not machine-translated — the
tone difference was the whole point of the critique (the Chinese side
had its own mirror-rhetoric habits that machine translation would just
echo). Dead Ends and Limitations were written from scratch in Chinese,
not translated from the English.

## What was rejected

Two things we kept after considering:

- **Keeping the peer-LLM-critique `FINDINGS.md` genre separate from
  `README.md`.** The README is the project overview; `FINDINGS.md`
  and memory files are the working archive. Dead Ends went into the
  README because the README should carry enough failure signal to be
  honestly readable, but full per-incident post-mortems stay in memory
  where they live now.
- **The CE6→CE10 jailbreak narrative in the Phase write-ups.** That
  material is genuinely load-bearing evidence, not rhetoric — it is
  what changed the project's stakes and the license choice. Critique
  did not touch it and we didn't either.
