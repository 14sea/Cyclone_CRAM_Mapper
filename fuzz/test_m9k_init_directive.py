# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the M9K.INIT FASM directive.

The `X{x}Y{y}N{n}.INIT_{width}x{depth} = 0x{hex}` line loads the M9K
initialization words for a calibrated block.  The codec itself
(`fuzz/m9k_init_basis.py`) is validated in its own module; these tests
cover the FASM-level parse and bitgen wiring:

  1. Parser extracts (x, y, n, width, depth, words) correctly.
  2. End-to-end bitgen round-trip: FASM -> RBF -> `read_init` -> words,
     parametrized across multiple calibrated anchors.
  3. XOR idempotence: applying the same INIT line twice returns to base.
  4. Unknown site raises FasmError.
  5. Hex length mismatch (short and long) raises FasmError.

Runs standalone via `python3 fuzz/test_m9k_init_directive.py`.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import fasm2rbf as f
from m9k_init_basis import M9K_INIT_ANCHORS, read_init


NV_ZERO = ROOT / "results" / "rbf" / "nv_zero_global.rbf"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _words_to_hex(words, width, depth):
    """Pack `depth` `width`-bit words into a hex string matching
    the parser's `blob_int >> (i*width)` convention: word 0 occupies
    the least-significant `width` bits of the integer."""
    total_bits = width * depth
    mask = (1 << width) - 1
    blob = 0
    for i in range(depth):
        blob |= (words[i] & mask) << (i * width)
    hex_chars = (total_bits + 3) // 4
    return f"{blob:0{hex_chars}x}"


def _pattern_words(depth, width):
    """Small but non-trivial pattern — index-modulated."""
    mask = (1 << width) - 1
    return [(i * 7 + 0x55) & mask for i in range(depth)]


def _require_baseline():
    if not NV_ZERO.exists():
        raise AssertionError(f"baseline RBF missing: {NV_ZERO}")
    return NV_ZERO.read_bytes()


# ---------------------------------------------------------------------------
# 1. Parser test
# ---------------------------------------------------------------------------


def test_parse_m9k_init_line():
    width, depth = 9, 512
    words = [i & 0x1FF for i in range(depth)]
    blob = _words_to_hex(words, width, depth)
    fasm = f"X15Y2N0.INIT_{width}x{depth} = 0x{blob}\n"

    parsed = f.parse_fasm(fasm)
    m9k_inits = parsed[7]  # 8th element per bitgen unpack order
    assert len(m9k_inits) == 1, f"expected 1 entry, got {len(m9k_inits)}"
    x, y, n, w, d, got_words = m9k_inits[0]
    assert (x, y, n) == (15, 2, 0), f"coords = {(x, y, n)}"
    assert (w, d) == (width, depth), f"dims = {(w, d)}"
    assert got_words == words, (
        f"words mismatch at index "
        f"{next(i for i, (a, b) in enumerate(zip(got_words, words)) if a != b)}"
    )
    print("  test_parse_m9k_init_line: OK")


# ---------------------------------------------------------------------------
# 2 + 6. Parametrized round-trip at multiple anchors
# ---------------------------------------------------------------------------


# Three anchors spanning the two column families + distinct bp values.
_ANCHOR_SITES = [
    (15, 10, 0),  # X=15, Y=10, bp=4
    (15, 18, 0),  # X=15, Y=18, bp=1
    (27, 4, 0),   # X=27, Y=4, bp=6 (Stage A/B legacy)
]


def _run_round_trip(site_x, site_y, site_n):
    width, depth = 9, 512
    site_key = (f"X{site_x}_Y{site_y}_N{site_n}", width, depth)
    if site_key not in M9K_INIT_ANCHORS:
        raise AssertionError(f"no anchor for {site_key}")
    anchor, bp = M9K_INIT_ANCHORS[site_key]

    base = _require_baseline()
    words = _pattern_words(depth, width)
    blob = _words_to_hex(words, width, depth)
    fasm = (
        f"X{site_x}Y{site_y}N{site_n}.INIT_{width}x{depth} = 0x{blob}\n"
    )

    out = f.bitgen(fasm, base)
    decoded = read_init(out, anchor, width=width, depth=depth, bp=bp)
    if decoded != words:
        first = next(
            (i for i, (a, b) in enumerate(zip(decoded, words)) if a != b),
            -1,
        )
        raise AssertionError(
            f"round-trip failed at site {site_key}: first diff word {first} "
            f"decoded=0x{decoded[first]:03x} expected=0x{words[first]:03x}"
        )


def test_m9k_init_bitgen_round_trip():
    for site in _ANCHOR_SITES:
        _run_round_trip(*site)
        print(f"  test_m9k_init_bitgen_round_trip[X{site[0]}Y{site[1]}N{site[2]}]: OK")


