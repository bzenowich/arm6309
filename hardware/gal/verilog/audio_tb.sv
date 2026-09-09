// The audio card's CPLD, run rather than swept: the eight-slot walk against the
// colour clock, the divide-by-five that has to BE the Amiga's CIA-B clock,
// Paula's set/clear registers, and 9.4.5's read/clear ordering.
//
// check:audio exercises the same equations exhaustively as six GAL22V10s. What
// this adds is time: the ratios in audio.md 3.1, 4.1 and 8.2 are claims about
// counts of clock edges, and a truth table cannot count edges.
//
// A comment line here must never begin with the simulator's own name.

module audio_tb;

  // One tick = one 28.37516 MHz slot.
  logic SLOTCLK = 0;
  always #1 SLOTCLK <= ~SLOTCLK;

  logic RESET = 1, SEL = 0, RW = 1, E = 0;
  logic A0 = 0, A1 = 0, A2 = 0, A3 = 0;
  logic [7:0] D = 0;
  logic SET0=0, SET1=0, SET2=0, SET3=0, SET4=0, SET5=0;

  wire S0,S1,S2, CCLK, CHANSLOT, TMRSLOT, HOSTSLOT, DEFSLOT, DEFREQ, DEFACK;
  wire WAIDX, WDMACON, WINTENA, WINTREQ, WCTRL, RINTREQ, RASTAT, SFCE, SRCE, HOSTREQ;
  wire DMAEN0,DMAEN1,DMAEN2,DMAEN3, P0,P1,P2, CIACLK;
  wire ENA0,ENA1,ENA2,ENA3,ENA4,ENA5;
  wire REQ0,REQ1,REQ2,REQ3,REQ4,REQ5;
  wire PEND0,PEND1,PEND2,PEND3,PEND4,PEND5;
  wire CTRL0,CTRL1,CTRL2,CTRL3,CTRL4,CTRL5,CTRL6,CTRL7;
  wire SYNCH1,SYNCH2,SYNCR1,SYNCR2,SYNCS1,SYNCS2, MERGE, FIRQANY, NEWREQ;
  wire FIRQ, FIRQ_OE;

  audio dut (.*, .D0(D[0]),.D1(D[1]),.D2(D[2]),.D3(D[3]),
             .D4(D[4]),.D5(D[5]),.D6(D[6]),.D7(D[7]));

  int fails = 0;
  task automatic ok(input bit good, input string claim);
    if (good) $display("ok    %s", claim);
    else begin fails++; $display("FAIL  %s", claim); end
  endtask

  // A 6809 write at E rate: the card's port is asynchronous to it (9.4).
  task automatic rd(input int off);
    @(negedge SLOTCLK);
    SEL = 1; {A3,A2,A1,A0} = off[3:0]; RW = 1;
    repeat (3) @(negedge SLOTCLK);
    E = 1;
    repeat (7) @(negedge SLOTCLK);
    E = 0;
    @(negedge SLOTCLK);
    SEL = 0; {A3,A2,A1,A0} = 4'h0;
    repeat (14) @(negedge SLOTCLK);
  endtask

  task automatic wr(input int off, input logic [7:0] v);
    @(negedge SLOTCLK);
    SEL = 1; {A3,A2,A1,A0} = off[3:0]; RW = 0; D = v;
    repeat (3) @(negedge SLOTCLK);
    E = 1;
    repeat (7) @(negedge SLOTCLK);   // E high, comfortably longer than a slot
    E = 0;
    @(negedge SLOTCLK);
    SEL = 0; RW = 1; D = 0; {A3,A2,A1,A0} = 4'h0;
    repeat (14) @(negedge SLOTCLK);
  endtask

  int n, cclks, cias, slots, i;
  int seen[8];
  bit bad;
  logic [5:0] req_now, ena_now, dma_now;

  initial begin
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
      seen[{S2,S1,S0}]++;
      if (CCLK) cclks++;
    end
    bad = 0;
    for (i = 0; i < 8; i++) if (seen[i] != 100) bad = 1;
    ok(!bad, "the slot counter visits all eight slots equally");
    ok(cclks == 100, $sformatf("CCLK is one slot in eight - the colour clock (got %0d of 800)", cclks));

    // 3.1's allocation: 0-3 channels, 4 timer, 5 host, 6-7 deferred.
    bad = 0;
    for (i = 0; i < 64; i++) begin
      @(posedge SLOTCLK); #0;
      if (CHANSLOT != ({S2,S1,S0} < 3'd4)) bad = 1;
      if (TMRSLOT  != ({S2,S1,S0} == 3'd4)) bad = 1;
      if (HOSTSLOT != ({S2,S1,S0} == 3'd5)) bad = 1;
      if (DEFSLOT  != ({S2,S1,S0} >= 3'd6)) bad = 1;
    end
    ok(!bad, "slots 0-3 are the channels, 4 the timer, 5 host service, 6-7 deferred");

    $display("");
    $display("The CIA-B tempo clock - audio.md 8.2: colourclock / 5, exactly");
    $display("");
    cclks = 0; cias = 0;
    for (i = 0; i < 8 * 5 * 200; i++) begin
      @(posedge SLOTCLK); #0;
      if (CCLK) cclks++;
      if (CIACLK) cias++;
    end
    ok(cclks == 1000 && cias == 200,
       $sformatf("%0d colour clocks produce %0d CIA ticks - the ratio is exactly 5",
                 cclks, cias));

    $display("");
    $display("Paula's set/clear convention - audio.md 9.2");
    $display("");
    wr('h2, 8'h8F);                       // DMACON: set channels 0-3
    ok({DMAEN3,DMAEN2,DMAEN1,DMAEN0} == 4'hF, "DMACON $8F enables all four channels");
    wr('h2, 8'h05);                       // clear 0 and 2
    ok({DMAEN3,DMAEN2,DMAEN1,DMAEN0} == 4'hA,
       $sformatf("DMACON $05 clears channels 0 and 2 and leaves 1 and 3 (got %0h)",
                 {DMAEN3,DMAEN2,DMAEN1,DMAEN0}));
    wr('h2, 8'h80);                       // set nothing
    ok({DMAEN3,DMAEN2,DMAEN1,DMAEN0} == 4'hA, "a set of no bits changes nothing");

    wr('h3, 8'hBF);                       // INTENA: enable all six
    ok({ENA5,ENA4,ENA3,ENA2,ENA1,ENA0} == 6'h3F, "INTENA $BF enables all six sources");
    wr('h3, 8'h10);                       // clear the timer enable
    ok({ENA5,ENA4,ENA3,ENA2,ENA1,ENA0} == 6'h2F,
       $sformatf("INTENA $10 clears bit 4 alone (got %0h)",
                 {ENA5,ENA4,ENA3,ENA2,ENA1,ENA0}));

    $display("");
    $display("/FIRQ is open drain - audio.md 8.1's wire-OR");
    $display("");
    wr('h3, 8'h90);                       // re-enable the timer source
    wr('h4, 8'h90);                       // INTREQ set: the timer's request bit
    repeat (40) @(posedge SLOTCLK);
    ok(REQ4 == 1'b1, "AINTREQ's set form raises a request - 9.2's normative write");
    ok(FIRQ_OE == 1'b1,
       "and /FIRQ is driven low, because bit 4 is enabled - the pin drives or floats");
    wr('h3, 8'h10);                       // clear ENA4
    repeat (10) @(posedge SLOTCLK);
    ok(FIRQ_OE == 1'b0, "masking the source releases the line without clearing the flag");
    ok(REQ4 == 1'b1, "and the flag survives the mask");
    wr('h4, 8'h10);                       // INTREQ clear bit 4
    repeat (10) @(posedge SLOTCLK);
    ok(REQ4 == 1'b0, "a write with b7 = 0 clears the named bit");

    $display("");
    $display("9.4.5 - a set arriving under a host read is not lost");
    $display("");
    // Raise SET0 (a buffer-exhaust from the sequencer) and merge it.
    SET0 = 1; repeat (4) @(posedge SLOTCLK); SET0 = 0;
    repeat (400) @(posedge SLOTCLK);
    ok(REQ0 == 1'b1, {"⭐ a channel's SET reaches AINTREQ with the host doing ",
                      "nothing - which is what makes an end-of-buffer interrupt ",
                      "deliverable at all"});
    ok(PEND0 == 1'b0, {"and the pending register has handed it over rather than ",
                       "holding it: MERGE is every colour clock, not the trailing ",
                       "edge of a read that may never come"});
    // MERGE = CCLK & SYNCR2 & !SYNCR1 - the trailing edge of a host READ of
    // AINTREQ. Nothing else produces it.
    // And a read must not lose one either: walk the read across every slot
    // phase and set a request in the middle of each.
    n = 0;
    for (i = 0; i < 16; i++) begin
      wr('h4, 8'h01);                          // clear REQ0
      repeat (i) @(posedge SLOTCLK);           // shift the read by one slot
      fork
        begin rd('h4); end
        begin
          repeat (6 + i) @(posedge SLOTCLK);
          SET0 = 1; repeat (2) @(posedge SLOTCLK); SET0 = 0;
        end
      join
      repeat (40) @(posedge SLOTCLK);
      if (REQ0) n++;
    end
    ok(n == 16, $sformatf("a request raised DURING a host read survives it, at every one of 16 read phases (merged %0d)", n));

    $display("");
    $display("The two-flop host synchroniser - audio.md 9.4.4");
    $display("");
    // NEWREQ must be one slot wide per host access, never two.
    n = 0;
    fork
      begin wr('h5, 8'h01); end
      begin
        for (i = 0; i < 60; i++) begin @(posedge SLOTCLK); #0; if (NEWREQ) n++; end
      end
    join
    ok(n == 1, $sformatf("one host access produces exactly one NEWREQ pulse (got %0d)", n));
    ok(CTRL0 == 1'b1, "and ACTRL took the write");

    $display("");
    if (fails == 0) $display("audio_tb OK");
    else $display("audio_tb: %0d FAILURES", fails);
    $finish;
  end
endmodule
