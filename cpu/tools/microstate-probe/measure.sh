#!/usr/bin/env bash
# Cycle-count the microstate probe.  cpu/docs/plan.md §3.3(d).
#
# Compiles with the SAME flags as the firmware target (see CMakeLists.txt) and
# runs each function body through llvm-mca's Cortex-M4 model.
#
# What the numbers mean, and do not mean:
#   - llvm-mca models the M4 as an in-order scalar pipeline and assumes every
#     memory access hits with no wait states.  That matches the hot loop's
#     actual home (CCM SRAM, zero-wait, §3.4(1)) but it is still a MODEL.
#   - Functions containing branches are counted as if every instruction
#     executes, which over-counts -- conservative, i.e. the safe direction.
#   - Silicon is the arbiter.  These numbers exist to size a design decision
#     before hardware, not to replace the Phase 1 measurement.

set -euo pipefail

CC=${CC:-arm-none-eabi-gcc}
MCA=${MCA:-llvm-mca-18}
OPT=${OPT:--O2}
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${OUT:-$(mktemp -d)}
mkdir -p "$OUT"

CFLAGS=(-mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard
        "$OPT" -ffreestanding -fno-common
        -Wall -Wextra -Wshadow -Wundef -Wconversion)

"$CC" "${CFLAGS[@]}" -S "$HERE/microstates.c" -o "$OUT/microstates.s"
"$CC" "${CFLAGS[@]}" -S "$HERE/tuned.c"       -o "$OUT/tuned.s"
cat "$OUT/tuned.s" >> "$OUT/microstates.s"

# Pull one function body out of the .s and strip everything that is not an
# instruction: directives, literal-pool data, and comment-only lines.
extract() {
    awk -v fn="$1" '
        $0 ~ "^"fn":$"          { inside = 1; next }
        inside && $0 ~ "\\.size" { inside = 0 }
        inside                   { print }
    ' "$OUT/microstates.s" |
    grep -vE '^\s*\.(align|size|type|thumb|syntax|global|section|word|short|byte|ascii|space|fnstart|fnend|cantunwind|save|setfp|pad|eabi)' |
    grep -vE '^\s*@' |
    grep -vE '^\s*$'
}

printf '%-18s %8s %8s %8s   %s\n' FUNCTION INSNS CYCLES BRANCHES NOTE
printf '%.0s-' {1..64}; echo

for fn in ms_idx_postinc ms_adda ms_addd ms_tfm_step ms_sample_ctrl \
          cyc_adda_tuned cyc_sample_ctrl_tuned cyc_full_adda_tuned \
          cyc_idx_postinc_tuned cc_materialise ctrl_decode; do
    extract "$fn" > "$OUT/$fn.s"

    cyc=$("$MCA" -mtriple=thumbv7em-none-eabi -mcpu=cortex-m4 -iterations=1 \
              "$OUT/$fn.s" 2>/dev/null | awk '/^Total Cycles:/ {print $3}')
    ins=$("$MCA" -mtriple=thumbv7em-none-eabi -mcpu=cortex-m4 -iterations=1 \
              "$OUT/$fn.s" 2>/dev/null | awk '/^Instructions:/ {print $2}')
    # Any branch means llvm-mca's straight-line count is an over-estimate.
    br=$(grep -cE '^\s+(b|bl|blx|bx|beq|bne|bcs|bcc|bmi|bpl|bhi|bls|bge|blt|bgt|ble|cbz|cbnz)(\.[nw])?\s' "$OUT/$fn.s" || true)

    note=""
    [ "${br:-0}" -gt 1 ] && note="control flow -> upper bound"
    printf '%-18s %8s %8s %8s   %s\n' "$fn" "${ins:-?}" "${cyc:-?}" "${br:-0}" "$note"
done

echo
echo "assembly kept in $OUT"

echo
echo "=== tuned hand-written hot path (cpu/tools/microstate-probe/tuned.S) ==="
"$MCA" -mtriple=thumbv7em-none-eabi -mcpu=cortex-m4 -iterations=1 \
    "$HERE/tuned.S" 2>/dev/null |
  awk '/Code Region/ {sub(/.*- /,"",$0); r=$0}
       /^Instructions:/ {i=$2}
       /^Total Cycles:/ {printf "%-24s %4s insns %5s cycles\n", r, i, $3}'
