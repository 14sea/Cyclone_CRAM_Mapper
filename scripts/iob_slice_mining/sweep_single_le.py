# SPDX-License-Identifier: GPL-3.0-or-later
"""Sweep-derive single_le_cells entries for every (pin, target) combo
whose supporting clock-mining data is available today.

For each (pin, dx, dy, dn, port):
  1. Generate a minimal Quartus project (KEY=pin → LUT@XdxYdyNdn → DFF
     → LED=G15) in work/single_le_<pin>_to_<dx>_<dy>_<dn>_<port>/.
  2. Run quartus_map / _fit / _asm / _cpf to produce the gold RBF.
  3. Derive  IOB_ROUTE_primary = gold_delta ^ (all other directives)
     using the same algebra as derive_iob_route_primary.py.
  4. Verify the FASM rebuild matches gold byte-for-byte.
  5. Collect entries into results/iob_to_slice_sigcache.json under
     single_le_cells.

Parallelism: up to --jobs Quartus builds run concurrently; derivation is
single-threaded (it's sub-second per entry).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "fuzz"))

import fasm2rbf as f  # noqa: E402


PRE = 32
FRAME = 210
FIRST = 25
LAST = 1751
CRAM_END = PRE + (LAST + 1) * FRAME


# Immediately doable: pins × targets whose LAB_CLK_SEL + LAB_CLK_SEL_LE
# data is already mined.  (10,10,0) and (10,4,2) need more mining first
# and are excluded by filter_supported().
PINS = ["E16", "E15", "M16"]
TARGETS = [
    (10, 4, 0, "dataa"),
    (10, 4, 4, "dataa"),
    (16, 4, 0, "dataa"),
]


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


def filter_supported(combos):
    """Drop entries whose supporting clock data is missing (would error
    in the derivation step)."""
    supported = []
    skipped = []
    for pin, dx, dy, dn, port in combos:
        try:
            f._load_lab_clk_sel_cells(dx, dy)
            f._load_lab_clk_sel_le_cells(dx, dy, dn)
            supported.append((pin, dx, dy, dn, port))
        except Exception as e:
            skipped.append(((pin, dx, dy, dn, port), str(e)))
    return supported, skipped


def project_dir(pin, dx, dy, dn, port):
    name = f"single_le_{pin}_to_{dx}_{dy}_{dn}_{port}"
    return HERE / "work" / name, name


def write_project(pin, dx, dy, dn, port):
    pdir, name = project_dir(pin, dx, dy, dn, port)
    pdir.mkdir(parents=True, exist_ok=True)

    # Verilog: same as simple_led_E16_to_G15 — dataa-passthrough LUT
    # with dont_touch pinned to LCCOMB_X{dx}_Y{dy}_N{dn}, DFF → LED.
    # Note: Quartus canonicalizes single-input LUTs to dataa; the port
    # parameter in the sigcache key is just a label for now.
    vtext = """// SPDX-License-Identifier: GPL-3.0-or-later
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
        'DATE = "2026-04-15"\n'
        f'PROJECT_REVISION = "{name}"\n'
    )
    (pdir / f"{name}.qpf").write_text(qpf)

    return pdir, name


def build_project(pin, dx, dy, dn, port):
    """Run quartus_map / fit / asm / cpf.  Return (ok, rbf_path, log)."""
    pdir, name = write_project(pin, dx, dy, dn, port)
    rbf = pdir / "output_files" / f"{name}.rbf"
    sof = pdir / "output_files" / f"{name}.sof"
    if rbf.exists():
        return True, rbf, "cached"

    log_lines = []
    for step in ("quartus_map", "quartus_fit", "quartus_asm"):
        r = subprocess.run(
            [step, name],
            cwd=pdir,
            capture_output=True,
            text=True,
            errors="replace",
        )
        log_lines.append(f"=== {step} ===\n{r.stdout[-2000:]}")
        if r.returncode != 0:
            log_lines.append(f"RC={r.returncode}\nSTDERR:\n{r.stderr[-2000:]}")
            (pdir / "build.log").write_text("\n".join(log_lines))
            return False, rbf, "\n".join(log_lines)
    # cpf: convert .sof -> .rbf with compression off
    r = subprocess.run(
        ["quartus_cpf", "-c", "-o", "bitstream_compression=off",
         str(sof), str(rbf)],
        cwd=pdir,
        capture_output=True,
        text=True,
        errors="replace",
    )
    log_lines.append(f"=== quartus_cpf ===\n{r.stdout[-2000:]}")
    (pdir / "build.log").write_text("\n".join(log_lines))
    return r.returncode == 0 and rbf.exists(), rbf, "\n".join(log_lines)


