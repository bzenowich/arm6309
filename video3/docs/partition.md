# video3 — the partition

**DRAFT, 2026-09-16.** Which programmable part holds what, derived from
[`signals.md`](signals.md)'s census. This is plan §15 step 4's first half: a partition
comes before term lists, and how many parts video3 takes is an *output* of it.

> ⭐ **ALL FIVE PARTS ARE FITTED** — the four `ATF1508AS` (`hardware/gal/video3/*.cpld.ts`,
> `gal/cpld/*.fit`) and the `v3lane` `GAL22V10` (`v3lane.jedec.ts`, with a CUPL reference
> and `v3lane.check.ts`). Numbers below that are *not* marked FITTED are still bits of
> state plus an estimate of the combinational logic around them. An `ATF1508AS` in
> PLCC-84 is **128 macrocells and 64 I/O**; a `GAL22V10` is 10 macrocells in a DIP-24.
> ⚠ **No figure from `video/`'s fit applies here** (plan §14 item 4).

### ⭐ The broadcast, adopted 2026-09-16 — and it paid on every part

`v3host` first fitted **full — every I/O pin taken**, with 77 macrocells idle and no next
step in it ([`history.md`](history.md) has the figures). §2.4's estimate was 19 pins light for a reason worth stating plainly — **a
per-register load strobe is a pin, and video3 has 30 of them.**

§3's answer was already in this document: broadcast `RA4..RA0` + `REGWR` and let each part
decode the offsets it cares about. **All four CPLDs are wired that way**,
and the offsets live in one shared table, `hardware/gal/video3/regmap.ts`, read by all four
designs — a private copy per part is exactly the drift this card cannot afford, because a
decode that disagrees with the spec fits perfectly well and answers the wrong address.

⭐ **What each part costs now** — and [`history.md`](history.md) has what each cost before,
which is where the comparison lives, because a superseded utilisation figure in a spec is
a number `check:docs` cannot tell from a live one:

| | cells | I/O | cascades | |
|---|---|---|---|---|
| `v3host` | 58 / 128 | ⛔ **64 / 64** | 0 | the backplane, the decode, the palette commit, the copy's phase machine, the reload walk, `IRQEN`, the lane `DIR` |
| `v3scan` | 112 / 128 | 63 / 64 | 3 | the map word in silicon |
| `v3ptr` | **124 / 128** | 58 / 64 | 3 | Nodes+FB 132 % |
| `v3dot` | **121 / 128** | 63 / 64 | ⚠ **5** | |
| `v3lane` | a `GAL22V10`, 10 of 10 macrocells, 10 inputs | | | the lanes and the internal bus's drivers |
| `v3scan_mq` | 107 / 128 | 46 / 64 | ⚠ **41** | ⚠ a fit of the 2026-09-16 term list, not refitted since — §2.2 |

⚠ **What the broadcast bought is arithmetic, not the fitter's deltas.** The expectation
was ~6 cells of decode each against an unchanged pin count; the same six-cell edit made
`v3scan` 14 cells cheaper and `v3scan_mq` 25 dearer, which is placement heuristics above
80 % utilisation. What it bought for certain is **22 pins on `v3host`** — spent since on
the copy's phase machine, the reload walk, `IRQEN`, `PWCK`, `IRQPEND` and `DIR`.

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
| `ATO7..ATO0` | 8 | the attribute byte **leaving** for the LUT's high address byte — §3's crossing table never listed it |
| `PA7..PA0` | 8 | the pixel bus is **sixteen** bits here, because one ×16 spare access carries both map bytes |

⭐ **And the escape §5 risk 2 is plumbed to buys pins as well as cells**: with the pipeline
in four `'574` on the pixel bus, neither map byte enters this part. **Both are fitted:**

| | cells | I/O | cascades |
|---|---|---|---|
| ⭐ `v3scan`, map word in silicon — **the build** | 112 / 128 (87 %) | 63 / 64 (98 %) | 3 |
| `v3scan_mq`, map word discrete | 107 / 128 (83 %) | 46 / 64 (71 %) | ⚠ **41** |

