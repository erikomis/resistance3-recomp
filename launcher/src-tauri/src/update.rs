//! Updates: the port's sources (the checkout the builds come from) and the
//! launcher itself.
//!
//! - **Sources.** When the port folder is a git checkout with an upstream,
//!   `git fetch` and the count of commits it is behind; "Get the new sources"
//!   is `git pull --ff-only` (never a merge, never a reset: a checkout with
//!   changes of its own is left to the player). The builds are "older than
//!   the sources" when the newest commit touching what goes into them
//!   (port/, patches/, tools/) is newer than the EBOOT build.
//! - **The launcher.** The newest GitHub release of the repository (its
//!   tag, `vX.Y.Z`) against this build's version, once per session when the
//!   setting is on and on "Check again"; the card links to the release page.
//!   There is no signed self-install yet: that needs a release signing key
//!   (see the launcher README). `RES_NO_UPDATE_CHECK=1` turns the check off.

use serde::Serialize;
use std::path::Path;
use std::process::{Command, Stdio};

pub const REPO: &str = "erikomis/resistance3-recomp";

fn git(root: &Path, args: &[&str]) -> Option<String> {
    let out = crate::no_console(&mut Command::new("git"))
        .arg("-C")
        .arg(root)
        .args(args)
        .env("GIT_TERMINAL_PROMPT", "0")
        .stdin(Stdio::null())
        .stderr(Stdio::null())
        .output()
        .ok()?;
    out.status.success().then(|| String::from_utf8_lossy(&out.stdout).trim().to_string())
}

#[derive(Serialize, Default, Debug)]
#[serde(rename_all = "camelCase")]
pub struct Sources {
    /// The port folder is a git checkout.
    pub git: bool,
    pub branch: String,
    pub commit: String,
    pub subject: String,
    /// Seconds since the epoch of the commit checked out.
    pub commit_time: u64,
    /// The upstream it follows, and how far behind/ahead it is (after a fetch).
    pub upstream: String,
    pub behind: u32,
    pub ahead: u32,
    /// Files changed in the working tree (git status --porcelain, tracked only).
    pub dirty: u32,
    /// The newest commit touching what goes into the builds.
    pub sources_time: u64,
    pub fetched: bool,
    pub error: Option<String>,
}

