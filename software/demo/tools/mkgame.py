#!/usr/bin/env python3
"""Build the game half of the demo: tiles, a world, a hero and a script.

    python3 software/demo/tools/mkgame.py BUILD

Writes, all consumed by demo.asm through mkdemorom.py's layout:

  tiles.bin    256 x 64 bytes. Tile n's pixel (r, c) is byte n*64 + r*8 + c -
               graphics.md 6.4.1's concatenation, so the file IS the VRAM image.
               Codes SPRA..SPRA+29 are left for the hero's two tile buffers.
  world.bin    WORLD_H rows x 256 bytes of cell codes, row stride 256 so a cell
               is (y << 8) | x and the 6809 needs no multiply to find one.
  sprites.bin  8 frames x 32 x 16 bytes; KEY is transparent.
  frames.bin   one 8-byte record per 70 Hz frame, big-endian:
                 CAMX  CAMY  (frame << 12 | LINKX)  LINKY
               in VRAM pixels and rows of the world.
  game.inc     the constants the assembler shares with this file.
  model.npz    the same data for software/demo/tools/checkvideo.py

THE LOOK. The card's cell mode is 80 x 25 cells of 8 x 8 bytes in VMODE 00,
which the connector shows as 640 x 400: every VRAM pixel is one dot wide and two
lines tall. So art is drawn at 16 x 16 "art pixels", each 2 bytes wide and one
row tall - square on the screen - and a 16 x 16 metatile is 4 x 2 cells.
Original art in the style of an 8-bit overworld; nothing here is copied.
"""
import os, sys
import numpy as np

KEY = 0xE3                       # transparent sprite byte (magenta, unused in art)
SPRA = 226                       # first of 30 tile codes reserved for the hero
SCREEN_W, SCREEN_H = 80, 24      # a world screen, in cells (the view is 80 x 25)
SW, SH = 3, 3                    # screens across and down
WORLD_W = SCREEN_W * SW          # 240
WORLD_H = SCREEN_H * SH + 4      # 76: the bottom screen's view reaches row 73


def c332(r, g, b):
    q = lambda v, n: min(n, max(0, int(round(v / 255 * n))))
    return (q(r, 7) << 5) | (q(g, 7) << 2) | q(b, 3)


PAL = {
    '.': c332(252, 216, 168),    # sand
    ',': c332(220, 176, 120),    # sand speck
    'G': c332(0, 168, 0),        # leaf
    'g': c332(0, 96, 0),         # leaf shadow
    'l': c332(128, 208, 16),     # leaf light
    'B': c332(140, 80, 20),      # bark
    'k': c332(0, 0, 0),          # outline
    'R': c332(200, 76, 12),      # rock
    'r': c332(136, 40, 0),       # rock shadow
    'o': c332(252, 152, 56),     # rock light
    'W': c332(32, 56, 236),      # water
    'w': c332(92, 148, 252),     # wave
    'd': c332(0, 24, 140),       # deep
    'F': c332(252, 60, 60),      # flower
    'y': c332(252, 224, 0),      # flower centre / skin light
    'n': c332(0, 0, 0),          # cave
    's': c332(252, 188, 116),    # skin
    'T': c332(40, 184, 40),      # tunic
    't': c332(0, 112, 0),        # tunic shadow
    'h': c332(160, 96, 16),      # hair / belt
    'S': c332(172, 172, 172),    # shield
    'x': KEY,
}
for k, v in PAL.items():
    assert k == 'x' or v != KEY, k

