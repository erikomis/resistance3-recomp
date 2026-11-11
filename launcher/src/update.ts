// Advanced > Updates (src-tauri/src/update.rs): the port checkout's sources
// (git fetch; behind its upstream, or newer than the builds) and the newest
// launcher release on GitHub. Checked once per session on start when the
// setting is on, and on "Check again". Home shows a bar when there is news.
import { invoke } from "@tauri-apps/api/core";
import { lang, t } from "./i18n";

interface Sources {
  git: boolean;
  branch: string;
  commit: string;
  subject: string;
  commitTime: number;
  upstream: string;
  behind: number;
  ahead: number;
  dirty: number;
  sourcesTime: number;
  fetched: boolean;
  error: string | null;
}
interface AppUpdate {
  current: string;
  latest: string | null;
  newer: boolean;
  url: string | null;
  notes: string | null;
  disabled: boolean;
  error: string | null;
}
interface UpdateInfo {
  sources: Sources;
  rebuildNeeded: boolean;
  builtAt: number;
  app: AppUpdate;
}

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
let info: UpdateInfo | null = null;
let online = false;
let checking = false;
let opts: {
  auto: () => boolean;
  busy: () => boolean;
  canRebuild: () => boolean;
  rebuild: () => void;
  pull: () => void;
};

const date = (s: number) => (s ? new Date(s * 1000).toLocaleString(lang()) : "?");

/** `net`: also ask the network (git fetch, GitHub). */
export async function refreshUpdates(net: boolean) {
  if (checking) return;
  checking = true;
  renderUpdates();
  try {
    info = await invoke<UpdateInfo>("check_updates", { online: net });
    online = online || net;
  } catch {
    info = null;
  }
  checking = false;
  renderUpdates();
}

function line(cls: string, text: string): HTMLElement {
  const d = document.createElement("div");
  d.className = cls;
  d.textContent = text;
  return d;
}

export function renderUpdates() {
  if (!opts) return;
  const src = $("src-info");
  const app = $("app-info");
  src.replaceChildren();
  app.replaceChildren();
  $<HTMLButtonElement>("update-check").disabled = checking;
  $("update-check").textContent = t(checking ? "update.checking" : "update.check");
  const s = info?.sources;
  if (!info || !s) {
    src.append(line("small muted", t(checking ? "update.checking" : "update.notChecked")));
  } else if (!s.git) {
    src.append(line("small muted", t("update.noGit")));
  } else {
    src.append(line("", t("update.at", { branch: s.branch, commit: s.commit, subject: s.subject, date: date(s.commitTime) })));
    if (s.error) src.append(line("small warn-text", t("update.fetchFailed", { e: s.error })));
    if (!s.upstream) src.append(line("small muted", t("update.noUpstream")));
    else if (s.behind) src.append(line("warn-text", t("update.behind", { n: s.behind, up: s.upstream })));
    else if (online && s.fetched) src.append(line("ok-text small", t("update.upToDate", { up: s.upstream })));
    if (s.ahead) src.append(line("small muted", t("update.ahead", { n: s.ahead })));
    if (s.dirty) src.append(line("small muted", t("update.dirty", { n: s.dirty })));
    if (info.rebuildNeeded) src.append(line("warn-text", t("update.rebuildNeeded", { built: date(info.builtAt), src: date(s.sourcesTime) })));
  }
  const pull = $<HTMLButtonElement>("src-pull");
  pull.classList.toggle("hidden", !(s?.behind && !s.dirty));
  pull.disabled = opts.busy();
  const rb = $<HTMLButtonElement>("src-rebuild");
  rb.classList.toggle("hidden", !info?.rebuildNeeded);
  rb.disabled = !opts.canRebuild();

  const a = info?.app;
  if (!a) app.append(line("small muted", t("update.notChecked")));
  else if (a.disabled) app.append(line("small muted", t("update.disabled", { cur: a.current })));
  else if (!online) app.append(line("small muted", t("update.appCurrent", { cur: a.current })));
  else if (a.newer) {
    app.append(line("warn-text", t("update.newRelease", { v: a.latest ?? "", cur: a.current })));
    if (a.notes) app.append(line("update-notes", a.notes));
  } else if (a.error) app.append(line("small muted", t("update.appError", { cur: a.current, e: a.error })));
  else app.append(line("ok-text", t("update.appUpToDate", { cur: a.current })));
  $("app-open").classList.toggle("hidden", !a?.newer || !a.url);

  // Home: one bar for whatever is new
  const news: string[] = [];
  if (s?.behind) news.push(t("update.behind", { n: s.behind, up: s.upstream }));
  if (info?.rebuildNeeded) news.push(t("update.rebuildShort"));
  if (a?.newer) news.push(t("update.newRelease", { v: a.latest ?? "", cur: a.current }));
  $("home-update").classList.toggle("hidden", !news.length);
  $("home-update-text").textContent = news.join(" ");
}

export function initUpdates(o: typeof opts) {
  opts = o;
  $("update-check").addEventListener("click", () => refreshUpdates(true));
  $("src-pull").addEventListener("click", () => opts.pull());
  $("src-rebuild").addEventListener("click", () => opts.rebuild());
  $("app-open").addEventListener("click", () => info?.app.url && invoke("open_url", { url: info.app.url }));
  $("home-update-go").addEventListener("click", () => {
    document.querySelector<HTMLElement>('.nav[data-view="advanced"]')?.click();
    document.querySelector<HTMLElement>('.tab[data-tab="updates"]')?.click();
  });
}
