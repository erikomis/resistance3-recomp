#!/usr/bin/env python3
"""Find and lift Resistance 3's "ig job modules" from EBOOT.elf.

Insomniac's igPm SPURS policy module (tools/prepare_r3_ig_pm.py) runs a job
loop (its second stage, raw bytes at EBOOT VA 0x00E28A00 that igPm loads at LS
0x3F580). For each job it reads a 64-byte job descriptor whose word at +0x30
is the guest address of the job's module, and whose first six halfwords say
where the module goes. The modules are raw SPU bytes in the EBOOT's read-only
data, so the SPU image scanner never sees them and they ran in the
interpreter.

A module starts with a 0x20-byte header, code follows at +0x20:

  +0x00  four `ila $2, <hash>` words that identify it
  +0x10  eight big-endian halfwords h0..h7, each a count of words (x4 = bytes):
           h0  local-store address it is loaded at         (0x40  -> LS 0x100)
           h1  bytes it occupies from there to the end of its bss
           h2  bytes to copy, this header included
           h3  local-store address of its bss
           h4  bytes of bss to clear
           h5  local-store address of its entry (called with bisl)
           h6  not read by the loader (0x0000..0x1000)
           h7  0 (0x8000 marks the other, position-independent kind below)

The loader copies the module with MFC GETs of at most 16 KB each, the first
one from the module's guest address to LS h0*4, so the module is
position-fixed: each is lifted at its own load address (they all say 0x100)
into port/spu/igjobs/igjob_<ea>/ (spu_recomp.c/.h, image.bin, functions.json,
lift.json: translated game code, never commit it), and igjobs_register.c
registers each lift as a resident code region keyed on the module's guest
address (spu_overlay_register_region), which is what that first GET matches.
The region spans the module's code only, not the data behind it: a GET the
job makes into its own data must not retire the lift. PS3_IGJOBS=0 leaves the
modules to the interpreter.

Code and data are told apart by following the code (see discover), because
several modules keep tables between functions and all of them keep tables
after the last one; what is not found is still run, by the interpreter.

The EBOOT holds about 150 more blobs with the same four-ila signature and h7
= 0x8000, h1 = h2 = h3 = their size: position-independent sub-modules, as the
job loop itself is, that tables elsewhere point at ("igNav" at 0x00FF4580,
{id, address, size} at 0x00D07F30, 0x00F1F1A0). This loader cannot place
them (h0 is not a load address there); --list shows them, nothing lifts them
yet.

  tools/lift_r3_igjobs.py                 # find and lift every module
  tools/lift_r3_igjobs.py --only 00E0A480 # one of them (repeatable; igBink)
  tools/lift_r3_igjobs.py --loop          # also igPm's job loop itself
  tools/lift_r3_igjobs.py --list          # what the scan finds, lift nothing
  tools/lift_r3_igjobs.py --check         # the lifted images match the EBOOT

Re-run cmake afterwards.
"""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3_layout  # noqa: E402

# The igPm policy module: its bytes pin the EBOOT these findings are for.
IGPM_VA, IGPM_SIZE, IGPM_FNV = 0x00E28F80, 560, 0xCA191E29E59B1967
# igPm's second stage, the job loop: same header with h0 = 0 (it is
# position-independent); igPm loads it at this address (`ila $39, 0x3F580`).
LOOP_VA, LOOP_LS = 0x00E28A00, 0x3F580
LOOP_HALFWORDS = (0, 0x160, 0x160, 0x160, 0, 8, 0, 0)
HEADER = 0x20
FIRST_IMAGE_ID = 940000
LOOP_IMAGE_ID = 940900
# Names known from a run (the job descriptor carries a name pointer); the
# EBOOT has no static table from name to module.
NAMES = {0x00E0A480: "igBink"}


class Module:
    def __init__(self, ea, base, size, entry, bss, bss_size, halfwords, name=None):
        self.ea, self.base, self.size, self.entry = ea, base, size, entry
        self.bss, self.bss_size, self.halfwords = bss, bss_size, halfwords
        self.name = name or NAMES.get(ea, "")
        self.dir = f"igjob_{ea:08x}"
        self.prefix = f"r3_igjob_{ea:08x}_"


