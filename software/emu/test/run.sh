#!/bin/sh
# cpu6809.c against mc6809e.v, the core every machine simulation runs.
#
#   sh software/emu/test/run.sh
#   SEEDS=8 CYC=3000000 SECS=40 ITRACE=1 DEMO=software/archive/demo sh software/emu/test/run.sh
#
# EXIT CODE IS THE ANSWER: 0 only if every claim below printed ok.
#
#  (a) SEEDS generated exercisers (gen.py), each run for CYC E cycles on both
#      cores under the same pseudo-random IRQ/FIRQ/NMI schedule: the traces -
#      every register at every instruction boundary, every write with its E
#      cycle - are identical; together they execute every documented opcode;
#      and every instruction length the Verilog shows is the datasheet's or
#      one of the exceptions cpu6809.c's header lists (cycles.py).
#  (b) the demo's replayer on demo_run.c for SECS seconds of music: its
#      register trace and sample RAM are refplayer's, compared exactly as
#      bench/run-replay.sh compares the Verilog's.
#  (c) ITRACE=1: the same demo run on demo_run.c and on bench/replay_tb.sv
#      (as demo_tb.sv) is identical instruction by instruction, for the whole
#      run. ~4 minutes of Verilator; ITRACE=0 skips it.
#
# Build products and traces go in obj_c/, obj_cpu/ and obj_demo/ beside this
# file. Traces of passing seeds are deleted; a failing seed's are kept.
set -u
cd "$(dirname "$0")"
T=$(pwd)
ROOT=$(cd ../../.. && pwd)
DEMO=${DEMO:-$ROOT/software/archive/demo}       # another checkout's software/archive/demo, if this one is mid-edit
SEEDS=${SEEDS:-8}
CYC=${CYC:-3000000}
SECS=${SECS:-40}
ITRACE=${ITRACE:-1}
O=$T/obj_c
mkdir -p "$O"
fail=0
say() { echo "$@"; }
V="verilator --binary --timing -Wno-fatal -Wno-lint -Wno-style --timescale 1ns/1ps"
CORE="$ROOT/hardware/cpu/sim/mc6809/mc6809e.v $ROOT/hardware/cpu/sim/mc6809/mc6809i.v"

# ---- build ---------------------------------------------------------------------
CC="gcc -std=c99 -O2 -Wall -Wextra -Werror -D_POSIX_C_SOURCE=199309L"
$CC -o "$O/cpu_run" ../cpu6809.c ../hd6309.c cpu_run.c || { say "FAIL  cpu_run does not build"; exit 1; }
$CC -o "$O/demo_run" ../cpu6809.c ../hd6309.c demo_run.c || { say "FAIL  demo_run does not build"; exit 1; }
$V --top-module cpu_tb -Mdir obj_cpu $CORE cpu_tb.sv -o cpu_tb > "$O/cpu_tb_build.log" 2>&1 ||
  { tail -20 "$O/cpu_tb_build.log"; say "FAIL  cpu_tb does not build"; exit 1; }
$CC -I.. -o "$O/refuse6309" ../cpu6809.c ../hd6309.c refuse6309.c || { say "FAIL  refuse6309 does not build"; exit 1; }
say "ok    built cpu_run, demo_run (-Wall -Wextra -Werror) and cpu_tb"

# ---- (a0) the 6309 refusal set -------------------------------------------------
# ⛔ This core is a 6809 and the machine's CPU is an HD6309E.  Every 6309-only
# encoding must be REFUSED rather than decoded as its 6809 ghost - see
# arm6309 hardware/cpu/docs/6309.md §4.0 and armio.asm:513.  Two claims: the generated
# header still matches the checked-in table, and the core acts on it.
python3 mk6309tab.py --from-tab > /dev/null 2>&1 || { say "FAIL  cannot regenerate hd6309ops.h from hd6309.tab"; fail=1; }
if git -C "$ROOT" diff --quiet -- software/emu/hd6309ops.h 2>/dev/null; then
  say "ok    hd6309ops.h is what hd6309.tab generates"
