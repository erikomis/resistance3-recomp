#!/usr/bin/env python3
"""r3_save.py -- inspect / edit a Resistance 3 (BCUS98176 01.00) GAME.SAV.

    tools/r3_save.py --info GAME.SAV
    tools/r3_save.py --levels
    tools/r3_save.py --set-level <name|index> [--checkpoint <name|N>]
                     [--difficulty 0-3] [--unlock-all] IN.SAV OUT.SAV
    tools/r3_save.py --unlock-all IN.SAV OUT.SAV          (level left alone)
    tools/r3_save.py --fix-crc IN.SAV OUT.SAV

Python 3, no dependencies. Never writes IN.SAV (OUT must be another path).

FILE LAYOUT (0x7E70 = 32368 bytes, big-endian). Offsets are file offsets;
"P" is the campaign block at 0x2BE4. Evidence is the guest address of the
code that shows it (game/BCUS98176/EBOOT.elf).

  0x0000 u32  magic 'IGSD'                          [certain: 0x3D8738/0x3D88BC]
  0x0004 u32  0x00092406 (format version)           [certain: compared on load]
  0x0008 u32  0x20100812 (a date stamp)             [certain: compared on load]
  0x000C u32  checksum                              [certain, see below]
  0x0010 16   header remainder, not checksummed     [unknown meaning]
  0x0020 ...  body, 0x7E48 bytes (options, campaign block, unlocks, stats)
  0x7E68 u8   1 after the profile was initialised   [not checksummed]

  CHECKSUM: func_007E9C8C(file+0x20, 0x7E48, 0xFFFFFFFF) -- the reflected
  CRC-32 (table at 0x00CF6148 = the standard 0xEDB88320 table), initial value
  0xFFFFFFFF and NO final inversion, i.e. (~zlib.crc32(file[0x20:0x7E68])) &
  0xFFFFFFFF. Written by 0x3D8738, verified by 0x3D88BC (magic, version, date
  and CRC must all match or the save is rejected). Reproduces the stored value
  of both saves examined. [certain]

  Campaign block P = 0x2BE4 (code reaches it as save+11236):
  P+0x00  60 bytes  carried-over inventory, player 1   [layout: fairly sure,
  P+0x3C  60 bytes  carried-over inventory, player 2    meanings: guesses]
            +0x00 12 x {u16,u16}  one pair per weapon slot, 0xFFFF = empty
                                  (two ammo counts; func_0016A8B0)
            +0x30 u8              health (integer)
            +0x31 u8, +0x32 u8    two selected-weapon bytes (0xFF = none)
            +0x33 5 x u8          five small counters (grenades?)
            +0x38 u32             player flags
  P+0x78  4 bytes   unknown (reset to FF)
  P+0x7C  s32  LEVEL the campaign resumes in, -1 = no campaign   [certain]
               file 0x2C60. Written from the current-level global 0x00F1D594
               (0x1BCD54); read by Continue (0x34BC54, 0x1BDF50); the main
               menu offers Continue when it is > -1 (0x35B048).
  P+0x80  s32  CHECKPOINT index inside that level                [certain]
               file 0x2C64. From/to the checkpoint global 0x010F3DF4.
               Level 0 + checkpoint 0 is treated as "new game" (0x34BC64).
  P+0x84  u8   counter bumped by func_001BD908 (restarts?)       [guess]
  P+0x85  s8   DIFFICULTY 0 casual, 1 normal, 2 difficult,
               3 superhuman (-> global 0x00F08C70)               [sure]
  P+0x88  u16  bit n set = level n may be picked in the campaign
               level select (0x34A5EC; set at 0x1BD348/0x1BDA88) [sure]
  P+0x8A  s8[11][64]  per level, per checkpoint: the best difficulty at
               which the section starting at that checkpoint was finished,
               -1 (FF) = not yet, -2 (FE) = the level has no such checkpoint
               (written when a level is finished). func_003D78C8 writes it,
               func_003D7A94 reads it ("whole campaign done at difficulty
               >= d"), the level select accepts checkpoint N > 0 only when
               some entry below N is >= 0 (0x34A600..0x34A63C).   [sure]
               file 0x2C6E .. 0x2F2D.

  LEVEL INDEX = the game's LEVEL_* enum (names at 0x00CC1BE0), which is also
  the campaign order: 0 haven_town_center, 1 haven_town_ridge, 2
  haven_town_defense, 3 haven_traversal_boat, 4 stlouis_rescue, 5
  stlouisambush_01, 6 mine_town_approach, 7 mine_traversal_train, 8
  penn_prison_arena, 9 new_york_approach, 10 new_york_terraformer. [sure:
  a new game opens haven_town_center first in the port's logs; the save
  taken in "Haven, OK - Ridge" holds 1; chapter numbers in each level's
  levelconfig.lua rise in this order]
  CHECKPOINT INDEX = position of the define_checkpoint() call in the level's
  levelconfig.lua (inside its level_cached.psarc); the table below is copied
  from the disc. [sure: level 0 has 9, and a finished level 0 has exactly 9
  entries >= 0 followed by FE]

WHAT --set-level DOES: sets P+0x7C / P+0x80, sets the level's bit in P+0x88,
marks the checkpoints below the chosen one as finished (so the lobby's own
validity test accepts the pair), optionally sets the difficulty, and
recomputes the checksum. Inventory is left as it is, so Continue enters the
level with whatever the source save carried. --unlock-all additionally sets
all 11 level bits and marks every checkpoint of every level finished (what a
completed campaign looks like), which opens the whole level/checkpoint select.
NOT VERIFIED IN A RUN: this tool was written from static analysis only.

WHERE THE FILE GOES: the game keeps TWO save folders and alternates between
them, <hdd0>/home/00000001/savedata/BCUS98176_SAVE_0/ and .../BCUS98176_SAVE_0_/
(the port's log shows the boot-time load reading BCUS98176_SAVE_0_). Put the
same edited GAME.SAV in both; PARAM.SFO / PARAM.PFD / ICON0.PNG stay as they
are (the list subtitle will still name the old place). In memory the loaded
save sits, header included, at guest 0x011CB1E0 + slot * 0x7E70 (slot 0 for
the first signed-in user: func_003D7370), so level = 0x011CDE40, checkpoint =
0x011CDE44, mask = 0x011CDE4C, table = 0x011CDE4E.
"""
import argparse
import struct
import sys
import zlib

