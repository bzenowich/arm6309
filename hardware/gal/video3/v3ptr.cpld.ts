/* v3ptr - video3's pointers, span writer and copy engine, as an ATF1508AS.
 *
 * video3/docs/partition.md §2.3.  The other half of the tri-stated FBA bus:
 * v3scan drives it for the scan and map addresses, this part for WPTR and CPTR,
 * and v3dot's arbiter is the one place that decides which (partition.md §1).
 *
 * ⭐ SO THIS MUX IS TWO SOURCES.  `video`'s vaddr carries four with one spare and
 * graphics.md §10.1.6.2 records fits that ran out there.  v3scan's fit already
 * showed three is cheap; this is the other half of that claim.
 *
 * ⛔ AND THE POINTERS NAME THE FIRST CELL PROCESSED, not the rectangle's origin
 * (plan §6.2, corrected while writing this file).  Naming the origin and walking
 * inside it means starting at origin + height - 1, which is an ADDER, and
 * graphics.md §6.4.1 and §7.2 build this card on not having one.
 */

import { toCupl, type Merged } from "../jedec/cupl"
import type { Cell } from "../jedec/assemble"
import { BROADCAST, decodeCells, type RegName } from "./regmap"
import { counterTerms, loadable } from "../jedec/counter"

/* ⭐ V3_COPYDIR picks which of the copy engine's direction bits are BUILT.
 * plan §6.2 says the column bit is "an optimisation, not a requirement" because
 * an overlapping copy can stage through the off-screen columns in two passes -
 * and the same trick works on rows, where plan §4 keeps rows 480-511 as scratch.
 * It is a switch and not a comment because the fit is the only thing that can
 * say what they cost.
 *   both (default) | rows | none */
export const COPYDIR = process.env.V3_COPYDIR ?? "none"

/* ⛔ V3_SEQ PICKS WHICH SEQUENCERS ARE BUILT, and it exists because the fit
 * said no. With both of them in this part the ATF1508AS fitter answers
 * "Grouping fail / Design does not fit" on all four passes - and a failed fit
 * reports no utilisation at all, so it cannot say by how much. The switch is
 * how the question gets bisected, exactly as V3_COPYDIR bisected the
 * direction bits: a variant is kept as a FIT, not as prose.
 *   both | span | copy | split | none (the state before 2026-09-18)
 *
 * ⭐ `split` IS THE PARTITION EXPERIMENT partition.md §2.3 owes: the two wide
 * decodes - CEOR and CHLAST, which need ten and nine of THIS part's counter
 * bits - stay here beside the counters, and the copy's phase machine moves to
 * v3host, which is 27/128 with 22 spare pins. Seven signals cross instead of
 * nineteen. v3host.cpld.ts reads the same switch. */
/* ⭐ AND THE DEFAULT IS THE ONE THAT FITS, as COPYDIR's is. Measured
 * 2026-09-18, all three from gal/cpld/*.fit:
 *
 *   none  110/128 cells, 44/64 I/O, 3 cascades  ⭐ THIS BUILD, unchanged
 *   span  115/128,        48/64,     3 cascades  the span writer's, +5 cells
 *                                                and NO cascade change
 *   copy  117/128,        41/64,     8 cascades  the copy engine's, +5
 *                                                CASCADES on its own
 *   both  ⛔ DOES NOT FIT - refused under two different file names,
 *         "Grouping fail" and "Design does not fit"
 *
 * ⚠ 122 is what the two would cost if the cells simply added, and 122 is
 * under 128 - so the refusal is NOT the cell count. It is LAB grouping:
 * Nodes+FB/MCells is already 125% with ONE sequencer, and CEOR and CHLAST
 * each need ten and nine counter bits inside one block.
 *
 * ⛔ AND THE DEFAULT IS `none` FOR A REASON THAT IS NOT THE DESIGN. The span
 * variant FITS - twice, as `v3ptr_span.pld` - and the SAME BYTES refuse four
 * times in a row as `v3ptr.pld`. The committed baseline still fits under its
 * own name, so the prefix is healthy; the fitter's placement is simply
 * sensitive to the output file name on a design this close to the edge. Until
 * that is understood, the build does not change on the strength of a design
 * that cannot be fitted under its own name - the variants carry the evidence,
 * exactly as V3_COPYDIR's do. plan §14 item 14.
 *
 */
