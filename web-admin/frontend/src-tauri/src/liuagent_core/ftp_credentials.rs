//! Desktop-global FTP credentials used by local deploy tools.
//!
//! Project deploy settings only store credential IDs. Actual host/user/password
//! values live in this desktop runtime file, not in the project catalog.

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::HashSet;
use std::env;
use std::fs;
use std::path::PathBuf;

use super::paths::{desktop_runtime_root, ensure_desktop_runtime_migrated};

pub const FTP_CREDENTIALS_VERSION: u32 = 1;
const MAX_FTP_CREDENTIALS: usize = 200;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DesktopFtpCredentials {
    #[serde(default = "default_ftp_credentials_version")]
    pub version: u32,
    #[serde(default)]
    pub credentials: Vec<Value>,
}

impl Default for DesktopFtpCredentials {
    fn default() -> Self {
        Self {
            version: FTP_CREDENTIALS_VERSION,
            credentials: Vec::new(),
        }
    }
}

pub fn global_ftp_credentials_path() -> Result<PathBuf, String> {
    let home = env::var_os("HOME")
        .map(PathBuf::from)
        .ok_or_else(|| "缺少 HOME，无法定位全局 FTP 连接".to_string())?;
    ensure_desktop_runtime_migrated(&home)
        .map_err(|err| format!("迁移旧全局桌面 Runtime 数据失败：{err}"))?;
    Ok(desktop_runtime_root(&home).join("ftp-credentials.json"))
}

pub fn read_global_ftp_credentials() -> Result<DesktopFtpCredentials, String> {
    let path = global_ftp_credentials_path()?;
    if !path.exists() {
        return Ok(DesktopFtpCredentials::default());
    }
    if !path.is_file() {
        return Err("全局 FTP 连接路径不是文件".to_string());
    }
    let content =
        fs::read_to_string(&path).map_err(|err| format!("无法读取全局 FTP 连接：{err}"))?;
    parse_ftp_credentials_content(&content)
}

pub fn write_global_ftp_credentials(
    credentials: DesktopFtpCredentials,
) -> Result<DesktopFtpCredentials, String> {
    let normalized = normalize_ftp_credentials(credentials)?;
    let path = global_ftp_credentials_path()?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|err| format!("无法创建全局 FTP 连接目录：{err}"))?;
    }
    let content = serde_json::to_string_pretty(&normalized)
        .map_err(|err| format!("无法序列化全局 FTP 连接：{err}"))?;
    fs::write(&path, format!("{content}\n"))
        .map_err(|err| format!("无法写入全局 FTP 连接：{err}"))?;
    Ok(normalized)
}

pub fn parse_ftp_credentials_content(content: &str) -> Result<DesktopFtpCredentials, String> {
    let raw = content.trim();
    if raw.is_empty() || raw == "undefined" {
        return Ok(DesktopFtpCredentials::default());
    }
    if raw.starts_with('[') {
        let credentials: Vec<Value> = serde_json::from_str(raw)
            .map_err(|err| format!("全局 FTP 连接 JSON 解析失败：{err}"))?;
        return normalize_ftp_credentials(DesktopFtpCredentials {
            version: FTP_CREDENTIALS_VERSION,
            credentials,
        });
    }
    let parsed: DesktopFtpCredentials =
        serde_json::from_str(raw).map_err(|err| format!("全局 FTP 连接 JSON 解析失败：{err}"))?;
    normalize_ftp_credentials(parsed)
}

pub fn find_global_ftp_credential(credential_id: &str) -> Result<Option<Value>, String> {
    let normalized_id = credential_id.trim();
    if normalized_id.is_empty() {
        return Ok(None);
    }
    Ok(read_global_ftp_credentials()?
        .credentials
        .into_iter()
        .find(|item| credential_id_of(item) == normalized_id))
}

pub fn credential_id_of(value: &Value) -> String {
    value
        .get("id")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string()
}

pub fn credential_enabled(value: &Value) -> bool {
    value
        .get("enabled")
        .and_then(Value::as_bool)
        .unwrap_or(true)
}

pub fn credential_u64(value: &Value, key: &str, default: u64) -> u64 {
    match value.get(key) {
        Some(Value::Number(number)) => number.as_u64().unwrap_or(default),
        Some(Value::String(text)) => text.trim().parse().unwrap_or(default),
        _ => default,
    }
}

