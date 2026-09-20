#!/usr/bin/env python3
"""ps2check.py - the SECOND implementation of PS2_SCRIPT's encoding.

software/demo/emu/ps2script.h turns a script into PS/2 traffic in C, inside
the emulator, and hands it to the line-level device model.  This file turns
the same script into the same traffic in Python, from io/ps2/docs/ps2.md
11.1 and 11.3 - its own scan code table, its own splitting, its own sign
encoding - and every subcommand below is a comparison of the two.

⛔ ONE IMPLEMENTATION AGREEING WITH ITSELF IS NOT EVIDENCE, which is why the
recorded stream is never compared against the thing that produced it.  And
because a comparison that cannot fail is worse than none, `--mutate` on the
comparing subcommands corrupts one byte of the expectation and REQUIRES the
comparison to fail; run-ps2script.sh spends a claim on each.

Subcommands (each exits 0 for pass, 1 for fail, and says why):

  bytes SCRIPT PORT        print how many bytes this script sends on that
                           port (0 keyboard, 1 mouse) - the argument
                           run-ps2script.sh gives `ps2tst`
  match SCRIPT DUMP        PS2_SCRIPT_DUMP's stream is the independent one,
                           bytes AND nominal times
  delivered SCRIPT PS2TXT  a run's ps2.txt carries exactly that byte stream,
                           per port, in order (times are the machine's)
  console SCRIPT CONSOLE   ⭐ and so does what ps2tst ECHOED off the card -
                           the bytes that made it through the wire, the
                           card's '193/'595 and the one-byte latch
  pointer PS2TXT           ⭐ the pointer rebuilt from the bytes the GUEST
                           read equals the script's, and it moved
  split SCRIPT DUMP        the RECORDED packets are inside the 9-bit field,
                           set no overflow bit, and land exactly where the
                           script said at every step - which is what an
                           encoder that truncates instead of splitting gets
                           wrong, silently
  nobuttons PS2TXT         ⛔ the negative control: no button ever changed
  silent PS2TXT            ⛔ and the emptier one: no traffic at all
"""
import contextlib
import io
import re
import sys

# --------------------------------------------------------------- scan code set 2
# ps2.md 11.1.  Written out here from the specification rather than shared
# with the C table: a typo in either one is then a failed claim.
BASE = {
    "a": 0x1C, "b": 0x32, "c": 0x21, "d": 0x23, "e": 0x24, "f": 0x2B, "g": 0x34,
    "h": 0x33, "i": 0x43, "j": 0x3B, "k": 0x42, "l": 0x4B, "m": 0x3A, "n": 0x31,
    "o": 0x44, "p": 0x4D, "q": 0x15, "r": 0x2D, "s": 0x1B, "t": 0x2C, "u": 0x3C,
    "v": 0x2A, "w": 0x1D, "x": 0x22, "y": 0x35, "z": 0x1A,
    "1": 0x16, "2": 0x1E, "3": 0x26, "4": 0x25, "5": 0x2E,
    "6": 0x36, "7": 0x3D, "8": 0x3E, "9": 0x46, "0": 0x45,
    "`": 0x0E, "-": 0x4E, "=": 0x55, "\\": 0x5D, "[": 0x54, "]": 0x5B,
    ";": 0x4C, "'": 0x52, ",": 0x41, ".": 0x49, "/": 0x4A,
    "space": 0x29, "tab": 0x0D, "backspace": 0x66, "enter": 0x5A, "esc": 0x76,
    "capslock": 0x58, "numlock": 0x77, "scrolllock": 0x7E,
    "lshift": 0x12, "rshift": 0x59, "lctrl": 0x14, "lalt": 0x11,
    "f1": 0x05, "f2": 0x06, "f3": 0x04, "f4": 0x0C, "f5": 0x03, "f6": 0x0B,
    "f7": 0x83, "f8": 0x0A, "f9": 0x01, "f10": 0x09, "f11": 0x78, "f12": 0x07,
    "kp0": 0x70, "kp1": 0x69, "kp2": 0x72, "kp3": 0x7A, "kp4": 0x6B,
    "kp5": 0x73, "kp6": 0x74, "kp7": 0x6C, "kp8": 0x75, "kp9": 0x7D,
    "kp.": 0x71, "kp+": 0x79, "kp-": 0x7B, "kp*": 0x7C,
}
# the E0 set
EXT = {
    "rctrl": 0x14, "ralt": 0x11, "lgui": 0x1F, "rgui": 0x27, "apps": 0x2F,
    "insert": 0x70, "home": 0x6C, "pageup": 0x7D, "delete": 0x71,
    "end": 0x69, "pagedown": 0x7A,
    "up": 0x75, "left": 0x6B, "down": 0x72, "right": 0x74,
    "kp/": 0x4A, "kpenter": 0x5A,
}
ALIAS = {
    "grave": "`", "minus": "-", "equal": "=", "backslash": "\\",
    "lbracket": "[", "rbracket": "]", "semicolon": ";", "quote": "'",
    "comma": ",", "period": ".", "slash": "/",
    "bksp": "backspace", "return": "enter", "escape": "esc",
    "shift": "lshift", "ctrl": "lctrl", "alt": "lalt", "menu": "apps",
    "pgup": "pageup", "pgdn": "pagedown", "del": "delete", "prtsc": "printscreen",
}
PAUSE = [0xE1, 0x14, 0x77, 0xE1, 0xF0, 0x14, 0xF0, 0x77]
PRTSC_MAKE = [0xE0, 0x12, 0xE0, 0x7C]
PRTSC_BREAK = [0xE0, 0xF0, 0x7C, 0xE0, 0xF0, 0x12]

