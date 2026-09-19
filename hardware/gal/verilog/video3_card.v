// video3, wired: v3dot + v3scan + v3ptr + v3host, and the discrete parts of
// video3/docs/plan.md §13.1 around them - the two AS6C8016 framebuffer parts,
// the 32K x 8 register file, the fetch ranks, the '153 pixel mux, the index
// and attribute '574s, the 64K x 16 LUT and its output '273s, the PIDX and
// PDAT latches, the posted-write and vread '574s, and the VSTAT '244 and the
// read-back '245 onto the backplane.
//
// ⭐ EVERY NET BETWEEN TWO PARTS IS THE TERM LISTS' OWN. The wire list and the
// four instance port maps are GENERATED - v3portmap.ts, run by gen.ts, rewrites
// them between their two markers from the .cpld.ts inputs and EXTERNAL sets -
// so ⚠ edit the parts, not that region. A port a part does not let out of its
// package is not connected here, so a buried cell cannot become a net by being
// mentioned. reach.check.ts's census rule, restated for a board. Everything
// from THE BOARD down is hand-written.
//
// ⛔ AND WHERE THE BOARD NEEDS A SIGNAL NO PACKAGE LETS OUT, IT SAYS SO.
// Building this file is what found them: signals.md §1 lists control lines a
// DISCRETE chip needs and no part produces, and check:reach cannot see that
// shape - a signal no part reads or produces falls through both of its
// directions. Each one below is reached by HIERARCHICAL REFERENCE into the
// part (`u_ptr.WC0`) and named GAP_n, so it is visibly different in the source
// and `grep -c 'u_[a-z]*\.' video3_card.v` counts them. They are what the
// board would need and does not have - not a design:
//
//   GAP_1  the byte lane of a single-byte access. v3ptr's mux drives FBA18..2
//          and never WC1:WC0 / CC1:CC0, so no discrete part can tell which of
//          the four bytes the span writer, the copy or the prefetch means.
//   GAP_2  the framebuffer's /VWE, /VOE and four byte enables (signals.md
//          §1.3). Nothing produces them. Derived here from WEN, CSTEP and the
//          lane - both writers' strobes, which DO leave their packages.
//   GAP_3  the fetch ranks' clock. SLOTTICK leaves v3dot, but a '574 has no
//          clock enable: the board needs a CLOCK, not a combinational tick.
//   GAP_4  the map word's part select (plan §2.5: A1 is the cell column's low
//          bit, MC0) - v3scan is 64/64 and cannot let it out.
//   GAP_5  VSTAT b0, the pending interrupt. IRQPEND is buried in v3host.
//   GAP_6  the copy's write data. §6 says the byte goes vread -> posted-write
//          '574 -> the framebuffer (trade 1: no copy latch), and no strobe on
//          the card moves it from one to the other.
//   GAP_7  which source the framebuffer's write data comes from - the posted-
//          write '574 (direct mode), the register file (span modes: §5's
//          "WFG or WBG without a mux") or vread (the copy). Needs an output
//          enable per source; none is produced.
//
// ⭐ PROPOSED, NOT A GAP: the palette's four load strobes - PIDX low ('163
// load, +$0E), PIDX high ('574 clock, +$0F), PDATL and PDATH ('573 LEs, +$10/
// +$11). v3host only strobes these latches and decodes PDATH alone. The
// broadcast REGWR/RA4..RA0 already leave v3host, so ONE '138 on the board
// decodes all four for zero CPLD pins - the answer regfile.ts's header gave
// for the other card. It is modelled that way and it is +1 IC.
//
// WHAT IS MODELLED is the logic, as every wrapper here: memories read
// combinationally on the address the parts drive and written on the dot the
// strobe is asserted. Propagation delay, the switch matrix and placement are
// cpld/*.fit's business. The sprite's four '165 are not modelled - the sprite
// needs register-file addresses above +$1F that RFA does not reach yet.

