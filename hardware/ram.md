# The Memory System

## 32 MB of Map, 16 MB of DRAM, 1 MB of ROM, and the Three Ceilings That Are Not the Same Height

**Question this answers:** what is on the motherboard between the CPU socket and the
slots, and why. That is the MMU's address path, four SIMM sockets of DRAM, and the boot
ROM — **the whole of the machine's memory**, because since 2026-09-08 there is no
memory on a card except the video ring, the audio card's samples and the card buffers.

> Superseded material is archived in [history.md](history.md); this document describes
> only the present design.

**Status: ⭐ decided 2026-09-08 for the memory system; brainstorm for the rest.**
§5, §6 and §6.7 are decisions — the physical map is re-carved, the memory is four
30-pin SIMM sockets, and the boot ROM is on the board. §3's map widening comes with
them because it has to (§5.1). §§2.1, 4 and 9 are still options. Every option is priced
against the parts on
[`mainboard/mainboard.circuit.tsx`](mainboard/mainboard.circuit.tsx), which
⚠ **still draws the nine-IC board this document superseded** — the board file is behind
the decisions and `hardware/README.md` open item 3 is where that is tracked.

> **The short answer.** The address path to 32 MB costs **one SRAM and one GAL
> output** — it is nearly free, because the MMU was built with 128× more map
> storage than it uses, and it needs **no backplane pins at all** because
> `/IOPAGE` already does the work (§5.3). The *memory* costs a DRAM controller and
> a SIMM bank, which is where the real work is. And the **operating system tops out
> around 2 MB**, which is why §10 says build the address path, populate 2 MB, and
> treat the rest as unmanaged store.

---

## 0. Three ceilings, and only the third one is still binding

Conflating these is how "how much RAM can it take?" gets a wrong answer.

| Ceiling | Where it was | **Where it is** | What moved it |
|---|---|---|---|
| **Physical address** | 2 MB — 8-bit map entries, `A20..A13` | ⭐ **32 MB** — 16-bit entries, `A24..A13` | §3 — one SRAM and a GAL output |
| **Parts** | 512 KB in one DIP-32 | ⭐ **4–16 MB in four SIMM sockets** | §6 — DRAM, and the refresh owner the machine finally has |
| **⚠ Operating system** | **512 KB native, ~2 MB patched** | **unchanged, and it is now the binding one** | §9 — NitrOS-9's memory manager, and nobody has done it |

**The three are independent and the smallest one is the OS.** The first two are
decided; be honest that the third is what decides how much of it NitrOS-9 will ever
hand to a process.

---

## 1. Where the machine is

From [`gal/README.md`](gal/README.md), `docs/machine.md` §6.3.1, §7.1 and §7.2, and
§§3, 5, 6 and 6.7 below:

| | |
|---|---|
| Logical space | 64 KB, **eight 8 KB blocks** |
| Map entry | **16 bits**, of which **12 are physical `A24..A13`** — 4096 blocks, **32 MB** (§3.1) |
| Map store | **two `CY7C128A`, 2K×8**, read in parallel — **16 of 2048 words used** (§3.2) |
| Index | `{TASK, block}` — ⚠ `TASK` is **one bit** on the board as drawn; §3.2 widens it to 8 for zero parts and that is step 0 of §10 |
| Registers | `$FFA0`–`$FFAF` sixteen entries; `$FFB0` `TASK`, `$FFB1` `BOOT` (`machine.md` §3, §7.2) |
| **System RAM** | **four 30-pin SIMM sockets, 4–16 MB of DRAM**, at physical **4–20 MB** (§6) |
| **Boot ROM** | **1 MB**, read-only, at physical **2.0–3.0 MB** (§6.7) |
| **SRAM on the motherboard** | **none but the map's own two** (§6.2) |
| Physical map | §5.2 — VRAM, card buffers, ROM and four SIMM windows in a 32 MB space |

**This started as the GIME's architecture with the third-party 2 MB upgrade already
applied**, and it is not that any more. A stock GIME uses 6 of its 8 entry bits — 64
blocks, 512 KB — and the CoCo 3 community's 2 MB boards spend the two spare bits. This
machine spent the eighth on `A20` on 2026-09-08 and then **stopped being 8-bit
entries at all**, because §5.1 showed the SIMM sockets could not be addressed
otherwise.

⚠ **The one thing the widening did not buy is an operating system that can use it** —
§9, and it is the ceiling §0 says is now the binding one.

---

## 2. What 16 MB actually requires

16 MB in 8 KB blocks is 2048 blocks, so **11 bits per map entry** — `A23..A13`.
Eleven bits do not fit in a byte, and that single fact drives everything below.

| Target | Entry bits | Blocks | Entry size |
|---|---|---|---|
| 512 KB | 6 | 64 | 1 byte |
| 2 MB — what this machine had until 2026-09-08 | 8 | 256 | 1 byte |
| 4 MB | 9 | 512 | 2 bytes |
| 8 MB | 10 | 1024 | 2 bytes |
| 16 MB | 11 | 2048 | 2 bytes |
| **32 MB — taken, §5.2** | **12** | **4096** | **2 bytes** |

**Two bytes per entry buys 32 MB as easily as 16**, and §5.2 spends the extra
bit: four 4 MB SIMMs is 16 MB of DRAM, which does not fit a 16 MB map alongside
2 MB of SRAM, VRAM and the card regions. **`A24` costs one more wire on the
motherboard and nothing else**, so the map is 32 MB and the four remaining
entry bits are §3.3's.

### 2.1 ⚠ Why a bank register is the wrong shape, and it is worth being precise

The obvious cheap answer — **a 16-bit bank register supplying the high address
bits** — is one `74HC574` pair and no map changes. It is also wrong for this
machine, and the reason is not subtle:

**A bank register is global; the map is per block.** With eight blocks sharing
one set of high bits, a process cannot hold pages from two different megabytes
at once — which is exactly what a paged OS does on every `fork`, every shared
library and every I/O buffer that lives outside the process. NitrOS-9's memory
manager allocates *arbitrary* physical blocks and maps them wherever it likes;
a bank register makes that illegal.

**It is the right answer for a different question.** If the goal were a large
unmanaged store — a RAM disk, a sample bank, a frame buffer pool — a bank
register over a single 8 KB window is cheap, obvious and enough. §9 is where
that comes back, because it is what >2 MB is realistically *for*.

---

## 3. The address path — one SRAM and one GAL output (no backplane pins, §5.3)

### 3.1 The change

**Widen the map entry to 16 bits by putting a second `CY7C128A` beside the
first**, read in parallel. The low byte drives `A20..A13` as it does now; the
high byte drives `A23..A21` and five flags.

| | Cost |
|---|---|
| Second `CY7C128A` map SRAM | **+1 IC** |
| High-byte write strobe | **+1 output on U3** — and pin 23 is deliberately free (`mmu.pld`) |
| `A21`–`A24` to the backplane | **0** — §5.3 keeps them on the motherboard and pulls `/IOPAGE` instead |
| Isolation `'245` | **0** — both SRAMs sit on the same `D0`–`D7`; the address picks which is written |
| Address mux `'157` | **0** — §3.2 |
| **Address path alone** | **9 ICs → 10** — §8 has the whole motherboard at 17 |

**Both bytes must be read in the same access**, which is why this is two
byte-wide parts and not one wider one: translation needs `A23..A13`
simultaneously, and a single SRAM read sequentially would double the map
latency inside a 110 ns `t_AD` budget that has 15 ns of SRAM in it already.

### 3.2 ⭐ And the map store is already 128× larger than the design uses

`gal/README.md` records it without drawing the conclusion: *"Sixteen 8-bit
block registers is the whole 2 KB SRAM's useful content — **16 of 2048**."*

**2048 locations is exactly 256 tasks × 8 blocks.** And the register that holds
`TASK` is a `74HC574` with **one bit used and seven wired to nothing** —
`mainboard.circuit.tsx` `noConnect={["Q2".."Q8"]}`.

So widening `TASK` from 1 bit to 8 costs **zero parts**:

| | Today | Widened |
|---|---|---|
| `TASK` | 1 bit of a `'574` | **8 bits of the same `'574`** |
| Map index | `{TASK, block}` = 4 lines | `{TASK[7:0], block[2:0]}` = **11 lines** |
| Map SRAM addressing | `A0`–`A3` of 11 | **`A0`–`A10`, all of them** |
| Contexts | **2** | **256** |
| `'157` mux | 4 bits, 4 used | 4 bits, **3 used** — only `block[2:0]` is muxed; `TASK` comes from the register and needs no mux |

⭐ **What that is worth is not memory, it is context switches.** Today a
NitrOS-9 process switch rewrites eight map entries. With 256 contexts resident
it is **one write to `TASK`** — the same trick the 6809's `DP` register plays
at a smaller scale, and it takes the switch from eight bus cycles to one.

**This is independent of the 16 MB question and cheaper than it.** It could be
done today, on 8-bit entries, for nothing but the wiring and a NitrOS-9 change.

### 3.3 What the five spare bits buy

At 16 MB an entry is `A23..A13` in 11 bits, leaving five:

| Bit | Candidate | Why it is worth a bit |
|---|---|---|
| **write-protect** | `/WE` gated per block | text-segment protection, and catching a wild store *at the block that owns it* rather than three screens later |
| **valid** | unmapped block asserts nothing | reading an unmapped block returns open bus today (`machine.md` §2). A valid bit could drive a fault instead |
| **no-cache** | — | the machine has no cache; recorded as unused |
| 2 spare | 32 MB, if the map ever wants it | §2 |

**⚠ None of these is free in software.** A write-protect bit needs a fault path
the CPU module must implement, and `machine.md` §5 item 6's divergence ledger
grows by one for each. Reserve the bits; specify them later.

---

## 4. Where the registers go, and the compatibility trade

Two layouts, and they differ in what they give up.

### 4.1 Layout A — 8 blocks × 2 bytes in the existing 16

| Window | Contents |
|---|---|
| `$FFA0`–`$FFA7` | blocks 0–7, **low byte** — `A20..A13` |
| `$FFA8`–`$FFAF` | blocks 0–7, **high byte** — `A23..A21` + flags |
| `$FFB0` | **`TASK`, 8 bits** — one bit on the board as drawn, aliased 8× on even addresses; `$FFB1` is `BOOT` (`machine.md` §3, §7.2) |

**It fits the windows that exist, exactly, with no new I/O space** — and the
`$FFB0`–`$FFBF` alias that has been carrying one bit since the map was
specified finally earns its byte.

⚠ **What it costs is the last of the GIME's register layout.** On a CoCo 3,
`$FFA0`–`$FFA7` is task 0's eight blocks and `$FFA8`–`$FFAF` is task 1's — both
tasks visible at once, which is how the GIME's fast task switch works. Layout A
replaces task 1's window with the high bytes, so **only one task's map is
addressable at a time** and switching tasks to write a map becomes ordinary.
`machine.md` §5 item 6 gains an entry.

### 4.2 Layout B — high bytes in the control window

| Window | Contents |
|---|---|
| `$FFA0`–`$FFAF` | **unchanged** — two tasks × 8 blocks, low byte |
| `$FFB0` | control / `TASK` |
| `$FFB8`–`$FFBF` | high bytes for the **current** task's 8 blocks |

