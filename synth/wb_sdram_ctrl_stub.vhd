-- SPDX-License-Identifier: GPL-3.0-or-later
-- VHDL entity stub for wb_sdram_ctrl (real implementation in
-- $AX301_RTL/wb_sdram_ctrl.v). GHDL needs a VHDL entity matching the
-- component declaration in ax301_top.vhd so default binding succeeds
-- during elaboration; without this GHDL 7.0.0-dev hits an internal
-- "no field Actual" assertion crash. Yosys merges this stub with the
-- Verilog implementation by module name when both are read into the
-- same design.

library ieee;
use ieee.std_logic_1164.all;

entity wb_sdram_ctrl is
  port (
    clk        : in    std_ulogic;
    rst_n      : in    std_ulogic;
    -- XBUS (Wishbone)
    xbus_adr   : in    std_ulogic_vector(31 downto 0);
    xbus_dat_w : in    std_ulogic_vector(31 downto 0);
    xbus_sel   : in    std_ulogic_vector(3 downto 0);
    xbus_we    : in    std_ulogic;
    xbus_stb   : in    std_ulogic;
    xbus_cyc   : in    std_ulogic;
    xbus_dat_r : out   std_ulogic_vector(31 downto 0);
    xbus_ack   : out   std_ulogic;
    xbus_err   : out   std_ulogic;
    -- SDRAM pins
    S_CLK      : out   std_ulogic;
    S_CKE      : out   std_ulogic;
    S_NCS      : out   std_ulogic;
    S_NRAS     : out   std_ulogic;
    S_NCAS     : out   std_ulogic;
    S_NWE      : out   std_ulogic;
    S_BA       : out   std_ulogic_vector(1 downto 0);
    S_A        : out   std_ulogic_vector(12 downto 0);
    S_DQM      : out   std_ulogic_vector(1 downto 0);
    S_DB       : inout std_ulogic_vector(15 downto 0);
    -- Debug
    dbg_leds   : out   std_ulogic_vector(3 downto 0)
  );
end entity wb_sdram_ctrl;

-- Empty architecture — Yosys binds to the Verilog implementation.
architecture stub of wb_sdram_ctrl is
begin
end architecture stub;
