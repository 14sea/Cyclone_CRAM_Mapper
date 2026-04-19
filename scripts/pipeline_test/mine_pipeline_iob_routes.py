# SPDX-License-Identifier: GPL-3.0-or-later
"""Mine all IOB_ROUTE sig-cache entries needed by the pipeline test.

Two-phase approach:
  Phase 1: Mine missing per-LE CLK_SEL data (clk_lab_sel_probe) for
           any (LAB, N) combo that the pipeline test targets but lacks.
  Phase 2: Build single-LE Quartus gold RBFs and derive IOB_ROUTE cells
           by subtracting all known FASM directives — identical to
           sweep_single_le.py but with dynamically-determined targets.

Usage:
    python3 scripts/pipeline_test/mine_pipeline_iob_routes.py [--jobs 4]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "fuzz"))
sys.path.insert(0, str(REPO / "synth"))

import fasm2rbf as f  # noqa: E402

PRE = 32
FRAME = 210
FIRST = 25
LAST = 1751
CRAM_END = PRE + (LAST + 1) * FRAME


def is_crc(off: int) -> bool:
    if off < PRE or off >= CRAM_END:
        return False
    return (off - PRE) % FRAME >= 208


def bit_cells(rbf_xor: bytes) -> set[tuple[int, int]]:
    out = set()
    for i, b in enumerate(rbf_xor):
        if not b:
            continue
        for bp in range(8):
            if b & (1 << bp):
                out.add((i, bp))
    return out


def get_missing_iob_routes() -> list[tuple[str, int, int, int, str]]:
    """Parse the pipeline test placed JSON and return missing IOB_ROUTE entries."""
    placed = REPO / "tmp" / "pipeline_test_open" / "test_top_placed.json"
    if not placed.exists():
        print("ERROR: run build_open.py first to generate placed JSON")
        sys.exit(1)
    from np2fasm import convert
    data = json.loads(placed.read_text())
    _, warnings = convert(data, baseline="pure")
    entries = []
    seen = set()
    for w in warnings:
        if "no iob_to_slice sig-cache" not in w:
            continue
        key = w.split(": IOB_")[1]
        if key in seen:
            continue
        seen.add(key)
        pin, tgt = key.split("->")
        parts = tgt.split(",")
        dx, dy, dn = int(parts[0]), int(parts[1]), int(parts[2])
        port = parts[3]
        entries.append((pin, dx, dy, dn, port))
    return entries


def get_missing_clk_sel_le(
    targets: list[tuple[str, int, int, int, str]],
) -> tuple[list[tuple[str, int, int, int, str]],
           list[tuple[str, int, int, int, str]],
           set[tuple[int, int]]]:
    """Split targets into those with CLK_SEL_LE data and those without.

    Returns (supported, unsupported, labs_needing_mining).
    """
    per_le = json.loads(
        (REPO / "results" / "clk_lab_sel_per_le.json").read_text()
    )
    supported = []
    unsupported = []
    labs_needed = set()
    for pin, dx, dy, dn, port in targets:
        lab_key = f"X{dx}Y{dy}"
        n_key = f"n{dn}_specific"
        if lab_key in per_le and n_key in per_le[lab_key]:
            supported.append((pin, dx, dy, dn, port))
        else:
            unsupported.append((pin, dx, dy, dn, port))
            labs_needed.add((dx, dy))
    return supported, unsupported, labs_needed


def mine_clk_sel_le(labs: set[tuple[int, int]], jobs: int) -> None:
    """Run clk_lab_sel_probe for each LAB, then regenerate per_le.json."""
    probe = REPO / "fuzz" / "clk_lab_sel_probe.py"
    work_root = REPO / "tmp" / "clk_lab_sel_pipeline"
    work_root.mkdir(parents=True, exist_ok=True)

    def run_probe(lab):
        x, y = lab
        work = work_root / f"X{x}Y{y}"
        work.mkdir(parents=True, exist_ok=True)
        p = subprocess.run(
            [sys.executable, str(probe),
             "--lab", f"{x},{y}",
             "--work", str(work)],
            cwd=str(REPO),
            capture_output=True, text=True, errors="replace",
        )
        cached = sum(1 for l in p.stdout.splitlines() if "cached" in l)
        built = sum(1 for l in p.stdout.splitlines()
                    if "s" in l and "cached" not in l and ("forced" in l or "auto" in l))
        return (x, y), p.returncode, cached, built

    print(f"\n{'='*60}")
    print(f"Phase 1: Mining CLK_SEL_LE for {len(labs)} LABs ({jobs} workers)")
    print(f"{'='*60}")

    results = []
    with cf.ThreadPoolExecutor(max_workers=jobs) as ex:
        futs = {ex.submit(run_probe, lab): lab for lab in sorted(labs)}
        for fut in cf.as_completed(futs):
            lab = futs[fut]
            try:
                (x, y), rc, cached, built = fut.result()
                tag = "OK  " if rc == 0 else "FAIL"
                print(f"  [{tag}] LAB({x:2d},{y:2d}) "
                      f"cached={cached} built={built}")
                results.append(((x, y), rc))
            except Exception as e:
                print(f"  [ERR ] LAB{lab}: {e}")
                results.append((lab, 1))

    failed = sum(1 for _, rc in results if rc != 0)
    if failed:
        print(f"\n{failed} LAB probe(s) failed!")

    print("\nRegenerating clk_lab_sel_per_le.json...")
    subprocess.run(
        [sys.executable, str(REPO / "fuzz" / "clk_lab_sel_per_le.py")],
        cwd=str(REPO),
        capture_output=True,
    )
    print("  done")


def project_dir(pin, dx, dy, dn, port):
    name = f"single_le_{pin}_to_{dx}_{dy}_{dn}_{port}"
    work = REPO / "scripts" / "iob_slice_mining" / "work"
    return work / name, name


def write_project(pin, dx, dy, dn, port):
    pdir, name = project_dir(pin, dx, dy, dn, port)
    pdir.mkdir(parents=True, exist_ok=True)

    vtext = """\