**Keeps the two-task layout and the GIME's shape**, at the cost of an
asymmetry: low bytes for both tasks are addressable, high bytes only for the
selected one. That is confusing in exactly the way that produces a bug at
3 a.m., and it forecloses §3.2's 256 contexts.

**Neither is obviously right.** Layout A is cleaner hardware and a bigger
divergence; Layout B is compatible and awkward. **The decision belongs to
whoever owns the NitrOS-9 port**, because it is a software-cost question
wearing a hardware costume.

---

## 5. ⭐ The re-carve — decided

### 5.1 Why populating the footprints forces the map wider

**Four × 512 KB is 2 MB, which is the entire `A0`–`A20` map.** There is no
arrangement of a 2 MB space that holds 2 MB of system RAM *and* the video ring
*and* the card regions. So:

> **The three reserved SRAM footprints cannot be populated at 8-bit map
> entries, at all, under any re-carve.** §3's second map SRAM is not an
> optional companion to filling them — it is a precondition.

That was not obvious when the footprints were reserved, and it is the single
most useful thing this document found.

### 5.2 The map

**12 of the 16 entry bits, `A24..A13` — a 32 MB space**, addressed in 512 KB quadrants
by `A24..A19`:

| `A24..A19` | Range | Contents | Status |
|---|---|---|---|
| `000000` | 0.0–0.5 M | **reserved** | nothing answers here |
| `000001` | 0.5–1.0 M | **VRAM** — the video ring | **unchanged** |
| `00001x` | 1.0–2.0 M | **card buffers — 16 regions of 64 KB** | **unchanged** |
| `00010x` | **2.0–3.0 M** | ⭐ **the boot ROM — 1 MB, read-only** | §6.7 |
| `00011x` | 3.0–4.0 M | reserved | |
| `001xxx`–`100xxx` | **4–20 M** | **four SIMM windows of 4 MB — all of system RAM** | §6 |
| `101xxx`–`111xxx` | 20–32 M | reserved | |

**Nothing that exists changes address.** VRAM keeps `A20:A19 = 01` and the card regions
keep `A20 = 1`, so **the video card is untouched and no card document is
re-specified.** The ROM went into the 2.0–4.0 MB block that was already reserved and
that nothing had asked for, which is why it cost no re-carving either.

⚠ **The bottom 0.5 MB is empty and stays empty.** It was reserved as "the natural home
for a boot scratch" while §6.4 was open; §6.7 closed that without needing any, so the
quadrant has no claimant. It is the obvious place for the next thing that needs a fixed
physical address, and there is no such thing today.

⭐ **And system RAM is not in the bottom 4 MB at all** — it is 4–20 MB, entirely on the
SIMMs. **Nothing cares**, because this is a block-mapped machine: physical addresses are
invisible to software except through the MMU, and the memory manager allocates blocks
rather than ranges.

### 5.3 ⭐ And no card needs `A21` and above — `/IOPAGE` already does the work

The obvious problem with a map above 2 MB is that **cards decode only
`A0`–`A20`**, so an access at 2.5 MB looks to a card exactly like one at
0.5 MB. Giving every card `A21`–`A24` is four backplane pins the slot does not
have — and `vctrl` sits at **64 of 64 I/O** (`gal/cpld/vctrl.fit`), with no
room for four more inputs.

**It does not have to.** `machine.md` §2 already requires every physical decode
on every card to qualify against `/IOPAGE`, and `/IOPAGE` is **open-drain**. So
the motherboard's new decode GAL simply **pulls `/IOPAGE` low for any access
above the bottom 2 MB**, and every card goes silent for free:

| | |
|---|---|
| Card changes | **none** |
| New backplane pins | **none** |
| Cost | one open-drain output on a GAL that has to exist anyway (§6.2) |

**`/IOPAGE` stops meaning "the `$FFxx` page" and starts meaning "cards must not
respond".** It already meant the second thing; the first was just the only
reason it had to. ⚠ **That is a redefinition and it belongs in
`machine.md` §2**, because a card author reading the old sentence would get it
wrong.

---

## 6. ⭐ The memory — four 30-pin SIMM sockets, decided

**512K×8 in a DIP-32 is the ceiling for through-hole SRAM.** 16 MB is
**32 packages**, which is not a motherboard — [`place/`](place/) already puts
the board at 272 × 224 mm and most of that is slot field.

| Approach | 16 MB costs | Verdict |
|---|---|---|
| DIP SRAM, `AS6C4008` | **32 packages**, ~1,300 cm² | not a board |
| SMD SRAM | 4–8 packages | ⚠ no sourced part number — §11 |
| **30-pin SIMM, DRAM** | **four sockets and four ICs** | **taken** |
| 72-pin SIMM | one socket | 32 bits wide; three quarters of the data path wasted or muxed |

### 6.1 Why the DRAM objection expired

`machine.md` §7.1 rejected DRAM on exactly one ground:

> SRAM rather than DRAM because **DRAM needs a refresh owner and this machine
> has none**.

⭐ **That ground is gone.** `machine.md` §5 item 8 (2026-09-08) gives the E/Q
divider a `/WAIT` hold, so a controller can stall the CPU mid-cycle — which is
precisely what a refresh needs.

### 6.2 ⭐ And the DIP SRAM goes away entirely

**Decided 2026-09-08, after the SIMM sockets.** `place/` reserved four `AS6C4008`
footprints and §5.1 showed they could not be populated without a wider map. Once the map
*is* wider and there are SIMM sockets on the board, **the four DIP SRAMs have no job
left**: 2 MB of SRAM against 4–16 MB of DRAM in four sockets, for four packages and
~120 cm² of a board that is mostly slot field.

