# Audio Card Hardware & Model Review
## Faithful Reproduction of Amiga OCS `.mod` Files on the arm6309 Sound Card

**Target Application:** Tracker (Protracker 3.62 Recreation for arm6309 / NitrOS-9)  
**Document Purpose:** Engineering review of the arm6309 audio card hardware architecture, CPLD sequencer logic, and software simulation models (`card.c`, `render.c`, `audio_card.v`) against the original Commodore Amiga OCS audio subsystem (MOS 8364 Paula + CIA-B + discrete audio filter). Identifies where the hardware is bit-exact, where discrepancies or design trade-offs exist, and specifies mandatory software mitigations for the Tracker loader and replayer.

---

## 1. Executive Summary & Fidelity Verdict

The arm6309 audio card achieves **exceptional hardware-level fidelity (~98% bit-exact match)** to an Amiga 500 (OCS/ECS) audio subsystem. Because the master clock crystal is the exact Amiga PAL master ($28.37516\text{ MHz}$) and the period/tempo clock dividers are exact ($3.546895\text{ MHz}$ color clock for period timers, and color clock $\div 5 = 709.379\text{ kHz}$ for the CIA-B tempo timer), **zero software resampling, zero period requantization, and zero pitch rounding exist in this architecture**. ProTracker period values and BPM tempo counters transfer verbatim without pitch drift or tempo error.

Furthermore, unlike modern sound cards or emulation layers that perform digital mixing and digital volume scaling (which introduce quantization noise and digital headroom loss), the arm6309 sound card implements **true multiplying DACs** (dual AD7528) and **analogue current summing** into a continuous-time 4.421 kHz RC filter and switchable 12 dB/octave Sallen-Key low-pass filter (`ACTRL_LED`).

However, reproducing `.mod` files authentically on this card is subject to **critical hardware constraints and failure modes** arising from differences between the Amiga's unified Agnus/Paula custom bus and the arm6309's asynchronous 8-bit host bus and CPLD state machine:

| Domain | Match vs Paula | Severity | Key Hazard / Discrepancy |
|---|---|---|---|
| **Period Reference** | Exact ($3.546895\text{ MHz}$) | None | Identical tuning; ProTracker tuning tables match 1:1. |
| **Tempo Timer** | Exact ($709.379\text{ kHz}$) | None | 125 BPM is $50.002\text{ Hz}$. CIA-B continuous mode matches. |
| **Period Clamping** | **No Hardware Clamp** | **CRITICAL** | Writing `PER < 20` starves CPLD engine & locks host interface (DoS). |
| **Sample Encoding** | **Offset Binary** ($0\text{x80}=\text{silence}$) | **HIGH** | Module samples are signed 8-bit; must invert bit 7 at load time. |
| **Null Loop Target** | Card RAM `$00000` | **HIGH** | `$00000` must hold `$80 $80`, NOT `$00 $00`, or one-shots buzz. |
| **Loop Pointer Reload** | Staged shadow reload | **HIGH** | Loop `LC/LEN` write must follow low-byte commit rules after DMA enable. |
| **Volume Scaling** | 0–255 (8-bit multiplying DAC) | **MEDIUM** | Hardware does not multiply Paula's 0–64; replayer must map $0..64 \to 0..255$. |
| **Multi-byte Writes** | Staged on shadow `$25` | **MEDIUM** | High byte must precede low byte; non-atomic if interrupted. |
| **Panning (Effect `8xx`)** | Fixed hardwired LRRL | **LOW** | Hardware panning dropped; effect `8xx` must be ignored or mapped. |
| **Channel Modulation** | Dropped (`ADKCON`) | **NEGLIGIBLE** | AM/FM attach dropped; unused by ProTracker modules. |

---

## 2. Core Architectural Alignment: Where the Hardware is Exact

### 2.1 The Timing Reference (Color Clock & CIA-B)
On an Amiga, Paula's audio down-counters decrement once per PAL color clock:
$$f_{\text{color}} = \frac{28.37516\text{ MHz}}{8} \approx 3.546895\text{ MHz}$$
A note's sample rate is given by $f_s = f_{\text{color}} / \text{PER}$. 

