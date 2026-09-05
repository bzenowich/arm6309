# Design Review

**Date:** 2026-09-04. **Scope:** every subsystem specification, the machine-level
documents, the firmware spike, the reference player, and the repo itself. Each
subsystem was reviewed independently, with the load-bearing arithmetic re-derived and
part behaviour checked against the datasheets in `reference/` rather than taken from
the documents. Findings deliberately exclude what the documents already flag as open
items — the value here is what the documents missed or got wrong.

**Severity scale:** **CRITICAL** — the design cannot work as specified. **MAJOR** —
will cause rework or failure if unaddressed. **MINOR** — quality/robustness.
**NOTE** — observation, no action forced.

---

## Resolution status — all findings applied 2026-09-04

Every finding below has been acted on in the same pass that produced this document. The
subsystem sections are left **exactly as first written**, including the one finding that
turned out to be wrong: a review that quietly edits its own misses is not a review. Where
a fix changed a document, the superseded claim is marked in place there, per the house
convention.

| | |
|---|---|
| **Applied** | all 6 critical, all 35 major, and the minors and notes |
| **Disproved by measurement** | **one** — `Aud-m2`. See below |
| **Left for the owner** | 8 decisions, listed below. None blocks the others |

**What moved most.** The machine gained a boot story, an `/IOPAGE` inhibit signal, a
system-RAM owner, an electrical section and a power budget (`machine.md` §§2.1, 7, 8);
the CPU moved to the `STM32G431CBU6` and tightened its pass gate from 18 cycles to 14;
and **the honest IC counts rose about 45 % in aggregate** — video 33 → **40**, audio 35 →
**57**, PS/2 9 → **11**, storage unchanged at 7. The machine is ~131 ICs and 2–3 A, not
~90 and 1.5–2.5 A.

**The reference player got measurably better, not just different.** The A/B ladder against
libopenmpt went from **18/22 probes agreeing to 22/22**, with four probes moving from
outright failure (`17_ec0` 0.000 → 1.000, `21_loopbreak` 0.070 → 0.998, `16_tpspeed`
0.519 → 0.998, `20_offsetmem` 0.823 → 0.999). The rebuilt tuning instrument resolves
~1 cent where the old one could only ever report 0 or ±50, and it immediately exposed a
real +1.96-cent divergence in `1xx`/`2xx` portamento that had been invisible.

### ⚠ One finding was wrong: `Aud-m2`

The review claimed the reference player's tick-0 period write during sustained
vibrato was "an extra write ProTracker never issues". **It is not.** ProTracker's
`mt_CheckMoreEffects` falls through to `mt_PerNop` for every command outside
`{9,B,D,E,F,C}`, so it *does* rewrite the base period at tick 0 under a sustained `4xy`.
Applying the "fix" dropped the vibrato probe from 0.996 to 0.969, and reading the
fundamental out of libopenmpt's own `a500` render by autocorrelation shows the snap
plainly — **183.5 Hz** at tick 0 of rows 2–4, the un-modulated base, against 174.9 /
187.3 / 190.5 Hz for a player that holds the modulated value.

The behaviour was therefore **kept**, and `test_effect_vibrato_row_snap` now pins it so
that nobody removes it again on the strength of this document. The finding stands below
as written, and is wrong.

### Left for the owner

These are decisions, not omissions — each was priced rather than taken, because each
trades something the review has no standing to spend:

1. **A licence for the project's own work** (§Sys-M6). Nothing was chosen; a wrong
   licence is worse than none.
2. **Purging `reference/68k/` from git history** (§Sys-M6). The files are out of the
   working tree and the index, but history rewriting needs `git filter-repo` and a force
   push to the GitHub remote — a rewrite of published history, and yours to trigger.
3. **The `TFM` firmware option** (`sdcard.md` §11.6). Specifying resume-without-re-read
   in the CPU firmware deletes the storage hazard and buys 27 %, at the price of a
   fidelity divergence in the shared CoCo 3 core.
4. **The audio card's envelope at 57 ICs** (`audio.md` §16 item 19). Double-height,
   mezzanine, or the four-DAC analogue sum of its item 17 — which is both cheaper *and*
   closer to Paula, and is the largest single lever on that 57.
5. **Boot: shadow ROM or motherboard EPROM** (`machine.md` §7.2). The EPROM costs 2 ICs
   and restores the "drop a real HD63C09E in" property the shadow ROM spends.
6. **The `PF1` machine strap versus a build-time flag** (`plan.md` §10.7). The strap is
   the machine's last free pin; the flag keeps the pin and gives up one-firmware.
7. **The PS/2 masked-transmit trade** (`ps2.md` §14 item 9). Four mitigations tabulated,
   none free; "mask and accept" is the current default.
8. **Fast-E policy for the serial card** (`serial.md` §13 item 6). Buy a 4 MHz part, have
   the driver refuse ÷8, or quiesce across the transition.

**Two things the fixes could not close**, and both want a bench rather than a decision:
the video card's sync GAL pair is **24 macrocells wanted against 20** (three escapes
priced in `graphics.md` §19 item 8, and the headline 40 assumes one of the first two),
and `sdcard.md` §9 remains **entirely recalled** — there is no SD specification in
`reference/`, and this pass *increased* that exposure by adding the init dialog, the
write sequence and every timing ceiling from memory.

---

## Executive summary

The per-card documents are unusually careful, and most of their arithmetic survives
re-derivation exactly — the datasheet numbers, clock trees, throughput figures, and
register-map fits are almost all right. The serious problems cluster in four places:

1. **The machine cannot boot.** No document allocates a boot ROM, decodes the vector
   page, or explains where the first instruction comes from. The reset vector at
   `$FFFE` lands inside the I/O page — which overrides MMU translation by design —
   and nothing is decoded there; the 1 MB physical map has no room for a ROM; and
   the NitrOS-9 load path is circular. This is invisible from inside any single card
   spec, and it is missing from `machine.md` §5's "each one blocks a board" list.
   (Sys-C1)

2. **The CPU pinout does not exist on the committed package.** BA, BS, and the debug
   UART sit on PC4/PC6/PC10/PC11 — pins bonded out on the UFQFPN48, not the LQFP48
   the BOM commits to. The fix is nearly free (same die in the QFN package), but as
   written every pin-budget table and `machine.md`'s "5 spare pins" argument is
   wrong. (Cpu-C1)

3. **The I/O page is electrically unsafe.** During any `$FFxx` access the map SRAM
   still emits a translated physical address onto the backplane, so system RAM or
   VRAM sees a valid memory cycle concurrently with the addressed I/O card — double
   drive on reads, silent corruption on writes. Two reviews converged on this
   independently. One backplane signal fixes it, but it must exist before the
   backplane is drawn. Relatedly, the 3-IC motherboard MMU cannot be wired as drawn
   (data-bus conflict, missing address mux — honestly 4–5 ICs). (Sys-M1, Vid-C1,
   Vid-C2)

4. **Several cards' central claims fail one level below the prose.** The storage
   card's only software listing loses byte 0 of every block by the card's own
   register semantics; the audio card feeds two's-complement samples to a DAC that
   requires offset binary (full-scale jumps at every zero crossing) and specifies a
   5-pole LED filter where the A500's is 2-pole; the PS/2 card's no-FIFO argument
   rests on a hold window that is the inter-byte gap, not the claimed full frame;
   the video card's analog back end has no drive stage and no blanking mechanism;
   the serial card's flow-control claim describes a 16550, not a 6551. (Sto-C1,
   Aud-M1, Aud-M4, IO-P1, Vid-M4, IO-S2)

**Totals: 6 critical, 35 major** findings, plus minors and notes, detailed per
subsystem below. A recurring pattern: the *static* layer of each design — protocol
facts, part selection, register maps, clock arithmetic — is strong; the reference
code is validated where external tools pushed back. What slips is the *dynamic*
layer (what happens when two things are in flight at once: torn multi-byte register
writes, interrupts during transfers, transmit during receive), the *boundary* layer
(power-up state, reset generation, bus contention between cards), and the
*unowned middle* (system RAM, boot ROM, power budget, /RESET — things that belong
to the machine, where "the machine" has no board yet). Also worth noting: three
findings were confirmed by *running* the reference player, and one repo-level issue
(committed Apple ROM and CHM source archives on a public GitHub remote) needs
attention independent of any hardware decision. (Aud-M6/M7/M8, Sys-M6)

---

## 1. Machine / system integration

### Verified clean

The `$FF` map is fully consistent across all six owners — every card doc agrees with
`machine.md` §3 on exact addresses and sizes, with no stale addresses in any register
table. Interrupt ownership agrees everywhere with `machine.md` §4. The SD card's
interrupt masking *is* accounted for against audio (49 µs vs the 20 ms tick = 0.25 %,
FIRQ delayed-not-lost), and VBL is latched in `VSTAT`, so it survives masking. No
build outputs are committed; `build-*/` is correctly ignored.

### Sys-C1 — CRITICAL: the machine as specified cannot boot

