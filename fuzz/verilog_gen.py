# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate minimal Verilog designs for bitstream fuzzing."""


def gen_lut4(expression: str, name: str = "fuzz_top") -> str:
    """Generate a minimal Verilog module with a single LUT4.

    Args:
        expression: Boolean expression using A, B, C, D (e.g. "A & B")
        name: Top-level module name
    """
    return f"""module {name}(
    input  wire A, B, C, D,
    output wire Q
);
    wire lut_out /* synthesis keep */;
    assign lut_out = {expression};
    assign Q = lut_out;
endmodule
"""


def gen_ff(name: str = "fuzz_top") -> str:
    """Generate a minimal Verilog module with a single D flip-flop."""
    return f"""module {name}(
    input  wire CLK,
    input  wire D,
    output reg  Q
);
    (* keep *) reg ff_out;
    always @(posedge CLK)
        ff_out <= D;
    assign Q = ff_out;
endmodule
"""


def gen_lut4_ff(expression: str, name: str = "fuzz_top") -> str:
    """Generate a LUT4 feeding a D flip-flop."""
    return f"""module {name}(
    input  wire CLK,
    input  wire A, B, C, D,
    output reg  Q
);
    wire lut_out /* synthesis keep */;
    assign lut_out = {expression};
    always @(posedge CLK)
        Q <= lut_out;
endmodule
"""


def gen_two_luts(expr1: str, expr2: str, name: str = "fuzz_top") -> str:
    """Generate two LUT4s connected: lut1 -> lut2 input A, for routing fuzzing."""
    return f"""module {name}(
    input  wire A, B, C, D,
    input  wire E, F, G,
    output wire Q
);
    wire lut1_out /* synthesis keep */;
    wire lut2_out /* synthesis keep */;
    assign lut1_out = {expr1};
    assign lut2_out = lut1_out & {expr2};
    assign Q = lut2_out;
endmodule
"""


def gen_lut4_primitive(mask: int, name: str = "fuzz_top") -> str:
    """Generate a design using the cycloneive_lcell_comb primitive directly.

    This gives precise control over the 16-bit LUT mask without
    relying on synthesis interpretation.

    Args:
        mask: 16-bit truth table (e.g. 0x8000 = A & B & C & D)
    """
    return f"""module {name}(
    input  wire A, B, C, D,
    output wire Q
);
    wire lut_out;
    cycloneive_lcell_comb #(
        .lut_mask(16'h{mask:04X}),
        .sum_lutc_input("datac"),
        .dont_touch("on")
    ) lut_inst (
        .dataa(A),
        .datab(B),
        .datac(C),
        .datad(D),
        .combout(lut_out)
    );
    assign Q = lut_out;
endmodule
"""


def gen_two_luts_primitive(mask1: int, mask2: int,
                           connect_port: str = "dataa",
                           name: str = "fuzz_top") -> str:
    """Generate two connected LUT primitives for routing fuzzing.

    lut1 drives lut2 via the specified input port.
    Both use explicit cycloneive_lcell_comb primitives for placement control.

    Args:
        mask1: 16-bit truth table for driver LUT
        mask2: 16-bit truth table for load LUT
        connect_port: Which lut2 input to connect lut1 to (dataa/datab/datac/datad)
    """
    # Build lut2 port connections
    lut2_ports = []
    for port, default_sig in [("dataa", "E"), ("datab", "F"), ("datac", "G"), ("datad", "1'b0")]:
        sig = "lut1_out" if port == connect_port else default_sig
        lut2_ports.append(f"        .{port}({sig})")

    lut2_ports_str = ",\n".join(lut2_ports)

    return f"""module {name}(
    input  wire A, B, C, D,
    input  wire E, F, G,
    output wire Q
);
    wire lut1_out;
    wire lut2_out;

    cycloneive_lcell_comb #(
        .lut_mask(16'h{mask1:04X}),
        .sum_lutc_input("datac"),
        .dont_touch("on")
    ) lut1 (
        .dataa(A),
        .datab(B),
        .datac(C),
        .datad(D),
        .combout(lut1_out)
    );

    cycloneive_lcell_comb #(
        .lut_mask(16'h{mask2:04X}),
        .sum_lutc_input("datac"),
        .dont_touch("on")
    ) lut2 (
{lut2_ports_str},
        .combout(lut2_out)
    );

    assign Q = lut2_out;
endmodule
"""


def gen_two_luts_single_input(mask1: int, mask2: int,
                              connect_port: str = "datab",
                              name: str = "fuzz_top") -> str:
    """Two connected LUTs where lut2 only has ONE meaningful input.

    Unlike gen_two_luts_primitive, the unused lut2 inputs are tied to constant
    literals (1'b0) instead of top-level pins. This prevents Quartus from
    routing external signals through lut2's other input ports, so the only LI
    MUX activation at lut2's destination LAB is the lut1 -> lut2 path. The
    top-level still has A..D pins to keep the IO signature similar to other
    designs (and to drive lut1).

    Args:
        mask1: 16-bit truth table for driver LUT (lut1)
        mask2: 16-bit truth table for load LUT (lut2)
        connect_port: which lut2 input port lut1's output drives
                      (dataa | datab | datac | datad)
    """
    lut2_ports = []
    for port in ("dataa", "datab", "datac", "datad"):
        sig = "lut1_out" if port == connect_port else "1'b0"
        lut2_ports.append(f"        .{port}({sig})")
    lut2_ports_str = ",\n".join(lut2_ports)

    return f"""module {name}(
    input  wire A, B, C, D,
    output wire Q
);
    wire lut1_out;
    wire lut2_out;

    cycloneive_lcell_comb #(
        .lut_mask(16'h{mask1:04X}),
        .sum_lutc_input("datac"),
        .dont_touch("on")
    ) lut1 (
        .dataa(A),
        .datab(B),
        .datac(C),
        .datad(D),
        .combout(lut1_out)
    );

    cycloneive_lcell_comb #(
        .lut_mask(16'h{mask2:04X}),
        .sum_lutc_input("datac"),
        .dont_touch("on")
    ) lut2 (
{lut2_ports_str},
        .combout(lut2_out)
    );

    assign Q = lut2_out;
endmodule
"""


