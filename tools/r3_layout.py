"""Where things live, for the Python tools in this folder.

Two layouts are understood:

  this repository  <repo>/port/ (the port), <repo>/ps3recomp/ (the toolkit,
                   tools/setup_toolkit.sh), <repo>/game/<title>/EBOOT.elf
  a toolkit tree   the port in <toolkit>/project/, the EBOOT in
                   <toolkit>/game/EBOOT.elf, these tools in <toolkit>/tools/
                   (how the port was first developed)

Environment overrides: PS3RECOMP_DIR (the toolkit), R3_EBOOT (the decrypted
EBOOT.elf), RES_TITLE_ID (default BCUS98176, Resistance 3 USA; BCES01118 is
the European disc).

From the Resistance 2 port (tools/r2_layout.py).
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IN_REPO = (ROOT / "port").is_dir()
PORT = ROOT / ("port" if IN_REPO else "project")
SPU_DIR = PORT / "spu"
BUILD = ROOT / "build"
TITLE_ID = os.environ.get("RES_TITLE_ID") or "BCUS98176"


def toolkit():
    env = os.environ.get("PS3RECOMP_DIR")
    if env:
        return Path(env).resolve()
    return ROOT / "ps3recomp" if IN_REPO else ROOT


def eboot():
    env = os.environ.get("R3_EBOOT")
    if env:
        return Path(env).resolve()
    return ROOT / (f"game/{TITLE_ID}/EBOOT.elf" if IN_REPO else "game/EBOOT.elf")


def executable():
    return BUILD / TITLE_ID / "ResistanceRecomp"


def disc_root():
    """The folder holding PS3_GAME/: PS3_VFS_ROOT, game/<title> when the
    disc was extracted there, or the toolkit tree itself (dev layout)."""
    env = os.environ.get("PS3_VFS_ROOT")
    if env:
        return Path(env)
    if IN_REPO:
        return ROOT / "game" / TITLE_ID
    return ROOT


def fnv1a64(data):
    value = 1469598103934665603
    for byte in data:
        value = ((value ^ byte) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return value


def eboot_bytes(path, va, size, what):
    """The size bytes at guest address va of the big-endian ELF64 at path."""
    import struct
    elf = Path(path).read_bytes()
    if elf[:6] != b"\x7fELF\x02\x02":
        raise SystemExit(f"{path}: not a big-endian ELF64 (decrypt EBOOT.BIN first)")
    phoff = struct.unpack_from(">Q", elf, 32)[0]
    phentsize, phnum = struct.unpack_from(">HH", elf, 54)
    for i in range(phnum):
        off = phoff + i * phentsize
        kind = struct.unpack_from(">I", elf, off)[0]
        fileoff, vaddr, _, filesz = struct.unpack_from(">QQQQ", elf, off + 8)
        if kind == 1 and vaddr <= va and va + size <= vaddr + filesz:
            return elf[fileoff + va - vaddr:fileoff + va - vaddr + size]
    raise SystemExit(f"{what} not found in the segments of {path}")


def write_if_changed(path, data):
    path = Path(path)
    if not path.exists() or path.read_bytes() != data:
        path.write_bytes(data)


def lift_raw(raw, dest, base, prefix, tk=None):
    """Lift raw SPU bytes loaded at LS base into dest/spu_recomp.{c,h} with the
    toolkit's find_spu_functions.py and spu_lifter.py. Writes image.bin,
    functions.json and lift.json beside them (all game-derived, .gitignore'd).
    Returns the number of functions."""
    import json
    import subprocess
    import sys
    import tempfile
    tk = Path(tk) if tk else toolkit()
    if not (tk / "tools/spu_lifter.py").is_file():
        raise SystemExit(f"no toolkit at {tk} (run tools/setup_toolkit.sh, or set PS3RECOMP_DIR)")
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    write_if_changed(dest / "image.bin", raw)
    sys.path.insert(0, str(tk / "tools"))
    from find_spu_functions import detect_functions
    functions, _ = detect_functions(raw, base_override=base, verbose=False, raw=True)
    bounds = json.dumps([{"start": a, "end": b} for a, b in functions], indent=2).encode()
    write_if_changed(dest / "functions.json", bounds)
    with tempfile.TemporaryDirectory() as temp:
        out = Path(temp)
        subprocess.run([sys.executable, str(tk / "tools/spu_lifter.py"),
                        str(dest / "image.bin"), "--base", hex(base),
                        "--functions", str(dest / "functions.json"),
                        "--symbol-prefix", prefix, "--return-entries",
                        "--output", str(out), "--report", str(out / "lift.json")], check=True)
        for name in ("spu_recomp.c", "spu_recomp.h", "lift.json"):
            content = (out / name).read_bytes()
            content = content.replace(b'"../../runtime/spu/spu_helpers.h"', b'"spu_helpers.h"')
            content = content.replace(b'"../../runtime/spu/spu_context.h"', b'"spu_context.h"')
            write_if_changed(dest / name, content)
    return len(functions)


def check_image(dest, raw, what, script):
    """--check: the image.bin a previous lift wrote is these bytes."""
    image = Path(dest) / "image.bin"
    if not image.is_file() or image.read_bytes() != raw:
        raise SystemExit(f"{image} is missing or stale: run tools/{script}")
