# RAM Expansion

## 512 KB to 16 MB, and the Three Ceilings That Are Not the Same Height

**Question this answers:** the machine has 512 KB of system RAM and a 2 MB
physical map. What would it take to reach **16 MB**, and what is the cheapest
path that does not throw away the 2 MB that already works?

> Superseded material is archived in [history.md](history.md); this document describes
> only the present design.

**Status: ⭐ decided 2026-09-08 for the memory system; brainstorm for the rest.**
§5 and §6 are decisions — the physical map is re-carved and the memory is four
30-pin SIMM sockets. §3's map widening comes with them because it has to (§5.1).
Everything else is still options. Every option is priced against
the parts that exist on [`mainboard/mainboard.circuit.tsx`](mainboard/mainboard.circuit.tsx)
today, and the recommendation at §10 is a staging order rather than a design.

> **The short answer.** The address path to 16 MB costs **one SRAM, one GAL
> output and three backplane pins** — it is nearly free, because the MMU was
> built with 128× more map storage than it uses. The *memory* costs a DRAM
> controller and a SIMM bank, which is where the real work is. And the
> **operating system tops out around 2 MB**, which is why §10 says build the
> address path, populate 2 MB, and treat the rest as unmanaged store.

---

## 0. Three ceilings, and they are at 2 MB, 16 MB and 32 packages

Conflating these is how "how much RAM can it take?" gets a wrong answer.

| Ceiling | Where it is now | Where it could be | What moves it |
|---|---|---|---|
| **Physical address** | **2 MB** — 8-bit map entries, `A20..A13` | **16 MB** at 11 bits, 32 MB at 12 | §3 — one SRAM and a GAL output |
| **Parts** | 512 KB in one DIP-32 | **16 MB needs 32 of them**, or four SIMM sockets | §6 — DRAM, and the refresh owner the machine has never had |
| **⚠ Operating system** | **512 KB native, ~2 MB patched** | unknown above that | §9 — NitrOS-9's memory manager, and nobody has done it |

**The three are independent and the smallest one is the OS.** Build the first,
buy the second, and be honest that the third is what decides how much of it
NitrOS-9 will ever hand to a process.

---

## 1. Where the machine is today

From [`gal/README.md`](gal/README.md) and `docs/machine.md` §6.3.1, §7.1:

| | |
|---|---|
| Logical space | 64 KB, **eight 8 KB blocks** |
| Map entry | **8 bits = physical `A20..A13`** — 256 blocks, **2 MB** |
| Map store | one **`CY7C128A`, 2K×8**, of which **16 bytes are used** |
| Index | `{TASK, block}` — `TASK` is **one bit**, so two task contexts |
| Registers | `$FFA0`–`$FFAF` sixteen entries; `$FFB0`–`$FFBF` control, **one bit, aliased 16×** |
| System RAM | **one `AS6C4008`, 512 KB**, at `A20 = 0, A19 = 0` |
| Physical map | `00` RAM · `01` VRAM · `1x` card buffers (`machine.md` §5 item 7) |

**This is the GIME's architecture with the third-party 2 MB upgrade already
applied.** A stock GIME uses 6 of its 8 entry bits — 64 blocks, 512 KB — and
the CoCo 3 community's 2 MB boards spend the two spare bits. This machine took
bit 7 for `A20` on 2026-09-08 and is at exactly that ceiling: **8 bits, 2 MB,
nothing left in the byte.**

⚠ **So the next megabyte is not free the way the last one was.** `A20` cost one
backplane pin and no parts because the map SRAM was already byte-wide and the
eighth bit was already stored. **There is no ninth bit.**

---

## 2. What 16 MB actually requires

16 MB in 8 KB blocks is 2048 blocks, so **11 bits per map entry** — `A23..A13`.
Eleven bits do not fit in a byte, and that single fact drives everything below.

| Target | Entry bits | Blocks | Entry size |
|---|---|---|---|
| 512 KB | 6 | 64 | 1 byte |
| **2 MB — today** | **8** | 256 | **1 byte** |
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
| **Address path alone** | **9 ICs → 10** — §8 has the whole memory system at 14 |

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
| `$FFB0` | **`TASK`, 8 bits** (today one bit, aliased 16×) |

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
| `000000` | 0.0–0.5 M | **reserved** — the natural home for §6.5's boot scratch | |
| `000001` | 0.5–1.0 M | **VRAM** — the video ring | **unchanged** |
| `00001x` | 1.0–2.0 M | **card buffers — 16 regions of 64 KB** | **unchanged** |
| `0001xx` | 2.0–4.0 M | reserved | |
| `001xxx`–`100xxx` | **4–20 M** | **four SIMM windows of 4 MB — all of system RAM** | §6 |
| `101xxx`–`111xxx` | 20–32 M | reserved | |

