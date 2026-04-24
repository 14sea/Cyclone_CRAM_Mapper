# SPDX-License-Identifier: GPL-3.0-or-later
"""ζ corpus regression: run zeta_pipeline against every fixture in
`tests/zeta_corpus/manifest.json` and assert byte-identity + region-cell
invariants.

This is the broader sibling of `zeta_selftest.py`:

- selftest is a single-fixture, sub-second pre-commit smoke,
- regression is the full corpus, takes a few seconds, suitable for CI or
  "before pushing" checks.

A fixture passes iff:
  1. It exists locally (else SKIP with warning).
  2. Its on-disk SHA256 matches `manifest.entries[].sha256` (else FAIL:
     gold drift — decide whether to re-anchor).
  3. `zeta_pipeline` returns OK (ζ → fasm2rbf → byte-identity all green).
  4. The rebuilt RBF's SHA256 matches the gold's SHA256 (redundant with
     the pipeline's own byte-identity gate, but cheap and catches buggy
     gates).
  5. `zeta_rbf_diff.categorize(base, gold)` returns the region-bit /
     region-byte counts in the manifest (catches drift where round-trip
     still succeeds but the gold's cell footprint changed).

Re-anchor mode (`--reanchor`) overwrites the manifest with current
SHA256s + region counts for every entry that either (a) has a `TBD`
SHA256, or (b) is missing one of the expected fields. It never silently
changes an existing correct anchor — if the anchor has drifted, you
must pass `--reanchor-all` to accept the new values.

Usage:
    python3 scripts/bit_workaround/zeta_regression.py
    python3 scripts/bit_workaround/zeta_regression.py --strict
    python3 scripts/bit_workaround/zeta_regression.py --reanchor
    python3 scripts/bit_workaround/zeta_regression.py --reanchor-all
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "tests" / "zeta_corpus" / "manifest.json"
PIPELINE = ROOT / "scripts" / "bit_workaround" / "zeta_pipeline.py"

sys.path.insert(0, str(ROOT / "scripts" / "bit_workaround"))
from zeta_rbf_diff import categorize  # type: ignore  # noqa: E402


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def region_bits_bytes(base: Path, gold: Path) -> tuple[dict, dict]:
    rep = categorize(base.read_bytes(), gold.read_bytes())
    names = ("preamble", "header_data", "header_crc",
             "fabric_data", "fabric_crc", "postamble")
    bits = {n: rep[n]["bits"] for n in names}
    byts = {n: rep[n]["bytes"] for n in names}
    return bits, byts


def run_pipeline(gold: Path, base: Path, workdir: Path) -> tuple[bool, str, Path]:
    workdir.mkdir(parents=True, exist_ok=True)
    rebuilt = workdir / f"{gold.stem}.rebuilt.rbf"
    rc = subprocess.run(
        ["python3", str(PIPELINE), str(gold),
         "--base", str(base),
         "--workdir", str(workdir)],
        capture_output=True, text=True,
    )
    ok = rc.returncode == 0 and rebuilt.exists()
    # last non-empty line of stdout is usually the "[OK] ..." or "FAIL" summary
    tail = [l for l in rc.stdout.split("\n") if l.strip()]
    msg = tail[-1] if tail else f"rc={rc.returncode}"
    if not ok and rc.stderr.strip():
        msg += f" | stderr: {rc.stderr.strip().split(chr(10))[-1][:120]}"
    return ok, msg, rebuilt


def check_entry(entry: dict, base: Path, work_root: Path, reanchor_all: bool) -> dict:
    """Run all gates for a single entry. Return result dict."""
    name = entry["name"]
    path = ROOT / entry["path"]
    res = {"name": name, "path": str(path.relative_to(ROOT)),
           "status": None, "msg": "", "seconds": 0.0, "anchors": {}}

    if not path.exists():
        res["status"] = "SKIP"
        res["msg"] = "fixture not present locally"
        return res

    t0 = time.time()
    actual_sha = sha256_file(path)
    expected_sha = entry.get("sha256", "")
    if expected_sha.upper() != "TBD" and actual_sha != expected_sha and not reanchor_all:
        res["status"] = "FAIL"
        res["msg"] = (f"SHA256 drift: manifest={expected_sha[:12]}… "
                      f"on-disk={actual_sha[:12]}…")
        res["seconds"] = time.time() - t0
        return res

    # Pipeline round-trip
    wd = work_root / name
    ok, msg, rebuilt = run_pipeline(path, base, wd)
    if not ok:
        res["status"] = "FAIL"
        res["msg"] = f"pipeline: {msg}"
        res["seconds"] = time.time() - t0
        return res

    rebuilt_sha = sha256_file(rebuilt)
    if rebuilt_sha != actual_sha:
        res["status"] = "FAIL"
        res["msg"] = (f"rebuilt SHA256 ≠ gold: "
                      f"rebuilt={rebuilt_sha[:12]}… gold={actual_sha[:12]}…")
        res["seconds"] = time.time() - t0
        return res

    # Region invariants
    bits, byts = region_bits_bytes(base, path)
    total_bits = sum(bits.values())
    expected_bits = entry.get("region_bits")
    expected_bytes = entry.get("region_bytes")
    expected_total = entry.get("zeta_bits_total")

    drift = []
    if expected_bits is not None and expected_bits != bits:
        drift.append(f"region_bits {expected_bits} → {bits}")
    if expected_bytes is not None and expected_bytes != byts:
        drift.append(f"region_bytes {expected_bytes} → {byts}")
    if expected_total is not None and expected_total != total_bits:
        drift.append(f"zeta_bits_total {expected_total} → {total_bits}")

    res["anchors"] = {"sha256": actual_sha, "zeta_bits_total": total_bits,
                      "region_bits": bits, "region_bytes": byts}
    res["seconds"] = time.time() - t0

    if drift and not reanchor_all:
        res["status"] = "FAIL"
        res["msg"] = "region drift: " + "; ".join(drift)
        return res

    res["status"] = "OK"
    res["msg"] = f"{total_bits} bits, {sum(byts.values())} bytes"
    return res


def reanchor_manifest(manifest: dict, results: list, only_tbd: bool):
    """Write fresh SHA256/region counts into manifest for entries that need it."""
    by_name = {e["name"]: e for e in manifest["entries"]}
    updated = []
    for r in results:
        if r["status"] != "OK" and r["status"] != "FAIL":
            continue
        if not r.get("anchors"):
            continue
        entry = by_name[r["name"]]
        a = r["anchors"]
        # Only update if TBD (gentle) OR caller passed --reanchor-all (forcing)
        needs_update = (
            (only_tbd and entry.get("sha256", "").upper() == "TBD")
            or (not only_tbd)
        )
        if not needs_update:
            continue
        entry["sha256"] = a["sha256"]
        entry["zeta_bits_total"] = a["zeta_bits_total"]
        entry["region_bits"] = a["region_bits"]
        entry["region_bytes"] = a["region_bytes"]
        updated.append(r["name"])
    if updated:
        CORPUS.write_text(json.dumps(manifest, indent=2) + "\n")
    return updated


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strict", action="store_true",
                    help="treat SKIP (missing fixture) as FAIL")
    ap.add_argument("--reanchor", action="store_true",
                    help="update manifest entries whose sha256 is 'TBD'")
    ap.add_argument("--reanchor-all", action="store_true",
                    help="force-update every manifest entry to current values "
                         "(accept drift — use only for intentional changes)")
    ap.add_argument("--workdir", type=Path,
                    default=ROOT / "tmp" / "zeta_regression")
    ap.add_argument("--json", type=Path, default=None,
                    help="write full results JSON here")
    args = ap.parse_args()

    manifest = json.loads(CORPUS.read_text())
    base_rel = manifest["base"]["path"]
    base = ROOT / base_rel
    if not base.exists():
        sys.exit(f"[FAIL] baseline missing: {base}")

    base_sha = sha256_file(base)
    if base_sha != manifest["base"]["sha256"] and not args.reanchor_all:
        sys.exit(f"[FAIL] baseline SHA256 drift: "
                 f"manifest={manifest['base']['sha256'][:12]}… "
                 f"on-disk={base_sha[:12]}…")

    args.workdir.mkdir(parents=True, exist_ok=True)

    results = []
    for entry in manifest["entries"]:
        r = check_entry(entry, base, args.workdir, args.reanchor_all)
        results.append(r)

    # Print aligned report
    name_w = max((len(r["name"]) for r in results), default=8)
    print(f"\nζ regression ({len(results)} entries, base={base_rel}):\n")
    print(f"  {'status':<6}  {'name':<{name_w}}  {'s':>5}  detail")
    print(f"  {'-'*6}  {'-'*name_w}  {'-'*5}  {'-'*40}")
    for r in results:
        print(f"  {r['status']:<6}  {r['name']:<{name_w}}  "
              f"{r['seconds']:>5.2f}  {r['msg']}")

    any_fail = any(r["status"] == "FAIL" for r in results)
    any_skip = any(r["status"] == "SKIP" for r in results)

    if args.reanchor or args.reanchor_all:
        updated = reanchor_manifest(manifest, results, only_tbd=not args.reanchor_all)
        print(f"\n[reanchor] updated {len(updated)} entries: {', '.join(updated) or '-'}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({
            "base": {"path": base_rel, "sha256": base_sha},
            "results": results,
        }, indent=2) + "\n")
        print(f"\nwrote {args.json}")

    if any_fail:
        sys.exit(1)
    if any_skip and args.strict:
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
