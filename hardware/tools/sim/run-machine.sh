#!/bin/sh
# The whole machine: a 6809E, the motherboard, video3 and the audio card,
# running the boot ROM's own instructions.
#
#   npm run check:machine            (from hardware/)
#   TRACE=40 npm run check:machine   ... with the first 40 bus cycles printed
#   SCENARIOS=main npm run check:machine   ... the boot run alone
#
# EXIT CODE IS THE ANSWER, for the reason run.sh states: a testbench reports a
# failed claim and then calls $finish, which exits 0.
_here=$(cd "$(dirname "$0")" && pwd)   # before any cd: $0 may be relative
set -e
cd "$(dirname "$0")"
# ⭐ everything this writes - Verilator's objects, the screenshots, the logs -
# goes to hardware/tools/build/, which is this directory's depth, so the
# benches' ../../../software/... paths hold from it too
BUILD=$(cd .. && pwd)/build
mkdir -p "$BUILD"
# the NitrOS-9 port's ROMs are that component's build output
N9ROM=$(cd ../../../software/nitros9 && pwd)/build/rom
N9DLG=$(cd ../../../software/nitros9 && pwd)/build/dialog

ROM=../../../software/boot/build/boot.hex
if [ ! -f "$ROM" ] || [ ../../../software/boot/boot.asm -nt "$ROM" ]; then
  sh ../../../software/tools/mkrom.sh
fi

# ⚠ THE VENDOR CORE'S WARNINGS ARE WAIVED ON THE COMMAND LINE AND NOWHERE ELSE.
# hardware/cpu/sim/mc6809/README.md: the four .v files are byte-identical to
# upstream and must stay that way, so the copyright notice and the BSD terms
# travel intact. Every waiver below is one mc6809i.v raises:
#
#   SIDEEFFECT  functions called inside a concatenation on the LHS of an assign
#   UNOPTFLAT   the address depends on the byte just read, which is a real loop
#               in a real 6809E too and settles the same way
#   CASEX       its instruction decode is casex, which is what a decode is
#
# ⭐ AND NOT -Wno-lint, which is the lazy version: this project's OWN files are
# still checked, and a warning that appears in machine.v or machine_tb.sv is
# still an error here.
WAIVE="-Wno-SIDEEFFECT -Wno-UNOPTFLAT -Wno-CASEX -Wno-GENUNNAMED -Wno-PINMISSING"
WAIVE="$WAIVE -Wno-UNUSEDPARAM -Wno-VARHIDDEN -Wno-TIMESCALEMOD -Wno-CASEINCOMPLETE"
WAIVE="$WAIVE -Wno-BLKSEQ -Wno-SYNCASYNCNET -Wno-MULTIDRIVEN -Wno-LATCH"
WAIVE="$WAIVE -Wno-UNSIGNED -Wno-CMPCONST"

V="verilator --binary --timing -Wall -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL"
V="$V -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC $WAIVE --timescale 1ns/1ps"

# ⭐ machine3.v SINCE 2026-09-20, not machine.v: software/boot/boot.asm drives
# video3 now and the archived `video` card's four files left this line with it
# (hardware/archive/README.md). machine.v, video_card.v, vctrl.v, vaddr.v and vsup.v are
# all still here and demo_tb.sv still compiles them.
# ⚠ -Wno-PINMISSING is on the WAIVE line above because video3_card.v leaves
# every buried macrocell unconnected on purpose - a cell is not a net until it
# leaves its package - which is the same reason run.sh waives it for v3card.
# each card's models live in its own sim/ directory (hardware/<card>/sim/)
H=$(cd ../.. && pwd)
MB=$H/mainboard/sim AU=$H/audio/sim ST=$H/storage/sim V3=$H/video3/sim
SER=$H/io/serial/sim CPU=$H/cpu/sim/mc6809
SRC="-I$AU -I$MB -I$ST -I$V3 $H/tools/sim/machine3.v $MB/mainboard.v $MB/clkdec.v $MB/mmu.v $MB/u9.v $MB/u10.v"
SRC="$SRC $V3/video3_card.v $V3/v3dot.v $V3/v3scan.v $V3/v3ptr.v $V3/v3host.v $V3/v3lane.v"
SRC="$SRC $AU/audio_card.v $AU/audio.v $AU/aseq.v"       # elaborated only when AUDIO = 1
SRC="$SRC $SER/tl16c550.v"                         # the console; answers only when SERIAL = 1
# ⭐ AND THE STORAGE CARD SINCE 2026-09-21, with a behavioural SDHC card in
# its socket: boot.asm 10b reads block 0 over SPI to decide whether the boot
# dialog says "Disk found", and a stub that cannot answer CMD0 can only ever
# make it say no (machine3.v's header).
SRC="$SRC $ST/storage_card.v $ST/sdbus.v $ST/sdeng.v $ST/sd_model.v"
SRC="$SRC $CPU/mc6809e.v $CPU/mc6809i.v"

