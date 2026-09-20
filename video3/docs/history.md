# video3 — history

Superseded claims from [`plan.md`](plan.md), [`signals.md`](signals.md),
[`partition.md`](partition.md), [`keyed-copy.md`](keyed-copy.md),
[`demo-report.md`](demo-report.md) and the two READMEs (`video3/README.md`,
`hardware/gal/video3/README.md`), with the date each moved and what replaced it.
`CLAUDE.md`'s rule: **specs describe only the present design**, and a superseded
utilisation figure is a number `check:docs` cannot distinguish from a live one.

## `video3/bench/README.md` — "the ROM disk is full" (2026-09-20)

The bench README carried the constraint every scene bench was built around, and the
recipe carried the mechanism. Superseded when the demo programs moved off the boot
ROM's ROM disk and onto an SD card (`software/nitros9/mksddisk.sh`,
`video3/bench/run-v3sd.sh`); the ROM disk is now a rescue system with ~65 K free.

> ⚠ **The ROM disk is full** — 488 K, 6,656 bytes free — and `pinball` is 36 K.
> The recipe therefore takes `CMDS_EXTRA` and `CMDS_DROP`
> (`recipes/arm6309/arm6309.mak`), and `run-v3pin.sh` asks for its command and
> gives back `monster`, `mvania`, `ded`, `dcheck` and `debug`. It deletes
> `romdisk.dsk` on the way in **and on the way out**, because the recipe's disk
> rule depends on the module files and not on the list of them.

and, in the recipe itself:

> ⭐ **THE ROM DISK IS FULL, so a scene has to ASK for its command and GIVE BACK
> the room.** 61 ROM pages is 488 K and there were 6,656 bytes free before
> `pinball` was written; its table is 35 K. `video3/bench/run-v3pin.sh` passes
> `CMDS_EXTRA=pinball CMDS_DROP="monster mvania ded dcheck debug"` and nothing
> else in the tree changes.

**What replaced it.** `$(DEMOS)` in `recipes/arm6309/arm6309.mak` builds the demo
programs but does not put them in the disk image; `$(CMDS)` is the kernel, the shell,
`CoArm`, `libvid`, the self-tests and a rescue command set (`format` was added for it).
Measured on the `-DV3=1` build: **22 free sectors (5,632 bytes) before, 260 (66,560)
after** — 238 sectors net, and 256 before `format`'s 18 are counted back. `CMDS_EXTRA`
survives and still means "put this one in the ROM disk", for the older scene benches
that boot with an empty socket; `CMDS_DROP` survives and is used by nothing.

⭐ **And the stale-disk hazard the old text described is closed rather than worked
around.** The `$(ROMDSK)` rule depended on the module *files* and not on the list of
them, so a shorter `$(CMDS)` alone left yesterday's disk in place — which is why the
bench had to delete `romdisk.dsk` at both ends. `.cmdlist` now holds the list as a file,
is rewritten only when it differs, and is a prerequisite of the disk.

## `keyed-copy.md` §3.1 — "the batch's cost, which has not been measured either" (2026-09-19)

§3.1's table ended on an unmeasured number and the section said so:

> | batched, one commit | the batch's cost, **which has not been measured either** |
>
> ⚠ **So §3.1 is not proven.** It is plausible and it is the right shape, and it
> now rests on a second unmeasured number rather than the one §3.2 retired. The
> bench that would settle it is `v3cpyb` again, issuing its copies through
> `SS.Batch` instead.

**What settled it.** Not `v3cpyb` but `mvania`, whose scroll batch is the
smallest `SS.Batch` there is: **1.90 ms a frame**, measured off `marks.txt`
with `-DBTMARK=1`. The split is in §3.1 as it now stands, and it moved the
question — 1.05 ms of the 1.90 is IOMan and SCF and belongs to no card.

## `plan.md` §2.2 and §10 — the attribute's lane, and the pointer's step (2026-09-19)

The four-byte cell landed earlier the same day with **the code in lane 0 and the
attribute in lane 1**, lanes 2 and 3 unused, and `WPTR` stepping by one:

> ```
>   map cell    lane 0 glyph code     lane 1 attribute     lanes 2, 3 unused
> ```
> `A1..A0   the lane   0 = code, 1 = attribute, 2 and 3 unused`
>
> `| +$0B | WADV | 00 continue, 01 next row same column, 10 by the stride |`

**What it cost, and what replaced it.** With both bytes in one part's lanes, a
character was FOUR stores: the code, the attribute, and two of filler, because
re-pointing `WPTR` between cells costs three register writes to save two. The
driver port measured 99.8 → 108.3 µs a character for it.

`v3scan`'s sixteen data pins may be wired to any two of the four lanes, and the two
parts' LOW bytes — lanes 0 and 2 — are the pair a pointer stepping by TWO reaches with
one write each. So the attribute moved to lane 2 and `WADV` gained b2, "step by two":
one more product term on each of `WPTR`'s ten column bits (`v3ptr` 122 → 124 of 128),
and a character is two stores again. ⚠ The step is the write pointer's, so a span's
retires and a `VDATA` read's post-increment move by two while the bit is set.

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

## `v3card_tb`'s second round — the four-byte cell, the sprite in VRAM and the byte lanes (2026-09-19)

