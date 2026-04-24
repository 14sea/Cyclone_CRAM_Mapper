# SPDX-License-Identifier: GPL-3.0-or-later
"""Region-aware diff between two EP4CE6 RBFs.

Splits each 368 011-byte bitstream into preamble (32 B) + 1752 frames of
210 B (208 data + 2 CRC) + postamble (59 B), then reports per-region byte
and bit differences. The intent is "what actually changed between two
Quartus builds?" — a raw `cmp -l` is dominated by CRC churn whenever any
data byte flips, which makes the output useless for human review.

Header-band frames (0..24) are reported separately from fabric frames
(25..1751): header is the 4-5-bit noise floor region documented in CLAUDE.md.
CRC bytes are the last two bytes of every frame ≥25.

Usage:
    python3 scripts/bit_workaround/zeta_rbf_diff.py A.rbf B.rbf
    python3 scripts/bit_workaround/zeta_rbf_diff.py A.rbf B.rbf --json out.json
    python3 scripts/bit_workaround/zeta_rbf_diff.py A.rbf B.rbf --top-frames 20
"""
import argparse
import json
import sys
from pathlib import Path

RBF_SIZE = 368011
PREAMBLE = 32
POSTAMBLE = 59
FRAME_SIZE = 210
FRAME_DATA = 208
FRAME_CRC = 2
N_FRAMES = 1752
HEADER_FRAMES = 25  # frames 0..24 are header band


def popcount(x: int) -> int:
    return bin(x).count("1")


def categorize(a: bytes, b: bytes) -> dict:
    """Walk both RBFs once, bucket byte/bit diffs by region."""
    if len(a) != RBF_SIZE or len(b) != RBF_SIZE:
        raise ValueError(f"RBFs must be {RBF_SIZE} B; got {len(a)}/{len(b)}")

    # byte counts
    pre_bytes = 0; pre_bits = 0
    hdr_data_bytes = 0; hdr_data_bits = 0
    hdr_crc_bytes = 0; hdr_crc_bits = 0
    fab_data_bytes = 0; fab_data_bits = 0
    fab_crc_bytes = 0; fab_crc_bits = 0
    post_bytes = 0; post_bits = 0

    # frame histogram: frame_index -> (data_byte_diffs, crc_byte_diffs)
    frame_hist: dict[int, tuple[int, int]] = {}

    for i in range(RBF_SIZE):
        x = a[i] ^ b[i]
        if not x:
            continue
        bits = popcount(x)

        if i < PREAMBLE:
            pre_bytes += 1; pre_bits += bits
            continue

        post_start = PREAMBLE + N_FRAMES * FRAME_SIZE
        if i >= post_start:
            post_bytes += 1; post_bits += bits
            continue

        rel = i - PREAMBLE
        frame = rel // FRAME_SIZE
        pos = rel % FRAME_SIZE
        is_crc = (pos >= FRAME_DATA)
        is_hdr = (frame < HEADER_FRAMES)

        d_prev, c_prev = frame_hist.get(frame, (0, 0))
        if is_crc:
            frame_hist[frame] = (d_prev, c_prev + 1)
            if is_hdr:
                hdr_crc_bytes += 1; hdr_crc_bits += bits
            else:
                fab_crc_bytes += 1; fab_crc_bits += bits
        else:
            frame_hist[frame] = (d_prev + 1, c_prev)
            if is_hdr:
                hdr_data_bytes += 1; hdr_data_bits += bits
            else:
                fab_data_bytes += 1; fab_data_bits += bits

    # Frames touched — split hdr vs fab for clarity
    hdr_frames = sum(1 for f in frame_hist if f < HEADER_FRAMES)
    fab_frames = sum(1 for f in frame_hist if f >= HEADER_FRAMES)

    total_bytes = (pre_bytes + hdr_data_bytes + hdr_crc_bytes +
                   fab_data_bytes + fab_crc_bytes + post_bytes)
    total_bits = (pre_bits + hdr_data_bits + hdr_crc_bits +
                  fab_data_bits + fab_crc_bits + post_bits)

    return {
        "total": {"bytes": total_bytes, "bits": total_bits},
        "preamble": {"bytes": pre_bytes, "bits": pre_bits, "size": PREAMBLE},
        "header_data": {"bytes": hdr_data_bytes, "bits": hdr_data_bits,
                         "size": HEADER_FRAMES * FRAME_DATA},
        "header_crc":  {"bytes": hdr_crc_bytes,  "bits": hdr_crc_bits,
                         "size": HEADER_FRAMES * FRAME_CRC},
        "fabric_data": {"bytes": fab_data_bytes, "bits": fab_data_bits,
                         "size": (N_FRAMES - HEADER_FRAMES) * FRAME_DATA},
        "fabric_crc":  {"bytes": fab_crc_bytes,  "bits": fab_crc_bits,
                         "size": (N_FRAMES - HEADER_FRAMES) * FRAME_CRC},
        "postamble": {"bytes": post_bytes, "bits": post_bits, "size": POSTAMBLE},
        "frames_touched": {"header": hdr_frames, "fabric": fab_frames,
                            "total": len(frame_hist)},
        "frame_hist": frame_hist,
    }


def print_report(rep: dict, top_frames: int):
    """Human-readable summary. No emojis, aligned columns."""
    print(f"total:        {rep['total']['bytes']:>7} bytes   {rep['total']['bits']:>8} bits")
    print(f"-- by region -------------------------------------------------")
    for name in ("preamble", "header_data", "header_crc",
                 "fabric_data", "fabric_crc", "postamble"):
        r = rep[name]
        pct = (100.0 * r["bytes"] / r["size"]) if r["size"] else 0.0
        print(f"  {name:<13} {r['bytes']:>7} / {r['size']:<6} B  "
              f"({pct:5.2f}%)   {r['bits']:>8} bits")
    ft = rep["frames_touched"]
    print(f"-- frames touched: {ft['total']} ({ft['header']} hdr, {ft['fabric']} fab) of {N_FRAMES}")

    if top_frames > 0 and rep["frame_hist"]:
        ranked = sorted(rep["frame_hist"].items(),
                        key=lambda kv: kv[1][0] + kv[1][1], reverse=True)
        print(f"-- top {min(top_frames, len(ranked))} frames by byte-diff count:")
        print(f"  {'frame':>6}  {'data':>5}  {'crc':>3}  region")
        for fr, (d, c) in ranked[:top_frames]:
            region = "hdr" if fr < HEADER_FRAMES else "fab"
            print(f"  {fr:>6}  {d:>5}  {c:>3}  {region}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a", type=Path)
    ap.add_argument("b", type=Path)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--top-frames", type=int, default=0,
                    help="show top-N frames by byte-diff count (0 = off)")
    args = ap.parse_args()

    a = args.a.read_bytes()
    b = args.b.read_bytes()
    if len(a) != RBF_SIZE or len(b) != RBF_SIZE:
        sys.exit(f"both inputs must be {RBF_SIZE} B EP4CE6 RBFs "
                 f"(got {len(a)}, {len(b)})")

    rep = categorize(a, b)
    print(f"A: {args.a}  ({len(a)} B)")
    print(f"B: {args.b}  ({len(b)} B)")
    print()
    print_report(rep, args.top_frames)

    if args.json:
        # JSON-friendly: frame_hist keys must be strings
        out = dict(rep)
        out["frame_hist"] = {str(k): list(v) for k, v in rep["frame_hist"].items()}
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(out, indent=2) + "\n")
        print(f"\nwrote {args.json}")

    sys.exit(0 if rep["total"]["bytes"] == 0 else 1)


if __name__ == "__main__":
    main()
