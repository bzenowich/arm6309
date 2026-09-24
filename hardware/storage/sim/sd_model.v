// sd_model.v - an SD card in SPI mode, behavioural: as much of one as
// hardware/storage/docs/sdcard.md §9.0's initialisation, §9.1/§9.1.1's reads and
// §9.2's write actually ask the driver to talk to.  HAND-WRITTEN; it is a
// model of the PART IN THE SOCKET, not of anything this project fabricates,
// so nothing here is generated and nothing here is fitted.
//
// ** SPI MODE 0, and the edge each side owns.  DI is sampled on SCK's RISING
// edge and DO changes on the FALLING one.  A real card's DO is high-Z with a
// host pull-up, so it is modelled as a 1 whenever the card is deselected or
// has nothing to say.
//
// ** ⚠ THE 74-CLOCK POWER-UP RULE IS A GATE, NOT A NOTE.  SD requires >= 74
// clocks with CS high AND DI high before CMD0, and a card that does not get
// them does not enter SPI mode.  This model counts them (consecutively - a
// low DI resets the count) and REFUSES a CMD0 that arrives early: it answers
// $FF for ever, sets `bad_powerup`, and leaves `card_up` clear.  That is what
// makes storage_card.v's deliberate $00 power-up of the '574 (§6.4 - the part
// has no MR pin, so the hold register really does come up holding garbage)
// catch a driver that skips §9.0 step 1's SDMOSI <- $FF write.  Without the
// refusal the bad driver reads $01 like the good one and the hazard the card
// was designed around is untested.
//
// ** SDHC ONLY, per §9.0.1: CMD58's OCR has CCS set, and CMD17/CMD18/CMD24
// take a BLOCK number, never a byte address.
//
// ** WHAT IS NOT MODELLED, deliberately: CRC7 checking beyond CMD0/CMD8 (the
// spec ignores it in SPI mode and §9.0 hard-codes the two constants that
// matter, so the two constants are what is checked); CMD25; CMD13; card
// removal; and any timing at all - every latency here is counted in whole
// byte times, which is the only unit a bit-banged SPI master can observe.
`default_nettype none

module sd_model #(
    // R1 of ACMD41 is $01 this many times before the card leaves idle, so a
    // driver that does not LOOP (§9.0 step 5) fails instead of passing.
    parameter ACMD41_IDLE = 2,
    parameter NCR         = 2,   // byte times from the last command byte to R1
    parameter READ_LAT    = 4,   // R1 to the $FE data token, CMD17/first CMD18
    parameter MULTI_LAT   = 1,   // and between blocks of a CMD18 stream
    parameter PROG_BYTES  = 8,   // CMD24's program time, DO held low
    parameter NBLOCKS     = 64
) (
    input  wire PORn,   // power-on reset: a fresh card in the socket
    input  wire SCK,
    input  wire MOSI,
    input  wire CSn,
    output wire MISO
);

  localparam NBYTES = NBLOCKS * 512;

  // ⚠ THE WHOLE MODEL IS WRITTEN WITH BLOCKING ASSIGNMENTS AND THAT IS
  // DELIBERATE.  It is a behavioural card, not synthesisable logic: a byte
  // arrives, a command is decoded and the next byte to send is chosen, all
  // inside one edge, and each step reads what the one before it wrote.
  // Nothing in here is ever read by another process on the same edge - the
  // only thing that leaves is MISO, which changes on the OTHER edge.
  /* verilator lint_off BLKSEQ */

  // ---- the backing store --------------------------------------------------
  // A pattern the testbench can predict without being handed it.
  reg [7:0] mem [0:NBYTES-1];
  integer   mi, mv;
  // ⭐ +sdimage=<file> REPLACES THE PATTERN WITH A REAL CARD'S BYTES, added
  // 2026-09-21 so machine3.v can put a card the boot ROM will actually boot
  // from in the socket.  Without the plusarg nothing changes and storage_tb
  // still predicts every byte without being handed it - which is the reason
  // the pattern is there.  ⚠ The file is $readmemh, one byte a line, and it
  // must not be LONGER than NBLOCKS*512 records; run-machine.sh pads and
  // truncates the card image to exactly that.
  string    sdimg;
  initial begin
    for (mi = 0; mi < NBYTES; mi = mi + 1) begin
      mv = (mi / 512) * 7 + (mi % 512) * 13;
      mem[mi] = mv[7:0];
    end
    if ($value$plusargs("sdimage=%s", sdimg)) begin
      $readmemh(sdimg, mem);
      // ⛔ AND IT SAYS WHAT IT LOADED. A $readmemh that silently did not
      // happen leaves the synthetic pattern in place, which is a card with
      // no filesystem on it - and every claim downstream then fails for a
      // reason that has nothing to do with the design.
      $display("      sd_model: %s, %0d blocks, LSN 0 +$F0 = %02x %02x %02x %02x %02x",
               sdimg, NBLOCKS, mem[240], mem[241], mem[242], mem[243], mem[244]);
    end
  end

  function [7:0] peek(input integer b, input integer i);
    peek = mem[b * 512 + i];
  endfunction

  // ---- what the testbench may assert on -----------------------------------
  integer initclk;         // consecutive clocks seen with CS high and DI high
  integer bytes_seen;      // complete bytes exchanged, either direction
  integer cmds_seen;
  reg     power_ok;        // >= 74 of them have gone by
  reg     bad_powerup;     // a CMD0 arrived before they had
  reg     card_up;         // CMD0 was accepted: the card is in SPI mode
  reg     idle_st;         // R1 bit 0
  reg     crc0_bad;        // CMD0 arrived with a CRC other than $95
  reg     crc8_bad;        // CMD8 arrived with a CRC other than $87
  reg [7:0] last_cmd;

  // ---- byte framing -------------------------------------------------------
  reg [7:0] out_sr, in_sr, tx_next;
  reg [2:0] bitn;
  reg       byte_end;

  assign MISO = CSn ? 1'b1 : out_sr[7];

  // ---- the command being assembled ----------------------------------------
  reg [7:0] cmd_buf [0:5];
  integer   cmd_i;
  reg       app_pending;   // the last command was CMD55, so the next is an ACMD
  integer   a41_n;

  // ---- what the card is about to say --------------------------------------
  reg [7:0] resp [0:7];
  integer   resp_n, resp_i, ncr_cnt, busy_n;

  // ---- the outbound data stream (CMD17 / CMD18) ---------------------------
  localparam D_NONE = 0, D_LAT = 1, D_DATA = 2, D_CRC = 3;
  integer    dstate, dlat, dblk, di, ci;
  reg [15:0] dcrc;
  reg        multi;

  // ---- the inbound data block (CMD24) -------------------------------------
  localparam R_CMD = 0, R_TOK = 1, R_DAT = 2, R_CRC = 3;
  integer    rxst, wblk, wi, wci;
  reg [7:0]  wbuf [0:511];

  function [15:0] crc16b(input [15:0] c, input [7:0] d);
    integer k;
    reg [15:0] cc;
    begin
      cc = c;
      for (k = 0; k < 8; k = k + 1)
        cc = {cc[14:0], 1'b0} ^ ((cc[15] ^ d[7-k]) ? 16'h1021 : 16'h0000);
      crc16b = cc;
    end
  endfunction

  function [7:0] r1;
    input dummy;
    r1 = idle_st ? 8'h01 : 8'h00;
  endfunction

  task reset_state;
    integer k;
    begin
      out_sr = 8'hFF; in_sr = 8'hFF; tx_next = 8'hFF; bitn = 3'd0; byte_end = 1'b0;
      initclk = 0; bytes_seen = 0; cmds_seen = 0;
      power_ok = 1'b0; bad_powerup = 1'b0; card_up = 1'b0; idle_st = 1'b1;
      crc0_bad = 1'b0; crc8_bad = 1'b0; last_cmd = 8'hFF;
      cmd_i = 0; app_pending = 1'b0; a41_n = 0;
      resp_n = 0; resp_i = 0; ncr_cnt = 0; busy_n = 0;
      dstate = D_NONE; dlat = 0; dblk = 0; di = 0; ci = 0; dcrc = 16'h0000; multi = 1'b0;
      rxst = R_CMD; wblk = 0; wi = 0; wci = 0;
      for (k = 0; k < 6; k = k + 1) cmd_buf[k] = 8'hFF;
    end
  endtask

  initial reset_state;
  always @(negedge PORn) reset_state;

  task newresp;
    begin resp_n = 0; resp_i = 0; end
  endtask

  task push(input [7:0] v);
    begin resp[resp_n] = v; resp_n = resp_n + 1; end
  endtask

  // ** A COMMAND HAS ARRIVED.  Everything R1-shaped is queued into `resp` and
  // paid out a byte time at a time by pick_tx below; nothing here touches the
  // wire.
  task do_command;
    reg [5:0]  c;
    reg [31:0] arg;
    reg [7:0]  crc;
    reg        app;
    integer    k;
    begin
      c   = cmd_buf[0][5:0];
      arg = {cmd_buf[1], cmd_buf[2], cmd_buf[3], cmd_buf[4]};
      crc = cmd_buf[5];
      app = app_pending; app_pending = 1'b0;
      last_cmd = {2'b00, c};
      cmds_seen = cmds_seen + 1;
      newresp;
      ncr_cnt = NCR;

      if (c == 6'd0) begin
        // §9.0 step 3.  The CRC is checked because the card does not yet know
        // it is in SPI mode; $95 is the only correct value for arg 0.
        if (crc !== 8'h95) crc0_bad = 1'b1;
        if (!power_ok) begin
          // ⚠ THE GATE.  Not an error response - a card that never entered
          // SPI mode has nothing to answer with.
          bad_powerup = 1'b1;
          ncr_cnt = 0;
        end else begin
          card_up = 1'b1; idle_st = 1'b1;
          dstate = D_NONE; multi = 1'b0; rxst = R_CMD;
          push(8'h01);
        end
      end else if (!card_up) begin
        ncr_cnt = 0;                      // still not in SPI mode: silence
      end else begin
        case (c)
          6'd8: begin                      // SEND_IF_COND -> R7
            if (crc !== 8'h87) crc8_bad = 1'b1;
            if (arg[11:0] != 12'h1AA) push(8'h05);
            else begin
              push(r1(1'b0)); push(8'h00); push(8'h00); push(8'h01); push(8'hAA);
            end
          end
          6'd55: begin push(r1(1'b0)); app_pending = 1'b1; end
          6'd41: begin                     // ACMD41, and only after CMD55
            if (!app) push(8'h04);
            else if (!arg[30]) push(8'h05);            // HCS clear: §9.0.1
            else if (a41_n < ACMD41_IDLE) begin a41_n = a41_n + 1; push(8'h01); end
            else begin idle_st = 1'b0; push(8'h00); end
          end
          6'd58: begin                     // READ_OCR: bit 31 done, bit 30 CCS
            push(r1(1'b0));
            push(8'hC0); push(8'hFF); push(8'h80); push(8'h00);
          end
          6'd17: begin
            push(r1(1'b0));
            dblk = arg % NBLOCKS; multi = 1'b0; dstate = D_LAT; dlat = READ_LAT;
          end
          6'd18: begin
            push(r1(1'b0));
            dblk = arg % NBLOCKS; multi = 1'b1; dstate = D_LAT; dlat = READ_LAT;
          end
          6'd12: begin                     // STOP_TRANSMISSION: stuff, R1, busy
            dstate = D_NONE; multi = 1'b0;
            push(8'hFF); push(r1(1'b0));
            busy_n = 2;
          end
          6'd24: begin
            push(r1(1'b0));
            wblk = arg % NBLOCKS; rxst = R_TOK; wi = 0; wci = 0;
          end
          default: push(8'h04);            // illegal command
        endcase
      end
      k = 0;
    end
  endtask

  // ** A BYTE HAS BEEN RECEIVED.
  task on_byte(input [7:0] b);
    integer k;
    begin
      case (rxst)
        R_CMD: begin
          if (cmd_i == 0) begin
            if (b[7:6] == 2'b01) begin cmd_buf[0] = b; cmd_i = 1; end
          end else begin
            cmd_buf[cmd_i] = b;
            cmd_i = cmd_i + 1;
            if (cmd_i == 6) begin cmd_i = 0; do_command; end
          end
        end
        R_TOK: if (b == 8'hFE) begin rxst = R_DAT; wi = 0; end
        R_DAT: begin
          wbuf[wi] = b; wi = wi + 1;
          if (wi == 512) begin rxst = R_CRC; wci = 0; end
        end
        R_CRC: begin
          wci = wci + 1;
          if (wci == 2) begin
            // accepted: commit, answer $05, then hold DO low while it programs
            for (k = 0; k < 512; k = k + 1) mem[wblk * 512 + k] = wbuf[k];
            newresp; ncr_cnt = 0;
            push(8'h05);
            busy_n = PROG_BYTES;
            rxst = R_CMD;
          end
        end
        default: ;
      endcase
    end
  endtask

  // ** WHAT GOES OUT IN THE NEXT BYTE TIME.  The order is the protocol's: the
  // N_CR gap first, then whatever R1-shaped thing is queued, then the program
  // busy, and only then the data stream.
  task pick_tx;
    begin
      if (ncr_cnt > 0) begin
        ncr_cnt = ncr_cnt - 1; tx_next = 8'hFF;
      end else if (resp_i < resp_n) begin
        tx_next = resp[resp_i]; resp_i = resp_i + 1;
      end else if (busy_n > 0) begin
        busy_n = busy_n - 1; tx_next = 8'h00;
      end else begin
        case (dstate)
          D_LAT: begin
            if (dlat > 0) begin dlat = dlat - 1; tx_next = 8'hFF; end
            else begin
              tx_next = 8'hFE; dstate = D_DATA; di = 0; dcrc = 16'h0000;
            end
          end
          D_DATA: begin
            tx_next = mem[dblk * 512 + di];
            dcrc = crc16b(dcrc, tx_next);
            di = di + 1;
            if (di == 512) begin dstate = D_CRC; ci = 0; end
          end
          D_CRC: begin
            tx_next = (ci == 0) ? dcrc[15:8] : dcrc[7:0];
            ci = ci + 1;
            if (ci == 2) begin
              if (multi) begin
                dblk = (dblk + 1) % NBLOCKS; dstate = D_LAT; dlat = MULTI_LAT;
              end else dstate = D_NONE;
            end
          end
          default: tx_next = 8'hFF;
        endcase
      end
    end
  endtask

  // ---- the wire -----------------------------------------------------------
  // ⚠ DI is read here on the SAME rising edge the '165 shifts it on, which is
  // §6.6's accepted hold-time race stated as a scheduling fact: the host's
  // shift is a nonblocking assignment, so this sees the bit that was on the
  // pin before the edge - which is the bit a real card with a positive hold
  // time sees too.  The bench cannot decide §6.6; §12 step 3's scope can.
  always @(posedge SCK) begin
    if (CSn) begin
      // Deselected.  This is the only place SD counts anything: §6.4's 74
      // clocks, which must be CONSECUTIVE and must all have DI high.
      if (MOSI) begin
        initclk = initclk + 1;
        if (initclk >= 74) power_ok = 1'b1;
      end else initclk = 0;
      bitn = 3'd0; in_sr = 8'hFF; byte_end = 1'b0; cmd_i = 0;
    end else begin
      in_sr = {in_sr[6:0], MOSI};
      if (bitn == 3'd7) begin
        bitn = 3'd0;
        byte_end = 1'b1;
        bytes_seen = bytes_seen + 1;
        on_byte(in_sr);
        pick_tx;
      end else bitn = bitn + 1;
    end
  end

  always @(negedge SCK) begin
    if (!CSn) begin
      if (byte_end) begin out_sr = tx_next; byte_end = 1'b0; end
      else out_sr = {out_sr[6:0], 1'b1};
    end
  end

  // A deselect abandons whatever byte was half-clocked; the card does not
  // carry framing across /CS.
  always @(posedge CSn) begin
    bitn = 3'd0; byte_end = 1'b0; cmd_i = 0; out_sr = 8'hFF;
  end

  /* verilator lint_on BLKSEQ */

endmodule
`default_nettype wire
