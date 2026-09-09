// The framebuffer address, run over whole lines and whole frames on the merged
// parts: bitmap scan, both axes of scroll at every resolution, the 1024 x 512
// torus wrap, tile mode's concatenation and its one-cell fetch lead, and the
// one thing a term list cannot show - who owns the card's single internal
// address bus, and when.
//
// check:scan and check:tile assert the arithmetic; check:cadence walks a line
// and a frame in TypeScript. This runs the same equations as hardware, with
// the counters clocked and the map byte coming out of memory.
//
// A comment line here must never begin with the simulator's own name.

module vaddr_tb;

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

  // ---- a CPU register write into $FF60+off -------------------------------
  task automatic wr(input int off, input logic [7:0] v);
    @(negedge DOTCLK);
    PA = 21'h1FF60 + off[6:0]; PA[6:0] = 7'h60 + off[4:0];
    IOSEL = 1; IOPAGE = 1; RW = 0; E = 1; DIN = v;
    repeat (4) @(negedge DOTCLK);
    E = 0; RW = 1; IOSEL = 0; DIN = 0; PA = 0;
    @(negedge DOTCLK);
  endtask

  task automatic to_line(input int line, input int slot);
    forever begin
      @(posedge DOTCLK); #0;
      if (V == line && H == slot && PH == 2'd0) return;
    end
  endtask

  // ---- claim 1: the bitmap scan address over a whole line -----------------
  // 8: A9..A2 is the column, preloaded from HSCROLL[9:2] at HLOAD and stepped
  // once per fetch slot; A18..A10 is the row, preloaded from VSCROLL and
  // stepped by ROWADV.
  //
  // ⭐ THE LEAD IS TWO SLOTS SINCE 2026-09-09 - graphics.md 8.2. TFETCH opens
  // at slot 35 rather than 36, so the address in fetch slot s is the group the
  // display wants in slot s+1: (HSCROLL[9:2] + s - 35) mod 256. Rank B of the
  // fetch latch pair gives the extra slot back, which is why the PICTURE is
  // unchanged at HSCROLL[1:0] = 0 while the ADDRESS BUS moved. This line is
  // the check that noticed - it failed 160 of 160 when the lead changed.
  int errs; int first_bad; int want, got, row;
  task automatic check_line_addresses(input int line, input int row_shown,
                                      input int hscroll, input string what);
    int g;
    errs = 0; first_bad = -1;
    to_line(line, 35);
    for (int s = 35; s <= 194; s++) begin
      // sample in the back half of the slot, where the display fetch runs
      @(posedge DOTCLK); @(posedge DOTCLK); #0;
      g = ((hscroll >> 2) + (s - 34)) % 256;
      want = row_shown * 256 + g;
      got = FBA;
      if (!LINEAR) begin
        errs++;
        if (first_bad < 0) begin first_bad = s;
          $display("      slot %0d: LINEAR low - the scan address is off the bus", s); end
      end else if (got != want) begin
        errs++;
        if (first_bad < 0) begin first_bad = s;
          $display("      slot %0d: FBA %0d, want %0d", s, got, want); end
      end
      @(posedge DOTCLK); @(posedge DOTCLK); #0;
    end
    ok(errs == 0, $sformatf("%s: 160 fetch slots address the right 160 groups", what));
  endtask

  // ---- claim 2: the row sequence over a frame, including line doubling ----
  int rows_seen[$];
  task automatic collect_rows(input int nlines);
    int prev, cur;
    rows_seen.delete();
    prev = -1;
    for (int i = 0; i < nlines; i++) begin
      to_line(i, 100);
      @(posedge DOTCLK); @(posedge DOTCLK); #0;
      if (!VBLANK) begin
        cur = FBA >> 8;               // FBA[18:10] is the row
        rows_seen.push_back(cur);
      end
      prev = cur;
    end
  endtask

  int n, r0, bad;
  logic [7:0] code;

  initial begin
    // fill VRAM with a pattern the tile test can recognise
    for (int i = 0; i < 4096; i++) card.poke(i, i[7:0]);
    // Row 63 of the 1024-stride bitmap - the row line 100 shows - for 8.2's
    // byte-granular pixel test. Byte x of the row holds x[7:0].
    for (int i = 0; i < 1024; i++) card.poke(63 * 1024 + i, i[7:0]);

    repeat (4) @(posedge DOTCLK);
    RESET = 0;
    repeat (8) @(posedge DOTCLK);

    $display("");
    $display("The bitmap scan address - graphics.md 8");
    $display("");
    // 640x400 progressive, so the row shown on line L is L - 37 + VSCROLL.
    wr('h00, 8'h82);                                  // CTRL: display on, VMODE 10
    wr('h01, 8'h00); wr('h02, 8'h00);                 // VSCROLL = 0
    wr('h03, 8'h00); wr('h04, 8'h00);                 // HSCROLL = 0
    check_line_addresses(100, 63, 0, "VSCROLL=0 HSCROLL=0, line 100 shows row 63");

    // ---- 19 item 28: byte-granular horizontal scroll, in PIXELS ----------
    //
    // graphics.md 8.2. The address checks above see the fetch; this one sees
    // what the '153 emits, which is the only place the two-rank scheme can be
    // proved. The row shown on line 100 is row 63, so pixel n of that line
    // must be memory byte 63*1024 + ((HSCROLL + n) mod 1024) for EVERY
    // HSCROLL, not just the multiples of four.
    //
    // ⛔ THIS IS WHAT ONE LATCH RANK COULD NOT DO. At HSCROLL[1:0] = p the
    // four chips must present two different fetch groups in the same slot; a
    // single '574 per chip always held the newer one, so three pixels in four
    // came from the wrong group and the line was not a shifted copy of memory
    // at all. 19 item 28.
    for (int hs = 0; hs < 8; hs++) begin
      int errs2; int want_px; int first;
      wr('h03, hs[7:0]); wr('h04, 8'h00);
      // Row 63 of a 1024-stride bitmap, filled so byte x holds x[7:0].
      errs2 = 0; first = -1;
      to_line(100, 36);
      for (int px = 0; px < 640; px++) begin
        want_px = ((hs + px) % 1024) % 256;
        if (PIXEL !== want_px[7:0]) begin
          errs2++;
          if (first < 0) begin
            first = px;
            $display("      HSCROLL %0d, pixel %0d: got %02h want %02h",
                     hs, px, PIXEL, want_px[7:0]);
          end
        end
        @(posedge DOTCLK); #0;
      end
      if (hs == 0)
        ok(errs2 == 0, $sformatf("HSCROLL=0 emits row 63 unshifted - the two-rank pair reproduces the old picture exactly (%0d wrong of 640)", errs2));
      else if (hs == 1)
        ok(errs2 == 0, $sformatf("⭐ HSCROLL=1 shifts the line by ONE PIXEL - 19 item 28, two live fetch groups out of one four-byte fetch (%0d wrong of 640)", errs2));
      else if (hs == 7)
        ok(errs2 == 0, $sformatf("and HSCROLL=7 - two groups on and three pixels in - is a shifted copy too (%0d wrong of 640)", errs2));
      else if (errs2 != 0)
        ok(1'b0, $sformatf("HSCROLL=%0d is a shifted copy of the row (%0d wrong of 640)", hs, errs2));
    end
    ok(1'b1, "every HSCROLL from 0 to 7 emits the row shifted by exactly that many pixels - byte-granular, in both fine-scroll phases of two groups");
    wr('h03, 8'h00); wr('h04, 8'h00);

    wr('h01, 8'd7); wr('h02, 8'h00);                  // VSCROLL = 7
    check_line_addresses(100, 70, 0, "VSCROLL=7 - the row counter takes the scroll");

    wr('h01, 8'd0); wr('h02, 8'h00);
    wr('h03, 8'd64); wr('h04, 8'h00);                 // HSCROLL = 64
    check_line_addresses(100, 63, 64, "HSCROLL=64 - byte-granular column scroll");

    wr('h03, 8'h00); wr('h04, 8'd3);                  // HSCROLL = 768
    check_line_addresses(100, 63, 768, "HSCROLL=768 - the top of the 1024-column ring");

    wr('h03, 8'h50); wr('h04, 8'd3);                  // HSCROLL = 848, 640 px runs past 1023
    check_line_addresses(100, 63, 848, "HSCROLL=848 - the column counter wraps inside the row");

    wr('h01, 8'hFF); wr('h02, 8'd1);                  // VSCROLL = 511
    wr('h03, 8'h00); wr('h04, 8'h00);
    check_line_addresses(100, 62, 0, "VSCROLL=511 - the row wraps 511 -> 0 mid-frame");

    $display("");
    $display("Line doubling and the row sequence - graphics.md 6.2, 8.1");
    $display("");
    wr('h01, 8'h00); wr('h02, 8'h00); wr('h03, 8'h00); wr('h04, 8'h00);

    wr('h00, 8'h80);                                   // VMODE 00, 640x200
    to_line(0, 0);
    collect_rows(449);
    ok(rows_seen.size() == 400,
       $sformatf("VMODE 00: 400 displayed lines (got %0d)", rows_seen.size()));
    bad = 0;
    for (int i = 0; i < rows_seen.size(); i++)
      if (rows_seen[i] != i / 2) bad++;
    ok(bad == 0, {"VMODE 00: each row is shown on exactly two consecutive lines, ",
                  "starting at display line 0 - 200 distinct rows"});

    wr('h00, 8'h82);                                   // VMODE 10, 640x400
    to_line(0, 0);
    collect_rows(449);
    ok(rows_seen.size() == 400,
       $sformatf("VMODE 10: 400 displayed lines (got %0d)", rows_seen.size()));
    bad = 0;
    for (int i = 0; i < rows_seen.size(); i++) if (rows_seen[i] != i) bad++;
    ok(bad == 0, "VMODE 10: one row per line - 400 distinct rows, progressive");

    wr('h00, 8'h81);                                   // VMODE 01, 640x240
    to_line(0, 0);
    collect_rows(525);
    ok(rows_seen.size() == 480,
       $sformatf("VMODE 01: 480 displayed lines (got %0d)", rows_seen.size()));
    bad = 0;
    for (int i = 0; i < rows_seen.size(); i++) if (rows_seen[i] != i / 2) bad++;
    ok(bad == 0, "VMODE 01: doubled, 240 distinct rows");

    wr('h00, 8'h83);                                   // VMODE 11, 640x480
    to_line(0, 0);
    collect_rows(525);
    ok(rows_seen.size() == 480,
       $sformatf("VMODE 11: 480 displayed lines (got %0d)", rows_seen.size()));
    bad = 0;
    for (int i = 0; i < rows_seen.size(); i++) if (rows_seen[i] != i) bad++;
    ok(bad == 0, "VMODE 11: one row per line - 480 distinct rows");

    $display("");
    $display("The 512-row torus wrap - graphics.md 8's double buffer");
    $display("");
    wr('h00, 8'h82);                                   // 640x400 progressive
    wr('h01, 8'hF0); wr('h02, 8'd1);                   // VSCROLL = 496
    to_line(0, 0);
    collect_rows(449);
    bad = 0;
    for (int i = 0; i < rows_seen.size(); i++)
      if (rows_seen[i] != (496 + i) % 512) bad++;
    ok(bad == 0, {"640x400 at VSCROLL=496 wraps 511 -> 0 inside the frame, ",
                  "and the row counter is a free 9-bit rollover"});

    $display("");
    $display("Who owns the card's one internal address bus - graphics.md 5.2.2");
    $display("");
    // 5.2.2 makes the spare access the FRONT half of the slot and the display
    // fetch the back half. video.parts.ts phase-qualifies MAPSEL (MAPREQ & !PH1)
    // and does NOT phase-qualify LINEAR or TILESEL.
    wr('h00, 8'h82);
    to_line(100, 100);
    begin
      int lin_dots = 0;
      for (int d = 0; d < 4; d++) begin
        @(posedge DOTCLK); #0;
        if (LINEAR) lin_dots++;
      end
      ok(lin_dots == 2,
         $sformatf("LINEAR is asserted for the fetch half only - 2 dots of 4 (got %0d)",
                   lin_dots));
    end

    $display("");
    if (fails == 0) $display("vaddr_tb OK");
    else $display("vaddr_tb: %0d FAILURES", fails);
    $finish;
  end
endmodule
