#!/usr/bin/env python3
"""video3's character mode, rendered from the plan rather than from the ROM.

    python3 video3/tools/v3model.py <frames.bin> <v3char.json>

It shares DATA with the 6809 (bench/v3char.json) and no code, which is the
discipline software/nitros9/tools/vtmodel.py keeps: two implementations of
plan §2.2 and §3 agreeing is evidence, one implementation agreeing with itself
is not.

plan §3:   row[x] = LUT[(attr << 8) | glyphpixel]
plan §2.5: the map is two bytes a cell on a 1024-byte stride, six-bit cell row,
           no ring and no horizontal scroll - so cell column is x >> 3 and
           nothing wraps.
"""
import json, os, sys

def render(d, height, dbl=2):
    """The picture video3 must show, as RGB565 words.

    ⭐ `dbl` is 2 for VMODE 00 and 01 (line-doubled, 400 and 480 scanlines for
    200 and 240 picture rows) and 1 for VMODE 10 and 11 (progressive, 400 and
    480 picture rows - 80x50 and 80x60, the geometries `video` cannot reach in
    cell mode at all)."""
    glyphs = {int(k): v for k, v in d["glyphs"].items()}
    pal = d["pal"]
    out = []
    for y in range(height):
        py = y // dbl
        crow, grow = py >> 3, py & 7
        row = []
        for x in range(640):
            ccol = x >> 3
            if crow < d["rows"] and ccol < d["cols"]:
                code, attr = d["map"][crow][ccol]
            else:
                code, attr = 0, 0        # VRAM is zero outside the written map
            g = glyphs.get(code)
            px = 0 if g is None else (1 if g[grow] & (0x80 >> (x & 7)) else 0)
            row.append(pal[attr][px])
        out.append(row)
    return out

# software/demo/tools/frames.py already reads machine.c's recording, bitmap and
# all - reusing it is what stops a second transcription of the format.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..",
                                "software", "demo", "tools"))
import numpy as np
import frames as fr


def copy_result(d):
    """plan §6, applied to VRAM as an array.  ⭐ CPTR and WPTR name the FIRST
    CELL PROCESSED and the direction bits step from there - naming the origin
    and walking inside the rectangle would need origin + h - 1, an adder the
    card does not have (plan §6.2, corrected 2026-09-16)."""
    W, H = d["w"], d["h"]
    vram = np.zeros((512, 1024), dtype=np.uint8)
    r = np.arange(H)[:, None]; c = np.arange(W)[None, :]
    vram[:H, :W] = ((r * 7 + c * 3) & 0xFF).astype(np.uint8)
    for _, sr, sc, dr, dc, w, h, rd, cd in d["copies"]:
        assert rd == 0 and cd == 0, (
            "the card has no direction bits - v3ptr's fit priced them at 18 "
            "macrocells, so an overlapping copy stages through scratch")
        for y in range(h):
            sy, dy = (sr + y if rd == 0 else sr - y), (dr + y if rd == 0 else dr - y)
            for x in range(w):
                sx, dx = (sc + x if cd == 0 else sc - x), (dc + x if cd == 0 else dc - x)
                vram[dy & 511, dx & 1023] = vram[sy & 511, sx & 1023]
    return vram


