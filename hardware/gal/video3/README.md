# `hardware/gal/video3/` — video3's CPLD designs

```sh
cd hardware
bun run gal/video3/v3scan.cpld.ts > gal/video3/v3scan.pld       # the term list -> CUPL
sh gal/prjbureau/fit1508.sh gal/video3/v3scan.pld               # place and route
V3_MAPQ=discrete bun run gal/video3/v3scan.cpld.ts > gal/video3/v3scan_mq.pld
sh gal/prjbureau/fit1508.sh gal/video3/v3scan_mq.pld
```

⛔ **One fit at a time** — the Wine prefix is one shared working directory, and two
concurrent fits write the same `cpld/<name>.fit`. And **"Design fits successfully"
appears only in the fitter's stdout, never in the `.fit`**: `fit1508.sh` requires that
sentence, which is the only thing standing between a failed fit and a *convincing*
`.fit` left over from the last one. `CLAUDE.md`'s trap list has both.

| | cells | I/O | cascades | |
|---|---|---|---|---|
| `v3scan` | 114 / 128 | ⚠ **63 / 64** | 16 | the map word in silicon |
| `v3scan_mq` | 82 / 128 | 46 / 64 | 16 | ⭐ the map word in four `'574` |

⭐ **`V3_MAPQ=discrete` is a switch and not a comment**, the way `ARM6309_LIST` is in
`gal/video.cpld.ts`, because both sides of it are fitted and the difference is the
answer to `video3/docs/partition.md` §5 risk 2.

## Not written yet

`v3dot`, `v3ptr`, `v3host`. `v3scan` was fitted first because `partition.md` §2.2 called
it the tightest, and because it carries the address mux — `graphics.md` §10.1.2's "the
one place merging costs silicon rather than saving it".
