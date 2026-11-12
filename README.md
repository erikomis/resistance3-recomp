# Resistance 3 — static recompilation for PC (macOS)

🌐 **English** · [Português (BR)](README.pt-BR.md)

A native port of **Resistance 3** (PS3, disc `BCUS98176`; the European disc
is `BCES01118`) to **macOS/arm64**, built with static recompilation: the
game's PowerPC and SPU code is translated to C/C++ and compiled into a native
executable, with graphics on Metal. It is not an emulator.

The third port in the series, after the author's
[Resistance: Fall of Man](https://github.com/erikomis/resistance-recomp) and
[Resistance 2](https://github.com/erikomis/resistance2-recomp) ports, on
[ps3recomp](https://github.com/sp00nznet/ps3recomp). Resistance 3 is the same
Insomniac engine three years on, so this port starts from the Resistance 2
port's toolkit patch, scripts, runner and launcher. See
[CREDITS.md](CREDITS.md).

> [!WARNING]
> **Not playable yet.** The game boots to its first screen and stops at the
> loading movie that follows it. What comes next is in
> [ROADMAP.md](ROADMAP.md).
>
> **This repository contains no game data, no firmware, no Sony keys and
> nothing translated from them.** Everyone generates all of that locally from
> their own legitimate copy. A fan project, not affiliated with Sony
> Interactive Entertainment or Insomniac Games.

## Status

As of 2026-11-11: the 01.00 disc is lifted and built; the first boot copies
1.5 GB to the HDD and shows a 30 fps screen that waits for X, and the loading
movie after it stalls (its Bink jobs on Insomniac's igPm job system never
finish).

- The toolkit: ps3recomp v0.17.0 (`a6d76c8`) plus
  `patches/ps3recomp-a6d76c8-resistance3.patch`, the Resistance 2 patch with
  one change so far (`PS3_GAMEDATA_MARKERS`, below).
- `tools/r3_survey.py`, new: identifies the EBOOT by RPCS3's PPU hash
  (01.00 disc or 01.05 update, USA or Europe), and lists what the earlier
  ports had to find by hand: the embedded SPU ELFs, the WWS job modules, the
  relocatable SPU blobs, the Insomniac pieces named in strings
  (`igInitRawSpu`, `Wws_Job`, Bink), any second executable, and the words the
  community FPS/FOV patches change. Checked against the Resistance 2 EBOOT
  (it finds the 3 SPU ELFs, 29 job modules and 142 relocatable blobs that
  port documents, and RPCS3's hash for it).
- The community patches RPCS3 ships for this game ("Unlock FPS" by
  Whatcookie and boma, "Extended FOV" by illusion) are wired in
  (`RES_UNLOCK_FPS`, `RES_FOV`), to be generated from the EBOOT.

## How it works

The same pipeline as the earlier ports:

1. The disc's `EBOOT.BIN` (a SELF) is decrypted to an ELF
   (`tools/decrypt_self.py`, keys from RPCS3's public source; RPCS3 itself as
   the fallback).
2. The toolkit's `ppu_loader.py` finds the functions and imports, and
   `ppu_lifter.py` translates every PowerPC function to C++.
3. The SPU programs are lifted to C: the SPU ELFs the build finds by itself,
   the WWS job modules (`tools/regen_r3_jobmods.sh`), and the raw SPU code
   the survey points at (port-specific `tools/prepare_r3_*.py`, written as
   they are found).
4. CMake builds that with the toolkit's runtime (HLE firmware libraries,
   lv2 syscalls, SPURS, the RSX→Metal backend) and `port/` (the runner, the
   patches) into `build/BCUS98176/ResistanceRecomp`.

## Building from source

### What you need

- An Apple-silicon Mac (macOS with Metal).
- Your own **Resistance 3 disc** (`BCUS98176`), dumped to an image and
  mounted, or extracted to `game/BCUS98176/` (the folder that holds
  `PS3_GAME/`). For the European disc set `RES_TITLE_ID=BCES01118`.
- The Xcode Command Line Tools. Everything else (CMake, Ninja, Python, SDL2,
  glslang, SPIRV-Cross, SPIRV-Tools, FFmpeg) is installed without Homebrew by
  `tools/install.sh` (`tools/bootstrap_deps.sh`), or from Homebrew:

```sh
brew install cmake ninja sdl2 glslang spirv-cross spirv-tools ffmpeg python@3.12
```

### Building

```sh
git clone https://github.com/erikomis/resistance3-recomp.git
cd resistance3-recomp
tools/install.sh            # deps, toolkit, venv, decrypt, survey, analyse, lift, spu, build
```

or, with the tools already installed, `tools/rebuild.sh`, whose steps run
alone by name too (`tools/rebuild.sh survey`, `tools/rebuild.sh lift build`):

| Step | What it does |
| --- | --- |
| `toolkit` | `tools/setup_toolkit.sh`: clones ps3recomp to `./ps3recomp`, checks out `a6d76c8`, applies the patch |
| `decrypt` | `EBOOT.BIN` → `game/<title>/EBOOT.elf` (and `PARAM.SFO` beside it); `RES_EBOOT_BIN=<path>` decrypts another one, e.g. the 01.05 update's |
| `survey` | `tools/r3_survey.py` → `out/survey/<title>.txt` and `.json` |
| `analyse` | `ppu_loader.py` → `analysis/<title>/` |
| `lift` | `ppu_lifter.py` → `recompiled/<title>/` (24 chunks; `JOBS` limits parallelism), with `port/patches/eboot_<version>.insn.json` when it exists |
| `spu` | `tools/regen_r3_jobmods.sh` and every `tools/prepare_r3_*.py` → `port/spu/` |
| `build` | CMake + Ninja → `build/<title>/ResistanceRecomp` and `build/<title>/Resistance` |

The disc is found through `PS3_VFS_ROOT`, `game/<title>/PS3_GAME`, or a
volume under `/Volumes` whose `PARAM.SFO` names the title (`tools/env.sh`).

### The 01.05 update

RPCS3's community patches exist for both 01.00 (the disc) and 01.05 (the last
update). To port the update's executable, install the update in RPCS3 and
point the decrypt step at its EBOOT:

```sh
rm -f game/BCUS98176/EBOOT.elf
RES_EBOOT_BIN=~/Library/Application\ Support/rpcs3/dev_hdd0/game/BCUS98176/USRDIR/EBOOT.BIN \
    tools/rebuild.sh decrypt survey analyse lift spu build
```

### The FPS and FOV patches

Once the EBOOT is decrypted:

```sh
tools/r3_survey.py game/BCUS98176/EBOOT.elf --write-insn port/patches
tools/rebuild.sh lift build
```

writes `port/patches/eboot_<version>.insn.json` (the code words, lifted in
both forms) and `eboot_<version>.words.h` (the original words
`port/patches.cpp` checks, and the data words it writes). Then
`RES_UNLOCK_FPS=1` and `RES_FOV=0.7` work with `tools/play.sh`.

## Playing

The launcher in [`launcher/`](launcher/README.md) installs, rebuilds and
plays without a terminal (it is the Resistance 2 port's, renamed). From a
terminal, with the disc mounted and a controller connected:

```sh
tools/play.sh
```

Saves, the HDD folders and the log (`last.log`) live in
`~/Library/Application Support/resistance-recomp-3/` (`RES_DATA`).

### Environment

| Variable | Effect |
| --- | --- |
| `RES_TITLE_ID` | `BCUS98176` (default) or `BCES01118` |
| `PS3_VFS_ROOT` | the folder holding `PS3_GAME/` |
| `RES_EBOOT_BIN` | the `EBOOT.BIN` the decrypt step reads |
| `RES_DATA` | saves, HDD folders and the log |
| `RES_UNLOCK_FPS=1` | "Unlock FPS"; the frame rate follows the vblank rate (`PS3_VBLANK_HZ`, default 62.5; patch.yml advises against more than 60–75) |
| `RES_FOV=<f>` | "Extended FOV" (RPCS3's value is 0.7) |
| `RES_HTTP_POLL_COMPAT=0` | `cellHttpClientPollConnections` back to the toolkit default (carried from Resistance 2, where the default made the HTTP thread spin) |
| `PS3_GAMEDATA_MARKERS` | the files whose presence means the first boot's HDD install is done (`:`-separated, relative to the game-data folder); the default is Resistance 2's pair |

The runner keeps Resistance 2's defaults (SPURS kernel-style scheduling,
`sys_lwcond` events, a 50 µs RSX wake-up, stereo with a limiter); each has a
switch to turn it off for comparison, documented in `port/main.cpp` and
`tools/play.sh`.

## Updating the toolkit patch

Change the toolkit in `./ps3recomp`, then:

```sh
tools/export_toolkit_patch.sh
```

regenerates `patches/ps3recomp-a6d76c8-resistance3.patch` from it (never
exporting game-derived files) and checks it applies to a clean `a6d76c8`.

## Layout

| Path | What |
| --- | --- |
| `port/` | the runner (`main.cpp`), patches and hooks (`patches.cpp`, `stubs.cpp`), `CMakeLists.txt` |
| `port/patches/` | generated FPS/FOV patch words (`tools/r3_survey.py --write-insn`) |
| `patches/` | the toolkit patch |
| `tools/` | install, rebuild, play, survey, SPU and toolkit scripts |
| `launcher/` | the desktop app (Tauri) |
| `game/`, `analysis/`, `recompiled/`, `build/`, `out/`, `ps3recomp/` | generated locally, never committed |

## License

MIT; see [LICENSE](LICENSE) and [CREDITS.md](CREDITS.md).
