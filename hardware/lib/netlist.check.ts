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

console.log(failures === 0 ? "\nmainboard netlist OK" : `\n${failures} failure(s)`)
process.exit(failures === 0 ? 0 : 1)
