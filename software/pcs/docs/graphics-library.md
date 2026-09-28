# Bill Budge's Graphics Library in *Pinball Construction Set* (Apple II, 1982–1983)
## Architectural Analysis, Routine Catalog, and Design Foundation for the 6309 Homebrew PC

---

## 1. Executive Summary & Historical Context

In 1982, Bill Budge published *Pinball Construction Set* (PCS) for the Apple II through BudgeCo (and subsequently Electronic Arts in 1983). PCS is universally celebrated as a landmark title that pioneered the "construction set" genre, featuring a graphical user interface with floating windows, draggable tool icons, and a mouse/paddle cursor years before the Macintosh was unveiled.

Beneath its groundbreaking interface lay what was arguably the most sophisticated, cycle-squeezed 2D graphics engine ever authored for the MOS 6502 microprocessor. Operating within the constraints of a 1.0227 MHz 8-bit CPU, 48 KB of RAM, and the idiosyncratic Apple II High-Resolution Graphics (HGR) subsystem (280 × 192 monochrome or 140 × 192 artifact color, 7 pixels packed per byte with complex row interleaving), Budge created:
1. **A 28-cycle-per-byte sub-pixel bitmap blitter (`XOFFDRAW`)** capable of shifting unaligned 7-bit bitmaps across byte boundaries at arbitrary horizontal offsets without runtime shift instructions.
2. **A real-time Active Edge List (AEL) polygon scan converter (`SCANPOLY`)** with 16.8 fixed-point edge stepping, midpoint rounding, and topological orientation normalization on a 6502.
3. **A unified display list and collision spatial index (`PBDX`)** implemented as a dynamic gap buffer that served simultaneously as the rendering list, the UI hit-test structure, and the physics simulation collision geometry.
4. **An incremental XOR delta blitter (`BALLDOWN`, `BALLUP`, etc.)** that animated moving objects by XORing precomputed single-pixel boundary differences (`VBALL`, `HBALL`), cutting screen bus bandwidth by over 60% compared to full redraws.
5. **A real-time "fat bits" pixel magnifier (`BLOWUP`)** using self-modifying unrolled write loops to magnify screen pixels into a 6×6 block editor with full Apple II NTSC color artifact emulation.
6. **An orthogonal Manhattan wire router (`DRAWWIRE`)** that generated multi-segment circuit connections using fast horizontal and vertical span routines.

This document presents a comprehensive, routine-by-routine disassembly and architectural analysis of the original Apple II assembly source code for PCS (`source_disc1/CDRAW.S`, `source_disc1/PPAK.S`, `source_disc1/EDIT.S`, `source_disc2/RUN.S`, `source_disc1/RUN2.S`, and `source_disc2/WIRE.S`), dissecting how each routine operated and how Budge optimized it. It concludes with concrete architectural blueprints translating these 8-bit graphics engineering patterns to the **arm6309** homebrew computer (a Hitachi HD63C09E running native mode at 2.0979 MHz with the `video3` 640 × 480 chunky 8bpp card).

---

## 2. Apple II Hi-Res Hardware Architecture & Coordinate Model

To appreciate Budge's optimizations, one must understand the idiosyncratic constraints of the Apple II High-Resolution Graphics subsystem.

### 2.1 The Apple II Framebuffer: 7 Pixels per Byte and Interleaved Rows
The Apple II HGR screen occupies 8,192 bytes ($2000–$3FFF for Page 1; $4000–$5FFF for Page 2). It provides a nominal resolution of 280 × 192 pixels.
- **7 Pixels per Byte:** Bits 0–6 represent seven horizontal pixels (bit 0 leftmost, bit 6 rightmost). Bit 7 does not display a pixel; instead, it delays the pixel phase by half a color clock, choosing between two color palettes (Green/Violet vs. Orange/Blue on NTSC displays).
- **Scanline Interleaving:** Rather than being a linear array where scanline $Y$ follows $Y-1$, the Apple II hardware addresses scanlines in three 64-line tiers, interleaved in 8-line groups:
  $$\text{Address}(Y) = \text{Base} + ((Y \pmod 8) \times 1024) + (\lfloor (Y \pmod{64}) / 8 \rfloor \times 40) + (\lfloor Y / 64 \rfloor \times 40)$$

### 2.2 Budge's Coordinate Decomposition & Lookup Tables
Rather than calculating this polynomial at runtime, Budge uses two 192-byte lookup tables:
- `LO` ($1600): The low byte of the base address for scanline $Y$.
- `HI` ($16C0): The high byte of the base address for scanline $Y$ (values $20..$3F).

Every horizontal pixel coordinate $X$ ($0..279$) is decomposed into:
$$\text{HDIV7} = X / 7 \quad (\text{byte offset } 0..39 \text{ across the scanline})$$
$$\text{HMOD7} = X \pmod 7 \quad (\text{bit shift } 0..6 \text{ within the byte})$$

Budge replaces division and modulo with precalculated 256-byte lookup tables:
- `DIV7` ($1400): Given $X$, returns $X / 7$.
- `MOD7` ($1500): Given $X$, returns $X \pmod 7$.

Accessing screen byte address for $(X, Y)$ requires just 17 clock cycles:
```assembly
LDY YCOORD
LDA LO,Y        ; 4 cycles: Low byte of scanline
CLC             ; 2 cycles
ADC DIV7,X      ; 4 cycles: Byte offset (X/7)
STA BASE1       ; 3 cycles
LDA HI,Y        ; 4 cycles: High byte of scanline
STA BASE1+1     ; 3 cycles
```

