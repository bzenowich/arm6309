# Protracker 3.62 Feature Inventory & Haiku Tracker Roadmap

This document catalogs every feature, sub-screen, effect, and tool provided by **Protracker 3.62** (the late-era Amiga 4-channel MOD tracker, developed by Cryptoburners and maintained through v3.61/v3.62 by Tom Beyer and Jan Poruba in 1996).

It serves as the specification checklist for designing **Tracker** on the **arm6309** homebrew personal computer, mapping classic Amiga tracker functionality onto the machine's discrete Paula-compatible sound card and high-resolution Haiku GUI.

---

## 1. System Context & Architecture

| Component | Classic Amiga (OCS/AGA) | arm6309 Homebrew PC |
|---|---|---|
| **CPU** | Motorola 68000 @ 7.09 MHz (or 68020/030) | Hitachi HD6309E @ 2.098 MHz ($E$ clock) |
| **Operating System** | AmigaOS / Exec / Intuition (or direct hardware) | NitrOS-9 Level 2 (UNIX-like multitasking, MMU banked) |
| **Sound Hardware** | Paula discrete 4-channel 8-bit signed PCM | Discrete 4-channel Paula replica with 512 KB sample SRAM |
| **Period Reference Clock** | 3.546895 MHz (PAL color clock) | 3.546895 MHz (PAL color clock) — **100% bit-exact tuning** |
| **Tempo Timer** | CIA-B Timer A (clocked at 709.379 kHz) | On-card 16-bit timer @ 709.379 kHz — **exact CIA tempo** |
| **Replayer Interrupt** | Level 6 / Level 4 Audio Interrupt | CPU `/FIRQ` interrupt (~2.7% CPU overhead @ 2.098 MHz) |
| **Scheduling Priority** | AmigaOS Task Priority (+20 or custom) | NitrOS-9 Priority 135 (`F$SPrior`) with `F$Sleep 2` yielding — prioritized without CPU starvation |
| **Analogue Filter** | Switchable RC + 2nd-order Sallen-Key ("LED filter") | On-card hardware Sallen-Key low-pass filter (`ACTRL_LED`) |
| **Screen Resolution** | 320 × 256 @ 50 Hz (PAL) or 320 × 200 (NTSC), 4/8 bpp | **640 × 480 @ 60 Hz 16-bit RGB565** (Video3 Card) |
| **Storage / Filesystem** | OFS/FFS on 3.5" 880 KB floppies (`df0:`) or HDD | SDHC SPI controller on `/sd0` (RBF hierarchical filesystem) |
| **User Interface** | Fixed 320×256 custom bitmap screens | **Haiku-inspired GUI** via ROM Toolbox (`tbox`), mouse + PS/2 keyboard |

---

## 2. Complete Protracker 3.62 Feature Inventory

### 2.1 Pattern Editor & Playback Core
* **4-Channel Matrix Display**: 4 polyphonic tracks (Tracks 1–4), hard-panned Left-Right-Right-Left (LRRL).
* **64 Rows per Pattern**: Standard rows `00` through `63` per pattern.
* **100 Patterns Allocation**: Patterns `00` to `99` supported (up from 64 in early trackers).
* **128 Song Positions**: Order list with positions `000` through `127` pointing to pattern indices.
* **Song Length**: Configurable number of positions (`001` to `128`).
* **Restart Position**: Loop jump target position.
* **Note Entry via Keyboard**: 2-octave chromatic piano keyboard mapped across QWERTY keys (with octave transposition).
* **Octave Selector**: Octaves 1, 2, and 3 (extended tuning range up to Octave 4 in PT 3.x).
* **Step Increment (Auto-Advance)**: Configurable cursor advance step after entering a note (`00` to `16` rows).
* **Edit Modes**:
  * **Edit Mode**: Standard cursor navigation and note/effect entry.
  * **Record Mode**: Real-time note recording during playback.
* **Transport Controls**:
  * **Play Song**: Plays full module from current song position to the end.
  * **Play Pattern**: Loops current pattern continuously.
  * **Play from Cursor**: Starts playback from current row.
  * **Stop**: Immediately halts audio playback and silences all channels.
