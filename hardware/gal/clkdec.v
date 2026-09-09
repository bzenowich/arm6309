// Motherboard U6 - the E/Q divider, the $FF00-$FF7F window strobe, and boot
// mode. Same equations as clkdec.pld.
//
// The system RAM's /CE, /OE and /WE were here until 2026-09-09. There is no
// system RAM - hardware/ram.md 6.2 dropped the DIP SRAM for four SIMM sockets
// a day earlier - and boot mode moved into the macrocells they vacated.
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
    input  wire       la5,       // $FFA0-$FFBF window select, with la7/la6
    input  wire       la4,       // 0 = block registers, 1 = control
    input  wire       la0,       // $FFB0 is TASK, $FFB1 is BOOT
    input  wire       wait_i,    // /WAIT, active high here. Holds the divider
    input  wire       rw,

    output reg  [3:0] cnt,       // on pins, unconnected: four free test points
    output reg        e,
    output reg        q,
    // RUN = 0 IS BOOT MODE, and it is zero at reset because a 22V10 has one
    // shared asynchronous reset that resets to zero and no per-macrocell
    // preset. A bit that had to come up SET could not live on this part at
    // all - machine.md 7.2, clkdec.pld.
    output reg        run,

    output wire       n_iosel,
    output wire       n_bootoe
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

  // $FFB1: the strobe that leaves boot mode. A level over E-high on a write,
  // so it is sampled on several CLK25 edges and setting an already-set bit is
  // idempotent. $FFB0 (la0 = 0) is TASK and does NOT set it, which is what
  // lets boot code write TASK, then the sixteen map entries, then $FFB1 - in
  // that order, because the map index is {TASK, block}.
  wire set_run = ~n_iopage & la7 & ~la6 & la5 & la4 & la0 & ~rw & e;

  // The 22V10's asynchronous reset is one product term shared by every
  // registered macrocell, so all seven land in a defined state together.
  // /WAIT holds the divider. machine.md 5 item 8: vctrl.pld drove this signal
  // and nothing listened, so the video card's span writer held nothing. One
  // hold term per macrocell, no macrocells - clkdec.pld has the two rules that
  // go with it (CLK25-synchronous, and asserted only while E is high).
  //
  // RUN IS NOT HELD BY /WAIT. It is not part of the divider; it is a mode bit
  // that happens to live on the same part, and holding it would mean a $FFB1
  // write during a stretched cycle did nothing.
  always @(posedge clk25 or negedge n_reset)
    if (!n_reset)     begin cnt <= 4'd0; e <= 1'b0; q <= 1'b0; run <= 1'b0; end
    else begin
      if (!wait_i)    begin cnt <= nxt;  e <= e_nxt; q <= q_nxt; end
      if (set_run)          run <= 1'b1;
    end

  // The two combinational outputs are a separate module so that a testbench
  // can sweep them without reaching inside the divider. In the GAL they are
  // simply two more macrocells on the same part.
  decode dec (.n_iopage(n_iopage), .la7(la7), .la6(la6), .run(run),
              .n_iosel(n_iosel), .n_bootoe(n_bootoe));

endmodule


module decode (
    input  wire n_iopage, la7, la6, run,
    output wire n_iosel, n_bootoe
);

  // $FF00-$FF7F: the I/O page with A7 = 0 - machine.md 2 and 3. /IOPAGE comes
  // from U3. Two independent changes landed on this line on 2026-09-08 - a
  // polarity fix and the widening - and clkdec.pld sets both out.
  assign n_iosel = ~(~n_iopage & ~la7);

  // $FFC0-$FFFF, the vector page. ONE product term, because /IOPAGE already
  // means "logical $FF00-$FFFF": the vector page is that page with A7 and A6
  // both high. A card-style A15..A8 compare would have cost eight literals
  // and an input pin.
  wire vecsel = ~n_iopage & la7 & la6;

  // The '244 drives physical A20-A13 whenever the map SRAMs do not: for the
  // whole of boot mode, and for the vector page forever. U9 forms the SRAMs'
  // chip enables from the same two conditions, so the changeover is one
  // signal seen by two parts rather than two decodes that have to agree.
  assign n_bootoe = ~(~run | vecsel);

endmodule

`default_nettype wire
