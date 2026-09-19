/* video3_card.v's wiring, from the term lists - the four instance port maps
 * and the wire list, rewritten between two markers in the hand-written file.
 *
 * ⭐ A PORT A PART DOES NOT LET OUT OF ITS PACKAGE IS NOT CONNECTED. Each map
 * is the part's inputs plus its EXTERNAL cells (and `_OE` for an oe'd one),
 * and nothing else, so a buried cell cannot become a net on the board by being
 * mentioned in the wrapper - and a pin that moves between parts moves here
 * the moment its .cpld.ts does, instead of when somebody remembers.
 * Where the board needs a signal no package lets out, video3_card.v reaches
 * into the part by hierarchical reference and calls it GAP_n; this file
 * never writes one.
 *
 * Run by gen.ts, so `npm run check:video` and every check:sim script keep it
 * current. */
import { readFileSync, writeFileSync } from "fs"
import type { Merged } from "../jedec/cupl"

const BEGIN = "  // ---- every net that leaves a package ------------------------------------"
const END = "  // ======================================================================\n  // THE BOARD"

/* the card's pins and the nets the board declares itself */
const BOARD = new Set([
  "CLK25", "RESET", "E", "RW", "IOSEL", "IOPGH", "HSYNC", "VSYNC", "BLANK",
  ...[0, 1, 2, 3, 4, 5, 6, 19, 20].map((b) => `A${b}`),
  ...[...Array(8).keys()].flatMap((b) => [`D${b}`, `PA${b}`, `PB${b}`]),
])

/* the two address-bus owners get a net each; the board resolves FBA */
const net = (part: string, n: string) =>
  /^FBA\d+$/.test(n) ? `${part === "v3scan" ? "scan" : "ptr"}_${n}` : n

const wrap = (head: string, items: string[], sep: string, end: string) => {
  const out: string[] = []
  let cur = head
  items.forEach((it, i) => {
    const add = (cur === head ? "" : sep) + it
    if (cur !== head && (cur + add).length > 90) { out.push(cur + sep.trimEnd()); cur = "       " + it }
    else cur += add
  })
  return [...out, cur + end].join("\n")
}

export const portmap = (parts: [string, string, Merged][]): string => {
  const nets = new Set<string>()
  const insts = parts.map(([mod, inst, d]) => {
    const ports: string[] = []
    for (const i of d.inputs) { ports.push(`.${i.name}(${i.name})`); nets.add(i.name) }
    for (const c of d.cells) {
      if (!d.external.has(c.name)) continue
      const n = net(mod, c.name)
      ports.push(`.${c.name}(${n})`); nets.add(n)
      if (c.oe) { ports.push(`.${c.name}_OE(${n}_OE)`); nets.add(`${n}_OE`) }
    }
    const lines: string[] = []
    let cur = "   "
    for (const p of ports) {
      if ((cur + " " + p + ",").length > 92) { lines.push(cur); cur = "   " }
      cur += " " + p + ","
    }
    lines.push(cur.replace(/,$/, ""))
    return `  ${mod} ${inst} (\n${lines.join("\n")}\n  );\n`
  })
  const wires = [...nets].filter((n) => !BOARD.has(n)).sort()
  return [
    BEGIN,
    wrap("  wire ", wires, ", ", ";"),
    "",
    "  // ---- the four parts: generated port maps --------------------------------",
    ...insts,
  ].join("\n") + "\n"
}

export const rewrite = (file: string, parts: [string, string, Merged][]) => {
  const src = readFileSync(file, "utf8")
  const a = src.indexOf(BEGIN), b = src.indexOf(END)
  if (a < 0 || b < 0 || b < a) throw new Error(`${file}: the port-map markers are missing`)
  const next = src.slice(0, a) + portmap(parts) + src.slice(b)
  if (next !== src) writeFileSync(file, next)
}
