/* The board drawings. Millimetres are the SVG's own units, so the viewBox is
 * the board plus a margin and everything inside is life-size. */
import { type CardSpec, type Kind, BOARD_H, FINGER_W, FINGER_H } from "./parts"
import { pack } from "./pack"

const FILL: Record<Kind, string> = {
  pld: "var(--k-pld)", mem: "var(--k-mem)", bus: "var(--k-bus)",
  glue: "var(--k-glue)", analog: "var(--k-analog)", clk: "var(--k-clk)",
  conn: "var(--k-conn)",
}
export const esc = (t: string) => t.replace(/&/g, "&amp;").replace(/</g, "&lt;")

const scaleBar = (x: number, y: number) => [
  `<line class="sc" x1="${x}" y1="${y}" x2="${x + 50}" y2="${y}"/>`,
  ...[0, 25, 50].map((t) =>
    `<line class="sc" x1="${x + t}" y1="${y - 1.7}" x2="${x + t}" y2="${y + 1.7}"/>`),
  `<text class="dim" x="${x + 53}" y="${y + 1.6}">50 mm</text>`,
]

export const cardSvg = (c: CardSpec, pad = 14): string => {
  const W = c.length
  const r = pack(c)
  const o: string[] = [
    `<svg viewBox="0 0 ${W + 2 * pad} ${BOARD_H + 2 * pad}" role="img" ` +
    `aria-label="${esc(c.title)} card, ${W} by ${BOARD_H} mm">`,
    `<rect class="sub" x="${pad}" y="${pad}" width="${W}" height="${BOARD_H}" rx="2"/>`,
  ]
  const fx = pad + r.fingerX, fy = pad + BOARD_H - FINGER_H
  o.push(`<rect class="edge" x="${fx.toFixed(1)}" y="${fy}" width="${FINGER_W}" height="${FINGER_H}"/>`)
  for (let i = 0; i < 36; i++) {
    o.push(`<rect class="fing" x="${(fx + 1.2 + i * 2.54).toFixed(2)}" y="${fy + 1.5}" ` +
      `width="1.5" height="${FINGER_H - 3}"/>`)
  }
  o.push(`<text class="dim" x="${(fx + FINGER_W / 2).toFixed(1)}" y="${(fy - 1.8).toFixed(1)}" ` +
    `text-anchor="middle">72-pin edge &#183; 91.4 mm</text>`)

  for (const p of r.placed) {
    const x = pad + p.x, y = pad + p.y
    const cls = p.reserved ? "resv" : "pk"
    o.push(`<rect class="${cls}" x="${x.toFixed(1)}" y="${y.toFixed(1)}" ` +
      `width="${p.w.toFixed(1)}" height="${p.h.toFixed(1)}" rx="0.7" style="fill:${FILL[p.kind]}"/>`)
    if (!p.reserved) {
      o.push(`<circle class="p1" cx="${(x + 1.6).toFixed(1)}" cy="${(y + 1.6).toFixed(1)}" r="0.65"/>`)
    }
    const fs = p.reserved ? 2.9 : p.h > 12 ? 3.0 : 2.7
    if (p.w > 9) {
      o.push(`<text class="${p.reserved ? "rl" : "pl"}" style="font-size:${fs}px" ` +
        `x="${(x + p.w / 2).toFixed(1)}" y="${(y + p.h / 2 + fs * 0.36).toFixed(1)}" ` +
        `text-anchor="middle">${esc(p.reserved ? p.label : p.short)}</text>`)
    }
  }
  o.push(...scaleBar(pad, pad + BOARD_H + 7.5))
  o.push(`<text class="dim" x="${pad + W / 2}" y="${pad - 4}" text-anchor="middle">${W} mm</text>`)
  o.push(`<text class="dim" x="${pad - 4}" y="${pad + BOARD_H / 2}" text-anchor="middle" ` +
    `transform="rotate(-90 ${pad - 4} ${pad + BOARD_H / 2})">${BOARD_H} mm</text>`)
  o.push("</svg>")
  return o.join("\n")
}

/* ---- the motherboard, placed by hand because it has no packing problem ---- */
export const MB = { W: 272, H: 190, pad: 15, slotL: 91.4, slotW: 10.16, pitch: 20.32, sx: 168, sy: 10 }