### 2.3 Color Representation & Artifact Dithering
Because adjacent 1-bits bleed together on NTSC color screens, two adjacent bits produce white ($7F), while alternating bits produce pure colors depending on whether they land on odd or even bit positions. Budge pre-populates a 40-byte line buffer `COLORBAR` ($0200) with repeating byte pairs corresponding to each selected color index (`CLRPATCH`, `PPAK.S:277`):
- Black: `$00, $00`
- Green: `$2A, $55`
- Violet: `$55, $2A`
- White: `$7F, $7F`
- Red (Orange): `$AA, $D5` (with bit 7 palette shift)
- Blue: `$D5, $AA` (with bit 7 palette shift)

---

## 3. Detailed Catalog of PCS Apple II Drawing Routines

### 3.1 Low-Level Bitmaps and Blitting (`CDRAW.S`)

#### `GETBITS` (`CDRAW.S:83–110`)
* **Purpose:** Unpacks a 7-byte bitmap descriptor into zero-page working variables.
* **Input:** Pointer to descriptor in `A` (low) and `X` (high).
* **Format of Descriptor:**
  * `Bytes 0..1`: 16-bit source pointer to raw bitmap data.
  * `Byte 2`: Vertical scanline $Y$ ($0..191$).
  * `Byte 3`: Horizontal byte column $\text{HDIV7} = X / 7$ ($0..39$).
  * `Byte 4`: Horizontal sub-pixel bit offset $\text{HMOD7} = X \pmod 7$ ($0..6$).
  * `Byte 5`: Height in scanlines.
  * `Byte 6`: Width in bytes (stored as $\text{Width}-1$ for zero-indexed loops).
* **Optimization:** Loads all fields directly into zero page (`BASE2`, `VERT`, `HDIV7`, `HMOD7`, `HEIGHT`, `WIDTH`). By decrementing width by 1 at unpack time (`SBC #1`), the inner blit loops can use post-decrement indexing (`DEY; BPL loop`) with zero branch penalties.

#### `SETMODE` (`CDRAW.S:138–164`)
* **Purpose:** Sets the raster operation (pen mode) for bitmap and rectangle rendering: `STORE` (overwrite), `GRAB` (readback), `XOR` (invert/composite), `CLR` (mask clear), and `OR` (mask set).
* **Input:** Pen mode index in register `Y` ($0..4$).
* **Optimization:** **Zero-branch runtime dispatch via self-modifying code.** Instead of testing a mode variable inside pixel blit loops, `SETMODE` reads the address of the corresponding mode routine from jump tables (`PTBL1`, `PTBL2`, `PTBL3`) and directly overwrites the target address operand of `JMP` instructions in `DRAWBITS` (`PMPATCH1`), `HLINE` (`PMPATCH2`, `PMPATCH3`), and `VLINE` (`PMPATCH4`).
```assembly
SETMODE LDA PTBL1,Y      ; Y = Pen Mode (0=STORE, 1=GRAB, 2=XOR, 3=CLR, 4=OR)
        STA PMPATCH1     ; Overwrite JMP target in DRAWBITS
        LDA PTBL2,Y
        STA PMPATCH2     ; Overwrite JMP target in HLINE
        LDA PTBL3,Y
        STA PMPATCH3
        STA PMPATCH4     ; Overwrite JMP target in VLINE
        RTS
```
Inside the inner loops, dispatch is an unconditional `JMP` taking 3 cycles, completely eliminating `CMP`/`BEQ`/`BNE` trees (which would cost 10–15 cycles per scanline).

#### `DRAWBITS` (`CDRAW.S:165–192`)
* **Purpose:** Blits a byte-aligned ($\text{HMOD7} = 0$) rectangular bitmap to screen memory.
* **Input:** Bitmap descriptor passed to `GETBITS`.
* **Execution Flow:**
  1. Calls `GETBITS`.
  2. For each scanline ($Y = \text{VERT}$):
     - Looks up base screen pointer from `LO,Y` and `HI,Y`.
     - Adds `HDIV7` to compute destination `BASE1`.
     - Jumps to patched mode handler (`STORE`, `XOR`, etc.).
     - Steps source `BASE2` by `WIDTH` and increments `VERT`.
* **Mode Handlers (`CDRAW.S:114–135`):**
  ```assembly
  STORE LDA (BASE2),Y   ; 5 cycles
        STA (BASE1),Y   ; 6 cycles
        DEY             ; 2 cycles
        BPL STORE       ; 3 cycles (16 cycles / byte total!)
        BMI DRAWBTS3
  XOR   LDA (BASE2),Y   ; 5 cycles
        EOR (BASE1),Y   ; 5 cycles
        STA (BASE1),Y   ; 6 cycles
        DEY             ; 2 cycles
        BPL XOR         ; 3 cycles (21 cycles / byte total!)
        BMI DRAWBTS3
  ```

#### `XOFFDRAW` (`CDRAW.S:211–258`) — *The Budge Sub-Pixel Shifter*
* **Purpose:** Blits a bitmap at an arbitrary sub-byte bit offset ($\text{HMOD7} = 1..6$) across byte boundaries in XOR mode.
* **The Engineering Problem:** On the 6502, shifting an 8-bit accumulator across byte boundaries requires repeated `ASL`/`ROL` or `LSR`/`ROR` instructions. Shifting an $N$-byte scanline by $S$ bits requires $N \times S \times 4$ cycles—prohibitive for real-time 60 Hz animation.
* **Budge’s Solution:** **Two 1,536-byte precomputed shift lookup tables (`SHFRSLT` and `SHFOUT`) coupled with self-modifying code.**
  * `SHFRSLT` ($0800–$0DFF): 6 pages of 256 bytes. For each possible byte value ($0..255$) and each shift amount ($1..6$), it stores the bits that remain in the current byte:
    $$\text{SHFRSLT}[S][B] = (B \ll S) \ \& \ \$7F$$
  * `SHFOUT` ($0E00–$13FF): 6 pages of 256 bytes. For each possible byte value and shift amount, it stores the bits that overflow into the adjacent byte:
    $$\text{SHFOUT}[S][B] = (B \gg (7 - S)) \ \& \ \$7F$$
