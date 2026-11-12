#!/usr/bin/env python3
"""Extract and lift Resistance 3's "igPm" SPURS policy module from EBOOT.elf.

BCUS98176 01.00 creates a second SPURS instance ("ig", 5 SPUs) and adds an
"igPm" / "igPmWorkload" workload whose policy module is raw SPU bytes at
EBOOT VA 0x00E28F80, 560 bytes: Insomniac's own scheduler, new since
Resistance 2. Without a lift cellSpurs reports "PM NOT LIFTED -- workload
will not run". This cuts it out of your decrypted EBOOT, checks its FNV-1a
fingerprint and lifts it into port/spu/r3_ig_pm/ (translated game code,
.gitignore'd). port/spu/r3_ig_pm/register.c registers it under that
fingerprint.

  tools/prepare_r3_ig_pm.py             # extract and lift
  tools/prepare_r3_ig_pm.py --check     # the lifted image matches the EBOOT
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3_layout  # noqa: E402

if __name__ == "__main__":
    r3_layout.pm_main(__doc__, 0x00E28F80, 560, 0xCA191E29E59B1967, "ig_pm")
