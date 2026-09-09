#!/bin/sh
# Generate the video card's Verilog from the term lists, then compile and run
# every testbench. From hardware/: npm run check:video
#
# EXIT CODE IS THE ANSWER. A testbench reports a failed claim and then calls
# $finish, which exits 0 - so "the simulation ran" and "the design is right"
# were the same exit status until 2026-09-09, and a broken card looked like a
# passing build to anything reading $?. Each run is filtered for FAIL lines
# here and the count decides the status.
set -e
cd "$(dirname "$0")"
V="verilator --binary --timing -Wall -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC"
CARD="video_card.v vctrl.v vaddr.v vsup.v"
TBS=${TBS:-"vsync vaddr vtile vspan vpal audio mainboard"}
out=$(mktemp)
trap 'rm -f "$out"' EXIT

for tb in $TBS; do
  case $tb in
    vsync)     SRC="vctrl.v" ;;
    audio)     SRC="audio.v" ;;
    mainboard) SRC="mainboard.v ../clkdec.v ../mmu.v u9.v u10.v" ;;
    *)         SRC="$CARD" ;;
  esac
  $V --top-module "${tb}_tb" $SRC "${tb}_tb.sv" -o "${tb}_tb" > /dev/null
  "./obj_dir/${tb}_tb" | tee -a "$out"
done

ok=$(grep -c '^ok' "$out" || true)
bad=$(grep -c '^FAIL' "$out" || true)
echo
echo "$ok claims, $bad failed"
[ "$bad" -eq 0 ]