* **Inner Loop Disassembly & Cycle Count (`CDRAW.S:232–245`):**
```assembly
XOFFDRW3 LDX $FFFF,Y     ; 4 cycles: Load raw sprite byte (address patched at runtime)
SHIFTOUT ORA SHFOUT,X    ; 4 cycles: Merge overflow from previous byte (high byte patched)
         EOR (BASE1),Y   ; 5 cycles: XOR directly into screen memory
         STA (BASE1),Y   ; 6 cycles: Store back to screen
SHIFTRESULT LDA SHFRSLT,X; 4 cycles: Fetch remaining shifted bits for next byte
         DEY             ; 2 cycles: Advance byte index across line
         BPL XOFFDRW3    ; 3 cycles
; Loop total: 28 CYCLES PER BYTE!
```
* **The Rightmost Boundary Spill (`CDRAW.S:242–245`):**
  When the loop terminates ($Y = -1 = \$FF$), the final residual bits in `A` must be XORed into the byte immediately preceding `BASE1`. Budge accomplishes a 16-bit decrement in two instructions:
```assembly
DEC BASE1+1      ; 5 cycles: Decrement high byte of screen pointer
EOR (BASE1),Y    ; 5 cycles: Y=$FF, so (BASE1+1-1)*256 + 255 = BASE1 - 1!
STA (BASE1),Y    ; 6 cycles: Stored into the left boundary byte
```
This is a masterclass in 6502 micro-optimization: using 8-bit page wrapping ($Y=\$FF$ with decremented high byte) to avoid a 16-bit pointer subtraction.

---

### 3.2 Geometric Primitives & Span Drawing (`CDRAW.S`)

#### `GETRECT` (`CDRAW.S:265–302`)
* **Purpose:** Unpacks a 6-byte rectangle record:
  $$\text{Record} = [\text{TOP}, \text{LFTDIV7}, \text{LFTMOD7}, \text{HEIGHT}, \text{WIDTH\_DIV7}, \text{WIDTH\_MOD7}]$$
* **Calculations:**
  - Calculates $\text{BOTTOM} = \text{TOP} + \text{HEIGHT}$.
  - Computes right edge column and bit offset:
    $$\text{RTMOD7} = (\text{LFTMOD7} + \text{WIDTH\_MOD7}) \pmod 7$$
    $$\text{RTDIV7} = \text{LFTDIV7} + \text{WIDTH\_DIV7} + \lfloor (\text{LFTMOD7} + \text{WIDTH\_MOD7}) / 7 \rfloor$$
  - Synthesizes edge bitmasks from table `MASKS` ($00, 01, 03, 07, 0F, 1F, 3F, 7F$):
    - `LEFTMASK` $= \text{MASKS}[\text{LFTMOD7}] \oplus \$7F$ (bits from `LFTMOD7` to 6 are 1).
    - `RIGHTMASK` $= \text{MASKS}[\text{RTMOD7} + 1]$ (bits from 0 to `RTMOD7` are 1).

#### `HLINE` (`CDRAW.S:311–331`)
* **Purpose:** Renders a horizontal scanline segment from `(LFTDIV7, LFTMOD7)` to `(RTDIV7, RTMOD7)`.
* **Optimization:** Splits the span into three mutually exclusive structural cases:
  1. **Single-Byte Span (`LFTDIV7 == RTDIV7`):**
     Both edges fall in the same byte. The mask is formed by:
     $$\text{Mask} = (\text{LEFTMASK} \oplus \text{RIGHTMASK}) \oplus \$7F$$
     Composited in a single memory access via `HLIN2` / `STORE3`.
  2. **Left Boundary Byte:**
     Applies `LEFTMASK` to preserve pixels to the left of `LFTMOD7`. Written via patched handler `PMPATCH2`.
  3. **Solid Middle Bytes:**
     If `RTDIV7 > LFTDIV7 + 1`, a loop executes for intermediate bytes using full byte masks (`$7F`):
     ```assembly
     XOR2A LDA #$7F
     XOR2  EOR (BASE1),Y
           STA (BASE1),Y
           INY
           CPY RTDIV7
           BCC XOR2A
     ```
  4. **Right Boundary Byte:**
     Applies `RIGHTMASK` via `PMPATCH3` / `STORE3`.

#### `VLINE` (`CDRAW.S:334–351`)
* **Purpose:** Draws a vertical line 1 pixel wide from scanline `TOP` to `BOTTOM` at column `(LFTDIV7, LFTMOD7)`.
* **Optimization:** Uses the `EDGES` table ($01, 02, 04, 08, 10, 20, 40$) to extract a 1-bit mask corresponding to `LFTMOD7`. Steps vertically using the `LO,X` and `HI,X` tables, writing through patched mode `PMPATCH4`:
```assembly
VLIN2 LDA LO,X
      STA BASE1
      LDA HI,X
      STA BASE1+1
      LDA LEFTEDGE
      JSR STORE3     ; Self-modifying vector (EOR (BASE1),Y / STA (BASE1),Y)
      INX
      CPX BOTTOM
      BCC VLIN2
```

#### `FRAMERECT` & `DRAWRECT` (`CDRAW.S:400–430`)
* **`FRAMERECT`:** Unpacks bounding box via `GETRECT`, calls `HLINE` for `TOP` and `BOTTOM`, then adjusts `TOP`/`BOTTOM` inward and calls `VLINE` for left and right columns.
* **`DRAWRECT`:** Fills a solid or XOR box. Loops from $X = \text{TOP}$ to $\text{BOTTOM}$, calling `HLINE` once per scanline.

