// The span writer and the display list, on the real seqctl, arbiter and WPTR,
// with vshim supplying the SPANLEN counter, the mask serialiser, the grants and
// the register strobes that no fitted design contains.
//
// graphics.md 7.4 is the specification: four WMODEs, one retire per fetch slot,
// SPANBUSY as VSTAT b7 and the /WAIT condition, WADV chaining. features.md 8.4
// adds sprite mode. 10.3.1 is the list engine's reload rule.
//
// A comment line here must never begin with the simulator's own name.

module vspan_tb;

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

  wire [9:2] HSCR; wire LPH_o, LWAIT_o;   // 10.3.2's descriptor engine

  // 9's palette, and 10.3.3's turnaround on the card's internal data bus.
  wire [15:0] RGB; wire [7:0] PIDX;
  wire PWE_o, PDOE_o, PIXOE_o, DBUS_FIGHT;

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
    repeat (6) @(negedge DOTCLK);          // E low half
    E = 1;
    repeat (6) @(negedge DOTCLK);          // E high half
    E = 0; RW = 1; IOSEL = 0; IOPAGE = 1; DIN = 0; PA = 0;
  endtask

  task automatic wreg(input int off, input logic [7:0] v);
    bus_cycle(21'h0060 + off[6:0], 1, 1, v);
  endtask
  task automatic wvram(input int addr, input logic [7:0] v);
    bus_cycle({2'b01, addr[18:0]}, 0, 1, v);
  endtask
  task automatic rvram(input int addr);
    bus_cycle({2'b01, addr[18:0]}, 0, 0, 8'h00);
  endtask

  int retires, wens, slots, busy_dots;
  int start_ptr;
  bit saw_wait;

  // Run until SPANBUSY falls, counting what happened.
  int rp_dots;
  task automatic run_span(input int limit);
    retires = 0; wens = 0; busy_dots = 0; slots = 0; rp_dots = 0;
    for (int i = 0; i < limit; i++) begin
      @(posedge DOTCLK); #0;
      if (SPANBUSY) busy_dots++;
      if (RETIRE) retires++;
      if (WEN) wens++;
      if (SLOTTICK && SPANBUSY) slots++;
      if (card.RP0 || card.RP1) rp_dots++;
      /* ⚠ Not the moment SPANBUSY falls: 7.2's column reload is two dots
       * after it, so a test that stopped there would read the pointer
       * mid-repair. */
      if (!SPANBUSY && i > 4 && !card.RP0 && !card.RP1) break;
    end
  endtask

  // Set WPTR to a byte address: three writes, 13's +$08..+$0A.
  task automatic set_wptr(input int a);
    wreg('h08, a[7:0]);
    wreg('h09, {6'b0, a[9:8]});
    wreg('h0a, {5'b0, a[18:16]});
    // 13/access.jedec.ts: byte 0 is A7..A0, byte 1 is A9..A8 AND A15..A10,
    // byte 2 is A18..A16.
    wreg('h09, {a[15:10], a[9:8]});
  endtask

  int i, n, got;
  int m, waited;
  int wait_lines;          // HLOADs across a WAIT - 10.3's "next line", counted
  logic prev_hload;
  logic [7:0] hscr_before_wait;
  logic [7:0] b;
  logic [7:0] mask8 = 8'hB4;

  initial begin
    for (i = 0; i < 8192; i++) card.poke(i, 8'hEE);

    repeat (4) @(posedge DOTCLK);
    RESET = 0;
    repeat (8) @(posedge DOTCLK);

    wreg('h00, 8'h80);          // CTRL: display on, WMODE 00 (direct)
    wreg('h06, 8'hA1);          // WFG - the register FILE holds it now, and
    wreg('h07, 8'h5C);          // WBG   rfa addresses it by the mask bit

    $display("");
    $display("WMODE 00 - direct: one posted write, one byte (graphics.md 7.4)");
    $display("");
    set_wptr(20);
    start_ptr = WPTR;
    ok(start_ptr == 20, $sformatf("WPTR loads from +$08..+$0A (got %0d)", start_ptr));
    wvram(20, 8'h3C);
    run_span(4000);
    ok(retires == 1, $sformatf("direct mode retires exactly one byte (got %0d)", retires));
    ok(card.peek(20) == 8'h3C,
       $sformatf("and the byte lands at WPTR (got %02h)", card.peek(20)));
    ok(WPTR == 21, $sformatf("WPTR post-increments (got %0d)", WPTR));

    $display("");
    $display("WMODE 01 - span-mask: eight pixels, WFG or WBG per mask bit");
    $display("");
    wreg('h00, 8'h88);          // WMODE 01
    set_wptr(64);
    wvram(64, 8'hB4);           // mask 1011 0100
    run_span(8000);
    ok(retires == 8, $sformatf("span-mask retires eight bytes - the cell width (got %0d)",
                               retires));
    ok(wens == 8, $sformatf("and writes all eight (got %0d)", wens));
    n = 0;
    for (i = 0; i < 8; i++) begin
      b = mask8[7-i] ? 8'hA1 : 8'h5C;
      if (card.peek(64 + i) != b) n++;
    end
    ok(n == 0, $sformatf("the eight bytes are WFG/WBG per mask bit, MSB first (%0d wrong)", n));
    ok(WPTR == 72, $sformatf("WPTR advanced by eight (got %0d)", WPTR - 0));

    $display("");
    $display("WMODE 10 - span-solid: SPANLEN + 1 bytes of one colour");
    $display("");
    wreg('h00, 8'h90);          // WMODE 10
    wreg('h05, 8'd31);          // SPANLEN = 31 -> 32 bytes
    set_wptr(128);
    wvram(128, 8'h00);
    run_span(40000);
    ok(retires == 32, $sformatf("span-solid retires SPANLEN+1 = 32 bytes (got %0d)",
                                retires));
    n = 0;
    for (i = 0; i < 32; i++) if (card.peek(128 + i) != 8'hA1) n++;
    ok(n == 0, $sformatf("all 32 are WFG (%0d wrong)", n));

    $display("");
    $display("WMODE 11 - sprite: eight retires, and a 0 bit writes nothing");
    $display("");
    wreg('h00, 8'h98);          // WMODE 11
    set_wptr(256);
    for (i = 0; i < 8; i++) card.poke(256 + i, 8'h11);
    wvram(256, 8'hB4);          // 1011 0100 - five ones
    run_span(8000);
    ok(retires == 8, $sformatf("sprite mode retires eight (got %0d)", retires));
    ok(wens == 4, $sformatf("and writes only the set bits - four of eight (got %0d)",
                            wens));
    ok(WPTR == 264, $sformatf("the pointer still advances by eight, or the shape draws squashed (got %0d)", WPTR - 256));
    n = 0;
    for (i = 0; i < 8; i++) begin
      b = mask8[7-i] ? 8'hA1 : 8'h11;   // untouched background stays $11
      if (card.peek(256 + i) != b) n++;
    end
    ok(n == 0, $sformatf("transparent pixels leave the background alone (%0d wrong)", n));

    $display("");
    $display("The retire rate - 7.4: one granted retire per 158.9 ns fetch slot");
    $display("");
    wreg('h00, 8'h90);          // solid
    wreg('h05, 8'd31);
    set_wptr(1024);
    wvram(1024, 8'h00);
    run_span(40000);
    ok(retires == 32, "32 bytes again");
    ok(slots >= retires - 1 && slots <= retires,
       $sformatf("one retire per slot: %0d retires in %0d slots of SPANBUSY",
                 retires, slots));

    $display("");
    $display("/WAIT - 7.4: writes wait, reads never do");
    $display("");
    wreg('h05, 8'd255);         // a 256-byte span, the worst case
    set_wptr(2048);
    wvram(2048, 8'h00);
    // a CPU VRAM WRITE while the span runs
    saw_wait = 0;
    fork
      begin wvram(3000, 8'h77); end
      begin repeat (12) @(posedge DOTCLK); if (WAIT_OE) saw_wait = 1; end
    join
    ok(saw_wait, "a CPU VRAM write during a span pulls /WAIT");
    // a CPU VRAM READ while the span runs
    saw_wait = 0;
    fork
      begin rvram(3000); end
      begin repeat (12) @(posedge DOTCLK); if (WAIT_OE) saw_wait = 1; end
    join
    ok(!saw_wait, "a CPU VRAM read does NOT - the !RW qualification of 7.4");
    // and nothing in the I/O page waits, which is what makes polling VSTAT free
    saw_wait = 0;
    fork
      begin bus_cycle(21'h0073, 1, 0, 8'h00); end
      begin repeat (12) @(posedge DOTCLK); if (WAIT_OE) saw_wait = 1; end
    join
    ok(!saw_wait, "reading VSTAT at $FF73 never waits - 7.4's polling rule");
    run_span(400000);

    $display("");
    $display("WADV = 01 - 7.2's chaining, which is what makes a glyph eight writes");
    $display("");
    wreg('h00, 8'h88);          // WMODE 01, mask
    wreg('h14, 8'h01);          // WADV = 01, next row same column
    set_wptr(4096);             // row 4, column 0
    wvram(4096, 8'hFF);
    run_span(8000);
    // 7.2's reload is two dots AFTER the span ends, so let it finish.
    repeat (8) @(posedge DOTCLK);
    ok(WPTR == 4096 + 1024,
       $sformatf("at span end WPTR is one row on and back at the same column: got %0d, want %0d", WPTR, 4096 + 1024));

    $display("");
    $display("The display list - graphics.md 10.3, 10.3.1");
    $display("");
    // 10.3.2's descriptor format, graphics.md 19 item 32. Three MOVEs, one
    // WAIT and a terminator, in eight bytes:
    //
    //   $03 $55   MOVE HSCROLL, $55    HS7..HS2 = $55[7:2] = 6'b010101
    //   $04 $02   MOVE HSCROLLH, $02   HS9:HS8  = $02[1:0] = 2'b10
    //   $80       WAIT                 resume at the next HLOAD
    //   $03 $FF   MOVE HSCROLL, $FF    ** AN OPERAND OF $FF IS A VALUE
    //   $FF       END
    wreg('h00, 8'h80);          // WMODE 00, display enabled
    wreg('h14, 8'h00);
    card.poke(8192 + 0, 8'h03); card.poke(8192 + 1, 8'h55);
    card.poke(8192 + 2, 8'h04); card.poke(8192 + 3, 8'h02);
    card.poke(8192 + 4, 8'h80);
    card.poke(8192 + 5, 8'h03); card.poke(8192 + 6, 8'hFF);
    card.poke(8192 + 7, 8'hFF);
    wreg('h03, 8'h00); wreg('h04, 8'h00);   // HSCROLL = 0 before the list runs
    set_wptr(8192);
    wreg('h0e, 8'h01);          // BCTRL.GO
    /* ⚠ AND THE WAIT HAS TO BE ONE LINE, which nothing counted until
     * 2026-09-10. graphics.md 10.3 sells the list engine as per-scanline -
     * gradients, split palettes, raster bars - and the whole of that rests on
     * WAIT resuming at the NEXT HLOAD rather than some later one. "LWAIT was
     * asserted" is a claim about the stall and says nothing about its length,
     * so the lines are counted here: HLOAD pulses from the instant LWAIT rises
     * to the instant it falls, and the answer has to be one. */
    n = 0; m = 0; waited = 0; hscr_before_wait = 8'hxx;
    wait_lines = 0; prev_hload = 1'b0;
    for (i = 0; i < 40000; i++) begin
      @(posedge DOTCLK); #0;
      if (card.LMOVE) n++;
      if (LWAIT_o) begin
        waited = 1;
        if (m == 0) begin hscr_before_wait = HSCR; m = 1; end
        if (card.HLOAD && !prev_hload) wait_lines++;
      end
      prev_hload = card.HLOAD;
      if (i > 40 && !LRUN) break;
    end
    ok(LRUN == 1'b0, "BSTAT b0 LRUN falls when the engine meets the $FF terminator");
    ok(n == 3, $sformatf("three MOVEs, one operand cycle each - the opcode bytes and the WAIT are not writes (got %0d)", n));
    ok(waited == 1, "⭐ the WAIT opcode stalled the engine - LWAIT was asserted");
    ok(wait_lines == 1,
       $sformatf("⭐ and it resumed on the NEXT line - %0d HLOAD across the stall, and 10.3's per-scanline gradients are that number being one", wait_lines));
    ok(hscr_before_wait == 8'h95,
       $sformatf("and by then both MOVEs had landed: HSCROLL[9:2] = $95 (got $%02h)", hscr_before_wait));
    ok(HSCR == 8'hBF,
       $sformatf("⚠ an operand of $FF is a SCROLL VALUE and not a terminator: $BF after the third MOVE (got $%02h)", HSCR));
    ok(WPTR == 8192 + 8,
       $sformatf("and it clobbered WPTR, which is 10.3.1's rule (got %0d)", WPTR));

    // 19 item 24: the engine's walk is a plain +1 whatever WADV says.
    wreg('h14, 8'h02);          // WADV = 10, vertical - the mode that broke it
    card.poke(8192 + 0, 8'h03); card.poke(8192 + 1, 8'h11);
    card.poke(8192 + 2, 8'hFF);
    set_wptr(8192);
    wreg('h0e, 8'h01);
    for (i = 0; i < 40000; i++) begin
      @(posedge DOTCLK); #0;
      if (i > 40 && !LRUN) break;
    end
    ok(WPTR == 8192 + 3,
       $sformatf("⭐ 19 item 24: a list started with WADV = 10 still steps by one, not by the 1,024 stride (got %0d)", WPTR));
    wreg('h14, 8'h00);

    $display("");
    $display("One strobe per job - design-review2.md V-2");
    $display("");
    // rfa's WSTB is a write to $FF60-$FF7F and vctrl forms WSTBV from
    // VRAMSEL & /RW & E. They were one signal, so writing any card register
    // started a span and a posted VRAM write started none.
    saw_wait = 0;
    fork
      begin wreg('h03, 8'h10); end     // HSCROLL - a perfectly ordinary write
      begin repeat (20) @(posedge DOTCLK) if (SPANBUSY) saw_wait = 1; end
    join
    ok(!saw_wait, "writing HSCROLL does not start a span");
    saw_wait = 0;
    fork
      begin wvram(16384, 8'h42); end
      begin repeat (30) @(posedge DOTCLK) if (SPANBUSY) saw_wait = 1; end
    join
    ok(saw_wait, "and a posted VRAM write does");

    $display("");
    $display("The VBL interrupt - graphics.md 12.1");
    $display("");
    wreg('h00, 8'hC0);              // IRQEN, display off
    n = 0;
    for (i = 0; i < 359200 + 4000; i++) begin
      @(posedge DOTCLK); #0;
      if (IRQ_OE && !VSYNC) ;       // level, sampled below
      if (IRQ_OE) n++;
      if (n > 0 && i > 359200) break;
    end
    ok(n > 0, "/IRQ is asserted once vertical blank has been reached");
    // clear it by writing VSTAT
    wreg('h13, 8'h00);
    repeat (8) @(posedge DOTCLK);
    ok(!IRQ_OE, "and a write to VSTAT clears the pending flag - 12.1's VSTATWR");

    $display("");
    if (fails == 0) $display("vspan_tb OK");
    else $display("vspan_tb: %0d FAILURES", fails);
    $finish;
  end
endmodule
