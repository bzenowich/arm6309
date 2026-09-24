# Proportional antialiased text — where the time goes, and what the copy engine can take

⚠ **A DESIGN STUDY, NOT A DESIGN.** Nothing here is built and nothing here is
proposed for a spec yet. Asked 2026-09-21: *how do we make antialiased
proportional text fast, what did the early Macintosh and GEOS do, and how should
the copyrect protocol be packed?* Figures marked **measured** come from
`hardware/video3/docs/demo-report.md` §16, `software/desk/docs/boot-and-desktop.md` §5 item 8 and
`hardware/video3/docs/keyed-copy.md` §7.1; figures marked **estimated** are cycle counts
read off the source at E = 2.0979 MHz, and §9 says which measurement settles
them. `hardware/video3/docs/keyed-copy.md` §3.2 and `software/desk/docs/boot-and-desktop.md` §5 item 8
are the two documents this one argues with.

---

## 0. The short answer, and it contradicts the question

**The packing is not the problem.** For the case that matters — a glyph out of a
strike — the present register map already needs only **six bytes** and **no
shifting at all**, because the card's copy address is a *concatenation* and not a
sum: the source column's low byte **is** `CPTR0`. Packing six unpacked bytes into
seven packed ones would cost shifts to save nothing.

⭐ **But the question's number is right for the wrong reason.** Seven bytes is
exactly the target — not because seven bits-worth of fields fit in seven bytes,
but because **seven *consecutive* bytes is what an HD6309 writes in three
instructions** (`STQ`, `STW`, `STA`) out of an image it never has to build. The
lever is the **order** of the registers in the 32-byte window, not the width of
the fields in them. §5.4.

⚠ **And since 2026-09-21 that is measured rather than argued** — the host emulator
runs 6309 code (`hardware/cpu/docs/6309.md` §4.1). It is worth **1.11×, not the 1.9× §5.4
estimated**, and ⛔ **the same instructions on the map as it stands are 0.94× —
a regression.** §8 has the table.

The three findings, in the order they are worth money:

| | worth |
|---|---|
| ⛔ **§2 — a per-glyph blit is FASTER than the software path, not slower.** `boot-and-desktop.md` §5 item 8 rules it out against a baseline that is not the software path | ⭐ **measured at 6.7×** (§6.1). The *direction* is what item 8 got wrong, and it is the whole of the rest of this document |
| ⭐ **§4 — the Mac's strike maps onto copyrect with ZERO shifting**, because this card is chunky 8 bpp. The shift was both the Mac's and GEOS's inner loop | ⛔ **BUILT AND MEASURED 2026-09-22: 222.89 ms → 33.42 ms, 6.7×** — not the 78× estimated. §6.1 |
| ⛔ **§6 — `/WAIT` forbids overlapping the CPU's set-up with the engine's run**, and the two cost the same to within 1 %. So the ceiling on *all* protocol work is exactly 2× | ⛔ **RETRACTED 2026-09-22 by §6.1.** A glyph measures **769 µs** and the engine is **29 µs of it**; the two do not cost the same, and the silicon this priced buys under 4 %. **The per-copy call is the cost**, and §5 never counted it |

⭐ And **the window-title problem dissolved in the asking** — see §4.4. The user's
suggestion (gradient only above and below the text, a flat band behind it) turns
the one ramp with no flat paper into one with a flat paper, which removes the
only case that needed the colour key, which removes the palette renumber that
`boot-and-desktop.md` §5 item 8 names as the blocker. **The strike path needs no
new silicon and no palette change.**

---

## 1. What the machine renders today

### 1.1 The font is already proportional and already antialiased

From the built blob (`software/archive/nitros9-video/build3/tbox.bin`, parsed
2026-09-21 — these are **measured**, not estimated):

| | regular | bold |
|---|---|---|
| source | Noto Sans 12 px, rendered by `mktbox.py:134-167` | Noto Sans Bold 12 |
| glyphs | **95**, codes 32–126 (out of range → `'?'`) | 95 |
| height / ascent | **17 / 13 rows** | 17 / 13 |
| widths | **3–11 px, mean 6.39** | 3–12 px, mean 6.79 |
| **total width of all 95** | ⭐ **607 px** | ⭐ **645 px** |
| storage | **2 bits a pixel**, MSB first, `(w+3)//4` bytes a row | " |
| the location table | **95 × 3 bytes: `[width][2-byte offset]`** | " |

⭐ **THE MAC'S `locTable` ALREADY EXISTS**, and so does its `owTable`: the
3-byte directory entry is a width and an offset, `Glyph` (`tbox.asm:516`) reads
it and `TextW` (`:534`) sums the widths. Nothing has to be added to the font
format to build a strike — §4.

### 1.2 A "ramp" is three palette entries, and it bakes the background in

`mktbox.py:40-52`: palette entries **32–55 are eight text ramps, three entries
each** — `lerp(paper, ink, ⅓)`, `lerp(paper, ink, ⅔)`, `ink`. A glyph pixel is
quantised to **four levels**: level 0 is the *paper*, levels 1–3 are `RAMP+0`,
`+1`, `+2` (`tbox.asm:554`, `Lev` at `:702`).

⛔ **So the antialiasing is not a blend performed at draw time — it is a blend
performed at ROM-build time against a specific background.** That is the whole
of the transparency difficulty, and it is not a limitation of the copy engine:
an 8 bpp indexed card cannot blend, so an antialiased fringe must be *baked*,
and a baked fringe is only correct over the paper it was baked for. Any scheme
that draws antialiased text over an arbitrary background on this machine is
choosing which wrong answer to give.

### 1.3 What it costs, measured

| | |
|---|---|
| a `Text` call that draws nothing (the floor) | **13.58 ms** |
| each further character | **11.52 ms** (a slope) → **5.47 ms** after the 2026-09-18 work |
| a 40-character line, as shipped | ⛔ **218.64 ms** (was 479.03) |
| a 7-character file name, opaque, in `desk` | **71.4 ms** |
| `DrawFiles` — the file manager's whole repaint | ⛔ **2,956.8 ms** |
| of which, actual `VDATA` pixels | ⭐ **6.8 ms — 1.4 %** |

⭐ **The path is CPU-bound by ~70×.** `demo-report.md` §16.1 splits it: call
floor 2 %, escape parsing 8 %, composition (`GRow` + fill + run scan) **48 %**,
the card's half **41 %** — of which the pixels are 1.4 % and the rest is ~395
`RowPut` calls at 2.1 bytes a call.

⚠ **Two software wins are already taken** and are in that 218.64: `F.Opaq`
(one run a row instead of ~395) and `TB.NTab` (a nibble is two destination bytes
in one `ldd`/`std`). This document is about what is left.

---

## 2. ⛔ THE CORRECTION — a per-glyph blit is FASTER, not slower (measured: 6.7×)

`software/desk/docs/boot-and-desktop.md` §5 item 8 (2026-09-21) says:

> ⛔ **And the arithmetic still says a per-glyph blit would be SLOWER than
> `F.Opaq`.** A copy costs ~87 µs of setup whatever its size (`monster`'s
> measurement), so a 40-character title as 40 glyph copies is ~3.5 ms — against
> one opaque line.

**The arithmetic is right and the baseline is not.** "One opaque line" is not
3.5 ms and is not 87 µs. It is the thing the same section measures four
paragraphs above: a *seven*-character name costs **71.4 ms** opaque, and
`demo-report.md` §16 puts a forty-character line at **218.64 ms**.

| a 40-character line | |
|---|---|
| `F.Opaq`, as shipped — **measured** | **218.64 ms** |
| 40 glyph copies at `monster`'s 87 µs — **estimated** | ⭐ **3.5 ms** |
| | ⭐ **62×** |
| ⭐ **40 glyph copies, BUILT AND MEASURED 2026-09-22** (§6.1) | ⛔ **33.42 ms — 6.7×** |

⛔ **And the estimate's own error is the finding that outlived it.** A glyph
copy measures **769 µs**, not `monster`'s 87 — **nine times** — because
`monster` owns the card and this path goes toolbox → `TVCALL` → `TbVec` →
`RowCopy`. §6.1 and §7 are where that leads.