* **Follow Song (Scroll Lock)**: Toggle whether pattern display follows the playback cursor or stays fixed during editing.
* **Channel Controls**:
  * Channel Mute (silence individual channels 1–4).
  * Channel Solo (solo a selected channel).

---

### 2.2 Protracker Effect Command Set
Protracker 3.62 implements the full standard MOD effect set:

| Command | Name | Parameters | Behavior |
|---|---|---|---|
| `0xy` | **Arpeggio** | `x`: semitone 1, `y`: semitone 2 | Cycles root note, note+$x$, note+$y$ on alternating ticks |
| `1xx` | **Portamento Up** | `xx`: slide speed | Slides pitch upward by $xx$ units per tick |
| `2xx` | **Portamento Down** | `xx`: slide speed | Slides pitch downward by $xx$ units per tick |
| `3xx` | **Tone Portamento** | `xx`: slide speed | Glides pitch toward target note at speed $xx$ |
| `4xy` | **Vibrato** | `x`: speed, `y`: depth | Oscillates pitch with sine/ramp/square waveform |
| `5xy` | **Tone Portamento + Volume Slide** | `x`: up speed, `y`: down speed | Continues tone portamento (`300`) while sliding volume |
| `6xy` | **Vibrato + Volume Slide** | `x`: up speed, `y`: down speed | Continues vibrato (`400`) while sliding volume |
| `7xy` | **Tremolo** | `x`: speed, `y`: depth | Oscillates volume with sine/ramp/square waveform |
| `8xx` | **Set Panning** *(optional)* | `xx`: panning ($00$–$FF$) | Unused on classic Paula (hardwired LRRL); optional in PT3 |
| `9xx` | **Sample Offset** | `xx`: offset in 256-byte blocks | Starts sample playback at byte offset $xx \times 256$ |
| `Axy` | **Volume Slide** | `x`: slide up, `y`: slide down | Changes channel volume by $+x$ or $-y$ per tick |
| `Bxx` | **Position Jump** | `xx`: order position | Jumps to song position $xx$ at the start of next row |
| `Cxx` | **Set Volume** | `xx`: volume ($00$–$40$) | Immediately sets channel volume ($0$ to $64$) |
| `Dxx` | **Pattern Break** | `xx`: row number (BCD/hex) | Jumps to next pattern at row $xx$ |
| `E0x` | **Set Filter** | `x`: 0 = filter ON, 1 = OFF | Toggles hardware 3.3 kHz Sallen-Key audio low-pass filter |
| `E1x` | **Fine Portamento Up** | `x`: pitch units | Slides pitch up by $x$ once on tick 0 |
| `E2x` | **Fine Portamento Down** | `x`: pitch units | Slides pitch down by $x$ once on tick 0 |
| `E3x` | **Glissando Control** | `x`: 0 = smooth, 1 = semitones | Toggles whether portamento slides smoothly or chromatically |
| `E4x` | **Set Vibrato Waveform** | `x`: waveform & retrigger | 0=sine, 1=sawtooth, 2=square, +4=no retrigger |
| `E5x` | **Set Finetune** | `x`: signed finetune ($-8$..$+7$) | Overrides sample finetune parameter on current channel |
| `E6x` | **Pattern Loop** | `x`: 0 = set loop point, >0 = count | Loops current pattern segment $x$ times |
| `E7x` | **Set Tremolo Waveform** | `x`: waveform & retrigger | 0=sine, 1=sawtooth, 2=square, +4=no retrigger |
| `E9x` | **Retrigger Note** | `x`: tick interval | Retriggers the note every $x$ ticks |
| `EAx` | **Fine Volume Slide Up** | `x`: volume units | Increases volume by $x$ once on tick 0 |
| `EBx` | **Fine Volume Slide Down** | `x`: volume units | Decreases volume by $x$ once on tick 0 |
| `ECx` | **Note Cut** | `x`: tick count | Mutes channel after $x$ ticks |
| `EDx` | **Note Delay** | `x`: tick count | Delays note triggering until tick $x$ |
| `EEx` | **Pattern Delay** | `x`: row duration multiplier | Freezes pattern progression for $x$ rows |
| `EFx` | **Invert Loop (Funk Repeat)**| `x`: speed | Cycles loop backwards/forwards (rarely used effect) |
| `Fxx` | **Set Speed / Tempo** | `xx`: $01$–$1F$ speed; $20$–$FF$ BPM | Sets ticks per row ($1$–$31$) or BPM tempo ($32$–$255$) |

