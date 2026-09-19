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
TBS=${TBS:-"vsync vaddr vtile vspan vpal audio mainboard v3dot v3card"}
out=$(mktemp)
trap 'rm -f "$out"' EXIT

for tb in $TBS; do
  case $tb in
    # Every source named, not found. Verilator resolves an undeclared module
    # by searching the current directory, so "vctrl.v" and "audio.v" alone
    # compiled - and a stale or renamed file would have been picked up the
    # same way, silently (2026-09-11).
    vsync)     SRC="$CARD" ;;
    audio)     SRC="audio_card.v audio.v aseq.v" ;;
    mainboard) SRC="mainboard.v ../clkdec.v ../mmu.v u9.v u10.v" ;;
    # ⭐ video3: the raster part alone. There is no video3_card.v yet - the
    # cadence needs one, and this does not pretend to be it.
    v3dot)     SRC="v3dot.v" ;;
    # ⭐ video3 as a card: the four parts and the board around them. Every
    # buried cell is left unconnected on purpose - a cell is not a net until
    # it leaves its package - so PINMISSING is the design, not a slip.
    v3card)    SRC="-Wno-PINMISSING video3_card.v v3dot.v v3scan.v v3ptr.v v3host.v v3lane.v" ;;
    *)         SRC="$CARD" ;;
  esac
  $V --top-module "${tb}_tb" $SRC "${tb}_tb.sv" -o "${tb}_tb" > /dev/null
  # TBARGS reaches the bench as plusargs: `TBARGS=+ONLY=sprite` runs v3card_tb's
  # sprite scenarios alone, for a debug loop - never for a claim count.
  "./obj_dir/${tb}_tb" ${TBARGS:-} | tee -a "$out"
done

ok=$(grep -c '^ok' "$out" || true)
bad=$(grep -c '^FAIL' "$out" || true)
echo
echo "$ok claims, $bad failed"
[ "$bad" -eq 0 ]
