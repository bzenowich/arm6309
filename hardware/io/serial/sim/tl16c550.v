// A TL16C550C, as a bus-functional model: the serial card's UART
// (hardware/io/serial/docs/serial.md 7), for the machine to have a console.
//
// ⚠ THIS IS A MODEL OF A BOUGHT PART, NOT A DESIGN OUTPUT. Nothing in it is
// fitted or placed; it exists so that software on the machine - NitrOS-9's
// sc16550 driver, first - talks to a register set that behaves like the
// datasheet's, and so a testbench can type at it and read what it prints.
// It is written from the same behaviour software/emu/machine.c models,
// and those two must agree.
//
// WHAT IT MODELS
//   - the eight registers at A2..A0, with LCR b7's divisor latch over 0 and 1
//   - 16-byte receive and transmit FIFOs. A transmitted character takes ten
//     bits at 7,372,800 / 16 / divisor baud, counted in dots, so THRE comes
//     back when the line has really sent it
//   - IIR's priorities, as serial.md 7.3 tabulates them: receive data at or
//     above FCR's trigger level ($04), the character timeout four character
//     times after the receive FIFO last moved ($0C), THR empty ($02, cleared
//     by reading IIR or writing THR)
//   - INTR, asserted high, for the board to turn into open-drain /IRQ
//
// WHAT IT DOES NOT
//   - line status errors, break, the modem-status interrupt. MSR reads $B0,
//     CTS, DSR and DCD asserted, with no deltas. MCR is a latch
//   - the pins' timing. Registers are written from the byte on D0-D7 at E's
//     fall and a read's side effect (RBR's pop, IIR's THRE clear) lands one
//     dot after it, so the CPU has already sampled the byte it pops.
//
// THE BENCH'S SIDE: tx_strobe pulses for one CLK25 period with tx_byte as
// each character finishes on the line; rx_push() queues a character as if it
// had just arrived.