#### `INRECT` & `CRSRINRECT` (`CDRAW.S:434–458, 616–625`)
* **Purpose:** Point-in-rectangle hit testing for UI buttons, icons, and menus.
* **Optimization:** Compares coordinates directly in divided/modular form without computing a 16-bit pixel coordinate:
  First tests byte column against `LFTDIV7` and `RTDIV7`. Only if the point lies on the boundary byte does it test the `MOD7` sub-pixel offset. Finally tests vertical row against `TOP` and `BOTTOM`.

---

### 3.3 Polygon Scan Conversion and Span Database (`PPAK.S`)

The core of PCS is its vector-to-raster scan converter. Polygons define walls, flipper outlines, bumpers, and the table background.

```
       Polygon Vertices
              │
              ▼
       PROCESSPOLY
   (Sort extrema into starts,
     chains, & terminals)
              │
              ▼
           DIVIDE
  (Fixed-point 16.8 slopes
   & 16 surface normal codes)
              │
              ▼
          SCANPLY
  (Active Edge List scanline
   stepping & midpoint ROR)
              │
              ▼
           DOSCAN
   ┌──────────┴──────────┐
   ▼                     ▼
 DOBAR                PBDX
(Raster XOR span  (Retained span DB
 to screen)        & collision model)
```

#### `PROCESSPOLY` (`PPAK.S:459–495`)
* **Purpose:** Traverses the vertex ring of a polygon (up to 63 vertices) and classifies every vertex into local extrema:
  - **Start:** $V_{prev}.Y < V_{curr}.Y > V_{next}.Y$ (a local minimum in screen space; introduces two new active edges).
  - **Terminal:** $V_{prev}.Y > V_{curr}.Y < V_{next}.Y$ (a local maximum; terminates two edges).
  - **Chain:** Monotonic edge continuation ($V_{prev}.Y < V_{curr}.Y < V_{next}.Y$).
* **Optimization:** Detects and skips purely horizontal edges (`PRVRTX2: CMP (PLYPTRY),Y; BEQ PRVRTX2`), which contribute no spans and cause divide-by-zero errors in slope calculation.
* **Wrap-around Protection (`PPAK.S:469–494`):**
  Uses a `WRAPPOINT` sentinel to ensure that the closing edge from $V_{N-1}$ to $V_0$ is evaluated with correct topological continuity.

#### `DIVIDE` and `QDIV` (`PPAK.S:684–786`)
* **Purpose:** Computes edge slopes $dx/dy$ as 16-bit fixed-point values (`DXCOEFF` integer, `DXFRACT` 8-bit fractional part), and quantizes slope angles into 16 surface normal codes.
* **`QDIV` (Quick 16 × 8 Division, `PPAK.S:744–786`):**
  A customized non-restoring binary divider. Pre-scales the divisor `DVSR` by shifting left until its MSB aligns with the dividend, then executes an 8-iteration shift-and-subtract loop.
* **Surface Normal Quantization (`PPAK.S:706–741`):**
  Maps the calculated slope into a 4-bit angle index ($0..15$) using two lookup tables:
  - `DXCODESA`: For steep slopes ($|dx/dy| \ge 1$).
  - `DXCODESB`: For shallow slopes ($|dx/dy| < 1$).
  These codes represent surface normals and are stored in the span database. When the ball collides with an edge in `RUN.S`, this code immediately indexes reflection cosine tables without any vector dot-product calculation!

#### `SCANPLY` (`PPAK.S:380–454`) — *The Active Edge List Rasterizer*
* **Purpose:** Scan-converts the active edges down the screen line by line.
* **Active Edge Structure (`ANEXT`, `ANVRTX`, `AYFLG`, `AXCOEFF`, `AXFRACT`, `ADXCOEFF`, `ADXFRACT`, `ADXCODE`):**
  Holds up to 8 active edges simultaneously.
* **Fractional Edge Stepping & Midpoint Rounding (`PPAK.S:424–435`):**
```assembly
SCANPLY6 LDA AXFRACT,X
         CLC
         ADC ADXFRACT,X  ; Add fractional slope
         STA AXFRACT,X
         LDA AXCOEFF,X   ; Current integer X
         STA TEMP
         ADC ADXCOEFF,X  ; Add integer slope + carry
         STA AXCOEFF,X
         CLC
         ADC TEMP        ; Average X_old and X_new:
         ROR             ; (X_old + X_new) / 2 = MIDPOINT ROUNDING!
         LDY HCNT
         STA (MIDBTM),Y  ; Store rounded X span boundary into DB
```
* **Why Midpoint Rounding Matters:** Shifting an edge across a scanline introduces aliasing. Averaging the entry coordinate and exit coordinate of the scanline (`ADC TEMP; ROR`) rounds the edge intersection to the center of the pixel, producing symmetric geometry and preventing single-pixel dropouts.

#### `DOSCAN` and `DOBAR` (`PPAK.S:790–950`)
* **Purpose:** Emits horizontal spans for the current scanline to both the screen (`DOBAR`) and the collision database (`PBDX`).
* **Complement Mode (`BPOLYGON` Background):**
  If `SCANMODE` bit 6 is set, the object is a backdrop. The routine inverts span polarity: instead of filling the interior of the edge pairs, it fills the gaps between them, painting the playfield around the obstacles.