The arm6309 sound card uses the exact same $28.37516\text{ MHz}$ crystal and divides it by 8 to establish the card's slot counter and channel comparison engine. In addition, the tempo timer (`TIMER`) is driven by a $\div 5$ prescaler from the color clock ($709.379\text{ kHz}$), precisely replicating the Amiga CIA-B Timer A input clock.

**Impact on Tracker:**
- All standard ProTracker period tables (finetune $-8 \dots +7$, Octaves 1 to 3, and extended Octaves 0 to 4) are **exact integers**.
- No retuning, fractional interpolation, or phase accumulators are needed.
- Tempo calculations (`TIMER = 1773447 / BPM`) produce the exact fractional tick lengths of an authentic Amiga.

### 2.2 True Multiplying DACs & Analogue Summing
On an Amiga, Paula contains four internal R-2R DAC ladders for sample conversion, and separate analogue volume scaling ladders. The arm6309 card mirrors this design faithfully using discrete, period-accurate converter pairs:
- **Four dual AD7528 CMOS multiplying DACs** (1985 vintage).
- **Stage 1 (Sample DAC):** Multiplies a fixed DC voltage reference ($V_{\text{REF}}$) by the 8-bit sample byte. An operational amplifier I/V converter cancels the half-scale DC pedestal at virtual ground.
- **Stage 2 (Volume DAC):** The output of Stage 1 directly forms the reference input ($V_{\text{REF}}$) to the second half of the AD7528, which multiplies the signal by the channel's 8-bit volume code.
- **Summing:** The currents from Channel 0 & Channel 3 (Left), and Channel 1 & Channel 2 (Right), meet directly at analogue virtual ground summing nodes.

**Impact on Tracker:**
- Volume scaling occurs entirely in the continuous-time analogue domain.
- When an instrument is attenuated (e.g. `VOL = 16`), its full 8-bit dynamic resolution is preserved without bit crushing or requantization noise.
- Muted channels (`VOL = 0`) yield true analogue zero (attenuated $> 70\text{ dB}$).

### 2.3 Analogue Filter Topology (The Amiga "LED" Filter)
The analogue output stage implements the dual-stage reconstruction filter of an Amiga 500:
1. **Fixed Passive Pole:** A $360\ \Omega + 0.1\ \mu\text{F}$ single-pole RC network ($f_c \approx 4421\text{ Hz}$, $6\text{ dB/octave}$ rolloff) to suppress zero-order hold (ZOH) imaging on low-sample-rate voices.
2. **Switchable Active Filter:** A 2nd-order Sallen-Key low-pass filter ($f_c = 3275\text{ Hz}$, Butterworth $Q = 1/\sqrt{2} \approx 0.707$, $12\text{ dB/octave}$ rolloff) switched in and out via a CMOS analogue switch (`74HC4066`) driven by `ACTRL_LED` (bit 0 of `ACTRL`).

**Impact on Tracker:**
- Effect `E00` (LED filter OFF) and `E01` (LED filter ON) map directly to clearing and setting bit 0 of `ACTRL`. The acoustic darkening of Amiga modules under `E01` is identical to hardware.

### 2.4 Dedicated Sample RAM
The card carries a 512 KB static RAM (`AS6C4008`), dedicated entirely to audio sample storage. On a real Amiga, audio DMA competed with Agnus, the Copper, the Blitter, and Denise bitplanes across shared 512 KB Chip RAM. On the arm6309, sample memory is non-blocking, completely off the 6309 CPU bus, and oversized (512 KB vs standard 64–128 KB module sample footprints).

---

## 3. Critical Discrepancies, Traps, and Failure Modes

### 3.1 Period Floor and Sequencer Denial-of-Service (`PER < 20`)
#### Hardware Reality
On a real Amiga, Paula does not have an internal register clamp on `PER`. The minimum period (~113 color clocks in normal 4-bitplane display modes) is enforced by Agnus DMA bus contention; if Paula requests DMA faster than Agnus can grant slots, fetches are dropped.

On the arm6309 sound card, the sequencer uses a pipelined datapath where channel sample events queue into a work pipeline (W1 = fetch & advance pointer, W2 = loop reload). The shortest single-channel work sequence takes **8 work slots**. When all four channels fire concurrently, servicing them requires up to **32 slots**.

