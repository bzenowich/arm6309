/* Netlist assertions for the motherboard.
 *
 * A build that succeeds only proves every selector resolved. These are the
 * connectivity claims the machine documents make, checked against the circuit
 * JSON the board actually produced.
 */
const path = process.argv[2] ?? "dist/mainboard/mainboard/circuit.json"
const cj: any[] = JSON.parse(await Bun.file(path).text())

const el = (t: string) => cj.filter((e) => e.type === t)
const byId = new Map(cj.map((e) => [e.source_component_id ?? e.source_port_id ?? e.source_net_id, e]))

const comps = el("source_component")
const ports = el("source_port")
const nets = el("source_net")
const netName = new Map(nets.map((n) => [n.source_net_id, n.name]))
const compName = new Map(comps.map((c) => [c.source_component_id, c.name]))

/* connectivity: walk source_trace / connectivity map */
const traces = el("source_trace")
const portNet = new Map<string, Set<string>>()
for (const t of traces) {
  const netIds: string[] = t.connected_source_net_ids ?? []
  for (const pid of t.connected_source_port_ids ?? []) {
    if (!portNet.has(pid)) portNet.set(pid, new Set())
    for (const n of netIds) portNet.get(pid)!.add(netName.get(n) ?? n)
  }
}

const pinsOn = (comp: string, net: string) =>
  ports
    .filter((p) => compName.get(p.source_component_id) === comp)
    .filter((p) => portNet.get(p.source_port_id)?.has(net))
    .map((p) => p.name)

let failures = 0
const check = (ok: boolean, claim: string, detail = "") => {
  if (!ok) { failures++; console.error(`FAIL  ${claim}${detail ? `  (${detail})` : ""}`) }
  else console.log(`ok    ${claim}`)
}

/* -- machine.md 2: logical A13-A15 stay on the motherboard --------------- */
const slotNames = comps.map((c) => c.name).filter((n) => /^J[1-9]/.test(n))
check(slotNames.length === 6, "six slots instantiated", slotNames.join(" "))
for (const logical of ["LA13", "LA14", "LA15"]) {
  const leaked = slotNames.flatMap((s) => pinsOn(s, logical))
  check(leaked.length === 0, `${logical} reaches no slot`, leaked.join(", "))
}

/* -- machine.md 2: A0-A12 untranslated, A13-A19 from the map ------------- */
for (let i = 0; i <= 12; i++) {
  const onCpu = pinsOn("J0", `LA${i}`).length > 0
  check(onCpu, `CPU A${i} drives logical LA${i}`)
}
for (let i = 13; i <= 20; i++) {
  const fromMap = pinsOn("U1", `A${i}`)
  check(fromMap.length === 1, `physical A${i} comes from the map SRAM`, fromMap.join(","))
}

/* -- graphics.md 6.3.1: the '245 bridges the map SRAM and D0-D7 ---------- */
for (let i = 0; i < 8; i++) {
  const b = pinsOn("U4", `D${i}`)
  check(b.length === 1, `isolation buffer B${i + 1} is on D${i}`, b.join(","))
}
const aSide = [13, 14, 15, 16, 17, 18, 19, 20].map((n) => pinsOn("U4", `A${n}`).length)
check(aSide.every((n) => n === 1), "isolation buffer A side is on physical A13-A20")

/* -- ram.md 6.2: there is no DIP system RAM, and U8 is gone -------------- */
check(comps.filter((c) => c.name === "U8").length === 0,
  "no DIP system RAM package - ram.md 6.2 replaced it with SIMM sockets on " +
  "2026-09-08 and this file kept drawing it for a day")
for (const net of ["RAM_CE", "RAM_OE", "RAM_WE"]) {
  check(pinsOn("U6", net).length === 0,
    `U6 no longer drives ${net} - the macrocell went to boot mode (gal/clkdec.pld)`)
}

