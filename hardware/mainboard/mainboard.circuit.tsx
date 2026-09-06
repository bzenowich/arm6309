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
 * Schematic-level. Placement and routing are not attempted yet - the GALs have
 * to be fitted first (graphics.md 18 step 0) and three of the parts here still
 * need a datasheet (hardware/README.md open item 1).
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
        /* DQ0-DQ6 are physical A13-A19. DQ7 is spare and reads back as the
         * eighth bit of a map entry. */
        DQ0: pa(13), DQ1: pa(14), DQ2: pa(15), DQ3: pa(16),
        DQ4: pa(17), DQ5: pa(18), DQ6: pa(19), DQ7: "net.MAPD7",
        nCE: "net.GND", nOE: "net.MAP_OE", nWE: "net.MAP_WE",
      }}
    />

    {/* U2 - task select, MMU enable, and the 7.2 shadow-ROM disable. Three
      * bits of eight; the rest are spare and readable nowhere. */}
    <chip
      name="U2"
      footprint={HC574.footprint}
      pinLabels={labels(HC574)}
      connections={{
        VCC: "net.V5", GND: "net.GND", nOE: "net.GND", CP: "net.CTRL_CP",
        ...Object.fromEntries(Array.from({ length: 8 }, (_, i) => [`D${i + 1}`, d(i)])),
        Q1: "net.TASK", Q2: "net.MMU_EN", Q3: "net.SHADOW_DIS",
      }}
      noConnect={["Q4", "Q5", "Q6", "Q7", "Q8"]}
    />

    {/* U3 - the write decode, the /IOPAGE term, and the sequencing of U1/U4/U5.
      *
      * /IOPAGE is (LA15..LA13 = 111) AND (LA12..LA8 = 11111) - machine.md 2.
      * /IOSEL is that term AND (LA7,LA6 = 01), i.e. $FF40-$FF7F.
      *
      * ⚠ Not fitted. graphics.md 6.3.1 already shows the mux cannot fold in
      * here; whether the remaining terms fit a 22V10 is unproven, and
      * graphics.md 18 step 0 requires fitting before layout. */}
    <chip
      name="U3"
      footprint="dip24_w0.3in"
      pinLabels={labels(gal22v10({
        2: "LA15", 3: "LA14", 4: "LA13", 5: "LA12", 6: "LA11", 7: "LA10",
        8: "LA9", 9: "LA8", 10: "LA7", 11: "LA6",
        13: "LA5", 14: "LA4", 15: "E", 16: "R/W", 17: "MMU_EN",
        18: "/IOPAGE", 19: "/IOSEL", 20: "MAP_OE", 21: "MAP_WE",
        22: "ISO_DIR", 23: "ISO_OE",
      }))}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        ...busConnections("LA", 10, la, 6),
        E: "net.E", R_W: "net.R_W", MMU_EN: "net.MMU_EN",
        nIOPAGE: "net.nIOPAGE", nIOSEL: "net.nIOSEL",
        MAP_OE: "net.MAP_OE", MAP_WE: "net.MAP_WE",
        ISO_DIR: "net.ISO_DIR", ISO_OE: "net.ISO_OE",
      }}
      noConnect={["CLK"]}
    />

    {/* U4 - break-before-make isolation between U1's common I/O and D0-D7.
      * The ordering in graphics.md 6.3.1's table is load-bearing: U1's /OE
      * comes away before U4 is enabled, and goes back on last. */}
    <chip
      name="U4"
      footprint={HC245.footprint}
      pinLabels={labels(HC245)}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        DIR: "net.ISO_DIR", nOE: "net.ISO_OE",
        A1: pa(13), A2: pa(14), A3: pa(15), A4: pa(16),
        A5: pa(17), A6: pa(18), A7: pa(19), A8: "net.MAPD7",
        ...Object.fromEntries(Array.from({ length: 8 }, (_, i) => [`B${i + 1}`, d(i)])),
      }}
    />

    {/* U5 - the quad 2:1 the mux argument in graphics.md 6.3.1 costs a package
      * for. SEL low = translate, SEL high = the map-write index. */}
    <chip
      name="U5"
      footprint={HC157.footprint}
      pinLabels={labels(HC157)}
      connections={{
        VCC: "net.V5", GND: "net.GND", nE: "net.GND", SEL: "net.MAP_WE",
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
      * rating, and is below the real HD63C09E's t_cyc minimum. */}
    <chip
      name="U6"
      footprint="dip24_w0.3in"
      pinLabels={labels(gal22v10({
        2: "FAST_E", 3: "/RESET",
        22: "E", 23: "Q",
      }))}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        CLK: "net.CLK25", FAST_E: "net.GND", nRESET: "net.nRESET",
        E: "net.E", Q: "net.Q",
      }}
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
      * same sentence goes with the other three: /CE is the A19 = 0 AND
      * /IOPAGE term, which U3 already forms. See hardware/README.md finding 1. */}
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