⭐ **The build keeps the map word in silicon**, and it is the only variant that follows the
design: the attribute takes three stages there (plan §2.5), and the last stage drives the
LUT's high byte itself through `ATOE`, which is what let the `ATTR` `'574` go. ⚠
**`v3scan_mq` has not followed the four-byte cell or the three-stage attribute**, so its
fit prices a pipeline this card no longer has, and its 41 cascades are a placement result
at 83 % rather than a property of either design.

⚠ **63 of 64 I/O is one pin of headroom** — the state `graphics.md` already treats as a
standing hazard on the other card. The pin that makes it 63 and not 64 came from `MRQ`:
`v3scan` makes every map strobe from three cadence pins where it took five (plan §15.4,
defect 15).

---

## 0. The answer, and the thing it runs into

**Four `ATF1508AS` and one `GAL22V10`**, and `plan.md` §13.5 measured that **four
PLCC-84s is the most that places on a 240 mm board** — a fifth does not place even in the
GAL's stead. The ceiling is PLCC-84 area; `v3lane` is a DIP-24.

⛔ **So video3 is exactly at its ceiling.** There is no fifth PLCC-84, which means there
is no room for a feature that needs one — and the partition below has no slack to give a
later change. That is the single most important consequence of this document, and it
should be read before anything is added to plan §0.

| | Cells | I/O | What it is |
|---|---|---|---|
| **`v3dot`** | **121 / 128, FITTED** | 63 / 64, FITTED | the raster, the dot path, the sprite, the arbiter, the palette's load strobes, `WMODE` |
| **`v3scan`** | **112 / 128, FITTED** | 63 / 64, FITTED | the scan and cell addresses, the map word, the attribute onto the LUT |
| **`v3ptr`** | ⭐ **124 / 128, FITTED** | 58 / 64, FITTED | `WPTR`, `CPTR`, the span writer, the copy's counters and decodes, the lane, `VWE`, `WADV` b2's step |
| **`v3host`** | 58 / 128, FITTED | ⛔ **64 / 64, FITTED** | the backplane, the registers, the palette commit, the copy's phase machine, the reload walk |
| **`v3lane`** | `GAL22V10`, 10 of 10, FITTED | 10 inputs | the lane `'245`s' enables, the byte enables, `PWOE`, `RFOE` |

⚠ **`v3host` is pin-bound, not cell-bound** — under half full of macrocells and every pin
taken, because it is the part the backplane lands on. **It is not cells that stop
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

## 2. The parts

### 2.1 `v3dot` — the raster, the dot path, the sprite, the arbiter

