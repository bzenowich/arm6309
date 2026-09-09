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
  // stepped by ROWADV. The group the display wants in fetch slot s is
  // (HSCROLL[9:2] + s - 36) mod 256 of the row this line is showing.
  int errs; int first_bad; int want, got, row;
  task automatic check_line_addresses(input int line, input int row_shown,
                                      input int hscroll, input string what);
    int g;
    errs = 0; first_bad = -1;
    to_line(line, 36);
    for (int s = 36; s <= 195; s++) begin
      // sample in the back half of the slot, where the display fetch runs
      @(posedge DOTCLK); @(posedge DOTCLK); #0;
      g = ((hscroll >> 2) + (s - 36)) % 256;
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
