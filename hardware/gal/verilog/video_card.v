// The video card, wired: vctrl + vaddr + rfa + vlen, the register file, the
// four interleaved framebuffer chips, the four fetch latches and the '153
// pixel mux.
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
    output wire        VBLANK, HBLANK
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
  wire LD0,LD1,LD2,LD3,LD4,LD5,LD6,LD7, LSTOP, LADV, LFETCH, LMOVE;
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
    .MASKBIT(MASKBIT), .WSTBV(WSTBV), .SPNREQ(SPNREQ), .SPNTICK(SPNTICK),
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
    .MCADV(MCADV), .SRC0(SRC0), .SRC1(SRC1), .LGRANT(LGRANT), .CELLTICK(CELLTICK),
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
    .WINC(WINC), .BCTRLGO(BCTRLGO), .LDADV(LDADV),
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
    .LD0(LD0),.LD1(LD1),.LD2(LD2),.LD3(LD3),
    .LD4(LD4),.LD5(LD5),.LD6(LD6),.LD7(LD7),
    .LRUN(LRUN),.LSTOP(LSTOP),.LADV(LADV),.LFETCH(LFETCH),.LMOVE(LMOVE),
    .FBA2(FBA2),.FBA3(FBA3),.FBA4(FBA4),.FBA5(FBA5),.FBA6(FBA6),
    .FBA7(FBA7),.FBA8(FBA8),.FBA9(FBA9),.FBA10(FBA10),.FBA11(FBA11),
    .FBA12(FBA12),.FBA13(FBA13),.FBA14(FBA14),.FBA15(FBA15),
    .FBA16(FBA16),.FBA17(FBA17),.FBA18(FBA18)
  );

  rfa u_rfa (
    .IOSEL(IOSEL), .A5(PA[5]), .A6(PA[6]),
    .A0(PA[0]),.A1(PA[1]),.A2(PA[2]),.A3(PA[3]),.A4(PA[4]),
    .RW(RW), .E(E), .SPANBUSY(SPANBUSY), .MASKBIT(MASKBIT),
    .RP0(RP0), .RP1(RP1),
    .WSTB(WSTB_REG), .WCTRL(WCTRL), .VSTATWR(VSTATWR),
    .RA0(RA[0]),.RA1(RA[1]),.RA2(RA[2]),.RA3(RA[3]),.RA4(RA[4])
  );

  // ---- vlen: the span-solid length counter ---------------------------------
  // graphics.md 7.4's '161 pair, as one GAL22V10. It loads from the register
  // file's read bus, which is why it is a package and not a block inside one
  // of the CPLDs - vctrl is at 64 of 64 I/O and vaddr at 61 of 64.
  wire NSL0,NSL1,NSL2,NSL3,NSL4,NSL5,NSL6,NSL7,LDLEN;
  vlen u_vlen (
    .CLK(DOTCLK),
    .RD0(RD[0]),.RD1(RD[1]),.RD2(RD[2]),.RD3(RD[3]),
    .RD4(RD[4]),.RD5(RD[5]),.RD6(RD[6]),.RD7(RD[7]),
    .WSTBV(WSTBV), .SPANBUSY(SPANBUSY), .RETIRE(RETIRE),
    .NSL0(NSL0),.NSL1(NSL1),.NSL2(NSL2),.NSL3(NSL3),
    .NSL4(NSL4),.NSL5(NSL5),.NSL6(NSL6),.NSL7(NSL7),
    .LDLEN(LDLEN), .TC(TC)
  );

  // ⭐ THE CARD'S INTERNAL DATA BUS, which 3.2's '245 bridges to D0-D7. On a
  // CPU write the '245 drives it inward and every register on the card sees
  // the CPU's byte; the rest of the time the register file drives it, which is
  // what 7.2's column reload reads. One bus, two directions, and the reload
  // needs no path of its own - design-review2.md V-6.
  wire [7:0] DBUS = WSTB_REG ? DIN : RD;

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
  assign VBLANK = VBLANK_w;
  assign HBLANK = HBLANK_w;
  assign SPAREWIN = SPAREWIN_w;

  // ---- the framebuffer: four chips in 4-way interleave --------------------
  // 2.1's interleave. A1:A0 is the chip and A18:A2 the intra-chip address, so
  // byte b lives at chip b[1:0], address b[18:2] (14.2.2).
  reg [7:0] mem0 [0:131071];
  reg [7:0] mem1 [0:131071];
  reg [7:0] mem2 [0:131071];
  reg [7:0] mem3 [0:131071];

  wire [16:0] a = FBA;
  wire [7:0] rd0 = mem0[a], rd1 = mem1[a], rd2 = mem2[a], rd3 = mem3[a];

  // The display fetch reads all four chips; it is captured at the end of the
  // fetch half, which is the moment 5.2.2 puts the late latch clock at.
  reg [7:0] f0, f1, f2, f3;
  always @(posedge DOTCLK) if (PH == 2'd3) begin
    f0 <= rd0; f1 <= rd1; f2 <= rd2; f3 <= rd3;
  end

  // The four '574 fetch latches, clocked per chip (5.2.2, 19 item 23a).
  reg [7:0] l0, l1, l2, l3;
  always @(posedge FCLK0) l0 <= f0;
  always @(posedge FCLK1) l1 <= f1;
  always @(posedge FCLK2) l2 <= f2;
  always @(posedge FCLK3) l3 <= f3;

  // The four '153: a 4:1 mux on MUXSEL, which is the dot phase plus HSCROLL[1:0].
  wire [1:0] sel = {MUXSEL1, MUXSEL0};
  assign PIXEL = DISPEN ? (sel == 2'd0 ? l0 : sel == 2'd1 ? l1 :
                           sel == 2'd2 ? l2 : l3) : 8'h00;

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
