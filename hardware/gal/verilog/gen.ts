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
import { fromDesign, fromMerged, toVerilog } from "./emit"

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
