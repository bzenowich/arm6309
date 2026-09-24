# `software/pcs/` — Pinball Construction Set

Bill Budge's *Pinball Construction Set* (Atari 800, 1983), ported from his own MIT-licensed 6502 to a 6809 under NitrOS-9 Level 2, at 640 × 480 on video3. The world stays in the Atari's own units and only the renderer is doubled, so a Python transliteration of the 6502 is the gate.

| | |
|---|---|
| 6809 source | `../nitros9` (branch `arm6309`), `level2/arm6309/cmds/pcs.asm`, `pcsdat.asm` (generated) and the `pcs*.inc` it includes |
| Generator and models | `bench/mkpcs.py` writes `pcsdat.asm`; `bench/pcsobj.py`, `pcspak.py`, `pcsphys.py`, … are the transliterations of the 6502 the bench checks against |
| Benches | `bench/run-pcs.sh` (the gate, ~8 min — run `python3 software/pcs/bench/pcsobj.py` first), `bench/run-pcssheet.sh` (every shipped table on one contact sheet) |
| Docs | [`docs/pcs.md`](docs/pcs.md) is the spec; [`docs/status.md`](docs/status.md) is where the port stands |
| Video | `make video` / `make video-sheet` - mode 20 played by `bench/scripts/pcsplay.ps2` (`video/run-video.sh`) |
| Reference | [`reference/`](reference/): the original 6502 sources (`pcs-source/`, MIT) and the retail disk images the tables are read from (not tracked) |

⭐ **`run-pcssheet.sh` is a review tool and not a gate**: it paints all 26 tables
that come off the retail disks and puts them on a contact sheet, with the pixel
distance from the model printed under each name — so a table that looks plausible
and a table that IS the 6502's are told apart at a glance. ⛔ It is **batched, six
to a ROM**, because 32 KB of object area in one module makes `pcs` fail to fork
with `E$MemFul` — a machine that boots perfectly and answers `Error #207`.
⚠ The tables are not in this repository (`pcs.md` §5c); it prints and exits if the
disk images are not in `reference/`.

⭐⭐ **`run-pcs.sh` is the one that PROVES A SIMULATION rather than showing it.**
`pcs` is Bill Budge's *Pinball Construction Set* (Atari 800, 1983), ported from his
own MIT-licensed 6502 in `software/pcs/reference/pcs-source/`; `software/pcs/docs/pcs.md` is the spec. The
decision the whole port rests on is that **the world stayed in the Atari's own
units and only the renderer is doubled** — so every number in the database and the
simulator is exact integer arithmetic, and a Python transliteration of the 6502 can
be the gate. The bench requires the 6809 to produce the identical ball, the
identical part states and the identical score on every one of 600 frames.

⛔ **The model is checked before the machine is built**, and ⛔ **it is never
corrected to agree with the 6809** — when they differ the 6502 decides. Correcting
the model against the *6502* is the one direction allowed, and it has happened
twice.

⭐⭐ **And since 2026-09-23 a table is a FILE ON THE CARD.** `pcs 0 30 demo2.pbt`
loads `/SD0/DATA/demo2.pbt` through `pcsfile.inc` — the container is `mkpcs.py`'s,
the payload is exactly the bytes at `logic,u`, and the `f0` leg compares the span
database it came to **record for record** rather than just the picture, because a
loader that dropped a byte would still paint something. ⛔ With an `fX` control
naming a table that is not there, which must print `PCS-NOFILE` and refuse: a
named table that will not load is an error, not a quiet fall back to the built-in
one. ⚠ The `.pbt` files are generated from the retail disks and are **not in the
repository**, so a clone without them has no tables on the card and `fX`'s
sibling legs say so rather than passing vacuously.

⛔ **The gate requires five LIBRARY PARTS to have been struck.** A ball that only
ever met the backdrop proves nothing about the object system, and that is exactly
the run an earlier table gave: 600 frames and 21 bounces agreeing over a collision
walk that was reading half the world, because five plain polygons are only ever met
side-on and `CHECKHORIZ` has no two modes to get wrong.
