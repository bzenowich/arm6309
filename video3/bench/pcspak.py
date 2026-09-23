#!/usr/bin/env python3
"""pcspak.py - the polygon scan converter, transliterated from PPAK.s.

⛔ WRITTEN FROM THE 6502, NEVER ADJUSTED TO MATCH THE 6809.  It is the gate:
`checkpcs.py` builds the same table this builds and requires the machine's
span database to match it byte for byte.  See pcsphys.py's header.

⭐ THE OUTPUT IS NOT A PICTURE.  A span record is four bytes --

    x_left | object index | x_right | (slope_right << 4) | slope_left

-- and `pbdx[y]` counts the bytes on scanline y.  That structure is at once
the picture, the z-order (object order, later on top), the mouse hit test
(SELECTPOLY walks it backwards) and the ball's collision world (CHECKHORIZ and
CHECKVERT read the slope nibbles as surface normals).  Getting it right is the
whole of step 2 of the port.

⚠ THE CARRY FLAG CARRIES THE VERTEX CLASSIFICATION.  PROCESSVERTEX takes the
previous call's carry as "the run is currently descending" and returns the
same for the next.  Written out:

    edge descends (y2 >= y1)   was ascending  -> START    (a local maximum)
                               was descending -> CHAIN
    edge ascends  (y2 <  y1)   was descending -> TERMINAL (a local minimum)
                               was ascending  -> CHAIN

and horizontal edges are skipped entirely before the test.  Budge's comments
name three of those four cases; this is the fourth made explicit.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pcsphys                                                 # noqa: E402

NEDGE = 8               # PPAK.s:568 - 8 active edge records, 4 spans a line
NVTX = 64               # the vertex ceiling
POLY, BPOLY, LIBOBJ = 1, 2, 3


class Abort(Exception):
    """⛔ The converter gave up: more than 8 active edges, or the span database
    is within 32 bytes of full.  Every editor operation checks for this and
    rolls the object back - which is why a table can never be left half drawn."""


class Obj(object):
    """One object record, as PKObj unpacks it."""

    def __init__(self, objid, fillcolor, xs, ys):
        assert len(xs) == len(ys)
        self.objid = objid
        self.fillcolor = fillcolor
        self.x = list(xs)
        self.y = list(ys)

    @property
    def n(self):
        return len(self.x)

    def align(self):
        """ALIGNPOLY (PPAK.s:927) - rotate the vertex list until edge 0 slopes
        DOWN, i.e. y[0] < y[1].  Returns False if every Y is equal.

        ⛔ THIS IS A PRECONDITION OF THE SCAN CONVERTER, not a tidy-up.  A
        polygon whose first edge is horizontal walks PROCESSPOLY past its own
        wrap point - Y is left after the skipped run, so it never equals
        WRAPPOINT again - and the sweep goes round the polygon until it runs
        out of edge records and aborts.  The editor calls this after every
        vertex move (DRAGPOINT, EDIT.s:780) so a stored table always satisfies
        it; a table built any other way must call it too.
        """
        for _ in range(self.n):
            if self.y[0] < self.y[1]:
                return True
            self.x.append(self.x.pop(0))
            self.y.append(self.y.pop(0))
        return False


class Pak(object):
    """The scan converter and the span database, for one table."""

    def __init__(self, height=240, width=160, spanbytes=8192):
        self.TH, self.TW = height, width
        self.spanbytes = spanbytes
        self.objs = []
        self.reset()

    # ------------------------------------------------------------------
    def reset(self):
        self.pbdx = [0] * self.TH
        self.rows = [[] for _ in range(self.TH)]   # the gap buffer, flattened
        self.aborted = False

    def display(self):
        """DRAWDISPLAY (PPAK.s:160) - rebuild the world."""
        self.reset()
        for i, _ in enumerate(self.objs):
            self.draw(i)
        return self

    def draw(self, index):
        """DRAWOBJ + SCANPOLY for one object."""
        o = self.objs[index]
        if o.objid > LIBOBJ:
            return
        self.cur = index
        self.o = o
        self.bpoly = (o.objid == BPOLY)
        self._scan()

    # ------------------------------------------------------------------
    def _scan(self):
        o = self.o
        self.anext = [0] * NEDGE
        self.anvrtx = [0] * NEDGE
        self.ayflg = [0] * NEDGE
        self.axcoeff = [0] * NEDGE
        self.axfract = [0] * NEDGE
        self.adxcoeff = [0] * NEDGE
        self.adxfract = [0] * NEDGE
        self.adxcode = [0] * NEDGE
        self.nvrtx = [0] * NVTX
        self.ndxcoeff = [0] * NVTX
        self.ndxfract = [0] * NVTX
        self.ndxcode = [0] * NVTX

        self._process()
        self._sort()

        if self.nextstart & 0x80:
            return
        self.scanline = self.ayflg[self.nextstart]

        while True:
            # ADDSTARTS (PPAK.s:285)
            b = self.nextstart
            while not (b & 0x80):
                if self.ayflg[b] != self.scanline:
                    break
                v = self.anvrtx[b]
                self.ayflg[b] = o.y[v]          # start-Y becomes end-Y
                nxt = self.anext[b]
                self._insert(b)
                b = nxt
            self.nextstart = b

            # SCANPLY2 (PPAK.s:355)
            self.hcnt = 0
            self.buf = []                       # (x, obj, code) per crossing
            b = self.firstactv
            prev = None
            while not (b & 0x80):
                nxt = self._edge(b, prev)
                if nxt is None:                 # the edge was unlinked
                    b = self._unlinked_next
                else:
                    prev = b
                    b = nxt
            if self.firstactv & 0x80 and not self.buf:
                return
            self._doscan()
            self.scanline += 1
            if self.scanline >= self.TH:
                return
            if (self.firstactv & 0x80) and (self.nextstart & 0x80):
                return

    # ------------------------------------------------------------------
    def _edge(self, b, prev):
        """SCANPLY3-7.  Returns the next record, or None if this one was
        unlinked (in which case _unlinked_next holds the successor)."""
        o = self.o
        if self.ayflg[b] == self.scanline:
            v = self.anvrtx[b]
            if self.nvrtx[v] & 0x80:            # TERMINATE
                nxt = self.anext[b]
                if b == self.firstactv:
                    self.firstactv = nxt
                else:
                    self.anext[prev] = nxt
                self._unlinked_next = nxt
                return None
            # CHAIN into the next edge of the same run
            w = self.nvrtx[v]
            self.anvrtx[b] = w
            self.adxcoeff[b] = self.ndxcoeff[v]
            self.adxfract[b] = self.ndxfract[v]
            self.adxcode[b] = self.ndxcode[v]
            self.axcoeff[b] = o.x[v]
            self.axfract[b] = 0
            self.ayflg[b] = o.y[self.anvrtx[b]]

        # SCANPLY6: step the edge and emit its crossing.
        # ⭐ The x emitted is the MIDPOINT of the edge's travel across this
        # scanline - `CLC / ADC TEMP / ROR` averages the old and new integer x.
        f = self.axfract[b] + self.adxfract[b]
        self.axfract[b] = f & 0xFF
        old = self.axcoeff[b]
        self.axcoeff[b] = (old + self.adxcoeff[b] + (f >> 8)) & 0xFF
        # `CLC / ADC TEMP / ROR` is a NINE-bit average: the add's carry becomes
        # the rotate's incoming bit 7, so no precision is lost when old + new
        # exceeds 255.
        mid = ((old + self.axcoeff[b]) >> 1) & 0xFF
        self.buf.append((mid, self.cur, self.adxcode[b]))
        self.hcnt += 2
        return self.anext[b]

    # ------------------------------------------------------------------
    def _insert(self, b):
        """ADDSTARTS3-7 - into the active list, sorted by x, ties by slope."""
        if self.firstactv & 0x80:
            self.anext[b] = 0x80
            self.firstactv = b
            return
        prev = None
        y = self.firstactv
        while True:
            ahead = self.axcoeff[b] < self.axcoeff[y]
            if not ahead and self.axcoeff[b] == self.axcoeff[y]:
                # Equal x: the shallower slope goes first (ADDSTARTS6).
                d = ((self.adxcoeff[b] << 8) | self.adxfract[b]) - \
                    ((self.adxcoeff[y] << 8) | self.adxfract[y])
                ahead = _s16(d) < 0
            if ahead:
                self.anext[b] = y
                if y == self.firstactv:
                    self.firstactv = b
                else:
                    self.anext[prev] = b
                return
            prev = y
            y = self.anext[y]
            if y & 0x80:
                self.anext[b] = 0x80
                self.anext[prev] = b
                return

    # ------------------------------------------------------------------
    def _doscan(self):
        """DOSCAN (PPAK.s:764) - pack this scanline's crossings into records
        and merge them into the database.

        ⭐⭐ A B-POLYGON'S COMPLEMENT IS A DRAWING RULE, NOT A STORAGE RULE, and
        getting that backwards is the difference between a working table and a
        ball that falls through the floor.  DOSCN5 (PPAK.s:824) packs
        CONSECUTIVE CROSSING PAIRS into records whatever the object is, so a
        B-polygon STORES ITS INTERIOR exactly as a normal polygon does; only
        DOBAR's walk differs, starting at x=159 and finishing at x=0 so that
        the OUTSIDE is what gets painted.

        That is what makes the whole collision model work: the table's backdrop
        is object 0, a B-polygon whose vertices trace the playfield, so its
        records ARE the open area and the gaps between them are wall -- which
        is exactly how CHECKVERT (RUN.s:1668) reads them.  The picture is the
        other way up: the open area is left alone and the wall is painted.
        """
        if not self.buf:
            return
        xs = [c[0] for c in self.buf]
        codes = [c[2] for c in self.buf]
        recs = []
        for i in range(0, len(xs) - 1, 2):
            recs.append((xs[i], self.cur, xs[i + 1],
                         ((codes[i + 1] & 15) << 4) | (codes[i] & 15)))
        if not recs:
            return
        row = self.rows[self.scanline]
        # ⛔ ABORT WITH 32 BYTES TO SPARE (DOSCN4, PPAK.s:790).  Every editor
        # operation checks for it and rolls the object back, which is why a
        # table can never be left half converted.
        if (self.used() + len(recs) * 4 + 32) > self.spanbytes:
            raise Abort('the span database is full')
        row.extend(recs)
        self.pbdx[self.scanline] = len(row) * 4

    def used(self):
        return sum(self.pbdx)

    # ------------------------------------------------------------------
    def _process(self):
        """PROCESSPOLY / PROCESSVERTEX (PPAK.s:433)."""
        o = self.o
        self.startcount = 0
        self.lastlink = 0
        self.x1, self.y1 = o.x[0], o.y[0]
        i = 1
        wrap = 1
        carry = True                            # SEC before the first call
        while True:
            carry, j = self._vertex(i, carry)
            # ⛔ PROCESSVERTEX LEAVES Y PAST THE HORIZONTAL RUN IT SKIPPED, and
            # PROCESSPOLY carries on from THERE - `LDA (PLYPTRX),Y / STA X1`
            # reads the vertex the skip stopped at, not the one we called with.
            # Restarting from i+1 instead re-processes every horizontal edge as
            # a fresh vertex; a U-shape then grows a staircase where its bottom
            # bar should be, and a B-polygon runs past its own last scanline.
            # Both were visible the moment the model drew them.
            self.x1, self.y1 = o.x[j], o.y[j]
            i = j + 1
            if i == wrap:
                break
            if i == o.n:
                i = 0
        self._vertex(i, carry)

    def _vertex(self, i, carry_in):
        """PROCESSVERTEX (PPAK.s:511).

        `carry_in` is "the run is currently descending"; the first return value
        is the same fact for the next vertex.  The second is where Y is LEFT --
        past any horizontal run - which PROCESSPOLY continues from.
        """
        o = self.o
        x2 = o.x[i]
        dx = (x2 - self.x1) & 0xFF
        dxpos = x2 >= self.x1                   # the carry out of the SBC
        y2 = o.y[i]

        # PRVRTX2 (PPAK.s:527): skip any horizontal edges that follow.  `j`
        # ends on the LAST vertex of the run, and is where Y is left.
        j = i
        while True:
            k = (j + 1) % o.n
            if o.y[k] != y2:
                break
            j = k

        if y2 >= self.y1:                       # the edge DESCENDS
            dy = (y2 - self.y1) & 0xFF
            self.dx = pcsphys.divide(dx, dy, dxpos)
            if not carry_in:
                self._start(j)                  # START: a local maximum
            else:
                self._chain_from_last(j)        # CHAIN
            return True, j

        # PRVRTX4: the edge ASCENDS.  dy and dx are negated and the sign handed
        # to the divide is inverted with them.
        dy = (-(y2 - self.y1)) & 0xFF
        dxn = (-(x2 - self.x1)) & 0xFF
        self.dx = pcsphys.divide(dxn, dy, not dxpos)
        if carry_in:                            # TERMINAL: a local minimum
            self.nvrtx[self.lastlink] = 0x80
        # ⚠ The ascending chain links the vertex we were CALLED with, not the
        # one the skip ended on - PRVRTX4 does `LDY TEMP` before PRVRTX6 and
        # only restores Y afterwards.
        self._chain_to(i)
        return False, j

    def _start(self, i):
        """PRVRTX3 - allocate the two edges leaving a local maximum."""
        x = self.startcount
        if x >= NEDGE:
            raise Abort('more than %d active edges' % NEDGE)
        co, fr, cd = self.dx
        o = self.o
        self.anvrtx[x] = i
        self.axcoeff[x] = self.x1
        self.adxcoeff[x], self.adxfract[x], self.adxcode[x] = co, fr, cd

        v = self.lastlink
        self.anvrtx[x + 1] = self.nvrtx[v]
        self.axcoeff[x + 1] = o.x[v]
        self.adxcoeff[x + 1] = self.ndxcoeff[v]
        self.adxfract[x + 1] = self.ndxfract[v]
        self.adxcode[x + 1] = self.ndxcode[v]

        self.ayflg[x] = self.ayflg[x + 1] = self.y1
        self.axfract[x] = self.axfract[x + 1] = 0
        self.startcount = x + 2
        self.lastlink = i

    def _chain_from_last(self, i):
        """The descending CHAIN: link LASTLINK -> this vertex."""
        co, fr, cd = self.dx
        v = self.lastlink
        self.nvrtx[v] = i
        self.ndxcoeff[v] = co
        self.ndxfract[v] = fr
        self.ndxcode[v] = cd
        self.lastlink = i

    def _chain_to(self, i):
        """PRVRTX5/6: the ascending CHAIN links this vertex -> LASTLINK."""
        co, fr, cd = self.dx
        self.nvrtx[i] = self.lastlink
        self.ndxcoeff[i] = co
        self.ndxfract[i] = fr
        self.ndxcode[i] = cd
        self.lastlink = i

    def _sort(self):
        """SORTSTARTS (PPAK.s:471) - the start records by ascending Y."""
        self.firstactv = 0x80
        idx = list(range(self.startcount))
        idx.sort(key=lambda k: self.ayflg[k])
        self.nextstart = idx[0] if idx else 0x80
        for a, b in zip(idx, idx[1:]):
            self.anext[a] = b
        if idx:
            self.anext[idx[-1]] = 0x80


def _s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def render(pak, colours, width=None, height=None):
    """The span database as a picture: one byte a pixel, palette indices.

    ⭐ THIS IS THE PORT'S RENDERER, in Python, and it is what `pcsdraw.inc`
    does on the card with one span-solid write per span.  Walk each scanline's
    records in order and fill each span with its object's colour; later objects
    overwrite earlier ones, which IS the z-order.  A fillcolor of 0 writes
    nothing -- unfilled, but still solid (PPAK.s:269), which is how an
    invisible wall is built.

    ⛔ A B-POLYGON PAINTS THE COMPLEMENT OF ITS OWN SPANS on that row -- see
    _doscan.  The records are its interior; the picture is everything else.
    """
    w = width or pak.TW
    h = height or pak.TH
    fb = bytearray(w * h)

    def fill(xl, xr, c):
        if xr < xl:
            xl, xr = xr, xl
        for x in range(max(0, xl), min(w - 1, xr) + 1):
            fb[y * w + x] = c

    for y in range(min(h, pak.TH)):
        run = []                                # consecutive records of one object
        for rec in pak.rows[y] + [None]:
            if run and (rec is None or rec[1] != run[0][1]):
                obj = run[0][1]
                c = colours[obj] if obj < len(colours) else 0
                if c:
                    if pak.objs[obj].objid == BPOLY:
                        edges = [0]
                        for (xl, _o, xr, _s) in run:
                            edges += [xl, xr]
                        edges.append(w - 1)
                        for i in range(0, len(edges) - 1, 2):
                            fill(edges[i], edges[i + 1], c)
                    else:
                        for (xl, _o, xr, _s) in run:
                            fill(xl, xr, c)
                run = []
            if rec is not None:
                run.append(rec)
    return fb


# ══════════════════════════════════════════════════════════════════════
def _selftest():
    """⭐ THE SCAN CONVERTER, CHECKED BY ITS OUTPUT rather than by reading it.

    Four shapes, each of which broke something real while this was written:

      triangle   the base case - sloped edges, the midpoint rounding
      U          ⛔ CONCAVE, so two spans a scanline, and horizontal edges.
                 PROCESSVERTEX leaves Y past a horizontal run and PROCESSPOLY
                 continues from THERE; restarting from i+1 instead re-processes
                 every horizontal edge and the bottom bar grows a staircase.
      backdrop   ⛔ A B-POLYGON STORES ITS INTERIOR AND PAINTS THE COMPLEMENT.
                 Storing the complement instead looks identical on screen and
                 inverts the ball's world.
      unaligned  ⛔ a first edge that is horizontal violates ALIGNPOLY's
                 precondition and the sweep runs out of edge records.
    """
    fails = []

    def pic(objs, w, h, colours):
        p = Pak(height=h, width=w)
        p.objs = objs
        p.display()
        return p, render(p, colours, w, h)

    def rows(fb, w, h):
        return [''.join('#' if fb[y * w + x] else '.' for x in range(w))
                for y in range(h)]

    # --- 1  a triangle fills, and its apex is one row -------------------
    t = Obj(POLY, 1, [5, 30, 12], [2, 4, 20])
    t.align()
    p, fb = pic([t], 40, 24, [1])
    r = rows(fb, 40, 24)
    if r[0].count('#') or r[1].count('#'):
        fails.append('triangle: painted above its apex')
    if not 0 < r[2].count('#') < r[4].count('#'):
        fails.append('triangle: does not widen from the apex')
    if r[20].count('#'):
        fails.append('triangle: painted below its last vertex')

    # --- 2  a concave U has TWO spans in its uprights and one in its bar -
    u = Obj(POLY, 1, [4, 12, 12, 24, 24, 32, 32, 4], [2, 2, 16, 16, 2, 2, 21, 21])
    u.align()
    p, fb = pic([u], 40, 24, [1])
    if len(p.rows[8]) != 2:
        fails.append('U: %d spans on row 8, wanted 2 (the uprights)' % len(p.rows[8]))
    if len(p.rows[18]) != 1:
        fails.append('U: %d spans on row 18, wanted 1 (the bar)' % len(p.rows[18]))
    r = rows(fb, 40, 24)
    if r[18].count('#') <= r[8].count('#'):
        fails.append('U: its bar is no wider than its uprights')
    if r[21].count('#'):
        fails.append('U: painted below its last vertex')

    # --- 3  a B-polygon stores its interior and paints the outside -------
    back = Obj(BPOLY, 2, [4, 40, 40, 4], [1, 1, 20, 20])
    back.align()
    p, fb = pic([back], 44, 22, [2])
    got = p.rows[8]
    if len(got) != 1 or got[0][0] != 4 or got[0][2] != 40:
        fails.append('B-polygon: row 8 records %r, wanted one span 4..40' % (got,))
    r = rows(fb, 44, 22)
    if r[8][10] == '#':
        fails.append('B-polygon: painted INSIDE itself - the complement is inverted')
    if r[8][0] != '#' or r[8][43] != '#':
        fails.append('B-polygon: did not paint outside itself')

    # --- 4  the alignment precondition ----------------------------------
    flat = Obj(POLY, 1, [4, 20, 20, 4], [5, 5, 5, 5])
    if flat.align():
        fails.append('align: a polygon with every Y equal was accepted')
    bad = Obj(POLY, 1, [4, 20, 20, 4], [5, 5, 12, 12])
    p = Pak(height=24, width=40)
    p.objs = [bad]
    try:
        p.display()
        fails.append('unaligned: converted without complaint')
    except Abort:
        pass
    if not bad.align() or not (bad.y[0] < bad.y[1]):
        fails.append('align: did not rotate the list to a descending first edge')

    return fails


if __name__ == '__main__':
    bad = _selftest()
    for b in bad:
        print('FAIL', b)
    if bad:
        sys.exit(1)
    print('ok  the scan converter: a triangle, a concave U with two spans a')
    print('    scanline, a B-polygon that stores its interior and paints its')
    print('    complement, and ALIGNPOLY\'s precondition enforced.')