const SEQ = process.env.V3_SEQ ?? "split"
const SPANSEQ = SEQ === "both" || SEQ === "span" || SEQ === "split"
const COPYSEQ = SEQ === "both" || SEQ === "copy"
/* split: the decodes stay, the phase machine goes to v3host */
const COPYDEC = SEQ === "split"
/* ⭐ V3_RELOAD builds §7.2's END-OF-ROW COLUMN RELOAD, which nothing did.
 * Both engines need it: a chained glyph would step eight pixels right on every
 * row (design-review2.md V-6 is that defect on the other card) and a copy's
 * two columns would climb across rows instead of restarting. */
const RELOAD = (process.env.V3_RELOAD ?? "on") === "on" && SEQ === "split"
const DIRC = COPYDIR === "both" ? "CDIRC" : null
const DIRR = COPYDIR === "none" ? null : "CDIRR"

/* -- a load whose strobe differs per bit ---------------------------------
 *
 * ⛔ counter.ts's `loadable` takes ONE strobe, and this part's registers are
 * wider than the bus: WPTR is 19 bits arriving as three bytes, CPTR likewise,
 * and CWIDTH's top two bits and CHEIGHT's top bit ride in CCTRL (plan §10).
 * With one strobe per register, `LDWCOL & D0` drove WC0 AND WC8 - one store
 * landing in two bits. So the strobe is per bit, and the hold is too: bit i
 * holds unless ITS OWN byte is the one being written. */
const loadableM = (bits: string[], enable: string, load: string[],
                   from: string[]): string[][] => {
  const counted = counterTerms({ bits, enable })
  return bits.map((_, i) => [
    `${load[i]} & ${from[i]}`,
    ...counted[i].map((t) => `!${load[i]} & ${t}`),
  ])
}

/* -- ⭐ A LOAD WITH TWO SOURCES - the CPU's store and the column reload ----
 *
 * ⛔ AND THE STROBES MUST STAY SEPARATE. `LDA # RLDA` is the obvious escape
 * and access.jedec.ts records what it costs: CUPL substitutes combinational
 * intermediates, so every HOLD term becomes `!(LDA # RLDA)` - two terms where
 * there was one, across all ten macrocells - and the ATF1508 fitter aborts
 * with INTERNAL ERROR. One term per source, and the hold names both. */
const loadable2 = (bits: string[], enable: string, load: string[],
                   from: string[], rld: string[], rfrom: string[]): string[][] => {
  const counted = counterTerms({ bits, enable })
  return bits.map((_, i) => [
    `${load[i]} & ${from[i]}`,
    `${rld[i]} & ${rfrom[i]}`,
    ...counted[i].map((t) => `!${load[i]} & !${rld[i]} & ${t}`),
  ])
}

/* -- an up/down counter, which counter.ts does not have ------------------
 *
 * Bit i toggles when every lower bit is 1 counting up, or 0 counting down.
 * ⚠ This is the one block on the part whose product-term cost grows with
 * width, so it is where a refusal would come from. */
const upDown = (bits: string[], en: string, dir: string | null, load?: string[],
                from?: string[]): Cell[] =>
  dir === null
    /* up only: counter.ts's own terms, which cost a fraction of the pair */
    ? bits.map((q, i) => ({
        pin: 0, name: q, assertedLow: false, s0: 1 as const, registered: true,
        terms: load && from
          ? loadableM(bits, en, load, from)[i]
          : counterTerms({ bits, enable: en })[i],
      }))
  : bits.map((q, i) => {
    const lower = bits.slice(0, i)
    const up = [`!${dir}`, en, ...lower]
    const dn = [dir, en, ...lower.map((b) => `!${b}`)]
    const hold = [`!${en}`, q]
    const terms = [
      /* hold when not enabled, or when enabled but not toggling */
      hold.join(" & "),
      ...(lower.length ? lower.map((b) => [en, q, `!${b}`, `!${dir}`].join(" & ")) : []),
      ...(lower.length ? lower.map((b) => [en, q, b, dir].join(" & ")) : []),
      /* toggle 0 -> 1 */
      [`!${q}`, ...up].join(" & "),
      [`!${q}`, ...dn].join(" & "),
    ]
    return {
      pin: 0, name: q, assertedLow: false, s0: 1 as const, registered: true,
      terms: load && from
        ? [`${load[i]} & ${from[i]}`, ...terms.map((t) => `!${load[i]} & ${t}`)]
        : terms,
    }
  })

/* -- WPTR: the span writer's, the CPU port's and copyrect's destination ---
 *
 * The column reloads at end-of-row from the register file (graphics.md §7.2):
 * rfa points the file at +$08 then +$09 and each byte lands on the SAME load
 * path the CPU's own write uses, so the reload costs no latch and no mux - it
 * is LDWA/LDWB driven by the sequencer instead of by a store. */
