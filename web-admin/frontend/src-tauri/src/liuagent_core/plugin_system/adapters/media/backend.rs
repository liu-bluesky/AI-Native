//! 非图片媒体插件共用的后端协议适配器。

use reqwest::blocking::Client;
use reqwest::header::{HeaderMap, HeaderValue, AUTHORIZATION, CONTENT_TYPE};
use reqwest::Url;
use serde_json::{json, Value};
use std::time::Duration;

use crate::liuagent_core::args::{number_arg, required_string_arg, string_arg};
use crate::liuagent_core::types::ToolError;

pub fn execute_media_tool(
    tool_name: &str,
    arguments: &Value,
) -> Result<(Value, String), ToolError> {
    if let Some(validation_error) = arguments
        .get("_media_validation_error")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        return Err(ToolError::new("tool.schema_invalid", validation_error));
    }
    let provider_id = required_string_arg(arguments, "_media_provider_id")?;
    let model_name = required_string_arg(arguments, "_media_model_name")?;
    let operation = string_arg(arguments, "operation", "text_to_video");
    if tool_name == "generate_video"
        && is_openai_provider(&provider_id)
        && matches!(operation.as_str(), "video_modify" | "video_remix")
    {
        return execute_openai_video_edit(arguments, &provider_id, &model_name, &operation);
    }
    let timeout_ms = number_arg(arguments, "timeout_ms", 300_000, 1_000, 900_000) as u64;
    let api_base_url = required_string_arg(arguments, "_backend_api_base_url")?;
    let backend_token = required_string_arg(arguments, "_backend_token")?;
    let project_id = required_string_arg(arguments, "project_id")?;
    let endpoint = media_tool_url(&api_base_url, &project_id)?;
    let body = json!({
        "tool_name": tool_name,
        "provider_id": provider_id,
        "model_name": model_name,
        "prompt": string_arg(arguments, "prompt", ""),
        "operation": operation,
        "input_asset_ids": arguments.get("input_asset_ids").cloned().unwrap_or_else(|| json!([])),
        "media_inputs": arguments.get("_media_inputs").cloned().unwrap_or_else(|| json!([])),
        "reference_images": arguments.get("_reference_images").cloned().unwrap_or_else(|| json!([])),
        "audio_data_url": string_arg(arguments, "_audio_data_url", ""),
        "audio_filename": string_arg(arguments, "_audio_filename", ""),
        "audio_mime_type": string_arg(arguments, "_audio_mime_type", ""),
        "voice": string_arg(arguments, "voice", ""),
        "response_format": string_arg(arguments, "response_format", "wav"),
        "speed": arguments.get("speed").and_then(Value::as_f64).unwrap_or(1.0),
    });
    let response = backend_post_json(
        endpoint,
        &backend_token,
        timeout_ms,
        &body,
        tool_name,
        &provider_id,
        &model_name,
    )?;
    let summary = response
        .get("content")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or("媒体工具执行完成")
        .to_string();
    Ok((response, summary))
}

fn is_openai_provider(provider_id: &str) -> bool {
    matches!(
        provider_id.trim().to_ascii_lowercase().as_str(),
        "openai" | "openai_sora" | "sora"
    )
}

fn execute_openai_video_edit(
    arguments: &Value,
    provider_id: &str,
    model_name: &str,
    operation: &str,
) -> Result<(Value, String), ToolError> {
    let api_key = required_string_arg(arguments, "_media_api_key")?;
    let base_url = required_string_arg(arguments, "_media_base_url")?;
    let prompt = required_string_arg(arguments, "prompt")?;
    let input = arguments
        .get("_media_inputs")
        .and_then(Value::as_array)
        .and_then(|items| items.first())
        .ok_or_else(|| ToolError::new("tool.schema_invalid", "video input is required"))?;
    if input.get("resource_type").and_then(Value::as_str) != Some("provider_video_id") {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "OpenAI video editing requires provider_video_id",
        ));
    }
    let video_id = input
        .get("resource_id")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| ToolError::new("tool.schema_invalid", "OpenAI video ID is required"))?;
    let endpoint = provider_video_edits_url(&base_url)?;
    let payload = provider_post_json(
        endpoint,
        &api_key,
        &json!({"video": {"id": video_id}, "prompt": prompt}),
    )?;
    let task_id = payload
        .get("id")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .trim()
        .to_string();
    Ok((
        json!({
            "content": "OpenAI 视频编辑任务已提交",
            "operation": operation,
            "provider_id": provider_id,
            "model_name": model_name,
            "task_id": task_id,
            "provider_video_id": task_id,
            "input_asset_ids": arguments.get("input_asset_ids").cloned().unwrap_or_else(|| json!([])),
            "provider_response": payload
        }),
        "OpenAI 视频编辑任务已提交".to_string(),
    ))
}

