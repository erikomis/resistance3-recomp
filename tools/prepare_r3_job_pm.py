#!/usr/bin/env python3
"""Extract and lift Resistance 3's Wws_Job SPURS policy module from EBOOT.elf.

BCUS98176 01.00 adds two "Wws_Job" workloads (SharedList0_OS and
SharedList1_OS) whose policy module is raw SPU bytes (not an ELF) at EBOOT VA
0x00EB9E00, 12,544 bytes, as Resistance 2's was. The SPU image scanner
cannot see it, and without it cellSpurs reports "PM NOT LIFTED -- workload
will not run". This cuts it out of your decrypted EBOOT, checks its FNV-1a
fingerprint and lifts it into port/spu/r3_job_pm/ (spu_recomp.c/.h,
image.bin, functions.json, lift.json: translated game code, .gitignore'd).
port/spu/r3_job_pm/register.c registers it under that fingerprint.

  tools/prepare_r3_job_pm.py            # extract and lift
  tools/prepare_r3_job_pm.py --check    # the lifted image matches the EBOOT
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3_layout  # noqa: E402

if __name__ == "__main__":
    r3_layout.pm_main(__doc__, 0x00EB9E00, 12544, 0xEA3A104FE30430AA, "job_pm")