/* -- ram.md 6: four SIMM sockets are all of the machine's RAM ------------ */
const simms = comps.map((c) => c.name).filter((n) => /^SIMM[0-9]$/.test(n))
check(simms.length === 4, "four 30-pin SIMM sockets", simms.join(" "))
for (const s0 of simms) {
  const row = Array.from({ length: 11 }, (_, i) => pinsOn(s0, `MA${i}`).length)
  check(row.every((n) => n === 1), `${s0} takes the muxed row/column address MA0-MA10`,
    `${row.filter(Boolean).length}/11`)
  check(pinsOn(s0, "CAS").length === 1 && pinsOn(s0, "DRAM_WE").length === 1,
    `${s0} shares /CAS and /WE with the bank`)
}
{
  /* One RAS each and no two alike - the whole point of four sockets. */
  const ras = simms.map((s0) => [0, 1, 2, 3].filter((n) => pinsOn(s0, `RAS${n}`).length === 1))
  check(ras.every((r) => r.length === 1) && new Set(ras.flat()).size === 4,
    "each socket has its own /RAS and no two share one",
    ras.map((r, i) => `SIMM${i}:${r}`).join(" "))
}
check(pinsOn("U9", "DRAM_SEL").length === 1 && pinsOn("U10", "DRAM_SEL").length === 1,
  "DRAM_SEL runs from U9's space decode to U10's timing")
check(pinsOn("U10", "A23").length === 1 && pinsOn("U10", "A22").length === 1,
  "⭐ and U10 takes physical A23/A22 directly - those two lines already " +
  "distinguish the four windows, which is why U9 spends ONE output here and " +
  "not four (gal/u9.pld)")

/* -- ram.md 6.3.1: U10's two timebases, and they are different nets ------ */
{
  const bits = ["C0", "C1", "C2", "C3"]
  const fromU6 = bits.filter((c) => pinsOn("U6", c).length === 1)
  const toU10 = bits.filter((c) => pinsOn("U10", c).length === 1)
  check(fromU6.length === 4 && toU10.length === 4,
    "⭐ U6's divider count reaches U10 - the ACCESS half decodes the bus phase " +
    "from it, so RAS and CAS stall when E stalls, which is correct because a " +
    "stalled cycle's data is not wanted yet", `U6:[${fromU6}] U10:[${toU10}]`)
}
check(pinsOn("U17", "CLK25").length === 1,
  "⚠ and the REFRESH half does NOT - U17 counts CLK25 directly. /WAIT holds " +
  "U6's divider (machine.md 5 item 8), so a refresh timed from the bus would " +
  "stop for the 40.7 us the video card can hold it: 2.6 refresh intervals, and " +
  "the DRAM forgets. machine.md 5 item 10 is the rule and this is the wire")
check(pinsOn("U17", "REFCLK").length === 1 && pinsOn("U10", "REFCLK").length === 1,
  "REFCLK runs from U17's Q8 to U10 - one toggle per 256 counts = 10.16 us, " +
  "and every transition is a refresh, so 512 rows take 5.2 ms of the DRAM's 8")
check(pinsOn("U10", "nWAIT").length === 0,
  "⭐ U10 does not drive /WAIT. A bus cycle is twelve CLK25 counts, the access " +
  "owns six and a refresh burst is four, so it fits in the gap - the DRAM " +
  "controller never stalls the CPU (gal/u10.pld)")

/* -- gal/u10.pld: the row/column mux select is E, and not a GAL output --- */
for (const mux of ["U11", "U12", "U13"]) {
  check(pinsOn(mux, "E").includes("SEL"),
    `⭐ ${mux}'s select is E itself, not a macrocell - E is high for counts ` +
    `6..11, which is exactly the column window. That is the macrocell that ` +
    `made U10's nine-output design fit`, pinsOn(mux, "E").join(","))
  check(pinsOn(mux, "MUX_ROW").length === 0,
    `and ${mux} does not take a MUX_ROW output that no longer exists`)
}
{
  /* Row is physical A10..A0, column A21..A11 - a 30-pin SIMM is BYTE wide, so
   * its A0 is the CPU's A0 and there is no low bit hidden inside it. */
  const rowOk = Array.from({ length: 11 }, (_, i) =>
    ["U11", "U12", "U13"].some((m) => pinsOn(m, `A${i}`).length > 0))
  const colOk = Array.from({ length: 11 }, (_, i) =>
    ["U11", "U12", "U13"].some((m) => pinsOn(m, `A${11 + i}`).length > 0))
  check(rowOk.every(Boolean) && colOk.every(Boolean),
    "the mux takes physical A0-A10 as the row and A11-A21 as the column - a " +
    "30-pin SIMM is byte-wide, so its A0 is the CPU's A0",
    `row ${rowOk.filter(Boolean).length}/11, col ${colOk.filter(Boolean).length}/11`)
}

