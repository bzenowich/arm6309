# video3 — the control lines, and what generates them

**DRAFT, 2026-09-16.** The signal census that has to exist before a partition, and
therefore before any term list. [`plan.md`](plan.md) is the design; this is its
plumbing, derived block by block from plan §3–§10 and §13.

> ⚠ **Nothing here is fitted.** Counts are *derived from the parts list*
> (`hardware/place/parts.ts`, the `video3` alternate), not from a fitter. What this
> document is for is the question plan §14 item 4 cannot answer without it: **how many
> programmable parts, and what goes in each** — and §13.5 bounds the answer at four,
> because a fifth PLCC-84 does not place on a 240 mm board.

---

## 1. The control lines, by block

### 1.1 The dot path — plan §3

Everything here runs at 39.72 ns and is the card's tightest timing (§14 item 1).

| | n | Drives | A function of |
|---|---|---|---|
| `FCLK0`, `FCLK1` | 2 | the two fetch-latch ranks, 4 × `'574` each | the slot phase, and which rank this line's `HSCROLL[1:0]` wants |
| `FOE0`, `FOE1` | 2 | the ranks' `/OE` | ⭐ **constant for a whole line** — `graphics.md` §8.2: `c < HSCROLL[1:0]` is why the rank select is an output enable and not a mux. The second rank is what buys **one-pixel** `HSCROLL` |
| `MUXSEL[1:0]` | 2 | the four `'153` | the dot phase within the slot |
| `IXCLK` | 1 | the index `'574` | every dot |
| `ATCLK` | 1 | the `ATTR` `'574` | every dot — see §3.2 for **why not per cell** |
| `PIXOE` | 1 | the index latch's `/OE` **and** the LUT's `/OE` | one pin, both halves — §3.1 |
| `ATOE` | 1 | the `ATTR` latch's `/OE` onto LUT `A15..A8` | §3.1 |
| `SPRA[1:0]` | 2 | LUT `A9..A8` directly, in bitmap mode | the sprite serialiser — plan §13.4's open choice |
| `OCLK` | 1 | the output register, 2 × `'273` | every dot |
| `/OMR` | 1 | the same register's master reset | **blanking** — `graphics.md` §9.2's blank-to-black |

### 1.2 The palette write path — plan §10, `graphics.md` §13.1

| | n | |
|---|---|---|
| `PIDXLD` | 1 | load the `'163` pair from the internal data bus (`+$0E`) |
| `PIDXCE` | 1 | count enable — the auto-increment after `PDATH` |
| `PIDXHCK` | 1 | the `PIDX`-high `'574`'s clock (`+$0F`) |
| `PIDXOE` | 1 | **two** `'244` onto the LUT address bus — 16 bits now, not 8 |
| `PDLLE`, `PDHLE` | 2 | the two `'573` |
| `LUTWE` | 1 | the LUT's `/WE` during a commit |

### 1.3 The framebuffer — plan §4

| | n | |
|---|---|---|
| `VA[16:0]` | 17 | the address, from §1.7's mux |
| `/VOE` | 1 | |
| `/VWE` | 1 | |
| `/VLB0` `/VUB0` `/VLB1` `/VUB1` | 4 | ⭐ **the byte enables do three jobs here**: §7.4's broadcast write, §6's four-byte copy, and §2.2's map **word**. `video/` has only the first |

### 1.4 The span writer — `graphics.md` §7.4, inherited whole

| | n | |
|---|---|---|
| `WSTBV` | 1 | ⛔ **the posted VRAM write, formed locally** — `VPORT & /RW & E`. It was one signal with the *register* strobe on `video/` and that was a two-directional defect |
| `RETIRE` | 1 | one byte retires: steps `WPTR`, shifts the serialiser, counts `SPANLEN` |
| `WEN` | 1 | ⚠ **not the same as `RETIRE`** — sprite `WMODE` retires without writing |
| `SPANEND` | 1 | apply `WADV`, clear `SPANBUSY` |
| `MASKLD`, `MASKSH` | 2 | the mask serialiser |
| `WINC`, `WROWADV` | 2 | `WPTR`'s increment and `WADV 01`'s row step |
| `PWCK`, `PWOE` | 2 | the posted-write data `'574` |

### 1.5 The copy engine — plan §6

