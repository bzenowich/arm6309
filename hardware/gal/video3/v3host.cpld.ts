/* v3host - video3's backplane, register decode and palette write path.
 *
 * video3/docs/partition.md §2.4.  The pin-bound part: a fifth of its macrocells
 * and two thirds of its pins, because the backplane is 27 signals on its own
 * (signals.md §2.1) and it is where they land.  Merging it into any neighbour
 * overflows PINS, never cells - §7 has that arithmetic.
 *
 * ⭐ IT NEEDS NO INTERNAL DATA BUS.  Every register it touches is a discrete
 * latch or counter that loads from IDB itself - PIDX is two '163 and a '574,
 * PDATL/PDATH are two '573 - so this part only STROBES them.  Eight pins that
 * the census had it spending.
 */

import { toCupl, type Merged } from "../jedec/cupl"
import type { Cell } from "../jedec/assemble"

const reg = (name: string, terms: string[]): Cell =>
  ({ pin: 0, name, assertedLow: false, s0: 1 as const, registered: true, terms })
const comb = (name: string, terms: string[], oe?: string): Cell =>
  ({ pin: 0, name, assertedLow: false, s0: 1 as const, registered: false, terms, oe })

/* -- the window, and the two decodes that are not register writes --------
 *
 * machine.md §5 item 1 A: /IOSEL is the $FF00-$FF7F strobe common to every
 * slot, so a card matches A0-A6 against its base.  ⚠ A6 is NOT implied by the
 * strobe since the window widened - a card that matches only A0-A5 answers at
 * its base AND 64 bytes below it. */
const REGSEL = "IOSEL & A6 & A5"
/* graphics.md §6.3.2: the ring is A20 = 0, A19 = 1 - the second quarter of a
 * 2 MB map, and NOT the top half of a 1 MB one. */
const VRAMSEL = "!IOSEL & A19 & !A20"

/* ⭐ THE ESCAPE, and this part is the reason it exists.
 *
 * "strobes" gives every register its own load line, which is what the three
 * fitted parts declare as inputs - and it puts this part at 64/64 pins, full,
 * with 78 macrocells idle.  "broadcast" sends A4-A0 + REGWR instead and lets
 * each part decode its own offsets (partition.md §3), which costs each RECEIVER
 * a handful of cells it has spare and buys this part back the pins it does not.
 *
 * ⚠ The variant is priced, not adopted: adopting it rewires v3scan, v3ptr and
 * v3dot, and all three are fitted against the strobe convention today. */
const DECODE = (process.env.V3_DECODE ?? "strobes") as "strobes" | "broadcast"
const WR = (a: number) => `${REGSEL} & WRCYC & ` +
  [4, 3, 2, 1, 0].map((b) => `${(a >> b) & 1 ? "" : "!"}A${b}`).join(" & ")

const strobes: [string, number][] = [
  ["LDCTRL", 0x00], ["LDVSL", 0x01], ["LDVSH", 0x02], ["LDHSL", 0x03],
  ["LDHSH", 0x04], ["LDSPLEN", 0x05], ["LDWFG", 0x06], ["LDWBG", 0x07],
  ["LDWCOL", 0x08], ["LDWCOLH", 0x09], ["LDWROW", 0x0A], ["LDWADV", 0x0B],
  ["LDPIDXL", 0x0E], ["LDPIDXH", 0x0F], ["LDPDATL", 0x10], ["LDPDATH", 0x11],
  ["LDCCOL", 0x12], ["LDCCOLH", 0x13], ["LDCROW", 0x14], ["LDCW", 0x15],
  ["LDCH", 0x16], ["LDCCTRL", 0x17], ["LDTB", 0x18], ["LDMB", 0x19],
  ["LDSPRX", 0x1A], ["LDSPRY", 0x1B], ["LDSPRH", 0x1C], ["LDSPRIX", 0x1D],
  ["LDSPRDA", 0x1E],
]

/* -- the palette commit: graphics.md §13.1 response 3 ---------------------
 *
 * ⭐ A CPU's PDATH write POSTS the commit to the next HLOAD; in vertical
 * blanking it runs at once.  PBUSY is VSTAT b1 and the rule it leaves is one
 * bit: do not write +$0E..+$11 while it is set, because the pending entry IS
 * PIDX and the '573s.
 *
 * The turnaround is three dots (vpal_tb counted them), so PS0..PS3 walk it and
 * PALTURN is the window v3dot stands the pixel path off for. */
