// storage_card.v - the SD card over SPI, as a board: two GAL22V10s and the
// six discrete packages around them.  HAND-WRITTEN; sdbus.v and sdeng.v are
// generated from the term lists in ../storage/*.jedec.ts and must not be.
//
// ** THE CARD (storage/docs/sdcard.md §3.1, NormalLuser's BE6502 interface).
// A read of SDDATA puts the byte the previous burst shifted in onto the bus
// AND starts the burst that fetches the next one.  Software never counts a
// clock and never polls in the fast path; a 512-byte block is a `TFM` loop
// in 32-byte chunks with interrupts masked (§4.4), 537 KiB/s.
//
// ** THE PACKAGES, and which of them is the one to get wrong:
//
//   U1 GAL22V10  sdbus - the $FF58 decode, four strobes, SDSTAT's three bits
//   U2 GAL22V10  sdeng - SDCTRL, and the eight-clock burst engine
//   U3 74HCT595  MISO shift + storage, three-stated onto D0-D7
//   U4 74HC165   MOSI shift, parallel-loaded from U5 while BUSY is low
//   U5 74HC574   the MOSI hold register - ⚠ NO CLEAR INPUT, see below
//   U6 74HC163   the burst counter: /CLR wired to BUSY, Q3 is the 8th clock
//   U7 74HC393   the clock divider: /2 = 12.588 MHz, /64 = 393 kHz init
//   U8 74LVC125  3.3 V level shift for SCK, MOSI and /CS (not modelled)
//
// ⚠ U5 POWERS UP HOLDING GARBAGE and there is nothing on the card that can
// clear it (§6.4): a '574 has no MR pin.  This model therefore powers it up
// holding $00 ON PURPOSE - the value that breaks SD's power-up rule, which
// wants DI high for 74 clocks - so a driver that forgets §9.0 step 1's write
// to SDMOSI fails here instead of on the bench.
//
// ⚠ EVERY GAL SIGNAL IS IN ASSERTED SENSE and this file does the inverting,
// which is the convention `npm run check:pins` exists to police: emit.ts
// writes the equations as the term lists mean them, and a pin that is low
// when asserted is inverted HERE, once.
`default_nettype none

module storage_card (
    // the backplane (machine.md §2)
    input  wire       CLK25,
    input  wire       IOSELn,     // /IOPAGE & /A7 - the $FF00-$FF7F window
    input  wire [6:0] A,          // A6..A0
    input  wire       RW,
    input  wire       E,
    input  wire       RESETn,
    inout  wire [7:0] D,

    // the socket
    output wire       SD_SCK,
    output wire       SD_MOSI,
    input  wire       SD_MISO,
    output wire       SD_CSn,
    input  wire       CDn,        // card detect, closed to ground
    input  wire       WPn,        // write protect, likewise

    // ⭐ observation only - a testbench watches the burst without reaching
    // inside a module.  Nothing on the board is wired to these.
    output wire       OBS_BUSY,
    output wire       OBS_RCLK,
    // ⭐ and WHETHER THE CARD IS DRIVING D7..D0 at all, added 2026-09-21 when
    // machine3.v took the real card in place of its $FF59 stub.  A machine
    // that resolves its bus from explicit drivers (design-review2.md §10 -
    // "a model that ORs its drivers cannot see a bus fight") needs the card
    // to SAY when it is on the bus rather than restating the card's decode
    // in the board above it, which is the divergence video3 pays this same
    // price to avoid.
    output wire       OBS_DOE
);

  // ---- U7, the 74HC393 divider ------------------------------------------
  // Free-running off the backplane master; the card has no oscillator (§3.3).
  reg [5:0] div = 6'd0;
  always @(posedge CLK25) div <= div + 6'd1;
  wire DIV2  = div[0];   // 12.588 MHz
  wire DIV64 = div[5];   // 393 kHz, inside SD's 400 kHz init ceiling

  // ---- U1, sdbus --------------------------------------------------------
  wire DATSTB, RDST, CTRLW, OE595, MOSICK, SD0, SD1, SD2;
  wire SD0_OE, SD1_OE, SD2_OE;
  wire BUSY, TRIGP;

  sdbus u1 (
      .IOSEL (~IOSELn),
      .A6 (A[6]), .A5 (A[5]), .A4 (A[4]), .A3 (A[3]), .A2 (A[2]),
      .A1 (A[1]), .A0 (A[0]),
      .RW (RW), .E (E),
      .BUSY (BUSY), .TRIGP (TRIGP),
      .CD (~CDn), .WP (~WPn),
      .DATSTB (DATSTB), .RDST (RDST), .CTRLW (CTRLW),
      .OE595 (OE595), .MOSICK (MOSICK),
      .SD0 (SD0), .SD1 (SD1), .SD2 (SD2),
      .SD0_OE (SD0_OE), .SD1_OE (SD1_OE), .SD2_OE (SD2_OE)
  );

  // ---- U6, the 74HC163 burst counter ------------------------------------
  // ⭐ /CLR IS WIRED TO BUSY, which is §6.5's re-trigger lockout made
  // structural: while BUSY is low the counter is held at zero on every
  // SPICLK edge, so an access arriving mid-burst cannot reload it.  From the
  // instant BUSY rises it counts 1..8 and Q3 is the eighth clock.
  wire SPICLK;
  reg [3:0] cnt = 4'd0;
  always @(posedge SPICLK) cnt <= BUSY ? cnt + 4'd1 : 4'd0;
  wire CNT8 = cnt[3];

  // ---- U2, sdeng --------------------------------------------------------
  wire CS, FAST, SPQ, DATQ, SCK, SCKN, RCLK;

  sdeng u2 (
      .CLK (CLK25),
      .RESET (~RESETn),
      .CTRLW (CTRLW), .DATSTB (DATSTB),
      .DIV2 (DIV2), .DIV64 (DIV64), .CNT8 (CNT8),
      .D0 (D[0]), .D1 (D[1]), .D7 (D[7]),
      .CS (CS), .FAST (FAST),
      .SPICLK (SPICLK), .SPQ (SPQ),
      .DATQ (DATQ), .TRIGP (TRIGP), .BUSY (BUSY),
      .SCK (SCK), .SCKN (SCKN), .RCLK (RCLK)
  );

  // ---- U5, the 74HC574 MOSI hold register --------------------------------
  // Clocked by MOSICK's RISING edge, which the term list puts at E-fall so
  // the byte is latched before the burst it triggered can start (§6.2).
  // ⚠ $00 at power-up on purpose - see the header.
  // The PIN is low while MOSICK is asserted, so the pin's rising edge is
  // this signal's falling one.  Written as `negedge MOSICK` rather than
  // through an inverted alias, because an alias is a wire nothing reads and
  // `check:reach` is right to say so.
  reg [7:0] hold = 8'h00;
  always @(negedge MOSICK) hold <= D;

  // ---- U4, the 74HC165 MOSI shifter --------------------------------------
  // SH//LD is wired to BUSY: low while idle, so the shifter tracks U5 and
  // MOSI already carries bit 7 when the first SCK edge arrives.
  // ⭐ CLOCKED BY SCKN, NOT SCK - §6.6's robust form, taken 2026-09-20.  The
  // pin is the complement of the gated clock, so its rising edge is SCK's
  // FALLING one: DI changes there and is stable for a full half period,
  // 39.7 ns, before the card samples it on the rising edge.  The form it
  // replaces had both happening at the same instant and rested on the
  // '165's unspecified MINIMUM propagation delay.
  // ⚠ SYNCASYNCNET is waived HERE AND NOWHERE ELSE, and the warning is
  // right about the fact: BUSY is a synchronous term in U6's clear and an
  // asynchronous one in U4's SH//LD.  That is what the board does - one GAL
  // output fans out to a '163's /CLR and a '165's SH//LD - so it is the
  // design and not a slip.  What makes it safe is that BUSY only ever
  // changes on SPICLK's falling edge (sdeng's FALL), so neither part sees it
  // move near its own clock edge.
  // ⚠ SH//LD LOW IS A TRANSPARENT PARALLEL LOAD, NOT AN EDGE.  A '165 with
  // SH//LD low follows its parallel inputs continuously and only begins to
  // hold from the instant the pin goes high, which is what "tracks U5" above
  // means.  Loading on `negedge BUSY` alone models a part that samples U5 at
  // the END of the previous burst, so every burst shifts out the byte before
  // the one software just wrote - a whole-byte delay of the MOSI stream,
  // silent because the card keys off tokens rather than counts (found by
  // storage_tb, 2026-09-20).  `preload` is the transparency: until this
  // burst's first SCK edge the shifter presents U5, and the first shift takes
  // its source from U5 too.
  /* verilator lint_off SYNCASYNCNET */
  reg [7:0] mosi_sr = 8'hFF;
  reg       preload = 1'b1;
  always @(negedge SCKN or negedge BUSY) begin
    if (!BUSY) preload <= 1'b1;
    else begin
      mosi_sr <= {(preload ? hold[6:0] : mosi_sr[6:0]), 1'b1};
      preload <= 1'b0;
    end
  end
  /* verilator lint_on SYNCASYNCNET */
  assign SD_MOSI = (BUSY && !preload) ? mosi_sr[7] : hold[7];

  // ---- U3, the 74HCT595 MISO shifter + storage ---------------------------
  // SRCLK is SCK; the storage register takes the byte when RCLK is RELEASED
  // at the end of the burst, 636 ns before any read can ask for it (§3.4).
  reg [7:0] rx_sr = 8'h00;
  reg [7:0] rx    = 8'h00;
  always @(posedge SCK)   rx_sr <= {rx_sr[6:0], SD_MISO};
  always @(negedge RCLK)  rx    <= rx_sr;   // the pin rises as RCLK deasserts

  // ---- the bus ------------------------------------------------------------
  // Exactly one of these may drive at a time, which is a claim the testbench
  // makes rather than a property of writing them here.
  assign D = OE595 ? rx
           : (SD0_OE | SD1_OE | SD2_OE) ? {5'b0, SD2, SD1, SD0}
           : 8'hzz;

  assign SD_SCK  = SCK;
  assign SD_CSn  = ~CS;                   // SDCTRL b0 asserts it; $00 releases
  assign OBS_BUSY = BUSY;
  assign OBS_RCLK = RCLK;
  assign OBS_DOE  = OE595 | SD0_OE | SD1_OE | SD2_OE;

endmodule

`default_nettype wire
