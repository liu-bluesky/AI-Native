use rusqlite::{params, Connection, OpenFlags, OptionalExtension};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};
use tauri::Manager;

const JSON_STORE_VERSION: i64 = 1;
const JSON_STORE_DIRECTORY: &str = "project-chat-data";
const SQLITE_MIGRATION_MARKER: &str = ".sqlite-runtime-migration-v1.complete";
const SQLITE_CANONICAL_MIGRATION_KEY: &str = "desktop-project-chat-v1";
static INITIALIZED_CANONICAL_DATABASES: OnceLock<Mutex<BTreeSet<PathBuf>>> = OnceLock::new();

fn initialized_canonical_databases() -> &'static Mutex<BTreeSet<PathBuf>> {
    INITIALIZED_CANONICAL_DATABASES.get_or_init(|| Mutex::new(BTreeSet::new()))
}

fn normalized(value: &str, field: &str) -> Result<String, String> {
    let value = value.trim();
    if value.is_empty() {
        return Err(format!("缺少{field}"));
    }
    Ok(value.to_string())
}

fn normalized_session_project_id(project_id: &str, session: &Value) -> Result<String, String> {
    let project_id = normalized(project_id, "项目 ID")?;
    let embedded_project_id = value_text(session, &["project_id", "projectId"]);
    if !embedded_project_id.is_empty() && embedded_project_id != project_id {
        return Err("会话项目 ID 与请求项目 ID 不一致".to_string());
    }
    Ok(project_id)
}

fn database_path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let app_data_dir = app.path().app_data_dir().map_err(|err| err.to_string())?;
    fs::create_dir_all(&app_data_dir).map_err(|err| err.to_string())?;
    Ok(app_data_dir.join("project-chat.sqlite3"))
}

fn path_component(value: &str) -> String {
    value
        .as_bytes()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>()
}

fn json_store_root(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let app_data_dir = app.path().app_data_dir().map_err(|err| err.to_string())?;
    let root = app_data_dir.join(JSON_STORE_DIRECTORY);
    fs::create_dir_all(&root).map_err(|err| err.to_string())?;
    Ok(root)
}

fn json_project_directory(
    app: &tauri::AppHandle,
    username: &str,
    project_id: &str,
) -> Result<PathBuf, String> {
    let directory = json_store_root(app)?
        .join(path_component(username))
        .join(path_component(project_id));
    fs::create_dir_all(&directory).map_err(|err| err.to_string())?;
    Ok(directory)
}

fn json_session_path(
    app: &tauri::AppHandle,
    username: &str,
    project_id: &str,
    chat_session_id: &str,
) -> Result<PathBuf, String> {
    Ok(json_project_directory(app, username, project_id)?
        .join(format!("{}.json", path_component(chat_session_id))))
}

fn read_json_envelope(path: &Path) -> Result<Value, String> {
    let raw = fs::read_to_string(path).map_err(|err| err.to_string())?;
    serde_json::from_str(&raw).map_err(|err| err.to_string())
}

fn write_json_envelope(path: &Path, envelope: &Value) -> Result<(), String> {
    let parent = path
        .parent()
        .ok_or_else(|| "会话文件路径无效".to_string())?;
    fs::create_dir_all(parent).map_err(|err| err.to_string())?;
    let temporary = parent.join(format!(
        ".{}.{}.tmp",
        path.file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("session.json"),
        std::process::id()
    ));
    let payload = serde_json::to_vec_pretty(envelope).map_err(|err| err.to_string())?;
    fs::write(&temporary, payload).map_err(|err| err.to_string())?;
    let backup = parent.join(format!(
        ".{}.backup",
        path.file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("session.json")
    ));
    if path.exists() {
        if backup.exists() {
            fs::remove_file(&backup).map_err(|err| err.to_string())?;
        }
        fs::rename(path, &backup).map_err(|err| err.to_string())?;
    }
    if let Err(error) = fs::rename(&temporary, path) {
        if backup.exists() {
            let _ = fs::rename(&backup, path);
        }
        return Err(error.to_string());
    }
    if backup.exists() {
        fs::remove_file(backup).map_err(|err| err.to_string())?;
    }
    Ok(())
}

fn load_json_envelopes(
    app: &tauri::AppHandle,
    username: &str,
    project_id: &str,
) -> Result<Vec<Value>, String> {
    migrate_legacy_sqlite_project(app, username, project_id)?;
    let directory = json_project_directory(app, username, project_id)?;
    let mut envelopes = Vec::new();
    for entry in fs::read_dir(directory).map_err(|err| err.to_string())? {
        let entry = entry.map_err(|err| err.to_string())?;
        let path = entry.path();
        if path.extension().and_then(|value| value.to_str()) != Some("json") {
            continue;
        }
        envelopes.push(read_json_envelope(&path)?);
    }
    Ok(envelopes)
}

fn build_session_from_runtime(chat_session_id: &str, runtime: &Value, updated_at: &str) -> Value {
    let messages = runtime
        .get("messages")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let first_user_content = messages
        .iter()
        .find(|message| value_text(message, &["role"]).eq_ignore_ascii_case("user"))
        .map(|message| value_text(message, &["content"]))
        .unwrap_or_default();
    let last_message_content = messages
        .iter()
        .rev()
        .map(|message| value_text(message, &["content"]))
        .find(|content| !content.is_empty())
        .unwrap_or_default();
    let last_message_id = messages
        .iter()
        .rev()
        .find(|message| !value_text(message, &["content"]).is_empty())
        .map(|message| value_text(message, &["id"]))
        .unwrap_or_default();
    json!({
        "id": chat_session_id,
        "title": if first_user_content.is_empty() { "新对话".to_string() } else { clipped(&first_user_content, 48) },
        "preview": clipped(&last_message_content, 120),
        "latest_requirement": clipped(&first_user_content, 240),
        "last_message": clipped(&last_message_content, 240),
        "last_message_id": last_message_id,
        "message_count": messages.len(),
        "created_at": updated_at,
        "updated_at": updated_at,
        "last_message_at": if last_message_content.is_empty() { String::new() } else { updated_at.to_string() },
        "source": "desktop_json_runtime"
    })
}

fn merge_session_with_runtime(
    chat_session_id: &str,
    stored_session: Option<&Value>,
    runtime: &Value,
    updated_at: &str,
) -> Value {
    let mut session = build_session_from_runtime(chat_session_id, runtime, updated_at);
    if let (Some(target), Some(source)) = (
        session.as_object_mut(),
        stored_session.and_then(Value::as_object),
    ) {
        for (key, value) in source {
            if key != "message_count"
                && key != "preview"
                && key != "latest_requirement"
                && key != "last_message"
                && key != "last_message_id"
                && key != "last_message_at"
            {
                target.insert(key.clone(), value.clone());
            }
        }
    }
    session["id"] = Value::String(chat_session_id.to_string());
    session["updated_at"] = Value::String(updated_at.to_string());
    session
}

fn runtime_message_activity(runtime: &Value) -> Vec<Value> {
    runtime
        .get("messages")
        .and_then(Value::as_array)
        .map(|messages| {
            messages
                .iter()
                .map(|message| {
                    json!({
                        "id": value_text(message, &["id"]),
                        "role": value_text(message, &["role"]),
                        "content": value_text(message, &["content"]),
                    })
                })
                .collect()
        })
        .unwrap_or_default()
}

fn session_stable_position_at(session: &Value) -> String {
    value_text(session, &["created_at"])
}

fn compare_sessions_by_stable_position(left: &Value, right: &Value) -> std::cmp::Ordering {
    session_stable_position_at(right)
        .cmp(&session_stable_position_at(left))
        .then_with(|| value_text(left, &["id"]).cmp(&value_text(right, &["id"])))
}

fn session_activity_at(session: &Value) -> String {
    value_text(session, &["last_message_at", "updated_at", "created_at"])
}

fn runtime_activity_updated_at(
    existing: Option<&Value>,
    runtime: &Value,
    requested_updated_at: &str,
) -> String {
    let Some(existing) = existing else {
        return requested_updated_at.to_string();
    };
    let existing_activity = existing
        .get("runtime")
        .map(runtime_message_activity)
        .unwrap_or_default();
    if existing_activity != runtime_message_activity(runtime) {
        return requested_updated_at.to_string();
    }
    let existing_session_activity = existing
        .get("session")
        .map(session_activity_at)
        .unwrap_or_default();
    if !existing_session_activity.is_empty() {
        return existing_session_activity;
    }
    let envelope_activity = value_text(existing, &["updated_at"]);
    if envelope_activity.is_empty() {
        requested_updated_at.to_string()
    } else {
        envelope_activity
    }
}

fn build_json_envelope(
    username: &str,
    project_id: &str,
    chat_session_id: &str,
    session: Value,
    runtime: Value,
    updated_at: &str,
) -> Value {
    json!({
        "version": JSON_STORE_VERSION,
        "username": username,
        "project_id": project_id,
        "chat_session_id": chat_session_id,
        "updated_at": updated_at,
        "session": session,
        "runtime": runtime
    })
}

fn sqlite_table_exists(connection: &Connection, table: &str) -> Result<bool, String> {
    connection
        .query_row(
            "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?1)",
            params![table],
            |row| row.get::<_, i64>(0),
        )
        .map(|value| value != 0)
        .map_err(|err| err.to_string())
}

fn ensure_canonical_sqlite_schema(connection: &Connection) -> Result<(), String> {
    connection
        .execute_batch(
            "PRAGMA journal_mode = WAL;
             PRAGMA foreign_keys = ON;
             CREATE TABLE IF NOT EXISTS desktop_project_chat_sessions (
                 username TEXT NOT NULL,
                 project_id TEXT NOT NULL,
                 chat_session_id TEXT NOT NULL,
                 session_json TEXT NOT NULL,
                 updated_at TEXT NOT NULL DEFAULT '',
                 PRIMARY KEY (username, project_id, chat_session_id)
             );
             CREATE INDEX IF NOT EXISTS idx_desktop_project_chat_sessions_user_updated
                 ON desktop_project_chat_sessions(username, updated_at DESC);
             CREATE TABLE IF NOT EXISTS desktop_project_chat_runtimes (
                 username TEXT NOT NULL,
                 project_id TEXT NOT NULL,
                 chat_session_id TEXT NOT NULL,
                 runtime_json TEXT NOT NULL,
                 updated_at TEXT NOT NULL DEFAULT '',
                 PRIMARY KEY (username, project_id, chat_session_id)
             );
             CREATE TABLE IF NOT EXISTS desktop_project_chat_message_snapshots (
                 username TEXT NOT NULL,
                 project_id TEXT NOT NULL,
                 chat_session_id TEXT NOT NULL,
                 messages_json TEXT NOT NULL,
                 updated_at TEXT NOT NULL DEFAULT '',
                 PRIMARY KEY (username, project_id, chat_session_id)
             );
             CREATE TABLE IF NOT EXISTS desktop_project_chat_metadata (
                 key TEXT PRIMARY KEY,
                 value TEXT NOT NULL
             );
             CREATE TABLE IF NOT EXISTS desktop_local_ai_tasks (
                 task_id TEXT PRIMARY KEY,
                 task_json TEXT NOT NULL,
                 updated_at TEXT NOT NULL DEFAULT ''
             );
             CREATE TABLE IF NOT EXISTS desktop_local_records (
                 record_key TEXT PRIMARY KEY,
                 value_json TEXT NOT NULL,
                 updated_at TEXT NOT NULL DEFAULT ''
             );",
        )
        .map_err(|err| err.to_string())
}

