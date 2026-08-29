# The Module Loader and Replayer
## Turning a `.mod` File Into Writes to the arm6309 Sound Card

**Question this answers:** [`audio.md`](audio.md) designs a card whose acceptance
test is "load an existing Amiga OCS module and play it back correctly". This is
the software that does that — what the loader has to parse and relocate, what the
replayer has to compute, and which of ProTracker's behaviours are *load-bearing*
rather than incidental.

**Short answer: the loader is a relocator and the replayer is a state machine,
and neither has to do any signal processing at all.** That is the whole payoff of
[`audio.md`](audio.md) §4.1 and §8.2 — because the card's period reference and
tempo clock are the Amiga's exact numbers, every value in the file transfers
verbatim and the only arithmetic in the system is address relocation. A converter
that has to resample, retune or requantise is a converter with a rounding error,
and modules are unforgiving about rounding errors in `PER`.

**Scope.** ProTracker-class 4-channel `.mod` (`M.K.`/`M!K!`), which is the corpus.
§2.3 says what to do about the variants. Everything here is written against
[`audio.md`](audio.md) §9's register map, so it runs unchanged on the discrete
card and on the §12.5 MCU bring-up card — which is the point of freezing that map
first.

---

## 0. Summary

| | |
|---|---|
| **Loader input** | a `.mod` file, 1084-byte header + patterns + 8-bit signed sample data |
| **Loader output** | sample data in card RAM, a 31-entry address table, a pattern buffer in system RAM |
| **What the loader transforms** | **addresses only.** Not periods, not volumes, not lengths, not finetune, not sample data |
| **Resident RAM** | patterns (typ. 10–30 KB) + ~4 KB of tables and code |
| **Card RAM** | 2 bytes of silence at `$00000` (the null-loop target) + sample data |
| **Replayer entry** | `/FIRQ` from the card's tempo timer ([`audio.md`](audio.md) §8.1) |
| **Tick rate** | `TIMER = 1773447 / BPM`, default BPM 125 → 50.002 Hz |
| **Per-tick cost** | ~900 cycles plain, ~2,200 on a row tick — **~2.7 % of a 2.098 MHz 6309** |
| **Worst-case margin** | 2,200 cycles against a 41,960-cycle tick budget — **19×** |
| **The one thing that must be exactly right** | the loop-pointer write *after* the DMA enable (§5.3) |

---

## 1. The two halves, and why they are separable

| | **Loader** | **Replayer** |
|---|---|---|
| Runs | once, at song load | 50–102 times a second, forever |
| Context | ordinary user code, can block on disk | `/FIRQ`, must not block |
| Language | C or assembly, does not matter | 6309 assembly, native mode |
| Touches | disk, system RAM, card sample RAM | card registers, pattern buffer |
| Cost | ~200 ms per song (§4.4) | ~2.7 % of the CPU (§7) |
| Fails by | rejecting a malformed file | losing a tick |

They share exactly one data structure — the **song image** of §3 — and nothing
else. Write them as separate modules; the loader can be replaced (a different
format, a different disk stack) without touching the replayer, and the replayer
is the piece that has to be perfect.

---

## 2. The `.mod` format

### 2.1 File layout

All multi-byte fields are **big-endian**, which is convenient: so is the 6309.

| Offset | Size | Field |
|---|---|---|
| 0 | 20 | song title, ASCII, NUL-padded |
| 20 | 930 | **31 sample headers**, 30 bytes each (§2.2) |
| 950 | 1 | song length in positions, 1–128 |
| 951 | 1 | restart position (historically `$7F`; ignore it — §10.9) |
| 952 | 128 | **order table**: pattern number for each position |
| 1080 | 4 | magic (§2.3) |
| 1084 | *n* × 1024 | **pattern data**, 64 rows × 4 channels × 4 bytes |
| — | rest | **sample data**, 8-bit signed, in sample order |

**Pattern count is not stored.** It is `1 + max(order[0..127])` — over the whole
128-entry table, not just the first `songlength` entries, because some modules
hide unreferenced patterns above the end and the sample data offset depends on
getting this right. Getting it wrong shifts every sample by a multiple of 1 KB,
which is the single most common loader bug.

### 2.2 Sample header — 30 bytes

| Offset | Size | Field | Goes to |
|---|---|---|---|
| 0 | 22 | name, ASCII | display only |
| 22 | 2 | **length in words** | `LEN` **verbatim** |
| 24 | 1 | finetune, low nibble, signed −8…+7 | period-table row |
| 25 | 1 | volume 0–64 | `VOL` **verbatim** |
| 26 | 2 | **repeat offset in words** | `LC` = base + 2 × offset |
| 28 | 2 | **repeat length in words** | `LEN` **verbatim** on the loop write |

Note the asymmetry that [`audio.md`](audio.md) §9.3 froze: **`LEN` stays in words,
`LC` becomes a byte address.** Lengths copy verbatim; only addresses are computed.

### 2.3 Variants, and what to do about each

| Magic at 1080 | Meaning | Do |
|---|---|---|
| `M.K.` | 31 samples, ≤64 patterns — **the corpus** | **play** |
| `M!K!` | 31 samples, >64 patterns | **play** — identical otherwise |
| `4CHN`, `FLT4` | 31 samples, 4 channels, other trackers | **play** |
| `M&K!`, `N.T.` | NoiseTracker variants | **play**, they are `M.K.`-compatible |
| *(none)* | 15-sample Soundtracker: 470-byte header table, order at 470, patterns at 600 | **play** — a second header parser, ~40 lines |
| `6CHN`, `8CHN`, `CD81`, `OKTA` | 6 or 8 channels | **reject for now** — [`audio.md`](audio.md) §11.2's 8-channel mode is unbuilt and unfitted |

