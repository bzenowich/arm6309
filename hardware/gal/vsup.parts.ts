/* The blocks that exist only because the video card gained a THIRD
 * ATF1508AS - graphics.md 10.1.7 - plus the one block graphics.md has put in
 * v1 since 9 and nobody had written.
 *
 * ⛔ THE PALETTE HAD NO WRITE PATH AT ALL. 9 specifies a 256 x 16 b LUT and 13
 * gives it three registers - +$10 PIDX, +$11 PDATL, +$12 PDATH - and 14's
 * parts list carries the '593 index counter and the LUT SRAM. What no design
 * file contained was anything that LOADS the counter, DRIVES the LUT's address
 * during a write, or asserts its /WE: census.ts booked them as one line item,
 *
 *     ["'165 load, '161 load, PIDX '593 load and count", 4]
 *
 * with no cell behind it - the same class of defect design-review2.md 1.2
 * found eleven of, and the same one the '165 and the '161 pair were. So the
 * CPU could not write the palette, which on a card whose only colour path is
 * the LUT means it could not put a colour on the screen at all. 9's boot
 * identity palette was unreachable.
 *
 * It is fitted here rather than on vaddr or vctrl for the reason every other
 * block ends up where it does: pins. The write path costs THIRTEEN - eight for
 * the LUT's address, five for the strobes and enables - and vctrl is at 64 of
 * 64 while vaddr is at 63 of 64.
 */

import type { Cell } from "./jedec/assemble"
import { isReg, isRegOn, REGS } from "./regfile"

const comb = (name: string, terms: string[], why?: string): Cell =>
  ({ pin: 0, name, assertedLow: false, s0: 1, registered: false, terms, why })

const reg = (name: string, terms: string[], why?: string): Cell =>
  ({ pin: 0, name, assertedLow: false, s0: 1, registered: true, terms, why })

/** A pin whose ASSERTED sense is the useful one and whose silicon is active
 *  low - an SRAM /WE, a '573 /OE. assertedLow inverts at the pin only, which
 *  is the convention assemble.ts and emit.ts both use. */
const lowPin = (name: string, terms: string[], why?: string): Cell =>
  ({ pin: 0, name, assertedLow: true, s0: 1, registered: false, terms, why })

/* ---- the register writes this part decodes for itself -------------------
 *
 * rfa's WSTB and RA4..RA0 are on this die now, so a strobe is a product term
 * rather than a pin. 10.1.6.3's trade - "six address lines and a write strobe
 * replace nine of them" - runs the other way inside one package: the address
 * lines are already here, so each strobe is free.
 */
export const vsupStrobes: Cell[] = [
  /* 8.2's CPU write port, for the HSCROLL[1:0] copy pxsel holds. vaddr decodes
   * the same offset for vctrl's copy; two decodes of one address is cheaper
   * than the pin that would carry one of them. */
  comb("LDHS", [`WSTB & ${isReg(REGS.HSCROLL)}`]),
  /* ⛔ 13's +$14, AND vctrl'S WADV1:0 HAD NO DRIVER ON SILICON UNTIL 2026-09-11.
   * vaddr decoded it and kept it: a buried combinational cell, substituted and
   * pinned nowhere, while vctrl declared an input pin for it (cpld/vctrl.fit
   * pin 9). The same for LDHS, pin 51, which both vaddr and this part computed
   * and neither exported. emit.ts makes every cell a Verilog port, so the board
   * file wired the net and every simulation was green. check:reach now asserts
   * that an input another part computes is an output of that part.
   * ⭐ HERE AND NOT ON vaddr, because this part has the pins and vaddr has none
   * to spare - and vaddr's copy of LDADV had no other reader, so it is gone. */
  comb("LDADV", [`WSTB & ${isReg(REGS.WADV)}`], "13's +$14 - 7.2's next-row-same-column mode, to vctrl"),
  comb("WSPL", [`WSTB & ${isReg(REGS.SPANLEN)}`],
    "13's +$05 - and it had no strobe, because SPANLEN was only ever read"),
  comb("WPIDX", [`WSTB & ${isReg(REGS.PIDX)}`], "13's +$10"),
  comb("WPDL", [`WSTB & ${isReg(REGS.PDATL)}`], "13's +$11"),
  comb("WPDH", [`WSTB & ${isReg(REGS.PDATH)}`], "13's +$12 - the commit"),
]

