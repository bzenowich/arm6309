#!/usr/bin/env python3
"""Write the demo's stand-in module: an original four-channel ProTracker tune.

    python3 software/demo/tools/mkmod.py out.mod

A STAND-IN, and original. The demo is meant to play a real module; the sandbox
this was written in could not download one, so this is a tune composed for the
purpose, with every sample synthesised here - there is nothing in it anybody
else owns. Replace it by pointing mkdemorom.py at any 4-channel M.K. module.

It is also written to be a FAIR TEST of the 6809 replayer rather than a
flattering one: the parts use arpeggio (0xy), tone portamento (3xx), vibrato
(4xy), volume slide (Axy), set volume (Cxx), note cut (ECx), retrigger (E9x),
sample offset (9xx), portamento up/down (1xx/2xx), pattern break (Dxx),
position jump (Bxx) and set speed (Fxx) - the effects a real module leans on,
and the ones audio/refplayer's trace will catch the port getting wrong.

Channels are Amiga LRRL: 0 lead (L), 1 bass (R), 2 chords (R), 3 drums (L).
"""
import math, random, struct, sys

# ProTracker's finetune-0 row, C-1 .. B-3 (indices 0..35).
NOTES = [856, 808, 762, 720, 678, 640, 604, 570, 538, 508, 480, 453,
         428, 404, 381, 360, 339, 320, 302, 285, 269, 254, 240, 226,
         214, 202, 190, 180, 170, 160, 151, 143, 135, 127, 120, 113]
NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def n(name):
    """'A4' -> table index. Octave 4 is ProTracker's C-2 row (index 12..23)."""
    note, octv = name[:-1], int(name[-1])
    return NAMES.index(note) + (octv - 3) * 12


# ------------------------------------------------------------- samples ----
RATE = 3546895 / 428          # a sample played at C-2 advances at 8287 Hz


def s8(v):
    return max(-128, min(127, int(round(v))))


def wave_pulse(length, duty, amp):
    return [s8(amp if (i + 0.5) / length < duty else -amp) for i in range(length)]


def wave_saw(length, amp):
    # a saw with its top harmonics rolled off by averaging, so the bass is warm
    raw = [amp * (2 * i / length - 1) for i in range(length)]
    return [s8((raw[i - 1] + 2 * raw[i] + raw[(i + 1) % length]) / 4) for i in range(length)]


def kick():
    out, ph = [], 0.0
    for i in range(1800):
        t = i / RATE
        f = 45 + 110 * math.exp(-t * 30)
        ph += 2 * math.pi * f / RATE
        out.append(s8(120 * math.exp(-t * 9) * math.sin(ph)))
    return out


def snare():
    rnd = random.Random(6309)
    out, ph = [], 0.0
    for i in range(2200):
        t = i / RATE
        ph += 2 * math.pi * 185 / RATE
        body = 60 * math.exp(-t * 28) * math.sin(ph)
        noise = 90 * math.exp(-t * 14) * (rnd.random() * 2 - 1)
        out.append(s8(body + noise))
    return out


def hat():
    rnd = random.Random(1983)
    out, prev = [], 0.0
    for i in range(700):
        t = i / RATE
        x = rnd.random() * 2 - 1
        hp = x - prev          # first difference: a crude high-pass
        prev = x
        out.append(s8(70 * math.exp(-t * 60) * hp))
    return out


def even(data):
    return data + [0] * (len(data) & 1)


# name, data, finetune, volume, loop start (bytes), loop length (bytes; 0 = none)
SAMPLES = [
    ("lead pulse", wave_pulse(32, 0.25, 72), 0, 48, 0, 32),
    ("bass saw",   wave_saw(64, 100),        0, 60, 0, 64),
    ("chord sq",   wave_pulse(32, 0.5, 60),  0, 24, 0, 32),
    ("kick",       even(kick()),             0, 64, 0, 0),
    ("snare",      even(snare()),            0, 52, 0, 0),
    ("hat",        even(hat()),              0, 40, 0, 0),
]
LEAD, BASS, CHORD, KICK, SNARE, HAT = 1, 2, 3, 4, 5, 6