---

### 2.3 Pattern & Track Operations (Edit Op)
* **Track Operations**:
  * Copy Track / Paste Track.
  * Clear / Erase Track.
  * Transpose Track Up/Down by 1 semitone.
  * Transpose Track Up/Down by 1 octave (12 semitones).
* **Pattern Operations**:
  * Copy Pattern / Paste Pattern.
  * Clear / Erase Pattern.
  * Transpose Pattern Up/Down (1 semitone or 1 octave).
  * Expand Pattern (doubles row spacing, inserts empty rows).
  * Compress Pattern (halves row spacing, drops alternating rows).
* **Block Editing**:
  * Set Block Mark Start / Mark End.
  * Cut / Copy / Paste Block (with merge/overwrite options).
  * Erase / Clear Block.
* **Sample Remapping**:
  * Exchange Instrument: swap Sample $A$ with Sample $B$ across the current track, current pattern, or entire module.
* **Quantization**:
  * Align notes to rhythmic grids (useful after real-time recording).

---

### 2.4 Sample Management & Sample Editor
* **31 Sample Slots** (`01` through `31`):
  * Sample Name (22 ASCII characters).
  * Sample Length (stored in 16-bit words, up to 64 Kwords = 128 KB per sample).
  * Finetune (signed $-8$ to $+7$, adjustments of $\pm 1/8$ semitone).
  * Default Volume ($0$ to $64$).
  * Repeat (Loop) Offset (word offset).
  * Repeat (Loop) Length (word count; length $>1$ enables looping).
* **Waveform Display & Editing**:
  * Visual graphic waveform canvas displaying sample amplitude over time.
  * Zoom In / Zoom Out / View All.
  * Interactive Loop Marker adjustment (visual start and length markers).
  * Range Selection (Mark Start, Mark End).
  * Clipboard operations: Cut, Copy, Paste, Insert, Crop (keep selection only), Erase/Silence.
  * Pencil / Freehand waveform drawing (direct sample point editing).
* **Sample DSP Tools**:
  * **Normalize**: Scale peak amplitude to maximum dynamic range ($\pm 127$).
  * **Maximize / Limiter**: Hard limiting and compression to boost quiet sections.
  * **Remove DC Offset (`NormalDC`)**: Centers waveform around zero axis to eliminate pops and thumps.
  * **Invert**: Inverts waveform phase ($x \to -x$).
  * **Reverse**: Flips sample backwards in time.
  * **Fade In / Fade Out**: Linear or exponential volume ramping.
  * **Volume Scale / Boost**: Manual amplification or attenuation.
  * **Resample / Tuning**: Pitch-shift or change sample rate.
  * **Mix / Blend**: Combine two samples with crossfading or summing.
* **Auditioning / Playback**:
  * Play Range (play selected portion).
  * Play Display (play zoomed section).
  * Play All (play full sample).
  * Play Looped (play with looping active).

---

### 2.5 7-Note Chord Editor ("Chord Maker")
* **Polyphonic Chord Stacking**: Mixes up to 7 notes of a sample together into a single sample, allowing full chords to play on a single audio channel.
* **Chord Presets**:
  * Major, Minor, 5th (Power Chord).
  * Dominant 7th, Minor 7th, Major 7th, Diminished 7th, Half-Diminished.
  * Suspended 2nd, Suspended 4th, Added 9th, Minor 9th.
* **Custom Intervals**: Manually set semitone offset for each of the 7 voice components.
* **Inversion & Octave Controls**: Octave shift and chord inversions (1st, 2nd, 3rd inversion).
* **Automatic Leveling**: Normalizes and scales the combined waveform to prevent digital clipping/distortion.
* **Automatic Loop Recalculation**: Computes a seamless loop point for the newly generated chord sample.

---

### 2.6 Position Editor (Pos Ed)
* **Song Structure Overview**: Visual table of the song order list ($000$ to $127$).
* **List Navigation**: Scroll through the sequence of patterns forming the song.
* **Insert Position**: Insert a new pattern position into the sequence.
* **Delete Position**: Remove a position from the sequence.
* **Duplicate / Clone Position**: Repeat existing patterns.
* **Restart Marker**: Set loopback position when song ends.

