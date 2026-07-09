//! Backend project tools for the desktop local runtime.
//!
//! These tools keep read-only project metadata access in the desktop runtime
//! while preserving backend auth and data-scope checks.

use reqwest::blocking::Client;
use reqwest::header::{HeaderMap, HeaderValue, AUTHORIZATION};
use reqwest::Url;
use serde_json::{json, Value};
use std::time::Duration;

use crate::liuagent_core::args::{number_arg, required_string_arg, string_arg};
use crate::liuagent_core::types::ToolError;

pub fn list_projects(arguments: &Value) -> Result<(Value, String), ToolError> {
    let api_base_url = string_arg(arguments, "_backend_api_base_url", "");
    let backend_token = string_arg(arguments, "_backend_token", "");
    if api_base_url.is_empty() || backend_token.is_empty() {
        return Err(ToolError::new(
            "projects.backend_context_missing",
            "缺少后端登录上下文，不能读取真实项目列表",
        ));
    }

    let page = number_arg(arguments, "page", 1, 1, 10_000);
    let page_size = number_arg(arguments, "page_size", 20, 1, 100);
    let name = string_arg(arguments, "name", "");
    let created_by = string_arg(arguments, "created_by", "");
    let timeout_ms = number_arg(arguments, "timeout_ms", 30_000, 1_000, 120_000) as u64;
    let endpoint = projects_url(&api_base_url, page, page_size, &name, &created_by)?;

    let body = backend_get_json(endpoint, &backend_token, timeout_ms, "读取项目列表失败")?;
    let total = body
        .get("total")
        .and_then(Value::as_i64)
        .or_else(|| {
            body.get("pagination")
                .and_then(|pagination| pagination.get("total"))
                .and_then(Value::as_i64)
        })
        .unwrap_or_else(|| {
            body.get("projects")
                .and_then(Value::as_array)
                .map(|items| items.len() as i64)
                .unwrap_or(0)
        });
    let count = body
        .get("projects")
        .and_then(Value::as_array)
        .map(Vec::len)
        .unwrap_or(0);

    Ok((
        json!({
            "page": page,
            "page_size": page_size,
            "name": name,
            "created_by": created_by,
            "total": total,
            "count": count,
            "response": body,
        }),
        format!("已读取当前登录用户可见项目：本页 {count} 个，总计 {total} 个"),
    ))
}

pub fn get_project(arguments: &Value) -> Result<(Value, String), ToolError> {
    let api_base_url = string_arg(arguments, "_backend_api_base_url", "");
    let backend_token = string_arg(arguments, "_backend_token", "");
    if api_base_url.is_empty() || backend_token.is_empty() {
        return Err(ToolError::new(
            "projects.backend_context_missing",
            "缺少后端登录上下文，不能读取项目详情",
        ));
    }

    let project_id = required_string_arg(arguments, "project_id")?;
    let timeout_ms = number_arg(arguments, "timeout_ms", 30_000, 1_000, 120_000) as u64;
    let endpoint = project_detail_url(&api_base_url, &project_id)?;
    let body = backend_get_json(endpoint, &backend_token, timeout_ms, "读取项目详情失败")?;
    let project_name = body
        .get("project")
        .and_then(|project| project.get("name"))
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or(project_id.as_str());

    Ok((
        json!({
            "project_id": project_id,
            "response": body,
        }),
        format!("已读取项目详情：{project_name}"),
    ))
}

fn backend_get_json(
    endpoint: Url,
    backend_token: &str,
    timeout_ms: u64,
    failure_message: &str,
) -> Result<Value, ToolError> {
    let mut headers = HeaderMap::new();
    let auth =
        HeaderValue::from_str(&format!("Bearer {}", backend_token.trim())).map_err(|err| {
            ToolError::new(
                "tool.schema_invalid",
                format!("invalid backend auth header: {err}"),
            )
        })?;
    headers.insert(AUTHORIZATION, auth);
    let client = Client::builder()
        .timeout(Duration::from_millis(timeout_ms))
        .user_agent("liuAgent-desktop-local-runtime/0.1")
        .build()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("create http client failed: {err}"),
            )
        })?;
    let response = client
        .get(endpoint)
        .headers(headers)
        .send()
        .map_err(|err| {
            ToolError::new("tool.execution_failed", format!("{failure_message}: {err}"))
        })?;
    let status = response.status().as_u16();
    let text = response.text().map_err(|err| {
        ToolError::new("tool.execution_failed", format!("读取后端响应失败: {err}"))
    })?;
    let body = serde_json::from_str::<Value>(&text).unwrap_or_else(|_| json!({"raw": text}));
    if !(200..300).contains(&status) {
        return Err(ToolError::new(
            "tool.execution_failed",
            format!(
                "{failure_message}，HTTP {status}: {}",
                safe_error_detail(&body)
            ),
        ));
    }
    Ok(body)
}

fn projects_url(
    api_base_url: &str,
    page: i64,
    page_size: i64,
    name: &str,
    created_by: &str,
) -> Result<Url, ToolError> {
    let mut endpoint = backend_url(api_base_url, "projects")?;
    {
        let mut query = endpoint.query_pairs_mut();
        query.append_pair("page", &page.to_string());
        query.append_pair("page_size", &page_size.to_string());
        if !name.trim().is_empty() {
            query.append_pair("name", name.trim());
        }
        if !created_by.trim().is_empty() {
            query.append_pair("created_by", created_by.trim());
        }
    }
    Ok(endpoint)
}

fn project_detail_url(api_base_url: &str, project_id: &str) -> Result<Url, ToolError> {
    backend_url(
        api_base_url,
        format!("projects/{}", url_path_escape(project_id)).as_str(),
    )
}

fn backend_url(api_base_url: &str, path: &str) -> Result<Url, ToolError> {
    let base = Url::parse(api_base_url.trim()).map_err(|err| {
        ToolError::new(
            "tool.schema_invalid",
            format!("invalid api_base_url: {err}"),
        )
    })?;
    if !matches!(base.scheme(), "http" | "https") {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "api_base_url must use http or https",
        ));
    }
    let clean_base = base.as_str().trim_end_matches('/');
    let clean_path = path.trim_start_matches('/');
    Url::parse(&format!("{clean_base}/{clean_path}"))
        .map_err(|err| ToolError::new("tool.schema_invalid", format!("invalid backend url: {err}")))
}

fn safe_error_detail(body: &Value) -> String {
    body.get("detail")
        .or_else(|| body.get("message"))
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| body.as_str().unwrap_or("request failed"))
        .chars()
        .take(1000)
        .collect()
}

fn url_path_escape(value: &str) -> String {
    value
        .bytes()
        .flat_map(|byte| match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                vec![byte as char]
            }
            _ => format!("%{byte:02X}").chars().collect(),
        })
        .collect()
}
