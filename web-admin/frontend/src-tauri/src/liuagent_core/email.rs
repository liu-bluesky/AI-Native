use lettre::message::{header::ContentType, Mailbox, Message, SinglePart};
use lettre::transport::smtp::authentication::Credentials;
use lettre::{SmtpTransport, Transport};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;

use super::paths::{desktop_runtime_root, ensure_desktop_runtime_migrated, global_user_home_dir};

pub const QQ_EMAIL_CONFIG_VERSION: u32 = 1;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct QqEmailConfig {
    #[serde(default = "default_version")]
    pub version: u32,
    #[serde(default)]
    pub enabled: bool,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub address: String,
    #[serde(default)]
    pub authorization_code: String,
}

impl Default for QqEmailConfig {
    fn default() -> Self {
        Self {
            version: QQ_EMAIL_CONFIG_VERSION,
            enabled: false,
            name: String::new(),
            address: String::new(),
            authorization_code: String::new(),
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SendQqEmailRequest {
    pub to: String,
    #[serde(default)]
    pub cc: String,
    #[serde(default)]
    pub subject: String,
    pub content: String,
}

fn default_version() -> u32 {
    QQ_EMAIL_CONFIG_VERSION
}

pub fn global_qq_email_config_path() -> Result<PathBuf, String> {
    let home = global_user_home_dir().ok_or_else(|| "无法定位用户目录".to_string())?;
    ensure_desktop_runtime_migrated(&home)
        .map_err(|err| format!("迁移桌面运行时数据失败：{err}"))?;
    Ok(desktop_runtime_root(&home).join("qq-email.json"))
}

pub fn read_global_qq_email_config() -> Result<QqEmailConfig, String> {
    let path = global_qq_email_config_path()?;
    if !path.exists() {
        return Ok(QqEmailConfig::default());
    }
    let content = fs::read_to_string(path).map_err(|err| format!("无法读取 QQ 邮箱配置：{err}"))?;
    parse_qq_email_config(&content)
}

pub fn parse_qq_email_config(content: &str) -> Result<QqEmailConfig, String> {
    if content.trim().is_empty() {
        return Ok(QqEmailConfig::default());
    }
    let mut config: QqEmailConfig =
        serde_json::from_str(content).map_err(|err| format!("QQ 邮箱配置 JSON 解析失败：{err}"))?;
    config.version = QQ_EMAIL_CONFIG_VERSION;
    config.name = config.name.trim().to_string();
    config.address = config.address.trim().to_string();
    Ok(config)
}

pub fn write_global_qq_email_config(mut config: QqEmailConfig) -> Result<QqEmailConfig, String> {
    config.version = QQ_EMAIL_CONFIG_VERSION;
    config.name = config.name.trim().to_string();
    config.address = config.address.trim().to_string();
    config.authorization_code = config.authorization_code.trim().to_string();
    if config.address.is_empty() || !config.address.contains('@') {
        return Err("请填写有效的 QQ 邮箱地址".to_string());
    }
    if config.authorization_code.is_empty() {
        return Err("请填写 QQ 邮箱授权码".to_string());
    }
    let path = global_qq_email_config_path()?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|err| format!("无法创建邮箱配置目录：{err}"))?;
    }
    let content = serde_json::to_string_pretty(&config)
        .map_err(|err| format!("无法序列化 QQ 邮箱配置：{err}"))?;
    fs::write(path, format!("{content}\n"))
        .map_err(|err| format!("无法保存 QQ 邮箱配置：{err}"))?;
    Ok(config)
}

pub fn send_qq_email(request: SendQqEmailRequest) -> Result<(), String> {
    let config = read_global_qq_email_config()?;
    if !config.enabled {
        return Err("请先启用并保存 QQ 邮箱配置".to_string());
    }
    if config.authorization_code.is_empty() {
        return Err("QQ 邮箱授权码未配置".to_string());
    }
    let sender: Mailbox = config
        .address
        .parse()
        .map_err(|err| format!("发件人地址无效：{err}"))?;
    let mut builder = Message::builder()
        .from(sender)
        .subject(request.subject.trim());
    for address in request
        .to
        .split([',', ';', '\n'])
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        builder = builder.to(address
            .parse()
            .map_err(|err| format!("收件人地址无效：{err}"))?);
    }
    for address in request
        .cc
        .split([',', ';', '\n'])
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        builder = builder.cc(address
            .parse()
            .map_err(|err| format!("抄送地址无效：{err}"))?);
    }
    let message = builder
        .singlepart(
            SinglePart::builder()
                .header(ContentType::TEXT_PLAIN)
                .body(request.content),
        )
        .map_err(|err| format!("邮件内容构建失败：{err}"))?;
    SmtpTransport::relay("smtp.qq.com")
        .map_err(|err| format!("QQ 邮箱 SMTP 初始化失败：{err}"))?
        .credentials(Credentials::new(config.address, config.authorization_code))
        .port(465)
        .build()
        .send(&message)
        .map_err(|err| format!("邮件发送失败：{err}"))?;
    Ok(())
}