const WCOL = [...Array(10).keys()].map((b) => `WC${b}`)
const WROW = [...Array(9).keys()].map((b) => `WR${b}`)
/* ⭐ The 19-bit pointer packs little-endian across +$08..+$0A, so the byte a
 * bit arrives in is what names its strobe:
 *   +$08  D7..D0 -> WC7..WC0
 *   +$09  D1..D0 -> WC9..WC8   and   D7..D2 -> WR5..WR0
 *   +$0A  D2..D0 -> WR8..WR6
 * The bit-to-D mapping below is the one this part already had, and it was
 * right; only the strobe was wrong. CPTR at +$12..+$14 is the same shape. */
const PTRCOL_LD = (b: number) => (b < 8 ? 0 : 1)
const PTRCOL_D = (b: number) => (b < 8 ? `D${b}` : `D${b - 8}`)
const PTRROW_LD = (b: number) => (b < 6 ? 1 : 2)
const PTRROW_D = (b: number) => (b < 6 ? `D${b + 2}` : `D${b - 6}`)
const ptrLd = (pfx: string, f: (b: number) => number, n: number) =>
  [...Array(n).keys()].map((b) => `LD${pfx}P${f(b)}`)

const wptr: Cell[] = [
  ...WCOL.map((name, i) => ({
    pin: 0, name, assertedLow: false, s0: 1 as const, registered: true,
    terms: (RELOAD
      ? loadable2(WCOL, "WINC", ptrLd("W", PTRCOL_LD, 10),
          [...Array(10).keys()].map(PTRCOL_D),
          [...Array(10).keys()].map((b) => (b < 8 ? "RP1" : "RP2")),
          [...Array(10).keys()].map(PTRCOL_D))
      : loadableM(WCOL, "WINC", ptrLd("W", PTRCOL_LD, 10),
          [...Array(10).keys()].map(PTRCOL_D)))[i],
  })),
  ...upDown(WROW, "WROWADV", DIRR, ptrLd("W", PTRROW_LD, 9),
    [...Array(9).keys()].map(PTRROW_D)),
]

/* -- CPTR: the copy engine's source -------------------------------------- */
const CCOL = [...Array(10).keys()].map((b) => `CC${b}`)
const CROW = [...Array(9).keys()].map((b) => `CR${b}`)
const cptr: Cell[] = [
  ...(RELOAD && DIRC === null
    ? CCOL.map((name, i) => ({
        pin: 0, name, assertedLow: false, s0: 1 as const, registered: true,
        terms: loadable2(CCOL, "CSTEP", ptrLd("C", PTRCOL_LD, 10),
          [...Array(10).keys()].map(PTRCOL_D),
          [...Array(10).keys()].map((b) => (b < 8 ? "RP3" : "RP4")),
          [...Array(10).keys()].map(PTRCOL_D))[i],
      }))
    : upDown(CCOL, "CSTEP", DIRC, ptrLd("C", PTRCOL_LD, 10),
        [...Array(10).keys()].map(PTRCOL_D))),
  ...upDown(CROW, "CROWADV", DIRR, ptrLd("C", PTRROW_LD, 9),
    [...Array(9).keys()].map(PTRROW_D)),
]

/* -- the copy's width and height ----------------------------------------
 *
 * The width is a register AND a working counter, because it reloads every row;
 * the height counts once, so its register IS the counter and software reloads
 * it for the next copy. */
const CW = [...Array(10).keys()].map((b) => `CW${b}`)
const CWN = [...Array(10).keys()].map((b) => `CWN${b}`)
const CH = [...Array(9).keys()].map((b) => `CH${b}`)
const counters: Cell[] = [
  /* ⚠ plan §10: CCTRL b4..3 IS CWIDTH[9:8], so the top two bits load from a
   * different offset than the bottom eight - one register in the programmer's
   * model, two bytes on the bus. */
  ...CW.map((name, i) => {
    const ld = i < 8 ? "LDCW" : "LDCCTRL"
    return {
      pin: 0, name, assertedLow: false, s0: 1 as const, registered: true,
      terms: [`${ld} & ${i < 8 ? `D${i}` : `D${i - 5}`}`, `${name} & !${ld}`],
    }
  }),
  /* ⭐ THE WORKING COUNTERS HOLD THE COMPLEMENT AND COUNT UP - vlen.jedec.ts's
   * idiom, and the reason counter.ts has no down-counter generator. The load
   * inverts for free (one literal on a term that exists anyway) and the
   * terminal decode becomes ONE product term instead of a comparator.
   *
   * ⛔ AND THE DECODE IS `..11110`, NOT `..11111`. CWIDTH is the plain byte
   * count N - the emulator, the functional model, both NitrOS-9 drivers and
   * the bench all agree, none of them biases it - so loading ~N and testing
   * all-ones would end the row one byte late. The counter is sampled BEFORE
   * the edge that steps it, so during byte k it holds ~N + k - 1, and byte N
   * is ~N + N - 1 = all-ones-except-bit-0. Ten literals, still one term, and
   * still no adder anywhere (plan §6).
   * ⚠ N = 0 would copy 1024 bytes rather than none; armvid.d documents
   * CP.W as 1-1023 and both models return early on zero. */
  ...CWN.map((name, i) => ({
    pin: 0, name, assertedLow: false, s0: 1 as const, registered: true,
    terms: loadable(CWN, "CSTEP", "CWLOAD", CW.map((n) => `!${n}`))[i],
  })),
  /* and CCTRL b5 is CHEIGHT[8], the same way */
  ...CH.map((name, i) => ({
    pin: 0, name, assertedLow: false, s0: 1 as const, registered: true,
    terms: loadableM(CH, "CROWADV",
      [...Array(9).keys()].map((b) => (b < 8 ? "LDCH" : "LDCCTRL")),
      [...Array(9).keys()].map((b) => (b < 8 ? `!D${b}` : "!D5")))[i],
  })),
]

