# video3 — the control lines, and what generates them

**DRAFT, 2026-09-16.** The signal census that has to exist before a partition, and
therefore before any term list. [`plan.md`](plan.md) is the design; this is its
plumbing, derived block by block from plan §3–§10 and §13.

> ⚠ **This is the census the partition was derived from, not a fit.** Counts are
> *derived from the parts list* (`hardware/place/parts.ts`, the `video3` alternate). The
> term lists in `hardware/gal/video3/` are the authority wherever they differ, and each
> row below names the part that produces the line where the partition has settled it.
> What this document is for is the question plan §14 item 4 could not answer without it:
> **how many programmable parts, and what goes in each** — and plan §13.5 bounds the answer
> at four PLCC-84s, because a fifth does not place on a 240 mm board.

---

## 1. The control lines, by block

### 1.1 The dot path — plan §3

Everything here runs at 39.72 ns and is the card's tightest timing (§14 item 1).

| | n | Drives | A function of |
|---|---|---|---|
| `SPARE` | 1 | the fetch ranks' clock, both ranks | `v3dot`: `!DP1`, so its rising edge ends the display access, when the group is on the lanes |
| `OEA0..2`, `OEB0..2` | 6 | the ranks' `/OE`, **per chip** — chip 3's pair is strapped to rank B | ⭐ `v3dot`, **constant for a whole line** — `graphics.md` §8.2: chip *c* shows the next group when *c* < `HSCROLL[1:0]`, which is why the rank select is an output enable and not a mux. The second rank is what buys **one-pixel** `HSCROLL` |
| `MUXSEL[1:0]` | 2 | the four `'153` | `v3dot`: the dot phase within the slot **plus `HSCROLL[1:0]`** — zero scroll in character mode |
| `IXCLK` | 1 | the index `'574` | every dot |
| `PIXOE` | 1 | the index latch's `/OE` **and** the LUT's `/OE` | one pin, both halves — §3.1 |
| `ATO7..ATO0` + `ATOE` | 8 + 1 | LUT `A15..A8`, **character mode only** | `v3scan`'s third attribute stage, driving the LUT itself; `ATOE` is `v3dot`'s — §3.1. Tile mode's high byte is zero through pull-downs |
| `SPRA[1:0]` + `SPRAOE` | 2 + 1 | LUT `A9..A8` directly, in bitmap mode | `v3dot`: the `'165`s' serial outputs, re-registered |
| `OCLK` | 1 | the output register, 2 × `'273` | every dot |
| `/OMR` | 1 | the same register's master reset | **blanking** — `graphics.md` §9.2's blank-to-black |

### 1.2 The palette write path — plan §10, `graphics.md` §13.1

| | n | |
|---|---|---|
| `LDPIDXL` | 1 | load the `'163` pair from the internal data bus (`+$0E`) — `v3dot`, off the broadcast |
| `PIDXCE` | 1 | count enable — the auto-increment after `PDATH` (`v3host`) |
| `LDPIDXH` | 1 | the `PIDX`-high `'574`'s clock (`+$0F`) — `v3dot` |
| `PIDXOE` | 1 | **two** `'244` onto the LUT address bus — 16 bits now, not 8 |
| `LDPDATL`, `LDPDATH` | 2 | the two `'573` (`+$10`, `+$11`) — `v3dot`. ⚠ **Not a `'138`**: +$0E/+$0F and +$10/+$11 differ in all of `RA4..RA1` |
| `LUTWE` | 1 | the LUT's `/WE` during a commit |

### 1.3 The framebuffer — plan §4

| | n | |
|---|---|---|
| `VA[16:0]` | 17 | the address, from §1.7's mux — `v3scan`, `v3ptr`, and `v3dot` on `VA[3:0]` (`FBA5..FBA2`) for the sprite's row |
| `/VOE` | 1 | |
| `/VWE` | 1 | `v3ptr`'s `VWE`, for both writers — a span retire and the copy's write |
| `/VLB0` `/VUB0` `/VLB1` `/VUB1` | 4 | `v3lane`: all four for a read (the display fetch, the map word, the sprite row, a byte read), **the lane alone for a write** |
| ⭐ `LOE0..3`, `DIR` | 4 + 1 | the four lane `'245`s between the framebuffer and the internal bus: `/OE` from `v3lane` for the one lane of a prefetch, a copy access or a retire, `DIR` from `v3host`, held for the whole access |
| ⭐ `LANE1:0` | 2 | `v3ptr`: its address mux's two low bits, which the ×16 parts take as byte enables, not address |

### 1.4 The span writer — `graphics.md` §7.4, inherited whole

| | n | |
|---|---|---|
| `WSTBV` | 1 | ⛔ **the posted VRAM write, formed locally** — `VPORT & /RW & E`. It was one signal with the *register* strobe on `video/` and that was a two-directional defect |
| `RETIRE` | 1 | one byte retires: steps `WPTR`, shifts the serialiser, counts `SPANLEN` |
| `VWE` | 1 | ⚠ **not the same as `RETIRE`** — sprite `WMODE` retires without writing — and it is the copy's write strobe as well (§1.3) |
| `SPANEND` | 1 | apply `WADV`, clear `SPANBUSY` |
| `MASKLD`, `MASKSH` | 2 | the mask serialiser |
| `WINC`, `WROWADV` | 2 | `WPTR`'s increment and `WADV 01`'s row step |
| `PWCK`, `PWOE` | 2 | the posted-write data `'574`: `PWCK` (`v3host`) is the CPU's VRAM write **or the copy's read**; `PWOE` (`v3lane`) is a direct-mode span's byte or the copy's write |