$V --Mdir "$BUILD/obj_machine" --top-module machine_tb $SRC machine_tb.sv -o machine_tb > /dev/null

# The logs are KEPT. A mktemp removed on EXIT deletes the FAIL lines of the run
# that failed - run-modplay.sh paid for that once already.
OUT=${OUT:-$(cd "$_here/.." && pwd)/build/machine}
mkdir -p "$OUT"

ARGS=""
[ -n "$TRACE" ] && ARGS="+trace=$TRACE"
[ -n "$AFTER" ] && ARGS="$ARGS +after=$AFTER"
[ -n "$HB" ] && ARGS="$ARGS +hb=$HB"

# ⭐ SEVEN RUNS. `main` is the boot on four SIMMs. `s1`-`s3` are the other
# populations ram.md 6.4.1's walk must report, and `alias` a 1M x 8 module it
# must reject. In `e1` (no SIMM) and `e2` (a corrupted VRAM byte) boot.asm's
# error path is the right answer and is asserted as such. SCENARIOS narrows it:
# SCENARIOS=main for the boot alone.
SCENARIOS=${SCENARIOS:-"main e1 s1 s2 s3 alias e2 disk nodisk"}
# ⭐ AND AN EIGHTH THAT IS NOT IN THAT LIST: `nitros9` boots NitrOS-9 Level 2
# from reset through boot.asm to a shell on the UART and types `dir` - about
# 2.5 s of machine, which is minutes here, so it is asked for by name:
#   SCENARIOS=nitros9 npm run check:machine
# and a ninth, `reboot`: boot, then F$Debug's reboot back through boot.asm's POST
# to a second prompt:
#   SCENARIOS=reboot npm run check:machine
# It needs the port's ROM, built from $NITROS9DIR (software/nitros9/README.md).
# ⛔ CPU=6809, because machine3.v's CPU is mc6809e.v: the recipe builds for the
# 6309 by default since 2026-09-24, and a 6309 build on a 6809 core runs until
# its first 6309 opcode and then does something else (hardware/cpu/docs/6309.md).
# ⭐ ONE ROM FOR ALL FOUR SINCE 2026-09-22.  They used to be two flavours in
# two directories; `recipes/arm6309/arm6309.mak` puts -DV3=1 in AFLAGS itself
# now, so there is one build and $N9ROM is where it goes.
case " $SCENARIOS " in *" nitros9 "*|*" reboot "*)
  CPU=6809 sh ../../../software/nitros9/mkrom.sh $N9ROM || exit 1 ;;
esac
# ⭐ AND TWO MORE, `disk` and `nodisk`: boot.asm 10a's boot dialog
# (software/desk/docs/boot-and-desktop.md 1). They differ in one bit - machine3.v's sd_cd,
# which is SDSTAT b1, "a card is in the socket":
#   SCENARIOS="disk nodisk" npm run check:machine
#
# ⚠ THEY USED TO NEED A ROM OF THEIR OWN. The toolbox is ROM page 64 and the
# recipe only built it under -DV3=1, so a default build left page 64 blank,
# boot.asm 10a found no "TB" there, reported $63 and skipped the dialog - and
# every claim about the picture waited for a progress code that never came.
# ⭐ Since 2026-09-22 every build has the toolbox, so this is the SAME ROM as
# the two above; it keeps its own directory only so that a run of
# SCENARIOS="disk nodisk" alone still builds one.
case " $SCENARIOS " in *" disk "*|*" nodisk "*)
  CPU=6809 sh ../../../software/nitros9/mkrom.sh $N9DLG || exit 1 ;;
esac
# ⭐ AND `disk` NEEDS A CARD THE ROM WILL ACTUALLY BOOT FROM, because since
# 2026-09-21 "Disk found" means sdcard.md 9.5's signature over a non-zero
# DD.BT and not a closed socket switch. software/nitros9/mksddisk.sh writes
# one, BOOT= and all, and sd_model.v reads its first SDBLOCKS*512 bytes
# through $readmemh.
#
# ⚠ THE HEX IS PADDED AND TRUNCATED TO EXACTLY THAT, and both halves matter:
# $readmemh warns and stops early on a short file and errors on a long one,
# and either way the card in the socket would not be the card on disk.
# ⛔ 1792, NOT 128, SINCE 2026-09-22: `nitros9` and `reboot` boot NitrOS-9 OFF
# THE CARD now, and mksyscard.sh's image is ~898 KB.  machine_tb.sv's SDB is
# the same number and sd_model.v's array is NBLOCKS*512 bytes; a smaller one
# would wrap a read of the bootfile back onto block 0 (`arg % NBLOCKS`).
SDB=1792                                  # sd_model.v's NBLOCKS for this machine