**Nothing that exists changes address.** VRAM keeps `A20:A19 = 01` and the card regions
keep `A20 = 1`, so **the video card is untouched and no card document is
re-specified.**

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
| Motherboard | **18 → 14 ICs**, and the board shrinks with them |
| The `74HC139` the footprints needed | never built; U9 does the space decode |

⚠ **What it costs is the boot path** — §6.5.

### 6.3 What the bank costs

| | Part | Role |
|---|---|---|
| 4 | **30-pin SIMM socket** | ×8 or ×9, 1 MB or **4 MB** each — **4 to 16 MB** |
| 1 | **`GAL22V10` U9** | space decode: the four SIMM windows, and §5.3's open-drain `/IOPAGE` pull |
| 1 | **`GAL22V10` U10** | SIMM timing — `RAS0`–`RAS3`, `CAS`, `/WE`, the mux select, refresh request and `/WAIT` |
| 3 | **`74HC157`** | RAS/CAS address mux, 11 bits (a 4 MB 30-pin SIMM is 4M×8 — 22 bits, 11 row + 11 column) |
| **+5 ICs and 4 sockets** | | **all** of the machine's memory, against 32 packages for 16 MB of SRAM |

⭐ **Refresh needs no counter.** **CAS-before-RAS** makes the DRAM generate its own row
address, so the refresh row counter a 1980s design would have carried — a `74HC4040` and
its mux path — is **not on this list**. One request every ~15.6 µs, arbitrated by U10.

### 6.4 ⚠ The boot path, which is what the SRAM was quietly insuring

**With no SRAM, the machine has no memory at all until the DRAM controller is up.** The
CPU module serves its shadow ROM and vector page without a bus cycle (`machine.md` §7.2),
so it *executes* — but **the first `JSR` needs a stack**, and there is nowhere to put one.

Two answers, and the second is nearly free:

| | |
|---|---|
| **Stackless DRAM init** | boot code brings up refresh and the map using registers only, no subroutine calls, until the first SIMM answers. The 6309 has the registers for it; it is careful assembly and a real constraint on the boot ROM |
| ⭐ **The CPU module serves a scratch RAM** | it already serves an 8 KB shadow ROM and a 16-byte vector RAM from its own flash and SRAM. **An `STM32G431CB` has 32 KB of SRAM**; serving 2 KB of it as a logical window costs **zero ICs** and a firmware change, and it parallels §7.2 exactly |

**The second is recommended and not specified.** It also gives the machine somewhere to
run from if a SIMM is absent or dead, which the four-SRAM version got for free and this
one does not.

### 6.5 The motherboard, assembled

| | ICs |
|---|---|
| the board as drawn today (`mainboard.circuit.tsx`) | 9 |
| − the DIP system RAM, removed (§6.2) | −1 |
| + second map SRAM, 16-bit entries (§3.1) | +1 |
| + U9 space decode, U10 SIMM timing, 3 × `'157` | +5 |
| **total** | **14 ICs + 4 SIMM sockets** |

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

## 7. The backplane — zero new pins (§5.3)

**The motherboard keeps every address bit above `A20` to itself** and pulls
`/IOPAGE` low for accesses above 2 MB, so cards see the machine they already
see. **Zero new pins.**

**Which is fortunate**, because the slot has none to give —
[`lib/slot.ts`](lib/slot.ts) spent its last position on physical `A20` — and
`vctrl` sits at 64 of 64 I/O, with no room for an address extension.

> **What is still true** is that the connector's own justification expired when
> the card format changed: a 240 mm edge holds 98 positions at 0.1″ where the
> Eurocard held 39 ([`README.md`](README.md)). The DMA request/grant pair
> `net.md` §13.1 wanted and a future rail are still waiting on that decision.
> **RAM is no longer one of the claimants**, which makes the decision smaller
> rather than larger.

## 8. What it costs, assembled

