/* U9's behaviour - the physical space decode - as arithmetic.
 *
 * hardware/ram.md 6.3 and 6.7. This part answers one question about every bus
 * cycle: WHICH MEMORY, IF ANY, IS THIS? The 32 MB map of ram.md 5.2 has four
 * inhabited regions and U9 decodes three of them (the video ring and the card
 * buffers are decoded on the cards themselves, which is what /IOPAGE is for).
 *
 * Deliberately NOT a sum of products. u9.jedec.ts holds the terms a 22V10
 * implements; this file states the intent in ranges and comparisons, so that
 * jedec.check.ts compares the fuses against an independent statement rather
 * than against the same one twice. It is the same split mmu.model.ts and
 * clkdec.model.ts make, and the reason is the same: on 2026-09-07 two errors
 * survived 178 passing checks because the assembler and the simulator shared
 * one description and agreed with each other.
 */

/** ram.md 5.2, as byte addresses. */
export const MAP = {
  /** The boot ROM: 1 MB at 2.0-3.0 M. machine.md 7.2. */
  romBase: 0x200000,
  romTop: 0x300000,
  /** Four 4 MB SIMM windows, 4-20 M. ram.md 6. */
  simmBase: 0x400000,
  simmTop: 0x1400000,
  /** Below this, a card may answer; above it, U9 pulls /IOPAGE and none does.
   *  ram.md 5.3 - it is what saves four backplane pins. */
  cardCeiling: 0x200000,
} as const

export interface In {
  /** Physical A24..A19, off the two map SRAMs. Only A24..A19 reach this part. */
  pa: number
  /** U3's /IOPAGE PIN level: low when the cycle is logical $FF00-$FFFF. */
  nIopage: 0 | 1
  /** U6's RUN register. 0 is boot mode. */
  run: 0 | 1
  la7: 0 | 1
  la6: 0 | 1
  la5: 0 | 1
  la4: 0 | 1
  la3: 0 | 1
  rw: 0 | 1
}

export interface Out {
  /** The two 512K x 8 flash devices, machine.md 7.2. Active low. */
  nRomCe0: 0 | 1
  nRomCe1: 0 | 1
  /** The backplane's /IOPAGE - U3's term, plus everything above 2 MB. */
  nIopageBp: 0 | 1
  /** To U10, which turns it into one of four RAS. Active high. */
  dramSel: 0 | 1
  /** The two map SRAMs. Active low. */
  nMapCeLo: 0 | 1
  nMapCeHi: 0 | 1
}

const not = (b: boolean): 0 | 1 => (b ? 0 : 1)
const yes = (b: boolean): 0 | 1 => (b ? 1 : 0)

/** Physical A24..A19 as this part sees them, from a full byte address. */
export const paOf = (byteAddr: number): number => (byteAddr >>> 19) & 0x3f

export const u9 = (i: In): Out => {
  const iopage = !i.nIopage // an $FF00-$FFFF cycle
  const boot = !i.run

  /* $FFC0-$FFFF, the vector page. ONE product term, because /IOPAGE already
   * means "logical $FF00-$FFFF": the vector page is that page with A7 and A6
   * both high. U6 forms the same condition for the boot buffer's output enable, from
   * the same two pins. machine.md 7.2. */
  const vecsel = iopage && !!i.la7 && !!i.la6

  /* $FFA0-$FFAF, the sixteen block registers. Layout A (ram.md 4.1) puts the
   * low byte at $FFA0-$FFA7 and the high byte at $FFA8-$FFAF, so LA3 picks
   * which SRAM a write lands in. Both are selected for a translation. */
  const blksel = iopage && !!i.la7 && !i.la6 && !!i.la5 && !i.la4

  /* A24..A19, shifted so the comparisons read like the map. */
  const above = (n: number) => i.pa >= n >>> 19
  const within = (lo: number, hi: number) => i.pa >= lo >>> 19 && i.pa < hi >>> 19

  /* The ROM answers three ways, and the first two ignore the physical address
   * entirely - which is the point, because at reset the map SRAM's contents
   * are whatever they are and the '244 is driving A20..A13 to zero. */
  const romsel =
    (boot && !iopage) || // boot mode, outside $FF00-$FFBF
    vecsel || // the vector page, forever
    (within(MAP.romBase, MAP.romTop) && !iopage) // ordinary mapped memory

  /* Physical A19 picks the device. During boot and vector cycles the '244
   * drives it low, so both land in device 0's first 8 KB - which is where the
   * boot monitor and the vector table live. */
  const a19 = (i.pa & 1) as 0 | 1

  return {
    /* /OE is tied low on both devices and /CE carries R/W, which is the same
     * move gal/README.md makes for the system RAM's /OE and for the same
     * reason: a ROM that drives during a write cycle fights the CPU. */
    nRomCe0: not(romsel && !a19 && !!i.rw),
    nRomCe1: not(romsel && !!a19 && !!i.rw),

    /* U3's term, plus every access above the bottom 2 MB - ram.md 5.3, which
     * is what lets a card decode A0-A20 and stay silent above it for no
     * backplane pins at all.
     *
     * GATED ON RUN, and that is not decoration: during boot the high map SRAM
     * is deselected and A24..A21 float, so an ungated compare would assert
     * /IOPAGE at random - and /IOSEL is /IOPAGE AND /A7, so a random assertion
     * makes every card decode a fetch. */
    nIopageBp: not(iopage || (!!i.run && above(MAP.cardCeiling))),

    dramSel: yes(!iopage && !!i.run && within(MAP.simmBase, MAP.simmTop)),

    /* The map SRAMs drive the physical address on every ordinary cycle, and
     * are addressed by the CPU during a block-register access. They are
     * DESELECTED for the whole of boot mode and for the vector page, which is
     * exactly when U6 has the buffer driving instead. */
    nMapCeLo: not((!!i.run && !iopage) || (blksel && !i.la3)),
    nMapCeHi: not((!!i.run && !iopage) || (blksel && !!i.la3)),
  }
}
