//! Debug mode ("Report a problem"): a session started in debug mode writes
//! the game's log and its diagnostics into a folder of its own,
//! `<data>/reports/<UTC time>/`, with a session index, `events.tsv`: the
//! start, a tick every 2 s with the log's size, each capture, the exit (and
//! the macOS crash report, when there is one, as `crash.ips`).
//!
//! What the toolkit offers this port for it: the whole frame every 120
//! presents (PS3RECOMP_METAL_FRAME_DUMP), the per-pass capture of the draw
//! engine started by a trigger file (RSX_ENGINE_PASS_DUMP with
//! RSX_ENGINE_PASS_DUMP_TRIGGER: the first capture of a session dumps that
//! frame pass by pass, its render targets and one line per draw), the frame
//! rate and frame times in the log, the window's own timings, and the problem
//! logs in `DEBUG_ENV`. `summarise` reads the log afterwards (`triage.md`,
//! `triage.json`), and the folder is packed into a .zip to send (images as
//! PNG, text with the home folder's path replaced by `~`).

use crate::zipfile;
use flate2::write::ZlibEncoder;
use flate2::Compression;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

/// The file whose appearance starts the per-pass capture.
pub const TRIGGER: &str = ".dump-now";
/// The game's output in debug mode.
pub const LOG: &str = "game.log";
/// One line per capture the player asked for.
pub const CAPTURES: &str = "captures.txt";
pub const SYSTEM: &str = "system.txt";
pub const NOTES: &str = "notes.txt";
/// The session index: one tab-separated line per event (utc, unix ms, the
/// log's size then, event, detail).
pub const EVENTS: &str = "events.tsv";
pub const TRIAGE_MD: &str = "triage.md";
pub const TRIAGE_JSON: &str = "triage.json";
/// The macOS crash report of a game that crashed, copied from
/// ~/Library/Logs/DiagnosticReports.
pub const CRASH: &str = "crash.ips";
/// The per-pass capture's folder (passes.txt, passNNN_*.ppm, draws.txt).
pub const PASSES: &str = "passes";

/// What debug mode adds: lines in the log when something goes wrong, none of
/// which changes what the game draws.
pub const DEBUG_ENV: &[(&str, &str)] = &[
    // every syscall that fails, once per (number, error), at most 64
    ("LV2_ERRDBG", "1"),
    // the window's publish-to-screen latency and copied/dropped frames, once a second
    ("PS3RECOMP_HOST_STATS", "1"),
    // the runtime's per-event lines, which normal play keeps out of the log
    ("PS3_VERBOSE", "1"),
];

/// The capture variables pointed at `dir`, and `DEBUG_ENV`.
pub fn env(dir: &Path) -> Vec<(String, String)> {
    let p = |s: &str| dir.join(s).to_string_lossy().into_owned();
    [
        ("PS3RECOMP_METAL_FRAME_DUMP", p("frame.ppm")),
        ("RSX_ENGINE_PASS_DUMP", p(PASSES)),
        ("RSX_ENGINE_PASS_DUMP_TRIGGER", p(TRIGGER)),
        ("RSX_ENGINE_PASS_DUMP_DRAWS", "1".into()),
        ("PS3RECOMP_METAL_FPS", "1".into()),
    ]
    .into_iter()
    .map(|(k, v)| (k.to_string(), v))
    .chain(DEBUG_ENV.iter().map(|(k, v)| (k.to_string(), v.to_string())))
    .collect()
}

/// Append one line to the session index.
pub fn event(dir: &Path, unix_ms: u64, utc: &str, kind: &str, detail: &str) -> Result<(), String> {
    let path = dir.join(EVENTS);
    let new = !path.exists();
    let size = fs::metadata(dir.join(LOG)).map(|m| m.len()).unwrap_or(0);
    let mut f = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|e| format!("{}: {e}", path.display()))?;
    let mut line = String::new();
    if new {
        line.push_str("# utc\tunix_ms\tlog_bytes\tevent\tdetail\n");
    }
    line.push_str(&format!("{utc}\t{unix_ms}\t{size}\t{kind}\t{}\n", detail.replace(['\t', '\n'], " ")));
    f.write_all(line.as_bytes()).map_err(|e| e.to_string())
}

