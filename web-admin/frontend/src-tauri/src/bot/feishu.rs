use base64::{engine::general_purpose, Engine as _};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::{HashMap, HashSet};
use std::env;
use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex, OnceLock};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Emitter, Manager};

use crate::bot::types::{BotChatRequest, BotConnectorConfig, BotSourceContext};
use crate::liuagent_core::{
    execute_tool, LocalBackendContext, LocalChatMessage, LocalChatResult, LocalModelRuntimeConfig,
    PermissionDecisionInput, ToolExecutionRequest,
};

const FEISHU_SDK_WORKER_RELATIVE_PATH: &str = "bot_workers/feishu_sdk_listener.py";
const FEISHU_PYTHON_ENV: &str = "AI_EMPLOYEE_FEISHU_PYTHON";
const DESKTOP_BOT_GLOBAL_PROJECT_ID: &str = "desktop-bot-global";

static FEISHU_LISTENERS: OnceLock<Mutex<HashMap<String, FeishuListenerProcess>>> = OnceLock::new();
static FEISHU_PROCESSING_EVENTS: OnceLock<Mutex<HashSet<String>>> = OnceLock::new();

fn listener_store() -> &'static Mutex<HashMap<String, FeishuListenerProcess>> {
    FEISHU_LISTENERS.get_or_init(|| Mutex::new(HashMap::new()))
}

fn processing_events() -> &'static Mutex<HashSet<String>> {
    FEISHU_PROCESSING_EVENTS.get_or_init(|| Mutex::new(HashSet::new()))
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FeishuLocalListenerStartRequest {
    pub connector_id: String,
    #[serde(default)]
    pub workspace_path: String,
    #[serde(default)]
    pub owner_username: String,
    #[serde(default)]
    pub model_runtime: Option<LocalModelRuntimeConfig>,
    #[serde(default)]
    pub mcp_config: Value,
    #[serde(default)]
    pub backend_context: Option<LocalBackendContext>,
    #[serde(default)]
    pub permission_decision: Option<PermissionDecisionInput>,
}

#[derive(Debug, Deserialize, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
struct StoredFeishuListenerContext {
    connector_id: String,
    workspace_path: String,
    owner_username: String,
    #[serde(default)]
    model_runtime: Option<LocalModelRuntimeConfig>,
    #[serde(default)]
    mcp_config: Value,
    #[serde(default)]
    backend_context: Option<LocalBackendContext>,
}

#[derive(Debug, Deserialize, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
struct StoredBotConversation {
    version: u32,
    connector_id: String,
    chat_session_id: String,
    updated_at_epoch_ms: u128,
    #[serde(default)]
    messages: Vec<LocalChatMessage>,
}

#[derive(Debug, Deserialize, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
struct StoredBotProjectBinding {
    version: u32,
    connector_id: String,
    chat_session_id: String,
    project_id: String,
    project_name: String,
    workspace_path: String,
    updated_at_epoch_ms: u128,
}

#[derive(Debug, Deserialize, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
struct StoredBotPendingApproval {
    version: u32,
    connector_id: String,
    chat_session_id: String,
    request_id: String,
    project_id: String,
    workspace_path: String,
    user_message: String,
    external_chat_id: String,
    external_sender_id: String,
    external_message_id: String,
    thread_id: String,
    approval_message_id: String,
    #[serde(default)]
    approval_payload: Value,
    #[serde(default)]
    original_event: Value,
    #[serde(default)]
    history: Vec<LocalChatMessage>,
    status: String,
    updated_at_epoch_ms: u128,
}

