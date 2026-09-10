# `software/` — code that runs *on* the machine

Guest software: 6809/6309 code executed by the CPU, as opposed to the STM32 firmware in
[`../cpu/`](../cpu/) that *is* the CPU. The two were in the same directory until this
tree was reorganised, and they are not the same kind of thing at all — different target,
different toolchain, different lifecycle.

| | |
|---|---|
| ⭐ [`boot/`](boot/) | **`boot.asm` — the machine's own first instructions**, and the only code in this repository that has ever executed. `machine.md` §7.2's boot sequence plus a video bring-up |
| ⭐ [`tools/`](tools/) | `fetch-a09.sh` — the assembler, fetched and built on demand — and `mkrom.sh`, which turns `boot.asm` into the ROM image the simulation loads |
| [`6809/`](6809/) | third-party 6809 code, imported as-is: a monitor and a FORTH. **Neither has been assembled yet** |

Expected to grow: the mod replayer of
[`../audio/docs/modplayer.md`](../audio/docs/modplayer.md) §5 is 6309 native-mode
assembly and belongs here once it is transliterated from
[`../audio/refplayer/`](../audio/refplayer/), as does anything written against the
video card's register map.

⭐ **There is an assembler now**, and it is not ours: **A09** (Hermann Seib), GPL v2,
6809 *and* 6309, fetched to a scratch directory and built by
[`tools/fetch-a09.sh`](tools/fetch-a09.sh). Nothing GPL is committed here — the same
rule `hardware/gal/verilog/oracle/fetch-paula.sh` states for `Paula.v`, applied to a
build tool rather than to a model.

Nothing here is built by CMake. `npm run rom` from `hardware/` is the build, because
that is where every other check in this project runs from.
