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
  wire  IDB_FIGHT, IDB_FLOAT, LANE_FLOAT, RANK_FIGHT;

  video3_card dut (.*);

  // ---- claims -------------------------------------------------------------
  int fails = 0, passes = 0;
  task automatic ok(input bit c, input string what);
    if (c) begin passes++; $display("ok    %s", what); end
    else   begin fails++;  $display("FAIL  %s", what); end
  endtask

  // ---- fights: counted every dot, from reset to the end -------------------
  int fba_fights = 0, dbus_fights = 0, luta_fights = 0;
  int idb_fights = 0, idb_floats = 0, lane_floats = 0, rank_fights = 0;
  always @(posedge CLK25) if (!RESET) begin
    if (FBA_FIGHT)  fba_fights  <= fba_fights + 1;
    if (DBUS_FIGHT) dbus_fights <= dbus_fights + 1;
    if (LUTA_FIGHT) luta_fights <= luta_fights + 1;
    if (IDB_FIGHT)  idb_fights  <= idb_fights + 1;
    if (IDB_FLOAT)  idb_floats  <= idb_floats + 1;
    if (LANE_FLOAT) lane_floats <= lane_floats + 1;
    if (RANK_FIGHT) rank_fights <= rank_fights + 1;
  end

  // ---- what the copy engine's time goes on --------------------------------
  int cp_dots = 0, cp_ticks = 0, cp_rd = 0, cp_map = 0, cp_spn = 0, cp_none = 0;
  always @(posedge CLK25) if (dut.CBUSY) begin
    cp_dots <= cp_dots + 1;
    if (dut.DP0 & dut.SPARE) begin                      // the spare access's last dot
      if (dut.GCPY)      cp_ticks <= cp_ticks + 1;
      else if (dut.GRD)  cp_rd    <= cp_rd + 1;
      else if (dut.MRQ)  cp_map   <= cp_map + 1;
      else if (dut.GSPN) cp_spn   <= cp_spn + 1;
      else               cp_none  <= cp_none + 1;
    end
  end

  // a VRAM write trace, switched on around a scenario that needs looking at
  bit trace = 0;
  always @(posedge CLK25) if (trace && dut.VWE)
    $display("      write fba %05h  IDB %02h  BE %04b LOE %04b DIR %0d  (CSTEP %0d)",
             dut.fba, dut.IDB, dut.be, dut.loe, dut.DIR, dut.CSTEP);
  always @(posedge CLK25) if (trace && (dut.RP1 | dut.RP2 | dut.WSTART | dut.WSTB))
    $display("      t%0t  RP1 %0d RP2 %0d WSTART %0d WSTB %0d  RFA %02h IDB %02h  E %0d WAIT %0d",
             $time, dut.RP1, dut.RP2, dut.WSTART, dut.WSTB, dut.rfa, dut.IDB, E, WAIT_OE);

  bit strace = 0;
  always @(posedge CLK25) if (strace && dut.u_dot.LINETICK)
    $display("      line: SPREN %0d SVC %0d SR %0d SPRVHIT %0d ROWADV %0d VBLANK %0d MODE %0d%0d",
             dut.u_dot.SPREN, {dut.u_dot.SVC8, dut.u_dot.SVC7, dut.u_dot.SVC6, dut.u_dot.SVC5, dut.u_dot.SVC4,
              dut.u_dot.SVC3, dut.u_dot.SVC2, dut.u_dot.SVC1, dut.u_dot.SVC0},
             {dut.u_dot.SR4, dut.u_dot.SR3, dut.u_dot.SR2, dut.u_dot.SR1, dut.u_dot.SR0},
             dut.u_dot.SPRVHIT, dut.ROWADV, dut.VBLANK, dut.MODE1, dut.MODE0);
  int sprdots = 0;
  always @(posedge CLK25) if (strace && dut.u_dot.SPRROW && dut.u_dot.ACTIVE && sprdots < 24
                              && (dut.u_dot.SPRACT || dut.u_dot.SPRHIT || dut.SPRA0 || dut.SPRA1)) begin
    sprdots <= sprdots + 1;
    $display("      h: SHC %0d SPRHIT %0d SPRACT %0d SQ %0d%0d SPRA %0d%0d OE %0d%0d SPRSH %0d",
             {dut.u_dot.SHC9, dut.u_dot.SHC8, dut.u_dot.SHC7, dut.u_dot.SHC6, dut.u_dot.SHC5,
              dut.u_dot.SHC4, dut.u_dot.SHC3, dut.u_dot.SHC2, dut.u_dot.SHC1, dut.u_dot.SHC0},
             dut.u_dot.SPRHIT, dut.u_dot.SPRACT, dut.SQ1, dut.SQ0, dut.SPRA1, dut.SPRA0,
             dut.SPRA1_OE, dut.SPRA0_OE, dut.SPRSH);
  end
  always @(posedge CLK25) if (strace && (dut.SPRLD || (dut.MRQ && !dut.MODE0 && !dut.MODE1)))
    $display("      sprite: MRQ %0d SPRLD %0d fba %05h lanes %02h %02h %02h %02h  SR %0d SPRROW %0d SVC %0d",
             dut.MRQ, dut.SPRLD, dut.fba, dut.lane_rd[0], dut.lane_rd[1], dut.lane_rd[2], dut.lane_rd[3],
             {dut.u_dot.SR4, dut.u_dot.SR3, dut.u_dot.SR2, dut.u_dot.SR1, dut.u_dot.SR0}, dut.u_dot.SPRROW,
             {dut.u_dot.SVC8, dut.u_dot.SVC7, dut.u_dot.SVC6, dut.u_dot.SVC5, dut.u_dot.SVC4,
              dut.u_dot.SVC3, dut.u_dot.SVC2, dut.u_dot.SVC1, dut.u_dot.SVC0});

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
    CCTRL = 5'h17, VSL = 5'h01, VSH = 5'h02, HSL = 5'h03, HSH = 5'h04,
    TILEB = 5'h18, MAPB = 5'h19, SPRX = 5'h1A, SPRY = 5'h1B, SPRH = 5'h1C;
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

  // ---- a frame, as the connector sees it ------------------------------------
  // OMR is the '273s' /MR - "this pixel may show" - so a line is the run of
  // dots it is asserted for, and a pixel whose LUT entry is zero still counts.
  // ⚠ Not "RGB is non-zero", which is what the first frame check here used:
  // every LUT below is the IDENTITY, LUT[a] = a, so each dot of RGB is the
  // whole sixteen-bit LUT address the card formed - the attribute or sprite
  // byte and the pixel - and entry 0 is black.
  logic [15:0] pic [0:479][0:639];
  int pic_lines, pic_badlen;
  task automatic capture();
    int x; bit in_line;
    pic_lines = 0; pic_badlen = 0; x = 0; in_line = 0;
    // a capture that ended at VSYNC's start takes the very next frame
    if (!VSYNC) @(posedge VSYNC);
    @(negedge VSYNC);
    for (int d = 0; d < 800 * 526; d++) begin
      @(posedge CLK25);
      if (VSYNC) break;                               // the frame is over
      if (dut.OMR) begin
        if (!in_line) begin in_line = 1; x = 0; end
        if (x < 640 && pic_lines < 480) pic[pic_lines][x] = RGB;
        x++;
      end else if (in_line) begin
        in_line = 0;
        if (x != 640) pic_badlen++;
        pic_lines++;
      end
    end
  endtask
  // the settings take at the next frame (VSCROLL, the family, HLOAD's copies):
  // let one go by, then capture the one after
  task automatic next_frame();
    @(posedge VSYNC); @(negedge VSYNC);
  endtask
  // the first wrong pixel, and a few around it
  task automatic show_bad(input int y, input int x, input logic [15:0] want);
    $display("      first wrong: line %0d x %0d  got %04h want %04h", y, x, pic[y][x], want);
    $write("      line %0d from x %0d:", y, x < 4 ? 0 : x - 4);
    for (int k = (x < 4 ? 0 : x - 4); k < (x < 4 ? 0 : x - 4) + 12 && k < 640; k++) $write(" %04h", pic[y][k]);
    $display("");
  endtask
  function automatic int lines_of(input int vmode);
    lines_of = vmode[1] ? (vmode[0] ? 480 : 400) : (vmode[0] ? 480 : 400);
  endfunction

  // `+ONLY=a,b` runs the named scenario groups alone - a debug loop, never a
  // claim count (run.sh's TBARGS). Groups: palette direct span copy bitmap
  // sprite char tile.
  string only = "";
  function automatic bit run_group(input string g);
    if (only == "") return 1;
    for (int i = 0; i + g.len() <= only.len(); i++)
      if (only.substr(i, i + g.len() - 1) == g) return 1;
    return 0;
  endfunction

  initial begin
    void'($value$plusargs("ONLY=%s", only));
    dots(20);
    RESET = 0;
    dots(20);

    if (run_group("palette")) begin
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

    end
    if (run_group("direct")) begin
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

    end
    if (run_group("span")) begin
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
    trace = 1;
    set_ptr(WPTR0, 19'h00A00);
    wr(VDATA, 8'h00);
    wait_clear(7, "SPANBUSY after a span-solid");
    trace = 0;
    bad = 0;
    for (int i = 0; i < 20; i++) if (dut.peek(19'h00A00 + i) !== 8'hF1) bad++;
    ok(bad == 0 && dut.peek(19'h00A14) === 8'h00,
       $sformatf("span-solid with SPANLEN 19 is exactly 20 WFG bytes (%0d wrong, next %02h)", bad, dut.peek(19'h00A14)));
    if (bad) begin $write("      got:"); for (int i = 0; i < 22; i++) $write(" %02h", dut.peek(19'h00A00 + i)); $display(""); end
    wr(VDATA, 8'h00);
    wait_clear(7, "SPANBUSY after a second span-solid");
    bad = 0;
    for (int i = 20; i < 40; i++) if (dut.peek(19'h00A00 + i) !== 8'hF1) bad++;
    ok(bad == 0, $sformatf("and a second span-solid with no SPANLEN write is 20 more (%0d wrong) - one SPANLEN, many spans", bad));

    // ============================= WMODE 11: sprite mode, and transparency
    // ⭐ plan §5's fourth WMODE, and the one nothing had ever run: a mask bit
    // of 1 writes WFG and a 0 RETIRES WITHOUT WRITING, which is how software
    // draws a transparent actor at eight pixels a write (keyed-copy.md §6's
    // sprites over a static playfield). Onto a background of $C3, so a
    // transparent pixel that DID write is a byte that does not match - the
    // defect a span-mask test cannot see, because there both values are
    // written.
    for (int i = 0; i < 24; i++) dut.poke(19'h00C00 + i, 8'hC3);
    wr(CTRL, 8'hB0);                                   // WMODE 11, sprite
    set_ptr(WPTR0, 19'h00C04);
    wr(VDATA, 8'b1011_0010);
    wait_clear(7, "SPANBUSY after a sprite-mode write");
    bad = 0;
    for (int i = 0; i < 8; i++)
      if (dut.peek(19'h00C04 + i) !== (((8'b1011_0010 >> (7 - i)) & 1) ? 8'hF1 : 8'hC3)) bad++;
    ok(bad == 0, $sformatf("sprite WMODE: a 1 writes WFG and a 0 leaves the background standing (%0d of 8 wrong)", bad));
    if (bad) begin
      $write("      got:"); for (int i = 0; i < 8; i++) $write(" %02h", dut.peek(19'h00C04 + i)); $display("");
    end
    ok(dut.peek(19'h00C03) === 8'hC3 && dut.peek(19'h00C0C) === 8'hC3,
       "and the byte either side of the eight is untouched");
    // ⚠ AND IT STILL RETIRES: the pointer moves over a transparent pixel, so
    // the next write lands eight pixels on and not where the ink stopped.
    wr(VDATA, 8'b1111_1111);
    wait_clear(7, "SPANBUSY after the second sprite-mode write");
    bad = 0;
    for (int i = 8; i < 16; i++) if (dut.peek(19'h00C04 + i) !== 8'hF1) bad++;
    ok(bad == 0, $sformatf("a transparent pixel RETIRES: the next eight land at WPTR + 8 (%0d wrong)", bad));

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

    // ============================= §2.5: WADV b2, the step-by-two write
    // ⭐ A CELL IS TWO STORES. The map's cell is a four-byte group with the
    // code in lane 0 and the attribute in lane 2, so the console writes a
    // character with two VDATA writes and the pointer steps by two each time -
    // the store count a two-byte cell had. Direct mode, four cells in a row.
    wr(CTRL, 8'h80);                                   // WMODE 00, direct
    wr(WADV, 8'h04);                                   // b2: step by two
    set_ptr(WPTR0, 19'h02000);
    for (int c = 0; c < 4; c++) begin
      wr(VDATA, 8'h41 + c[7:0]);                       // the code, lane 0
      wr(VDATA, 8'h90 + c[7:0]);                       // the attribute, lane 2
    end
    wait_clear(7, "SPANBUSY after four step-by-two cells");
    bad = 0;
    for (int c = 0; c < 4; c++) begin
      if (dut.peek(19'h02000 + c * 4 + 0) !== 8'h41 + c) bad++;   // code
      if (dut.peek(19'h02000 + c * 4 + 2) !== 8'h90 + c) bad++;   // attribute
      if (dut.peek(19'h02000 + c * 4 + 1) !== 8'h00) bad++;       // untouched
      if (dut.peek(19'h02000 + c * 4 + 3) !== 8'h00) bad++;
    end
    ok(bad == 0, $sformatf("WADV b2: two VDATA writes fill a cell's lanes 0 and 2 and step to the next (%0d of 16 wrong)", bad));
    if (bad) begin
      $write("      got:"); for (int i = 0; i < 16; i++) $write(" %02h", dut.peek(19'h02000 + i)); $display("");
    end
    // and the step goes away with the mode bit
    wr(WADV, 8'h00);
    set_ptr(WPTR0, 19'h02100);
    for (int i = 0; i < 4; i++) wr(VDATA, 8'hE0 + i[7:0]);
    wait_clear(7, "SPANBUSY after four ordinary writes");
    bad = 0;
    for (int i = 0; i < 4; i++) if (dut.peek(19'h02100 + i) !== 8'hE0 + i) bad++;
    ok(bad == 0, $sformatf("and with b2 clear the pointer steps by one again (%0d wrong)", bad));

    end
    if (run_group("copy")) begin
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

    end
    // ========================================================== the picture
    // Every LUT entry is its own address from here on (see capture above), so
    // a pixel IS the LUT address the card formed.
    for (int i = 0; i < 65536; i++) dut.poke_lut(i, i[15:0]);
    // VRAM rows 0..511 x 1024: every byte's value is a function of its place,
    // so a wrong row or a wrong column is a wrong pixel
    for (int r = 0; r < 512; r++)
      for (int x = 0; x < 1024; x++) dut.poke(r * 1024 + x, (r * 3 + x) & 8'hFF);

    if (run_group("bitmap")) begin
    // ---------------------------------------------- bitmap, at every scroll
    // Bitmap, VMODE 11: 640 x 480, one VRAM row a line. pixel(y, x) is the
    // byte at ((VSCROLL + y) mod 512, (HSCROLL + x) mod 1024), through
    // sub-palette 0. HSCROLL 0 first; then fine scrolls 1, 2 and 3 - the '153
    // phase and the per-chip rank select (graphics.md §8.2), which nothing on
    // this card had ever displayed - and a wrap of both axes.
    wr(CTRL, 8'h83);
    begin
      int hs_list [5] = '{0, 5, 2, 7, 1021};
      int vs_list [5] = '{0, 0, 3, 0, 509};
      for (int k = 0; k < 5; k++) begin
        int hs, vs, badpx, by, bx; logic [15:0] want, bw;
        hs = hs_list[k]; vs = vs_list[k];
        wr(HSL, hs[7:0]); wr(HSH, {6'd0, hs[9:8]});
        wr(VSL, vs[7:0]); wr(VSH, {7'd0, vs[8]});
        next_frame(); capture();
        badpx = 0; by = -1;
        for (int y = 0; y < 480; y++)
          for (int x = 0; x < 640; x++) begin
            want = {8'h00, 8'((((vs + y) & 511) * 3 + ((hs + x) & 1023)) & 8'hFF)};
            if (pic[y][x] !== want) begin
              if (by < 0) begin by = y; bx = x; bw = want; end
              badpx++;
            end
          end
        ok(pic_lines == 480 && pic_badlen == 0,
           $sformatf("bitmap HSCROLL %0d VSCROLL %0d: 480 lines of 640 (%0d lines, %0d wrong length)",
                     hs, vs, pic_lines, pic_badlen));
        ok(badpx == 0, $sformatf("bitmap HSCROLL %0d VSCROLL %0d: every pixel is the byte at its scrolled address (%0d wrong)",
                                 hs, vs, badpx));
        if (by >= 0) show_bad(by, bx, bw);
      end
      wr(HSL, 8'd0); wr(HSH, 8'd0); wr(VSL, 8'd0); wr(VSH, 8'd0);
    end

    end
    if (run_group("sprite")) begin
    // ------------------------------------------------------ the sprite
    // plan §7: the shape is the top 64 bytes of MAPBASE's 64 KB, a row four
    // bytes - plane 0 columns 0-7 and 8-15, then plane 1's - bit 7 leftmost,
    // the pixel's code (plane1, plane0) the LUT's A9..A8. Every row of this
    // shape is different, and every column of it, so a row or column slip is
    // a wrong pixel: code(r, c) = (r + c) mod 4, transparent where it is 0.
    wr(MAPB, 8'd7);
    for (int r = 0; r < 16; r++) begin
      logic [15:0] p0, p1;
      p0 = 0; p1 = 0;
      for (int c = 0; c < 16; c++) begin
        p0[15 - c] = ((r + c) % 4) & 1;
        p1[15 - c] = (((r + c) % 4) >> 1) & 1;
      end
      dut.poke(19'h7FFC0 + r * 4 + 0, p0[15:8]);
      dut.poke(19'h7FFC0 + r * 4 + 1, p0[7:0]);
      dut.poke(19'h7FFC0 + r * 4 + 2, p1[15:8]);
      dut.poke(19'h7FFC0 + r * 4 + 3, p1[7:0]);
    end
    begin
      int sx_list [3] = '{101, 3, 618};
      int sy_list [3] = '{37, 0, 190};
      int vm_list [3] = '{3, 3, 0};
      for (int k = 0; k < 3; k++) begin
        int sx, sy, vm, badpx, in_spr, by, bx, dbl; logic [15:0] want, bw;
        sx = sx_list[k]; sy = sy_list[k]; vm = vm_list[k];
        dbl = vm[1] ? 1 : 2;
        wr(CTRL, 8'h80 | vm[1:0]);
        wr(SPRX, sx[7:0]); wr(SPRY, sy[7:0]);
        wr(SPRH, {1'b1, 4'd0, sy[8], sx[9:8]});
        next_frame();
        if (k == 0) begin strace = 1; dots(800 * 100); strace = 0; end
        capture();
        badpx = 0; in_spr = 0; by = -1;
        for (int y = 0; y < lines_of(vm); y++)
          for (int x = 0; x < 640; x++) begin
            int row, code;
            row = y / dbl;
            code = 0;
            if (row >= sy && row < sy + 16 && x >= sx && x < sx + 16)
              code = ((row - sy) + (x - sx)) % 4;
            if (code) in_spr++;
            want = {6'd0, 2'(code), 8'((row * 3 + x) & 8'hFF)};
            if (pic[y][x] !== want) begin
              if (by < 0) begin by = y; bx = x; bw = want; end
              badpx++;
            end
          end
        ok(badpx == 0 && in_spr > 0,
           $sformatf("the sprite at (%0d, %0d), VMODE %02b: every pixel, %0d of them its own (%0d wrong)",
                     sx, sy, vm[1:0], in_spr, badpx));
        if (by >= 0) show_bad(by, bx, bw);
      end
      wr(SPRH, 8'h00);
    end

    end
    if (run_group("char")) begin
    // ------------------------------------------------ character mode
    // plan §2.2 and §2.5: MODE 01, VMODE 11 - 80 x 60. The map on the
    // four-byte cell stride, code in lane 0 and attribute in lane 1; glyphs a
    // byte a pixel at TILEBASE; the LUT address {attribute, glyph pixel}.
    // ⭐ HSCROLL, VSCROLL and the sprite are all set, and character mode must
    // show none of them (plan §2.5, §7).
    wr(TILEB, 8'd2);                                  // glyphs at $08000
    wr(MAPB, 8'd5);                                   // map at $50000
    for (int g = 0; g < 256; g++)
      for (int r = 0; r < 8; r++)
        for (int c = 0; c < 8; c++) dut.poke(19'h08000 + g * 64 + r * 8 + c, (g * 7 + r * 8 + c + 1) & 8'hFF);
    for (int row = 0; row < 64; row++)
      for (int col = 0; col < 128; col++) begin
        dut.poke(19'h50000 + row * 1024 + col * 4 + 0, (row * 3 + col) & 8'hFF);   // code
        dut.poke(19'h50000 + row * 1024 + col * 4 + 2, (row + col * 5) & 8'hFF);   // attribute
        dut.poke(19'h50000 + row * 1024 + col * 4 + 1, 8'hDE);                     // unused
        dut.poke(19'h50000 + row * 1024 + col * 4 + 3, 8'hAD);
      end
    wr(HSL, 8'd13); wr(VSL, 8'd11);
    wr(SPRX, 8'd40); wr(SPRY, 8'd40); wr(SPRH, 8'h80);
    begin
      // ⚠ VMODE 00 TWICE, CONSECUTIVELY: a doubled picture's pair phase once
      // alternated from frame to frame (the families' line counts are odd),
      // and one frame in two was right
      int vmc [3] = '{3, 0, 0};
      for (int k = 0; k < 3; k++) begin
        int vm, badpx, by, bx, dbl; logic [15:0] want, bw;
        vm = vmc[k]; dbl = vm[1] ? 1 : 2;
        if (k < 2) begin wr(CTRL, 8'h84 | vm[1:0]); next_frame(); end
        capture();
        badpx = 0; by = -1;
        for (int y = 0; y < lines_of(vm); y++)
          for (int x = 0; x < 640; x++) begin
            int row, crow, grow, col, code, attr;
            row = y / dbl; crow = row >> 3; grow = row & 7; col = x >> 3;
            code = (crow * 3 + col) & 255; attr = (crow + col * 5) & 255;
            want = {8'(attr), 8'((code * 7 + grow * 8 + (x & 7) + 1) & 255)};
            if (pic[y][x] !== want) begin
              if (by < 0) begin by = y; bx = x; bw = want; end
              badpx++;
            end
          end
        ok(pic_lines == lines_of(vm) && pic_badlen == 0,
           $sformatf("character mode VMODE %02b: %0d lines of 640 (%0d, %0d wrong length)",
                     vm[1:0], lines_of(vm), pic_lines, pic_badlen));
        ok(badpx == 0, $sformatf("character mode VMODE %02b (80 x %0d)%s: every pixel is {attribute, glyph pixel} of its own cell, with the scrolls and the sprite ignored (%0d wrong)",
                                 vm[1:0], lines_of(vm) / dbl / 8, k == 2 ? ", the very next frame" : "", badpx));
        if (by >= 0) show_bad(by, bx, bw);
      end
    end

    // ----------------------------- a copy while character mode displays
    // §8.2: the console scrolls by copying, so the copy has to share the spare
    // access with the map - which takes every other one. 13 x 5, from and to
    // places the picture does not read.
    begin
      int bad2, t0;
      for (int r = 0; r < 5; r++)
        for (int c = 0; c < 13; c++) dut.poke(19'h60000 + r * 1024 + 3 + c, 8'h80 + r * 16 + c);
      set_ptr(CPTR0, 19'h60003);
      set_ptr(WPTR0, 19'h62009);
      wr(CWIDTH, 8'd13); wr(CHEIGHT, 8'd5);
      t0 = cp_ticks;
      wr(CCTRL, 8'h01);
      wait_clear(4, "CBUSY after a copy under character mode");
      bad2 = 0;
      for (int r = 0; r < 5; r++)
        for (int c = 0; c < 13; c++)
          if (dut.peek(19'h62009 + r * 1024 + c) !== 8'h80 + r * 16 + c) bad2++;
      if (bad2) for (int r = 0; r < 5; r++) begin
        $write("      dst row %0d:", r);
        for (int c = -1; c < 14; c++) $write(" %02h", dut.peek(19'h62009 + r * 1024 + c));
        $display("");
      end
      ok(bad2 == 0 && cp_ticks - t0 == 130,
         $sformatf("a 13 x 5 copy under character mode lands byte for byte, still two accesses a byte (%0d wrong, %0d accesses)",
                   bad2, cp_ticks - t0));
    end

    end
    if (run_group("tile")) begin
    // ------------------------------------------------------- tile mode
    // plan §2.4: MODE 10, a one-byte code a cell on the same four-byte
    // stride (lane 0), 8bpp tiles at TILEBASE, both scroll axes, ATTR zero.
    // HSCROLL[2] is the cell phase the map's access has to follow (graphics.md
    // §6.4.9): 13 has it set with fine scroll 1, 6 has it set with fine 2, and
    // 16 has it clear. Each with a VSCROLL, 500 wrapping the ring.
    begin
      int ths [3] = '{13, 6, 16};
      int tvs [3] = '{11, 0, 500};
      wr(SPRH, 8'h00);
      for (int k = 0; k < 3; k++) begin
        int hs, vs, badpx, by, bx; logic [15:0] want, bw;
        hs = ths[k]; vs = tvs[k];
        wr(CTRL, 8'h88 | 2'b11);
        wr(HSL, hs[7:0]); wr(HSH, {6'd0, hs[9:8]});
        wr(VSL, vs[7:0]); wr(VSH, {7'd0, vs[8]});
        next_frame(); capture();
        badpx = 0; by = -1;
        for (int y = 0; y < 480; y++)
          for (int x = 0; x < 640; x++) begin
            int ry, cx, crow, ccol, code;
            ry = (vs + y) & 511; cx = (hs + x) & 1023;
            crow = (ry >> 3) & 63; ccol = (cx >> 3) & 127;
            code = (crow * 3 + ccol) & 255;           // lane 0 of the character map above
            want = {8'h00, 8'((code * 7 + (ry & 7) * 8 + (cx & 7) + 1) & 255)};
            if (pic[y][x] !== want) begin
              if (by < 0) begin by = y; bx = x; bw = want; end
              badpx++;
            end
          end
        ok(badpx == 0 && pic_lines == 480,
           $sformatf("tile mode HSCROLL %0d (HSCROLL[2] %0d) VSCROLL %0d: every pixel is its scrolled cell's tile, ATTR zero (%0d wrong, %0d lines)",
                     hs, (hs >> 2) & 1, vs, badpx, pic_lines));
        if (by >= 0) show_bad(by, bx, bw);
      end
    end

    end
    // ================================================================= end
    ok(fba_fights == 0, $sformatf("v3scan and v3ptr never both drive the address bus (%0d dots)", fba_fights));
    ok(dbus_fights == 0, $sformatf("never two drivers on D7..D0 (%0d dots)", dbus_fights));
    ok(luta_fights == 0, $sformatf("never two masters on the LUT address bus (%0d dots)", luta_fights));
    ok(idb_fights == 0, $sformatf("never two drivers on the internal data bus (%0d dots)", idb_fights));
    ok(idb_floats == 0, $sformatf("and nothing ever samples it undriven (%0d dots)", idb_floats));
    ok(lane_floats == 0, $sformatf("no byte is written from a lane nothing drives (%0d dots)", lane_floats));
    ok(rank_fights == 0, $sformatf("each chip's two fetch ranks: exactly one on, always (%0d dots)", rank_fights));
    ok(max_wait < 4000, $sformatf("/WAIT always released (longest %0d dots)", max_wait));
    $display("\n%0d claims, %0d failed", passes + fails, fails);
    $finish;
  end

  // a hang is worse than a failure: bound the whole run
  initial begin
    #200000000;
    $display("FAIL  the bench did not finish");
    $finish;
  end

endmodule
`default_nettype wire
