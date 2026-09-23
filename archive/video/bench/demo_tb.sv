// THE WHOLE MACHINE, PLAYING THE DEMO: a 6809E, the motherboard, the video card
// AND the audio card, running software/demo/ out of the boot ROM, with the
// picture and the converter codes recorded for a video file.
//
//   sh gal/verilog/run-demo.sh [seconds]          (from hardware/)
//
// ⭐ WHAT IS NEW IN IT. machine_tb has never had the audio card in the machine,
// and nothing in this repository had taken an interrupt: boot.asm masks both
// lines and never unmasks them. The demo runs its replayer from the audio
// card's /FIRQ and counts frames from the video card's VBL /IRQ, on two
// crystals that do not share a clock, for tens of seconds - so the async host
// port (audio.md 9.4), both interrupt paths and the two cards sharing one bus
// are all in the loop at once.
//
// WHAT IT RECORDS, all under +out=DIR:
//   frames.bin   every frame at the connector, from RGB/BLANK/HSYNC/VSYNC and
//                nothing else (machine_tb's rule), plus the state the demo says
//                it was showing - its camera and hero records - read out of the
//                SIMM at the frame's first active line
//   card.dac     the eight converter codes on every change, in colour clocks,
//                for audio/tools/dacwav
//   card.trace   every audio-card register write, numbered by tick exactly as
//                audio/refplayer numbers its own - so the whole run's register
//                stream, delivered over the real bus to the real card, is
//                diffed against the reference
//   sync.txt     the simulated time at colour clock 0 and at each frame, so the
//                picture and the sound line up in the file
//
// ⚠ IT MODELS THE LOGIC AND NOT THE TIMING, as every bench here does (CLAUDE.md):
// propagation delay, setup and hold on either card are not in it.
//
// A comment line here must never begin with the simulator's own name.
`timescale 1ps/1ps

module demo_tb;

  // ---- two crystals ----------------------------------------------------------
  // 25.175 MHz and 28.37516 MHz, as half periods in picoseconds. Neither is a
  // multiple of the other, so the audio card's host port sees E at every phase.
  logic CLK25 = 0;
  always #19861 CLK25 = ~CLK25;
  logic SLOTCLK = 0;
  always #17621 SLOTCLK = ~SLOTCLK;
  localparam longint DOT_PS = 39722;
  localparam longint SLOT_PS = 35242;

  logic n_reset = 0, fast_e = 0;
  wire [15:0] RGB;
  wire BLANK, HSYNC, VSYNC;
  wire [7:0] PIXEL, H;
  wire [9:0] V;
  wire e, q, run, rw, lic, avma;
  wire [15:0] la;
  wire [7:0] cpu_dout, cpu_din;
  wire [24:0] pa;
  wire n_iosel, n_iopage_bp, wait_asserted;
  wire [18:0] WPTR;
  wire [1:0] VMODE;
  wire SPANBUSY, VBLANK, HBLANK;
  wire bus_conflict, pa_conflict, vram_read;
  wire [7:0] DACSAMP0, DACSAMP1, DACSAMP2, DACSAMP3;
  wire [7:0] DACVOL0, DACVOL1, DACVOL2, DACVOL3;
  wire [15:0] ACOUNT;
  wire firq_asserted, irq_asserted;

  machine #(.SIMMS(4), .AUDIO(1)) m (.*);

  int fails = 0, claims = 0;
  task automatic ok(input bit good, input string claim);
    claims++;
    if (good) $display("ok    %s", claim);
    else begin fails++; $display("FAIL  %s", claim); end
  endtask

  string outdir = "/tmp/arm6309-demo";
  string rom_path = "../../../software/demo/build/rom.hex";
  int secs = 30;
  initial begin
    void'($value$plusargs("out=%s", outdir));
    void'($value$plusargs("rom=%s", rom_path));
    void'($value$plusargs("secs=%d", secs));
  end

  // ---- the progress port ------------------------------------------------------
  logic [7:0] progress = 8'h00;
  always @(negedge e)
    if (!n_iosel && pa[7:0] == 8'h2F && !rw) begin
      progress <= cpu_dout;
      $display("      %8.3f s  progress $%02h", real'($time) / 1.0e12, cpu_dout);
    end

  // ---- marks.txt: timing marks, for the budget the game keeps in the blank --
  // A write to $FF2E - which, like $FF2F, decodes nowhere on the board - is a
  // mark: demo.asm writes 1 when the flip starts and 2 when it ends. With them
  // go VBLANK's rising edge and each frame's first active dot, so how much of
  // the blank the flip used, and whether it overran, is measured, not guessed.
  int markfd;
  bit vbl_d = 0;
  // With them: /IRQ's rising edge (I), and at each mark the E cycles and the
  // /WAIT dots since the previous one - so a slow flip says whether it was the
  // code or the card that held it.
  int mark_e = 0, mark_wait = 0;
  bit irqm_d = 0;
  always @(negedge e)
    if (!n_iosel && pa[7:0] == 8'h2E && !rw) begin
      $fwrite(markfd, "%0d M%0d %0d %0d\n", $time, cpu_dout, mark_e, mark_wait);
      mark_e = 0; mark_wait = 0;
    end else mark_e++;
  always @(posedge CLK25) begin
    if (VBLANK && !vbl_d) $fwrite(markfd, "%0d V\n", $time);
    if (irq_asserted && !irqm_d) $fwrite(markfd, "%0d I\n", $time);
    if (wait_asserted) mark_wait++;
    vbl_d <= VBLANK;
    irqm_d <= irq_asserted;
  end

  // ---- the things that must never happen ------------------------------------
  bit saw_bus_conflict = 0, saw_pa_conflict = 0;
  always @(posedge CLK25) begin
    if (bus_conflict) saw_bus_conflict = 1;
    if (pa_conflict)  saw_pa_conflict = 1;
  end

  // ---- interrupts, counted at the CPU -------------------------------------
  int irq_edges = 0, firq_edges = 0;
  bit irq_d = 0, firq_d = 0;
  always @(posedge CLK25) begin
    if (irq_asserted && !irq_d) irq_edges++;
    if (firq_asserted && !firq_d) firq_edges++;
    irq_d <= irq_asserted;
    firq_d <= firq_asserted;
  end

  // ---- the audio card's register stream, numbered as refplayer numbers it --
  int trfd, timfd, trace_tick = 0, aud_writes = 0;
  bit music_marked = 0;
  function automatic string rname(input logic [3:0] r);
    case (r)
      0: return "AIDX";    1: return "ADATA";   2: return "ADMACON"; 3: return "AINTENA";
      4: return "AINTREQ"; 5: return "ACTRL";   6: return "SPTR2";   7: return "SPTR1";
      8: return "SPTR0";   9: return "SDATA";  10: return "ASTAT";  11: return "TIMER1";
     12: return "TIMER0";  default: return "R?";
    endcase
  endfunction
  function automatic string hex2(input logic [7:0] v);
    string h;
    h = "0123456789ABCDEF";
    return {h.substr(v[7:4], v[7:4]), h.substr(v[3:0], v[3:0])};
  endfunction
  always @(negedge e)
    if (!n_iosel && pa[7:4] == 4'h4 && !rw) begin
      aud_writes++;
      // mod_start's first write is AIDX; the loader never writes AIDX. So the
      // first one is the instant the module starts, for the audio A/B.
      if (pa[3:0] == 4'h0 && !music_marked) begin
        music_marked = 1;
        $fwrite(syncfd, "music_ps %0d\n", $time);
        $fflush(syncfd);
      end
      if (pa[3:0] == 4'h4 && cpu_dout == 8'h10) trace_tick++;
      if (pa[3:0] < 4'h6 || pa[3:0] > 4'h9) begin
        $fwrite(trfd, "%06d %-7s %s\n", trace_tick, rname(pa[3:0]), hex2(cpu_dout));
        // ... and WHEN, in the card's colour clocks, for tracewav's control
        $fwrite(timfd, "%0d %h %s\n", cc, pa[3:0], hex2(cpu_dout));
      end
    end

  // ---- the converters, on change ----------------------------------------------
  int dacfd;
  longint cc = 0;
  logic [15:0] prev_count = 16'h0;
  bit counting = 0;
  logic [7:0] ls [0:7];
  always @(posedge SLOTCLK) if (counting) begin
    if (ACOUNT !== prev_count) begin
      cc++;
      prev_count = ACOUNT;
    end
    if (DACSAMP0 !== ls[0] || DACSAMP1 !== ls[1] || DACSAMP2 !== ls[2] || DACSAMP3 !== ls[3]
        || DACVOL0 !== ls[4] || DACVOL1 !== ls[5] || DACVOL2 !== ls[6] || DACVOL3 !== ls[7]) begin
      $fwrite(dacfd, "%0d %0d %0d %0d %0d %0d %0d %0d %0d\n", cc,
              DACSAMP0, DACSAMP1, DACSAMP2, DACSAMP3, DACVOL0, DACVOL1, DACVOL2, DACVOL3);
      ls[0] = DACSAMP0; ls[1] = DACSAMP1; ls[2] = DACSAMP2; ls[3] = DACSAMP3;
      ls[4] = DACVOL0;  ls[5] = DACVOL1;  ls[6] = DACVOL2;  ls[7] = DACVOL3;
    end
  end

  // ---- the picture ------------------------------------------------------------
  // Frames are delimited by VSYNC's leading edge and lines by HSYNC's; a pixel
  // is a dot with BLANK deasserted. The sync senses follow VMODE0
  // (graphics.md 6.2.1), as in machine_tb.
  localparam int MAXW = 1024, MAXH = 512;
  logic [15:0] cur [0:MAXH-1][0:MAXW-1];
  logic [15:0] prv [0:MAXH-1][0:MAXW-1];
  int linew [0:MAXH-1];
  int x = 0, lines = 0, frame_n = 0, dup_n = 0, prv_w = 0, prv_h = 0;
  bit prev_hs = 0, prev_vs = 0, first_active_seen = 0;
  logic [15:0] st_dispk = 0, st_herok = 0, st_missed = 0;
  logic [7:0] st_prog = 0;
  logic [1:0] st_vmode = 0;
  // the show's checkpoint and raster phase (software/demo/gui.asm, $C600 and
  // $C602) at the frame's first active dot and at its last, and whether a
  // display list was running at line 1 - tools/checkdemo.py judges a frame
  // against a model picture only when the two readings agree
  logic [15:0] st_ck0 = 0, st_ck1 = 0, st_ph0 = 0, st_ph1 = 0;
  logic [7:0] st_lrun = 0;
  bit rowchg [0:MAXH-1];
  int frfd, syncfd;

  wire hs_on = VMODE[0] ? 1'b1 : 1'b0;
  wire vs_on = VMODE[0] ? 1'b0 : 1'b1;

  function automatic logic [15:0] ram16(input int adr);
    return {m.mb.peek_dram(adr), m.mb.peek_dram(adr + 1)};
  endfunction

  // A record is the whole picture (repeat 0), nothing (1: the last one
  // again), or (2) a bitmap of the rows that changed and those rows - a pointer
  // moving over a still desktop is one or two rows a frame. tools/frames.py.
  task automatic emit_frame();
    int w, h, same, nchg, kind;
    longint t;
    logic [7:0] bm;
    w = 0; h = lines > MAXH ? MAXH : lines;
    for (int i = 0; i < h; i++) if (linew[i] > w) w = linew[i];
    if (w > MAXW) w = MAXW;
    same = (w == prv_w && h == prv_h);
    nchg = 0;
    for (int yy = 0; yy < h; yy++) begin
      rowchg[yy] = 0;
      for (int xx = 0; xx < w; xx++) begin
        logic [15:0] c;
        c = (xx < linew[yy]) ? cur[yy][xx] : 16'h0000;
        if (c !== prv[yy][xx]) begin rowchg[yy] = 1; break; end
      end
      if (rowchg[yy]) nchg++;
    end
    kind = !same ? 0 : (nchg == 0 ? 1 : 2);
    t = $time;
    $fwrite(frfd, "F%c%c%c%c", frame_n[7:0], frame_n[15:8], frame_n[23:16], frame_n[31:24]);
    for (int b = 0; b < 64; b += 8) $fwrite(frfd, "%c", t[b +: 8]);
    $fwrite(frfd, "%c%c%c%c", w[7:0], w[15:8], h[7:0], h[15:8]);
    $fwrite(frfd, "%c%c%c%c%c%c", st_dispk[7:0], st_dispk[15:8], st_herok[7:0], st_herok[15:8],
            st_missed[7:0], st_missed[15:8]);
    $fwrite(frfd, "%c%c%c", st_prog, {6'b0, st_vmode}, kind[7:0]);
    $fwrite(frfd, "%c%c%c%c%c%c%c%c%c", st_ck0[7:0], st_ck0[15:8], st_ck1[7:0], st_ck1[15:8],
            st_ph0[7:0], st_ph0[15:8], st_ph1[7:0], st_ph1[15:8], st_lrun);
    if (kind == 2)
      for (int yy = 0; yy < h; yy += 8) begin
        bm = 0;
        for (int i = 0; i < 8 && yy + i < h; i++) bm[i] = rowchg[yy + i];
        $fwrite(frfd, "%c", bm);
      end
    if (kind != 1) begin
      for (int yy = 0; yy < h; yy++)
        if (kind == 0 || rowchg[yy])
          for (int xx = 0; xx < w; xx++) begin
            logic [15:0] c;
            c = (xx < linew[yy]) ? cur[yy][xx] : 16'h0000;
            prv[yy][xx] = c;
            $fwrite(frfd, "%c%c", c[7:0], c[15:8]);
          end
      prv_w = w; prv_h = h;
    end else dup_n++;
    frame_n++;
  endtask

  always @(posedge CLK25) if (n_reset) begin
    #1;
    if (!BLANK) begin
      if (!first_active_seen) begin
        first_active_seen = 1;
        $fwrite(markfd, "%0d A\n", $time);
      end
      // ⚠ THE STATE IS SAMPLED AT EVERY ACTIVE DOT AND THE LAST ONE KEPT. The
      // flip that puts the hero in the map is timed from the blank and can run
      // into the top of the next frame; the record numbers it writes then belong
      // to that frame's picture only from where it finished. Keeping the last
      // dot's values means a frame is judged against the state it ENDED with,
      // and a flip that changed cells after they were scanned is a mismatch.
      st_dispk = ram16(32'h00C208);
      st_herok = ram16(32'h00C20A);
      st_missed = ram16(32'h00C225);
      st_prog = progress;
      st_vmode = VMODE;
      if (lines == 0 && x == 0) begin
        st_ck0 = ram16(32'h00C600);
        st_ph0 = ram16(32'h00C602);
      end
      if (lines == 1 && x == 0) st_lrun = {7'b0, m.vid_lrun};
      if (x == 639) begin
        st_ck1 = ram16(32'h00C600);
        st_ph1 = ram16(32'h00C602);
      end
      if (lines < MAXH && x < MAXW) cur[lines][x] = RGB;
      x++;
    end
    if ((HSYNC == hs_on) && !prev_hs) begin
      if (x > 0) begin
        if (lines < MAXH) linew[lines] = x;
        lines++;
      end
      x = 0;
    end
    prev_hs = (HSYNC == hs_on);
    if ((VSYNC == vs_on) && !prev_vs) begin
      if (lines > 0) emit_frame();
      lines = 0; x = 0; first_active_seen = 0;
      for (int i = 0; i < MAXH; i++) linew[i] = 0;
    end
    prev_vs = (VSYNC == vs_on);
  end

  // ---- the run --------------------------------------------------------------
  longint t_end;
  initial begin
    trfd = $fopen({outdir, "/card.trace"}, "w");
    timfd = $fopen({outdir, "/card.times"}, "w");
    dacfd = $fopen({outdir, "/card.dac"}, "w");
    frfd = $fopen({outdir, "/frames.bin"}, "wb");
    syncfd = $fopen({outdir, "/sync.txt"}, "w");
    markfd = $fopen({outdir, "/marks.txt"}, "w");
    ok(trfd != 0 && dacfd != 0 && frfd != 0 && syncfd != 0, $sformatf("the outputs open in %s", outdir));
    for (int i = 0; i < 8; i++) ls[i] = 8'hFF;

    m.mb.load_rom_file(rom_path);
    ok(m.mb.rom[20'h2000] === 8'h36 && m.mb.rom[20'h2003] === 8'h39,
       "the demo is in ROM page 1 and carries boot.asm's \"6309\" signature");
    m.cpu.cpucore.NMILatched = 1'b1;      // machine_tb.sv has why

    repeat (240) @(posedge CLK25);
    n_reset = 1;
    // colour clock 0: the first COUNT change after the card leaves reset
    @(posedge SLOTCLK);
    prev_count = ACOUNT;
    while (ACOUNT === prev_count) @(posedge SLOTCLK);
    prev_count = ACOUNT;
    counting = 1;
    $fwrite(syncfd, "cc0_ps %0d\nslot_ps %0d\n", $time, SLOT_PS);
    $fflush(syncfd);

    t_end = longint'(secs) * 64'd1000000000000;
    while ($time < t_end) begin
      #(64'd500000000000);                // half a second of machine
      $display("      %8.3f s  prog $%02h  frames %0d (%0d repeats)  IRQ %0d  FIRQ %0d  ticks %0d  camera %0d  hero %0d  missed %0d",
               real'($time) / 1.0e12, progress, frame_n, dup_n, irq_edges, firq_edges, trace_tick,
               ram16(32'h00C208), ram16(32'h00C20A), ram16(32'h00C225));
      $fflush(trfd); $fflush(timfd); $fflush(dacfd); $fflush(frfd);
      if (progress >= 8'hE0) begin
        $display("FAIL  the ROM reported $%02h", progress);
        fails++;
        break;
      end
    end

    $display("");
    ok(progress == 8'h87, $sformatf("the show ran to its end - the game played, the desktop came back and the audio player stopped the module: progress $87 (got $%02h)", progress));
    ok(firq_edges > 0, $sformatf("⭐ /FIRQ WAS TAKEN: the audio card's tempo timer interrupted the CPU %0d times", firq_edges));
    ok(irq_edges > 0, $sformatf("⭐ /IRQ WAS TAKEN: the video card's VBL interrupted the CPU %0d times", irq_edges));
    ok(!saw_bus_conflict, "no cycle had two drivers on D0-D7 - with two cards on the bus");
    ok(!saw_pa_conflict, "no cycle had two drivers on physical A20-A13");
    $display("      %0d frames (%0d repeats), %0d audio writes, %0d ticks, cc %0d",
             frame_n, dup_n, aud_writes, trace_tick, cc);
    $fclose(trfd); $fclose(timfd); $fclose(dacfd); $fclose(frfd);
    $fwrite(syncfd, "end_ps %0d\ncc_end %0d\n", $time, cc);
    $fclose(syncfd);
    if (fails == 0) $display("demo_tb OK - %0d claims", claims);
    else            $display("demo_tb - %0d of %0d claims FAILED", fails, claims);
    $finish;
  end

endmodule
