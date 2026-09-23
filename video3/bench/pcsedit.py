#!/usr/bin/env python3
"""pcsedit.py - EDIT.s's operations on the object database.

⛔ WRITTEN FROM THE 6502 AND NEVER ADJUSTED TO MATCH THE 6809.

⭐⭐ THIS IS WHAT A CONSTRUCTION SET IS.  Seven operations - add a part, delete
one, drag it, drag a vertex, cut a vertex, paste one, paint it - and every one
of them has to leave the span database CONSISTENT, because that database is
simultaneously the picture, the hit test and the ball's collision world
(`video3/docs/pcs.md` 2).  The original's shape is the same every time:

    REMOVEPOLY  - take the object's spans out
    (the edit)
    DRAWOBJ     - scan it again
    if it aborted: take them out, put the old ones back, and undo the edit

⚠ THE GAP BUFFER DOES NOT PORT AND NEITHER DOES HALF OF EACH ROUTINE.  Most of
EDIT.s's lines here are `MOVEUP`/`MOVEDOWN`/`ADDIYX` sliding bytes around
`MIDTOP`/`MIDBTM`/`MEMBTM` so a record can grow in the middle of a packed
array.  The port's database is a per-scanline linked list with a free list
(pcs.md 2), so what is left is the EDIT - which is what this models.

⛔ AND DELETING AN OBJECT RENUMBERS EVERY OTHER ONE.  Object indices live in
three places at once: the span records, the wiring kit's LOGIC table, and the
draw order itself.  `DELOBJ2` walks the whole span database decrementing, and
`FIXINDX` does the LOGIC table - and an entry that named the DELETED object
becomes 0, which is "unwired".

Source: `reference/pcs/EDIT.s`, lines cited throughout.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pcsobj                                                  # noqa: E402
import pcspak as K                                             # noqa: E402


MAXOBJ = 127            # PBDATA[0], EDIT.s:707's `LDX OBJCOUNT / INX / BMI`
MAXVTX = 63             # EDIT.s:938's `CPX #63 / BCS ABORTPP`
MINVTX = 3              # EDIT.s:870's `CPX #4 / BCS` - below four, delete


class Abort(Exception):
    """An edit the database refused.  ⭐ The original's answer to every one of
    these is to put the object back exactly as it was, which is why each
    routine's failure arm re-scans the OLD record rather than reporting."""