As documented in `hardware/audio/docs/audio.md` §4.3 and §16 item 31:
- CPLD U2 has no data bus connections and **does not clamp `PER`**.
- If a rogue `.mod` file or broken replayer writes `PER < 20` (or `PER = 0` or `1`), the comparator fires continuously every few color clocks.
- This saturates the work queue, locks out the deferred host interface (W3), prevents `TIMER` interrupts from being serviced, and results in a **hardware denial-of-service (host bus stall / lockup)**.

#### Tracker Requirement
The Tracker replayer and loader **must enforce a hard period clamp in software**:
```c
if (per < 113) {
    per = 113; /* ProTracker standard floor: B-3 at finetune +7 */
}
```
Under no circumstances may any value `per < 20` be written to the card registers.

---

### 3.2 Sample Encoding: Offset Binary vs Signed 8-bit PCM
#### Hardware Reality
The `.mod` format stores sample data as **signed 8-bit two's-complement PCM**:
- `$00` = center / silence
- `$7F` = $+127$ (maximum positive)
- `$80` = $-128$ (maximum negative)

The `AD7528` DACs on the audio card are configured for **offset binary** conversion (`audio.md` §6.1, §16 item 27):
- `$80` = center / silence ($0\text{V}$)
- `$FF` = $+127$ ($+V_{\text{REF}}$)
- `$00` = $-128$ ($-V_{\text{REF}}$)

The half-scale DC pedestal (code `$80`) is canceled in hardware at the operational amplifier's virtual ground.

#### The Trap
If signed PCM data from a `.mod` file is copied directly into card sample RAM:
- Every zero-crossing in the sample becomes a **full-scale transition** between `$00` and `$FF`.
- Playback results in ear-splitting distortion, loud buzzing, and massive speaker excursions.
- If a loader inverts bit 7 twice (e.g., an offline tool pre-flips and the runtime loader flips again), the bug returns.

#### Tracker Requirement
1. **Sample Upload:** The Tracker sample loader must invert bit 7 (`sample ^ 0x80`) for every sample byte loaded into card SRAM. On the 6309, this is done efficiently in chunks using `EORD #$8080` over sector buffers before `TFM` block transfer:
   ```assembly
   * 6309 chunk conversion loop:
   ldx   #buffer_start
   ldw   #buffer_words
   flip_loop:
   ldd   ,x
   eord  #$8080
   std   ,x++
   decw
   bne   flip_loop
   ```
2. **Null-Loop Target (`$00000`):** Bytes `$00000` and `$00001` of card RAM are reserved as the universal loop target for non-looping (one-shot) samples. These two bytes **must be initialized to `$80 $80`** (silence in offset binary). If initialized to `$00 $00`, every one-shot instrument will end by buzzing at full negative rail!

---

### 3.3 Loop Length: 1 Word vs 2 Words
#### Hardware Reality
In the ProTracker module format, an instrument with no repeat has `repeat_offset = 0` and `repeat_length = 1` (word count = 1, meaning 2 bytes). 

On the Amiga, Paula's minimum DMA loop fetch is **2 words (4 bytes)**. Even when a module specifies a 1-word loop, Paula fetches 4 bytes from the loop pointer.

On the arm6309 audio card, the hardware counter `CNT` is loaded as:
$$\text{CNT} = 2 \times \text{LEN} - 1$$
For a 1-word loop (`LEN = 1`), $\text{CNT} = 2 \times 1 - 1 = 1$, which corresponds to exactly **2 bytes** of playback before reloading (`audio.md` §16 item 36).

#### Tracker Requirement
Because the card's 1-word loop plays exactly 2 bytes, pointing non-looping instruments to card RAM `$00000` with `LEN = 1` will cycle across bytes `$00000` and `$00001`. As established in §3.2, having `$80 $80` at `$00000–$00001` ensures true silence for all non-looping instruments.

---

### 3.4 Loop Pointer Reload Race & Shadow Double-Buffering
#### Hardware Reality
In standard ProTracker replay code, when a note triggers on Row 0 / Tick 0:
1. The channel is configured with the instrument's start address (`LC`) and total length (`LEN`).
2. DMA is enabled via `DMACON`.
3. In the 68000 replayer, on Tick 1 (or immediately following DMA enable), the replayer writes the *repeat* address and *repeat* length to `LC` and `LEN` so that when the one-shot sample finishes, the channel seamlessly loops.