* **`DOBAR` (`PPAK.S:908–949`):**
  Fills a span from $X_1$ to $X_2$ using `COLORBAR` patterns:
  - Maps $X_1 \to \text{DIV7, MOD7}$ and $X_2 \to \text{DIV7, MOD7}$.
  - Generates `LEFTMASK` and `RIGHTMASK`.
  - Loops across the span, applying:
    $$\text{Screen}[Y] = \text{Screen}[Y] \oplus (\text{COLORBAR}[Y] \ \& \ \text{Mask})$$
  Because it XORs with `COLORBAR`, drawing the same polygon twice erases it completely.

---

### 3.4 The Retained Span Database (`PPAK.S`)

Unlike modern rendering pipelines that discard rasterized geometry after writing to the framebuffer, PCS retains every span in a structured in-memory display list:
$$\text{Span Record (4 bytes)} = [X_{left}, \text{ObjectID}, X_{right}, (\text{Slope}_{right} \ll 4) \mid \text{Slope}_{left}]$$

- `PBDX` ($6F40–$703F): A 192-byte array containing the byte length of span records on each scanline $Y$.
- **Gap Buffer Storage (`MIDBTM`, `MIDTOP`, `MAKEHOLE`, `PPAK.S:1048–1089`):**
  Span records are stored sequentially in a memory arena. When an object is added or deleted:
  - `GETSCAN` finds the offset of scanline $Y$.
  - `MAKEHOLE` moves subsequent spans up or down (`MOVEUP`/`MOVEDOWN`), sliding a memory gap to the target insertion point.
- **Why this was Revolutionary:**
  1. **Zero-Cost Hit Testing (`SELECTPOLY`, `PPAK.S:1093–1126`):**
     To determine which polygon the user clicked, `SELECTPOLY` reads scanline $Y = \text{CURSORY}$, gets the span records from `PBDX`, and searches for a span whose $[X_{left}, X_{right}]$ encloses `CURSORX`. Hit testing takes microseconds and requires no point-in-polygon math.
  2. **Unified Collision Model (`RUN.S:1570, 1668`):**
     During physics simulation, the ball probes `PBDX` at `CHECKVERT` and `CHECKHORIZ`. If the ball enters a span, collision is detected instantly, and the stored slope codes immediately yield reflection angles.

---

### 3.5 The Fat-Bits Magnifier Engine (`EDIT.S`)

PCS features a full-screen pixel editing magnifying glass ("Fat Bits"), allowing players to edit graphics at a pixel level.

```
 Real Screen (16x14 px)            Magnifier Viewport (96x84 px)
┌──────────────────────┐          ┌───────────────────────────────┐
│                      │  BLOWUP  │  ██████  ░░░░░░  ██████       │
│      [16x14 px]      │ ───────► │  ██████  ░░░░░░  ██████  x 6  │
│                      │          │  (Unrolled STA $FFFF,X loops) │
└──────────────────────┘          └───────────────────────────────┘
           ▲                                      │
           │               HPLOT                  │
           └──────────────────────────────────────┘
                  (Synchronized pixel edits)
```

#### `BLOWUP` (`EDIT.S:2164–2182`)
* **Purpose:** Takes a 16 × 14 pixel rectangle on the playfield (centered at `VRXD7, VRXM7, VRY`) and blows it up into a magnified 96 × 84 pixel viewport displayed on the editor panel ($Y = 71..168$).
* **Structure:**
  Loops across the 14 rows (`VERTA`). Each source row is magnified into 6 vertical screen lines (`VERTB` steps by 7, leaving 1 line for an optional grid line).

#### `DOROWBW` and `UNWND1` (`EDIT.S:2194–2274`) — *Unwound Self-Modifying Rasterizer*
* **The Problem:** Each pixel must be rendered as a 6-pixel wide by 6-pixel high block. Drawing $16 \times 6 = 96$ pixels across 6 interleaved Apple II scanlines via standard loops would take thousands of cycles.
* **Budge’s Solution:**
  1. Computes the base screen address for all 6 target scanlines:
     ```assembly
     DOROWBW LDA LO,Y
             STA UNWND1,X     ; Self-modify destination address operand
             LDA HI,Y
             STA UNWND1+1,X
             INY
             INX; INX; INX
             CPX #18
             BCC DOROWBW
     ```
  2. Unwinds the write instruction across all 6 scanlines simultaneously:
     ```assembly
     UNWND1 EQU *+1
     ZAPBW  STA $FFFF,X      ; Line 0
            STA $FFFF,X      ; Line 1
            STA $FFFF,X      ; Line 2
            STA $FFFF,X      ; Line 3
            STA $FFFF,X      ; Line 4
            STA $FFFF,X      ; Line 5
     ```
     Stores to all 6 scanlines consecutively in just $6 \times 5 = 30$ cycles!

#### `DOROWCLR` and `DODOTCLR` (`EDIT.S:2275–2414`)
* **Purpose:** Emulates Apple II NTSC color artifacting in the magnified fat-bits viewer.
* **Algorithm:**
  In Apple II color mode, a single pixel bit does not simply produce white or black; its color depends on:
  1. Even vs. odd column parity (Green vs. Violet).
  2. The state of adjacent bits to the left and right (`ZONE` and `NEXTZONE`).
  3. Bit 7 of the byte (palette select: Orange/Blue shift).
  `DODOTCLR` tracks `ZONE` and `NEXTZONE` across byte boundaries using `ROL` and `LSR`, selecting between color dither bit patterns (`$2A, $55, $AA, $D5`) so that the fat bits display the actual perceived color of the pixel on an NTSC TV.

#### `HPLOT` (`EDIT.S:1794–1867`)
* **Purpose:** Plots a single pixel on the Apple II hi-res screen during magnifier drawing.
* **Optimization:**
  - In monochrome mode (`COLBW` negative): Isolates target bit using `MASK,Y`, XORs or sets the bit in screen memory.
  - In color mode (`COLBW` positive): Modifies both the target bit and adjacent artifact bits using `CLRMASK` ($8300, 8C00, B000, C081, \dots$) to prevent color fringing from bleeding across neighboring pixels.

