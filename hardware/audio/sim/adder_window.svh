// audio.md 16 item 37: how long the '283 chain is given to settle, MEASURED
// on the running design rather than derived from PROGRAM's geometry. Included
// by audio_tb and modplay_tb, both of which name the card `card` and define `ok`.
//
// ⛔ WHY IT EXISTS. The 16-bit ripple is 192 ns at 25 C and 240 ns over
// temperature (the CD74HC283 sheet, arom.check.ts), and two adjacent work
// slots give it 53. The re-timing puts every adder write in slot 5 with the
// operands latched in slot 7 of the colour clock before; this is what says
// whether every write in a whole run really waited that long, including the
// ones a chained or host-delayed sequence produced.
//
// What is measured: for every state-file write that takes the adder's sum
// (SUMOE with any SFWE lane), the time since the adder's inputs last moved -
// ALAT or BLAT clocked, or BLATOE, ONESOE or ACIN changed. Half-slot
// resolution: the state file and both latches take their data on the falling
// slot edge, U2's registered selects change on the rising one.
//
// ⚠ It is logic time, not silicon: the '244's 23 ns and the SRAM's 6 ns setup
// are inside the window, and no delay is modelled. The claim is that the
// window the sequencer GIVES is at least what the datasheet path needs.
//
// A comment line here must never begin with the simulator's own name.

longint adw_t = 0;                 // half-slots since reset
longint adw_last_in = 0;
longint adw_min = 64'h7fffffffffffffff;
int     adw_writes = 0;
logic   adw_q_blatoe = 0, adw_q_onesoe = 0, adw_q_acin = 0;

// One process on both slot edges: the counters are written from one place.
always @(SLOTCLK) begin
  adw_t <= adw_t + 1;
  if (SLOTCLK) begin
    if (card.BLATOE !== adw_q_blatoe || card.ONESOE !== adw_q_onesoe || card.ACIN !== adw_q_acin)
      adw_last_in <= adw_t;
    adw_q_blatoe <= card.BLATOE; adw_q_onesoe <= card.ONESOE; adw_q_acin <= card.ACIN;
  end else begin
    if (card.SUMOE && (card.SFWE0 || card.SFWE1 || card.SFWE2)) begin
      adw_writes <= adw_writes + 1;
      if (adw_t - adw_last_in < adw_min) adw_min <= adw_t - adw_last_in;
    end
    if (card.ALATCK || card.BLATCK) adw_last_in <= adw_t;
  end
end

// 35.24 ns per slot (audio.md 3.1), so 17.62 per half-slot, in picoseconds.
function automatic longint adw_ps(input longint half); return half * 17620; endfunction

// ⭐ The bar is the datasheet path at 25 C: 163 ns of carry, the '244's 23 and
// the SRAM's 6 - 192 ns. The window is reported against it and against the
// 240 ns over-temperature figure, which item 37 records as not closing.
task automatic adder_window_report();
  ok(adw_writes > 0 && adw_ps(adw_min) >= 192000,
     $sformatf("⭐ 16 item 37: every adder write waited for the '283 chain - the shortest window in %0d sum writes is %0d half-slots, %0d.%01d ns, against the datasheet's 192 ns (240 over temperature)",
               adw_writes, adw_min, adw_ps(adw_min) / 1000, (adw_ps(adw_min) % 1000) / 100));
endtask
