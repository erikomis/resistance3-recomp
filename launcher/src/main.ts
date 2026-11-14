import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { ask, open } from "@tauri-apps/plugin-dialog";
import { CONSOLE_LANGS, Key, Lang, lang, setLang, t, translateDom } from "./i18n";
import { initControls, renderControls, showControls } from "./controls";
import { PICK_IDS, RebuildProgress, StepId } from "./progress";
import { initSaves, refresh as refreshSaves, render as renderSaves } from "./saves";
import { initUpdates, refreshUpdates, renderUpdates } from "./update";
import { initLog, renderLog, showLog } from "./gamelog";
import { initMods, refreshMods, renderMods } from "./mods";
import { flashSaved, human } from "./ui";

// ---- types shared with src-tauri/src/lib.rs (camelCase) ----------------------
export interface Settings {
  uiLang: string;
  portDir: string;
  discPath: string;
  discImage: string;
  autoMount: boolean;
  playDir: string;
  gameLang: string;
  windowSize: string;
  windowMode: string;
  display: string;
  vsync: boolean;
  upscale: string;
  resScale: string;
  gameIcon: boolean;
  aa: string;
  sharpen: number;
  aniso: number;
  gammaOverride: boolean;
  gamma: number;
  vibrance: number;
  contrast: number;
  vignette: number;
  grain: number;
  lutPath: string;
  lutStrength: number;
  mods: string[];
  modsDump: boolean;
  inputMode: string;
  mouse: boolean;
  mouseSens: number;
  mouseInvertY: boolean;
  mouseInvertX: boolean;
  mouseDeadzone: number;
  mouseCapture: boolean;
  rumble: boolean;
  rumbleStrength: number;
  adaptiveTriggers: boolean;
  padLight: string;
  padLightHit: boolean;
  gyro: number;
  gyroAlways: boolean;
  audioVolume: number;
  audioMute: boolean;
  audioDevice: string;
  showFps: boolean;
  vertexCache: boolean;
  vertexCacheSplit: boolean;
  bindChangedOnly: boolean;
  zeta16Gpu: boolean;
  fetchMany: boolean;
  vcacheSparse: boolean;
  vcacheFrameReuse: boolean;
  vcacheChurn: boolean;
  blitGpu: boolean;
  guestWrite: boolean;
  shaderCache: boolean;
  shaderAsync: boolean;
  shaderAsyncJobs: number;
  shaderSyncHit: number;
  frameClockUs: number;
  padLog: boolean;
  telemetry: boolean;
  drainSpikeMs: number;
  vcacheStats: boolean;
  fpUnnormVol: boolean;
  keepAwake: boolean;
  video: boolean;
  ffmpegAvcodec: string;
  ffmpegAvutil: string;
  quietLog: boolean;
  extraEnv: string;
  rebuildSteps: string[];
  jobs: number;
  saveBackupsKeep: number;
  autoUpdateCheck: boolean;
}
interface Builds {
  root: string;
  host: string | null;
  eboot: string | null;
  ebootElf: string | null;
  ok: boolean;
  missing: string[];
  rebuildSh: string | null;
  builtAt: number;
}
interface DiscInfo {
  root: string | null;
  title: string;
  titleId: string;
  appVer: string;
  image: string | null;
  ours: boolean;
  mounted: string[];
}
interface SaveInfo {
  name: string;
  title: string;
  subtitle: string;
  modified: number;
  folder: string;
}
interface Status {
  builds: Builds | null;
  disc: DiscInfo;
  icon: string | null;
  background: string | null;
  lastSave: SaveInfo | null;
  gameRunning: boolean;
  otherGameRunning: boolean;
  rebuildRunning: boolean;
  playDir: string;
  dataRoot: string;
  /** The first boot's HDD install (several hundred MB from the disc) has not completed. */
  firstBoot: boolean;
  hostSupported: boolean;
  /** The port's build for this system is untested (Windows). */
  experimental: boolean;
  os: string;
  appBundle: string | null;
  finderIcon: boolean;
  version: string;
  /** The feature markers (environment variable names) the builds contain. */
  features: string[];
}
interface CheckItem {
  /** "info": only to know; "optional": absent and not needed. */
  level: "ok" | "warn" | "fail" | "info" | "optional";
  name: string;
  /** English fallback for `key`. */
  message: string;
  /** i18n key under prereq.msg. ("" = the detail is only the path). */
  key: string;
  vars: Record<string, string>;
  path: string | null;
  /** A fallback tool, not a requirement. */
  optional: boolean;
}
interface Prereqs {
  supported: boolean;
  clt: boolean;
  checks: CheckItem[];
  ok: boolean;
  /** The build tools and libraries are there (tools/bootstrap_deps.sh's, or Homebrew's). */
  deps: boolean;
  /** The port has tools/bootstrap_deps.sh to install them (no Homebrew). */
  bootstrap: boolean;
  depsDir: string;
  /** The port's sources (a checkout with tools/rebuild.sh); none = Install downloads them. */
  sources: string | null;
  elfs: boolean;
  /** The decrypt step can run (EBOOT.elf there, the port's own decryptor, or RPCS3). */
  decrypt: boolean;
  disc: boolean;
  buildsOk: boolean;
  freeGb: number | null;
  needGb: number;
}
interface ReportInfo {
  dir: string;
  id: string;
  live: boolean;
  debug: boolean;
  captures: number;
  pending: boolean;
  passes: number;
  bytes: number;
  logBytes: number;
  duration: number | null;
  exit: string | null;
  stopped: boolean;
  crashReport: boolean;
  zip: string | null;
  zipBytes: number;
  triage: Triage | null;
}
interface Triage {
  errors: number;
  warnings: number;
  lines: number;
  fpsAvg: number | null;
  fpsMin: number | null;
  stale: boolean;
  md: string;
  top: { severity: string; title: string; count: number; firstLine: number }[];
}

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
const show = (el: HTMLElement, on: boolean) => el.classList.toggle("hidden", !on);
const tilde = (p: string) => p.replace(/^\/Users\/[^/]+/, "~");

let settings: Settings;
let status: Status | null = null;
let gameRunning = false;
let rebuildRunning = false;
const progress = new RebuildProgress();

// ---- navigation ----------------------------------------------------------------
let advancedTab = "install";

function showView(view: string, tab?: string) {
  document.querySelectorAll<HTMLElement>(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${view}`));
  document.querySelectorAll<HTMLElement>(".nav").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  document.querySelector("main")!.scrollTop = 0;
  if (view === "home") refreshStatus();
  if (view === "graphics") {
    refreshScreens();
    refreshMods();
  }
  if (view === "performance") refreshShaderCache();
  if (view === "game") {
    refreshDisc();
    refreshSaves();
    refreshAudioOutputs();
  }
  showControls(view === "controls");
  if (view === "advanced") showTab(tab ?? advancedTab);
}

function showTab(tab: string) {
  advancedTab = tab;
  document.querySelectorAll<HTMLElement>(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll<HTMLElement>(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tab}`));
  if (tab === "env") updatePreview();
  if (tab === "log") showLog();
  if (tab === "updates") renderUpdates();
  if (tab === "diagnostics") refreshReport();
  if (tab === "install") {
    refreshPrereqs();
    renderPort();
  }
}

document.querySelectorAll<HTMLElement>(".nav").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view!)));
document.querySelectorAll<HTMLElement>(".tab").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab!)));
document.querySelectorAll<HTMLElement>("[data-go]").forEach((b) =>
  b.addEventListener("click", () => {
    const [view, tab] = b.dataset.go!.split(":");
    showView(view, tab);
  }));
document.querySelectorAll<HTMLElement>("[data-url]").forEach((b) =>
  b.addEventListener("click", () => invoke("open_url", { url: b.dataset.url })));

// ---- settings persistence --------------------------------------------------------
let saveTimer = 0;
function persist(after?: () => void) {
  window.clearTimeout(saveTimer);
  saveTimer = window.setTimeout(async () => {
    await invoke("save_settings", { settings });
    flashSaved();
    updatePreview();
    after?.();
  }, 250);
}

async function updatePreview() {
  try {
    $("preview").textContent = await invoke<string>("launch_preview", { settings });
  } catch (e) {
    $("preview").textContent = String(e);
  }
}

// ---- shader cache ----------------------------------------------------------------
interface ShaderCacheInfo {
  path: string | null;
  bytes: number;
  files: number;
}
async function refreshShaderCache(msg = "") {
  try {
    const c = await invoke<ShaderCacheInfo>("shader_cache_info");
    $("sc-info").textContent =
      (c.path ? t("sc.size", { size: human(c.bytes), files: c.files, path: tilde(c.path) }) : t("sc.off")) + (msg ? ` — ${msg}` : "");
    $<HTMLButtonElement>("sc-clear").disabled = !c.path || c.files === 0;
  } catch (e) {
    $("sc-info").textContent = String(e);
  }
}
$("sc-clear").addEventListener("click", async () => {
  try {
    await invoke("shader_cache_clear");
    refreshShaderCache(t("sc.cleared"));
  } catch (e) {
    refreshShaderCache(String(e));
  }
});

/** A setting can have more than one control (Home's quick settings repeat a
 * few of the pages'): after every change each control is set again. */
const syncers: (() => void)[] = [];
function syncAll() {
  for (const f of syncers) f();
  syncDependent();
}

