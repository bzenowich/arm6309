#!/bin/sh
# NitrOS-9 Level 2 on the host emulator: build the ROM, boot it, type at the
# shell, and check what comes back.
#
#   sh software/nitros9/run-emu.sh              (from the repository root)
#   NOBUILD=1 sh software/nitros9/run-emu.sh    (use the ROM already built)
#   OUT=dir   overrides /tmp/arm6309-nitros9
#
# ⚠ NOT THE MACHINE. software/demo/emu/machine.c says what it models. It is the
# CPU core checked against mc6809e.v, the map with both tasks, the video card's
# vertical blank as the system tick, and a TL16C550C on the console.
#
# The port lives in the NitrOS-9 tree, on its `arm6309` branch:
# $NITROS9DIR/recipes/arm6309/l2 builds the 1 MB ROM with this repository's
# software/boot/boot.bin as page 0. README.md beside this script has the layout.
#
# ⛔ The exit code is the answer. Each check below is a claim that fails the
# run; the emulator is bounded by SECONDS of machine time and by SERIAL_STOP.
set -e
cd "$(dirname "$0")/../.."
ROOT=$(pwd)
OUT=${OUT:-/tmp/arm6309-nitros9}
SECONDS_OF_MACHINE=${SECONDS_OF_MACHINE:-150}
mkdir -p "$OUT"

if [ -z "$NOBUILD" ]; then
  sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom-nitros9.log" 2>&1 || { cat "$OUT/mkrom-nitros9.log"; exit 1; }
fi
ROM="$OUT/arm6309_rom.bin"
[ -f "$ROM" ] || { echo "FAIL  no $ROM"; exit 1; }

# ⛔ A V3 ROM NEEDS THE V3 EMULATOR, AND EVERY ROM IS A V3 ROM SINCE
# 2026-09-22.  CoArm carries video3's code and polls VSTAT at $FF6D; run
# against this emulator's DEFAULT card - archive/video/'s - that read answers
# out of a register file and the poll SPINS FOR EVER.  The machine prints its
# banner and never reaches a shell, which reads as a broken boot rather than a
# mismatched pair.  ⚠ This used to follow a `$V3` the caller set; the recipe
# puts -DV3=1 in AFLAGS itself now, so there is nothing left to follow and the
# pairing is unconditional.
export VIDEO3=1
cc -O2 -Wall -Iaudio/refplayer -o "$OUT/emu" software/demo/emu/machine.c software/demo/emu/cpu6809.c software/demo/emu/hd6309.c audio/refplayer/card.c

# What is typed, from 8 s of machine time on: the shell is up by ~3 s.
# `sleep 2100` is 2100 ticks: 30 s at VMODE 00's 70.086 Hz. Then `vmodetst 1`
# puts the card in the 525-line family, where `sleep 1800` is 30.03 s at
# 59.940 Hz - and would read as 25.7 s to a clock that still counted 70 ticks
# to the second, which is what defs/arm6309.d's per-tick period replaced.
# `firqtst` runs twice: the second run is after the driver's Term has put the
# previous FIRQ service back, so it is the install/remove path as well.
printf 'dir /sd0\rdir /sd0/cmds\rdir /dd/cmds\rmfree\rdate -t\rsleep 2100\rdate -t\rprocs\rvmodetst 1\rdate -t\rsleep 1800\rdate -t\rvmodetst 0\rload /sd0/modules/firqtst\rfirqtst\rfirqtst\rps2tst\rload pmap\rmemtst\recho DONE-arm6309\r' > "$OUT/typed.txt"

# SERIAL_STOP is the echo's OUTPUT line: a line feed then the word, which the
# typed command line ("echo DONE-...") does not contain.
STOP=$(printf '\nDONE-arm6309')
# ps2tst initialises both PS/2 ports by ps2.md 7 and 11.2, then echoes three
# bytes from each: these, which the emulator's devices send once they are
# enabled.
export PS2_KBD="1C F0 1C" PS2_MOUSE="09 05 FB"
# ⛔ AND IT BOOTS OFF THE CARD SINCE 2026-09-22.  The ROM carries no
# filesystem at all - pages 3-63 are zeros - so a run with an EMPTY SOCKET
# does not reach a prompt: boot_sd finds no system disk and the kernel takes
# D.Crash.  mkrom.sh builds system.img beside the ROM for exactly this.
[ -f "$OUT/system.img" ] || { echo "FAIL  no $OUT/system.img - mkrom.sh should have built the system card"; exit 1; }
(cd "$OUT" && SERIAL_IN=typed.txt SERIAL_AT=8 SERIAL_STOP="$STOP" WILD=1 SDIMG="$OUT/system.img" ./emu "$ROM" . "$SECONDS_OF_MACHINE" > /dev/null 2> emu.log) || true
tr -d '\000' < "$OUT/serial.out" | tr -d '\r' > "$OUT/console.txt"

fail=0; n=0
claim() {  # claim "what" command...
  n=$((n+1)); what=$1; shift
  if "$@" >/dev/null 2>&1; then echo "ok    $what"; else echo "FAIL  $what"; fail=$((fail+1)); fi
}
has() { grep -q -- "$1" "$OUT/console.txt"; }

