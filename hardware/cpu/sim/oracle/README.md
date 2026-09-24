# `hardware/cpu/sim/oracle/` — what `hd6309.c` is checked against

Nothing here is a 6309. It is the harness around two things this repository does not
carry, and must not: both are **fetched at a pinned commit into `hardware/cpu/build/oracle/`**
and never copied into the tree.

| | what | licence | used for |
|---|---|---|---|
| `fetch-xroar.sh`, `xroar_run.c`, `xroar_stubs.c` | **XRoar's HD6309 core** (Ciaran Anscomb), built with our harness into `xroar_run`, which writes the trace `test/run6309.c` writes | GPL-3.0 — a separate program, never linked into ours | the differential: `test/run.sh` §(a2), `test/cmp6309.py` |
| `checkcyc.py` | **hoglet67's 6809Decoder** (`em_6809.c`): per-opcode cycles validated against logic-analyser captures of real HD6309s, and the Burke & Burke addendum's indexed postbyte tables | none stated — read, never copied | the cycle table: `hd6309.silicon` and `hd6309.c`'s `IX_EM`/`IX_NM` must equal it |

`hardware/cpu/docs/6309.md` §4.1 is the design; the order of trust (silicon, then the
book, then XRoar) is at the top of `hd6309.c`.
