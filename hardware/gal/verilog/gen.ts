/* Emit the video card's two CPLDs and its one GAL as Verilog, into
 * hardware/gal/verilog/. `npm run check:video` compiles and runs them. */

import { mkdirSync, writeFileSync } from "fs"
import { dirname, join } from "path"
import { fileURLToPath } from "url"
import { vaddrCpld, vctrlCpld } from "../video.cpld"
import { vsupCpld } from "../vsup.cpld"
import { rfaDesign } from "../regfile.jedec"
import { vlenDesign } from "../vlen.jedec"
import { pxselDesign } from "../pxsel.jedec"
import { audioCpld } from "../audio.cpld"
import { aseqCpld } from "../aseq.cpld"
import { u9Design } from "../u9.jedec"
import { u10Design } from "../u10.jedec"
import { v3dot } from "../video3/v3dot.cpld"
import { v3scan } from "../video3/v3scan.cpld"
import { v3ptr } from "../video3/v3ptr.cpld"
import { v3host } from "../video3/v3host.cpld"
import { fromDesign, fromMerged, toVerilog } from "./emit"
import { rewrite } from "./v3portmap"

const here = dirname(fileURLToPath(import.meta.url))
mkdirSync(here, { recursive: true })

const write = (name: string, text: string) => {
  writeFileSync(join(here, `${name}.v`), text)
  console.log(`ok    ${name}.v  ${text.split("\n").length} lines`)
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

/* ⭐ video3's four parts (video3/docs/partition.md).  The same `Cell` term
 * lists the fitter compiles, so a testbench runs the DESIGN and not a second
 * description of it - which is the whole reason emit.ts exists. */
write("v3dot", toVerilog(fromMerged(v3dot)))
write("v3scan", toVerilog(fromMerged(v3scan)))
write("v3ptr", toVerilog(fromMerged(v3ptr)))
write("v3host", toVerilog(fromMerged(v3host)))
/* ⭐ and the board's wiring between them, from the same four definitions */
rewrite(join(here, "video3_card.v"), [
  ["v3dot", "u_dot", v3dot], ["v3scan", "u_scan", v3scan],
  ["v3ptr", "u_ptr", v3ptr], ["v3host", "u_host", v3host],
])
