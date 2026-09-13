// THE REPLAYER, ON THE CPU AND NOTHING ELSE - a quick bench for demo.asm.
//
//   sh software/demo/bench/run-replay.sh [ticks]
//
// ⚠ WHAT THIS IS NOT: THE MACHINE. There is no motherboard, no video card and
// no audio card here - a 64 K logical map through sixteen map entries, a ROM,
// some RAM, and a register-level stand-in for the audio card's host port whose
// only behaviour is audio.md 8.2's tempo timer. hardware/gal/verilog/demo_tb.sv
// is the real run. This one exists because the real run takes a minute of wall
// clock per second of machine, and diffing a 6809 replayer against
// audio/refplayer's trace needs forty seconds of music every time a routine is
// fixed.
//
// ⭐ WHAT IT DOES CHECK, and the machine run cannot do it faster: the core is
// the same mc6809e, the ROM is the same rom.hex, and the trace it writes is in
// refplayer's own format - "%06lu %-7s %02X", tick, register, byte - so
// `diff` names the first tick at which the port and mod_replay.c disagree.
//
// The tick number is the count of /FIRQs asserted so far, which is what
// refplayer's p->ticks counts: mod_start's writes are tick 0, and the first
// timer fire is tick 1.
`timescale 1ns/1ps

module replay_tb;
  logic E = 0, Q = 0, n_reset = 0, n_firq = 1;
  wire [7:0] dout;
  wire [15:0] addr;
  wire rnw, bs, ba, avma, busy, lic;
  logic [7:0] din;

  mc6809e cpu (.D(din), .DOut(dout), .ADDR(addr), .RnW(rnw), .E(E), .Q(Q),
               .BS(bs), .BA(ba), .nIRQ(1'b1), .nFIRQ(n_firq), .nNMI(1'b1),
               .AVMA(avma), .BUSY(busy), .LIC(lic), .nHALT(1'b1), .nRESET(n_reset));

  // ---- memory: ROM pages behind map high byte $01, RAM behind anything else
  logic [7:0] rom [0:1048575];
  logic [7:0] ram [0:1048575];
  logic [7:0] maplo [0:15];
  logic [7:0] maphi [0:15];

  function automatic int phys(input logic [15:0] a);
    int blk;
    blk = a[15:13];
    return {maplo[blk][6:0], a[12:0]};
  endfunction
  function automatic bit isrom(input logic [15:0] a);
    return maphi[a[15:13]] == 8'h01;
  endfunction

  // ---- the audio card's host port, as far as the replayer can see it ------
  int ticks = 0, want_ticks = 2001, trace_tick = 0;
  longint e_count = 0, next_fire = -1;
  logic [15:0] timer = 16'd0;
  bit timer_on = 0;
  int fd;
  string names [0:15];
  initial begin
    names[0]="AIDX"; names[1]="ADATA"; names[2]="ADMACON"; names[3]="AINTENA";
    names[4]="AINTREQ"; names[5]="ACTRL"; names[6]="SPTR2"; names[7]="SPTR1";
    names[8]="SPTR0"; names[9]="SDATA"; names[10]="ASTAT"; names[11]="TIMER1";
    names[12]="TIMER0"; names[13]="R13"; names[14]="R14"; names[15]="R15";
  end

  // One tick is 5 * TIMER colour clocks (audio.md 8.2); E is 25.175 MHz / 12.
  function automatic longint period_e();
    return (5 * longint'(timer) * 64'd2097917) / 64'd3546895;
  endfunction

  int sdata_n = 0, progress = 0, dbg_n = 0;
  function automatic string hex2(input logic [7:0] v);
    string h;
    h = "0123456789ABCDEF";
    return {h.substr(v[7:4], v[7:4]), h.substr(v[3:0], v[3:0])};
  endfunction
  logic [7:0] sram [0:524287];
  logic [18:0] sptr = 0;

  always_comb begin
    din = 8'h00;
    if (addr >= 16'hFFF0)                          din = rom[{4'h0, 3'b000, addr[12:0]}];
    else if (addr[15:8] == 8'hFF)                  din = 8'h00;   // ASTAT never busy, VSTAT idle
    else if (isrom(addr))                          din = rom[phys(addr)];
    else                                           din = ram[phys(addr)];
    // THE RESET VECTOR POINTS AT THE DEMO, not at boot.asm's tests
    if (addr == 16'hFFFE) din = 8'h80;
    if (addr == 16'hFFFF) din = 8'h04;
  end

  always @(negedge E) begin
    e_count++;
    if (!rnw) begin
      if (addr[15:4] == 12'hFF9)       maphi[addr[3:0]] = dout;
      else if (addr[15:4] == 12'hFFA)  maplo[addr[3:0]] = dout;
      else if (addr == 16'hFF2F)       progress = dout;
      else if (addr[15:4] == 12'hFF4) begin
        // refplayer's p->ticks counts mod_tick() calls, and a tick's first
        // write is always AINTREQ := $10 - so that write is where a tick starts
        if (addr[3:0] == 4'h4 && dout == 8'h10) trace_tick++;
        if (addr[3:0] != 4'h6 && addr[3:0] != 4'h7 && addr[3:0] != 4'h8 && addr[3:0] != 4'h9)
          $fwrite(fd, "%06d %-7s %s\n", trace_tick, names[addr[3:0]], hex2(dout));
        case (addr[3:0])
          4'h6: sptr[18:16] = dout[2:0];
          4'h7: sptr[15:8] = dout;
          4'h8: sptr[7:0] = dout;
          4'h9: begin
            sram[sptr] = dout; sptr++; sdata_n++;
          end
          4'hB: timer[15:8] = dout;
          4'hC: timer[7:0] = dout;
          4'h5: if (dout[6] && !timer_on) begin timer_on = 1; next_fire = e_count + period_e(); end
          4'h4: if (!dout[7] && dout[4]) n_firq = 1;
          default: ;
        endcase
      end
      else if (!isrom(addr) && addr[15:8] != 8'hFF) ram[phys(addr)] = dout;
    end
    if (timer_on && e_count >= next_fire) begin
      n_firq = 0;
      ticks++;
      next_fire = next_fire + period_e();
    end
  end

  // ---- E and Q: quadrature, Q leading ----------------------------------
  initial forever begin
    #10 Q = 1; #10 E = 1; #10 Q = 0; #10 E = 0;
  end

  string rom_path, trace_path, sram_path;
  initial begin
    if (!$value$plusargs("rom=%s", rom_path)) rom_path = "build/rom.hex";
    if (!$value$plusargs("trace=%s", trace_path)) trace_path = "build/replay.trace";
    void'($value$plusargs("sram=%s", sram_path));
    void'($value$plusargs("ticks=%d", want_ticks));
    $readmemh(rom_path, rom);
    for (int i = 0; i < 16; i++) begin maplo[i] = 0; maphi[i] = 0; end
    maplo[4] = 1; maphi[4] = 1; maplo[5] = 2; maphi[5] = 1;   // boot.asm's handoff
    maplo[6] = 6; maphi[6] = 2;                               // the SIMM block
    maplo[7] = 0; maphi[7] = 1;                               // ROM page 0
    for (int i = 0; i < 524288; i++) sram[i] = 8'h00;
    cpu.cpucore.NMILatched = 1'b1;       // machine_tb.sv says why
    fd = $fopen(trace_path, "w");
    repeat (20) @(negedge E);
    n_reset = 1;
    while (ticks < want_ticks) begin
      @(negedge E);
      if (progress >= 8'hE0) begin
        $display("FAIL  replay_tb: the demo reported $%02h", progress);
        break;
      end
      if (e_count > 64'd2097917 * 120) begin
        $display("FAIL  replay_tb: 120 s of E and only %0d ticks", ticks);
        break;
      end
    end
    // let the last tick's writes land before closing
    repeat (20000) @(negedge E);
    $fclose(fd);
    if (sram_path != "") begin
      fd = $fopen(sram_path, "w");
      for (int i = 0; i < sdata_n && i < 524288; i++) $fwrite(fd, "%s\n", hex2(sram[i]));
      $fclose(fd);
    end
    $display("replay_tb: %0d ticks, %0d sample bytes, progress $%02h, %0d E cycles",
             ticks, sdata_n, progress, e_count);
    $finish;
  end
endmodule
