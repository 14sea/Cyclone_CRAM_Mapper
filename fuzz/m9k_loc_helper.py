# SPDX-License-Identifier: GPL-3.0-or-later
"""M9K LOC helper — post-compile LOC-honored verification.

Background
----------
Earlier drafts of this file tried to solve the "LOC silently ignored"
bug by discovering the per-config ``altsyncram_<hash>`` wrapper name
via a ``quartus_map``-only pass and building a hierarchical LOC node
path like ``altsyncram:u|altsyncram_2v11:auto_generated|ALTSYNCRAM``.
**That approach was wrong.** Even with the correct wrapper name,
Fitter rejects the path with:

    Warning (15706): Node "altsyncram:u|altsyncram_2v11:auto_generated
    |ALTSYNCRAM" is assigned to location or region, but does not
    exist in design

The correct LOC target is simply the Verilog instance name of the
``altsyncram`` — e.g. ``-to "u"``. Quartus follows the instance name
into the megafunction wrapper automatically and places the underlying
RAMBLOCK at the requested M9K site. ``fuzz/m9k_probe_mine.py`` had
the right syntax all along.

This module now only provides ``verify_loc_honored`` — a post-compile
safety net that parses ``fit.rpt`` and confirms the M9K landed at the
requested site. Stage A/B were mined in a silent-LOC state because
no verifier ran; keeping this check mandatory on every mining compile
prevents a repeat.

Public API
----------
    verify_loc_honored(proj_dir, project_name, expected_site)
    # -> (honored: bool, actual_site: str | None, reason: str)
"""
from __future__ import annotations
import os
import re

# Fitter "Ignored locations" warning — the authoritative signal that
# a LOC assignment did NOT take effect. Fitter emits one of these per
# dropped assignment, listing the offending node name.
_IGNORED_LOC_RE = re.compile(
    r'Node\s+"([^"]+)"\s+is\s+assigned\s+to\s+location\s+or\s+region,\s+'
    r'but\s+does\s+not\s+exist\s+in\s+design'
)

# Match an M9K coordinate token. Used to find the placed site from
# the Fitter "Resource Utilization by Entity" or single-M9K fallback.
_M9K_SITE_RE = re.compile(r"M9K_X(\d+)_Y(\d+)_N(\d+)")


def verify_loc_honored(
    proj_dir: str,
    project_name: str,
    expected_site: str,
) -> tuple[bool, str | None, str]:
    """Inspect ``fit.rpt`` and confirm the altsyncram M9K landed at
    ``expected_site`` (e.g. ``"X15_Y2_N0"``).

    Returns ``(honored, actual_site, reason)`` where ``honored`` is
    True iff Quartus placed the M9K at the requested coordinates.

    Implementation notes:
    1. First scans for Fitter "Ignored locations" warnings. If
       Quartus dropped a LOC that mentions an altsyncram or M9K
       node, the assignment clearly did not take effect — return
       False immediately. This is the authoritative signal; it is
       the warning that Stage A/B silently triggered for every
       compile.
    2. If no ignored-LOC warning fired, fall through to a placement
       check: grab the set of M9K_X*_Y*_N* coordinates from fit.rpt.
       If exactly one site is present (true for any single-M9K
       harness) and it matches ``expected_site``, return ok. If it
       differs, the LOC was dropped without a warning — still a
       failure.
    """
    fit_rpt = os.path.join(
        proj_dir, "output_files", f"{project_name}.fit.rpt"
    )
    if not os.path.exists(fit_rpt):
        return False, None, f"fit.rpt missing: {fit_rpt}"
    try:
        txt = open(fit_rpt, errors="replace").read()
    except Exception as e:
        return False, None, f"fit.rpt unreadable: {e}"

    # (1) Ignored-LOC warnings — any match involving altsyncram / M9K
    # / the expected site means Quartus silently dropped the LOC.
    for m in _IGNORED_LOC_RE.finditer(txt):
        node = m.group(1)
        if ("altsyncram" in node or "M9K" in node or
                node == "u" or node.endswith("|u")):
            return (False, None,
                    f"Fitter ignored LOC on node {node!r}")

    # (2) Placement check — use the set of all distinct M9K sites in
    # fit.rpt. Only sensible for single-M9K harnesses.
    sites = set()
    for m in _M9K_SITE_RE.finditer(txt):
        sites.add(f"X{m.group(1)}_Y{m.group(2)}_N{m.group(3)}")
    if not sites:
        return False, None, "no M9K placement found in fit.rpt"
    if expected_site in sites and len(sites) == 1:
        return True, expected_site, "ok"
    if expected_site in sites:
        # Multi-M9K design — expected site present among several.
        return (True, expected_site,
                f"ok (one of {len(sites)} M9K sites)")
    # Expected site absent. Report whichever single site we saw.
    if len(sites) == 1:
        actual = next(iter(sites))
        return (False, actual,
                f"LOC dropped silently: requested {expected_site}, "
                f"got {actual}")
    return (False, None,
            f"LOC dropped: requested {expected_site}, sites present: "
            f"{sorted(sites)}")


if __name__ == "__main__":
    # Self-test: run the verifier against the 4 RBFs left on disk by
    # the most recent m9k_anchor_sweep.py run (or any single-M9K
    # compile in work/). Requires work/ artifacts to exist — this is
    # read-only diagnostic, not a full build.
    import glob
    import sys
    pattern = sys.argv[1] if len(sys.argv) > 1 else "work/m9k_as_*"
    dirs = sorted(glob.glob(pattern))
    for d in dirs:
        tag = os.path.basename(d)
        # Extract expected site from tag: m9k_as_X15_Y4_N0_9x512_w0_b0
        m = re.search(r"X\d+_Y\d+_N\d+", tag)
        if not m:
            continue
        expected = m.group(0)
        ok, actual, reason = verify_loc_honored(d, tag, expected)
        mark = "OK" if ok else "!!"
        print(f"  [{mark}] {tag}: expected={expected} "
              f"actual={actual} — {reason}")