**Where:** `machine.md` §2/§3 (no ROM appears anywhere); `graphics.md` §6.3/§6.3.1;
`sdcard.md` §12 step 0; `software/6809/README.md`.

Nothing in the repository allocates a boot ROM, decodes `$FFF0`–`$FFFF`, or explains
where the first instruction comes from. Three compounding facts:

1. **The reset vector is inside the I/O page.** The 6309 reads `$FFFE`–`$FFFF` on
   reset; `machine.md` §2's override term covers all of `$FF00`–`$FFFF`, so vector
   fetches bypass MMU translation by design — exactly like a CoCo 3. But the CoCo's
   SAM/GIME *specifically maps `$FFF2`–`$FFFF` onto ROM*; here the only decodes in
   the I/O page are `$FF40`–`$FF7F` (geographic) and `$FFA0`–`$FFAF` (MMU,
   write-side). `$FFFE` selects nothing. The CPU fetches its reset vector from an
   undriven bus.
2. **There is no physical address for a ROM even if one were added.** `graphics.md`
   §6.3 fixes the entire 1 MB map: `A19=0` system RAM, `A19=1` VRAM. Zero bytes of
   physical space are reservable for ROM without a carve-out nobody has drawn.
3. **The NitrOS-9 load path is circular.** `sdcard.md` §12 step 0 boots NitrOS-9
   over DriveWire "before any of this exists" — but DriveWire needs a running 6809
   boot client, which needs ROM, which doesn't exist. ASSIST09 is "2 KB at `$F800`"
   and there is nowhere to put it at reset.

**Fix:** the natural answer is the one the architecture is begging for: **the STM32
serves the vectors and a small boot ROM internally** (vector fetches and a
`$FFE0`-region window satisfied without a bus cycle; the CoCo drop-in firmware never
does this, so it must be a mode bit). Alternatively a motherboard ROM with an
explicit vector/ROM carve-out from the I/O page. Either way this belongs in
`machine.md` §5 as **item 0, above the I/O-window item**. Note the tension either
answer creates with `graphics.md` §16 item 8's "drop a real HD63C09E in" property —
an internal-ROM answer silently breaks it.

### Sys-M1 — MAJOR: undefined physical-bus state during I/O-page cycles

**Where:** `machine.md` §2; `graphics.md` §6.3 consequence 2, §6.3.1.

During a `$FF00`–`$FFFF` access the map SRAM still emits *translated* physical
A13–A19 onto the backplane — nothing gates it. System RAM decodes `A19=0`; the video
card decodes physical A0–A18 + `A19=1`. Whatever the current task's block 7 maps to,
either RAM or VRAM sees a valid memory cycle **concurrently with the addressed I/O
card**: on a read, two drivers on D0–D7 (electrical double-drive); on a write to,
say, `$FF60`, a byte is silently written into some translated RAM/VRAM location.
`graphics.md` §6.3 explicitly allows any MMU block to point at VRAM, so a task with
`$E000`–`$FFFF` mapped to VRAM puts `A19=1` on the backplane during *every* I/O
access. The backplane has no `/IOPAGE`-inhibit signal, and the video card cannot
compute the inhibit itself because logical A13–A15 "never reach a slot."

**Fix:** one backplane signal (`/IOPAGE` or `/MEMEN`) that every physical-memory
decode — system RAM *and* the video card's VRAM select — must qualify against; or
force the map SRAM outputs to a reserved pattern during I/O-page cycles. One
sentence in `machine.md` §2; a wrong backplane etch without it.

### Sys-M2 — MAJOR: 512 KB of system RAM has no owner

**Where:** `machine.md` §0/§2 assert `A19=0` = 512 KB system RAM; no document says
who provides it. It is in no chip budget (every card accounts only for its own
parts; the motherboard is specified as 3 MMU ICs + 1 divider GAL). SRAM vs DRAM is
undecided — DRAM needs a refresh owner and none exists; 512 KB of SRAM is ~4 ×
AS6C4008 plus decode, unbudgeted for cost, power, or board area. `machine.md` §5
asks "backplane or single board?" but never "where is the memory?"

**Fix:** add to `machine.md` §5. Given the house style, 4 × 512K×8 SRAM on the
motherboard with `/CS` from `A19=0` (gated per Sys-M1) is one line — but it must be
written down and its current added to the power budget (Sys-M5).

### Sys-M3 — MAJOR: no interrupt-source consolidation, and the polling order is destructive

**Where:** `machine.md` §4; `graphics.md` §12.2; `serial.md` §7.3; `ps2.md` §8.1.

Four `/IRQ` sources have status in four different cards' registers (`VSTAT $FF73`,
`IOSTAT $FF52`, serial `STATUS $FF55`, plus raster compare inside the CPU).
`machine.md` §4 says NitrOS-9's CoCo 3 IRQ code "already expects a GIME-compatible
interrupt-source block" — but this machine provides no such block: `$FF92/$FF93` is
decoded by nothing, and `machine.md` §5 item 6 itself lists the interrupt block as a
GIME divergence, contradicting `graphics.md` §12.2's "can be made
register-compatible." Worse, the polling chain is order-sensitive: serial's `STATUS`
read **clears the interrupt and carries the error bits in the same read**, so a
dispatcher that probes serial before deciding it wasn't the source destroys state.
No document defines the machine's polling order or dispatch cost — the very number
`ps2.md` §14 item 3 calls its weakest.

**Fix:** either commit to the STM32 internally serving a read-only consolidated
pending register (it already owns raster compare; zero ICs), or specify the polling
order in `machine.md` §4 with serial last and its handler consuming errors
immediately.

### Sys-M4 — MAJOR: no machine-level electrical spec

**Where:** `machine.md` §2; `graphics.md` §6.3.1 pin table, §17.

Signals every card assumes have no owner:

- **/RESET** is on the backplane, an input to the CPU, the 6551, and every card —
  and no power-on reset circuit appears in any budget. Nobody generates it.
- **/HALT** is in the CPU module's pin budget but **absent from `machine.md` §2's
  backplane list**. Unconnected, it floats; the CoCo ties it up with 4.7 kΩ and this
  machine says nothing.
- **Open-drain pull-ups:** `/IRQ`, `/FIRQ`, `/WAIT`, `/NMI` are declared open-drain;
  no document places the pull-up resistors.
- **Audio output pins:** `graphics.md` §17 instructs the backplane to carry stereo
  L/R ("two pins and two grounds"); `machine.md` §2's table omits them.
- **Bus voltage and drive:** the 5 V TTL nature of the backplane is only inferable
  from per-card HCT arguments; `machine.md` never states it, nor that the CPU
  module's 3.3 V-side buffers front this bus, nor the fan-out — D0–D7 alone sees ~6
  drivers/receivers plus system RAM.

**Fix:** a §2.1 "electrical" table in `machine.md`: reset supervisor (DS1233-class
or RC + Schmitt), /HALT tied high on the motherboard, pull-up values and location,
5 V TTL levels, per-signal load counts.

### Sys-M5 — MAJOR: no machine power budget

Video estimates its own current ("450–650 mA", itself understated — see Vid-m3),
audio "250–350 mA"; PS/2 (9 ICs), serial, SD (plus its LDO and write bursts),
motherboard, and the unowned system RAM estimate nothing, and nothing sums them. The
machine is plausibly 1.5–2.5 A at 5 V across ~90 ICs plus a 3.3 V domain — a real
PSU and slot-connector power-pin decision that per-card "measure at bring-up" does
not cover. **Fix:** a power row per card in `machine.md` §0's table and a summed
supply spec next to §5 item 5's connector question.

### Sys-M6 — MAJOR: copyright — Mac-Plus.ROM and the CHM Apple zips are committed and pushed

**Where:** `reference/68k/`, pushed to a public GitHub remote.

`Mac-Plus.ROM` is Apple's copyrighted ROM image with no redistribution license of
any kind — hosting it on GitHub is straightforward infringement and a DMCA magnet.
The QuickDraw/MacPaint zips were released by the Computer History Museum **under
Apple's terms for non-commercial use distributed via CHM** — the license does not
grant onward redistribution; `reference/68k/README.md` acknowledges "not covered by
this project's licensing" and tracks them anyway. (ASSIST09, © Motorola 1979, is the
same class. There is also no LICENSE file for the project's own work.)

**Fix:** remove all three from the repo **and its history** (`git filter-repo`),
list them in the README exactly like the ignored PDF scans ("obtain from CHM"),
extend `.gitignore`, add a LICENSE. The README's own logic for ignoring the scans —
"freely available from the vendors" — applies *more* strongly here.

### System — MINOR

- **Sys-m1. The master oscillator's location contradicts itself.** `machine.md`
  §0/§1: "on the motherboard." `graphics.md` §14 lists the same 25.175 MHz can
  **inside the video card's own IC budget**. If it is on the card, pulling the video
  card kills E and the CPU — fatal for the bring-up sequences that run before video
  exists. Put it on the motherboard; delete it from the card budget.