`default_nettype none

module tl16c550 (
    input  wire       CLK25,      // the dot clock: the model's only clock
    input  wire       RESET,      // asserted high
    input  wire       SEL,        // the card's decode: this window, this cycle
    input  wire       E,
    input  wire       RW,
    input  wire [2:0] A,
    input  wire [7:0] DIN,
    output wire [7:0] DOUT,       // the register the current cycle reads
    output wire       INTR,
    output reg        tx_strobe,
    output reg  [7:0] tx_byte
);

  // 25,175,000 / 7,372,800 dots per crystal cycle, times 16 x 10 per character
  // per unit of divisor: 546.3. Integer, rounded; 0.05 % is inside any UART's
  // tolerance and nothing here measures the baud rate.
  localparam int DOTS_PER_CHAR_PER_DIV = 546;

  reg [7:0] ier, lcr, mcr, scr, dll, dlm, fcr;
  reg [7:0] rxf [0:15];
  reg [7:0] txf [0:15];
  reg [4:0] rx_n, tx_n;
  reg [3:0] rx_head, tx_head;
  reg       thre_int;
  int       tx_dots;              // dots left on the character being sent
  int       rx_idle;              // dots since the receive FIFO last moved
  int       rx_line;              // dots since the last character arrived: one per character time

  wire dlab = lcr[7];
  wire [15:0] divisor = {dlm, dll};
  wire [31:0] char_dots = DOTS_PER_CHAR_PER_DIV * ((divisor == 16'd0) ? 32'd1 : {16'd0, divisor});

  reg [4:0] trig;
  always @* case (fcr[7:6])
    2'b00: trig = 5'd1;  2'b01: trig = 5'd4;  2'b10: trig = 5'd8;  default: trig = 5'd14;
  endcase
  wire rx_level   = fcr[0] ? (rx_n >= trig) : (rx_n != 5'd0);
  wire rx_timeout = (rx_n != 5'd0) && (rx_idle >= 4 * char_dots);
  wire rx_int     = ier[0] && (rx_level || rx_timeout);
  wire tx_int     = ier[1] && thre_int;
  assign INTR = rx_int || tx_int;

  wire [7:0] fifo_bits = fcr[0] ? 8'hC0 : 8'h00;
  wire [7:0] iir = rx_int ? (fifo_bits | (rx_level ? 8'h04 : 8'h0C))
                 : tx_int ? (fifo_bits | 8'h02)
                 :          (fifo_bits | 8'h01);
  wire [7:0] lsr = {1'b0, (tx_n == 5'd0) && (tx_dots == 0), tx_n == 5'd0, 4'b0000, rx_n != 5'd0};

  reg [7:0] rd;
  always @* case (A)
    3'd0: rd = dlab ? dll : ((rx_n != 5'd0) ? rxf[rx_head] : 8'h00);
    3'd1: rd = dlab ? dlm : ier;
    3'd2: rd = iir;
    3'd3: rd = lcr;
    3'd4: rd = mcr;
    3'd5: rd = lsr;
    3'd6: rd = 8'hB0;
    default: rd = scr;
  endcase
  assign DOUT = rd;

  // ---- the cycle, as seen from the dot clock -----------------------------
  // What the cycle was, captured while E is high; its effect lands at the
  // first dot after E falls.
  reg       e_d, sel_h, rw_h;
  reg [2:0] a_h;
  reg [7:0] din_h, iir_h;

  // rx_push's queue, drained into the FIFO on the dot clock so that only one
  // process writes the FIFO
  reg [7:0] inq [0:255];
  reg [7:0] inq_head = 8'd0, inq_tail = 8'd0;
  task automatic rx_push(input logic [7:0] c);
    inq[inq_tail] = c;
    inq_tail = inq_tail + 8'd1;
  endtask

  // The FIFO counts can move three ways in one dot - a character arriving, one
  // leaving the line, and the CPU's read or write - so each is computed as a
  // running value and assigned once, rather than as three competing <=.
  reg [4:0] rn, tn;
  reg [3:0] rh, th;
  always @(posedge CLK25) begin
    tx_strobe <= 1'b0;
    if (RESET) begin
      ier <= 0; lcr <= 0; mcr <= 0; scr <= 0; dll <= 0; dlm <= 0; fcr <= 0;
      rx_n <= 0; tx_n <= 0; rx_head <= 0; tx_head <= 0; thre_int <= 0;
      tx_dots <= 0; rx_idle <= 0; rx_line <= 0; e_d <= 0; sel_h <= 0; rw_h <= 1;
      inq_head <= inq_tail;
    end else begin
      rn = rx_n; tn = tx_n; rh = rx_head; th = tx_head;
      e_d <= E;
      if (E) begin
        sel_h <= SEL; rw_h <= RW; a_h <= A; din_h <= DIN; iir_h <= iir;
      end

      rx_idle <= rx_idle + 1;
      rx_line <= rx_line + 1;

      // the transmitter: one character on the line at a time
      if (tx_dots > 0) begin
        tx_dots <= tx_dots - 1;
        if (tx_dots == 1) begin
          tx_strobe <= 1'b1;
          tx_byte <= txf[th];
          th = th + 4'd1;
          tn = tn - 5'd1;
          if (tn == 5'd0) thre_int <= 1'b1;
        end
      end else if (tn != 5'd0) begin
        tx_dots <= char_dots;
      end

      // the end of a cycle addressed to this part
      if (e_d && !E && sel_h) begin
        if (!rw_h) begin
          case (a_h)
            3'd0: if (lcr[7]) dll <= din_h;
                  else if (tn < 5'd16) begin
                    txf[th + tn[3:0]] <= din_h;
                    tn = tn + 5'd1;
                    thre_int <= 1'b0;
                  end
            3'd1: if (lcr[7]) dlm <= din_h;
                  else begin
                    if (din_h[1] && !ier[1] && tn == 5'd0) thre_int <= 1'b1;
                    ier <= {4'd0, din_h[3:0]};
                  end
            3'd2: begin
                    fcr <= din_h;
                    if (din_h[1]) begin rn = 0; rh = 0; end
                    if (din_h[2]) begin tn = 0; th = 0; tx_dots <= 0; end
                  end
            3'd3: lcr <= din_h;
            3'd4: mcr <= din_h;
            3'd7: scr <= din_h;
            default: ;
          endcase
        end else begin
          if (a_h == 3'd0 && !lcr[7] && rn != 5'd0) begin
            rh = rh + 4'd1;
            rn = rn - 5'd1;
            rx_idle <= 0;
          end
          if (a_h == 3'd2 && iir_h[3:0] == 4'h2) thre_int <= 1'b0;
        end
      end

      // a character arriving
      if (inq_head != inq_tail && rn < 5'd16 && rx_line >= char_dots) begin
        rxf[rh + rn[3:0]] <= inq[inq_head];
        inq_head <= inq_head + 8'd1;
        rn = rn + 5'd1;
        rx_idle <= 0;
        rx_line <= 0;
      end

      rx_n <= rn; tx_n <= tn; rx_head <= rh; tx_head <= th;
    end
  end

endmodule
`default_nettype wire
