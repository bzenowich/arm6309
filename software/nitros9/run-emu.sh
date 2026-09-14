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
NITROS9DIR=${NITROS9DIR:-$(cd "$ROOT/../nitros9" 2>/dev/null && pwd)}
SECONDS_OF_MACHINE=${SECONDS_OF_MACHINE:-90}
export PATH="$ROOT/.tools/bin:$PATH"
mkdir -p "$OUT"

[ -n "$NITROS9DIR" ] && [ -d "$NITROS9DIR/recipes/arm6309" ] || {
  echo "FAIL  no NitrOS-9 tree with recipes/arm6309 (set NITROS9DIR; branch arm6309)"; exit 1; }
command -v lwasm >/dev/null && command -v os9 >/dev/null || {
  echo "FAIL  no lwasm/os9: run sh software/tools/fetch-nitros9-tools.sh"; exit 1; }

ROM="$NITROS9DIR/recipes/arm6309/l2/arm6309_rom.bin"
if [ -z "$NOBUILD" ]; then
  sh software/tools/mkrom.sh > "$OUT/mkrom.log" 2>&1 || { tail -5 "$OUT/mkrom.log"; exit 1; }
  make -C "$NITROS9DIR/recipes/arm6309/l2" NITROS9DIR="$NITROS9DIR" ARM6309DIR="$ROOT" \
    > "$OUT/build.log" 2>&1 || { grep -v '^lwasm\|^lwlink' "$OUT/build.log" | tail -20; echo "FAIL  the ROM did not build"; exit 1; }
fi
[ -f "$ROM" ] || { echo "FAIL  no $ROM"; exit 1; }

cc -O2 -Wall -o "$OUT/emu" software/demo/emu/machine.c software/demo/emu/cpu6809.c

# What is typed, from 8 s of machine time on: the shell is up by ~3 s.
# `sleep 2100` is 2100 ticks: 30 s at VMODE 00's 70 Hz, and 35 s if the tick were 60 Hz.
printf 'dir\rdir /dd/cmds\rmfree\rdate -t\rsleep 2100\rdate -t\rprocs\recho DONE-arm6309\r' > "$OUT/typed.txt"

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
claim "dir lists the ROM disk's root"                        has 'OS9Boot *CMDS *SYS *startup'
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

echo "$n claims, $fail failed        (console in $OUT/console.txt)"
[ "$fail" -eq 0 ]
