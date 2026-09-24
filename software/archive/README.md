# `software/archive/` — retired software

Programs and tools that are no longer built or run, kept whole as the record. Like
[`../../hardware/archive/`](../../hardware/archive/), what is here is **frozen** and
still citable: nothing in it describes the present machine.

| | What | Retired | Replaced by |
|---|---|---|---|
| [`demo/`](demo/) | the bare-metal show for the archived `video/` card — raster bars, per-scanline palette, a Zelda segment, a MOD — and its benches | 2026-09-20, with the card | the desktop and its applications. ⚠ Four of its tools were live and moved out: `frames.py`, `show.py`, `mkshow.py` and `mkparrots.py` to `../tools/`, and `mkgame.py` to `../zelda/bench/` |
| [`overworld/`](overworld/) | the tile-mode Zelda-like overworld for the `video/` card: `vgmodel.py`'s streams and checker | 2026-09-23 | [`../zelda/`](../zelda/) |
| [`pinball/`](pinball/) | three pinball tables before `pcs` | 2026-09-23 | [`../pcs/`](../pcs/) |
| [`zelda/`](zelda/) | the Zelda-like overworld as a video3 room game: its generators, art, terrain model (`mkgame.py`) and demo video | 2026-09-24 | [`../tilescroll/`](../tilescroll/), whose creatures are zelda's cast (`bench/cast.py`) |
| [`paint/`](paint/) | `ansi-original.py`, this project's own ANSI piece, which `v3art` drew so the icon would work without Blocktronics' file | 2026-09-24 | `v3art` is *we-tortuga* only ([`../paint/`](../paint/)) |
| [`nitros9-video/`](nitros9-video/) | the recorded NitrOS-9 demo sessions (`session.py`, `session3.py`, `run-video3.sh`) and their committed build output | 2026-09-21 | [`../desk/video/`](../desk/video/), which runs the program rather than a recording |

The 6809 sources of retired programs are in `../nitros9`'s `level2/arm6309/archive/`.