const WINDOW_SIZES = ["", "1600x900", "1920x1080", "2560x1440", "3840x2160"];

function fillFixedSelects() {
  document.querySelectorAll<HTMLSelectElement>("select.size-select").forEach((sel) => {
    sel.innerHTML = "";
    for (const v of WINDOW_SIZES) {
      const o = document.createElement("option");
      o.value = v;
      o.textContent = v ? v.replace("x", " × ") : t("settings.windowSizeDefault");
      sel.appendChild(o);
    }
  });
  const gl = $<HTMLSelectElement>("game-lang");
  gl.innerHTML = "";
  const def = document.createElement("option");
  def.value = "";
  def.textContent = t("settings.langMac");
  gl.appendChild(def);
  for (const l of CONSOLE_LANGS) {
    const o = document.createElement("option");
    o.value = l.code;
    o.textContent = lang() === "en" ? l.en : l.pt;
    gl.appendChild(o);
  }
}

type BoolKey = { [K in keyof Settings]: Settings[K] extends boolean ? K : never }[keyof Settings];
type NumKey = { [K in keyof Settings]: Settings[K] extends number ? K : never }[keyof Settings];
type StrKey = { [K in keyof Settings]: Settings[K] extends string ? K : never }[keyof Settings];

function bindCheck(id: string, key: BoolKey) {
  const el = $<HTMLInputElement>(id);
  const sync = () => (el.checked = settings[key]);
  syncers.push(sync);
  sync();
  el.addEventListener("change", () => {
    settings[key] = el.checked;
    syncAll();
    persist(key === "gameIcon" ? () => refreshStatus() : undefined);
  });
}

function bindRange(id: string, key: NumKey, fmt: (v: number) => string) {
  const el = $<HTMLInputElement>(id);
  const out = $(`${id}-out`);
  const sync = () => {
    el.value = String(settings[key]);
    out.textContent = fmt(Number(el.value));
  };
  syncers.push(sync);
  sync();
  el.addEventListener("input", () => {
    settings[key] = Number(el.value);
    out.textContent = fmt(Number(el.value));
    syncPreset();
    persist();
  });
}

type NumSelectKey = "aniso" | "frameClockUs" | "shaderAsyncJobs" | "shaderSyncHit" | "drainSpikeMs" | "gyro";
const NUM_SELECTS: string[] = ["aniso", "frameClockUs", "shaderAsyncJobs", "shaderSyncHit", "drainSpikeMs", "gyro"];

function bindSelect(id: string, key: StrKey | NumSelectKey) {
  const el = $<HTMLSelectElement>(id);
  const sync = () => {
    el.value = String(settings[key]);
    if (el.value !== String(settings[key])) el.selectedIndex = 0;
  };
  syncers.push(sync);
  sync();
  el.addEventListener("change", () => {
    if (NUM_SELECTS.includes(key)) (settings as unknown as Record<string, number>)[key] = Number(el.value);
    else (settings as unknown as Record<string, string>)[key] = el.value;
    syncAll();
    persist();
  });
}

function bindText(id: string, key: StrKey, after?: () => void) {
  const el = $<HTMLInputElement | HTMLTextAreaElement>(id);
  const sync = () => (el.value = settings[key]);
  syncers.push(sync);
  sync();
  el.addEventListener("change", () => {
    settings[key] = el.value.trim();
    persist(after);
  });
}

/** Image-quality profiles over the three image options (the PS3 look,
 * a light clean-up, everything on). The list shows the one the values match. */
const PRESETS: Record<string, Pick<Settings, "aniso" | "aa" | "sharpen">> = {
  native: { aniso: 0, aa: "", sharpen: 0 },
  balanced: { aniso: 4, aa: "fxaa", sharpen: 0.2 },
  quality: { aniso: 16, aa: "fxaa", sharpen: 0.35 },
};
function currentPreset(): string {
  for (const [name, p] of Object.entries(PRESETS)) {
    if (settings.aniso === p.aniso && settings.aa === p.aa && Math.abs(settings.sharpen - p.sharpen) < 0.005) return name;
  }
  return "custom";
}
function syncPreset() {
  $<HTMLSelectElement>("preset").value = currentPreset();
}

// ---- screens (PS3_DISPLAY) --------------------------------------------------------
let screens: string[] = [];
async function refreshScreens() {
  screens = await invoke<string[]>("list_screens").catch(() => []);
  fillScreens();
}
/** The main screen (the default), the connected ones, and the saved one when
 * it is not connected now. */
function fillScreens() {
  const sel = $<HTMLSelectElement>("display");
  sel.replaceChildren(new Option(t("settings.screenMain"), ""));
  for (const n of screens) sel.append(new Option(n, n));
  const cur = settings.display;
  if (cur && !screens.includes(cur)) sel.append(new Option(t("settings.screenMissing", { name: cur }), cur));
  sel.value = cur;
}

// ---- sound outputs (PS3_AUDIO_DEVICE) ---------------------------------------------
let audioOutputs: string[] = [];
async function refreshAudioOutputs() {
  audioOutputs = await invoke<string[]>("list_audio_outputs").catch(() => []);
  fillAudioOutputs();
}
/** The system's default output, the ones the Mac has now, and the saved one
 * when it is not connected. */
function fillAudioOutputs() {
  const sel = $<HTMLSelectElement>("audio-device");
  sel.replaceChildren(new Option(t("settings.audioDeviceDefault"), ""));
  for (const n of audioOutputs) sel.append(new Option(n, n));
  const cur = settings.audioDevice;
  if (cur && !audioOutputs.includes(cur)) sel.append(new Option(t("settings.screenMissing", { name: cur }), cur));
  sel.value = cur;
}

// ---- what the build supports ------------------------------------------------------
/** Sections whose feature the build lacks say so ("rebuild"). */
function renderFeatures() {
  const have = new Set(status?.features ?? []);
  const known = !!status?.builds; // no builds yet: nothing to say
  document.querySelectorAll<HTMLElement>("[data-feature]").forEach((el) => {
    const missing = known && !have.has(el.dataset.feature!);
    let note = el.querySelector<HTMLElement>(":scope > .needs-rebuild");
    if (missing && !note) {
      note = document.createElement("p");
      note.className = "hint hint-warn needs-rebuild";
      const head = el.querySelector(":scope > h2, :scope > .section-head");
      if (head) head.after(note);
      else el.querySelector(".opt-text")?.append(note);
    }
    if (note) {
      note.textContent = t("feature.rebuild");
      show(note, missing);
    }
  });
}