**Detect by magic, not by file size.** A 15-sample module has no magic, so the
test is: read bytes 1080–1083; if they match a known 31-sample tag, use the
1084-byte layout; otherwise fall back to the 600-byte layout and validate (§4.6).

### 2.4 The pattern cell — 4 bytes per channel

```
  byte 0 :  s s s s p p p p     ssss = sample number, high nibble
  byte 1 :  p p p p p p p p     pppppppppppp = period, 12 bits
  byte 2 :  s s s s e e e e     ssss = sample number, low nibble; eeee = effect
  byte 3 :  x x x x x x x x     effect parameter
```

```
  sample = (b0 & $F0) | (b2 >> 4)          ; 0 = "no sample given"
  period = ((b0 & $0F) << 8) | b1          ; 0 = "no note given"
  effect = b2 & $0F
  param  = b3
```

On the 6309 this is four loads and some nibble work per cell — and `sample` is
the one field that has to be reassembled from two halves, which is why §4.5
recommends the loader pre-splits patterns if RAM allows.

**Period, not note number.** The file stores the *period value directly*, which is
why [`audio.md`](audio.md) §4.1's clock choice matters so much: `period` goes to
`PER` with no lookup at all when there is no finetune and no portamento. The
period table (§5.4) exists only for finetune, arpeggio and tone portamento, all
of which need to know *which note* a period is.

---

## 3. The song image

What the loader hands the replayer. Keep it flat and pointer-free where possible —
the replayer runs in `FIRQ` and every indirection is cycles.

```
song_image:
  +$000  order[128]         ; pattern number per position
  +$080  songlength         ; positions
  +$081  npatterns
  +$082  patterns_ptr       ; -> pattern buffer, npatterns * 1024 bytes
  +$084  sample_addr[32]    ; 3 bytes each: card-RAM BYTE address of sample n
  +$0E4  sample_len[32]     ; 2 bytes each: length in WORDS, verbatim
  +$124  sample_rep[32]     ; 3 bytes each: card-RAM BYTE address of repeat point
  +$184  sample_replen[32]  ; 2 bytes each: repeat length in WORDS, verbatim
  +$1C4  sample_vol[32]     ; 1 byte each, verbatim
  +$1E4  sample_ft[32]      ; 1 byte each, finetune 0..15 (as a table row index)
                            ; total $204 = 516 bytes
```

516 bytes plus the pattern buffer. **The tables hold 32 entries, not 31**, so the
pattern's sample number indexes them directly with no decrement — and entry 0 is
the null sample of §4.2, which is what makes "no sample given" and a corrupt
pattern byte both safe by construction rather than by a test in the `FIRQ` path.

**`sample_ft` stores the finetune as a table row index 0–15, not as the signed
−8…+7 the file holds.** The file's low nibble already *is* the row index in two's
complement order (`0…7` = finetune 0…+7, `8…15` = −8…−1), which is exactly how
ProTracker's period table is laid out. **Copy the nibble; do not sign-extend it.**
Sign-extending here is the second most common loader bug.

---

## 4. The loader

### 4.1 Stream, do not buffer

The naive loader reads the whole file into RAM and then copies the sample region
to the card. A 300 KB module does not fit in a 64 KB logical space, and even with
the MMU it wastes half the machine's RAM for 200 ms.

**Read the header, then the patterns, then stream sample data straight from disk
into `SDATA`.** The card's write pointer auto-increments, so the disk buffer can
be any size — 512 bytes is fine:

```
  1. read 1084 bytes                    -> header
  2. parse, compute npatterns, validate -> §4.6
  3. read npatterns * 1024 bytes        -> pattern buffer in system RAM
  4. SPTR <- $00000 ; SDATA <- 0, 0     -> the null-loop block (§4.2)
  5. for each sample 1..31:
        sample_addr[n] <- current card address
        stream sample_len[n]*2 bytes from disk -> SDATA
        fix up sample_rep[n] (§4.3)
  6. build the replayer's channel state, load TIMER, start
```

Peak resident memory is the pattern buffer plus one disk sector.

### 4.2 Card RAM layout, and the null-loop block

```
  $00000  $00 $00        <- THE NULL-LOOP BLOCK: two bytes of silence
  $00002  sample 1 data
          sample 2 data
          ...
```

**The two zero bytes at `$00000` are not padding — they are the mechanism by which
non-looping samples stop.** A `.mod` marks "no loop" with a repeat length of 0 or
1 word. Paula has no "stop at end" mode; it always reloads from `LC`/`LEN`. So the
idiom, on the Amiga and here, is to point the loop at two bytes of silence:

```
  if replen <= 1:   sample_rep[n] = $00000 ;  sample_replen[n] = 1
  else:             sample_rep[n] = sample_addr[n] + 2*repoffset ; replen verbatim
```

The channel then plays its one-shot, loops into the silent word, and holds `$00`
forever at whatever `PER` it was given — inaudible, and costing one sample fetch
every `PER` colour clocks that nobody hears. That is exactly what an Amiga does,
and it is why "turn the channel off when the sample ends" is *not* something the
replayer should try to do.

