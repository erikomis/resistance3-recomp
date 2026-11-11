#!/usr/bin/env python3
"""r3_survey.py -- what is in a decrypted Resistance 3 EBOOT.elf, before porting it.

    tools/r3_survey.py game/BCUS98176/EBOOT.elf [--sfo PARAM.SFO] [--disc DIR]
                       [--json out/survey/BCUS98176.json]
    tools/r3_survey.py --identify EBOOT.elf      # prints 100 / 105, or nothing
    tools/r3_survey.py EBOOT.elf --write-insn port/patches

The first thing to run once the disc is here (tools/rebuild.sh runs it as its
"survey" step). Read-only unless --write-insn is given. It reports:

  * which executable this is: RPCS3's PPU hash (the PPU-<sha1> key of its
    patch.yml), matched against the four known Resistance 3 executables
    (BCUS98176 / BCES01118, 01.00 disc and 01.05 update);
  * PARAM.SFO (TITLE_ID, APP_VER, VERSION, TITLE) when given;
  * the ELF's segments and sections, the entry OPD and its TOC (r2);
  * the SPU code embedded in it, which the Resistance 1 and 2 ports had to
    cut out and lift by hand: SPU ELFs (the build's image scanner finds
    those), WWS job modules (0xC0DEC0DE: tools/regen_r3_jobmods.sh),
    position-independent blobs behind DEADDEAD padding (Resistance 2's
    lift_r2_relocmods.py; raw-SPU programs such as the Bink decoder have the
    same header), and the strings that name the Insomniac pieces the earlier
    ports met (igInitRawSpu, Wws_Job, Bink, ...);
  * other executables the EBOOT names (.self/.sprx: Resistance: Fall of Man
    exitspawns into game.self; Resistance 2 is a single EBOOT), and with
    --disc the ones in PS3_GAME/USRDIR;
  * the community patches RPCS3 ships for this executable ("Unlock FPS" by
    Whatcookie and boma, "Extended FOV" by illusion): each word's address,
    its section, the word there now and the one the patch writes, and
    whether it is code (lifted in both forms, --insn-patches) or data
    (written into guest memory by port/patches.cpp).

--write-insn DIR writes, for a known executable, DIR/eboot_<ver>.insn.json
(the code words, for tools/rebuild.sh's lift step) and DIR/eboot_<ver>.words.h
(every patched word's original value as the signature port/patches.cpp checks,
and the data words it writes). Re-lift and rebuild afterwards.

Only the Python standard library: it runs before the toolkit is installed.
"""
import argparse
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

# RPCS3's PPU hash -> (title ID, version key, APP_VER). From RPCS3's patch.yml.
KNOWN = {
    '502feb2351d2b637a2704d5a50cb44bc1b781532': ('BCUS98176', '100', '01.00'),
    '4aa1887bfdd285e3026e6a97d65ed617ddcf4789': ('BCUS98176', '105', '01.05'),
    '2701cf372814d59f26e771dc9394323d4f799682': ('BCES01118', '100', '01.00'),
    'cd72aa19da7e24a00802932d06460034c7d94fc6': ('BCES01118', '105', '01.05'),
}

# RPCS3 patch.yml, "Resistance 3" (the same addresses on both discs):
#   Unlock FPS (Whatcookie, boma): three be32 words
#   Extended FOV (illusion): one bef32, 0.7
# Notes from patch.yml: "Maximum framerate with the patch is proportionate to
# Vblank frequency. More than 60 Vblank is not recommended as framerates above
# 75 can cause issues with left analog-stick input detection [...] ladder
# climbing may require several attempts."
COMMUNITY = {
    '100': {'unlock': [(0x007EEAC8, 0xC0228DCC), (0x00F02AD4, 0x38D1B717), (0x00736C44, 0x60000000)],
            'fov': 0x00F0608C},
    '105': {'unlock': [(0x00817D48, 0xC0228DD4), (0x00F330FC, 0x38D1B717), (0x0075FA54, 0x60000000)],
            'fov': 0x00F3668C},
}
FOV_DEFAULT = 0.7

STRINGS = [b'igInitRawSpu', b'Wws_Job', b'SpursJq', b'Bink', b'bink', b'spurs',
           b'game.self', b'.self', b'.sprx', b'exitspawn', b'-level', b'packed/levels',
           b'ps3.online.scea.com', b'.scea.com', b'Insomniac', b'TROPHY', b'cellHttp']

PT = {0: 'NULL', 1: 'LOAD', 2: 'DYNAMIC', 4: 'NOTE', 7: 'TLS',
      0x60000001: 'SCE_PROC_PARAM', 0x60000002: 'SCE_PRX_PARAM', 0x700000A4: 'SCE_PPURELA'}


