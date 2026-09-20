// storage_tb.sv - the SD card as a CARD: storage_card.v's two GALs and six
// discrete packages, driven one 6809E bus cycle at a time, with a real SPI
// card model (sd_model.v) in the socket.  HAND-WRITTEN.
//
// ⭐ WHY THIS EXISTS.  storage.check.ts proves the two term lists compute
// their own equations, which is not the same as the card exchanging a byte:
// every claim about the off-by-one receive pipeline (§6.2), the '574's
// power-up garbage (§6.4), the re-trigger lockout (§6.5) and the two clock
// rates (§3.3) was prose until something clocked a card with them.  Nothing
// here pokes a register - every access is a bus cycle through the $FF58
// decode, which is the only way the seams get exercised.
//
// ⚠ THE RECEIVE PIPELINE IS OFF BY ONE AND THAT IS THE DESIGN (§6.2, §9.1).
// A read of SDDATA returns the byte the PREVIOUS burst shifted in and, as a
// side effect of the same access, starts the burst that fetches the next
// one.  So `spiByte(tx, prev)` hands back the response to the byte BEFORE
// tx, and every sequence below is written the way §9.1's driver is: send,
// then read one byte later than feels right.  Getting this wrong does not
// fail loudly - it shifts a block by one and reads perfectly plausible
// rubbish, which is why §9.1 says to check it against known content.
//
// ⚠ AND THE PACING IS PART OF THE DESIGN TOO.  A burst is 636 ns at the fast
// clock against a 476.7 ns bus cycle, so back-to-back SDDATA accesses WOULD
// hit §6.5's lockout: the margin §6.5 actually claims is the instruction's,
// "a native-mode STA >SDDATA is 4-5 cycles = 1.9-2.4 us against a 0.636 us
// burst".  This bench spends three bus cycles per byte for the same reason,
// and at the 393 kHz init rate it polls SDSTAT b0 exactly as §6.5 requires.
//
// A comment line here must never begin with the simulator's own name.

