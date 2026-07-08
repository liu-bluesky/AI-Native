//! 本地网络工具。
//!
//! 网络请求由桌面端本机发起；禁止自动携带 Cookie、Authorization 等本地凭据。

use reqwest::blocking::{Client, Response};
use reqwest::header::{HeaderMap, HeaderName, HeaderValue};
use reqwest::Url;
use serde_json::{json, Value};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::Duration;

use crate::liuagent_core::args::{bool_arg, number_arg, required_string_arg};
use crate::liuagent_core::permission::require_approval;
use crate::liuagent_core::types::{PermissionDecisionInput, ToolError};
use crate::liuagent_core::workspace::{
    resolve_workspace_root, resolve_workspace_write_target, workspace_relative_path,
};

const MAX_BODY_CHARS: usize = 80_000;
const MAX_DOWNLOAD_BYTES: usize = 20 * 1024 * 1024;
const MAX_SEARCH_RESULTS: usize = 10;
const MAX_EXTRACT_URLS: usize = 5;
const MAX_EXTRACT_CONTENT_CHARS: usize = 80_000;
pub const WEB_TOOL_CONFIG_TEMPLATE: &str = r#"{
  "version": 1,
  "backend": "",
  "search": {
    "backend": ""
  },
  "extract": {
    "backend": ""
  },
  "providers": {
    "managed": {
      "search_url": "",
      "search_token": "",
      "extract_url": "",
      "extract_token": ""
    },
    "firecrawl": {
      "api_key": "",
      "api_url": ""
    },
    "parallel": {
      "api_key": ""
    },
    "tavily": {
      "api_key": ""
    },
    "exa": {
      "api_key": ""
    }
  }
}
"#;

pub fn http_get(_workspace_path: &str, arguments: &Value) -> Result<(Value, String), ToolError> {
    let url = parse_http_url(&required_string_arg(arguments, "url")?)?;
    let timeout_ms = number_arg(arguments, "timeout_ms", 30_000, 1_000, 120_000) as u64;
    let headers = parse_headers(arguments.get("headers"))?;
    let response = request_client(timeout_ms)?
        .get(url.clone())
        .headers(headers)
        .send()
        .map_err(|err| {
            ToolError::new("tool.execution_failed", format!("http get failed: {err}"))
        })?;
    response_to_result("GET", url.as_str(), response)
}

pub fn http_post(
    tool_call_id: &str,
    _workspace_path: &str,
    arguments: &Value,
    permission_decision: Option<&PermissionDecisionInput>,
) -> Result<(Value, String), ToolError> {
    let url = parse_http_url(&required_string_arg(arguments, "url")?)?;
    let timeout_ms = number_arg(arguments, "timeout_ms", 30_000, 1_000, 120_000) as u64;
    let headers = parse_headers(arguments.get("headers"))?;
    let body = arguments
        .get("body")
        .ok_or_else(|| ToolError::new("tool.schema_invalid", "missing required argument: body"))?
        .clone();
    require_approval(
        tool_call_id,
        "network.write",
        "high",
        "network",
        &format!("发送 HTTP POST：{}", url.as_str()),
        json!({
            "url": url.as_str(),
            "body_summary": summarize_json_value(&body),
            "timeout_ms": timeout_ms
        }),
        permission_decision,
    )?;

    let response = request_client(timeout_ms)?
        .post(url.clone())
        .headers(headers)
        .json(&body)
        .send()
        .map_err(|err| {
            ToolError::new("tool.execution_failed", format!("http post failed: {err}"))
        })?;
    response_to_result("POST", url.as_str(), response)
}

pub fn web_search(workspace_path: &str, arguments: &Value) -> Result<(Value, String), ToolError> {
    let query = required_string_arg(arguments, "query")?;
    let limit = number_arg(arguments, "limit", 5, 1, MAX_SEARCH_RESULTS as i64) as usize;
    let timeout_ms = number_arg(arguments, "timeout_ms", 30_000, 1_000, 120_000) as u64;
    let backend = match resolve_web_search_backend(workspace_path) {
        Ok(backend) => backend,
        Err(error) if error.code == "web_search.unconfigured" => {
            return Ok(web_search_unconfigured_result(&query));
        }
        Err(error) => return Err(error),
    };

    match backend {
        WebSearchBackend::Managed { url, token } => {
            let response =
                send_managed_search_request(&url, token.as_deref(), &query, limit, timeout_ms)?;
            search_response_to_result("managed", &query, response, limit)
        }
        WebSearchBackend::Firecrawl { api_url, api_key } => {
            let response = send_firecrawl_search_request(
                &api_url,
                api_key.as_deref(),
                &query,
                limit,
                timeout_ms,
            )?;
            search_response_to_result("firecrawl", &query, response, limit)
        }
        WebSearchBackend::Parallel { api_key } => {
            let response = send_parallel_search_request(&api_key, &query, timeout_ms)?;
            search_response_to_result("parallel", &query, response, limit)
        }
        WebSearchBackend::Tavily { api_key } => {
            let response = send_tavily_search_request(&api_key, &query, limit, timeout_ms)?;
            search_response_to_result("tavily", &query, response, limit)
        }
        WebSearchBackend::Exa { api_key } => {
            let response = send_exa_search_request(&api_key, &query, limit, timeout_ms)?;
            search_response_to_result("exa", &query, response, limit)
        }
    }
}

pub fn web_search_configured(workspace_path: &str) -> bool {
    resolve_web_search_backend(workspace_path).is_ok()
}

pub fn web_extract(workspace_path: &str, arguments: &Value) -> Result<(Value, String), ToolError> {
    let urls = required_url_array_arg(arguments, "urls", MAX_EXTRACT_URLS)?;
    let timeout_ms = number_arg(arguments, "timeout_ms", 30_000, 1_000, 120_000) as u64;
    let format = string_field(arguments, &["format"]).unwrap_or_else(|| "markdown".to_string());
    let backend = match resolve_web_extract_backend(workspace_path) {
        Ok(backend) => backend,
        Err(error) if error.code == "web_extract.unconfigured" => {
            return Ok(web_extract_unconfigured_result(&urls));
        }
        Err(error) => return Err(error),
    };

    match backend {
        WebExtractBackend::Managed { url, token } => {
            let response =
                send_managed_extract_request(&url, token.as_deref(), &urls, &format, timeout_ms)?;
            extract_response_to_result("managed", response)
        }
        WebExtractBackend::Firecrawl { api_url, api_key } => {
            firecrawl_extract_to_result(&api_url, api_key.as_deref(), &urls, &format, timeout_ms)
        }
        WebExtractBackend::Parallel { api_key } => {
            let response = send_parallel_extract_request(&api_key, &urls, timeout_ms)?;
            extract_response_to_result("parallel", response)
        }
        WebExtractBackend::Tavily { api_key } => {
            let response = send_tavily_extract_request(&api_key, &urls, timeout_ms)?;
            extract_response_to_result("tavily", response)
        }
        WebExtractBackend::Exa { api_key } => {
            let response = send_exa_extract_request(&api_key, &urls, timeout_ms)?;
            extract_response_to_result("exa", response)
        }
    }
}

pub fn web_extract_configured(workspace_path: &str) -> bool {
    resolve_web_extract_backend(workspace_path).is_ok()
}

fn web_search_unconfigured_result(query: &str) -> (Value, String) {
    (
        json!({
            "backend": "unconfigured",
            "query": query,
            "result_count": 0,
            "results": [],
            "status": "unconfigured",
            "recoverable": true,
            "recovery_scope": "configure_search_backend_or_use_http_get",
            "required_config": [
                ".ai-employee/agent-runtime-v2/web-tools/config.json",
                "backend/search.backend = managed|firecrawl|parallel|tavily|exa",
                "LIUAGENT_WEB_BACKEND",
                "AI_EMPLOYEE_WEB_BACKEND",
                "WEB_BACKEND",
                "LIUAGENT_WEB_SEARCH_URL",
                "AI_EMPLOYEE_WEB_SEARCH_URL",
                "FIRECRAWL_API_KEY",
                "FIRECRAWL_API_URL",
                "PARALLEL_API_KEY",
                "TAVILY_API_KEY",
                "EXA_API_KEY"
            ],
            "message": "web_search is not configured; enable a backend in .ai-employee/agent-runtime-v2/web-tools/config.json or set WEB_BACKEND together with provider credentials, or use http_get for known URLs"
        }),
        format!("web_search 未配置，无法直接搜索：{query}；需在 .ai-employee/agent-runtime-v2/web-tools/config.json 启用 backend=managed/firecrawl/parallel/tavily/exa 并保留对应配置，或对已知 URL 改用 http_get。"),
    )
}

