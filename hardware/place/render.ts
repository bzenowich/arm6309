/* Renders the placement study to dist/boards.html.
 *
 * place/page.html is the prose with three placeholders; everything numeric in
 * it comes from parts.ts through pack.ts, so a card that grows a package
 * redraws rather than going stale. The stylesheet is place/style.css and is
 * inlined, because the page is published as a self-contained artifact.
 *
 *   npm run render:boards
 */
import { readFileSync, writeFileSync, mkdirSync } from "node:fs"
import { join } from "node:path"

import { CARDS, icCount } from "./parts"
import { pack } from "./pack"
import { cardSvg, mbSvg } from "./svg"

const here = new URL(".", import.meta.url).pathname
const read = (f: string) => readFileSync(join(here, f), "utf8")

const ORDER = ["video", "audio", "net", "storage", "io"] as const
const WINDOW: Record<string, string> = {
  video: "$FF60&ndash;$FF7F", audio: "$FF40&ndash;$FF4F", net: "$FF5C&ndash;$FF5F",
  storage: "$FF58&ndash;$FF5B", io: "$FF50&ndash;$FF57",
}
const BIGGEST: Record<string, string> = {
  video: "2 &times; PLCC-84 &middot; 4 &times; DIP-32 &middot; 3 &times; DIP-28",
  audio: "PLCC-84 &middot; DIP-32 &middot; 4 &times; AD7528",
  net: "2 &times; PLCC-84 &middot; DIP-28 &middot; DIP-24 wide",
  storage: "DIP-24 wide &middot; 2 &times; GAL22V10 &middot; 3 &times; 74HC157",
  io: "DIP-28 ACIA &middot; 2 &times; GAL22V10 &middot; MAX232 &middot; 2 &times; 74HC595",
}

const used = (k: string) => {
  const r = pack(CARDS[k])
  return Math.round((100 * r.courtyard) / r.placeable)
}

const cells = ORDER.map((k) => {
  const c = CARDS[k], u = used(k)
  return `<button class="cell" type="button" data-board="${k}">
  <div class="head"><h3>${c.title}</h3><span class="pct">${c.length / 10} cm &middot; ${icCount(c)} IC &middot; ${u}%</span></div>
  <div class="art">${cardSvg(c)}</div>
  <div class="foot"><div class="bar"><i style="width:${u}%"></i></div>
  <span class="zoom">Click to enlarge</span></div>
</button>`
}).join("\n")

const rows = ORDER.map((k) => {
  const c = CARDS[k], r = pack(c)
  return `<tr><td>${c.title}</td><td class="n">${c.length / 10} cm</td>` +
    `<td class="n">${icCount(c)}</td><td class="n">${r.courtyard} cm&sup2;</td>` +
    `<td class="n">${r.placeable} cm&sup2;</td><td class="n">${used(k)}%</td>` +
    `<td class="mono">${WINDOW[k]}</td><td class="mono">${BIGGEST[k]}</td></tr>`
}).join("\n")

const envelopes = [
  ...ORDER.map((k) => ({ len: CARDS[k].length, label: `${CARDS[k].title.toLowerCase()} ${CARDS[k].length / 10}` })),
  { len: 120, label: "spare" },
]
const mb = `<button class="cell" type="button" data-board="mb" style="max-width:100%">
  <div class="head"><h3>Motherboard</h3><span class="pct">9 IC populated &middot; 4 reserved &middot; 272 &times; 190 mm</span></div>
  <div class="art">${mbSvg(envelopes)}</div>
  <div class="foot"><span class="zoom">Click to enlarge</span></div>
</button>`

const meta = Object.fromEntries([
  ...ORDER.map((k) => {
    const c = CARDS[k], r = pack(c)
    return [k, `${c.length / 10} × 10 cm · ${icCount(c)} ICs · ${r.courtyard} cm² courtyard ` +
      `of ${r.placeable} cm² placeable · ${c.note}`]
  }),
  ["mb", "9 ICs populated + 4 reserved footprints · six 72-pin sockets · 272 × 190 mm · derived, not specified"],
])
const titles = Object.fromEntries([
  ...ORDER.map((k) => [k, `${CARDS[k].title} card — ${CARDS[k].length} × 100 mm`]),
  ["mb", "Motherboard — 272 × 190 mm"],
])

const page = read("page.html")
  .replace("{{CELLS}}", cells).replace("{{MB}}", mb).replace("{{ROWS}}", rows)

const html = `<title>Boards, To Scale</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap">
<style>
${read("style.css")}</style>
${page}
<dialog class="lb" id="lb" aria-label="Board detail">
  <div class="panel">
    <div class="bar2"><h3 id="lbT">Board</h3><span class="meta" id="lbM"></span>
      <button class="x" type="button" id="lbX">Close &#183; Esc</button></div>
    <div id="lbB"></div>
  </div>
</dialog>

<script>
const META = ${JSON.stringify(meta)};
const TITLE = ${JSON.stringify(titles)};
const lb = document.getElementById('lb'), lbB = document.getElementById('lbB'),
      lbT = document.getElementById('lbT'), lbM = document.getElementById('lbM');
document.querySelectorAll('.cell').forEach(function (btn) {
  btn.addEventListener('click', function () {
    const k = btn.dataset.board;
    lbB.innerHTML = btn.querySelector('svg').outerHTML;
    lbT.textContent = TITLE[k]; lbM.textContent = META[k];
    lb.showModal();
  });
});
document.getElementById('lbX').addEventListener('click', function () { lb.close(); });
lb.addEventListener('click', function (e) { if (e.target === lb) lb.close(); });
</script>
`

mkdirSync(join(here, "../dist"), { recursive: true })
writeFileSync(join(here, "../dist/boards.html"), html)
console.log(`wrote dist/boards.html — ${ORDER.length} cards + motherboard, ${html.length} bytes`)
