/* What every part IS, and what it DOES here — the hover text on the drawings.
 *
 * Two separate things, deliberately kept apart:
 *
 *   FAMILY   the datasheet fact. A '574 is an octal D flip-flop wherever it
 *            sits, so this is keyed by part number and written once.
 *   ROLE     the circuit fact. Keyed by `card:label`, because the same part
 *            number does different jobs on different cards - `74HC244 addr`
 *            on net and `74HC244 VSTAT` on video share nothing but silicon.
 *
 * ⚠ A ROLE IS A CLAIM ABOUT THE DESIGN and can go stale exactly like a
 * headline number. Where the card's own document is the authority the role
 * cites its section, so the two can be compared. `place.check.ts` asserts that
 * every placed part has both entries - an unlabelled part is a part nobody can
 * explain, and this file is worth having only if it is complete.
 */

/** The datasheet fact, by part number. */
export const FAMILY: Record<string, string> = {
  /* --- programmable logic --- */
  ATF1508AS: "EEPROM CPLD, 128 macrocells in 8 logic blocks, PLCC-84. A logic block sees only 40 signals through the switch matrix — the limit that binds before macrocells or pins.",
  GAL22V10: "Electrically-erasable PLD: 10 macrocells, 12 dedicated inputs, 8–16 product terms per output depending on position.",

  /* --- memory --- */
  AS6C8016: "512K × 16 asynchronous CMOS SRAM, 55 ns, with /LB and /UB byte enables.",
  AS6C4008: "512K × 8 asynchronous CMOS SRAM, 55 ns.",
  IS61C6416: "64K × 16 asynchronous SRAM, 10–15 ns — fast enough to answer inside one 39.7 ns dot.",
  "32Kx8": "32K × 8 asynchronous SRAM.",
  "62256": "32K × 8 asynchronous SRAM.",
  "6264": "8K × 8 asynchronous SRAM.",
  "6116": "2K × 8 asynchronous SRAM.",

  /* --- registers, latches and buffers --- */
  "74AHCT574": "Octal D flip-flop with 3-state outputs and a common clock — edge-triggered, so it samples at one instant rather than following its input.",
  "74HC574": "Octal D flip-flop with 3-state outputs and a common clock.",
  "74HC573": "Octal transparent D latch with 3-state outputs — follows its input while the enable is high, holds when it falls.",
  "74AHCT273": "Octal D flip-flop with an asynchronous master reset and no 3-state — the reset is why it suits a blanking path.",
  "74HC273": "Octal D flip-flop with asynchronous master reset.",
  "74HC244": "Octal 3-state buffer in two independent nibbles — a one-way gate onto a shared bus.",
  "74AHCT244": "Octal 3-state buffer in two independent nibbles.",
  "74HC245": "Octal bus transceiver: 3-state, bidirectional, with a direction pin.",
  "74HCT245": "Octal bus transceiver, TTL-level inputs.",
  "74LVC125": "Quad 3-state buffer, 5 V-tolerant inputs on a 3.3 V rail — a level translator that needs no separate part.",

  /* --- selectors --- */
  "74AHCT153": "Dual 4-to-1 multiplexer with common select lines.",
  "74HC157": "Quad 2-to-1 multiplexer.",
  "74HC138": "3-to-8 line decoder — exactly one output low, which is what makes mutually exclusive strobes cheap.",
  "74HC4066": "Quad bilateral analogue switch.",

  /* --- counters and arithmetic --- */
  "74AHCT163A": "Synchronous 4-bit binary counter with synchronous load and clear — the load is a clocked edge, not a level, so it cannot glitch.",
  "74HC163": "Synchronous 4-bit binary counter with synchronous load and clear.",
  "74HC193": "Presettable 4-bit up/down binary counter.",
  "74HC393": "Dual 4-bit binary ripple counter.",
  "74HC4020": "14-stage binary ripple counter.",
  "74HC4040": "12-stage binary ripple counter.",
  "74HC590": "8-bit binary counter with a 3-state output register — counter and register in one package.",
  "74HC283": "4-bit binary full adder with fast carry.",
  "74HC688": "8-bit magnitude comparator, equality output.",

  /* --- shift registers --- */
  "74HC165": "8-bit parallel-in, serial-out shift register.",
  "74HC595": "8-bit serial-in shift register with a separate output latch — the output does not move while the shift is in progress.",
  "74HCT595": "8-bit serial-in shift register with output latch, TTL-level inputs.",

  /* --- gates and timing --- */
  "74HC00": "Quad 2-input NAND.",
  "74HC86": "Quad 2-input XOR.",
  "74HCT132": "Quad 2-input NAND with Schmitt-trigger inputs — hysteresis, for a slow or noisy edge.",
  "7407": "Hex buffer with open-collector outputs — drives a wired-AND line, and tolerates a higher pull-up rail than its own.",
  "74HC221": "Dual monostable multivibrator with Schmitt-trigger inputs.",
  "74HC123": "Dual retriggerable monostable multivibrator.",

  /* --- analogue and interface --- */
  AD7528: "Dual 8-bit multiplying DAC. The reference is an input, so the output is a product — which is how one part does both level and pan.",
  TL074: "Quad JFET-input op-amp.",
  TL072: "Dual JFET-input op-amp.",
  NJM4556A: "Dual high-current op-amp, ~70 mA per channel — enough to drive headphones directly.",
  TL16C550C: "UART with 16-byte transmit and receive FIFOs — eight registers, against a 6551's four.",
  MAX232: "Dual RS-232 driver and receiver with an on-chip charge pump, so the card needs no negative rail.",
  SN75C1168: "Quad differential line driver/receiver pair.",

  /* --- clocks --- */
  osc: "Packaged crystal oscillator — a clock with no external network to get wrong.",
  xtal: "Quartz crystal.",
}

