#!/usr/bin/env python3
"""bootsheet.py OUT - a contact sheet of the machine BOOTING, power-on to desktop.

    python3 software/boot/bench/bootsheet.py software/boot/build/bootsheet

⭐ WHY THIS IS NOT checkv3mon.py's make_sheets().  A game scene is a steady
stream: sampling it every 0.6 s gives an even spread of a thing that is always
moving.  A BOOT is the opposite - long stretches where nothing changes at all
(the dialog sits there while the card is read; NitrOS-9 loads behind a screen
that does not move) punctuated by transitions that last one frame.  Sampling on
a clock would spend twenty tiles on the dialog and miss the moment the desktop
appears.

So this samples ON CHANGE: a tile is kept when the picture differs from the last
one kept, with a floor on the gap so a cursor blink does not produce five hundred
tiles, and a ⭐ FORCED tile whenever the POST's progress code changes - because
that is a phase boundary whether or not the pixels moved much.

⚠ THE LABELS COME OUT OF boot.asm, NOT OUT OF THIS FILE.  The P_* equates are
parsed from the ROM's source, so a progress code that is renamed or renumbered
cannot quietly go on being labelled with its old meaning.  A code the source
does not define is labelled as unknown and SAID SO, rather than dropped.
"""
import os, re, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "software", "tools"))
import frames as fr                                          # noqa: E402

BOOT = os.path.join(ROOT, "software", "boot", "boot.asm")
COLS = 3
MIN_GAP = 0.40          # s: two tiles may not be closer than this
# ⛔ AND A CHANGE HAS TO BE A REAL ONE.  video3 draws the pointer as a 16 x 16
# SPRITE, so simply moving the mouse changes 256 pixels and a change-detector
# that counts any difference produces a tile per mouse move - the first run of
# this made 84 tiles, most of them the same screen with the arrow somewhere
# else.  A window opening changes tens of thousands.  0.5 % of the frame sits
# between the two with a wide margin either side.
MIN_CHANGE = 0.005
FONT = "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"


def progress_names(path=BOOT):
    """P_* -> (code, comment), read from the ROM's own source.

    ⚠ A09's form is `P_NAME  EQU  $xx   comment`.  The comment is the label a
    person reads, so it is taken verbatim rather than paraphrased here.
    """
    out = {}
    for line in open(path, encoding="utf-8", errors="replace"):
        m = re.match(r"^(P_\w+)\s+EQU\s+\$([0-9A-Fa-f]{2})\s*(.*)$", line)
        if m:
            name, code, why = m.group(1), int(m.group(2), 16), m.group(3).strip()
            out[code] = (name, re.sub(r"\s+", " ", why))
    return out


def label_for(prog, names):
    if prog in names:
        name, why = names[prog]
        return "$%02X %s%s" % (prog, name, "  -  " + why if why else "")
    return "$%02X  (no P_ equate in boot.asm defines this)" % prog


BOXW, BOXH, LABEL = 640, 480, 40


