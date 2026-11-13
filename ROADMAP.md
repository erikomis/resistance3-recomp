# Roadmap

🌐 **English** · [Português (BR)](ROADMAP.pt-BR.md)

Status of the native Resistance 3 (`BCUS98176`) port to macOS/arm64 and what
comes next. Same layout as the Resistance: Fall of Man and Resistance 2
roadmaps. `[x]` = done and verified; `[ ]` = to do; "(in progress)" = being
worked on.

## Status at a glance (2026-11-12)

- **Boots, plays movies, opens the menu and plays the first level.** The
  01.00 disc is lifted and built, and the player walks on the ground: ground
  probes return hits (4-18 per query) and the camera stays at floor height.
- Gameplay averages ~29 fps even with the Mac thermally throttled (it was
  18-20 there): igPm's job loop is lifted (`lift_r3_igjobs.py --loop`, now in
  `tools/rebuild.sh`); interpreted, it cleared every job's bss one quadword
  at a time, ~20 M interpreted steps/s. And a thread that only polls the
  timebase (the main thread waiting for its SPU jobs) sleeps 10 us per read
  after 2000 empty reads instead of holding a core at 100%
  (`PS3_TB_POLL_SLEEP_US`, 0 = off).
- Haven's streets: the RSX engine's texture cache holds 4096 textures
  (`PS3RECOMP_ENG_TEXCACHE_SLOTS`, port default; it was 1024). At 1024 it
  evicted and re-uploaded ~9,500 textures every 120 frames outdoors (frames
  of 300-800 ms, 6 fps), and evicting in the middle of a frame is what made
  the pause menu's background vertical garbage. Lines, line strips and line
  loops are rebuilt into a line list bounded by the restart cuts
  (`PS3RECOMP_ENG_LINE_REBUILD`, on): the power lines, indexed line strips,
  used to join each wire to the next across the sky.
