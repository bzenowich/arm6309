/* v3host - video3's backplane, register decode and palette write path.
 *
 * hardware/video3/docs/partition.md §2.4.  The pin-bound part: a fifth of its macrocells
 * and two thirds of its pins, because the backplane is 27 signals on its own
 * (signals.md §2.1) and it is where they land.  Merging it into any neighbour
 * overflows PINS, never cells - §7 has that arithmetic.
 *
 * ⭐ IT NEEDS NO INTERNAL DATA BUS.  Every register it touches is a discrete
 * latch or counter that loads from IDB itself - PIDX is two '163 and a '574,
 * PDATL/PDATH are two '573 - so this part only STROBES them.  Eight pins that
 * the census had it spending.
 */

import { toCupl, type Merged } from "../../tools/gal/jedec/cupl"
import type { Cell } from "../../tools/gal/jedec/assemble"
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
/* ⛔ AND NOT IN THE I/O PAGE. graphics.md §6.3.2: physical A19 keeps being
 * emitted during an I/O cycle, so A19 alone matches every I/O access in the
 * machine, and §6.3.2 requires the /IOPAGE term "on the posted-write capture
 * and not only on the read path". It used to sit on /WAIT instead - where it
 * also caught VDATA, an I/O-page register, so a VDATA write never waited for a
 * running span and its byte replaced the span's colour on IDB (v3card_tb). */
const VRAMSEL = "!IOSEL & !IOPGH & A19 & !A20"

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
const RELOAD = (process.env.V3_RELOAD ?? "on") === "on" && COPYHOST
/* the decode, off the backplane.  ⭐ The offsets live in regmap.ts and nowhere
 * else: three other parts decode the same table, and a private copy here is
 * exactly the drift this card cannot afford - a decode that disagrees with the
 * spec fits perfectly well and answers the wrong address. */
/* ⛔ THE CPU DOES NOT GET THE CARD WHILE THE CARD IS BUSY - IT IS HELD.
 * v3card_tb found the seam: /WAIT stretches E-high, and every strobe below is
 * an E-high level, so a HELD write still reached the card - the '245 put the
 * CPU's byte on IDB and the running span retired it as its colour, the mask
 * serialiser reloaded mid-span, and the register file's /WE fired at the
 * SPAN's address and overwrote WFG. The same is true of a copy and of §7.2's
 * reload walk, which reads +$08/+$09 out of the file. So every CPU strobe is
 * qualified by !BUSY, and /WAIT holds any card write - register or VRAM -
 * while BUSY, which it did not do for a copy at all (plan §6: "/WAIT holds a
 * CPU VRAM access while CBUSY exactly as it does while SPANBUSY"). ⚠ !BUSY
 * is the complement of an OR, so it is ONE product term - no intermediate
 * blows up the way access.jedec.ts warns. */
const BUSY = "!SPANBUSY & !CBUSY & !RP1 & !RP2 & !RP3 & !RP4"
const WRQ = `${REGSEL} & WRCYC & ${BUSY}`
const WR = (r: RegName) => hostTerm(r, WRQ)