class DB(object):
    """The object database, and the display built from it.

    ⭐ `objs` is the list `PPAK.s` walks and `pak` is what it built; an edit
    mutates the first and re-runs the second.  ⚠ The MACHINE re-scans one
    object and merges its spans back in place; rebuilding everything gives the
    same CONTENT because the records are in object order either way, and the
    content is what the bench compares.  That is exactly the division that
    makes the incremental path checkable at all.
    """

    def __init__(self, objs, logic=None, width=160, height=240):
        self.objs = list(objs)
        self.logic = list(logic or [0] * 24)
        self.TW, self.TH = width, height
        self.pak = None
        self.rescan()

    def rescan(self):
        pak = K.Pak(height=self.TH, width=self.TW)
        pak.objs = self.objs
        pak.display()
        self.pak = pak
        return pak

    # ⚠ A copy deep enough to roll back: the records are what edits touch.
    def _snap(self):
        return [K.Obj(o.objid, o.fillcolor, o.x, o.y, o.L) for o in self.objs], \
            list(self.logic)

    def _restore(self, snap):
        self.objs, self.logic = snap[0], snap[1]

    def _commit(self, snap):
        """⭐ THE SHAPE OF EVERY OPERATION: re-scan, and if the converter gave
        up, put the object back exactly as it was.  `DRAWOBJ`'s carry is the
        whole protocol.
        ⛔ AND THE LIMIT IS PER OBJECT, NOT PER SCANLINE.  `PRVRTX3` aborts at
        eight ACTIVE EDGE RECORDS (PPAK.s:568) and the active list belongs to
        the polygon being scanned - so one polygon may have four spans on a
        line and the next polygon gets its own eight.  There is no cap on spans
        per scanline anywhere in PPAK.s; the only other refusal is the gap
        buffer running out, which ADDOBJ and PASTEPOINT check up front.
        ⚠ A "four spans a scanline" check was invented here and had to come
        out: the model is corrected against the 6502, never the other way.
        """
        try:
            self.rescan()
        except K.Abort:
            self._restore(snap)
            self.rescan()
            raise Abort('the scan converter refused the edit')

    # ── ADDOBJ (EDIT.s:703) ────────────────────────────────────────────
    def add(self, obj):
        """A template onto the table.  ⚠ The limits are the original's and
        stay: 127 objects, because PBDATA[0] is the count AND the offset."""
        if len(self.objs) >= MAXOBJ:
            raise Abort('127 objects is the limit')
        snap = self._snap()
        self.objs.append(obj)
        self._commit(snap)
        return len(self.objs) - 1

    # ── DELETEOBJ (EDIT.s:610) ─────────────────────────────────────────
    def delete(self, i):
        """⛔ AND IT RENUMBERS EVERYTHING.  Every span record above the deleted
        object decrements, and so does every LOGIC entry - `FIXINDX`, and an
        entry that NAMED the deleted object becomes 0, which is unwired.

        ⚠ Object 0 is the backdrop and the editor never offers to delete it;
        `CUTPOINT4` checks `LDA NEXTOBJ / BEQ ENDPTEDIT` for exactly that.
        """
        if i == 0:
            raise Abort('object 0 is the backdrop')
        if not 0 <= i < len(self.objs):
            raise Abort('no such object')
        snap = self._snap()
        del self.objs[i]
        for k, v in enumerate(self.logic):
            if k % 4 == 3:
                continue            # the action byte is not an index
            if v == i:
                self.logic[k] = 0
            elif v > i:
                self.logic[k] = v - 1
        self._commit(snap)

    # ── DRAGOBJ (EDIT.s:439) ───────────────────────────────────────────
    def drag(self, i, dx, dy):
        """Translate every vertex, with the bounding box kept on the table.

        ⚠ The original clamps x against 255 and y against 191 - the ATARI's
        screen height, and for x effectively no clamp at all, because PPAK.s
        clips at 159 anyway.  The port clamps to its own table: the world grew
        to 240 rows (pcs.md 3) and a number that was the screen's is not one to
        carry across.
        """
        o = self.objs[i]
        snap = self._snap()
        lo_x, hi_x = min(o.x), max(o.x)
        lo_y, hi_y = min(o.y), max(o.y)
        dx = max(1 - lo_x, min(dx, self.TW - 2 - hi_x))
        dy = max(1 - lo_y, min(dy, self.TH - 2 - hi_y))
        o.x = [v + dx for v in o.x]
        o.y = [v + dy for v in o.y]
        # ⭐ A library part's ART moves with its vertices, because they are the
        # same coordinates - which is the whole reason the port keeps one `px`.
        if o.L:
            o.L[pcsobj.L_PX] = (o.L[pcsobj.L_PX] + dx) & 0xFF
            o.L[pcsobj.L_VERT] = (o.L[pcsobj.L_VERT] + dy) & 0xFF
        if not o.align():
            self._restore(snap)
            self.rescan()
            raise Abort('the drag made every Y equal')
        self._commit(snap)
        return dx, dy

    # ── DRAGPOINT (EDIT.s:780) ─────────────────────────────────────────
    def dragpoint(self, i, v, x, y):
        """Move one vertex.  ⭐ ALIGNPOLY runs after every move and may ROTATE
        the vertex list, so the vertex's index moves with it - `MINPT` is
        corrected by the rotation ALIGNPOLY reports.  ⛔ And if ALIGNPOLY fails
        (every Y equal) the vertex goes back where it was, which is the only
        undo in the program."""
        o = self.objs[i]
        snap = self._snap()
        ox, oy = o.x[v], o.y[v]
        o.x[v] = max(1, min(x, self.TW - 2))
        o.y[v] = max(1, min(y, self.TH - 2))
        n = _align_rot(o)
        if n is None:
            o.x[v], o.y[v] = ox, oy
            o.align()
            self._restore(snap)
            self.rescan()
            raise Abort('every Y would be equal')
        v = (v - n) % o.n
        self._commit(snap)
        return v

    # ── CUTPOINT (EDIT.s:855) ──────────────────────────────────────────
    def cutpoint(self, i, v):
        """⛔ BELOW FOUR VERTICES THE OBJECT GOES, not the vertex: a polygon
        needs three, so cutting the fourth deletes the part.  ⚠ Except object
        0, which is the backdrop and simply refuses."""
        o = self.objs[i]
        if o.n < 4:
            if i == 0:
                raise Abort('the backdrop cannot be cut away')
            return self.delete(i)
        snap = self._snap()
        del o.x[v]
        del o.y[v]
        if not o.align():
            self._restore(snap)
            self.rescan()
            if i == 0:
                raise Abort('every Y would be equal')
            return self.delete(i)
        self._commit(snap)

    # ── PASTEPOINT (EDIT.s:935) ────────────────────────────────────────
    def pastepoint(self, i, v):
        """A new vertex after `v`, at the MIDPOINT of that edge.

        ⭐ The original puts it at (MINX, MINY) - where SELECTPOINT last found
        the cursor - so pasting is "drop a vertex where I am pointing".  The
        bench's scripted session has no cursor, so it asks for the midpoint,
        which is the same operation with the caller choosing the point."""
        o = self.objs[i]
        if o.n >= MAXVTX:
            raise Abort('63 vertices is the limit')
        snap = self._snap()
        w = (v + 1) % o.n
        mx = (o.x[v] + o.x[w]) // 2
        my = (o.y[v] + o.y[w]) // 2
        o.x.insert(v + 1, mx)
        o.y.insert(v + 1, my)
        if not o.align():
            self._restore(snap)
            self.rescan()
            raise Abort('every Y would be equal')
        self._commit(snap)
        return (v + 1) % o.n

    # ── PAINTOBJ (EDIT.s:1132) ─────────────────────────────────────────
    def paint(self, i, colour):
        """⛔ A LIBRARY PART CANNOT BE PAINTED - `CMP #<LIBOBJ / BEQ PAINTO4`
        returns without touching it, because its picture is its art and its
        polygon is the invisible collision shape.

        ⭐ AND PAINTING WITH THE COLOUR IT ALREADY HAS CLEARS IT: `CMP
        FILLCOLOR / BNE *+4 / LDA #0`.  The brush is a toggle, and 0 is
        unfilled-but-solid, so that is how an invisible wall is made.

        ⛔ The original then stores `new XOR old` and XOR-blits the difference.
        This card cannot XOR (pcs.md 2), so the port stores the new colour and
        repaints - which the Apple II sources make unavoidable anyway, because
        that trick only works while a colour is three bits wide.
        """
        o = self.objs[i]
        if o.objid == K.LIBOBJ:
            return o.fillcolor
        o.fillcolor = 0 if colour == o.fillcolor else colour
        self.rescan()
        return o.fillcolor


