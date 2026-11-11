# Launcher (Tauri)

A desktop app that takes the player from their own Resistance 3 disc
(BCUS98176) to "Play" without a terminal: it finds the port's builds and the
disc, mounts the disc image, keeps the game's settings, runs the install or
the rebuild with a progress bar and starts the game the way `tools/play.sh`
does. It ships no game code or files; the cover art on the home screen is
read from the player's mounted disc (`PS3_GAME/ICON0.PNG`, `PIC1.PNG`).

It is the [Resistance 2 port's
launcher](https://github.com/erikomis/resistance2-recomp/tree/main/launcher)
(itself the [Resistance: Fall of Man port's](https://github.com/erikomis/resistance-recomp/tree/main/launcher),
modelled on the inFAMOUS 2 port's) with the title, the disc ID and the folders
changed: the same look, layout and code (Play shortcut, Add to Steam, the
Dock icon from the player's copy, debug mode, the saves manager, the log
viewer, the controls page). Made for Apple-silicon macOS, like the game.

> [!NOTE]
> Where this document describes what the game does (the first boot's HDD
> install and the files it writes, the save slots, the disk space a build
> takes), it describes Resistance 2. Those parts are confirmed or changed for
> Resistance 3 once the port boots it; until then the launcher behaves as it
> did for Resistance 2. The app screenshots are not carried over.

## What the player does

1. **Home > Install the game** (shown until the game is built): choose the
   disc image (`.iso`) and press the button. The app checks the free disk
   space (8 GB asked; Resistance 2 took: the lift about 1.2 GB, the build 0.5 GB, the build
   tools 0.5 GB) and says it takes 15 to 45 minutes, opens Apple's Command
   Line Tools installer when they are missing (`xcode-select --install`) and
   waits for it (polling every 5 s), clones the sources into
   `~/Library/Application Support/resistance-recomp-3/src` when there is no
   checkout (at the tag `v<launcher version>` when it exists, on the default
   branch so Updates can pull; `RES_SOURCES_URL` overrides the repository),
   then runs `tools/install.sh`: `tools/bootstrap_deps.sh` (CMake, Ninja,
   Python 3.12, SDL2, SPIRV-Tools, glslang, SPIRV-Cross, FFmpeg into
   `<data>/deps`, no Homebrew; skipped with `RES_NO_DEPS=1` when Homebrew
   already has them all), the toolkit, the venv, decrypt (the disc's
   `EBOOT.BIN` with `tools/decrypt_self.py`, keys fetched once by
   `tools/fetch_keys.py` from RPCS3's public source; RPCS3 only as the
   fallback), analyse, lift, SPU, build. One progress bar with the stage's
   name and a time estimate; **Cancel**; on a failure a plain-language reason
   by stage (no internet, a full disk, the disc, the SPU fingerprints, the
   compile...) with **Copy log**, **Show the log file** (`<data>/install.log`)
   and **Report a problem** (the log's end copied, a new GitHub issue
   opened). Pressing it again after a quit or a failure continues where it
   stopped: what is installed is skipped, analyse, lift and SPU run only when
   their inputs changed, the build is incremental. Quitting the app stops the
   install (its own process group, by pid). A checkout without
   `tools/install.sh` gets `tools/bootstrap_deps.sh` (when it has it) and the
   full rebuild instead, which decrypts with RPCS3. Power users: **Advanced >
   Install / rebuild** lists what the Mac needs and runs `tools/rebuild.sh`
   with the chosen steps. Or build from a terminal (main README, "Building
   from source").
2. **Game > Disc**: **Mount the disc image…** picks the `.iso` and attaches
   it read-only (`hdiutil attach -readonly`); the image is remembered and
   mounted again on Play when it is not (setting "Mount the image on Play").
   A folder holding `PS3_GAME/` works too. Without either, the disc is found
   as `tools/env.sh` finds it: extracted into the port folder
   (`game/BCUS98176/`, or the folder itself in the development tree), else
   the first BCUS98176 volume under `/Volumes`.
3. **Play** on Home. On the first boot of a play folder the game copies about
   several hundred MB from the disc to its HDD folder (`cellGameDataCheckCreate2`: its
   caches and the streamed dialogue), as the PS3 does; Home says so until it
   is done.

## Screens

Screenshots are made with `scripts/screenshots.sh` (1280×800, the
`scripts/ui-mock.js` backend, no game art) into `docs/screenshots/`; this
port's are not taken yet. The Resistance 2 launcher's show the same screens.

**Settings are saved the moment they change** (`launcher.json`) and apply the
next time the game starts.

- **Home / Início**: a hero with the player's own disc art when it is
  mounted, else a plain styled title; "BCUS98176 · version 01.00" and the
  build date; **Play** (Stop while the game runs; **Capture this frame** in
  debug mode). A bar for whatever blocks Play, with its fix: no builds (the
  Install the game card, or Install / rebuild), no disc (mount an image or
  pick a folder), a disc that is not BCUS98176. The first-boot note (the
  several hundred MB HDD install), a bar when Updates has news. Cards: **Quick
  settings** (window size, display mode, fps counter, keep the Mac awake),
  **Last save**, **Status** (state, disc, the HDD install, builds, play
  folder; links to the log, Updates, **Play shortcut on the Desktop**, **Add
  to Steam**).
- **Graphics / Gráficos**: the window: display mode (`PS3_WINDOW_MODE=
  fullscreen|borderless`; windowed is the default and passes nothing), window
  size (`--size WxH` of the window host, which letterboxes the picture),
  screen (`PS3_DISPLAY`, by the names `NSScreen` gives), vsync (`PS3_VSYNC=0`
  when off), "Your disc's icon in the Dock" (and "Use as the app's Finder
  icon"); image quality: profile, internal resolution (`PS3_RES_SCALE=1.5|2|3`,
  labelled experimental), MetalFX upscaling (`PS3_UPSCALE=metalfx`), FXAA or
  SMAA (`PS3_AA`), sharpening (`PS3_SHARPEN`), anisotropic filtering
  (`PS3_ANISO`), gamma override (`PS3_DISPLAY_GAMMA`); filters: vibrance,
  contrast, vignette, grain (`PS3_VIBRANCE`, `PS3_CONTRAST`, `PS3_VIGNETTE`,
  `PS3_GRAIN`), a colour LUT file and its strength (`PS3_LUT`,
  `PS3_LUT_STRENGTH`); texture packs: the folders in `<data>/mods`, ticked
  and ordered (`PS3_MODS_DIR`, `PS3_MODS`, first wins), and **Dump the
  game's textures** (`PS3_MODS_DUMP=<data>/texture-dump`). The toolkit is the
  Resistance: Fall of Man one plus Resistance 3's changes, so these are the
  same options (every name is in this build); they were tested there, not
  through a whole Resistance 3 session.
- **Performance / Desempenho**: vertex cache (`PS3RECOMP_ENG_VCACHE=0` when
  off) and its per-stream split (`PS3RECOMP_ENG_VCACHE_SPLIT=0`), bind only
  changed state (`PS3RECOMP_METAL_BIND_ALL=1` when off); **Resistance 3's
  draw-engine changes** (the main README's environment table), all on, each
  off passing `=0`: shadow maps on the GPU (`PS3RECOMP_ENG_ZETA16_GPU`),
  attribute-major vertex fetch (`PS3RECOMP_ENG_FETCH_MANY`), sparse hashing
  (`PS3RECOMP_ENG_VCACHE_SPARSE`), same-frame vertex reuse
  (`PS3RECOMP_ENG_VCACHE_FRAMEREUSE`), the churn bypass
  (`PS3RECOMP_ENG_VCACHE_CHURN`), the GPU depth downsample
  (`PS3RECOMP_ENG_BLIT_GPU`), CPU writes into GPU targets
  (`PS3RECOMP_ENG_GUEST_WRITE`), and the volume-texture fix
  (`PS3RECOMP_FP_UNNORM_VOL=1`, on as in `play.sh`); the shader cache
  (`PS3_SHADER_CACHE=<play>/shadercache`, `play.sh`'s folder, with its size
  and **Clear**), background shader builds (`PS3_SHADER_ASYNC=1`, on as in
  `play.sh`) with the builds at once (`PS3_SHADER_ASYNC_JOBS`, 4) and what a
  cached translation does (`PS3_SHADER_ASYNC_SYNC_HIT` 0/1/2, 2); the frame
  clock (`PS3_FRAMECLOCK_US`: 50 µs is the port's default, 1 ms brings back
  the FIFO race), the frame-rate counter (`PS3RECOMP_METAL_FPS=1`), keep the
  Mac awake (`caffeinate -i`). Each switch is passed only when it differs
  from the runtime's default.
- **Game / Jogo**: the disc (path, the image it is mounted from, mount,
  folder, find, eject, mount on Play); the console language (`PS3_LANG`,
  empty = the Mac's); movies (`PS3RECOMP_FFMPEG=0` when off, and the
  `PS3RECOMP_FFMPEG_AVCODEC` / `_AVUTIL` paths: `<data>/deps/lib`'s when the
  install put them there, else Homebrew's, as `tools/env.sh`); **audio**:
  volume (`PS3_AUDIO_VOLUME` 0-100, passed below 100), mute
  (`PS3_AUDIO_MUTE=1`) and the output device (`PS3_AUDIO_DEVICE`, part of
  its name); the play folder (empty =
  `~/Library/Application Support/resistance-recomp-3`, `play.sh`'s
  `RES_DATA`) and whether its first-boot HDD install is done; the **saves
  manager** (below).
- **Controls / Controles**: the bindings table, PS3 control by keyboard,
  mouse button and controller, with what each does in Resistance 3, as the
  game's own on-screen hints name the buttons (R1 fire, R2 secondary fire,
  L1 zoom, L2 grenade, ✕ jump, ○ crouch, □ reload/use/pick up, △ switch
  weapons, L3 sprint, R3 melee, START pause, SELECT the map, left stick move,
  right stick look). Click a cell and press the input; it is written at once
  to `<data>/input.toml` (the toolkit's `libs/input/pad_input_map.h` format,
  the same file and the same built-in layout as the Resistance: Fall of Man
  port: `[keyboard]`, `[mouse_buttons]`, `[controller]`, any other section
  kept), which Play passes as `PS3_INPUT_MAP`. Until a binding changes there
  is no file and the game's built-in layout applies; **Restore defaults**
  moves the file to `input.toml.bak`. Pressing keys, mouse buttons or
  controller buttons lights the rows they drive, and the controller test
  shows the pad's name and both sticks. Then: what drives the game
  (`PS3_INPUT_MODE=controller|keyboard`; both is the default), the mouse
  (camera on/off `PS3_MOUSE=0`, `PS3_MOUSE_SENS`, `PS3_MOUSE_INVERT_Y`,
  `PS3_MOUSE_INVERT_X`, `PS3_MOUSE_DEADZONE` 0-120, cursor capture
  `PS3_MOUSE_CAPTURE=0`) and vibration (`PS3_RUMBLE=0`,
  `PS3_RUMBLE_STRENGTH` 0-200 %). The window host (`tools/host_window`) feeds
  the keyboard and the mouse to the game as in the first port; Resistance 3
  itself has been played with a controller.
- Every setting is passed only when it differs from the runtime's default,
  and the defaults are `tools/play.sh`'s: with them, Play starts the game
  with exactly `play.sh`'s environment. A section whose feature the build
  lacks (the builds' executables are searched for the variable's name) says
  to rebuild instead.
- **Advanced / Avançado**, five tabs:
  - **Install / rebuild**: 1. the requirements (Apple's CLT installer; the
    build tools, `tools/bootstrap_deps.sh`'s with **Install the build
    tools**, or Homebrew's when it has them all, with the `brew install …`
    line for what is missing otherwise; RPCS3, needed only when the port has
    no decryptor of its own and no `game/BCUS98176/EBOOT.elf` yet); 2. the
    port folder (below); 3. the rebuild: the steps (decrypt, analyse, lift,
    SPU, build; the toolkit and a Python venv always come first; decrypt
    tries `tools/decrypt_self.py` before `tools/rebuild.sh`'s RPCS3), JOBS, a
    progress bar with a time estimate, the step list and the log; **Cancel**
    stops it and everything it started.
  - **Updates**: the port checkout (branch, commit, `git fetch`, commits
    behind its upstream, **Get the new sources** = `git pull --ff-only`,
    refused with local changes) and "the sources changed after the builds"
    (the newest commit touching `port/`, `patches/` or `tools/` against the
    build's time) with **Rebuild the game**; the newest launcher release on
    GitHub. Once per session on start when **Check for updates when the app
    opens** is on; `RES_NO_UPDATE_CHECK=1` turns the launcher check off.
  - **Game log**: the end of `last.log` (or the debug session's log), at most
    512 KB, followed every 2 s, a filter, warnings and errors only (a `[tele]
    FREEZE` counts as an error), copy, show in Finder, **Earlier sessions**
    (the `logs/` folder).
  - **Debug mode**: see below.
  - **Environment**: extra variables (passed last, so they win; the main
    README's environment table; `RES_LEVEL=<n>` also passes `PS3_ARGV=
    -level;<n>` as `play.sh` does), **the game's log** (the controller button
    log `PS3_PAD_LOG=1`, telemetry and the stall report `PS3_TELEMETRY=1`,
    slow FIFO passes `RSX_DRAIN_SPIKE_MS` 100, the cache statistics
    `PS3RECOMP_ENG_VCACHE_STATS=1`, all on as in `play.sh`; quiet log
    `PS3_VERBOSE=0`, off as in `play.sh`), the equivalent command line,
    Restore defaults.
- UI in Brazilian Portuguese (default) and English (sidebar), English as the
  fallback for a missing string.

## How it fits together

```
launcher (Rust, src-tauri/src/lib.rs)
 ├─ Install → zsh in <data>: [git clone → <data>/src,] tools/install.sh
 │            (bootstrap_deps.sh → <data>/deps, toolkit, venv, decrypt … build;
 │            resumable; its output also in <data>/install.log)
 ├─ Rebuild → zsh in the port folder: [tools/bootstrap_deps.sh,] tools/rebuild.sh toolkit,
 │            python3.12 -m venv .venv + pip install -r ps3recomp/requirements.txt (once),
 │            [tools/decrypt_self.py,] PY=.venv/bin/python tools/rebuild.sh <steps>
 │            ("==> step" lines: src/progress.ts)
 └─ Play    → cd <play folder> &&
              [caffeinate -i] build/BCUS98176/Resistance [--size WxH] --
                  build/BCUS98176/ResistanceRecomp game/BCUS98176/EBOOT.elf  > last.log.raw 2>&1
              (a thread copies last.log.raw into last.log, "[  12.34] " before each line)
```

- **The port folder** is a checkout with `build/BCUS98176/{Resistance,
  ResistanceRecomp}` and `game/BCUS98176/EBOOT.elf`: this repository after
  `tools/rebuild.sh`, or the toolkit tree the port was developed in (its
  EBOOT at `game/EBOOT.elf`, its disc extracted beside it, as its `jogar.sh`
  has them). Empty setting = found on its own: `RES_ROOT`, the repository the
  launcher was built from, `<data>/src` (where Install the game clones the
  sources), then any folder one level under `~/Desktop`, `~/Developer`,
  `~/Documents`, `~/Projects`, `~/src`, `~/code`, `~/git` or `~` that has
  `build/BCUS98176`, complete builds and the newest first. Rebuilding needs
  the folder to have `tools/rebuild.sh`.
- **The build tools**: with `<data>/deps` complete (`RES_DEPS`), the install
  and the rebuild put its `bin/` first on `PATH` and set `CMAKE_PREFIX_PATH`,
  `PKG_CONFIG_LIBDIR` and `HOMEBREW_PREFIX` to it, which is where this port's
  `tools/rebuild.sh` and `tools/env.sh` take the FFmpeg headers and
  libraries from; without it, Homebrew's are used.
- **Play's environment**: `PS3_VFS_ROOT` (the disc), `PS3_HDD0_ROOT` /
  `PS3_HDD1_ROOT` (`<play>/dev_hdd0`, `dev_hdd1`), the FFmpeg paths, what
  `play.sh` turns on (`PS3RECOMP_METAL_FPS=1`, `PS3_PAD_LOG=1`,
  `PS3_TELEMETRY=1`, `RSX_DRAIN_SPIKE_MS=100`,
  `PS3RECOMP_ENG_VCACHE_STATS=1`, `PS3RECOMP_FP_UNNORM_VOL=1`,
  `PS3_SHADER_CACHE=<play>/shadercache`, `PS3_SHADER_ASYNC=1`), then only
  the other settings that differ from the port's defaults, then the extra
  variables. It drops an inherited `PS3RECOMP_METAL_HEADLESS`,
  `PS3RECOMP_HOST_SURFACES`, `PS3RECOMP_WINDOW_STATE` and `PS3_ARGV`. A GUI
  app starts with a bare `PATH`; the build tools' `<data>/deps/bin`, then
  Homebrew's folders go in front.
- **The log**, as `play.sh`: a non-empty `last.log` from the previous session
  moves to `logs/session-<its time>.log` and only the 10 newest stay; the
  game writes `last.log.raw`, and every line reaches `last.log` prefixed with
  the seconds since launch; the raw file goes when the game exits. Debug
  mode stamps its session's `game.log` the same way (the analysis ignores the
  stamps).
- **Stop** sends SIGTERM to the process group Play started (the window host
  closes the game, then itself), and SIGKILL to that group 8 s later if it
  is still there. Processes are never looked up by name to be signalled; a
  `ResistanceRecomp` started elsewhere (`play.sh`, a probe) is only shown
  ("running, started outside the launcher") and keeps the saves manager
  read-only.
- Settings live in `~/Library/Application Support/resistance-recomp-3/launcher.json`,
  next to the default play folder.

## Saves

`src-tauri/src/saves.rs`. Resistance 3 saves through cellSaveData only: the
slots `BCUS98176_SAVE_<n>` (PARAM.SFO, PARAM.PFD, ICON0.PNG, GAME.SAV),
written at every checkpoint (`cellSaveDataUserListAutoSave`) and from the
menu, under `<play>/dev_hdd0/home/00000001/savedata` (`PS3_HDD0_ROOT`) and
RPCS3's `dev_hdd0/home/<user>/savedata`. (The first port's separate
`quick.sav` checkpoint file has no counterpart here.)

Both sides are listed side by side, with "same as / differs from the other
side". Back up one or all, copy either way, delete, export to `.zip`, import
a `.zip` (an RPCS3 `savedata` zipped works), restore a backup. Backups go to
`<data>/save-backups/<UTC time>-<side>-<reason>/` with `backup.json`; one is
made before every Play (skipped when nothing changed; the newest N kept,
default 10, 0 = off) and before every restore, copy, import and delete. A
slot is built next to the old one and swapped in by renaming. The game's
files are copied byte for byte; crossing sides converts only the metadata:
the port's `PARAM.PFD` (the SECUREFILE names, one per line) becomes RPCS3's
`*<file>` keys and `RPCS3_BLIST` in PARAM.SFO, and back (RPCS3's own
PARAM.SFO is kept when it already has the slot). Everything refuses while
the game runs.

## Debug mode

`src-tauri/src/report.rs`, Advanced > Debug mode. **Play in debug mode**
starts the game as Play does, with its log and dumps in a new folder
`<data>/reports/<UTC time>/`:

| Variable | What it adds |
|---|---|
| `PS3RECOMP_METAL_FRAME_DUMP=<dir>/frame.ppm` | the whole frame every 120 presents |
| `RSX_ENGINE_PASS_DUMP=<dir>/passes`, `RSX_ENGINE_PASS_DUMP_TRIGGER=<dir>/.dump-now`, `RSX_ENGINE_PASS_DUMP_DRAWS=1` | on the first capture, the next frame pass by pass: each pass's render targets and depth, `passes.txt`, one line per draw in `draws.txt` |
| `PS3RECOMP_METAL_FPS=1`, `PS3RECOMP_HOST_STATS=1` | the frame rate and frame times, the window's latency and dropped frames |
| `LV2_ERRDBG=1` | each failing syscall, once per (number, error) |
| `PS3_VERBOSE=1` | the runtime's per-event lines |

(The first port's `AUDIO_RATE=1` is left out: this build does not contain
it.) **Capture this frame** keeps the latest whole frame as
`shots/shot<n>.ppm` and touches the trigger; `events.tsv` indexes the session
(start, a tick every 2 s with the log's size, captures, stop, exit),
`system.txt` has the Mac, macOS, GPU, the disc, the builds and the command
and variables. After a crash the macOS crash report (`ResistanceRecomp-*.ips`
or `Resistance-*.ips`) is copied as `crash.ips`. **Analyse** groups the
log's error and warning lines by message (numbers and the time stamps
masked), most frequent first, with the frame rate from the `[RSX FPS]` lines
(`triage.md`, `triage.json`). **Create .zip** packs the folder (PPM/PGM as
PNG, the home folder's path as `~`, the optional description as `notes.txt`)
to attach to an issue.

## The Play shortcut and Add to Steam

As in the first port's launcher (`play_shortcut.rs`, `steam.rs`, `vdf.rs`,
`steam_art.rs`): `--play` on the command line starts the game once the
window is up (`open -b io.github.erikomis.resistance3recomp --args --play`);
Home > Status > **Play shortcut on the Desktop** writes `~/Desktop/Play
Resistance 3.app` running that line. **Add to Steam** (Steam installed, the
packaged app) writes a non-Steam entry "Resistance 3" into every account's
`shortcuts.vdf` (backed up first as `shortcuts.vdf.resistance3-backup`,
other entries untouched; Steam must be closed, the app offers to quit it),
with library art drawn at that moment from the player's own `ICON0.PNG` and
`PIC1.PNG`; the entry runs `--play --exit-with-game`, so Steam sees the game
exactly as long as it runs. **Remove from Steam** takes it out again.

## Development

Needs Node 20+, Rust (stable) and the Xcode Command Line Tools.

```sh
cd launcher
npm ci
npm run tauri dev        # the app, with the frontend hot-reloaded
npm run tauri build      # .app and .dmg in src-tauri/target/release/bundle/
npx tauri build --debug  # the same, unoptimised, in src-tauri/target/debug/bundle/
npm run typecheck        # frontend only
(cd src-tauri && cargo test)
```

`--view <page>[:<tab>]` on the command line opens a page (and an Advanced
tab), e.g. `--view advanced:log`.

The screenshots in `docs/screenshots/` come from the built frontend in a
plain browser with a fake backend: `npm run build && scripts/screenshots.sh`
serves a copy of `dist/` with `scripts/ui-mock.js` loaded before the app and
captures each screen with headless Chrome (Playwright's
`chrome-headless-shell` when installed). The mock takes its state from an
earlier init script (`window.__UI_MOCK__ = { noBuilds: true }`, `{ noDisc:
true }`, `{ running: true }`, `{ firstBoot: true }`, `{ lang: "en" }`,
`{ view: "advanced:log" }`) or from the page's query string
(`?view=performance&lang=en`).

`scripts/check_bundle.py <.app|.dmg>` fails when a bundle carries anything
from the game (names, PS3 file headers, PowerPC/SPU ELFs, big files; a
debug build's executable is over its 16 MB limit, a release one is not). The
builds are unsigned: right-click the app and choose Open the first time
(Gatekeeper).

The icon is an original placeholder (`scripts/make_icon.py`, then `npx
tauri icon src-tauri/icons/app-icon.png`): a targeting reticle with a double
ring (the first port's has one), no game art or logo. The font is Oswald
(SIL Open Font License, `src/assets/fonts/`).

## Windows

The launcher's Windows code (Mount-DiskImage, `taskkill`, `%APPDATA%\
resistance-recomp-3`) is kept from the first port's launcher and compiles,
but the Resistance 3 port is made for macOS only: the app shows an
"experimental" banner there, and none of it is tested.

## Not done (from the first port's launcher)

- **60 fps and field of view**: the first port's `RES_UNLOCK_FPS`,
  `RES_MENU_60FPS` and `RES_FOV` game patches do not exist for Resistance 3
  (the build has none of these names); the page has no such section.
- **The campaign version switch and the update-files mover**: Resistance 3
  is a single EBOOT, with no v1.7 `game.self` exitspawn.
- **App self-update**, **button-icon settings, the built-in LUT presets, the
  tone curve, voice/subtitle languages, trophies**: as in the first port.
- **A bundled port**: the app carries no sources; Install the game clones
  them and builds from that checkout.
- **A CI workflow** (`.github/workflows/launcher.yml` in the first port) and
  `tools/rebuild.sh launcher`: this repository has neither yet.