- **Sys-m2. No machine-wide ÷8 compatibility statement.** `machine.md` §5 item 4
  flags only the video read path. At ÷8, E = 3.147 MHz is **57 % over a 2 MHz
  R6551A's rating** (serial never examines ÷8 at all — see IO-S1); SD's burst margin
  drops from 2.25× to 1.5× (still fine, unstated). §5 item 4 should become a
  per-card ÷8 compatibility table.
- **Sys-m3. `graphics.md` §17 is stale and unmarked**, violating the repo's own
  "superseded text is marked, not deleted" convention: it still says `$FF50–$FF5F`
  is "left for a disk controller," and §18 step 0's freeze criterion describes a map
  that no longer exists (three cards now live there).
- **Sys-m4. Video IC count disagrees across four documents:** README and
  `machine.md` say "~33", `serial.md` §9 says 33, `graphics.md` §14's own table sums
  to **36** (and see Vid-M1 — the honest number is higher still). Sync to the owning
  doc.
- **Sys-m5. /WAIT's implementer is underspecified.** `graphics.md` §3.3 assigns
  E-stretch to "the motherboard's E/Q generator," but §14's alternative parts — a
  bare '163 + '74 — cannot implement it; and `serial.md`'s plan to use /WAIT for a
  slow 6551 needs a per-access decode term its GAL budget never mentions. Specify:
  GAL only; /WAIT is a divider input; name which cards carry a /WAIT term. Also the
  two documents use "stretch" for opposite things (see IO-S1).
- **Sys-m6. The system tick changes frequency with video mode** (70.09 Hz in
  `VMODE 0/2`, 60.0 Hz in `VMODE 1/3`) and NitrOS-9 timekeeping is never told; and
  the bring-up orderings that boot NitrOS-9 before video exists have no tick source
  at all — audio's general-purpose `TIMER` on /FIRQ is the obvious stand-in and no
  document connects the two.
- **Sys-m7. The imported 6809 software needs more than a "retarget."** ASSIST09 and
  forth9 assume a 6850/PTM I/O model the machine doesn't have (the 6551's register
  model differs materially from the 6850), and "ROM-able at `$F800`" collides with
  Sys-C1 — there is no ROM to be ROM-able into. Worth a sentence in
  `software/6809/README.md` so bring-up step 6 isn't discovered to be a porting
  project on the day.

### System — NOTE

- **Sys-n1.** Build system is healthy: host/ARM configs cleanly disjoint, both tests
  wired into CTest, no hardcoded toolchain paths. One reproducibility gap:
  `graphics.md` §20 cites its normative sources as `~/code/colormin/docs/*.md` —
  home-directory paths into a sibling repo. Load-bearing claims ("transfers
  unchanged from minimal256.md §11") are uncheckable from a fresh clone; snapshot
  them under `reference/` or point at a public location.
- **Sys-n2.** `sandbox.conf` grants the boxed agent write access to the colormin
  repo — broader than this project needs.
- **Sys-n3.** `ps2.md` §3.2 says the WD1773 is "four registers plus a latch";
  `machine.md` §3 says five. The WD1773 has four register addresses; `machine.md` is
  wrong.

---

## 2. CPU

### Verified clean

Every HD6309E and MC6809E datasheet number the plan relies on was re-read from the
scans and matches — t_AD 110/110 ns, t_DSR 40/20, t_DHR, t_PCS, the "t_AD does not
tighten at 3 MHz" claim, and the choice to design against Motorola's 10 ns data
hold. The cycle arithmetic, the PLL/boost configuration in `clock.c` (M=4/N=85/R=2 →
170 MHz, 4 wait states, compliant boost-entry sequence), the entire `stm32g431.h`
register map (including the DMAMUX request numbers and the EXTI event-mode
procedure), the 5 V-tolerance core claim (PA0–PA7 are TT_a, so buffers are genuinely
mandatory), the memory/linker/startup arrangement, and the plan's analysis judgments
(open-drain rejection RC math, EXTI-ISR infeasibility, the Q-fall anchor surviving a
live speed switch) all verify against RM0440 and DS12589.

### Cpu-C1 — CRITICAL: the pinout does not exist on the committed package

**Where:** `pinout.h`; `plan.md` §3.1/§3.2; `gpio.c`; `machine.md` §5 item 6.

The design is committed to the **STM32G431CBT6 (LQFP48)**, and the pinout places BA
on PC4, BS on PC6, and the debug UART on PC10/PC11. **None of these pins exist on
the LQFP48.** DS12589 Table 2: GPIOs = "38 in LQFP48, 42 in UFQFPN48"; the LQFP48
figure carries PA0–15, PB0–15, PC13/14/15, PF0/PF1, PG10 and nothing else on port C.
PC4/PC6/PC10/PC11 appear only on the **UFQFPN48** and larger packages — the plan's
"verified against modm-devices" evidently read the family pin list, not the LQFP48
bonding. Real budget: 38 − SWD − NRST = **35 usable**, not 39. The 33 mandatory
CoCo 3 signals fit; the only spares are PF0/PF1 — so on this package there is no
BA, no BS, no debug UART, and `machine.md`'s "5 spare" homebrew arithmetic is wrong.
(The external-MMU decision *survives* — the in-CPU MMU becomes even more
infeasible.) `gpio_init()` silently configures registers for unbonded pins.

**Fix:** switch the BOM to the **STM32G431CBU6 (UFQFPN48)** — same die, same
firmware, the pinout works verbatim; QFN soldering is the only cost. Or stay LQFP48
and delete BA/BS/UART from every table. Either way, correct `plan.md` §3.1/§3.2,
`pinout.h`, and `machine.md` item 6.

### Cpu-M1 — MAJOR: variant 3's DMA source is in CCM — the DMA cannot read it; the spike will always time out

**Where:** `spike_dma.c:66` (`__ccmbss s_dma_addr`) and `:91` (`CMAR`).

RM0440 §2.4: CCM SRAM "can be accessed by DMA **only** by the aliased address"
(0x2000 5800 on category-2 parts). `__ccmbss` links the variable at 0x1000xxxx —
exactly the window DMA cannot reach. The transfer bus-errors, every cycle falls out
of the guard, and `dma_timeouts` = n_cycles. Aggravation: the README says a timeout
"points at wiring or a clock enable rather than a wrong bit position" — this failure
would be misdiagnosed on the bench by the project's own documentation. **Fix:** put
`s_dma_addr` in ordinary SRAM (or program the alias), and check TEIF in the timeout
path so a bus error is distinguishable from "never triggered."

### Cpu-M2 — MAJOR: BOOT0 is PB8 = A8, sampled at every reset — nondeterministic boot in the socket

On the STM32G431, BOOT0 lives on **PB8** (RM0440 §2.6: sampled during the whole
reset phase while `nSWBOOT0`=1, the shipping default). PB8 is address line A8 here,
wired to a '541 input whose level at reset is undefined — the part will
intermittently boot into the system bootloader instead of flash. Classic "works with
a debugger, fails in the socket." No document mentions BOOT0 anywhere. **Fix:**
program option bytes `nSWBOOT0=0, nBOOT0=1` at provisioning (document it), or pull
PB8 down; record next to the PB map in `pinout.h`.

### Cpu-M3 — MAJOR: §3.6's read-latch glue is wrong as specified

Four defects in the bus-buffer glue: (1) a '574 clocks on the **rising** edge, so
"clocked by E's falling edge" needs an inverted E — and no inverter exists anywhere
in the parts list (the '541/'125 are non-inverting); its delay also eats the 10 ns
hold budget. (2) The OE polarities are swapped: as written, the read latch is
disabled during reads and the write buffer during writes; the correct wiring needs
/R/W, from another missing gate. (3) The '574 has a single OE, so combining /R/W
with `BUS_OE` needs an OR gate — more missing glue. (4) The one 74LVC125 (4
channels) cannot cover the ~7 control inputs plus derived signals; and any control
input wired directly to the 5 V socket violates the FT-pin absolute maximum
(min(VDD,VDDA)+4.0 V) during LDO ramp-up. **Fix:** redraw §3.6 completely — add a
'1G04/'14 or swap a '541 for a '540, correct the OE table, re-count buffer channels
— before Phase 7.

### Cpu-M4 — MAJOR: the Phase-1 latency measurement is biased optimistic, not "conservative"

The README claims the DSB "errs in the safe direction." Two systematic errors run
the other way: (1) TIM1's capture path synchronizes TI1 even with ICF=0, so the
E-fall timestamp lags the physical edge by ~2–3 core cycles — every cycle of lag
subtracts from measured latency; (2) t_done excludes pad slew (~3.3 ns) plus '541
propagation plus the inbound E buffer, all of which land after the DSB. Net:
`lat_worst` can flatter the true socket-referred latency by roughly **3–5 cycles
against a claimed margin of 5.7** — a spike reading 17 could be a real 21 and the
gate would pass. **Fix:** tighten the pass gate to ~14–15, or calibrate the
synchronizer offset out; at minimum delete the "conservative" claim.

### CPU — MINOR

- **Cpu-m1.** `gpio_init()` clobbers the SWD pulls it promises to preserve:
  `GPIOA->PUPDR = 0` clears PA13's pull-up/PA14's pull-down (only MODER is masked).
  Mask PUPDR/OSPEEDR the same way.
- **Cpu-m2.** UCPD dead-battery pull-downs: a 5.1 kΩ pull-down on PB6 (A6) is
  activated by a high on PA9 (**Q — toggling at bus rate**) and on PB4 (A4) by PA10
  (R/W), until `UCPD1_DBDIS` is set — and firmware never sets it. Levels survive;
  it's free jitter and ST says turn it off. One line in `clock_init`.
- **Cpu-m3.** Address-bus power-on glitch: MODER is set to outputs before ODR is
  written, so the module drives $0000 briefly. Write BSRR first.
- **Cpu-m4.** The recorded TT_a inventory is incomplete (Table 12 also lists
  PB13/PB14): conclusion unchanged, but the risk table's own instruction is "verify
  before PCB" and the recorded list is wrong.
- **Cpu-m5.** The two exit-path comments in `spike_poll_asm.S` (lines ~391/397) are
  swapped — each describes the other's case. Register selection is correct.
- **Cpu-m6.** Doc drift, three instances that will mislead on the bench: `main.c`
  says "no spare pins (the pinout uses all 39)" contradicting plan/README; the
  stimulus README claims the deadline is recomputed per cycle (it's a fixed
  constant); `spike.h`/`gpio.c` still carry the retired "quarter-cycle = 23.7
  cycles" framing above the correct constants.
- **Cpu-m7.** The homebrew machine's actual E rates were never run through the
  plan's arithmetic: everything analyzes 1.79/2.0/3.0 MHz, not 2.098/3.147. At
  3.147 MHz the bus cycle is 54.0 core cycles (budget ~31 with latch; TFM's
  measured 25 keeps ~6, not 9). And **317.8 ns < the HD63C09E's 333 ns t_cyc
  minimum — ÷8 mode is out of spec for the real 6309**, so §6.2's silicon A/B
  reference cannot be captured at that rate with a rated part.
- **Cpu-m8.** Variant 2's asm loop has no overrun-of-slack detection: at 3 MHz its
  bookkeeping (~35–40 cycles) can arrive after Q-fall, silently including late-entry
  cycles in latency numbers. The C variant counts this (`slack_late`); the asm
  reports nothing.

### CPU — NOTE

- The "sample gaps of 4 and 6 cycles verified against the disassembly" claim
  overstates what a listing can verify: an AHB2 GPIO load can cost 3+ cycles, not 2,
  which would fail the 40 ns soundness gate. The hardware jitter measurement will
  catch it — treat 4/6 as the thing being measured, not established fact.
- The §4.1 AND-fold samples /NMI//IRQ//FIRQ//HALT at an undefined instant within the
  bus cycle; real silicon samples at a defined point with t_PCS setup. Can shift
  interrupt recognition by one bus cycle when an edge lands near the boundary —
  worth pinning once cycle accuracy is the product.
- The microstate probe's TFM fragment is not TFM-shaped (r9 double-booked; 2-bit
  register fields vs the real 4-bit postbyte with validity trap) — the 25-cycle
  "worst measured" is a floor for TFM, not a worst case.