# ---------------------------------------------------------------------------
# ELF
# ---------------------------------------------------------------------------
class Elf:
    def __init__(self, path):
        self.path = Path(path)
        self.d = self.path.read_bytes()
        d = self.d
        if d[:6] != b'\x7fELF\x02\x02':
            raise SystemExit(f'{path}: not a big-endian ELF64 (decrypt EBOOT.BIN first: tools/rebuild.sh decrypt)')
        self.entry, phoff, shoff = struct.unpack_from('>QQQ', d, 0x18)
        phentsize, phnum, shentsize, shnum, shstrndx = struct.unpack_from('>HHHHH', d, 0x36)
        self.segs = []
        for i in range(phnum):
            o = phoff + i * phentsize
            t, fl, off, va, pa, fs, ms, al = struct.unpack_from('>IIQQQQQQ', d, o)
            self.segs.append(dict(type=t, flags=fl, off=off, va=va, filesz=fs, memsz=ms))
        self.secs = []
        if shoff and shnum and shoff + shnum * shentsize <= len(d):
            raw = []
            for i in range(shnum):
                o = shoff + i * shentsize
                name, t, fl, addr, off, size = struct.unpack_from('>IIQQQQ', d, o)
                raw.append((name, t, fl, addr, off, size))
            strtab = raw[shstrndx] if shstrndx < len(raw) else None
            for name, t, fl, addr, off, size in raw:
                nm = ''
                if strtab:
                    s = strtab[4] + name
                    e = d.find(b'\0', s)
                    nm = d[s:e].decode('latin-1') if e > s else ''
                self.secs.append(dict(name=nm, type=t, flags=fl, addr=addr, off=off, size=size))

    def ppu_hash(self):
        """RPCS3's PPU-<sha1>: over every program header's type and flags, and
        each loadable segment's vaddr, memsz and file bytes (ppu_load_exec)."""
        h = hashlib.sha1()
        for s in self.segs:
            h.update(struct.pack('>II', s['type'], s['flags']))
            if s['type'] == 1 and s['memsz']:
                h.update(struct.pack('>QQ', s['va'], s['memsz']))
                h.update(self.d[s['off']:s['off'] + s['filesz']])
        return h.hexdigest()

    def va_to_off(self, va, size=4):
        for s in self.segs:
            if s['type'] == 1 and s['va'] <= va and va + size <= s['va'] + s['filesz']:
                return s['off'] + va - s['va']
        return None

    def off_to_va(self, off):
        for s in self.segs:
            if s['type'] == 1 and s['off'] <= off < s['off'] + s['filesz']:
                return s['va'] + off - s['off']
        return None

    def rd32(self, va):
        o = self.va_to_off(va)
        return None if o is None else struct.unpack_from('>I', self.d, o)[0]

    def section_of(self, va):
        for s in self.secs:
            if s['addr'] and s['addr'] <= va < s['addr'] + s['size']:
                return s
        return None

    def is_code(self, va):
        """In an SHF_EXECINSTR section; without section headers, an executable
        segment (which may also hold read-only data: check by hand)."""
        s = self.section_of(va)
        if s is not None:
            return bool(s['flags'] & 0x4)
        for g in self.segs:
            if g['type'] == 1 and g['va'] <= va < g['va'] + g['memsz']:
                return bool(g['flags'] & 0x1)
        return False

    def toc(self):
        """The entry OPD's second word: the TOC base the code addresses r2 from."""
        o = self.va_to_off(self.entry, 8)
        if o is None:
            return None, None
        func, toc = struct.unpack_from('>II', self.d, o)
        return func, toc


# ---------------------------------------------------------------------------
# PARAM.SFO
# ---------------------------------------------------------------------------
def read_sfo(path):
    d = Path(path).read_bytes()
    if d[:4] != b'\0PSF':
        return {}
    _, kt, dt, n = struct.unpack_from('<IIII', d, 4)
    out = {}
    for i in range(n):
        ko, fmt, ln, mx, do = struct.unpack_from('<HHIII', d, 0x14 + i * 16)
        e = d.find(b'\0', kt + ko)
        key = d[kt + ko:e].decode('latin-1')
        v = d[dt + do:dt + do + ln]
        if fmt == 0x0404:
            out[key] = struct.unpack('<I', v[:4])[0]
        else:
            out[key] = v.rstrip(b'\0').decode('utf-8', 'replace')
    return out


