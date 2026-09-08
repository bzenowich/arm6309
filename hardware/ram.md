# RAM Expansion

## 512 KB to 16 MB, and the Three Ceilings That Are Not the Same Height

**Question this answers:** the machine has 512 KB of system RAM and a 2 MB
physical map. What would it take to reach **16 MB**, and what is the cheapest
path that does not throw away the 2 MB that already works?

**Status: brainstorm.** Nothing here is decided. Every option is priced against
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
| **16 MB** | **11** | **2048** | **2 bytes** |
| 32 MB | 12 | 4096 | 2 bytes |

**Two bytes per entry buys 32 MB as easily as 16.** The width is a step
function: once the entry is 16 bits there are five spare bits at 16 MB, and
spending one of them costs nothing. §3.3 is what they are worth.

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

## 3. The address path — one SRAM, one GAL output, three pins

### 3.1 The change

**Widen the map entry to 16 bits by putting a second `CY7C128A` beside the
first**, read in parallel. The low byte drives `A20..A13` as it does now; the
high byte drives `A23..A21` and five flags.

| | Cost |
|---|---|
| Second `CY7C128A` map SRAM | **+1 IC** |
| High-byte write strobe | **+1 output on U3** — and pin 23 is deliberately free (`mmu.pld`) |
| `A21`, `A22`, `A23` to the backplane | **+3 slot pins** — §7, and the slot has none |
| Isolation `'245` | **0** — both SRAMs sit on the same `D0`–`D7`; the address picks which is written |
| Address mux `'157` | **0** — §3.2 |
| **Motherboard total** | **9 ICs → 10** |

**Both bytes must be read in the same access**, which is why this is two
byte-wide parts and not one wider one: translation needs `A23..A13`
simultaneously, and a single SRAM read sequentially would double the map
latency inside a 110 ns `t_AD` budget that has 15 ns of SRAM in it already.

### 3.2 ⭐ And the map store is already 128× larger than the design uses

`gal/README.md` records it without drawing the conclusion: *"Sixteen 7-bit
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
| `$FFB0` | **`TASK`, 8 bits** (was 1 bit aliased 16×) |

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

## 5. The physical map — and how not to move anything

16 MB re-carves `A23..A19`, and three things already live in the bottom 2 MB:
system RAM, the video ring, and `machine.md` §5 item 7's sixteen card-buffer
regions, **two of which storage and net now hold**.

**So do not re-carve it. Extend above it:**

| `A23..A21` | Size | Contents |
|---|---|---|
| `000` | 2 MB | **the machine exactly as it is** — RAM 512 KB, VRAM 512 KB, card buffers 1 MB. Nothing moves |
| `001`–`111` | **14 MB** | expansion RAM |

**Nothing that exists changes address**, no card is re-specified, and
`clkdec.pld`'s `ramsel` term keeps working for the first 512 KB while the
expansion decodes above it. The alternative — a clean map with RAM contiguous
from zero — is tidier on paper and costs a re-specification of every card that
took a region four days ago.

⚠ **The cost is that system RAM is not contiguous**: 512 KB at the bottom and
14 MB starting at 2 MB, with VRAM and card space in the hole. A memory manager
handles that trivially — it allocates blocks, not ranges — but any code that
assumes flat RAM does not.

---

## 6. The memory itself, which is the expensive half

**512K×8 in a DIP-32 is the ceiling for through-hole SRAM.** 16 MB is
**32 packages**, which is not a motherboard — [`place/`](place/) puts nine ICs
and four reserved footprints on 272 × 190 mm and that board is already mostly
slot field.

| Approach | 16 MB costs | Verdict |
|---|---|---|
| **DIP SRAM**, `AS6C4008` | **32 packages**, ~1,300 cm² | not a board |
| SMD SRAM | 4–8 packages | ⚠ needs a part number nobody has sourced — §11 |
| **30-pin SIMM, DRAM** | **four sockets** at 4 MB each | **the period answer, and the cheap one** |
| 72-pin SIMM | one socket | 32 bits wide; three quarters of the data path wasted or muxed |

