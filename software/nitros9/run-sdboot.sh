#!/bin/sh
# ⭐ THE MACHINE BOOTS NitrOS-9 OFF THE SD CARD - from reset, through the boot
# ROM's own reader, to a shell.
#
#   sh software/nitros9/run-sdboot.sh           (from the repository root)
#   NOBUILD=1 sh software/nitros9/run-sdboot.sh (use the ROM already built)
#   OUT=dir   overrides /tmp/arm6309-sdboot
#
# ⚠ NOT THE MACHINE, in the sense software/demo/emu/machine.c means: it is the
# CPU core checked against mc6809e.v, the map, video3, the vertical blank as
# the system tick, a TL16C550C on the console - and the storage card at $FF58
# with a real SDHC card in SPI mode behind it, backed by an image file, ported
# byte for byte from hardware/gal/verilog/storage_card.v and sd_model.v.  The
# 74-clock power-up gate is a GATE there: a reader that skips sdcard.md §9.0
# step 1's `SDMOSI <- $FF` gets $FF from CMD0 for ever, here as on a bench.
#
# ** WHAT THIS ASSERTS THAT NO OTHER BENCH DOES.  run-sd.sh mounts /SD0 from a
# driver the OS already loaded; run-v3sd.sh runs a program off the card.  Both
# need the OS to be running first.  This one is about where the OS ITSELF came
# from, which is two pieces of code neither of those touches:
#
#   software/boot/boot.asm §10b, the boot ROM's own reader - §9.0's init and
#     §9.1's CMD17 - which decides which of the boot dialog's three pictures
#     is true (docs/boot-and-desktop.md §1, §2)
#   nitros9 level2/arm6309/modules/boot_sd.asm, the F$Boot module, which reads
#     OS9Boot off the card and falls back to the ROM disk when it cannot
#
# ⛔ "A SHELL APPEARED" IS NOT EVIDENCE, and that is the whole difficulty: the
# fallback works, so a machine that silently ignored the card boots to exactly
# the same prompt.  Two independent things say the card was the source:
#
#   1. boot_sd prints `s` through D.BtBug where the fallback prints `r`, so
#      the console carries the answer from the code path that ran.
#   2. ⭐ THE CARD'S OS9Boot IS NOT THE ROM DISK'S.  This bench appends the
#      FIRQ stub's two modules to the bootfile it puts on the card, so a
#      machine that booted from the card has `FIRQDrv` and `FT0` in its
#      module directory WITHOUT ANYTHING HAVING LOADED THEM, and one that
#      booted from the ROM disk does not.  `mdir` is asked, and the ROM
#      disk's own OS9Boot is asked of the HOST, so the claim cannot pass on
#      a ROM that happened to carry them too.
#
# ⛔ AND THREE CARD STATES, because the interesting one is in the middle:
#
#   card     a blessed volume: `os9 gen`'d OS9Boot and §9.5's signature
#   plain    ⭐ A CARD THAT IS THERE AND IS NOT BOOTABLE.  This is the state
#            the old card-detect test could not see at all - the socket
#            switch is closed either way - and it is the Macintosh's actual
#            question mark: there IS a disk and it is not a system disk
#   nocard   an empty socket
#
# The last two must both reach a shell off the ROM disk and SAY they did.
#
# ⛔ The exit code is the answer.
set -e
cd "$(dirname "$0")/../.."
ROOT=$(pwd)
OUT=${OUT:-/tmp/arm6309-sdboot}
SECONDS_OF_MACHINE=${SECONDS_OF_MACHINE:-120}
REBOOT_SECONDS=${REBOOT_SECONDS:-20}
NITROS9DIR=${NITROS9DIR:-$(cd "$ROOT/../nitros9" 2>/dev/null && pwd)}
REC="$NITROS9DIR/recipes/arm6309/l2"
TOOLS=${TOOLS:-$ROOT/.tools/bin}
PATH="$TOOLS:$PATH"; export PATH
mkdir -p "$OUT"

