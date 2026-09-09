// The video card's raster, run for whole frames in each of graphics.md 13's
// four VMODE codes, against the Verilog generated from the fitted term lists.
//
// check:sync already sweeps the sync trio's fuses against sync.model.ts, and
// check:cadence walks a frame against the same term lists in TypeScript. What
// neither does is run the MERGED part: vctrl is hgen + vgen + vdec + seqph +
// seqctl + arb + CTRL + the cadence, and the things that only exist after the
// merge - HPOL from VMODE0, CE from SLOTTICK, the CTRL register itself - are
// exactly the ones no standalone check can see.
//
// A comment line here must never begin with the simulator's own name.

module vsync_tb;

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

  // ⭐ The whole card, not vctrl on its own. The sync trio is inside a part
  // that also holds CTRL, and CTRL is written through rfa's decode - so
  // "which VMODE is selected" is a claim about three packages now, which is
  // exactly the seam design-review2.md V-1 found the card's registers missing
  // from.
  video_card card (.*);

  int fails = 0;
  task automatic ok(input bit good, input string claim);
    if (good) $display("ok    %s", claim);
    else begin fails++; $display("FAIL  %s", claim); end
  endtask

  // ---- one CTRL write, over the bus, through rfa's decode ----------------
  task automatic set_ctrl(input logic [7:0] v);
    @(negedge DOTCLK);
    PA = 0; PA[6:0] = 7'h60;
    IOSEL = 1; IOPAGE = 1; RW = 0; E = 1; DIN = v;
    repeat (6) @(negedge DOTCLK);
    E = 0; RW = 1; IOSEL = 0; DIN = 0; PA = 0;
    repeat (2) @(negedge DOTCLK);
  endtask

  // ---- measurement ---------------------------------------------------------
  int dots, lines;
  int hsync_dots, hblank_dots, active_dots;
  int vsync_lines, vblank_lines, active_lines;
  bit hsync_lo_in_window, hsync_hi_out;
  bit vsync_asserted_level;
  int irq_pulses;
  bit prev_hsync, prev_vsync, prev_irq;
  int slot;

  // Wait for the start of a frame: the dot on which V returns to 0.
  function automatic int vnum();
    return V;
  endfunction
  function automatic int hnum();
    return H;
  endfunction

  task automatic to_frame_start();
    // V wraps to 0 at VTC; wait for the transition into line 0 slot 0.
    forever begin
      @(posedge DOTCLK); #0;
      if (vnum() == 0 && hnum() == 0 && SLOTTICK == 0 && PH == 2'd0) return;
    end
  endtask

  // Count one whole frame. Everything is sampled after the clock edge.
  task automatic measure_frame(input int want_lines, input int want_active);
    int line_dots;
    dots = 0; lines = 0;
    hsync_dots = 0; hblank_dots = 0; active_dots = 0;
    vsync_lines = 0; vblank_lines = 0; active_lines = 0;
    line_dots = 0;
    begin
      int v_prev = 0;   // we start AT line 0, so do not count entering it
      forever begin
        @(posedge DOTCLK); #0;
        dots++;
        line_dots++;
        if (!HBLANK && !VBLANK) active_dots++;
        if (!HBLANK) hblank_dots++;                 // counts ACTIVE h dots
        if (HSYNC == (VMODE[0] ? 1'b1 : 1'b0)) hsync_dots++;   // asserted level
        if (vnum() != v_prev) begin
          v_prev = vnum();
          lines++;
          if (!VBLANK) active_lines++;
          if (VSYNC == (VMODE[0] ? 1'b0 : 1'b1)) vsync_lines++;
        end
        if (dots > 1 && vnum() == 0 && hnum() == 0 && PH == 2'd0) break;
      end
    end
  endtask

  string mode_name;

  task automatic run_mode(input logic [1:0] vmode, input int want_lines,
                          input int want_active, input bit want_vsync_pos,
                          input string nm);
    mode_name = nm;
    set_ctrl({6'b0, vmode});
    to_frame_start();
    measure_frame(want_lines, want_active);
    ok(dots == want_lines * 800,
       $sformatf("%s: frame is %0d dots (want %0d)", nm, dots, want_lines*800));
    ok(lines == want_lines,
       $sformatf("%s: %0d lines (want %0d)", nm, lines, want_lines));
    ok(active_lines == want_active,
       $sformatf("%s: %0d active lines (want %0d)", nm, active_lines, want_active));
    ok(active_dots == want_active * 640,
       $sformatf("%s: %0d active dots (want %0d)", nm, active_dots, want_active*640));
    ok(hblank_dots == want_lines * 640,
       $sformatf("%s: 640 unblanked dots on every one of %0d lines", nm, want_lines));
  endtask

  // ---- polarity, measured at the connector --------------------------------
  // graphics.md 6.2.1: HSYNC is NEGATIVE in both families, VSYNC positive in
  // the 449-line family and negative in the 525-line one. Sampled inside the
  // pulse window, which sync.timing.ts puts at h <= 23 and v <= 1.
  bit h_level_in_pulse, v_level_in_pulse;
  task automatic sample_polarity();
    // inside HSYNC's window
    forever begin @(posedge DOTCLK); #0; if (hnum() == 10) break; end
    h_level_in_pulse = HSYNC;
    // inside VSYNC's window
    forever begin @(posedge DOTCLK); #0; if (vnum() == 1 && hnum() == 100) break; end
    v_level_in_pulse = VSYNC;
  endtask

  initial begin
    repeat (4) @(posedge DOTCLK);
    RESET = 0;
    repeat (8) @(posedge DOTCLK);

    $display("");
    $display("Raster geometry - graphics.md 6.2's four VMODE codes");
    $display("");
    run_mode(2'b00, 449, 400, 1, "VMODE 00  640x200 line-doubled");
    run_mode(2'b01, 525, 480, 0, "VMODE 01  640x240 line-doubled");
    run_mode(2'b10, 449, 400, 1, "VMODE 10  640x400 progressive");
    run_mode(2'b11, 525, 480, 0, "VMODE 11  640x480 progressive");

    $display("");
    $display("Sync widths, shared horizontal timing");
    $display("");
    set_ctrl(8'h00); to_frame_start();
    begin
      int hs = 0, n = 0;
      forever begin
        @(posedge DOTCLK); #0;
        if (hnum() <= 23) hs++;
        n++;
        if (n == 800) break;
      end
      ok(hs == 96, $sformatf("HSYNC window is %0d dots (want 96)", hs));
    end

    $display("");
    $display("Sync POLARITY - graphics.md 6.2.1, which is how the monitor picks");
    $display("the vertical format. Both families are negative-H.");
    $display("");
    set_ctrl(8'h00); to_frame_start(); sample_polarity();
    ok(h_level_in_pulse == 1'b0,
       $sformatf("VMODE 00: HSYNC is LOW through its pulse - negative (got %0d)",
                 h_level_in_pulse));
    ok(v_level_in_pulse == 1'b1,
       $sformatf("VMODE 00: VSYNC is HIGH through its pulse - positive (got %0d)",
                 v_level_in_pulse));

    set_ctrl(8'h01); to_frame_start(); sample_polarity();
    ok(h_level_in_pulse == 1'b0,
       $sformatf("VMODE 01: HSYNC is LOW through its pulse - negative (got %0d)",
                 h_level_in_pulse));
    ok(v_level_in_pulse == 1'b0,
       $sformatf("VMODE 01: VSYNC is LOW through its pulse - negative (got %0d)",
                 v_level_in_pulse));

    set_ctrl(8'h03); to_frame_start(); sample_polarity();
    ok(h_level_in_pulse == 1'b0,
       $sformatf("VMODE 11: HSYNC is LOW through its pulse - negative (got %0d)",
                 h_level_in_pulse));

    $display("");
    $display("BLANK reaches the post-LUT '273 (9.2) whenever either axis blanks");
    $display("");
    set_ctrl(8'h00); to_frame_start();
    begin
      bit bad = 0;
      int n = 0;
      forever begin
        @(posedge DOTCLK); #0;
        if (BLANK != (HBLANK | VBLANK)) bad = 1;
        n++;
        if (n == 800 * 449) break;
      end
      ok(!bad, "BLANK = HBLANK # VBLANK over a whole frame");
    end

    $display("");
    if (fails == 0) $display("vsync_tb OK");
    else $display("vsync_tb: %0d FAILURES", fails);
    $finish;
  end
endmodule
