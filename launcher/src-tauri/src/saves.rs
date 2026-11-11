//! The saves manager: Resistance 3's saves in the port's play folder and in
//! RPCS3, timestamped backups, restore, copies between the two and .zip
//! archives.
//!
//! The game keeps its saves as cellSaveData slots (`BCUS98176_SAVE_<n>`:
//! PARAM.SFO, PARAM.PFD, ICON0.PNG, GAME.SAV), written at every checkpoint
//! (cellSaveDataUserListAutoSave) and from the menu. In the port they are
//! under `<play>/dev_hdd0/home/00000001/savedata` (PS3_HDD0_ROOT), in RPCS3
//! under `dev_hdd0/home/<user>/savedata`. Unlike Resistance: Fall of Man,
//! there is no checkpoint file of its own in the game's data folder.
//!
//! Both sides write a binary PARAM.SFO. The port also keeps the names of the
//! files the game wrote as SECUREFILE in PARAM.PFD (one per line); RPCS3 keeps
//! one integer `*<file>` key per file in PARAM.SFO instead and writes no
//! PARAM.PFD. The game's files are copied byte for byte; only that metadata
//! is converted when a slot crosses sides. Every operation that replaces or
//! removes a save backs it up first, and a slot is swapped in whole (built
//! next to it, then renamed), so a failed copy leaves the old one in place.
//!
//! Everything takes its folders from `Locations`, so the tests run on
//! temporary directories.

use crate::zipfile;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::UNIX_EPOCH;

pub const TITLE_ID: &str = "BCUS98176";
/// The PS3 user the port's cellSaveData writes under.
pub const PORT_USER: &str = "00000001";
const MANIFEST: &str = "backup.json";
const ZIP_MANIFEST: &str = "resistance3-saves.json";
const SFO: &str = "PARAM.SFO";
const PFD: &str = "PARAM.PFD";
/// Files cellSaveData types as content, never SECUREFILE.
const CONTENT_FILES: &[&str] = &["ICON0.PNG", "ICON1.PAM", "PIC1.PNG", "SND0.AT3"];

pub struct Locations {
    /// The port's `savedata` folder.
    pub port_savedata: PathBuf,
    /// RPCS3's `dev_hdd0`.
    pub rpcs3_hdd0: PathBuf,
    /// Where backups go (`<data>/save-backups`).
    pub backups: PathBuf,
}

impl Locations {
    pub fn rpcs3_savedata(&self, user: &str) -> PathBuf {
        self.rpcs3_hdd0.join("home").join(user).join("savedata")
    }
    fn savedata(&self, side: Side, user: &str) -> Result<PathBuf, String> {
        match side {
            Side::Port => Ok(self.port_savedata.clone()),
            Side::Rpcs3 if valid_user(user) => Ok(self.rpcs3_savedata(user)),
            Side::Rpcs3 => Err(format!("{user:?}: not an RPCS3 user folder")),
        }
    }
}

#[derive(Serialize, Deserialize, Clone, Copy, PartialEq, Eq, Debug, Default)]
#[serde(rename_all = "lowercase")]
pub enum Side {
    #[default]
    Port,
    Rpcs3,
}

impl Side {
    fn label(self) -> &'static str {
        match self {
            Side::Port => "port",
            Side::Rpcs3 => "rpcs3",
        }
    }
}

// ---------------------------------------------------------------------------
// Names
// ---------------------------------------------------------------------------

/// A save folder of this game, with a name that is safe to join onto a path.
pub fn valid_slot(name: &str) -> bool {
    name.len() <= 64
        && name.len() > TITLE_ID.len()
        && name.starts_with(TITLE_ID)
        && name.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-')
}

/// A slot name the operations take: a save folder of this game.
fn check_slot(name: &str) -> Result<(), String> {
    if valid_slot(name) {
        Ok(())
    } else {
        Err(format!("{name:?}: not a Resistance 3 save"))
    }
}

/// A PS3 user folder: eight digits.
pub fn valid_user(u: &str) -> bool {
    u.len() == 8 && u.bytes().all(|b| b.is_ascii_digit())
}

fn valid_id(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= 128
        && !id.starts_with('.')
        && id.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-')
}

/// One path component from an archive or a PFD line.
fn safe_component(n: &str) -> bool {
    !n.is_empty() && n != "." && n != ".." && n.len() <= 255 && !n.contains(['/', '\\', '\0', ':'])
}

// ---------------------------------------------------------------------------
// PARAM.SFO
// ---------------------------------------------------------------------------

pub const PSF_UTF8: u16 = 0x0204;
pub const PSF_INT: u16 = 0x0404;

/// One key of a binary PSF (PARAM.SFO), kept whole so a rewrite changes only
/// the keys it means to.
#[derive(Clone, Debug, PartialEq)]
pub struct PsfEntry {
    pub key: String,
    pub fmt: u16,
    /// Bytes used (strings include their NUL).
    pub data: Vec<u8>,
    pub max_len: u32,
}

