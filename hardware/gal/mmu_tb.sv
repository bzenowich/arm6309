// Testbench for the MMU GAL - mmu.v against the claims that
// video/docs/graphics.md 6.3.1 and docs/machine.md 2 make about it.
//
// Run it with `npm run check:sim` from hardware/. A comment line here must
// never begin with the simulator's own name: it would be read as a directive.
//
// This asserts the same properties as mmu.check.ts, deliberately. The two
// exist because they check different things: mmu.check.ts checks that the
// equations mean what the phase table says, and this checks that mmu.v - the
// artefact a future 6809-core co-simulation will drive - still agrees with
// them. Three statements of one logic, and this is the seam between two.

module mmu_tb;

  logic [15:4] la;
  logic        e, q, rw;
  logic        n_iopage, muxsel, n_isooe, n_mapwe, n_mapoe, n_ctrlcp;

  logic blkhi, blklo;
  mmu dut (.la(la), .e(e), .q(q), .rw(rw), .blkhi(blkhi), .blklo(blklo),
           .n_iopage(n_iopage), .muxsel(muxsel), .n_isooe(n_isooe),
           .n_mapwe(n_mapwe), .n_mapoe(n_mapoe), .n_ctrlcp(n_ctrlcp));

  int fails = 0;

  task automatic ok(input bit good, input string claim);
    if (good) $display("ok    %s", claim);
    else begin fails++; $display("FAIL  %s", claim); end
  endtask

  // Q leads E by 90 degrees: E-fall, Q-rise, E-rise, Q-fall, E-fall.
  localparam bit PH_E [0:3] = '{1'b0, 1'b0, 1'b1, 1'b1};
  localparam bit PH_Q [0:3] = '{1'b0, 1'b1, 1'b1, 1'b0};

  // The tasks below take a full 16-bit address so the call sites can read
  // $FFA0 and $FFB0 as themselves, and then use only addr[15:4] - because
  // that is exactly what the part has pins for. The unused low nibble is the
  // design, not an oversight, so the lint is waived here and nowhere else.
  /* verilator lint_off UNUSEDSIGNAL */
  task automatic drive(input logic [15:0] addr, input logic [1:0] ph, input bit r);
    la = addr[15:4]; e = PH_E[ph]; q = PH_Q[ph]; rw = r;
    #1;
  endtask

  // Four-phase trace of one signal over one cycle, as "0011" etc. A task and
  // not a function because it advances time, which IEEE 1800 13.4.4 forbids
  // in a function.
  task automatic trace(input logic [15:0] addr, input bit r, input int sig,
                       output string s);
    s = "";
    for (int ph = 0; ph < 4; ph++) begin
      la = addr[15:4]; e = PH_E[ph[1:0]]; q = PH_Q[ph[1:0]]; rw = r;
      #1;
      case (sig)
        0: s = {s, n_iopage ? "0" : "1"};
        1: s = {s, muxsel   ? "1" : "0"};
        2: s = {s, n_isooe  ? "0" : "1"};
        3: s = {s, n_mapwe  ? "0" : "1"};
        4: s = {s, n_mapoe  ? "0" : "1"};
        5: s = {s, n_ctrlcp ? "1" : "0"};   // the PIN level, high is idle
      endcase
    end
  endtask
  /* verilator lint_on UNUSEDSIGNAL */

  bit dec_hi, dec_lo, dec_page, dec_blk, dec_wr, dec_rd, bbm, wr_in_buf, ctl_out;
  string t;
  int edges;
  bit prev, cur;

  initial begin
    dec_page = 1; dec_blk = 1; dec_wr = 1; dec_rd = 1; dec_hi = 1; dec_lo = 1;
    bbm = 1; wr_in_buf = 1; ctl_out = 1;

    // Exhaustive: 65536 addresses x 4 phases x R/W.
    for (int a = 0; a < 65536; a++)
      for (int ph = 0; ph < 4; ph++)
        for (int r = 0; r < 2; r++) begin
          automatic bit in_page = (a >= 16'hFF00);
          // TWO block windows since 2026-09-09: the high byte at $FF90-$FF9F
          // and the low at $FFA0-$FFAF, because LA3 is the write index's TASK
          // bit and cannot also pick the SRAM. mmu.pld, design-review2.md M-1.
          automatic bit in_hi   = (a >= 16'hFF90 && a <= 16'hFF9F);
          automatic bit in_lo   = (a >= 16'hFFA0 && a <= 16'hFFAF);
          automatic bit in_blk  = in_hi || in_lo;
          automatic bit in_ctl  = (a >= 16'hFFB0 && a <= 16'hFFBF);
          drive(a[15:0], ph[1:0], r[0]);

          if ((!n_iopage) != in_page)                 dec_page  = 0;
          if (muxsel      != in_blk)                  dec_blk   = 0;
          if (blkhi       != in_hi)                   dec_hi    = 0;
          if (blklo       != in_lo)                   dec_lo    = 0;
          if (!n_mapwe && !(in_blk && r == 0))        dec_wr    = 0;
          if (!n_ctrlcp && !in_ctl)                   ctl_out   = 0;
          // Direction-aware: ISO_DIR is R/W, so the '245 drives the SRAM's
          // pins only on a write. Both open together on a read is correct.
          if (!n_mapoe && !n_isooe && r == 0)         bbm       = 0;
          if (!n_mapwe && n_isooe)                    wr_in_buf = 0;
          if (!n_mapoe && !n_mapwe)                   dec_rd    = 0;
        end

    ok(dec_page,  "/IOPAGE is asserted for $FF00-$FFFF and nowhere else");
    ok(dec_blk,   "the block windows are $FF90-$FF9F and $FFA0-$FFAF, and nowhere else");
    ok(dec_hi,    "$FF90-$FF9F selects the HIGH map byte - physical A24..A21");
    ok(dec_lo,    "$FFA0-$FFAF selects the LOW map byte - physical A20..A13");
    ok(dec_wr,    "/WE only ever asserts inside a block window on a write");
    ok(ctl_out,   "the control latch never strobes outside $FFB0-$FFBF");
    ok(bbm,       "break before make: nothing drives the map SRAM's pins while it drives");
    ok(wr_in_buf, "/WE is only ever asserted while the '245 is enabled");
    ok(dec_rd,    "the map SRAM never drives during a block write");

    trace(16'hFFA0, 1'b0, 2, t); ok(t == "0011", "a block write enables the '245 at E-rise");
    trace(16'hFFA0, 1'b0, 3, t); ok(t == "0001", "/WE is one phase wide, a quarter cycle behind it");
    trace(16'hFFA0, 1'b0, 1, t); ok(t == "1111", "the mux is switched for the whole cycle");
    trace(16'hFFA0, 1'b0, 4, t); ok(t == "0000", "the map SRAM is off for every phase of a block write");
    trace(16'hFFA0, 1'b1, 4, t); ok(t == "0011", "a block read turns the map SRAM back on, E-high only");
    trace(16'h1234, 1'b0, 4, t); ok(t == "1111", "translation is live through an ordinary memory cycle");
    trace(16'hFFB0, 1'b0, 5, t); ok(t == "1100", "the '574 clock falls at E-rise and rises at E-fall");

    // Exactly one rising edge per control write - the bug the first draft had.
    edges = 0;
    drive(16'hFFB0, 2'd3, 1'b0); prev = n_ctrlcp;
    for (int ph = 0; ph < 4; ph++) begin
      drive(16'hFFB0, ph[1:0], 1'b0); cur = n_ctrlcp;
      if (cur && !prev) edges++;
      prev = cur;
    end
    ok(edges == 1, "one rising edge on the '574 clock per control write");

    edges = 0;
    drive(16'hFFB0, 2'd3, 1'b1); prev = n_ctrlcp;
    for (int ph = 0; ph < 4; ph++) begin
      drive(16'hFFB0, ph[1:0], 1'b1); cur = n_ctrlcp;
      if (cur && !prev) edges++;
      prev = cur;
    end
    ok(edges == 0, "no rising edge on a control read");

    if (fails == 0) $display("\nmmu.v OK - 16 claims, exhaustive over the address space");
    else            $display("\n%0d FAILED", fails);
    if (fails != 0) $fatal(1);
    $finish;
  end

endmodule
