/* Skyline placement, bottom-left, with the rear connectors and the gold
 * fingers pre-loaded as obstacles.
 *
 * WHY NOT ROWS. The first version of this packed parts into rows banked by
 * height, and it reported the video card as unplaceable at 64 % area — a row
 * is as tall as its tallest member, so a 33 mm PLCC in a band of 7.6 mm DIPs
 * wastes the difference across the whole band. A skyline lets a pair of 0.3"
 * DIPs stack beside a PLCC, which is what a through-hole board actually does,
 * and it is the difference between a study that measures the design and one
 * that measures the packer.
 */
import { type CardSpec, type Kind, BOARD_H, FINGER_W, FINGER_H } from "./parts"

/** 0.1" of clearance on every side — the tightest a hand-routed board gets. */
export const END = 2.54
export const ROW = 2.54
const STEP = 0.5

export interface Placed {
  x: number; y: number; w: number; h: number
  label: string; short: string; kind: Kind; reserved: boolean
}
export interface Packing {
  placed: Placed[]; fingerX: number; skyline: number
  over: string[]; courtyard: number; placeable: number
}

/** The rear connectors stack down the right-hand edge, in declaration order. */
const rearBlocks = (c: CardSpec, W: number): Placed[] => {
  let y = 3
  return c.rear.map((r) => {
    const b: Placed = { x: W - r.w - 3, y, w: r.w, h: r.h, label: r.label,
                        short: r.label, kind: r.kind, reserved: true }
    y += r.h + 3.5
    return b
  })
}

export const pack = (c: CardSpec, W = c.length): Packing => {
  const fingerX = W > FINGER_W + 24 ? W - 18.6 - FINGER_W : (W - FINGER_W) / 2
  const placed = rearBlocks(c, W)

  const x0 = 3, x1 = W - 3
  const n = Math.floor((x1 - x0) / STEP)
  const sky = new Array<number>(n).fill(3)
  const lim = new Array<number>(n).fill(BOARD_H - 3)
  for (let i = 0; i < n; i++) {
    const cx = x0 + i * STEP
    if (cx >= fingerX - 2 && cx <= fingerX + FINGER_W + 2) lim[i] = BOARD_H - FINGER_H - 2
    for (const r of placed) {
      if (cx >= r.x - 1.5 && cx <= r.x + r.w + 1.5) sky[i] = Math.max(sky[i], r.y + r.h + 2)
    }
  }

  /* Largest first: a big part placed late has nowhere left that fits it. */
  const rem = c.parts.flatMap((p) => Array.from({ length: p.qty }, () => p))
    .sort((a, b) => (b.w * b.l - a.w * a.l) || (b.w - a.w))

  const over: string[] = []
  for (const p of rem) {
    const w = p.l + END, h = p.w + ROW
    const span = Math.max(1, Math.round(w / STEP))
    let best: { top: number; i: number } | null = null
    for (let i = 0; i + span <= n; i++) {
      let top = 0, cap = Infinity
      for (let j = i; j < i + span; j++) { top = Math.max(top, sky[j]); cap = Math.min(cap, lim[j]) }
      if (top + h > cap) continue
      if (best === null || top < best.top) best = { top, i }
    }
    if (best === null) { over.push(p.label); continue }
    placed.push({ x: x0 + best.i * STEP, y: best.top, w: p.l, h: p.w,
                  label: p.label, short: p.short, kind: p.kind, reserved: false })
    for (let j = best.i; j < best.i + span; j++) sky[j] = best.top + h
  }

  const courtyard = c.parts.reduce((a, p) => a + p.qty * (p.l + END) * (p.w + ROW), 0) / 100
  const placeable = (W * BOARD_H - FINGER_W * FINGER_H
    - c.rear.reduce((a, r) => a + r.w * r.h, 0)) / 100
  return { placed, fingerX, skyline: Math.max(...sky), over,
           courtyard: Math.round(courtyard * 10) / 10,
           placeable: Math.round(placeable * 10) / 10 }
}

/** Does every part land on a board this long, with the skyline inside it? */
export const fits = (c: CardSpec, W: number): boolean => {
  const r = pack(c, W)
  return r.over.length === 0 && r.skyline <= BOARD_H - 3
}