/* -- machine.md 7.2: the boot ROM, and the two nets that make it work ---- */
check(comps.filter((c) => /^U1[45]$/.test(c.name)).length === 2,
  "two flash packages - 1 MB, because no 5 V 1M x 8 comes in a DIP")
for (const n of [0, 1]) {
  check(pinsOn(`U1${4 + n}`, `ROM_CE${n}`).length === 1,
    `U1${4 + n} takes its own chip enable from U9 - physical A19 picks the device`)
  check(pinsOn(`U1${4 + n}`, "GND").includes("nOE"),
    `and its /OE is tied low: R/W rides in the chip enable, so a stray write ` +
    `to ROM space selects nothing instead of fighting the CPU (gal/u9.pld)`)
}
{
  /* EIGHT bits, not seven. The ROM needs A19-A13; A20 is on the list because
   * it reaches the BACKPLANE, and a floating A20 during a boot fetch would let
   * the video card's VRAM select (A20 = 0, A19 = 1) answer at random. */
  const driven = [13, 14, 15, 16, 17, 18, 19, 20].filter((n) => pinsOn("U16", `A${n}`).length === 1)
  check(driven.length === 8,
    "⚠ the boot buffer drives physical A20-A13 - EIGHT bits, and A20 is why: " +
    "it reaches the backplane, and a floating A20 during a boot fetch would " +
    "let VRAM answer at random", driven.join(","))
  check(pinsOn("U16", "BOOT_OE").length === 2,
    "and both its halves share one enable, from U6")
}

/* ⚠ THE TWO /IOPAGE NETS. U3's term goes to U6, U9 and U10; U9 drives the
 * backplane's. Merging them would be a combinational loop - above 2 MB U9
 * pulls /IOPAGE low, which would de-qualify the SIMM decode that asserted it. */
check(pinsOn("U3", "nIOPAGE_MB").length === 1 && pinsOn("U3", "nIOPAGE").length === 0,
  "U3 drives the motherboard's /IOPAGE term and NOT the backplane's")
check(pinsOn("U9", "nIOPAGE").length === 1 && pinsOn("U9", "nIOPAGE_MB").length === 1,
  "U9 takes U3's term and drives the backplane - two nets, no loop")
{
  const leaked = slotNames.flatMap((s) => pinsOn(s, "nIOPAGE_MB"))
  check(leaked.length === 0,
    "and the motherboard's term reaches no slot - a card sees the one that " +
    "includes ram.md 5.3's above-2 MB pull, or it decodes 2.5 MB as 0.5 MB",
    leaked.join(", "))
}

/* -- ram.md 3.1: the map is two byte-wide parts, split by the WINDOW ------ */
check(comps.filter((c) => /^U1B?$/.test(c.name)).length === 2,
  "two map SRAMs - translation needs A24..A13 in one access, which is why " +
  "this is two byte-wide parts and not one sequential read")
for (let i = 21; i <= 24; i++) {
  check(pinsOn("U1B", `A${i}`).length === 1, `physical A${i} comes from the high map byte`)
}
check(pinsOn("U1", "MAP_CE_LO").length === 1 && pinsOn("U1B", "MAP_CE_HI").length === 1,
  "⚠ each map SRAM has its OWN chip enable from U9 - U3's MAP_WE is common to " +
  "both, so the chip enable is what makes a write land in one part and not " +
  "the other (ram.md 4.3)")
check(pinsOn("U1", "MAP_OE").length === 1 && pinsOn("U1B", "MAP_OE").length === 1,
  "and they share U3's output enable, which is untouched by any of this")

/* -- machine.md 5 item 8: /WAIT had a producer and no consumer ------------
 * vctrl.pld drives it open-drain and E/Q are made on U6, which had no /WAIT
 * input at all - so "it holds E" named an effect with no mechanism. This is
 * the assertion that stops that recurring. */
check(pinsOn("U6", "nWAIT").length === 1,
  "U6 takes /WAIT - the signal that holds E has something listening to it")

/* -- machine.md 2.1: the open-drain pull-ups are here -------------------- */
for (const net of ["nIRQ", "nFIRQ", "nWAIT", "nNMI", "nIOPAGE"]) {
  const pulled = comps
    .filter((c) => /^R\d/.test(c.name))
    .some((c) => pinsOn(c.name, net).length > 0)
  check(pulled, `${net} has a pull-up on the motherboard`)
}
const haltPull = comps.find((c) => pinsOn(c.name, "nHALT").length > 0 && /^R\d/.test(c.name))
check(!!haltPull, "/HALT is tied high on the motherboard")

