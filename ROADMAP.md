# Roadmap

🌐 **English** · [Português (BR)](ROADMAP.pt-BR.md)

Status of the native Resistance 3 (`BCUS98176`) port to macOS/arm64 and what
comes next. Same layout as the Resistance: Fall of Man and Resistance 2
roadmaps. `[x]` = done and verified; `[ ]` = to do; "(in progress)" = being
worked on.

## Status at a glance (2026-11-11)

- **Set up, waiting for the disc.** The scripts, the toolkit patch, the
  runner and the launcher are in place and build; nothing of Resistance 3 has
  been decrypted, lifted or booted.

## Done

- [x] Repository layout from the Resistance 2 port: `tools/` (install,
  rebuild, play, deps without Homebrew, decryption without RPCS3), `port/`
  (runner, patches, CMake), `launcher/`, bilingual docs, MIT license.
- [x] The toolkit: ps3recomp v0.17.0 (`a6d76c8`) plus the Resistance 2 patch
  as `patches/ps3recomp-a6d76c8-resistance3.patch`; `tools/setup_toolkit.sh`
  applies it and `tools/export_toolkit_patch.sh` re-exports it (round trip
  checked).
- [x] `PS3_GAMEDATA_MARKERS` in the toolkit's `cellGame.c`: the files that
  mark the first boot's HDD install as done were Resistance 2's, fixed in the
  code.
- [x] `port/CMakeLists.txt` configures and `main.cpp`, `patches.cpp`,
  `stubs.cpp` and the window host compile against the patched toolkit
  (checked with the Resistance 2 lift as a stand-in); `patches.cpp` rebuilds
  when generated patch words appear or go.
- [x] The launcher renamed for Resistance 3 (`BCUS98176`,
  `resistance-recomp-3`, `io.github.erikomis.resistance3recomp`):
  typecheck, frontend build and the Rust tests (59) pass.
- [x] `tools/r3_survey.py`: RPCS3's PPU hash (checked equal to RPCS3's for the
  Resistance 2 EBOOT) against the four known Resistance 3 executables
  (BCUS98176 / BCES01118, 01.00 / 01.05), PARAM.SFO, segments and sections,
  the TOC, embedded SPU ELFs, WWS job modules, DEADDEAD relocatable blobs,
  Insomniac strings, other executables, and the community patch words
  (`--write-insn`: the lift's `insn.json` and `patches.cpp`'s words).
- [x] `tools/regen_r3_jobmods.sh`: the generic 0xC0DEC0DE job-module lift.
- [x] RPCS3's "Unlock FPS" and "Extended FOV" for 01.00 and 01.05 wired into
  `port/patches.cpp` (`RES_UNLOCK_FPS`, `RES_FOV`), keyed to the words
  generated from the player's EBOOT.

## Next

- [ ] Dump the disc; `tools/install.sh` (or `tools/rebuild.sh toolkit
  decrypt survey`). Note the version (01.00 or 01.05) and the key revision
  (`tools/decrypt_self.py --info`).
- [ ] Read the survey: how many SPU ELFs, job modules and relocatable blobs;
  is there an `igInitRawSpu` loader and raw-SPU programs (Bink); is there a
  second executable (an exitspawn, as Resistance 1's `game.self`).
- [ ] Analyse and lift the EBOOT; compile and link everything (the lift will
  be larger than Resistance 2's ~41,500 functions).
- [ ] The raw SPU code, following Resistance 2's tools: the Wws_Job policy
  module (`prepare_r2_job_pm.py`), the raw-SPU loader and programs
  (`prepare_r2_rawspu_loader.py`, `prepare_r2_rawspu.py`), the relocatable
  modules (`lift_r2_relocmods.py`), as `tools/prepare_r3_*.py` and
  `tools/lift_r3_relocmods.py` with Resistance 3's addresses and fingerprints.
- [ ] First boot: logos, the auto-save notice, input (Resistance 2 needed a
  front-end port-0 hook), menus.
- [ ] The first boot's HDD install: which files Resistance 3 writes, for
  `PS3_GAMEDATA_MARKERS` and the launcher's `HDD_INSTALL_MARKERS`; the save
  slot names for the saves manager.
- [ ] Movies (Bink on a raw SPU in Resistance 2).
- [ ] New Game → the first level; then 30 fps throughout.
- [ ] `tools/r3_survey.py --write-insn` and `RES_UNLOCK_FPS=1` / `RES_FOV` in
  play; then 60 fps.
- [ ] Re-measure the disk space a full install takes (the launcher and
  `tools/install.sh` ask for 8 GB until then).
- [ ] Publish the repository (`erikomis/resistance3-recomp`, the name the
  launcher's updater and its sources clone already use) and the launcher's
  first release.

## Later

- [ ] Online multiplayer. Sony closed Resistance 3's servers with the rest of
  the series; the Resistance 1 and 2 ports carry the groundwork in their
  toolkit patch (real sockets `PS3_NET_ONLINE=1`, `PS3_NET_DNS`, a local PSN
  sign-in `PS3_NP_SIGNIN=1`), all off by default and in this patch too.
  The campaign comes first.