#[derive(Debug, Deserialize, Serialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
struct StoredBotFullAccessGrant {
    version: u32,
    connector_id: String,
    chat_session_id: String,
    grant_scope: String,
    source_request_id: String,
    updated_at_epoch_ms: u128,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FeishuLocalReplyRequest {
    #[serde(default)]
    pub connector_id: String,
    pub message_id: String,
    pub content: String,
    #[serde(default)]
    pub content_format: String,
    #[serde(default)]
    pub reply_identity: String,
    #[serde(default)]
    pub reply_in_thread: bool,
    #[serde(default)]
    pub idempotency_key: String,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct FeishuLocalListenerStatus {
    pub connector_id: String,
    pub running: bool,
    pub project_id: String,
    pub chat_session_id: String,
    pub workspace_path: String,
    pub started_at_epoch_ms: u128,
    pub reason: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct FeishuLocalReplyResult {
    pub ok: bool,
    pub stdout: String,
    pub stderr: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FeishuChatScanRequest {
    #[serde(default)]
    pub identity: String,
    #[serde(default)]
    pub page_size: u16,
    #[serde(default)]
    pub page_limit: u16,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct FeishuChatScanResult {
    pub status: String,
    pub identity: String,
    pub count: usize,
    pub items: Vec<Value>,
    pub notices: Vec<Value>,
    pub message: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FeishuResourceDownloadRequest {
    pub message_id: String,
    pub file_key: String,
    #[serde(default)]
    pub resource_type: String,
    #[serde(default)]
    pub identity: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct FeishuResourceDownloadResult {
    pub ok: bool,
    pub local_path: String,
    pub name: String,
    pub size: u64,
    pub data_url: String,
    pub resource_type: String,
    pub stdout: String,
    pub stderr: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FeishuMessageGetRequest {
    pub message_id: String,
    #[serde(default)]
    pub identity: String,
    #[serde(default)]
    pub download_resources: bool,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct FeishuMessageGetResult {
    pub ok: bool,
    pub message_id: String,
    pub payload: Value,
    pub stdout: String,
    pub stderr: String,
}

struct FeishuListenerProcess {
    status: FeishuLocalListenerStatus,
    child: Child,
}

#[derive(Clone)]
struct FeishuBotRuntimeContext {
    connector: BotConnectorConfig,
    workspace_path: String,
    model_runtime: Option<LocalModelRuntimeConfig>,
    mcp_config: Value,
    backend_context: Option<LocalBackendContext>,
    permission_decision: Option<PermissionDecisionInput>,
}

fn global_bot_connector_config_path() -> Result<PathBuf, String> {
    env::var_os("HOME")
        .map(|home| {
            PathBuf::from(home)
                .join(".ai-employee")
                .join("agent-runtime-v2")
                .join("bots")
                .join("connectors.json")
        })
        .ok_or_else(|| "缺少 HOME，无法定位全局机器人连接器配置文件".to_string())
}

fn global_bot_listener_context_path() -> Result<PathBuf, String> {
    env::var_os("HOME")
        .map(|home| {
            PathBuf::from(home)
                .join(".ai-employee")
                .join("agent-runtime-v2")
                .join("bots")
                .join("listener-contexts.json")
        })
        .ok_or_else(|| "缺少 HOME，无法定位全局机器人监听上下文文件".to_string())
}

fn global_bot_listener_log_path() -> Option<PathBuf> {
    env::var_os("HOME").map(|home| {
        PathBuf::from(home)
            .join(".ai-employee")
            .join("agent-runtime-v2")
            .join("bots")
            .join("feishu-listener.jsonl")
    })
}

fn global_bot_conversation_dir() -> Result<PathBuf, String> {
    env::var_os("HOME")
        .map(|home| {
            PathBuf::from(home)
                .join(".ai-employee")
                .join("agent-runtime-v2")
                .join("bots")
                .join("conversations")
        })
        .ok_or_else(|| "缺少 HOME，无法定位全局机器人会话历史目录".to_string())
}

fn global_bot_project_binding_dir() -> Result<PathBuf, String> {
    env::var_os("HOME")
        .map(|home| {
            PathBuf::from(home)
                .join(".ai-employee")
                .join("agent-runtime-v2")
                .join("bots")
                .join("project-bindings")
        })
        .ok_or_else(|| "缺少 HOME，无法定位全局机器人项目绑定目录".to_string())
}

fn global_bot_pending_approval_dir() -> Result<PathBuf, String> {
    env::var_os("HOME")
        .map(|home| {
            PathBuf::from(home)
                .join(".ai-employee")
                .join("agent-runtime-v2")
                .join("bots")
                .join("pending-approvals")
        })
        .ok_or_else(|| "缺少 HOME，无法定位全局机器人授权确认目录".to_string())
}

fn global_bot_full_access_grant_dir() -> Result<PathBuf, String> {
    env::var_os("HOME")
        .map(|home| {
            PathBuf::from(home)
                .join(".ai-employee")
                .join("agent-runtime-v2")
                .join("bots")
                .join("full-access-grants")
        })
        .ok_or_else(|| "缺少 HOME，无法定位全局机器人完全授权目录".to_string())
}

fn append_listener_log(payload: Value) {
    let Some(path) = global_bot_listener_log_path() else {
        return;
    };
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let mut item = payload;
    if let Some(object) = item.as_object_mut() {
        object.insert("createdAtEpochMs".to_string(), json!(epoch_millis()));
    }
    if let Ok(line) = serde_json::to_string(&item) {
        use std::io::Write;
        if let Ok(mut file) = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(path)
        {
            let _ = writeln!(file, "{line}");
        }
    }
}

fn global_mcp_config_path() -> Option<PathBuf> {
    env::var_os("HOME").map(|home| PathBuf::from(home).join(".ai-employee").join("mcp.json"))
}

fn load_global_mcp_config() -> Value {
    let Some(path) = global_mcp_config_path() else {
        return json!({"mcpServers": {}});
    };
    let Ok(content) = std::fs::read_to_string(path) else {
        return json!({"mcpServers": {}});
    };
    serde_json::from_str::<Value>(&content).unwrap_or_else(|_| json!({"mcpServers": {}}))
}

fn default_bot_workspace_path() -> PathBuf {
    let base = if cfg!(target_os = "macos") {
        env::var_os("HOME")
            .map(PathBuf::from)
            .map(|home| home.join("Library").join("Application Support"))
    } else if cfg!(target_os = "windows") {
        env::var_os("APPDATA").map(PathBuf::from)
    } else {
        env::var_os("XDG_DATA_HOME").map(PathBuf::from).or_else(|| {
            env::var_os("HOME")
                .map(PathBuf::from)
                .map(|home| home.join(".local").join("share"))
        })
    };
    let path = base
        .unwrap_or_else(env::temp_dir)
        .join("ai-employee")
        .join("bot-workspace");
    let _ = std::fs::create_dir_all(&path);
    path
}

fn resolve_bot_workspace_path(raw: &str) -> String {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return default_bot_workspace_path().to_string_lossy().to_string();
    }
    trimmed.to_string()
}

fn load_local_bot_connectors() -> Result<Vec<Value>, String> {
    let path = global_bot_connector_config_path()?;
    let content =
        std::fs::read_to_string(&path).map_err(|err| format!("无法读取本机机器人配置：{err}"))?;
    let payload = serde_json::from_str::<Value>(&content)
        .map_err(|err| format!("机器人配置 JSON 无效：{err}"))?;
    Ok(payload
        .get("connectors")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default())
}

fn load_local_bot_connector(connector_id: &str) -> Result<Value, String> {
    load_local_bot_connectors()?
        .into_iter()
        .find(|item| {
            item.get("id")
                .and_then(Value::as_str)
                .map(|id| id.trim() == connector_id)
                .unwrap_or(false)
        })
        .ok_or_else(|| format!("本机机器人配置中找不到连接器：{connector_id}"))
}

fn load_stored_listener_contexts() -> Vec<StoredFeishuListenerContext> {
    let Ok(path) = global_bot_listener_context_path() else {
        return Vec::new();
    };
    let Ok(content) = std::fs::read_to_string(path) else {
        return Vec::new();
    };
    let Ok(payload) = serde_json::from_str::<Value>(&content) else {
        return Vec::new();
    };
    payload
        .get("listeners")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default()
        .into_iter()
        .filter_map(|item| serde_json::from_value::<StoredFeishuListenerContext>(item).ok())
        .collect()
}

fn persist_listener_context(context: StoredFeishuListenerContext) {
    if context.connector_id.trim().is_empty() || context.workspace_path.trim().is_empty() {
        return;
    }
    let Ok(path) = global_bot_listener_context_path() else {
        return;
    };
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let mut contexts = load_stored_listener_contexts();
    contexts.retain(|item| item.connector_id.trim() != context.connector_id.trim());
    contexts.push(context);
    let payload = json!({
        "version": 1,
        "listeners": contexts,
    });
    if let Ok(content) = serde_json::to_string_pretty(&payload) {
        let _ = std::fs::write(path, content);
    }
}

fn connector_auto_start_enabled(connector: &Value) -> bool {
    connector_bool(connector, "enabled", "enabled", true)
        && connector_bool(connector, "auto_start_worker", "autoStartWorker", false)
        && connector_field(connector, "platform", "platform").eq_ignore_ascii_case("feishu")
        && connector_field(connector, "event_receive_mode", "eventReceiveMode")
            .eq_ignore_ascii_case("long_connection")
}

fn connector_field(connector: &Value, snake: &str, camel: &str) -> String {
    connector
        .get(snake)
        .or_else(|| connector.get(camel))
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string()
}

fn connector_bool(connector: &Value, snake: &str, camel: &str, fallback: bool) -> bool {
    connector
        .get(snake)
        .or_else(|| connector.get(camel))
        .and_then(Value::as_bool)
        .unwrap_or(fallback)
}

fn connector_model_runtime(connector: &Value) -> Option<LocalModelRuntimeConfig> {
    connector
        .get("model_runtime")
        .or_else(|| connector.get("modelRuntime"))
        .and_then(|value| serde_json::from_value::<LocalModelRuntimeConfig>(value.clone()).ok())
}

fn connector_config_from_value(connector: &Value, owner_username: &str) -> BotConnectorConfig {
    BotConnectorConfig {
        connector_id: connector_field(connector, "id", "id"),
        platform: connector_field(connector, "platform", "platform"),
        name: connector_field(connector, "name", "name"),
        system_prompt: connector_field(connector, "system_prompt", "systemPrompt"),
        provider_id: connector_field(connector, "provider_id", "providerId"),
        model_name: connector_field(connector, "model_name", "modelName"),
        reply_identity: connector_field(connector, "reply_identity", "replyIdentity"),
        owner_username: owner_username.trim().to_string(),
        sandbox_mode: connector_field(connector, "sandbox_mode", "sandboxMode"),
        high_risk_tool_confirm: Some(connector_bool(
            connector,
            "high_risk_tool_confirm",
            "highRiskToolConfirm",
            true,
        )),
    }
}

fn value_string(value: &Value, keys: &[&str]) -> String {
    keys.iter()
        .find_map(|key| value.get(*key).and_then(Value::as_str))
        .unwrap_or("")
        .trim()
        .to_string()
}

fn event_text(event: &Value) -> String {
    value_string(event, &["content", "text", "message"])
}

fn normalize_message_text(connector: &BotConnectorConfig, event: &Value) -> String {
    let mut content = event_text(event);
    for name in [
        connector.name.as_str(),
        connector.connector_id.as_str(),
        connector.platform.as_str(),
    ] {
        let normalized = name.trim();
        if normalized.is_empty() {
            continue;
        }
        let lowered = content.to_ascii_lowercase();
        let target = normalized.to_ascii_lowercase();
        for prefix in [
            format!("@{target}"),
            format!("{target}:"),
            format!("{target}："),
            target.clone(),
        ] {
            if lowered.starts_with(&prefix) {
                content = content[prefix.len()..]
                    .trim_start_matches([' ', ':', '：', ',', '，'])
                    .trim()
                    .to_string();
                break;
            }
        }
    }
    content.trim().to_string()
}

fn event_mention_count(event: &Value) -> usize {
    ["mentions", "message_mentions"]
        .iter()
        .filter_map(|key| event.get(*key).and_then(Value::as_array))
        .map(Vec::len)
        .sum()
}

fn event_text_matches_connector(connector: &BotConnectorConfig, event: &Value) -> bool {
    let content = event_text(event).to_ascii_lowercase();
    [connector.name.as_str(), connector.connector_id.as_str()]
        .iter()
        .map(|value| value.trim().to_ascii_lowercase())
        .filter(|value| !value.is_empty())
        .any(|value| content.contains(&value))
}

fn should_handle_event(_connector: &BotConnectorConfig, event: &Value) -> bool {
    let chat_type = value_string(event, &["chat_type", "chatType"]).to_ascii_lowercase();
    chat_type == "p2p"
}

fn resolve_feishu_sdk_worker_path(app: &AppHandle) -> Result<PathBuf, String> {
    let dev_path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(FEISHU_SDK_WORKER_RELATIVE_PATH);
    if dev_path.is_file() {
        return Ok(dev_path);
    }
    if let Ok(resource_dir) = app.path().resource_dir() {
        let candidate = resource_dir.join(FEISHU_SDK_WORKER_RELATIVE_PATH);
        if candidate.is_file() {
            return Ok(candidate);
        }
    }
    let exe_dir = env::current_exe()
        .ok()
        .and_then(|path| path.parent().map(PathBuf::from));
    if let Some(dir) = exe_dir {
        for candidate in [
            dir.join(FEISHU_SDK_WORKER_RELATIVE_PATH),
            dir.join("resources").join(FEISHU_SDK_WORKER_RELATIVE_PATH),
            dir.join("../Resources")
                .join(FEISHU_SDK_WORKER_RELATIVE_PATH),
        ] {
            if candidate.is_file() {
                return Ok(candidate);
            }
        }
    }
    Err("无法定位飞书 Python SDK 本地监听 worker".to_string())
}

fn resolve_feishu_sdk_worker_path_for_command() -> Result<PathBuf, String> {
    let dev_path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(FEISHU_SDK_WORKER_RELATIVE_PATH);
    if dev_path.is_file() {
        return Ok(dev_path);
    }
    let exe_dir = env::current_exe()
        .ok()
        .and_then(|path| path.parent().map(PathBuf::from));
    if let Some(dir) = exe_dir {
        for candidate in [
            dir.join(FEISHU_SDK_WORKER_RELATIVE_PATH),
            dir.join("resources").join(FEISHU_SDK_WORKER_RELATIVE_PATH),
            dir.join("../Resources")
                .join(FEISHU_SDK_WORKER_RELATIVE_PATH),
        ] {
            if candidate.is_file() {
                return Ok(candidate);
            }
        }
    }
    Err("无法定位飞书 Python SDK 本地监听 worker".to_string())
}

fn resolve_feishu_sdk_python() -> Result<PathBuf, String> {
    if let Some(path) = env::var_os(FEISHU_PYTHON_ENV).map(PathBuf::from) {
        if path.is_file() {
            return Ok(path);
        }
        return Err(format!(
            "{} 指向的 Python 不存在：{}",
            FEISHU_PYTHON_ENV,
            path.to_string_lossy()
        ));
    }

    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    #[cfg(target_os = "windows")]
    let api_venv_python = manifest_dir.join("..\\..\\api\\.venv\\Scripts\\python.exe");
    #[cfg(not(target_os = "windows"))]
    let api_venv_python = manifest_dir.join("../../api/.venv/bin/python");
    if api_venv_python.is_file() {
        return Ok(api_venv_python);
    }

    Ok(PathBuf::from("python3"))
}

pub fn start_local_listener(
    app: AppHandle,
    request: FeishuLocalListenerStartRequest,
) -> Result<FeishuLocalListenerStatus, String> {
    let connector_id = request.connector_id.trim().to_string();
    if connector_id.is_empty() {
        return Err("缺少机器人连接器 ID".to_string());
    }

    let mut store = listener_store()
        .lock()
        .map_err(|_| "无法访问本地飞书监听器状态".to_string())?;
    if store.is_empty() {
        stop_stale_sdk_listener_processes();
    }
    if let Some(mut existing) = store.remove(&connector_id) {
        existing.child.stdin.take();
        let _ = existing.child.kill();
        let _ = existing.child.wait();
    }

    let connector = load_local_bot_connector(&connector_id)?;
    let app_id = connector_field(&connector, "app_id", "appId");
    let app_secret = connector_field(&connector, "app_secret", "appSecret");
    if app_id.is_empty() || app_secret.is_empty() {
        return Err("飞书机器人缺少 App ID 或 App Secret".to_string());
    }
    let runtime_context = FeishuBotRuntimeContext {
        connector: connector_config_from_value(&connector, request.owner_username.as_str()),
        workspace_path: resolve_bot_workspace_path(&request.workspace_path),
        model_runtime: request
            .model_runtime
            .clone()
            .or_else(|| connector_model_runtime(&connector)),
        mcp_config: request.mcp_config.clone(),
        backend_context: request.backend_context.clone(),
        permission_decision: request.permission_decision.clone(),
    };
    let worker_path = resolve_feishu_sdk_worker_path(&app)?;
    let python = resolve_feishu_sdk_python()?;
    let mut child = Command::new(python)
        .arg(worker_path)
        .env("AI_EMPLOYEE_FEISHU_CONNECTOR_ID", connector_id.as_str())
        .env("AI_EMPLOYEE_FEISHU_APP_ID", app_id.as_str())
        .env("AI_EMPLOYEE_FEISHU_APP_SECRET", app_secret.as_str())
        .env(
            "AI_EMPLOYEE_FEISHU_ENCRYPT_KEY",
            connector_field(&connector, "encrypt_key", "encryptKey"),
        )
        .env(
            "AI_EMPLOYEE_FEISHU_VERIFICATION_TOKEN",
            connector_field(&connector, "verification_token", "verificationToken"),
        )
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|err| format!("无法启动飞书 Python SDK 本地监听：{err}"))?;

    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "无法读取飞书 Python SDK 事件输出".to_string())?;
    let stderr = child
        .stderr
        .take()
        .ok_or_else(|| "无法读取飞书 Python SDK 监听状态".to_string())?;

    let status = FeishuLocalListenerStatus {
        connector_id: connector_id.clone(),
        running: true,
        project_id: DESKTOP_BOT_GLOBAL_PROJECT_ID.to_string(),
        chat_session_id: String::new(),
        workspace_path: runtime_context.workspace_path.clone(),
        started_at_epoch_ms: epoch_millis(),
        reason: "running".to_string(),
    };

    emit_listener_status(&app, &status, "starting", "飞书 Python SDK 本地监听启动中");
    spawn_stderr_forwarder(app.clone(), status.clone(), stderr);
    spawn_stdout_forwarder(app, status.clone(), stdout, runtime_context.clone());
    store.insert(
        connector_id,
        FeishuListenerProcess {
            status: status.clone(),
            child,
        },
    );
    persist_listener_context(StoredFeishuListenerContext {
        connector_id: status.connector_id.clone(),
        workspace_path: status.workspace_path.clone(),
        owner_username: runtime_context.connector.owner_username.clone(),
        model_runtime: runtime_context.model_runtime.clone(),
        mcp_config: runtime_context.mcp_config.clone(),
        backend_context: runtime_context.backend_context.clone(),
    });
    Ok(status)
}

pub fn stop_local_listener(connector_id: String) -> Result<FeishuLocalListenerStatus, String> {
    let connector_id = connector_id.trim().to_string();
    if connector_id.is_empty() {
        return Err("缺少机器人连接器 ID".to_string());
    }
    let mut process = {
        let mut store = listener_store()
            .lock()
            .map_err(|_| "无法访问本地飞书监听器状态".to_string())?;
        match store.remove(&connector_id) {
            Some(process) => process,
            None => {
                return Ok(FeishuLocalListenerStatus {
                    connector_id,
                    running: false,
                    project_id: String::new(),
                    chat_session_id: String::new(),
                    workspace_path: String::new(),
                    started_at_epoch_ms: 0,
                    reason: "not_running".to_string(),
                });
            }
        }
    };

    process.child.stdin.take();
    let deadline = Instant::now() + Duration::from_secs(3);
    loop {
        match process.child.try_wait() {
            Ok(Some(_status)) => break,
            Ok(None) if Instant::now() < deadline => thread::sleep(Duration::from_millis(100)),
            Ok(None) => {
                let _ = process.child.kill();
                let _ = process.child.wait();
                break;
            }
            Err(_) => break,
        }
    }
    process.status.running = false;
    process.status.reason = "stopped".to_string();
    Ok(process.status)
}

pub fn list_local_listeners() -> Vec<FeishuLocalListenerStatus> {
    let Ok(store) = listener_store().lock() else {
        return Vec::new();
    };
    store
        .values()
        .map(|process| process.status.clone())
        .collect()
}

pub fn start_persisted_local_listeners(app: AppHandle) {
    thread::spawn(move || {
        stop_stale_sdk_listener_processes();
        let connectors = load_local_bot_connectors().unwrap_or_default();
        if connectors.is_empty() {
            return;
        }
        let contexts = load_stored_listener_contexts();
        for connector in connectors
            .iter()
            .filter(|item| connector_auto_start_enabled(item))
        {
            let connector_id = connector_field(connector, "id", "id");
            if connector_id.is_empty() {
                continue;
            }
            let context = contexts
                .iter()
                .find(|item| item.connector_id.trim() == connector_id)
                .cloned()
                .unwrap_or_else(|| StoredFeishuListenerContext {
                    connector_id: connector_id.clone(),
                    workspace_path: default_bot_workspace_path().to_string_lossy().to_string(),
                    owner_username: String::new(),
                    model_runtime: None,
                    mcp_config: load_global_mcp_config(),
                    backend_context: None,
                });
            let request = FeishuLocalListenerStartRequest {
                connector_id: connector_id.clone(),
                workspace_path: context.workspace_path,
                owner_username: context.owner_username,
                model_runtime: context
                    .model_runtime
                    .or_else(|| connector_model_runtime(connector)),
                mcp_config: load_global_mcp_config(),
                backend_context: context.backend_context,
                permission_decision: None,
            };
            if let Err(error) = start_local_listener(app.clone(), request) {
                let status = FeishuLocalListenerStatus {
                    connector_id,
                    running: false,
                    project_id: String::new(),
                    chat_session_id: String::new(),
                    workspace_path: String::new(),
                    started_at_epoch_ms: 0,
                    reason: "auto_start_failed".to_string(),
                };
                emit_listener_status(
                    &app,
                    &status,
                    "error",
                    format!("飞书本地监听自动启动失败：{error}").as_str(),
                );
            }
        }
    });
}

fn stop_stale_sdk_listener_processes() {
    #[cfg(unix)]
    {
        let pattern = FEISHU_SDK_WORKER_RELATIVE_PATH;
        let _ = Command::new("pkill").args(["-f", pattern]).status();
    }
}

pub fn reply_message(request: FeishuLocalReplyRequest) -> Result<FeishuLocalReplyResult, String> {
    let connector_id = request.connector_id.trim().to_string();
    if !connector_id.is_empty() {
        return reply_message_with_connector(&connector_id, request);
    }
    Err("缺少机器人连接器 ID，无法使用飞书 SDK 回复".to_string())
}

fn reply_message_with_connector(
    connector_id: &str,
    request: FeishuLocalReplyRequest,
) -> Result<FeishuLocalReplyResult, String> {
    let message_id = request.message_id.trim();
    let content = request.content.trim();
    if message_id.is_empty() {
        return Err("缺少飞书 message_id，无法回复".to_string());
    }
    if content.is_empty() {
        return Err("缺少回复内容".to_string());
    }
    if matches!(
        request.reply_identity.trim().to_ascii_lowercase().as_str(),
        "user"
    ) {
        return Err("飞书 SDK 本地机器人回复只支持 bot 身份，不能代表用户发送".to_string());
    }
    let connector = load_local_bot_connector(connector_id)?;
    let app_id = connector_field(&connector, "app_id", "appId");
    let app_secret = connector_field(&connector, "app_secret", "appSecret");
    if app_id.is_empty() || app_secret.is_empty() {
        return Err("飞书机器人缺少 App ID 或 App Secret".to_string());
    }
    let idempotency_key = if request.idempotency_key.trim().is_empty() {
        format!("desktop-bot-reply-{message_id}")
    } else {
        request.idempotency_key.trim().to_string()
    };

    let python = resolve_feishu_sdk_python()?;
    let worker_path = resolve_feishu_sdk_worker_path_for_command()?;
    let mut command = Command::new(python);
    command
        .arg(worker_path)
        .env("AI_EMPLOYEE_FEISHU_COMMAND", "reply")
        .env("AI_EMPLOYEE_FEISHU_CONNECTOR_ID", connector_id)
        .env("AI_EMPLOYEE_FEISHU_APP_ID", app_id.as_str())
        .env("AI_EMPLOYEE_FEISHU_APP_SECRET", app_secret.as_str())
        .env("AI_EMPLOYEE_FEISHU_MESSAGE_ID", message_id)
        .env("AI_EMPLOYEE_FEISHU_REPLY_CONTENT", content)
        .env(
            "AI_EMPLOYEE_FEISHU_REPLY_FORMAT",
            request.content_format.trim(),
        )
        .env(
            "AI_EMPLOYEE_FEISHU_IDEMPOTENCY_KEY",
            idempotency_key.as_str(),
        )
        .env(
            "AI_EMPLOYEE_FEISHU_REPLY_IN_THREAD",
            if request.reply_in_thread {
                "true"
            } else {
                "false"
            },
        );
    let output = command
        .output()
        .map_err(|err| format!("无法执行飞书 Python SDK 回复：{err}"))?;
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
    if !output.status.success() {
        return Err(format!(
            "飞书 Python SDK 回复失败：{}",
            if stderr.is_empty() {
                stdout.as_str()
            } else {
                stderr.as_str()
            }
        ));
    }
    Ok(FeishuLocalReplyResult {
        ok: true,
        stdout,
        stderr,
    })
}

fn send_feishu_interactive_card(
    connector_id: &str,
    chat_id: &str,
    card: Value,
    idempotency_key: &str,
) -> Result<Value, String> {
    let chat_id = chat_id.trim();
    if chat_id.is_empty() {
        return Err("缺少飞书 chat_id，无法发送授权卡片".to_string());
    }
    run_feishu_card_worker_command(
        connector_id,
        "send_card",
        "",
        chat_id,
        card,
        idempotency_key,
    )
}

fn update_feishu_interactive_card(
    connector_id: &str,
    message_id: &str,
    card: Value,
) -> Result<Value, String> {
    let message_id = message_id.trim();
    if message_id.is_empty() {
        return Err("缺少飞书 message_id，无法更新授权卡片".to_string());
    }
    run_feishu_card_worker_command(connector_id, "update_card", message_id, "", card, "")
}

fn run_feishu_card_worker_command(
    connector_id: &str,
    command_name: &str,
    message_id: &str,
    chat_id: &str,
    card: Value,
    idempotency_key: &str,
) -> Result<Value, String> {
    let connector = load_local_bot_connector(connector_id)?;
    let app_id = connector_field(&connector, "app_id", "appId");
    let app_secret = connector_field(&connector, "app_secret", "appSecret");
    if app_id.is_empty() || app_secret.is_empty() {
        return Err("飞书机器人缺少 App ID 或 App Secret".to_string());
    }
    let content =
        serde_json::to_string(&card).map_err(|err| format!("授权卡片 JSON 无效：{err}"))?;
    let python = resolve_feishu_sdk_python()?;
    let worker_path = resolve_feishu_sdk_worker_path_for_command()?;
    let mut command = Command::new(python);
    command
        .arg(worker_path)
        .env("AI_EMPLOYEE_FEISHU_COMMAND", command_name)
        .env("AI_EMPLOYEE_FEISHU_CONNECTOR_ID", connector_id)
        .env("AI_EMPLOYEE_FEISHU_APP_ID", app_id.as_str())
        .env("AI_EMPLOYEE_FEISHU_APP_SECRET", app_secret.as_str())
        .env("AI_EMPLOYEE_FEISHU_MESSAGE_ID", message_id.trim())
        .env("AI_EMPLOYEE_FEISHU_CHAT_ID", chat_id.trim())
        .env("AI_EMPLOYEE_FEISHU_CARD_CONTENT", content)
        .env("AI_EMPLOYEE_FEISHU_IDEMPOTENCY_KEY", idempotency_key.trim());
    let output = command
        .output()
        .map_err(|err| format!("无法执行飞书 Python SDK 卡片命令：{err}"))?;
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
    if !output.status.success() {
        return Err(format!(
            "飞书 Python SDK 卡片命令失败：{}",
            if stderr.is_empty() {
                stdout.as_str()
            } else {
                stderr.as_str()
            }
        ));
    }
    serde_json::from_str::<Value>(&stdout)
        .map_err(|err| format!("飞书 Python SDK 卡片命令返回无效 JSON：{err}"))
}

pub fn scan_chats(request: FeishuChatScanRequest) -> Result<FeishuChatScanResult, String> {
    let identity = match request.identity.trim().to_ascii_lowercase().as_str() {
        "user" => "user",
        _ => "bot",
    };
    let page_size = request.page_size.clamp(1, 100).to_string();
    let page_limit = usize::from(request.page_limit.clamp(1, 20));
    let mut page_token = String::new();
    let mut items = Vec::new();
    let mut notices = Vec::new();

    for _page in 0..page_limit {
        let mut command = Command::new("lark-cli");
        command.args([
            "im",
            "+chat-list",
            "--as",
            identity,
            "--sort",
            "active_time",
            "--page-size",
            page_size.as_str(),
            "--json",
        ]);
        if !page_token.is_empty() {
            command.args(["--page-token", page_token.as_str()]);
        }
        let output = command
            .output()
            .map_err(|err| format!("无法执行 lark-cli 群扫描：{err}"))?;
        let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
        if !output.status.success() {
            return Err(format!(
                "lark-cli 群扫描失败：{}",
                if stderr.is_empty() {
                    stdout.as_str()
                } else {
                    stderr.as_str()
                }
            ));
        }
        let payload = serde_json::from_str::<Value>(&stdout)
            .map_err(|err| format!("飞书群扫描结果不是有效 JSON：{err}"))?;
        items.extend(extract_chat_items(&payload));
        notices.extend(extract_array_field(&payload, "notices"));
        page_token = extract_next_page_token(&payload);
        if page_token.is_empty() {
            break;
        }
    }

    Ok(FeishuChatScanResult {
        status: "scanned".to_string(),
        identity: identity.to_string(),
        count: items.len(),
        items,
        notices,
        message: "桌面端已通过 lark-cli 扫描当前身份可见群".to_string(),
    })
}

pub fn download_resource(
    request: FeishuResourceDownloadRequest,
) -> Result<FeishuResourceDownloadResult, String> {
    let message_id = request.message_id.trim();
    let file_key = request.file_key.trim();
    if message_id.is_empty() || file_key.is_empty() {
        return Err("下载飞书资源需要 message_id 和 file_key".to_string());
    }
    let identity = match request.identity.trim().to_ascii_lowercase().as_str() {
        "user" => "user",
        _ => "bot",
    };
    let resource_type = match request.resource_type.trim().to_ascii_lowercase().as_str() {
        "file" => "file",
        _ => "image",
    };
    let root = std::env::temp_dir().join("ai-employee-feishu-resources");
    std::fs::create_dir_all(&root).map_err(|err| format!("无法创建飞书资源目录：{err}"))?;
    let output_name = safe_resource_filename(message_id, file_key, resource_type);
    let mut command = Command::new("lark-cli");
    command.current_dir(&root).args([
        "im",
        "+messages-resources-download",
        "--as",
        identity,
        "--message-id",
        message_id,
        "--file-key",
        file_key,
        "--type",
        resource_type,
        "--output",
        output_name.as_str(),
        "--json",
    ]);
    let output = command
        .output()
        .map_err(|err| format!("无法执行 lark-cli 资源下载：{err}"))?;
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
    if !output.status.success() {
        return Err(format!(
            "lark-cli 飞书资源下载失败：{}",
            if stderr.is_empty() {
                stdout.as_str()
            } else {
                stderr.as_str()
            }
        ));
    }
    let local_path = resolve_downloaded_resource_path(&root, &output_name, &stdout);
    let bytes = std::fs::read(&local_path).unwrap_or_default();
    let size = u64::try_from(bytes.len()).unwrap_or(0);
    let mime_type = infer_resource_mime_type(&local_path, resource_type);
    let data_url = if bytes.is_empty() {
        String::new()
    } else {
        format!(
            "data:{};base64,{}",
            mime_type,
            general_purpose::STANDARD.encode(bytes)
        )
    };
    Ok(FeishuResourceDownloadResult {
        ok: true,
        local_path: local_path.to_string_lossy().to_string(),
        name: local_path
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or(output_name.as_str())
            .to_string(),
        size,
        data_url,
        resource_type: resource_type.to_string(),
        stdout,
        stderr,
    })
}

pub fn get_message(request: FeishuMessageGetRequest) -> Result<FeishuMessageGetResult, String> {
    let message_id = request.message_id.trim();
    if message_id.is_empty() {
        return Err("读取飞书消息需要 message_id".to_string());
    }
    let identity = match request.identity.trim().to_ascii_lowercase().as_str() {
        "user" => "user",
        _ => "bot",
    };
    let root = std::env::temp_dir().join("ai-employee-feishu-message-details");
    std::fs::create_dir_all(&root).map_err(|err| format!("无法创建飞书消息详情目录：{err}"))?;
    let mut command = Command::new("lark-cli");
    command.current_dir(&root).args([
        "im",
        "+messages-mget",
        "--as",
        identity,
        "--message-ids",
        message_id,
        "--json",
    ]);
    if request.download_resources {
        command.arg("--download-resources");
    }
    let output = command
        .output()
        .map_err(|err| format!("无法执行 lark-cli 消息详情读取：{err}"))?;
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
    if !output.status.success() {
        return Err(format!(
            "lark-cli 飞书消息详情读取失败：{}",
            if stderr.is_empty() {
                stdout.as_str()
            } else {
                stderr.as_str()
            }
        ));
    }
    let payload = serde_json::from_str::<Value>(&stdout)
        .map_err(|err| format!("飞书消息详情结果不是有效 JSON：{err}"))?;
    Ok(FeishuMessageGetResult {
        ok: true,
        message_id: message_id.to_string(),
        payload,
        stdout,
        stderr,
    })
}

fn spawn_stdout_forwarder(
    app: AppHandle,
    status: FeishuLocalListenerStatus,
    stdout: impl std::io::Read + Send + 'static,
    runtime_context: FeishuBotRuntimeContext,
) {
    thread::spawn(move || {
        let reader = BufReader::new(stdout);
        for line in reader.lines().map_while(Result::ok) {
            let raw = line.trim();
            if raw.is_empty() {
                continue;
            }
            let event =
                serde_json::from_str::<Value>(raw).unwrap_or_else(|_| json!({ "raw": raw }));
            let payload = json!({
                "connectorId": status.connector_id.as_str(),
                "projectId": status.project_id.as_str(),
                "chatSessionId": status.chat_session_id.as_str(),
                "workspacePath": status.workspace_path.as_str(),
                "event": event,
                "source": "tauri_feishu_local_listener"
            });
            append_listener_log(json!({
                "kind": "event",
                "connectorId": status.connector_id.as_str(),
                "messageId": payload["event"].get("message_id").and_then(Value::as_str).unwrap_or(""),
                "chatId": payload["event"].get("chat_id").and_then(Value::as_str).unwrap_or(""),
                "chatType": payload["event"].get("chat_type").and_then(Value::as_str).unwrap_or("")
            }));
            let _ = app.emit("bot-feishu-local-event", payload.clone());
            let _ = app.emit("bot://feishu-local-event", payload);
            let app_for_event = app.clone();
            let status_for_event = status.clone();
            let runtime_context_for_event = runtime_context.clone();
            thread::spawn(move || {
                if let Err(error) = handle_local_feishu_event(
                    app_for_event.clone(),
                    status_for_event.clone(),
                    runtime_context_for_event,
                    event,
                ) {
                    emit_listener_status(
                        &app_for_event,
                        &status_for_event,
                        "error",
                        format!("飞书本地机器人处理失败：{error}").as_str(),
                    );
                }
            });
        }
    });
}

fn handle_local_feishu_event(
    app: AppHandle,
    status: FeishuLocalListenerStatus,
    context: FeishuBotRuntimeContext,
    event: Value,
) -> Result<(), String> {
    let event_id = first_value_string(
        [
            value_string(&event, &["event_id", "eventId"]),
            value_string(&event, &["message_id", "messageId"]),
            value_string(&event, &["id"]),
        ],
        "",
    );
    let dedupe_key = format!(
        "{}:{}",
        context.connector.connector_id,
        if event_id.is_empty() {
            serde_json::to_string(&event)
                .unwrap_or_default()
                .chars()
                .take(160)
                .collect::<String>()
        } else {
            event_id.clone()
        }
    );
    {
        let mut processing = processing_events()
            .lock()
            .map_err(|_| "无法访问飞书消息去重状态".to_string())?;
        if processing.contains(&dedupe_key) {
            return Ok(());
        }
        processing.insert(dedupe_key.clone());
    }

    let result = handle_local_feishu_event_inner(&app, &status, context, event);
    let _ = processing_events()
        .lock()
        .map(|mut processing| processing.remove(&dedupe_key));
    result
}

fn handle_local_feishu_event_inner(
    app: &AppHandle,
    status: &FeishuLocalListenerStatus,
    context: FeishuBotRuntimeContext,
    event: Value,
) -> Result<(), String> {
    if is_feishu_card_action_event(&event) {
        return handle_local_feishu_card_action(app, status, context, event);
    }
    if !should_handle_event(&context.connector, &event) {
        let chat_type = value_string(&event, &["chat_type", "chatType"]);
        let mention_count = event_mention_count(&event);
        let name_matched = event_text_matches_connector(&context.connector, &event);
        emit_listener_status(
            app,
            status,
            "ignored",
            format!(
                "飞书消息未进入机器人：仅处理私聊；chatType={} mentions={} nameMatched={}",
                if chat_type.is_empty() {
                    "unknown"
                } else {
                    chat_type.as_str()
                },
                mention_count,
                name_matched
            )
            .as_str(),
        );
        return Ok(());
    }
    let message_id = value_string(&event, &["message_id", "messageId", "id"]);
    let message = normalize_message_text(&context.connector, &event);
    if context.workspace_path.is_empty() {
        return Err("缺少桌面机器人工作区，无法执行桌面机器人".to_string());
    }
    if message_id.is_empty() || message.is_empty() {
        return Err("飞书事件缺少 message_id 或有效文本内容".to_string());
    }
    if let Some(decision) = text_permission_decision(&message) {
        if let Some(mut pending) = load_latest_pending_approval_for_chat(
            &context.connector.connector_id,
            &value_string(&event, &["chat_id", "chatId"]),
            &value_string(&event, &["sender_id", "senderId"]),
        ) {
            pending.original_event = event.clone();
            pending.external_message_id = message_id.clone();
            return handle_pending_approval_decision(
                app,
                status,
                context,
                pending,
                decision.as_str(),
                "text_reply",
            );
        }
    }

    emit_listener_status(app, status, "processing", "飞书消息已进入桌面智能体运行时");
    if let Err(error) =
        reply_feishu_status_message(&context, &event, &message_id, "👋 收到，正在处理。", "ack")
    {
        emit_listener_status(
            app,
            status,
            "warning",
            format!("飞书在线回执发送失败：{error}").as_str(),
        );
    }
    let chat_session_id = bot_chat_session_id(&context.connector.connector_id, &event);
    let history = load_bot_conversation_history(&context.connector.connector_id, &chat_session_id);
    let existing_project_binding =
        load_bot_project_binding(&context.connector.connector_id, &chat_session_id).or_else(|| {
            prefetch_bot_project_binding_from_context(
                &context.connector.connector_id,
                &chat_session_id,
                &message,
                &history,
                context.backend_context.as_ref(),
            )
        });
    let bound_project_id = existing_project_binding
        .as_ref()
        .map(|binding| binding.project_id.trim())
        .filter(|value| !value.is_empty())
        .unwrap_or(DESKTOP_BOT_GLOBAL_PROJECT_ID)
        .to_string();
    let bound_workspace_path = existing_project_binding
        .as_ref()
        .map(|binding| binding.workspace_path.trim())
        .filter(|value| !value.is_empty())
        .unwrap_or(context.workspace_path.as_str())
        .to_string();
    let history_for_pending_approval = history.clone();
    let source_type =
        if value_string(&event, &["chat_type", "chatType"]).to_ascii_lowercase() == "p2p" {
            "private_message"
        } else {
            "group_message"
        };
    let request_permission_decision = context.permission_decision.clone().or_else(|| {
        bot_full_access_permission_decision(&context.connector.connector_id, &chat_session_id)
    });
    let request = BotChatRequest {
        project_id: bound_project_id.clone(),
        chat_session_id: chat_session_id.clone(),
        message_id: Some(message_id.clone()),
        assistant_message_id: Some(format!("bot-local-{}", epoch_millis())),
        message: message.clone(),
        workspace_path: bound_workspace_path.clone(),
        history,
        connector: context.connector.clone(),
        source_context: BotSourceContext {
            source_type: source_type.to_string(),
            external_chat_id: value_string(&event, &["chat_id", "chatId"]),
            external_chat_name: value_string(&event, &["chat_name", "chatName"]),
            external_message_id: message_id.clone(),
            thread_id: value_string(&event, &["thread_id", "threadId"]),
            raw: event.clone(),
        },
        permission_contract: None,
        provider_id: Some(context.connector.provider_id.clone()),
        model_name: Some(context.connector.model_name.clone()),
        model_runtime: context.model_runtime.clone(),
        attachments: Vec::new(),
        mcp_config: context.mcp_config.clone(),
        backend_context: context.backend_context.clone(),
        permission_decision: request_permission_decision,
    };

    let app_for_events = app.clone();
    let status_for_events = status.clone();
    let context_for_events = context.clone();
    let event_for_replies = event.clone();
    let message_id_for_replies = message_id.clone();
    let sent_progress_replies = Mutex::new(HashSet::<String>::new());
    let approval_card_sent = Arc::new(Mutex::new(false));
    let approval_card_sent_for_events = approval_card_sent.clone();
    let discovered_project_binding = Arc::new(Mutex::new(None::<StoredBotProjectBinding>));
    let discovered_project_binding_for_events = discovered_project_binding.clone();
    let project_id_for_approval = bound_project_id.clone();
    let workspace_path_for_approval = bound_workspace_path.clone();
    let user_message_for_approval = message.clone();
    let history_for_approval = history_for_pending_approval.clone();
    let result = crate::bot::start_bot_chat_with_event_sink(request, |event| {
        let _ = app_for_events.emit("bot-runtime-event", event.clone());
        let _ = app_for_events.emit("bot://runtime-event", event.clone());
        if let Some(binding) = bot_project_binding_from_runtime_event(
            &context_for_events.connector.connector_id,
            &chat_session_id,
            &event,
        ) {
            if let Ok(mut current) = discovered_project_binding_for_events.lock() {
                *current = Some(binding);
            }
        }
        if is_runtime_approval_required_event(&event) {
            let request_id = approval_request_id_from_runtime_event(&event);
            let progress_key = format!("approval-{}", sanitize_id(request_id.as_str()));
            let should_send = sent_progress_replies
                .lock()
                .map(|mut sent| {
                    if sent.contains(progress_key.as_str()) {
                        false
                    } else {
                        sent.insert(progress_key.clone());
                        true
                    }
                })
                .unwrap_or(false);
            if should_send {
                if let Err(error) = reply_feishu_status_message(
                    &context_for_events,
                    &event_for_replies,
                    &message_id_for_replies,
                    approval_status_message(&event).as_str(),
                    format!("approval-status-{progress_key}").as_str(),
                ) {
                    emit_listener_status(
                        &app_for_events,
                        &status_for_events,
                        "warning",
                        format!("飞书授权说明发送失败：{error}").as_str(),
                    );
                }
                match send_bot_approval_card_for_runtime_event(
                    &context_for_events,
                    &event_for_replies,
                    &message_id_for_replies,
                    &chat_session_id,
                    &project_id_for_approval,
                    &workspace_path_for_approval,
                    &user_message_for_approval,
                    &history_for_approval,
                    &event,
                ) {
                    Ok(()) => {
                        let _ = approval_card_sent_for_events
                            .lock()
                            .map(|mut sent| *sent = true);
                    }
                    Err(error) => emit_listener_status(
                        &app_for_events,
                        &status_for_events,
                        "warning",
                        format!("飞书授权卡片发送失败：{error}").as_str(),
                    ),
                }
            }
            return;
        }
        let Some((progress_key, progress_content)) = bot_progress_reply_for_runtime_event(&event)
        else {
            return;
        };
        let should_send = sent_progress_replies
            .lock()
            .map(|mut sent| {
                if sent.contains(progress_key.as_str()) {
                    false
                } else {
                    sent.insert(progress_key.clone());
                    true
                }
            })
            .unwrap_or(false);
        if !should_send {
            return;
        }
        if let Err(error) = reply_feishu_status_message(
            &context_for_events,
            &event_for_replies,
            &message_id_for_replies,
            progress_content.as_str(),
            progress_key.as_str(),
        ) {
            emit_listener_status(
                &app_for_events,
                &status_for_events,
                "warning",
                format!("飞书进度消息发送失败：{error}").as_str(),
            );
        }
    });
    if !result.ok {
        let waiting_for_feishu_approval = result.error_code.trim() == "permission.required"
            && approval_card_sent.lock().map(|sent| *sent).unwrap_or(false);
        if waiting_for_feishu_approval {
            emit_listener_status(
                app,
                status,
                "waiting_approval",
                "已发送飞书授权卡片，等待用户确认",
            );
            return Ok(());
        }
        emit_listener_status(
            app,
            status,
            "warning",
            format!("桌面智能体未完成：{}", bot_result_status_summary(&result)).as_str(),
        );
        if let Err(error) = reply_feishu_status_message(
            &context,
            &event,
            &message_id,
            bot_safe_failure_reply(&result).as_str(),
            "failed",
        ) {
            emit_listener_status(
                app,
                status,
                "warning",
                format!("飞书失败提示发送失败：{error}").as_str(),
            );
        }
        return Ok(());
    }
    let reply_content = bot_reply_content(&result);
    if reply_content.is_empty() {
        emit_listener_status(app, status, "warning", "桌面智能体没有返回可回复内容");
        return Ok(());
    }
    reply_message_with_connector(
        &context.connector.connector_id,
        FeishuLocalReplyRequest {
            connector_id: context.connector.connector_id.clone(),
            message_id,
            content: reply_content.clone(),
            content_format: "text".to_string(),
            reply_identity: context.connector.reply_identity.clone(),
            reply_in_thread: !value_string(&event, &["thread_id", "threadId"]).is_empty(),
            idempotency_key: String::new(),
        },
    )?;
    if let Err(error) = append_bot_conversation_turn(
        &context.connector.connector_id,
        &chat_session_id,
        &message,
        &reply_content,
    ) {
        emit_listener_status(
            app,
            status,
            "warning",
            format!("飞书机器人会话历史写入失败：{error}").as_str(),
        );
    }
    let latest_project_binding = discovered_project_binding
        .lock()
        .ok()
        .and_then(|guard| guard.clone());
    if let Some(binding) = latest_project_binding {
        if let Err(error) = persist_bot_project_binding(&binding) {
            emit_listener_status(
                app,
                status,
                "warning",
                format!("飞书机器人项目绑定写入失败：{error}").as_str(),
            );
        }
    }
    emit_listener_status(app, status, "replied", "桌面智能体已回复飞书消息");
    Ok(())
}

fn reply_feishu_status_message(
    context: &FeishuBotRuntimeContext,
    event: &Value,
    message_id: &str,
    content: &str,
    idempotency_suffix: &str,
) -> Result<FeishuLocalReplyResult, String> {
    let normalized_suffix = sanitize_id(idempotency_suffix);
    reply_message_with_connector(
        &context.connector.connector_id,
        FeishuLocalReplyRequest {
            connector_id: context.connector.connector_id.clone(),
            message_id: message_id.to_string(),
            content: content.trim().to_string(),
            content_format: "text".to_string(),
            reply_identity: context.connector.reply_identity.clone(),
            reply_in_thread: !value_string(event, &["thread_id", "threadId"]).is_empty(),
            idempotency_key: format!("desktop-bot-{normalized_suffix}-{message_id}"),
        },
    )
}

fn load_bot_conversation_history(
    connector_id: &str,
    chat_session_id: &str,
) -> Vec<LocalChatMessage> {
    let path = match bot_conversation_path(connector_id, chat_session_id) {
        Ok(path) => path,
        Err(_) => return Vec::new(),
    };
    let Ok(raw) = std::fs::read_to_string(path) else {
        return Vec::new();
    };
    let Ok(record) = serde_json::from_str::<StoredBotConversation>(&raw) else {
        return Vec::new();
    };
    trim_bot_conversation_history(record.messages, 20)
}

fn append_bot_conversation_turn(
    connector_id: &str,
    chat_session_id: &str,
    user_message: &str,
    assistant_message: &str,
) -> Result<(), String> {
    let path = bot_conversation_path(connector_id, chat_session_id)?;
    let mut messages = load_bot_conversation_history(connector_id, chat_session_id);
    append_bot_conversation_messages(&mut messages, user_message, assistant_message, 20);
    let record = StoredBotConversation {
        version: 1,
        connector_id: connector_id.trim().to_string(),
        chat_session_id: chat_session_id.trim().to_string(),
        updated_at_epoch_ms: epoch_millis(),
        messages,
    };
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|err| format!("无法创建飞书机器人会话历史目录 {}：{err}", parent.display()))?;
    }
    let content = serde_json::to_string_pretty(&record)
        .map_err(|err| format!("无法序列化飞书机器人会话历史：{err}"))?;
    std::fs::write(&path, content)
        .map_err(|err| format!("无法写入飞书机器人会话历史 {}：{err}", path.display()))
}

fn append_bot_conversation_messages(
    messages: &mut Vec<LocalChatMessage>,
    user_message: &str,
    assistant_message: &str,
    max_messages: usize,
) {
    let user_content = user_message.trim();
    let assistant_content = assistant_message.trim();
    if user_content.is_empty() || assistant_content.is_empty() {
        return;
    }
    messages.push(bot_history_message("user", user_content));
    messages.push(bot_history_message("assistant", assistant_content));
    let trimmed = trim_bot_conversation_history(std::mem::take(messages), max_messages);
    *messages = trimmed;
}

fn trim_bot_conversation_history(
    messages: Vec<LocalChatMessage>,
    max_messages: usize,
) -> Vec<LocalChatMessage> {
    let mut clean = messages
        .into_iter()
        .filter(|message| {
            matches!(message.role.trim(), "user" | "assistant")
                && !message.content.trim().is_empty()
                && !message.diagnostic.unwrap_or(false)
        })
        .collect::<Vec<_>>();
    if max_messages > 0 && clean.len() > max_messages {
        clean = clean.split_off(clean.len() - max_messages);
    }
    clean
}

fn bot_history_message(role: &str, content: &str) -> LocalChatMessage {
    LocalChatMessage {
        role: role.to_string(),
        content: content.trim().to_string(),
        reasoning_content: None,
        source_kind: Some("feishu_bot_conversation".to_string()),
        diagnostic: Some(false),
        visibility: Some("conversation".to_string()),
    }
}

fn bot_conversation_path(connector_id: &str, chat_session_id: &str) -> Result<PathBuf, String> {
    let dir = global_bot_conversation_dir()?;
    let file_name = format!(
        "{}__{}.json",
        sanitize_id(connector_id),
        sanitize_id(chat_session_id)
    );
    Ok(dir.join(file_name))
}

fn load_bot_project_binding(
    connector_id: &str,
    chat_session_id: &str,
) -> Option<StoredBotProjectBinding> {
    let path = bot_project_binding_path(connector_id, chat_session_id).ok()?;
    let raw = std::fs::read_to_string(path).ok()?;
    let binding = serde_json::from_str::<StoredBotProjectBinding>(&raw).ok()?;
    valid_bot_project_binding(binding)
}

fn persist_bot_project_binding(binding: &StoredBotProjectBinding) -> Result<(), String> {
    let binding = valid_bot_project_binding(binding.clone())
        .ok_or_else(|| "项目绑定缺少有效 project_id 或 workspace_path".to_string())?;
    let path = bot_project_binding_path(&binding.connector_id, &binding.chat_session_id)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|err| format!("无法创建飞书机器人项目绑定目录 {}：{err}", parent.display()))?;
    }
    let content = serde_json::to_string_pretty(&binding)
        .map_err(|err| format!("无法序列化飞书机器人项目绑定：{err}"))?;
    std::fs::write(&path, content)
        .map_err(|err| format!("无法写入飞书机器人项目绑定 {}：{err}", path.display()))
}

fn bot_project_binding_path(connector_id: &str, chat_session_id: &str) -> Result<PathBuf, String> {
    let dir = global_bot_project_binding_dir()?;
    let file_name = format!(
        "{}__{}.json",
        sanitize_id(connector_id),
        sanitize_id(chat_session_id)
    );
    Ok(dir.join(file_name))
}

fn prefetch_bot_project_binding_from_context(
    connector_id: &str,
    chat_session_id: &str,
    message: &str,
    history: &[LocalChatMessage],
    backend_context: Option<&LocalBackendContext>,
) -> Option<StoredBotProjectBinding> {
    let backend_context = backend_context?;
    let mut project_ids = project_ids_from_text(message);
    for item in history.iter().rev() {
        project_ids.extend(project_ids_from_text(&item.content));
    }
    let project_id = project_ids
        .into_iter()
        .find(|value| !value.trim().is_empty())?;
    let result = execute_tool(ToolExecutionRequest {
        tool_call_id: Some("prefetch_project_binding".to_string()),
        name: "get_project".to_string(),
        arguments: json!({
            "project_id": project_id,
            "_backend_api_base_url": backend_context.api_base_url,
            "_backend_token": backend_context.token,
        }),
        workspace_path: String::new(),
        permission_decision: None,
    });
    if !result.ok {
        return None;
    }
    bot_project_binding_from_project_content(connector_id, chat_session_id, &result.content)
}

fn bot_project_binding_from_runtime_event(
    connector_id: &str,
    chat_session_id: &str,
    event: &Value,
) -> Option<StoredBotProjectBinding> {
    if event.get("type").and_then(Value::as_str).unwrap_or("") != "tool_result" {
        return None;
    }
    let payload = event.get("payload")?;
    if !payload.get("ok").and_then(Value::as_bool).unwrap_or(false) {
        return None;
    }
    let tool_name = payload
        .get("tool_name")
        .and_then(Value::as_str)
        .unwrap_or("");
    let content = payload.get("content").unwrap_or(&Value::Null);
    match tool_name {
        "get_project" => {
            bot_project_binding_from_project_content(connector_id, chat_session_id, content)
        }
        "list_projects" => {
            bot_project_binding_from_project_list_content(connector_id, chat_session_id, content)
        }
        _ => None,
    }
}

fn bot_project_binding_from_project_content(
    connector_id: &str,
    chat_session_id: &str,
    content: &Value,
) -> Option<StoredBotProjectBinding> {
    let project = content
        .get("response")
        .and_then(|response| response.get("project"))
        .or_else(|| content.get("project"))
        .unwrap_or(content);
    bot_project_binding_from_project_value(connector_id, chat_session_id, project)
}

fn bot_project_binding_from_project_list_content(
    connector_id: &str,
    chat_session_id: &str,
    content: &Value,
) -> Option<StoredBotProjectBinding> {
    let projects = content
        .get("response")
        .and_then(|response| response.get("projects"))
        .and_then(Value::as_array)
        .or_else(|| content.get("projects").and_then(Value::as_array))?;
    if projects.len() != 1 {
        return None;
    }
    bot_project_binding_from_project_value(connector_id, chat_session_id, &projects[0])
}

fn bot_project_binding_from_project_value(
    connector_id: &str,
    chat_session_id: &str,
    project: &Value,
) -> Option<StoredBotProjectBinding> {
    let project_id = value_string(project, &["id", "project_id", "projectId"]);
    let project_name = value_string(project, &["name", "project_name", "projectName"]);
    let workspace_path = value_string(project, &["workspace_path", "workspacePath"]);
    valid_bot_project_binding(StoredBotProjectBinding {
        version: 1,
        connector_id: connector_id.trim().to_string(),
        chat_session_id: chat_session_id.trim().to_string(),
        project_id,
        project_name,
        workspace_path,
        updated_at_epoch_ms: epoch_millis(),
    })
}

fn valid_bot_project_binding(binding: StoredBotProjectBinding) -> Option<StoredBotProjectBinding> {
    let project_id = binding.project_id.trim();
    let workspace_path = binding.workspace_path.trim();
    if project_id.is_empty() || workspace_path.is_empty() {
        return None;
    }
    let path = PathBuf::from(workspace_path);
    if !path.is_absolute() || !path.is_dir() {
        return None;
    }
    Some(StoredBotProjectBinding {
        version: 1,
        connector_id: binding.connector_id.trim().to_string(),
        chat_session_id: binding.chat_session_id.trim().to_string(),
        project_id: project_id.to_string(),
        project_name: binding.project_name.trim().to_string(),
        workspace_path: path.to_string_lossy().to_string(),
        updated_at_epoch_ms: binding.updated_at_epoch_ms,
    })
}

fn project_ids_from_text(text: &str) -> Vec<String> {
    let mut ids = Vec::new();
    for token in text.split(|ch: char| {
        ch.is_whitespace()
            || matches!(
                ch,
                '`' | '\''
                    | '"'
                    | ','
                    | '，'
                    | '.'
                    | '。'
                    | ':'
                    | '：'
                    | ';'
                    | '；'
                    | '('
                    | ')'
                    | '（'
                    | '）'
                    | '['
                    | ']'
                    | '【'
                    | '】'
            )
    }) {
        let token = token.trim();
        if token.starts_with("proj-")
            && token
                .chars()
                .all(|ch| ch.is_ascii_alphanumeric() || ch == '-' || ch == '_')
            && !ids.iter().any(|item| item == token)
        {
            ids.push(token.to_string());
        }
    }
    ids
}

fn is_feishu_card_action_event(event: &Value) -> bool {
    value_string(event, &["kind"]) == "card_action"
        || value_string(event, &["type"]) == "p2.card.action.trigger"
}

fn card_action_value(event: &Value) -> Value {
    event
        .get("actionValue")
        .or_else(|| event.get("action_value"))
        .cloned()
        .unwrap_or(Value::Null)
}

fn is_runtime_approval_required_event(event: &Value) -> bool {
    event.get("type").and_then(Value::as_str).unwrap_or("") == "approval_required"
}

fn approval_payload_from_runtime_event(event: &Value) -> Value {
    event.get("payload").cloned().unwrap_or(Value::Null)
}

fn approval_request_id_from_runtime_event(event: &Value) -> String {
    let payload = approval_payload_from_runtime_event(event);
    value_string(&payload, &["requestId", "request_id"])
}

fn send_bot_approval_card_for_runtime_event(
    context: &FeishuBotRuntimeContext,
    original_event: &Value,
    original_message_id: &str,
    chat_session_id: &str,
    project_id: &str,
    workspace_path: &str,
    user_message: &str,
    history: &[LocalChatMessage],
    runtime_event: &Value,
) -> Result<(), String> {
    let payload = approval_payload_from_runtime_event(runtime_event);
    let request_id = value_string(&payload, &["requestId", "request_id"]);
    if request_id.is_empty() {
        return Err("授权事件缺少 requestId".to_string());
    }
    let chat_id = value_string(original_event, &["chat_id", "chatId"]);
    if chat_id.is_empty() {
        return Err("授权事件缺少飞书 chat_id".to_string());
    }
    let card = feishu_bot_approval_card(
        &context.connector.connector_id,
        chat_session_id,
        &request_id,
        &payload,
        "",
    );
    let response = send_feishu_interactive_card(
        &context.connector.connector_id,
        &chat_id,
        card,
        format!("desktop-bot-approval-{request_id}").as_str(),
    )?;
    let approval_message_id = value_string(&response, &["message_id", "messageId"]);
    let pending = StoredBotPendingApproval {
        version: 1,
        connector_id: context.connector.connector_id.clone(),
        chat_session_id: chat_session_id.trim().to_string(),
        request_id: request_id.clone(),
        project_id: project_id.trim().to_string(),
        workspace_path: workspace_path.trim().to_string(),
        user_message: user_message.trim().to_string(),
        external_chat_id: chat_id,
        external_sender_id: value_string(original_event, &["sender_id", "senderId"]),
        external_message_id: original_message_id.trim().to_string(),
        thread_id: value_string(original_event, &["thread_id", "threadId"]),
        approval_message_id,
        approval_payload: payload,
        original_event: original_event.clone(),
        history: history.to_vec(),
        status: "pending".to_string(),
        updated_at_epoch_ms: epoch_millis(),
    };
    persist_bot_pending_approval(&pending)
}

fn feishu_bot_approval_card(
    connector_id: &str,
    chat_session_id: &str,
    request_id: &str,
    approval: &Value,
    resolved_label: &str,
) -> Value {
    let summary = approval_human_summary(approval);
    let title = if resolved_label.is_empty() {
        "需要你确认后继续"
    } else {
        resolved_label
    };
    let template = if resolved_label.contains("拒绝") || resolved_label.contains("取消") {
        "red"
    } else if resolved_label.is_empty() {
        "orange"
    } else {
        "green"
    };
    let mut lines = Vec::new();
    lines.push(format!(
        "**我要做什么**：{}",
        markdown_escape(&summary.purpose)
    ));
    lines.push(format!(
        "**为什么需要确认**：{}",
        markdown_escape(&summary.confirm_reason)
    ));
    if !summary.operation.is_empty() {
        lines.push(format!(
            "**操作内容**：`{}`",
            markdown_escape(&summary.operation)
        ));
    }
    if !summary.location.is_empty() {
        lines.push(format!(
            "**作用位置**：`{}`",
            markdown_escape(&summary.location)
        ));
    }
    if !summary.risk_label.is_empty() {
        lines.push(format!(
            "**风险级别**：{}",
            markdown_escape(&summary.risk_label)
        ));
    }
    if !resolved_label.is_empty() {
        lines.push(markdown_escape(resolved_label));
    } else {
        lines.push(
            "如果按钮提示应用尚未配置卡片回调，可以直接在本私聊回复 `本次授权`、`会话授权`、`完全授权` 或 `拒绝`。".to_string(),
        );
    }
    let content = lines.join("\n\n");
    if !resolved_label.is_empty() {
        return json!({
            "config": {"wide_screen_mode": true},
            "header": {
                "title": {"content": title, "tag": "plain_text"},
                "template": template
            },
            "elements": [{"tag": "markdown", "content": content}]
        });
    }
    json!({
        "config": {"wide_screen_mode": true},
        "header": {
            "title": {"content": title, "tag": "plain_text"},
            "template": template
        },
        "elements": [
            {"tag": "markdown", "content": content},
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "本次授权"},
                        "type": "primary",
                        "value": {
                            "ai_employee_action": "bot_permission",
                            "connector_id": connector_id,
                            "chat_session_id": chat_session_id,
                            "request_id": request_id,
                            "decision": "approve_once"
                        }
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "会话授权"},
                        "type": "default",
                        "value": {
                            "ai_employee_action": "bot_permission",
                            "connector_id": connector_id,
                            "chat_session_id": chat_session_id,
                            "request_id": request_id,
                            "decision": "approve_session"
                        }
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "完全授权"},
                        "type": "default",
                        "value": {
                            "ai_employee_action": "bot_permission",
                            "connector_id": connector_id,
                            "chat_session_id": chat_session_id,
                            "request_id": request_id,
                            "decision": "approve_full_access"
                        }
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "拒绝"},
                        "type": "danger",
                        "value": {
                            "ai_employee_action": "bot_permission",
                            "connector_id": connector_id,
                            "chat_session_id": chat_session_id,
                            "request_id": request_id,
                            "decision": "deny"
                        }
                    }
                ]
            }
        ]
    })
}

