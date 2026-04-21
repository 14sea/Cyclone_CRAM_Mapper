# SPDX-License-Identifier: GPL-3.0-or-later
# enumerate_ir.tcl — brute-force JTAG IR enumeration for Cyclone IV
#
# Scans all 1024 possible 10-bit IR codes, probes DR length for each
# by shifting complementary patterns (0xAAA... / 0x555...) and
# capturing TDO output.  DR length = position of first set bit in the
# XOR of the two captures.
#
# Usage:  quartus_stp -t enumerate_ir.tcl [max_dr_bits]
#
# Output (stdout, one line per IR code):
#   IR <decimal_code> <cap_a_hex> <cap_b_hex>
# Lines starting with # are comments / progress.

package require ::quartus::jtag

# --- configuration ---
set MAX_DR 1024
if {[llength $argv] > 0} {
    set MAX_DR [lindex $argv 0]
}
set NUM_IR 1024
set HEX_LEN [expr {$MAX_DR / 4}]

# complementary bit patterns for DR length detection
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
puts "# MAX_DR: $MAX_DR bits ($HEX_LEN hex chars)"

open_device -device_name $dev -hardware_name $hw
device_lock -timeout 10000

# --- verify IDCODE (IR = 6) ---
device_ir_shift -ir_value 6 -no_captured_ir_value
set id_raw [device_dr_shift -length 32 -dr_value "00000000" -value_in_hex]
puts "# IDCODE: $id_raw"

# --- enumerate all IR codes ---
puts "# BEGIN SCAN"
flush stdout

for {set ir 0} {$ir < $NUM_IR} {incr ir} {
    # shift target IR
    device_ir_shift -ir_value $ir -no_captured_ir_value

    # shift pattern A, capture
    set cap_a [device_dr_shift -length $MAX_DR -dr_value $PAT_A -value_in_hex]

    # shift pattern B (complement), capture
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
