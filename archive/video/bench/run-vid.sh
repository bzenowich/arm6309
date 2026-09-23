#!/bin/sh
# The NitrOS-9 video console on the host emulator: build the ROM, run the
# scripted clients, and judge what reached the screen.
#
#   sh software/nitros9/run-vid.sh              (from the repository root)
#   NOBUILD=1 sh software/nitros9/run-vid.sh    (use the ROM already built)
#   OUT=dir   overrides /tmp/arm6309-vid
#
# docs/nitros9-av-plan.md phases P1 and P2 are closed by this: scripted clients'
# output against Python models of the expected screens (tools/vtmodel.py for text,
# tools/vgmodel.py for bitmap windows and the pointer), pixel for pixel, and the
# IRQ-masked time measured (the emulator's MASKLOG and CALLTIME). The
# modules are in $NITROS9DIR on its arm6309 branch: level2/arm6309/modules/armio,
# coarm, vidcore, kbdarm and armwin (README.md beside this script).
#
# ⛔ The exit code is the answer. Each emulator run is bounded by machine seconds
# and by SERIAL_STOP; tools/checkvid.py makes the claims.
set -e
cd "$(dirname "$0")/../.."
ROOT=$(pwd)
OUT=${OUT:-/tmp/arm6309-vid}
mkdir -p "$OUT"

if [ -z "$NOBUILD" ]; then
  # ⚠ CMDS_EXTRA: since 2026-09-20 the demos are NOT in the ROM disk (they go
  # on an SD card - software/nitros9/mksddisk.sh).  This session boots with an
  # empty socket and types these three at /DD, so it asks for them by name.
  # ⚠ SYSROM=all: this session types `copy /dd/sys/...` at the shell, so the
  # demo data has to be in /DD/SYS.  It is on the card's DATA directory by
  # default (2026-09-20) and /SYS holds only errmsg; SYSROM= is what also
  # copies it to /SYS.  ⛔ AND /DD IS THE CARD SINCE 2026-09-22: mksyscard.sh
  # puts $OUT/romsys there, because the ROM has no filesystem to put it in.
  CMDS_EXTRA="rastbar wave overworld" SYSROM=all sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom-nitros9.log" 2>&1 || { cat "$OUT/mkrom-nitros9.log"; exit 1; }
fi
ROM="$OUT/arm6309_rom.bin"
[ -f "$ROM" ] || { echo "FAIL  no $ROM"; exit 1; }
# ⛔ THE CARD IS THE SYSTEM DISK since 2026-09-22 (arm6309 docs/history.md):
# the ROM carries the toolbox and no filesystem, so a session with an EMPTY
# SOCKET does not reach a shell at all.  mkrom.sh writes system.img beside the
# ROM out of the same build, and /DD is that card - which is why the
# `copy /dd/sys/...` lines below still read what SYSROM/$OUT/sys put there.
SDIMG="$OUT/system.img"; export SDIMG
[ -f "$SDIMG" ] || { echo "FAIL  no $SDIMG - mkrom.sh should have built the system card"; exit 1; }
cc -O2 -Wall -Iaudio/refplayer -o "$OUT/emu" software/demo/emu/machine.c software/demo/emu/cpu6809.c software/demo/emu/hd6309.c audio/refplayer/card.c

STOP=$(printf '\nDONE-arm6309')
# the VBL service, timed call by call (the emulator's CALLTIME)
SVC=$(sh software/nitros9/tools/modsym.sh "$OUT" armio.asm VcSvc) || { echo "FAIL  no VcSvc in armio.asm's listing"; exit 1; }

# select: /W1 is displayed at its Init and given vtp1; /W2 (80 x 30) is made
# while /W1 is displayed and given vtw2, then selected, then /W1 again. A
# sleep follows each Select: a palette takes eight blanks to commit.
mkdir -p "$OUT/select"
printf 'iniz w1\rcopy /dd/sys/vtp1 /w1\riniz w2\rcopy /dd/sys/vtw2 /w2\rsleep 20\rdisplay 1b 21 >/w2\rsleep 70\rdisplay 1b 21 >/w1\rsleep 70\recho DONE-arm6309\r' > "$OUT/select/typed.txt"
(cd "$OUT/select" && SERIAL_IN=typed.txt SERIAL_AT=4 SERIAL_STOP="$STOP" WILD=1 MASKLOG=4 CALLTIME="ArmIO+\$$SVC" ../emu "$ROM" . 60 > /dev/null 2> emu.log) || true
tr -d '\000' < "$OUT/select/serial.out" | tr -d '\r' > "$OUT/select/console.txt"