SIZE = 0x7E70
BODY, BODY_LEN = 0x20, 0x7E48
MAGIC, VERSION, STAMP = 0x49475344, 0x00092406, 0x20100812
P = 0x2BE4
O_LEVEL, O_CP, O_CNT, O_DIFF, O_MASK, O_TABLE = P + 0x7C, P + 0x80, P + 0x84, P + 0x85, P + 0x88, P + 0x8A
NLEV, NCP = 11, 64
DIFFS = ['casual', 'normal', 'difficult', 'superhuman']

# (folder name, [checkpoint names in define_checkpoint order])
LEVELS = [
    ('haven_town_center', ['htc_training', 'htc_training_post_intro', 'htc_start', 'htc_bowling',
                           'htc_mainstreet', 'htc_stalker', 'htc_outskirt_basement', 'htc_outskirt',
                           'htc_garage']),
    ('haven_town_ridge', ['START', 'FARM', 'BACKYARD', 'GULCH', 'MARSH', 'DEPOT', 'DEPOT_2', 'BRIDGE']),
    ('haven_town_defense', ['htd_start', 'htd_start_no_intro', 'htd_junkyard', 'htd_junkyard_wave2',
                            'htd_longleg_intro', 'htd_back_to_mainstreet', 'htd_mainstreet',
                            'htd_mainstreet_mid', 'htd_hulk_fight']),
    ('haven_traversal_boat', ['START', 'KRAKEN', 'ICE_INTRO', 'MOTEL', 'MOTEL_POST_CINEMATIC', 'TOWN',
                              'ICE_TOWN', 'DOCKS', 'DOCKS_POST_CINEMATIC', 'BRIDGE', 'OUTSKIRTS',
                              'OUTSKIRTS_FAR', 'CITY']),
    ('stlouis_rescue', ['SLR_START', 'COALTOWER', 'POWERPLANT_OUTSIDE', 'POWERPLANT_START',
                        'POWERPLANT_1ST_FLOOR', 'POWERPLANT_2ND_FLOOR', 'TRAVERSAL', 'TRAVERSAL_BRIDGE',
                        'VTOLSTART', 'VTOLFIGHT', 'VTOLPILOT', 'BREWERYDEFENSE', 'BREWERYDEFENSE2',
                        'BREWERYESCAPE', 'SEWER_START', 'HULKSTART', 'HULKEND']),
    ('stlouisambush_01', ['START', 'AMBUSH', 'AMBUSH_2', 'AMBUSH_3', 'CHASE', 'MEET_SALLY', 'PALACE',
                          'APARTMENTS', 'SAFEROOM', 'ROOFTOPS', 'ROOFTOPS_2', 'WIDOWMAKER',
                          'WIDOWMAKER_TWO', 'WIDOWMAKER_THREE']),
    ('mine_town_approach', ['mta_sniper_intro', 'mta_forest', 'mta_mine_intro', 'mta_cliff',
                            'mta_mine_exit', 'mta_bridge_battle', 'mta_town_intro', 'mta_leech_intro',
                            'mta_post_leech_intro', 'mta_church', 'mta_town_2', 'mta_powerplant_entrance',
                            'mta_powerplant_fight', 'mta_post_powerplant', 'mta_complex', 'mta_complex_mid',
                            'mta_complex_transition', 'mta_complex_end', 'MTM00_START',
                            'MTM01_FaceFight_01', 'MTM03_RFL_01', 'MTM04_RFL_02', 'MTM05_FaceFight_02',
                            'MTM06_FaceFight_02_End', 'MTM07_RFL_03', 'MTM08_MineCartRide',
                            'MTM09_FaceFight_03', 'MTM10_FaceFight_Final']),
    ('mine_traversal_train', ['START', 'INTRO_1', 'INTRO_2', 'CAVERNS', 'VALLEY', 'VALLEY_POST_CINEMATIC',
                              'TRENCH', 'FOREST', 'BRIDGE', 'CRACKED_EARTH', 'RPG', 'WIDOWMAKERS']),
    ('penn_prison_arena', ['start', 'arena_battle_start', 'arena_battle_wardens', 'cellblock_a',
                           'cellblock_a2', 'cellblock_a_exit', 'showers', 'showers2', 'showers_exit',
                           'cellblock_b', 'cellblock_b2', 'cellblock_b_exit', 'arena_after_CBB',
                           'cafeteria', 'cafeteria2', 'cafeteria3', 'cafeteria_exit', 'pit', 'pit2',
                           'pit3', 'pit4', 'pit_exit', 'motorpool', 'motorpool2', 'boss_enter', 'boss']),
    ('new_york_approach', ['nya_level_start', 'washington_square_start', 'washington_square_mid_left',
                           'washington_square_mid_right', 'washington_square_end',
                           'washington_square_done', 'subway_start', 'subway_station', 'subway_tunnel',
                           'subway_done', 'subway_to_time_square_start', 'times_square_start',
                           'times_square_2', 'times_square_wm_dead', 'times_to_c130_start',
                           'c130_crash_start', 'c130_crash_mid', 'c130_crash_done', 'bunkers_start',
                           'bunkers_right_side_done_first', 'bunkers_left_side_done_first',
                           'bunkers_climax_left', 'bunkers_climax_right', 'bunkers_done',
                           'waste_land_wall_interior', 'waste_land_start', 'waste_land_mid',
                           'waste_land_end', 'crawl_sequence']),
    ('new_york_terraformer', ['START', 'PISTON_ROOM', 'COLD_LOCK_ROOM', 'MAINTENANCE_SPACE',
                              'GENERATOR_ROOM', 'SHIELD_WALL', 'CHASM', 'CATWALK_ROOMS', 'CAROUSEL_ROOM_1',
                              'CAROUSEL_ROOM_2', 'MAP_ROOM', 'SNIPERS_DEAD', 'SHIELD_CONTROL_LEFT_DOWN_1ST',
                              'SHIELD_CONTROL_RIGHT_DOWN_1ST', 'SHIELD_CONTROL_RIGHT_DOWN_2ND',
                              'SHIELD_CONTROL_LEFT_DOWN_2ND', 'BEAM_CANNON_ROOM', 'CORE_ROOM',
                              'CORE_ROOM_HALFWAY_1', 'CORE_ROOM_HALFWAY_2', 'CORE_ROOM_HALFWAY_3',
                              'CORE_ROOM_HALFWAY_4', 'CORE_ROOM_HALFWAY_5', 'CORE_ROOM_HALFWAY_6',
                              'CORE_ROOM_SHIELD_DOWN', 'CORE_ROOM_SHIELD_DOWN_2', 'CORE_DESTROYED']),
]