| | |
|---|---|
| Reserved footprints | **removed** — `place/svg.ts` |
| Motherboard | **18 → 14 ICs**, and the board shrinks with them (§6.7 puts three back) |
| The `74HC139` the footprints needed | never built; U9 does the space decode |

**What it cost was the boot path, for one day** — §6.4, closed by §6.7.

### 6.3 What the bank costs

| | Part | Role |
|---|---|---|
| 4 | **30-pin SIMM socket** | ×8 or ×9, 1 MB or **4 MB** each — **4 to 16 MB** |
| 1 | **`GAL22V10` U9** | space decode: the four SIMM windows, and §5.3's open-drain `/IOPAGE` pull |
| 1 | **`GAL22V10` U10** | SIMM timing — `RAS0`–`RAS3`, `CAS`, `/WE`, the mux select, refresh request and `/WAIT` |
| 3 | **`74HC157`** | RAS/CAS address mux, 11 bits — **row is physical `A10`–`A0`, column `A21`–`A11`**, and the select is `E` itself rather than a GAL output (§6.3.1) |
| **1** | **`74HC4040`** | ⚠ **the refresh timebase, and it was on nobody's list** — §6.3.1 |
| **+6 ICs and 4 sockets** | | **all** of the machine's memory, against 32 packages for 16 MB of SRAM |

⭐ **Refresh needs no ROW counter.** **CAS-before-RAS** makes the DRAM generate its own
row address, so the refresh row counter a 1980s design would have carried — a `74HC4040`
**and its mux path** — is not needed for that job.

> ⚠ **And that sentence hid a package for a day.** It used to end "…is **not on this
> list**", which is true of the *row* counter and false of the **interval** timer. They
> are different things: one supplies an address, the other says *when*. 15.6 µs of
> `CLK25` is 393 counts — **nine macrocells on a part that has ten** — so the interval
> cannot live on U10 and cannot come from anything else already on the board. It is a
> `74HC4040` after all, doing the other job. §6.3.1.

### 6.3.1 ⭐ U10 is fitted, and it moved three things

> **2026-09-09.** [`gal/u10.pld`](gal/u10.pld), [`gal/u10.jedec.ts`](gal/u10.jedec.ts)
> and [`gal/u10.model.ts`](gal/u10.model.ts). `npm run check:jedec` steps the fuses and
> the model together over **1,920 clock edges** — every bus phase, DRAM cycle and not,
> both `R/W` directions, across many refresh bursts — and `npm run check:cupl` runs
> **Atmel's own CUPL output** through the same sweep. It fits at **9 macrocells of 10**,
> 11 inputs, two spare pins, widest equation five terms.

§11 item 6 said this part *"has not been counted at all"*. Counting it moved three
things, and only one of them was a cost:

| | |
|---|---|
| ⭐ **The mux select is `E`** | and not an output. `E` is high for counts 6–11 of U6's divider, which is **exactly** the column window, so the three `'157` take a wire from the backplane. **That is the macrocell that made a nine-output design fit** — and it is what a 1970s DRAM controller on a 6800-family bus would have done anyway |
| ⭐ **`/WAIT` is not needed** | §6.3's line item lists it. A bus cycle is twelve `CLK25` counts, the access owns six of them, and a refresh burst is four — **so it fits in the gap and the DRAM controller never stalls the CPU.** ⚠ §6.6's "well under 1 % of the bus" is now **zero bus cycles**, and the thing it was worried about does not exist |
| ⚠ **The refresh timebase is a package** | above. +1 IC, and the motherboard is **18** |

#### The cycle, in counts of 39.7 ns from E-fall

| count | | why |
|---|---|---|
| 0–2 | address not yet valid | the 6809's `t_AD` is 110 ns, which is count 2.77 |
| **4** | **`/RAS` falls** | 158.8 ns — **48.8 ns of row-address setup** |
| **6** | `E` rises: the `'157` switch to the column half | 79 ns of row hold after `/RAS` |
| **7** | **`/CAS` falls** | 40 ns of column setup — and **49 ns of write-data setup**, because 6809 write data is valid at 229 ns |
| **10** | both released | **238 ns of `t_RAS`**, and 238 ns of precharge before the next |

**`/WE` leads `/CAS` by three counts — an early write**, so the module takes its data at
`/CAS`-fall and never drives `D0`–`D7` at all. A late write would put the SIMM's output
on the bus during a write cycle, which is the contention `gal/README.md` argues about for
the system RAM's `/OE`.

#### ⭐ Two timebases, and that is the whole design

| | derived from | why |
|---|---|---|
| **the access** | **U6's counter `C3..C0`** | host-facing, so it *should* stall when `E` stalls — a stalled bus cycle is one whose data is not wanted yet |
| **the refresh** | **`CLK25`, through U17** | ⚠ it must not touch that counter. `/WAIT` holds U6's divider (`machine.md` §5 item 8), so a refresh timed from the bus **would stop dead for the 40.7 µs the video card can hold it** — 2.6 refresh intervals, and the DRAM forgets |

**`machine.md` §5 item 10 is the rule and this is the part it was written for.** §6.6
asserts that refresh and the video stall never contend; the mechanism is that a stalled
cycle is a VRAM *write*, so `DRAMSEL` is low — and a burst may start at **any** count when
the cycle is not a DRAM cycle. During a stall, refresh runs freely.

When the CPU *is* using the DRAM, a burst may start only at **count 10 or 11**: it takes
four counts and must finish, with precharge, before the access's `/RAS` falls at count 4.
Starting at count 0 would put its `/RAS` at counts 2–3 and leave **none**. A request waits
at most twelve counts — 476.7 ns — against 5.4 µs of slack, so **it cannot be starved.**