pub fn credential_text(value: &Value, key: &str) -> String {
    match value.get(key) {
        Some(Value::String(text)) => text.to_string(),
        Some(Value::Number(number)) => number.to_string(),
        _ => String::new(),
    }
}

fn default_ftp_credentials_version() -> u32 {
    FTP_CREDENTIALS_VERSION
}

fn normalize_ftp_credentials(
    mut file: DesktopFtpCredentials,
) -> Result<DesktopFtpCredentials, String> {
    if file.credentials.len() > MAX_FTP_CREDENTIALS {
        return Err(format!("全局 FTP 连接最多可包含 {MAX_FTP_CREDENTIALS} 条"));
    }

    let mut ids = HashSet::with_capacity(file.credentials.len());
    let mut normalized = Vec::with_capacity(file.credentials.len());
    for (index, item) in file.credentials.into_iter().enumerate() {
        if !item.is_object() {
            return Err(format!("全局 FTP 连接第 {} 条格式无效", index + 1));
        }
        let id = credential_id_of(&item);
        if id.is_empty() {
            return Err(format!("全局 FTP 连接第 {} 条缺少连接 ID", index + 1));
        }
        if !ids.insert(id.clone()) {
            return Err(format!("全局 FTP 连接存在重复 ID：{id}"));
        }
        let name = credential_text(&item, "name").trim().to_string();
        let host = credential_text(&item, "host").trim().to_string();
        let username = credential_text(&item, "username");
        let password = credential_text(&item, "password");
        let port = credential_u64(&item, "port", 21).clamp(1, 65535);
        let max_upload_threads = credential_u64(&item, "max_upload_threads", 4).clamp(1, 32);
        let enabled = credential_enabled(&item);
        let mut credential = item;
        if let Some(object) = credential.as_object_mut() {
            object.insert("id".to_string(), json!(id));
            object.insert("name".to_string(), json!(name));
            object.insert("host".to_string(), json!(host));
            object.insert("username".to_string(), json!(username));
            object.insert("password".to_string(), json!(password));
            object.insert("port".to_string(), json!(port));
            object.insert("max_upload_threads".to_string(), json!(max_upload_threads));
            object.insert("enabled".to_string(), json!(enabled));
        }
        normalized.push(credential);
    }

    file.version = FTP_CREDENTIALS_VERSION;
    file.credentials = normalized;
    Ok(file)
}

#[cfg(test)]
mod tests {
    use super::{parse_ftp_credentials_content, FTP_CREDENTIALS_VERSION};
    use serde_json::json;

    #[test]
    fn parses_snake_case_ftp_credentials() {
        let file = parse_ftp_credentials_content(
            r#"{
                "version": 9,
                "credentials": [{
                    "id": "ftp-1",
                    "name": "生产 FTP",
                    "host": "ftp.example.com",
                    "port": "21",
                    "username": "deploy",
                    "password": "secret",
                    "max_upload_threads": "8",
                    "enabled": true
                }]
            }"#,
        )
        .unwrap();

        assert_eq!(file.version, FTP_CREDENTIALS_VERSION);
        assert_eq!(file.credentials.len(), 1);
        assert_eq!(file.credentials[0]["id"], "ftp-1");
        assert_eq!(file.credentials[0]["host"], "ftp.example.com");
        assert_eq!(file.credentials[0]["port"], 21);
        assert_eq!(file.credentials[0]["max_upload_threads"], 8);
        assert_eq!(file.credentials[0]["password"], "secret");
    }

    #[test]
    fn parses_raw_credential_array() {
        let file = parse_ftp_credentials_content(
            r#"[{
                "id": "ftp-2",
                "host": "10.0.0.1",
                "username": "user",
                "password": "pwd"
            }]"#,
        )
        .unwrap();

        assert_eq!(file.credentials[0]["id"], "ftp-2");
        assert_eq!(file.credentials[0]["port"], 21);
        assert_eq!(file.credentials[0]["enabled"], true);
    }

    #[test]
    fn rejects_duplicate_credential_ids() {
        let error = parse_ftp_credentials_content(
            r#"{
                "credentials": [
                    {"id": "ftp-1"},
                    {"id": "ftp-1"}
                ]
            }"#,
        )
        .unwrap_err();

        assert!(error.contains("重复 ID"));
    }
}