| | n | |
|---|---|---|
| `CGO`, `CBUSY` | 2 | start and status (`VSTAT` b4) |
| `CRD`, `CWR` | 2 | the read access and the write access — ⭐ **two accesses a group**, which makes this the heaviest requester in §1.8 |
| ⛔ ~~`CLCK`, `CLOE`~~ | 0 | **deleted** — plan §13.3 trade 1: the copy is byte-granular and reuses `vread` and the posted-write `'574`. There is no copy-read latch |
| `CCOL`, `CROW` | 2 | the shared column counter's step and the row step, each ±1 by `CCTRL` b1/b2 |
| `CWCE`, `CHCE` | 2 | the width and height down-counters |

### 1.6 The sprite — plan §7

| | n | |
|---|---|---|
| `SPRLD` | 1 | load the two 8-bit shift registers from the register file, once per displayed sprite row |
| `SPRSH` | 1 | shift, once per dot inside the sprite's eight columns |
| `SPRHIT` | 1 | the sprite covers this dot: an **equality** against the column counter, then an eight-state window counter |

### 1.7 The address mux — plan §14 item 3

| | n | |
|---|---|---|
| `SRCSEL` | 5 | one per source: the bitmap scan address, the cell/tile concatenation, `WPTR`, the map fetch, and `CPTR` |

⛔ **Five sources is the budget, not a finding.** An ATF15xx macrocell holds about five
before it cascades (`graphics.md` §6.4.1, a property of the family), so a sixth source
is where cascading starts. Nothing here is fitted.

### 1.8 The arbiter — ⭐ the hard part

`check:video3` asserts that a 158.9 ns slot fits **two** 72 ns accesses and not three,
so there is **one spare access a slot**. These want it:

| Requester | Wants | Priority |
|---|---|---|
| the display fetch | the slot's *first* access, always | **not arbitrated** — it is the picture |
| the map **word** (character, tile) | one spare access a cell | 1 — refuse it and the cell shows a stale code, every frame |
| the sprite's row fetch | one *register-file* read a sprite row | — ⭐ **not on this bus at all**, which is why plan §7 put the shape in the register file |
| the CPU's read prefetch | one spare access after an invalidation | 2 |
| **the copy engine** | **two** spare accesses a **byte** — a read and a write | 3 |
| the span writer | one spare access a retire | 4 |

⛔ **This is plan §14 item 8 and it is the largest unanswered thing about the card.**
The functional model cannot see it — it renders a line at a time — so only Verilator
can. `graphics.md` §6.4.2 already halves the span writer's slots in cell mode *before*
video3 adds a copy engine.

### 1.9 Host, status and sync

| | n | |
|---|---|---|
| `/WAIT` | 1 | open-drain, and the OE idiom spends the macrocell's one OE term |
| `/IRQ` | 1 | open-drain, VBL |
| `VSTATOE` | 1 | the `'244` that puts live macrocells on `D0`–`D7` |
| `RDCK`, `RDOE`, `RDVALID` | 3 | the `vread` `'574` and its prefetch validity |
| `RFWE`, `RFOE`, `RFA[n]` | ~7 | the register file — ⭐ **`RFA[0]` is the span-mask bit**, which is what makes per-pixel colour selection free |
| `RDBKOE`, `RDBKDIR` | 2 | the read-back `'245` |
| `HSYNC`, `VSYNC`, `BLANK` | 3 | the connector, **and the backplane** — `graphics.md` §12.2 needs both syncs at a slot pin for the CPU module's line compare |

**Roughly 90 control lines**, of which ~17 are the framebuffer address and ~7 the
register file's.

---

## 2. The inputs

### 2.1 From the backplane — the pins the card must have

| | n | Used by |
|---|---|---|
| `CLK25` | 1 | everything. ⭐ **The card is clock-slaved** (`graphics.md` §5.3) and should stay so — there is no oscillator on it |
| `E`, `Q`, `R/W` | 3 | `WSTBV`, `/WAIT`, the read path's edges. ⚠ A 6809E samples on E's **fall** |
| `/IOSEL` | 1 | the `$FF00`–`$FF7F` window strobe |
| `A6`–`A0` | 7 | the register offset. ⚠ **A6 is not implied by the strobe** since the window widened — every card decodes `A0`–`A6` |
| `A20`, `A19` | 2 | `VRAMSEL` = `A19 · /A20 · /IOSEL` |
| `D7`–`D0` | 8 | bidirectional |
| `/RESET` | 1 | `CTRL := 0` — display off, bitmap, direct writes, no interrupt |
| **out:** `/WAIT`, `/IRQ`, `HSYNC`, `VSYNC` | 4 | |

**~27 backplane signals.** ⚠ Note what is **absent**: no `PA[18:2]`. `graphics.md`
§3.1.1 and §19 item 44 — every CPU VRAM access is at `WPTR`, so the physical address
selects the *window* and nothing else, and `video/` once listed three address latches
that no design ever clocked. **video3 must not re-add them.**

