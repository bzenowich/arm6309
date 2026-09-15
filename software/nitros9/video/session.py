#!/usr/bin/env python3
"""session.py OUT - the NitrOS-9 progress video's session, as the emulator's inputs.

    OUT/typed.txt   SERIAL_IN: the commands typed at /Term, a line per shell prompt
                    (SERIAL_GATE); each $01 byte is a one-second pause, not sent
    OUT/kbd.txt     PS2_KBD: a line typed on the PS/2 keyboard into a shell on /W1
    OUT/mouse.txt   PS2_MOUSE: a tour of /W3 with the pointer

CAPTIONS says what each scene shows. mkvideo.py puts one under the screen from the
moment its trigger has been transmitted on the serial port.
"""
import math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
import vtmodel  # noqa: E402

P = "\x01"          # a second


def pause(s):
    return P * s


# (typed at /Term, seconds to wait once the shell has taken it)
LINES = [
    ("dir", 2), ("mfree", 3), ("procs", 2),
    # the text console: /W1 80 x 25 in cell mode, then /W2 80 x 30 made while /W1 shows
    ("iniz w1", 0), ("copy /dd/sys/vtp1 /w1", 4),
    ("iniz w2", 0), ("copy /dd/sys/vtw2 /w2", 0), ("display 1b 21 >/w2", 4),
    # a second shell, on /W1, fed by the PS/2 keyboard (kbd.txt waits for this line)
    ("display 1b 21 >/w1", 1), ("shell i=/w1&", 0),
    ("echo now typing on the PS/2 keyboard", 23),
    # bitmap windows: /W3 640 x 200, the pointer toured by the PS/2 mouse
    ("iniz w3", 0), ("copy /dd/sys/vgp2a /w3", 0), ("display 1b 21 >/w3", 1),
    ("echo now moving the PS/2 mouse", 9),
    ("iniz w4", 0), ("copy /dd/sys/vgp2b /w4", 0), ("display 1b 21 >/w4", 4),
    ("display 1b 21 >/w3", 3),
    # the extension escapes and an ANSI overlay
    ("display 1b 24 >/w3", 0), ("copy /dd/sys/vgp3 /w3", 5),
    # display lists, rewritten every frame by SS.Raster
    ("display 1b 24 >/w3", 0), ("rastbar >/w3", 1),
    ("display 1b 24 >/w3", 0), ("wave >/w3", 1),
    # the demo's game, on an exclusive tile screen
    ("display 1b 24 >/w3", 0), ("overworld >/w3", 1),
    ("display 1b 24 >/w3", 0), ("procs", 3),
    # back through the boot ROM's POST
    ("reboot", 0), ("dir", 2),
    ("echo DONE-arm6309", 0),
]

KBD_GATE = "PS/2 keyboard"
KBD_LINES = ["dir /dd/cmds", "mfree", "procs", "echo typed on /W1 >/term"]

MOUSE_GATE = "PS/2 mouse"

# (trigger on the serial output, caption)
CAPTIONS = [
    ("RKBoot", "NitrOS-9 Level 2 boots from ROM: loader, kernel, bootfile from the ROM disk"),
    ("DD:dir", "A shell on the TL16C550C: dir, mfree (8 MB on 16-bit blocks), procs"),
    ("vtp1 /w1", "/W1: an 80x25 text window in cell mode, one write a character"),
    ("21 >/w2", "Select /W2: 80x30, drawn while /W1 was on the screen"),
    ("i=/w1&", "A second shell on /W1, typed at on the PS/2 keyboard"),
    ("vgp2a /w3", "/W3: a 640x200 bitmap window - text styles, lines, circles, fills, GP buffers"),
    ("PS/2 mouse", "The PS/2 mouse: the pointer is drawn into VRAM from the kernel's idle loop"),
    ("21 >/w4", "Select /W4: 640x240, drawn in DRAM while /W3 was displayed"),
    ("vgp3 /w3", "Extension escapes: patterns, polygons, icons, images, an ANSI overlay"),
    ("rastbar >", "rastbar: a display list rewritten every frame - a palette entry per scanline"),
    ("wave >", "wave: a per-scanline HSCROLL list, by SS.Raster"),
    ("overworld >", "overworld: the demo's game on an exclusive tile screen - SS.Excl, SS.Batch"),
    ("DD:procs", "procs: both shells still running"),
    ("DD:reboot", "reboot: back through the boot ROM's power-on self-test, and up again"),
]


def typed():
    return "".join(cmd + "\r" + pause(s) for cmd, s in LINES).encode()


def keys():
    out = ["w1500"]
    for line in KBD_LINES:
        for ch in line + "\r":
            out.append(vtmodel.scancodes(ch))
            out.append("w90")
        out.append("w3500")
    return " ".join(out)


def mouse():
    """ps2.md 11.3's packets: to the top left, then a slow figure of eight."""
    out = ["w800"]
    steps = [(-127, 127)] * 8                     # the corner, whatever the start
    x, y = 0.0, 0.0
    px, py = 0, 0
    n = 300
    for i in range(1, n + 1):
        a = 2 * math.pi * i / n
        x, y = 320 + 260 * math.sin(a), 100 - 80 * math.sin(2 * a)
        if i == 1:
            steps.append((int(x), -int(y)))       # PS/2 y is up
            px, py = int(x), int(y)
            continue
        dx, dy = int(round(x)) - px, int(round(y)) - py
        px, py = px + dx, py + dy
        steps.append((dx, -dy))
    for dx, dy in steps:
        while dx or dy:
            sx, sy = max(-127, min(127, dx)), max(-127, min(127, dy))
            b0 = 0x08 | (0x10 if sx < 0 else 0) | (0x20 if sy < 0 else 0)
            out.append("%02X %02X %02X" % (b0, sx & 0xFF, sy & 0xFF))
            dx, dy = dx - sx, dy - sy
    return " ".join(out)


if __name__ == "__main__":
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, "typed.txt"), "wb").write(typed())
    open(os.path.join(out, "kbd.txt"), "w").write(keys())
    open(os.path.join(out, "mouse.txt"), "w").write(mouse())