#[derive(Debug, Clone, Default)]
struct ApprovalHumanSummary {
    purpose: String,
    confirm_reason: String,
    operation: String,
    location: String,
    risk_label: String,
}

fn approval_human_summary(approval: &Value) -> ApprovalHumanSummary {
    let action = value_string(approval, &["action"]);
    let reason = value_string(approval, &["reason"]);
    let risk = value_string(approval, &["risk"]);
    let preview = approval.get("preview").cloned().unwrap_or(Value::Null);
    let cmd = value_string(&preview, &["cmd", "command"]);
    let path = value_string(&preview, &["path", "file_path", "filePath"]);
    let cwd = value_string(&preview, &["cwd", "working_dir", "workingDir"]);
    let url = value_string(&preview, &["url"]);
    let purpose = if action == "command.run" || !cmd.is_empty() {
        "我准备在你的电脑上执行一条本地命令，用它继续完成你刚才交给机器人的任务。".to_string()
    } else if action.contains("file.write") || action.contains("write") {
        "我准备修改或写入本地文件。".to_string()
    } else if action.contains("file.delete") || action.contains("delete") {
        "我准备删除本地文件。".to_string()
    } else if action.contains("network") || !url.is_empty() {
        "我准备访问网络资源。".to_string()
    } else {
        "我准备执行一步需要你确认的本地工具操作。".to_string()
    };
    let operation = first_value_string(
        [
            cmd,
            path,
            url,
            truncate_status_text(&reason.replace('\n', " "), 180),
        ],
        "",
    );
    let location = first_value_string(
        [
            cwd,
            value_string(&preview, &["workspace_path", "workspacePath"]),
            value_string(approval, &["scope"]),
        ],
        "",
    );
    let risk_label = match risk.as_str() {
        "high" => "高，需要特别确认".to_string(),
        "medium" => "中等，继续前需要确认".to_string(),
        "low" => "低".to_string(),
        value if !value.is_empty() => value.to_string(),
        _ => String::new(),
    };
    let confirm_reason = if !reason.is_empty() {
        reason
    } else if !risk_label.is_empty() {
        "这一步会使用桌面端本地 Runner 执行，继续前需要你的授权。".to_string()
    } else {
        "这一步会影响本机工作区或外部资源，继续前需要你的授权。".to_string()
    };
    ApprovalHumanSummary {
        purpose,
        confirm_reason,
        operation,
        location,
        risk_label,
    }
}

