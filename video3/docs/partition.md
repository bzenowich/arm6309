# video3 — the partition

**DRAFT, 2026-09-16.** Which programmable part holds what, derived from
[`signals.md`](signals.md)'s census. This is plan §15 step 4's first half: a partition
comes before term lists, and how many parts video3 takes is an *output* of it.

> ⭐ **ALL FOUR PARTS ARE FITTED since 2026-09-16** — `hardware/gal/video3/*.cpld.ts`,
> `gal/cpld/*.fit`. Numbers below that are *not* marked FITTED are still bits of state
> plus an estimate of the combinational logic around them. An `ATF1508AS` in PLCC-84 is
> **128 macrocells and 64 I/O**.
> ⚠ **No figure from `video/`'s fit applies here** (plan §14 item 4).

### ⭐ The broadcast, adopted 2026-09-16 — and it paid on every part

`v3host` first fitted **full — every I/O pin taken**, with 77 macrocells idle and no next
step in it ([`history.md`](history.md) has the figures). §2.4's estimate was 19 pins light for a reason worth stating plainly — **a
per-register load strobe is a pin, and video3 has 30 of them.**

§3's answer was already in this document: broadcast `RA4..RA0` + `REGWR` and let each part
decode the offsets it cares about. **All four parts are now wired that way and re-fitted**,
and the offsets live in one shared table, `hardware/gal/video3/regmap.ts`, read by all four
designs — a private copy per part is exactly the drift this card cannot afford, because a
decode that disagrees with the spec fits perfectly well and answers the wrong address.

⭐ **What each part costs now** — and [`history.md`](history.md) has what it cost before,
which is where the comparison lives, because a superseded utilisation figure in a spec is
a number `check:docs` cannot tell from a live one:

| | cells | I/O | cascades | what the swap did |
|---|---|---|---|---|
| `v3host` | **27 / 128** | ⭐ **42 / 64** | 0 | **22 pins back**, off a part that had none |
| `v3scan` | ⭐ **100 / 128** | 63 / 64 | ⭐ **2** | 14 cells and 14 cascades *cheaper* |
| `v3scan_mq` | 107 / 128 | 46 / 64 | ⚠ **41** | ⛔ 25 cells and 25 cascades dearer |
| `v3ptr` | **110 / 128** | **44 / 64** | 3 | free — and it gained the fix below |
| `v3dot` | **117 / 128** | **52 / 64** | 4 | a cell for a pin, then the raster fix |

⚠ **The receivers mostly did not pay, and the fitter is why — which means none of these
deltas is a property of the design.** The expectation was ~6 cells of decode each against an
unchanged pin count. What happened is that the same six-cell edit made `v3scan` 14 cells
cheaper and `v3scan_mq` 25 cells dearer, in opposite directions, with 41 cascades on the
variant §5 recommends. **That is placement heuristics above 80 % utilisation**, and the only
figure here worth designing against is `v3host`'s 22 pins, which is arithmetic.

⛔ **And it bought something the strobe wiring could not express at any price.** A strobe per
*register* cannot load a register **wider than the bus**, and v3ptr has six of them — `WPTR`
and `CPTR` are 19 bits across three bytes, `CWIDTH` is 10 with its top two in `CCTRL`,
`CHEIGHT` is 9 with its top one there. Every one was loading all its bits from a single
strobe, so a store to `+$08` put `D0` into **both `WC0` and `WC8`**. On the broadcast an
extra offset is a decode cell, not a pin: `v3ptr` went from 7 strobes to 10 offsets, the
loads are per-bit, and **the fix cost nothing** — same 110 cells, one pin fewer. §6.1 has it
as a finding, because it is a third instance of the shape that section is about.

⚠ **`v3ptr_rows` and `v3ptr_both` now refuse outright** (`INTERNAL ERROR`), where the strobe
wiring fitted them at 128 / 128. The per-bit load costs product terms in exactly the block
whose cost grows with width, so plan §6.2's rejection of the direction bits is no longer a
judgement about cascades — it is the fitter declining. Their stale `.fit`s were deleted
rather than kept: they describe a term list that no longer exists.