# ---------------------------------------------------------------------------
# Embedded SPU code
# ---------------------------------------------------------------------------
def spu_elfs(d):
    out, i = [], 0
    while True:
        i = d.find(b'\x7fELF\x01\x02\x01', i + 1)
        if i < 0:
            break
        if i + 0x34 <= len(d) and struct.unpack_from('>H', d, i + 0x12)[0] == 0x17:
            entry = struct.unpack_from('>I', d, i + 0x18)[0]
            out.append((i, entry))
    return out


def jobmods(d):
    out, i = [], 0
    while True:
        i = d.find(b'\xC0\xDE\xC0\xDE', i + 1)
        if i < 0:
            break
        s = i - 0x20
        if i % 4 or s < 0 or s + 0x30 > len(d):
            continue
        if all((w >> 24) in (0x42, 0x43) for w in struct.unpack_from('>4I', d, s)):
            entry, size = struct.unpack_from('>II', d, s + 0x10)
            base = struct.unpack_from('>I', d, s + 0x28)[0]
            out.append((s, entry, size, base))
    return out


def deaddead_blobs(d, code_ranges):
    """Resistance 2's relocatable-module header: 4 ila-family words, small
    fields, DEADDEAD x2 at +0x28, code at +0x30 (lift_r2_relocmods.py)."""
    out, seen, i = [], set(), 0
    pat = b'\xDE\xAD\xDE\xAD\xDE\xAD\xDE\xAD'
    while True:
        i = d.find(pat, i + 1)
        if i < 0:
            break
        o = i - 0x28
        if o < 0 or o % 16 or o in seen or any(lo <= o < hi for lo, hi in code_ranges):
            continue
        w = struct.unpack_from('>8I', d, o)
        if not all((x >> 24) in (0x40, 0x41, 0x42, 0x43) for x in w[:4]):
            continue
        if w[5] or w[6] or w[4] >= 0x40000 or w[7] >= 0x40000:
            continue
        seen.add(o)
        out.append(o)
    return out


def find_strings(d):
    res = {}
    for s in STRINGS:
        hits, i = [], -1
        while len(hits) < 2000:
            i = d.find(s, i + 1)
            if i < 0:
                break
            hits.append(i)
        if hits:
            res[s.decode()] = hits
    return res


def cstring_at(d, o, limit=96):
    a = o
    while a > 0 and 0x20 <= d[a - 1] < 0x7F and o - a < limit:
        a -= 1
    b = o
    while b < len(d) and 0x20 <= d[b] < 0x7F and b - a < limit:
        b += 1
    return d[a:b].decode('latin-1')


def decode_toc_load(word, toc):
    """lfs/lwz/lfd/ld rD,d(r2): the address it reads, for the notes."""
    op = word >> 26
    names = {32: 'lwz', 48: 'lfs', 50: 'lfd', 58: 'ld'}
    if op not in names or ((word >> 16) & 31) != 2 or toc is None:
        return None
    disp = word & 0xFFFF
    if op == 58:
        disp &= 0xFFFC
    if disp & 0x8000:
        disp -= 0x10000
    return f'{names[op]} r/f{(word >> 21) & 31},{disp:#x}(r2) -> 0x{(toc + disp) & 0xFFFFFFFF:08X}'


def f32(w):
    return struct.unpack('>f', struct.pack('>I', w))[0]


# ---------------------------------------------------------------------------
# The community patches
# ---------------------------------------------------------------------------
def patch_words(elf, ver):
    """[(kind, addr, orig, new, code?, section)] for this version."""
    c = COMMUNITY[ver]
    rows = []
    for a, new in c['unlock']:
        rows.append(('unlock', a, elf.rd32(a), new, elf.is_code(a), elf.section_of(a)))
    a = c['fov']
    rows.append(('fov', a, elf.rd32(a), struct.unpack('>I', struct.pack('>f', FOV_DEFAULT))[0],
                 elf.is_code(a), elf.section_of(a)))
    return rows


