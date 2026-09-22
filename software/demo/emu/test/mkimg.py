#!/usr/bin/env python3
"""Assemble a 6309 source file into a flat 64K image.

    mkimg.py source.asm out.bin

⚠ `lwasm --format=raw` CONCATENATES sections and drops their addresses, so a
program with several `org`s - which any program with vectors has - comes out as
a short blob at offset 0 that loads nowhere near where it was assembled to run.
The listing carries the real addresses, so the image is built from that.
"""
import re, subprocess, sys, os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
LWASM = os.path.join(ROOT, ".tools", "bin", "lwasm")
LINE = re.compile(r"^([0-9A-F]{4}) ([0-9A-F]+)\s+\(")


def main():
    src, out = sys.argv[1], sys.argv[2]
    p = subprocess.run([LWASM, "--6309", "--format=raw", "--list=-",
                        "--output=" + os.devnull, src],
                       capture_output=True, text=True)
    if p.returncode != 0 or "ERROR" in p.stdout or "ERROR" in p.stderr:
        sys.stderr.write(p.stdout + p.stderr)
        sys.stderr.write("FAIL  mkimg: %s did not assemble\n" % src)
        return 1
    img = bytearray(65536)
    placed = 0
    for ln in p.stdout.splitlines():
        m = LINE.match(ln)
        if not m:
            continue
        addr = int(m.group(1), 16)
        data = bytes.fromhex(m.group(2))
        img[addr:addr + len(data)] = data
        placed += len(data)
    if placed == 0:
        sys.stderr.write("FAIL  mkimg: nothing placed from %s\n" % src)
        return 1
    open(out, "wb").write(bytes(img))
    print("mkimg: %s -> %s, %d bytes placed" % (src, out, placed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
