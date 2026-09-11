// THE MACHINE: a 6809E in the socket, the motherboard under it, and the video
// card in a slot. docs/machine.md §2 is the backplane this wires.
//
// ⭐ WHY THIS EXISTS, AND WHAT IT IS THE FIRST OF. Every testbench before it
// drives the bus by hand: mainboard_tb walks §7.2's boot sequence as twenty
// literal bus cycles, and vspan_tb writes the video card's registers from a
// task. Both are models of what software WOULD do. This one instantiates
// hardware/vendor/mc6809/mc6809e.v - which nothing in this repository had ever
// instantiated - and lets the boot ROM's own instructions do it, so the
// question stops being "is each part right" and becomes "does the machine
// run its own software". The seams that answer only shows up in are the ones
// design-review2.md §10 says this repository keeps paying for.
//
// ⚠ WHAT IS MODELLED HERE AND NOT IN THE CARD. Two board-level things live in
// this file because video_card.v does not have them, and both are named where
// they are built:
//
//   1. THE CARD'S DATA-BUS DRIVER. video_card.v exports RD_o - the register
//      file's output - and no output enable, so nothing in it says WHEN the
//      card drives D0-D7. graphics.md §3.2's '245 is the part; the condition
//      is rfa's own decode, which is why it can be restated exactly here.
//   2. VSTAT's '244. graphics.md §13 says +$13 is read "through the '244 of
//      §12.1, not the register file", and §12.1's '244 is not in video_card.v
//      either. It is assembled below from the card's own SPANBUSY, VBLANK,
//      HBLANK and IRQ.
//
// ⛔ AND ONE PATH IS DELIBERATELY ABSENT: graphics.md §11's readable VRAM. The
// card has no read latch in video_card.v, so a CPU read of a VRAM address gets
// nothing here and `vram_read_attempt` says so rather than a plausible byte
// arriving from a path the design does not contain. machine_tb asserts the
// software never does it.