SHIFTED = {
    "~": "`", "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6",
    "&": "7", "*": "8", "(": "9", ")": "0", "_": "-", "+": "=", "|": "\\",
    "{": "[", "}": "]", ":": ";", '"': "'", "<": ",", ">": ".", "?": "/",
}


def keybytes(name, make):
    """The bytes for one key.  ps2.md 11.1: F0 before a break, E0 before an
    extended key (and so E0 F0 xx for an extended break)."""
    name = ALIAS.get(name, name)
    if name == "pause":
        return list(PAUSE) if make else []          # no break sequence at all
    if name == "printscreen":
        return list(PRTSC_MAKE) if make else list(PRTSC_BREAK)
    if name in BASE:
        return ([0xF0] if not make else []) + [BASE[name]]
    if name in EXT:
        return [0xE0] + ([0xF0] if not make else []) + [EXT[name]]
    raise ValueError("unknown key %r" % name)


def charkey(c):
    """(name, shifted) for a printable character, or None."""
    if c == "\n" or c == "\r":
        return ("enter", False)
    if c == "\t":
        return ("tab", False)
    if c == " ":
        return ("space", False)
    if c.isupper():
        return (c.lower(), True)
    if c in SHIFTED:
        return (SHIFTED[c], True)
    if c in BASE:
        return (c, False)
    return None


# ------------------------------------------------------------------- the encoder
class Ev(object):
    __slots__ = ("t", "port", "b", "kind", "name", "x", "y", "btn")

    def __init__(self, t, port, b, kind, name, x, y, btn):
        self.t, self.port, self.b = t, port, list(b)
        self.kind, self.name = kind, name
        self.x, self.y, self.btn = x, y, btn

    def hexs(self):
        return " ".join("%02X" % v for v in self.b)


def split_axis(d):
    """9-bit field, ps2.md 11.3, and ps2script.h's rule: steps of at most
    +-255 until the remainder is nothing."""
    out = []
    while d:
        s = 255 if d > 255 else (-255 if d < -255 else d)
        out.append(s)
        d -= s
    return out


def strip_comment(line):
    """⚠ A `#` or `;` inside a quoted string is not a comment.  One pass,
    quote-aware, escapes honoured - the same rule ps2script.h applies."""
    q, i = False, 0
    while i < len(line):
        c = line[i]
        if c == "\\":
            i += 2
            continue
        if c == '"':
            q = not q
        elif not q and c in "#;":
            return line[:i]
        i += 1
    return line