def crc(data):
    return ~zlib.crc32(bytes(data[BODY:BODY + BODY_LEN])) & 0xFFFFFFFF


def s8(b):
    return b - 256 if b > 127 else b


def load(path):
    d = bytearray(open(path, 'rb').read())
    if len(d) != SIZE:
        sys.exit(f'{path}: {len(d)} bytes, expected {SIZE}')
    m, v, st = struct.unpack_from('>III', d, 0)
    if (m, v, st) != (MAGIC, VERSION, STAMP):
        sys.exit(f'{path}: header {m:08X} {v:08X} {st:08X} is not IGSD 00092406 20100812')
    return d


def level_arg(s):
    try:
        n = int(s, 0)
    except ValueError:
        k = s.lower()
        if k.startswith('level_'):
            k = k[6:]
        k = k.replace('stlouis_ambush_01', 'stlouisambush_01')
        names = [n for n, _ in LEVELS]
        if k not in names:
            sys.exit(f'unknown level "{s}" (see --levels)')
        return names.index(k)
    if not 0 <= n < NLEV:
        sys.exit(f'level index {n} out of range 0..{NLEV - 1}')
    return n


def cp_arg(level, s):
    cps = LEVELS[level][1]
    try:
        n = int(s, 0)
    except ValueError:
        low = [c.lower() for c in cps]
        if s.lower() not in low:
            sys.exit(f'{LEVELS[level][0]} has no checkpoint "{s}" (see --levels)')
        return low.index(s.lower())
    if not 0 <= n < len(cps):
        sys.exit(f'{LEVELS[level][0]} has checkpoints 0..{len(cps) - 1}, not {n}')
    return n


