#!/usr/bin/env python3
"""pcssheet.py - every shipped table as the CARD painted it, on one sheet.

⭐ The pictures are read out of each run's `vram.bin`, so this is the machine's
own framebuffer and not a re-render of the model.  Beside each name it prints
how many of the 153,600 card pixels differ from `mkpcs.render_table`'s - the
same comparison `checkpcs.py` gates on - so a sheet that looks right and a
sheet that IS right are distinguishable at a glance.

    sh software/pcs/bench/run-pcssheet.sh          # builds the runs, then this
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mkpcs                                                  # noqa: E402
import pcsfile                                                # noqa: E402
import pcspal                                                 # noqa: E402
import pcspak as K                                            # noqa: E402

STRIDE = 1024


def shot(vram, w, h):
    return [vram[y * STRIDE:y * STRIDE + w] for y in range(h)]


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'build', 'pcs')
    png = sys.argv[2] if len(sys.argv) > 2 else os.path.join(out, 'tables.png')
    from PIL import Image, ImageDraw

    pal = pcspal.palette()
    tables = list(pcsfile.demo_tables())
    if not tables:
        print('no tables - the disk images are not in reference/')
        return 1

    cells = []
    for i, (name, logic, wset, objs) in enumerate(tables):
        d = os.path.join(out, 't%d' % i)      # run-pcssheet.sh names them
        vf = os.path.join(d, 'vram.bin')
        if not os.path.exists(vf):
            print('%-22s no run' % name)
            continue
        vram = open(vf, 'rb').read()

        # ⭐ The model's picture, for the pixel count beside the name.
        for o in objs:
            o.fillcolor = pcspal.FROM_APPLE.get(o.fillcolor, pcspal.PAINT0 + 5)
        pak = K.Pak(height=mkpcs.TH, width=mkpcs.TW)
        pak.objs = objs
        note = ''
        try:
            pak.display()
            fb, w, h = mkpcs.render_table(pak, objs, None)
            bad = sum(1 for y in range(h) for x in range(w)
                      if vram[y * STRIDE + x] != fb[y * w + x])
            note = 'exact' if bad == 0 else '%d px' % bad
        except Exception as e:                    # a table the converter refuses
            w, h = mkpcs.TW * mkpcs.SCALE, mkpcs.TH * mkpcs.SCALE
            note = str(e)[:18]

        im = Image.new('RGB', (w, h))
        px = im.load()
        for y in range(h):
            row = vram[y * STRIDE:y * STRIDE + w]
            for x in range(w):
                px[x, y] = pal[row[x]]
        cells.append((name.replace('.PB', ''), note, im))
        print('%-22s %s' % (name, note))

    # ── the sheet ────────────────────────────────────────────────────────
    NC = 6
    NR = (len(cells) + NC - 1) // NC
    TW_, TH_ = 150, 225                           # a table, scaled to fit
    PAD, CAP, HEAD = 10, 26, 46
    CW, CH = TW_ + PAD, TH_ + CAP
    sheet = Image.new('RGB', (NC * CW + PAD, HEAD + NR * CH + PAD), (16, 16, 22))
    d = ImageDraw.Draw(sheet)
    d.text((PAD, 10), 'PINBALL CONSTRUCTION SET - %d shipped tables, painted by '
           'the video3 card' % len(cells), fill=(235, 235, 245))
    d.text((PAD, 26), 'vram.bin from `pcs <mode> 30`; the note is how far the '
           'card is from PPAK.s + render_table', fill=(140, 140, 160))
    for i, (name, note, im) in enumerate(cells):
        cx = PAD + (i % NC) * CW
        cy = HEAD + (i // NC) * CH
        sheet.paste(im.resize((TW_, TH_), Image.NEAREST), (cx, cy))
        d.text((cx, cy + TH_ + 2), name[:22], fill=(235, 235, 245))
        d.text((cx, cy + TH_ + 13), note,
               fill=(120, 220, 140) if note == 'exact' else (240, 140, 120))
    sheet.save(png)
    print('\nwrote %s  (%d x %d)' % (png, sheet.width, sheet.height))
    return 0


if __name__ == '__main__':
    sys.exit(main())