function bindSettings() {
  fillFixedSelects();
  bindCheck("game-icon", "gameIcon");
  bindCheck("gamma-on", "gammaOverride");
  bindCheck("show-fps", "showFps");
  bindCheck("q-fps", "showFps");
  bindCheck("keep-awake", "keepAwake");
  bindCheck("q-awake", "keepAwake");
  bindCheck("vcache", "vertexCache");
  bindCheck("vcache-split", "vertexCacheSplit");
  bindCheck("bind-changed", "bindChangedOnly");
  bindCheck("shader-cache", "shaderCache");
  bindCheck("shader-async", "shaderAsync");
  bindCheck("zeta16-gpu", "zeta16Gpu");
  bindCheck("fetch-many", "fetchMany");
  bindCheck("vcache-sparse", "vcacheSparse");
  bindCheck("vcache-reuse", "vcacheFrameReuse");
  bindCheck("vcache-churn", "vcacheChurn");
  bindCheck("blit-gpu", "blitGpu");
  bindCheck("guest-write", "guestWrite");
  bindCheck("unnorm-vol", "fpUnnormVol");
  bindCheck("pad-log", "padLog");
  bindCheck("telemetry", "telemetry");
  bindCheck("vcache-stats", "vcacheStats");
  bindCheck("video", "video");
  bindCheck("auto-mount", "autoMount");
  bindCheck("quiet-log", "quietLog");
  bindCheck("update-auto", "autoUpdateCheck");
  bindCheck("vsync", "vsync");
  bindCheck("mods-dump", "modsDump");
  bindCheck("mouse-on", "mouse");
  bindCheck("mouse-invert", "mouseInvertY");
  bindCheck("mouse-invert-x", "mouseInvertX");
  bindCheck("mouse-capture", "mouseCapture");
  bindCheck("rumble-on", "rumble");
  bindCheck("adaptive-on", "adaptiveTriggers");
  bindSelect("pad-light", "padLight");
  bindCheck("pad-light-hit", "padLightHit");
  bindSelect("gyro", "gyro");
  bindCheck("gyro-always", "gyroAlways");
  bindCheck("audio-mute", "audioMute");
  bindSelect("window-mode", "windowMode");
  bindSelect("q-window-mode", "windowMode");
  bindSelect("display", "display");
  bindSelect("res-scale", "resScale");
  bindSelect("upscale", "upscale");
  bindSelect("input-mode", "inputMode");
  bindSelect("window-size", "windowSize");
  bindSelect("q-window-size", "windowSize");
  bindSelect("game-lang", "gameLang");
  bindSelect("aa", "aa");
  bindSelect("aniso", "aniso");
  bindSelect("frame-clock", "frameClockUs");
  bindSelect("shader-jobs", "shaderAsyncJobs");
  bindSelect("shader-sync-hit", "shaderSyncHit");
  bindSelect("drain-spike", "drainSpikeMs");
  bindRange("sharpen", "sharpen", (v) => (v > 0 ? `${Math.round(v * 100)}%` : t("settings.off")));
  bindRange("gamma", "gamma", (v) => v.toFixed(2));
  const signedPct = (v: number) => (Math.abs(v) < 0.005 ? t("settings.off") : `${v > 0 ? "+" : ""}${Math.round(v * 100)}%`);
  const pct = (v: number) => (v > 0.005 ? `${Math.round(v * 100)}%` : t("settings.off"));
  bindRange("vibrance", "vibrance", signedPct);
  bindRange("contrast", "contrast", (v) => (Math.abs(v - 1) < 0.005 ? t("settings.off") : `${Math.round(v * 100)}%`));
  bindRange("vignette", "vignette", pct);
  bindRange("grain", "grain", pct);
  bindRange("lut-strength", "lutStrength", (v) => `${Math.round(v * 100)}%`);
  bindRange("mouse-sens", "mouseSens", (v) => `${v.toFixed(2)}×`);
  bindRange("mouse-dz", "mouseDeadzone", (v) => String(v));
  bindRange("rumble-strength", "rumbleStrength", (v) => `${v}%`);
  bindRange("audio-volume", "audioVolume", (v) => `${v}%`);
  const lutSync = () => {
    $("lut-file").textContent = settings.lutPath ? tilde(settings.lutPath) : t("settings.lutNone");
  };
  syncers.push(lutSync);
  lutSync();
  $("lut-pick").addEventListener("click", async () => {
    const p = await open({ title: t("settings.lut"), filters: [{ name: "PNG", extensions: ["png"] }] });
    if (typeof p === "string") {
      settings.lutPath = p;
      syncAll();
      persist();
    }
  });
  $("lut-clear").addEventListener("click", () => {
    settings.lutPath = "";
    syncAll();
    persist();
  });
  bindText("ffmpeg-avcodec", "ffmpegAvcodec");
  bindText("ffmpeg-avutil", "ffmpegAvutil");
  bindText("play-dir", "playDir", () => refreshStatus());
  bindText("extra-env", "extraEnv");
  bindSelect("audio-device", "audioDevice");
  syncers.push(syncPreset);
  syncPreset();
  $("preset").addEventListener("change", () => {
    const p = PRESETS[$<HTMLSelectElement>("preset").value];
    if (!p) return;
    Object.assign(settings, p);
    syncAll();
    persist();
  });
  // the extra variables are saved as they are typed
  $("extra-env").addEventListener("input", () => {
    settings.extraEnv = $<HTMLTextAreaElement>("extra-env").value;
    persist();
  });
  for (const [btn, key, name] of [["pick-avcodec", "ffmpegAvcodec", "libavcodec"], ["pick-avutil", "ffmpegAvutil", "libavutil"]] as const) {
    $(btn).addEventListener("click", async () => {
      const p = await open({ title: name, defaultPath: "/opt/homebrew/lib", filters: [{ name: "dylib", extensions: ["dylib"] }] });
      if (typeof p === "string") {
        settings[key] = p;
        syncAll();
        persist();
      }
    });
  }
  $("pick-play-dir").addEventListener("click", async () => {
    const p = await open({ directory: true, defaultPath: status?.playDir });
    if (typeof p === "string") {
      settings.playDir = p;
      syncAll();
      persist(() => refreshStatus());
    }
  });
  $("open-play-dir").addEventListener("click", () => status && invoke("reveal", { path: status.playDir }));
  $("finder-icon").addEventListener("click", toggleFinderIcon);
  const ui = $<HTMLSelectElement>("ui-lang");
  ui.value = settings.uiLang;
  ui.addEventListener("change", () => {
    settings.uiLang = ui.value;
    applyLang(ui.value as Lang);
    persist();
  });
  $("reset").addEventListener("click", async () => {
    const yes = await ask(t("settings.resetAsk"), { title: t("settings.reset"), kind: "warning" });
    if (!yes) return;
    const keep: Partial<Settings> = {
      uiLang: settings.uiLang,
      portDir: settings.portDir,
      discPath: settings.discPath,
      discImage: settings.discImage,
      playDir: settings.playDir,
      saveBackupsKeep: settings.saveBackupsKeep,
    };
    Object.assign(settings, DEFAULTS, keep);
    await invoke("save_settings", { settings });
    location.reload();
  });
  syncDependent();
}

/** lib.rs Settings::default() for the options the Restore button resets. */
const DEFAULTS: Partial<Settings> = {
  autoMount: true,
  gameLang: "",
  windowSize: "",
  windowMode: "windowed",
  display: "",
  vsync: true,
  upscale: "",
  resScale: "",
  gameIcon: false,
  aa: "",
  sharpen: 0,
  aniso: 0,
  gammaOverride: false,
  gamma: 1,
  vibrance: 0,
  contrast: 1,
  vignette: 0,
  grain: 0,
  lutPath: "",
  lutStrength: 1,
  mods: [],
  modsDump: false,
  inputMode: "both",
  mouse: true,
  mouseSens: 1,
  mouseInvertY: false,
  mouseInvertX: false,
  mouseDeadzone: 30,
  mouseCapture: true,
  rumble: true,
  rumbleStrength: 100,
  adaptiveTriggers: true,
  padLight: "",
  padLightHit: true,
  gyro: 0,
  gyroAlways: false,
  audioVolume: 100,
  audioMute: false,
  audioDevice: "",
  showFps: true,
  vertexCache: true,
  vertexCacheSplit: true,
  bindChangedOnly: true,
  zeta16Gpu: true,
  fetchMany: true,
  vcacheSparse: true,
  vcacheFrameReuse: true,
  vcacheChurn: true,
  blitGpu: true,
  guestWrite: true,
  shaderCache: true,
  shaderAsync: true,
  shaderAsyncJobs: 4,
  shaderSyncHit: 2,
  frameClockUs: 50,
  padLog: true,
  telemetry: true,
  drainSpikeMs: 100,
  vcacheStats: true,
  fpUnnormVol: true,
  keepAwake: true,
  video: true,
  ffmpegAvcodec: "",
  ffmpegAvutil: "",
  quietLog: false,
  extraEnv: "",
  rebuildSteps: [],
  jobs: 0,
  autoUpdateCheck: true,
};

function syncDependent() {
  $<HTMLInputElement>("gamma").disabled = !settings.gammaOverride;
  for (const id of ["mouse-sens", "mouse-invert", "mouse-invert-x", "mouse-dz", "mouse-capture"]) $<HTMLInputElement>(id).disabled = !settings.mouse;
  $<HTMLInputElement>("rumble-strength").disabled = !settings.rumble;
  $<HTMLInputElement>("audio-volume").disabled = settings.audioMute;
  $<HTMLInputElement>("lut-strength").disabled = !settings.lutPath;
  $<HTMLButtonElement>("lut-clear").disabled = !settings.lutPath;
  $<HTMLInputElement>("vcache-split").disabled = !settings.vertexCache;
  for (const id of ["vcache-sparse", "vcache-reuse", "vcache-churn"]) $<HTMLInputElement>(id).disabled = !settings.vertexCache;
  for (const id of ["shader-jobs", "shader-sync-hit"]) $<HTMLSelectElement>(id).disabled = !settings.shaderAsync;
  for (const id of ["ffmpeg-avcodec", "ffmpeg-avutil", "pick-avcodec", "pick-avutil"]) ($(id) as HTMLInputElement).disabled = !settings.video;
}

function applyLang(l: Lang) {
  setLang(l);
  translateDom();
  fillFixedSelects();
  syncAll();
  renderHome();
  renderFinderIcon();
  renderProgress();
  renderPrereqs();
  renderInstall();
  renderPort();
  renderDisc();
  renderControls();
  renderMods();
  fillScreens();
  fillAudioOutputs();
  renderFeatures();
  renderSaves();
  renderReport();
  renderSessions();
  renderLog();
  renderUpdates();
}

// ---- the Dock / Finder icon from the disc ----------------------------------------
function renderFinderIcon(msg?: string) {
  const can = !!status?.appBundle && status.os === "macos" && (!!status.icon || status.finderIcon);
  show($("finder-icon-row"), can);
  $("finder-icon").textContent = t(status?.finderIcon ? "settings.finderIconUnset" : "settings.finderIconSet");
  $("finder-icon-msg").textContent = msg ?? t("settings.finderIconHint");
}

async function toggleFinderIcon() {
  if (!status) return;
  const btn = $<HTMLButtonElement>("finder-icon");
  btn.disabled = true;
  try {
    status.finderIcon = await invoke<boolean>("finder_icon", { set: !status.finderIcon });
    renderFinderIcon(t("settings.finderIconDone"));
  } catch (e) {
    renderFinderIcon(t("settings.finderIconFailed", { e: String(e) }));
  } finally {
    btn.disabled = false;
  }
}

// ---- home ---------------------------------------------------------------------
let statusSeq = 0;
async function refreshStatus() {
  const seq = ++statusSeq;
  const s = await invoke<Status>("get_status");
  if (seq !== statusSeq) return;
  status = s;
  gameRunning = s.gameRunning;
  rebuildRunning = s.rebuildRunning || rebuildRunning;
  $("app-version").textContent = `v${s.version}`;
  renderHome();
  renderFinderIcon();
  renderPort();
  renderDisc();
  renderFeatures();
  refreshSteam();
}

