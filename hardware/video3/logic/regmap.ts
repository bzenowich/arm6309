/* video3's register offsets - ONE table, shared by the part that decodes the
 * bus and the three parts that decode the broadcast.
 *
 * ⭐ WHY THIS FILE EXISTS.  v3host used to own a private copy of this map and
 * emit one load strobe per register, which put it at 64/64 pins with 78
 * macrocells idle (partition.md §0, the fourth fit).  The card now broadcasts
 * RA4..RA0 + REGWR and each part decodes the offsets it cares about - so the
 * map is read by four designs and must not be able to drift between them.
 *
 * plan.md §10 is the specification; this is that table in machine-readable
 * form, and `npm run check:docs` is not what checks it - a decode that
 * disagrees with the spec fits perfectly well and answers the wrong address. */

/** The offsets, from plan.md §10.  Names are the LOAD STROBE each produces. */
export const REGS = {
  LDCTRL:   0x00, // CTRL
  LDVSL:    0x01, // VSCROLL low
  LDVSH:    0x02, // VSCROLL high
  LDHSL:    0x03, // HSCROLL low   - read by BOTH v3scan and v3dot
  LDHSH:    0x04, // HSCROLL high
  LDSPLEN:  0x05, // SPANLEN
  LDWFG:    0x06, // WFG  - must stay even (plan §5)
  LDWBG:    0x07, // WBG  - must stay at the odd offset above WFG
  LDWP0:    0x08, // WPTR bits 7..0
  LDWP1:    0x09, // WPTR bits 15..8
  LDWP2:    0x0a, // WPTR bits 18..16
  LDWADV:   0x0b, // WADV
  /*        0x0c    VDATA - the VRAM port, not a register (v3host's VDSEL) */
  /*        0x0d    VSTAT - read-only through a '244; a WRITE is the IRQ ack */
  LDIRQACK: 0x0d,
  LDPIDXL:  0x0e, // PIDX low
  LDPIDXH:  0x0f, // PIDX high
  LDPDATL:  0x10, // PDATL
  LDPDATH:  0x11, // PDATH - the write posts the palette commit
  LDCP0:    0x12, // CPTR bits 7..0
  LDCP1:    0x13, // CPTR bits 15..8
  LDCP2:    0x14, // CPTR bits 18..16
  LDCW:     0x15, // CWIDTH low 8
  LDCH:     0x16, // CHEIGHT low 8
  LDCCTRL:  0x17, // CCTRL - and it carries CWIDTH[9:8] and CHEIGHT[8]
  LDTB:     0x18, // TILEBASE
  LDMB:     0x19, // MAPBASE
  LDSPRX:   0x1a, // SPRX
  LDSPRY:   0x1b, // SPRY
  LDSPRH:   0x1c, // SPRH - SPRX[9:8], SPRY[8], enable
  LDSPRIX:  0x1d, // SPRIDX
  LDSPRDA:  0x1e, // SPRDAT
  /*        0x1f    reserved */
} as const

export type RegName = keyof typeof REGS

/** The five broadcast address lines and their qualifier (signals.md §3). */
export const BROADCAST = ["REGWR", "RA0", "RA1", "RA2", "RA3", "RA4"] as const

const match = (a: number, pfx: string) =>
  [4, 3, 2, 1, 0].map((b) => `${(a >> b) & 1 ? "" : "!"}${pfx}${b}`).join(" & ")

/** One product term: this offset is being written, off the broadcast. */
export const decodeTerm = (r: RegName): string => `REGWR & ${match(REGS[r], "RA")}`

/** The same decode off the backplane, for the part that makes the broadcast. */
export const hostTerm = (r: RegName, qualifier: string): string =>
  `${qualifier} & ${match(REGS[r], "A")}`

/** A receiver's decode cells - internal nodes, so they cost a cell and no pin. */
export const decodeCells = (names: readonly RegName[]) =>
  names.map((n) => ({
    pin: 0, name: n as string, assertedLow: false, s0: 1 as const,
    registered: false, terms: [decodeTerm(n)],
  }))
