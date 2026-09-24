#!/usr/bin/env python3
"""Render the demo's stand-in picture - three parrots on a branch - and reduce
it to the card's RGB332 palette.

    python3 software/tools/mkparrots.py out.raw [preview.png] [--src photo.jpg]

A STAND-IN. The demo is meant to show a photograph; the sandbox this was written
in could not download one, so this draws an illustration instead, from
primitives, at 4x and box-filtered down. `--src` takes any image instead and
does exactly the same reduction, which is the part the machine cares about.

THE OUTPUT IS 640 x 480 BYTES, ONE PALETTE INDEX PER PIXEL, and the index IS
the colour: RRRGGGBB. demo.asm loads the palette entry i = RGB332(i) expanded to
the card's RGB565, so nothing in between holds a lookup table and a byte that
reaches the connector names its own colour. Floyd-Steinberg dithering spreads
the error, because 3-3-2 bits of a sky gradient band visibly without it.
"""
import math, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W, H, SS = 640, 480, 4


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def rot(points, cx, cy, ang):
    c, s = math.cos(ang), math.sin(ang)
    return [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c) for x, y in points]


def ellipse_poly(cx, cy, rx, ry, ang=0.0, n=64):
    pts = [(cx + rx * math.cos(2 * math.pi * k / n), cy + ry * math.sin(2 * math.pi * k / n)) for k in range(n)]
    return rot(pts, cx, cy, ang)


def background(img):
    d = ImageDraw.Draw(img)
    top, bot = (18, 60, 40), (120, 170, 90)
    for y in range(H * SS):
        d.line([(0, y), (W * SS, y)], fill=lerp(top, bot, y / (H * SS)))
    rnd = np.random.default_rng(7)
    # soft jungle leaves, blurred into depth
    leaves = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(leaves)
    for _ in range(90):
        x, y = rnd.uniform(0, W * SS), rnd.uniform(0, H * SS)
        r = rnd.uniform(60, 220)
        g = int(rnd.uniform(70, 150))
        col = (int(g * 0.35), g, int(g * 0.45), int(rnd.uniform(90, 200)))
        ld.polygon(ellipse_poly(x, y, r, r * 0.38, rnd.uniform(0, math.pi)), fill=col)
    leaves = leaves.filter(ImageFilter.GaussianBlur(18))
    img.alpha_composite(leaves)
    # a sun glow upper right
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([W * SS * 0.62, -H * SS * 0.25, W * SS * 1.15, H * SS * 0.35],
                                 fill=(255, 240, 170, 120))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(80)))


def branch(img):
    d = ImageDraw.Draw(img)
    y0, y1 = 372 * SS, 352 * SS
    pts_top = [(x, y0 + (y1 - y0) * x / (W * SS) + 10 * SS * math.sin(x / (70 * SS))) for x in range(-40, W * SS + 40, 8)]
    pts_bot = [(x, y + 30 * SS - 6 * SS * x / (W * SS)) for x, y in reversed(pts_top)]
    d.polygon(pts_top + pts_bot, fill=(92, 58, 34))
    for k in range(0, len(pts_top), 6):
        x, y = pts_top[k]
        d.line([(x, y + 8 * SS), (x + 60 * SS, y + 12 * SS)], fill=(70, 42, 24), width=3 * SS)
    d.line(pts_top, fill=(140, 98, 60), width=4 * SS)
    return pts_top