### ⛔ What the first fit corrected

| | estimated | **fitted** | |
|---|---|---|---|
| `v3scan` cells | ~108 | **114** | close |
| `v3scan` I/O | ~50 | ⚠ **63 of 64** | ⛔ **the estimate was wrong by thirteen pins** |

**Both misses have one cause: the map is a *word*.**

| missed | pins | |
|---|---|---|
| `ATO7..ATO0` | 8 | the attribute byte **leaving** for the `ATTR` latch — §3's crossing table never listed it |
| `PA7..PA0` | 8 | the pixel bus is **sixteen** bits here, because one ×16 spare access carries both map bytes |

⭐ **And the escape §5 risk 2 is plumbed to turns out to buy pins as well as cells** —
which an earlier analysis got wrong by calling it "pin-neutral", having forgotten the
same sixteen bits. With the pipeline in four `'574` on the pixel bus, neither map byte
enters this part: the code arrives already staged, and the attribute goes straight to the
`ATTR` latch. **Both fitted:**

| | cells | I/O | cascades |
|---|---|---|---|
| `v3scan`, map word in silicon | 100 / 128 (78 %) | **63 / 64 (98 %)** | 2 |
| `v3scan_mq`, map word discrete | **107 / 128 (83 %)** | **46 / 64 (71 %)** | ⚠ **41** |

⚠ **Both figures moved when the broadcast went in, and they moved in opposite
directions** — the silicon variant lost 14 cells and 14 cascades, the discrete one gained
25 cells and 25 cascades, from the same six-cell edit. That is placement heuristics at 83 %
utilisation, not logic, and it means **neither cascade count should be read as a property
of the design**. ⛔ **41 cascades on the variant this section recommends is a delay
question that only a timing analysis answers**, and it is now §5's first risk.

⛔ **63 of 64 I/O is one pin of headroom**, which is the state `graphics.md` flags on
`vsup` as a standing hazard. **The discrete variant is not an emergency valve any more —
it is the sensible default**, and plan §13.3 trade 1 already bought the four packages
for it.

---

## 0. The answer, and the thing it runs into

**Four parts**, and `plan.md` §13.5 already measured that **four is the most that places
on a 240 mm board**.

⛔ **So video3 is exactly at its ceiling.** There is no fifth part, which means there is
no room for a feature that needs one — and the partition below has no slack to give a
later change. That is the single most important consequence of this document, and it
should be read before anything is added to plan §0.

| | Cells, est. | I/O, est. | What it is |
|---|---|---|---|
| **`v3dot`** | ⭐ **117 / 128, FITTED** | **52 / 64, FITTED** | the raster, the dot path, the sprite, the arbiter |
| **`v3scan`** | ⭐ **100 / 128, FITTED** | ⚠ **63 / 64, FITTED** | the scan and cell addresses, the map word |
| **`v3ptr`** | ⭐ **110 / 128, FITTED** | **44 / 64, FITTED** | `WPTR`, `CPTR`, the span writer, the copy engine |
| **`v3host`** | **27 / 128, FITTED** | **42 / 64, FITTED** | the backplane, the registers, the palette write path |

⚠ **`v3host` is pin-bound, not cell-bound** — a fifth full of macrocells and two thirds
full of pins, because it is the part the backplane lands on. **It is not cells that stop
it merging** — §7 has the arithmetic, and it is pins every time.

> ⚠ **Corrected 2026-09-16**: an earlier draft put `v3host` at ~40 cells by counting
> `PIDX`'s sixteen bits. `PIDX` is **discrete** in `hardware/place/parts.ts` — two
> `'163` and a `'574` — so those bits are not macrocells at all. The conclusion does not
> move, because the constraint was never cells.

---

## 1. What forced the shape

`graphics.md` §10.1.2 is the precedent and the warning: a ten-GAL build spent **52 % of
its pins on the packaging talking to itself**, and the one place merging costs silicon
rather than saving it is the framebuffer address mux — *"on GALs the scan and `WPTR`
pairs tri-state onto a shared bus for free; inside one die two macrocells cannot drive
one pin."*

**`VA[16:0]` has five sources** (plan §14 item 3) and they fall into two clusters:

