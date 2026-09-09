/* arm6309 motherboard. 18 ICs and four SIMM sockets.
 *
 * docs/machine.md 6 lists "Draw the motherboard" as an open item owned by the
 * machine. This is the board.
 *
 * What lives here, and the section that put it here:
 *   the CPU module's 40-pin socket        machine.md 5 item 5 (decided: socket)
 *   the MMU, six packages                 graphics.md 6.3.1 + ram.md 3.1
 *   the E/Q divider and boot mode, U6     machine.md 1, machine.md 7.2
 *   the 25.175 MHz master oscillator      machine.md 1
 *   the power-on reset supervisor         machine.md 2.1
 *   the space decode, U9                  ram.md 6.3, 6.7
 *   the SIMM controller, U10 + 3 x '157   ram.md 6.3
 *   the refresh timebase, U17            ram.md 6.3.1 - and it was never counted
 *   four 30-pin SIMM sockets, 4-16 MB     ram.md 6
 *   a 1 MB boot ROM and its address buffer  machine.md 7.2
 *   the open-drain pull-ups               machine.md 2.1
 *   six expansion slots                   hardware/README.md
 *
 * WHAT LEFT ON 2026-09-09: U8, the 512 KB DIP system RAM. ram.md 6.2 replaced
 * it with SIMM sockets on 2026-09-08 and this file kept drawing it for a day -
 * which is what hardware/README.md open item 3 was tracking. The part moved to
 * the audio card (audio.md 5), where it is 512 KB of sample RAM in one package.
 *
 * Schematic-level; placement and routing are not attempted. ALL FOUR of the
 * board's GALs are now fitted at the fuse level and checked against Atmel's
 * own CUPL - U3 (gal/mmu.pld), U6 (gal/clkdec.pld), U9 (gal/u9.pld) and U10
 * (gal/u10.pld). There is no unwritten logic on this board.
 */
import { SlotSocket } from "../lib/SlotConnector"
import {
  CPU_SOCKET, MAP_SRAM, HC574, HC245, HC157, HCT244, FLASH_512K, SIMM30,
  HC4040, gal22v10, labels,
} from "../lib/parts"