const TITLE_ID = "BCUS98176";

/** What keeps Play from working, the first one only. */
function blocker(): { title: Key; text: string; act: Key; run: () => void; act2?: Key; run2?: () => void } | null {
  if (!status || !status.hostSupported) return null;
  const b = status.builds;
  if ((!b || !b.ok) && installCard()) return null; // the Install the game card says it all
  if (!b || !b.ok) {
    return {
      title: "block.builds",
      text: b ? t("block.buildsText", { dir: tilde(b.root), missing: b.missing.join(", ") }) : t("block.noPort"),
      act: "block.buildsAct",
      run: () => showView("advanced", "install"),
    };
  }
  if (!status.disc.root && !(settings.autoMount && settings.discImage)) {
    return { title: "block.disc", text: t("block.discText"), act: "disc.mount", run: mountImage, act2: "disc.folder", run2: pickDiscFolder };
  }
  if (status.disc.root && !status.disc.ours) {
    return { title: "block.notOurs", text: t("block.notOursText", { id: status.disc.titleId || "?", dir: status.disc.root }), act: "disc.mount", run: mountImage };
  }
  return null;
}

function renderHome() {
  if (!status) return;
  const d = status.disc;
  const b = status.builds;
  const cover = $<HTMLImageElement>("cover");
  if (status.icon) cover.src = status.icon;
  show(cover, !!status.icon);
  $("hero-art").style.backgroundImage = status.background ? `url(${status.background})` : "";
  $("hero").classList.toggle("no-art", !status.background);
  $("game-title").textContent = d.title || "Resistance 3";
  $("game-id").textContent = d.root ? `${d.titleId || TITLE_ID}${d.appVer ? ` · ${t("home.version")} ${d.appVer}` : ""}` : TITLE_ID;
  const meta: string[] = [];
  if (b?.builtAt) meta.push(`${t("home.builtAt")} ${new Date(b.builtAt * 1000).toLocaleString(lang())}`);
  $("game-meta").textContent = meta.join(" · ");

  const block = blocker();
  show($("home-blocker"), !!block && !gameRunning);
  if (block) {
    $("home-blocker-title").textContent = t(block.title);
    $("home-blocker-text").textContent = block.text;
    $("home-blocker-act").textContent = t(block.act);
    $("home-blocker-act").onclick = block.run;
    const a2 = $("home-blocker-act2");
    show(a2, !!block.act2);
    if (block.act2) {
      a2.textContent = t(block.act2);
      a2.onclick = block.run2 ?? null;
    }
  }
  show($("home-first"), !gameRunning && !block && status.firstBoot && !!b?.ok);
  renderInstall();

  const play = $<HTMLButtonElement>("play");
  $("play-label").textContent = t(gameRunning ? "home.stop" : "home.play");
  play.classList.toggle("stop", gameRunning);
  play.disabled = !gameRunning && (rebuildRunning || !status.hostSupported || !b?.ok);
  show($("run-state"), gameRunning || status.otherGameRunning);
  $("run-state-text").textContent = t(gameRunning ? "home.running" : "home.otherRunning");
  show($("make-shortcut"), !!status.appBundle && status.os === "macos" && !!b?.ok);
  show($("home-unsupported"), !status.hostSupported);
  show($("home-experimental"), status.experimental);
  document.body.classList.toggle("os-windows", status.os === "windows");
  renderSteam();
  renderStatusList();
  renderReport();
  renderUpdates();

  const s = status.lastSave;
  const box = $("save-info");
  box.innerHTML = "";
  if (!s) {
    box.textContent = t("home.noSave");
  } else {
    const st = document.createElement("strong");
    st.textContent = s.subtitle || s.title || s.name;
    const w = document.createElement("div");
    w.className = "small";
    w.textContent = s.modified ? new Date(s.modified * 1000).toLocaleString(lang()) : "";
    box.append(st, w);
  }
}

function renderStatusList() {
  if (!status) return;
  const b = status.builds;
  const d = status.disc;
  const live = !!report?.live && gameRunning;
  const rows: [Key, string, string?][] = [];
  rows.push([
    "home.st.state",
    rebuildRunning
      ? t("home.st.rebuilding")
      : gameRunning
        ? t(live ? "home.st.diag" : "home.st.running")
        : b?.ok
          ? t("home.st.ready")
          : t("home.st.notBuilt"),
    gameRunning || b?.ok ? "ok-text" : "warn-text",
  ]);
  rows.push(["home.st.disc", d.root ? tilde(d.image ?? d.root) : t("home.st.noDisc"), d.root ? undefined : "warn-text"]);
  if (b?.ok) rows.push(["home.st.hdd", t(status.firstBoot ? "home.st.hddPending" : "home.st.hddDone")]);
  if (b) rows.push(["home.st.port", tilde(b.root)]);
  rows.push(["home.st.play", tilde(status.playDir)]);
  const dl = $("status-list");
  dl.replaceChildren();
  for (const [k, v, cls] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = t(k);
    const dd = document.createElement("dd");
    dd.textContent = v;
    if (cls) dd.className = cls;
    dl.append(dt, dd);
  }
}

async function startGame(diagnostic: boolean) {
  const msg = $("home-msg");
  try {
    const r = await invoke<{ log: string; backup: string | null; backupError: string | null; report: string | null; mounted: string | null; firstBoot: boolean; previousLog: string | null }>("play", { diagnostic });
    gameRunning = true;
    msg.textContent =
      (r.report ? t("home.startedDiag", { dir: tilde(r.report) }) : t("home.started", { log: tilde(r.log) })) +
      (r.mounted ? " " + t("home.mounted", { dir: r.mounted }) : "") +
      (r.firstBoot ? " " + t("home.firstBootShort") : "") +
      (r.backup ? t("home.backedUp", { id: r.backup }) : "") +
      (r.backupError ? t("home.backupFailed", { e: r.backupError }) : "");
    $("report-msg").textContent = "";
  } catch (e) {
    const err = String(e);
    msg.textContent = err === "no-disc" ? t("block.discText") : err;
  }
  await refreshStatus();
  refreshReport();
}

$("play").addEventListener("click", async () => {
  if (gameRunning) {
    await invoke("stop_game").catch((e) => ($("home-msg").textContent = String(e)));
    return;
  }
  await startGame(false);
});

$("make-shortcut").addEventListener("click", async () => {
  const btn = $<HTMLButtonElement>("make-shortcut");
  const msg = $("home-msg");
  btn.disabled = true;
  try {
    const path = await invoke<string>("create_play_shortcut");
    msg.textContent = t("home.shortcutDone", { path: tilde(path) });
  } catch (e) {
    msg.textContent = t("home.shortcutFailed", { e: String(e) });
  } finally {
    btn.disabled = false;
  }
});
$("go-saves").addEventListener("click", () => {
  showView("game");
  $("saves-section").scrollIntoView({ behavior: "smooth", block: "start" });
});
$("open-saves").addEventListener("click", async () => {
  const p = await invoke<Record<string, string>>("log_paths");
  invoke("reveal", { path: status?.lastSave?.folder ?? p.saves });
});
$("open-log").addEventListener("click", async () => {
  const p = await invoke<Record<string, string>>("log_paths");
  invoke("reveal", { path: p.game });
});

// ---- the disc ------------------------------------------------------------------
async function refreshDisc() {
  try {
    const d = await invoke<DiscInfo>("disc_status");
    if (status) status.disc = d;
  } catch {
    /* keep the last one */
  }
  renderDisc();
}

function renderDisc() {
  if (!status) return;
  const d = status.disc;
  $("disc-path").textContent = d.root ?? t("disc.none");
  const st = $("disc-state");
  st.className = "pill " + (d.root ? (d.ours ? "" : "bad") : "warn");
  st.textContent = d.root ? (d.ours ? `${d.titleId} ${d.appVer}`.trim() : t("disc.notOurs")) : t("disc.notMounted");
  $("disc-image").textContent = d.image
    ? t("disc.fromImage", { img: tilde(d.image) })
    : settings.discImage
      ? t("disc.imageRemembered", { img: tilde(settings.discImage) })
      : "";
  show($("disc-eject"), !!d.image);
  $("hdd-install").textContent = t(status.firstBoot ? "play.hddPending" : "play.hddDone");
}

async function mountImage() {
  const p = await open({ title: t("disc.mount"), filters: [{ name: t("disc.imageFilter"), extensions: ["iso", "ISO", "dmg", "cdr"] }] });
  if (typeof p !== "string") return;
  const msg = $("disc-msg");
  msg.textContent = t("disc.mounting");
  $("home-msg").textContent = t("disc.mounting");
  try {
    const d = await invoke<DiscInfo>("mount_image", { path: p });
    settings.discImage = p;
    settings.discPath = d.root ?? "";
    msg.textContent = t("disc.mounted", { dir: d.root ?? "" });
    $("home-msg").textContent = msg.textContent;
  } catch (e) {
    msg.textContent = String(e);
    $("home-msg").textContent = String(e);
  }
  await refreshStatus();
}

