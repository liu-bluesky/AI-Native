//! 工具参数读取辅助。
//!
//! 这里不做业务兜底，只负责把 JSON 参数按工具 schema 的基本类型读出来。

use serde_json::Value;

use super::types::ToolError;

pub fn required_string_arg(arguments: &Value, key: &str) -> Result<String, ToolError> {
    let value = string_arg(arguments, key, "");
    if value.is_empty() {
        Err(ToolError::new(
            "tool.schema_invalid",
            format!("missing required argument: {key}"),
        ))
    } else {
        Ok(value)
    }
}

pub fn string_arg(arguments: &Value, key: &str, default: &str) -> String {
    arguments
        .get(key)
        .and_then(Value::as_str)
        .unwrap_or(default)
        .trim()
        .to_string()
}

pub fn number_arg(arguments: &Value, key: &str, default: i64, minimum: i64, maximum: i64) -> i64 {
    arguments
        .get(key)
        .and_then(|value| {
            value
                .as_i64()
                .or_else(|| value.as_u64().map(|item| item as i64))
        })
        .unwrap_or(default)
        .clamp(minimum, maximum)
}

pub fn bool_arg(arguments: &Value, key: &str, default: bool) -> bool {
    arguments
        .get(key)
        .and_then(Value::as_bool)
        .unwrap_or(default)
}