`v3card_tb` went on from bitmap mode to character mode, tile mode, the sprite, the fine
scroll and a copy under character mode, and `video3_card.v` stopped reaching into its
parts for the seven signals no package produced. That closed plan §14 items 16, 17, 18
and 19 and found the defects plan §15.4 lists as 15–31. The card's programming model
changed in three places — the map's cell stride, where the sprite's shape lives, and what
drives the LUT's high byte — and its parts list changed with it: the `ATTR` `'574` went,
and four `74AHCT245` lane transceivers and the `v3lane` `GAL22V10` came in. Every
utilisation figure moved:

| | was: cells | I/O | cascades | → | cells | I/O | cascades |
|---|---|---|---|---|---|---|---|
| `v3dot` | 120/128 | 50/64 | 5 | → | 121/128 | 63/64 | 5 |
| `v3scan` | 100/128 | 64/64 | 2 | → | 112/128 | 63/64 | 3 |
| `v3ptr` | 125/128 | 55/64 | 3 | → | 122/128 | 57/64 | 3 |
| `v3host` | 55/128 | 63/64 | 0 | → | 58/128 | 64/64 | 0 |

`v3card_tb` went from 34 claims to 57. The spec text each change replaced follows, by
section.

### `plan.md` header, and `video3/README.md`'s opening

The header read:

> **DRAFT, 2026-09-16.** ⚠ **Nothing in this document is fitted, placed, simulated or
> costed.** It is a specification to be attacked, not a build. Every number is either
> inherited from [`archive/video/docs/graphics.md`](../../archive/video/docs/graphics.md) with its
> section cited, or derived here and marked. §14 lists what would refute each load-
> bearing claim, and §15 is the verification this card would need before a board.

and `video3/README.md`:

> **DRAFT.** [`docs/plan.md`](docs/plan.md) is the specification. Nothing here is
> fitted, placed, simulated or costed; §14 of the plan lists what would refute each
> load-bearing claim and §15 is the order the work would have to be done in.
>
> ⛔ **video3 has no partition yet, and no utilisation figure from `video/`'s fit applies
> to it.** Mechanism and timing arithmetic transfer; cell counts, fan-in and "which part
> has room" do not — plan §14 item 4.

Both had been false since 2026-09-16 (the first fits) and 2026-09-19 (the first card
bench). `video3/README.md`'s requirement row read *"**One 8×8 sprite** | the mouse
pointer, bitmap mode only"*, and plan §0's the same with **bitmap mode only** in bold —
both stale since the sprite became 16×16 on 2026-09-17.

### `plan.md` §2.2, §2.4 and §2.5 — two bytes a cell

⛔ **Every odd cell's map word was unreachable.** `v3scan` has sixteen data pins, lanes 0
and 1 of framebuffer part 0, and on a two-byte stride every odd cell's word was in part 1
(`video3_card.v`'s `GAP_4`). The cell became a four-byte fetch group. §2.2 opened:

> **Two bytes a cell**, and the attribute is a palette selector rather than a colour:
>
> ```
>   map word    [15:8] attribute      [7:0] glyph code
>   LUT address [15:8] attribute      [7:0] the glyph's pixel byte
> ```

§2.4 ended *"The only difference is that tile mode's map is one byte and drives the LUT's
low half through the glyph path, where character mode's is two and drives both halves."*
§2.5 read, from the stride on:

> ⭐ **And the map's row stride is 1024 — a whole VRAM row — not the 160 bytes it needs.**
> §6's copy engine steps rows by the framebuffer's stride, and §8.2 makes character-mode
> scrolling *depend* on that engine reaching the map, so **the map and the framebuffer
> must share a stride or the engine must learn two.**
>
> ⚠ **This draft picks one stride and spends the memory, and that is a choice rather than
> a constraint.** A stride select is a small mux on which bit the row step lands; whether
> it is cheaper than 48 KB is a question for the equations, and §14 item 12 keeps it open.
> Nothing here is fitted, so nothing here can say it does not fit.
>
> ```
>   A18..A16   MAPBASE       (register, 8 positions)
>   A15..A10   cell row      6 bits, 64 rows
>   A9..A8     0             the stride's padding
>   A7..A1     cell column   7 bits, 128 cells (80 displayed)
>   A0         0 = code, 1 = attribute   -- the byte enables of one x16 access
> ```
>
> Still a concatenation, still no adder. **The map costs 64 KB of the 512**, against
> 16 KB at a packed stride — **a real 48 KB**, and §14 item 12 is where the alternative
> is booked.
>
> ⛔ **There is no horizontal scroll in character mode** (§0), so `graphics.md` §6.4.9's
> phase term `H0` ⊕ `HSCROLL[2]` is **not inherited here**: a cell's phase is `H0`, a line
> is **80 codes and not 81**, and §19 item 48's half cell at each end does not exist. The
> term survives in tile mode, where the playfield needs it.

What the address layout did not say, and the design had wrong, is in plan §15.4's
defects 15–17: the map load and grant could never fire, and the attribute arrived two
slots early.

### `plan.md` §3 — the `ATTR` latch

The `ATTR` `'574` is gone: `v3scan`'s last attribute stage drives LUT `A15..A8` through
`ATOE`, the sprite has its own two lines, and the package went to the lane
transceivers. §3 read:

> ```
>       pixel byte  ->  index latch  ->  LUT A7..A0   ---+
>                                                        +--> LUT -> output register -> DAC
>       ATTR byte   ->  ATTR latch   ->  LUT A15..A8  ---+
> ```
>
> | Mode | What drives `ATTR` | Clocked |
> |---|---|---|
> | Character | the map word's attribute byte | once a **cell** — constant for eight dots |
> | Bitmap | the sprite's 2-bit code, zero-extended | once a **dot** |
> | Tile | zero | — |
>
> **The timing claim, stated so it can be attacked.** Both halves of the LUT address
> come from `74AHCT574`s clocked by the same dot edge, so the chain is **index latch →
> LUT → output register, exactly as today**. The LUT's t<sub>AA</sub> is specified from
> *any* address change, so sixteen lines settling together cost what eight do: §6.1's
> budget of 8 + 12 + 5 = 25 ns in 39.72 is unchanged, and **so is the 11.7 ns of
> margin.** ⚠ What is *not* unchanged is fan-out and board routing: eight more address
> lines to a TSOP-44, and §14.2.6's TTL-level constraint (`V_OH` 2.4 V, so `74AHCT` and
> never `74AHC`) applies to them exactly as to the rest.

### `plan.md` §4 — the register file and the scratch rows

The register file's row read *"§5, §7.2's column shadow, and §7's sprite shape"*; the
address map's rows read *"rows 480–511 | off-screen scratch — copyrect staging and `OWSet`
saves. ⭐ The sprite needs none of it (§7 composes at scan time)"* and *"a 64 KB region
at `MAPBASE` | character mode's map, one VRAM row a cell row (§2.5)"*. The shape is now in
that region's last 64 bytes, which with `MAPBASE` 7 is row 511.

### `plan.md` §6, §6.1, §6.2 and §13.3 trade 1 — the copy's byte in `vread`

⛔ **The copy's byte never reached the framebuffer**: its read landed in `vread`, which
drives the backplane and not the internal bus (`GAP_6`). It lands in the posted-write
`'574` now. §6's table read:

> | Write side | **`WPTR`** — the pointer the span writer and the CPU port already use, with `WADV = 01`'s end-of-row behaviour (reload the column from the register-file shadow, step the row). Its byte goes out through the posted-write `'574` |
> | Read side | **`CPTR`**, a second nineteen-bit pointer — its byte arrives in `vread` — with its own column counter, its own shadow and its own row register. ⭐ **Its shadow is a register-file location**, not macrocells — §7.2's trick, and the reason a second pointer is affordable at all |

and its last row *"| **No shifter and ⭐ NO LATCH either** | §13.3 trade 1, settled: the engine
is **byte-granular**, so it reuses §11's `vread` for the read and §5's posted-write `'574`
for the write. **Nothing new on the data path** |"*. §6.1's scroll row read *"| A
character-mode scrolled line (§8.2) | 10.0 ms of **CPU** | **0.95 ms of engine** | |"*.
§6.2 reserved *"rows 480–511"* for the staging and ended *"⚠ Whether it *is* expensive is
a question for the equations; nothing here has been fitted."* Trade 1's second and third
paragraphs read:

>    ⭐ **But the latch is not needed, because the four-byte group is not.** A
>    byte-granular copy reuses two latches the card already has — §11's `vread` and §5's
>    posted-write `'574` — and both reuses are safe under rules that already exist: a copy
>    moves `WPTR`, which is one of the things `RDVALID` already falls on, and `/WAIT`
>    holds a CPU VRAM access while `CBUSY` exactly as it does while `SPANBUSY`.
>
>    **It costs 4× the copy time and buys four packages** — and those four are what pays
>    for the cell-budget escape (`partition.md` §8). ⭐ It also deletes an alignment rule:
>    with no fast path, column congruence stops mattering to software.

### `plan.md` §7 — the shape in the register file

⛔ **Nothing could reach it**: the file's address is `RFA4..RFA0`, and a shape above `+$1F`
needed a sixth and seventh bit, an arbiter against the span writer's colour reads and four
`'165` load strobes — about fifteen pins, on a card whose four parts had nine between
them (plan §14 item 17). §7's table read:

> | Shape | **16×16, two bits a pixel**: 0 transparent, 1 and 2 the two cursor colours, 3 reserved. **64 bytes** — four a row, the low plane's columns 0–7 and 8–15 then the high plane's — written through `SPRIDX` (six bits) / `SPRDAT` |
> | Where it lives | ⭐ **the register file**, not VRAM — so the spare-access arbiter, the map latch and the fetch cadence are all untouched |
> | Per displayed sprite row | **four** register-file bytes into **four `'165`** — two cascaded a plane, so each plane is a sixteen-bit shift chain (`partition.md` §8's escape, which §5 risk 3 says is a requirement) |
> | Per dot of the sprite's sixteen columns | two bits shift out into the **`ATTR` latch** |
> | Colour | sub-palettes 1 and 2, all 256 entries of each loaded with one colour: **1,024 writes, ~2.9 ms**, and only when the cursor's colours change |
> | Position | `SPRX` 10 bits, `SPRY` 9 bits, enable in `SPRH` b7 — the hotspot is the shape's top-left corner |

and the paragraphs under it:

> ⭐ **Why 16×16 and not 8×8** (2026-09-17; `history.md` has the 8×8 text). An arrow with
> a tail does not fit in eight rows — `software/demo`'s pointer is 16×16 and its shape is
> now this card's, pixel for pixel — and eight rows made the cursor an arrowhead whose
> fill reached the outline's outer edge. The price is 48 more bytes of register file, two
> more `'165`, and four macrocells on `v3dot`: the column and row window counters go from
> three bits to four and `SPRIDX` from four to six. ⭐ **The refit for it (2026-09-17)
> took those four cells and cascades *fell* from four to zero**, so the sprite made the
> timing argument no worse; `v3dot`'s present fit, and why its cascades are five, is §14
> item 14. `video3/bench/run-v3sprite.sh` renders every X phase, both 4-byte phases, the
> edges, the line-doubling boundary and all four `VMODE`s against `v3model.py`, and all 36
> positions match pixel for pixel.
>
> ⭐ **Why a serialiser is affordable here and was not for Variant B.** §6.4.6 limit 3
> refuses a glyph serialiser because its output feeds a foreground/background mux
> *inside* index → LUT → output. Here the shift register's output is **re-registered by
> the `ATTR` latch before it reaches the LUT**, so the serialiser has a whole dot period
> to settle and the critical path is untouched. **The register is the difference.**
>
> ⚠ **The X compare is the part to check.** "This dot is the sprite's first" is an
> equality against a 10-bit counter, and then a **16**-state down-counter runs the window —
> equality, not magnitude, and `graphics.md` §6.4.9 already runs compares at this rate.
> But it is dot-rate logic in a CPLD and it has not been fitted. §14 item 2.

The position logic that paragraph called unfitted was fitted, and then found to be three
defects (plan §15.4, 20–22).

### `plan.md` §8.2 — the two-byte cell's scroll arithmetic

> taste. One scrolled line at 80×25 — 24 rows of 160 bytes moved, one row cleared:
>
> | | card work | CPU work |
> |---|---|---|
> | `VSCROLL += 8` | one register write | **clear one row: 271 µs** |
> | **§6's copyrect** | 3,840 bytes at 4.05 MB/s = **948 µs of engine** | six register writes + **the same 271 µs clear** |
> | the same move by CPU, no engine | — | ⛔ **10.0 ms** |
>
> ⭐ **The clear dominates the CPU and both paths pay it**, so at 115.2 kbaud (~144 lines
> a second) the two cost **3.9 % and 4.1 % of the CPU**. The difference is noise. ⚠ The
> copy is **948 µs of *engine*** — 14 % of the engine at that line rate, and the engine
> becomes the limit only past ~1,000 lines a second, which no serial port reaches. At
> 80×60 it is 2.3 ms of engine and the CPU's share is unchanged.

and the paragraph after the table: *"the CPU move is 10.0 ms, so … which is why §2.5 spends
48 KB to give the map the framebuffer's stride."* Every figure scaled with the cell, and
§14 item 11 said *"The CPU move is **10.0 ms a line** (§8.2)"*.

### `plan.md` §9 and §10 — the register map

§9's *"`VSTAT` b0 read and any write to `VSTAT` clearing it"* had no producer behind b0
(`GAP_5`); it is `v3host`'s `IRQPEND`. §10's rows read:

| Off | Name | |
|---|---|---|
| `+$17` | `CCTRL` | b0 `GO`; b1 row direction; b2 column direction; b4..3 `CWIDTH[9:8]`; b5 `CHEIGHT[8]` |
| `+$1D` | `SPRIDX` | shape byte index 0–15, auto-increments after `SPRDAT` |
| `+$1E` | `SPRDAT` | shape byte |

`CCTRL` b1/b2 had been reserved since 2026-09-16 (§6.2), and `SPRIDX` six bits since
2026-09-17; both rows were stale before the shape moved.

### `plan.md` §11 and §12

§11's rows read *"`'153` pixel mux, index latch, output register | §6.1 | **Required** —
and §3 adds one latch beside it"*, *"Register file + `'245` read-back | §3.2 | **Required** —
and §7 puts the sprite shape in it"*, *"Cell addressing by concatenation | §6.4.1 |
**Required**, ⚠ **widened**: six-bit row, two-byte map (§2.5)"*, *"Map fetch pipelined one
cell ahead, two-stage `MAP`/`MAPQ` | §6.4.9 | **Required**, ⚠ **doubled** — the map is a
word now"*, and for `vlen` and `rfa` *"⚠ **Open** — it was a `GAL22V10` because it loaded
from eight pins; whether it absorbs here depends on the partition. §14 item 4"* and
*"⚠ **Open** — same"*. §12's gain read *"**ANSI art renders at 2 writes a cell instead of
11–13**"*.

### `plan.md` §13 — the parts

§13's opening ended *"⚠ **Nothing here is placed or costed**; the programmable-logic count
is deliberately absent, because §14 item 4 says video3 has no partition yet."* §13.1's
rows that changed read:

> | Part | n | Required by |
> |---|---|---|
> | **32K×8 register file** | **1** | §5. ⛔ **It cannot be macrocells**: the span-mask bit *is* this SRAM's address bit 0, which is what makes per-pixel colour selection free. It also holds `SPANLEN`, `WPTR`'s and `CPTR`'s column shadows and §7's sprite shape |
> | ⭐ `74AHCT574` **`ATTR` latch** | **1** | §3. **NEW.** LUT A15..A8 — the cell attribute in character mode |
> | `74HC574` posted-write data | **1** | §5. The span writer's byte, fanned to all four lanes — which is what makes the broadcast write free |
> | `74HCT574` `vread` | **1** | §6 and `VDATA`. The prefetched VRAM byte |

and its total:

> **Discrete total: 32**, against `video/`'s 30 — ⭐ **and no new datapath at all**, because §13.3 trade 1 made the copy engine byte-granular. ⚠ **Plus programmable logic,
> count unknown** (§14 item 4) — and §13.5 says what the board allows.

§13.2's row read *"A sprite shape store | 0 | §7 puts it in the register file, so no
package and no VRAM access"*. Trade 2 said the board *"places at **42 ICs, 75 %** with
everything"* and that *"there is one 8 × 8 sprite"*. §13.4 read:

> ### 13.4 ⚠ Two things that could move between silicon and packages
>
> Recorded because they are partition choices, and §14 item 4 says the partition is not
> written:
>
> - **The map word's two-stage latch.** `graphics.md` §6.4.9 needs the map pipelined one
>   cell ahead, with `MAP` fetched while `MAPQ` is still being displayed. video3's map is
>   a **word**, so that is 32 bits of pipeline. In programmable logic it is macrocells; as
>   two `'574` it is two packages. **Whichever is cheaper is a fit's answer.**
> - **The sprite's two bits onto LUT A9:A8.** Either the `ATTR` latch carries them
>   (one 8-bit mux ahead of it) or a CPLD macrocell drives those two lines directly while
>   the `ATTR` latch stands off. ⚠ **The second is cheaper and puts two drivers on two LUT
>   address lines** — which wants `graphics.md` §13.1's discipline, where *one* pin does
>   both halves of a turnaround so the bus can never have two masters.

§13.5, from its first table on, read:

> | | ICs | courtyard | 240 mm |
> |---|---|---|---|
> | `video`, the built card | 33 | 124.4 cm² | places, 59 % |
> | **video3 as drawn, 3 programmable parts** | **39** | 143 cm² | **places, 67 %** |
> | **video3 as drawn, 4** | **40** | 150 cm² | **places, 73 %** |
> | **video3 as drawn, 5** | 41 | 166 cm² | ⛔ **does not place** |
> | video3 without the copy latch, 4 | 36 | 137 cm² | places, 68 % |
>
> ⛔ **THE PARTITION HAS A CEILING OF FOUR PARTS, and 240 mm is the longest board there
> is.** A PLCC-84 is 33 × 33 mm, so the fifth one is worth three DIP-20s of skyline and
> the board refuses it. **That is a constraint on §14 item 4 that no amount of prose
> would have produced** — and it is the reason this list exists as a file rather than as
> a table in this document.
>
> **The trades of §13.3 against it:**
>
> | | discrete | with 4 parts | |
> |---|---|---|---|
> | Trade 1 taken — **the built configuration** | **32** | **36** | **places, 68 %** |
> | … + `MAP`/`MAPQ` discrete (`partition.md` §8's escape) | 36 | **40** | **places, 73 %** |
> | … + the sprite's **four** `'165` (16×16, §7) | 40 | **44** | **places** — `check:place` asserts placement on 24 cm, and `parts.ts` now carries the four, so the card's own list totals **39** with three parts assumed |
> | ⛔ trade 3, the tri-state pixel bus | — | — | **settled the other way** |
> | ⛔ trade 2, four-pixel `HSCROLL` | — | | **settled the other way** — one pixel is kept |
>
> ⚠ **The `ics` figure in `parts.ts` assumes three programmable parts and says so in its
> own comment.** It is a placeholder, not a finding; what is *asserted* is that the list
> totals its own claim and that 24 cm is the shortest length that holds it.
>
> > ⭐ **This section used to say 35 and it was wrong.** Writing the parts list found the
> > arithmetic error immediately — which is the argument for keeping counts in a file a
> > check reads rather than in a paragraph. `docs.check.ts`'s own header: *"stale headline
> > numbers are this repository's oldest recurring defect."*

The four-part ceiling was a statement about PLCC-84 area, and it stands as that: a fifth
`ATF1508AS` does not place even in `v3lane`'s stead.

### `plan.md` §14 — the open items this round closed or changed

Items **16, 17, 18 and 19** were the four things plan §15.4's first round could not reach,
and all four are closed. They read:

> 16. ⛔ **THE MAP WORD IS NEVER LOADED: `MAPLD = SPARE & CELLTICK` on `v3dot` is
>     unsatisfiable.** `SPARE` is dots 0–1 of the slot and `CELLTICK` is dot 3, so the
>     product is never true and `v3scan` never latches a code or an attribute. **Character
>     and tile mode are unbuilt in effect**, whatever the fits say — and **no bench reaches
>     either mode**: `v3card_tb` runs bitmap mode, `v3dot_tb` runs the raster, and the
>     host emulator (§15 step 2b) models the intent rather than the equations. Whatever
>     replaces it is a `v3dot` edit on a part at 120/128, so it is a refit, and it wants a
>     character-mode frame in `v3card_tb` before it is believed.
> 17. ⚠ **The sprite is not in the card model.** `video3_card.v` has no `'165`s, because the
>     shape lives in the register file **above +$1F** and `RFA4..RFA0` does not reach it —
>     so the file's address is **five bits where §7's 64 shape bytes need more**, and
>     nothing produces the rest. §7's pixel-exact claims rest on the emulator
>     (`run-v3sprite.sh`) and on `v3dot`'s fit, not on a bench of the parts.
> 18. ⚠ **The board needs seven signals no package produces**, and `check:reach` cannot see
>     them: a line only a *discrete* chip reads, and no part produces, falls through both
>     of its directions. `video3_card.v` reaches each by hierarchical reference and names
>     it, so they are counted and not hidden:
>
>     | | |
>     |---|---|
>     | `GAP_1` | **the byte lane of a single-byte access.** `v3ptr`'s mux drives `FBA18..2` and never `WC1:WC0`/`CC1:CC0`, so no discrete part can tell which of the four bytes the span writer, the copy or the prefetch means |
>     | `GAP_2` | **the framebuffer's `/VWE`, `/VOE` and four byte enables** (`signals.md` §1.3). The model derives them from `WEN`, `CSTEP` and the lane — both writers' strobes do leave their packages |
>     | `GAP_3` | **the fetch ranks' clock.** `SLOTTICK` leaves `v3dot`, but it is a combinational tick and a `'574` has no clock enable: the board needs a *clock* |
>     | `GAP_4` | **the map word's part select** — §2.5's `A1` is the cell column's low bit, `MC0`, and `v3scan` is 64/64 and cannot let it out |
>     | `GAP_5` | **`VSTAT` b0, the pending interrupt.** `IRQPEND` is buried in `v3host` |
>     | `GAP_6` | **the copy's write data.** §6's byte goes `vread` → posted-write `'574` → framebuffer (§13.3 trade 1: no copy latch), and no strobe on the card moves it from one to the other |
>     | `GAP_7` | **which source drives the framebuffer's write data** — the posted-write `'574` (direct mode), the register file (span modes: §5's "`WFG` or `WBG` without a mux") or `vread` (the copy). Each needs an output enable, and none is produced |
>
>     ⭐ **And one proposal, not a gap: a `'138` for the palette's four load strobes** —
>     `PIDX` low (`'163` load, +$0E), `PIDX` high (`'574` clock, +$0F), `PDATL` and
>     `PDATH` (`'573` LEs, +$10/+$11). `REGWR` and `RA4..RA0` already leave `v3host`, so one
>     `'138` decodes all four for zero CPLD pins; the model is built that way. It is
>     **+1 IC**, and `hardware/place/parts.ts` does not have it yet.
> 19. ⚠ **`HSCROLL`'s fetch-rank select is not byte-granular in the model.** `v3dot`
>     exports `FOE0`/`FOE1` from `HS1..HS0`, but `video3_card.v`'s `'153` takes all four
>     bytes of a group from the one rank `FOE0` picks, so a bitmap scroll that is not a
>     multiple of four pixels is neither modelled nor checked. `v3card_tb`'s frame is at
>     `HSCROLL` 0.

Item **2** read:

> 2. ⚠ **§7's sprite compare is dot-rate logic and unfitted.** Equality against the
>    column counter plus an eight-state window counter is the cheap form; whether it
>    fits beside the cell counters is a fit, not an estimate.

Item **0**'s closing listed *"the discrete `MAP`/`MAPQ` latches *and* the sprite's shift
registers — **44 ICs**"*; the build took the sprite's escape and not the map's, and is 44
ICs for a different reason — the lane transceivers and `v3lane` in, the `ATTR` `'574` out.
Item **4** read:

> 4. ⚠ **The partition is drafted — [`partition.md`](partition.md) — at FOUR parts, which
>    §13.5 says is the most that places, so **video3 is at its ceiling**. ⭐ **ALL FOUR
>    ARE FITTED.** `v3dot` is **120/128 cells and 50/64 I/O**; `v3ptr` is **125/128 and
>    55/64**; `v3host` is **55/128 and 63/64**. `v3scan` — the map word in silicon — is
>    **100/128 cells and 64/64 I/O**, and `v3scan_mq` — the same part with the map word in
>    four `'574` — is **107/128 cells and 46/64 I/O**. **NO NUMBER FROM `video/`'s FIT APPLIES HERE.**
>    `video/` is three `ATF1508AS` whose utilisation is recorded in
>    `hardware/gal/cpld/*.fit`; **those figures describe a different design** — one with
>    a display list, per-scanline scrolling, a one-byte map and no copy engine. video3
>    has none of that and has no `vaddr`. ⚠ **An earlier draft of this document quoted
>    `video/`'s cell and fan-in counts as if they constrained video3, and used them to
>    justify §2.5's stride and to call §6.2's column direction doubtful.** Both are
>    withdrawn: they are open questions for the equations, not settled by another card's
>    report. **What transfers from `video/` is mechanism and arithmetic; what does not
>    transfer is utilisation.**

Item **5** — *"⚠ **`vlen` and `rfa`** (§11's last two rows) exist on `video/` for partition
reasons that may not survive a re-partition."* — closed: both are absorbed. Item **8**
read:

> 8. ⛔ **The spare-access budget has four requesters now and has not been re-derived.**
>    `graphics.md` §6.4.2 already halves the span writer's slots in cell mode, because
>    the map fetch takes the internal address bus one slot in two. video3 adds **the map
>    *word*** (same access, wider), **copyrect** (two accesses a group), **the sprite row
>    fetch**, and the CPU's read prefetch — against one spare access a slot.
>    `cadence.check.ts`'s equivalent is what decides whether §6.1's rates are real.

Item **12**'s arithmetic was the two-byte cell's — *"at **48 KB**. The alternative is a
stride select … for 16 KB of map"* — and item **13** counted *"a fourth programmable part,
an extra dot-rate `'574` and possibly six more discrete packages"*. Item **15** ended
*"⚠ Rule 3 (`CONSUMERS`) still does not reach video3 — it needs a drawn board, which is
§15 step 8."* `video3_card.v` turned out to be enough of a board for it.

Item **14** stays closed; the parts of it this round changed read:

> … `GSPN & MUXSEL0` *is* the tick, for one literal on a term the receiver has anyway.
>
> **`WMODE` is held on `v3ptr`**: `v3dot` holds `CTRL` as `CT0..CT7` and has no pin to
> export b5..4, so `v3ptr` decodes `LDCTRL` off the broadcast and keeps `WM0`/`WM1`
> itself — `partition.md` §3's idiom, and the same duplication `v3dot` makes of
> `HSCROLL[1:0]`.
> …
> | `RMAP` | `v3dot`'s own `CELLTICK`, mode-qualified — bitmap mode has no map, and granting it the slot's only spare access would spend it on a fetch nothing reads. ⛔ But the map *load* never happens — item 16 |
> | `RRD` | `v3host`'s `RDREQ`, `!RDVALID` — §11's request under its own name, as `video/` spells it |
> | `WRCYC` | `!RW & E`. ⚠ A 6809E write is only valid in E's second half |
> | `RDCK` | the `vread` `'574`'s clock, **active low** so the rising edge ends the access. Two users: the prefetch (`GRD & !RDVALID`) and the copy's read access, which §6 lands in `vread` (trade 1: no copy latch). ⚠ Only the prefetch sets `RDVALID` — a copy byte is from `CPTR`, not the byte at `WPTR` |
> | `RSTART` | `RPQ & !E`, §11's **post-increment** — the dot after a VRAM read's E falls. It reaches `WPTR` as `v3host`'s `WSTEP = CSTEP # RSTART`: one pin, because every `v3ptr` LAB is at 38 of the fitter's 40 inputs and a third `WINC` term did not fit |
> | `IRQEN` | `CTRL` b6, on `v3host`, which pays a data-bus pin for it — `v3ptr` refused it |
> …
> | | cells | I/O | cascades | |
> |---|---|---|---|---|
> | `v3dot` | 120/128 | 50/64 | ⚠ **5** | the raster, the arbiter, `MAPREQ` |
> | `v3scan` | 100/128 | ⛔ **64/64** | 2 | ⛔ **full** — it decodes its own address source |
> | `v3ptr` | **125/128** | 55/64 | **3** | the span sequencer, the two copy decodes, `WMODE`, `RFA0` |
> | `v3host` | 55/128 | ⛔ **63/64** | 0 | the copy's phase machine, the reload walk, `IRQEN` |
>
> ⚠ **`v3dot`'s cascades are five, for `MAPREQ` and its mode qualifier.** `CLAUDE.md`:
> a change in cascades is a timing change even when the cell count is flat. Nothing on
> this card has been timed (item 1), so it is recorded rather than assessed.
>
> ⛔ **`v3host` is one pin from full, and `v3ptr` has three cells** with every LAB at 38
> of 40 inputs — the card's ceiling, and `partition.md` §7.1's point that the binding
> constraint is pins. `keyed-copy.md` §7.2's keyed compare wants **eight** pins on
> whichever part gates the write strobe and there is no such part: its `74HC688`
> version — one pin — is the only one that fits anywhere on this card.

`MUXSEL0` stopped being the bare dot when the `'153` phase took `HSCROLL[1:0]` (defect 19),
so the sequencers take `DP0`; `WMODE` moved back to `v3dot` when the lane mux needed
`v3ptr`'s cells; `RDCK` lost the copy to `PWCK` (defect 25).

### `plan.md` §15 — the ladder, the bench table and the card bench

§15's table read *"It found the ceiling of four programmable parts"* (step 1), *"`ATCLK`
must not be mode-dependent"* (step 2c), *"**four parts**, which §13.5 says is the most
that places. ⛔ **So video3 is exactly at its ceiling**: there is no fifth part, and no room
for a feature that needs one"* (step 4a), *"in that order. `partition.md` §6"* (step 4b)
and *"⭐ **started**: `v3dot_tb` and `v3card_tb` run in `npm run check:video`"* (step 7).
§15.1's bench rows read:

> | `v3dot_tb` | the fetch latches, the mux, both LUT latches, the LUT, the output register | §3: that the `ATTR` half of the address is stable across a cell in character mode and per-dot in bitmap, and that the two never have two masters — `video_card.v`'s `PIXOE` assertion, generalised |
> | `v3char_tb` | the whole card | a CP437 screen with 256 attribute pairs, **the 80×50 and 80×60 geometries**, and §8.2's copy-scroll — the modes `video/` cannot reach at all |
> | `v3copy_tb` | the whole card | §6: aligned and unaligned, both directions, an overlapping scroll, and **that a copy under a span waits** |
> | `v3sprite_tb` | the whole card | §7: the sprite at every X phase including the two that straddle a slot boundary, and that it is **off** in character mode |
> | ⭐ **`v3card_tb`** — **built, §15.4** | **the four parts and the board around them**, `video3_card.v`, driven by a 6809E bus model that honours `/WAIT` | the seams between parts and packages: the register file, the palette path, both sequencers, the reload, a whole frame through the LUT, and the bus fights no single part can see |

§15.4's opening and claim table read:

> `hardware/gal/verilog/video3_card.v` is the four parts wired to the discrete parts of
> §13.1: the two framebuffer parts, the register file, the fetch ranks, the `'153`, the
> index and `ATTR` `'574`s, the LUT and its `'273`s, the `PIDX`/`PDAT` latches, the
> posted-write and `vread` `'574`s, the `VSTAT` `'244` and the read-back `'245`. ⭐ **Every
> net between two parts is the term lists' own**: the port maps and the wire list are
> generated by `v3portmap.ts` (run by `gen.ts`) from the `.cpld.ts` inputs and externals,
> so a buried cell cannot become a net by being mentioned. Where the board needs a signal
> no package lets out, the wrapper reaches into the part by hierarchical reference and
> names it `GAP_n` — §14 item 18.
>
> `v3card_tb` drives it one 6809E bus cycle at a time, **stretching E-high while `/WAIT` is
> asserted** with `clkdec`'s semantics, and a bound turns a hang into a failure. It runs in
> `npm run check:video` as `v3card` — **34 claims, 0 failed**:
>
> | | |
> |---|---|
> | the palette | four writes land at LUT entries 0..3, and `PIDX` walks |
> | direct `VDATA` | eight writes land at `WPTR`, `WPTR`+1, …, nothing either side moves, and eight reads return them in order, **post-incrementing** |
> | the span writer | a mask of `$86` is `F1 B2 B2 B2 B2 F1 F1 B2` — **bit 7 first** — four back-to-back `$FF` masks are 32 `WFG` pixels with the CPU held by `/WAIT` while each span runs; span-solid is **one `SPANLEN`, many spans**; `WADV` 01 chains four masks down four rows at the same column |
> | the copy | a 13 × 5 copy lands byte for byte in every lane and row, `CBUSY` sets and clears in `VSTAT`, nothing around it moves, and it takes **130 granted accesses for 65 bytes** — two a byte, §6.1's 4.05 MB/s (the claim allows 130–150) |
> | the picture | a whole 640 × 480 `VMODE` 11 frame: 480 lines of 640, VRAM row 0 first, each line the next row, **every pixel the byte at its own address through the LUT** |
> | the board | `v3scan` and `v3ptr` never both on the address bus, never two drivers on D7..D0, never two masters on the LUT address, and `/WAIT` always released |

and its close:

> ⛔ **It found fourteen defects, every one of which had fitted.** Each is fixed in the
> term lists with a ⛔ comment at the fix; the list is the card's argument for §15.1's
> "top down":
> …
> ⚠ **What it does not reach**: character and tile mode (§14 item 16 — the map word is
> never loaded), the sprite (item 17), a horizontal scroll that is not a multiple of four
> (item 19), and the timing. It is a model of the logic, as every wrapper in
> `hardware/gal/verilog/` is.

### `partition.md` — the figures, the lanes, and the sprite read

The header said *"⭐ **ALL FOUR PARTS ARE FITTED since 2026-09-16**"*. The broadcast
section's table and the paragraph under it read:

> | | cells | I/O | cascades | what the swap did |
> |---|---|---|---|---|
> | `v3host` | **55 / 128** | ⛔ **63 / 64** | 0 | **22 pins back**, off a part that had none — and spent since on the copy's phase machine, the reload walk and `IRQEN` (plan §14 item 14) |
> | `v3scan` | ⭐ **100 / 128** | 64 / 64 | ⭐ **2** | 14 cells and 14 cascades *cheaper* |
> | `v3scan_mq` | 107 / 128 | 46 / 64 | ⚠ **41** | ⛔ 25 cells and 25 cascades dearer |
> | `v3ptr` | **125 / 128** | **55 / 64** | 3 | free — and it gained the fix below |
> | `v3dot` | **120 / 128** | **50 / 64** | 5 | a cell for a pin, the raster fix, then the 16×16 sprite |
>
> ⚠ **The receivers mostly did not pay, and the fitter is why — which means none of these
> deltas is a property of the design.** The expectation was ~6 cells of decode each against an
> unchanged pin count. What happened is that the same six-cell edit made `v3scan` 14 cells
> cheaper and `v3scan_mq` 25 cells dearer, in opposite directions, with 41 cascades on the
> variant §5 recommends. **That is placement heuristics above 80 % utilisation**, and the only
> figure the swap produced worth designing against is `v3host`'s 22 pins, which is arithmetic.

The first-fit section, from its misses table on:

> | `ATO7..ATO0` | 8 | the attribute byte **leaving** for the `ATTR` latch — §3's crossing table never listed it |
> | `PA7..PA0` | 8 | the pixel bus is **sixteen** bits here, because one ×16 spare access carries both map bytes |
>
> ⭐ **And the escape §5 risk 2 is plumbed to turns out to buy pins as well as cells** —
> which an earlier analysis got wrong by calling it "pin-neutral", having forgotten the
> same sixteen bits. With the pipeline in four `'574` on the pixel bus, neither map byte
> enters this part: the code arrives already staged, and the attribute goes straight to the
> `ATTR` latch. **Both fitted:**
>
> | | cells | I/O | cascades |
> |---|---|---|---|
> | `v3scan`, map word in silicon | 100 / 128 (78 %) | **64 / 64 (100 %)** | 2 |
> | `v3scan_mq`, map word discrete | **107 / 128 (83 %)** | **46 / 64 (71 %)** | ⚠ **41** |
>
> ⚠ **Both figures moved when the broadcast went in, and they moved in opposite
> directions** — the silicon variant lost 14 cells and 14 cascades, the discrete one gained
> 25 cells and 25 cascades, from the same six-cell edit. That is placement heuristics at 83 %
> utilisation, not logic, and it means **neither cascade count should be read as a property
> of the design**. ⛔ **41 cascades on the variant this section recommends is a delay
> question that only a timing analysis answers**, and it is now §5's first risk.
>
> ⛔ **64 of 64 I/O is no headroom at all** — less than the single spare pin `graphics.md`
> already treats as a standing hazard on the other card. **The discrete variant is not an emergency valve any more —
> it is the sensible default**, and plan §13.3 trade 1 already bought the four packages
> for it.

§0:

> **Four parts**, and `plan.md` §13.5 already measured that **four is the most that places
> on a 240 mm board**.
>
> ⛔ **So video3 is exactly at its ceiling.** There is no fifth part, which means there is
> no room for a feature that needs one — and the partition below has no slack to give a
> later change. That is the single most important consequence of this document, and it
> should be read before anything is added to plan §0.
>
> | | Cells, est. | I/O, est. | What it is |
> |---|---|---|---|
> | **`v3dot`** | ⭐ **120 / 128, FITTED** | **50 / 64, FITTED** | the raster, the dot path, the sprite, the arbiter |
> | **`v3scan`** | ⭐ **100 / 128, FITTED** | ⚠ **64 / 64, FITTED** | the scan and cell addresses, the map word |
> | **`v3ptr`** | ⭐ **125 / 128, FITTED** | **55 / 64, FITTED** | `WPTR`, `CPTR`, the span writer, the copy engine |
> | **`v3host`** | **55 / 128, FITTED** | ⛔ **63 / 64, FITTED** | the backplane, the registers, the palette write path |
>
> ⚠ **`v3host` is pin-bound, not cell-bound** — under half full of macrocells and one pin
> from full, because it is the part the backplane lands on.

§2's tables, rows that changed: `v3dot` held *"`CTRL` — `VMODE`, `MODE`, `WMODE`, enables |
8"*, *"the sprite: `SPRX`, `SPRY`, `SPRH`, `SPRIDX`, two shift registers, the window
counter | ~46"* and *"plus the dot-path control, sync, blanking, the cadence | ~30
combinational"*, and *"⭐ **Why the LUT's three output enables are here.** `PIXOE`, `ATOE`
and `PIDXOE` …"*. `v3scan`:

> | ⚠ **`MAP` / `MAPQ`** — the map is a word, so the two-stage pipeline is **32 bits** | 32 |
> | `TILEBASE`, `MAPBASE` | 8 |
> | the `VA` mux, scan side | 17 |
>
> ⚠ **`MAP`/`MAPQ` is a third of this part**, and plan §13.4 already records the
> alternative: two `'574` instead, at two packages. **If the fit is short, this is the
> first thing to move** — and §13.5 says the board has room for the packages where it has
> none for a fifth PLCC.

`v3ptr` held *"`SPANLEN`, the mask serialiser, the three-bit mask counter, `WADV` | 21"*,
*"`SPANBUSY`, `CBUSY`, the span and copy sequencers | ~10"*, and *"So `RFA`, `RFWE` and
`RFOE` are here."* `v3host`: *"It is **~24 cells and ~45 pins** … ⭐ **And it needs no
`IDB`** — every register it touches is a discrete latch or counter that loads from the bus
itself, so `v3host` only strobes them."* — it takes `D6` for `IRQEN`. §3's crossing rows
read:

> | `IDB[7:0]` — the card's internal data bus | 8 | every part. The `'245` bridges it to the backplane; the register file, the `'573`s and the posted-write latch sit on it |
> | the cadence — `SLOTPH[1:0]`, `FETCH`, `SPARE`, `CELLTICK`, `HLOAD`, `VLOAD`, `ROWADV` | 8 | `v3dot` → `v3scan`, `v3ptr` |
> | requests / grants — map, copy, span, prefetch | 4 + 4 | in and out of `v3dot` |
> | `MODE[1:0]`, `M0` | 3 | `v3dot` → the others |
> | `WMODE[1:0]` | 2 | `v3dot` → `v3ptr` |
> | ⚠ the sprite shape read — `SPRRD`, `SPRROW[2:0]` | 4 | `v3dot` → `v3ptr` |
> | ⭐ `HSCROLL[1:0]` | **0** | **duplicated on `v3dot`, not routed** — both parts are on `IDB` and the register bus, so the same store writes both copies: 2 macrocells against 2 pins (`signals.md` §3.4) |

and §3.1, withdrawn with the register-file shape:

> ### 3.1 ⚠ The sprite shape is the one cross-part read, and it is a cost plan §7 did not price
>
> plan §7 put the shape in the register file *"so the spare-access arbiter, the map latch
> and the fetch cadence are all untouched"* — which is true, and it was the right call
> against a VRAM-resident shape. **But the register file is `v3ptr`'s and the sprite is
> `v3dot`'s**, so once a scanline `v3dot` has to ask for two bytes: `SPRRD` plus three
> bits of row, and the byte comes back on `IDB`.
>
> **Four pins on each part, and the timing is relaxed** — the fetch is once per displayed
> sprite row and can sit in horizontal blanking. Recorded because it is a real cost of a
> choice made before the partition existed, and because the alternatives are worse: the
> shape in macrocells is 128 bits, and the shape in VRAM puts `v3dot` on the arbiter *and*
> needs `PB[7:0]` on it, which is eight more pins than this.

§4's last row read *"A fifth part for the copy engine | ⛔ it does not place"*. §5's first
four risks:

> 1. ⛔ **There is no fifth part.** §0. Any later feature needing one is a card revision.
> 2. ⚠ **`v3scan` at ~108 estimated cells is the tightest — but its escape is now paid
>    for.** A third of it is `MAP`/`MAPQ`, and plan §13.4 offers discrete latches instead.
>    §8 measured that the board would not take them *and* four CPLDs — until plan §13.3
>    trade 1 returned four packages. **It now places at 40 ICs, 73 %.**
> 3. ⛔ **`v3dot` NEEDS its escape — it is not optional.** With the sprite's shift
>    registers in silicon the fitter answers **`Design does not fit`**; with them in
>    `'165`s — four since the sprite became 16×16, plan §7 — it is **120/128 cells, 50/64
>    I/O, 5 cascades**. §8's escape is therefore a
>    requirement, and plan §13.3 trade 1 is what paid for it.
> 4. ⚠ **The `VA` tri-state discipline.** Two parts on seventeen nets, and the rule that
>    they never drive together has to be *checked*, not asserted —
>    `graphics.md`'s lesson that **a model which ORs its drivers cannot see a bus fight**
>    applies directly.

§6 counted *"four term lists, four fits, seven variants"*, struck steps 1, 3 and 5 through
with `~~`, and its step 6 read *"⛔ **Explain `v3scan_mq`'s 41 cascades, or accept them
with a timing number.** It is the recommended variant and it is the only figure on the
card that got worse."* §6.1 ended *"plan §14 item 18 has the seven the card wrapper
found."* §8, whose placement tables were measured against the list as it stood on
2026-09-16:

> ## 8. ⭐ What does buy headroom — and what the board charges for it
>
> Two moves take logic out of silicon without adding a pin:
>
> | | Buys | Costs |
> |---|---|---|
> | **`MAP`/`MAPQ` → 4 × `'574`** | **−32 cells** on `v3scan`, the tightest part. ⭐ And the **attribute half never enters a CPLD at all** — `PB` → `MAPQ` → the `ATTR` latch → the LUT — so `v3scan` loses eight output pins and gains eight input pins for the code half: **pin-neutral** | 4 packages |
> | **the sprite's shift registers → `'165`** | **−32 cells and −2 pins** on `v3dot` (−16 when the sprite was 8×8). The serial outputs go straight to LUT `A9..A8`, so they never come back | **4 packages** — two cascaded a plane, because a 16×16 row is 32 bits |
>
> ⛔ **But the board is full, and `npm run check:place`'s packer says so:**
>
> | | ICs | 240 mm |
> |---|---|---|
> | 4 CPLD, as drawn | 40 | **places, 73 %** |
> | 4 CPLD **+ `MAP`/`MAPQ` discrete** | 44 | ⛔ **does not place** |
> | 4 CPLD + `MAP`/`MAPQ` + the sprite shifters | 46 | ⛔ **does not place** |
> | 5 CPLD | 41 | ⛔ **does not place** |
>
> ⭐ **So relief in silicon has to be paid for in packages, and only plan §13.3's trades
> have any to give:**
>
> | | ICs | |
> |---|---|---|
> | ⛔ ~~minus the `'153` mux~~ (trade 3) | — | **withdrawn** — trade 3 is settled the other way, plan §13.3 |
> | 4 CPLD + `MAP`/`MAPQ`, **minus the copy latch** (trade 1: it borrows the fetch rank) | 40 | **places, 73 %** |
> | 4 CPLD + both discrete moves, minus the copy latch | 42 | **places, 75 %** |
>
> ⭐ **BOTH TRADES ARE SETTLED SINCE 2026-09-16, and the coupling is gone.**
>
> **Trade 3** went the other way — the `'153` mux stays, because the tri-state bus must
> break before make and §8.2's second rank doubled the drivers after §6.1 costed four of
> them. So it yields nothing.
>
> **Trade 1** was never a sharing question: a `'574` has one output enable and the fetch
> rank's is committed to the pixel bus. ⭐ **But the latch is not needed at all** — a
> byte-granular copy reuses `vread` and the posted-write `'574` — and that returns **four
> packages**:
>
> | | ICs | 240 mm |
> |---|---|---|
> | 4 CPLD, trade 1 taken | **36** | **places, 68 %** |
> | … + `MAP`/`MAPQ` discrete — §5 risk 2's escape | **40** | **places, 73 %** |
> | … + the sprite's shift registers — §5 risk 3's escape | **42** | **places, 75 %** |
>
> ⛔ **AND BOTH ESCAPES TURNED OUT TO BE MANDATORY, not optional.** The fits say so:
> `v3dot` with its shifters in silicon is refused outright, and `v3scan` with the map word
> in silicon is **64 of 64 I/O** — not one pin spare, past the state `graphics.md` flags on `vsup` as a
> standing hazard. **So the six discrete packages are part of the design, not a reserve**,
> and the board places them: 42 ICs at 75 %.
>
> ⭐ **The package budget no longer gates the macrocell budget**, and the partition has
> slack it did not have this morning.
> What it cost is **4× the copy time** — 30 ms for a 192-row window scroll against 350 ms
> without an engine at all.
>
> **Trade 2 is settled too, and the other way**: `HSCROLL` keeps its one-pixel step and its
> second fetch rank, because trade 1 already paid for the escapes that rank's four packages
> used to be earmarked for. plan §13.3 has the reasoning; ⚠ plan §14 item 13 — **there is no
> power budget** — is the only thing that could reopen it.

### `signals.md` — the lines that were renamed, moved or deleted

The header's note read:

> ⚠ **Nothing here is fitted.** Counts are *derived from the parts list*
> (`hardware/place/parts.ts`, the `video3` alternate), not from a fitter. What this
> document is for is the question plan §14 item 4 cannot answer without it: **how many
> programmable parts, and what goes in each** — and §13.5 bounds the answer at four,
> because a fifth PLCC-84 does not place on a 240 mm board.

The rows that changed read:

> | `FCLK0`, `FCLK1` | 2 | the two fetch-latch ranks, 4 × `'574` each | the slot phase, and which rank this line's `HSCROLL[1:0]` wants |
> | `FOE0`, `FOE1` | 2 | the ranks' `/OE` | ⭐ **constant for a whole line** — `graphics.md` §8.2: `c < HSCROLL[1:0]` is why the rank select is an output enable and not a mux. The second rank is what buys **one-pixel** `HSCROLL` |
> | `MUXSEL[1:0]` | 2 | the four `'153` | the dot phase within the slot |
> | `IXCLK` | 1 | the index `'574` | every dot |
> | `ATCLK` | 1 | the `ATTR` `'574` | every dot — see §3.2 for **why not per cell** |
> | `PIXOE` | 1 | the index latch's `/OE` **and** the LUT's `/OE` | one pin, both halves — §3.1 |
> | `ATOE` | 1 | the `ATTR` latch's `/OE` onto LUT `A15..A8` | §3.1 |
> | `SPRA[1:0]` | 2 | LUT `A9..A8` directly, in bitmap mode | the sprite serialiser — plan §13.4's open choice |
> | `PIDXLD` | 1 | load the `'163` pair from the internal data bus (`+$0E`) |
> | `PIDXCE` | 1 | count enable — the auto-increment after `PDATH` |
> | `PIDXHCK` | 1 | the `PIDX`-high `'574`'s clock (`+$0F`) |
> | `PIDXOE` | 1 | **two** `'244` onto the LUT address bus — 16 bits now, not 8 |
> | `PDLLE`, `PDHLE` | 2 | the two `'573` |
> | `/VLB0` `/VUB0` `/VLB1` `/VUB1` | 4 | ⭐ **the byte enables do three jobs here**: §7.4's broadcast write, §6's four-byte copy, and §2.2's map **word**. `video/` has only the first |
> | `WEN` | 1 | ⚠ **not the same as `RETIRE`** — sprite `WMODE` retires without writing |
> | `CRD`, `CWR` | 2 | the read access and the write access — ⭐ **two accesses a group**, which makes this the heaviest requester in §1.8 |
> | `CCOL`, `CROW` | 2 | the shared column counter's step and the row step, each ±1 by `CCTRL` b1/b2 |
> | `SPRLD` | 1 | load the **four** `'165` from the register file — 16×16 is four bytes — once per displayed sprite row |
> | `SPRSH` | 1 | shift, once per dot inside the sprite's eight columns |
> | `SPRHIT` | 1 | the sprite covers this dot: an **equality** against the column counter, then a **sixteen**-state window counter |
> | the sprite's row fetch | one *register-file* read a sprite row | — ⭐ **not on this bus at all**, which is why plan §7 put the shape in the register file |
> | `MAP` / `MAPQ` | **32** | ⚠ **the map is a WORD now**, so `graphics.md` §6.4.9's two-stage pipeline doubles |
> | `SPRX`, `SPRY`, `SPRH`, the window counters | 36 | the sprite — the shift registers are the four `'165` |
> | `PB[7:0]` | 8 | the pixel bus — the map latch, the copy latch and `vread` all read it |
> | `A15..A8` | the `ATTR` latch; the sprite's two lines; `PIDX`'s high `'244` |

§3.2, withdrawn with the latch it was about:

> ### 3.2 `ATCLK` must run every dot, even in character mode
>
> The tempting saving is to clock the `ATTR` latch once a **cell**, since plan §3's
> timing argument is that the attribute is constant across one. ⛔ **Do not**: that makes
> a clock line mode-dependent, which is a mux on a clock, and clock muxes glitch.
>
> ⭐ **Clock it every dot and hold its *input* constant instead.** The timing argument is
> about when the LUT's address settles, not about how often the latch is clocked — a
> latch reloaded with the same value is as stable as one not clocked at all, and the
> control line stays a constant.

and §3.3 said copyrect wants two accesses *"for every four-byte group"* — it is two a byte
since 2026-09-16 (plan §13.3 trade 1). §1.5's copy-latch row read *"⛔ ~~`CLCK`, `CLOE`~~ | 0 | **deleted** — plan §13.3 trade 1: the copy is byte-granular and reuses `vread` and the posted-write `'574`. There is no copy-read latch"*.

### `keyed-copy.md` §1, §5, §7 — where the source byte is, and who has pins

§1 read *"The source byte is already latched in `vread` on the read access and leaves
through the posted-write `'574` on the write"* and *"`v3ptr` has **3 macrocells and 9 pins
spare**, `v3host` **one pin**"*. §5's checklist: *"`v3dot` has 14 pins and 8 cells,
`v3scan` none, `v3ptr` 9 pins and 3 cells, and `v3host` **one pin**"*. §7's table and the
paragraphs under it:

> | `v3dot` | **120/128** — 8 spare | 50/64 — 14 spare | ⚠ 5 | 43/128 |
> | `v3host` | 55/128 — 73 spare | ⛔ **63/64** — **one** pin spare | 0 | 0 |
> | `v3ptr` | ⛔ **125/128** — 3 spare | 55/64 — 9 spare | **3** | 50/128 |
> | `v3scan` | 100/128 — 28 spare | ⛔ **64/64** — **no** pin spare | 2 | 20/128 |
>
> ⚠ **`v3ptr`'s 3 cascades are the baseline a refit is compared against**, not
> zero, and its Nodes+FB is at 134 % with every LAB at 38 of 40 inputs — a part
> that refuses additions on grouping before it runs out of cells.
>
> ⛔ **The room is cells on `v3host` and `v3scan`, and neither has pins.** Pins
> are the binding constraint (`partition.md` §7.1), and the only part with more
> than one spare is `v3dot`, which gates no write strobe.

§7.2 opened *"`vread` latches it on the read access and it leaves through the
posted-write `'574`"*, and §7.3 ended:

> ⭐ **AND THE KEY WOULD BE A DESIGN-IN, NOT A RETROFIT — which makes it cheaper
> than any of the above suggests.** `CDONE`, `CSTEP`, `CROWADV` and `RCPY` are
> declared as **inputs** on `v3ptr` (`v3ptr.cpld.ts` §228) and consumed by `v3dot`'s
> arbiter (§205), and **nothing in the repository generates them**: the copy
> micro-sequencer does not exist yet. Whoever builds it decides where the write
> strobe comes from, and a key is one more term on a strobe that is still being
> designed — rather than a change to a part that has already fitted at 85% with 3
> cascades.
>
> ⚠ **What is still missing before any of this is a design**: the copy sequencer
> itself; a **re**fit of whichever part gains the compare, read out of the new
> `.fit` and compared **against `v3ptr`'s existing 3 cascades and 110 cells**, not
> against zero; and the spare-access budget re-derived, which `plan.md` §14 item 8
> has owed since before any of this was asked.

The copy sequencer it waited for was built the same day (plan §14 item 14), and the write
strobe it would gate is `v3ptr`'s `VWE`.

### `hardware/gal/video3/README.md`

Its table's rows read `v3scan` *"100 / 128 | ⚠ **64 / 64** | 2 | the map word in
silicon"*, `v3scan_mq` *"⭐ the map word in four `'574`"* (then the recommended variant),
`v3dot` *"**120 / 128** | 50 / 64 | ⚠ **5**"*, `v3ptr` *"**125 / 128** | 55 / 64 |
**3**"* and `v3host` *"**55 / 128** | ⛔ **63 / 64** | **0**"*, and it closed with a
section headed *"Not written yet"* naming `v3host`, which had been written and fitted on
2026-09-16.