/* every offset, for the "strobes" variant */
const ALL_REGS = Object.keys(REGS) as RegName[]
/* the ones this part acts on ITSELF, whichever way the offsets travel */
const MINE: RegName[] = ["LDPDATH", "LDIRQACK", "LDCTRL"]

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
  /* ⛔ THE COMMIT RUNS ON AN EDGE, NOT ON THE WRITE'S LEVEL. LDPDATH is the
   * broadcast decode of +$11, so it is asserted for the whole of E-high - six
   * dots and more under /WAIT - and PS0..PS3 is a four-dot walk. v3card_tb's
   * first run wrote entry 0's colour into entries 0, 1, 2 and 3: one PDATH
   * write ran the walk and advanced PIDX several times over. graphics.md §19
   * item 37 is the same defect on the other card's span writer. */
  reg("PDQ", ["LDPDATH"]),
  comb("PDGO", ["LDPDATH & !PDQ"]),
  /* ⛔ IT CLEARED ON PS0, WHICH IS ONE DOT TOO LATE. HLOAD is a LEVEL - four
   * slots, sixteen dots - and PS0 is `PPEND & HLOAD`, so the walk started
   * again on the next dot: PPEND only cleared on the edge AFTER PS0 set.
   * Every palette write outside vertical blanking landed TWICE and stepped
   * PIDX twice, so a 256-entry load through the auto-increment took 479
   * writes, wrapped, and overwrote the entries it had got right. ⭐ Clearing
   * on HLOAD itself makes the pulse one dot whatever the level's length.
   * ⚠ v3card_tb could not see it: its palette runs just after reset, where
   * VBLANK takes the other path - `PDGO & VBLANK`, already a one-dot pulse.
   * v3machine_tb, a 6809E executing a ROM with the display on, found it on
   * its first run. */
  reg("PPEND", ["PDGO & !VBLANK", "PPEND & !HLOAD"]),
  /* ⛔ A SHIFT REGISTER, ONE DOT A STAGE - as vsup.parts.ts has it. The port
   * to this part gave each stage a hold (`PS1 & !PS2` and so on), which
   * stretched every stage to two dots: PIDXCE (PS3) fired twice a commit and
   * v3card_tb found the palette landing at entries 0, 2 and 4. PS0 is one dot
   * already, because PPEND clears on it and PDGO is an edge. */
  reg("PS0", ["PPEND & HLOAD", "PDGO & VBLANK"]),
  reg("PS1", ["PS0"]),
  reg("PS2", ["PS1"]),
  reg("PS3", ["PS2"]),
  comb("PALTURN", ["PS0", "PS1", "PS2"]),
  comb("PBUSY", ["PPEND", "PS0", "PS1", "PS2", "PS3"]),
  comb("LUTWE", ["PS1"]),
  /* ⭐ OMR (the '273 pair's /MR, BLANK two registers late) is v3dot's: this
   * part needed the two pins it cost for PWCK and IRQPEND. */
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
  comb("WSTBV", [`VPORT & !RW & E & ${BUSY}`]),
  /* ⭐ THE SPAN STARTS ON THE E-FALL EDGE OF A POSTED VRAM WRITE, and on
   * nothing else. v3ptr started spans on WSTB - the REGISTER strobe - so every
   * register write started a span, and WSTB is a level over E-high, so every
   * one re-armed it: v3card_tb found WPTR moved 21 for eight VDATA writes, the
   * five set-up writes retiring stale bytes and each VDATA write retiring
   * twice. graphics.md §19 item 37 again, and video/'s answer again: the
   * level delayed a dot, and the one-dot edge made from it. ⚠ At that edge
   * the '245 has let go of IDB and the file is back at +$05, so SPANLEN is
   * what v3ptr's length counter loads - video/'s "the load needs no address of
   * its own". */
  reg("WPQ", ["WSTBV"]),
  comb("WSTART", ["WPQ & !WSTBV"]),
  comb("WSTB", [WRQ]),
  /* ⛔ THE PREFETCH'S CLOCK AND THE LATCH'S CLOCK ARE NOT THE SAME SIGNAL.
   * The vread '574 has one clock pin and two users now: §11's prefetch, and
   * the copy engine's READ access, which §6 says lands its byte in vread
   * (trade 1: no copy latch). Nothing clocked it for the copy. But RDVALID
   * must be set by the PREFETCH alone - a copy byte in the latch is a byte
   * from CPTR, not the one at WPTR, and marking it valid would hand the CPU
   * the wrong byte on its next VDATA read. So RDCKP is the prefetch's, RDCK
   * is the pin, and a copy step invalidates like any other WPTR move. */
  comb("RDCKP", ["GRD & !RDVALID"]),
  reg("RDVALID", ["RDCKP", "RDVALID & !RDINV"]),
  comb("RDINV", ["WSTB", "RETIRE", "RSTART", "CSTEP"]),
  /* -- ⭐ §11's READ PREFETCH AND THE REGISTER WRITE CYCLE, ported from
   * vsup.parts.ts. ⛔ All four were INPUTS that nothing produced, which meant
   * the card could not be written to (WRCYC qualifies every register write),
   * the CPU could not read VRAM (RDCK clocks the vread '574) and WPTR never
   * post-incremented after a read (RSTART). */
  /* ⚠ A 6809E WRITE IS ONLY VALID IN THE SECOND HALF OF E, which is the whole
   * of this: regfile.jedec.ts qualifies the register strobe the same way. */
  comb("WRCYC", ["!RW & E"]),
  /* §11's post-increment: the dot after a VRAM read's E falls. ⚠ NOT "the
   * copy has started" - an earlier note in reach.check.ts guessed that from
   * the name and vsup.parts.ts says otherwise. */
  reg("RPQ", ["VPORT & RW & E"]),
  comb("RSTART", ["RPQ & !E"]),
  /* ⭐ WSTEP IS WHAT v3ptr's WRITE COLUMN STEPS ON besides its own RETIRE: a
   * copy's write and a VDATA read's post-increment. Sent as one pin rather than
   * RSTART beside CSTEP, because every LAB on v3ptr sits at 38 of the fitter's
   * 40 inputs and a third term in WINC was the one that did not fit. */
  comb("WSTEP", ["CSTEP", "RSTART"]),
  /* ⚠ ACTIVE LOW, so the '574's RISING edge is the END of the granted access,
   * when the framebuffer has answered. GRD is the arbiter's grant for the
   * prefetch; video/ had `& !LRUN` here and video3 has no list engine. */
  comb("RDCK", ["RDCKP"], undefined, true),
  /* ⭐ THE POSTED-WRITE '574 IS THE COPY's LATCH TOO (plan §6, trade 1), and
   * this is its clock: a CPU write to the VRAM port, or the copy's read access
   * - the byte crosses IDB from its lane into the '574, and the copy's write
   * access drives it back out to the destination lane. ⛔ The copy read into
   * vread, and nothing moved it from vread to the framebuffer (GAP_6): vread
   * drives the backplane, not IDB. ACTIVE LOW for the same reason as RDCK. */
  comb("PWCK", ["WSTBV", "CTICK & !CPH"], undefined, true),
  comb("RDOE", ["VPORT & RW"]),
  /* ⭐ AND ONLY WHEN IDB IS FREE: a prefetch puts its lane on the card's
   * internal bus, which the CPU owns through E-high of any card access other
   * than the VDATA read that is waiting for it, the reload walk owns for its
   * four dots, and a span owns from the dot it starts - WSTART loads SPANLEN
   * off the file, and every retire takes WFG or WBG from it. ⛔ v3card_tb's
   * span-solid wrote ONE byte: a VDATA write invalidates the prefetch, the
   * prefetch runs in E-low, and E-low is where WSTART is - so a lane '245 had
   * IDB when SPANLEN was loaded. (A prefetch during a span is wasted anyway:
   * every retire moves WPTR.) E-low is six dots, so a free spare window
   * always comes. */
  comb("RDREQ", ["!RDVALID & !E & !WPQ & !SPANBUSY & !RP1 & !RP2 & !RP3 & !RP4",
                 "!RDVALID & E & RW & VPORT & !SPANBUSY & !RP1 & !RP2 & !RP3 & !RP4"]),
  /* ⭐ open-drain, §1.9's idiom: the value is a constant 0 and the condition
   * rides on the output enable. ACTIVE-LOW, like /WAIT on the slot - audio's
   * FIRQ and vctrl's WAIT are declared the same way. */
  comb("CARDBUSY", ["SPANBUSY", "CBUSY", "RP1", "RP2", "RP3", "RP4"]),
  comb("WAITN", [], `VPORT & E & CARDBUSY # ${REGSEL} & !RW & E & CARDBUSY # VPORT & E & RW & !RDVALID`, true),
  reg("IRQPEND", ["VBLRISE", "IRQPEND & !IRQACK"]),
  reg("VBLQ", ["VBLANK"]),
  comb("VBLRISE", ["VBLANK & !VBLQ"]),
  comb("IRQACK", ["LDIRQACK"]),
  /* ⛔ CTRL b6, AND IT WAS AN INPUT NOTHING PRODUCED - so the VBL interrupt
   * could never be enabled. ⚠ It costs this part its FIRST data-bus pin, and
   * the header's "IT NEEDS NO INTERNAL DATA BUS" is now one bit less true:
   * every other register it touches is a discrete latch that loads from IDB
   * itself, and this one is a macrocell here because /IRQ is. ⭐ v3ptr has the
   * whole bus and decodes WMODE the same way, and it was tried there first -
   * the fitter refused it at 125/128. */
  reg("IRQEN", ["LDCTRL & D6", "IRQEN & !LDCTRL"]),
  comb("IRQN", [], "IRQPEND & IRQEN", true),      /* open-drain /IRQ, likewise */
  /* VSTAT is read through a '244 (graphics.md §12.1): SPANBUSY, CBUSY and
   * PBUSY are live macrocells and the register file has no path to them. */
  comb("VSTATOE", [`${REGSEL} & !A4 & A3 & A2 & !A1 & A0 & RW & E`]),
  /* ⛔ NOT +$0D EITHER. RDBKOE excluded VDATA and not VSTAT, so every VSTAT
   * poll put the read-back '245 and the VSTAT '244 on D7..D0 together - 30
   * dots of fight in v3card_tb's first run. +$0C and +$0D are 0110x, so the
   * exclusion is one term per literal of A4..A1 and no intermediate. */
  /* ⭐ AND INBOUND: the same '245 carries a card write onto IDB (DIR is R/W),
   * so its enable is the qualified write strobes as well - a write /WAIT is
   * holding does not reach IDB, where a span's colour may be. */
  comb("RDBKOE", [...["A4", "!A3", "!A2", "A1"].map((l) => `${REGSEL} & RW & E & ${l}`),
                  "WSTB", "WSTBV"]),
]

