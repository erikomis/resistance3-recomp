#!/usr/bin/env python3
"""Extract the WWS SPU job code modules embedded in the EBOOT.

ps3recomp's extract_jobmods.py pulls these out of a title's SDATA archives;
inFAMOUS 2 links them into the executable instead. Same format either way:

    +0x00  4 x ila          (the 16 bytes lift_jobmods.py signs a module by)
    +0x10  entryOffset
    +0x14  imageSize        (may run a few bytes past the file image: bss)
    +0x20  0xC0DEC0DE
    +0x28  load base        (0x4000, the job code buffer)

Output: <out>/jobmod_<sha1[:12]>_e<entryOffset>.bin, the naming
lift_jobmods.py expects.

--entries FILE also writes the routines a module names only in a table of
function pointers (see pointer_table_entries), as the comma-separated LS
addresses lift_jobmods.py takes in LBP_JOBMOD_EXTRA_FUNCS.

Usage: extract_jobmods_elf.py game/BCUS98176/EBOOT.elf --out out/jobmods
(tools/regen_r3_jobmods.sh runs it and lifts the result.)

From the inFAMOUS 2 port (infamous2-lle/tools/extract_eboot_jobmods.py).
Resistance: Fall of Man links 15 of these modules into both EBOOT.BIN and
game.self (the same 15); two are linked at LS 0x7000 rather than 0x4000.
Resistance 2 links 29 into its EBOOT. Resistance 3: tools/r3_survey.py counts them.
"""
import argparse, hashlib, os, struct

MAGIC = b"\xC0\xDE\xC0\xDE"


def is_module(d, s):
    if s < 0 or s + 0x30 > len(d):
        return False
    ilas = struct.unpack_from(">4I", d, s)
    return all((w >> 24) in (0x42, 0x43) for w in ilas)


def pointer_table_entries(raw):
    """LS addresses of routines the module reaches only through a table of
    absolute function pointers in its data.

    Resistance 3's module at 0x00E9F800 keeps {.., routine, ..} records at LS
    0x11B50 for three hand-written vertex loops (0x5300, 0x4600 and a `bi $r0`
    stub at 0xCA78) and calls them with `bisl`. No branch names them, so the
    lift had no entry there: each call began in the interpreter and stayed in
    it for the routine's first pass, down to the loop's own `bi` (1.3 M
    interpreted instructions a second in the Wws_Job lane, LS 0x5000-0x57FF).

    A word counts when it is a 4-aligned address inside the module, the word
    in front of that address ends a routine or pads one (`bi $r0`, nop, lnop)
    and the one at it does not. No instruction looks like such a word (it
    would be `stop`), and a false hit only splits a lifted function in two."""
    if len(raw) < 0x30 or raw[0x20:0x24] != MAGIC:
        return []
    base = struct.unpack_from(">I", raw, 0x28)[0] or 0x4000
    words = struct.unpack_from(f">{len(raw) // 4}I", raw)

    def filler(w):
        return w == 0x00200000 or (w >> 21) == 0x201            # lnop, nop

    out = set()
    for w in words[0x30 // 4:]:
        i = (w - base) // 4
        if (w % 4 == 0 and base + 0x34 <= w < base + len(words) * 4
                and (words[i - 1] == 0x35000000 or filler(words[i - 1]))
                and words[i] and not filler(words[i])):
            out.add(w)
    return sorted(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("elf")
    ap.add_argument("--out", required=True)
    ap.add_argument("--entries", metavar="FILE",
                    help="write the pointer-table routines of all modules here")
    args = ap.parse_args()

    d = open(args.elf, "rb").read()
    starts, i = [], 0
    while True:
        i = d.find(MAGIC, i + 1)
        if i < 0:
            break
        if i % 4 == 0 and is_module(d, i - 0x20):
            starts.append(i - 0x20)

    os.makedirs(args.out, exist_ok=True)
    entries = set()
    for n, s in enumerate(starts):
        entry, size = struct.unpack_from(">II", d, s + 0x10)
        end = s + size
        if n + 1 < len(starts):
            end = min(end, starts[n + 1])
        raw = d[s:min(end, len(d))]
        name = f"jobmod_{hashlib.sha1(raw).hexdigest()[:12]}_e{entry:x}.bin"
        with open(os.path.join(args.out, name), "wb") as f:
            f.write(raw)
        print(f"  file+0x{s:06X}  entry=0x{entry:05X} size=0x{size:05X} "
              f"({len(raw)} bytes) -> {name}")
        found = pointer_table_entries(raw)
        if found:
            print("    pointer-table routines: " + ", ".join(f"0x{a:X}" for a in found))
        entries.update(found)
    print(f"Extracted {len(starts)} job module(s) into {args.out}")
    if args.entries:
        # One list for every module: they all load at the same address and
        # lift_jobmods.py offers each address to each module, where it can
        # only split a function that spans it.
        with open(args.entries, "w") as f:
            f.write(",".join(f"0x{a:X}" for a in sorted(entries)))


if __name__ == "__main__":
    main()