- Gameplay at the 30 fps cap in Haven combat (median 29.9 fps; the RSX
  thread's CPU time per frame 44 -> 22 ms over the day): the RSX engine skips
  the legacy state shadow nobody reads, looks textures up through a hash
  index, copies only the vertex constants that changed, hands remapped
  triangle lists to Metal as indices, and more (knobs: `GCM_STATE_SHADOW`,
  `PS3RECOMP_ENG_TEXSLOT_INDEX`, `PS3RECOMP_ENG_VSCB_SYNC`,
  `PS3RECOMP_ENG_ADDR_FILTER`). A/B in the same fight: 22.9 fps with them off.
- SPU code interpreted in gameplay fell from ~2.5 M to ~0.0-0.1 M steps/s:
  the runtime keeps 16 resident lifted regions with least-recently-entered
  replacement (the physics sub-module 0x00DB2D80 lost its slot to stale
  ones), checks that a region still holds its code before dispatching into
  it, and routines a WWS job module calls only through a function-pointer
  table now get lifted entries. `SPU_RESIDENT_POLICY=old`,
  `SPU_RESIDENT_VERIFY=0`, `SPU_RESIDENT_SLOTS`, `SPU_NO_ENTRY` for A/B.
- Pause menu background: the game stashes the frozen frame in its half-res
  depth buffer's memory; the engine retired that stash falsely, reused the
  dead slot as live and restored from the depth buffer (depth drawn as
  colour). Fixed in the engine (a retired slot is never returned as live, a
  guest copy newer than both targets is the blit source, the engine's own
  stores no longer retire, the depth copy covers the whole target).
- Intermittent gameplay hang (main thread calling a virtual method through a
  zeroed table ~50 s after a level starts): the GCM FIFO walker followed a
  one-off command list the game frees right after the RSX returns from it,
  decoded the freed bytes as NV4097 state, bound a garbage render target and
  the engine stored it with no bounds check, wrapping into the game's .bss.
  A watcher thread now snapshots the word at the walker's resting point the
  moment `put` moves (`GCM_PUT_WATCH`), so a reclaimed link is still
  followed; a store outside RSX memory is refused
  (`PS3RECOMP_ENG_STORE_BOUNDS`) and a tripwire logs "FIFO desync suspect".
- Ported from upstream ps3recomp's open PRs (triaged against R3's import
  table): event queues published under their lock (#759), stale HLE
  in-flight slot (#776), SPU drain return points cleared on restart (#761),
  one reservation context per thread (#758: the registry filled after ~127
  thread starts), POSIX detach of a finished thread (#717), no 3 s retry on
  directory opens (#768), short cellFsWrite reports EIO (#705), 40 GiB free
  space as RPCS3 reports (#692), a 7-op NEON shufb (#716), opt-in live
  reservation holder counts (#731, `PS3RECOMP_SPU_LIVE_HOLDERS`); RSX:
  report-stamp scale (#753, `PS3RECOMP_GCM_REPORT_BUSY_SCALE`,
  default unchanged), 16384 Metal records a frame (#719; R3 filled 8192
  64+ times a run), per-unit texture decode memo (#762), opt-in single
  present (#721), unmap rounding (#704), TXD (#701). #675 (new-style JUMP)
  was tried and reverted: it broke R3's FIFO walk (a hang after a desync).
  #757 (branch bits read at run time) was reverted too: it changes every
  vertex program's translation, so a player's whole shader cache went stale
  and recompiled during play (127 builds queued, 8-20 fps, freezes).
- Shader stalls in new areas: every pipeline built at once is charged to
  the compile budget (functions and pipeline state), not only disk-cache
  functions (`PS3_SHADER_SYNC_BUDGET_ALL`, on). With an empty shader cache
  in the same fight the worst RSX pass went from 3.07 s to 198 ms.
- Black patches on the ground in Haven: decals light themselves from 16x16
  render targets; when the target table filled, those were evicted without
  their content and the decals multiplied by zero. Small targets are now
  stored to guest memory before eviction when that memory is still theirs
  (`PS3RECOMP_ENG_EVICT_STORE_SMALL`, default 4096 bytes).
- Green and dark translucent wedges reaching into the sky (ribbons and
  billboards near effects and the Stalker): RSX vertex arrays with stride 0
  were fetched as tightly packed arrays (OpenGL's meaning). On the RSX stride
  0 repeats one element for every vertex; R3 keeps one record per draw that
  way, so each vertex read the next strands' records
  (`PS3RECOMP_ENG_STRIDE0=packed` restores the old reading). The render-target
  table has 512 slots by default (`PS3RECOMP_ENG_SURFACE_SLOTS`; 128 evicted
  thousands of targets a session).
- Fixed collision: CollBroad leaves its candidate list in its own local
  store and CollNarrow GETs it through the SPU thread LS window
  (EA 0xF0000000 + n*0x100000, here 0xF0007410). The MFC read that EA as
  plain guest memory (zeros), so every probe tested 0 triangles and the
  player fell through the world. The toolkit now serves the window from the
  SPURS lane's context (`spu_ls_window_copy`, spurs_policy.c). Found with an
  offline replay of CollNarrow from a live snapshot (`R3_COLL_SNAPSHOT`,
  `R3_COLL_SNAPSHOT_LR=other`).
- Fixed SPU fast dispatch: jobs that overwrite a policy module now use the
  resident code, including relocatable modules. A regression test against
  the real registry fails before the fix and passes afterwards. This fix
  alone does not resolve gameplay collision.
- A/B: interpreting CollBroad, CollNarrow and their ten submodules also
  reproduces the fall. A fresh HDD1 does not resolve it either; the main
  installed HDD0 archive has the same SHA256 as the disc: this is what
  pointed at the runtime rather than the lift.

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

- [x] The loading movie (igBink jobs, lifted with `tools/lift_r3_igjobs.py`),
  the first autosave, the lobby (front end) and, pressing X through it, the
  first level (`haven_town_ridge`) at 30 fps.
- [x] Relocatable SPU modules: 184 modules lifted by
  `tools/lift_r3_relocmods.py` (151 ig and 33 DEADDEAD).
- [ ] First boot: logos, the auto-save notice, input (Resistance 2 needed a
  front-end port-0 hook), menus.
- [ ] The first boot's HDD install: which files Resistance 3 writes, for
  `PS3_GAMEDATA_MARKERS` and the launcher's `HDD_INSTALL_MARKERS`; the save
  slot names for the saves manager.
- [x] Bink movies on the igPm queues; 3D cinematics also render.
- [x] Player collision in the first level (SPU LS window).
- [ ] Validate the campaign at 30 fps throughout (gameplay runs at 25-30 fps
  with some SPU code still interpreted).
- [ ] `tools/r3_survey.py --write-insn` and `RES_UNLOCK_FPS=1` / `RES_FOV` in
  play; then 60 fps.
- [ ] Re-measure the disk space a full install takes (the launcher and
  `tools/install.sh` ask for 8 GB until then).
- [ ] Publish the repository (`erikomis/resistance3-recomp`, the name the
  launcher's updater and its sources clone already use) and the launcher's
  first release.
- [ ] RecompLauncher: the profile (`recomplauncher.json`), the launcher's
  headless `--prepare` and `scripts/package-recomplauncher.sh` are in; a
  release with that zip attached, a full prepare on a clean Mac, and the
  listing on recomplauncher.com are still to do (launcher README,
  "RecompLauncher").

## Later

- [ ] Online multiplayer. Sony closed Resistance 3's servers with the rest of
  the series; the Resistance 1 and 2 ports carry the groundwork in their
  toolkit patch (real sockets `PS3_NET_ONLINE=1`, `PS3_NET_DNS`, a local PSN
  sign-in `PS3_NP_SIGNIN=1`), all off by default and in this patch too.
  The campaign comes first.