fn upsert_canonical_session(
    connection: &Connection,
    username: &str,
    project_id: &str,
    chat_session_id: &str,
    session: &Value,
    updated_at: &str,
) -> Result<(), String> {
    let payload = serde_json::to_string(session).map_err(|err| err.to_string())?;
    connection
        .execute(
            "INSERT INTO desktop_project_chat_sessions
                 (username, project_id, chat_session_id, session_json, updated_at)
             VALUES (?1, ?2, ?3, ?4, ?5)
             ON CONFLICT(username, project_id, chat_session_id) DO UPDATE SET
                 session_json = excluded.session_json,
                 updated_at = excluded.updated_at",
            params![username, project_id, chat_session_id, payload, updated_at],
        )
        .map_err(|err| err.to_string())?;
    Ok(())
}

fn upsert_canonical_runtime(
    connection: &Connection,
    username: &str,
    project_id: &str,
    chat_session_id: &str,
    runtime: &Value,
    updated_at: &str,
) -> Result<(), String> {
    let payload = serde_json::to_string(runtime).map_err(|err| err.to_string())?;
    connection
        .execute(
            "INSERT INTO desktop_project_chat_runtimes
                 (username, project_id, chat_session_id, runtime_json, updated_at)
             VALUES (?1, ?2, ?3, ?4, ?5)
             ON CONFLICT(username, project_id, chat_session_id) DO UPDATE SET
                 runtime_json = excluded.runtime_json,
                 updated_at = excluded.updated_at",
            params![username, project_id, chat_session_id, payload, updated_at],
        )
        .map_err(|err| err.to_string())?;
    Ok(())
}

fn upsert_canonical_message_snapshot(
    connection: &Connection,
    username: &str,
    project_id: &str,
    chat_session_id: &str,
    runtime: &Value,
    updated_at: &str,
) -> Result<(), String> {
    let messages = runtime
        .get("messages")
        .cloned()
        .unwrap_or_else(|| Value::Array(Vec::new()));
    let payload = serde_json::to_string(&messages).map_err(|err| err.to_string())?;
    connection
        .execute(
            "INSERT INTO desktop_project_chat_message_snapshots
                 (username, project_id, chat_session_id, messages_json, updated_at)
             VALUES (?1, ?2, ?3, ?4, ?5)
             ON CONFLICT(username, project_id, chat_session_id) DO UPDATE SET
                 messages_json = excluded.messages_json,
                 updated_at = excluded.updated_at",
            params![username, project_id, chat_session_id, payload, updated_at],
        )
        .map_err(|err| err.to_string())?;
    Ok(())
}

fn message_id_set(messages: &[Value]) -> BTreeSet<String> {
    messages
        .iter()
        .map(|message| value_text(message, &["id"]))
        .filter(|id| !id.is_empty())
        .collect()
}

fn string_array_set(value: Option<&Value>) -> BTreeSet<String> {
    value
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(str::trim)
                .filter(|id| !id.is_empty())
                .map(ToString::to_string)
                .collect()
        })
        .unwrap_or_default()
}

fn string_set_json_value(values: &BTreeSet<String>) -> Value {
    Value::Array(
        values
            .iter()
            .cloned()
            .map(Value::String)
            .collect::<Vec<_>>(),
    )
}

fn merge_runtime_payload(existing: Option<&Value>, incoming: &Value) -> Value {
    let replace_messages = incoming
        .get("replace_messages")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let Some(existing) = existing else {
        let mut next = incoming.clone();
        if let Some(object) = next.as_object_mut() {
            object.remove("replace_messages");
            object.insert(
                "messages_authoritative".to_string(),
                Value::Bool(replace_messages),
            );
        }
        return next;
    };
    let (Some(existing_object), Some(incoming_object)) =
        (existing.as_object(), incoming.as_object())
    else {
        let mut next = incoming.clone();
        if let Some(object) = next.as_object_mut() {
            object.remove("replace_messages");
            object.insert(
                "messages_authoritative".to_string(),
                Value::Bool(replace_messages),
            );
        }
        return next;
    };
    let mut merged = existing_object.clone();
    for (key, value) in incoming_object {
        merged.insert(key.clone(), value.clone());
    }

    let existing_messages = existing_object
        .get("messages")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let incoming_messages = incoming_object
        .get("messages")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut deleted_message_ids = string_array_set(
        existing_object
            .get("deleted_message_ids")
            .or_else(|| existing_object.get("deletedMessageIds")),
    );
    deleted_message_ids.extend(string_array_set(
        incoming_object
            .get("deleted_message_ids")
            .or_else(|| incoming_object.get("deletedMessageIds")),
    ));

    if incoming_object.get("messages").is_some() {
        if replace_messages {
            // An authoritative snapshot is allowed to remove messages. The
            // removed IDs are retained so a queued stale snapshot cannot
            // re-introduce them later.
            let existing_ids = message_id_set(&existing_messages);
            let incoming_ids = message_id_set(&incoming_messages);
            deleted_message_ids.extend(existing_ids.difference(&incoming_ids).cloned());
            merged.insert(
                "messages".to_string(),
                Value::Array(
                    incoming_messages
                        .into_iter()
                        .filter(|message| {
                            let id = value_text(message, &["id"]);
                            id.is_empty() || !deleted_message_ids.contains(&id)
                        })
                        .collect(),
                ),
            );
        } else {
            let mut incoming_by_id = BTreeMap::new();
            let mut incoming_message_order = Vec::new();
            let mut incoming_without_id = Vec::new();
            for message in incoming_messages {
                let id = value_text(&message, &["id"]);
                if id.is_empty() {
                    incoming_without_id.push(message);
                    continue;
                }
                if deleted_message_ids.contains(&id) {
                    continue;
                }
                if !incoming_by_id.contains_key(&id) {
                    incoming_message_order.push(id.clone());
                }
                incoming_by_id.insert(id, message);
            }

            let mut messages =
                Vec::with_capacity(incoming_message_order.len() + existing_messages.len());
            let mut existing_ids = BTreeSet::new();
            for previous in existing_messages {
                let id = value_text(&previous, &["id"]);
                if id.is_empty() {
                    messages.push(previous);
                    continue;
                }
                if deleted_message_ids.contains(&id) {
                    continue;
                }
                existing_ids.insert(id.clone());
                if let Some(message) = incoming_by_id.get(&id) {
                    let (Some(previous_object), Some(message_object)) =
                        (previous.as_object(), message.as_object())
                    else {
                        messages.push(message.clone());
                        continue;
                    };
                    let mut merged_message = previous_object.clone();
                    for (key, value) in message_object {
                        let preserve_answer_id = matches!(key.as_str(), "answerId" | "answer_id")
                            && value.as_str().is_some_and(|text| text.trim().is_empty());
                        let preserve_content = key == "content"
                            && value.as_str().is_some_and(|text| text.trim().is_empty())
                            && !value_text(&previous, &["content"]).is_empty();
                        if !preserve_answer_id && !preserve_content {
                            merged_message.insert(key.clone(), value.clone());
                        }
                    }
                    messages.push(Value::Object(merged_message));
                    continue;
                }
                messages.push(previous);
            }
            for id in incoming_message_order {
                if existing_ids.contains(&id) {
                    continue;
                }
                if let Some(message) = incoming_by_id.get(&id) {
                    messages.push(message.clone());
                }
            }
            messages.extend(incoming_without_id);
            merged.insert("messages".to_string(), Value::Array(messages));
        }
    }
    if deleted_message_ids.is_empty() {
        merged.remove("deleted_message_ids");
    } else {
        merged.insert(
            "deleted_message_ids".to_string(),
            string_set_json_value(&deleted_message_ids),
        );
    }
    merged.insert(
        "messages_authoritative".to_string(),
        Value::Bool(
            replace_messages
                || existing_object
                    .get("messages_authoritative")
                    .and_then(Value::as_bool)
                    .unwrap_or(false),
        ),
    );
    merged.remove("replace_messages");
    Value::Object(merged)
}

fn migrate_legacy_tables_to_canonical(connection: &Connection) -> Result<usize, String> {
    let mut migrated = 0;
    if sqlite_table_exists(connection, "project_chat_sessions")? {
        migrated += connection
            .execute(
                "INSERT OR IGNORE INTO desktop_project_chat_sessions
                     (username, project_id, chat_session_id, session_json, updated_at)
                 SELECT username, project_id, chat_session_id, payload_json, updated_at
                 FROM project_chat_sessions",
                [],
            )
            .map_err(|err| err.to_string())?;
    }
    if sqlite_table_exists(connection, "project_chat_runtimes")? {
        migrated += connection
            .execute(
                "INSERT OR IGNORE INTO desktop_project_chat_runtimes
                     (username, project_id, chat_session_id, runtime_json, updated_at)
                 SELECT username, project_id, chat_session_id, payload_json, updated_at
                 FROM project_chat_runtimes",
                [],
            )
            .map_err(|err| err.to_string())?;
    }
    Ok(migrated)
}

fn migrate_json_store_to_canonical(connection: &Connection, root: &Path) -> Result<usize, String> {
    if !root.exists() {
        return Ok(0);
    }
    let mut pending = vec![root.to_path_buf()];
    let mut migrated = 0;
    while let Some(directory) = pending.pop() {
        for entry in fs::read_dir(directory).map_err(|err| err.to_string())? {
            let entry = entry.map_err(|err| err.to_string())?;
            let path = entry.path();
            if path.is_dir() {
                pending.push(path);
                continue;
            }
            if path.extension().and_then(|value| value.to_str()) != Some("json") {
                continue;
            }
            let envelope = read_json_envelope(&path)?;
            let username = value_text(&envelope, &["username"]);
            let project_id = value_text(&envelope, &["project_id"]);
            let chat_session_id = value_text(&envelope, &["chat_session_id"]);
            if username.is_empty() || project_id.is_empty() || chat_session_id.is_empty() {
                continue;
            }
            let updated_at = value_text(&envelope, &["updated_at"]);
            let runtime = envelope
                .get("runtime")
                .cloned()
                .unwrap_or_else(|| json!({"version": 1, "updated_at": updated_at, "messages": []}));
            let session = merge_session_with_runtime(
                &chat_session_id,
                envelope.get("session"),
                &runtime,
                &updated_at,
            );
            upsert_canonical_session(
                connection,
                &username,
                &project_id,
                &chat_session_id,
                &session,
                &updated_at,
            )?;
            upsert_canonical_runtime(
                connection,
                &username,
                &project_id,
                &chat_session_id,
                &runtime,
                &updated_at,
            )?;
            migrated += 1;
        }
    }
    Ok(migrated)
}

