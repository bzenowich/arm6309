# `software/nitros9/video/` — NitrOS-9 on the virtual machine, as a video

One NitrOS-9 Level 2 session on the host emulator, typed and moused by script. The video shows
the video card's picture on the left and the serial console on the right.

```sh
sh software/nitros9/video/run-video.sh     # ROM, session, encode -> nitros9-progress.mp4
NOBUILD=1 sh software/nitros9/video/run-video.sh
```

⚠ **This is the emulator (`software/demo/emu/`), not the RTL machine.** The video console has
not run on `machine_tb` (`../docs/video-console.md`). The video is **silent**: there is no
NitrOS-9 audio driver yet (`docs/nitros9-av-plan.md` phase P4).

| | |
|---|---|
| `session.py` | the session: commands typed at `/Term`, keys typed on the PS/2 keyboard, the mouse's path, and the captions |
| `run-video.sh` | builds the ROM (`../mkrom.sh`) and the emulator, runs the session, and fails if it did not finish or a command printed `Error #` |
| `mkvideo.py` | 1920 × 1080 at 60 fps: the screen at 1280 × 960, a caption under it, and `/Term` in 80 columns of the VGA font, each byte shown when it was transmitted |
| `build/` | untracked: the ROM, `frames.bin`, `serial.times`, `console.txt`, `emu.log` |

## How the session is driven

The emulator takes these inputs (`machine.c`'s header lists them):

- **`SERIAL_GATE`** holds each typed line until the shell's prompt (`DD:`) arrives.
  `SERIAL_TYPE` spaces the characters, `SERIAL_THINK` waits after the prompt, and a `$01` byte
  in the input is a one-second pause that is not sent.
- **`SERIAL_TIMES`** records when each byte was transmitted, so the console panel shows the
  real timing.
- **`PS2_KBD_GATE`** and **`PS2_MOUSE_GATE`** hold the keyboard's and the mouse's scripts until
  a string has been transmitted (an `echo` in the session). `w<ms>` in a PS/2 script is a pause.

## The scenes

Boot; `dir`, `mfree` and `procs` at `/Term`. `/W1` and `/W2` text windows. A second shell on
`/W1`, typed at on the PS/2 keyboard. `/W3`'s bitmap window, with the mouse moving the pointer.
Select `/W4` and back. `vgp3`'s extension escapes and ANSI overlay. `rastbar`, `wave` and
`overworld`. `procs` again, then `reboot` back through the boot ROM's POST.

## ⛔ What making it found

With `vtp1` drawn on `/W1` and `/W1` still defined, **`copy /dd/sys/vgp2a /w3` fails at open
with error 64**. In the longer session, the next `Select` of `/W4` then sent CoArm (task 1)
wild. It is repeatable in a few emulator seconds:

```
iniz w1 / copy /dd/sys/vtp1 /w1 / iniz w3 / copy /dd/sys/vgp2a /w3   -> Error #064
```

The failure needs `vtp1`'s content. `vtw2` on `/W2`, a bare `iniz w1`, a shell on `/W1`, and
drawing `/W3` before `vtp1` all work, and so does `deiniz w1` first. `iniz w3` before `vtp1`
does not help. `run-vid.sh` never sees it
because each of its runs is a fresh boot with one client. The session ends `/W1` after
`vtp1` (`deiniz w1`) to get past it. **Not fixed.**