def segments(path):
    """[(guest address, bytes)] of the EBOOT's PT_LOADs: code with rodata, data."""
    elf = Path(path).read_bytes()
    if elf[:6] != b"\x7fELF\x02\x02":
        raise SystemExit(f"{path}: not a big-endian ELF64 (decrypt EBOOT.BIN first)")
    phoff = struct.unpack_from(">Q", elf, 32)[0]
    phentsize, phnum = struct.unpack_from(">HH", elf, 54)
    out = []
    for i in range(phnum):
        off = phoff + i * phentsize
        if struct.unpack_from(">I", elf, off)[0] != 1:
            continue
        fileoff, vaddr, _, filesz = struct.unpack_from(">QQQQ", elf, off + 8)
        if filesz:
            out.append((vaddr, elf[fileoff:fileoff + filesz]))
    if not out:
        raise SystemExit(f"{path}: no PT_LOAD segment")
    return out


def has_signature(seg, off):
    """Four `ila $2, imm18` words."""
    return all(seg[off + i] in (0x42, 0x43) and seg[off + i + 3] & 0x7F == 2
               for i in (0, 4, 8, 12))


def scan(va, seg):
    """Every blob with the signature: (fixed-address modules the job loop
    loads, [(ea, halfwords)] of the position-independent kind, [(ea,
    halfwords)] of anything else)."""
    fixed, pic, other = [], [], []
    for off in range(0, len(seg) - HEADER, 16):
        if not has_signature(seg, off):
            continue
        h = struct.unpack_from(">8H", seg, off + 16)
        ea = va + off
        base, mem, size, bss, bss_size, entry = (x << 2 for x in h[:6])
        if (h[7] == 0 and base >= 0x100 and base % 16 == 0 and size > HEADER
                and off + size <= len(seg)
                and bss % 16 == 0 and bss >= base + size and mem == bss + bss_size - base
                and bss + bss_size <= LOOP_LS
                and base + HEADER <= entry < base + size):
            fixed.append(Module(ea, base, size, entry, bss, bss_size, h))
        elif h[7] == 0x8000 and h[2] == h[3] and (h[5] << 2) >= HEADER:
            pic.append((ea, h))
        else:
            other.append((ea, h))
    return fixed, pic, other


def loop_module(va, seg):
    off = LOOP_VA - va
    if not has_signature(seg, off) or struct.unpack_from(">8H", seg, off + 16) != LOOP_HALFWORDS:
        raise SystemExit("igPm's job loop is not at 0x%08X: not the BCUS98176 01.00 EBOOT?" % LOOP_VA)
    size = LOOP_HALFWORDS[2] << 2
    m = Module(LOOP_VA, LOOP_LS, size, LOOP_LS + (LOOP_HALFWORDS[5] << 2), LOOP_LS + size, 0,
               LOOP_HALFWORDS, "igPm job loop")
    m.dir, m.prefix = "igpm_loop", "r3_igpm_loop_"
    return m


# ---------------------------------------------------------------------------
# Code discovery

_DIRECT = {"br", "bra", "brsl", "brasl", "brz", "brnz", "brhz", "brhnz"}
_UNDECODED = {"???", ".word"}
_PADDING = {"nop", "lnop"}


def _targets(ins):
    return [int(t, 16) for t in (x.strip() for x in ins.operands.split(",")) if t.startswith("0x")]


