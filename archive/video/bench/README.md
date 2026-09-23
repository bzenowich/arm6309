# `archive/video/bench/` — the retired card's benches, frozen

⛔ **Nothing here runs, and nothing here is maintained.** These are the scripts and
testbenches that exercised the `video/` card — the machine's video card until
2026-09-20 — plus the ones for `software/demo/`, the bare-metal show that only ever
targeted it. They moved here on **2026-09-22**, when the NitrOS-9 recipe stopped being
able to build a non-`video3` flavour at all (`recipes/arm6309/arm6309.mak`: `-DV3=1` is
in `AFLAGS`, not in a caller's hands).

⚠ **Their paths are relative to where they used to live**, so they do not run from here
without editing. That is deliberate: a script that still runs is a script somebody will
still run, and the answer it gives would be about a card this machine does not have.

## What is here, and what it used to prove

| | |
|---|---|
| `run-vid.sh` | the NitrOS-9 **video console** on the host emulator, against `vtmodel.py`/`vgmodel.py` pixel for pixel, plus the IRQ-masked time. `docs/nitros9-av-plan.md` P1 and P2 |
| `run-video.sh` | the progress video — one scripted session, screen and serial console side by side, `nitros9-progress.mp4` |
| `run-demo.sh` | ⭐ **the whole machine with both cards**, `demo_tb`, ~4.5 h: `software/demo`'s show out of ROM, the audio A/B'd against libopenmpt, every checkpoint frame against `show.Model` |
| `run-demo-emu.sh` | the same show on the host emulator, in seconds |
| `run-replay.sh` | the module replayer alone on the CPU |
| `run-calib.sh`, `run-vramrate.sh`, `run-vramrate-rtl.sh` | the VRAM-rate measurements the demo's budget came out of |
| `demo_tb.sv` | the testbench `run-demo.sh` drives |
| `vsync_tb.sv` | raster geometry in all four `VMODE` codes, sync widths and polarity, blanking |
| `vaddr_tb.sv` | the bitmap scan address over whole lines, both scroll axes, both ring wraps, line doubling |
| `vtile_tb.sv` | the cell fetch cadence, both address concatenations, cell-mode scroll, the 32-row ring |
| `vspan_tb.sv` | all four `WMODE`s, the retire rate, `/WAIT`'s read/write rule, `WADV` chaining, the display list, the VBL interrupt |
| `vpal_tb.sv` | the palette |

## ⚠ What did NOT move, and why it matters

**The card's design sources are still live in `hardware/gal/`**, and
[`../../README.md`](../README.md) §"What did NOT move" is the record of that trade.
⛔ **With `demo_tb` here, the last thing that instantiated the card as a card is
gone** — so `hardware/gal/`'s `vaddr.v`, `vctrl.v`, `vsup.v`, `rfa.v`, `vlen.v` and
`pxsel.v` are now compiled by `gen.ts` and executed by **nothing**.

⚠ `software/demo/` itself stays where it is, and not out of sentiment:
`software/nitros9/tools/mktbox.py`'s `build_icons()` imports `show` and `mkshow` from
it, so **the ROM toolbox's icon art is generated from the demo's own drawing code**.
`software/demo/emu/machine.c` is likewise the host emulator every live bench still
runs. What retired is the demo's *benches*, not the demo's *code*.
