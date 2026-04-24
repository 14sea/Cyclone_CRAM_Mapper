# SPDX-License-Identifier: GPL-3.0-or-later
# sld_hub_probe_v2.tcl — variants of the hub-info sequence
# Phase 2c follow-up: the single-shot probe returned all-0 on a design
# known to contain an SLD hub (sld_smoke). Try 6 variants of the
# hub-addressing sequence + shift-length to find which one produces a
# valid Altera hub header (mfg_id = 0x06E at bits [18:8]).

package require ::quartus::jtag

set IR_USER0 12
set IR_USER1 14

set hw [lindex [get_hardware_names] 0]
set dev [lindex [get_device_names -hardware_name $hw] 0]
puts "# HW: $hw"
puts "# DEV: $dev"

open_device -device_name $dev -hardware_name $hw
device_lock -timeout 10000

device_ir_shift -ir_value 6 -no_captured_ir_value
puts "# IDCODE: [device_dr_shift -length 32 -dr_value 00000000 -value_in_hex]"

proc hex_zeros {bits} { return [string repeat "0" [expr {$bits / 4}]] }
proc hex_ones  {bits} { return [string repeat "F" [expr {$bits / 4}]] }

# TAP reset between variants: BYPASS IR, 1-bit DR
proc tap_idle {} {
    device_ir_shift -ir_value 1023 -no_captured_ir_value
    device_dr_shift -length 1 -dr_value 0 -value_in_hex \
        -no_captured_dr_value
}

# === variant A: baseline (what we already tried) ===
# USER1 DR=32x1, USER0 DR=256 (capture)
proc variant_A {} {
    global IR_USER0 IR_USER1
    device_ir_shift -ir_value $IR_USER1 -no_captured_ir_value
    device_dr_shift -length 32 -dr_value [hex_ones 32] -value_in_hex \
        -no_captured_dr_value
    device_ir_shift -ir_value $IR_USER0 -no_captured_ir_value
    return [device_dr_shift -length 256 -dr_value [hex_zeros 256] \
                -value_in_hex]
}

# === variant B: short VIR (8 bits) ===
proc variant_B {} {
    global IR_USER0 IR_USER1
    device_ir_shift -ir_value $IR_USER1 -no_captured_ir_value
    device_dr_shift -length 8 -dr_value FF -value_in_hex \
        -no_captured_dr_value
    device_ir_shift -ir_value $IR_USER0 -no_captured_ir_value
    return [device_dr_shift -length 256 -dr_value [hex_zeros 256] \
                -value_in_hex]
}

# === variant C: one USER0 "priming" scan, then real read ===
# Per some AN 628 implementations, the hub info register only becomes
# the active VDR after a USER0 UPDATE-DR transition.
proc variant_C {} {
    global IR_USER0 IR_USER1
    device_ir_shift -ir_value $IR_USER1 -no_captured_ir_value
    device_dr_shift -length 32 -dr_value [hex_ones 32] -value_in_hex \
        -no_captured_dr_value
    device_ir_shift -ir_value $IR_USER0 -no_captured_ir_value
    # priming shift — forces UPDATE-DR
    device_dr_shift -length 1 -dr_value 0 -value_in_hex \
        -no_captured_dr_value
    # real read — CAPTURE-DR should now load hub info
    return [device_dr_shift -length 256 -dr_value [hex_zeros 256] \
                -value_in_hex]
}

# === variant D: re-enter USER0 IR between each 32-bit word ===
# Some implementations latch a fresh 32-bit hub info word on each
# CAPTURE-DR only if preceded by IR-scan.
proc variant_D {} {
    global IR_USER0 IR_USER1
    device_ir_shift -ir_value $IR_USER1 -no_captured_ir_value
    device_dr_shift -length 32 -dr_value [hex_ones 32] -value_in_hex \
        -no_captured_dr_value
    set acc ""
    for {set i 0} {$i < 8} {incr i} {
        device_ir_shift -ir_value $IR_USER0 -no_captured_ir_value
        set w [device_dr_shift -length 32 -dr_value 00000000 \
                   -value_in_hex]
        append acc "$w "
    }
    return $acc
}

# === variant E: TAP-RESET before, then USER1/USER0 ===
proc variant_E {} {
    global IR_USER0 IR_USER1
    # approximate TAP-RESET: shift IR=BYPASS, long 0-DR, then USER1
    device_ir_shift -ir_value 1023 -no_captured_ir_value
    device_dr_shift -length 64 -dr_value [hex_zeros 64] -value_in_hex \
        -no_captured_dr_value
    device_ir_shift -ir_value $IR_USER1 -no_captured_ir_value
    device_dr_shift -length 32 -dr_value [hex_ones 32] -value_in_hex \
        -no_captured_dr_value
    device_ir_shift -ir_value $IR_USER0 -no_captured_ir_value
    return [device_dr_shift -length 256 -dr_value [hex_zeros 256] \
                -value_in_hex]
}

# === variant F: shift VIR = 0 (no address → possibly resets) then hub ===
proc variant_F {} {
    global IR_USER0 IR_USER1
    device_ir_shift -ir_value $IR_USER1 -no_captured_ir_value
    device_dr_shift -length 8 -dr_value 00 -value_in_hex \
        -no_captured_dr_value
    device_ir_shift -ir_value $IR_USER1 -no_captured_ir_value
    device_dr_shift -length 8 -dr_value FF -value_in_hex \
        -no_captured_dr_value
    device_ir_shift -ir_value $IR_USER0 -no_captured_ir_value
    return [device_dr_shift -length 256 -dr_value [hex_zeros 256] \
                -value_in_hex]
}

foreach {name proc_name} {A variant_A B variant_B C variant_C D variant_D E variant_E F variant_F} {
    tap_idle
    set result [$proc_name]
    puts "VARIANT $name $result"
    flush stdout
}

tap_idle
device_unlock
close_device
puts "# DONE"