def discover(raw, base, entry, tk_tools):
    """Function bounds [(start, end)] of the module's code, and the address
    its last instruction ends at.

    Followed from the entry first. Much of a module is reached only through
    pointers the job computes (direct branches from the entry of the module
    at 0x00D7A480 reach 5 KB of its 64 KB of code), so three more sources
    seed it, each accepted only if everything it leads to decodes, without a
    stop (stopd, the game's assert, is fine), to a branch:
      - constants the code loads and branches to (the toolkit's collectors),
      - words outside the code that hold the address of a function start,
      - whatever follows a return, a jump or padding (the next function).
    The cases of a position-independent switch are followed through its
    table: `ila $t, table` ... `bi $2`, the table right behind the bi, each
    entry the distance from the table to a case (igBink's decoder loop at LS
    0x5570 is one such case and ran in the interpreter without this).
    Then, descending, what follows undecodable words or a stop: the first
    function behind a table. A short table that decodes and runs into a
    function already found is not code. Last, every 8-byte boundary still uncovered
    between the first and the last instruction found: accepted if it decodes
    to a branch, or runs for 16 instructions into code already found."""
    sys.path.insert(0, str(tk_tools))
    import find_spu_functions as fsf
    from spu_disasm import disassemble_spu
    lo, hi = base + HEADER, base + len(raw)
    by = {i.addr: i for i in disassemble_spu(raw[HEADER:], base_addr=lo)}

    def ends(ins):
        """No fall-through past this instruction."""
        if ins.mnemonic in ("br", "bra", "bi", "iret", "stopd"):
            return True
        return ins.mnemonic == "stop" and not fsf.is_resuming_stop(ins)

    reached, starts, rejected = set(), set(), set()

    def explore(seed, strict=True):
        """Instructions reachable from seed and not yet reached, the direct
        branch targets among them, and what was wrong with it, if anything:
        'bytes' (not instructions, a stop, or the end of the image) or
        'falls' (runs into code already found without a branch). Not strict:
        the seed is known to be code, a stop is an assert and ends a path."""
        seen, found, work, wrong = set(), set(), [seed], set()
        while work:
            pc = work.pop()
            first = True
            while pc not in seen:
                if pc in reached:
                    if not first:
                        wrong.add("falls")
                    break
                ins = by.get(pc)
                # `stopd $0,$1,$1` is the game's assert and ends a path; a
                # stop is what a table of small integers decodes to.
                if ins is None or ins.mnemonic in _UNDECODED or (
                        strict and ins.mnemonic == "stop"):
                    if strict or first:
                        wrong.add("bytes")
                    break
                seen.add(pc)
                first = False
                if ins.mnemonic in _DIRECT:
                    for t in _targets(ins):
                        if lo <= t < hi and t % 4 == 0:
                            found.add(t)
                            work.append(t)
                        elif strict:
                            wrong.add("bytes")
                if ends(ins):
                    break
                pc += 4
        return seen, found, wrong

    def take(seed, may_fall=True, least=1, fall_least=0, strict=True):
        """Accept seed as a function start if what it leads to is code."""
        if seed in starts or not (lo <= seed < hi) or seed % 4:
            return False
        if seed in reached:
            starts.add(seed)
            return True
        if strict and seed in rejected:
            return False
        seen, found, wrong = explore(seed, strict)
        if ("bytes" in wrong or len(seen) < least
                or ("falls" in wrong and (not may_fall or len(seen) < fall_least))):
            rejected.add(seed)
            return False
        reached.update(seen)
        starts.update(found)
        starts.add(seed)
        return True

    # The entry is code whatever it leads to (a stop is an assert there).
    seen, work = set(), [entry]
    while work:
        pc = work.pop()
        while lo <= pc < hi and pc not in seen and by[pc].mnemonic not in _UNDECODED:
            seen.add(pc)
            if by[pc].mnemonic in _DIRECT:
                for t in _targets(by[pc]):
                    if lo <= t < hi and t % 4 == 0:
                        starts.add(t)
                        work.append(t)
            if ends(by[pc]):
                break
            pc += 4
    reached.update(seen)
    starts.add(entry)

    def after(a, kinds):
        prev = by.get(a - 4)
        return prev is not None and prev.mnemonic in kinds

    while True:
        grew = False
        insns = [by[a] for a in sorted(reached)]
        for t in sorted(fsf.collect_link_register_targets(insns)
                        | fsf.collect_computed_branch_targets(insns)
                        | fsf.collect_jump_table_targets(insns, raw[HEADER:], lo, hi)
                        | fsf.collect_ila_continuation_targets(insns, lo, hi)
                        | fsf.collect_duff_targets(insns, lo, hi)):
            grew |= take(t)
        # Words outside the code holding the address of something that
        # follows a return, a jump or padding: callbacks and tables.
        for a in range(lo, hi - 3, 4):
            if a in reached:
                continue
            t = struct.unpack_from(">I", raw, a - base)[0]
            if lo < t < hi and after(t, ("bi", "br", "bra", "nop", "lnop")):
                grew |= take(t, least=2)
        # The cases of a switch: `bi` with its table behind it, named by an ila.
        tables = {t for i in insns if i.mnemonic == "ila" for t in _targets(i)}
        for i in insns:
            table = i.addr + 4
            if i.mnemonic != "bi" or table not in tables or table in reached:
                continue
            cases = []
            for a in range(table, hi - 3, 4):
                t = (table + struct.unpack_from(">I", raw, a - base)[0]) & 0xFFFFFFFF
                if a in reached or t % 4 or not (lo <= t < hi):
                    break
                cases.append(t)
            if len(cases) >= 2:
                for t in cases:
                    grew |= take(t, strict=False)
        # The next function: what follows a return, a jump or padding in code.
        # (Not padding anywhere: the compiler pads inside functions too.)
        for a in range(lo + 4, hi, 4):
            if a not in reached and a - 4 in reached and after(a, ("bi", "br", "bra", "nop", "lnop")):
                grew |= take(a)
        if grew:
            continue
        # The first function behind a table, from the top down.
        for a in range(hi - 4, lo, -4):
            if a not in reached and a - 4 not in reached and (
                    a - 4 < lo or after(a, ("stop", "stopd") + tuple(_UNDECODED))):
                grew |= take(a, least=4, fall_least=16)
        if grew:
            continue
        # What is left between the first and the last instruction found.
        for a in range((min(reached) + 7) & ~7, max(reached), 8):
            if a not in reached:
                grew |= take(a, least=4, fall_least=16)
        if not grew:
            break

    bounds = []
    for s in sorted(a for a in starts if a in reached):
        e = s
        while e in reached and (e == s or e not in starts):
            e += 4
        bounds.append((s, e))
    return bounds, max(reached) + 4