// SPDX-License-Identifier: GPL-3.0-or-later
module fuzz_top(
    input  wire CLK,
    input  wire KEY,
    output reg  LED
);
    wire lut_out;
    cycloneive_lcell_comb #(
        .lut_mask(16'hAAAA),
        .sum_lutc_input("datac"),
        .dont_touch("on")
    ) lut_prim (
        .dataa(KEY),
        .datab(1'b0),
        .datac(1'b0),
        .datad(1'b0),
        .combout(lut_out)
    );
    always @(posedge CLK) begin
        LED <= lut_out;
    end
endmodule
"""
    (pdir / "fuzz_top.v").write_text(vtext)

    qsf = (
        'set_global_assignment -name FAMILY "Cyclone IV E"\n'
        'set_global_assignment -name DEVICE EP4CE6F17C8\n'
        'set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top\n'
        'set_global_assignment -name VERILOG_FILE fuzz_top.v\n'
        'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files\n'
        'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"\n'
        'set_global_assignment -name SEED 1\n'
        f'set_location_assignment PIN_E1  -to CLK\n'
        f'set_location_assignment PIN_{pin} -to KEY\n'
        f'set_location_assignment PIN_G15 -to LED\n'
        f'set_location_assignment LCCOMB_X{dx}_Y{dy}_N{dn} -to "lut_prim"\n'
        'set_instance_assignment -name GLOBAL_SIGNAL "GLOBAL CLOCK" -to CLK\n'
    )
    (pdir / f"{name}.qsf").write_text(qsf)

    qpf = (
        'QUARTUS_VERSION = "21.1"\n'
        'DATE = "2026-04-19"\n'
        f'PROJECT_REVISION = "{name}"\n'
    )
    (pdir / f"{name}.qpf").write_text(qpf)
    return pdir, name


def build_project(pin, dx, dy, dn, port):
    pdir, name = write_project(pin, dx, dy, dn, port)
    rbf = pdir / "output_files" / f"{name}.rbf"
    sof = pdir / "output_files" / f"{name}.sof"
    if rbf.exists():
        return True, rbf, "cached"

    for step in ("quartus_map", "quartus_fit", "quartus_asm"):
        r = subprocess.run(
            [step, name], cwd=pdir,
            capture_output=True, text=True, errors="replace",
        )
        if r.returncode != 0:
            return False, rbf, f"{step} FAIL"

    r = subprocess.run(
        ["quartus_cpf", "-c", "-o", "bitstream_compression=off",
         str(sof), str(rbf)],
        cwd=pdir,
        capture_output=True, text=True, errors="replace",
    )
    return r.returncode == 0 and rbf.exists(), rbf, "built"


def derive_primary(pin, dx, dy, dn, port, gold_path):
    """Solve IOB_ROUTE_primary = gold_delta ^ (all other directives)."""
    f._IOB_BASELINE_HDR_CACHE = None
    f._IOB_MAP_CACHE = None
    f._IOB_ROUTE_CACHE = None
    f._GCLK_PIN_CACHE = None
    f._LAB_CLK_SEL_CACHE.clear()
    f._LAB_CLK_SEL_LE_CACHE = None
    f._IOB_CLK_INPUT_CACHE = None

    nv = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()
    gold = Path(gold_path).read_bytes()
    gold_xor = bytes(a ^ b for a, b in zip(gold, nv))
    gold_cells = {c for c in bit_cells(gold_xor)
                  if not is_crc(c[0]) and c[0] < CRAM_END}

    iob_map = f._load_iob_map()
    other_parity = Counter()
    directive_sets = [
        {tuple(c) for c in f._load_iob_baseline_hdr_cells()},
        {tuple(c) for c in f._iob_delta_cells("IN", pin, iob_map)},
        {tuple(c) for c in f._iob_delta_cells("OUT", "G15", iob_map)},
        {tuple(c) for c in f._load_iob_clk_input_cells("E1")},
        set(f._load_gclk_pin_cells("E1")),
        set(f._load_lab_clk_sel_cells(dx, dy)),
        set(f._load_lab_clk_sel_le_cells(dx, dy, dn)),
    ]
    for cs in directive_sets:
        for c in cs:
            other_parity[c] ^= 1
    other_cells = {c for c, v in other_parity.items() if v
                   and not is_crc(c[0]) and c[0] < CRAM_END}

    primary = gold_cells ^ other_cells
    primary_sorted = sorted(list(c) for c in primary)

    key = f"IOB_{pin}->{dx},{dy},{dn},{port}"
    f._IOB_ROUTE_CACHE = {key: primary_sorted}

    fasm_text = (
        "IOB_BASELINE_NV\n"
        f"IOB_IN  PIN_{pin}\n"
        "IOB_OUT PIN_G15\n"
        "IOB_CLK_INPUT PIN_E1\n"
        f"IOB_ROUTE PIN_{pin} -> X{dx}Y{dy}N{dn}.{port}\n"
        "GCLK_PIN PIN_E1\n"
        f"LAB_CLK_SEL X{dx}Y{dy}\n"
        f"LAB_CLK_SEL_LE X{dx}Y{dy}N{dn}\n"
    )
    out = f.bitgen(fasm_text, nv, patch_crc=True)

    data_diffs = 0
    crc_diffs = 0
    for i in range(len(out)):
        if out[i] != gold[i]:
            if is_crc(i):
                crc_diffs += 1
            else:
                data_diffs += 1
    return primary_sorted, data_diffs, crc_diffs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--skip-clk-mining", action="store_true",
                    help="Skip Phase 1 (assume CLK_SEL_LE data is current)")
    args = ap.parse_args()

    # Get missing IOB_ROUTE entries from the pipeline test
    entries = get_missing_iob_routes()
    print(f"Missing IOB_ROUTE entries: {len(entries)}")
    if not entries:
        print("Nothing to mine!")
        return 0

    # Phase 1: Mine CLK_SEL_LE if needed
    if not args.skip_clk_mining:
        supported, unsupported, labs_needed = get_missing_clk_sel_le(entries)
        if labs_needed:
            mine_clk_sel_le(labs_needed, args.jobs)
            # Re-check after mining
            supported2, unsupported2, labs2 = get_missing_clk_sel_le(entries)
            if unsupported2:
                print(f"\nWARNING: {len(unsupported2)} entries still lack "
                      f"CLK_SEL_LE data after mining:")
                for pin, dx, dy, dn, port in unsupported2[:5]:
                    print(f"  IOB_{pin}->{dx},{dy},{dn},{port}")
                entries = supported2
            else:
                print(f"\nAll {len(entries)} entries now have CLK_SEL_LE data")
        else:
            print("All CLK_SEL_LE data already mined")

    # Verify all entries have CLK_SEL_LE support
    supported, unsupported, _ = get_missing_clk_sel_le(entries)
    if unsupported:
        print(f"\nSkipping {len(unsupported)} entries without CLK_SEL_LE data")
        entries = supported

    # Phase 2: Build gold RBFs and derive IOB_ROUTE cells
    print(f"\n{'='*60}")
    print(f"Phase 2: Building {len(entries)} single-LE gold RBFs ({args.jobs} workers)")
    print(f"{'='*60}")

    build_results = {}
    with cf.ThreadPoolExecutor(max_workers=args.jobs) as ex:
        futs = {ex.submit(build_project, *e): e for e in entries}
        for fut in cf.as_completed(futs):
            entry = futs[fut]
            try:
                ok, rbf, msg = fut.result()
                pin, dx, dy, dn, port = entry
                key = f"IOB_{pin}->{dx},{dy},{dn},{port}"
                tag = "OK  " if ok else "FAIL"
                print(f"  [{tag}] {key:45s} {msg}")
                build_results[entry] = (ok, rbf)
            except Exception as e:
                print(f"  [ERR ] {entry}: {e}")
                build_results[entry] = (False, None)

    # Phase 3: Derive IOB_ROUTE cells
    print(f"\n{'='*60}")
    print(f"Phase 3: Deriving IOB_ROUTE cells")
    print(f"{'='*60}")

    derived = {}
    failures = []
    for entry, (ok, rbf) in sorted(build_results.items()):
        if not ok or rbf is None or not Path(rbf).exists():
            failures.append((entry, "build failed"))
            continue
        pin, dx, dy, dn, port = entry
        try:
            cells, data_diff, crc_diff = derive_primary(
                pin, dx, dy, dn, port, rbf
            )
        except Exception as e:
            failures.append((entry, f"derive error: {e}"))
            continue
        total = data_diff + crc_diff
        key = f"IOB_{pin}->{dx},{dy},{dn},{port}"
        print(f"  [{total:3d} diffs] {key}: {len(cells)} cells")
        if total == 0:
            derived[key] = cells
        else:
            failures.append((entry, f"nonzero diffs: data={data_diff} "
                                    f"crc={crc_diff}"))

    # Phase 4: Update sigcache
    print(f"\n{'='*60}")
    print(f"Phase 4: Updating sigcache")
    print(f"{'='*60}")

    sigcache_path = REPO / "results" / "iob_to_slice_sigcache.json"
    sig = json.loads(sigcache_path.read_text())
    existing = sig.setdefault("single_le_cells", {})
    added = 0
    for k, cells in derived.items():
        if k not in existing:
            existing[k] = cells
            added += 1
        elif existing[k] != cells:
            existing[k] = cells
            added += 1

    if derived:
        sigcache_path.write_text(json.dumps(sig, indent=2) + "\n")
        print(f"  Added {added} new single_le_cells entries")
        print(f"  Total single_le_cells: {len(existing)}")

    if failures:
        print(f"\n{len(failures)} FAILURES:")
        for entry, reason in failures:
            pin, dx, dy, dn, port = entry
            print(f"  IOB_{pin}->{dx},{dy},{dn},{port}: {reason}")

    print(f"\n{'='*60}")
    print(f"Summary: {len(derived)}/{len(entries)} entries derived cleanly")
    print(f"{'='*60}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