---

### 2.7 Disk Operations (Disk Op) & File Formats
* **File Management**:
  * Directory browser with file list.
  * Path navigation (switch drives, go up to parent directory).
  * Delete file, Rename file.
  * Disk free space indicator.
* **Supported File Types**:
  * **Module (`.MOD`)**: Load and Save standard 4-channel Protracker modules (`M.K.` / `M!K!` magic).
  * **Sample (`.SMP` / `.IFF` / `.RAW`)**:
    * Load and Save raw 8-bit signed PCM samples.
    * Load and Save Amiga IFF-8SVX (Interchange File Format 8-bit Sampled Voice) files.
  * **Pattern (`.PAT`)**: Save or load individual pattern data.
  * **Track (`.TRK`)**: Save or load single-channel track data.
* **Historical Features Removed**:
  * *XPK Decompression*: Amiga-specific library compressor cut; raw and standard MOD files only.
  * *Amiga Floppy Polling*: Custom trackdisk/motor delay code cut; standard NitrOS-9 filesystem I/O used instead.
  * *DYN 14-Bit System*: Obsolete experimental mode cut.
  * *IFF-MOD Container*: Redundant container format cut; standard `.mod` used.
  * *mod2smp*: Obsolete standalone dump utility cut.

---

### 2.8 Visual Feedback
* **Hardware LED Indicator**: Visual status indicator displaying state of the hardware Sallen-Key audio filter (`ACTRL_LED`).
*(Note: Real-time scopes, VU meters, and spectrum analyzers are cut to preserve 6309 CPU cycles for rock-solid replayer timing and low UI latency).*

---

### 2.9 Setup Screen & Configuration
* **Audio Filter Control**: Manual toggle for the hardware audio low-pass filter (`ACTRL_LED`).
* **Keyboard Repeat Settings**: Key repeat speed and initial delay.
* **Cursor Styling**: Solid block, outline, or underline pattern cursor.
* **Metronome**: Audio click generator at configurable beat intervals.
*(Note: NTSC tuning toggle is omitted because the arm6309 hardware is fixed to PAL 28.37516 MHz master crystal).*

---

## 3. Analysis: What to Keep, What to Modernize, What to Drop

### 3.1 What Must Be 100% Kept (Core Tracker Identity)
1. **The Replayer Engine**: Byte-for-byte fidelity with the Amiga Paula playback rules (loop pointer updates after DMA enable, period calculations, volume laws, full effect table `0`–`F`, `E0`–`EF`).
2. **Keyboard Ergonomics**: The classic tracker 2-octave piano keyboard layout on QWERTY keys, with cursor navigation, Delete, Insert, and rapid effect entry.
3. **MOD File Compatibility**: Flawless loading and saving of standard 4-channel `M.K.` modules that play identically on real Amigas and PC tracker tools.
4. **Sample Editor**: Complete visual waveform trimming, loop point setting, normalization, and volume scaling.
5. **Chord Editor**: 7-note chord generation is one of Protracker 3's standout creative tools.
6. **Hardware LED Indicator**: Visual indicator for the hardware Sallen-Key low-pass filter state.

### 3.2 What Is Dropped (Historical Baggage & Real-Time Visualizers)
* **XPK Decompression**: Amiga-specific library compressor. On arm6309, standard raw files or standard formats on the SD filesystem are preferred.
* **Amiga Disk Polling (`df0:`, `df1:`, DMA wait settings)**: Classic PT3 spent significant code dealing with slow floppy motor timing and custom trackdisk routines. On arm6309, NitrOS-9 handles high-speed SPI SD card transfers via standard POSIX/OS-9 file calls.
* **Experimental DYN System**: An abandoned 14-bit audio experiment from early PT 3.x that was broken and incompatible with standard MOD players.
* **IFF-MOD Format & mod2smp**: Obsolete auxiliary formats.
* **NTSC Switch**: Sound card has a dedicated PAL master crystal; NTSC tuning tables are omitted to save memory and avoid off-pitch playback.
* **Real-time Visualizers**: Quadrascope, VU meters, and spectrum analyzer are cut to eliminate display redraw overhead during playback on a 2 MHz 6309.
* **320×256 Screen Swapping**: On the Amiga, the pattern editor, sample editor, and disk op had to completely overwrite each other due to the 320×256 display. With 640×480, this limitation is eliminated.

