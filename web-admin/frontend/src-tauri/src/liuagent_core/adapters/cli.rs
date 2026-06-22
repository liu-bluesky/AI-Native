//! CLI adapter helpers.
//!
//! The CLI surface should consume the same AgentRuntimeEvent values as Tauri.
//! This helper keeps the first reusable boundary small: render events as NDJSON
//! without changing core runtime semantics.

use serde_json::Value;

use crate::liuagent_core::types::ToolError;

pub fn runtime_events_to_ndjson(events: &[Value]) -> Result<String, ToolError> {
    let mut output = String::new();
    for event in events {
        let line = serde_json::to_string(event).map_err(|err| {
            ToolError::new(
                "adapter.serialize_failed",
                format!("serialize CLI runtime event failed: {err}"),
            )
        })?;
        output.push_str(&line);
        output.push('\n');
    }
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn renders_runtime_events_as_ndjson() {
        let output = runtime_events_to_ndjson(&[
            json!({"event_id":"evt-1","type":"message"}),
            json!({"event_id":"evt-2","type":"state_changed"}),
        ])
        .expect("render ndjson");
        let lines = output.lines().collect::<Vec<_>>();
        assert_eq!(lines.len(), 2);
        assert!(lines[0].contains("\"evt-1\""));
        assert!(lines[1].contains("\"state_changed\""));
    }
}