/* the copy engine's sequence: two accesses a byte, one spare access a slot,
 * so two SLOTS a byte - and the phase bit is all the state that needs. */
const copyHost: Cell[] = [
  comb("CTICK", ["GCPY & DP0"]),
  reg("CPH", ["CBUSY & CTICK & !CPH", "CBUSY & !CTICK & CPH"]),
  /* ⚠ qualified by CBUSY: this is the address mux's select, and an idle
   * engine must leave WPTR on the bus for the span writer and the CPU port. */
  comb("CRDSEL", ["CBUSY & !CPH"]),
  /* ⭐ THE LANE '245s' DIRECTION: IDB -> lane for a write access, lane -> IDB
   * for the two reads (the prefetch and the copy's read). Held for the whole
   * access, not the write tick: the '245 has to have turned before /WE, and a
   * read-direction dot inside a write would put the SRAM's own output on IDB
   * against whatever is driving it. */
  comb("DIR", ["!GRD & !CRDSEL"]),
  comb("CSTEP", ["CTICK & CPH"]),
  comb("CROWADV", ["CSTEP & CEOR"]),
  /* ⭐ AND WHILE IDLE: the width counter is loaded at the end of every row
   * and for as long as no copy runs, so the first row starts from CWIDTH too.
   * The load wins over the count, and CBUSY is what lets the count go. */
  comb("CWLOAD", ["CROWADV", "!CBUSY"]),
  comb("CDONE", ["CROWADV & CHLAST"]),
  /* ⭐ THE COPY's REQUEST, AND IT WAITS FOR THE RELOAD WALK. A row's last
   * write starts the walk (CROWADV), and the walk's last two dots are the next
   * slot's spare window - where the copy's next read would put a lane on IDB
   * while v3ptr loads CPTR's column from the register file across the same
   * bus. One slot a row. */
  comb("RCPY", ["CBUSY & !RP1 & !RP2 & !RP3 & !RP4"]),
]

