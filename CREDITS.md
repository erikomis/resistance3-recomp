# Credits

🌐 **English** · [Português (BR)](CREDITS.pt-BR.md)

This port only exists because of the work below. Thank you all.

## Toolkit

- **[ps3recomp](https://github.com/sp00nznet/ps3recomp)** — Ned Heller
  ([@sp00nznet](https://github.com/sp00nznet)) and
  [contributors](https://github.com/sp00nznet/ps3recomp/blob/master/CONTRIBUTORS.md).
  The runtime, the HLE libraries, the PPU and SPU lifters, the Metal backend,
  the FFmpeg-backed cellVdec, and the project template this port's
  `main.cpp`, `stubs.cpp`, `CMakeLists.txt` and `config.toml` start from. The
  port builds against v0.17.0 (`a6d76c8`). MIT.

## Toolkit fixes from upstream pull requests

The toolkit patch (the Resistance: Fall of Man one, inside the Resistance 2
one this port's patch starts from) carries these ps3recomp pull requests (some adapted to v0.17.0 or
to that port), with their authors kept in the patch headers:

- **undecuple** — the console's licence area, North America (it fixed the
  overlapping legal-screen text; [#429](https://github.com/sp00nznet/ps3recomp/pull/429)); XInput loaded at run time on
  Windows ([#494](https://github.com/sp00nznet/ps3recomp/pull/494)).
- **n0madic** ([@n0madic](https://github.com/n0madic)) — vertex-program branch
  bits ([#485](https://github.com/sp00nznet/ps3recomp/pull/485)); `WPOS` on antialiased render targets ([#446](https://github.com/sp00nznet/ps3recomp/pull/446)).
- **Will Tekulve** ([@tekulvw](https://github.com/tekulvw)) — the fs fd-table
  race ([#430](https://github.com/sp00nznet/ps3recomp/pull/430)); linear A8R8G8B8 fast decode ([#432](https://github.com/sp00nznet/ps3recomp/pull/432)); the texture-slot
  memo ([#438](https://github.com/sp00nznet/ps3recomp/pull/438)); the SPU decrementer on the raw clock ([#451](https://github.com/sp00nznet/ps3recomp/pull/451)); the yield
  on repeated SPU DMA ([#448](https://github.com/sp00nznet/ps3recomp/pull/448)); small SPU DMA savings ([#453](https://github.com/sp00nznet/ps3recomp/pull/453), [#454](https://github.com/sp00nznet/ps3recomp/pull/454), [#455](https://github.com/sp00nznet/ps3recomp/pull/455)).
- **Heitor Mendonça** — repositioning a file when its fd switches between
  reading and writing ([#456](https://github.com/sp00nznet/ps3recomp/pull/456)).
- **Ryan Bagas** — the `stwcx.` reservation re-check ([#522](https://github.com/sp00nznet/ps3recomp/pull/522)).
- **Noah Peterson** ([@NoahBPeterson](https://github.com/NoahBPeterson)) —
  real-time pacing of the POSIX audio mixer (from the inFAMOUS 2 work).
- **erikomis** — `getenv` looked up once per call site ([#515](https://github.com/sp00nznet/ps3recomp/pull/515)); audio volume
  and output device; the opt-in `usleep` spin.

The Resistance 2 changes add:

- **Ryan Setyanto** ([@rigaz29](https://github.com/rigaz29)) — an SPU PUT's
  first 128 bytes written last ([#632](https://github.com/sp00nznet/ps3recomp/pull/632), ported).

## The ports it follows

- **[resistance2-recomp](https://github.com/erikomis/resistance2-recomp)** —
  the author's Resistance 2 port. This repository starts as a copy of it: the
  toolkit patch, `tools/` (install, rebuild, play, deps, decryption, the
  job-module lift), the runner in `port/`, the launcher, and the raw-SPU,
  policy-module and relocatable-module work Resistance 3 will follow.
- **[resistance-recomp](https://github.com/erikomis/resistance-recomp)** —
  the author's Resistance: Fall of Man port on the same toolkit. Its toolkit
  patch is the base of the Resistance 2 one, and the repository layout, the
  toolkit-patch approach (`tools/setup_toolkit.sh`), the rebuild and play
  scripts, the window launcher, the SPU job-module tools
  (`tools/extract_jobmods_elf.py`) and the raw-SPU and policy-module work
  come from there.
- **[infamous2-recomp](https://github.com/erikomis/infamous2-recomp)** — the
  author's inFAMOUS 2 port, where that layout, the job-module extraction and
  the fix for running the guest off the macOS main thread started. It in turn
  stands on [NoahBPeterson](https://github.com/NoahBPeterson/ps3recomp)'s
  inFAMOUS 1 fork of ps3recomp.

## Community patches

- RPCS3's `patch.yml` entries for Resistance 3: **Whatcookie** and **boma**
  ("Unlock FPS") and **illusion** ("Extended FOV"), carried over by
  `port/patches.cpp` and `tools/r3_survey.py`.

## Tools

- [RPCS3](https://github.com/RPCS3/rpcs3) — its public key table
  (`tools/fetch_keys.py`) and `rpcs3 --decrypt` for the player's own
  `EBOOT.BIN`, the PPU hash its patches are keyed by, and the behaviour
  reference for the toolkit.
- [FFmpeg](https://ffmpeg.org/) (libavcodec, libavutil; LGPL/GPL, loaded at
  runtime from the player's own Homebrew install, not shipped) — video decoding.
- [SDL2](https://www.libsdl.org/), [glslang](https://github.com/KhronosGroup/glslang),
  [SPIRV-Cross](https://github.com/KhronosGroup/SPIRV-Cross),
  [SPIRV-Tools](https://github.com/KhronosGroup/SPIRV-Tools), CMake, Ninja.
- [SMAA](https://github.com/iryoku/smaa) — Jorge Jimenez, Jose I. Echevarria,
  Belen Masia, Fernando Navarro and Diego Gutierrez: the anti-aliasing behind
  `PS3_AA=smaa` (`third_party/smaa` in the toolkit patch, with its licence
  file). MIT.
- The [PS3 Developer Wiki](https://www.psdevwiki.com/ps3/).

## Game

Resistance 3 © 2011 Sony Interactive Entertainment LLC, developed by
Insomniac Games. This project is not affiliated with or endorsed by Sony or
Insomniac, and contains no game or firmware data. To use it you need a
legitimate copy of the game (the `BCUS98176` or `BCES01118` disc).
