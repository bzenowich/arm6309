# `software/paint/reference/`

| File | What | Tracked |
|---|---|---|
| `we-tortuga.ans` | Blocktronics' *we-tortuga*, from the 2016 *Block 'n' Roll* pack on 16colo.rs — the ANSI art `v3art` shows | ✗ — not this project's work |
| `we-tortuga.ans.png` | its reference render, which the stream's colours are checked against | ✗ |

`tools/v3show.py`'s `have_art()` looks here; without the file the ANSI-art stream is
left out and everything else builds.
