# `archive/` — retired designs, kept whole

**This directory holds card designs the machine no longer uses.** Nothing here is
deleted, nothing here is corrected, and nothing here is maintained. A document in
`archive/` describes the design as it stood on the day it was retired, and the date and
the reason are recorded below and in [`../docs/history.md`](../docs/history.md).

## ⭐ An archived document is still citable

**`archive/video/docs/graphics.md` is where this machine was designed.** The 72-pin
backplane, the slot model, the card decode rule, the arbitration discipline, the clock
tree, the `/WAIT` convention, the dot-clock arithmetic and the 39.72 ns pixel budget
were all first written down there, because the video card was the first card and every
one of those questions had to be answered before it could exist. `docs/machine.md`,
`audio/docs/audio.md`, `io/`, `net/`, `storage/`, `hardware/lib/slot.ts` and
`video3/docs/plan.md` all cite it, and **they are right to.**

⚠ **The card being retired does not make its derivations wrong.** A citation to
`graphics.md` §5.3 for `t_AD`, or §17 for the slot, or §8.2 for the two-rank fetch
latch, is a citation to a piece of reasoning that still holds and that nothing else in
this repository states as well. Rewriting those citations out would lose the provenance
and gain nothing.

What an archived document is **not** is a statement about the present machine. It is not
the video card's register map, it is not what `check:place` measures, and it is not what
`npm run check` runs. For the machine as it is, read [`../docs/machine.md`](../docs/machine.md)
and [`../video3/docs/plan.md`](../video3/docs/plan.md).

## What is here

| | Archived | Why |
|---|---|---|
| [`video/`](video/) | **2026-09-20** | The machine's specified video card until that date: 640×200 × 256 colours, 80×25 text, a display list, byte-granular scroll, a span writer — **33 ICs on a 24 cm board, three fitted `ATF1508AS`**, simulated end to end and executed by a 6809E out of its own boot ROM. ⭐ **[`video3/`](../video3/) replaced it**, which does character mode with per-cell colour, a keyed copy engine and a sprite, and which NitrOS-9 and ANSI art need and `video/` cannot give (`software/nitros9/docs/video-compat.md`). Superseded, not wrong |
| [`video2/`](video2/) | **2026-09-20** | A microcoded ANSI text card — two flash control stores, no CPLDs, no GALs, hardware character generator, fixed RGB332. **Paper only**: a plan and a datapath PDF, never built, never fitted, never placed in `hardware/place/parts.ts`. `video3` took the question it was asked to answer |

[`../docs/video-options.md`](../docs/video-options.md) is the comparison the decision
came out of, and it is a historical record now too — its header says so.

## What did NOT move, and why

⚠ **`video/`'s design sources are still in `hardware/gal/`**, and its board drawing is
still `hardware/cards/video.circuit.tsx`. That is deliberate and it is a compromise:

- `hardware/gal/verilog/gen.ts` emits `vaddr.v`, `vctrl.v`, `vsup.v`, `rfa.v`, `vlen.v`
  and `pxsel.v` from those term lists, and **`machine_tb` and `demo_tb` still
  instantiate the card** — `npm run check:machine` is the machine running
  `software/boot/boot.asm`, and that ROM still drives `video`. Retargeting it to
  `video3` is a separate job; moving the sources now would break the one check that
  executes an instruction.
- `hardware/gal/fold.check.ts` uses the video arbiter as the **fixture** for
  `jedec/cupl.ts`'s constant fold — a build-tool transformation the live cards depend
  on, and the only exhaustive test of it there is. It stays for the tool, not for the
  card.
- `place/parts.ts` keeps the card in `ALTERNATES`: placed, length-checked and totalled
  against its own 33, and tied to `cards/video.circuit.tsx`'s `icBudget`. An alternate
  owns no `$FF` window, which is what `lib/cards.check.ts` now asserts of it.

⛔ **What that costs, stated plainly: the `video` sources are still compiled and are no
longer checked.** They left `gal/designs.ts`, `jedec/cupl.check.ts`'s registry,
`pins.check.ts`'s parts and consumers, `reach.check.ts`'s cards, ten scripts in
`npm run check`'s chain and five testbenches in `gal/verilog/run.sh`'s default `TBS`.
The benches still run when named — `TBS="vsync vaddr vtile vspan vpal" sh run.sh` — and
`check:machine` still exercises the card as a whole. When the boot ROM is retargeted,
the sources and the drawing can follow their documents here.

## The convention

`CLAUDE.md`'s documentation rules are unchanged by this directory. A spec describes the
present design; a `history.md` beside it archives superseded claims. **Archiving is a
third thing**: the whole component moves, its `history.md` moves with it, and
`docs/history.md` records the move. Nothing is rewritten on the way in, which is why
`archive/video/docs/graphics.md` still says "the card is 33 ICs" in the present tense —
it was, on the day it stopped being a card. `hardware/lib/docs.check.ts` exempts
`archive/` for the same reason it exempts `history.md` and the design reviews.