# ------------------------------------------------------------ patterns ----
EMPTY = (0, 0, 0, 0)          # sample, note index + 1 (0 = none), effect, param


class Pattern:
    def __init__(self):
        self.rows = [[EMPTY] * 4 for _ in range(64)]

    def put(self, row, ch, smp=0, note=None, eff=0, par=0):
        self.rows[row][ch] = (smp, 0 if note is None else note + 1, eff, par)

    def fx(self, row, ch, eff, par):
        s, nt, _, _ = self.rows[row][ch]
        self.rows[row][ch] = (s, nt, eff, par)

    def bytes(self):
        out = bytearray()
        for r in self.rows:
            for smp, nt, eff, par in r:
                per = NOTES[nt - 1] if nt else 0
                out += bytes([(smp & 0xF0) | (per >> 8), per & 0xFF,
                              ((smp & 0x0F) << 4) | eff, par])
        return bytes(out)


# i - VI - III - VII, then VI - VII - v - i. (root name, arpeggio param)
PROG_A = [("A", 0x37), ("F", 0x47), ("C", 0x47), ("G", 0x47)]
PROG_B = [("F", 0x47), ("G", 0x47), ("E", 0x37), ("A", 0x37)]


def bass(p, prog, staccato=True):
    for bar, (root, _) in enumerate(prog):
        lo = n(root + "3") if n(root + "3") >= 0 else n(root + "4")
        for k in range(8):
            r = bar * 16 + k * 2
            note = lo if k % 2 == 0 else lo + 12
            p.put(r, 1, BASS, note)
            if staccato:
                p.fx(r, 1, 0xE, 0xC1)          # ECx: cut after one tick


def chords(p, prog, vol=0x18):
    for bar, (root, arp) in enumerate(prog):
        base = n(root + "4")
        p.put(bar * 16, 2, CHORD, base, 0xC, vol)
        for k in range(1, 16):
            p.fx(bar * 16 + k, 2, 0x0, arp)    # 0xy is per row, so every row


def drums(p, fill=False):
    for bar in range(4):
        b = bar * 16
        p.put(b + 0, 3, KICK, n("C4"))
        p.put(b + 2, 3, HAT, n("C5"), 0xC, 0x20)
        p.put(b + 4, 3, SNARE, n("C4"))
        p.put(b + 6, 3, HAT, n("C5"), 0xC, 0x18)
        p.put(b + 8, 3, KICK, n("C4"))
        p.put(b + 10, 3, KICK, n("C4"), 0xC, 0x30)
        p.put(b + 12, 3, SNARE, n("C4"), 0x9, 0x02)   # 9xx: start 512 bytes in
        p.put(b + 14, 3, HAT, n("C5"))
    if fill:
        for r in range(56, 64):
            p.put(r, 3, SNARE, n("C4"), 0xE, 0x93 if r < 60 else 0x92)  # E9x


def melody(p, notes, ch=0, smp=LEAD):
    """notes: (name or None, rows, effect, param) - a held note gets its effect
    on the rows after the first."""
    r = 0
    for name, length, eff, par in notes:
        if name is not None:
            if eff == 0x3:
                p.put(r, ch, 0, n(name), 0x3, par)     # slide to it, no retrigger
            else:
                p.put(r, ch, smp, n(name))
            for k in range(1, length):
                if eff and eff != 0x3:
                    p.fx(r + k, ch, eff, par)
                elif eff == 0x3:
                    p.fx(r + k, ch, 0x3, 0)
        r += length
    assert r == 64, r


MEL_A = [("A4", 8, 0x4, 0x34), ("E5", 4, 0, 0), ("A5", 4, 0, 0),
         ("G5", 6, 0x4, 0x44), ("F5", 2, 0, 0), ("E5", 4, 0, 0), ("C5", 4, 0, 0),
         ("D5", 4, 0, 0), ("E5", 4, 0, 0), ("G5", 8, 0x4, 0x46),
         ("F5", 4, 0, 0), ("E5", 4, 0, 0), ("D5", 4, 0, 0), ("E5", 4, 0x3, 0x08)]
