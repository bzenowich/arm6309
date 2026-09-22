# CoArm is full — the overlay, and the part of it that is not obvious

⚠ **A DESIGN, NOT A BUILD.** Nothing here is implemented. Written 2026-09-21,
when `RowCopy` — 224 bytes to let the ROM toolbox reach the copy engine
(`docs/proportional-font.md` §4) — took CoArm from 16,384 bytes to 16,608 and
the build refused it.

---

## 0. The wall, measured

| | | |
|---|---|---|
| ⛔ **CoArm code** | **16,384 of 16,384** | **zero free** |
| CoArm globals (`CG.Size`) | 12,125 of 16,384 | 4,259 free — ⛔ but not a whole block |
| toolbox code (ROM page 64) | 2,703 of 8,192 | 5,489 free |
| toolbox RAM (`CG.LBuf`, borrowed) | 786 of 1,024 | 236 free |

`recipes/arm6309/arm6309.mak:280` is the guard:

> `FAIL coarm is more than the two blocks ArmIO maps it in (defs/armvid.d Co.Code)`

`demo-report.md` §910 already said it: *"any of CoArm's 16 KB window, which has
one byte free."* This is that, one feature later.

### 0.1 ⛔ Two things that look like room and are not

**The data window.** `Co.DBlks` is 2 — 16 KB — for 12,125 bytes of globals, so
4 KB sits unused. It cannot be donated: a slot is 8 KB and the globals need
1.48 of them. ⚠ **`armvid.d`'s note contradicts itself on this point** and one
half is wrong:

> ⭐ video3 moves ONE BLOCK FROM DATA TO CODE … **The globals measure well under
> one block** — the assert at the end of `coarm.asm` is what checks that
> ⛔ AND THERE IS NO THIRD CODE BLOCK TO BE HAD … **the globals measure over 8 K
> so data cannot give one up**

The second is true. The first is left over from a plan that was not taken, and
it is worth deleting before it is believed: `CG.Size` is 12,125, and the three
arrays are where it goes — `CG.Scr` 8 × 532 = 4,256, `CG.Win` 32 × 140 = 4,480,
`CG.GPB` 48 × 12 = 576. ⚠ A grep of the numeric `RMB` lines answers **2,813**
and misses all three, which is exactly how this was nearly got wrong twice in
one afternoon. `boot.asm` is the check that caught it: it records
`TB = CoG + CG.LBuf = $8A4C`, an offset of 10,828, which cannot be inside one
8 KB block.

**⭐ And a third code block is already WIRED — it is just never selected.**
`armio.asm`'s map builder has

```asm
        IFGT      Co.CBlks-2
        ldd       4,y       video3: a third, for the CP437 font
        std       VG.CoImg+6,u
        ENDC
```

and lays the data blocks at `VG.CoImg+2+2*Co.CBlks`. The path was written for
video3's CP437 font, the 2 KB came out of `ca_v3txt.asm` instead, and
`Co.CBlks` stayed 2. It is a `check:reach` finding in software — a capability
built and nothing selecting it — and **the overlay wants the same machinery**,
so it is where this starts rather than something to delete.

---

## 1. The map, and why the overlay has to be a code slot

Eight slots of 8 KB (`armvid.d` §Co.*):

| slot | | |
|---|---|---|
| 0 | `$0000` | block 0 — the stack at `Co.Stack`, the kernel's |
| 1–2 | **`$2000`** | ⛔ **CoArm's code, `Co.CBlks` = 2** |
| 3–4 | `$6000` | CoArm's globals, `Co.DBlks` = 2 |
| 5 | `$A000` | `Co.WinA` — sources: the toolbox's ROM page, GP buffers |
| 6 | `$C000` | `Co.WinB` — screen stores, the font page |
| 7 | `$E000` | the kernel and the I/O page |

⛔ **There is no free slot**, so the overlay window has to be a slot that is
already CoArm's. `Co.WinA` and `Co.WinB` are both contended — `tbox.asm`'s own
header records that *"the row layer maps a screen's STORE at `Co.WinB`, so every
routine here maps it again"*, and `keyed-copy.md` §4 item 2 killed a proposal
outright because *"there is no second block window for a table"*. That leaves a
**code** slot, which is the classic answer anyway.