def uncovered(raw, base, bounds, code_end, tk_tools):
    """[(address, bytes)] of what discover left out between the first function
    and the end of the code that still reads as code: runs of four or more
    words that decode and are not a stop or padding. Tables of small
    integers and floats read as code too, so this over-reports."""
    sys.path.insert(0, str(tk_tools))
    from spu_disasm import disassemble_spu
    covered = set()
    for a, b in bounds:
        covered.update(range(a, b, 4))
    first = min(a for a, _ in bounds)
    out, run = [], 0
    for ins in disassemble_spu(raw[first - base:code_end - base], base_addr=first):
        if (ins.addr in covered or ins.mnemonic in _UNDECODED or ins.mnemonic in _PADDING
                or ins.mnemonic in ("stop", "stopd")):
            if run >= 4:
                out.append((ins.addr - 4 * run, 4 * run))
            run = 0
        else:
            run += 1
    if run >= 4:
        out.append((code_end - 4 * run, 4 * run))
    return out


def lift(m, raw, dest, tk):
    """Lift one module into dest; returns its manifest entry."""
    dest.mkdir(parents=True, exist_ok=True)
    bounds, code_end = discover(raw, m.base, m.entry, tk / "tools")
    r3_layout.write_if_changed(dest / "image.bin", raw)
    r3_layout.write_if_changed(dest / "functions.json", json.dumps(
        [{"start": a, "end": b} for a, b in bounds], indent=2).encode())
    with tempfile.TemporaryDirectory() as temp:
        out = Path(temp)
        r = subprocess.run([sys.executable, str(tk / "tools/spu_lifter.py"),
                            str(dest / "image.bin"), "--base", hex(m.base),
                            "--functions", str(dest / "functions.json"),
                            "--code-end", hex(code_end),
                            "--symbol-prefix", m.prefix, "--return-entries",
                            "--output", str(out), "--report", str(out / "lift.json")],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"{m.dir}: lift failed\n{r.stdout[-2000:]}\n{r.stderr[-3000:]}")
        for name in ("spu_recomp.c", "spu_recomp.h", "lift.json"):
            content = (out / name).read_bytes()
            content = content.replace(b'"../../runtime/spu/spu_helpers.h"', b'"spu_helpers.h"')
            content = content.replace(b'"../../runtime/spu/spu_context.h"', b'"spu_context.h"')
            r3_layout.write_if_changed(dest / name, content)
    report = json.loads((dest / "lift.json").read_text())
    return {"ea": m.ea, "name": m.name, "dir": m.dir, "prefix": m.prefix,
            "base": m.base, "size": m.size, "entry": m.entry,
            "bss": m.bss, "bss_size": m.bss_size, "code_end": code_end,
            # The resident region: the header and the code, to a quadword.
            "span": (code_end - m.base + 15) & ~15,
            "fnv": f"{r3_layout.fnv1a64(raw):016X}",
            "functions": len(report.get("functions", [])),
            "code_bytes": sum(b - a for a, b in bounds),
            "gaps": [[a, n] for a, n in uncovered(raw, m.base, bounds, code_end, tk / "tools")],
            "unsupported": report.get("unsupported", {})}


