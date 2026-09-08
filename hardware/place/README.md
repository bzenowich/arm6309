# `place/` — the placement study

**Every board drawn 1 : 1 from its own document's parts list.** Nothing in this
repository had ever been placed; `graphics.md` §14 carried an area claim
(*"~150 of 160 cm²"*) that nobody had checked against a package outline.

```sh
npm run check:place     # the arithmetic
npm run render:boards   # dist/boards.html
```

| | |
|---|---|
| [`parts.ts`](parts.ts) | the six chip budgets as footprints — **the second copy, and the risk** |
| [`pack.ts`](pack.ts) | skyline placement with the fingers and rear connectors as obstacles |
| [`svg.ts`](svg.ts) | the drawings, in board millimetres |
| [`page.html`](page.html), [`style.css`](style.css) | the prose and the stylesheet |
| [`render.ts`](render.ts) | writes `../dist/boards.html` |
| [`place.check.ts`](place.check.ts) | what makes it a check rather than a picture |

## What it found

**The video card did not fit a Eurocard.** 30 packages come to 134.4 cm² of
courtyard against 133.4 cm² of placeable area on 100 × 160 mm — over budget
before a single routing channel, at 0.1″ clearances. That is what moved the
card format to 250 × 100 and then to per-card lengths.

**Three of five cards fit 12 cm**, one needs 18 and only video needs 24. Five
cards come to 780 cm² of board against 1,200 if every card were cut to the
longest.

## The assertion that matters

`icCount(spec)` must equal the `icBudget` in `cards/*.circuit.tsx`, which is
transcribed from the card's own document. **Two independent transcriptions of
one table disagreeing is the error this file exists for**: on 2026-09-08 the
storage card was published as 13 ICs against its own §8 table of 14, because
the rows are numbered 1–13 and two of them carry more than one package.
Counting rows is not counting parts, and only enumerating the footprints found
it.

The other three claims: every package places, the placement stays inside
100 mm, and **the declared length is the shortest of the three that works** —
so a card that grows a package fails the check rather than silently spilling
off the board.

## What it is not

A layout. There are no traces, no vias and no decoupling capacitors — about
thirty per card, another 6 cm² the percentages do not carry. Real placement
groups by signal, not by what fits lowest. **The area figure is the finding;
the arrangement illustrates it.**

⚠ **`Part.counted` exists because the documents disagree about oscillators.**
`audio.md` §10 numbers its 28.37516 MHz can among the 29; `net.md` §9 lists its
20 MHz can below the numbered rows; `serial.md` §9 says *"Total: 3. Plus a
1.8432 MHz crystal."* The footprint is placed either way — it occupies board —
and only the count follows the card's own document.