# ⚠ V3=1, because §10a's dialog is what §10b's verdict drives and the toolbox
# it draws with is ROM page 64, which only a V3=1 build has.  Without it the
# ROM writes $63 (no toolbox) and never reaches the reader at all.
if [ -z "$NOBUILD" ]; then
  V3=1 sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom-sdboot.log" 2>&1 || {
    tail -20 "$OUT/mkrom-sdboot.log"; echo "FAIL  the ROM did not build"; exit 1; }
fi
ROM="$OUT/arm6309_rom.bin"
[ -f "$ROM" ] || { echo "FAIL  no ROM in $OUT"; exit 1; }
[ -f "$REC/bootfile" ] || { echo "FAIL  no $REC/bootfile - the recipe did not build"; exit 1; }
[ -f "$REC/modules_firqtst" ] || { echo "FAIL  no $REC/modules_firqtst"; exit 1; }

# ⭐ THE CARD'S OS9Boot, AND IT IS DELIBERATELY NOT THE ROM'S.  A NitrOS-9
# bootfile is a concatenation of modules - `merge` is what the recipe uses -
# so the FIRQ stub's driver and descriptor append with `cat`, and `mdir` on
# the running machine is then a statement about which image was read.
cat "$REC/bootfile" "$REC/modules_firqtst" > "$OUT/cardboot"
cmp -s "$REC/bootfile" "$OUT/cardboot" && {
  echo "FAIL  the card's bootfile is identical to the ROM disk's - the whole test is vacuous"; exit 1; }

BOOT="$OUT/cardboot" NAME="arm6309 boot" \
  sh software/nitros9/mksddisk.sh "$OUT/sdboot.img" overworld > "$OUT/mksddisk.log" 2>&1 || {
    cat "$OUT/mksddisk.log"; echo "FAIL  the bootable card did not build"; exit 1; }
cat "$OUT/mksddisk.log"
# ...and the same card WITHOUT the blessing: same tools, same files, no
# `os9 gen` and no signature.  ⛔ It has to be a VALID RBF VOLUME, or the
# middle state would be "a card the machine cannot read" rather than "a card
# the machine can read and must not boot from".
NAME="arm6309 data" \
  sh software/nitros9/mksddisk.sh "$OUT/sdplain.img" overworld > "$OUT/mksddisk-plain.log" 2>&1 || {
    cat "$OUT/mksddisk-plain.log"; echo "FAIL  the plain card did not build"; exit 1; }
sig=$(od -An -v -tx1 -j240 -N8 "$OUT/sdplain.img" | tr -d ' \n')
[ "$sig" = "0000000000000000" ] || {
  echo "FAIL  the plain card carries $sig at LSN 0 +\$F0 - it is not the control it claims to be"; exit 1; }

cc -O2 -Wall -I"$ROOT/audio/refplayer" -o "$OUT/emu" software/demo/emu/machine.c \
   software/demo/emu/cpu6809.c software/demo/emu/hd6309.c "$ROOT/audio/refplayer/card.c"

# ⚠ CR, not LF.  `mdir` first: it is the claim, and a long listing that
# scrolls is still all in serial.out.
printf 'mdir\rdir\rdir /sd0\rfree /sd0\recho DONE-arm6309-sdboot\r' > "$OUT/typed.txt"
STOP=$(printf '\nDONE-arm6309-sdboot')
# ⛔ AND A SECOND RUN OF EACH, BECAUSE THIS EMULATOR DOES NOT COLD-START THE
# BOOT ROM.  software/demo/emu/machine.c enters at $8004 with boot.asm's
# handoff already applied - the map, the memory descriptor - so the POST and
# §10a's dialog never run on a fresh start, and the progress port reads $00
# for the whole of one.  `reboot` (F$Debug 255) re-enters at the reset vector
# with the map live, which is the ONLY way this emulator executes §10b at
# all.  It is also what run-emu.sh does for the same reason.
printf 'reboot\r' > "$OUT/typedr.txt"

