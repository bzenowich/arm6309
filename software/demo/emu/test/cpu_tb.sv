// THE REFERENCE SIDE OF THE DIFFERENTIAL TEST: mc6809e on 64 K of flat RAM.
//
//   obj_cpu/cpu_tb +image=prog.hex +sched=prog.sched +trace=v.trace +maxcyc=N
//
// Writes one line per instruction boundary and one per bus write, in the
// format cpu_run.c writes, so `cmp` names the first divergence:
//
//   <cycle> <PC> <A> <B> <X> <Y> <U> <S> <DP> <CC>     at each boundary
//   <cycle> W <addr> <value>                           at each write
//
// ⚠ A BOUNDARY IS CpuState == CPUSTATE_FETCH_I1, NOT LIC. The core raises LIC
// on the last cycle of an instruction but also through every cycle of an
// interrupt's stacking, its vector fetch, SYNC and HALT - so LIC marks
// "not mid-instruction" and cannot count instructions. FETCH_I1 is the one
// state every instruction and every interrupt entry starts from; the
// registers read at the falling edge that ends it are the architectural state
// between instructions. Cycle 0 is the first FETCH_I1 after reset.
//
// The schedule is "<cycle> <line> <level>" per line, line 0 IRQ, 1 FIRQ,
// 2 NMI, level 1 = asserted, sorted by cycle: the level is on the pin during
// that cycle and after it. A write to $FFE0 ends the run.
`timescale 1ns/1ps

module cpu_tb;
  logic E = 0, Q = 0, n_reset = 0, n_irq = 1, n_firq = 1, n_nmi = 1;
  wire [7:0] dout;
  wire [15:0] addr;
  wire rnw, bs, ba, avma, busy, lic;
  logic [7:0] mem [0:65535];
  wire [7:0] din = mem[addr];

  mc6809e cpu (.D(din), .DOut(dout), .ADDR(addr), .RnW(rnw), .E(E), .Q(Q),
               .BS(bs), .BA(ba), .nIRQ(n_irq), .nFIRQ(n_firq), .nNMI(n_nmi),
               .AVMA(avma), .BUSY(busy), .LIC(lic), .nHALT(1'b1), .nRESET(n_reset));

  localparam FETCH_I1 = 7'd4, NMI_START = 7'd87, IRQ_START = 7'd89, FIRQ_START = 7'd93,
             CWAI_POST = 7'd110, IRQ_VECTOR_HI = 7'd91;

  longint ev_t [$];
  int ev_line [$], ev_lvl [$];
  int ei = 0;
  longint cyc = 0, maxcyc = 1000000;
  bit started = 0, done = 0;
  longint nbound = 0, nwrite = 0, n_irq_e = 0, n_firq_e = 0, n_nmi_e = 0, n_cwai_e = 0;
  int fd;

  always @(negedge E) begin
    if (!started && cpu.cpucore.CpuState == FETCH_I1) started = 1;
    if (started && !done) begin
      if (cpu.cpucore.CpuState == FETCH_I1) begin
        if (cyc >= maxcyc) done = 1;
        else begin
          $fwrite(fd, "%0d %04x %02x %02x %04x %04x %04x %04x %02x %02x\n", cyc,
                  cpu.cpucore.pc, cpu.cpucore.a, cpu.cpucore.b, cpu.cpucore.x, cpu.cpucore.y,
                  cpu.cpucore.u, cpu.cpucore.s, cpu.cpucore.dp, cpu.cpucore.cc);
          nbound++;
        end
      end
      case (cpu.cpucore.CpuState)
        NMI_START:  n_nmi_e++;
        IRQ_START:  n_irq_e++;
        FIRQ_START: n_firq_e++;
        CWAI_POST:  if (cpu.cpucore.CpuState_nxt == IRQ_VECTOR_HI) n_cwai_e++;
        default: ;
      endcase
      if (!done && !rnw) begin
        $fwrite(fd, "%0d W %04x %02x\n", cyc, addr, dout);
        mem[addr] = dout;
        nwrite++;
        if (addr == 16'hFFE0) done = 1;
      end
      cyc++;
      while (ei < ev_t.size() && ev_t[ei] <= cyc) begin
        case (ev_line[ei])
          0: n_irq = !ev_lvl[ei];
          1: n_firq = !ev_lvl[ei];
          default: n_nmi = !ev_lvl[ei];
        endcase
        ei++;
      end
    end
  end

  initial forever begin
    #10 Q = 1; #10 E = 1; #10 Q = 0; #10 E = 0;
  end

  string image, sched, trace;
  initial begin
    int sf, r;
    longint t;
    int l, v;
    if (!$value$plusargs("image=%s", image)) image = "prog.hex";
    if (!$value$plusargs("sched=%s", sched)) sched = "prog.sched";
    if (!$value$plusargs("trace=%s", trace)) trace = "v.trace";
    void'($value$plusargs("maxcyc=%d", maxcyc));
    $readmemh(image, mem);
    sf = $fopen(sched, "r");
    if (sf != 0) begin
      while (!$feof(sf)) begin
        r = $fscanf(sf, "%d %d %d\n", t, l, v);
        if (r == 3) begin ev_t.push_back(t); ev_line.push_back(l); ev_lvl.push_back(v); end
        else break;
      end
      $fclose(sf);
    end
    // machine_tb.sv: a two-state simulator powers NMILatched up asserted
    cpu.cpucore.NMILatched = 1'b1;
    fd = $fopen(trace, "w");
    repeat (20) @(negedge E);
    n_reset = 1;
    // bounded: every program ends by writing $FFE0 or reaching maxcyc
    while (!done) begin
      @(negedge E);
      if (cyc > maxcyc + 200000) begin
        $display("FAIL  cpu_tb: no boundary within 200000 cycles of maxcyc");
        break;
      end
    end
    $fclose(fd);
    $display("cpu_tb: %0d boundaries, %0d writes, %0d cycles; entries IRQ %0d FIRQ %0d NMI %0d, from CWAI %0d",
             nbound, nwrite, cyc, n_irq_e, n_firq_e, n_nmi_e, n_cwai_e);
    $finish;
  end
endmodule