claim "the loader ran and entered krn (R, K)"                has '^RK'
# ⭐ ONE DISK, TWO NAMES (2026-09-22).  rbromdisk, its DD and its R0 left the
# bootfile with the ROM disk; what is left is the card's driver and its two
# descriptors - /DD, which SysGo and every program's data path name, and /SD0.
claim "krn found Boot and loaded OS9Boot"                    has 'bKrnP2 KrnP3 Init IOMan RBF rbsd DD SD0 SCF sc16550 Term'
claim "⛔ ...and NO rbromdisk: there is no ROM disk to drive" \
  sh -c "! grep -q 'rbromdisk' '$OUT/console.txt'"
# ⭐ AND IT CAME OFF THE CARD, which is boot_sd.asm's own character: `s` for
# a card it read, `n` for no system disk.  ⚠ It mattered more when there was
# a ROM disk to fall back to; it is kept because it says WHICH of sdcard.md
# §9.0's steps refused when one does.
claim "⭐ ...and OS9Boot came off the SD CARD, not the ROM (boot_sd's 's')" has 'tbs0'
claim "SysGo printed the banner, naming this machine"        has '^arm6309$'
claim "the shell prompted on /Term"                          has '{Term|02}/DD:'
claim "⭐ dir /sd0 lists the CARD's root: NitrOS-9 lives here now"  has 'OS9Boot *CMDS *DATA *MODULES *SYS'
# ⚠ NOT A COLUMN PATTERN: the card carries the demos as well as the command
# set, so the five-column layout depends on how many demos this build made.
claim "dir /sd0/cmds lists the whole command set" \
  sh -c "for c in mfree mmap procs setime verify; do sed -n '/Directory of .sd0.cmds/,/^\$/p' '$OUT/console.txt' | grep -qw \$c || exit 1; done"
# ⭐ AND /DD IS THE CARD - the same disk under both names, which is what lets
# SysGo, armio.asm's CoPath and every program's /DD path keep working with no
# ROM disk under them.
claim "⭐ /DD and /SD0 are the SAME disk: /DD/CMDS is the card's command set" \
  sh -c "for c in mfree mmap procs setime verify; do sed -n '/Directory of .dd.cmds/,/^\$/p' '$OUT/console.txt' | grep -qw \$c || exit 1; done"
# ⛔ ...and the ROM carries no filesystem at all.  The host asks, because the
# machine cannot see what is not mounted.
claim "⛔ AND THE ROM HAS NO FILESYSTEM: pages 3-63 are all zero" \
  sh -c "python3 -c \"
import sys
d=open('$OUT/arm6309_rom.bin','rb').read()[3*8192:64*8192]
sys.exit(0 if not any(d) else 1)\""
# (free blocks: the bootfile, system memory and the shell, loaded from /DD/CMDS, have the rest)
claim "mfree reports 8 MB of RAM mapped: four SIMM sockets, capped at F\$GBlkMp's 1024 blocks" has 'Total: *3F5 *8104k'
claim "procs shows the shell running procs"                  has 'Procs *$'
claim "the run ended at the last command, not by the clock"  grep -q 'SERIAL_STOP seen' "$OUT/emu.log"
claim "the CPU never ran through empty RAM (WILD)"           sh -c "! grep -q '^WILD' '$OUT/emu.log'"
# the tick: two date -t readings around sleep 2100. The second is read a command
# later (the fork and the ROM-disk load of date), so 30 to 32; a 60 Hz tick is 35+
# (Shell+'s startup banner prints a time too: take the two after the typing began)
t=$(sed -n '/date -t/,$p' "$OUT/console.txt" | grep -o '[0-9][0-9]:[0-9][0-9]:[0-9][0-9]$' | awk -F: '{print $1*3600+$2*60+$3}')
d=$(echo "$t" | awk 'NR==1{a=$1} NR==2{b=$1} END{print b-a}')
d525=$(echo "$t" | awk 'NR==3{a=$1} NR==4{b=$1} END{print b-a}')
claim "sleep 2100 in VMODE 00 took 30 s of the clock: VBL is the 70.086 Hz tick (got ${d:-none})" test "${d:-0}" -ge 30 -a "${d:-0}" -le 32

# the FIRQ stub (krn.asm ArmFIRQ): level2/arm6309/cmds/firqtst.asm says what each line means
sys=$(grep -o 'FIRQs in 100 ticks: [0-9]*' "$OUT/console.txt" | awk '{print $5+0}')
usr=$(grep 'FIRQs in user state:' "$OUT/console.txt" | awk '{print $5+0}')
inrange() { for v in $1; do [ "$v" -ge "$2" ] && [ "$v" -le "$3" ] || return 1; done; [ "$(echo $1 | wc -w)" -eq 2 ]; }
claim "FIRQ: the audio card's 50 Hz timer, counted across 100 ticks, twice: $(echo $sys) (69-73 each)" inrange "$sys" 69 73
claim "FIRQ in user state, twice: $(echo $usr) (100-140 each)" inrange "$usr" 100 140
claim "and every register the stub saves came back, both times" test "$(grep -c 'FIRQs in user state: [0-9]*, registers intact' "$OUT/console.txt")" -eq 2
claim "no crash: nothing printed D.Crash's '!'" sh -c "! grep -q '![0-9A-F][0-9A-F]' '$OUT/console.txt'"

