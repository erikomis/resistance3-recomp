#!/usr/bin/env python3
"""Find and lift Resistance 3's position-independent SPU modules from EBOOT.elf.

Besides the job modules igPm's job loop loads at LS 0x100
(tools/lift_r3_igjobs.py), the EBOOT carries two kinds of SPU code that a job
loads wherever it has room in local store and calls through a pointer:

  ig sub-modules   the same header as a job module (four `ila $2` words, then
                   eight halfwords), with h7 = 0x8000 and h1 = h2 = h3 = the
                   size in words; h0 is the words actually used, h4 the bss
                   after it, h5 the entry (+0x20 for most; three return a
                   table of offsets from +0x30). 151 of them. Tables in the
                   EBOOT list them for the PPU: {id, address, size} from
                   0x00D07F30, "igNav" at 0x00FF4580, 0x00F1F1A0. The jobs
                   keep a table of entry addresses by id in their own data
                   and call through it (`bisl`); the code calls back into
                   the job the same way.
  DEADDEAD modules Resistance 2's format: a 0x30-byte header (four ila words,
                   four words, 0xFFFFFFEF, DEADDEAD padding), code at +0x30.
                   33 of them, listed at 0x00FED080..0x00FED2CC.

None has an absolute address in it (no lqa, stqa, bra or brasl), so a
fixed-address lift cannot match them and they ran in the interpreter. Each is
lifted at LS 0 with spu_lifter.py --relocatable (every address derived from
the code's own position adds spu_context.code_base) into
port/spu/relocmods/relocmod_<ea>/ (spu_recomp.c/.h, image.bin, functions.json,
lift.json: translated game code, never commit it), and relocmods_register.c
registers each with spu_overlay_register_region_reloc at its guest address:
a GET from that address, header first, makes the lift resident wherever it
lands. That the jobs load them that way is read from the tables, not from
the jobs' code; a module loaded any other way (from a copy, or without its
header) is simply never resident and keeps running in the interpreter.
PS3_RELOCMODS=0 leaves them all there.

Code and data are told apart as for the job modules
(lift_r3_igjobs.discover), plus the toolkit's scans for hand-made link
addresses and position-independent switch tables. The resident region spans
the header and the code only.

  tools/lift_r3_relocmods.py                  # find and lift every module
  tools/lift_r3_relocmods.py --only 00E35F00  # some of them (repeatable)
  tools/lift_r3_relocmods.py --list           # what the scan finds, lift nothing
  tools/lift_r3_relocmods.py --check          # the lifted images match the EBOOT

Re-run cmake afterwards (port/CMakeLists.txt globs spu/relocmods/).
"""
import argparse
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3_layout  # noqa: E402
import lift_r3_igjobs as igjobs  # noqa: E402

# Relocatable images answer only for their own id, which must be below 4096
# (spu_overlay_register_region_reloc). 200.. are the WWS job modules.
FIRST_IMAGE_ID = 300
DEAD = b"\xDE\xAD" * 4


class Module:
    def __init__(self, ea, kind, header, entry, raw, halfwords):
        self.ea, self.kind, self.header, self.entry = ea, kind, header, entry
        self.raw, self.halfwords = raw, halfwords
        self.dir = f"relocmod_{ea:08x}"
        self.prefix = f"relocmod_{ea:08x}_"