def register_c(entries):
    lines = [
        "/* igjobs_register.c -- GENERATED by tools/lift_r3_igjobs.py.",
        " * Resistance 3's ig job modules: raw SPU code in EBOOT.elf that igPm's job",
        " * loop copies to a fixed local-store address (GETs of up to 16 KB, the first",
        " * from the module's guest address) and enters with bisl. Each is lifted at",
        " * that address and registered as a resident code region keyed on the guest",
        " * address; the region spans the header and the code, not the data after it.",
        " * PS3_IGJOBS=0 leaves them all to the interpreter; PS3_IGJOBS_ONLY=<ea,ea,..>",
        " * (hex) registers only those, to bisect a bad lift. */",
        "#include <stdint.h>", "#include <stdlib.h>", "",
        "extern void spu_begin_image(int image_id);",
        "extern void spu_overlay_register_region(uint32_t content_ea, uint32_t span, int image_id);",
    ]
    lines += [f"extern void {e['prefix']}spu_recomp_register(void);" for e in entries]
    lines += [
        "",
        "static int r3_igjob_wanted(uint32_t ea)",
        "{",
        '    const char* only = getenv("PS3_IGJOBS_ONLY");',
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
        "__attribute__((constructor)) static void r3_igjobs_register(void)",
        "{",
        '    { const char* e = getenv("PS3_IGJOBS"); if (e && e[0] == \'0\') return; }',
    ]
    for e in entries:
        what = f"{e['name']}: " if e["name"] else ""
        lines += [
            f"    /* {what}LS 0x{e['base']:X}..0x{e['base'] + e['size']:X}, entry 0x{e['entry']:X}, "
            f"code to 0x{e['code_end']:X} */",
            f"    if (r3_igjob_wanted(0x{e['ea']:08X}u)) {{",
            f"        spu_begin_image({e['image_id']});",
            f"        {e['prefix']}spu_recomp_register();",
            f"        spu_overlay_register_region(0x{e['ea']:08X}u, 0x{e['span']:X}u, {e['image_id']});",
            "    }",
        ]
    lines += ["    spu_begin_image(0);", "}", ""]
    return "\n".join(lines).encode()


