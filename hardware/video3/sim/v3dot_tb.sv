// video3's raster, run for whole frames in each of plan §2.2's four VMODE
// codes, against the Verilog generated from the FITTED term lists.
//
// ⭐ This runs v3dot on its own, which is honest about what it proves: the
// part holds the whole dot path - hcount, vcount, the sync trio, the mode
// decode, the sprite and the arbiter - so the raster is entirely inside one
// package and needs no board around it. What it does NOT reach is plan §14
// item 8, the cadence: five requesters against one spare access a slot is a
// claim about v3dot AND v3scan AND v3ptr AND the SRAMs, and that needs the
// card wrapper this file deliberately does not pretend to be.
//
// A comment line here must never begin with the simulator's own name.

module v3dot_tb;

  logic CLK25 = 0;
  always #1 CLK25 <= ~CLK25;

  logic RESET = 1;
  logic D0=0,D1=0,D2=0,D3=0,D4=0,D5=0,D6=0,D7=0;
  logic REGWR = 0, RA0=0, RA1=0, RA2=0, RA3=0, RA4=0;
  // ⛔ RMAP and RRD were inputs until 2026-09-19: the map fetch's request is
  // this part's own MAPREQ now and the prefetch's is v3host's RDREQ. This
  // bench declared the old two and failed to compile from 4a7d398 until the
  // card bench was written - check:video was not run after that change.
  logic RDREQ=0, RCPY=0, SPANBUSY=0, PALTURN=0, SQ0=0, SQ1=0;

  // Every cell of the part is a port, buried ones included, so the counters
  // are watchable, and `.*` needs every one of them declared here by name.
  // ⭐ GENERATED between the two markers by v3portmap.ts (gen.ts) from
  // v3dot.cpld.ts - this list was typed, and every change to the part broke
  // the bench until someone retyped it (4a7d398 went unnoticed for a day).
  // ---- generated: every port of v3dot ----
  wire LDCTRL, LDHSL, LDSPRX, LDSPRY, LDSPRH, LDPIDXL, LDPIDXH, LDPDATL, LDPDATH, DP0, DP1,
       HC0, HC1, HC2, HC3, HC4, HC5, HC6, HC7, VC0, VC1, VC2, VC3, VC4, VC5, VC6, VC7, VC8,
       VC9, M0, CT0, CT1, CT2, CT3, CT4, CT5, CT7, HS0, HS1, HS2, SX0, SX1, SX2, SX3, SX4,
       SX5, SX6, SX7, SX8, SX9, SY0, SY1, SY2, SY3, SY4, SY5, SY6, SY7, SY8, SPREN, SHC0,
       SHC1, SHC2, SHC3, SHC4, SHC5, SHC6, SHC7, SHC8, SHC9, SVC0, SVC1, SVC2, SVC3, SVC4,
       SVC5, SVC6, SVC7, SVC8, SHQ, SVQ, SR0, SR1, SR2, SR3, SR4, SPRA0, SPRA0_OE, SPRA1,
       SPRA1_OE, SLOTTICK, HBLANK, HSYNC, VSYNC, VBLANK, BLANK, FRAMEEND, LINETICK, SPARE,
       HLOAD, VLOAD, ROWADV, DBLHOLD, MWIN, MRQ, MAPREQ, MUXSEL0, MUXSEL1, PIXOE, ATOE,
       PIDXOE, SPRAOE, BD1, OMR, OEA0, OEB0, OEA1, OEB1, OEA2, OEB2, SPRACT, SPRSH, SPRLD,
       FBA2, FBA2_OE, FBA3, FBA3_OE, FBA4, FBA4_OE, FBA5, FBA5_OE, GMAP, GRD, GCPY, GSPN,
       FBOEPTR, HLAST, ACTIVE, VACTIVE, VBLANKRAW, VTC, SPRVHIT, SPRHIT, SPRROW, VMODE0,
       MODE0, MODE1, WM0, WM1;
  // ---- end of generated ports ----

  v3dot dut (.*);

  wire [7:0] H = {HC7,HC6,HC5,HC4,HC3,HC2,HC1,HC0};
  wire [9:0] V = {VC9,VC8,VC7,VC6,VC5,VC4,VC3,VC2,VC1,VC0};
  wire [1:0] DP = {DP1, DP0};
  wire [7:0] CTRL = {CT7,1'b0,CT5,CT4,CT3,CT2,CT1,CT0};   // b6 is v3host's (IRQEN)

  int fails = 0;
  task automatic ok(input bit c, input string what);
    if (!c) begin $display("FAIL  %s", what); fails++; end
    else      $display("ok    %s", what);
  endtask

  // ⚠ EVERY wait in this file carries a bound and fails on exhaustion.
  // graphics.md's own lesson, learned when vsync_tb spun for half an hour on
  // a conjunction that had become unsatisfiable.
  task automatic wait_for(input string what, ref logic sig, input bit level, input int bound);
    int n = 0;
    while (sig !== level) begin
      @(posedge CLK25);
      n++;
      if (n > bound) begin
        $display("FAIL  %s: never reached %0d in %0d dots", what, level, bound);
        fails++;
        return;
      end
    end
  endtask

  // write CTRL over the register broadcast: RA4..RA0 = 0, REGWR high
  task automatic set_ctrl(input logic [7:0] v);
    @(negedge CLK25);
    {D7,D6,D5,D4,D3,D2,D1,D0} = v;
    {RA4,RA3,RA2,RA1,RA0} = 5'd0;
    REGWR = 1;
    @(posedge CLK25);
    @(negedge CLK25);
    REGWR = 0;
  endtask

  // One whole line: dots between LINETICKs, and the HSYNC width.
  //
  // ⚠ LINETICK AND FRAMEEND ARE SLOT-WIDE, NOT DOT-WIDE.  H counts SLOTS of
  // four dots (DP is the dot phase), so every tick this part produces is high
  // for four CLK25 edges.  A loop that breaks on `if (LINETICK)` immediately
  // after `@(posedge LINETICK)` therefore measures a line as ONE dot - which
  // is what it did, and it reads exactly like a dead counter.
  task automatic measure_line(output int dots, output int sync_lo, output int sync_hi);
    int n = 0, lo = 0, hi = 0;
    @(posedge LINETICK);
    @(negedge LINETICK);
    forever begin
      @(posedge CLK25);
      n++;
      if (HSYNC) hi++; else lo++;
      if (LINETICK) break;
      if (n > 4000) begin $display("FAIL  a line never ended"); fails++; break; end
    end
    dots = n; sync_lo = lo; sync_hi = hi;
  endtask

  // the lines of one frame, and how many of them are active
  task automatic measure_frame(output int lines, output int act);
    lines = 0; act = 0;
    @(posedge FRAMEEND);
    @(negedge FRAMEEND);
    forever begin
      @(posedge LINETICK);
      lines++;
      if (VACTIVE) act++;
      // ⚠ FRAMEEND AND LINETICK ARE BOTH ONE DOT WIDE and fall together -
      // FRAMEEND is LINETICK qualified by VTC - so it has to be read WHILE
      // LINETICK is high. Reading it after the negedge is always false, and
      // the loop then runs to its own bound and reports the design as
      // never ending a frame.
      if (FRAMEEND) begin @(negedge LINETICK); break; end
      @(negedge LINETICK);
      if (lines > 900) begin
        $display("FAIL  a frame never ended"); fails++; break;
      end
    end
  endtask

  int dots, slo, shi, lines, act, vm;
  // plan §2.2: 800 dots a line always; 449 lines in VMODE 00/10 and 525 in
  // 01/11, and the active height is 200/240/400/480 ROWS - which is 400/480
  // LINES in every mode, because 00 and 01 double every row.
  int want_lines [4] = '{449, 525, 449, 525};
  int want_act   [4] = '{400, 480, 400, 480};

  initial begin
    repeat (8) @(posedge CLK25);
    RESET = 0;
    repeat (8) @(posedge CLK25);
`ifdef TRACE
    begin
      int i;
      for (i = 0; i < 40; i++) begin
        @(posedge CLK25);
        $display("t%0d H=%0d DP=%0d LINETICK=%b SLOTTICK=%b HSYNC=%b HBLANK=%b ACTIVE=%b V=%0d",
                 i, H, DP, LINETICK, SLOTTICK, HSYNC, HBLANK, ACTIVE, V);
      end
      $finish;
    end
`endif

    for (vm = 0; vm < 4; vm++) begin
      // CTRL: display on, VBL IRQ on, bitmap, this VMODE
      set_ctrl(8'hC0 | vm[7:0]);
      // let the frame in progress finish so the family change lands
      repeat (2) @(posedge FRAMEEND);

      measure_line(dots, slo, shi);
      ok(dots == 800, $sformatf("VMODE %0d: a line is 800 dots (got %0d)", vm, dots));
      ok(shi == 96 || shi == 96, $sformatf("VMODE %0d: HSYNC is 96 dots (got %0d)", vm, shi));

      measure_frame(lines, act);
      ok(lines == want_lines[vm],
         $sformatf("VMODE %0d: %0d lines a frame (got %0d)", vm, want_lines[vm], lines));
      // ⚠ VACTIVE counts the LINES the picture is on.  VMODE 00 and 01 double
      // every row, so 200 rows are 400 lines and 240 are 480; 10 and 11 do not.
      ok(act == want_act[vm],
         $sformatf("VMODE %0d: %0d active lines (got %0d)", vm, want_act[vm], act));
    end

    // ⭐ M0, the frame-end latch: a family change is taken where the frame
    // ends (plan §2.2), so M0 must only move at FRAMEEND.
    set_ctrl(8'hC0);
    @(posedge FRAMEEND);
    ok(1, "the four VMODE codes all ran to a frame end");

    $display("%0d claims, %0d failed", 4*4 + 1, fails);
    $finish;
  end
endmodule