/// A new, empty report folder `<reports>/<UTC time>` (with a suffix when two
/// start in the same second), with `passes/` (the draw engine wants it to
/// exist) and `shots/`.
pub fn create(reports: &Path, id: &str) -> Result<PathBuf, String> {
    fs::create_dir_all(reports).map_err(|e| format!("{}: {e}", reports.display()))?;
    let mut dir = reports.join(id);
    let mut n = 1;
    while dir.exists() {
        n += 1;
        dir = reports.join(format!("{id}-{n}"));
    }
    for sub in [PASSES, "shots"] {
        fs::create_dir_all(dir.join(sub)).map_err(|e| format!("{}: {e}", dir.display()))?;
    }
    Ok(dir)
}

/// "Capture this frame": keep the latest whole frame (written every 120
/// presents) as `shots/shot<n>.ppm`, touch the trigger (the first capture of
/// a session also dumps the next frame pass by pass), and note it in
/// captures.txt and the session index. Returns the capture's number.
pub fn capture(dir: &Path, when: &str, unix_ms: u64) -> Result<u32, String> {
    let n = count_captures(dir) + 1;
    let first = !dir.join(TRIGGER).exists();
    fs::write(dir.join(TRIGGER), b"").map_err(|e| format!("{}: {e}", dir.display()))?;
    let shot = if fs::copy(dir.join("frame.ppm"), dir.join("shots").join(format!("shot{n}.ppm"))).is_ok() {
        format!("shots/shot{n}.png")
    } else {
        "-".into()
    };
    let mut f = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(dir.join(CAPTURES))
        .map_err(|e| e.to_string())?;
    let passes = if first { ", passes dumped from the next frame" } else { "" };
    writeln!(f, "capture {n} at {when} UTC (last whole frame: {shot}{passes})").map_err(|e| e.to_string())?;
    event(dir, unix_ms, when, "capture", &format!("n={n} shot={shot} passes={}", u8::from(first)))?;
    Ok(n)
}

fn count_captures(dir: &Path) -> u32 {
    fs::read_to_string(dir.join(CAPTURES))
        .map(|s| s.lines().filter(|l| l.starts_with("capture ")).count() as u32)
        .unwrap_or(0)
}

#[derive(Serialize, Clone, Debug, Default)]
#[serde(rename_all = "camelCase")]
pub struct Info {
    pub dir: String,
    pub id: String,
    /// The game started with this report is still running.
    pub live: bool,
    /// It has a session index.
    pub debug: bool,
    pub captures: u32,
    /// A capture was asked for and the per-pass dump has not been written yet.
    pub pending: bool,
    /// Images of the per-pass capture.
    pub passes: u32,
    pub bytes: u64,
    pub log_bytes: u64,
    /// Seconds from the start to the exit (or the last tick).
    pub duration: Option<f64>,
    /// How it ended: "code=0", "signal=11", ...
    pub exit: Option<String>,
    pub stopped: bool,
    pub crash_report: bool,
    pub zip: Option<String>,
    pub zip_bytes: u64,
    pub triage: Option<Triage>,
}

/// The summary `summarise` writes (triage.json) and the launcher shows.
#[derive(Serialize, Deserialize, Clone, Debug, Default, PartialEq)]
#[serde(rename_all = "camelCase", default)]
pub struct Triage {
    pub errors: u64,
    pub warnings: u64,
    pub lines: u64,
    /// The [RSX FPS] lines' display rate: average and lowest, when present.
    pub fps_avg: Option<f64>,
    pub fps_min: Option<f64>,
    /// The log changed after the summary was made.
    pub stale: bool,
    pub md: String,
    pub top: Vec<Issue>,
}

#[derive(Serialize, Deserialize, Clone, Debug, Default, PartialEq)]
#[serde(rename_all = "camelCase", default)]
pub struct Issue {
    pub severity: String,
    pub title: String,
    pub count: u64,
    /// The first line it appeared on (1-based).
    pub first_line: u64,
}

fn is_err(l: &str) -> bool {
    let l = l.to_ascii_lowercase();
    ["error", "fail", "fatal", "abort", "panic", "exception", "crash", "assert"].iter().any(|w| l.contains(w))
}

