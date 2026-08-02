# Header integrity field — byte-doubled option floor + data-frame CRC-16 (decode-or-refuse)

Device-general (die `cycloneive1`, EP4CE6 == EP4CE10). Code: `scripts/header_field.py`
(standalone; no Quartus device files needed). Result: `results/header_integrity_decomp.json`.
Provenance: transcribed from an EP4CE6/EP4CE10 device-file + live-trace RE campaign;
the validation image is referred to as `<target>.rbf`.

This documents the config-image header region the fork currently treats as an opaque
"no CRC" band (frames 0..24) and pins the two — and only two — integrity engines that
run over the whole 368011-byte image. It lets the project emit a **valid whole-image
header**, not just per-frame data CRCs.

## What

The image is `PREAMBLE(32) + SYNC + 1752 frames of stride 210` (208 payload bytes +
a 2-byte trailing field at offset 208..209) + a 59-byte `0xFF` postamble.

1. **Data frames (F ≥ 25):** the trailing 2 bytes are a **reflected CRC-16 over the
   frame's 208 payload bytes** — engine `PGM_COMMON::calculate_crc16` (reflected poly
   `0xA001`), selected by the dispatcher `PGMIO_F2P::calculate_crc` @`0x36eb00`. The
   dispatcher hands crc16 init `0xFFFF` over a constant 2-byte header prefix (`0xCCE8`)
   ahead of the payload; that is identical to an **effective init `0xFE54`** applied
   directly over the 208 payload bytes. Little-endian: low byte → [208], high → [209].
   `header_field.emit_frame_crcs` is the closed-form generator; `crc16_frame` the engine.

2. **Header frames (F 0..24):** the trailing 2 bytes are **not a payload checksum**.
   They are an 8-bit configuration/header-structure field, **byte-doubled** into bytes
   208 AND 209 (`byte[209] == byte[208]`, a duplication law). The set-bit census is
   **53 logical set-bits × 2 stored copies = 106** — the "106-bit header integrity
   floor". Decomposition:
   - **Duplication law** (general): the high copy is DERIVED unconditionally from the
     low copy.
   - **22 of 25 frames**: the low byte is a per-frame **GF(2)-affine** function of that
     frame's own 208-byte payload (`field_F = M_F · payload_F ⊕ c_F`) — option bits
     linearly encoded; a general derived function of the payload for any design.
   - **3 frames (F3, F5, F9)**: `field_F = affine(payload_F) ⊕ (opt_M9K ? δ_F : 0)`
     with δ = {F3:`0x04`, F5:`0x40`, F9:`0x10`}. `opt_M9K` is a **non-payload design
     input** (an option-register M9K-memory-block-usage flag) — see honest limits.

3. **32-bit whole-configuration SEU CRC:** **ABSENT** from this passive-serial image;
   `header_field.seu_crc_status` verifies the postamble is 59 × `0xFF` and reports the
   SEU field as **LOCATED but not CLOSED** — it is not one of the 106 floor bits.

## Why device-general

The frame geometry, the two engine parameterisations, and the duplication + affine
structure are properties of the die and the Quartus programming binary, not of any
design. The engine parameters are read straight out of the vendor code (cited function
addresses); the duplication law and the 22 affine maps are proven across a 471-design
same-die corpus. The data-frame CRC-16 generator is closed-form and needs no tables.

## How validated

- **Data-frame CRC-16: 1727/1727 bit-exact** (all F ≥ 25). Device constant: an
  all-zero frame returns `0x7D9A` = `crc16(zeros₂₀₈, 0xFE54)`, observed verbatim in the
  live trace and asserted in `header_field.py`'s self-test. The dispatcher-init and
  effective-init forms reconcile exactly through the `0xCCE8` prefix.
- **`calculate_crc8` refuted as dead code by live gdb trace.** `PGMIO_F2P::calculate_crc8`
  @`0x36e8d0` (a reflected poly-`0x88` CRC-8) exists in `libpgm_pgmio.so` but is **never
  called**: a full intercept of `quartus_cpf` (sof→rbf) counted **3470 dispatches, all
  crc_type=0 (crc16 branch), 0 crc8 calls**; a full `quartus_asm` run made **0 CRC calls
  of any kind** yet emitted a valid image. So the header field is carried as option data,
  computed by no checksum routine. Data-side confirmation: the header field matches a
  crc16 low/high byte in only 1/25 frames (coincidental at a 1-set-bit field), and crc8
  over the payload fails for essentially every frame.
- **Duplication law: 471/471 designs, 0 mismatch.**
- **22 affine frames: proven held-out on 471 designs**, bit-exact wherever the corpus
  exercises the input direction. Leave-`<target>`-out closure reproduces all 25 header
  fields → all 106 physical bits of the validation image DERIVED bit-exact.

## Honest limits (stated, not bluffed)

- **F3/F5/F9 are design-input-bound and REFUSED for foreign designs.** Their extra
  field bit is set only when the design instantiates an M9K memory block — a design
  feature outside the frame payload (a correlation search over all 25×1664
  header-payload bits found no bit set in exactly the residual-carrying designs). It is
  therefore not a polynomial term and is correctly **EXPLICIT_UNKNOWN** for a foreign
  design. For the validation image `opt_M9K = 0` in these frames, so the affine map
  predicts them exactly (DERIVED). `header_field.refused_general_frames()` enumerates
  them.
- **The general per-frame affine maps are not shipped.** They are recovered from the
  design corpus; `header_field.py` reads the field values decode-or-refuse and does not
  synthesise them for a foreign design.
- **The 32-bit whole-config SEU CRC was located, not closed.** It is absent from this
  passive-serial image (error detection disabled); the module reports it, never invents
  it.

Net: the two general, closed-form engines (data-frame CRC-16 + header duplication law)
are emit-ready; the design-input-bound header bits are declared and refused.