def parse(path):
    """The script -> the events it encodes to.  Times in seconds."""
    t, x, y, btn = 0.0, 0, 0, 0
    rate, gap, hold = 1.0 / 60.0, 0.050, 0.030
    origin = [None]
    evs = []

    def packet(dx_screen, dy_screen):
        # ps2.md 11.3: Y is positive UPWARD, the script is screen coordinates
        dy = -dy_screen
        b0 = 0x08 | (btn & 7)
        if dx_screen < 0:
            b0 |= 0x10
        if dy < 0:
            b0 |= 0x20
        evs.append(Ev(t, 1, [b0, dx_screen & 0xFF, dy & 0xFF],
                      "move" if (dx_screen or dy) else "button", "", x, y, btn))

    def mark():
        if origin[0] is None:
            origin[0] = (x, y)

    def key(name, make):
        b = keybytes(name, make)
        if b:
            evs.append(Ev(t, 0, b, "make" if make else "break", ALIAS.get(name, name),
                          x, y, btn))

    def chord(spec, make):
        # ⚠ `kp+` is a key name with a `+` in it: a whole name wins
        try:
            keybytes(spec, make)
            key(spec, make)
            return
        except ValueError:
            pass
        parts = [p for p in spec.split("+") if p]
        if not parts:
            raise ValueError("empty key name")
        if len(parts) == 1:
            key(parts[0], make)
            return
        for nm in (parts if make else list(reversed(parts))):
            key(nm, make)

    for ln, raw in enumerate(open(path), 1):
        line = strip_comment(raw).strip()
        if not line:
            continue
        w = line.split()
        if w[0] == "at":
            t = float(w[1])
            w = w[2:]
        elif w[0].startswith("+"):
            t += float(w[0][1:])
            w = w[1:]
        if not w:
            continue
        op = w[0]
        try:
            if op == "origin":
                x, y = int(w[1]), int(w[2])
            elif op in ("rate", "gap", "hold"):
                v = float(w[1]) / 1000.0
                if op == "rate":
                    rate = v
                elif op == "gap":
                    gap = v
                else:
                    hold = v
            elif op == "move":
                mark()
                a, b = int(w[2]), int(w[3])
                tx, ty = (a, b) if w[1] == "to" else (x + a, y + b)
                if w[1] not in ("to", "by"):
                    raise ValueError("move %s?" % w[1])
                xs, ys = split_axis(tx - x), split_axis(ty - y)
                n = max(len(xs), len(ys))
                xs += [0] * (n - len(xs))
                ys += [0] * (n - len(ys))
                for i in range(n):
                    x += xs[i]
                    y += ys[i]
                    packet(xs[i], ys[i])
                    if i != n - 1:
                        t += rate
            elif op in ("down", "up", "click"):
                mark()
                mask = {"left": 1, "right": 2, "middle": 4}[w[1]]
                if op == "down":
                    btn |= mask
                    packet(0, 0)
                elif op == "up":
                    btn &= ~mask
                    packet(0, 0)
                else:
                    btn |= mask
                    packet(0, 0)
                    t += gap
                    btn &= ~mask
                    packet(0, 0)
            elif op == "key":
                how, name = w[1], w[2]
                if how in ("press", "down"):
                    chord(name, True)
                elif how in ("release", "up"):
                    chord(name, False)
                elif how == "tap":
                    chord(name, True)
                    t += hold
                    chord(name, False)
                else:
                    raise ValueError("key %s?" % how)
            elif op == "type":
                s = unquote(line[line.index("type") + 4:])
                for i, c in enumerate(s):
                    ck = charkey(c)
                    if ck is None:
                        raise ValueError("no key for %r" % c)
                    nm, sh = ck
                    if sh:
                        key("lshift", True)
                    key(nm, True)
                    t += hold
                    key(nm, False)
                    if sh:
                        key("lshift", False)
                    if i != len(s) - 1:
                        t += hold
            else:
                raise ValueError("what is %r?" % op)
        except (IndexError, KeyError, ValueError) as ex:
            raise SystemExit("FAIL  %s line %d: %s" % (path, ln, ex))
    return evs, (origin[0] or (0, 0))