# kbd: a shell on /W1, and a line typed on the PS/2 keyboard, a backspace in it
mkdir -p "$OUT/kbd"
printf 'iniz w1\rshell i=/w1&\r' > "$OUT/kbd/typed.txt"
KEYS=$(python3 software/nitros9/tools/vtmodel.py --keys 'echx\bo KBD-OK >/term\r')
(cd "$OUT/kbd" && SERIAL_IN=typed.txt SERIAL_AT=4 SERIAL_STOP="KBD-OK" PS2_KBD="$KEYS" PS2_AT=7 WILD=1 ../emu "$ROM" . 30 > /dev/null 2> emu.log) || true
tr -d '\000' < "$OUT/kbd/serial.out" | tr -d '\r' > "$OUT/kbd/console.txt"

# p2: /W3 (640 x 200 bitmap) given vgp2a and displayed; /W4 (640 x 240) made
# and given vgp2b while /W3 is displayed; Select /W4; Select /W3 again
mkdir -p "$OUT/p2"
printf 'iniz w3\rcopy /dd/sys/vgp2a /w3\riniz w4\rcopy /dd/sys/vgp2b /w4\rsleep 30\rdisplay 1b 21 >/w4\rsleep 90\rdisplay 1b 21 >/w3\rsleep 90\recho DONE-arm6309\r' > "$OUT/p2/typed.txt"
(cd "$OUT/p2" && SERIAL_IN=typed.txt SERIAL_AT=4 SERIAL_STOP="$STOP" WILD=1 MASKLOG=5 ../emu "$ROM" . 90 > /dev/null 2> emu.log) || true
tr -d '\000' < "$OUT/p2/serial.out" | tr -d '\r' > "$OUT/p2/console.txt"

# mouse: vgp2a on /W3, then PS/2 mouse packets (vgmodel.py's MOVES) while the
# system is idle; the pointer move is timed call by call
PTRMOVE=$(sh software/nitros9/tools/modsym.sh "$OUT" armio.asm PtrMove) || { echo "FAIL  no PtrMove in armio.asm's listing"; exit 1; }
mkdir -p "$OUT/mouse"
printf 'iniz w3\rcopy /dd/sys/vgp2a /w3\rsleep 600\recho DONE-arm6309\r' > "$OUT/mouse/typed.txt"
MOVES=$(python3 software/nitros9/tools/vgmodel.py --mouse)
(cd "$OUT/mouse" && SERIAL_IN=typed.txt SERIAL_AT=4 SERIAL_STOP="$STOP" PS2_MOUSE="$MOVES" PS2_AT=26 WILD=1 MASKLOG=5 CALLTIME="ArmIO+\$$PTRMOVE" ../emu "$ROM" . 45 > /dev/null 2> emu.log) || true
tr -d '\000' < "$OUT/mouse/serial.out" | tr -d '\r' > "$OUT/mouse/console.txt"

# p3: every extension escape on /W3 (tools/vgmodel.py's vgp3), and an ANSI
# terminal in an overlay
mkdir -p "$OUT/p3"
printf 'iniz w3\rcopy /dd/sys/vgp3 /w3\rsleep 60\recho DONE-arm6309\r' > "$OUT/p3/typed.txt"
(cd "$OUT/p3" && SERIAL_IN=typed.txt SERIAL_AT=4 SERIAL_STOP="$STOP" WILD=1 MASKLOG=5 ../emu "$ROM" . 90 > /dev/null 2> emu.log) || true
tr -d '\000' < "$OUT/p3/serial.out" | tr -d '\r' > "$OUT/p3/console.txt"

# rast and wave (P3): a client rewrites a bitmap screen's display list every
# frame by SS.Raster - a palette entry per band line, and HSCROLL per band
# line. MARKS=1104 records the video globals' frame words with each frame
# (VG.MkPh: the tag of the list the VBL service started)
for R in rast:rastbar wave:wave; do
  D=${R%%:*}; C=${R##*:}
  mkdir -p "$OUT/$D"
  printf 'iniz w3\r%s >/w3\recho DONE-arm6309\r' "$C" > "$OUT/$D/typed.txt"
  (cd "$OUT/$D" && SERIAL_IN=typed.txt SERIAL_AT=4 SERIAL_STOP="$STOP" WILD=1 MASKLOG=5 MARKS=1104 ../emu "$ROM" . 60 > /dev/null 2> emu.log) || true
  tr -d '\000' < "$OUT/$D/serial.out" | tr -d '\r' > "$OUT/$D/console.txt"
done

# game (P3): overworld on an exclusive tile screen - SS.Excl, SS.TileLd,
# SS.MapWr, libvid and SS.Batch - judged against software/demo/tools/mkgame.py's
# render() for the camera and hero records each frame's batch committed
mkdir -p "$OUT/game"
printf 'iniz w3\roverworld >/w3\recho DONE-arm6309\r' > "$OUT/game/typed.txt"
(cd "$OUT/game" && SERIAL_IN=typed.txt SERIAL_AT=4 SERIAL_STOP="$STOP" WILD=1 MASKLOG=5 MARKS=1104 ../emu "$ROM" . 120 > /dev/null 2> emu.log) || true
tr -d '\000' < "$OUT/game/serial.out" | tr -d '\r' > "$OUT/game/console.txt"

python3 software/nitros9/tools/checkvid.py "$OUT"