/** What the part does in THIS circuit, by `card:label`. */
export const ROLE: Record<string, string> = {
  /* ---------------- video ---------------- */
  "video:ATF1508AS vaddr/vctrl/vsup": "The card's three CPLDs. `vaddr` is the address datapath (scan counters, WPTR, the tile/list sources); `vctrl` is sync, the sequencer, span control and the spare-access arbiter; `vsup` holds the register-file address, the span length counter, the fetch-rank select and the palette write path. graphics.md §10.1.6.",
  "video:AS6C8016 512Kx16": "The 512 KB framebuffer, four-way interleaved so one fetch reads four adjacent pixels at once. Byte b lives at chip b[1:0], address b[18:2]. §2.1.",
  "video:IS61C6416 64Kx16 LUT": "The 256-entry palette. Read every 39.7 ns dot, which is why it has to be a 10–15 ns part. §6.1.",
  "video:32Kx8 regfile": "The card's register file — §13's 32 registers, addressed by `vsup` and read out continuously.",
  "video:74AHCT574 fetch": "⭐ TWO RANKS OF FOUR, in series. Rank A holds this slot's fetch group and rank B the previous one, so the four chips can present two different groups in the same slot — which is what byte-granular horizontal scroll needs and what one rank provably could not do. Exactly one rank per chip drives, chosen by output enable because `c < HSCROLL[1:0]` is constant for a whole line. §8.2, §19 item 28.",
  "video:74AHCT153 mux": "The pixel mux: 4-to-1 on `MUXSEL`, selecting one of the four interleaved chips per dot. The select is the dot phase plus HSCROLL[1:0], mod 4. §6.1.",
  "video:74AHCT574 index": "Latches the fetched pixel byte and drives it at the LUT's address pins — one lookup per dot.",
  "video:74AHCT273 out": "The post-LUT output register, feeding the video DACs. Its asynchronous master reset is `BLANK`, which is how blanking costs no extra part. §9.2.",
  "video:74AHCT163A PIDX": "The palette index counter — loadable, and auto-incrementing after each `PDATH` commit so a whole palette is written without re-addressing. ⚠ Replaces the `74HC593`, which is discontinued; the two ordinary counters load from the data bus instead of sharing the counter's own output pins, which deletes one of the two bus turnarounds. §9, §19 item 9.",
  "video:74AHCT244 pidx-oe": "Puts the index counter onto the LUT's address bus for the duration of a palette commit, and releases it. The pixel path owns that bus every other dot — §13.1's snow rule is this turnaround.",
  "video:74HC573 PDAT": "`PDATL` and `PDATH` — hold the 16-bit palette entry until the write to `PDATH` commits both halves to the LUT together.",
  "video:74HC244 lbyte": "Puts the display list's fetched descriptor byte onto the card's internal data bus, so a `MOVE` operand reaches the same register write path the CPU uses. §10.3.3.",
  "video:74HC574 pw-data": "The posted VRAM write's data latch: captures the CPU's byte at `E` fall so the bus cycle can end before the span writer has run. §3.1.1.",
  "video:74HC574 pw-addr": "The posted write's address latch — 19 bits across three packages, held while the span writer retires.",
  "video:74HC245 rdbk": "Bridges the card's internal data bus to the backplane for register read-back.",
  "video:74HC574 vread": "The VRAM read latch — §11's read-back path, which is what lets a windowing OS avoid keeping a 128 KB shadow of the screen in system RAM.",
  "video:74HC244 VSTAT": "Drives `VSTAT` onto the data bus on a read: `SPANBUSY`, `VBLANK`, `HBLANK` and the IRQ flag. Read-only and outside VRAM, so polling it never triggers `/WAIT`. §12.1.",
  "video:74HC244 fanout": "Clock and load fan-out, and carries `HSYNC`/`VSYNC` out to the backplane at TTL level for §12.2's raster-compare timer in the CPU module.",

  /* ---------------- audio ---------------- */
  "audio:ATF1508AS": "U1 is the register block, host interface and slot decode; U2 (`aseq`) is the microcoded sequencer — a work-type selects one of six micro-op sequences and every control output is a decode of (type, step). U2 is exactly full at 128 of 128 macrocells. audio.md §10.2.",
  "audio:28.375 MHz osc": "The PAL colour clock, and the card's whole time base: ÷8 gives the 3.546895 MHz period reference and ÷5 the 709,379 Hz CIA-B tempo clock. Eight slots per colour clock.",
  "audio:AS6C4008 sample RAM": "512 KB of sample memory — the card holds its own samples rather than fetching them across the backplane.",
  "audio:IS61C6416 state file": "The channel state file: pointer, length, period, volume and the running counters for every channel, read and written by the sequencer twice per slot.",
  "audio:74HC590 counter": "Walks the state file's address during a micro-op sequence — counter and 3-state output register in one package.",
  "audio:74HC688 compare": "The event comparator: fires when a channel's `NEXT` count reaches the running period reference, which is what makes a sample due.",
  "audio:74HC283 adder": "The 16-bit adder the sequencer shares across every channel — `NEXT += PER`, `PTR + 1` and `CNT − 1` are all this one datapath.",
  "audio:74HC574 ALAT": "The adder's A operand latch.",
  "audio:74HC574 BLAT": "The adder's B operand latch.",
  "audio:74HC244 B=$FFFF": "Drives a constant `$FFFF` onto the adder's B input, so a decrement is an addition — `A − 1` is `A + $FFFF` and the card needs no subtractor.",
  "audio:74HC244 sum OE": "Three-states the adder's sum back onto the state file's data bus, so the result of a read-modify-write returns down the path it came up.",
  "audio:74HC574 sample hold": "Holds the fetched sample byte for the slot in which its converter is strobed.",
  "audio:74HC574 conv port": "One per channel: presents that channel's byte at its DAC. Four are needed because §6.2's two converter windows collide with the slot walk order — channel 0's byte is on the bus in slot 0, channel 3's in slot 3.",
  "audio:74HC138 conv ctl": "Decodes one 3-bit control code into four converter port clocks and three DAC chip selects. They are mutually exclusive, so eight outputs cover idle plus all seven — which is what bought U2 six pins it did not have.",
  "audio:74HC00 /WE gate": "Gates the state file's byte-lane write enables with the second half of the slot clock, so a write lands after the address has settled.",
  "audio:AD7528 dual MDAC": "The output converters. The reference input is what carries volume and pan, so level and position are a multiplication rather than a second stage.",
  "audio:TL074": "The output filter and summing stages.",
  "audio:TL072": "Output buffering.",
  "audio:74HC4066": "Switches the reconstruction filter in and out — `ACTRL` b0/b1, so software can choose a filtered or raw output.",
  "audio:NJM4556A hp drv": "Drives the headphone jack directly, at ~70 mA per channel, so no separate amplifier is needed.",
  "audio:74HC574 pw": "The host's posted-write latch: captures the CPU's byte so the bus cycle can complete before the sequencer retires it.",
  "audio:74HC574 prefetch": "Read-back prefetch — one per state-file byte lane, so the host can read a value the sequencer is otherwise using every slot. §9.3.",

  /* ---------------- net ---------------- */
  "net:ATF1508AS U1/U2": "The card's logic: the 10BASE-T framer, Manchester encode/decode, the ring buffers' addressing and the host interface. net.md §9.",
  "net:20 MHz osc": "The bit-rate reference — 10 Mbit/s Manchester needs a 20 MHz clock to sample both half-bits.",
  "net:62256 RX ring": "The receive ring buffer: frames land here without the CPU, and are read out through the card's window.",
  "net:6264 TX": "The transmit buffer.",
  "net:74HC244 addr": "Buffers the buffer-RAM address between the framer's counter and the host's.",
  "net:74HCT245 data": "Bidirectional bridge between the card's buffer RAM and the backplane data bus.",
  "net:SN75C1168": "The 10BASE-T line interface — differential drive onto the twisted pair and differential receive from it.",
  "net:74HC86 edge": "XOR on the received signal: Manchester carries its clock in the mid-bit transition, and an XOR is what recovers it.",
  "net:74HC221 rec_clk": "The receive clock recovery monostable — retimes the sampling instant to the middle of each half-bit.",
  "net:74HC123 NIDLE": "Detects idle: no transition for longer than a bit time means the line is quiet, which is what carrier sense needs.",
  "net:74HC4020 NLP": "Generates the normal link pulse — the ~16 ms heartbeat 10BASE-T uses to say the link is alive when no frames are flowing.",

  /* ---------------- storage ---------------- */
  "storage:GAL22V10": "The card's sequencer and decode: the SPI state machine, block addressing and the host handshake. sdcard.md §8.",
  "storage:6116 block buffer": "A 512-byte block buffer, so a card read lands in memory the CPU can address ordinarily rather than being popped a byte at a time from a port.",
  "storage:74HCT595 MISO": "Shifts the card's serial reply into a parallel byte.",
  "storage:74HC165 MOSI": "Shifts a parallel byte out to the card, most significant bit first.",
  "storage:74HC574 hold": "Holds the assembled byte while the next one shifts.",
  "storage:74HC163 burst": "Counts the eight clocks of a byte, so the sequencer needs no state for the bit position.",
  "storage:74HC393 divider": "Divides the bus clock down to the SPI rate — slow for initialisation, fast once the card is in SPI mode.",
  "storage:74LVC125 3V3": "Level translation: an SD card is a 3.3 V part on a 5 V bus, and this buffer is 5 V-tolerant on its inputs.",
  "storage:74HC4040 blkaddr": "Walks the block buffer's address as bytes arrive, so a whole 512-byte transfer costs the CPU nothing.",
  "storage:74HC157 addr mux": "Chooses between the sequencer's address and the host's for the block buffer — the two never drive it at once.",
  "storage:74HCT245 data": "Bridges the block buffer to the backplane data bus.",

  /* ---------------- io ---------------- */
  "io:GAL22V10 ps2": "The PS/2 side: both ports' clock and data state machines, parity, and the start/stop framing. ps2.md §9.",
  "io:GAL22V10 serial": "The serial side's decode and handshake. serial.md §9.",
  "io:TL16C550C UART": "The UART, with 16-byte FIFOs in each direction — the depth is what makes 115,200 baud survivable under a shared-`/IRQ` dispatch that can take 191 µs.",
  "io:MAX232": "RS-232 levels for TX, RX and one handshake pair, with its own charge pump.",
  "io:7.3728 MHz xtal": "The UART's baud reference — 7.3728 MHz divides exactly to 115,200 and every rate below it.",
  "io:74HC273 IOCTRL": "The card's control register.",
  "io:74HC244 IOSTAT": "Drives the card's status byte onto the data bus on a read.",
  "io:7407 open-coll": "Open-collector drive for the PS/2 clock and data lines. Both are bidirectional wired-AND: a device or the host may pull low, neither may drive high, and the line idles high through a pull-up.",
  "io:74HCT132 Schmitt": "Squares up the PS/2 clock edges — the line is a slow open-collector rise through a pull-up, and hysteresis is what stops it double-clocking.",
  "io:74HC595 shift": "Assembles each port's incoming serial frame into a parallel byte.",
  "io:74HC193 bitcnt": "Counts the eleven bits of a PS/2 frame — start, eight data, parity, stop.",
  "io:74HC574 latch": "Holds the completed byte for the host to read.",
}