**So: slot 1 (`$2000`–`$3FFF`) stays resident and slot 2 (`$4000`–`$5FFF`)
becomes the bank window.**

⭐ **The mechanism already exists and costs about twenty bytes.** `ca_row.asm`'s
`MapA`/`MapB` are the model:

```asm
MapB    cmpd  >CoG+CG.WinB      already there?
        beq   x@
        std   >CoG+CG.WinB      the cache
        std   VG.CoImg+12,y     the image, for the next time task 1 is loaded
        pshs  cc
        orcc  #IntMasks
        stb   >DAT.Regs+8+6     and the map, now
        adda  #RAM.Hi
        sta   >DAT.RegsHi+8+6
        puls  cc
x@      rts
```

`MapOv` is that against slot 2 — `VG.CoImg+4`, `DAT.Regs+8+2`. ⚠ Updating the
image as well as the register is not optional: task 1 is reloaded, and a bank
that is only in the MMU is gone the next time it is.

---

## 2. The cut

Per-file object sizes, read out of the listing (`--list`, addresses bucketed by
source):

| | bytes | |
|---|---|---|
| `ca_ext.asm` | **2,502** | `PatBar`, `PutMask`, `Icon`, `Poly`, `Image`, `AnsiSw` — `nitros9-av-plan.md` P3 |
| `ca_draw.asm` | 2,475 | lines, circles, fills |
| `ca_scr.asm` | 2,228 | screen alloc, switch, store ↔ card |
| `ca_v3txt.asm` | 1,683 | ⭐ the console — **hot** |
| `ca_bmtx.asm` | 1,307 | bitmap text |
| `ca_gpb.asm` | **1,233** | GP buffers |
| `coarmfont.asm` | 1,016 | the 8×8 font — data, not code |
| `ca_row.asm` | 946 | ⭐ the bottleneck row layer — **hot** |
| `vidcore.asm` | 725 | ⭐ the card — **hot** |
| `ca_tile.asm` | 477 | tile screens |
| `vidptr3.asm` | 329 | ⭐ the pointer — **hot, and runs from an IRQ** |
| `ca_ptr.asm` | 293 | ⭐ **hot, IRQ** |
| `ca_tbox.asm` | 164 | the toolbox escape |
| `coarm.asm` itself | ~1,200 | ⭐ the dispatcher — **must be resident** |

⭐ **The hot set is small**: dispatcher + `vidcore` + `ca_row` + `ca_v3txt` +
`ca_ptr` + `vidptr3` + `ca_tbox` ≈ **5,140 bytes**, comfortably inside one 8 KB
resident slot with ~3 KB for the thunk table and growth.

⭐ **The cold set is 10,238** and does not fit one bank, so it is two:
`ca_ext` + `ca_gpb` + `ca_tile` + `coarmfont` ≈ 5,228, and `ca_draw` + `ca_scr`
+ `ca_bmtx` ≈ 6,010.

⚠ **`ca_scr` is the awkward one.** Screen switching is called from the
dispatcher and calls the row layer; it is cold by frequency and central by
position. It goes in a bank, and §4's rule about re-entry is mostly about it.

---

## 3. ⛔ The crux is the BUILD, not the mapping

The mapping is twenty bytes. The problem is that **an OS-9 module is one
contiguous image** and an overlay needs N chunks that all *run* at `$4000` and
are *stored* end to end.

What that forces:

1. Each bank is `org $4000`, assembled independently, **padded to exactly
   8,192 bytes**, and concatenated after the resident 8 KB.
2. ⛔ **The assembler will not resolve a symbol across two chunks with the same
   origin**, so every call out of the resident half into a bank, and every call
   between banks, goes through a **thunk table at a fixed address in the
   resident half**. That table is the module's real interface, and it has to be
   generated rather than hand-kept — the same argument `regmap.ts` makes for the
   register window.
