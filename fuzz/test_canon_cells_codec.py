#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression for the σ⁻¹ canonicalization-cell codec layer.

Phase 3 codec wiring of the Phase 2 global canon table — exercises:

  - Module-level constants load with expected shapes.
  - canon_axis_diff: a/b/c/d transitions match Phase 2 table sizes
    (25 / 16 / 23 / 0) and respect c ≡ d aliasing.
  - canon_apply_transition: round-trip closure (apply twice = identity)
    and composition (a→b→c == a→c).
  - canon_classify_transition: identifies single axis-pair + neg deltas.
  - LutCodec.write_tt(... canon_to=...) preserves legacy default
    behavior when canon_to is None, and XOR-adds canon cells when set.
  - Self-consistency against the codec's read_tt: lab_cram TT bits stay
    decodable regardless of canon state (canon cells live outside the
    codec's lab_cram model).

Scope caveat: this is RBF-level wiring + invariants test.  It does NOT
validate against Quartus emission byte-identity (the codec's TT model
emits ctrl cells for 0xAAAA, Quartus emits 0 lab_cram cells via LUT
bypass routing — Phase 4 territory, not Phase 3).
"""
from __future__ import annotations

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "fuzz"))

from bitstream import (  # noqa: E402
    BYPASS_1INPUT_MASKS,
    CANON_AXIS_PAIR_DIFFS,
    CANON_NEG_DIFF,
    LutCodec,
    canon_apply_transition,
    canon_axis_diff,
    canon_classify_transition,
    is_bypass_mask,
    lut_input_dependence,
)


ZERO_RBF_PATH = os.path.join(REPO, "results", "rbf", "nv_zero_global.rbf")
CACHE_DIR = os.path.join(REPO, "tmp", "real_tt_mining")


def _load(p):
    with open(p, "rb") as f:
        return f.read()


def t_canon_table_shapes():
    # Phase 2 verdict: 5 non-empty pair-diff sets + c_d (empty); neg = 7
    assert len(CANON_AXIS_PAIR_DIFFS) == 6, len(CANON_AXIS_PAIR_DIFFS)
    expected_sizes = {
        frozenset(("a", "b")): 25,
        frozenset(("a", "c")): 16,
        frozenset(("a", "d")): 16,
        frozenset(("b", "c")): 23,
        frozenset(("b", "d")): 23,
        frozenset(("c", "d")): 0,
    }
    for k, want in expected_sizes.items():
        got = len(CANON_AXIS_PAIR_DIFFS[k])
        assert got == want, f"axis_pair {set(k)}: want {want}, got {got}"
    assert len(CANON_NEG_DIFF) == 7, len(CANON_NEG_DIFF)
    # Sanity: c_d is empty, and a_c ≡ a_d, b_c ≡ b_d (silicon c≡d)
    assert CANON_AXIS_PAIR_DIFFS[frozenset(("a", "c"))] == \
           CANON_AXIS_PAIR_DIFFS[frozenset(("a", "d"))]
    assert CANON_AXIS_PAIR_DIFFS[frozenset(("b", "c"))] == \
           CANON_AXIS_PAIR_DIFFS[frozenset(("b", "d"))]


def t_canon_axis_diff_api():
    assert len(canon_axis_diff("a", "b")) == 25
    assert len(canon_axis_diff("a", "c")) == 16
    assert len(canon_axis_diff("a", "d")) == 16  # d≡c
    assert len(canon_axis_diff("c", "d")) == 0   # c≡d
    assert len(canon_axis_diff("a", "a")) == 0
    # Symmetric
    assert canon_axis_diff("a", "b") == canon_axis_diff("b", "a")
    # Triangle: a_b XOR a_c == b_c (Phase 2 verified transitivity)
    ab = canon_axis_diff("a", "b")
    ac = canon_axis_diff("a", "c")
    bc = canon_axis_diff("b", "c")
    assert (ab ^ ac) == bc, "transitivity broken"
    # Bad axis
    try:
        canon_axis_diff("x", "a")
    except ValueError:
        pass
    else:
        assert False, "bad axis should raise"


def t_apply_transition_round_trip():
    zero = _load(ZERO_RBF_PATH)
    # Apply a→b, then b→a, should restore zero exactly
    once = canon_apply_transition(zero, "a", "b")
    twice = canon_apply_transition(once, "b", "a")
    assert twice == zero
    # neg toggle round-trip
    one_neg = canon_apply_transition(zero, "a", "a", from_negated=False, to_negated=True)
    no_neg = canon_apply_transition(one_neg, "a", "a", from_negated=True, to_negated=False)
    assert no_neg == zero
    # Composition: a→b then b→c == a→c (over canon region)
    ab_then_bc = canon_apply_transition(
        canon_apply_transition(zero, "a", "b"), "b", "c")
    ac_direct = canon_apply_transition(zero, "a", "c")
    assert ab_then_bc == ac_direct, "composition broken"


def t_classify_transition():
    zero = _load(ZERO_RBF_PATH)
    ab = canon_apply_transition(zero, "a", "b")
    kind, pair, neg = canon_classify_transition(zero, ab)
    assert kind == "axis_pair" and pair == frozenset(("a", "b")) and neg is False
    # neg-only
    neg_only = canon_apply_transition(zero, "a", "a",
                                      from_negated=False, to_negated=True)
    kind, pair, neg = canon_classify_transition(zero, neg_only)
    assert kind == "axis_pair" and pair == frozenset(("a", "a")) and neg is True
    # Both axis + neg
    abn = canon_apply_transition(zero, "a", "b",
                                 from_negated=False, to_negated=True)
    kind, pair, neg = canon_classify_transition(zero, abn)
    assert kind == "axis_pair" and pair == frozenset(("a", "b")) and neg is True


def t_classify_cached_quartus_rbfs():
    """Stronger: cached Quartus canon_a/_b/_c/_d/_na/_nb/_nc/_nd RBFs
    classify correctly between each other.  Only runs if cache present."""
    pos = "X4Y4N0"
    cached = {}
    for tag in ("a", "b", "c", "d", "na", "nb", "nc", "nd"):
        p = os.path.join(CACHE_DIR, f"canon_{tag}_{pos}", f"canon_{tag}_{pos}.rbf")
        if os.path.exists(p):
            cached[tag] = _load(p)
    if not cached:
        print("  [skip] no cached Quartus probe RBFs (tmp/real_tt_mining/ empty)")
        return
    # a vs b → axis pair {a,b}, no neg
    if "a" in cached and "b" in cached:
        k, p, n = canon_classify_transition(cached["a"], cached["b"])
        assert k == "axis_pair" and p == frozenset(("a", "b")) and n is False
    # a vs c → {a,c}
    if "a" in cached and "c" in cached:
        k, p, n = canon_classify_transition(cached["a"], cached["c"])
        assert k == "axis_pair" and p == frozenset(("a", "c")) and n is False
    # c vs d → empty axis (≡) and no neg
    if "c" in cached and "d" in cached:
        k, p, n = canon_classify_transition(cached["c"], cached["d"])
        # c == d in canon (Phase 1 evidence): expect no flips
        assert k == "axis_pair" and (p == frozenset(("a", "a")) or len(p) == 0
                                     or p in CANON_AXIS_PAIR_DIFFS) and n is False
    # a vs na → neg flip, no axis
    if "a" in cached and "na" in cached:
        k, p, n = canon_classify_transition(cached["a"], cached["na"])
        assert k == "axis_pair" and n is True


def t_lutcodec_write_tt_legacy_default():
    """canon_to=None must preserve byte-identical legacy behavior."""
    zero = _load(ZERO_RBF_PATH)
    codec = LutCodec.from_cram_model(4, 4, 0)
    for mask in (0x0000, 0xAAAA, 0xCCCC, 0xF0F0, 0xFFFF, 0x8888, 0x6996):
        out_default = codec.write_tt(zero, mask)
        # Must equal old code path: zero XOR predict_sram(mask)
        expected = bytearray(zero)
        for addr, bp in codec.predict_sram(mask):
            expected[addr] ^= (1 << bp)
        assert out_default == bytes(expected), \
            f"legacy default broken at mask 0x{mask:04X}"
    print("  legacy default write_tt preserved for 7 masks")


def t_lutcodec_write_tt_with_canon():
    """canon_to='b' adds the axis_a_b cells on top of TT bits."""
    zero = _load(ZERO_RBF_PATH)
    codec = LutCodec.from_cram_model(4, 4, 0)
    base = codec.write_tt(zero, 0xAAAA)              # no canon transition
    with_b = codec.write_tt(zero, 0xAAAA, canon_to="b", canon_from="a")
    # diff between the two should be exactly the a_b set
    diff = set()
    for off, bp in CANON_AXIS_PAIR_DIFFS[frozenset(("a", "b"))]:
        if (base[off] ^ with_b[off]) & (1 << bp):
            diff.add((off, bp))
    assert diff == CANON_AXIS_PAIR_DIFFS[frozenset(("a", "b"))], \
        f"canon_to='b' diff mismatch: {len(diff)}"
    # neg toggle on top
    with_b_neg = codec.write_tt(zero, 0xAAAA, canon_to="b",
                                canon_from="a",
                                neg_from=False, neg_to=True)
    diff_neg = set()
    for off, bp in CANON_NEG_DIFF:
        if (with_b[off] ^ with_b_neg[off]) & (1 << bp):
            diff_neg.add((off, bp))
    assert diff_neg == CANON_NEG_DIFF, "neg toggle broken"


def t_lutcodec_tt_decoding_canon_orthogonal():
    """Canon cells live OUTSIDE the codec's TT cells — read_tt's answer
    must NOT change when we toggle canon state."""
    zero = _load(ZERO_RBF_PATH)
    codec = LutCodec.from_cram_model(4, 4, 0)
    for mask in (0xAAAA, 0xCCCC, 0xF0F0, 0xFF00, 0x6996, 0x8888):
        base = codec.write_tt(zero, mask)
        m_back = codec.read_tt(base, zero)
        assert m_back == mask, f"base round-trip broken at 0x{mask:04X}"
        for ax in ("a", "b", "c", "d"):
            for neg in (False, True):
                rotated = codec.write_tt(zero, mask,
                                         canon_from="a", canon_to=ax,
                                         neg_from=False, neg_to=neg)
                m_back2 = codec.read_tt(rotated, zero)
                assert m_back2 == mask, \
                    (f"canon transition perturbed lab_cram read at "
                     f"mask=0x{mask:04X} ax={ax} neg={neg}: "
                     f"got 0x{m_back2:04X}")


def t_lut_input_dependence():
    """Phase 4: lut_input_dependence enumerates axis dependence correctly."""
    # 1-input passthrough/negation: depend on exactly 1 axis.
    cases_1 = {
        0xAAAA: {"a"},
        0xCCCC: {"b"},
        0xF0F0: {"c"},
        0xFF00: {"d"},
        0x5555: {"a"},  # !a
        0x3333: {"b"},  # !b
        0x0F0F: {"c"},  # !c
        0x00FF: {"d"},  # !d
    }
    for mask, want in cases_1.items():
        got = lut_input_dependence(mask)
        assert got == want, f"0x{mask:04X}: want {want}, got {got}"
    # Constants — 0 inputs.
    assert lut_input_dependence(0x0000) == set()
    assert lut_input_dependence(0xFFFF) == set()
    # 2-input AND/OR/XOR — exactly 2 axes.
    assert lut_input_dependence(0x8888) == {"a", "b"}   # a&b
    assert lut_input_dependence(0xEEEE) == {"a", "b"}   # a|b
    assert lut_input_dependence(0x6666) == {"a", "b"}   # a^b
    assert lut_input_dependence(0xA0A0) == {"a", "c"}   # a&c
    assert lut_input_dependence(0xF000) == {"c", "d"}   # c&d
    # 4-input XOR — all 4.
    assert lut_input_dependence(0x6996) == {"a", "b", "c", "d"}


def t_is_bypass_mask():
    """Phase 4: is_bypass_mask captures the 1-input + constant cases."""
    # All declared bypass masks classify as bypass.
    for m in BYPASS_1INPUT_MASKS:
        assert is_bypass_mask(m), f"declared bypass 0x{m:04X} rejected"
    # Constants are also bypass (0-input).
    assert is_bypass_mask(0x0000)
    assert is_bypass_mask(0xFFFF)
    # 2+-input masks are NOT bypass.
    for m in (0x8888, 0xEEEE, 0x6666, 0xA0A0, 0xC0C0, 0xF000,
              0x6996, 0x9669, 0x1234):
        assert not is_bypass_mask(m), f"non-bypass 0x{m:04X} flagged bypass"
    # Set has exactly the 8 1-input passthrough/negation entries.
    assert len(BYPASS_1INPUT_MASKS) == 8


def t_write_tt_bypass_emits_zero_tt_cells():
    """Phase 4 fix: write_tt(..., bypass=True) for a 1-input mask must NOT
    flip any of codec.predict_sram(mask)'s cells.  Confirms the lab_cram
    TT-frame byte-identity gap (Pitfall #16) is closed for bypass cases.
    """
    zero = _load(ZERO_RBF_PATH)
    codec = LutCodec.from_cram_model(4, 4, 0)
    for mask in sorted(BYPASS_1INPUT_MASKS):
        out = codec.write_tt(zero, mask, bypass=True)
        # No SRAM-region cells should have flipped.
        for addr, bp in codec.predict_sram(mask):
            assert ((out[addr] ^ zero[addr]) & (1 << bp)) == 0, (
                f"bypass=True mask 0x{mask:04X}: codec emitted SRAM "
                f"cell ({addr},{bp})")
        # In fact, with no canon kwargs, output must equal zero bytewise.
        assert out == zero, (
            f"bypass=True mask 0x{mask:04X}: unexpected byte delta")


def t_write_tt_bypass_with_canon_layer():
    """write_tt(bypass=True, canon_to=...) applies canon cells only —
    no SRAM cells — and matches `canon_apply_transition(zero, ...)`."""
    zero = _load(ZERO_RBF_PATH)
    codec = LutCodec.from_cram_model(4, 4, 0)
    for ax in ("a", "b", "c", "d"):
        for neg in (False, True):
            got = codec.write_tt(zero, 0xAAAA, bypass=True,
                                 canon_from="a", canon_to=ax,
                                 neg_from=False, neg_to=neg)
            want = canon_apply_transition(zero, "a", ax,
                                          from_negated=False,
                                          to_negated=neg)
            assert got == want, (
                f"bypass + canon mismatch: ax={ax} neg={neg}")


def t_write_tt_default_still_emits_sram():
    """Critical: default behavior unchanged.  bypass=False (default) MUST
    still XOR-emit predict_sram cells for legacy callers and round-trip.
    """
    zero = _load(ZERO_RBF_PATH)
    codec = LutCodec.from_cram_model(4, 4, 0)
    for mask in (0xAAAA, 0xCCCC, 0x8888, 0x6996):
        out = codec.write_tt(zero, mask)
        # SRAM cells from predict_sram should be flipped.
        for addr, bp in codec.predict_sram(mask):
            assert ((out[addr] ^ zero[addr]) & (1 << bp)) != 0, (
                f"legacy default broke at 0x{mask:04X}: cell ({addr},{bp}) "
                f"not flipped")
        # Round-trip via read_tt
        assert codec.read_tt(out, zero) == mask


def main():
    tests = [
        ("canon_table_shapes",           t_canon_table_shapes),
        ("canon_axis_diff_api",          t_canon_axis_diff_api),
        ("apply_transition_round_trip",  t_apply_transition_round_trip),
        ("classify_transition",          t_classify_transition),
        ("classify_cached_quartus",      t_classify_cached_quartus_rbfs),
        ("write_tt_legacy_default",      t_lutcodec_write_tt_legacy_default),
        ("write_tt_with_canon",          t_lutcodec_write_tt_with_canon),
        ("tt_decoding_canon_orthogonal", t_lutcodec_tt_decoding_canon_orthogonal),
        # Phase 4 — bypass-mode TT model.
        ("lut_input_dependence",         t_lut_input_dependence),
        ("is_bypass_mask",               t_is_bypass_mask),
        ("write_tt_bypass_zero_cells",   t_write_tt_bypass_emits_zero_tt_cells),
        ("write_tt_bypass_with_canon",   t_write_tt_bypass_with_canon_layer),
        ("write_tt_default_emits_sram",  t_write_tt_default_still_emits_sram),
    ]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed.append((name, str(e)))
            print(f"  FAIL  {name}: {e}")
        except Exception as e:
            failed.append((name, f"{type(e).__name__}: {e}"))
            print(f"  ERR   {name}: {type(e).__name__}: {e}")
    print()
    if failed:
        print(f"FAILED: {len(failed)}/{len(tests)}")
        return 1
    print(f"PASS: {len(tests)}/{len(tests)} canon-codec tests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