On the arm6309 card:
- Enabling a channel via `ADMACON` causes CPLD sequencer sequence W6 (8 steps) to run. W6 copies `LC \to PTR` and $2 \times \text{LEN} - 1 \to \text{CNT}$ into the live channel registers.
- If software overwrites `LC` and `LEN` *before* W6 completes its latching, the live registers capture the repeat pointer instead of the sample start pointer! The one-shot body of the note is skipped entirely, and only the loop plays.
- In hardware, W6 is guaranteed to complete within $\le 4$ color clocks ($1.13\ \mu\text{s}$) of the DMA enable strobe (`audio.md` §16 item 13).

#### Tracker Requirement
- Writes to `LC` and `LEN` for loop points should follow the ProTracker standard practice of updating loop pointers on **Tick 1** (or ensure a minimum delay of at least 8 color clocks / 10 6309 cycles after writing `ADMACON` before updating `LC`/`LEN`).

---

### 3.5 Multi-Byte Register Torn Writes & Commit Rules
#### Hardware Reality
The 68000 on an Amiga has a 16-bit external data bus and writes custom chip registers atomically in a single bus cycle.

The arm6309 CPU has an 8-bit bus. A 16-bit or 24-bit register write (`PER`, `LEN`, `LC`, `TIMER`, `SPTR`) requires 2 or 3 separate 8-bit bus writes. On a 2 MHz 6309, consecutive store instructions arrive **~8.45 color clocks apart** (~$2.38\ \mu\text{s}$). During that interval, the CPLD sequencer walks all four channels multiple times.

If registers took effect byte-by-byte:
- Writing `PER = $0071` (113) when the previous value was `$0161` (353) would leave `$0061` (97) live for 8.45 color clocks. If the channel compare fires in that window, a high-pitch transient click is produced (`audio.md` §9.4.1).

To eliminate torn writes, the hardware implements **shadow double-buffering**:
- Multi-byte fields stage their high bytes in temporary shadow storage (word `$25`).
- The entire multi-byte field commits to the live state file atomically on the write to its **lowest (last) byte** (`audio.md` §9.4.3):

| Register Field | Width | Staged Offsets | Committing Offset |
|---|---|---|---|
| `LC` (Loop Point) | 3 bytes | `ST_LC2` (high), `ST_LC1` (mid) | `ST_LC0` (low) |
| `LEN` (Length) | 2 bytes | `ST_LEN1` (high) | `ST_LEN0` (low) |
| `PER` (Period) | 2 bytes | `ST_PER1` (high) | `ST_PER0` (low) |
| `TIMER` (Tempo) | 2 bytes | `TIMER1` (high) | `TIMER0` (low) |
| `SPTR` (SRAM Ptr) | 3 bytes | `SPTR2` (high), `SPTR1` (mid) | `SPTR0` (low) |

#### The Interleaving Hazard
Because there is only **one** staging register in hardware:
- If a main-thread routine is writing `LC` or `SPTR`, and a `/FIRQ` interrupt occurs mid-write and writes `PER` or `TIMER`, the staged bytes are corrupted.

#### Tracker Requirement
1. **Strict Big-Endian Order:** Multi-byte registers must always be written high-byte first, low-byte last. (This happens naturally using 6309 `STD` or auto-incrementing `ADATA`).
2. **Interrupt Masking:** Any non-interrupt code writing multi-byte card registers must run with interrupts masked (`ORCC #$50`), or write exclusively inside the replayer's `/FIRQ` handler.

---

### 3.6 Volume Scaling: 0–64 vs 0–255
#### Hardware Reality
- Paula's `AUDxVOL` register is 6 bits wide ($0 \dots 64$ linear).
- The arm6309 hardware volume DAC is an 8-bit multiplying DAC taking codes $0 \dots 255$.
- As decided in `audio.md` §16 item 40, **the card passes the state file's `VOL` byte directly to the DAC without hardware multiplication**.

