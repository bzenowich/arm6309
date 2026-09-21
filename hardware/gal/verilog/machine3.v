// THE MACHINE, WITH video3 IN THE SLOT: a 6809E in the socket, the motherboard
// under it, and video3_card.v on the backplane. docs/machine.md §2 is the
// backplane this wires; video3/docs/plan.md §10 is the card's register map.
//
// ⭐ WHY THIS EXISTS. machine.v does exactly this for video/, and
// video3/docs/plan.md §15.2 says video3's machine bench "should be that one
// with video_card.v replaced, not a new harness - so that what changes between
// a passing run and a failing one is the card". This file is that swap. It is
// a separate module rather than a parameter of machine.v because the two cards'
// backplane interfaces are not the same shape: video_card.v exports RD_o and no
// output enable, so machine.v has to restate graphics.md §3.2's '245 decode and
// assemble VSTAT's '244 itself, while video3_card.v already has the '245, the
// '244 and the vread '574 on the card where the board puts them and exports
// DOUT/DOE. Adding a mode switch to machine.v would have meant making those
// three board-level blocks conditional, which is more machinery than a second
// top level.
//
// ⚠ WHAT IS NOT IN IT, said rather than implied:
//
//   1. NO DISPLAY LIST, NO BSTAT, NO BORDER - the card does not have them
//      (plan.md §10), so neither does this.
//
// ⭐ AND WHAT WENT INTO IT ON 2026-09-20, when software/boot/boot.asm was
// retargeted from the archived `video` card to this one and machine_tb.sv
// followed: the OTHER TWO SLOTS, as machine.v has them, both off by default.
//
//   AUDIO = 1   audio_card.v at $FF40 (audio.md §9.1) on its own 28.37516 MHz
//               crystal, asynchronous to CLK25 exactly as the two cards are on
//               the backplane, with its open-drain /FIRQ on the wired-AND
//               beside video3's /IRQ. plan.md §15.2 asked for exactly this -
//               "two cards, one backplane". 0 leaves the slot empty, not
//               modelled-as-silent, so v3machine_tb is the machine it was.
//   SERIAL = 1  a TL16C550C (tl16c550.v, a bus model of the bought part) at
//               $FF38 - io/serial/docs/serial.md §7.1 - with its INTR on the
//               shared /IRQ. It is NitrOS-9's console. 0 leaves the window
//               undecoded, so a read of it answers from the motherboard like
//               any other free byte.
//
// ⭐ AND A THIRD SLOT, which was one bit of a stub until 2026-09-21:
//
//   STORAGE = 1 storage_card.v at $FF58 - the eight ICs and two GALs of
//               storage/docs/sdcard.md §3.1 - with sd_model.v, a behavioural
//               SDHC card, in its socket. `sd_cd` is that socket's mechanical
//               card-detect switch and `+sdimage=<hex>` is what is on the
//               card. 0 leaves the four bytes undecoded, which is an empty
//               slot and not a silent one.
//
// ⛔ IT USED TO BE A STUB THAT ANSWERED $FF59 AND NOTHING ELSE, and the
// argument for that was that boot.asm §10a only needed one bit - "a card is
// in the socket" - to choose a picture, and the whole card would put a
// second clock domain in every run. §10b took that argument away on
// 2026-09-21: "found" now means a card that answered CMD58 with CCS and
// whose block 0 carries a boot signature, so the ROM issues real commands
// and reads real bytes, and a stub could only ever answer "not bootable".
// ⚠ The stub is KEPT for STORAGE = 0 rather than deleted, because
// v3machine_tb wants a machine with an empty storage slot and $FF59 still
// has to read as an open socket there.
//
// ⚠ AND WHAT THE CARD ALREADY DOES FOR ITSELF, which is why this file is short.
// video3_card.v resolves its own buses from explicit drivers and exports seven
// fight/float lines; they are brought straight out to the top here so the bench
// can assert them against a run driven by a CPU instead of by a task. The only
// bus this file has to resolve is D7..D0 between the card and the motherboard,
// and it REPORTS a double drive rather than ORing it (design-review2.md §10).