/* -- ⭐ §7.2's COLUMN-RELOAD WALK, AND THE REGISTER FILE'S ADDRESS --------
 *
 * ⛔ NOTHING ON THIS CARD PRODUCED RFA, AND §7.2's RELOAD COULD NOT BE
 * FINISHED WITHOUT IT. The file holds the readback bytes, WFG/WBG, SPANLEN,
 * the sprite shape and the two column shadows, and its address had no
 * generator at all. `video/`'s rfa is the same block and this is a port, with
 * three differences:
 *
 *   - ⭐ THE CPU'S OFFSET IS ALREADY HERE. rfa recomputed REGSEL from IOSEL,
 *     A6 and A5 "because importing it would cost a pin"; this part IS the
 *     register decode, so REGSEL and A0-A4 are its own already.
 *   - ⚠ FOUR RELOAD STATES, NOT TWO. video/ restores WPTR's column alone;
 *     the copy engine has to restore CPTR's as well, so the walk is +$08,
 *     +$09, +$12, +$13 and RFA4 stops being constant.
 *   - ⛔ RFA0 IS NOT HERE. §5 makes the file's address bit 0 the MASK BIT and
 *     the serialiser is on v3ptr, so that one bit is v3ptr's; RFA4..RFA1 are
 *     an ordinary address. The walk is here because v3ptr does not fit with
 *     it - refused under two names at 124/128.
 *
 * ⭐ ONE-HOT, SO THE STATES ARE THE STROBES. A four-dot walk that also needs
 * four load strobes is five cells this way and nine as a counter plus decodes,
 * and the counter has nothing else to say. v3ptr's column counters take RP1
 * and RP2 (WPTR) and RP3 and RP4 (CPTR) as load sources directly.
 *
 * ⚠ AND THE ADDRESS LEADS THE LOAD BY A DOT: RFA changes on the edge that
 * ENTERS a state and v3ptr loads on the edge that LEAVES it, so the 20 ns
 * register file and this decode have a whole 39.7 ns dot to settle in. */