fn provider_video_edits_url(base_url: &str) -> Result<Url, ToolError> {
    let base = Url::parse(base_url.trim()).map_err(|err| {
        ToolError::new(
            "tool.schema_invalid",
            format!("invalid media base url: {err}"),
        )
    })?;
    if !matches!(base.scheme(), "http" | "https") {
        return Err(ToolError::new(
            "tool.schema_invalid",
            "media base url must use http or https",
        ));
    }
    Url::parse(&format!(
        "{}/videos/edits",
        base.as_str().trim_end_matches('/')
    ))
    .map_err(|err| {
        ToolError::new(
            "tool.schema_invalid",
            format!("invalid video edit url: {err}"),
        )
    })
}

fn provider_post_json(endpoint: Url, api_key: &str, body: &Value) -> Result<Value, ToolError> {
    let response = Client::builder()
        .timeout(Duration::from_millis(300_000))
        .user_agent("liuAgent-desktop-local-runtime/0.1")
        .build()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("create provider client failed: {err}"),
            )
        })?
        .post(endpoint)
        .bearer_auth(api_key.trim())
        .json(body)
        .send()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("provider video edit failed: {err}"),
            )
        })?;
    let status = response.status();
    let text = response.text().map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("read provider response failed: {err}"),
        )
    })?;
    let payload = serde_json::from_str::<Value>(&text).unwrap_or_else(|_| json!({"raw": text}));
    if !status.is_success() {
        let detail = payload
            .get("error")
            .and_then(|error| error.get("message"))
            .and_then(Value::as_str)
            .or_else(|| payload.get("message").and_then(Value::as_str))
            .unwrap_or("unknown provider error");
        return Err(ToolError::new(
            "tool.execution_failed",
            format!(
                "provider video edit failed (HTTP {}): {detail}",
                status.as_u16()
            ),
        ));
    }
    Ok(payload)
}

fn media_tool_url(api_base_url: &str, project_id: &str) -> Result<Url, ToolError> {
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
    if !project_id
        .chars()
        .all(|character| character.is_ascii_alphanumeric() || matches!(character, '-' | '_'))
    {
        return Err(ToolError::new("tool.schema_invalid", "invalid project_id"));
    }
    Url::parse(&format!(
        "{clean_base}/projects/{project_id}/chat/media-tool"
    ))
    .map_err(|err| ToolError::new("tool.schema_invalid", format!("invalid backend url: {err}")))
}

fn backend_post_json(
    endpoint: Url,
    backend_token: &str,
    timeout_ms: u64,
    body: &Value,
    tool_name: &str,
    provider_id: &str,
    model_name: &str,
) -> Result<Value, ToolError> {
    let mut headers = HeaderMap::new();
    headers.insert(
        AUTHORIZATION,
        HeaderValue::from_str(&format!("Bearer {}", backend_token.trim())).map_err(|err| {
            ToolError::new(
                "tool.schema_invalid",
                format!("invalid backend auth header: {err}"),
            )
        })?,
    );
    headers.insert(CONTENT_TYPE, HeaderValue::from_static("application/json"));
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
    let endpoint_text = endpoint.to_string();
    let response = client
        .post(endpoint)
        .headers(headers)
        .json(body)
        .send()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!(
                    "媒体模型调用失败：{err}；工具={tool_name}，provider_id={provider_id}，model={model_name}，请求地址={endpoint_text}"
                ),
            )
        })?;
    let status = response.status().as_u16();
    let text = response.text().map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!(
                "读取媒体模型响应失败：{err}；工具={tool_name}，provider_id={provider_id}，model={model_name}，请求地址={endpoint_text}"
            ),
        )
    })?;
    let payload = serde_json::from_str::<Value>(&text).unwrap_or_else(|_| json!({"raw": text}));
    if !(200..300).contains(&status) {
        let detail = extract_error_detail(&payload)
            .or_else(|| {
                payload
                    .get("raw")
                    .and_then(Value::as_str)
                    .map(str::to_string)
            })
            .unwrap_or_else(|| "媒体模型调用失败".to_string());
        return Err(ToolError::new(
            "tool.execution_failed",
            format!(
                "媒体模型调用失败，HTTP {status}：{detail}；工具={tool_name}，provider_id={provider_id}，model={model_name}，请求地址={endpoint_text}"
            ),
        ));
    }
    Ok(payload)
}

fn extract_error_detail(payload: &Value) -> Option<String> {
    let candidates = [
        payload.get("detail"),
        payload.get("message"),
        payload.get("error"),
        payload.get("errors"),
    ];
    candidates
        .into_iter()
        .flatten()
        .find_map(|value| match value {
            Value::String(text) if !text.trim().is_empty() => Some(text.trim().to_string()),
            Value::Object(_) | Value::Array(_) => Some(value.to_string()),
            _ => None,
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extracts_nested_backend_error_details() {
        let detail = extract_error_detail(&json!({
            "detail": {"message": "provider rejected image request", "code": "invalid_model"}
        }));

        assert_eq!(
            detail.as_deref(),
            Some(r#"{"code":"invalid_model","message":"provider rejected image request"}"#)
        );
    }
}