/* ---- 13's +$05, and the eight pins that stop being pins ------------------
 *
 * ⭐ SPANLEN MOVES OUT OF THE REGISTER FILE, 2026-09-09. vlen.jedec.ts's whole
 * argument for being a package was this:
 *
 *   "it cannot go inside either CPLD, for one reason: 7.4 loads it from the
 *    REGISTER FILE, not from the CPU bus ... Loading it means eight pins on
 *    the register file's read bus, and vctrl is at 64 of 64 I/O while vaddr is
 *    at 61 of 64 with three. Eight pins is the whole story."
 *
 * The reason 7.4 puts it in the file is PERSISTENCE - "a span-solid is issued
 * as WPTR x3 + the posted write with SPANLEN written once, so the length has
 * to persist somewhere across spans" - and eight macrocells persist exactly as
 * well as eight SRAM cells. The file's byte at +$05 is still written by the
 * CPU and still reads back; nothing reads it any more.
 *
 * ⚠ AND IT REMOVES A COLLISION rather than only pins. vlen loaded at WSTBV, a
 * posted VRAM write, from whatever rfa had the file pointed at - which is why
 * rfa carries an IDLE state holding the address at $05, and why the load
 * carries !SPANBUSY (vlen.jedec.ts: "without this literal the counter would
 * reload from the colour byte on every later edge of the same strobe"). With
 * the length held here the load reads a register that is never anything else.
 */
export const spanLength: Cell[] = [0, 1, 2, 3, 4, 5, 6, 7].map((b) =>
  reg(`SL${b}`, [`WSPL & D${b}`, `SL${b} & !WSPL`]))

/* ---- 10.3.2's descriptor decode, and 10.3.1's GO ------------------------ *
 *
 * ⭐ THE WHOLE DESCRIPTOR HALF OF THE ENGINE LIVES HERE - moved off vaddr on
 * 2026-09-09, and both reasons are worth stating.
 *
 * ⛔ vaddr WILL NOT TAKE ANOTHER LITERAL. It fits at 124 of 128 cells and 160
 * of 128 nodes, with LAB FAN-IN AT 40 OF 40 IN EVERY BLOCK - the ATF1508AS
 * switch matrix's limit, not a capacity one. Three one-literal changes to the
 * engine were tried that afternoon: two returned "Grouping fail / Design does
 * not fit" and the third returned "INTERNAL ERROR". Fan-in is the third thing
 * this family runs out of, after cells and pins, and the .fit is the only
 * place it is visible.
 *
 * ⭐ AND ONE DECODE BEATS TWO. For an afternoon this part carried a SECOND
 * copy of the latch - vaddr's fed from the pixel bus, this one from the card's
 * internal data bus - on the argument that they could not diverge. vpal_tb
 * showed that they could, in the one case 10.3.1's rule cannot forbid: BCTRL's
 * own GO write. One home for the decode, one net for the byte, and the
 * question does not arise.
 *
 * What still crosses to vaddr is three signals and no state: LADV for WPTR's
 * increment, LWHSL and LWHSH for 8's scroll holds.
 */