fn is_warn(l: &str) -> bool {
    let l = l.to_ascii_lowercase();
    ["warn", "stub", "unimplemented", "missing", "unresolved", "not found"].iter().any(|w| l.contains(w))
}

/// The line without the "[  123.45] " the launcher stamps on each line of the
/// log (the seconds since launch, as tools/play.sh), so repeats still group.
pub fn strip_stamp(l: &str) -> &str {
    let Some(rest) = l.strip_prefix('[') else { return l };
    let Some(end) = rest.find("] ") else { return l };
    let t = rest[..end].trim_start();
    if !t.is_empty() && t.bytes().all(|b| b.is_ascii_digit() || b == b'.') {
        &rest[end + 2..]
    } else {
        l
    }
}

/// A message with its numbers and addresses masked, so repeats group.
fn mask(l: &str) -> String {
    let mut out = String::with_capacity(l.len());
    let mut prev_digit = false;
    let b = l.as_bytes();
    let mut i = 0;
    while i < b.len() {
        let c = b[i] as char;
        if c == '0' && i + 1 < b.len() && (b[i + 1] == b'x' || b[i + 1] == b'X') {
            i += 2;
            while i < b.len() && (b[i] as char).is_ascii_hexdigit() {
                i += 1;
            }
            out.push('#');
            prev_digit = true;
            continue;
        }
        if c.is_ascii_digit() {
            if !prev_digit {
                out.push('#');
            }
            prev_digit = true;
        } else {
            prev_digit = false;
            out.push(c);
        }
        i += 1;
    }
    out.trim().chars().take(200).collect()
}

