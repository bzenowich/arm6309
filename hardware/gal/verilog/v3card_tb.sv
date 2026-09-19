// video3 as a CARD: the four fitted parts and the board around them, driven
// the way the machine drives them - one 6809E bus cycle at a time, with /WAIT
// stretching E-high, and every register reached through the backplane rather
// than poked into a part.
//
// ⭐ WHY THIS EXISTS. Until 2026-09-19 video3 had one bench, v3dot_tb, which
// runs the raster part alone and says honestly that the cadence "needs the
// card wrapper this file deliberately does not pretend to be". Every other
// claim about the card - the two sequencers, the column reload, the arbiter,
// the register file - was a fit result: the equations place and route, which
// is not the same as computing the right thing. machine_tb on the other card
// found three defects twelve benches and 543 model claims had missed, and all
// three were seams. This is the first thing that exercises video3's seams.
//
// ⚠ IT DRIVES THE BUS FROM ITS OWN COUNTER, BUT IT HONOURS /WAIT. CLAUDE.md:
// "a testbench that drives E from its own free-running counter has a CPU that
// cannot be waited", and /WAIT is the only signal on this backplane that
// changes what the CPU does. So E-high is stretched while WAIT_OE, exactly as
// the 6809E's MRDY would, and a bound turns a hang into a failure.
//
// A comment line here must never begin with the simulator's own name.