fn web_extract_unconfigured_result(urls: &[Url]) -> (Value, String) {
    (
        json!({
            "backend": "unconfigured",
            "urls": urls.iter().map(Url::as_str).collect::<Vec<_>>(),
            "result_count": 0,
            "documents": [],
            "status": "unconfigured",
            "recoverable": true,
            "recovery_scope": "configure_extract_backend_or_use_http_get",
            "required_config": [
                ".ai-employee/agent-runtime-v2/web-tools/config.json",
                "backend/extract.backend = managed|firecrawl|parallel|tavily|exa",
                "LIUAGENT_WEB_BACKEND",
                "AI_EMPLOYEE_WEB_BACKEND",
                "WEB_BACKEND",
                "LIUAGENT_WEB_EXTRACT_URL",
                "AI_EMPLOYEE_WEB_EXTRACT_URL",
                "FIRECRAWL_API_KEY",
                "FIRECRAWL_API_URL",
                "PARALLEL_API_KEY",
                "TAVILY_API_KEY",
                "EXA_API_KEY"
            ],
            "message": "web_extract is not configured; enable a backend in .ai-employee/agent-runtime-v2/web-tools/config.json or set WEB_BACKEND together with provider credentials, or use http_get for known URLs"
        }),
        format!(
            "web_extract 未配置，无法抽取 {} 个 URL；需在 .ai-employee/agent-runtime-v2/web-tools/config.json 启用 backend=managed/firecrawl/parallel/tavily/exa 并保留对应配置，或对已知 URL 改用 http_get。",
            urls.len()
        ),
    )
}

pub fn download_file(
    tool_call_id: &str,
    workspace_path: &str,
    arguments: &Value,
    permission_decision: Option<&PermissionDecisionInput>,
) -> Result<(Value, String), ToolError> {
    let root = resolve_workspace_root(workspace_path)?;
    let url = parse_http_url(&required_string_arg(arguments, "url")?)?;
    let dest_path = required_string_arg(arguments, "dest_path")?;
    let overwrite = bool_arg(arguments, "overwrite", false);
    let timeout_ms = number_arg(arguments, "timeout_ms", 30_000, 1_000, 120_000) as u64;
    let target = resolve_workspace_write_target(&root, &dest_path)?;
    let exists = target.exists();
    if exists && !target.is_file() {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "dest_path is not a file",
        ));
    }
    if exists && !overwrite {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "file already exists; set overwrite=true to replace it",
        ));
    }
    let relative_path = workspace_relative_path(&root, &target);
    require_approval(
        tool_call_id,
        "network.read",
        if exists { "high" } else { "medium" },
        "workspace",
        &format!("下载文件到 {relative_path}"),
        json!({
            "url": url.as_str(),
            "dest_path": relative_path,
            "overwrite": overwrite,
            "exists": exists,
            "timeout_ms": timeout_ms
        }),
        permission_decision,
    )?;

    let response = request_client(timeout_ms)?
        .get(url.clone())
        .send()
        .map_err(|err| {
            ToolError::new("tool.execution_failed", format!("download failed: {err}"))
        })?;
    let status = response.status().as_u16();
    let content_type = response
        .headers()
        .get("content-type")
        .and_then(|value| value.to_str().ok())
        .unwrap_or("")
        .to_string();
    if !response.status().is_success() {
        return Err(ToolError::new(
            "tool.execution_failed",
            format!("download failed with http status {status}"),
        ));
    }
    let bytes = response.bytes().map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("read download failed: {err}"),
        )
    })?;
    if bytes.len() > MAX_DOWNLOAD_BYTES {
        return Err(ToolError::new(
            "tool.output_too_large",
            format!("download is larger than {} bytes", MAX_DOWNLOAD_BYTES),
        ));
    }
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent).map_err(|err| {
            ToolError::new("tool.execution_failed", format!("create dir failed: {err}"))
        })?;
    }
    fs::write(&target, &bytes).map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("write download failed: {err}"),
        )
    })?;
    let summary = format!("下载 {} 字节到 {}", bytes.len(), relative_path);
    Ok((
        json!({
            "dest_path": relative_path,
            "bytes": bytes.len(),
            "content_type": content_type,
            "status": status
        }),
        summary,
    ))
}

#[derive(Debug)]
enum WebSearchBackend {
    Managed {
        url: Url,
        token: Option<String>,
    },
    Firecrawl {
        api_url: Url,
        api_key: Option<String>,
    },
    Parallel {
        api_key: String,
    },
    Tavily {
        api_key: String,
    },
    Exa {
        api_key: String,
    },
}

#[derive(Debug)]
enum WebExtractBackend {
    Managed {
        url: Url,
        token: Option<String>,
    },
    Firecrawl {
        api_url: Url,
        api_key: Option<String>,
    },
    Parallel {
        api_key: String,
    },
    Tavily {
        api_key: String,
    },
    Exa {
        api_key: String,
    },
}

fn resolve_web_search_backend(workspace_path: &str) -> Result<WebSearchBackend, ToolError> {
    let config = load_web_tool_config(workspace_path)?;
    resolve_web_search_backend_from_config(&config)
}

fn resolve_web_search_backend_from_config(
    config: &WebToolConfig,
) -> Result<WebSearchBackend, ToolError> {
    resolve_web_search_backend_from_values(
        config_first(
            config,
            &[&["search", "backend"], &["backend"]],
            &[
                "LIUAGENT_WEB_BACKEND",
                "AI_EMPLOYEE_WEB_BACKEND",
                "WEB_BACKEND",
            ],
        ),
        config_first(
            config,
            &[
                &["search", "managed_url"],
                &["search", "url"],
                &["providers", "managed", "search_url"],
                &["managed", "search_url"],
            ],
            &["LIUAGENT_WEB_SEARCH_URL", "AI_EMPLOYEE_WEB_SEARCH_URL"],
        ),
        config_first(
            config,
            &[
                &["search", "managed_token"],
                &["search", "token"],
                &["providers", "managed", "search_token"],
                &["managed", "search_token"],
            ],
            &[
                "LIUAGENT_WEB_SEARCH_TOKEN",
                "AI_EMPLOYEE_WEB_SEARCH_TOKEN",
                "WEB_SEARCH_TOKEN",
            ],
        ),
        config_first(
            config,
            &[
                &["providers", "firecrawl", "api_url"],
                &["firecrawl", "api_url"],
            ],
            &["FIRECRAWL_API_URL"],
        ),
        config_first(
            config,
            &[
                &["providers", "firecrawl", "api_key"],
                &["providers", "firecrawl", "apiKey"],
                &["firecrawl", "api_key"],
                &["firecrawl", "apiKey"],
            ],
            &["FIRECRAWL_API_KEY"],
        ),
        config_first(
            config,
            &[
                &["providers", "parallel", "api_key"],
                &["providers", "parallel", "apiKey"],
                &["parallel", "api_key"],
                &["parallel", "apiKey"],
            ],
            &["PARALLEL_API_KEY"],
        ),
        config_first(
            config,
            &[
                &["providers", "tavily", "api_key"],
                &["providers", "tavily", "apiKey"],
                &["tavily", "api_key"],
                &["tavily", "apiKey"],
            ],
            &["TAVILY_API_KEY"],
        ),
        config_first(
            config,
            &[
                &["providers", "exa", "api_key"],
                &["providers", "exa", "apiKey"],
                &["exa", "api_key"],
                &["exa", "apiKey"],
            ],
            &["EXA_API_KEY"],
        ),
    )
}