---

### 3.6 Real-Time Physics Animation & Delta Blitting (`RUN.S`, `RUN2.S`)

The physics simulation runs at ~300 ticks per second. Redrawing sprites in their entirety would overwhelm the CPU.

```
       Ball moves Down by 1 pixel:
       
       Previous 5x5:             New 5x5:
         . XXX .                   . ... .
         XXXXXXX                   . XXX .
         XXXXXXX       ──────►     XXXXXXX
         XXXXXXX                   XXXXXXX
         . XXX .                   XXXXXXX
         . ... .                   . XXX .
         
               XOR Difference (VBALL):
                   . XXX .  <-- Top edge erased
                   X ... X  <-- Mid boundary
                   . ... .
                   . ... .
                   X ... X  <-- Mid boundary
                   . XXX .  <-- Bottom edge drawn
       (Only top & bottom scanlines touched!)
```

#### `BALLDOWN`, `BALLUP`, `BALLRIGHT`, `BALLLEFT` (`RUN.S:1846–1904`) — *The XOR Delta Blitter*
* **The Discovery:** The ball is a 5 × 5 circular disc (`IBALL`, `RUN.S:624`):
  ```
  . X X X .   ($0E)
  X X X X X   ($1F)
  X X X X X   ($1F)
  X X X X X   ($1F)
  . X X X .   ($0E)
  ```
* **The Optimization:** When the ball advances by 1 pixel during a physics tick:
  $$\text{New Image} \oplus \text{Old Image} = \text{Delta Mask}$$
  Because $A \oplus B \oplus A = B$, XORing the delta mask over the old position transforms it into the new position in a single pass without clearing or redrawing the interior!

* **Vertical Delta Mask (`VBALL`, `RUN.S:1901–1904`):**
  When moving down by 1 row, scanlines 1, 2, and 3 of the old ball overlap scanlines 0, 1, and 2 of the new ball. The interior pixels cancel out completely! The difference consists exclusively of:
  ```assembly
  VBALL DA *+7
        HEX 00,00,00,06,01 ; Y, Xdiv7, Xmod7, Height=6, Width=1
        HEX 0E, 11, 00, 00, 11, 0E
  ```
  - Row 0 (`$0E`): Erases the top arc of the old ball.
  - Rows 1 & 4 (`$11`): Updates the two corner pixels.
  - Rows 2 & 3 (`$00`): **Untouched!** Zero screen writes.
  - Row 5 (`$0E`): Draws the bottom arc of the new ball.
  `BALLDOWN` blits `VBALL`, increments $Y$, and returns. A 5-line redraw is reduced to touching only the outer boundary bytes!

* **Horizontal Delta Mask (`HBALL`, `RUN.S:1897–1900`):**
  ```assembly
  HBALL DA *+7
        HEX 00,00,00,05,01 ; Height=5, Width=1
        HEX 12, 21, 21, 21, 12
  ```
  XORs only the entering and leaving vertical pixel columns!

#### `ADVANCE` and `RETREAT` (`RUN.S:1274–1310`)
* **Purpose:** Multi-frame sprite animation engine for bumpers, knockers, spinners, and flippers.
* **Mechanism:**
  - Each library object maintains its state in a tail record $L$.
  - $L[0..1]$: Base address of current frame bitmap.
  - $L[7]$: Byte stride of one frame ($\text{Height} \times \text{Width}$).
  - $L[8]$: Current frame index.
  - `ADVANCE`: Adds $L[7]$ to $L[0..1]$, increments $L[8]$, and calls `XOFFDRAW` to draw the next frame.
  - `RETREAT`: Calls `XOFFDRAW` to erase the current frame, subtracts $L[7]$ from $L[0..1]$, and decrements $L[8]$.

---

### 3.7 Typography and Text Rendering (`CDRAW.S`, `RUN2.S`)

#### `PRCHAR` and `PRINT` (`CDRAW.S:865–906`)
* **Mini-Font Design:** 36 proportional glyphs (A–Z, 0–9, space), 7 scanlines high, packed 1 byte wide (`FONT`, `CDRAW.S:910–946`).
* **Multiplication by 7 Optimization (`CDRAW.S:868–872`):**
  To find the byte offset of character $A$ in `FONT` ($A \times 7$), Budge avoids multiplication tables:
  ```assembly
  STA TEMP      ; TEMP = A
  ASL           ; 2 * A
  ASL           ; 4 * A
  ASL           ; 8 * A
  SEC
  SBC TEMP      ; 8 * A - A = 7 * A! (Only 10 cycles!)
  ```
* **Proportional Kerning:**
  Reads character width from `CWIDTH` table ($4..7$ pixels wide).
  Advances horizontal position:
  $$\text{CHARBITS+4} = \text{CHARBITS+4} + \text{CWIDTH}[A]$$
  If $\text{CHARBITS+4} \ge 7$, it subtracts 7 and increments byte column $\text{CHARBITS+3}$.
* **Rendering:** Passes the character glyph descriptor to `XOFFDRAW`, rendering proportional text at arbitrary pixel boundaries with full XOR compositing.

---

### 3.8 Manhattan Wire Routing (`WIRE.S`)