def parrot(img, cx, cy, s, body, belly, wing, wingtip, head, face, tail, flip=False, ang=0.0):
    """One parrot perched with its feet at (cx, cy), scale s ~ 1 = 200 px tall."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f = -1 if flip else 1
    S = s * SS

    def P(x, y):
        return (cx * SS + f * x * S, cy * SS + y * S)

    def poly(points, fill):
        d.polygon(rot([P(x, y) for x, y in points], cx * SS, cy * SS, ang * f), fill=fill)

    def ell(x, y, rx, ry, a, fill):
        px, py = P(x, y)
        pts = ellipse_poly(px, py, rx * S, ry * S, f * a)
        d.polygon(rot(pts, cx * SS, cy * SS, ang * f), fill=fill)

    # tail: long tapered bands, drawn first so the body sits on it
    poly([(-8, -40), (8, -40), (-10, 150), (-30, 150)], tail[0])
    poly([(-2, -40), (8, -40), (-14, 150), (-22, 152)], tail[1])
    poly([(-10, 60), (-2, 60), (-18, 150), (-28, 150)], tail[2])
    # body
    ell(0, -70, 34, 62, 0.25, body)
    ell(8, -58, 20, 44, 0.25, belly)
    # wing, with feather stripes toward the tip
    ell(-14, -64, 24, 58, 0.32, wing)
    for k in range(4):
        ell(-22 - k * 3, -30 + k * 14, 16 - k * 2, 16, 0.4, wingtip if k % 2 == 0 else wing)
    # head
    ell(8, -142, 30, 30, 0.0, head)
    ell(18, -142, 16, 18, 0.0, face)
    # beak: an upper hook and a lower mandible
    poly([(26, -156), (54, -148), (58, -130), (48, -118), (36, -130), (26, -132)], (40, 36, 34))
    poly([(26, -150), (46, -146), (50, -134), (40, -126), (30, -136)], (232, 226, 210))
    poly([(28, -130), (44, -124), (36, -114), (26, -120)], (30, 28, 28))
    # eye
    ell(16, -148, 7, 7, 0, (250, 250, 240))
    ell(18, -148, 3.5, 3.5, 0, (10, 10, 10))
    ell(19, -149.5, 1.2, 1.2, 0, (255, 255, 255))
    # feet gripping the branch
    for dx in (-8, 10):
        poly([(dx - 6, -8), (dx + 6, -8), (dx + 10, 6), (dx - 10, 6)], (70, 70, 74))
    # soft shadow, then the bird
    shadow = layer.split()[3].filter(ImageFilter.GaussianBlur(10 * SS))
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sh.putalpha(shadow.point(lambda a: a * 0.45))
    img.alpha_composite(sh, (6 * SS, 8 * SS))
    img.alpha_composite(layer)


def illustration():
    img = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 255))
    background(img)
    top = branch(img)

    def perch(x):
        k = min(range(len(top)), key=lambda i: abs(top[i][0] - x * SS))
        return top[k][1] / SS + 4

    # scarlet macaw
    parrot(img, 150, perch(150), 1.05,
           body=(214, 30, 36), belly=(232, 60, 44), wing=(30, 90, 200), wingtip=(250, 205, 40),
           head=(220, 34, 38), face=(245, 240, 232), tail=((200, 30, 30), (40, 90, 210), (250, 200, 40)))
    # blue-and-gold macaw, facing the other way
    parrot(img, 470, perch(470), 1.1,
           body=(34, 110, 220), belly=(250, 196, 30), wing=(26, 84, 190), wingtip=(20, 60, 140),
           head=(40, 150, 90), face=(245, 245, 240), tail=((30, 90, 200), (20, 70, 170), (250, 190, 30)),
           flip=True)
    # green-winged parrot in the middle, slightly smaller and forward
    parrot(img, 318, perch(318), 0.92,
           body=(60, 180, 70), belly=(160, 220, 60), wing=(30, 130, 60), wingtip=(40, 90, 200),
           head=(240, 120, 30), face=(250, 220, 90), tail=((50, 160, 60), (230, 60, 40), (40, 100, 210)),
           ang=-0.08)
    return img.resize((W, H), Image.LANCZOS).convert("RGB")


def to_rgb332(img):
    """Floyd-Steinberg onto the 3-3-2 lattice. Returns (indices, preview)."""
    a = np.asarray(img, dtype=np.float32).copy()
    levels = [7, 7, 3]
    idx = np.zeros((H, W), dtype=np.uint8)
    for y in range(H):
        for x in range(W):
            px = a[y, x]
            q = [min(levels[c], max(0, int(round(px[c] / 255 * levels[c])))) for c in range(3)]
            err = px - np.array([q[c] * 255 / levels[c] for c in range(3)], dtype=np.float32)
            idx[y, x] = (q[0] << 5) | (q[1] << 2) | q[2]
            if x + 1 < W:
                a[y, x + 1] += err * 7 / 16
            if y + 1 < H:
                if x > 0:
                    a[y + 1, x - 1] += err * 3 / 16
                a[y + 1, x] += err * 5 / 16
                if x + 1 < W:
                    a[y + 1, x + 1] += err * 1 / 16
    return idx


def expand332(idx):
    """The same expansion demo.asm's palette makes: RGB332 -> RGB565 -> 8 bits."""
    idx = idx.astype(np.int32)
    r3, g3, b2 = idx >> 5, (idx >> 2) & 7, idx & 3
    r5, g6, b5 = (r3 * 31 + 3) // 7, (g3 * 63 + 3) // 7, (b2 * 31 + 1) // 3
    return np.stack([(r5 << 3) | (r5 >> 2), (g6 << 2) | (g6 >> 4), (b5 << 3) | (b5 >> 2)], -1).astype(np.uint8)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    src = sys.argv[sys.argv.index("--src") + 1] if "--src" in sys.argv else None
    if src:
        args = [a for a in args if a != src]
        img = Image.open(src).convert("RGB")
        # cover 640x480, centre-cropped
        sc = max(W / img.width, H / img.height)
        img = img.resize((math.ceil(img.width * sc), math.ceil(img.height * sc)), Image.LANCZOS)
        l, t = (img.width - W) // 2, (img.height - H) // 2
        img = img.crop((l, t, l + W, t + H))
    else:
        img = illustration()
    idx = to_rgb332(img)
    open(args[0], "wb").write(idx.tobytes())
    if len(args) > 1:
        Image.fromarray(expand332(idx)).save(args[1])
    print(f"wrote {args[0]}: {idx.size} bytes, {len(np.unique(idx))} distinct indices")