fn resolve_web_search_backend_from_values(
    preferred_backend: Option<String>,
    managed_url: Option<String>,
    managed_token: Option<String>,
    firecrawl_api_url: Option<String>,
    firecrawl_api_key: Option<String>,
    parallel_key: Option<String>,
    tavily_key: Option<String>,
    exa_key: Option<String>,
) -> Result<WebSearchBackend, ToolError> {
    let managed_url = managed_url
        .map(|raw_url| parse_http_url(&raw_url))
        .transpose()?;
    let firecrawl_api_url = firecrawl_api_url
        .map(|raw_url| parse_http_url(&raw_url))
        .transpose()?;
    let preferred_backend = preferred_backend
        .as_deref()
        .and_then(normalize_web_backend_preference);

    if let Some(backend) = build_preferred_search_backend(
        preferred_backend,
        managed_url.clone(),
        managed_token.clone(),
        firecrawl_api_url.clone(),
        firecrawl_api_key.clone(),
        parallel_key.clone(),
        tavily_key.clone(),
        exa_key.clone(),
    ) {
        return Ok(backend);
    }

    Err(ToolError::new(
        "web_search.unconfigured",
        "web_search is not configured; enable a web backend in .ai-employee/agent-runtime-v2/web-tools/config.json or set LIUAGENT_WEB_BACKEND/AI_EMPLOYEE_WEB_BACKEND/WEB_BACKEND together with provider credentials",
    ))
}

fn build_preferred_search_backend(
    preferred_backend: Option<&str>,
    managed_url: Option<Url>,
    managed_token: Option<String>,
    firecrawl_api_url: Option<Url>,
    firecrawl_api_key: Option<String>,
    parallel_key: Option<String>,
    tavily_key: Option<String>,
    exa_key: Option<String>,
) -> Option<WebSearchBackend> {
    match preferred_backend? {
        "managed" => managed_url.map(|url| WebSearchBackend::Managed {
            url,
            token: managed_token,
        }),
        "firecrawl" => {
            if firecrawl_api_key.is_some() || firecrawl_api_url.is_some() {
                Some(WebSearchBackend::Firecrawl {
                    api_url: firecrawl_api_url.unwrap_or_else(default_firecrawl_api_url),
                    api_key: firecrawl_api_key,
                })
            } else {
                None
            }
        }
        "parallel" => parallel_key.map(|api_key| WebSearchBackend::Parallel { api_key }),
        "tavily" => tavily_key.map(|api_key| WebSearchBackend::Tavily { api_key }),
        "exa" => exa_key.map(|api_key| WebSearchBackend::Exa { api_key }),
        _ => None,
    }
}

fn resolve_web_extract_backend(workspace_path: &str) -> Result<WebExtractBackend, ToolError> {
    let config = load_web_tool_config(workspace_path)?;
    resolve_web_extract_backend_from_config(&config)
}

fn resolve_web_extract_backend_from_config(
    config: &WebToolConfig,
) -> Result<WebExtractBackend, ToolError> {
    resolve_web_extract_backend_from_values(
        config_first(
            config,
            &[&["extract", "backend"], &["backend"]],
            &[
                "LIUAGENT_WEB_BACKEND",
                "AI_EMPLOYEE_WEB_BACKEND",
                "WEB_BACKEND",
            ],
        ),
        config_first(
            config,
            &[
                &["extract", "managed_url"],
                &["extract", "url"],
                &["providers", "managed", "extract_url"],
                &["managed", "extract_url"],
            ],
            &["LIUAGENT_WEB_EXTRACT_URL", "AI_EMPLOYEE_WEB_EXTRACT_URL"],
        ),
        config_first(
            config,
            &[
                &["extract", "managed_token"],
                &["extract", "token"],
                &["providers", "managed", "extract_token"],
                &["managed", "extract_token"],
            ],
            &[
                "LIUAGENT_WEB_EXTRACT_TOKEN",
                "AI_EMPLOYEE_WEB_EXTRACT_TOKEN",
                "WEB_EXTRACT_TOKEN",
            ],
        ),
        config_first(
            config,
            &[
                &["providers", "firecrawl", "api_url"],
                &["firecrawl", "api_url"],
            ],
            &["FIRECRAWL_API_URL"],
        ),
        config_first(
            config,
            &[
                &["providers", "firecrawl", "api_key"],
                &["providers", "firecrawl", "apiKey"],
                &["firecrawl", "api_key"],
                &["firecrawl", "apiKey"],
            ],
            &["FIRECRAWL_API_KEY"],
        ),
        config_first(
            config,
            &[
                &["providers", "parallel", "api_key"],
                &["providers", "parallel", "apiKey"],
                &["parallel", "api_key"],
                &["parallel", "apiKey"],
            ],
            &["PARALLEL_API_KEY"],
        ),
        config_first(
            config,
            &[
                &["providers", "tavily", "api_key"],
                &["providers", "tavily", "apiKey"],
                &["tavily", "api_key"],
                &["tavily", "apiKey"],
            ],
            &["TAVILY_API_KEY"],
        ),
        config_first(
            config,
            &[
                &["providers", "exa", "api_key"],
                &["providers", "exa", "apiKey"],
                &["exa", "api_key"],
                &["exa", "apiKey"],
            ],
            &["EXA_API_KEY"],
        ),
    )
}

fn resolve_web_extract_backend_from_values(
    preferred_backend: Option<String>,
    managed_url: Option<String>,
    managed_token: Option<String>,
    firecrawl_api_url: Option<String>,
    firecrawl_api_key: Option<String>,
    parallel_key: Option<String>,
    tavily_key: Option<String>,
    exa_key: Option<String>,
) -> Result<WebExtractBackend, ToolError> {
    let managed_url = managed_url
        .map(|raw_url| parse_http_url(&raw_url))
        .transpose()?;
    let firecrawl_api_url = firecrawl_api_url
        .map(|raw_url| parse_http_url(&raw_url))
        .transpose()?;
    let preferred_backend = preferred_backend
        .as_deref()
        .and_then(normalize_web_backend_preference);

    if let Some(backend) = build_preferred_extract_backend(
        preferred_backend,
        managed_url.clone(),
        managed_token.clone(),
        firecrawl_api_url.clone(),
        firecrawl_api_key.clone(),
        parallel_key.clone(),
        tavily_key.clone(),
        exa_key.clone(),
    ) {
        return Ok(backend);
    }

    Err(ToolError::new(
        "web_extract.unconfigured",
        "web_extract is not configured; enable a web backend in .ai-employee/agent-runtime-v2/web-tools/config.json or set LIUAGENT_WEB_BACKEND/AI_EMPLOYEE_WEB_BACKEND/WEB_BACKEND together with provider credentials",
    ))
}

fn build_preferred_extract_backend(
    preferred_backend: Option<&str>,
    managed_url: Option<Url>,
    managed_token: Option<String>,
    firecrawl_api_url: Option<Url>,
    firecrawl_api_key: Option<String>,
    parallel_key: Option<String>,
    tavily_key: Option<String>,
    exa_key: Option<String>,
) -> Option<WebExtractBackend> {
    match preferred_backend? {
        "managed" => managed_url.map(|url| WebExtractBackend::Managed {
            url,
            token: managed_token,
        }),
        "firecrawl" => {
            if firecrawl_api_key.is_some() || firecrawl_api_url.is_some() {
                Some(WebExtractBackend::Firecrawl {
                    api_url: firecrawl_api_url.unwrap_or_else(default_firecrawl_api_url),
                    api_key: firecrawl_api_key,
                })
            } else {
                None
            }
        }
        "parallel" => parallel_key.map(|api_key| WebExtractBackend::Parallel { api_key }),
        "tavily" => tavily_key.map(|api_key| WebExtractBackend::Tavily { api_key }),
        "exa" => exa_key.map(|api_key| WebExtractBackend::Exa { api_key }),
        _ => None,
    }
}

fn normalize_web_backend_preference(value: &str) -> Option<&'static str> {
    match value.trim().to_ascii_lowercase().as_str() {
        "managed" | "custom" => Some("managed"),
        "firecrawl" => Some("firecrawl"),
        "parallel" => Some("parallel"),
        "tavily" => Some("tavily"),
        "exa" => Some("exa"),
        _ => None,
    }
}

fn default_firecrawl_api_url() -> Url {
    Url::parse("https://api.firecrawl.dev").expect("valid default firecrawl api url")
}

