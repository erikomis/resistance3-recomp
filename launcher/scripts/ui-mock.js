// A fake Tauri backend so the built frontend can be looked at in a plain
// browser (the screenshots in docs/screenshots). Injected before the page
// loads:
//
//   npm run build && npx vite preview --port 4173
//   # then, e.g. with Playwright: page.addInitScript({ path: "scripts/ui-mock.js" })
//
// It answers the commands the window calls with a built port, a mounted disc,
// saves and a log, and no art (the art only ever comes from the player's
// disc). window.__UI_MOCK__ = { noBuilds: true }, { noDisc: true },
// { running: true }, { firstBoot: true } or { prereqProblems: true }, set by an earlier init script,
// shows those states instead; { oldBuild: true } is a build from before the
// keyboard/mouse, filters and window modes, { lang: "en" } the English UI,
// { view: "advanced:log" } opens on that page (and tab). Without an init
// script, the page's query string sets the same flags
// (?view=performance&lang=en&noBuilds=1).
(() => {
  const q = new URLSearchParams(location.search);
  const fromQuery = Object.fromEntries([...q.entries()].map(([k, v]) => [k, v === "1" ? true : v]));
  const flags = window.__UI_MOCK__ || fromQuery;
  const home = "/Users/player";
  const data = `${home}/Library/Application Support/resistance-recomp-3`;
  const settings = {
    uiLang: flags.lang || "pt-BR", portDir: "", discPath: "", discImage: `${home}/Games/Resistance 3.iso`, autoMount: true, playDir: "",
    gameLang: "", windowSize: "1920x1080", gameIcon: false, aa: "fxaa", sharpen: 0.2, aniso: 4,
    gammaOverride: false, gamma: 1, showFps: true, vertexCache: true, vertexCacheSplit: true, bindChangedOnly: true,
    zeta16Gpu: true, fetchMany: true, vcacheSparse: true, vcacheFrameReuse: true, vcacheChurn: true, blitGpu: true, guestWrite: true,
    shaderCache: true, shaderAsync: true, shaderAsyncJobs: 4, shaderSyncHit: 2, frameClockUs: 50,
    padLog: true, telemetry: true, drainSpikeMs: 100, vcacheStats: true, fpUnnormVol: true,
    keepAwake: true, video: true, ffmpegAvcodec: "", ffmpegAvutil: "",
    quietLog: false, extraEnv: "", rebuildSteps: [], jobs: 0, saveBackupsKeep: 10, autoUpdateCheck: true,
    windowMode: "windowed", display: "", vsync: true, upscale: "", resScale: "", vibrance: 0, contrast: 1, vignette: 0, grain: 0,
    lutPath: "", lutStrength: 1, mods: ["HD Chimera"], modsDump: false, inputMode: "both", mouse: true, mouseSens: 1,
    mouseInvertY: false, mouseInvertX: false, mouseDeadzone: 30, mouseCapture: true, rumble: true, rumbleStrength: 100,
    audioVolume: 100, audioMute: false, audioDevice: "",
  };
  const features = flags.oldBuild ? [] : [
    "PS3_INPUT_MAP", "PS3_LUT_STRENGTH", "PS3_MODS_DIR", "PS3_RES_SCALE", "PS3_UPSCALE", "PS3_WINDOW_MODE", "PS3_AUDIO_VOLUME",
    "PS3_SHADER_ASYNC_SYNC_HIT", "PS3RECOMP_ENG_ZETA16_GPU", "PS3RECOMP_ENG_VCACHE_FRAMEREUSE", "PS3RECOMP_ENG_GUEST_WRITE", "PS3_TELEMETRY",
  ];
  const now = Math.floor(Date.now() / 1000);
  const root = `${home}/Developer/resistance3-recomp`;
  const builds = {
    root, host: `${root}/build/BCUS98176/Resistance`, eboot: `${root}/build/BCUS98176/ResistanceRecomp`,
    ebootElf: `${root}/game/BCUS98176/EBOOT.elf`, ok: true, missing: [], rebuildSh: `${root}/tools/rebuild.sh`, builtAt: now - 3600 * 3,
  };
  const disc = flags.noDisc
    ? { root: null, title: "", titleId: "", appVer: "", image: null, ours: false, mounted: [] }
    : { root: "/Volumes/RESISTANCE_2", title: "Resistance 3", titleId: "BCUS98176", appVer: "01.00", image: `${home}/Games/Resistance 3.iso`, ours: true, mounted: ["/Volumes/RESISTANCE_2"] };
  const slot = (name, sub, mod, hash) => ({
    name, kind: "save", title: "Resistance 3", subtitle: sub, detail: "", modified: mod, bytes: 518000, path: `/saves/${name}`, icon: null, hash,
  });
  const log = [
    "[    0.02] [host window] 'Resistance 3' pid 4242 window 812, game pid 4243",
    "[    0.41] [cellSysutil] system language 1 (host)",
    "[    0.88] [RSX metal] host window: 5 surfaces 1280x720 (generation 1)",
    "[    0.90] [shader cache] PS3_SHADER_ASYNC: pipelines build in the background (their draws are skipped until ready), up to PS3_SHADER_ASYNC_JOBS at once",
    "[    1.20] [cellVdec] FFmpeg libavcodec loaded",
    "[    2.05] [cellGame] DataCheckCreate2: funcStat returned result=0",
    "[   61.34] [tele] frames=30 draws=1874",
    "[   61.35] [RSX FPS] display=29.80 guest=29.80 avg_ms=33.50 p95_ms=36.10 max_ms=41.00 age_s=0.00",
    "[   62.10] [hle] stub cellNetCtlGetInfo (offline)",
    "[   88.72] [rsx drain] pass of 118 ms: 1912 draws, 7 pipeline builds, vertex fetch 61 ms",
    "[   89.35] [RSX FPS] display=28.90 guest=28.90 avg_ms=34.60 p95_ms=38.40 max_ms=118.00 age_s=0.00",
  ].join("\n") + "\n";
  const answers = {
    get_settings: () => settings,
    save_settings: () => null,
    get_status: () => ({
      builds: flags.noBuilds ? { ...builds, ok: false, host: null, eboot: null, ebootElf: null, missing: ["build/BCUS98176/Resistance", "build/BCUS98176/ResistanceRecomp", "game/BCUS98176/EBOOT.elf"], builtAt: 0 } : builds,
      disc, icon: null, background: null,
      lastSave: { name: "BCUS98176_SAVE_0", title: "Resistance 3", subtitle: "Campaign", modified: now - 3600 * 5, folder: "/saves" },
      gameRunning: !!flags.running, otherGameRunning: false, rebuildRunning: false, playDir: data, dataRoot: data,
      firstBoot: !!flags.firstBoot,
      hostSupported: true, experimental: false, os: "macos", appBundle: "/Applications/Resistance 3 Launcher.app", finderIcon: false, version: "0.1.0",
      features,
    }),
    disc_status: () => disc,
    find_port_dirs: () => [builds],
    check_updates: (a) => ({
      sources: { git: true, branch: "main", commit: "1a2b3c4", subject: "Launcher", commitTime: now - 7200, upstream: "origin/main", behind: 0, ahead: 0, dirty: 0, sourcesTime: now - 7200, fetched: !!a.online, error: null },
      rebuildNeeded: false, builtAt: builds.builtAt,
      app: { current: "0.1.0", latest: "v0.1.0", newer: false, url: null, notes: null, disabled: false, error: null },
    }),
    steam_status: () => ({ available: true, installed: true, running: false, users: 1, added: 0 }),
    shader_cache_info: () => ({ path: `${data}/shadercache`, bytes: 17800000, files: 2310 }),
    report_info: () => (flags.running ? { dir: "/r/x", id: "20261022-190000", live: true, debug: true, captures: 1, pending: false, passes: 64, bytes: 210000000, logBytes: 9000000, duration: 300, exit: null, stopped: false, crashReport: false, zip: null, zipBytes: 0, triage: null } : null),
    report_list: () => [
      { dir: "/r/20261022-181500", id: "20261022-181500", live: false, debug: true, captures: 2, pending: false, passes: 64, bytes: 286000000, logBytes: 41200000, duration: 1874, exit: "signal=15", stopped: true, crashReport: false, zip: null, zipBytes: 0,
        triage: { errors: 2, warnings: 41, lines: 120000, fpsAvg: 28.6, fpsMin: 19.5, stale: false, md: "/r/triage.md",
          top: [
            { severity: "error", title: "[tele] FREEZE: no guest frame for # s", count: 2, firstLine: 812 },
            { severity: "warning", title: "[hle] stub cellNetCtlGetInfo (offline)", count: 38, firstLine: 1204 },
          ] } },
    ],
    check_prereqs: () => {
      const ok = (name, path) => ({ level: "ok", name, message: path, key: "", vars: {}, path, optional: false });
      const msg = (level, name, key, message, vars = {}, extra = {}) => ({ level, name, message, key, vars, path: null, optional: false, ...extra });
      const checks = flags.prereqProblems
        ? [
            msg("ok", "xcode-clt", "cltOk", "installed"),
            msg("fail", "deps", "depsBrewMissing", "missing", { cmd: "brew install glslang spirv-cross" }),
            msg("fail", "rpcs3", "rpcs3Missing", "not installed"),
            msg("warn", "disc", "discForPlay", "not mounted (needed to play)"),
            msg("warn", "toolkit", "toolkitLater", "not set up yet"),
            msg("warn", "venv", "venvLater", "not made yet"),
            msg("warn", "disk", "diskLow", "only 4 GB free", { free: "4", need: "6" }),
          ]
        : [
            msg("ok", "xcode-clt", "cltOk", "installed"),
            msg("ok", "deps", "depsBrew", "Homebrew's", {}, { path: "/opt/homebrew" }),
            { ...ok("rpcs3", "/Applications/RPCS3.app/Contents/MacOS/rpcs3"), optional: true },
            ok("disc", `${home}/Desktop/resistance-recomp-3`),
            msg("info", "rebuild", "rebuildElsewhere", "use the resistance3-recomp checkout to rebuild"),
            msg("ok", "disk", "diskEnough", "11 GB free: enough", { free: "11" }),
            ok("builds", `${home}/Desktop/resistance-recomp-3`),
          ];
      return {
        supported: true, clt: true, checks, ok: !checks.some((c) => c.level === "fail"), deps: !flags.prereqProblems, bootstrap: false,
        depsDir: `${data}/deps`, sources: root, elfs: !flags.noBuilds, decrypt: !flags.prereqProblems, disc: !flags.noDisc,
        buildsOk: !flags.noBuilds, freeGb: flags.prereqProblems ? 4 : 11, needGb: flags.noBuilds ? 6 : 0,
      };
    },
    saves_overview: () => ({
      port: [slot("BCUS98176_SAVE_0", "Campaign", now - 3600 * 5, "a1")],
      rpcs3: [slot("BCUS98176_SAVE_0", "Campaign", now - 86400 * 9, "a0")],
      rpcs3Users: ["00000001"], rpcs3User: "00000001",
      backups: [{ id: "20261030-171500-port-auto", created: now - 3600 * 6, reason: "auto", side: "port", user: "", slots: ["BCUS98176_SAVE_0"], titles: { BCUS98176_SAVE_0: "Campaign" }, bytes: 518000 }],
      portDir: "/x/savedata", rpcs3Dir: "/x/rpcs3", backupsDir: "/x/save-backups", gameRunning: false, rpcs3Running: false,
    }),
    launch_preview: () => `cd '${data}' && PS3_VFS_ROOT=/Volumes/RESISTANCE_2 PS3_HDD0_ROOT='${data}/dev_hdd0' PS3_HDD1_ROOT='${data}/dev_hdd1' PS3RECOMP_FFMPEG_AVCODEC=/opt/homebrew/lib/libavcodec.dylib PS3RECOMP_FFMPEG_AVUTIL=/opt/homebrew/lib/libavutil.dylib PS3_AA=fxaa PS3_SHARPEN=0.20 PS3_ANISO=4 PS3RECOMP_METAL_FPS=1 PS3_PAD_LOG=1 PS3_TELEMETRY=1 RSX_DRAIN_SPIKE_MS=100 PS3RECOMP_ENG_VCACHE_STATS=1 PS3RECOMP_FP_UNNORM_VOL=1 PS3_SHADER_CACHE='${data}/shadercache' PS3_SHADER_ASYNC=1 /usr/bin/caffeinate -i ${root}/build/BCUS98176/Resistance --size 1920x1080 -- ${root}/build/BCUS98176/ResistanceRecomp ${root}/game/BCUS98176/EBOOT.elf > '${data}/last.log' 2>&1   # each line stamped with the seconds since launch into last.log, as tools/play.sh`,
    read_game_log: () => ({ path: `${data}/last.log`, exists: true, size: log.length, modified: now - 120, text: log, truncated: false }),
    log_paths: () => ({ game: `${data}/last.log`, saves: "/x/savedata", play: data, data, sessions: `${data}/logs` }),
    take_play_request: () => false,
    take_start_view: () => flags.view || null,
    frontend_log: (a) => console.warn("frontend:", a.message),
    get_input_map: () => ({ path: `${data}/input.toml`, exists: false, bindings: { keyboard: {}, mouseButtons: {}, controller: {} } }),
    save_input_map: () => `${data}/input.toml`,
    reset_input_map: () => null,
    list_screens: () => ["Built-in Retina Display", "LG ULTRAFINE"],
    list_mods: () => ({
      dir: `${data}/mods`, dumpDir: `${data}/texture-dump`,
      packs: [{ name: "HD Chimera", textures: 214, description: "Sharper Chimeran armour" }, { name: "Clean HUD", textures: 12, description: "" }],
    }),
  };
  let cb = 0;
  window.__TAURI_INTERNALS__ = {
    invoke: async (cmd, args) => {
      if (cmd.startsWith("plugin:event|")) return cmd.endsWith("listen") ? ++cb : null;
      if (cmd.startsWith("plugin:dialog|")) return null;
      if (cmd === "save_settings") Object.assign(settings, args.settings);
      const f = answers[cmd];
      if (!f) {
        console.warn("ui-mock: no answer for", cmd, args);
        return null;
      }
      return f(args || {});
    },
    transformCallback: () => ++cb,
    unregisterCallback: () => {},
    convertFileSrc: (p) => p,
    metadata: { currentWindow: { label: "main" }, currentWebview: { windowLabel: "main", label: "main" } },
  };
  window.__TAURI_EVENT_PLUGIN_INTERNALS__ = { unregisterListener: () => {} };
})();
