# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 4.5 factory-finalize — one-shot post-factory wrap-up.

Run after plan_d_prime_factory.py finishes (or at any point to get
a current snapshot). Steps:

  1. Re-run `nv_sig_cache_merge.py`  → results/route_cells_full.json
  2. Re-run `nv_edge_coverage.py`    → results/nv_edge_coverage.json
  3. Parse the coverage report and extract:
     - merged 7-tuple entries (total)
     - coverage % of 12,259 strict-deduped NEORV32 edges
     - sources fully covered / 4,291
  4. Substitute those numbers into /tmp/claude_md_phase45_draft.md
     placeholders and emit /tmp/claude_md_phase45_final.md
  5. Print a commit-ready summary block

Zero risk — all inputs are already stable, output is a text replace.

Usage:
    python3 fuzz/nv_factory_finalize.py          # run full pipeline
    python3 fuzz/nv_factory_finalize.py --dry    # skip re-merges, just
                                                   parse existing JSONs
"""
import os, sys, json, subprocess, re, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUZZ = os.path.join(ROOT, "fuzz")
RESULTS = os.path.join(ROOT, "results")
DRAFT = "/tmp/claude_md_phase45_draft.md"
FINAL = "/tmp/claude_md_phase45_final.md"


def run(script):
    path = os.path.join(FUZZ, script)
    print(f"  $ python3 fuzz/{script}")
    r = subprocess.run(
        [sys.executable, path], cwd=ROOT,
        capture_output=True, text=True, timeout=600,
    )
    if r.returncode != 0:
        print(f"  FAIL (rc={r.returncode})")
        print(f"  stderr: {r.stderr[-400:]}")
        sys.exit(1)
    print(f"  OK ({len(r.stdout.splitlines())} lines)")
    return r.stdout


def load_coverage():
    """Extract the numbers we need from the two JSON products."""
    cov_path = os.path.join(RESULTS, "nv_edge_coverage.json")
    full_path = os.path.join(RESULTS, "route_cells_full.json")

    if not os.path.exists(cov_path):
        print(f"  missing: {cov_path}")
        sys.exit(1)
    if not os.path.exists(full_path):
        print(f"  missing: {full_path}")
        sys.exit(1)

    with open(cov_path) as f:
        cov = json.load(f)
    with open(full_path) as f:
        full = json.load(f)

    # Accept either flat-dict or consolidated-structure full cache.
    if isinstance(full, dict) and "groups" in full:
        n_entries = sum(len(g.get("port_delta", {})) for g in full["groups"].values())
    else:
        n_entries = len(full)

    # Coverage JSON layout: per Task H, it records totals + per-source.
    # Expected keys (fall back gracefully if the schema was tweaked).
    total_edges = cov.get("total_edges") or cov.get("edges_total") or 12259
    covered     = cov.get("covered") or cov.get("edges_covered") or 0
    sources_full = (cov.get("sources_fully_covered")
                    or cov.get("sources_full") or 0)
    total_sources = (cov.get("total_sources")
                     or cov.get("sources_total") or 4291)
    pct = 100.0 * covered / total_edges if total_edges else 0

    return {
        "merged_entries": n_entries,
        "coverage_pct": pct,
        "covered_edges": covered,
        "total_edges": total_edges,
        "sources_full": sources_full,
        "total_sources": total_sources,
    }


def substitute(draft_text, stats):
    mapping = {
        "{{FINAL_MERGED_ENTRIES}}": f"{stats['merged_entries']:,}",
        "{{FINAL_COVERAGE_PCT}}":   f"{stats['coverage_pct']:.1f}",
        "{{FINAL_SOURCES_FULL}}":   f"{stats['sources_full']:,}",
    }
    out = draft_text
    for k, v in mapping.items():
        out = out.replace(k, v)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true",
                    help="skip merge/coverage re-runs, parse existing JSONs")
    args = ap.parse_args()

    print("=== Phase 4.5 factory finalize ===\n")

    if not args.dry:
        print("[1/2] merging sig-cache...")
        run("nv_sig_cache_merge.py")
        print("[2/2] running edge-coverage report...")
        run("nv_edge_coverage.py")
    else:
        print("(--dry: skipping merge/coverage)")

    print("\nparsing results...")
    stats = load_coverage()
    print(f"  merged entries:       {stats['merged_entries']:,}")
    print(f"  edges covered:        {stats['covered_edges']:,} / {stats['total_edges']:,} "
          f"({stats['coverage_pct']:.1f}%)")
    print(f"  sources fully cover'd: {stats['sources_full']:,} / {stats['total_sources']:,}")

    if not os.path.exists(DRAFT):
        print(f"\n  draft not found: {DRAFT}")
        print("  stats printed above; manual CLAUDE.md update needed.")
        return

    draft = open(DRAFT).read()
    final = substitute(draft, stats)
    with open(FINAL, "w") as f:
        f.write(final)
    print(f"\nwrote {FINAL}")

    unresolved = re.findall(r"\{\{[A-Z_]+\}\}", final)
    if unresolved:
        print(f"  WARNING: {len(unresolved)} placeholders still unresolved: "
              f"{sorted(set(unresolved))}")
    else:
        print("  all placeholders resolved — ready to insert into CLAUDE.md")

    print()
    print("=" * 60)
    print("Phase 4.5 summary for commit message:")
    print("=" * 60)
    print(f"Plan D' factory: {stats['merged_entries']:,} merged 7-tuple entries")
    print(f"NEORV32 edge coverage: {stats['coverage_pct']:.1f}% "
          f"({stats['covered_edges']:,}/{stats['total_edges']:,})")
    print(f"Sources fully covered: {stats['sources_full']:,}/{stats['total_sources']:,} "
          f"({100*stats['sources_full']/stats['total_sources']:.1f}%)")


if __name__ == "__main__":
    main()
