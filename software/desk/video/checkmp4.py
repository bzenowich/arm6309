#!/usr/bin/env python3
"""checkmp4.py FILE [SECONDS] - is this a COMPLETE MP4, or one still being written?

⛔ WHY THIS EXISTS.  On 2026-09-17 a 20 MB file with a plausible timestamp was
reported as the finished demo video.  It had no `moov` atom: ffmpeg writes that
last, so a truncated file is a large, recent, entirely unplayable one.  A second
encode was still running, and the `DONE=` marker that had been read belonged to
an earlier invocation of the same script writing the same log.

Two independent things are checked, because neither alone is enough:
  - the atom chain parses to exactly the file's length, and contains `moov`
  - the file is not growing

`ls -lh` answers neither.
"""
import os, struct, sys, time


def atoms(path):
    n = os.path.getsize(path)
    out, pos = [], 0
    with open(path, "rb") as f:
        while pos < n:
            f.seek(pos)
            hdr = f.read(8)
            if len(hdr) < 8:
                out.append(("<short>", n - pos))
                break
            sz = struct.unpack(">I", hdr[:4])[0]
            typ = hdr[4:8].decode("latin1", "replace")
            if sz == 1:
                sz = struct.unpack(">Q", f.read(8))[0]
            elif sz == 0:                      # "to end of file"
                sz = n - pos
            out.append((typ, sz))
            if sz <= 0:
                break
            pos += sz
    return n, out


def main(path, want_s=None):
    fails = []
    a = os.path.getsize(path)
    time.sleep(2)
    b = os.path.getsize(path)
    if b != a:
        fails.append("still growing (%d -> %d bytes): something is writing it" % (a, b))

    n, chain = atoms(path)
    kinds = [t for t, _ in chain]
    total = sum(s for _, s in chain)
    if "moov" not in kinds:
        fails.append("no moov atom: ffmpeg writes it last, so this file is truncated")
    if total != n:
        fails.append("the atom chain is %d bytes of a %d-byte file" % (total, n))
    if "<short>" in kinds:
        fails.append("the atom chain runs off the end of the file")

    print("      %s: %d bytes, atoms %s" % (path, n, " ".join(kinds)))
    for f in fails:
        print("FAIL  %s" % f)
    if not fails:
        print("ok    a complete MP4: the atom chain closes and moov is present")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else None))