fn approval_status_message(runtime_event: &Value) -> String {
    let payload = approval_payload_from_runtime_event(runtime_event);
    let summary = approval_human_summary(&payload);
    let mut parts = vec![
        "我暂停在一个需要授权的步骤。".to_string(),
        format!("目的：{}", summary.purpose),
    ];
    if !summary.operation.is_empty() {
        parts.push(format!("操作：{}", summary.operation));
    }
    if !summary.location.is_empty() {
        parts.push(format!("位置：{}", summary.location));
    }
    parts.push("请确认是否继续。你可以点击卡片按钮；如果飞书提示应用尚未配置卡片回调，直接回复“确认”或“拒绝”。".to_string());
    parts.join("\n")
}

fn markdown_escape(value: &str) -> String {
    value.replace('\\', "\\\\").replace('`', "\\`")
}

fn handle_local_feishu_card_action(
    app: &AppHandle,
    status: &FeishuLocalListenerStatus,
    context: FeishuBotRuntimeContext,
    event: Value,
) -> Result<(), String> {
    let action_value = card_action_value(&event);
    if value_string(&action_value, &["ai_employee_action"]) != "bot_permission" {
        return Ok(());
    }
    let request_id = value_string(&action_value, &["request_id", "requestId"]);
    if request_id.is_empty() {
        return Err("飞书授权卡片缺少 request_id".to_string());
    }
    let action_connector_id = value_string(&action_value, &["connector_id", "connectorId"]);
    if !action_connector_id.is_empty()
        && action_connector_id != context.connector.connector_id.trim()
    {
        return Ok(());
    }
    let pending = load_bot_pending_approval(&context.connector.connector_id, &request_id)
        .ok_or_else(|| "找不到对应的飞书待授权记录，可能已过期或已处理".to_string())?;
    validate_card_action_matches_pending(&event, &pending)?;
    if pending.status.trim() != "pending" && pending.status.trim() != "failed" {
        emit_listener_status(app, status, "ignored", "飞书授权卡片已处理，忽略重复点击");
        return Ok(());
    }
    let decision = value_string(&action_value, &["decision"]);
    handle_pending_approval_decision(app, status, context, pending, decision.as_str(), "card")
}

