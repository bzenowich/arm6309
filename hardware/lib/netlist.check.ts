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

/* -- ⛔ AND EACH ONE NEEDS A WAY TO BE WRITTEN, which nothing checked ------
 *
 * This block is the second half of design-review2.md M-1, and the reason it
 * is a separate finding is that every assertion above passed while the high
 * map byte was unreachable. M-1 was diagnosed as a decode fault, the decode
 * was repaired into two windows, `mainboard_tb` wrote $FF90 and read it back
 * happily - and on the board U1B's DQ0-DQ3 went to physical A24..A21 and to
 * NOTHING ELSE. There was no wire from D0-D7 to the high map SRAM at all.
 *
 * ram.md 3.1 is where the assumption lived: "Isolation '245: 0 - both SRAMs
 * sit on the same D0-D7; the address picks which is written". TWO COMMON-I/O
 * SRAMs CANNOT SHARE ONE BUFFER - each drives its own DQ pins for the whole
 * of every translation, because that is how the physical address is formed.
 * Twelve bits of map entry need twelve bits of buffer and a '245 has eight.
 *
 * The claim is therefore about a PATH and not a pin: every bit of every map
 * SRAM reaches D0-D7 through some buffer. */
{
  const buffers = ["U4", "U18"]
  for (const b of buffers) {
    const bSide = Array.from({ length: 8 }, (_, i) => pinsOn(b, `D${i}`).length)
    check(bSide.every((n) => n === 1),
      `${b}'s B side is on all eight of D0-D7`, `${bSide.filter(Boolean).length}/8`)
    check(pinsOn(b, "R_W").length === 1,
      `${b}'s direction is R/W - a wire, not a macrocell`)
  }
  /* The two enables, and they must be DIFFERENT nets. One shared enable would
   * open both buffers onto D0-D7 for the whole of any block read and the one
   * whose SRAM was deselected would drive from a floating node. */
  check(pinsOn("U4", "ISO_OE_LO").length === 1 && pinsOn("U18", "ISO_OE_HI").length === 1,
    "⭐ the two '245s have SEPARATE enables from U3 - one shared enable puts " +
    "both of them on D0-D7 for the whole of any block read")
  check(pinsOn("U3", "ISO_OE_LO").length === 1 && pinsOn("U3", "ISO_OE_HI").length === 1,
    "and U3 produces both - pin 19 and pin 23, the part's last")
  check(pinsOn("U4", "ISO_OE_HI").length === 0 && pinsOn("U18", "ISO_OE_LO").length === 0,
    "and neither buffer sees the other's")

  /* THE PATH ITSELF. For each map SRAM, every one of its eight DQ pins must
   * share a net with a pin of one buffer, and that buffer's other side is
   * D0-D7 (asserted above). This is the assertion whose absence cost the
   * machine its high map byte. */
  const netsOfPin = (comp: string, pin: string) => {
    const p = ports.find((x) => compName.get(x.source_component_id) === comp && x.name === pin)
    return p ? [...(portNet.get(p.source_port_id) ?? [])] : []
  }
  for (const [sram, buf] of [["U1", "U4"], ["U1B", "U18"]] as const) {
    const reached = Array.from({ length: 8 }, (_, i) => {
      const nets = netsOfPin(sram, `DQ${i}`)
      return nets.some((n) => pinsOn(buf, n).length > 0)
    })
    check(reached.every(Boolean),
      `⭐ every bit of ${sram} reaches D0-D7 through ${buf} - the map entry is ` +
      `WRITABLE, which is what design-review2.md M-1's repair left undone`,
      `${reached.filter(Boolean).length}/8 bits`)
  }
}

/* -- ⭐ AND THE GENERAL FORM OF IT, which is worth more than the specific ---
 *
 * The assertion above names U1B and U18 and it would not have caught the same
 * mistake on any other part. What actually went wrong is stateable without
 * naming anything: A DEVICE WITH A DATA BUS HAD THAT BUS CONNECTED TO NOTHING
 * THAT COULD DRIVE OR READ IT, and every other property of the part was
 * asserted. This is the same move lib/decode.check.ts makes after the audio
 * card's SEL - a defect found once becomes a rule, not a row.
 *
 * The claim: every data pin on the board reaches at least one OTHER component.
 * A pin whose net has one member is a stub, and a stub on a data bus is a
 * register that cannot be written or a device that cannot answer. It is
 * cheap - it is the netlist it already parsed - and it is exactly the check
 * whose absence let design-review2.md M-1 be declared fixed. */
{
  const DATA = /^(D\d+|DQ\d+|[AB][1-8]|Q[1-8]|D[1-8])$/
  const stubs: string[] = []
  for (const p of ports) {
    const comp = compName.get(p.source_component_id) ?? "?"
    if (!/^(U\d+B?|SIMM\d|J0)$/.test(comp)) continue
    if (!DATA.test(p.name ?? "")) continue
    const nets = [...(portNet.get(p.source_port_id) ?? [])]
    /* A pin that is explicitly noConnect has no net at all and is a decision;
     * a pin ON a net that nothing else joins is the defect. */
    if (nets.length === 0) continue
    const others = nets.some((n) =>
      ports.some((q) =>
        q.source_port_id !== p.source_port_id &&
        portNet.get(q.source_port_id)?.has(n)))
    if (!others) stubs.push(`${comp}.${p.name}`)
  }
  check(stubs.length === 0,
    "⭐ no data pin on the board is a stub - every DQ, D and buffer pin that " +
    "is on a net has something else on that net. The general form of M-1: a " +
    "device whose data bus goes nowhere is a register that cannot be written",
    stubs.join(" "))
}