claim "PS/2 keyboard: FF, F2, F4 each answered, by ps2.md 7's software transmit, then the scan codes" has '^kbd: FA AA FA AB 83 FA 1C F0 1C$'
claim "PS/2 mouse: FF, F3 3C, F4 each answered, then a packet" has '^mouse: FA AA 00 FA FA FA 09 05 FB$'
# memtst takes every free block and checks each is its own memory, through
# F$MapBlk and F$CpyMem, with pmap forked into the six highest (pmap is
# loaded first, so the fork does no file I/O that would free a low block).
claim "memtst: every free block, up to \$3F9, is distinct memory by F\$MapBlk and F\$CpyMem" has '^memtst: 03F[0-9A-F] blocks to \$03F9, MapBlk ok, CpyMem ok$'
claim "and pmap ran from the high blocks memtst gave back" has '^  4   FB \.\. \.\. \.\. \.\. \.\. [0-9A-F][0-9A-F] 3F  PMap'
claim "sleep 1800 in VMODE 01 took 30 s of the clock: the 59.940 Hz family keeps time too (got ${d525:-none}; a fixed 70 would be 26)" test "${d525:-0}" -ge 30 -a "${d525:-0}" -le 32

# A one-socket machine: the loader sizes RAM from the boot ROM's descriptor.
printf 'mfree\recho DONE-arm6309\r' > "$OUT/typed1.txt"
mkdir -p "$OUT/one"
(cd "$OUT/one" && EMU_SIMMS=1 SERIAL_IN=../typed1.txt SERIAL_AT=4 SERIAL_STOP="$STOP" SDIMG="$OUT/system.img" ../emu "$ROM" . 30 > /dev/null 2> emu.log) || true
tr -d '\000' < "$OUT/one/serial.out" | tr -d '\r' > "$OUT/one/console.txt"
claim "with one SIMM socket, mfree reports 4 MB: the size comes from the boot ROM's descriptor" grep -q 'Total: *1F5 *4008k' "$OUT/one/console.txt"

# A reboot: F$Debug 255 re-enters boot.asm at its reset vector with the map
# live; the POST runs again (the emulator reports its progress codes) and
# NitrOS-9 boots a second time.
printf 'reboot\r' > "$OUT/typedr.txt"
mkdir -p "$OUT/reboot"
(cd "$OUT/reboot" && SERIAL_IN=../typedr.txt SERIAL_AT=4 SDIMG="$OUT/system.img" ../emu "$ROM" . 14 > /dev/null 2> emu.log) || true
tr -d '\000' < "$OUT/reboot/serial.out" | tr -d '\r' > "$OUT/reboot/console.txt"
claim "reboot: boot.asm's POST ran again - the map, the SIMM walk, TASK 1 and the store-rate blocks, with no error" \
  sh -c "grep -q 'progress \$01' '$OUT/reboot/emu.log' && grep -q 'progress \$07' '$OUT/reboot/emu.log' && grep -q 'progress \$52' '$OUT/reboot/emu.log' && ! grep -q 'FAIL' '$OUT/reboot/emu.log'"
# ⭐ AND IT STOPS AT $06, NOT $40, SINCE 2026-09-20 - which is the answer this
# configuration must give. boot.asm §2c probes for a video3 card before its
# video POST and skips §3-§10 when there is none; this emulator models
# archive/video/'s card unless VIDEO3=1 (machine.c's m->v3), and a VSTAT poll
# at $FF6D against THAT card reads a register-file byte and can spin for ever.
# $40 is what VIDEO3=1 reports - software/nitros9/video/run-video3.sh - and
# what npm run check:machine asserts against the real design.
# ⚠ $06 without VIDEO3 (§2c probes, finds no card and skips §3-§10) and $40
# with it (the POST runs to the VRAM read-back).
# ⚠ $06 without VIDEO3 (§2c probes, finds no card and skips §3-§10) and $40
# with it (the POST runs to the VRAM read-back).  ⛔ NOT `${V3:+40}${V3:-06}`:
# with V3=1 that is "40" and "1" and gives $401.
PROG2C=40      # ⚠ video3's, and there is no other flavour since 2026-09-22
claim "⭐ and §2c's probe decided the video POST: \$$PROG2C" \
  grep -q "progress \$$PROG2C" "$OUT/reboot/emu.log"
claim "and NitrOS-9 booted a second time, to the shell" test "$(grep -c '{Term|02}/DD:' "$OUT/reboot/console.txt")" -ge 2

echo "$n claims, $fail failed        (console in $OUT/console.txt)"
[ "$fail" -eq 0 ]