else
  say "FAIL  hd6309ops.h and hd6309.tab disagree - re-run test/mk6309tab.py"; fail=1
fi
"$O/refuse6309" || fail=1

# ---- (a1) the 6309 core, and TFM's decided semantics ---------------------------
# ⭐ hardware/cpu/docs/plan.md §4.3.1: this core completes the byte before it takes an
# interrupt, so an interrupted TFM loses nothing. The control build models what
# SILICON does and is required to fail - a test that cannot see the difference
# is not testing the specification.
python3 mkimg.py tfm.asm "$O/tfm.bin" > /dev/null || { say "FAIL  tfm.asm does not assemble"; fail=1; }
$CC -I.. -o "$O/tfm6309" ../cpu6809.c ../hd6309.c tfm6309.c || { say "FAIL  tfm6309 does not build"; fail=1; }
$CC -I.. -DHD6309_FAITHFUL_TFM -o "$O/tfm_sil" ../cpu6809.c ../hd6309.c tfm6309.c || { say "FAIL  tfm_sil does not build"; fail=1; }
"$O/tfm6309" "$O/tfm.bin" || fail=1
"$O/tfm_sil" "$O/tfm.bin" || fail=1

# ⭐ and the cycle counts, against Appendix A of The 6309 Book via hd6309.tab.
# A wrong one is invisible - the instruction does the right thing and the
# machine is the wrong speed - and software/toolbox/docs/proportional-font.md quotes benchmarks
# that rest on them. It found 20 of 32 forms wrong on its first run.
$CC -I.. -o "$O/one6309" ../cpu6809.c ../hd6309.c one6309.c || { say "FAIL  one6309 does not build"; fail=1; }
python3 cyc6309.py || fail=1

# ---- (a) the exercisers, four at a time -------------------------------------------
one_seed() {
  s=$1
  python3 gen.py "$s" "$O" --maxcyc "$CYC" --undoc || { echo "FAIL" > "$O/seed_$s.result"; return; }
  timeout 1200 "$O/cpu_run" "$O/prog_$s.bin" "$O/prog_$s.sched" "$O/c$s.trace" "$CYC" "$O/prog_$s.cov" > "$O/c$s.log" 2>&1
  crc=$?
  timeout 1200 obj_cpu/cpu_tb +image="$O/prog_$s.hex" +sched="$O/prog_$s.sched" +trace="$O/v$s.trace" +maxcyc="$CYC" > "$O/v$s.log" 2>&1
  vrc=$?
  if [ $crc -ne 0 ] || [ $vrc -ne 0 ] || grep -q FAIL "$O/v$s.log"; then
    echo "FAIL run (cpu_run $crc, cpu_tb $vrc)" > "$O/seed_$s.result"
  elif cmp -s "$O/v$s.trace" "$O/c$s.trace"; then
    echo "ok" > "$O/seed_$s.result"
  else
    echo "FAIL differ" > "$O/seed_$s.result"
  fi
}
s=1
while [ $s -le "$SEEDS" ]; do
  j=0
  while [ $j -lt 4 ] && [ $s -le "$SEEDS" ]; do
    one_seed $s &
    s=$((s + 1)); j=$((j + 1))
  done
  wait
