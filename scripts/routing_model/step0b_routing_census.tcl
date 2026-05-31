# SPDX-License-Identifier: GPL-3.0-or-later
# STEP 0b — NEORV32 routing-resource wire-name census (no recompile).
# Dumps routing-annotated timing paths so the parser can histogram the
# per-class wire I-indices (C4 I=0 vs I!=0, R4 I-index coverage) — the
# split the fit-report "Routing Usage Summary" lumps together.
#   quartus_sta -t step0b_routing_census.tcl   (run from the quartus project dir)
project_open neorv32_demo -revision neorv32_demo
create_timing_netlist
catch {read_sdc}
update_timing_netlist
# Large path sample, full routing detail, both setup and hold corners.
report_timing -setup -npaths 4000 -detail full_path -show_routing \
    -file /tmp/step0b_sta_routing.rpt
project_close