- `test_stub_core.c:210`'s range check is vacuous (values masked to 16 bits at
  generation).

---

## 3. Video

### Verified clean

VGA timing arithmetic all checks: 25.175 MHz ÷ 800 = 31.469 kHz line; 449 lines →
70.087 Hz; 640×400@70 = 800×449 is the genuine standard mode; 525-line variants
correct. ÷12/÷8 fetch-slot integrality, bus-cycle times, bandwidth totals
(~33.9 M accesses/s), register map fit (+$00..+$16 in 32 bytes), scroll-register
widths against the 1024×512 torus, span/clear/scroll arithmetic, and the LUT chain
timing (28 ns vs the 39.72 ns dot) all re-derive exactly. Line doubling by
double-fetch is real and correctly counted in the bandwidth math.

### Vid-C1 — CRITICAL: the 3-IC MMU cannot be wired as drawn

**Where:** `graphics.md` §6.3.1; `machine.md` §5 item 6.

Two independent defects:

1. **Data-bus conflict.** The 2K×8 map SRAM's data pins are its *outputs driving
   physical A13–A19*. To write a map entry, CPU D0–D7 must reach those same pins. If
   the SRAM data pins are on the A13–A19 net, CPU data can never reach them; if they
   are on D0–D7, then A13–A19 *are* D0–D7 at all times. A common-I/O SRAM here
   requires an isolation buffer ('245/'541) between the SRAM I/O and one of the two
   nets, with break-before-make OE discipline during updates. That is a 4th IC. (The
   period-honest fix — the SWTPc DAT that §15 itself cites — used 74LS189-class
   register files precisely because they have *separate* data-in and data-out pins.)
2. **Missing address mux.** In translate mode the SRAM is addressed by
   `{TASK, A15..A13}`; when the CPU writes entry N at `$FFA0+N`, A15..A13 = 111
   (it's the I/O page), so the entry index must come from **A3..A0** instead. The
   SRAM address inputs need a 4-bit 2:1 mux. It could go in the GAL — but the input
   count (12-bit decode + 4 index + TASK + E + R/W = 19) exceeds a 22V10's usable
   inputs at the needed output count.

**Honest count: 5 ICs (SRAM, '574, GAL, buffer, '157) or 4 with a second
relaxed-decode GAL — not 3.** Also unstated: what A13–A19 carry *during* the
map-write cycle — safe only once Sys-M1 is fixed.

### Vid-C2 — CRITICAL: VRAM decode not inhibited during I/O-page cycles

Same finding as Sys-M1, reached independently from the video card's side: the card
"decodes physical A0–A18 plus a chip select" with no qualification against the I/O
page, so a task with an MMU block pointed at VRAM double-drives D0–D7 on every I/O
read and posts spurious VRAM writes on every I/O write. Additionally, with
`$FF00`–`$FFFF` overriding translation, *nothing responds to vector fetches at
`$FFF2`–`$FFFF`* (see Sys-C1) — and if the STM32 fakes them internally, §16 item 8's
"drop a real HD63C09E in" property silently breaks.

### Vid-M1 — MAJOR: the posted-write path is missing its address latches (~3 ICs)

**Where:** `graphics.md` §3.1, §6.3, §14.

colormin needed only a *data* latch because its VRAM was write-only through a
pointer — the address always came from the card. This card makes VRAM flat-mapped,
so a direct CPU write arrives with an arbitrary **19-bit physical address** that
must be captured at E-fall along with the data. The 6809E holds address only
~20–30 ns and data ≥30 ns after E-fall, but retirement can be a full fetch slot
(158.9 ns) later — at ÷8, well past the next cycle's address-out. §14 carries
exactly one '574 "posted-write data latch | =" — the "=" betrays it: copied from
colormin, where the address side didn't exist. 19 address bits + decode = **3 more
'574s**, taking the card to ~39 ICs. "One capture register, one edge" (§3.1) is
false for this card. A live-retire scheme fails at ÷8 outright.

### Vid-M2 — MAJOR: the §11 read budget closes at ÷12 only under an unstated sub-slot ordering

Re-deriving the §11 budget by phase: with the CPU/spare access scheduled in the
*front* half of each fetch slot, the read closes with 47 ns margin at ÷12 ✓. With
the video fetch first — which the stated "video → CPU" priority naturally implies —
the CPU access completes at 481.8 ns vs the 456.7 ns deadline: **misses by 25 ns**.
The claimed ~30 ns margin exists only under spare-first ordering, which nothing in
the document specifies. Happily spare-first is also what the fetch-latch clocking
wants, so the fix is a specification sentence, not hardware — but as written,
`machine.md` §5 item 4's "closes at ÷12" is not established. (The map SRAM also adds
15 ns to A13–A19 validity; doesn't change the slot math, but §11's "decode 15"
starting at t_AD ignores it.)

### Vid-M3 — MAJOR: sync polarity is never specified, and it is mode-critical

VGA monitors identify the vertical format **by sync polarity**: 640×400@70 is
HSYNC−/VSYNC+; 640×480@60 is HSYNC−/VSYNC−. The card offers both 449- and 525-line
modes via `VMODE`, so VSYNC polarity must flip with the mode or monitors will
mis-size the picture. One XOR term per sync output in the sync GAL — but it must be
in the spec and the GAL fit, and it isn't mentioned once in 1,326 lines.

### Vid-M4 — MAJOR: the analog back end is unbuildable as listed

**Where:** `graphics.md` §9, §13 (+$16), §14. Three stacked problems:

1. **No drive stage.** Proper VGA drive is double-terminated: 75 Ω source into 75 Ω
   load. An R-2R ladder's Thevenin impedance must then be ~75 Ω, whose MSB leg
   (150 Ω) pulls ~33 mA from a 74AHCT574 pin rated ±8 mA. Output sag is load- and
   code-dependent — the 6-bit green channel's DNL is destroyed before build step 1
   can measure it. Every credible discrete design buffers the ladder (three NPN
   emitter followers, or a 75 Ω-aware driver network). Zero packages are budgeted;
   there is no termination or black-level arithmetic anywhere.
