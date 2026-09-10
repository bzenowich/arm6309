// The ORACLE half: an independent Paula, playing a buffer, printing bytes.
//
// ⚠ THIS FILE IS OURS. Paula.v is not, is not in this repository, and is
// fetched on demand by fetch-paula.sh - read its header before doing anything
// with it beyond running this locally. The two models are never linked:
// run-oracle.sh builds this and card_oracle_tb.sv as SEPARATE binaries and
// compares their printed output.
//
// ** WHY AN ORACLE AT ALL. audio_tb.sv was written from the same understanding
// that produced the design, so it can only confirm the design does what its
// author thought. On 2026-09-10 that was not a theoretical worry: two audible
// defects (audio.md 16 item 36) survived 43 green claims, a design review and
// a port census, and what found them was this - a second implementation of
// Paula, written by other people from the hardware reference manual, driven
// with the same register writes and diffed.
//
// ** WHAT THE HARNESS HAS TO SUPPLY, and it is the interesting part. Paula
// does NOT fetch its own samples: it raises a data request and AGNUS delivers
// the word and owns the pointer. So the Agnus below is part of the oracle, and
// it is deliberately the simplest thing the hardware reference manual
// describes - a pointer per channel, reloaded from AUDxLC when Paula asserts
// its restart enable, incremented on every request. ⚠ Anything this Agnus gets
// wrong shows up as a difference and must NOT be charged to the card; item 36
// records one such result already (Paula discards the first word fetched after
// DMACON, which is a property of that fetch and not of the audio path).

