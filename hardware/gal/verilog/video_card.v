// The video card, wired: vctrl + vaddr + vsup, the register file, the four
// interleaved framebuffer chips, the two ranks of fetch latch, the '153 pixel
// mux, and 9's palette LUT with its write path.
//
// ⭐ vsup IS THE THIRD ATF1508AS - graphics.md 10.1.7. It absorbs rfa, vlen and
// pxsel (three GAL22V10s, one package), and the room that buys is what 9's
// palette write path and 10.3.3's list register port are built in.
//
// ⭐ vshim.v IS GONE. It held every signal that was an input to a fitted part
// with no producer anywhere on the card - eleven of them - and after
// 2026-09-09's repairs there are none: the mask serialiser, the length
// counter, CTRL's and VSTAT's write strobes, HSCROLL[1:0], WADV, the span
// request, the list grant and the posted-VRAM-write strobe are all designs
// now. docs/design-review2.md V-1 to V-3.
//
// WHAT IS MODELLED. The logic, the interleave, the latch clocking and the mux.
// Memory is a 512 KB array read combinationally on the address the mux emits
// and captured at the end of the fetch half. Propagation delay is NOT modelled
// - that is what cpld/*.fit and graphics.md 6.1's dot-path budget are for -
// with one exception recorded in vaddr_tb: whether a signal carries the sub-
// slot phase at all is logic, not delay, and this model does see that.
//
// ONE BOARD-LEVEL RENAME, of the same kind as CPUA0 = A0 and VLOAD = VBLANK
// (video.cpld.ts):
//     vctrl.SPNA0/1  <-  vaddr.WA0/1     5.2.1's "SPNCHIP = WPTR[1:0]"
//
// WINC is vaddr's own cell now (it is RETIRE or the list engine's LADV, and
// the engine's advance was the thing that did not exist), and WROWADV is
// exported.