2. **Blank-to-black has no mechanism.** RGB must sit at 0 V during porches and sync
   (monitors clamp black on the back porch). The post-LUT '574s hold the last pixel;
   /OE floats the ladder. Forcing index 0 upstream is wrong because palette entry 0
   is programmable. Blanking must act *after* the LUT; the spec never says how.
3. **`BORDER` (+$16) describes something VGA timing doesn't have.** 640×400@70 has
   porches, not overscan. Painting porches corrupts back-porch clamping; a reduced
   active window appears nowhere; and the '153 pixel mux has no spare input through
   which a border index could be injected. Delete the register or specify the
   window.

### Vid-M5 — MAJOR: §5.2's "by a wire, not a state machine" is wrong

Static phase-locking fixes *when* the CPU's access happens, but **which chip** it
hits is `address[1:0]` — dynamic, per access. The span writer may use "the other
three chips" only after a live compare of the CPU's low address bits against the
span's current chip, with the CPU access possibly absent entirely. That is a small
but real arbiter — decode terms and a grant per chip — not a wire. Related: `/WAIT`
stretch granularity must be an integral number of fetch slots to preserve the static
phase; implied, never stated.

### Video — MINOR

- **Vid-m1.** Q lead stated as "3 dots" unconditionally — correct only at ÷12; at ÷8
  it must be 2 dots. As written, the divider spec bakes a 135° error into fast mode.
  A real HD63C09E in the socket cares.
- **Vid-m2.** IC count internally inconsistent: §0 says "~33 (37 with the mux)", §14
  sums to 36 with the mux, 32 without — and §6.1/§14 make the mux the *default*. The
  honest headline is 36 (39 with Vid-M1's latches), not "~33".
- **Vid-m3.** Power estimate contradicts the doc's own per-GAL figure: 8 GALs at
  "~70–90 mA each" is already 560–720 mA, above the stated 450–650 mA card total,
  before four AS6C1008s and three fast SRAMs. Realistically 1.2–1.6 A — matters for
  the regulator and backplane power pins.
- **Vid-m4.** HSYNC (and a frame reference) are missing from the backplane list. The
  raster-compare timer counts HSYNC pulses but has **no origin** without VSYNC or an
  equivalent frame reset; resynchronizing in the VBL handler jitters by IRQ dispatch
  latency (±1 line).
- **Vid-m5.** The scan-address GAL pair is at exactly zero macrocell margin before
  tile mode: 18–19 of 20 macrocells committed for Rev A, before §6.4 asks for
  anything, and the mode/polarity terms (Vid-M3) land on the same pair's neighbours.
- **Vid-m6.** The hblank spare-access figure is ~10 % optimistic (charged at raw
  72 ns cadence instead of the 158.9 ns slot grid). Harmless at 80× headroom; noted
  because the table is quoted downstream.
- **Vid-m7.** `VSTAT`'s live bits (SPANBUSY/VBLANK/HBLANK) have no path to the data
  bus in the BOM — they need a tri-state driver ('244 or product-term OEs on
  already-contended sync-GAL macrocells). Unstated either way.
- **Vid-m8.** Palette writes during active display will snow: the '593 index counter
  and pixel-index '574 share the LUT address bus, so a mid-line CPU palette write
  steals LUT cycles inside the 39.7 ns pipeline. Restrict writes to blanking or
  accept glitches — `video-comparison.md` claims "mid-frame palette writes: yes"
  without confronting this.

### Video — NOTE

- 22V10 outputs are totem-pole; the open-drain idiom for `/IRQ`/`/WAIT` (data on OE)
  works but burns the per-macrocell OE product term — state it.
- Fetch-latch clocking must be per-chip, mid-slot — consistent with Vid-M2's
  spare-first ordering; one more reason to write that ordering down.
- `video-comparison.md` faithfully mirrors `graphics.md`, including the 36-vs-33
  count confusion, and repeats "steals CPU cycles: never" (true only once Vid-M5's
  arbiter exists).

---

## 4. Audio

### Verified clean

The DAC datasheet claims check out exactly: the AD7545's 250–400 ns write time at
VDD = 5 V confirms "a plain AD7545 does not close at a 281.9 ns frame," and every
LTC7545A number the spec relies on (tWR 100 ns, settling, glitch, pinout, the
transparent-latch caveat) is confirmed in the datasheet. Tempo arithmetic holds end
to end (709,379 Hz CIA clock; 50.002 Hz at BPM 125); period math, the period table's
four invariants, the 65-level volume law, the shadow-reload/one-shot idiom, and the
LEN=0 → 65536 behaviour all verify. The §10 IC tally sums to 35 as listed — the
problem is what's missing from the list, not the addition. The build passes and both
CTest tests pass. The replayer's position logic (Bxx+Dxx, E6x loops, F00-ignored)
matches documented ProTracker behaviour, with the exceptions below.

**The pattern:** the pieces cross-checked against something independent (DAC
datasheets, libopenmpt, pt2-clone) are solid; the failures cluster exactly where
nothing external pushed back — the analog signing path, byte-serial register
semantics, the LED filter order, and the PT corners the probe ladder doesn't reach.

### Aud-M1 — MAJOR: signed samples are fed to a unipolar-coded DAC; the offset-binary conversion exists nowhere

**Where:** `audio.md` §6.2/§6.3; `refplayer/card.c` (`card_dac` returns
two's-complement).

The AD7545/LTC7545A transfer function takes **unsigned binary**; bipolar operation
requires **offset-binary** data — the AD7545 datasheet's own application circuit
inverts the MSB to convert two's complement. Fed two's complement, every zero
crossing (`0xFFF` → `0x000`) is a full-scale output jump: the card as drawn produces
garbage. The bipolar circuit also needs two op-amps per side (I/V + offset
subtractor); §7 allots one. **Fix:** invert the accumulator MSB into DB11 (one GAL
term — but note the two-term sum must then handle the doubled offset deliberately),
and either add the offset amp or document the offset-drift trade. One paragraph in
§6.3; garbage audio without it.

### Aud-M2 — MAJOR: §6.2's "combinatorial, asynchronous" channel sum has no adder in the budget — or contradicts §3.4

A continuous combinational 13-bit `ch0+ch3` / `ch1+ch2` needs ≈8 '283 packages that
appear nowhere in the 35-IC tally (the listed four are assigned to slot-6/7 work).
The alternative — sequential accumulation through the shared '283 into the '574
accumulators — is what §6.2's own "held in the accumulators (slots 0–3)" hints at,
but then §3.4's "adder only in slots 6–7" is false and the '283 needs an unbudgeted
mux. The two sections cannot both be true. **Fix:** pick the latched-accumulator
version (cheaper, still updates the DAC on the exact colour clock), rewrite
§3.4/§6.2 consistently, re-tally §10.

### Aud-M3 — MAJOR: no atomicity story for multi-byte register writes; "one clock domain" is wrong at the host boundary

Paula's registers are written in one 68000 bus cycle; this card's arrive a byte at a
time from an asynchronous 2.098 MHz E bus. Consequences never mentioned: a torn
`PER` write leaves an out-of-range period live for ~8 colour clocks (the model
reproduces this); the 5-byte loop-shadow write (`LC`×3 + `LEN`×2) leaves a ~40-cc
window in which a one-shot exhausting mid-write reloads a torn pointer — a fetch of
arbitrary RAM, intermittent, exactly the bug class §16 item 13 kills for the enable
path but not here. The model itself already gave `TIMER` commit-on-low-byte
semantics because tearing broke it — but not `PER`/`LC`/`LEN`. And no synchronizer
for /IOSEL·E into the 28.375 MHz domain is enumerated anywhere; §9.3's "no /WAIT
path at all" makes that unspecified synchronizer the only defense. **Fix:** specify
commit semantics per field (multi-byte fields double-buffered, committed on the last
byte), state the two-flop synchronizer, correct §0 to "one *internal* clock domain,
asynchronous host port."

### Aud-M4 — MAJOR: the "LED" filter is specified, modelled, and test-enforced as 5-pole; the real A500's is 2-pole

The A500 chain is a fixed 1-pole RC (~4.4 kHz — §7 has this right) plus a
switchable **2nd-order** Sallen-Key at ~3.2–3.3 kHz. Every faithful model
(pt2-clone, libopenmpt `a500`) implements LED as 2-pole; `render.c`'s 3275 Hz
corner is itself pt2-clone's 2-pole corner transplanted under 4 poles. Built as §7
says, LED-on material is ~24 dB/oct darker than a real A500 — a direct violation of
the "Paula-exact" acceptance test, and the unit test now guards the wrong response.
The A/B ladder didn't catch it because no probe toggles `E0x`. **Fix:** one
Sallen-Key stage per channel in §7 (also −1 op-amp), two poles in `render.c`,
retarget the test, add an `E0x` probe against libopenmpt's `a500` LED behaviour.

### Aud-M5 — MAJOR: the 35-IC budget omits the host-pointer counters (~41 bits of state)

`SPTR` (19-bit auto-increment), `LIDX` (16), `AIDX` (6) = 41 flops of counter, plus
`INTENA`/`INTREQ`/`DMAEN`/prescale/slot-counter/queue state, against 3 × GAL22V10 =
30 macrocells total — which must also hold the entire sequencer. Either ~5 more
counter packages (or a 4th/5th GAL) are needed, or the state lives somewhere
unstated. (Smaller cousin: §9.3's argued-for `ADATA` read-prefetch latch has no
package listed either.) **Fix:** enumerate where every host-visible counter bit
lives before quoting "35"; expect an honest 38–42.

### Aud-M6 — MAJOR: the register trace — "the contract" — is missing tick 1 entirely

**Where:** `refplayer/main.c:131` vs `:136`. Confirmed by running: `mod_start()`
executes before the `--trace`/`--rowtrace` files are opened, so every trace begins
at tick 2 — row 0's `LC/LEN/PER/VOL` writes and the `ADMACON` stop/start pair are
absent. The README's own example excerpt is unproducible by the current code. A 6309
replayer that plays row 0 *correctly* will fail the trace diff at line 1. **Fix:**
open trace files before `mod_start()`; regenerate stored references.

### Aud-M7 — MAJOR: the loader's capacity check compares against the 512 KB footprint, not populated RAM

**Where:** `refplayer/mod_load.c:163`. Confirmed by running: a 180 KB-sample module
loads "successfully" at `--ram 128` — directly contradicting `modplayer.md` §4.7
("Reject with a clear message. The default."). On hardware this is fetching
unwritten SRAM at 28 kHz — §4.6's nightmare case. The error message even prints the
populated figure; the bound is just wrong. No unit test covers §4.7, which is why it
survived. **Fix:** compare against `c->sram_bytes`; add the rejection test.

### Aud-M8 — MAJOR: `3xx` tone-portamento speed memory ignores note-less parameter updates

**Where:** `mod_replay.c:384`. ProTracker updates the slide speed on every tick the
effect carries a parameter, note or not; modules routinely accelerate slides with
note-less `305 → 310 → 320` rows. Confirmed by probe: refplayer holds the old slope
forever. The A/B ladder's `05_toneporta` probe never varies the parameter without a
note, so it passes. **Fix:** update `porta_speed` from a nonzero param in the
per-tick `case 0x3` (and ensure `0x5` does *not*); add a probe.

### Aud-M9 — MAJOR: the A/B harness's tuning check has 50-cent resolution

**Where:** `tools/modcompare/abcompare.py:128` (and `ladder.py`): the spectral
cross-correlation runs at 24 bins/octave — 50 cents per step — then thresholds at
±12 cents, which an integer multiple of 50 can only pass at exactly 0. The design
brief is about errors of exactly this size: the NTSC-clock mistake is +16 cents, the
worst table transcription error 16 cents, finetune steps 12.5 cents — all invisible.
Both READMEs cite "+0.0 cents" as a closed exit criterion; the instrument cannot
support the claim. **Fix:** parabolic interpolation of the correlation peak, or FFT
peak interpolation on a single-note probe (~1-cent resolution); restate the claim.

### Audio — MINOR

- **Aud-m1.** Register-map fork: `audio.md` §9.2 puts 8-channel mode at **b4**;
  `card.h` defines it at **b3**. The map is "the deliverable to freeze"; freeze it
  un-forked.
- **Aud-m2.** ⚠ **WRONG — disproved by measurement; see Resolution status above. The
  behaviour was kept and is now pinned by a test.** Tick-0 rewrites `PER` to the base
  period during sustained vibrato/tremolo — an extra write PT never issues (confirmed in trace: a one-tick
  snap to base at every row boundary). Baked into the trace the 6309 port must
  reproduce, forcing it to replicate non-PT behaviour. Suppress the tick-0
  `set_per` for channels running effect 4/6/7.
- **Aud-m3.** `EDx`×`EEx` is documented as load-bearing (`modplayer.md` §10.10) but
  not implemented — a pattern-delay repeat never re-reads the row, so the delayed
  note triggers once total. Implement or move to the documented-as-ignored list.
- **Aud-m4.** `EC0` never cuts (no tick-0 `0xC` case) and `E9x` misses PT's tick-0
  retrigger on note-less rows.
- **Aud-m5.** `9xx` divergences: offset memory updates only on trigger (PT: whenever
  seen); `E9x` retrigger discards a prior `9xx` offset; offset-past-end maps to the
  null loop where PT sets length to one word. Document or fix.
- **Aud-m6.** Stale `break_pending`/`jump_pending` leak across an `E6x` loop-back —
  a `Dxx`/`Bxx` sharing the row fires one row *after* the loop, a teleport PT does
  not do.
- **Aud-m7.** `--ntsc` is clobbered: `mod_start` rewrites `ACTRL` from a shadow that
  never carries the NTSC bit, so any later `Fxx` recomputes tempo against PAL —
  0.92 % error mid-song. (`--led`/`--bypass` similarly bypass shadow and trace.)
- **Aud-m8.** 15-sample Soundtracker repeat offsets are in **bytes** in the original
  format; `mod_load.c` treats them as words, halving/misplacing loop points, and the
  all-names-printable heuristic bounces genuine STK files. The README's corpus row
  has no test.
- **Aud-m9.** No timer enable/stop bit exists in the map (§8.2 promises one; §9.2
  allocates none; in the model a written timer can never be stopped) — there is no
  clean "stop the music" path. Assign `ACTRL` b6.
- **Aud-m10.** `AINTREQ` write with b7=1 *sets* request bits in the model;
  §9.2 documents only the clear form. Document the Paula-style set or remove it.

### Audio — NOTE

- §4.1's headline example says C-2 = 8286 Hz; 3,546,895/428 = 8287.1 (the test
  asserts 8287).
- The model's CIA reload is one cycle short of a real 8520's latch+1 (0.007 % —
  irrelevant, but "CIA-B-identical" is the claim).
- Attach modulation wraps channel 3 → 0 in the model; Paula's channel 3 modulates
  nothing.
- `ASTAT` b6/b7 semantics are placeholders; the map freeze should define them.
- Six /FIRQ sources OR-ed onto an open-drain line need an open-collector stage a GAL
  output can't provide; no '05/'07 in the §10 tally.
- `AINT_FIFO` is dubious as motivated: §13.2 proves TFM can never fill the depth-1
  posted-write path, so the drain interrupt has no consumer.
- `modplayer.md` §2.2's 15-sample table has the order list at 470 (it's 472; the
  code is right); `audio.md` §13.2 says 128 KB is three TFMs, `modplayer.md` §4.4
  says two — it is three (65,535 + 65,535 + 2).
