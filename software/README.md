# `software/` — code that runs *on* the machine

Guest software: 6809/6309 code the CPU executes, and the host-side tools that build,
model and check it. (The STM32 firmware that *is* the CPU is hardware:
[`../hardware/cpu/`](../hardware/cpu/).)

⚠ **The NitrOS-9 port and every application's 6809 source live in `../nitros9`**, on
its `arm6309` branch (`level2/arm6309/`, `recipes/arm6309/`), because the NitrOS-9
recipe builds them there. Each program's README below names its files. Everything
else — generators, models, benches, art, docs — is here.

| | |
|---|---|
| [`boot/`](boot/) | ⭐ **`boot.asm`, the machine's first instructions**: the POST, the video3 bring-up, the SD card reader and the boot dialog, and the hand-off to NitrOS-9's `boot_sd`. `v3boot/` is `v3machine_tb`'s fixture ROM |
| [`toolbox/`](toolbox/) | the **ROM toolbox** — reusable drawing routines (proportional text, rectangles, copies, icons) shared by the boot dialog and CoArm; its ROM pages are built by `tools/mktbox.py` |
| [`nitros9/`](nitros9/) | NitrOS-9 Level 2 on this machine: `mkrom.sh` (the ROM), `mksyscard.sh` (a bootable system card), `run-sdboot.sh` (boots only off the card), `run-emu.sh`, and the port's docs |
| [`desk/`](desk/) | ⭐ the **desktop** the boot ends at — menu bar, icons, the Tracker file manager, a draggable window — and its demo video |
| [`pcs/`](pcs/) | ⭐ **Pinball Construction Set**, Bill Budge's 1983 original ported from his 6502, with the simulation proved against a transliteration |
| [`stardew/`](stardew/) | a Stardew-like farm whose day passes in the palette |
| [`monster/`](monster/) | *Mayhem in Monsterland*-style block-streamed platform world |
| [`mvania/`](mvania/) | a metroidvania scene — the frame-budget measurement scene |
| [`tilescroll/`](tilescroll/) | **Explore**: a camera over a 4096 × 2048 world |
| [`paint/`](paint/) | Paint, the BBS and the ANSI-art viewer (Blocktronics' *we-tortuga*) — recorded CoArm streams |
| [`emu/`](emu/) | ⭐ the **host emulator**, `machine.c` — every software bench runs on it |
| [`tools/`](tools/) | shared host tools: [`video/`](tools/video/), which makes every program's demo video (`make -C software/<program> video`); the frame decoder (`frames.py`), the show and icon art (`show.py`, `mkshow.py`, `mkparrots.py`), and the fetchers for A09, LWTOOLS/ToolShed and ffmpeg (built into the repository's `.tools/`) |
| [`6809/`](6809/) | third-party 6809 code, imported as-is: a monitor and a FORTH. Never assembled |
| [`archive/`](archive/) | retired software — frozen |

A09 (Hermann Seib, GPL v2) assembles `boot.asm`; LWTOOLS and ToolShed (GPL) build
NitrOS-9. None of them is committed: `tools/fetch-*.sh` fetch and build them.