# ---------------------------------------------------------------------------
# 3. Idempotence
# ---------------------------------------------------------------------------


def test_m9k_init_xor_idempotence():
    """The bitgen dispatcher uses absolute semantics via a read-before-write
    (base_words sampled live from `work` each time), so double-apply of the
    same INIT line yields the same final RBF as a single application. Also
    verify that applying the INIT then applying it again with the zero
    pattern restores the baseline (driving the XOR-delta path in
    `write_init` directly)."""
    width, depth = 9, 512
    site_key = ("X15_Y10_N0", width, depth)
    assert site_key in M9K_INIT_ANCHORS, f"no anchor for {site_key}"
    anchor, bp = M9K_INIT_ANCHORS[site_key]

    base = _require_baseline()
    words = _pattern_words(depth, width)
    zero_words = [0] * depth
    blob = _words_to_hex(words, width, depth)
    zero_blob = _words_to_hex(zero_words, width, depth)
    fasm_once = f"X15Y10N0.INIT_{width}x{depth} = 0x{blob}\n"
    fasm_twice = fasm_once * 2
    fasm_pat_then_zero = (
        fasm_once
        + f"X15Y10N0.INIT_{width}x{depth} = 0x{zero_blob}\n"
    )

    # Sanity: single pass yields the input pattern.
    once = f.bitgen(fasm_once, base)
    decoded_once = read_init(once, anchor, width=width, depth=depth, bp=bp)
    assert decoded_once == words, "single-pass round-trip failed"

    # Double-apply of the same line is idempotent (final state unchanged).
    twice = f.bitgen(fasm_twice, base)
    decoded_twice = read_init(twice, anchor, width=width, depth=depth, bp=bp)
    assert decoded_twice == words, (
        "double-apply did not match single-apply (idempotence broken)"
    )
    assert twice == once, (
        "double-apply produced different RBF bytes than single-apply"
    )

    # Apply pattern then zero-pattern -> RBF restored to baseline bytes
    # (drives XOR-cancel path of write_init).
    restored = f.bitgen(fasm_pat_then_zero, base)
    baseline_words = read_init(base, anchor, width=width, depth=depth, bp=bp)
    decoded_restored = read_init(
        restored, anchor, width=width, depth=depth, bp=bp
    )
    assert decoded_restored == baseline_words, (
        "pattern then zero did not restore baseline words"
    )
    print("  test_m9k_init_xor_idempotence: OK")


# ---------------------------------------------------------------------------
# 4. Unknown site error
# ---------------------------------------------------------------------------


def test_m9k_init_unknown_site_raises():
    width, depth = 9, 512
    words = _pattern_words(depth, width)
    blob = _words_to_hex(words, width, depth)
    fasm = f"X99Y99N0.INIT_{width}x{depth} = 0x{blob}\n"
    base = _require_baseline()
    try:
        f.bitgen(fasm, base)
    except f.FasmError as e:
        assert "no calibrated anchor" in str(e), str(e)
        print("  test_m9k_init_unknown_site_raises: OK")
        return
    raise AssertionError("expected FasmError for uncalibrated site")


# ---------------------------------------------------------------------------
# 5. Hex length mismatch error
# ---------------------------------------------------------------------------


