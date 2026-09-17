# video3 — history

Superseded claims from [`plan.md`](plan.md), [`signals.md`](signals.md) and
[`partition.md`](partition.md), with the date each moved and what replaced it.
`CLAUDE.md`'s rule: **specs describe only the present design**, and a superseded
utilisation figure is a number `check:docs` cannot distinguish from a live one.

## `plan.md` §7 — the sprite was 8×8, and `v3dot`'s fit with it (2026-09-17)

Until 2026-09-17 the sprite was **8×8**, and §7's first three rows read:

| | |
|---|---|
| Shape | **8×8, two bits a pixel**: 0 transparent, 1 and 2 the two cursor colours, 3 reserved. **16 bytes**, written through `SPRIDX`/`SPRDAT` |
| Per displayed sprite row | **one** register-file read of two bytes into two eight-bit shift registers |
| Per dot of the sprite's eight columns | two bits shift out into the **`ATTR` latch** |

`SPRIDX` was four bits, both window counters three, and `partition.md` §8's escape was
**two** `'165` for **−16 cells and −2 pins**. With that sprite `v3dot` fitted at
**117 / 128 cells, 52 / 64 I/O and 4 cascades**, and `partition.md` §5 risk 3 quoted the
same fit as 117 / 128 with 1 cascade.

Eight rows cannot hold an arrow with a tail: the cursor was an arrowhead, and its
bottom row put a fill pixel outside the outline. `software/demo`'s pointer is 16×16, so
the sprite became 16×16 — four bytes a row, 64 in the register file, four `'165`, four
more macrocells — and refitted at **122 / 128, 0 cascades**. `demo-report.md` §10.6 is
the pass that did it.

## `plan.md` §10 — `+$1F` was reserved (2026-09-17)

Until 2026-09-17 the register map's last row read:

| Off | Name | |
|---|---|---|
| `+$1F` | — | reserved |

It is now the driver's frame count (`VR.FCnt`). Nothing in the hardware changed: the
byte was always a cell of the register file, and no logic reads it. What changed is
that the VBL service writes the low byte of `VG.Frames` there every frame, because
`overworld` needed to know whether a frame had ended without paying for a system call
— the third pass's measurement is `demo-report.md` §10.

## `partition.md` §0 — the register decode, before the broadcast (2026-09-16)

Until 2026-09-16 `v3host` emitted **one load strobe per register** and the other three
parts took those strobes as inputs. `partition.md` §3 had proposed broadcasting
`RA4..RA0` + `REGWR` instead from the start; the fit is what forced it. The figures that
wiring produced:

| | cells | I/O | cascades |
|---|---|---|---|
| `v3host` | 51 / 128 | ⛔ **64 / 64** | 0 |
| `v3scan` | 114 / 128 | 63 / 64 | 16 |
| `v3scan_mq` | 82 / 128 | 46 / 64 | 16 |
| `v3ptr` | 110 / 128 | 45 / 64 | 3 |
| `v3dot` | 115 / 128 | 53 / 64 | 1 |
| `v3ptr_rows` | 128 / 128 | 46 / 64 | 21 |
| `v3ptr_both` | 128 / 128 | 47 / 64 | 19 |

**Two things ended it.** `v3host` at 64 / 64 pins had no next step in it — a per-register
load strobe is a pin and video3 has 30 of them. And a strobe per *register* cannot load a
register **wider than the bus**, which v3ptr has six of, so every one of them was loading
all its bits from a single strobe and a store to `+$08` put `D0` into both `WC0` and `WC8`.

`v3ptr_rows` and `v3ptr_both` fitted at 128 / 128 under that wiring and **refuse outright**
(`INTERNAL ERROR`) under the per-bit loads the fix requires, so their reports were deleted
rather than kept: plan §6.2's rejection of the copy direction bits is no longer a judgement
about cascade counts, it is the fitter declining.

⚠ The `v3host` variant is kept fitted as `v3host_st`, because it is the evidence.
