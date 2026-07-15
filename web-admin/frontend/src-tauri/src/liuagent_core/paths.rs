use std::fs::{self, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};

pub const DESKTOP_RUNTIME_DIR_NAME: &str = "desktop-agent-runtime";
const LEGACY_RUNTIME_DIR_NAME: &str = "agent-runtime-v2";
const MIGRATION_MARKER_FILE: &str = ".legacy-agent-runtime-v2-migration-v1";
const DESKTOP_OWNED_LEGACY_ENTRIES: &[&str] = &[
    "bots",
    "maintenance.jsonl",
    "project-cache",
    "runtime-config",
    "session-cache",
    "sessions",
    "web-tools",
];

pub fn desktop_runtime_root(base_root: &Path) -> PathBuf {
    base_root
        .join(".ai-employee")
        .join(DESKTOP_RUNTIME_DIR_NAME)
}

pub fn ensure_desktop_runtime_migrated(base_root: &Path) -> io::Result<()> {
    let destination_root = desktop_runtime_root(base_root);
    let marker_path = destination_root.join(MIGRATION_MARKER_FILE);
    if marker_path.is_file() {
        return Ok(());
    }

    fs::create_dir_all(&destination_root)?;
    let legacy_root = base_root.join(".ai-employee").join(LEGACY_RUNTIME_DIR_NAME);
    if legacy_root.is_dir() {
        for entry_name in DESKTOP_OWNED_LEGACY_ENTRIES {
            copy_entry_if_missing(
                &legacy_root.join(entry_name),
                &destination_root.join(entry_name),
            )?;
        }
        copy_legacy_desktop_permission_files(&legacy_root, &destination_root)?;
    }

    write_marker_once(&marker_path)
}

fn copy_legacy_desktop_permission_files(
    legacy_root: &Path,
    destination_root: &Path,
) -> io::Result<()> {
    let legacy_permissions = legacy_root.join("permissions");
    let Ok(entries) = fs::read_dir(&legacy_permissions) else {
        return Ok(());
    };
    let destination_permissions = destination_root.join("permissions");
    for entry in entries {
        let entry = entry?;
        let metadata = fs::symlink_metadata(entry.path())?;
        if metadata.is_file() {
            copy_entry_if_missing(
                &entry.path(),
                &destination_permissions.join(entry.file_name()),
            )?;
        }
    }
    Ok(())
}

fn copy_entry_if_missing(source: &Path, destination: &Path) -> io::Result<()> {
    let Ok(metadata) = fs::symlink_metadata(source) else {
        return Ok(());
    };
    if metadata.file_type().is_symlink() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!(
                "legacy desktop runtime entry is a symlink: {}",
                source.display()
            ),
        ));
    }
    if metadata.is_dir() {
        fs::create_dir_all(destination)?;
        for entry in fs::read_dir(source)? {
            let entry = entry?;
            copy_entry_if_missing(&entry.path(), &destination.join(entry.file_name()))?;
        }
        return Ok(());
    }
    if !metadata.is_file() || destination.exists() {
        return Ok(());
    }
    if let Some(parent) = destination.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut source_file = fs::File::open(source)?;
    let mut destination_file = match OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(destination)
    {
        Ok(file) => file,
        Err(error) if error.kind() == io::ErrorKind::AlreadyExists => return Ok(()),
        Err(error) => return Err(error),
    };
    io::copy(&mut source_file, &mut destination_file)?;
    destination_file.sync_all()
}

fn write_marker_once(marker_path: &Path) -> io::Result<()> {
    match OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(marker_path)
    {
        Ok(mut marker) => {
            marker.write_all(b"desktop-agent-runtime migration v1 completed\n")?;
            marker.sync_all()
        }
        Err(error) if error.kind() == io::ErrorKind::AlreadyExists => Ok(()),
        Err(error) => Err(error),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn temp_dir(name: &str) -> PathBuf {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!("liuagent-paths-{name}-{suffix}"));
        fs::create_dir_all(&path).unwrap();
        path
    }

    #[test]
    fn migrates_only_desktop_owned_legacy_entries() {
        let base = temp_dir("selective");
        let legacy = base.join(".ai-employee").join(LEGACY_RUNTIME_DIR_NAME);
        fs::create_dir_all(legacy.join("sessions/chat-1")).unwrap();
        fs::create_dir_all(legacy.join("task-runs")).unwrap();
        fs::create_dir_all(legacy.join("events")).unwrap();
        fs::create_dir_all(legacy.join("permissions/decisions")).unwrap();
        fs::write(legacy.join("sessions/chat-1/state.json"), "desktop-state").unwrap();
        fs::write(legacy.join("task-runs/backend.json"), "backend-state").unwrap();
        fs::write(legacy.join("events/backend.jsonl"), "backend-event").unwrap();
        fs::write(legacy.join("permissions/chat-1.json"), "desktop-permission").unwrap();
        fs::write(
            legacy.join("permissions/decisions/backend.json"),
            "backend-permission",
        )
        .unwrap();

        ensure_desktop_runtime_migrated(&base).unwrap();

        let desktop = desktop_runtime_root(&base);
        assert_eq!(
            fs::read_to_string(desktop.join("sessions/chat-1/state.json")).unwrap(),
            "desktop-state"
        );
        assert!(!desktop.join("task-runs").exists());
        assert!(!desktop.join("events").exists());
        assert_eq!(
            fs::read_to_string(desktop.join("permissions/chat-1.json")).unwrap(),
            "desktop-permission"
        );
        assert!(!desktop.join("permissions/decisions").exists());
        assert!(desktop.join(MIGRATION_MARKER_FILE).is_file());
        fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn migration_is_idempotent_after_marker_creation() {
        let base = temp_dir("idempotent");
        let legacy_config = base
            .join(".ai-employee")
            .join(LEGACY_RUNTIME_DIR_NAME)
            .join("web-tools/config.json");
        fs::create_dir_all(legacy_config.parent().unwrap()).unwrap();
        fs::write(&legacy_config, "old-config").unwrap();

        ensure_desktop_runtime_migrated(&base).unwrap();
        fs::write(&legacy_config, "changed-after-migration").unwrap();
        ensure_desktop_runtime_migrated(&base).unwrap();

        assert_eq!(
            fs::read_to_string(desktop_runtime_root(&base).join("web-tools/config.json")).unwrap(),
            "old-config"
        );
        fs::remove_dir_all(base).unwrap();
    }
}