fn open_canonical_database(app: &tauri::AppHandle) -> Result<Connection, String> {
    let path = database_path(app)?;
    let connection = Connection::open(&path).map_err(|err| err.to_string())?;
    let mut initialized = initialized_canonical_databases()
        .lock()
        .map_err(|_| "本机聊天数据库初始化锁不可用".to_string())?;
    if initialized.contains(&path) {
        return Ok(connection);
    }
    ensure_canonical_sqlite_schema(&connection)?;
    let migrated = connection
        .query_row(
            "SELECT value FROM desktop_project_chat_metadata WHERE key = ?1",
            params![SQLITE_CANONICAL_MIGRATION_KEY],
            |row| row.get::<_, String>(0),
        )
        .optional()
        .map_err(|err| err.to_string())?
        .is_some();
    if !migrated {
        migrate_legacy_tables_to_canonical(&connection)?;
        let root = json_store_root(app)?;
        migrate_json_store_to_canonical(&connection, &root)?;
        connection
            .execute(
                "INSERT OR REPLACE INTO desktop_project_chat_metadata(key, value) VALUES (?1, ?2)",
                params![SQLITE_CANONICAL_MIGRATION_KEY, "complete"],
            )
            .map_err(|err| err.to_string())?;
    }
    initialized.insert(path);
    Ok(connection)
}

fn migrate_legacy_sqlite_project(
    app: &tauri::AppHandle,
    username: &str,
    project_id: &str,
) -> Result<usize, String> {
    let directory = json_project_directory(app, username, project_id)?;
    let legacy_path = database_path(app)?;
    migrate_legacy_sqlite_project_paths(&legacy_path, &directory, username, project_id)
}

fn migrate_legacy_sqlite_project_paths(
    legacy_path: &Path,
    directory: &Path,
    username: &str,
    project_id: &str,
) -> Result<usize, String> {
    fs::create_dir_all(directory).map_err(|err| err.to_string())?;
    let marker = directory.join(SQLITE_MIGRATION_MARKER);
    if !legacy_path.exists() {
        if !marker.exists() {
            fs::write(marker, b"no legacy database\n").map_err(|err| err.to_string())?;
        }
        return Ok(0);
    }
    let connection = Connection::open_with_flags(&legacy_path, OpenFlags::SQLITE_OPEN_READ_ONLY)
        .map_err(|err| err.to_string())?;
    let mut records: BTreeMap<String, (Option<Value>, Option<Value>, String)> = BTreeMap::new();
    if sqlite_table_exists(&connection, "project_chat_sessions")? {
        let mut statement = connection
            .prepare(
                "SELECT chat_session_id, payload_json, updated_at FROM project_chat_sessions
                 WHERE username = ?1 AND project_id = ?2",
            )
            .map_err(|err| err.to_string())?;
        let rows = statement
            .query_map(params![username, project_id], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                ))
            })
            .map_err(|err| err.to_string())?;
        for row in rows {
            let (chat_session_id, payload_json, updated_at) = row.map_err(|err| err.to_string())?;
            let session = serde_json::from_str(&payload_json).map_err(|err| err.to_string())?;
            records.insert(chat_session_id, (Some(session), None, updated_at));
        }
    }
    if sqlite_table_exists(&connection, "project_chat_runtimes")? {
        let mut statement = connection
            .prepare(
                "SELECT chat_session_id, payload_json, updated_at FROM project_chat_runtimes
                 WHERE username = ?1 AND project_id = ?2",
            )
            .map_err(|err| err.to_string())?;
        let rows = statement
            .query_map(params![username, project_id], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                ))
            })
            .map_err(|err| err.to_string())?;
        for row in rows {
            let (chat_session_id, payload_json, updated_at) = row.map_err(|err| err.to_string())?;
            let runtime = serde_json::from_str(&payload_json).map_err(|err| err.to_string())?;
            let entry = records
                .entry(chat_session_id)
                .or_insert_with(|| (None, None, updated_at.clone()));
            entry.1 = Some(runtime);
            entry.2 = updated_at;
        }
    }
    let mut migrated = 0;
    for (chat_session_id, (stored_session, stored_runtime, updated_at)) in records {
        let path = directory.join(format!("{}.json", path_component(&chat_session_id)));
        if path.exists() {
            continue;
        }
        let runtime = stored_runtime.unwrap_or_else(|| {
            json!({
                "version": 1,
                "updated_at": updated_at,
                "messages": []
            })
        });
        let session = merge_session_with_runtime(
            &chat_session_id,
            stored_session.as_ref(),
            &runtime,
            &updated_at,
        );
        let envelope = build_json_envelope(
            username,
            project_id,
            &chat_session_id,
            session,
            runtime,
            &updated_at,
        );
        write_json_envelope(&path, &envelope)?;
        migrated += 1;
    }
    fs::write(marker, format!("migrated={migrated}\n")).map_err(|err| err.to_string())?;
    Ok(migrated)
}

fn value_text(value: &Value, keys: &[&str]) -> String {
    for key in keys {
        if let Some(text) = value.get(*key).and_then(Value::as_str) {
            let normalized = text.trim();
            if !normalized.is_empty() {
                return normalized.to_string();
            }
        }
    }
    String::new()
}

fn value_i64(value: &Value, keys: &[&str]) -> i64 {
    for key in keys {
        if let Some(number) = value.get(*key).and_then(Value::as_i64) {
            return number;
        }
        if let Some(number) = value.get(*key).and_then(Value::as_u64) {
            return number.min(i64::MAX as u64) as i64;
        }
    }
    0
}

fn find_nested_text(value: &Value, keys: &[&str]) -> String {
    if let Some(object) = value.as_object() {
        for key in keys {
            if let Some(text) = object.get(*key).and_then(Value::as_str) {
                let normalized = text.trim();
                if !normalized.is_empty() {
                    return normalized.to_string();
                }
            }
        }
        for child in object.values() {
            let nested = find_nested_text(child, keys);
            if !nested.is_empty() {
                return nested;
            }
        }
    } else if let Some(items) = value.as_array() {
        for child in items {
            let nested = find_nested_text(child, keys);
            if !nested.is_empty() {
                return nested;
            }
        }
    }
    String::new()
}

fn clipped(value: &str, limit: usize) -> String {
    let normalized = value.trim();
    if normalized.chars().count() <= limit {
        return normalized.to_string();
    }
    let mut result = normalized.chars().take(limit).collect::<String>();
    result.push('…');
    result
}

fn stable_fragment(value: &str, fallback: &str) -> String {
    let normalized = value
        .chars()
        .map(|character| {
            if character.is_ascii_alphanumeric() || matches!(character, '-' | '_' | ':') {
                character
            } else {
                '_'
            }
        })
        .collect::<String>();
    let normalized = normalized.trim_matches('_');
    if normalized.is_empty() {
        fallback.to_string()
    } else {
        normalized.chars().take(120).collect()
    }
}

fn supervision_answer_status(message: &Value) -> String {
    let operations = message
        .get("operations")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let phases = operations
        .iter()
        .map(|operation| value_text(operation, &["phase", "status"]).to_lowercase())
        .collect::<Vec<_>>();
    if phases.iter().any(|phase| phase == "failed") {
        return "failed".to_string();
    }
    if phases
        .iter()
        .any(|phase| matches!(phase.as_str(), "blocked" | "waiting_user"))
    {
        return "blocked".to_string();
    }
    let started_at = value_i64(
        message,
        &[
            "agentRuntimeStartedAtEpochMs",
            "messageExecutionStartedAtEpochMs",
        ],
    );
    let ended_at = value_i64(
        message,
        &[
            "agentRuntimeEndedAtEpochMs",
            "messageExecutionEndedAtEpochMs",
        ],
    );
    if ended_at <= 0
        && (started_at > 0
            || phases
                .iter()
                .any(|phase| matches!(phase.as_str(), "pending" | "running")))
    {
        return "running".to_string();
    }
    "completed".to_string()
}

fn supervision_step_type(item: &Value, default_type: &str) -> String {
    let kind = value_text(item, &["kind", "eventType", "event_type"]).to_lowercase();
    let tool_name = find_nested_text(item, &["tool_name", "toolName"]);
    if !tool_name.is_empty() || kind.contains("tool") || kind.contains("command") {
        return "tool_call".to_string();
    }
    if kind.contains("model") {
        return "model_call".to_string();
    }
    if kind.contains("permission") || kind.contains("approval") || kind.contains("auth") {
        return "permission".to_string();
    }
    if kind.contains("plan") {
        return "plan".to_string();
    }
    if kind.contains("context") || kind.contains("prompt") {
        return "context_build".to_string();
    }
    if kind.contains("retry") {
        return "retry".to_string();
    }
    if kind.contains("pause") {
        return "pause".to_string();
    }
    if kind.contains("resume") || kind.contains("recover") {
        return "resume".to_string();
    }
    default_type.to_string()
}

fn process_step_status(item: &Value) -> String {
    match value_text(item, &["level", "status", "phase"])
        .to_lowercase()
        .as_str()
    {
        "error" | "failed" => "failed".to_string(),
        "warning" | "blocked" | "waiting_user" => "blocked".to_string(),
        "pending" | "running" => "running".to_string(),
        _ => "completed".to_string(),
    }
}

struct SupervisionStep {
    step_id: String,
    step_type: String,
    status: String,
    title: String,
    summary: String,
    detail_preview: String,
    tool_name: String,
    call_id: String,
    model_name: String,
    provider_id: String,
    provider_name: String,
    model_step_index: i64,
    context_snapshot_json: String,
    context_message_count: i64,
    context_input_tokens: i64,
    context_token_source: String,
    model_input_tokens: i64,
    model_output_tokens: i64,
    model_total_tokens: i64,
    model_cached_input_tokens: i64,
    model_reasoning_tokens: i64,
    model_token_source: String,
    started_at_epoch_ms: i64,
    ended_at_epoch_ms: i64,
    duration_ms: i64,
}

fn supervision_context_fields(snapshot: &Value) -> (String, i64, i64, String) {
    if !snapshot.is_object() {
        return ("{}".to_string(), 0, 0, String::new());
    }
    let snapshot_json = serde_json::to_string(snapshot).unwrap_or_else(|_| "{}".to_string());
    let message_count = value_i64(snapshot, &["message_count", "messageCount"]);
    let input_tokens = value_i64(
        snapshot,
        &["estimated_input_tokens", "estimatedInputTokens"],
    );
    let token_source = value_text(snapshot, &["token_source", "tokenSource"]);
    (snapshot_json, message_count, input_tokens, token_source)
}