def _align_rot(o):
    """ALIGNPOLY, reporting HOW FAR it rotated.  ⭐ EDIT.s needs the rotation
    to correct MINPT (`SEC / SBC YTEMP ;ALIGN DISP`), which is the only reason
    it is not just a boolean."""
    for n in range(o.n):
        if o.y[0] < o.y[1]:
            return n
        o.x.append(o.x.pop(0))
        o.y.append(o.y.pop(0))
    return None


def run_script(db, script):
    """⭐ THE SESSION, STEP BY STEP, AND WHAT EACH ONE CAME TO.

    Returns one byte a step: 0 for "the edit took", 1 for "the database refused
    it".  ⛔ That sequence is half the gate - an edit the converter will not
    take has to leave NO TRACE, and the only way to check a rollback is to
    provoke one and then compare everything.
    """
    import mkpcs
    out = []
    for (op, a, b, c, d) in script:
        if op == mkpcs.PE_END:
            break
        try:
            if op == mkpcs.PE_ADD:
                db.add(mkpcs.place(a, b, c))
            elif op == mkpcs.PE_DEL:
                db.delete(a)
            elif op == mkpcs.PE_DRAG:
                db.drag(a, _sb(b), _sb(c))
            elif op == mkpcs.PE_DRAGP:
                db.dragpoint(a, b, c, d)
            elif op == mkpcs.PE_CUT:
                db.cutpoint(a, b)
            elif op == mkpcs.PE_PASTE:
                db.pastepoint(a, b)
            elif op == mkpcs.PE_PAINT:
                db.paint(a, b)
            else:
                raise Abort('unknown operation %d' % op)
            out.append(0)
        except (Abort, ValueError, IndexError, KeyError):
            out.append(1)
    return bytes(out)