impl PsfEntry {
    fn int(key: &str, v: u32) -> Self {
        PsfEntry { key: key.into(), fmt: PSF_INT, data: v.to_le_bytes().to_vec(), max_len: 4 }
    }
    fn string(key: &str, v: &str, max_len: u32) -> Self {
        let mut e = PsfEntry { key: key.into(), fmt: PSF_UTF8, data: Vec::new(), max_len };
        e.set_str(v);
        e
    }
    /// A NUL-terminated UTF-8 value, cut (on a character boundary) to fit.
    fn set_str(&mut self, v: &str) {
        let room = (self.max_len as usize).saturating_sub(1);
        let mut end = v.len().min(room);
        while !v.is_char_boundary(end) {
            end -= 1;
        }
        self.data = v.as_bytes()[..end].to_vec();
        self.data.push(0);
    }
    fn as_int(&self) -> Option<u32> {
        (self.fmt == PSF_INT && self.data.len() >= 4).then(|| u32::from_le_bytes(self.data[..4].try_into().unwrap()))
    }
    fn as_string(&self) -> String {
        match self.as_int() {
            Some(n) => n.to_string(),
            None => String::from_utf8_lossy(&self.data).trim_end_matches('\0').to_string(),
        }
    }
}

pub fn psf_parse(d: &[u8]) -> Option<Vec<PsfEntry>> {
    if d.len() < 20 || &d[..4] != b"\0PSF" {
        return None;
    }
    let u32le = |o: usize| -> Option<u32> { Some(u32::from_le_bytes(d.get(o..o + 4)?.try_into().ok()?)) };
    let u16le = |o: usize| -> Option<u16> { Some(u16::from_le_bytes(d.get(o..o + 2)?.try_into().ok()?)) };
    let (kt, dt, n) = (u32le(8)? as usize, u32le(12)? as usize, u32le(16)? as usize);
    let mut out = Vec::new();
    for k in 0..n.min(512) {
        let e = 20 + 16 * k;
        let (ko, fmt, len, max, off) =
            (u16le(e)? as usize, u16le(e + 2)?, u32le(e + 4)? as usize, u32le(e + 8)?, u32le(e + 12)? as usize);
        let key_bytes = d.get(kt + ko..)?;
        let key_end = key_bytes.iter().position(|&b| b == 0)?;
        let key = String::from_utf8_lossy(&key_bytes[..key_end]).into_owned();
        let data = d.get(dt + off..dt + off + len)?.to_vec();
        out.push(PsfEntry { key, fmt, data, max_len: max.max(len as u32) });
    }
    Some(out)
}

/// A PSF as the PS3 (and RPCS3) lays it out: keys sorted, key table padded
/// to 4 bytes, each value padded to its max length.
pub fn psf_write(entries: &[PsfEntry]) -> Vec<u8> {
    let mut es: Vec<&PsfEntry> = entries.iter().collect();
    es.sort_by(|a, b| a.key.cmp(&b.key));
    let mut keys = Vec::new();
    let mut index = Vec::new();
    let mut data = Vec::new();
    for e in &es {
        let max = (e.max_len as usize).max(e.data.len());
        index.extend_from_slice(&(keys.len() as u16).to_le_bytes());
        index.extend_from_slice(&e.fmt.to_le_bytes());
        index.extend_from_slice(&(e.data.len() as u32).to_le_bytes());
        index.extend_from_slice(&(max as u32).to_le_bytes());
        index.extend_from_slice(&(data.len() as u32).to_le_bytes());
        keys.extend_from_slice(e.key.as_bytes());
        keys.push(0);
        data.extend_from_slice(&e.data);
        data.resize(data.len() + max - e.data.len(), 0);
    }
    while keys.len() % 4 != 0 {
        keys.push(0);
    }
    let kt = 20 + index.len();
    let dt = kt + keys.len();
    let mut out = Vec::with_capacity(dt + data.len());
    out.extend_from_slice(b"\0PSF");
    out.extend_from_slice(&0x0101u32.to_le_bytes());
    out.extend_from_slice(&(kt as u32).to_le_bytes());
    out.extend_from_slice(&(dt as u32).to_le_bytes());
    out.extend_from_slice(&(es.len() as u32).to_le_bytes());
    out.extend_from_slice(&index);
    out.extend_from_slice(&keys);
    out.extend_from_slice(&data);
    out
}

/// PARAM.SFO as key -> value (empty when it is not a PSF).
pub fn sfo_values(d: &[u8]) -> BTreeMap<String, String> {
    psf_parse(d)
        .map(|es| es.into_iter().map(|e| (e.key.clone(), e.as_string())).collect())
        .unwrap_or_default()
}

pub fn read_sfo(path: &Path) -> Option<BTreeMap<String, String>> {
    fs::read(path).ok().filter(|d| psf_parse(d).is_some()).map(|d| sfo_values(&d))
}

/// The port's PARAM.PFD (file names, one per line), if `d` is one.
fn text_pfd(d: &[u8]) -> Option<Vec<String>> {
    let s = std::str::from_utf8(d).ok()?;
    let names: Vec<String> = s.lines().map(str::trim).filter(|l| !l.is_empty()).map(String::from).collect();
    names.iter().all(|n| safe_component(n) && n.len() < 64).then_some(names)
}

/// RPCS3's `*<file>` keys: the files and whether each is secure.
fn rpcs3_secure_files(es: &[PsfEntry]) -> Vec<(String, bool)> {
    es.iter()
        .filter_map(|e| {
            let n = e.key.strip_prefix('*')?;
            safe_component(n).then(|| (n.to_string(), e.as_int().unwrap_or(0) != 0))
        })
        .collect()
}

