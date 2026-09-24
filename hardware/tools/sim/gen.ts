/* Emit every programmable part as Verilog, into its own card's sim/ directory
 * (hardware/<card>/sim/). `make -C hardware check-sim` compiles and runs them. */

import { mkdirSync, writeFileSync } from "fs"
import { dirname, join } from "path"
import { fileURLToPath } from "url"
import { vaddrCpld, vctrlCpld } from "../../archive/video/logic/video.cpld"
import { vsupCpld } from "../../archive/video/logic/vsup.cpld"
import { rfaDesign } from "../../archive/video/logic/regfile.jedec"
import { vlenDesign } from "../../archive/video/logic/vlen.jedec"
import { pxselDesign } from "../../archive/video/logic/pxsel.jedec"
import { audioCpld } from "../../audio/logic/audio.cpld"
import { aseqCpld } from "../../audio/logic/aseq.cpld"
import { u9Design } from "../../mainboard/logic/u9.jedec"
import { u10Design } from "../../mainboard/logic/u10.jedec"
import { v3dot } from "../../video3/logic/v3dot.cpld"
import { v3scan } from "../../video3/logic/v3scan.cpld"
import { v3ptr } from "../../video3/logic/v3ptr.cpld"
import { v3host } from "../../video3/logic/v3host.cpld"
import { v3laneDesign } from "../../video3/logic/v3lane.jedec"
import { sdbusDesign } from "../../storage/logic/sdbus.jedec"
import { sdengDesign } from "../../storage/logic/sdeng.jedec"
import { fromDesign, fromMerged, toVerilog } from "./emit"
import { rewrite, rewriteTb } from "../../video3/sim/v3portmap"

const here = dirname(fileURLToPath(import.meta.url))
const HW = join(here, "..", "..")
/* which card's sim/ each generated part lands in */
const CARD: Record<string, string> = {
  vaddr: "archive/video", vctrl: "archive/video", vsup: "archive/video",
  rfa: "archive/video", vlen: "archive/video", pxsel: "archive/video",
  audio: "audio", aseq: "audio", u9: "mainboard", u10: "mainboard",
  v3dot: "video3", v3scan: "video3", v3ptr: "video3", v3host: "video3", v3lane: "video3",
  sdbus: "storage", sdeng: "storage",
}
const simDir = (card: string) => join(HW, card, "sim")

const write = (name: string, text: string) => {
  const dir = simDir(CARD[name])
  mkdirSync(dir, { recursive: true })
  writeFileSync(join(dir, `${name}.v`), text)
  console.log(`ok    ${CARD[name]}/sim/${name}.v  ${text.split("\n").length} lines`)
}

write("vaddr", toVerilog(fromMerged(vaddrCpld)))
write("vctrl", toVerilog(fromMerged(vctrlCpld)))
write("vsup", toVerilog(fromMerged(vsupCpld)))
write("rfa", toVerilog(fromDesign(rfaDesign)))
write("vlen", toVerilog(fromDesign(vlenDesign)))
write("pxsel", toVerilog(fromDesign(pxselDesign)))
write("audio", toVerilog(fromMerged(audioCpld)))
write("aseq", toVerilog(fromMerged(aseqCpld)))
write("u9", toVerilog(fromDesign(u9Design)))
write("u10", toVerilog(fromDesign(u10Design)))

/* ⭐ video3's four parts (hardware/video3/docs/partition.md).  The same `Cell` term
 * lists the fitter compiles, so a testbench runs the DESIGN and not a second
 * description of it - which is the whole reason emit.ts exists. */
write("v3dot", toVerilog(fromMerged(v3dot)))
write("v3scan", toVerilog(fromMerged(v3scan)))
write("v3ptr", toVerilog(fromMerged(v3ptr)))
write("v3host", toVerilog(fromMerged(v3host)))
write("v3lane", toVerilog(fromDesign(v3laneDesign)))

/* ⭐ storage's two GAL22V10s (sdcard.md §8, and storage/logic/census.ts for why
 * it is two and which two). storage_card.v is hand-written: it is the six
 * discrete packages around them. */
write("sdbus", toVerilog(fromDesign(sdbusDesign)))
write("sdeng", toVerilog(fromDesign(sdengDesign)))
/* ⭐ and the board's wiring between them, from the same four definitions */
rewrite(join(simDir("video3"), "video3_card.v"), [
  ["v3dot", "u_dot", v3dot], ["v3scan", "u_scan", v3scan],
  ["v3ptr", "u_ptr", v3ptr], ["v3host", "u_host", v3host],
  ["v3lane", "u_lane", { ...v3laneDesign, external: new Set(v3laneDesign.cells.map((c) => c.name)) }],
])
rewriteTb(join(simDir("video3"), "v3dot_tb.sv"), "v3dot", v3dot)
