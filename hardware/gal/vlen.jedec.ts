/* vlen - the span-solid length counter, and the card's second GAL22V10.
 *
 * ⛔ WHY IT EXISTS. graphics.md 10.1.6 lists "the `'161` SPANLEN pair" among
 * the packages the two CPLDs absorbed and 14.1 deletes both from the IC count;
 * no design file contained the counter, so `TC` was an input to vctrl that
 * nothing on the card produced. seqctl's span-solid termination is
 * `RETIRE & SOLID & TC`, so with TC never asserted SPANBUSY latched for ever
 * and /WAIT held the machine on the first PaintRect. design-review2.md V-1.
 *
 * ⚠ AND IT CANNOT GO INSIDE EITHER CPLD, for one reason: 7.4 loads it from the
 * REGISTER FILE, not from the CPU bus. It has to, and that is not an
 * implementation detail - a span-solid is issued as "WPTR x3 + the posted
 * write" with SPANLEN written once (7.3's full-screen clear is 500 spans and
 * one SPANLEN), so the length has to persist somewhere across spans, and the
 * register file is where 19 item 23(b) put it. Loading it means eight pins on
 * the register file's read bus, and vctrl is at 64 of 64 I/O while vaddr is at
 * 61 of 64 with three. Eight pins is the whole story; the nine macrocells
 * would have fitted either part.
 *
 * ⭐ SO IT IS ONE GAL22V10 WHERE 14.1 DELETED TWO '161s, and the card is 28
 * ICs rather than 27 or 30. The other two absorptions - CTRL's '273 and the
 * '165 serialiser - are real, and are on vctrl now.
 *
 * ⭐ IT COUNTS UP IN THE COMPLEMENT, which is what makes it fit ten macrocells
 * with room. A down-counter's borrow chain and an up-counter's carry chain are
 * the same equations on inverted state, so the part holds ~SPANLEN, loads it
 * through the load term's own inversion (`LDLEN & !RD0`, free), and its
 * terminal count is the one everybody wants anyway: SPANLEN = 0 is ~SPANLEN =
 * 255, which is ONE product term of eight literals instead of eight terms of
 * one. counterTerms generates up-counters and this is why it never needed a
 * second generator.
 */

import { loadable } from "./jedec/counter"
import { place } from "./jedec/place"
import type { Cell, Design } from "./jedec/assemble"

const NSL = [0, 1, 2, 3, 4, 5, 6, 7].map((i) => `NSL${i}`)

/* Loaded with the complement of the register file's byte, counted on every
 * retired byte. 13's SPANLEN is "span length - 1", so a load of N gives N + 1
 * bytes: the counter reaches 255-complement - that is, zero - on the (N+1)th. */
const counted = loadable(NSL, "RETIRE", "LDLEN", NSL.map((_, i) => `!RD${i}`))

const cells: Cell[] = [
  /* The load condition, as a cell so the counter's terms can name it. */
  {
    pin: 0, name: "LDLEN", assertedLow: false, s0: 1, registered: false,
    terms: ["WSTBV & !SPANBUSY"],
  },
  ...NSL.map((name, i) => ({
    pin: 0, name, assertedLow: false, s0: 1 as const, registered: true,
    terms: counted[i],
  })),
  /* SPANLEN has counted out. One term, because the state is complemented. */
  {
    pin: 0, name: "TC", assertedLow: false, s0: 1, registered: false,
    why: "SPANLEN = 0 is ~SPANLEN = 255 - one eight-literal term, not eight terms",
    terms: [NSL.join(" & ")],
  },
]

const pins = place(cells, [14, 15, 16, 17, 18, 19, 20, 21, 22, 23])

export const vlenDesign: Design = {
  name: "vlen",
  partNo: "ARM6309-UV11",
  location: "video card - span-solid length counter",
  signature: "A6309VB",
  clockPin: 1,
  inputs: [
    /* The register file's read bus. While no span is running rfa holds the
     * file at $05 (regfile.jedec.ts), so SPANLEN is what these carry - which
     * is why the load needs no address of its own. */
    ...[0, 1, 2, 3, 4, 5, 6, 7].map((i) => ({ name: `RD${i}`, pin: 2 + i })),
    /* 3.1.1's posted VRAM write, from vctrl. */
    { name: "WSTBV", pin: 10 },
    /* ⚠ AND !SPANBUSY WITH IT. WSTBV is a level over E-high and SPANBUSY rises
     * on the first dot clock inside it - at which instant rfa switches the
     * file from SPANLEN to WFG/WBG. Without this literal the counter would
     * reload from the colour byte on every later edge of the same strobe. */
    { name: "SPANBUSY", pin: 11 },
    /* One granted retire, from seqctl. */
    { name: "RETIRE", pin: 13 },
  ],
  cells: cells.map((c) => ({ ...c, pin: pins[c.name] })),
  spares: [],
}