const palette: Cell[] = [
  reg("PPEND", [`${WR(0x11)} & !VBLANK`, "PPEND & !PS0"]),
  reg("PS0", ["PPEND & HLOAD", `${WR(0x11)} & VBLANK`, "PS0 & !PS1"]),
  reg("PS1", ["PS0", "PS1 & !PS2"]),
  reg("PS2", ["PS1", "PS2 & !PS3"]),
  reg("PS3", ["PS2"]),
  comb("PALTURN", ["PS0", "PS1", "PS2"]),
  comb("PBUSY", ["PPEND", "PS0", "PS1", "PS2", "PS3"]),
  comb("LUTWE", ["PS1"]),
  comb("PIDXCE", ["PS3"]),
]

/* -- the VRAM port, /WAIT and /IRQ ---------------------------------------
 *
 * graphics.md §11: VPORT is the window OR +$0C, and §7.4's rule is that ONLY
 * writes wait on a span - a read waits on the span AND on its own prefetch.
 * ⛔ The OE idiom spends the macrocell's one output-enable term, so the whole
 * assertion condition has to live in it: the pin drives low or floats. */
const port: Cell[] = [
  comb("VDSEL", [`${REGSEL} & !A4 & A3 & A2 & !A1 & !A0`]),
  comb("VPORT", [VRAMSEL, "VDSEL"]),
  comb("WSTBV", ["VPORT & !RW & E"]),
  comb("WSTB", [`${REGSEL} & WRCYC`]),
  reg("RDVALID", ["RDCK", "RDVALID & !RDINV"]),
  comb("RDINV", ["WSTB", "RETIRE", "RSTART"]),
  comb("RDOE", ["VPORT & RW"]),
  comb("RDREQ", ["!RDVALID"]),
  comb("WAITN", [], "VPORT & !IOPGH & E & SPANBUSY # VPORT & !IOPGH & E & RW & !RDVALID"),
  reg("IRQPEND", ["VBLRISE", "IRQPEND & !IRQACK"]),
  reg("VBLQ", ["VBLANK"]),
  comb("VBLRISE", ["VBLANK & !VBLQ"]),
  comb("IRQACK", [`${WR(0x0D)}`]),
  comb("IRQN", [], "IRQPEND & IRQEN"),
  /* VSTAT is read through a '244 (graphics.md §12.1): SPANBUSY, CBUSY and
   * PBUSY are live macrocells and the register file has no path to them. */
  comb("VSTATOE", [`${REGSEL} & !A4 & A3 & A2 & !A1 & A0 & RW & E`]),
  comb("RDBKOE", [`${REGSEL} & RW & E & !VDSEL`]),
]

export const v3host: Merged = {
  name: DECODE === "strobes" ? "v3host" : "v3host_bc",
  partNo: "ARM6309-V3H",
  location: "video3 - backplane, register decode, palette write path",
  device: "f1508ispplcc84",
  clock: "CLK25",
  inputs: [
    { name: "CLK25" }, { name: "RESET", activeLow: true },
    { name: "IOSEL" }, { name: "IOPGH" },
    ...[0, 1, 2, 3, 4, 5, 6].map((b) => ({ name: `A${b}` })),
    { name: "A19" }, { name: "A20" }, { name: "E" }, { name: "RW" },
    { name: "WRCYC" },
    /* status, for VSTAT and /WAIT */
    { name: "SPANBUSY" }, { name: "CBUSY" },
    /* the raster, from v3dot */
    { name: "VBLANK" }, { name: "HLOAD" },
    /* the read path's own signals */
    { name: "RDCK" }, { name: "RETIRE" }, { name: "RSTART" }, { name: "IRQEN" },
  ],
  cells: [
    ...(DECODE === "strobes"
      ? strobes.map(([n, a]) => comb(n, [WR(a)]))
      : /* the broadcast: the offset and one qualifier, decoded at each receiver */
        [comb("REGWR", [`${REGSEL} & WRCYC`]),
         ...[0, 1, 2, 3, 4].map((b) => comb(`RA${b}`, [`A${b}`]))]),
    ...palette,
    ...port,
  ],
  external: new Set([
    ...(DECODE === "strobes"
      ? strobes.map(([n]) => n)
      : ["REGWR", "RA0", "RA1", "RA2", "RA3", "RA4"]),
    "PALTURN", "PBUSY", "LUTWE", "PIDXCE",
    "WSTBV", "WSTB", "RDOE", "RDREQ", "WAITN", "IRQN", "VSTATOE", "RDBKOE",
    "VDSEL", "VPORT", "RDVALID",
  ]),
}

if (import.meta.main) {
  console.log(`v3host: ${v3host.cells.length} cells, ${v3host.inputs.length} declared inputs`)
  console.log(toCupl(v3host))
}