| Holds | bits |
|---|---|
| dot counter, line counter | ~20 |
| `M0`, the frame-end family latch | 1 |
| ⭐ **`CTRL`** — `VMODE`, `MODE`, `WMODE`, display enable (b6, the IRQ enable, is `v3host`'s) | 7 |
| `HSCROLL[2:0]`, duplicated — the fine scroll and tile mode's cell phase | 3 |
| the sprite: `SPRX`, `SPRY`, `SPRH`, the two position counters, `SHQ`/`SVQ`, the row `SR`, `SPRA1..0` — the shift registers are four `'165` | ~50 |
| the map request `MRQ` and its window `MWIN`, `ACTIVE`, `DBLHOLD`, `OMR`'s two-register delay | ~6 |
| the spare-access arbiter | ~6 |
| **plus** the dot-path control, sync, blanking, the per-chip rank enables, the palette's four load strobes | ~30 combinational |

**Why `CTRL` is here and not on the host part.** Everything reads it and one thing
writes it. Put it where `MODE` and `VMODE` are consumed at dot rate, and export two
bits of `MODE` rather than importing six.

⭐ **Why the arbiter is here.** It has the cadence, and the cadence is the timing
reference. §3 is the whole of it.

⭐ **Why the LUT's output enables are here.** `PIXOE`, `ATOE`, `SPRAOE` and `PIDXOE` are
the masters of `signals.md` §3.1, and `graphics.md` §13.1's discipline is *one pin doing
both halves of the turnaround so the pair can never be half-turned*. With several masters
that becomes **one part deciding all of them**, never several parts agreeing.

⭐ **Why the sprite's row address is here.** The shape is in VRAM (plan §7) and its row
counter is this part's, so `v3dot` drives `FBA5..FBA2` for the sprite's access and
`v3scan` the rest — no row bits cross — and `SPRLD` loads the `'165`s off the lanes.

### 2.2 `v3scan` — the scan and cell addresses

| Holds | bits |
|---|---|
| `HSCROLL`, `VSCROLL` | 19 |
| the scan row and column counters | 19 |
| the cell row (six bits) and cell column counters | 13 |
| ⚠ **`MAP`, `MAPQ`, `MAPA`, `ATQ`, `ATO`** — the code's two stages and the attribute's three (plan §2.5) | 40 |
| `TILEBASE`, `MAPBASE` | 8 |
| the `VA` mux, scan side — the scan address, the cell concatenation, the map fetch, and the sprite row's base | 17 |

⚠ **The map pipeline is a third of this part**, and `v3scan_mq` is the alternative in
four `'574` (§0's first-fit tables). **The build keeps it in silicon**: the attribute's
last stage is the LUT's high byte, driven through `ATOE`, which is what deleted the
`ATTR` `'574`.

### 2.3 `v3ptr` — the pointers, the span writer, the copy engine

| Holds | bits |
|---|---|
| `WPTR` | 19 |
| `CPTR` | 19 |
| `CWIDTH`, `CHEIGHT`, `CCTRL` | 22 |
| `SPANLEN`, the mask serialiser and its marker bit `MS8`, `WADV` | 19 |
| `SPANBUSY`, `CBUSY`, the span sequencer, the copy's `CEOR`/`CHLAST` | ~10 |
| the `VA` mux, pointer side, and the lane `LANE1:0` — its two low bits | 19 |
| `VWE`, the framebuffer's `/WE` for both writers | 1 |

⭐ **The mask serialiser and the register-file address bit 0 must share a part**, because
`graphics.md` §7.4's trick is that *the serialiser's serial output is the register
file's address bit 0* — which is what makes per-pixel colour selection free. So `RFA0` is
here; `RFA4..RFA1` are `v3host`'s (the decode and the reload walk), and `RFOE` is
`v3lane`'s.

⭐ **And the column shadows cost nothing here**: `WPTR`'s and `CPTR`'s are register-file
locations, not macrocells (§7.2's trick, and the reason a second pointer is affordable).

### 2.4 `v3host` — the backplane, the registers, the palette

| Holds | bits |
|---|---|
| the register decode, `VSTAT` assembly | ~10 |
| `PPEND`, `PS0`–`PS3` — ⚠ **not `PIDX`, which is discrete** | 5 |
| `RDVALID` and the prefetch | ~4 |
| `/WAIT`, `/IRQ`, the `'245` and `'244` controls | ~5 |

It also holds the copy's phase machine, §7.2's reload walk and `RFA4..RFA1`, `IRQEN`, the lane
`'245`s' `DIR`, `PWCK` and `IRQPEND` (plan §14 item 14). The backplane is 27 signals on
its own (`signals.md` §2.1). ⭐ **It takes one bit of `IDB`**, `D6`, for `IRQEN` — every
other register it touches is a discrete latch or counter that loads from the bus itself,
so `v3host` only strobes them.

### 2.5 `v3lane` — the byte lanes and the internal bus's drivers

A `GAL22V10`, purely combinational, ten inputs (`LANE1:0`, `CRDSEL`, the three grants,
`WM1:0`, `/VWE`, `WSTBV`) and all ten macrocells: the four lane `'245`s' `/OE` (this
access's lane, during its grant), the four byte enables (all four for a read, the lane
alone for a write), `PWOE` (a direct-mode span's byte or the copy's write) and `RFOE` (the
register file, unless a lane read, the `'574` or a posted CPU write has the bus).

⭐ **It is §7.1's worst shape and it earns its place anyway**, because it relieves no
CPLD: every output is an enable of a discrete part and every input is already on the
board, so its pins are its data the way a `'574`'s are. No CPLD had ten pins to give it
— `v3host` is full — and the logic is what the board lacked, not what a part could not
hold (plan §15.4, defect 24).

---

## 3. What crosses between parts

| | pins each | |
|---|---|---|
| `IDB[7:0]` — the card's internal data bus | 8 | `v3dot`, `v3scan` and `v3ptr`; `v3host` takes `D6` alone. The host `'245` bridges it to the backplane and the four lane `'245`s to the framebuffer; the register file, the `'573`s, `vread`'s input and the posted-write `'574` sit on it |
| `A4`–`A0` + `REGWR` | 6 | every part decodes **its own** register offsets. ⭐ Cheaper than `v3host` emitting 24 individual strobes |
| `VA[16:0]` | 17 | `v3scan` and `v3ptr`, tri-stated |
| the cadence — `DP1:0`, `SPARE`, `MRQ`, `HLOAD`, `ROWADV`, `VBLANK` | 7 | `v3dot` → `v3scan`, `v3ptr`, `v3host`. ⭐ Each receiver makes its own ticks from the dot phase and `MRQ` — `v3scan`'s `FETCH`, `GMAP`, `MAPLD` and `MCADV` are terms, not pins |
| requests / grants — map, copy, span, prefetch | 4 + 4 | in and out of `v3dot`; the map's request is `v3dot`'s own `MRQ` |
| `MODE[1:0]` | 2 | `v3dot` → the others |
| `WMODE[1:0]` | 2 | `v3dot` → `v3ptr` and `v3lane`: `CTRL` b5..4 as two **combinational** pins `WM0`/`WM1` |
| ⭐ the lane — `LANE1:0`, `CRDSEL`, the three grants, `WM1:0`, `VWE`, `WSTBV` | 10 | → `v3lane`, whose ten outputs are the lane `'245`s', the byte enables, `PWOE` and `RFOE` |
| status — `SPANBUSY`, `CBUSY`, `PBUSY` | 3 | → `v3host`, for `VSTAT` and `/WAIT` |
| the palette commit — `PCREQ`, `PCGO` | 2 | `v3host` ↔ `v3dot` |
| ⭐ `HSCROLL[2:0]` | **0** | **duplicated on `v3dot`, not routed** — both parts are on `IDB` and the register bus, so the same store writes both copies: 3 macrocells against 3 pins (`signals.md` §3.4) |

⭐ **Registers driving pins place worse than combinational copies of them, on these
parts** — measured four times. `v3dot`'s `WMODE` as the `CTRL` registers on two pins was
refused, and as two combinational copies it fits; a `WMODE` copy held on `v3ptr` was
refused under two names once `v3ptr` needed those cells; exporting `v3ptr`'s four column
counter bits for `v3lane` to mux was refused, where two mux cells of the same shape as
`FBA`'s fit; and exporting two registers from `v3dot` was refused. The lane mux's two
cells were paid for by deleting `RSPN` (`SPANBUSY` under a second name) and folding the
mask counter `MK2..0` into one marker bit (plan §15.4, defect 29).

### 3.1 The sprite shape read (withdrawn 2026-09-19; see history.md)

The shape is in VRAM (plan §7) and nothing crosses a part to read it.

---

## 4. What was considered and rejected

| | Why not |
|---|---|
| **Three parts** | `v3host` is only ~40 cells, but merging it into either neighbour passes 128. Its pins are the point, not its logic |
| **`VA` owned by one part** | ~125 macrocells before any control logic, and `MAP`/`MAPQ` is 32 of them |
| **`v3host` emitting a write strobe per register** | 24 pins out of the pin-bound part, against 6 into each of three |
| **`CTRL` on `v3host`** | six bits out instead of three; and `MODE` is consumed at dot rate |
| **The sprite on `v3ptr`** | `SPRA[1:0]` drives LUT `A9..A8` and `SPRHIT` needs the dot counter — both are `v3dot`'s |
| **The sprite shape in the register file** | `RFA4..RFA0` reaches 32 bytes and the shape is 64; reading it needed a sixth and seventh address bit, an arbiter against the span writer's colour reads and four `'165` load strobes — about fifteen pins. ⭐ In VRAM it is one spare access bitmap mode has free, and the `'165`s load off the lanes, so it needs neither `v3dot` on `PB` nor anything on the internal bus |
| **A fifth PLCC-84 for the copy engine** | ⛔ **it does not place** (plan §13.5) |

---

## 5. Risks, in the order they would bite

1. ⛔ **There is no fifth PLCC-84.** §0. Any later feature needing one is a card revision.
2. ⚠ **`v3scan` holds the map pipeline in silicon, and its escape is not taken.** It fits
   at 112/128 cells and 63/64 I/O with the attribute's three stages in it; the discrete
   variant (§0) has not followed the design, and the board's packages went to the lane
   transceivers (plan §13.5).
3. ⛔ **`v3dot` NEEDS its escape — it is not optional.** With the sprite's shift
   registers in silicon the fitter answers **`Design does not fit`**; with them in four
   `'165`s it is **121/128 cells, 63/64 I/O, 5 cascades**. §8's escape is therefore a
   requirement, and plan §13.3 trade 1 is what paid for it.
4. ⚠ **The `VA` tri-state discipline.** Three parts on the address bus now — `v3scan`,
   `v3ptr`, and `v3dot` on `FBA5..FBA2` for the sprite's row — and the rule that they never
   drive together has to be *checked*, not asserted: `graphics.md`'s lesson that **a model
   which ORs its drivers cannot see a bus fight** applies directly. ⭐ `video3_card.v`
   resolves the bus and `v3card_tb` counts fights every dot, as it does on the internal
   bus, the lanes and the LUT address.
5. ⚠ **Estimates, not fits.** Every number above except 128 and 64 and those marked
   FITTED.

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
| ⭐ **`v3lane` is not a counter-example** | it relieves no CPLD: its ten outputs are enables of discrete parts and its ten inputs are already on the board, so its pins are its data the way a `'574`'s are (§2.5) |

---

## 8. ⭐ What does buy headroom — and what the board charges for it

Two moves take logic out of silicon without adding a pin:

| | Buys | Costs | |
|---|---|---|---|
| **`MAP`/`MAPQ` → 4 × `'574`** | cells on `v3scan`, and neither map byte enters it | 4 packages | ⚠ **not taken** — §5 risk 2 |
| **the sprite's shift registers → `'165`** | **−32 cells and −2 pins** on `v3dot`. The serial outputs come back to `v3dot` as `SQ0`/`SQ1` and are re-registered onto LUT `A9..A8` | **4 packages** — two cascaded a plane, because a 16×16 row is 32 bits | ⭐ **taken, and mandatory**: without them `v3dot` does not fit |

⛔ **The board is full, and `npm run check:place`'s packer says so.** plan §13.5 has the
measurements: the card as built is **45 ICs — four `ATF1508AS`, `v3lane` and 40 discrete
— and places on 24 cm at 78 %**; a fifth PLCC-84 does not place, even in `v3lane`'s
stead. Relief in silicon has to be paid for in packages, and only plan §13.3's trades had
any to give:

- **Trade 3** went the other way — the `'153` mux stays, because the tri-state bus must
  break before make and §8.2's second rank doubled the drivers after §6.1 costed four of
  them. So it yields nothing.
- **Trade 1** was never a sharing question: a `'574` has one output enable and the fetch
  rank's is committed to the pixel bus. ⭐ **But the latch is not needed at all** — a
  byte-granular copy keeps its byte in flight in the posted-write `'574` — and that
  returns **four packages**, which the sprite's `'165`s take.
- **Trade 2** is settled the other way too: `HSCROLL` keeps its one-pixel step and its
  second fetch rank. plan §13.3 has the reasoning; ⚠ plan §14 item 13 — **there is no
  power budget** — is the only thing that could reopen it.

⭐ **And the `ATTR` `'574` is gone** (plan §3), which with the `MAP`/`MAPQ` escape not
taken is what let the four lane `'245`s and `v3lane` onto the board. What trade 1 cost is
**4× the copy time** — 30 ms for a 192-row window scroll against 350 ms without an engine
at all.

---

## 6. What to do with it

Steps 1, 3 and 5 are **done** — five term lists, five fits, and the variants between them.

1. ✅ **Term lists per part** — `hardware/gal/video3/v3{dot,scan,ptr,host}.cpld.ts` and
   `v3lane.jedec.ts`.
2. ⭐ **A pin census from the term lists, not from this document** —
   `graphics.md` §10.1.2's `npm run census` is the precedent, and it is what turns §3's
   estimate into a measurement. **Still to do, and §6.1 is why it matters.**
   `v3portmap.ts` already generates `video3_card.v`'s nets from the term lists, which is
   half of one.
3. ✅ **A fit, one part at a time** — and `CLAUDE.md`'s trap held twice: `v3dot_si`
   answered `INTERNAL ERROR` and wrote a convincing report anyway, and a `v3ptr` figure was
   quoted from a `.fit` the next variant had already overwritten.
4. **`reach` and `census` from the first term list, not retrofitted** (plan §15 step 5).
   ⭐ `check:reach` covers video3, with `video3_card.v` as its board and `v3lane` a part.
5. ✅ **Adopt the broadcast** — all four CPLDs decode it, offsets in
   `gal/video3/regmap.ts`.
6. ⚠ **`v3scan_mq`'s 41 cascades are unexplained**, and moot unless it is refitted: the
   build is the silicon variant (§5 risk 2).

### 6.1 What is fitted is not what is specified — two signals with no cell behind them (closed 2026-09-19; see history.md)

Both are built (plan §14 item 14): the register file's address is `RFA4..RFA1` from
`v3host`'s reload walk and `RFA0` from `v3ptr`, and `WPTR`'s end-of-row reload is that
walk's `RP1`/`RP2`. The third finding of the same shape, the multi-byte loads, was fixed
on 2026-09-16 and is in §0.

⛔ **The lesson stands, and it is why plan §15 step 5 is not optional paperwork**:
`check:reach` asks *which signals does the design produce that nothing reads*, and its
mirror — a signal a document names that nothing produces — is what caught these two by
hand. ⚠ **Neither direction sees a line only a discrete chip needs — unless the card has a
board**: `video3_card.v` is video3's board for `check:reach`, and plan §14 item 18 has the
seven lines it found and what produces each.
