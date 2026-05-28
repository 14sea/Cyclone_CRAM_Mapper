# SPDX-License-Identifier: GPL-3.0-or-later
# A2 — NEORV32 routing-resource wire-name census from the compiled DB.
# Dumps routing-annotated timing paths; the parser classifies the
# routing-element wire-name prefixes to resolve what "Block interconnects"
# physically are (alias vs new physical class).
#   quartus_sta -t a2_routing_census.tcl   (run from the project dir)
project_open neorv32_demo -revision neorv32_demo
create_timing_netlist
catch {read_sdc}
update_timing_netlist
report_timing -setup -npaths 300 -detail full_path -show_routing \
    -file /tmp/a2_sta_routing_big.rpt
catch {delete_timing_netlist}
project_close