fn firecrawl_endpoint_url(
    api_url: &Url,
    endpoint_name: &str,
    default_relative_path: &str,
) -> Result<Url, ToolError> {
    let normalized_endpoint = endpoint_name.trim().trim_start_matches('/');
    let normalized_default_path = default_relative_path.trim().trim_start_matches('/');
    if normalized_endpoint.is_empty() {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "firecrawl endpoint name is required",
        ));
    }
    let path = api_url.path().trim_end_matches('/');
    let last_segment = path.rsplit('/').next().unwrap_or("");
    if last_segment.eq_ignore_ascii_case(normalized_endpoint) {
        return Ok(api_url.clone());
    }
    if path.is_empty() || path == "/" {
        return api_url.join(normalized_default_path).map_err(|err| {
            ToolError::new(
                "tool.schema_invalid",
                format!("invalid firecrawl api url: {err}"),
            )
        });
    }
    if path
        .rsplit('/')
        .next()
        .map(is_version_segment)
        .unwrap_or(false)
    {
        let mut version_base = api_url.clone();
        if !version_base.path().ends_with('/') {
            version_base.set_path(&format!("{}/", version_base.path()));
        }
        return version_base.join(normalized_endpoint).map_err(|err| {
            ToolError::new(
                "tool.schema_invalid",
                format!("invalid firecrawl api url: {err}"),
            )
        });
    }
    Ok(api_url.clone())
}

fn is_version_segment(segment: &str) -> bool {
    let bytes = segment.as_bytes();
    bytes.len() >= 2 && bytes[0] == b'v' && bytes[1..].iter().all(u8::is_ascii_digit)
}

#[derive(Debug, Default)]
struct WebToolConfig {
    global: Option<Value>,
    project: Option<Value>,
}

fn load_web_tool_config(workspace_path: &str) -> Result<WebToolConfig, ToolError> {
    let root = resolve_workspace_root(workspace_path)?;
    load_web_tool_config_from_paths(
        global_web_tool_config_path().as_deref(),
        &project_web_tool_config_path(&root),
    )
}

fn load_web_tool_config_from_paths(
    global_path: Option<&Path>,
    project_path: &Path,
) -> Result<WebToolConfig, ToolError> {
    Ok(WebToolConfig {
        global: match global_path {
            Some(path) => read_optional_web_tool_config("global", path)?,
            None => None,
        },
        project: read_optional_web_tool_config("project", project_path)?,
    })
}

fn read_optional_web_tool_config(scope: &str, path: &Path) -> Result<Option<Value>, ToolError> {
    if !path.exists() {
        return Ok(None);
    }
    if !path.is_file() {
        return Err(ToolError::new(
            "web_tools.config_invalid",
            format!(
                "{scope} web tool config path is not a file: {}",
                path.display()
            ),
        ));
    }
    let raw = fs::read_to_string(path).map_err(|err| {
        ToolError::new(
            "web_tools.config_invalid",
            format!("read {scope} web tool config failed: {err}"),
        )
    })?;
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return Ok(None);
    }
    serde_json::from_str::<Value>(trimmed)
        .map(Some)
        .map_err(|err| {
            ToolError::new(
                "web_tools.config_invalid",
                format!(
                    "{scope} web tool config is not valid json: {} ({})",
                    path.display(),
                    err
                ),
            )
        })
}

pub fn global_web_tool_config_path() -> Option<PathBuf> {
    env::var_os("HOME").map(|home| {
        PathBuf::from(home)
            .join(".ai-employee")
            .join("agent-runtime-v2")
            .join("web-tools")
            .join("config.json")
    })
}

pub fn project_web_tool_config_path(workspace_root: &Path) -> PathBuf {
    workspace_root
        .join(".ai-employee")
        .join("agent-runtime-v2")
        .join("web-tools")
        .join("config.json")
}

fn config_first(
    config: &WebToolConfig,
    config_paths: &[&[&str]],
    env_keys: &[&str],
) -> Option<String> {
    config
        .project
        .as_ref()
        .and_then(|value| first_config_string(value, config_paths))
        .or_else(|| {
            config
                .global
                .as_ref()
                .and_then(|value| first_config_string(value, config_paths))
        })
        .or_else(|| env_first_slice(env_keys))
}

fn first_config_string(config: &Value, paths: &[&[&str]]) -> Option<String> {
    paths
        .iter()
        .filter_map(|path| config_string(config, path))
        .find(|value| !value.is_empty())
}

fn config_string(config: &Value, path: &[&str]) -> Option<String> {
    let mut current = config;
    for segment in path {
        current = current.get(*segment)?;
    }
    current.as_str().map(str::trim).map(str::to_string)
}

fn env_first_slice(keys: &[&str]) -> Option<String> {
    keys.iter()
        .filter_map(|key| env::var(key).ok())
        .map(|value| value.trim().to_string())
        .find(|value| !value.is_empty())
}

fn send_managed_search_request(
    url: &Url,
    token: Option<&str>,
    query: &str,
    limit: usize,
    timeout_ms: u64,
) -> Result<Response, ToolError> {
    let client = request_client(timeout_ms)?;
    let mut request = client.post(url.clone()).json(&json!({
        "query": query,
        "limit": limit,
    }));
    if let Some(token) = token.filter(|item| !item.trim().is_empty()) {
        request = request.bearer_auth(token.trim());
    }
    request
        .send()
        .map_err(|err| ToolError::new("tool.execution_failed", format!("web search failed: {err}")))
}

fn send_firecrawl_search_request(
    api_url: &Url,
    api_key: Option<&str>,
    query: &str,
    limit: usize,
    timeout_ms: u64,
) -> Result<Response, ToolError> {
    let url = firecrawl_endpoint_url(api_url, "search", "v2/search")?;
    let mut request = request_client(timeout_ms)?.post(url).json(&json!({
        "query": query,
        "limit": limit,
        "sources": ["web"],
    }));
    if let Some(api_key) = api_key.filter(|item| !item.trim().is_empty()) {
        request = request.bearer_auth(api_key.trim());
    }
    request.send().map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("firecrawl search failed: {err}"),
        )
    })
}

fn send_parallel_search_request(
    api_key: &str,
    query: &str,
    timeout_ms: u64,
) -> Result<Response, ToolError> {
    request_client(timeout_ms)?
        .post("https://api.parallel.ai/v1/search")
        .header("x-api-key", api_key.trim())
        .json(&json!({
            "search_queries": [query],
            "objective": query,
            "processor": parallel_search_processor(),
        }))
        .send()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("parallel search failed: {err}"),
            )
        })
}

fn send_tavily_search_request(
    api_key: &str,
    query: &str,
    limit: usize,
    timeout_ms: u64,
) -> Result<Response, ToolError> {
    request_client(timeout_ms)?
        .post("https://api.tavily.com/search")
        .json(&json!({
            "api_key": api_key,
            "query": query,
            "max_results": limit,
            "search_depth": "basic",
            "include_answer": false,
            "include_raw_content": false,
            "include_images": false
        }))
        .send()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("tavily search failed: {err}"),
            )
        })
}

fn send_exa_search_request(
    api_key: &str,
    query: &str,
    limit: usize,
    timeout_ms: u64,
) -> Result<Response, ToolError> {
    request_client(timeout_ms)?
        .post("https://api.exa.ai/search")
        .header("x-api-key", api_key.trim())
        .json(&json!({
            "query": query,
            "numResults": limit,
            "contents": {
                "highlights": true
            }
        }))
        .send()
        .map_err(|err| ToolError::new("tool.execution_failed", format!("exa search failed: {err}")))
}

fn send_managed_extract_request(
    url: &Url,
    token: Option<&str>,
    urls: &[Url],
    format: &str,
    timeout_ms: u64,
) -> Result<Response, ToolError> {
    let client = request_client(timeout_ms)?;
    let mut request = client.post(url.clone()).json(&json!({
        "urls": urls.iter().map(Url::as_str).collect::<Vec<_>>(),
        "format": format,
    }));
    if let Some(token) = token.filter(|item| !item.trim().is_empty()) {
        request = request.bearer_auth(token.trim());
    }
    request.send().map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("web extract failed: {err}"),
        )
    })
}