⚠ **The sentence is defensible under one reading** — that a *string* cache (one
copy of a pre-composed line, `keyed-copy.md` §3.2) beats a *glyph* cache, which
is true: 3.5 ms against ~0.1 ms. ⛔ **But as written it reads as "glyph copies
lose to software text", and that is wrong — measured, by 6.7×.** The two
schemes are not alternatives, either; §4.5 uses both, because a string cache
only pays for a string drawn more than once and a strike pays the first time.

⚠ **`keyed-copy.md` §3.2's retraction is the same shape and is also worth
re-reading**: it killed the glyph cache on the number **5.81 ms a copy**, which
§7.1 of that same document later showed was a forked command's wall clock —
**2,143 µs** through `SS.Copy`, **344 µs** through `SS.CopyN`, and ~87 µs in a
process that owns the card. The retraction was never carried back into §3.2's
conclusion. At 87 µs the "dead" design is 62× ahead.

⛔ **And this document is a subtraction too, so §9 says what to measure before
any of it is built.** That is the discipline `boot-and-desktop.md` §5 item 8 sets
out and it applies here with more force, not less.

---

## 3. What the Macintosh and GEOS actually did

Both arrived at the same data structure independently, and both spent their
inner loop on the one thing this card does not need.

### 3.1 The Macintosh: the strike, the `locTable`, and the `owTable`

A `FONT`/`NFNT` resource is **one bitmap** — every glyph of one face at one size
packed side by side on a common baseline, `rowWords` wide and `fRectHeight`
tall, with no gaps. Beside it:

- **`locTable`** — one 16-bit entry a glyph, the glyph's horizontal **bit**
  offset in that strike. Glyph *i*'s width in the strike is
  `locTable[i+1] − locTable[i]`, so **one table gives both the source X and the
  width, and adjacent entries give both of them for free**.
- **`owTable`** — an offset/width pair a glyph: the left side bearing and the
  **advance**, which is what makes the spacing proportional and is *not* the same
  as the strike width.

`DrawText` walks the string, blits a column range out of the strike for each
character, and advances the pen by `owTable`'s width. ⭐ **Every glyph in a
string has the same source row and the same height**; only the horizontal
offsets change. That is the structural fact this whole document turns on.

Three more Mac techniques, and what each is worth here:

| | on this machine |
|---|---|
| **compose the string into a buffer, then move it once** | ⭐ already done — `TextAt` fills `TB.Buf` and calls `BlitRow`. `boot-and-desktop.md` §5 item 8 is right that this one is taken |
| **synthesized styles** — bold is the glyph OR'd with itself shifted one pixel; italic is a per-row shear; outline is four smears minus the original | ⭐ **bold is two keyed copies one pixel apart**, and costs a second copy rather than a second ROM font. ⚠ Only under the key, and only for a 1-bit-ish face; an antialiased fringe OR'd with itself is not a bold fringe. Worth a line, not a plan |
| **the strike cache in the system heap** — strikes built or loaded on demand and kept | ⭐ **this is the answer to §4.3's build cost**, and it is the Mac's own answer to the same question |

### 3.2 GEOS and GeoWrite: the same table, a tighter bitstream

A GEOS font is a "mega font": one bitmap card set with `f_index`, a word a
character holding a **bit** offset into a bitstream, plus `f_setwidth`,
`f_baseline`, `f_height`. Widths are `f_index[i+1] − f_index[i]` — the Mac's
`locTable` under another name. GeoWrite composed a line into an off-screen
buffer and blitted it, and kept a dirty region so an edit redrew only what
changed.

### 3.3 ⭐ And the half this machine gets for nothing

⛔ **Both systems' inner loop is a SHIFT.** A bit offset is not a byte offset, so
every glyph blit on a Mac or a C64 is a shift-and-mask across word boundaries;
QuickDraw's `DrawText` and GEOS's `PutChar` are largely that shift, and it is why
the Mac generated code at run time (`docs/video-copyrect.md` §5.3) and why GEOS
kept pre-shifted copies.