def render_bitmap(vram, height, vscroll=0, pal=None, dbl=2):
    """plan §2.3: the pixel byte is the LUT's low eight bits and ATTR is zero,
    so with sub-palette 0 loaded as i -> i * $0101 a pixel IS its VRAM byte."""
    out = np.zeros((height, 640), dtype="<u2")
    for y in range(height):
        ry = (vscroll + y // dbl) & 511
        b = vram[ry, :640].astype(np.uint16)
        out[y] = b * 0x0101 if pal is None else pal[b]
    return out


def background(height, vscroll=0):
    vram = np.zeros((512, 1024), dtype=np.uint8)
    r = np.arange(200)[:, None]; c = np.arange(640)[None, :]
    vram[:200, :640] = ((r * 7 + c * 3) & 0xFF).astype(np.uint8)
    return vram


def render_sprite(d, height, sx, sy, vram, dbl=2):
    """plan §7: the sprite's two bits are the ATTR half of the LUT address, so
    0 is transparent and 1 and 2 are sub-palettes 1 and 2 - which this ROM
    loads as $F800 and $001F in ALL 256 entries, so the pixel under them does
    not matter.  Bitmap mode only."""
    out = render_bitmap(vram, height, dbl=dbl)
    shape = d["shape"]
    for y in range(height):
        py = y // dbl
        if not (sy <= py < sy + 8):
            continue
        for x in range(640):
            if not (sx <= x < sx + 8):
                continue
            sr, sc = py - sy, x - sx
            lo, hi = shape[sr * 2], shape[sr * 2 + 1]
            attr = ((hi >> (7 - sc)) & 1) * 2 + ((lo >> (7 - sc)) & 1)
            if attr == 1:   out[y][x] = 0xF800
            elif attr == 2: out[y][x] = 0x001F
    return out


def render_tile(d, height, hs, vs, dbl=2):
    """plan §2.4: a ONE-byte map, 8bpp tiles, both scroll axes, a six-bit cell
    row - and ATTR is ZERO, so every pixel comes from sub-palette 0.  The bank
    is the formula the ROM computes; the map is the table the ROM streams."""
    out = np.zeros((height, 640), dtype="<u2")
    mp, a, b = d["map"], d["tile_a"], d["tile_b"]
    for y in range(height):
        ry = (vs + y // dbl) & 511
        crow, grow = (ry >> 3) & 63, ry & 7
        for x in range(640):
            cx = (hs + x) & 1023
            t = mp[crow * d["cell_cols"] + ((cx >> 3) & 127)]
            px = (t * a + (grow * 8 + (cx & 7)) * b) & 0xFF
            out[y][x] = px * 0x0101          # sub-palette 0 is the identity
    return out


if __name__ == "__main__":
    d = json.load(open(sys.argv[2]))
    got = [(meta, px) for meta, px in fr.read(sys.argv[1])]
    if not got:
        print("FAIL  no frames in the recording"); sys.exit(1)
    meta, last = got[-1]
    if "vmodes" in d:
        # ⭐ every frame carries the VMODE the ROM had settled on, so one run
        # covers 80x25, 80x30, 80x50 and 80x60.
        want_v = {v[0]: v for v in d["vmodes"]}   # marker -> (mk,h,dbl,ctrl,title)
        seen, bad, checked = set(), 0, 0
        for meta, px in got:
            v = meta["herok"]
            if v not in want_v:
                continue
            _, h, dbl, cv, title = want_v[v]
            if meta["h"] != h:
                print(f"FAIL  VMODE {v:02b} ({title}): {meta['h']} active lines, want {h}")
                sys.exit(1)
            if meta["vmode"] != cv:
                print(f"FAIL  {title}: the frame reports CTRL VMODE "
                      f"{meta['vmode']:02b}, want {cv:02b}")
                sys.exit(1)
            want = np.array(render(d, h, dbl), dtype="<u2")
            n = int((want != px).sum())
            if n and bad == 0:
                ys, xs = np.nonzero(want != px)
                y0, x0 = int(ys[0]), int(xs[0])
                print(f"      first difference at ({x0},{y0}) in {title} "
                      f"- cell ({x0 >> 3},{y0 // dbl >> 3})")
            bad += n; checked += 1; seen.add(v)
        print(f"      {len(got)} frames, {checked} judged, "
              f"{len(seen)} of {len(want_v)} VMODEs seen")
        miss = [want_v[v][3] for v in want_v if v not in seen]
        if miss:
            print(f"FAIL  never reached a frame: {miss}"); sys.exit(1)
        print(("FAIL  " if bad else "ok    ") +
              "⭐ character mode in all four geometries - " +
              ", ".join(want_v[v][4].split(",")[0] for v in sorted(want_v) if v < 4) +
              f" - every pixel is the plan's ({bad} differ)")
        # ⭐ plan §7's negative, reported as its own claim: marker 4 renders the
        # VMODE 00 picture with the sprite ARMED, so a leak is a difference.
        print(("FAIL  " if bad else "ok    ") +
              "⭐ the sprite is bitmap-mode only: armed at (32,8) over a cell whose "
              "attribute is $2A, character mode shows no trace of it")
        sys.exit(1 if bad else 0)
    if "pos" in d and "map" in d:
        # ⭐ every frame carries the scroll it was rendered at, set only after
        # the frame-start latch had taken it (plan §8.1)
        want_pos = {(h, vs | (vm << 12)): (h, vs, vm) for h, vs, vm in d["pos"]}
        seen, bad, checked, green = set(), 0, 0, 0
        for meta, px in got:
            key = (meta["camk"], meta["herok"])
            if key not in want_pos:
                continue
            hs, vs, vm = want_pos[key]
            if meta["vmode"] != vm:
                print(f"FAIL  the frame reports VMODE {meta['vmode']:02b}, want {vm:02b}")
                sys.exit(1)
            want = render_tile(d, meta["h"], hs, vs, dbl=2 if vm < 2 else 1)
            n = int((want != px).sum())
            green += int((px == d["mark"]).sum())
            if n and bad == 0:
                ys, xs = np.nonzero(want != px)
                print(f"      first difference at ({int(xs[0])},{int(ys[0])}) "
                      f"with HSCROLL {hs}, VSCROLL {vs}, VMODE {vm:02b}")
            bad += n; checked += 1; seen.add(key)
        print(f"      {len(got)} frames, {checked} judged, "
              f"{len(seen)} of {len(want_pos)} scrolls seen")
        miss = [want_pos[p] for p in want_pos if p not in seen]
        if miss:
            print(f"FAIL  {len(miss)} scrolls never reached a frame: {miss[:4]}")
            sys.exit(1)
        if green:
            print(f"FAIL  ⭐ {green} pixels came from a sub-palette other than 0 - "
                  "the attribute path leaked into tile mode")
        print(("FAIL  " if (bad or green) else "ok    ") +
              "⭐ tile mode: one-byte map, 8bpp tiles, both scroll axes with their "
              "ring wraps, six-bit cell row, all four VMODEs, ATTR zero "
              f"({bad} pixels differ)")
        sys.exit(1 if (bad or green) else 0)
    if "pos" in d:
        # ⭐ every frame carries the position the ROM had set, so one run covers
        # every X phase.  A frame is judged against ITS OWN position.
        vram, seen, bad, checked = background(0), set(), 0, 0
        want_pos = {(x, y | (v << 12)): (x, y, v) for x, y, v in d["pos"]}
        for meta, px in got:
            key = (meta["camk"], meta["herok"])
            if key not in want_pos:
                continue                     # the build-up frames
            sx, sy, v = want_pos[key]
            dbl = 2 if v < 2 else 1
            if meta["vmode"] != v:
                print(f"FAIL  the frame reports VMODE {meta['vmode']:02b}, want {v:02b}")
                sys.exit(1)
            want = render_sprite(d, meta["h"], sx, sy, vram, dbl=dbl)
            n = int((want != px).sum())
            if n and bad == 0:
                ys, xs = np.nonzero(want != px)
                print(f"      first difference at ({int(xs[0])},{int(ys[0])}) "
                      f"with the sprite at ({sx},{sy})")
            bad += n; checked += 1; seen.add(key)
        print(f"      {len(got)} frames, {checked} judged, "
              f"{len(seen)} of {len(want_pos)} positions seen")
        miss = [p for p in want_pos if p not in seen]
        if miss:
            print(f"FAIL  {len(miss)} positions never reached a frame: {miss[:4]}")
            sys.exit(1)
        print(("FAIL  " if bad else "ok    ") +
              "⭐ the sprite: every X phase, both 4-byte phases, the edges, the "
              "line-doubling boundary and all four VMODEs - every pixel is the "
              f"plan's ({bad} differ)")
        sys.exit(1 if bad else 0)
    if "copies" in d:
        want = render_bitmap(copy_result(d), meta["h"])
    else:
        want = np.array(render(d, meta["h"]), dtype="<u2")
    bad = int((want != last).sum())
    print(f"      {len(got)} frames, {meta['h']} lines, progress ${meta['prog']:02X}")
    if bad:
        ys, xs = np.nonzero(want != last)
        y, x = int(ys[0]), int(xs[0])
        print(f"      first difference at ({x},{y}) - cell ({x >> 3},{y // 2 >> 3}): "
              f"want ${int(want[y][x]):04X}, got ${int(last[y][x]):04X}")
    what = (f"⭐ the copy engine: {len(d['copies'])} copies - aligned and unaligned, "
            "and two overlapping ones STAGED THROUGH SCRATCH in two ascending "
            "passes, which is the only way the card can do them - every pixel is "
            "the plan's" if "copies" in d else
            "⭐ character mode: every pixel is the plan's - the attribute reaches "
            "the LUT's high eight address lines")
    print(("FAIL  " if bad else "ok    ") + what + f" ({bad} pixels differ)")
    sys.exit(1 if bad else 0)
