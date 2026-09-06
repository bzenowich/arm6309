// The MMU sequencer, motherboard U3 - the same equations as mmu.pld.
//
// A model of a GAL22V10, not a design to synthesise. It exists so that the
// orderings graphics.md 6.3.1 calls load-bearing can be asserted mechanically,
// which a fitter checks nothing about - see mmu_tb.sv. Keep it in step with
// mmu.pld by hand; there are seven equations and they are the deliverable.
`default_nettype none

module mmu (
    // Logical address, and the range is the point: this GAL has no LA3..LA0
    // pins. The entry index goes to the '157, not here, and that is why the
    // control register at $FFB0 is aliased across sixteen addresses - see
    // README.md, the pin budget.
    input  wire [15:4] la,
    input  wire        e,       // 6809 E
    input  wire        q,       // 6809 Q, leading E by 90 degrees
    input  wire        rw,      // high = read

    output wire        n_iopage,
    output wire        muxsel,
    output wire        n_isooe,
    output wire        n_mapwe,
    output wire        n_mapoe,
    output wire        n_ctrlcp   // '574 CP: rises at E-fall, once per write
);

  // $FF00-$FFFF
  wire iopage = &la[15:8];

  // $FFA0-$FFBF, split by A4
  wire mmusel = iopage & la[7] & ~la[6] & la[5];
  wire blksel = mmusel & ~la[4];   // $FFA0-$FFAF, 16 block registers
  wire ctlsel = mmusel &  la[4];   // $FFB0-$FFBF, control, aliased

  assign n_iopage = ~iopage;
  assign muxsel   =  blksel;
  assign n_isooe  = ~(blksel & e);
  assign n_mapwe  = ~(blksel & ~rw & e & ~q);
  assign n_mapoe  = ~(~iopage | (blksel & rw & e));
  assign n_ctrlcp = ~(ctlsel & ~rw & e);

endmodule

`default_nettype wire
