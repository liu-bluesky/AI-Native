warning: unused import: `types::BotChatRequest`
--> src\bot\mod.rs:13:9
|
13 | pub use types::BotChatRequest;
| ^^^^^^^^^^^^^^^^^^^^^
|
= note: `#[warn(unused_imports)]` (part of `#[warn(unused)]`) on by default
warning: unused imports: `Command` and `Stdio`
--> src\liuagent_core\runtime.rs:18:20
|
18 | use std::process::{Command, Stdio};
| ^^^^^^^ ^^^^^
warning: unused imports: `DesktopFtpCredentials`, `FTP_CREDENTIALS_VERSION`, and `find_global_ftp_credential`
--> src\liuagent_core\mod.rs:31:5
|
31 | find_global_ftp_credential, global_ftp_credentials_path, parse_ftp_credentials_content,
| ^^^^^^^^^^^^^^^^^^^^^^^^^^
32 | read_global_ftp_credentials, write_global_ftp_credentials, DesktopFtpCredentials,
| ^^^^^^^^^^^^^^^^^^^^^
33 | FTP_CREDENTIALS_VERSION,
| ^^^^^^^^^^^^^^^^^^^^^^^
warning: unused import: `normalize_local_backend_api_base_url`
--> src\liuagent_core\mod.rs:37:60
|
37 | desktop_runtime_root, ensure_desktop_runtime_migrated, normalize_local_backend_api_base_url,
| ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
warning: unused imports: `DesktopProjectCatalog` and `PROJECT_CATALOG_VERSION`
--> src\liuagent_core\mod.rs:41:64
|
41 | read_global_project_catalog, write_global_project_catalog, DesktopProjectCatalog,
| ^^^^^^^^^^^^^^^^^^^^^
42 | DesktopProjectCatalogEntry, PROJECT_CATALOG_VERSION,
| ^^^^^^^^^^^^^^^^^^^^^^^
warning: unused import: `LocalBackendContext`
--> src\liuagent_core\mod.rs:58:52
|
58 | AgentInvocationRequest, AgentInvocationResult, LocalBackendContext, LocalChatAttachment,
| ^^^^^^^^^^^^^^^^^^^
warning: unused variable: `command`
--> src\liuagent_core\tools\process.rs:820:39
|
820 | pub(crate) fn configure_process_group(command: &mut Command) {
| ^^^^^^^ help: if this is intentional, prefix it with an underscore: `_command`
|
= note: `#[warn(unused_variables)]` (part of `#[warn(unused)]`) on by default
warning: unused variable: `pid`
--> src\liuagent_core\tools\process.rs:834:9
|
834 | let pid = child.id();
| ^^^ help: if this is intentional, prefix it with an underscore: `_pid`
warning: unused variable: `pid`
--> src\liuagent_core\tools\process.rs:845:50
|
845 | fn terminate_process_group(child: &Mutex<Child>, pid: u32) -> Result<(), ToolError> {
| ^^^ help: if this is intentional, prefix it with an underscore: `_pid`
warning: unused variable: `pid`
--> src\liuagent_core\tools\process.rs:876:51
|
876 | fn force_kill_process_group(child: &Mutex<Child>, pid: u32) -> Result<(), ToolError> {
| ^^^ help: if this is intentional, prefix it with an underscore: `_pid`
warning: unused variable: `pid`
--> src\liuagent_core\tools\process.rs:908:9
|
908 | let pid = child.id();
| ^^^ help: if this is intentional, prefix it with an underscore: `_pid`
warning: function `find_global_ftp_credential` is never used
--> src\liuagent_core\ftp_credentials.rs:91:8
|
91 | pub fn find_global_ftp_credential(credential_id: &str) -> Result<Option<Value>, String> {
| ^^^^^^^^^^^^^^^^^^^^^^^^^^
|
= note: `#[warn(dead_code)]` (part of `#[warn(unused)]`) on by default
warning: function `prompt_stack_from_model_request` is never used
--> src\liuagent_core\runtime.rs:2543:4
|
2543 | fn prompt_stack_from_model_request(model_request: &ModelStepRequest) -> PromptStack {
| ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
warning: function `build_assistant_content` is never used
--> src\liuagent_core\runtime.rs:3853:4
|
3853 | fn build_assistant_content(
| ^^^^^^^^^^^^^^^^^^^^^^^
warning: function `project_workspace_root_from_tool_result` is never used
--> src\liuagent_core\runtime.rs:5349:4
|
5349 | fn project_workspace_root_from_tool_result(
| ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
warning: function `describe_planned_tool_intent` is never used
--> src\liuagent_core\runtime.rs:5596:4
|
5596 | fn describe_planned_tool_intent(tool: &PlannedLocalTool) -> String {
| ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
warning: function `planned_tool_line_range` is never used
--> src\liuagent_core\runtime.rs:5978:4
|
5978 | fn planned_tool_line_range(arguments: &Value) -> String {
| ^^^^^^^^^^^^^^^^^^^^^^^
warning: function `build_model_request` is never used
--> src\liuagent_core\runtime.rs:8943:4
|
8943 | fn build_model_request(request: &LocalChatRequest, user_message: &str) -> ModelStepRequest {
| ^^^^^^^^^^^^^^^^^^^
warning: function `tool_available_for_request_with_overrides` is never used
--> src\liuagent_core\runtime.rs:10445:4
|
10445 | fn tool_available_for_request_with_overrides(
| ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
warning: function `tool_definitions_for_request_with_web_search_config` is never used
--> src\liuagent_core\runtime.rs:10482:4
|
10482 | fn tool_definitions_for_request_with_web_search_config(
| ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
warning: fields `original_path` and `name` are never read
--> src\liuagent_core\tools\deploy.rs:35:5
|
32 | struct UploadEntry {
| ----------- fields in this struct
...
35 | original_path: String,
| ^^^^^^^^^^^^^
36 | name: String,
| ^^^^
|
= note: `UploadEntry` has a derived impl for the trait `Debug`, but this is intentionally ignored during dead code analysis
warning: function `upload_manifest_arg` is never used
--> src\liuagent_core\tools\deploy.rs:767:4
|
767 | fn upload_manifest_arg(arguments: &Value, source: &UploadSource) -> Result<Value, ToolError> {
| ^^^^^^^^^^^^^^^^^^^
warning: function `manifest_arg` is never used
--> src\liuagent_core\tools\deploy.rs:1303:4
|
1303 | fn manifest_arg(arguments: &Value) -> Result<Value, ToolError> {
| ^^^^^^^^^^^^
warning: field `agent_directory` is never read
--> src\liuagent_core\types.rs:56:9
|
38 | pub struct LocalChatRequest {
| ---------------- field in this struct
...
56 | pub agent_directory: Option<String>,
| ^^^^^^^^^^^^^^^
|
= note: `LocalChatRequest` has a derived impl for the trait `Debug`, but this is intentionally ignored during dead code analysis
warning: function `json_session_path` is never used
--> src\project_chat_store.rs:63:4
|
63 | fn json_session_path(
| ^^^^^^^^^^^^^^^^^
