# `software/tracker/reference/`

Reference ProTracker modules (.MOD files) used for verification and bundled on the system card.

**Not in git**: Reference MOD files under any `reference/` are `.gitignore`d (see [the root `reference/` README](../../../reference/README.md)). Expected contents, and what cites each:

| File | What | Cited by |
|---|---|---|
| `Guitar-Slinger.mod` | 4-channel ProTracker MOD by Jogeir Liljedahl (1990), 406,354 bytes, 41 patterns, 31 samples | `software/nitros9/mkrom.sh` (bundled into `/dd/data/`), `software/tracker/docs/features.md` §3 — reference test for multi-pattern (>40 patterns) on-demand loading and Sound Card SRAM streaming |
| `Physical-Presence.mod` | 4-channel ProTracker MOD by 4-Mat / Matthew Simmonds (1992), 285,004 bytes, 49 patterns, 31 samples | `software/nitros9/mkrom.sh` (bundled into `/dd/data/`), `software/tracker/docs/features.md` §3 — reference test for dense effect sequencing and large pattern table navigation |