/// Read a session's log and write triage.md / triage.json: error and warning
/// lines grouped by message (numbers masked), the most frequent first, and
/// the frame rate from the [RSX FPS] lines.
pub fn summarise(dir: &Path) -> Result<Triage, String> {
    let log = dir.join(LOG);
    let data = fs::read(&log).map_err(|e| format!("{}: {e}", log.display()))?;
    let text = String::from_utf8_lossy(&data);
    let mut groups: BTreeMap<String, Issue> = BTreeMap::new();
    let (mut errors, mut warnings, mut lines) = (0u64, 0u64, 0u64);
    let mut fps: Vec<f64> = Vec::new();
    for (n, l) in text.lines().enumerate() {
        lines += 1;
        let l = strip_stamp(l);
        if let Some(i) = l.find("[RSX FPS] display=") {
            if let Some(v) = l[i + 18..].split_whitespace().next().and_then(|v| v.parse::<f64>().ok()) {
                fps.push(v);
            }
            continue;
        }
        let sev = if is_err(l) {
            errors += 1;
            "error"
        } else if is_warn(l) {
            warnings += 1;
            "warning"
        } else {
            continue;
        };
        let key = mask(l);
        let g = groups.entry(key.clone()).or_insert_with(|| Issue { severity: sev.into(), title: key, count: 0, first_line: n as u64 + 1 });
        g.count += 1;
    }
    let mut top: Vec<Issue> = groups.into_values().collect();
    top.sort_by(|a, b| (b.severity == "error").cmp(&(a.severity == "error")).then(b.count.cmp(&a.count)).then(a.first_line.cmp(&b.first_line)));
    top.truncate(30);
    // the first second or two of a session report 0 fps while it boots
    let live: Vec<f64> = fps.iter().copied().filter(|v| *v > 0.5).collect();
    let t = Triage {
        errors,
        warnings,
        lines,
        fps_avg: (!live.is_empty()).then(|| live.iter().sum::<f64>() / live.len() as f64),
        fps_min: live.iter().copied().reduce(f64::min),
        stale: false,
        md: dir.join(TRIAGE_MD).to_string_lossy().into_owned(),
        top,
    };
    let mut md = format!("# Session {}\n\n", dir.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default());
    md.push_str(&format!("- log lines: {lines}\n- error lines: {errors}\n- warning lines: {warnings}\n"));
    if let (Some(a), Some(m)) = (t.fps_avg, t.fps_min) {
        md.push_str(&format!("- frame rate: {a:.1} fps on average, {m:.1} at the lowest ({} samples)\n", live.len()));
    }
    md.push_str("\n| severity | count | first line | message |\n|---|---|---|---|\n");
    for i in &t.top {
        md.push_str(&format!("| {} | {} | {} | `{}` |\n", i.severity, i.count, i.first_line, i.title.replace('|', "\\|").replace('`', "'")));
    }
    fs::write(dir.join(TRIAGE_MD), md).map_err(|e| e.to_string())?;
    fs::write(dir.join(TRIAGE_JSON), serde_json::to_string_pretty(&t).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
    Ok(t)
}

pub fn read_triage(dir: &Path) -> Option<Triage> {
    let path = dir.join(TRIAGE_JSON);
    let mut t: Triage = serde_json::from_str(&fs::read_to_string(&path).ok()?).ok()?;
    let mtime = |p: PathBuf| fs::metadata(p).and_then(|m| m.modified()).ok();
    t.stale = match (mtime(dir.join(LOG)), mtime(path)) {
        (Some(log), Some(tr)) => log > tr,
        _ => false,
    };
    Some(t)
}

struct Ending {
    duration: Option<f64>,
    exit: Option<String>,
    stopped: bool,
}

fn ending(dir: &Path) -> Option<Ending> {
    let text = fs::read_to_string(dir.join(EVENTS)).ok()?;
    let (mut start, mut last, mut exit, mut stopped) = (None, None, None, false);
    for l in text.lines().filter(|l| !l.starts_with('#')) {
        let p: Vec<&str> = l.split('\t').collect();
        let Some(ms) = p.get(1).and_then(|v| v.parse::<u64>().ok()) else { continue };
        match p.get(3).copied() {
            Some("start") => start = Some(ms),
            Some("stop") => stopped = true,
            Some("exit") => exit = p.get(4).map(|d| d.to_string()),
            _ => {}
        }
        last = Some(ms);
    }
    Some(Ending { duration: start.zip(last).map(|(a, b)| b.saturating_sub(a) as f64 / 1000.0), exit, stopped })
}

fn files(dir: &Path) -> Vec<PathBuf> {
    let mut out = Vec::new();
    let mut stack = vec![dir.to_path_buf()];
    while let Some(d) = stack.pop() {
        let Ok(it) = fs::read_dir(&d) else { continue };
        for e in it.flatten() {
            let p = e.path();
            match e.file_type() {
                Ok(t) if t.is_dir() => stack.push(p),
                Ok(t) if t.is_file() => out.push(p),
                _ => {}
            }
        }
    }
    out.sort();
    out
}

pub fn zip_path(dir: &Path) -> PathBuf {
    let id = dir.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
    dir.with_file_name(format!("resistance3-report-{id}.zip"))
}

pub fn info(dir: &Path, live: bool) -> Info {
    let all = files(dir);
    let zip = zip_path(dir);
    let zip_bytes = fs::metadata(&zip).map(|m| m.len()).ok();
    let end = ending(dir);
    let passes_txt = dir.join(PASSES).join("passes.txt");
    Info {
        dir: dir.to_string_lossy().into_owned(),
        id: dir.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default(),
        live,
        debug: end.is_some(),
        captures: count_captures(dir),
        pending: dir.join(TRIGGER).exists() && !passes_txt.exists(),
        passes: all
            .iter()
            .filter(|p| p.parent().and_then(Path::file_name).is_some_and(|n| n == PASSES))
            .filter(|p| p.extension().is_some_and(|e| e == "ppm" || e == "pgm"))
            .count() as u32,
        bytes: all.iter().filter_map(|p| fs::metadata(p).ok()).map(|m| m.len()).sum(),
        log_bytes: fs::metadata(dir.join(LOG)).map(|m| m.len()).unwrap_or(0),
        duration: end.as_ref().and_then(|e| e.duration),
        exit: end.as_ref().and_then(|e| e.exit.clone()),
        stopped: end.as_ref().is_some_and(|e| e.stopped),
        crash_report: dir.join(CRASH).is_file(),
        zip: zip_bytes.map(|_| zip.to_string_lossy().into_owned()),
        zip_bytes: zip_bytes.unwrap_or(0),
        triage: read_triage(dir),
    }
}

fn is_report(p: &Path) -> bool {
    p.is_dir() && p.file_name().is_some_and(|n| n.to_string_lossy().starts_with(|c: char| c.is_ascii_digit()))
}

/// Every report folder under `reports`, newest first (at most `max`).
pub fn list(reports: &Path, max: usize) -> Vec<PathBuf> {
    let mut v: Vec<PathBuf> = fs::read_dir(reports).into_iter().flatten().flatten().map(|e| e.path()).filter(|p| is_report(p)).collect();
    v.sort();
    v.reverse();
    v.truncate(max);
    v
}

pub fn latest(reports: &Path) -> Option<PathBuf> {
    list(reports, 1).pop()
}

/// A report folder by its id, refusing anything that is not a plain name
/// under `reports`.
pub fn by_id(reports: &Path, id: &str) -> Result<PathBuf, String> {
    let ok = !id.is_empty() && id.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_');
    let dir = reports.join(id);
    if ok && dir.is_dir() {
        Ok(dir)
    } else {
        Err(format!("no report {id:?}"))
    }
}

/// Delete a report folder and its .zip.
pub fn delete(reports: &Path, id: &str) -> Result<(), String> {
    let dir = by_id(reports, id)?;
    let _ = fs::remove_file(zip_path(&dir));
    fs::remove_dir_all(&dir).map_err(|e| format!("{}: {e}", dir.display()))
}

/// The newest macOS crash report of one of `exes` written at or after
/// `since` (seconds since the epoch) in `reports_dir`.
pub fn find_crash_report(reports_dir: &Path, exes: &[&str], since: u64) -> Option<PathBuf> {
    let mut best: Option<(u64, PathBuf)> = None;
    for e in fs::read_dir(reports_dir).ok()?.flatten() {
        let name = e.file_name().to_string_lossy().into_owned();
        let ours = exes.iter().any(|x| name.starts_with(&format!("{x}-")) || name.starts_with(&format!("{x}_")));
        if !ours || !(name.ends_with(".ips") || name.ends_with(".crash")) {
            continue;
        }
        let Some(t) = e
            .metadata()
            .and_then(|m| m.modified())
            .ok()
            .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
            .map(|d| d.as_secs())
        else {
            continue;
        };
        if t >= since && best.as_ref().map_or(true, |(b, _)| t > *b) {
            best = Some((t, e.path()));
        }
    }
    best.map(|(_, p)| p)
}

/// Binary PPM (P6) or PGM (P5), maxval 255 -> PNG ("Sub" filter on every
/// row); None when it is not one (or was cut short while being written).
pub fn pnm_to_png(d: &[u8]) -> Option<Vec<u8>> {
    let ch = match d.get(..2)? {
        b"P6" => 3usize,
        b"P5" => 1usize,
        _ => return None,
    };
    let mut i = 2;
    let mut nums = [0usize; 3];
    for n in nums.iter_mut() {
        loop {
            while d.get(i)?.is_ascii_whitespace() {
                i += 1;
            }
            if *d.get(i)? == b'#' {
                while *d.get(i)? != b'\n' {
                    i += 1;
                }
            } else {
                break;
            }
        }
        let start = i;
        while d.get(i)?.is_ascii_digit() {
            i += 1;
        }
        *n = std::str::from_utf8(&d[start..i]).ok()?.parse().ok()?;
    }
    let [w, h, max] = nums;
    if max != 255 || w == 0 || h == 0 || w > 16384 || h > 16384 || !d.get(i)?.is_ascii_whitespace() {
        return None;
    }
    let px = d.get(i + 1..i + 1 + w * h * ch)?;
    let stride = w * ch;
    let mut raw = Vec::with_capacity((stride + 1) * h);
    for row in px.chunks_exact(stride) {
        raw.push(1u8); // Sub: each byte minus the same channel one pixel left
        raw.extend_from_slice(&row[..ch]);
        raw.extend(row[ch..].iter().zip(row.iter()).map(|(a, b)| a.wrapping_sub(*b)));
    }
    let mut z = ZlibEncoder::new(Vec::new(), Compression::default());
    z.write_all(&raw).ok()?;
    let idat = z.finish().ok()?;
    let mut ihdr = Vec::with_capacity(13);
    ihdr.extend_from_slice(&(w as u32).to_be_bytes());
    ihdr.extend_from_slice(&(h as u32).to_be_bytes());
    ihdr.extend_from_slice(&[8, if ch == 3 { 2 } else { 0 }, 0, 0, 0]);
    let mut out = b"\x89PNG\r\n\x1a\n".to_vec();
    for (kind, body) in [(&b"IHDR"[..], &ihdr[..]), (b"IDAT", &idat), (b"IEND", &[])] {
        out.extend_from_slice(&(body.len() as u32).to_be_bytes());
        let start = out.len();
        out.extend_from_slice(kind);
        out.extend_from_slice(body);
        let crc = crc32fast::hash(&out[start..]);
        out.extend_from_slice(&crc.to_be_bytes());
    }
    Some(out)
}

fn is_text(name: &str) -> bool {
    [".log", ".txt", ".md", ".json", ".tsv", ".ips"].iter().any(|e| name.ends_with(e))
}

/// Pack `dir` into `dest`: every file but the trigger and earlier archives,
/// PPM/PGM images as PNG, text with `home` shown as `~`.
pub fn pack(dir: &Path, dest: &Path, home: &str) -> Result<u64, String> {
    let mut entries = Vec::new();
    for p in files(dir) {
        let rel = p.strip_prefix(dir).map_err(|e| e.to_string())?;
        let mut name = rel.components().map(|c| c.as_os_str().to_string_lossy()).collect::<Vec<_>>().join("/");
        if name == TRIGGER || name.ends_with(".zip") || name.ends_with(".partial") {
            continue;
        }
        let mtime = fs::metadata(&p)
            .and_then(|m| m.modified())
            .ok()
            .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
            .map(|d| d.as_secs())
            .unwrap_or(0);
        let Ok(mut data) = fs::read(&p) else { continue };
        if name.ends_with(".ppm") || name.ends_with(".pgm") {
            if let Some(png) = pnm_to_png(&data) {
                data = png;
                name.truncate(name.len() - 4);
                name.push_str(".png");
            }
        } else if is_text(&name) && home.len() > 1 {
            data = String::from_utf8_lossy(&data).replace(home, "~").into_bytes();
        }
        entries.push(zipfile::Entry { name, data, mtime });
    }
    if entries.is_empty() {
        return Err(format!("{}: nothing to pack", dir.display()));
    }
    zipfile::write(dest, &entries)?;
    fs::metadata(dest).map(|m| m.len()).map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ppm(w: usize, h: usize) -> Vec<u8> {
        let mut d = format!("P6\n# c\n{w} {h}\n255\n").into_bytes();
        d.extend((0..w * h * 3).map(|i| (i * 7 % 251) as u8));
        d
    }

    #[test]
    fn stamps_are_stripped() {
        assert_eq!(strip_stamp("[    1.25] [cellPad] x"), "[cellPad] x");
        assert_eq!(strip_stamp("[  123.45] warn: y"), "warn: y");
        assert_eq!(strip_stamp("[RSX FPS] display=30"), "[RSX FPS] display=30");
        assert_eq!(strip_stamp("plain"), "plain");
    }

    #[test]
    fn images_become_png() {
        let png = pnm_to_png(&ppm(5, 3)).unwrap();
        assert_eq!(&png[..8], b"\x89PNG\r\n\x1a\n");
        assert_eq!(png[25], 2); // RGB
        let mut pgm = b"P5\n2 2\n255\n".to_vec();
        pgm.extend([0, 64, 128, 255]);
        assert_eq!(pnm_to_png(&pgm).unwrap()[25], 0); // grey
        let d = ppm(4, 4);
        assert!(pnm_to_png(&d[..d.len() - 1]).is_none());
        assert!(pnm_to_png(b"").is_none());
    }

    #[test]
    fn env_points_the_dumps_at_the_report() {
        let env: BTreeMap<_, _> = env(Path::new("/r/x")).into_iter().collect();
        assert_eq!(env["RSX_ENGINE_PASS_DUMP_TRIGGER"], "/r/x/.dump-now");
        assert_eq!(env["RSX_ENGINE_PASS_DUMP"], "/r/x/passes");
        assert_eq!(env["PS3RECOMP_METAL_FRAME_DUMP"], "/r/x/frame.ppm");
        assert_eq!(env["PS3RECOMP_METAL_FPS"], "1");
        assert_eq!(env["LV2_ERRDBG"], "1");
    }

    #[test]
    fn session_capture_summary_zip() {
        let root = std::env::temp_dir().join(format!("rl-report-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        let dir = create(&root, "20261022-120000").unwrap();
        assert!(dir.join(PASSES).is_dir());
        assert_eq!(create(&root, "20261022-120000").unwrap(), root.join("20261022-120000-2"));
        let home = "/Users/someone";
        fs::write(
            dir.join(LOG),
            format!(
                "[boot] {home}/x\n[RSX FPS] display=0.00 guest=0\n[RSX FPS] display=30.50 guest=30\n[RSX FPS] display=28.50 guest=28\n\
                 [fs] open FAIL /dev_hdd0/a 12\n[fs] open FAIL /dev_hdd0/a 13\n[hle] stub cellFoo\n"
            ),
        )
        .unwrap();
        event(&dir, 1_000, "2026-10-22 12:00:00", "start", "").unwrap();
        fs::write(dir.join("frame.ppm"), ppm(2, 2)).unwrap();
        assert_eq!(capture(&dir, "2026-10-22 12:00:01", 2_000).unwrap(), 1);
        assert!(info(&dir, true).pending);
        fs::write(dir.join(PASSES).join("passes.txt"), "x").unwrap();
        fs::write(dir.join(PASSES).join("pass000_t0.ppm"), ppm(3, 2)).unwrap();
        assert_eq!(capture(&dir, "2026-10-22 12:00:05", 6_000).unwrap(), 2);
        event(&dir, 9_000, "2026-10-22 12:00:09", "exit", "signal=11").unwrap();
        let i = info(&dir, false);
        assert_eq!((i.captures, i.passes, i.pending), (2, 1, false));
        assert_eq!(i.exit.as_deref(), Some("signal=11"));
        assert_eq!(i.duration, Some(8.0));

        let t = summarise(&dir).unwrap();
        assert_eq!((t.errors, t.warnings), (2, 1));
        assert_eq!(t.top[0].count, 2);
        assert_eq!(t.top[0].title, "[fs] open FAIL /dev_hdd#/a #");
        assert_eq!(t.fps_avg, Some(29.5));
        assert_eq!(t.fps_min, Some(28.5));
        assert_eq!(read_triage(&dir).unwrap().errors, 2);

        let zip = zip_path(&dir);
        pack(&dir, &zip, home).unwrap();
        let lim = zipfile::Limits { entries: 100, file: 1 << 24, total: 1 << 26 };
        let got = zipfile::read(&zip, &lim).unwrap();
        let names: Vec<&str> = got.iter().map(|e| e.name.as_str()).collect();
        for want in ["game.log", "captures.txt", "events.tsv", "frame.png", "shots/shot1.png", "passes/pass000_t0.png", "triage.md"] {
            assert!(names.contains(&want), "{want} missing from {names:?}");
        }
        assert!(!names.iter().any(|n| n.contains(TRIGGER)));
        let log = got.iter().find(|e| e.name == "game.log").unwrap();
        assert!(String::from_utf8_lossy(&log.data).starts_with("[boot] ~/x"));
        assert_eq!(list(&root, 10).len(), 2);
        assert!(by_id(&root, "../x").is_err());
        delete(&root, "20261022-120000").unwrap();
        assert!(!zip.exists() && !dir.exists());

        let diag = root.join("diag");
        fs::create_dir_all(&diag).unwrap();
        fs::write(diag.join("ResistanceRecomp-2026-10-22-120010.ips"), "{}").unwrap();
        fs::write(diag.join("Other-2026-10-22-120010.ips"), "{}").unwrap();
        assert!(find_crash_report(&diag, &["ResistanceRecomp", "Resistance"], 0).is_some());
        assert!(find_crash_report(&diag, &["Resistance"], 0).is_none());
        fs::remove_dir_all(&root).unwrap();
    }
}
