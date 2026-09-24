# `hardware/tools/gal/reference/`

Reference material for the programmable parts every card's logic is fitted to.

**Not in git**: PDFs, scans, disk images and archives under any `reference/` are `.gitignore`d (see [the root `reference/` README](../../../../reference/README.md)). Expected contents, and what cites each:

| File | What | Cited by |
|---|---|---|
| `ATF22V10C.pdf` | Microchip (Atmel) ATF22V10C — the in-production `GAL22V10` | the motherboard's U3 and U6, and the audio and I/O cards. `hardware/tools/gal/jedec/gal22v10.ts` is built from its §10 fuse counts and §11 array diagram |
| `ATF1508AS.pdf` | Atmel/Microchip **ATF1508AS(L)**, Rev 0784P–PLD–7/05 — 5 V, 128 macrocells, 84/100/160-pin | **the video card's logic, all of it** (`graphics.md` §10.1.3). Icc vs frequency (p. 16) is the figure §14's power table needed; the DC table's separate `VCCINT` / `VCCIO` rails are why §10.1.3 can leave the 3.3 V `ATF1508ASV` question open |
| `MAX7000.PDF` | Altera MAX 7000 family | `hardware/archive/video/docs/graphics.md` §10.1.2 — the period argument for CPLDs (tracked: small, and not a vendor download any more) |
