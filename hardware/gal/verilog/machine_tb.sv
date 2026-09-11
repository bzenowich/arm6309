// THE MACHINE RUNS ITS OWN SOFTWARE, AND THE PICTURE IS SAMPLED AT THE
// CONNECTOR.
//
// software/boot/boot.asm, assembled by A09 (software/tools/mkrom.sh), executed
// by mc6809e.v on mainboard.v with video_card.v in a slot. U9, U10 and the
// video card's three ATF1508AS are generated from the same term lists
// hardware/gal/jedec/cupl.ts compiles for the fitter. ⚠ U3 and U6 are NOT: they
// are the hand-written gal/mmu.v and gal/clkdec.v, checked against their fuse
// maps by check:sim and jedec/cupl.check.ts rather than generated.
//
// ⚠ EVERY GENERATED PART IS IN ASSERTED SENSE, and the wrappers invert the
// backplane lines by hand, so no claim here can see a pin declared with the
// wrong polarity - nine of them passed this bench until 2026-09-11.
// gal/pins.check.ts is what holds pin senses.
//
// WHAT IS NEW HERE, and it is the reason this file exists rather than a
// thirteenth register-level testbench: nothing before it ran an INSTRUCTION.
// mainboard_tb walks machine.md 7.2's boot sequence as literal bus cycles and
// vspan_tb writes video registers from a task, so both check that the parts do
// what their author thought when driven the way their author expected. This
// one hands the bus to a CPU core somebody else wrote and lets the ROM drive.
//
// THE SCREENSHOT IS TAKEN FROM RGB, BLANK, HSYNC AND VSYNC AND NOTHING ELSE -
// the four signals that leave the card. It uses no internal counter, no H, no
// V and no VMODE-derived geometry, because a capture that reads the card's own
// idea of where it is cannot disagree with it. Lines are delimited by HSYNC,
// frames by VSYNC, and pixels are the dots in which BLANK is not asserted.
//
// A comment line here must never begin with the simulator's own name.

