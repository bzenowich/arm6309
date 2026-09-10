// The CARD half of the differential oracle: this card, playing the same
// buffer, printing the same stream.
//
// ⚠ IT IS A SEPARATE BINARY FROM paula_oracle_tb.sv AND ALWAYS WILL BE.
// run-oracle.sh builds each on its own and diffs the printed output. That is
// cleaner legally - Paula.v's licensing is unsettled and nothing here links
// against it - and it is better testing, because neither model can reach into
// the other and no shared harness bug can cancel out in both.
//
// ** WHAT IS COMPARED. The byte at the sample converter's port - `DACSAMP0`,
// which is what an AD7528 would actually latch - printed as `SAMPLE n xx` on
// every change. Paula's side prints the byte in its own sample register.
// Neither is an analogue measurement and neither is meant to be: 16 item 36's
// two defects were both errors in WHICH BYTES ARE PLAYED AND HOW MANY, which
// is a property of the digital path alone.
//
// ⚠ SAMPLES ARE LOADED RAW, not offset-binary. 6.1 has the loader flip bit 7
// on the way into card RAM and the converter unflip it in the analogue domain;
// flipping here would compare the card's coding against Paula's rather than
// the card's SEQUENCING against Paula's, which is the question.

`default_nettype none

module card_oracle_tb;

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
  wire [7:0] DACSAMP0, DACSAMP1, DACSAMP2, DACSAMP3;
  wire [7:0] DACVOL0, DACVOL1, DACVOL2, DACVOL3;

  audio_card card (.*);

  // ---- the host port, at E rate (9.4: asynchronous to the card) ----------
  task automatic idle(); IOSEL = 0; RW = 1; hostDrv = 0; A = 7'h00; endtask

  task automatic wrraw(input int addr, input logic [7:0] v);
    @(negedge SLOTCLK); IOSEL = 1; A = addr[6:0]; RW = 0; hostD = v; hostDrv = 1;
    repeat (3) @(negedge SLOTCLK);
    E = 1;
    repeat (7) @(negedge SLOTCLK);
    E = 0; @(negedge SLOTCLK); idle();
    repeat (24) @(negedge SLOTCLK);
  endtask

  task automatic wr(input int off, input logic [7:0] v);
    wrraw(7'h40 | off[3:0], v);
  endtask

  // ⚠ ADATA IS FLOW-CONTROLLED. There is one posted-write latch and ASTAT b6
  // says whether it is free; a write while it is high is an overrun the card
  // drops and flags. Bounded, per CLAUDE.md's fifth trap - an unbounded wait
  // would hang rather than fail.
  task automatic pwwait();
    int w; w = 0;
    while (card.u2.PWBUSY === 1'b1 && w < 4096) begin @(posedge SLOTCLK); w++; end
    if (w >= 4096) $display("FAIL  PWBUSY never cleared");
  endtask
  task automatic aidx(input int v);  pwwait(); wr('h0, v[7:0]); endtask
  task automatic adata(input logic [7:0] v); pwwait(); wr('h1, v); endtask

  localparam int unsigned LC  = 32'h02000;
  localparam int unsigned LEN = 2;
  localparam int unsigned PER = 64;

  logic [7:0] last;
  int unsigned emitted = 0;
  logic started = 0;
  int i;

  // A monitor, not a driver.
  always @(posedge SLOTCLK) begin
    if (started && DACSAMP0 !== last) begin
      last <= DACSAMP0;
      emitted <= emitted + 1;
      $display("SAMPLE %0d %02h   (PTR=%05h CNT=%0d)", emitted + 1, DACSAMP0,
               {card.SF[2][18:16], card.SF[2][15:0]},
               {card.SF[1][16], card.SF[1][15:0]});
    end
  end

  initial begin
    // The same buffer Paula's chip RAM holds: byte b is b + 2.
    for (i = 0; i < 256; i++) card.SRAM[LC + i] = i[7:0] + 8'd2;

    repeat (10) @(posedge SLOTCLK);
    RESET = 0;
    repeat (40) @(posedge SLOTCLK);

    $display("");
    $display("arm6309 audio card. LEN = %0d words, PER = %0d, VOL = 64, channel 0.",
             LEN, PER);
    $display("");

    wr('h5, 8'h80);                                // ACTRL: master enable
    aidx(0);
    adata(8'h00); adata(8'h20); adata(8'h00);      // LC = $02000, commits on the low byte
    adata(8'h00); adata(8'h02);                    // LEN = 2 words
    adata(8'h00); adata(8'h40);                    // PER = 64
    adata(8'h40);                                  // VOL = 64
    if (card.SF[3][18:0] !== LC[18:0] || card.SF[5][15:0] !== 16'(LEN)
        || card.SF[4][15:0] !== 16'(PER))
      $display("FAIL  setup did not land: LC=%05h LEN=%0d PER=%0d",
               card.SF[3][18:0], card.SF[5][15:0], card.SF[4][15:0]);

    last    = DACSAMP0;
    started = 1;
    wr('h2, 8'h81);                                // ADMACON: set, channel 0

    for (i = 0; i < 400000 && emitted <= 24; i++) @(posedge SLOTCLK);

    $display("");
    $display("CARD samples=%0d", emitted);
    $finish;
  end

endmodule
