# `hardware/gal/prjbureau/` — extending Project Bureau to the ATF1508AS

`graphics.md` §10.1.6 picks two `ATF1508AS` in PLCC-84 for the video card, and
`../README.md` explains why the GAL fitter in [`../jedec/`](../jedec/) does not become
a CPLD fitter: **we wrote that from the ATF22V10C datasheet's fuse map, and the
ATF1508AS datasheet has no fuse numbers at all.** Grep both PDFs in
`reference/datasheets/` — the 22V10 gives "(5892 Fuses)" and `INPUT LINES 0..43`, the
1508 gives nothing.

[Project Bureau](https://github.com/whitequark/prjbureau) is the project that recovers
that information, by **fuzzing the vendor fitter** rather than reading a datasheet. Its
own status table rates the parts:

| Device | Fuse database | Programming |
|---|---|---|
| ATF1502AS/ASV/ASL | **Complete** | **Complete** |
| ATF1504AS/ASV/ASL | Near-complete | Untested |
| **ATF1508AS/ASV/ASL** | **Partial** | **Untested** |

and the checked-in `database.json` has no 1508 entry at all. **A 1508 fuse map is the
prerequisite for everything downstream** — a fitter, a fuse-level simulator, and
retiring "Untested" on the programming path. This directory is the part of that work
that needs no toolchain.

## What is here

| | |
|---|---|
| [`extract_pins.py`](extract_pins.py) | derives the macrocell-to-pin maps from Atmel's own BSDL files |
| [`atf1508_pins.json`](atf1508_pins.json) | its output — the data a prjbureau device description needs |

**The mapping is not in the datasheet.** `ATF1508AS.pdf` draws all four pinouts and
labels every pin `I/O`, never `MC57`. It *is* in the boundary-scan files prjbureau
already vendors, one comment at a time:

```
--Input, pin81 MC128
"2    (BC_4,IO81,input,X),"&
```

so this reads them back out rather than anyone transcribing 128 numbers twice.

**It cross-checks without being told the answer.** PLCC-84 comes out at 60 pinned
macrocells and TQFP-100 at 76, with JTAG on MC32/MC48/MC96/MC112 in both — so 64 and
80 I/O, which is exactly what Microchip and the distributors quote. The per-block
distribution is `8 7 7 8 8 7 7 8`, and the four blocks showing seven are precisely the
four that hold a JTAG macrocell. Nothing was fitted to make that come out.

**Two packages are missing and are recorded as missing:** the `Q100` and `Q160` BSDLs
use a different comment style and carry no macrocell pairs, so PQFP-100 and PQFP-160
need another source. Neither is the package §10.1.6 selects.

## What the ATF1508AS is, from this data

128 macrocells in **8 logic blocks of 16**, and **8 of each block's 16 reach a pin** in
PLCC-84. So the package exposes 64 of 128 macrocells and **68 are permanently
buried** — which is the property §10.1.6 is buying: the card's 36 address-counter bits
and its dot phase, mask counter and line counter never wanted pins.

## What is blocked, and what it needs

The fuzzers drive the **vendor fitter under Wine** and use yosys as a front end
(`util/toolchain.py` sets `WINEPREFIX`, `FITTERDIR`; `run_uncached` shells out to
`yosys` for Verilog → EDIF). None of that is installed here:

> ⚠ **The claim that this needs `wine32:i386` was wrong and is withdrawn.** Wine 9
> runs the 32-bit fitters with WoW64 built in — no multiarch, no `wine32`, no root.

**The fitters are extracted and working.** [`extract-wincupl.sh`](extract-wincupl.sh)
pulls them out of Microchip's `awincupl.exe` installer on Linux with no root and no
display:

```sh
./extract-wincupl.sh /path/to/awincupl.exe.zip
#   Atmel ATF1508AS Fitter Version 1.8.7.8 (02-05-03)
```

Three things about that were not obvious:

- Wine runs the installer, which **fails at the GUI** — but it has already
  self-extracted `WinCupl.msi` into the prefix's `Temp` by then, which is enough.
- **7-Zip cannot open the payload cabinet if you carve it out of the `.exe` by byte
  offset.** MSI streams live in non-contiguous 4 KB sectors, so the bytes are not
  consecutive; a carve looks like a valid cabinet header and then fails to inflate.
  Extract `Data1.cab` *from the MSI* and it opens.
- `cupl.exe` needs its phase DLLs (`cupla`…`cuplx`) beside it or it exits silently
  with no message and no output file.

What remains for the fuzzers themselves:

```sh
sudo apt install yosys                                   # prjbureau's front end
python3 -m venv .venv && .venv/bin/pip install bitarray  # PEP 668 blocks system pip
```

With those in place:

```sh
git clone https://github.com/whitequark/prjbureau && cd prjbureau
# add an atf1508xx entry to fuzzers/000-init/fuzzer.py using atf1508_pins.json:
#   blocks = "ABCDEFGH", 8 blocks x 16 macrocells, specials TDI=M32 TMS=M48
#   TCK=M96 TDO=M112, and the PLCC84/TQFP100 pin lists from that file
./bootstrap.sh
```

`bootstrap.sh` runs every fuzzer in turn and rewrites `database.json`.

## The plan: fuzz first, decompile the gap

There are two ways to recover a fuse map, and they are **not alternatives** — the
order makes each one cheaper, and each validates the other.

### Phase 1 — fuzz, to measure the gap

Not to answer "does it work" but **how long the tail is.** whitequark took the 1502 to
Complete, the 1504 to Near-complete and the 1508 to Partial, and gives the reason as
*"peculiarities of the toolchain"* rather than anything architectural. The 1508 is the
same architecture with 8 blocks instead of 4 and the fuzzers are parameterised by block
count, so most should simply run.

**What to measure:** the fraction of fuses that resolve, and specifically whether the
`uim_mux` fuzzers (025–027) — which map the 40-of-~200 switch matrix — scale to eight
blocks. That matrix is what makes fitting a search problem rather than arithmetic, and
it is where a "peculiarity" would most plausibly live.

**The output that matters is the list of fuses that did *not* resolve.** That turns
"Partial" from a status into a work item.

### Phase 2 — decompile, but only the gap

**Fuzzing has a structural blind spot.** It only finds fuses it can provoke the fitter
into toggling; anything the tool never emits differently — reserved bits, defaults,
modes CUPL cannot express — is invisible to a differ. That is the most likely reason
the 1508 sits at Partial, and no amount of additional fuzzing fixes it.

**The fuse map is almost certainly data, not algorithm.** The fitter directory ships
`aprim.lib` and `atmel.std` — shared across devices — and then **one executable per
device**: `fit1502.exe`, `fit1504.exe`, `fit1508.exe`. Shared data files plus
per-device binaries says the device tables are compiled in. So the target is static
arrays in `.rdata`, which is the easy end of binary analysis: pattern-hunting for
fuse-index tables, not reading control flow.

**It would also settle problem 2** (`../README.md`): the switch matrix's legal
selections are the data a hand-fitter needs, and fuzzing only ever maps them
statistically.

### Why both, rather than either

`jedec/gal22v10.ts` is trustworthy because **two independent sources agree** — the
ATF22V10C datasheet's fuse counts and array diagram, and galette's tables, entry for
entry. A 1508 fuse map derived one way only has exactly the circularity that file's
provenance note warns about, with nothing to check it against.

Decompiled tables validated against fuzzed observations is that same two-source
structure. **Doing both is not twice the work; it is the only way either result earns
confidence.**

> **On provenance, because it changes what can be published.** prjbureau is 0-BSD.
> Observations of a program's output are cleaner to redistribute than tables lifted out
> of its binary, which is plausibly why a public project chose fuzzing. Microchip's
> licence almost certainly forbids reverse engineering; interoperability exceptions
> exist in several jurisdictions (EU Software Directive Art. 6, US DMCA §1201(f),
> *Sega v. Accolade*) and are fact- and jurisdiction-specific. The practical bite is on
> **redistribution**, not on building this machine. If the 1508 entry is meant to be
> upstreamed, the fuzzed half is the half to contribute.

## Prior art worth reading first

[`peterzieba/5Vpld`](https://github.com/peterzieba/5Vpld) covers this exact ground —
ATF16V8/22V10/1502/1504/1508 under modern Linux. It does **not** vendor the fitter
binaries, but it carries things this plan needs:

| | |
|---|---|
| `atmel-fitters/fitter15xx.pdf` | Atmel's own fitter documentation |
| `atmel-fitters/showargs.cpp` | a shim that captures the arguments WinCUPL passes the fitter — useful for driving it directly, and RE by observation rather than disassembly |
| `abs-decode/cupl-abs.ksy` | a Kaitai Struct spec for CUPL's `.abs` format — precedent that this family's file formats yield |
| `linux-workflow/5vcomp` | a wrapper for `cupl.exe` under Linux |

**And it names a fitting route this plan had not considered:** Quartus targeting an
**EPM7128** — which the ATF1508 is the drop-in replacement for — then Atmel's `POF2JED`
to convert. Quartus runs natively on Linux. That would sidestep `fit1508.exe` for
*fitting* entirely, though not for the fuse map, which still needs Phase 1 or 2.
Worth evaluating before committing to the Wine route.