/* -- ⭐ THE COPY ENGINE'S SEQUENCER - plan §6, and it did not exist ------
 *
 * ⛔ CGO, CDONE, CSTEP, CROWADV, CWLOAD and CRDSEL were declared as INPUTS
 * here, "likewise from v3dot", and v3dot exports none of them: the pointers,
 * the counters and CBUSY were all built and nothing started or stepped any of
 * them (plan §14 item 14). This is §6's engine itself - the thing §1's
 * deletion of the display list was what paid for.
 *
 * ⭐ TWO ACCESSES A BYTE IS TWO SLOTS A BYTE, and that is the whole of the
 * state machine. There is ONE spare access a slot (check:video3 asserts it),
 * the copy wants a read and a write, so a byte takes two grants and the phase
 * bit is the only state the sequence needs:
 *
 *   CPH = 0   the READ access:  CPTR on the address bus, the byte lands in
 *             §11's `vread` '574
 *   CPH = 1   the WRITE access: WPTR on the bus, the posted-write '574 drives
 *             it back - and the pointers step with this one
 *
 * ⚠ 4.05 MB/s follows: 8.1 M spare accesses a second, two a byte.
 *
 * ⛔ WHAT IS STILL OWED, and it is not on this part: the COLUMN RELOAD at
 * end of row. plan §6 and §7.2 keep both columns' shadows in the REGISTER
 * FILE, so the reload is `rfa` pointing the file at +$08/+$09 and +$12/+$13
 * and driving the same LDWP/LDCP load path a CPU store uses. That is the
 * register-file address owner's business - v3host - and CROWADV is the
 * handshake it has to take. Without it both columns keep climbing across
 * rows. The counters, the pointers and the termination below are complete;
 * the reload is the one piece this part cannot build alone. */
/* \u2b50 the split: only what needs this part's counter bits, plus the busy flag
 * whose GO term is a register decode this part already has. */
