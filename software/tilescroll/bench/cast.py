"""cast.py - the hero and the creatures, as art: `tilescroll`'s actors.

The sprites were drawn for `zelda` (software/archive/zelda/bench/mkzelda.py)
and `tilescroll` put the same cast in its world.  When `zelda` was archived on
2026-09-24 the art came here, verbatim, so that a live program does not import
an archived one; mktilescroll.py reads HERO, CAST and c332 from this file.
"""
import numpy as np

KEY = 0x00                    # the copy engine's transparent byte: never drawn
ZNHERO = 8                    # hero slots: down, up, left, right x 2


def c332(r, g, b):
    """RGB332, the byte the card's LUT is loaded with for this game.

    ⛔ NEVER 0, because 0 is the copy engine's transparent key: a drawn colour
    that quantises to it would be a HOLE in the shape.  1 is the next index
    up - (0, 0, 85), which is as near black as this palette gets."""
    v = ((r >> 5) << 5) | ((g >> 5) << 2) | (b >> 6)
    return v if v else 1




HPAL = {
    "K": (20, 16, 16),        # outline
    "H": (26, 92, 40),        # cap, shadow side
    "h": (58, 158, 66),       # cap
    "G": (30, 110, 44),       # tunic, shadow
    "g": (72, 176, 78),       # tunic
    "S": (246, 206, 160),     # skin
    "s": (206, 158, 116),     # skin, shadow
    "E": (28, 24, 40),        # eye
    "B": (130, 76, 38),       # boot
    "b": (170, 108, 56),      # boot, lit
    "W": (226, 230, 240),     # shield rim
    "w": (72, 104, 210),      # shield face
    "Y": (240, 214, 96),      # belt / hair
}

HERO = {
 "down1": [
   "....KKKKKKKK....",
   "...KhhhhhhhhK...",
   "..KhhhHHHHhhhK..",
   "..KhSSSSSSSShK..",
   "..KSSSSSSSSSSK..",
   "..KSEESSSSEESK..",
   "..KSSSSSSSSSSK..",
   "...KSSsssSSK....",
   "..KKGGGGGGGGKK..",
   ".KWwGggggggGGK..",
   ".KWWwGgYYYgGKSK.",
   ".KWWwGGYYYGGKSK.",
   "..KWwGGGGGGGK.K.",
   "...KGGGGGGGGK...",
   "...KBbKKKKbBK...",
   "...KKK....KKK...",
 ],
 "down2": [
   "....KKKKKKKK....",
   "...KhhhhhhhhK...",
   "..KhhhHHHHhhhK..",
   "..KhSSSSSSSShK..",
   "..KSSSSSSSSSSK..",
   "..KSEESSSSEESK..",
   "..KSSSSSSSSSSK..",
   "...KSSsssSSK....",
   ".KKGGGGGGGGKK...",
   "KWwGggggggGGK...",
   "KWWwGgYYYgGKSK..",
   "KWWwGGYYYGGKSK..",
   ".KWwGGGGGGGK.K..",
   "..KGGGGGGGGK....",
   "..KbBKKKKBbK....",
   "..KKK....KKK....",
 ],
 "up1": [
   "....KKKKKKKK....",
   "...KhhhhhhhhK...",
   "..KhhhhhhhhhhK..",
   "..KhhhhhhhhhhK..",
   "..KhhhhhhhhhhK..",
   "..KhHHhhhhHHhK..",
   "..KhhhhhhhhhhK..",
   "...KhhhhhhhK....",
   "..KKGGGGGGGGKK..",
   "..KSGggggggGWK..",
   ".KSKGgYYYgGWWWK.",
   ".KSKGGYYYGGWWWK.",
   "..K.KGGGGGGGWK..",
   "...KGGGGGGGGK...",
   "...KBbKKKKbBK...",
   "...KKK....KKK...",
 ],
 "up2": [
   "....KKKKKKKK....",
   "...KhhhhhhhhK...",
   "..KhhhhhhhhhhK..",
   "..KhhhhhhhhhhK..",
   "..KhhhhhhhhhhK..",
   "..KhHHhhhhHHhK..",
   "..KhhhhhhhhhhK..",
   "...KhhhhhhhK....",
   "...KKGGGGGGGGKK.",
   "...KSGggggggGWK.",
   "..KSKGgYYYgGWWWK",
   "..KSKGGYYYGGWWWK",
   "...K.KGGGGGGGWK.",
   "....KGGGGGGGGK..",
   "....KbBKKKKBbK..",
   "....KKK....KKK..",
 ],
 "left1": [
   "....KKKKKKK.....",
   "...KhhhhhhhK....",
   "..KhhHHhhhhhK...",
   "..KhSSSSSShhK...",
   ".KSSSSSSSSShK...",
   ".KSSESSSSSShK...",
   ".KSSSSSSSSShK...",
   "..KSSsssSSK.....",
   "..KKGGGGGGKK....",
   ".KWwGgggggGGK...",
   "KWWwGgYYYggGKS..",
   "KWWwGGYYYGGGKS..",
   ".KWwGGGGGGGGK...",
   "..KGGGGGGGGK....",
   "..KBbKKKKbBK....",
   "..KKK....KKK....",
 ],
 "left2": [
   "....KKKKKKK.....",
   "...KhhhhhhhK....",
   "..KhhHHhhhhhK...",
   "..KhSSSSSShhK...",
   ".KSSSSSSSSShK...",
   ".KSSESSSSSShK...",
   ".KSSSSSSSSShK...",
   "..KSSsssSSK.....",
   "..KKGGGGGGKK....",
   ".KWwGgggggGGK...",
   "KWWwGgYYYggGKS..",
   "KWWwGGYYYGGGKS..",
   ".KWwGGGGGGGGK...",
   "...KGGGGGGGK....",
   "...KbBKKKKBK....",
   "...KKK...KKK....",
 ],
}
HERO_ORDER = ["down1", "down2", "up1", "up2", "left1", "left2"]   # then two mirrors


