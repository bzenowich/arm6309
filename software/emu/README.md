# `software/emu/` — the host emulator

`machine.c` is the whole machine on the host — a cycle-counted 6809/6309 (`hardware/cpu/sim/cpu6809.c`, `hd6309.c` — the CPU models are `hardware/cpu`'s), the motherboard, the video3 card (`VIDEO3=1`), the audio card, the storage card with an SD image, and PS/2 and serial at line level. **Every software bench runs on it.**

| | |
|---|---|
| Tests | the CPU cores' are `hardware/cpu/sim/test/run.sh` (`make -C hardware/cpu sim`); here, `test/run-sdtest.sh`, `test/run-ps2script.sh` (the PS/2 input script, 27 claims) |
| Diagnostics | `TRACE_AT`/`TRACE`, `WATCH`, `MARKS`, `VRAMDUMP`, `KEEPFRAMES` — see `CLAUDE.md`'s trace note; `test/pchist.py` weights a trace by dots |
| Reference | [`reference/`](reference/) |

