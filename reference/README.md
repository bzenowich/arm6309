# `reference/` — datasheets, manuals and ROMs

Primary sources. Nothing here is written by this project; it is the material the
specifications are checked *against*, and the documents cite it by filename and page
wherever a claim rests on it.

| | |
|---|---|
| [`datasheets/`](datasheets/) | chip documentation — the 6809/6309 and the STM32 |
| [`manuals/`](manuals/) | machine and OS documentation |
| [`schematics/`](schematics/) | scanned schematics |
| [`articles/`](articles/) | prior art and design history — narratives, not schematics |
| [`68k/`](68k/) | 68000-era material, kept for reading |

## The big scans are not in git

PDFs and TIFFs under `reference/` are `.gitignore`d — about 93 MB of scans, all freely
available from the vendors and from
[colorcomputerarchive.com](https://colorcomputerarchive.com). Each subdirectory's README
lists exactly which files are expected and what cites them, so a fresh clone can be
refilled deliberately rather than by guessing.

Small binaries that *are* tracked — the ROM and source archives in `68k/` — are tracked
because they are small and because they are not obtainable by the same one-click route.

## The confidence convention

Several documents carry a "Sources and confidence" table that grades every claim class as
**verified against the PDF**, *recalled and corroborated*, or ⚠ **flagged — verify before
relying on**. That grading is the point of keeping this directory: a claim marked
"verified" names the file and page here, and one that cannot is marked ⚠ instead.