def hero_art():
    """The eight frames, as 16 x 16 arrays of RGB332 - RIGHT mirrored from LEFT."""
    lut = {k: c332(*v) for k, v in HPAL.items()}
    out = []
    for name in HERO_ORDER:
        rows = HERO[name]
        assert len(rows) == 16, (name, len(rows))
        a = np.full((16, 16), KEY, np.uint8)
        for r, row in enumerate(rows):
            assert len(row) == 16, (name, r, len(row))
            for c, ch in enumerate(row):
                if ch in lut:
                    a[r, c] = lut[ch]
        out.append(a)
    # ⭐ RIGHT IS LEFT MIRRORED, generated and not drawn: two hand-drawn
    # mirrors are two places for a pixel to be wrong in only one of them.
    out.append(out[4][:, ::-1].copy())
    out.append(out[5][:, ::-1].copy())
    assert len(out) == ZNHERO, len(out)
    return out


# ⭐ THE CAST, DRAWN RATHER THAN CUT OUT.  The first attempt took 2 x 2 blocks
# of the overworld's own cells and knocked their corners off, on the theory
# that a creature made of the terrain belongs to it - ⛔ and they came out as
# eight featureless dark blobs, because most of the map is flat ground.  A
# rendering of the bank is what said so, which is the rule: LOOK at the data
# when the symptom is a wrong answer of the right shape.
#
# ⚠ '.' is the key and every other character is an index into the shape's own
# palette below it.  Sixteen rows of sixteen, asserted on the way in.
CAST = [
 ("octorok", {"1": (200, 40, 40), "2": (250, 120, 60), "3": (30, 20, 20), "4": (250, 250, 250)},
  ["................",
   ".....111111.....",
   "....11111111....",
   "...1122221111...",
   "..112222222111..",
   "..122444442211..",
   "..122433342211..",
   "..122433342211..",
   "..122444442211..",
   "..112222222111..",
   "...1122221111...",
   "...111111111....",
   "..1..1...1..1...",
   ".33..33.33..33..",
   "................",
   "................"]),
 ("octorok2", {"1": (200, 40, 40), "2": (250, 120, 60), "3": (30, 20, 20), "4": (250, 250, 250)},
  ["................",
   ".....111111.....",
   "....11111111....",
   "...1122221111...",
   "..112222222111..",
   "..122444442211..",
   "..122343433211..",
   "..122343433211..",
   "..122444442211..",
   "..112222222111..",
   "...1122221111...",
   "...111111111....",
   "...1.11.11.1....",
   "..33.33.33.33...",
   "................",
   "................"]),
 ("moblin", {"1": (60, 130, 50), "2": (120, 190, 80), "3": (25, 20, 15), "4": (240, 230, 160)},
  ["................",
   "...11......11...",
   "...111....111...",
   "....11111111....",
   "...122222221....",
   "..12233223321...",
   "..12233223321...",
   "..1222222221....",
   "..1224444221....",
   "...12222221.....",
   "...111111111....",
   "..1111111111....",
   "..1.111111.1....",
   "..3..1111..3....",
   ".....3..3.......",
   "................"]),
 ("moblin2", {"1": (60, 130, 50), "2": (120, 190, 80), "3": (25, 20, 15), "4": (240, 230, 160)},
  ["................",
   "...11......11...",
   "...111....111...",
   "....11111111....",
   "...122222221....",
   "..12332233221...",
   "..12332233221...",
   "..1222222221....",
   "..1224444221....",
   "...12222221.....",
   "...111111111....",
   "...1111111111...",
   "...1.111111.1...",
   "....3.1111.3....",
   "......3..3......",
   "................"]),
 ("rupee", {"1": (40, 200, 120), "2": (170, 255, 210), "3": (10, 80, 60)},
  ["................",
   "................",
   ".......11.......",
   "......1221......",
   ".....122221.....",
   "....12222331....",
   "...1222233331...",
   "...1222333331...",
   "...1223333331...",
   "...1233333331...",
   "....133333 1....",
   ".....1333 1.....",
   "......131 ......",
   ".......1 .......",
   "................",
   "................"]),
 ("heart", {"1": (220, 40, 70), "2": (255, 150, 170), "3": (120, 10, 30)},
  ["................",
   "................",
   "...11.....11....",
   "..1221...1221...",
   ".122221.122221..",
   ".122222112222 1.",
   ".1222222222233 .",
   ".1222222222333 .",
   "..12222222333 ..",
   "...122222333 ...",
   "....1222333 ....",
   ".....12333 .....",
   "......13 3......",
   ".......1 .......",
   "................",
   "................"]),
 ("bush", {"1": (30, 110, 40), "2": (70, 180, 70), "3": (110, 70, 35)},
  ["................",
   "................",
   "....11...11.....",
   "...1221.1221....",
   "..122221222 1...",
   "..12222222221...",
   ".1222222222221..",
   ".1222122212221..",
   ".1222222222221..",
   "..12222222221...",
   "...111111111....",
   "......333.......",
   "......333.......",
   "......333.......",
   "................",
   "................"]),
 ("rock", {"1": (120, 120, 120), "2": (180, 180, 180), "3": (60, 60, 60)},
  ["................",
   "................",
   "....111111......",
   "...12222211.....",
   "..1222222211....",
   ".122222222211...",
   ".122222222221...",
   ".122333222221...",
   ".122333222221...",
   ".122222222221...",
   "..1222222221....",
   "...13333331.....",
   "....333333......",
   "................",
   "................",
   "................"]),
]