const reloadWalk: Cell[] = [
  /* ⚠ remembered, because CROWADV is one dot and the walk is four */
  reg("CRLD", ["CROWADV", "CRLD & !RP4"]),
  reg("RP1", ["!RP1 & !RP2 & !RP3 & !RP4 & WROWADV"]),
  reg("RP2", ["RP1"]),
  reg("RP3", ["RP2 & CRLD"]),
  reg("RP4", ["RP3"]),
]

/* ⛔ THE CPU DOES NOT GET THE FILE WHILE A SPAN RUNS, and rfa records what
 * that cost: §5's colour path IS the file's address, so an access during a
 * span retired whatever byte the CPU's own address named - three pixels a
 * poll, and machine_tb drew every span with a hole in it (graphics.md 19
 * item 38). The span's claim wins, and `!SPANBUSY` is the whole fix.
 *
 *   idle    +$05  00101   SPANLEN, so span-solid's load needs no address
 *   span    +$06  0011x   WFG / WBG, bit 0 the mask bit (on v3ptr)
 *   RP1     +$08  01000   RP2  +$09  01001
 *   RP3     +$12  10010   RP4  +$13  10011 */
const rf: Cell[] = (() => {
  const IDLE = "!RP1 & !RP2 & !RP3 & !RP4"
  /* ⚠ THE CPU OWNS THE FILE IN E-HIGH ONLY. Without E, a register access's
   * address - held a moment past E's fall - kept the file off +$05 on exactly
   * the dot the span writer loads SPANLEN from it. */
  const CPU = `${REGSEL} & E & !SPANBUSY & ${IDLE}`
  const SPAN = `SPANBUSY & ${IDLE}`
  /* not the CPU, not a span, not a reload: +$05. One term per literal of the
   * CPU's claim, because !CPU would be an intermediate (access.jedec.ts) */
  const REST = ["!IOSEL", "!A6", "!A5", "!E"].map((l) => `${l} & !SPANBUSY & ${IDLE}`)
  const extra: Record<number, string[]> = {
    1: [SPAN, "RP3", "RP4"],
    2: [...REST, SPAN],
    3: ["RP1", "RP2"],
    4: ["RP3", "RP4"],
  }
  return [1, 2, 3, 4].map((n) =>
    comb(`RFA${n}`, [`${CPU} & A${n}`, ...extra[n]]))
})()
/* ⭐ and the same claim for v3ptr's RFA0, which could only see REGWR - a
 * WRITE - so every register READ took bit 0 from the idle term and returned
 * the odd register beside the one asked for. */
