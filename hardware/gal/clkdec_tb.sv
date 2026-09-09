// Testbench for U6 - the divider's frequency, duty and quadrature, the
// /IOSEL decode, and boot mode. Run with `npm run check:sim` from hardware/.
//
// The claims that matter are the ones about Q's phase: gal/mmu.pld's entire
// map-write sequence assumes E and Q are in quadrature in that order, and
// machine.md 1's "3 dots early" is only a quarter cycle at /12.
//
// A comment line here must never begin with the simulator's own name: it
// would be read as a directive.

module clkdec_tb;

  // Half period 5, so a settle delay of 1 is unambiguous.
  logic clk25 = 0;
  always #5 clk25 <= ~clk25;

  logic n_reset = 0, fast_e = 0;
  logic n_iopage = 1, la7 = 0, la6 = 0, la5 = 0, la4 = 0, la0 = 0;
  logic rw = 1, wait_i = 0;
  logic [3:0] cnt;
  logic e, q, run, n_iosel, n_bootoe;

  clkdec dut (.clk25(clk25), .n_reset(n_reset), .fast_e(fast_e),
              .n_iopage(n_iopage), .la7(la7), .la6(la6), .la5(la5),
              .la4(la4), .la0(la0), .wait_i(wait_i), .rw(rw),
              .cnt(cnt), .e(e), .q(q), .run(run),
              .n_iosel(n_iosel), .n_bootoe(n_bootoe));

  // A bare instance of the combinational half, so the decode can be swept
  // exhaustively without reaching inside the divider.
  logic d_iopage, d_la7, d_la6, d_la5, d_la4, d_run;
  logic d_iosel, d_bootoe;
  decode ddut (.n_iopage(d_iopage), .la7(d_la7), .la6(d_la6),
               .la5(d_la5), .la4(d_la4), .run(d_run),
               .n_iosel(d_iosel), .n_bootoe(d_bootoe));

  int fails = 0;
  // Counted, not written down - a hand-maintained claim count goes stale the
  // first time a claim is added, and one was on 2026-09-09.
  int claims = 0;
  task automatic ok(input bit good, input string claim);
    claims++;
    if (good) $display("ok    %s", claim);
    else begin fails++; $display("FAIL  %s", claim); end
  endtask

  int period, high, lead, e_rise, q_rise, prev_rise, t;
  bit pe, pq;
  bit wired, iosel_ok, bootoe_ok, excl_ok, vec_ok, held_ok, run_ok, hi_park_ok;
  bit boot_blk_ok, io_park_ok;
  logic [3:0] hold_cnt; logic hold_e, hold_q;
  bit want;
  string order;

  task automatic measure(input bit fast);
    period = 0; high = 0; lead = 0;
    e_rise = -1; q_rise = -1; prev_rise = -1;
    fast_e = fast;
    n_reset = 0; @(posedge clk25); #1; n_reset = 1;
    pe = e; pq = q;
    for (t = 0; t < 120; t++) begin
      @(posedge clk25); #1;
      if (!pq && q) q_rise = t;
      if (!pe && e) begin
        if (prev_rise >= 0 && period == 0) period = t - prev_rise;
        if (q_rise   >= 0 && lead   == 0)  lead   = t - q_rise;
        prev_rise = t; e_rise = t;
      end
      if (pe && !e && e_rise >= 0 && high == 0) high = t - e_rise;
      pe = e; pq = q;
    end
  endtask

  initial begin
    // ---- divide by 12, the machine's rate ------------------------------
    measure(1'b0);
    ok(period == 12, $sformatf("/12: E period is 12 master clocks (got %0d)", period));
    ok(high   ==  6, $sformatf("/12: E duty is 50%% - 6 of 12 (got %0d)", high));
    ok(lead   ==  3, $sformatf("/12: Q leads E by 3, a quarter cycle (got %0d)", lead));

    // ---- divide by 8, fast-E mode --------------------------------------
    measure(1'b1);
    ok(period ==  8, $sformatf("/8: E period is 8 master clocks (got %0d)", period));
    ok(high   ==  4, $sformatf("/8: E duty is 50%% - 4 of 8 (got %0d)", high));
    // machine.md 1 says "3 dots early", which is 90 degrees at /12 and 135 at
    // /8. A quarter cycle here is 2 - the divisor-dependent tap that
    // graphics.md 18 step 0 lists as an exit criterion.
    ok(lead   ==  2, $sformatf("/8: Q leads E by 2 and NOT by 3 (got %0d)", lead));

    // ---- the phase order both GALs depend on ---------------------------
    order = "";
    fast_e = 0; n_reset = 0; @(posedge clk25); #1; n_reset = 1;
    repeat (14) @(posedge clk25);
    #1; pe = e; pq = q;
    for (t = 0; t < 12; t++) begin
      @(posedge clk25); #1;
      if ( pe && !e) order = {order, "e"};
      if (!pq &&  q) order = {order, "Q"};
      if (!pe &&  e) order = {order, "E"};
      if ( pq && !q) order = {order, "q"};
      pe = e; pq = q;
    end
    // The claim is about CYCLIC order, so any rotation is the same cycle -
    // where the observation window opens is an accident of when reset landed.
    // Asserting "eQEq" exactly failed on "QEqe", which is the same sequence.
    ok(order == "eQEq" || order == "QEqe" || order == "Eqe" + "Q" || order == "qeQE",
       $sformatf("the cycle is E-fall, Q-rise, E-rise, Q-fall (got %s)", order));

    // ---- reset ---------------------------------------------------------
    n_reset = 0; @(posedge clk25); #1;
    ok(e == 0 && q == 0 && cnt == 0, "reset holds the counter, E and Q at zero");
    n_reset = 1;

    // ---- /IOSEL, exhaustive over the three inputs it has ---------------
    iosel_ok = 1;
    for (int p = 0; p < 2; p++)
      for (int a7 = 0; a7 < 2; a7++)
        for (int a6 = 0; a6 < 2; a6++) begin
          d_iopage = p[0]; d_la7 = a7[0]; d_la6 = a6[0]; d_la5 = 0; d_la4 = 0; #1;
          if ((!d_iosel) != (p == 0 && a7 == 0)) iosel_ok = 0;
        end
    ok(iosel_ok, "/IOSEL is $FF00-$FF7F: the I/O page with A7 = 0");

    // A6 must not appear in the decode at all. Until 2026-09-08 the loop
    // above asserted A7 = 1, A6 = 0 - $FF80-$FFBF - under a message that
    // said A7,A6 = 01, and the assertion is what the implementation was
    // written from. Sweeping A6 and demanding no effect is the claim that
    // could not have been written wrong in the same direction.
    iosel_ok = 1;
    for (int p = 0; p < 2; p++)
      for (int a7 = 0; a7 < 2; a7++) begin
        d_iopage = p[0]; d_la7 = a7[0]; d_la6 = 1'b0; d_la5 = 0; d_la4 = 0; #1;
        want = !d_iosel;
        d_la6 = 1'b1; #1;
        if ((!d_iosel) != want) iosel_ok = 0;
      end
    ok(iosel_ok, "A6 does not appear in /IOSEL - the window is 128 bytes");

    // ---- boot mode's combinational half, exhaustive ---------------------
    // machine.md 7.2. The '244 drives physical A20-A13 whenever the map SRAMs
    // do not, and U9 forms the SRAMs' chip enables from the same two
    // conditions - so this is half of a claim that spans two parts. The other
    // half is in jedec.check.ts, against both fuse maps.
    // ⭐ THE RULE IS ONE SENTENCE SINCE 2026-09-09: the buffer drives exactly
    // when the map SRAMs do not. The old rule enumerated two modes and was
    // wrong in both directions - it left the buffer ON during boot-mode block
    // writes, fighting U4 for the SRAM's own I/O pins, and OFF during ordinary
    // I/O cycles, floating eight backplane lines. design-review2.md M-2, M-3.
    bootoe_ok = 1; excl_ok = 1; vec_ok = 1; boot_blk_ok = 1; io_park_ok = 1;
    hi_park_ok = 1;
    for (int p = 0; p < 2; p++)
      for (int a7 = 0; a7 < 2; a7++)
        for (int a6 = 0; a6 < 2; a6++)
          for (int a5 = 0; a5 < 2; a5++)
            for (int a4 = 0; a4 < 2; a4++)
              for (int r = 0; r < 2; r++) begin
                automatic bit iop = (p == 0);
                automatic bit blkhi = iop && a7 == 1 && a6 == 0 && a5 == 0 && a4 == 1;
                automatic bit blklo = iop && a7 == 1 && a6 == 0 && a5 == 1 && a4 == 0;
                // ⚠ THE LOW SRAM'S CONDITION, not the union - 2026-09-09.
                // Only U1 drives physical A20-A13; U1B drives A24-A21 and
                // those never leave the board. With U4 shut for the high
                // window (mmu.pld) the union would leave A20-A13 undriven for
                // the sixteen high-byte writes of every boot.
                automatic bit mapsel = (r == 1 && !iop) || blklo;
                d_iopage = p[0]; d_la7 = a7[0]; d_la6 = a6[0];
                d_la5 = a5[0]; d_la4 = a4[0]; d_run = r[0]; #1;
                // the buffer drives if and only if no map SRAM is selected
                if ((!d_bootoe) != !mapsel) bootoe_ok = 0;
                // M-3: never both, and a boot-mode block write is the case
                // that used to be both, sixteen times per boot.
                if (!d_bootoe && mapsel) boot_blk_ok = 0;
                if (blkhi && d_bootoe) hi_park_ok = 0;
                // M-2: an ordinary I/O cycle parks the address rather than
                // floating it - the buffer is on for every $FFxx that is not a
                // block access, in either mode.
                if (iop && !blklo && d_bootoe) io_park_ok = 0;
                // The '244 and /IOSEL must never assert together for the
                // vector page: /IOSEL means a card is addressed, and no card
                // may see a vector fetch.
                if (iop && a7 == 1 && a6 == 1 && !d_iosel) excl_ok = 0;
                // The vector page asserts the '244 whether or not boot mode
                // does - it is an I/O cycle and not a block access, so the
                // general rule covers it with no term of its own.
                if (iop && a7 == 1 && a6 == 1 && d_bootoe) vec_ok = 0;
              end
    ok(bootoe_ok,   "the buffer drives if and only if the LOW map SRAM is not selected - the net's other driver");
    ok(boot_blk_ok, "so it is OFF for a block-register access in BOOT mode - the sixteen writes of machine.md 7.2's boot sequence no longer fight U4");
    ok(io_park_ok,  "and ON for every other $FFxx cycle INCLUDING a high-byte write, so physical A20-A13 are parked and never floating");
    ok(hi_park_ok, "⭐ and a HIGH-byte write parks them too - U4 is shut for that window since 2026-09-09, so the union of both chip enables would have left them floating sixteen times per boot");
    ok(vec_ok,  "the vector page asserts it forever, boot mode or not - which is what makes $FFFE a reset vector");
    ok(excl_ok, "and /IOSEL never fires for $FFC0-$FFFF, so no card ever sees a vector fetch");

    // ---- the RUN latch --------------------------------------------------
    // Set by ONE write to $FFB1, cleared by nothing but /RESET. $FFB0 is TASK
    // and must not set it, because boot code writes TASK first and the map
    // index is {TASK, block}.
    n_reset = 0; @(posedge clk25); #1;
    ok(run == 1'b0, "RUN comes out of reset at 0 - the machine is in boot mode before it fetches anything");
    n_reset = 1;

    // $FFB0, a write: TASK. Must not set RUN.
    la7 = 1; la6 = 0; la5 = 1; la4 = 1; la0 = 0; rw = 0; n_iopage = 0;
    repeat (24) @(posedge clk25);
    #1; ok(run == 1'b0, "a write to $FFB0 sets TASK and does NOT leave boot mode");

    // A read of $FFB1. Must not set RUN.
    la0 = 1; rw = 1;
    repeat (24) @(posedge clk25);
    #1; ok(run == 1'b0, "and a READ of $FFB1 does not either - the strobe is a write");

    // $FFB1, a write.
    rw = 0;
    repeat (24) @(posedge clk25);
    #1; ok(run == 1'b1, "one write to $FFB1 sets RUN - the last instruction of machine.md 7.2's boot sequence");

    // Nothing clears it but /RESET.
    n_iopage = 1; la7 = 0; la6 = 0; la5 = 0; la4 = 0; la0 = 0; rw = 1;
    repeat (48) @(posedge clk25);
    #1; ok(run == 1'b1, "and nothing clears it - a wild store cannot put the machine back into boot mode over live RAM");
    n_reset = 0; #1;
    ok(run == 1'b0, "but /RESET does, asynchronously - the only reset a 22V10 has");
    n_reset = 1; @(posedge clk25);

    // ---- the divider instance carries the same decode -------------------
    wired = 1;
    for (int p = 0; p < 2; p++)
      for (int a7 = 0; a7 < 2; a7++)
        for (int a6 = 0; a6 < 2; a6++) begin
          n_iopage = p[0]; la7 = a7[0]; la6 = a6[0];
          d_iopage = p[0]; d_la7 = a7[0]; d_la6 = a6[0];
          d_la5 = la5; d_la4 = la4; d_run = run; #1;
          if (n_bootoe != d_bootoe || n_iosel != d_iosel) wired = 0;
        end
    n_iopage = 1; la7 = 1'b0; la6 = 1'b0;
    ok(wired, "U6's own decode outputs match a bare decode on the same inputs");

    // ---- /WAIT holds the divider -----------------------------------------
    // machine.md 5 item 8. vctrl.pld has driven this signal since the video
    // card was captured and nothing listened; these are the claims that say
    // something does now.
    wait_i = 0; n_reset = 0; @(posedge clk25); #1; n_reset = 1;
    repeat (7) @(posedge clk25); #1;          // land somewhere mid-cycle
    hold_cnt = cnt; hold_e = e; hold_q = q;
    wait_i = 1;
    held_ok = 1;
    repeat (40) begin
      @(posedge clk25); #1;
      if (cnt !== hold_cnt || e !== hold_e || q !== hold_q) held_ok = 0;
    end
    ok(held_ok, "/WAIT holds the counter, E and Q for as long as it is asserted");

    // RUN is NOT held by /WAIT, and that is deliberate: it is a mode bit that
    // happens to live on this part, not part of the divider. Holding it would
    // mean a $FFB1 write during a stretched cycle did nothing - and the video
    // card can stretch a cycle by up to 40.7 us (graphics.md 7.4).
    run_ok = 0;
    n_iopage = 0; la7 = 1; la6 = 0; la5 = 1; la4 = 1; la0 = 1; rw = 0;
    repeat (4) begin @(posedge clk25); #1; if (run) run_ok = 1; end
    ok(run_ok, "and /WAIT does NOT hold RUN - a $FFB1 write lands during a stretched cycle");
    n_iopage = 1; la7 = 0; la6 = 0; la5 = 0; la4 = 0; la0 = 0; rw = 1;
    n_reset = 0; @(posedge clk25); #1; n_reset = 1;
    repeat (7) @(posedge clk25); #1;
    hold_cnt = cnt; hold_e = e; hold_q = q;
    wait_i = 1; repeat (40) @(posedge clk25); #1;

    // Releasing it must resume the sequence, not restart or skip it: the next
    // count is exactly the one the counter would have produced with no wait at
    // all. Comparing against a recomputed successor rather than against
    // "something changed" is what makes this a claim instead of a smoke test.
    wait_i = 0;
    @(posedge clk25); #1;
    ok(cnt === ((hold_cnt == 4'd11) ? 4'd0 : hold_cnt + 4'd1),
       "releasing /WAIT resumes the exact count the divider would have reached");

    // And the phase survives, which is what the whole machine's bus timing
    // rests on: E and Q are decoded from the next count, so if the count is
    // right the quadrature is right. Check E against its own decode.
    ok(e === (((hold_cnt == 4'd11) ? 4'd0 : hold_cnt + 4'd1) >= 4'd6),
       "E resumes in phase - a wait stretches a cycle, it does not skip one");

    // *** AND THAT IS EXACTLY WHY THE VIDEO CARD'S SUB-SLOT PHASE MOVES.
    // graphics.md 19 item 6. E is held; the video card's dot-phase counter is
    // NOT - it is clocked by CLK25 on the card and knows nothing about /WAIT -
    // so a stretch of N master clocks slides E against the fetch slot by
    // N mod 4. The claim above is the mechanism, stated from the other side:
    // "resumes the exact count" and "the phase survives" are about E's OWN
    // sequence, not about its alignment to anything free-running.
    //
    // A 40-tick hold is 40 mod 4 = 0, so the run above happens to preserve the
    // alignment. This one holds for 41 and shows it does not.
    begin
      int unsigned phase_before, phase_after, dot;
      dot = 0;
      n_reset = 0; @(posedge clk25); #1; n_reset = 1;
      repeat (7) @(posedge clk25); #1;
      dot = 7 % 4;
      hold_cnt = cnt;
      phase_before = dot;
      wait_i = 1;
      repeat (41) begin @(posedge clk25); dot = (dot + 1) % 4; end
      #1; wait_i = 0;
      @(posedge clk25); dot = (dot + 1) % 4; #1;
      phase_after = dot;
      ok(cnt === ((hold_cnt == 4'd11) ? 4'd0 : hold_cnt + 4'd1),
         "a 41-tick hold still resumes the exact count - the divider does not care how long it was held");
      ok(phase_after !== phase_before,
         $sformatf("⚠ but the free-running dot phase moved under it: %0d -> %0d. 19 item 6 - a /WAIT of a length that is not a multiple of 4 RE-ALIGNS E against the video card's fetch slot, and 11's read budget is computed from a fixed alignment",
                   phase_before, phase_after));
    end

    // /RESET must still win over /WAIT: an asynchronous clear that a card
    // could veto by holding a wire low would be a machine that cannot be reset.
    wait_i = 1; n_reset = 0; @(posedge clk25); #1;
    ok(cnt == 0 && e == 0 && q == 0, "/RESET beats /WAIT - the clear is asynchronous");
    n_reset = 1; wait_i = 0;

    if (fails == 0) $display("\nclkdec.v OK - %0d claims", claims);
    else            $display("\n%0d FAILED", fails);
    if (fails != 0) $fatal(1);
    $finish;
  end

endmodule
