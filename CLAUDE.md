# CLAUDE.md

## Documentation structure: present design vs. archived history

Since 2026-09-08 the docs are split in two (this replaced the old "superseded text
is marked, not deleted" convention — see the root `README.md` Conventions section):

- **Specs describe only the present design.** One spec document per card
  (`video3/docs/plan.md`, `audio/docs/audio.md`, `cpu/docs/plan.md`,
  `net/docs/net.md`, `storage/docs/sdcard.md`, `io/ps2/docs/ps2.md`,
  `io/serial/docs/serial.md`, `hardware/ram.md`, machine-level `docs/machine.md`).
- **Each component has a `history.md` beside its spec** archiving superseded
  claims, with dates and the reason each number moved. Machine-level history is
  `docs/history.md`; the hardware area shares one `hardware/history.md`.
- **`docs/design-review.md` and `docs/design-review2.md` are frozen dated records**
  (the 2026-09-04 review, and the 2026-09-09 simulation review). Never update their
  findings; the specs and history files carry what changed since.
- ⭐ **`archive/` holds retired designs, and its documents are frozen too.**
  `archive/video/` (the machine's video card until 2026-09-20) and
  `archive/video2/` (a plan, never built) moved there when `video3` became the
  machine's video card — `archive/README.md` and `docs/history.md`. ⚠ **An
  archived document is still citable as provenance**: this machine's backplane,
  slot model, arbitration rule and clock tree were designed in
  `archive/video/docs/graphics.md`, and the card being retired does not make
  those derivations wrong. What it is not is a statement about the present
  machine. `lib/docs.check.ts` exempts `archive/` for the same reason it
  exempts `history.md`.
  ⛔ **`video/`'s DESIGN SOURCES DID NOT MOVE.** They are still in
  `hardware/gal/`, still compiled by `gen.ts`, still instantiated by
  `machine.v` and so by **`demo_tb`** — and **checked by nothing**.
  `archive/README.md` §"What did NOT move" is the record of that trade.
  ⭐ **`machine_tb` left them on 2026-09-20**, when `software/boot/boot.asm`'s
  video POST was retargeted to `video3` and the bench moved to `machine3.v`
  (`docs/history.md` §7.2). So the only thing now holding those sources in the
  tree is `software/demo/`, whose raster bars and per-scanline palette writes
  have no `video3` equivalent.

### Reading rules

- A `⚠` in a spec marks a **live** hazard, constraint, or unverified assumption —
  never a revision. (`docs/coco3_c64.md` has its own ⚠ convention, declared in its
  header: "recalled figure, unverified against a primary document".)
- Trust precedence when documents disagree: **design outputs beat prose**
  (`hardware/gal/*.jedec.ts` / `*.pld` / `cpld/*.fit`, `hardware/cards/*.circuit.tsx`,
  `hardware/place/parts.ts`, `cpu/src/`, `cpu/include/`), then the latest-dated doc
  statement, then older ones.
- ⛔ **A design output can be absent, and prose does not notice.** `design-review2.md`
  (2026-09-09) found eleven blocks described as fitted with no cell behind them. Before
  citing a spec's "built" or "fitted", check that something *produces* the signal: the
  port census in `hardware/gal/verilog/` is what does it, and `npm run check:video`
  runs the design rather than its equations.
- Cross-document claims cite section numbers (`graphics.md §14.1`). Section numbers
  are stable — see the maintenance rules — so citations can be followed literally.

### Maintenance rules

- **When a design decision supersedes spec text, move the old text to that
  component's `history.md`** (entry keyed by spec section, with the date and what
  replaced it) and rewrite the spec in present tense. Do not leave strikethroughs
  (`~~…~~`), "used to say", "amended <date>", or superseded-`⚠` blocks in a spec.
- **Never renumber sections.** If a whole numbered section becomes historical,
  leave a one-line stub in place (e.g. `#### 6.4.3 Variant B (dropped 2026-09-08;
  see history.md)`) and move the body to history.
- Keep the rationale for the *current* design in the spec (condensed, present
  tense); only the revision narrative — what it used to say, who caught it, the
  chain of old values — goes to history.
- When changing a headline number (IC count, power, rate, address map), grep for
  it repo-wide: the root `README.md`, `docs/machine.md` §0/§8, the component
  `README.md`, and other cards' comparison tables usually quote it.
- History entries preserve the technical content verbatim or lightly trimmed —
  the archive is the record, not a summary.

## Running the checks

**Everything runs from `hardware/`.** `bun` is a `devDependency` and lives in
`node_modules/.bin`, so invoke these as npm scripts — `bun run …` from a shell
will not find it. The Verilator tests need `verilator` on `PATH` (5.020
verified); the CPLD fitter additionally needs `wine` and the WinCUPL extraction
under `~/.wine_atf` (`gal/prjbureau/extract-wincupl.sh`).

| | |
|---|---|
| `npm run check` | every GAL design against its own model, and the live ones against Atmel's CUPL. **641 claims, ~60 s** — ⚠ **895 until 2026-09-20**, when the archived `video` card's ten scripts left the chain and three surviving checks shrank (`docs/history.md`) |
| **`npm run check:video`** | ⭐ **the Verilator tests.** Regenerates the Verilog from the term lists, then compiles and runs six testbenches — `audio`, `mainboard`, `storage`, `v3dot`, `v3card`, `v3machine`. **320 claims, ~4 min** — most of it whole frames at 25.175 MHz, so budget for it rather than assuming it hung. ⚠ **435 over ten benches until 2026-09-20**: the archived `video` card's `vsync`, `vaddr`, `vtile`, `vspan` and `vpal` (115 claims) left the default `TBS` and are asked for by name |
| `npm run check:sim` | the two *hand-written* Verilog models, `gal/mmu.v` and `gal/clkdec.v`, with their own testbenches. Older and separate from `check:video` |
| `npm run check:netlist` | the motherboard's connectivity, against `dist/mainboard/mainboard/circuit.json`, and the video card's against `dist/cards/video/circuit.json` — what is drawn, and the nets with no producer on the board as a list checked both ways (`graphics.md` §19 item 34). **Build artefacts**, so run `npm run build` first if a `.circuit.tsx` changed. ⚠ `tsci build` prints "Build completed with errors" and exits 0 when it cannot reach the supplier API; connectivity is unaffected |
| `npm run gen:pld` | writes `gal/{vaddr,vctrl,vsup,audio,aseq}.pld` from the term lists |
| ⭐ **`npm run check:machine`** | **the whole machine**: a 6809E core, the motherboard, **the `video3` card** and the audio card (`machine3.v`), running `software/boot/boot.asm` out of the boot ROM, and a screenshot taken off `RGB`/`BLANK`/`HSYNC`/`VSYNC`. Seven runs: the boot on four SIMMs, the SIMM sizing walk against one, two and three sockets and an aliasing module, and two faults (no SIMM, a corrupted VRAM byte) in which the ROM's error path is the asserted answer. ⭐ **It ran the ARCHIVED `video` card until 2026-09-20**, when the ROM was retargeted; every motherboard claim and all six fault/population scenarios are unchanged, so what moved is the card. **146 claims, ~7.5 min** (133 and ~4 min on the archived card: video3 is a bigger model, and the POST does more); `SCENARIOS=main` for the boot alone. ⭐ **Four more runs, asked for by name**, and all of them need `../nitros9` on its `arm6309` branch (`software/nitros9/README.md`): **`SCENARIOS=nitros9`**, NitrOS-9 Level 2 from reset to a shell on the TL16C550C with `dir`, `mfree` and `firqtst q` on the audio card's `/FIRQ` (**19 claims, ~13 min**); **`SCENARIOS=reboot`**, boot, `reboot` back through `boot.asm`'s POST, and a second shell (**11 claims, ~14 min**); and ⭐ **`SCENARIOS="disk nodisk"`**, `boot.asm` §10a's **boot dialog** read off the connector pixel by pixel in both card-detect states (**52 claims, ~20 min** — `docs/boot-and-desktop.md` §1). ⛔ The last pair loads a **`V3=1`** ROM into `/tmp/arm6309-dialog`, because the toolbox is ROM page 64 and `recipes/arm6309/arm6309.mak` only builds it under that flag; the other two load the non-V3 one into `/tmp/arm6309-nitros9`, so they cannot share a directory |
| `npm run rom` | assembles `software/boot/boot.asm` with A09 → `boot.bin`, `boot.hex`, `boot.lst` |
| `sh gal/verilog/run-demo.sh 118` | **the whole machine with BOTH cards**, running `software/demo/`'s show from ROM — a desktop, an audio player, a paint program, a BBS, raster bars, the overworld — then: the card's register stream against refplayer, the card's sound A/B'd against libopenmpt, every checkpoint frame against `show.Model`'s picture and every game frame against the game model, and an H.264 file for the web. ⚠ **~4.5 h on a quiet host**, and not in any aggregate. ⭐ `sh ../software/demo/emu/run-emu.sh 120` runs the same ROM on the host emulator in seconds, and `checkdemo.py` reads either recording. `software/demo/bench/run-replay.sh` is the replayer alone on the CPU, in two minutes |
| ⭐ **`sh software/demo/emu/test/run-ps2script.sh`** | **the PS/2 input script**: `PS2_SCRIPT=file` gives the host emulator a timed, semantic keyboard and mouse script (`move to 320 240`, `click left`, `type "..."`), encoded into set-2 scan codes and 9-bit-split mouse packets and fed to `machine.c`'s **line-level** devices rather than past them (`io/ps2/docs/ps2.md` §11.5, `software/demo/emu/ps2script.h`). The bench encodes every script a SECOND time in Python (`emu/test/ps2check.py`), drives `ps2tst 24` on a booted NitrOS-9 and compares the bytes the 6809 echoed back off the card — plus a moves-and-no-clicks control, an empty-script control, and a corrupted-expectation run of each comparison that is **required to fail**. **27 claims, ~2 min**; needs `../nitros9` on its `arm6309` branch, so it is in no aggregate |
| ⭐ **`npm run check:reach`** | **every signal the machine produces must reach something.** `design-review2.md` closed the direction "a fitted part reads what nothing produces"; this is the other one — a signal that is *produced* and that nothing reads, which for a register bit means **a feature the host can write and the card cannot perform**. ⭐ **And since 2026-09-18 the same question of INPUTS** for video3: its four parts turned out to be a datapath and an arbiter with **neither sequencer built** — 19 control lines nothing produces. ⭐ Since 2026-09-19 video3's board is `video3_card.v` (a model, not a drawing), and counting against it found a macrocell nothing read. Part of `npm run check` |
| ⭐ **`npm run check:pins`** | **every programmable part's pin has the sense of what it is wired to.** The generated Verilog is in asserted sense and the wrappers invert by hand, so **no simulation can see a pin declared with the wrong polarity** — nine passed every check until 2026-09-11. Asserts backplane `/` signals are active-low, a signal crossing between two parts has one sense at both ends, and each pin in its `CONSUMERS` table matches the discrete part pin it drives. ⚠ It found three more on 2026-09-18, the day video3 was added to it. Part of `npm run check` |
| ⭐ **`npm run check:modplay`** | **a module plays on `audio_card.v`** — `14_fourchan.mod`, both stereo pairs — and its converter codes are rendered to a WAV and A/B'd against libopenmpt, with `refplayer` as the control. ⛔ **The A/B is a gate**: a card that scores worse than `refplayer` (level ±0.5 dB, envelope, spectral, tuning) fails the check. The bench log is kept as `/tmp/arm6309-modplay/<module>.log`. Needs `libopenmpt.so.0` and numpy, and says so before simulating |
| ⭐ **`npm run check:audio:all`** | `check:sim:audio`, `check:oracle` and `check:modplay` — **the audio card's three benches, ~5 min.** Not in `npm run check` (it needs Verilator and libopenmpt); `build:all` ends with it. ⛔ `audio_tb` alone passed through two audio regressions that `check:modplay` caught (`audio.md` §16 item 47) |
| `npm run build` | renders every `.circuit.tsx` to `dist/` with `tsci` |
| `npm run build:all` | all of the above in order — `gen:pld`, `build`, `check`, `check:netlist`, `check:sim`, `check:video`, `check:machine`, `check:audio:all` |

### `check:reach` — the census, and why it is not optional

⛔ **`ACTRL` b3 was latched, read back through `ASTAT`, and taken by no cell on
either CPLD for two days.** So `audio.md` §6.1's *"the card doing the ×4"* was
never built and the card sat 12.04 dB below every output level §7.1 specifies.
**Nothing caught it**, because every other check in this repository asks whether
a part computes its own equations correctly — and a bit nobody reads has no
equation to get wrong.

`gal/reach.check.ts` asks the other question. For each card it takes the term
lists and the hand-written board file and finds every signal that is produced
and read by nothing, then requires each one to be on a `RESERVED` list with a
reason:

| | |
|---|---|
| `open` | ⛔ **specified, allocated a bit, and not built.** These are the findings |
| `stale` | a bit for a feature that was **withdrawn**; the card correctly does nothing |
| `dead` | logic that costs a macrocell and buys nothing — the job moved and the cell stayed |
| `board` | its consumer is a discrete part the board model does not have. ⚠ **Not a free pass**: `check:netlist` is what should close it, and `graphics.md` §19 item 34 says that board is partial |

⚠ **The list is checked in both directions.** An entry that is *no longer*
unread fails too, so a feature that gets built has to be taken off it — which is
what stops `RESERVED` becoming a place to put things.

⚠ **Four bugs in this check's own first four runs are worth knowing, because
each of them made it report the opposite of the truth:**

- **a cell reading itself is not a consumer.** Every registered bit holds with
  `X & !STROBE`, so a naive scan finds all of them "read" — it reported every
  `ACTRL` bit as live.
- **a port map is not a use.** `.MAPCE_LO(mapce_lo)` says the pin was wired to a
  net; whether anything reads that net is the question. Follow the alias.
- **`wire x = expr;` is a continuous assignment wearing a declaration's
  clothes.** Stripping declarations took the uses with them and reported the
  whole of U3 as dangling.
- **`HOSTMAP` is not evidence.** Being host-writable is exactly what `DAT`,
  `ATT` and `PAN` already are; reading the host map as a consumer is the check
  answering its own question.

### The CPLD fitter and CUPL — how to get them, and how to know they worked

⚠ **A fresh clone has no fitter, and `npm run check` still passes without one.**
The Atmel toolchain is not a dependency of the model checks — it is the thing
that answers *does the design still fit the part*, which no model check can — so
its absence is **silent**. **Set it up before changing any `.jedec.ts`,
`video.cpld.ts`, `aseq.cpld.ts` or `audio.cpld.ts`.** The installer is tracked at
the repository root; nothing else is needed but `wine`, `7z` and `unzip`:

```sh
sh hardware/gal/prjbureau/extract-wincupl.sh awincupl.exe.zip    # ~1 min, from the repo root
# -> "fitters and CUPL in <repo>/.wine_atf/drive_c/Wincupl"
#    "Atmel ATF1508AS Fitter Version 1.8.7.8"
```

⭐ **The Wine prefix lives at `<repo>/.wine_atf`, not in `$HOME`.** This project is
developed inside a sandbox whose `$HOME` does not survive the session, so a prefix
under `~/.wine_atf` is extracted, used once and gone — and, per the paragraph
above, gone silently. It is **1.3 GB and `.gitignore`d**: a Wine prefix with
Microchip's WinCUPL inside it, which this project has no right to redistribute.
`$ATF_HOME` overrides the location and `$WINEPREFIX` / `$SHARED` / `$FITTERS`
override that, so a prefix you already have elsewhere keeps working.

Then, **from `hardware/`**, and after `npm run gen:pld`:

| | |
|---|---|
| `sh gal/prjbureau/fit1508.sh gal/vctrl.pld` | place and route one CPLD → `gal/cpld/vctrl.{jed,fit}`. Also `vaddr`, `vsup`, `audio`, `aseq` |
| `sh gal/prjbureau/cupl-reference.sh gal/arb.pld` | recompile one **GAL**'s reference JEDEC → `gal/jedec/reference/arb.cupl.jed` |

⛔ **`Error Code = 1` on the fitter's first line is normal noise and is not the
answer.** The answer is the sentence **"Design fits successfully"**, which
appears only in stdout and never in the `.fit` — `fit1508.sh` requires it and
refuses `INTERNAL ERROR`, and the two traps at the bottom of this file are why.
Read the utilisation out of the new `.fit` and compare it against the old one
(`Total Logic cells used`, `Total I/O pins used`, `Total cascade used`); a
change in cascades is a timing change even when the cell count is flat.

⚠ **Changing a GAL design breaks `check:cupl` until its `.pld` AND its reference
are regenerated**, and the failure names a fuse, not a file:
`FAIL CUPL arb.jed: matches our fuse map ... (GCPU0 at inputs 0000000011: ours 0, CUPL 1)`.
The `.pld` for a GAL is written by `toGalPld()` (`gal/jedec/galpld.ts`), so the
sequence is: edit the `.jedec.ts` → rewrite the `.pld` → `cupl-reference.sh` →
`npm run check`.

⚠ **One fit at a time, always** — the Wine prefix is one shared working
directory, and two concurrent fits write the same `cpld/<name>.fit`.

### The Verilator tests

`npm run check:video` is the one that runs the *design* rather than its
equations. It ends with a line like `435 claims, 0 failed`, and **its exit code
is the answer** — a testbench prints a failed claim and then calls `$finish`,
which exits 0, so the count is what decides the status. Read the `FAIL` lines;
each names the claim and the observed value.

⚠ **RUN ONLY THE TESTBENCHES THE CHANGE CAN REACH.** The full suite is ~3
minutes and most of it is whole frames of video that an audio-card edit cannot
touch. There are scoped scripts for exactly this, and `check:video` is for a
change to the video card, the mainboard, or `emit.ts` itself:

| changed | run |
|---|---|
| `audio.jedec.ts`, `aseq.*`, `audio_card.v`, `audio_tb.sv` | `npm run check:sim:audio` (~25 s), then ⭐ **`npm run check:audio:all`** before committing |
| the mainboard, `u9`/`u10` | `npm run check:sim:board` |
| `verilog/emit.ts`, or anything every card shares | `npm run check:video` (everything) |
| the **archived** `video` card (`video.cpld.ts`, `vsup.cpld.ts`, `sync`/`scan`/`access`/`seqph`/`seqctl`/`regfile`/`vlen`/`pxsel`) | ⚠ nothing runs by default, **and since 2026-09-20 no aggregate runs it at all**: `check:machine` moved to `video3` with the boot ROM. Its five benches are asked for by name — `bun run gal/verilog/gen.ts`, then from `gal/verilog/` `TBS="vsync vaddr vtile vspan vpal" sh run.sh` — and `sh gal/verilog/run-demo.sh` (~4.5 h) is the only thing left that executes the card as a card |
| the video3 card (`gal/video3/*.cpld.ts`, `v3lane.jedec.ts`, `video3_card.v`) | `bun run gal/verilog/gen.ts`, then from `gal/verilog/` `TBS="v3dot v3card v3machine" sh run.sh` (~4 min), refit every CPLD you touched, and for `v3lane` its check and `cupl-reference.sh` |
| anything the CPU touches — the map, the boot path, `boot.asm`, `machine3.v` | ⭐ **`npm run check:machine`** |
| the NitrOS-9 port, `tl16c550.v`, or anything NitrOS-9 boots through (the vectors, the map, the tick, the UART) | `sh software/nitros9/run-emu.sh` (~30 s) first, then ⭐ **`SCENARIOS=nitros9 npm run check:machine`** |
| the audio card's *behaviour* | ⭐ **`npm run check:oracle`** as well — this card against an independent Paula (`gal/verilog/oracle/`). It is what found `audio.md` §16 items 36 and 39, and `audio_tb` could not |

Or one at a time, from `hardware/gal/verilog/`:

```sh
TBS=vtile sh run.sh          # one; TBS="vsync vaddr" for several
```
⚠ `run.sh` does **not** regenerate the Verilog — `npm run check:video` does that
first. After editing a `.jedec.ts`, run `bun run gal/verilog/gen.ts` or a
`check:sim:*` script, or you will test the previous design and believe it.

| Testbench | Parts instantiated | What it asserts |
|---|---|---|
| `vsync_tb` ⚠ | the whole **archived** `video` card (`archive/`) — by name only since 2026-09-20 | raster geometry in all four `VMODE` codes, sync widths and **polarity**, blanking |
| `vaddr_tb` ⚠ | " | the bitmap scan address over whole lines, both scroll axes, both ring wraps, line doubling, who owns the internal address bus |
| `vtile_tb` ⚠ | " | the cell fetch cadence, both address concatenations, cell-mode scroll in both axes, the 32-row ring |
| `vspan_tb` ⚠ | " | all four `WMODE`s, the retire rate, `/WAIT`'s read/write rule, `WADV` chaining, the display list, the VBL interrupt |
| `audio_tb` | both audio CPLDs + the state file, the sample RAM, the adder and the converters | the slot walk, the ÷5 CIA clock, Paula's set/clear, open-drain `/FIRQ`, §9.4.5's merge, the six micro-op sequences — **and how many samples a buffer yields**, which is the claim two audible defects survived 43 green ones by not having (`audio.md` §16 item 36) |
| `mainboard_tb` | U3, U6, U9, U10 + the map SRAMs, `'157`, `'574`, boot `'244`, flash and SIMMs | the boot sequence, the 32 MB map, the four SIMM windows, `/IOPAGE`, and that exactly one thing drives physical `A20`–`A13` |
| ⭐ `machine_tb` | **`mc6809e` + the whole motherboard + the whole `video3` card + the whole audio card** (`machine3.v`), and a TL16C550C bus model | that the machine executes its own boot ROM: leaves boot mode with a map it wrote, finds its SIMM, **probes for the video card**, loads 256 palette entries, paints 640 × 200 with the span writer, chains 200 spans with `WADV`, shows all four `VMODE`s, runs the copy engine and the sprite, paints 2,000 tile cells two stores at a time, and reads VRAM back — every frame pixel for pixel. It reads DRAM and VRAM independently of the ROM's own compares, and runs `$E1`/`$E2` on purpose — **it found `graphics.md` §19 items 36, 37 and 38 on the card it used to run, and `video3/docs/plan.md` §14 items 20 and 21 on the day it was moved to this one** |
| ⭐ `modplay_tb` | **the whole audio card** | that a real module plays: samples uploaded through `SPTR`/`SDATA`, the register stream delivered on the card's own §8.2 tick interrupt, and the four `AD7528` pairs' codes recorded for `audio/tools/dacwav` |
| ⭐ `v3card_tb` | **the whole video3 card**: `v3dot`, `v3scan`, `v3ptr`, `v3host` and the `v3lane` GAL + `video3_card.v`'s framebuffer and lane `'245`s, register file, fetch ranks, `'153`, sprite `'165`s, LUT, latches and host `'245`, and a 6809E bus model that honours `/WAIT` the way `clkdec` does | the palette, direct `VDATA` writes and post-incrementing reads, the span writer in every mode, `WADV` chaining, a copy **at two accesses a byte** in bitmap and under character mode, and **whole frames pixel for pixel through an identity LUT**: bitmap at fine scrolls 1-3 and a two-axis wrap, the sprite at three positions in two families, character mode at 80×60 and 80×25 (two consecutive frames), tile mode at both cell phases. ⭐ **Every bus is resolved from explicit drivers** - FBA, the internal data bus, each lane, the LUT address - so a fight or a floating sample is a failed claim. The port maps are **generated** (`v3portmap.ts`, from `gen.ts`); `TBARGS=+ONLY=sprite,char` runs named groups for a debug loop. **It found fourteen defects `v3dot_tb` and 770 model claims could not, and then sixteen more** (`video3/docs/history.md`, 2026-09-19) |
| ⭐ `v3machine_tb` | **`mc6809e` + the motherboard + the whole video3 card** (`machine3.v`), running `software/v3boot/v3boot.asm` out of the boot ROM | that the machine executes a program against the card: the map it writes, the palette both ways, direct writes and post-incrementing reads, a span, a `WADV`-chained glyph, a copy, and a 400-line frame whose every pixel is the card's own LUT entry for the byte the ROM drew. ⭐ **And the three things only a CPU can ask**: a real instruction's bus cycle stretched to 987 dots by `/WAIT`, the VBL interrupt fetched and serviced, and an engine surviving the polls of its own `VSTAT`. **It found the palette commit firing twice outside vertical blanking on its first run** — 48 claims, ~40 s, 34 of them compiling the core |

**What is generated and what is written.** `verilog/emit.ts` turns a `Merged`
or a `Design` into Verilog from **the same `Cell` term lists `jedec/cupl.ts`
compiles for the fitter** — so `vaddr.v`, `vctrl.v`, `rfa.v`, `vlen.v`,
`audio.v`, `u9.v` and `u10.v` are build outputs and ⚠ **must not be edited**;
change the `.jedec.ts` and re-run. The card and board wrappers
(`video_card.v`, `mainboard.v`) and every `*_tb.sv` are hand-written.
`verilog/README.md` has the rest.

⭐ **AND THE ONE THING NONE OF THEM DID UNTIL 2026-09-10 IS EXECUTE AN
INSTRUCTION.** `mainboard_tb` walks `machine.md` §7.2's boot sequence as twenty
literal bus cycles and `vspan_tb` writes the video card's registers from a
task, so both check that each part does what its author thought when driven the
way its author expected. `machine_tb` hands the bus to a CPU core somebody else
wrote and lets the boot ROM drive, and **three defects fell out of the first run
that had survived everything else** (`graphics.md` §19 items 36–38). Each was a
seam: the arbiter refused the span writer the chip the CPU's own stalled write
was holding; `SPANBUSY` was set by a level over `E`-high, which `/WAIT` makes
unbounded; and §7.4's own "poll `VSTAT`" rule took the register file away from
the span whose colour that file *is*.

⚠ **The reason none of the older benches could see any of them is the same
reason**, and it is worth stating as a rule: **a testbench that drives `E` from
its own free-running counter has a CPU that cannot be waited.** `/WAIT` is the
only signal on this backplane that changes what the CPU does rather than what it
reads, and a harness that ignores it is testing a machine that does not exist.

⚠ **It models the logic and not the timing.** Propagation delay, the switch
matrix, product-term cascading and placement are `fit1508.exe`'s business and
`cpld/*.fit` is where they are recorded. Whether a signal carries the sub-slot
phase *at all* is logic, not delay, and this model does see that — which is
where two of `design-review2.md`'s findings came from.

### Twelve traps this repository has already paid for

- **A failed CPLD fit leaves the previous `.fit` in place.** A stale
  utilisation report reads exactly like a passing one. Compare the file's hash
  across the run, or grep the fitter's output for `INTERNAL ERROR` /
  `does not fit`. `gal/prjbureau/fit1508.sh` records the same trap for CUPL's
  `.tt2`.
  ⛔ **And its nastier sibling, found 2026-09-10: a failed fit that leaves a
  CONVINCING one.** `fit1508.exe` answered `INTERNAL ERROR` for a design that
  does not fit and **wrote a `.jed` and a `.fit` anyway** — so the wrapper's
  "does a JEDEC exist" test passed, it printed `wrote …`, and the report it
  copied out claimed a plausible 128/128 cells and a *better* LAB fan-in than
  the design that really did fit. ⚠ **"Design fits successfully" appears only in
  the fitter's stdout, never in the `.fit`**, so nothing downstream can recover
  it. `fit1508.sh` now requires that sentence and refuses `INTERNAL ERROR`.
- ⛔ **AND THE VERDICT CAN DEPEND ON THE FILE NAME** — found 2026-09-18.
  `gal/video3/v3ptr.pld` and `v3ptr_span.pld`, generated from the same term list
  and **byte-identical apart from CUPL's timestamp comment**, fit differently:
  `v3ptr_span` answered *"Design fits successfully"* twice and `v3ptr` answered
  `INTERNAL ERROR` four times in a row. The prefix was not poisoned — the
  committed baseline still fitted under the name `v3ptr` in the middle of the
  same session. ⚠ So on a design near the edge (that one is at **Nodes+FB
  125%**), **"it does not fit" is not a result until it has been refused under a
  second name**; and "it fits" is a property of the JEDEC you got rather than of
  the design, so the build does not change on the strength of a variant that
  cannot be fitted under its own name.

- **Every `.pld` must be 7-bit ASCII.** Atmel's CUPL is an MS-DOS program and
  its lexer aborts on the `⚠`/`⭐`/`⛔` this repository's prose is made of —
  `illegal character: ASCII code 226`. `jedec.check.ts` asserts it.
- **A check that holds an input constant cannot see a defect in it**, and a
  model that ORs its drivers cannot see a bus fight. Both cost a real defect on
  2026-09-09; `design-review2.md` §10 has them.
- **A model that is more capable than the hardware cannot fail.** `mainboard.v`
  wrote the high map byte into `map_hi` from `dout` — through a wire
  `mainboard.circuit.tsx` does not have — so `mainboard_tb` verified a register
  the machine could not reach, and **M-1 was closed twice**. The netlist is the
  arbiter of what exists; a Verilog model is a model of the *design*, and the
  two are the same thing only if something checks it. ⚠ **A stub check is not
  the fix** — U1B's `DQ` pins were never dangling, they were on a net with three
  other parts and connected to the wrong one. `lib/netlist.check.ts` asserts
  **reachability**: every data pin on every memory or register part reaches
  `D0`–`D7`, across a buffer or directly.
- ⛔ **A `pgrep`/`pkill -f` pattern matches the waiting command's own line.**
  `until ! pgrep -f "fit1508"; do sleep 60; done` never exits: the shell running
  it *contains* the string `fit1508`, so it waits on itself — thirteen minutes,
  once. The same shape read six `tsci build` processes that were five monitoring
  commands and one build, and turned a healthy build into a reported failure.
  ⚠ And `pkill -f` on a generic pattern reaches into **other sessions** — one
  broad kill took out unrelated agents' wait loops. **Poll a completion marker
  the job itself writes** (`echo "DONE=$?" >> log`), or wait on a PID; and
  before concluding anything from a process count, check `ppid` — two
  `fit1508.exe` with different parents are two *fits*, not one wrapper pair.

  ⛔ **AND THE MARKER IS NOT WRITTEN WHEN THE JOB DIES, SO BOUND THE WAIT.**
  Polling a marker fixes the self-match and creates an immortal loop in its
  place: if the job is killed, segfaults, or exits down a path that never
  reaches the `echo`, the marker never appears and `until grep -q …; do sleep
  N; done` waits for ever. On 2026-09-10 **eight of them were found spinning,
  17 to 38 hours old**, reparented to `ppid 2`, each waiting on a file that had
  stopped growing the day before — one on a fit whose log says only
  `Error Code = 1`. They blocked the session from exiting and cost nothing
  visible while doing it, which is why nobody noticed. **Every unbounded wait
  gets an iteration bound and fails loudly on exhaustion**, exactly as the
  testbenches do (see "A hang is worse than a failure" below — the same lesson,
  learned twice, in the shell as well as in Verilog):

  ```sh
  n=0
  until grep -q "DONE=" log; do
    n=$((n+1)); [ $n -gt 120 ] && { echo "FAIL: no DONE= after 10 min"; break; }
    sleep 5
  done
  ```

  ⚠ **And a background task is owned by the SESSION, not by the shell that
  spawned it.** Those eight carried a different shell snapshot in their
  `cmdline` and were nonetheless this session's tracked tasks. A snapshot id
  says which shell started a process; it says nothing about who owns it. Check
  the harness's own task list, not `/proc`.
- ⛔ **`grep '^FAIL'` cannot match a failure, because `bun` colours stderr.**
  `console.error` emits `ESC[0m ESC[31m FAIL …`, so the line begins with an
  escape, not an `F`. The pattern matches nothing and **reports nothing, which
  reads exactly like passing** — it was used to verify this repository all
  through 2026-09-09 and was vacuous every time. ⚠ The `&&` chain in
  `npm run check` is what hid it: a failure stops the chain, so the `ok` count
  collapses and the drop is visible — **except for the LAST script in the
  chain**, where the count barely moves. `check:docs` is last. Strip first
  (`sed 's/\x1b\[[0-9;]*m//g'`), or trust the **exit code**, which is never
  coloured.
- ⛔ **Killing `wine` mid-fit poisons the prefix, and the symptom names the
  wrong culprit.** Afterwards *every* design fails with "CUPL produced no
  `.tt2`" and **no error anywhere in the `.lst`** — it reads like a broken
  design, not a broken toolchain. `WINEPREFIX=~/.wine_atf wineserver -k` and
  retry. ⚠ The prefix is also **one shared resource**: concurrent fits write the
  same `cpld/<name>.fit`, so two of them do not race to a winner, they grind
  indefinitely and produce nothing. One fit at a time, always.
- ⛔ **A SHELL FUNCTION IS INVISIBLE TO `sh -c`, AND `! <not found>` IS TRUE**
  — found 2026-09-20, and it is the `grep '^FAIL'` trap wearing different
  clothes. A bench defined a helper as a shell function and then asserted the
  negative case with `claim "..." sh -c "! indir /dd/sys v3desk"`. The
  subshell has no such function, printed `indir: not found`, exited 127 — and
  the negation turned that into **true**. Three claims passed vacuously,
  including the one asserting the ROM disk no longer carried the desktop.
  ⚠ **A negated claim that can only be satisfied by the thing under test
  EXISTING must prove the tool ran**; call the helper directly rather than
  through `sh -c`, or have it echo a token the claim greps for. Two more from
  the same session, both of which silently produced the right-looking answer:
  **`grep -c` exits 1 when the count is zero**, so `n=$(grep -c ...)` kills a
  `set -e` script with no message at exactly the moment the count becomes
  correct; and **`sed -n "/Directory of /dd/sys/,…"`** is a syntax error,
  because the path's slashes close the regex — it prints nothing and every
  listing claim fails while the machine is perfectly right.

- ⛔ **A `//` COMMENT CONTAINING `/*` SWALLOWS THE FILE, and the tool that
  reads it says nothing** — found 2026-09-20. `gal/reach.check.ts` stripped
  comments in two passes, block first and line second. `storage_card.v`'s
  header says *"generated from the term lists in `../storage/*.jedec.ts`"* —
  and `storage/` followed by `*` **is** the digraph `/*`, so the first pass
  opened a comment there and closed it at the next `*/` 139 lines later.
  **72 % of the file was gone before the scan began**, and the check reported
  four signals as produced-and-unread, which is exactly its FINDING output.
  ⚠ Here it was a false alarm; the same swallowed region hides a true finding
  just as well, and `video_card.v` — a live card — had **9 %** of its body
  invisible the same way. **Strip both kinds of comment in ONE alternated
  pass** (`/\/\*[\s\S]*?\*\/|\/\/[^\n]*/g`), which is what a lexer does:
  whichever delimiter comes first wins. Any tool in this repository that
  reads Verilog or C as text has the same obligation.

- ⛔ **A09 HAS NO COMMENT DELIMITER, AND A COMMA IN A COMMENT IS A REGISTER** —
  found 2026-09-20, and it is the `//`-containing-`/*` trap in an assembler.
  `software/boot/boot.asm` wrote

  ```
          pshs    d               ,s = pixels left; 3,s = the colour
  ```

  and A09 kept parsing the **register list** across the whitespace: postbyte
  `$46`, `PSHS A,B,U`, **four bytes where two were meant**. Every stack offset
  in the routine was off by two, the boot dialog's row layer took the toolbox's
  transparent-key byte for its fill colour, and the `puls` at the end returned
  into VRAM — which presented as a machine that stopped, five minutes into a
  seven-minute simulation, with no output. ⚠ **`pshs d` on its own assembles
  correctly**, so a one-line test of the mnemonic proves nothing; it is the
  comment that does it. **A `pshs`/`puls` comment never starts with a comma,
  and the register list is always written out in full** (`cc,a,b,x,u`, never
  `cc,d,x,u`). `boot.lst` has the postbytes: `$06` is `A,B`, `$46` is `A,B,U`.

- **A hang is worse than a failure.** `vsync_tb` waited on
  `SLOTTICK == 0 && PH == 0`; `SLOTTICK` later moved phase, the conjunction
  became unsatisfiable, and the `forever` spun for half an hour. **`run.sh`'s
  exit code cannot see a hang and the claim count cannot see it** — it presents
  as "budget more time", which is exactly how it was misdiagnosed. Every
  unbounded wait in a testbench carries an iteration bound and calls
  `ok(0, …)` on exhaustion; the bounds are themselves claims, and adding them
  took `vsync_tb` from 26 to 37.