| | Sources | Lives with |
|---|---|---|
| **scan-side** | the bitmap scan address, the cell/tile concatenation, the map fetch | the scan counters, the cell counters, `TILEBASE`/`MAPBASE` |
| **pointer-side** | `WPTR`, `CPTR` | the span writer and the copy engine |

Putting both clusters in one part costs ~125 macrocells before any control logic — the
scan side alone carries **32 bits of `MAP`/`MAPQ`**, because video3's map is a *word*.

⭐ **So `VA` is a tri-stated bus between `v3scan` and `v3ptr`**, exactly as the GAL build
had it and for the same reason. An `ATF1508AS` macrocell has a product-term output
enable, so this costs no extra silicon — **17 pins on each part, one net each.**

⛔ **And it costs a discipline**: the two parts must never drive `VA` together. The
grant that decides it is one signal from one place (§3), not an agreement between two.

---

## 2. The four parts

### 2.1 `v3dot` — the raster, the dot path, the sprite, the arbiter

| Holds | bits |
|---|---|
| dot counter, line counter | ~20 |
| `M0`, the frame-end family latch | 1 |
| ⭐ **`CTRL`** — `VMODE`, `MODE`, `WMODE`, enables | 8 |
| the sprite: `SPRX`, `SPRY`, `SPRH`, `SPRIDX`, two shift registers, the window counter | ~46 |
| the spare-access arbiter | ~6 |
| **plus** the dot-path control, sync, blanking, the cadence | ~30 combinational |

**Why `CTRL` is here and not on the host part.** Everything reads it and one thing
writes it. Put it where `MODE` and `VMODE` are consumed at dot rate, and export two
bits of `MODE` rather than importing six.

⭐ **Why the arbiter is here.** It has the cadence, and the cadence is the timing
reference. §3 is the whole of it.

⭐ **Why the LUT's three output enables are here.** `PIXOE`, `ATOE` and `PIDXOE` are the
three masters of §1 of `signals.md` §3.1, and `graphics.md` §13.1's discipline is *one
pin doing both halves of the turnaround so the pair can never be half-turned*. With
three masters that becomes **one part deciding all three**, never three parts agreeing.

### 2.2 `v3scan` — the scan and cell addresses

| Holds | bits |
|---|---|
| `HSCROLL`, `VSCROLL` | 19 |
| the scan row and column counters | 19 |
| the cell row (six bits) and cell column counters | 13 |
| ⚠ **`MAP` / `MAPQ`** — the map is a word, so the two-stage pipeline is **32 bits** | 32 |
| `TILEBASE`, `MAPBASE` | 8 |
| the `VA` mux, scan side | 17 |

⚠ **`MAP`/`MAPQ` is a third of this part**, and plan §13.4 already records the
alternative: two `'574` instead, at two packages. **If the fit is short, this is the
first thing to move** — and §13.5 says the board has room for the packages where it has
none for a fifth PLCC.

### 2.3 `v3ptr` — the pointers, the span writer, the copy engine

| Holds | bits |
|---|---|
| `WPTR` | 19 |
| `CPTR` | 19 |
| `CWIDTH`, `CHEIGHT`, `CCTRL` | 22 |
| `SPANLEN`, the mask serialiser, the three-bit mask counter, `WADV` | 21 |
| `SPANBUSY`, `CBUSY`, the span and copy sequencers | ~10 |
| the `VA` mux, pointer side | 17 |

⭐ **The mask serialiser and the register-file address must share a part**, because
`graphics.md` §7.4's trick is that *the serialiser's serial output is the register
file's address bit 0* — which is what makes per-pixel colour selection free. So `RFA`,
`RFWE` and `RFOE` are here.

