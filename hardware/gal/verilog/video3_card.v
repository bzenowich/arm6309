// video3, wired: v3dot + v3scan + v3ptr + v3host + v3lane, and the discrete
// parts of video3/docs/plan.md §13.1 around them - the two AS6C8016
// framebuffer parts and their four lane '245s, the 32K x 8 register file, the
// fetch ranks, the '153 pixel mux, the index '574, the four sprite '165s, the
// 64K x 16 LUT and its output '273s, the PIDX and PDAT latches, the
// posted-write and vread '574s, and the VSTAT '244 and the host '245 onto the
// backplane.
//
// ⭐ EVERY NET BETWEEN TWO PARTS IS THE TERM LISTS' OWN. The wire list and the
// five instance port maps are GENERATED - v3portmap.ts, run by gen.ts, rewrites
// them between their two markers from the .cpld.ts / .jedec.ts inputs and
// EXTERNAL sets - so ⚠ edit the parts, not that region. A port a part does not
// let out of its package is not connected here, so a buried cell cannot become
// a net by being mentioned. reach.check.ts's census rule, restated for a
// board. Everything from THE BOARD down is hand-written, and ⭐ it reaches into
// no part: `grep -c 'u_[a-z]*\.' video3_card.v` is zero outside the back doors.
// It was seven, GAP_1..GAP_7, each a signal the board needed and no package
// let out; plan.md §14 item 18 has what closed each.
//
// ⭐ THE BUSES ARE RESOLVED, NOT CHOSEN. The card's internal data bus (IDB),
// the framebuffer's address (FBA18..FBA2), each byte lane and the LUT's high
// address byte are modelled as nets with explicit drivers, each driver behind
// its own enable, and every dot counts how many drive: two is a FIGHT, and a
// sample taken with none is a FLOAT. A model that picks one driver by
// priority cannot see either (CLAUDE.md: "a model that ORs its drivers cannot
// see a bus fight").
//
// WHAT IS MODELLED is the logic, as every wrapper here: memories read
// combinationally on the address the parts drive and written on the dot the
// strobe is asserted. Propagation delay, the switch matrix and placement are
// cpld/*.fit's business.

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

    // board-level fights and floats, which no single part can see
    output wire        FBA_FIGHT,  // two parts on one framebuffer address bit
    output wire        DBUS_FIGHT, // two of the host '245, the '244 and vread on D
    output wire        LUTA_FIGHT, // two masters on a LUT address bit
    output wire        IDB_FIGHT,  // two drivers on the internal data bus
    output wire        IDB_FLOAT,  // IDB sampled with nothing driving it
    output wire        LANE_FLOAT, // a byte written from a lane nothing drives
    output wire        RANK_FIGHT  // a chip's two fetch ranks both on, or neither
);

  wire D0, D1, D2, D3, D4, D5, D6, D7;
  wire PA0, PA1, PA2, PA3, PA4, PA5, PA6, PA7;
  wire PB0, PB1, PB2, PB3, PB4, PB5, PB6, PB7;
  wire A0 = PA[0], A1 = PA[1], A2 = PA[2], A3 = PA[3], A4 = PA[4];
  wire A5 = PA[5], A6 = PA[6], A19 = PA[19], A20 = PA[20];

  // ---- every net that leaves a package ------------------------------------
  wire ATO0, ATO0_OE, ATO1, ATO1_OE, ATO2, ATO2_OE, ATO3, ATO3_OE, ATO4, ATO4_OE, ATO5,
       ATO5_OE, ATO6, ATO6_OE, ATO7, ATO7_OE, ATOE, CBUSY, CDONE, CEOR, CHLAST, CPURF,
       CRDSEL, CROWADV, CSTEP, CWLOAD, DIR, DP0, DP1, FBOEPTR, GCPY, GRD, GSPN, HBLANK,
       HLOAD, IRQN, IRQN_OE, IRQPEND, KEY, LANE0, LANE1, LB0, LB1, LDPDATH, LDPDATL,
       LDPIDXH, LDPIDXL, LOE0, LOE1, LOE2, LOE3, LUTWE, MODE0, MODE1, MRQ, MUXSEL0,
       MUXSEL1, OEA0, OEA1, OEA2, OEB0, OEB1, OEB2, OMR, PALTURN, PBUSY, PIDXCE, PIDXOE,
       PIXOE, PWCK, PWOE, RA0, RA1, RA2, RA3, RA4, RCPY, RDBKOE, RDCK, RDOE, RDREQ, REGWR,
       RETIRE, RFA0, RFA1, RFA2, RFA3, RFA4, RFOE, ROWADV, RP1, RP2, RP3, RP4, SPANBUSY,
       SPARE, SPRA0, SPRA0_OE, SPRA1, SPRA1_OE, SPRLD, SPRSH, SQ0, SQ1, UB0, UB1, VBLANK,
       VSTATOE, VWE, WAITN, WAITN_OE, WM0, WM1, WROWADV, WSTART, WSTB, WSTBV, WSTEP,
       dot_FBA2, dot_FBA2_OE, dot_FBA3, dot_FBA3_OE, dot_FBA4, dot_FBA4_OE, dot_FBA5,
       dot_FBA5_OE, ptr_FBA10, ptr_FBA10_OE, ptr_FBA11, ptr_FBA11_OE, ptr_FBA12,
       ptr_FBA12_OE, ptr_FBA13, ptr_FBA13_OE, ptr_FBA14, ptr_FBA14_OE, ptr_FBA15,
       ptr_FBA15_OE, ptr_FBA16, ptr_FBA16_OE, ptr_FBA17, ptr_FBA17_OE, ptr_FBA18,
       ptr_FBA18_OE, ptr_FBA2, ptr_FBA2_OE, ptr_FBA3, ptr_FBA3_OE, ptr_FBA4, ptr_FBA4_OE,
       ptr_FBA5, ptr_FBA5_OE, ptr_FBA6, ptr_FBA6_OE, ptr_FBA7, ptr_FBA7_OE, ptr_FBA8,
       ptr_FBA8_OE, ptr_FBA9, ptr_FBA9_OE, scan_FBA10, scan_FBA10_OE, scan_FBA11,
       scan_FBA11_OE, scan_FBA12, scan_FBA12_OE, scan_FBA13, scan_FBA13_OE, scan_FBA14,
       scan_FBA14_OE, scan_FBA15, scan_FBA15_OE, scan_FBA16, scan_FBA16_OE, scan_FBA17,
       scan_FBA17_OE, scan_FBA18, scan_FBA18_OE, scan_FBA2, scan_FBA2_OE, scan_FBA3,
       scan_FBA3_OE, scan_FBA4, scan_FBA4_OE, scan_FBA5, scan_FBA5_OE, scan_FBA6,
       scan_FBA6_OE, scan_FBA7, scan_FBA7_OE, scan_FBA8, scan_FBA8_OE, scan_FBA9,
       scan_FBA9_OE;

  // ---- the five parts: generated port maps --------------------------------
  v3dot u_dot (
    .CLK25(CLK25), .RESET(RESET), .D0(D0), .D1(D1), .D2(D2), .D3(D3), .D4(D4), .D5(D5),
    .D6(D6), .D7(D7), .REGWR(REGWR), .RA0(RA0), .RA1(RA1), .RA2(RA2), .RA3(RA3), .RA4(RA4),
    .RDREQ(RDREQ), .RCPY(RCPY), .SPANBUSY(SPANBUSY), .PALTURN(PALTURN), .SQ0(SQ0),
    .SQ1(SQ1), .LDPIDXL(LDPIDXL), .LDPIDXH(LDPIDXH), .LDPDATL(LDPDATL), .LDPDATH(LDPDATH),
    .DP0(DP0), .DP1(DP1), .SPRA0(SPRA0), .SPRA0_OE(SPRA0_OE), .SPRA1(SPRA1),
    .SPRA1_OE(SPRA1_OE), .HBLANK(HBLANK), .HSYNC(HSYNC), .VSYNC(VSYNC), .VBLANK(VBLANK),
    .BLANK(BLANK), .SPARE(SPARE), .HLOAD(HLOAD), .ROWADV(ROWADV), .MRQ(MRQ),
    .MUXSEL0(MUXSEL0), .MUXSEL1(MUXSEL1), .PIXOE(PIXOE), .ATOE(ATOE), .PIDXOE(PIDXOE),
    .OMR(OMR), .OEA0(OEA0), .OEB0(OEB0), .OEA1(OEA1), .OEB1(OEB1), .OEA2(OEA2), .OEB2(OEB2),
    .SPRSH(SPRSH), .SPRLD(SPRLD), .FBA2(dot_FBA2), .FBA2_OE(dot_FBA2_OE), .FBA3(dot_FBA3),
    .FBA3_OE(dot_FBA3_OE), .FBA4(dot_FBA4), .FBA4_OE(dot_FBA4_OE), .FBA5(dot_FBA5),
    .FBA5_OE(dot_FBA5_OE), .GRD(GRD), .GCPY(GCPY), .GSPN(GSPN), .FBOEPTR(FBOEPTR),
    .MODE0(MODE0), .MODE1(MODE1), .WM0(WM0), .WM1(WM1)
  );

  v3scan u_scan (
    .CLK25(CLK25), .RESET(RESET), .DP0(DP0), .DP1(DP1), .MRQ(MRQ), .HLOAD(HLOAD),
    .VBLANK(VBLANK), .ROWADV(ROWADV), .MODE0(MODE0), .MODE1(MODE1), .ATOE(ATOE), .D0(D0),
    .D1(D1), .D2(D2), .D3(D3), .D4(D4), .D5(D5), .D6(D6), .D7(D7), .PB0(PB0), .PB1(PB1),
    .PB2(PB2), .PB3(PB3), .PB4(PB4), .PB5(PB5), .PB6(PB6), .PB7(PB7), .PA0(PA0), .PA1(PA1),
    .PA2(PA2), .PA3(PA3), .PA4(PA4), .PA5(PA5), .PA6(PA6), .PA7(PA7), .REGWR(REGWR),
    .RA0(RA0), .RA1(RA1), .RA2(RA2), .RA3(RA3), .RA4(RA4), .ATO0(ATO0), .ATO0_OE(ATO0_OE),
    .ATO1(ATO1), .ATO1_OE(ATO1_OE), .ATO2(ATO2), .ATO2_OE(ATO2_OE), .ATO3(ATO3),
    .ATO3_OE(ATO3_OE), .ATO4(ATO4), .ATO4_OE(ATO4_OE), .ATO5(ATO5), .ATO5_OE(ATO5_OE),
    .ATO6(ATO6), .ATO6_OE(ATO6_OE), .ATO7(ATO7), .ATO7_OE(ATO7_OE), .FBA2(scan_FBA2),
    .FBA2_OE(scan_FBA2_OE), .FBA3(scan_FBA3), .FBA3_OE(scan_FBA3_OE), .FBA4(scan_FBA4),
    .FBA4_OE(scan_FBA4_OE), .FBA5(scan_FBA5), .FBA5_OE(scan_FBA5_OE), .FBA6(scan_FBA6),
    .FBA6_OE(scan_FBA6_OE), .FBA7(scan_FBA7), .FBA7_OE(scan_FBA7_OE), .FBA8(scan_FBA8),
    .FBA8_OE(scan_FBA8_OE), .FBA9(scan_FBA9), .FBA9_OE(scan_FBA9_OE), .FBA10(scan_FBA10),
    .FBA10_OE(scan_FBA10_OE), .FBA11(scan_FBA11), .FBA11_OE(scan_FBA11_OE),
    .FBA12(scan_FBA12), .FBA12_OE(scan_FBA12_OE), .FBA13(scan_FBA13),
    .FBA13_OE(scan_FBA13_OE), .FBA14(scan_FBA14), .FBA14_OE(scan_FBA14_OE),
    .FBA15(scan_FBA15), .FBA15_OE(scan_FBA15_OE), .FBA16(scan_FBA16),
    .FBA16_OE(scan_FBA16_OE), .FBA17(scan_FBA17), .FBA17_OE(scan_FBA17_OE),
    .FBA18(scan_FBA18), .FBA18_OE(scan_FBA18_OE)
  );

  v3ptr u_ptr (
    .CLK25(CLK25), .RESET(RESET), .D0(D0), .D1(D1), .D2(D2), .D3(D3), .D4(D4), .D5(D5),
    .D6(D6), .D7(D7), .WSTBV(WSTBV), .WSTART(WSTART), .WM0(WM0), .WM1(WM1), .DP0(DP0),
    .RP1(RP1), .RP2(RP2), .RP3(RP3), .RP4(RP4), .WSTEP(WSTEP), .CPURF(CPURF), .GSPN(GSPN),
    .CDONE(CDONE), .CSTEP(CSTEP), .CROWADV(CROWADV), .CWLOAD(CWLOAD), .CRDSEL(CRDSEL),
    .REGWR(REGWR), .RA0(RA0), .RA1(RA1), .RA2(RA2), .RA3(RA3), .RA4(RA4), .FBOEPTR(FBOEPTR),
    .CEOR(CEOR), .CHLAST(CHLAST), .CBUSY(CBUSY), .SPANBUSY(SPANBUSY), .RETIRE(RETIRE),
    .VWE(VWE), .WROWADV(WROWADV), .RFA0(RFA0), .FBA2(ptr_FBA2), .FBA2_OE(ptr_FBA2_OE),
    .FBA3(ptr_FBA3), .FBA3_OE(ptr_FBA3_OE), .FBA4(ptr_FBA4), .FBA4_OE(ptr_FBA4_OE),
    .FBA5(ptr_FBA5), .FBA5_OE(ptr_FBA5_OE), .FBA6(ptr_FBA6), .FBA6_OE(ptr_FBA6_OE),
    .FBA7(ptr_FBA7), .FBA7_OE(ptr_FBA7_OE), .FBA8(ptr_FBA8), .FBA8_OE(ptr_FBA8_OE),
    .FBA9(ptr_FBA9), .FBA9_OE(ptr_FBA9_OE), .FBA10(ptr_FBA10), .FBA10_OE(ptr_FBA10_OE),
    .FBA11(ptr_FBA11), .FBA11_OE(ptr_FBA11_OE), .FBA12(ptr_FBA12), .FBA12_OE(ptr_FBA12_OE),
    .FBA13(ptr_FBA13), .FBA13_OE(ptr_FBA13_OE), .FBA14(ptr_FBA14), .FBA14_OE(ptr_FBA14_OE),
    .FBA15(ptr_FBA15), .FBA15_OE(ptr_FBA15_OE), .FBA16(ptr_FBA16), .FBA16_OE(ptr_FBA16_OE),
    .FBA17(ptr_FBA17), .FBA17_OE(ptr_FBA17_OE), .FBA18(ptr_FBA18), .FBA18_OE(ptr_FBA18_OE),
    .LANE0(LANE0), .LANE1(LANE1)
  );

  v3host u_host (
    .CLK25(CLK25), .RESET(RESET), .IOSEL(IOSEL), .IOPGH(IOPGH), .A0(A0), .A1(A1), .A2(A2),
    .A3(A3), .A4(A4), .A5(A5), .A6(A6), .A19(A19), .A20(A20), .E(E), .RW(RW),
    .SPANBUSY(SPANBUSY), .CBUSY(CBUSY), .VBLANK(VBLANK), .HLOAD(HLOAD), .RETIRE(RETIRE),
    .GRD(GRD), .D6(D6), .CEOR(CEOR), .CHLAST(CHLAST), .GCPY(GCPY), .DP0(DP0),
    .WROWADV(WROWADV), .REGWR(REGWR), .RA0(RA0), .RA1(RA1), .RA2(RA2), .RA3(RA3), .RA4(RA4),
    .PALTURN(PALTURN), .PBUSY(PBUSY), .LUTWE(LUTWE), .PIDXCE(PIDXCE), .WSTBV(WSTBV),
    .WSTART(WSTART), .WSTB(WSTB), .WSTEP(WSTEP), .RDCK(RDCK), .PWCK(PWCK), .RDOE(RDOE),
    .RDREQ(RDREQ), .WAITN(WAITN), .WAITN_OE(WAITN_OE), .IRQPEND(IRQPEND), .IRQN(IRQN),
    .IRQN_OE(IRQN_OE), .VSTATOE(VSTATOE), .RDBKOE(RDBKOE), .CRDSEL(CRDSEL), .DIR(DIR),
    .CSTEP(CSTEP), .CROWADV(CROWADV), .CWLOAD(CWLOAD), .CDONE(CDONE), .RCPY(RCPY),
    .RP1(RP1), .RP2(RP2), .RP3(RP3), .RP4(RP4), .RFA1(RFA1), .RFA2(RFA2), .RFA3(RFA3),
    .RFA4(RFA4), .CPURF(CPURF)
  );

  v3lane u_lane (
    .LANE0(LANE0), .LANE1(LANE1), .CRDSEL(CRDSEL), .GRD(GRD), .GCPY(GCPY), .GSPN(GSPN),
    .WM0(WM0), .WM1(WM1), .VWE(VWE), .WSTBV(WSTBV), .KEY(KEY), .LOE0(LOE0), .LOE1(LOE1),
    .LOE2(LOE2), .LOE3(LOE3), .LB0(LB0), .UB0(UB0), .LB1(LB1), .UB1(UB1), .PWOE(PWOE),
    .RFOE(RFOE)
  );

  // ======================================================================
  // THE BOARD
  // ======================================================================

  // ---- the framebuffer's address: three parts, per-bit enables --------------
  // v3scan (the display half, the map and the sprite's base), v3ptr (a byte
  // access) and v3dot (the sprite's row, FBA5..FBA2). The arbiter's grants
  // decide; two on one bit is a fight on the board.
  wire [16:0] scan_fba = {scan_FBA18, scan_FBA17, scan_FBA16, scan_FBA15, scan_FBA14,
                          scan_FBA13, scan_FBA12, scan_FBA11, scan_FBA10, scan_FBA9,
                          scan_FBA8, scan_FBA7, scan_FBA6, scan_FBA5, scan_FBA4,
                          scan_FBA3, scan_FBA2};
  wire [16:0] scan_oe  = {scan_FBA18_OE, scan_FBA17_OE, scan_FBA16_OE, scan_FBA15_OE,
                          scan_FBA14_OE, scan_FBA13_OE, scan_FBA12_OE, scan_FBA11_OE,
                          scan_FBA10_OE, scan_FBA9_OE, scan_FBA8_OE, scan_FBA7_OE,
                          scan_FBA6_OE, scan_FBA5_OE, scan_FBA4_OE, scan_FBA3_OE,
                          scan_FBA2_OE};
  wire [16:0] ptr_fba  = {ptr_FBA18, ptr_FBA17, ptr_FBA16, ptr_FBA15, ptr_FBA14,
                          ptr_FBA13, ptr_FBA12, ptr_FBA11, ptr_FBA10, ptr_FBA9,
                          ptr_FBA8, ptr_FBA7, ptr_FBA6, ptr_FBA5, ptr_FBA4,
                          ptr_FBA3, ptr_FBA2};
  wire [16:0] ptr_oe   = {ptr_FBA18_OE, ptr_FBA17_OE, ptr_FBA16_OE, ptr_FBA15_OE,
                          ptr_FBA14_OE, ptr_FBA13_OE, ptr_FBA12_OE, ptr_FBA11_OE,
                          ptr_FBA10_OE, ptr_FBA9_OE, ptr_FBA8_OE, ptr_FBA7_OE,
                          ptr_FBA6_OE, ptr_FBA5_OE, ptr_FBA4_OE, ptr_FBA3_OE,
                          ptr_FBA2_OE};
  wire [16:0] dot_fba  = {13'd0, dot_FBA5, dot_FBA4, dot_FBA3, dot_FBA2};
  wire [16:0] dot_oe   = {13'd0, dot_FBA5_OE, dot_FBA4_OE, dot_FBA3_OE, dot_FBA2_OE};
  wire [16:0] fba = (scan_oe & scan_fba) | (ptr_oe & ptr_fba) | (dot_oe & dot_fba);
  assign FBA_FIGHT = |((scan_oe & ptr_oe) | (scan_oe & dot_oe) | (ptr_oe & dot_oe));

  reg [7:0] vram [0:524287];
  wire [7:0] lane_rd [0:3];
  assign lane_rd[0] = vram[{fba, 2'd0}];
  assign lane_rd[1] = vram[{fba, 2'd1}];
  assign lane_rd[2] = vram[{fba, 2'd2}];
  assign lane_rd[3] = vram[{fba, 2'd3}];

  // ---- IDB, the card's internal data bus, and its five drivers ------------
  //   the host '245   RDBKOE with DIR = R/W: inbound on a card write
  //   the register file  RFOE (v3lane), and never while WSTB writes it
  //   the posted-write '574's Q   PWOE (v3lane)
  //   a lane '245     its LOE with DIR low (v3host): the prefetch, the copy's read
  // The CPLDs' D inputs, the file's I/O, vread's D, the '574's D and the
  // palette latches all read it.
  wire [3:0] loe = {LOE3, LOE2, LOE1, LOE0};
  wire [1:0] lane_n = LOE3 ? 2'd3 : LOE2 ? 2'd2 : LOE1 ? 2'd1 : 2'd0;
  wire drv_host = RDBKOE & ~RW;
  wire drv_rf   = RFOE & ~WSTB;
  wire drv_pw   = PWOE;
  wire drv_lane = (|loe) & ~DIR;
  wire [2:0] n_idb = {2'd0, drv_host} + {2'd0, drv_rf} + {2'd0, drv_pw} + {2'd0, drv_lane};
  wire [7:0] rf_out, pw_q;
  wire [7:0] IDB = drv_host ? DIN : drv_pw ? pw_q : drv_lane ? lane_rd[lane_n]
                 : drv_rf ? rf_out : 8'h00;
  assign {D7, D6, D5, D4, D3, D2, D1, D0} = IDB;
  assign IDB_FIGHT = n_idb > 3'd1;
  // A float is only a defect when something SAMPLES the bus: the file's write,
  // the two '574s, vread, a palette latch, the reload walk, or a span or copy
  // write taking its byte from a lane '245.
  wire idb_sampled = WSTB | PWCK | RDCK | LDPIDXL | LDPIDXH | LDPDATL | LDPDATH
                   | RP1 | RP2 | RP3 | RP4 | (VWE & DIR);
  assign IDB_FLOAT = idb_sampled & (n_idb == 3'd0);

  // ---- the copy's colour key: one 8-input NOR (keyed-copy.md) -------------
  // ⭐ THE BYTE ABOUT TO BE WRITTEN IS ALREADY ON IDB. A copy's write access
  // drives the posted-write '574 onto the bus for both its dots (PWOE), so the
  // compare has the whole access to settle and gates VWE at the tick - no
  // pipeline register, where comparing during the READ access would have
  // needed one and left about 5 ns of margin. The key is ZERO: a 74HC4078
  // against a '688's key register is a DIP-14 against a DIP-20, and the board
  // has room for exactly one of them (check:place).
  assign KEY = ~|IDB;

  // ---- the register file: 32 bytes of the 32K x 8 (plan §5) --------------
  // /WE is WSTB; the address is RFA - bit 0 is v3ptr's, because §5 makes it
  // the span-mask bit, and bits 4..1 are v3host's with the reload walk.
  wire [4:0] rfa = {RFA4, RFA3, RFA2, RFA1, RFA0};
  reg  [7:0] rf [0:31];
  assign rf_out = rf[rfa];
  always @(posedge CLK25) if (WSTB) rf[rfa] <= IDB;

  // ---- the posted-write and vread '574s (plan §5, §6, §11) ----------------
  // Both clocks are ACTIVE LOW on the pins, so the '574 takes the bus on the
  // edge that ENDS the strobe - modelled as the last dot of it.
  reg [7:0] pw, vread;
  assign pw_q = pw;
  always @(posedge CLK25) if (PWCK) pw <= IDB;
  always @(posedge CLK25) if (RDCK) vread <= IDB;

  // ---- the lanes: a '245 each, and the byte enables (v3lane) -------------
  // A lane is driven onto the SRAM by its '245 when that lane's LOE is on and
  // DIR says write; /WE is VWE on both parts, and the byte enables pick the
  // byte. Writing a byte whose lane nothing drives is a float.
  wire [3:0] be = {UB1, LB1, UB0, LB0};
  reg lane_float;
  integer li;
  always @(*) begin
    lane_float = 1'b0;
    for (li = 0; li < 4; li = li + 1)
      if (VWE & be[li] & ~(loe[li] & DIR)) lane_float = 1'b1;
  end
  assign LANE_FLOAT = lane_float;
  always @(posedge CLK25) if (VWE) begin
    if (LB0 & LOE0 & DIR) vram[{fba, 2'd0}] <= IDB;
    if (UB0 & LOE1 & DIR) vram[{fba, 2'd1}] <= IDB;
    if (LB1 & LOE2 & DIR) vram[{fba, 2'd2}] <= IDB;
    if (UB1 & LOE3 & DIR) vram[{fba, 2'd3}] <= IDB;
  end

  // ---- the map word: v3scan's PB and PA are the two parts' LOW bytes -------
  // ⭐ LANE 0 AND LANE 2, not 0 and 1: a cell is a four-byte group with the
  // code at +0 and the attribute at +2 (plan §2.5), so that WPTR's step-by-two
  // reaches both with one write each - two stores a character, as a two-byte
  // cell had. v3scan may be wired to any two lanes; what it cannot have is all
  // four.
  assign {PB7, PB6, PB5, PB4, PB3, PB2, PB1, PB0} = lane_rd[0];
  assign {PA7, PA6, PA5, PA4, PA3, PA2, PA1, PA0} = lane_rd[2];

  // ---- the fetch ranks: eight '574 (plan §2.3, graphics.md §8.2) ---------
  // Clocked by SPARE's rising edge - the edge that ends the display access,
  // dot 3 into dot 0 - which is when this dot is dot 3: SPARE low, DP0 high.
  wire fclk = ~SPARE & DP0;
  reg [7:0] fa0, fa1, fa2, fa3, fb0, fb1, fb2, fb3;
  always @(posedge CLK25) if (fclk) begin
    fb0 <= fa0; fb1 <= fa1; fb2 <= fa2; fb3 <= fa3;
    fa0 <= lane_rd[0]; fa1 <= lane_rd[1]; fa2 <= lane_rd[2]; fa3 <= lane_rd[3];
  end

  // Each chip's '153 input is ONE of its two ranks, by output enable: rank A
  // (the next group) exactly when the chip is below the fine scroll. Chip 3's
  // pair is strapped: A off, B on.
  wire [3:0] oea = {1'b0, OEA2, OEA1, OEA0};
  wire [3:0] oeb = {1'b1, OEB2, OEB1, OEB0};
  assign RANK_FIGHT = |((oea & oeb) | (~oea & ~oeb));
  wire [7:0] l0 = OEA0 ? fa0 : fb0, l1 = OEA1 ? fa1 : fb1;
  wire [7:0] l2 = OEA2 ? fa2 : fb2, l3 = fb3;
  wire [1:0] sel = {MUXSEL1, MUXSEL0};
  wire [7:0] pix = sel == 2'd0 ? l0 : sel == 2'd1 ? l1 : sel == 2'd2 ? l2 : l3;

  // ---- the index '574: every dot (plan §3) --------------------------------
  reg [7:0] pixidx;
  always @(posedge CLK25) pixidx <= pix;

  // ---- the sprite: four '165, two cascaded a plane (plan §7) ---------------
  // /PL is SPRLD, while the sprite's row is on the lanes: plane 0's two bytes
  // are lanes 0 and 1, plane 1's lanes 2 and 3. CLK INH is !SPRSH. The far
  // '165's serial input is tied low, so after sixteen shifts the chain shows
  // zero - transparent - for the rest of the line.
  reg [15:0] sp0, sp1;
  always @(posedge CLK25)
    if (SPRLD) begin
      sp0 <= {lane_rd[0], lane_rd[1]};
      sp1 <= {lane_rd[2], lane_rd[3]};
    end else if (SPRSH) begin
      sp0 <= {sp0[14:0], 1'b0};
      sp1 <= {sp1[14:0], 1'b0};
    end
  assign SQ0 = sp0[15];
  assign SQ1 = sp1[15];

  // ---- the palette write path (plan §10, graphics.md §13.1) ---------------
  // PIDX low: two '163, parallel load; PIDX high: a '574; PDATL and PDATH:
  // two '573. v3dot decodes all four strobes off the broadcast.
  reg [7:0] pidx_lo, pidx_hi, pdatl, pdath;
  always @(posedge CLK25) begin
    if (LDPIDXL)     pidx_lo <= IDB;
    else if (PIDXCE) pidx_lo <= pidx_lo + 8'd1;
    if (LDPIDXH)     pidx_hi <= IDB;
    if (LDPDATL)     pdatl   <= IDB;
    if (LDPDATH)     pdath   <= IDB;
  end

  // ---- the LUT's address: three masters on the high byte, two on the low ---
  // A15..A8: the PIDX-high '244 (PIDXOE), v3scan's ATO (character mode, its
  // own enables) and v3dot's SPRA on A9..A8 (bitmap and tile). Pulled low
  // where nothing drives - tile mode's sub-palette 0.
  wire [7:0] ato    = {ATO7, ATO6, ATO5, ATO4, ATO3, ATO2, ATO1, ATO0};
  wire [7:0] ato_oe = {ATO7_OE, ATO6_OE, ATO5_OE, ATO4_OE, ATO3_OE, ATO2_OE, ATO1_OE, ATO0_OE};
  wire [7:0] spr    = {6'd0, SPRA1, SPRA0};
  wire [7:0] spr_oe = {6'd0, SPRA1_OE, SPRA0_OE};
  wire [7:0] pid_oe = {8{PIDXOE}};
  wire [7:0] lut_hi = (pid_oe & pidx_hi) | (ato_oe & ato) | (spr_oe & spr);
  wire [7:0] lut_lo = PIDXOE ? pidx_lo : PIXOE ? pixidx : 8'h00;
  wire [15:0] lut_a = {lut_hi, lut_lo};
  assign LUTA_FIGHT = |((pid_oe & ato_oe) | (pid_oe & spr_oe) | (ato_oe & spr_oe))
                    | (PIDXOE & PIXOE);
  reg [15:0] lut [0:65535];
  always @(posedge CLK25) if (LUTWE) lut[lut_a] <= {pdath, pdatl};

  // The two '273: /MR is OMR (v3dot: BLANK two registers late), so a blanked
  // dot is 0 V (plan §9.2). ⚠ /MR IS ASYNCHRONOUS on a '273 - it forces the
  // outputs low while it is asserted, whatever the clock does - so it gates the
  // register's OUTPUT, not what the register captures. PIXOE is the LUT's /OE
  // too: through a palette turn the LUT's data pins are the '573s'.
  reg [15:0] rgb_q;
  always @(posedge CLK25) rgb_q <= PIXOE ? lut[lut_a] : 16'h0000;
  assign RGB = OMR ? rgb_q : 16'h0000;

  // ---- D7..D0: the host '245 outbound, the VSTAT '244 and vread ------------
  wire [7:0] vstat = {SPANBUSY, VBLANK, HBLANK, CBUSY, 2'b00, PBUSY, IRQPEND};
  wire drv_rdbk = RDBKOE & RW;
  assign DOE  = drv_rdbk | VSTATOE | RDOE;
  assign DOUT = VSTATOE ? vstat : RDOE ? vread : IDB;
  assign DBUS_FIGHT = (drv_rdbk & VSTATOE) | (drv_rdbk & RDOE) | (VSTATOE & RDOE);

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