fn supervision_model_token_fields(
    model: &Value,
    snapshot: &Value,
) -> (i64, i64, i64, i64, i64, String) {
    let usage = model
        .get("tokenUsage")
        .or_else(|| model.get("token_usage"))
        .filter(|value| value.is_object())
        .or_else(|| {
            snapshot
                .get("tokenUsage")
                .or_else(|| snapshot.get("token_usage"))
                .filter(|value| value.is_object())
        })
        .unwrap_or(&Value::Null);
    (
        value_i64(
            usage,
            &[
                "input_tokens",
                "inputTokens",
                "prompt_tokens",
                "promptTokens",
            ],
        ),
        value_i64(
            usage,
            &[
                "output_tokens",
                "outputTokens",
                "completion_tokens",
                "completionTokens",
            ],
        ),
        value_i64(usage, &["total_tokens", "totalTokens"]),
        value_i64(
            usage,
            &[
                "cached_input_tokens",
                "cachedInputTokens",
                "cached_tokens",
                "cachedTokens",
            ],
        ),
        value_i64(usage, &["reasoning_tokens", "reasoningTokens"]),
        value_text(usage, &["source"]),
    )
}

fn collect_execution_cycle_steps(
    message: &Value,
    assistant_message_id: &str,
) -> Vec<SupervisionStep> {
    let message_cycles = message
        .get("agentExecutionCycles")
        .or_else(|| message.get("agent_execution_cycles"))
        .and_then(Value::as_array);
    let cycles = message_cycles.map(Vec::as_slice).unwrap_or_default();
    if cycles.is_empty() {
        return Vec::new();
    }
    let mut steps = Vec::new();
    for (cycle_offset, cycle) in cycles.iter().enumerate() {
        let model_step_index =
            value_i64(cycle, &["cycleIndex", "cycle_index"]).max((cycle_offset + 1) as i64);
        let snapshot = cycle
            .get("contextSnapshot")
            .or_else(|| cycle.get("context_snapshot"))
            .unwrap_or(&Value::Null);
        let (
            context_snapshot_json,
            context_message_count,
            context_input_tokens,
            context_token_source,
        ) = supervision_context_fields(snapshot);
        let model = cycle.get("model").unwrap_or(&Value::Null);
        let (
            model_input_tokens,
            model_output_tokens,
            model_total_tokens,
            model_cached_input_tokens,
            model_reasoning_tokens,
            model_token_source,
        ) = supervision_model_token_fields(model, snapshot);
        let model_summary = value_text(model, &["summary", "error"]);
        let model_name = value_text(model, &["modelName", "model_name"]);
        let provider_id = value_text(model, &["providerId", "provider_id"]);
        let provider_name = value_text(model, &["providerName", "provider_name"]);
        let model_status = if value_text(model, &["status"]).eq_ignore_ascii_case("failed") {
            "failed".to_string()
        } else {
            "completed".to_string()
        };
        steps.push(SupervisionStep {
            step_id: format!("step:{assistant_message_id}:cycle:{model_step_index}:model"),
            step_type: "model_call".to_string(),
            status: model_status,
            title: format!("模型循环第 {model_step_index} 轮"),
            summary: clipped(
                if model_summary.is_empty() {
                    "模型基于本轮上下文进行判断"
                } else {
                    &model_summary
                },
                500,
            ),
            detail_preview: clipped(
                &[
                    if provider_name.is_empty() {
                        String::new()
                    } else {
                        format!("provider={provider_name}")
                    },
                    if model_name.is_empty() {
                        String::new()
                    } else {
                        format!("model={model_name}")
                    },
                    model_summary,
                ]
                .into_iter()
                .filter(|value| !value.is_empty())
                .collect::<Vec<_>>()
                .join("\n"),
                2000,
            ),
            tool_name: String::new(),
            call_id: String::new(),
            model_name,
            provider_id,
            provider_name,
            model_step_index,
            context_snapshot_json: context_snapshot_json.clone(),
            context_message_count,
            context_input_tokens,
            context_token_source: context_token_source.clone(),
            model_input_tokens,
            model_output_tokens,
            model_total_tokens,
            model_cached_input_tokens,
            model_reasoning_tokens,
            model_token_source,
            started_at_epoch_ms: 0,
            ended_at_epoch_ms: 0,
            duration_ms: 0,
        });
        if let Some(tools) = cycle.get("tools").and_then(Value::as_array) {
            for (tool_offset, tool) in tools.iter().enumerate() {
                let tool_name = value_text(tool, &["name"]);
                let call_id = value_text(tool, &["toolCallId", "tool_call_id"]);
                let summary = value_text(tool, &["summary", "error"]);
                let ok = tool.get("ok").and_then(Value::as_bool).unwrap_or(true);
                steps.push(SupervisionStep {
                    step_id: format!(
                        "step:{assistant_message_id}:cycle:{model_step_index}:tool:{}",
                        stable_fragment(&call_id, &tool_offset.to_string())
                    ),
                    step_type: "tool_call".to_string(),
                    status: if ok { "completed" } else { "failed" }.to_string(),
                    title: if tool_name.is_empty() {
                        format!("第 {model_step_index} 轮工具调用")
                    } else {
                        format!("工具：{tool_name}")
                    },
                    summary: clipped(&summary, 500),
                    detail_preview: clipped(&summary, 2000),
                    tool_name,
                    call_id,
                    model_name: String::new(),
                    provider_id: String::new(),
                    provider_name: String::new(),
                    model_step_index,
                    context_snapshot_json: context_snapshot_json.clone(),
                    context_message_count,
                    context_input_tokens,
                    context_token_source: context_token_source.clone(),
                    model_input_tokens: 0,
                    model_output_tokens: 0,
                    model_total_tokens: 0,
                    model_cached_input_tokens: 0,
                    model_reasoning_tokens: 0,
                    model_token_source: String::new(),
                    started_at_epoch_ms: 0,
                    ended_at_epoch_ms: 0,
                    duration_ms: 0,
                });
            }
        }
    }
    steps
}

fn collect_supervision_steps(
    message: &Value,
    assistant_message_id: &str,
    question_preview: &str,
    answer_status: &str,
) -> Vec<SupervisionStep> {
    let started_at = value_i64(
        message,
        &[
            "agentRuntimeStartedAtEpochMs",
            "messageExecutionStartedAtEpochMs",
        ],
    );
    let ended_at = value_i64(
        message,
        &[
            "agentRuntimeEndedAtEpochMs",
            "messageExecutionEndedAtEpochMs",
        ],
    );
    let duration_ms = value_i64(
        message,
        &["agentRuntimeDurationMs", "messageExecutionDurationMs"],
    );
    let mut steps = vec![SupervisionStep {
        step_id: format!("step:{assistant_message_id}:request"),
        step_type: "request".to_string(),
        status: "completed".to_string(),
        title: "用户问题".to_string(),
        summary: clipped(question_preview, 240),
        detail_preview: clipped(question_preview, 1200),
        tool_name: String::new(),
        call_id: String::new(),
        model_name: String::new(),
        provider_id: String::new(),
        provider_name: String::new(),
        model_step_index: 0,
        context_snapshot_json: "{}".to_string(),
        context_message_count: 0,
        context_input_tokens: 0,
        context_token_source: String::new(),
        model_input_tokens: 0,
        model_output_tokens: 0,
        model_total_tokens: 0,
        model_cached_input_tokens: 0,
        model_reasoning_tokens: 0,
        model_token_source: String::new(),
        started_at_epoch_ms: started_at,
        ended_at_epoch_ms: started_at,
        duration_ms: 0,
    }];
    let cycle_steps = collect_execution_cycle_steps(message, assistant_message_id);
    let has_execution_cycles = !cycle_steps.is_empty();
    steps.extend(cycle_steps);

    if let Some(logs) = message.get("processLog").and_then(Value::as_array) {
        for (index, item) in logs.iter().enumerate() {
            let text = value_text(item, &["text", "content"]);
            if text.is_empty() {
                continue;
            }
            let raw_id = value_text(item, &["id"]);
            let fragment = stable_fragment(&raw_id, &format!("{index}"));
            let tool_name = find_nested_text(item, &["tool_name", "toolName"]);
            let call_id =
                find_nested_text(item, &["toolCallId", "tool_call_id", "call_id", "callId"]);
            let step_type = supervision_step_type(item, "observation");
            if has_execution_cycles && matches!(step_type.as_str(), "model_call" | "tool_call") {
                continue;
            }
            steps.push(SupervisionStep {
                step_id: format!("step:{assistant_message_id}:log:{fragment}"),
                step_type,
                status: process_step_status(item),
                title: clipped(&text, 160),
                summary: clipped(&text, 320),
                detail_preview: clipped(&text, 2000),
                tool_name,
                call_id,
                model_name: String::new(),
                provider_id: String::new(),
                provider_name: String::new(),
                model_step_index: 0,
                context_snapshot_json: "{}".to_string(),
                context_message_count: 0,
                context_input_tokens: 0,
                context_token_source: String::new(),
                model_input_tokens: 0,
                model_output_tokens: 0,
                model_total_tokens: 0,
                model_cached_input_tokens: 0,
                model_reasoning_tokens: 0,
                model_token_source: String::new(),
                started_at_epoch_ms: 0,
                ended_at_epoch_ms: 0,
                duration_ms: 0,
            });
        }
    }

    if let Some(operations) = message.get("operations").and_then(Value::as_array) {
        let mut model_operation_index = 0i64;
        for (index, item) in operations.iter().enumerate() {
            let raw_id = value_text(item, &["operationId", "operation_id", "id"]);
            let fragment = stable_fragment(&raw_id, &format!("{index}"));
            let title = value_text(item, &["title"]);
            let summary = value_text(item, &["summary"]);
            let detail = value_text(item, &["detail"]);
            let tool_name = find_nested_text(item, &["tool_name", "toolName"]);
            let call_id =
                find_nested_text(item, &["call_id", "callId", "tool_call_id", "toolCallId"]);
            let step_type = supervision_step_type(item, "operation");
            if has_execution_cycles && matches!(step_type.as_str(), "model_call" | "tool_call") {
                continue;
            }
            let metadata = item
                .get("meta")
                .or_else(|| item.get("payload"))
                .unwrap_or(&Value::Null);
            if step_type == "model_call" {
                model_operation_index += 1;
            }
            let model_step_index = if step_type == "model_call" {
                value_i64(metadata, &["model_step_index", "modelStepIndex", "index"])
                    .max(model_operation_index)
            } else {
                0
            };
            let (
                model_input_tokens,
                model_output_tokens,
                model_total_tokens,
                model_cached_input_tokens,
                model_reasoning_tokens,
                model_token_source,
            ) = supervision_model_token_fields(metadata, &Value::Null);
            steps.push(SupervisionStep {
                step_id: format!("step:{assistant_message_id}:operation:{fragment}"),
                step_type,
                status: process_step_status(item),
                title: clipped(
                    if title.is_empty() {
                        "执行步骤"
                    } else {
                        &title
                    },
                    160,
                ),
                summary: clipped(&summary, 500),
                detail_preview: clipped(&detail, 2000),
                tool_name,
                call_id,
                model_name: value_text(metadata, &["model_name", "modelName"]),
                provider_id: value_text(metadata, &["provider_id", "providerId"]),
                provider_name: value_text(metadata, &["provider_name", "providerName"]),
                model_step_index,
                context_snapshot_json: "{}".to_string(),
                context_message_count: 0,
                context_input_tokens: 0,
                context_token_source: String::new(),
                model_input_tokens,
                model_output_tokens,
                model_total_tokens,
                model_cached_input_tokens,
                model_reasoning_tokens,
                model_token_source,
                started_at_epoch_ms: 0,
                ended_at_epoch_ms: 0,
                duration_ms: 0,
            });
        }
    }

    let answer = value_text(message, &["content"]);
    if !answer.is_empty() {
        steps.push(SupervisionStep {
            step_id: format!("step:{assistant_message_id}:answer"),
            step_type: "final_answer".to_string(),
            status: answer_status.to_string(),
            title: "最终回答".to_string(),
            summary: clipped(&answer, 360),
            detail_preview: clipped(&answer, 4000),
            tool_name: String::new(),
            call_id: String::new(),
            model_name: String::new(),
            provider_id: String::new(),
            provider_name: String::new(),
            model_step_index: 0,
            context_snapshot_json: "{}".to_string(),
            context_message_count: 0,
            context_input_tokens: 0,
            context_token_source: String::new(),
            model_input_tokens: 0,
            model_output_tokens: 0,
            model_total_tokens: 0,
            model_cached_input_tokens: 0,
            model_reasoning_tokens: 0,
            model_token_source: String::new(),
            started_at_epoch_ms: ended_at,
            ended_at_epoch_ms: ended_at,
            duration_ms,
        });
    }
    steps
}