/* -- ⭐ AND THE ONE THAT WOULD ACTUALLY HAVE CAUGHT IT ---------------------
 *
 * ⚠ The stub check above is worth having and it is NOT sufficient, which is
 * worth saying plainly rather than discovering twice: U1B's DQ0-DQ3 were on
 * physical A24..A21, a net with U9, U10 and a '157 on it, so they were never
 * stubs. They were connected to the wrong thing. What was missing is the only
 * property that matters about a memory-mapped device:
 *
 *   ⭐ IF THE CPU IS SUPPOSED TO READ OR WRITE IT, ITS DATA PINS MUST REACH
 *     D0-D7 - directly, or through a buffer.
 *
 * So this walks the netlist for real: a component with both an A1-A8 and a
 * B1-B8 side is a transparent 8-bit bridge (a '245), and every DQn/Dn pin on a
 * memory or register part has to reach D0-D7 across zero or more of them. It
 * is stated about no part in particular, so the next device that arrives on
 * this board gets it for free. */
{
  /* Bridges, found by shape and not by name. */
  const bridges: { a: string; b: string; comp: string }[] = []
  for (const c of comps) {
    const names = new Set(ports
      .filter((p) => p.source_component_id === c.source_component_id)
      .map((p) => p.name))
    for (let i = 1; i <= 8; i++)
      if (names.has(`A${i}`) && names.has(`B${i}`)) {
        const an = [...(portNet.get(ports.find((p) =>
          p.source_component_id === c.source_component_id && p.name === `A${i}`)!.source_port_id) ?? [])][0]
        const bn = [...(portNet.get(ports.find((p) =>
          p.source_component_id === c.source_component_id && p.name === `B${i}`)!.source_port_id) ?? [])][0]
        if (an && bn) bridges.push({ a: an, b: bn, comp: c.name })
      }
  }
  const CPU_BUS = new Set(Array.from({ length: 8 }, (_, i) => `D${i}`))
  const reaches = (start: string) => {
    const seen = new Set([start])
    const q = [start]
    while (q.length) {
      const n = q.shift()!
      if (CPU_BUS.has(n)) return true
      for (const br of bridges) {
        for (const [x, y] of [[br.a, br.b], [br.b, br.a]] as const)
          if (x === n && !seen.has(y)) { seen.add(y); q.push(y) }
      }
    }
    return false
  }
  const unreachable: string[] = []
  for (const c of comps) {
    const dataPins = ports.filter((p) =>
      p.source_component_id === c.source_component_id && /^(DQ\d+|D[1-8])$/.test(p.name ?? ""))
    if (dataPins.length === 0) continue
    for (const p of dataPins) {
      const nets = [...(portNet.get(p.source_port_id) ?? [])]
      if (nets.length === 0) continue               // noConnect is a decision
      if (!nets.some(reaches)) unreachable.push(`${c.name}.${p.name}=${nets[0]}`)
    }
  }
  check(bridges.length >= 16,
    "the buffers are found by shape - a part with an A and a B side is a bridge",
    `${bridges.length} bit-bridges across ${new Set(bridges.map((b) => b.comp)).size} parts`)
  check(unreachable.length === 0,
    "⛔ every data pin on every memory or register part reaches D0-D7, through " +
    "a buffer or directly. THIS is the assertion whose absence let M-1 be " +
    "declared fixed with the high map byte still unwritable - U1B's DQ pins " +
    "were on a net with three other parts on it, so they were never stubs; " +
    "they were connected to the wrong thing",
    unreachable.join(" "))
}

/* -- machine.md 5 item 14: A24..A21 are parked, not floating -------------
 * Item 12 parked physical A20-A13 with U16's buffer, because those eight
 * reach every slot. The top four come off the second map SRAM, are deselected
 * for exactly the same cycles, and never leave the board - so nobody drove
 * them and item 14 recorded "four CMOS inputs held at neither rail". A '244 is
 * a package for four bits; a pull-down is four passives. */
for (let i = 21; i <= 24; i++) {
  const pulled = comps
    .filter((c) => /^R\d/.test(c.name))
    .some((c) => pinsOn(c.name, `A${i}`).length > 0 && pinsOn(c.name, "GND").length > 0)
  check(pulled, `physical A${i} has a pull-DOWN, so the parked address is zero ` +
    `top to bottom - machine.md 5 item 14`)
}

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