- Test hygiene: `test_refplayer.c` writes probe files into the CWD; no tests for
  torn writes, §4.7 rejection, 15-sample loading, or any replayer effect (effects
  are covered only by the out-of-CI Python ladder).

---

## 5. I/O — PS/2

### Verified clean

The classic receive-only mistake is *not* made: host-to-device transmit, `F4`,
`F3`+rate, and the correct inhibit sequence are all present and correct, as are the
mouse packet format and the b3-based resync. Interrupt arithmetic is exact
everywhere checked (0.86 %/3.4 % at 180 int/s; the quadrature rejection's 76 %
figure; machine.md's 9 %/37 % serial figures). IC tallies (9; fallbacks 13 and 5)
add up. Register maps fit and match `machine.md`. The HCT-Schmitt conditioning
argument is sound, and pull-ups are in the BOM.

### IO-P1 — CRITICAL: the "one byte of buffering = one full frame time" claim is false

**Where:** `ps2.md` §5, §4.1 idea 2, §6.1 step 2.

The no-FIFO decision — the card's central engineering claim — rests on the '595
storage register holding byte N "while the next frame shifts in." It does not.
`RCLK` is driven by `Q0` of the '193, which toggles on every clock edge of every
frame, so the storage register is re-copied from the shift register throughout the
*next* frame. For the capture to work at all, `Q0` must rise on odd edges (1, 3, 5,
7, 9) — and edge 1 of frame N+1 is its start bit, at which point the storage
register is overwritten with garbage (frame N shifted once more). Byte N is valid
only from edge 9 of frame N until **edge 1 of frame N+1**: the service deadline is
the inter-byte gap — device-dependent, possibly a few hundred µs inside a mouse
packet — not 660 µs of frame time. One NitrOS-9 dispatch at the 400-cycle guess is
already 191 µs, before the shared-/IRQ chain polls video's sources, before the
handler runs. And with no parity/framing check, a torn or garbage byte is
indistinguishable from a good one. (Separately: "660 µs at the slowest clock rate"
is wrong on its own terms — 660 µs is the *fastest* clock; the slowest gives
1.1 ms.)

**Fix:** either (a) a second-stage latch per port — a '574 clocked by `~TCD`
captures at end-of-frame, making the buffer genuinely one frame deep (+2 ICs); or
(b) keep the hardware and document the true deadline, and make §13 step 1's scope
measurement of the **mouse intra-packet inter-byte gap** an explicit gate on the
no-FIFO decision.

### IO-P2 — MAJOR: the '193 is never loaded

**Where:** `ps2.md` §4.3, §6.1, §8.2.

The doc says the '193 idles "preloaded" but never says with what value or by what
mechanism — the datapath shows no connection to `/PL` or the preset inputs. Worse,
`KRST` is specified as holding the '193 "in reset" — but '193 `MR` forces **0000**,
not the preload; a down-counter released at zero borrows on its first edge, sets
`DR` immediately with garbage, and every subsequent frame is misaligned. The value
matters too: correct capture requires an even preload (10 lands the borrow on edge
11, the stop bit); 11 captures the wrong eight bits. Between frames the counter must
self-reload (`~TCD` → `/PL`, as the Minimal 64x4 does); never drawn.

**Fix:** preset inputs strapped to the frame count, `~TCD` wired to `/PL`, `KRST`
driving `/PL` held asserted (not `MR`); record the preload value where §13 step 2's
breadboard can falsify it.

### IO-P3 — MAJOR: no power-on reset anywhere on the card

`/RESET` is not an input to any IC on the card (contrast the serial card, which
wires it). At power-up the `IOCTRL` '574 and the GAL's `DR` latches are random: the
card may hold both ports' clock lines low (inhibiting the devices' power-on BAT),
and `IRQEN` may wake up 1 with a `DR` latch stuck set — the OS enables `/IRQ` for
the VBL tick *before* the PS/2 driver runs, so a stuck `DR` holds `/IRQ` low with no
handler that clears it: interrupt storm, boot hangs.

