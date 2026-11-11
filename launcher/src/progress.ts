// The rebuild's and the install's progress, read from the scripts' output:
// each step starts with a "==> <step>" line (zsh's bold escapes stripped), the
// next one ends it, "==> done" ends the run; tools/bootstrap_deps.sh's
// "==> [k/n] <component>" lines move the deps step along. The weights are a
// step's rough share of a full install on an Apple-silicon Mac (the lift and
// the compile dominate).

export const STEP_IDS = ["sources", "deps", "toolkit", "venv", "decrypt", "analyse", "lift", "spu", "build"] as const;
export type StepId = (typeof STEP_IDS)[number];
/** The steps Advanced > Install / rebuild lets the player pick. */
export const PICK_IDS: StepId[] = ["toolkit", "decrypt", "analyse", "lift", "spu", "build"];
const WEIGHT: Record<StepId, number> = { sources: 1, deps: 8, toolkit: 2, venv: 3, decrypt: 2, analyse: 6, lift: 35, spu: 6, build: 37 };

export interface Step {
  id: StepId;
  state: "pending" | "running" | "done" | "error" | "skipped";
  start: number;
  secs: number;
  /** The share done, when the step reports it ("==> [k/n]"). */
  sub?: number;
}

const ESC = /\x1b\[[0-9;]*[A-Za-z]/g;

export class RebuildProgress {
  steps: Step[] = [];
  log: string[] = [];
  cancelled = false;
  started = 0;
  /** "rebuild", "install" (Home's Install the game: every step), or "pull"
   * for Updates > Get the new sources (no steps). */
  kind: "rebuild" | "install" | "pull" = "rebuild";
  /** The "ERROR: ..." lines the scripts printed. */
  errors: string[] = [];

  reset(only: string[] = [], kind: "rebuild" | "install" | "pull" = "rebuild") {
    this.kind = kind;
    this.log = [];
    this.errors = [];
    this.cancelled = false;
    this.started = Date.now();
    // a rebuild shows the build tools' step only when it is asked for ("deps":
    // they are missing, so the rebuild installs them first)
    const want = (id: StepId) =>
      kind === "install" ||
      (id === "deps" ? only.includes("deps") : id !== "sources" && (!only.length || only.includes(id) || id === "toolkit" || id === "venv"));
    this.steps = kind === "pull" ? [] : STEP_IDS.filter(want).map((id) => ({ id, state: "pending", start: 0, secs: 0 }));
  }

  /** The step that is running, or the one that failed. */
  stage(): Step | undefined {
    return this.steps.find((s) => s.state === "running" || s.state === "error");
  }

  private current(): Step | undefined {
    return this.steps.find((s) => s.state === "running");
  }

  private close(state: Step["state"]) {
    const c = this.current();
    if (c) {
      c.state = state;
      c.secs = (Date.now() - c.start) / 1000;
    }
  }

  feed(raw: string) {
    const line = raw.replace(ESC, "");
    this.log.push(line);
    if (this.log.length > 20000) this.log.splice(0, this.log.length - 20000);
    if (line.startsWith("ERROR:")) this.errors.push(line.slice(6).trim());
    const k = line.match(/^==>\s+\[(\d+)\/(\d+)\]/);
    if (k) {
      const c = this.current();
      if (c) c.sub = (Number(k[1]) - 1) / Math.max(1, Number(k[2]));
      return;
    }
    const m = line.match(/^==>\s+([a-z]+)/);
    if (!m) return;
    const word = m[1];
    if (word === "done") {
      this.close("done");
      return;
    }
    const step = this.steps.find((s) => s.id === word);
    if (!step) return;
    this.close("done");
    // steps the script went past without a line of their own (venv when it exists)
    for (const s of this.steps) {
      if (s === step) break;
      if (s.state === "pending") s.state = "skipped";
    }
    step.state = "running";
    step.start = Date.now();
  }

  finish(ok: boolean) {
    this.close(ok ? "done" : "error");
    if (ok) for (const s of this.steps) if (s.state === "pending") s.state = "skipped";
  }

  fraction(): number {
    const total = this.steps.reduce((a, s) => a + WEIGHT[s.id], 0);
    if (!total) return 0;
    let done = 0;
    for (const s of this.steps) {
      if (s.state === "done" || s.state === "skipped") done += WEIGHT[s.id];
      else if (s.state === "running") {
        // a running step counts as half done after its usual share of time,
        // or as far as it says it is
        const el = (Date.now() - s.start) / 1000;
        done += WEIGHT[s.id] * Math.max(s.sub ?? 0, Math.min(0.9, el / (el + 120)));
      }
    }
    return done / total;
  }

  /** Minutes left, from the time so far and the share done; null early on. */
  etaMinutes(): number | null {
    const f = this.fraction();
    const el = (Date.now() - this.started) / 60000;
    if (f < 0.05 || el < 0.5) return null;
    return (el / f) * (1 - f);
  }
}