def show(fixed, pic, other):
    print(f"{len(fixed)} job modules the igPm job loop loads at a fixed address:")
    for m in fixed:
        print(f"  {m.ea:08X}  LS 0x{m.base:X}..0x{m.base + m.size:X}  entry 0x{m.entry:X}  "
              f"bss 0x{m.bss:X}+0x{m.bss_size:X}  h6 {m.halfwords[6]:04X}  {m.name}")
    print(f"{len(pic)} position-independent sub-modules (h7 = 0x8000), not lifted:")
    for ea, h in pic:
        print(f"  {ea:08X}  0x{h[2] << 2:X} bytes  entry +0x{h[5] << 2:X}  bss 0x{h[4] << 2:X}")
    print(f"{len(other)} other blobs with the signature (igPm, its job loop, other loaders' DEADDEAD and C0DEC0DE modules):")
    for ea, h in other:
        print(f"  {ea:08X}  " + " ".join(f"{x:04X}" for x in h))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="only check the current extraction")
    parser.add_argument("--list", action="store_true", help="only show what the scan finds")
    parser.add_argument("--only", action="append", metavar="EA",
                        help="limit to the module at this guest address, hex (repeatable)")
    parser.add_argument("--loop", action="store_true",
                        help="also lift igPm's job loop (EBOOT 0x%08X, LS 0x%X)" % (LOOP_VA, LOOP_LS))
    parser.add_argument("--eboot", type=Path, default=r3_layout.eboot())
    parser.add_argument("--dest", type=Path, default=r3_layout.SPU_DIR / "igjobs")
    parser.add_argument("--toolkit", type=Path, default=None, help="default: PS3RECOMP_DIR or ./ps3recomp")
    args = parser.parse_args()

    raw = r3_layout.eboot_bytes(args.eboot, IGPM_VA, IGPM_SIZE, "the igPm policy module")
    if r3_layout.fnv1a64(raw) != IGPM_FNV:
        raise SystemExit("the igPm policy module's fingerprint differs: "
                         "not the BCUS98176 01.00 EBOOT this loader was read from?")
    segs = segments(args.eboot)
    va, seg = segs[0]          # every module the job loop loads is in rodata
    fixed, pic, other = scan(va, seg)
    for more in segs[1:]:
        fixed2, pic2, other2 = scan(*more)
        pic += pic2
        other += [(m.ea, m.halfwords) for m in fixed2] + other2
    if args.list:
        show(fixed, pic, other)
        return
    if not fixed:
        raise SystemExit("no ig job modules found")
    manifest_path = args.dest / "igjobs_manifest.json"

    if args.check:
        if not manifest_path.is_file():
            raise SystemExit(f"{manifest_path} is missing: run tools/lift_r3_igjobs.py")
        entries = json.loads(manifest_path.read_text())["modules"]
        for e in entries:
            image = args.dest / e["dir"] / "image.bin"
            want = seg[e["ea"] - va:e["ea"] - va + e["size"]]
            if (not image.is_file() or image.read_bytes() != want
                    or not (args.dest / e["dir"] / "spu_recomp.c").is_file()):
                raise SystemExit(f"{image} is missing or stale: run tools/lift_r3_igjobs.py")
        if not (args.dest / "igjobs_register.c").is_file():
            raise SystemExit(f"{args.dest}/igjobs_register.c is missing: run tools/lift_r3_igjobs.py")
        jobs = sum(e["ea"] != LOOP_VA for e in entries)
        print(f"R3 ig job modules: {jobs} of {len(fixed)} in the EBOOT lifted"
              + (", and igPm's job loop" if jobs != len(entries) else "") + ", OK")
        return

    modules = list(fixed)
    if args.only:
        want = {int(x, 16) for x in args.only}
        modules = [m for m in modules if m.ea in want]
        if len(modules) != len(want):
            raise SystemExit("--only: no module at " + ", ".join(
                f"{x:08X}" for x in sorted(want - {m.ea for m in modules})))
    if args.loop:
        modules.append(loop_module(va, seg))
    tk = Path(args.toolkit) if args.toolkit else r3_layout.toolkit()
    if not (tk / "tools/spu_lifter.py").is_file():
        raise SystemExit(f"no toolkit at {tk} (run tools/setup_toolkit.sh, or set PS3RECOMP_DIR)")

    args.dest.mkdir(parents=True, exist_ok=True)
    # Everything here is translated game code or derived from it.
    r3_layout.write_if_changed(args.dest / ".gitignore", b"*\n")
    order = {m.ea: n for n, m in enumerate(fixed)}
    entries = []
    for m in modules:
        e = lift(m, seg[m.ea - va:m.ea - va + m.size], args.dest / m.dir, tk)
        e["image_id"] = LOOP_IMAGE_ID if m.ea == LOOP_VA else FIRST_IMAGE_ID + order[m.ea]
        entries.append(e)
        bad = sum(e["unsupported"].values())
        print(f"  {m.ea:08X} {m.name or '-':<14} LS 0x{m.base:X}..0x{m.base + m.size:X} entry 0x{m.entry:X} "
              f"code to 0x{e['code_end']:X} ({e['code_bytes']} bytes): {e['functions']} functions, "
              f"{bad} unsupported, {sum(n for _, n in e['gaps'])} bytes in {len(e['gaps'])} "
              f"uncovered runs -> image {e['image_id']}")
    # A partial run (--only) replaces the whole registration: stale folders of
    # other modules stay on disk but are neither registered nor compiled.
    r3_layout.write_if_changed(manifest_path, json.dumps(
        {"eboot_igpm_fnv": f"{IGPM_FNV:016X}", "modules": entries}, indent=2).encode())
    r3_layout.write_if_changed(args.dest / "igjobs_register.c", register_c(entries))
    r3_layout.write_if_changed(args.dest / "igjobs_sources.cmake", (
        "# GENERATED by tools/lift_r3_igjobs.py: the lifts igjobs_register.c registers.\n"
        "set(R3_IGJOB_SOURCES\n" + "".join(
            f'    "${{CMAKE_CURRENT_LIST_DIR}}/{e["dir"]}/spu_recomp.c"\n' for e in entries)
        + '    "${CMAKE_CURRENT_LIST_DIR}/igjobs_register.c")\n').encode())
    total = sum(sum(e["unsupported"].values()) for e in entries)
    print(f"R3 ig job modules ready: {len(entries)} lifted, {sum(e['functions'] for e in entries)} "
          f"functions, {total} unsupported instructions -> {args.dest}")


if __name__ == "__main__":
    main()
