# `software/nitros9/bench/` — NitrOS-9 off the SD card

### ⭐ `run-v3sd.sh` — the desktop, Paint and a demo, all **off the SD card**

```sh
sh software/nitros9/bench/run-v3sd.sh           # two runs, 29 claims, ~3 min. Its exit code is the answer
```

Every other bench here types a command that is *inside the boot ROM*, and
reads data that is inside it too. This one boots the machine with **both**
cards — video3 and the storage card at `$FF58` (`hardware/storage/docs/sdcard.md`
§9.4) — and runs the Haiku desktop, Paint, `changefont` and `mvania` from a
card that `software/nitros9/mksddisk.sh` wrote with the host's `os9` tools. It
is about **where the program and its data came from**, so the scene is 28
frames and no more; `run-v3mv.sh` is what measures a scene.

⭐ **Two halves, and they are found two different ways.** The desktop and
Paint are *streams*, `copy`d to a window — so the path is the caller's
already, and `copy /sd0/data/v3desk /w3` is the whole change.
`changefont` is a program that opens a file **for itself**, and it now names
the face without a directory and lets `DOpen` (card, then `/DD/SYS`) decide;
`overworld`, `rastbar` and `wave` do the same.

⛔ **Everything `copy` and `display` do comes before `chx /sd0/cmds`**, and
that is not tidiness: after the execution directory moves to the card, the
only things the shell can fork are the card's own commands and shell+'s
merged built-ins. `copy` lives in `/DD/CMDS` and becomes unfindable.

⭐ **The claim is that a picture was PAINTED, not that a command was typed.**
`checkv3sd.py` reduces the recording to `frames`, `painted`, `changed` and two
*shapes*:

| | |
|---|---|
| `desk` | one colour over ≥ 45% of the frame **and** ≥ 40 colours — a big flat background with icons, a Deskbar and window chrome on it |
| `paint` | ≥ 20% of the frame **pure white** and ≥ 40 colours — Paint's page under Haiku chrome |

⚠ Measured and not guessed: the finished desktop is 50.8% one colour with 54
colours; Paint is 35.5% its top colour, 27–34% white, 50 colours; the no-card
control is **one colour over the whole frame**. The scene's own colour values
are deliberately not in the test, so repainting the desktop cannot fail a
claim about loading a file. ⚠ An earlier cut asked for **64 colours** and
failed a run whose picture was perfect — `mvania`'s room is a stylised
side-view, not a dithered photograph. The number to pick is the one the
*control* cannot reach.

⛔ **And the control is the same ROM, the same keystrokes and an empty
socket.** `/SD0` refuses at §9.0 with `E$NotRdy`; every `copy` says so;
`changefont`'s bare name misses **both** legs of `DOpen` and reports the ROM's
`E$PNNF`; and the demo is `E$PNNF` rather than a hang. ⛔ **A blank screen is
not a pass**: `iniz w3` and `display 1b 21` need no card, so the control still
records eleven hundred frames — of nothing. `desk` and `paint` must both be
zero.

⭐ **One error is expected in the card run and it is deliberate.**
`changefont /sd0/data/nosuchface` gives an explicit path to a face that is not
there, and an override the caller asks for is not second-guessed. The bench
requires **exactly one** `Error #` — two would mean the *first* `changefont`,
a bare name that goes through `DOpen`, had not found its face on the card. So
the count is the positive claim about `DOpen` as well.

Five more claims said the ROM disk carried none of it — `mvania` not in
`/DD/CMDS`, the desktop, Paint and the faces not in `/DD/SYS`, `errmsg` still
there. ⚠ **They are about a disk that no longer exists** (2026-09-22): `/DD`
is the card, so what they now assert is that the *card* carries the demo only
when a bench asked for it.