const cpurf = comb("CPURF", [`${REGSEL} & E & !SPANBUSY & !RP1 & !RP2 & !RP3 & !RP4`])

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
    /* ⛔ WRCYC is a CELL now, not an input - see the read-prefetch block */
    /* status, for VSTAT and /WAIT */
    { name: "SPANBUSY" }, { name: "CBUSY" },
    /* the raster, from v3dot */
    { name: "VBLANK" }, { name: "HLOAD" },
    /* the read path's own signals */
    { name: "RETIRE" }, { name: "GRD" }, { name: "D6" },
    ...(COPYHOST ? [{ name: "CEOR" }, { name: "CHLAST" },
                    { name: "GCPY" }, { name: "DP0" }] : []),
    ...(RELOAD ? [{ name: "WROWADV" }] : []),
  ],
  /* ⭐ the pins whose consumer is active-low (check:pins); the equations stay
   * in asserted sense */
  cells: ([
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
    ...(RELOAD ? [...reloadWalk, ...rf, cpurf] : []),
  ] as Cell[]).map((c) => (["WSTB", "RDBKOE", "VSTATOE", "RDOE", "LUTWE"].includes(c.name)
    ? { ...c, assertedLow: true } : c)),
  external: new Set([
    ...(DECODE === "strobes"
      ? ALL_REGS
      : ["REGWR", "RA0", "RA1", "RA2", "RA3", "RA4"]),
    "PALTURN", "PBUSY", "LUTWE", "PIDXCE",
    "WSTBV", "WSTB", "RDOE", "RDREQ", "WAITN", "IRQN", "VSTATOE", "RDBKOE",
    /* ⚠ VDSEL, VPORT, RDVALID and WRCYC used to leave here too, and the pin
     * map showed nothing on the board read any of them - four pins on the
     * card's pin wall, which is what WSTART and CPURF are paid for with. */
    "WSTEP", "RDCK", "WSTART",
    /* ⭐ the posted-write '574's clock (v3lane's GAP_6), and VSTAT b0 */
    "PWCK", "IRQPEND",
    ...(RELOAD ? ["CPURF"] : []),
    /* the copy engine's, when the phase machine lives here */
    ...(COPYHOST ? ["CRDSEL", "CSTEP", "CROWADV", "CWLOAD", "CDONE", "RCPY", "DIR"] : []),
    ...(RELOAD ? ["RP1", "RP2", "RP3", "RP4", "RFA1", "RFA2", "RFA3", "RFA4"] : []),
  ]),
}

if (import.meta.main) {
  console.log(`v3host: ${v3host.cells.length} cells, ${v3host.inputs.length} declared inputs`)
  console.log(toCupl(v3host))
}
