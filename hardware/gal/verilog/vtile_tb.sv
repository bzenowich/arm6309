// graphics.md 6.4: the tile fetch. The address is a concatenation (6.4.1), the
// cadence is nine accesses per eight dots with the map byte one cell ahead
// (6.4.9), and both axes scroll from the same two registers as bitmap mode
// (6.4.6 limit 2).
//
// check:tile asserts the arithmetic and check:cadence walks a line in
// TypeScript. This runs it: the map byte comes out of memory through the
// latch, and the tile address is read off the same mux the bitmap uses.
//
// A comment line here must never begin with the simulator's own name.

module vtile_tb;

  logic DOTCLK = 0;
  always #1 DOTCLK <= ~DOTCLK;

  logic RESET = 1, E = 0, RW = 1, IOSEL = 0, IOPAGE = 1;
  logic [20:0] PA = 0;
  logic [7:0]  DIN = 0;

  wire WAIT_OE, IRQ_OE, BLANK, HSYNC, VSYNC;
  wire [7:0] PIXEL;
  wire [7:0] H;  wire [9:0] V;  wire [1:0] PH;
  wire [18:2] FBA;
  wire LINEAR, TILESEL, MAPSEL, SPNGRANT, SPANBUSY, LRUN;
  wire RETIRE, WEN, SPANEND, MAPLD, MAPREQ, SLOTTICK, SPAREWIN;
  wire [18:0] WPTR;  wire [1:0] VMODE;  wire VBLANK, HBLANK;
  wire [7:0] RD_o;

  wire [9:2] HSCR; wire LPH_o, LWAIT_o;   // 10.3.2's descriptor engine

  // 9's palette, and 10.3.3's turnaround on the card's internal data bus.
  wire [15:0] RGB; wire [7:0] PIDX;
  wire PWE_o, PDOE_o, PIXOE_o, DBUS_FIGHT;

  video_card card (.*);

  int fails = 0;
  task automatic ok(input bit good, input string claim);
    if (good) $display("ok    %s", claim);
    else begin fails++; $display("FAIL  %s", claim); end
  endtask

  task automatic wr(input int off, input logic [7:0] v);
    @(negedge DOTCLK);
    PA = 0; PA[6:0] = 7'h60 + off[4:0];
    IOSEL = 1; IOPAGE = 1; RW = 0; E = 1; DIN = v;
    repeat (4) @(negedge DOTCLK);
    E = 0; RW = 1; IOSEL = 0; DIN = 0; PA = 0;
    @(negedge DOTCLK);
  endtask

  task automatic to_line(input int line, input int slot);
    forever begin
      @(posedge DOTCLK); #0;
      if (V == line && H == slot && PH == 2'd0) return;
    end
  endtask

  localparam int TILEB = 5'h01;    // tiles at 0x04000, 16 KB aligned
  localparam int MAPB  = 7'h02;    // map   at 0x02000,  4 KB aligned

  // ---- what the line should look like -------------------------------------
  function automatic int map_addr(input int cell_row, input int cell_col);
    return (MAPB << 12) | ((cell_row & 31) << 7) | (cell_col & 127);
  endfunction
  function automatic int tile_addr(input int code, input int row_in_cell,
                                   input int half);
    return (TILEB << 14) | (code << 6) | (row_in_cell << 3) | (half << 2);
  endfunction

  int map_slots, map_lds, i, n;
  int seen_map[$], seen_tile[$], seen_code[$];
  int cell_row, row_in_cell, want, bad, disp_row, off_by_one, lead_bad;
  logic [7:0] mapbyte;

  task automatic walk_line(input int line, input int vscroll, input int hscroll);
    seen_map.delete(); seen_tile.delete(); seen_code.delete();
    map_slots = 0; map_lds = 0;
    to_line(line, 0);
    for (int s = 0; s < 200; s++) begin
      for (int d = 0; d < 4; d++) begin
        @(posedge DOTCLK); #0;
        if (MAPSEL && d == 0) begin
          map_slots++;
          seen_map.push_back({FBA, card.MAPA1, card.MAPA0});
        end
        if (MAPLD) map_lds++;
        if (TILESEL && d == 2 && s >= 34 && s <= 193) begin
          seen_tile.push_back(FBA);
          // ⭐ MAPQ, not MAP. Since 2026-09-09 the map byte is a two-stage
          // pipeline: MAP is the fetch target and MAPQ is what the address mux
          // reads, handed over at the cell boundary. One register could not do
          // it - design-review2.md V-5 and video.parts.ts.
          seen_code.push_back({card.MAPQ7,card.MAPQ6,card.MAPQ5,card.MAPQ4,
                               card.MAPQ3,card.MAPQ2,card.MAPQ1,card.MAPQ0});
        end
      end
    end
  endtask

  initial begin
    // A map whose byte at (row, col) is a recognisable function of the cell.
    for (int r = 0; r < 32; r++)
      for (int c = 0; c < 128; c++)
        card.poke((MAPB << 12) | (r << 7) | c, (r * 5 + c * 3) & 8'hFF);
    // Tiles: byte b of tile t is t ^ b.
    for (int t = 0; t < 256; t++)
      for (int b = 0; b < 64; b++)
        card.poke((TILEB << 14) | (t << 6) | b, (t ^ b) & 8'hFF);

    repeat (4) @(posedge DOTCLK);
    RESET = 0;
    repeat (8) @(posedge DOTCLK);

    wr('h17, TILEB);           // TILEBASE
    wr('h19, MAPB);            // MAPBASE
    wr('h01, 8'h00); wr('h02, 8'h00);
    wr('h03, 8'h00); wr('h04, 8'h00);
    wr('h00, 8'hA2);           // DISPEN | CELL | VMODE 10 (640x400 progressive)

    $display("");
    $display("The cell fetch cadence - graphics.md 6.4.9");
    $display("");
    walk_line(100, 0, 0);
    ok(map_slots == 80,
       $sformatf("80 map accesses on a line, one per cell (got %0d)", map_slots));
    ok(map_lds == 80,
       $sformatf("MAPLD latches once per map access (got %0d)", map_lds));
    ok(seen_tile.size() == 160,
       $sformatf("160 tile fetch slots in TFETCH - two per cell (got %0d)",
                 seen_tile.size()));

    $display("");
    $display("The map address is MAPBASE | cellRow<<7 | cellCol - 6.4.1");
    $display("");
    disp_row = 100 - 37;               // 640x400: active starts at V = 37
    cell_row = (disp_row / 8) % 32;
    bad = 0;
    for (i = 0; i < seen_map.size(); i++) begin
      // the map fetch leads by one cell, so map access i names cell i
      want = map_addr(cell_row, i);
      if (seen_map[i] != want) begin
        if (bad == 0) $display("      map access %0d: %0h, want %0h", i, seen_map[i], want);
        bad++;
      end
    end
    ok(bad == 0, $sformatf("all 80 map addresses are the concatenation (%0d wrong)", bad));

    $display("");
    $display("The map byte reaches the tile address one cell later - 6.4.9's lead");
    $display("");
    bad = 0; off_by_one = 0; lead_bad = 0;
    for (i = 0; i < 160; i++) begin
      // tile fetch slot i belongs to cell i/2; its code is the map byte for
      // that cell, which the map fetch collected one cell earlier.
      mapbyte = ((cell_row * 5) + ((i / 2) * 3)) & 8'hFF;
      if (seen_code[i] != mapbyte) begin
        if (bad == 0)
          $display("      tile slot %0d (cell %0d): code %0h, want %0h  [cell+1 would be %0h]",
                   i, i/2, seen_code[i], mapbyte,
                   ((cell_row * 5) + ((i / 2 + 1) * 3)) & 8'hFF);
        bad++;
      end
      if (seen_code[i] == (((cell_row * 5) + ((i / 2 + 1) * 3)) & 8'hFF)) off_by_one++;
      // and the fetch rank is one cell ahead of it, which is 6.4.9's lead
      if (i % 2 == 0 && i < 156) begin
        if (({card.MAPQ7,card.MAPQ6,card.MAPQ5,card.MAPQ4,
              card.MAPQ3,card.MAPQ2,card.MAPQ1,card.MAPQ0}) == 8'h00) lead_bad++;
      end
    end
    ok(bad == 0, $sformatf("each cell's tile fetch carries that cell's map byte (%0d wrong of 160)", bad));
    $display("      of the %0d wrong, %0d carry the NEXT cell's code exactly", bad, off_by_one);

    $display("");
    $display("The tile address is TILEBASE | code<<6 | row<<3 | half<<2 - 6.4.1");
    $display("");
    row_in_cell = disp_row % 8;
    bad = 0;
    // Against the code the card ACTUALLY holds, so this isolates the address
    // arithmetic from the one-cell latch defect above.
    for (i = 0; i < 160; i++) begin
      mapbyte = seen_code[i][7:0];
      want = tile_addr(mapbyte, row_in_cell, i % 2) >> 2;
      if (seen_tile[i] != want) begin
        if (bad == 0)
          $display("      tile slot %0d: FBA %0h, want %0h", i, seen_tile[i], want);
        bad++;
      end
    end
    ok(bad == 0, $sformatf("all tile addresses are TILEBASE|code<<6|row<<3|half<<2 for the code held (%0d wrong of 160)", bad));

    $display("");
    $display("Cell mode scrolls in both axes from HSCROLL/VSCROLL - 6.4.6 limit 2");
    $display("");
    // vertical, whole cells: VSCROLL += 8 advances one cell row
    wr('h01, 8'd8);
    walk_line(100, 8, 0);
    cell_row = ((disp_row + 8) / 8) % 32;
    bad = 0;
    for (i = 0; i < seen_map.size(); i++)
      if (seen_map[i] != map_addr(cell_row, i)) bad++;
    ok(bad == 0, "VSCROLL += 8 advances the map by one whole cell row");

    // vertical, sub-cell: VSCROLL += 1 moves the row inside the cell
    wr('h01, 8'd1);
    walk_line(100, 1, 0);
    cell_row = ((disp_row + 1) / 8) % 32;
    row_in_cell = (disp_row + 1) % 8;
    bad = 0;
    for (i = 0; i < 160; i++) begin
      mapbyte = seen_code[i][7:0];
      if (seen_tile[i] != (tile_addr(mapbyte, row_in_cell, i % 2) >> 2)) bad++;
    end
    ok(bad == 0, {"VSCROLL += 1 is pixel-smooth in cell mode - the row inside the ",
                  "cell is SA12..SA10"});

    // horizontal, whole cells
    wr('h01, 8'd0);
    wr('h03, 8'd24);                    // HSCROLL = 24 = cell 3, offset 0
    walk_line(100, 0, 24);
    cell_row = (disp_row / 8) % 32;
    bad = 0;
    for (i = 0; i < seen_map.size(); i++)
      if (seen_map[i] != map_addr(cell_row, 3 + i)) bad++;
    ok(bad == 0, "HSCROLL = 24 starts the map at cell 3 - HSCROLL[9:3] is the cell");

    // horizontal, across the 128-cell ring
    wr('h03, 8'h00); wr('h04, 8'd3);    // HSCROLL = 768 = cell 96
    walk_line(100, 0, 768);
    bad = 0;
    for (i = 0; i < seen_map.size(); i++)
      if (seen_map[i] != map_addr(cell_row, (96 + i) % 128)) bad++;
    ok(bad == 0, "HSCROLL = 768 wraps the 128-cell horizontal ring inside the line");

    $display("");
    $display("The vertical ring is 32 cell rows - 6.4.6's asymmetry");
    $display("");
    wr('h03, 8'h00); wr('h04, 8'h00);
    wr('h01, 8'd248);                   // VSCROLL = 248 = cell row 31
    walk_line(37 + 8, 248, 0);          // display row 8 -> cell row 32 -> wraps to 0
    bad = 0;
    for (i = 0; i < seen_map.size(); i++)
      if (seen_map[i] != map_addr(0, i)) bad++;
    ok(bad == 0, {"cell row 32 is cell row 0 - the map address has no A18, so the ",
                  "vertical ring is 32 rows against the bitmap's 512"});

    $display("");
    if (fails == 0) $display("vtile_tb OK");
    else $display("vtile_tb: %0d FAILURES", fails);
    $finish;
  end
endmodule
