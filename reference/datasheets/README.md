# `reference/datasheets/`

**Not in git** — see [`../README.md`](../README.md). Expected contents:

## The CPU and its candidates

| File | What | Cited by |
|---|---|---|
| `HD6309E_datasheet.pdf` | Hitachi HD63B09E / HD63C09E | `cpu/docs/plan.md` §3.3 — the real timing figures. **This is the authoritative one.** |
| `MC6809E.pdf` | Motorola MC6809E / MC68A09E / MC68B09E | `cpu/docs/plan.md`, `cpu/README.md` — `t_DSR`/`t_DHR`. **Superseded above 2 MHz:** its columns stop at the MC68B09E. |
| `stm32g4-refman.pdf` | ST RM0440 Rev 9, STM32G4 reference manual | `cpu/docs/plan.md`, `cpu/include/stm32g431.h` — every register constant, and the DMAMUX/EXTI verification |
| `stm32g431kb.pdf` | ST STM32G431 datasheet | `cpu/docs/plan.md` §3.2 — pin budget, and the `TT_a` 3.6 V pins that made buffers mandatory |
| `ATSAMD51G19A.pdf` | Microchip SAMD51 | `cpu/docs/plan.md` §3.7 — the MCU review, i.e. the part that was *not* chosen |

## The audio card's converters

| File | What | Cited by |
|---|---|---|
| `AD7528.pdf` | Analog Devices AD7528, **dual** 8-bit parallel multiplying DAC | `audio/docs/audio.md` §6.1–§6.3 — **the specified DAC.** The `VREF` input-resistance match (±1 %), the write timing, the glitch impulse, and the datasheet's own dual-attenuator application, which is what the card's volume stage is |
| `AD7545A.pdf` | Analog Devices AD7545A, 12-bit buffered multiplying DAC | `audio/docs/audio.md` §6.3 and §17 — **the period part.** Its `tWR` is the one number that decides whether 1989's part would actually have worked |
| `AD7545.pdf` | Analog Devices AD7545, the original | `audio/docs/audio.md` §6.3 — the pin-compatibility and timing comparison. **Note this is the plain `AD7545`, not the `AD7545A`** above; §6.3 explains why the difference matters |
| `LTC7545A.pdf` | Linear Technology LTC7545A, 12-bit parallel multiplying DAC | `audio/docs/audio.md` §6.3 — **superseded**, kept because the section's history and its `tWR`/glitch comparisons are argued against it |

## The logic the boards actually fit

Fetched 2026-09-06 to close `hardware/README.md` open item 1 — `hardware/lib/parts.ts`
carried DIP pin *numbers* written from familiarity, with no datasheet behind any of them.
Sources are named because the part on the board is a period type, not the modern SKU: the
TI `SN74HC…` sheets are the family documents, and pin numbering is what they are here for.

