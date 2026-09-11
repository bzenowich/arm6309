// The audio card, wired: U1 (audio.v), U2 (aseq.v) and the datapath they
// drive.  audio.md 10.2.2 is the parts list and this is the same list as
// behaviour - the state file, the sample RAM, the free-running counter, the
// comparator, the adder chain, the six three-state things that may drive the
// two internal buses, the converter port registers and the host's three
// latches.
//
// HAND-WRITTEN, like video_card.v. The two CPLDs are generated; this is the
// board between them, and it is where a claim about the card rather than about
// a part gets to be true or false.
//
// A comment line here must never begin with the simulator's own name.

`default_nettype none

module audio_card (
    input  wire        SLOTCLK,
    input  wire        RESET,
    // the backplane's I/O port
    input  wire        IOSEL,
    input  wire        E,
    input  wire        RW,
    input  wire [6:0]  A,
    inout  wire [7:0]  HD,
    output wire        FIRQ_OE,
    // observation, for the testbench only
    output wire [15:0] COUNT,
    output wire [7:0]  DACSAMP0, DACSAMP1, DACSAMP2, DACSAMP3,
    output wire [7:0]  DACVOL0,  DACVOL1,  DACVOL2,  DACVOL3
);

  // ---------------------------------------------------------------- U1 ---
  wire S0, S1, S2, CCLK, SEL, NEQL, NEQH;
  // ⭐ CIACLK is gone - audio.md 16 item 42, 2026-09-10. It was 8.2's ÷5 tempo
  // clock on a pin, and the timer is counted by U2's microcode against the
  // shared adder, so nothing on this board ever took it. The pin it frees is
  // where 6.1's ×4 select goes.
  wire DMAEN0,DMAEN1,DMAEN2,DMAEN3, FIRQ;
  wire CTRL0,CTRL1,CTRL2,CTRL3,CTRL4,CTRL5,CTRL6,CTRL7;
  wire SETA,SETB,SETC, PWBUSY, PFVALID;
  // U1 buried
  wire CHANSLOT, TMRSLOT, HOSTSLOT, DEFSLOT, WAIDX, WDMACON, WINTENA;
  wire WINTREQ, WCTRL, RINTREQ, RASTAT, P0, P1, P2, ENA0, ENA1, ENA2, ENA3;
  wire ENA4, ENA5, PEND0, PEND1, PEND2, PEND3, PEND4, PEND5, REQ0, REQ1;
  wire REQ2, REQ3, REQ4, REQ5, SET0, SET1, SET2, SET3, SET4, SET5, CT0;
  wire CT1, CT2, CT3, CT4, CT5, CT6, CT7, CT8, CT9, CT10, CT11, CT12, CT13;
  wire CT14, CT15, EQ0, EQ1, EQ2, EQ3, PF0, PF1, PF2, PF3, PF4, PF5, PF6;
  wire PF7, SYNCR1, SYNCR2, MERGE, FIRQANY, HRD, RPF, SD0_OE;
  wire SD1_OE, SD2_OE, SD3_OE, SD4_OE, SD5_OE, SD6_OE, SD7_OE, SD8_OE;
  wire SD9_OE, SD10_OE, SD11_OE, SD12_OE, SD13_OE, SD14_OE, SD15_OE, D0_OE;
  wire D1_OE, D2_OE, D3_OE, D4_OE, D5_OE, D6_OE, D7_OE;
  audio u1 (
    .SLOTCLK(SLOTCLK), .RESET(RESET), .IOSEL(IOSEL), .E(E), .RW(RW),
    .A0(A[0]), .A1(A[1]), .A2(A[2]), .A3(A[3]),
    .A4(A[4]), .A5(A[5]), .A6(A[6]),
    .D0(HD[0]), .D1(HD[1]), .D2(HD[2]), .D3(HD[3]),
    .D4(HD[4]), .D5(HD[5]), .D6(HD[6]), .D7(HD[7]),
    .SETA(SETA), .SETB(SETB), .SETC(SETC),
    .PWBUSY(PWBUSY), .PFVALID(PFVALID),
    .SD0(SD[0]),   .SD1(SD[1]),   .SD2(SD[2]),   .SD3(SD[3]),
    .SD4(SD[4]),   .SD5(SD[5]),   .SD6(SD[6]),   .SD7(SD[7]),
    .SD8(SD[8]),   .SD9(SD[9]),   .SD10(SD[10]), .SD11(SD[11]),
    .SD12(SD[12]), .SD13(SD[13]), .SD14(SD[14]), .SD15(SD[15]),
    .*);

  // ---------------------------------------------------------------- U2 ---
  wire [5:0] SFA;
  wire       SFOE, SFWE0, SFWE1, SFWE2, SROE, SRWE, PFLANE;
  wire       ALATCK, BLATCK, BLATOE, ONESOE, CNTOE, ACIN, SUMOE, SBOE;

  wire       CVOEA, CVC0, CVC1, CVC2;
  wire       PFOE0, PFOE1, PFOE2, PFCK, PWCK, PWOE;
  wire       ACOUT;
  wire [23:0] SD;
  // U2's buried microprogram state, brought out so the testbench can watch a
  // sequence run. emit.ts makes every cell a port for exactly this reason.
  wire QCHAN, QTMR, RUN, WORKSLOT, T0, T1, T2, T3, LAST, RSTANY, DUEANY;
  wire START, BUSY, ENDNOW, WT0, WT1, WT2, WC0, WC1, RPICK0, RPICK1;
  wire RPICK2, RPICK3, DPICK0, DPICK1, DPICK2, DPICK3, DUE0, DUE1, DUE2;
  wire DUE3, CLR0, CLR1, CLR2, CLR3, TDUE, TACK, TQ, TARM, DMAQ0, DMAQ1;
  wire DMAQ2, DMAQ3, RST0, RST1, RST2, RST3, RCLR0, RCLR1, RCLR2, RCLR3;
  wire HSY1, HSY2, HSTB, HA0, HA1, HA2, HA3, HRW, HDUE, HACK, ISADATA, ISAIDX;
  wire ISSDATA, ISSPTR, ISTIMER, AIDXLD, AINC, AIDX0, AIDX1, AIDX2, AIDX3;
  wire AIDX4, AIDX5, HW0, HW1, HW2, HL0, HL1, HRO, HSTAGE, HCOMMIT;
  wire GBL, SDHCAP, SDHOE, SDQ0, SDQ1, SDQ2, CVBUSY, CVB;
  wire WROTE0, WROTE1, WROTE2, WROTE3, CVCSS, CVCSV, CVCSP, CVLD0, CVLD1;
  wire CVLD2, CVLD3, VDIRTY, VACK, FIRE0, FIRE1, FIRE2, FIRE3;
  wire FIRE4, FIRE5, NOFIRE, CHAIN1, SDH0_OE, SDH1_OE, SDH2_OE;

  aseq u2 (
    .SLOTCLK(SLOTCLK), .RESET(RESET),
    .S0(S0), .S1(S1), .S2(S2),
    .SEL(SEL), .E(E), .RW(RW),
    .A0(A[0]), .A1(A[1]), .A2(A[2]), .A3(A[3]),
    .D0(HD[0]), .D1(HD[1]), .D2(HD[2]), .D3(HD[3]), .D4(HD[4]), .D5(HD[5]),
    .NEQL(NEQL), .NEQH(NEQH), .ACOUT(ACOUT),
    .DMAEN0(DMAEN0), .DMAEN1(DMAEN1), .DMAEN2(DMAEN2), .DMAEN3(DMAEN3),
    .CTRL6(CTRL6), .CTRL7(CTRL7),
    .SFA0(SFA[0]), .SFA1(SFA[1]), .SFA2(SFA[2]),
    .SFA3(SFA[3]), .SFA4(SFA[4]), .SFA5(SFA[5]),
    .SDH0(SD[16]), .SDH1(SD[17]), .SDH2(SD[18]),
    .*);

  // ------------------------------------------------- the two buses -------
  // SD is the state file's 24 bits - lane 3 is not populated (10.2.1). BBUS is
  // the adder's B side AND the comparator's reference, which is the trick that
  // lets the free-running counter and the PER latch share one set of wires:
  // the compare only matters in the walk slots and the adder only in the work
  // slots. Both buses are pulled DOWN, so "nothing driving" is a hard zero -
  // which is how A+1 costs no package and how ACTRL b5 = 0 writes a zero into
  // a converter without a constant generator anywhere on the card.
  reg  [23:0] SF   [0:63];      // the state file: 2 x IS61C6416, lanes 0-2
  reg  [7:0]  SRAM [0:524287];  // the sample RAM: 1 x AS6C4008
  reg  [15:0] ALAT, BLAT, PWLAT;
  reg  [7:0]  SBLAT;
  reg  [7:0]  CVR0, CVR1, CVR2, CVR3;   // 4 converter port registers

  // 4.2's compare moved into U1 with the counter, so nothing outside compares
  // and the B bus is just the adder's second operand again.
  wire [15:0] BBUS = BLATOE ? BLAT : ONESOE ? 16'hFFFF : 16'h0000;
  wire [16:0] SUMX = {1'b0, ALAT} + {1'b0, BBUS} + {16'b0, ACIN};
  wire [15:0] SUM  = SUMX[15:0];
  assign      ACOUT = SUMX[16];

  wire [23:0] SFOUT = SF[SFA];
  // U1 drives these too, when W6 asks it for the count (10.2.3).
  assign SD[15:0]  = CNTOE ? 16'bz
                   : SFOE  ? SFOUT[15:0]  : SUMOE ? SUM
                   : PWOE  ? {PWLAT[7:0], PWLAT[7:0]} : 16'h0000;
  assign SD[23:19] = SFOE  ? SFOUT[23:19] : SBOE ? SBLAT[7:3]
                   : PWOE  ? PWLAT[7:3] : 5'b0;
  // SD[18:16] are U2's own pins; the file and the two byte sources share them.
  assign SD[18:16] = SDHOE ? 3'bzzz
                   : SFOE  ? SFOUT[18:16] : SBOE ? SBLAT[2:0]
                   : PWOE  ? PWLAT[2:0] : 3'b000;

  assign COUNT = {CT15,CT14,CT13,CT12,CT11,CT10,CT9,CT8,CT7,CT6,CT5,CT4,CT3,CT2,CT1,CT0};

  // The free-running colour-clock counter (2 x 74HC590), and the state file.
  // Writes land mid-slot, which is what the 74HC00 gating of 10.2.2 buys: the
  // address has settled and the pulse ends inside the slot.
  always @(negedge SLOTCLK) begin
    if (SFWE0) SF[SFA][7:0]   <= SD[7:0];
    if (SFWE1) SF[SFA][15:8]  <= SD[15:8];
    if (SFWE2) SF[SFA][23:16] <= SD[23:16];
    if (SRWE)  SRAM[SFOUT[18:0]] <= PWLAT[7:0];
    if (ALATCK) ALAT  <= SD[15:0];
    if (BLATCK) BLAT  <= SD[15:0];
    if (SROE)   SBLAT <= SRAM[SFOUT[18:0]];
    if (PWCK)   PWLAT <= {8'h00, HD};
    // 6.2's four port registers, clocked by the 74HC138 that 10.2.6's lever
    // put on CVC[2:0]: codes 1-4 are the clocks, 5-7 the three chip selects.
    if ({CVC2,CVC1,CVC0} == 3'd1) CVR0 <= SD[23:16];
    if ({CVC2,CVC1,CVC0} == 3'd2) CVR1 <= SD[23:16];
    if ({CVC2,CVC1,CVC0} == 3'd3) CVR2 <= SD[23:16];
    if ({CVC2,CVC1,CVC0} == 3'd4) CVR3 <= SD[23:16];
  end

  // 9.3's read-back is U1's now - it latches the byte off SD and drives the
  // host bus through the macrocells AINTREQ and ASTAT already use.

  // ----------------------------------------------- the six AD7528 --------
  // Each package's port is driven by one of two port registers, chosen by
  // CVOEA; its DAC A / DAC B select is the same bit. A rising /CS captures.
  // Classic MOD's fixed LRRL: channels 0 and 3 are the left summing node and
  // 1 and 2 the right, which is wiring and not logic. Four packages, eight
  // halves - one sample and one volume converter per channel.
  wire [7:0] PORTL = CVOEA ? CVR0 : CVR3;   // packages #1 #3 - ch0 and ch3
  wire [7:0] PORTR = CVOEA ? CVR1 : CVR2;   // packages #2 #4 - ch1 and ch2
  wire [2:0] CVCODE = {CVC2, CVC1, CVC0};
  reg [7:0] ds0, ds1, ds2, ds3, dv0, dv1, dv2, dv3;
  always @(posedge SLOTCLK) begin
    if (CVCODE == 3'd5) begin                     // the two sample packages
      if (CVOEA) begin ds0 <= PORTL; ds1 <= PORTR; end
      else       begin ds3 <= PORTL; ds2 <= PORTR; end
    end
    if (CVCODE == 3'd6) begin                     // the two volume packages
      if (CVOEA) begin dv0 <= PORTL; dv1 <= PORTR; end
      else       begin dv3 <= PORTL; dv2 <= PORTR; end
    end
  end
  assign {DACSAMP0,DACSAMP1,DACSAMP2,DACSAMP3} = {ds0,ds1,ds2,ds3};
  assign {DACVOL0, DACVOL1, DACVOL2, DACVOL3}  = {dv0,dv1,dv2,dv3};

endmodule