fn handle_pending_approval_decision(
    app: &AppHandle,
    status: &FeishuLocalListenerStatus,
    context: FeishuBotRuntimeContext,
    mut pending: StoredBotPendingApproval,
    decision: &str,
    source: &str,
) -> Result<(), String> {
    if decision == "deny" {
        pending.status = "denied".to_string();
        pending.updated_at_epoch_ms = epoch_millis();
        persist_bot_pending_approval(&pending)?;
        update_pending_approval_card(&context, &pending, "已拒绝，操作已取消");
        if !pending.external_message_id.trim().is_empty() {
            let _ = reply_feishu_status_message(
                &context,
                &pending.original_event,
                &pending.external_message_id,
                "已取消本次需要授权的操作。",
                format!("approval-denied-{}", pending.request_id).as_str(),
            );
        }
        emit_listener_status(
            app,
            status,
            "approval_denied",
            "用户已在飞书拒绝本地工具操作",
        );
        return Ok(());
    }
    if !matches!(
        decision,
        "approve_once" | "approve_session" | "approve_full_access"
    ) {
        return Err(format!("未知的飞书授权决定：{decision}"));
    }
    pending.status = "resolving".to_string();
    pending.updated_at_epoch_ms = epoch_millis();
    persist_bot_pending_approval(&pending)?;
    update_pending_approval_card(
        &context,
        &pending,
        approval_resolved_label_for_decision(decision, true).as_str(),
    );
    if source == "text_reply" && !pending.external_message_id.trim().is_empty() {
        let _ = reply_feishu_status_message(
            &context,
            &pending.original_event,
            &pending.external_message_id,
            approval_text_reply_ack(decision).as_str(),
            format!("approval-confirmed-{}", pending.request_id).as_str(),
        );
    }
    emit_listener_status(
        app,
        status,
        "approval_resuming",
        "用户已在飞书确认，桌面智能体继续执行",
    );
    let result = resume_feishu_pending_approval(&context, &pending, decision, app, status);
    match result {
        Ok(reply_content) => {
            if decision == "approve_full_access" {
                persist_bot_full_access_grant(&StoredBotFullAccessGrant {
                    version: 1,
                    connector_id: context.connector.connector_id.clone(),
                    chat_session_id: pending.chat_session_id.clone(),
                    grant_scope: "session_full_access".to_string(),
                    source_request_id: pending.request_id.clone(),
                    updated_at_epoch_ms: epoch_millis(),
                })?;
            }
            pending.status = "approved".to_string();
            pending.updated_at_epoch_ms = epoch_millis();
            persist_bot_pending_approval(&pending)?;
            update_pending_approval_card(
                &context,
                &pending,
                approval_resolved_label_for_decision(decision, false).as_str(),
            );
            if !reply_content.trim().is_empty() {
                append_bot_conversation_turn(
                    &context.connector.connector_id,
                    &pending.chat_session_id,
                    &pending.user_message,
                    &reply_content,
                )?;
            }
            emit_listener_status(
                app,
                status,
                "approval_completed",
                "飞书授权后的桌面智能体执行已完成",
            );
            Ok(())
        }
        Err(error) => {
            pending.status = "failed".to_string();
            pending.updated_at_epoch_ms = epoch_millis();
            persist_bot_pending_approval(&pending)?;
            update_pending_approval_card(&context, &pending, "已确认，但继续执行失败");
            Err(error)
        }
    }
}

