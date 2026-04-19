// SPDX-License-Identifier: GPL-3.0-or-later
// Pipeline validation: heartbeat + UART TX + key passthrough
// Target: EP4CE6F17C8 (AX301), ~200 LEs
module test_top (
    input        CLOCK,  // 50 MHz, PIN_E1
    input        KEY2,   // reset (active-low), PIN_E16
    input        KEY3,   // PIN_M16
    input        KEY4,   // PIN_M15
    output       TXD,    // UART 115200 8N1, PIN_G1
    output [3:0] LED     // G15, F16, F15, D16
);

    wire clk   = CLOCK;
    wire rst_n = KEY2;

    // --- Heartbeat: 28-bit counter ---
    reg [27:0] heartbeat;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) heartbeat <= 0;
        else        heartbeat <= heartbeat + 1;

    assign LED[0] = heartbeat[23];  // ~3 Hz
    assign LED[1] = ~KEY3;
    assign LED[2] = ~KEY4;

    // --- UART TX: "Hi!\r\n" every ~0.5s, 115200 baud ---
    localparam BAUD_DIV = 434;
    localparam MSG_LEN  = 5;

    reg [7:0] tx_char;
    reg [2:0] char_idx;
    always @(*) begin
        case (char_idx)
            3'd0:    tx_char = 8'h48;
            3'd1:    tx_char = 8'h69;
            3'd2:    tx_char = 8'h21;
            3'd3:    tx_char = 8'h0D;
            3'd4:    tx_char = 8'h0A;
            default: tx_char = 8'h00;
        endcase
    end

    reg [1:0]  state;
    reg [15:0] baud_cnt;
    reg [3:0]  bit_idx;
    reg [24:0] pause_cnt;
    reg [9:0]  frame;
    reg        tx_out;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state     <= 0;
            baud_cnt  <= 0;
            bit_idx   <= 0;
            char_idx  <= 0;
            pause_cnt <= 0;
            frame     <= 10'h3FF;
            tx_out    <= 1;
        end else begin
            case (state)
                2'd0: begin
                    frame    <= {1'b1, tx_char, 1'b0};
                    tx_out   <= 0;
                    bit_idx  <= 0;
                    baud_cnt <= 0;
                    state    <= 2'd1;
                end
                2'd1: begin
                    if (baud_cnt >= BAUD_DIV - 1) begin
                        baud_cnt <= 0;
                        if (bit_idx >= 4'd9) begin
                            tx_out <= 1;
                            if (char_idx >= MSG_LEN - 1) begin
                                char_idx  <= 0;
                                pause_cnt <= 0;
                                state     <= 2'd2;
                            end else begin
                                char_idx <= char_idx + 1;
                                state    <= 2'd0;
                            end
                        end else begin
                            bit_idx <= bit_idx + 1;
                            tx_out  <= frame[bit_idx + 1];
                        end
                    end else begin
                        baud_cnt <= baud_cnt + 1;
                    end
                end
                2'd2: begin
                    tx_out <= 1;
                    if (pause_cnt >= 25_000_000 - 1)
                        state <= 2'd0;
                    else
                        pause_cnt <= pause_cnt + 1;
                end
                default: state <= 2'd0;
            endcase
        end
    end

    assign TXD    = tx_out;
    assign LED[3] = (state == 2'd1);

endmodule