def write_insn(elf, ver, label, phash, outdir, rows):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    if any(r[2] is None for r in rows):
        raise SystemExit('a patch address is outside the ELF\'s file image: not writing')
    code = [r for r in rows if r[4]]
    data = [r for r in rows if not r[4]]
    if any(r[0] == 'fov' for r in code):
        raise SystemExit('the FOV word is in a code section: check by hand before writing')
    _, toc = elf.toc()
    insn = {
        'elf': f'EBOOT.elf (Resistance 3 {label}, RPCS3 PPU-{phash[:8]}...)',
        'source': 'RPCS3 patch.yml, "Unlock FPS" (Whatcookie, boma)',
        'generated_by': 'tools/r3_survey.py --write-insn',
        'patches': [{'addr': f'0x{a:08X}', 'orig': f'0x{o:08X}', 'new': f'0x{n:08X}',
                     'guard': 'g_res_unlock_fps',
                     'note': decode_toc_load(n, toc) or ('nop' if n == 0x60000000 else '')}
                    for _, a, o, n, _, _ in code],
    }
    (outdir / f'eboot_{ver}.insn.json').write_text(json.dumps(insn, indent=2) + '\n')

    L = [f'/* eboot_{ver}.words.h -- GENERATED by tools/r3_survey.py --write-insn from',
         f' * EBOOT.elf (Resistance 3 {label}, RPCS3 PPU-{phash}).',
         ' * The words the community patches touch: their original values (the',
         ' * signature port/patches.cpp checks before it writes anything) and the data',
         ' * words "Unlock FPS" writes. The code words are in eboot_' + ver + '.insn.json. */',
         f'#define R3_HAVE_SET_{ver} 1',
         f'static const R3Word kR3Sig_{ver}[] = {{']
    for kind, a, o, n, isc, _ in rows:
        L.append(f'    {{0x{a:08X}u, 0x{o:08X}u}},   /* {kind}, {"code" if isc else "data"} */')
        nxt = elf.rd32(a + 4)
        if nxt is not None:
            L.append(f'    {{0x{a + 4:08X}u, 0x{nxt:08X}u}},')
    L.append('};')
    L.append(f'static const R3Word kR3UnlockData_{ver}[] = {{')
    for kind, a, o, n, isc, _ in data:
        if kind == 'unlock':
            L.append(f'    {{0x{a:08X}u, 0x{n:08X}u}},   /* {f32(o):g} -> {f32(n):g} */')
    L.append('    {0, 0}')
    L.append('};')
    fov = [r for r in data if r[0] == 'fov']
    L.append(f'static const uint32_t kR3Fov_{ver} = 0x{fov[0][1]:08X}u;   /* game value {f32(fov[0][2]):g} */')
    (outdir / f'eboot_{ver}.words.h').write_text('\n'.join(L) + '\n')
    return outdir / f'eboot_{ver}.insn.json', outdir / f'eboot_{ver}.words.h'


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('eboot', nargs='?')
    ap.add_argument('--identify', metavar='ELF', help='print the version key (100, 105) and exit; nothing if unknown')
    ap.add_argument('--sfo', help='PARAM.SFO to read (default: beside the ELF)')
    ap.add_argument('--disc', help='the folder holding PS3_GAME/ (lists USRDIR executables)')
    ap.add_argument('--json', help='also write the report as JSON here')
    ap.add_argument('--write-insn', metavar='DIR', help='write eboot_<ver>.insn.json and .words.h into DIR')
    a = ap.parse_args()

    if a.identify:
        try:
            k = KNOWN.get(Elf(a.identify).ppu_hash())
        except (OSError, SystemExit):
            return 1
        if not k:
            return 1
        print(k[1])
        return 0
    if not a.eboot:
        ap.error('the decrypted EBOOT.elf is required')

    elf = Elf(a.eboot)
    d = elf.d
    rep = {'file': str(elf.path), 'size': len(d)}
    p = print

    phash = elf.ppu_hash()
    known = KNOWN.get(phash)
    rep['ppu_hash'] = 'PPU-' + phash
    rep['known'] = dict(zip(('title_id', 'version', 'app_ver'), known)) if known else None
    p(f'== {elf.path.name}: {len(d):,} bytes')
    p(f'RPCS3 hash   PPU-{phash}')
    p(f'identified   ' + (f'Resistance 3 {known[0]} {known[2]}' if known else
                          'NOT a known Resistance 3 executable (patch sets and fingerprints will not match)'))

    sfo = a.sfo or str(elf.path.parent / 'PARAM.SFO')
    if os.path.isfile(sfo):
        s = read_sfo(sfo)
        rep['sfo'] = {k: s.get(k) for k in ('TITLE_ID', 'TITLE', 'APP_VER', 'VERSION', 'CATEGORY', 'PS3_SYSTEM_VER') if k in s}
        p('PARAM.SFO    ' + ', '.join(f'{k}={v}' for k, v in rep['sfo'].items()))

    func, toc = elf.toc()
    rep['entry'] = {'opd': elf.entry, 'func': func, 'toc': toc}
    p(f'entry OPD    0x{elf.entry:08X} -> func 0x{(func or 0):08X}, TOC r2 = 0x{(toc or 0):08X}')

    p('\n== segments')
    rep['segments'] = []
    for s in elf.segs:
        fl = ''.join(c if s['flags'] & b else '-' for c, b in (('R', 4), ('W', 2), ('X', 1)))
        p(f"  {PT.get(s['type'], hex(s['type'])):15} {fl}  va 0x{s['va']:08X}  file 0x{s['off']:08X}+0x{s['filesz']:X}  mem 0x{s['memsz']:X}")
        rep['segments'].append({**s, 'type_name': PT.get(s['type'], hex(s['type']))})
    if elf.secs:
        p(f'\n== sections ({len(elf.secs)})')
        for s in elf.secs:
            if s['size'] and s['addr']:
                p(f"  {s['name'] or '?':24} 0x{s['addr']:08X} +0x{s['size']:X}  {'X' if s['flags'] & 4 else ' '}{'W' if s['flags'] & 1 else ' '}")
        rep['sections'] = elf.secs

    code_ranges = [(s['off'], s['off'] + s['size']) for s in elf.secs if s['flags'] & 4 and s['size']]

    p('\n== embedded SPU code')
    se = spu_elfs(d)
    rep['spu_elfs'] = [{'file_off': o, 'va': elf.off_to_va(o), 'entry': e} for o, e in se]
    p(f'SPU ELFs           {len(se)}  (the build\'s image scanner lifts these)')
    for o, e in se[:40]:
        va = elf.off_to_va(o)
        p(f'  file 0x{o:08X}  va {"0x%08X" % va if va is not None else "-":10}  entry 0x{e:05X}')
    jm = jobmods(d)
    rep['jobmods'] = [{'file_off': s, 'entry': e, 'size': z, 'ls_base': b} for s, e, z, b in jm]
    bases = sorted({b for *_, b in jm})
    p(f'WWS job modules    {len(jm)}  (0xC0DEC0DE; LS bases {", ".join(hex(b) for b in bases) or "-"}; tools/regen_r3_jobmods.sh)')
    dd = deaddead_blobs(d, code_ranges)
    rep['deaddead_blobs'] = [{'file_off': o, 'va': elf.off_to_va(o)} for o in dd]
    p(f'DEADDEAD blobs     {len(dd)}  (relocatable SPU modules: the R2 EBOOT has 142)')
    for o in dd[:12]:
        va = elf.off_to_va(o)
        p(f'  file 0x{o:08X}  va {"0x%08X" % va if va is not None else "-"}')
    if len(dd) > 12:
        p(f'  ... {len(dd) - 12} more (see the JSON)')

    p('\n== strings')
    st = find_strings(d)
    rep['strings'] = {}
    for k, hits in st.items():
        ctx = sorted({cstring_at(d, h) for h in hits})
        rep['strings'][k] = {'count': len(hits), 'examples': ctx[:40]}
        p(f'  {k!r:24} {len(hits):5}  e.g. ' + ' | '.join(ctx[:4]))

    if a.disc:
        usr = Path(a.disc) / 'PS3_GAME' / 'USRDIR'
        ex = sorted(str(x.relative_to(usr)) for x in usr.rglob('*')
                    if x.suffix.lower() in ('.self', '.sprx', '.elf', '.bin') and x.is_file())
        rep['usrdir_executables'] = ex
        p(f'\n== executables in {usr} ({len(ex)})')
        for x in ex[:60]:
            p('  ' + x)

    if known:
        ver, label = known[1], f'{known[0]} {known[2]}'
        rows = patch_words(elf, ver)
        p(f'\n== community patches for {label} (RPCS3 patch.yml)')
        rep['community_patches'] = []
        for kind, addr, orig, new, isc, sec in rows:
            o = 'outside the file' if orig is None else f'0x{orig:08X}'
            extra = decode_toc_load(new, toc) if isc else f'{f32(orig) if orig is not None else 0:g} -> {f32(new):g}'
            p(f'  {kind:6} 0x{addr:08X}  {(sec or {}).get("name", "?"):14} {"code" if isc else "data"}  {o} -> 0x{new:08X}  {extra or ""}')
            rep['community_patches'].append({'kind': kind, 'addr': addr, 'orig': orig, 'new': new,
                                             'code': isc, 'section': (sec or {}).get('name')})
        if a.write_insn:
            j, h = write_insn(elf, ver, label, phash, a.write_insn, rows)
            p(f'wrote {j} and {h}: re-lift (tools/rebuild.sh lift build)')
    elif a.write_insn:
        raise SystemExit('--write-insn: not a known Resistance 3 executable, nothing written')

    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(rep, indent=1, default=str) + '\n')
        p(f'\nreport: {a.json}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
