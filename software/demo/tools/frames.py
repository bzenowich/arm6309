"""Read demo_tb.sv's frames.bin.

Each record: 'F', u32 frame number, u64 simulated time in ps, u16 width,
u16 height, u16 camera record, u16 hero record, u16 missed blanks, u8 progress,
u8 VMODE, u8 repeat - then width * height RGB565 words, little-endian, unless
repeat is 1, in which case the pixels are the previous record's.
"""
import struct
import numpy as np

HDR = struct.Struct("<cIQHHHHHBBB")


def read(path):
    """Yield (meta dict, pixels as uint16 [h, w]) - a repeat yields the same array."""
    last = None
    with open(path, "rb") as f:
        while True:
            head = f.read(HDR.size)
            if len(head) < HDR.size:
                return
            tag, n, t, w, h, camk, herok, missed, prog, vmode, rep = HDR.unpack(head)
            if tag != b"F":
                raise ValueError(f"frames.bin out of step at frame {n}")
            if not rep:
                raw = f.read(w * h * 2)
                if len(raw) < w * h * 2:
                    return                      # a run cut short mid-frame
                last = np.frombuffer(raw, dtype="<u2").reshape(h, w)
            yield dict(n=n, t=t / 1e12, w=w, h=h, camk=camk, herok=herok, missed=missed,
                       prog=prog, vmode=vmode, repeat=bool(rep)), last


def rgb565_to_rgb8(px):
    px = px.astype(np.uint32)
    r5, g6, b5 = px >> 11, (px >> 5) & 63, px & 31
    return np.stack([(r5 << 3) | (r5 >> 2), (g6 << 2) | (g6 >> 4), (b5 << 3) | (b5 >> 2)], -1).astype(np.uint8)


def palette565():
    """demo.asm's palette: entry i = RGB332(i) as RGB565 - the same tables."""
    r5 = [0, 4, 9, 13, 18, 22, 27, 31]
    g6 = [0, 9, 18, 27, 36, 45, 54, 63]
    b5 = [0, 10, 21, 31]
    return np.array([(r5[i >> 5] << 11) | (g6[(i >> 2) & 7] << 5) | b5[i & 3] for i in range(256)], dtype=np.uint16)
