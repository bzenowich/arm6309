#!/usr/bin/env python3
"""pcsasm.py - read Bill Budge's 6502 sources as DATA.

`reference/pcs/` holds Pinball Construction Set (Atari 800, 1983) under the MIT
licence.  The port in nitros9's level2/arm6309/cmds/pcs.asm claims to *be* that
program rather than to resemble it, and the whole of that claim rests on taking
the tables, the artwork and the physics constants from the original instead of
redrawing or re-deriving them.  This module is what takes them.

It is a reader for exactly the three directives those files use for data --

    LABEL HEX 0011,22 33        bytes, commas and spaces ignored
          HEX 4455              a continuation line: no label, same block
    LABEL DA  SYMBOL            two bytes, little-endian, of a SYMBOL's value
    LABEL EQU SYMBOL+$48        an assemble-time constant

-- and nothing else.  It is not an assembler and must never become one: the
moment it needs to understand an instruction, the thing being asked of it is a
job for the reader, not for a parser.

⚠ EQU VALUES ARE ATARI ADDRESSES AND MEAN NOTHING HERE.  They are resolved for
one purpose only: BITMAPS.OBJ is a flat blob whose shapes are delimited by the
EQU chain at RUN.s:100-118 (`LFLIPB EQU LAUNCHERB+$48`), so the DIFFERENCES
between those addresses are the shape lengths.  Nothing else may use them.
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PCSDIR = os.path.join(ROOT, 'reference', 'pcs')

# A source line is `[LABEL] MNEMONIC OPERAND [;comment]`, except that a `*` in
# column 1 is a whole-line comment.  A label is in column 1; anything a
# directive needs is separated by whitespace.
_LINE = re.compile(r'^(?P<label>[A-Za-z0-9_.]*)\s+(?P<op>[A-Za-z]+)(?:\s+(?P<arg>[^;]*))?')

_cache = {}


def load(name):
    """The lines of one source file, comments and blanks kept (line numbers matter)."""
    if name not in _cache:
        path = os.path.join(PCSDIR, name)
        with open(path, 'r', encoding='latin-1') as f:
            _cache[name] = f.read().split('\n')
    return _cache[name]


def _parse(line):
    """(label, op, arg) or None.  `*` in column 1 is a comment, as is a blank line."""
    if not line or line.startswith('*'):
        return None
    m = _LINE.match(line)
    if not m:
        return None
    return m.group('label'), m.group('op').upper(), (m.group('arg') or '').strip()


def _hexbytes(arg):
    """`0011,22 33` -> b'\\x00\\x11\\x22\\x33'.  ⚠ An odd digit count is a typo in
    the source, not something to pad silently -- it raises."""
    digits = re.sub(r'[\s,]', '', arg)
    if len(digits) % 2:
        raise ValueError('HEX operand has an odd digit count: %r' % arg)
    return bytes.fromhex(digits)


def block(name, label):
    """The bytes of the data block starting at `label`.

    The block is the labelled line plus every following UNLABELLED HEX/DA line.
    ⛔ It stops at the next label, at any other mnemonic, and at a `*` comment --
    which is how every table in these files is in fact terminated, and which is
    what stops a block running on into the code after it.

    `DA SYMBOL` contributes two bytes of that symbol's resolved value; in the
    tables this module reads, DA is only ever used for pointer tables whose
    STRUCTURE matters and whose values do not, so a caller normally wants
    `block_syms` instead.
    """
    return b''.join(chunk for _, chunk in _block_parts(name, label))


def block_syms(name, label):
    """Like `block`, but returns a list of the DA operands as written.

    This is what reads a pointer table -- `ICONS DA HAND / DA POINTER / ...` --
    where the answer wanted is the list of NAMES, because the addresses are the
    Atari's and the names are what this port keys its art by.
    """
    out = []
    for kind, chunk in _block_parts(name, label):
        if kind == 'DA':
            out.append(chunk)
    return out


def _block_parts(name, label):
    lines = load(name)
    start = None
    for i, line in enumerate(lines):
        p = _parse(line)
        if p and p[0] == label and p[1] in ('HEX', 'DA'):
            start = i
            break
    if start is None:
        raise KeyError('%s: no data block labelled %r' % (name, label))

    parts = []
    for i in range(start, len(lines)):
        p = _parse(lines[i])
        if p is None:
            break
        lab, op, arg = p
        if i > start and lab:
            break
        if op == 'HEX':
            parts.append(('HEX', _hexbytes(arg)))
        elif op == 'DA':
            parts.append(('DA', arg.strip()))
        else:
            break
    return parts


def blocks_from(name, first, count):
    """`count` successive labelled data blocks, in SOURCE ORDER, from `first`.

    ⭐ This is how the 43 part templates are read, and it has to be positional
    rather than by name: `EDIT.s`'s OBJADDRLO calls them POLY..MGNT while
    `RUN.s` labels four of them differently (LFLIP2/LFLIPPER2,
    RFLIP2/RFLIPPER2, SPIN/SPIN1, MGNT/MAG1), because EDIT.s does not reference
    the labels at all -- it computes every template's address by adding OBJLEN
    to the one before (EDIT.s:160-206).  Position is the only thing the two
    files actually agree on, so position is what this reads, and `pcsparts`
    checks the EQU chain's deltas against OBJLEN to prove the agreement.

    Returns [(label, line_number, [(kind, chunk), ...]), ...].
    """
    lines = load(name)
    start = None
    for i, line in enumerate(lines):
        p = _parse(line)
        if p and p[0] == first and p[1] in ('HEX', 'DA'):
            start = i
            break
    if start is None:
        raise KeyError('%s: no data block labelled %r' % (name, first))

    out = []
    cur = None
    for i in range(start, len(lines)):
        p = _parse(lines[i])
        if p is None:
            continue                    # a `*` separator between blocks
        lab, op, arg = p
        if op not in ('HEX', 'DA'):
            break                       # code: the run of templates has ended
        if lab:
            if len(out) == count:
                break
            cur = (lab, i + 1, [])
            out.append(cur)
        if cur is None:
            continue
        cur[2].append(('HEX', _hexbytes(arg)) if op == 'HEX' else ('DA', arg.strip()))
    if len(out) != count:
        raise ValueError('%s: wanted %d blocks from %s, found %d'
                         % (name, count, first, len(out)))
    return out


def equs(name):
    """{symbol: value} for every EQU in one file, resolved in source order.

    ⚠ Deliberately one pass and forward-referencing is an error.  These files
    were written for a two-pass assembler, but every EQU chain this module cares
    about is defined before use, and a symbol that resolves to None is a louder
    failure than a symbol that silently resolves to zero.
    """
    vals = {}
    for line in load(name):
        p = _parse(line)
        if not p:
            continue
        lab, op, arg = p
        if op != 'EQU' or not lab:
            continue
        v = _value(arg, vals)
        if v is not None:
            vals[lab] = v
    return vals


# ⛔ THE IDENTIFIER ALTERNATIVE MUST COME FIRST, and hex must be `$`-prefixed.
# Written the other way round -- `\$?[0-9A-Fa-f]+` leading -- the symbol BITMAPS
# matches the HEX branch as the single digit `B`, the rest of the name is left
# over, and `LAUNCHERB EQU BITMAPS` silently resolves to nothing.  Every symbol
# in these files whose name begins with A-F is exposed to that: BMP1B, CATCH1B,
# DROP1B, FONT, EFFECTS.  It cost one debugging round here, and it is the same
# shape as CLAUDE.md's `//`-containing-`/*`: an alternation whose order decides
# the answer.
_TERM = re.compile(r'([+-]?)\s*(\$[0-9A-Fa-f]+|[A-Za-z_][A-Za-z0-9_]*|[0-9]+)')


def _value(expr, vals):
    """`LAUNCHERB+$48` -> an int, or None if a term is unknown.

    Handles the `<` and `>` low/high-byte prefixes the sources use in operands,
    though no EQU this module reads needs them.
    """
    expr = expr.split(';')[0].strip()
    if not expr:
        return None
    if expr[0] in '<>':
        inner = _value(expr[1:], vals)
        if inner is None:
            return None
        return inner & 0xFF if expr[0] == '<' else (inner >> 8) & 0xFF
    total, pos = 0, 0
    seen = False
    for m in _TERM.finditer(expr):
        if m.start() != pos:
            return None
        pos = m.end()
        sign, term = m.group(1), m.group(2)
        if term.startswith('$'):
            v = int(term[1:], 16)
        elif re.fullmatch(r'[0-9]+', term):
            v = int(term)
        elif term in vals:
            v = vals[term]
        else:
            return None
        total += -v if sign == '-' else v
        seen = True
    if not seen or pos != len(expr):
        return None
    return total


def blob(name):
    """A binary file from reference/pcs/ (BITMAPS.OBJ)."""
    with open(os.path.join(PCSDIR, name), 'rb') as f:
        return f.read()