**Fix:** swap the '574 for a 74HC273 (same register + `/MR`; `IOCTRL` never drives
the bus, so the '574's OE is unused anyway) wired to `/RESET`, and add `/RESET` as a
GAL input clearing both `DR` latches. Zero IC-count change.

### IO-P4 — MAJOR: software transmit cannot survive concurrent input traffic

**Where:** `ps2.md` §7, §11.2.

§7's only concurrency rule is "not inside an interrupt handler." The missing half:
transmit at task level *with interrupts enabled* is corrupted **by** handlers — the
host must present each bit within one device clock-low half-period (30–50 µs by the
doc's own table), and one dispatch is 48–191 µs. One mouse byte or serial byte
landing mid-transmit blows several bit slots; the device answers `FE`; the driver
retries into the same traffic. And transmit is not boot-only: caps-lock `ED` updates
happen during live typing with the mouse streaming, forever.

**Fix:** document that the per-bit loop runs with `/IRQ` masked (~0.8–1.3 ms per
frame) — then confront the cost: at 19,200 baud the 6551's inter-byte deadline is
521 µs, so a masked LED update mid-download **guarantees a serial overrun**
(recoverable only if flow control actually works — see IO-S2), and it can tear a
concurrent mouse byte (IO-P1). This §7 ↔ `serial.md` §5 interaction is recorded in
neither document.

### PS/2 — MINOR / NOTE

- **IO-P5 (minor).** 60 samples/s is a standard PS/2 mouse rate the doc's table
  omits, and by the doc's own criterion (largest standard rate under the 70.09 Hz
  frame rate) the answer is 60, not 40. 40 is a defensible economy; the stated
  justification is wrong and the menu misstated.
- **IO-P6 (minor).** The '132 NAND conditioning **inverts** CLK/DATA — load-bearing
  for the receive path, but it also means `IOSTAT` presents inverted line states,
  and §7's transmit walkthrough is written in true-line polarity. All four '132
  gates are consumed; nothing can re-invert. One sentence defining register polarity
  saves a debugging session.
- **IO-P7 (minor).** Pause is eight bytes in set 2 (`E1 14 77 E1 F0 14 F0 77`), not
  seven.
- **IO-P8 (note).** No +5 V provisioning for the connectors — a keyboard draws
  ~50–100 mA from mini-DIN pin 4; a polyfuse per port is standard on a hot-pluggable
  connector.

---

## 6. I/O — Serial

### Verified clean

The W65C51N TDRE erratum is real and the R6551A/G65SC51 sourcing response correct.
The 6551 register layout, read-STATUS-clears-IRQ, programmed reset, the
15-rate/19,200-max baud generator, and the tie-/DCD-and-/DSR-**low** warning are all
correct — the last prevents the classic dead-card build. 6551-on-6809-E is genuinely
precedented (Deluxe RS-232 Pak), and the 6850+MC14411 and bit-bang rejections are
correctly argued. NitrOS-9's `sc6551` driver does exist (the doc's §13 item 2 can be
graded up after the ten-minute check it prescribes).

### IO-S1 — MAJOR: ÷8 mode is never addressed; the speed-grade analysis stops at 2.0979 MHz

The 6551 sits directly on E as φ2. §3.3 works the numbers only at 2.0979 MHz ("a
2 MHz R6551A is 5 % over"). At ÷8, E = 3.147 MHz is **57 % over** that rating and
over 3 MHz CMOS grades too; only a genuine 4 MHz G65SC51 covers it. Any software
that flips into ÷8 with the serial driver live takes the ACIA out of spec
mid-session. Compounding: §3.3 offers `/WAIT` ("stretch E") as the *slow-down*
escape hatch while `machine.md` §1 uses "stretch mode" as the name of the *faster*
÷8 rate — the documents use "stretch" for opposite things. **Fix:** require the
`G65SC51-4` explicitly, or record "serial not guaranteed in ÷8" in `machine.md` §5
item 4; rename one of the stretches.

### IO-S2 — MAJOR: "/RTS wired ⇒ overrun becomes throttling" describes a 16550, not a 6551

On the 6551, `/RTS` is a command-register bit, not receiver-driven — and the 2-bit
field's only RTS-deasserted code **also disables the transmit interrupt**. So:
throttling is software flow control over a hardware wire (ISR-driven at a
ring-buffer high-water mark); while throttled, interrupt-driven transmit is off; the
far end delivers 1–2 more characters after `/RTS` drops, so the mark needs headroom;
and during any /IRQ-masked window longer than 521 µs at 19,200 — which the PS/2
card's transmit creates for ~1 ms (IO-P4) — the overrun has already happened.
(`/CTS` *is* automatic on the transmit side; that direction is fine.) **Fix:**
rewrite the §5 bullet with the real mechanism and cross-reference the PS/2
interaction from both documents.

### Serial — MINOR / NOTE

- **IO-S3 (minor).** The throughput table counts receive interrupts only; full
  duplex (terminal echo, XMODEM ACKs) doubles it — up to 3,840 int/s at 19,200,
  i.e. 18 %/73 % at the doc's own dispatch figures. The 4800–19,200 ceiling
  survives but shifts toward the low end; the table should say it is
  receive-only.
- **IO-S4 (minor).** "Straight-through cable to a modern USB-serial adapter" is
  wrong: both ends are DTE, so the first cable anyone plugs in must be a
  **null-modem crossover**.
- **IO-S5 (minor).** `/DSR`/`/DCD` transitions raise unmaskable status interrupts;
  strapped low they never fire, but §8's contemplated second-MAX232 modem variant
  would interrupt on every carrier drop, and §10.2's handler sketch checks only
  RDRF/overrun.
- **IO-S6 (note).** The 6551's /IRQ being open-drain is probably right (NMOS parts
  document it) but the actually-sourced part will be one of two out-of-production
  families — add "IRQB output structure = open-drain" to §12 step 1's datasheet
  checklist; a push-pull variant needs a diode, but only if someone looks.

---

## 7. Storage

### Verified clean

Clock math (12.588 MHz burst clock, 635.7 ns burst vs 1,430 ns TFM interval, 2.25×
margin; 393.4 kHz init clock), throughput/latency arithmetic (3.01/3.81 cyc/byte,
537 KiB/s, chunk latencies, 1-in-7 interrupt-per-block odds), 6809-family phantom
reads (dummy cycles drive `$FFFF`, outside the geographic window — a classic killer
checked and absent), burst-vs-read-strobe overlap, chunk-boundary safety, the
49 µs masking budget vs the replayer tick, the MISO level path (2.48 V vs 2.0 V
V_IH — thin but real), and full consistency with `machine.md` all verify. The ÷8
case, which the doc never checks, also passes (1.5× margin).

### Sto-C1 — CRITICAL: §9.1's read sequence loses byte 0 and pollutes MOSI, by the doc's own register semantics

The listed sequence — send CMD17, poll `SDDATA` for the `$FE` token, write `$FF`,
then TFM — is broken twice:

1. **Byte 0 is destroyed.** §6.2 defines a write to `SDDATA` as "load the MOSI hold
   register **and** trigger a burst," and every burst's completion latches the '595.
   The poll read that returned `$FE` has already prefetched data byte 0 — then step
   5's write triggers another burst whose completion latches byte 1 **over** byte 0.
   Every block is shifted by one, silently — exactly the failure mode §9.1 itself
   warns about, designed into the listing.