async function pickDiscFolder() {
  const p = await open({ directory: true, title: t("disc.folder") });
  if (typeof p !== "string") return;
  settings.discPath = p;
  persist(async () => {
    await refreshStatus();
    $("disc-msg").textContent = status?.disc.root ? "" : t("disc.notADisc", { dir: p });
  });
}

$("disc-mount").addEventListener("click", mountImage);
$("disc-folder").addEventListener("click", pickDiscFolder);
$("disc-auto").addEventListener("click", () => {
  settings.discPath = "";
  persist(async () => {
    await refreshStatus();
    $("disc-msg").textContent = status?.disc.root ? t("disc.found", { dir: status.disc.root }) : t("disc.notFound");
  });
});
$("disc-eject").addEventListener("click", async () => {
  const yes = await ask(t("disc.ejectAsk"), { title: t("disc.eject"), kind: "info" });
  if (!yes) return;
  try {
    await invoke("eject_disc");
    $("disc-msg").textContent = t("disc.ejected");
  } catch (e) {
    $("disc-msg").textContent = String(e);
  }
  await refreshStatus();
});

// ---- Add to Steam ----------------------------------------------------------------
interface SteamStatus {
  available: boolean;
  installed: boolean;
  running: boolean;
  users: number;
  added: number;
}
let steam: SteamStatus | null = null;
let steamBusy = false;

async function refreshSteam() {
  steam = await invoke<SteamStatus>("steam_status").catch(() => null);
  renderSteam();
}

function renderSteam() {
  const ok = !!steam?.available && steam.installed && status?.os === "macos" && !!status?.builds?.ok;
  const add = $<HTMLButtonElement>("steam-add");
  const remove = $<HTMLButtonElement>("steam-remove");
  show(add, ok && steam!.added < steam!.users);
  show(remove, ok && steam!.added > 0);
  add.disabled = remove.disabled = steamBusy;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function steamClosed(msg: HTMLElement): Promise<boolean> {
  const st = await invoke<SteamStatus>("steam_status").catch(() => null);
  if (!st?.running) return true;
  const quit = await ask(t("steam.quitAsk"), { title: "Steam", kind: "warning", okLabel: t("steam.quit"), cancelLabel: t("install.cancel") });
  if (!quit) {
    msg.textContent = t("steam.running");
    return false;
  }
  msg.textContent = t("steam.quitting");
  await invoke("steam_quit").catch(() => {});
  for (let i = 0; i < 40; i++) {
    await sleep(500);
    const s = await invoke<SteamStatus>("steam_status").catch(() => null);
    if (!s?.running) {
      await sleep(1000);
      return true;
    }
  }
  msg.textContent = t("steam.quitFailed");
  return false;
}

async function steamAction(kind: "add" | "remove") {
  const msg = $("home-msg");
  if (steamBusy) return;
  if (kind === "add") {
    const yes = await ask(t("steam.confirmAdd"), { title: t("steam.add"), kind: "info", okLabel: t("steam.add"), cancelLabel: t("install.cancel") });
    if (!yes) return;
  }
  steamBusy = true;
  renderSteam();
  try {
    if (!(await steamClosed(msg))) return;
    if (kind === "add") {
      const r = await invoke<{ users: number; art: boolean }>("steam_add");
      msg.textContent = t("steam.added", { n: r.users }) + (r.art ? "" : " " + t("steam.noArt"));
    } else {
      const n = await invoke<number>("steam_remove");
      msg.textContent = t(n ? "steam.removed" : "steam.notThere");
    }
  } catch (e) {
    msg.textContent = String(e) === "steam-running" ? t("steam.running") : t("steam.failed", { e: String(e) });
  } finally {
    steamBusy = false;
    await refreshSteam();
  }
}
$("steam-add").addEventListener("click", () => steamAction("add"));
$("steam-remove").addEventListener("click", () => steamAction("remove"));

// ---- debug mode (report.rs) --------------------------------------------------------
let report: ReportInfo | null = null;
let reportPoll = 0;
let sessions: ReportInfo[] = [];
const busy = new Map<string, string>();
const URL_ISSUE = "https://github.com/erikomis/resistance3-recomp/issues/new";

async function refreshReport() {
  try {
    report = await invoke<ReportInfo | null>("report_info");
  } catch {
    report = null;
  }
  renderReport();
  const live = !!report?.live && gameRunning;
  if (live && !reportPoll) reportPoll = window.setInterval(refreshReport, 2000);
  if (!live && reportPoll) {
    window.clearInterval(reportPoll);
    reportPoll = 0;
  }
  if (advancedTab === "diagnostics") refreshSessions();
}

function renderReport() {
  const r = report;
  const live = !!r?.live && gameRunning;
  $("report-hint").textContent = t(live ? "report.hintLive" : gameRunning ? "report.hintNotDiag" : "report.hintIdle");
  show($("report-play"), !gameRunning);
  $<HTMLButtonElement>("report-play").disabled = rebuildRunning || !status?.hostSupported || !status?.builds?.ok;
  show($("report-capture"), live);
  show($("hero-capture"), live);
  $("report-state").textContent =
    r && live ? t("report.state", { id: r.id, captures: r.captures, passes: r.passes, size: human(r.bytes) }) + (r.pending ? t("report.pending") : "") : "";
}

$("report-play").addEventListener("click", () => startGame(true));
async function captureFrame() {
  let text: string;
  try {
    report = await invoke<ReportInfo>("report_capture");
    text = t("report.captured", { n: report.captures });
  } catch (e) {
    text = String(e);
  }
  $("report-msg").textContent = text;
  $("home-msg").textContent = text;
  renderReport();
}
$("report-capture").addEventListener("click", captureFrame);
$("hero-capture").addEventListener("click", captureFrame);
$("report-issue").addEventListener("click", () => invoke("open_url", { url: URL_ISSUE }));
$("report-refresh").addEventListener("click", () => refreshSessions());
listen("report-changed", () => refreshSessions());

async function refreshSessions() {
  try {
    sessions = await invoke<ReportInfo[]>("report_list");
  } catch (e) {
    $("report-msg").textContent = String(e);
  }
  renderSessions();
}

function sessionTime(id: string): string {
  const m = id.match(/^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})/);
  if (!m) return id;
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]));
  return d.toLocaleString(lang(), { dateStyle: "medium", timeStyle: "short" });
}

function clock(secs: number | null): string {
  if (secs == null) return "-";
  const s = Math.round(secs);
  const h = Math.floor(s / 3600);
  const mm = String(Math.floor((s % 3600) / 60)).padStart(h ? 2 : 1, "0");
  const ss = String(s % 60).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls = "", text = ""): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text) e.textContent = text;
  return e;
}

function sessionEnd(r: ReportInfo): [string, string] {
  if (r.live && gameRunning) return [t("report.live"), "accent"];
  if (!r.debug) return [t("report.oldReport"), "muted-pill"];
  if (r.stopped) return [t("report.stopped"), "muted-pill"];
  if (r.exit && r.exit !== "code=0") return [t("report.crashed", { exit: r.exit }), "bad"];
  return [t("report.ended"), "muted-pill"];
}

function renderSessions() {
  const ul = $("report-sessions");
  ul.replaceChildren();
  show($("report-none"), sessions.length === 0);
  for (const r of sessions) {
    const li = el("li", "session");
    const head = el("div", "row session-head");
    head.append(el("strong", "", sessionTime(r.id)));
    if (r.duration != null) head.append(el("span", "small muted", clock(r.duration)));
    const [end, cls] = sessionEnd(r);
    head.append(el("span", `pill ${cls}`, end));
    if (r.crashReport) head.append(el("span", "pill bad", t("report.crashReport")));
    li.append(head);
    li.append(el("div", "small muted", t("report.rowMeta", { captures: r.captures, passes: r.passes, log: human(r.logBytes), size: human(r.bytes) })));
    const tr = r.triage;
    const sum = el("div", "session-triage");
    if (!tr) {
      sum.append(el("span", "small muted", t("report.triageNone")));
    } else {
      const counts = el("div", "row");
      counts.append(el("span", tr.errors ? "pill bad" : "pill muted-pill", t("report.triageCounts", { errors: tr.errors, warnings: tr.warnings, lines: tr.lines })));
      if (tr.fpsAvg != null) counts.append(el("span", "pill muted-pill", t("report.fps", { avg: tr.fpsAvg.toFixed(1), min: (tr.fpsMin ?? 0).toFixed(1) })));
      if (tr.stale) counts.append(el("span", "small warn-text", t("report.stale")));
      sum.append(counts);
      if (!tr.top.length) sum.append(el("p", "small muted", t("report.clean")));
      else {
        const ol = el("ol", "issues");
        for (const g of tr.top.slice(0, 8)) {
          const item = el("li", `sev-${g.severity === "error" ? "error" : "warn"}`);
          item.append(el("span", "issue-title", g.title));
          item.append(el("span", "small muted", ` ×${g.count} · ${t("report.line", { n: g.firstLine })}`));
          ol.append(item);
        }
        sum.append(ol);
      }
    }
    li.append(sum);
    const act = el("div", "row");
    const work = busy.get(r.id);
    const analyse = el("button", "", t(work === "triage" ? "report.analysing" : "report.analyse"));
    analyse.disabled = !!work;
    analyse.addEventListener("click", () => sessionAction(r, "triage"));
    const zip = el("button", "", t("report.zip") + (work === "zip" ? "…" : ""));
    zip.disabled = !!work || (r.live && gameRunning);
    zip.addEventListener("click", () => sessionAction(r, "zip"));
    const openB = el("button", "link", t("report.open"));
    openB.addEventListener("click", () => invoke("reveal", { path: r.dir }));
    act.append(analyse, zip, openB);
    if (tr) {
      const md = el("button", "link", t("report.openTriage"));
      md.addEventListener("click", () => invoke("reveal", { path: tr.md }));
      act.append(md);
    }
    if (r.zip) {
      const z = el("button", "link", t("report.showZip"));
      z.addEventListener("click", () => invoke("reveal", { path: r.zip! }));
      act.append(z);
    }
    if (!(r.live && gameRunning)) {
      const del = el("button", "link danger-link", t("report.delete"));
      del.addEventListener("click", async () => {
        if (!(await ask(t("report.deleteAsk"), { title: t("report.delete"), kind: "warning" }))) return;
        await invoke("report_delete", { id: r.id }).catch((e) => ($("report-msg").textContent = String(e)));
        refreshSessions();
      });
      act.append(del);
    }
    li.append(act);
    ul.append(li);
  }
}