export const listDecode: Cell[] = [
  /* ⭐ LRUN RISES WHEN THE GO WRITE ENDS, NOT WHEN IT STARTS - and vpal_tb is
   * what found it.
   *
   * ⛔ IT READ `BCTRLGO # LRUN & !LSTOP`, so the engine started on the FIRST
   * dot inside E-high of the write to +$0E. E is high for six dots at 2.1 MHz
   * and a spare access is granted every four, so the engine took its first
   * grant WHILE THE CPU WAS STILL DRIVING THE CARD'S INTERNAL DATA BUS - and
   * 10.3.3's '244, which is how a descriptor byte gets onto that bus, stands
   * off for exactly that reason. Simulated: the list's first opcode was the
   * CPU's own $01.
   *
   * ⚠ AND 10.3.1'S RULE CANNOT COVER IT. "Do not write card registers while
   * LRUN is set" forbids every other collision on that bus; it cannot forbid
   * the write that turns the engine on. So the start is deferred: LGO latches
   * the GO, holds while the write is in flight, and hands over on the dot WSTB
   * falls. One macrocell, and the engine never sees a dot in which the CPU
   * owns the bus it fetches through. */
  comb("BCTRLGO", [`WSTB & ${isReg(REGS.BCTRL)} & D0`],
    "10.3.1's GO - a strobe, because LRUN is what holds"),
  reg("LGO", ["BCTRLGO", "LGO & WSTB"],
    "the GO, held until the write cycle that issued it has ended"),
  reg("LRUN", ["LGO & !WSTB", "LRUN & !LSTOP"], "13's +$0F, BSTAT b0"),
  comb("LSTOP", ["LRUN & LD7 & LD4 & LD3 & LD2 & LD1 & LD0"],
    "END is any b7 byte with b4..b0 set - canonically $FF"),

  /* ⭐ vctrl grants the spare access to "whoever is not the span writer" as
   * SGRANT since 2026-09-11, so the list engine's share is formed here, where
   * LRUN is - and 11's read prefetch takes the rest (vramRead, below). */
  comb("LGRANT", ["LRUN & SGRANT"], "10.3's grant: the spare access, while the engine runs"),
  comb("LADV", ["LRUN & LGRANT & !LWAIT"],
    "10.3.2's consumption cycle - WPTR's increment, through VINC"),
  /* Expressed through LADV rather than repeating its three literals: the same
   * function, and it is what let the decode fit beside everything else. */
  comb("LFETCH", ["LADV & !LPH"]),
  comb("LMOVE", ["LADV & LPH"]),

  /* 0 = the next byte fetched is an opcode, 1 = it is MOVE's operand. Set by
   * fetching an opcode with b7 clear - D7 and not LD7, because LD is loading
   * on that same edge - and cleared when the operand is consumed.
   *
   * ⛔ AND BY LGO, WHICH IS THE SECOND HALF OF A DEFECT vspan_tb FOUND on
   * 2026-09-09: A LIST COULD NOT BE STARTED TWICE. LD holds the last byte
   * fetched, so after a list terminates it holds the terminator - and LSTOP is
   * a function of LD and LRUN alone, so the instant LRUN rose again LSTOP was
   * already true and the engine stopped on the same dot. Simulated: the second
   * list of a run walked WPTR zero bytes.
   *
   * ⚠ IT WAS ALWAYS BROKEN AND THE OLD EQUATION HID IT. LRUN used to be set by
   * BCTRLGO, a LEVEL over the whole of E-high - six dots at 2.1 MHz - so LRUN
   * was re-asserted every dot until a grant happened to land inside the write
   * and overwrite LD with a real opcode. Whether a second list ran at all
   * depended on where the grant fell in E. Deferring the start to one dot
   * (LGO above) turned a coincidence into a failure, which is the useful
   * direction for a defect to move.
   *
   * The repair is one literal on seven registers: the GO write clears the
   * descriptor state, so every list starts from opcode phase with no
   * terminator in the latch. */
  reg("LPH", ["LFETCH & !D7", "LPH & !LMOVE & !LGO"]),
  /* ⛔ HLOAD IS A LEVEL, AND UNTIL 2026-09-10 LWAIT WAS CLEARED BY IT. HLOAD
   * runs from count 0 to the slot before MFETCH opens - thirty-three fetch
   * slots of sync and back porch - and the engine is granted a dot in each of
   * them, so every WAIT reached inside that window cleared on the dot it was
   * set and the next descriptor came straight after it. A run of WAITs, which
   * is the ONLY way 10.3.2 offers to wait n lines, therefore collapsed to one
   * WAIT per SLOT. machine_tb measured twenty-seven descriptors consumed in a
   * single HLOAD window; boot.asm's 180-WAIT raster bar ran start to finish in
   * three scanlines of vertical blank and never reached the display.
   *
   * LREL is the repair and it is one register: armed whenever HLOAD is low -
   * that is, through the whole displayed part of a line - and disarmed by the
   * first LADV after HLOAD rises. So the window releases the engine exactly
   * once, and the WAIT fetched on the way out holds until the next line.
   * ⚠ Disarming on LADV rather than on a dot counter is what makes it robust:
   * LGRANT is one dot per slot and can be withheld by a span, so the release
   * has to be held until the engine actually takes it, not for a fixed time. */
  reg("LREL", ["!HLOAD", "LREL & !LADV"],
    "one release per line, held until the engine takes it"),
  /* Stalled between lines. HLOAD is the start of a line, which is what loads
   * the scan column counter from HSCROLL - the very register a list writes.
   * !LSTOP is what stops a $FF from leaving this set after LRUN falls.
   * ⚠ EVERY line, blanked ones included: HLOAD is a horizontal decode with no
   * vertical term, so 10.3.2's WAIT counts scanlines and not displayed lines,
   * and a list started at the top of vertical blank spends its first WAITs
   * there. graphics.md 10.3.2 says so; boot.asm starts at blank's end. */
  reg("LWAIT", ["LFETCH & D7 & !LSTOP",
                "LWAIT & !HLOAD & LRUN & !LSTOP",
                "LWAIT & !LREL & LRUN & !LSTOP"]),
  /* The opcode byte. b6 and b5 are reserved, so they are not latched, and the
   * GO write clears what is left of the previous list - see LPH. */
  ...[0, 1, 2, 3, 4, 7].map((b) =>
    reg(`LD${b}`, [`LFETCH & D${b}`, `LD${b} & !LFETCH & !LGO`])),

  /* ---- 10.3.3: the descriptor's path onto the internal data bus ---------
   *
   * The fetched byte is on the PIXEL bus, where the spare access puts it, and
   * every register with a list port is loaded from the card's INTERNAL DATA
   * BUS - which is the path the CPU already writes through, so a MOVE costs no
   * second load path anywhere. One '244 bridges the two for the dot a granted
   * engine slot lasts, and this part drives both halves of the turnaround.
   *
   * ⚠ THE CPU'S WRITE WINS, IN HARDWARE, AND 10.3.1's RULE IS WHAT MAKES THAT
   * SAFE. The '244 and 3.2's '245 are both hard drivers on this bus, so !WSTB
   * stands the buffer off rather than letting them fight: a CPU register write
   * in the same dot as a granted engine slot costs the list a descriptor byte,
   * which is a rule violation with a consequence rather than a bus
   * contention. LGO above is why the GO write itself is not such a case. */
  comb("LBYTE", ["LADV & !WSTB"]),
  lowPin("LDBOE", ["LBYTE"], "10.3.3's '244 /OE - the descriptor byte owns the bus"),
  /* The register file's /OE, which census.ts has listed as a produced signal
   * since the beginning and which nothing produced. It is what stops the file
   * fighting the '244; the file is not read during a list cycle, because a
   * list and a span cannot run at once (10.3.1). */
  { pin: 0, name: "RFOE", assertedLow: true, s0: 1, registered: false,
    why: "the register file drives, except while 10.3.3's buffer does",
    terms: ["!LADV", "WSTB"] },

  /* 13's offsets, decoded from the latched opcode. Four cells rather than four
   * inline products, because the hold term of every target register is
   * `!strobe` and the complement of a six-literal product is six terms.
   *
   * ⭐ THE PALETTE IS THE HALF THAT IS NEW. HSCROLL and HSCROLLH were reachable
   * before because they are held on the part that decoded the descriptor;
   * +$10-$12 are reachable now for exactly the same reason, and that is what
   * makes 12.3's per-scanline palette a thing the card does rather than a
   * thing 10.3 hopes for. */
  comb("LWHSL", [`LMOVE & ${isRegOn("LD", REGS.HSCROLL)}`]),   /* +$03 */
  comb("LWHSH", [`LMOVE & ${isRegOn("LD", REGS.HSCROLLH)}`]),  /* +$04 */
  comb("LWPI", [`LMOVE & ${isRegOn("LD", REGS.PIDX)}`]),       /* +$10 */
  comb("LWPDL", [`LMOVE & ${isRegOn("LD", REGS.PDATL)}`]),     /* +$11 */
  comb("LWPDH", [`LMOVE & ${isRegOn("LD", REGS.PDATH)}`]),     /* +$12 */
]