**Sample index 0** ("no sample given") points at the same null block, so a
malformed pattern cell can never make the card fetch from unwritten RAM.

### 4.3 Relocation is the only arithmetic

| Field | Transformation |
|---|---|
| Sample data | **copy verbatim** — 8-bit signed, same encoding, no requantisation |
| `length` (words) | **copy verbatim** into `sample_len` |
| `volume` (0–64) | **copy verbatim** |
| `finetune` nibble | **copy verbatim** as a row index (§3) |
| `repeat length` (words) | **copy verbatim**, except the ≤1 case of §4.2 |
| Periods in patterns | **copy verbatim** — same reference clock ([`audio.md`](audio.md) §4.1) |
| `Fxx` tempo bytes | **copy verbatim** — same CIA arithmetic ([`audio.md`](audio.md) §8.2) |
| Sample **start address** | `base + running offset` — **the only computed value** |
| Repeat **start address** | `sample_addr[n] + 2 × repoffset` — the only other one |

**Nothing else.** If a loader is doing arithmetic on a period, a volume or a
length, it is doing something wrong.

### 4.4 Upload cost, and the instruction that makes it cheap

The 6309's `TFM` has a **fixed-destination mode**, `TFM X+,Y`, which is exactly
"stream a block to an I/O port" — and `SDATA`'s auto-increment does the addressing
on the card side ([`audio.md`](audio.md) §13.2):

| | Cycles/byte | 128 KB @ 2.098 MHz |
|---|---|---|
| `LDA ,X+` / `STA SDATA` loop | ~10 | 625 ms |
| **`TFM X+,Y`** | **3** | **187 ms** |

`W` is 16 bits, so a >64 KB sample is two `TFM`s. In the streaming loader of §4.1
the block size is the disk buffer, so `TFM` is issued per sector and `W` never
approaches its limit.

**No `/WAIT`, no FIFO stall.** `TFM` sustains ~700 k writes/s against the card's
3.55 M/s posted-write retire rate — a 5× margin ([`audio.md`](audio.md) §9.3).
The card is the only one in the machine that never stalls the CPU, and this is
where that shows up.

### 4.5 An optional loader pass that pays for itself

If RAM allows, **pre-split the pattern data** from packed 4-byte cells into four
parallel arrays (`sample`, `period`, `effect`, `param`). It costs 25 % more
pattern RAM and removes the nibble reassembly of §2.4 from the `FIRQ` path — worth
roughly 25 cycles per channel per row tick, or ~0.05 % of the CPU. **Not worth it
on its own**, but it becomes worth it if §7's budget ever gets tight, and it is a
change the replayer does not see if the accessor is a macro.

Do not do it speculatively. Record it here so it is available.

### 4.6 Validate, and reject loudly

A `.mod` is a 1980s file format with no checksum, no length field and no version.
Every one of these has to be checked, because the failure mode of not checking is
the card fetching from unwritten RAM at 28 kHz:

| Check | Reject if |
|---|---|
| magic (§2.3) | unknown, or a channel count we cannot play |
| `songlength` | 0, or > 128 |
| order entries | > 127 |
| `npatterns` | pattern data would run past the file |
| sample lengths | sum exceeds card RAM (§4.7) |
| repeat offset | `2 × repoffset ≥ 2 × length` for a looped sample |
| sample length | odd (impossible — the field is in words) |
| file size | shorter than `1084 + npatterns×1024 + Σ sample bytes` |

**A truncated file is common** — the corpus is full of modules whose last sample
is short because a BBS transfer failed. Do not reject those: clamp
`sample_len[n]` to what actually arrived and play on. That is what every Amiga
player did, and it is the difference between playing 98 % of a corpus and 90 %.

### 4.7 When the module does not fit

[`audio.md`](audio.md) §5 populates 128 KB with footprints for 512 KB. If
`Σ sample bytes` exceeds card RAM, the honest options in order:

1. **Reject with a clear message.** The default. "Needs 214 KB, card has 128 KB."
2. **Truncate the longest samples.** Musically destructive; do not do it silently.
3. **Populate the other three SRAMs.** The real fix, +3 ICs, and the reason the
   footprints are on the board.

There is no fourth option: sample data cannot live in system RAM, because the card
has no bus-master path to it ([`audio.md`](audio.md) §5), and it cannot live in
VRAM ([`graphics.md`](graphics.md) §17).

---

## 5. The replayer

### 5.1 State

**Song state** (~16 bytes):

```
  position      0..songlength-1     ; index into order[]
  pattern       order[position]
  row           0..63
  tick          0..speed-1
  speed         ticks per row, default 6         ; Fxx, xx < $20
  bpm           default 125                      ; Fxx, xx >= $20
  pattern_delay EEx counter
  break_pending / jump_pending + their targets   ; §5.8
```

**Channel state**, ×4 (~28 bytes each). The size is worth noting: ProTracker's
per-channel structure is the replayer, and most "my mod player sounds wrong" bugs
are a missing field here.

```
  sample_num        current instrument
  period            what gets written to PER this tick
  note_period       the period the note was triggered at, before vibrato/arpeggio
  target_period     tone portamento destination (3xx)
  volume            0..64, what gets written to VOL
  finetune          table row 0..15
  porta_speed       3xx memory
  vib_pos, vib_cmd  4xy: position in the sine table, speed/depth
  trem_pos, trem_cmd 7xy
  wave_ctrl         E4x/E7x waveform selects, packed
  offset_mem        9xx memory
  loop_row, loop_cnt E6x pattern loop
  funk_pos, funk_off EFx invert-loop (§10.8)
  loopstart, replen the values to write on the tick-1 shadow write (§5.3)
  dma_pending       bit set at tick 0, consumed at the DMACON write
```