async function sessionAction(r: ReportInfo, what: "triage" | "zip") {
  const msg = $("report-msg");
  busy.set(r.id, what);
  msg.textContent = t(what === "zip" ? "report.zipping" : "report.analysing");
  renderSessions();
  try {
    const got =
      what === "zip"
        ? await invoke<ReportInfo>("report_zip", { id: r.id, notes: $<HTMLTextAreaElement>("report-notes").value })
        : await invoke<ReportInfo>("report_triage", { id: r.id });
    sessions = sessions.map((s) => (s.id === got.id ? got : s));
    msg.textContent = what === "zip" ? t("report.zipped", { file: tilde(got.zip ?? ""), size: human(got.zipBytes) }) : "";
    if (what === "zip" && got.zip) invoke("reveal", { path: got.zip });
  } catch (e) {
    msg.textContent = String(e);
  }
  busy.delete(r.id);
  renderSessions();
}

// ---- Home: Install the game (macOS) ------------------------------------------------
// One button from the disc image to Play: the disc, Apple's Command Line Tools
// (their own installer, waited for), then start_install (the sources when
// there is no checkout, tools/install.sh: the build tools, the toolkit,
// decrypt, analyse, lift, SPU, build) with one progress bar. Pressing it again
// after a quit or a failure continues where it stopped.
/** A full install's minutes: the lift is ~41,500 functions in 24 units and
 * the build compiles them (README: "The first build compiles a lot of
 * generated code"); more on a smaller Mac or a slow connection. */
const INSTALL_MINUTES = "15–45";
let installOutcome: "" | "done" | "failed" | "cancelled" = "";
let installFacts: Prereqs | null = null;
let cltWait = 0;
let installBusy = false;

/** The Install the game card replaces the "not built" bar: macOS, nothing built. */
function installCard(): boolean {
  if (!status || !status.hostSupported || status.os !== "macos") return false;
  return !status.builds?.ok || (progress.kind === "install" && (rebuildRunning || installOutcome !== ""));
}

async function refreshInstallFacts() {
  if (!installCard()) return;
  installFacts = await invoke<Prereqs>("check_prereqs").catch(() => installFacts);
  renderInstall();
}

/** The plain-language reason an install stopped, from the stage and the log. */
function installError(): { text: string; detail: string } {
  const log = progress.log.slice(-400).join("\n");
  const detail = progress.errors[progress.errors.length - 1] ?? "";
  const stage = progress.stage()?.id;
  let key: Key = "inst.err.generic";
  if (/No space left on device|not enough free disk space/i.test(log)) key = "inst.err.disk";
  else if (/could not download|Could not resolve host|Failed to connect|unable to access|Connection timed out|Network is unreachable/i.test(log)) key = "inst.err.net";
  else if (stage) key = `inst.err.${stage}` as Key;
  return { text: t(key), detail };
}

function stageLabel(id: StepId | undefined): string {
  return id ? t(`inst.stage.${id}` as Key) : t("inst.starting");
}

function renderInstall() {
  const card = $("home-install");
  const on = installCard() && !gameRunning;
  show(card, on);
  if (!on) return;
  const live = progress.kind === "install" && rebuildRunning;
  const f = installFacts;
  const discImg = settings.discImage || status?.disc.image || status?.disc.root || "";
  const pill = $("inst-pill");
  pill.className = "pill " + (installOutcome === "done" ? "" : "warm");
  show(pill, live || installOutcome === "done");
  pill.textContent = installOutcome === "done" ? t("inst.pillDone") : t("inst.pillRunning");

  $("inst-lead").textContent = live
    ? t("inst.leadRunning")
    : t("inst.lead", { min: INSTALL_MINUTES, gb: f?.needGb || 6 });
  $("inst-disc").textContent = discImg ? t("inst.disc", { img: tilde(discImg) }) : f?.elfs ? "" : t("inst.noDisc");

  show($("inst-live"), live || installOutcome === "failed" || installOutcome === "cancelled");
  const st = progress.stage();
  $("inst-stage").textContent = cltWait ? t("inst.cltWaiting") : stageLabel(st?.id);
  const frac = progress.fraction();
  $("inst-bar").style.width = `${((live || installOutcome !== "" ? frac : 0) * 100).toFixed(1)}%`;
  const eta = progress.etaMinutes();
  const n = progress.steps.length;
  const i = st ? progress.steps.indexOf(st) + 1 : 0;
  $("inst-text").textContent = live
    ? `${t("inst.stepN", { i, n })} · ${Math.floor(frac * 100)}%` + (eta !== null ? ` · ${t("install.eta", { min: Math.max(1, Math.round(eta)) })}` : "")
    : "";

  const failed = installOutcome === "failed" && !live;
  show($("inst-error"), failed);
  if (failed) {
    const e = installError();
    $("inst-error-text").textContent = e.text;
    $("inst-error-detail").textContent = e.detail;
  }
  const start = $<HTMLButtonElement>("inst-start");
  const done = installOutcome === "done";
  show(start, !live && !cltWait && !done);
  start.disabled = installBusy || gameRunning || (rebuildRunning && !live);
  start.textContent = t(failed || installOutcome === "cancelled" ? "inst.retry" : "inst.start");
  show($("inst-pick"), !live && !cltWait && !done);
  $("inst-pick").textContent = t(discImg ? "inst.pickOther" : "inst.pickDisc");
  show($("inst-cancel"), live || !!cltWait);
  for (const id of ["inst-copy", "inst-showlog"]) show($(id), progress.kind === "install" && progress.log.length > 0);
  show($("inst-report"), failed);
}

/** Wait for Apple's Command Line Tools installer: true once they are there. */
function waitForClt(): Promise<boolean> {
  return new Promise((resolve) => {
    const tick = async () => {
      if (!cltWait) return resolve(false); // cancelled
      const p = await invoke<Prereqs>("check_prereqs").catch(() => null);
      if (p?.clt) {
        window.clearInterval(cltWait);
        cltWait = 0;
        installFacts = p;
        renderInstall();
        resolve(true);
      }
    };
    cltWait = window.setInterval(tick, 5000);
    renderInstall();
  });
}

async function installGame() {
  if (installBusy || rebuildRunning) return;
  installBusy = true;
  const msg = $("inst-msg");
  msg.textContent = t("prereq.checking");
  renderInstall();
  try {
    let p = await invoke<Prereqs>("check_prereqs");
    installFacts = p;
    // 1. the disc
    if (!p.disc && !p.elfs && !settings.discImage) {
      await mountImage();
      p = await invoke<Prereqs>("check_prereqs");
      installFacts = p;
      if (!p.disc) {
        msg.textContent = t("inst.noDisc");
        return;
      }
    }
    // the decrypt step: RPCS3, unless EBOOT.elf is there or the port decrypts itself
    if (!p.decrypt) {
      msg.textContent = t("inst.needRpcs3");
      return;
    }
    // 2. disk space and time
    if (p.freeGb !== null && p.freeGb < p.needGb) {
      const go = await ask(t("inst.diskLow", { free: p.freeGb, gb: p.needGb }), { title: t("inst.title"), kind: "warning", okLabel: t("inst.anyway"), cancelLabel: t("install.cancel") });
      if (!go) {
        msg.textContent = "";
        return;
      }
    } else if (installOutcome === "") {
      const go = await ask(t("inst.ask", { min: INSTALL_MINUTES, gb: p.needGb || 6 }), { title: t("inst.title"), kind: "info", okLabel: t("inst.start"), cancelLabel: t("install.cancel") });
      if (!go) {
        msg.textContent = "";
        return;
      }
    }
    // 3. Apple's Command Line Tools (the compiler and git): their installer, waited for
    if (!p.clt) {
      msg.textContent = t("inst.clt");
      await invoke("install_clt").catch(() => undefined); // already open / installing: keep waiting
      if (!(await waitForClt())) {
        msg.textContent = "";
        return;
      }
    }
    // 4. everything else, in one go
    msg.textContent = "";
    progress.reset([], "install");
    installOutcome = "";
    $("log").textContent = "";
    $("install-msg").textContent = "";
    await invoke<string>("start_install");
    rebuildRunning = true;
    // no sources here: the install clones its own, and a port folder set by
    // hand that cannot be rebuilt gave way to them (start_install)
    if (!p.sources) settings.portDir = "";
  } catch (e) {
    const err = String(e);
    msg.textContent = err === "no-disc" ? t("inst.noDisc") : err === "clt" ? t("inst.clt") : err === "rpcs3" ? t("inst.needRpcs3") : err;
  } finally {
    installBusy = false;
    renderProgress();
    renderHome();
  }
}