run() {   # run <name> <image or empty> <typed file> <machine seconds> [stop]
  D="$OUT/$1"; rm -rf "$D"; mkdir -p "$D"
  (cd "$D" && SERIAL_IN="../$3" SERIAL_GATE="02}" SERIAL_TYPE=60 SERIAL_THINK=700 \
     SERIAL_STOP="$5" WILD=1 VIDEO3=1 SDIMG=$2 \
     "$OUT/emu" "$ROM" . "$4" > /dev/null 2> emu.log) || true
  tr -d '\000' < "$D/serial.out" | tr -d '\r' > "$D/console.txt"
  sed 's/\x1b\[[0-9;]*m//g' "$D/emu.log" > "$D/emu.txt"
  rm -f "$D/frames.bin"
}

if [ -z "$NORUN" ]; then
  run card   "$OUT/sdboot.img" typed.txt "$SECONDS_OF_MACHINE" "$STOP"
  run plain  "$OUT/sdplain.img" typed.txt "$SECONDS_OF_MACHINE" "$STOP"  # readable, NOT bootable
  run nocard ""                 typed.txt "$SECONDS_OF_MACHINE" "$STOP"  # machine.c reports CD = 0
  run rcard   "$OUT/sdboot.img" typedr.txt "$REBOOT_SECONDS" ""
  run rplain  "$OUT/sdplain.img" typedr.txt "$REBOOT_SECONDS" ""
  run rnocard ""                 typedr.txt "$REBOOT_SECONDS" ""
fi
[ -f "$OUT/card/console.txt" ] || { echo "FAIL  no run to read (drop NORUN)"; exit 1; }

fail=0; n=0
claim() { n=$((n+1)); what=$1; shift
  if "$@" >/dev/null 2>&1; then echo "ok    $what"; else echo "FAIL  $what"; fail=$((fail+1)); fi; }
inc()   { grep -q -- "$2" "$OUT/$1/console.txt"; }
notin() { grep -q -- "$2" "$OUT/$1/console.txt" && return 1; return 0; }
# ⛔ `"progress \\$$2"` IS $$ - THE SHELL'S PID - NOT AN ESCAPED DOLLAR
# FOLLOWED BY $2, and it cost a run.  The pattern then matched nothing, every
# positive claim failed honestly and every NEGATIVE one passed vacuously,
# which is CLAUDE.md's `grep '^FAIL'` trap wearing a dollar sign.  The `$` in
# `progress $64` is matched with `.` and the code is concatenated outside the
# quotes, so there is no escape to get wrong.
prog()  { grep -q "progress .$2" "$OUT/$1/emu.txt"; }
noprog(){ grep -q "progress .$2" "$OUT/$1/emu.txt" && return 1; return 0; }
# ⛔ CALLED DIRECTLY AND NEVER THROUGH `sh -c`: a shell function is invisible
# to a subshell, which exits 127, and `! <not found>` is TRUE - CLAUDE.md's
# 2026-09-20 trap, in which three negated claims passed vacuously.

echo
# --- 1. the boot ROM's own reader -----------------------------------------
# boot.asm §10b writes $64 or $65 BEFORE the picture it chooses, so these say
# which question the ROM answered and not merely which picture came out.
for s in rcard rplain rnocard; do
  claim "[$s] boot.asm's POST ran again and finished (\$52, then the video POST's \$40)" \
    sh -c "grep -q 'progress .52' '$OUT/$s/emu.txt' && grep -q 'progress .40' '$OUT/$s/emu.txt'"
  claim "[$s] ...and reached the dialog, so the toolbox is on ROM page 64 (\$60, not \$63)" \
    sh -c "grep -q 'progress .60' '$OUT/$s/emu.txt' && ! grep -q 'progress .63' '$OUT/$s/emu.txt'"
done
claim "⭐ THE ROM READ THE CARD: CMD58 said CCS and block 0 carried \"6309\" (\$64)" prog rcard 64
claim "   and the dialog therefore says Disk found (\$61)"                          prog rcard 61
claim "   and never reached the question mark"                                      noprog rcard 62
# ⭐ THE TEST THAT CHANGED.  Card detect alone cannot tell these two apart -
# the socket switch is closed in both - so before §10b the run below drew
# "Disk found" over a card with no operating system on it.
claim "⛔ A CARD THAT IS NOT BOOTABLE: the socket is closed and the ROM says \$65"    prog rplain 65
claim "   and the picture is the question mark (\$62), not Disk found"               prog rplain 62
claim "   ...so it never says \$64, and never says Disk found"                       noprog rplain 64
claim "   ⛔ which is the whole difference: the OLD test would have said \$61 here"   noprog rplain 61
claim "⛔ AN EMPTY SOCKET: the question mark"                                        prog rnocard 62
claim "   and \$65 is NOT written - §10b sits behind the card-detect test"           noprog rnocard 65
claim "   no \$64"                                                                   noprog rnocard 64
claim "   and no \$61"                                                               noprog rnocard 61