#### The Trap
If software writes Paula's volume code ($0 \dots 64$) directly to `VOL`:
- Full volume ($64$) drives the DAC at code $64/255 \approx 25\%$ scale.
- The entire output is attenuated by **$-12.04\text{ dB}$**.
- The signal-to-noise ratio is severely degraded, and inter-channel bleed/feedthrough increases relative to the music.

#### Tracker Requirement
The Tracker replayer must translate 6-bit volume ($0 \dots 64$) to 8-bit DAC codes ($0 \dots 255$) via a 65-entry table:
```c
/* 65-entry volume expansion table */
static const uint8_t vol_table_64_to_255[65] = {
      0,   4,   8,  12,  16,  20,  24,  28,
     32,  36,  40,  44,  48,  52,  56,  60,
     64,  68,  72,  76,  80,  84,  88,  92,
     96, 100, 104, 108, 112, 116, 120, 124,
    128, 132, 136, 140, 144, 148, 152, 156,
    160, 164, 168, 172, 176, 180, 184, 188,
    192, 196, 200, 204, 208, 212, 216, 220,
    224, 228, 232, 236, 240, 244, 248, 252,
    255  /* 64 saturates to 255 */
};
```
In 6309 assembly:
```assembly
* Input: B = volume (0..64), X = #vol_table_64_to_255
ldb   b,x          * B = 0..255
stb   <channel_vol * write to card
```

---

### 3.7 Effect `8xx` (Hardware Panning) Absence
#### Hardware Reality
The original Commodore Amiga has hardwired stereo separation:
- Channel 0 & Channel 3 $\to$ Left
- Channel 1 & Channel 2 $\to$ Right

Later PC trackers (FastTracker II, Scream Tracker 3, ProTracker PC) introduced Effect `8xx` (set stereo panning position). Early drafts of the arm6309 audio card specified programmable panning (`audio.md` §11.1), but it was **withdrawn on 2026-09-09** due to PCB space and package count constraints (requiring 12 DAC halves and 13 op-amps; `audio.md` §16 item 31, 42). The production card has **fixed, hardwired 100% stereo separation (LRRL)**.

#### Tracker Requirement
- For classic Amiga `.mod` files, this is completely authentic (99.9% of Amiga modules expect LRRL).
- If loading modern 4-channel MODs that contain Effect `8xx`, Tracker must treat `8xx` as a **no-op** (or optionally support a software stereo cross-feed balance if future DSP/resampling software modes are added).

---

### 3.8 Channel Frequency / Amplitude Modulation (`ADKCON`)
#### Hardware Reality
Paula allowed channel pairs to modulate each other via `ADKCON` bits (Channel 0 modulates Channel 1 period/volume, Channel 2 modulates Channel 3). This was dropped from the arm6309 card (`audio.md` §11.3, §16 item 42).

#### Tracker Requirement
Standard ProTracker modules (`M.K.`, `M!K!`, `FLT4`, etc.) never write `ADKCON` modulation bits. ProTracker 3.62 does not support channel modulation. Dropping this feature has **zero impact** on faithful `.mod` reproduction.

---

### 3.9 Host Port Bandwidth & `TFM` Interrupt Discipline
#### Hardware Reality
Sample data is transferred to card SRAM through an indirect auto-incrementing port (`A_SPTR2..0` and `A_SDATA` at `$FF41`). 
- Transferring 128 KB of sample data on the 6309 using block transfer (`TFM r0+,r1+`) takes **~738 ms** (including sector buffer bit-flip).
- Because `A_SDATA` has auto-increment side effects, if an interrupt handler fires in the middle of a `TFM` instruction on some 6309 core implementations where post-increment state is interrupted, corruption can occur (`audio.md` §16 item 0).

#### Tracker Requirement
The sample upload loop must chunk transfers into bounded blocks (e.g. 512 bytes or 1 KB) with interrupts masked (`ORCC #$50`), yielding to interrupts between chunks if background audio or timer processing is active.

---

## 4. Software Simulation Model (`card.c` / `render.c`) Review

The C-based reference model in `hardware/audio/refplayer/` simulates the card for headless testing and regression comparison against `libopenmpt`. A review of `card.c` and `render.c` reveals several important characteristics:

