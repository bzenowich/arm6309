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

```sh
# the Atmel fitters are 32-bit Windows binaries
sudo dpkg --add-architecture i386 && sudo apt update && sudo apt install wine32:i386

# prjbureau's front end
sudo apt install yosys

# PEP 668 blocks a system pip install, so a venv
python3 -m venv .venv && .venv/bin/pip install bitarray
```

and then the one thing no package manager provides:

> ⚠ **The Atmel ATF15xx fitters** (`fit1502.exe`, `fit1504.exe`, `fit1508.exe` and
> their data files) have to go in prjbureau's `vendor/`. They ship with WinCUPL and
> with Microchip's standalone ATF15xx fitter package. **This sandbox's proxy refuses
> `microchip.com`**, so that download is a human step.

With those in place:

```sh
git clone https://github.com/whitequark/prjbureau && cd prjbureau
# add an atf1508xx entry to fuzzers/000-init/fuzzer.py using atf1508_pins.json:
#   blocks = "ABCDEFGH", 8 blocks x 16 macrocells, specials TDI=M32 TMS=M48
#   TCK=M96 TDO=M112, and the PLCC84/TQFP100 pin lists from that file
./bootstrap.sh
```

`bootstrap.sh` runs every fuzzer in turn and rewrites `database.json`.

## What the spike is meant to answer

Not "does it work" — **how long the tail is.** whitequark took the 1502 to Complete,
the 1504 to Near-complete and the 1508 to Partial, and gives the reason as
*"peculiarities of the toolchain"* rather than anything architectural. The 1508 is the
same architecture with 8 blocks instead of 4, and the fuzzers are parameterised by
block count, so most of them should simply run. **The number worth measuring is what
fraction of fuses resolve** — and specifically whether the `uim_mux` fuzzers (025–027),
which map the 40-of-~200 switch matrix, scale to eight blocks. That matrix is the
thing that makes fitting a search problem rather than arithmetic, and it is where a
"peculiarity" would most plausibly live.