> ⚠ **The tightest number on the part: `/RAS` is low for two counts during a refresh —
> 79 ns.** `t_RAS` min is about 70 ns on a 70 ns module and about 60 on a 60 ns one, so
> the margin is 9 ns or 19. A third count needs a five-state sequencer and a third
> macrocell U10 has not got, **so it is a speed-grade requirement instead: buy 60 ns
> modules.** §11 item 7 now has two attributes to match, not one.

#### ⚠ And the mux mapping is for 4M × 8 modules only

Row is physical `A10`–`A0`, column `A21`–`A11`. A 30-pin SIMM is **byte-wide**, so its
`A0` is the CPU's `A0` — there is no low address bit hidden inside it the way there is on
a ×16 or ×32 module.

**A 1M × 8 module will not work in that mapping.** It has ten row and ten column bits and
ignores `MA10`, which drops physical `A10` out of the address entirely — so its megabyte
would be neither contiguous nor unaliased. The correct 1 MB mapping is row `A9`–`A0`,
column `A19`–`A10`, and the two differ in **which physical lines feed the `'157` B
inputs**: it is a rewire, not a jumper, so it is a build-time choice.

⚠ **§11 item 7 recommends 1 MB modules on availability grounds and was written without
this in view.** Either the board is wired for the size that is bought, or three more
`'157` buy the choice at run time.

### 6.4 ⭐ The boot path — stackless, and shorter than it sounds

**With no SRAM, the machine has no writable memory at all until the DRAM controller is
up.** It *executes* from the moment `/RESET` releases — `machine.md` §7.2's `BOOT` mode
puts the boot ROM's first 8 KB behind every logical block — but **the first `JSR` needs
a stack**, and there is nowhere to put one.

**The answer is that the sequence that fixes it contains no `JSR`.** In full:

```
        ; RUN = 0 out of reset: boot mode.  Every logical block reads ROM
        ; page 0.  No RAM, no stack, no subroutine calls in this block.
        clra
        sta   $FFB0               ; TASK := 0 - and $FFB0 is EVEN, so it does
                                  ; NOT leave boot mode
        lda   #$xx                ; physical page holding the ROM's own page 0
        sta   $FFA0               ; ... one store per block, sixteen of them
        ...
        sta   $FFB1               ; RUN := 1.  The map takes over.
        lds   #stacktop           ; the first SIMM answers; ordinary code
```

Eighteen stores and an `LDS`. **Refresh needs nothing at all**, because U10's refresh
timer free-runs off `CLK25` from reset — `machine.md` §5 item 10's rule requires that of
it independently, so it is not a favour asked of the DRAM controller but a property it
has to have anyway.

⭐ **`TASK` first, then the map, then `$FFB1` — and the address parity is what allows
that order.** The map index is `{TASK, block}`, so writing sixteen entries before `TASK`
is set puts them under whatever the `'574` powered up holding. A control window that left
boot mode on *any* write would have made the correct order impossible; one literal on
`A0` splits `$FFB0` (TASK) from `$FFB1` (the strobe). `gal/clkdec.pld`.

⚠ **The one real constraint is that the block the code is executing from must survive the
last store.** Point one map entry at physical 2.0 MB — the same ROM page 0 the code is
already running out of — and setting `RUN` does not move the instruction stream. That is a
rule about the boot code, not about the hardware, and it belongs in the ROM's source next
to the sequence above.

> **What was proposed instead, and is withdrawn.** Until §6.7 the recommendation was
> that the CPU module serve 2 KB of its own SRAM as a logical window — zero ICs, and it
> paralleled the shadow ROM exactly. **It is not needed, and it was the last thing
> keeping boot inside the CPU module.** Archived in [history.md](history.md).

### 6.5 The motherboard, assembled

| | ICs |
|---|---|
| the board as drawn in `mainboard.circuit.tsx` | 9 |
| − the DIP system RAM, removed (§6.2) | −1 |
| + second map SRAM, 16-bit entries (§3.1) | +1 |
| + U9 space decode, U10 SIMM timing, 3 × `'157`, U17 refresh timebase | +6 |
| + **the boot ROM: 2 × `SST39SF040` and the `'244`** (§6.7) | **+3** |
| **total** | **18 ICs + 4 SIMM sockets** |

⚠ **`mainboard.circuit.tsx` still draws the nine.** The board file is a schematic of the
state before §3.1, §6.2 and §6.7, and closing that gap is `hardware/README.md` open
item 3 — it is a drawing job, not a design one.

### 6.6 ⭐ Refresh against stretched cycles — settled

This was the open question and `graphics.md` §7.4 closed it on 2026-09-08.

**The video card's `/WAIT` is `SPANBUSY · VRAMSEL · /IOPAGE · E · write`**
(`gal/access.jedec.ts`) — it is asserted only when the CPU is **writing VRAM**; reads
never wait. The bound is **40.7 µs**, a 256-byte span-solid at one retired byte per
158.9 ns fetch slot.

⭐ **Refresh and the video stall never contend.** During those 40.7 µs the CPU is stalled
*on VRAM*, so the DRAM bus is idle and U10's refresh runs off `CLK25` regardless of what
`E` is doing. **A maximal span is 2.6 refresh intervals of completely free DRAM time**,
which is better than neutral.

**What is left is smaller and it is a rule rather than a mechanism.** `machine.md` §5
item 10: *a card's internal realtime scheduling free-runs on `CLK25`; only host-facing
windows may be derived from `E`.* U10's refresh timer obeys it by construction — it has
no reason to count bus cycles — and the rule exists because the net card did count them
and would have lost 50 bytes of a frame per maximal span.