module machine_tb;

  // ---- 25.175 MHz. One dot per 2 timesteps; E is this divided by 12. ------
  logic CLK25 = 0;
  always #1 CLK25 <= ~CLK25;

  logic n_reset = 0, fast_e = 0;

  wire [15:0] RGB;
  wire BLANK, HSYNC, VSYNC;
  wire [7:0] PIXEL;
  wire [7:0] H;
  wire [9:0] V;
  wire e, q, run, rw, lic, avma;
  wire [15:0] la;
  wire [7:0] cpu_dout, cpu_din;
  wire [24:0] pa;
  wire n_iosel, n_iopage_bp, wait_asserted;
  wire [18:0] WPTR;
  wire [1:0] VMODE;
  wire SPANBUSY, VBLANK, HBLANK;
  wire bus_conflict, pa_conflict, vram_read;

  machine #(.SIMMS(4)) m (.*);

  int fails = 0;
  int claims = 0;
  task automatic ok(input bit good, input string claim);
    claims++;
    if (good) $display("ok    %s", claim);
    else begin fails++; $display("FAIL  %s", claim); end
  endtask

  // ---- boot.asm's progress port -------------------------------------------
  // $FF2F, in machine.md 3's free block. Sampled at E-fall, which is the edge
  // a 6809E write's data is guaranteed on (graphics.md 3.1).
  logic [7:0] progress = 8'h00;
  int         progress_writes = 0;
  always @(negedge e)
    if (!n_iosel && pa[7:0] == 8'h2F && !rw) begin
      progress <= cpu_dout;
      progress_writes++;
    end

  // ---- the three things that must never happen ----------------------------
  // Sticky, because they are single-dot events in a run of millions and a
  // sampled check would miss them. design-review2.md 10: a model that ORs its
  // drivers cannot see a bus fight, so machine.v does not OR them and this
  // watches what it reports instead.
  bit saw_bus_conflict = 0, saw_pa_conflict = 0;
  bit saw_lrun = 0;
  always @(posedge CLK25) if (m.vid_lrun) saw_lrun = 1;
  always @(posedge CLK25) begin
    if (bus_conflict)      saw_bus_conflict = 1;
    if (pa_conflict)       saw_pa_conflict  = 1;
  end

  // How much of the run the card spent holding the CPU. graphics.md 7.4's
  // /WAIT is a backstop boot.asm is written not to need - it polls VSTAT - so
  // a nonzero count here means the polling rule is not sufficient.
  int wait_dots = 0;
  always @(posedge CLK25) if (wait_asserted) wait_dots++;
  // ... and how much of it was a VDATA access waiting, which the window's
  // decode cannot produce: the cycle is in the I/O page.
  int vdata_wait_dots = 0;
  always @(posedge CLK25) if (wait_asserted && !n_iosel && pa[7:0] == 8'h75) vdata_wait_dots++;

  // Work counters, so a stall says WHAT stalled rather than only that it did.
  int vram_writes = 0, vstat_reads = 0, reg_writes = 0, vram_reads = 0;
  int vdata_reads = 0, vdata_writes = 0;
  always @(negedge e) begin
    // +$15 VDATA, the VRAM port in the I/O page - graphics.md 19 item 47
    if (rw && !n_iosel && pa[7:0] == 8'h75) vdata_reads++;
    if (!rw && !n_iosel && pa[7:0] == 8'h75) vdata_writes++;
    if (!rw && n_iopage_bp && !pa[20] && pa[19]) vram_writes++;
    if (vram_read) vram_reads++;
    if (rw && !n_iosel && pa[7:0] == 8'h73) vstat_reads++;
    if (!rw && !n_iosel && pa[7:5] == 3'b011) reg_writes++;
  end

  int e_cycles = 0;
  always @(negedge e) e_cycles++;



  // ---- +hb=N: a heartbeat every N dots ------------------------------------
  // What it is for: E can be HELD, and a testbench that only prints on E's own
  // edge goes silent exactly when the interesting thing happens. This ticks on
  // the dot clock, which nothing can stop.
  int hb_every = 0, hb = 0;
  /* ⭐ VBLANK's duty cycle, because it is what boot.asm's `settle` waits on and
   * a stuck poll is indistinguishable from a slow one without it. 49 blanked
   * lines of 449 is 10.9%; the first run after machine.v's read fix measured
   * 11.4%, which is how the signal was cleared of suspicion and the read path
   * convicted. */
  int vbl_hi = 0, vbl_lo = 0;
  always @(posedge CLK25) if (VBLANK) vbl_hi++; else vbl_lo++;
  initial void'($value$plusargs("hb=%d", hb_every));
  always @(posedge CLK25) begin
    hb++;
    if (hb_every > 0 && hb % hb_every == 0)
      $display("      hb %0d dots: %0d E, %0d /WAIT dots, BUSY=%b VBL=%b vstat=%02h WPTR=%0d LA=%04h prog=%02h",
               hb, e_cycles, wait_dots, SPANBUSY, VBLANK, m.vstat, WPTR, la, progress);
  end

  // ---- +trace=N: the first N bus cycles, as the CPU sees them -------------
  // Not decoration. The first thing this testbench found was a machine that
  // fetched nothing, and a bus trace is the only instrument that says whether
  // the address, the byte or the clock is the one that is wrong.
  int trace_n = 0;
  int trace_after = -1;          // +after=N: start the trace when progress hits N
  int trace_base = 0;
  initial void'($value$plusargs("trace=%d", trace_n));
  initial void'($value$plusargs("after=%d", trace_after));
  always @(negedge e)
    if (trace_after >= 0 && progress == trace_after[7:0] && trace_base == 0)
      trace_base = e_cycles;
  always @(negedge e)
    if ((trace_after < 0 && e_cycles <= trace_n)
        || (trace_base != 0 && e_cycles <= trace_base + trace_n))
      $display("      %6d  E| LA=%04h %s PA=%07h D=%02h  BUSY=%b WAIT=%b WPTR=%0d",
               e_cycles, la, rw ? "R" : "W", pa[24:0],
               rw ? cpu_din : cpu_dout, SPANBUSY, wait_asserted, WPTR);

  // ---- a BOUNDED wait, because a marker that never arrives must not hang ---
  // CLAUDE.md's rule, and vsync_tb's: every unbounded wait carries an
  // iteration bound and fails loudly on exhaustion. `budget` is in E cycles,
  // which is the machine's own unit of progress.
  bit timed_out;
  task automatic wait_progress(input logic [7:0] want, input int budget,
                               input string what);
    int spent;
    spent = 0;
    timed_out = 0;
    while (progress !== want) begin
      @(negedge e);
      spent++;
      if (spent > budget) begin
        timed_out = 1;
        $display("FAIL  %s: progress stuck at $%02h after %0d E cycles (want $%02h)",
                 what, progress, budget, want);
        fails++;
        claims++;
        return;
      end
    end
    claims++;
    $display("ok    %s (%0d E cycles)", what, spent);
  endtask

  /* --------------------------------------------------------------------- *
   * The screenshot.
   *
   * 640 x 200 is 128,000 pixels; the capture array is sized for the widest
   * active line VMODE 11 can produce so the geometry is measured rather than
   * assumed.
   * --------------------------------------------------------------------- */
  localparam int MAXW = 1024;
  localparam int MAXH = 512;
  logic [15:0] shot [0:MAXH-1][0:MAXW-1];
  int          linew [0:MAXH-1];
  int          shot_lines;
  int          shot_w_min, shot_w_max;

  // The asserted level of each sync, at the connector. graphics.md 6.2.1 makes
  // it part of the mode; vsync_tb 160 measures it, and this reads the same
  // rule off VMODE rather than repeating the measurement.
  wire hs_on = VMODE[0] ? 1'b1 : 1'b0;
  wire vs_on = VMODE[0] ? 1'b0 : 1'b1;

  bit shot_overflow;
  task automatic capture_frame(input int budget);
    int dots, x;
    bit prev_hs, prev_vs;
    shot_lines = 0; x = 0; dots = 0; shot_overflow = 0;
    for (int i = 0; i < MAXH; i++) linew[i] = 0;

    // Find the start of a frame: the leading edge of VSYNC.
    prev_vs = (VSYNC == vs_on);
    forever begin
      @(posedge CLK25); #0;
      dots++;
      if (dots > budget) begin
        $display("FAIL  screenshot: no VSYNC edge in %0d dots", budget);
        fails++; claims++; return;
      end
      if ((VSYNC == vs_on) && !prev_vs) break;
      prev_vs = (VSYNC == vs_on);
    end

    // From here to the next VSYNC leading edge is one frame.
    prev_hs = (HSYNC == hs_on);
    prev_vs = 1;
    dots = 0;
    forever begin
      @(posedge CLK25); #0;
      dots++;
      if (dots > budget) begin
        $display("FAIL  screenshot: frame did not end in %0d dots", budget);
        fails++; claims++; return;
      end

      if (!BLANK) begin
        if (shot_lines < MAXH && x < MAXW) shot[shot_lines][x] = RGB;
        else shot_overflow = 1;
        x++;
      end

      // A line ends at HSYNC's leading edge. A line with no active dots in it
      // is a blanked line and is not part of the picture.
      if ((HSYNC == hs_on) && !prev_hs) begin
        if (x > 0) begin
          if (shot_lines < MAXH) linew[shot_lines] = x;
          shot_lines++;
        end
        x = 0;
      end
      prev_hs = (HSYNC == hs_on);

      if ((VSYNC == vs_on) && !prev_vs) break;
      prev_vs = (VSYNC == vs_on);
    end

    shot_w_min = MAXW; shot_w_max = 0;
    for (int i = 0; i < shot_lines && i < MAXH; i++) begin
      if (linew[i] < shot_w_min) shot_w_min = linew[i];
      if (linew[i] > shot_w_max) shot_w_max = linew[i];
    end
  endtask

  // RGB565 at the connector: the two post-LUT '273 carry {PDATH, PDATL}, which
  // graphics.md 13 defines as RRRRRGGG GGGBBBBB.
  function automatic logic [7:0] r8(input logic [15:0] c);
    r8 = {c[15:11], c[15:13]};
  endfunction
  function automatic logic [7:0] g8(input logic [15:0] c);
    g8 = {c[10:5], c[10:9]};
  endfunction
  function automatic logic [7:0] b8(input logic [15:0] c);
    b8 = {c[4:0], c[4:2]};
  endfunction

  int fd;
  task automatic write_ppm(input string path);
    fd = $fopen(path, "wb");
    if (fd == 0) begin
      $display("FAIL  screenshot: cannot open %s", path);
      fails++; claims++; return;
    end
    $fwrite(fd, "P6\n%0d %0d\n255\n", shot_w_max, shot_lines);
    for (int y = 0; y < shot_lines; y++)
      for (int x = 0; x < shot_w_max; x++) begin
        logic [15:0] c;
        c = (x < linew[y]) ? shot[y][x] : 16'h0000;
        $fwrite(fd, "%c%c%c", r8(c), g8(c), b8(c));
      end
    $fclose(fd);
    $display("      wrote %s (%0d x %0d)", path, shot_w_max, shot_lines);
  endtask

  /* boot.asm's pattern, restated here independently of the source.
   *
   *   index(x,y) = (y & $F8) | (x / 128),  and $FF for the stripe at x 256-263
   *
   * ⚠ This is a SECOND statement of the same intent, not a copy of the code
   * that drew it: the assembler's output and this expression agree only if the
   * whole address path - map, backplane, span writer, ring stride, interleave,
   * scan counter and palette - is right. */
  function automatic logic [7:0] want_index(input int x, input int y);
    if (x >= 256 && x < 264) want_index = 8'hFF;
    else want_index = 8'((y & 'hF8) | (x / 128));
  endfunction

  /* ---- one scene, asserted ------------------------------------------------ *
   *
   * ⭐ THE MODE IS CHECKED AT THE CONNECTOR AND FROM CPU CODE, which is what
   * makes these four claims different from vsync_tb's. That bench drives CTRL
   * from a task and counts dots against vctrl's own H and V; this reads a frame
   * boot.asm asked for, with known content in it, and asks whether the shape is
   * right.
   *
   * ⚠ AND LINE DOUBLING FALLS OUT RATHER THAN BEING ASSUMED. VMODE 00 and 01
   * double, 10 and 11 do not (graphics.md 6.2), so the picture row a scanline
   * shows is `L/2` or `L` - and asserting the pattern through that mapping is
   * what proves the doubling from outside the card.
   *
   * ⚠ ROWS THE PATTERN NEVER REACHED MUST BE BLACK. boot.asm painted 200 rows
   * of a 512-row ring, so 10 and 11 scan rows of VRAM that were never written -
   * and that is a claim too: it says the scan address kept going rather than
   * wrapping or repeating. */
  task automatic check_picture(input string what, input int lines, input bit doubled);
    int bad, fx, fy, pairs;
    ok(shot_lines == lines,
       $sformatf("%s: %0d active scanlines (got %0d)", what, lines, shot_lines));
    ok(shot_w_min == 640 && shot_w_max == 640,
       $sformatf("%s: every line is 640 pixels (got %0d..%0d)", what,
                 shot_w_min, shot_w_max));
    if (doubled) begin
      pairs = 0;
      for (int k = 0; k * 2 + 1 < shot_lines; k++)
        for (int x = 0; x < 640; x++)
          if (shot[k*2][x] !== shot[k*2+1][x]) pairs++;
      ok(pairs == 0,
         $sformatf("%s: each picture row is scanned twice, identically (%0d differ)",
                   what, pairs));
    end
    bad = 0; fx = -1; fy = -1;
    for (int L = 0; L < shot_lines && L < MAXH; L++) begin
      int row;
      row = doubled ? L / 2 : L;
      for (int x = shift; x < 640; x++) begin
        logic [7:0] w;
        w = (row >= 200) ? 8'h00 : want_index(x - shift, row);
        if (shot[L][x] !== {w, w}) begin
          bad++;
          if (fx < 0) begin fx = x; fy = L; end
        end
      end
    end
    ok(bad == 0,
       $sformatf("%s: every pixel is the index boot.asm drew, and rows 200+ are black (%0d wrong%s)",
                 what, bad,
                 fx < 0 ? "" : $sformatf(", first at x=%0d line=%0d: got %04h", fx, fy, shot[fy][fx])));
  endtask

  // ---- the run -------------------------------------------------------------
  int bad, first_bad_x, first_bad_y, i, shift;
  logic [15:0] got;
  logic [7:0]  want;
  string rom_path;

  initial begin
    rom_path = "../../../software/boot/boot.hex";
    m.mb.load_rom_file(rom_path);
    // A byte of the image, read back through the model that will fetch it, so
    // "the ROM loaded" is a claim and not an assumption.
    ok(m.mb.rom[20'h1FFE] === 8'hE0 && m.mb.rom[20'h1FFF] === 8'h00,
       "the boot image is in the ROM and $1FFE holds the reset vector $E000");

    /* ⚠ ONE REGISTER IN THE VENDOR CORE HAS TO BE INITIALISED HERE, and it is
     * a property of the SIMULATOR rather than of the machine.
     *
     * mc6809i.v holds NMILatched in a flip-flop with an asynchronous set and
     * NO reset: `always @(negedge NMISample2 or posedge wNMIClear)`. On real
     * silicon it powers up in one state or the other and the first NMI
     * clear defines it; in a four-state simulator it is X and `if (NMILatched
     * == 0)` is false, so no NMI is taken. This simulator is TWO-state - X is
     * 0 - so the core takes an NMI before its first instruction, stacks
     * twelve bytes through a stack pointer that is still $FFFD, and vectors
     * away. The trace shows it exactly: PC = $E000 pushed at $FFFC before
     * $4F is ever executed.
     *
     * Deasserted is 1. Setting it here is the same waiver the vendor README
     * describes for the lint warnings - the four .v files stay byte-identical
     * to upstream - and it is NOT hiding a machine-level fault: nNMI is tied
     * high on this board (machine.md 2.1 lists no NMI source at all), so the
     * machine can never assert it.
     *
     * The other three interrupt lines need no help: CC comes out of reset with
     * F and I set, and their sample chains fill with the deasserted level
     * during the reset below. */
    m.cpu.cpucore.NMILatched = 1'b1;

    // Long enough that every /HALT, /IRQ, /FIRQ and /DMABREQ sample stage has
    // clocked the deasserted level in before the core starts. Three E cycles
    // is the core's own synchroniser depth; this is twenty.
    repeat (240) @(posedge CLK25);
    n_reset = 1;

    $display("");
    $display("1. Boot - machine.md 7.2, and no JSR until the LDS");
    $display("");
    wait_progress(8'h01, 2000, "the machine leaves boot mode and sets up a stack");
    if (!timed_out) begin
      ok(run === 1'b1, "RUN is set, so the map SRAMs own physical A20-A13");
      ok(m.mb.map_lo_at(7) === 8'h00 && m.mb.map_hi_at(7) === 8'h01,
         "block 7 points at the ROM page the code is running from - ram.md 6.4");
      ok(m.mb.map_lo_at(1) === 8'h40 && m.mb.map_hi_at(1) === 8'h00,
         "block 1 points at the video ring, physical A20:A19 = 01 - ram.md 5.2");
      ok(m.mb.map_lo_at(6) === 8'h06 && m.mb.map_hi_at(6) === 8'h02,
         "block 6 points at the first SIMM, physical 4 MB");
    end

    $display("");
    $display("2. The SIMM - ram.md 6.4.1's read-back through a driven bus");
    $display("");
    wait_progress(8'h02, 4000, "a byte survives a round trip to DRAM and back");

    $display("");
    $display("3. The palette - 256 entries through 13's write path");
    $display("");
    wait_progress(8'h03, 40000, "256 palette entries load from one write to PIDX");
    if (!timed_out) begin
      bad = 0;
      for (i = 0; i < 256; i++)
        if (m.card.peek_pal(i) !== {i[7:0], i[7:0]}) bad++;
      ok(bad == 0,
         $sformatf("every entry holds what was written - PIDX auto-incremented 256 times (%0d wrong)", bad));
    end

    $display("");
    $display("4. The pattern - 1000 span-solid writes, 128 bytes each");
    $display("");
    wait_progress(8'h04, 900000, "the span writer paints 640 x 200 from the CPU");

    $display("");
    $display("5. The stripe - 7.2's WADV = 01 chaining, 200 rows");
    $display("");
    wait_progress(8'h05, 200000, "200 chained spans draw a column without reloading WPTR");

    wait_progress(8'hFF, 4000, "the display is enabled");

    $display("");
    $display("6. The screenshot - RGB, BLANK, HSYNC, VSYNC and nothing else");
    $display("");
    capture_frame(1200000);
    ok(!shot_overflow, "the capture fits: no line wider than 1024, no frame taller than 512");
    // ⭐ 400 SCANLINES, NOT 200. VMODE 00's 640x200 is a 640x400 VGA mode with
    // every picture row scanned twice - vaddr_tb calls it line doubling and
    // this is what it looks like at the connector. A capture that expected 200
    // would have been measuring its own assumption.
    ok(shot_w_min == 640 && shot_w_max == 640,
       $sformatf("every line is 640 pixels wide (got %0d..%0d)", shot_w_min, shot_w_max));

    if (shot_lines > 0) write_ppm("screenshot.ppm");

    /* ---- where the picture starts, measured once -------------------------
     *
     * ⚠ THE HORIZONTAL OFFSET IS MEASURED, NOT ASSUMED. The pixel path is
     * three registers deep behind the scan counter ('153 mux -> index '574 ->
     * LUT -> post-LUT '273, graphics.md 6.1) and BLANK is delayed to match
     * (19 item 35), so "which dot of the active window carries framebuffer
     * byte 0" is a question the design answers. Searching for it and REPORTING
     * it separates two claims: whether the address path, the interleave, the
     * ring stride and the palette are right, and whether the picture sits
     * where the sync says it does. The four modes below reuse the answer. */
    shift = -1;
    for (int sh = 0; sh <= 16 && shift < 0; sh++) begin
      int miss;
      miss = 0;
      for (int k = 0; k * 2 < shot_lines && k < 200 && miss == 0; k++)
        for (int x = sh; x < 640 && miss == 0; x++) begin
          want = want_index(x - sh, k);
          if (shot[k*2][x] !== {want, want}) miss = 1;
        end
      if (miss == 0) shift = sh;
    end
    ok(shift == 0,
       $sformatf("the picture starts on the first dot of the active window (offset %0d)",
                 shift));
    if (shift < 0) shift = 0;

    /* ---- all four of graphics.md 13's VMODEs, from CPU code --------------
     *
     * ⭐ THE OTHER THREE HAD NEVER BEEN REACHED BY SOFTWARE. vsync_tb drives
     * CTRL from a task and counts dots against vctrl's own counters; boot.asm
     * writes the register and waits on VSTAT b6, and what is checked is a frame
     * with known content in it. */
    check_picture("VMODE 00 - 640x200 doubled", 400, 1);

    wait_progress(8'h10, 600000, "VMODE 10 is selected - 640x400 progressive");
    capture_frame(1200000);
    if (shot_lines > 0) write_ppm("screenshot-vmode10.ppm");
    check_picture("VMODE 10 - 640x400 progressive", 400, 0);

    wait_progress(8'h11, 600000, "VMODE 01 is selected - 640x240 doubled");
    capture_frame(1400000);
    check_picture("VMODE 01 - 640x240 doubled", 480, 1);

    wait_progress(8'h12, 600000, "VMODE 11 is selected - 640x480 progressive");
    capture_frame(1400000);
    if (shot_lines > 0) write_ppm("screenshot-vmode11.ppm");
    check_picture("VMODE 11 - 640x480 progressive", 480, 0);

    /* ---- the display list, started by software ---------------------------
     *
     * ⭐ IT HAD NEVER BEEN STARTED BY SOFTWARE. vspan_tb pokes descriptors
     * straight into the framebuffer array and writes BCTRL from a task; these
     * two lists were BUILT through the span writer, byte by byte at WPTR, and
     * started out of a VBL poll - which is 10.3.1's own rule and 12.1's own
     * handler. */
    wait_progress(8'h20, 900000, "a display list is running - graphics.md 10.3's raster bar");
    capture_frame(1400000);
    if (shot_lines > 0) write_ppm("screenshot-rasterbar.ppm");
    ok(saw_lrun, "BSTAT b0 LRUN went high - the engine took WPTR and walked");
    $display("      list A: HSCROLL[9:2]=%02h  pal[$FF]=%04h  WPTR=%0d  VRAM[8192..8195]=%02h %02h %02h %02h",
             m.vid_hscr, m.card.peek_pal(255), WPTR,
             m.card.peek(8192), m.card.peek(8193), m.card.peek(8194), m.card.peek(8195));
    /* The stripe is index $FF on every row, so the list repainting that one
     * entry part way down IS a bar. Count the lines of each colour on the
     * stripe's own column. */
    begin
      int white, magenta, other, flips;
      logic [15:0] prev;
      white = 0; magenta = 0; other = 0; flips = 0; prev = 16'hxxxx;
      for (int L = 0; L < shot_lines; L++) begin
        logic [15:0] c;
        c = shot[L][256 + shift + 2];
        if (c === 16'hFFFF) white++;
        else if (c === 16'hF81F) magenta++;
        else other++;
        if (L > 0 && c !== prev) flips++;
        prev = c;
      end
      ok(other == 0,
         $sformatf("the stripe is one of the list's two colours on every line (%0d neither)", other));
      ok(white > 20 && magenta > 20,
         $sformatf("⭐ A RASTER BAR: %0d lines white, %0d magenta - one palette entry, changed and changed back mid-frame", white, magenta));
      ok(flips == 2,
         $sformatf("and exactly two transitions down the frame, which is the bar's two edges (got %0d)", flips));
    end

    /* ---- per-scanline HSCROLL ------------------------------------------- */
    wait_progress(8'h21, 900000, "the second list is running - per-scanline HSCROLL");
    capture_frame(1400000);
    if (shot_lines > 0) write_ppm("screenshot-hscroll.ppm");
    begin
      int positions[int];
      int distinct, found;
      distinct = 0;
      for (int L = 0; L < shot_lines; L++) begin
        found = -1;
        for (int x = 0; x < 640 && found < 0; x++)
          if (shot[L][x] === 16'hFFFF || shot[L][x] === 16'hF81F) found = x;
        if (found >= 0 && !positions.exists(found)) begin
          positions[found] = 1;
          distinct++;
        end
      end
      ok(distinct >= 16,
         $sformatf("⭐ PER-SCANLINE HSCROLL: the stripe stands in %0d distinct columns in ONE frame - 8.2's byte-granular scroll, moved by a descriptor per line", distinct));
    end

    /* ---- cell mode ------------------------------------------------------
     *
     * ⭐ vtile_tb DRIVES THE FETCH AND READS BACK THE ADDRESS. This reads the
     * PICTURE, out of a tilemap 6809 code put in VRAM through the span writer,
     * and states graphics.md 6.4.1's concatenation as one expression:
     *
     *     index(x, y) = code(x/8, y/8) << 6 | (y & 7) << 3 | (x & 7)
     *     code(cx, cy) = (cx + cy) & 3               boot.asm's map
     *
     * The tile set is the bytes 0..255, so a pixel's index IS the three fields
     * that addressed it; §9's palette is the identity map, so the value
     * survives to the connector. Every field is checked at every pixel. */
    wait_progress(8'h30, 900000, "⭐ cell mode is on - graphics.md 6.4's tilemap, built by the CPU");
    capture_frame(1400000);
    if (shot_lines > 0) write_ppm("screenshot-cellmode.ppm");
    ok(shot_lines == 400,
       $sformatf("VMODE 00 doubles, so cell mode still fills the frame (%0d lines)", shot_lines));
    begin
      int bad, first_bad_x, first_bad_y, codes[int];
      logic [7:0] want, got;
      bad = 0; first_bad_x = -1; first_bad_y = -1;
      for (int L = 0; L < shot_lines; L++) begin
        int y;
        y = L / 2;                       // VMODE 00 is 200 rows doubled to 400
        for (int x = 0; x < 640; x++) begin
          want = (((x / 8) + (y / 8)) & 3) << 6 | ((y & 7) << 3) | (x & 7);
          got  = shot[L][x][15:8];       // the identity palette: RRRRRGGG = i
          if (got !== want) begin
            bad++;
            if (first_bad_x < 0) begin first_bad_x = x; first_bad_y = y; end
          end
          if (L == 0 || L == 398) codes[want >> 6] = 1;
        end
      end
      /* ⚠ ON FAILURE, SAY WHICH HALF. A wrong picture here is either a wrong
       * tilemap in VRAM or a wrong fetch of a right one, and the two look
       * identical at the connector - printing both is what separated §19
       * item 43 from a fetch bug in ten minutes rather than an afternoon. */
      if (bad > 0) begin
        string r1, r2;
        $display("      first wrong pixel at x=%0d y=%0d", first_bad_x, first_bad_y);
        r1 = ""; r2 = "";
        for (int i = 0; i < 16; i++) r1 = {r1, $sformatf("%02h ", m.card.peek(131072 + i))};
        for (int i = 0; i < 16; i++) r2 = {r2, $sformatf("%02h ", m.card.peek(163840 + i))};
        $display("      tiles at 131072: %s   (want 00 01 02 03 ...)", r1);
        $display("      map   at 163840: %s   (want 00 01 02 03 00 ...)", r2);
      end
      ok(bad == 0,
         $sformatf("⭐ EVERY PIXEL IS TILEBASE|code<<6|row<<3|col, for the code the map holds (%0d wrong of 256000)", bad));
      ok(codes.size() == 4,
         $sformatf("and all four tile codes are on the screen, so the map fetch really varies (%0d)", codes.size()));
    end

    // ---- graphics.md 11: the software reads VRAM back --------------------
    /* boot.asm section 10: the tile set in cell mode, then 32 stores each
     * followed straight away by a load, then the whole area again. The ROM
     * compares every byte itself and reports $40, or $E2 with the index. */
    $display("");
    $display("6b. Readable VRAM - graphics.md 11, from the software's own compare");
    $display("");
    wait_progress(8'h40, 900000,
                  "⭐ VRAM READS BACK: 256 tile bytes, 32 store-then-load pairs with no poll between, the 64 bytes they left, a load issued under a 256-byte span, and the span - and through +$15 VDATA 64 stores, 64 loads, two spans started back to back and 512 bytes of them - every byte the ROM compared was right");
    if (progress === 8'hE2)
      $display("      boot.asm section 10 reported $E2 - a byte read back wrong (vidx/vgot are in the SIMM at $C01A)");
    ok(vram_reads >= 256 + 32 + 64 + 1 + 256,
       $sformatf("and the CPU really read the window - %0d VRAM read cycles", vram_reads));
    ok(wait_dots > 0,
       $sformatf("⭐ and a read WAITED - section 10 (d)'s load under a span held the CPU on /WAIT for %0d dots and still got the right byte", wait_dots));
    ok(vdata_writes >= 64 + 1 + 2 && vdata_reads >= 64 + 1 + 512,
       $sformatf("⭐ graphics.md 19 item 47: the CPU used +$15 VDATA - %0d stores and %0d loads in the I/O page, with no MMU block", vdata_writes, vdata_reads));
    ok(vdata_wait_dots > 0,
       $sformatf("⭐ and a VDATA access WAITED in the I/O page - section 10 (h)'s store and load under a span held the CPU for %0d dots, and the span still came out one colour", vdata_wait_dots));

    // ---- and the things that must not have happened -------------------
    $display("");
    $display("7. What must not have happened");
    $display("");
    ok(!saw_bus_conflict, "no cycle had two drivers on D0-D7 - machine.md 2's whole point");
    ok(!saw_pa_conflict,  "no cycle had two drivers on physical A20-A13");
    ok(progress_writes >= 6,
       $sformatf("every stage reported (%0d writes to the progress port)", progress_writes));

    $display("");
    $display("      %0d E cycles, %0d dots of /WAIT, %0d VRAM writes, %0d VRAM reads, %0d VSTAT reads",
             e_cycles, wait_dots, vram_writes, vram_reads, vstat_reads);
    $display("");
    if (fails == 0) $display("machine_tb OK - %0d claims", claims);
    else            $display("machine_tb - %0d of %0d claims FAILED", fails, claims);
    $finish;
  end

  // ---- the backstop -------------------------------------------------------
  // If anything above stops making progress in a way its own bound cannot see,
  // this ends the run rather than letting it spin. CLAUDE.md: a hang is worse
  // than a failure, and run.sh's exit code cannot see one.
  initial begin
    #400000000;
    $display("FAIL  machine_tb: global timeout - progress $%02h at %0d E cycles",
             progress, e_cycles);
    $display("      %0d VRAM writes, %0d VSTAT reads, %0d register writes, %0d /WAIT dots",
             vram_writes, vstat_reads, reg_writes, wait_dots);
    $display("      SPANBUSY=%b WPTR=%0d", SPANBUSY, WPTR);
    $display("machine_tb - TIMED OUT");
    $finish;
  end

endmodule