$("inst-start").addEventListener("click", installGame);
$("inst-pick").addEventListener("click", async () => {
  await mountImage();
  await refreshInstallFacts();
});
$("inst-cancel").addEventListener("click", async () => {
  if (cltWait) {
    window.clearInterval(cltWait);
    cltWait = 0;
    $("inst-msg").textContent = "";
    renderInstall();
    return;
  }
  const yes = await ask(t("inst.askCancel"), { title: t("install.cancel"), kind: "warning", okLabel: t("install.cancel"), cancelLabel: t("inst.keepGoing") });
  if (!yes) return;
  progress.cancelled = true;
  invoke("cancel_rebuild");
});
$("inst-copy").addEventListener("click", async () => {
  await navigator.clipboard.writeText(progress.log.join("\n"));
  $("inst-msg").textContent = t("inst.copied");
});
$("inst-showlog").addEventListener("click", async () => {
  const p = await invoke<Record<string, string>>("log_paths");
  invoke("reveal", { path: p.install });
});
$("inst-report").addEventListener("click", async () => {
  await navigator.clipboard.writeText(progress.log.slice(-300).join("\n")).catch(() => undefined);
  $("inst-msg").textContent = t("inst.reportCopied");
  invoke("open_url", { url: URL_ISSUE });
});

// ---- install: 1. requirements ------------------------------------------------------
let prereqs: Prereqs | null = null;
let setupRunning = false;
let cltPoll = 0;
const ICON: Record<string, string> = { ok: "✓", warn: "!", fail: "✕", info: "i", optional: "–" };

function checkLabel(name: string): string {
  const k = `prereq.name.${name}` as Key;
  const v = t(k);
  return v === k ? name : v;
}

/** A check's detail line, translated (the English text when there is no key). */
function checkDetail(c: CheckItem): string {
  if (!c.key) return c.path ? "" : c.message;
  const k = `prereq.msg.${c.key}` as Key;
  const v = t(k, c.vars);
  return v === k ? c.message : v;
}

let prereqSeq = 0;
async function refreshPrereqs() {
  $("prereq-msg").textContent = t("prereq.checking");
  const seq = ++prereqSeq;
  const p = await invoke<Prereqs>("check_prereqs");
  if (seq !== prereqSeq) return;
  prereqs = p;
  $("prereq-msg").textContent = "";
  renderPrereqs();
  if (cltPoll && prereqs.clt) {
    window.clearInterval(cltPoll);
    cltPoll = 0;
  }
}

function prereqActions(c: CheckItem): HTMLButtonElement[] {
  if (c.level !== "warn" && c.level !== "fail") return [];
  const button = (label: Key, run: () => unknown) => {
    const b = document.createElement("button");
    b.textContent = t(label);
    b.addEventListener("click", () => run());
    return b;
  };
  switch (c.name) {
    case "xcode-clt":
      return [button("prereq.installClt", installClt)];
    case "disc":
      return [button("disc.mount", mountImage)];
    case "rpcs3":
      return [button("prereq.getRpcs3", () => invoke("open_url", { url: "https://rpcs3.net/download" }))];
    case "deps":
      return status?.os === "macos" ? [button("prereq.getBrew", () => invoke("open_url", { url: "https://brew.sh/" }))] : [];
    case "rebuild":
    case "builds":
      return [button("port.pickShort", pickPortDir)];
    default:
      return [];
  }
}

function renderPrereqs() {
  const p = prereqs;
  const list = $("prereqs");
  list.innerHTML = "";
  const supported = status?.hostSupported ?? p?.supported ?? true;
  show($("install-unsupported"), !supported);
  show($("install-experimental"), !!status?.experimental);
  for (const id of ["card-prereqs", "card-port", "card-run"]) $(id).classList.toggle("disabled", !supported);
  if (!p || !p.supported) {
    $("prereq-summary").textContent = "";
    show($("prereq-fix"), false);
    return;
  }
  const fails = p.checks.filter((c) => c.level === "fail");
  const warns = p.checks.filter((c) => c.level === "warn");
  // what needs doing first, then the rest in their order
  for (const c of [...fails, ...warns, ...p.checks.filter((c) => c.level !== "fail" && c.level !== "warn")]) {
    const li = el("li", `check check-${c.level}`);
    li.append(el("span", "check-ico", ICON[c.level] ?? "·"));
    const body = el("div", "check-body");
    const title = el("div", "check-title");
    title.append(el("b", "", checkLabel(c.name)));
    if (c.optional) title.append(el("span", "check-tag", t("prereq.optionalTag")));
    body.append(title);
    const detail = checkDetail(c);
    if (detail) body.append(el("div", "check-detail", detail));
    if (c.path) {
      const path = el("div", "check-path", tilde(c.path));
      path.title = c.path;
      body.append(path);
    }
    const acts = prereqActions(c);
    if (acts.length) {
      const row = el("div", "check-actions");
      row.append(...acts);
      body.append(row);
    }
    li.append(body);
    list.appendChild(li);
  }
  const sum = $("prereq-summary");
  sum.className = "pill " + (fails.length ? "bad" : warns.length ? "warn" : "");
  sum.textContent = fails.length
    ? t("prereq.missingN", { n: fails.length })
    : warns.length
      ? t(warns.length === 1 ? "prereq.readyWarning" : "prereq.readyWarnings", { n: warns.length })
      : t("prereq.allOk");
  $("card-prereqs").classList.toggle("done", p.ok);
  const mac = status?.os === "macos";
  show($("prereq-fix"), mac && (!p.clt || (!p.deps && !!p.sources && p.bootstrap)));
  $<HTMLButtonElement>("prereq-fix").disabled = setupRunning || rebuildRunning;
  $("prereq-fix").textContent = p.clt ? t("prereq.fixDeps") : t("prereq.installClt");
  show($("setup-cancel"), setupRunning);
}

async function installClt() {
  const yes = await ask(t("prereq.askClt"), { title: t("prereq.installClt"), kind: "info" });
  if (!yes) return;
  try {
    await invoke("install_clt");
    $("prereq-msg").textContent = t("prereq.cltStarted");
    if (!cltPoll) cltPoll = window.setInterval(refreshPrereqs, 15000);
  } catch (e) {
    $("prereq-msg").textContent = String(e);
  }
}

$("prereq-fix").addEventListener("click", async () => {
  if (!prereqs) return;
  if (!prereqs.clt) return installClt();
  if (prereqs.deps) return;
  const yes = await ask(t("prereq.askDeps", { dir: tilde(prereqs.depsDir) }), { title: t("prereq.fixDeps"), kind: "info" });
  if (!yes) return;
  const pre = $("setup-log");
  pre.textContent = "";
  show(pre, true);
  try {
    await invoke("install_deps");
    setupRunning = true;
    $("prereq-msg").textContent = t("prereq.depsRunning");
  } catch (e) {
    $("prereq-msg").textContent = String(e);
  }
  renderPrereqs();
});
$("prereq-recheck").addEventListener("click", refreshPrereqs);
$("setup-cancel").addEventListener("click", () => invoke("cancel_setup"));
listen<string>("setup-line", (ev) => {
  const pre = $("setup-log");
  pre.textContent += ev.payload + "\n";
  pre.scrollTop = pre.scrollHeight;
});
listen<number>("setup-exit", (ev) => {
  setupRunning = false;
  $("prereq-msg").textContent = ev.payload === 0 ? t("prereq.depsDone") : t("prereq.depsFailed", { code: ev.payload });
  refreshPrereqs();
});

// ---- install: 2. the port folder --------------------------------------------------
let found: Builds[] = [];

function buildsSummary(b: Builds): string {
  if (b.ok) {
    return t("port.ok", { date: b.builtAt ? new Date(b.builtAt * 1000).toLocaleString(lang()) : "?" });
  }
  return t("port.missing", { missing: b.missing.join(", ") });
}

function renderPort() {
  const input = $<HTMLInputElement>("port-dir");
  if (document.activeElement !== input) input.value = settings.portDir;
  const b = status?.builds ?? null;
  const box = $("port-builds");
  show(box, !!b);
  const sum = $("port-summary");
  if (b) {
    box.replaceChildren(
      el("div", "", (settings.portDir ? "" : t("port.autoFound") + " ") + tilde(b.root)),
      el("div", b.ok ? "ok-text small" : "warn-text small", buildsSummary(b)),
      el("div", "small muted", b.rebuildSh ? t("port.canRebuild") : t("port.noRebuild")),
    );
    sum.className = "pill " + (b.ok ? "" : "warn");
    sum.textContent = b.ok ? t("port.ready") : t("port.notReady");
  } else {
    sum.className = "pill warn";
    sum.textContent = t("port.none");
  }
  $("port-builds").closest(".card")!.classList.toggle("done", !!b?.ok);
  const ul = $("port-list");
  ul.replaceChildren();
  for (const f of found) {
    if (b && f.root === b.root) continue;
    const li = el("li");
    const what = el("div", "grow");
    what.append(el("div", "", tilde(f.root)), el("div", f.ok ? "ok-text small" : "small muted", buildsSummary(f)));
    const use = el("button", "", t("port.use"));
    use.addEventListener("click", () => setPortDir(f.root));
    li.append(what, use);
    ul.append(li);
  }
  // the rebuild card: only for the repository that has tools/rebuild.sh
  const canRebuild = !!b?.rebuildSh;
  $<HTMLButtonElement>("start").disabled = rebuildRunning || !canRebuild || gameRunning;
  $("run-lead-extra")?.remove();
  if (!canRebuild) {
    const p = el("p", "hint warn-text", t("run.needRepo"));
    p.id = "run-lead-extra";
    $("steps-pick").before(p);
  }
}