| | ICs | Notes |
|---|---|---|
| Second map SRAM | +1 | `CY7C128A`, §3.1 — **and it is what lets the footprints be populated at all** (§5.1) |
| U3 high-byte write strobe | 0 | pin 23 is free |
| `TASK` widened to 8 bits | 0 | seven unused bits of an existing `'574`, §3.2 |
| The DIP system RAM, removed | −1 | **no DIP SRAM at all — §6.2** |
| U9 space decode | +1 | §6.3 |
| U10 SIMM timing + 3 × `'157` | +4 | §6.3 |
| **Motherboard** | **9 → 14** | plus four SIMM sockets |
| Backplane | **0 pins** | §5.3 |
| Cards | **0 changes** | one jumper position on storage and net, §5.2 |

**Up to 16 MB of DRAM for five packages and no card re-specification.** The map widening
is the load-bearing part and it is one of the five. ⚠ **And the machine now has no SRAM
at all**, which is §6.4's boot problem and the one thing this design gives up.

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
- **`audio.md`'s sample memory**, which is card-local today and 128 KB
  (`audio.md` §16 item 0 asks whether it should move into the physical map).
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
| **2** | **U9 and the SIMM bank** — 4 sockets, U10, 3 × `'157` (§6.3) | +5 ICs | **4–16 MB of DRAM: all of the machine's memory** |
| **4** | A bank-register window (§2.1) | +2 ICs | the space above the OS ceiling as an unmanaged store, without a memory-manager port |

⚠ **Step 1 before step 2 is not a preference.** The SIMM windows are at 4–20 MB and an
8-bit map entry reaches 2 MB; **no SIMM is addressable until the entries are 16 bits
wide.**

⚠ **And there is no step that yields a working machine without DRAM any more**, which is
what dropping the four SRAMs cost (§6.2, §6.4). The machine executes from the CPU
module's shadow ROM and has nowhere to put a stack until a SIMM answers. **§6.4's
scratch-RAM-in-the-module is the cheap insurance and it is not specified.**

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
4. ⚠ **NEW — the boot path has no RAM** (§6.4). Either the boot ROM initialises DRAM
   without a stack, or the CPU module serves 2 KB of its own SRAM as a window — zero
   ICs, and it parallels `machine.md` §7.2 exactly. **Not specified, and it is the thing
   the four SRAMs were quietly insuring.**
5. **Does U3 fit the second write strobe?** Pin 23 is free and `gal/README.md`
   says the part fits *"with one pin spare"*. One output costs a macrocell
   **and** a pin. **Fit it before believing §8's "+1 IC".**
6. **Fit U9 and U10.** U9 is smaller than it was — the four SRAM chip selects went with
   the SRAM — so it is the four SIMM windows and the `/IOPAGE` pull, comfortably inside a
   `GAL22V10`. U10 carries the RAS/CAS state machine, refresh arbitration
   and `/WAIT`, and has not been counted at all.
7. **Source the SIMMs.** 4 MB 30-pin modules were made and are not
   current-production; this is `net.md` §13.6's lesson again — **availability is
   the first question about a part.** 1 MB modules are commoner and give 4 MB.
8. **Period audit.** 30-pin SIMMs are 1987 and in period. **16 MB in 1989 was a
   workstation** and a 2 MB CoCo 3 was exotic, so the *capacity* is a stretch
   even though every part is not. `docs/machine.md` §15 if this is built.
9. **Nobody has measured a process switch**, so §3.2's "eight bus cycles to one"
   is arithmetic. Same unmeasured NitrOS-9 dispatch cost as `ps2.md` §14 item 3.

## 12. Cross-references

| | |
|---|---|
| [`gal/README.md`](gal/README.md) | the MMU's register map, the entry format, and the "16 of 2048" line §3.2 turns into a capability |
| [`../docs/machine.md`](../docs/machine.md) | §5 item 1 the 2 MB map, §5 item 5 the connector, §5 item 7 the card regions, §5 item 8 `/WAIT`, §5 item 10 stretched cycles, §7.1 system RAM and the DRAM rejection |
| [`place/`](place/) | the placement study — `svg.ts` draws the motherboard at 14 ICs and four SIMM sockets, with no SRAM |
| [`mainboard/mainboard.circuit.tsx`](mainboard/mainboard.circuit.tsx) | the `'574` with seven unused bits, and U3's free pin 23 |
| [`../audio/docs/audio.md`](../audio/docs/audio.md) §16 item 0 | the other card asking to put its memory in the physical map |
