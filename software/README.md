# `software/` — code that runs *on* the machine

Guest software: 6809/6309 code executed by the CPU, as opposed to the STM32 firmware in
[`../cpu/`](../cpu/) that *is* the CPU. The two were in the same directory until this
tree was reorganised, and they are not the same kind of thing at all — different target,
different toolchain, different lifecycle.

| | |
|---|---|
| [`6809/`](6809/) | third-party 6809 code, imported as-is: a monitor and a FORTH |

Expected to grow: the mod replayer of
[`../audio/docs/modplayer.md`](../audio/docs/modplayer.md) §5 is 6309 native-mode
assembly and belongs here once it is transliterated from
[`../audio/refplayer/`](../audio/refplayer/), as does anything written against the
video card's register map.

Nothing here is built by CMake — there is no 6809 assembler in the build yet.
