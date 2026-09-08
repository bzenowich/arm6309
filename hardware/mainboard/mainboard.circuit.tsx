/* arm6309 motherboard.
 *
 * docs/machine.md 6 lists "Draw the motherboard" as an open item owned by the
 * machine, with no document behind it. This is the first pass at it.
 *
 * What lives here, and the section that put it here:
 *   the CPU module's 40-pin socket        machine.md 5 item 5 (decided: socket)
 *   the MMU, five packages                graphics.md 6.3.1
 *   the E/Q divider, one GAL              machine.md 1
 *   the 25.175 MHz master oscillator      machine.md 1
 *   the power-on reset supervisor         machine.md 2.1
 *   512 KB of system SRAM                 machine.md 7.1
 *   the open-drain pull-ups               machine.md 2.1
 *   six expansion slots                   machine.md 5 item 5 (still open)
 *
 * Schematic-level. Placement and routing are not attempted yet. Two of the
 * three blockers have moved: every package pinout is datasheet-verified
 * (lib/parts.ts, and U1's was wrong), and U3's equations are written
 * (gal/mmu.pld, and four things here were wrong). U6 is still unwritten, and
 * the system RAM's control lines still have no source - see U8.
 */
import { SlotSocket } from "../lib/SlotConnector"
import {
  CPU_SOCKET, MAP_SRAM, HC574, HC245, HC157, SRAM_512K, gal22v10, labels,
} from "../lib/parts"

const SLOTS = 6

/* Logical A0-A15 come off the CPU socket and stay on the motherboard: A13-A15
 * are the map SRAM's address inputs and nothing on a card may see them
 * (machine.md 2). A0-A12 pass through untranslated and become backplane
 * A0-A12; A13-A19 are the map SRAM's output. */
const la = (n: number) => `net.LA${n}`
const pa = (n: number) => `net.A${n}`
const d = (n: number) => `net.D${n}`

const busConnections = (
  prefix: string,
  count: number,
  net: (n: number) => string,
  from = 0,
) => Object.fromEntries(
  Array.from({ length: count }, (_, i) => [`${prefix}${from + i}`, net(from + i)]),
)

