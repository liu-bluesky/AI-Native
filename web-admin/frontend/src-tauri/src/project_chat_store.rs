use rusqlite::{params, Connection, OptionalExtension, Transaction};
use serde_json::{json, Value};
use std::fs;
use std::path::PathBuf;
use tauri::Manager;

fn normalized(value: &str, field: &str) -> Result<String, String> {
    let value = value.trim();
    if value.is_empty() {
        return Err(format!("缺少{field}"));
    }
    Ok(value.to_string())
}

fn database_path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let app_data_dir = app.path().app_data_dir().map_err(|err| err.to_string())?;
    fs::create_dir_all(&app_data_dir).map_err(|err| err.to_string())?;
    Ok(app_data_dir.join("project-chat.sqlite3"))
}

fn open_database(app: &tauri::AppHandle) -> Result<Connection, String> {
    let connection = Connection::open(database_path(app)?).map_err(|err| err.to_string())?;
    initialize_database(&connection)?;
    Ok(connection)
}

fn initialize_database(connection: &Connection) -> Result<(), String> {
    connection
        .execute_batch(
            "PRAGMA journal_mode = WAL;
             PRAGMA busy_timeout = 5000;
             PRAGMA foreign_keys = ON;
             CREATE TABLE IF NOT EXISTS project_chat_sessions (
               username TEXT NOT NULL,
               project_id TEXT NOT NULL,
               chat_session_id TEXT NOT NULL,
               payload_json TEXT NOT NULL,
               updated_at TEXT NOT NULL,
               PRIMARY KEY (username, project_id, chat_session_id)
             );
             CREATE INDEX IF NOT EXISTS idx_project_chat_sessions_updated
               ON project_chat_sessions(username, project_id, updated_at DESC);
             CREATE TABLE IF NOT EXISTS project_chat_runtimes (
               username TEXT NOT NULL,
               project_id TEXT NOT NULL,
               chat_session_id TEXT NOT NULL,
               payload_json TEXT NOT NULL,
               updated_at TEXT NOT NULL,
               PRIMARY KEY (username, project_id, chat_session_id)
             );
             CREATE TABLE IF NOT EXISTS agent_supervision_answers (
               username TEXT NOT NULL,
               project_id TEXT NOT NULL,
               chat_session_id TEXT NOT NULL,
               assistant_message_id TEXT NOT NULL,
               answer_id TEXT NOT NULL,
               user_message_id TEXT NOT NULL DEFAULT '',
               question_preview TEXT NOT NULL DEFAULT '',
               answer_preview TEXT NOT NULL DEFAULT '',
               status TEXT NOT NULL DEFAULT 'completed',
               started_at_epoch_ms INTEGER NOT NULL DEFAULT 0,
               ended_at_epoch_ms INTEGER NOT NULL DEFAULT 0,
               duration_ms INTEGER NOT NULL DEFAULT 0,
               updated_at TEXT NOT NULL DEFAULT '',
               PRIMARY KEY (username, project_id, assistant_message_id)
             );
             CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_supervision_answer_id
               ON agent_supervision_answers(username, project_id, answer_id);
             CREATE INDEX IF NOT EXISTS idx_agent_supervision_answer_session
               ON agent_supervision_answers(username, project_id, chat_session_id, updated_at DESC);
             CREATE TABLE IF NOT EXISTS agent_supervision_runs (
               username TEXT NOT NULL,
               project_id TEXT NOT NULL,
               run_id TEXT NOT NULL,
               assistant_message_id TEXT NOT NULL,
               answer_id TEXT NOT NULL,
               request_id TEXT NOT NULL DEFAULT '',
               status TEXT NOT NULL DEFAULT 'completed',
               model_round_count INTEGER NOT NULL DEFAULT 0,
               tool_call_count INTEGER NOT NULL DEFAULT 0,
               started_at_epoch_ms INTEGER NOT NULL DEFAULT 0,
               ended_at_epoch_ms INTEGER NOT NULL DEFAULT 0,
               duration_ms INTEGER NOT NULL DEFAULT 0,
               updated_at TEXT NOT NULL DEFAULT '',
               PRIMARY KEY (username, project_id, run_id),
               FOREIGN KEY (username, project_id, assistant_message_id)
                 REFERENCES agent_supervision_answers(username, project_id, assistant_message_id)
                 ON DELETE CASCADE
             );
             CREATE INDEX IF NOT EXISTS idx_agent_supervision_run_answer
               ON agent_supervision_runs(username, project_id, assistant_message_id, updated_at DESC);
             CREATE TABLE IF NOT EXISTS agent_supervision_steps (
               username TEXT NOT NULL,
               project_id TEXT NOT NULL,
               step_id TEXT NOT NULL,
               run_id TEXT NOT NULL,
               parent_step_id TEXT NOT NULL DEFAULT '',
               sort_order INTEGER NOT NULL DEFAULT 0,
               step_type TEXT NOT NULL DEFAULT 'observation',
               status TEXT NOT NULL DEFAULT 'completed',
               title TEXT NOT NULL DEFAULT '',
               summary TEXT NOT NULL DEFAULT '',
               detail_preview TEXT NOT NULL DEFAULT '',
               tool_name TEXT NOT NULL DEFAULT '',
               call_id TEXT NOT NULL DEFAULT '',
               started_at_epoch_ms INTEGER NOT NULL DEFAULT 0,
               ended_at_epoch_ms INTEGER NOT NULL DEFAULT 0,
               duration_ms INTEGER NOT NULL DEFAULT 0,
               PRIMARY KEY (username, project_id, step_id),
               FOREIGN KEY (username, project_id, run_id)
                 REFERENCES agent_supervision_runs(username, project_id, run_id)
                 ON DELETE CASCADE
             );
             CREATE INDEX IF NOT EXISTS idx_agent_supervision_step_run
               ON agent_supervision_steps(username, project_id, run_id, sort_order);
             CREATE TABLE IF NOT EXISTS agent_supervision_edges (
               username TEXT NOT NULL,
               project_id TEXT NOT NULL,
               edge_id TEXT NOT NULL,
               run_id TEXT NOT NULL,
               source_step_id TEXT NOT NULL,
               target_step_id TEXT NOT NULL,
               edge_type TEXT NOT NULL DEFAULT 'sequence',
               label TEXT NOT NULL DEFAULT '',
               sort_order INTEGER NOT NULL DEFAULT 0,
               PRIMARY KEY (username, project_id, edge_id),
               FOREIGN KEY (username, project_id, run_id)
                 REFERENCES agent_supervision_runs(username, project_id, run_id)
                 ON DELETE CASCADE
             );",
        )
        .map_err(|err| err.to_string())?;
    Ok(())
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
    started_at_epoch_ms: i64,
    ended_at_epoch_ms: i64,
    duration_ms: i64,
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
        started_at_epoch_ms: started_at,
        ended_at_epoch_ms: started_at,
        duration_ms: 0,
    }];

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
            steps.push(SupervisionStep {
                step_id: format!("step:{assistant_message_id}:log:{fragment}"),
                step_type: supervision_step_type(item, "observation"),
                status: process_step_status(item),
                title: clipped(&text, 160),
                summary: clipped(&text, 320),
                detail_preview: clipped(&text, 2000),
                tool_name,
                call_id,
                started_at_epoch_ms: 0,
                ended_at_epoch_ms: 0,
                duration_ms: 0,
            });
        }
    }

    if let Some(operations) = message.get("operations").and_then(Value::as_array) {
        for (index, item) in operations.iter().enumerate() {
            let raw_id = value_text(item, &["operationId", "operation_id", "id"]);
            let fragment = stable_fragment(&raw_id, &format!("{index}"));
            let title = value_text(item, &["title"]);
            let summary = value_text(item, &["summary"]);
            let detail = value_text(item, &["detail"]);
            let tool_name = find_nested_text(item, &["tool_name", "toolName"]);
            let call_id =
                find_nested_text(item, &["call_id", "callId", "tool_call_id", "toolCallId"]);
            steps.push(SupervisionStep {
                step_id: format!("step:{assistant_message_id}:operation:{fragment}"),
                step_type: supervision_step_type(item, "operation"),
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
            started_at_epoch_ms: ended_at,
            ended_at_epoch_ms: ended_at,
            duration_ms,
        });
    }
    steps
}