fn firecrawl_extract_to_result(
    api_url: &Url,
    api_key: Option<&str>,
    urls: &[Url],
    format: &str,
    timeout_ms: u64,
) -> Result<(Value, String), ToolError> {
    let endpoint = firecrawl_endpoint_url(api_url, "scrape", "v2/scrape")?;
    let formats = if format.eq_ignore_ascii_case("html") {
        vec!["html"]
    } else {
        vec!["markdown"]
    };
    let mut documents = Vec::new();
    for url in urls {
        let mut request = request_client(timeout_ms)?
            .post(endpoint.clone())
            .json(&json!({
                "url": url.as_str(),
                "formats": formats,
                "onlyMainContent": true,
                "removeBase64Images": true,
                "timeout": timeout_ms
            }));
        if let Some(api_key) = api_key.filter(|item| !item.trim().is_empty()) {
            request = request.bearer_auth(api_key.trim());
        }
        let response = request.send().map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("firecrawl scrape failed: {err}"),
            )
        })?;
        let status = response.status().as_u16();
        let text = response.text().map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("read firecrawl scrape response failed: {err}"),
            )
        })?;
        if !(200..300).contains(&status) {
            let (body, truncated) = truncate_chars(&text, 2_000);
            return Err(ToolError::new(
                "tool.execution_failed",
                format!(
                    "firecrawl scrape returned http status {status}: {}{}",
                    body,
                    if truncated { "..." } else { "" }
                ),
            ));
        }
        let payload: Value = serde_json::from_str(&text).map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("firecrawl scrape response is not valid json: {err}"),
            )
        })?;
        if let Some(document) = normalize_firecrawl_scrape_document(&payload, url) {
            documents.push(document);
        }
    }
    if documents.is_empty() {
        return Err(ToolError::new(
            "tool.execution_failed",
            "firecrawl extract returned no usable documents",
        ));
    }
    let documents = documents
        .into_iter()
        .enumerate()
        .map(|(index, mut item)| {
            if let Some(object) = item.as_object_mut() {
                object.insert("position".to_string(), json!(index + 1));
                object.insert("source_status".to_string(), json!("extracted_content"));
            }
            item
        })
        .collect::<Vec<_>>();
    let result_count = documents.len();
    Ok((
        json!({
            "backend": "firecrawl",
            "result_count": result_count,
            "documents": documents,
        }),
        format!("web_extract firecrawl 返回 {result_count} 个可用文档"),
    ))
}

fn send_parallel_extract_request(
    api_key: &str,
    urls: &[Url],
    timeout_ms: u64,
) -> Result<Response, ToolError> {
    request_client(timeout_ms)?
        .post("https://api.parallel.ai/v1/extract")
        .header("x-api-key", api_key.trim())
        .json(&json!({
            "urls": urls.iter().map(Url::as_str).collect::<Vec<_>>(),
            "objective": "Extract the main readable page content.",
            "max_chars_total": MAX_EXTRACT_CONTENT_CHARS,
        }))
        .send()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("parallel extract failed: {err}"),
            )
        })
}

fn send_tavily_extract_request(
    api_key: &str,
    urls: &[Url],
    timeout_ms: u64,
) -> Result<Response, ToolError> {
    request_client(timeout_ms)?
        .post("https://api.tavily.com/extract")
        .json(&json!({
            "api_key": api_key,
            "urls": urls.iter().map(Url::as_str).collect::<Vec<_>>(),
            "extract_depth": "basic",
            "include_images": false
        }))
        .send()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("tavily extract failed: {err}"),
            )
        })
}

fn send_exa_extract_request(
    api_key: &str,
    urls: &[Url],
    timeout_ms: u64,
) -> Result<Response, ToolError> {
    request_client(timeout_ms)?
        .post("https://api.exa.ai/contents")
        .header("x-api-key", api_key.trim())
        .json(&json!({
            "ids": urls.iter().map(Url::as_str).collect::<Vec<_>>(),
            "text": true
        }))
        .send()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("exa extract failed: {err}"),
            )
        })
}

fn parallel_search_processor() -> &'static str {
    match env::var("PARALLEL_SEARCH_MODE")
        .unwrap_or_else(|_| "advanced".to_string())
        .trim()
        .to_ascii_lowercase()
        .as_str()
    {
        "fast" | "turbo" => "turbo",
        "one-shot" | "oneshot" | "basic" => "basic",
        "agentic" | "advanced" => "advanced",
        _ => "advanced",
    }
}

fn search_response_to_result(
    backend: &str,
    query: &str,
    response: Response,
    limit: usize,
) -> Result<(Value, String), ToolError> {
    let status = response.status().as_u16();
    let text = response.text().map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("read web search response failed: {err}"),
        )
    })?;
    if !(200..300).contains(&status) {
        let (body, truncated) = truncate_chars(&text, 2_000);
        return Err(ToolError::new(
            "tool.execution_failed",
            format!(
                "web search backend returned http status {status}: {}{}",
                body,
                if truncated { "..." } else { "" }
            ),
        ));
    }
    let payload: Value = serde_json::from_str(&text).map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("web search response is not valid json: {err}"),
        )
    })?;
    let results = normalize_search_results(&payload, limit);
    let result_count = results.len();
    if result_count == 0 {
        return Err(ToolError::new(
            "tool.execution_failed",
            "web search returned no usable http/https results",
        ));
    }
    Ok((
        json!({
            "backend": backend,
            "query": query,
            "result_count": result_count,
            "results": results,
        }),
        format!("web_search {backend} 返回 {result_count} 条可用结果：{query}"),
    ))
}

fn extract_response_to_result(
    backend: &str,
    response: Response,
) -> Result<(Value, String), ToolError> {
    let status = response.status().as_u16();
    let text = response.text().map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("read web extract response failed: {err}"),
        )
    })?;
    if !(200..300).contains(&status) {
        let (body, truncated) = truncate_chars(&text, 2_000);
        return Err(ToolError::new(
            "tool.execution_failed",
            format!(
                "web extract backend returned http status {status}: {}{}",
                body,
                if truncated { "..." } else { "" }
            ),
        ));
    }
    let payload: Value = serde_json::from_str(&text).map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("web extract response is not valid json: {err}"),
        )
    })?;
    let documents = normalize_extract_documents(&payload);
    let result_count = documents.len();
    if result_count == 0 {
        return Err(ToolError::new(
            "tool.execution_failed",
            "web extract returned no usable documents",
        ));
    }
    Ok((
        json!({
            "backend": backend,
            "result_count": result_count,
            "documents": documents,
        }),
        format!("web_extract {backend} 返回 {result_count} 个可用文档"),
    ))
}

fn normalize_search_results(payload: &Value, limit: usize) -> Vec<Value> {
    candidate_search_arrays(payload)
        .into_iter()
        .flat_map(|items| items.iter())
        .filter_map(normalize_search_result_item)
        .take(limit)
        .enumerate()
        .map(|(index, mut item)| {
            if let Some(object) = item.as_object_mut() {
                object.insert("position".to_string(), json!(index + 1));
                object.insert("source_status".to_string(), json!("search_result"));
            }
            item
        })
        .collect()
}

fn normalize_extract_documents(payload: &Value) -> Vec<Value> {
    candidate_extract_arrays(payload)
        .into_iter()
        .flat_map(|items| items.iter())
        .filter_map(normalize_extract_document_item)
        .enumerate()
        .map(|(index, mut item)| {
            if let Some(object) = item.as_object_mut() {
                object.insert("position".to_string(), json!(index + 1));
                object.insert("source_status".to_string(), json!("extracted_content"));
            }
            item
        })
        .collect()
}

fn candidate_extract_arrays(payload: &Value) -> Vec<&Vec<Value>> {
    let mut arrays = Vec::new();
    if let Some(items) = payload.get("results").and_then(Value::as_array) {
        arrays.push(items);
    }
    if let Some(items) = payload
        .get("data")
        .and_then(|value| value.get("results"))
        .and_then(Value::as_array)
    {
        arrays.push(items);
    }
    if let Some(items) = payload
        .get("data")
        .and_then(|value| value.get("documents"))
        .and_then(Value::as_array)
    {
        arrays.push(items);
    }
    if let Some(items) = payload.get("documents").and_then(Value::as_array) {
        arrays.push(items);
    }
    if let Some(items) = payload.get("data").and_then(Value::as_array) {
        arrays.push(items);
    }
    arrays
}