⭐ **On a chunky 8 bpp card a proportional glyph is a byte-aligned rectangle,
exactly.** One pixel is one byte; the strike's column *is* the address's low
byte (`vidcpy3.asm`'s own note: *"the address is an OR, not an add… the
address's low byte **is** the column's low byte"*). There is no shift, no mask,
no word boundary and no pre-shifting. **The expensive half of both historical
designs is absent, and the cheap half — the location table — is already in the
ROM.**

⚠ **What we give up for that** is the Mac's density: 607 px × 17 rows is
**10,319 bytes** a strike at 8 bpp where the Mac's whole strike was ~2 KB at 1
bpp. §4.2 is the budget, and it fits.

---

## 4. The strike in VRAM

### 4.1 The shape

One band, one face, one ramp: **607 columns × 17 rows**, glyphs in code order,
byte per pixel, each byte already a palette index in that ramp.

⭐ **607 px fits inside VRAM's 1024-byte stride**, so a whole strike is one
contiguous band of 17 rows and:

- `CPTR2` (row bits 8–6) is **constant** across the strike;
- `CPTR1`'s row bits are constant across the strike, and its low two bits are
  the source column's bits 9–8;
- the source column is `loc[c]` — the running sum of widths that `TextW`
  already computes.

⚠ **`CPTR`'s row is left advanced by `CHEIGHT` at the end of a copy and is not
restored** (`v3host.cpld.ts:307-314` restores only the *column*). Row 480 + 17 =
497, whose bits 8–6 are still `111`, so `CPTR2` survives; `CPTR1` carries row
bits 5–0 and must be rewritten anyway. §5.2 counts it.

### 4.2 Where it lives

⭐ **Where the 384 comes from, because it is asked:** the framebuffer's stride is
**1024 bytes a row** (`plan.md` §4) and **every one of the four `VMODE`s is 640
pixels wide** — 640×200, 640×240, 640×400, 640×480 (`plan.md` §2.1). So columns
**640–1023 are never displayed**, and `1024 − 640 = 384`. It is this machine's own
arithmetic, ⛔ **not a Macintosh figure**: the Mac 128K's framebuffer is
512 × 342 × 1 bpp = 21,888 bytes (`video-copyrect.md` §5), and nothing this
document borrows from the Mac is a dimension — the strike layout and the
`locTable` are structures.

| candidate | rows | verdict |
|---|---|---|
| rows 480–510, full width | 31 | ⛔ **taken** — copyrect staging and `OWSet` saves (`plan.md:272`), and row 511's last 64 bytes are the pointer shape |
| ⭐ **columns 640–1023 of rows 0–511** — the scroll margin | 384 × 512 = **196,608 bytes (192 KiB)** | ⭐ **this one.** Where Paint already keeps its document (`keyed-copy.md` §3.2) |

⚠ **Two published figures for this area, and they do not contradict each other.**
`plan.md` §4 says **196 KB** for 384 × 512 = 196,608 bytes — every row. `keyed-copy.md`
§3.2 says **184 KB** for the same columns over **rows 0–479 only**, 184,320 bytes,
excluding the rows 480–511 scratch. ⚠ Neither document declares a unit and the two
round differently: 196,608 bytes is **192 KiB** (or 197 kB decimal), while 184,320
bytes is **180 KiB** (and 184 kB decimal, which is what that figure is). Byte counts
are given here instead, because a strike budget that is out by 8 % is a strike that
does not fit. (`sdcard.md` declares `KiB` explicitly for exactly this reason.)

A strike is 607 px and the margin is 384, so a strike is **two bands of 17 rows**
— 34 rows, 13 KB of margin. ⭐ **Keep both bands inside one 64-row group** (rows
0–33, 64–97, 128–161, …) and `CPTR2` stays constant for the whole strike, because
`CPTR2` *is* row bits 8–6. **Eight groups, eight strikes, one per ramp**, each
using 34 of its group's 64 rows and leaving 30 rows × 384 px (11.5 KB) over.

⚠ **Two costs to state up front.** The margin is the 1024-column torus that
`HSCROLL` scrolls into, so a screen that scrolls horizontally would scroll its
own font into view — acceptable for a desktop, fatal for a game. And **Paint's
document is already there**: this is an allocation decision, not free space.

### 4.3 How it is built, and what that costs

⭐ **Nothing new is needed to build one.** A strike is what `TextAt` already
produces: give it the 95-character string `" !"#$…~"` at the strike's origin and
it composes exactly the bytes a strike is made of — the same `GRow`, the same
`TB.NTab`, the same ramp. ⚠ `TB.Buf` is 660 bytes and a band is 384, so it is two
calls a band.

| building one strike | **estimated** |
|---|---|
| by composition, at today's 5.47 ms a character | **~0.52 s** |
| ⭐ by **upload** of pre-expanded bytes through `VDATA` at 7.63 µs a byte | **~79 ms** — at the price of 10.3 KB a strike in ROM or on the SD card |

⛔ **0.52 s × 8 is four and a half seconds of desktop start-up, which is not
acceptable, and it is the exact problem the Mac solved with a strike cache.**
Build the two or three ramps `desk` actually uses at start-up and the rest on
first demand, keeping N resident. `RPaper fcb 2,1,255,6,9,8,2,10` names all
eight; the file manager and the pull-downs use `R.White`, `R.Panel`, `R.Sel` and
`R.Dim`.

### 4.4 ⭐ The ramp problem, and how the window title dissolved it

The strike bakes one ramp, so text over a background that is not that ramp's
paper is wrong. There are exactly five places this bites (`boot-and-desktop.md`
§5 item 8 enumerates them):

| | today | with a strike |
|---|---|---|
| list rows, pull-down items | ⭐ already opaque, flat paper | ⭐ **strike, opaque copy, pixel-identical** |
| the manager's column header, its status strip | transparent **for one pixel** — `FM.HH`/`FM.SH` are 17 and the box needs 18 | ⭐ **give them one more row** — the document already says so — then strike |
| the menu bar's titles | transparent for one pixel — `GEO.TITY` is 2, so the box ends on `GEO.RULEY` | ⭐ same fix, then strike |
| ⭐ **the window tab** | ⛔ `RPaper` is **255**: the tab's paper is a step of a gradient, so `F.Opaq` is refused. `boot-and-desktop.md` calls this *"the most-drawn text in the GUI, and exactly what a key would rescue"* | ⭐⭐ **see below — it is not a key that rescues it** |
| desktop icon labels | transparent over the **wallpaper** | ⛔ genuinely non-flat. §4.5 |

⭐⭐ **THE TAB: the user's answer, 2026-09-21 — "2–3 lines of gradient above the
text, then a flat band, then 2–3 lines below".** `TGrad` (`tbox.asm`) walks the
tab's rows and steps `TB.C` through `C.TabG`'s eight entries by a Bresenham
accumulator, so the gradient is **a function of row**. Confining it to a few rows
at each edge and flattening the middle:

- gives `R.Tab` **a flat paper that is a palette entry**, so `RPaper`'s `255`
  becomes a real index and **`F.Opaq` starts working there with no other change**
  — a win on the software path *today*, before any strike exists;
- makes the tab strike-able like every other ramp;
- ⭐ **and removes the last reason to want a colour key for text at all** — which
  removes the palette renumber (`tbox`'s `KEY` is 15, the card's key is 0) that
  `boot-and-desktop.md` §5 item 8 names as the first obstacle anyone hits.

⚠ It is a change to `desk`'s tab geometry and `TGrad`'s call, and the benches read
the tab pixel by pixel (`run-v3desk.sh`, `checkdesk.py`), so it moves claims. That
is the cost, and it is small.

⚠ **Two footnotes.** A baked strike would work over a *full* gradient too — the
glyph sits at a fixed Y within the tab, so each glyph row lands on a known
gradient step and bakes exactly — but it would need a tab-specific strike whose
rows each use a different ramp, which is a second font build rather than a
selected ramp. The flat band is much cheaper. And even after the change, the
gradient rows above and below the text are unaffected: the text box is 17 rows
and the tab is taller.

### 4.5 ⛔ The one case that stays

**Desktop icon labels sit on the wallpaper**, which is a picture. There is no
correct antialiased answer: a baked fringe shows its paper, and the key is
binary. The honest options, in order:

1. ⭐ **Leave it on the software path.** It is one call site and a desktop holds a
   dozen labels, not four hundred. This is what the Mac did too — it had no
   antialiasing at all.
2. **A keyed strike** whose level 0 is index 0, baked against the wallpaper's
   dominant colour, accepting a one-pixel halo. ⚠ Costs the palette renumber.
3. **A 1-bit strike** for this site — level ≥ 2 is ink, below is transparent.
   Correct under the key, and visibly worse than the antialiased text beside it.

⛔ **Do not solve this one first.** It is the smallest case and the only expensive
one.

---

## 5. The protocol — what a glyph copy actually needs

### 5.1 The register map as it is

32 bytes at `$FF60`–`$FF7F` (`plan.md` §10, `regmap.ts`). The copy engine's
share, **and note the two blocks are not adjacent**:

| off | reg | |
|---|---|---|
| `+$08`–`$0A` | `WPTR` | destination, 19 bits, **little-endian**: `+$08` = column bits 7–0; `+$09` = column 9–8 in D1–D0, row 5–0 in D7–D2; `+$0A` = row 8–6 |
| `+$12`–`$14` | `CPTR` | source, same packing |
| `+$15` | `CWIDTH` | bytes a row (low 8) |
| `+$16` | `CHEIGHT` | rows (low 8) |
| `+$17` | `CCTRL` | b0 `GO`, b4–3 `CWIDTH[9:8]`, b5 `CHEIGHT[8]` |

**A general copy is nine bytes to nine addresses**, and that is what `boot.asm`,
`v3card_tb.sv` and `vidcpy3.asm`'s `CpSrc`/`CpDst`/`CpGo` all write. ⚠ A store is
**5 E cycles = 2.38 µs and is never stretched while the card is idle** —
`WAITN`'s only register term is `REGSEL & !RW & E & CARDBUSY`, and `CARDBUSY` is
`SPANBUSY # CBUSY # RP1..RP4`. So nine bytes is ~21 µs of bus, which is
`keyed-copy.md:305`'s "~33 µs" with the loads and the arithmetic included.

### 5.2 A glyph out of a strike needs six of them

Across a whole string, on one text baseline, out of one strike:

| field | across a string | per glyph |
|---|---|---|
| `CTRL`'s `WMODE` | ⭐ **invariant** — opaque, 00 | — |
| `WADV` | ⭐ **invariant** — must be 0 for a copy | — |
| `CPTR2` (source row 8–6) | ⭐ **invariant**, §4.1 | — |
| `WPTR2` (dest row 8–6) | ⭐ **invariant** while the line does not cross a 64-row group | — |
| `CHEIGHT` | the font height, **17, invariant** | ⛔ **1 byte — the hardware makes its register the counter** (`v3ptr.cpld.ts:243`), so software reloads it every copy |
| `CCTRL` | `GO` only; width ≤ 11 and height 17, so bits 5–3 are 0 — **a constant `$01`** | 1 byte |
| `CPTR1:CPTR0` | the strike column, from `loc[c]` | **2 bytes** |
| `WPTR1:WPTR0` | the pen, advanced by the width | **2 bytes** |
| `CWIDTH` | `loc[c+1] − loc[c]` | 1 byte |
| | | ⭐ **6 bytes** |

⭐ **And none of them needs a shift.** The address is an OR, so a 16-bit table
entry holding `(rowbits | column)` **pre-byte-swapped** goes straight out with one
`std` — `std` writes A at the address and B at the address+1, and `+$12` is the
*low* byte, so the table holds `(low, high)`. The pen is maintained by one `addd`
of the glyph width in the same byte-swapped form. ⚠ Byte-swapping a running sum is
not free; §9 lists it as the thing to check, and the alternative is to keep the pen
unswapped and pay one `exg a,b` (8 cycles) a glyph.

### 5.3 The loop, and the number that falls out of it

⚠ **Estimated**, at E = 2.0979 MHz. `Y` walks a per-string list of 5-byte
records that `TextW` emits on its existing pass; `U` is the card window; `X` is
the count:

```
b@      ldd     ,y++            6     CPTR pair, pre-swapped
        std     VR.CPTR0,u      6     -- 2 register bytes
        ldd     ,y++            6     WPTR pair, pre-swapped
        std     VR.WPTR0,u      6     -- 2
        lda     ,y+             6     this glyph's width
        sta     VR.CWIDTH,u     5     -- 1
        ldd     #(17*256)+1     3     CHEIGHT, and CCTRL with GO
        sta     VR.CHEIGHT,u    5     -- 1
        stb     VR.CCTRL,u      5     -- 1  the copy starts here
        leax    -1,x            5
        bne     b@              3
                              ----
                               56 E cycles = 26.7 us
```

⭐ **MEASURED 2026-09-21: 60.42 cycles, 28.80 µs** (`test/glyphloop.asm`, 40
glyphs on the host emulator). The estimate above was **56 — 8 % optimistic**, which
is about what reading a loop off the page is worth. The measured figure is what §6
and §8 use.

And the engine, for the mean glyph: 6.39 px × 17 rows = 109 bytes at the
engine's **0.247 µs a byte** =

| | |
|---|---|
| the driver loop — **measured** | **28.80 µs** |
| the engine | **26.9 µs** |

⭐⭐ **They are equal to within seven percent**, and the estimate had them equal to
within one. The conclusion does not move: That is not a coincidence worth
admiring, it is the number that decides everything below: the protocol and the
silicon are already balanced, so **no amount of protocol work can be worth more
than 2×**, and §6 says why it is not free either.

### 5.4 ⛔ Why packing to seven bits-worth of bytes is the wrong move

The proposal was 10 + 9 + 8 + 8 + 10 + 9 = 54 bits, "just under 7 bytes", against
a protocol believed to use more.

| a strike glyph | register bytes | shifts | E cycles |
|---|---|---|---|
| ⭐ **as it is, exploiting invariance** | **6** | **none** | 56 |
| the packed 54-bit form | 7 | ⛔ six fields to align and merge | ~100+ |
| ⛔ the general 9-byte copy, as `vidcpy3` writes it | 9 | four, plus `CCTRL`'s bit assembly | ~145 |

⛔ **Packing loses twice.** It writes *more* bytes than six, and it re-introduces
the shifting that the card's OR-not-add address layout exists to avoid. The
saving it is aimed at — three of the nine bytes — is available for free by
noticing that three of the six fields do not change across a string.

⭐ **The user's seven is right about a different thing**, and since 2026-09-21 it
is measured rather than argued (§8). Seven *consecutive* bytes, unpacked, is what
an HD6309 writes in three instructions:

| | |
|---|---|
| `STQ` | four bytes — `CPTR0`, `CPTR1`, `WPTR0`, `WPTR1` |
| `STW` | two — `CWIDTH`, `CHEIGHT` |
| `STA` | one — `CCTRL`, and the copy starts |

⛔ **The present map cannot do it**: `WPTR` is at `+$08` and `CPTR` at `+$12`, ten
bytes apart, so `STQ` can reach neither pair of pairs. **Re-ordering the window so
the copy engine's nine bytes are contiguous in that order** makes a *general* copy
`STQ`+`STQ`+`STA` — three instructions, nine bytes — and a strike glyph
`STQ`+`STW`+`STA`.

⛔ **MEASURED, AND WORTH 1.11× RATHER THAN THE 1.9× THIS SECTION ESTIMATED.**
60.42 → **54.42 cycles** a glyph, not 56 → ~30 (§8's table). The conclusion that the
driver ducks under the engine survives — 25.94 µs against 26.9 — but by a hair.
⛔⛔ **And using the wide stores WITHOUT the re-order is 0.94×, a regression**: the
`$10` prefix costs a cycle an instruction and buys nothing while the pairs are ten
bytes apart. The re-order is not an optimisation on top of the 6309; it is what
makes the 6309 worth anything in this loop.

⚠ **What that costs.** It is a pure address re-assignment: no new logic, no new
pins, no wider bus. But it is a **spec change** reaching `regmap.ts`, `plan.md`
§10, `boot.asm`'s POST, `machine.c`, `vidcpy3.asm`, `v3card_tb.sv`, `mkv3copy.py`
and every `.cpld.ts` that decodes an offset — and the decodes it moves are
`v3ptr`'s, which is at **124/128 cells, 133 % Nodes+FB, seven of eight LABs at
39 of 40 inputs**. A re-assignment should not add product terms, but "should not"
is not a result: **it needs a fit, read out of the new `.fit` against `v3ptr`'s
existing 3 cascades**, and CLAUDE.md's ninth trap applies — a refusal is not a
result until a second file name refuses it too.

### 5.5 ⭐ The 32-byte window has two free bytes — verified, and it is the cheap version

⭐ **CHECKED, 2026-09-21, and it is now a gate**: `video3/logic/regmap.check.ts`
(`make -C hardware check`) walks all 32 offsets and requires each to be *decoded by a live
part*, *read by the register file's own address generator*, or *a dedicated port*.
**29 used, 3 spare.** The full table is the check's own output.

⛔ **"It reads back" is not evidence, which is why the check asks a different
question.** Every offset but `+$0C` and `+$0D` reads back from the 32-byte file,
because the file is RAM and `RDBKOE` puts it on the bus — `boot.asm` uses `+$13`
as its card-probe scratch for exactly that reason. A byte that reads back what was
written and is decoded by nothing is the `ACTRL` b3 defect wearing an address.

Three ways an offset earns its place, and all three are in use:

| | offsets |
|---|---|
| a **load strobe** decoded by a live part | 22 of them — `LDCTRL` by `v3dot` *and* `v3host`, `LDHSL` by `v3dot` *and* `v3scan`, the rest singly |
| ⭐ the **register file's address generator reads it** — no strobe at all | `+$05` `SPANLEN` (where `RFA` parks when idle), `+$06`/`+$07` `WFG`/`WBG` (where it points through a span, `RFA0` being the mask bit), and `+$08`, `+$09`, `+$12`, `+$13` (the four-state walk that restores the two columns) |
| a **dedicated port**, not a file byte | `+$0C` `VDATA`, `+$0D` `VSTAT`/`LDIRQACK` |

⚠ **And the spare count is three, not two.** `+$1F` is spare in *hardware* too —
nothing decodes or reads it — but the VBL service parks its frame count there
(`plan.md` §10), so **two are free for silicon: `+$1D` and `+$1E`.**

⛔ **The trap this check exists for is already in the tree.** `regmap.ts:46-47`
still declares `LDSPRIX` and `LDSPRDA` at those two offsets, and
`video3/logic/v3dot_si.pld` and `v3host_st.pld` *do* decode them — with real
sequencer logic behind them. Those are **partition variants**, not the board:
`video3_card.v` instantiates the bare `v3dot`, `v3scan`, `v3ptr`, `v3host` and
`v3lane`, and `v3host.cpld.ts` emits `"v3host_st"` only under
`DECODE === "strobes"`. **Counting a variant's decode as a use is exactly how
"`+$1D` is taken" would get believed**, so the check reads the live designs only
and names the two orphaned strobes as a claim of its own.

⭐ **Two bytes is exactly enough for the cheapest useful change**: alias `CWIDTH`
at `+$1D` such that **a write there is `CWIDTH` and `GO` together**. A strike
glyph then costs **5 bytes and one fewer store** (`CCTRL` disappears from the
loop; `CHEIGHT` stays because the hardware counts it down).

⚠ **The cost is one CELL, not one term, and on this part that matters.**
`decodeCells()` makes each strobe an internal node — a macrocell with a single
product term — so `LDCWGO` would take one of `v3ptr`'s four spare cells, and
`GOQ`'s term list gains it. `v3ptr` is **124/128 with 3 cascades**, and its
Nodes+FB is over 130 % with seven of eight LABs at 39 of 40 inputs: a part that
refuses additions on grouping before it runs out of cells. **That is a fit and
not an assumption**, read out of the new `.fit` against those numbers, and
CLAUDE.md's ninth trap applies — a refusal is not a result until a second file
name refuses it too.

⚠ Two bytes is **not** enough to make the nine contiguous, so §5.4's re-order and
this are alternatives at different prices, not steps of one plan.

---

## 6. ⛔ `/WAIT` IS THE CEILING, and it is 2×

`v3host.cpld.ts:223`:

```
WAITN = VPORT & E & CARDBUSY
      # REGSEL & !RW & E & CARDBUSY
      # VPORT & E & RW & !RDVALID
```

with `CARDBUSY = SPANBUSY # CBUSY # RP1 # RP2 # RP3 # RP4`.

⛔ **The second term means the host cannot set up the next copy while this one
runs.** The first store of glyph *n+1* stalls until glyph *n* retires. There is
no pipelining and no queue — video3 deleted the display-list engine, and that
deletion is what paid for the copy engine in the first place (`plan.md:70`).

So, with the driver loop and the engine both at ~27 µs:

⛔ **THE TABLE BELOW IS THE ESTIMATE, AND §6.1 MEASURED IT AT 33.42 ms.** It is
left standing because the *shape* of its argument — `/WAIT` serializes the driver
against the engine — is still right, and because the way it is wrong is the
useful part: it counts the register sequence and nothing around it, and the
per-copy call turns out to be 97 % of the bill.

| a 40-character line | ⛔ **estimated, and wrong by 19×** | |
|---|---|---|
| `F.Opaq`, as shipped — **measured** | **218.64 ms** | |
| ⭐ strike, serialized by `/WAIT` (27 + 27) | **2.2 ms** | **99×** |
| + building the per-string list (~14 µs a glyph) | **2.8 ms** | ⭐ **78×** |
| ⭐⭐ strike + a shadowed `GO` (the two overlap) | **1.1 ms** | 199× |
| the engine alone — the floor | **1.1 ms** | |

⭐ **This was meant to be the number that prices the silicon**, and ⛔ **§6.1
takes that role away from it.** The argument above is that the driver loop and
the engine cost the same, so nothing but overlapping them is worth 2×. Measured,
a glyph costs **769 µs** and the engine's 29 µs is **2 % of it** — so the two
do not cost the same, the serialization `/WAIT` imposes is not the binding
constraint, and **the overlap this section asks silicon for buys 2 %.**

⚠ **What binds instead is the per-copy call**, which this section did not count
at all. See §6.1, and §7's re-opened ranking.

---

## 6.1 ⛔ BUILT AND MEASURED 2026-09-22 — 6.7×, not 78×

⭐ **The strike is built, and it draws the same pixels.** `tbox.asm`'s
`SkHave`/`SkBuild`/`SkText`, toolbox call 12, gated by `run-v3text.sh`
(**22 claims, 0 failed**): a line drawn as one copy-engine rectangle a glyph is
**0 of 3,825 bytes different** from the same line composed a pixel at a time.
§4's design works — the bands come out of the positions `mktbox.py` bakes, so
the ROM and the host cannot disagree about the layout.

⛔ **And the speed is nothing like what this document predicted.** Measured, a
40-character line (`run-v3text.sh`, 29 claims):

| | |
|---|---|
| transparent, as `desk` drew it before 2026-09-21 | **368.72 ms** |
| opaque (`F.Opaq`), the shipping path | **222.89 ms** |
| ⭐ out of the strike, **paying for the build** | **55.68 ms — 4.0×** |
| ⭐⭐ out of the strike, **steady state** | **33.42 ms — 6.7×** |
| §6's estimate | ⛔ **2.8 ms — 78×** |

⚠ **The two strike rows are the same code and the difference is the cache.**
`v3t40s` is the first caller for its (font, ramp) in the session, so its 25
draws carry the one build; `v3tlow` runs next in the same pair and does not.
**The build costs ~556 ms** — it composes 95 glyphs — so it pays for itself
after about three 40-character lines, and the bench asserts the ordering rather
than assuming it.

**A glyph costs 769 µs in steady state.** §5.3 estimated 28.80 µs of driver and
§6 added 26.9 µs of engine, for ~56 — so the measurement is **fourteen times**
the estimate, and every multiplier in §0, §2 and §6 that rests on it is wrong by
about that factor.

⚠ **What the estimate left out is the per-copy call, and this document already
knew better.** `keyed-copy.md` §7.1 measures a rectangle at **2,143 µs** through
`SS.Copy`, **344 µs** through `SS.CopyN` and ~87 µs in a process that owns the
card; §5.3 counted the eleven instructions of the register sequence and nothing
around them. The path here is toolbox → `TVCALL` → `TbVec` → `RowCopy`, which is
cheaper than an OS call and dearer than owning the card, and 769 µs sits
between those two figures rather than near the instruction count.

⭐ **The conclusion that survives is the one §2 corrected.** A per-glyph blit is
**6.7× faster than the software path**, not slower — `boot-and-desktop.md` §5
item 8's arithmetic was wrong about the direction, and this measurement settles
it in the same direction by a smaller factor. What does *not* survive is §6's
"the driver loop and the engine cost the same, so the ceiling is 2×": at 769 µs
a glyph the engine's 29 µs is **under 4 % of the bill** and the ceiling on
protocol work is nowhere near reached.

⛔ **So §7's ranking is re-opened.** The strike made text 6.7× faster for no
silicon; what would make it faster again is **removing the per-copy call**, which
is `SS.CopyN`'s argument (a list of rectangles, one call) applied to glyphs
rather than to sprites — §7 item 5's hardware descriptor walker, or a toolbox
call that takes a whole string's worth of rectangles. That is the next
measurement to take, and it should be taken before any of §7's silicon.

⚠ **And two limits of what is built**, both recorded in `tbox.asm`: `SkText`
**does not clip** — a glyph past the window's edge is drawn anyway, and the
caller keeps the string inside, which `TextW` answers — and there is **one
strike at a time**, so a caller that alternates ramps rebuilds on every call and
should not use it.

---

## 6.2 ⭐⭐ WHERE THE 768 µs GOES — traced 2026-09-22

§6.1 said the per-copy call was 97 % of a glyph and did not say what the call
*is*. This is that, measured: a time-weighted PC histogram of 600,000
instructions over one 1.27 s command that draws **800 glyphs out of the strike**
(`emu/test/pchist.py`, and `machine.c`'s trace line now carries a dot count so
the histogram can be weighted by time instead of by instruction).

| per glyph | µs | 6809E cycles |
|---|---|---|
| `ca_row.asm` — `RowCopy`, `CardAddr` ×2, `CpRest`, `CpWaitR` | **302** | **543** |
| `tbox.asm` — `SkText`'s loop, `Glyph` | **203** | **364** |
| `vidcore.asm` — `VcMode`, `VcAdv`, `VcLoad`, `VcCLoad`, `VcWait` | **129** | **232** |
| `coarm.asm` — the escape parser and the dispatch | **95** | **171** |
| ⭐ **total in CoArm + the toolbox** | **729** | **1,310** |

⚠ The rest of the command — `Krn`, `ArmIO`, `rbromdisk`, `SCF`, `IOMan`, `RBF` —
is the stream reaching the window, which is exactly what `run-v3text.sh`'s
copy-to-`/nil` subtracts. 729 µs against the bench's 768 is the two methods
agreeing.

### 6.2.1 ⛔ The layering is 22× the protocol it wraps

`test/glyphloop.asm` measured the **register sequence itself at 60.42 cycles**
(§5.3) and the engine's share of a 7 × 17 glyph is ~29 µs, or **52 cycles** of
`/WAIT`. So:

| | cycles | |
|---|---|---|
| the protocol — `CPTR`/`WPTR`/`CWIDTH`/`CHEIGHT`/`CCTRL` | 60 | 4.6 % |
| the copy engine | 52 | 4.0 % |
| ⛔ **everything else** | **1,198** | **91.4 %** |

⛔ **And none of it is a stall.** The most expensive single instruction in the
whole trace is **5.2 µs** — an ordinary extended-addressing 6809 instruction at
1.8 MHz. There is no `/WAIT` pile-up, no bus contention and no wait loop: the
1,310 cycles are **about 350 instructions**, executed to blit one 7 × 17
rectangle whose register sequence is eleven of them.

### 6.2.2 What that means for §5 and §7

⛔ **The register encoding is 4.6 % and the silicon is 4.0 %.** Packing the
fields into the 32-byte window — the question this document was opened to
answer — is worth **at most 4.6 %**, and less after the CPU pays to assemble the
packed form. §7 item 3's shadowed `GO` buys the overlap of two things that are
**8.6 % together**.

⭐ **The room is in collapsing the layers**, and the trace prices each one:

| | µs/glyph | |
|---|---|---|
| `VcMode` + `VcAdv` + `CpRest` + `VcWait` — the card's mode saved, set and put back | **70** | ⭐ **per BATCH, not per glyph** |
| `RowCopy`'s entry tests | **34** | ⭐ mostly hoistable |
| `CardAddr`, called **twice** a glyph to recompute addresses that advance by a constant | **56** | ⭐ incremental instead |
| `VcLoad` + `VcCLoad` — the cache-compare wrappers around two register writes | **50** | ⚠ ~11 cycles of this is the protocol |
| `SkText`'s loop, including a `TVCALL` round trip **a glyph** | **143** | ⭐ one call for a string |

⚠ **A conservative batched call — one entry for N glyphs, mode set once, entry
tests hoisted, addresses carried forward — removes ~160 µs of 768, which is
1.3×.** The larger prize is a *string* primitive inside CoArm that does the
setup once and then, per glyph, only the addressing and the register sequence:
that is ~100 cycles plus the engine's 52, or **~85 µs a glyph, which would be
9×**.

⛔ **That second figure is an estimate and this document has a record.** §6
predicted 2.8 ms a line and measured 33.42. What is different this time is that
the estimate is bounded by a **measured floor** (60 cycles of protocol and 52 of
engine, both measured, not derived) and a **measured actual** (1,310), rather
than by a subtraction — so the answer is known to be between 1× and 12× before
anyone writes a line of it.

## 6.3 ⭐⭐ THE BATCHED CALL, BUILT AND MEASURED 2026-09-22 — 1.23×

`TV.CopyN` (`ca_row.asm` `RowCopyN`, `armvid.d` `CG.CpLst`) takes a **run** of
rectangles that share a destination row, a height and the card's mode.
`SkText` appends five bytes a glyph — the band's row, its column and the width
— and issues one call a line; the destination is implied by the first corner
and each width advances it.

| a 40-character line, steady state | | |
|---|---|---|
| a copy a glyph, §6.1 | 33.41 ms | 768 µs a glyph |
| ⭐ **a run a line** | **27.08 ms** | **610 µs a glyph** |
| | **1.23×** | and **8.2×** against composing it opaque |

⭐ **The prediction held.** §6.2 said ~160 µs a glyph and the measurement is
**158**. That is worth saying plainly because §6's estimate was 19× out: the
difference is that this one was read off a trace of the routines being removed,
not derived from a model of what the hardware ought to cost.

⚠ **And the pixels are the same** — `run-v3text.sh`'s four comparison bands are
unchanged at 0 bytes different, above and below the strike's own rows.

⛔ **`CpTest` is shared, not copied.** The disjoint-rectangle rule is one
routine that both `RowCopy` and `RowCopyN` call. A second copy of it would
still be refusing every glyph drawn below row 320, which is the defect §6.1
records — and a batched path with its own subtly older rule is exactly how that
class of bug comes back.

---

### 6.3.1 ⛔ What is left, and a correction to §6.2's ceiling

Traced again after the change — same 800 glyphs, same instrument:

| per glyph | before | after |
|---|---|---|
| `ca_row.asm` | 302 µs | **260** |
| `tbox.asm` | 203 µs | **174** |
| `coarm.asm` — the escape parser | 95 µs | **95** |
| `vidcore.asm` | 129 µs | ⭐ **52** |
| **total** | **729 µs** | **585 µs** |

⭐ `vidcore` fell by 60 % — that is the `WMODE`/`WADV` save-set-restore and
`VcWait` moving from per glyph to per line, which is what the call was for.
What remains there is `VcLoad` + `VcCLoad`, 50 µs, and those **are** the
protocol.

⛔ **And `coarm.asm` did not move at all, which is the correction.** §6.2 priced
a full string primitive at ~85 µs a glyph and **that was wrong**, because it
assumed away a cost the trace had already shown: 95 µs a glyph is CoArm's
**escape parser**, and a `sktext` escape is 46 bytes for 40 glyphs — so this is
**82 µs to collect ONE parameter byte**, 148 cycles, and it is spent before any
drawing routine is entered. No primitive further down can remove it.

⚠ **So the honest ceiling for this path is about 3×, not 9×.** A floor of the
parser (95) plus a tight inner loop and the engine (~110) is ~205 µs a glyph
against today's 610. The remaining items, in order of what they cost now:

| | µs/glyph | |
|---|---|---|
| `RowCopyN`'s per-entry body | **135** | every value goes out through a global and `CardAddr` reads it back; the card base and the addresses could stay in registers across the run |
| `SkText`'s loop | **113** | `Glyph`, the clip test, five stores |
| ⛔ **CoArm's escape parser** | **95** | **82 µs a byte** — its own finding, and the largest single thing left |
| `Glyph`'s lookup | 37 | |
| the pen and address advance | 31 | |
| `VcLoad` + `VcCLoad` | 50 | ~19 µs of this is the six register stores; the wrappers are the rest |
| `CardAddr`, now once | 29 | |
| `CpTest` | 19 | |

⭐ **The next measurement is the parser, not the copy engine.** 82 µs a byte is
the same order as a whole glyph blit, it is paid by *every* escape this machine
draws, and nothing in §5 or §7 touches it.

---

## 6.4 ⭐⭐ THE INNER LOOPS, BUILT AND MEASURED 2026-09-22 — 9.5×

§6.3.1 named two items worth 248 µs of a 610 µs glyph and said both were the
same defect: values marshalled through CoArm's globals between layers that
could hold them in registers. Four changes, all of them local:

| | |
|---|---|
| ⭐ **`CpSrcA`, a second ENTRY POINT into `CardAddr`** | `RowCopyN` used to hand the source corner in by pushing `CG.RY`/`CG.RX`, overwriting them, calling `CardAddr` and putting them back — eight instructions and two stack pairs a rectangle, to avoid a second copy of the arithmetic. Two operand addresses and a shared body cost neither |
| ⭐ **the card in `X`, so `U` stays the list** | `ldu VG.Base,y` took the list pointer with it, and the loop rebuilt it from `CG.CpLI` with a `MUL` every rectangle |
| ⭐ **`CCTRL` computed once a run** | its width bits are bits 9–8 of `CWIDTH` and an entry's width is **one byte**, so they are zero by construction; its height bit is shared by the run. ⚠ `CHEIGHT` itself is still written per rectangle — the emulator models it sticky and the card does not (`CLAUDE.md`) |
| ⭐ **three of the four clip edges hoisted** | the pen's row never moves over a string and its left edge is only ever the first glyph's, because the pen is monotonic. Only the right edge is asked per glyph |

| a 40-character line, steady state | | |
|---|---|---|
| a copy a glyph (§6.1) | 33.41 ms | 768 µs |
| a run a line (§6.3) | 27.08 ms | 610 µs |
| ⭐ **with the loops tightened** | **23.41 ms** | **518 µs** |

⭐ **9.5× against composing it opaque, and 15.8× against the transparent path
`desk` drew before 2026-09-21.** The prediction was ~90 µs a glyph and the
measurement is 92 — the second estimate in a row to hold, for the same reason:
both were read off a trace of the instructions being removed.

⚠ **And the pixels are still the same** — all four comparison bands at 0 bytes
different, above and below the strike's own rows.

### 6.4.0 What each change was worth, traced

Same instrument, same 800 glyphs, before and after each step:

| per glyph | §6.1 | §6.3 | ⭐ §6.4 |
|---|---|---|---|
| `ca_row.asm` | 302 µs | 260 | **197** |
| `tbox.asm` | 203 µs | 174 | **149** |
| `vidcore.asm` | 129 µs | **52** | 52 |
| `coarm.asm` — the escape parser | 95 µs | 95 | 95 |
| **total** | **729** | **585** | **496** |

The two routines §6.3.1 named came down as predicted: `RowCopyN`'s per-entry
body **135 → 84 µs**, `SkText`'s loop **113 → 87 µs**.

⛔ **And `coarm.asm` has not moved through any of this, which is now the
largest single item left.** §6.3.1 examined it and found the fix worth ~21 µs:
`CF.WriteN` already delivers a run, CoArm's per-call prologue already happens
once a run — but SCF's scan stops at any byte below `$20` and an escape stream
is full of them, so the runs are **4.6 bytes instead of 46**. Three-quarters of
the parser's cost is genuinely per byte and no batching reaches it. ⚠ The
remaining quarter needs a change to `level1/modules/scf.asm`, which every
device on this machine writes through, for ~4 %; it is not worth it yet.

| what is left, per glyph | µs |
|---|---|
| `SkText`'s loop | 87 |
| `RowCopyN`'s per-entry body | 84 |
| `Glyph`'s font-directory lookup | 37 |
| `VcLoad` + `VcCLoad` | 50 |
| `CardAddr` / `CpSrcA` | 22 |
| `CoWriteN`'s byte loop + `Collect1` | 42 |
| `CpTest` | 19 |

### 6.4.1 The whole story, in one table

| a 40-character line | ms | × |
|---|---|---|
| transparent, as `desk` drew it before 2026-09-21 | 368.70 | 1.0 |
| `F.Opaq` | 222.95 | 1.65 |
| ⭐ the glyph strike, a copy a glyph | 33.41 | 11.0 |
| ⭐ one run a line | 27.08 | 13.6 |
| ⭐⭐ **the tightened loops** | **23.41** | **15.8** |
| ⛔ §6's estimate | 2.8 | 132 |

⛔ **None of it was silicon and none of it was the protocol.** §6 asked for a
shadowed `GO`; the register sequence and the copy engine together were 8.6 % of
a glyph before any of this and are ~13 % of one now. Everything above came from
deleting software that was doing per rectangle what a run needs once.

### 6.4.2 ⛔ What it broke: the BOOT ROM's dialog (found and fixed 2026-09-22)

`TVCALL` is `jsr [CG.TbV + TV.<name>]` — an **offset into whatever the caller
put at `CG.TbV`** — and §6.3 gave `tbox.asm` a new one, `TV.CopyN` at offset 24.
⛔ **`software/boot/boot.asm` has its own row layer** (`tbvec`, seven entries,
last at offset 18) because the boot dialog draws with the toolbox before there
is a CoArm, and it was not extended. `SkFlush` therefore jumped to `tbvec+24`,
which is **the middle of `tbmapb`'s `cmpd` operand**: four bytes of an operand
executed as instructions, an `rts` into VRAM, and the machine ran wild two
seconds into every boot with no bootable card.

⚠ **It was invisible on the machine that works.** *"Disk found"* is `F.Reg` and
flushes no batch; only the question mark's `F.Bold+F.Opaq` reaches `SkFlush`
with a list pending. So the card path drew perfectly and every bench that had a
card passed — `software/nitros9/run-sdboot.sh`'s two controls are what found it,
and only after they stopped being able to fall back to a ROM disk.

⭐ **The fix is the documented answer, not a stub.** `TV.Copy` says *"carry set
if it could not"* and `TV.CopyN` says *"carry back means compose the whole
string"*, so `boot.asm` answers both with `orcc #$01` and the dialog composes its
thirty characters the long way — which is what it did before the strike existed.
⛔ **Nothing checks the two tables against each other**, and that is the live
hazard: a new `TV.*` entry in `tbox.asm` is a new entry in `boot.asm` on the same
day, or the next thing that flushes jumps into an operand.

⛔ **And that fix alone was not enough — `machine_tb`'s `nodisk` caught the rest.**
A refused flush still left `SkHave` having *built* the strike: 95 glyphs composed
into the margin at ~556 ms a face, for a layer that can never copy one out.
`$60` → `$62` took **846 ms**, and the RTL scenario timed out with the progress
port stuck at `$60`. ⭐ **`SkHave` asks first now** — `SkCan`, an **empty run**
(`CG.CpLN = 0`, which `ca_row.asm`'s `RowCopyN` answers carry-clear and draws
nothing) — and a layer with no copy engine refuses it whatever the list says.
One probe a face, and the dialog is **274 ms**: the 572 ms saved is exactly the
build that was being thrown away.
⚠ **The general shape is worth the name**: a cache whose *only* use is a fast
path must not be filled by a caller that cannot take that path. The strike has
no other consumer, so "can I copy?" is the question that gates the build.

### 6.4.3 ⛔ And it had stopped the `video/` build assembling at all

`CpSrcA` — §6.2's shared entry point into `CardAddr`, the one that saved eight
instructions a rectangle — was hoisted **above** `ca_row.asm`'s `IFNE V3` guard
while `CG.CpSY`/`CG.CpSX` stayed inside `armvid.d`'s. So a build without `V3=1`
died on *"Undefined symbol CG.CpSY"*, and **nothing noticed for a day**: every
bench that runs CoArm passes `V3=1`, because the desktop, the toolbox and the
copy engine are all inside that flag. ⚠ `machine_tb`'s `nitros9` scenario is the
one that does not — and it is asked for by name, so it is not in any aggregate
either. ⭐ It is inside the guard now.

---

## 7. What silicon would buy, in order

The budget, which decides what is askable (`optimizations.md`, `keyed-copy.md`
§7):

| part | cells | I/O pins | cascades |
|---|---|---|---|
| `v3dot` | 121/128 | 63/64 | 5 |
| `v3scan` | 112/128 | 63/64 | 3 |
| `v3ptr` | ⛔ **124/128** | 58/64 | 3, **133 % Nodes+FB** |
| `v3host` | ⭐ **58/128 — 70 spare** | ⛔ **64/64 — none** | 0 |

⭐ **Every item below is decode and sequencing, so every one of them needs zero
new pins** — which is the constraint that killed the programmable key and the
extra sprites. The room is on `v3host`. ⛔ The parts that own the copy registers'
decode are `v3ptr`'s, and `v3ptr` is the part that refuses.

| | what it buys | cost | |
|---|---|---|---|
| 1 | ⭐ **`CWIDTH`+`GO` alias at `+$1D`** (§5.5) | 6 bytes → 5, one store a glyph | one decode term on `v3ptr` | ⚠ needs a fit |
| 2 | ⭐ **`CHEIGHT` sticky** — a holding register beside the counter, the way `CWIDTH` already has one (`CWLOAD = CROWADV # !CBUSY`, `v3ptr.cpld.ts:242`) | 5 bytes → 4; and it removes a **real trap** — the emulator models `CHEIGHT` as sticky and the hardware does not, so code written against `machine.c` runs 512-row copies on silicon | 8 macrocells on `v3ptr` | ⛔ **`v3ptr` has 4 cells.** Would have to move to `v3host`, which has the cells and no pins — and the decode broadcast (`REGWR + RA4..RA0`) is exactly how it would get there |
| 3 | ⭐⭐ **A shadowed `GO`** — one spare set of `CPTR`/`WPTR`/`CWIDTH`/`CHEIGHT`, written while the current copy runs, consumed at retire | ⭐ **the only change worth 2×** (§6) | ~40 macrocells on `v3host` of 70 spare, no pins. ⚠ And the mechanism half-exists: the register file is RAM and the **column-reload walk `RP1..RP4` already reads shadows out of it** (`v3host.cpld.ts:307-314`) | ⚠ 40 of 70 is not a small ask; and `WAITN`'s second term has to learn the difference |
| 4 | **`WPTR` auto-advance by `CWIDTH`** — a pen | 4 bytes → 2 | an adder on `WPTR` | ⛔ worth little once §6 is understood, and `v3ptr` refuses adders |
| 5 | ⛔ **the hardware descriptor walker** | concurrency and persistent lists | `v3host`'s cells | ⛔ `keyed-copy.md` §4.1: the CPU spends **91.6 µs** building a VRAM descriptor against **~33 µs** writing the registers it replaces. For 27 µs of glyph, it is a loss |

⭐ **The honest ranking: build nothing** — and ⛔ **the re-measure §6.1 asked
for has happened, so the ranking above is stale in one specific way.** Item 3, "the
only one worth 2×", rests on §6's claim that the driver and the engine cost the
same; at a measured 769 µs a glyph the engine is under 4 % of the bill and **a
shadowed `GO` is worth 2 %, not 2×**. Item 5's arithmetic changes sign for the
same reason: `keyed-copy.md` §4.1 prices a VRAM descriptor at 91.6 µs against
~33 µs of registers and calls it a loss *for a 27 µs glyph* — against a **769 µs**
one, a descriptor list that replaces N calls with one is the largest win on the
page. ⚠ Nothing here should be asked of the fitter until the per-call cost is
taken apart, because every row of this table is priced against an engine that
turns out not to be the cost.

---

## 8. The 6309 — MEASURED 2026-09-21, and §5.4's estimate was wrong

⭐ **The host emulator executes 6309 instructions now.** `emu/hd6309.c` (2026-09-21,
`hardware/cpu/docs/6309.md` §4.1) runs `TFM`, `LDW`/`STW`, `LDQ`/`STQ`, `ADDW`/`SUBW`/`CMPW`,
the inter-register group, `PSHSW`/`PULSW`/`PSHUW`/`PULUW`, `SEXW`, `LDMD` and the
extended `TFR`/`EXG` codes; everything else is **refused by name** rather than
executed as a 6809 ghost. So this section stops estimating.

`test/glyphloop.asm` runs §5.3's loop and two 6309 forms of it, 40 glyphs each,
and counts. **Measured, emulation mode:**

| a strike glyph, the CPU's own work | E cycles | µs | |
|---|---|---|---|
| **6809, today's map** — §5.3's loop | **60.42** | **28.80** | ⚠ §5.3 estimated **56**: 8 % optimistic |
| ⛔ **6309 `STW` pairs, today's map** | **64.42** | 30.71 | ⛔ **0.94× — SLOWER** |
| ⭐ **6309 `STQ`+`STW`+`STA`, §5.4's re-order** | **54.42** | **25.94** | ⭐ 1.11× |

⛔ **§5.4's "56 → ~30 cycles = 14 µs" was wrong by 1.8×.** The re-ordered 6309
form is **54.42 cycles, not 30**. Its *conclusion* survives — 25.94 µs is under the
engine's 26.9 µs, so the driver does duck below the engine and the engine does
become the floor — but **by a hair, not by a factor of two.**

⛔⛔ **AND THE MIDDLE ROW IS THE WARNING.** Using the 6309's wide stores on the map
as it stands is a **regression**: every `$10`-prefixed instruction costs a cycle for
the prefix, and on a map where `WPTR` is at `+$08` and `CPTR` at `+$12` that cycle
buys nothing, because `STQ` can reach neither pair of pairs. **"Use `STW`/`STQ`"
without §5.4's re-order is 4 cycles a glyph slower than plain 6809 code.** The
re-order is not an optimisation *on top of* the 6309 — it is the thing that makes
the 6309 worth anything here at all.

⚠ **These are EMULATION-MODE figures and native mode is not implemented.**
`hd6309_nm_delta[]` is generated from the book but not yet applied, so the 6309
column is a **floor**: Appendix A shortens many of these forms by a cycle in native
mode (`LDW` direct 6 → 5, `SUBW` direct 7 → 5), and `LDQ`/`STQ` indexed are
unchanged at `8+`. §9 item 6 is what settles it.

⚠ **And the cycle counts themselves are gated**, because a wrong one is invisible —
the instruction does the right thing and the machine is simply the wrong speed.
`test/cyc6309.py` times every implemented form against Appendix A via
`test/hd6309.tab`. ⛔ **It found 20 of 32 forms wrong on its first run**, and the
table above is what they became after that was fixed; the numbers in the first
draft of this section were taken before it existed and were not trustworthy.

What the 6309 is still worth beyond this loop:

| | |
|---|---|
| ⛔ **`TFM` for the copy registers** | ⚠ **no use here**, unchanged. `TFM` streams to one address or an incrementing one; a copy's registers are neither |
| ⭐ **`TFM` to `VDATA`** | a different question and a real one — `optimizations.md` §9: 3 cycles a byte against `vidcore`'s 16. It is now runnable, and ⭐ **`TFM`'s interrupt behaviour is decided** (`hardware/cpu/docs/plan.md` §4.3.1, option C: the byte completes before the interrupt, so nothing is lost against a side-effecting port) |
| ⭐ **`-DH6309=1`**, unrelated to text | the kernel's own 6309 paths stop being compiled out. ⭐ **`CPU=6309` now implies it** (`hardware/cpu/docs/6309.md` §4.3); the two used to be separate knobs and setting one alone compiled every `ifne H6309` out silently |

⛔ **What still cannot run it is everything else.** `machine3.v` instantiates an
`mc6809e`, and `hardware/cpu/`'s own core has no decoder. So a 6309 measurement is a
*host-emulator* measurement — which is where every number in §1.3 came from too,
so it is the right instrument for this document and the wrong one for `boot.asm`.

---

## 9. ⚠ What to measure, before any of this is built

`boot-and-desktop.md` §5 item 8 ends by refusing to build on a subtraction, and
it is right; this document is a longer subtraction than that one was. The
measurements, in the order they decide something:

1. ⭐ **The three-way `TextAt` split that `boot-and-desktop.md` already
   specifies** — `GRow`+fill, `BlitRow`, and `FontAgain` marked separately at
   `$FF2E` inside one call. It is owed to that document and it prices §4's
   *build* cost, which is the strike plan's one soft number (§4.3).
2. ⭐⭐ ~~**One glyph, blitted.**~~ ⭐ **DONE 2026-09-22 — and it was the whole
   document in one number, exactly as this item claimed.** `run-v3text.sh`'s
   `v3tlow` draws the line out of the strike: **33.42 ms, 769 µs a glyph**.
   It settled §2's correction (the direction is right, 6.7×) and it **overturned
   §6's serialization** (the engine is 2 % of a glyph, not half of it). §6.1.
   ⚠ **The remaining open half is the one this item did not think to name**: what
   the 1,244 µs between the six stores and the engine's 29 is *made of*.
   ⭐ The instrument for that exists — `TRACE_AT`/`TRACE` with `module_of()`
   (`CLAUDE.md`, "Debugging by hypothesis") resolves a PC histogram to a module,
   so the answer is a run rather than an argument.
3. **A strike's worth of pixels compared.** `run-v3text.sh` already draws a line
   two ways into two bands and compares VRAM — *"0 of 5,712 bytes differ"*. ⭐ A
   strike must pass exactly that gate against the software path, per ramp.
4. **The tab, flattened** (§4.4) — `RPaper`'s `255` becomes an index, `F.Opaq`
   starts working on the most-drawn text in the GUI, and the benches that read
   the tab pixel by pixel move. ⭐ **This is measurable today and needs nothing
   else in this document.**
5. Only then §7 item 1, and only then a fit.
6. ⚠ **Native mode, once `hd6309.c` applies it.** §8's 6309 figures are
   emulation-mode and therefore a floor; `hd6309_nm_delta[]` is generated from
   Appendix A and not yet used. Until it is, "the 6309 is worth 1.11× here" is an
   understatement of unknown size and should not be quoted as the final word.

---

## 10. What would have to be true

- [ ] A per-glyph copy really costs ~87 µs or less in a process that owns the
      card — **`monster`'s figure, borrowed, not re-measured here.** Everything
      in §2 rests on it.
- [x] ⭐ **§5.3's loop is measured**: 60.42 cycles, not the 56 estimated
      (`test/glyphloop.asm`, 2026-09-21).
- [ ] It survives contact with a real `TextAt` — the list build, the clip and the
      byte-swapped pen are outside the measured loop and are still estimated.
- [ ] ⚠ **§8's 6309 figures are re-taken in native mode.** They are
      emulation-mode today and so are a floor.
- [ ] The margin is available. ⚠ **Paint's document is already in it**, and a
      screen that uses `HSCROLL` would scroll the font into view (§4.2).
- [ ] The strike's pixels are bit-identical to the software path's, per ramp
      (§9.3). ⛔ If they are not, the ramp indices or `GRow`'s 4-pixel overrun are
      wrong, and the overrun is real: `GRow` writes four pixels whole and a glyph
      whose width is not a multiple of four spills up to three pixels into its
      neighbour. **In `TB.Buf` the neighbour overwrites it; in a strike it does
      not.** ⚠ This is the single most likely way the strike draws different
      pixels, and §9.3 is what catches it.
- [ ] `CHEIGHT` is reloaded every copy. ⛔ The **emulator does not model this**
      (`machine.c:445` treats it as sticky, `v3ptr.cpld.ts:243` does not) — so a
      strike blitter developed against the host emulator can omit the store, pass,
      and run 512-row copies on silicon. `v3card_tb.sv:562-565` is the record of
      that trap being paid for once already.
- [ ] Any register-map change is **fitted**, read out of the new `.fit` against
      `v3ptr`'s existing 3 cascades and 124 cells, and refused under a second
      file name before "it does not fit" is believed.
