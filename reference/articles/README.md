# `reference/articles/`

Prior art and design history — writing rather than specification. **Not in git** — see
[`../README.md`](../README.md).

| File | What | Cited by |
|---|---|---|
| `folklore-apple2-mouse-card.pdf` | Andy Hertzfeld, *Apple II Mouse Card*, folklore.org, June 1981. Burrell Smith's two-chip mouse interface: a 6522 VIA and a dual flip-flop, where the Apple II division later shipped "more than a dozen" chips. | `io/ps2/docs/ps2.md` §4.4 — the interrupt argument, the derive-it-from-the-bus habit, and §4.4(c)'s rejection of interrupt-per-notch |
| `gal.html` + `gal_files/` | Frank DeCaire, *Generic Array Logic Devices*, January 2017. Reverse-engineers the GAL16V8 JEDEC fuse map by hand, having failed to find a PALASM in any language but FORTRAN, and programs a part from it. | `hardware/gal/jedec/README.md` — the fuse-polarity convention (`0` is an intact link), and the demonstration that hand-writing a fuse map is ordinary rather than exotic |

Originals at <https://www.folklore.org/Apple_II_Mouse_Card.html> and
<https://www.decaire.net/2017/01/22/generic-array-logic-devices/>.

**The GAL article is about the 16V8, and this machine's parts are 22V10s.** Nearly
everything specific in it — `SYN`, `AC0`, `AC1`, the `PTD` fuses, "simple mode" — is
16V8 OLMC plumbing that the 22V10 does not have; the 22V10 has two config bits per
macrocell and no mode word. What transfers is the method, the fuse polarity, and the
warning about how long it takes to get right by trial and error.

**These are narratives, not schematics.** `ps2.md` §1 grades this one accordingly: a
first-hand account by someone who wrote the driver, which is strong evidence for *why* a
design was shaped a certain way and weak evidence for any specific pin.