const SLOTS = 6
const SIMMS = 4

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
        /* ⚠ /CE WAS TIED LOW until 2026-09-09 and is U9's now. Boot mode has
         * to take the map off the physical address bus so the '244 can drive
         * it, and /OE cannot do that job: U3's MAP_OE is asserted for every
         * non-$FFxx cycle, which is most of boot. One net, no parts, and it
         * is what makes the buffer and the SRAMs exact complements
         * (gal/u9.pld, gal/jedec.check.ts). */
        nCE: "net.MAP_CE_LO", nOE: "net.MAP_OE", nWE: "net.MAP_WE",
      }}
    />

    {/* U1B - the HIGH map byte, ram.md 3.1. Read in parallel with U1 on the
      * same address and the same D0-D7: translation needs A24..A13 at once,
      * which is why this is two byte-wide parts and not one sequential read
      * inside a 110 ns t_AD budget that already has 15 ns of SRAM in it.
      *
      * Four of its eight bits are physical A24..A21; the other four are
      * ram.md 3.3's spare flags and drive nothing yet.
      *
      * ⚠ A24..A21 NEVER REACH A SLOT. That is ram.md 5.3: a card decodes
      * A0-A20 and U9 pulls /IOPAGE for everything above 2 MB, so the four
      * backplane pins the map would otherwise need cost nothing at all. */}
    <chip
      name="U1B"
      footprint={MAP_SRAM.footprint}
      pinLabels={labels(MAP_SRAM)}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        A0: "net.MAPA0", A1: "net.MAPA1", A2: "net.MAPA2", A3: "net.MAPA3",
        A4: "net.GND", A5: "net.GND", A6: "net.GND", A7: "net.GND",
        A8: "net.GND", A9: "net.GND", A10: "net.GND",
        DQ0: pa(21), DQ1: pa(22), DQ2: pa(23), DQ3: pa(24),
        nCE: "net.MAP_CE_HI", nOE: "net.MAP_OE", nWE: "net.MAP_WE",
      }}
      noConnect={["DQ4", "DQ5", "DQ6", "DQ7"]}
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
        17: "/IOPAGE_MB", 18: "MUX_SEL", 19: "/ISO_OE", 20: "/MAP_WE",
        21: "/MAP_OE", 22: "CTRL_CP", 23: "SPARE",
      }))}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        ...busConnections("LA", 12, la, 4),
        E: "net.E", Q: "net.Q", R_W: "net.R_W",
        /* ⚠ THE MOTHERBOARD'S TERM, NOT THE BACKPLANE'S, since 2026-09-09.
         * U9 drives the backplane's /IOPAGE as this term OR "above 2 MB"
         * (ram.md 5.3). Merging the two nets would be a combinational loop:
         * above 2 MB U9 pulls /IOPAGE low, which would then de-qualify the
         * SIMM decode that asserted it. */
        nIOPAGE_MB: "net.nIOPAGE_MB", MUX_SEL: "net.MUX_SEL",
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
        /* ⚠ 4B IS LA3 AND IT IS THE TASK BIT OF THE WRITE INDEX. machine.md 3:
         * $FFA0+n is task n>>3, block n&7. Until 2026-09-09 U9 ALSO used LA3
         * to choose which of the two map SRAMs a write landed in, and one
         * line cannot do both jobs - design-review2.md M-1. The byte is
         * chosen by the window now and this wire keeps its one job. */
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

    {/* U6 - the divider and boot mode. 25.175 / 12 = 2.0979 MHz, and that is
      * the machine's rate (machine.md 1.1). The /8 path exists but is an
      * experiment a builder opts into: it breaks the video read-back, takes
      * the serial part 57 % over its rating, and is below the real HD63C09E's
      * t_cyc minimum.
      *
      * gal/clkdec.pld is the source of truth for these pins. Three jobs:
      *
      *   1. the E/Q divider, with the /WAIT hold of machine.md 5 item 8
      *   2. /IOSEL - /IOPAGE AND A7 = 0, $FF00-$FF7F. It is here and not on
      *      U3 because U3 does not fit with it. /IOPAGE stays on U3: routing
      *      it through here would put a second GAL delay ahead of MAP_OE, the
      *      edge the break-before-make margin is measured from
      *   3. BOOT MODE - the RUN latch and the '244's output enable
      *
      * ⚠ RAM_CE, RAM_OE and RAM_WE ARE GONE (2026-09-09). They drove U8, which
      * left the board with ram.md 6.2. Boot mode moved into two of the three
      * macrocells they vacated and the third is left as a spare INPUT - the
      * first spare pin this part has ever had.
      *
      * RUN = 0 IS BOOT MODE and it is zero at reset, which is not a
      * preference: a 22V10 has one asynchronous reset shared by every
      * registered macrocell and it resets to ZERO. A bit that had to come up
      * SET could not live on this part at all.
      *
      * The four counter bits come out on pins nothing connects to. That is
      * deliberate - they are free test points on the signal that is hardest
      * to characterise from outside, and a 22V10 has no buried nodes. */}
    <chip
      name="U6"
      footprint="dip24_w0.3in"
      pinLabels={labels(gal22v10({
        2: "FAST_E", 3: "/RESET", 4: "/IOPAGE", 5: "LA7", 6: "LA6",
        7: "LA5", 8: "R/W", 9: "LA4", 10: "/WAIT", 11: "LA0",
        14: "/BOOTOE", 15: "/IOSEL", 16: "C0", 17: "C1", 18: "E", 19: "Q",
        20: "C2", 21: "C3", 22: "RUN", 23: "SPARE",
      }))}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        CLK: "net.CLK25", FAST_E: "net.GND", nRESET: "net.nRESET",
        nIOPAGE: "net.nIOPAGE_MB", LA7: la(7), LA6: la(6),
        LA5: la(5), LA4: la(4), LA0: la(0),
        R_W: "net.R_W", nWAIT: "net.nWAIT",
        nIOSEL: "net.nIOSEL", E: "net.E", Q: "net.Q",
        nBOOTOE: "net.BOOT_OE", RUN: "net.RUN",
        /* ⭐ THE COUNTER BITS ARE A SIGNAL NOW, not four test points. U10
         * decodes them as the bus phase: RAS at count 4, CAS at 7, both
         * released at 10 (gal/u10.pld). They were on pins nothing connected
         * to precisely so they could be probed - and it turned out the DRAM
         * controller wanted exactly that.
         *
         * ⚠ THEY FREEZE WHEN /WAIT FREEZES THEM, which is correct for the
         * access half and fatal for the refresh half - see U10 and U17. */
        C0: "net.C0", C1: "net.C1", C2: "net.C2", C3: "net.C3",
      }}
      noConnect={["SPARE"]}
    />

    {/* U7 - power-on reset. Every card takes /RESET as an input and no card
      * budgeted the supervisor; machine.md 2.1 puts it here. */}
    <chip
      name="U7"
      footprint="sot23_3"
      pinLabels={{ pin1: "GND", pin2: "nRST", pin3: "VCC" }}
      connections={{ GND: "net.GND", VCC: "net.V5", nRST: "net.nRESET" }}
    />

    {/* ------------------------------------------- the space decode ------- */}
    {/* U9 - which memory, if any, is this? gal/u9.pld is the source of truth
      * and gal/jedec.check.ts checks its fuses against gal/u9.model.ts over
      * all 16,384 input combinations; Atmel's own CUPL agrees with them.
      *
      * ram.md 11 item 6 said this part might not fit a GAL22V10 - ten outputs
      * counted against ten, before inputs. It fits at SIX outputs and fourteen
      * inputs, with two macrocells left as spare inputs, because two of the
      * counts were wrong: the four SIMM selects collapse to one (U10 takes
      * physical A23/A22 and picks its own RAS), and the two map-SRAM chip
      * enables were never on the list at all.
      *
      * ⚠ IOPAGE COMES IN FROM U3 AND GOES OUT TO THE BACKPLANE, and they are
      * two nets. Reading back the wire this part drives would be a
      * combinational loop: above 2 MB U9 pulls /IOPAGE low, which would then
      * de-qualify the SIMM decode that asserted it.
      *
      * ⭐ LA3 LEFT THIS PART ON 2026-09-09 and pin 14 is free. It split the
      * two map bytes - $FFA0-$FFA7 low, $FFA8-$FFAF high - and it is also the
      * TASK bit of the write index U5 puts on MAPA3, so the high byte landed
      * in the other task's entry and nothing above physical 2 MB was
      * reachable. The two bytes have two WINDOWS now, $FF90-$FF9F and
      * $FFA0-$FFAF, out of 32 bytes that decoded nowhere.
      * hardware/ram.md 4.3, docs/design-review2.md M-1. */}
    <chip
      name="U9"
      footprint="dip24_w0.3in"
      pinLabels={labels(gal22v10({
        1: "A24", 2: "A23", 3: "A22", 4: "A21", 5: "A20", 6: "A19",
        7: "/IOPAGE_MB", 8: "RUN", 9: "LA7", 10: "LA6", 11: "LA5",
        13: "LA4", 23: "R/W",
        15: "/MAP_CE_LO", 16: "/MAP_CE_HI", 17: "/ROM_CE0",
        18: "/IOPAGE", 19: "DRAM_SEL", 20: "/ROM_CE1",
      }))}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        A24: pa(24), A23: pa(23), A22: pa(22), A21: pa(21),
        A20: pa(20), A19: pa(19),
        nIOPAGE_MB: "net.nIOPAGE_MB", RUN: "net.RUN",
        LA7: la(7), LA6: la(6), LA5: la(5), LA4: la(4),
        R_W: "net.R_W",
        nMAP_CE_LO: "net.MAP_CE_LO", nMAP_CE_HI: "net.MAP_CE_HI",
        nROM_CE0: "net.ROM_CE0", nROM_CE1: "net.ROM_CE1",
        nIOPAGE: "net.nIOPAGE", DRAM_SEL: "net.DRAM_SEL",
      }}
    />

    {/* --------------------------------------------- the boot ROM --------- */}
    {/* machine.md 7.2, 1 MB at physical 2.0-3.0 M. It holds the boot monitor
      * in its first 8 KB - including the $FFC0-$FFFF vector table, which is
      * why a real HD63C09E is a valid part for the socket again - and a
      * read-only NitrOS-9 ROM disk in the rest.
      *
      * Two packages because no 5 V 1M x 8 part comes in a DIP. Physical A19
      * picks between them, and during boot and vector cycles U16 drives it
      * low, so both land in device 0's first 8 KB.
      *
      * ⚠ THE PINOUT IS UNVERIFIED - lib/parts.ts FLASH_512K names the two
      * pins that differ from the SRAM sitting next to it in that file, and
      * `npm run check` lists this part until a datasheet is fetched. It is
      * the first unverified pinout on this board since 2026-09-06, and
      * hardware/history.md finding 4 is what happened last time.
      *
      * /OE is tied low and R/W rides in the chip enable (gal/u9.pld) - so a
      * stray write to ROM space selects nothing instead of fighting the CPU
      * for the whole of E-high. /WE is tied high: these are programmed in a
      * socket, not in circuit. */}
    {[0, 1].map((n) => (
      <chip
        key={n}
        name={`U1${4 + n}`}
        footprint={FLASH_512K.footprint}
        pinLabels={labels(FLASH_512K)}
        connections={{
          VCC: "net.V5", GND: "net.GND",
          ...busConnections("A", 19, pa),
          ...Object.fromEntries(Array.from({ length: 8 }, (_, i) => [`DQ${i}`, d(i)])),
          nCE: `net.ROM_CE${n}`, nOE: "net.GND", nWE: "net.V5",
        }}
      />
    ))}

    {/* U16 - the boot address buffer. It drives physical A20-A13 to zero
      * whenever the map SRAMs are deselected: for the whole of boot mode, and
      * for the vector page forever.
      *
      * ⚠ EIGHT BITS, NOT SEVEN, and A20 is why. The ROM needs A19-A13 above
      * the untranslated A12-A0 - but A20 also goes to the BACKPLANE, and a
      * floating A20 during a boot fetch would let the video card's VRAM
      * select (A20 = 0, A19 = 1) answer at random. Driving all eight to zero
      * puts every card's memory decode out of range by construction.
      *
      * A24-A21 still float during boot, and that is deliberate rather than
      * overlooked: they never leave the motherboard, and every U9 equation
      * that reads them is qualified on RUN.
      *
      * ⭐ A '244 AND NOT THE '541 machine.md 7.2 first named. Both are octal
      * three-state buffers; the '244's datasheet is in the repository and the
      * '541's is not, so the '244 is the one whose pin numbering is read
      * rather than remembered. Its two enables tie together. */}
    <chip
      name="U16"
      footprint={HCT244.footprint}
      pinLabels={labels(HCT244)}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        n1OE: "net.BOOT_OE", n2OE: "net.BOOT_OE",
        "1A1": "net.GND", "1A2": "net.GND", "1A3": "net.GND", "1A4": "net.GND",
        "2A1": "net.GND", "2A2": "net.GND", "2A3": "net.GND", "2A4": "net.GND",
        "1Y1": pa(20), "1Y2": pa(19), "1Y3": pa(18), "1Y4": pa(17),
        "2Y1": pa(16), "2Y2": pa(15), "2Y3": pa(14), "2Y4": pa(13),
      }}
    />

    {/* ------------------------------------------------ system memory ----- */}
    {/* U10 - the SIMM controller. gal/u10.pld is the source of truth and
      * gal/jedec.check.ts checks its fuses against gal/u10.model.ts over 1,920
      * clock edges; Atmel's own CUPL agrees with them.
      *
      * ram.md 11 item 6 said this part "has not been counted at all". Counting
      * it moved three things:
      *
      *  ⭐ THE MUX SELECT IS `E` AND IS NOT AN OUTPUT. E is high for counts
      *     6..11 of U6's divider, which is exactly the column window, so U11-U13
      *     take a wire from the backplane. That is the macrocell that made a
      *     nine-output design fit - and it is what a 1970s DRAM controller on a
      *     6800-family bus would have done anyway.
      *  ⭐ /WAIT IS NOT NEEDED AND IS NOT HERE. A bus cycle is twelve CLK25
      *     counts; the access owns six (4..9) and a refresh burst is four, which
      *     fits in the gap. ram.md 6.3's line item lists /WAIT; this part does
      *     not drive it, and the DRAM controller never stalls the CPU.
      *  ⚠ THE REFRESH TIMEBASE IS A PACKAGE - U17 below, and it was on nobody's
      *     list.
      *
      * TWO TIMEBASES. The ACCESS decodes C3..C0, so it stalls when E stalls -
      * correct, because a stalled cycle's data is not wanted yet. The REFRESH
      * must not: /WAIT freezes that counter (machine.md 5 item 8) and a frozen
      * refresh is lost data, so it runs off U17. machine.md 5 item 10 is the
      * rule and this is the part it was written for. */}
    <chip
      name="U10"
      footprint="dip24_w0.3in"
      pinLabels={labels(gal22v10({
        2: "DRAM_SEL", 3: "A23", 4: "A22", 5: "C0", 6: "C1", 7: "C2", 8: "C3",
        9: "R/W", 10: "REFCLK", 11: "/RESET",
        14: "RF1", 15: "REFQ", 16: "RF0",
        17: "/RAS0", 18: "/CAS", 19: "/RAS1", 20: "/RAS2", 21: "/RAS3",
        22: "/DRAM_WE", 23: "SPARE",
      }))}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        CLK: "net.CLK25", DRAM_SEL: "net.DRAM_SEL", nRESET: "net.nRESET",
        A23: pa(23), A22: pa(22),
        C0: "net.C0", C1: "net.C1", C2: "net.C2", C3: "net.C3",
        R_W: "net.R_W", REFCLK: "net.REFCLK",
        nRAS0: "net.RAS0", nRAS1: "net.RAS1", nRAS2: "net.RAS2",
        nRAS3: "net.RAS3", nCAS: "net.CAS", nDRAM_WE: "net.DRAM_WE",
      }}
      /* The refresh sequencer's three state bits come out on pins nothing
       * connects to - free test points on the one thing here that cannot be
       * observed from the bus, the same call U6 makes for its counter. */
      noConnect={["RF0", "RF1", "REFQ", "SPARE"]}
    />

    {/* U17 - the refresh timebase, and it was on nobody's list.
      *
      * ⚠ ram.md 6.3's "refresh needs no counter" is about the ROW counter,
      * which CAS-before-RAS genuinely deletes - the DRAM counts its own row.
      * The INTERVAL timer is a different thing: 15.6 us of CLK25 is 393 counts,
      * nine macrocells on a part that has ten.
      *
      * Q8 toggles every 256 counts = 10.16 us, and U10 refreshes on every
      * TRANSITION, so 512 rows take 5.2 ms against the DRAM's 8 ms - 35 % of
      * margin. Q7 would be 5.08 us and merely wasteful; Q9 would be 20.3 us and
      * too slow.
      *
      * ⚠ FREE-RUNNING ON CLK25, NOT ON E, and that is the whole reason it is a
      * package. /WAIT holds U6's divider, so a refresh interval taken from the
      * bus would stop for the 40.7 us the video card can hold it.
      *
      * The alternative that was rejected: HSYNC is on the backplane and is
      * 31.78 us, so two bursts a line would do. But it comes from the video
      * card, and a machine whose RAM forgets when you pull the video card is
      * the failure machine.md 1 puts the master oscillator on the motherboard
      * to avoid - the same argument, one subsystem along. */}
    <chip
      name="U17"
      footprint={HC4040.footprint}
      pinLabels={labels(HC4040)}
      connections={{
        VCC: "net.V5", GND: "net.GND",
        CLK: "net.CLK25",
        /* MR is ACTIVE HIGH on a 4040. Tied low: the counter free-runs and its
         * phase is irrelevant - only the interval between transitions matters,
         * and U10's REFQ makes the first one after reset a normal request. */
        MR: "net.GND",
        Q8: "net.REFCLK",
      }}
      noConnect={["Q0", "Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q9", "Q10", "Q11"]}
    />

    {/* U11-U13 - the RAS/CAS address mux, 11 bits. A 4 MB 30-pin SIMM is
      * 4M x 8: 22 address bits, 11 row and 11 column, multiplexed onto eleven
      * pins. Three quad muxes give twelve lines and eleven are used.
      *
      * ROW IS PHYSICAL A10..A0 AND COLUMN IS A21..A11. A 30-pin module is
      * BYTE-wide, so its A0 is the CPU's A0 - there is no low bit hidden
      * inside it the way there is on a x16 or x32 module.
      *
      * ⭐ SEL IS `E`, not a GAL output (gal/u10.pld). A '157's pin 1 is A/B
      * with the bar over the A, so SEL low selects the A inputs - and E is low
      * for counts 0..5, which is the row window. One wire.
      *
      * ⚠ THE MAPPING IS FOR 4M x 8 MODULES AND A 1M x 8 WILL NOT WORK IN IT.
      * A 1 MB module has ten row and ten column bits and ignores MA10, which
      * drops physical A10 out of the address entirely - so its 1 MB would not
      * be contiguous and would alias. The fix is a different column mapping,
      * which is board wiring rather than a jumper: it is a build-time choice.
      * ram.md 11 item 7 recommends 1 MB modules on availability grounds and
      * was written without this in view. */}
    {[0, 1, 2].map((n) => (
      <chip
        key={n}
        name={`U1${1 + n}`}
        footprint={HC157.footprint}
        pinLabels={labels(HC157)}
        connections={{
          VCC: "net.V5", GND: "net.GND", nE: "net.GND", SEL: "net.E",
          ...Object.fromEntries([0, 1, 2, 3].flatMap((i) => {
            const bit = n * 4 + i
            return bit > 10 ? [] : [
              [`${i + 1}A`, pa(bit)],
              [`${i + 1}B`, pa(11 + bit)],
              [`${i + 1}Y`, `net.MA${bit}`],
            ]
          })),
        }}
        noConnect={n === 2 ? ["4A", "4B", "4Y"] : []}
      />
    ))}

    {/* Four 30-pin SIMM sockets - 4 to 16 MB, and ALL of the machine's RAM
      * (ram.md 6). They are at physical 4-20 M, which is above everything a
      * card can see, so nothing on a slot ever decodes them.
      *
      * ⚠ THE FOOTPRINT IS A PIN ROW, not a SIMM socket: the pad grid and the
      * numbering are right and the outline is not, the same caveat the slot
      * socket carries (hardware/README.md open item 2).
      *
      * DQ8 is the parity bit on a x9 module and is left unconnected - this
      * machine does not check parity, and a x8 module has no such pin. */}
    {Array.from({ length: SIMMS }, (_, n) => (
      <chip
        key={n}
        name={`SIMM${n}`}
        footprint={SIMM30.footprint}
        pinLabels={labels(SIMM30)}
        connections={{
          VCC: "net.V5", GND: "net.GND",
          ...Object.fromEntries(Array.from({ length: 11 }, (_, i) => [`A${i}`, `net.MA${i}`])),
          ...Object.fromEntries(Array.from({ length: 8 }, (_, i) => [`DQ${i}`, d(i)])),
          nRAS: `net.RAS${n}`, nCAS: "net.CAS", nWE: "net.DRAM_WE",
        }}
        noConnect={["DQ8", "nCASP", "NC"]}
      />
    ))}

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
