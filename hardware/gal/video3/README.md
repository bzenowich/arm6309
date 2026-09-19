# `hardware/gal/video3/` — video3's programmable parts

```sh
cd hardware
bun run gal/video3/v3scan.cpld.ts > gal/video3/v3scan.pld       # the term list -> CUPL
sh gal/prjbureau/fit1508.sh gal/video3/v3scan.pld               # place and route
V3_MAPQ=discrete bun run gal/video3/v3scan.cpld.ts > gal/video3/v3scan_mq.pld
sh gal/prjbureau/fit1508.sh gal/video3/v3scan_mq.pld
```

⛔ **One fit at a time** — the Wine prefix is one shared working directory, and two
concurrent fits write the same `cpld/<name>.fit`. And **"Design fits successfully"
appears only in the fitter's stdout, never in the `.fit`**: `fit1508.sh` requires that
sentence, which is the only thing standing between a failed fit and a *convincing*
`.fit` left over from the last one. `CLAUDE.md`'s trap list has both.

⭐ **All four CPLDs take the register broadcast** (`RA4..RA0` + `REGWR`) and decode their
own offsets from `regmap.ts`, which is the single table plan §10 specifies.

| | cells | I/O | cascades | |
|---|---|---|---|---|
| **`v3scan`** | **112 / 128** | 63 / 64 | 3 | ⭐ the build — the map word in silicon, the attribute onto the LUT |
| `v3scan_mq` | 107 / 128 | 46 / 64 | ⚠ **41** | the map word in four `'574` — ⚠ a fit of the 2026-09-16 term list, before the four-byte cell and the three-stage attribute |
| **`v3dot`** | **121 / 128** | 63 / 64 | ⚠ **5** | ⭐ the build — a 16×16 sprite, shifters in 4 × `'165` |
| `v3dot_si` | — | — | — | ⛔ shifters in silicon: **`Design does not fit`** |
| **`v3ptr`** | **124 / 128** | 58 / 64 | **3** | ⭐ the build — ascending copies only |
| `v3ptr_rows` | — | — | — | ⛔ row direction: **`INTERNAL ERROR`** |
| `v3ptr_both` | — | — | — | ⛔ both directions: **`INTERNAL ERROR`** |
| **`v3host`** | **58 / 128** | ⛔ **64 / 64** | **0** | ⭐ the build — the broadcast |
| `v3host_st` | 51 / 128 | ⛔ **64 / 64** | 0 | one load strobe per register — **replaced** |

⛔ **Keep a rejected variant's fit, do not overwrite it.** The three `v3ptr` rows are the
evidence for plan §6.2's decision, and the first write-up quoted a figure after the run
that produced it had already been overwritten by the next variant — `check:docs` found a
number with no design output behind it. `CLAUDE.md`'s first trap, wearing different
clothes.

⛔ **`v3host_st` is kept fitted because it is the evidence**, not because it is an option:
one load strobe per register puts that part at 64 / 64 pins with 77 macrocells idle. It is
also **unable to load a register wider than the bus** — `WPTR` is 19 bits across three
bytes — which is how `+$08`'s `D0` came to drive both `WC0` and `WC8`. `partition.md` §0
has what the swap cost each part; the short version is that only `v3dot` paid, one cell.

⛔ **`v3ptr_rows` and `v3ptr_both` have no `.fit` here any more.** They fitted at 128 / 128
under the strobe wiring and **refuse outright** under the per-bit loads, so their old
reports were deleted: a `.fit` that describes a term list which no longer exists is the
same trap as a stale one, wearing a date that looks current.

⭐ **`V3_MAPQ`, `V3_COPYDIR`, `V3_SPRSHIFT` and `V3_DECODE` are switches and not comments**, the way `ARM6309_LIST`
is in `gal/video.cpld.ts`: every side of both is fitted, and the differences *are* the
answers to `partition.md` §5 risk 2 and plan §6.2.

⛔ **`v3dot_si` has no `.fit` in this directory ON PURPOSE.** `fit1508.exe` answered
`INTERNAL ERROR` and **wrote a report anyway**, in the Wine prefix — `CLAUDE.md`'s
nastiest trap, live. `fit1508.sh` requires the sentence *"Design fits successfully"*,
which appears only in stdout, and refused to copy it out. **A rejected variant gets a
fit only when it fits.**

## `v3lane` — the one GAL

`v3lane.jedec.ts` is a `GAL22V10`, 10 of 10 macrocells and 10 inputs: the four lane
`'245`s' `/OE`, the four byte enables, `PWOE` and `RFOE` (`partition.md` §2.5). Like every
GAL here it ships with a CUPL reference, `gal/jedec/reference/v3lane.cupl.jed`, and

```sh
bun run gal/video3/v3lane.check.ts     # part of npm run check
```

writes `v3lane.jed`, `.doc` and `.pld` and sweeps all 1,024 inputs — the fuse map
against a model written from the board's rules, then against CUPL's compile of the
`.pld`.