`default_nettype none

module video_card (
    input  wire        DOTCLK,
    input  wire        RESET,

    // the 6809 bus, as the card sees it
    input  wire        E,
    input  wire        RW,
    input  wire        IOSEL,
    input  wire        IOPAGE,     // asserted-high here: 1 = an $FF00-$FFFF cycle
    input  wire [20:0] PA,         // physical address
    input  wire [7:0]  DIN,

    output wire        WAIT_OE,
    output wire        IRQ_OE,

    // the picture
    output wire [7:0]  PIXEL,
    output wire        BLANK,
    output wire        HSYNC,
    output wire        VSYNC,

    // observation points for the testbenches
    output wire [7:0]  H,
    output wire [9:0]  V,
    output wire [1:0]  PH,
    output wire [18:2] FBA,
    output wire        LINEAR, TILESEL, MAPSEL, SPNGRANT, SPANBUSY, LRUN,
    output wire        RETIRE, WEN, SPANEND, MAPLD, MAPREQ, SLOTTICK, SPAREWIN,
    output wire [18:0] WPTR,
    output wire [7:0]  RD_o,
    output wire [1:0]  VMODE,
    output wire        VBLANK, HBLANK,
    // 10.3.2's descriptor engine, for vspan_tb: the held scroll value the
    // engine writes (HSCROLL[9:2] - HS0/HS1 are on vctrl), and its state.
    output wire [9:2]  HSCR,
    output wire        LPH_o, LWAIT_o,

    // ---- 9's palette, which had no write path at all until 2026-09-09 -----
    // RGB is what the connector sees: the LUT's 16-bit entry through the two
    // post-LUT '273s, whose /MR is BLANK (9.2's blank-to-black).
    output wire [15:0] RGB,
    output wire [7:0]  PIDX,          // the index vsup counts and drives
    output wire        PWE_o, PDOE_o, PIXOE_o,
    output wire        DBUS_FIGHT
);

  // ---- the three parts -----------------------------------------------------
  wire H0,H1,H2,H3,H4,H5,H6,H7, HBLANK_w;
  wire V0,V1,V2,V3,V4,V5,V6,V7,V8,V9, VTC, VBLANK_w, VSDLY, VBLPEND;
  wire IRQ;
  wire PH0, PH1, SPAREWIN_w;
  wire FCLK0,FCLK1,FCLK2,FCLK3, MUXSEL0, MUXSEL1;
  wire WROWADV_w; wire MCm0,MCm1,MCm2;
  wire GCPU0,GCPU1,GCPU2,GCPU3, GSPN0,GSPN1,GSPN2,GSPN3, WAIT;
  wire ACPU0,ACPU1,ACPU2,ACPU3;
  wire VMODE0,VMODE1,WM0,WM1,CELL,IRQEN,DISPEN;
  wire M0,HPOL,TILEMODE;
  wire TFETCH,MFETCH,FETCH,HLOAD,HEND,ROWADV,MCADV;
  wire SPNREQG, GMAP0,GMAP1,GMAP2,GMAP3, MAPHOLD, WAITSRC, WAITRW, VRAMSEL;
  wire SRC0, SRC1;
  wire MAPA0, MAPA1;

  wire WCTRL, VSTATWR, BCTRLGO, HS0, HS1, WADV0, WADV1, TC, MASKBIT, WSTBV;
  // WPQ / WSTART: the posted-write level delayed a dot, and the one-dot E-FALL
  // edge made from it. Added 2026-09-10 - SPANBUSY is set by WSTART, because a
  // level over E-high re-arms the span for ever once /WAIT stretches the cycle.
  // graphics.md 7.4, 19 item 37; video.cpld.ts has the derivation.
  wire WPQ, WSTART;
  wire SPNREQ, SPNTICK, LGRANT, CELLTICK, WINC;
  wire SR0,SR1,SR2,SR3,SR4,SR5,SR6,SR7;
  wire LDADV;

  wire [4:0] RA;
  wire WSTB_REG;                      // rfa's strobe: a write to $FF60-$FF7F

  wire WA0,WA1,WA2,WA3,WA4,WA5,WA6,WA7,WA8,WA9;
  wire WA10,WA11,WA12,WA13,WA14,WA15,WA16,WA17,WA18;
  wire SA2,SA3,SA4,SA5,SA6,SA7,SA8,SA9;
  wire SA10,SA11,SA12,SA13,SA14,SA15,SA16,SA17,SA18;
  wire FBA2,FBA3,FBA4,FBA5,FBA6,FBA7,FBA8,FBA9,FBA10;
  wire FBA11,FBA12,FBA13,FBA14,FBA15,FBA16,FBA17,FBA18;
  wire HS2,HS3,HS4,HS5,HS6,HS7,HS8,HS9;
  wire VS0,VS1,VS2,VS3,VS4,VS5,VS6,VS7,VS8;
  wire MAP0,MAP1,MAP2,MAP3,MAP4,MAP5,MAP6,MAP7;
  wire MAPQ0,MAPQ1,MAPQ2,MAPQ3,MAPQ4,MAPQ5,MAPQ6,MAPQ7;
  wire LDVSL,LDVSH,LDHS,LDHSH;
  wire MB0,MB1,MB2,MB3,MB4,MB5,MB6, TB0,TB1,TB2,TB3,TB4;
  wire MCa0,MCa1,MCa2,MCa3,MCa4,MCa5,MCa6;
  // 10.3.2's descriptor format: LD5/LD6 are gone (b6, b5 reserved), and
  // LPH/LWAIT/LWHSL/LWHSH are the opcode phase, the line wait and the two
  // MOVE strobes. graphics.md 19 item 32.
  // 10.3's engine, all of it on vsup - graphics.md 10.3.3.
  wire LD0,LD1,LD2,LD3,LD4,LD7, LSTOP, LADV, LFETCH, LMOVE, LGO;
  wire LPH, LWAIT, LWHSL, LWHSH, LBYTE, LWPI, LWPDL, LWPDH;
  wire LDBOE, RFOE, PLOAD, PDHW, PINC, PILD, PS0,PS1,PS2,PS3;
  wire LDPDL, LDPDH, PDOE, PIXOE, PWE;
  wire WSPL, WPIDX, WPDL, WPDH;
  // ⚠ vsup DECODES +$03 FOR ITSELF, and vaddr decodes it too - for vctrl's
  // copy of HSCROLL[1:0]. Two decodes of one address are cheaper than the pin
  // that would carry one of them, and this wire is the one they agree on.
  wire VS_LDHS;
  wire SL0,SL1,SL2,SL3,SL4,SL5,SL6,SL7;
  wire LDA,LDB,LDC,LDTB,LDFB,LDMB;
  wire RP0, RP1, RLDA, RLDB;
  wire [7:0] PB;

  vctrl u_vctrl (
    .DOTCLK(DOTCLK), .RESET(RESET),
    .VSTATWR(VSTATWR), .LDHS(LDHS), .LDADV(LDADV), .TC(TC), .LRUN(LRUN),
    .IOPAGE(IOPAGE),
    .A0(PA[0]), .A1(PA[1]), .SPNA0(WA0), .SPNA1(WA1), .E(E), .WCTRL(WCTRL),
    .D0(DIN[0]),.D1(DIN[1]),.D2(DIN[2]),.D3(DIN[3]),
    .D4(DIN[4]),.D5(DIN[5]),.D6(DIN[6]),.D7(DIN[7]),
    .MAPA0(MAPA0), .MAPA1(MAPA1), .RW(RW),
    .A19(PA[19]), .A20(PA[20]),
    .HS0(HS0), .HS1(HS1), .WADV0(WADV0), .WADV1(WADV1),
    .MASKBIT(MASKBIT), .WSTBV(WSTBV), .WPQ(WPQ), .WSTART(WSTART), .SPNREQ(SPNREQ), .SPNTICK(SPNTICK),
    .LGRANT(LGRANT), .CELLTICK(CELLTICK),
    .SR0(SR0),.SR1(SR1),.SR2(SR2),.SR3(SR3),
    .SR4(SR4),.SR5(SR5),.SR6(SR6),.SR7(SR7),
    .H0(H0),.H1(H1),.H2(H2),.H3(H3),.H4(H4),.H5(H5),.H6(H6),.H7(H7),
    .HSYNC(HSYNC), .HBLANK(HBLANK_w),
    .V0(V0),.V1(V1),.V2(V2),.V3(V3),.V4(V4),.V5(V5),.V6(V6),.V7(V7),.V8(V8),.V9(V9),
    .VTC(VTC), .VSYNC(VSYNC), .VBLANK(VBLANK_w), .BLANK(BLANK),
    .VSDLY(VSDLY), .VBLPEND(VBLPEND), .IRQ(IRQ), .IRQ_OE(IRQ_OE),
    .PH0(PH0), .PH1(PH1), .SLOTTICK(SLOTTICK), .SPAREWIN(SPAREWIN_w),
    .FCLK0(FCLK0),.FCLK1(FCLK1),.FCLK2(FCLK2),.FCLK3(FCLK3),
    .MUXSEL0(MUXSEL0), .MUXSEL1(MUXSEL1),
    .SPANBUSY(SPANBUSY), .RETIRE(RETIRE),
    .MC0(MCm0),.MC1(MCm1),.MC2(MCm2), .SPANEND(SPANEND), .WEN(WEN),
    .WROWADV(WROWADV_w),
    .GCPU0(GCPU0),.GCPU1(GCPU1),.GCPU2(GCPU2),.GCPU3(GCPU3),
    .GSPN0(GSPN0),.GSPN1(GSPN1),.GSPN2(GSPN2),.GSPN3(GSPN3),
    .SPNGRANT(SPNGRANT), .WAIT(WAIT), .WAIT_OE(WAIT_OE),
    .ACPU0(ACPU0),.ACPU1(ACPU1),.ACPU2(ACPU2),.ACPU3(ACPU3),
    .VMODE0(VMODE0),.VMODE1(VMODE1),.WM0(WM0),.WM1(WM1),
    .CELL(CELL),.IRQEN(IRQEN),.DISPEN(DISPEN),
    .M0(M0),.HPOL(HPOL),.TILEMODE(TILEMODE),
    .TFETCH(TFETCH),.MFETCH(MFETCH),.FETCH(FETCH),.HLOAD(HLOAD),.HEND(HEND),
    .ROWADV(ROWADV),.MAPREQ(MAPREQ),.MCADV(MCADV),.MAPLD(MAPLD),
    .MAPSEL(MAPSEL),.TILESEL(TILESEL),.LINEAR(LINEAR),
    .SRC0(SRC0),.SRC1(SRC1),
    .SPNREQG(SPNREQG),
    .GMAP0(GMAP0),.GMAP1(GMAP1),.GMAP2(GMAP2),.GMAP3(GMAP3),
    .MAPHOLD(MAPHOLD),.WAITSRC(WAITSRC),.WAITRW(WAITRW),.VRAMSEL(VRAMSEL)
  );

  vaddr u_vaddr (
    .DOTCLK(DOTCLK), .RESET(RESET),
    .FETCH(FETCH), .HLOAD(HLOAD), .ROWADV(ROWADV), .VBLANK(VBLANK_w),
    .MAPLD(MAPLD),
    .MCADV(MCADV), .SRC0(SRC0), .SRC1(SRC1), .CELLTICK(CELLTICK),
    .RP0(RP0), .RP1(RP1), .RLDA(RLDA), .RLDB(RLDB),
    .RETIRE(RETIRE), .WROWADV(WROWADV_w), .WSTB(WSTB_REG),
    .RA0(RA[0]),.RA1(RA[1]),.RA2(RA[2]),.RA3(RA[3]),.RA4(RA[4]),
    .D0(DBUS[0]),.D1(DBUS[1]),.D2(DBUS[2]),.D3(DBUS[3]),
    .D4(DBUS[4]),.D5(DBUS[5]),.D6(DBUS[6]),.D7(DBUS[7]),
    .PB0(PB[0]),.PB1(PB[1]),.PB2(PB[2]),.PB3(PB[3]),
    .PB4(PB[4]),.PB5(PB[5]),.PB6(PB[6]),.PB7(PB[7]),
    .HS2(HS2),.HS3(HS3),.HS4(HS4),.HS5(HS5),.HS6(HS6),.HS7(HS7),.HS8(HS8),.HS9(HS9),
    .VS0(VS0),.VS1(VS1),.VS2(VS2),.VS3(VS3),.VS4(VS4),
    .VS5(VS5),.VS6(VS6),.VS7(VS7),.VS8(VS8),
    .TB0(TB0),.TB1(TB1),.TB2(TB2),.TB3(TB3),.TB4(TB4),
    .MB0(MB0),.MB1(MB1),.MB2(MB2),.MB3(MB3),.MB4(MB4),.MB5(MB5),.MB6(MB6),
    .MAP0(MAP0),.MAP1(MAP1),.MAP2(MAP2),.MAP3(MAP3),
    .MAP4(MAP4),.MAP5(MAP5),.MAP6(MAP6),.MAP7(MAP7),
    .MAPQ0(MAPQ0),.MAPQ1(MAPQ1),.MAPQ2(MAPQ2),.MAPQ3(MAPQ3),
    .MAPQ4(MAPQ4),.MAPQ5(MAPQ5),.MAPQ6(MAPQ6),.MAPQ7(MAPQ7),
    // 10.3's engine: three signals in, no state - its descriptor half is on
    // vsup now (vsup.parts.ts), because this part's LAB fan-in is full.
    .WINC(WINC), .LADV(LADV), .LWHSL(LWHSL), .LWHSH(LWHSH), .LDADV(LDADV),
    .MC0(MCa0),.MC1(MCa1),.MC2(MCa2),.MC3(MCa3),.MC4(MCa4),.MC5(MCa5),.MC6(MCa6),
    .MAPA0(MAPA0),.MAPA1(MAPA1),
    .SA2(SA2),.SA3(SA3),.SA4(SA4),.SA5(SA5),.SA6(SA6),.SA7(SA7),
    .SA8(SA8),.SA9(SA9),
    .SA10(SA10),.SA11(SA11),.SA12(SA12),.SA13(SA13),.SA14(SA14),
    .SA15(SA15),.SA16(SA16),.SA17(SA17),.SA18(SA18),
    .WA0(WA0),.WA1(WA1),.WA2(WA2),.WA3(WA3),.WA4(WA4),
    .WA5(WA5),.WA6(WA6),.WA7(WA7),.WA8(WA8),.WA9(WA9),
    .WA10(WA10),.WA11(WA11),.WA12(WA12),.WA13(WA13),.WA14(WA14),
    .WA15(WA15),.WA16(WA16),.WA17(WA17),.WA18(WA18),
    .LDVSL(LDVSL),.LDVSH(LDVSH),.LDHS(LDHS),.LDHSH(LDHSH),
    .LDA(LDA),.LDB(LDB),.LDC(LDC),.LDTB(LDTB),.LDFB(LDFB),.LDMB(LDMB),
    .FBA2(FBA2),.FBA3(FBA3),.FBA4(FBA4),.FBA5(FBA5),.FBA6(FBA6),
    .FBA7(FBA7),.FBA8(FBA8),.FBA9(FBA9),.FBA10(FBA10),.FBA11(FBA11),
    .FBA12(FBA12),.FBA13(FBA13),.FBA14(FBA14),.FBA15(FBA15),
    .FBA16(FBA16),.FBA17(FBA17),.FBA18(FBA18)
  );

  // ---- vsup: the third ATF1508AS -----------------------------------------
  // graphics.md 10.1.7. Three GAL22V10s went in - rfa (the register-file
  // address, 10.1.6.3), vlen (7.4's span-solid length counter) and pxsel
  // (8.2's fetch-rank select) - and two blocks that had nowhere to live came
  // with them: 9's palette write path and 10.3.3's list register port.
  //
  // ⭐ SPANLEN IS INSIDE IT NOW. vlen was a package because 7.4 loaded it from
  // the register file's read bus and that was eight pins neither CPLD had; the
  // eight bits are macrocells here, so the load reads a register that is never
  // anything else and the file's +$05 is a read-back shadow.
  wire OEA0, OEA1, OEA2, OEB0, OEB1, OEB2, PX_HS0, PX_HS1;
  wire NSL0,NSL1,NSL2,NSL3,NSL4,NSL5,NSL6,NSL7,LDLEN;
  vsup u_vsup (
    .DOTCLK(DOTCLK), .RESET(RESET),
    .IOSEL(IOSEL), .A5(PA[5]), .A6(PA[6]),
    .A0(PA[0]),.A1(PA[1]),.A2(PA[2]),.A3(PA[3]),.A4(PA[4]),
    .RW(RW), .E(E), .SPANBUSY(SPANBUSY), .MASKBIT(MASKBIT),
    .RP0(RP0), .RP1(RP1), .WSTBV(WSTBV), .RETIRE(RETIRE),
    .D0(DBUS[0]),.D1(DBUS[1]),.D2(DBUS[2]),.D3(DBUS[3]),
    .D4(DBUS[4]),.D5(DBUS[5]),.D6(DBUS[6]),.D7(DBUS[7]),
    .LGRANT(LGRANT), .HLOAD(HLOAD),
    // rfa's half
    .WSTB(WSTB_REG), .WCTRL(WCTRL), .VSTATWR(VSTATWR),
    .RA0(RA[0]),.RA1(RA[1]),.RA2(RA[2]),.RA3(RA[3]),.RA4(RA[4]),
    // vlen's half - SPANLEN is SL7..SL0 on this die
    .LDLEN(LDLEN), .TC(TC),
    .NSL0(NSL0),.NSL1(NSL1),.NSL2(NSL2),.NSL3(NSL3),
    .NSL4(NSL4),.NSL5(NSL5),.NSL6(NSL6),.NSL7(NSL7),
    .SL0(SL0),.SL1(SL1),.SL2(SL2),.SL3(SL3),
    .SL4(SL4),.SL5(SL5),.SL6(SL6),.SL7(SL7), .WSPL(WSPL),
    // pxsel's half. ⚠ vsup DECODES +$03 FOR ITSELF - vaddr decodes the same
    // offset for vctrl's copy of HSCROLL[1:0], and two decodes of one address
    // are cheaper than the pin that would carry one of them. They are separate
    // nets on the board and the testbench asserts they never disagree.
    .LDHS(VS_LDHS), .HS0(PX_HS0), .HS1(PX_HS1),
    .OEA0(OEA0), .OEA1(OEA1), .OEA2(OEA2),
    .OEB0(OEB0), .OEB1(OEB1), .OEB2(OEB2),
    // 10.3's descriptor decode, whole - and 10.3.1's deferred GO
    .BCTRLGO(BCTRLGO), .LGO(LGO), .LRUN(LRUN), .LSTOP(LSTOP),
    .LADV(LADV), .LFETCH(LFETCH), .LMOVE(LMOVE), .LPH(LPH), .LWAIT(LWAIT),
    .LD0(LD0),.LD1(LD1),.LD2(LD2),.LD3(LD3),.LD4(LD4),.LD7(LD7),
    .LBYTE(LBYTE), .LDBOE(LDBOE), .RFOE(RFOE),
    .LWHSL(LWHSL), .LWHSH(LWHSH),
    .LWPI(LWPI), .LWPDL(LWPDL), .LWPDH(LWPDH),
    // 9's palette write path
    .WPIDX(WPIDX), .WPDL(WPDL), .WPDH(WPDH), .PLOAD(PLOAD), .PDHW(PDHW),
    .PINC(PINC), .PILD(PILD), .PS0(PS0),.PS1(PS1),.PS2(PS2),.PS3(PS3),
    .LDPDL(LDPDL), .LDPDH(LDPDH),
    .PDOE(PDOE), .PIXOE(PIXOE), .PWE(PWE)
  );

  // ⭐ THE CARD'S INTERNAL DATA BUS, which 3.2's '245 bridges to D0-D7. On a
  // CPU write the '245 drives it inward and every register on the card sees
  // the CPU's byte; the rest of the time the register file drives it, which is
  // what 7.2's column reload reads. One bus, two directions, and the reload
  // needs no path of its own - design-review2.md V-6.
  //
  // ⭐ AND A THIRD MASTER SINCE 2026-09-09 - graphics.md 10.3.3. One '244 puts
  // the display list's fetched byte on this bus for the dot a granted engine
  // slot lasts, so a descriptor MOVE reaches every register the CPU can write
  // through the load path the CPU already uses. vsup drives both halves of the
  // turnaround: LDBOE enables the buffer, RFOE stands the register file off.
  //
  // ⚠ THE CPU'S WRITE WINS. LBYTE carries !WSTB, so a register write landing
  // in the same dot as a list fetch takes the bus and the descriptor byte is
  // lost - 10.3.1's rule forbids the case, and this is what makes the rule
  // enforceable rather than merely stated.
  wire [7:0] DBUS = WSTB_REG ? DIN : (LDBOE ? PB : RD);

  // The two turnaround pins must be complements: both asserted is a fight
  // between the '244 and the register file, neither is a floating bus.
  assign DBUS_FIGHT = ~(LDBOE ^ RFOE);

  // ---- the register file: 32 bytes of the 32K x 8 SRAM 14 lists -----------
  // Written by the CPU at WSTB, addressed by rfa's RA, read out continuously.
  // 7.4's colour path is the address: RA0 is the mask bit, so RD IS WFG or WBG
  // without a mux, a multiplexer term or a macrocell.
  reg [7:0] regfile [0:31];
  wire [7:0] RD = regfile[RA];
  always @(posedge DOTCLK) if (WSTB_REG) regfile[RA] <= DIN;



  assign H  = {H7,H6,H5,H4,H3,H2,H1,H0};
  assign V  = {V9,V8,V7,V6,V5,V4,V3,V2,V1,V0};
  assign PH = {PH1,PH0};
  assign FBA = {FBA18,FBA17,FBA16,FBA15,FBA14,FBA13,FBA12,FBA11,FBA10,
                FBA9,FBA8,FBA7,FBA6,FBA5,FBA4,FBA3,FBA2};
  assign WPTR = {WA18,WA17,WA16,WA15,WA14,WA13,WA12,WA11,WA10,
                 WA9,WA8,WA7,WA6,WA5,WA4,WA3,WA2,WA1,WA0};
  assign VMODE = {VMODE1, VMODE0};
  assign RD_o = RD;
  assign HSCR = {HS9,HS8,HS7,HS6,HS5,HS4,HS3,HS2};
  assign LPH_o = LPH;
  assign LWAIT_o = LWAIT;
  assign VBLANK = VBLANK_w;
  assign HBLANK = HBLANK_w;
  assign SPAREWIN = SPAREWIN_w;
  assign PWE_o = PWE;
  assign PDOE_o = PDOE;
  assign PIXOE_o = PIXOE;

  // ---- the framebuffer: four chips in 4-way interleave --------------------
  // 2.1's interleave. A1:A0 is the chip and A18:A2 the intra-chip address, so
  // byte b lives at chip b[1:0], address b[18:2] (14.2.2).
  reg [7:0] mem0 [0:131071];
  reg [7:0] mem1 [0:131071];
  reg [7:0] mem2 [0:131071];
  reg [7:0] mem3 [0:131071];

  wire [16:0] a = FBA;
  wire [7:0] rd0 = mem0[a], rd1 = mem1[a], rd2 = mem2[a], rd3 = mem3[a];

  // The display fetch reads all four chips. FBA carries the DISPLAY address
  // only in the back half of the slot (LINEAR/TILESEL carry PH1 - 5.2.2), so
  // this samples it there; the '574s are clocked at the slot boundary, after
  // the phase-3 pixel has been emitted from their old contents.
  reg [7:0] f0, f1, f2, f3;
  always @(posedge DOTCLK) if (PH == 2'd3) begin
    f0 <= rd0; f1 <= rd1; f2 <= rd2; f3 <= rd3;
  end

  // ⭐ TWO RANKS OF '574 IN SERIES SINCE 2026-09-09 - graphics.md 8.2, and it
  // is 19 item 28's answer. Rank A is clocked per chip at the end of that
  // chip's fetch (5.2.2); rank B is clocked on the same edge and therefore
  // holds what A held before it, which is the PREVIOUS fetch group.
  //
  // With TFETCH opening one slot early (video.parts.ts) the address bus runs
  // one group ahead of the picture, so during display slot s:
  //
  //     rank A = group s+1        rank B = group s
  //
  // and chip c presents A when c < HSCROLL[1:0] and B otherwise. That is two
  // live groups out of one four-byte fetch, which is what byte-granular
  // horizontal scroll needs and what one rank provably could not give.
  reg [7:0] a0, a1, a2, a3;             // rank A - this slot's fetch
  reg [7:0] b0, b1, b2, b3;             // rank B - the previous one
  always @(posedge FCLK0) begin b0 <= a0; a0 <= f0; end
  always @(posedge FCLK1) begin b1 <= a1; a1 <= f1; end
  always @(posedge FCLK2) begin b2 <= a2; a2 <= f2; end
  always @(posedge FCLK3) begin b3 <= a3; a3 <= f3; end

  // ⚠ THE SELECT IS AN OUTPUT ENABLE AND NOT A MUX, which is what makes this
  // four packages instead of twelve: `c < p` is constant for a whole line, so
  // one rank per chip drives that chip's '153 input and the other tri-states.
  // pxsel drives the pairs and asserts that they are never equal.
  wire [3:0] oea = {1'b0, OEA2, OEA1, OEA0};
  wire [3:0] oeb = {1'b1, OEB2, OEB1, OEB0};
  wire [7:0] l0 = oea[0] ? a0 : b0;
  wire [7:0] l1 = oea[1] ? a1 : b1;
  wire [7:0] l2 = oea[2] ? a2 : b2;
  wire [7:0] l3 = oea[3] ? a3 : b3;

  // The four '153: a 4:1 mux on MUXSEL, which is the dot phase plus HSCROLL[1:0].
  wire [1:0] sel = {MUXSEL1, MUXSEL0};
  assign PIXEL = DISPEN ? (sel == 2'd0 ? l0 : sel == 2'd1 ? l1 :
                           sel == 2'd2 ? l2 : l3) : 8'h00;

  // The board has no wire on which both ranks drive: a '574 output enable is
  // hard, not open-drain, so a moment with both asserted is a fight and a
  // moment with neither is a floating pixel bus. pxsel makes them complements
  // by construction; this is the board-level restatement of that claim.
  wire rank_fight = |(oea & oeb) | |(~oea & ~oeb);

  // The spare access's data - what the map latch and the list engine read.
  // 6.4.1 calls this "the pixel bus"; 14's parts list has no path from the
  // SRAM data pins to it (design-review2.md V-6).
  wire [1:0] spare_chip = MAPSEL ? {MAPA1, MAPA0} : {WA1, WA0};
  assign PB = spare_chip == 2'd0 ? rd0 : spare_chip == 2'd1 ? rd1 :
              spare_chip == 2'd2 ? rd2 : rd3;

  // ⭐ The span writer's byte, and it is one wire. 7.4: direct mode retires
  // 3.1.1's posted data latch; every span mode retires whatever the register
  // file is presenting, and rfa has already put WFG or WBG there according to
  // the mask bit. There is no colour mux on this card and there never was
  // meant to be - that is the whole of "choosing the source colour costs no
  // macrocell and no product term".
  reg [7:0] wdata_latch;              // 3.1.1's posted-write data '574
  always @(posedge DOTCLK) if (WSTBV) wdata_latch <= DIN;
  wire direct = (WM1 == 1'b0) && (WM0 == 1'b0);
  wire [7:0] span_byte = direct ? wdata_latch : RD;

  always @(posedge DOTCLK) if (WEN) begin
    case ({WA1, WA0})
      2'd0: mem0[WPTR[18:2]] <= span_byte;
      2'd1: mem1[WPTR[18:2]] <= span_byte;
      2'd2: mem2[WPTR[18:2]] <= span_byte;
      2'd3: mem3[WPTR[18:2]] <= span_byte;
    endcase
  end

  // ---- 9's palette: the LUT, its two masters, and the write path ---------
  //
  // ⛔ NONE OF THIS EXISTED UNTIL 2026-09-09. 14's parts list carried the LUT
  // SRAM, the pixel-index '574 and a '593 index counter; census.ts booked
  // "PIDX '593 load and count" as a line item with no cell behind it, so
  // nothing on the card could load the index, drive the LUT's address during a
  // write, or assert its /WE. The CPU could not write the palette, and on a
  // card whose only colour path is the LUT that is the whole picture.
  //
  // 6.1's chain, one dot deep at each stage:
  //     '153 mux -> pixel-index '574 -> 15 ns LUT -> post-LUT '273 -> ladders
  //
  // 13.1's turnaround is the second master. During a palette commit vsup
  // three-states the index '574 AND the LUT's own data drivers with one pin
  // (PIXOE), drives the address from PIDX and the data from the two '573s.

  // The pixel-index 74AHCT574 - 14's "palette index latch".
  reg [7:0] pixidx;
  always @(posedge DOTCLK) pixidx <= PIXEL;

  // ⭐ 13's PIDX: TWO 74AHCT163A, not the 74HC593 the parts list carried.
  // 19 item 9 closed on 2026-09-09 - the '593 is DISCONTINUED, with no widely
  // available pin-compatible replacement - and the substitute is better than
  // the original rather than merely available. A '593's eight pins are one
  // SHARED bidirectional port, so the CPU's index byte has to reach the LUT's
  // address bus before it can be latched at all: a second turnaround on a bus
  // 13.1 already calls unarbitrated. A '163 has ordinary parallel inputs, so
  // the counters load from the card's internal data bus like every other
  // register on the card, and touch the LUT's address bus only to drive it.
  reg [7:0] pidx_ctr;
  always @(posedge DOTCLK) begin
    if (PILD)      pidx_ctr <= DBUS;       // synchronous parallel load
    else if (PINC) pidx_ctr <= pidx_ctr + 8'd1;
  end
  assign PIDX = pidx_ctr;

  // 13's PDATL and PDATH: two 74HC573 transparent latches on the internal data
  // bus. A '573 closes on the TRAILING edge of its LE, which is the only edge
  // at which a 6809E write's data is guaranteed (3.1) - an edge-triggered '574
  // clocked on the strobe's rising edge would sample before the CPU has
  // driven. Modelled on the dot clock, which captures the same final value.
  reg [7:0] pdatl, pdath;
  always @(posedge DOTCLK) begin
    if (LDPDL) pdatl <= DBUS;
    if (LDPDH) pdath <= DBUS;
  end

  // 13.1's LUT address bus and its two masters, which is the table 13.1 has:
  //   PIXOE  the pixel-index '574, every dot
  //   PDOE   the index '244, fed by the '163 pair, through a commit
  // The load path is NOT a third master any more - that is what the '163s buy.
  wire [7:0] lut_a = PIXOE ? pixidx : PIDX;
  reg [15:0] lut [0:255];
  always @(posedge DOTCLK) if (PWE) lut[lut_a] <= {pdath, pdatl};

  // The two post-LUT 74AHCT273. 9.2: /MR is BLANK, and it is asynchronous, so
  // the porches are 0.000 V and the monitor's back-porch clamp has something
  // true to clamp to. Rejected alternatives are in 9.2; this is the reason the
  // part is a '273 and not a '574.
  // PIXOE is the LUT's own /OE as well as the index '574's: the picture owns
  // both of the LUT's buses, or the write does. 13.1's snow is exactly the
  // dots in which it is the write.
  reg [15:0] rgb_r;
  always @(posedge DOTCLK) rgb_r <= PIXOE ? lut[lut_a] : 16'hxxxx;
  assign RGB = BLANK ? 16'h0000 : rgb_r;

  // The board-level restatement of vsup's own claim: the LUT's data pins and
  // the '573 pair are never enabled together, and neither are the index '574
  // and PIDX. One pin does both turnarounds, so this is one comparison.
  // verilator lint_off UNUSEDSIGNAL
  // No two of the LUT address bus's three masters are ever enabled together,
  // and the LUT's own data drivers stand off exactly while the '573 pair runs.
  wire pal_fight = PIXOE & PDOE;
  // verilator lint_on UNUSEDSIGNAL

  // a back door for the testbenches to preload VRAM
  // verilator lint_off UNUSEDSIGNAL
  task automatic poke(input int addr, input logic [7:0] v);
    case (addr[1:0])
      2'd0: mem0[addr[18:2]] = v;
      2'd1: mem1[addr[18:2]] = v;
      2'd2: mem2[addr[18:2]] = v;
      2'd3: mem3[addr[18:2]] = v;
    endcase
  endtask
  function automatic logic [15:0] peek_pal(input int idx);
    peek_pal = lut[idx[7:0]];
  endfunction
  function automatic logic [7:0] peek(input int addr);
    case (addr[1:0])
      2'd0: peek = mem0[addr[18:2]];
      2'd1: peek = mem1[addr[18:2]];
      2'd2: peek = mem2[addr[18:2]];
      default: peek = mem3[addr[18:2]];
    endcase
  endfunction
  // verilator lint_on UNUSEDSIGNAL

endmodule
`default_nettype wire