/* ---- 9's palette write path -------------------------------------------- *
 *
 * ⛔ THE '593 IS NOT BUILDABLE AND THE PART IS NOT THE POINT. 19 item 9 has
 * carried "74HC593 availability - confirm it" since minimal256.md 6.1 flagged
 * it as the thin part of the BOM. The answer came back on 2026-09-09: the
 * device is DISCONTINUED and there is no widely available pin-compatible
 * replacement. So the item closes, and it closes as a design decision rather
 * than a sourcing worry.
 *
 * ** WHAT REPLACES IT, AND WHY IT IS BETTER THAN A SUBSTITUTE. A '593 is a
 * loadable 8-bit counter whose eight pins are ONE shared bidirectional port -
 * the counter's outputs and its load inputs are the same wires. That is the
 * unusual thing about it, and it is the thing worth not reproducing: it forces
 * the CPU's index byte to reach the LUT's ADDRESS bus before it can be latched
 * at all, which is a second turnaround on a bus 13.1 already calls
 * unarbitrated. Two 74AHCT163A synchronous loadable counters have ORDINARY
 * parallel inputs and ORDINARY outputs, so:
 *
 *   load    P3..P0 of each '163 sit on the card's internal data bus, and
 *           /LOAD is PILD. The CPU's write and a list MOVE use the one path
 *           every other register on the card uses. No bus turnaround at all.
 *   drive   the eight Q outputs go through one '244 onto the LUT's address
 *           bus, /OE = PDOE.
 *
 * ⭐ SO 13.1's RULE GETS SMALLER, AND IT IS NOT RETIRED. The LUT has one
 * address bus and two masters that both want it - the pixel-index '574 every
 * dot, and the index counter while a write is in flight - so the tri-state
 * turnaround is structural and the snow is real. What goes away is the SECOND
 * turnaround: writing +$10 no longer touches the LUT's address bus, because
 * the counters load from the data bus. Snow costs three dots per COMMITTED
 * ENTRY now, and nothing per index write.
 *
 * ⚠ IT IS THREE PACKAGES WHERE THE PARTS LIST HAD ONE, and 14 says so: 2 x
 * '163 and 1 x '244 against the '593's single DIP-20. Against putting PIDX in
 * this part's macrocells - eight registers and a product-term output enable,
 * which fitted at 66 of 128 cells and 61 of 64 I/O - it is three packages
 * against eight I/O pins. The pins were chosen deliberately: on this card
 * every block that could not be built was short of PINS and never of
 * macrocells, so blitter room is a pin question.
 *
 * ** THE COMMIT IS FOUR DOTS AND IT RUNS AFTER THE WRITE CYCLE, not inside it.
 * 13's PDATL and PDATH are 74HC573 transparent latches on the card's internal
 * data bus, so each closes on the TRAILING edge of its own strobe - which is
 * the only edge at which a 6809E write's data is guaranteed (3.1). The LUT
 * write cannot begin until that edge has passed, and this is what waits:
 *
 *   PS0    the commit strobe, one dot late
 *   PS1    the '244 and the '573 pair take the LUT's two buses
 *   PS2    the LUT's /WE, 39.7 ns with address and data already settled
 *   PS3    data held past /WE's rising edge, then PIDX increments
 */
