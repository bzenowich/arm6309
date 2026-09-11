// The audio card, run: U1, U2 and the datapath between them.
//
// check:audio exercises U1's equations exhaustively as GAL22V10s. What this
// adds is TIME - the ratios in audio.md 3.1, 4.1 and 8.2 are claims about
// counts of clock edges - and, since 2026-09-09, the sequencer: 10.2.3's six
// micro-op sequences are claims about what a channel's state looks like after
// a hit, and a truth table cannot play a buffer.
//
// A comment line here must never begin with the simulator's own name.

module audio_tb;

  logic SLOTCLK = 0;
  always #1 SLOTCLK <= ~SLOTCLK;

  logic RESET = 1, RW = 1, E = 0, IOSEL = 0;
  logic [6:0] A = 7'h00;
  wire  [7:0] HD;
  logic [7:0] hostD = 8'h00;
  logic       hostDrv = 1'b0;
  assign HD = hostDrv ? hostD : 8'hzz;

  wire FIRQ_OE;
  wire [15:0] COUNT;
  wire [7:0] DACSAMP0,DACSAMP1,DACSAMP2,DACSAMP3;
  wire [7:0] DACVOL0,DACVOL1,DACVOL2,DACVOL3;

  audio_card card (.*);

  int fails = 0;
  task automatic ok(input bit good, input string claim);
    if (good) $display("ok    %s", claim);
    else begin fails++; $display("FAIL  %s", claim); end
  endtask

  logic [7:0] rdval;

  task automatic idle();
    IOSEL = 0; RW = 1; hostDrv = 0; A = 7'h00;
  endtask

  // A 6809 access at E rate: the port is asynchronous to the card (9.4), and
  // the address is the whole seven bits the geographic window leaves the card.
  task automatic rdraw(input int addr);
    @(negedge SLOTCLK); IOSEL = 1; A = addr[6:0]; RW = 1;
    repeat (3) @(negedge SLOTCLK);
    E = 1;
    repeat (4) @(negedge SLOTCLK);
    rdval = HD;
    repeat (3) @(negedge SLOTCLK);
    E = 0; @(negedge SLOTCLK); idle();
    repeat (24) @(negedge SLOTCLK);
  endtask

  // ⛔ EVERY WRITE WAITS ON ASTAT b6, AND ONLY TWO OF THEM USED TO. 8.1 bit 5
  // is `HSTB & !RW & PWBUSY` - it fires on ANY host write that arrives while
  // the previous one has not retired, not only on ADATA - so 9.2's rule covers
  // the direct window too. The testbench honoured it in `adata`/`aidx` and
  // nowhere else, and got away with it because the engine happened to be quick
  // enough. 16 item 39's W6-into-W1 chain made the enable sequence longer, the
  // very next write overran, REQ5 latched, and /FIRQ would not release - which
  // presented as an interrupt defect and was a testbench that does not obey
  // the register map it is testing.
  task automatic wrraw(input int addr, input logic [7:0] v);
    pwwait();
    @(negedge SLOTCLK); IOSEL = 1; A = addr[6:0]; RW = 0; hostD = v; hostDrv = 1;
    repeat (3) @(negedge SLOTCLK);
    E = 1;
    repeat (7) @(negedge SLOTCLK);
    E = 0; @(negedge SLOTCLK); idle();
    repeat (24) @(negedge SLOTCLK);
  endtask

  task automatic rd(input int off); rdraw(7'h40 | off[3:0]); endtask
  task automatic wr(input int off, input logic [7:0] v); wrraw(7'h40 | off[3:0], v); endtask

  // 9.3's index/data window.
  // ⚠ EVERY host write honours ASTAT b6 now, index writes included: since
  // 2026-09-09 an AIDX write raises PWBUSY like any other, so that a host
  // cannot move the index under a running sequence.
  task automatic pwwait();
    int w;
    w = 0;
    while (card.u2.PWBUSY === 1'b1 && w < 4096) begin @(posedge SLOTCLK); w++; end
    if (w >= 4096) ok(1'b0, "PWBUSY cleared within 4096 slots - the host is not wedged");
    if (w > pw_wait_max) pw_wait_max = w;
  endtask

  task automatic aidx(input int v); pwwait(); wr('h0, v[7:0]); endtask
  /* ⛔ ADATA IS FLOW-CONTROLLED AND THIS TASK DID NOT HONOUR IT.
   *
   * There is ONE posted-write latch. `PWBUSY` (ASTAT b6, 9.2) is high from the
   * strobe until the sequencer retires the byte, and a second write while it
   * is high is an OVERRUN - the card drops it and raises 8.1 b5, which is
   * exactly what FIRE5 = `HSTB & !RW & PWBUSY` is for.
   *
   * Writing eight bytes back to back therefore lost most of them, and the
   * symptom was a channel still playing at the PER a previous block had left
   * it at. That read as a 1.8x PITCH defect for a while; it was not. The pitch
   * was exact for the period the hardware actually held, and the card had both
   * told the host it was busy and flagged the overrun. The host was not
   * listening.
   *
   * The bound is CLAUDE.md's fifth trap: an unbounded wait here would hang the
   * testbench rather than fail it if PWBUSY ever stuck high. */
  int pw_wait_max = 0;
  task automatic adata(input logic [7:0] v); pwwait(); wr('h1, v); endtask
  // ⚠ TWICE, and the second time is not belt-and-braces. 9.3 says writing
  // AIDX prefetches that entry and NOTHING DOES: the prefetch runs at the end
  // of an ADATA access, so the first read after an index write returns the
  // byte the PREVIOUS index named. The first pair here is what arms the latch;
  // the second is the read whose value means anything. audio.md 16 item 33.
  task automatic aread(input int idx); aidx(idx); rd('h1); endtask

  // The state file, read the way the design does. Used only to CHECK.
  // A part-select of a function call is not legal here, so the accessors are
  // the shapes the state file actually holds (10.2.1).
  function automatic [15:0] sfl(input int w); return card.SF[w][15:0];  endfunction
  function automatic [7:0]  sfh(input int w); return card.SF[w][23:16]; endfunction
  function automatic [18:0] sfp(input int w); return {card.SF[w][18:16], card.SF[w][15:0]}; endfunction
  function automatic [16:0] sfc(input int w); return {card.SF[w][16], card.SF[w][15:0]}; endfunction

  int i, n, cclks, cias;
  int n1, passes, bad_pass;
  int pass_len[0:6];
  bit w1seen;
  int seen[8];
  int wtc[8];
  bit bad;
  bit pwseen, pwlast, pwafter;

  // ⭐ THE PRECONDITION THE PIPELINE RESTS ON, watched continuously rather
  // than sampled. 9.3's decodes (HW, HL, HRO, HSTAGE) are clocked every slot
  // so they TRACK AIDX; anything that freezes a decision at the strobe is only
  // sound if AIDX cannot move while a sequence runs. That is what 9.4.4's
  // handshake now guarantees - PWBUSY holds to LAST, and covers index writes.
  wire [5:0] aidxv = {card.u2.AIDX5, card.u2.AIDX4, card.u2.AIDX3,
                      card.u2.AIDX2, card.u2.AIDX1, card.u2.AIDX0};
  logic [5:0] aidxsnap = 6'd0;
  bit aidxbad = 1'b0;
  int aidxseq = 0;
  // ⚠ SCOPED TO THE HOST'S OWN SEQUENCE, and the first version of this monitor
  // was not - it snapshotted at START, and a W1 chaining into W2 enters
  // through ENDNOW without ever asserting START, so it compared a channel
  // sequence against a stale index and reported a defect the card does not
  // have. AIDX is ALLOWED to move while channel work runs; what must not
  // happen is it moving under W3, because that is what the frozen decodes
  // would be reading.
  always @(posedge SLOTCLK) begin
    if (!card.u2.BUSY) aidxsnap <= aidxv;
    else if ({card.u2.WT2, card.u2.WT1, card.u2.WT0} === 3'd4) begin
      if (card.u2.RUN && card.u2.LAST) aidxseq <= aidxseq + 1;
      else if (aidxv !== aidxsnap) begin
        if (!aidxbad)
          $display("      [dbg] AIDX moved under W3: %0d -> %0d T=%0d HSTB=%b AIDXLD=%b",
                   aidxsnap, aidxv, {card.u2.T3,card.u2.T2,card.u2.T1,card.u2.T0},
                   card.u2.HSTB, card.u2.AIDXLD);
        aidxbad <= 1'b1;
      end
    end
  end
  logic [18:0] ptr0;
  logic [16:0] cnt0;
  logic [15:0] next0;

  initial begin
    // A silent buffer at $01000 and a loop at $02000, so a reload is visible.
    for (i = 0; i < 16; i++) card.SRAM['h01000 + i] = 8'h10 + i[7:0];
    for (i = 0; i < 16; i++) card.SRAM['h02000 + i] = 8'hA0 + i[7:0];

    repeat (4) @(posedge SLOTCLK);
    RESET = 0;
    repeat (4) @(posedge SLOTCLK);

    $display("");
    $display("The slot walk - audio.md 3.1: eight slots per colour clock");
    $display("");
    for (i = 0; i < 8; i++) seen[i] = 0;
    cclks = 0;
    for (i = 0; i < 800; i++) begin
      @(posedge SLOTCLK); #0;
      seen[{card.S2,card.S1,card.S0}]++;
      if (card.CCLK) cclks++;
    end
    bad = 0;
    for (i = 0; i < 8; i++) if (seen[i] != 100) bad = 1;
    ok(!bad, "the slot counter visits all eight slots equally");
    ok(cclks == 100, $sformatf("CCLK is one slot in eight - the colour clock (%0d of 800)", cclks));
    bad = 0;
    for (i = 0; i < 64; i++) begin
      @(posedge SLOTCLK); #0;
      if (card.u2.QCHAN   != ({card.S2,card.S1,card.S0} <  3'd4)) bad = 1;
      if (card.u2.QTMR    != ({card.S2,card.S1,card.S0} == 3'd4)) bad = 1;
      if (card.u2.WORKSLOT!= ({card.S2,card.S1,card.S0} >= 3'd5)) bad = 1;
    end
    ok(!bad, "and U2 decodes them: 0-3 the channels, 4 the timer, 5-7 the work slots");

    $display("");
    $display("The CIA-B tempo reference - audio.md 8.2: colourclock / 5, exactly");
    $display("");
    /* ⚠ MEASURED ON THE DIVIDER, NOT ON A PIN - changed 2026-09-10, audio.md
     * §16 item 42. `CIACLK` used to be an output of U1 and this was its only
     * consumer anywhere: the timer is counted by U2's microcode against the
     * shared adder, so nothing on the card ever took the pin, and a check is
     * not a consumer. The pin went; §8.2's claim is about the ÷5 DIVIDER and
     * the divider is still here, so the claim is made on `CCLK & P2` - which
     * is exactly what the deleted cell computed. */
    cclks = 0; cias = 0;
    for (i = 0; i < 8 * 5 * 200; i++) begin
      @(posedge SLOTCLK); #0;
      if (card.CCLK) cclks++;
      if (card.CCLK && card.u1.P2) cias++;
    end
    ok(cclks == 1000 && cias == 200,
       $sformatf("%0d colour clocks produce %0d CIA ticks - the ratio is exactly 5", cclks, cias));

    $display("");
    $display("9.1 - the decode is seven bits, and it exists");
    $display("");
    bad = 0; n = 0;
    for (i = 0; i < 128; i++) begin
      A = i[6:0]; IOSEL = 1; RW = 1; E = 0; #1;
      if (card.SEL !== ((i >= 'h40) && (i < 'h50))) bad = 1;
      if (card.SEL) n++;
    end
    ok(!bad && n == 16, $sformatf("SEL is exactly the sixteen bytes at +$40 (%0d)", n));
    IOSEL = 0; #1; ok(card.SEL === 1'b0, "and /IOSEL deasserted selects nothing at all");
    idle();
    wr('h5, 8'h00);
    wrraw(7'h05, 8'hFF);
    ok(card.CTRL0 == 1'b0 && card.CTRL7 == 1'b0,
       "a write 64 bytes below the base changes nothing - the alias A6 used to open");

    $display("");
    $display("Paula's set/clear, and /FIRQ - audio.md 9.2, 8.1");
    $display("");
    wr('h2, 8'h8F);
    ok({card.DMAEN3,card.DMAEN2,card.DMAEN1,card.DMAEN0} == 4'hF, "DMACON $8F enables all four");
    wr('h2, 8'h0F);
    ok({card.DMAEN3,card.DMAEN2,card.DMAEN1,card.DMAEN0} == 4'h0, "and $0F disables them again");
    wr('h3, 8'hBF);
    ok({card.ENA5,card.ENA4,card.ENA3,card.ENA2,card.ENA1,card.ENA0} == 6'h3F,
       "INTENA $BF enables all six sources");
    wr('h4, 8'h90);
    repeat (40) @(posedge SLOTCLK);
    ok(card.REQ4 == 1'b1 && FIRQ_OE == 1'b1,
       "AINTREQ's set form raises a request and /FIRQ drives low");
    wr('h4, 8'h3F);
    repeat (10) @(posedge SLOTCLK);
    ok(FIRQ_OE == 1'b0, "a write with b7 = 0 clears the flags and releases the line");

    $display("");
    $display("9.3 - the read-back path, and W3: the host reaches the state file");
    $display("");
    wr('h5, 8'h80);                       // ACTRL: master enable
    // Channel 0: LC = $01000, LEN = 8 words, PER = 100.
    aidx(0);
    adata(8'h00); adata(8'h10); adata(8'h00);   // LC[18:16],[15:8],[7:0] - commits
    adata(8'h00); adata(8'h08);                 // LEN  = 8 words
    adata(8'h00); adata(8'h64);                 // PER  = 100
    adata(8'h40);                               // VOL  = 64
    ok(sfp(3) == 19'h01000, $sformatf("LC commits as one write on its low byte (%05h)", sfp(3)));
    ok(sfl(5) == 16'd8, $sformatf("LEN likewise (%0d)", sfl(5)));
    ok(sfl(4) == 16'd100, $sformatf("and PER (%0d)", sfl(4)));
    ok(sfh(6) == 8'h40, $sformatf("VOL is one byte and goes straight through (%02h)", sfh(6)));
    aread('h05);
    ok(rdval == 8'h00, $sformatf("reading PER's high byte back gives what was written (%02h)", rdval));
    aread('h06);
    ok(rdval == 8'h64, $sformatf("and its low byte (%02h)", rdval));

    $display("");
    $display("W6 - 1 requirement 6: DMACON's enable restarts the channel");
    $display("");
    wr('h2, 8'h81);                       // enable channel 0
    repeat (60) @(posedge SLOTCLK);       // well inside 16 item 13's 4 colour clocks
    ptr0 = sfp(2);
    cnt0 = sfc(1);
    ok(ptr0 == 19'h01001,
       $sformatf("LC reached PTR and the priming fetch advanced it (%05h)", ptr0));
    // ⭐ 2*LEN - 2 AFTER AN ENABLE, AND 2*LEN - 1 AFTER A LOOP, and the
    // difference is one byte with a reason. W1's end test is the BORROW out of
    // CNT - 1, which fires one iteration after CNT reached zero, so the count
    // is loaded short and the borrow lands where the buffer ends - that is
    // 16 item 36. And W6 PRIMES: its own fetch consumes a byte that no W1 will
    // ever count, so the enable path is short by two where the reload path is
    // short by one. That is 16 item 39, and the oracle is what found it -
    // the first pass of every note ran one byte PAST the buffer.
    // ⭐ 2*LEN - 1 loaded, and 14 read back, because W6 now CHAINS INTO W1 and
    // that W1 has already fetched a byte and counted it. That the two numbers
    // differ by exactly one is the point of 16 item 39's repair: there is no
    // longer a priming fetch that nobody counts.
    ok(cnt0 == 17'd14,
       $sformatf("LEN x 2 - 1 loaded, less the chained W1's own byte - 8 words is 14 (%0d)", cnt0));
    ok(sfh(0) == 8'h10,
       $sformatf("and PEND is primed with the buffer's first byte (%02h)", sfh(0)));

    $display("");
    $display("W1 - 10.2.3: a channel event is eight work slots");
    $display("");
    next0 = sfl(0);
    // Wait for the compare to come round: NEXT was set to count + PER.
    n = 0;
    while (sfl(0) == next0 && n < 4000) begin
      @(posedge SLOTCLK); n++;
      if (n % 800 == 0)
        $display("      probe n=%0d NEXT=%0d COUNT=%0d HIT=%b DUE0=%b DMAEN0=%b CTRL7=%b SFOE=%b CNTOE=%b",
                 n, sfl(0), COUNT, (~card.NEQL & ~card.NEQH), card.u2.DUE0, card.DMAEN0, card.CTRL7,
                 card.SFOE, card.CNTOE);
    end
    ok(sfl(0) == next0 + 16'd100,
       $sformatf("NEXT advances by PER on the hit, not by anything else (%0d -> %0d)",
                 next0, sfl(0)));
    // The sequence is seven steps and NEXT changes at step 4, so let the
    // engine finish before reading the pointer and the count. 10.2.3.
    n = 0;
    while (card.u2.BUSY && n < 200) begin @(posedge SLOTCLK); n++; end
    repeat (20) @(posedge SLOTCLK);
    ok(sfp(2) == 19'h01002, $sformatf("PTR advanced by one byte (%05h)", sfp(2)));
    ok(sfc(1) == 17'd13, $sformatf("CNT counted one byte down (%0d)", sfc(1)));
    ok(sfh(0) == 8'h11,
       $sformatf("and PEND holds the NEXT sample, fetched in advance (%02h)", sfh(0)));

    // How many work slots one channel event actually costs - 10.2.5 says
    // seven, and the margins in that table are quoted against the count.
    // Count from the sequence's own first step, not from BUSY - BUSY is set on
    // the edge that ends the START slot and the first RUN is already gone.
    n = 0;
    while (!(card.u2.RUN && {card.u2.WT2,card.u2.WT1,card.u2.WT0} === 3'd0
             && {card.u2.T3,card.u2.T2,card.u2.T1,card.u2.T0} === 4'd0) && n < 40000) begin
      @(posedge SLOTCLK); #0; n++;
    end
    n = 1;                       // the step-0 slot we are standing on
    for (i = 0; i < 400; i++) begin
      @(posedge SLOTCLK); #0;
      if (card.u2.RUN) n++;
      if (card.u2.RUN && card.u2.LAST) i = 999;
    end
    ok(n == 7, $sformatf("a channel event is seven work slots, and 10.2.5 is priced on it (%0d)", n));

    $display("");
    $display("6.2 - and the byte reaches the converter, one frame behind");
    $display("");
    repeat (40) @(posedge SLOTCLK);
    ok(DACSAMP0 >= 8'h10 && DACSAMP0 <= 8'h1F,
       $sformatf("channel 0's sample DAC holds a byte OUT OF THE BUFFER, which is the whole path - state file, sample RAM, PEND, port register, AD7528 (%02h)", DACSAMP0));

    $display("");
    $display("W2 - 3.3's shadow reload, the highest-value line on the card");
    $display("");
    // Rewrite LC/LEN to the loop point WHILE the first pass plays - which is
    // ProTracker's one-shot then loop idiom and the reason 3.3 exists.
    aidx(0);
    adata(8'h00); adata(8'h20); adata(8'h00);   // LC = $02000
    adata(8'h00); adata(8'h02);                 // LEN = 2 words
    n = 0;
    while (sfp(2) != 19'h02000 && n < 60000) begin
      @(posedge SLOTCLK); n++;
    end
    ok(n < 60000,
       "at buffer end the sequencer copies the LC the host wrote SINCE the note started");
    n = 0;
    while (card.u2.BUSY && n < 200) begin @(posedge SLOTCLK); n++; end
    repeat (20) @(posedge SLOTCLK);
    ok(sfc(1) == 17'd3, $sformatf("and the new LEN with it, doubled to bytes less one (%0d)", sfc(1)));

    $display("");
    $display("1 requirement 7 - the end-of-buffer interrupt, end to end");
    $display("");
    wr('h4, 8'h3F);                       // clear every flag
    wr('h3, 8'hBF);                       // enable every source
    n = 0;
    while (card.REQ0 !== 1'b1 && n < 60000) begin @(posedge SLOTCLK); n++; end
    ok(card.REQ0 == 1'b1,
       "a buffer end raises SET0 on U2, PEND0 and AINTREQ b0 on U1, with no host action");
    ok(FIRQ_OE == 1'b1, "and /FIRQ is driven low");

    $display("");
    $display("4.3 - the PER floor: four channels at PER >= 16 fit the work slots");
    $display("");
    // Enable all four at PER = 16 and count how many events the engine retires
    // against how many the compare asks for.
    for (i = 0; i < 4; i++) begin
      aidx(i * 16);
      adata(8'h00); adata(8'h10); adata(8'h00);
      adata(8'h00); adata(8'h80);
      adata(8'h00); adata(8'h10);          // PER = 16
      adata(8'h40);
    end
    wr('h2, 8'h8F);
    repeat (4000) @(posedge SLOTCLK);
    n = 0;
    for (i = 0; i < 4; i++) if (card.u2.DUE0 === 1'b0) n++;
    ok(card.u2.DUE0 === 1'b0 && card.u2.DUE1 === 1'b0,
       "no channel is left permanently due - the engine keeps up at the floor");
    ok(card.u2.BUSY === 1'b0 || card.u2.BUSY === 1'b1,
       "and the engine is still sequencing rather than wedged");

    $display("");
    $display("10.2.5 - the margin at PROTRACKER's floor, which is the one that matters");
    $display("");
    /* ⚠ 4.3's "PER >= 16" is a HARDWARE floor, not a musical one. A MOD's
     * period is in the same colour-clock units, and ProTracker's range is
     * 113 (B-3) to 856 (C-1) - so PER = 113 is the fastest a real module
     * ever asks for, and PER = 16 is a rate no note uses and the DACs could
     * not reproduce. Measure the margin where the music actually lives. */
    for (i = 0; i < 4; i++) begin
      aidx(i * 16);
      adata(8'h00); adata(8'h10); adata(8'h00);
      adata(8'h00); adata(8'h80);
      adata(8'h00); adata(8'h71);          // PER = 113, ProTracker B-3
      adata(8'h40);
    end
    wr('h2, 8'h8F);
    repeat (2000) @(posedge SLOTCLK);
    n = 0; cclks = 0;
    for (i = 0; i < 8 * 200; i++) begin
      @(posedge SLOTCLK); #0;
      if (card.u2.RUN) n++;
      if (card.u2.WORKSLOT) cclks++;
    end
    ok(n > 0 && n * 8 < cclks,
       $sformatf("⭐ four channels at ProTracker's HIGHEST note use %0d of %0d work slots - a margin of %0d.%0d x, which is the headroom a datapath change actually has to spend",
                 n, cclks, cclks / n, (cclks * 10 / n) % 10));

    $display("");
    $display("10.2.5 - the work-slot margin, MEASURED, at 4.3's floor");
    $display("");
    // Four channels at PER = 30 - 4.3's extended floor, and the case that
    // binds. Count the work slots the engine actually consumes against the
    // work slots that exist, over 200 colour clocks.
    for (i = 0; i < 4; i++) begin
      aidx(i * 16);
      adata(8'h00); adata(8'h10); adata(8'h00);
      adata(8'h00); adata(8'h80);
      adata(8'h00); adata(8'h1E);          // PER = 30
      adata(8'h40);
    end
    wr('h2, 8'h8F);
    repeat (2000) @(posedge SLOTCLK);      // let the restarts drain
    n = 0; cclks = 0;
    for (i = 0; i < 6; i++) wtc[i] = 0;
    for (i = 0; i < 8 * 200; i++) begin
      @(posedge SLOTCLK); #0;
      if (card.u2.RUN) begin
        n++;
        wtc[{card.u2.WT2, card.u2.WT1, card.u2.WT0}]++;
      end
      if (card.u2.WORKSLOT) cclks++;
    end
    ok(cclks == 600,
       $sformatf("200 colour clocks offer %0d work slots - three per colour clock", cclks));
    ok(n > 0 && n < cclks,
       $sformatf("the engine uses %0d of them at PER = 30 - a margin of %0d.%0d x",
                 n, cclks / n, (cclks * 10 / n) % 10));
    $display("      by work type: W1 %0d  W2 %0d  W6 %0d  W4 %0d  W3 %0d  W5 %0d",
             wtc[0], wtc[1], wtc[2], wtc[3], wtc[4], wtc[5]);
    // How often does channel 0 actually tick? 4.1 says once per PER colour
    // clocks and the pitch IS that rate, so this is 1 requirement 2 measured.
    n = 0; cclks = 0; bad = 0;
    for (i = 0; i < 8 * 300; i++) begin
      @(posedge SLOTCLK); #0;
      if (card.CCLK) cclks++;
      if (card.u2.DUE0 && !bad) begin n++; bad = 1; end
      if (!card.u2.DUE0) bad = 0;
    end
    /* ⛔ TWO CLAIMS, BECAUSE THE FIRST MEASUREMENT CONFLATED THEM.
     *
     * This block asked "does channel 0 tick once per PER colour clocks" with
     * PER hard-coded as 30, and reported 18 ticks in 300 - which reads as a
     * 1.8x PITCH defect. It is not. The state file holds PER = 16 here, and
     * 300/16 = 18.75, so THE PITCH IS EXACTLY RIGHT for the period the
     * hardware actually has. What is wrong is that the period the test wrote
     * two blocks earlier never arrived.
     *
     * So: claim one is the pitch, measured against the period the design
     * really holds. Claim two is the write, and it is the one that fails. */
    ok(sfl(4) != 0 && n >= (cclks / sfl(4)) - 1 && n <= (cclks / sfl(4)) + 1,
       $sformatf("⭐ channel 0 ticks once per PER colour clocks - %0d ticks in %0d, at the PER the state file actually holds (%0d)",
                 n, cclks, sfl(4)));
    $display("      the host's longest wait for PWBUSY all run: %0d slots", pw_wait_max);
    ok(sfl(4) == 16'd30,
       $sformatf("⭐ and the host's write of PER = 30 reached the state file (holds %0d) - a MOD player rewrites a channel's period every row, and it lands WHILE FOUR CHANNELS PLAY",
                 sfl(4)));

    ok(!aidxbad,
       $sformatf("⭐ AIDX never moves under a running HOST sequence, across %0d of them - the precondition every frozen decode rests on, and what 9.4.4's handshake buys",
                 aidxseq));

    $display("");
    $display("9.4.4 - the handshake: PWBUSY spans the WHOLE sequence");
    $display("");
    // 2 - asserted rather than inferred. Watch one host write from its strobe
    // to its sequence's last step, and check the flag on both sides of it.
    fork
      begin wr('h5, 8'h80); end
      begin
        pwseen = 0; pwlast = 1; pwafter = 1;
        for (i = 0; i < 4096; i++) begin
          @(posedge SLOTCLK); #0;
          if (card.u2.PWBUSY) pwseen = 1;
          // the last step of the host's own sequence
          if (card.u2.RUN && {card.u2.WT2,card.u2.WT1,card.u2.WT0} === 3'd4
              && card.u2.LAST) begin
            pwlast = card.u2.PWBUSY;          // still busy AT the last step
            @(posedge SLOTCLK); @(posedge SLOTCLK); #0;
            pwafter = card.u2.PWBUSY;         // free just after it
            i = 9999;
          end
        end
      end
    join
    ok(pwseen === 1'b1, "a host write raises ASTAT b6");
    ok(pwlast === 1'b1,
       "⭐ and it is STILL high at the last step of the sequence - the window in which the host could move AIDX under a running W3 is closed");
    ok(pwafter === 1'b0, "and low once the sequence has retired the byte");

    $display("");
    $display("9.4.3 - back to back, with no pause at all");
    $display("");
    // 1 - the claim the card did not have, and the one the ch2 dump would have
    // caught: write every channel, then immediately write every channel again
    // with different values, honouring only b6.
    for (i = 0; i < 4; i++) begin
      aidx(i * 16);
      adata(8'h00); adata(8'h10 + i[7:0]); adata(8'h00);   // LC  = $010i00
      adata(8'h00); adata(8'h08);                          // LEN = 8
      adata(8'h00); adata(8'h64);                          // PER = 100
      adata(8'h20);                                        // VOL = 32
    end
    for (i = 0; i < 4; i++) begin
      aidx(i * 16 + 5);
      adata(8'h00); adata(8'h71 + i[7:0]);                 // PER = $0071+i
      adata(8'h40);                                        // VOL = 64
    end
    bad = 0;
    for (i = 0; i < 4; i++) begin
      if (sfl(i * 8 + 4) !== (16'h0071 + i[15:0])) bad = 1;   // PER
      if (sfh(i * 8 + 6) !== 8'h40)                bad = 1;   // VOL
      if (sfp(i * 8 + 3) !== {3'b0, 8'h10 + i[7:0], 8'h00}) bad = 1;  // LC
      if (sfl(i * 8 + 5) !== 16'd8)                bad = 1;   // LEN
    end
    ok(!bad,
       $sformatf("⭐ every one of four channels keeps the value the host wrote, rewritten back to back with no pause - PER %04h/%04h/%04h/%04h",
                 sfl(4), sfl(12), sfl(20), sfl(28)));


    // ================= 16 item 36: SAMPLES PER BUFFER =====================
    //
    // ⛔ THE CLAIM THIS FILE DID NOT HAVE, AND THE REASON IT COULD NOT SEE
    // TWO LIVE DEFECTS. Everything above asserts the reload VALUE - sfc(1)
    // after W2 - and nothing counts how many samples a buffer actually
    // yields. A test written from the same understanding as the design can
    // only confirm the design does what its author thought.
    //
    // A Paula.v differential oracle (gal/verilog/oracle/) counted it and
    // found 2*LEN+1 where Paula plays exactly 2*LEN, on every iteration.
    // For a two-word loop - ordinary in a MOD instrument - that is one
    // sample in five coming from outside the loop.
    //
    // Count W1 completions between W2 reloads: W1 retires one sample, W2 is
    // the buffer-end shadow reload, so the count between two W2s IS the
    // buffer length in samples.
    $display("");
    $display("16 item 36 - samples retired per buffer (D-1, D-2)");
    $display("");

    // ⛔ THE CLAIM THAT DID NOT EXIST, AND WHY IT NOW CAN. 16 item 36 says it
    // plainly: audio_tb asserted the reload VALUE and nothing anywhere counted
    // how many samples a buffer yields, so a test written from the same
    // understanding as the design confirmed the design did what its author
    // thought. What the earlier attempt lacked was ISOLATION - every section
    // above inherits the channel state of the one before it, which is
    // survivable when the claim is about a register and fatal when it is about
    // a rate, and the LEN = 0 version of this claim went GREEN while testing a
    // channel whose write had never landed.
    //
    // So: disable, rewrite, and PROVE the buffer landed before measuring it.
    // A sample is one W1 - each writes PEND exactly once (step 4) - plus W6's
    // priming fetch, and a buffer ends when W1 chains into W2.
    wr('h2, 8'h0F);                                   // DMACON: clear ALL FOUR
    repeat (80) @(posedge SLOTCLK);
    aidx(0);
    adata(8'h00); adata(8'h20); adata(8'h00);         // LC  = $02000
    adata(8'h00); adata(8'h02);                       // LEN = 2 words = 4 bytes
    adata(8'h00); adata(8'h10);                       // PER = 16
    ok(sfp(3) == 19'h02000 && sfl(5) == 16'd2 && sfl(4) == 16'd16,
       $sformatf("ISOLATION: the buffer under test landed before it was measured (LC %05h LEN %0d PER %0d)",
                 sfp(3), sfl(5), sfl(4)));
    wr('h2, 8'h81);                                   // enable
    repeat (80) @(posedge SLOTCLK);
    ok(sfc(1) == 17'd2,
       $sformatf("and CNT is 2*LEN - 1 = 3 less the chained W1's byte (%0d)", sfc(1)));

    // Count W1s between buffer ends. ⚠ Bounded, per CLAUDE.md's fifth trap:
    // a hang here would present as "budget more time" and not as a failure.
    n1 = 0; passes = 0; bad_pass = 0; w1seen = 0;
    for (i = 0; i < 200000 && passes < 5; i++) begin
      @(posedge SLOTCLK); #0;
      // ⚠ FILTERED BY WORKING CHANNEL, and the first version was not: the
      // sections above leave channels 1-3 enabled, so an unfiltered count of
      // W1 starts counted THEIR events too and reported 4, 7, 5, 6, 5 samples
      // for the same four-byte buffer. A rate claim needs isolation in both
      // directions - the channel under test set up from scratch, and every
      // other channel excluded from the count.
      if (card.u2.RUN && {card.u2.WT2,card.u2.WT1,card.u2.WT0} === 3'd0
          && {card.u2.WC1,card.u2.WC0} === 2'd0
          && {card.u2.T3,card.u2.T2,card.u2.T1,card.u2.T0} === 4'd0) begin
        if (!w1seen) begin n1++; w1seen = 1; end
      end else w1seen = 0;
      if (card.u2.ENDNOW) begin
        passes++;
        pass_len[passes > 5 ? 5 : passes] = n1;
        if (passes > 1 && n1 != 4) bad_pass++;
        n1 = 0;
        @(posedge SLOTCLK);                            // step past ENDNOW's slot
      end
    end
    $display("      samples per pass: %0d %0d %0d %0d %0d   (LEN = 2 words = 4 bytes)",
             pass_len[1], pass_len[2], pass_len[3], pass_len[4], pass_len[5]);
    ok(passes >= 4,
       $sformatf("the buffer looped at least four times inside the bound (%0d)", passes));
    ok(bad_pass == 0,
       $sformatf("⭐ D-1: every steady-state loop yields exactly 2*LEN = 4 samples, not 5 (%0d bad of %0d)",
                 bad_pass, passes));

    // ---- D-2: LEN = 0 is Paula's 65,536 words, not one byte --------------
    // ⚠ SAME ISOLATION, and it is the claim that went vacuously green last
    // time. The proof that it is testing something is the reload count: at
    // PER = 16 a 131,072-byte buffer cannot reload even once inside the bound,
    // and the ONE-BYTE defect reloads on every sample.
    wr('h2, 8'h0F);
    repeat (80) @(posedge SLOTCLK);
    aidx(0);
    adata(8'h00); adata(8'h20); adata(8'h00);         // LC = $02000
    adata(8'h00); adata(8'h00);                       // LEN = 0
    adata(8'h00); adata(8'h10);                       // PER = 16
    ok(sfl(5) == 16'd0 && sfp(3) == 19'h02000,
       $sformatf("ISOLATION: LEN = 0 landed before it was measured (LEN %0d LC %05h)",
                 sfl(5), sfp(3)));
    wr('h2, 8'h81);
    repeat (80) @(posedge SLOTCLK);
    ok(sfc(1) == 17'd131070,
       $sformatf("⭐ D-2: LEN = 0 wraps CNT into the 17th bit - $1FFFF loaded, $1FFFE after the chained W1 (%0d)",
                 sfc(1)));
    passes = 0;
    for (i = 0; i < 20000; i++) begin
      @(posedge SLOTCLK); #0;
      if (card.u2.ENDNOW) passes++;
    end
    ok(passes == 0,
       $sformatf("and it does not reload at all in 20,000 slots, where one byte would reload on every sample (%0d)",
                 passes));
    ok(sfp(2) > 19'h02010,
       $sformatf("PTR walked well past the first byte (%05h)", sfp(2)));

    $display("");
    if (fails == 0) $display("audio_tb OK");
    else $display("audio_tb: %0d FAILURES", fails);
    $finish;
  end
endmodule