const copyDec: Cell[] = [
  { pin: 0, name: "CEOR", assertedLow: false, s0: 1, registered: false,
    why: "the last byte of a row - ~N + N - 1, one product term",
    terms: [`!${CWN[0]} & ${CWN.slice(1).join(" & ")}`] },
  { pin: 0, name: "CHLAST", assertedLow: false, s0: 1, registered: false,
    terms: [`!${CH[0]} & ${CH.slice(1).join(" & ")}`] },
  { pin: 0, name: "CBUSY", assertedLow: false, s0: 1, registered: true,
    terms: ["LDCCTRL & D0", "CBUSY & !CDONE"] },
]
const copyStub: Cell[] = [
  { pin: 0, name: "CBUSY", assertedLow: false, s0: 1, registered: true,
    terms: ["CGO", "CBUSY & !CDONE"] },
]
const copySeq: Cell[] = [
  /* one tick per granted copy access. ⚠ SPARETICK for the same reason the
   * span writer needs it: the arbiter is combinational and GCPY is asserted
   * for every dot of the spare window (design-review2.md V-4). */
  { pin: 0, name: "CTICK", assertedLow: false, s0: 1, registered: false,
    terms: ["GCPY & SPARETICK"] },
  { pin: 0, name: "CPH", assertedLow: false, s0: 1, registered: true,
    why: "0 = the read access, 1 = the write. Zero whenever the engine is idle",
    terms: ["CBUSY & CTICK & !CPH", "CBUSY & !CTICK & CPH"] },
  /* ⚠ QUALIFIED BY CBUSY, not just !CPH: this is the address mux's select,
   * and an idle engine must leave WPTR on the bus for the span writer and the
   * CPU port. */
  { pin: 0, name: "CRDSEL", assertedLow: false, s0: 1, registered: false,
    terms: ["CBUSY & !CPH"] },
  { pin: 0, name: "CSTEP", assertedLow: false, s0: 1, registered: false,
    why: "the byte is written: both columns step and the width counter counts",
    terms: ["CTICK & CPH"] },
  { pin: 0, name: "CEOR", assertedLow: false, s0: 1, registered: false,
    why: "the last byte of a row - ~N + N - 1, one product term",
    terms: [`!${CWN[0]} & ${CWN.slice(1).join(" & ")}`] },
  { pin: 0, name: "CROWADV", assertedLow: false, s0: 1, registered: false,
    terms: ["CSTEP & CEOR"] },
  { pin: 0, name: "CWLOAD", assertedLow: false, s0: 1, registered: false,
    why: "the width reloads every row; the height does not - software rewrites it",
    terms: ["CROWADV"] },
  { pin: 0, name: "CHLAST", assertedLow: false, s0: 1, registered: false,
    terms: [`!${CH[0]} & ${CH.slice(1).join(" & ")}`] },
  { pin: 0, name: "CDONE", assertedLow: false, s0: 1, registered: false,
    terms: ["CROWADV & CHLAST"] },
  /* ⭐ the request into v3dot's arbiter, and it is the busy flag: a copy in
   * flight IS the request, exactly as census.ts records SPANBUSY -> SPNREQ for
   * the other card. */
  { pin: 0, name: "RCPY", assertedLow: false, s0: 1, registered: false,
    terms: ["CBUSY"] },
  /* ⛔ CBUSY's set term WAS an input called CGO that nothing produced. GO is
   * CCTRL b0 and CCTRL is decoded on this part, so it is a term, not a pin. */
  { pin: 0, name: "CBUSY", assertedLow: false, s0: 1, registered: true,
    terms: ["LDCCTRL & D0", "CBUSY & !CDONE"] },
]

/* -- the span writer: graphics.md §7.4, inherited whole -------------------
 *
 * ⭐ The serialiser's serial output IS the register file's address bit 0, which
 * is what makes per-pixel colour selection free - so RFA and the serialiser are
 * on one part by construction, not by choice. */