def inventory(d, off):
    pairs = [struct.unpack_from('>HH', d, off + 4 * i) for i in range(12)]
    w = ' '.join(f'{i}:{a}/{b}' for i, (a, b) in enumerate(pairs) if (a, b) != (0xFFFF, 0xFFFF)) or '(empty)'
    return (f'weapon slots {w}; health {d[off + 0x30]}; sel {d[off + 0x31]:02X} {d[off + 0x32]:02X}; '
            f'counters {d[off + 0x33:off + 0x38].hex()}; flags {struct.unpack_from(">I", d, off + 0x38)[0]:08X}')


def info(path):
    d = load(path)
    stored, calc = struct.unpack_from('>I', d, 0xC)[0], crc(d)
    print(f'{path}')
    print(f'  header    IGSD {VERSION:08X} {STAMP:08X}, rest {d[0x10:0x20].hex()}')
    print(f'  checksum  stored {stored:08X}, computed {calc:08X}: {"OK" if stored == calc else "MISMATCH (the game rejects this file)"}')
    lvl, cp = struct.unpack_from('>ii', d, O_LEVEL)
    diff = s8(d[O_DIFF])
    if lvl == -1:
        print('  resume    no campaign in progress (level -1)')
    elif 0 <= lvl < NLEV:
        cps = LEVELS[lvl][1]
        cpn = cps[cp] if 0 <= cp < len(cps) else '?? out of range'
        print(f'  resume    level {lvl} {LEVELS[lvl][0]}, checkpoint {cp} {cpn}'
              + ('   (0/0 = the game treats this as a new game)' if lvl == 0 and cp == 0 else ''))
    else:
        print(f'  resume    level {lvl} ?? out of range, checkpoint {cp}')
    print(f'  difficulty {diff} {DIFFS[diff] if 0 <= diff < 4 else "??"};  counter P+0x84 = {d[O_CNT]};  P+0x78 = {d[P + 0x78:P + 0x7C].hex()}')
    mask = struct.unpack_from('>H', d, O_MASK)[0]
    print(f'  level select mask {mask:04X}: ' + (', '.join(f'{i} {LEVELS[i][0]}' for i in range(NLEV) if mask >> i & 1) or 'none'))
    print('  checkpoints finished (best difficulty; . = not yet, - = no such checkpoint):')
    for i, (name, cps) in enumerate(LEVELS):
        row = [s8(b) for b in d[O_TABLE + i * NCP:O_TABLE + (i + 1) * NCP]]
        txt = ''.join('.' if v == -1 else '-' if v == -2 else str(v) if 0 <= v <= 9 else '?' for v in row)
        done = sum(1 for v in row[:len(cps)] if v >= 0)
        print(f'    {i:2} {name:22} {done:2}/{len(cps):2}  {txt[:max(len(cps), 1)]}|{txt[len(cps):].rstrip(".") or ""}')
    print(f'  inventory P1: {inventory(d, P)}')
    print(f'  inventory P2: {inventory(d, P + 0x3C)}')
    print(f'  init flag (0x7E68): {d[0x7E68]}')
    return 0 if stored == calc else 1