### 6.1 SIMMs, and the refresh owner the machine has never had

**A 30-pin SIMM is byte-wide (×8, or ×9 with parity), 1987, and stocked in
1 MB and 4 MB.** Four sockets is 4–16 MB, socketed, on a board that already
reserves four SRAM footprints (`place/svg.ts`).

**It is DRAM, and `machine.md` §7.1 rejected DRAM on exactly one ground:**

> SRAM rather than DRAM because **DRAM needs a refresh owner and this machine
> has none**.

⭐ **That changed on 2026-09-08.** `machine.md` §5 item 8 gave the E/Q divider a
`/WAIT` hold — a card can now stall the CPU mid-cycle, which is precisely what
a refresh controller needs and what the machine could not do before. **The
sentence that rejected DRAM was true when it was written and is not any more.**

What a SIMM bank needs:

| | |
|---|---|
| RAS/CAS address mux, 11 bits | **3 × `74HC157`** |
| Refresh counter and timing | a `GAL22V10` — CAS-before-RAS, ~15.6 µs interval |
| Refresh arbitration | `/WAIT`, per the rule: **driven synchronously to `CLK25`, asserted only while E is high** (`clkdec.pld`) |
| Data buffering | probably one `'245` |
| **Total** | **~5–6 ICs for 4–16 MB**, against 32 for SRAM |

⚠ **Refresh steals cycles, and nothing in this machine has ever stolen one.**
A CAS-before-RAS burst every 15.6 µs is well under 1 % of the bus, but it is
1 % that `audio.md` §13's replayer budget and `net.md` §3.4's dispatch
arithmetic have never had to carry. **It also interacts with `machine.md` §5
item 10** — a stretched cycle starves any card scheduling its buffer against
`E`, and refresh would be a second source of stretches after the video card's
span writer. That is the item to check before committing, not after.

---

## 7. The backplane — three pins the slot does not have

`A21`, `A22` and `A23` have to reach any card that decodes physical addresses,
and [`lib/slot.ts`](lib/slot.ts) has **no spare positions**: A34 was the last
one and physical `A20` took it.

**But the card format changed on 2026-09-08** and
[`README.md`](README.md) records what that did to the connector's own
justification: *"a 100 mm Eurocard edge at 0.1″ pitch holds 39 positions… the
card format sizes the connector."* **A 240 mm edge holds 98.**

| | |
|---|---|
| Needed for 16 MB | `A21`, `A22`, `A23` — **3 pins** |
| Also waiting on pins | DMA request/grant (`net.md` §13.1) — 2, plus `BA`/`BS` |
| Also waiting | a future rail |
| Available on a 240 mm edge | **~26 more positions at 0.1″** |

⚠ **This is one decision, not three, and it is `machine.md` §5 item 5.** The
connector should be re-specified once, for everything that wants a pin, rather
than three times. **A RAM expansion is the third claimant in a week.**

> **One escape worth naming.** If expansion RAM lives **only on the
> motherboard**, `A21`–`A23` never leave it and the backplane does not change
> at all. That works for a SIMM bank and fails the moment anyone wants a RAM
> *card* — which is the traditional way this machine's ancestors got memory.

---

## 8. What it costs, assembled

| | ICs | Notes |
|---|---|---|
| Second map SRAM | +1 | `CY7C128A`, §3.1 |
| U3 high-byte write strobe | 0 | pin 23 is free |
| `TASK` widened to 8 bits | 0 | seven unused bits of an existing `'574`, §3.2 |
| **Address path to 16 MB** | **+1** | **9 → 10 ICs** |
| SIMM bank, 4–16 MB | +5–6 | §6.1, includes the refresh GAL |
| **Motherboard total** | **~16 ICs** | from 9 |
| Backplane | +3 pins | §7, or zero if RAM stays on the motherboard |