### 5.2 The tick engine

One `/FIRQ` per tick. Two paths, and they are genuinely different amounts of work:

```
  firq_entry:
      clear AINTREQ bit 4               ; ack the timer
      tick = tick + 1
      if tick >= speed:
          tick = 0
          if pattern_delay > 0: pattern_delay -= 1 ; goto effects_only
          read row -> 4 cells           ; §2.4
          for ch in 0..3: new_row(ch)   ; §5.3
          commit DMA starts             ; one DMACON write for all four channels
          write loop shadows            ; §5.3 -- the critical one
          advance_position()            ; §5.8
      else:
          for ch in 0..3: per_tick_effect(ch)   ; §5.5
      for ch in 0..3: write PER, VOL if changed
      rti
```

Three disciplines that matter:

1. **One `DMACON` write, not four.** The register is a bitmask
   ([`audio.md`](audio.md) §9.2), so all four channels start on the same store —
   which is both faster and, more importantly, means four simultaneous notes start
   on the *same colour clock*. Starting them one store apart smears the attack by
   ~7 µs per channel, which is audible on drum hits.
2. **Write `PER`/`VOL` only when they changed.** Most ticks change one or two
   channels. A dirty flag per channel saves ~60 cycles a tick for free.
3. **Never block.** No disk, no OS call, no loops of unbounded length. §5.8's
   position advance is the only place with a loop, and it is bounded at 128.

### 5.3 The note trigger — the one thing that must be exactly right

This is [`audio.md`](audio.md) §1 requirement 3 and §3.3, and it is where a mod
player either works or plays every looped instrument as an endless attack.

```
  ; --- tick 0, channel has a new note ---
  AIDX <- ch*16 + 0
  ADATA <- sample_addr[n]  (3 bytes)     ; LC  = one-shot start
  ADATA <- sample_len[n]   (2 bytes)     ; LEN = full length, in words
  ADATA <- period          (2 bytes)     ; PER
  ADATA <- volume          (1 byte)      ; VOL
  ...for each triggering channel...

  ADMACON <- $00 | mask                  ; STOP the channels being retriggered
  ADMACON <- $80 | mask                  ; START them: card latches PTR<-LC, CNT<-LEN

  ; --- immediately after, same tick ---
  AIDX <- ch*16 + 0
  ADATA <- sample_rep[n]    (3 bytes)    ; LC  = LOOP point
  ADATA <- sample_replen[n] (2 bytes)    ; LEN = loop length
```

The second write does **not** disturb the note that is playing. It only changes
what the card will reload *when the one-shot runs out* — which is precisely the
shadow behaviour [`audio.md`](audio.md) §3.3 builds. The channel plays its attack
once and then loops the sustain, forever, with no further CPU involvement.

**Three ways to get this wrong**, all of which have shipped in real players:

- **Writing the loop pointer instead of the start pointer at trigger time.** Every
  instrument loses its attack.
- **Writing it on the *next* tick instead of immediately.** Works, and is what
  ProTracker does, but it fails for samples shorter than one tick — and short
  one-shot drum samples are common.
- **Inserting ProTracker's delay loop between the `DMACON` write and the shadow
  write.** Unnecessary here, and it costs ~100 wasted cycles a row. On a 68000 the
  delay existed because Agnus needed time to fetch; on this card the enable-driven
  latch is bounded at 4 colour clocks — **1.13 µs, shorter than the 2.4 µs between
  two 6309 stores** ([`audio.md`](audio.md) §16 item 13). Drop the loop, but note
  that it depends on that bound being specified rather than observed.

**The stop-then-start pair matters too.** Clearing `DMACON` before setting it is
what makes a retrigger restart from the beginning; without it, retriggering a
still-playing channel does nothing until its current buffer ends.

### 5.4 The period table

ProTracker's table is **16 finetune rows × 36 periods** (C-1…B-3), 2 bytes each —
**1,152 bytes**. Row 0 (finetune 0) is the canonical Amiga tuning:

```
  856 808 762 720 678 640 604 570 538 508 480 453     ; octave 1
  428 404 381 360 339 320 302 285 269 254 240 226     ; octave 2
  214 202 190 180 170 160 151 143 135 127 120 113     ; octave 3
```

The other 15 rows are the same notes at ±1…±8/8 semitone. **Copy the table from a
known-good source; do not compute it** — and the cost of ignoring that is larger
than it looks. Measured against the real table:

| | Computing it from row 0 |
|---|---|
| Entries that come out wrong | **229 of 576 — 40 %** |
| Worst error | **16 cents**, at finetune +7 B-3 (108 vs 107) |
| Wrong targets absent from their own row | **all 229** |

The last row is the serious one. A tone portamento (§5.5, `3xx`) slides toward a
target period and stops when it arrives; if the target is not an entry in that
finetune's row, **it never arrives** and the note slides until the next one
triggers. The same fact shows up a third way: **86 of the 384 octave relations in
the real table are not `floor(x/2)`**, because ProTracker rounded each octave
independently.

