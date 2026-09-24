"""Read demo_tb.sv's frames.bin - or the emulator's, which writes the same.

Each record: 'F', u32 frame number, u64 simulated time in ps, u16 width,
u16 height, u16 camera record, u16 hero record, u16 missed blanks, u8 progress,
u8 VMODE, u8 repeat, u16 checkpoint at the first active dot, u16 checkpoint at
the last, u16 raster phase at the first and at the last, u8 LRUN at line 1 -
then the pixels, RGB565 little-endian:
  repeat 0   width * height words
  repeat 1   none: the previous record's picture
  repeat 2   a bitmap of changed rows, ceil(height / 8) bytes with row y at
             bit y & 7 of byte y >> 3, then width words for each changed row
"""
import struct
import numpy as np

HDR = struct.Struct("<cIQHHHHHBBBHHHHB")
LEGACY = struct.Struct("<cIQHHHHHBBB")     # before the checkpoints (2026-09-13)


def read(path, legacy=False):
    """Yield (meta dict, pixels as uint16 [h, w]) - a repeat yields the same array."""
    last = None
    hdr = LEGACY if legacy else HDR
    with open(path, "rb") as f:
        while True:
            head = f.read(hdr.size)
            if len(head) < hdr.size:
                return
            if legacy:
                tag, n, t, w, h, camk, herok, missed, prog, vmode, rep = hdr.unpack(head)
                ck0 = ck1 = ph0 = ph1 = lrun = 0
            else:
                tag, n, t, w, h, camk, herok, missed, prog, vmode, rep, ck0, ck1, ph0, ph1, lrun = hdr.unpack(head)
            if tag != b"F":
                raise ValueError(f"frames.bin out of step at frame {n}")
            if rep == 0:
                raw = f.read(w * h * 2)
                if len(raw) < w * h * 2:
                    return                      # a run cut short mid-frame
                last = np.frombuffer(raw, dtype="<u2").reshape(h, w).copy()
            elif rep == 2:
                bm = f.read((h + 7) // 8)
                if len(bm) < (h + 7) // 8:
                    return
                last = last.copy()
                for y in range(h):
                    if bm[y >> 3] & (1 << (y & 7)):
                        raw = f.read(w * 2)
                        if len(raw) < w * 2:
                            return
                        last[y] = np.frombuffer(raw, dtype="<u2")
            yield dict(n=n, t=t / 1e12, w=w, h=h, camk=camk, herok=herok, missed=missed,
                       prog=prog, vmode=vmode, repeat=rep == 1, ck=(ck0, ck1), ph=(ph0, ph1),
                       lrun=lrun), last


def rgb565_to_rgb8(px):
    px = px.astype(np.uint32)
    r5, g6, b5 = px >> 11, (px >> 5) & 63, px & 31
    return np.stack([(r5 << 3) | (r5 >> 2), (g6 << 2) | (g6 >> 4), (b5 << 3) | (b5 >> 2)], -1).astype(np.uint8)


def palette565():
    """demo.asm's game palette: entry i = RGB332(i) as RGB565 - the same tables."""
    r5 = [0, 4, 9, 13, 18, 22, 27, 31]
    g6 = [0, 9, 18, 27, 36, 45, 54, 63]
    b5 = [0, 10, 21, 31]
    return np.array([(r5[i >> 5] << 11) | (g6[(i >> 2) & 7] << 5) | b5[i & 3] for i in range(256)], dtype=np.uint16)
