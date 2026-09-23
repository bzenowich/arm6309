#!/usr/bin/env python3
"""pcsfile.py - reading a real PCS table off a real disk.

⭐⭐ A SAVED TABLE IS AN ATARI DOS BINARY-LOAD FILE, and that is the whole
format.  `DISK.s`'s `SAVE` (line 373) sets `BSPARM` to `PBBASE`..`MIDBTM` and
calls `BSAVE`; `LOAD` (line 259) reads `$FF $FF`, then repeating
`start, end` address pairs each followed by `end - start + 1` bytes.  One
segment starts at **`$4B00`**, and that segment IS the table:

    $4B00  LOGIC[24]   six three-input AND gates, {in0, in1, in2, action}
    $4B18  WSET[4]     gravity, speed, kick, elasticity
    $4B1C  PBDATA      the object count, the record lengths, then the records
    ...    the free-hand (magnifier) layer, run-length compressed

⛔ AND THE RECORDS HOLD 6502 ADDRESSES, which is the one thing that cannot
survive the change of machine (`video3/docs/pcs.md` 5b).  A library object's
tail carries a bitmap pointer at `L[0..1]` and three proc vectors at
`L[10..15]`, all of them absolute.  ⭐ They are recoverable EXACTLY rather than
guessed: `RUN.s`'s own `EQU` chain gives every part's bitmap a numeric address
(`BITMAPS EQU $7B00`, `LFLIPB EQU LAUNCHERB+$48`, ...), so `L[0..1]` names the
template, and the template names the part type.  That is the re-keying the port
does on load, and it needs no table of its own.

⚠ THE DEFAULT TABLE IS NOT IN THE MIT SOURCE RELEASE.  `$4B00` is assembled by
no source file - `GOATARI.s` is `ORG $4B45`, forty-one bytes into `PBDATA` - and
both `pcs-source*.dsk` are the DEVELOPMENT disks: their DOS 3.3 catalogs hold
only `.S`, `.O`, `GPAK.OBJ`, `BITMAPS.OBJ` and the title pictures, with no
deleted entries.  `find_tables()` below is what to point at a GAME disk.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pcsasm as A                                             # noqa: E402
import pcsobj                                                  # noqa: E402
import pcspak as K                                             # noqa: E402

PBBASE = 0x4B00         # LOGIC
WSET = 0x4B18
PBDATA = 0x4B1C
BITMAPS = 0x7B00


# ── the Atari DOS binary-load format ───────────────────────────────────────
def segments(blob):
    """Every (start, bytes) of an Atari binary-load file.

    ⚠ `$FF $FF` heads the file and MAY repeat before any segment - Atari DOS
    allows it and `LOAD`'s `RDDRC` loop re-reads four bytes each time round,
    so a second `$FF $FF` simply reads as a segment from $FFFF to $FFFF.  This
    skips them, which is what every loader in practice does.
    """
    out, i = [], 0
    if len(blob) < 6 or blob[0] != 0xFF or blob[1] != 0xFF:
        return out
    i = 2
    while i + 4 <= len(blob):
        if blob[i] == 0xFF and blob[i + 1] == 0xFF:
            i += 2
            continue
        lo = blob[i] | (blob[i + 1] << 8)
        hi = blob[i + 2] | (blob[i + 3] << 8)
        i += 4
        if hi < lo:
            break
        n = hi - lo + 1
        out.append((lo, bytes(blob[i:i + n])))
        i += n
    return out


def find_tables(blob, minobj=4):
    """⭐ EVERY PCS TABLE IN A BLOB - point it at a disk image.

    A table is a binary-load segment that starts at or spans `$4B00` and whose
    object area walks cleanly.  ⚠ It also finds a table that is simply SITTING
    in a disk's sectors with no file header, because the shipped default is a
    memory image and not a saved file - so the raw walk is tried at every
    offset as well.
    """
    found = []
    for start, data in segments(blob):
        if start <= PBDATA < start + len(data):
            objs = _walk(data, PBDATA - start, minobj)
            if objs:
                found.append(('segment $%04X' % start, PBDATA - start, objs))
    for i in range(len(blob) - 8):
        objs = _walk(blob, i, minobj)
        if objs:
            found.append(('raw', i, objs))
    return found


def _walk(d, i, minobj):
    """The object area at `d[i]`, strictly, or None.

    ⭐ Every constraint here is one `PPAK.s` itself relies on, which is what
    makes this a test rather than a guess: `PBDATA[0]` is the count AND the
    offset to the first record, object 0 is the backdrop B-polygon, a plain
    polygon's record is exactly `3 + 2n` bytes and a library part's is longer.
    """
    if i >= len(d):
        return None
    c = d[i]
    if not minobj <= c <= 127 or i + 1 + c > len(d):
        return None
    lens, off, objs = d[i + 1:i + 1 + c], i + 1 + c, []
    for ln in lens:
        if ln < 9 or off + ln > len(d):
            return None
        r = d[off:off + ln]
        objid, fill, n = r[0], r[1], r[2]
        if objid not in (1, 2, 3) or not 3 <= n <= 63:
            return None
        if objid == 3 and ln < 3 + 2 * n + 16:
            return None
        if objid != 3 and ln != 3 + 2 * n:
            return None
        xs, ys = list(r[3:3 + n]), list(r[3 + n:3 + 2 * n])
        if max(xs) > 200 or max(ys) > 200:
            return None
        objs.append((objid, fill, xs, ys, bytes(r[3 + 2 * n:])))
        off += ln
    if objs[0][0] != 2:                 # object 0 is the backdrop
        return None
    return objs


# ── the re-keying ──────────────────────────────────────────────────────────
_BMP = None


def bitmap_map():
    """⭐ Every template's BITMAP ADDRESS to its index, out of RUN.s's own
    `EQU` chain and the `DA` in each template.  ⚠ Nine parts share a blob and
    reference it with a displacement (`DA ROLLB+30`), so the map is keyed on
    the resolved address and not on the symbol."""
    global _BMP
    if _BMP is None:
        import pcsparts
        e = A.equs('RUN.s')
        _BMP = {}
        for p in pcsparts.parts():
            if not p.lib or not p.bmpref:
                continue
            _BMP[_addr(p.bmpref, e)] = p.index
    return _BMP


def _addr(expr, vals):
    """`ROLLB+30` or `LANEB+10` - a symbol and an optional decimal offset."""
    expr = expr.strip()
    for op in ('+', '-'):
        if op in expr:
            a, b = expr.split(op, 1)
            v = vals[a.strip()]
            d = int(b.strip(), 16) if b.strip().startswith('$') else int(b.strip())
            return v + d if op == '+' else v - d
    return vals[expr]


def rekey(objs):
    """⛔ THE ONE THING THAT CANNOT SURVIVE THE CHANGE OF MACHINE.

    A loaded library record carries a 6502 bitmap pointer at `L[0..1]` and three
    6502 vectors at `L[10..15]`.  The port replaces the first with the TEMPLATE
    INDEX - which is how the part finds its picture - and the second with the
    PART TYPE - which is how it finds its three procs (pcs.md 5b).  ⭐ Both come
    from the bitmap address, exactly, so nothing is guessed and a record whose
    pointer names no template is an error rather than a default.
    """
    import pcsparts
    m = bitmap_map()
    tmpl = pcsparts.parts()
    out, bad = [], []
    for k, (objid, fill, xs, ys, L) in enumerate(objs):
        L = bytearray(L)
        if objid == K.LIBOBJ:
            a = L[0] | (L[1] << 8)
            if a not in m:
                bad.append('object %d: bitmap $%04X names no template' % (k, a))
                continue
            i = m[a]
            kind = pcsobj.kind_of(tmpl[i])
            if kind is None:
                bad.append('object %d: template %s has no port part type'
                           % (k, tmpl[i].name))
                continue
            L[pcsobj.L_TMPL] = i
            L[pcsobj.L_TYPE] = pcsobj.TYPEID[kind]
        o = K.Obj(objid, fill, xs, ys, L)
        out.append(o)
    return out, bad


def load(path, height=240):
    """A `.PB` off disk, as `pcspak.Obj`s the port can scan.

    ⚠ It does NOT move the table: a file authored for a 192-row world loads
    into the top of a 240-row one, which is what pcs.md 3 says and what a
    version byte in the port's own container will record.
    """
    blob = open(path, 'rb').read()
    t = find_tables(blob)
    if not t:
        raise ValueError('%s carries no PCS table' % path)
    where, off, objs = t[0]
    got, bad = rekey(objs)
    for o in got:
        o.align()
    return got, bad, where


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('usage: pcsfile.py FILE [FILE...]   - find and dump any PCS table')
        m = bitmap_map()
        print('%d template bitmap addresses, $%04X..$%04X'
              % (len(m), min(m), max(m)))
        sys.exit(0)
    for p in sys.argv[1:]:
        blob = open(p, 'rb').read()
        t = find_tables(blob)
        if not t:
            print('%-40s no table' % p)
            continue
        for where, off, objs in t[:3]:
            print('%-40s %s at +0x%04X: %d objects' % (p, where, off, len(objs)))
            got, bad = rekey(objs)
            for b in bad:
                print('    ⚠ %s' % b)
            for i, o in enumerate(got[:40]):
                kind = 'BPOLY' if o.objid == 2 else ('POLY' if o.objid == 1
                                                     else 'LIB tmpl %d' % o.L[0])
                print('    %2d %-12s fill %3d  %2d vertices  x %d..%d y %d..%d'
                      % (i, kind, o.fillcolor, o.n, min(o.x), max(o.x),
                         min(o.y), max(o.y)))