3. The module header's size and CRC must cover the whole image. `os9 module`'s
   accounting has to be checked, not assumed.
4. `armio.asm` must read **N+1** block numbers out of `MD$MPDAT` and keep the
   bank list (the `IFGT Co.CBlks-2` arm is the start of this, but it stores into
   `VG.CoImg`, which is slot images; banks need their own array — `VG.CoOv`).

⚠ **This is the part that makes the overlay a day rather than an afternoon**,
and it is the part that should be prototyped first: a two-bank CoArm that does
nothing but prove a call reaches a bank and returns.

---

## 4. ⚠ The hazards, each of which has a cheap rule

| | rule |
|---|---|
| ⛔ **An IRQ during a bank call** — `ca_ptr`/`vidptr3` run from the pointer interrupt and would run against whatever bank happens to be mapped | ⭐ **Keep every IRQ path resident.** They are 622 bytes together and they are already in the hot set. Then no handler ever needs a bank and nothing has to be saved |
| **Re-entry**: a bank routine calls the dispatcher, which calls another bank | ⭐ The thunk **saves the current bank on the stack and restores it on return**. Six bytes a thunk, and it makes the banks re-entrant without anyone thinking about it |
| **Task 1 reload** loses a bank set only in the MMU | `MapOv` writes `VG.CoImg+4` as `MapA`/`MapB` write `+10`/`+12`. Not optional |
| ⛔ **A bank routine that falls through to the next routine** — fine today, wrong when the next routine is in another bank | The cut is at file boundaries and each bank ends in padding, so a fall-through runs into `$00`s rather than into plausible code. ⚠ Worth an explicit trap byte instead: `SWI3` or an illegal opcode, so it stops rather than drifts |
| **`CG.WinA`/`CG.WinB` caching** is a compare-before-write; the same for the bank | One byte in `CG.*`, and ⚠ it must be **invalidated when task 1 is reloaded**, or the cache says a bank is mapped that is not |

---

## 5. What it is worth, and the honest alternative

⭐ **The overlay buys 8 KB now and a second 8 KB when a third bank is added**,
against 224 bytes needed today. It is the only option that does not have to be
revisited.

⛔ **And the alternative is much cheaper for today's problem.** `RowCopy` is
called from the toolbox, the toolbox has **5,489 bytes free**, and `TbVec`
entries are already entered with `Y = VG` — so the toolbox has the video globals
and could drive `$FF60` itself, with `CG.TTop` for the ring. Zero CoArm growth.

⚠ What that costs is the layering: `ca_row.asm` is the single bottleneck routine
that `video-copyrect.md` §5.2 recommends keeping, and putting card access
outside it is the thing that section warns against. **It is a real cost and it
is not a large one** — one routine, in a module that already maps and reads the
card's own font pages.

⭐ **The two are not exclusive.** Putting `RowCopy` in the toolbox unblocks
`proportional-font.md` §4 this week; the overlay is what stops the next 224
bytes being a crisis. If both are done, the overlay is not on anyone's critical
path while it is built, which is the condition under which this kind of change
goes well.

---

## 6. The order

1. ⭐ **Correct `armvid.d`'s note** — one of its two sentences about the globals
   is wrong and it is the one someone will act on (§0.1).
2. ⭐ **A two-bank prototype that proves nothing but the call**: resident stub,
   one bank with one routine, a thunk, `MapOv`, and a bench that calls it. ⛔ The
   build layout is the risk and it is the whole of this step.
3. `armio.asm` reads the bank list into `VG.CoOv`.
4. Move `ca_ext` + `ca_gpb` + `ca_tile` into bank 1. **Nothing else.** Gate on
   `run-v3desk.sh`, `run-v3files.sh` and the demo.
5. Only then bank 2, and only if it is needed.

⚠ **And the gate is the existing benches, not a new one.** `run-v3files.sh` is
65 claims that draw a window, list a directory and read the glyphs off the
pixels; `run-v3desk.sh` is 48 that drive a menu. Between them they exercise the
row layer, the console, the pointer, the toolbox and the screen switch — which
is most of the cut.
