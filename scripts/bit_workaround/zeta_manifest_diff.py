# SPDX-License-Identifier: GPL-3.0-or-later
"""Diff two ζ pipeline manifests (e.g. bootloader v1 vs v2).

Every successful `zeta_pipeline.py` run drops a sidecar `<stem>.manifest.json`
next to the rebuilt RBF. This tool compares two of those without touching the
RBFs themselves — you get a one-screen drift report showing:

  - whether gold SHA256 changed (did Quartus emit a different bitstream?)
  - whether rebuilt SHA256 changed (did ζ + fasm2rbf produce a different
    rebuild from the same gold? — that would be a ζ bug or fasm2rbf drift)
  - whether region cell counts shifted (is the change header-only, fabric,
    or CRC churn?)
  - baseline mismatch (did someone switch the ζ XOR baseline?)

Exit code 0 iff the two manifests agree on every anchor; 1 otherwise.

Usage:
    python3 scripts/bit_workaround/zeta_manifest_diff.py A.manifest.json B.manifest.json
    python3 scripts/bit_workaround/zeta_manifest_diff.py --json out.json A.json B.json
"""
import argparse
import json
import sys
from pathlib import Path


REGIONS = ("preamble", "header_data", "header_crc",
           "fabric_data", "fabric_crc", "postamble")


def short(sha: str | None) -> str:
    if not sha:
        return "(none)"
    return sha[:12] + "…"


def load(p: Path) -> dict:
    try:
        return json.loads(p.read_text())
    except Exception as exc:
        sys.exit(f"[FAIL] cannot load manifest {p}: {exc}")


def _region_delta(a: dict | None, b: dict | None) -> list[tuple[str, int | None, int | None, int | None]]:
    out = []
    if a is None or b is None:
        return out
    for name in REGIONS:
        va = a.get(name)
        vb = b.get(name)
        if va == vb:
            continue
        delta = None
        if isinstance(va, int) and isinstance(vb, int):
            delta = vb - va
        out.append((name, va, vb, delta))
    return out


def diff(a: dict, b: dict) -> dict:
    rep = {"equal": True, "fields": []}

    # Baseline
    ba = a.get("base", {}).get("sha256")
    bb = b.get("base", {}).get("sha256")
    if ba != bb:
        rep["equal"] = False
        rep["fields"].append({"name": "base.sha256",
                               "a": short(ba), "b": short(bb),
                               "severity": "high",
                               "hint": "ζ baseline changed — comparison may be misleading"})

    # Gold
    ga = a.get("gold", {}).get("sha256")
    gb = b.get("gold", {}).get("sha256")
    if ga != gb:
        rep["equal"] = False
        rep["fields"].append({"name": "gold.sha256",
                               "a": short(ga), "b": short(gb),
                               "severity": "high",
                               "hint": "Quartus produced a different bitstream between v1 and v2"})

    # Rebuilt
    ra = a.get("rebuilt", {}).get("sha256")
    rb = b.get("rebuilt", {}).get("sha256")
    if ra != rb:
        rep["equal"] = False
        sev = "high" if ga == gb else "low"
        hint = ("ζ + fasm2rbf produced a different rebuild from the SAME gold "
                "— investigate zeta/fasm2rbf drift") if ga == gb else \
               "rebuilt differs because gold differs (expected)"
        rep["fields"].append({"name": "rebuilt.sha256",
                               "a": short(ra), "b": short(rb),
                               "severity": sev, "hint": hint})

    # Totals
    for fname in ("zeta_bits_total", "zeta_bytes_total"):
        va = a.get(fname); vb = b.get(fname)
        if va != vb:
            rep["equal"] = False
            delta = (vb - va) if (isinstance(va, int) and isinstance(vb, int)) else None
            rep["fields"].append({"name": fname, "a": va, "b": vb,
                                   "delta": delta, "severity": "low"})

    # Regions
    reg_bits = _region_delta(a.get("region_bits") or {}, b.get("region_bits") or {})
    for name, va, vb, delta in reg_bits:
        rep["equal"] = False
        rep["fields"].append({"name": f"region_bits.{name}",
                               "a": va, "b": vb, "delta": delta,
                               "severity": "low"})
    reg_bytes = _region_delta(a.get("region_bytes") or {}, b.get("region_bytes") or {})
    for name, va, vb, delta in reg_bytes:
        rep["equal"] = False
        rep["fields"].append({"name": f"region_bytes.{name}",
                               "a": va, "b": vb, "delta": delta,
                               "severity": "low"})

    return rep


def print_report(a_path: Path, b_path: Path, a: dict, b: dict, rep: dict):
    print(f"A: {a_path}")
    print(f"   git={a.get('git_head', '?')[:12]}  ts={a.get('timestamp', '?')}")
    print(f"   input={a.get('input', {}).get('path', '?')}")
    print(f"B: {b_path}")
    print(f"   git={b.get('git_head', '?')[:12]}  ts={b.get('timestamp', '?')}")
    print(f"   input={b.get('input', {}).get('path', '?')}")
    print()

    if rep["equal"]:
        print("[OK] manifests agree on every anchor (gold, rebuilt, base, all region counts).")
        return

    # Column-aligned
    name_w = max(len(f["name"]) for f in rep["fields"])
    print(f"  {'field':<{name_w}}  {'A':>18}  {'B':>18}  {'Δ':>10}  hint")
    print(f"  {'-'*name_w}  {'-'*18}  {'-'*18}  {'-'*10}  {'-'*40}")
    for f in rep["fields"]:
        va = str(f.get("a", ""))[:18]
        vb = str(f.get("b", ""))[:18]
        delta = f.get("delta")
        delta_s = f"{delta:+d}" if isinstance(delta, int) else ""
        hint = f.get("hint", "")
        print(f"  {f['name']:<{name_w}}  {va:>18}  {vb:>18}  {delta_s:>10}  {hint}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a", type=Path)
    ap.add_argument("b", type=Path)
    ap.add_argument("--json", type=Path, default=None,
                    help="write machine-readable diff here")
    args = ap.parse_args()

    a = load(args.a); b = load(args.b)
    rep = diff(a, b)
    print_report(args.a, args.b, a, b, rep)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(rep, indent=2) + "\n")
        print(f"\nwrote {args.json}")

    sys.exit(0 if rep["equal"] else 1)


if __name__ == "__main__":
    main()