def mark(d, level, upto, diff, close=False):
    """Checkpoints [0, upto) of `level` become finished at >= diff."""
    base = O_TABLE + level * NCP
    for i in range(upto):
        if s8(d[base + i]) < 0:
            d[base + i] = diff
    if close:
        for i in range(upto, NCP):
            d[base + i] = 0xFE


def main():
    ap = argparse.ArgumentParser(description='Resistance 3 GAME.SAV inspector/editor', epilog='see the docstring for the format')
    ap.add_argument('--info', metavar='GAME.SAV')
    ap.add_argument('--levels', action='store_true', help='list level and checkpoint indices')
    ap.add_argument('--set-level', metavar='NAME|INDEX')
    ap.add_argument('--checkpoint', metavar='NAME|N', default='0')
    ap.add_argument('--difficulty', type=int, choices=range(4), metavar='0-3')
    ap.add_argument('--unlock-all', action='store_true')
    ap.add_argument('--fix-crc', action='store_true', help='only recompute the checksum')
    ap.add_argument('files', nargs='*', metavar='IN OUT')
    a = ap.parse_args()

    if a.levels:
        for i, (name, cps) in enumerate(LEVELS):
            print(f'{i:2} {name}')
            for j, c in enumerate(cps):
                print(f'      {j:2} {c}')
        return 0
    if a.info:
        return info(a.info)
    if a.set_level is None and not a.unlock_all and a.difficulty is None and not a.fix_crc:
        ap.error('nothing to do')
    if len(a.files) != 2:
        ap.error('need IN and OUT')
    src, dst = a.files
    import os
    if os.path.exists(dst) and os.path.samefile(src, dst):
        sys.exit('OUT must not be IN')
    d = load(src)
    if struct.unpack_from('>I', d, 0xC)[0] != crc(d):
        print(f'warning: {src} has a bad checksum to begin with', file=sys.stderr)

    if a.difficulty is not None:
        d[O_DIFF] = a.difficulty
    diff = s8(d[O_DIFF])
    if not 0 <= diff < 4:
        diff = 1
        d[O_DIFF] = diff
    if a.set_level is not None:
        lvl = level_arg(a.set_level)
        cp = cp_arg(lvl, a.checkpoint)
        struct.pack_into('>ii', d, O_LEVEL, lvl, cp)
        d[O_CNT] = 0
        struct.pack_into('>H', d, O_MASK, struct.unpack_from('>H', d, O_MASK)[0] | 1 << lvl)
        mark(d, lvl, cp, diff)
        if lvl == 0 and cp == 0:
            print('note: level 0 checkpoint 0 is what the game calls a new game', file=sys.stderr)
    if a.unlock_all:
        struct.pack_into('>H', d, O_MASK, (1 << NLEV) - 1)
        for i, (_, cps) in enumerate(LEVELS):
            mark(d, i, len(cps), diff, close=True)
    struct.pack_into('>I', d, 0xC, crc(d))
    with open(dst, 'wb') as f:
        f.write(d)
    print(f'wrote {dst}')
    return info(dst)


if __name__ == '__main__':
    sys.exit(main())