`default_nettype none

module v3card_tb;

  logic CLK25 = 0;
  always #1 CLK25 <= ~CLK25;

  logic RESET = 1;
  logic E = 0, RW = 1, IOSEL = 0, IOPGH = 0;
  logic [20:0] PA = 0;
  logic [7:0]  DIN = 0;
  wire  [7:0]  DOUT;
  wire  DOE, WAIT_OE, IRQ_OE;
  wire  [15:0] RGB;
  wire  HSYNC, VSYNC, BLANK, FBA_FIGHT, DBUS_FIGHT, LUTA_FIGHT;

  video3_card dut (.*);

  // ---- claims -------------------------------------------------------------
  int fails = 0, passes = 0;
  task automatic ok(input bit c, input string what);
    if (c) begin passes++; $display("ok    %s", what); end
    else   begin fails++;  $display("FAIL  %s", what); end
  endtask

  // ---- fights: counted every dot, from reset to the end -------------------
  int fba_fights = 0, dbus_fights = 0, luta_fights = 0;
  always @(posedge CLK25) if (!RESET) begin
    if (FBA_FIGHT)  fba_fights  <= fba_fights + 1;
    if (DBUS_FIGHT) dbus_fights <= dbus_fights + 1;
    if (LUTA_FIGHT) luta_fights <= luta_fights + 1;
  end

  // ---- what the copy engine's time goes on --------------------------------
  int cp_dots = 0, cp_ticks = 0, cp_rd = 0, cp_map = 0, cp_spn = 0, cp_none = 0;
  always @(posedge CLK25) if (dut.CBUSY) begin
    cp_dots <= cp_dots + 1;
    if (dut.MUXSEL0 & dut.SPARE) begin                  // the spare access's last dot
      if (dut.GCPY)      cp_ticks <= cp_ticks + 1;
      else if (dut.GRD)  cp_rd    <= cp_rd + 1;
      else if (dut.GMAP) cp_map   <= cp_map + 1;
      else if (dut.GSPN) cp_spn   <= cp_spn + 1;
      else               cp_none  <= cp_none + 1;
    end
  end

  // a VRAM write trace, switched on around a scenario that needs looking at
  bit trace = 0;
  always @(posedge CLK25) if (trace && dut.vwe)
    $display("      vram[%05h] <= %02h   (WEN %0d CSTEP %0d lane %0d)",
             dut.byte_a, dut.wdata, dut.WEN, dut.CSTEP, dut.lane);
  always @(posedge CLK25) if (trace && (dut.RP1 | dut.RP2 | dut.WSTART | dut.WSTB))
    $display("      t%0t  RP1 %0d RP2 %0d WSTART %0d WSTB %0d  RFA %02h IDB %02h  E %0d WAIT %0d",
             $time, dut.RP1, dut.RP2, dut.WSTART, dut.WSTB, dut.rfa, dut.IDB, E, WAIT_OE);

  task automatic dots(input int n);
    repeat (n) @(posedge CLK25);
  endtask

  // ---- the 6809E bus: 12 dots a cycle at E = 2.0979 MHz --------------------
  // E-low 6 dots, E-high at least 6, stretched while /WAIT is asserted.
  int max_wait = 0;
  task automatic cycle(input logic [20:0] a, input bit rw, input bit io,
                       input logic [7:0] d, output logic [7:0] q);
    int w;
    PA = a; RW = rw; DIN = rw ? 8'h00 : d;
    // /IOSEL is the $FF00-$FF7F strobe and IOPGH the I/O page - both only for
    // an I/O access; the VRAM window is a plain physical address (A19 = 1).
    IOSEL = io && a[15:7] == 9'b1111_1111_0;
    IOPGH = io;
    E = 0; dots(6);
    // ⭐ E-HIGH IS SIX UN-WAITED DOTS, NOT SIX DOTS AND THEN A WAIT. The
    // motherboard's clkdec makes E, not the 6809E, and its phase counter
    // FREEZES while /WAIT is asserted (clkdec.jedec.ts: every bit holds with
    // `Cn & WAIT`) and resumes where it stopped - so a write released from a
    // hold keeps the rest of its E-high. An earlier version of this bench
    // dropped E the instant /WAIT released, which gave a held write zero dots
    // to be accepted in and lost it: a defect of the bench, found by tracing.
    E = 1;
    w = 0;
    for (int n = 0; n < 6 && w < 4000; ) begin
      dots(1);
      if (WAIT_OE) w++; else n++;
    end
    if (w > max_wait) max_wait = w;
    q = DOUT;
    E = 0; dots(1);
    RW = 1; IOSEL = 0; IOPGH = 0;
  endtask

  // registers are $FF60 + offset, in the I/O page
  task automatic wr(input logic [4:0] off, input logic [7:0] v);
    logic [7:0] q;
    cycle({5'b0, 16'hFF60 | off}, 1'b0, 1'b1, v, q);
  endtask
  task automatic rd(input logic [4:0] off, output logic [7:0] v);
    cycle({5'b0, 16'hFF60 | off}, 1'b1, 1'b1, 8'h00, v);
  endtask

  // register offsets, plan §10 - the whole map, whether or not a scenario
  // below reaches each one yet
  // verilator lint_off UNUSEDPARAM
  localparam logic [4:0] CTRL = 5'h00, SPANLEN = 5'h05, WFG = 5'h06, WBG = 5'h07,
    WPTR0 = 5'h08, WPTR1 = 5'h09, WPTR2 = 5'h0A, WADV = 5'h0B, VDATA = 5'h0C,
    VSTAT = 5'h0D, PIDXL = 5'h0E, PIDXH = 5'h0F, PDATL = 5'h10, PDATH = 5'h11,
    CPTR0 = 5'h12, CPTR1 = 5'h13, CPTR2 = 5'h14, CWIDTH = 5'h15, CHEIGHT = 5'h16,
    CCTRL = 5'h17;
  // verilator lint_on UNUSEDPARAM

  // WPTR / CPTR pack a 19-bit address little-endian over three bytes
  task automatic set_ptr(input logic [4:0] base, input logic [18:0] a);
    wr(base,     a[7:0]);
    wr(base + 1, a[15:8]);
    wr(base + 2, {5'b0, a[18:16]});
  endtask

  // a VSTAT poll, bounded: the register never waits (plan §10's '244)
  task automatic wait_clear(input int bitno, input string what);
    logic [7:0] s; int n;
    n = 0;
    do begin rd(VSTAT, s); n++; end while (s[bitno] && n < 5000);
    ok(!s[bitno], $sformatf("%s clears (VSTAT b%0d, %0d polls)", what, bitno, n));
  endtask

  // ---- the scenarios -------------------------------------------------------
  logic [7:0] q;
  int bad;
  logic [15:0] frame [0:800 * 526 - 1];
  bit fblank [0:800 * 526 - 1];
  logic [7:0] fhc [0:800 * 526 - 1];
  logic [9:0] fvc [0:800 * 526 - 1];
  bit fhb [0:800 * 526 - 1], fvb [0:800 * 526 - 1];

  initial begin
    dots(20);
    RESET = 0;
    dots(20);

    // ================================================================ palette
    // plan §10: PIDX is sixteen bits (+$0E low, +$0F high) and auto-increments
    // after PDATH; a CPU commit posts to the next HLOAD and PBUSY covers it.
    wr(PIDXL, 8'h00); wr(PIDXH, 8'h00);
    for (int i = 0; i < 4; i++) begin
      wr(PDATL, 8'h10 + i);
      wr(PDATH, 8'hA0 + i);
      wait_clear(1, $sformatf("PBUSY after palette entry %0d", i));
    end
    bad = 0;
    for (int i = 0; i < 4; i++)
      if (dut.peek_lut(i) !== {8'hA0 + i[7:0], 8'h10 + i[7:0]}) bad++;
    ok(bad == 0, $sformatf("four palette writes land at LUT 0..3 and PIDX walks (%0d wrong)", bad));
    if (bad) for (int i = 0; i < 6; i++) $display("      LUT[%0d] = %04h", i, dut.peek_lut(i));

    // ============================================== bitmap, direct writes
    // CTRL: VMODE 00, MODE 00 bitmap, WMODE 00 direct, display on.
    wr(CTRL, 8'h80);
    wr(WADV, 8'h00);
    set_ptr(WPTR0, 19'h00400);
    for (int i = 0; i < 8; i++) wr(VDATA, 8'h30 + i);
    wait_clear(7, "SPANBUSY after eight direct writes");
    bad = 0;
    for (int i = 0; i < 8; i++)
      if (dut.peek(19'h00400 + i) !== 8'h30 + i) bad++;
    ok(bad == 0, $sformatf("eight VDATA writes land at WPTR, WPTR+1 .. (%0d wrong)", bad));
    if (bad) begin
      $write("      VRAM $3FC..$40B:");
      for (int i = 'h3FC; i < 'h40C; i++) $write(" %02h", dut.peek(i));
      $display("");
      $display("      WPTR now = %05h", {dut.u_ptr.WR8,dut.u_ptr.WR7,dut.u_ptr.WR6,dut.u_ptr.WR5,dut.u_ptr.WR4,
        dut.u_ptr.WR3,dut.u_ptr.WR2,dut.u_ptr.WR1,dut.u_ptr.WR0,dut.u_ptr.WC9,dut.u_ptr.WC8,dut.u_ptr.WC7,
        dut.u_ptr.WC6,dut.u_ptr.WC5,dut.u_ptr.WC4,dut.u_ptr.WC3,dut.u_ptr.WC2,dut.u_ptr.WC1,dut.u_ptr.WC0});
    end
    ok(dut.peek(19'h003FF) === 8'h00 && dut.peek(19'h00408) === 8'h00,
       "and nothing either side of them is touched");

    // ============================================== reading them back
    set_ptr(WPTR0, 19'h00400);
    bad = 0;
    for (int i = 0; i < 8; i++) begin
      rd(VDATA, q);
      if (q !== 8'h30 + i) bad++;
    end
    ok(bad == 0, $sformatf("eight VDATA reads return them in order, post-incrementing (%0d wrong)", bad));

    // ================================================ span-mask, bit order
    // WMODE 01 is CTRL b5..4 (plan §10). A mask 1 is ink - WFG, the EVEN
    // register, because §5 makes the mask bit the file's address bit 0. And
    // the bit order is the emulator's, which is the contract NitrOS-9's fonts
    // are built against: `v & (0x80 >> i)`, bit 7 FIRST.
    wr(WFG, 8'hF1); wr(WBG, 8'hB2);
    wr(CTRL, 8'h90);
    set_ptr(WPTR0, 19'h00800);
    wr(VDATA, 8'b1000_0110);
    wait_clear(7, "SPANBUSY after one span-mask write");
    bad = 0;
    for (int i = 0; i < 8; i++)
      if (dut.peek(19'h00800 + i) !== (((8'b1000_0110 >> (7 - i)) & 1) ? 8'hF1 : 8'hB2)) bad++;
    ok(bad == 0, $sformatf("span-mask: $86 is F1 B2 B2 B2 B2 F1 F1 B2 - bit 7 first, 1 = WFG (%0d wrong)", bad));
    if (bad) begin
      $write("      got:"); for (int i = 0; i < 8; i++) $write(" %02h", dut.peek(19'h00800 + i)); $display("");
    end

    // =================================== span-mask back to back: /WAIT
    // Eight retires is 32 dots and the next write's E-high comes 7 dots after
    // the last one ended, so a span still running MUST hold the CPU - through
    // the VRAM window (IOPGH low), where /WAIT applies.
    set_ptr(WPTR0, 19'h00900);
    for (int i = 0; i < 4; i++) begin
      logic [7:0] qq;
      cycle(21'h080900 + i, 1'b0, 1'b0, 8'hFF, qq);     // A19 = 1: the window
    end
    wait_clear(7, "SPANBUSY after four back-to-back window writes");
    bad = 0;
    for (int i = 0; i < 32; i++) if (dut.peek(19'h00900 + i) !== 8'hF1) bad++;
    ok(bad == 0, $sformatf("four $FF masks through the window are 32 WFG pixels in a row (%0d wrong)", bad));
    ok(max_wait > 0, $sformatf("and the CPU was held by /WAIT while a span ran (longest %0d dots)", max_wait));

    // ======================================================== span-solid
    // SPANLEN is "span length - 1" (plan §10); the length counter loads it
    // from the file's +$05 on the span's first edge.
    wr(SPANLEN, 8'd19);
    wr(CTRL, 8'hA0);
    set_ptr(WPTR0, 19'h00A00);
    wr(VDATA, 8'h00);
    wait_clear(7, "SPANBUSY after a span-solid");
    bad = 0;
    for (int i = 0; i < 20; i++) if (dut.peek(19'h00A00 + i) !== 8'hF1) bad++;
    ok(bad == 0 && dut.peek(19'h00A14) === 8'h00,
       $sformatf("span-solid with SPANLEN 19 is exactly 20 WFG bytes (%0d wrong, next %02h)", bad, dut.peek(19'h00A14)));
    wr(VDATA, 8'h00);
    wait_clear(7, "SPANBUSY after a second span-solid");
    bad = 0;
    for (int i = 20; i < 40; i++) if (dut.peek(19'h00A00 + i) !== 8'hF1) bad++;
    ok(bad == 0, $sformatf("and a second span-solid with no SPANLEN write is 20 more (%0d wrong) - one SPANLEN, many spans", bad));

    // ======================== §7.2: WADV 01, a glyph with no WPTR rewrite
    // WADV 01 is "next row, same column": at span end the row steps and the
    // column comes back from the file's +$08/+$09. That is the whole of the
    // text engine's 13 writes a cell - and nothing tested it until now.
    wr(CTRL, 8'h90);
    wr(WADV, 8'h01);
    set_ptr(WPTR0, 19'h01004);                         // row 4, column 4
    for (int r = 0; r < 4; r++) wr(VDATA, 8'hF0);
    wait_clear(7, "SPANBUSY after four chained glyph rows");
    bad = 0;
    for (int r = 0; r < 4; r++)
      for (int i = 0; i < 8; i++)
        if (dut.peek(19'h01004 + r * 1024 + i) !== (i < 4 ? 8'hF1 : 8'hB2)) bad++;
    ok(bad == 0, $sformatf("WADV 01: four mask writes are four rows at the SAME column (%0d wrong)", bad));
    if (bad) for (int r = 0; r < 4; r++) begin
      $write("      row %0d:", r); for (int i = -2; i < 10; i++) $write(" %02h", dut.peek(19'h01004 + r * 1024 + i)); $display("");
    end
    wr(WADV, 8'h00);

    // =========================================================== the copy
    // plan §6: CPTR the source, WPTR the destination, CWIDTH / CHEIGHT the
    // plain byte and row counts (the emulator, the model and both drivers
    // agree none of them is biased), CCTRL b0 GO. Two accesses a byte, and at
    // each row end BOTH columns come back from the file (§7.2's walk, four
    // states for a copy) while both rows step. 13 x 5, misaligned at both ends
    // so every lane is read and written; a one-byte ring around the
    // destination must stay untouched.
    // ⛔ NEITHER BACKGROUND IS ZERO. The first version of this left both
    // empty, and a copy whose first row ran 1,023 bytes passed - the overrun
    // copied zeros onto zeros. The source's surroundings are $5A and the
    // destination's $EE, so any byte copied from outside the rectangle, or
    // written outside it, is a byte that does not match.
    for (int r = -1; r < 7; r++)
      for (int c = -40; c < 60; c++) begin
        dut.poke(19'h05000 + r * 1024 + 10 + c, 8'h5A);
        dut.poke(19'h0A000 + r * 1024 + 7 + c, 8'hEE);
      end
    for (int r = 0; r < 5; r++)
      for (int c = 0; c < 13; c++)
        dut.poke(19'h05000 + r * 1024 + 10 + c, 8'h40 + r * 16 + c);
    wr(CTRL, 8'h80);
    set_ptr(CPTR0, 19'h05000 + 10);                   // row 20, column 10
    set_ptr(WPTR0, 19'h0A000 + 7);                    // row 40, column 7
    wr(CWIDTH, 8'd13);
    wr(CHEIGHT, 8'd5);
    wr(CCTRL, 8'h01);                                 // GO
    begin
      logic [7:0] st; int n; bit seen;
      n = 0; seen = 0;
      do begin rd(VSTAT, st); n++; if (st[4]) seen = 1; end while (st[4] && n < 5000);
      ok(seen, "CBUSY (VSTAT b4) is set while the copy runs");
      ok(!st[4], $sformatf("and clears when it ends (%0d polls)", n));
    end
    bad = 0;
    for (int r = 0; r < 5; r++)
      for (int c = 0; c < 13; c++)
        if (dut.peek(19'h0A000 + r * 1024 + 7 + c) !== 8'h40 + r * 16 + c) bad++;
    ok(bad == 0, $sformatf("a 13 x 5 copy lands byte for byte, every lane, every row (%0d of 65 wrong)", bad));
    if (bad) for (int r = 0; r < 6; r++) begin
      $write("      dst row %0d:", r);
      for (int c = -1; c < 15; c++) $write(" %02h", dut.peek(19'h0A000 + r * 1024 + 7 + c));
      $display("");
    end
    bad = 0;
    for (int r = -1; r < 7; r++)
      for (int c = -40; c < 60; c++)
        if ((r < 0 || r > 4 || c < 0 || c > 12) && dut.peek(19'h0A000 + r * 1024 + 7 + c) !== 8'hEE) bad++;
    ok(bad == 0, $sformatf("and nothing around it moves - forty bytes either side, a row above and two below (%0d)", bad));
    ok(cp_ticks >= 130 && cp_ticks <= 150,
       $sformatf("two accesses a byte: %0d copy accesses for 65 bytes (plan §6.1's 4.05 MB/s)", cp_ticks));
    $display("      copy: %0d dots busy; spare accesses: copy %0d, prefetch %0d, map %0d, span %0d, none %0d",
             cp_dots, cp_ticks, cp_rd, cp_map, cp_spn, cp_none);

    // ========================================================== the picture
    // Bitmap, VMODE 11: 640 x 480 on the 525-line family, one VRAM row a line.
    // Every byte's VALUE is its own position - vram[row*1024 + x] = row + x -
    // and every LUT entry is a distinct non-zero colour, {$C0, index}, so each
    // dot of RGB says which byte of VRAM the card put there. The palette's bus
    // path is proven above; this fills it through the back door.
    for (int i = 0; i < 256; i++) dut.poke_lut(i, {8'hC0, i[7:0]});
    for (int r = 0; r < 480; r++)
      for (int x = 0; x < 640; x++) dut.poke(r * 1024 + x, (r + x) & 8'hFF);
    wr(CTRL, 8'h83);
    // the family is latched at frame end (M0): let one frame go by, then take
    // the next from its first line
    @(posedge VSYNC); @(negedge VSYNC);
    @(posedge VSYNC); @(negedge VSYNC);
    begin
      int line, x, lines_seen, bad_px, bad_len, first_row, prev_row, bad_row;
      logic [7:0] row0;
      bit in_line;
      lines_seen = 0; bad_px = 0; bad_len = 0; bad_row = 0; prev_row = -1; first_row = -1;
      in_line = 0; x = 0;
      // one frame: 800 x 525 dots, with a margin - recorded, so a wrong frame
      // can be looked at afterwards
      for (int d = 0; d < 800 * 526; d++) begin
        @(posedge CLK25);
        frame[d] = RGB; fblank[d] = BLANK;
        fhc[d] = {dut.u_dot.HC7, dut.u_dot.HC6, dut.u_dot.HC5, dut.u_dot.HC4,
                  dut.u_dot.HC3, dut.u_dot.HC2, dut.u_dot.HC1, dut.u_dot.HC0};
        fvc[d] = {dut.u_dot.VC9, dut.u_dot.VC8, dut.u_dot.VC7, dut.u_dot.VC6, dut.u_dot.VC5,
                  dut.u_dot.VC4, dut.u_dot.VC3, dut.u_dot.VC2, dut.u_dot.VC1, dut.u_dot.VC0};
        fhb[d] = dut.HBLANK; fvb[d] = dut.VBLANK;
        if (RGB != 16'h0000) begin
          if (!in_line) begin in_line = 1; x = 0; row0 = RGB[7:0]; end
          if (RGB[15:8] !== 8'hC0 || RGB[7:0] !== ((row0 + x) & 8'hFF)) bad_px++;
          x++;
        end else if (in_line) begin
          in_line = 0;
          if (x != 640) bad_len++;
          if (first_row < 0) first_row = row0;
          else if (row0 !== ((prev_row + 1) & 8'hFF)) bad_row++;
          prev_row = row0;
          lines_seen++;
        end
      end
      ok(lines_seen == 480, $sformatf("a frame shows 480 lines (%0d)", lines_seen));
      ok(bad_len == 0, $sformatf("every line is 640 pixels (%0d are not)", bad_len));
      ok(first_row == 0, $sformatf("the first line is VRAM row 0, from its first byte (starts at %0d)", first_row));
      ok(bad_row == 0, $sformatf("each line is the next VRAM row (%0d out of order)", bad_row));
      ok(bad_px == 0, $sformatf("and every pixel is the byte at its own address, through the LUT (%0d wrong)", bad_px));
      if (lines_seen != 480 || bad_px != 0) begin
        // the first line with anything on it, forty dots before to the end
        int d0; string ln;
        d0 = 0;
        while (d0 < 800 * 526 && frame[d0] == 16'h0000) d0++;
        $display("      first non-black dot at %0d (line %0d, dot %0d)", d0, d0 / 800, d0 % 800);
        for (int k = d0 - 4; k < d0 + 40; k += 2)
          $display("      d%0d  HC %0d VC %0d  HBLANK %0d VBLANK %0d BLANK %0d  RGB %04h",
                   k, fhc[k], fvc[k], fhb[k], fvb[k], fblank[k], frame[k]);
        d0 = d0 - 40;
        for (int k = 0; k < 800; k += 32) begin
          ln = "";
          for (int j = 0; j < 32; j++)
            ln = {ln, frame[d0 + k + j] == 16'h0000 ? (fblank[d0 + k + j] ? " bb" : " ..")
                                                    : $sformatf(" %02h", frame[d0 + k + j][7:0])};
          $display("      %3d:%s", k, ln);
        end
      end
    end

    // ================================================================= end
    ok(fba_fights == 0, $sformatf("v3scan and v3ptr never both drive the address bus (%0d dots)", fba_fights));
    ok(dbus_fights == 0, $sformatf("never two drivers on D7..D0 (%0d dots)", dbus_fights));
    ok(luta_fights == 0, $sformatf("never two masters on the LUT address bus (%0d dots)", luta_fights));
    ok(max_wait < 4000, $sformatf("/WAIT always released (longest %0d dots)", max_wait));
    $display("\n%0d claims, %0d failed", passes + fails, fails);
    $finish;
  end

  // a hang is worse than a failure: bound the whole run
  initial begin
    #40000000;
    $display("FAIL  the bench did not finish");
    $finish;
  end

endmodule
`default_nettype wire