**The table is now in [`tools/refplayer/period_table.c`](../tools/refplayer/period_table.c)**,
taken from `pt2-clone`'s `periodTable` (a faithful C reimplementation of
ProTracker 2.3D), with the finetune-0 row confirmed byte-for-byte against
`libopenmpt` and `libmodplug`. That file's header records the provenance and the
four structural invariants the table was validated against; `test_refplayer.c`
re-checks all four so an edit cannot silently corrupt it.

The table is used for exactly three things:

| Use | Why the table and not the raw period |
|---|---|
| **Finetune** | the file gives period-at-finetune-0; the actual period is the same note in another row |
| **Arpeggio** (`0xy`) | needs "this note +x semitones" — a table index step, not arithmetic |
| **Tone portamento** (`3xx`) | needs the exact target period, which must be a table entry |

Everything else — the note in the pattern, `1xx`, `2xx`, `4xy` — works on the raw
period value and never touches the table.

### 5.5 Effect commands

Every one of these ends in a write to `PER` or `VOL` and nothing else. `t` = tick
number within the row.

| Cmd | Name | Behaviour | Writes |
|---|---|---|---|
| `0xy` | Arpeggio | `t mod 3` selects note, note+x, note+y semitones via the table | `PER` |
| `1xx` | Portamento up | `t>0`: `period -= xx`, clamp ≥ 113 | `PER` |
| `2xx` | Portamento down | `t>0`: `period += xx`, clamp ≤ 856 | `PER` |
| `3xx` | Tone portamento | `t>0`: slide `period` toward `target_period` by `xx`; `xx=0` reuses memory | `PER` |
| `4xy` | Vibrato | `t>0`: `PER = period + sine[vib_pos]×y/128`; `vib_pos += x×4` | `PER` |
| `5xy` | `3xx` + volume slide | tone porta with `Axy` semantics, no new porta speed | both |
| `6xy` | `4xy` + volume slide | vibrato continues, `Axy` semantics | both |
| `7xy` | Tremolo | as `4xy` but modulates `volume`, depth ×/64 | `VOL` |
| `8xx` | *(panning in later trackers)* | **ignore** — see §10.6 | — |
| `9xx` | Sample offset | `t=0`: start at `xx × 256` bytes in; `xx=0` reuses memory | `LC` at trigger |
| `Axy` | Volume slide | `t>0`: `x` up or `y` down, clamp 0…64 | `VOL` |
| `Bxx` | Position jump | `t=0`: queue jump to position `xx` (§5.8) | — |
| `Cxx` | Set volume | `t=0`: `volume = min(xx, 64)` | `VOL` |
| `Dxx` | Pattern break | `t=0`: queue break to row `(xx>>4)×10 + (xx&15)` — **decimal** (§10.4) | — |
| `Exy` | Extended | §5.6 | varies |
| `Fxx` | Set speed / tempo | `t=0`: `xx<$20` → `speed=xx`; `xx≥$20` → `bpm=xx` (§5.7) | `TIMER` |

The vibrato sine table is **32 entries** (a quarter wave, mirrored), and `vib_pos`
is 6 bits with the top bit selecting sign. 32 bytes.

### 5.6 The `E` commands — including the one that talks to the filter

| Cmd | Name | Note |
|---|---|---|
| `E0x` | **Set filter** | `x=0` → LED filter **on**; `x=1` → **off**. Writes `ACTRL.0` |
| `E1x` | Fine portamento up | `t=0` only, once |
| `E2x` | Fine portamento down | `t=0` only, once |
| `E3x` | Glissando control | quantise `3xx` to semitones. Rare; implement or document as ignored |
| `E4x` | Vibrato waveform | 0 sine, 1 ramp down, 2 square, 3 random; `+4` = no retrigger on new note |
| `E5x` | Set finetune | overrides the sample's finetune for this note |
| `E6x` | Pattern loop | `x=0` sets the loop start row; `x>0` loops back `x` times (§5.8) |
| `E7x` | Tremolo waveform | as `E4x`, for `7xy` |
| `E8x` | *(unused)* | ignore |
| `E9x` | Retrigger note | retrigger every `x` ticks within the row |
| `EAx` | Fine volume up | `t=0` only, once |
| `EBx` | Fine volume down | `t=0` only, once |
| `ECx` | Note cut | at `t == x`, `volume = 0` |
| `EDx` | Note delay | trigger the note at `t == x`, not `t == 0` |
| `EEx` | Pattern delay | repeat the current row `x` more times, **effects keep running** |
| `EFx` | Invert loop | "funk repeat". Rare and destructive — §10.8 |

> **`E0x` is the reason [`audio.md`](audio.md) §7 builds both Amiga filters.** The
> module format has a command for the LED filter, composers used it, and the card
> has the filter. It is a one-byte write to `ACTRL` and it is the only effect in
> the entire command set that reaches hardware other than a channel register.
>
> **Do not honour `E0x` when the user has selected filter bypass.** Bypass is for
> native software using the extended period range ([`audio.md`](audio.md) §4.3);
> a module toggling the filter underneath that setting is fighting the user.

### 5.7 Tempo

```
  Fxx, xx < $20 :  speed = xx        ; ticks per row. Does not touch TIMER.
  Fxx, xx >= $20:  bpm   = xx        ; TIMER <- 1773447 / bpm
```

The divide is a 32-by-8 that happens at most once per row — a few hundred cycles
on the rare tick that needs it, or a 224-entry table (BPM 32…255) at 448 bytes if
you would rather not have a divide in the `FIRQ` path. **Table it**; the divide is
the only non-trivial arithmetic in the replayer and removing it makes the worst-case
tick cost flat.

