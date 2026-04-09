#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.2 calibration helper — fit a 2D linear M9K init formula
for an arbitrary (x, y, n, width, depth) placement by running a small
parallel probe sweep and solving for (anchor, dW_odd, dB, bp).

Generalized formula model:
    byte(w, bit) = anchor + (w // 2) * dW_pair + (w %% 2) * dW_odd
                          + bit * dB
    bp           = constant per site

Stage A (X27_Y4_N0) fit:   dW_pair=+210, dW_odd=-1, dB=-2, bp=6
LED harness (X27_Y16_N0):  dW_pair=+210, dW_odd=-1, dB=??,  bp=2 (w0_b8 empty)

Bit axis can have sign flipped or land on a different bp row depending
on placement. This script does not pre-assume the layout — it probes
the (word, bit) corners, filters frame CRC bytes (offset 208/209), and
fits the linear model from the clean singletons.

Usage (as a library):
    from m9k_calibrate import calibrate_site
    fit = calibrate_site(harness_module, probe_words=[1,2], probe_bits=[0,1,2,4,8])
    # fit = {"anchor": int, "bp": int, "dW_pair": int, "dW_odd": int,
    #        "dB": int, "site_tag": str, "coverage": float}
"""
import os, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from compile import setup_project, compile_full, generate_rbf
from config import RBF_DIR
from rbf_diff import diff_rbf_files


def _is_crc_byte(byte_offset: int) -> bool:
    """Per-frame CRC slot (210-byte frames, offsets 208/209)."""
    return (byte_offset - 32) % 210 in (208, 209)


def _nocrc_cram(base_rbf: str, probe_rbf: str) -> list[tuple[int, int]]:
    cells = [(d.byte_offset, d.bit_position)
             for d in diff_rbf_files(base_rbf, probe_rbf)]
    return [c for c in cells
            if c[0] >= 32 + 5282 and not _is_crc_byte(c[0])]


def _compile_probe(harness_mod_name: str, tag: str,
                   overrides: dict[int, int]) -> tuple[str, str | None, str]:
    """Worker: build one probe RBF for harness_mod_name."""
    import importlib
    h = importlib.import_module(harness_mod_name)

    def gen_mif(ov):
        lines = [f"WIDTH = {h.WIDTH};", f"DEPTH = {h.DEPTH};",
                 "ADDRESS_RADIX = HEX;", "DATA_RADIX = HEX;",
                 "CONTENT BEGIN"]
        hex_w = (h.WIDTH + 3) // 4
        for w in range(h.DEPTH):
            v = ov.get(w, 0)
            lines.append(f"  {w:03X} : {v:0{hex_w}X};")
        lines.append("END;")
        return "\n".join(lines) + "\n"

    proj = setup_project(tag, h.gen_verilog(), h.gen_qsf())
    with open(os.path.join(proj, "m9k_init.mif"), "w") as f:
        f.write(gen_mif(overrides))
    with open(os.path.join(proj, f"{tag}.qpf"), "w") as f:
        f.write(f'PROJECT_REVISION = "{tag}"\n')
    ok, elapsed, err = compile_full(tag, proj)
    if not ok:
        return tag, None, err
    out = os.path.join(RBF_DIR, f"{tag}.rbf")
    generate_rbf(tag, proj, out)
    return tag, out, ""


def calibrate_site(
    harness_mod_name: str,
    probe_words: list[int] = (1, 2),
    probe_bits: list[int] = (1, 2, 4),
    workers: int = 6,
) -> dict:
    """Calibrate a 2D M9K init formula for harness_mod_name.

    Runs baseline + probes for (w=0,b=0), each (w∈probe_words, b=0), and
    each (w=0, b∈probe_bits). Fits the linear model from clean
    nocrc-CRAM singletons.

    Returns dict with keys: anchor, bp, dW_pair, dW_odd, dB, site_tag,
    coverage. Raises RuntimeError on fit failure.
    """
    import importlib
    h = importlib.import_module(harness_mod_name)
    width, depth = h.WIDTH, h.DEPTH

    tasks = [("cal_base", {}), ("cal_w0_b0", {0: 1 << 0})]
    for w in probe_words:
        tasks.append((f"cal_w{w}_b0", {w: 1 << 0}))
    for b in probe_bits:
        tasks.append((f"cal_w0_b{b}", {0: 1 << b}))

    prefix = harness_mod_name.replace(".", "_")
    print(f"[{prefix}] dispatching {len(tasks)} compiles across {workers} "
          f"workers")
    t0 = time.time()
    results = {}
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_compile_probe, harness_mod_name,
                          f"{prefix}_{tag}", ov) for tag, ov in tasks]
        for fut in as_completed(futs):
            tag, rbf, err = fut.result()
            key = tag.rsplit("_", 1)[-1] if False else tag.split("_", 2)[-1]
            short = tag[len(prefix) + 1:]
            if rbf is None:
                print(f"  {short}: FAIL {err[:120]}")
                results[short] = None
            else:
                print(f"  {short}: OK")
                results[short] = rbf
    print(f"[{prefix}] sweep wall: {time.time() - t0:.1f}s")

    if any(v is None for v in results.values()):
        raise RuntimeError("probe compilation failed")
    base = results["cal_base"]

    # Extract singletons
    def one(tag):
        cells = _nocrc_cram(base, results[tag])
        if len(cells) != 1:
            raise RuntimeError(
                f"{tag}: expected 1 clean cell, got {len(cells)}: {cells}")
        return cells[0]

    anchor_cell = one("cal_w0_b0")
    anchor, bp = anchor_cell

    # Word axis: byte(w, 0) = anchor + (w//2)*dW_pair + (w%2)*dW_odd
    # Need at least one even-word and one odd-word sample to solve.
    dW_pair = None
    dW_odd = None
    for w in probe_words:
        c = one(f"cal_w{w}_b0")
        if c[1] != bp:
            raise RuntimeError(
                f"w={w} b=0: bp={c[1]} != anchor bp={bp}")
        delta = c[0] - anchor
        if w % 2 == 0 and w > 0:
            # byte = anchor + (w/2)*dW_pair  → dW_pair = delta / (w/2)
            dW_pair = delta // (w // 2)
        elif w % 2 == 1:
            # byte = anchor + (w//2)*dW_pair + dW_odd
            #     when dW_pair known: dW_odd = delta - (w//2)*dW_pair
            pass  # solved in second pass
    if dW_pair is None:
        raise RuntimeError(
            "need at least one even-w>=2 probe to solve dW_pair")
    for w in probe_words:
        if w % 2 == 1:
            c = one(f"cal_w{w}_b0")
            dW_odd = (c[0] - anchor) - (w // 2) * dW_pair
            break
    if dW_odd is None:
        raise RuntimeError("need at least one odd-w probe to solve dW_odd")

    # Bit axis: byte(0, bit) = anchor + bit * dB ; filter bits that
    # landed on the same bp row (others live on a different row).
    dB_candidates = []
    for b in probe_bits:
        cells = _nocrc_cram(base, results[f"cal_w0_b{b}"])
        same_bp = [c for c in cells if c[1] == bp]
        if len(same_bp) == 1:
            dB_candidates.append(((same_bp[0][0] - anchor) // b, b))
    if not dB_candidates:
        raise RuntimeError(
            f"no bit probe landed on bp={bp}: bit axis uses a different row")
    dB = dB_candidates[0][0]
    # Check consistency
    for d, b in dB_candidates[1:]:
        if d != dB:
            raise RuntimeError(
                f"inconsistent dB: {dB_candidates}")

    # Predict all probed cells; report coverage
    hit = 0
    total = 0
    for w in [0] + list(probe_words):
        total += 1
        c = one(f"cal_w{w}_b0")
        pred = (anchor + (w // 2) * dW_pair + (w % 2) * dW_odd, bp)
        if pred == c:
            hit += 1
    for b in probe_bits:
        cells = _nocrc_cram(base, results[f"cal_w0_b{b}"])
        total += 1
        pred = (anchor + b * dB, bp)
        if pred in cells:
            hit += 1
    coverage = hit / total

    site_tag = f"X{getattr(h, 'SITE_X', '?')}_Y{getattr(h, 'SITE_Y', '?')}_N{getattr(h, 'SITE_N', '?')}"
    return {
        "anchor": anchor,
        "bp": bp,
        "dW_pair": dW_pair,
        "dW_odd": dW_odd,
        "dB": dB,
        "site_tag": site_tag,
        "width": width,
        "depth": depth,
        "coverage": coverage,
    }


if __name__ == "__main__":
    harness = sys.argv[1] if len(sys.argv) > 1 else "m9k_led_harness"
    fit = calibrate_site(harness)
    print("\n=== fit ===")
    for k, v in fit.items():
        print(f"  {k}: {v}")