META = {
    'sand': """
................
..,.............
..........,.....
................
.....,..........
................
.............,..
................
..,.............
................
........,.......
................
................
.,..........,...
................
......,.........""",
    'tree': """
....kgggggggk...
..kgGGlGGGGGgk..
.kgGlGGGGgGGGGk.
.gGGGGgGGGGlGGg.
kgGlGGGGGGGGGGgk
kGGGGGGGlGGGgGGk
kgGGgGGGGGGGGGgk
kGGGGGGgGGlGGGGk
kgGlGGGGGGGGgGgk
kgGGGGgGGGGGGGgk
.kgGGGGGGlGGGgk.
..kggGGGGGGggk..
...kkggggggkk...
......kBBk......
.....kBBBBk.,...
....kkkkkkkk....""",
    'rock': """
kRRRoRRRRRRoRRRk
RoRRRRrRRRRRRRor
RRRRRRrRRoRRRRRr
RRRoRRRrRRRRRRRr
rRRRRRRrrRRRRoRr
RRRRRRRRRrRRRRRr
RoRRRRRRRRrRRRRr
RRRRrRRRRRRrRRRr
RRRRRrRRRRRRRRRr
RRoRRRrrRRRRoRRr
RRRRRRRrRRRRRRRr
rRRRRRRRrRRRRRRr
RRRRoRRRRrRRRRRr
RRRRRRRRRRrrRRRr
RRRRRRRRRRRRrRRr
rrrrrrrrrrrrrrrr""",
    'water': """
WWWWWWWWWWWWWWWW
WWWwwWWWWWWWWWWW
WWwWWwWWWWWWwwWW
WWWWWWWWWWWwWWwW
WWWWWWWWWWWWWWWW
WWWWWWdWWWWWWWWW
WWWWWWWWWWWWWWWW
WwwWWWWWWWWWWWWW
wWWwWWWWWWwwWWWW
WWWWWWWWWwWWwWWW
WWWWWWWWWWWWWWWW
WWWWWWWWWWWWWdWW
WWWWWWWWWWWWWWWW
WWWWwwWWWWWWWWWW
WWWwWWwWWWWWWWWW
WWWWWWWWWWWWWWWW""",
    'flower': """
................
...F............
..FyF.......,...
...F............
................
.........F......
........FyF.....
.........F......
..,.............
................
....F.......F...
...FyF.....FyF..
....F.......F...
................
.........,......
................""",
    'cave': """
kRRRoRRRRRRoRRRk
RoRRRkkkkkkRRRor
RRRRkknnnnkkRRRr
RRRknnnnnnnnkRRr
rRRknnnnnnnnkRRr
RRknnnnnnnnnnkRr
RoknnnnnnnnnnkRr
RRknnnnnnnnnnkRr
RRknnnnnnnnnnkRr
RRknnnnnnnnnnkRr
RRknnnnnnnnnnkRr
rRknnnnnnnnnnkRr
RRknnnnnnnnnnkRr
RRknnnnnnnnnnkRr
RRknnnnnnnnnnkRr
rrknnnnnnnnnnkrr""",
    'shore': """
................
.......,........
................
..........,.....
,...............
................
wwwwwwwwwwwwwwww
WWWWWWWWWWWWWWWW
WWWwwWWWWWWWWWWW
WWwWWwWWWWWWwwWW
WWWWWWWWWWWwWWwW
WWWWWWWWWWWWWWWW
WWWWWWdWWWWWWWWW
WWWWWWWWWWWWWWWW
WwwWWWWWWWWWWWWW
WWWWWWWWWWWWWWWW""",
}