def unquote(s):
    s = s.strip()
    if not s.startswith('"') or not s.endswith('"') or len(s) < 2:
        raise ValueError("type wants a quoted string")
    out, i, s = [], 1, s
    while i < len(s) - 1:
        c = s[i]
        if c == "\\" and i + 1 < len(s) - 1:
            i += 1
            c = {"n": "\n", "t": "\t", "r": "\r"}.get(s[i], s[i])
        out.append(c)
        i += 1
    return "".join(out)


# ------------------------------------------------------------------ the records
def read_log(path):
    """ps2.txt or a PS2_SCRIPT_DUMP: (ps, tag, fields)."""
    out = []
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        f = line.split()
        if len(f) < 2:
            continue
        out.append((int(f[0]), f[1], f[2:]))
    return out


# where the hex starts in each record: K <kind> <name> ..., M <x> <y> <btn> ...
HEXAT = {"K": 2, "M": 3}


def stream(recs, tag):
    """the bytes of every record with that tag, concatenated, in order"""
    out = []
    for _, t, f in recs:
        if t != tag:
            continue
        out += [int(v, 16) for v in f[HEXAT[t]:]]
    return out


def expected(evs, port):
    out = []
    for e in evs:
        if e.port == port:
            out += e.b
    return out


def hx(b):
    return " ".join("%02X" % v for v in b)


QUIET = [False]


def say(*a):
    if not QUIET[0]:
        print(*a)


def diff(what, got, want):
    """0 if equal; otherwise print where they first part and return 1."""
    if got == want:
        return 0
    if QUIET[0]:
        return 1
    n = min(len(got), len(want))
    i = next((k for k in range(n) if got[k] != want[k]), n)
    print("FAIL  %s: %d bytes, expected %d; first difference at %d" % (what, len(got), len(want), i))
    print("        got  %s" % hx(got[max(0, i - 4):i + 8]))
    print("        want %s" % hx(want[max(0, i - 4):i + 8]))
    return 1