At BPM 125 the reload is 14,187 and the tick rate is 50.002 Hz
([`audio.md`](audio.md) §8.2), which is the PAL vblank rate to within 0.004 % —
so modules written for vblank timing and modules written for CIA timing both play
at the right speed with no special case.

`Fxx` with `xx = 0` is "stop the song" in some trackers and "ignore" in others.
**Ignore it** — treating it as a stop breaks more modules than it fixes.

### 5.8 Position advance — the classic bug nest

The order of operations at the end of a row tick is where players diverge, and
where mods that "work everywhere else" break. The correct sequence:

```
  1. if pattern_delay was set this row (EEx): decrement, do NOT advance, return
  2. if E6x loop is active and the counter is non-zero:
         row = loop_row ; decrement ; return       <- loop wins over normal advance
  3. row = row + 1
  4. if break_pending (Dxx):  row = break_row ; position = position + 1
  5. if jump_pending  (Bxx):  position = jump_pos ; row = break_row if break_pending else 0
  6. if row > 63:             row = 0 ; position = position + 1
  7. if position >= songlength: position = 0        <- and see §10.9
  8. pattern = order[position]
```

Three specific traps:

- **`Bxx` and `Dxx` on the same row** means "jump to position `Bxx`, row `Dxx`" —
  not "jump to position `Bxx` row 0, then break". Step 5 has to see step 4's row.
- **`Dxx` advances the position**, it does not just change the row. A `D00` is
  "next pattern, row 0", which is how most modules end a pattern early.
- **`E6x` pattern loop is per-channel in the file but per-song in effect.** Four
  channels can each carry a loop command; ProTracker's behaviour is that the last
  one processed wins. Match it rather than trying to improve on it.

---

## 6. `FIRQ` discipline

The card is the **sole** `/FIRQ` source in the machine
([`audio.md`](audio.md) §8.1, [`graphics.md`](graphics.md) §17), which buys three
things worth spending deliberately:

1. **No polling chain.** The handler does not have to ask "was it me?" — it was.
   That is ~20 cycles and a whole class of latency.
2. **`FIRQ` stacks only `PC` and `CC`.** The handler saves exactly the registers it
   uses. A replayer tick that keeps its working set in `U`-relative direct page can
   get away with pushing `D`, `X` and `Y` — ~12 cycles of entry overhead against
   `IRQ`'s ~21.
3. **It is independent of video.** The video card's VBL is 70.09 Hz
   ([`graphics.md`](graphics.md) §6.2) and a mod tick is 50–102 Hz. Deriving one
   from the other is not possible cleanly, and now nobody has to try.

**Under NitrOS-9:** own `/FIRQ` outright rather than going through the kernel's
interrupt polling, which is `IRQ`-oriented. The handler touches nothing the kernel
owns — the card's registers, the pattern buffer, and its own state — so it needs
no synchronisation beyond making the loader mask the timer while it rebuilds the
song image. Document it as a hard owner; it is the correct design *and* it is only
correct as long as nothing else is put on `/FIRQ` later.

---

## 7. Cycle budget

Against a **2.098 MHz 6309 in native mode**, at the same assumed ~5 core cycles
per store that [`graphics.md`](graphics.md) §7.3 and [`audio.md`](audio.md) §13.1
use — and with the same warning, that **every figure here scales on that
assumption** (§11 item 1).

**Plain tick** (no new row), per channel:

| Work | Cycles |
|---|---|
| effect dispatch through a jump table | ~15 |
| effect body (vibrato is the worst at ~60; volume slide ~30) | ~30–60 |
| write `PER` (`AIDX` + 2 × `ADATA`) | ~24 |
| write `VOL`, if dirty | ~12 |
| **per channel** | **~100–130** |
| × 4 channels | ~440 |
| `FIRQ` entry/exit, timer ack, tick counter | ~180 |
| **plain tick total** | **~900** |

**Row tick**, additionally:

| Work | Cycles |
|---|---|
| read and unpack 4 cells (§2.4) | ~160 |
| period-table lookup + note setup, per triggering channel | ~110 × 4 |
| one `DMACON` stop/start pair | ~16 |
| loop-shadow writes, per triggering channel (§5.3) | ~40 × 4 |
| tick-0 effects (`Cxx`, `9xx`, `Fxx`, `E`-commands) | ~160 |
| position advance (§5.8) | ~60 |
| **row tick total** | **~2,200** |

At BPM 125, speed 6 — 50 ticks/s of which 8.33 are row ticks:

```
  41.7 plain x  900  = 37,500
   8.3 row   x 2200  = 18,300
                       ------
                       55,800 cycles/s  =  2.7 % of 2,098,000
```

**The worst case is what matters, and it is comfortable.** A row tick where all
four channels trigger with tone portamento is ~2,200 cycles against a tick budget
of **41,960 cycles** at 50 Hz — a **19× margin**. At the fastest tempo a module
can request, BPM 255, the budget is 20,568 cycles and the margin is still **9×**.
There is no tempo, speed or pattern that can make this replayer lose a tick.

For context: on the CoCo 3 hardware this machine replaces, sampled-music playback
consumes essentially the entire processor. Here it is a rounding error against an
80×25 text scroll ([`graphics.md`](graphics.md) §7.3, ~2.5 ms).

---

## 8. Build order

Aligned with [`audio.md`](audio.md) §15, which gates the discrete card on this
software existing first.

