# Roadmap

🌐 **English** · [Português (BR)](ROADMAP.pt-BR.md)

Status of the native Resistance 3 (`BCUS98176`) port to macOS/arm64 and what
comes next. Same layout as the Resistance: Fall of Man and Resistance 2
roadmaps. `[x]` = done and verified; `[ ]` = to do; "(in progress)" = being
worked on.

## Status at a glance (2026-11-11)

- **Boots to its first screen.** The 01.00 disc is decrypted, surveyed,
  lifted (35,741 functions) and built; the first boot copies its 1.5 GB to
  the HDD and shows a 30 fps screen that waits for X. Past X the loading
  movie starts and the game stops: the Bink jobs on queues 3 and 4 of the
  igPm job system never finish (next).

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
- [x] The disc (BCUS98176 01.00, RPCS3 hash `PPU-502feb23…`): decrypted,
  surveyed (3 SPU ELFs, 3 job modules, 18 relocatable blobs; `game.self` is
  the EBOOT again, so one executable), lifted (35,741 functions) and built.
- [x] The Edge zlib inflate task (the `.psarc` decompressor) is a stripped
  SPU ELF whose text segment ends in data: the toolkit's SPU generator takes
  `--text-end` per image (`port/CMakeLists.txt` sets it), so it is lifted.
- [x] Both raw SPURS policy modules lifted: Wws_Job (`tools/prepare_r3_job_pm.py`)
  and Insomniac's igPm (`tools/prepare_r3_ig_pm.py`, new since Resistance 2).
- [x] igPm runs on the five SPUs of the "ig" instance, each serving the job
  queue whose number the game writes to its SNR1. Toolkit: SPU thread ids
  for SPURS SPUs in `cellSpursGetInfo` and `sys_spu_thread_write_snr` on
  them; a policy module's lift is not used once code is loaded over it.
  Runner: `SPURS_WIDEN=0` and `SPU_CH_BLOCK=1` by default.
- [x] `tools/rebuild.sh` compiles one chunk per 10 GB of RAM at low priority
  (Ninja's default froze a 24 GB Mac).
- [x] The first boot's HDD copy (sound banks, 1.5 GB, 5,218 files) and the
  first screen at 30 fps.

## Next

- [ ] The loading movie: the Bink jobs igPm runs on queues 3 and 4 (loaded
  over the policy module, so interpreted) never complete, and the main
  thread waits on them in `SpuJob::SyncJob`.
- [ ] Relocatable SPU modules: 18 DEADDEAD blobs as in Resistance 2, plus
  ila-headed modules in a newer format (tables `igNav` and others).
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