def _sb(v):
    return v - 256 if v & 0x80 else v


# ═══════════════════════════════════════════════════════════════════════════
def selftest():
    """⭐ THE OPERATIONS, CHECKED BY WHAT THEY LEAVE BEHIND.

    Every claim here is about the DATABASE after an edit, because the database
    is the picture, the hit test and the collision world at once - and the one
    thing a construction set must never do is leave the three disagreeing.
    """
    import mkpcs
    bad = []

    def fresh():
        return DB(mkpcs.test_table(), width=mkpcs.TW, height=mkpcs.TH)

    def plain():
        """⚠ A table with room in it.  The bench's own is deliberately at the
        four-span limit in places (pcs.md 5), so an edit that legitimately
        overflows would be indistinguishable from one that is wrong."""
        os_ = [K.Obj(K.BPOLY, 24, [4, 156, 156, 4], [2, 2, 236, 236]),
               K.Obj(K.POLY, 4, [30, 90, 60], [40, 60, 100])]
        for o in os_:
            o.align()          # ⚠ ALIGNPOLY's precondition, always
        return DB(os_, width=mkpcs.TW, height=mkpcs.TH)

    db = fresh()
    n0 = len(db.objs)
    rows0 = [list(r) for r in db.pak.rows]

    # -- 1  add, then delete, and the database is what it was --------------
    o = mkpcs.place('BMP1', 20, 8)     # ⚠ clear of the bar and the U
    i = db.add(o)
    if i != n0 or len(db.objs) != n0 + 1:
        bad.append('add() put the object at %d of %d' % (i, len(db.objs)))
    if db.pak.rows == rows0:
        bad.append('adding an object changed no scanline')
    db.delete(i)
    if [list(r) for r in db.pak.rows] != rows0:
        bad.append('add then delete did not restore the database')

    # -- 2  ⛔ DELETING RENUMBERS EVERY SPAN ABOVE IT ----------------------
    db = fresh()
    before = set(rec[1] for r in db.pak.rows for rec in r)
    db.delete(1)                      # the sloped bar
    after = set(rec[1] for r in db.pak.rows for rec in r)
    if max(after) != max(before) - 1:
        bad.append('delete left the object indices at %s' % sorted(after))
    if any(o >= len(db.objs) for o in after):
        bad.append('a span names an object that is gone')

    # ⛔ ... and the WIRING with it.  An entry naming the deleted object goes
    # to 0, and every entry above it comes down one.
    db = fresh()
    db.logic[0:4] = [1, 3, 5, 0x11]
    db.delete(3)
    if db.logic[0:3] != [1, 0, 4]:
        bad.append('delete left LOGIC as %s, wanted [1, 0, 4]' % db.logic[0:3])
    if db.logic[3] != 0x11:
        bad.append('delete renumbered the gate ACTION byte')

    # -- 3  object 0 is the backdrop and refuses ---------------------------
    db = fresh()
    try:
        db.delete(0)
        bad.append('the backdrop was deleted')
    except Abort:
        pass

    # -- 4  drag, and the ART moves with the vertices ----------------------
    db = fresh()
    o = db.objs[-1]                   # the BALL part
    px, vert = o.L[pcsobj.L_PX], o.L[pcsobj.L_VERT]
    x0 = list(o.x)
    dx, dy = db.drag(len(db.objs) - 1, 5, 7)
    if (dx, dy) != (5, 7):
        bad.append('the drag was clamped to (%d, %d) in open table' % (dx, dy))
    if o.x != [v + 5 for v in x0]:
        bad.append('the drag did not translate every vertex')
    if o.L[pcsobj.L_PX] != px + 5 or o.L[pcsobj.L_VERT] != vert + 7:
        bad.append("the drag left the part's ART behind")

    # ⛔ ... and the bounding box stays on the table.
    db = fresh()
    dx, dy = db.drag(len(db.objs) - 1, 120, 0)
    o = db.objs[-1]
    if max(o.x) > mkpcs.TW - 2:
        bad.append('a drag put a vertex at x=%d, off the table' % max(o.x))

    # -- 5  a vertex moves, and ALIGNPOLY may renumber it ------------------
    db = plain()
    o = db.objs[1]
    v = db.dragpoint(1, 0, 25, 35)
    if (o.x[v], o.y[v]) != (25, 35):
        bad.append('dragpoint lost track of the vertex it moved')
    # ⭐ and the precondition still holds, which is what ALIGNPOLY is for
    if not o.y[0] < o.y[1]:
        bad.append("dragpoint left ALIGNPOLY's precondition broken")

    # ⛔ ... and it is CLAMPED to the table, which is what stops a vertex
    # walking off the edge and the converter walking off with it.
    db = plain()
    v = db.dragpoint(1, 0, 250, 250)
    o = db.objs[1]
    if o.x[v] != mkpcs.TW - 2 or o.y[v] != mkpcs.TH - 2:
        bad.append('dragpoint clamped to (%d, %d)' % (o.x[v], o.y[v]))

    # -- 6  paste and cut are inverses, in vertex COUNT --------------------
    db = plain()
    n = db.objs[1].n
    db.pastepoint(1, 0)
    if db.objs[1].n != n + 1:
        bad.append('pastepoint gave %d vertices' % db.objs[1].n)
    db.cutpoint(1, 1)
    if db.objs[1].n != n:
        bad.append('cutpoint gave %d vertices' % db.objs[1].n)

    # ⛔ CUTTING A TRIANGLE DELETES THE OBJECT, because a polygon needs three.
    db = plain()
    tri = next(i for i, o in enumerate(db.objs) if o.n == 3)
    n0 = len(db.objs)
    db.cutpoint(tri, 0)
    if len(db.objs) != n0 - 1:
        bad.append('cutting a triangle left %d objects' % len(db.objs))

    # -- 7  paint, and its two rules ---------------------------------------
    db = plain()
    was = db.objs[1].fillcolor
    if db.paint(1, was + 1) != was + 1:
        bad.append('paint did not take')
    # ⭐ the same colour twice clears it to unfilled
    if db.paint(1, was + 1) != 0:
        bad.append('painting the same colour twice did not clear it')
    # ⛔ and a library part refuses
    db = fresh()
    lib = next(i for i, o in enumerate(db.objs) if o.objid == K.LIBOBJ)
    c = db.objs[lib].fillcolor
    db.paint(lib, 9)
    if db.objs[lib].fillcolor != c:
        bad.append('a library part was painted')

    # -- 8  ⛔ AN EDIT THE DATABASE REFUSES IS UNDONE ENTIRELY --------------
    # ⭐ ALIGNPOLY's precondition is the one a script can reach: a triangle
    # whose third vertex is dragged level with the other two has no edge that
    # slopes down, and the answer is not a broken picture - it is the edit not
    # happening.
    db = plain()
    o = db.objs[1]
    o.x, o.y = [30, 90, 60], [40, 40, 100]
    o.align()
    db.rescan()
    before = [list(r) for r in db.pak.rows]
    was = (list(o.x), list(o.y))
    v = next(i for i in range(3) if o.y[i] != 40)
    try:
        db.dragpoint(1, v, o.x[v], 40)
        bad.append('a degenerate polygon was accepted')
    except Abort:
        pass
    if (db.objs[1].x, db.objs[1].y) != was:
        bad.append('the refused vertex move was not undone')
    if [list(r) for r in db.pak.rows] != before:
        bad.append('a refused edit left the database changed')

    for m in bad:
        print('FAIL  %s' % m)
    if not bad:
        print('ok    the editor: add and delete round-trip, deleting renumbers\n'
              '      every span AND the wiring, the backdrop refuses, a drag\n'
              "      carries the part's art and stops at the table edge, a\n"
              '      vertex move survives ALIGNPOLY rotating the list, paste\n'
              '      and cut are inverses, cutting a triangle deletes the\n'
              '      object, paint toggles and refuses a library part, and an\n'
              '      edit the converter refuses leaves no trace.')
    return not bad


if __name__ == '__main__':
    sys.exit(0 if selftest() else 1)