| # | Step | Exit criterion |
|---|---|---|
| 0 | ~~**Write a host-side reference player** in C against the §9 register model~~ — **done, [`tools/refplayer/`](../tools/refplayer/)**, A/B'd in [`tools/modcompare/`](../tools/modcompare/) | **closed.** 15/15 single-effect probes and `ode2ptk.mod` agree with libopenmpt's Paula emulation: +0.0 cents tuning, ≤0.3 dB gain, spectral correlation at or above the calibration ceiling — and the whole 1112-row path through `ode2ptk.mod` is identical |
| 1 | **Loader on the MCU card** ([`audio.md`](audio.md) §12.5) | a module's samples land in card RAM byte-for-byte identical to the reference |
| 2 | **Replayer, tick engine and note trigger only** — no effects | a module plays recognisably; §5.3's shadow write verified on a looped instrument |
| 3 | **Effects, in order of corpus frequency**: `Cxx`, `Fxx`, `Axy`, `Dxx`, `1xx`/`2xx`, `3xx`, `4xy`, `0xy`, then the `E` set | each effect A/B'd against the reference on a targeted test module |
| 4 | **Position advance and the `Bxx`/`Dxx`/`E6x`/`EEx` interactions** (§5.8) | the pathological test modules of §9 traverse identically to the reference |
| 5 | **Port to the discrete card** — no software change expected | the same corpus plays identically on both cards |
| 6 | **NitrOS-9 integration**: `/FIRQ` ownership, loader as a subroutine module | music plays under a running console with no tick loss |

**Step 0 is not optional.** Without a reference implementation there is nothing to
A/B against, and "it sounds about right" is not an acceptance test for a system
whose entire premise is bit-exact compatibility.

**It paid for itself twice.** Building the model found four things these
documents had wrong: the volume LUT was one address bit short of
Paula's 0–64 range ([`audio.md`](audio.md) §6.1); the tempo clock was out by
2.5× ([`audio.md`](audio.md) §8.2); a reference that runs the replayer in zero
card time *hides* the §5.3 race instead of testing it, so the model charges each
register store its real cost; and the LED filter model had a passband bump, which
a filter cannot have. Three of those would otherwise have reached a GAL.

And A/B'ing it against libopenmpt found a fifth, in the replayer itself:
**`mod_start()` armed the tempo timer and then waited for it**, so row 0 played
one whole tick — 20 ms — late. Audibly that is a beat of silence before the
music; for measurement it is worse, because a constant offset skews every RMS
comparison. Real driver code has the same obligation: play row 0, then let the
timer drive ticks 1..n.

**Climb the ladder in order.** That A/B was first attempted directly against
`ode2ptk.mod`, which is *built* to break players — it walks backwards through its
own pattern and rewrites the tempo on almost every row. Every disagreement it
produced was ambiguous. The 20 ms bug only became visible on a synthetic probe
playing one note with one effect, where nothing else could be responsible.
Single-effect probes first, ordinary modules second, antagonistic modules last;
[`tools/modcompare/`](../tools/modcompare/) is built around that order.

**The register trace is the contract, not the audio.** `refplayer --trace` emits
the register-write stream timestamped by tick, and a correct 6309 replayer
produces a byte-identical one. When it does not, the diff names the register, the
tick and the channel; comparing waveforms only tells you that something is wrong.
`--rowtrace` is the same idea one level up, and comparing it against another
player's order/pattern/row is the sharpest single check available — it is what
confirmed §5.8's ordering over 1112 rows.

---

## 9. Test corpus

The acceptance test is not "a module plays". It is a set of modules chosen so that
each one fails loudly if a specific thing is wrong.

| What it tests | Choose a module that… |
|---|---|
| **The shadow write (§5.3)** | uses long looped sustains — any melodic lead. Fails as an endless attack |
| **Non-looping samples (§4.2)** | is drum-heavy. Fails as a stuck buzz after the first hit |
| **Period accuracy ([`audio.md`](audio.md) §4.1)** | plays sustained chords across channels. Fails as beating/detune |
| **Finetune (§3)** | uses non-zero finetune on a lead instrument. Fails as a semitone-ish error |
| **Tone portamento + the table (§5.4)** | uses `3xx` heavily. Fails as slides that never arrive |
| **Tempo (§5.7)** | changes `Fxx` BPM mid-song. Fails as a speed step |
| **Position logic (§5.8)** | uses `Bxx`, `Dxx` on the same row, and `E6x` loops |
| **`9xx` sample offset** | uses offset for vocal or breakbeat slicing |
| **The filter (§5.6)** | uses `E0x`. Fails as no audible timbre change |
| **Loader robustness (§4.6)** | is truncated, and one that is a 15-sample Soundtracker file |
| **Card RAM limits (§4.7)** | exceeds 128 KB of samples. Must reject cleanly, not corrupt |

**A dozen modules chosen this way is worth more than a thousand chosen at random**,
and the list doubles as the regression suite for the discrete card in build step 5.

---

## 10. ProTracker behaviours that are load-bearing

These are not bugs to be improved on. Modules were written against them by ear,
and "fixing" any of them makes real songs sound wrong.

1. **Sample number without a note** sets the volume and selects the instrument for
   the *next* note — it does **not** retrigger. Retriggering here is the single
   most audible wrong behaviour in a naive player.
2. **Note without a sample number** retriggers using the channel's current
   instrument at the channel's current volume, not the sample's default volume.
