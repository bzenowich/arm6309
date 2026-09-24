/* Every GAL22V10 design in the machine, in one list, so that the cost probes
 * can walk them without importing a script that writes files as a side effect.
 *
 * ⭐ THE `video` CARD LEFT THIS LIST ON 2026-09-20, when `video3` became the
 * machine's video card and `video/` was archived (`hardware/archive/README.md`,
 * `docs/history.md`). Twelve designs went with it - `hgen`, `vgen`, `vdec`,
 * `hadr`, `vadr`, `arb`, `wcol`, `wrow`, `seqph`, `seqctl`, `vlen` and `rfa`.
 *
 * ⚠ THEIR SOURCES ARE STILL HERE, in `<card>/logic/*.jedec.ts`, and that is deliberate:
 * `verilog/gen.ts` emits `vaddr.v`, `vctrl.v`, `vsup.v`, `rfa.v`, `vlen.v` and
 * `pxsel.v` from these same term lists, and `machine_tb`/`demo_tb` still
 * instantiate the card. What changed is that nothing CHECKS them any more -
 * they are an archived design carried for the benches that have not been
 * retargeted yet, not a part of the machine. See `hardware/archive/README.md`.
 */

import type { Design } from "./jedec/assemble"
import { mmuDesign } from "../../mainboard/logic/mmu.jedec"
import { clkdecDesign } from "../../mainboard/logic/clkdec.jedec"
import { u9Design } from "../../mainboard/logic/u9.jedec"
import { u10Design } from "../../mainboard/logic/u10.jedec"
import { aseqDesign, adecDesign, admatDesign, aintenaDesign, apendDesign } from "../../audio/logic/audio.jedec"
import { v3laneDesign } from "../../video3/logic/v3lane.jedec"
import { sdbusDesign } from "../../storage/logic/sdbus.jedec"
import { sdengDesign } from "../../storage/logic/sdeng.jedec"

export const ALL: Design[] = [
  mmuDesign, clkdecDesign, u9Design, u10Design,
  aseqDesign, adecDesign, admatDesign, aintenaDesign, apendDesign,
  v3laneDesign,
  sdbusDesign, sdengDesign,
]