/** x, y, w, h, label, kind, reserved. Overlap-checked by place.check.ts. */
export const MB_PARTS: [number, number, number, number, string, Kind, boolean][] = [
  [12, 140, 40.6, 15.24, "U8 512Kx8", "mem", false],
  [56, 140, 40.6, 15.24, "RAM2 512K", "mem", true],
  [100, 140, 40.6, 15.24, "RAM3 512K", "mem", true],
  [144, 140, 40.6, 15.24, "RAM4 512K", "mem", true],
  [190, 140, 20.3, 7.62, "U9 139", "bus", true],
  [12, 162, 50.8, 15.24, "J0 6309 socket", "pld", false],
  [68, 162, 30.5, 15.24, "U1 map SRAM", "mem", false],
  [104, 162, 30.5, 7.62, "U3 GAL22V10", "pld", false],
  [104, 172, 30.5, 7.62, "U6 GAL22V10 E/Q", "pld", false],
  [139, 162, 25.4, 7.62, "U4 245", "bus", false],
  [139, 172, 25.4, 7.62, "U2 574", "bus", false],
  [169, 162, 20.3, 7.62, "U5 157", "bus", false],
  [169, 172, 10.2, 7.62, "OSC1", "clk", false],
  [184, 172, 3.0, 3.0, "U7", "analog", false],
  [196, 164, 32.0, 12.0, "power in", "conn", false],
]

export const mbSvg = (envelopes: { len: number; label: string }[]): string => {
  const { W, H, pad, slotL, slotW, pitch, sx, sy } = MB
  const o = [`<svg viewBox="0 0 ${W + 2 * pad} ${H + 2 * pad}" role="img" ` +
    `aria-label="Motherboard, ${W} by ${H} mm">`,
    `<rect class="sub" x="${pad}" y="${pad}" width="${W}" height="${H}" rx="2"/>`]
  envelopes.forEach((e, i) => {
    const y = sy + i * pitch, cx = sx + slotL - e.len
    o.push(`<rect class="env" x="${(pad + cx).toFixed(1)}" y="${pad + y - 3}" ` +
      `width="${e.len}" height="${pitch - 1.5}" rx="1"/>`)
    o.push(`<text class="dim" style="font-size:2.9px" x="${(pad + cx + 3).toFixed(1)}" ` +
      `y="${pad + y + 5.6}">${esc(e.label)}</text>`)
    o.push(`<rect class="slot" x="${pad + sx}" y="${pad + y}" width="${slotL}" height="${slotW}" rx="1"/>`)
    for (let j = 0; j < 36; j++) {
      o.push(`<rect class="fing" x="${(pad + sx + 1.4 + j * 2.54).toFixed(2)}" ` +
        `y="${pad + y + 1.5}" width="1.4" height="${slotW - 3}"/>`)
    }
    o.push(`<text class="pl" style="font-size:3.2px" x="${pad + sx + slotL + 3.5}" ` +
      `y="${pad + y + slotW / 2 + 1.3}">J${i + 1}</text>`)
  })
  o.push(`<text class="dim" style="font-size:3.0px" x="${pad + 12}" y="${pad + 137}">` +
    `system RAM bank &#8212; 1 populated, 3 reserved</text>`)
  for (const [x, y, w, h, lab, kind, rsv] of MB_PARTS) {
    o.push(`<rect class="${rsv ? "resv" : "pk"}" x="${pad + x}" y="${pad + y}" ` +
      `width="${w}" height="${h}" rx="0.7" style="fill:${FILL[kind]}"/>`)
    if (!rsv) o.push(`<circle class="p1" cx="${pad + x + 1.6}" cy="${pad + y + 1.6}" r="0.65"/>`)
    if (w > 12) {
      o.push(`<text class="${rsv ? "rl" : "pl"}" style="font-size:3.0px" ` +
        `x="${pad + x + w / 2}" y="${pad + y + h / 2 + 1.2}" text-anchor="middle">${esc(lab)}</text>`)
    }
  }
  o.push(`<text class="dim" x="${pad + W / 2}" y="${pad - 4}" text-anchor="middle">` +
    `${W} mm &#8212; set by the longest card, not by any document</text>`)
  o.push(`<text class="dim" x="${pad - 4}" y="${pad + H / 2}" text-anchor="middle" ` +
    `transform="rotate(-90 ${pad - 4} ${pad + H / 2})">${H} mm</text>`)
  o.push(...scaleBar(pad, pad + H + 8))
  o.push("</svg>")
  return o.join("\n")
}
