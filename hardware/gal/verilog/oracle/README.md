# `oracle/` — this card against an independent Paula

```sh
sh gal/verilog/oracle/run-oracle.sh        # from hardware/
```

**Why it exists.** `audio_tb.sv` was written from the same understanding that produced
the design, so it can only confirm the design does what its author thought. That is not
a theoretical worry here: on 2026-09-10 **two audible defects survived 43 green claims,
a design review and a port census**, and what found them was this — a second
implementation of Paula, written by other people from the hardware reference manual,
driven with the same register writes and diffed
([`audio.md`](../../../../audio/docs/audio.md) §16 item 36).

⚠ **And a green `modcompare` says nothing about it.** `audio/tools/modcompare/` A/Bs
`audio/refplayer/` — a **C model** of this card — against libopenmpt, and has agreed
almost perfectly since 2026-09-04. `card.c` ends a buffer with `if (--ch->cnt == 0u)`,
which is right; the hardware ended it on a borrow, which was not. **Two independent
implementations of one paragraph, and the A/B only ever tested one of them.**

| | |
|---|---|
| `fetch-paula.sh` | pulls `Paula.v` to a scratch directory. ⛔ **It is not vendored** — its header says GPL v3 and its repository says CC BY-NC 4.0, which are incompatible with each other and with a hardware project that might one day be sold |
| `paula_oracle_tb.sv` | **ours.** Drives Paula, prints the sample-byte stream |
| `card_oracle_tb.sv` | **ours.** Drives this card, prints the same |
| `run-oracle.sh` | builds each as a **separate binary** and compares the printed output |

⛔ **Two binaries, never one.** Nothing here links against `Paula.v`. That is cleaner
legally, and it is better testing: no shared harness bug can cancel out in both halves.

## What the harness has to supply, and what that cost

**Paula does not fetch its own samples.** It raises a data request and *Agnus* delivers
the word and owns the pointer, so an Agnus is part of the oracle — and three of its four
bugs looked exactly like findings before they were understood:

| Symptom | Cause |
|---|---|
| `AUDxLEN` and `AUDxPER` read back 0 while `DMACON` took | RGA was left asserted for the data colour clock, so every register was written a second time with zero. **DMACON survived because "clear these bits: none" is a no-op** — a harness bug that hides itself in three registers out of four |
| `fetches=0`, which looks like a chip that never asks | Paula multiplexes one audio state machine across four channels and every control output is a four-bit **rotating** shift register. It only reads as "bit *i* is channel *i*" while `cck` is high. Sampling mid-rotation sees channel 3's bit in channel 0's place |
| `fetches=1` and then silence | Paula **holds** the request until Agnus answers, so an Agnus that waits for a rising edge answers once and waits for ever |
| the sample walking 04 05 06 07 … off the end of the buffer | the restart flag is `dmasen \| lenfin`, not `dmasen` alone — `r_dmal[7] <= r_AUDxDR[0] & (r_dmasen[0] \| r_lenfin[0])`, and `r_lenfin` is `r_lenctr == 1` |

⚠ **An oracle is a claim and needs the same scepticism as the design.** Every one of
those produced a plausible "difference" that was the harness's, not the card's.

## What is compared, and what deliberately is not

**The stream of sample bytes each design presents to its converter** — not audio. Both
defects item 36 found were errors in *which bytes are played and how many*, which the
digital path decides on its own.

⚠ **The steady state is the claim; the first pass is not.** Both designs have a start-up
transient and they are *different* transients, for reasons recorded rather than fixed:
Paula discards the first word fetched after `DMACON` (an Agnus cycle this harness cannot
settle — item 36), and this card does not strobe its priming byte into the converter and
loads its count one short of what priming needs (item 39). The comparison drops the first
loop and asserts that what repeats is the same cyclic sequence.

⚠ **Compared as a cycle, not as a string.** The two reach the same loop at different
points in it, so a literal comparison of two tails reports `04 05 02 03 …` against
`05 02 03 04 …` and calls a match a failure.
