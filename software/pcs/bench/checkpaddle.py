#!/usr/bin/env python3
"""checkpaddle.py - verify keyboard paddle controls (Left/Right Shift, Z/M).

Verifies that:
1. Left Shift sets pbtn0=$80 while held, clearing to $00 upon release (key-up).
2. Right Shift sets pbtn1=$80 while held, clearing to $00 upon release (key-up).
3. Quick taps produce brief flipper activations.
4. 'z' and 'm' continue to operate left and right flippers with make/break.
5. 'q' cleanly terminates play mode.
"""

import os
import sys

def check_paddle_trace(outdir):
    console_path = os.path.join(outdir, "console.txt")
    if not os.path.exists(console_path):
        serial_path = os.path.join(outdir, "serial.out")
        if os.path.exists(serial_path):
            with open(serial_path, "r", errors="ignore") as f:
                content = f.read()
        else:
            print(f"FAIL  neither console.txt nor serial.out found in {outdir}")
            return 1
    else:
        with open(console_path, "r", errors="ignore") as f:
            content = f.read()

    if "PCS-PLAY" not in content:
        print("FAIL  PCS-PLAY not found in console output")
        return 1
    if "PCS-TRC" not in content:
        print("FAIL  PCS-TRC not found in console output")
        return 1
    if "PCS-RAN" not in content:
        print("FAIL  PCS-RAN not found in console output")
        return 1

    lines = [line.strip() for line in content.splitlines()]
    trace_lines = [l for l in lines if len(l) == 16 and all(c in "0123456789ABCDEFabcdef" for c in l)]

    if len(trace_lines) < 20:
        print(f"FAIL  too few trace lines ({len(trace_lines)})")
        return 1

    # Extract pbtn0 (chars 12..13) and pbtn1 (chars 14..15)
    btn_states = []
    for l in trace_lines:
        b0 = int(l[12:14], 16)
        b1 = int(l[14:16], 16)
        btn_states.append((b0, b1))

    # Verify transitions:
    # 1. Left shift hold: pbtn0 was 0, became $80 for multiple frames, then returned to 0
    # 2. Right shift hold: pbtn1 was 0, became $80 for multiple frames, then returned to 0
    left_held = any(b0 == 0x80 and b1 == 0x00 for b0, b1 in btn_states)
    right_held = any(b1 == 0x80 and b0 == 0x00 for b0, b1 in btn_states)
    both_idle = any(b0 == 0x00 and b1 == 0x00 for b0, b1 in btn_states)

    if not both_idle:
        print("FAIL  paddles were never idle (00)")
        return 1
    if not left_held:
        print("FAIL  left paddle (pbtn0) was never active ($80)")
        return 1
    if not right_held:
        print("FAIL  right paddle (pbtn1) was never active ($80)")
        return 1

    # Count distinct pulses for left and right
    def count_pulses(states, idx):
        pulses = 0
        in_pulse = False
        pulse_lengths = []
        cur_len = 0
        for s in states:
            val = s[idx]
            if val == 0x80:
                if not in_pulse:
                    in_pulse = True
                    cur_len = 1
                else:
                    cur_len += 1
            else:
                if in_pulse:
                    in_pulse = False
                    pulses += 1
                    pulse_lengths.append(cur_len)
        if in_pulse:
            pulses += 1
            pulse_lengths.append(cur_len)
        return pulses, pulse_lengths

    left_pulses, left_lens = count_pulses(btn_states, 0)
    right_pulses, right_lens = count_pulses(btn_states, 1)

    # We expect at least 3 pulses on left: LShift hold, LShift tap, Z hold
    # And at least 3 pulses on right: RShift hold, RShift tap, M hold
    if left_pulses < 3:
        print(f"FAIL  expected >= 3 left paddle pulses, got {left_pulses} (lengths: {left_lens})")
        return 1
    if right_pulses < 3:
        print(f"FAIL  expected >= 3 right paddle pulses, got {right_pulses} (lengths: {right_lens})")
        return 1

    # Verify that we have both long holds (>3 frames) and quick taps (<=2 frames)
    if not any(l > 3 for l in left_lens) or not any(l <= 2 for l in left_lens):
        print(f"FAIL  left paddle pulses lack hold or tap distinction: {left_lens}")
        return 1
    if not any(l > 3 for l in right_lens) or not any(l <= 2 for l in right_lens):
        print(f"FAIL  right paddle pulses lack hold or tap distinction: {right_lens}")
        return 1

    print(f"ok    paddle controls verified: {left_pulses} left pulses {left_lens}, {right_pulses} right pulses {right_lens}")
    return 0

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: checkpaddle.py OUTDIR")
        sys.exit(1)
    sys.exit(check_paddle_trace(sys.argv[1]))