def scan(segs):
    """Every position-independent module, in address order."""
    mods = []
    for va, seg in segs:
        hits = [off for off in range(0, len(seg) - 0x30, 16) if igjobs.has_signature(seg, off)]
        for n, off in enumerate(hits):
            h = struct.unpack_from(">8H", seg, off + 16)
            size, used, entry = h[2] << 2, h[0] << 2, h[5] << 2
            if (h[7] == 0x8000 and h[1] >= h[2] == h[3] and 0x20 <= entry < used <= size
                    and off + size <= len(seg)):
                mods.append(Module(va + off, "ig", 0x20, entry, seg[off:off + size], h))
            elif seg[off + 0x28:off + 0x30] == DEAD and seg[off + 0x20:off + 0x23] == b"\xFF\xFF\xFF":
                # No size in the header: to the next module, or to where 256
                # zero bytes begin. The last one has other data behind it
                # (0x01011280): it ends at the first 0x80 boundary its zero
                # padding reaches, as the modules before it do.
                end = hits[n + 1] if n + 1 < len(hits) else len(seg)
                zeros = seg.find(b"\x00" * 256, off + 0x30, end)
                if zeros > 0:
                    end = zeros
                if n + 1 == len(hits):
                    end = next((x for x in range(off + 0x80, end, 0x80)
                                if not any(seg[x - 32:x])), end)
                end = off + min((end - off + 15) & ~15, 0x3C000)
                if end > off + 0x34:
                    mods.append(Module(va + off, "dead", 0x30, 0x30, seg[off:end],
                                       struct.unpack_from(">4I", seg, off + 16)))
    return sorted(mods, key=lambda m: m.ea)


def discover(m, tk):
    """Function bounds, the end of the code, and entries only a
    position-independent scan finds, for the lifter to split at."""
    sys.path.insert(0, str(tk / "tools"))
    import lift_jobmods
    # igjobs.discover skips a 0x20-byte header; the DEADDEAD kind has 0x30.
    saved = igjobs.HEADER
    igjobs.HEADER = m.header
    try:
        bounds, code_end = igjobs.discover(m.raw, 0, m.entry, tk / "tools")
    finally:
        igjobs.HEADER = saved
    extra = sorted({t for t in (set(lift_jobmods.manual_link_targets(m.raw, base=0))
                                | set(lift_jobmods.switch_table_targets(m.raw, base=0)))
                    if m.header <= t < code_end and t % 4 == 0
                    and not any(s == t for s, _ in bounds)})
    return bounds, code_end, extra


def lift(m, dest, tk):
    """Lift one module into dest; returns its manifest entry."""
    dest.mkdir(parents=True, exist_ok=True)
    bounds, code_end, extra = discover(m, tk)
    r3_layout.write_if_changed(dest / "image.bin", m.raw)
    r3_layout.write_if_changed(dest / "functions.json", json.dumps(
        [{"start": a, "end": b} for a, b in bounds], indent=2).encode())
    with tempfile.TemporaryDirectory() as temp:
        out = Path(temp)
        cmd = [sys.executable, str(tk / "tools/spu_lifter.py"), str(dest / "image.bin"),
               "--base", "0", "--relocatable",
               "--functions", str(dest / "functions.json"), "--code-end", hex(code_end),
               "--symbol-prefix", m.prefix, "--return-entries",
               "--output", str(out), "--report", str(out / "lift.json")]
        if extra:
            cmd += ["--extra-funcs", ",".join(hex(x) for x in extra)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"{m.dir}: lift failed\n{r.stdout[-2000:]}\n{r.stderr[-3000:]}")
        for name in ("spu_recomp.c", "spu_recomp.h", "lift.json"):
            content = (out / name).read_bytes()
            content = content.replace(b'"../../runtime/spu/spu_helpers.h"', b'"spu_helpers.h"')
            content = content.replace(b'"../../runtime/spu/spu_context.h"', b'"spu_context.h"')
            r3_layout.write_if_changed(dest / name, content)
    report = json.loads((dest / "lift.json").read_text())
    return {"ea": m.ea, "kind": m.kind, "dir": m.dir, "prefix": m.prefix,
            "size": len(m.raw), "entry": m.entry, "code_end": code_end,
            # The resident region: the header and the code, to a quadword.
            "span": (code_end + 15) & ~15,
            "fnv": f"{r3_layout.fnv1a64(m.raw):016X}",
            "functions": len(report.get("functions", [])),
            "code_bytes": sum(b - a for a, b in bounds),
            "unsupported": report.get("unsupported", {})}