MEL_B = [("C5", 4, 0, 0), ("F5", 4, 0, 0), ("A5", 8, 0x4, 0x44),
         ("B5", 4, 0, 0), ("A5", 4, 0, 0), ("G5", 8, 0x4, 0x44),
         ("G5", 4, 0, 0), ("E5", 4, 0, 0), ("B4", 8, 0x4, 0x34),
         ("C5", 4, 0, 0), ("B4", 4, 0, 0), ("A4", 8, 0xA, 0x03)]
# the second half of A an octave lower, sliding
MEL_C = [("A4", 4, 0, 0), ("C5", 4, 0, 0), ("E5", 8, 0x4, 0x56),
         ("D5", 4, 0, 0), ("C5", 4, 0, 0), ("A4", 8, 0x3, 0x06),
         ("G4", 8, 0x4, 0x34), ("C5", 8, 0x3, 0x0C),
         ("B4", 4, 0, 0), ("D5", 4, 0, 0), ("G5", 8, 0xA, 0x02)]


def build(path):
    pats = []

    intro = Pattern()                              # 0: no lead; the lead slides in
    bass(intro, PROG_A)
    chords(intro, PROG_A, 0x14)
    drums(intro)
    intro.put(0, 0, 0, None, 0xF, 0x06)            # speed 6
    intro.put(1, 0, 0, None, 0xF, 0x7D)            # 125 BPM - a TIMER write
    intro.put(56, 0, LEAD, n("E4"), 0xC, 0x20)
    for r in range(57, 64):
        intro.fx(r, 0, 0x1, 0x02)                  # 1xx: bend up into the tune
    pats.append(intro)

    a = Pattern()                                  # 1
    melody(a, MEL_A); bass(a, PROG_A); chords(a, PROG_A); drums(a)
    pats.append(a)

    b = Pattern()                                  # 2
    melody(b, MEL_B); bass(b, PROG_B); chords(b, PROG_B); drums(b, fill=True)
    pats.append(b)

    c = Pattern()                                  # 3
    melody(c, MEL_C); bass(c, PROG_A, staccato=False); chords(c, PROG_A, 0x1C); drums(c)
    pats.append(c)

    d = Pattern()                                  # 4: breakdown, 32 rows
    bass(d, PROG_B)
    for r in range(0, 32, 4):
        d.put(r, 3, KICK, n("C4"))
    d.put(0, 0, LEAD, n("A5"), 0xC, 0x30)
    for r in range(1, 24):
        d.fx(r, 0, 0x2, 0x01)                      # 2xx: a slow fall
    d.put(24, 0, 0, None, 0xE, 0xC0)               # EC0: cut at tick 0
    d.put(31, 2, 0, None, 0xD, 0x00)               # Dxx: break to the next position
    pats.append(d)

    e = Pattern()                                  # 5: B again, then jump back
    melody(e, MEL_B); bass(e, PROG_B); chords(e, PROG_B); drums(e, fill=True)
    e.put(63, 2, 0, None, 0xB, 0x01)               # Bxx: loop to position 1
    pats.append(e)

    order = [0, 1, 2, 1, 3, 4, 5]

    f = bytearray(b"arm6309 demo".ljust(20, b"\0"))
    for i in range(31):
        if i < len(SAMPLES):
            name, data, ft, vol, ls, ll = SAMPLES[i]
            raw = bytes((v & 0xFF) for v in data)
            f += name.encode().ljust(22, b"\0") + struct.pack(">H", len(raw) // 2)
            f += bytes([ft, vol])
            if ll:
                f += struct.pack(">HH", ls // 2, ll // 2)
            else:
                f += struct.pack(">HH", 0, 1)
        else:
            f += b"\0" * 22 + struct.pack(">HBBHH", 0, 0, 0, 0, 1)
    f += bytes([len(order), 127]) + bytes(order + [0] * (128 - len(order))) + b"M.K."
    for p in pats:
        f += p.bytes()
    for _, data, *_ in SAMPLES:
        f += bytes((v & 0xFF) for v in data)
    open(path, "wb").write(bytes(f))
    return len(f)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "demo.mod"
    print(f"wrote {out}: {build(out)} bytes")
