// THE MACHINE RUNS ITS OWN SOFTWARE, WITH video3 IN THE SLOT, AND THE PICTURE
// IS SAMPLED AT THE CONNECTOR.
//
// software/v3boot/v3boot.asm, assembled by A09 (software/v3boot/mkv3rom.sh),
// executed by mc6809e.v on mainboard.v with video3_card.v in the slot: v3dot,
// v3scan, v3ptr, v3host and the v3lane GAL, all generated from the same term
// lists gal/jedec/cupl.ts compiles for the fitter, plus the board of
// video3/docs/plan.md §13.1. ⚠ U3 and U6 are NOT generated: they are the
// hand-written gal/mmu.v and gal/clkdec.v.
//
// ⭐ WHY THIS EXISTS, AND WHAT ONLY IT CAN SAY. video3's other two benches are
// v3dot_tb, which runs the raster part alone, and v3card_tb, which drives the
// whole card one bus cycle at a time from a task that honours /WAIT. Both are
// models of what software WOULD do. plan.md §15's ladder puts this one last and
// §15.1 says why, quoting graphics.md: on the other card, the bench that handed
// the bus to a CPU core somebody else wrote found three defects that twelve
// testbenches and 543 model claims had missed, and every one of them was a seam
// - the arbiter, /WAIT over E-high, and a poll rule that took the register file
// away from the span that needed it.
//
// So the claims here are deliberately NOT a second pass over v3card_tb's. What
// this bench asks that nothing else can:
//
//   1. ⭐ THAT A REAL INSTRUCTION'S BUS CYCLE IS STRETCHED. v3card_tb's task
//      honours /WAIT because it was written to; this one cannot do otherwise,
//      because E comes out of the motherboard's clkdec, whose phase counter
//      freezes on /WAIT, and the 6809E in the socket is clocked by it. The ROM
//      fires three 256-byte spans back to back with no poll between them; if
//      the hold does not work the second and third triggers are DROPPED and the
//      picture is 256 bytes wide instead of 768. The claim is measured in dots
//      of one E-high, and it names the cycle.
//   2. ⭐ THAT THE VBL INTERRUPT REACHES THE CPU. plan.md §9 makes it NitrOS-9's
//      system tick. Nothing before this had a CPU to interrupt: the card's
//      IRQ_OE was a wire into a counter. Here it is /IRQ on the backplane, the
//      core's vector fetch at $FFF8, a handler that clears the flag by writing
//      VSTAT, and a count that the handler leaves in the card's own +$1F.
//   3. That the motherboard and the card never both drive D7..D0 - one card,
//      one map, one bus, and a CPU that reads it.
//   4. That an engine survives being POLLED. plan.md §10's rule is "read VSTAT
//      until the bit clears", and the register file the copy engine and the
//      span writer walk is addressed by the same RA4..RA0 a CPU access drives.
//      graphics.md §19 item 38 is that seam on the other card. The counts are
//      in the claims, so "it landed" is not separable from "it was poked".
//
// ⛔ WHAT IT FOUND ON ITS FIRST RUN (2026-09-19): the posted palette commit
// fires on every DOT of HLOAD instead of once, so outside VBLANK every entry
// is written twice and PIDX steps twice - section 2a, which asks the question
// on purpose and at a defined point in the frame. v3card_tb cannot see it: its
// four-entry palette is loaded straight after reset, inside VBLANK, where
// v3host's other commit path (PDGO & VBLANK) is a one-dot pulse and correct.
//
// ⚠ AND ONE DEFECT OF ITS OWN, WORTH MORE THAN THE FINDING. The first version
// of machine3.v let DOE go away at E-fall, which is the one instant a 6809E
// samples. Reads did not return zero - mainboard.v holds the last byte anybody
// drove - they returned the last ROM byte fetched, so every status poll in the
// ROM exited early and the card appeared to truncate spans and copies. Three
// "card defects" evaporated when the harness was fixed. machine3.v's D7..D0
// section carries the whole argument.
//
// THE SCREENSHOT is taken from the card's output register enable (OMR), the way
// v3card_tb takes it, and the bench also asserts that OMR is exactly the
// connector's BLANK delayed by two dots - so the capture is derivable from the
// four signals that leave the card and is not reading the card's own idea of
// where it is.
//
// A comment line here must never begin with the simulator's own name.

