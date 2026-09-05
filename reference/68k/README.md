# `reference/68k/`

68000-era material. **Reading, not a build input** — nothing in this repository targets a
68000, and no document cites these files.

**Not tracked in git.** Fetch them yourself; the table says where from.

| Expected file | What | Where from |
|---|---|---|
| `Mac-Plus.ROM` | Macintosh Plus ROM image | Apple's, and not redistributable. Dump your own, or obtain it the way emulator users do. |
| `102658076_quickdraw_acc.zip` | Apple **QuickDraw** source, released by the Computer History Museum (catalogue no. 102658076) | [computerhistory.org](https://computerhistory.org/blog/macpaint-and-quickdraw-source-code/) — one click, free, registration-free |
| `102658076_macpaint_acc.zip` | Apple **MacPaint** source, same CHM release | same page |

QuickDraw is here for the same reason `docs/coco3_c64.md` is: it is the best-documented
worked example of getting a lot of graphics out of very little hardware, and
`video/docs/graphics.md`'s span writer solves a related problem in TTL.

> ⚠ **These were tracked in git until 2026-09-04, and should not have been.** The
> argument was that they are small — which is true and beside the point.
> `Mac-Plus.ROM` is Apple's copyrighted ROM image carrying no redistribution grant of
> any kind. The CHM archives were released under Apple's own terms **for
> non-commercial use distributed via CHM**, which grants nothing about onward
> redistribution; the previous revision of this file acknowledged they are "not
> covered by this project's licensing" and tracked them regardless.
>
> `reference/README.md`'s reason for keeping the ~93 MB of scans out of history —
> that they are freely available from the vendors — applies *more* strongly here, not
> less: the CHM download is a single click. Size was never the criterion; the right to
> redistribute is.
>
> **They are gone from the working tree and the index, but they remain in the
> repository's history**, which is where a copyright claim would find them. Purging
> them needs `git filter-repo` and a force push to the GitHub remote — a rewrite of
> published history, and the owner's call, not a cleanup a review gets to perform.
> See `docs/design-review.md` §Sys-M6.