/// The checkout's state; `fetch` asks the remote first (network).
pub fn sources(root: &Path, fetch: bool) -> Sources {
    let mut s = Sources::default();
    if git(root, &["rev-parse", "--is-inside-work-tree"]).as_deref() != Some("true") {
        return s;
    }
    s.git = true;
    s.branch = git(root, &["rev-parse", "--abbrev-ref", "HEAD"]).unwrap_or_default();
    s.commit = git(root, &["rev-parse", "--short", "HEAD"]).unwrap_or_default();
    s.subject = git(root, &["log", "-1", "--format=%s"]).unwrap_or_default();
    s.commit_time = git(root, &["log", "-1", "--format=%ct"]).and_then(|v| v.parse().ok()).unwrap_or(0);
    s.sources_time = git(root, &["log", "-1", "--format=%ct", "--", "port", "patches", "tools"])
        .and_then(|v| v.parse().ok())
        .unwrap_or(0);
    s.dirty = git(root, &["status", "--porcelain", "--untracked-files=no"]).map(|v| v.lines().count() as u32).unwrap_or(0);
    s.upstream = git(root, &["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]).unwrap_or_default();
    if s.upstream.is_empty() {
        return s;
    }
    if fetch {
        let remote = s.upstream.split('/').next().unwrap_or("origin").to_string();
        match crate::no_console(&mut Command::new("git"))
            .arg("-C")
            .arg(root)
            .args(["fetch", "--quiet", &remote])
            .env("GIT_TERMINAL_PROMPT", "0")
            .env("GIT_SSH_COMMAND", "ssh -o BatchMode=yes -o ConnectTimeout=10")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .output()
        {
            Ok(o) if o.status.success() => s.fetched = true,
            Ok(o) => s.error = Some(String::from_utf8_lossy(&o.stderr).trim().lines().last().unwrap_or("git fetch failed").to_string()),
            Err(e) => s.error = Some(format!("git: {e}")),
        }
    }
    if let Some(v) = git(root, &["rev-list", "--left-right", "--count", "HEAD...@{u}"]) {
        let mut it = v.split_whitespace().map(|n| n.parse::<u32>().unwrap_or(0));
        s.ahead = it.next().unwrap_or(0);
        s.behind = it.next().unwrap_or(0);
    }
    s
}

#[derive(Serialize, Default, Debug)]
#[serde(rename_all = "camelCase")]
pub struct AppUpdate {
    pub current: String,
    pub latest: Option<String>,
    pub newer: bool,
    pub url: Option<String>,
    pub notes: Option<String>,
    pub disabled: bool,
    pub error: Option<String>,
}

/// "1.2.3" (a leading v allowed) -> (1, 2, 3).
pub fn parse_version(v: &str) -> Option<(u32, u32, u32)> {
    let v = v.trim().trim_start_matches('v');
    let core = v.split(['-', '+']).next()?;
    let mut it = core.split('.').map(|p| p.parse::<u32>().ok());
    Some((it.next()??, it.next().unwrap_or(Some(0))?, it.next().unwrap_or(Some(0))?))
}

/// The newest release on GitHub (curl, which every Mac and Windows 10+ has;
/// no token).
pub fn check_app(current: &str) -> AppUpdate {
    let mut u = AppUpdate { current: current.into(), ..Default::default() };
    if std::env::var_os("RES_NO_UPDATE_CHECK").is_some_and(|v| !v.is_empty() && v != "0") {
        u.disabled = true;
        return u;
    }
    let url = format!("https://api.github.com/repos/{REPO}/releases/latest");
    let curl = if cfg!(windows) { "curl.exe" } else { "/usr/bin/curl" };
    let out = crate::no_console(&mut Command::new(curl))
        .args(["-fsSL", "--max-time", "15", "-H", "Accept: application/vnd.github+json", "-A", "resistance3-launcher", &url])
        .stdin(Stdio::null())
        .stderr(Stdio::piped())
        .output();
    let out = match out {
        Ok(o) => o,
        Err(e) => {
            u.error = Some(format!("curl: {e}"));
            return u;
        }
    };
    if !out.status.success() {
        let err = String::from_utf8_lossy(&out.stderr);
        // 404: no release published yet
        u.error = Some(if err.contains("404") { "no release yet".into() } else { err.trim().to_string() });
        return u;
    }
    let v: serde_json::Value = match serde_json::from_slice(&out.stdout) {
        Ok(v) => v,
        Err(e) => {
            u.error = Some(e.to_string());
            return u;
        }
    };
    let tag = v["tag_name"].as_str().unwrap_or("").to_string();
    u.newer = matches!((parse_version(&tag), parse_version(current)), (Some(a), Some(b)) if a > b);
    u.latest = (!tag.is_empty()).then_some(tag);
    u.url = v["html_url"].as_str().map(String::from);
    u.notes = v["body"].as_str().map(|s| s.chars().take(4000).collect());
    u
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn versions() {
        assert_eq!(parse_version("v0.2.10"), Some((0, 2, 10)));
        assert_eq!(parse_version("1.0"), Some((1, 0, 0)));
        assert_eq!(parse_version("0.3.0-beta.1"), Some((0, 3, 0)));
        assert_eq!(parse_version("x"), None);
        assert!(parse_version("v0.2.0") > parse_version("0.1.9"));
    }

    #[test]
    fn not_a_checkout() {
        let d = std::env::temp_dir().join(format!("rl-nogit-{}", std::process::id()));
        std::fs::create_dir_all(&d).unwrap();
        let s = sources(&d, false);
        assert!(!s.git);
        std::fs::remove_dir_all(&d).unwrap();
    }
}
