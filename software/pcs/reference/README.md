# `software/pcs/reference/`

The original. **Everything the port is checked against comes from here.**

| File | What | Tracked |
|---|---|---|
| [`pcs-source/`](pcs-source/) | Bill Budge's 6502 sources for the Atari 800 *Pinball Construction Set* (1983), **MIT-licensed** by the author — `pcs-source/README.md` has the provenance and the licence | ✓ |
| `pinball2.dsk` | a retail disk image; `bench/pcsfile.py` reads the shipped tables off it and `bench/mkpcs.py` writes them to `bench/pcstbl/*.pbt` | ✗ — a retail disk is not the MIT sources, and the right to redistribute is the criterion |
| `a2_asimov_pinball_construction_set.zip` | the Apple II release, from the Asimov archive, for comparison | ✗ — same rule |

A clone without the two images simply has no tables on the card; every bench that
names one says so rather than passing vacuously (`docs/pcs.md` §5c).