fn supervision_step_json(step: &SupervisionStep, index: usize, parent_step_id: &str) -> Value {
    json!({
        "step_id": step.step_id,
        "parent_step_id": parent_step_id,
        "sort_order": index as i64,
        "step_type": step.step_type,
        "status": step.status,
        "title": step.title,
        "summary": step.summary,
        "detail_preview": step.detail_preview,
        "tool_name": step.tool_name,
        "call_id": step.call_id,
        "model_name": step.model_name,
        "provider_id": step.provider_id,
        "provider_name": step.provider_name,
        "model_step_index": step.model_step_index,
        "context_snapshot": serde_json::from_str::<Value>(&step.context_snapshot_json)
            .unwrap_or_else(|_| json!({})),
        "context_message_count": step.context_message_count,
        "context_input_tokens": step.context_input_tokens,
        "context_token_source": step.context_token_source,
        "model_input_tokens": step.model_input_tokens,
        "model_output_tokens": step.model_output_tokens,
        "model_total_tokens": step.model_total_tokens,
        "model_cached_input_tokens": step.model_cached_input_tokens,
        "model_reasoning_tokens": step.model_reasoning_tokens,
        "model_token_source": step.model_token_source,
        "started_at_epoch_ms": step.started_at_epoch_ms,
        "ended_at_epoch_ms": step.ended_at_epoch_ms,
        "duration_ms": step.duration_ms
    })
}

fn build_supervision_details(
    chat_session_id: &str,
    payload: &Value,
    updated_at: &str,
) -> Result<Vec<Value>, String> {
    let messages = payload
        .get("messages")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut previous_user_id = String::new();
    let mut previous_user_content = String::new();
    let mut details = Vec::new();
    for message in messages {
        let role = value_text(&message, &["role"]).to_lowercase();
        let message_id = value_text(&message, &["id"]);
        if role == "user" {
            previous_user_id = message_id;
            previous_user_content = value_text(&message, &["content"]);
            continue;
        }
        if message_id.is_empty() {
            continue;
        }
        let content = value_text(&message, &["content"]);
        let has_steps = message
            .get("processLog")
            .and_then(Value::as_array)
            .is_some_and(|items| !items.is_empty())
            || message
                .get("operations")
                .and_then(Value::as_array)
                .is_some_and(|items| !items.is_empty());
        if content.is_empty() && !has_steps {
            continue;
        }
        let explicit_answer_id = value_text(&message, &["answerId", "answer_id"]);
        let answer_id = if explicit_answer_id.is_empty() {
            if message_id.starts_with("ans_") {
                message_id.clone()
            } else {
                format!("ans_{message_id}")
            }
        } else {
            explicit_answer_id
        };
        let status = supervision_answer_status(&message);
        let started_at = value_i64(
            &message,
            &[
                "agentRuntimeStartedAtEpochMs",
                "messageExecutionStartedAtEpochMs",
            ],
        );
        let ended_at = value_i64(
            &message,
            &[
                "agentRuntimeEndedAtEpochMs",
                "messageExecutionEndedAtEpochMs",
            ],
        );
        let duration_ms = value_i64(
            &message,
            &["agentRuntimeDurationMs", "messageExecutionDurationMs"],
        );
        let nested_run_id = find_nested_text(&message, &["run_id", "runId"]);
        let run_id = if nested_run_id.is_empty() {
            format!("run:{message_id}")
        } else {
            nested_run_id
        };
        let request_id = find_nested_text(&message, &["request_id", "requestId"]);
        let collected_steps =
            collect_supervision_steps(&message, &message_id, &previous_user_content, &status);
        let model_round_count = collected_steps
            .iter()
            .filter(|step| step.step_type == "model_call")
            .count() as i64;
        let tool_call_count = collected_steps
            .iter()
            .filter(|step| step.step_type == "tool_call")
            .count() as i64;
        let mut steps = Vec::new();
        let mut edges = Vec::new();
        let mut previous_step_id = String::new();
        for (index, step) in collected_steps.iter().enumerate() {
            steps.push(supervision_step_json(step, index, &previous_step_id));
            if !previous_step_id.is_empty() {
                edges.push(json!({
                    "edge_id": format!("edge:{message_id}:{index}"),
                    "source_step_id": previous_step_id,
                    "target_step_id": step.step_id,
                    "edge_type": "sequence",
                    "label": "",
                    "sort_order": index as i64
                }));
            }
            previous_step_id = step.step_id.clone();
        }
        details.push(json!({
            "answer": {
                "assistant_message_id": message_id,
                "answer_id": answer_id,
                "chat_session_id": chat_session_id,
                "user_message_id": previous_user_id,
                "question_preview": clipped(&previous_user_content, 1200),
                "answer_preview": clipped(&content, 4000),
                "status": status,
                "started_at_epoch_ms": started_at,
                "ended_at_epoch_ms": ended_at,
                "duration_ms": duration_ms,
                "updated_at": updated_at
            },
            "run": {
                "run_id": run_id,
                "request_id": request_id,
                "status": status,
                "model_round_count": model_round_count,
                "tool_call_count": tool_call_count,
                "started_at_epoch_ms": started_at,
                "ended_at_epoch_ms": ended_at,
                "duration_ms": duration_ms,
                "updated_at": updated_at
            },
            "steps": steps,
            "edges": edges
        }));
    }
    Ok(details)
}

fn list_canonical_sessions(
    app: &tauri::AppHandle,
    username: &str,
    project_id: Option<&str>,
) -> Result<Vec<Value>, String> {
    let connection = open_canonical_database(&app)?;
    let mut statement = connection
        .prepare(
            "SELECT project_id, chat_session_id, session_json, updated_at
             FROM desktop_project_chat_sessions
             WHERE username = ?1 AND (?2 IS NULL OR project_id = ?2)
             ORDER BY updated_at DESC, chat_session_id ASC",
        )
        .map_err(|err| err.to_string())?;
    let rows = statement
        .query_map(params![username, project_id], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
            ))
        })
        .map_err(|err| err.to_string())?;
    let mut sessions = Vec::new();
    for row in rows {
        let (stored_project_id, chat_session_id, session_json, updated_at) =
            row.map_err(|err| err.to_string())?;
        let session =
            serde_json::from_str::<Value>(&session_json).map_err(|err| err.to_string())?;
        let mut merged = session;
        if value_text(&merged, &["id"]).is_empty() {
            merged["id"] = Value::String(chat_session_id.clone());
        }
        if value_text(&merged, &["updated_at"]).is_empty() {
            merged["updated_at"] = Value::String(updated_at);
        }
        merged["project_id"] = Value::String(stored_project_id);
        sessions.push(merged);
    }
    sessions.sort_by(compare_sessions_by_stable_position);
    Ok(sessions)
}

#[tauri::command]
pub fn project_chat_list_sessions(
    app: tauri::AppHandle,
    username: String,
    project_id: String,
) -> Result<Vec<Value>, String> {
    let username = normalized(&username, "用户名")?;
    let project_id = normalized(&project_id, "项目 ID")?;
    list_canonical_sessions(&app, &username, Some(&project_id))
}

#[tauri::command]
pub fn project_chat_list_all_sessions(
    app: tauri::AppHandle,
    username: String,
) -> Result<Vec<Value>, String> {
    let username = normalized(&username, "用户名")?;
    list_canonical_sessions(&app, &username, None)
}

#[tauri::command]
pub fn project_chat_upsert_session(
    app: tauri::AppHandle,
    username: String,
    project_id: String,
    session: Value,
) -> Result<bool, String> {
    let username = normalized(&username, "用户名")?;
    let project_id = normalized(&project_id, "项目 ID")?;
    let session_project_id = normalized_session_project_id(&project_id, &session)?;
    let session_id = normalized(
        session
            .get("id")
            .and_then(Value::as_str)
            .unwrap_or_default(),
        "聊天会话 ID",
    )?;
    let updated_at = value_text(&session, &["updated_at", "created_at"]);
    let connection = open_canonical_database(&app)?;
    let runtime_json = connection
        .query_row(
            "SELECT runtime_json FROM desktop_project_chat_runtimes
             WHERE username = ?1 AND project_id = ?2 AND chat_session_id = ?3",
            params![username, session_project_id, session_id],
            |row| row.get::<_, String>(0),
        )
        .optional()
        .map_err(|err| err.to_string())?;
    let runtime = runtime_json
        .as_ref()
        .map(|value| serde_json::from_str::<Value>(value).map_err(|err| err.to_string()))
        .transpose()?
        .unwrap_or_else(|| json!({"version": 1, "updated_at": updated_at, "messages": []}));
    let mut normalized_session = session;
    normalized_session["project_id"] = Value::String(session_project_id.clone());
    let merged = merge_session_with_runtime(
        &session_id,
        Some(&normalized_session),
        &runtime,
        &updated_at,
    );
    upsert_canonical_session(
        &connection,
        &username,
        &session_project_id,
        &session_id,
        &merged,
        &updated_at,
    )?;
    if runtime_json.is_none() {
        upsert_canonical_runtime(
            &connection,
            &username,
            &session_project_id,
            &session_id,
            &runtime,
            &updated_at,
        )?;
    }
    Ok(true)
}