⚠ **What is still not measured** is refresh's own cost: a CAS-before-RAS burst every
15.6 µs is well under 1 % of the bus, and it is 1 % that `audio.md` §13's replayer budget
and `net.md` §3.4's dispatch arithmetic have never carried. **Small, and nobody has
subtracted it from anything.**

### 6.7 ⭐ The boot ROM — 1 MB on the motherboard, decided

`machine.md` §7.2 is the owning section and carries the reasoning; this is the part of
it that is a motherboard parts list.

| Qty | Part | Role |
|---|---|---|
| **2** | **`SST39SF040`** — 512K×8, 5 V, 70 ns, PDIP-32 | 1 MB at physical **2.0–3.0 MB**. Physical `A19` selects between them — one literal on U9 |
| **1** | **`74HCT244`** | drives physical `A20`–`A13` to zero while boot mode or the vector page has the map SRAMs deselected. ⭐ **A `'244` and not the `'541` §7.2 first named**: both are octal three-state buffers, and the `'244` has a datasheet in `reference/datasheets/` where the `'541` does not — so it is the one whose pin numbering is read rather than remembered. ⚠ **Eight bits, not seven**: `A20` reaches the backplane, and a floating `A20` during a boot fetch would let the video card's VRAM select answer at random

**What it needs from the logic on this board**, and none of it is a new part:

| Signal | Where | Cost |
|---|---|---|
| `RUN` — cleared by `/RESET`, set by a write to `$FFB1` | a registered macrocell on **U6** | 1 macrocell, 2 terms |
| `/BOOTOE` — the buffer's output enable, `/RUN` or the vector page | **U6** | 1 macrocell, 2 terms |
| `ROM /CE0`, `/CE1` | **U9** — boot mode, the vector page, or the 2.0–3.0 M compare, each ANDed with `R/W` and physical `A19` | 2 macrocells, 3 terms each |
| the backplane's `/IOPAGE` | **U9** — U3's term, plus above-2 MB **gated on `RUN`** | 1 macrocell, 5 terms |
| `MAP_CE_LO`, `MAP_CE_HI` | **U9** — and `LA3` is what splits a block-register write between the two SRAMs | 2 macrocells, 2 terms each |

### 6.7.1 ⭐ U9 is fitted, and §11 item 6 had the count wrong in both directions

> **2026-09-09.** [`gal/u9.pld`](gal/u9.pld), [`gal/u9.jedec.ts`](gal/u9.jedec.ts) and
> [`gal/u9.model.ts`](gal/u9.model.ts); `npm run check:jedec` evaluates the fuses against
> the model over all 16,384 input combinations and `npm run check:cupl` runs **Atmel's own
> CUPL output** through the same sweep.

§11 item 6 said this part was *"no longer obviously comfortable"* — **ten outputs on a
part that has ten, before counting inputs.** It fits at **six outputs and fourteen
inputs**, with two macrocells left as spare inputs and the widest equation at five product
terms of sixteen. Two of the counts were wrong:

| | counted | actual | why |
|---|---|---|---|
| SIMM window selects | 4 | **1** | The four windows are at physical `A24..A22` = 001, 010, 011, 100 — and those four codes are **already distinct in `A23:A22` alone**. U10 takes those two lines directly (it needs them for its RAS/CAS mux anyway) and picks its own RAS; U9 says only *whether* a SIMM answers |
| map-SRAM chip enables | 0 | **2** | Not on anyone's list. §3.1 says *"both SRAMs sit on the same `D0`–`D7`; the address picks which is written"* and **nothing said what forms that.** It is `LA3`, and it closes §11 item 5 by making U3's second write strobe unnecessary |
| `BOOT`, `VECSEL`, the enables | 3 | **0** | They went to **U6**. A 22V10 has exactly one clock and one asynchronous reset; U6 has `CLK25` on pin 1 and `/RESET` in the array because it is the divider, and it had just lost three macrocells to §6.2's departed system RAM. U9 would have paid three pins for what U6 had already |

⚠ **And the fit found one real defect.** The `/IOPAGE` pull has to be **gated on `RUN`**:
during boot the high map SRAM is deselected and `A24`–`A21` float, so an ungated
above-2 MB compare asserts `/IOPAGE` at random — and `/IOSEL` is `/IOPAGE · /A7`, so a
random assertion makes **every card in the machine decode a boot fetch** against its
jumpered base and drive `D0`–`D7`. One literal on four terms, and it is the difference
between a machine that boots and one that does not.

### 6.7.2 The changeover is free, and that is checked rather than argued

The buffer and the map SRAMs must never drive the physical address together. They are
**complements of the same two conditions on two different parts** — U6 forms
`/RUN # vecsel` for the buffer, U9 forms `RUN & !IOPAGE # blksel` for the SRAMs — and
`check:jedec` asserts over every combination of `RUN`, `/IOPAGE`, `LA7` and `LA6` that
the two are never both asserted.

⭐ **The handover edge is free as well, and by construction rather than by timing.**
`RUN` is set by a write to `$FFB1`, which is an `$FFxx` cycle — and the map SRAMs are
deselected for **every** `$FFxx` cycle, for an independent reason. So there is no instant
at which one turns on as the other turns off; the changeover happens inside a cycle where
the SRAM is already off.

**⚠ What is still owed is U10.** It carries the RAS/CAS state machine, refresh
arbitration and `/WAIT`, and it has not been written. It is the only piece of logic on
the motherboard that is not fitted at the fuse level — §11 item 6.

## 7. The backplane — zero new pins (§5.3)

**The motherboard keeps every address bit above `A20` to itself** and pulls
`/IOPAGE` low for accesses above 2 MB, so cards see the machine they already
see. **Zero new pins.**

