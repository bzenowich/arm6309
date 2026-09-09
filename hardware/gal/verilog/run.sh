#!/bin/sh
# Generate the video card's Verilog from the term lists, then compile and run
# every testbench. From hardware/: npm run check:video
set -e
cd "$(dirname "$0")"
V="verilator --binary --timing -Wall -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC"
CARD="video_card.v vctrl.v vaddr.v rfa.v vlen.v"
fail=0
for tb in vsync vaddr vtile vspan audio mainboard; do
  case $tb in
    vsync) SRC="vctrl.v" ;;
    audio) SRC="audio.v" ;;
    mainboard) SRC="mainboard.v ../clkdec.v ../mmu.v u9.v u10.v" ;;
    *)     SRC="$CARD" ;;
  esac
  $V --top-module ${tb}_tb $SRC ${tb}_tb.sv -o ${tb}_tb > /dev/null
  ./obj_dir/${tb}_tb || fail=1
done
exit $fail