export const paletteWrite: Cell[] = [
  /* The two write ports, CPU and list, exactly as 8.2's scroll pair has. */
  comb("PLOAD", ["WPIDX", "LWPI"], "13's +$10, from either port"),
  comb("PDHW", ["WPDH", "LWPDH"], "13's +$12, the commit, from either port"),

  reg("PS0", ["PDHW"]),
  reg("PS1", ["PS0 & !PDHW"]),
  reg("PS2", ["PS1"]),
  reg("PS3", ["PS2"]),

  /* The two 74HC573 latch enables. Active HIGH and level, which is why they
   * are the strobes themselves: a '573 closes when LE falls. */
  comb("LDPDL", ["WPDL", "LWPDL"], "13's +$11, PDATL's '573 LE"),
  comb("LDPDH", ["PDHW"], "13's +$12, PDATH's '573 LE"),

  /* The counter pair's two controls. A '163 loads synchronously on the clock
   * edge while /LOAD is asserted and counts while ENT & ENP are, so both are
   * levels on the dot clock and neither needs an edge of its own. */
  { pin: 0, name: "PILD", assertedLow: true, s0: 1, registered: false,
    why: "the '163 pair's /LOAD - from the card's internal data bus, no turnaround",
    terms: ["PLOAD"] },
  comb("PINC", ["PS3"], "13: PIDX auto-increments after PDATH"),

  /* Who owns the LUT's two buses. PDOE is the window in which the index
   * '244 drives the address pins and the '573 pair drives the data pins -
   * they turn together, so one pin does both. */
  lowPin("PDOE", ["PS1", "PS2", "PS3"],
    "the index '244 drives the LUT's address and the '573 pair its data"),
  /* ⭐ ONE PIN FOR BOTH SIDES OF 13.1's TURNAROUND. The pixel-index '574's /OE
   * and the LUT's own /OE are the same condition - the picture owns both buses
   * or the write does - so they share a net and the pair can never be half
   * turned. */
  { pin: 0, name: "PIXOE", assertedLow: true, s0: 1, registered: false,
    why: "the pixel-index '574 drives the LUT's address AND the LUT drives its data",
    terms: ["!PDOE"] },
  lowPin("PWE", ["PS2"], "the LUT's /WE - one dot, inside PDOE at both ends"),
]

