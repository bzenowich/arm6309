// The motherboard: U3 (MMU sequencer), U6 (divider, /IOSEL, boot mode), U9
// (physical space decode), U10 (SIMM controller), plus the parts they steer -
// the two map SRAMs, the '157 index mux, the TASK '574, the boot '244, the two
// flash devices and the SIMM bank.
//
// Everything here is either generated from the design files or transcribed from
// hardware/mainboard/mainboard.circuit.tsx, which is the netlist of record.

`default_nettype none

module mainboard #(
    parameter int SIMMS = 4          // how many of the four sockets are populated
) (
    input  wire        CLK25,
    input  wire        n_reset,
    input  wire        fast_e,

    // the CPU, as a 6809E on the motherboard's socket
    input  wire [15:0] la,
    input  wire        rw,
    input  wire [7:0]  dout,          // what the CPU is writing
    output wire [7:0]  din,           // what answers

    output wire        e,
    output wire        q,
    output wire        run,
    output wire        n_iosel,
    output wire        n_iopage_bp,   // the backplane's, U9's
    output wire [24:0] pa,            // the physical address, as a card sees A0-A20
    output wire        pa_valid,      // 0 = A20..A13 are floating (nothing drives them)
    output wire        pa_conflict,   // 1 = more than one driver on that net
    output wire        dramsel,
    output wire [3:0]  ras,
    output wire        romsel
);

  // ---- U6: the divider, /IOSEL and boot mode ------------------------------
  wire [3:0] cnt;
  wire n_bootoe, n_iopage_u3;
  clkdec u6 (.clk25(CLK25), .n_reset(n_reset), .fast_e(fast_e),
             .n_iopage(n_iopage_u3), .la7(la[7]), .la6(la[6]), .la5(la[5]),
             .la4(la[4]), .la0(la[0]), .wait_i(1'b0), .rw(rw),
             .cnt(cnt), .e(e), .q(q), .run(run),
             .n_iosel(n_iosel), .n_bootoe(n_bootoe));

  // ---- U3: the MMU sequencer ----------------------------------------------
  wire muxsel, n_isooe, n_mapwe, n_mapoe, n_ctrlcp, blkhi, blklo;
  mmu u3 (.la(la[15:4]), .e(e), .q(q), .rw(rw), .blkhi(blkhi), .blklo(blklo),
          .n_iopage(n_iopage_u3), .muxsel(muxsel), .n_isooe(n_isooe),
          .n_mapwe(n_mapwe), .n_mapoe(n_mapoe), .n_ctrlcp(n_ctrlcp));

  // ---- the TASK '574 -------------------------------------------------------
  // One live bit of eight (graphics.md 6.3.1), clocked on n_ctrlcp's rising
  // edge - which is E-fall on any $FFB0-$FFBF write.
  reg task_bit;
  always @(posedge n_ctrlcp or negedge n_reset)
    if (!n_reset) task_bit <= 1'b0; else task_bit <= dout[0];

  // ---- the '157 index mux --------------------------------------------------
  // mainboard.circuit.tsx: 1A/1B = LA13/LA0, 2A/2B = LA14/LA1, 3A/3B = LA15/LA2,
  // 4A/4B = TASK/LA3. SEL high selects the B (map-write) side.
  wire [3:0] mapa = muxsel ? la[3:0] : {task_bit, la[15:13]};

  // ---- the two map SRAMs ---------------------------------------------------
  wire mapce_lo, mapce_hi, romce0, romce1, iopage_bp_w, dramsel_w;
  u9 u9i (.A24(pa[24]), .A23(pa[23]), .A22(pa[22]), .A21(pa[21]),
          .A20(pa[20]), .A19(pa[19]),
          .IOPAGE(~n_iopage_u3), .RUN(run),
          .LA7(la[7]), .LA6(la[6]), .LA5(la[5]), .LA4(la[4]),
          .RW(rw),
          .MAPCE_LO(mapce_lo), .MAPCE_HI(mapce_hi),
          .ROMCE0(romce0), .ROMCE1(romce1),
          .IOPAGE_BP(iopage_bp_w), .DRAMSEL(dramsel_w));

  // 2K x 8 each; sixteen locations used.
  reg [7:0] map_lo [0:2047];
  reg [7:0] map_hi [0:2047];
  // The write lands on E-fall of a $FFAx write - n_mapwe is a level over
  // (blksel & !rw & e & !q); take its trailing edge.
  // /WE is a level over E-high, Q-low; model the SRAM as writing while it is
  // asserted, which is what a transparent write is.
  always @(posedge CLK25)
    if (!n_mapwe) begin
      if (mapce_lo) map_lo[{7'd0, mapa}] <= dout;
      if (mapce_hi) map_hi[{7'd0, mapa}] <= dout;
    end

  // ---- the physical address ------------------------------------------------
  // Three drivers, and at most one at a time: the map SRAMs while translating,
  // the '244 during boot and the vector page, and NOTHING during an ordinary
  // I/O cycle - which is what pa_valid reports.
  // ⭐ THREE DRIVERS ON ONE NET, and the model has to say so rather than OR
  // them. Physical A20-A13 is the map SRAM's own common I/O (U1's DQ0-DQ7 are
  // pa(13)..pa(20) in mainboard.circuit.tsx), so the '245 drives it during a
  // map WRITE and the SRAM itself during a translation or a map read - and the
  // boot '244 drives it whenever neither does. Modelling that as "map_drives |
  // buf_drives" is what let design-review2.md's first pass miss M-3: the
  // buffer and the '245 were both on for all sixteen writes of the boot
  // sequence and an OR cannot see a fight.
  wire map_drives  = mapce_lo && !n_mapoe;              // the SRAM's outputs
  wire iso_drives  = !n_isooe && !rw;                   // the '245, toward it
  wire buf_drives  = !n_bootoe;                         // the boot buffer
  wire [7:0] map_lo_q = map_lo[{7'd0, mapa}];
  wire [7:0] map_hi_q = map_hi[{7'd0, mapa}];

  // Exactly one driver, always. pa_valid says something drives; pa_conflict
  // says more than one does, and both are assertions in mainboard_tb.
  assign pa_valid    = map_drives | iso_drives | buf_drives;
  assign pa_conflict = (map_drives & buf_drives) | (iso_drives & buf_drives)
                     | (map_drives & iso_drives);
  assign pa = { buf_drives ? 4'd0 : map_hi_q[3:0],          // A24..A21
                buf_drives ? 8'd0 : map_lo_q,               // A20..A13
                la[12:0] };                                 // untranslated

  assign n_iopage_bp = ~iopage_bp_w;
  assign dramsel = dramsel_w;
  assign romsel = romce0 | romce1;   // asserted-high in the generated Verilog

  // ---- U10: the SIMM controller -------------------------------------------
  // The refresh timebase is the '4040's Q8 - one toggle per 256 CLK25 counts.
  reg [8:0] refdiv;
  always @(posedge CLK25 or negedge n_reset)
    if (!n_reset) refdiv <= 9'd0; else refdiv <= refdiv + 9'd1;
  wire cas, dwe, rf0, rf1, refq;
  u10 u10i (.CLK(CLK25), .DRAMSEL(dramsel_w), .A23(pa[23]), .A22(pa[22]),
            .C0(cnt[0]), .C1(cnt[1]), .C2(cnt[2]), .C3(cnt[3]), .RW(rw),
            .REFCLK(refdiv[8]), .RESET(~n_reset),
            .RF0(rf0), .RF1(rf1), .REFQ(refq),
            .RAS0(ras[0]), .RAS1(ras[1]), .RAS2(ras[2]), .RAS3(ras[3]),
            .CAS(cas), .DWE(dwe));

  // ---- what answers --------------------------------------------------------
  // The boot ROM, 1 MB across two devices. Physical A19 picks the device and
  // A18..A0 the byte, so the byte offset is pa[19:0].
  reg [7:0] rom [0:1048575];
  // The SIMM bank: four 4 MB windows at physical 4-20 MB. A socket that is not
  // populated answers with nothing.
  reg [7:0] dram [0:16777215];
  wire [1:0] simm = pa[23:22] - 2'd1;      // A24..A22 = 001,010,011,100
  wire simm_present = dramsel_w && ({1'b0, pa[24:22]} - 4'd1) < SIMMS;

  assign din = (romce0 || romce1) ? rom[pa[19:0]]
             : simm_present       ? dram[{pa[23:22] - 2'd1, pa[21:0]}]
             : 8'hFF;                       // an undriven bus reads as pull-ups

  // verilator lint_off UNUSEDSIGNAL
  task automatic load_rom(input int addr, input logic [7:0] v);
    rom[addr] = v;
  endtask
  function automatic logic [7:0] map_lo_at(input int i); return map_lo[i]; endfunction
  function automatic logic [7:0] map_hi_at(input int i); return map_hi[i]; endfunction
  task automatic set_map(input int entry, input logic [7:0] lo, input logic [7:0] hi);
    map_lo[entry] = lo; map_hi[entry] = hi;
  endtask
  task automatic poke_dram(input int addr, input logic [7:0] v);
    dram[addr] = v;
  endtask
  function automatic logic [7:0] peek_dram(input int addr); return dram[addr]; endfunction
  // verilator lint_on UNUSEDSIGNAL

endmodule
`default_nettype wire