done
covs=""
traces=""
nb=0; nw=0; ni=0
s=1
while [ $s -le "$SEEDS" ]; do
  r=$(cat "$O/seed_$s.result" 2>/dev/null || echo "FAIL no result")
  if [ "$r" = ok ]; then
    # "cpu_tb: B boundaries, W writes, C cycles; entries IRQ i FIRQ f NMI n, from CWAI w"
    set -- $(sed -n 's/^cpu_tb: \([0-9]*\) boundaries, \([0-9]*\) writes.*IRQ \([0-9]*\) FIRQ \([0-9]*\) NMI \([0-9]*\), from CWAI \([0-9]*\)/\1 \2 \3 \4 \5 \6/p' "$O/v$s.log")
    nb=$((nb + $1)); nw=$((nw + $2)); ni=$((ni + $3 + $4 + $5 + $6))
    say "ok    seed $s: identical - $1 boundaries, $2 writes, interrupts IRQ $3 FIRQ $4 NMI $5 (+$6 out of CWAI)"
    covs="$covs $O/prog_$s.cov"
    traces="$traces $O/prog_$s.bin $O/v$s.trace"
  else
    say "FAIL  seed $s: $r"
    fail=1
    if [ -f "$O/v$s.trace" ] && [ -f "$O/c$s.trace" ]; then
      say "      first difference (< Verilog, > C), with the lines before it:"
      line=$(cmp "$O/v$s.trace" "$O/c$s.trace" 2>/dev/null | sed -n 's/.* line \([0-9]*\).*/\1/p')
      if [ -n "$line" ]; then
        from=$((line > 6 ? line - 6 : 1))
        sed -n "${from},$((line - 1))p" "$O/v$s.trace" | sed 's/^/        /'
        sed -n "${line},$((line + 3))p" "$O/v$s.trace" > "$O/v.head"
        sed -n "${line},$((line + 3))p" "$O/c$s.trace" > "$O/c.head"
        diff "$O/v.head" "$O/c.head" | sed 's/^/      /'
      fi
    fi
    cat "$O/c$s.log" "$O/v$s.log" 2>/dev/null | sed 's/^/      /'
  fi
  s=$((s + 1))
done
if [ $fail -eq 0 ]; then
  say "ok    $SEEDS exercisers identical: $nb instruction boundaries, $nw writes, $ni interrupt entries"
  if "$O/cpu_run" --report $covs; then
    say "ok    every documented 6809 opcode executed on both cores"
  else
    say "FAIL  a documented opcode never ran - raise SEEDS or CYC"; fail=1
  fi
  python3 cycles.py $traces || fail=1
  s=1
  while [ $s -le "$SEEDS" ]; do rm -f "$O/v$s.trace" "$O/c$s.trace"; s=$((s + 1)); done
fi

# ---- (b) the replayer against refplayer ----------------------------------------------
if [ ! -f "$DEMO/build/rom-replay.bin" ] || [ ! -f "$DEMO/build/demo.mod" ]; then
  sh "$DEMO/build.sh" || { say "FAIL  software/archive/demo/build.sh"; exit 1; }
fi
"$ROOT/hardware/audio/build/host/refplayer" --trace "$O/ref.trace" --sram "$O/ref.sram" --seconds "$SECS" "$DEMO/build/demo.mod" > /dev/null ||
  { say "FAIL  refplayer"; exit 1; }
TICKS=$(tail -1 "$O/ref.trace" | awk '{print $1+0}')
timeout 600 "$O/demo_run" --rom "$DEMO/build/rom-replay.bin" --trace "$O/replay.trace" --sram "$O/replay.sram" \
  --ticks $((TICKS + 1)) > "$O/demo_run.log" 2>&1 || { cat "$O/demo_run.log"; fail=1; }
cat "$O/demo_run.log"
awk -v t="$TICKS" '$1+0 <= t' "$O/replay.trace" > "$O/replay.cmp"
awk -v t="$TICKS" '$1+0 <= t' "$O/ref.trace" > "$O/ref.cmp"
if cmp -s "$O/replay.cmp" "$O/ref.cmp"; then
  say "ok    demo_run's register trace is refplayer's, byte for byte: $(wc -l < "$O/ref.cmp") writes over $TICKS ticks"
else
  say "FAIL  demo_run's register trace differs from refplayer's - first difference:"
  diff "$O/ref.cmp" "$O/replay.cmp" | head -12
  fail=1