/// An RPCS3 PARAM.SFO for a slot that comes from the port: the port's own
/// keys, plus the RPCS3_BLIST and one `*<file>` key per game file (1 for the
/// ones the port's PARAM.PFD names). When RPCS3 already has the slot, its
/// PARAM.SFO is kept and only the titles shown in its list follow.
fn rpcs3_sfo(port_sfo: &[u8], existing: Option<&[u8]>, files: &[(String, bool)]) -> Vec<u8> {
    let port = psf_parse(port_sfo).unwrap_or_default();
    let mut es = match existing.and_then(psf_parse) {
        Some(mut old) => {
            for e in old.iter_mut() {
                if matches!(e.key.as_str(), "TITLE" | "SUB_TITLE" | "DETAIL") && e.fmt == PSF_UTF8 {
                    if let Some(p) = port.iter().find(|p| p.key == e.key) {
                        let v = p.as_string();
                        if !v.is_empty() {
                            e.set_str(&v);
                        }
                    }
                }
            }
            old
        }
        None => {
            let mut es: Vec<PsfEntry> = port.into_iter().filter(|e| !e.key.starts_with('*') && e.key != "RPCS3_BLIST").collect();
            let blist = files.iter().map(|(n, _)| n.as_str()).collect::<Vec<_>>().join("/");
            es.push(PsfEntry::string("RPCS3_BLIST", &blist, (blist.len() as u32 + 1).div_ceil(4) * 4));
            es
        }
    };
    for (n, secure) in files {
        let k = format!("*{n}");
        if !es.iter().any(|e| e.key == k) {
            es.push(PsfEntry::int(&k, u32::from(*secure)));
        }
    }
    psf_write(&es)
}

// ---------------------------------------------------------------------------
// Files
// ---------------------------------------------------------------------------

fn io<T>(r: std::io::Result<T>, p: &Path) -> Result<T, String> {
    r.map_err(|e| format!("{}: {e}", p.display()))
}

