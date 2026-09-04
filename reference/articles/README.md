# `reference/articles/`

Prior art and design history — writing rather than specification. **Not in git** — see
[`../README.md`](../README.md).

| File | What | Cited by |
|---|---|---|
| `folklore-apple2-mouse-card.pdf` | Andy Hertzfeld, *Apple II Mouse Card*, folklore.org, June 1981. Burrell Smith's two-chip mouse interface: a 6522 VIA and a dual flip-flop, where the Apple II division later shipped "more than a dozen" chips. | `io/ps2/docs/ps2.md` §4.4 — the interrupt argument, the derive-it-from-the-bus habit, and §4.4(c)'s rejection of interrupt-per-notch |

Original at <https://www.folklore.org/Apple_II_Mouse_Card.html>.

**These are narratives, not schematics.** `ps2.md` §1 grades this one accordingly: a
first-hand account by someone who wrote the driver, which is strong evidence for *why* a
design was shaped a certain way and weak evidence for any specific pin.