# The hero, facing right, two walk frames, and down / up. 16 x 16 art pixels.
HERO = {
    'right0': """
xxxxxkkkkkxxxxxx
xxxxkTTTTTkkxxxx
xxxkTTTTTTTTkxxx
xxxkhhTTsskkxxxx
xxkhhssskskxxxxx
xxkhsssssssxxxxx
xxxkssssskxxxxxx
xxkkTTTTTkxxxxxx
xkSSkTTTTTkxxxxx
kSSSkTsTTTskxxxx
kSSSkTTTTTkxxxxx
kSSSkhhhhhkxxxxx
xkSkTTTTTTkxxxxx
xxkTTkkkTTkxxxxx
xxkhhkxxkhhkxxxx
xxkkkxxxxkkkxxxx""",
    'right1': """
xxxxxkkkkkxxxxxx
xxxxkTTTTTkkxxxx
xxxkTTTTTTTTkxxx
xxxkhhTTsskkxxxx
xxkhhssskskxxxxx
xxkhsssssssxxxxx
xxxkssssskxxxxxx
xxkkTTTTTkxxxxxx
xkSSkTTTTTkxxxxx
kSSSkTsTTTskxxxx
kSSSkTTTTTkxxxxx
kSSSkhhhhhkxxxxx
xkSkTTTTTTkxxxxx
xxxkTTkTTkxxxxxx
xxxkhhkhhkxxxxxx
xxxxkkkkkxxxxxxx""",
    'down0': """
xxxxxkkkkkkxxxxx
xxxxkTTTTTTkxxxx
xxxkTTTTTTTTkxxx
xxxkhTTTTTThkxxx
xxkhhsssssshhkxx
xxkhskssssksshkx
xxxksssssssskxxx
xxxxkssyyssskxxx
xxxkkTTTTTTkkxxx
xxkSSkTTTTTsskxx
xkSSSkTTTTTsskxx
xkSSSkhhhhhhkxxx
xxkSkTTTTTTTkxxx
xxxkTTkkkkTTkxxx
xxxkhhkxxxkhhkxx
xxxkkkxxxxxkkkxx""",
    'down1': """
xxxxxkkkkkkxxxxx
xxxxkTTTTTTkxxxx
xxxkTTTTTTTTkxxx
xxxkhTTTTTThkxxx
xxkhhsssssshhkxx
xxkhskssssksshkx
xxxksssssssskxxx
xxxxkssyyssskxxx
xxxkkTTTTTTkkxxx
xxkSSkTTTTTsskxx
xkSSSkTTTTTsskxx
xkSSSkhhhhhhkxxx
xxkSkTTTTTTTkxxx
xxkTTkkkkTTkxxxx
xkhhkxxxkhhkxxxx
xkkkxxxxxkkkxxxx""",
    'up0': """
xxxxxkkkkkkxxxxx
xxxxkTTTTTTkxxxx
xxxkTTTTTTTTkxxx
xxxkTTTTTTTTkxxx
xxkhhhhhhhhhhkxx
xxkhhhhhhhhhhkxx
xxxkhhhhhhhhkxxx
xxxxkhhhhhhkxxxx
xxxkkTTTTTTkkxxx
xxkssTTTTTTkSkxx
xxkssTTTTTkSSSkx
xxxkhhhhhhkSSSkx
xxxkTTTTTTTkSkxx
xxxkTTkkkkTTkxxx
xxkhhkxxxxkhhkxx
xxkkkxxxxxxkkkxx""",
    'up1': """
xxxxxkkkkkkxxxxx
xxxxkTTTTTTkxxxx
xxxkTTTTTTTTkxxx
xxxkTTTTTTTTkxxx
xxkhhhhhhhhhhkxx
xxkhhhhhhhhhhkxx
xxxkhhhhhhhhkxxx
xxxxkhhhhhhkxxxx
xxxkkTTTTTTkkxxx
xxkssTTTTTTkSkxx
xxkssTTTTTkSSSkx
xxxkhhhhhhkSSSkx
xxxkTTTTTTTkSkxx
xxxxkTTkkTTkxxxx
xxxxkhhkkhhkxxxx
xxxxkkkxxkkkxxxx""",
}
FRAME_NAMES = ['right0', 'right1', 'left0', 'left1', 'down0', 'down1', 'up0', 'up1']
DIR_FRAME = {'right': 0, 'left': 2, 'down': 4, 'up': 6}


def art(text):
    rows = [r for r in text.strip("\n").split("\n")]
    assert len(rows) == 16 and all(len(r) == 16 for r in rows), text
    a = np.array([[PAL[ch] for ch in r] for r in rows], dtype=np.uint8)
    return np.repeat(a, 2, axis=1)            # 32 x 16 bytes: art pixels are 2 wide


def hero_frames():
    out = []
    for name in FRAME_NAMES:
        if name.startswith('left'):
            a = art(HERO['right' + name[-1]])[:, ::-1]
        else:
            a = art(HERO[name])
        out.append(a)
    return np.array(out)                       # 8 x 16 x 32


# ------------------------------------------------------------------ world ----
def design_world():
    """Metatile grid, 60 x 38 (each 4 x 2 cells). Nine screens of 20 x 12."""
    MW, MH = WORLD_W // 4, WORLD_H // 2
    g = [['sand'] * MW for _ in range(MH)]
    rnd = np.random.default_rng(1986)

    def border(sx, sy, open_sides):
        x0, y0 = sx * 20, sy * 12
        for x in range(20):
            for y in (0, 11):
                side = 'n' if y == 0 else 's'
                if side in open_sides and 8 <= x <= 11:
                    continue
                g[y0 + y][x0 + x] = 'tree' if (sx + sy) % 2 == 0 else 'rock'
        for y in range(12):
            for x in (0, 19):
                side = 'w' if x == 0 else 'e'
                if side in open_sides and 4 <= y <= 7:
                    continue
                g[y0 + y][x0 + x] = 'tree' if (sx + sy) % 2 == 0 else 'rock'

    for sy in range(SH):
        for sx in range(SW):
            opens = set()
            if sx > 0: opens.add('w')
            if sx < SW - 1: opens.add('e')
            if sy > 0: opens.add('n')
            if sy < SH - 1: opens.add('s')
            border(sx, sy, opens)
            x0, y0 = sx * 20, sy * 12
            # scattered trees and flowers, kept clear of the hero's paths
            for _ in range(10):
                x, y = rnd.integers(2, 18), rnd.integers(2, 10)
                if 4 <= y <= 7 or 8 <= x <= 11:
                    continue
                g[y0 + y][x0 + x] = 'tree' if rnd.random() < 0.6 else 'flower'
    # a lake with a shore on screen (1, 0), a cave in the mountains on (0, 1)
    for y in range(2, 4):
        for x in range(24, 36):
            g[y][x] = 'shore' if y == 2 else 'water'
    for x in range(26, 34):
        g[4][x] = 'water'
    g[13][4] = 'cave'
    for x in range(2, 8):
        g[12 + 1][x] = 'rock' if x != 4 else 'cave'
    # the bottom margin rows under the last screen
    for y in range(SH * 12, MH):
        for x in range(MW):
            g[y][x] = 'rock'
    return g


