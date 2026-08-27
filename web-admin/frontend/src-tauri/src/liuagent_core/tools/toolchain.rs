use std::collections::HashSet;
use std::env;
use std::path::{Path, PathBuf};
use std::process::Command;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ResolvedCommand {
    pub program: PathBuf,
    pub search_paths: Vec<PathBuf>,
}

pub fn resolve_command(command: &str) -> ResolvedCommand {
    let raw = command.trim();
    let search_paths = search_paths();
    let path = Path::new(raw);
    if path.components().count() > 1 || path.is_absolute() {
        return ResolvedCommand {
            program: path.to_path_buf(),
            search_paths,
        };
    }
    if let Some(program) = find_in_paths(raw, &search_paths) {
        return ResolvedCommand {
            program,
            search_paths,
        };
    }
    ResolvedCommand {
        program: PathBuf::from(raw),
        search_paths,
    }
}

pub fn merged_path(search_paths: &[PathBuf], configured_path: Option<&str>) -> Option<String> {
    let mut entries = Vec::new();
    let mut seen = HashSet::new();
    let add = |value: &Path, entries: &mut Vec<String>, seen: &mut HashSet<String>| {
        let raw = value.to_string_lossy().to_string();
        if !raw.is_empty() && seen.insert(raw.clone()) {
            entries.push(raw);
        }
    };
    if let Some(path) = configured_path {
        for entry in env::split_paths(path) {
            add(&entry, &mut entries, &mut seen);
        }
    }
    for entry in search_paths {
        add(entry, &mut entries, &mut seen);
    }
    env::join_paths(entries.iter().map(Path::new))
        .ok()
        .and_then(|value| value.into_string().ok())
}

pub fn configure_command_environment(command: &mut Command) {
    let paths = search_paths();
    let configured_path = env::var("PATH").ok();
    if let Some(path) = merged_path(&paths, configured_path.as_deref()) {
        command.env("PATH", path);
    }
}

fn search_paths() -> Vec<PathBuf> {
    let mut paths = env::var_os("PATH")
        .map(|value| env::split_paths(&value).collect::<Vec<_>>())
        .unwrap_or_default();
    let home = env::var_os(if cfg!(windows) { "USERPROFILE" } else { "HOME" }).map(PathBuf::from);
    let mut registered = Vec::new();
    if cfg!(target_os = "macos") {
        registered.extend([
            PathBuf::from("/opt/homebrew/bin"),
            PathBuf::from("/usr/local/bin"),
            PathBuf::from("/usr/bin"),
            PathBuf::from("/bin"),
        ]);
        if let Some(home) = &home {
            registered.extend([
                home.join(".local/bin"),
                home.join(".cargo/bin"),
                home.join(".pyenv/shims"),
                home.join(".asdf/shims"),
                home.join(".asdf/bin"),
            ]);
            add_versioned_bin_dirs(&mut registered, &home.join(".nvm/versions/node"));
        }
    } else if cfg!(windows) {
        registered.extend([
            PathBuf::from(r"C:\Program Files\nodejs"),
            PathBuf::from(r"C:\Program Files\Git\cmd"),
        ]);
        if let Some(home) = &home {
            registered.extend([
                home.join(".cargo/bin"),
                home.join(".local/bin"),
                home.join("AppData/Roaming/npm"),
                home.join("AppData/Local/Microsoft/WinGet/Links"),
            ]);
        }
        if let Some(local_app_data) = env::var_os("LOCALAPPDATA") {
            registered.push(PathBuf::from(local_app_data).join("Programs/Python"));
        }
    } else if let Some(home) = &home {
        registered.extend([
            home.join(".local/bin"),
            home.join(".cargo/bin"),
            home.join(".pyenv/shims"),
            home.join(".asdf/shims"),
        ]);
    }
    registered.extend(paths.drain(..));
    deduplicate_paths(registered)
}

fn add_versioned_bin_dirs(output: &mut Vec<PathBuf>, root: &Path) {
    let Ok(entries) = std::fs::read_dir(root) else {
        return;
    };
    let mut versions = entries
        .filter_map(Result::ok)
        .map(|entry| entry.path().join("bin"))
        .filter(|path| path.is_dir())
        .collect::<Vec<_>>();
    versions.sort_by(|left, right| right.cmp(left));
    output.extend(versions);
}

fn deduplicate_paths(paths: Vec<PathBuf>) -> Vec<PathBuf> {
    let mut seen = HashSet::new();
    paths
        .into_iter()
        .filter(|path| seen.insert(path.to_string_lossy().to_string()))
        .collect()
}

fn find_in_paths(command: &str, paths: &[PathBuf]) -> Option<PathBuf> {
    paths
        .iter()
        .map(|path| path.join(command))
        .find(|candidate| {
            candidate.is_file()
                || (cfg!(windows)
                    && [".exe", ".cmd", ".bat"]
                        .iter()
                        .map(|suffix| candidate.with_extension(suffix.trim_start_matches('.')))
                        .any(|variant| variant.is_file()))
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn keeps_absolute_commands_unchanged() {
        let resolved = resolve_command("/usr/bin/env");
        assert_eq!(resolved.program, PathBuf::from("/usr/bin/env"));
    }

    #[test]
    fn merged_path_deduplicates_entries() {
        let path = merged_path(
            &[PathBuf::from("/custom/bin"), PathBuf::from("/usr/bin")],
            Some("/usr/bin:/configured/bin"),
        )
        .expect("merged path");
        assert_eq!(path.matches("/usr/bin").count(), 1);
        assert!(path.starts_with("/usr/bin"));
        assert!(path.contains("/custom/bin"));
    }
}
