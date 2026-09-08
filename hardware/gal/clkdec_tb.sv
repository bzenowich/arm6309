// Testbench for U6 - the divider's frequency, duty and quadrature, and the
// two decodes that ride with it. Run with `npm run check:sim` from hardware/.
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
  logic n_iopage = 1, la7 = 0, la6 = 0, a19 = 0, a20 = 0, rw = 1, wait_i = 0;
  logic [3:0] cnt;
  logic e, q, n_iosel, n_ram_ce, n_ram_oe, n_ram_we;

  clkdec dut (.clk25(clk25), .n_reset(n_reset), .fast_e(fast_e),
              .n_iopage(n_iopage), .la7(la7), .la6(la6), .a19(a19), .a20(a20),
              .wait_i(wait_i), .rw(rw),
              .cnt(cnt), .e(e), .q(q), .n_iosel(n_iosel),
              .n_ram_ce(n_ram_ce), .n_ram_oe(n_ram_oe), .n_ram_we(n_ram_we));

  // A bare instance of the combinational half, so the decode can be swept
  // exhaustively without reaching inside the divider.
  logic d_iopage, d_la7, d_la6, d_a19, d_a20, d_rw, d_e;
  logic d_iosel, d_ce, d_oe, d_we;
  decode ddut (.n_iopage(d_iopage), .la7(d_la7), .la6(d_la6), .a19(d_a19),
               .a20(d_a20), .rw(d_rw), .e(d_e), .n_iosel(d_iosel),
               .n_ram_ce(d_ce), .n_ram_oe(d_oe), .n_ram_we(d_we));

  int fails = 0;
  task automatic ok(input bit good, input string claim);
    if (good) $display("ok    %s", claim);
    else begin fails++; $display("FAIL  %s", claim); end
  endtask

  int period, high, lead, e_rise, q_rise, prev_rise, t;
  bit pe, pq;
  bit sel_ok, oe_ok, we_ok, never_io, never_both, wired, iosel_ok, top_ok;
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
          d_iopage = p[0]; d_la7 = a7[0]; d_la6 = a6[0]; #1;
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
        d_iopage = p[0]; d_la7 = a7[0]; d_la6 = 1'b0; #1;
        want = !d_iosel;
        d_la6 = 1'b1; #1;
        if ((!d_iosel) != want) iosel_ok = 0;
      end
    ok(iosel_ok, "A6 does not appear in /IOSEL - the window is 128 bytes");

    // ---- the system RAM decode, exhaustive ------------------------------
    sel_ok = 1; oe_ok = 1; we_ok = 1; never_io = 1; never_both = 1; top_ok = 1;
    for (int p = 0; p < 2; p++)
      for (int a = 0; a < 2; a++)
        for (int a2 = 0; a2 < 2; a2++)
          for (int r = 0; r < 2; r++)
            for (int ee = 0; ee < 2; ee++) begin
              // not the I/O page, A20 = 0 and A19 = 0
              want = (p == 1 && a == 0 && a2 == 0);
              d_iopage = p[0]; d_a19 = a[0]; d_a20 = a2[0];
              d_rw = r[0]; d_e = ee[0]; #1;
              if ((!d_ce) != want)                        sel_ok     = 0;
              if ((!d_oe) != (want && r == 1))            oe_ok      = 0;
              if ((!d_we) != (want && r == 0 && ee == 1)) we_ok      = 0;
              if (p == 0 && (!d_ce || !d_we))             never_io   = 0;
              if (!d_oe && !d_we)                         never_both = 0;
              if (a2 == 1 && (!d_ce || !d_oe || !d_we))   top_ok     = 0;
            end
    ok(sel_ok,     "system RAM is selected by A20 = 0 and A19 = 0, outside the I/O page");
    ok(top_ok,     "system RAM is silent throughout A20 = 1 - the megabyte cards may claim");
    ok(oe_ok,      "RAM /OE is qualified by R/W - no bus fight on a write");
    ok(we_ok,      "RAM /WE is the decode, R/W low and E high");
    ok(never_io,   "the system RAM is never selected or written during an I/O cycle");
    ok(never_both, "RAM /OE and /WE are never asserted together");

    // ---- the divider instance carries the same decode -------------------
    wired = 1;
    for (int p = 0; p < 2; p++)
      for (int a = 0; a < 2; a++)
        for (int r = 0; r < 2; r++) begin
          n_iopage = p[0]; a19 = a[0]; rw = r[0]; la7 = 1'b0; la6 = 1'b0;
          a20 = 1'b0;
          d_iopage = p[0]; d_a19 = a[0]; d_rw = r[0]; d_e = e;
          d_la7 = 1'b0; d_la6 = 1'b0; d_a20 = 1'b0; #1;
          if (n_ram_ce != d_ce || n_ram_oe != d_oe
              || n_ram_we != d_we || n_iosel != d_iosel) wired = 0;
        end
    ok(wired, "U6's own decode outputs match a bare decode on the same inputs");

    // ---- /WAIT holds the divider -----------------------------------------
    // machine.md 5 item 8. vctrl.pld has driven this signal since the video
    // card was captured and nothing listened; these are the claims that say
    // something does now.
    wait_i = 0; n_reset = 0; @(posedge clk25); #1; n_reset = 1;
    repeat (7) @(posedge clk25); #1;          // land somewhere mid-cycle
    hold_cnt = cnt; hold_e = e; hold_q = q;
    wait_i = 1;
    top_ok = 1;
    repeat (40) begin
      @(posedge clk25); #1;
      if (cnt !== hold_cnt || e !== hold_e || q !== hold_q) top_ok = 0;
    end
    ok(top_ok, "/WAIT holds the counter, E and Q for as long as it is asserted");

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

    // /RESET must still win over /WAIT: an asynchronous clear that a card
    // could veto by holding a wire low would be a machine that cannot be reset.
    wait_i = 1; n_reset = 0; @(posedge clk25); #1;
    ok(cnt == 0 && e == 0 && q == 0, "/RESET beats /WAIT - the clear is asynchronous");
    n_reset = 1; wait_i = 0;

    if (fails == 0) $display("\nclkdec.v OK - 21 claims");
    else            $display("\n%0d FAILED", fails);
    if (fails != 0) $fatal(1);
    $finish;
  end

endmodule
