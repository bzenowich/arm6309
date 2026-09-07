#!/usr/bin/env python3
"""Derive the ATF1508AS macrocell-to-pin maps from Atmel's own BSDL files.

prjbureau's device descriptions need, for each package, the pin number of every
macrocell M1..M128 - with 0 for the macrocells that have no pin, because the
ATF1508AS has 128 macrocells in packages that cannot expose them all. That list
is not in the datasheet: reference/datasheets/ATF1508AS.pdf draws the pinouts
but labels them "I/O", never "MC57".

It IS in the boundary-scan files, which prjbureau already vendors in bsdl/.
Atmel's own comments carry the mapping a cell at a time:

    --Input, pin81 MC128
    "2    (BC_4,IO81,input,X),"&

so this reads them back out rather than anybody transcribing 128 numbers twice.

The result cross-checks against the distributor figures without being told them:
PLCC-84 comes out at 60 pinned macrocells and TQFP-100 at 76, and both packages
put JTAG on MC32/MC48/MC96/MC112 - 60 + 4 = 64 I/O and 76 + 4 = 80, which is
what Microchip and the distributors quote for those two packages.

    python3 extract_pins.py path/to/prjbureau/bsdl
"""

import json
import re
import sys
from pathlib import Path

PACKAGES = {"J84": "PLCC84", "A100": "TQFP100", "Q100": "PQFP100", "Q160": "PQFP160"}


def parse(text):
    """(macrocell -> pin, jtag function -> macrocell, dedicated input -> pin)"""
    macrocells = {
        int(m.group(2)): int(m.group(1))
        for m in re.finditer(r"pin\s*(\d+)\s+MC(\d+)", text)
    }
    jtag = {
        m.group(2): int(m.group(1))
        for m in re.finditer(r"--Internal,\s*MC(\d+)\s+(TDI|TMS|TCK|TDO)", text)
    }
    dedicated = {
        m.group(1): int(m.group(2))
        for m in re.finditer(
            r"--\s*Input,\s*(GCLK\d|GOE\d|GCLR)\s*\n\s*\"\d+\s*\(BC_4,IN(\d+)", text)
    }
    return macrocells, jtag, dedicated


def main(bsdl_dir):
    result = {}
    for suffix, name in PACKAGES.items():
        path = Path(bsdl_dir) / f"1508AS_{suffix}.BSD"
        if not path.exists():
            print(f"{name:8} - no {path.name}", file=sys.stderr)
            continue
        macrocells, jtag, dedicated = parse(path.read_text())
        if not macrocells:
            # Q100 and Q160 use a different comment style and carry no
            # "pin<n> MC<m>" pairs at all. Recorded rather than guessed.
            print(f"{name:8} - BSDL has no macrocell comments; needs another source",
                  file=sys.stderr)
            continue
        result[name] = {
            "macrocell_pin": {str(k): v for k, v in sorted(macrocells.items())},
            "jtag_macrocell": jtag,
            "dedicated_input_pin": dedicated,
        }
        per_block = [
            sum(1 for i in range(b * 16 + 1, b * 16 + 17) if i in macrocells)
            for b in range(8)
        ]
        print(f"{name:8} {len(macrocells):3} pinned macrocells + {len(jtag)} JTAG "
              f"= {len(macrocells) + len(jtag):3} I/O; per block {per_block}",
              file=sys.stderr)
    json.dump(result, sys.stdout, indent=1)
    print()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "bsdl")