### 2.2 Internal state — what the control lines are functions of

| | bits | Feeds |
|---|---|---|
| dot/slot counter | ~10 | `MUXSEL`, `FCLK`, `SPRHIT`, the fetch cadence, `HSYNC`, `BLANK` |
| line counter | ~10 | `VSYNC`, `BLANK`, `VBL`, the row counter's load |
| **`M0`** | 1 | ⭐ the **latched** `VMODE[0]` — the family, taken at frame end, or a mid-frame write costs 1.5 s of lost sync |
| `CTRL` | 8 | `VMODE`, `MODE`, `WMODE`, IRQ enable, display enable — **`MODE` reaches almost everything** |
| `HSCROLL`, `VSCROLL` | 19 | the scan counters' loads, `FOE0/1` |
| scan row/column counters | ~19 | `VA` in bitmap and tile modes |
| cell counters | ~13 | six-bit row, seven-bit column |
| `MAP` / `MAPQ` | **32** | ⚠ **the map is a WORD now**, so `graphics.md` §6.4.9's two-stage pipeline doubles |
| `WPTR` + its column shadow | 19 + 10 | the span writer, the CPU port, copyrect's destination |
| `CPTR` + its shadow | 19 + 10 | copyrect's source — ⭐ **the shadow is a register-file location**, not macrocells (§7.2's trick) |
| `SPANLEN`, the mask serialiser, the 3-bit mask counter | 19 | the span writer |
| `CWIDTH`, `CHEIGHT`, `CCTRL` | 22 | the copy engine |
| `SPRX`, `SPRY`, `SPRH`, two shift registers | 36 | the sprite |
| `TILEBASE`, `MAPBASE` | 8 | the cell address concatenation |
| `PIDX`, `PPEND`, `PS0`–`PS3` | 22 | the palette commit and `PBUSY` |
| `RDVALID` | 1 | the prefetch |
| `PB[7:0]` | 8 | the pixel bus — the map latch, the copy latch and `vread` all read it |

**~280 bits of state.** ⚠ That number is the reason §14 item 4 is open: `video/` fits
three `ATF1508AS` at 128 macrocells each, and video3 deletes a display list from that
budget while adding a 32-bit map pipeline, a second 19-bit pointer, four counters and a
sprite.

---

## 3. ⭐ Three things the census makes visible

### 3.1 The LUT address bus now has masters on **both** halves

`graphics.md` §13.1 has two masters on eight lines, and one pin — `PIXOE` — doing both
halves of the turnaround *"so the pair can never be half-turned and the two buses can
never have two masters"*. video3 has:

| Half | Masters |
|---|---|
| `A7..A0` | the index latch; `PIDX`'s low `'244` |
| `A15..A8` | the `ATTR` latch; the sprite's two lines; `PIDX`'s high `'244` |

⛔ **A palette commit must take all sixteen at once**, so the turnaround is wider and
there are more ways to get it half-turned. §13.1's discipline has to be *extended*, not
copied: **one enable that stands every other master off**, not three enables that must
agree.

### 3.2 `ATCLK` must run every dot, even in character mode

The tempting saving is to clock the `ATTR` latch once a **cell**, since plan §3's
timing argument is that the attribute is constant across one. ⛔ **Do not**: that makes
a clock line mode-dependent, which is a mux on a clock, and clock muxes glitch.

⭐ **Clock it every dot and hold its *input* constant instead.** The timing argument is
about when the LUT's address settles, not about how often the latch is clocked — a
latch reloaded with the same value is as stable as one not clocked at all, and the
control line stays a constant.

### 3.3 The copy engine is the heaviest requester, and it is new

Every other spare-access user wants **one** access. Copyrect wants **two** — a read and
a write — for every four-byte group. §1.8's table is the input to plan §14 item 8, and
the thing to check first is not whether the engine is fast but **whether the span
writer and the CPU prefetch still get slots while it runs.**

---

## 4. What this is for

1. **A partition.** Group §1's lines by what state they read: the dot path and the
   sync counters barely touch the host side; the span writer, the copy engine and the
   register file are one cluster; the address mux is the thing that forces a choice.
2. **A pin budget per part**, which is what actually decides the count — `graphics.md`
   §10.1.2 found **52 % of a ten-GAL build's pins were the packaging talking to
   itself**, and that is the number a partition is trying to minimise.
3. **Then term lists, then a fit** — plan §15 step 4, and only then does "three parts
   or four" have an answer.