function setPortDir(p: string) {
  settings.portDir = p;
  $<HTMLInputElement>("port-dir").value = p;
  persist(async () => {
    await refreshStatus();
    refreshPrereqs();
  });
}

async function pickPortDir() {
  showView("advanced", "install");
  const p = await open({ directory: true, title: t("port.title"), defaultPath: settings.portDir || undefined });
  if (typeof p === "string") setPortDir(p);
}

async function findPortDirs() {
  $("port-summary").textContent = t("port.searching");
  found = await invoke<Builds[]>("find_port_dirs").catch(() => []);
  renderPort();
  if (!found.length) $("port-summary").textContent = t("port.none");
}

$("pick-port-dir").addEventListener("click", pickPortDir);
$("find-port-dirs").addEventListener("click", findPortDirs);
$("port-dir").addEventListener("change", () => setPortDir($<HTMLInputElement>("port-dir").value.trim()));

// ---- install: 3. the rebuild -----------------------------------------------------
function renderStepsPick() {
  const box = $("steps-pick");
  box.replaceChildren();
  const chosen = settings.rebuildSteps?.length ? settings.rebuildSteps : PICK_IDS;
  for (const s of PICK_IDS) {
    const l = el("label", "check");
    const c = el("input");
    c.type = "checkbox";
    c.checked = chosen.includes(s);
    c.addEventListener("change", () => {
      const all = Array.from(box.querySelectorAll<HTMLInputElement>("input")).map((i, n) => [i.checked, PICK_IDS[n]] as const);
      const on = all.filter(([v]) => v).map(([, n]) => n);
      settings.rebuildSteps = on.length === all.length ? [] : on;
      persist();
    });
    l.append(c, el("span", "", t(`step.${s}` as Key)));
    box.append(l);
  }
  const jobs = $<HTMLInputElement>("jobs");
  jobs.value = String(settings.jobs || 0);
}
$("jobs").addEventListener("change", () => {
  settings.jobs = Math.max(0, Math.min(64, Number($<HTMLInputElement>("jobs").value) || 0));
  persist();
});

async function startRebuild() {
  const steps = settings.rebuildSteps?.length ? settings.rebuildSteps : [];
  if (!steps.length && !(await ask(t("run.askAll"), { title: t("run.start"), kind: "info" }))) return;
  if (prereqs && !prereqs.ok && !(await ask(t("install.askMissing"), { title: t("run.start"), kind: "warning" }))) return;
  // without the build tools the rebuild installs them first (tools/bootstrap_deps.sh)
  progress.reset(prereqs && !prereqs.deps && status?.os === "macos" ? [...(steps.length ? steps : PICK_IDS), "deps"] : steps);
  $("log").textContent = "";
  $("install-msg").textContent = "";
  try {
    await invoke("start_rebuild", { req: { steps, jobs: settings.jobs || null } });
    rebuildRunning = true;
  } catch (e) {
    $("install-msg").textContent = String(e);
  }
  renderProgress();
  renderHome();
}
$("start").addEventListener("click", startRebuild);
$("cancel").addEventListener("click", () => {
  progress.cancelled = true;
  invoke("cancel_rebuild");
});
$("copy-log").addEventListener("click", () => navigator.clipboard.writeText(progress.log.join("\n")));

function renderProgress() {
  show($("cancel"), rebuildRunning);
  $<HTMLButtonElement>("start").disabled = rebuildRunning || !status?.builds?.rebuildSh || gameRunning;
  const steps = $("steps");
  steps.innerHTML = "";
  for (const s of progress.steps) {
    const li = document.createElement("li");
    li.className = `step-${s.state}`;
    li.innerHTML = `<span class="name"></span><span class="state"></span>`;
    li.querySelector(".name")!.textContent = t(`step.${s.id}` as Key);
    li.querySelector(".state")!.textContent = t(`state.${s.state}` as Key) + (s.secs ? ` · ${clock(s.secs)}` : "");
    steps.appendChild(li);
  }
  const frac = progress.fraction();
  $("bar").style.width = `${(frac * 100).toFixed(1)}%`;
  const eta = progress.etaMinutes();
  $("progress-text").textContent = rebuildRunning
    ? `${Math.floor(frac * 100)}%` + (eta !== null ? ` · ${t("install.eta", { min: Math.max(1, Math.round(eta)) })}` : "")
    : "";
  renderInstall();
}

let frame = 0;
function flushLog() {
  frame = 0;
  const pre = $("log");
  const atBottom = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 30;
  pre.textContent = progress.log.slice(-2000).join("\n");
  if (atBottom) pre.scrollTop = pre.scrollHeight;
  renderProgress();
}
listen<string>("rebuild-line", (ev) => {
  progress.feed(ev.payload);
  if (!frame) frame = requestAnimationFrame(flushLog);
});
listen<number>("rebuild-exit", (ev) => {
  rebuildRunning = false;
  const code = ev.payload;
  const msg = $("install-msg");
  if (progress.cancelled) msg.textContent = t("install.cancelled");
  else if (code === 0) msg.textContent = t(progress.kind === "pull" ? "update.pulled" : "install.done");
  else msg.textContent = t("install.failed", { code });
  msg.className = code === 0 ? "ok" : "bad";
  progress.finish(code === 0);
  if (progress.kind === "install") {
    installOutcome = progress.cancelled ? "cancelled" : code === 0 ? "done" : "failed";
    $("inst-msg").textContent = installOutcome === "done" ? t("inst.done") : installOutcome === "cancelled" ? t("inst.cancelled") : "";
  }
  flushLog();
  refreshStatus();
  refreshUpdates(false);
});

const gameExitWaiters: (() => void)[] = [];
listen<number>("game-exit", (ev) => {
  gameRunning = false;
  gameExitWaiters.splice(0).forEach((f) => f());
  $("home-msg").textContent = t("home.exited", { code: ev.payload });
  refreshStatus();
  refreshReport();
  if ($("tab-log").classList.contains("active")) showLog();
});

// ---- start ---------------------------------------------------------------------
// Uncaught errors go to the launcher's stderr too (the window has no console
// outside a development build).
const reportError = (what: unknown) => {
  const m = what instanceof Error ? `${what.message}\n${what.stack ?? ""}` : String(what);
  invoke("frontend_log", { message: m }).catch(() => undefined);
};
window.addEventListener("error", (e) => reportError(e.error ?? e.message));
window.addEventListener("unhandledrejection", (e) => reportError(e.reason));

async function main() {
  settings = await invoke<Settings>("get_settings");
  setLang(settings.uiLang as Lang);
  translateDom();
  bindSettings();
  renderStepsPick();
  initControls();
  initMods({
    enabled: () => settings.mods ?? [],
    setEnabled: (names) => {
      settings.mods = names;
      persist();
    },
  });
  initLog();
  initSaves({
    keep: () => settings.saveBackupsKeep ?? 10,
    setKeep: (n) => {
      settings.saveBackupsKeep = n;
      persist();
    },
  });
  initUpdates({
    auto: () => settings.autoUpdateCheck ?? true,
    busy: () => rebuildRunning || gameRunning,
    canRebuild: () => !rebuildRunning && !gameRunning && !!status?.builds?.rebuildSh,
    rebuild: () => {
      showView("advanced", "install");
      startRebuild();
    },
    pull: async () => {
      showView("advanced", "install");
      progress.reset([], "pull");
      $("log").textContent = "";
      try {
        await invoke("pull_sources");
        rebuildRunning = true;
      } catch (e) {
        $("install-msg").textContent = String(e);
      }
      renderProgress();
    },
  });
  applyLang(settings.uiLang as Lang);
  await refreshStatus();
  void refreshInstallFacts();
  refreshReport();
  refreshShaderCache();
  void refreshUpdates(settings.autoUpdateCheck ?? true);
  if (status && !status.builds) void findPortDirs();
  // opened by the Play shortcut (--play): start the game as the Play button would
  const playNow = await invoke<boolean>("take_play_request").catch(() => false);
  // --view <page>[:<tab>] on the command line (docs screenshots)
  const view = await invoke<string | null>("take_start_view").catch(() => null);
  const [page, tab] = (view ?? "").split(":");
  if (playNow && status?.builds?.ok && status.hostSupported && !gameRunning && !rebuildRunning) await startGame(false);
  else if (status && !status.builds?.ok && !installCard()) showView("advanced", "install");
  else if (page && ["home", "graphics", "performance", "game", "controls", "advanced"].includes(page)) showView(page, tab || undefined);
}
main().catch(reportError);