fn validate_card_action_matches_pending(
    event: &Value,
    pending: &StoredBotPendingApproval,
) -> Result<(), String> {
    let chat_id = value_string(event, &["chat_id", "chatId"]);
    if !chat_id.is_empty()
        && !pending.external_chat_id.trim().is_empty()
        && chat_id != pending.external_chat_id
    {
        return Err("飞书授权卡片来源会话不匹配".to_string());
    }
    let operator_id = value_string(event, &["operator_id", "operatorId"]);
    if !operator_id.is_empty()
        && !pending.external_sender_id.trim().is_empty()
        && operator_id != pending.external_sender_id
    {
        return Err("飞书授权点击人不是原始请求人".to_string());
    }
    Ok(())
}

fn runtime_permission_decision_parts(decision: &str) -> (String, Option<String>) {
    match decision {
        "approve_session" => ("approve_session".to_string(), Some("session".to_string())),
        "approve_full_access" => (
            "approve_session".to_string(),
            Some("session_full_access".to_string()),
        ),
        _ => ("approve_once".to_string(), Some("once".to_string())),
    }
}

fn approval_resolved_label_for_decision(decision: &str, in_progress: bool) -> String {
    match (decision, in_progress) {
        ("approve_session", true) => "已选择会话授权，正在继续执行".to_string(),
        ("approve_session", false) => "已会话授权，操作已继续执行".to_string(),
        ("approve_full_access", true) => "已选择完全授权，正在继续执行".to_string(),
        ("approve_full_access", false) => "已完全授权，后续本会话工具操作将自动继续".to_string(),
        (_, true) => "已确认本次授权，正在继续执行".to_string(),
        _ => "已确认本次授权，操作已继续执行".to_string(),
    }
}

fn approval_text_reply_ack(decision: &str) -> String {
    match decision {
        "approve_session" => "已收到会话授权，正在继续刚才等待授权的操作。".to_string(),
        "approve_full_access" => {
            "已收到完全授权，正在继续；后续本会话工具操作会自动授权。".to_string()
        }
        _ => "已收到本次授权，正在继续刚才等待授权的操作。".to_string(),
    }
}

fn resume_feishu_pending_approval(
    context: &FeishuBotRuntimeContext,
    pending: &StoredBotPendingApproval,
    decision: &str,
    app: &AppHandle,
    status: &FeishuLocalListenerStatus,
) -> Result<String, String> {
    let (runtime_decision, runtime_grant_scope) = runtime_permission_decision_parts(decision);
    let permission_decision = PermissionDecisionInput {
        request_id: Some(pending.request_id.clone()),
        decision: runtime_decision,
        grant_scope: runtime_grant_scope,
        comment: Some("feishu_bot_card".to_string()),
    };
    let request = BotChatRequest {
        project_id: pending.project_id.clone(),
        chat_session_id: pending.chat_session_id.clone(),
        message_id: Some(pending.external_message_id.clone()),
        assistant_message_id: Some(format!("bot-local-approval-{}", epoch_millis())),
        message: pending.user_message.clone(),
        workspace_path: pending.workspace_path.clone(),
        history: pending.history.clone(),
        connector: context.connector.clone(),
        source_context: BotSourceContext {
            source_type: "private_message".to_string(),
            external_chat_id: pending.external_chat_id.clone(),
            external_chat_name: String::new(),
            external_message_id: pending.external_message_id.clone(),
            thread_id: pending.thread_id.clone(),
            raw: pending.original_event.clone(),
        },
        permission_contract: None,
        provider_id: Some(context.connector.provider_id.clone()),
        model_name: Some(context.connector.model_name.clone()),
        model_runtime: context.model_runtime.clone(),
        attachments: Vec::new(),
        mcp_config: context.mcp_config.clone(),
        backend_context: context.backend_context.clone(),
        permission_decision: Some(permission_decision),
    };
    let context_for_events = context.clone();
    let pending_for_events = pending.clone();
    let approval_card_sent = Arc::new(Mutex::new(false));
    let approval_card_sent_for_events = approval_card_sent.clone();
    let result = crate::bot::start_bot_chat_with_event_sink(request, |event| {
        let _ = app.emit("bot-runtime-event", event.clone());
        let _ = app.emit("bot://runtime-event", event.clone());
        if is_runtime_approval_required_event(&event) {
            let _ = reply_feishu_status_message(
                &context_for_events,
                &pending_for_events.original_event,
                &pending_for_events.external_message_id,
                approval_status_message(&event).as_str(),
                format!(
                    "approval-status-{}",
                    approval_request_id_from_runtime_event(&event)
                )
                .as_str(),
            );
            if send_bot_approval_card_for_runtime_event(
                &context_for_events,
                &pending_for_events.original_event,
                &pending_for_events.external_message_id,
                &pending_for_events.chat_session_id,
                &pending_for_events.project_id,
                &pending_for_events.workspace_path,
                &pending_for_events.user_message,
                &pending_for_events.history,
                &event,
            )
            .is_ok()
            {
                let _ = approval_card_sent_for_events
                    .lock()
                    .map(|mut sent| *sent = true);
            }
            return;
        }
        let Some((progress_key, progress_content)) = bot_progress_reply_for_runtime_event(&event)
        else {
            return;
        };
        if let Err(error) = reply_feishu_status_message(
            &context_for_events,
            &pending_for_events.original_event,
            &pending_for_events.external_message_id,
            progress_content.as_str(),
            format!("approval-{progress_key}-{}", pending_for_events.request_id).as_str(),
        ) {
            emit_listener_status(
                app,
                status,
                "warning",
                format!("飞书授权恢复进度消息发送失败：{error}").as_str(),
            );
        }
    });
    if !result.ok {
        let waiting_for_next_feishu_approval = result.error_code.trim() == "permission.required"
            && approval_card_sent.lock().map(|sent| *sent).unwrap_or(false);
        if waiting_for_next_feishu_approval {
            return Ok(String::new());
        }
        let failure = bot_safe_failure_reply(&result);
        if !pending.external_message_id.trim().is_empty() {
            let _ = reply_feishu_status_message(
                context,
                &pending.original_event,
                &pending.external_message_id,
                failure.as_str(),
                format!("approval-failed-{}", pending.request_id).as_str(),
            );
        }
        return Err(format!(
            "授权后继续执行失败：{}",
            bot_result_status_summary(&result)
        ));
    }
    let reply_content = bot_reply_content(&result);
    if !reply_content.trim().is_empty() {
        reply_message_with_connector(
            &context.connector.connector_id,
            FeishuLocalReplyRequest {
                connector_id: context.connector.connector_id.clone(),
                message_id: pending.external_message_id.clone(),
                content: reply_content.clone(),
                content_format: "text".to_string(),
                reply_identity: context.connector.reply_identity.clone(),
                reply_in_thread: !pending.thread_id.trim().is_empty(),
                idempotency_key: format!("desktop-bot-approval-reply-{}", pending.request_id),
            },
        )?;
    }
    Ok(reply_content)
}