`default_nettype none

module storage_tb;

  // one CLK25 dot is two time units; the machine's dot is 39.72 ns
  logic CLK25 = 0;
  always #1 CLK25 <= ~CLK25;

  logic        RESETn = 0;
  logic        IOSELn = 1;
  logic [6:0]  A      = 7'h7F;
  logic        RW     = 1;
  logic        E      = 0;
  logic        PORn   = 1;

  logic       tb_oe = 0;
  logic [7:0] tb_d  = 8'h00;
  wire  [7:0] D;
  assign D = tb_oe ? tb_d : 8'hzz;

  wire SD_SCK, SD_MOSI, SD_MISO, SD_CSn, OBS_BUSY, OBS_RCLK;

  storage_card dut (
      .CLK25 (CLK25), .IOSELn (IOSELn), .A (A), .RW (RW), .E (E),
      .RESETn (RESETn), .D (D),
      .SD_SCK (SD_SCK), .SD_MOSI (SD_MOSI), .SD_MISO (SD_MISO),
      .SD_CSn (SD_CSn),
      .CDn (1'b0),          // a card is in the socket
      .WPn (1'b1),          // and its tab is not set
      .OBS_BUSY (OBS_BUSY), .OBS_RCLK (OBS_RCLK)
  );

  sd_model card (
      .PORn (PORn), .SCK (SD_SCK), .MOSI (SD_MOSI), .CSn (SD_CSn),
      .MISO (SD_MISO)
  );

  // ---- claims --------------------------------------------------------------
  int fails = 0, passes = 0;
  task automatic ok(input bit c, input string what);
    if (c) begin passes++; $display("ok    %s", what); end
    else   begin fails++;  $display("FAIL  %s", what); end
  endtask

  // ---- the bus, and who is allowed on it -----------------------------------
  // ⛔ storage_card.v's header says out loud that "exactly one of these may
  // drive at a time" is a claim the testbench makes rather than a property of
  // the board file.  This is that claim, counted every dot from reset on.
  wire card_drv = dut.OE595 | dut.SD0_OE | dut.SD1_OE | dut.SD2_OE;
  wire stat_drv = dut.SD0_OE | dut.SD1_OE | dut.SD2_OE;
  int  d_fights = 0, card_fights = 0;

  /* verilator lint_off BLKSEQ */
  // ---- the burst, watched through the card's own observation pins ----------
  int dotc = 0, cnt_e = 0, t0 = 0;
  int burst_edges = 0, burst_dots = 0, bursts = 0;
  bit sck_d = 0, busy_d = 0;
  always @(posedge CLK25) begin
    dotc = dotc + 1;
    if (RESETn) begin
      if (tb_oe && card_drv)          d_fights    = d_fights + 1;
      if (dut.OE595 && stat_drv)      card_fights = card_fights + 1;
    end
    if (OBS_BUSY && !busy_d) begin cnt_e = 0; t0 = dotc; end
    if (OBS_BUSY && SD_SCK && !sck_d) cnt_e = cnt_e + 1;
    if (!OBS_BUSY && busy_d) begin
      burst_edges = cnt_e; burst_dots = dotc - t0; bursts = bursts + 1;
    end
    sck_d = SD_SCK; busy_d = OBS_BUSY;
  end
  /* verilator lint_on BLKSEQ */

  // ---- one 6809E bus cycle -------------------------------------------------
  // Twelve dots: E low for six, high for six.  E falls one dot before the
  // cycle ends, because that falling edge is the '574's clock (sdbus's MOSICK
  // is E-qualified and storage_card takes its FALLING edge) and a 6809E holds
  // the write data past it - t_DHW.  Release the bus a dot later, never at
  // the edge itself.
  task automatic cycle(input logic [6:0] a, input bit rw, input logic [7:0] wd,
                       output logic [7:0] q);
    A = a; RW = rw; IOSELn = 1'b0; tb_oe = ~rw; tb_d = wd;
    repeat (5) @(negedge CLK25);
    E = 1;
    repeat (5) @(negedge CLK25);
    q = D;
    @(negedge CLK25);
    E = 0;
    @(negedge CLK25);
    tb_oe = 1'b0; IOSELn = 1'b1; RW = 1'b1; A = 7'h7F;
  endtask

  task automatic idle(input int n);
    tb_oe = 1'b0; IOSELn = 1'b1; RW = 1'b1; A = 7'h7F; E = 1'b0;
    repeat (12 * n) @(negedge CLK25);
  endtask

  // §6.1: the decode is A6..A0, and $FF58-$FF5B is four bytes of it
  localparam logic [6:0] SDDATA = 7'h58, SDSTAT = 7'h59,
                         SDCTRL = 7'h5A, SDMOSI = 7'h5B;

  task automatic wr(input logic [6:0] a, input logic [7:0] v);
    logic [7:0] q;
    cycle(a, 1'b0, v, q);
  endtask
  task automatic rd(input logic [6:0] a, output logic [7:0] v);
    cycle(a, 1'b1, 8'h00, v);
  endtask

  // ---- pacing: §6.5's two rules, one per clock rate ------------------------
  bit fastclk = 0;
  int poll_max = 0;
  int r1_reads = 0;      // reads from the sixth command byte to R1

  // At 393 kHz a burst is 20.4 us = 43 bus cycles and MUST be polled.  ⚠ And
  // the poll has to see BUSY GO UP first: the trigger sets an internal
  // pending flag at E-fall but BUSY does not rise until SPICLK's next falling
  // edge, which at the init rate is up to 2.54 us - five bus cycles - later.
  // A driver that polls "until BUSY is clear" and nothing else walks straight
  // through that window and reads the byte before last.  Bounded, and loud.
  task automatic wait_burst(input string what);
    logic [7:0] s;
    int n; bit seen;
    seen = 0; n = 0;
    forever begin
      rd(SDSTAT, s);
      if (s[0]) seen = 1;
      else if (seen) break;
      n = n + 1;
      if (n > 400) begin
        ok(0, $sformatf("burst finishes (%s): BUSY never %s after %0d polls",
                        what, seen ? "cleared" : "set", n));
        return;
      end
    end
    if (n > poll_max) poll_max = n;
  endtask

  task automatic pace(input string what);
    if (fastclk) idle(2);        // three bus cycles a byte - see the header
    else wait_burst(what);
  endtask

  // ---- the three SPI primitives §6.2 gives the driver ----------------------
  // ⚠ Every one of them returns the PREVIOUS burst's byte.  spiByte is the
  // general form: SDMOSI sets DI without consuming a byte time, then the
  // SDDATA read hands back what came in last time and starts the burst that
  // sends `tx`.
  task automatic spiByte(input logic [7:0] tx, output logic [7:0] prev);
    wr(SDMOSI, tx);
    rd(SDDATA, prev);
    pace("spiByte");
  endtask

  // sending a command byte: a write to SDDATA loads the hold register and
  // triggers in one access (§6.2), and what came back is discarded
  task automatic sdSend(input logic [7:0] tx);
    wr(SDDATA, tx);
    pace("send");
  endtask

  // receiving: DI is already $FF, so no write is needed and the read is the
  // whole transaction
  task automatic sdRecv(output logic [7:0] prev);
    rd(SDDATA, prev);
    pace("recv");
  endtask

  // ---- a command, and §9.1 steps 2-4 ---------------------------------------
  task automatic sd_cmd(input logic [5:0] c, input logic [31:0] arg,
                        input logic [7:0] crc, output logic [7:0] r1);
    int n;
    sdSend({2'b01, c});
    sdSend(arg[31:24]); sdSend(arg[23:16]); sdSend(arg[15:8]); sdSend(arg[7:0]);
    sdSend(crc);
    wr(SDMOSI, 8'hFF);          // §9.1 step 3, and it is where it is on purpose
    r1 = 8'hFF; n = 0;
    while (r1 == 8'hFF && n < 24) begin sdRecv(r1); n = n + 1; end
    r1_reads = n;
  endtask

  // ---- the scenarios --------------------------------------------------------
  logic [7:0] q, r1, tok, c0, c1, dr;
  logic [7:0] ocr [0:3];
  logic [7:0] ifc [0:3];
  logic [7:0] wdat [0:511];
  int i, n, bad, blk, nb;
  logic [15:0] crcexp;
  int slow_edges, slow_dots, fast_edges, fast_dots;
  bit neg_idle;

  function automatic logic [15:0] crc16b(input logic [15:0] c, input logic [7:0] d);
    logic [15:0] cc;
    cc = c;
    for (int k = 0; k < 8; k++)
      cc = {cc[14:0], 1'b0} ^ ((cc[15] ^ d[7-k]) ? 16'h1021 : 16'h0000);
    return cc;
  endfunction

  initial begin
    repeat (20) @(negedge CLK25);
    RESETn = 1;
    repeat (20) @(negedge CLK25);

    // ================================================== 1. the reset state
    // §6.4: a GAL22V10's registers power up reset and /RESET forces $00, and
    // both of SDCTRL's live bits are defined active-high so that $00 is the
    // safe one - /CS released, init clock.
    ok(SD_CSn === 1'b1, "out of reset SDCTRL is $00 in effect: /CS is released");
    ok(dut.FAST === 1'b0, "and the 393 kHz init clock is selected, not 12.588 MHz");
    rd(SDSTAT, q);
    ok(q === 8'h02,
       $sformatf("SDSTAT reads CD set, WP and BUSY clear, b3-b7 zero (got $%02h)", q));

    // ============================== 2. the negative control for the 74 clocks
    // ⭐ THIS RUNS FIRST, BEFORE ANY WRITE TO SDMOSI, because that is the only
    // way the '574 still holds its power-up value.  §6.4: the part has no MR
    // pin, storage_card.v powers it up holding $00 on purpose, and a driver
    // that goes straight to CMD0 therefore clocks 80 bits of DI LOW at a card
    // that is waiting for 74 high ones.
    ok(SD_MOSI === 1'b0, "the '574 powers up holding $00, so DI is LOW");
    for (i = 0; i < 10; i++) sdRecv(q);
    ok(card.initclk == 0,
       $sformatf("ten bare SDDATA reads give the card ZERO valid init clocks (%0d)",
                 card.initclk));
    ok(card.power_ok === 1'b0, "so the card has not seen SD's power-up sequence");
    wr(SDCTRL, 8'h01);                       // /CS low, still the init clock
    sd_cmd(6'd0, 32'h0000_0000, 8'h95, r1);
    neg_idle = (r1 == 8'h01);
    ok(!neg_idle,
       $sformatf("⭐ CMD0 without §9.0 step 1's SDMOSI <- $FF does NOT reach idle (R1 $%02h)", r1));
    ok(card.bad_powerup === 1'b1, "and the card recorded the power-up violation");
    ok(card.card_up === 1'b0, "the card never entered SPI mode");
    wr(SDCTRL, 8'h00);                       // /CS high again

    // ================================================== 3. a fresh card, done right
    PORn = 0; repeat (8) @(negedge CLK25); PORn = 1;
    RESETn = 0; repeat (8) @(negedge CLK25); RESETn = 1;
    repeat (8) @(negedge CLK25);

    wr(SDMOSI, 8'hFF);                       // §9.0 step 1
    ok(SD_MOSI === 1'b1, "SDMOSI <- $FF puts DI high with no clock issued");
    for (i = 0; i < 10; i++) sdRecv(q);      // §9.0 step 2: 80 >= 74 clocks
    ok(card.initclk >= 74,
       $sformatf("ten SDDATA reads with /CS high give >= 74 init clocks (%0d)",
                 card.initclk));
    ok(card.power_ok === 1'b1, "and the card accepts the power-up sequence");
    slow_edges = burst_edges; slow_dots = burst_dots;
    ok(slow_edges == 8,
       $sformatf("one access is exactly eight SCK edges (%0d)", slow_edges));
    ok(slow_dots > 400,
       $sformatf("at the init rate a burst is %0d dots - 43 bus cycles, so it is polled",
                 slow_dots));

    // ================================================== 4. §9.0, all of it
    wr(SDCTRL, 8'h01);                       // /CS low
    sd_cmd(6'd0, 32'h0000_0000, 8'h95, r1);
    ok(r1 == 8'h01, $sformatf("CMD0 GO_IDLE_STATE -> R1 $01 (got $%02h)", r1));
    ok(card.crc0_bad === 1'b0, "and it went out with CRC $95, which CMD0 is checked on");
    // ⭐ WHERE R1 LANDS IS THE WHOLE PIPELINE, IN ONE NUMBER.  The first read
    // after the sixth command byte returns the byte the card sent DURING it -
    // that is §6.2's off-by-one on the receive side, and it is the design.
    // Two more are the model's N_CR.  A fourth read is R1.  A '165 that took
    // its parallel load at the END of a burst instead of tracking U5 while
    // BUSY is low delays the whole MOSI stream by a byte and moves R1 to the
    // fifth - which is exactly the defect this bench found in storage_card.v
    // on 2026-09-20, and it is silent everywhere else because the card keys
    // off tokens and not counts.
    ok(r1_reads == 4,
       $sformatf("R1 is the 4th read after the sixth command byte: receive off by one, transmit by none (%0d)",
                 r1_reads));

    sd_cmd(6'd8, 32'h0000_01AA, 8'h87, r1);
    for (i = 0; i < 4; i++) sdRecv(ifc[i]);
    ok(r1 == 8'h01, $sformatf("CMD8 SEND_IF_COND -> R1 $01 (got $%02h)", r1));
    ok(ifc[0] == 8'h00 && ifc[1] == 8'h00 && ifc[2] == 8'h01 && ifc[3] == 8'hAA,
       $sformatf("and R7 echoes $1AA: %02h %02h %02h %02h",
                 ifc[0], ifc[1], ifc[2], ifc[3]));
    ok(card.crc8_bad === 1'b0, "CMD8's mandatory CRC $87 was correct");

    n = 0;
    r1 = 8'h01;
    while (r1 != 8'h00 && n < 10) begin
      sd_cmd(6'd55, 32'h0000_0000, 8'h01, r1);
      if (r1[3:0] > 4'h1) begin
        ok(0, $sformatf("CMD55 APP_CMD -> R1 $%02h", r1));
        n = 99;
      end else begin
        sd_cmd(6'd41, 32'h4000_0000, 8'h01, r1);
        n = n + 1;
      end
    end
    ok(r1 == 8'h00 && n < 10,
       $sformatf("⭐ the ACMD41 loop leaves idle after %0d iterations (R1 $%02h)", n, r1));
    ok(n > 1, "and it really looped - a driver that sent ACMD41 once would have failed");

    sd_cmd(6'd58, 32'h0000_0000, 8'h01, r1);
    for (i = 0; i < 4; i++) sdRecv(ocr[i]);
    ok(r1 == 8'h00, $sformatf("CMD58 READ_OCR -> R1 $00 (got $%02h)", r1));
    ok(ocr[0][6] === 1'b1,
       $sformatf("and CCS is set: SDHC, block addressing (OCR %02h%02h%02h%02h)",
                 ocr[0], ocr[1], ocr[2], ocr[3]));

    // ================================ 5. §9.0 step 8: up to the transfer clock
    // The rate changes with /CS HIGH and BUSY low, then eight dummy clocks at
    // each rate - §3.3's ripple-counter rule.
    wr(SDMOSI, 8'hFF);
    wr(SDCTRL, 8'h00);
    sdRecv(q);
    wr(SDCTRL, 8'h02);
    fastclk = 1;
    sdRecv(q);
    fast_edges = burst_edges; fast_dots = burst_dots;
    ok(fast_edges == 8,
       $sformatf("at 12.588 MHz a burst is still exactly eight SCK (%0d)", fast_edges));
    // ⚠ 636 ns against a 476.7 ns bus cycle: the burst is LONGER than one bus
    // cycle, not shorter.  §6.5's margin is the instruction's 4-5 E cycles,
    // which is what `pace` above spends.
    ok(fast_dots > 15 && fast_dots < 24,
       $sformatf("and it takes %0d dots - 1.33 bus cycles, vs %0d at the init rate",
                 fast_dots, slow_dots));
    ok(slow_dots > 20 * fast_dots,
       $sformatf("the two rates really are a factor of 32 apart (%0d / %0d)",
                 slow_dots, fast_dots));

    // ============================================ 6. §9.1: CMD17, one block
    wr(SDCTRL, 8'h03);                       // /CS low, fast clock
    sd_cmd(6'd17, 32'd3, 8'hFF, r1);
    ok(r1 == 8'h00, $sformatf("CMD17 READ_SINGLE_BLOCK block 3 -> R1 $00 (got $%02h)", r1));
    tok = 8'hFF; n = 0;
    while (tok == 8'hFF && n < 64) begin sdRecv(tok); n = n + 1; end
    ok(tok == 8'hFE, $sformatf("the data token $FE arrives (got $%02h after %0d reads)",
                               tok, n));
    bad = 0; crcexp = 16'h0000;
    for (i = 0; i < 512; i++) begin
      sdRecv(q);
      crcexp = crc16b(crcexp, q);
      if (q !== card.peek(3, i)) begin
        if (bad == 0)
          $display("      first wrong: byte %0d got $%02h want $%02h",
                   i, q, card.peek(3, i));
        bad = bad + 1;
      end
    end
    ok(bad == 0,
       $sformatf("⭐ all 512 bytes of block 3 arrive, in order, unshifted (%0d wrong)", bad));
    sdRecv(c0); sdRecv(c1);
    ok({c0, c1} == crcexp,
       $sformatf("and the two CRC16 bytes are the card's CRC over exactly those 512 (%04h vs %04h)",
                 {c0, c1}, crcexp));
    wr(SDCTRL, 8'h02);                       // §9.1 step 9: /CS high,
    sdRecv(q);                               // then eight idle clocks

    // ============================================ 7. §9.2: CMD24, and read back
    for (i = 0; i < 512; i++) wdat[i] = 8'((i * 11 + 77) & 8'hFF);
    bad = 0;
    for (i = 0; i < 512; i++) if (wdat[i] !== card.peek(5, i)) bad = bad + 1;
    ok(bad > 400,
       $sformatf("the bytes about to be written differ from what block 5 holds (%0d of 512)",
                 bad));

    wr(SDCTRL, 8'h03);
    sd_cmd(6'd24, 32'd5, 8'hFF, r1);
    ok(r1 == 8'h00, $sformatf("CMD24 WRITE_BLOCK block 5 -> R1 $00 (got $%02h)", r1));
    sdRecv(q);                               // §9.2 step 4: one idle byte
    sdSend(8'hFE);                           // the start token
    for (i = 0; i < 512; i++) sdSend(wdat[i]);
    sdSend(8'hFF); sdSend(8'hFF);            // the two CRC16 bytes: clocks only
    wr(SDMOSI, 8'hFF);
    dr = 8'hFF; n = 0;
    while (dr == 8'hFF && n < 16) begin sdRecv(dr); n = n + 1; end
    ok((dr & 8'h1F) == 8'h05,
       $sformatf("the data-response token says accepted (got $%02h)", dr));
    n = 0; q = 8'h00;
    while (q != 8'hFF && n < 400) begin sdRecv(q); n = n + 1; end
    ok(q == 8'hFF && n < 400,
       $sformatf("the program busy phase releases DO after %0d byte times", n));
    ok(n > 1, "and the card really held DO low - the busy poll was not vacuous");
    wr(SDCTRL, 8'h02); sdRecv(q);

    wr(SDCTRL, 8'h03);
    sd_cmd(6'd17, 32'd5, 8'hFF, r1);
    ok(r1 == 8'h00, $sformatf("CMD17 block 5 back -> R1 $00 (got $%02h)", r1));
    tok = 8'hFF; n = 0;
    while (tok == 8'hFF && n < 64) begin sdRecv(tok); n = n + 1; end
    ok(tok == 8'hFE, $sformatf("its data token arrives (got $%02h)", tok));
    bad = 0;
    for (i = 0; i < 512; i++) begin
      sdRecv(q);
      if (q !== wdat[i]) begin
        if (bad == 0)
          $display("      first wrong: byte %0d got $%02h want $%02h", i, q, wdat[i]);
        bad = bad + 1;
      end
    end
    ok(bad == 0,
       $sformatf("⭐ read-after-write through the real hardware path: 512 bytes (%0d wrong)",
                 bad));
    sdRecv(c0); sdRecv(c1);
    wr(SDCTRL, 8'h02); sdRecv(q);

    // ==================================== 8. §9.1.1: CMD18, three blocks, CMD12
    wr(SDCTRL, 8'h03);
    sd_cmd(6'd18, 32'd8, 8'hFF, r1);
    ok(r1 == 8'h00, $sformatf("CMD18 READ_MULTIPLE_BLOCK from block 8 -> R1 $00 (got $%02h)", r1));
    bad = 0;
    for (blk = 8; blk <= 10; blk++) begin
      tok = 8'hFF; n = 0;
      while (tok == 8'hFF && n < 64) begin sdRecv(tok); n = n + 1; end
      if (tok != 8'hFE) begin
        ok(0, $sformatf("block %0d's data token (got $%02h)", blk, tok));
        bad = bad + 1000;
      end
      crcexp = 16'h0000;
      for (i = 0; i < 512; i++) begin
        sdRecv(q);
        crcexp = crc16b(crcexp, q);
        if (q !== card.peek(blk, i)) begin
          if (bad == 0)
            $display("      first wrong: block %0d byte %0d got $%02h want $%02h",
                     blk, i, q, card.peek(blk, i));
          bad = bad + 1;
        end
      end
      sdRecv(c0); sdRecv(c1);
      if ({c0, c1} != crcexp) bad = bad + 1;
    end
    ok(bad == 0,
       $sformatf("⭐ three consecutive blocks stream on one command: 1536 bytes (%0d wrong)",
                 bad));

    // §9.1.1 step 5: CMD12, and the one stuff byte the pipeline puts in front
    // of it.  ⚠ The first read after the sixth command byte returns the byte
    // the card was still STREAMING - it is discarded, not polled on.
    sdSend(8'h4C); sdSend(8'h00); sdSend(8'h00); sdSend(8'h00); sdSend(8'h00);
    sdSend(8'hFF);
    wr(SDMOSI, 8'hFF);
    sdRecv(q);                               // the in-flight stream byte
    r1 = 8'hFF; n = 0;
    while (r1 == 8'hFF && n < 24) begin sdRecv(r1); n = n + 1; end
    ok(r1 == 8'h00, $sformatf("CMD12 STOP_TRANSMISSION -> R1 $00 (got $%02h)", r1));
    n = 0; q = 8'h00;
    while (q != 8'hFF && n < 64) begin sdRecv(q); n = n + 1; end
    ok(q == 8'hFF && n < 64,
       $sformatf("and its R1b busy phase releases after %0d byte times", n));
    wr(SDCTRL, 8'h02); sdRecv(q);

    // ============================== 11. §6.5: the re-trigger lockout, on purpose
    // ⛔ THE WORST FAILURE ON THIS CARD, per §6.5: an SDDATA access arriving
    // mid-burst that reloaded the '163 would truncate the burst to fewer than
    // eight clocks, and host and card would disagree about the bit position
    // for the rest of the session - permanently, and silently.  The '163's
    // /CLR is wired to BUSY so the reload cannot happen; what the software
    // sees instead is a DUPLICATED byte.  Everything above paces its accesses
    // so that this never arises; this deliberately does not.
    wr(SDCTRL, 8'h03);
    sd_cmd(6'd17, 32'd1, 8'hFF, r1);
    tok = 8'hFF; n = 0;
    while (tok == 8'hFF && n < 64) begin sdRecv(tok); n = n + 1; end
    ok(tok == 8'hFE, $sformatf("CMD17 block 1: the data token arrives (got $%02h)", tok));
    sdRecv(q);
    ok(q == card.peek(1, 0), $sformatf("and byte 0 is $%02h", q));
    nb = bursts;
    rd(SDDATA, c0);            // paced normally by what came before
    rd(SDDATA, c1);            // ⛔ the very next bus cycle - 476.7 ns into a 636 ns burst
    idle(3);
    ok(c0 == card.peek(1, 1),
       $sformatf("the first of a back-to-back pair returns its byte (got $%02h)", c0));
    ok(bursts == nb + 1,
       $sformatf("⭐ the mid-burst trigger is DROPPED, not queued: one burst, not two (%0d)",
                 bursts - nb));
    ok(burst_edges == 8,
       $sformatf("and the '163, held clear by BUSY, could not be reloaded - still eight clocks (%0d)",
                 burst_edges));
    ok(c1 == c0,
       $sformatf("⭐ so the locked-out read returns the PREVIOUS byte again - a duplicate, not a framing error ($%02h)",
                 c1));
    sdRecv(q);
    ok(q == card.peek(1, 2),
       $sformatf("⭐ and host and card still agree on the bit position afterwards (got $%02h, want $%02h)",
                 q, card.peek(1, 2)));
    wr(SDCTRL, 8'h02); sdRecv(q);

    // ==================================================== 9 and 10: the gates
    ok(d_fights == 0,
       $sformatf("never two drivers on D7..D0 - the board and the bus master (%0d dots)",
                 d_fights));
    ok(card_fights == 0,
       $sformatf("and never the '595 and SDSTAT at once (%0d dots)", card_fights));
    ok(card.bytes_seen > 2000,
       $sformatf("⭐ %0d bytes were actually exchanged with the card", card.bytes_seen));
    ok(bursts > 2000,
       $sformatf("and the engine ran %0d bursts, every one of them eight clocks",
                 bursts));
    // CMD0 CMD8 3x(CMD55 ACMD41) CMD58 CMD17 CMD24 CMD17 CMD18 CMD12 CMD17.
    // The negative control's refused CMD0 is not among them: the card was
    // power cycled after it, which is the point of the power cycle.
    ok(card.cmds_seen == 15,
       $sformatf("fifteen commands reached the card after the power cycle (%0d)",
                 card.cmds_seen));
    $display("      longest SDSTAT poll at the init rate: %0d reads", poll_max);

    $display("\n%0d claims, %0d failed", passes + fails, fails);
    $finish;
  end

  // a hang is worse than a failure: bound the whole run
  initial begin
    #40000000;
    $display("FAIL  the bench did not finish");
    $display("\n%0d claims, %0d failed", passes + fails + 1, fails + 1);
    $finish;
  end

endmodule
`default_nettype wire