def gen_two_luts_single_input_clocked(mask1: int, mask2: int,
                                      connect_port: str = "datab",
                                      name: str = "fuzz_top") -> str:
    """Same as gen_two_luts_single_input but registers Q with a flip-flop.

    Adds a CLK port and a 1-bit register on the output. The register sits
    downstream of lut2, so the LI activation feeding lut2's datab is
    unchanged compared to the unclocked variant. The point of the register
    is to give Quartus' STA a real timing arc (clock-to-output) so we can
    extract the routing path with `report_timing -show_routing`.
    """
    lut2_ports = []
    for port in ("dataa", "datab", "datac", "datad"):
        sig = "lut1_out" if port == connect_port else "1'b0"
        lut2_ports.append(f"        .{port}({sig})")
    lut2_ports_str = ",\n".join(lut2_ports)

    return f"""module {name}(
    input  wire CLK,
    input  wire A, B, C, D,
    output reg  Q
);
    wire lut1_out;
    wire lut2_out;

    cycloneive_lcell_comb #(
        .lut_mask(16'h{mask1:04X}),
        .sum_lutc_input("datac"),
        .dont_touch("on")
    ) lut1 (
        .dataa(A),
        .datab(B),
        .datac(C),
        .datad(D),
        .combout(lut1_out)
    );

    cycloneive_lcell_comb #(
        .lut_mask(16'h{mask2:04X}),
        .sum_lutc_input("datac"),
        .dont_touch("on")
    ) lut2 (
{lut2_ports_str},
        .combout(lut2_out)
    );

    always @(posedge CLK)
        Q <= lut2_out;
endmodule
"""


def gen_two_luts_pinned_clocked(mask1: int, mask2: int,
                                connect_port: str = "datab",
                                name: str = "fuzz_top") -> str:
    """Two LUTs where lut2's unused inputs come from REAL top-level pins (E,F,G)
    instead of 1'b0, and Q is registered.

    Solves two problems at once:
      1. No constant-network noise in the RBF diff (no 1'b0 routing).
      2. lut1 and lut2 have real fanin/fanout, so dont_touch can't be folded
         away by the fitter — STA timing graph contains lut1→lut2 edge.

    Maps the 3 unused lut2 ports to E,F,G in some order so connect_port still
    receives lut1_out.
    """
    spare = iter(("E", "F", "G"))
    lut2_ports = []
    for port in ("dataa", "datab", "datac", "datad"):
        if port == connect_port:
            sig = "lut1_out"
        else:
            sig = next(spare)
        lut2_ports.append(f"        .{port}({sig})")
    lut2_ports_str = ",\n".join(lut2_ports)

    return f"""module {name}(
    input  wire CLK,
    input  wire A, B, C, D,
    input  wire E, F, G,
    output reg  Q
);
    wire lut1_out;
    wire lut2_out;

    cycloneive_lcell_comb #(
        .lut_mask(16'h{mask1:04X}),
        .sum_lutc_input("datac"),
        .dont_touch("on")
    ) lut1 (
        .dataa(A),
        .datab(B),
        .datac(C),
        .datad(D),
        .combout(lut1_out)
    );

    cycloneive_lcell_comb #(
        .lut_mask(16'h{mask2:04X}),
        .sum_lutc_input("datac"),
        .dont_touch("on")
    ) lut2 (
{lut2_ports_str},
        .combout(lut2_out)
    );

    always @(posedge CLK)
        Q <= lut2_out;
endmodule
"""


def gen_single_lut_primitive_extra_inputs(mask: int, name: str = "fuzz_top") -> str:
    """Generate a single LUT primitive with 7 input ports (for routing baseline).

    Same I/O signature as two-LUT designs so only routing differs in pair-diff.
    """
    return f"""module {name}(
    input  wire A, B, C, D,
    input  wire E, F, G,
    output wire Q
);
    wire lut_out;

    cycloneive_lcell_comb #(
        .lut_mask(16'h{mask:04X}),
        .sum_lutc_input("datac"),
        .dont_touch("on")
    ) lut1 (
        .dataa(A),
        .datab(B),
        .datac(C),
        .datad(D),
        .combout(lut_out)
    );

    assign Q = lut_out;
endmodule
"""


def gen_empty(name: str = "fuzz_top") -> str:
    """Generate an empty design (just I/O buffers, no logic).

    This serves as the baseline for all diffs.
    """
    return f"""module {name}(
    input  wire A, B, C, D,
    output wire Q
);
    assign Q = 1'b0;
endmodule
"""