def mutate(b):
    """⛔ corrupt the expectation, so the comparison has to notice"""
    if not b:
        return [0x00]
    b = list(b)
    b[len(b) // 2] ^= 0x01
    return b


# ------------------------------------------------------------------ subcommands
def cmd_bytes(a):
    evs, _ = parse(a[0])
    print(len(expected(evs, int(a[1]))))
    return 0


def cmd_match(a, mut):
    evs, _ = parse(a[0])
    recs = read_log(a[1])
    got = [r for r in recs if r[1] in "KM"]
    if len(got) != len(evs):
        print("FAIL  dump has %d events, the encoder says %d" % (len(got), len(evs)))
        return 1
    rc = 0
    for i, (e, (ps, tag, f)) in enumerate(zip(evs, got)):
        want = mutate(e.b) if (mut and i == len(evs) // 2) else e.b
        if tag not in HEXAT:
            print("FAIL  event %d: unexpected record `%s`" % (i, tag))
            return 1
        b = [int(v, 16) for v in f[HEXAT[tag]:]]
        if tag != ("K" if e.port == 0 else "M"):
            print("FAIL  event %d: port %s, expected %d" % (i, tag, e.port))
            rc = 1
        elif b != want:
            print("FAIL  event %d (%s %s): %s, expected %s" % (i, e.kind, e.name, hx(b), hx(want)))
            rc = 1
        elif abs(ps - e.t * 1e12) > 1e6:        # 1 us: the C side rounds through E cycles
            print("FAIL  event %d: at %.6f s, expected %.6f s" % (i, ps / 1e12, e.t))
            rc = 1
        if e.port == 1 and not mut:
            if int(f[2]) != e.btn:
                print("FAIL  event %d: buttons %s, expected %d" % (i, f[2], e.btn))
                rc = 1
            if (int(f[0]), int(f[1])) != (e.x, e.y):
                print("FAIL  event %d: pointer %s,%s, expected %d,%d" % (i, f[0], f[1], e.x, e.y))
                rc = 1
    return rc


def cmd_delivered(a, mut):
    evs, _ = parse(a[0])
    recs = read_log(a[1])
    rc = 0
    for port, tag in ((0, "K"), (1, "M")):
        want = expected(evs, port)
        if mut:
            want = mutate(want)
        rc |= diff("%s stream" % ("keyboard" if port == 0 else "mouse"), stream(recs, tag), want)
    end = [r for r in recs if r[1] == "E"]
    if not end:
        print("FAIL  ps2.txt has no E line: the run did not finish")
        return 1
    if int(end[-1][2][1]):
        print("FAIL  %s events were never delivered" % end[-1][2][1])
        rc = 1
    return rc


CMDREPLY = {
    # what ps2tst's own commands produce before the script's traffic starts
    "kbd": [0xFA, 0xAA, 0xFA, 0xAB, 0x83, 0xFA],
    "mouse": [0xFA, 0xAA, 0x00, 0xFA, 0xFA, 0xFA],
}


def cmd_console(a, mut):
    """ps2tst prints `kbd: ...` and `mouse: ...`: every byte it read."""
    evs, _ = parse(a[0])
    text = open(a[1], errors="replace").read()
    rc = 0
    for name, port in (("kbd", 0), ("mouse", 1)):
        mm = re.search(r"^%s:((?: [0-9A-F-]{2})+)\s*$" % name, text, re.M)
        if not mm:
            print("FAIL  no `%s:` line in the console" % name)
            rc = 1
            continue
        toks = mm.group(1).split()
        if "--" in toks:
            print("FAIL  %s: ps2tst timed out waiting for a byte: %s" % (name, " ".join(toks)))
            rc = 1
            continue
        got = [int(v, 16) for v in toks]
        want = CMDREPLY[name] + expected(evs, port)
        if mut:
            want = mutate(want)
        rc |= diff("%s echoed by ps2tst" % name, got, want)
    return rc


def cmd_pointer(a):
    recs = read_log(a[0])
    end = [r for r in recs if r[1] == "E"]
    if not end or len(end[-1][2]) < 6:
        print("FAIL  ps2.txt has no E line with both pointers")
        return 1
    _, _, sx, sy, gx, gy = [int(v) for v in end[-1][2][:6]]
    g = [r for r in recs if r[1] == "G"]
    mv = [r for r in recs if r[1] == "M"]
    rc = 0
    if not g:
        print("FAIL  the guest read no mouse packet at all")
        return 1
    if (sx, sy) != (gx, gy):
        print("FAIL  the script's pointer is %d,%d and the machine's is %d,%d" % (sx, sy, gx, gy))
        rc = 1
    lg = [int(v) for v in g[-1][2][:2]]
    if lg != [gx, gy]:
        print("FAIL  the last G line says %s and E says %d,%d" % (lg, gx, gy))
        rc = 1
    # ⛔ and it must have MOVED, or "they agree" is satisfied by nothing happening
    if len(g) < 2 or all(r[2][:2] == g[0][2][:2] for r in g):
        print("FAIL  the guest's pointer never moved (%d G lines)" % len(g))
        rc = 1
    if len(g) != len(mv):
        print("FAIL  %d packets sent, %d read by the guest" % (len(mv), len(g)))
        rc = 1
    if not rc:
        print("      script %d,%d == machine %d,%d over %d packets" % (sx, sy, gx, gy, len(g)))
    return rc


def cmd_split(a):
    """⛔ THE SPLITTING, checked against the OTHER implementation's packets.

    It reads the C encoder's own bytes out of the dump and only the target
    positions out of its own parse: every packet inside the 9-bit field, no
    overflow bit, b3 set, and the accumulated deltas landing exactly where
    the script said at every step.  An encoder that truncated an oversized
    move instead of splitting it has the right FIRST packet and the wrong
    total, which is the failure mode that is otherwise silent."""
    evs, origin = parse(a[0])
    recs = read_log(a[1])
    got = [r for r in recs if r[1] == "M"]
    want = [e for e in evs if e.port == 1]
    if len(got) != len(want):
        print("FAIL  %d packets recorded, the encoder should have sent %d" % (len(got), len(want)))
        return 1
    x, y = origin
    rc = 0
    for i, (_, _, f) in enumerate(got):
        b = [int(v, 16) for v in f[HEXAT["M"]:]]
        if len(b) != 3:
            print("FAIL  packet %d is %d bytes" % (i, len(b)))
            return 1
        b0, b1, b2 = b
        if b0 & 0xC0:
            print("FAIL  packet %d sets an overflow bit: %s" % (i, hx(b)))
            rc = 1
        if not (b0 & 0x08):
            print("FAIL  packet %d has b3 = 0: %s" % (i, hx(b)))
            rc = 1
        dx = b1 - 256 if (b0 & 0x10) else b1
        dy = b2 - 256 if (b0 & 0x20) else b2
        if not (-255 <= dx <= 255 and -255 <= dy <= 255):
            print("FAIL  packet %d is outside +-255: %d,%d" % (i, dx, dy))
            rc = 1
        x += dx
        y -= dy                          # ps2.md 11.3: Y is positive upward
        if (x, y) != (want[i].x, want[i].y):
            print("FAIL  packet %d lands at %d,%d and the script says %d,%d"
                  % (i, x, y, want[i].x, want[i].y))
            rc = 1
    if not rc:
        print("      %d packets from %d,%d to %d,%d, every step exact" % (len(got), origin[0], origin[1], x, y))
    return rc


def cmd_nobuttons(a):
    recs = read_log(a[0])
    rc, n = 0, 0
    for ps, tag, f in recs:
        if tag != "M":
            continue
        n += 1
        if int(f[2]) != 0:
            print("FAIL  a packet at %d ps carries buttons %s" % (ps, f[2]))
            rc = 1
        if int(f[3], 16) & 7:
            print("FAIL  a packet at %d ps has a button bit set: %s" % (ps, f[3]))
            rc = 1
    if n == 0:
        print("FAIL  no packets at all - the control proves nothing")
        return 1
    if not rc:
        print("      %d packets, not one button bit" % n)
    return rc


def cmd_silent(a):
    recs = read_log(a[0])
    bad = [r for r in recs if r[1] in ("K", "M", "G")]
    if bad:
        print("FAIL  an empty script produced %d events" % len(bad))
        return 1
    end = [r for r in recs if r[1] == "E"]
    if not end or end[-1][2][0] != "0":
        print("FAIL  ps2.txt's E line does not say 0 delivered: %s" % (end[-1][2] if end else None))
        return 1
    print("      no traffic, and E says 0 delivered")
    return 0


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    mut = "--mutate" in argv
    argv = [a for a in argv if a != "--mutate"]
    cmd, a = argv[1], argv[2:]
    if mut:
        # ⛔ the comparison is required to FAIL on a corrupted expectation, so
        # the answer is inverted here rather than by a `!` in the shell: a
        # negated claim that a missing tool also satisfies proves nothing
        # (CLAUDE.md, "a shell function is invisible to sh -c")
        QUIET[0] = True
        f = {"match": cmd_match, "delivered": cmd_delivered, "console": cmd_console}.get(cmd)
        if not f:
            print("FAIL  --mutate does not apply to %s" % cmd)
            return 2
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            bad = f(a, True)
        if bad:
            print("      ⛔ the mutated stream was caught by `%s`" % cmd)
            return 0
        print("FAIL  `%s` passed a stream with a corrupted byte: it is vacuous" % cmd)
        return 1
    if cmd == "bytes":
        return cmd_bytes(a)
    if cmd == "match":
        return cmd_match(a, mut)
    if cmd == "delivered":
        return cmd_delivered(a, mut)
    if cmd == "console":
        return cmd_console(a, mut)
    if cmd == "pointer":
        return cmd_pointer(a)
    if cmd == "split":
        return cmd_split(a)
    if cmd == "nobuttons":
        return cmd_nobuttons(a)
    if cmd == "silent":
        return cmd_silent(a)
    print("FAIL  no such subcommand: %s" % cmd)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
