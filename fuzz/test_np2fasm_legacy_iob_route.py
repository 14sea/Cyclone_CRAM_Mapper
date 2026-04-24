# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the np2fasm → fasm2rbf ``legacy_iob_route`` pragma channel.

np2fasm.convert(legacy_iob_route=True) emits a ``# fasm2rbf:
legacy_iob_route=1`` pragma; fasm2rbf.parse_pragmas(text) round-trips
the pragma back into a kwarg dict that callers forward to bitgen().
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "synth"))

import fasm2rbf
import np2fasm


MIN_JSON = {
    "modules": {
        "top": {
            "attributes": {"top": 1},
            "cells": {},
            "netnames": {},
            "ports": {},
        }
    }
}


def test_convert_no_flag_emits_no_pragma():
    lines, _ = np2fasm.convert(MIN_JSON, baseline="nv")
    joined = "\n".join(lines)
    assert "legacy_iob_route" not in joined, lines
    print("  test_convert_no_flag_emits_no_pragma: OK")


def test_convert_flag_emits_pragma_before_content():
    lines, _ = np2fasm.convert(
        MIN_JSON, baseline="pure", legacy_iob_route=True,
    )
    assert lines[0] == "# fasm2rbf: legacy_iob_route=1", lines
    assert lines[1] == "NV_BASELINE_PACK", lines
    print("  test_convert_flag_emits_pragma_before_content: OK")


def test_parse_pragmas_round_trips():
    text = "# fasm2rbf: legacy_iob_route=1\nNV_BASELINE_PACK\n"
    assert fasm2rbf.parse_pragmas(text) == {"legacy_iob_route": True}
    text2 = "# fasm2rbf: legacy_iob_route=false\n"
    assert fasm2rbf.parse_pragmas(text2) == {"legacy_iob_route": False}
    assert fasm2rbf.parse_pragmas("NV_BASELINE_PACK\n") == {}
    print("  test_parse_pragmas_round_trips: OK")


def test_parse_pragmas_rejects_unknown_key():
    text = "# fasm2rbf: not_a_real_pragma=1\n"
    try:
        fasm2rbf.parse_pragmas(text)
    except ValueError as e:
        assert "not_a_real_pragma" in str(e)
        print("  test_parse_pragmas_rejects_unknown_key: OK")
        return
    raise AssertionError("parse_pragmas should have raised")


def test_parse_pragmas_rejects_bad_value():
    text = "# fasm2rbf: legacy_iob_route=maybe\n"
    try:
        fasm2rbf.parse_pragmas(text)
    except ValueError as e:
        assert "maybe" in str(e)
        print("  test_parse_pragmas_rejects_bad_value: OK")
        return
    raise AssertionError("parse_pragmas should have raised")


def test_bitgen_accepts_parsed_pragma_kwargs():
    """End-to-end: convert → parse_pragmas → bitgen forwards legacy_iob_route."""
    from pure_zero_rbf import make_pure_zero_rbf
    lines, _ = np2fasm.convert(
        MIN_JSON, baseline="nv", legacy_iob_route=True,
    )
    text = "\n".join(lines) + "\n"
    pragmas = fasm2rbf.parse_pragmas(text)
    assert pragmas == {"legacy_iob_route": True}
    # bitgen should accept the kwarg without raising; empty FASM body
    # just returns the base unchanged (modulo CRC patching).
    rbf = fasm2rbf.bitgen(text, make_pure_zero_rbf(), **pragmas)
    assert len(rbf) == 368011
    print("  test_bitgen_accepts_parsed_pragma_kwargs: OK")


def main() -> int:
    tests = [
        test_convert_no_flag_emits_no_pragma,
        test_convert_flag_emits_pragma_before_content,
        test_parse_pragmas_round_trips,
        test_parse_pragmas_rejects_unknown_key,
        test_parse_pragmas_rejects_bad_value,
        test_bitgen_accepts_parsed_pragma_kwargs,
    ]
    ok = 0
    for t in tests:
        t()
        ok += 1
    print(f"\n{ok}/{len(tests)} tests OK")
    return 0 if ok == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
