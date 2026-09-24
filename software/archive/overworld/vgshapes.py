"""The shapes CoArm draws, defined once, as sets of pixels.

vgmodel.py renders CoWin's graphics escapes with these; CoArm's ca_draw.asm
implements the same definitions in 6809 code - independently, from this
docstring - and run-vid.sh compares the two pictures pixel for pixel. So the
definitions are exact, integer, and stated here in the words the 6809 code
follows:

LINE (x0, y0)-(x1, y1), both ends included: Bresenham with
    dx = |x1 - x0|, sx = sign(x1 - x0), dy = -|y1 - y0|, sy = sign(y1 - y0),
    err = dx + dy; plot; stop at the end; e2 = 2 err;
    if e2 >= dy: err += dy, x += sx;  if e2 <= dx: err += dx, y += sy.

BOX (x0, y0)-(x1, y1): the outline of the normalised rectangle, every pixel
    once: the top and bottom rows whole, the sides between them.

BAR (x0, y0)-(x1, y1): the normalised rectangle, both corners included.

ELLIPSE centre (cx, cy), radii rx, ry (each clamped to 0-255): for a row
    dy in -ry..ry, its half-width is
        w(dy) = isqrt( floor(rx^2 (ry^2 - dy^2) / ry^2) + rx )
    (isqrt = floor square root; ry = 0 gives w(0) = rx). FILLED: each row's
    span [cx - w, cx + w]. OUTLINE: with wn = w(|dy| + 1), or -1 at |dy| = ry,
    and k = min(max(wn + 1, 0), w): k = 0 is the span [cx - w, cx + w]; else
    the two spans [cx - w, cx - k] and [cx + k, cx + w]. A CIRCLE is the
    ellipse with rx = ry = r.

ARC rx ry x1 y1 x2 y2: the ellipse outline's pixels (dx, dy), relative to the
    centre, for which (x2 - x1)(dy - y1) - (y2 - y1)(dx - x1) >= 0.

FFILL from (x, y): every pixel 4-connected to it through pixels of its colour,
    inside the clip, becomes the new colour; nothing if it already is that
    colour.
"""


def isqrt(n):
    if n <= 0:
        return 0
    x = int(n ** 0.5)
    while x * x > n:
        x -= 1
    while (x + 1) * (x + 1) <= n:
        x += 1
    return x


def line(x0, y0, x1, y1):
    dx, sx = abs(x1 - x0), (1 if x1 >= x0 else -1)
    dy, sy = -abs(y1 - y0), (1 if y1 >= y0 else -1)
    err = dx + dy
    out = []
    while True:
        out.append((x0, y0))
        if x0 == x1 and y0 == y1:
            return out
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def box(x0, y0, x1, y1):
    xa, xb = sorted((x0, x1))
    ya, yb = sorted((y0, y1))
    pts = [(x, ya) for x in range(xa, xb + 1)]
    if yb != ya:
        pts += [(x, yb) for x in range(xa, xb + 1)]
    for y in range(ya + 1, yb):
        pts.append((xa, y))
        if xb != xa:
            pts.append((xb, y))
    return pts


def bar_spans(x0, y0, x1, y1):
    xa, xb = sorted((x0, x1))
    ya, yb = sorted((y0, y1))
    return [(y, xa, xb) for y in range(ya, yb + 1)]


def half_width(rx, ry, dy):
    rx, ry = min(max(rx, 0), 255), min(max(ry, 0), 255)
    if ry == 0:
        return rx
    return isqrt((rx * rx * (ry * ry - dy * dy)) // (ry * ry) + rx)


def ellipse_spans(cx, cy, rx, ry, filled):
    """[(y, xa, xb)], xa <= xb, each pixel once."""
    rx, ry = min(max(rx, 0), 255), min(max(ry, 0), 255)
    out = []
    for dy in range(-ry, ry + 1):
        w = half_width(rx, ry, abs(dy))
        if filled:
            out.append((cy + dy, cx - w, cx + w))
            continue
        wn = half_width(rx, ry, abs(dy) + 1) if abs(dy) < ry else -1
        k = min(max(wn + 1, 0), w)
        if k == 0:
            out.append((cy + dy, cx - w, cx + w))
        else:
            out.append((cy + dy, cx - w, cx - k))
            out.append((cy + dy, cx + k, cx + w))
    return out


def arc_points(cx, cy, rx, ry, x1, y1, x2, y2):
    pts = []
    for y, xa, xb in ellipse_spans(cx, cy, rx, ry, False):
        for x in range(xa, xb + 1):
            dx, dy = x - cx, y - cy
            if (x2 - x1) * (dy - y1) - (y2 - y1) * (dx - x1) >= 0:
                pts.append((x, y))
    return pts


def ffill(pix, x, y, colour, clip):
    """pix: a 2-D array [y][x]; clip: (x0, y0, x1, y1) inclusive. In place."""
    x0, y0, x1, y1 = clip
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return
    target = int(pix[y][x])
    if target == colour:
        return
    stack = [(x, y)]
    while stack:
        px, py = stack.pop()
        if pix[py][px] != target:
            continue
        pix[py][px] = colour
        for nx, ny in ((px - 1, py), (px + 1, py), (px, py - 1), (px, py + 1)):
            if x0 <= nx <= x1 and y0 <= ny <= y1 and pix[ny][nx] == target:
                stack.append((nx, ny))