2. **MOSI is wrong during polling.** During the token poll the hold register still
   contains CMD17's last byte and replays it on every poll burst; SD hosts must hold
   DI at `$FF` while awaiting a response, and a replayed byte with bit7=0/bit6=1 can
   parse as a new command start.

**Fix:** write `$FF` once immediately after the sixth command byte, *before*
polling; or define the reserved `+$3` as a non-triggering hold-register write.
Either way §9.1 must be rewritten.

### Sto-M1 — MAJOR: the write path ignores the SD write protocol; the 680 KB/s write claim is off by several ×

§9.2 has no start token, no CRC bytes, no data-response token, and no **busy phase**
— after a write, the card holds DO low while programming, typically 250 µs–several
ms per block (spec allows 250 ms). Programming time, not SPI clocking, dominates
sustained writes; a typical card sustains 100–300 KB/s on single-block writes
regardless of how fast TFM feeds it. **Fix:** write §9.2 as a real sequence (token,
data, CRC, response check, busy poll) and restate the rate as transfer-bounded-by-
program-time, measured at §12 step 5.

### Sto-M2 — MAJOR: sustained-read claims omit command and access latency; CMD18 never considered

The "30 KB in 56 ms" figures are pure transfer time × block count. Each CMD17 also
costs 6 command bytes + NCR + **read access latency before the `$FE` token**
(typically 100 µs–1 ms+, spec ceiling 100 ms) — at ~1 ms per block, effective
throughput halves. CMD18 READ_MULTIPLE_BLOCK — zero extra hardware, and how
CoCoSDC-class devices actually get their sustained rates — is absent from the
document. **Fix:** add CMD18/CMD12 to §9; restate 537 KB/s as the intra-block
ceiling; make §12 step 7's exit criterion sustained multi-block rate.

### Sto-M3 — MAJOR: no R1 check, no error tokens, no timeouts — the driver as specified hangs or corrupts on any error

§9.1 polls for `$FE` with no R1 response check first: a failed CMD17 (bad address,
card removed) never sends a token and the loop spins forever; an error token
(`000xxxxx`) is skipped as filler. No timeout is specified anywhere. Hot-plug has no
story: `CD` exists in `SDSTAT` but there is no card-change handling, and a card
swapped mid-mount corrupts the filesystem silently. **Fix:** specify R1-with-NCR-
timeout, 100 ms token timeout, error-token decode, and a VBL-tick CD poll driving
invalidate + re-init.

### Sto-M4 — MAJOR: the init sequence is unspecified — and the only listing implies fast clock before init completes

The entire init dialog — CMD0 (CS low, CRC `$95`), CMD8 (CRC `$87`, check-pattern
echo), ACMD41 loop with HCS, CMD58/CCS, CMD16 — appears nowhere; §9.1 as literally
written switches to the fast clock at step 2, before init, violating the spec's
≤400 kHz init requirement. **SDSC vs SDHC addressing (byte vs block argument) is
never mentioned** — getting it wrong reads the wrong sector silently. With no CRC
hardware, the two mandatory CRCs must be stated as hard-coded constants. **Fix:** a
§9.0 init sequence; scope §9.1 as "card already initialized"; record the SDHC/SDSC
branch (or require SDHC-only, which also serves §13 item 3's known-good-card plan).

### Sto-M5 — MAJOR: the doc treats TFM resume behaviour as immutable silicon — but the CPU is the project's own firmware

§4 frames the hazard as "undocumented CPU behaviour" to be *discovered*. But this
machine's CPU is C11 on an STM32; the silicon capture exists to decide what the
emulator *implements*. The option §4.3's "hardware cannot fix it" list never
considers: implement TFM interrupt recognition as
complete-current-byte-then-resume-without-re-read. That deletes the hazard, the
chunking, and the 21 % tax (537 → 680 KB/s), at the cost of a fidelity divergence —
gate it per-SKU or behind a mode bit, and put it in the divergence ledger the
machine already keeps. Whether to reject it on fidelity grounds is the owner's call;
a document whose central section is this hazard must at least price the option.

### Sto-M6 — MAJOR: §9.2 contradicts §4.4 on write-side interrupt safety

§9.2 asserts writes "need no chunking and no masking," but the write is `TFM X+,Y`
against a port whose *write* has a side effect, and §4.4 itself admits the capture
might show "a doubled write" — which would duplicate a byte mid-block and
desynchronize the CRC/response/busy sequence: the same silent corruption, on the
path declared safe. §12 step 1's exit criterion asks only "whether the source is
re-read." **Fix:** extend it to "whether the destination can be written twice";
soften §9.2 to "pending step 1's answer." (The same exposure applies to
`modplayer.md` §4.4's audio upload if that port has write side effects.)

### Storage — MINOR

- **Sto-m1.** Power-up state of the MOSI hold register and `SDCTRL` is undefined:
  the 74-clock power-up sequence requires DI *high*, but the '574 holds garbage, and
  nothing says `/RESET` initializes the GAL's CS/clock-select bits. Make step 1
  "write `$FF` to SDDATA first" and specify /RESET forcing CS high + init clock.
- **Sto-m2.** Re-trigger during an in-progress burst is unspecified (a second
  `SDDATA` access mid-burst hits the '163 mid-count), and the GAL is already at
  10/10 macrocells, so a lockout term has nowhere stated to live. Specify
  lockout-while-BUSY or an explicit software prohibition.
- **Sto-m3.** MOSI hold-time race on the shared SCK edge: if the '165 shifts on the
  same rising edge the card samples, correctness rests on unspecified HC minimum
  propagation delays. Clocking the '165 on inverted SCK is robust but needs an
  inverter the card doesn't have. Also, the '393 is a ripple counter — state that
  the speed bit changes only with CS high, or runt SCK pulses result.
- **Sto-m4.** NitrOS-9 RBF sectors are 256 bytes; SD blocks are 512. The driver
  must deblock (read-modify-write on single-sector writes), which further degrades
  Sto-M1's write rate and strengthens §13 item 4's CoCoSDC-map suggestion. Never
  mentioned.
- **Sto-m5.** Unit sloppiness: 537/680 "KB/s" here are KiB/s; `modplayer.md` calls
  the same rate "~700 KB/s" decimal; §2 compares them as commensurate. Pick a unit.

---

## 8. Priority list

What to act on, in order. The grouping principle: decisions that gate a board etch
first, then correctness of things already "done," then paper fixes.

### Before any board is drawn

1. **Sys-C1 — decide the boot story.** Vector fetch, boot ROM, and the NitrOS-9
   load path. The STM32-serves-the-vectors answer costs zero ICs and one mode bit;
   whatever the answer, it is `machine.md` §5 item 0.
2. **Sys-M1 / Vid-C2 — add the I/O-page inhibit to the backplane spec.** One
   signal, one sentence, before the etch.
3. **Cpu-C1 — pick the CBU6 (UFQFPN48) or redo the pin budget.** One BOM line if
   decided now; a dead board if discovered at bring-up.
4. **Vid-C1 — redraw the MMU with its isolation buffer and address mux**, and
   restate its honest IC count (with Sys-M2's system RAM and Sys-M4/M5's
   electrical/power specs, this is really "specify the motherboard," which is
   currently four line items and no document).
5. **Aud-M1 / Aud-M2 — fix the DAC signing and the adder story** before the audio
   register map is frozen; **Aud-M3**'s commit semantics belong in the same freeze.
6. **IO-P1/P2/P3 — rework the PS/2 receive path** (second-stage latch or
   documented true deadline; '193 preload; reset). All three are wiring-level, cheap
   now.

### Correctness of things believed done

7. **Aud-M6/M7/M8 — fix the three confirmed refplayer bugs** (trace misses tick 1;
   capacity check against the wrong bound; portamento speed memory) and regenerate
   references. **Aud-M9** — fix the tuning harness before re-citing "+0.0 cents."
8. **Sto-C1 — rewrite `sdcard.md` §9.1** (the byte-0 loss), and add the init
   sequence, error handling, and write protocol (Sto-M1…M4).
9. **Cpu-M1/M2 — move the DMA variable out of CCM and settle BOOT0** before first
   silicon; **Cpu-M4** — tighten the latency gate before trusting a pass.
10. **Aud-M4 — make the LED filter 2-pole** in spec, model, and test.

### Repo, independent of hardware

11. **Sys-M6 — remove Mac-Plus.ROM and the CHM zips from the repo and its
    history**; add a LICENSE.
12. The documentation consistency sweep: the ÷8 compatibility table (Sys-m2,
    IO-S1, Cpu-m7 — three subsystems hit the same gap independently), the
    oscillator's location (Sys-m1), the IC-count sync (Sys-m4, Vid-m2), the
    "stretch" naming collision, and the stale `graphics.md` §17.

One observation to close on: the two questions this review kept answering were
"who owns this?" and "what happens when two things overlap?" The project's house
rule of a documented register map before a board has clearly worked — the maps are
the cleanest layer in the design. Extending the same discipline to a documented
*motherboard* (boot, RAM, reset, power, electrical) and a documented *concurrency
story* per card (what may interrupt what, and what state survives it) would have
caught most of what's above.
