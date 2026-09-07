# `hardware/gal/jedec/` — the fitter, and what it is worth

`../README.md` open item 1 said *"nothing has been fitted. The pin budget is
arithmetic, not a fitter's report."* This directory closes it, and does so
without WinCUPL, without Wine, without a 32-bit runtime and without a Windows
binary that cannot run in CI.

| | |
|---|---|
| [`gal22v10.ts`](gal22v10.ts) | the device: 132 × 44 array, row and column maps, config bits |
| [`assemble.ts`](assemble.ts) | product terms → fuses → `.jed`, and the `.doc` report |
| [`simulate.ts`](simulate.ts) | a GAL22V10 that runs on a parsed `.jed` |

The designs are [`../mmu.jedec.ts`](../mmu.jedec.ts) and
[`../clkdec.jedec.ts`](../clkdec.jedec.ts); the check is
[`../jedec.check.ts`](../jedec.check.ts), and `npm run check:jedec` runs it.

## Why this is stronger than a fitter's report, and where it is weaker

A compiler answers "does it fit" with its own say-so. Assembling the fuses
answers it by construction — the terms are placed or the assembler refuses —
and then the placed fuses can be executed:

    mmu.jed  ──parse──▶  AND array + macrocell config  ──evaluate──▶  compared
                                                                     with
                                                                     mmu.model.ts

That comparison is over the whole 16-bit address space × 4 quadrature phases ×
R/W for U3, and over both divisors × every count × all 32 decode inputs for U6.
It is a check on **the bits that go onto the chip**, which is not something
anyone does with a compiler's output — you compile, you get a `.jed`, and you
trust it.

**Where it is weaker: self-consistency is not correctness.** If the column map
in `gal22v10.ts` were wrong, the assembler and the simulator would share the
error, agree with each other perfectly, and the check would pass on a file that
programs a part to do something else. No amount of simulation closes that,
because both ends read the same table.

## So the table is corroborated twice, and was falsified a third way

Everything in `gal22v10.ts` comes from two sources that were consulted
independently and agree in every entry:

1. **`reference/datasheets/ATF22V10C.pdf`.** §10's compiler-mode table gives
   5828 fuses in PAL mode, **5892 in GAL mode** and 5893 with power-down. §11's
   functional logic diagram, page 10, draws the array: 44 columns labelled
   `INPUT LINES 0..43`, one `AR` row, then ten groups of one `OE` row and
   8/10/12/14/16/16/14/12/10/8 term rows, then `SP`. 132 × 44 = 5808, plus 20
   config bits and the 64-bit signature = 5892 with nothing left over.
2. **galette** (`github.com/simon-frankau/galette`), a GAL assembler that has
   programmed real parts. `GAL22V10_DATA`, `OLMC_ROWS_22V10`,
   `OLMC_SIZE_22V10` and `PIN_TO_COL_22V10` match the datasheet reading
   entry for entry, and `set_and`'s `neg_off` fixes the true/complement column
   order that `reference/articles/gal.html` shows for the GAL16V8.

**The third way was done on 2026-09-07, and it found two errors.**
[`../prjbureau/extract-wincupl.sh`](../prjbureau/extract-wincupl.sh) pulls
Atmel's own CUPL 5.0a out of the WinCUPL installer under Wine; `../mmu.pld` and
`../clkdec.pld` compiled with it are committed as [`reference/`](reference/),
and `npm run check:cupl` executes them on our fuse map. Both errors were exactly
what the warning above describes — the assembler and the simulator shared the
mistake, so all 178 checks passed either way:

| | Was | Is |
|---|---|---|
| **S0/S1 config-bit order** | pin 14 upward | **pin 23 downward** |
| **registered macrocell feedback** | the pin level | **the complement of `Q`** |

The first came from misreading galette, which fills `xor[]` with
`xor[num_olmcs - 1 - i]` — that inversion means index 0 is the *last* macrocell.
Symmetric pins hid most of it: only 18 and 19 disagreed visibly.

The second is the sharper one. CUPL emits `clkdec`'s `C0.d = !C0` as the single
literal `C0`, which is only a working counter if the array is fed from `/Q`.
Ours was written the other way and counted correctly **in our own simulator and
nowhere else** — every `.jed` here with a registered output that feeds back
would have been wrong on silicon.

**So the two-source rule this section applies to the device description now
applies to the fuse map too**, and `check:cupl` keeps it that way: edit
`gal22v10.ts` again and Atmel's reference files stop evaluating.

Programming a part and testing it on the bench is still the last word, and has
to happen anyway.

## The conventions that are easy to get backwards

- **`0` is an intact link.** A fuse of `0` means the signal *is* connected to
  that product term. So an all-zero row is permanently **false** (every signal
  ANDed with its own complement) and an all-one row is permanently **true**
  (the AND of nothing). Unused product terms are all-zero rows; a permanently
  enabled output has an all-one `OE` row. This is the convention that cost the
  author of `reference/articles/gal.html` twenty chips.
- **A macrocell pin used as an input must be combinational and must never
  drive.** A registered macrocell feeds the array from its register, and its
  pin is not an array input at all. U3 puts `E`, `Q` and `R/W` on pins 14–16,
  so this is checked rather than assumed.
- **Emit `*QF5892`, never 5893.** The 5893rd fuse is the power-down enable, and
  it makes DIP pin 4 the `PD` pin. `clkdec.pld` has `/IOPAGE` on pin 4, which
  is *high* on every cycle that is not `$FFxx` — the part would power down
  continuously and it would look like a clock fault.
- **Nothing but fuse data after an `*L`.** A JEDEC field runs to the next
  asterisk, so an annotation on a fuse line is read as fuses. The annotated
  map is the `.doc`, not the `.jed`.

## Burning one

`minipro` (open source, TL866II+/T48) programs the ATF22V10C and takes these
files directly. The security fuse is left unprogrammed (`*G0`). The 64-bit user
signature carries the part number — `A6309U3`, `A6309U6` — and stays readable
off a programmed chip even if the security fuse is later set, which makes an
unlabelled part identifiable on the bench.
