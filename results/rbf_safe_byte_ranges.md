# EP4CE6 RBF — Safe Byte Ranges (Deliverable 4 for rot_tpu_handoff mode H)

**Status**: Promoted from `results/FINDINGS.md` + `fuzz/bitstream.py` constants. Verified against Quartus Lite 21.1 builds. Cross-version drift vs Quartus 13.0sp1 **not yet measured** — see Caveats.

**Schema version**: 1
**Generated**: 2026-05-21 (consumer side: 14sea, mode H Plan C-1 v5)

---

## 1. RBF file layout

Total size **368,011 bytes**, fixed.

| Region | Byte range (half-open) | Length | Content | Editable by mode H? |
|---|---|---|---|---|
| Preamble | `[0, 32)` | 32 | All `0xFF` | **No** — must not touch |
| Header frames 0..24 | `[32, 5282)` | 5,250 (25 × 210) | Device config, GCLK pins, IOB infra, per-build variable bytes | **No** for LUT mode H. CRC bytes at frame offsets 208/209 exist but are not validated by the config controller for these frames |
| CRAM frames 25..1751 | `[5282, 367952)` | 362,670 (1,727 × 210) | LAB CRAM (LUT, routing, FF control) + per-frame CRC | **Yes** — XOR-edit + CRC repair |
| Postamble | `[367952, 368011)` | 59 | All `0xFF` | **No** — must not touch |

Math: `32 + 1752 × 210 + 59 = 368011` ✓
Source: `fuzz/bitstream.py:213-225`.

## 2. Per-frame layout

Every frame is 210 bytes:

| Within-frame offset | Length | Content |
|---|---|---|
| `[0, 208)` | 208 | Data (CRAM cells, ctrl/data interleaved per `results/FINDINGS.md` §"Y-Address Formula") |
| `208` | 1 | CRC-16 low byte (LSB) |
| `209` | 1 | CRC-16 high byte (MSB) |

CRC spec: reflected CRC-16-IBM, poly `0x8005` (right-shift form `0xA001`), init `0xFE54`. CRC is computed over the 208 data bytes; only frames 25..1751 are checked at load time. `fuzz/bitstream.crc16_rbf_frame()` is the reference C-portable implementation.

**Pitfall #11 (CRC byte detection)**: Use `(absolute_offset - 32) % 210 >= 208` to test whether an absolute file offset is a CRC byte. Do **not** use `offset % 210`.

## 3. Header-band per-build variable bytes

These bytes vary across Quartus builds even for byte-identical Verilog (resource-usage encoding + design-CRC). Mode H must exclude them when verifying byte-identity vs a golden RBF.

| Byte range (absolute) | Length | Content |
|---|---|---|
| `[0x29, 0x35)` | 12 | Design-dependent (likely resource usage encoding) |
| `[0x49, 0x4B)` | 2 | Design-level CRC/checksum (changes with every design modification) |

All other header bytes (including `[0x20, 0x29)` device header and `[0x35, 0x49)`) are stable across builds of byte-identical Verilog under the **same Quartus version**.

## 4. Python helper