**Which is fortunate**, because the slot has none to give —
[`lib/slot.ts`](lib/slot.ts) spent its last position on physical `A20` — and
`vctrl` sits at 64 of 64 I/O, with no room for an address extension.

> **What is still true** is that the connector's own justification expired when the
> card format changed: a 240 mm edge holds 98 positions at 0.1″ where the 100 mm
> Eurocard the 72-pin count was derived from held 39 ([`README.md`](README.md),
> `machine.md` §5 item 5). The DMA request/grant pair `net.md` §13.1 wanted and a
> future rail are the two claimants left. **Neither RAM nor the boot ROM is one of
> them** — §5.3 and §6.7 both stay on the motherboard — which makes the decision
> smaller rather than larger, and it is not being reopened.

## 8. What it costs, assembled

| | ICs | Notes |
|---|---|---|
| Second map SRAM | +1 | `CY7C128A`, §3.1 — **and it is what lets the SIMMs be addressed at all** (§5.1) |
| U3 high-byte write strobe | 0 | pin 23 is free |
| `TASK` widened to 8 bits | 0 | seven unused bits of an existing `'574`, §3.2 |
| The DIP system RAM, removed | −1 | **no DIP SRAM at all — §6.2** |
| U9 space decode | +1 | §6.3 |
| U10 SIMM timing + 3 × `'157` + U17 refresh timebase | +5 | §6.3, §6.3.1 |
| **Boot ROM: 2 × `SST39SF040` + `'244`** | **+3** | §6.7 |
| **Motherboard** | **9 → 18** | plus four SIMM sockets |
| Backplane | **0 pins** | §5.3, §6.7 |
| Cards | **0 changes** | one jumper position on storage and net, §5.2 |

**Up to 16 MB of DRAM for five packages, a bootable machine for three more, and no card
re-specification.** The map widening is the load-bearing part and it is one of the
five. ⚠ **The machine has no SRAM outside the map**, which was §6.4's boot problem until
§6.7 made boot a sequence of stores.

## 9. ⚠ The ceiling that is not hardware

**NitrOS-9 Level 2's memory manager is sized for the GIME**, whose block
numbers are 8 bits. This machine's are about to be 11. That is not a patch; the
process descriptor's map, the free-block bitmap and the allocator's arithmetic
all carry the width.

| | Status |
|---|---|
| 512 KB | **native** |
| **2 MB** | **the CoCo 3 community's 2 MB boards have precedent and patches** |
| 4 MB+ | ⚠ **nobody has done it.** A memory-manager port, and `machine.md` §6 already keeps a ledger of NitrOS-9 divergences nobody is summing |

**So what is >2 MB actually for?** Not more processes — it is for stores that no
OS manages:

- **A RAM disk**, which is the traditional answer and needs no memory manager
  at all — a driver, a bank register (§2.1!) and a window.
- **`audio.md`'s sample memory**, which is card-local and **512 KB since 2026-09-08**
  (`audio.md` §5). `audio.md` §5.2 decided it stays card-local: memory-mapping it costs
  three `'157` on a card that had collapsed the mux away.
- **`net.md`'s ring and `sdcard.md`'s block buffer**, which already live in the
  physical map and would like to be bigger.
- **Video**, whose ring is 512 KB and whose §6.2 modes want 307 KB for one
  640×480 screen — four buffers would be 1.2 MB.

⭐ **Every one of those is a §2.1 bank register over a window, not a paged
allocation.** Which is worth saying plainly: **the expensive per-block map path
of §3 serves the 2 MB the OS can use, and the cheap bank register serves the
14 MB it cannot.** They are complementary rather than alternatives, and a
design that built both would be smaller than one that built the map path alone
and tried to make the OS use all of it.

---

## 10. A staging order

**Each step is useful on its own and none of them strands the last.**

| | Step | Cost | What it buys |
|---|---|---|---|
| **0** | **Widen `TASK` to 8 bits** (§3.2) | **0 ICs** | 256 resident contexts; a process switch becomes one write. Independent of everything below and the only step that helps software that exists today |
| **1** | **Second map SRAM, 16-bit entries** (§3.1, §4) | +1 IC | the 32 MB address path — ⚠ **and the precondition for step 2**, which §5.1 is about |
| **2** | **U9 and the SIMM bank** — 4 sockets, U10, 3 × `'157`, U17 (§6.3) | +6 ICs | **4–16 MB of DRAM: all of the machine's memory** |
| **3** | **The boot ROM** — 2 flash + a `'244` (§6.7) | +3 ICs | ⭐ **a machine that boots standalone**, and the `$FFC0`–`$FFFF` vectors. Independent of steps 1 and 2 in hardware, and **required before either can be tested**, because nothing else puts an instruction in front of the CPU |
| **4** | A bank-register window (§2.1) | +2 ICs | the space above the OS ceiling as an unmanaged store, without a memory-manager port |

⚠ **Step 1 before step 2 is not a preference.** The SIMM windows are at 4–20 MB and an
8-bit map entry reaches 2 MB; **no SIMM is addressable until the entries are 16 bits
wide.**

⚠ **And step 3 is not optional either, though it is independent.** With no SRAM there is
no step that yields a working machine without DRAM (§6.2), and with no ROM there is no
step that yields one that can execute at all. **Build step 3 first if you want a bench
to test steps 1 and 2 on** — a machine with a boot ROM and no SIMMs runs the monitor out
of ROM registers-only, which is exactly what §6.4's sequence is.

## 11. Open items