`default_nettype none

module machine #(
    parameter int SIMMS = 4
) (
    input  wire        CLK25,        // 25.175 MHz - the dot clock AND the divider's input
    input  wire        n_reset,
    input  wire        fast_e,

    // ---- the picture, as the connector sees it --------------------------
    output wire [15:0] RGB,
    output wire        BLANK,
    output wire        HSYNC,
    output wire        VSYNC,
    output wire [7:0]  PIXEL,
    output wire [7:0]  H,
    output wire [9:0]  V,

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
    output wire [18:0] WPTR,
    output wire [1:0]  VMODE,      // sync polarity follows VMODE0 - graphics.md 6.2.1
    output wire        SPANBUSY,
    output wire        VBLANK,
    output wire        HBLANK,

    // ---- the three things that must never happen ------------------------
    output wire        bus_conflict,       // two drivers on D0-D7
    output wire        pa_conflict,        // two drivers on physical A20-A13
    output wire        vram_read_attempt   // §11's path, which is not modelled
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
  // active low on the connector and asserted-high inside the models.
  wire iosel  = ~n_iosel;
  wire iopage = ~n_iopage_bp;

  // ---- the video card -----------------------------------------------------
  wire vid_wait_oe, vid_irq_oe;
  wire [7:0] vid_rd;
  wire [1:0] vid_ph;
  wire [18:2] vid_fba;
  wire vid_linear, vid_tilesel, vid_mapsel, vid_spngrant, vid_lrun;
  wire vid_retire, vid_wen, vid_spanend, vid_mapld, vid_mapreq;
  wire vid_slottick, vid_sparewin;
  wire [7:0] vid_pidx;
  wire [9:2] vid_hscr;
  wire vid_lph, vid_lwait, vid_pwe, vid_pdoe, vid_pixoe, vid_dbus_fight;

  video_card card (
      .DOTCLK(CLK25), .RESET(~n_reset),
      .E(e), .RW(cpu_rnw), .IOSEL(iosel), .IOPAGE(iopage),
      .PA(pa[20:0]), .DIN(cpu_d_out),
      .WAIT_OE(vid_wait_oe), .IRQ_OE(vid_irq_oe),
      .PIXEL(PIXEL), .BLANK(BLANK), .HSYNC(HSYNC), .VSYNC(VSYNC),
      .H(H), .V(V), .PH(vid_ph), .FBA(vid_fba),
      .LINEAR(vid_linear), .TILESEL(vid_tilesel), .MAPSEL(vid_mapsel),
      .SPNGRANT(vid_spngrant), .SPANBUSY(SPANBUSY), .LRUN(vid_lrun),
      .RETIRE(vid_retire), .WEN(vid_wen), .SPANEND(vid_spanend),
      .MAPLD(vid_mapld), .MAPREQ(vid_mapreq), .SLOTTICK(vid_slottick),
      .SPAREWIN(vid_sparewin),
      .WPTR(WPTR), .RD_o(vid_rd), .VMODE(VMODE),
      .VBLANK(VBLANK), .HBLANK(HBLANK),
      .HSCR(vid_hscr), .LPH_o(vid_lph), .LWAIT_o(vid_lwait),
      .RGB(RGB), .PIDX(vid_pidx),
      .PWE_o(vid_pwe), .PDOE_o(vid_pdoe), .PIXOE_o(vid_pixoe),
      .DBUS_FIGHT(vid_dbus_fight)
  );

  // ---- the open-drain control lines ---------------------------------------
  // §2.1: /IRQ, /FIRQ, /WAIT are open-drain with pull-ups on the motherboard,
  // so a card that is not pulling contributes nothing. One card here, so the
  // wired-AND is one term - written as a reduction anyway, because the next
  // card added must not need this line rewritten.
  assign wait_asserted = vid_wait_oe;
  assign n_irq  = ~vid_irq_oe;
  assign n_firq = 1'b1;                  // the audio card's line; no audio card here

  // ---- D0-D7 --------------------------------------------------------------
  // 1. graphics.md §3.2's '245, whose enable is rfa's own decode: the card owns
  //    the bus for a READ of its 32-byte window and at no other time.
  wire vid_regsel   = iosel & pa[6] & pa[5];
  /* ⛔ AND THE ENABLE IS THE CYCLE, NOT E-HIGH. This read `& e` until
   * 2026-09-10 and the CPU could not read a card register at all.
   *
   * A 6809E latches read data ON THE FALLING EDGE of E (graphics.md 3.1), and
   * in a zero-delay model `e` is already 0 in the delta where the core samples
   * - so gating the card's data on E-high presents it for the whole cycle and
   * then removes it at the one instant that matters. Every read of $FF60-$FF7F
   * returned the motherboard's stale byte instead.
   *
   * ⚠ IT HID ITSELF, which is why it lasted a day. boot.asm polls VSTAT b7
   * before each span (7.4's rule) and the loop exited immediately on a stale
   * zero, so the picture still came out right - the spans were spaced by the
   * CPU's own arithmetic instead. It only became visible when software waited
   * on a bit that is zero MOST of the time rather than one that is zero when
   * the card is idle: VSTAT b6, VBLANK, which is high for 49 lines of 449.
   *
   * ⭐ The hardware is fine and it is the model that was wrong: graphics.md
   * 3.2's '245 sits on the card's own decode, its output is combinational, and
   * t_DSR is satisfied long before E falls. So the enable here is the read
   * cycle - there is no other driver in this window, because mb_drives
   * excludes it by construction below. */
  wire vid_drives   = vid_regsel & cpu_rnw;

  // 2. VSTAT's '244 - §12.1, §13. b7 SPANBUSY, b6 VBLANK, b5 HBLANK,
  //    b4 LRUN, b0 IRQ.
  wire vstat_sel = vid_regsel & (pa[4:0] == 5'h13);
  /* ⛔ b4 IS LRUN, BECAUSE BSTAT HAD NO PATH TO THE DATA BUS - §19 item 43.
   * §13 puts LRUN at +$0F and §10.3.1 calls it "the bit a driver polls", but
   * §12.1's argument for VSTAT's own '244 applies to it word for word: LRUN is
   * a live macrocell on vsup, not a register-file location, so §3.2's '245 has
   * nothing to read back at +$0F and a read returns whatever the CPU last
   * wrote there. boot.asm polled it, got zero, and loaded WPTR while the list
   * engine was still walking it; machine_tb saw LRUN = 1 through the whole of
   * the tilemap upload, its 256 bytes landing at addresses that skipped. The
   * '244 that exists carries four bits of eight and LRUN is already a pin, so
   * this is one net and no package. */
  wire [7:0] vstat = {SPANBUSY, VBLANK, HBLANK, vid_lrun, 3'b000, vid_irq_oe};

  wire [7:0] vid_d = vstat_sel ? vstat : vid_rd;

  // 3. The motherboard, which answers for everything that is not a card.
  wire mb_drives = mb_din_valid & cpu_rnw & ~(iosel & pa[6] & pa[5]);

  // ⛔ TWO DRIVERS IS THE FAILURE /IOPAGE EXISTS TO PREVENT (machine.md §2), so
  // this reports it rather than ORing it. design-review2.md §10: "a model that
  // ORs its drivers cannot see a bus fight".
  assign bus_conflict = mb_drives & vid_drives;

  assign cpu_d_in = vid_drives ? vid_d : mb_din;

  // §11's readable VRAM: a CPU read of a mapped VRAM address. The card would
  // answer; video_card.v has no path that does, so say so.
  assign vram_read_attempt = cpu_rnw & e & ~iopage & ~pa[20] & pa[19];

  // verilator lint_off UNUSEDSIGNAL
  wire _unused = &{1'b0, cpu_ba, cpu_bs, cpu_busy, pa_valid, pa_hi_valid,
                   pa_hi_conflict, pa_hi_pulled, dramsel, romsel, ras,
                   vid_ph, vid_fba, vid_linear, vid_tilesel, vid_mapsel,
                   vid_spngrant, vid_lrun, vid_retire, vid_wen, vid_spanend,
                   vid_mapld, vid_mapreq, vid_slottick, vid_sparewin,
                   vid_pidx, vid_hscr, vid_lph, vid_lwait,
                   vid_pwe, vid_pdoe, vid_pixoe, vid_dbus_fight, 1'b0};
  // verilator lint_on UNUSEDSIGNAL

endmodule
`default_nettype wire