### 1.5 The copy engine — plan §6

| | n | |
|---|---|---|
| `CGO`, `CBUSY` | 2 | start and status (`VSTAT` b4) |
| `CRD`, `CWR` | 2 | the read access and the write access — ⭐ **two accesses a byte**, which makes this the heaviest requester in §1.8. `v3host`'s phase `CPH` and `CRDSEL` |
| ⛔ `CLCK`, `CLOE` | 0 | **deleted** — plan §13.3 trade 1: the copy is byte-granular and keeps its byte in flight in the posted-write `'574`. There is no copy-read latch |
| `CCOL`, `CROW` | 2 | the column counter's step and the row step, each +1 — there are no direction bits (plan §6.2) |
| `CWCE`, `CHCE` | 2 | the width and height down-counters |

### 1.6 The sprite — plan §7

| | n | |
|---|---|---|
| `SPRLD` | 1 | load the **four** `'165` **off the four lanes** — 16×16 is four bytes a row — in the sprite row's spare access, slot 8 (`v3dot`) |
| `SPRSH` | 1 | the `'165`s' `CLK INH`: shift every dot from the sprite's first column to the end of the line, inside `ACTIVE` — zeros shift in behind the shape |
| `SPRHIT` | 1 | the sprite has started on this line: a **counter** loaded with `~SPRX`, all-ones on the first dot, held in `SHQ` — plan §7 |

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
| the sprite's row fetch | one spare access a sprite line, slot 8, **bitmap mode only** | 1 — it is `MRQ` in the one mode with no map, so the two never compete |
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
| `RFWE`, `RFOE`, `RFA[4:0]` | 7 | the register file — ⭐ **`RFA[0]` is the span-mask bit** (`v3ptr`), which is what makes per-pixel colour selection free; `RFA[4:1]` are `v3host`'s, `RFOE` is `v3lane`'s |
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
| `HSCROLL`, `VSCROLL` | 19 | the scan counters' loads, `FOE0/1`. ⭐ **Both widths are minimal, not chosen**: `ceil(log2(1024))` and `ceil(log2(512))` — a scroll register has to be able to name any column of the ring, and the ring is the stride, and the stride is the smallest power of two ≥ 640 (`graphics.md` §6.1's no-adder property). ⚠ `HSCROLL[1:0]` is duplicated on `v3dot` — §3.4 |
| scan row/column counters | ~19 | `VA` in bitmap and tile modes |
| cell counters | ~13 | six-bit row, seven-bit column |
| `MAP`, `MAPQ`, `MAPA`, `ATQ`, `ATO` | **40** | ⚠ **the map is a WORD**: `graphics.md` §6.4.9's two stages for the code and three for the attribute (plan §2.5) |
| `WPTR` + its column shadow | 19 + 10 | the span writer, the CPU port, copyrect's destination |
| `CPTR` + its shadow | 19 + 10 | copyrect's source — ⭐ **the shadow is a register-file location**, not macrocells (§7.2's trick) |
| `SPANLEN`, the mask serialiser, the 3-bit mask counter | 19 | the span writer |
| `CWIDTH`, `CHEIGHT`, `CCTRL` | 22 | the copy engine |
| `SPRX`, `SPRY`, `SPRH`, the two position counters, `SHQ`/`SVQ`, the row `SR` | ~46 | the sprite — the shift registers are the four `'165` |
| `TILEBASE`, `MAPBASE` | 8 | the cell address concatenation |
| `PIDX`, `PPEND`, `PS0`–`PS3` | 22 | the palette commit and `PBUSY` |
| `RDVALID` | 1 | the prefetch |
| the four lanes | 32 | the framebuffer's data — the fetch ranks, `v3scan`'s map word (lanes 0 and 1), the sprite `'165`s, and the internal bus through the lane `'245`s |

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
| `A15..A8` | `v3scan`'s `ATO` (character mode); `v3dot`'s `SPRA` on `A9..A8` (bitmap mode); `PIDX`'s high `'244`; pull-downs when none of them drives (tile mode) |

⛔ **A palette commit must take all sixteen at once**, so the turnaround is wider and
there are more ways to get it half-turned. §13.1's discipline has to be *extended*, not
copied: **one enable that stands every other master off**, not three enables that must
agree.

### 3.2 `ATCLK` must run every dot (withdrawn 2026-09-19 with the `ATTR` latch; see history.md)

The rule stands for what replaced it: `v3scan`'s attribute stages are clocked by `CLK25`
every dot and step by holding their inputs, never by a mode-dependent clock.

### 3.3 The copy engine is the heaviest requester, and it is new

Every other spare-access user wants **one** access. Copyrect wants **two** — a read and
a write — for every byte. §1.8's table is the input to plan §14 item 8, and
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