```python
"""Safe-byte-range helper for mode H. Pure data, no deps."""

RBF_TOTAL_BYTES        = 368_011
RBF_PREAMBLE_BYTES     = 32
RBF_POSTAMBLE_BYTES    = 59
RBF_FRAME_SIZE         = 210
RBF_FRAME_DATA_BYTES   = 208
RBF_HEADER_FRAMES      = 25       # frames 0..24, not CRC-validated
RBF_FIRST_CRAM_FRAME   = 25
RBF_LAST_CRAM_FRAME    = 1751
RBF_CRC_INIT           = 0xFE54
RBF_CRC_POLY_REFLECTED = 0xA001   # reflected CRC-16-IBM (poly 0x8005)

# Per-build variable bytes inside the header (absolute file offsets).
RBF_PER_BUILD_VARIABLE_RANGES = ((0x29, 0x35), (0x49, 0x4B))


def mode_h_safe_edit_range():
    """Return (lo, hi) — mode H may only XOR-edit absolute file bytes in [lo, hi).

    Bytes outside this range either are constants the config controller
    expects (preamble/postamble) or are header frames whose semantics are
    not currently modeled for safe LUT XOR-editing.
    """
    lo = RBF_PREAMBLE_BYTES + RBF_HEADER_FRAMES * RBF_FRAME_SIZE   # 5282
    hi = lo + (RBF_LAST_CRAM_FRAME - RBF_FIRST_CRAM_FRAME + 1) * RBF_FRAME_SIZE  # 367952
    return lo, hi


def is_crc_byte(abs_off: int) -> bool:
    """True iff abs_off lies on a per-frame CRC byte (208 or 209 within-frame)."""
    if abs_off < RBF_PREAMBLE_BYTES:
        return False
    if abs_off >= RBF_PREAMBLE_BYTES + (RBF_LAST_CRAM_FRAME + 1) * RBF_FRAME_SIZE:
        return False
    return (abs_off - RBF_PREAMBLE_BYTES) % RBF_FRAME_SIZE >= RBF_FRAME_DATA_BYTES


def in_per_build_variable_range(abs_off: int) -> bool:
    """True iff abs_off is in the design-dependent header band (exclude from byte-identity asserts)."""
    return any(lo <= abs_off < hi for lo, hi in RBF_PER_BUILD_VARIABLE_RANGES)


# Self-check expected values (handy for unit tests):
#   mode_h_safe_edit_range() == (5282, 367952)
#   is_crc_byte(5282 + 208)  is True
#   is_crc_byte(5282)        is False
#   in_per_build_variable_range(0x30) is True
#   in_per_build_variable_range(0x40) is False
```

## 5. Suggested mode H asserts

Three asserts the consumer wants to plant in `mode_fabric_surgery`:

1. **All dirty-bitmap bits fall within the editable range.**
   ```c
   for each dirty byte d_off:
       assert(d_off >= 5282 && d_off < 367952);
   ```

2. **No edit's `lc.base_addr + pair*210 + delta` touches preamble/header/postamble.**
   Equivalent to assert (1) applied to every minterm address derived from `lc`.

3. **Readback verify: preamble + postamble bytes identical to pre-edit input.**
   ```c
   assert(memcmp(post[0:32],          pre[0:32],          32) == 0);
   assert(memcmp(post[367952:368011], pre[367952:368011], 59) == 0);
   ```

(Header band `[32, 5282)` is **also** expected to be byte-identical in mode H since mode H never edits there — the consumer can add a 4th assert covering `[32, 5282)` if they want a stricter guarantee.)

## 6. Caveats

- **Cross-version drift unmeasured**: All numbers verified against Quartus Lite 21.1 outputs (the EP4CE6 repo's primary build environment). Quartus 13.0sp1 builds may shift `[0x29, 0x35)` and `[0x49, 0x4B)` content but the structural offsets (preamble = 32, frame size = 210, postamble = 59, CRC poly/init) are device-format constants and will not differ. **Recommendation**: keep host-side and target-side on the same Quartus version when verifying byte-identity (matches Q1 in the original target doc).
- **Header frames 0..24 carry GCLK/IOB infra**: Some legitimate edits land there (e.g., `GCLK_PIN`, `IOB_BASELINE_NV`, `LAB_CLK_SEL`). Mode H scope is LUT-only, so the editable range above excludes them deliberately. If mode H scope ever widens to clocks/IO, this doc needs an update.
- **Per-frame CRC repair is mandatory** for any edit in `[5282, 367952)`. The C port `lc_patch_rbf_crc_frames` (consumer side) is the reference implementation; `fuzz/bitstream.patch_rbf_crc()` is the Python ground truth.

## 7. References

- `fuzz/bitstream.py:213-251` — Python ground truth for CRC constants + per-frame repair.
- `results/FINDINGS.md` §"RBF Format", §"Global Header Region" — original write-up.
- `CLAUDE.md` Pitfall #11 — CRC-byte detection offset formula.
- `~/.claude/projects/-home-test-EP4CE6/memory/preamble_offset_bug.md` — incident memo.
