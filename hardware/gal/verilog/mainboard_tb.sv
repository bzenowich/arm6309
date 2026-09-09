// The machine boots, and the memory map is what machine.md 2, 3 and 7.2 say.
//
// The pieces have checks of their own - mmu.check.ts, jedec.check.ts and
// clkdec_tb between them cover every equation on the motherboard exhaustively.
// What none of them can do is run machine.md 7.2's boot sequence, because that
// is twenty bus cycles through four parts and two SRAMs, and the question it
// answers - does this machine reach its first mapped instruction - is a
// question about the sequence and not about any one part.
//
// A comment line here must never begin with the simulator's own name.

module mainboard_tb;

  logic CLK25 = 0;
  always #1 CLK25 <= ~CLK25;

  logic n_reset = 0, fast_e = 0, rw = 1;
  logic [15:0] la = 16'hFFFE;
  logic [7:0]  dout = 0;
  wire  [7:0]  din;
  wire e, q, run, n_iosel, n_iopage_bp, pa_valid, pa_conflict, dramsel, romsel;
  wire [24:0] pa;
  wire [3:0] ras;

  mainboard #(.SIMMS(4)) mb (.*);

  int fails = 0;
  task automatic ok(input bit good, input string claim);
    if (good) $display("ok    %s", claim);
    else begin fails++; $display("FAIL  %s", claim); end
  endtask

  // ---- one 6809 bus cycle -------------------------------------------------
  logic [7:0] got;
  logic [24:0] pa_seen;
  logic pa_ok, pa_fight, iosel_seen, iopage_seen, dram_seen, rom_seen;
  logic [3:0] ras_seen;

  task automatic cycle(input logic [15:0] a, input bit write, input logic [7:0] v);
    // set up while E is low
    @(negedge e);
    la = a; rw = ~write; dout = v;
    @(posedge e);
    #0;
    pa_seen = pa; pa_ok = pa_valid; pa_fight = pa_conflict; iosel_seen = ~n_iosel;
    iopage_seen = ~n_iopage_bp; dram_seen = dramsel; rom_seen = romsel;
    ras_seen = ras;
    got = din;
    // 6809 t_DHW: write data is held past E-fall. Without it the TASK '574's
    // clock edge and the testbench's release of the data bus are the same
    // simulation instant and the latch is a race.
    @(negedge e);
    @(posedge CLK25);
    rw = 1; dout = 0;
  endtask

  int i, n, bad;
  logic [7:0] b;

  initial begin
    // a recognisable ROM: byte n is n's low byte, with the reset vector at
    // $1FFE pointing at $0400 - which in boot mode is ROM $0400.
    for (i = 0; i < 1048576; i++) mb.load_rom(i, i[7:0]);
    mb.load_rom('h1FFE, 8'h04);
    mb.load_rom('h1FFF, 8'h00);

    repeat (8) @(posedge CLK25);
    n_reset = 1;
    repeat (30) @(posedge CLK25);

    $display("");
    $display("Reset - machine.md 7.2: $FFFE must be a vector, not an undriven bus");
    $display("");
    ok(run == 1'b0, "RUN comes out of reset at 0 - the machine is in boot mode");
    cycle(16'hFFFE, 0, 8'h00);
    ok(rom_seen, "$FFFE selects the boot ROM");
    ok(pa_seen[19:0] == 20'h01FFE,
       $sformatf("and it reads ROM $1FFE - the '244 drives A20..A13 to zero (got %05h)",
                 pa_seen[19:0]));
    ok(got == 8'h04, $sformatf("the reset vector's high byte reads back (got %02h)", got));
    cycle(16'hFFFF, 0, 8'h00);
    ok(got == 8'h00, "and its low byte");

    $display("");
    $display("Boot mode - every logical block reads ROM page 0");
    $display("");
    n = 0;
    for (i = 0; i < 8; i++) begin
      cycle(16'h0400 + (i[15:0] << 13), 0, 8'h00);
      if (rom_seen && pa_seen[19:0] == {7'd0, 13'h0400}) n++;
    end
    ok(n == 8, $sformatf("all eight logical blocks fetch from ROM $0400 (got %0d)", n));

    $display("");
    $display("The boot sequence - machine.md 7.2, instruction by instruction");
    $display("");
    cycle(16'hFFB0, 1, 8'h00);              // TASK := 0
    ok(run == 1'b0, "STA $FFB0 sets TASK and does NOT leave boot mode - $FFB0 is even");

    // Sixteen map writes. machine.md 5 item 3: "$FFA0+n is task n>>3, block n&7"
    // and the entry is the low byte. ram.md 4.1 Layout A: "$FFA0-$FFA7 blocks
    // 0-7 low byte, $FFA8-$FFAF blocks 0-7 high byte". Those two readings of
    // the same sixteen addresses are different, and the board implements one
    // of them; both are written here so the sim says which.
    for (i = 0; i < 8; i++)
      cycle(16'hFFA0 + i[15:0], 1, 8'h00);  // low byte: physical A20..A13 = 0
    for (i = 8; i < 16; i++)
      cycle(16'hFFA0 + i[15:0], 1, 8'h00);  // high byte: physical A24..A21 = 0

    cycle(16'hFFB1, 1, 8'h00);              // RUN := 1
    ok(run == 1'b1, "STA $FFB1 leaves boot mode - the map takes over");

    $display("");
    $display("And the map now has to translate - graphics.md 6.3.1");
    $display("");
    cycle(16'h0400, 0, 8'h00);
    ok(pa_ok, "something drives physical A20..A13 on an ordinary cycle");
    ok(pa_seen == 25'h0000400,
       $sformatf("logical $0400 with a zeroed map is physical $0000400 (got %07h)",
                 pa_seen));
    ok(rom_seen == 1'b0 && dram_seen == 1'b0,
       "and nothing on the motherboard answers at physical 0 - machine.md 2 reserves it");

    $display("");
    $display("Writing a block register - hardware/ram.md 4.3's two windows");
    $display("");
    // A map entry is sixteen bits across two SRAMs, and the write INDEX is
    // LA3..LA0 through U5's '157 - so LA3 is machine.md 3's TASK bit. Until
    // 2026-09-09 U9 used the same LA3 to choose the SRAM, and one line cannot
    // do both: $FFA8 put the high byte in TASK 1's entry 8 while TASK 0's
    // translation read entry 0. design-review2.md M-1.
    cycle(16'hFFA0, 1, 8'h00);              // block 0, low  byte = $00
    cycle(16'hFF90, 1, 8'h02);              // block 0, high byte = $2 -> 4 MB
    $display("      after writing $FFA0 = $00 and $FF90 = $02:");
    for (i = 0; i < 16; i++)
      if (mb.map_lo_at(i) != 0 || mb.map_hi_at(i) != 0)
        $display("        entry %2d:  low $%02h   high $%02h",
                 i, mb.map_lo_at(i), mb.map_hi_at(i));
    ok(mb.map_hi_at(0) == 8'h02 && mb.map_lo_at(0) == 8'h00,
       "both bytes of TASK 0's block 0 land in entry 0");
    cycle(16'h0000, 0, 8'h00);
    ok(pa_seen == 25'h0400000,
       $sformatf("logical $0000 -> physical 4 MB (got %07h, want 0400000)", pa_seen));
    ok(dram_seen, "and DRAMSEL asserts - the first SIMM window");

    $display("");
    $display("The other task's map is addressable from this one - the GIME shape");
    $display("");
    // $FFA0+n is task n>>3, block n&7, in BOTH windows. So TASK 0 can write
    // TASK 1's map without switching to it, which is what a Level 2 task
    // switch does and what ram.md 4.1's Layout A would have made impossible.
    cycle(16'hFFA8, 1, 8'h20);              // task 1, block 0, low  = $20
    cycle(16'hFF98, 1, 8'h00);              // task 1, block 0, high = $0
    ok(mb.map_lo_at(8) == 8'h20 && mb.map_hi_at(8) == 8'h00,
       "writing $FFA8/$FF98 from TASK 0 fills entry 8 - TASK 1's block 0");
    cycle(16'h0000, 0, 8'h00);
    ok(pa_seen == 25'h0400000,
       "and TASK 0's own translation is untouched by it");
    cycle(16'hFFB0, 1, 8'h01);              // TASK := 1
    cycle(16'h0000, 0, 8'h00);
    ok(pa_seen == 25'h0040000,
       $sformatf("switching TASK moves to the map just written - 0.25 MB (got %07h)",
                 pa_seen));
    cycle(16'hFFB0, 1, 8'h00);              // TASK := 0

    $display("");
    $display("The decode itself, with the map loaded through the back door");
    $display("");
    cycle(16'hFFB0, 1, 8'h00);              // TASK := 0
    // 4 MB, 8 MB, 12 MB, 16 MB: A24..A21 = 2, 4, 6, 8 with A20..A13 = 0.
    n = 0;
    for (i = 0; i < 4; i++) begin
      mb.set_map(0, 8'h00, 8'h02 + i[7:0] * 8'h02);
      cycle(16'h0000, 0, 8'h00);
      if (dram_seen && ras_seen != 0) n++;
      $display("      SIMM %0d at physical %2d MB: pa %07h  DRAMSEL %0d  RAS %04b",
               i, 4 + 4 * i, pa_seen, dram_seen, ras_seen);
    end
    ok(n == 4, $sformatf("all four SIMM windows decode - 16 MB of DRAM (got %0d)", n));
    ok(ras_seen == 4'b1000 || ras_seen == 4'b0001,
       "and the fourth window picks a different RAS from the first");

    mb.set_map(0, 8'h00, 8'h0A);            // 20 MB
    cycle(16'h0000, 0, 8'h00);
    ok(!dram_seen, "20 MB is past the last window and DRAMSEL stays low");

    $display("");
    $display("The physical map's four inhabited regions - machine.md 2");
    $display("");
    mb.set_map(0, 8'h40, 8'h00);            // 0.5 MB - the video ring
    cycle(16'h0000, 0, 8'h00);
    ok(pa_seen == 25'h0080000, $sformatf("logical $0000 -> 0.5 MB (got %07h)", pa_seen));
    ok(!iopage_seen, "the video ring at 0.5-1.0 MB leaves /IOPAGE released - cards may answer");
    ok(!dram_seen && !rom_seen, "and nothing on the motherboard answers there");

    mb.set_map(0, 8'h80, 8'h00);            // 1.0 MB - the card buffers
    cycle(16'h0000, 0, 8'h00);
    ok(!iopage_seen, "the card-buffer megabyte at A20 = 1 leaves /IOPAGE released");

    mb.set_map(0, 8'h00, 8'h01);            // 2.0 MB - the ROM
    cycle(16'h0000, 0, 8'h00);
    ok(rom_seen, "the boot ROM answers at physical 2.0 MB as ordinary mapped memory");
    ok(iopage_seen, "and /IOPAGE is pulled above 2 MB, so no card answers");
    ok(got == pa_seen[7:0],
       $sformatf("and the byte read is the ROM's (got %02h)", got));

    mb.set_map(0, 8'h40, 8'h01);            // 2.5 MB: physical A19 = 1
    cycle(16'h0000, 0, 8'h00);
    ok(rom_seen && pa_seen == 25'h0280000,
       $sformatf("both flash devices answer - physical A19 picks between them (pa %07h)",
                 pa_seen));

    $display("");
    $display("The I/O page - machine.md 3");
    $display("");
    cycle(16'hFF60, 0, 8'h00);
    ok(iosel_seen, "$FF60 asserts /IOSEL - the video card's window");
    ok(iopage_seen, "and /IOPAGE, so no card's physical decode fires");
    cycle(16'hFF80, 0, 8'h00);
    ok(!iosel_seen, "$FF80 does not - the geographic window is $FF00-$FF7F");
    cycle(16'hFFC0, 0, 8'h00);
    ok(!iosel_seen, "$FFC0 does not either - it is the vector page");
    ok(rom_seen, "and the ROM answers there unconditionally, boot mode or not");
    ok(pa_seen[19:0] == 20'h01FC0,
       $sformatf("at ROM $1FC0 (got %05h) - the '244 drives, not the map", pa_seen[19:0]));

    $display("");
    $display("Exactly one driver on physical A20-A13, always - M-2 and M-3");
    $display("");
    // The map SRAM's DQ0-DQ7 ARE pa(13)..pa(20) (mainboard.circuit.tsx), so
    // three things can drive that net: the SRAM, the '245 during a map write,
    // and the boot '244. U6's enable is the complement of U9's chip enable
    // since 2026-09-09, which is what makes this a theorem rather than a hope.
    cycle(16'hFF60, 0, 8'h00);
    ok(pa_ok,   "an ordinary I/O cycle: the '244 parks them at zero");
    ok(!pa_fight, "and nothing else is driving");
    cycle(16'h0000, 0, 8'h00);
    ok(pa_ok && !pa_fight, "an ordinary memory cycle: the map SRAM alone");
    cycle(16'hFFC0, 0, 8'h00);
    ok(pa_ok && !pa_fight, "the vector page: the '244 alone");

    // The case that used to be a bus fight sixteen times per boot.
    n = 0; bad = 0;
    for (i = 0; i < 16; i++) begin
      cycle(16'hFFA0 + i[15:0], 1, 8'h00);
      if (pa_ok) n++;
      if (pa_fight) bad++;
      cycle(16'hFF90 + i[15:0], 1, 8'h00);
      if (pa_ok) n++;
      if (pa_fight) bad++;
    end
    ok(bad == 0, $sformatf("and all 32 block-register writes have exactly one driver (%0d fights)", bad));
    ok(n == 32, $sformatf("with something driving in every one of them (%0d of 32)", n));

    $display("");
    if (fails == 0) $display("mainboard_tb OK");
    else $display("mainboard_tb: %0d FAILURES", fails);
    $finish;
  end
endmodule