# ⭐ hexcard <image> <out-base> - pad or truncate to SDB blocks and $readmemh it
hexcard() {
  head -c $((SDB * 512)) "$1" > "$2.bin"
  pad=$((SDB * 512 - $(wc -c < "$2.bin")))
  [ "$pad" -gt 0 ] && dd if=/dev/zero bs=1 count=$pad >> "$2.bin" 2>/dev/null
  od -An -v -tx1 -w16 "$2.bin" | tr -s ' ' '\n' | grep -v '^$' > "$2.hex"
  [ "$(wc -l < "$2.hex")" -eq $((SDB * 512)) ] || {
    echo "FAIL  $2.hex is not $((SDB * 512)) records"; exit 1; }
}

# ⛔ AND `nitros9`/`reboot` NEED THE SYSTEM CARD, because the ROM has carried no
# filesystem since 2026-09-22.  mkrom.sh writes system.img beside the ROM out of
# the same build, so the modules on the card are the modules in that ROM's
# recipe - which is the only way `mdir`'s answer means anything.
case " $SCENARIOS " in *" nitros9 "*|*" reboot "*)
  D=$N9ROM
  [ -f "$D/system.img" ] || { echo "FAIL  no $D/system.img - mkrom.sh should have built it"; exit 1; }
  hexcard "$D/system.img" "$D/sdcard"
  sig=$(sed -n '241,248p' "$D/sdcard.hex" | tr -d '\n')
  [ "$sig" = "3633303901000000" ] || {
    echo "FAIL  the system card carries $sig at LSN 0 +\$F0, not the boot signature"; exit 1; }
  ;;
esac

case " $SCENARIOS " in *" disk "*)
  D=$N9DLG
  N9=${NITROS9DIR:-$(cd ../../../../nitros9 2>/dev/null && pwd)}
  [ -f "$N9/recipes/arm6309/l2/bootfile" ] || {
    echo "FAIL  no $N9/recipes/arm6309/l2/bootfile - the ROM build did not run"; exit 1; }
  OUT="$D" DATA="$D/data" NAME="arm6309 boot" NITROS9DIR="$N9" \
    sh ../../../software/nitros9/mksyscard.sh "$D/sdboot.img" tilescroll > "$D/mksddisk.log" 2>&1 || {
      cat "$D/mksddisk.log"; echo "FAIL  the bootable card image did not build"; exit 1; }
  hexcard "$D/sdboot.img" "$D/sdcard"
  # ⛔ AND THE SIGNATURE IS CHECKED HERE TOO, because a card image that lost
  # it would make `disk` draw the question mark and read as a ROM defect.
  sig=$(sed -n '241,248p' "$D/sdcard.hex" | tr -d '\n')
  [ "$sig" = "3633303901000000" ] || {
    echo "FAIL  the card image carries $sig at LSN 0 +\$F0, not the boot signature"; exit 1; }
  ;;
esac
ok=0; bad=0; missing=0
for sc in $SCENARIOS; do
  log="$OUT/$sc.log"
  SDARG=""
  [ "$sc" = "disk" ] && SDARG="+sdimage=$N9DLG/sdcard.hex"
  case "$sc" in nitros9|reboot) SDARG="+sdimage=$N9ROM/sdcard.hex" ;; esac
  (cd "$BUILD" && ./obj_machine/machine_tb $ARGS $SDARG +scenario=$sc) | tee "$log"
  ok=$((ok + $(grep -c '^ok' "$log" || true)))
  bad=$((bad + $(grep -c '^FAIL' "$log" || true)))
  # A run that crashed or hit the backstop prints no OK summary. It counts.
  if ! grep -q '^machine_tb .*OK - ' "$log" && ! grep -q '^FAIL' "$log"; then
    echo "FAIL  machine_tb [$sc] produced no summary line"
    missing=$((missing + 1))
  fi
done

echo
echo "$ok claims, $((bad + missing)) failed        (logs in $OUT)"
[ "$bad" -eq 0 ] && [ "$missing" -eq 0 ]
