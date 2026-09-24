// audio.md 6.2 and 16 item 43: what the AD7528 needs from the card, claimed
// on every converter write of a whole run. Included by audio_tb and modplay_tb,
// both of which name the card `card` and define `ok`.
//
// ⛔ WHY IT EXISTS. The card strobed its converters for 35 ns against a 90 ns
// write pulse, moved the DAC select on the edge it strobed on, and wrote
// volume codes into sample converters - and 225 Verilator claims passed,
// because a model that captures on a clock edge captures at any width, and
// every claim compared a converter against the byte the design intended rather
// than against the byte its own channel owned. These are both halves.
//
// Sampled on the slot edge, where U2's registers and S3 still hold the slot
// that just ended - which is the slot a transparent latch was following.
//
// A comment line here must never begin with the simulator's own name.

int cvc_runs = 0, cvc_badw = 0, cvc_unstable = 0;
int cvc_samp_caps = 0, cvc_samp_bad = 0, cvc_vol_caps = 0, cvc_vol_bad = 0;
int cvc_len [0:2];
bit cvc_told = 0;
bit cvc_ok_last [0:2];            // stable through the last active slot seen
logic [7:0] cvc_gotL [0:2], cvc_gotR [0:2], cvc_expL [0:2], cvc_expR [0:2];
logic [7:0] cvc_hL [0:4], cvc_hR [0:4];
logic       cvc_hS [0:4];
initial for (int k = 0; k < 3; k++) cvc_len[k] = 0;

function automatic logic [7:0] cvc_pend(input int ch); return card.SF[ch * 8][23:16];     endfunction
function automatic logic [7:0] cvc_vol (input int ch); return card.SF[ch * 8 + 6][23:16]; endfunction

// The monitor keeps a five-slot history and reads it in the same process, so
// its assignments are blocking on purpose. The pragma below is deliberate.
/* verilator lint_off BLKSEQ */
always @(posedge SLOTCLK) begin : cvc_watch
  logic [2:0] act;
  bit stable;
  act = {card.CSV, card.CSSR, card.CSSL};
  for (int k = 4; k > 0; k--) begin
    cvc_hL[k] = cvc_hL[k - 1]; cvc_hR[k] = cvc_hR[k - 1]; cvc_hS[k] = cvc_hS[k - 1];
  end
  cvc_hL[0] = card.PORTL; cvc_hR[0] = card.PORTR; cvc_hS[0] = card.S3;

  for (int i = 0; i < 3; i++) begin
    if (act[i]) begin
      cvc_len[i]++;
      // ⭐ the frame boundary switched the select and the port; from there to
      // the capturing edge - five slots, 0 to 4 - nothing the strobed
      // package reads may move, and nothing may be X (a fight, or a float).
      stable = 1;
      for (int k = 1; k < 5; k++) begin
        if (cvc_hS[k] !== cvc_hS[0]) stable = 0;
        if ((i != 1) && cvc_hL[k] !== cvc_hL[0]) stable = 0;
        if ((i != 0) && cvc_hR[k] !== cvc_hR[0]) stable = 0;
      end
      if (((i != 1) && $isunknown(cvc_hL[0])) || ((i != 0) && $isunknown(cvc_hR[0]))
          || $isunknown(cvc_hS[0])) stable = 0;
      cvc_ok_last[i] = stable;
      cvc_gotL[i] = cvc_hL[0];  cvc_gotR[i] = cvc_hR[0];
      if (i == 2) begin
        cvc_expL[i] = cvc_vol(cvc_hS[0] ? 3 : 0);  cvc_expR[i] = cvc_vol(cvc_hS[0] ? 2 : 1);
      end else begin
        cvc_expL[i] = cvc_pend(cvc_hS[0] ? 3 : 0); cvc_expR[i] = cvc_pend(cvc_hS[0] ? 2 : 1);
      end
    end else if (cvc_len[i] > 0) begin
      // the strobe rose on the edge before this one: that was the capture
      cvc_runs++;
      if (cvc_len[i] != 3) cvc_badw++;
      if (!cvc_ok_last[i]) cvc_unstable++;
      case (i)
        0: begin cvc_samp_caps++; if (cvc_gotL[i] !== cvc_expL[i]) cvc_samp_bad++; end
        1: begin cvc_samp_caps++; if (cvc_gotR[i] !== cvc_expR[i]) cvc_samp_bad++; end
        2: begin
             cvc_vol_caps += 2;
             if (cvc_gotL[i] !== cvc_expL[i]) cvc_vol_bad++;
             if (cvc_gotR[i] !== cvc_expR[i]) cvc_vol_bad++;
           end
      endcase
      if (!cvc_told && (cvc_samp_bad + cvc_vol_bad) > 0) begin
        cvc_told = 1;
        $display("      [conv] first wrong capture: strobe %0d S3=%b got L %02h R %02h, owned L %02h R %02h",
                 i, cvc_hS[1], cvc_gotL[i], cvc_gotR[i], cvc_expL[i], cvc_expR[i]);
      end
      cvc_len[i] = 0;
    end
  end
end
/* verilator lint_on BLKSEQ */

task automatic conv_report();
  ok(cvc_runs > 0 && cvc_badw == 0,
     $sformatf("⭐ 16 item 43: every AD7528 /CS is low for exactly three slots, 106 ns against the part's 100 ns write pulse (%0d strobes, %0d another width)",
               cvc_runs, cvc_badw));
  ok(cvc_runs > 0 && cvc_unstable == 0,
     $sformatf("⭐ and the port and the DAC select hold one driven value for five slots, from the frame boundary to the capturing edge - at least 138 ns of setup after the '574's 38 ns enable, against 90 ns, and the select never moves under a transparent latch (%0d strobes did not)",
               cvc_unstable));
  ok(cvc_samp_caps > 0 && cvc_samp_bad == 0,
     $sformatf("⭐ every sample-converter capture is its OWN channel's PEND byte - never a volume code, never the partner's sample (%0d captures, %0d wrong)",
               cvc_samp_caps, cvc_samp_bad));
  ok(cvc_vol_caps > 0 && cvc_vol_bad == 0,
     $sformatf("and every volume-converter capture is that channel's VOL (%0d captures, %0d wrong)",
               cvc_vol_caps, cvc_vol_bad));
endtask
