#!/usr/bin/env python3
"""pcsdisk.py - the editor's DISK panel, modelled (pcs.md §8, pcsdisk.inc).

DISK.s offered LOAD, SAVE and QUIT over a name typed blind.  The port keeps
the name field and the three buttons and adds a catalogue: the `*.pbt` tables
in /SD0/DATA, sorted, DK_ROWS a page, picked with the mouse.  This module is
the model `checkpcs.py` applies each DISK gesture and key through, and the
`.pbt` reader it loads the card's files with - so a LOAD in the model reads
the same bytes the machine's PFLoad did, and a SAVE writes the bytes the
machine's PFSave must have written.
"""
import pcspak as K

# card pixels (pcsdisk.inc)
TOOLX = 536                 # a press here ends the panel and takes the tool
DX, DW = 332, 192           # the controls' left edge and width
RY, RH, ROWS = 56, 16, 14   # the list's first row, a row, rows a page
BW, BH = 60, 24             # a button
BUTTONS = (('LOAD', DX, 296), ('SAVE', DX + 66, 296),
           ('QUIT', DX + 132, 296), ('MORE', DX, 328))
MAXN, NAMELEN = 48, 8

# records' op[1] kinds (EDL.* in pcsdisk.inc), after pcsmag's 4..6
EDL_KEY, EDL_DPICK, EDL_DLOAD, EDL_DSAVE, EDL_DQUIT, EDL_DPAGE = range(7, 13)
# pferr (pcsfile.inc) and the panel's own two
PF_ENOF, PF_EHDR, PF_EMAG, PF_EBIG, PF_ESHRT, PF_ECNT, PF_EWRT, PF_ELAY = \
    range(1, 9)
DK_EABT, DK_ENAM = 9, 10

LOGIC, WSET = 24, 4
DBSIZE = 4096               # PC.DBSize: the object area


class Table(object):
    """One `.pbt`: rows, logic[24], wset[4], the objects and the layer."""

    def __init__(self, rows, logic, wset, objs, layer):
        self.rows, self.logic, self.wset = rows, list(logic), list(wset)
        self.objs, self.layer = objs, list(layer)


def parse(blob):
    """⭐ PFLoad's checks, in PFLoad's order: the answer is a Table, or the
    pferr the machine refuses the file with."""
    if len(blob) < 8:
        return PF_EHDR
    if blob[:4] != b'PCS1':
        return PF_EMAG
    rows, nobj, plen = blob[4], blob[5], blob[6] << 8 | blob[7]
    if plen > DBSIZE + LOGIC + WSET:
        return PF_EBIG
    pay = blob[8:8 + plen]
    if len(pay) < plen:
        return PF_ESHRT
    area = pay[LOGIC + WSET:]
    if not area or area[0] != nobj:
        return PF_ECNT
    n = area[0]
    lens = area[1:1 + n]
    p = 1 + n
    objs = []
    for ln in lens:
        r = area[p:p + ln]
        p += ln
        k = r[2]
        objs.append(K.Obj(r[0], r[1], list(r[3:3 + k]), list(r[3 + k:3 + 2 * k]),
                          list(r[3 + 2 * k:])))
    layer = []
    t = blob[8 + plen:]
    if t:
        if len(t) < 4 or t[:2] != b'PL':
            return PF_ELAY
        cnt = t[2] << 8 | t[3]
        if len(t) < 4 + 3 * cnt:
            return PF_ELAY
        for i in range(cnt):
            y, x, c = t[4 + 3 * i:7 + 3 * i]
            if y >= 240 or x >= 160 or not c:
                return PF_ELAY
            layer.append((y, x, c))
    return Table(rows, pay[:LOGIC], pay[LOGIC:LOGIC + WSET], objs, layer)


def listed(name):
    """A catalogue entry, or None: one to eight letters and digits before a
    `.pbt`, folded to lower case - DkParse."""
    base, dot, ext = name.rpartition('.')
    if not dot or ext.lower() != 'pbt':
        return None
    if not 1 <= len(base) <= NAMELEN or not all(
            c.isascii() and c.isalnum() for c in base):
        return None
    return base.lower()


def catalogue(files):
    """⭐ Sorted as NUL-padded bytes, which is DkCmp's order - so `demo2`
    sorts before `demo2l` - and the first MAXN of them."""
    names = sorted(n for n in (listed(f) for f in files) if n)
    return names[:MAXN]


def in_rect(px, py, x, y, w, h):
    return 0 <= px - x < w and 0 <= py - y < h