`default_nettype none

module v3machine_tb;

  // ---- 25.175 MHz. One dot per 2 timesteps; E is this divided by 12. ------
  logic CLK25 = 0;
  always #1 CLK25 <= ~CLK25;

  logic n_reset = 0, fast_e = 0;

  wire [15:0] RGB;
  wire BLANK, HSYNC, VSYNC;
  wire e, q, run, rw, lic, avma;
  wire [15:0] la;
  wire [7:0] cpu_dout, cpu_din;
  wire [24:0] pa;
  wire n_iosel, n_iopage_bp, wait_asserted, irq_asserted, card_drives;
  wire bus_conflict, pa_conflict;
  wire FBA_FIGHT, DBUS_FIGHT, LUTA_FIGHT, IDB_FIGHT, IDB_FLOAT, LANE_FLOAT, RANK_FIGHT;

  /* ⚠ THE OTHER TWO SLOTS, DECLARED AND LEFT EMPTY. machine3.v grew machine.v's
   * audio card and TL16C550C on 2026-09-20, when machine_tb moved onto it with
   * the retargeted boot ROM; both are off by default and this bench leaves them
   * off, so it is the machine it was - one card, and the only interrupt is
   * video3's VBL. The ports are named here because `.*` binds by name and an
   * unnamed one is an error rather than a warning. */
  logic       SLOTCLK = 0;          // the audio card's crystal - unused at AUDIO 0
  wire [7:0]  DACSAMP0, DACSAMP1, DACSAMP2, DACSAMP3;
  wire [7:0]  DACVOL0,  DACVOL1,  DACVOL2,  DACVOL3;
  wire [15:0] ACOUNT;
  wire        firq_asserted;

  machine3 #(.SIMMS(4)) m (.*);

  int fails = 0, claims = 0;
  task automatic ok(input bit good, input string claim);
    claims++;
    if (good) $display("ok    %s", claim);
    else begin fails++; $display("FAIL  %s", claim); end
  endtask

  // ---- v3boot.asm's progress port -----------------------------------------
  // $FF2F, in machine.md §3's free block - it decodes nowhere on this machine,
  // so on real hardware the write does nothing at all. Sampled at E-fall,
  // which is the edge a 6809E write's data is guaranteed on.
  logic [7:0] progress = 8'h00;
  int progress_writes = 0;
  always @(negedge e)
    if (!n_iosel && pa[7:0] == 8'h2F && !rw) begin
      progress <= cpu_dout;
      progress_writes++;
    end

  bit timed_out = 0;
  // ⚠ EVERY WAIT IS BOUNDED AND FAILS LOUDLY. CLAUDE.md: "a hang is worse than
  // a failure" - run.sh's exit code cannot see one and the claim count cannot
  // either, so it presents as "budget more time". The budget is in E cycles,
  // which is the machine's own clock and not the wall's.
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
        claims++; fails++;
        $display("FAIL  %s: progress stuck at $%02h after %0d E cycles (want $%02h)",
                 what, progress, budget, want);
        return;
      end
    end
    claims++;
    $display("ok    %s (%0d E cycles)", what, spent);
  endtask

  // ---- the things that must never happen ----------------------------------
  // Sticky and counted, because each is a single-dot event in a run of
  // millions and a sampled check would miss it. design-review2.md §10: a model
  // that ORs its drivers cannot see a bus fight, so machine3.v and
  // video3_card.v do not OR them and this counts what they report.
  int n_bus_conflict = 0, n_pa_conflict = 0;
  int n_fba = 0, n_dbus = 0, n_luta = 0, n_idbf = 0, n_idbz = 0, n_lane = 0, n_rank = 0;
  always @(posedge CLK25) if (n_reset) begin
    if (bus_conflict) n_bus_conflict++;
    if (pa_conflict)  n_pa_conflict++;
    if (FBA_FIGHT)  n_fba++;
    if (DBUS_FIGHT) n_dbus++;
    if (LUTA_FIGHT) n_luta++;
    if (IDB_FIGHT)  n_idbf++;
    if (IDB_FLOAT)  n_idbz++;
    if (LANE_FLOAT) n_lane++;
    if (RANK_FIGHT) n_rank++;
  end

  // ---- /WAIT, measured in the CPU's own cycles ----------------------------
  /* ⭐ THE CLAIM ONLY THIS BENCH CAN MAKE. A 6809E's E comes from the board,
   * and clkdec's phase counter holds every bit with `Cn & WAIT`, so an
   * asserted /WAIT freezes E-high and the CPU with it. What is measured here
   * is therefore not "the card asserted a signal" but "this instruction's bus
   * cycle lasted N dots instead of six", with the cycle named. */
  int  ehi = 0, max_ehi = 0, waited_cycles = 0, wait_dots = 0;
  logic [15:0] cyc_la, max_la;
  bit cyc_rw, cyc_win, cyc_waited, max_rw, max_win, max_waited;
  logic e_prev = 0;
  always @(posedge CLK25) begin
    e_prev <= e;
    if (wait_asserted) wait_dots++;
    if (e) begin
      if (!e_prev) begin
        cyc_la <= la; cyc_rw <= rw; cyc_waited <= 1'b0;
        // the VRAM window: a plain physical cycle, A19 = 1, A20 = 0, and NOT
        // in the I/O page (n_iopage_bp is the backplane's, active low)
        cyc_win <= n_iopage_bp & pa[19] & ~pa[20];
      end
      ehi <= ehi + 1;
      if (wait_asserted) cyc_waited <= 1'b1;
    end else if (e_prev) begin
      if (cyc_waited) waited_cycles++;
      if (ehi > max_ehi) begin
        max_ehi <= ehi; max_la <= cyc_la; max_rw <= cyc_rw;
        max_win <= cyc_win; max_waited <= cyc_waited;
      end
      ehi <= 0;
    end
  end

  // ---- how much the CPU poked the card WHILE an engine was running --------
  /* ⭐ graphics.md §19 item 38 on the other card was exactly this: "§7.4's own
   * 'poll VSTAT' rule took the register file away from the span whose colour
   * that file is". The rule plan.md §10 hands software is "read VSTAT until
   * the bit clears", and the file the engines walk is addressed by the same
   * RA4..RA0 a CPU access drives. So the count is evidence for the claims
   * below: a copy that lands byte for byte with forty reads over the top of it
   * is a different statement from one that ran undisturbed. */
  int polls_spanbusy = 0, polls_cbusy = 0;
  logic cardrd_prev = 0;
  always @(posedge CLK25) begin
    cardrd_prev <= m.card.IOSEL & m.card.A6 & m.card.A5 & m.card.RW & m.card.E;
    if ((m.card.IOSEL & m.card.A6 & m.card.A5 & m.card.RW & m.card.E) & ~cardrd_prev) begin
      if (m.card.SPANBUSY) polls_spanbusy++;
      if (m.card.CBUSY)    polls_cbusy++;
    end
  end

  // ---- the VBL interrupt, on the wire and in the core ---------------------
  int irq_rise = 0, irq_fall = 0, vec_fetch = 0, irq_after_off = 0;
  logic irq_prev = 0;
  bit watch_off = 0;
  always @(posedge CLK25) begin
    irq_prev <= irq_asserted;
    if (irq_asserted & ~irq_prev) irq_rise++;
    if (~irq_asserted & irq_prev) irq_fall++;
    if (watch_off & irq_asserted) irq_after_off++;
  end
  // the 6809E's IRQ vector is at $FFF8 - a read of it is the core taking the
  // interrupt, which no counter on the card can see
  always @(negedge e) if (rw && la == 16'hFFF8) vec_fetch++;

  // dots since time zero, so a trace line says WHEN as well as what
  int dotcount = 0;
  always @(posedge CLK25) dotcount++;

  // ---- ⭐ every LUT write, and every one after the load is finished --------
  // The palette is 256 entries and the ROM writes each one once, so a load
  // that takes more writes than it has entries is already wrong - and once the
  // load is checked, NOTHING may write the LUT again until software asks.
  bit watch_lut = 0;
  int lutwe_after = 0, lutwe_all = 0, lw_n = 0;
  logic [15:0] lw_a [0:511], lw_d [0:511];
  logic [7:0]  lw_idxl [0:511];
  int          lw_t [0:511];
  bit          lw_vbl [0:511], lw_hl [0:511];
  always @(posedge CLK25) if (n_reset && m.card.LUTWE) begin
    lutwe_all++;
    if (watch_lut) lutwe_after++;
    if (lw_n < 512) begin
      lw_a[lw_n] = m.card.lut_a;
      lw_d[lw_n] = {m.card.pdath, m.card.pdatl};
      lw_idxl[lw_n] = m.card.pidx_lo;
      lw_t[lw_n] = dotcount;
      lw_vbl[lw_n] = m.card.VBLANK; lw_hl[lw_n] = m.card.HLOAD;
      lw_n++;
    end
  end

  // ---- OMR against the connector ------------------------------------------
  // plan.md §9.2: the '273s' /MR is BLANK two registers late, so the dot that
  // may show is ~BLANK delayed by two. Asserting it is what makes capturing on
  // OMR the same thing as capturing on the four signals that leave the card.
  logic [1:0] blank_sr = 2'b11;
  int omr_mismatch = 0;
  always @(posedge CLK25) begin
    blank_sr <= {blank_sr[0], BLANK};
    if (n_reset && (m.card.OMR !== ~blank_sr[1])) omr_mismatch++;
  end

  // ---- the picture ---------------------------------------------------------
  // VMODE 00 is 640 x 200 doubled to 400 lines (plan.md §2.1). A line is the
  // run of dots OMR is asserted for, and a pixel whose LUT entry is zero still
  // counts - "RGB is non-zero" is not the test.
  logic [15:0] pic [0:399][0:639];
  int pic_lines, pic_badlen;
  // the first 16 dots of the first captured line, from inside the card: what
  // the fetch addressed, what the four lanes held, which one the '153 picked
  // and what the index latch took. Printed only when the picture fails, and
  // there to say WHERE a wrong pixel came from rather than only that it is
  // wrong.
  logic [16:0] d_fba [0:15];
  logic [7:0]  d_l [0:15][0:3];
  logic [7:0]  d_pix [0:15], d_idx [0:15];
  logic [1:0]  d_sel [0:15];
  logic [2:0]  d_oea [0:15], d_oeb [0:15];
  logic [15:0] d_luta [0:15], d_rgbq [0:15];
  logic [4:0]  d_en [0:15];
  task automatic capture();
    int x; bit in_line;
    pic_lines = 0; pic_badlen = 0; x = 0; in_line = 0;
    if (!VSYNC) @(posedge VSYNC);
    @(negedge VSYNC);
    for (int d = 0; d < 800 * 526; d++) begin
      @(posedge CLK25);
      if (VSYNC) break;
      if (m.card.OMR) begin
        if (!in_line) begin in_line = 1; x = 0; end
        if (x < 640 && pic_lines < 400) pic[pic_lines][x] = RGB;
        if (x < 16 && pic_lines == 0) begin
          d_fba[x] = m.card.fba;
          d_l[x][0] = m.card.lane_rd[0]; d_l[x][1] = m.card.lane_rd[1];
          d_l[x][2] = m.card.lane_rd[2]; d_l[x][3] = m.card.lane_rd[3];
          d_pix[x] = m.card.pix; d_idx[x] = m.card.pixidx; d_sel[x] = m.card.sel;
          d_oea[x] = {m.card.OEA2, m.card.OEA1, m.card.OEA0};
          d_oeb[x] = {m.card.OEB2, m.card.OEB1, m.card.OEB0};
          d_luta[x] = m.card.lut_a; d_rgbq[x] = m.card.rgb_q;
          d_en[x] = {m.card.PIXOE, m.card.PIDXOE, m.card.OMR, m.card.LUTWE, m.card.PALTURN};
        end
        x++;
      end else if (in_line) begin
        in_line = 0;
        if (x != 640) pic_badlen++;
        pic_lines++;
      end
    end
  endtask

  // ---- what v3boot.asm drew, stated once ----------------------------------
  /* ⚠ THE GLYPH'S BYTES ARE WRITTEN OUT HERE AND IN THE ROM, on purpose. The
   * bench could read them out of the loaded image, and then a typo in the
   * table would agree with itself. Eight literals in two places is the cheapest
   * independent statement there is. */
  localparam logic [7:0] GLYPH [0:7] = '{8'hF0, 8'hC8, 8'hA4, 8'h92, 8'h89, 8'h45, 8'h23, 8'h17};
  localparam int ROW = 1024;               // plan.md §2.5: a VRAM row

  // the bench's background, put in VRAM before the machine starts: a function
  // of the byte's place, so a wrong row or column is a wrong pixel
  function automatic logic [7:0] bg(input int r, input int c);
    bg = 8'((r * 5 + c * 3 + 1) & 8'hFF);
  endfunction

  // the index at VRAM row r, column c after the ROM has run
  function automatic logic [7:0] drew(input int r, input int c);
    if (r == 2 && c < 8)                                     drew = 8'(8'h30 + c);
    else if (r == 4 && c < 64)                               drew = 8'h3C;
    else if (r >= 8  && r < 16 && c >= 16 && c < 24)
      drew = GLYPH[r - 8][7 - (c - 16)]  ? 8'hF1 : 8'hB2;
    else if (r >= 20 && r < 28 && c >= 32 && c < 40)
      drew = GLYPH[r - 20][7 - (c - 32)] ? 8'hF1 : 8'hB2;
    else if (r == 40 && c < 768)                             drew = 8'h5A;
    else                                                     drew = bg(r, c);
  endfunction

  // the palette v3boot.asm loaded: entry i is $(~i)(i)
  function automatic logic [15:0] pal(input logic [7:0] i);
    pal = {~i, i};
  endfunction

  task automatic show_bad(input int y, input int x, input logic [15:0] want);
    $display("      first wrong: line %0d x %0d  got %04h want %04h", y, x, pic[y][x], want);
    $write("      line %0d from x %0d:", y, x < 4 ? 0 : x - 4);
    for (int k = (x < 4 ? 0 : x - 4); k < (x < 4 ? 0 : x - 4) + 12 && k < 640; k++)
      $write(" %04h", pic[y][k]);
    $display("");
  endtask

  // ---- the run -------------------------------------------------------------
  int bad, by, bx;
  logic [15:0] lut_snap [0:255];
  logic [15:0] bw;
  logic [7:0] fcnt, ramcnt;

  initial begin
    m.mb.load_rom_file("../../../software/v3boot/v3boot.hex");
    ok(m.mb.rom[20'h1FFE] === 8'hE0 && m.mb.rom[20'h1FFF] === 8'h00,
       "the fixture image is in the ROM and $1FFE holds the reset vector $E000");

    /* ⚠ ONE REGISTER IN THE VENDOR CORE HAS TO BE INITIALISED HERE, and it is
     * a property of the SIMULATOR rather than of the machine - machine_tb.sv
     * carries the whole argument. mc6809i.v holds NMILatched in a flip-flop
     * with an asynchronous set and no reset; in a two-state simulator X is 0,
     * so the core takes an NMI before its first instruction. nNMI is tied high
     * on this board (machine.md §2.1 lists no NMI source at all), so the
     * machine can never assert it. */
    m.cpu.cpucore.NMILatched = 1'b1;

    // the background, before power: 256 rows of it, which is more than the 200
    // this mode displays, so a scan that runs off the bottom shows a wrong
    // pixel rather than an X
    for (int r = 0; r < 256; r++)
      for (int c = 0; c < 1024; c++) m.card.poke(r * ROW + c, bg(r, c));

    repeat (240) @(posedge CLK25);
    n_reset = 1;

    $display("");
    $display("1. Boot - machine.md 7.2, and the map the ROM then uses");
    $display("");
    wait_progress(8'h01, 4000, "the machine leaves boot mode, the SIMM answers and the stack is up");
    ok(run === 1'b1, "and RUN is asserted - the '244 is off the physical address bus");
    // the sixteen entries it wrote, read out of the map SRAMs rather than out
    // of the ROM's opinion of them
    ok(m.mb.map_lo_at(1) === 8'h40 && m.mb.map_hi_at(1) === 8'h00,
       $sformatf("block 1 points at the card's VRAM window (map %02h %02h)",
                 m.mb.map_hi_at(1), m.mb.map_lo_at(1)));
    ok(m.mb.map_lo_at(6) === 8'h06 && m.mb.map_hi_at(6) === 8'h02,
       "block 6 points at the SIMM, which is where the stack and the counter are");
    ok(m.mb.map_lo_at(7) === 8'h00 && m.mb.map_hi_at(7) === 8'h01,
       "and block 7 at the ROM page it is executing out of");

    $display("");
    $display("2a. The palette index's auto-increment, out of VBLANK on purpose");
    $display("");
    wait_progress(8'h02, 200000,
                  "eight entries written with PIDX set once and left to step itself");
    bad = 0;
    for (int i = 0; i < 8; i++)
      if (m.card.peek_lut('h100 + i) !== {8'(8'hB0 + i), 8'(8'hA0 + i)}) bad++;
    /* ⛔ plan.md §10: "PIDX - 16 bits, the whole LUT. Auto-increments after
     * PDATH". v3boot.asm writes PIDX once and then eight entries, at the top
     * of the active area so that every commit takes v3host's PPEND/HLOAD path
     * rather than its PDGO & VBLANK one. */
    ok(bad == 0,
       $sformatf("PIDX steps by one an entry: the eight land at LUT $0100..$0107 (%0d wrong)", bad));
    if (bad) begin
      for (int i = 0; i < 16; i++)
        $display("      LUT[%04h] = %04h  (entry %0d wants %04h)",
                 'h100 + i, m.card.peek_lut('h100 + i), i,
                 i < 8 ? {8'(8'hB0 + i), 8'(8'hA0 + i)} : 16'h0000);
      $display("      %0d LUT writes for eight entries; every one of them:", lw_n);
      for (int k = 0; k < lw_n && k < 24; k++)
        $display("      write %2d at dot %7d (+%5d): LUT[%04h] <= %04h  (pidx_lo %02h, VBLANK %0d, HLOAD %0d)",
                 k, lw_t[k], k > 0 ? lw_t[k] - lw_t[k-1] : 0, lw_a[k], lw_d[k],
                 lw_idxl[k], lw_vbl[k], lw_hl[k]);
    end

    $display("");
    $display("2b. 256 entries in sub-palette 0, with the index written every time");
    $display("");
    wait_progress(8'h0B, 400000, "256 palette entries through PIDX/PDATL/PDATH");
    bad = 0;
    for (int i = 0; i < 256; i++) if (m.card.peek_lut(i) !== pal(8'(i))) bad++;
    ok(bad == 0, $sformatf("every one of them is in the LUT, read out of the array the display reads (%0d wrong)", bad));
    if (bad) for (int i = 0; i < 8; i++)
      $display("      LUT[%0d] = %04h  (want %04h)", i, m.card.peek_lut(i), pal(8'(i)));
    ok(m.card.peek_lut('h200) === 16'h0000 && m.card.peek_lut('h2FF) === 16'h0000,
       "and nothing landed in a sub-palette the ROM never named");
    // the snapshot the picture's last claim is measured against
    for (int i = 0; i < 256; i++) lut_snap[i] = m.card.peek_lut(i);
    watch_lut = 1;

    $display("");
    $display("3. Direct VDATA writes, and reading them back through the same port");
    $display("");
    wait_progress(8'h03, 20000, "eight direct VDATA writes");
    bad = 0;
    for (int i = 0; i < 8; i++) if (m.card.peek(2 * ROW + i) !== 8'(8'h30 + i)) bad++;
    ok(bad == 0, $sformatf("$30..$37 are at VRAM row 2, byte 0 on (%0d wrong)", bad));
    ok(m.card.peek(2 * ROW + 8) === bg(2, 8) && m.card.peek(2 * ROW - 1) === bg(1, 1023),
       "and the bytes either side of them still hold the background");
    wait_progress(8'h04, 20000, "and the ROM read all eight back in order through VDATA's post-increment");

    $display("");
    $display("4. The span writer, and 5. WADV 01 chaining a glyph");
    $display("");
    wait_progress(8'h05, 20000, "a span-solid of 64 bytes");
    bad = 0;
    for (int i = 0; i < 64; i++) if (m.card.peek(4 * ROW + i) !== 8'h3C) bad++;
    ok(bad == 0 && m.card.peek(4 * ROW + 64) === bg(4, 64),
       $sformatf("SPANLEN 63 wrote exactly 64 bytes of WFG and stopped (%0d wrong, next %02h)",
                 bad, m.card.peek(4 * ROW + 64)));
    wait_progress(8'h06, 20000, "eight span-mask writes chained by WADV 01");
    bad = 0;
    for (int r = 0; r < 8; r++)
      for (int c = 0; c < 8; c++)
        if (m.card.peek((8 + r) * ROW + 16 + c) !== drew(8 + r, 16 + c)) bad++;
    ok(bad == 0, $sformatf("the glyph is eight rows at the SAME column, ink where the mask bit is 1, bit 7 first (%0d of 64 wrong)", bad));
    if (bad) for (int r = 0; r < 8; r++) begin
      $write("      row %0d:", r);
      for (int c = -1; c < 9; c++) $write(" %02h", m.card.peek((8 + r) * ROW + 16 + c));
      $display("");
    end
    bad = 0;
    for (int r = 7; r < 17; r++)
      for (int c = 14; c < 26; c++)
        if ((r < 8 || r > 15 || c < 16 || c > 23) && m.card.peek(r * ROW + c) !== bg(r, c)) bad++;
    ok(bad == 0, $sformatf("and the ring around it is untouched background (%0d)", bad));

    $display("");
    $display("6. Copyrect");
    $display("");
    wait_progress(8'h07, 40000, "an 8 x 8 copyrect of the glyph");
    bad = 0;
    for (int r = 0; r < 8; r++)
      for (int c = 0; c < 8; c++)
        if (m.card.peek((20 + r) * ROW + 32 + c) !== m.card.peek((8 + r) * ROW + 16 + c)) bad++;
    /* ⭐ WITH THE CPU ALL OVER IT. v3boot.asm polls CBUSY the way plan.md §10
     * says to, so the register file the copy engine walks had the CPU's own
     * RA4..RA0 on it for six dots of every poll. graphics.md §19 item 38 is
     * that seam on the other card, and this is the claim that would have
     * caught it. */
    ok(bad == 0, $sformatf("it lands byte for byte where WPTR points, through %0d CPU reads of the card while CBUSY (%0d of 64 wrong)",
                           polls_cbusy, bad));
    if (bad) for (int r = 0; r < 8; r++) begin
      $write("      dst row %0d:", r);
      for (int c = -1; c < 9; c++) $write(" %02h", m.card.peek((20 + r) * ROW + 32 + c));
      $display("");
    end
    bad = 0;
    for (int r = 19; r < 29; r++)
      for (int c = 30; c < 42; c++)
        if ((r < 20 || r > 27 || c < 32 || c > 39) && m.card.peek(r * ROW + c) !== bg(r, c)) bad++;
    ok(bad == 0, $sformatf("and nothing around it moves (%0d)", bad));

    $display("");
    $display("7. The /WAIT block - three 256-byte spans, back to back, unpolled");
    $display("");
    wait_progress(8'h08, 40000, "three span triggers through the VRAM window with no poll between them");
    bad = 0;
    for (int i = 0; i < 768; i++) if (m.card.peek(40 * ROW + i) !== 8'h5A) bad++;
    /* ⛔ THIS IS THE CLAIM THE HOLD IS FOR. If /WAIT did not stretch the
     * CPU's cycle the second and third stores would arrive while SPANBUSY was
     * still set, v3host would refuse them (WSTBV is gated on it), and the row
     * would be 256 bytes wide. */
    ok(bad == 0 && m.card.peek(40 * ROW + 768) === bg(40, 768),
       $sformatf("all three spans ran: 768 bytes of WFG in one row (%0d wrong, next %02h)",
                 bad, m.card.peek(40 * ROW + 768)));
    if (bad) begin
      int first_bad;
      first_bad = -1;
      for (int i = 0; i < 800; i++)
        if (m.card.peek(40 * ROW + i) !== 8'h5A && first_bad < 0) first_bad = i;
      $display("      row 40: first byte that is not WFG is %0d", first_bad);
      for (int base = 0; base < 800; base += 32) begin
        $write("      +%04d:", base);
        for (int i = 0; i < 32; i++) $write(" %02h", m.card.peek(40 * ROW + base + i));
        $display("");
      end
      $display("      (the background there would be %02h %02h %02h)",
               bg(40, 0), bg(40, 1), bg(40, 2));
    end
    ok(max_ehi > 200 && max_waited && max_win && !max_rw,
       $sformatf("⭐ and a REAL instruction's bus cycle was stretched to %0d dots by /WAIT - a write at logical $%04h in the VRAM window, where an unwaited E-high is 6",
                 max_ehi, max_la));
    ok(waited_cycles >= 2,
       $sformatf("at least the second and third stores were held (%0d waited cycles, %0d dots of /WAIT so far)",
                 waited_cycles, wait_dots));
    ok(polls_spanbusy > 0,
       $sformatf("and a span survives being polled: %0d CPU reads of the card landed while SPANBUSY", polls_spanbusy));

    $display("");
    $display("8. The picture, sampled at the connector");
    $display("");
    wait_progress(8'hFF, 40000, "the display is enabled");
    capture();
    ok(pic_lines == 400 && pic_badlen == 0,
       $sformatf("VMODE 00 is 400 lines of 640 dots (%0d lines, %0d of the wrong length)",
                 pic_lines, pic_badlen));
    bad = 0; by = -1;
    for (int y = 0; y < 400; y++)
      for (int x = 0; x < 640; x++) begin
        logic [15:0] want;
        /* ⭐ THE CARD'S OWN LUT, NOT THE BENCH'S IDEA OF IT. What this claim
         * is about is the drawing and the raster: the byte the ROM put at that
         * VRAM address, fetched by the scan, picked by the '153, latched, and
         * looked up. Whether the LUT holds what software asked for is 2a and
         * 2b's question and is claimed there; taking the entry from the card
         * keeps one defect to one failing claim. */
        want = m.card.peek_lut(drew(y / 2, x));
        if (pic[y][x] !== want) begin
          if (by < 0) begin by = y; bx = x; bw = want; end
          bad++;
        end
      end
    ok(bad == 0, $sformatf("every pixel is its own LUT entry for the byte the ROM drew - the line is doubled, both scrolls are zero (%0d wrong)", bad));
    if (by >= 0) begin
      show_bad(by, bx, bw);
      for (int y = 0; y < 3; y++) begin
        $write("      pic line %0d:", y);
        for (int k = 0; k < 12; k++) $write(" %04h", pic[y][k]);
        $display("");
      end
      for (int r = 0; r < 2; r++) begin
        $write("      vram row %0d:", r);
        for (int k = 0; k < 12; k++) $write(" %02h", m.card.peek(r * ROW + k));
        $display("");
      end
      $display("      dot  fba    lanes 0..3      sel pix idx  oea oeb  luta rgbq  PIXOE/PIDXOE/OMR/LUTWE/PALTURN");
      for (int k = 0; k < 16; k++)
        $display("      %3d  %05h  %02h %02h %02h %02h  %0d   %02h  %02h   %03b %03b  %04h %04h  %05b",
                 k, d_fba[k], d_l[k][0], d_l[k][1], d_l[k][2], d_l[k][3],
                 d_sel[k], d_pix[k], d_idx[k], d_oea[k], d_oeb[k],
                 d_luta[k], d_rgbq[k], d_en[k]);
    end
    begin
      int changed;
      changed = 0;
      for (int i = 0; i < 256; i++) if (m.card.peek_lut(i) !== lut_snap[i]) changed++;
      ok(changed == 0 && lutwe_after == 0,
         $sformatf("⭐ and the palette is still the palette: %0d entries moved and %0d LUT writes happened after the load",
                   changed, lutwe_after));
      if (lutwe_after) for (int k = 0; k < 16 && k < lutwe_after; k++)
        $display("      unasked LUT write %0d: addr %04h data %04h (pidx_lo %02h)",
                 k, lw_a[k], lw_d[k], lw_idxl[k]);
    end
    ok(omr_mismatch == 0,
       $sformatf("and the dot that shows is exactly the connector's BLANK two dots late (%0d dots disagree)", omr_mismatch));

    $display("");
    $display("9. The VBL interrupt - plan.md 9, on the backplane and in the core");
    $display("");
    wait_progress(8'h10, 300000, "three VBL interrupts are taken and serviced");
    fcnt   = m.card.peek_rf(5'h1F);
    ramcnt = m.mb.peek_dram(32'h00C010);
    ok(vec_fetch >= 3,
       $sformatf("⭐ the core fetched the IRQ vector at $FFF8 (%0d times) - /IRQ reached the CPU", vec_fetch));
    ok(irq_rise >= 3 && irq_fall >= 3,
       $sformatf("and the card asserted and released /IRQ once a frame (%0d rises, %0d falls) - the handler's VSTAT write clears the flag",
                 irq_rise, irq_fall));
    ok(fcnt === ramcnt && fcnt >= 8'd3,
       $sformatf("the handler's frame count is in the card's own +$1F (%0d) and in RAM (%0d) - plan.md 10's spare byte",
                 fcnt, ramcnt));
    // with CTRL b6 cleared the card must stop pulling the line: watch a frame
    watch_off = 1;
    repeat (800 * 526) @(posedge CLK25);
    watch_off = 0;
    ok(irq_after_off == 0,
       $sformatf("and with the enable cleared it stops pulling /IRQ, though VBL keeps happening (%0d dots)", irq_after_off));

    $display("");
    $display("10. What must never have happened");
    $display("");
    ok(n_bus_conflict == 0,
       $sformatf("the card and the motherboard never both drove D7..D0 (%0d dots)", n_bus_conflict));
    ok(n_pa_conflict == 0,
       $sformatf("never two drivers on physical A20-A13 (%0d dots)", n_pa_conflict));
    ok(n_fba == 0,  $sformatf("never two parts on the framebuffer address bus (%0d dots)", n_fba));
    ok(n_dbus == 0, $sformatf("never two of the host '245, the VSTAT '244 and vread on D7..D0 (%0d dots)", n_dbus));
    ok(n_luta == 0, $sformatf("never two masters on the LUT address bus (%0d dots)", n_luta));
    ok(n_idbf == 0, $sformatf("never two drivers on the card's internal data bus (%0d dots)", n_idbf));
    ok(n_idbz == 0, $sformatf("and nothing ever sampled it undriven (%0d dots)", n_idbz));
    ok(n_lane == 0, $sformatf("no byte was written from a lane nothing drives (%0d dots)", n_lane));
    ok(n_rank == 0, $sformatf("each chip's two fetch ranks: exactly one on, always (%0d dots)", n_rank));
    ok(!wait_asserted && max_ehi < 4000,
       $sformatf("/WAIT was always released - the longest E-high in the run was %0d dots", max_ehi));

    $display("");
    $display("      %0d progress writes, %0d waited cycles, %0d dots of /WAIT",
             progress_writes, waited_cycles, wait_dots);
    $display("      %0d dots of machine time - %0d us at 25.175 MHz",
             dotcount, dotcount / 25);
    $display("");
    $display("%0d claims, %0d failed", claims, fails);
    $finish;
  end

  // a hang is worse than a failure: bound the whole run, and say so
  initial begin
    #20000000;
    $display("FAIL  the bench did not finish - progress stuck at $%02h", progress);
    $display("");
    $display("%0d claims, %0d failed", claims + 1, fails + 1);
    $finish;
  end

endmodule
`default_nettype wire
