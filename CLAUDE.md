# CLAUDE.md

## Documentation structure: present design vs. archived history

Since 2026-09-08 the docs are split in two (this replaced the old "superseded text
is marked, not deleted" convention — see the root `README.md` Conventions section):

- **Specs describe only the present design.** One spec document per card
  (`hardware/video3/docs/plan.md`, `hardware/audio/docs/audio.md`, `hardware/cpu/docs/plan.md`,
  `hardware/net/docs/net.md`, `hardware/storage/docs/sdcard.md`, `hardware/io/ps2/docs/ps2.md`,
  `hardware/io/serial/docs/serial.md`, `hardware/mainboard/docs/ram.md`, machine-level `docs/machine.md`).
- **Each component has a `history.md` beside its spec** archiving superseded
  claims, with dates and the reason each number moved. Machine-level history is
  `docs/history.md`; the hardware area shares one `hardware/history.md`.
- **`docs/design-review.md` and `docs/design-review2.md` are frozen dated records**
  (the 2026-09-04 review, and the 2026-09-09 simulation review). Never update their
  findings; the specs and history files carry what changed since.
- ⭐ **`hardware/archive/` holds retired designs, and its documents are frozen too.**
  `hardware/archive/video/` (the machine's video card until 2026-09-20) and
  `hardware/archive/video2/` (a plan, never built) moved there when `video3` became the
  machine's video card — `hardware/archive/README.md` and `docs/history.md`. ⚠ **An
  archived document is still citable as provenance**: this machine's backplane,
  slot model, arbitration rule and clock tree were designed in
  `hardware/archive/video/docs/graphics.md`, and the card being retired does not make
  those derivations wrong. What it is not is a statement about the present
  machine. `tools/lib/docs.check.ts` exempts `hardware/archive/` for the same reason it
  exempts `history.md`.
  ⛔ **`video/`'s DESIGN SOURCES ARE STILL COMPILED.** Since 2026-09-23 they
  live in `hardware/archive/video/logic/` and `sim/` with the rest of the card,
  but `gen.ts` still emits their Verilog, `machine.v` and so **`demo_tb`**
  still instantiate it, `fold.check.ts` still uses the arbiter as its fixture,
  `reach.check.ts` still reads `machine.v` for the motherboard — and the card
  itself is **checked by nothing**. `hardware/archive/README.md` §"What did NOT
  move" is the record of that trade.
  ⭐ **`machine_tb` left them on 2026-09-20**, when `software/boot/boot.asm`'s
  video POST was retargeted to `video3` and the bench moved to `machine3.v`
  (`docs/history.md` §7.2). So the only thing now holding those sources in the
  tree is `software/archive/demo/`, whose raster bars and per-scanline palette writes
  have no `video3` equivalent.

### Reading rules

- A `⚠` in a spec marks a **live** hazard, constraint, or unverified assumption —
  never a revision. (`docs/coco3_c64.md` has its own ⚠ convention, declared in its
  header: "recalled figure, unverified against a primary document".)
- Trust precedence when documents disagree: **design outputs beat prose**
  (`hardware/<card>/logic/*.jedec.ts` / `*.pld` / `cpld/*.fit`, `hardware/<card>/board/*.circuit.tsx`,
  `hardware/tools/place/parts.ts`, `hardware/cpu/src/`, `hardware/cpu/include/`), then the latest-dated doc
  statement, then older ones.
- ⛔ **A design output can be absent, and prose does not notice.** `design-review2.md`
  (2026-09-09) found eleven blocks described as fitted with no cell behind them. Before
  citing a spec's "built" or "fitted", check that something *produces* the signal: the
  port census in `hardware/tools/sim/` is what does it, and `make -C hardware sim`
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

## Repository layout

Since 2026-09-23 the tree is **one directory per component** — the root
`README.md` §Layout has the picture, and `docs/history.md` the map from every old
path. In short: `hardware/<card>/` (`mainboard`, `cpu`, `video3`, `audio`, `io`,
`storage`, `net`) each hold `docs/`, `board/`, `logic/` (term lists, `.pld`,
`cpld/*.fit`, `cupl/*.cupl.jed`), `sim/` (generated and hand-written Verilog,
testbenches) and `reference/`; `hardware/tools/` is what they share (`lib/`,
`place/`, `gal/` = the JEDEC/CUPL/fitter toolchain, `sim/` = the Verilog generator,
the runners and the whole-machine bench). `software/<program>/` (`boot`,
`nitros9`, `toolbox`, `desk`, `pcs`, `stardew`, `monster`, `mvania`,
`tilescroll`, `paint`) each hold `bench/` (generator, model, checker, `run-*.sh`),
`docs/` and `reference/`; `software/emu/` is the host emulator. Retired work is in
`hardware/archive/` and `software/archive/`, frozen.

⛔ **The applications' 6809 source is NOT in this repository.** It is in
`../nitros9` on its `arm6309` branch (`level2/arm6309/cmds/`, `modules/`), where
the recipe builds it; retired programs are in its `level2/arm6309/archive/`.

## Running the checks

⭐ **`make` everywhere, since 2026-09-23.** Every component has a `Makefile` with
the same targets — `make help` lists them from each rule's `## ` comment, `check`
is fast, `bench` is slow, and `clean` removes `build/`. **Everything a component
writes goes to its own `build/`** (Verilator objects, bench output, ROMs, CMake
builds, screenshots) — except the design outputs this repository tracks on
purpose: fitted `.jed`/`.fit`, the generated Verilog and `.pld`, `boot.bin`.
`make -C hardware help`, `make -C hardware/audio help`, `make -C software/pcs
help`. ⚠ The old `npm run …` names still work from `hardware/` — they are aliases
for these targets — but `make` is what the documents mean.


`bun` is a `devDependency` and lives in `hardware/node_modules/.bin`; the
Makefiles call it there (and run `npm ci` if it is missing), so `bun run …` from a
shell will not find it. The Verilator tests need `verilator` on `PATH` (5.020
verified); the CPLD fitter additionally needs `wine` and the WinCUPL extraction
under `~/.wine_atf` (`tools/gal/prjbureau/extract-wincupl.sh`).

| | |
|---|---|
| `make -C hardware check` | every GAL design against its own model, and the live ones against Atmel's CUPL. **641 claims, ~60 s** — ⚠ **895 until 2026-09-20**, when the archived `video` card's ten scripts left the chain and three surviving checks shrank (`docs/history.md`) |
| **`make -C hardware sim`** | ⭐ **the Verilator tests.** Regenerates the Verilog from the term lists, then compiles and runs six testbenches — `audio`, `mainboard`, `storage`, `v3dot`, `v3card`, `v3machine`. **320 claims, ~4 min** — most of it whole frames at 25.175 MHz, so budget for it rather than assuming it hung. ⚠ **435 over ten benches until 2026-09-20**: the archived `video` card's `vsync`, `vaddr`, `vtile`, `vspan` and `vpal` (115 claims) left the default `TBS` then, and on **2026-09-22 they left the tree** — `hardware/archive/video/bench/`. `run.sh` answers those five names with a pointer rather than a missing file |
| `make -C hardware sim-hand` | the two *hand-written* Verilog models, `mainboard/sim/mmu.v` and `mainboard/sim/clkdec.v`, with their own testbenches. Older and separate from `check:video` |
| `make -C hardware netlist` | the motherboard's connectivity, against `dist/mainboard/mainboard/circuit.json`, and the video card's against `dist/cards/video/circuit.json` — what is drawn, and the nets with no producer on the board as a list checked both ways (`graphics.md` §19 item 34). **Build artefacts**, so run `make -C hardware boards` first if a `.circuit.tsx` changed. ⚠ `tsci build` prints "Build completed with errors" and exits 0 when it cannot reach the supplier API; connectivity is unaffected |
| `make -C hardware pld` | writes `gal/{vaddr,vctrl,vsup,audio,aseq}.pld` from the term lists |
| ⭐ **`make -C hardware machine`** | **the whole machine**: a 6809E core, the motherboard, **the `video3` card**, the audio card and — ⭐ since 2026-09-21 — **the storage card with an SDHC card in its socket** (`machine3.v`), running `software/boot/boot.asm` out of the boot ROM, and a screenshot taken off `RGB`/`BLANK`/`HSYNC`/`VSYNC`. Seven runs: the boot on four SIMMs, the SIMM sizing walk against one, two and three sockets and an aliasing module, and two faults (no SIMM, a corrupted VRAM byte) in which the ROM's error path is the asserted answer. ⭐ **It ran the ARCHIVED `video` card until 2026-09-20**, when the ROM was retargeted; every motherboard claim and all six fault/population scenarios are unchanged, so what moved is the card. **146 claims, ~7.5 min** (133 and ~4 min on the archived card: video3 is a bigger model, and the POST does more); `SCENARIOS=main` for the boot alone. ⭐ **Four more runs, asked for by name**, and all of them need `../nitros9` on its `arm6309` branch (`software/nitros9/README.md`): **`SCENARIOS=nitros9`**, NitrOS-9 Level 2 from reset to a shell on the TL16C550C with `dir`, `mfree` and `firqtst q` on the audio card's `/FIRQ` (**19 claims, ~13 min**); **`SCENARIOS=reboot`**, boot, `reboot` back through `boot.asm`'s POST, and a second shell (**11 claims, ~14 min**); and ⭐ **`SCENARIOS="disk nodisk"`**, `boot.asm` §10a's **boot dialog** read off the connector pixel by pixel (**52 claims, ~20 min** — `software/desk/docs/boot-and-desktop.md` §1). ⭐ **Since 2026-09-21 `disk` is a real card**: `run-machine.sh` builds a blessed image with `mksddisk.sh BOOT=`, hands it to `sd_model.v` through `+sdimage=`, and *found* is what `boot.asm` §10b earns by running §9.0's init and §9.1's `CMD17` over SPI. A closed socket switch is no longer the found state - it is the question mark. ⛔ The last pair loads a **`V3=1`** ROM into `software/nitros9/build/dialog`, because the toolbox is ROM page 64 and `recipes/arm6309/arm6309.mak` only builds it under that flag; the other two load the non-V3 one into `software/nitros9/build/rom`, so they cannot share a directory. ⛔ **AND `nitros9`/`reboot` BOOT OFF A CARD TOO SINCE 2026-09-22**: the ROM disk is gone, so `run-machine.sh` hands them `mksyscard.sh`'s whole `system.img` through `+sdimage=` and `sd_model.v` grew from 128 blocks to **1,792** |
| `make -C software/boot rom` | assembles `software/boot/boot.asm` with A09 → `boot.bin`, `boot.hex`, `boot.lst` |
| ⛔ **ONE FLAVOUR, since 2026-09-22** | `recipes/arm6309/arm6309.mak` puts **`-DV3=1` in `AFLAGS`**, so there is no `video/` build to ask for and `V3=1` in front of `mkrom.sh` is accepted and ignored. ⚠ **`VIDEO3=1` on the emulator is therefore unconditional too**: a video3 ROM against the default card model polls `VSTAT` at `$FF6D`, reads a register file, and spins for ever — a machine that prints its banner and never reaches a shell. Why the switch had to go: the non-V3 build had **stopped assembling** and nothing noticed for a day, because the only bench that built it is `SCENARIOS=nitros9`, which is asked for by name |
| ⭐ **`sh software/nitros9/mksyscard.sh IMG [demo …]`** | ⭐ **A BOOTABLE SYSTEM CARD** — NitrOS-9 itself (`OS9Boot`, the whole command set, `MODULES`, `SYS`, `startup`) plus whatever demos are named. ⛔ **Since the ROM carries no filesystem, a bench that builds a plain data card builds a machine that does not start**; `mkrom.sh` writes `$OUT/system.img` with this and most benches just use that. A bench that wants a *deliberately* unbootable card calls `mksddisk.sh` directly — that is the whole difference between the two |
| ⛔ ~~`sh gal/verilog/run-demo.sh`~~ | **RETIRED 2026-09-22 to [`hardware/archive/video/bench/`](hardware/archive/video/bench/)**, with `demo_tb.sv`, `run-demo-emu.sh`, `run-replay.sh`, `run-calib.sh` and the two `run-vramrate` scripts. They ran `software/archive/demo/`'s show on the **archived `video` card**, which nothing builds against any more. ⚠ `software/archive/demo/` itself STAYS: `mktbox.py` generates the ROM toolbox's icon art from its drawing code, and `software/emu/machine.c` is the host emulator every live bench runs |
| ⭐ **`sh software/emu/test/run-ps2script.sh`** | **the PS/2 input script**: `PS2_SCRIPT=file` gives the host emulator a timed, semantic keyboard and mouse script (`move to 320 240`, `click left`, `type "..."`), encoded into set-2 scan codes and 9-bit-split mouse packets and fed to `machine.c`'s **line-level** devices rather than past them (`hardware/io/ps2/docs/ps2.md` §11.5, `software/emu/ps2script.h`). The bench encodes every script a SECOND time in Python (`emu/test/ps2check.py`), drives `ps2tst 24` on a booted NitrOS-9 and compares the bytes the 6809 echoed back off the card — plus a moves-and-no-clicks control, an empty-script control, and a corrupted-expectation run of each comparison that is **required to fail**. **27 claims, ~2 min**; needs `../nitros9` on its `arm6309` branch, so it is in no aggregate |
| ⭐ **`sh software/nitros9/run-sdboot.sh`** | ⭐ **THE OS BOOTS OFF THE CARD, AND ONLY OFF THE CARD.** From reset, through `boot.asm` §10b's own SD reader and NitrOS-9's `boot_sd`, to a shell — `hardware/storage/docs/sdcard.md` §9.5. ⛔ **THERE IS NO ROM DISK SINCE 2026-09-22**: ROM pages 3–63 are 499,712 bytes of zeros, NitrOS-9 lives on the card, and a machine with no bootable card blinks §10a's question mark for ever rather than handing off to a kernel with nothing to load. `boot_sd` says **`s`** for the card and **`n`** for nothing — the old `r` (the ROM disk) is gone. ⛔ **Three card states**: blessed, **present and not bootable** (the Macintosh's real question mark), and empty; the last two no longer reach a shell, which is the point. Needs `../nitros9` on its `arm6309` branch, so it is in no aggregate |
| ⭐ **`sh software/desk/bench/run-v3desk.sh`** | ⭐ **THE DESKTOP SHELL, CLICKED AT.** `desk` (nitros9 `level2/arm6309/cmds/desk.asm`) is the program that emits live what `v3desk` and `v3menu` only recorded — an event loop on `SS.Mouse`, a menu bar that pulls down and highlights, and a launcher that forks `v3paint`, `monster` and `pinball` off `/SD0/CMDS` (`software/desk/docs/boot-and-desktop.md` §3). The bench boots the machine, runs it off the card and drives it with a **`PS2_SCRIPT`**, then reads every answer off the recorded FRAMES: the bar's rows, the pull-down where nothing was, the highlight on the item the pointer is over, the rectangle's CRC restored on dismissal, and **Paint's own page** as the proof a program was forked. ⛔ **With a control that walks the bar and never clicks**, in which the pull-down's rectangle must hold exactly ONE picture. ⭐ Its geometry and its menu table are **parsed out of `desk.asm`**, so a renamed or un-greyed item moves the claims with it. **48 claims, ~3 min**; needs `../nitros9` on its `arm6309` branch, so it is in no aggregate |
| ⭐ **`sh software/tilescroll/bench/run-tilescroll.sh`** | ⭐⭐ **A WORLD OF ANY SIZE, AND THE RING CHECKED BYTE FOR BYTE.** `tilescroll` (`software/tilescroll/docs/scrolling.md`) is the other answer to the problem the retired `zelda` solved by being a room game: the camera roams a 4096 × 2048 world in **`VMODE` 11's square 640 × 480**, and the tile bank lives in the **384 × 512 rectangle of ring the raster never looks at** — rotating through it one 32-column strip at a time so it is never in the way. ⭐ **The gate is the invariant, not a screenshot**: `checktilescroll.py` walks the same path the program walks, works out where all nine strips ended up, and compares **all 524,288 bytes**. ⛔ **With two mutations that are REQUIRED to fail** — the strip not moved, and the vertical band not composed. **~12 min**; needs `../nitros9` on its `arm6309` branch, so it is in no aggregate |
| ⭐ **`sh software/toolbox/bench/run-v3text.sh`** | ⭐ **WHAT A TOOLBOX TEXT CALL COSTS, MEASURED** — the only timing bench of `tbox.asm` there is. Every stream is copied twice, to `/nil` and to a window, and the difference is the drawing; it prices the escape parser, a call that draws nothing, a character, and a line. ⭐⭐ **And since 2026-09-22 it is the gate on the GLYPH STRIKE** (`software/toolbox/docs/proportional-font.md` §6.1): a 40-character line is **222.93 ms composed and 33.41 ms out of the strike — 6.7×** — and the same bench asserts the two are **pixel for pixel identical**, below row 320 as well as above it. ⛔ **`v3t40p` must use toolbox call 13 and not call 0**, because call 0 takes the strike now and a baseline that is the thing under test measures 1.0×. **29 claims, ~11 min**; needs `../nitros9` on its `arm6309` branch, so it is in no aggregate |
| ⭐ **`sh software/desk/bench/run-v3files.sh`** | ⭐ **THE FILE MANAGER, AND THE LISTING READ OFF THE PIXELS.** `desk`'s Tracker window (`software/desk/docs/boot-and-desktop.md` §3.6) lists a real directory, enters one, scrolls, goes back up and forks what is clicked. The bench drives it with a **`PS2_SCRIPT`** and then **rebuilds every candidate name out of the ROM's own font blob** (`mktbox.py` wrote it) to match the glyphs in each row — so the listing it prints is what the machine DREW, and the claims compare that with what the host's **`os9 dir`** says is on the image. ⭐ Three runs: the driven one, ⛔ a **control** whose window is already up on `/SD0/DATA` and whose mouse walks the list, both scroll arrows and the menu bar without ever pressing (the list must hold exactly ONE picture), and **`v3trk` driven from the shell into the same rectangle**, which is the other side of `modules/v3dir.inc`. **65 claims, ~11 min**; needs `../nitros9` on its `arm6309` branch, so it is in no aggregate. `RUNS='idle trk'` re-does one leg |
| ⭐ **`sh software/pcs/bench/run-pcs.sh`** | ⭐⭐ **PINBALL CONSTRUCTION SET, AND THE SIMULATION PROVED RATHER THAN SHOWN.** `pcs` is Bill Budge's 1983 Atari 800 program ported from his own MIT-licensed sources in `software/pcs/reference/pcs-source/` (`software/pcs/docs/pcs.md`). ⭐ **The world stayed in the Atari's own units and only the RENDERER is doubled**, so every number is exact integer arithmetic - which is what lets a Python transliteration of the 6502 be the gate rather than a screenshot. Five legs: the scan converter's 153,600 bytes and its span database record for record; ⭐⭐ **the whole simulator over 600 frames** - the ball's `(x, y, BDX, BDY)` every frame, every part's state byte, and the score, the sound and the run chain, against `pcsobj.py`; and ⛔ **three mutations**, each required to fail. ⛔ **The gate requires five LIBRARY PARTS to have been struck**: a ball that only ever met the backdrop proves nothing about the object system, and that is exactly the run an earlier table gave - 600 frames agreeing over a collision walk that was reading half the world. ⚠ The bench drives the player, because a mouse and two keys are not reproducible. **~8 min**; needs `../nitros9` on its `arm6309` branch, so it is in no aggregate. `RUNS=m4` re-does one leg |
| ⭐ **`sh software/desk/bench/run-v3move.sh`** | ⭐ **MILESTONE 4: THE WINDOW MOVES, AND THE CARD MOVES IT** (`software/desk/docs/boot-and-desktop.md` §3.7). `desk`'s manager window is grabbed by its tab with a **`PS2_SCRIPT`** and dragged round a figure-8; every step is ONE `SS.Copy` of its 284 × 279 bounding box and the list is never redrawn. ⛔ **The claim that matters is not "it moved"** — `v3drag` has walked a canned figure-8 since 2026-09-16 and would pass that. What is asserted is that **the window went where the MOUSE went** (83 % of the script's own samples exactly, the rest in flight between two of them); that it came home **bit-exact**; and ⛔ **that every pixel outside it is the one it was before the grab** — the window is dragged straight over six desktop icons and they come back. ⛔ With a control that walks the same path and never presses, in which the window holds exactly ONE position. ⚠ **`FM.W` is 284 because the off-screen margin is 384 columns**: the backing store is the window plus Marg=50 a side, and `SW` is not kept at all because the move is screen to screen. **13 + 7 claims, ~15 min**; needs `../nitros9` on its `arm6309` branch, so it is in no aggregate. `RUNS=drag` re-does one leg |
| ⭐ **`sh software/desk/video/run-desk.sh`** | ⭐ **THE DESKTOP DEMO VIDEO** — boot from reset, `desk` off the card, the file manager opened off the `home` icon onto **`/DD/CMDS`'s 63 real NitrOS-9 commands**, and the figure-8 drag, as a 1920 × 1080 H.264 file with the serial console beside the screen. `SHEET=1` writes contact sheets instead, in seconds rather than minutes — ⭐ **what a pass is reviewed from before the full-motion file is worth making**. ~9 min for the session, ~4 min to encode |
| ⭐ **`make -C software/<program> sheet`, THEN `video`** | ⭐ **EVERY PROGRAM'S DEMO, AS A CONTACT SHEET AND THEN A VIDEO** (2026-09-24): `boot` (from the reset vector, `COLDBOOT=1`, to the file manager), `tilescroll` (`ACTORS=0` for the engine alone), `stardew`, `pcs` (mode 20 played by `bench/scripts/pcsplay.ps2`), `monster`, `mvania`, `desk`, and `paint` (`WHICH=v3bbs`/`v3art`/`v3paint`, or all three) → `software/<program>/video/*.mp4`. ⛔ **Sheet first, always** — this project reviews a demo from its sheet before committing to a video, so `sheet` keeps the recording and `video` encodes **that same run**; with no sheet or `FRESH=1` it records first. `make sheet` / `make video` at the root do every program. Each `video/run-video.sh` is a few lines on `software/tools/video/record.sh` (rebuild the ROM, boot off the card, type the command, keep every frame; `CARD_DATA` for a program whose data the general card lacks) and `clip.py`, which cuts the scene **by the serial log** — the command's echo to `echo DONE-arm6309`'s — trims blank setup screens and, with `--hold`, still waits, and encodes 2×, 30 fps, x264 crf 20. ⛔ **`PS2` is the shell's continuation prompt and always set**: the mouse-script variable is `PS2FILE`. Needs `../nitros9` and `make -C software/tools ffmpeg`; `software/tools/video/README.md` |
| ⭐ **`make -C hardware reach`** | **every signal the machine produces must reach something.** `design-review2.md` closed the direction "a fitted part reads what nothing produces"; this is the other one — a signal that is *produced* and that nothing reads, which for a register bit means **a feature the host can write and the card cannot perform**. ⭐ **And since 2026-09-18 the same question of INPUTS** for video3: its four parts turned out to be a datapath and an arbiter with **neither sequencer built** — 19 control lines nothing produces. ⭐ Since 2026-09-19 video3's board is `video3_card.v` (a model, not a drawing), and counting against it found a macrocell nothing read. Part of `make -C hardware check` |
| ⭐ **`make -C hardware pins`** | **every programmable part's pin has the sense of what it is wired to.** The generated Verilog is in asserted sense and the wrappers invert by hand, so **no simulation can see a pin declared with the wrong polarity** — nine passed every check until 2026-09-11. Asserts backplane `/` signals are active-low, a signal crossing between two parts has one sense at both ends, and each pin in its `CONSUMERS` table matches the discrete part pin it drives. ⚠ It found three more on 2026-09-18, the day video3 was added to it. Part of `make -C hardware check` |
| ⭐ **`make -C hardware/audio modplay`** | **a module plays on `audio_card.v`** — `14_fourchan.mod`, both stereo pairs — and its converter codes are rendered to a WAV and A/B'd against libopenmpt, with `refplayer` as the control. ⛔ **The A/B is a gate**: a card that scores worse than `refplayer` (level ±0.5 dB, envelope, spectral, tuning) fails the check. The bench log is kept as `hardware/audio/build/modplay/<module>.log`. Needs `libopenmpt.so.0` and numpy, and says so before simulating |
| ⭐ **`make -C hardware/audio bench`** | `check:sim:audio`, `check:oracle` and `check:modplay` — **the audio card's three benches, ~5 min.** Not in `make -C hardware check` (it needs Verilator and libopenmpt); `build:all` ends with it. ⛔ `audio_tb` alone passed through two audio regressions that `check:modplay` caught (`audio.md` §16 item 47) |
| `make -C hardware boards` | renders every `.circuit.tsx` to `dist/` with `tsci` |
| `make -C hardware all` | all of the above in order — `gen:pld`, `build`, `check`, `check:netlist`, `check:sim`, `check:video`, `check:machine`, `check:audio:all` |

