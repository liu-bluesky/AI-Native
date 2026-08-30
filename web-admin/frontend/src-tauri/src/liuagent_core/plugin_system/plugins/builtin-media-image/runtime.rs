use reqwest::blocking::Client;
use reqwest::Url;
use serde_json::{json, Value};
use std::time::Duration;

use crate::liuagent_core::args::{required_string_arg, string_arg};
use crate::liuagent_core::types::ToolError;

pub fn execute_builtin_media_image_tool(
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
    let model_name = required_string_arg(arguments, "_media_model_name")?;
    let base_url = string_arg(arguments, "_media_base_url", "")
        .trim()
        .to_string();
    let api_key = string_arg(arguments, "_media_api_key", "")
        .trim()
        .to_string();
    if base_url.is_empty() || api_key.is_empty() {
        let provider_id = string_arg(arguments, "_media_provider_id", "");
        return Err(ToolError::new(
            "tool.schema_invalid",
            format!(
                "图片模型缺少桌面直连配置：provider_id={provider_id}，model={model_name}；请重新加载供应商配置后再试"
            ),
        ));
    }
    execute_direct_image_tool(tool_name, &model_name, &base_url, &api_key, arguments)
}

fn execute_direct_image_tool(
    tool_name: &str,
    model_name: &str,
    base_url: &str,
    api_key: &str,
    arguments: &Value,
) -> Result<(Value, String), ToolError> {
    let base = base_url.trim().trim_end_matches('/');
    let path = if tool_name == "edit_image" {
        "/images/edits"
    } else {
        "/images/generations"
    };
    let endpoint = format!("{base}{path}");
    let parsed = Url::parse(&endpoint)
        .map_err(|err| ToolError::new("tool.schema_invalid", format!("图片接口地址无效：{err}")))?;
    let prompt = string_arg(arguments, "prompt", "").trim().to_string();
    if prompt.is_empty() {
        return Err(ToolError::new("tool.schema_invalid", "图片提示词不能为空"));
    }
    let body = build_direct_image_request_body(tool_name, model_name, &prompt, arguments);
    let client = Client::builder()
        .timeout(Duration::from_secs(120))
        .build()
        .map_err(|err| {
            ToolError::new(
                "tool.execution_failed",
                format!("创建图片客户端失败：{err}"),
            )
        })?;
    let mut request = client.post(parsed).bearer_auth(api_key).json(&body);
    if let Some(headers) = arguments
        .get("_media_extra_headers")
        .and_then(Value::as_object)
    {
        for (name, value) in headers {
            if let Some(value) = value.as_str() {
                request = request.header(name, value);
            }
        }
    }
    let response = request.send().map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("图片模型直连失败：{err}，地址={endpoint}"),
        )
    })?;
    let status = response.status();
    let text = response.text().map_err(|err| {
        ToolError::new(
            "tool.execution_failed",
            format!("读取图片响应失败：{err}，地址={endpoint}"),
        )
    })?;
    let payload = serde_json::from_str::<Value>(&text).unwrap_or_else(|_| json!({"raw": text}));
    if !status.is_success() {
        let detail =
            extract_error_detail(&payload).unwrap_or_else(|| text.chars().take(800).collect());
        return Err(ToolError::new(
            "tool.execution_failed",
            format!(
                "图片模型调用失败，HTTP {}：{}，地址={endpoint}",
                status.as_u16(),
                detail
            ),
        ));
    }
    let artifacts = extract_image_artifacts(&payload);
    if artifacts.is_empty() {
        let detail = format!("图片接口请求已成功，但响应结果未提取到图片，地址={endpoint}");
        return Ok((
            json!({
                "ok": true,
                "content": "图片接口已成功响应，但结果解析失败；任务可以继续执行",
                "postProcessError": {
                    "code": "plugin.response_missing_artifacts",
                    "phase": "parse",
                    "message": detail.clone(),
                    "rawResponse": payload
                },
                "artifacts": [],
                "images": []
            }),
            detail,
        ));
    }
    let urls = artifacts
        .iter()
        .filter_map(|item| item.get("content_url").and_then(Value::as_str))
        .map(str::to_string)
        .collect::<Vec<_>>();
    Ok((
        json!({"ok": true, "content": "图片生成成功", "artifacts": artifacts, "images": urls}),
        "图片生成成功".to_string(),
    ))
}

fn build_direct_image_request_body(
    tool_name: &str,
    model_name: &str,
    prompt: &str,
    arguments: &Value,
) -> Value {
    let mut body = json!({"model": model_name, "prompt": prompt, "n": 1});
    if tool_name != "edit_image" {
        return body;
    }
    let images = arguments
        .get("_reference_images")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|reference| {
            if reference.is_object() {
                return Some(reference.clone());
            }
            reference
                .as_str()
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .map(|image_url| json!({"image_url": image_url}))
        })
        .collect::<Vec<_>>();
    body["images"] = json!(images);
    body
}

fn extract_image_artifacts(payload: &Value) -> Vec<Value> {
    payload
        .get("data")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|item| {
            if let Some(url) = item
                .get("url")
                .and_then(Value::as_str)
                .filter(|value| !value.trim().is_empty())
            {
                Some(json!({"asset_type":"image","content_url":url,"preview_url":url,"title":"图片生成结果"}))
            } else if let Some(data) = item
                .get("b64_json")
                .and_then(Value::as_str)
                .filter(|value| !value.trim().is_empty())
            {
                let url = format!("data:image/png;base64,{data}");
                Some(json!({"asset_type":"image","content_url":url,"preview_url":url,"title":"图片生成结果"}))
            } else {
                None
            }
        })
        .collect()
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
    fn media_validation_error_stops_before_provider_execution() {
        let error = execute_builtin_media_image_tool(
            "edit_image",
            &json!({"_media_validation_error": "input_asset_ids is required"}),
        )
        .unwrap_err();

        assert_eq!(error.code, "tool.schema_invalid");
        assert_eq!(error.message, "input_asset_ids is required");
    }

    #[test]
    fn edit_image_wraps_reference_urls_in_image_objects() {
        let body = build_direct_image_request_body(
            "edit_image",
            "image-model",
            "制作产品海报",
            &json!({
                "_reference_images": [
                    "data:image/png;base64,abc",
                    {"file_id": "file-123"}
                ]
            }),
        );

        assert_eq!(
            body["images"],
            json!([
                {"image_url": "data:image/png;base64,abc"},
                {"file_id": "file-123"}
            ])
        );
    }
}