1. **`machine.md` §5 item 7 is settled — nothing is owed.** The card space is 16 regions
   of 64 KB and `net.md` and `sdcard.md` both say four jumper positions. (The one-day
   halving that briefly said otherwise is archived in [history.md](history.md).)
2. ⭐ **Refresh against stretched cycles — SETTLED.** §6.6: the video card's `/WAIT`
   is qualified on `VRAMSEL`, so the DRAM bus is idle for the whole 40.7 µs and refresh
   never contends. What remains is `machine.md` §5 item 10's rule, which U10 obeys by
   construction.
3. **⚠ Layout A or B** (§4) — a NitrOS-9 cost question, not a hardware one, and
   the only genuinely open part of §3.
4. **CLOSED 2026-09-08 — the boot path is stackless and it is eighteen instructions**
   (§6.4). `machine.md` §7.2's motherboard ROM serves page 0 behind every logical block
   out of reset, refresh free-runs, and the map is written with stores. The
   scratch-RAM-in-the-CPU-module proposal is withdrawn.
5. **CLOSED 2026-09-09 — U3 needs no second write strobe and is untouched.** The
   question was whether pin 23 could become the high byte's write strobe. It does not
   have to: **U9 gives each map SRAM its own chip enable**, split by `LA3`, so U3's single
   `MAPWE` reaches both parts and the chip enable decides where the byte lands (§6.7.1).
   U3's fuse map, its 23 checks and its Verilog testbench are unchanged by any of this —
   pin 23 stays a spare **input**.
6. **CLOSED 2026-09-09 — U9 and U10 are both fitted, and there is no unwritten logic
   on the motherboard.** This item said U9 might not fit — *"ten outputs on a
   `GAL22V10`'s ten, before counting inputs"* — and that U10 *"has not been counted at
   all"*. Both are wrong in the same direction:

   | | said | is |
   |---|---|---|
   | **U9** | may not fit | **6 outputs of 10**, 14 inputs, 2 spare macrocells — §6.7.1 |
   | **U10** | never counted | **9 outputs of 10**, 11 inputs, 2 spare pins — §6.3.1 |

   Both are checked at the fuse level against a behavioural model **and** against Atmel's
   own CUPL. ⚠ **What counting U10 found was a package nobody had listed** — the refresh
   *interval* timer, which §6.3's "refresh needs no counter" had quietly conflated with
   the *row* counter CAS-before-RAS genuinely deletes.

7. **⚠ Source the SIMMs, and there are now THREE attributes to match.** 4 MB 30-pin
   modules were made and are not current-production; this is `net.md` §13.6's lesson
   again — **availability is the first question about a part.**

   - **4M × 8 or ×9**, because §6.3.1's mux mapping is for eleven row and eleven column
     bits. ⚠ **A 1M × 8 module does not work in it** — it ignores `MA10`, which drops
     physical `A10` out of the address. The 1 MB mapping is a *rewire* of the `'157` B
     inputs, so it is a build-time choice; this item used to recommend 1 MB modules and
     was written without that in view.
   - **60 ns or faster.** §6.3.1's refresh burst holds `/RAS` low for 79 ns against a
     `t_RAS` min of ~70 ns on a 70 ns part — 9 ns of margin, against 19 at 60 ns.
   - **All four the same size**, since the mapping is one wiring.

   ⭐ **1 MB modules are still buildable**, at the cost of the mapping and 4 MB total.
   Nothing about U10 changes.
8. **Period audit.** 30-pin SIMMs are 1987 and in period. **16 MB in 1989 was a
   workstation** and a 2 MB CoCo 3 was exotic, so the *capacity* is a stretch
   even though every part is not. ⚠ **The boot ROM is the weaker claim**: an 8 Mbit
   ROM is 1991-era mask/EPROM territory and the `SST39SF040` §6.7 actually specifies is
   a **1995** flash part. It is in the same posture as the two CPLD cards — buildable
   and honestly late — and `graphics.md` §15's audit is the model. `docs/machine.md`
   §15 if this is built.

9. **Nobody has measured a process switch**, so §3.2's "eight bus cycles to one"
   is arithmetic. Same unmeasured NitrOS-9 dispatch cost as `ps2.md` §14 item 3.
10. **⚠ NEW — nothing burns the ROM yet.** §6.7 specifies the part and the decode; the
    *contents* — boot monitor, the `$FFC0`–`$FFFF` vector table, the ROM-disk image and
    the tool that assembles the three into a `.bin` — are `software/` work that does not
    exist. [`../docs/drivewire.md`](../docs/drivewire.md) §6.1 is one of its callers,
    and `machine.md` §7.2 is what it has to satisfy.

## 12. Cross-references

| | |
|---|---|
| [`gal/README.md`](gal/README.md) | the MMU's register map, the entry format, and the "16 of 2048" line §3.2 turns into a capability |
| [`../docs/machine.md`](../docs/machine.md) | §5 item 1 the second megabyte, §5 item 5 the connector, §5 item 7 the card regions, §5 item 8 `/WAIT`, §5 item 10 stretched cycles, §7.1 system RAM and **§7.2 the boot ROM, which §6.7 is the parts list for** |
| [`place/`](place/) | the placement study — `svg.ts` draws the motherboard at **18 ICs**, four SIMM sockets and the boot ROM, with no SRAM outside the map |
| [`mainboard/mainboard.circuit.tsx`](mainboard/mainboard.circuit.tsx) | the `'574` with seven unused bits, and U3's free pin 23 |
| [`../audio/docs/audio.md`](../audio/docs/audio.md) §5.2 | the other card that asked to put its memory in the physical map, and the arithmetic that said no |
| [`../docs/drivewire.md`](../docs/drivewire.md) | what the boot ROM's spare megabyte is *not* for, and how a new one gets onto the machine |