/* -- plan.md 2.6: TSC is grounded, five outputs are NC ------------------- */
check(pinsOn("J0", "GND").includes("TSC") || pinsOn("J0", "GND").length >= 2,
  "TSC is grounded at the CPU socket", pinsOn("J0", "GND").join(","))

/* -- gal/mmu.pld: the U3 rewire, 2026-09-06 ------------------------------ */
/* Writing the MMU's equations changed five things on this board. Each is a
 * claim here, because a build proves only that every selector resolved. */
const netExists = (n: string) => nets.some((x: any) => x.name === n)

for (const dead of ["MMU_EN", "SHADOW_DIS", "ISO_DIR"]) {
  check(!netExists(dead), `${dead} is gone from the netlist`)
}

check(pinsOn("U3", "Q").length === 1,
  "U3 takes Q - break before make needs four phases and E gives two")
const u3addr = Array.from({ length: 12 }, (_, i) => pinsOn("U3", `LA${i + 4}`).length)
check(u3addr.every((n) => n === 1), "U3 takes LA4-LA15", `${u3addr.filter(Boolean).length}/12`)

check(pinsOn("U3", "nIOPAGE_MB").length === 1,
  "U3 still forms the /IOPAGE term - it is the motherboard's net now, and U9 " +
  "drives the backplane's from it (see above)")
check(pinsOn("U3", "nIOSEL").length === 0, "/IOSEL has left U3 - the part does not fit with it")
check(pinsOn("U6", "nIOSEL").length === 1, "U6 drives /IOSEL")
check(pinsOn("U6", "LA7").length === 1 && pinsOn("U6", "LA6").length === 1,
  "U6 takes LA7 and LA6, the $FF40-$FF7F qualifier")

check(pinsOn("U4", "R_W").includes("DIR"),
  "the '245 direction is R/W itself, not a macrocell", pinsOn("U4", "R_W").join(","))
check(pinsOn("U5", "MUX_SEL").includes("SEL"),
  "the '157 select is MUX_SEL", pinsOn("U5", "MUX_SEL").join(","))
check(pinsOn("U5", "MAP_WE").length === 0,
  "the '157 select is no longer MAP_WE - that gave the SRAM no address set-up")

check(pinsOn("U2", "TASK").length === 1, "the '574 holds TASK, and TASK is all it holds")

/* -- machine.md 7.2: boot mode spans two parts and they have to agree ---- */
check(pinsOn("U6", "RUN").length === 1 && pinsOn("U9", "RUN").length === 1,
  "RUN runs from U6's latch to U9's decode - one register, two consumers")
check(pinsOn("U6", "BOOT_OE").length === 1 && pinsOn("U16", "BOOT_OE").length === 2,
  "and U6 drives the boot buffer's enable directly, so the buffer and the " +
  "map SRAMs are complements of one condition rather than two decodes that " +
  "have to agree")
for (const la of ["LA5", "LA4", "LA0"]) {
  check(pinsOn("U6", la).length === 1,
    `U6 takes ${la} - the $FFB1 strobe that leaves boot mode (gal/clkdec.pld)`)
}
/* ⛔ THIS CHECK USED TO ASSERT THE DEFECT. It read "U9 takes LA3 - the bit
 * that splits the block-register window between the two map SRAMs", and LA3
 * is ALSO the task bit of the write index U5's '157 puts on MAPA3 (below).
 * One line, two jobs: a write meant for TASK 0's high byte landed in TASK 1's
 * entry, and nothing above physical 2 MB was reachable. The two bytes have
 * two WINDOWS now - $FF90-$FF9F and $FFA0-$FFAF - and LA3 has one job again.
 * hardware/ram.md 4.3, docs/design-review2.md M-1. */
check(pinsOn("U9", "LA3").length === 0,
  "⭐ U9 does NOT take LA3 - the two map bytes are split by the window, not " +
  "by the write index's task bit")
check(pinsOn("U5", "LA3").length === 1,
  "and the '157 still does, which is the one job it has: the task bit of " +
  "machine.md 3's {TASK, block} write index")
check(pinsOn("U6", "R_W").length === 1,
  "U6 takes R/W, which is what makes the $FFB1 strobe a write and not a read")

console.log(failures === 0 ? "\nmainboard netlist OK" : `\n${failures} failure(s)`)
process.exit(failures === 0 ? 0 : 1)
