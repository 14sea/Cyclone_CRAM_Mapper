# SPDX-License-Identifier: GPL-3.0-or-later
# enumerate_ir_configured.tcl — JTAG IR enumeration, CONFIGURED-state
#
# Phase 2a of the JTAG backdoor exploration. Same probe logic as
# enumerate_ir.tcl but starts from IR=START_IR (default 6) instead
# of 0 so we do NOT trigger EXTEST / PULSE_NCONFIG / SAMPLE etc. and
# unconfigure the FPGA mid-scan.
#
# Prereq: flash a known-good stable design first (e.g.
# results/rbf/nv_zero_global.rbf — configured but idle).
#
# Usage:  quartus_stp -t enumerate_ir_configured.tcl [max_dr_bits] [start_ir]
# Output (stdout, one line per IR code):
#   IR <decimal_code> <cap_a_hex> <cap_b_hex>

package require ::quartus::jtag

# --- configuration ---
set MAX_DR 1024
set START_IR 6
if {[llength $argv] >= 1} {
    set MAX_DR [lindex $argv 0]
}
if {[llength $argv] >= 2} {
    set START_IR [lindex $argv 1]
}
set NUM_IR 1024
set HEX_LEN [expr {$MAX_DR / 4}]

set PAT_A [string repeat "A" $HEX_LEN]
set PAT_B [string repeat "5" $HEX_LEN]

# --- open JTAG connection ---
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
puts "# MODE: CONFIGURED-state scan (expects prior FPGA configuration)"
puts "# MAX_DR: $MAX_DR bits ($HEX_LEN hex chars)"
puts "# START_IR: $START_IR (IR 0..[expr {$START_IR - 1}] skipped to avoid state-changing instructions)"

open_device -device_name $dev -hardware_name $hw
device_lock -timeout 10000

# --- verify IDCODE (IR = 6) as sanity check ---
device_ir_shift -ir_value 6 -no_captured_ir_value
set id_raw [device_dr_shift -length 32 -dr_value "00000000" -value_in_hex]
puts "# IDCODE: $id_raw"

# --- enumerate from START_IR to NUM_IR-1 ---
puts "# BEGIN SCAN"
flush stdout

for {set ir $START_IR} {$ir < $NUM_IR} {incr ir} {
    device_ir_shift -ir_value $ir -no_captured_ir_value
    set cap_a [device_dr_shift -length $MAX_DR -dr_value $PAT_A -value_in_hex]
    set cap_b [device_dr_shift -length $MAX_DR -dr_value $PAT_B -value_in_hex]
    puts "IR $ir $cap_a $cap_b"

    if {$ir % 128 == 0} {
        puts "# progress: $ir / $NUM_IR"
    }
    flush stdout
}

# --- restore BYPASS ---
device_ir_shift -ir_value 1023 -no_captured_ir_value
device_dr_shift -length 1 -dr_value "0" -value_in_hex -no_captured_dr_value

device_unlock
close_device
puts "# DONE"
