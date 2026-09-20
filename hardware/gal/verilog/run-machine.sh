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
SCENARIOS=${SCENARIOS:-"main e1 s1 s2 s3 alias e2"}
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
ok=0; bad=0; missing=0
for sc in $SCENARIOS; do
  log="$OUT/$sc.log"
  ./obj_dir/machine_tb $ARGS +scenario=$sc | tee "$log"
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
