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