#### `DRAWWIRE` (`WIRE.S:779–853`)
* **Purpose:** Automatically routes and renders schematic wires connecting pinball bumpers/targets to logic AND-gates.
* **Algorithm:**
  Given a source object index and target gate terminal:
  1. Calls `GETBOUNDS` to find the source object's rightmost edge $(X_1, Y_1)$.
  2. Target terminal is at $(X_2, Y_2)$ (where $X_2 = 160$, the divider wall).
  3. Computes orthogonal midpoint: $\text{MIDX} = (X_1 + X_2) / 2$.
  4. Generates three discrete segments:
     - **Segment 1 (Horizontal):** From $(X_1, Y_1)$ to $(\text{MIDX}, Y_1)$ via `HLINE`.
     - **Segment 2 (Horizontal):** From $(\text{MIDX}, Y_2)$ to $(X_2, Y_2)$ via `HLINE`.
     - **Segment 3 (Vertical):** At column $\text{MIDX}$, from $\min(Y_1, Y_2) + 1$ to $\max(Y_1, Y_2) - 1$ via `VLINE`.
* **Optimization:** Rendered entirely via XOR pen mode. Drawing a wire connects it; drawing it a second time cleanly cuts/erases it without damaging background playfield geometry.

---

## 4. Architectural Comparison: Apple II (6502) vs. arm6309 (Hitachi 6309 + video3)

| Architectural Dimension | Apple II (PCS Original) | arm6309 Homebrew PC |
|---|---|---|
| **CPU** | MOS 6502 @ 1.0227 MHz | Hitachi HD63C09E @ 2.0979 MHz (Native Mode) |
| **Registers** | A, X, Y (8-bit); 256-byte stack | A, B, E, F (8-bit); D, W, X, Y, U, S, V (16-bit); Q (32-bit) |
| **Arithmetic** | 8-bit only; software 16-bit multi-step; no hardware mul/div | 16-bit add/sub/cmp; hardware `MULD` (16×16→32) & `DIVQ` (32÷16→16) |
| **Block Transfers** | Software loops (`LDA (zp),Y / STA (zp),Y; DEY; BPL`) | Hardware `TFM` (Transfer Memory): `TFM r1+, r2+` @ 3 cycles/byte |
| **Framebuffer** | 280 × 192, 1bpp (7 px/byte), interleaved scanlines | 640 × 480, 8bpp chunky (1 byte = 1 pixel), linear address space |
| **Color Model** | NTSC phase artifact dither (Green/Violet/Orange/Blue) | 256-color hardware palette LUT (RGB) |
| **Read-Modify-Write** | Native CPU bus access: `EOR (zp),Y / STA (zp),Y` | **No hardware VRAM RMW**: Span writes write solid `WFG`; copies overwrite |
| **VRAM Access** | Directly mapped in CPU address space ($2000–$3FFF) | Windowed or streamed via auto-incrementing registers (`WPTR`, `WADV`, `VDATA`) |
| **Hardware Blitter** | None (CPU bit-shift loops with `SHFRSLT`/`SHFOUT`) | Hardware Copy Engine (Rectangular copy, transparency keying) |
| **Sprite Hardware** | None (Software XOR blitting) | 1 Hardware Sprite (16 × 16, used for mouse cursor) |
| **Off-screen Memory** | Page 2 ($4000) or high RAM | 196 KB VRAM margin (columns 640–1023, rows 0–511) |

---

## 5. Design Blueprints for the 6309 Homebrew PC

Based on the analysis of Budge's routines, this section provides concrete blueprints for implementing an optimized 2D graphics library on the 6309 homebrew PC.

```
       Budge Apple II Paradigm                      6309 / video3 Paradigm
┌─────────────────────────────────────┐      ┌─────────────────────────────────────┐
│ 1bpp Interleaved Framebuffer        │      │ 640x480 Chunky 8bpp Framebuffer     │
│ Software Bit-Shift Tables (SHFRSLT) │ ───► │ Byte = Pixel (No shifting needed!)  │
│ XOR Compositing Over Screen         │      │ Off-screen Margin Damage Bands      │
│ CPU Span Loop (21 cycles/byte)      │      │ Hardware Blitter / WADV Streaming   │
└─────────────────────────────────────┘      └─────────────────────────────────────┘
```

### Blueprint 1: Chunky Span Filler (Replacing `DOBAR` & `HLINE`)
* **Apple II Lesson:** `DOBAR` had to unpack bit boundaries and XOR against repeating color bar patterns.
* **6309 Implementation:** In chunky 8bpp, 1 pixel is 1 byte. A span is simply a contiguous range of byte addresses.
* **Optimization:** Using the 6309's auto-incrementing video address register (`WADV = 00`, auto-advance horizontal column):
```assembly
; Fill span from X1 to X2 on row Y with Color in Register A
; Inputs: D = X1, Y = Y (row), X = Width (X2 - X1)
FillSpan:
        ; Calculate VRAM address: Addr = (Y << 10) + X1
        TFR   Y,D             ; D = Y
        LSLD                  ; D = Y * 2
        LSLD                  ; D = Y * 4 ... (Shift left 10 for 1024-byte row pitch)
        ; ... set WPTR ...
        LDA   #FILL_COLOR     ; Load color
FillLoop:
        STA   VDATA           ; Write pixel, auto-advances column!
        LEAX  -1,X            ; Decrement count
        BNE   FillLoop
        RTS
```
* **Even Faster (Hardware Block Fill):** Configure `video3`'s copy engine with source fixed at a single color register, or use `TFM` block write if VRAM is memory mapped.

---

### Blueprint 2: 1bpp Masked Art Blitter (Translating `XOFFDRAW` & `DRAWBITS`)
* **Apple II Lesson:** Budge stored part artwork as 1bpp monochrome bitmaps and used `SHFRSLT`/`SHFOUT` to shift them to arbitrary horizontal pixels.
* **6309 Implementation:** The 1bpp bitmap format can be **preserved verbatim** (saving huge amounts of ROM/RAM compared to storing 8bpp sprites), but expanded in hardware!
* **Hardware Feature:** `video3` provides `WM.Mask` and `WM.Sprite` modes:
  - `WM.Mask`: Takes a CPU-written byte as an 8-pixel bitmap, expanding 1-bits to `WFG` (foreground color) and 0-bits to `WBG` (background color).
  - `WM.Sprite`: Writes `WFG` for 1-bits and **writes nothing** for 0-bits (hardware transparency!).
