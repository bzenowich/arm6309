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
set -e
cd "$(dirname "$0")"

ROM=../../../software/boot/boot.hex
if [ ! -f "$ROM" ] || [ ../../../software/boot/boot.asm -nt "$ROM" ]; then
  sh ../../../software/tools/mkrom.sh
fi

# ⚠ THE VENDOR CORE'S WARNINGS ARE WAIVED ON THE COMMAND LINE AND NOWHERE ELSE.
# hardware/vendor/mc6809/README.md: the four .v files are byte-identical to
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
# (archive/README.md). machine.v, video_card.v, vctrl.v, vaddr.v and vsup.v are
# all still here and demo_tb.sv still compiles them.
# ⚠ -Wno-PINMISSING is on the WAIVE line above because video3_card.v leaves
# every buried macrocell unconnected on purpose - a cell is not a net until it
# leaves its package - which is the same reason run.sh waives it for v3card.
SRC="machine3.v mainboard.v ../clkdec.v ../mmu.v u9.v u10.v"
SRC="$SRC video3_card.v v3dot.v v3scan.v v3ptr.v v3host.v v3lane.v"
SRC="$SRC audio_card.v audio.v aseq.v"       # elaborated only when AUDIO = 1
SRC="$SRC tl16c550.v"                         # the console; answers only when SERIAL = 1
# ⭐ AND THE STORAGE CARD SINCE 2026-09-21, with a behavioural SDHC card in
# its socket: boot.asm 10b reads block 0 over SPI to decide whether the boot
# dialog says "Disk found", and a stub that cannot answer CMD0 can only ever
# make it say no (machine3.v's header).
SRC="$SRC storage_card.v sdbus.v sdeng.v sd_model.v"
SRC="$SRC ../../vendor/mc6809/mc6809e.v ../../vendor/mc6809/mc6809i.v"

$V --top-module machine_tb $SRC machine_tb.sv -o machine_tb > /dev/null

# The logs are KEPT. A mktemp removed on EXIT deletes the FAIL lines of the run
# that failed - run-modplay.sh paid for that once already.
OUT=${OUT:-/tmp/arm6309-machine}
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
case " $SCENARIOS " in *" nitros9 "*|*" reboot "*)
  sh ../../../software/nitros9/mkrom.sh /tmp/arm6309-nitros9 || exit 1 ;;
esac
# ⭐ AND TWO MORE, `disk` and `nodisk`: boot.asm 10a's boot dialog
# (docs/boot-and-desktop.md 1). They differ in one bit - machine3.v's sd_cd,
# which is SDSTAT b1, "a card is in the socket":
#   SCENARIOS="disk nodisk" npm run check:machine
#
# ⛔ AND THEIR ROM IS A V3=1 ROM, IN A DIRECTORY OF ITS OWN. The toolbox is
# ROM page 64 and recipes/arm6309/arm6309.mak only builds it under -DV3=1
# (`TBOX = tbox` is inside that ifneq) - without the flag page 64 is 8 KB of
# zeros, boot.asm 10a finds no "TB" there, reports $63 and skips the dialog,
# and every claim about the picture would be waiting for a progress code that
# never comes. The `nitros9` and `reboot` runs above build the OTHER flavour,
# so the two cannot share an output directory.
case " $SCENARIOS " in *" disk "*|*" nodisk "*)
  V3=1 sh ../../../software/nitros9/mkrom.sh /tmp/arm6309-dialog || exit 1 ;;
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
SDB=128                                   # sd_model.v's NBLOCKS for this machine
case " $SCENARIOS " in *" disk "*)
  D=/tmp/arm6309-dialog
  N9=${NITROS9DIR:-$(cd ../../../../nitros9 2>/dev/null && pwd)}
  [ -f "$N9/recipes/arm6309/l2/bootfile" ] || {
    echo "FAIL  no $N9/recipes/arm6309/l2/bootfile - the ROM build did not run"; exit 1; }
  BOOT="$N9/recipes/arm6309/l2/bootfile" NAME="arm6309 boot" \
    sh ../../../software/nitros9/mksddisk.sh "$D/sdboot.img" overworld > "$D/mksddisk.log" 2>&1 || {
      cat "$D/mksddisk.log"; echo "FAIL  the bootable card image did not build"; exit 1; }
  head -c $((SDB * 512)) "$D/sdboot.img" > "$D/sdcard.bin"
  pad=$((SDB * 512 - $(wc -c < "$D/sdcard.bin")))
  [ "$pad" -gt 0 ] && dd if=/dev/zero bs=1 count=$pad >> "$D/sdcard.bin" 2>/dev/null
  od -An -v -tx1 -w16 "$D/sdcard.bin" | tr -s ' ' '\n' | grep -v '^$' > "$D/sdcard.hex"
  [ "$(wc -l < "$D/sdcard.hex")" -eq $((SDB * 512)) ] || {
    echo "FAIL  $D/sdcard.hex is not $((SDB * 512)) records"; exit 1; }
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
  [ "$sc" = "disk" ] && SDARG="+sdimage=/tmp/arm6309-dialog/sdcard.hex"
  ./obj_dir/machine_tb $ARGS $SDARG +scenario=$sc | tee "$log"
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