fn normalize_extract_document_item(item: &Value) -> Option<Value> {
    let raw_url = string_field(item, &["url", "source_url", "sourceURL", "link", "href"])?;
    let url = parse_http_url(&raw_url).ok()?;
    let title = string_field(item, &["title", "name"]).unwrap_or_default();
    let content = text_field(
        item,
        &[
            "content",
            "raw_content",
            "markdown",
            "text",
            "body",
            "summary",
            "extract",
            "full_content",
            "excerpts",
        ],
    )?;
    let content_chars = content.chars().count();
    let (content, truncated) = truncate_chars(&content, MAX_EXTRACT_CONTENT_CHARS);
    Some(json!({
        "title": truncate_search_text(&title, 300),
        "url": url.as_str(),
        "content": content,
        "content_chars": content_chars,
        "truncated": truncated
    }))
}

fn normalize_firecrawl_scrape_document(payload: &Value, fallback_url: &Url) -> Option<Value> {
    let data = payload.get("data").unwrap_or(payload);
    let metadata = data.get("metadata").and_then(Value::as_object);
    let raw_url = metadata
        .and_then(|item| item.get("sourceURL").and_then(Value::as_str))
        .or_else(|| metadata.and_then(|item| item.get("url").and_then(Value::as_str)))
        .unwrap_or_else(|| fallback_url.as_str());
    let url = parse_http_url(raw_url).ok()?;
    let title = metadata
        .and_then(|item| item.get("title").and_then(Value::as_str))
        .unwrap_or_default();
    let content = text_field(
        data,
        &["markdown", "html", "content", "text", "raw_content"],
    )?;
    let content_chars = content.chars().count();
    let (content, truncated) = truncate_chars(&content, MAX_EXTRACT_CONTENT_CHARS);
    Some(json!({
        "title": truncate_search_text(title, 300),
        "url": url.as_str(),
        "content": content,
        "content_chars": content_chars,
        "truncated": truncated
    }))
}

fn candidate_search_arrays(payload: &Value) -> Vec<&Vec<Value>> {
    let mut arrays = Vec::new();
    if let Some(items) = payload.get("results").and_then(Value::as_array) {
        arrays.push(items);
    }
    if let Some(items) = payload.get("web").and_then(Value::as_array) {
        arrays.push(items);
    }
    if let Some(items) = payload.get("search_results").and_then(Value::as_array) {
        arrays.push(items);
    }
    if let Some(items) = payload
        .get("data")
        .and_then(|value| value.get("web"))
        .and_then(Value::as_array)
    {
        arrays.push(items);
    }
    if let Some(items) = payload
        .get("data")
        .and_then(|value| value.get("search_results"))
        .and_then(Value::as_array)
    {
        arrays.push(items);
    }
    if let Some(items) = payload
        .get("data")
        .and_then(|value| value.get("results"))
        .and_then(Value::as_array)
    {
        arrays.push(items);
    }
    if let Some(items) = payload.get("data").and_then(Value::as_array) {
        arrays.push(items);
    }
    if let Some(items) = payload.get("items").and_then(Value::as_array) {
        arrays.push(items);
    }
    arrays
}

fn normalize_search_result_item(item: &Value) -> Option<Value> {
    let object = item.as_object()?;
    let raw_url = string_field(item, &["url", "link", "href"])?;
    let url = parse_http_url(&raw_url).ok()?;
    let title = string_field(item, &["title", "name"])
        .unwrap_or_else(|| url.host_str().unwrap_or(url.as_str()).to_string());
    let description = text_field(
        item,
        &[
            "description",
            "snippet",
            "content",
            "summary",
            "text",
            "raw_content",
            "highlights",
            "excerpts",
        ],
    )
    .unwrap_or_default();
    let published_at = string_field(item, &["published_at", "publishedDate", "date"]);
    let mut normalized = serde_json::Map::new();
    normalized.insert(
        "title".to_string(),
        json!(truncate_search_text(&title, 300)),
    );
    normalized.insert("url".to_string(), json!(url.as_str()));
    normalized.insert(
        "description".to_string(),
        json!(truncate_search_text(&description, 1_000)),
    );
    if let Some(published_at) = published_at {
        normalized.insert("published_at".to_string(), json!(published_at));
    }
    if let Some(score) = object.get("score").and_then(Value::as_f64) {
        normalized.insert("score".to_string(), json!(score));
    }
    Some(Value::Object(normalized))
}

fn required_url_array_arg(
    arguments: &Value,
    key: &str,
    max_items: usize,
) -> Result<Vec<Url>, ToolError> {
    let items = arguments
        .get(key)
        .and_then(Value::as_array)
        .ok_or_else(|| {
            ToolError::new(
                "tool.schema_invalid",
                format!("missing required argument: {key}"),
            )
        })?;
    if items.is_empty() {
        return Err(ToolError::new(
            "tool.schema_invalid",
            format!("{key} must not be empty"),
        ));
    }
    if items.len() > max_items {
        return Err(ToolError::new(
            "tool.schema_invalid",
            format!("{key} supports at most {max_items} URLs"),
        ));
    }
    items
        .iter()
        .map(|item| {
            let raw = item.as_str().ok_or_else(|| {
                ToolError::new(
                    "tool.schema_invalid",
                    format!("{key} items must be strings"),
                )
            })?;
            parse_http_url(raw)
        })
        .collect()
}

fn string_field(item: &Value, keys: &[&str]) -> Option<String> {
    keys.iter()
        .filter_map(|key| item.get(*key).and_then(Value::as_str))
        .map(|value| value.trim().to_string())
        .find(|value| !value.is_empty())
}

fn text_field(item: &Value, keys: &[&str]) -> Option<String> {
    keys.iter()
        .filter_map(|key| item.get(*key))
        .filter_map(value_to_text)
        .map(|value| value.trim().to_string())
        .find(|value| !value.is_empty())
}

fn value_to_text(value: &Value) -> Option<String> {
    if let Some(text) = value.as_str() {
        return Some(text.to_string());
    }
    let items = value.as_array()?;
    let joined = items
        .iter()
        .filter_map(|item| {
            item.as_str().map(str::to_string).or_else(|| {
                item.get("text")
                    .and_then(Value::as_str)
                    .or_else(|| item.get("content").and_then(Value::as_str))
                    .map(str::to_string)
            })
        })
        .collect::<Vec<_>>()
        .join("\n\n");
    if joined.trim().is_empty() {
        None
    } else {
        Some(joined)
    }
}

fn truncate_search_text(value: &str, max_chars: usize) -> String {
    if value.chars().count() <= max_chars {
        value.to_string()
    } else {
        value.chars().take(max_chars).collect()
    }
}

fn request_client(timeout_ms: u64) -> Result<Client, ToolError> {
    Client::builder()
        .timeout(Duration::from_millis(timeout_ms))
        .user_agent("liuAgent-desktop-local-runtime/0.1")
        .build()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("create http client failed: {err}"),
            )
        })
}

fn parse_http_url(raw: &str) -> Result<Url, ToolError> {
    let url = Url::parse(raw.trim())
        .map_err(|err| ToolError::new("tool.schema_invalid", format!("invalid url: {err}")))?;
    if !matches!(url.scheme(), "http" | "https") {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "only http and https urls are allowed",
        ));
    }
    Ok(url)
}

fn parse_headers(value: Option<&Value>) -> Result<HeaderMap, ToolError> {
    let mut headers = HeaderMap::new();
    let Some(Value::Object(map)) = value else {
        return Ok(headers);
    };
    for (key, value) in map {
        if is_sensitive_header(key) {
            return Err(ToolError::new(
                "tool.schema_invalid",
                format!("sensitive header is not allowed: {key}"),
            ));
        }
        let Some(raw_value) = value.as_str() else {
            return Err(ToolError::new(
                "tool.schema_invalid",
                format!("header value must be string: {key}"),
            ));
        };
        let name = HeaderName::from_bytes(key.as_bytes()).map_err(|err| {
            ToolError::new("tool.schema_invalid", format!("invalid header name: {err}"))
        })?;
        let header_value = HeaderValue::from_str(raw_value).map_err(|err| {
            ToolError::new(
                "tool.schema_invalid",
                format!("invalid header value: {err}"),
            )
        })?;
        headers.insert(name, header_value);
    }
    Ok(headers)
}

fn response_to_result(
    method: &str,
    url: &str,
    response: Response,
) -> Result<(Value, String), ToolError> {
    let status = response.status().as_u16();
    let headers = safe_response_headers(response.headers());
    let text = response.text().map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("read response failed: {err}"),
        )
    })?;
    let (body, truncated) = truncate_chars(&text, MAX_BODY_CHARS);
    let summary = format!(
        "{method} {url} -> HTTP {status}{}",
        if truncated { "（已截断）" } else { "" }
    );
    Ok((
        json!({
            "status": status,
            "headers": headers,
            "body": body,
            "truncated": truncated
        }),
        summary,
    ))
}

