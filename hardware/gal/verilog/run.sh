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
# ⛔ THE `video` CARD'S FIVE ARE GONE FROM HERE (2026-09-22).  They left the
# default on 2026-09-20 when the card was archived, and stayed runnable by name
# because `machine_tb` and `demo_tb` still instantiated the card.  Neither does
# now - the boot ROM was retargeted, and `demo_tb` followed its benches into
# `archive/video/bench/`.  ⚠ `video_card.v` and the generated `vctrl.v`,
# `vaddr.v` and `vsup.v` are STILL HERE and still emitted by `gen.ts`; what is
# gone is anything that executes them.  `archive/video/bench/README.md` is the
# record of that, and `archive/README.md` §"What did NOT move" the trade.
TBS=${TBS:-"audio mainboard storage v3dot v3card v3machine"}
out=$(mktemp)
trap 'rm -f "$out"' EXIT

for tb in $TBS; do
  case $tb in
    # Every source named, not found. Verilator resolves an undeclared module
    # by searching the current directory, so "vctrl.v" and "audio.v" alone
    # compiled - and a stale or renamed file would have been picked up the
    # same way, silently (2026-09-11).
    # ⛔ AND THE ARCHIVED CARD'S NAMES ANSWER, rather than failing obscurely
    # three steps later on a missing .sv file.
    vsync|vaddr|vtile|vspan|vpal)
      echo "FAIL  '$tb' is the archived video/ card's bench - archive/video/bench/"
      exit 1 ;;
    audio)     SRC="audio_card.v audio.v aseq.v" ;;
    mainboard) SRC="mainboard.v ../clkdec.v ../mmu.v u9.v u10.v" ;;
    # ⭐ the storage card, with a behavioural SPI-mode SD card in the socket.
    # sd_model.v is a model of the PART, not of anything this project makes,
    # so it is hand-written and nothing fits it.
    storage)   SRC="storage_card.v sdbus.v sdeng.v sd_model.v" ;;
    # ⭐ video3: the raster part alone. There is no video3_card.v yet - the
    # cadence needs one, and this does not pretend to be it.
    v3dot)     SRC="v3dot.v" ;;
    # ⭐ video3 as a card: the four parts and the board around them. Every
    # buried cell is left unconnected on purpose - a cell is not a net until
    # it leaves its package - so PINMISSING is the design, not a slip.
    v3card)    SRC="-Wno-PINMISSING video3_card.v v3dot.v v3scan.v v3ptr.v v3host.v v3lane.v" ;;
    # ⭐ video3 as a MACHINE: a 6809E in the socket, the motherboard under it
    # and the card in the slot, running software/v3boot's fixture ROM. Asked
    # for by name - it is not in the default TBS. ⚠ About 40 s: 5 s of
    # simulation (59 ms of machine time) and the rest Verilator compiling a
    # 6809E core it compiles for nothing else.
    v3machine)
      ROM=../../../software/v3boot/v3boot.hex
      if [ ! -f "$ROM" ] || [ ../../../software/v3boot/v3boot.asm -nt "$ROM" ]; then
        sh ../../../software/v3boot/mkv3rom.sh
      fi
      # ⚠ THE VENDOR CORE'S WARNINGS ARE WAIVED ON THIS LINE AND NOWHERE ELSE,
      # exactly as run-machine.sh waives them: hardware/vendor/mc6809/README.md
      # keeps the four .v files byte-identical to upstream, so the waivers
      # travel with the compile rather than with the source. ⭐ And not
      # -Wno-lint: a warning in machine3.v or v3machine_tb.sv is still an error.
      W="-Wno-SIDEEFFECT -Wno-UNOPTFLAT -Wno-CASEX -Wno-GENUNNAMED -Wno-PINMISSING"
      W="$W -Wno-UNUSEDPARAM -Wno-VARHIDDEN -Wno-TIMESCALEMOD -Wno-CASEINCOMPLETE"
      W="$W -Wno-BLKSEQ -Wno-SYNCASYNCNET -Wno-MULTIDRIVEN -Wno-LATCH"
      W="$W -Wno-UNSIGNED -Wno-CMPCONST --timescale 1ns/1ps"
      SRC="$W machine3.v mainboard.v ../clkdec.v ../mmu.v u9.v u10.v"
      SRC="$SRC video3_card.v v3dot.v v3scan.v v3ptr.v v3host.v v3lane.v"
      # ⚠ NAMED THOUGH v3machine LEAVES THE SLOT EMPTY (machine3.v STORAGE = 0,
      # so the card is in a dead generate branch): Verilator resolves an
      # instantiated module by searching the current directory, and a file it
      # found rather than was given is the 2026-09-11 trap this case list
      # exists to close.
      SRC="$SRC storage_card.v sdbus.v sdeng.v sd_model.v"
      SRC="$SRC ../../vendor/mc6809/mc6809e.v ../../vendor/mc6809/mc6809i.v" ;;
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