`default_nettype none

module paula_oracle_tb;

  // 28.37516 MHz, one time unit per half period - the same scale audio_tb uses.
  logic clk = 0;
  always #1 clk = ~clk;

  logic rst = 1;

  // ---- the chipset's clock phases ---------------------------------------
  // 28 MHz master; CDAC_n at 7 MHz; CCK - the colour clock - at 3.5 MHz.
  // Registers move on (cdac_r & cck), once per colour clock; the four audio
  // state machines are multiplexed through the four !cck cycles.
  int unsigned phase = 0;
  always @(posedge clk) phase <= (phase == 7) ? 0 : phase + 1;
  wire clk_28m   = 1'b1;
  wire cck       = (phase < 4);
  wire cdac_r    = (phase == 0) || (phase == 4);
  wire cdac_f    = (phase == 2) || (phase == 6);
  wire cclk_edge = (phase == 7);            // one pulse per colour clock

  // ---- Paula ------------------------------------------------------------
  logic  [8:1] rga_in = 8'h00;
  logic [15:0] db_in  = 16'h0000;
  wire  [15:0] db_out, db_out_er;
  wire         db_oe, dmal, dkwr_n, dkwe, txd, aud_l, aud_r;
  wire   [2:0] ipl_n;

  Paula dut (
    .rst(rst), .clk(clk), .clk_28m(clk_28m), .cck(cck),
    .cdac_r(cdac_r), .cdac_f(cdac_f),
    .cfg_ecs(1'b0), .cfg_a1k(1'b0),
    .rga_in(rga_in), .db_in(db_in), .db_out(db_out), .db_out_er(db_out_er),
    .db_oe(db_oe),
    .int2_n(1'b1), .int3_n(1'b1), .int6_n(1'b1), .ipl_n(ipl_n),
    .rxd(1'b1), .txd(txd), .dmal(dmal),
    .dkrd_n(1'b1), .dkwr_n(dkwr_n), .dkwe(dkwe),
    .aud_l(aud_l), .aud_r(aud_r));

  // ---- the register port -------------------------------------------------
  // "Data bus is latched one cycle after address bus" - Paula.v's own header.
  // The decode latches RGA on one (cdac_r & cck) and the write acts on db_in
  // at the next, so a write is two colour clocks and the address leads.
  // ⛔ ALIGNED TO PHASE 3, AND THE PHASE MATTERS. Paula multiplexes ONE audio
  // state machine across the four channels, and every control output -
  // AUDxDR, dmasen, pbufld, penhi - is a four-bit ROTATING shift register that
  // is shifted once per !cck cycle. It only reads as "bit i belongs to channel
  // i" while cck is high, after all four shifts have completed. Sampling the
  // request line at phase 7, mid-rotation, sees channel 3's bit in channel 0's
  // place and the Agnus never answers: `fetches=0`, which looks exactly like a
  // card that is not asking.
  task automatic cclk(input int n);
    for (int k = 0; k < n; k++) begin
      @(posedge clk);
      while (phase != 3) @(posedge clk);
    end
  endtask

  // ⛔ RGA IS RELEASED BEFORE THE DATA COLOUR CLOCK, AND THE FIRST VERSION DID
  // NOT DO THAT. The decode block re-latches on EVERY (cdac_r & cck), so
  // leaving the address asserted for the data cycle latches the same register
  // a second time - and the colour clock after that writes it again with
  // whatever db_in has fallen back to, which is zero. AUDxLEN and AUDxPER
  // therefore read back 0 while DMACON survived, because DMACON's second write
  // has bit 15 clear and "clear these bits: none" is a no-op. A harness bug
  // that hides itself in three registers out of four is exactly the kind of
  // thing an oracle has to not have.
  task automatic wreg(input int unsigned addr, input logic [15:0] v);
    rga_in = addr[9:1];
    cclk(1);                  // the decode latches RGA here
    rga_in = 8'h00;
    db_in  = v;
    cclk(1);                  // and acts on db_in here
    db_in  = 16'h0000;
  endtask

  // ---- chip RAM ----------------------------------------------------------
  localparam int unsigned LC   = 32'h02000;
  localparam int unsigned LEN  = 2;          // words
  localparam int unsigned PER  = 64;

  logic [7:0] chipram [0:65535];

  // ---- what is compared: channel 0's sample byte -------------------------
  logic [7:0] last;
  int unsigned emitted = 0, fetches = 0, reloads = 0;
  logic started = 0;

  // A monitor, not a driver - so it cannot perturb what it is watching.
  always @(posedge clk) begin
    if (started && dut.r_smpbuf[0] !== last) begin
      last <= dut.r_smpbuf[0];
      emitted <= emitted + 1;
      $display("SAMPLE %0d %02h", emitted + 1, dut.r_smpbuf[0]);
    end
  end

  // ---- the Agnus, and the run --------------------------------------------
  int unsigned aptr;
  logic drprev;
  int unsigned i;

  initial begin
    for (i = 0; i < 65536; i++) chipram[i] = 8'h00;
    // buffer byte b holds b + 2, which is what item 36's measurement used
    for (i = 0; i < 256; i++) chipram[LC + i] = i[7:0] + 8'd2;

    repeat (64) @(posedge clk);
    rst = 0;
    cclk(4);

    $display("");
    $display("Paula - the oracle. LEN = %0d words, PER = %0d, VOL = 64, channel 0.",
             LEN, PER);
    $display("");

    wreg(32'h0A4, LEN[15:0]);
    wreg(32'h0A6, PER[15:0]);
    wreg(32'h0A8, 16'd64);
    wreg(32'h096, 16'h8201);        // DMACON: set, master DMAEN + AUD0

    $display("      after DMACON: DMAEN=%b AUDEN=%b state0=%b LEN=%0d PER=%0d",
             dut.r_DMAEN, dut.r_AUDEN, dut.r_audstate[0], dut.r_AUDxLEN[0], dut.r_AUDxPER[0]);

    last    = dut.r_smpbuf[0];
    started = 1;
    aptr    = LC;
    drprev  = 1'b0;

    // Service Paula's data requests. One word per request; the restart enable
    // reloads the pointer from AUDxLC, exactly as the hardware reference
    // manual describes Agnus doing it.
    // ⚠ NO EDGE DETECTION. Paula holds the request until Agnus answers it, so
    // an Agnus that waits for a rising edge answers once and then waits for
    // ever - which is what `fetches=1` looked like. A DMA slot services the
    // line as it stands; writing AUDxDAT is what clears it.
    for (i = 0; i < 60000 && emitted <= 24; i++) begin
      cclk(1);
      if (dut.r_AUDxDR[0]) begin
        // ⭐ THE RESTART FLAG IS `dmasen | lenfin`, AND IT IS PAULA'S OWN
        // ARITHMETIC, not ours. It is the expression Paula.v puts on the DMAL
        // serial line for Agnus:
        //
        //     r_dmal[7] <= r_AUDxDR[0] & (r_dmasen[0] | r_lenfin[0]);
        //
        // and `r_lenfin` is `r_lenctr == 16'd1`, not zero. ⚠ An Agnus that
        // reloads only on `dmasen` reloads once and then walks off the end of
        // the buffer for ever, playing 04 05 06 07 ... out of whatever follows
        // it in chip RAM. That was this harness's third bug and it is the one
        // that would have been easiest to mistake for a finding.
        if (dut.r_dmasen[0] || dut.r_lenfin[0]) begin
          aptr = LC; reloads = reloads + 1;
        end
        wreg(32'h0AA, {chipram[aptr], chipram[aptr + 1]});
        aptr = aptr + 2;
        fetches = fetches + 1;
      end
    end

    $display("");
    $display("PAULA fetches=%0d reloads=%0d samples=%0d", fetches, reloads, emitted);
    $finish;
  end

endmodule