fn update_pending_approval_card(
    context: &FeishuBotRuntimeContext,
    pending: &StoredBotPendingApproval,
    resolved_label: &str,
) {
    if pending.approval_message_id.trim().is_empty() {
        return;
    }
    let card = feishu_bot_approval_card(
        &context.connector.connector_id,
        &pending.chat_session_id,
        &pending.request_id,
        &pending.approval_payload,
        resolved_label,
    );
    let _ = update_feishu_interactive_card(
        &context.connector.connector_id,
        &pending.approval_message_id,
        card,
    );
}

fn bot_pending_approval_path(connector_id: &str, request_id: &str) -> Result<PathBuf, String> {
    let dir = global_bot_pending_approval_dir()?;
    let file_name = format!(
        "{}__{}.json",
        sanitize_id(connector_id),
        sanitize_id(request_id)
    );
    Ok(dir.join(file_name))
}

fn load_bot_pending_approval(
    connector_id: &str,
    request_id: &str,
) -> Option<StoredBotPendingApproval> {
    let path = bot_pending_approval_path(connector_id, request_id).ok()?;
    let raw = std::fs::read_to_string(path).ok()?;
    serde_json::from_str::<StoredBotPendingApproval>(&raw).ok()
}

fn load_latest_pending_approval_for_chat(
    connector_id: &str,
    chat_id: &str,
    sender_id: &str,
) -> Option<StoredBotPendingApproval> {
    let dir = global_bot_pending_approval_dir().ok()?;
    let prefix = format!("{}__", sanitize_id(connector_id));
    std::fs::read_dir(dir)
        .ok()?
        .filter_map(Result::ok)
        .filter(|entry| {
            entry
                .file_name()
                .to_string_lossy()
                .starts_with(prefix.as_str())
        })
        .filter_map(|entry| std::fs::read_to_string(entry.path()).ok())
        .filter_map(|raw| serde_json::from_str::<StoredBotPendingApproval>(&raw).ok())
        .filter(|pending| {
            matches!(pending.status.trim(), "pending" | "failed")
                && pending.connector_id.trim() == connector_id.trim()
                && pending.external_chat_id.trim() == chat_id.trim()
                && (pending.external_sender_id.trim().is_empty()
                    || sender_id.trim().is_empty()
                    || pending.external_sender_id.trim() == sender_id.trim())
        })
        .max_by_key(|pending| pending.updated_at_epoch_ms)
}

fn text_permission_decision(message: &str) -> Option<String> {
    let normalized = message
        .trim()
        .trim_matches(|ch: char| ch.is_ascii_punctuation() || ch.is_whitespace())
        .to_ascii_lowercase();
    if normalized.is_empty() {
        return None;
    }
    if matches!(
        normalized.as_str(),
        "会话授权" | "本会话批准" | "本会话授权" | "本会话" | "approve_session" | "session"
    ) {
        return Some("approve_session".to_string());
    }
    if matches!(
        normalized.as_str(),
        "完全授权" | "完全访问" | "full_access" | "approve_full_access" | "full"
    ) {
        return Some("approve_full_access".to_string());
    }
    if matches!(
        normalized.as_str(),
        "确认"
            | "同意"
            | "允许"
            | "继续"
            | "执行"
            | "确认执行"
            | "可以"
            | "approve"
            | "approved"
            | "yes"
            | "y"
            | "ok"
    ) {
        return Some("approve_once".to_string());
    }
    if matches!(
        normalized.as_str(),
        "拒绝" | "取消" | "不同意" | "不要" | "不执行" | "deny" | "denied" | "no" | "n"
    ) {
        return Some("deny".to_string());
    }
    None
}

fn persist_bot_pending_approval(pending: &StoredBotPendingApproval) -> Result<(), String> {
    let path = bot_pending_approval_path(&pending.connector_id, &pending.request_id)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|err| format!("无法创建飞书机器人授权确认目录 {}：{err}", parent.display()))?;
    }
    let content = serde_json::to_string_pretty(pending)
        .map_err(|err| format!("无法序列化飞书机器人授权确认记录：{err}"))?;
    std::fs::write(&path, content)
        .map_err(|err| format!("无法写入飞书机器人授权确认记录 {}：{err}", path.display()))
}

fn bot_full_access_grant_path(
    connector_id: &str,
    chat_session_id: &str,
) -> Result<PathBuf, String> {
    let dir = global_bot_full_access_grant_dir()?;
    let file_name = format!(
        "{}__{}.json",
        sanitize_id(connector_id),
        sanitize_id(chat_session_id)
    );
    Ok(dir.join(file_name))
}

fn load_bot_full_access_grant(
    connector_id: &str,
    chat_session_id: &str,
) -> Option<StoredBotFullAccessGrant> {
    let path = bot_full_access_grant_path(connector_id, chat_session_id).ok()?;
    let raw = std::fs::read_to_string(path).ok()?;
    let grant = serde_json::from_str::<StoredBotFullAccessGrant>(&raw).ok()?;
    if grant.connector_id.trim() == connector_id.trim()
        && grant.chat_session_id.trim() == chat_session_id.trim()
        && matches!(
            grant.grant_scope.trim(),
            "session_full_access" | "full_access" | "workspace_full_access"
        )
    {
        Some(grant)
    } else {
        None
    }
}

fn persist_bot_full_access_grant(grant: &StoredBotFullAccessGrant) -> Result<(), String> {
    let path = bot_full_access_grant_path(&grant.connector_id, &grant.chat_session_id)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|err| format!("无法创建飞书机器人完全授权目录 {}：{err}", parent.display()))?;
    }
    let content = serde_json::to_string_pretty(grant)
        .map_err(|err| format!("无法序列化飞书机器人完全授权记录：{err}"))?;
    std::fs::write(&path, content)
        .map_err(|err| format!("无法写入飞书机器人完全授权记录 {}：{err}", path.display()))
}

fn bot_full_access_permission_decision(
    connector_id: &str,
    chat_session_id: &str,
) -> Option<PermissionDecisionInput> {
    let grant = load_bot_full_access_grant(connector_id, chat_session_id)?;
    Some(PermissionDecisionInput {
        request_id: None,
        decision: "approve_session".to_string(),
        grant_scope: Some(grant.grant_scope),
        comment: Some("feishu_bot_full_access".to_string()),
    })
}

fn bot_progress_reply_for_runtime_event(event: &Value) -> Option<(String, String)> {
    let payload = event.get("payload").unwrap_or(&Value::Null);
    match event.get("type").and_then(Value::as_str).unwrap_or("") {
        "plan_created" | "plan_updated" | "plan_completed" => {
            let steps = payload
                .get("steps")
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default();
            if steps.is_empty() {
                return None;
            }
            let lines = steps
                .iter()
                .map(|step| {
                    let status = value_string(step, &["status"]);
                    let marker = match status.as_str() {
                        "completed" | "done" | "skipped" => "✓",
                        "running" | "in_progress" | "verifying" => "◉",
                        "blocked" | "failed" => "!",
                        _ => "□",
                    };
                    let title = value_string(step, &["title"]);
                    format!("{marker} {}", truncate_status_text(&title, 60))
                })
                .collect::<Vec<_>>()
                .join("\n");
            Some((
                "plan-progress".to_string(),
                format!("Updated Plan\n{lines}"),
            ))
        }
        "model_call_started" => Some((
            "model-started".to_string(),
            "正在调用模型处理。".to_string(),
        )),
        "progress_update" => {
            let summary = value_string(payload, &["summary"]);
            if summary.is_empty() {
                Some(("progress".to_string(), "正在推进处理。".to_string()))
            } else {
                Some((
                    "progress".to_string(),
                    format!("正在处理：{}", truncate_status_text(&summary, 80)),
                ))
            }
        }
        "tool_call_started" => {
            let tool_name = value_string(payload, &["tool_name"]);
            let summary = value_string(payload, &["summary"]);
            let label = if summary.is_empty() {
                tool_name.as_str()
            } else {
                summary.as_str()
            };
            if label.trim().is_empty() {
                Some((
                    "tool-started".to_string(),
                    "正在使用桌面工具处理。".to_string(),
                ))
            } else {
                Some((
                    format!("tool-{}", sanitize_id(tool_name.as_str())),
                    format!("正在使用工具：{}", truncate_status_text(label, 60)),
                ))
            }
        }
        "approval_required" => None,
        _ => None,
    }
}

fn bot_reply_content(result: &LocalChatResult) -> String {
    if !result.ok {
        return String::new();
    }
    result.assistant_content.trim().to_string()
}

fn bot_safe_failure_reply(result: &LocalChatResult) -> String {
    let status = bot_result_status_summary(result);
    if result.error_code.trim() == "permission.required" {
        return "需要在桌面端确认权限后才能继续处理。".to_string();
    }
    if status.trim().is_empty() || status == "unknown" {
        "处理失败，请在桌面端查看机器人运行状态后重试。".to_string()
    } else {
        format!(
            "处理未完成：{}",
            truncate_status_text(&status.replace('\n', " "), 120)
        )
    }
}

fn truncate_status_text(value: &str, max_chars: usize) -> String {
    let normalized = value.split_whitespace().collect::<Vec<_>>().join(" ");
    let mut truncated = normalized.chars().take(max_chars).collect::<String>();
    if normalized.chars().count() > max_chars {
        truncated.push_str("...");
    }
    truncated
}

fn bot_result_status_summary(result: &LocalChatResult) -> String {
    first_value_string(
        [
            result.user_visible_error_summary.clone(),
            result.summary.clone(),
            result.error.clone(),
            result.error_code.clone(),
        ],
        "unknown",
    )
}

fn first_value_string(values: impl IntoIterator<Item = String>, fallback: &str) -> String {
    values
        .into_iter()
        .map(|value| value.trim().to_string())
        .find(|value| !value.is_empty())
        .unwrap_or_else(|| fallback.to_string())
}

fn bot_chat_session_id(connector_id: &str, event: &Value) -> String {
    let chat_id = value_string(event, &["chat_id", "chatId"]);
    let sender_id = value_string(event, &["sender_id", "senderId"]);
    let source = first_value_string(
        [
            chat_id,
            sender_id,
            value_string(event, &["message_id", "messageId", "id"]),
        ],
        "unknown",
    );
    format!(
        "bot-feishu-{}-{}",
        sanitize_id(connector_id),
        sanitize_id(source.as_str())
    )
}

fn sanitize_id(value: &str) -> String {
    let normalized = value
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || ch == '-' || ch == '_' {
                ch
            } else {
                '-'
            }
        })
        .collect::<String>()
        .trim_matches('-')
        .to_string();
    if normalized.is_empty() {
        "unknown".to_string()
    } else {
        normalized
    }
}

fn spawn_stderr_forwarder(
    app: AppHandle,
    status: FeishuLocalListenerStatus,
    stderr: impl std::io::Read + Send + 'static,
) {
    thread::spawn(move || {
        let reader = BufReader::new(stderr);
        for line in reader.lines().map_while(Result::ok) {
            let text = line.trim();
            if text.is_empty() {
                continue;
            }
            if text.contains("[event] ready") || text.contains("[feishu-sdk] ready") {
                emit_listener_status(&app, &status, "ready", text);
                continue;
            }
            if text.starts_with('{') {
                emit_listener_status(&app, &status, "error", text);
            }
            let payload = json!({
                "connectorId": status.connector_id.as_str(),
                "projectId": status.project_id.as_str(),
                "chatSessionId": status.chat_session_id.as_str(),
                "workspacePath": status.workspace_path.as_str(),
                "message": text,
                "source": "tauri_feishu_local_listener"
            });
            let _ = app.emit("bot-feishu-local-status", payload.clone());
            let _ = app.emit("bot://feishu-local-status", payload);
        }
        let _ = listener_store()
            .lock()
            .map(|mut store| store.remove(status.connector_id.as_str()));
        emit_listener_status(&app, &status, "exited", "飞书本地监听已退出");
    });
}

fn emit_listener_status(
    app: &AppHandle,
    status: &FeishuLocalListenerStatus,
    state: &str,
    message: &str,
) {
    let payload = json!({
        "connectorId": status.connector_id.as_str(),
        "projectId": status.project_id.as_str(),
        "chatSessionId": status.chat_session_id.as_str(),
        "workspacePath": status.workspace_path.as_str(),
        "state": state,
        "message": message,
        "source": "tauri_feishu_local_listener"
    });
    append_listener_log(json!({
        "kind": "status",
        "connectorId": status.connector_id.as_str(),
        "state": state,
        "message": message
    }));
    let _ = app.emit("bot-feishu-local-status", payload.clone());
    let _ = app.emit("bot://feishu-local-status", payload);
}

fn extract_chat_items(payload: &Value) -> Vec<Value> {
    if let Some(items) = payload.get("chats").and_then(Value::as_array) {
        return items.clone();
    }
    if let Some(items) = payload.pointer("/data/items").and_then(Value::as_array) {
        return items.clone();
    }
    if let Some(items) = payload.get("items").and_then(Value::as_array) {
        return items.clone();
    }
    if let Some(items) = payload.pointer("/data/chats").and_then(Value::as_array) {
        return items.clone();
    }
    Vec::new()
}