#[tauri::command]
pub fn project_chat_replace_sessions(
    app: tauri::AppHandle,
    username: String,
    project_id: String,
    sessions: Vec<Value>,
) -> Result<usize, String> {
    let username = normalized(&username, "用户名")?;
    let project_id = normalized(&project_id, "项目 ID")?;
    let connection = open_canonical_database(&app)?;
    let mut written = 0;
    for session in &sessions {
        let session_project_id = normalized_session_project_id(&project_id, session)?;
        let session_id = normalized(
            session
                .get("id")
                .and_then(Value::as_str)
                .unwrap_or_default(),
            "聊天会话 ID",
        )?;
        let updated_at = value_text(session, &["updated_at", "created_at"]);
        let runtime_json = connection
            .query_row(
                "SELECT runtime_json FROM desktop_project_chat_runtimes
                 WHERE username = ?1 AND project_id = ?2 AND chat_session_id = ?3",
                params![username, session_project_id, session_id],
                |row| row.get::<_, String>(0),
            )
            .optional()
            .map_err(|err| err.to_string())?;
        let runtime = runtime_json
            .as_ref()
            .map(|value| serde_json::from_str::<Value>(value).map_err(|err| err.to_string()))
            .transpose()?
            .unwrap_or_else(|| json!({"version": 1, "updated_at": updated_at, "messages": []}));
        let mut normalized_session = session.clone();
        normalized_session["project_id"] = Value::String(session_project_id.clone());
        let merged = merge_session_with_runtime(
            &session_id,
            Some(&normalized_session),
            &runtime,
            &updated_at,
        );
        upsert_canonical_session(
            &connection,
            &username,
            &session_project_id,
            &session_id,
            &merged,
            &updated_at,
        )?;
        if runtime_json.is_none() {
            upsert_canonical_runtime(
                &connection,
                &username,
                &session_project_id,
                &session_id,
                &runtime,
                &updated_at,
            )?;
        }
        written += 1;
    }
    Ok(written)
}

#[tauri::command]
pub fn project_chat_read_runtime(
    app: tauri::AppHandle,
    username: String,
    project_id: String,
    chat_session_id: String,
) -> Result<Option<Value>, String> {
    let username = normalized(&username, "用户名")?;
    let project_id = normalized(&project_id, "项目 ID")?;
    let chat_session_id = normalized(&chat_session_id, "聊天会话 ID")?;
    let connection = open_canonical_database(&app)?;
    let payload = connection
        .query_row(
            "SELECT runtime_json FROM desktop_project_chat_runtimes
             WHERE username = ?1 AND project_id = ?2 AND chat_session_id = ?3",
            params![username, project_id, chat_session_id],
            |row| row.get::<_, String>(0),
        )
        .optional()
        .map_err(|err| err.to_string())?;
    payload
        .map(|value| serde_json::from_str::<Value>(&value).map_err(|err| err.to_string()))
        .transpose()
}

#[tauri::command]
pub fn project_chat_read_message_snapshot(
    app: tauri::AppHandle,
    username: String,
    project_id: String,
    chat_session_id: String,
) -> Result<Vec<Value>, String> {
    let username = normalized(&username, "用户名")?;
    let project_id = normalized(&project_id, "项目 ID")?;
    let chat_session_id = normalized(&chat_session_id, "聊天会话 ID")?;
    let connection = open_canonical_database(&app)?;
    let snapshot = connection
        .query_row(
            "SELECT messages_json FROM desktop_project_chat_message_snapshots
             WHERE username = ?1 AND project_id = ?2 AND chat_session_id = ?3",
            params![username, project_id, chat_session_id],
            |row| row.get::<_, String>(0),
        )
        .optional()
        .map_err(|err| err.to_string())?;
    if let Some(value) = snapshot {
        return serde_json::from_str::<Vec<Value>>(&value).map_err(|err| err.to_string());
    }
    let runtime = connection
        .query_row(
            "SELECT runtime_json FROM desktop_project_chat_runtimes
             WHERE username = ?1 AND project_id = ?2 AND chat_session_id = ?3",
            params![username, project_id, chat_session_id],
            |row| row.get::<_, String>(0),
        )
        .optional()
        .map_err(|err| err.to_string())?;
    let messages = runtime
        .and_then(|value| serde_json::from_str::<Value>(&value).ok())
        .and_then(|value| value.get("messages").and_then(Value::as_array).cloned())
        .unwrap_or_default();
    let payload = serde_json::to_string(&messages).map_err(|err| err.to_string())?;
    connection
        .execute(
            "INSERT OR REPLACE INTO desktop_project_chat_message_snapshots
                 (username, project_id, chat_session_id, messages_json, updated_at)
             VALUES (?1, ?2, ?3, ?4, datetime('now'))",
            params![username, project_id, chat_session_id, payload],
        )
        .map_err(|err| err.to_string())?;
    Ok(messages)
}

#[tauri::command]
pub fn project_chat_write_runtime(
    app: tauri::AppHandle,
    username: String,
    project_id: String,
    chat_session_id: String,
    payload: Value,
) -> Result<bool, String> {
    let username = normalized(&username, "用户名")?;
    let project_id = normalized(&project_id, "项目 ID")?;
    let chat_session_id = normalized(&chat_session_id, "聊天会话 ID")?;
    let requested_updated_at = value_text(&payload, &["updated_at"]);
    let connection = open_canonical_database(&app)?;
    let existing_runtime_json = connection
        .query_row(
            "SELECT runtime_json FROM desktop_project_chat_runtimes
             WHERE username = ?1 AND project_id = ?2 AND chat_session_id = ?3",
            params![username, project_id, chat_session_id],
            |row| row.get::<_, String>(0),
        )
        .optional()
        .map_err(|err| err.to_string())?;
    let existing_session_json = connection
        .query_row(
            "SELECT session_json FROM desktop_project_chat_sessions
             WHERE username = ?1 AND project_id = ?2 AND chat_session_id = ?3",
            params![username, project_id, chat_session_id],
            |row| row.get::<_, String>(0),
        )
        .optional()
        .map_err(|err| err.to_string())?;
    let existing_envelope = existing_runtime_json.as_ref().map(|runtime_json| {
        json!({
            "runtime": serde_json::from_str::<Value>(runtime_json).unwrap_or_else(|_| json!({})),
            "session": existing_session_json.as_ref()
                .and_then(|value| serde_json::from_str::<Value>(value).ok())
                .unwrap_or_else(|| json!({}))
        })
    });
    let merged_payload = merge_runtime_payload(
        existing_envelope
            .as_ref()
            .and_then(|value| value.get("runtime")),
        &payload,
    );
    let activity_updated_at = runtime_activity_updated_at(
        existing_envelope.as_ref(),
        &merged_payload,
        &requested_updated_at,
    );
    let mut session = merge_session_with_runtime(
        &chat_session_id,
        existing_envelope
            .as_ref()
            .and_then(|value| value.get("session")),
        &merged_payload,
        &activity_updated_at,
    );
    session["project_id"] = Value::String(project_id.clone());
    upsert_canonical_runtime(
        &connection,
        &username,
        &project_id,
        &chat_session_id,
        &merged_payload,
        &activity_updated_at,
    )?;
    upsert_canonical_message_snapshot(
        &connection,
        &username,
        &project_id,
        &chat_session_id,
        &merged_payload,
        &activity_updated_at,
    )?;
    upsert_canonical_session(
        &connection,
        &username,
        &project_id,
        &chat_session_id,
        &session,
        &activity_updated_at,
    )?;
    Ok(true)
}

#[tauri::command]
pub fn agent_supervision_search_answers(
    app: tauri::AppHandle,
    username: String,
    project_id: String,
    query: String,
    limit: Option<usize>,
) -> Result<Vec<Value>, String> {
    let username = normalized(&username, "用户名")?;
    let project_id = normalized(&project_id, "项目 ID")?;
    let query = query.trim().to_lowercase();
    let limit = limit.unwrap_or(50).clamp(1, 200);
    let mut answers = Vec::new();
    for envelope in load_json_envelopes(&app, &username, &project_id)? {
        let chat_session_id = value_text(&envelope, &["chat_session_id"]);
        let updated_at = value_text(&envelope, &["updated_at"]);
        let runtime = envelope
            .get("runtime")
            .cloned()
            .unwrap_or_else(|| json!({}));
        for detail in build_supervision_details(&chat_session_id, &runtime, &updated_at)? {
            let answer = detail.get("answer").cloned().unwrap_or_else(|| json!({}));
            let haystack = [
                value_text(&answer, &["answer_id"]),
                value_text(&answer, &["assistant_message_id"]),
                value_text(&answer, &["question_preview"]),
                value_text(&answer, &["answer_preview"]),
            ]
            .join("\n")
            .to_lowercase();
            if query.is_empty() || haystack.contains(&query) {
                answers.push(answer);
            }
        }
    }
    answers.sort_by(|left, right| {
        value_text(right, &["updated_at"])
            .cmp(&value_text(left, &["updated_at"]))
            .then_with(|| {
                value_i64(right, &["started_at_epoch_ms"])
                    .cmp(&value_i64(left, &["started_at_epoch_ms"]))
            })
    });
    answers.truncate(limit);
    Ok(answers)
}

#[tauri::command]
pub fn agent_supervision_get_answer(
    app: tauri::AppHandle,
    username: String,
    project_id: String,
    answer_id: String,
) -> Result<Option<Value>, String> {
    let username = normalized(&username, "用户名")?;
    let project_id = normalized(&project_id, "项目 ID")?;
    let answer_id = normalized(&answer_id, "回答 ID")?;
    let alternate_answer_id = if answer_id.starts_with("ans_") {
        answer_id.trim_start_matches("ans_").to_string()
    } else {
        format!("ans_{answer_id}")
    };
    for envelope in load_json_envelopes(&app, &username, &project_id)? {
        let chat_session_id = value_text(&envelope, &["chat_session_id"]);
        let updated_at = value_text(&envelope, &["updated_at"]);
        let runtime = envelope
            .get("runtime")
            .cloned()
            .unwrap_or_else(|| json!({}));
        for detail in build_supervision_details(&chat_session_id, &runtime, &updated_at)? {
            let answer = detail.get("answer").cloned().unwrap_or_else(|| json!({}));
            let stored_answer_id = value_text(&answer, &["answer_id"]);
            let assistant_message_id = value_text(&answer, &["assistant_message_id"]);
            if stored_answer_id == answer_id
                || assistant_message_id == answer_id
                || stored_answer_id == alternate_answer_id
                || assistant_message_id == alternate_answer_id
            {
                return Ok(Some(detail));
            }
        }
    }
    Ok(None)
}

