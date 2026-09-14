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
SECONDS_OF_MACHINE=${SECONDS_OF_MACHINE:-90}
mkdir -p "$OUT"

if [ -z "$NOBUILD" ]; then
  sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom-nitros9.log" 2>&1 || { cat "$OUT/mkrom-nitros9.log"; exit 1; }
fi
ROM="$OUT/arm6309_rom.bin"
[ -f "$ROM" ] || { echo "FAIL  no $ROM"; exit 1; }

cc -O2 -Wall -o "$OUT/emu" software/demo/emu/machine.c software/demo/emu/cpu6809.c

# What is typed, from 8 s of machine time on: the shell is up by ~3 s.
# `sleep 2100` is 2100 ticks: 30 s at VMODE 00's 70 Hz, and 35 s if the tick were 60 Hz.
# `firqtst` runs twice: the second run is after the driver's Term has put the
# previous FIRQ service back, so it is the install/remove path as well.
printf 'dir\rdir /dd/cmds\rmfree\rdate -t\rsleep 2100\rdate -t\rprocs\rload /dd/modules/firqtst\rfirqtst\rfirqtst\recho DONE-arm6309\r' > "$OUT/typed.txt"

# SERIAL_STOP is the echo's OUTPUT line: a line feed then the word, which the
# typed command line ("echo DONE-...") does not contain.
STOP=$(printf '\nDONE-arm6309')
(cd "$OUT" && SERIAL_IN=typed.txt SERIAL_AT=8 SERIAL_STOP="$STOP" WILD=1 ./emu "$ROM" . "$SECONDS_OF_MACHINE" > /dev/null 2> emu.log) || true
tr -d '\000' < "$OUT/serial.out" | tr -d '\r' > "$OUT/console.txt"

fail=0; n=0
claim() {  # claim "what" command...
  n=$((n+1)); what=$1; shift
  if "$@" >/dev/null 2>&1; then echo "ok    $what"; else echo "FAIL  $what"; fail=$((fail+1)); fi
}
has() { grep -q -- "$1" "$OUT/console.txt"; }

claim "the loader ran and entered krn (R, K)"                has '^RK'
claim "krn found Boot and loaded OS9Boot from the ROM disk"  has 'bKrnP2 KrnP3 Init IOMan RBF rbromdisk DD R0 SCF sc16550 Term'
claim "SysGo printed the banner, naming this machine"        has '^arm6309$'
claim "the shell prompted on /Term"                          has '{Term|02}/DD:'
claim "dir lists the ROM disk's root"                        has 'OS9Boot *CMDS *MODULES *SYS *startup'
claim "dir /dd/cmds lists commands on the ROM disk"          has 'mfree *mmap *more'
claim "mfree reports 2 MB of RAM mapped"                     has 'Total: *F6 *1968k'
claim "procs shows the shell running procs"                  has 'Procs *$'
claim "the run ended at the last command, not by the clock"  grep -q 'SERIAL_STOP seen' "$OUT/emu.log"
claim "the CPU never ran through empty RAM (WILD)"           sh -c "! grep -q '^WILD' '$OUT/emu.log'"
# the tick: two date -t readings around sleep 2100. The second is read a command
# later (the fork and the ROM-disk load of date), so 30 to 32; a 60 Hz tick is 35+
# (Shell+'s startup banner prints a time too: take the two after the typing began)
t=$(sed -n '/date -t/,$p' "$OUT/console.txt" | grep -o '[0-9][0-9]:[0-9][0-9]:[0-9][0-9]$' | awk -F: '{print $1*3600+$2*60+$3}')
d=$(echo "$t" | awk 'NR==1{a=$1} NR==2{b=$1} END{print b-a}')
claim "sleep 2100 took 30 s of the clock: VBL is the 70 Hz tick (got ${d:-none})" test "${d:-0}" -ge 30 -a "${d:-0}" -le 32

# the FIRQ stub (krn.asm ArmFIRQ): level2/arm6309/cmds/firqtst.asm says what each line means
sys=$(grep -o 'FIRQs in 100 ticks: [0-9]*' "$OUT/console.txt" | awk '{print $5+0}')
usr=$(grep 'FIRQs in user state:' "$OUT/console.txt" | awk '{print $5+0}')
inrange() { for v in $1; do [ "$v" -ge "$2" ] && [ "$v" -le "$3" ] || return 1; done; [ "$(echo $1 | wc -w)" -eq 2 ]; }
claim "FIRQ: the audio card's 50 Hz timer, counted across 100 ticks, twice: $(echo $sys) (69-73 each)" inrange "$sys" 69 73
claim "FIRQ in user state, twice: $(echo $usr) (100-140 each)" inrange "$usr" 100 140
claim "and every register the stub saves came back, both times" test "$(grep -c 'FIRQs in user state: [0-9]*, registers intact' "$OUT/console.txt")" -eq 2
claim "no crash: nothing printed D.Crash's '!'" sh -c "! grep -q '![0-9A-F][0-9A-F]' '$OUT/console.txt'"

echo "$n claims, $fail failed        (console in $OUT/console.txt)"
[ "$fail" -eq 0 ]
