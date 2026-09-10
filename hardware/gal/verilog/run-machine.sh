#!/bin/sh
# The whole machine: a 6809E, the motherboard and the video card, running the
# boot ROM's own instructions.
#
#   npm run check:machine            (from hardware/)
#   TRACE=40 npm run check:machine   ... with the first 40 bus cycles printed
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

SRC="machine.v mainboard.v ../clkdec.v ../mmu.v u9.v u10.v"
SRC="$SRC video_card.v vctrl.v vaddr.v vsup.v"
SRC="$SRC ../../vendor/mc6809/mc6809e.v ../../vendor/mc6809/mc6809i.v"

$V --top-module machine_tb $SRC machine_tb.sv -o machine_tb > /dev/null

out=$(mktemp)
trap 'rm -f "$out"' EXIT

ARGS=""
[ -n "$TRACE" ] && ARGS="+trace=$TRACE"
[ -n "$AFTER" ] && ARGS="$ARGS +after=$AFTER"
[ -n "$HB" ] && ARGS="$ARGS +hb=$HB"
./obj_dir/machine_tb $ARGS | tee "$out"

ok=$(grep -c '^ok' "$out" || true)
bad=$(grep -c '^FAIL' "$out" || true)
echo
echo "$ok claims, $bad failed"
[ "$bad" -eq 0 ]