| File | What | Cited by |
|---|---|---|
| `CY7C128A.pdf` | Cypress CY7C128A, 2K × 8 SRAM, 15 ns (`-15PC` is the 300-mil DIP-24 grade) | `hardware/lib/parts.ts` `MAP_SRAM` — the MMU block map, `graphics.md` §6.3.1 |
| `AS6C4008.pdf` | Alliance Memory AS6C4008, 512K × 8 low-power SRAM, 55 ns, DIP-32 | `hardware/lib/parts.ts` `SRAM_512K` — the machine's system RAM, `machine.md` §7.1 |
| `sn74hc574.pdf` | TI SN74HC574 octal D flip-flop | `cpu/docs/plan.md` §3.6 (the read-data latch — the design calls for the LVC part; this is the family datasheet), and `parts.ts` `HC574` |
| `sn74hc245.pdf` | TI SN74HC245 octal bus transceiver | `parts.ts` `HC245` — break-before-make isolation between the map SRAM and D0–D7 |
| `sn74hc157.pdf` | TI SN74HC157 quad 2:1 multiplexer | `parts.ts` `HC157` — the mux on the map SRAM address |
| `sn74hc244.pdf` | TI SN74HC244 octal buffer / line driver | `graphics.md`, `ps2.md`, and `audio.md` §10.3.5 / §16 item 37 — its 23 ns is the delay the audio card's sum crosses on its way to the state file |
| `cd74hc283.pdf` | TI CD54HC283 / CD74HC283 / CD74HCT283, 4-bit binary full adder with fast carry, SCHS176E | **`audio/docs/audio.md` §10.3.5 and §16 item 37 — the number that re-timed the audio card's datapath.** §5.5: `A`/`B` → `C_OUT` **39 ns**, `C_IN` → `C_OUT` **39 ns**, `C_IN` → `S3` **46 ns** at 4.5 V / 50 pF / 25 °C max, so a 16-bit ripple is 163 ns of carry alone. It withdrew §16 item 34's 8-bit datapath and it is why one read-modify-write per colour clock is the audio card's arithmetic rate |
| `SN74F283.pdf` | TI SN54F283 / **SN74F283**, 4-bit binary full adder with fast carry, SDFS034B | **`audio/docs/audio.md` §16 item 37 open item 1 — the part that item said to price before costing.** Priced 2026-09-10 and **not taken.** Its speed is real (`C0`→`C4` **7.5 ns** max at 25 °C, 8.5 ns over temp, against the `'HC283`'s 39/49) but two numbers rule it out: `V_OH` is **2.7 V min**, which is the level incompatibility item 37 predicted, and `I_CC` is **55 mA per package**. ⛔ **And the packaging addendum lists no plastic DIP at all** — commercial orderable is `SN74F283D`, SOIC only |
| `CD74ACT283.pdf` | Harris/TI CD54AC283, CD74AC283, **CD54ACT283, CD74ACT283**, 4-bit binary full adder | ⭐ **`audio/docs/audio.md` §16 item 37 open item 1 — the candidate that replaces it, pending availability.** At 5 V, worst case over −40…85 °C: `A`/`B`→`C_OUT`, `C_IN`→`C_OUT`, `C_IN`→`S_n` all **16 ns**, `A`/`B`→`S_n` **16.5 ns** — a 16-bit ripple of **64 ns against the `'HC283`'s 163**, and that is already the over-temperature column. `V_OH` is **4.4 V**, so unlike the `'F283` it drives `74HC` inputs directly and costs no `74HCT` conversion. ⚠ Availability in a through-hole package is **not yet checked**, and that is the question `net.md` §13.6 puts first |
| `CD74HC4040.pdf` | TI CD54HC4040 / **CD74HC4040** / CD54HCT4040 / CD74HCT4040, 12-stage ripple counter | `hardware/lib/parts.ts` `HC4040` and `ram.md` §6.3.1 — the refresh timebase. ⛔ **It found three rotated pins**: 12 is `Q8` (not `Q10`), 13 is `Q7` (not `Q8`), 15 is `Q10` (not `Q7`) — a 3-cycle rotation, the same shape as finding 4's map SRAM, on the same board. `hardware/history.md` has what it would have cost. `MR` active high is confirmed |
| `SN74AHC574.pdf` | TI SN54AHC574 / **SN74AHC574** octal D-type flip-flop | `video/docs/graphics.md` §14.2.6 — **the `V_IH` half of why the dot path is `AHCT` and not `AHC`.** Recommended operating conditions: `V_IH` = **3.85 V at `V_CC` = 5.5 V**, against the framebuffer SRAMs' 2.4 V `V_OH`. ⚠ **This is the `AHC` part, not the `AHCT` one the card actually specifies** — it is here for the threshold comparison, and an `SN74AHCT574` sheet is still wanted |
| `sn74hc273.pdf` | TI SN74HC273 octal D flip-flop with clear | `graphics.md`, `ps2.md`, `audio.md` |
| `sn74hc595.pdf` | TI SN74HC595 8-bit shift register with output latch | `ps2.md` §3 — the receive shift register |
| `74hc_hct595.pdf` | Nexperia 74HC595 **and 74HCT595**, one document | `sdcard.md` §7 — the SD card's receive register is the **HCT** part deliberately, and the reason is an input threshold: 3.3 V `MISO` clears an HCT input's 2.0 V `V_IH`, so the return path needs no level shifter. That number is here and not in the TI HC sheet above |
| `sn74hc193.pdf` | TI SN74HC193 4-bit up/down counter | `ps2.md` |
| `sn74lvc125a.pdf` | TI SN74LVC125A quad bus buffer, 1.65–3.6 V | `sdcard.md` §7 — three of four gates level-shift `SCK`/`MOSI`/`/CS` down to 3.3 V; also `cpu/docs/plan.md` for the LVC family's 5 V-tolerant inputs |
| `ATF22V10C.pdf` | Microchip (Atmel) ATF22V10C — the in-production `GAL22V10` | the motherboard's U3 and U6, and the audio and I/O cards. `hardware/gal/jedec/gal22v10.ts` is built from its §10 fuse counts and §11 array diagram |
| `ATF1508AS.pdf` | Atmel/Microchip **ATF1508AS(L)**, Rev 0784P–PLD–7/05 — 5 V, 128 macrocells, 84/100/160-pin | **the video card's logic, all of it** (`graphics.md` §10.1.3). Icc vs frequency (p. 16) is the figure §14's power table needed; the DC table's separate `VCCINT` / `VCCIO` rails are why §10.1.3 can leave the 3.3 V `ATF1508ASV` question open |

## The memories the cards fit

Fetched 2026-09-10 from Octopart's datasheet CDN (`datasheet.octopart.com`), which serves
the vendor PDFs directly. These are the three parts whose numbers other documents were
**assuming** rather than reading.

| File | What | Cited by |
|---|---|---|
| `SST39SF040.pdf` | SST/Microchip SST39SF010A / SST39SF020A / **SST39SF040**, 512K × 8 MPF flash, DS25022A | `hardware/lib/parts.ts` `FLASH_512K` and `docs/machine.md` §7.2 — **the boot ROM.** It was the board's only unverified pinout from 2026-09-06; Figure 4 (32-pin PDIP) confirms all 32 pins, including the two the note flagged: **pin 3 is A15** and **pin 31 is `/WE`**, both already right. ⚠ **Pin 1 is A18 only on the 4 Mbit part** — NC on the 010A/020A, which share the footprint, so a smaller substitute silently drops the top address line. Grades 45/55/70 ns; 600-mil PDIP |
| `IS61C6416.pdf` | ISSI IS61C6416AL / IS62C6416AL / IS64C6416AL / IS65C6416AL, 64K × 16 SRAM, Rev. B | **`audio/docs/audio.md` §10.3.5 and §16 item 37 — the state file's write setup.** §16 item 37 open item 2 assumed `t_SD` = 6 ns with no sheet in the repository; **6 ns is exactly right, and only for the `-12` grade** the card specifies (`-15` is 9, `-35` is 20, `-45` is 25). It also carries the numbers the card never budgeted: `t_PWE` 9 ns, `t_AW` 9 ns, `t_HD` 0 ns. Packages are 44-pin SOJ and TSOP-II only |
| `AS6C8016.pdf` | Alliance Memory AS6C8016, 512K × 16 low-power SRAM, 55 ns, V 1.0 | `video/docs/graphics.md` §14.2 and §14.4 — **the framebuffer.** Confirms 55 ns, 44-pin 400-mil TSOP-II, 2.7–5.5 V, and `/LB`/`/UB`. ⚠ **Two numbers the power table should read again:** `I_CC` is **30 mA typ and 60 mA max**, and §14's table budgets the typ; standby 6 µA is the **LL** version's typ against a 50 µA max. ⚠ And **`V_OH` is 2.4 V min** — a TTL level, not a CMOS one, which is why the dot path has to stay `74AHCT` (§14.2.6) |

## The serial card's UART

| File | What | Cited by |
|---|---|---|
| `TL16C550C.pdf` | TI **TL16C550C / TL16C550CI** ACE with autoflow control, SLLS644I | `io/serial/docs/serial.md` §7.2, §7.3, §9.2 — **the specified UART**, and the part that closed §13 item 1 on 2026-09-10. It answers all three lookups that item named: the **N (PDIP-40) package is documented but "Not Recommended for New Designs" and appears in no ACTIVE row of the packaging addendum** — orderable is `FN` PLCC-44, `PT` LQFP-48, `PFB` TQFP-48; **FCR[7:6] is 00/01/10/11 → 1/4/8/14 bytes** (Table 7-4), so §5.4's trigger-of-14 is `FCR = $C1`; and the **character timeout** is `IIR = $0C` — at least one character in the RX FIFO, and neither a new character nor a host read for four continuous character times, timed off `RCLK` |
| `W65C51N.pdf` | WDC W65C51N ACIA | **Historical.** `serial.md` §3.3 ruled this part out over its transmit-empty defect, and §9.2 records that the whole `R6551A`/`G65SC51` hunt stopped existing when the card took the `TL16C550C`. Kept because §3 argues against it |

⭐ **The "missing, and wanted" `R6551A`/`G65SC51` note that stood here is retired.**
It said `serial.md` §3.4's speed grade rested on recalled figures from a part neither
distributor carries. §9.2 deleted the requirement on 2026-09-09: the `TL16C550C` takes no
clock from the bus, so there is no speed grade to match, and there is no defective sibling
to avoid. `hardware/README.md` open item 1 still quotes the old note.

## Still wanted

Ordered by what each would settle, not by how easy it is to get. Nothing below blocks a
present claim; each closes a ⚠ that a document is currently carrying.

| Part | What it would settle |
|---|---|
| **`SN74AHCT574`** (or any TI `74AHCT` family sheet) | `graphics.md` §14.2.6 cites the `AHC` threshold from a sheet and the **`AHCT` one from the family's standard 2.0 V, uncited**. Eleven packages on the video card are `AHCT` and the reason is now written down; the number behind it is not |
| **`74ACT283` availability**, and its current production status | `audio.md` §16 item 37 open item 1 — the part that replaced the refused `'F283`. The **electrical case is closed from `CD74ACT283.pdf`**; what is open is `net.md` §13.6's first question, and `AC`/`ACT` 283 is a sparse line. **Do not move the BOM until a through-hole one is confirmed orderable** |
| **`NJM4556A`** | `audio.md` §7.1's headphone driver — the analogue half of the card is the part that is still unmeasured. ⚠ A 1-page scan of the plain `NJM4556S` was fetched on 2026-09-10 and **deleted rather than kept**: it is the wrong variant and carries no extractable text, and a misleading reference is worse than an absent one |
| **`27C512`** (or `AT27C512R`) | `audio.md` §16 item 38 — §10.3's control store is four of them, and the access time is what decides whether the arrangement works at all |
| **`MAX232`** | `serial.md` §8's **120 kbit/s charge-pump ceiling**, which is what stops the card at 115,200 rather than the 460,800 the crystal allows. `io.circuit.tsx` cites it as "MAX232-class" and no sheet backs the number |
| **`SN75C1168`** | `net.md` §9's line driver |
| **`TL072` / `TL074`, `74HC4066`** | `audio.md` §6's filters and switching — the analogue section generally |
| a 30-pin SIMM module sheet, or the JEDEC standard | `lib/parts.ts` `SIMM30`, the **last** part in `KNOWN_UNVERIFIED`. It also wants `hardware/README.md` open item 2's measured socket footprint |

⚠ **How these were fetched, because it is not obvious.** Octopart's HTML
(`octopart.com/part/...`) needs a full browser header set and **rate-limits hard** after a
few dozen requests — it returns 403 for roughly an hour afterwards. Its PDF CDN
(`datasheet.octopart.com`) is **not** rate-limited and serves vendor PDFs directly, so the
working route is: find the CDN URL with a web search, then fetch it. ⛔ **Mouser, Digi-Key
and Newark are all in the sandbox allowlist and all three bot-block**, Mouser with an
Akamai challenge that returns **HTTP 200 with an HTML body**, so a naive fetch saves a
denial page under a `.pdf` name. Check `file(1)` says `PDF document` before trusting a
download.
