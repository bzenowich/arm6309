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
import { REGS, hostTerm, type RegName } from "./regmap"

/* ⛔ `assertedLow` IS A PIN DECLARATION, AND NO SIMULATION CAN SEE IT.
 * verilog/emit.ts emits the asserted sense and ignores this flag entirely, so
 * a wrong one is a JEDEC that fails on the board and a bench that passes -
 * which is why `npm run check:pins` exists and why it found the two below.
 * These helpers used to hard-code `false`, so nothing on this part COULD be
 * declared active-low; `low` is the parameter that fixes that. */
const reg = (name: string, terms: string[], low = false): Cell =>
  ({ pin: 0, name, assertedLow: low, s0: 1 as const, registered: true, terms })
const comb = (name: string, terms: string[], oe?: string, low = false): Cell =>
  ({ pin: 0, name, assertedLow: low, s0: 1 as const, registered: false, terms, oe })

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
 * ⭐ "broadcast" IS THE BUILD since 2026-09-16.  It sends RA4..RA0 + REGWR and
 * each part decodes its own offsets from the shared table in `regmap.ts`.
 *
 * "strobes" is the variant it replaced, kept fitted because it is the evidence:
 * one load line per register put this part at 64/64 pins with 78 macrocells
 * idle.  ⛔ And it could not express a register wider than the bus at all - a
 * strobe per REGISTER cannot load WPTR's three bytes separately, which is how
 * `LDWCOL & D0` came to drive both WC0 and WC8 on v3ptr. */
const DECODE = (process.env.V3_DECODE ?? "broadcast") as "strobes" | "broadcast"

/* ⭐ V3_SEQ=split PUTS THE COPY ENGINE'S PHASE MACHINE HERE, and v3ptr.cpld.ts
 * is where the switch is documented. The short version: v3ptr does not fit
 * with both sequencers in it (plan §14 item 14), and this part is 27/128 with
 * 22 spare pins - "v3host is where the room is, by a wide margin".
 *
 * ⚠ THE SPLIT IS CHOSEN BY FAN-IN, NOT BY CONVENIENCE. CEOR and CHLAST
 * decode ten and nine bits of v3ptr's own width and height counters, so they
 * stay beside them; what crosses is the two decoded bits plus CBUSY - which
 * this part ALREADY takes, for VSTAT - and the five outputs that drive the
 * counters and the address mux back. Seven signals instead of nineteen. */
const SEQ = process.env.V3_SEQ ?? "split"
const COPYHOST = SEQ === "split"
/* the decode, off the backplane.  ⭐ The offsets live in regmap.ts and nowhere
 * else: three other parts decode the same table, and a private copy here is
 * exactly the drift this card cannot afford - a decode that disagrees with the
 * spec fits perfectly well and answers the wrong address. */
const WRQ = `${REGSEL} & WRCYC`
const WR = (r: RegName) => hostTerm(r, WRQ)

/* every offset, for the "strobes" variant */
const ALL_REGS = Object.keys(REGS) as RegName[]
/* the ones this part acts on ITSELF, whichever way the offsets travel */
const MINE: RegName[] = ["LDPDATH", "LDIRQACK"]

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
  reg("PPEND", ["LDPDATH & !VBLANK", "PPEND & !PS0"]),
  reg("PS0", ["PPEND & HLOAD", "LDPDATH & VBLANK", "PS0 & !PS1"]),
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
  /* ⭐ open-drain, §1.9's idiom: the value is a constant 0 and the condition
   * rides on the output enable. ACTIVE-LOW, like /WAIT on the slot - audio's
   * FIRQ and vctrl's WAIT are declared the same way. */
  comb("WAITN", [], "VPORT & !IOPGH & E & SPANBUSY # VPORT & !IOPGH & E & RW & !RDVALID", true),
  reg("IRQPEND", ["VBLRISE", "IRQPEND & !IRQACK"]),
  reg("VBLQ", ["VBLANK"]),
  comb("VBLRISE", ["VBLANK & !VBLQ"]),
  comb("IRQACK", ["LDIRQACK"]),
  comb("IRQN", [], "IRQPEND & IRQEN", true),      /* open-drain /IRQ, likewise */
  /* VSTAT is read through a '244 (graphics.md §12.1): SPANBUSY, CBUSY and
   * PBUSY are live macrocells and the register file has no path to them. */
  comb("VSTATOE", [`${REGSEL} & !A4 & A3 & A2 & !A1 & A0 & RW & E`]),
  comb("RDBKOE", [`${REGSEL} & RW & E & !VDSEL`]),
]

