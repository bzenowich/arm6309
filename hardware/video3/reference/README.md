# `hardware/video3/reference/`

Reference material for the video card's framebuffer SRAM.

**Not in git**: PDFs, scans, disk images and archives under any `reference/` are `.gitignore`d (see [the root `reference/` README](../../../reference/README.md)). Expected contents, and what cites each:

| File | What | Cited by |
|---|---|---|
| `AS6C8016.pdf` | Alliance Memory AS6C8016, 512K × 16 low-power SRAM, 55 ns, V 1.0 | `hardware/archive/video/docs/graphics.md` §14.2 and §14.4 — **the framebuffer.** Confirms 55 ns, 44-pin 400-mil TSOP-II, 2.7–5.5 V, and `/LB`/`/UB`. ⚠ **Two numbers the power table should read again:** `I_CC` is **30 mA typ and 60 mA max**, and §14's table budgets the typ; standby 6 µA is the **LL** version's typ against a 50 µA max. ⚠ And **`V_OH` is 2.4 V min** — a TTL level, not a CMOS one, which is why the dot path has to stay `74AHCT` (§14.2.6) |