fn write_supervision_projection(
    transaction: &Transaction<'_>,
    username: &str,
    project_id: &str,
    chat_session_id: &str,
    payload: &Value,
    updated_at: &str,
) -> Result<(), String> {
    transaction
        .execute(
            "DELETE FROM agent_supervision_answers
             WHERE username = ?1 AND project_id = ?2 AND chat_session_id = ?3",
            params![username, project_id, chat_session_id],
        )
        .map_err(|err| err.to_string())?;

    let messages = payload
        .get("messages")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut previous_user_id = String::new();
    let mut previous_user_content = String::new();
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
        transaction
            .execute(
                "INSERT INTO agent_supervision_answers
                 (username, project_id, chat_session_id, assistant_message_id, answer_id,
                  user_message_id, question_preview, answer_preview, status,
                  started_at_epoch_ms, ended_at_epoch_ms, duration_ms, updated_at)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13)",
                params![
                    username,
                    project_id,
                    chat_session_id,
                    message_id,
                    answer_id,
                    previous_user_id,
                    clipped(&previous_user_content, 1200),
                    clipped(&content, 4000),
                    status,
                    started_at,
                    ended_at,
                    duration_ms,
                    updated_at
                ],
            )
            .map_err(|err| err.to_string())?;

        let nested_run_id = find_nested_text(&message, &["run_id", "runId"]);
        let run_id = if nested_run_id.is_empty() {
            format!("run:{message_id}")
        } else {
            nested_run_id
        };
        let request_id = find_nested_text(&message, &["request_id", "requestId"]);
        let steps =
            collect_supervision_steps(&message, &message_id, &previous_user_content, &status);
        let model_round_count = steps
            .iter()
            .filter(|step| step.step_type == "model_call")
            .count() as i64;
        let tool_call_count = steps
            .iter()
            .filter(|step| step.step_type == "tool_call")
            .count() as i64;
        transaction
            .execute(
                "INSERT INTO agent_supervision_runs
                 (username, project_id, run_id, assistant_message_id, answer_id, request_id,
                  status, model_round_count, tool_call_count, started_at_epoch_ms,
                  ended_at_epoch_ms, duration_ms, updated_at)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13)",
                params![
                    username,
                    project_id,
                    run_id,
                    message_id,
                    answer_id,
                    request_id,
                    status,
                    model_round_count,
                    tool_call_count,
                    started_at,
                    ended_at,
                    duration_ms,
                    updated_at
                ],
            )
            .map_err(|err| err.to_string())?;

        let mut previous_step_id = String::new();
        for (index, step) in steps.iter().enumerate() {
            transaction
                .execute(
                    "INSERT INTO agent_supervision_steps
                     (username, project_id, step_id, run_id, parent_step_id, sort_order,
                      step_type, status, title, summary, detail_preview, tool_name, call_id,
                      started_at_epoch_ms, ended_at_epoch_ms, duration_ms)
                     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16)",
                    params![
                        username,
                        project_id,
                        step.step_id,
                        run_id,
                        previous_step_id,
                        index as i64,
                        step.step_type,
                        step.status,
                        step.title,
                        step.summary,
                        step.detail_preview,
                        step.tool_name,
                        step.call_id,
                        step.started_at_epoch_ms,
                        step.ended_at_epoch_ms,
                        step.duration_ms
                    ],
                )
                .map_err(|err| err.to_string())?;
            if !previous_step_id.is_empty() {
                let edge_id = format!("edge:{message_id}:{index}");
                transaction
                    .execute(
                        "INSERT INTO agent_supervision_edges
                         (username, project_id, edge_id, run_id, source_step_id,
                          target_step_id, edge_type, label, sort_order)
                         VALUES (?1, ?2, ?3, ?4, ?5, ?6, 'sequence', '', ?7)",
                        params![
                            username,
                            project_id,
                            edge_id,
                            run_id,
                            previous_step_id,
                            step.step_id,
                            index as i64
                        ],
                    )
                    .map_err(|err| err.to_string())?;
            }
            previous_step_id = step.step_id.clone();
        }
    }
    Ok(())
}

