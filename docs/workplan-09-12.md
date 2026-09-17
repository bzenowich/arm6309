# Work plan — 2026-09-12

**This is a plan, not a specification.** It records what to do next and why, in
priority order, with the check that closes each item. It is dated and
disposable: when an item lands, its substance belongs in the component spec and
its narrative in that component's `history.md` — delete the item here rather
than letting this file become a second, competing record.

It comes out of one session that reverted `ba57e14` (the audio sequencer's
across-the-walk re-timing, which stopped the card playing) and audited
`boot.asm`'s test coverage. Two findings shape the ordering:

- ⛔ **The regression was invisible to every aggregate command.** `audio_tb`
  passed 67 claims throughout, because it backdoor-loads `card.SRAM` instead of
  uploading through `SDATA`. `check:modplay` is the only bench that drives that
  path, and it is in neither `npm run check` nor `npm run build:all`.
- ⛔ **The same shape is sitting in `machine_tb` right now.** `boot.asm`'s two
  largest stages are self-verified: they pass iff the ROM's own comparisons
  pass, and nothing reads the memory independently.

---

## P0 — landed 2026-09-12

Items 1–4 are done: `audio.md` §16 items 46 and 47, and `audio/docs/history.md`. The
four-channel probe found a live host-port defect on its first run (§16 item 47), which
is fixed.

---

## P1 — landed 2026-09-12

Items 5–7 are done: `software/boot/README.md` "What `machine_tb` checks without asking
the ROM". One part of item 7 is not: **no interrupt vector is ever taken**. That needs
`boot.asm` to issue an `SWI` or unmask an interrupt, and it is listed under that README's
"What it does not do yet".

---

## P2 — landed 2026-09-12

Items 8–11 are done; `software/boot/README.md` has each. The sizing walk is in the ROM
and runs against every population. The unbounded `VSTAT` waits are a recorded decision
(no timeout, until there is a console to report one). `mkrom.sh` compares all seven
vectors, and `boot.bin` is tracked. All sixteen map entries are asserted, and TASK 1 is
exercised.

---

## P3 — landed 2026-09-12

- **Item 12.** `docs.check.ts` scans paragraphs, list items and table rows. It tests
  tense per clause, reads `N/M`, and counts `pins` as I/O. It found 72 stale figures that
  the old line scanner passed; each is corrected or now visibly dated, with the replaced
  text in the component `history.md` files. The check covers 94 claims, up from 12.
- **Item 13.** `check:netlist` runs against the video card: what is drawn, and the nets
  with no producer, as a list checked both ways. The rest of the drawing is `graphics.md`
  §19 item 34, still open.
- **Item 14.** `graphics.md` §19 item 46 records that `vsup` and both audio CPLDs also
  fit on pass 2, and that only `vaddr` places on pass 1. The `check:machine` count was
  corrected in P1.

---

## P4 — landed 2026-09-13

Item 15 is done: `audio.md` §16 item 37 sub-item 3 and item 48. The re-timing, rebuilt
on P0's host-strobe repair, plays both probes, and the adder window is measured at
211 ns on every sum write. ⚠ U2 now places on pass 1 with fourteen cascades, including
the state-file address. Nothing times that, and U2's speed grade is unspecified.

---

## The rule this session is worth turning into a habit

⛔ **A claim count in a commit message is not evidence unless the command ran on
the tree being committed.** `487ddd7` wrote "18 claims, 0 failed" into the spec
while its own message said the check was not run; the next commit repeated the
figure for a sequencer it had just re-timed; and the constant-fold commit
confesses to the same class of error in its own body. Quote counts only from a
run of the tree you are committing, and say which command produced them.
