# SPDX-License-Identifier: GPL-3.0-or-later
# sld_hub_probe.tcl — Altera SLD Hub / Virtual JTAG probe (AN 628)
#
# Phase 2c of the JTAG backdoor exploration. IR 0x00C (USER0) and
# IR 0x00E (USER1) behaved as pure scan-through registers in Phase
# 2a/2b (cap_a XOR cap_b == 0 → no fixed-length DR) — that's the
# Altera Virtual JTAG VIR/VDR pair.
#
# This script talks the SLD Hub Info Register protocol:
#   1. IR -> USER1   : shift VIR = all 1s  (addresses the hub itself)
#   2. IR -> USER0   : shift N bits of 0 out of VDR  → hub_info stream
# The first 32 bits of the stream encode hub version / m (VIR length) /
# manufacturer ID / number of SLD nodes. Each subsequent 32-bit word
# describes one instrument node.
#
# We don't know m (VIR bit-length) a priori; Altera silicon LSB-aligns
# the VIR shift, so overshooting (e.g. 32 bits of 1s) still produces
# an "all-ones" VIR value up to the real m. As a sanity check we also
# drive a few other VIR values and dump the USER0 stream for each.
#
# Prereq: flash a stable configured design first (e.g.
# results/rbf/nv_zero_global.rbf) so USER0/USER1 are populated.
#
# Usage:
#   quartus_stp -t sld_hub_probe.tcl [stream_bits] [vir_bits]
# Defaults: stream_bits=1024 (hub header + up to 31 nodes),
#           vir_bits=32 (overshoot to cover any m ≤ 32)
#
# Output (stdout) — self-describing line format:
#   # ... metadata comments
#   VIR <vir_hex> <stream_hex>
# where <stream_hex> is <stream_bits> hex chars of USER0 capture, MSB
# of the hex string = last bit shifted out = highest bit index.

package require ::quartus::jtag

# --- configuration ---
set IR_USER0 12
set IR_USER1 14
set STREAM_BITS 1024
set VIR_BITS 32
if {[llength $argv] >= 1} {
    set STREAM_BITS [lindex $argv 0]
}
if {[llength $argv] >= 2} {
    set VIR_BITS [lindex $argv 1]
}
set STREAM_HEX_LEN [expr {$STREAM_BITS / 4}]
set VIR_HEX_LEN [expr {$VIR_BITS / 4}]

# VIR values to probe:
#   all-1s        → hub info register
#   0             → often a no-op / idle
#   1..7          → low node addresses (if present)
#   0x5A, 0xA5    → alternating patterns to sanity-check VIR reach
set VIR_HUB_HEX [string repeat "F" $VIR_HEX_LEN]
set VIR_PROBE_LIST [list \
    $VIR_HUB_HEX \
    [format "%0*X" $VIR_HEX_LEN 0] \
    [format "%0*X" $VIR_HEX_LEN 1] \
    [format "%0*X" $VIR_HEX_LEN 2] \
    [format "%0*X" $VIR_HEX_LEN 3] \
    [format "%0*X" $VIR_HEX_LEN 4] \
    [format "%0*X" $VIR_HEX_LEN 5] \
    [format "%0*X" $VIR_HEX_LEN 6] \
    [format "%0*X" $VIR_HEX_LEN 7] \
    [format "%0*X" $VIR_HEX_LEN 90] \
    [format "%0*X" $VIR_HEX_LEN 165] \
]

# --- open JTAG ---
set hw_list [get_hardware_names]
if {[llength $hw_list] == 0} {
    puts "# ERROR: no JTAG hardware found"
    exit 1
}
set hw [lindex $hw_list 0]
puts "# HW: $hw"

set dev_list [get_device_names -hardware_name $hw]
if {[llength $dev_list] == 0} {
    puts "# ERROR: no device on $hw"
    exit 1
}
set dev [lindex $dev_list 0]
puts "# DEV: $dev"
puts "# MODE: SLD HUB PROBE (Phase 2c) — AN 628 Virtual JTAG"
puts "# STREAM_BITS: $STREAM_BITS ($STREAM_HEX_LEN hex chars)"
puts "# VIR_BITS:    $VIR_BITS ($VIR_HEX_LEN hex chars, overshoots actual m)"
puts "# IR_USER0:    0x[format %03X $IR_USER0]"
puts "# IR_USER1:    0x[format %03X $IR_USER1]"

open_device -device_name $dev -hardware_name $hw
device_lock -timeout 10000

# sanity: IDCODE
device_ir_shift -ir_value 6 -no_captured_ir_value
set id_raw [device_dr_shift -length 32 -dr_value "00000000" -value_in_hex]
puts "# IDCODE: $id_raw"

set ZERO_STREAM [string repeat "0" $STREAM_HEX_LEN]

puts "# BEGIN PROBE"
flush stdout

# For each VIR value, address a virtual instrument, then scan its VDR.
foreach vir $VIR_PROBE_LIST {
    # --- load VIR through USER1 ---
    device_ir_shift -ir_value $IR_USER1 -no_captured_ir_value
    device_dr_shift -length $VIR_BITS -dr_value $vir -value_in_hex \
        -no_captured_dr_value

    # --- scan VDR through USER0 ---
    device_ir_shift -ir_value $IR_USER0 -no_captured_ir_value
    set stream [device_dr_shift -length $STREAM_BITS -dr_value $ZERO_STREAM \
                    -value_in_hex]

    puts "VIR $vir $stream"
    flush stdout
}

# --- restore BYPASS ---
device_ir_shift -ir_value 1023 -no_captured_ir_value
device_dr_shift -length 1 -dr_value "0" -value_in_hex -no_captured_dr_value

device_unlock
close_device
puts "# DONE"
