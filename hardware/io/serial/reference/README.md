# `hardware/io/serial/reference/`

Reference material for the serial card's UART, and the part it replaced.

**Not in git**: PDFs, scans, disk images and archives under any `reference/` are `.gitignore`d (see [the root `reference/` README](../../../../reference/README.md)). Expected contents, and what cites each:

| File | What | Cited by |
|---|---|---|
| `TL16C550C.pdf` | TI **TL16C550C / TL16C550CI** ACE with autoflow control, SLLS644I | `hardware/io/serial/docs/serial.md` §7.2, §7.3, §9.2 — **the specified UART**, and the part that closed §13 item 1 on 2026-09-10. It answers all three lookups that item named: the **N (PDIP-40) package is documented but "Not Recommended for New Designs" and appears in no ACTIVE row of the packaging addendum** — orderable is `FN` PLCC-44, `PT` LQFP-48, `PFB` TQFP-48; **FCR[7:6] is 00/01/10/11 → 1/4/8/14 bytes** (Table 7-4), so §5.4's trigger-of-14 is `FCR = $C1`; and the **character timeout** is `IIR = $0C` — at least one character in the RX FIFO, and neither a new character nor a host read for four continuous character times, timed off `RCLK` |
| `W65C51N.pdf` | WDC W65C51N ACIA | **Historical.** `serial.md` §3.3 ruled this part out over its transmit-empty defect, and §9.2 records that the whole `R6551A`/`G65SC51` hunt stopped existing when the card took the `TL16C550C`. Kept because §3 argues against it |
