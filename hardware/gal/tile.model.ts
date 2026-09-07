/* The tile and character address, as arithmetic - graphics.md 6.4.1.
 *
 * A tile lookup is base + code x size + row, and with an aligned tile set
 * every term lands on its own address bits, so THERE IS NO ADDER. That is the
 * whole reason 6.4 is affordable, and it is the property this file exists to
 * check rather than assume: three modes, three different concatenations, one
 * 19-bit result.
 *
 *   linear     A18..A10  scan row        A9..A0   scan column
 *   tile   (A) A18..A14  TILEBASE        A13..A6  code   A5..A3 row  A2..A0 col
 *   char   (B) A18..A11  FONTBASE        A10..A3  code   A2..A0 row
 *
 * A1..A0 never leave the logic - they are the 4-way interleave phase (2.1),
 * so the framebuffer sees A18..A2 and the '153 mux picks the byte. In tile
 * mode that means A2 selects which group of four pixels within the 8-pixel
 * cell row, which falls out of the concatenation rather than being arranged.
 */

export const enum Mode { Linear = 0, Tile = 1, Char = 2 }

export interface LinearIn { scanRow: number; scanCol: number }
export interface TileIn { tilebase: number; code: number; cellRow: number; cellCol: number }
export interface CharIn { fontbase: number; code: number; cellRow: number }

const field = (value: number, width: number, shift: number) =>
  (value & ((1 << width) - 1)) << shift

/** 8bpp tiles, 8x8 = 64 B each, 256 tiles = 16 KB aligned to 16 KB. */
export const tileAddress = (i: TileIn) =>
  field(i.tilebase, 5, 14) | field(i.code, 8, 6) | field(i.cellRow, 3, 3) | field(i.cellCol, 3, 0)

/** 1bpp glyphs, 8 B each, 256 glyphs = 2 KB aligned to 2 KB. */
export const charAddress = (i: CharIn) =>
  field(i.fontbase, 8, 11) | field(i.code, 8, 3) | field(i.cellRow, 3, 0)

/** The bitmap scan address, section 8's torus. */
export const linearAddress = (i: LinearIn) => field(i.scanRow, 9, 10) | field(i.scanCol, 10, 0)

/** What the four framebuffer chips see: the scan address less its bottom two
 *  bits, which are the interleave phase. */
export const chipAddress = (a: number) => a >>> 2

/* ------------------------------------------------------------------------
 * The map fetch, which 6.4 does not specify and which is not free by default.
 *
 * 6.4.2 gives "Screen memory 2,000 B" for an 80x25 map. 2,000 is 80 x 25 and
 * 80 IS NOT A POWER OF TWO, so a packed map costs
 *
 *     mapAddr = MAPBASE + cellRow * 80 + cellCol
 *
 * which is a multiply-accumulate, or at best an adder - and 6.4.1's entire
 * argument is "there is no adder". A 128-byte row stride restores the
 * concatenation for 1,200 bytes of the 512 KB nobody is using.
 * ---------------------------------------------------------------------- */

export const MAP_STRIDE = 128
export const MAP_ROWS = 25
export const MAP_COLS = 80

/** Concatenated: MAPBASE in A18..A12, cell row in A11..A7, cell column in
 *  A6..A0. Free, and 3,200 B rather than 2,000. */
export const mapAddress = (mapbase: number, cellRow: number, cellCol: number) =>
  field(mapbase, 7, 12) | field(cellRow, 5, 7) | field(cellCol, 7, 0)

/** What 6.4.2's "2,000 B" implies, for comparison - and it needs an adder. */
export const packedMapAddress = (mapbase: number, cellRow: number, cellCol: number) =>
  mapbase * 2048 + cellRow * MAP_COLS + cellCol