`default_nettype none

module video3_card (
    input  wire        CLK25,
    input  wire        RESET,

    // the 6809E bus, as the card sees it (asserted-high, like every model here)
    input  wire        E,
    input  wire        RW,
    input  wire        IOSEL,      // /IOSEL asserted: an $FF00-$FF7F cycle
    input  wire        IOPGH,      // the I/O page, as the backplane gives it
    input  wire [20:0] PA,
    input  wire [7:0]  DIN,
    output wire [7:0]  DOUT,
    output wire        DOE,        // the card is driving D7..D0
    output wire        WAIT_OE,    // open drain: asserted = /WAIT pulled low
    output wire        IRQ_OE,

    // the picture
    output wire [15:0] RGB,
    output wire        HSYNC,
    output wire        VSYNC,
    output wire        BLANK,

    // board-level fights, which no single part can see
    output wire        FBA_FIGHT,  // v3scan and v3ptr both on the address bus
    output wire        DBUS_FIGHT, // two of the '245, the '244 and vread on D
    output wire        LUTA_FIGHT  // two masters on the LUT address bus
);

  wire D0, D1, D2, D3, D4, D5, D6, D7;
  wire PA0, PA1, PA2, PA3, PA4, PA5, PA6, PA7;
  wire PB0, PB1, PB2, PB3, PB4, PB5, PB6, PB7;
  wire A0 = PA[0], A1 = PA[1], A2 = PA[2], A3 = PA[3], A4 = PA[4];
  wire A5 = PA[5], A6 = PA[6], A19 = PA[19], A20 = PA[20];

  // ---- every net that leaves a package ------------------------------------
  wire ATO0, ATO1, ATO2, ATO3, ATO4, ATO5, ATO6, ATO7, ATOE, CBUSY, CDONE, CELLTICK, CEOR,
       CHLAST, CPURF, CRDSEL, CROWADV, CSTEP, CWLOAD, FBOEPTR, FBOESCAN, FETCH, FOE0, FOE1,
       GCPY, GMAP, GRD, GSPN, HBLANK, HLOAD, IRQN, IRQN_OE, LUTWE, M0, MAPLD, MCADV, MODE0,
       MODE1, MUXSEL0, MUXSEL1, OMR, PALTURN, PBUSY, PIDXCE, PIDXOE, PIXOE, RA0, RA1, RA2,
       RA3, RA4, RCPY, RDBKOE, RDCK, RDOE, RDREQ, REGWR, RETIRE, RFA0, RFA1, RFA2, RFA3,
       RFA4, ROWADV, RP1, RP2, RP3, RP4, RSPN, SLOTTICK, SPANBUSY, SPARE, SPRLD, SPRSH,
       VBLANK, VLOAD, VSTATOE, WAITN, WAITN_OE, WEN, WROWADV, WSTART, WSTB, WSTBV, WSTEP,
       ptr_FBA10, ptr_FBA10_OE, ptr_FBA11, ptr_FBA11_OE, ptr_FBA12, ptr_FBA12_OE,
       ptr_FBA13, ptr_FBA13_OE, ptr_FBA14, ptr_FBA14_OE, ptr_FBA15, ptr_FBA15_OE,
       ptr_FBA16, ptr_FBA16_OE, ptr_FBA17, ptr_FBA17_OE, ptr_FBA18, ptr_FBA18_OE, ptr_FBA2,
       ptr_FBA2_OE, ptr_FBA3, ptr_FBA3_OE, ptr_FBA4, ptr_FBA4_OE, ptr_FBA5, ptr_FBA5_OE,
       ptr_FBA6, ptr_FBA6_OE, ptr_FBA7, ptr_FBA7_OE, ptr_FBA8, ptr_FBA8_OE, ptr_FBA9,
       ptr_FBA9_OE, scan_FBA10, scan_FBA10_OE, scan_FBA11, scan_FBA11_OE, scan_FBA12,
       scan_FBA12_OE, scan_FBA13, scan_FBA13_OE, scan_FBA14, scan_FBA14_OE, scan_FBA15,
       scan_FBA15_OE, scan_FBA16, scan_FBA16_OE, scan_FBA17, scan_FBA17_OE, scan_FBA18,
       scan_FBA18_OE, scan_FBA2, scan_FBA2_OE, scan_FBA3, scan_FBA3_OE, scan_FBA4,
       scan_FBA4_OE, scan_FBA5, scan_FBA5_OE, scan_FBA6, scan_FBA6_OE, scan_FBA7,
       scan_FBA7_OE, scan_FBA8, scan_FBA8_OE, scan_FBA9, scan_FBA9_OE;

  // ---- the four parts: generated port maps --------------------------------
  v3dot u_dot (
    .CLK25(CLK25), .RESET(RESET), .D0(D0), .D1(D1), .D2(D2), .D3(D3), .D4(D4), .D5(D5),
    .D6(D6), .D7(D7), .REGWR(REGWR), .RA0(RA0), .RA1(RA1), .RA2(RA2), .RA3(RA3), .RA4(RA4),
    .RDREQ(RDREQ), .RCPY(RCPY), .RSPN(RSPN), .PALTURN(PALTURN), .M0(M0),
    .SLOTTICK(SLOTTICK), .HBLANK(HBLANK), .HSYNC(HSYNC), .VSYNC(VSYNC), .VBLANK(VBLANK),
    .BLANK(BLANK), .FETCH(FETCH), .SPARE(SPARE), .CELLTICK(CELLTICK), .HLOAD(HLOAD),
    .VLOAD(VLOAD), .ROWADV(ROWADV), .MCADV(MCADV), .MAPLD(MAPLD), .MUXSEL0(MUXSEL0),
    .MUXSEL1(MUXSEL1), .PIXOE(PIXOE), .ATOE(ATOE), .PIDXOE(PIDXOE), .FOE0(FOE0),
    .FOE1(FOE1), .SPRSH(SPRSH), .SPRLD(SPRLD), .GMAP(GMAP), .GRD(GRD), .GCPY(GCPY),
    .GSPN(GSPN), .FBOESCAN(FBOESCAN), .FBOEPTR(FBOEPTR), .MODE0(MODE0), .MODE1(MODE1)
  );

  v3scan u_scan (
    .CLK25(CLK25), .RESET(RESET), .FETCH(FETCH), .HLOAD(HLOAD), .VLOAD(VLOAD),
    .ROWADV(ROWADV), .MCADV(MCADV), .MAPLD(MAPLD), .GMAP(GMAP), .MODE0(MODE0),
    .MODE1(MODE1), .FBOESCAN(FBOESCAN), .D0(D0), .D1(D1), .D2(D2), .D3(D3), .D4(D4),
    .D5(D5), .D6(D6), .D7(D7), .PB0(PB0), .PB1(PB1), .PB2(PB2), .PB3(PB3), .PB4(PB4),
    .PB5(PB5), .PB6(PB6), .PB7(PB7), .PA0(PA0), .PA1(PA1), .PA2(PA2), .PA3(PA3), .PA4(PA4),
    .PA5(PA5), .PA6(PA6), .PA7(PA7), .REGWR(REGWR), .RA0(RA0), .RA1(RA1), .RA2(RA2),
    .RA3(RA3), .RA4(RA4), .ATO0(ATO0), .ATO1(ATO1), .ATO2(ATO2), .ATO3(ATO3), .ATO4(ATO4),
    .ATO5(ATO5), .ATO6(ATO6), .ATO7(ATO7), .FBA2(scan_FBA2), .FBA2_OE(scan_FBA2_OE),
    .FBA3(scan_FBA3), .FBA3_OE(scan_FBA3_OE), .FBA4(scan_FBA4), .FBA4_OE(scan_FBA4_OE),
    .FBA5(scan_FBA5), .FBA5_OE(scan_FBA5_OE), .FBA6(scan_FBA6), .FBA6_OE(scan_FBA6_OE),
    .FBA7(scan_FBA7), .FBA7_OE(scan_FBA7_OE), .FBA8(scan_FBA8), .FBA8_OE(scan_FBA8_OE),
    .FBA9(scan_FBA9), .FBA9_OE(scan_FBA9_OE), .FBA10(scan_FBA10), .FBA10_OE(scan_FBA10_OE),
    .FBA11(scan_FBA11), .FBA11_OE(scan_FBA11_OE), .FBA12(scan_FBA12),
    .FBA12_OE(scan_FBA12_OE), .FBA13(scan_FBA13), .FBA13_OE(scan_FBA13_OE),
    .FBA14(scan_FBA14), .FBA14_OE(scan_FBA14_OE), .FBA15(scan_FBA15),
    .FBA15_OE(scan_FBA15_OE), .FBA16(scan_FBA16), .FBA16_OE(scan_FBA16_OE),
    .FBA17(scan_FBA17), .FBA17_OE(scan_FBA17_OE), .FBA18(scan_FBA18),
    .FBA18_OE(scan_FBA18_OE)
  );

  v3ptr u_ptr (
    .CLK25(CLK25), .RESET(RESET), .D0(D0), .D1(D1), .D2(D2), .D3(D3), .D4(D4), .D5(D5),
    .D6(D6), .D7(D7), .WSTBV(WSTBV), .WSTART(WSTART), .MUXSEL0(MUXSEL0), .RP1(RP1),
    .RP2(RP2), .RP3(RP3), .RP4(RP4), .WSTEP(WSTEP), .CPURF(CPURF), .GSPN(GSPN),
    .CDONE(CDONE), .CSTEP(CSTEP), .CROWADV(CROWADV), .CWLOAD(CWLOAD), .CRDSEL(CRDSEL),
    .REGWR(REGWR), .RA0(RA0), .RA1(RA1), .RA2(RA2), .RA3(RA3), .RA4(RA4), .FBOEPTR(FBOEPTR),
    .CEOR(CEOR), .CHLAST(CHLAST), .CBUSY(CBUSY), .SPANBUSY(SPANBUSY), .RSPN(RSPN),
    .RETIRE(RETIRE), .WEN(WEN), .WROWADV(WROWADV), .RFA0(RFA0), .FBA2(ptr_FBA2),
    .FBA2_OE(ptr_FBA2_OE), .FBA3(ptr_FBA3), .FBA3_OE(ptr_FBA3_OE), .FBA4(ptr_FBA4),
    .FBA4_OE(ptr_FBA4_OE), .FBA5(ptr_FBA5), .FBA5_OE(ptr_FBA5_OE), .FBA6(ptr_FBA6),
    .FBA6_OE(ptr_FBA6_OE), .FBA7(ptr_FBA7), .FBA7_OE(ptr_FBA7_OE), .FBA8(ptr_FBA8),
    .FBA8_OE(ptr_FBA8_OE), .FBA9(ptr_FBA9), .FBA9_OE(ptr_FBA9_OE), .FBA10(ptr_FBA10),
    .FBA10_OE(ptr_FBA10_OE), .FBA11(ptr_FBA11), .FBA11_OE(ptr_FBA11_OE), .FBA12(ptr_FBA12),
    .FBA12_OE(ptr_FBA12_OE), .FBA13(ptr_FBA13), .FBA13_OE(ptr_FBA13_OE), .FBA14(ptr_FBA14),
    .FBA14_OE(ptr_FBA14_OE), .FBA15(ptr_FBA15), .FBA15_OE(ptr_FBA15_OE), .FBA16(ptr_FBA16),
    .FBA16_OE(ptr_FBA16_OE), .FBA17(ptr_FBA17), .FBA17_OE(ptr_FBA17_OE), .FBA18(ptr_FBA18),
    .FBA18_OE(ptr_FBA18_OE)
  );

  v3host u_host (
    .CLK25(CLK25), .RESET(RESET), .IOSEL(IOSEL), .IOPGH(IOPGH), .A0(A0), .A1(A1), .A2(A2),
    .A3(A3), .A4(A4), .A5(A5), .A6(A6), .A19(A19), .A20(A20), .E(E), .RW(RW),
    .SPANBUSY(SPANBUSY), .CBUSY(CBUSY), .VBLANK(VBLANK), .HLOAD(HLOAD), .BLANK(BLANK),
    .RETIRE(RETIRE), .GRD(GRD), .D6(D6), .CEOR(CEOR), .CHLAST(CHLAST), .GCPY(GCPY),
    .MUXSEL0(MUXSEL0), .WROWADV(WROWADV), .REGWR(REGWR), .RA0(RA0), .RA1(RA1), .RA2(RA2),
    .RA3(RA3), .RA4(RA4), .PALTURN(PALTURN), .PBUSY(PBUSY), .LUTWE(LUTWE), .OMR(OMR),
    .PIDXCE(PIDXCE), .WSTBV(WSTBV), .WSTART(WSTART), .WSTB(WSTB), .WSTEP(WSTEP),
    .RDCK(RDCK), .RDOE(RDOE), .RDREQ(RDREQ), .WAITN(WAITN), .WAITN_OE(WAITN_OE),
    .IRQN(IRQN), .IRQN_OE(IRQN_OE), .VSTATOE(VSTATOE), .RDBKOE(RDBKOE), .CRDSEL(CRDSEL),
    .CSTEP(CSTEP), .CROWADV(CROWADV), .CWLOAD(CWLOAD), .CDONE(CDONE), .RCPY(RCPY),
    .RP1(RP1), .RP2(RP2), .RP3(RP3), .RP4(RP4), .RFA1(RFA1), .RFA2(RFA2), .RFA3(RFA3),
    .RFA4(RFA4), .CPURF(CPURF)
  );

  // ======================================================================
  // THE BOARD
  // ======================================================================

  // ---- the card's internal data bus, IDB (partition.md §2.4) -------------
  // The '245 drives it inward on every CPU write to the card - a register
  // write (WSTB) or a posted VRAM write (WSTBV) - and the register file drives
  // it the rest of the time, which is what §7.2's column reload reads.
  // ⚠ So a CPU write in flight during a span replaces the span's colour on
  // this bus: the model does what the board would, and a bench can see it.
  wire [7:0] rf_out;
  wire       idb_in = WSTB | WSTBV;
  wire [7:0] IDB = idb_in ? DIN : rf_out;
  assign {D7, D6, D5, D4, D3, D2, D1, D0} = IDB;

  // ---- the register file: 32 bytes of the 32K x 8 (plan §5) --------------
  // /WE is WSTB; the address is RFA - bit 0 is v3ptr's, because §5 makes it
  // the span-mask bit, and bits 4..1 are v3host's with the reload walk.
  wire [4:0] rfa = {RFA4, RFA3, RFA2, RFA1, RFA0};
  reg  [7:0] rf [0:31];
  assign rf_out = rf[rfa];
  always @(posedge CLK25) if (WSTB) rf[rfa] <= DIN;

  // ---- the framebuffer: two AS6C8016, as 512 KB (plan §4) ----------------
  // A byte address is {VA16..VA0, A1, A0}: A1 the part, A0 its /LB-/UB.
  // v3scan and v3ptr drive the same seventeen VA nets; the arbiter's two
  // grants choose, and a moment with both is a fight on the board.
  wire [16:0] scan_fba = {scan_FBA18, scan_FBA17, scan_FBA16, scan_FBA15, scan_FBA14,
                          scan_FBA13, scan_FBA12, scan_FBA11, scan_FBA10, scan_FBA9,
                          scan_FBA8, scan_FBA7, scan_FBA6, scan_FBA5, scan_FBA4,
                          scan_FBA3, scan_FBA2};
  wire [16:0] ptr_fba  = {ptr_FBA18, ptr_FBA17, ptr_FBA16, ptr_FBA15, ptr_FBA14,
                          ptr_FBA13, ptr_FBA12, ptr_FBA11, ptr_FBA10, ptr_FBA9,
                          ptr_FBA8, ptr_FBA7, ptr_FBA6, ptr_FBA5, ptr_FBA4,
                          ptr_FBA3, ptr_FBA2};
  wire scan_oe = scan_FBA2_OE, ptr_oe = ptr_FBA2_OE;
  wire [16:0] fba = scan_oe ? scan_fba : ptr_fba;
  assign FBA_FIGHT = scan_oe & ptr_oe;

  reg [7:0] vram [0:524287];

  // GAP_1: the lane of a single-byte access - the read and write pointers'
  // own low column bits, which v3ptr's address mux never drives out.
  wire [1:0]  lane   = CRDSEL ? {u_ptr.CC1, u_ptr.CC0} : {u_ptr.WC1, u_ptr.WC0};
  wire [18:0] byte_a = {fba, lane};

  // GAP_4: the map word is one x16 access, part A1 = the map column's low
  // bit; the code is the low byte (A0 = 0) and the attribute the high one.
  wire [18:0] map_a = {fba, u_scan.MC0, 1'b0};
  assign {PB7, PB6, PB5, PB4, PB3, PB2, PB1, PB0} = vram[map_a];
  assign {PA7, PA6, PA5, PA4, PA3, PA2, PA1, PA0} = vram[map_a | 19'd1];

  // ---- the fetch ranks: eight '574 (plan §2.3, graphics.md §8.2) ---------
  // GAP_3: clocked on SLOTTICK here, the end of the display half; rank B
  // holds what rank A held, the previous group.
  reg [7:0] fa0, fa1, fa2, fa3, fb0, fb1, fb2, fb3;
  always @(posedge CLK25) if (SLOTTICK) begin
    fb0 <= fa0; fb1 <= fa1; fb2 <= fa2; fb3 <= fa3;
    fa0 <= vram[{fba, 2'd0}]; fa1 <= vram[{fba, 2'd1}];
    fa2 <= vram[{fba, 2'd2}]; fa3 <= vram[{fba, 2'd3}];
  end

  // The '153: one of the four latched bytes a dot, from the rank FOE picks.
  wire [7:0] r0 = FOE0 ? fa0 : fb0, r1 = FOE0 ? fa1 : fb1;
  wire [7:0] r2 = FOE0 ? fa2 : fb2, r3 = FOE0 ? fa3 : fb3;
  wire [1:0] sel = {MUXSEL1, MUXSEL0};
  wire [7:0] pix = sel == 2'd0 ? r0 : sel == 2'd1 ? r1 : sel == 2'd2 ? r2 : r3;

  // ---- the index and ATTR '574, the LUT and its output '273 (plan §3) ----
  // Clocked every dot off the '244 clock fan-out (§13.1).
  reg [7:0] pixidx, attr;
  always @(posedge CLK25) begin
    pixidx <= pix;
    attr   <= {ATO7, ATO6, ATO5, ATO4, ATO3, ATO2, ATO1, ATO0};
  end

  // ⭐ PROPOSED: one '138 off the broadcast for the palette's four load
  // strobes (see the header). REGWR and RA4..RA0 already leave v3host.
  wire [4:0] ra = {RA4, RA3, RA2, RA1, RA0};
  wire st_pidxl = REGWR && ra == 5'h0E;
  wire st_pidxh = REGWR && ra == 5'h0F;
  wire st_pdatl = REGWR && ra == 5'h10;
  wire st_pdath = REGWR && ra == 5'h11;
  reg [7:0] pidx_lo, pidx_hi, pdatl, pdath;
  always @(posedge CLK25) begin
    if (st_pidxl)    pidx_lo <= IDB;          // two '163, parallel load
    else if (PIDXCE) pidx_lo <= pidx_lo + 8'd1;
    if (st_pidxh)    pidx_hi <= IDB;          // the '574, plan §10
    if (st_pdatl)    pdatl   <= IDB;          // the two '573
    if (st_pdath)    pdath   <= IDB;
  end

  // The LUT's sixteen address bits have three masters, and v3dot decides all
  // three (plan §3): PIXOE the index '574, ATOE the ATTR '574, PIDXOE the two
  // '244 from PIDX. In bitmap mode nothing drives A15..A8 - modelled as pulled
  // low, which is sub-palette 0.
  wire [7:0]  lut_hi = PIDXOE ? pidx_hi : ATOE ? attr : 8'h00;
  wire [7:0]  lut_lo = PIDXOE ? pidx_lo : pixidx;
  wire [15:0] lut_a  = {lut_hi, lut_lo};
  assign LUTA_FIGHT = (PIDXOE & PIXOE) | (PIDXOE & ATOE);
  reg [15:0] lut [0:65535];
  always @(posedge CLK25) if (LUTWE) lut[lut_a] <= {pdath, pdatl};

  // The two '273: /MR is OMR, so a blanked dot is 0 V (plan §9.2).
  // ⚠ /MR IS ASYNCHRONOUS on a '273 - it forces the outputs low while it is
  // asserted, whatever the clock does - so it gates the register's OUTPUT,
  // not what the register captures. An earlier version of this model treated
  // it as a synchronous clear and put the whole picture one dot early.
  reg [15:0] rgb_q;
  always @(posedge CLK25) rgb_q <= PIXOE ? lut[lut_a] : 16'h0000;
  assign RGB = OMR ? rgb_q : 16'h0000;

  // ---- the posted-write and vread '574s (plan §5, §11) --------------------
  reg [7:0] pw, vread;
  always @(posedge CLK25) if (WSTBV) pw <= IDB;
  always @(posedge CLK25) if (RDCK)  vread <= vram[byte_a];

  // GAP_2, GAP_6, GAP_7: the framebuffer's write strobe, and where its byte
  // comes from. Both writers' strobes DO leave their packages - WEN from the
  // span writer, CSTEP from the copy - but the byte enables, /VWE and the
  // data-source enables do not exist anywhere.
  wire direct = ~u_ptr.WM1 & ~u_ptr.WM0;
  wire vwe    = WEN | CSTEP;
  wire [7:0] wdata = CSTEP ? vread : direct ? pw : IDB;
  always @(posedge CLK25) if (vwe) vram[byte_a] <= wdata;

  // ---- D7..D0: the read-back '245, the VSTAT '244 and vread ---------------
  // GAP_5: VSTAT b0 is the pending interrupt, buried in v3host.
  wire [7:0] vstat = {SPANBUSY, VBLANK, HBLANK, CBUSY, 2'b00, PBUSY, u_host.IRQPEND};
  assign DOE  = RDBKOE | VSTATOE | RDOE;
  assign DOUT = VSTATOE ? vstat : RDOE ? vread : rf_out;
  assign DBUS_FIGHT = (RDBKOE & VSTATOE) | (RDBKOE & RDOE) | (VSTATOE & RDOE);

  assign WAIT_OE = WAITN_OE;
  assign IRQ_OE  = IRQN_OE;

  // ---- back doors for the benches -----------------------------------------
  // verilator lint_off UNUSEDSIGNAL
  task automatic poke(input int addr, input logic [7:0] v);
    vram[addr[18:0]] = v;
  endtask
  function automatic logic [7:0] peek(input int addr);
    peek = vram[addr[18:0]];
  endfunction
  task automatic poke_lut(input int a, input logic [15:0] v);
    lut[a[15:0]] = v;
  endtask
  function automatic logic [15:0] peek_lut(input int a);
    peek_lut = lut[a[15:0]];
  endfunction
  function automatic logic [7:0] peek_rf(input int a);
    peek_rf = rf[a[4:0]];
  endfunction
  // verilator lint_on UNUSEDSIGNAL

endmodule
`default_nettype wire