#[tauri::command]
pub fn agent_supervision_find_answer(
    app: tauri::AppHandle,
    username: String,
    answer_id: String,
    project_id: Option<String>,
) -> Result<Option<Value>, String> {
    let username = normalized(&username, "用户名")?;
    let answer_id = normalized(&answer_id, "回答 ID")?;
    let project_id = project_id
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or_default()
        .to_string();
    let alternate_answer_id = if answer_id.starts_with("ans_") {
        answer_id.trim_start_matches("ans_").to_string()
    } else {
        format!("ans_{answer_id}")
    };
    let connection = open_canonical_database(&app)?;
    let mut statement = connection
        .prepare(
            "SELECT project_id, chat_session_id, runtime_json, updated_at
             FROM desktop_project_chat_runtimes
             WHERE (?1 = '' OR username = ?1)
               AND (?2 = '' OR project_id = ?2)",
        )
        .map_err(|err| err.to_string())?;
    let rows = statement
        .query_map(
            params![
                if project_id.is_empty() {
                    username
                } else {
                    String::new()
                },
                project_id
            ],
            |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, String>(3)?,
                ))
            },
        )
        .map_err(|err| err.to_string())?;
    for row in rows {
        let (project_id, chat_session_id, runtime_json, updated_at) =
            row.map_err(|err| err.to_string())?;
        let runtime =
            serde_json::from_str::<Value>(&runtime_json).map_err(|err| err.to_string())?;
        for detail in build_supervision_details(&chat_session_id, &runtime, &updated_at)? {
            let answer = detail.get("answer").cloned().unwrap_or_else(|| json!({}));
            let stored_answer_id = value_text(&answer, &["answer_id"]);
            let assistant_message_id = value_text(&answer, &["assistant_message_id"]);
            if stored_answer_id == answer_id
                || assistant_message_id == answer_id
                || stored_answer_id == alternate_answer_id
                || assistant_message_id == alternate_answer_id
            {
                return Ok(Some(json!({
                    "project_id": project_id,
                    "detail": detail,
                })));
            }
        }
    }
    Ok(None)
}

#[tauri::command]
pub fn project_chat_delete_session(
    app: tauri::AppHandle,
    username: String,
    project_id: String,
    chat_session_id: String,
) -> Result<bool, String> {
    let username = normalized(&username, "用户名")?;
    let project_id = normalized(&project_id, "项目 ID")?;
    let chat_session_id = normalized(&chat_session_id, "聊天会话 ID")?;
    let mut connection = open_canonical_database(&app)?;
    let transaction = connection.transaction().map_err(|err| err.to_string())?;
    transaction
        .execute(
            "DELETE FROM desktop_project_chat_sessions
             WHERE username = ?1 AND project_id = ?2 AND chat_session_id = ?3",
            params![username, project_id, chat_session_id],
        )
        .map_err(|err| err.to_string())?;
    transaction
        .execute(
            "DELETE FROM desktop_project_chat_runtimes
             WHERE username = ?1 AND project_id = ?2 AND chat_session_id = ?3",
            params![username, project_id, chat_session_id],
        )
        .map_err(|err| err.to_string())?;
    transaction.commit().map_err(|err| err.to_string())?;
    Ok(true)
}

#[tauri::command]
pub fn local_ai_task_list(app: tauri::AppHandle) -> Result<Vec<Value>, String> {
    let connection = open_canonical_database(&app)?;
    let mut statement = connection
        .prepare(
            "SELECT task_json FROM desktop_local_ai_tasks
             ORDER BY updated_at DESC, task_id ASC",
        )
        .map_err(|err| err.to_string())?;
    let rows = statement
        .query_map([], |row| row.get::<_, String>(0))
        .map_err(|err| err.to_string())?;
    rows.map(|row| {
        let payload = row.map_err(|err| err.to_string())?;
        serde_json::from_str::<Value>(&payload).map_err(|err| err.to_string())
    })
    .collect()
}

#[tauri::command]
pub fn local_ai_task_replace(app: tauri::AppHandle, tasks: Vec<Value>) -> Result<bool, String> {
    let mut connection = open_canonical_database(&app)?;
    let transaction = connection.transaction().map_err(|err| err.to_string())?;
    transaction
        .execute("DELETE FROM desktop_local_ai_tasks", [])
        .map_err(|err| err.to_string())?;
    for task in tasks {
        let task_id = normalized(
            task.get("id").and_then(Value::as_str).unwrap_or_default(),
            "本地 AI 任务 ID",
        )?;
        let updated_at = value_text(
            &task,
            &["updatedAt", "updated_at", "createdAt", "created_at"],
        );
        let task_json = serde_json::to_string(&task).map_err(|err| err.to_string())?;
        transaction
            .execute(
                "INSERT INTO desktop_local_ai_tasks(task_id, task_json, updated_at)
                 VALUES (?1, ?2, ?3)",
                params![task_id, task_json, updated_at],
            )
            .map_err(|err| err.to_string())?;
    }
    transaction.commit().map_err(|err| err.to_string())?;
    Ok(true)
}

#[tauri::command]
pub fn local_record_list(app: tauri::AppHandle) -> Result<Vec<Value>, String> {
    let connection = open_canonical_database(&app)?;
    let mut statement = connection
        .prepare(
            "SELECT record_key, value_json, updated_at FROM desktop_local_records
             ORDER BY record_key ASC",
        )
        .map_err(|err| err.to_string())?;
    let rows = statement
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
            ))
        })
        .map_err(|err| err.to_string())?;
    rows.map(|row| {
        let (key, value_json, updated_at) = row.map_err(|err| err.to_string())?;
        let value = serde_json::from_str::<Value>(&value_json).map_err(|err| err.to_string())?;
        Ok(json!({ "key": key, "value": value, "updated_at": updated_at }))
    })
    .collect()
}