/* ---- graphics.md 11: readable VRAM, at WPTR, prefetched ------------------
 *
 * ⭐ A READ IS A WRITE RUN BACKWARDS. Every CPU VRAM write retires at WPTR and
 * post-increments; the physical address a store carries selects the VRAM
 * window and nothing else (3.1.1's address capture is in no design). So a CPU
 * read of the window returns the byte at WPTR and post-increments too, and the
 * software that walks a write with X+ walks a read the same way.
 *
 * The byte comes from 14's `74HC574 vread`, which the parts list has carried
 * since 11 was written and no design clocked:
 *
 *   RDVALID  "the read latch holds the byte WPTR names"
 *   RDCK     its clock - the spare access vctrl grants to the non-span
 *            requesters (SGRANT), when the engine is not the one running
 *   RDOE     its /OE onto D0-D7 - the whole read cycle, not E-high
 *            (machine.v's 2026-09-10 lesson: a 6809E samples on E's fall)
 *   RSTART   the read's own post-increment, one dot after E falls - WPQ and
 *            WSTART's shape on vctrl, for the same reason: only an edge
 *            survives a cycle /WAIT has stretched
 *
 * RDVALID falls on ANYTHING that can move WPTR or change the byte at it: a
 * register write (WSTB - WPTR's three bytes, and nothing is lost by refilling
 * after the others), a span retire, a list advance, 7.2's column reload walk,
 * and the read's own increment. Refilling once too often costs a spare access;
 * missing one returns a wrong byte, so the list errs one way. While RDVALID is
 * low, vctrl asks for the access (SPNREQ) and holds a VRAM read on /WAIT.
 *
 * ⚠ AND IT NEEDS NO CPU ADDRESS AT ALL, which is why it closes at both E rates:
 * the byte is fetched before the CPU asks for it, not inside the CPU's cycle,
 * so 11's phase-by-phase ÷12 budget - and its ÷8 failure - do not apply. */
const RDCLR = "!WSTB & !RETIRE & !LADV & !RSTART & !RP0 & !RP1"
/* ⭐ VDATA, +$15 - graphics.md 11, 19 item 47. The same port at an address in
 * the I/O page, so a task or a handler reaches VRAM without an MMU block. It is
 * decoded from the RAW address and not from RA: while a span runs RA is WFG or
 * WBG, and a VDATA access under a span is exactly the one that has to wait.
 * VRAMSEL cannot carry it - it is qualified !IOPAGE so that no I/O cycle ever
 * touches VRAM - so every consumer of the port takes VRAMSEL # VDSEL. */
const VDSEL_TERM = `IOSEL & A6 & A5 & ${[4, 3, 2, 1, 0]
  .map((b) => `${(REGS.VDATA >> b) & 1 ? "" : "!"}A${b}`).join(" & ")}`
export const vramRead: Cell[] = [
  comb("VDSEL", [VDSEL_TERM], "13: +$15 VDATA, the VRAM port in the I/O page - to vctrl's strobe and /WAIT"),
  reg("RPQ", ["VRAMSEL & RW & E", "VDSEL & RW & E"], "a VRAM read was in E-high on the last dot"),
  comb("RSTART", ["RPQ & !E"], "11's post-increment: the dot after a VRAM read's E falls"),
  /* Active low, so the '574's rising edge is the END of the granted dot, when
   * the framebuffer has answered - the same instant the list engine's latch
   * takes the same bus. */
  lowPin("RDCK", ["SGRANT & !LRUN & !RDVALID"],
    "11: clock the vread '574 off the pixel bus - the spare access, at WPTR"),
  reg("RDVALID", [`RDCK & ${RDCLR}`, `RDVALID & ${RDCLR}`],
    "11: the read latch holds the byte at WPTR"),
  lowPin("RDOE", ["VRAMSEL & RW", "VDSEL & RW"], "11: the vread '574 drives D0-D7 for a VRAM read cycle"),
  comb("VINC", ["LADV", "RSTART"], "WPTR's increment: the list engine's, or a VRAM read's"),
]