/** The motherboard, keyed by the reference designator on the drawing.
 *
 * ⚠ Several of these were repaired on 2026-09-09 and the roles say so, because
 * "U18 exists" is the whole of `design-review2.md` M-1's second half and the
 * next person to read this board will want to know why there are two `'245`s.
 */
export const MB_ROLE: Record<string, { fam: string; role: string }> = {
  "J0 6309 socket": { fam: "40-pin socket for the CPU module.",
    role: "The HD6309E's seat. What plugs in is an `STM32G431CBU6` presenting the 6309's bus - `machine.md` §5 item 6." },
  "U1 map lo": { fam: "2K \u00d7 8 asynchronous SRAM.",
    role: "The MMU's low map byte: physical `A20`\u2013`A13` for every one of the 8 KB blocks, indexed by {TASK, block}. Written through `$FFA0`\u2013`$FFAF`. `ram.md` \u00a74.3." },
  "U1B map hi": { fam: "2K \u00d7 8 asynchronous SRAM.",
    role: "The map's HIGH byte - physical `A24`\u2013`A21` and \u00a73.3's flags, written through `$FF90`\u2013`$FF9F`. \u26a0 Until 2026-09-09 its data pins went to the physical address bus and nowhere else, so this byte was neither readable nor writable and nothing above 2 MB was reachable. `design-review2.md` M-1." },
  "U3 GAL22V10": { fam: "Electrically-erasable PLD, 10 macrocells.",
    role: "The MMU's write decode and the map SRAMs' control: two block windows, the control window, and both isolation enables. \u26a0 FULL since 2026-09-09 - 7 outputs, 15 inputs, no spare pin - because M-1's repair needed a second isolation enable." },
  "U6 GAL22V10 E/Q": { fam: "Electrically-erasable PLD, 10 macrocells.",
    role: "The clock divider: E and Q in quadrature from the 25.175 MHz master, \u00f712 or \u00f78. Also `/IOSEL`, `/BOOTOE` and the `RUN` latch. Every registered macrocell carries a `/WAIT` hold term, which is how a card stops the machine. `gal/clkdec.pld`." },
  "U4 245 map lo": { fam: "Octal bus transceiver, 3-state, with a direction pin.",
    role: "Isolates the low map SRAM's data pins from the CPU's data bus, so the SRAM can drive physical `A20`\u2013`A13` continuously and still be written." },
  "U18 245 map hi": { fam: "Octal bus transceiver, 3-state, with a direction pin.",
    role: "\u2b50 The same job for the HIGH map byte, and it did not exist until 2026-09-09. `ram.md` \u00a73.1 costed the isolation at zero on the argument that both SRAMs sit on the same `D0`\u2013`D7` - two common-I/O SRAMs cannot, because their data pins ARE the physical address for the whole of every translation. Twelve bits of map need twelve bits of buffer and a `'245` is eight." },
  "U2 574": { fam: "Octal D flip-flop with 3-state outputs.",
    role: "The `TASK` latch - one bit selecting which half of the map is live, written at `$FFB0`. A task switch is one store." },
  "U5 157": { fam: "Quad 2-to-1 multiplexer.",
    role: "Chooses the map SRAM's index: the CPU's block number while the CPU is writing the map, the running logical address `A15`\u2013`A13` otherwise." },
  OSC1: { fam: "Packaged crystal oscillator.",
    role: "25.175 MHz - the VGA dot clock, and the master from which E and Q are divided. One oscillator times the whole machine." },
  U7: { fam: "Logic.",
    role: "Bus glue." },
  "U9 GAL22V10": { fam: "Electrically-erasable PLD, 10 macrocells.",
    role: "The physical-address decode: which of the four SIMM windows, the flash, or a card's `A20 = 1` buffer answers - and the two map SRAMs' separate chip enables, which is what makes a map write land in one byte and not the other." },
  "U10 GAL22V10": { fam: "Electrically-erasable PLD, 10 macrocells.",
    role: "DRAM control: `/RAS`, `/CAS` and `/WE` for the SIMMs, including the refresh cycle." },
  "U11 157": { fam: "Quad 2-to-1 multiplexer.",
    role: "DRAM row/column address multiplexing - a 30-pin SIMM takes its address in two halves." },
  "U12 157": { fam: "Quad 2-to-1 multiplexer.", role: "DRAM row/column address multiplexing." },
  "U13 157": { fam: "Quad 2-to-1 multiplexer.", role: "DRAM row/column address multiplexing." },
  "U17 4040 refresh": { fam: "12-stage binary ripple counter.",
    role: "The refresh row counter. It free-runs on `CLK25` rather than on E, because `/WAIT` can stop E for up to 40.7 \u00b5s and DRAM cannot wait - `machine.md` \u00a75 item 10's rule that a card's realtime scheduling never counts bus cycles." },
  "U14 SST39SF040": { fam: "512K \u00d7 8 flash memory.",
    role: "Boot ROM. Answers at physical 2.0\u20133.0 MB, and unconditionally in the vector page so `$FFFE` is a reset vector with the map switched off." },
  "U15 SST39SF040": { fam: "512K \u00d7 8 flash memory.", role: "The second half of the 1 MB boot ROM." },
  "U16 244 boot addr": { fam: "Octal 3-state buffer in two nibbles.",
    role: "Drives physical `A19`\u2013`A13` to zero while `BOOT` or `VECSEL` is asserted, so the ROM's page 0 answers before the map holds anything. \u26a0 It must drive exactly when the map SRAMs do not - `design-review2.md` M-2 and M-3 were both this net having no driver, or two." },
  "power in": { fam: "Power entry.", role: "+5 V for the whole machine; the cards take theirs through the backplane's five power pins." },
  "30-pin SIMM 0": { fam: "30-pin SIMM socket, 8 bits wide.",
    role: "System DRAM. One socket is required and three are optional. \u26a0 A 30-pin SIMM has NO presence-detect pins, so nothing can size memory in hardware - the boot monitor walks each socket with two complementary patterns instead. `ram.md` \u00a76.4.1." },
  "30-pin SIMM 1": { fam: "30-pin SIMM socket, 8 bits wide.", role: "Optional system DRAM." },
  "30-pin SIMM 2": { fam: "30-pin SIMM socket, 8 bits wide.", role: "Optional system DRAM." },
  "30-pin SIMM 3": { fam: "30-pin SIMM socket, 8 bits wide.", role: "Optional system DRAM - the fourth takes the machine to 16 MB." },
}