3. **Period clamping to 113…856** ("Amiga limits") applies to `1xx`/`2xx`/`3xx`
   results, not to the raw period in the pattern. The card would happily play
   outside that range ([`audio.md`](audio.md) §4.3) — **clamp anyway** in mod mode.
4. **`Dxx` is decimal**: `D10` breaks to row **10**, not row 16. A surprising
   number of modules end patterns with `D00` and a few use `D32`.
5. **Arpeggio runs on `t mod 3`**, and it does *not* reset at the row boundary in
   the way some players assume. It also uses the table, so it is affected by
   finetune.
6. **`8xx` is not panning here.** Some trackers wrote panning into `8xx`; on OCS
   it does nothing, and honouring it would break Paula's hard-panned stereo, which
   is [`audio.md`](audio.md) §1 requirement 5. **Ignore it.**
7. **Volume is clamped 0…64 at every step**, not just at `Cxx`. A volume slide that
   would go negative sticks at 0 and comes back up from 0.
8. **`EFx` (invert loop / funk repeat) modifies sample data in place.** It is rare,
   it is destructive, and on this card the data lives in card RAM where a
   read-modify-write costs two register accesses per byte. **Document it as
   unimplemented** unless a module in the corpus needs it — and if one does,
   implement it against a RAM copy, not the card.
9. **The restart position at offset 951 is unreliable.** Most modules store `$7F`
   or garbage. Loop to position 0 (§5.8 step 7) and ignore the field.
10. **`EDx` note delay interacts with `EEx` pattern delay** — the delayed note
    triggers once per repeat of the row, not once per row. This is obscure, and it
    is also exactly the kind of thing the reference player of §8 step 0 exists to
    settle.

---

## 11. Open items

1. **Confirm the CPU store rate.** §7's whole budget, and
   [`audio.md`](audio.md) §13's, scale on "~5 core cycles per store, native mode".
   Measure it once against real `STA extended` / `AIDX`+`ADATA` sequences and both
   documents get their numbers. Same item as
   [`graphics.md`](graphics.md) §19 item 1.
2. **Settle the `DMACON`-latch bound** ([`audio.md`](audio.md) §16 item 13). §5.3
   drops ProTracker's delay loop on the strength of a ≤4-colour-clock guarantee
   that is currently proposed rather than specified. If it is not specified, the
   delay loop goes back in and §7's row-tick figure grows by ~100 cycles.
3. **Decide `E3x` (glissando) and `EFx` (invert loop).** Both are rare. Implement,
   or document as ignored — but decide, because "silently does nothing" and
   "documented as ignored" are different things to a user comparing against an
   Amiga.
4. ~~**Source the period table from a known-good ProTracker build**~~ — **closed.**
   The real 16 × 36 table is in
   [`period_table.c`](../tools/refplayer/period_table.c) with its provenance and
   four validated invariants (§5.4). Diffing it against a computed one is what
   produced the 40 % / 16-cent / never-terminating figures now in §5.4, and it
   confirmed that the hand-rounding is real and unavoidable rather than an
   artefact of one source.
5. **Choose the tempo strategy**: 448-byte table or a runtime divide (§5.7). The
   table is recommended; confirm the RAM is there.
6. **Decide whether 6-channel and 8-channel modules are in scope.** §2.3 rejects
   them because [`audio.md`](audio.md) §11.2's mode is unbuilt and unfitted. If
   they are wanted, that fit (§11.2, and [`audio.md`](audio.md) §16 item 7) has to
   happen before the sequencer GAL is committed, not after.
7. **Pattern buffer placement under NitrOS-9.** A 64-pattern module is 64 KB of
   patterns, which does not fit alongside the replayer in one 64 KB logical space.
   Either the pattern buffer gets its own MMU block and the replayer maps it per
   tick (cheap, but it is MMU state in a `FIRQ` handler), or patterns are read from
   disk per position (unacceptable latency). **Resolve before build step 6** — this
   is the only place the replayer and the memory manager interact, and it is not
   yet designed.
8. **Streaming loader vs. disk stack.** §4.1 assumes the disk layer can deliver
   sectors into a small buffer on demand. Confirm against whatever NitrOS-9 device
   driver the machine ends up with; if it cannot, the loader falls back to
   buffering and §4.1's memory argument needs revisiting.

---

## 12. Sources and cross-references

- [`audio.md`](audio.md) — §1 (the nine fidelity requirements this document
  implements), §3.3 (the shadow reload behind §5.3), §4.1 (the period reference
  that makes §4.3 a copy), §7 (the filter `E0x` reaches), §8 (the `/FIRQ` and
  tempo model), §9 (the register map every code fragment here writes to),
  §13 (`TFM` upload), §16 item 13 (the latch bound §5.3 depends on).
- [`graphics.md`](graphics.md) — §7.3 (the store-rate assumption §7 shares),
  §17 (`/FIRQ` ownership, and why sample data is not in VRAM).
- [`plan.md`](plan.md) — §4.3 (`TFM`, including the fixed-destination mode §4.4
  relies on).
- **The `.mod` format and ProTracker's replayer behaviour.** §2, §5.5, §5.6, §5.8
  and §10 are written from the documented format and the well-known replayer
  semantics. **Every behavioural claim in them must be verified against a
  known-good reference implementation in build step 0** (§8) — particularly §5.8's
  ordering and §10's ten items, which are exactly the places where published
  descriptions of ProTracker disagree with each other and where only the reference
  settles it.