fn mtime(p: &Path) -> u64 {
    fs::metadata(p)
        .and_then(|m| m.modified())
        .ok()
        .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

/// Copy a file and keep its modification time (the date the list shows).
fn copy_file(src: &Path, dst: &Path) -> Result<(), String> {
    if let Some(d) = dst.parent() {
        io(fs::create_dir_all(d), d)?;
    }
    io(fs::copy(src, dst), src)?;
    if let Ok(t) = fs::metadata(src).and_then(|m| m.modified()) {
        if let Ok(f) = fs::OpenOptions::new().write(true).open(dst) {
            let _ = f.set_modified(t);
        }
    }
    Ok(())
}

/// Copy a folder tree (links are skipped), keeping modification times.
fn copy_tree(src: &Path, dst: &Path, skip: &[&str]) -> Result<(), String> {
    io(fs::create_dir_all(dst), dst)?;
    for e in io(fs::read_dir(src), src)?.flatten() {
        let name = e.file_name();
        if skip.iter().any(|s| name == *s) {
            continue;
        }
        let Ok(ft) = e.file_type() else { continue };
        let (from, to) = (e.path(), dst.join(&name));
        if ft.is_dir() {
            copy_tree(&from, &to, &[])?;
        } else if ft.is_file() {
            copy_file(&from, &to)?;
        }
    }
    Ok(())
}

/// Every regular file under `dir`, as ('/'-joined relative path, full path).
fn walk(dir: &Path) -> Vec<(String, PathBuf)> {
    fn go(base: &Path, rel: &str, out: &mut Vec<(String, PathBuf)>) {
        let Ok(it) = fs::read_dir(base) else { return };
        for e in it.flatten() {
            let Ok(ft) = e.file_type() else { continue };
            let name = e.file_name().to_string_lossy().into_owned();
            let r = if rel.is_empty() { name.clone() } else { format!("{rel}/{name}") };
            if ft.is_dir() {
                go(&e.path(), &r, out);
            } else if ft.is_file() {
                out.push((r, e.path()));
            }
        }
    }
    let mut out = Vec::new();
    go(dir, "", &mut out);
    out.sort();
    out
}

/// FNV-1a, to tell two saves (or two backups) apart.
fn fnv64(d: &[u8]) -> u64 {
    d.iter().fold(0xcbf2_9ce4_8422_2325u64, |h, &b| (h ^ b as u64).wrapping_mul(0x0100_0000_01b3))
}

/// Swap a slot in whole: build the new one next to it, move the old one
/// aside, rename, and only then delete the old one. A failure on the way
/// leaves the old one where it was.
fn replace_dir(dest: &Path, fill: impl FnOnce(&Path) -> Result<(), String>) -> Result<(), String> {
    let parent = dest.parent().ok_or("no parent folder")?;
    let name = dest.file_name().ok_or("no folder name")?.to_string_lossy().into_owned();
    io(fs::create_dir_all(parent), parent)?;
    let tmp = parent.join(format!(".{name}.incoming"));
    let old = parent.join(format!(".{name}.previous"));
    let _ = fs::remove_dir_all(&tmp);
    io(fs::create_dir_all(&tmp), &tmp)?;
    if let Err(e) = fill(&tmp) {
        let _ = fs::remove_dir_all(&tmp);
        return Err(e);
    }
    let had_old = dest.exists();
    if had_old {
        let _ = fs::remove_dir_all(&old);
        if let Err(e) = fs::rename(dest, &old) {
            let _ = fs::remove_dir_all(&tmp);
            return Err(format!("{}: {e}", dest.display()));
        }
    }
    if let Err(e) = fs::rename(&tmp, dest) {
        if had_old {
            let _ = fs::rename(&old, dest);
        }
        let _ = fs::remove_dir_all(&tmp);
        return Err(format!("{}: {e}", dest.display()));
    }
    if had_old {
        let _ = fs::remove_dir_all(&old);
    }
    Ok(())
}

/// UTC "YYYYMMDD-HHMMSS" for backup folder names.
pub(crate) fn stamp(secs: u64) -> String {
    let (y, m, d) = zipfile::civil_from_days((secs / 86_400) as i64);
    let r = secs % 86_400;
    format!("{y:04}{m:02}{d:02}-{:02}{:02}{:02}", r / 3600, r % 3600 / 60, r % 60)
}

fn base64(data: &[u8]) -> String {
    const T: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut s = String::with_capacity(data.len().div_ceil(3) * 4);
    for c in data.chunks(3) {
        let n = (c[0] as u32) << 16 | (*c.get(1).unwrap_or(&0) as u32) << 8 | *c.get(2).unwrap_or(&0) as u32;
        s.push(T[(n >> 18) as usize & 63] as char);
        s.push(T[(n >> 12) as usize & 63] as char);
        s.push(if c.len() > 1 { T[(n >> 6) as usize & 63] as char } else { '=' });
        s.push(if c.len() > 2 { T[n as usize & 63] as char } else { '=' });
    }
    s
}

// ---------------------------------------------------------------------------
// Slots
// ---------------------------------------------------------------------------

#[derive(Serialize, Clone, Debug, Default)]
#[serde(rename_all = "camelCase")]
pub struct Slot {
    /// The folder name (BCUS98176_SAVE_<n>).
    pub name: String,
    /// "save" (a savedata slot).
    pub kind: String,
    pub title: String,
    pub subtitle: String,
    pub detail: String,
    /// Seconds since the epoch (the newest file).
    pub modified: u64,
    pub bytes: u64,
    pub path: String,
    /// ICON0.PNG as a data URL (when asked for).
    pub icon: Option<String>,
    /// A hash of the game's own files, to tell whether both sides match.
    pub hash: String,
}

fn slot_hash(dir: &Path) -> u64 {
    // the game's files only: the metadata differs between the sides
    walk(dir)
        .into_iter()
        .filter(|(r, _)| r != SFO && r != PFD && !r.starts_with('.'))
        .fold(0u64, |h, (r, p)| {
            let d = fs::read(&p).map(|d| fnv64(&d)).unwrap_or(0);
            h.rotate_left(7) ^ fnv64(r.as_bytes()) ^ d
        })
}

fn read_slot(dir: &Path, icons: bool) -> Slot {
    let files = walk(dir);
    let v = read_sfo(&dir.join(SFO)).unwrap_or_default();
    let g = |k: &str| v.get(k).cloned().unwrap_or_default();
    let icon = if icons {
        fs::read(dir.join("ICON0.PNG")).ok().filter(|d| d.len() < 2 << 20).map(|d| format!("data:image/png;base64,{}", base64(&d)))
    } else {
        None
    };
    Slot {
        name: dir.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default(),
        kind: "save".into(),
        title: g("TITLE"),
        subtitle: g("SUB_TITLE"),
        detail: g("DETAIL"),
        modified: files.iter().map(|(_, p)| mtime(p)).max().unwrap_or(0),
        bytes: files.iter().filter_map(|(_, p)| fs::metadata(p).ok()).map(|m| m.len()).sum(),
        path: dir.to_string_lossy().into_owned(),
        icon,
        hash: format!("{:016x}", slot_hash(dir)),
    }
}

/// RPCS3's PS3 users that exist (the ones with a home folder), sorted.
pub fn rpcs3_users(loc: &Locations) -> Vec<String> {
    let mut v: Vec<String> = fs::read_dir(loc.rpcs3_hdd0.join("home"))
        .map(|it| it.flatten().map(|e| e.file_name().to_string_lossy().into_owned()).filter(|u| valid_user(u)).collect())
        .unwrap_or_default();
    v.sort();
    v
}

/// The saves of one side: its savedata slots, by name.
pub fn list_slots(loc: &Locations, side: Side, user: &str, icons: bool) -> Vec<Slot> {
    let mut out: Vec<Slot> = Vec::new();
    if let Ok(dir) = loc.savedata(side, user) {
        if let Ok(it) = fs::read_dir(&dir) {
            let mut names: Vec<String> =
                it.flatten().filter(|e| e.path().is_dir()).map(|e| e.file_name().to_string_lossy().into_owned()).filter(|n| valid_slot(n)).collect();
            names.sort();
            out.extend(names.iter().map(|n| read_slot(&dir.join(n), icons)));
        }
    }
    out
}

// ---------------------------------------------------------------------------
// Backups
// ---------------------------------------------------------------------------

#[derive(Serialize, Deserialize, Clone, Debug, Default)]
#[serde(rename_all = "camelCase", default)]
pub struct BackupMeta {
    pub id: String,
    /// Seconds since the epoch.
    pub created: u64,
    /// "auto" (before Play), "manual", "before-restore", "before-copy",
    /// "before-import", "before-delete".
    pub reason: String,
    pub side: Side,
    /// The RPCS3 user for an RPCS3 backup.
    pub user: String,
    pub slots: Vec<String>,
    pub titles: BTreeMap<String, String>,
    pub bytes: u64,
    /// The saves' contents, to skip an automatic backup that would repeat
    /// the last one.
    pub digest: String,
}

fn side_digest(loc: &Locations, side: Side, user: &str, slots: &[String]) -> String {
    let mut h = 0u64;
    for s in slots {
        let v = loc.savedata(side, user).map(|d| slot_hash(&d.join(s))).unwrap_or(0);
        h = h.rotate_left(9) ^ fnv64(s.as_bytes()) ^ v;
    }
    format!("{h:016x}")
}

/// Back up `slots` (all of that side's saves when None) into
/// `<backups>/<stamp>-<side>-<reason>/`: `savedata/<slot>/…`, with
/// backup.json. Written to a hidden folder and
/// renamed when complete. None when there is nothing to back up.
pub fn create_backup(loc: &Locations, side: Side, user: &str, slots: Option<&[String]>, reason: &str, now: u64) -> Result<Option<BackupMeta>, String> {
    let all: Vec<String> = list_slots(loc, side, user, false).into_iter().map(|s| s.name).collect();
    let want: Vec<String> = match slots {
        Some(s) => {
            for n in s {
                check_slot(n)?;
            }
            s.iter().filter(|n| all.contains(n)).cloned().collect()
        }
        None => all,
    };
    if want.is_empty() {
        return Ok(None);
    }
    let mut id = format!("{}-{}-{reason}", stamp(now), side.label());
    let mut n = 1;
    while loc.backups.join(&id).exists() {
        n += 1;
        id = format!("{}-{}-{reason}-{n}", stamp(now), side.label());
    }
    let tmp = loc.backups.join(format!(".{id}.partial"));
    let _ = fs::remove_dir_all(&tmp);
    io(fs::create_dir_all(&tmp), &tmp)?;
    let result = (|| -> Result<BackupMeta, String> {
        let mut meta = BackupMeta {
            id: id.clone(),
            created: now,
            reason: reason.into(),
            side,
            user: if side == Side::Rpcs3 { user.into() } else { String::new() },
            ..Default::default()
        };
        for s in &want {
            let src = loc.savedata(side, user)?.join(s);
            copy_tree(&src, &tmp.join("savedata").join(s), &[])?;
            let v = read_sfo(&src.join(SFO)).unwrap_or_default();
            meta.titles.insert(s.clone(), v.get("SUB_TITLE").or(v.get("TITLE")).cloned().unwrap_or_default());
            meta.slots.push(s.clone());
        }
        meta.bytes = walk(&tmp).iter().filter_map(|(_, p)| fs::metadata(p).ok()).map(|m| m.len()).sum();
        meta.digest = side_digest(loc, side, user, &want);
        io(fs::write(tmp.join(MANIFEST), serde_json::to_string_pretty(&meta).map_err(|e| e.to_string())?), &tmp)?;
        Ok(meta)
    })();
    match result {
        Ok(meta) => {
            io(fs::rename(&tmp, loc.backups.join(&id)), &tmp)?;
            Ok(Some(meta))
        }
        Err(e) => {
            let _ = fs::remove_dir_all(&tmp);
            Err(e)
        }
    }
}

/// Every complete backup, newest first.
pub fn list_backups(loc: &Locations) -> Vec<BackupMeta> {
    let mut v: Vec<BackupMeta> = fs::read_dir(&loc.backups)
        .into_iter()
        .flatten()
        .flatten()
        .filter(|e| !e.file_name().to_string_lossy().starts_with('.'))
        .filter_map(|e| fs::read_to_string(e.path().join(MANIFEST)).ok())
        .filter_map(|t| serde_json::from_str::<BackupMeta>(&t).ok())
        .filter(|m| valid_id(&m.id))
        .collect();
    v.sort_by(|a, b| b.created.cmp(&a.created).then(b.id.cmp(&a.id)));
    v
}

fn backup_dir(loc: &Locations, id: &str) -> Result<PathBuf, String> {
    let d = loc.backups.join(id);
    if valid_id(id) && d.join(MANIFEST).is_file() {
        Ok(d)
    } else {
        Err(format!("no backup {id:?}"))
    }
}

pub fn delete_backup(loc: &Locations, id: &str) -> Result<(), String> {
    let d = backup_dir(loc, id)?;
    io(fs::remove_dir_all(&d), &d)
}

/// Keep the newest `keep` backups made for `reason`; returns how many went.
pub fn prune_backups(loc: &Locations, reason: &str, keep: usize) -> Result<usize, String> {
    let old: Vec<BackupMeta> = list_backups(loc).into_iter().filter(|b| b.reason == reason).skip(keep).collect();
    for b in &old {
        delete_backup(loc, &b.id)?;
    }
    Ok(old.len())
}

/// Before Play: the port's saves, unless nothing changed since the last
/// automatic backup; the newest `keep` are kept (0 = off).
pub fn backup_before_play(loc: &Locations, keep: u32, now: u64) -> Result<Option<BackupMeta>, String> {
    if keep == 0 {
        return Ok(None);
    }
    let names: Vec<String> = list_slots(loc, Side::Port, "", false).into_iter().map(|s| s.name).collect();
    if names.is_empty() {
        return Ok(None);
    }
    let digest = side_digest(loc, Side::Port, "", &names);
    if list_backups(loc).iter().find(|b| b.reason == "auto").is_some_and(|b| b.digest == digest) {
        return Ok(None);
    }
    let b = create_backup(loc, Side::Port, "", None, "auto", now)?;
    prune_backups(loc, "auto", keep as usize)?;
    Ok(b)
}

#[derive(Serialize, Debug, Default)]
#[serde(rename_all = "camelCase")]
pub struct Report {
    /// The saves written.
    pub slots: Vec<String>,
    /// The backup made of what they replaced, if anything was there.
    pub backup: Option<String>,
}

/// Write one slot (a folder under `savedata`) to `side` from `src`, a folder
/// holding the slot's files. `from` is the side the files come from, for the
/// metadata conversion.
fn write_slot(loc: &Locations, side: Side, user: &str, slot: &str, src: &Path, from: Side) -> Result<(), String> {
    let dest = loc.savedata(side, user)?.join(slot);
    let existing_sfo = fs::read(dest.join(SFO)).ok();
    replace_dir(&dest, |tmp| {
        copy_tree(src, tmp, &[SFO, PFD])?;
        let sfo = fs::read(src.join(SFO)).ok();
        let game_files: Vec<String> = walk(tmp).into_iter().map(|(r, _)| r).filter(|r| !r.contains('/')).collect();
        match (from, side) {
            (Side::Rpcs3, Side::Port) => {
                // RPCS3's *<file> keys become the port's PARAM.PFD
                if let Some(d) = &sfo {
                    io(fs::write(tmp.join(SFO), d), tmp)?;
                    let secure: Vec<String> = psf_parse(d)
                        .map(|es| rpcs3_secure_files(&es).into_iter().filter(|(_, s)| *s).map(|(n, _)| n).collect())
                        .unwrap_or_default();
                    if !secure.is_empty() {
                        io(fs::write(tmp.join(PFD), secure.join("\n") + "\n"), tmp)?;
                    }
                }
            }
            (Side::Port, Side::Rpcs3) => {
                if let Some(d) = &sfo {
                    let secure = fs::read(src.join(PFD)).ok().and_then(|p| text_pfd(&p)).unwrap_or_default();
                    let files: Vec<(String, bool)> = game_files
                        .iter()
                        .map(|n| (n.clone(), secure.contains(n) && !CONTENT_FILES.contains(&n.as_str())))
                        .collect();
                    io(fs::write(tmp.join(SFO), rpcs3_sfo(d, existing_sfo.as_deref(), &files)), tmp)?;
                }
            }
            _ => {
                // the same side (a restore): the metadata as it was
                if let Some(d) = &sfo {
                    io(fs::write(tmp.join(SFO), d), tmp)?;
                }
                if let Ok(p) = fs::read(src.join(PFD)) {
                    io(fs::write(tmp.join(PFD), p), tmp)?;
                }
            }
        }
        Ok(())
    })
}

fn exists(loc: &Locations, side: Side, user: &str, slot: &str) -> bool {
    loc.savedata(side, user).is_ok_and(|d| d.join(slot).is_dir())
}

/// Put a backup back where it came from (all of its saves, or one).
pub fn restore_backup(loc: &Locations, id: &str, slot: Option<&str>, now: u64) -> Result<Report, String> {
    let dir = backup_dir(loc, id)?;
    let meta: BackupMeta = serde_json::from_str(&io(fs::read_to_string(dir.join(MANIFEST)), &dir)?).map_err(|e| e.to_string())?;
    let slots: Vec<String> = match slot {
        Some(s) if meta.slots.iter().any(|m| m == s) => vec![s.to_string()],
        Some(s) => return Err(format!("{s:?} is not in backup {id}")),
        None => meta.slots.clone(),
    };
    let here: Vec<String> = slots.iter().filter(|s| exists(loc, meta.side, &meta.user, s)).cloned().collect();
    let backup = create_backup(loc, meta.side, &meta.user, Some(&here), "before-restore", now)?.map(|b| b.id);
    for s in &slots {
        check_slot(s)?;
        write_slot(loc, meta.side, &meta.user, s, &dir.join("savedata").join(s), meta.side)?;
    }
    Ok(Report { slots, backup })
}

/// Copy one save from one side to the other (the destination's copy backed
/// up first).
pub fn copy_slot(loc: &Locations, from: Side, to: Side, user: &str, slot: &str, now: u64) -> Result<Report, String> {
    check_slot(slot)?;
    if from == to {
        return Err("copy to the same side".into());
    }
    if from == Side::Rpcs3 || to == Side::Rpcs3 {
        if !valid_user(user) {
            return Err(format!("{user:?}: not an RPCS3 user folder"));
        }
    }
    let src = loc.savedata(from, user)?.join(slot);
    if !src.exists() {
        return Err(format!("{}: not there", src.display()));
    }
    let backup = if exists(loc, to, user, slot) {
        create_backup(loc, to, user, Some(&[slot.to_string()]), "before-copy", now)?.map(|b| b.id)
    } else {
        None
    };
    write_slot(loc, to, user, slot, &src, from)?;
    Ok(Report { slots: vec![slot.to_string()], backup })
}

/// Delete one save, after a backup that must succeed first.
pub fn delete_slot(loc: &Locations, side: Side, user: &str, slot: &str, now: u64) -> Result<BackupMeta, String> {
    check_slot(slot)?;
    let b = create_backup(loc, side, user, Some(&[slot.to_string()]), "before-delete", now)?
        .ok_or_else(|| format!("{slot}: nothing to delete"))?;
    let p = loc.savedata(side, user)?.join(slot);
    io(fs::remove_dir_all(&p), &p)?;
    Ok(b)
}

// ---------------------------------------------------------------------------
// .zip
// ---------------------------------------------------------------------------

const ZIP_LIMITS: zipfile::Limits = zipfile::Limits { entries: 4096, file: 64 << 20, total: 256 << 20 };

/// The port's saves (all, or the ones named) as `<slot>/<file>`, plus a
/// small manifest. Returns how many saves went in.
pub fn export_zip(loc: &Locations, slots: Option<&[String]>, dest: &Path, now: u64) -> Result<usize, String> {
    let all = list_slots(loc, Side::Port, "", false);
    let want: Vec<&Slot> = all.iter().filter(|s| slots.is_none_or(|w| w.iter().any(|n| *n == s.name))).collect();
    if want.is_empty() {
        return Err("no saves to export".into());
    }
    let mut entries = Vec::new();
    for s in &want {
        for (rel, p) in walk(Path::new(&s.path)) {
            entries.push(zipfile::Entry { name: format!("{}/{rel}", s.name), data: io(fs::read(&p), &p)?, mtime: mtime(&p) });
        }
    }
    let manifest = serde_json::json!({
        "game": TITLE_ID,
        "created": now,
        "saves": want.iter().map(|s| &s.name).collect::<Vec<_>>(),
    });
    entries.push(zipfile::Entry { name: ZIP_MANIFEST.into(), data: manifest.to_string().into_bytes(), mtime: now });
    zipfile::write(dest, &entries)?;
    Ok(want.len())
}

/// Import a .zip into the port: every `BCUS98176*` folder in it (anywhere in
/// the archive, so a zipped RPCS3 `savedata` works). An RPCS3 slot (no
/// PARAM.PFD, `*<file>` keys) is converted as a copy from RPCS3 is. The
/// port's saves are backed up first.
pub fn import_zip(loc: &Locations, zip: &Path, now: u64) -> Result<Report, String> {
    let entries = zipfile::read(zip, &ZIP_LIMITS)?;
    let mut slots: BTreeMap<String, Vec<(String, &zipfile::Entry)>> = BTreeMap::new();
    for e in &entries {
        let parts: Vec<&str> = e.name.split('/').filter(|p| !p.is_empty()).collect();
        if parts.iter().any(|p| *p == "__MACOSX" || !safe_component(p)) {
            continue;
        }
        if let Some(i) = parts.iter().position(|p| valid_slot(p)) {
            if i + 2 == parts.len() {
                slots.entry(parts[i].to_string()).or_default().push((parts[i + 1].to_string(), e));
            }
        }
    }
    if slots.is_empty() {
        return Err("no Resistance 3 saves in this archive".into());
    }
    let names: Vec<String> = slots.keys().cloned().collect();
    let here: Vec<String> = names.iter().filter(|s| exists(loc, Side::Port, "", s)).cloned().collect();
    let backup = create_backup(loc, Side::Port, "", Some(&here), "before-import", now)?.map(|b| b.id);
    let stage = loc.backups.join(format!(".import-{}", stamp(now)));
    let _ = fs::remove_dir_all(&stage);
    let result = (|| -> Result<(), String> {
        for (slot, files) in &slots {
            let d = stage.join(slot);
            io(fs::create_dir_all(&d), &d)?;
            for (name, e) in files {
                io(fs::write(d.join(name), &e.data), &d)?;
            }
            let from_rpcs3 = !d.join(PFD).is_file()
                && fs::read(d.join(SFO)).ok().and_then(|s| psf_parse(&s)).is_some_and(|es| es.iter().any(|e| e.key.starts_with('*')));
            write_slot(loc, Side::Port, "", slot, &d, if from_rpcs3 { Side::Rpcs3 } else { Side::Port })?;
        }
        Ok(())
    })();
    let _ = fs::remove_dir_all(&stage);
    result?;
    Ok(Report { slots: names, backup })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn loc(tag: &str) -> (PathBuf, Locations) {
        let root = std::env::temp_dir().join(format!("rl2-saves-{tag}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        let l = Locations {
            port_savedata: root.join("play/dev_hdd0/home/00000001/savedata"),
            rpcs3_hdd0: root.join("rpcs3/dev_hdd0"),
            backups: root.join("backups"),
        };
        (root, l)
    }

    const SLOT: &str = "BCUS98176_SAVE_0";

    fn port_sfo(sub: &str) -> Vec<u8> {
        psf_write(&[
            PsfEntry::string("TITLE", "Resistance 3", 128),
            PsfEntry::string("SUB_TITLE", sub, 128),
            PsfEntry::string("DETAIL", "", 1024),
            PsfEntry::string("SAVEDATA_DIRECTORY", SLOT, 32),
        ])
    }

    fn port_save(l: &Locations, data: &[u8]) {
        let d = l.port_savedata.join(SLOT);
        fs::create_dir_all(&d).unwrap();
        fs::write(d.join(SFO), port_sfo("Campaign")).unwrap();
        fs::write(d.join(PFD), "GAME.SAV\n").unwrap();
        fs::write(d.join("GAME.SAV"), data).unwrap();
        fs::write(d.join("ICON0.PNG"), b"png").unwrap();
    }

    #[test]
    fn names() {
        assert!(valid_slot(SLOT));
        assert!(valid_slot("BCUS98176_SAVE_12"));
        assert!(!valid_slot("BCUS98176"));
        assert!(!valid_slot("BCUS98107_PROFILE"));
        assert!(!valid_slot("BCUS98176_../x"));
        assert!(check_slot("quick.sav").is_err());
        assert!(valid_user("00000001") && !valid_user("1") && !valid_user("../00001"));
    }

    #[test]
    fn psf_round_trip_and_rpcs3_keys() {
        let d = port_sfo("Campaign");
        let v = sfo_values(&d);
        assert_eq!(v["SUB_TITLE"], "Campaign");
        let files = vec![("GAME.SAV".to_string(), true), ("ICON0.PNG".to_string(), false)];
        let r = rpcs3_sfo(&d, None, &files);
        let es = psf_parse(&r).unwrap();
        assert_eq!(rpcs3_secure_files(&es), files);
        assert_eq!(sfo_values(&r)["RPCS3_BLIST"], "GAME.SAV/ICON0.PNG");
        // an RPCS3 slot that is there keeps its own keys, titles follow the port
        let old = psf_write(&[PsfEntry::string("SUB_TITLE", "old", 128), PsfEntry::string("ACCOUNT_ID", "x", 16)]);
        let r = sfo_values(&rpcs3_sfo(&port_sfo("new"), Some(&old), &files));
        assert_eq!(r["SUB_TITLE"], "new");
        assert_eq!(r["ACCOUNT_ID"], "x");
    }

    #[test]
    fn backups_restore_copy_delete_zip() {
        let (root, l) = loc("all");
        port_save(&l, b"one");
        let s = list_slots(&l, Side::Port, "", true);
        assert_eq!(s.iter().map(|x| x.name.as_str()).collect::<Vec<_>>(), vec![SLOT]);
        assert_eq!(s[0].subtitle, "Campaign");
        assert_eq!(s[0].kind, "save");
        assert!(s[0].icon.as_deref().unwrap().starts_with("data:image/png;base64,"));

        // automatic backups skip a repeat
        let a = backup_before_play(&l, 3, 1_000).unwrap().unwrap();
        assert!(backup_before_play(&l, 3, 1_001).unwrap().is_none());
        let pd = l.port_savedata.join(SLOT);
        fs::write(pd.join("GAME.SAV"), b"two").unwrap();
        assert!(backup_before_play(&l, 3, 1_002).unwrap().is_some());

        // restore the first one: the save comes back, the current one is backed up
        let r = restore_backup(&l, &a.id, Some(SLOT), 1_003).unwrap();
        assert!(r.backup.is_some());
        assert_eq!(fs::read(pd.join("GAME.SAV")).unwrap(), b"one");

        // port -> RPCS3 and back
        fs::create_dir_all(l.rpcs3_hdd0.join("home/00000001")).unwrap();
        copy_slot(&l, Side::Port, Side::Rpcs3, "00000001", SLOT, 1_004).unwrap();
        let rd = l.rpcs3_savedata("00000001").join(SLOT);
        assert!(!rd.join(PFD).exists());
        let es = psf_parse(&fs::read(rd.join(SFO)).unwrap()).unwrap();
        assert!(rpcs3_secure_files(&es).contains(&("GAME.SAV".to_string(), true)));
        assert_eq!(list_slots(&l, Side::Rpcs3, "00000001", false)[0].hash, list_slots(&l, Side::Port, "", false)[0].hash);
        fs::write(rd.join("GAME.SAV"), b"three").unwrap();
        let r = copy_slot(&l, Side::Rpcs3, Side::Port, "00000001", SLOT, 1_005).unwrap();
        assert!(r.backup.is_some());
        assert_eq!(fs::read(pd.join("GAME.SAV")).unwrap(), b"three");
        assert_eq!(fs::read_to_string(pd.join(PFD)).unwrap(), "GAME.SAV\n");

        // .zip out and in
        let z = root.join("saves.zip");
        assert_eq!(export_zip(&l, None, &z, 1_007).unwrap(), 1);
        let b = delete_slot(&l, Side::Port, "", SLOT, 1_008).unwrap();
        assert_eq!(b.reason, "before-delete");
        assert!(!pd.exists());
        let r = import_zip(&l, &z, 1_009).unwrap();
        assert_eq!(r.slots, vec![SLOT.to_string()]);
        assert_eq!(fs::read(pd.join("GAME.SAV")).unwrap(), b"three");

        // pruning keeps the newest automatic ones
        assert_eq!(prune_backups(&l, "auto", 1).unwrap(), 1);
        assert_eq!(list_backups(&l).iter().filter(|b| b.reason == "auto").count(), 1);
        fs::remove_dir_all(&root).unwrap();
    }
}