### 3.3 What Should Be Modernized (Haiku GUI Enhancements)
1. **640 × 480 High-Resolution Screen Space**:
   * Display **16 to 32 pattern rows** simultaneously (compared to only 8 on the Amiga).
   * Keep the **transport bar, sample details, song position, and hardware LED indicator permanently visible** above or beside the pattern editor.
   * Wide, high-resolution sample waveform editor (e.g. 512×120 pixels instead of Amiga's cramped 300×60).
2. **Haiku-Style UI Components**:
   * **Yellow Title Tabs**: Distinctive Haiku window tabs with close box and title in proportional font.
   * **Beveled Buttons & Controls**: Clean system grey bevels matching the desktop and `desk.asm`.
   * **Top Menu Bar**: Pull-down menus (`File`, `Edit`, `Track`, `Sample`, `View`, `Settings`) accessible via mouse or <kbd>Alt</kbd> shortcuts.
   * **Visual Tabs for Sub-Views**: Clean tabs to switch between *Pattern View*, *Sample Studio*, *Chord Maker*, and *Song Structure*.
3. **Enhanced Mouse & File Navigation**:
   * Mouse drag for block selection in patterns.
   * Interactive dragging of loop start/end points on the sample waveform.
   * Standard NitrOS-9 file dialog with hierarchical directory traversal and long paths.
   * Mouse scroll-wheel support for scrolling through patterns, samples, and file lists.

---

## 4. Final Feature Scope & Roadmap for `software/tracker`

We divide development into four progressive tiers:

### Tier 1: Replayer & Standalone Player ("MOD Player")
* Full `.MOD` file loader (streaming parser: header, 31 sample headers, pattern matrix, sample PCM with bit 7 inversion).
* Upload sample data into dedicated 512 KB sound card SRAM with chunked `TFM` and interrupt discipline.
* FIRQ-driven 50 Hz/BPM timer replayer implementing all Protracker effects (`0`–`F`, `E0`–`EF`).
* Null-loop target (`$80 $80`) initialization at card RAM `$00000`.
* Standalone CLI player command: `modplay <file.mod>`.
* **Balanced Scheduling & Sleep Yielding**: Set NitrOS-9 priority to 135 (`F$SPrior`) and yield CPU on the sleep queue (`F$Sleep 2`) between audio ticks so playback is glitch-free while desktop clicking, window drags, and virtual consoles remain fully responsive.
* Optimized terminal output: Refresh status display only on row boundary (`tick == 0`) or user action to eliminate serial/SCF latency.

### Tier 2: Core Haiku Tracker Interface & Pattern Editor
* 640 × 480 Video3 GUI with Haiku window chrome, top menu bar, and yellow tabs.
* 4-channel pattern matrix display showing 16–32 rows with current playhead highlighting.
* QWERTY piano keyboard note entry, octave switching, edit step auto-advance.
* Transport controls (Play Song, Play Pattern, Stop, Record).
* Song position list editor (Pos, SongLen, Patt index).
* Hardware LED filter indicator (showing state of `ACTRL_LED`). No scope/VU meter overhead.
* **Balanced Application Priority**: Tracker process initializes with priority 135 and yields via `F$Sleep 2` between ticks so interactive audio playback remains stutter-free even while multi-tasking.

### Tier 3: Editing Tools & File Operations
* Track and Pattern editing: Transpose, Copy, Paste, Clear, Quantize.
* Pattern block selection (Cut, Copy, Paste).
* Sample remapping across tracks and patterns.
* File browser dialog (Load/Save Song, Load/Save Sample, directory navigation on `/sd0`).

### Tier 4: Sample Studio & Chord Maker
* Graphical Waveform Editor with Zoom, Selection, and Loop Marker editing.
* Sample DSP tools: Normalize, Remove DC Offset, Invert, Reverse, Volume Fade.
* 7-Note Chord Editor with presets and automated loop calculation.
* Save modified samples and export complete MOD files.