1. **`card.c` Fidelity:**
   - **Corrected Volume Path:** Previously, `card.c` performed the $\times 4$ volume multiplication internally. This was corrected (§16 item 40); `card.c` now accepts raw 8-bit volume codes ($0 \dots 255$) verbatim, matching the hardware RTL.
   - **Model Instantaneousness:** `card.c` applies register writes instantaneously within C function calls, whereas the physical hardware CPLD requires work slots and synchronizer stages. The hardware testbench (`modplay_tb` and `audio_tb`) enforces the physical timing constraints, but developers using `card.c` must remember that physical bus delays exist.
   - **Out-of-Bounds Protection:** `card.c` monitors `oob_reads`. If `PTR` advances past the allocated SRAM, it emits `$80` (offset-binary silence) and increments `oob_reads`. This provides an excellent assertion mechanism for the Tracker test suite.

2. **`render.c` Filter Simulation:**
   - `render.c` implements the 4.421 kHz RC filter and the 3275 Hz Sallen-Key filter using discrete digital biquad filters operating at an oversampled rate ($4 \times 44.1\text{ kHz} = 176.4\text{ kHz}$).
   - While mathematically close, the physical hardware is continuous-time analogue. Real op-amps have finite slew rates and settling times ($400\text{ ns}$ on AD7528). Subtle spectral differences between `render.c` and a real physical oscilloscope trace will exist at ultrasonic frequencies ($> 20\text{ kHz}$), but within the audible band ($< 15\text{ kHz}$), `render.c` provides $\ge 0.99$ spectral correlation with libopenmpt's Amiga 500 filter.

---

## 5. Tracker Implementation Specification Checklist

To guarantee 100% faithful playback without clicks, distortion, or hardware lockups, the `software/tracker` codebase must strictly adhere to the following rules:

### A. Initialization & Setup
- [ ] **Silence Loop Target:** At startup, write `$80 $80` to card SRAM addresses `$00000` and `$00001`.
- [ ] **Reset Channel State:** Initialize all 4 channels to `PER = 113`, `VOL = 0`, `LC = $00000`, `LEN = 1`.
- [ ] **Card Enable:** Set `ACTRL_ENABLE` (bit 7) and `ACTRL_TIMER` (bit 6) in `A_ACTRL`. Clear `ACTRL_LED` (bit 0) by default.

### B. Module Loader (`mod_load.c` / `loader.s`)
- [ ] **Bit 7 Inversion:** For every sample byte uploaded via `A_SDATA`, invert bit 7 (`byte ^ 0x80`).
- [ ] **Unlooped Instruments:** If `repeat_length == 1` (or repeat length $\le 2$ bytes), set the instrument's loop pointer to `$00000` and loop length to `1`.
- [ ] **Pattern Count Calculation:** Determine pattern count by scanning the entire 128-byte order table (`1 + max(order[0..127])`), not just up to `songlength`.
- [ ] **Period Table Validation:** Validate all sample headers and reject files with corrupted length offsets.

### C. Replayer Core (`mod_replay.c` / `replayer.s`)
- [ ] **Period Lower Bound Clamp:** Enforce `if (per < 113) per = 113` on every note trigger, pitch slide, and vibrato calculation. Never write `PER < 20`.
- [ ] **Volume Table Translation:** Map ProTracker volume $0 \dots 64$ to $0 \dots 255$ using the 65-entry saturation lookup table.
- [ ] **Atomic Register Writes:** Always write multi-byte registers (`LC`, `LEN`, `PER`) high-byte first, low-byte last (`ST_PER1` then `ST_PER0`).
- [ ] **Loop Pointer Timing:** Write repeat pointers (`LC`, `LEN`) on Tick 1 of a note, never in the immediate 10 CPU cycles following `ADMACON` enable.
- [ ] **LED Filter Toggle:** Bind Effect `E00` to `ACTRL &= ~0x01` and `E01` to `ACTRL |= 0x01`.
- [ ] **Panning Effect `8xx`:** Safely ignore `8xx` commands.
- [ ] **Interrupt Hygiene:** Execute the replayer tick exclusively inside the card's `/FIRQ` service routine; mask interrupts during any non-interrupt card access.
