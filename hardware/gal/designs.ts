/* Every GAL22V10 design in the machine, in one list, so that the cost probes
 * can walk them without importing a script that writes files as a side effect.
 */

import type { Design } from "./jedec/assemble"
import { mmuDesign } from "./mmu.jedec"
import { clkdecDesign } from "./clkdec.jedec"
import { u9Design } from "./u9.jedec"
import { u10Design } from "./u10.jedec"
import { hgenDesign, vgenDesign, vdecDesign } from "./sync.jedec"
import { hadrDesign, vadrDesign } from "./scan.jedec"
import { arbDesign, wcolDesign, wrowDesign } from "./access.jedec"
import { seqphDesign } from "./seqph.jedec"
import { seqctlDesign } from "./seqctl.jedec"
import { vlenDesign } from "./vlen.jedec"
import { rfaDesign } from "./regfile.jedec"
import { aseqDesign, adecDesign, admatDesign, aintenaDesign, apendDesign } from "./audio.jedec"

export const ALL: Design[] = [
  mmuDesign, clkdecDesign, u9Design, u10Design,
  hgenDesign, vgenDesign, vdecDesign,
  hadrDesign, vadrDesign,
  arbDesign, wcolDesign, wrowDesign,
  seqphDesign, seqctlDesign, vlenDesign, rfaDesign,
  aseqDesign, adecDesign, admatDesign, aintenaDesign, apendDesign,
]