const MASK = [...Array(8).keys()].map((b) => `MS${b}`)
const spanWriter: Cell[] = [
  ...MASK.map((name, i) => ({
    pin: 0, name, assertedLow: false, s0: 1 as const, registered: true,
    terms: i === 7
      ? [`WSTB & D7`, `!WSTB & !RETIRE & ${name}`]
      : [`WSTB & D${i}`, `!WSTB & RETIRE & MS${i + 1}`, `!WSTB & !RETIRE & ${name}`],
  })),
  /* ⭐ SPANLEN HOLDS ITS COMPLEMENT AND COUNTS UP, which is vlen.jedec.ts's
   * idiom and the reason counter.ts never needed a down-counter generator:
   * "a down-counter's borrow chain and an up-counter's carry chain are the
   * same equations on inverted state", and the terminal count is then ONE
   * product term of eight literals instead of eight terms of one. plan §10
   * writes SPANLEN as "span length - 1", so a load of N gives N + 1 bytes.
   * ⛔ The load was NOT inverted before this, so the counter counted up from
   * the length and could never reach a terminal count - invisible, because
   * nothing produced RETIRE to clock it. */
  ...[...Array(8).keys()].map((b) => ({
    pin: 0, name: `NSL${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: loadable([...Array(8).keys()].map((i) => `NSL${i}`), "RETIRE", "WSTB",
      [...Array(8).keys()].map((i) => `!D${i}`))[b],
  })),
  ...[...Array(3).keys()].map((b) => ({
    pin: 0, name: `MK${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: counterTerms({ bits: [...Array(3).keys()].map((i) => `MK${i}`),
                          enable: "RETIRE", clear: "WSTB" })[b],
  })),
  ...[0, 1].map((b) => ({
    pin: 0, name: `WADV${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`LDWADV & D${b}`, `WADV${b} & !LDWADV`],
  })),
  { pin: 0, name: "SPANBUSY", assertedLow: false, s0: 1, registered: true,
    terms: ["WSTB", "SPANBUSY & !SPANEND"] },
  /* ⭐ the request into v3dot's arbiter: a span in flight IS the request,
   * which is what census.ts records as seqctl.SPANBUSY -> SPNREQ on the other
   * card. A cell and not a spelling coincidence, because a net that depends on
   * two engineers choosing the same word is not a net. */
  ...(SPANSEQ ? [{ pin: 0, name: "RSPN", assertedLow: false, s0: 1 as const,
    registered: false, terms: ["SPANBUSY"] }] : []),
]

/* -- ⭐ THE SPAN WRITER'S SEQUENCER - seqctl.jedec.ts, ported -------------
 *
 * ⛔ IT DID NOT EXIST. `RETIRE`, `SPANEND`, `WINC` and `WROWADV` were
 * declared as INPUTS on this part, commented "from v3dot", and v3dot exports
 * none of them: the counters, the serialiser and SPANBUSY were built and
 * nothing stepped them (plan §14 item 14, found by check:reach 2026-09-18).
 * `video/`'s seqctl is the same machine, fitted and simulated by vspan_tb, so
 * this is a port and not a design - with two differences and one saving:
 *
 *   - NO `!LRUN`. video3 deletes the display-list engine (plan §1), so
 *     WROWADV needs no "the list owns WPTR" qualification. Two literals gone.
 *   - `TC` IS INTERNAL. seqctl took it from the discrete '161 pair; here
 *     SPANLEN is on this part, so the terminal count folds into SPANEND's own
 *     term as the eight-literal conjunction above.
 *   - ⭐ MASK AND SPRITE SHARE A TERM. Both end on the three-bit counter and
 *     both have WMODE b0 set, while direct (00) and solid (10) do not - so
 *     `WM0 & MK2 & MK1 & MK0` is one term where seqctl wrote two.
 *
 * ⚠ SPNTICK IS NOT OPTIONAL, and design-review2.md V-4 is why: v3dot's
 * arbiter is combinational, so GSPN is asserted for every dot of the spare
 * window and a retire on each would move four bytes a slot instead of one.
 * SPARETICK is the window's last dot. */
const spanSeq: Cell[] = [
  /* ⛔ WMODE HAD NO PRODUCER ANYWHERE. plan §10 puts it at CTRL b5..4 and
   * v3dot holds CTRL as CT0..CT7 - but it exports MODE and VMODE and not these
   * two, and v3dot is 122/128 with Nodes+FB at 124%, so it cannot grow a cell
   * or a pin to do it (measured: a SPARETICK cell and a DP0 export were both
   * refused). partition.md §3's answer is that a part decodes the offsets it
   * needs off the broadcast, which is what this does - the same duplication
   * v3dot already makes of HSCROLL[1:0]. Three cells, and the span writer has
   * its mode. */
  ...[0, 1].map((b) => ({
    pin: 0, name: `WM${b}`, assertedLow: false, s0: 1 as const, registered: true,
    terms: [`LDCTRL & D${b + 4}`, `WM${b} & !LDCTRL`],
  })),
  { pin: 0, name: "RETIRE", assertedLow: false, s0: 1, registered: false,
    why: "one byte goes to VRAM: also WPTR's column step, the serialiser's shift and SPANLEN's count",
    terms: ["SPANBUSY & GSPN & MUXSEL0"] },
  { pin: 0, name: "SPANEND", assertedLow: false, s0: 1, registered: false,
    terms: [
      "RETIRE & !WM1 & !WM0",                                   /* direct: one byte */
      "RETIRE & WM0 & MK2 & MK1 & MK0",                         /* mask and sprite: eight */
      `RETIRE & WM1 & !WM0 & ${[...Array(8).keys()].map((i) => `NSL${i}`).join(" & ")}`,
    ] },
  /* ⭐ the whole of sprite mode, and it is one macrocell: every other mode
   * writes every byte it retires, and sprite mode suppresses only the WRITE.
   * ⚠ The pointer must still advance or the sprite draws squashed, which is
   * why this is a second output and not a qualification of RETIRE.
   * ⚠ MS0 IS THE CURRENT BIT: the serialiser shifts DOWN (MS_i takes
   * MS_i+1 on RETIRE), so MS0 is what leaves. */
  { pin: 0, name: "WEN", assertedLow: false, s0: 1, registered: false,
    why: "RETIRE, except a transparent pixel in sprite mode",
    terms: ["RETIRE & !WM1", "RETIRE & !WM0", "RETIRE & MS0"] },
  /* ⛔ WPTR IS THE COPY'S DESTINATION TOO (plan §6), so both pointers'
   * advances are ORs of the two engines. Only one can be busy: the arbiter
   * grants one requester an access. */
  { pin: 0, name: "WINC", assertedLow: false, s0: 1, registered: false,
    terms: ["RETIRE", "CSTEP"] },
  { pin: 0, name: "WROWADV", assertedLow: false, s0: 1, registered: false,
    terms: ["SPANEND & WADV0", "SPANEND & WADV1", "CROWADV"] },
]

/* -- ⭐ §7.2's END-OF-ROW COLUMN RELOAD - this part's half --------------
 *
 * ⛔ IT DID NOT EXIST, AND WITHOUT IT NEITHER ENGINE CHAINS. §7.2 is the
 * section that takes a character cell from 26 CPU writes to 13 - "set it once
 * and a glyph becomes eight mask writes and nothing else" - and it does that
 * by restoring WPTR's COLUMN at end of row while the row steps. With the
 * column's only load path being the CPU's own three-byte store, a chained
 * glyph steps eight pixels right on every row; `video/` shipped exactly that
 * defect and design-review2.md V-6 is it. The copy engine has it twice over,
 * because BOTH its columns have to come back.
 *
 * ⭐ THE SHADOWS ARE THE REGISTER FILE, and they are free: +$08/+$09 and
 * +$12/+$13 already hold what the CPU last wrote, which IS the column the
 * rectangle started at. ⚠ `video/` records that ten macrocells of shadow
 * REGISTERS would be simpler - and that the fitter returned INTERNAL ERROR
 * for them (graphics.md 19 item 31). Here it would be TWENTY, on a part with
 * nine cells free.
 *
 * ⛔ AND THE FOUR-DOT WALK IS ON v3host, not here. Built on this part it was
 * five more cells on top of these load terms and the fitter refused it under
 * two names. What stays is what CANNOT leave: the load terms themselves, and
 * RFA0 - because §5 makes the file's address bit 0 the MASK BIT, and the
 * serialiser is here. partition.md §2.3's "RFA and the serialiser are on one
 * part by construction" holds for the bit that is the construction; RFA4..RFA1
 * are an ordinary address and they are on v3host with the walk.
 *
 *   RP1  +$08 -> WC7..WC0      RP3  +$12 -> CC7..CC0   (copy only)
 *   RP2  +$09 -> WC9..WC8      RP4  +$13 -> CC9..CC8
 *
 * ⚠ TWO STROBES A POINTER AND NOT ONE, and the ROW is why: +$09 carries
 * WC9..WC8 in D1..D0 AND WR5..WR0 in D7..D2, so a reload that reused the
 * CPU's own LDWP1 would undo the row advance the same span just made. */
const reload: Cell[] = [
  /* ⚠ BIT 0 IS THE MASK BIT INVERTED. WFG is +$06 and WBG is +$07, so A0 = 0
   * selects the FOREGROUND - and a glyph's 1 bits are its ink. ⛔ And the CPU
   * does not get the file while a span runs: §5's colour path IS this address,
   * so an access during a span retires whatever byte the CPU's own address
   * named - three pixels a poll, and machine_tb drew every span with a hole
   * in it (graphics.md 19 item 38). */
  { pin: 0, name: "RFA0", assertedLow: false, s0: 1, registered: false,
    why: "§5: the mask bit IS the register file's address bit 0, inverted",
    terms: ["REGWR & !SPANBUSY & RIDLE & RA0",
            "SPANBUSY & RIDLE & !MS0",
            "!REGWR & !SPANBUSY & RIDLE",      /* idle: +$05, SPANLEN */
            "RP2", "RP4"],                     /* +$09 and +$13 */
  },
  { pin: 0, name: "RIDLE", assertedLow: false, s0: 1, registered: false,
    terms: ["!RP1 & !RP2 & !RP3 & !RP4"] },
]

/* -- the address bus: TWO sources, and an output enable ------------------ */
const addressMux: Cell[] = [...Array(17).keys()].map((i) => {
  const bit = i + 2
  const w = bit >= 10 ? `WR${bit - 10}` : `WC${bit}`
  const c = bit >= 10 ? `CR${bit - 10}` : `CC${bit}`
  return {
    pin: 0, name: `FBA${bit}`, assertedLow: false, s0: 1 as const, registered: false,
    terms: [`!CRDSEL & ${w}`, `CRDSEL & ${c}`],
    oe: "FBOEPTR",
  }
})

/* the offsets this part answers to.  ⭐ Ten, where the strobe wiring gave it
 * seven - and the three extra are the multi-byte loads that wiring could not
 * express at all, because a strobe per REGISTER cannot load a register wider
 * than the bus. On the broadcast an extra offset is a decode cell, not a pin. */
const MY_REGS: RegName[] = [
  "LDWP0", "LDWP1", "LDWP2", "LDWADV",
  "LDCP0", "LDCP1", "LDCP2", "LDCW", "LDCH", "LDCCTRL",
  /* ⚠ CTRL, for WMODE alone - see WM0/WM1 in the span sequencer */
  ...((SPANSEQ ? ["LDCTRL"] : []) as RegName[]),
]

export const v3ptr: Merged = {
  name: "v3ptr",
  partNo: "ARM6309-V3P",
  location: "video3 - pointers, span writer, copy engine",
  device: "f1508ispplcc84",
  clock: "CLK25",
  inputs: [
    { name: "CLK25" }, { name: "RESET", activeLow: true },
    ...[0, 1, 2, 3, 4, 5, 6, 7].map((b) => ({ name: `D${b}` })),
    /* ⛔ TEN OF THESE WERE THE TWO SEQUENCERS, taken as inputs from a part
     * that never produced them. What is left is what genuinely arrives: the
     * posted write's strobe, the two grants, the spare window's last dot, and
     * WMODE - which lives in CTRL on v3host. */
    { name: "WSTB" },
    /* ⭐ MUXSEL0 IS THE DOT PHASE'S LOW BIT, and taking it costs v3dot NOTHING.
     * Both sequencers need the spare window's LAST dot: the arbiter is pure
     * combinational grant logic with no phase term, so GSPN and GCPY are
     * asserted for every dot of the window and a step on each would move four
     * bytes a slot (design-review2.md V-4). ⛔ A `SPARETICK` cell on v3dot was
     * the obvious way and the fitter refused it twice - that part is 122/128
     * with Nodes+FB at 124% - and so was exporting DP0 itself, because forcing
     * a buried counter bit onto a pin is not free there either. But SPARE is
     * `!DP1`, the grants already contain it, and `comb("MUXSEL0", ["DP0"])` is
     * ALREADY an external. So `GSPN & MUXSEL0` is the tick, for one literal on
     * a term the receiver has anyway and not one macrocell anywhere. */
    ...(SPANSEQ || COPYSEQ ? [{ name: "MUXSEL0" }] : []),
    ...(RELOAD ? [{ name: "RP1" }, { name: "RP2" }, { name: "RP3" },
                  { name: "RP4" }] : []),
    ...(SPANSEQ ? [{ name: "GSPN" }]
                : [{ name: "RETIRE" }, { name: "SPANEND" }, { name: "WINC" },
                   { name: "WROWADV" }]),
    ...(COPYSEQ ? [{ name: "GCPY" }]
                : COPYDEC
                /* the phase machine is on v3host: its five outputs come back */
                ? [{ name: "CDONE" }, { name: "CSTEP" }, { name: "CROWADV" },
                   { name: "CWLOAD" }, { name: "CRDSEL" }]
                : [{ name: "CGO" }, { name: "CDONE" }, { name: "CSTEP" },
                   { name: "CROWADV" }, { name: "CWLOAD" }, { name: "CRDSEL" }]),
    ...(DIRR ? [{ name: "CDIRR" }] : []),
    ...(DIRC ? [{ name: "CDIRC" }] : []),
    /* ⭐ the register broadcast, decoded HERE (partition.md §3) */
    ...BROADCAST.map((n) => ({ name: n })),
    /* the bus grant - one signal, from one place */
    { name: "FBOEPTR" },
  ],
  cells: [
    ...decodeCells(MY_REGS), ...wptr, ...cptr, ...counters,
    ...(COPYSEQ ? copySeq : COPYDEC ? copyDec : copyStub), ...spanWriter,
    ...(SPANSEQ ? spanSeq : []), ...(RELOAD ? reload : []), ...addressMux],
  /* the address bus, and the three status bits v3host assembles into VSTAT */
  external: new Set([
    ...[...Array(17).keys()].map((i) => `FBA${i + 2}`),
    /* ⭐ the two status bits v3host assembles into VSTAT, the two requests the
     * arbiter answers, the write strobe the framebuffer takes, and RETIRE -
     * which also reaches v3host, where it invalidates the CPU's prefetch. */
    "SPANBUSY", "CBUSY",
    ...(SPANSEQ ? ["RSPN", "RETIRE", "WEN", "SPANEND", "WROWADV"] : []),
    ...(COPYSEQ ? ["RCPY"] : []),
    ...(COPYDEC ? ["CEOR", "CHLAST"] : []),
    /* §7.2's walk, for v3host's register-file address - and MS0, the mask
     * bit, which IS that address's bit 0 (§5) */
    ...(RELOAD ? ["RFA0", "MS0"] : []),
  ]),
}

if (import.meta.main) {
  console.log(`v3ptr (copydir=${COPYDIR}): ${v3ptr.cells.length} cells, ` +
              `${v3ptr.inputs.length} declared inputs`)
  console.log(toCupl(v3ptr))
}