# --- 2. where OS9Boot came from -------------------------------------------
# boot_sd prints one character between krn's "tb" and boot_common's "0".
claim "⭐ boot_sd read OS9Boot OFF THE CARD and said so (tb s 0)"    inc card 'tbs0'
claim "⛔ the unbootable card fell back to the ROM disk (tb r 0)"    inc plain 'tbr0'
claim "⛔ the empty socket did too"                                  inc nocard 'tbr0'
claim "   and the card run did NOT take the fallback"                notin card 'tbr0'
claim "   and neither control claims the card"                       notin plain 'tbs0'
claim "   nor the empty socket"                                      notin nocard 'tbs0'

# ⭐ AND THE SECOND, INDEPENDENT ANSWER: the card's OS9Boot carries two
# modules the ROM disk's does not, and nothing loaded them.
claim "⭐⭐ THE MODULE DIRECTORY PROVES IT: FIRQDrv is in memory, from the card's OS9Boot" \
  inc card 'FIRQDrv'
claim "     and its descriptor FT0 with it"                          inc card 'FT0'
claim "⛔ and NOT on the unbootable card's run - so it came off the card and not out of the ROM" \
  notin plain 'FIRQDrv'
claim "⛔ nor on the empty socket's"                                 notin nocard 'FIRQDrv'
# ...asked of the HOST as well, which is the arbiter: if the ROM's own
# bootfile carried FIRQDrv the claims above would pass on nothing
# ⚠ `FIRQDrv` IS NOT IN EITHER FILE AS A STRING.  An OS-9 module name is
# high-bit terminated, so the bytes are `FIRQDr` + $F6 - and a host-side grep
# for the whole name matches NOTHING and makes the negative form pass
# vacuously.  Six characters, and the positive form beside it is what proves
# the pattern can match at all.
claim "⛔ and the ROM DISK's OS9Boot does not contain it (the host asks)" \
  sh -c "! grep -qa FIRQDr '$REC/bootfile'"
claim "   while the card's does - so the pattern is one that CAN match" \
  sh -c "grep -qa FIRQDr '$OUT/cardboot'"

# --- 3. it is a working machine, in all three states ----------------------
for s in card plain nocard; do
  claim "[$s] the machine reached a shell"                inc $s '{Term|02}/DD:'
  claim "[$s] the run ended at the last command"          grep -q 'SERIAL_STOP seen' "$OUT/$s/emu.txt"
  claim "[$s] no crash: nothing printed D.Crash's '!'"    notin $s '![0-9A-F][0-9A-F]'
  claim "[$s] the CPU never ran through empty RAM (WILD)" sh -c "! grep -q '^WILD' '$OUT/$s/emu.txt'"
done
# ⚠ /DD IS STILL THE ROM DISK EVEN WHEN THE BOOT CAME OFF THE CARD.  Only
# OS9Boot moved; the system disk is a separate decision (sdcard.md §9.5) and
# this is where that is stated rather than assumed.
claim "⭐ /DD is the ROM disk in every case - only OS9Boot moved" \
  inc card 'OS9Boot *CMDS *MODULES *SYS *startup'
claim "   and the card is still an ordinary RBF volume beside it" inc card 'CMDS *DATA'
claim "   whose own OS9Boot the host tools wrote"                 inc card '"arm6309 boot" created'
claim "⛔ and the control card mounts too - it is readable and simply not blessed" \
  inc plain '"arm6309 data" created'

echo
echo "      $n claims, $fail failed        (consoles in $OUT/{card,plain,nocard}/console.txt)"
[ "$fail" -eq 0 ] || exit 1