/* the copy engine's sequence: two accesses a byte, one spare access a slot,
 * so two SLOTS a byte - and the phase bit is all the state that needs. */
const copyHost: Cell[] = [
  comb("CTICK", ["GCPY & MUXSEL0"]),
  reg("CPH", ["CBUSY & CTICK & !CPH", "CBUSY & !CTICK & CPH"]),
  /* ⚠ qualified by CBUSY: this is the address mux's select, and an idle
   * engine must leave WPTR on the bus for the span writer and the CPU port. */
  comb("CRDSEL", ["CBUSY & !CPH"]),
  comb("CSTEP", ["CTICK & CPH"]),
  comb("CROWADV", ["CSTEP & CEOR"]),
  comb("CWLOAD", ["CROWADV"]),
  comb("CDONE", ["CROWADV & CHLAST"]),
  comb("RCPY", ["CBUSY"]),
]

export const v3host: Merged = {
  name: DECODE === "strobes" ? "v3host_st" : "v3host",
  partNo: "ARM6309-V3H",
  location: "video3 - backplane, register decode, palette write path",
  device: "f1508ispplcc84",
  clock: "CLK25",
  inputs: [
    { name: "CLK25" }, { name: "RESET", activeLow: true },
    /* ⛔ /IOSEL IS ACTIVE-LOW ON THE SLOT (signals.md §2.1), and the terms
     * above already use its ASSERTED sense - REGSEL is `IOSEL & A6 & A5` and
     * VRAMSEL is `!IOSEL & ...`, "not selected". Only the declaration was
     * wrong, and a wrong one is the exact defect check:pins was written for:
     * the video card's /IOSEL was one of the nine found on 2026-09-11. */
    { name: "IOSEL", activeLow: true }, { name: "IOPGH" },
    ...[0, 1, 2, 3, 4, 5, 6].map((b) => ({ name: `A${b}` })),
    { name: "A19" }, { name: "A20" }, { name: "E" }, { name: "RW" },
    { name: "WRCYC" },
    /* status, for VSTAT and /WAIT */
    { name: "SPANBUSY" }, { name: "CBUSY" },
    /* the raster, from v3dot */
    { name: "VBLANK" }, { name: "HLOAD" },
    /* the read path's own signals */
    { name: "RDCK" }, { name: "RETIRE" }, { name: "RSTART" }, { name: "IRQEN" },
    ...(COPYHOST ? [{ name: "CEOR" }, { name: "CHLAST" },
                    { name: "GCPY" }, { name: "MUXSEL0" }] : []),
  ],
  cells: [
    ...(DECODE === "strobes"
      ? ALL_REGS.map((r) => comb(r, [WR(r)]))
      : /* ⭐ the broadcast: the offset and one qualifier, decoded at each
         * receiver.  Six pins carry all 30 offsets - and, unlike a strobe per
         * register, it can carry an offset a receiver invents later. */
        [comb("REGWR", [WRQ]),
         ...[0, 1, 2, 3, 4].map((b) => comb(`RA${b}`, [`A${b}`]))]),
    /* the two this part acts on itself are decoded here either way */
    ...(DECODE === "strobes" ? [] : MINE.map((r) => comb(r, [WR(r)]))),
    ...palette,
    ...port,
    ...(COPYHOST ? copyHost : []),
  ],
  external: new Set([
    ...(DECODE === "strobes"
      ? ALL_REGS
      : ["REGWR", "RA0", "RA1", "RA2", "RA3", "RA4"]),
    "PALTURN", "PBUSY", "LUTWE", "PIDXCE",
    "WSTBV", "WSTB", "RDOE", "RDREQ", "WAITN", "IRQN", "VSTATOE", "RDBKOE",
    "VDSEL", "VPORT", "RDVALID",
    /* the copy engine's, when the phase machine lives here */
    ...(COPYHOST ? ["CRDSEL", "CSTEP", "CROWADV", "CWLOAD", "CDONE", "RCPY"] : []),
  ]),
}

if (import.meta.main) {
  console.log(`v3host: ${v3host.cells.length} cells, ${v3host.inputs.length} declared inputs`)
  console.log(toCupl(v3host))
}