export default () => (
  <board name="arm6309-mainboard" width="220mm" height="180mm" routingDisabled>
    {/* ------------------------------------------------ CPU module socket -- */}
    {/* The module is the 40-pin drop-in board cpu/ already builds for the
      * CoCo 3, plugged in here. Its own '541/'245 level buffers ride with it
      * (plan.md 2.6), so the motherboard adds no buffering of its own.
      * BUSY, /LIC, AVMA and TSC are not emulated - plan.md 3.2 drops them, and
      * TSC is grounded exactly as the CoCo 3 grounds it. */}
    <connector
      name="J0"
      footprint={CPU_SOCKET.footprint}
      pinLabels={labels(CPU_SOCKET)}
      connections={{
        GND: "net.GND", VCC: "net.V5",
        ...busConnections("A", 16, la),
        ...busConnections("D", 8, d),
        R_W: "net.R_W", E: "net.E", Q: "net.Q",
        nRESET: "net.nRESET", nHALT: "net.nHALT",
        nIRQ: "net.nIRQ", nFIRQ: "net.nFIRQ", nNMI: "net.nNMI",
        TSC: "net.GND",
      }}
      noConnect={["BS", "BA", "BUSY", "AVMA", "nLIC"]}
    />

    {/* ------------------------------------------------------------ MMU --- */}
    {/* Five packages, and graphics.md 6.3.1 argues each one: a common-I/O SRAM
      * needs the '245 to keep its data pins off A13-A19, and a map write needs
      * the '157 because logical A15..A13 is 111 during the very cycle that
      * writes the entry. */}

    {/* U1 - the block map. Addressed {TASK, LA15..LA13} while translating,
      * LA3..LA0 during a map write. Sixteen of 2048 locations are used; a
      * 15 ns 2K x 8 is stocked and a 16 x 8 is not. */}
    <chip
      name="U1"
      footprint={MAP_SRAM.footprint}
      pinLabels={labels(MAP_SRAM)}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        A0: "net.MAPA0", A1: "net.MAPA1", A2: "net.MAPA2", A3: "net.MAPA3",
        A4: "net.GND", A5: "net.GND", A6: "net.GND", A7: "net.GND",
        A8: "net.GND", A9: "net.GND", A10: "net.GND",
        /* DQ0-DQ7 are physical A13-A20.
         *
         * ⚠ DQ7 WAS "spare and reads back as the eighth bit of a map entry"
         * until 2026-09-08, and that is the whole cost of doubling the
         * physical map to 2 MB (machine.md 5 item 1 option D): the bit was
         * already stored, already written through U4, and already read back.
         * It drove nothing. It now drives slot A34. Zero ICs. */
        DQ0: pa(13), DQ1: pa(14), DQ2: pa(15), DQ3: pa(16),
        DQ4: pa(17), DQ5: pa(18), DQ6: pa(19), DQ7: pa(20),
        nCE: "net.GND", nOE: "net.MAP_OE", nWE: "net.MAP_WE",
      }}
    />

    {/* U2 - task select. ONE bit of eight, not the three this comment used to
      * claim (gal/README.md findings 1 and 3): MMU_EN was dropped because no
      * bypass path exists for it to switch, and SHADOW_DIS was dropped because
      * the shadow ROM is inside the CPU module and all 40 socket pins are
      * defined - there is no wire for it and nowhere to put one.
      *
      * The package stays. A '74 would hold TASK in DIP-14, but seven spare
      * latched bits on a motherboard are worth more than six pins, and
      * graphics.md 6.3.1's five-IC count is written against a '574.
      *
      * CP idles high and its rising edge is at E-fall - U3 emits the inverted
      * term, so there is exactly one edge per control write and it lands where
      * 6809 write data has been valid for 247 ns. */}
    <chip
      name="U2"
      footprint={HC574.footprint}
      pinLabels={labels(HC574)}
      connections={{
        VCC: "net.V5", GND: "net.GND", nOE: "net.GND", CP: "net.CTRL_CP",
        ...Object.fromEntries(Array.from({ length: 8 }, (_, i) => [`D${i + 1}`, d(i)])),
        Q1: "net.TASK",
      }}
      noConnect={["Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8"]}
    />

    {/* U3 - the MMU sequencer. gal/mmu.pld is the source of truth for these
      * pins and this board follows it; gal/README.md carries the derivation.
      *
      * /IOPAGE is (LA15..LA13 = 111) AND (LA12..LA8 = 11111) - machine.md 2.
      * $FFA0-$FFBF is that term AND (LA7..LA5 = 101), split by LA4 into the
      * 16 block registers and the control latch - machine.md 5 item 3, signed
      * off 2026-09-06.
      *
      * Q is here because the break-before-make ordering graphics.md 6.3.1
      * calls load-bearing needs four phases and E alone gives two.
      *
      * /IOSEL is NOT here - it is on U6. With it the part needs 16 inputs and
      * has 15. ISO_DIR is not here either: it is R/W, and a wire. */}
    <chip
      name="U3"
      footprint="dip24_w0.3in"
      pinLabels={labels(gal22v10({
        1: "LA15", 2: "LA14", 3: "LA13", 4: "LA12", 5: "LA11", 6: "LA10",
        7: "LA9", 8: "LA8", 9: "LA7", 10: "LA6", 11: "LA5",
        13: "LA4", 14: "E", 15: "Q", 16: "R/W",
        17: "/IOPAGE", 18: "MUX_SEL", 19: "/ISO_OE", 20: "/MAP_WE",
        21: "/MAP_OE", 22: "CTRL_CP", 23: "SPARE",
      }))}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        ...busConnections("LA", 12, la, 4),
        E: "net.E", Q: "net.Q", R_W: "net.R_W",
        nIOPAGE: "net.nIOPAGE", MUX_SEL: "net.MUX_SEL",
        nISO_OE: "net.ISO_OE", nMAP_WE: "net.MAP_WE", nMAP_OE: "net.MAP_OE",
        CTRL_CP: "net.CTRL_CP",
      }}
      noConnect={["SPARE"]}
    />

    {/* U4 - break-before-make isolation between U1's common I/O and D0-D7.
      * The ordering in graphics.md 6.3.1's table is load-bearing: U1's /OE
      * comes away before U4 is enabled, and goes back on last. U4 turns on at
      * E-rise, which puts ~174 ns between the two - gal/README.md.
      *
      * DIR is R/W directly, not a GAL output: a read wants A-to-B and a write
      * B-to-A, which is R/W exactly. That is one macrocell back, and it is
      * what makes the break-before-make claim direction-aware. */}
    <chip
      name="U4"
      footprint={HC245.footprint}
      pinLabels={labels(HC245)}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        DIR: "net.R_W", nOE: "net.ISO_OE",
        A1: pa(13), A2: pa(14), A3: pa(15), A4: pa(16),
        A5: pa(17), A6: pa(18), A7: pa(19), A8: pa(20),
        ...Object.fromEntries(Array.from({ length: 8 }, (_, i) => [`B${i + 1}`, d(i)])),
      }}
    />

    {/* U5 - the quad 2:1 the mux argument in graphics.md 6.3.1 costs a package
      * for. SEL low = translate, SEL high = the map-write index - the part's
      * pin 1 is A/B with the bar over the A, so low selects the A inputs.
      *
      * ⚠ SEL was MAP_WE until 2026-09-06, which switched the SRAM's address at
      * the instant the write strobe asserted (gal/README.md finding 2). It is
      * MUX_SEL now: asserted on address decode, 367 ns of set-up against the
      * CY7C128A-15's 12 ns tAW. */}
    <chip
      name="U5"
      footprint={HC157.footprint}
      pinLabels={labels(HC157)}
      connections={{
        VCC: "net.V5", GND: "net.GND", nE: "net.GND", SEL: "net.MUX_SEL",
        "1A": la(13), "1B": la(0), "1Y": "net.MAPA0",
        "2A": la(14), "2B": la(1), "2Y": "net.MAPA1",
        "3A": la(15), "3B": la(2), "3Y": "net.MAPA2",
        "4A": "net.TASK", "4B": la(3), "4Y": "net.MAPA3",
      }}
    />

    {/* ------------------------------------------------- clock and reset --- */}
    {/* OSC1 - the one master. It is on the motherboard and not on the video card
      * for the reason machine.md 1 gives: pulling the video card would
      * otherwise stop E, and bring-up runs before video exists. */}
    <chip
      name="OSC1"
      footprint="dip8_w0.3in"
      pinLabels={{ pin1: "EN", pin4: "GND", pin5: "OUT", pin8: "VCC" }}
      connections={{ EN: "net.V5", GND: "net.GND", VCC: "net.V5", OUT: "net.CLK25" }}
      noConnect={["pin2", "pin3", "pin6", "pin7"]}
    />

    {/* U6 - the divider. 25.175 / 12 = 2.0979 MHz, and that is the machine's
      * rate (machine.md 1.1). The /8 path exists but is an experiment a builder
      * opts into: it breaks the video read-back, takes the 6551 57 % over its
      * rating, and is below the real HD63C09E's t_cyc minimum.
      *
      * gal/clkdec.pld is the source of truth for these pins. It carries three
      * jobs: the divider, /IOSEL, and the system RAM's control lines.
      *
      * /IOSEL is /IOPAGE AND A7 = 0 - $FF00-$FF7F, widened from $FF40 on
      * 2026-09-08 (machine.md 5 item 1 A), which DELETED the LA6 term rather
      * than adding one. LA6 stays wired to pin 6 driving nothing, so
      * $FF80-$FF8F remains a one-line change. Pin 9 took physical A20 in the
      * same pass. gal/clkdec.pld is the source of truth and it records that
      * this equation also had its polarity wrong until that day.
      *
      * /IOSEL is a machine-level backplane
      * signal rather than MMU sequencing, and it is here because U3 does not
      * fit with it. /IOPAGE stays on U3: routing it through here would put a
      * second GAL delay ahead of MAP_OE, the edge the break-before-make
      * margin is measured from.
      *
      * RAM_CE/OE/WE are here because U3 cannot take them either - it has one
      * free pin and /CE alone needs two (A19 in, /CE out). They were driven
      * by NOTHING until 2026-09-06; see hardware/README.md open item 4. Note
      * A19 is PHYSICAL, so this decode is downstream of the map SRAM: t_AD
      * 110 + map 15 + GAL 10 + RAM 55 = 190 ns against ~437 available.
      *
      * The four counter bits come out on pins nothing connects to. That is
      * deliberate - they are free test points on the signal that is hardest
      * to characterise from outside, and a 22V10 has no buried nodes. */}
    <chip
      name="U6"
      footprint="dip24_w0.3in"
      pinLabels={labels(gal22v10({
        2: "FAST_E", 3: "/RESET", 4: "/IOPAGE", 5: "LA7", 6: "LA6",
        7: "A19", 8: "R/W", 9: "A20", 10: "/WAIT",
        14: "/RAM_OE", 15: "/IOSEL", 16: "C0", 17: "C1", 18: "E", 19: "Q",
        20: "C2", 21: "C3", 22: "/RAM_CE", 23: "/RAM_WE",
      }))}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        CLK: "net.CLK25", FAST_E: "net.GND", nRESET: "net.nRESET",
        nIOPAGE: "net.nIOPAGE", LA7: la(7), LA6: la(6),
        A19: pa(19), A20: pa(20), R_W: "net.R_W", nWAIT: "net.nWAIT",
        nIOSEL: "net.nIOSEL", E: "net.E", Q: "net.Q",
        nRAM_CE: "net.RAM_CE", nRAM_OE: "net.RAM_OE", nRAM_WE: "net.RAM_WE",
      }}
      noConnect={["C0", "C1", "C2", "C3"]}
    />

    {/* U7 - power-on reset. Every card takes /RESET as an input and no card
      * budgeted the supervisor; machine.md 2.1 puts it here. */}
    <chip
      name="U7"
      footprint="sot23_3"
      pinLabels={{ pin1: "GND", pin2: "nRST", pin3: "VCC" }}
      connections={{ GND: "net.GND", VCC: "net.V5", nRST: "net.nRESET" }}
    />

    {/* -------------------------------------------------- system RAM ------- */}
    {/* ⚠ ONE part, not the four machine.md 7.1 asks for. 512K x 8 is 512 KB,
      * so four of them is 2 MB - against a 512 KB requirement, in a 1 MB
      * physical map that allots system RAM exactly A19 = 0, i.e. A0-A18.
      * Nineteen address lines is exactly this part. The "and a decode" in the
      * same sentence goes with the other three. See hardware/README.md finding 1.
      *
      * RAM_CE, RAM_OE and RAM_WE come from U6 (gal/clkdec.pld). They were
      * driven by nothing at all until 2026-09-06, behind a comment claiming
      * "/CE is the A19 = 0 AND /IOPAGE term, which U3 already forms" - U3
      * forms no such term. /OE is qualified by R/W rather than tied low,
      * which is what keeps the SRAM and the CPU off D0-D7 together on a
      * write. hardware/README.md open item 4, closed. */}
    <chip
      name="U8"
      footprint={SRAM_512K.footprint}
      pinLabels={labels(SRAM_512K)}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        ...busConnections("A", 19, pa),
        ...Object.fromEntries(Array.from({ length: 8 }, (_, i) => [`DQ${i}`, d(i)])),
        nCE: "net.RAM_CE", nOE: "net.RAM_OE", nWE: "net.RAM_WE",
      }}
    />

    {/* -------------------------------------------- backplane pull-ups ----- */}
    {/* machine.md 2.1: four cards declare open-drain outputs and no document
      * placed the resistors. 3.3k, here. /HALT is 4.7k and tied high because
      * nothing in this machine drives it - saying so is the point. */}
    {["nIRQ", "nFIRQ", "nWAIT", "nNMI", "nIOPAGE"].map((net, i) => (
      <resistor
        key={net}
        name={`R${i + 1}`}
        resistance="3.3k"
        footprint="0805"
        connections={{ pin1: "net.V5", pin2: `net.${net}` }}
      />
    ))}
    <resistor
      name="R6"
      resistance="4.7k"
      footprint="0805"
      connections={{ pin1: "net.V5", pin2: "net.nHALT" }}
    />

    {/* ------------------------------------------------------- the slots --- */}
    {/* ⚠ Six is a guess. machine.md 5 item 5 has never said how many, and the
      * five specified cards plus one free is the least defensible-by-arithmetic
      * answer available. Six slots is also 12 A of finger capacity against a
      * 2-3 A machine, so the supply, not the connector, is the limit. */}
    {Array.from({ length: SLOTS }, (_, i) => (
      <SlotSocket key={i} name={`J${i + 1}`} />
    ))}

    {/* A0-A12 are untranslated: the backplane's physical A0-A12 are the CPU's
      * logical A0-A12, straight through. */}
    {Array.from({ length: 13 }, (_, i) => (
      <trace key={i} name={`ta${i}`} from={la(i)} to={pa(i)} />
    ))}
  </board>
)
