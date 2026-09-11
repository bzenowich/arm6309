// 9's palette write path and 10.3.3's display-list register port, on the real
// vsup: the '163 index counter pair, the two '573 data latches, the LUT's two
// buses and 13.1's turnaround between their masters.
//
// WHY THIS FILE EXISTS. Until 2026-09-09 the palette had NO PRODUCER AT ALL -
// census.ts booked "PIDX '593 load and count" as a line item with no cell
// behind it, so nothing loaded the counter, drove the LUT's address during a
// write or asserted its /WE - and the '593 itself turned out to be
// discontinued (19 item 9, closed 2026-09-09). The CPU could not write the palette, and on a card
// whose only colour path is the LUT that is the whole picture. Every claim
// below would have been unrunnable a day ago.
//
// A comment line here must never begin with the simulator's own name.

module vpal_tb;

  logic DOTCLK = 0;
  always #1 DOTCLK <= ~DOTCLK;

  logic RESET = 1, E = 0, RW = 1, IOSEL = 0, IOPAGE = 1;
  logic [20:0] PA = 0;
  logic [7:0]  DIN = 0;

  wire WAIT_OE, IRQ_OE, BLANK, HSYNC, VSYNC;
  wire [7:0] PIXEL;
  wire [7:0] H;  wire [9:0] V;  wire [1:0] PH;
  wire [18:2] FBA;
  wire LINEAR, TILESEL, MAPSEL, SPNGRANT, SPANBUSY, LRUN;
  wire RETIRE, WEN, SPANEND, MAPLD, MAPREQ, SLOTTICK, SPAREWIN;
  wire [18:0] WPTR;  wire [1:0] VMODE;  wire VBLANK, HBLANK;
  wire [7:0] RD_o;
  wire [9:2] HSCR; wire LPH_o, LWAIT_o;

  wire [15:0] RGB; wire [7:0] PIDX;
  wire PWE_o, PDOE_o, PIXOE_o, DBUS_FIGHT;
  wire [7:0] VREAD; wire RDOE_o;          // graphics.md 11's vread '574

  video_card card (.*);

  int fails = 0;
  task automatic ok(input bit good, input string claim);
    if (good) $display("ok    %s", claim);
    else begin fails++; $display("FAIL  %s", claim); end
  endtask

  // ---- the 6809 bus at /12: E high for 6 dots of 12 ----------------------
  task automatic bus_cycle(input logic [20:0] addr, input bit is_io,
                           input bit write, input logic [7:0] v);
    @(negedge DOTCLK);
    PA = addr; IOPAGE = is_io; IOSEL = is_io & (addr[7:0] < 8'h80);
    RW = ~write; DIN = v;
    repeat (6) @(negedge DOTCLK);
    E = 1;
    repeat (6) @(negedge DOTCLK);
    E = 0; RW = 1; IOSEL = 0; IOPAGE = 1; DIN = 0; PA = 0;
  endtask

  task automatic wreg(input int off, input logic [7:0] v);
    bus_cycle(21'h0060 + off[6:0], 1, 1, v);
    // the commit sequence is four dots and it runs AFTER the write cycle
    repeat (8) @(posedge DOTCLK);
  endtask

  // 13's three-write palette entry: index once, then a pair per colour.
  task automatic wpal(input int idx, input logic [15:0] rgb);
    wreg('h10, idx[7:0]);
    wreg('h11, rgb[7:0]);
    wreg('h12, rgb[15:8]);
  endtask

  task automatic set_wptr(input int a);
    wreg('h08, a[7:0]); wreg('h09, a[15:8]); wreg('h0a, {5'b0, a[18:16]});
  endtask

  // 9's boot identity palette: PALETTE[i] = rgb565_of_rgb332(i).
  function automatic logic [15:0] ident(input logic [7:0] i);
    logic [4:0] r; logic [5:0] g; logic [4:0] b;
    r = {i[7:5], i[7:6]};
    g = {i[4:2], i[4:2]};
    b = {i[1:0], i[1:0], i[1]};
    ident = {r, g, b};
  endfunction

  int i, n, wrong, fights, moves;
  // 10.3.3's two claims run for the whole of the list, GO included, so they
  // are a process and not a loop body.
  bit watching = 0;
  /* verilator lint_off BLKSEQ */
  always @(posedge DOTCLK) if (watching) begin
    if (card.LMOVE) moves++;
    // 10.3.3's two buses: neither may ever have two masters, and vaddr's
    // decode of +$03 must agree with vsup's - they are separate nets.
    if (DBUS_FIGHT || card.pal_fight) fights++;
    if (card.VS_LDHS !== card.LDHS) wrong++;
  end
  /* verilator lint_on BLKSEQ */
  logic [15:0] want;
  logic [7:0] idx_d1 = 8'hxx;

  initial begin
    for (i = 0; i < 16384; i++) card.poke(i, 8'hEE);

    repeat (4) @(posedge DOTCLK);
    RESET = 0;
    repeat (8) @(posedge DOTCLK);
    wreg('h00, 8'h00);          // CTRL = 0: display off, direct writes

    $display("");
    $display("9's palette write path - the CPU side (graphics.md 13, +$10-$12)");
    $display("");

    wpal('h12, 16'h5634);
    ok(card.peek_pal('h12) == 16'h5634,
       $sformatf("a PDATH write commits the entry: LUT[$12] = $5634 (got $%04h)",
                 card.peek_pal('h12)));
    ok(PIDX == 8'h13,
       $sformatf("13: PIDX auto-increments after PDATH (got $%02h)", PIDX));

    // Two entries from one index write - which is what makes 13.1's "all 256
    // in one vertical blank at 2 writes per entry" true rather than 3.
    wreg('h10, 8'h40);
    wreg('h11, 8'h11); wreg('h12, 8'h22);
    wreg('h11, 8'h33); wreg('h12, 8'h44);
    ok(card.peek_pal('h40) == 16'h2211 && card.peek_pal('h41) == 16'h4433,
       $sformatf("and the counter runs: $40 = $%04h, $41 = $%04h, from ONE index write",
                 card.peek_pal('h40), card.peek_pal('h41)));

    // 9's whole point: software that thinks in RGB332 is bit-identical to a
    // fixed-ladder card once this is loaded.
    wreg('h10, 8'h00);
    for (i = 0; i < 256; i++) begin
      want = ident(i[7:0]);
      wreg('h11, want[7:0]);
      wreg('h12, want[15:8]);
    end
    wrong = 0;
    for (i = 0; i < 256; i++)
      if (card.peek_pal(i) !== ident(i[7:0])) wrong++;
    ok(wrong == 0,
       $sformatf("⭐ 9's boot identity palette loads end to end - 256 entries, 512 writes, %0d wrong", wrong));
    ok(PIDX == 8'h00,
       $sformatf("and PIDX wrapped back to $00 after the 256th (got $%02h)", PIDX));

    $display("");
    $display("13.1's turnaround - two masters on the LUT address bus");
    $display("");

    // The whole of 13.1 is that the bus is shared by tri-state turnaround and
    // there is no arbitration. What there must never be is two masters at once.
    fights = 0;
    fork
      begin wpal('h77, 16'hBEEF); end
      begin repeat (200) @(posedge DOTCLK) if (card.pal_fight) fights++; end
    join
    ok(fights == 0,
       $sformatf("the pixel-index '574 and the index '244 never drive the LUT's address together (%0d dots)", fights));
    ok(card.peek_pal('h77) == 16'hBEEF, "and the entry still lands");

    // 13.1 says a palette write costs the pixel path some dots. Count them, so
    // the rule has a number rather than "one or two".
    n = 0;
    fork
      begin wreg('h12, 8'h00); end
      begin repeat (200) @(posedge DOTCLK) if (!PIXOE_o) n++; end
    join
    ok(n > 0 && n <= 8,
       $sformatf("⚠ 13.1's snow is bounded and measured: %0d dots of turnaround per commit", n));

    $display("");
    $display("The dot path - '153 -> index '574 -> LUT -> '273 (graphics.md 6.1)");
    $display("");

    // Load a known palette and a known framebuffer, turn the display on, and
    // check the colour the connector sees against the entry the index selects.
    // ⭐ This is the first check in the repository that ever followed a pixel
    // all the way from VRAM to RGB - vaddr_tb compares a pixel to memory and
    // stops at the '153.
    //
    // ⚠ THE SNOW TEST ABOVE OVERWROTE AN ENTRY, which is the point of it, so
    // 9's identity palette goes back in first.
    wreg('h10, 8'h00);
    for (i = 0; i < 256; i++) begin
      want = ident(i[7:0]);
      wreg('h11, want[7:0]);
      wreg('h12, want[15:8]);
    end
    for (i = 0; i < 8192; i++) card.poke(i, i[7:0]);
    wreg('h01, 8'h00); wreg('h02, 8'h00);       // VSCROLL = 0
    wreg('h03, 8'h00); wreg('h04, 8'h00);       // HSCROLL = 0
    wreg('h00, 8'h80);                          // display on, VMODE 00
    wrong = 0; n = 0;
    for (i = 0; i < 400000; i++) begin
      @(posedge DOTCLK); #0;
      // The '273 holds what the LUT read from the index the '574 latched one
      // dot earlier - 6.1's chain, and the shadow is how the check follows it.
      if (!BLANK && n < 256 && idx_d1 !== 8'hxx) begin
        if (RGB !== ident(idx_d1)) wrong++;
        n++;
      end
      idx_d1 = card.pixidx;
      if (n >= 256) break;
    end
    ok(n > 0, $sformatf("the picture reaches the ladders: %0d dots sampled", n));
    ok(wrong == 0,
       $sformatf("⭐ every dot's RGB is the palette entry its index selects - %0d wrong of %0d", wrong, n));

    // 9.2: blank-to-black is the post-LUT '273's /MR, and it is why the part
    // is a '273 and not a '574.
    n = 0;
    for (i = 0; i < 200000; i++) begin
      @(posedge DOTCLK); #0;
      if (BLANK && RGB !== 16'h0000) n++;
      if (i > 4000 && VBLANK) break;
    end
    ok(n == 0, "9.2: RGB is 0.000 V for every blanked dot - the '273's /MR, not an /OE");

    $display("");
    $display("10.3.3 - the display list's register port");
    $display("");

    // 10.3.2's format, now reaching 9's palette:
    //   $10 $A0   MOVE PIDX, $A0
    //   $11 $CD   MOVE PDATL, $CD
    //   $12 $AB   MOVE PDATH, $AB     -> LUT[$A0] = $ABCD, PIDX -> $A1
    //   $03 $55   MOVE HSCROLL, $55   -> 8.2's fine pair AND HS9..HS2
    //   $FF       END
    wreg('h00, 8'h80);
    card.poke(12288 + 0, 8'h10); card.poke(12288 + 1, 8'hA0);
    card.poke(12288 + 2, 8'h11); card.poke(12288 + 3, 8'hCD);
    card.poke(12288 + 4, 8'h12); card.poke(12288 + 5, 8'hAB);
    card.poke(12288 + 6, 8'h03); card.poke(12288 + 7, 8'h55);
    card.poke(12288 + 8, 8'hFF);
    wreg('h03, 8'h00); wreg('h04, 8'h00);
    set_wptr(12288);
    moves = 0; wrong = 0; fights = 0;
    // ⚠ THE WATCH STARTS BEFORE THE GO. An earlier version issued BCTRL.GO
    // concurrently with the counting loop and the CPU's own write cycle then
    // overlapped the engine's first fetch: LBYTE carries !WSTB, the '244 stood
    // off, and vsup latched the CPU's $01 as the opcode while vaddr latched
    // $10 off the pixel bus. That is 10.3.3's collision, exactly as specified,
    // and it is the one case in which the two copies of the decode can differ.
    watching = 1;
    wreg('h0e, 8'h01);                          // BCTRL.GO
    for (i = 0; i < 200000; i++) begin
      @(posedge DOTCLK); #0;
      if (i > 40 && !LRUN) break;
    end
    watching = 0;
    ok(LRUN == 1'b0, "the engine ran to the $FF terminator");
    ok(moves == 4, $sformatf("four MOVEs, one operand cycle each (got %0d)", moves));
    ok(card.peek_pal('hA0) == 16'hABCD,
       $sformatf("⭐ a display list writes the palette: LUT[$A0] = $ABCD (got $%04h)",
                 card.peek_pal('hA0)));
    ok(PIDX == 8'hA1,
       $sformatf("and PIDX auto-incremented under the list too (got $%02h)", PIDX));
    ok(HSCR == 8'h15,
       $sformatf("8.2's HSCROLL[9:2] took the same list's MOVE (got $%02h)", HSCR));
    ok(card.PX_HS0 == 1'b1 && card.PX_HS1 == 1'b0,
       $sformatf("⭐ and so did the FINE pair on vsup - HSCROLL[1:0] = $55 & 3 = 1 (got %0d%0d)",
                 card.PX_HS1, card.PX_HS0));
    ok(wrong == 0,
       $sformatf("⚠ vaddr's decode of +$03 and vsup's never disagree - %0d dots differed", wrong));
    ok(fights == 0,
       $sformatf("and no bus has two masters at any dot of the run (%0d)", fights));

    $display("");
    $display("7.4's SPANLEN, which is eight macrocells on vsup now");
    $display("");
    wreg('h05, 8'h07);
    ok({card.SL7,card.SL6,card.SL5,card.SL4,card.SL3,card.SL2,card.SL1,card.SL0} == 8'h07,
       "13's +$05 is held on vsup rather than read back out of the register file");
    wreg('h05, 8'h00);
    ok({card.SL7,card.SL6,card.SL5,card.SL4,card.SL3,card.SL2,card.SL1,card.SL0} == 8'h00,
       "and it is a register, not a strobe - a second write replaces it");

    $display("");
    if (fails == 0) $display("vpal_tb OK");
    else $display("vpal_tb: %0d FAILURES", fails);
    $finish;
  end
endmodule