fn safe_response_headers(headers: &HeaderMap) -> Value {
    let mut result = serde_json::Map::new();
    for key in [
        "content-type",
        "content-length",
        "etag",
        "last-modified",
        "cache-control",
    ] {
        if let Some(value) = headers.get(key).and_then(|item| item.to_str().ok()) {
            result.insert(key.to_string(), json!(value));
        }
    }
    Value::Object(result)
}

fn is_sensitive_header(key: &str) -> bool {
    matches!(
        key.to_ascii_lowercase().as_str(),
        "authorization"
            | "cookie"
            | "set-cookie"
            | "proxy-authorization"
            | "x-api-key"
            | "x-auth-token"
    )
}

fn summarize_json_value(value: &Value) -> Value {
    match value {
        Value::String(text) => json!({"type": "string", "chars": text.chars().count()}),
        Value::Array(items) => json!({"type": "array", "items": items.len()}),
        Value::Object(map) => {
            json!({"type": "object", "keys": map.keys().cloned().collect::<Vec<_>>() })
        }
        Value::Null => json!({"type": "null"}),
        Value::Bool(_) => json!({"type": "boolean"}),
        Value::Number(_) => json!({"type": "number"}),
    }
}

fn truncate_chars(value: &str, max_chars: usize) -> (String, bool) {
    if value.chars().count() <= max_chars {
        return (value.to_string(), false);
    }
    (value.chars().take(max_chars).collect(), true)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn temp_workspace(name: &str) -> std::path::PathBuf {
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let dir = std::env::temp_dir().join(format!("liuagent_web_tools_{name}_{now}"));
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    fn write_local_web_tool_config(workspace: &Path, raw: &str) {
        let path = project_web_tool_config_path(workspace);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, raw).unwrap();
    }

    fn write_web_tool_config(path: &Path, raw: &str) {
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, raw).unwrap();
    }

    #[test]
    fn web_search_backend_reports_unconfigured_without_env() {
        let result =
            resolve_web_search_backend_from_values(None, None, None, None, None, None, None, None);

        assert!(result.is_err());
        assert_eq!(result.unwrap_err().code, "web_search.unconfigured");
    }

    #[test]
    fn web_extract_backend_reports_unconfigured_without_env() {
        let result =
            resolve_web_extract_backend_from_values(None, None, None, None, None, None, None, None);

        assert!(result.is_err());
        assert_eq!(result.unwrap_err().code, "web_extract.unconfigured");
    }

    #[test]
    fn web_search_backend_requires_explicit_backend_preference() {
        let managed = resolve_web_search_backend_from_values(
            Some("managed".to_string()),
            Some("https://search.example.test/api".to_string()),
            None,
            None,
            None,
            None,
            None,
            None,
        );
        assert!(managed.is_ok());

        let firecrawl = resolve_web_search_backend_from_values(
            Some("firecrawl".to_string()),
            None,
            None,
            None,
            Some("fc-test".to_string()),
            None,
            None,
            None,
        );
        assert!(matches!(
            firecrawl.unwrap(),
            WebSearchBackend::Firecrawl { .. }
        ));

        let parallel = resolve_web_search_backend_from_values(
            Some("parallel".to_string()),
            None,
            None,
            None,
            None,
            Some("parallel-test".to_string()),
            None,
            None,
        );
        assert!(matches!(
            parallel.unwrap(),
            WebSearchBackend::Parallel { .. }
        ));

        let tavily = resolve_web_search_backend_from_values(
            Some("tavily".to_string()),
            None,
            None,
            None,
            None,
            None,
            Some("tvly-test".to_string()),
            None,
        );
        assert!(tavily.is_ok());

        let exa = resolve_web_search_backend_from_values(
            Some("exa".to_string()),
            None,
            None,
            None,
            None,
            None,
            None,
            Some("exa-test".to_string()),
        );
        assert!(matches!(exa.unwrap(), WebSearchBackend::Exa { .. }));
    }

    #[test]
    fn web_search_backend_preserves_provider_config_but_stays_disabled_without_backend() {
        let firecrawl = resolve_web_search_backend_from_values(
            None,
            None,
            None,
            Some("https://api.firecrawl.dev/v2/search".to_string()),
            Some("fc-test".to_string()),
            None,
            None,
            None,
        );

        assert!(firecrawl.is_err());
        assert_eq!(firecrawl.unwrap_err().code, "web_search.unconfigured");
    }

    #[test]
    fn web_extract_backend_requires_explicit_backend_preference() {
        let managed = resolve_web_extract_backend_from_values(
            Some("managed".to_string()),
            Some("https://extract.example.test/api".to_string()),
            None,
            None,
            None,
            None,
            None,
            None,
        );
        assert!(managed.is_ok());

        let firecrawl = resolve_web_extract_backend_from_values(
            Some("firecrawl".to_string()),
            None,
            None,
            None,
            Some("fc-test".to_string()),
            None,
            None,
            None,
        );
        assert!(matches!(
            firecrawl.unwrap(),
            WebExtractBackend::Firecrawl { .. }
        ));

        let parallel = resolve_web_extract_backend_from_values(
            Some("parallel".to_string()),
            None,
            None,
            None,
            None,
            Some("parallel-test".to_string()),
            None,
            None,
        );
        assert!(matches!(
            parallel.unwrap(),
            WebExtractBackend::Parallel { .. }
        ));

        let tavily = resolve_web_extract_backend_from_values(
            Some("tavily".to_string()),
            None,
            None,
            None,
            None,
            None,
            Some("tvly-test".to_string()),
            None,
        );
        assert!(tavily.is_ok());

        let exa = resolve_web_extract_backend_from_values(
            Some("exa".to_string()),
            None,
            None,
            None,
            None,
            None,
            None,
            Some("exa-test".to_string()),
        );
        assert!(matches!(exa.unwrap(), WebExtractBackend::Exa { .. }));
    }

    #[test]
    fn firecrawl_endpoint_uses_complete_url_without_rewriting_path() {
        let exact_search = Url::parse("https://proxy.example.test/firecrawl/v2/search").unwrap();
        assert_eq!(
            firecrawl_endpoint_url(&exact_search, "search", "v2/search").unwrap(),
            exact_search
        );

        let proxy_search = Url::parse("https://proxy.example.test/custom-search").unwrap();
        assert_eq!(
            firecrawl_endpoint_url(&proxy_search, "search", "v2/search").unwrap(),
            proxy_search
        );
    }

    #[test]
    fn firecrawl_endpoint_appends_default_endpoint_only_for_root_or_version_base() {
        assert_eq!(
            firecrawl_endpoint_url(
                &Url::parse("https://api.firecrawl.dev").unwrap(),
                "search",
                "v2/search",
            )
            .unwrap()
            .as_str(),
            "https://api.firecrawl.dev/v2/search"
        );
        assert_eq!(
            firecrawl_endpoint_url(
                &Url::parse("https://api.firecrawl.dev/v2").unwrap(),
                "search",
                "v2/search",
            )
            .unwrap()
            .as_str(),
            "https://api.firecrawl.dev/v2/search"
        );
        assert_eq!(
            firecrawl_endpoint_url(
                &Url::parse("https://api.firecrawl.dev/v3").unwrap(),
                "search",
                "v2/search",
            )
            .unwrap()
            .as_str(),
            "https://api.firecrawl.dev/v3/search"
        );
    }

    #[test]
    fn explicit_web_backend_preference_selects_configured_provider() {
        let search = resolve_web_search_backend_from_values(
            Some("exa".to_string()),
            Some("https://search.example.test/api".to_string()),
            None,
            None,
            Some("fc-test".to_string()),
            Some("parallel-test".to_string()),
            Some("tvly-test".to_string()),
            Some("exa-test".to_string()),
        )
        .unwrap();
        assert!(matches!(search, WebSearchBackend::Exa { .. }));

        let extract = resolve_web_extract_backend_from_values(
            Some("parallel".to_string()),
            Some("https://extract.example.test/api".to_string()),
            None,
            None,
            Some("fc-test".to_string()),
            Some("parallel-test".to_string()),
            Some("tvly-test".to_string()),
            Some("exa-test".to_string()),
        )
        .unwrap();
        assert!(matches!(extract, WebExtractBackend::Parallel { .. }));
    }

    #[test]
    fn local_web_tool_config_enables_desktop_agent_tools() {
        let dir = temp_workspace("local_config");
        write_local_web_tool_config(
            &dir,
            r#"{
              "backend": "exa",
              "providers": {
                "exa": {
                  "api_key": "exa-local-test"
                }
              }
            }"#,
        );
        let workspace = dir.to_string_lossy().to_string();

        assert!(web_search_configured(&workspace));
        assert!(web_extract_configured(&workspace));
        assert!(matches!(
            resolve_web_search_backend(&workspace).unwrap(),
            WebSearchBackend::Exa { .. }
        ));
        assert!(matches!(
            resolve_web_extract_backend(&workspace).unwrap(),
            WebExtractBackend::Exa { .. }
        ));

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn global_web_tool_config_enables_desktop_agent_tools() {
        let dir = temp_workspace("global_config");
        let global_path = dir.join("global").join("web-tools").join("config.json");
        let project_path = project_web_tool_config_path(&dir);
        write_web_tool_config(
            &global_path,
            r#"{
              "backend": "tavily",
              "providers": {
                "tavily": {
                  "api_key": "tvly-global-test"
                }
              }
            }"#,
        );
        let config = load_web_tool_config_from_paths(Some(&global_path), &project_path).unwrap();

        assert!(matches!(
            resolve_web_search_backend_from_config(&config).unwrap(),
            WebSearchBackend::Tavily { .. }
        ));
        assert!(matches!(
            resolve_web_extract_backend_from_config(&config).unwrap(),
            WebExtractBackend::Tavily { .. }
        ));

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn project_web_tool_config_overrides_global_non_empty_fields() {
        let dir = temp_workspace("project_overrides_global");
        let global_path = dir.join("global").join("web-tools").join("config.json");
        let project_path = project_web_tool_config_path(&dir);
        write_web_tool_config(
            &global_path,
            r#"{
              "backend": "tavily",
              "providers": {
                "tavily": {
                  "api_key": "tvly-global-test"
                },
                "exa": {
                  "api_key": "exa-global-test"
                }
              }
            }"#,
        );
        write_web_tool_config(
            &project_path,
            r#"{
              "backend": "exa",
              "providers": {
                "exa": {
                  "api_key": ""
                }
              }
            }"#,
        );
        let config = load_web_tool_config_from_paths(Some(&global_path), &project_path).unwrap();

        assert!(matches!(
            resolve_web_search_backend_from_config(&config).unwrap(),
            WebSearchBackend::Exa { .. }
        ));

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn missing_local_web_tool_config_does_not_create_template_or_enable_tools() {
        let dir = temp_workspace("missing_config_template");
        let config_path = project_web_tool_config_path(&dir);
        let workspace = dir.to_string_lossy().to_string();

        let result = resolve_web_search_backend(&workspace);

        assert!(result.is_err());
        assert_eq!(result.unwrap_err().code, "web_search.unconfigured");
        assert!(!config_path.exists());
        assert!(!web_search_configured(&workspace));
        assert!(!web_extract_configured(&workspace));

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn invalid_local_web_tool_config_is_not_silently_ignored() {
        let dir = temp_workspace("invalid_config");
        write_local_web_tool_config(&dir, "{not-json");
        let workspace = dir.to_string_lossy().to_string();

        let error = resolve_web_search_backend(&workspace).unwrap_err();

        assert_eq!(error.code, "web_tools.config_invalid");
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn invalid_project_web_tool_config_does_not_fallback_to_global() {
        let dir = temp_workspace("invalid_project_no_fallback");
        let global_path = dir.join("global").join("web-tools").join("config.json");
        let project_path = project_web_tool_config_path(&dir);
        write_web_tool_config(
            &global_path,
            r#"{
              "backend": "exa",
              "providers": {
                "exa": {
                  "api_key": "exa-global-test"
                }
              }
            }"#,
        );
        write_web_tool_config(&project_path, "{not-json");

        let error = load_web_tool_config_from_paths(Some(&global_path), &project_path).unwrap_err();

        assert_eq!(error.code, "web_tools.config_invalid");
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn web_search_unconfigured_result_is_structured_and_recoverable() {
        let (content, summary) = web_search_unconfigured_result("飞书 机器人 获取群成员列表");

        assert_eq!(content["backend"], "unconfigured");
        assert_eq!(content["status"], "unconfigured");
        assert_eq!(content["result_count"], 0);
        assert_eq!(content["recoverable"], true);
        assert!(summary.contains("web_search 未配置"));
    }

    #[test]
    fn web_extract_unconfigured_result_is_structured_and_recoverable() {
        let urls = vec![parse_http_url("https://example.com/doc").unwrap()];
        let (content, summary) = web_extract_unconfigured_result(&urls);

        assert_eq!(content["backend"], "unconfigured");
        assert_eq!(content["status"], "unconfigured");
        assert_eq!(content["result_count"], 0);
        assert_eq!(content["recoverable"], true);
        assert!(summary.contains("web_extract 未配置"));
    }

    #[test]
    fn normalizes_common_search_result_shapes() {
        let payload = json!({
            "data": {
                "results": [
                    {
                        "title": "获取群成员列表",
                        "url": "https://open.feishu.cn/document/example",
                        "snippet": "服务端 API 文档"
                    },
                    {
                        "title": "Bad",
                        "url": "file:///tmp/nope",
                        "snippet": "should be filtered"
                    }
                ]
            }
        });

        let results = normalize_search_results(&payload, 5);

        assert_eq!(results.len(), 1);
        assert_eq!(results[0]["title"], "获取群成员列表");
        assert_eq!(results[0]["position"], 1);
        assert_eq!(results[0]["source_status"], "search_result");
    }

    #[test]
    fn normalizes_provider_search_result_arrays() {
        let payload = json!({
            "data": {
                "web": [
                    {
                        "title": "Exa style",
                        "url": "https://example.com/exa",
                        "highlights": ["first", "second"]
                    },
                    {
                        "title": "Parallel style",
                        "url": "https://example.com/parallel",
                        "excerpts": [{"text": "excerpt"}]
                    }
                ]
            }
        });

        let results = normalize_search_results(&payload, 5);

        assert_eq!(results.len(), 2);
        assert_eq!(results[0]["description"], "first\n\nsecond");
        assert_eq!(results[1]["description"], "excerpt");
    }

    #[test]
    fn normalizes_common_extract_result_shapes() {
        let payload = json!({
            "results": [
                {
                    "title": "接口文档",
                    "url": "https://open.feishu.cn/document/example",
                    "raw_content": "完整正文"
                },
                {
                    "title": "Bad",
                    "url": "file:///tmp/nope",
                    "raw_content": "should be filtered"
                }
            ]
        });

        let documents = normalize_extract_documents(&payload);

        assert_eq!(documents.len(), 1);
        assert_eq!(documents[0]["title"], "接口文档");
        assert_eq!(documents[0]["content"], "完整正文");
        assert_eq!(documents[0]["position"], 1);
        assert_eq!(documents[0]["source_status"], "extracted_content");
    }

    #[test]
    fn normalizes_firecrawl_scrape_document_shape() {
        let payload = json!({
            "success": true,
            "data": {
                "markdown": "正文",
                "metadata": {
                    "title": "Firecrawl 文档",
                    "sourceURL": "https://example.com/firecrawl"
                }
            }
        });
        let fallback_url = parse_http_url("https://example.com/fallback").unwrap();

        let document = normalize_firecrawl_scrape_document(&payload, &fallback_url).unwrap();

        assert_eq!(document["title"], "Firecrawl 文档");
        assert_eq!(document["url"], "https://example.com/firecrawl");
        assert_eq!(document["content"], "正文");
    }

    #[test]
    fn web_extract_url_array_rejects_non_http_urls() {
        let result = required_url_array_arg(
            &json!({"urls": ["https://example.com", "file:///tmp/nope"]}),
            "urls",
            MAX_EXTRACT_URLS,
        );

        assert!(result.is_err());
        assert_eq!(result.unwrap_err().code, "tool.schema_invalid");
    }
}
