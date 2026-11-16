#!/usr/bin/env python3
"""Targeted regressions for the v0.19 backports. Requires Python 3.10+ and clang.

Run with .venv/bin/python tools/test_toolkit_v019.py. No game files are needed.
Fixtures compile the actual toolkit sources and check cache invalidation,
collisions, DMA transfers and math equivalence, rather than timing thresholds.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TK = ROOT / "ps3recomp"
sys.path.insert(0, str(TK / "tools"))


def main():
    if sys.version_info < (3, 10):
        raise SystemExit("Python 3.10+ required; use .venv/bin/python")
    from check_ppu_scaffold import stub_header
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("PPU_", "PS3_", "PS3RECOMP_", "SPU_", "SPURS_", "YDKJ_", "LBP_"))}
    with tempfile.TemporaryDirectory(prefix="r3-v019-tests-") as tmp:
        tmp = Path(tmp)
        (tmp / "ppu_recomp.h").write_text(stub_header())
        inc = ["-I" + str(p) for p in (tmp, TK / "include", TK / "runtime/ppu",
                                      TK / "runtime/spu", TK / "runtime/platform")]
        strip = ["-Wl,-dead_strip"] if sys.platform == "darwin" else ["-Wl,--gc-sections", "-ldl"]

        def fixture(name, sources, cxx=False, flags=()):
            binary = tmp / name
            cc = os.environ.get("CXX" if cxx else "CC", "c++" if cxx else "cc")
            subprocess.run([cc, "-std=c++17" if cxx else "-std=gnu17", "-O2", "-UNDEBUG", "-w",
                            "-ffunction-sections", "-fdata-sections", "-pthread", *inc,
                            *map(str, sources), *flags, "-lm", "-o", str(binary)], check=True)
            subprocess.run([str(binary)], env=env, check=True, timeout=60)

        fixture("test_vmx_converts", [TK / "runtime/ppu/tests/test_vmx_converts.c"])
        for name in ("test_ppu_lookup_cache", "test_hle_lookup_cache"):
            fixture(name, [TK / f"runtime/ppu/tests/{name}.cpp"], cxx=True, flags=strip)
        fixture("test_gcm_pump_idle", [TK / "libs/video/tests/test_gcm_pump_idle.c"], flags=strip)
        fixture("test_spu_fi_cflts_neon", [TK / "runtime/spu/tests/test_spu_fi_cflts_neon.c"])
        fixture("test_spu_fi_scalar", [TK / "runtime/spu/tests/test_spu_fi_cflts_neon.c"], flags=["-DSPU_SCALAR_HELPERS"])
        common = ["spu_drain.c", "spu_lockstep.c", "spu_coherency.c", "spu_workload.c",
                  "spurs_policy.c", "spurs_job.c", "spu_tsp_weak.c", "spu_vm_pagemap.c",
                  "spurs_policy_blob_weak.c", "spu_interp.c"]
        fixture("test_spu_mfc_params", [TK / "runtime/spu/tests/test_spu_mfc_params.c",
                *[TK / "runtime/spu" / f for f in common], TK / "runtime/platform/win32_compat.c"], flags=strip)
        subprocess.run([sys.executable, str(TK / "tools/test_gcm_io_mappings.py")], check=True, env=env)
    print("PASS: all v0.19 backport regressions")


if __name__ == "__main__":
    main()
