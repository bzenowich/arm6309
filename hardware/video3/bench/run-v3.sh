#!/bin/sh
# All three video3 exercisers on the host emulator.
#
#   sh hardware/video3/bench/run-v3.sh        ~1 min
#
# ⚠ Its exit code is the answer.
set -e
cd "$(dirname "$0")/../../.."
fail=0
for b in v3char v3copy v3sprite v3tile; do
  sh "video3/bench/run-$b.sh" || fail=1
done
[ $fail -eq 0 ] && echo "\nok    video3's four exercisers agree with the plan" \
               || echo "\nFAIL  see above"
exit $fail