def test_m9k_mode_parse_and_xor_idempotence():
    """The `M9K_MODE_{w}x{d}` directive flips the per-(site, W, D)
    enable cells (frames 1692-1738).  Verify parser arity, that bitgen
    flips exactly the cells in `results/m9k_mode_bits.json`, and that
    double-emit cancels (XOR-parity)."""
    import json
    base = _require_baseline()
    width, depth = 9, 512
    site_x, site_y, site_n = 15, 10, 0
    fasm_one = f"X{site_x}Y{site_y}N{site_n}.M9K_MODE_{width}x{depth}\n"

    # Parser arity check (m9k_modes is the 18th entry in parse_fasm).
    # Each element is a 6-tuple after Stage C.1 sub-flag scaffolding:
    # (x, y, n, width, depth, template).  Bare `M9K_MODE_{w}x{d}`
    # defaults template to "altsyncram".
    parsed = f.parse_fasm(fasm_one)
    assert len(parsed) == 20, f"parse_fasm arity {len(parsed)} != 20"
    m9k_modes = parsed[17]
    assert m9k_modes == [
        (site_x, site_y, site_n, width, depth, "altsyncram"),
    ], m9k_modes

    # Bitgen single-apply flips the recorded cells.  When the entry
    # has the Stage C.1 `cells_by_template` schema, the bare directive
    # form `M9K_MODE_{w}x{d}` resolves to the altsyncram bucket; older
    # entries (no `cells_by_template`) fall back to the legacy `cells`
    # field — handle both.
    cells_path = ROOT / "results" / "m9k_mode_bits.json"
    cells_data = json.loads(cells_path.read_text())
    key = f"X{site_x}_Y{site_y}_N{site_n}_{width}x{depth}"
    assert key in cells_data, f"missing mode-bits entry: {key}"
    entry = cells_data[key]
    by_template = entry.get("cells_by_template")
    if by_template is not None and "altsyncram" in by_template:
        expected_cells = {tuple(c) for c in by_template["altsyncram"]}
    else:
        expected_cells = {tuple(c) for c in entry["cells"]}

    # Reset cache so test is hermetic across reruns.
    f._M9K_MODE_CACHE = None
    out = f.bitgen(fasm_one, base)
    diffs = {(i, bp) for i in range(len(base)) for bp in range(8)
             if (base[i] ^ out[i]) & (1 << bp)}
    # CRC bytes (offset 208/209 in each 210-byte frame) are recomputed
    # by patch_rbf_crc, so filter them out before comparing.
    HDR = 32
    cram_diffs = set()
    for off, bp in diffs:
        if off < HDR:
            continue
        in_frame = (off - HDR) % 210
        if in_frame >= 208:
            continue
        cram_diffs.add((off, bp))
    assert cram_diffs == expected_cells, (
        f"bitgen diffs {len(cram_diffs)} ≠ expected {len(expected_cells)}; "
        f"missing={len(expected_cells - cram_diffs)} "
        f"extra={len(cram_diffs - expected_cells)}"
    )

    # Double-apply cancels (XOR parity).  CRC bytes will differ via
    # patch_rbf_crc, so compare via diff set instead of bytes-eq.
    f._M9K_MODE_CACHE = None
    out2 = f.bitgen(fasm_one * 2, base)
    diffs2 = {(i, bp) for i in range(len(base)) for bp in range(8)
              if (base[i] ^ out2[i]) & (1 << bp)}
    cram_diffs2 = set()
    for off, bp in diffs2:
        if off < HDR:
            continue
        in_frame = (off - HDR) % 210
        if in_frame >= 208:
            continue
        cram_diffs2.add((off, bp))
    assert cram_diffs2 == set(), (
        f"double-apply did not cancel: {len(cram_diffs2)} cells remain"
    )
    print(f"  test_m9k_mode_parse_and_xor_idempotence: OK "
          f"({len(expected_cells)} cells flipped, double cancels)")


def test_m9k_mode_unknown_site_raises():
    fasm = "X99Y99N0.M9K_MODE_9x512\n"
    base = _require_baseline()
    f._M9K_MODE_CACHE = None
    try:
        f.bitgen(fasm, base)
    except f.FasmError as e:
        assert "no mined entry" in str(e), str(e)
        print("  test_m9k_mode_unknown_site_raises: OK")
        return
    raise AssertionError("expected FasmError for unmined M9K_MODE site")


def test_m9k_mode_template_subflag_parses():
    """Stage C.1: parser accepts both bare and `_{template}` suffix forms.

    `M9K_MODE_9x512` defaults to template="altsyncram" (legacy /
    backward-compatible).  `M9K_MODE_9x512_inferred` and
    `M9K_MODE_9x512_altsyncram` are the explicit per-template forms.
    """
    fasm = (
        "X15Y10N0.M9K_MODE_9x512\n"             # bare → altsyncram
        "X15Y10N0.M9K_MODE_9x512_altsyncram\n"   # explicit altsyncram
        "X15Y10N0.M9K_MODE_9x512_inferred\n"     # explicit inferred
    )
    parsed = f.parse_fasm(fasm)
    m9k_modes = parsed[17]
    assert m9k_modes == [
        (15, 10, 0, 9, 512, "altsyncram"),
        (15, 10, 0, 9, 512, "altsyncram"),
        (15, 10, 0, 9, 512, "inferred"),
    ], m9k_modes
    print("  test_m9k_mode_template_subflag_parses: OK")