def tile_of(im, font, small, top, bottom):
    """⚠ ONE BOX FOR EVERY TILE, because the pictures are not one size: the
    POST paints 640x200, its dialog is 640x400 and the desktop is 640x480.
    Each is letterboxed into the same box rather than stretched, so a sheet
    does not silently rescale a 200-line screen into looking like a 480-line
    one - the black bars ARE the information that it is a different mode."""
    im = im.convert("RGB")
    box = Image.new("RGB", (BOXW, BOXH + LABEL), (16, 18, 22))
    if im.size != (BOXW, BOXH):
        w, h = im.size
        sc = min(BOXW / w, BOXH / h)
        im = im.resize((int(w * sc), int(h * sc)), Image.NEAREST)
    box.paste(im, ((BOXW - im.size[0]) // 2, (BOXH - im.size[1]) // 2))
    d = ImageDraw.Draw(box)
    d.text((5, BOXH + 3), top, font=font, fill=(255, 190, 80))
    d.text((5, BOXH + 21), bottom, font=small, fill=(150, 200, 255))
    return box


def dialog_tiles(paths, font, small):
    """⭐ The POST's dialog, from the VERILOG machine, labelled as such.

    ⛔ software/emu does not run the POST's video sections at all - its
    `progress` never leaves $00 and it records no frame until CoArm sets up a
    screen, which run-emu.sh's own PASSING run shows too.  So the dialog
    cannot come from the same run as the desktop, and a sheet that pasted the
    two together silently would be a staged photograph.  Each tile says which
    machine drew it, and the reader can tell.
    """
    out = []
    for path in paths:
        if not os.path.exists(path):
            print("⚠ no %s - the dialog tiles are missing from this sheet" % path)
            continue
        which = "no bootable disk" if "nodisk" in path else "a bootable card in the socket"
        out.append(tile_of(
            Image.open(path), font, small,
            "POST  -  the boot dialog, %s" % which,
            "machine_tb, the card in VERILOG - the C emulator does not run the POST's video"))
    return out


def emu_label(m, names):
    """⚠ NO PROGRESS CODE HERE, and that is the honest label.

    The POST's $FF2F writes are a machine_tb fact: software/emu boots
    NitrOS-9 but never runs the ROM's video sections, so `prog` sits at $00
    for the whole run - run-emu.sh's own passing run shows the same.  Printing
    "$00 (no P_ equate defines this)" on every tile would be true and useless,
    and would read as if the machine were stuck in a phase.  So the phase is
    named only when the model can actually have one.
    """
    if m["prog"]:
        return "software/emu - " + label_for(m["prog"], names)
    return "software/emu - NitrOS-9 and the desktop (this model runs no POST)"


def sheet(out, dialogs=()):
    fp = os.path.join(out, "frames.bin")
    if not os.path.exists(fp):
        print("FAIL  no frames.bin in %s" % out)
        return 1
    names = progress_names()
    if not names:
        print("FAIL  no P_* equates parsed out of %s - the labels would be blank" % BOOT)
        return 1

    font = ImageFont.truetype(FONT, 15)
    small = ImageFont.truetype(FONT, 13)
    tiles = dialog_tiles(dialogs, font, small)
    ndlg = len(tiles)
    kept_px, kept_t, last_prog, t0 = None, -1e9, None, None
    seen_prog = []
    for m, px in fr.read(fp):
        if t0 is None:
            t0 = m["t"]
        if kept_px is None:
            changed = True
        else:
            diff = int(np.count_nonzero(px != kept_px))
            changed = diff >= MIN_CHANGE * px.size
        phase = m["prog"] != last_prog
        if phase:
            seen_prog.append((m["t"] - t0, m["prog"]))
        if not (changed or phase):
            continue
        if (m["t"] - kept_t) < MIN_GAP and not phase:
            continue
        kept_px, kept_t, last_prog = px.copy(), m["t"], m["prog"]

        tiles.append(tile_of(
            Image.fromarray(fr.rgb565_to_rgb8(px)), font, small,
            "%6.2f s   %d x %d   VMODE %d" % (m["t"] - t0, m["w"], m["h"], m["vmode"]),
            emu_label(m, names)))

    if not tiles:
        print("FAIL  frames.bin has no frames")
        return 1

    tw, th = tiles[0].size
    paths = []
    per = COLS * 6
    for p in range(0, len(tiles), per):
        grp = tiles[p:p + per]
        rows = (len(grp) + COLS - 1) // COLS
        sh = Image.new("RGB", (COLS * tw, rows * th), (0, 0, 0))
        for i, t in enumerate(grp):
            sh.paste(t, ((i % COLS) * tw, (i // COLS) * th))
        path = os.path.join(out, "boot-sheet-%d.png" % (p // per + 1))
        sh.save(path)
        paths.append(path)

    print("ok    %d tiles on %d sheet(s): %s" % (len(tiles), len(paths), ", ".join(paths)))
    print("      %d from machine_tb (the POST, in Verilog), %d from the emulator's frames.bin"
          % (ndlg, len(tiles) - ndlg))
    print("      phases, in the order the machine reached them:")
    for t, pr in seen_prog:
        print("        %6.2f s  %s" % (t, label_for(pr, names)))
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    dl = []
    if "--dialog" in a:
        i = a.index("--dialog")
        dl = a[i + 1:]
        a = a[:i]
    sys.exit(sheet(a[0] if a else os.path.join(HERE, "..", "build", "bootsheet"), dl))
