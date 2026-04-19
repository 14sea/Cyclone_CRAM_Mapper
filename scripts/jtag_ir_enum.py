# SPDX-License-Identifier: GPL-3.0-or-later
"""JTAG IR enumeration for Cyclone IV EP4CE6 via USB-Blaster.

Scans all 1024 possible 10-bit IR codes, measures the DR chain length
for each, and identifies undocumented instructions.  Any IR code whose
DR length differs from the BYPASS default (1-bit) is potentially an
undocumented feature — especially codes whose DR length matches CRAM
frame width or M9K addressing.

SAFETY MODEL:
  Phase 1 (default): Read-only scan.  DR length measurement exits via
      Test-Logic-Reset (5×TMS=1) instead of Update-DR, so shifted
      marker bits are NEVER latched into the actual register.
  Phase 2 (--deep):  Reads DR capture value and tests write-readback.
      DANGEROUS — only use with --ir-only on a known-safe sandbox
      design.  Never run --deep on a full scan.

Requires: pyusb  (pip install pyusb)
          libusb (sudo apt install libusb-1.0-0-dev)
Hardware: Altera USB-Blaster connected to Cyclone IV JTAG header

Usage:
    # Phase 1.1 — safe blind scan (map all DR lengths)
    sudo python3 scripts/jtag_ir_enum.py --output results/jtag_ir_scan.json

    # Phase 1.2 — analyze JSON, identify suspects with DR > 32

    # Phase 1.3 — targeted deep probe (sandbox design loaded!)
    sudo python3 scripts/jtag_ir_enum.py --ir-only 0x0XX --deep
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

try:
    import usb.core
    import usb.util
except ImportError:
    print("ERROR: pyusb not installed.  Run:  pip install pyusb")
    print("       Also needs libusb:  sudo apt install libusb-1.0-0-dev")
    sys.exit(1)


# ── USB-Blaster constants ──────────────────────────────────────────

VENDOR_ID = 0x09FB
PRODUCT_IDS = [0x6001, 0x6810, 0x6010]  # Blaster I, II, clones
EP_OUT = 0x02
EP_IN = 0x81

# Bit-bang byte format (bit 6 = 1 selects bit-bang mode)
BB_MODE = 0x40   # bit 6
BB_READ = 0x80   # bit 7: request TDO readback
BB_TCK  = 0x10   # bit 4: pulse TCK
BB_TMS  = 0x20   # bit 5: TMS value
BB_TDI  = 0x01   # bit 0: TDI value
BB_LED  = 0x02   # bit 1: LED (active low)


# ── Known Cyclone IV JTAG instructions (10-bit IR) ─────────────────

KNOWN_IR = {
    0x001: ("SAMPLE_PRELOAD", "Boundary scan sample/preload"),
    0x002: ("EXTEST",         "Boundary scan external test"),
    0x004: ("PROGRAM",        "Enter programming mode"),
    0x005: ("STARTUP",        "Release from programming"),
    0x006: ("IDCODE",         "Read 32-bit device ID"),
    0x007: ("PULSE_NCONFIG",  "Trigger reconfiguration"),
    0x00A: ("USERCODE",       "Read 32-bit user code"),
    0x00C: ("CONFIG_IO",      "Configuration I/O access"),
    0x00E: ("HIGHZ",          "Tri-state all I/O"),
    0x00F: ("CLAMP",          "Clamp I/O to current state"),
    0x3FF: ("BYPASS",         "1-bit bypass register (default)"),
}

# DR lengths with special significance for Cyclone IV
INTERESTING_DR = {
    1:    "BYPASS (standard)",
    32:   "IDCODE/USERCODE/general config",
    # Cyclone IV CRAM: 210 bytes/frame × 8 = 1680 bits
    1680: "*** CRAM FRAME WIDTH (210 bytes) ***",
    1681: "*** CRAM FRAME + 1 (addr bit?) ***",
    # M9K: 9 bits × 512 = 4608 bits per block
    4608: "*** M9K BLOCK (9×512) ***",
    # Configuration frame addressing
    11:   "Frame address? (1752 frames needs 11 bits)",
    # SRAM-based config
    16:   "Possible 16-bit config register",
    8:    "Possible 8-bit config register",
}

# EP4CE6 expected IDCODE
EP4CE6_IDCODE = 0x020F10DD


# ── USB-Blaster driver ─────────────────────────────────────────────

class USBBlaster:
    """Low-level USB-Blaster JTAG bit-bang interface."""

    def __init__(self):
        self.dev = None
        self._write_buf = bytearray()

    def open(self):
        for pid in PRODUCT_IDS:
            self.dev = usb.core.find(idVendor=VENDOR_ID, idProduct=pid)
            if self.dev is not None:
                break
        if self.dev is None:
            raise RuntimeError(
                "USB-Blaster not found. Check connection and permissions.\n"
                "  Try: sudo chmod 666 /dev/bus/usb/$(lsusb | grep 09fb | "
                "awk '{print $2\"/\"$4}' | tr -d ':')")
        try:
            if self.dev.is_kernel_driver_active(0):
                self.dev.detach_kernel_driver(0)
        except (usb.core.USBError, NotImplementedError):
            pass
        self.dev.set_configuration()
        self.dev.reset()
        time.sleep(0.1)
        return self

    def close(self):
        if self.dev:
            usb.util.dispose_resources(self.dev)
            self.dev = None

    def _bb_byte(self, tms, tdi, read=False):
        """Construct a bit-bang byte for one TCK pulse."""
        b = BB_MODE | BB_TCK | BB_LED
        if tms:
            b |= BB_TMS
        if tdi:
            b |= BB_TDI
        if read:
            b |= BB_READ
        return b

    def _flush(self):
        if self._write_buf:
            self.dev.write(EP_OUT, bytes(self._write_buf))
            self._write_buf.clear()

    def clock_tms(self, tms_bits, n):
        """Clock n bits of TMS with TDI=0, no readback."""
        for i in range(n):
            tms = (tms_bits >> i) & 1
            self._write_buf.append(self._bb_byte(tms, 0))
        if len(self._write_buf) >= 60:
            self._flush()

    def shift_bits(self, tdi_bits, n, read=True, exit_tms=True):
        """Shift n bits through TDI, optionally reading TDO.

        If exit_tms=True, the last bit is clocked with TMS=1
        to exit Shift-IR/DR → Exit1-IR/DR.

        Returns list of TDO bits (LSB first) if read=True.
        """
        self._flush()
        tdo_bits = []

        for i in range(n):
            tdi = (tdi_bits >> i) & 1
            last = (i == n - 1) and exit_tms
            b = self._bb_byte(tms=last, tdi=tdi, read=read)
            self.dev.write(EP_OUT, bytes([b]))
            if read:
                try:
                    resp = self.dev.read(EP_IN, 2, timeout=100)
                    tdo_bits.append(resp[0] & 1 if len(resp) > 0 else 0)
                except usb.core.USBTimeoutError:
                    tdo_bits.append(0)

        return tdo_bits if read else []

    def shift_bits_fast(self, tdi_bits, n, exit_tms=True):
        """Shift n bits without reading — faster for IR loading."""
        for i in range(n):
            tdi = (tdi_bits >> i) & 1
            last = (i == n - 1) and exit_tms
            self._write_buf.append(self._bb_byte(tms=last, tdi=tdi, read=False))
        self._flush()


# ── JTAG TAP controller ───────────────────────────────────────────

class JTAGController:
    """JTAG TAP state machine navigation and scan operations.

    SAFETY: all scan operations default to aborting via
    Test-Logic-Reset (5×TMS=1) instead of Update-DR/IR, so
    shifted data is never latched unless explicitly requested.
    """

    def __init__(self, blaster: USBBlaster, ir_width: int = 10):
        self.blaster = blaster
        self.ir_width = ir_width

    def reset(self):
        """Navigate to Test-Logic-Reset (5× TMS=1)."""
        self.blaster.clock_tms(0x1F, 5)
        self.blaster._flush()

    def idle(self):
        """Navigate TLR → Run-Test-Idle."""
        self.blaster.clock_tms(0, 1)  # TMS=0
        self.blaster._flush()

    def _abort_to_idle(self):
        """Abort from any state → TLR → RTI without Update-DR/IR.

        5×TMS=1 guarantees TLR from any state.  Then TMS=0 → RTI.
        This is the SAFE exit: shifted data is discarded.
        """
        self.blaster.clock_tms(0x1F, 5)  # → TLR
        self.blaster.clock_tms(0x00, 1)   # → RTI
        self.blaster._flush()

    def shift_ir(self, ir_value, commit=True):
        """Load an IR value.

        If commit=True (default), goes through Update-IR to latch
        the new instruction — this IS required for IR to take effect.
        If commit=False, aborts via TLR (IR is not loaded).
        """
        # RTI → Select-DR-Scan → Select-IR-Scan
        self.blaster.clock_tms(0x03, 2)  # TMS=1,1
        # → Capture-IR → Shift-IR
        self.blaster.clock_tms(0x00, 2)  # TMS=0,0
        self.blaster._flush()
        # Shift IR data (LSB first), last bit with TMS=1 → Exit1-IR
        self.blaster.shift_bits_fast(ir_value, self.ir_width, exit_tms=True)

        if commit:
            # Exit1-IR → Update-IR → RTI  (latch the instruction)
            self.blaster.clock_tms(0x01, 2)  # TMS=1, then 0
            self.blaster._flush()
        else:
            self._abort_to_idle()

    def measure_dr_length(self, max_len=2048):
        """Measure DR chain length by shifting a marker bit.

        SAFE: exits via TLR (not Update-DR), so the marker bits
        shifted in are NEVER latched into the actual register.

        Technique: shift a 1 followed by 0s.  Count clocks until
        the 1 appears on TDO = DR chain length.
        """
        # RTI → Select-DR-Scan
        self.blaster.clock_tms(0x01, 1)  # TMS=1
        # → Capture-DR → Shift-DR
        self.blaster.clock_tms(0x00, 2)  # TMS=0,0
        self.blaster._flush()

        # Shift a 1-bit marker, then 0s, reading TDO each clock
        tdo = self.blaster.shift_bits(1, 1, read=True, exit_tms=False)
        dr_len = 0

        if tdo and tdo[0] == 1:
            # Marker came out immediately — could be capture value
            # containing a 1.  Keep shifting to disambiguate.
            pass

        for i in range(max_len):
            tdo = self.blaster.shift_bits(0, 1, read=True, exit_tms=False)
            if tdo and tdo[0] == 1:
                dr_len = i + 1
                break
        else:
            dr_len = -1  # chain longer than max_len

        # SAFE EXIT: abort via TLR — do NOT go through Update-DR
        # This discards the shifted marker bits.
        self._abort_to_idle()

        return dr_len

    def read_dr_safe(self, length):
        """Read DR capture value WITHOUT latching via Update-DR.

        Enters Capture-DR (device loads current value into shift
        register), shifts it out reading TDO, then aborts via TLR.
        The all-zeros shifted in are never latched.
        """
        # RTI → Select-DR-Scan → Capture-DR → Shift-DR
        self.blaster.clock_tms(0x01, 1)  # TMS=1
        self.blaster.clock_tms(0x00, 2)  # TMS=0,0
        self.blaster._flush()

        tdo = self.blaster.shift_bits(0, length, read=True, exit_tms=False)

        # SAFE EXIT: abort via TLR — shifted zeros not latched
        self._abort_to_idle()

        value = 0
        for i, bit in enumerate(tdo):
            value |= (bit << i)
        return value

    def write_dr_committed(self, value, length):
        """Write to DR and LATCH via Update-DR.

        ⚠️  DANGEROUS — the written value takes effect in hardware.
        Only call this on known-safe registers with a sandbox design.
        """
        # RTI → Select-DR-Scan → Capture-DR → Shift-DR
        self.blaster.clock_tms(0x01, 1)
        self.blaster.clock_tms(0x00, 2)
        self.blaster._flush()

        # Shift data, last bit exits to Exit1-DR
        self.blaster.shift_bits_fast(value, length, exit_tms=True)

        # Exit1-DR → Update-DR → RTI  (LATCH!)
        self.blaster.clock_tms(0x01, 2)
        self.blaster._flush()

    def read_idcode(self):
        """Read IDCODE via standard IR=0x006 (safe — IDCODE is read-only)."""
        self.shift_ir(0x006)
        return self.read_dr_safe(32)


# ── IR enumeration engine ─────────────────────────────────────────

def enumerate_ir(jtag: JTAGController, ir_width: int = 10,
                 ir_only=None, max_dr=2048, verbose=True):
    """Enumerate all IR codes and measure DR lengths.

    SAFE: uses measure_dr_length which aborts via TLR.
    No DR data is ever latched during enumeration.
    """
    results = {}
    n_codes = 1 << ir_width
    codes = [ir_only] if ir_only is not None else range(n_codes)
    total = len(codes) if ir_only is None else 1

    # Verify JTAG connection via IDCODE
    jtag.reset()
    jtag.idle()
    idcode = jtag.read_idcode()

    if verbose:
        print(f"Device IDCODE: 0x{idcode:08X}")
        if idcode == EP4CE6_IDCODE:
            print("  → EP4CE6F17C8 confirmed")
        elif idcode == 0x00000000 or idcode == 0xFFFFFFFF:
            print("  → WARNING: no device detected (check JTAG connection)")
            return results
        else:
            print(f"  → Unknown device (expected 0x{EP4CE6_IDCODE:08X})")

    # Measure BYPASS DR length as baseline
    jtag.reset()
    jtag.idle()
    jtag.shift_ir(0x3FF)  # BYPASS
    bypass_len = jtag.measure_dr_length(max_dr)
    if verbose:
        print(f"BYPASS DR length: {bypass_len} (expected 1)")
        print(f"\nScanning {total} IR codes (IR width={ir_width})...")
        print(f"Safety: DR length measurement via TLR abort "
              f"(no Update-DR latch)\n")

    non_bypass = []
    t0 = time.time()

    for idx, ir_code in enumerate(codes):
        jtag.reset()
        jtag.idle()
        jtag.shift_ir(ir_code)
        dr_len = jtag.measure_dr_length(max_dr)

        known = KNOWN_IR.get(ir_code)
        name = known[0] if known else ""
        desc = known[1] if known else ""

        entry = {
            "ir_code": ir_code,
            "ir_hex": f"0x{ir_code:03X}",
            "ir_bin": f"0b{ir_code:0{ir_width}b}",
            "dr_length": dr_len,
            "name": name,
            "description": desc,
            "is_bypass": (dr_len == bypass_len),
        }

        if dr_len in INTERESTING_DR:
            entry["note"] = INTERESTING_DR[dr_len]
        elif dr_len > 1 and dr_len != bypass_len:
            entry["note"] = f"NON-BYPASS DR={dr_len} — INVESTIGATE"

        results[ir_code] = entry

        if dr_len != bypass_len:
            non_bypass.append(entry)
            if verbose:
                flag = " *** UNDOCUMENTED ***" if not name else ""
                note = entry.get("note", "")
                print(f"  IR=0x{ir_code:03X} ({ir_code:0{ir_width}b})"
                      f"  DR={dr_len:5d}  {name:20s}{flag}"
                      f"  {note}")

        if verbose and (idx + 1) % 128 == 0:
            elapsed = time.time() - t0
            pct = (idx + 1) / total * 100
            print(f"  ... {idx+1}/{total} ({pct:.0f}%) "
                  f"  {elapsed:.0f}s elapsed  "
                  f"  {len(non_bypass)} non-bypass found")

    elapsed = time.time() - t0

    if verbose:
        print(f"\n{'='*60}")
        print(f"Scan complete in {elapsed:.1f}s")
        print(f"Total IR codes: {total}")
        print(f"Non-bypass: {len(non_bypass)}")
        print(f"Known: {sum(1 for e in non_bypass if e['name'])}")
        print(f"UNDOCUMENTED: {sum(1 for e in non_bypass if not e['name'])}")

        if non_bypass:
            print(f"\n{'='*60}")
            print("ALL NON-BYPASS INSTRUCTIONS:")
            print(f"{'IR':>7s}  {'Binary':>12s}  {'DR len':>6s}  "
                  f"{'Name':20s}  Note")
            print("-" * 75)
            for e in sorted(non_bypass, key=lambda x: x["ir_code"]):
                flag = "UNDOCUMENTED" if not e["name"] else ""
                note = e.get("note", flag)
                print(f"  0x{e['ir_code']:03X}  "
                      f"{e['ir_bin']:>12s}  "
                      f"{e['dr_length']:5d}   "
                      f"{e['name']:20s}  {note}")

        cram_candidates = [e for e in non_bypass
                           if not e["name"]
                           and e["dr_length"] > 32
                           and e["dr_length"] != bypass_len]
        if cram_candidates:
            print(f"\n{'='*60}")
            print("HIGH-INTEREST UNDOCUMENTED (DR > 32 bits):")
            for e in sorted(cram_candidates,
                            key=lambda x: x["dr_length"], reverse=True):
                print(f"  IR=0x{e['ir_code']:03X}  DR={e['dr_length']}  "
                      f"({e['dr_length']//8} bytes, "
                      f"{e['dr_length']/1680:.2f} CRAM frames)")

    return results


# ── Deep probe (Phase 1.3 — DANGEROUS, targeted use only) ────────

def deep_probe(jtag: JTAGController, ir_code: int, dr_length: int,
               verbose=True):
    """Deep-probe a single IR code: read capture value, test write-readback.

    ⚠️  DANGEROUS — writes to DR and latches via Update-DR.
    Only use on a specific --ir-only target with a sandbox design loaded.

    Returns dict with capture value, readback, and writability.
    """
    if dr_length <= 0 or dr_length > 4096:
        print(f"  Skipping: DR length {dr_length} out of range")
        return None

    hex_len = (dr_length + 3) // 4

    # Step 1: Read capture value (SAFE — uses TLR abort)
    if verbose:
        print(f"\n  Step 1: Reading DR capture value (safe, no latch)...")
    jtag.reset()
    jtag.idle()
    jtag.shift_ir(ir_code)
    capture = jtag.read_dr_safe(dr_length)

    if verbose:
        print(f"  Capture value: 0x{capture:0{hex_len}X}")
        if dr_length > 64:
            lo = capture & ((1 << 64) - 1)
            hi = (capture >> (dr_length - 64)) & ((1 << 64) - 1)
            print(f"    Low  64 bits: 0x{lo:016X}")
            print(f"    High 64 bits: 0x{hi:016X}")
        popcount = bin(capture).count('1')
        print(f"    Popcount: {popcount}/{dr_length} "
              f"({popcount/dr_length*100:.1f}% ones)")

    # Step 2: Write all-1s and read back (DANGEROUS — latches via Update-DR)
    if verbose:
        print(f"\n  Step 2: Write-readback test (DANGEROUS — Update-DR latch)")
        print(f"    Writing {dr_length} ones...")

    jtag.reset()
    jtag.idle()
    jtag.shift_ir(ir_code)
    all_ones = (1 << dr_length) - 1
    jtag.write_dr_committed(all_ones, dr_length)

    # Read back
    jtag.reset()
    jtag.idle()
    jtag.shift_ir(ir_code)
    readback = jtag.read_dr_safe(dr_length)

    writable = capture != readback
    if verbose:
        print(f"    Readback:  0x{readback:0{hex_len}X}")
        if writable:
            diff = capture ^ readback
            changed = bin(diff).count('1')
            print(f"    ⚠️  STATE CHANGED — {changed}/{dr_length} bits flipped")
        else:
            print(f"    No change (read-only or captured reset value)")

    # Step 3: Restore — write back original capture value
    if writable and verbose:
        print(f"\n  Step 3: Restoring original capture value...")
    if writable:
        jtag.reset()
        jtag.idle()
        jtag.shift_ir(ir_code)
        jtag.write_dr_committed(capture, dr_length)

        # Verify restore
        jtag.reset()
        jtag.idle()
        jtag.shift_ir(ir_code)
        verify = jtag.read_dr_safe(dr_length)
        restored = (verify == capture)
        if verbose:
            if restored:
                print(f"    Restored successfully")
            else:
                print(f"    ⚠️  RESTORE FAILED — value: 0x{verify:0{hex_len}X}")

    return {
        "ir_code": ir_code,
        "ir_hex": f"0x{ir_code:03X}",
        "dr_length": dr_length,
        "capture_hex": f"0x{capture:0{hex_len}X}",
        "readback_hex": f"0x{readback:0{hex_len}X}",
        "writable": writable,
        "bits_changed": bin(capture ^ readback).count('1') if writable else 0,
    }


# ── Main ───────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Enumerate Cyclone IV JTAG IR codes via USB-Blaster",
        epilog="""