def register_c(entries):
    lines = [
        "/* relocmods_register.c -- GENERATED by tools/lift_r3_relocmods.py.",
        " * Position-independent SPU code a job loads anywhere in local store (ig",
        " * sub-modules and DEADDEAD modules), lifted at LS 0 and registered at its",
        " * guest address: the GET that loads one, header first, makes its lift",
        " * resident wherever it landed. The region spans the header and the code.",
        " * PS3_RELOCMODS=0 leaves them all to the interpreter; PS3_RELOCMODS_ONLY=",
        " * <ea,ea,..> (hex) registers only those, to bisect a bad lift. */",
        "#include <stdint.h>", "#include <stdlib.h>", "",
        "extern void spu_begin_image(int image_id);",
        "extern void spu_overlay_register_region_reloc(uint32_t content_ea, uint32_t span, int image_id);",
    ]
    lines += [f"extern void {e['prefix']}spu_recomp_register(void);" for e in entries]
    lines += [
        "",
        "static const struct { uint32_t ea, span; int image_id; void (*reg)(void); } r3_relocmods[] = {",
    ]
    lines += [f"    {{ 0x{e['ea']:08X}u, 0x{e['span']:X}u, {e['image_id']}, {e['prefix']}spu_recomp_register }},"
              f"   /* {e['kind']}, entry +0x{e['entry']:X} */" for e in entries]
    lines += [
        "};",
        "",
        "static int r3_relocmod_wanted(uint32_t ea)",
        "{",
        '    const char* only = getenv("PS3_RELOCMODS_ONLY");',
        "    if (!only || !*only) return 1;",
        "    for (const char* p = only; *p; ) {",
        "        char* end;",
        "        if ((uint32_t)strtoul(p, &end, 16) == ea) return 1;",
        "        if (end == p) break;",
        "        p = end;",
        "        while (*p == ',') ++p;",
        "    }",
        "    return 0;",
        "}",
        "",
        "__attribute__((constructor)) static void r3_relocmods_register(void)",
        "{",
        '    { const char* e = getenv("PS3_RELOCMODS"); if (e && e[0] == \'0\') return; }',
        "    for (unsigned i = 0; i < sizeof r3_relocmods / sizeof r3_relocmods[0]; ++i) {",
        "        if (!r3_relocmod_wanted(r3_relocmods[i].ea)) continue;",
        "        spu_begin_image(r3_relocmods[i].image_id);",
        "        r3_relocmods[i].reg();",
        "        spu_overlay_register_region_reloc(r3_relocmods[i].ea, r3_relocmods[i].span,",
        "                                          r3_relocmods[i].image_id);",
        "    }",
        "    spu_begin_image(0);",
        "}",
        "",
    ]
    return "\n".join(lines).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="only check the current extraction")
    parser.add_argument("--list", action="store_true", help="only show what the scan finds")
    parser.add_argument("--only", action="append", metavar="EA",
                        help="lift again only the module at this guest address, hex (repeatable)")
    parser.add_argument("--eboot", type=Path, default=r3_layout.eboot())
    parser.add_argument("--dest", type=Path, default=r3_layout.SPU_DIR / "relocmods")
    parser.add_argument("--toolkit", type=Path, default=None, help="default: PS3RECOMP_DIR or ./ps3recomp")
    args = parser.parse_args()

    raw = r3_layout.eboot_bytes(args.eboot, igjobs.IGPM_VA, igjobs.IGPM_SIZE, "the igPm policy module")
    if r3_layout.fnv1a64(raw) != igjobs.IGPM_FNV:
        raise SystemExit("the igPm policy module's fingerprint differs: "
                         "not the BCUS98176 01.00 EBOOT these formats were read from?")
    mods = scan(igjobs.segments(args.eboot))
    # A module's image id is its place in the scan, whatever is lifted.
    image_id = {m.ea: FIRST_IMAGE_ID + n for n, m in enumerate(mods)}
    if args.list:
        for m in mods:
            print(f"  {m.ea:08X}  {m.kind:<4}  0x{len(m.raw):X} bytes  entry +0x{m.entry:X}  "
                  + " ".join(f"{x:04X}" for x in m.halfwords))
        print(f"{sum(m.kind == 'ig' for m in mods)} ig sub-modules, "
              f"{sum(m.kind == 'dead' for m in mods)} DEADDEAD modules")
        return
    if not mods:
        raise SystemExit("no position-independent modules found")
    manifest_path = args.dest / "relocmods_manifest.json"
    by_ea = {m.ea: m for m in mods}

    if args.check:
        if not manifest_path.is_file():
            raise SystemExit(f"{manifest_path} is missing: run tools/lift_r3_relocmods.py")
        entries = json.loads(manifest_path.read_text())["modules"]
        for e in entries:
            image = args.dest / e["dir"] / "image.bin"
            m = by_ea.get(e["ea"])
            if (m is None or not image.is_file() or image.read_bytes() != m.raw
                    or not (args.dest / e["dir"] / "spu_recomp.c").is_file()):
                raise SystemExit(f"{image} is missing or stale: run tools/lift_r3_relocmods.py")
        # port/CMakeLists.txt compiles every spu/relocmods/*/spu_recomp.c.
        known = {e["dir"] for e in entries}
        stray = [p.parent.name for p in args.dest.glob("*/spu_recomp.c") if p.parent.name not in known]
        if stray:
            raise SystemExit(f"{args.dest}: not in the manifest: {', '.join(sorted(stray))}: "
                             "run tools/lift_r3_relocmods.py")
        if not (args.dest / "relocmods_register.c").is_file():
            raise SystemExit(f"{args.dest}/relocmods_register.c is missing: run tools/lift_r3_relocmods.py")
        print(f"R3 relocatable SPU modules: {len(entries)} of {len(mods)} in the EBOOT lifted, OK")
        return

    tk = Path(args.toolkit) if args.toolkit else r3_layout.toolkit()
    if not (tk / "tools/spu_lifter.py").is_file():
        raise SystemExit(f"no toolkit at {tk} (run tools/setup_toolkit.sh, or set PS3RECOMP_DIR)")
    todo = mods
    kept = {}
    if args.only:
        want = {int(x, 16) for x in args.only}
        if want - set(by_ea):
            raise SystemExit("--only: no module at " + ", ".join(f"{x:08X}" for x in sorted(want - set(by_ea))))
        todo = [by_ea[ea] for ea in sorted(want)]
        # The others stay as the last run left them.
        if manifest_path.is_file():
            kept = {e["ea"]: e for e in json.loads(manifest_path.read_text())["modules"]
                    if e["ea"] in by_ea and (args.dest / e["dir"] / "spu_recomp.c").is_file()}

    args.dest.mkdir(parents=True, exist_ok=True)
    for m in todo:
        e = lift(m, args.dest / m.dir, tk)
        e["image_id"] = image_id[m.ea]
        kept[m.ea] = e
        bad = sum(e["unsupported"].values())
        print(f"  {m.ea:08X} {m.kind:<4} 0x{len(m.raw):X} bytes, entry +0x{m.entry:X}, code to 0x{e['code_end']:X} "
              f"({e['code_bytes']} bytes): {e['functions']} functions, {bad} unsupported -> image {e['image_id']}")
    entries = [kept[ea] for ea in sorted(kept)]
    # Every folder with a spu_recomp.c is compiled: none may outlive its module.
    known = {e["dir"] for e in entries}
    for p in args.dest.glob("relocmod_*"):
        if p.is_dir() and p.name not in known:
            shutil.rmtree(p)
    r3_layout.write_if_changed(manifest_path, json.dumps(
        {"eboot_igpm_fnv": f"{igjobs.IGPM_FNV:016X}", "modules": entries}, indent=2).encode())
    r3_layout.write_if_changed(args.dest / "relocmods_register.c", register_c(entries))
    total = sum(sum(e["unsupported"].values()) for e in entries)
    print(f"R3 relocatable SPU modules ready: {len(entries)} registered "
          f"({sum(e['kind'] == 'ig' for e in entries)} ig sub-modules, "
          f"{sum(e['kind'] == 'dead' for e in entries)} DEADDEAD), "
          f"{sum(e['functions'] for e in entries)} functions, {total} unsupported instructions -> {args.dest}")


if __name__ == "__main__":
    main()
