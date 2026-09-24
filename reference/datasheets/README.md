# `reference/datasheets/`

**Not in git** — see [`../README.md`](../README.md). Expected contents: the parts **more than one card uses**. A part only one component uses is in that component's own `reference/` (since 2026-09-23).

## The CPU and its candidates

Moved on 2026-09-23 to the component that uses them: [`hardware/cpu/reference/`](../../hardware/cpu/reference/).

## The audio card's converters

Moved on 2026-09-23 to the component that uses them: [`hardware/audio/reference/`](../../hardware/audio/reference/).

## The logic the boards actually fit

Fetched 2026-09-06 to close `hardware/README.md` open item 1 — `hardware/tools/lib/parts.ts`
carried DIP pin *numbers* written from familiarity, with no datasheet behind any of them.
Sources are named because the part on the board is a period type, not the modern SKU: the
TI `SN74HC…` sheets are the family documents, and pin numbering is what they are here for.

| File | What | Cited by |
|---|---|---|
| `sn74hc574.pdf` | TI SN74HC574 octal D flip-flop | `hardware/cpu/docs/plan.md` §3.6 (the read-data latch — the design calls for the LVC part; this is the family datasheet), and `parts.ts` `HC574` |
| `sn74hc245.pdf` | TI SN74HC245 octal bus transceiver | `parts.ts` `HC245` — break-before-make isolation between the map SRAM and D0–D7 |
| `sn74hc157.pdf` | TI SN74HC157 quad 2:1 multiplexer | `parts.ts` `HC157` — the mux on the map SRAM address |
| `sn74hc244.pdf` | TI SN74HC244 octal buffer / line driver | `graphics.md`, `ps2.md`, and `audio.md` §10.3.5 / §16 item 37 — its 23 ns is the delay the audio card's sum crosses on its way to the state file |
| `SN74AHC574.pdf` | TI SN54AHC574 / **SN74AHC574** octal D-type flip-flop | `hardware/archive/video/docs/graphics.md` §14.2.6 — **the `V_IH` half of why the dot path is `AHCT` and not `AHC`.** Recommended operating conditions: `V_IH` = **3.85 V at `V_CC` = 5.5 V**, against the framebuffer SRAMs' 2.4 V `V_OH`. ⚠ **This is the `AHC` part, not the `AHCT` one the card actually specifies** — it is here for the threshold comparison, and an `SN74AHCT574` sheet is still wanted |
| `sn74hc273.pdf` | TI SN74HC273 octal D flip-flop with clear | `graphics.md`, `ps2.md`, `audio.md` |

## The memories the cards fit

Moved on 2026-09-23 to the component that uses them: [`hardware/mainboard/reference/`](../../hardware/mainboard/reference/), [`hardware/video3/reference/`](../../hardware/video3/reference/) and [`hardware/audio/reference/`](../../hardware/audio/reference/).

## The serial card's UART

Moved on 2026-09-23 to the component that uses them: [`hardware/io/serial/reference/`](../../hardware/io/serial/reference/).

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
| a 30-pin SIMM module sheet, or the JEDEC standard | `tools/lib/parts.ts` `SIMM30`, the **last** part in `KNOWN_UNVERIFIED`. It also wants `hardware/README.md` open item 2's measured socket footprint |

⚠ **How these were fetched, because it is not obvious.** Octopart's HTML
(`octopart.com/part/...`) needs a full browser header set and **rate-limits hard** after a
few dozen requests — it returns 403 for roughly an hour afterwards. Its PDF CDN
(`datasheet.octopart.com`) is **not** rate-limited and serves vendor PDFs directly, so the
working route is: find the CDN URL with a web search, then fetch it. ⛔ **Mouser, Digi-Key
and Newark are all in the sandbox allowlist and all three bot-block**, Mouser with an
Akamai challenge that returns **HTTP 200 with an HTML body**, so a naive fetch saves a
denial page under a `.pdf` name. Check `file(1)` says `PDF document` before trusting a
download.