fn extract_array_field(payload: &Value, key: &str) -> Vec<Value> {
    payload
        .get(key)
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default()
}

fn extract_next_page_token(payload: &Value) -> String {
    [
        "/page_token",
        "/next_page_token",
        "/data/page_token",
        "/data/next_page_token",
    ]
    .iter()
    .find_map(|pointer| payload.pointer(pointer).and_then(Value::as_str))
    .unwrap_or("")
    .trim()
    .to_string()
}

fn safe_resource_filename(message_id: &str, file_key: &str, resource_type: &str) -> String {
    let sanitize = |value: &str| {
        value
            .chars()
            .map(|ch| {
                if ch.is_ascii_alphanumeric() || matches!(ch, '-' | '_' | '.') {
                    ch
                } else {
                    '_'
                }
            })
            .collect::<String>()
    };
    format!(
        "{}-{}-{}",
        sanitize(resource_type),
        sanitize(message_id),
        sanitize(file_key)
    )
}

fn resolve_downloaded_resource_path(root: &PathBuf, output_name: &str, stdout: &str) -> PathBuf {
    if let Ok(payload) = serde_json::from_str::<Value>(stdout) {
        for pointer in [
            "/local_path",
            "/path",
            "/file_path",
            "/data/local_path",
            "/data/path",
        ] {
            if let Some(path) = payload.pointer(pointer).and_then(Value::as_str) {
                let candidate = PathBuf::from(path);
                return if candidate.is_absolute() {
                    candidate
                } else {
                    root.join(candidate)
                };
            }
        }
    }
    root.join(output_name)
}

fn infer_resource_mime_type(path: &PathBuf, resource_type: &str) -> &'static str {
    let extension = path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    match extension.as_str() {
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "gif" => "image/gif",
        "webp" => "image/webp",
        "pdf" => "application/pdf",
        "txt" | "md" => "text/plain",
        "csv" => "text/csv",
        "json" => "application/json",
        _ if resource_type == "image" => "image/png",
        _ => "application/octet-stream",
    }
}

fn epoch_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::{
        append_bot_conversation_messages, approval_request_id_from_runtime_event,
        bot_progress_reply_for_runtime_event, bot_project_binding_from_project_content,
        bot_project_binding_from_runtime_event, bot_reply_content, card_action_value,
        connector_model_runtime, epoch_millis, extract_chat_items, extract_next_page_token,
        feishu_bot_approval_card, is_feishu_card_action_event, is_runtime_approval_required_event,
        project_ids_from_text, runtime_permission_decision_parts, safe_resource_filename,
        should_handle_event, text_permission_decision, trim_bot_conversation_history,
        validate_card_action_matches_pending, StoredBotPendingApproval,
    };
    use crate::bot::types::BotConnectorConfig;
    use crate::liuagent_core::{LocalChatMessage, LocalChatResult, ToolError};
    use serde_json::json;

    fn test_connector() -> BotConnectorConfig {
        BotConnectorConfig {
            connector_id: "feishu-test-bot".to_string(),
            platform: "feishu".to_string(),
            name: "测试机器人".to_string(),
            ..Default::default()
        }
    }

    #[test]
    fn plan_progress_uses_shared_step_statuses() {
        let event = json!({
            "type": "plan_updated",
            "payload": {
                "steps": [
                    {"title": "分析", "status": "completed"},
                    {"title": "实现", "status": "running"},
                    {"title": "验证", "status": "pending"}
                ]
            }
        });

        let (_, content) = bot_progress_reply_for_runtime_event(&event).unwrap();
        assert_eq!(content, "Updated Plan\n✓ 分析\n◉ 实现\n□ 验证");
    }

    #[test]
    fn extracts_chat_items_from_common_lark_shapes() {
        assert_eq!(
            extract_chat_items(&json!({"data": {"items": [{"chat_id": "oc_1"}]}})).len(),
            1
        );
        assert_eq!(
            extract_chat_items(&json!({"data": {"chats": [{"chat_id": "oc_2"}]}}))[0]["chat_id"],
            "oc_2"
        );
    }

    #[test]
    fn extracts_next_page_token_from_common_lark_shapes() {
        assert_eq!(
            extract_next_page_token(&json!({"data": {"page_token": " next "}})),
            "next"
        );
        assert_eq!(
            extract_next_page_token(&json!({"next_page_token": "n2"})),
            "n2"
        );
    }

    #[test]
    fn resource_filename_is_sanitized() {
        assert_eq!(
            safe_resource_filename("om/1", "img:abc", "image"),
            "image-om_1-img_abc"
        );
    }

    #[test]
    fn p2p_messages_are_handled() {
        assert!(should_handle_event(
            &test_connector(),
            &json!({
                "chat_type": "p2p",
                "content": "你好"
            }),
        ));
    }

    #[test]
    fn group_messages_are_ignored_even_when_mentioned_or_name_matched() {
        assert!(!should_handle_event(
            &test_connector(),
            &json!({
                "chat_type": "group",
                "content": "@测试机器人 帮我处理",
                "mentions": [{
                    "type": "bot",
                    "mention_name": "测试机器人"
                }]
            }),
        ));
    }

    #[test]
    fn failed_bot_result_has_no_feishu_reply_content() {
        let result = LocalChatResult::failed(
            "chat-1".to_string(),
            ToolError::new(
                "bot.model_runtime_unconfigured",
                "机器人未配置可用的桌面模型运行时，已跳过回复。",
            ),
        );

        assert_eq!(bot_reply_content(&result), "");
    }

    #[test]
    fn bot_conversation_history_keeps_only_final_user_assistant_turns() {
        let mut messages = vec![LocalChatMessage {
            role: "assistant".to_string(),
            content: "正在调用模型处理。".to_string(),
            reasoning_content: None,
            source_kind: Some("progress".to_string()),
            diagnostic: Some(true),
            visibility: Some("status".to_string()),
        }];

        append_bot_conversation_messages(
            &mut messages,
            "展示项目名字有 浩的",
            "找到 1 个项目：浩成CRM，项目 ID：proj-b786c6f1",
            20,
        );
        append_bot_conversation_messages(&mut messages, "展示这个项目路径", "路径：/crm", 20);

        assert_eq!(messages.len(), 4);
        assert_eq!(messages[0].role, "user");
        assert!(messages[1].content.contains("浩成CRM"));
        assert_eq!(messages[2].content, "展示这个项目路径");
        assert!(!messages
            .iter()
            .any(|item| item.content.contains("正在调用模型处理")));
    }

    #[test]
    fn bot_conversation_history_is_trimmed_to_recent_messages() {
        let messages = (0..8)
            .map(|index| LocalChatMessage {
                role: if index % 2 == 0 { "user" } else { "assistant" }.to_string(),
                content: format!("m{index}"),
                reasoning_content: None,
                source_kind: None,
                diagnostic: None,
                visibility: None,
            })
            .collect::<Vec<_>>();

        let trimmed = trim_bot_conversation_history(messages, 4);
        assert_eq!(trimmed.len(), 4);
        assert_eq!(trimmed[0].content, "m4");
        assert_eq!(trimmed[3].content, "m7");
    }

    #[test]
    fn project_ids_are_extracted_from_previous_bot_text() {
        let ids = project_ids_from_text("项目 ID：`proj-b786c6f1`，名称：浩成CRM");
        assert_eq!(ids, vec!["proj-b786c6f1"]);
    }

    #[test]
    fn project_binding_requires_backend_project_workspace() {
        let workspace = std::env::temp_dir().join(format!("feishu-binding-{}", epoch_millis()));
        std::fs::create_dir_all(&workspace).expect("workspace dir");
        let binding = bot_project_binding_from_project_content(
            "feishu-test-bot",
            "chat-1",
            &json!({
                "response": {
                    "project": {
                        "id": "proj-b786c6f1",
                        "name": "浩成CRM",
                        "workspace_path": workspace.to_string_lossy()
                    }
                }
            }),
        )
        .expect("project binding");

        assert_eq!(binding.project_id, "proj-b786c6f1");
        assert_eq!(binding.project_name, "浩成CRM");
        assert_eq!(binding.workspace_path, workspace.to_string_lossy());
        let _ = std::fs::remove_dir_all(workspace);
    }

    #[test]
    fn project_binding_is_discovered_from_get_project_tool_result_event() {
        let workspace =
            std::env::temp_dir().join(format!("feishu-binding-event-{}", epoch_millis()));
        std::fs::create_dir_all(&workspace).expect("workspace dir");
        let binding = bot_project_binding_from_runtime_event(
            "feishu-test-bot",
            "chat-1",
            &json!({
                "type": "tool_result",
                "payload": {
                    "tool_name": "get_project",
                    "ok": true,
                    "content": {
                        "response": {
                            "project": {
                                "id": "proj-b786c6f1",
                                "name": "浩成CRM",
                                "workspace_path": workspace.to_string_lossy()
                            }
                        }
                    }
                }
            }),
        )
        .expect("project binding");

        assert_eq!(binding.project_id, "proj-b786c6f1");
        assert_eq!(binding.workspace_path, workspace.to_string_lossy());
        let _ = std::fs::remove_dir_all(workspace);
    }

    #[test]
    fn parses_connector_embedded_model_runtime() {
        let runtime = connector_model_runtime(&json!({
            "modelRuntime": {
                "mode": "direct-openai-compatible",
                "providerId": "lmp-1",
                "modelName": "gpt-test",
                "baseUrl": "https://example.com/v1",
                "apiKey": "sk-test"
            }
        }))
        .expect("connector runtime should parse");

        assert_eq!(runtime.mode.as_deref(), Some("direct-openai-compatible"));
        assert_eq!(runtime.provider_id.as_deref(), Some("lmp-1"));
        assert_eq!(runtime.model_name.as_deref(), Some("gpt-test"));
        assert_eq!(runtime.base_url.as_deref(), Some("https://example.com/v1"));
        assert_eq!(runtime.api_key.as_deref(), Some("sk-test"));
    }

    #[test]
    fn approval_card_contains_permission_action_values() {
        let card = feishu_bot_approval_card(
            "feishu-test-bot",
            "chat-1",
            "perm_call_run_command_run",
            &json!({
                "requestId": "perm_call_run_command_run",
                "action": "command.run",
                "risk": "high",
                "scope": "workspace",
                "tool_name": "run_command",
                "preview": {"command": "npm test"}
            }),
            "",
        );
        let actions = card["elements"][1]["actions"].as_array().expect("actions");

        assert_eq!(actions[0]["value"]["ai_employee_action"], "bot_permission");
        assert_eq!(actions[0]["value"]["decision"], "approve_once");
        assert_eq!(actions[1]["value"]["decision"], "approve_session");
        assert_eq!(actions[2]["value"]["decision"], "approve_full_access");
        assert_eq!(actions[3]["value"]["decision"], "deny");
        assert_eq!(
            actions[0]["value"]["request_id"],
            "perm_call_run_command_run"
        );
        let content = card["elements"][0]["content"].as_str().unwrap_or("");
        assert!(content.contains("我要做什么"));
        assert!(content.contains("直接在本私聊回复 `本次授权`、`会话授权`、`完全授权` 或 `拒绝`"));
        assert!(!content.contains("\"cmd\""));
    }

    #[test]
    fn text_permission_decision_supports_confirm_and_deny_fallbacks() {
        assert_eq!(
            text_permission_decision("确认").as_deref(),
            Some("approve_once")
        );
        assert_eq!(
            text_permission_decision("ok").as_deref(),
            Some("approve_once")
        );
        assert_eq!(
            text_permission_decision("会话授权").as_deref(),
            Some("approve_session")
        );
        assert_eq!(
            text_permission_decision("完全授权").as_deref(),
            Some("approve_full_access")
        );
        assert_eq!(text_permission_decision("拒绝").as_deref(), Some("deny"));
        assert_eq!(text_permission_decision("普通消息"), None);
    }

    #[test]
    fn full_access_decision_maps_to_runtime_session_full_access() {
        let (decision, grant_scope) = runtime_permission_decision_parts("approve_full_access");
        assert_eq!(decision, "approve_session");
        assert_eq!(grant_scope.as_deref(), Some("session_full_access"));

        let (decision, grant_scope) = runtime_permission_decision_parts("approve_session");
        assert_eq!(decision, "approve_session");
        assert_eq!(grant_scope.as_deref(), Some("session"));
    }

    #[test]
    fn card_action_and_runtime_approval_events_are_detected() {
        let card_event = json!({
            "kind": "card_action",
            "actionValue": {
                "ai_employee_action": "bot_permission",
                "request_id": "perm_1",
                "decision": "approve_once"
            }
        });
        let runtime_event = json!({
            "type": "approval_required",
            "payload": {"requestId": "perm_1"}
        });

        assert!(is_feishu_card_action_event(&card_event));
        assert_eq!(card_action_value(&card_event)["decision"], "approve_once");
        assert!(is_runtime_approval_required_event(&runtime_event));
        assert_eq!(
            approval_request_id_from_runtime_event(&runtime_event),
            "perm_1"
        );
    }

    #[test]
    fn card_action_must_match_pending_chat_and_sender() {
        let pending = StoredBotPendingApproval {
            external_chat_id: "oc_1".to_string(),
            external_sender_id: "ou_1".to_string(),
            ..Default::default()
        };
        assert!(validate_card_action_matches_pending(
            &json!({"chat_id": "oc_1", "operator_id": "ou_1"}),
            &pending,
        )
        .is_ok());
        assert!(validate_card_action_matches_pending(
            &json!({"chat_id": "oc_2", "operator_id": "ou_1"}),
            &pending,
        )
        .is_err());
        assert!(validate_card_action_matches_pending(
            &json!({"chat_id": "oc_1", "operator_id": "ou_2"}),
            &pending,
        )
        .is_err());
    }
}
