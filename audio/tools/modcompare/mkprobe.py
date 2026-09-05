#!/usr/bin/env python3
"""Generate single-effect probe modules for the A/B ladder.

audio/docs/modplayer.md §9 argues for a corpus where each module fails loudly for one
specific reason. Real-world test modules (ode2ptk.mod and friends) are the other
end of the ladder: they are deliberately antagonistic, so a divergence there
could be any of a dozen things. These probes sit at the bottom -- one effect
each, one channel active, a sustaining looped sample -- so a disagreement with
another implementation names the effect that caused it.
"""
import struct, sys, os

NOTES = [856,808,762,720,678,640,604,570,538,508,480,453,
         428,404,381,360,339,320,302,285,269,254,240,226,
         214,202,190,180,170,160,151,143,135,127,120,113]

def be16(v): return struct.pack('>H', v)

def cell(smp=0, per=0, eff=0, par=0):
    return bytes([(smp & 0xF0) | ((per >> 8) & 0x0F), per & 0xFF,
                  ((smp & 0x0F) << 4) | (eff & 0x0F), par & 0xFF])

def build(path, rows, samples=None, songlen=1):
    """rows: list of 64 entries, each a list of 4 (smp,per,eff,par) tuples."""
    if samples is None:
        # 1: 64-byte saw, loops whole; 2: 64-byte square, one-shot
        saw = bytes([(i * 4) & 0xFF for i in range(64)])
        sq  = bytes([0x60] * 32 + [0xA0] * 32)
        samples = [("saw-loop", saw, 0, 0, 32, 64), ("sq-oneshot", sq, 0, 0, 1, 64)]
    f = bytearray(b'probe'.ljust(20, b'\0'))
    for i in range(31):
        if i < len(samples):
            name, data, ft, ro, rl, vol = samples[i]
            f += name.encode().ljust(22, b'\0') + be16(len(data) // 2) \
               + bytes([ft & 0x0F, vol]) + be16(ro) + be16(rl)
        else:
            f += b'\0' * 22 + be16(0) + bytes([0, 0]) + be16(0) + be16(1)
    f += bytes([songlen, 127]) + bytes(list(range(songlen)) + [0] * (128 - songlen)) + b'M.K.'
    for p in range(songlen):
        for r in range(64):
            spec = rows[p * 64 + r] if p * 64 + r < len(rows) else [(0, 0, 0, 0)] * 4
            for c in range(4):
                f += cell(*spec[c])
    for _, data, *_ in samples:
        f += data
    open(path, 'wb').write(bytes(f))
    return path

def blank(): return [(0, 0, 0, 0)] * 4

def probes(outdir):
    os.makedirs(outdir, exist_ok=True)
    made = []

    def emit(name, rowfn, songlen=1, samples=None):
        rows = []
        for r in range(64 * songlen):
            cs = blank()
            rowfn(r, cs)
            rows.append(cs)
        made.append((name, build(os.path.join(outdir, name + ".mod"), rows,
                                 samples=samples, songlen=songlen)))

    # baseline: a note every 8 rows, no effects at all
    emit("00_notes",   lambda r, c: c.__setitem__(0, (1, NOTES[(r // 8) % 24 + 12], 0, 0)) if r % 8 == 0 else None)
    # one-shot sample: must go silent, not buzz (modplayer.md §4.2)
    emit("01_oneshot", lambda r, c: c.__setitem__(0, (2, NOTES[12], 0, 0)) if r % 16 == 0 else None)
    # Cxx set volume
    emit("02_setvol",  lambda r, c: c.__setitem__(0, (1, NOTES[12], 0, 0) if r == 0 else (0, 0, 0xC, max(0, 64 - r))) )
    # Axy volume slide down then up
    emit("03_volslide", lambda r, c: c.__setitem__(0,
        (1, NOTES[12], 0, 0) if r == 0 else (0, 0, 0xA, 0x02 if r < 32 else 0x20)))
    # 1xx / 2xx portamento
    emit("04_porta",   lambda r, c: c.__setitem__(0,
        (1, NOTES[18], 0, 0) if r == 0 else (0, 0, 1 if r < 32 else 2, 0x08)))
    # 3xx tone portamento toward a target
    emit("05_toneporta", lambda r, c: c.__setitem__(0,
        (1, NOTES[24], 0, 0) if r == 0 else ((0, NOTES[12], 3, 0x10) if r == 8 else (0, 0, 3, 0))))
    # 4xy vibrato
    emit("06_vibrato", lambda r, c: c.__setitem__(0,
        (1, NOTES[18], 0, 0) if r == 0 else (0, 0, 4, 0x48)))
    # 7xy tremolo
    emit("07_tremolo", lambda r, c: c.__setitem__(0,
        (1, NOTES[18], 0, 0) if r == 0 else (0, 0, 7, 0x48)))
    # 0xy arpeggio
    emit("08_arpeggio", lambda r, c: c.__setitem__(0,
        (1, NOTES[18], 0, 0) if r == 0 else (0, 0, 0, 0x47)))
    # 9xx sample offset
    emit("09_offset",  lambda r, c: c.__setitem__(0, (1, NOTES[12], 9, 0x00)) if r % 8 == 0 else None)
    # ECx note cut / EDx note delay / E9x retrigger
    emit("10_ecut",    lambda r, c: c.__setitem__(0, (1, NOTES[12], 0xE, 0xC3)) if r % 4 == 0 else None)
    emit("11_edelay",  lambda r, c: c.__setitem__(0, (1, NOTES[12], 0xE, 0xD3)) if r % 4 == 0 else None)
    emit("12_eretrig", lambda r, c: c.__setitem__(0, (1, NOTES[12], 0xE, 0x93)) if r % 8 == 0 else None)
    # Fxx speed and tempo
    emit("13_tempo",   lambda r, c: (c.__setitem__(0, (1, NOTES[12 + (r // 8) % 12], 0, 0)),
                                     c.__setitem__(1, (0, 0, 0xF, [0x06,0x03,0x60,0x7D,0x2D,0x06,0x04,0x50][(r//8)%8]))) if r % 8 == 0 else None)
    # E0x LED filter -- the only effect that reaches hardware other than a
    # channel register, and the only probe that exercises the filter ORDER.
    # A sustained note, filter off for 16 rows then on for 16, repeatedly: the
    # comparison is against libopenmpt's own a500 LED behaviour, so a wrong
    # number of poles shows up as a spectral divergence and nothing else moves.
    emit("15_ledfilter", lambda r, c: c.__setitem__(0,
        (1, NOTES[12], 0, 0) if r == 0 else
        ((0, 0, 0xE, 0x00) if (r // 16) % 2 else (0, 0, 0xE, 0x01))))
    # 3xx with the speed changed on a NOTE-LESS row. ProTracker's
    # mt_TonePortamento takes a new speed from any non-zero parameter, note or
    # not, and 05_toneporta never varies the parameter without a note -- which
    # is exactly why a player that only reads it on a row carrying a note
    # passed the whole ladder while sliding at the first speed forever.
    emit("16_tpspeed", lambda r, c: c.__setitem__(0,
        (1, NOTES[24], 0, 0) if r == 0 else
        ((0, NOTES[12], 3, 0x01) if r == 8 else
         ((0, 0, 3, 0x10) if r >= 16 else (0, 0, 3, 0)))))
    # all four channels at once -- checks hard panning end to end
    emit("14_fourchan", lambda r, c: [c.__setitem__(k, (1, NOTES[12 + (r // 4 + k * 3) % 12], 0, 0))
                                      for k in range(4)] if r % 4 == 0 else None)

    # ---- the ProTracker corners the first fifteen probes never reach --------
    #
    # Every one of these was a real divergence that the ladder scored as "ok"
    # because nothing in it varied the thing that was wrong. They are cheap and
    # they are the difference between a passing ladder and a meaningful one.

    # EC0 cuts at TICK 0, from mt_CheckMoreEffects. A player that only runs the
    # E dispatcher on ticks >= 1 never cuts at all, and this probe is the
    # difference between silence and a note held forever.
    emit("17_ec0",    lambda r, c: c.__setitem__(0, (1, NOTES[12], 0xE, 0xC0))
                                   if r % 4 == 0 else None)
    # mt_RetrigNote also runs at tick 0, and on a row with no note that is a
    # retrigger -- tick 0 divides by x with remainder 0.
    emit("18_e9noteless", lambda r, c: c.__setitem__(0,
        (1, NOTES[12], 0, 0) if r == 0 else (0, 0, 0xE, 0x93)))
    # EDx x EEx: the delayed note fires once per REPEAT of the row
    # (modplayer.md §10.10), which needs the delay re-armed on each repeat.
    emit("19_edelay_ee", lambda r, c: (c.__setitem__(0, (1, NOTES[12], 0xE, 0xD3)),
                                       c.__setitem__(1, (0, 0, 0xE, 0xE3)))
                                      if r % 4 == 0 else None)
    # mt_SampleOffset takes the parameter into memory whenever the command is
    # SEEN, note or not. The sample is deliberately two different sounds spliced
    # at the offset, so playing from 0 instead of from 0x400 is unmistakable --
    # a periodic waveform would score the same either way and prove nothing.
    emit("20_offsetmem", lambda r, c: c.__setitem__(0,
            (0, 0, 9, 0x04) if r % 8 == 0 else
            ((1, NOTES[12], 9, 0x00) if r % 8 == 1 else (0, 0, 0, 0))),
         samples=[("split", bytes([(abs(512 - i) // 4) & 0x7F for i in range(1024)]
                                + [(i * 29) & 0xFF for i in range(3072)]), 0, 0, 2048, 64),
                  ("sq-oneshot", bytes([0x60] * 32 + [0xA0] * 32), 0, 0, 1, 64)])
    # An E6x loop-back sharing its row with a Dxx. Leaving the break armed
    # teleports one row after the loop, which is not a subtle difference.
    def _loopbreak(r, c):
        if r == 0:        c[0] = (1, NOTES[12], 0xE, 0x60)
        elif r == 4:      c[0] = (1, NOTES[16], 0xE, 0x62); c[1] = (0, 0, 0xD, 0x20)
        elif r % 2 == 0:  c[0] = (1, NOTES[12 + (r // 2) % 12], 0, 0)
    emit("21_loopbreak", _loopbreak)
    return made

if __name__ == "__main__":
    for name, path in probes(sys.argv[1] if len(sys.argv) > 1 else "probes"):
        print(f"  {name:14s} {os.path.getsize(path):6d} bytes")