def test_m9k_mode_template_buckets_differ():
    """Stage C.1: bare/_altsyncram and _inferred resolve to DIFFERENT
    cell sets when an entry has `cells_by_template`.

    The X15_Y10_N0_9x512 entry was extended by
    fuzz/m9k_mode_template_probe.py with both buckets:
      altsyncram → 73 cells (alt^baseline, probe v3)
      inferred   → 77 cells (inf^baseline, probe v3)
    Bare form must equal `_altsyncram`; `_inferred` must differ.
    """
    base = _require_baseline()
    fasm_bare = "X15Y10N0.M9K_MODE_9x512\n"
    fasm_alt = "X15Y10N0.M9K_MODE_9x512_altsyncram\n"
    fasm_inf = "X15Y10N0.M9K_MODE_9x512_inferred\n"
    HDR = 32

    def _diffs(fasm_text):
        f._M9K_MODE_CACHE = None
        out = f.bitgen(fasm_text, base)
        diffs = set()
        for off in range(len(base)):
            x = base[off] ^ out[off]
            if not x:
                continue
            in_frame = (off - HDR) % 210
            if off < HDR or in_frame >= 208:
                continue
            for bp in range(8):
                if x & (1 << bp):
                    diffs.add((off, bp))
        return diffs

    bare = _diffs(fasm_bare)
    alt = _diffs(fasm_alt)
    inf = _diffs(fasm_inf)
    assert bare == alt, (
        f"bare ({len(bare)}) != _altsyncram ({len(alt)}) — "
        f"sym diff = {len(bare ^ alt)}"
    )
    assert bare != inf, (
        f"bare ({len(bare)}) and _inferred ({len(inf)}) should differ; "
        f"sym diff = {len(bare ^ inf)}"
    )
    # Probe-recorded cell counts (sanity check on the schema migration).
    assert len(alt) == 73, f"_altsyncram expected 73 cells, got {len(alt)}"
    assert len(inf) == 77, f"_inferred expected 77 cells, got {len(inf)}"
    print(
        f"  test_m9k_mode_template_buckets_differ: OK "
        f"(altsyncram={len(alt)}, inferred={len(inf)}, "
        f"sym diff={len(alt ^ inf)})"
    )


def test_m9k_mode_template_unknown_raises():
    """Stage C.1: parser rejects unknown template names.

    Only `altsyncram` and `inferred` are valid suffixes.  Anything else
    must NOT match `_M9K_MODE_RE`, so the line falls through and
    `parse_fasm` raises `unknown line` if no other regex picks it up.
    """
    fasm = "X15Y10N0.M9K_MODE_9x512_garbage\n"
    try:
        f.parse_fasm(fasm)
    except f.FasmError as e:
        assert "unknown line" in str(e) or "garbage" in str(e), str(e)
        print("  test_m9k_mode_template_unknown_raises: OK")
        return
    raise AssertionError("expected FasmError for unknown template suffix")


def test_m9k_mode_template_inferred_missing_bucket_raises():
    """Stage C.1: requesting `_inferred` against an entry that has no
    `cells_by_template` (legacy schema) must raise `FasmError`.

    Pick a site that only has the legacy `cells` field.  X15_Y5_N0_9x512
    is one such — only X15_Y10_N0_9x512 was promoted to the new schema
    by fuzz/m9k_mode_template_probe.py.
    """
    base = _require_baseline()
    f._M9K_MODE_CACHE = None
    fasm = "X15Y5N0.M9K_MODE_9x512_inferred\n"
    try:
        f.bitgen(fasm, base)
    except f.FasmError as e:
        msg = str(e)
        assert "inferred" in msg and "cells_by_template" in msg, msg
        print("  test_m9k_mode_template_inferred_missing_bucket_raises: OK")
        return
    raise AssertionError(
        "expected FasmError for legacy entry queried as `_inferred`"
    )


def test_m9k_init_wrong_hex_length_raises():
    width, depth = 9, 512
    # Correct length = ceil(9*512/4) = 1152 hex chars.
    short_blob = "deadbeef"
    fasm_short = f"X15Y10N0.INIT_{width}x{depth} = 0x{short_blob}\n"
    base = _require_baseline()
    try:
        f.bitgen(fasm_short, base)
    except f.FasmError as e:
        assert "hex chars" in str(e), str(e)
    else:
        raise AssertionError("expected FasmError for short hex blob")

    long_blob = "ff" * 2000  # 4000 hex chars -- too many
    fasm_long = f"X15Y10N0.INIT_{width}x{depth} = 0x{long_blob}\n"
    try:
        f.bitgen(fasm_long, base)
    except f.FasmError as e:
        assert "hex chars" in str(e), str(e)
        print("  test_m9k_init_wrong_hex_length_raises: OK")
        return
    raise AssertionError("expected FasmError for long hex blob")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    tests = [
        test_parse_m9k_init_line,
        test_m9k_init_bitgen_round_trip,
        test_m9k_init_xor_idempotence,
        test_m9k_init_unknown_site_raises,
        test_m9k_mode_parse_and_xor_idempotence,
        test_m9k_mode_unknown_site_raises,
        test_m9k_mode_template_subflag_parses,
        test_m9k_mode_template_buckets_differ,
        test_m9k_mode_template_unknown_raises,
        test_m9k_mode_template_inferred_missing_bucket_raises,
        test_m9k_init_wrong_hex_length_raises,
    ]
    for t in tests:
        t()
    print(f"\n{len(tests)}/{len(tests)} tests OK")


if __name__ == "__main__":
    main()