fi
if cmp -s "$O/replay.sram" "$O/ref.sram"; then
  say "ok    the sample RAM demo_run's 6809 uploaded is refplayer's loader's, $(wc -l < "$O/ref.sram") bytes"
else
  say "FAIL  the sample RAM differs"; fail=1
fi

# ---- (c) the demo, instruction by instruction, against the Verilog ------------------------
if [ "$ITRACE" = 1 ]; then
  python3 mkdemotb.py "$DEMO/bench/replay_tb.sv" "$O/demo_tb.sv" || exit 1
  $V --top-module demo_tb -Mdir obj_demo $CORE "$O/demo_tb.sv" -o demo_tb > "$O/demo_tb_build.log" 2>&1 ||
    { tail -20 "$O/demo_tb_build.log"; say "FAIL  demo_tb does not build"; exit 1; }
  rm -f "$O/v.fifo" "$O/c.fifo" "$O/icmp.out"
  mkfifo "$O/v.fifo" "$O/c.fifo" || exit 1
  # the readers first, so neither writer can open a FIFO that is not there yet;
  # every process bounded, so a writer that dies cannot leave the others waiting
  # both runs end a few cycles apart (each stops when it notices the last
  # tick), so the traces stop at a cycle both reach
  ITMAX=$(( $(sed -n 's/.* \([0-9]*\) E cycles in .*/\1/p' "$O/demo_run.log") - 30000 ))
  timeout 1800 cmp "$O/v.fifo" "$O/c.fifo" > "$O/icmp.out" 2>&1 &
  cmp_pid=$!
  timeout 1800 obj_demo/demo_tb +rom="$DEMO/build/rom-replay.hex" +trace="$O/demo_tb.trace" +ticks=$((TICKS + 1)) \
    +itrace="$O/v.fifo" +itracemax=$ITMAX > "$O/demo_tb.log" 2>&1 &
  v_pid=$!
  timeout 1800 "$O/demo_run" --rom "$DEMO/build/rom-replay.bin" --trace "$O/replay2.trace" --ticks $((TICKS + 1)) \
    --itrace "$O/c.fifo" --itrace-cycles $ITMAX > "$O/demo_run2.log" 2>&1 &
  c_pid=$!
  wait $cmp_pid; crc=$?
  wait $v_pid; wait $c_pid
  rm -f "$O/v.fifo" "$O/c.fifo"
  if [ $crc -eq 0 ]; then
    say "ok    the demo on demo_run.c and on replay_tb's mc6809e: identical at every instruction boundary and write for $ITMAX E cycles"
  else
    say "FAIL  the demo's instruction traces differ (cmp exit $crc): $(cat "$O/icmp.out")"
    line=$(sed -n 's/.* line \([0-9]*\).*/\1/p' "$O/icmp.out")
    if [ -n "$line" ]; then
      # run both again into files, as far as the difference, and show it
      "$O/demo_run" --rom "$DEMO/build/rom-replay.bin" --trace /dev/null --ticks $((TICKS + 1)) --itrace "$O/c.itrace" \
        --itrace-cycles $ITMAX > /dev/null 2>&1
      stopcyc=$(sed -n "$((line + 4))p" "$O/c.itrace" | awk '{print $1+1}')
      head -n $((line + 4)) "$O/c.itrace" > "$O/c.head"; rm -f "$O/c.itrace"
      timeout 1800 obj_demo/demo_tb +rom="$DEMO/build/rom-replay.hex" +trace=/dev/null +ticks=$((TICKS + 1)) \
        +itrace="$O/v.itrace" +itracemax="$stopcyc" > /dev/null 2>&1
      head -n $((line + 4)) "$O/v.itrace" > "$O/v.head"
      say "      (< Verilog, > C)"
      diff "$O/v.head" "$O/c.head" | head -12 | sed 's/^/      /'
    fi
    fail=1
  fi
fi

[ $fail -eq 0 ] && say "ok    run.sh: all claims hold" || say "FAIL  run.sh"
exit $fail