* **Inner Loop:**
```assembly
; Blit 1bpp sprite with transparency in any palette color
; X = Sprite Data Pointer, Y = Row Count, B = Width in Bytes
Blit1bpp:
        STB   WADV            ; Advance down rows (WADV = 01)
BlitRow:
        LDA   ,X+             ; Fetch 1bpp bitmap byte (8 pixels)
        STA   VDATA           ; Hardware expands 8 pixels in parallel!
        DECB
        BNE   BlitRow
        ; ... step to next scanline ...
```
**Performance Gain:** The 6309 renders 8 fully colored, transparent pixels in just 10 CPU cycles (1.25 cycles/pixel), outperforming the 6502's 28 cycles for 7 pixels by a factor of 18!

---

### Blueprint 3: Native 6309 Fixed-Point Scan Converter (Translating `SCANPLY`)
* **Apple II Lesson:** Fractional slope stepping with midpoint rounding prevents visual aliasing.
* **6309 Implementation:** Utilize the 6309's 16-bit registers (`D`, `W`, `X`, `Y`) and native 32/16-bit division (`DIVQ`):
```assembly
; 6309 Active Edge Stepping
; Register W = Fractional Accumulator (16-bit)
; Register D = Fractional Delta (16-bit)
; Register X = Integer X coordinate (16-bit)
; Register Y = Integer Delta (16-bit)
StepEdge:
        ADDR  D,W             ; Add 16-bit fraction (W += D)
        ADCR  Y,X             ; Add integer slope + Carry from fraction!
        ; Midpoint Rounding:
        ; Simply test bit 15 of W: if set, X + 1 represents nearest pixel center
```
With 16-bit math and register pairing (`Q = D:W`), the entire active edge list traversal fits in CPU registers, eliminating zero-page thrashing.

---

### Blueprint 4: Off-Screen Margin Composition (Replacing XOR Compositing)
* **The Constraint:** The `video3` card does not support read-modify-write XOR operations.
* **Budge’s Structural Insight:** In PCS, the span database is already a retained display list.
* **The 6309 Architecture:**
  1. The `video3` card provides **196 KB of off-screen VRAM** in the right margin (columns 640–1023, rows 0–511).
  2. Maintain a **Damage Bounding Box** tracking rows modified by moving objects or edits.
  3. Recompose damaged rows off-screen in the margin:
     - Clear the off-screen band.
     - Walk the `PBDX` span database for the damaged rows, emitting solid spans.
     - Blit the 1bpp sprite artwork over the spans.
  4. Trigger the hardware copy engine to blit the clean off-screen band onto the visible screen in a single rectangular burst during VBLANK.
* **Result:** Eliminates flicker, supports 256 colors, and bypasses the lack of hardware XOR.

---

### Blueprint 5: Manhattan Wire Router for Schematic UIs
* **Apple II Lesson:** Budge's 3-segment orthogonal routing algorithm in `WIRE.S` provides clean, non-overlapping connections between arbitrary components with zero search overhead.
* **Implementation Blueprint:**
  1. Define connection endpoints $(X_1, Y_1)$ and $(X_2, Y_2)$.
  2. Calculate split column: $X_{mid} = (X_1 + X_2) / 2$.
  3. Draw horizontal segment 1: $(X_1, Y_1) \to (X_{mid}, Y_1)$.
  4. Draw horizontal segment 2: $(X_{mid}, Y_2) \to (X_2, Y_2)$.
  5. Draw vertical trunk: $(X_{mid}, \min(Y_1, Y_2)) \to (X_{mid}, \max(Y_1, Y_2))$.
  6. In a modern UI, store wire segments as records in a display list so they can be deleted, recolored, or rerouted without XOR artifacts.

---

## 6. Summary of Core Principles for 8-Bit / 16-Bit Engine Design

Bill Budge's *Pinball Construction Set* establishes seven immutable laws of high-performance retro graphics:

1. **Precompute Everything:** Eliminate division, modulo, and bit-shifting from the runtime path. Replace them with lookup tables (`DIV7`, `MOD7`, `SHFRSLT`, `SHFOUT`, `LO`, `HI`).
2. **Eliminate Branching via Self-Modifying Code:** Dynamic patching of jump targets (`SETMODE`, `UNWND1`) saves dozens of cycles per scanline compared to runtime condition checking.
3. **Unwind Repetitive Write Loops:** When writing fixed blocks (like fat-bits in `BLOWUP`), unroll writes across scanlines to saturate the memory bus.
4. **Treat Geometry as a Dual Structure:** The Active Edge List scan converter should produce both screen pixels and a retained spatial index (`PBDX`). Geometry should be rendered once and queried everywhere (drawing, hit testing, physics).
5. **Animate by Delta Whenever Possible:** Moving an object by one pixel does not require redrawing the object; only the leading and trailing edges change. XORing delta masks (`VBALL`, `HBALL`) preserves bandwidth.
6. **Normalize Geometry Topologically:** Pre-orienting polygon edges (`ALIGNPOLY`) and detecting extrema (`PROCESSPOLY`) simplifies edge stepping and eliminates runtime edge crossing anomalies.
7. **Scale the Renderer, Never the World:** Keep internal simulation coordinates, physics math, and database units in compact, integer units. Perform scaling and screen transformation strictly at the final rasterization stage.
