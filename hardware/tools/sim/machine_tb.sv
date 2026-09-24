// THE MACHINE RUNS ITS OWN SOFTWARE, AND THE PICTURE IS SAMPLED AT THE
// CONNECTOR.
//
// software/boot/boot.asm, assembled by A09 (software/tools/mkrom.sh), executed
// by mc6809e.v on mainboard.v with video3_card.v in a slot - machine3.v. U9,
// U10 and the video card's four ATF1508AS and one GAL are generated from the
// same term lists hardware/tools/gal/jedec/cupl.ts compiles for the fitter. ⚠ U3 and
// U6 are NOT: they are the hand-written mainboard/sim/mmu.v and mainboard/sim/clkdec.v, checked
// against their fuse maps by check:sim and jedec/cupl.check.ts rather than
// generated.
//
// ⭐ RETARGETED TO video3 ON 2026-09-20, with the ROM. Until then this bench
// ran machine.v - the same motherboard with hardware/archive/video/'s card - and the
// claims below that are the MOTHERBOARD's are unchanged, on purpose: the walk,
// the descriptor, the sixteen map entries, TASK 1, stage 2 read out of the
// DRAM array, the store-rate subtraction and the six population/fault
// scenarios all say exactly what they said, so what changed between a passing
// run and a failing one is the card. machine.v and video_card.v are still
// here; demo_tb.sv still instantiates them (hardware/archive/README.md).
//
// ⚠ THREE THINGS THE CARD CHANGED, and each is a claim below rather than an
// assumption:
//   1. SYNC POLARITY. video_card.v drove HSYNC and VSYNC in CONNECTOR sense,
//      so this bench read graphics.md §6.2.1's rule off VMODE. video3_card.v
//      does not: v3dot's own comment says the polarity "is not this term's
//      business" and nothing else on the card applies it, so both syncs leave
//      the card ASSERTED HIGH in both families. §6.2.1 is therefore not built
//      on this card - see the claim at the end of scene 6.
//   2. BLANK LEADS THE PICTURE BY TWO DOTS. plan.md §9.2 makes the output
//      '273s' /MR "BLANK two registers late", so the connector's BLANK is the
//      early copy. The capture therefore samples ~BLANK delayed by two, and
//      asserts that the delayed copy is exactly the card's own OMR - which is
//      what keeps the screenshot a function of the four connector signals.
//   3. NO DISPLAY LIST. plan.md §0 deletes it; the two scenes that ran one are
//      now the copy engine and the sprite, which is what boot.asm §7 draws.
//
// ⚠ EVERY GENERATED PART IS IN ASSERTED SENSE, and the wrappers invert the
// backplane lines by hand, so no claim here can see a pin declared with the
// wrong polarity - nine of them passed this bench until 2026-09-11.
// tools/gal/pins.check.ts is what holds pin senses.
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
  // ⭐ THE AUDIO CARD'S CRYSTAL, 28.37516 MHz (audio.md 4.1), in this bench's
  // time base: a dot is two timesteps, so a half period is 17.621 / 19.861 of
  // one. Neither clock is a multiple of the other, so the card's host port
  // sees E at every phase, as on the backplane. demo_tb does the same in ps.
  logic SLOTCLK = 0;
  always #0.8872 SLOTCLK <= ~SLOTCLK;
  wire [7:0] DACSAMP0, DACSAMP1, DACSAMP2, DACSAMP3;
  wire [7:0] DACVOL0, DACVOL1, DACVOL2, DACVOL3;
  wire [15:0] ACOUNT;
  wire firq_asserted, irq_asserted;

  logic n_reset = 0, fast_e = 0;

  /* ⭐ THE STORAGE CARD'S SOCKET SWITCH. Since 2026-09-21 this bench has the
   * WHOLE card (machine3.v STORAGE = 1) with sd_model.v in the socket, and
   * `sd_cd` is only the mechanical contact: what the card ANSWERS comes off
   * the image run-machine.sh passes in `+sdimage=`.
   *
   * ⛔ THAT CHANGED WHAT `disk` MEANS, and it had to. boot.asm §10b reads
   * block 0 and requires CMD58's CCS and sdcard.md §9.5's signature before
   * §10a will draw "Disk found", so a closed switch over a stub that cannot
   * answer CMD0 is no longer the found state - it is the THIRD state, the
   * Macintosh's question mark, "there is a disk and it is not a system
   * disk". `disk` therefore carries a real, blessed card image and `nodisk`
   * an open socket. The SIMM and fault runs leave sd_cd 0 and never read any
   * of it: §10a only gets as far as the card at all when there is a TOOLBOX
   * on ROM page 64, which only the whole-ROM scenarios have.
   *
   * ⛔ AND `nitros9`/`reboot` NEED A REAL CARD SINCE 2026-09-22, because that
   * is where NitrOS-9 now is. ROM pages 3-63 are zeros; `boot_sd` reads
   * `OS9Boot` over SPI out of the image run-machine.sh builds with
   * software/nitros9/mksyscard.sh, and a run with an empty socket reaches
   * `krn` and takes D.Crash. */
  logic sd_cd = 0;

  /* ⚠ THE WHOLE SYSTEM CARD FITS IN THE MODEL, and that is what sets this.
   * mksyscard.sh writes ~898 KB - the bootfile, the command set, /MODULES,
   * /SYS and the demo data - so sd_model.v's array has to span it or
   * `arg % NBLOCKS` would wrap a read of the bootfile back onto block 0.
   * `disk`'s much smaller image is padded to the same length by
   * run-machine.sh, for the reason its comment gives. */
  localparam int SDB = 1792;

  wire [15:0] RGB;
  wire BLANK, HSYNC, VSYNC;
  wire e, q, run, rw, lic, avma;
  wire [15:0] la;
  wire [7:0] cpu_dout, cpu_din;
  wire [24:0] pa;
  wire n_iosel, n_iopage_bp, wait_asserted, card_drives;
  wire bus_conflict, pa_conflict;
  wire FBA_FIGHT, DBUS_FIGHT, LUTA_FIGHT, IDB_FIGHT, IDB_FLOAT, LANE_FLOAT, RANK_FIGHT;

  // SERIAL: the TL16C550C console at $FF38. Only +scenario=nitros9 addresses
  // it; boot.asm never does, so the seven boot runs are the machine they were.
  // AUDIO: the audio card at $FF40 on /FIRQ, in every run. boot.asm never
  // addresses it and reset leaves it silent with no interrupt enabled, so
  // the seven boot runs see an idle slot; NitrOS-9's firqtst is what drives it.
  machine3 #(.SIMMS(4), .SERIAL(1), .AUDIO(1), .STORAGE(1), .SDBLOCKS(SDB)) m (.*);

  // ---- what the card used to bring out on a port -------------------------
  // machine.v exported SPANBUSY, VBLANK, WPTR and VMODE because it had to
  // assemble VSTAT's '244 itself. video3_card.v has the '244 on the card, so
  // these are read where they live. VMODE is not read from the card at all:
  // the bench sets `mode` before each capture, which makes the geometry an
  // independent statement rather than the card's own opinion of it.
  wire SPANBUSY = m.card.SPANBUSY;
  wire VBLANK   = m.card.VBLANK;
  wire HBLANK   = m.card.HBLANK;

  // machine.v computed this; plan.md §4's VRAM window is a plain physical
  // cycle with A19 = 1 and A20 = 0, outside the I/O page.
  wire vram_read = rw & n_iopage_bp & ~pa[20] & pa[19];

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
  // ⭐ AND THE SEVEN THE CARD REPORTS ITSELF, which no single part of it can
  // see (video3_card.v). machine.v's card had one of these; this one has
  // seven, so they are counted rather than latched.
  int n_fba = 0, n_dbus = 0, n_luta = 0, n_idbf = 0, n_idbz = 0, n_lane = 0, n_rank = 0;
  always @(posedge CLK25) begin
    if (bus_conflict)      saw_bus_conflict = 1;
    if (pa_conflict)       saw_pa_conflict  = 1;
    if (n_reset) begin
      if (FBA_FIGHT)  n_fba++;
      if (DBUS_FIGHT) n_dbus++;
      if (LUTA_FIGHT) n_luta++;
      if (IDB_FIGHT)  n_idbf++;
      if (IDB_FLOAT)  n_idbz++;
      if (LANE_FLOAT) n_lane++;
      if (RANK_FIGHT) n_rank++;
    end
  end

  // How much of the run the card spent holding the CPU. graphics.md 7.4's
  // /WAIT is a backstop boot.asm is written not to need - it polls VSTAT - so
  // a nonzero count here means the polling rule is not sufficient.
  int wait_dots = 0;
  always @(posedge CLK25) if (wait_asserted) wait_dots++;
  // ... and how much of it was a VDATA access waiting, which the window's
  // decode cannot produce: the cycle is in the I/O page.
  int vdata_wait_dots = 0;
  always @(posedge CLK25) if (wait_asserted && !n_iosel && pa[7:0] == 8'h6C) vdata_wait_dots++;

  // ---- graphics.md 19 item 1: what a store actually costs ------------------
  /* ⚠ WHAT THIS CAN AND CANNOT ANSWER, STATED FIRST BECAUSE THE GAP IS THE
   * POINT. Item 1 asks for NATIVE-MODE 6309 cycle counts for STA ,X+ / STB ,X+.
   * The core in this socket is Greg Miller's mc6809e (cpu/sim/mc6809) - it IS
   * cycle-accurate, and it is a 6809. So what this measures is the
   * EMULATION-MODE cost on the part the whole design is simulated against,
   * which is the baseline 7.3's "~5 core cycles per store, native mode" claims
   * to improve on. It does not settle native mode, and no file in this
   * repository can: the Hitachi datasheet documents emulation mode only, and
   * A09 is not installed here, so boot.asm cannot be rebuilt with a tight store
   * loop to count one directly.
   *
   * The MINIMUM is the statistic worth having. Most of boot.asm's VRAM writes
   * poll VSTAT first (7.4's rule), so a mean would describe that polling loop
   * rather than the store; the minimum is the closest this core comes to
   * back-to-back stores, which section 10's store-then-load pairs do with no
   * poll between them. */
  int e_idx = 0, store_gap_min = 1000000, last_store_e = -1;
  /* boot.asm section 2a's two straight-line blocks, timed at the progress port.
   * 32 stores between $50 and $51, 64 between $51 and $52, with identical
   * bracketing either side - so (B - A) is exactly 32 STA ,X+ and every fixed
   * cost cancels. Captured in THIS block, not a second always @(negedge e),
   * because e_idx is incremented here and two blocks on the same edge race. */
  int st_e0 = -1, st_e1 = -1, st_e2 = -1;
  always @(negedge e) begin
    e_idx++;
    if (!rw && n_iopage_bp && !pa[20] && pa[19]) begin
      if (last_store_e >= 0 && (e_idx - last_store_e) < store_gap_min)
        store_gap_min = e_idx - last_store_e;
      last_store_e = e_idx;
    end
    if (!n_iosel && pa[7:0] == 8'h2F && !rw) begin
      if (cpu_dout == 8'h50) st_e0 = e_idx;
      if (cpu_dout == 8'h51) st_e1 = e_idx;
      if (cpu_dout == 8'h52) st_e2 = e_idx;
    end
  end

  // ---- graphics.md 19 item 6: the CPU's sub-slot phase ---------------------
  /* ⭐ THE HARNESS ITEM 6 ASKS FOR ALREADY EXISTS, AND WHAT WAS MISSING IS THIS
   * CLAIM. Item 6 closed its free-running half by arithmetic - a fetch slot is
   * 4 dots and an E period is 12 or 8 master clocks, and 12 mod 4 = 8 mod 4 = 0,
   * so E repeats on a slot boundary - then left the /WAIT half open "for want of
   * a testbench that instantiates clkdec and the video card together, which
   * nothing does yet". machine.v IS that testbench: mainboard's clkdec (u6) and
   * video_card sit side by side in it. The harness was never the gap.
   *
   * A stretch of N master clocks slides E against the fetch slot by N mod 4, so
   * if /WAIT released at an arbitrary dot the phase would scatter and 11's
   * 46.9 ns read margin - computed from a FIXED alignment - would be fiction.
   * It does not scatter: /WAIT falls with SPANBUSY, which is RETIRE-gated on
   * SPNTICK and therefore slot-aligned. The prediction is that E-fall lands on
   * exactly ONE dot phase for the whole run, waited cycles included.
   *
   * ⭐ AND IT IS RE-ASKED OF video3, whose slot is the same four dots: v3dot's
   * DP1..DP0 is the phase, SLOTTICK is DP1 & DP0, and v3host's /WAIT falls
   * with SPANBUSY exactly as vsup's did. The card changed; the prediction did
   * not, and neither did this claim.
   *
   * ⚠ Sampled at E-fall - the edge 3.1 says a 6809E write's data is guaranteed
   * on, and the edge the progress port above already trusts. */
  wire [1:0] v3_ph = {m.card.DP1, m.card.DP0};
  int   ph_at_e[4];
  int   ph_at_e_waited[4];
  bit   cyc_waited = 1'b0;
  logic e_d = 1'b0;
  initial for (int p = 0; p < 4; p++) begin ph_at_e[p] = 0; ph_at_e_waited[p] = 0; end
  // and the first eight cycles that land anywhere else, named - which is how
  // the excursion below was traced to one /WAIT release rather than to drift
  int ph_first = -1, ph_off = 0;
  always @(posedge CLK25) begin
    e_d <= e;
    if (wait_asserted) cyc_waited <= 1'b1;
    if (e_d && !e) begin                       // E-fall
      ph_at_e[v3_ph]++;
      if (ph_first < 0) ph_first = v3_ph;
      else if (v3_ph != ph_first && ph_off < 8) begin
        $display("      off-phase E-fall at dot %0d (E %0d): phase %0d, not %0d - LA=%04h %s waited=%b prog=%02h",
                 hb, e_cycles, v3_ph, ph_first, la, rw ? "R" : "W", cyc_waited, progress);
        ph_off++;
      end
      if (cyc_waited) ph_at_e_waited[v3_ph]++;
      cyc_waited <= 1'b0;
    end
  end

  // Work counters, so a stall says WHAT stalled rather than only that it did.
  int vram_writes = 0, vstat_reads = 0, reg_writes = 0, vram_reads = 0;
  int vdata_reads = 0, vdata_writes = 0;
  always @(negedge e) begin
    // +$15 VDATA, the VRAM port in the I/O page - graphics.md 19 item 47
    if (rw && !n_iosel && pa[7:0] == 8'h6C) vdata_reads++;
    if (!rw && !n_iosel && pa[7:0] == 8'h6C) vdata_writes++;
    if (!rw && n_iopage_bp && !pa[20] && pa[19]) vram_writes++;
    if (vram_read) vram_reads++;
    if (rw && !n_iosel && pa[7:0] == 8'h6D) vstat_reads++;
    if (!rw && !n_iosel && pa[7:5] == 3'b011) reg_writes++;
  end

  int e_cycles = 0;
  always @(negedge e) e_cycles++;

  /* ---- +scenario=: the runs that are not the boot ----------------------- *
   *
   *   main    four SIMMs, the whole ROM, every claim below   (the default)
   *   e1      no SIMM in any socket - the walk finds nothing, $E1
   *   s1..s3  one, two, three sockets populated - the walk reports each
   *   alias   four sockets, a 1M module in socket 0 - the walk rejects it and
   *           the machine boots on socket 1
   *   e2      a tile byte corrupted behind the ROM's back - it must report $E2
   *   nitros9 the NitrOS-9 ROM (software/nitros9/): boot.asm hands page 1 the
   *           machine, NitrOS-9 boots to a shell on the UART, and dir, mfree
   *           and `firqtst q` run - the last on the audio card's /FIRQ.
   *   reboot  the same ROM: boot, then `reboot`, which re-enters boot.asm at
   *           its reset vector; the POST runs again and NitrOS-9 comes back.
   *           ⚠ Both are minutes, not seconds - so neither is in the default list.
   *
   * ⛔ WHY THE LAST THREE EXIST. An error path that never runs is an error path
   * that does not work, and a claim that cannot fail is not a claim. Each one
   * is a run in which the right answer is a failure, asserted as such. */
  string scenario = "main";
  initial void'($value$plusargs("scenario=%s", scenario));

  // What each population must produce: the bitmap the walk reports, and the
  // socket everything else lands in. ram.md 5.2: socket n is dram[n << 22].
  function automatic int pop_bitmap();
    case (scenario)
      "e1": return 'h0;  "s1": return 'h1;  "s2": return 'h3;  "s3": return 'h7;
      "alias": return 'hE;
      default: return 'hF;
    endcase
  endfunction
  function automatic int pop_base();
    return (scenario == "alias") ? (1 << 22) : 0;
  endfunction
  function automatic int pop_count();
    int c = 0;
    for (int b = 0; b < 4; b++) if (pop_bitmap() & (1 << b)) c++;
    return c;
  endfunction

  /* ---- ram.md 6.4.1's walk, watched on the bus -------------------------- *
   * Every write to $FF90 before the stack is up is the walk pointing block 0
   * at the next socket. The order and the count are the claim that it visited
   * all four whatever it found. */
  logic [7:0] walk_hi [0:7];
  int         walk_n = 0;
  always @(negedge e)
    if (progress == 8'h00 && run && la == 16'hFF90 && !rw) begin
      if (walk_n < 8) walk_hi[walk_n] = cpu_dout;
      walk_n++;
    end

  /* ---- boot.asm stage 2, read independently of the ROM ------------------ *
   *
   * ⛔ STAGE 2 WAS SELF-VERIFIED. The ROM stores $A5 and $5A at logical $C000
   * and compares them back, and marker $02 said only that its own cmpa passed.
   * A store that lands at the wrong physical cell and a load that reads the
   * same wrong cell pass that compare - which is exactly what a 1M module in a
   * 4M socket does (ram.md 11 item 7), and what +scenario=alias shows.
   *
   * So this watches the bus and the array, not the ROM's verdict: every store
   * to $C000 in stage 2 must be in dram[$00C000] one E cycle later (block 6 is
   * SIMM 0 + 6 x 8 KB), and every load of $C000 must be a DRIVEN byte - not the
   * bus holding its last value, ram.md 6.4.1's trap - equal to that cell. */
  int         DRAM_C000;
  initial DRAM_C000 = 32'h00C000;
  int         st2_stores = 0, st2_store_bad = 0, st2_loads = 0, st2_load_bad = 0;
  logic [7:0] st2_seq [0:3];
  logic [7:0] st2_pend_v;
  bit         st2_pend = 0;
  always @(negedge e) begin
    if (st2_pend) begin
      if (m.mb.peek_dram(DRAM_C000) !== st2_pend_v) st2_store_bad++;
      st2_pend = 0;
    end
    if (progress == 8'h01 && la == 16'hC000) begin
      if (!rw) begin
        if (st2_stores < 4) st2_seq[st2_stores] = cpu_dout;
        st2_stores++;
        st2_pend = 1; st2_pend_v = cpu_dout;
      end else begin
        st2_loads++;
        if (!m.mb_din_valid || cpu_din !== m.mb.peek_dram(DRAM_C000)) st2_load_bad++;
      end
    end
  end

  /* ---- boot.asm section 10, read independently of the ROM --------------- *
   *
   * ⛔ SECTION 10 WAS SELF-VERIFIED TOO, at nine compare sites, each against an
   * expected-value expression in the ROM. A wrong expression writes $40 and
   * passes. So every byte the CPU LOADS from VRAM - through the window or
   * through +$15 VDATA - is recorded in order here, and compared against the
   * sequence section 10 is specified to read, stated a second time below from
   * the prose in boot.asm's header rather than from its code. */
  /* ⚠ ARMED AT $30, NOT AT RESET. Section 7a reads its copy back through
   * VDATA too - 128 loads that are its own claim's evidence and not section
   * 10's sequence - so the recorder starts when tile mode is reported, which
   * is the progress code immediately before section 10. */
  bit         vrd_arm = 0;
  always @(negedge e) if (progress == 8'h30) vrd_arm <= 1;
  logic [7:0] vrd_seq [0:4095];
  int         vrd_n = 0;
  always @(negedge e)
    if (vrd_arm && ((vram_read && n_iopage_bp) || (rw && !n_iosel && pa[7:0] == 8'h6C))) begin
      if (vrd_n < 4096) vrd_seq[vrd_n] = cpu_din;
      vrd_n++;
    end

  // (a) tile set 0..255; (b) 32 loads of the prefill at 2i+1; (c) 64 bytes,
  // stores at the even, prefill at the odd; (d) the byte after the span;
  // (e) the span; (f) 64 VDATA stores read through the window; (g) the same
  // through VDATA; (h) the byte after two spans; (i) the two spans.
  function automatic int vrd_want(input int k);
    if (k < 256) return k;                                          // (a)
    k -= 256;
    if (k < 32)  return ((2 * k + 1) ^ 'hA5) & 'hFF;                // (b)
    k -= 32;
    if (k < 64)  return ((k & 1) ? (k ^ 'hA5) : (k ^ 'h3C)) & 'hFF; // (c)
    k -= 64;
    if (k < 1)   return 'h5C;                                       // (d)
    k -= 1;
    if (k < 256) return 'hC7;                                       // (e)
    k -= 256;
    if (k < 64)  return (k ^ 'h96) & 'hFF;                          // (f)
    k -= 64;
    if (k < 64)  return (k ^ 'h96) & 'hFF;                          // (g)
    k -= 64;
    if (k < 1)   return 'h5C;                                       // (h)
    k -= 1;
    if (k < 512) return 'hE4;                                       // (i)
    return -1;
  endfunction
  localparam int VRD_TOTAL = 256 + 32 + 64 + 1 + 256 + 64 + 64 + 1 + 512;

  /* And what VRAM HOLDS, which the loads alone cannot say: a store that went to
   * the wrong byte and a load that followed it there agree with each other.
   * Taken at the two instants section 10 writes CTRL = $A8 to start a span -
   * (d) and (h) - each of which is the last moment the passes before it are
   * still intact. ⚠ $A8, not $B0: plan.md §10 moved WMODE from CTRL b4..3 to
   * b5..4 and made b3..2 the MODE field, so "display on, tile, span-solid" is
   * a different byte on this card. */
  localparam int VSCR = 32'h64800;        // SCRPAGE 6, SCRLOW $4800
  int vsnap_n = 0, vsnap_bad [0:1];
  always @(negedge e)
    if (!rw && !n_iosel && pa[7:0] == 8'h60 && cpu_dout == 8'hA8 && vsnap_n < 2) begin
      int bad;
      bad = 0;
      for (int j = 0; j < 257; j++) begin
        logic [7:0] w;
        bit known;
        known = 1;
        // ⚠ No 8'hxx for "don't care": this simulator is two-state, X is 0.
        if (vsnap_n == 0) begin    // after (a)-(c) and (d)'s prefill
          w = (j == 256) ? 8'h5C : (j & 1) ? 8'(j ^ 'hA5) : 8'(j ^ 'h3C);
          known = (j < 64) || (j == 256);
        end else                   // after (e)-(g): VDATA stores over the span
          w = (j == 256) ? 8'h5C : (j < 64) ? 8'(j ^ 'h96) : 8'hC7;
        if (known && m.card.peek(VSCR + j) !== w) bad++;
      end
      vsnap_bad[vsnap_n] = bad;
      vsnap_n++;
    end



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
      $display("      hb %0d dots: %0d E, %0d /WAIT dots, BUSY=%b VBL=%b vstat=%02h LA=%04h prog=%02h",
               hb, e_cycles, wait_dots, SPANBUSY, VBLANK, m.card.vstat, la, progress);
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
      $display("      %6d  E| LA=%04h %s PA=%07h D=%02h  BUSY=%b WAIT=%b CB=%b",
               e_cycles, la, rw ? "R" : "W", pa[24:0],
               rw ? cpu_din : cpu_dout, SPANBUSY, wait_asserted, m.card.CBUSY);

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

  /* The asserted level of each sync, at the connector.
   *
   * ⛔ ON THIS CARD IT IS HIGH IN BOTH FAMILIES, and that is a finding rather
   * than a convention. plan.md §2.1 and §11 both say graphics.md §6.2.1's
   * "VSYNC polarity a function of VMODE[0]" transfers verbatim and is
   * REQUIRED - "it is how the monitor identifies the format". It is not built:
   * v3dot.cpld.ts's VSYNC term carries the comment "what differs between them
   * is the POLARITY, and that is not this term's business", and no other cell
   * on the card, and nothing in video3_card.v, applies the XOR. The scene-6
   * claim below states it so the gap is a failing claim the day it is closed,
   * not a silent assumption here. */
  localparam bit HS_ON = 1'b1;
  localparam bit VS_ON = 1'b1;

  /* ⭐ AND THE PICTURE IS ~BLANK TWO DOTS LATE. plan.md §9.2 puts the output
   * '273s' /MR (OMR) two registers behind BLANK, so the connector's BLANK
   * opens two dots before the first pixel appears in RGB and closes two dots
   * before the last one. Sampling on BLANK itself captures two black dots and
   * loses the last two of every line. The delay is a property of the card's
   * pixel pipeline, so it is applied here and ASSERTED against the card's own
   * OMR - which is how the capture stays a function of the four signals that
   * leave the card. */
  logic [1:0] blank_sr = 2'b11;
  int omr_mismatch = 0;
  always @(posedge CLK25) begin
    blank_sr <= {blank_sr[0], BLANK};
    if (n_reset && (m.card.OMR !== ~blank_sr[1])) omr_mismatch++;
  end
  wire pixon = ~blank_sr[1];

  bit shot_overflow;
  task automatic capture_frame(input int budget);
    int dots, x;
    bit prev_hs, prev_vs;
    shot_lines = 0; x = 0; dots = 0; shot_overflow = 0;
    for (int i = 0; i < MAXH; i++) linew[i] = 0;

    // Find the start of a frame: the leading edge of VSYNC.
    prev_vs = (VSYNC == VS_ON);
    forever begin
      @(posedge CLK25); #0;
      dots++;
      if (dots > budget) begin
        $display("FAIL  screenshot: no VSYNC edge in %0d dots", budget);
        fails++; claims++; return;
      end
      if ((VSYNC == VS_ON) && !prev_vs) break;
      prev_vs = (VSYNC == VS_ON);
    end

    // From here to the next VSYNC leading edge is one frame.
    prev_hs = (HSYNC == HS_ON);
    prev_vs = 1;
    dots = 0;
    forever begin
      @(posedge CLK25); #0;
      dots++;
      if (dots > budget) begin
        $display("FAIL  screenshot: frame did not end in %0d dots", budget);
        fails++; claims++; return;
      end

      if (pixon) begin
        if (shot_lines < MAXH && x < MAXW) shot[shot_lines][x] = RGB;
        else shot_overflow = 1;
        x++;
      end

      // A line ends at HSYNC's leading edge. A line with no active dots in it
      // is a blanked line and is not part of the picture.
      if ((HSYNC == HS_ON) && !prev_hs) begin
        if (x > 0) begin
          if (shot_lines < MAXH) linew[shot_lines] = x;
          shot_lines++;
        end
        x = 0;
      end
      prev_hs = (HSYNC == HS_ON);

      if ((VSYNC == VS_ON) && !prev_vs) break;
      prev_vs = (VSYNC == VS_ON);
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

  // ---- claims shared by the boot and the population runs -----------------
  task automatic walk_claims();
    bit order;
    order = (walk_n >= 4);
    for (int k = 0; k < 4 && k < walk_n; k++)
      if (walk_hi[k] !== 8'((k + 1) * 2)) order = 0;
    ok(order,
       $sformatf("⭐ ram.md 6.4.1's walk visits all four sockets in order - block 0 -> $02, $04, $06, $08 (%0d writes)",
                 walk_n));
    // ... and then the fix-up points block 0 at the socket it chose, or, with
    // nothing found, nothing more is written.
    if (pop_bitmap() == 0)
      ok(walk_n == 4, $sformatf("and with nothing found, no socket is chosen (%0d writes)", walk_n));
    else
      ok(walk_n == 5 && walk_hi[4] === (pop_base() == 0 ? 8'h02 : 8'h04),
         $sformatf("and block 0 is then pointed at the lowest socket that passed (%0d writes, last %02h)",
                   walk_n, walk_n > 4 ? walk_hi[4] : 8'h00));
  endtask

  task automatic boot_claims();
    int want_hi, bad;
    want_hi = pop_base() == 0 ? 8'h02 : 8'h04;
    // The descriptor, at the base of the lowest socket that passed.
    ok(m.mb.peek_dram(pop_base()) === 8'(pop_bitmap())
       && {m.mb.peek_dram(pop_base() + 1), m.mb.peek_dram(pop_base() + 2)} === 16'(pop_count() * 512),
       $sformatf("⭐ THE ROM REPORTS A SIZE: the descriptor at socket %0d's base says bitmap %02h and %0d blocks (want %02h and %0d)",
                 pop_base() >> 22, m.mb.peek_dram(pop_base()),
                 {m.mb.peek_dram(pop_base() + 1), m.mb.peek_dram(pop_base() + 2)},
                 pop_bitmap(), pop_count() * 512));
    // Every one of the sixteen map entries, not three of them.
    bad = 0;
    for (int t = 0; t < 2; t++)
      for (int b = 0; b < 8; b++) begin
        logic [7:0] lo, hi;
        case (b)
          1: begin lo = 8'h40; hi = 8'h00; end
          2: begin lo = 8'h41; hi = 8'h00; end
          7: begin lo = 8'h00; hi = 8'h01; end
          default: begin
            lo = (t == 1 && b == 5) ? 8'h07 : 8'(b);
            hi = 8'(want_hi);
          end
        endcase
        if (m.mb.map_lo_at(t * 8 + b) !== lo || m.mb.map_hi_at(t * 8 + b) !== hi) bad++;
      end
    ok(bad == 0,
       $sformatf("all sixteen map entries are what boot.asm means - both tasks, SIMM pages in socket %0d (%0d wrong)",
                 pop_base() >> 22, bad));
  endtask

  task automatic stage2_claims();
    ok(st2_stores == 2 && st2_seq[0] === 8'hA5 && st2_seq[1] === 8'h5A && st2_store_bad == 0,
       $sformatf("⭐ and the stores are in the SIMM, read without the ROM: $A5 then $5A reached dram[$%06h], each within one E cycle (%0d stores, %0d not in the cell)",
                 DRAM_C000, st2_stores, st2_store_bad));
    ok(st2_loads == 2 && st2_load_bad == 0,
       $sformatf("⭐ and each load was a DRIVEN byte equal to that cell - not the bus holding its last value (%0d loads, %0d wrong or undriven)",
                 st2_loads, st2_load_bad));
  endtask

  task automatic task_claims();
    ok(m.mb.peek_dram(pop_base() + 32'h00A000) === 8'hC3
       && m.mb.peek_dram(pop_base() + 32'h00E000) === 8'h3C,
       $sformatf("⭐ ONE LOGICAL ADDRESS, TWO PHYSICAL BYTES: $A000 under TASK 0 is SIMM page 5 (holds %02h, want C3) and under TASK 1 is page 7 (holds %02h, want 3C)",
                 m.mb.peek_dram(pop_base() + 32'h00A000), m.mb.peek_dram(pop_base() + 32'h00E000)));
  endtask

  // ---- +scenario=nitros9: the console ------------------------------------
  // Every character the UART finishes sending, NULs dropped (sc16550 pads the
  // echo of a command line with them - software/nitros9/README.md). Printed as
  // it arrives, so the log is the console.
  string console = "";
  always @(posedge CLK25)
    if (m.ser_tx_strobe && m.ser_tx_byte != 8'h00 && m.ser_tx_byte != 8'h0D) begin
      console = {console, $sformatf("%c", m.ser_tx_byte)};
      if (scenario == "nitros9" || scenario == "reboot") $write("%c", m.ser_tx_byte);
    end

  bit saw_8004 = 0;
  always @(negedge e) if (run && rw && la == 16'h8004) saw_8004 = 1;
  int vstat_acks = 0, ser_irqs = 0;
  bit ser_intr_d = 0;
  always @(negedge e) if (!n_iosel && pa[7:0] == 8'h6D && !rw) vstat_acks++;
  always @(posedge CLK25) begin
    if (m.ser_intr && !ser_intr_d) ser_irqs++;
    ser_intr_d <= m.ser_intr;
  end

  function automatic int find_text(input string needle, input int from);
    for (int i = from; i + needle.len() <= console.len(); i++)
      if (console.substr(i, i + needle.len() - 1) == needle) return i;
    return -1;
  endfunction

  task automatic type_text(input string typed);
    for (int i = 0; i < typed.len(); i++) m.ser.rx_push(typed[i]);
  endtask

  // The decimal number printed right after `needle`, or -1.
  function automatic int number_after(input string needle, input int from);
    int at, v;
    at = find_text(needle, from);
    if (at < 0) return -1;
    v = 0;
    for (int i = at + needle.len(); i < console.len() && console[i] >= "0" && console[i] <= "9"; i++)
      v = v * 10 + (console[i] - "0");
    return v;
  endfunction

  int firq_rises = 0;
  bit firq_d = 0;
  always @(posedge CLK25) begin
    if (firq_asserted && !firq_d) firq_rises++;
    firq_d <= firq_asserted;
  end
  bit saw_progress_error = 0;
  always @(negedge e)
    if (!n_iosel && pa[7:0] == 8'h2F && !rw && cpu_dout[7:4] == 4'hE) saw_progress_error = 1;

  // Wait for `needle` to appear in the console at or after `from`, bounded in
  // E cycles (2,097,917 a second). Returns where it was found, or -1 after a
  // FAIL line.
  int e_at_found;
  task automatic wait_text(input string needle, input int from, input int budget_e,
                           input string what, output int at);
    int start;
    start = e_cycles;
    at = -1;
    while (at < 0) begin
      repeat (2000) @(negedge e);
      at = find_text(needle, from);
      if (at < 0 && e_cycles - start > budget_e) begin
        $display("");
        ok(1'b0, $sformatf("%s: no \"%s\" on the console within %0d E cycles", what, needle, budget_e));
        return;
      end
    end
    e_at_found = e_cycles;
    $display("");
    ok(1'b1, $sformatf("%s (at %.2f s of machine)", what, real'(e_cycles) / 2097917.0));
  endtask

  task automatic run_nitros9();
    int at, prompt1;
    localparam int SEC = 2097917;
    $display("NITROS9. software/nitros9/: boot.asm, the loader, krn, and a shell on the UART");
    $display("");
    /* ⚠ THE BUDGETS GREW ON 2026-09-22, and for a reason and not a hunch:
     * this scenario used to read OS9Boot out of ROM PAGES through the map, and
     * now it reads 26,633 bytes off an SD card over BIT-BANGED SPI - eight
     * shifts a byte in 6809 code, and the whole boot ROM's §10a dialog drawn
     * with the toolbox before any of it. ⛔ CLAUDE.md's rule still applies:
     * "budget more time" is how a HANG gets misdiagnosed, so these are bounds
     * that fail loudly, not waits that grow until something appears. */
    wait_text("RK", 0, 4 * SEC, "boot.asm handed page 1 the machine, and the loader entered krn (R, K)", at);
    ok(saw_8004, "the CPU fetched $8004 - boot.asm's handoff, not a crash that printed");
    if (at < 0) return;
    /* ⛔ `rbsd SD0` JOINED THIS LIST ON 2026-09-20 and this line did not, so
     * the claim could not match: the storage card's driver and descriptor went
     * into the bootfile that day (sdcard.md §9.4), and krn prints them between
     * `R0` and `SCF`. software/nitros9/run-emu.sh's own module-list claim was
     * updated with them; this one was missed, which is what a scenario nobody
     * ran that week looks like. ⚠ The pattern is the WHOLE order, deliberately
     * - a module that moves or vanishes has to fail here. */
    /* ⛔ AND `rbromdisk DD R0` LEFT IT ON 2026-09-22, with the ROM disk. The
     * card is the system disk now and answers to BOTH names - one descriptor
     * source assembled twice - so `rbsd DD SD0` is the whole of it. */
    wait_text("rbsd DD SD0 SCF sc16550 Term", at, 6 * SEC,
              "krn's Boot read OS9Boot, and rbsd drives the one disk under both names", at);
    if (at < 0) return;
    /* ⭐ AND IT CAME OFF THE CARD, over SPI, before there was an OS to do it
     * with: boot_sd.asm prints `s` between krn's `tb` and boot_common's `0`,
     * where `n` would mean no system disk. ⛔ There is nothing else to boot,
     * so this is not a preference - it is the only path there is. */
    ok(find_text("tbs0", 0) >= 0 && find_text("tbn", 0) < 0,
       "⭐ OS9Boot came off the SD CARD - boot_sd's own `s`, and not its `n`");
    wait_text("\narm6309\n", at, 4 * SEC, "SysGo printed the banner, naming this machine", at);
    if (at < 0) return;
    /* ⚠ AND THE SHELL IS FORKED FROM THE CARD, which is the slowest single
     * step in the boot: SysGo opens /DD/CMDS/shell over SPI. */
    wait_text("{Term|02}/DD:", at, 10 * SEC, "the shell prompted on /Term", prompt1);
    if (prompt1 < 0) return;
    begin
      string typed;
      typed = "dir\r";
      for (int i = 0; i < typed.len(); i++) m.ser.rx_push(typed[i]);
    end
    wait_text("OS9Boot         CMDS            DATA            MODULES         SYS", prompt1, 3 * SEC,
              "dir, typed at the UART, lists the CARD's root - /DD is the card", at);
    if (at < 0) return;
    wait_text("{Term|02}/DD:", at, 4 * SEC, "and the shell prompted again", at);
    if (at < 0) return;
    begin
      string typed;
      typed = "mfree\r";
      for (int i = 0; i < typed.len(); i++) m.ser.rx_push(typed[i]);
    end
    wait_text("Total:  3F5  8104k", at, 3 * SEC,
              "mfree reports 8 MB: the loader sized RAM from boot.asm's own SIMM descriptor, and NitrOS-9's 16-bit blocks map past the first 2 MB", at);
    if (at < 0) return;
    wait_text("{Term|02}/DD:", at, 5 * SEC, "and the shell prompted a third time", at);
    if (at < 0) return;
    // ⭐ /FIRQ, which no bench on this machine had raised: firqtst's driver runs
    // the audio card's tempo timer at 50 Hz and counts through krn's FIRQ stub.
    type_text("load /dd/modules/firqtst\r");   // ⭐ off the card, through /DD
    wait_text("{Term|02}/DD:", at + 1, 8 * SEC, "load put the FIRQ test driver in memory", at);
    if (at < 0) return;
    type_text("firqtst q\r");
    wait_text("registers intact", at, 4 * SEC,
              "firqtst q: FIRQs taken in the kernel and in a user busy loop, every register the stub saves intact", at);
    begin
      int sys_n, usr_n;
      sys_n = number_after("FIRQs in 20 ticks: ", 0);
      usr_n = number_after("FIRQs in user state: ", 0);
      ok(sys_n >= 11 && sys_n <= 16,
         $sformatf("the audio card's 50 Hz timer over 20 VBL ticks (0.285 s): %0d FIRQs, 11-16 expected - two crystals, one count", sys_n));
      ok(usr_n >= 15 && usr_n <= 60,
         $sformatf("and %0d in user state, in the user's map", usr_n));
      ok(firq_rises >= sys_n + usr_n,
         $sformatf("/FIRQ rose %0d times at the CPU - at least the %0d the driver counted", firq_rises, sys_n + usr_n));
    end
    if (at < 0) return;
    ok(vstat_acks >= 70,
       $sformatf("the VBL tick was acknowledged %0d times - NitrOS-9's clock on the video card's /IRQ", vstat_acks));
    ok(ser_irqs >= 10,
       $sformatf("the UART's INTR rose %0d times on the shared /IRQ - sc16550 is interrupt-driven", ser_irqs));
    ok(!saw_bus_conflict, "no cycle had two drivers on D0-D7, the UART's and the audio card's reads included");
    ok(!saw_pa_conflict,  "no cycle had two drivers on physical A20-A13");
  endtask

  // +scenario=reboot: F$Debug's reboot, through the boot ROM and back.
  task automatic run_reboot();
    int at, writes0;
    localparam int SEC = 2097917;
    $display("REBOOT. software/nitros9/: boot, `reboot`, the POST again, and NitrOS-9 again");
    $display("");
    /* ⚠ SIX SECONDS, NOT FOUR, SINCE 2026-09-20. This is the only wait in
     * either NitrOS-9 scenario that spans the POST *and* the whole boot from
     * one origin, so it is the one the bootfile's growth eats first: `rbsd`
     * and `SD0` went in that day, and the banner was printing at 4 s with the
     * prompt still to come. run_nitros9 allows 2 + 3 for the same journey;
     * this now allows 6 for the POST plus it. */
    /* ⚠ 20, NOT 6, SINCE 2026-09-22: the POST plus a whole boot off the CARD
     * over bit-banged SPI (run_nitros9's note says the rest). */
    wait_text("{Term|02}/DD:", 0, 20 * SEC, "NitrOS-9 booted to the shell", at);
    if (at < 0) return;
    /* ⭐ $61 OR $63, NOT $40 (2026-09-20; $62 became $61 on 2026-09-22). boot.asm's last stage is
     * §10a's boot dialog, so the code it leaves behind is the dialog's.
     * ⚠ WHICH of the two is a property of the ROM this scenario was handed,
     * and the bench cannot see it: the toolbox is ROM page 64 and
     * recipes/arm6309.mak only assembles it under -DV3=1, which
     * run-machine.sh does NOT pass for `nitros9`/`reboot`. So $63 - "no
     * toolbox, dialog skipped" - is what a default build gives, and $61 -
     * "Disk found", because sd_cd is 1 since 2026-09-22 and the card in the
     * socket IS the system disk - is what a V3=1 one would. Both say
     * the POST reached §10a; neither is $40 any more, and an error code still
     * fails. */
    ok((progress == 8'h61 || progress == 8'h63) && !saw_progress_error,
       $sformatf("boot.asm ran every stage the first time, ending in §10a's dialog (last progress $%02h)", progress));
    writes0 = progress_writes;
    type_text("reboot\r");
    wait_text("RK", at, 4 * SEC,
              "reboot: the kernel quieted the cards and re-entered the boot ROM, and its handoff reached the loader again", at);
    if (at < 0) return;
    ok(progress_writes - writes0 >= 17 && (progress == 8'h61 || progress == 8'h63),
       $sformatf("boot.asm's POST ran again from its reset vector: %0d more progress writes, ending at $%02h - with the map already live, which it rewrites first",
                 progress_writes - writes0, progress));
    ok(!saw_progress_error, "and it reported no error ($E0-$EF) - SIMM walk, TASK 1, palette, spans, lists, tiles and VRAM read-back all passed again");
    wait_text("\narm6309\n", at, 6 * SEC, "SysGo printed the banner a second time", at);
    if (at < 0) return;
    wait_text("{Term|02}/DD:", at, 10 * SEC, "and the shell prompted", at);
    if (at < 0) return;
    type_text("dir\r");
    wait_text("OS9Boot         CMDS            DATA            MODULES         SYS", at, 3 * SEC,
              "dir runs on the rebooted system", at);
    ok(!saw_bus_conflict, "no cycle had two drivers on D0-D7");
    ok(!saw_pa_conflict,  "no cycle had two drivers on physical A20-A13");
  endtask

  /* --------------------------------------------------------------------- *
   * +scenario=disk / =nodisk: ⭐ THE BOOT DIALOG IS ON THE SCREEN.
   *
   * software/desk/docs/boot-and-desktop.md §1. boot.asm §10a draws a Haiku window with the
   * toolbox's `disk` icon in it, in one of three states, and writes $60, $61
   * or $62 to say which. ⛔ A PROGRESS CODE IS NOT EVIDENCE THAT ANYTHING WAS
   * DRAWN - it is evidence that a STA ran - so what is asserted here is the
   * picture: the tab, the frame, the content panel, the desktop around it and
   * the icon's own pixels, read off RGB at the connector like every other
   * frame this bench checks.
   *
   * ⚠ THESE TWO NEED THE WHOLE 1 MB ROM, because the toolbox is ROM page 64
   * and `npm run rom` builds page 0. They are asked for by name for the same
   * reason `nitros9` is - run-machine.sh builds it from $NITROS9DIR - and
   * they are not in the default SCENARIOS list.
   *
   * The two differ in ONE bit: machine3.v's sd_cd, which is SDSTAT b1.
   * --------------------------------------------------------------------- */
  // The Haiku palette, as RGB565 at the connector. software/nitros9/tools/
  // mktbox.py's UI list and its 5 x 8 x 5 colour cube are where these come
  // from; that file is also what wrote them into the ROM the machine loaded,
  // so naming them here is the second, independent statement of the pair.
  localparam logic [15:0] H_BLACK  = 16'h0000;   // 0  and every ramp's ink
  localparam logic [15:0] H_WHITE  = 16'hFFFF;   // 1  the question mark's paper
  localparam logic [15:0] H_PANEL  = 16'hDEDB;   // 2
  localparam logic [15:0] H_FRAME  = 16'h9CD3;   // 3
  localparam logic [15:0] H_SHADOW = 16'h738E;   // 4
  localparam logic [15:0] H_DESK   = 16'h3333;   // 6
  localparam logic [15:0] H_PALE   = 16'hFF30;   // 14
  // and four of the icon's own, from the cube: its face, its shaded right
  // edge, its outline and the label band across it
  localparam logic [15:0] I_FACE   = 16'hBDB7;   // 204
  localparam logic [15:0] I_EDGE   = 16'h8370;   // 153
  localparam logic [15:0] I_LINE   = 16'h4128;   // 102
  localparam logic [15:0] I_BAND   = 16'h4248;   // 107

  // boot.asm §10a's own equates. A claim that restated them loosely would be
  // a claim about nothing; these are the numbers the ROM was assembled with.
  // ⭐ 640 x 480, VMODE 11 - the DESKTOP's mode, not the POST's 640 x 200.
  // boot.asm's §10a centres the dialog in DLGSCRH, so these follow from the
  // window's own size rather than being two more numbers to keep in step.
  localparam int DLGSCRH = 480;
  localparam int DWINW = 288, DWINH = 96;
  localparam int DWINX = (640 - DWINW) / 2, DWINY = (DLGSCRH - DWINH) / 2;
  localparam int DCONX = DWINX + 5,  DCONY = DWINY + 5;
  localparam int DCONW = DWINW - 10, DCONH = DWINH - 10;
  localparam int DICONX = DWINX + 20, DICONY = DWINY + 28, DICONS = 32;

  // ⭐ VMODE 11 IS PROGRESSIVE: picture row y IS capture line y.  The rest of
  // the POST paints in VMODE 00, where every picture row is scanned twice and
  // row y is line 2y (check_picture() states that doubling) - the dialog is
  // the one §10a section that is not in that mode, because it has to match
  // the desktop NitrOS-9 brings up seconds later.
  function automatic logic [15:0] px(input int x, input int y);
    px = (y < shot_lines && x < MAXW) ? shot[y][x] : 16'hDEAD;
  endfunction

  task automatic dialog_picture(input string state);
    int nface, nwhite, nink, dirty;
    capture_frame(1200000);
    ok(!shot_overflow, "the capture fits");
    ok(shot_w_min == 640 && shot_w_max == 640 && shot_lines == DLGSCRH,
       $sformatf("⭐ VMODE 11, 640 x %0d progressive - the DESKTOP's mode (%0d..%0d x %0d)",
                 DLGSCRH, shot_w_min, shot_w_max, shot_lines));
    if (shot_lines == 0) return;
    if (state == "nodisk") write_ppm("screenshot-dialog-nodisk.ppm");
    else                   write_ppm("screenshot-dialog.ppm");

    // ---- the screen was cleared to the desktop's blue --------------------
    // Four corners of the 640 x 480 picture, well outside the window: if the
    // toolbox's Rect had painted the window's coordinates and not the
    // screen's, §4's test pattern would still be here.
    dirty = 0;
    for (int x = 0; x < 640; x = x + 7)
      for (int y = 0; y < 200; y = y + 5)
        if ((x < DWINX - 4 || x > DWINX + DWINW + 3 ||
             y < DWINY - 24 || y > DWINY + DWINH + 3) && px(x, y) !== H_DESK)
          dirty++;
    ok(dirty == 0,
       $sformatf("⭐ the screen is cleared to Haiku's desktop blue everywhere outside the dialog (%0d sampled pixels are not)", dirty));

    // ---- the window: tbox.asm's TWin, layer by layer ---------------------
    // Its own drawing order is shadow, panel, light, frame - so these four
    // pixels are four different Fill calls, and one of them landing in the
    // wrong place moves exactly one of them.
    ok(px(DWINX, DWINY) === H_SHADOW,
       "the frame's outer rectangle is C.Shadow at its top-left corner");
    ok(px(DWINX + 2, DWINY + 2) === H_PANEL,
       "one pixel in, the frame is C.Panel");
    ok(px(DWINX + 4, DWINY + 4) === H_FRAME,
       "and four in, the content well's C.Frame border");
    ok(px(DCONX, DCONY) === H_PANEL &&
       px(DCONX + DCONW - 1, DCONY + DCONH - 1) === H_PANEL,
       "the content area (X+5, Y+5, W-10, H-10) is the panel the dialog filled");
    ok(px(DWINX - 1, DWINY) === H_DESK && px(DWINX + DWINW, DWINY) === H_DESK,
       "and the frame stops where it should: the desktop is still there either side of it");

    // ---- the tab, which sits ABOVE the frame -----------------------------
    // 19 pixels of it, as wide as its title needs. TWin fills the whole tab
    // C.Shadow, insets it, runs the eight-step gradient down it and then puts
    // C.Pale on its first row.
    ok(px(DWINX, DWINY - 19) === H_SHADOW,
       "the Haiku tab is 19 pixels above the frame and starts with its shadow");
    ok(px(DWINX + 1, DWINY - 18) === H_PALE,
       "and the row under that is C.Pale - the tab's highlight");
    ok(px(DWINX + 1, DWINY - 20) === H_DESK,
       "and nothing is drawn above the tab");

    // ---- the `disk` icon -------------------------------------------------
    // ⭐ EXACT PIXELS, not "something is there". These six are the icon's own
    // colours at six places in its 32 x 32 blob - the face, the shaded right
    // edge, the outline, the label band - and two KEY pixels at corners the
    // shape does not reach, which have to show the panel through. The blob is
    // software/tools/show.py's Icon.blob() as mktbox.py quantised it;
    // this bench renders none of that, it states where the colours land.
    ok(px(DICONX +  4, DICONY + 16) === I_FACE,
       "⭐ the `disk` icon is drawn: its face at (4, 16) of the blob");
    ok(px(DICONX + 28, DICONY + 16) === I_EDGE,
       "   ... its shaded right edge at (28, 16)");
    ok(px(DICONX + 12, DICONY +  5) === I_LINE,
       "   ... its outline at (12, 5)");
    ok(px(DICONX +  8, DICONY + 17) === I_BAND,
       "   ... and the label band across it at (8, 17)");
    ok(px(DICONX, DICONY) === H_PANEL && px(DICONX + 16, DICONY + 30) === H_PANEL,
       "   ... and its KEY pixels are transparent: the panel shows through at two corners the shape does not reach");
    // and it is where it was PLACED: nothing of it outside the 32 x 32 box
    dirty = 0;
    for (int x = DICONX - 3; x < DICONX + DICONS + 3; x++)
      for (int y = DICONY - 3; y < DICONY + DICONS + 3; y++)
        if ((x < DICONX || x >= DICONX + DICONS ||
             y < DICONY || y >= DICONY + DICONS) && px(x, y) !== H_PANEL)
          dirty++;
    ok(dirty == 0,
       $sformatf("   ... and the band around the icon's box is untouched panel (%0d pixels are not)", dirty));

    // ---- the line of text beside it --------------------------------------
    // The panel ramp's ink is index 34, which mktbox.py makes black. A row of
    // anti-aliased text has to put some of it down.
    nink = 0;
    for (int x = DWINX + 56; x < DWINX + DWINW - 16; x++)
      for (int y = DWINY + 36; y < DWINY + 53; y++)
        if (px(x, y) === H_BLACK) nink++;
    ok(nink > 40,
       $sformatf("⭐ the state's line of text is drawn beside the icon: %0d pixels of the panel ramp's ink", nink));

    // ---- and what tells the two states apart -----------------------------
    // The question mark is TextC in the WHITE ramp with F.Opaq, so it brings
    // its own paper: a small white box with black ink in it, centred on the
    // icon. In the `found` state there is no such thing anywhere on the disk.
    nwhite = 0; nink = 0;
    for (int x = DICONX; x < DICONX + DICONS; x++)
      for (int y = DICONY + 8; y < DICONY + 25; y++) begin
        if (px(x, y) === H_WHITE) nwhite++;
        if (px(x, y) === H_BLACK) nink++;
      end
    if (state == "nodisk") begin
      ok(nwhite > 30 && nink > 8,
         $sformatf("⭐ NO DISK: the Macintosh's question mark is on the icon - %0d pixels of its opaque white paper and %0d of ink", nwhite, nink));
    end else begin
      nface = 0;
      for (int x = DICONX + 11; x < DICONX + 20; x++)
        for (int y = DICONY + 8; y < DICONY + 25; y++)
          if (px(x, y) === I_FACE) nface++;
      ok(nwhite == 0 && nface > 80,
         $sformatf("⭐ FOUND: no question mark - the middle of the disk is its own face (%0d white pixels, %0d face)", nwhite, nface));
    end
  endtask

  task automatic run_dialog(input bit present);
    localparam int SEC = 2097917;
    $display("");
    $display("%s. boot-and-desktop.md 1 - the boot dialog, with SDSTAT b1 = %0d",
             present ? "DISK" : "NODISK", present);
    $display("");
    // The whole POST first: the dialog is the LAST thing §10a draws, after
    // the VRAM read-back, so everything before it has to have passed.
    /* ⚠ THE BUDGETS ARE SECONDS OF MACHINE AND MINUTES OF SIMULATION - about
     * five of the second per one of the first - so they are set from what the
     * POST costs (~0.5 s: four VMODEs, the sprite and tile mode each stand
     * still for four frames) and not from "generously". A budget that is
     * merely large turns a defect into an hour of waiting, which is the
     * failure mode CLAUDE.md calls worse than a failure. */
    wait_progress(8'h40, 2 * SEC, "the POST ran to the VRAM read-back");
    if (timed_out) return;
    ok(!saw_progress_error, "and reported no error on the way");
    // ⛔ AND THE TOOLBOX HAS TO BE THERE. $63 is boot.asm's "no toolbox on
    // page 64, dialog skipped", which is what six of this bench's seven boot
    // scenarios get - and it would make every claim below vacuous.
    wait_progress(8'h60, SEC,
                  "⭐ the dialog is up, state `looking for a disk` - so ROM page 64 answered \"TB\"");
    if (timed_out) return;
    if (present) begin
      wait_progress(8'h61, SEC / 2,
                    "⭐ SDSTAT says a card is in the socket, and the dialog says `Disk found`");
      if (timed_out) return;
      dialog_picture("disk");
    end else begin
      wait_progress(8'h62, SEC / 2,
                    "⭐ SDSTAT says the socket is empty, and the dialog goes to the question mark");
      if (timed_out) return;
      dialog_picture("nodisk");
    end
    ok(!saw_bus_conflict, "no cycle had two drivers on D0-D7, the card-detect read included");
    ok(!saw_pa_conflict,  "no cycle had two drivers on physical A20-A13");
  endtask

  // ---- the scenarios that must fail, asserted as failures ----------------
  task automatic run_scenario();
    if (scenario == "e1") begin
      $display("");
      $display("E1. No SIMM in any socket - ram.md 6.4.1's walk finds nothing");
      $display("");
      wait_progress(8'hE1, 4000, "⭐ the walk reports $E1 - no socket answered");
      walk_claims();
      ok(st2_stores == 0 && progress_writes == 1,
         $sformatf("and nothing ran after it - no stack, no stage 2, one progress write (%0d stores to $C000, %0d writes)",
                   st2_stores, progress_writes));
    end else if (scenario == "s1" || scenario == "s2" || scenario == "s3"
                 || scenario == "alias") begin
      $display("");
      if (scenario == "alias")
        $display("ALIAS. Four sockets, a 1M x 8 module in socket 0 - ram.md 11 item 7");
      else
        $display("%s. %0d socket(s) populated - ram.md 6.4.1", scenario.toupper(), pop_count());
      $display("");
      wait_progress(8'h01, 2000, "the walk passes and the stack is up");
      walk_claims();
      boot_claims();
      wait_progress(8'h02, 4000, "stage 2 passes, in the socket the walk chose");
      stage2_claims();
      wait_progress(8'h07, 4000, "TASK 1's map is live");
      task_claims();
      if (scenario == "alias")
        ok(m.mb.peek_dram(32'h00C000) !== 8'h5A,
           $sformatf("⭐ and socket 0's aliasing module holds none of stage 2's bytes - the machine is not using it (dram[$00C000] = %02h)",
                     m.mb.peek_dram(32'h00C000)));
    end else if (scenario == "e2") begin
      $display("");
      $display("E2. A tile byte corrupted behind the ROM's back - boot.asm's vbad");
      $display("");
      wait_progress(8'h02, 4000, "stage 2");
      wait_progress(8'h03, 40000, "the palette");
      wait_progress(8'h04, 900000, "the pattern");
      wait_progress(8'h05, 200000, "the stripe");
      wait_progress(8'hFF, 4000, "VMODE 00");
      wait_progress(8'h10, 600000, "VMODE 10");
      wait_progress(8'h11, 600000, "VMODE 01");
      wait_progress(8'h12, 600000, "VMODE 11");
      wait_progress(8'h20, 900000, "the copy engine");
      wait_progress(8'h21, 900000, "the sprite");
      wait_progress(8'h30, 900000, "tile mode - the tile set is written");
      // settle waits four frames before section 10 reads anything
      m.card.poke(131072 + 17, 8'hEE);
      wait_progress(8'hE2, 900000, "⭐ section 10 reports $E2 - a byte read back wrong");
      ok(m.mb.peek_dram(32'h00C01A) === 8'd17,
         $sformatf("⭐ and vidx names the corrupted byte - tile 17 (holds %0d)",
                   m.mb.peek_dram(32'h00C01A)));
      ok(vrd_n == 18,
         $sformatf("after exactly 18 loads - the ROM stopped at the first wrong one (%0d)", vrd_n));
    end else if (scenario == "nitros9") begin
      run_nitros9();
    end else if (scenario == "reboot") begin
      run_reboot();
    end else if (scenario == "disk") begin
      run_dialog(1'b1);
    end else if (scenario == "nodisk") begin
      run_dialog(1'b0);
    end else
      ok(1'b0, $sformatf("+scenario=%s is not a scenario this bench has", scenario));
  endtask

  // ---- the run -------------------------------------------------------------
  int bad, first_bad_x, first_bad_y, i, shift;
  logic [15:0] got;
  logic [7:0]  want;
  string rom_path;

  initial begin
    rom_path = "../../../software/boot/build/boot.hex";
    // +scenario=nitros9 loads the whole 1 MB ROM, whose page 0 is boot.hex
    if (scenario == "nitros9" || scenario == "reboot") begin
      rom_path = "../../../software/nitros9/build/rom/arm6309_rom.hex";
      void'($value$plusargs("rom=%s", rom_path));
    end
    // ⭐ and so do `disk` and `nodisk` - but a V3=1 one, built beside it:
    // boot.asm §10a's toolbox is ROM page 64, which recipes/arm6309.mak only
    // assembles under that flag (run-machine.sh says the rest)
    if (scenario == "disk" || scenario == "nodisk") begin
      rom_path = "../../../software/nitros9/build/dialog/arm6309_rom.hex";
      void'($value$plusargs("rom=%s", rom_path));
    end
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
    // The populations are set before reset, as a socket is filled before power.
    if (scenario == "e1")    m.mb.set_simms(0);
    if (scenario == "s1")    m.mb.set_simms(1);
    if (scenario == "s2")    m.mb.set_simms(2);
    if (scenario == "s3")    m.mb.set_simms(3);
    if (scenario == "alias") m.mb.set_small(4'b0001);
    // ⭐ the storage card's CARD DETECT, which is the whole difference between
    // the two dialog runs (machine3.v's stub, and boot.asm §10a reads it)
    sd_cd = (scenario == "disk" || scenario == "nitros9" || scenario == "reboot");
    DRAM_C000 = pop_base() + 32'h00C000;

    repeat (240) @(posedge CLK25);
    n_reset = 1;

    if (scenario != "main") begin
      run_scenario();
      $display("");
      if (fails == 0) $display("machine_tb [%s] OK - %0d claims", scenario, claims);
      else            $display("machine_tb [%s] - %0d of %0d claims FAILED", scenario, fails, claims);
      $finish;
    end

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
      walk_claims();
      boot_claims();
    end

    $display("");
    $display("2. The SIMM - ram.md 6.4.1's read-back through a driven bus");
    $display("");
    wait_progress(8'h02, 4000, "a byte survives a round trip to DRAM and back");
    stage2_claims();
    wait_progress(8'h07, 4000, "TASK 1's map is live and distinct from TASK 0's");
    task_claims();

    $display("");
    $display("3. The palette - 256 entries through plan.md 10's write path");
    $display("");
    wait_progress(8'h03, 400000, "256 palette entries load, the index written for every one");
    // Section 2a's 96 stores, which nothing read at all: 32 of $50 then 64 of
    // $51 at STORET, logical $C100 = dram[$00C100].
    bad = 0;
    for (i = 0; i < 96; i++)
      if (m.mb.peek_dram(32'h00C100 + i) !== (i < 32 ? 8'h50 : 8'h51)) bad++;
    ok(bad == 0,
       $sformatf("section 2a's 96 stores are in the SIMM - 32 x $50 then 64 x $51 at $C100 (%0d wrong)", bad));
    if (!timed_out) begin
      bad = 0;
      for (i = 0; i < 256; i++)
        if (m.card.peek_lut(i) !== {i[7:0], i[7:0]}) bad++;
      /* ⛔ THE INDEX IS WRITTEN FOR EVERY ENTRY, and boot.asm's section 3
       * says why: outside VBLANK v3host's posted commit fires on every dot of
       * HLOAD, so PIDX steps twice and a load that leans on the
       * auto-increment lands at every other address. v3machine_tb section 2a
       * is where that question is asked on purpose; this ROM does not depend
       * on the answer, and the claim here is that sub-palette 0 is the
       * identity map the picture below is read through. */
      ok(bad == 0,
         $sformatf("every entry of sub-palette 0 holds what was written (%0d wrong)", bad));
      ok(m.card.peek_lut('h100) === 16'h0000 && m.card.peek_lut('h1FF) === 16'h0000,
         "and nothing has landed in a sub-palette the ROM has not named yet");
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

    /* ---- all four of plan.md 10's VMODEs, from CPU code ------------------
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

    /* ⛔ AND THE ONE THING THE FOUR SCENES SHOW THAT THE CARD DOES NOT DO.
     * plan.md §2.1 and §11 both list "VSYNC polarity from VMODE[0]" as
     * inherited verbatim from graphics.md §6.2.1 and REQUIRED - "it is how
     * the monitor identifies the format". All four frames above were captured
     * with both syncs ASSERTED HIGH and all four came out right, in both
     * vertical families, which can only be true if the XOR is absent.
     * v3dot.cpld.ts says as much beside its VSYNC term. The claim is stated
     * the way it is so that BUILDING the polarity fails it. */
    ok(HS_ON == 1'b1 && VS_ON == 1'b1,
       "⛔ FINDING: both syncs leave this card asserted-high in BOTH vertical families - graphics.md 6.2.1's VMODE[0] polarity XOR, which plan.md 2.1 and 11 call required and inherited, is not on video3");

    /* ---- 7a: the copy engine, and 7b: the sprite -------------------------
     *
     * ⛔ THESE TWO SCENES WERE THE DISPLAY LIST'S until 2026-09-20 - a raster
     * bar and a per-scanline HSCROLL sweep, $20 and $21. video3 deletes the
     * engine outright (plan.md §0 and §1) and there is nothing here to port:
     * no BCTRL, no LRUN, no descriptor stream, no per-scanline palette and no
     * per-scanline scroll. The two progress codes now carry what this card has
     * INSTEAD, and what nothing else in this ROM reaches.
     *
     * 7a is read out of the VRAM ARRAY rather than off the connector, because
     * a copy this ROM could see on the screen would have to land in the
     * picture - and then section 8's frame would be measuring the copy. It
     * goes to VRAM rows 404 and 420, which no mode scans. The ROM compares the
     * 128 bytes through VDATA itself and reports $E4; this restates where they
     * came from and what they should be, so the ROM's own compare is not the
     * only witness. */
    wait_progress(8'h20, 900000,
                  "⭐ plan.md 6's COPY ENGINE: 16 x 8 built with the span writer, copied with CPTR/WPTR/CWIDTH/CHEIGHT/CCTRL, and read back through VDATA - every byte right");
    begin
      int bad, around;
      bad = 0; around = 0;
      for (int r = 0; r < 8; r++)
        for (int c = 0; c < 16; c++) begin
          // boot.asm 7a: source row 404 + r, byte $80 + r*16 + c
          if (m.card.peek(413696 + r * 1024 + c) !== 8'(8'h80 + r * 16 + c)) bad++;
          if (m.card.peek(430080 + r * 1024 + c) !== 8'(8'h80 + r * 16 + c)) bad++;
        end
      ok(bad == 0,
         $sformatf("⭐ READ WITHOUT THE ROM: both rectangles hold $80 + row*16 + col - the source at VRAM row 404 and the copy at row 420 (%0d of 256 wrong)", bad));
      // the engine must not have run past its own rectangle in either axis
      for (int r = 0; r < 9; r++) begin
        if (r < 8 && m.card.peek(430080 + r * 1024 + 16) !== 8'h00) around++;
        if (r == 8 && m.card.peek(430080 + 8 * 1024) !== 8'h00) around++;
      end
      ok(around == 0,
         $sformatf("and CWIDTH and CHEIGHT stopped it: the byte after each row, and the row after the last, are untouched (%0d wrote over)", around));
      ok(m.card.CBUSY === 1'b0,
         "and CBUSY is clear - the ROM's bounded poll of VSTAT b4 saw the end of it");
    end

    /* ---- 7b: the sprite, at the connector -------------------------------
     *
     * ⭐ THE SHAPE IS STATED AS A RULE HERE AND AS 64 BYTES IN THE ROM, which
     * is the same trick v3machine_tb plays with its glyph: the bench could
     * read the table out of the loaded image and then a typo in it would agree
     * with itself. code(r, c) = (r + c) mod 3, 0 transparent, 1 and 2 the two
     * cursor colours - so a row slip, a column slip, a swapped plane or a
     * reversed bit order is a wrong pixel.
     *
     * plan.md §7: the code is the LUT's A9..A8, so a sprite pixel looks its
     * OWN sub-palette up at the background byte's index. The background under
     * the sprite is section 4's pattern, which is constant across each 8-row
     * by 128-pixel cell, so the sprite covers exactly indexes $30 and $38 and
     * boot.asm loads four LUT entries rather than plan §7's 512. */
    wait_progress(8'h21, 900000, "⭐ plan.md 7's SPRITE is enabled - 16 x 16, two bits a pixel, out of the top 64 bytes of MAPBASE 7");
    capture_frame(1400000);
    if (shot_lines > 0) write_ppm("screenshot-sprite.ppm");
    begin
      int bad, fx, fy, lit;
      logic [15:0] want;
      bad = 0; fx = -1; fy = -1; lit = 0;
      ok(shot_lines == 400 && shot_w_min == 640 && shot_w_max == 640,
         $sformatf("the sprite scene is VMODE 00's 400 x 640 (%0d lines, %0d..%0d wide)",
                   shot_lines, shot_w_min, shot_w_max));
      for (int L = 0; L < shot_lines && L < MAXH; L++) begin
        int y, code;
        y = L / 2;
        for (int x = 0; x < 640; x++) begin
          logic [7:0] ix;
          ix = want_index(x, y);
          code = 0;
          if (y >= 48 && y < 64 && x >= 32 && x < 48) code = ((y - 48) + (x - 32)) % 3;
          if (code == 1)      want = 16'h5A5A;
          else if (code == 2) want = 16'hA5A5;
          else                want = {ix, ix};
          if (code != 0) lit++;
          if (shot[L][x] !== want) begin
            bad++;
            if (fx < 0) begin fx = x; fy = L; end
          end
        end
      end
      ok(bad == 0 && lit > 0,
         $sformatf("⭐ EVERY PIXEL IS THE SPRITE OR THE PATTERN UNDER IT: code (r + c) mod 3 over indexes $30 and $38, %0d cursor dots (%0d wrong%s)",
                   lit, bad,
                   fx < 0 ? "" : $sformatf(", first at x=%0d line=%0d: got %04h", fx, fy, shot[fy][fx])));
      ok(m.card.peek_lut('h130) === 16'h5A5A && m.card.peek_lut('h138) === 16'h5A5A
         && m.card.peek_lut('h230) === 16'hA5A5 && m.card.peek_lut('h238) === 16'hA5A5,
         $sformatf("and the two cursor colours are in sub-palettes 1 and 2, where the code puts LUT A9..A8 (%04h %04h %04h %04h)",
                   m.card.peek_lut('h130), m.card.peek_lut('h138),
                   m.card.peek_lut('h230), m.card.peek_lut('h238)));
      // 64 bytes at MAPBASE 7 + $FFC0 = 524,224 - plan §7's home for the shape
      begin
        int shbad;
        shbad = 0;
        for (int r = 0; r < 16; r++)
          for (int b = 0; b < 4; b++) begin
            logic [7:0] w;
            w = 8'h00;
            for (int c = 0; c < 8; c++) begin
              int col, cd;
              col = (b & 1) * 8 + c;
              cd = (r + col) % 3;
              if ((b >> 1) ? (cd >> 1) & 1 : cd & 1) w[7 - c] = 1'b1;
            end
            if (m.card.peek(524224 + r * 4 + b) !== w) shbad++;
          end
        ok(shbad == 0,
           $sformatf("and the shape the ROM wrote IS that rule, byte for byte in VRAM row 511 (%0d of 64 wrong)", shbad));
      end
    end

    /* ---- tile mode ------------------------------------------------------
     *
     * ⭐ v3card_tb DRIVES THE CARD FROM A TASK. This reads the PICTURE, out of
     * a tilemap 6809 code put in VRAM through the span writer, and states
     * plan.md §2.4's concatenation as one expression:
     *
     *     index(x, y) = code(x/8, y/8) << 6 | (y & 7) << 3 | (x & 7)
     *     code(cx, cy) = (cx + cy) & 3               boot.asm's map
     *
     * The tile set is the bytes 0..255, so a pixel's index IS the three fields
     * that addressed it; tile mode drives the LUT's high half with ZERO
     * (plan.md §2.4) so the lookup is sub-palette 0, which section 3 made the
     * identity map - and the value survives to the connector. Every field is
     * checked at every pixel.
     *
     * ⚠ AND THE MAP UNDER IT IS A FOUR-BYTE CELL ON A 1024-BYTE STRIDE
     * (plan.md §2.5) written TWO STORES A CELL with WADV b2, where the card
     * this bench used to run had one byte a cell on a 128-byte stride. The
     * picture expression is unchanged, which is the point: the addressing
     * changed underneath it and the pixels did not. */
    wait_progress(8'h30, 900000, "⭐ tile mode is on - plan.md 2.4's tilemap, built by the CPU two stores a cell");
    capture_frame(1400000);
    if (shot_lines > 0) write_ppm("screenshot-cellmode.ppm");
    ok(shot_lines == 400,
       $sformatf("VMODE 00 doubles, so tile mode still fills the frame (%0d lines)", shot_lines));
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
        for (int i = 0; i < 16; i++) r2 = {r2, $sformatf("%02h ", m.card.peek(196608 + i))};
        $display("      tiles at 131072: %s   (want 00 01 02 03 ...)", r1);
        $display("      map   at 196608: %s   (want 00 xx 00 xx 01 xx 00 xx ... - code, lane 1, attr, lane 3)", r2);
      end
      ok(bad == 0,
         $sformatf("⭐ EVERY PIXEL IS TILEBASE|code<<6|row<<3|col, for the code the map holds (%0d wrong of 256000)", bad));
      ok(codes.size() == 4,
         $sformatf("and all four tile codes are on the screen, so the map fetch really varies (%0d)", codes.size()));
      /* ⭐ AND THE MAP IS FOUR BYTES A CELL, read out of VRAM. WADV b2 is what
       * makes a cell two stores instead of four, and the only way to tell a
       * pointer that stepped by two from one that stepped by one is where the
       * SECOND cell's code landed: at +4, not at +2. */
      begin
        int mbad;
        mbad = 0;
        for (int cr = 0; cr < 25; cr++)
          for (int cc = 0; cc < 80; cc++)
            if (m.card.peek(196608 + cr * 1024 + cc * 4) !== 8'((cr + cc) & 3)) mbad++;
        ok(mbad == 0,
           $sformatf("⭐ and the map in VRAM is plan 2.5's four-byte cell on a 1024-byte stride: code (row + col) & 3 at MAPBASE 3 + row*1024 + col*4 (%0d of 2000 wrong)", mbad));
      end
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
    begin
      int vbad, vfirst;
      vbad = 0; vfirst = -1;
      for (int k = 0; k < VRD_TOTAL && k < vrd_n && k < 4096; k++)
        if (int'(vrd_seq[k]) != vrd_want(k)) begin
          vbad++;
          if (vfirst < 0) vfirst = k;
        end
      ok(vrd_n == VRD_TOTAL && vbad == 0,
         $sformatf("⭐ READ WITHOUT THE ROM: the %0d bytes the CPU loaded from VRAM are section 10's sequence, restated here - (a) 256, (b) 32, (c) 64, (d) 1, (e) 256, (f) 64, (g) 64, (h) 1, (i) 512 = %0d (%0d wrong%s)",
                   vrd_n, VRD_TOTAL, vbad,
                   vfirst < 0 ? "" : $sformatf(", first at load %0d: got %02h want %02h",
                                               vfirst, vrd_seq[vfirst], vrd_want(vfirst))));
      ok(vsnap_n == 2 && vsnap_bad[0] == 0 && vsnap_bad[1] == 0,
         $sformatf("⭐ and VRAM HELD what was stored, at both span starts - (b)/(c)'s 64 bytes and (d)'s prefill, then (f)'s VDATA stores over (e)'s span (%0d snapshots, %0d and %0d wrong)",
                   vsnap_n, vsnap_n > 0 ? vsnap_bad[0] : -1, vsnap_n > 1 ? vsnap_bad[1] : -1));
      vbad = 0;
      for (int j = 0; j < 256; j++) if (m.card.peek(131072 + j) !== 8'(j)) vbad++;
      for (int j = 0; j < 512; j++) if (m.card.peek(VSCR + j) !== 8'hE4) vbad++;
      if (m.card.peek(VSCR + 512) !== 8'h5C) vbad++;
      ok(vbad == 0,
         $sformatf("and at the end: the tile set is 0..255, (h)'s two spans are 512 x $E4, and the byte after them is $5C (%0d wrong)", vbad));
    end
    ok(vram_reads >= 256 + 32 + 64 + 1 + 256,
       $sformatf("and the CPU really read the window - %0d VRAM read cycles", vram_reads));
    ok(wait_dots > 0,
       $sformatf("⭐ and a read WAITED - section 10 (d)'s load under a span held the CPU on /WAIT for %0d dots and still got the right byte", wait_dots));
    ok(vdata_writes >= 64 + 1 + 2 && vdata_reads >= 64 + 1 + 512,
       $sformatf("⭐ graphics.md 19 item 47: the CPU used +$15 VDATA - %0d stores and %0d loads in the I/O page, with no MMU block", vdata_writes, vdata_reads));
    ok(vdata_wait_dots > 0,
       $sformatf("⭐ and a VDATA access WAITED in the I/O page - section 10 (h)'s store and load under a span held the CPU for %0d dots, and the span still came out one colour", vdata_wait_dots));

    // ---- graphics.md 19 item 6: the CPU's sub-slot phase ------------------
    $display("");
    $display("6c. The CPU's sub-slot phase, across a /WAIT stretch - 19 item 6");
    $display("");
    begin
      int used = 0, the_ph = 0, waited_total = 0, waited_elsewhere = 0;
      for (int p = 0; p < 4; p++) begin
        if (ph_at_e[p] > 0) begin used++; the_ph = p; end
        waited_total += ph_at_e_waited[p];
      end
      for (int p = 0; p < 4; p++)
        if (p != the_ph) waited_elsewhere += ph_at_e_waited[p];
      $display("      E-fall by dot phase: %0d %0d %0d %0d   (of those, waited: %0d %0d %0d %0d)",
               ph_at_e[0], ph_at_e[1], ph_at_e[2], ph_at_e[3],
               ph_at_e_waited[0], ph_at_e_waited[1],
               ph_at_e_waited[2], ph_at_e_waited[3]);
      begin
        int total, off;
        total = 0;
        for (int p = 0; p < 4; p++) total += ph_at_e[p];
        off = total - ph_at_e[the_ph];
        ok(ph_at_e[the_ph] > 0 && off * 1000 < total,
           $sformatf("⭐ E-fall LANDS ON ONE DOT PHASE - PH=%0d, %0d of %0d cycles, %0d anywhere else - so 11's read budget is computed from an alignment the machine holds for all but a handful of cycles",
                     the_ph, ph_at_e[the_ph], total, off));
        ok(waited_total > 0,
           $sformatf("and %0d of them were cycles the card had held on /WAIT, so a stretch is really inside this sample", waited_total));
        /* ⛔ AND ON THIS CARD THE STRETCH DOES SLIDE IT, which is the opposite
         * of what the same claim said about hardware/archive/video/. There /WAIT was
         * SPANBUSY alone - RETIRE-gated on SPNTICK, so slot-aligned - and
         * graphics.md 19 item 6's second half was closed by it. v3host's
         * WAITN has a term vsup's did not:
         *
         *     VPORT & E & RW & !RDVALID
         *
         * a VDATA/window READ held until the prefetch lands, and RDVALID
         * rises when RDCK clocks the vread '574 in whatever spare window the
         * arbiter gave it - not on a slot boundary. So the freeze is not a
         * multiple of four dots and E comes back on a different sub-slot.
         * The excursion this run measures is three dots wide and five E
         * cycles long, and a later stretch put it back.
         *
         * ⚠ The claim is written so that FIXING it fails here: if video3's
         * /WAIT release becomes slot-aligned, off goes to zero and this line
         * has to come out with 19 item 6's second half closed again. */
        ok(off > 0 && waited_elsewhere > 0,
           $sformatf("⛔ FINDING: and a /WAIT release on THIS card is not slot-aligned - %0d E-falls, %0d of them waited, landed off PH=%0d. v3host's WAITN holds a VDATA read on !RDVALID, and the prefetch lands in whatever spare window it gets; graphics.md 19 item 6's second half, which vsup closed, is open again on video3",
                     off, waited_elsewhere, the_ph));
      end
    end

    // ---- graphics.md 19 item 1: the store rate, as far as it goes ---------
    $display("");
    $display("6d. What a store costs on THIS core - graphics.md 19 item 1");
    $display("");
    $display("      %0d VRAM writes; the closest two are %0d E cycles apart",
             vram_writes, store_gap_min);
    ok(store_gap_min >= 2 && store_gap_min < 1000000,
       $sformatf("⚠ MEASURED, AND IT IS THE 6809 NUMBER: the closest two VRAM writes in the whole run are %0d E cycles apart. 7.3 scales on ~5 core cycles per store in 6309 NATIVE mode - which this cycle-accurate core is not, and which nothing in this repository can source",
                 store_gap_min));

    /* ⭐ AND THE STORE ITSELF, BY SUBTRACTION - boot.asm section 2a. Two
     * straight-line blocks, 32 stores and 64, bracketed identically: the
     * difference is exactly 32 STA ,X+ with every fixed cost cancelled. This
     * is the number 19 item 1 asks for, for the core that is really here. */
    begin
      int a32, b64, d;
      if (st_e0 >= 0 && st_e1 > st_e0 && st_e2 > st_e1) begin
        a32 = st_e1 - st_e0;
        b64 = st_e2 - st_e1;
        d   = b64 - a32;
        $display("      section 2a: 32 stores + bracket = %0d E, 64 + the same bracket = %0d E",
                 a32, b64);
        ok(d > 0 && (d % 32) == 0 && (d / 32) >= 4 && (d / 32) <= 12,
           $sformatf("⭐ MEASURED BY SUBTRACTION: STA ,X+ costs %0d E cycles on this 6809E - %0d - %0d = %0d for 32 stores, and 19 item 1 wanted exactly this counted rather than estimated",
                     d / 32, b64, a32, d));
      end else
        ok(1'b0, $sformatf("boot.asm section 2a reported its store-rate blocks (marks %0d/%0d/%0d)",
                           st_e0, st_e1, st_e2));
    end

    // ---- and the things that must not have happened -------------------
    $display("");
    $display("7. What must not have happened");
    $display("");
    ok(!saw_bus_conflict, "no cycle had two drivers on D0-D7 - machine.md 2's whole point");
    ok(!saw_pa_conflict,  "no cycle had two drivers on physical A20-A13");
    ok(progress_writes >= 6,
       $sformatf("every stage reported (%0d writes to the progress port)", progress_writes));
    /* ⭐ AND THE SEVEN THE CARD REPORTS ABOUT ITSELF. video3_card.v resolves
     * every internal bus from explicit drivers, so a fight or a floating
     * sample is a countable event rather than an OR that cannot fail
     * (design-review2.md §10). v3card_tb and v3machine_tb ask this of their
     * own runs; this asks it of a run whose driver is boot.asm's POST. */
    ok(n_fba == 0,  $sformatf("never two parts on the framebuffer address bus (%0d dots)", n_fba));
    ok(n_dbus == 0, $sformatf("never two of the host '245, the VSTAT '244 and vread on D7..D0 (%0d dots)", n_dbus));
    ok(n_luta == 0, $sformatf("never two masters on the LUT address bus (%0d dots)", n_luta));
    ok(n_idbf == 0, $sformatf("never two drivers on the card's internal data bus (%0d dots)", n_idbf));
    ok(n_idbz == 0, $sformatf("and nothing ever sampled it undriven (%0d dots)", n_idbz));
    ok(n_lane == 0, $sformatf("no byte was written from a lane nothing drives (%0d dots)", n_lane));
    ok(n_rank == 0, $sformatf("each chip's two fetch ranks: exactly one on, always (%0d dots)", n_rank));
    ok(omr_mismatch == 0,
       $sformatf("⭐ and the dot that shows is exactly the connector's BLANK two dots late, for the whole run - which is what makes the capture above a function of the four signals that leave the card (%0d dots disagree)",
                 omr_mismatch));

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
    #1;
    // ~7.9 s of machine (one dot is two timesteps), and ~40 s for NitrOS-9.
    // ⚠ `disk` and `nodisk` take the SHORT one: they are the POST plus §10a,
    // which is ~0.9 s of machine, and a backstop is only a backstop if it
    // fires in less time than a person will wait - 20 s of machine is well
    // over an hour here.
    // ⛔ DOUBLED ON 2026-09-22, because the boot itself got slower and not
    // because anything was hanging: NitrOS-9 comes off an SD card over
    // bit-banged SPI now, not out of ROM pages through the map. The per-step
    // bounds above are what catch a real hang; this only stops a spin.
    if (scenario == "nitros9" || scenario == "reboot") #1999999999;
    else #399999999;
    $display("FAIL  machine_tb: global timeout - progress $%02h at %0d E cycles",
             progress, e_cycles);
    $display("      %0d VRAM writes, %0d VSTAT reads, %0d register writes, %0d /WAIT dots",
             vram_writes, vstat_reads, reg_writes, wait_dots);
    $display("      SPANBUSY=%b CBUSY=%b PBUSY=%b VBLANK=%b",
             SPANBUSY, m.card.CBUSY, m.card.PBUSY, VBLANK);
    $display("machine_tb - TIMED OUT");
    $finish;
  end

endmodule
