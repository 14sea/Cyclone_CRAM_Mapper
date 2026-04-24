# SPDX-License-Identifier: GPL-3.0-or-later
"""Capture UART output for a fixed window after flash.

Timestamps each chunk and writes both a hex-escaped log and the raw
bytes so callers can diff against a reference capture. The baud rate
MUST be supplied explicitly — NEORV32 bootloader is 19200, PL2303 Linux
runtime is 115200, and silently defaulting to the wrong one wastes a
flash cycle.
"""
import argparse, sys, time
from pathlib import Path
import serial


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--baud", type=int, required=True,
                    help="UART baud (no default — NEORV32=19200, PL2303 Linux=115200)")
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--out", type=Path, default=Path("tmp/neorv32_zeta/uart_log.txt"))
    ap.add_argument("--raw", type=Path, default=Path("tmp/neorv32_zeta/uart_raw.bin"))
    a = ap.parse_args()

    a.out.parent.mkdir(parents=True, exist_ok=True)
    s = serial.Serial(a.port, a.baud, timeout=0.2)
    s.reset_input_buffer()

    t0 = time.time()
    deadline = t0 + a.seconds
    raw = bytearray()
    log_lines = []
    print(f"[{0:6.2f}] observing {a.port} @ {a.baud} for {a.seconds:.1f}s...", flush=True)
    while time.time() < deadline:
        chunk = s.read(4096)
        if not chunk:
            continue
        t = time.time() - t0
        raw.extend(chunk)
        try:
            txt = chunk.decode("utf-8", errors="replace")
        except Exception:
            txt = repr(chunk)
        line = f"[{t:6.2f}] {len(chunk):4d}B  {txt!r}"
        log_lines.append(line)
        print(line, flush=True)
    s.close()

    a.raw.write_bytes(bytes(raw))
    a.out.write_text("\n".join(log_lines) + "\n")
    print(f"\nwrote {a.out}  ({len(log_lines)} chunks, {len(raw)} B raw)")
    print(f"wrote {a.raw}")

    if not raw:
        print("NO UART BYTES RECEIVED in window", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
