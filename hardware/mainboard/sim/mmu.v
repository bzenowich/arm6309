// The MMU sequencer, motherboard U3 - the same equations as mmu.pld.
//
// A model of a GAL22V10, not a design to synthesise. It exists so that the
// orderings graphics.md 6.3.1 calls load-bearing can be asserted mechanically,
// which a fitter checks nothing about - see mmu_tb.sv. Keep it in step with
// mmu.pld by hand; there are eight equations and they are the deliverable.
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

    output wire        blkhi,     // which map SRAM a write lands in - U9's job
    output wire        blklo,      //   on the board; exported here for the sim
    output wire        n_iopage,
    output wire        muxsel,
    // TWO ISOLATION ENABLES since 2026-09-09. A common-I/O SRAM drives its own
    // DQ pins for the whole of every translation, so the map's two byte-wide
    // parts are two nodes and each needs its own '245 - and one shared enable
    // would put both buffers on D0-D7 for the whole of any block read, one of
    // them driving from a floating node. design-review2.md M-1, second half:
    // the decode had two windows and the BOARD had no data path to the high
    // SRAM at all.
    output wire        n_isooe_lo,  // U4  - $FFA0-$FFAF, physical A20..A13
    output wire        n_isooe_hi,  // U18 - $FF90-$FF9F, physical A24..A21
    output wire        n_mapwe,
    output wire        n_mapoe,
    output wire        n_ctrlcp   // '574 CP: rises at E-fall, once per write
);

  // $FF00-$FFFF
  wire iopage = &la[15:8];

  // $FF90-$FFBF, split by A5:A4. TWO block windows since 2026-09-09: the
  // write index is LA3..LA0 through U5's '157, so LA3 is the TASK bit and
  // cannot also pick which of the two map SRAMs a write lands in. See
  // mmu.pld; $FF80-$FF8F is the fourth code and is free.
  wire mmusel = iopage & la[7] & ~la[6];
  assign blkhi = mmusel & ~la[5] &  la[4];  // $FF90-$FF9F, high byte
  assign blklo = mmusel &  la[5] & ~la[4];  // $FFA0-$FFAF, low byte
  wire blksel  = blkhi | blklo;             // same index, same strobes
  wire ctlsel = mmusel &  la[5] &  la[4];   // $FFB0-$FFBF, control, aliased

  assign n_iopage = ~iopage;
  assign muxsel   =  blksel;
  assign n_isooe_lo = ~(blklo & e);
  assign n_isooe_hi = ~(blkhi & e);
  assign n_mapwe  = ~(blksel & ~rw & e & ~q);
  assign n_mapoe  = ~(~iopage | (blksel & rw & e));
  assign n_ctrlcp = ~(ctlsel & ~rw & e);

endmodule

`default_nettype wire
