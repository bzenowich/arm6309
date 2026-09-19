# video3 — history

Superseded claims from [`plan.md`](plan.md), [`signals.md`](signals.md),
[`partition.md`](partition.md), [`keyed-copy.md`](keyed-copy.md) and
[`demo-report.md`](demo-report.md), with the date each moved and what replaced it.
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


## `plan.md` §14 item 14 — "neither sequencer is built", and the record of building them (2026-09-19)

Item 14 opened on 2026-09-18, when `check:reach` found that the four fitted parts were a
datapath and an arbiter with no sequencer, and was extended through 2026-09-19 as each
piece went in. By the end of that day every block it listed was built, and `v3card_tb`
(plan §15.4) then changed three of the four fits again, so the running narrative and
every figure in it described a design that no longer existed. It was replaced by a
**closed** item 14 that states the present design and the current fits. It read:

14. ⛔ **NEITHER SEQUENCER IS BUILT, AND THE FITS DO NOT CONTAIN THEM** — found
    2026-09-18 by putting video3 into `npm run check:reach`. The four parts are a
    **datapath and an arbiter**: pointers, counters, the address mux, the register
    decode, and `GMAP`/`GRD`/`GCPY`/`GSPN`. What no part produces is **19 control
    lines**: `RMAP`/`RRD`/`RCPY`/`RSPN` (the four *requests* into v3dot's own
    arbiter), `RETIRE`/`SPANEND`/`WINC`/`WROWADV`/`RSTART` (§5's span writer), and
    `CGO`/`CDONE`/`CSTEP`/`CROWADV`/`CWLOAD`/`CRDSEL` (§6's copy engine), plus
    v3host's `WRCYC`/`RDCK`/`IRQEN`. `v3ptr` counts on `CSTEP`, holds `CBUSY` on
    `CGO & !CDONE`, and nothing steps or starts it.
    ⚠ **So `v3ptr` 124/128 and `v3dot` 122/128 are fits of the datapath.**
    `partition.md` §2.3 budgets **~10 macrocells** for the two sequencers inside
    `v3ptr` and they are not in that fit; 18 spare cells and 3 existing cascades is
    what they have to come out of. **This is the number that decides whether there
    is room for anything else** — a keyed copyrect, a descriptor walker, more
    sprite. Nothing should be priced against `v3ptr` until it is refitted with
    them.
    ⭐ **AND THE EQUATIONS WERE WRITTEN AND FITTED, 2026-09-18** — `V3_SEQ` on
    `v3ptr.cpld.ts`, the way `V3_COPYDIR` bisected the direction bits. The span
    writer's is a port of `video/`'s `seqctl.jedec.ts`, which `vspan_tb` verifies,
    minus the display list's `!LRUN` and with `TC` folded in because SPANLEN is on
    this part; the copy engine's is new, and is only a phase bit, because two
    accesses a byte with one spare access a slot means **two slots a byte** and the
    phase is all the state the sequence needs.

    | `v3ptr` | cells | I/O | cascades |
    |---|---|---|---|
    | `none` — the build | 124/128 | 54/64 | 3 |
    | `span` | **115/128** | 48/64 | **3** — no timing change |
    | `copy` | **117/128** | 41/64 | ⚠ **8** — +5 on its own |
    | `both` | ⛔ **DOES NOT FIT**, refused under two different file names | | |

    ⭐ **AND THE PARTITION MOVE WORKS — BOTH SEQUENCERS ARE BUILT, 2026-09-19.**
    `V3_SEQ=split` keeps `CEOR` and `CHLAST` on `v3ptr`, beside the ten and nine
    counter bits they decode, and puts the copy's **phase machine** on `v3host`.
    Seven signals cross instead of nineteen: `CBUSY` (which `v3host` already took
    for `VSTAT`), the two decoded bits out, and `CRDSEL`/`CSTEP`/`CROWADV`/
    `CWLOAD`/`CDONE` back. It is the default build, and all four parts fit:

    | | cells | I/O | cascades |
    |---|---|---|---|
    | `v3dot` | 122/128 | 51/64 | 0 | ⭐ **unchanged — not one edit** |
    | `v3ptr` | **124/128** | 54/64 | **3** | the span sequencer, the two decodes, WMODE |
    | `v3host` | **49/128** | 63/64 | **0** | the copy engine's phase machine |
    | `v3scan` | 100/128 | 64/64 | 2 | ⚠ **full** — it now decodes its own address source |

    ⚠ **`v3ptr`'s cascades are still 3** — the count it had before any of this —
    so the span writer goes in with no timing change at all.

    ⛔ **THE TICK COST A LITERAL AND NOT A MACROCELL, after two refusals.** Both
    sequencers need the spare window's *last* dot, because the arbiter is pure
    combinational grant logic with no phase term and a step on every dot of the
    window would move four bytes a slot (`design-review2.md` V-4). A `SPARETICK`
    cell on `v3dot` was refused, and so was exporting `DP0` — that part is
    122/128 with Nodes+FB at 124%, and neither a cell nor forcing a buried
    counter bit onto a pin goes in. But `SPARE` is `!DP1`, the grants already
    contain it, and **`comb("MUXSEL0", ["DP0"])` is already an external**. So
    `GSPN & MUXSEL0` *is* the tick, for one extra literal on a term the receiver
    has anyway — and `v3dot.pld` did not change by a byte.

    ⛔ **AND WMODE HAD NO PRODUCER ANYWHERE.** §10 puts it at `CTRL` b5..4 and
    `v3dot` holds `CTRL` as `CT0..CT7`, but exports `MODE` and `VMODE` and not
    those two — and cannot grow a pin to do it. `v3ptr` decodes `LDCTRL` off the
    broadcast and holds `WM0`/`WM1` itself, which is `partition.md` §3's own
    idiom and the same duplication `v3dot` already makes of `HSCROLL[1:0]`.
    Three cells, and the span writer has its mode.

    ⚠ **122 is what the two would cost on one part if the cells added, and 122
    is under 128** — so the refusal is not the cell count. It is LAB grouping:
    Nodes+FB/MCells is already 125% with one sequencer, and `CEOR` and `CHLAST`
    need ten and nine counter bits inside one block. **`partition.md` §2.3's
    "~10 macrocells for the span and copy sequencers" is refuted by the fitter**,
    and §2.5's "a fifth part for the copy engine — it does not place" closes the
    other way out. ⭐ The move the numbers point at is **`v3host`, which is
    49/128 and has 22 spare pins**: keep `CEOR`/`CHLAST` on `v3ptr` beside the
    counters they decode and put the phase machine there, which is ~7 signals
    across rather than the 19 counter bits.

    ⭐ **AND §7.2's END-OF-ROW COLUMN RELOAD IS BUILT, 2026-09-19** — the last
    piece, and the one neither part could do alone. Without it neither engine
    chains: a glyph steps eight pixels right on every row (`video/` shipped
    exactly that, `design-review2.md` V-6) and a copy's two columns climb
    across rows instead of restarting.

    ⛔ **It could not be finished because nothing on this card produced `RFA`
    at all.** The register file holds the readback bytes, `WFG`/`WBG`,
    `SPANLEN`, the sprite shape *and* the two column shadows, and its address
    had no generator. `video/`'s `rfa` is the same block, so this is a port,
    with three differences: the CPU's offset is already on `v3host`, which IS
    the decode; the walk is **four** states and not two, because the copy has
    to restore `CPTR`'s column as well as `WPTR`'s; and **`RFA0` is on
    `v3ptr`** — §5 makes the file's address bit 0 the **mask bit**, and the
    serialiser is there.

    ⭐ **One-hot, so the states are the strobes**: a four-dot walk that also
    needs four load strobes is five cells that way and nine as a counter plus
    decodes. `RP1` → +$08 → `WC7..WC0`, `RP2` → +$09 → `WC9..WC8`, `RP3` →
    +$12 and `RP4` → +$13 for `CPTR`, the last two only when `CRLD` says the
    trigger was a copy's.

    ⚠ **Two strobes a pointer and not one, and the ROW is why**: +$09 carries
    `WC9..WC8` in D1..D0 **and `WR5..WR0` in D7..D2**, so a reload that reused
    the CPU's own `LDWP1` would undo the row advance the same span just made.
    ⚠ **And the strobes must stay separate**: `LDA # RLDA` is the obvious
    saving and `access.jedec.ts` records what it costs — CUPL substitutes the
    intermediate, every *hold* term becomes two, and the fitter aborts with
    INTERNAL ERROR.

    | | cells | I/O | cascades |
    |---|---|---|---|
    | `v3ptr` | **124/128** | 54/64 | **3** — still flat |
    | `v3host` | **49/128** | ⚠ **63/64** | 1 |

    ⭐ **AND THE LAST SIX UNBUILT BLOCKS FOLLOWED, 2026-09-19** — the census is
    now **empty of `unbuilt`**. Not one of them needed a new block, and four
    came straight out of `video/`:

    | | |
    |---|---|
    | `RMAP` | ⭐ is `v3dot`'s own `CELLTICK`. The map word is fetched once a cell and `MAPLD` was already `SPARE & CELLTICK`, so a separate request was the same decode under a second name. ⚠ **Mode-qualified, which `MAPLD` is not**: bitmap mode has no map, and granting it the slot's only spare access would spend it on a fetch nothing reads |
    | `RRD` | is `v3host`'s `RDREQ`, `!RDVALID` — §11's request under its own name, and `video/` spells it the same way |
    | `WRCYC` | `!RW & E`. ⚠ A 6809E write is only valid in E's second half |
    | `RDCK` | `GRD & !RDVALID`, **active low** so the `'574`'s *rising* edge is the END of the granted access — `vsup.parts.ts`'s, minus its `!LRUN` |
    | `RSTART` | `RPQ & !E`, §11's **post-increment**. ⚠ Not "the copy has started": that was a guess from the name, and `vsup.parts.ts` says it is the dot after a VRAM read's E falls |
    | `IRQEN` | `CTRL` b6. ⛔ Tried on `v3ptr`, which has the bus and the `CTRL` decode already, and the fitter refused it at 125/128; it is on `v3host`, which pays its **first data-bus pin** for it |

    ⚠ **`v3dot`'s cascades went 0 → 5** for `MAPREQ` and its mode qualifier.
    `CLAUDE.md`: a change in cascades is a timing change even when the cell
    count is flat. Nothing on this card has been timed yet, so it is recorded
    rather than assessed.

    ⛔ **`v3host` IS NOW TWO PINS FROM FULL, and that is the card's real
    ceiling showing.** `partition.md` §7.1 says the binding constraint is pins,
    and this is what it looks like: `keyed-copy.md` §7.2's keyed compare wanted
    **eight** pins for the source byte on whichever part gates the write
    strobe, and there is no part left with eight. The `74HC688` version — one
    pin — is now the only one that fits anywhere on this card.

    ⚠ **And three counters were built the wrong way round**, which only mattered
    because nothing clocked them: §5 and §6 specify SPANLEN, CWIDTH and CHEIGHT as
    **down**-counters and `counter.ts` has only an up-counter, so all three loaded
    the true value and counted up, past any terminal count. Fixed with
    `vlen.jedec.ts`'s idiom — hold the complement, count up, and the terminal
    decode is ONE product term. ⛔ The decode is `..11110` and not `..11111`,
    because CWIDTH is the plain byte count N (the emulator, the model, both
    drivers and the bench all agree, none of them biases it) and the counter is
    sampled before the edge that steps it. Free: the fit is 124/128 and 3
    cascades either way.

    ⚠ Two naming defects came out of the same run and are *not* the same thing:
    `v3scan` reads `SRC0`/`SRC1` where `v3dot` exports `MUXSEL0`/`MUXSEL1`, and
    **`v3ptr` and `v3scan` each declare a plain `FBOE` while `v3dot` exports two
    signals, `FBOESCAN` and `FBOEPTR`** — one name on both parts keeps them both
    on or both off the seventeen address nets `v3scan`'s own comment says `FBOE`
    exists to arbitrate.

The two naming defects at its end were fixed by `b591851` (2026-09-19): `v3ptr` reads
`FBOEPTR` and `v3scan` reads `FBOESCAN`, and `SRC0`/`SRC1` turned out not to be aliases of
`MUXSEL0`/`MUXSEL1` at all — they are `v3scan`'s address source, now `GMAP` and a mode
decode on `v3scan`. That commit's figures were `v3dot` 122/128 51/64 5 cascades, `v3scan`
100/128 64/64 2, `v3ptr` 124/128 54/64 3, `v3host` 49/128 63/64 1.

## The card bench's refit — every video3 utilisation figure (2026-09-19)

`v3card_tb`'s fourteen fixes (plan §15.4) moved three of the four parts:

| | cells | I/O | cascades | → | cells | I/O | cascades |
|---|---|---|---|---|---|---|---|
| `v3dot` | 122/128 | 51/64 | 5 | → | 120/128 | 50/64 | 5 |
| `v3ptr` | 124/128 | 54/64 | 3 | → | 125/128 | 55/64 | 3 |
| `v3host` | 49/128 | 63/64 | 1 | → | 55/128 | 63/64 | 0 |
| `v3scan` | 100/128 | 64/64 | 2 | | unchanged | | |

`v3dot` got *smaller* because `ACTIVE` became a register (plan §15.4 defect 12) and `OMR`
moved to `v3host`; `v3ptr`'s Nodes+FB/MCells went from 129 % to 134 %. The spec text each
figure was quoted in, as it read:

- `plan.md` §6.2's variant table, whose build row read
  `| ⭐ **`v3ptr` — neither, and this is the build** | **124 / 128** | **3** |`.
  ⚠ That row had been updated to the build's current size as the build grew, while the
  paragraph under it — *"18 macrocells and 16 cascades"* — is measured against the
  2026-09-16 fit, **110/128** (the `partition.md` §0 entry above). The table is now dated
  and carries 110.
- `plan.md` §7: *"⭐ **`v3dot` refitted at 122/128 cells, 51/64 I/O and 0 cascades** —
  cascades *fell* from four, so the timing argument got no worse."* True of the
  2026-09-17 sprite refit; the cascades went to 5 on 2026-09-19 for `MAPREQ` (plan §14
  item 14).
- `plan.md` §14 item 4: *"`v3dot` is **122/128 cells and 51/64 I/O**; `v3ptr` is
  **124/128 and 54/64**; `v3host` is **49/128 and 63/64**."*
- `partition.md`'s header table, *What each part costs now*:

  | | cells | I/O | cascades | what the swap did |
  |---|---|---|---|---|
  | `v3host` | **49 / 128** | ⭐ **63 / 64** | 0 | **22 pins back**, off a part that had none |
  | `v3ptr` | **124 / 128** | **54 / 64** | 3 | free — and it gained the fix below |
  | `v3dot` | **122 / 128** | **51 / 64** | 0 | a cell for a pin, the raster fix, then the 16×16 sprite |

  and under it: *"the only figure here worth designing against is `v3host`'s 22 pins,
  which is arithmetic."*
- `partition.md` §0's table: `v3dot` **122 / 128, FITTED** / **51 / 64, FITTED**; `v3ptr`
  **124 / 128, FITTED** / **54 / 64, FITTED**; `v3host` **49 / 128, FITTED** / **63 / 64,
  FITTED**.
- `partition.md` §0's note under that table: *"⚠ **`v3host` is pin-bound, not
  cell-bound** — a fifth full of macrocells and two thirds full of pins"* — true of
  `v3host` on 2026-09-16 at 42 pins.
- `partition.md` §5 risk 3: *"with them in two `'165` it is **122/128 cells, 51/64 I/O, 0
  cascades** (four of them since the sprite became 16×16 — plan §7)."*
- `keyed-copy.md` §1: *"`v3ptr` has **18 macrocells and 20 pins spare**
  (`partition.md` §2.3): about 8 pins to bring `vread` into the part, or one pin and a
  `'688` comparator, plus a `CCTRL` bit and a term."* — and §7.2: *"`v3ptr` has ~20 pins
  spare; spending 8 of them on a byte that is already on the board, to save one discrete
  package, is the trade this project has already refused once."*
- `keyed-copy.md` §5's opening and first checklist item:

  > ⛔ **AND ONE THING THAT HAS TO BE TRUE FIRST, found 2026-09-18.** video3 went
  > into `npm run check:reach`, and its four parts turned out to be a **datapath and
  > an arbiter with neither sequencer built** — 19 control lines nothing produces,
  > including the four *requests* into v3dot's own arbiter and the whole of §6's
  > copy micro-sequencer (`plan.md` §14 item 14). So `v3ptr`'s **124/128 is a fit of
  > the datapath**, and `partition.md` §2.3's ~10 macrocells for the sequencers are
  > not in it.
  >
  > ⭐ **That is good news for the key and bad news for every estimate in §7.** Good,
  > because a key is one more term on a write strobe still being designed rather than a
  > change to a part that has already fitted — §7.3's last paragraph said this and is now
  > measured rather than inferred. Bad, because **`v3ptr`'s 18 spare cells are already
  > spoken for**, and nothing in §7 should be priced against them until the part is
  > refitted **with** both sequencers in it. That refit is the gate, not the compare.
  >
  > - [x] ⭐ **The two sequencers are written and fitted** (2026-09-18), and the number
  >   is in: `plan.md` §14 item 14 has the table. **`v3ptr_span` is 115/128 with
  >   cascades flat at 3; `v3ptr_copy` is 117/128 but costs +5 cascades; ⛔ the two
  >   together DO NOT FIT.** 122 is what they would cost if cells added, and 122 is under
  >   128 — the refusal is LAB grouping, not cell count. ⭐ **AND THE PARTITION MOVE
  >   WORKS** (2026-09-19): `CEOR`/`CHLAST` stay on `v3ptr` beside the counters they
  >   decode and the phase machine goes to `v3host`. Both sequencers are built, all four
  >   parts fit, and `v3dot` did not change by a byte. **`v3ptr` 124/128 with cascades
  >   still at 3; `v3host` 49/128 with 0.** ⛔ **Which re-prices the key, and not in its
  >   favour.** §7's "18 spare cells and 20 spare pins on `v3ptr`" described a part that
  >   did not yet contain §6's engine; it now has **9 cells and 17 pins spare**, and
  >   Nodes+FB at **131%**. The compare wants the source byte, which means eight pins
  >   into whichever part gates the write strobe. ⭐ **That part is now `v3host` —
  >   49/128 cells, 11 spare pins, 0 cascades** — and it is the one place on this card
  >   with room. ⛔ **And then §7.2's column reload was built (2026-09-19) and `v3host`
  >   went to 63/64.** There is now **no part on this card with eight spare pins**:
  >   `v3dot` has 13 pins and six cells, `v3scan` has one pin, `v3ptr` has ten, and
  >   `v3host` — after the last six blocks went in on 2026-09-19 — has **one**. ⭐ So
  >   §7.2's **`74HC688` — one pin** — is no longer the cheaper-by-a-package option. It
  >   is the only version of this feature that fits anywhere. ⭐ **The good half of the
  >   news stands**: the key is still a term on a write strobe that is still being
  >   designed, which is the cheapest form it can take. It is the PART that is not
  >   settled, not the compare.
- `keyed-copy.md` §7's table and the two paragraphs under it:

  | part | logic cells | I/O pins | cascades | foldback |
  |---|---|---|---|---|
  | `v3dot` | **122/128 (95%)** — 6 spare | 51/64 | 0 | 37/128 |
  | `v3host` | ⭐ **49/128 (21%)** — 101 spare | 63/64 — 22 spare | 0 | 0 |
  | `v3ptr` | **124/128 (85%)** — 18 spare | 54/64 — 20 spare | **3** | 45/128 |
  | `v3scan` | 100/128 (78%) | ⛔ **64/64 (100%)** — **no** pin spare | 2 | 17/128 |

  > ⭐ **`partition.md`'s estimate for `v3ptr` was right to the cell**: 18 spare and 20
  > pins, which is what §10.5 quoted. ⚠ **And `v3ptr` already carries 3 cascades** —
  > that is the baseline a refit has to be compared against, not zero.
  >
  > ⭐ **`v3host` is where the room is**, by a wide margin: 101 cells and 22 pins. ⛔
  > **`v3dot` has six cells** and `v3scan` has **one pin**; neither can take anything.

  ⚠ Its rows had been edited piecemeal as the parts grew, so by 2026-09-19 they mixed the
  2026-09-16 spare counts (18, 20, 22, 101) with later cell counts. The 18-and-20 was
  `v3ptr` at 110/128 and 44/64.
- `demo-report.md` §6 and §10.6 quoted `v3dot` at 122/128; both are dated passes, and now
  say so.

### `partition.md` §2 and §5 — v3scan's "63 of 64"

Two sentences quoted `v3scan` with the map word in silicon at **63 of 64 I/O**, "one pin
of headroom". Its fit has said **64 / 64** since `b591851` moved the map-word part select
onto it (`SRC0`/`SRC1` decoded from `GMAP` and the mode, `MODE0`/`MODE1`/`GMAP` in, `SRC0`,
`SRC1` and `FBOE` out), and the check that polices these figures did not recognise "63 of
64" as a utilisation claim. Replaced by "64 of 64".

## `partition.md` §6.1 — two signals with no cell behind them (2026-09-19)

Both were built on 2026-09-19 (plan §14 item 14): `RFA` from `v3host`'s reload walk and
`v3ptr`'s `RFA0`, and `WPTR`'s end-of-row reload as that walk's `RP1`/`RP2`. The section
read:

⚠ **Four green fits do not mean the card is described.** `CLAUDE.md`'s standing warning
is that *a design output can be absent and prose does not notice*, and
`design-review2.md` found eleven such blocks on `video/`. Writing `v3host` against the
other three term lists surfaced **two on video3**, both of the same shape — this document
assigns the job, and no `Cell` performs it:

| | this document says | the term list has |
|---|---|---|
| `RFA`, `RFWE`, `RFOE` — the register file's address and controls | §2.3: *"the mask serialiser and the register-file address must share a part … so `RFA`, `RFWE` and `RFOE` are here"*, on `v3ptr` | ⛔ **nothing.** One mention, in a comment. `v3ptr` produces `MS0..MS7` and never turns the serial bit into an address |
| `WPTR`'s end-of-row reload | §7.2: the column shadow reloads `WPTR`'s column at every row advance, which is what makes a span a *rectangle* and not a line | ⚠ `LDWP0`/`LDWP1` take **only the CPU write**; `WROWADV` does not reload them. Blocked on the row above — the reload *is* a register-file read |
| ⭐ **the multi-byte loads** — `WPTR`, `CPTR`, `CWIDTH`, `CHEIGHT` | plan §10: 19 bits across three bytes, and `CCTRL` carries `CWIDTH[9:8]` and `CHEIGHT[8]` | ⭐ **FIXED 2026-09-16.** Every bit took one strobe, so `+$08`'s `D0` drove `WC0` *and* `WC8`. Now per-bit, off the broadcast, at no cost |

⭐ **Neither of the two open ones is a fit risk** — `v3ptr` sits at 124 / 128 cells and
54 / 64 I/O, and both additions are small. **Both are correctness gaps**, and the second
bites silently: a span writer whose column never reloads paints the first row and then
walks off down the framebuffer, which is a picture, just not the right one. ⚠ They are
also **one gap, not two** — the reload is a register-file read, so it is blocked on `RFA`.

⛔ **This is exactly what plan §15 step 5's `reach` check is for**, and it is the reason
that step is not optional paperwork: it asks *which signals does the design produce that
nothing reads*, and its mirror — a signal this document names that nothing produces — is
what caught these two by hand. Doing it by hand does not scale to four parts.
