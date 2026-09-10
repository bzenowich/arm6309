# CLAUDE.md

## Documentation structure: present design vs. archived history

Since 2026-09-08 the docs are split in two (this replaced the old "superseded text
is marked, not deleted" convention — see the root `README.md` Conventions section):

- **Specs describe only the present design.** One spec document per card
  (`video/docs/graphics.md`, `audio/docs/audio.md`, `cpu/docs/plan.md`,
  `net/docs/net.md`, `storage/docs/sdcard.md`, `io/ps2/docs/ps2.md`,
  `io/serial/docs/serial.md`, `hardware/ram.md`, machine-level `docs/machine.md`).
- **Each component has a `history.md` beside its spec** archiving superseded
  claims, with dates and the reason each number moved. Machine-level history is
  `docs/history.md`; the hardware area shares one `hardware/history.md`.
- **`docs/design-review.md` and `docs/design-review2.md` are frozen dated records**
  (the 2026-09-04 review, and the 2026-09-09 simulation review). Never update their
  findings; the specs and history files carry what changed since.

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
| `npm run check` | every GAL design against its own model, and the live ones against Atmel's CUPL. **391 claims, ~36 s** |
| **`npm run check:video`** | ⭐ **the Verilator tests.** Regenerates the Verilog from the term lists, then compiles and runs six testbenches. **140 claims, ~2 min 40 s** — most of it whole frames at 25.175 MHz, so budget for it rather than assuming it hung |
| `npm run check:sim` | the two *hand-written* Verilog models, `gal/mmu.v` and `gal/clkdec.v`, with their own testbenches. Older and separate from `check:video` |
| `npm run check:netlist` | the motherboard's connectivity, against `dist/mainboard/mainboard/circuit.json` — **a build artefact**, so run `npm run build` first if a `.circuit.tsx` changed |
| `npm run gen:pld` | writes `gal/{vaddr,vctrl,audio}.pld` from the term lists |
| `npm run build` | renders every `.circuit.tsx` to `dist/` with `tsci` |
| `npm run build:all` | all of the above in order — `gen:pld`, `build`, `check`, `check:netlist`, `check:sim`, `check:video` |

### The Verilator tests

`npm run check:video` is the one that runs the *design* rather than its
equations. It ends with a line like `140 claims, 0 failed`, and **its exit code
is the answer** — a testbench prints a failed claim and then calls `$finish`,
which exits 0, so the count is what decides the status. Read the `FAIL` lines;
each names the claim and the observed value.

One testbench at a time, from `hardware/gal/verilog/`:

```sh
TBS=vtile sh run.sh          # one; TBS="vsync vaddr" for several
```

| Testbench | Parts instantiated | What it asserts |
|---|---|---|
| `vsync_tb` | the whole video card | raster geometry in all four `VMODE` codes, sync widths and **polarity**, blanking |
| `vaddr_tb` | " | the bitmap scan address over whole lines, both scroll axes, both ring wraps, line doubling, who owns the internal address bus |
| `vtile_tb` | " | the cell fetch cadence, both address concatenations, cell-mode scroll in both axes, the 32-row ring |
| `vspan_tb` | " | all four `WMODE`s, the retire rate, `/WAIT`'s read/write rule, `WADV` chaining, the display list, the VBL interrupt |
| `audio_tb` | the audio CPLD | the slot walk, the ÷5 CIA clock, Paula's set/clear, open-drain `/FIRQ`, §9.4.5's merge |
| `mainboard_tb` | U3, U6, U9, U10 + the map SRAMs, `'157`, `'574`, boot `'244`, flash and SIMMs | the boot sequence, the 32 MB map, the four SIMM windows, `/IOPAGE`, and that exactly one thing drives physical `A20`–`A13` |

**What is generated and what is written.** `verilog/emit.ts` turns a `Merged`
or a `Design` into Verilog from **the same `Cell` term lists `jedec/cupl.ts`
compiles for the fitter** — so `vaddr.v`, `vctrl.v`, `rfa.v`, `vlen.v`,
`audio.v`, `u9.v` and `u10.v` are build outputs and ⚠ **must not be edited**;
change the `.jedec.ts` and re-run. The card and board wrappers
(`video_card.v`, `mainboard.v`) and every `*_tb.sv` are hand-written.
`verilog/README.md` has the rest.

⚠ **It models the logic and not the timing.** Propagation delay, the switch
matrix, product-term cascading and placement are `fit1508.exe`'s business and
`cpld/*.fit` is where they are recorded. Whether a signal carries the sub-slot
phase *at all* is logic, not delay, and this model does see that — which is
where two of `design-review2.md`'s findings came from.

### Seven traps this repository has already paid for

- **A failed CPLD fit leaves the previous `.fit` in place.** A stale
  utilisation report reads exactly like a passing one. Compare the file's hash
  across the run, or grep the fitter's output for `INTERNAL ERROR` /
  `does not fit`. `gal/prjbureau/fit1508.sh` records the same trap for CUPL's
  `.tt2`.
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
- ⛔ **Killing `wine` mid-fit poisons the prefix, and the symptom names the
  wrong culprit.** Afterwards *every* design fails with "CUPL produced no
  `.tt2`" and **no error anywhere in the `.lst`** — it reads like a broken
  design, not a broken toolchain. `WINEPREFIX=~/.wine_atf wineserver -k` and
  retry. ⚠ The prefix is also **one shared resource**: concurrent fits write the
  same `cpld/<name>.fit`, so two of them do not race to a winner, they grind
  indefinitely and produce nothing. One fit at a time, always.
- **A hang is worse than a failure.** `vsync_tb` waited on
  `SLOTTICK == 0 && PH == 0`; `SLOTTICK` later moved phase, the conjunction
  became unsatisfiable, and the `forever` spun for half an hour. **`run.sh`'s
  exit code cannot see a hang and the claim count cannot see it** — it presents
  as "budget more time", which is exactly how it was misdiagnosed. Every
  unbounded wait in a testbench carries an iteration bound and calls
  `ok(0, …)` on exhaustion; the bounds are themselves claims, and adding them
  took `vsync_tb` from 26 to 37.