`default_nettype none

module machine3 #(
    parameter int SIMMS = 4,         // how many of the four sockets are populated
    parameter bit AUDIO = 0,         // audio_card.v at $FF40 - see the header
    parameter bit SERIAL = 0,        // a TL16C550C at $FF38 - see the header
    parameter bit STORAGE = 0,       // ⭐ storage_card.v at $FF58 - see the header
    parameter int SDBLOCKS = 128     // ...and how big the card in its socket is
) (
    input  wire        CLK25,        // 25.175 MHz - the dot clock AND the divider's input
    input  wire        SLOTCLK,      // 28.37516 MHz - the audio card's crystal, used only if AUDIO
    input  wire        n_reset,
    input  wire        fast_e,
    input  wire        sd_cd,        // the storage card's CARD DETECT - see below

    // ---- the picture, as the connector sees it --------------------------
    output wire [15:0] RGB,
    output wire        BLANK,
    output wire        HSYNC,
    output wire        VSYNC,

    // ---- observation ----------------------------------------------------
    output wire        e,
    output wire        q,
    output wire        run,
    output wire [15:0] la,
    output wire        rw,
    output wire [7:0]  cpu_dout,
    output wire [7:0]  cpu_din,
    output wire [24:0] pa,
    output wire        lic,          // last instruction cycle - one pulse per instruction
    output wire        avma,
    output wire        n_iosel,
    output wire        n_iopage_bp,
    output wire        wait_asserted,
    output wire        irq_asserted,
    output wire        card_drives,  // the card owns D7..D0 this cycle

    // ---- the things that must never happen -------------------------------
    output wire        bus_conflict, // the card and the motherboard both on D7..D0
    output wire        pa_conflict,  // two drivers on physical A20-A13
    // the card's own, which no single part of it can see (video3_card.v)
    output wire        FBA_FIGHT,
    output wire        DBUS_FIGHT,
    output wire        LUTA_FIGHT,
    output wire        IDB_FIGHT,
    output wire        IDB_FLOAT,
    output wire        LANE_FLOAT,
    output wire        RANK_FIGHT,

    // ---- the audio card, when AUDIO: what its four AD7528 pairs are given
    output wire [7:0]  DACSAMP0, DACSAMP1, DACSAMP2, DACSAMP3,
    output wire [7:0]  DACVOL0,  DACVOL1,  DACVOL2,  DACVOL3,
    output wire [15:0] ACOUNT,
    output wire        firq_asserted
);

  // ---- the CPU ------------------------------------------------------------
  // mc6809e takes E and Q as INPUTS, which is what a 6809E is: the clock comes
  // from the board. hardware/vendor/mc6809/README.md is why this core.
  wire [7:0] cpu_d_in;
  wire [7:0] cpu_d_out;
  wire [15:0] cpu_addr;
  wire cpu_rnw, cpu_ba, cpu_bs, cpu_busy;
  wire n_irq, n_firq;

  mc6809e cpu (
      .D(cpu_d_in), .DOut(cpu_d_out), .ADDR(cpu_addr), .RnW(cpu_rnw),
      .E(e), .Q(q),
      .BS(cpu_bs), .BA(cpu_ba),
      .nIRQ(n_irq), .nFIRQ(n_firq), .nNMI(1'b1),
      .AVMA(avma), .BUSY(cpu_busy), .LIC(lic),
      .nHALT(1'b1), .nRESET(n_reset)
  );

  assign la = cpu_addr;
  assign rw = cpu_rnw;
  assign cpu_dout = cpu_d_out;
  assign cpu_din = cpu_d_in;

  // ---- the motherboard ----------------------------------------------------
  wire [7:0] mb_din;
  wire mb_din_valid, pa_valid, pa_hi_valid, pa_hi_conflict, pa_hi_pulled;
  wire dramsel, romsel;
  wire [3:0] ras;

  mainboard #(.SIMMS(SIMMS)) mb (
      .CLK25(CLK25), .n_reset(n_reset), .fast_e(fast_e), .wait_i(wait_asserted),
      .la(cpu_addr), .rw(cpu_rnw), .dout(cpu_d_out), .din(mb_din),
      .e(e), .q(q), .run(run),
      .n_iosel(n_iosel), .n_iopage_bp(n_iopage_bp),
      .pa(pa), .pa_valid(pa_valid), .pa_conflict(pa_conflict),
      .pa_hi_valid(pa_hi_valid), .pa_hi_conflict(pa_hi_conflict),
      .pa_hi_pulled(pa_hi_pulled),
      .dramsel(dramsel), .ras(ras), .romsel(romsel),
      .din_valid(mb_din_valid)
  );

  // ---- the backplane, as a card sees it -----------------------------------
  // §2: /IOSEL is the $FF00-$FF7F window strobe and /IOPAGE the inhibit, both
  // active low on the connector and asserted-high inside the models. v3host
  // reads the second as IOPGH and needs it LOW for the VRAM window, which is a
  // plain physical cycle with A19 = 1 and A20 = 0.
  wire iosel  = ~n_iosel;
  wire iopage = ~n_iopage_bp;

  // ---- the card -----------------------------------------------------------
  wire [7:0] card_dout;
  wire card_doe, card_wait_oe, card_irq_oe;

  video3_card card (
      .CLK25(CLK25), .RESET(~n_reset),
      .E(e), .RW(cpu_rnw), .IOSEL(iosel), .IOPGH(iopage),
      .PA(pa[20:0]), .DIN(cpu_d_out),
      .DOUT(card_dout), .DOE(card_doe),
      .WAIT_OE(card_wait_oe), .IRQ_OE(card_irq_oe),
      .RGB(RGB), .HSYNC(HSYNC), .VSYNC(VSYNC), .BLANK(BLANK),
      .FBA_FIGHT(FBA_FIGHT), .DBUS_FIGHT(DBUS_FIGHT), .LUTA_FIGHT(LUTA_FIGHT),
      .IDB_FIGHT(IDB_FIGHT), .IDB_FLOAT(IDB_FLOAT), .LANE_FLOAT(LANE_FLOAT),
      .RANK_FIGHT(RANK_FIGHT)
  );

  // ---- the serial card's UART ----------------------------------------------
  // serial.md §7.1: $FF38-$FF3F, the upper half of the I/O card's sixteen-byte
  // window at $FF30. $38 is 011 1xxx: A6 = 0, A5 = A4 = A3 = 1, and the part
  // decodes A2-A0 itself. ⚠ The strobe does not imply A6 (serial.md §7.1).
  // The INTR-to-open-drain inverter is on the card; here it is the OR below.
  wire ser_sel = (SERIAL != 0) & iosel & ~pa[6] & pa[5] & pa[4] & pa[3];
  wire ser_intr_raw, ser_tx_strobe;
  wire [7:0] ser_rd, ser_tx_byte;
  tl16c550 ser (
      .CLK25(CLK25), .RESET(~n_reset), .SEL(ser_sel), .E(e), .RW(cpu_rnw),
      .A(pa[2:0]), .DIN(cpu_d_out), .DOUT(ser_rd), .INTR(ser_intr_raw),
      .tx_strobe(ser_tx_strobe), .tx_byte(ser_tx_byte));
  wire ser_intr  = (SERIAL != 0) & ser_intr_raw;
  wire ser_drives = ser_sel & cpu_rnw;

  // ---- the audio card -----------------------------------------------------
  // audio.md §9.1: SEL = /IOSEL & A6 & !A5 & !A4, $FF40-$FF4F. The card's port
  // is D0-D7 itself, bidirectional: the CPU drives it for a write to the
  // card's window, and the card drives it for a read of it.
  wire aud_sel = iosel & pa[6] & ~pa[5] & ~pa[4];
  wire aud_firq_oe;
  wire [7:0] aud_hd;
  generate if (AUDIO) begin : slot_audio
    assign aud_hd = (aud_sel & ~cpu_rnw) ? cpu_d_out : 8'hzz;
    audio_card aud (
        .SLOTCLK(SLOTCLK), .RESET(~n_reset),
        .IOSEL(iosel), .E(e), .RW(cpu_rnw), .A(pa[6:0]), .HD(aud_hd),
        .FIRQ_OE(aud_firq_oe), .COUNT(ACOUNT),
        .DACSAMP0(DACSAMP0), .DACSAMP1(DACSAMP1), .DACSAMP2(DACSAMP2), .DACSAMP3(DACSAMP3),
        .DACVOL0(DACVOL0), .DACVOL1(DACVOL1), .DACVOL2(DACVOL2), .DACVOL3(DACVOL3));
  end else begin : slot_empty
    assign aud_hd = 8'h00;
    assign aud_firq_oe = 1'b0;
    assign ACOUNT = 16'h0;
    assign {DACSAMP0, DACSAMP1, DACSAMP2, DACSAMP3} = 32'h0;
    assign {DACVOL0, DACVOL1, DACVOL2, DACVOL3} = 32'h0;
  end endgenerate
  wire aud_drives = (AUDIO != 0) & aud_sel & cpu_rnw;

  // ---- the storage card ----------------------------------------------------
  // ⭐ THE REAL CARD SINCE 2026-09-21 (the header says why), with sd_model.v
  // in its socket. storage_card.v exports OBS_DOE so that this file does not
  // have to restate the card's decode: the card says when it is on the bus,
  // exactly as video3_card.v does, and `bus_conflict` below is then a real
  // question rather than a re-derivation.
  //
  // ⚠ D7..D0 IS A TRI-STATE NET HERE and nowhere else in this file. The card
  // has an `inout D` because a '595 with an output enable is what it is; the
  // harness drives it during a write and lets go during a read, which is the
  // pattern storage_tb.sv uses. Everything else in this machine resolves from
  // explicit drivers.
  wire [7:0] sd_rd;
  wire       sd_drives;
  generate if (STORAGE) begin : g_storage
    wire [7:0] sd_bus;
    wire       sd_sck, sd_mosi, sd_miso, sd_csn, sd_doe;
    wire       sd_obs_busy, sd_obs_rclk;   // storage_tb's, not this machine's
    /* ⛔ AND THE WRITE DATA HAS TO STILL BE THERE AT E-FALL, which is the
     * 2026-09-10 trap in its second costume. sdbus's MOSICK is
     * `... & ~RW & E` and storage_card.v clocks the '574 on its FALLING
     * edge - so the byte a write sends is latched at the instant E falls,
     * and in a zero-delay model the core has already moved on in that
     * delta. A real 6809E holds write data past E-fall (t_DHW) and
     * storage_tb.sv's own cycle task says so in as many words: "release the
     * bus a dot later, never at the edge itself". This is that dot. */
    reg  [7:0] sd_wd_q;
    reg        sd_wr_q;
    always @(posedge CLK25) begin sd_wd_q <= cpu_d_out; sd_wr_q <= ~cpu_rnw; end
    assign sd_bus = ~cpu_rnw ? cpu_d_out : sd_wr_q ? sd_wd_q : 8'hzz;
    storage_card u_store (
        .CLK25(CLK25), .IOSELn(n_iosel), .A(pa[6:0]), .RW(cpu_rnw), .E(e),
        .RESETn(n_reset), .D(sd_bus),
        .SD_SCK(sd_sck), .SD_MOSI(sd_mosi), .SD_MISO(sd_miso), .SD_CSn(sd_csn),
        .CDn(~sd_cd),        // the switch is closed to ground when a card is in
        .WPn(1'b1),          // and its write-protect tab is not set
        .OBS_BUSY(sd_obs_busy), .OBS_RCLK(sd_obs_rclk), .OBS_DOE(sd_doe));
    sd_model #(.NBLOCKS(SDBLOCKS)) u_card (
        .PORn(n_reset), .SCK(sd_sck), .MOSI(sd_mosi), .CSn(sd_csn), .MISO(sd_miso));
    assign sd_rd     = sd_bus;
    assign sd_drives = sd_doe;
    // verilator lint_off UNUSEDSIGNAL
    wire _unused_sd = &{1'b0, sd_obs_busy, sd_obs_rclk, 1'b0};
    // verilator lint_on UNUSEDSIGNAL
  end else begin : g_nostorage
    // ⚠ THE STUB, AND IT IS SAID HERE RATHER THAN IMPLIED. Exactly one
    // address answers: a READ of $FF59, with {WP = 0, CD = sd_cd, BUSY = 0}.
    // ⛔ SDDATA IS NOT MODELLED, deliberately. A read of $FF58 returns the
    // previous burst's byte AND STARTS ANOTHER (sdcard.md §6.2); a stub that
    // answered 0 for it would be a machine that is *less* dangerous than the
    // real one. The address is left to the motherboard, which is what an
    // empty socket does.
    assign sd_drives = iosel & (pa[6:0] == 7'h59) & cpu_rnw;
    assign sd_rd     = {6'b0, sd_cd, 1'b0};
  end endgenerate

  // ---- the open-drain control lines ---------------------------------------
  // §2.1: /IRQ, /FIRQ and /WAIT are open-drain with pull-ups on the
  // motherboard, so a card that is not pulling contributes nothing. Written as
  // a wired-AND over every puller, so that a third card needs no line of this
  // rewritten.
  assign wait_asserted = card_wait_oe;
  assign irq_asserted  = card_irq_oe | ser_intr;
  assign n_irq         = ~(card_irq_oe | ser_intr);
  assign firq_asserted = aud_firq_oe;
  assign n_firq        = ~aud_firq_oe;

  // ---- D7..D0 --------------------------------------------------------------
  // ⭐ THE CARD SAYS WHEN IT DRIVES, so unlike machine.v this file does not
  // restate a decode. video3_card.v's DOE is the OR of its host '245 outbound,
  // its VSTAT '244 and its vread '574, and the card reports a fight between
  // those three itself (DBUS_FIGHT). What is left for the machine is the one
  // question a card cannot answer: whether the MOTHERBOARD is also driving.
  //
  // The motherboard answers for everything that is not the card's register
  // window; the VRAM window (A19 = 1, A20 = 0, outside the I/O page) decodes to
  // no motherboard device at all, so din_valid is already low there and the
  // exclusion below is only the $FF60-$FF7F window's.
  // ⚠ AND THE STORAGE CARD'S FOUR BYTES COME OUT OF THE MOTHERBOARD'S SHARE
  // WHOLESALE, not just the one the card happens to be driving this cycle:
  // $FF58-$FF5B is the card's window (sdcard.md §6.1) whether or not the
  // read lands on a register that answers, and a motherboard byte on the bus
  // under a card read is a fight either way.
  wire sd_win = iosel & (pa[6:2] == 5'b10110);   // $FF58-$FF5B
  wire mb_drives = mb_din_valid & cpu_rnw & ~(iosel & pa[6] & pa[5])
                 & ~aud_drives & ~ser_drives & ~(STORAGE ? sd_win & cpu_rnw : sd_drives);
  assign card_drives = card_doe;

  /* ⛔ AND THE BYTE HAS TO STILL BE THERE AT E-FALL, WHICH IS THE ONE INSTANT
   * THAT MATTERS. This is machine.v's 2026-09-10 trap in the shape video3
   * gives it, and it cost this bench a day of chasing card defects that were
   * really harness defects.
   *
   * A 6809E latches read data ON THE FALLING EDGE of E (graphics.md §3.1).
   * v3host's three read enables - VSTATOE, RDBKOE and RDOE - are all product
   * terms with `E` in them, which is right for the hardware: the '244 and the
   * two '245s are combinational, and t_DSR is satisfied long before E falls.
   * But in a ZERO-DELAY MODEL `e` is already 0 in the delta where the core
   * samples, so DOE has already gone away and the CPU reads the motherboard's
   * stale byte instead.
   *
   * ⚠ IT DOES NOT PRESENT AS "READS RETURN ZERO". mainboard.v holds the last
   * byte anything drove (d_last, because D0-D7 has no pull-ups), so a poll of
   * VSTAT returns the last ROM byte the CPU fetched - a plausible-looking
   * value that clears the bit being polled after a few tries. Every status
   * loop in software/v3boot then EXITS EARLY, and the card looks like it
   * truncates spans and copies and scrambles its palette. It does not; the
   * harness was answering the polls.
   *
   * So the byte the card drove during E-high is held across E-fall. The hold
   * is refreshed every dot of E-high and is therefore exactly "what the card
   * was driving when E fell"; it is a model of the bus settling time, not of
   * a latch the board has. ⭐ The FIGHT check below still uses the card's real
   * enable, because a fight is a thing that happens while both parts drive. */
  reg [7:0] hold_dout;
  reg       hold_doe;
  always @(posedge CLK25) if (e) begin
    hold_doe  <= card_doe;
    hold_dout <= card_dout;
  end
  wire       card_rd   = e ? card_doe  : hold_doe;
  wire [7:0] card_rd_d = e ? card_dout : hold_dout;

  // ⛔ TWO DRIVERS IS THE FAILURE /IOPAGE EXISTS TO PREVENT (machine.md §2), so
  // this reports it rather than ORing it. design-review2.md §10: "a model that
  // ORs its drivers cannot see a bus fight".
  assign bus_conflict = (mb_drives & (card_doe | aud_drives | ser_drives | sd_drives))
                      | (card_doe  & (aud_drives | ser_drives | sd_drives))
                      | (aud_drives & (ser_drives | sd_drives))
                      | (ser_drives & sd_drives);
  /* ⛔ AND THE STORAGE CARD'S BYTE IS HELD ACROSS E-FALL FOR THE SAME REASON
   * video3's is, found 2026-09-21 by the `disk` scenario reading the question
   * mark off a card that was perfectly good. sdbus's OE595 and RDST are both
   * `... & RW & E` - which is right for the hardware, where the '595's
   * outputs settle long before E falls - but in a zero-delay model `e` is
   * already 0 in the delta where the core samples, so the enable has gone
   * away and the CPU reads the motherboard's stale byte instead. ⚠ It does
   * NOT present as "reads return zero": mainboard.v holds the last byte
   * anything drove, so §9.0's R1 poll reads a plausible ROM byte, decides the
   * card answered something that is not $FF, and the whole initialisation
   * fails for a reason that looks like the card. `bus_conflict` below still
   * uses the REAL enable, because a fight happens while both parts drive. */
  reg [7:0] hold_sd_d;
  reg       hold_sd_oe;
  always @(posedge CLK25) if (e) begin
    hold_sd_oe <= sd_drives;
    hold_sd_d  <= sd_rd;
  end
  wire       sd_read   = e ? sd_drives : hold_sd_oe;
  wire [7:0] sd_read_d = e ? sd_rd     : hold_sd_d;

  assign cpu_d_in = card_rd ? card_rd_d : aud_drives ? aud_hd
                  : ser_drives ? ser_rd : sd_read ? sd_read_d : mb_din;

  // verilator lint_off UNUSEDSIGNAL
  wire _unused = &{1'b0, cpu_ba, cpu_bs, cpu_busy, pa_valid, pa_hi_valid,
                   pa_hi_conflict, pa_hi_pulled, dramsel, romsel, ras,
                   ser_tx_strobe, ser_tx_byte, 1'b0};
  // verilator lint_on UNUSEDSIGNAL

endmodule
`default_nettype wire