fn projectable_supervision_answer_count(payload: &Value) -> usize {
    payload
        .get("messages")
        .and_then(Value::as_array)
        .map(|messages| {
            messages
                .iter()
                .filter(|message| {
                    let role = value_text(message, &["role"]).to_lowercase();
                    let message_id = value_text(message, &["id"]);
                    if role == "user" || message_id.is_empty() {
                        return false;
                    }
                    let has_content = !value_text(message, &["content"]).is_empty();
                    let has_steps = message
                        .get("processLog")
                        .and_then(Value::as_array)
                        .is_some_and(|items| !items.is_empty())
                        || message
                            .get("operations")
                            .and_then(Value::as_array)
                            .is_some_and(|items| !items.is_empty());
                    has_content || has_steps
                })
                .count()
        })
        .unwrap_or_default()
}

fn repair_supervision_projection_for_project(
    connection: &mut Connection,
    username: &str,
    project_id: &str,
) -> Result<usize, String> {
    let runtime_rows = {
        let mut statement = connection
            .prepare(
                "SELECT chat_session_id, payload_json, updated_at
                 FROM project_chat_runtimes
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
        let mut result = Vec::new();
        for row in rows {
            result.push(row.map_err(|err| err.to_string())?);
        }
        result
    };

    let mut repaired = 0;
    for (chat_session_id, payload_json, updated_at) in runtime_rows {
        let payload: Value = serde_json::from_str(&payload_json).map_err(|err| err.to_string())?;
        let expected_answers = projectable_supervision_answer_count(&payload) as i64;
        if expected_answers <= 0 {
            continue;
        }
        let projected_answers = connection
            .query_row(
                "SELECT COUNT(*)
                 FROM agent_supervision_answers
                 WHERE username = ?1 AND project_id = ?2 AND chat_session_id = ?3
                   AND updated_at = ?4",
                params![username, project_id, chat_session_id, updated_at],
                |row| row.get::<_, i64>(0),
            )
            .map_err(|err| err.to_string())?;
        let incomplete_answers = connection
            .query_row(
                "SELECT COUNT(DISTINCT answers.assistant_message_id)
                 FROM agent_supervision_answers AS answers
                 LEFT JOIN agent_supervision_runs AS runs
                   ON runs.username = answers.username
                  AND runs.project_id = answers.project_id
                  AND runs.assistant_message_id = answers.assistant_message_id
                 LEFT JOIN agent_supervision_steps AS steps
                   ON steps.username = runs.username
                  AND steps.project_id = runs.project_id
                  AND steps.run_id = runs.run_id
                 WHERE answers.username = ?1
                   AND answers.project_id = ?2
                   AND answers.chat_session_id = ?3
                   AND (runs.run_id IS NULL OR steps.step_id IS NULL)",
                params![username, project_id, chat_session_id],
                |row| row.get::<_, i64>(0),
            )
            .map_err(|err| err.to_string())?;
        if projected_answers == expected_answers && incomplete_answers == 0 {
            continue;
        }
        let transaction = connection.transaction().map_err(|err| err.to_string())?;
        write_supervision_projection(
            &transaction,
            username,
            project_id,
            &chat_session_id,
            &payload,
            &updated_at,
        )?;
        transaction.commit().map_err(|err| err.to_string())?;
        repaired += 1;
    }
    Ok(repaired)
}

#[tauri::command]
pub fn project_chat_list_sessions(
    app: tauri::AppHandle,
    username: String,
    project_id: String,
) -> Result<Vec<Value>, String> {
    let username = normalized(&username, "用户名")?;
    let project_id = normalized(&project_id, "项目 ID")?;
    let mut connection = open_database(&app)?;
    repair_supervision_projection_for_project(&mut connection, &username, &project_id)?;
    let mut statement = connection
        .prepare(
            "SELECT payload_json
             FROM project_chat_sessions
             WHERE username = ?1 AND project_id = ?2
             ORDER BY updated_at DESC",
        )
        .map_err(|err| err.to_string())?;
    let rows = statement
        .query_map(params![username, project_id], |row| row.get::<_, String>(0))
        .map_err(|err| err.to_string())?;
    let mut sessions = Vec::new();
    for row in rows {
        let raw = row.map_err(|err| err.to_string())?;
        sessions.push(serde_json::from_str(&raw).map_err(|err| err.to_string())?);
    }
    Ok(sessions)
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
    let mut connection = open_database(&app)?;
    let transaction = connection.transaction().map_err(|err| err.to_string())?;
    transaction
        .execute(
            "DELETE FROM project_chat_sessions WHERE username = ?1 AND project_id = ?2",
            params![username, project_id],
        )
        .map_err(|err| err.to_string())?;
    for session in &sessions {
        let session_id = normalized(
            session
                .get("id")
                .and_then(Value::as_str)
                .unwrap_or_default(),
            "聊天会话 ID",
        )?;
        let updated_at = session
            .get("updated_at")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .trim()
            .to_string();
        let payload_json = serde_json::to_string(session).map_err(|err| err.to_string())?;
        transaction
            .execute(
                "INSERT INTO project_chat_sessions
                 (username, project_id, chat_session_id, payload_json, updated_at)
                 VALUES (?1, ?2, ?3, ?4, ?5)",
                params![username, project_id, session_id, payload_json, updated_at],
            )
            .map_err(|err| err.to_string())?;
    }
    transaction.commit().map_err(|err| err.to_string())?;
    Ok(sessions.len())
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
    let connection = open_database(&app)?;
    let raw = connection
        .query_row(
            "SELECT payload_json FROM project_chat_runtimes
             WHERE username = ?1 AND project_id = ?2 AND chat_session_id = ?3",
            params![username, project_id, chat_session_id],
            |row| row.get::<_, String>(0),
        )
        .optional()
        .map_err(|err| err.to_string())?;
    raw.map(|value| serde_json::from_str(&value).map_err(|err| err.to_string()))
        .transpose()
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
    let updated_at = payload
        .get("updated_at")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .trim()
        .to_string();
    let payload_json = serde_json::to_string(&payload).map_err(|err| err.to_string())?;
    let mut connection = open_database(&app)?;
    let transaction = connection.transaction().map_err(|err| err.to_string())?;
    transaction
        .execute(
            "INSERT INTO project_chat_runtimes
             (username, project_id, chat_session_id, payload_json, updated_at)
             VALUES (?1, ?2, ?3, ?4, ?5)
             ON CONFLICT(username, project_id, chat_session_id) DO UPDATE SET
               payload_json = excluded.payload_json,
               updated_at = excluded.updated_at",
            params![
                username,
                project_id,
                chat_session_id,
                payload_json,
                updated_at
            ],
        )
        .map_err(|err| err.to_string())?;
    write_supervision_projection(
        &transaction,
        &username,
        &project_id,
        &chat_session_id,
        &payload,
        &updated_at,
    )?;
    transaction.commit().map_err(|err| err.to_string())?;
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
    let query = query.trim().to_string();
    let search_pattern = format!("%{query}%");
    let limit = limit.unwrap_or(50).clamp(1, 200) as i64;
    let connection = open_database(&app)?;
    let mut statement = connection
        .prepare(
            "SELECT assistant_message_id, answer_id, chat_session_id, user_message_id,
                    question_preview, answer_preview, status, started_at_epoch_ms,
                    ended_at_epoch_ms, duration_ms, updated_at
             FROM agent_supervision_answers
             WHERE username = ?1 AND project_id = ?2
               AND (?3 = '' OR answer_id LIKE ?4 OR assistant_message_id LIKE ?4
                    OR question_preview LIKE ?4 OR answer_preview LIKE ?4)
             ORDER BY updated_at DESC, started_at_epoch_ms DESC
             LIMIT ?5",
        )
        .map_err(|err| err.to_string())?;
    let rows = statement
        .query_map(
            params![username, project_id, query, search_pattern, limit],
            |row| {
                Ok(json!({
                    "assistant_message_id": row.get::<_, String>(0)?,
                    "answer_id": row.get::<_, String>(1)?,
                    "chat_session_id": row.get::<_, String>(2)?,
                    "user_message_id": row.get::<_, String>(3)?,
                    "question_preview": row.get::<_, String>(4)?,
                    "answer_preview": row.get::<_, String>(5)?,
                    "status": row.get::<_, String>(6)?,
                    "started_at_epoch_ms": row.get::<_, i64>(7)?,
                    "ended_at_epoch_ms": row.get::<_, i64>(8)?,
                    "duration_ms": row.get::<_, i64>(9)?,
                    "updated_at": row.get::<_, String>(10)?,
                }))
            },
        )
        .map_err(|err| err.to_string())?;
    let mut answers = Vec::new();
    for row in rows {
        answers.push(row.map_err(|err| err.to_string())?);
    }
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
    let mut connection = open_database(&app)?;
    repair_supervision_projection_for_project(&mut connection, &username, &project_id)?;
    let answer = connection
        .query_row(
            "SELECT assistant_message_id, answer_id, chat_session_id, user_message_id,
                    question_preview, answer_preview, status, started_at_epoch_ms,
                    ended_at_epoch_ms, duration_ms, updated_at
             FROM agent_supervision_answers
             WHERE username = ?1 AND project_id = ?2
               AND (answer_id = ?3 OR assistant_message_id = ?3
                    OR answer_id = ?4 OR assistant_message_id = ?4)
             LIMIT 1",
            params![username, project_id, answer_id, alternate_answer_id],
            |row| {
                Ok(json!({
                    "assistant_message_id": row.get::<_, String>(0)?,
                    "answer_id": row.get::<_, String>(1)?,
                    "chat_session_id": row.get::<_, String>(2)?,
                    "user_message_id": row.get::<_, String>(3)?,
                    "question_preview": row.get::<_, String>(4)?,
                    "answer_preview": row.get::<_, String>(5)?,
                    "status": row.get::<_, String>(6)?,
                    "started_at_epoch_ms": row.get::<_, i64>(7)?,
                    "ended_at_epoch_ms": row.get::<_, i64>(8)?,
                    "duration_ms": row.get::<_, i64>(9)?,
                    "updated_at": row.get::<_, String>(10)?,
                }))
            },
        )
        .optional()
        .map_err(|err| err.to_string())?;
    let Some(answer) = answer else {
        return Ok(None);
    };
    let assistant_message_id = answer
        .get("assistant_message_id")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();
    let run = connection
        .query_row(
            "SELECT run_id, request_id, status, model_round_count, tool_call_count,
                    started_at_epoch_ms, ended_at_epoch_ms, duration_ms, updated_at
             FROM agent_supervision_runs
             WHERE username = ?1 AND project_id = ?2 AND assistant_message_id = ?3
             ORDER BY updated_at DESC
             LIMIT 1",
            params![username, project_id, assistant_message_id],
            |row| {
                Ok(json!({
                    "run_id": row.get::<_, String>(0)?,
                    "request_id": row.get::<_, String>(1)?,
                    "status": row.get::<_, String>(2)?,
                    "model_round_count": row.get::<_, i64>(3)?,
                    "tool_call_count": row.get::<_, i64>(4)?,
                    "started_at_epoch_ms": row.get::<_, i64>(5)?,
                    "ended_at_epoch_ms": row.get::<_, i64>(6)?,
                    "duration_ms": row.get::<_, i64>(7)?,
                    "updated_at": row.get::<_, String>(8)?,
                }))
            },
        )
        .optional()
        .map_err(|err| err.to_string())?;
    let Some(run) = run else {
        return Ok(Some(json!({
            "answer": answer,
            "run": null,
            "steps": [],
            "edges": [],
        })));
    };
    let run_id = run
        .get("run_id")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();
    let mut step_statement = connection
        .prepare(
            "SELECT step_id, parent_step_id, sort_order, step_type, status, title,
                    summary, detail_preview, tool_name, call_id, started_at_epoch_ms,
                    ended_at_epoch_ms, duration_ms
             FROM agent_supervision_steps
             WHERE username = ?1 AND project_id = ?2 AND run_id = ?3
             ORDER BY sort_order ASC",
        )
        .map_err(|err| err.to_string())?;
    let step_rows = step_statement
        .query_map(params![username, project_id, run_id], |row| {
            Ok(json!({
                "step_id": row.get::<_, String>(0)?,
                "parent_step_id": row.get::<_, String>(1)?,
                "sort_order": row.get::<_, i64>(2)?,
                "step_type": row.get::<_, String>(3)?,
                "status": row.get::<_, String>(4)?,
                "title": row.get::<_, String>(5)?,
                "summary": row.get::<_, String>(6)?,
                "detail_preview": row.get::<_, String>(7)?,
                "tool_name": row.get::<_, String>(8)?,
                "call_id": row.get::<_, String>(9)?,
                "started_at_epoch_ms": row.get::<_, i64>(10)?,
                "ended_at_epoch_ms": row.get::<_, i64>(11)?,
                "duration_ms": row.get::<_, i64>(12)?,
            }))
        })
        .map_err(|err| err.to_string())?;
    let mut steps = Vec::new();
    for row in step_rows {
        steps.push(row.map_err(|err| err.to_string())?);
    }
    let mut edge_statement = connection
        .prepare(
            "SELECT edge_id, source_step_id, target_step_id, edge_type, label, sort_order
             FROM agent_supervision_edges
             WHERE username = ?1 AND project_id = ?2 AND run_id = ?3
             ORDER BY sort_order ASC",
        )
        .map_err(|err| err.to_string())?;
    let edge_rows = edge_statement
        .query_map(params![username, project_id, run_id], |row| {
            Ok(json!({
                "edge_id": row.get::<_, String>(0)?,
                "source_step_id": row.get::<_, String>(1)?,
                "target_step_id": row.get::<_, String>(2)?,
                "edge_type": row.get::<_, String>(3)?,
                "label": row.get::<_, String>(4)?,
                "sort_order": row.get::<_, i64>(5)?,
            }))
        })
        .map_err(|err| err.to_string())?;
    let mut edges = Vec::new();
    for row in edge_rows {
        edges.push(row.map_err(|err| err.to_string())?);
    }
    Ok(Some(json!({
        "answer": answer,
        "run": run,
        "steps": steps,
        "edges": edges,
    })))
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
    let mut connection = open_database(&app)?;
    let transaction = connection.transaction().map_err(|err| err.to_string())?;
    transaction
        .execute(
            "DELETE FROM agent_supervision_answers
             WHERE username = ?1 AND project_id = ?2 AND chat_session_id = ?3",
            params![username, project_id, chat_session_id],
        )
        .map_err(|err| err.to_string())?;
    transaction
        .execute(
            "DELETE FROM project_chat_sessions
             WHERE username = ?1 AND project_id = ?2 AND chat_session_id = ?3",
            params![username, project_id, chat_session_id],
        )
        .map_err(|err| err.to_string())?;
    transaction
        .execute(
            "DELETE FROM project_chat_runtimes
             WHERE username = ?1 AND project_id = ?2 AND chat_session_id = ?3",
            params![username, project_id, chat_session_id],
        )
        .map_err(|err| err.to_string())?;
    transaction.commit().map_err(|err| err.to_string())?;
    Ok(true)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sqlite_schema_stores_session_and_runtime_payloads() {
        let connection = Connection::open_in_memory().expect("open in-memory sqlite");
        initialize_database(&connection).expect("initialize project chat schema");
        connection
            .execute(
                "INSERT INTO project_chat_sessions
                 (username, project_id, chat_session_id, payload_json, updated_at)
                 VALUES (?1, ?2, ?3, ?4, ?5)",
                params!["admin", "project-1", "chat-1", r#"{"id":"chat-1"}"#, "1"],
            )
            .expect("insert session");
        connection
            .execute(
                "INSERT INTO project_chat_runtimes
                 (username, project_id, chat_session_id, payload_json, updated_at)
                 VALUES (?1, ?2, ?3, ?4, ?5)",
                params![
                    "admin",
                    "project-1",
                    "chat-1",
                    r#"{"messages":[{"role":"user","content":"hello"}]}"#,
                    "1"
                ],
            )
            .expect("insert runtime");
        let runtime: String = connection
            .query_row(
                "SELECT payload_json FROM project_chat_runtimes
                 WHERE username = ?1 AND project_id = ?2 AND chat_session_id = ?3",
                params!["admin", "project-1", "chat-1"],
                |row| row.get(0),
            )
            .expect("read runtime");
        assert!(runtime.contains("hello"));
    }

    #[test]
    fn runtime_snapshot_projects_searchable_supervision_graph() {
        let mut connection = Connection::open_in_memory().expect("open in-memory sqlite");
        initialize_database(&connection).expect("initialize project chat schema");
        let payload = json!({
            "updated_at": "2026-07-17T00:00:00Z",
            "messages": [
                {
                    "id": "user-1",
                    "role": "user",
                    "content": "检查构建状态"
                },
                {
                    "id": "assistant-1",
                    "role": "assistant",
                    "answerId": "ans_assistant-1",
                    "content": "构建已经通过。",
                    "agentRuntimeStartedAtEpochMs": 100,
                    "agentRuntimeEndedAtEpochMs": 400,
                    "agentRuntimeDurationMs": 300,
                    "processLog": [
                        {
                            "id": "log-model",
                            "text": "模型开始处理",
                            "eventType": "model_call_started"
                        },
                        {
                            "id": "log-tool",
                            "text": "执行 npm run build",
                            "kind": "command",
                            "payload": {
                                "tool_name": "run_command",
                                "tool_call_id": "call-1"
                            }
                        }
                    ],
                    "operations": [
                        {
                            "operationId": "request:req-1",
                            "kind": "request",
                            "title": "执行构建",
                            "phase": "completed",
                            "meta": {
                                "request_id": "req-1",
                                "run_id": "run-1"
                            }
                        }
                    ]
                }
            ]
        });
        let transaction = connection.transaction().expect("start transaction");
        write_supervision_projection(
            &transaction,
            "admin",
            "project-1",
            "chat-1",
            &payload,
            "2026-07-17T00:00:00Z",
        )
        .expect("project supervision snapshot");
        transaction.commit().expect("commit projection");

        let answer_id: String = connection
            .query_row(
                "SELECT answer_id FROM agent_supervision_answers
                 WHERE username = 'admin' AND project_id = 'project-1'",
                [],
                |row| row.get(0),
            )
            .expect("read answer id");
        let step_count: i64 = connection
            .query_row(
                "SELECT COUNT(*) FROM agent_supervision_steps
                 WHERE username = 'admin' AND project_id = 'project-1'",
                [],
                |row| row.get(0),
            )
            .expect("count steps");
        let edge_count: i64 = connection
            .query_row(
                "SELECT COUNT(*) FROM agent_supervision_edges
                 WHERE username = 'admin' AND project_id = 'project-1'",
                [],
                |row| row.get(0),
            )
            .expect("count edges");
        assert_eq!(answer_id, "ans_assistant-1");
        assert!(step_count >= 4);
        assert_eq!(edge_count, step_count - 1);
    }

    #[test]
    fn supervision_query_rebuilds_missing_runtime_projection() {
        let mut connection = Connection::open_in_memory().expect("open in-memory sqlite");
        initialize_database(&connection).expect("initialize project chat schema");
        let payload = json!({
            "updated_at": "2026-07-17T01:00:00Z",
            "messages": [
                {
                    "id": "user-repair",
                    "role": "user",
                    "content": "为什么执行链路是空的"
                },
                {
                    "id": "assistant-repair",
                    "role": "assistant",
                    "answerId": "ans_assistant-repair",
                    "content": "已经从运行快照重建。",
                    "processLog": [
                        {
                            "id": "repair-model",
                            "text": "模型调用",
                            "eventType": "model_call"
                        }
                    ],
                    "operations": [
                        {
                            "operationId": "repair-tool",
                            "kind": "tool_call",
                            "title": "读取运行快照",
                            "summary": "从 SQLite 重建投影",
                            "phase": "completed",
                            "payload": {
                                "tool_name": "sqlite"
                            }
                        }
                    ]
                }
            ]
        });
        connection
            .execute(
                "INSERT INTO project_chat_runtimes
                 (username, project_id, chat_session_id, payload_json, updated_at)
                 VALUES (?1, ?2, ?3, ?4, ?5)",
                params![
                    "admin",
                    "project-repair",
                    "chat-repair",
                    serde_json::to_string(&payload).expect("serialize runtime payload"),
                    "2026-07-17T01:00:00Z"
                ],
            )
            .expect("insert runtime without supervision projection");

        let repaired =
            repair_supervision_projection_for_project(&mut connection, "admin", "project-repair")
                .expect("repair supervision projection");
        assert_eq!(repaired, 1);

        let step_count: i64 = connection
            .query_row(
                "SELECT COUNT(*) FROM agent_supervision_steps
                 WHERE username = 'admin' AND project_id = 'project-repair'",
                [],
                |row| row.get(0),
            )
            .expect("count repaired steps");
        assert!(step_count >= 4);

        connection
            .execute(
                "DELETE FROM agent_supervision_steps
                 WHERE username = 'admin' AND project_id = 'project-repair'",
                [],
            )
            .expect("simulate incomplete projection");
        let repaired_incomplete =
            repair_supervision_projection_for_project(&mut connection, "admin", "project-repair")
                .expect("repair incomplete supervision projection");
        assert_eq!(repaired_incomplete, 1);
    }
}