#[tauri::command]
pub fn local_record_write(
    app: tauri::AppHandle,
    key: String,
    value: Value,
) -> Result<bool, String> {
    let key = normalized(&key, "本地记录键")?;
    let value_json = serde_json::to_string(&value).map_err(|err| err.to_string())?;
    let updated_at = chrono::Utc::now().to_rfc3339();
    let connection = open_canonical_database(&app)?;
    connection
        .execute(
            "INSERT INTO desktop_local_records(record_key, value_json, updated_at)
             VALUES (?1, ?2, ?3)
             ON CONFLICT(record_key) DO UPDATE SET
                 value_json = excluded.value_json,
                 updated_at = excluded.updated_at",
            params![key, value_json, updated_at],
        )
        .map_err(|err| err.to_string())?;
    Ok(true)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn session_project_scope_defaults_missing_project_id() {
        let project_id = normalized_session_project_id("project-a", &json!({"id": "chat-a"}))
            .expect("missing embedded project id should use request scope");
        assert_eq!(project_id, "project-a");
    }

    #[test]
    fn session_project_scope_rejects_mismatched_project_id() {
        let result = normalized_session_project_id(
            "project-a",
            &json!({"id": "chat-a", "project_id": "project-b"}),
        );
        assert!(result.is_err());
    }

    fn temporary_test_directory(name: &str) -> PathBuf {
        let suffix = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("system time after epoch")
            .as_nanos();
        std::env::temp_dir().join(format!("{name}-{suffix}"))
    }

    #[test]
    fn session_metadata_is_derived_from_runtime_messages() {
        let runtime = json!({
            "messages": [
                {"id": "user-1", "role": "user", "content": "展示目录结构"},
                {"id": "assistant-1", "role": "assistant", "content": "这是目录结构"}
            ]
        });
        let session = build_session_from_runtime("local-1", &runtime, "2026-07-21T00:00:00Z");
        assert_eq!(session["id"], "local-1");
        assert_eq!(session["title"], "展示目录结构");
        assert_eq!(session["message_count"], 2);
        assert_eq!(session["preview"], "这是目录结构");
        assert_eq!(session["last_message_id"], "assistant-1");
    }

    #[test]
    fn session_position_is_stable_when_message_activity_changes() {
        let mut sessions = vec![
            json!({
                "id": "older",
                "created_at": "2026-07-20T00:00:00Z",
                "updated_at": "2026-07-28T00:00:00Z",
                "last_message_at": "2026-07-28T00:00:00Z"
            }),
            json!({
                "id": "newer",
                "created_at": "2026-07-21T00:00:00Z",
                "updated_at": "2026-07-21T00:00:00Z",
                "last_message_at": "2026-07-21T00:00:00Z"
            }),
        ];
        sessions.sort_by(compare_sessions_by_stable_position);
        assert_eq!(value_text(&sessions[0], &["id"]), "newer");
        assert_eq!(value_text(&sessions[1], &["id"]), "older");
    }

    #[test]
    fn runtime_persistence_without_message_changes_preserves_session_activity_time() {
        let existing = json!({
            "updated_at": "2026-07-21T00:00:00Z",
            "session": {
                "id": "local-1",
                "created_at": "2026-07-20T00:00:00Z",
                "updated_at": "2026-07-21T00:00:00Z",
                "last_message_at": "2026-07-21T00:00:00Z"
            },
            "runtime": {
                "updated_at": "2026-07-21T00:00:00Z",
                "messages": [
                    {"id": "user-1", "role": "user", "content": "检查项目"},
                    {"id": "assistant-1", "role": "assistant", "content": "处理中"}
                ]
            }
        });
        let next_runtime = json!({
            "updated_at": "2026-07-28T00:00:00Z",
            "messages": [
                {"id": "user-1", "role": "user", "content": "检查项目"},
                {
                    "id": "assistant-1",
                    "role": "assistant",
                    "content": "处理中",
                    "processLog": [{"text": "切换会话时保存运行状态"}]
                }
            ]
        });

        assert_eq!(
            runtime_activity_updated_at(Some(&existing), &next_runtime, "2026-07-28T00:00:00Z"),
            "2026-07-21T00:00:00Z"
        );
    }

    #[test]
    fn runtime_persistence_with_new_message_updates_session_activity_time() {
        let existing = json!({
            "updated_at": "2026-07-21T00:00:00Z",
            "runtime": {
                "messages": [
                    {"id": "user-1", "role": "user", "content": "检查项目"}
                ]
            }
        });
        let next_runtime = json!({
            "messages": [
                {"id": "user-1", "role": "user", "content": "检查项目"},
                {"id": "assistant-1", "role": "assistant", "content": "检查完成"}
            ]
        });

        assert_eq!(
            runtime_activity_updated_at(Some(&existing), &next_runtime, "2026-07-28T00:00:00Z"),
            "2026-07-28T00:00:00Z"
        );
    }

    #[test]
    fn stale_runtime_write_does_not_drop_completed_answer_or_answer_id() {
        let existing = json!({
            "messages": [
                {"id": "user-1", "role": "user", "content": "检查项目"},
                {
                    "id": "assistant-1",
                    "role": "assistant",
                    "content": "检查完成",
                    "answerId": "ans_assistant-1"
                }
            ]
        });
        let stale = json!({
            "messages": [
                {"id": "user-1", "role": "user", "content": "检查项目"},
                {"id": "assistant-1", "role": "assistant", "content": ""}
            ]
        });

        let merged = merge_runtime_payload(Some(&existing), &stale);
        assert_eq!(merged["messages"][1]["content"], "检查完成");
        assert_eq!(merged["messages"][1]["answerId"], "ans_assistant-1");
    }

    #[test]
    fn stale_runtime_write_keeps_messages_added_by_newer_snapshot() {
        let existing = json!({
            "messages": [
                {"id": "user-1", "role": "user", "content": "第一问"},
                {"id": "assistant-1", "role": "assistant", "content": "第一答"},
                {
                    "id": "assistant-2",
                    "role": "assistant",
                    "content": "第二答",
                    "answerId": "ans_assistant-2"
                }
            ]
        });
        let stale = json!({
            "messages": [
                {"id": "user-1", "role": "user", "content": "第一问"},
                {"id": "assistant-1", "role": "assistant", "content": "第一答"}
            ]
        });

        let merged = merge_runtime_payload(Some(&existing), &stale);
        assert_eq!(merged["messages"].as_array().map(Vec::len), Some(3));
        assert_eq!(merged["messages"][2]["answerId"], "ans_assistant-2");
    }

    #[test]
    fn authoritative_runtime_write_removes_deleted_messages() {
        let existing = json!({
            "messages": [
                {"id": "user-1", "role": "user", "content": "第一问"},
                {"id": "assistant-1", "role": "assistant", "content": "第一答"},
                {"id": "user-2", "role": "user", "content": "第二问"}
            ]
        });
        let replacement = json!({
            "replace_messages": true,
            "messages": [
                {"id": "user-1", "role": "user", "content": "第一问"}
            ]
        });

        let merged = merge_runtime_payload(Some(&existing), &replacement);
        assert_eq!(merged["messages"].as_array().map(Vec::len), Some(1));
        assert_eq!(merged["messages"][0]["id"], "user-1");
        assert!(merged.get("replace_messages").is_none());
    }

    #[test]
    fn stale_runtime_write_cannot_restore_authoritatively_deleted_messages() {
        let existing = json!({
            "messages": [
                {"id": "user-1", "role": "user", "content": "第一问"},
                {"id": "assistant-1", "role": "assistant", "content": "第一答"},
                {"id": "user-2", "role": "user", "content": "第二问"}
            ]
        });
        let deleted = json!({
            "replace_messages": true,
            "deleted_message_ids": ["user-1", "assistant-1", "user-2"],
            "messages": []
        });
        let after_delete = merge_runtime_payload(Some(&existing), &deleted);
        let stale = json!({
            "messages": [
                {"id": "user-1", "role": "user", "content": "旧第一问"},
                {"id": "assistant-1", "role": "assistant", "content": "旧第一答"},
                {"id": "user-2", "role": "user", "content": "旧第二问"}
            ]
        });

        let merged = merge_runtime_payload(Some(&after_delete), &stale);
        assert_eq!(merged["messages"].as_array().map(Vec::len), Some(0));
        assert_eq!(
            merged["deleted_message_ids"].as_array().map(Vec::len),
            Some(3)
        );
    }

    #[test]
    fn non_authoritative_message_delete_preserves_unloaded_messages() {
        let existing = json!({
            "messages": [
                {"id": "user-1", "role": "user", "content": "第一问"},
                {"id": "assistant-1", "role": "assistant", "content": "第一答"},
                {"id": "user-2", "role": "user", "content": "第二问"},
                {"id": "assistant-2", "role": "assistant", "content": "第二答"}
            ]
        });
        let delete_first_round = json!({
            "replace_messages": false,
            "deleted_message_ids": ["user-1", "assistant-1"],
            "messages": [
                {"id": "user-2", "role": "user", "content": "第二问"},
                {"id": "assistant-2", "role": "assistant", "content": "第二答"}
            ]
        });

        let merged = merge_runtime_payload(Some(&existing), &delete_first_round);
        assert_eq!(merged["messages"].as_array().map(Vec::len), Some(2));
        assert_eq!(merged["messages"][0]["id"], "user-2");
        assert_eq!(merged["messages"][1]["id"], "assistant-2");
        assert_eq!(
            merged["deleted_message_ids"].as_array().map(Vec::len),
            Some(2)
        );

        let stale = json!({
            "messages": [
                {"id": "user-1", "role": "user", "content": "旧第一问"},
                {"id": "assistant-1", "role": "assistant", "content": "旧第一答"}
            ]
        });
        let after_stale = merge_runtime_payload(Some(&merged), &stale);
        assert_eq!(after_stale["messages"].as_array().map(Vec::len), Some(2));
        assert_eq!(after_stale["messages"][0]["id"], "user-2");
        assert_eq!(after_stale["messages"][1]["id"], "assistant-2");
    }

    #[test]
    fn supervision_is_derived_directly_from_runtime_messages() {
        let runtime = json!({
            "messages": [
                {"id": "user-1", "role": "user", "content": "检查项目"},
                {
                    "id": "chat-local-1-x4ubpr",
                    "answerId": "ans_chat-local-1-x4ubpr",
                    "role": "assistant",
                    "content": "检查完成",
                    "operations": [
                        {
                            "operationId": "model-1",
                            "kind": "model",
                            "title": "本地模型步骤 1",
                            "status": "completed",
                            "meta": {
                                "model_step_index": 1,
                                "model_name": "gpt-5.6-sol",
                                "provider_id": "lmp-5693bc7e",
                                "provider_name": "OpenAI",
                                "token_usage": {
                                    "input_tokens": 120,
                                    "output_tokens": 30,
                                    "total_tokens": 150,
                                    "source": "provider"
                                }
                            }
                        },
                        {
                            "operationId": "tool-1",
                            "title": "读取文件",
                            "summary": "读取项目文件",
                            "tool_name": "read_file",
                            "status": "completed"
                        }
                    ]
                }
            ]
        });
        let details =
            build_supervision_details("local-session-1", &runtime, "2026-07-21T00:00:00Z")
                .expect("build supervision details");
        assert_eq!(details.len(), 1);
        assert_eq!(details[0]["answer"]["answer_id"], "ans_chat-local-1-x4ubpr");
        assert_eq!(details[0]["answer"]["question_preview"], "检查项目");
        assert!(details[0]["steps"]
            .as_array()
            .is_some_and(|steps| steps.len() >= 3));
        let model_step = details[0]["steps"]
            .as_array()
            .and_then(|steps| steps.iter().find(|step| step["step_type"] == "model_call"))
            .expect("model operation fallback");
        assert_eq!(model_step["model_name"], "gpt-5.6-sol");
        assert_eq!(model_step["provider_id"], "lmp-5693bc7e");
        assert_eq!(model_step["provider_name"], "OpenAI");
        assert_eq!(model_step["model_step_index"], 1);
        assert_eq!(model_step["model_total_tokens"], 150);
    }

    #[test]
    fn supervision_prefers_persisted_execution_cycles() {
        let runtime = json!({
            "messages": [
                {"id": "user-1", "role": "user", "content": "检查项目"},
                {
                    "id": "chat-local-2-x4ubpr",
                    "answerId": "ans_chat-local-2-x4ubpr",
                    "role": "assistant",
                    "content": "检查完成",
                    "agentExecutionCycles": [{
                        "cycleIndex": 2,
                        "contextSnapshot": {
                            "message_count": 4,
                            "estimated_input_tokens": 88,
                            "token_source": "estimate"
                        },
                        "model": {
                            "status": "completed",
                            "modelName": "gpt-5.6-sol",
                            "providerId": "lmp-5693bc7e",
                            "providerName": "OpenAI"
                        },
                        "tools": []
                    }],
                    "operations": [{
                        "operationId": "model-legacy",
                        "kind": "model",
                        "meta": {"model_name": "wrong-fallback-model"}
                    }]
                }
            ]
        });
        let details =
            build_supervision_details("local-session-2", &runtime, "2026-07-21T00:00:00Z")
                .expect("build supervision details");
        let model_steps = details[0]["steps"]
            .as_array()
            .expect("steps")
            .iter()
            .filter(|step| step["step_type"] == "model_call")
            .collect::<Vec<_>>();
        assert_eq!(model_steps.len(), 1);
        assert_eq!(model_steps[0]["model_name"], "gpt-5.6-sol");
        assert_eq!(model_steps[0]["provider_name"], "OpenAI");
        assert_eq!(model_steps[0]["model_step_index"], 2);
        assert_eq!(model_steps[0]["context_message_count"], 4);
    }

    #[test]
    fn path_components_are_stable_and_filesystem_safe() {
        assert_eq!(path_component("admin"), "61646d696e");
        assert_eq!(
            path_component("proj-cc47efb1"),
            "70726f6a2d6363343765666231"
        );
        assert!(!path_component("用户/项目").contains('/'));
    }

    #[test]
    fn legacy_sqlite_runtime_is_migrated_read_only_to_json() {
        let root = temporary_test_directory("project-chat-json-migration");
        let legacy_path = root.join("project-chat.sqlite3");
        let json_directory = root.join("json");
        fs::create_dir_all(&root).expect("create test directory");
        let connection = Connection::open(&legacy_path).expect("create legacy sqlite");
        connection
            .execute_batch(
                "CREATE TABLE project_chat_runtimes (
                   username TEXT NOT NULL,
                   project_id TEXT NOT NULL,
                   chat_session_id TEXT NOT NULL,
                   payload_json TEXT NOT NULL,
                   updated_at TEXT NOT NULL
                 );",
            )
            .expect("create runtime table");
        let runtime = json!({
            "version": 1,
            "updated_at": "2026-07-21T00:00:00Z",
            "messages": [
                {"id": "user-1", "role": "user", "content": "迁移测试"},
                {"id": "assistant-1", "role": "assistant", "content": "迁移完成"}
            ]
        });
        connection
            .execute(
                "INSERT INTO project_chat_runtimes
                 (username, project_id, chat_session_id, payload_json, updated_at)
                 VALUES (?1, ?2, ?3, ?4, ?5)",
                params![
                    "admin",
                    "proj-cc47efb1",
                    "local-runtime-only",
                    serde_json::to_string(&runtime).expect("serialize runtime"),
                    "2026-07-21T00:00:00Z"
                ],
            )
            .expect("insert runtime");
        drop(connection);
        let legacy_before = fs::read(&legacy_path).expect("read legacy before migration");
        fs::create_dir_all(&json_directory).expect("create json directory");
        fs::write(
            json_directory.join(SQLITE_MIGRATION_MARKER),
            b"previous migration completed\n",
        )
        .expect("seed migration marker");

        let migrated = migrate_legacy_sqlite_project_paths(
            &legacy_path,
            &json_directory,
            "admin",
            "proj-cc47efb1",
        )
        .expect("migrate legacy sqlite");

        assert_eq!(migrated, 1);
        let json_path =
            json_directory.join(format!("{}.json", path_component("local-runtime-only")));
        let envelope = read_json_envelope(&json_path).expect("read migrated envelope");
        assert_eq!(envelope["chat_session_id"], "local-runtime-only");
        assert_eq!(envelope["session"]["title"], "迁移测试");
        assert_eq!(
            envelope["runtime"]["messages"].as_array().map(Vec::len),
            Some(2)
        );
        assert_eq!(
            fs::read(&legacy_path).expect("read legacy after migration"),
            legacy_before
        );
        assert!(json_directory.join(SQLITE_MIGRATION_MARKER).exists());
        fs::remove_dir_all(root).expect("remove test directory");
    }
}