class Panel(object):
    """The panel's state across a session: whether it is up, the name as
    typed, the page, and the card - `files`, name -> bytes, which a SAVE
    writes into and a LOAD reads out of."""

    def __init__(self, files):
        self.up = False
        self.name = ''
        self.pg = 0
        self.files = dict(files)
        self.cat = catalogue(self.files)

    def open(self):
        self.up = True
        self.pg = 0
        self.cat = catalogue(self.files)

    def key(self, ch):
        """[op0..op4], and the name after it."""
        if ch in (8, 0x7F):
            self.name = self.name[:-1]
        elif chr(ch).isascii() and chr(ch).isalnum() and len(self.name) < NAMELEN:
            self.name += chr(ch).lower()
        return [0, EDL_KEY, ch, len(self.name), 0]

    def press(self, px, py, st):
        """A press at (px, py): None if the panel does not take it (the tool
        column, which ends it), else (op, answer).  `st` is the editor's
        table - `db`, `wset`, `layer` - which LOAD replaces."""
        if px >= TOOLX:
            self.up = False
            return None
        miss = ([0] * 5, 0xFF)
        if not 0 <= px - DX < DW:
            return miss
        if 0 <= py - RY < ROWS * RH:
            i = self.pg + (py - RY) // RH
            if i >= len(self.cat):
                return miss
            self.name = self.cat[i]
            return [0, EDL_DPICK, i, len(self.name), 0], 0xFF
        hit = next((b for b, x, y in BUTTONS if in_rect(px, py, x, y, BW, BH)),
                   None)
        if hit == 'QUIT':
            self.up = False
            return [0, EDL_DQUIT, 0, 0, 0], 0xFF
        if hit == 'MORE':
            self.pg += ROWS
            if self.pg >= len(self.cat):
                self.pg = 0
            return [0, EDL_DPAGE, self.pg, 0, 0], 0xFF
        if hit == 'LOAD':
            return self.load(st)
        if hit == 'SAVE':
            return self.save(st)
        return miss

    def load(self, st):
        if not self.name:
            return [0, EDL_DLOAD, DK_ENAM, len(st['db'].objs), 0], 1
        blob = self.files.get(self.name + '.pbt')
        t = PF_ENOF if blob is None else parse(blob)
        if not isinstance(t, Table):
            if t == PF_ELAY:
                import pcsmag
                st['layer'] = pcsmag.Layer()    # ⚠ PFLoad cleared it
            return [0, EDL_DLOAD, t, len(st['db'].objs), 0], 1
        import pcsedit
        import pcsmag
        st['db'] = pcsedit.DB(t.objs, t.logic, width=160, height=240)
        st['wset'] = list(t.wset)
        st['layer'] = pcsmag.Layer(t.layer)
        return [0, EDL_DLOAD, 0, len(t.objs), 0], 0

    def save(self, st):
        if not self.name:
            return [0, EDL_DSAVE, DK_ENAM, len(self.cat), 0], 1
        self.files[self.name + '.pbt'] = image(st)
        self.cat = catalogue(self.files)
        return [0, EDL_DSAVE, 0, len(self.cat), 0], 0


def image(st):
    """The bytes PFSave writes for the editor's table: a 240-row header, the
    payload, and the layer's trailer if it has one."""
    import mkpcs
    return mkpcs.table_file(st['db'].logic, st['wset'], st['db'].objs,
                            st['layer'].triples(), rows=240)


def _selftest():
    import mkpcs
    import pcsmag
    objs = mkpcs.demo_table()
    blob = mkpcs.table_file([0] * 24, [5, 3, 3, 4], objs, pcsmag.demo_layer())
    t = parse(blob)
    assert isinstance(t, Table) and len(t.objs) == len(objs)
    assert mkpcs.serialise(t.objs) == mkpcs.serialise(objs)
    assert t.layer == sorted(pcsmag.demo_layer())
    assert parse(blob[:5]) == PF_EHDR and parse(b'XXXX' + blob[4:]) == PF_EMAG
    assert parse(blob[:40]) == PF_ESHRT
    assert parse(blob[:-1]) == PF_ELAY
    assert catalogue(['demo2l.pbt', 'demo2.pbt', 'Demo1.PBT', 'v3menu',
                      'toolongname.pbt', 'a.b.pbt', '.pbt']) \
        == ['demo1', 'demo2', 'demo2l']
    p = Panel({'demo1.pbt': blob})
    for c in b'Demo1\x08\x081':
        p.key(c)
    assert p.name == 'dem1', p.name
    print('ok    pcsdisk: the .pbt reader, its refusals, the catalogue, the name')


if __name__ == '__main__':
    _selftest()