SAFETY SOP:
  Phase 1.1: sudo python3 scripts/jtag_ir_enum.py --output results/jtag_ir_scan.json
             (safe blind scan — DR length only, no latch)
  Phase 1.2: Inspect JSON, identify suspects with DR > 32 bits
  Phase 1.3: Load sandbox design, then:
             sudo python3 scripts/jtag_ir_enum.py --ir-only 0xXXX --deep
             (targeted probe with write-readback — DANGEROUS)
""",
        formatter_class=argparse.RawDescriptionHelpFormatter)

    ap.add_argument("--ir-width", type=int, default=10,
                    help="IR register width in bits (default: 10)")
    ap.add_argument("--ir-only", type=str, default=None,
                    help="Probe a single IR code (hex, e.g. 0x006)")
    ap.add_argument("--max-dr", type=int, default=2048,
                    help="Max DR length to measure (default: 2048)")
    ap.add_argument("--deep", action="store_true",
                    help="⚠️  Deep-probe: write-readback test on DR. "
                         "Requires --ir-only. Dangerous on unknown registers.")
    ap.add_argument("--output", type=str, default=None,
                    help="Write results to JSON file")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    # Safety gate: --deep requires --ir-only
    if args.deep and not args.ir_only:
        print("ERROR: --deep requires --ir-only to target a specific IR code.")
        print("       Never run --deep on a full scan. See --help for SOP.")
        return 1

    ir_only = int(args.ir_only, 0) if args.ir_only else None

    print("Connecting to USB-Blaster...")
    blaster = USBBlaster()
    try:
        blaster.open()
    except RuntimeError as e:
        print(f"ERROR: {e}")
        return 1
    print("  Connected.\n")

    jtag = JTAGController(blaster, ir_width=args.ir_width)

    try:
        # Phase 1.1: Safe enumeration
        results = enumerate_ir(
            jtag,
            ir_width=args.ir_width,
            ir_only=ir_only,
            max_dr=args.max_dr,
            verbose=not args.quiet,
        )

        # Phase 1.3: Deep probe (only with --ir-only --deep)
        probe_result = None
        if args.deep and ir_only is not None:
            entry = results.get(ir_only)
            if entry and not entry["is_bypass"]:
                print(f"\n{'='*60}")
                print(f"⚠️  DEEP PROBE: IR=0x{ir_only:03X} "
                      f"(DR={entry['dr_length']} bits)")
                print(f"    This WRITES to the DR register via Update-DR.")
                print(f"    Ensure a safe sandbox design is loaded!")
                print(f"{'='*60}")
                probe_result = deep_probe(
                    jtag, ir_only, entry["dr_length"],
                    verbose=not args.quiet)
            elif entry:
                print(f"\nIR=0x{ir_only:03X} is BYPASS — nothing to probe.")

        # Save results
        if args.output:
            out = {
                "scan_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "ir_width": args.ir_width,
                "safety": "TLR-abort (no Update-DR latch during scan)",
                "instructions": {
                    f"0x{k:03X}": v for k, v in results.items()
                },
            }
            if probe_result:
                out["deep_probe"] = probe_result
            Path(args.output).write_text(
                json.dumps(out, indent=2, default=str))
            print(f"\nResults saved to {args.output}")

    finally:
        jtag.reset()
        blaster.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
