#!/usr/bin/env python3
"""Read run-vramrate.sh's progress-port timestamps and print cycles a byte.

machine.c prints "<t> s  progress $XX" for every write to $FF2F.  Each phase
writes its own marker on entry, so a phase's duration is the gap to the next.
"""
import re, sys

E_HZ    = 2097917.0          # machine.md: the E rate
NBYTES  = 8160 * 16          # vramrate.asm moves this many bytes a phase

PHASES = {
    0xA1: ("PUT   VDATA   vidcore.asm Strm, chunk 24", 21.0),
    0xA2: ("PUT   VDATA   unrolled DP, chunk 96",       9.06),
    0xA3: ("FILL  VDATA   vidcore.asm Strm, chunk 24", 15.0),
    0xA4: ("FILL  VDATA   unrolled DP, chunk 96",       5.06),
    0xA5: ("GET   VDATA   vidcore.asm Strm, chunk 24", 21.0),
    0xA6: ("GET   VDATA   unrolled DP, chunk 96",       9.06),
    0xA7: ("FILL  WINDOW  STD <dp, chunk 96",           3.56),
    0xA8: ("PUT   WINDOW  PULU + 3 x 16-bit ST, ch 96", 5.56),
}

# The two WINDOW phases use 16-bit stores, and machine.c recomputes m->dots
# from cpu.cycles only BETWEEN instructions (machine.c:1179), so both write
# cycles of an STD land at the same dot and the second one meets the first's
# busy_until.  On silicon they are consecutive E cycles, 476 ns apart, against
# a direct write's <=318 ns of SPANBUSY (graphics.md 2.1's no-stall guarantee,
# 7.4's 159 ns) - so the emulator's figure for $A7/$A8 is an UPPER bound.
# run-vramrate-rtl.sh is the arbiter.
EMU_16BIT_STALL = {0xA7, 0xA8}

pat = re.compile(r"([0-9.]+)\s*s\s+progress \$([0-9A-Fa-f]{2})")
marks = [(float(t), int(v, 16)) for t, v in pat.findall(open(sys.argv[1]).read())]
verdict = [v for _, v in marks if v in (0xAE, 0xEE)]
# $A0 closes the last phase; $AF is after the self-check and must NOT be
# the terminator, or the check's time lands inside the last phase.
marks = [m for m in marks if m[1] in PHASES or m[1] == 0xA0]
if len(marks) < len(PHASES) + 1:
    print(f"FAIL  only {len(marks)} markers (need {len(PHASES)+1}); the run did not finish "
          f"(give run-vramrate.sh more seconds)")
    sys.exit(1)

if 0xEE in verdict:
    print("FAIL  a PUT form read back different bytes than it wrote ($EE)")
    sys.exit(1)
if 0xAE not in verdict:
    print("FAIL  the self-check did not run: no $AE and no $EE")
    sys.exit(1)
print("ok    every PUT form wrote 960 bytes that read back byte for byte, each from its own seed ($AE)")
print(f"{NBYTES:,} bytes a phase, E = {E_HZ/1e6:.4f} MHz\n")
print(f"{'phase':<44}{'us/byte':>9}{'cyc/byte':>10}{'predicted':>11}{'vs $A1':>9}")
print("-" * 83)
base = None
rows = []
for (t0, v), (t1, _) in zip(marks, marks[1:]):
    name, pred = PHASES[v]
    us  = (t1 - t0) * 1e6 / NBYTES
    cyc = (t1 - t0) * E_HZ / NBYTES
    if base is None:
        base = us
    rows.append((v, name, us, cyc, pred, base / us))
    print(f"${v:02X} {name:<40}{us:>9.3f}{cyc:>10.2f}{pred:>11.2f}{base/us:>8.2f}x")

print()
bad = [(v, c, p) for v, _, _, c, p, _ in rows if abs(c - p) > 0.35]
for v, c, p in bad:
    why = ("  - machine.c stalls both write cycles of a 16-bit store against one\n"
           "     another (see EMU_16BIT_STALL); on silicon they are 476 ns apart.\n"
           "     Treat this as an UPPER bound and run run-vramrate-rtl.sh."
           if v in EMU_16BIT_STALL else
           "  - unexplained: the card stalled the CPU, or the loop is not what\n"
           "     the prediction assumes.  Read build/vramrate.lst.")
    print(f"~  ${v:02X}: measured {c:.2f} cycles a byte, predicted {p:.2f} "
          f"from the 6809 cycle table\n{why}")
clean = [v for v, _, _, c, p, _ in rows if abs(c - p) <= 0.35]
print(f"\nok  {len(clean)} of {len(rows)} phases match the 6809 cycle table to within")
print("    0.35 cycles a byte, so the card never stalled the CPU in them: what")
print("    they measure is the cost of the loop, not the cost of the card.")
