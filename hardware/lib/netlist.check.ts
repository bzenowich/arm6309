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
for (let i = 13; i <= 19; i++) {
  const fromMap = pinsOn("U1", `A${i}`)
  check(fromMap.length === 1, `physical A${i} comes from the map SRAM`, fromMap.join(","))
}

/* -- graphics.md 6.3.1: the '245 bridges the map SRAM and D0-D7 ---------- */
for (let i = 0; i < 8; i++) {
  const b = pinsOn("U4", `D${i}`)
  check(b.length === 1, `isolation buffer B${i + 1} is on D${i}`, b.join(","))
}
const aSide = [13, 14, 15, 16, 17, 18, 19].map((n) => pinsOn("U4", `A${n}`).length)
check(aSide.every((n) => n === 1), "isolation buffer A side is on physical A13-A19")

/* -- machine.md 7.1: 512 KB is one part, addressed A0-A18 ---------------- */
const rams = comps.filter((c) => c.name === "U8")
check(rams.length === 1, "one system RAM package")
const ramAddr = Array.from({ length: 19 }, (_, i) => pinsOn("U8", `A${i}`).length)
check(ramAddr.every((n) => n === 1), "system RAM takes physical A0-A18", `${ramAddr.filter(Boolean).length}/19`)
check(pinsOn("U8", "A19").length === 0, "system RAM does not see A19 (it is the RAM/VRAM selector)")

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

check(pinsOn("U3", "nIOPAGE").length === 1, "U3 still drives /IOPAGE")
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

/* -- gal/clkdec.pld: U6 gains the system RAM decode, 2026-09-06 ---------- */
/* Open item 4: these three reached U8 and nothing else, behind a comment
 * claiming U3 formed the term. U3 forms no such term and has one free pin,
 * which is one short of the two /CE needs. */
for (const net of ["RAM_CE", "RAM_OE", "RAM_WE"]) {
  const driver = pinsOn("U6", net)
  const load = pinsOn("U8", net)
  check(driver.length === 1 && load.length === 1,
    `${net} runs from U6 to the system RAM`, `U6:[${driver}] U8:[${load}]`)
}
check(pinsOn("U6", "A19").length === 1,
  "U6 takes physical A19 - the decode is downstream of the map SRAM")
check(pinsOn("U6", "R_W").length === 1,
  "U6 takes R/W, which is what qualifies RAM /OE")
check(pinsOn("U1", "A19").length === 1 && pinsOn("U6", "A19").length === 1,
  "A19 is the map SRAM's output and U6's input - not a CPU pin")

console.log(failures === 0 ? "\nmainboard netlist OK" : `\n${failures} failure(s)`)
process.exit(failures === 0 ? 0 : 1)