⭐ **And the column shadows cost nothing here**: `WPTR`'s and `CPTR`'s are register-file
locations, not macrocells (§7.2's trick, and the reason a second pointer is affordable).

### 2.4 `v3host` — the backplane, the registers, the palette

| Holds | bits |
|---|---|
| the register decode, `VSTAT` assembly | ~10 |
| `PPEND`, `PS0`–`PS3` — ⚠ **not `PIDX`, which is discrete** | 5 |
| `RDVALID` and the prefetch | ~4 |
| `/WAIT`, `/IRQ`, the `'245` and `'244` controls | ~5 |

It is **~24 cells and ~45 pins**: the backplane is 27 signals on its own
(`signals.md` §2.1) and the palette path's `'163`/`'574`/`'244`/`'573` controls are seven
more. ⭐ **And it needs no `IDB`** — every register it touches is a discrete latch or
counter that loads from the bus itself, so `v3host` only strobes them.

---

## 3. What crosses between parts

| | pins each | |
|---|---|---|
| `IDB[7:0]` — the card's internal data bus | 8 | every part. The `'245` bridges it to the backplane; the register file, the `'573`s and the posted-write latch sit on it |
| `A4`–`A0` + `REGWR` | 6 | every part decodes **its own** register offsets. ⭐ Cheaper than `v3host` emitting 24 individual strobes |
| `VA[16:0]` | 17 | `v3scan` and `v3ptr`, tri-stated |
| the cadence — `SLOTPH[1:0]`, `FETCH`, `SPARE`, `CELLTICK`, `HLOAD`, `VLOAD`, `ROWADV` | 8 | `v3dot` → `v3scan`, `v3ptr` |
| requests / grants — map, copy, span, prefetch | 4 + 4 | in and out of `v3dot` |
| `MODE[1:0]`, `M0` | 3 | `v3dot` → the others |
| `WMODE[1:0]` | 2 | `v3dot` → `v3ptr` |
| status — `SPANBUSY`, `CBUSY`, `PBUSY` | 3 | → `v3host`, for `VSTAT` and `/WAIT` |
| the palette commit — `PCREQ`, `PCGO` | 2 | `v3host` ↔ `v3dot` |
| ⚠ the sprite shape read — `SPRRD`, `SPRROW[2:0]` | 4 | `v3dot` → `v3ptr` |
| ⭐ `HSCROLL[1:0]` | **0** | **duplicated on `v3dot`, not routed** — both parts are on `IDB` and the register bus, so the same store writes both copies: 2 macrocells against 2 pins (`signals.md` §3.4) |

### 3.1 ⚠ The sprite shape is the one cross-part read, and it is a cost plan §7 did not price

plan §7 put the shape in the register file *"so the spare-access arbiter, the map latch
and the fetch cadence are all untouched"* — which is true, and it was the right call
against a VRAM-resident shape. **But the register file is `v3ptr`'s and the sprite is
`v3dot`'s**, so once a scanline `v3dot` has to ask for two bytes: `SPRRD` plus three
bits of row, and the byte comes back on `IDB`.

**Four pins on each part, and the timing is relaxed** — the fetch is once per displayed
sprite row and can sit in horizontal blanking. Recorded because it is a real cost of a
choice made before the partition existed, and because the alternatives are worse: the
shape in macrocells is 128 bits, and the shape in VRAM puts `v3dot` on the arbiter *and*
needs `PB[7:0]` on it, which is eight more pins than this.

---

## 4. What was considered and rejected

| | Why not |
|---|---|
| **Three parts** | `v3host` is only ~40 cells, but merging it into either neighbour passes 128. Its pins are the point, not its logic |
| **`VA` owned by one part** | ~125 macrocells before any control logic, and `MAP`/`MAPQ` is 32 of them |
| **`v3host` emitting a write strobe per register** | 24 pins out of the pin-bound part, against 6 into each of three |
| **`CTRL` on `v3host`** | six bits out instead of three; and `MODE` is consumed at dot rate |
| **The sprite on `v3ptr`** | `SPRA[1:0]` drives LUT `A9..A8` and `SPRHIT` needs the dot counter — both are `v3dot`'s |
| **A fifth part for the copy engine** | ⛔ **it does not place** (plan §13.5) |

---

## 5. Risks, in the order they would bite

1. ⛔ **There is no fifth part.** §0. Any later feature needing one is a card revision.
2. ⚠ **`v3scan` at ~108 estimated cells is the tightest — but its escape is now paid
   for.** A third of it is `MAP`/`MAPQ`, and plan §13.4 offers discrete latches instead.
   §8 measured that the board would not take them *and* four CPLDs — until plan §13.3
   trade 1 returned four packages. **It now places at 40 ICs, 73 %.**
3. ⛔ **`v3dot` NEEDS its escape — it is not optional.** With the sprite's shift
   registers in silicon the fitter answers **`Design does not fit`**; with them in two
   `'165` it is **117/128 cells, 52/64 I/O, 1 cascade**. §8's escape is therefore a
   requirement, and plan §13.3 trade 1 is what paid for it.
4. ⚠ **The `VA` tri-state discipline.** Two parts on seventeen nets, and the rule that
   they never drive together has to be *checked*, not asserted —
   `graphics.md`'s lesson that **a model which ORs its drivers cannot see a bus fight**
   applies directly.
5. ⚠ **Estimates, not fits.** Every number above except 128 and 64.

---

## 7. ⛔ Three parts does not close, and cells are not why

The macrocell total is **~333 against three parts' 384**, so cells were never the wall.
Every three-way merge fails on something else:

| Merge | Fails on |
|---|---|
| `v3host` into `v3ptr` | **pins.** Their external clusters alone are ~39 and ~38; the merge is ~84 against 64 |
| `v3host` into `v3dot` | **pins** — ~68 |
| `v3host` into `v3scan` | **pins** — ~72 |
| `v3scan` into `v3ptr` — the two `VA` drivers, which would also delete the tri-state | ⛔ **cells: ~207 against 128**, and this is the merge §1 exists to refuse |

⭐ **So the tri-stated `VA` bus is not a workaround for a partition; it *is* the
partition.** Undoing it is the one merge that fails by 60 %.

### 7.1 Why a GAL does not rescue it

| | |
|---|---|
| **A GAL cannot be the `VA` mux** | a 17-bit five-source mux is **85 inputs**; a `GAL22V10` has 22 pins |
| **There is no "tri-state problem" for a part to solve** | the discipline is a **one-hot grant**, and §2.1 puts it in one place for exactly that reason. It is ~6 macrocells, not a package |
| ⛔ **And the repository already measured the direction** | `graphics.md` §14.1: *"+1 × `ATF1508AS`, −3 × `GAL22V10` → **−2**"* — `vsup` absorbed `rfa`, `vlen` and `pxsel`, and **a third PLCC-84 REDUCED the package count**. §10.1.2 says why: *half the pin count is the packaging talking to itself* |
| **The ratio is the argument** | a `GAL22V10` is **10 macrocells for ~22 pins**. On a card whose binding constraint is pins, that is the worst available shape — ⭐ whereas a `'574` or a `'165` has **zero pin overhead**, because its pins *are* its data |

---

## 8. ⭐ What does buy headroom — and what the board charges for it

Two moves take logic out of silicon without adding a pin:

| | Buys | Costs |
|---|---|---|
| **`MAP`/`MAPQ` → 4 × `'574`** | **−32 cells** on `v3scan`, the tightest part. ⭐ And the **attribute half never enters a CPLD at all** — `PB` → `MAPQ` → the `ATTR` latch → the LUT — so `v3scan` loses eight output pins and gains eight input pins for the code half: **pin-neutral** | 4 packages |
| **the sprite's two shift registers → 2 × `'165`** | **−16 cells and −2 pins** on `v3dot`. The serial outputs go straight to LUT `A9..A8`, so they never come back | 2 packages |

⛔ **But the board is full, and `npm run check:place`'s packer says so:**

| | ICs | 240 mm |
|---|---|---|
| 4 CPLD, as drawn | 40 | **places, 73 %** |
| 4 CPLD **+ `MAP`/`MAPQ` discrete** | 44 | ⛔ **does not place** |
| 4 CPLD + `MAP`/`MAPQ` + the sprite shifters | 46 | ⛔ **does not place** |
| 5 CPLD | 41 | ⛔ **does not place** |

⭐ **So relief in silicon has to be paid for in packages, and only plan §13.3's trades
have any to give:**

| | ICs | |
|---|---|---|
| ⛔ ~~minus the `'153` mux~~ (trade 3) | — | **withdrawn** — trade 3 is settled the other way, plan §13.3 |
| 4 CPLD + `MAP`/`MAPQ`, **minus the copy latch** (trade 1: it borrows the fetch rank) | 40 | **places, 73 %** |
| 4 CPLD + both discrete moves, minus the copy latch | 42 | **places, 75 %** |

⭐ **BOTH TRADES ARE SETTLED SINCE 2026-09-16, and the coupling is gone.**

**Trade 3** went the other way — the `'153` mux stays, because the tri-state bus must
break before make and §8.2's second rank doubled the drivers after §6.1 costed four of
them. So it yields nothing.

**Trade 1** was never a sharing question: a `'574` has one output enable and the fetch
rank's is committed to the pixel bus. ⭐ **But the latch is not needed at all** — a
byte-granular copy reuses `vread` and the posted-write `'574` — and that returns **four
packages**:

| | ICs | 240 mm |
|---|---|---|
| 4 CPLD, trade 1 taken | **36** | **places, 68 %** |
| … + `MAP`/`MAPQ` discrete — §5 risk 2's escape | **40** | **places, 73 %** |
| … + the sprite's shift registers — §5 risk 3's escape | **42** | **places, 75 %** |

⛔ **AND BOTH ESCAPES TURNED OUT TO BE MANDATORY, not optional.** The fits say so:
`v3dot` with its shifters in silicon is refused outright, and `v3scan` with the map word
in silicon is **63 of 64 I/O** — one pin, the state `graphics.md` flags on `vsup` as a
standing hazard. **So the six discrete packages are part of the design, not a reserve**,
and the board places them: 42 ICs at 75 %.

⭐ **The package budget no longer gates the macrocell budget**, and the partition has
slack it did not have this morning.
What it cost is **4× the copy time** — 30 ms for a 192-row window scroll against 350 ms
without an engine at all.

**Trade 2 is settled too, and the other way**: `HSCROLL` keeps its one-pixel step and its
second fetch rank, because trade 1 already paid for the escapes that rank's four packages
used to be earmarked for. plan §13.3 has the reasoning; ⚠ plan §14 item 13 — **there is no
power budget** — is the only thing that could reopen it.

---

## 6. What to do with it

Steps 1 and 3 are **done** — four term lists, four fits, seven variants between them.

1. ~~Term lists per part~~ — `hardware/gal/video3/v3{dot,scan,ptr,host}.cpld.ts`.
2. ⭐ **A pin census from the term lists, not from this document** —
   `graphics.md` §10.1.2's `npm run census` is the precedent, and it is what turns §3's
   estimate into a measurement. **Still to do, and §6.1 is why it matters.**
3. ~~A fit, one part at a time~~ — and `CLAUDE.md`'s trap held twice: `v3dot_si` answered
   `INTERNAL ERROR` and wrote a convincing report anyway, and a `v3ptr` figure was quoted
   from a `.fit` the next variant had already overwritten.
4. **`reach` and `census` from the first term list, not retrofitted** (plan §15 step 5).
5. ~~Adopt the broadcast~~ — **done 2026-09-16**, all four parts re-fitted, offsets in
   `gal/video3/regmap.ts`.
6. ⛔ **Explain `v3scan_mq`'s 41 cascades, or accept them with a timing number.** It is
   the recommended variant and it is the only figure on the card that got worse.

### 6.1 ⛔ What is fitted is not what is specified — two signals with no cell behind them

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

⭐ **Neither of the two open ones is a fit risk** — `v3ptr` sits at 110 / 128 cells and
44 / 64 I/O, and both additions are small. **Both are correctness gaps**, and the second
bites silently: a span writer whose column never reloads paints the first row and then
walks off down the framebuffer, which is a picture, just not the right one. ⚠ They are
also **one gap, not two** — the reload is a register-file read, so it is blocked on `RFA`.

⛔ **This is exactly what plan §15 step 5's `reach` check is for**, and it is the reason
that step is not optional paperwork: it asks *which signals does the design produce that
nothing reads*, and its mirror — a signal this document names that nothing produces — is
what caught these two by hand. Doing it by hand does not scale to four parts.
