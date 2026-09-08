// Motherboard U6 - the E/Q divider, the $FF40-$FF7F window strobe, and the
// system RAM's control lines. Same equations as clkdec.pld.
//
// A model of a GAL22V10, not a design to synthesise. See README.md.
//
// The divider is the machine's clock (docs/machine.md 1): 25.175 MHz / 12 =
// 2.0979 MHz, with /8 = 3.1469 MHz as fast-E mode, which machine.md 1.1 keeps
// as an experiment a builder opts into rather than a speed software may throw.
//
// The Q TAP IS DIVISOR-DEPENDENT and that is the subtle part. machine.md 1
// says "Q = same divider, 3 dots early", which is 90 degrees at /12 and 135
// degrees at /8. Q must lead E by a quarter cycle in BOTH modes, so the tap is
// 3 counts at /12 and 2 at /8. graphics.md 18 step 0 lists this as an exit
// criterion; it is the one thing about this part that is not obvious.

`default_nettype none

module clkdec (
    input  wire       clk25,     // 25.175 MHz master, pin 1
    input  wire       n_reset,
    input  wire       fast_e,    // high = /8, machine.md 1.1

    input  wire       n_iopage,  // from U3
    input  wire       la7,
    input  wire       la6,
    input  wire       a19,       // PHYSICAL A19 - it comes out of the map SRAM
    input  wire       a20,       // PHYSICAL A20 - the map SRAM's eighth bit
    input  wire       rw,

    output reg  [3:0] cnt,       // on pins, unconnected: four free test points
    output reg        e,
    output reg        q,

    output wire       n_iosel,
    output wire       n_ram_ce,
    output wire       n_ram_oe,
    output wire       n_ram_we
);

  // Terminal count. 11 = 1011 and 7 = 0111; both partial decodes are exact
  // because the counter never reaches 15.
  wire [3:0] nxt = (fast_e ? (cnt == 4'd7) : (cnt == 4'd11)) ? 4'd0 : cnt + 4'd1;

  // E and Q are REGISTERED, decoded from the next count and not the current
  // one. A combinational decode of a 4-bit counter glitches on the codes where
  // several bits change at once, and this output is the machine's clock.
  wire e_nxt = fast_e ? (nxt >= 4'd4) : (nxt >= 4'd6);
  wire q_nxt = fast_e ? (nxt >= 4'd2 && nxt <= 4'd5)
                      : (nxt >= 4'd3 && nxt <= 4'd8);

  // The 22V10's asynchronous reset is one product term shared by every
  // registered macrocell, so all six land in a defined state together.
  always @(posedge clk25 or negedge n_reset)
    if (!n_reset) begin cnt <= 4'd0; e <= 1'b0; q <= 1'b0; end
    else          begin cnt <= nxt;  e <= e_nxt; q <= q_nxt; end

  // The four combinational outputs are a separate module so that a testbench
  // can sweep them without reaching inside the divider. In the GAL they are
  // simply four more macrocells on the same part.
  decode dec (.n_iopage(n_iopage), .la7(la7), .la6(la6), .a19(a19), .a20(a20), .rw(rw),
              .e(e), .n_iosel(n_iosel), .n_ram_ce(n_ram_ce),
              .n_ram_oe(n_ram_oe), .n_ram_we(n_ram_we));

endmodule


module decode (
    input  wire n_iopage, la7, a19, a20, rw, e,
    /* verilator lint_off UNUSEDSIGNAL */
    // A REAL PIN THAT NO EQUATION USES, and the port stays to say so. U6 pin
    // 6 is wired to LA6 on the board; the 2026-09-08 widening to $FF00-$FF7F
    // deleted the term that read it. Keeping the port here and the trace
    // there is what makes $FF80-$FF8F (machine.md 5 item 1's option A+) a
    // one-line change instead of a respin. clkdec.pld carries the argument.
    input  wire la6,
    /* verilator lint_on UNUSEDSIGNAL */
    output wire n_iosel, n_ram_ce, n_ram_oe, n_ram_we
);

  // $FF00-$FF7F: the I/O page with A7 = 0 - machine.md 2 and 3. /IOPAGE comes
  // from U3. Two independent changes landed on this line on 2026-09-08 - a
  // polarity fix and the widening - and clkdec.pld sets both out.
  assign n_iosel  = ~(~n_iopage & ~la7);

  // System RAM: physical A19 = 0, and never during an I/O cycle. Qualifying
  // /OE with R/W is what stops the SRAM and the CPU both driving D0-D7 on a
  // write - with /OE tied low the SRAM drives from /CE time until /WE asserts,
  // about 90 ns of contention on every write.
  // A20 = 0 as well since 2026-09-08 - the map is 2 MB and system RAM is
  // the bottom quarter. clkdec.pld carries the argument.
  wire ramsel = n_iopage & ~a19 & ~a20;
  assign n_ram_ce = ~ramsel;
  assign n_ram_oe = ~(ramsel & rw);
  assign n_ram_we = ~(ramsel & ~rw & e);

endmodule

`default_nettype wire