def build(outdir):
    os.makedirs(outdir, exist_ok=True)
    tiles = {}                                 # bytes -> code
    tilelist = []

    def code_of(block):
        key = block.tobytes()
        if key not in tiles:
            tiles[key] = len(tilelist)
            tilelist.append(block)
        return tiles[key]

    meta_cells = {}
    for name, text in META.items():
        a = art(text)                           # 16 rows x 32 bytes
        cells = [[code_of(a[r * 8:(r + 1) * 8, c * 8:(c + 1) * 8]) for c in range(4)] for r in range(2)]
        meta_cells[name] = cells
    # NitrOS-9's overworld keeps a third hero buffer at SPRA-15 (demo.asm uses two)
    if len(tilelist) > SPRA - 15:
        sys.exit(f"FAIL  {len(tilelist)} distinct tiles; codes {SPRA - 15}+ are the hero's")

    tileset = np.zeros((256, 64), dtype=np.uint8)
    for n, t in enumerate(tilelist):
        tileset[n] = t.reshape(64)

    g = design_world()
    world = np.zeros((WORLD_H, 256), dtype=np.uint8)
    for my, row in enumerate(g):
        for mx, name in enumerate(row):
            cells = meta_cells[name]
            for r in range(2):
                for c in range(4):
                    world[my * 2 + r, mx * 4 + c] = cells[r][c]

    sprites = hero_frames()

    # ---- the script: walk, carry, walk -------------------------------------
    frames = []
    cam = [0, 0]
    link = [320 - 16, 96]                        # world VRAM px/rows
    face = 'down'
    step = 0

    def emit():
        nonlocal step
        fr = DIR_FRAME[face] + ((step // 8) & 1)
        frames.append((cam[0], cam[1], fr, link[0], link[1]))
        step += 1

    def walk(dx, dy, n):
        nonlocal face
        face = 'right' if dx > 0 else 'left' if dx < 0 else 'down' if dy > 0 else 'up'
        for _ in range(n):
            link[0] += dx; link[1] += dy
            emit()

    def ramp(dist, vmax=16):
        """Per-frame steps that sum to `dist`, accelerating 1 -> vmax and back.

        ⭐ A transition used to be a constant 4 px a frame for 160 frames. It now
        ramps 1, 2, 3 ... up to 16 px a frame, cruises, and eases back to 1, so
        the scroll starts and stops rather than switching on and off. The card
        does not care - HSCROLL is a register - but the eye does, and 16 px a
        frame at 70 Hz is 1,120 px/s, which is what the hardware scroll is for.

        vmax falls back if the ramp alone would overshoot: a 200-pixel vertical
        transition cannot reach 16 and settle, so it peaks lower."""
        v = vmax
        while v > 1 and (v * (v + 1)) // 2 + ((v - 1) * v) // 2 > dist:
            v -= 1
        up = list(range(1, v + 1))
        down = list(range(v - 1, 0, -1))
        rem = dist - sum(up) - sum(down)
        cruise = [v] * (rem // v) + ([rem % v] if rem % v else [])
        steps = up + cruise + down
        assert sum(steps) == dist, (dist, sum(steps))
        return steps

    def carry(sx, sy, dist):
        """A screen transition: the camera moves `dist` pixels in direction
        (sx, sy) on an accelerating ramp, and the hero is carried from where he
        stands to the opposite edge of the new screen, MARGIN inside it, in a
        straight line on the screen. He never leaves the view - and must not,
        because cells above or below it alias into the 32-row map ring's
        visible rows (graphics.md 6.4.6)."""
        MARGIN = 8
        wx0, wy0 = link[0], link[1]
        steps = ramp(dist)
        ex, ey = cam[0] + sx * dist, cam[1] + sy * dist
        tx = ex + (MARGIN if sx > 0 else 640 - 32 - MARGIN if sx < 0 else wx0 - cam[0])
        ty = ey + (MARGIN if sy > 0 else 200 - 16 - MARGIN if sy < 0 else wy0 - cam[1])
        gone = 0
        for st in steps:
            gone += st
            cam[0] += sx * st; cam[1] += sy * st
            link[0] = wx0 + round((tx - wx0) * gone / dist)
            link[1] = wy0 + round((ty - wy0) * gone / dist)
            emit()

    def stand(n):
        for _ in range(n):
            frames.append((cam[0], cam[1], DIR_FRAME[face], link[0], link[1]))

    def walk_to(x, y):
        """Walk on the screen, a column then a row, to screen position (x, y)."""
        while link[0] - cam[0] != x:
            walk(2 if x > link[0] - cam[0] else -2, 0, 1)
        while link[1] - cam[1] != y:
            walk(0, 1 if y > link[1] - cam[1] else -1, 1)

    stand(35)
    walk_to(304, 56)                             # up to the path
    walk_to(600, 56)                             # east, to the edge of screen (0,0)
    carry(1, 0, 640)                             # east -> screen (1,0), on the ramp
    walk_to(8, 140)                              # south, in the gap
    walk_to(304, 140)
    walk_to(304, 176)                            # to the bottom edge
    carry(0, 1, 192)                             # south -> screen (1,1)
    walk_to(304, 56)
    walk_to(8, 56)                               # west
    carry(-1, 0, 640)                            # west -> screen (0,1)
    walk_to(304, 40)
    walk_to(304, 8)                              # to the top edge
    carry(0, -1, 192)                            # north -> screen (0,0)
    walk_to(304, 96)
    stand(35)
    frames_arr = np.array(frames, dtype=np.int32)
    assert frames_arr[:, 3].min() >= 0 and frames_arr[:, 3].max() < 4096 - 32
    sx, sy = frames_arr[:, 3] - frames_arr[:, 0], frames_arr[:, 4] - frames_arr[:, 1]
    if sx.min() < 0 or sx.max() > 640 - 32 or sy.min() < 0 or sy.max() > 200 - 16:
        sys.exit(f"FAIL  the hero leaves the view: screen x {sx.min()}..{sx.max()}, y {sy.min()}..{sy.max()}")
    first, last = frames[0], frames[-1]
    if first[0:2] != last[0:2]:
        sys.exit(f"FAIL  the script does not close: the camera starts at {first[0:2]} and ends at {last[0:2]}")
    rec = bytearray()
    for cx, cy, fr, lx, ly in frames:
        rec += bytes([cx >> 8, cx & 0xFF, cy >> 8, cy & 0xFF,
                      (fr << 4) | (lx >> 8), lx & 0xFF, ly >> 8, ly & 0xFF])

    open(os.path.join(outdir, "tiles.bin"), "wb").write(tileset.tobytes())
    open(os.path.join(outdir, "world.bin"), "wb").write(world.tobytes())
    open(os.path.join(outdir, "sprites.bin"), "wb").write(sprites.tobytes())
    open(os.path.join(outdir, "frames.bin"), "wb").write(bytes(rec))
    inc = [
        "* GENERATED by software/demo/tools/mkgame.py - do not edit",
        f"SPRKEY  EQU     ${KEY:02X}           transparent sprite byte",
        f"SPRA    EQU     {SPRA}             first of the hero's 30 tile codes",
        f"WORLDW  EQU     {WORLD_W}",
        f"WORLDH  EQU     {WORLD_H}",
        f"NFRAMES EQU     {len(frames)}           records in frames.bin",
    ]
    open(os.path.join(outdir, "game.inc"), "w").write("\n".join(inc) + "\n")
    np.savez(os.path.join(outdir, "model.npz"), tiles=tileset, world=world,
             sprites=sprites, frames=frames_arr, key=KEY, spra=SPRA)
    print(f"ok    {len(tilelist)} tiles, world {WORLD_W}x{WORLD_H} cells, "
          f"{len(frames)} frames ({len(frames) / 70.09:.1f} s at 70 Hz)")


def preview(outdir, k=None):
    """Render what frame k should look like at the connector (640 x 400)."""
    from PIL import Image
    m = np.load(os.path.join(outdir, "model.npz"))
    img = render(m, k if k is not None else 0)
    sys.path.insert(0, os.path.dirname(__file__))
    from mkparrots import expand332
    Image.fromarray(expand332(np.repeat(img, 2, axis=0))).save(os.path.join(outdir, f"game{k or 0}.png"))


def render(m, k, link_k=None):
    """The model: world + hero at record k, as 200 x 640 VRAM indices."""
    tiles, world, sprites, frames, key = m["tiles"], m["world"], m["sprites"], m["frames"], int(m["key"])
    cx, cy = int(frames[k][0]), int(frames[k][1])
    lk = k if link_k is None else link_k
    fr, lx, ly = int(frames[lk][2]), int(frames[lk][3]), int(frames[lk][4])
    big = np.zeros((208, 656), dtype=np.uint8)
    c0, r0 = cx // 8, cy // 8
    for r in range(26):
        for c in range(82):
            code = world[r0 + r, c0 + c] if (r0 + r) < world.shape[0] and (c0 + c) < 256 else 0
            big[r * 8:(r + 1) * 8, c * 8:(c + 1) * 8] = tiles[code].reshape(8, 8)
    view = big[cy % 8:cy % 8 + 200, cx % 8:cx % 8 + 640].copy()
    sx, sy = lx - cx, ly - cy
    spr = sprites[fr]
    for y in range(16):
        for x in range(32):
            if spr[y, x] != key and 0 <= sy + y < 200 and 0 <= sx + x < 640:
                view[sy + y, sx + x] = spr[y, x]
    return view


def render_cells(m, k, link_k=None, stale_half=False):
    """The same picture built the way the card builds it - from map codes and
    tiles - so a defect in how the card picks a cell's code can be modelled.

    The hero is fifteen composited tiles in the 5 x 3 cells he touches, as
    demo.asm's compose1 builds them. With stale_half, every pixel in the first
    half of a cell (column-within-cell 0..3) is drawn from the PREVIOUS cell's
    code - graphics.md 6.4.9's MAP -> MAPQ handover landing on the slot
    counter's cell boundary rather than the scrolled one, as demo_tb measured
    at HSCROLL[2:0] = 4."""
    tiles, world, sprites, frames, key = m["tiles"], m["world"], m["sprites"], m["frames"], int(m["key"])
    cx, cy = int(frames[k][0]), int(frames[k][1])
    c0, r0 = cx // 8, cy // 8
    R, C = 26, 82
    codes = np.zeros((R, C + 1), dtype=np.int32)          # column 0 is cell c0-1
    for r in range(R):
        for c in range(-1, C):
            wr_, wc = r0 + r, c0 + c
            codes[r, c + 1] = world[wr_, wc] if 0 <= wr_ < world.shape[0] and 0 <= wc < 256 else 0
    tl = [t.reshape(8, 8) for t in tiles]
    if link_k is not None:
        fr_, lx, ly = int(frames[link_k][2]), int(frames[link_k][3]), int(frames[link_k][4])
        hc, hr = lx // 8, ly // 8
        spr = sprites[fr_]
        for j in range(3):
            for i in range(5):
                wc, wr_ = hc + i, hr + j
                t = tl[world[wr_, wc]].copy()
                for pr in range(8):
                    sy = j * 8 + pr - (ly & 7)
                    if not 0 <= sy < 16:
                        continue
                    for pc in range(8):
                        sx = i * 8 + pc - (lx & 7)
                        if 0 <= sx < 32 and spr[sy, sx] != key:
                            t[pr, pc] = spr[sy, sx]
                tl.append(t)
                rr, cc = wr_ - r0, wc - c0 + 1
                if 0 <= rr < R and 0 <= cc < C + 1:
                    codes[rr, cc] = len(tl) - 1
    big = np.zeros((R * 8, C * 8), dtype=np.uint8)
    prev = np.zeros_like(big)
    for r in range(R):
        for c in range(C):
            big[r * 8:r * 8 + 8, c * 8:c * 8 + 8] = tl[codes[r, c + 1]]
            prev[r * 8:r * 8 + 8, c * 8:c * 8 + 8] = tl[codes[r, c]]
    if stale_half:
        colmask = (np.arange(C * 8) % 8) < 4
        big = np.where(colmask[None, :], prev, big)
    return big[cy % 8:cy % 8 + 200, cx % 8:cx % 8 + 640]


if __name__ == "__main__":
    build(sys.argv[1])
    if len(sys.argv) > 2:
        for k in sys.argv[2:]:
            preview(sys.argv[1], int(k))