### `check:reach` — the census, and why it is not optional

⛔ **`ACTRL` b3 was latched, read back through `ASTAT`, and taken by no cell on
either CPLD for two days.** So `audio.md` §6.1's *"the card doing the ×4"* was
never built and the card sat 12.04 dB below every output level §7.1 specifies.
**Nothing caught it**, because every other check in this repository asks whether
a part computes its own equations correctly — and a bit nobody reads has no
equation to get wrong.

`tools/gal/reach.check.ts` asks the other question. For each card it takes the term
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

⚠ **A fresh clone has no fitter, and `make -C hardware check` still passes without one.**
The Atmel toolchain is not a dependency of the model checks — it is the thing
that answers *does the design still fit the part*, which no model check can — so
its absence is **silent**. **Set it up before changing any `.jedec.ts`,
`video.cpld.ts`, `aseq.cpld.ts` or `audio.cpld.ts`.** The installer is tracked at
the repository root; nothing else is needed but `wine`, `7z` and `unzip`:

```sh
sh hardware/tools/gal/prjbureau/extract-wincupl.sh awincupl.exe.zip    # ~1 min, from the repo root
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

Then, **from `hardware/`**, and after `make pld` (or just `make -C hardware/audio fit` / `make -C hardware/video3 fit`, which do both):

| | |
|---|---|
| `sh tools/gal/prjbureau/fit1508.sh archive/video/logic/vctrl.pld` | place and route one CPLD → `gal/cpld/vctrl.{jed,fit}`. Also `vaddr`, `vsup`, `audio`, `aseq` |
| `sh tools/gal/prjbureau/cupl-reference.sh archive/video/logic/arb.pld` | recompile one **GAL**'s reference JEDEC → `archive/video/logic/cupl/arb.cupl.jed` |

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
The `.pld` for a GAL is written by `toGalPld()` (`tools/gal/jedec/galpld.ts`), so the
sequence is: edit the `.jedec.ts` → rewrite the `.pld` → `cupl-reference.sh` →
`make -C hardware check`.

⚠ **One fit at a time, always** — the Wine prefix is one shared working
directory, and two concurrent fits write the same `cpld/<name>.fit`.

### The Verilator tests

`make -C hardware sim` is the one that runs the *design* rather than its
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
| `audio.jedec.ts`, `aseq.*`, `audio_card.v`, `audio_tb.sv` | `make -C hardware/audio sim` (~25 s), then ⭐ **`make -C hardware/audio bench`** before committing |
| the mainboard, `u9`/`u10` | `make -C hardware/mainboard sim` |
| `verilog/emit.ts`, or anything every card shares | `make -C hardware sim` (everything) |
| the **archived** `video` card (`video.cpld.ts`, `vsup.cpld.ts`, `sync`/`scan`/`access`/`seqph`/`seqctl`/`regfile`/`vlen`/`pxsel`) | ⛔ **NOTHING RUNS IT AT ALL SINCE 2026-09-22.** Its five benches and `demo_tb` are in `hardware/archive/video/bench/`, `check:machine` moved to `video3` with the boot ROM on 2026-09-20, and the NitrOS-9 recipe cannot build against it (`-DV3=1` is in `AFLAGS`). ⚠ The **design sources are in `hardware/archive/video/logic/`** and `gen.ts` still emits their Verilog — compiled, and executed by nothing. `hardware/archive/README.md` §"What did NOT move" is the record of that trade |
| the video3 card (`video3/logic/*.cpld.ts`, `v3lane.jedec.ts`, `video3_card.v`) | `make -C hardware/video3 sim` (~4 min), refit every CPLD you touched (`make -C hardware/video3 fit`), and for `v3lane` `make -C hardware/video3 check cupl` |
| ⭐ `pcs`, the scan converter, the ball or any part proc | ⭐ **`sh software/pcs/bench/run-pcs.sh`** (~8 min), and ⛔ **run `python3 software/pcs/bench/pcsobj.py` first** - the model carries its own self-tests and a broken transliteration is not worth six minutes on a 6809. ⚠ The model is never corrected to agree with the 6809; when they differ the 6502 decides |
| ⭐ `desk.asm`, the window move, or anything the desktop shell draws | ⭐ **`sh software/desk/bench/run-v3move.sh`** (~14 min) and `sh software/desk/bench/run-v3files.sh` (~11 min) — the second is what catches a manager whose hit testing and drawing have drifted apart, because `SetX`/`SetY` and `FileHit` are the same two words read in opposite directions |
| anything the CPU touches — the map, the boot path, `boot.asm`, `machine3.v` | ⭐ **`make -C hardware machine`** |
| the NitrOS-9 port, `tl16c550.v`, or anything NitrOS-9 boots through (the vectors, the map, the tick, the UART) | `sh software/nitros9/run-emu.sh` (~30 s) first, then ⭐ **`SCENARIOS=nitros9 make -C hardware machine`** |
| ⭐ the storage card, `boot.asm` §10b, `boot_sd.asm`, `mksddisk.sh` or where `OS9Boot` lives | `make -C hardware/storage sim` (~20 s), then ⭐ **`sh software/nitros9/run-sdboot.sh`** (~4 min), and ⭐ **`SCENARIOS="disk nodisk" make -C hardware machine`** — which is the only thing that cold-starts §10b, because the host emulator enters at `$8004` and reaches it only after a `reboot` |
| the audio card's *behaviour* | ⭐ **`make -C hardware/audio oracle`** as well — this card against an independent Paula (`audio/sim/oracle/`). It is what found `audio.md` §16 items 36 and 39, and `audio_tb` could not |

Or one at a time, from `hardware/`:

```sh
make verilog && TBS=v3card sh tools/sim/run.sh     # one; TBS="audio storage" for several
```
⚠ `run.sh` does **not** regenerate the Verilog — every `make … sim` target does
that first. After editing a `.jedec.ts`, run `make -C hardware verilog` or a
card's `sim`, or you will test the previous design and believe it. Each card's
objects go to its own `build/obj_<tb>/`, and the bench runs from that `build/`.

| Testbench | Parts instantiated | What it asserts |
|---|---|---|
| ⛔ ~~`vsync_tb`, `vaddr_tb`, `vtile_tb`, `vspan_tb`, `vpal_tb`, `demo_tb`~~ | the **archived** `video` card | **RETIRED 2026-09-22 to `hardware/archive/video/bench/`**, where their README records what each proved. They are frozen and do not run from there |
| `audio_tb` | both audio CPLDs + the state file, the sample RAM, the adder and the converters | the slot walk, the ÷5 CIA clock, Paula's set/clear, open-drain `/FIRQ`, §9.4.5's merge, the six micro-op sequences — **and how many samples a buffer yields**, which is the claim two audible defects survived 43 green ones by not having (`audio.md` §16 item 36) |
| `mainboard_tb` | U3, U6, U9, U10 + the map SRAMs, `'157`, `'574`, boot `'244`, flash and SIMMs | the boot sequence, the 32 MB map, the four SIMM windows, `/IOPAGE`, and that exactly one thing drives physical `A20`–`A13` |
| ⭐ `machine_tb` | **`mc6809e` + the whole motherboard + the whole `video3` card + the whole audio card** (`machine3.v`), and a TL16C550C bus model | that the machine executes its own boot ROM: leaves boot mode with a map it wrote, finds its SIMM, **probes for the video card**, loads 256 palette entries, paints 640 × 200 with the span writer, chains 200 spans with `WADV`, shows all four `VMODE`s, runs the copy engine and the sprite, paints 2,000 tile cells two stores at a time, and reads VRAM back — every frame pixel for pixel. It reads DRAM and VRAM independently of the ROM's own compares, and runs `$E1`/`$E2` on purpose — **it found `graphics.md` §19 items 36, 37 and 38 on the card it used to run, and `hardware/video3/docs/plan.md` §14 items 20 and 21 on the day it was moved to this one** |
| ⭐ `modplay_tb` | **the whole audio card** | that a real module plays: samples uploaded through `SPTR`/`SDATA`, the register stream delivered on the card's own §8.2 tick interrupt, and the four `AD7528` pairs' codes recorded for `hardware/audio/tools/dacwav` |
| ⭐ `v3card_tb` | **the whole video3 card**: `v3dot`, `v3scan`, `v3ptr`, `v3host` and the `v3lane` GAL + `video3_card.v`'s framebuffer and lane `'245`s, register file, fetch ranks, `'153`, sprite `'165`s, LUT, latches and host `'245`, and a 6809E bus model that honours `/WAIT` the way `clkdec` does | the palette, direct `VDATA` writes and post-incrementing reads, the span writer in every mode, `WADV` chaining, a copy **at two accesses a byte** in bitmap and under character mode, and **whole frames pixel for pixel through an identity LUT**: bitmap at fine scrolls 1-3 and a two-axis wrap, the sprite at three positions in two families, character mode at 80×60 and 80×25 (two consecutive frames), tile mode at both cell phases. ⭐ **Every bus is resolved from explicit drivers** - FBA, the internal data bus, each lane, the LUT address - so a fight or a floating sample is a failed claim. The port maps are **generated** (`v3portmap.ts`, from `gen.ts`); `TBARGS=+ONLY=sprite,char` runs named groups for a debug loop. **It found fourteen defects `v3dot_tb` and 770 model claims could not, and then sixteen more** (`hardware/video3/docs/history.md`, 2026-09-19) |
| ⭐ `v3machine_tb` | **`mc6809e` + the motherboard + the whole video3 card** (`machine3.v`), running `software/boot/v3boot/v3boot.asm` out of the boot ROM | that the machine executes a program against the card: the map it writes, the palette both ways, direct writes and post-incrementing reads, a span, a `WADV`-chained glyph, a copy, and a 400-line frame whose every pixel is the card's own LUT entry for the byte the ROM drew. ⭐ **And the three things only a CPU can ask**: a real instruction's bus cycle stretched to 987 dots by `/WAIT`, the VBL interrupt fetched and serviced, and an engine surviving the polls of its own `VSTAT`. **It found the palette commit firing twice outside vertical blanking on its first run** — 48 claims, ~40 s, 34 of them compiling the core |

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

### Fifteen traps this repository has already paid for

- **A failed CPLD fit leaves the previous `.fit` in place.** A stale
  utilisation report reads exactly like a passing one. Compare the file's hash
  across the run, or grep the fitter's output for `INTERNAL ERROR` /
  `does not fit`. `tools/gal/prjbureau/fit1508.sh` records the same trap for CUPL's
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
  `video3/logic/v3ptr.pld` and `v3ptr_span.pld`, generated from the same term list
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
  other parts and connected to the wrong one. `tools/lib/netlist.check.ts` asserts
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
  `make -C hardware check` is what hid it: a failure stops the chain, so the `ok` count
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
  ⚠ That ROM disk is itself gone now (2026-09-22); the trap is not.
  ⚠ **A negated claim that can only be satisfied by the thing under test
  EXISTING must prove the tool ran**; call the helper directly rather than
  through `sh -c`, or have it echo a token the claim greps for. Two more from
  the same session, both of which silently produced the right-looking answer:
  **`grep -c` exits 1 when the count is zero**, so `n=$(grep -c ...)` kills a
  `set -e` script with no message at exactly the moment the count becomes
  correct; ⛔ **and it answers 1 for a console that is ONE LINE** — found
  2026-09-21. `desk`'s messages end in `C$CR` and every bench strips the CR,
  so the whole of `console.txt` is a single line: "how many times did
  `DESK-DIR` happen", counted with `grep -c`, is **1 whatever the answer**,
  which is exactly the number the claim was hoping for. `grep -o … | wc -l`.
  And **`sed -n "/Directory of /dd/sys/,…"`** is a syntax error,
  because the path's slashes close the regex — it prints nothing and every
  listing claim fails while the machine is perfectly right.

- ⛔ **A `//` COMMENT CONTAINING `/*` SWALLOWS THE FILE, and the tool that
  reads it says nothing** — found 2026-09-20. `tools/gal/reach.check.ts` stripped
  comments in two passes, block first and line second. `storage_card.v`'s
  header says *"generated from the term lists in `../storage/*.jedec.ts`"* —
  and `hardware/storage/` followed by `*` **is** the digraph `/*`, so the first pass
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

- ⛔ **DEBUGGING BY HYPOTHESIS WHEN THE EMULATOR WILL JUST TELL YOU** — paid
  for on 2026-09-22, at roughly six bench runs of ten minutes each. A toolbox
  copy drew its pixels perfectly and then the console went silent and the
  machine never ran another command. Four plausible causes were reasoned out
  and each one cost a full run to disprove: the block mapper being handed a
  `$FFFF` sentinel, a `WMODE`/`WADV` that was not put back, the copy engine
  left `CBUSY` so the next register write stalled in `/WAIT`, and a stale
  `VG.PtrGen`. ⭐ **The host emulator resolves the PC to a module and an
  offset and will hand you the answer in one run:**

  ```sh
  cd software/nitros9/build/rom          # any bench's OUT dir, with its built ROM
  SERIAL_IN=typed.txt SERIAL_GATE="DD:" WILD=1 VIDEO3=1     TRACE_AT=200 TRACE=300 ./emu arm6309_rom.bin . 202 2>trace.log
  grep '^PC ' trace.log | awk '{print $NF}' | sort | uniq -c | sort -rn
  ```

  `TRACE_AT` is machine seconds and `TRACE` is how many instructions to print;
  `machine.c`'s `module_of()` turns each `PC` into `CoArm+$0112`, and the
  register columns come with it. The histogram above named the routine
  immediately, and the instructions before it named the caller: `RowCopy` was
  calling `IsDisp`, which takes its screen in **X** and hands it to `SIdx` —
  a loop that subtracts `SC.Size` until it reaches zero, so a pointer that is
  not a screen record spins for ever. `X` still held the toolbox's own
  `Co.WinA` address.
  ⚠ **Find the wedge's time first** — the last line of `serial.times`, or the
  last `s  prog` line in `emu.log` that still changes — and set `TRACE_AT`
  just after it and the run length just past that, so the trace is seconds of
  wall clock rather than the whole session.
  ⚠ And the other diagnostics are worth knowing before guessing: `WATCH`
  (addresses), `MARKS`, `MASKLOG`, `CALLTIME`, `VRAMDUMP`, `RINGDUMP`,
  `KEEPFRAMES=1` on the video3 benches — a decoded frame is what proved the
  screen was uniformly black and ruled out fonts, the tab and the page header
  at a stroke.
  ⭐ **The rule: once a symptom is "it completes its work and then something
  else dies", stop reasoning and take a trace.** A hypothesis costs a bench
  run to disprove; the trace costs one run and disproves all of them.

  ⭐⭐ **AND FOR "WHERE DOES THE TIME GO", THE SAME TRACE ANSWERS IT — but only
  weighted by DOTS.** The trace line carries `D <dots>`, and
  `software/emu/test/pchist.py` charges each instruction the difference to
  the next line and resolves it to a routine out of the recipe's own listings
  (`mkdir -p LST/.mods; make -C l2 … LISTDIR=LST AFLAGS_EXTRA=-DV3=1
  .mods/coarm`). It is what priced `proportional-font.md` §6.2 — 1,310 cycles a
  glyph, of which the register protocol is 60 and the copy engine 52.
  ⛔ **Two traps in that script's own first three runs**, both of which produced
  a confident wrong answer rather than an error: **counting instructions instead
  of dots** reported 92 % in the kernel over a window that held almost no
  drawing (true of instructions, useless about cost, and `/WAIT` is invisible to
  it); and **taking a PC range for a module** — the toolbox is a ROM page run in
  place at `$A000` with no module header, and so is every task-0 user program
  linked there, so `rbromdisk` was reported as 15 % toolbox time. The test is the
  range **and** the module `module_of()` resolved from the live map.
  ⚠ A third: a listing's source column is **verbatim and padded**, so a label is
  a symbol at column 9 and a mnemonic is one at column 29 — strip the whitespace
  first and every `lbsr` becomes a label, and the histogram reports the time
  under instruction names, which reads exactly like an answer.

- ⛔ **A SCALAR THAT BECOMES AN ARRAY LEAVES READERS BEHIND, AND THE ONE IT
  LEAVES BEHIND STILL ASSEMBLES** — found 2026-09-22. `tbox.asm`'s glyph
  strike grew from one cached face to three slots, so `TB.SkF` went from a
  byte to `rmb SK.Slots`. Every writer was updated; one reader in `SkBuild`'s
  second pass still said `lda >TB+TB.SkF` — now slot 0's byte, which the
  allocator had just set to `$FF` to mark the slot empty. FONT `$FF` is a
  legal FONT byte: `FontMap` clamps the index to 0 and `F.Bold` and `F.Opaq`
  both take. So 95 glyphs were composed into the margin **in the wrong face**,
  every copy out of it was faithful, and the result still looked like text.
  ⚠ **`>SYMBOL` and `SYMBOL,x` assemble identically whether `SYMBOL` names one
  byte or the first of many**, so nothing warns. The fix is to give the
  build-time value its own name (`TB.SkFi`) rather than read an element of the
  table the build is about to write.
  ⛔ **And the tracer could not have found this one.** The PC histogram is flat
  and correct — the machine executes exactly the routine it should, with the
  wrong datum. What found it was **rendering both bands as ASCII and looking**:
  the reference was letters and the strike was a dense 57-column repeat.
  ⭐ **The rule that pairs with the tracer note above: trace when the symptom is
  CONTROL FLOW (it hangs, it dies, it never returns); look at the DATA when the
  symptom is a wrong answer of the right shape.** Six bench runs went into
  hypotheses before the first `print(''.join('.' if c==1 else '#' ...))`.

- ⛔ **A DISPATCH TABLE INDEXED BY A CONSTANT THAT LIVES IN ANOTHER FILE, AND
  THE SHORT TABLE JUMPS INTO AN OPERAND** — found 2026-09-22. The ROM toolbox
  calls its host back through `jsr [CG.TbV + TV.<name>]`, where `TV.*` are
  equates in `tbox.asm` and `CG.TbV` points at whichever row layer is running.
  There are two: CoArm's, and **`software/boot/boot.asm`'s own**, because the
  boot dialog draws before there is an OS. The glyph strike added `TV.CopyN` at
  offset 24; `boot.asm`'s table ends at 18; `SkFlush` jumped to `tbvec+24`,
  which is the **middle of `tbmapb`'s `cmpd` operand**. Four bytes of operand
  ran as instructions, the `rts` went into VRAM, and every boot with no
  bootable card ran wild two seconds in.
  ⚠ **It was invisible on the machine that works**: *"Disk found"* is `F.Reg`
  and flushes no batch, so the card path was perfect and only the question
  mark's `F.Bold` crashed. The two controls in `run-sdboot.sh` found it — and
  only after the ROM disk was removed, because until then that path fell back
  to a working boot. ⛔ **Nothing checks the two tables against each other.**
  A new `TV.*` in `tbox.asm` is a new entry in `boot.asm` on the same day.
  ⚠ The general shape: **a caller and a callee that agree by a number rather
  than by a symbol they both import are not checked by either assembler.**
  ⛔ **AND THE SAME DAY, THE OTHER HALF OF THE SAME SHAPE**: a routine that
  moved *out* of an `IFNE V3` guard while the fields it reads stayed in one.
  `ca_row.asm`'s `CpSrcA` reads `CG.CpSY`, which `armvid.d` only defines under
  `V3`, so a build without the flag stopped assembling — and nothing noticed,
  because **every bench that runs CoArm passes `V3=1`**. The one that does not
  is `SCENARIOS=nitros9`, which is asked for by name and in no aggregate. ⚠ A
  conditional build with no bench in any aggregate is a build that is broken
  for as long as nobody types its name.
  ⛔ **And the first fix was half of one.** Answering the new vector honestly
  (carry set = "compose it yourself") stopped the crash and left the toolbox
  still *building* a 95-glyph strike, ~556 ms a face, for a layer that could
  never copy out of it — `machine_tb`'s `nodisk` then timed out with the
  progress port stuck at `$60`. `SkHave` probes with an EMPTY run now and the
  dialog costs 274 ms instead of 846. ⚠ **A cache whose only use is a fast
  path must not be filled by a caller that cannot take that path.**

- **A hang is worse than a failure.** `vsync_tb` waited on
  `SLOTTICK == 0 && PH == 0`; `SLOTTICK` later moved phase, the conjunction
  became unsatisfiable, and the `forever` spun for half an hour. **`run.sh`'s
  exit code cannot see a hang and the claim count cannot see it** — it presents
  as "budget more time", which is exactly how it was misdiagnosed. Every
  unbounded wait in a testbench carries an iteration bound and calls
  `ok(0, …)` on exhaustion; the bounds are themselves claims, and adding them
  took `vsync_tb` from 26 to 37.