def derive_primary(pin, dx, dy, dn, port, gold_path):
    """Solve IOB_ROUTE_primary = gold_delta ^ (all other directives).

    Returns (primary_cells_sorted, n_data_diff, n_crc_diff).
    """
    # Reset caches for a clean run
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

    primary = (gold_cells ^ other_cells)
    primary_sorted = sorted(list(c) for c in primary)

    # Verify by patching in-memory and rebuilding
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
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-build", action="store_true",
                    help="Assume RBFs already built, just derive")
    args = ap.parse_args()

    combos = [(pin, dx, dy, dn, port)
              for pin in PINS for (dx, dy, dn, port) in TARGETS]
    supported, skipped = filter_supported(combos)
    for c, err in skipped:
        print(f"  [skip] {c}: {err.splitlines()[0]}")
    print(f"supported entries: {len(supported)}")

    if args.dry_run:
        for c in supported:
            print(f"  would build: {c}")
        return 0

    # Phase 1: parallel Quartus builds
    results = {}  # combo -> (ok, rbf, log)
    if not args.skip_build:
        with cf.ThreadPoolExecutor(max_workers=args.jobs) as ex:
            futs = {ex.submit(build_project, *c): c for c in supported}
            for fut in cf.as_completed(futs):
                combo = futs[fut]
                try:
                    ok, rbf, log = fut.result()
                except Exception as e:  # noqa: BLE001
                    ok, rbf, log = False, None, f"exception: {e}"
                results[combo] = (ok, rbf, log)
                status = "OK" if ok else "FAIL"
                print(f"  [{status}] build {combo} -> {rbf}")
    else:
        for combo in supported:
            pin, dx, dy, dn, port = combo
            pdir, name = project_dir(pin, dx, dy, dn, port)
            rbf = pdir / "output_files" / f"{name}.rbf"
            results[combo] = (rbf.exists(), rbf, "cached")

    # Phase 2: serial derivation (sub-second each)
    entries = {}
    failures = []
    for combo, (ok, rbf, _log) in results.items():
        if not ok or not rbf.exists():
            failures.append((combo, "build failed"))
            continue
        pin, dx, dy, dn, port = combo
        try:
            cells, data_diff, crc_diff = derive_primary(*combo, rbf)
        except Exception as e:  # noqa: BLE001
            failures.append((combo, f"derive error: {e}"))
            continue
        total = data_diff + crc_diff
        key = f"IOB_{pin}->{dx},{dy},{dn},{port}"
        print(f"  [{total:3d} diffs] {key}: {len(cells)} cells "
              f"(data={data_diff}, crc={crc_diff})")
        if total == 0:
            entries[key] = cells
        else:
            failures.append((combo, f"nonzero diffs: data={data_diff} "
                                    f"crc={crc_diff}"))

    # Phase 3: merge into sigcache
    sigcache_path = REPO / "results" / "iob_to_slice_sigcache.json"
    sig = json.loads(sigcache_path.read_text())
    existing = sig.setdefault("single_le_cells", {})
    added = 0
    updated = 0
    for k, cells in entries.items():
        if k in existing:
            if existing[k] != cells:
                existing[k] = cells
                updated += 1
        else:
            existing[k] = cells
            added += 1
    if entries:
        meta = sig.setdefault("meta", {})
        note = meta.setdefault("single_le_source", "")
        if "sweep_single_le.py" not in note:
            meta["single_le_source"] = (
                note + " | swept by "
                "scripts/iob_slice_mining/sweep_single_le.py "
                "on 2026-04-15"
            ).strip(" |")
        sigcache_path.write_text(json.dumps(sig, indent=2) + "\n")
        print(f"\nsigcache: +{added} added, {updated} updated, "
              f"now {len(existing)} single_le_cells entries")

    if failures:
        print("\nFAILURES:")
        for combo, reason in failures:
            print(f"  {combo}: {reason}")
        return 1
    print(f"\n{len(entries)}/{len(supported)} entries derived cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