**The address path is one package.** Everything expensive is the memory and its
controller, which is the honest shape of the answer: the MMU was over-built and
the memory subsystem was never built at all.

---

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
| **0** | **Widen `TASK` to 8 bits** (§3.2) | **0 ICs** | 256 resident contexts; a process switch becomes one write. Independent of everything below |
| **1** | Populate `RAM2`–`RAM4`, the footprints `place/` already reserves | 3 SRAM + the `'139` | **2 MB of system RAM** — the OS ceiling, with no map change at all ⚠ needs `machine.md` §5 item 7's card regions rehoused, which is the open question those footprints raised |
| **2** | Second map SRAM, 16-bit entries (§3.1, §4) | +1 IC, 3 pins | the **address path to 16 MB**, populated or not |
| **3** | SIMM bank and refresh (§6.1) | +5–6 ICs | **4–16 MB of actual memory** |
| **4** | A bank-register window (§2.1) | +2 ICs | the 14 MB above the OS ceiling, usable as a RAM disk without a memory-manager port |

**Step 0 first, because it is free and it is the only one that helps software
that exists today.** Step 1 before step 2, because 2 MB is the OS ceiling and
reaching it needs no map change. Steps 3 and 4 are one project and should be
specified together.

---

## 11. Open items

1. **⚠ `machine.md` §5 item 7 blocks step 1.** The three reserved SRAM
   footprints need `A20 = 1`, which is the card-buffer megabyte that storage and
   net both hold a region in. **Nothing above 512 KB can be populated until that
   is re-carved**, and §5's "extend above, move nothing" answer is the proposal.
2. **⚠ Layout A or B** (§4) — a NitrOS-9 cost question, not a hardware one.
3. **⚠ Does U3 fit the second write strobe?** Pin 23 is free and
   `gal/README.md` says the part fits *"with one pin spare"*. One output costs a
   macrocell **and** a pin. **Fit it before believing §8's "+1 IC".**
4. **The refresh interaction with `/WAIT`** — `machine.md` §5 item 10 already
   says a stretched cycle starves cards that schedule against `E`, and refresh
   would be the second source of stretches. Bound it before designing it.
5. **Source an SMD SRAM above 512 KB**, or accept DRAM. §6's table has a row it
   cannot fill.
6. **Three claimants for backplane pins in one week** (§7) — RAM's three, DMA's
   two, a rail. `machine.md` §5 item 5 should decide the connector once.
7. **Nobody has measured what a process switch costs today**, so §3.2's "eight
   bus cycles to one" is arithmetic rather than a saving. It is the same
   unmeasured NitrOS-9 dispatch cost as `ps2.md` §14 item 3.
8. **Period audit.** 30-pin SIMMs are 1987 and in period. **16 MB in 1989 was a
   workstation**, and a 2 MB CoCo 3 was exotic — so the *capacity* is a stretch
   even though every part is not. Worth an honest line in
   `docs/machine.md` §15 if this is ever built.

---

## 12. Cross-references

| | |
|---|---|
| [`gal/README.md`](gal/README.md) | the MMU's register map, the entry format, and the "16 of 2048" line §3.2 turns into a capability |
| [`../docs/machine.md`](../docs/machine.md) | §5 item 1 the 2 MB map, §5 item 5 the connector, §5 item 7 the card regions, §5 item 8 `/WAIT`, §5 item 10 stretched cycles, §7.1 system RAM and the DRAM rejection |
| [`place/`](place/) | the four SRAM footprints and the two preconditions they made visible |
| [`mainboard/mainboard.circuit.tsx`](mainboard/mainboard.circuit.tsx) | the `'574` with seven unused bits, and U3's free pin 23 |
| [`../audio/docs/audio.md`](../audio/docs/audio.md) §16 item 0 | the other card asking to put its memory in the physical map |
