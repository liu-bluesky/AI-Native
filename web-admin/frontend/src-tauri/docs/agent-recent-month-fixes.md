# src-tauri 最近一个月 Agent 问题与功能修复汇总

统计范围：`2026-06-06` 至 `2026-07-06`，路径限定为 `web-admin/frontend/src-tauri`。

数据来源：本地 Git 历史、当前 `src-tauri` 代码结构、`README.md` 和 Rust 测试用例名。写入本文档前，目标目录没有既有未提交改动；本轮新增本文档。

## 总体结论

最近一个月 `src-tauri` 从 Tauri 外部智能体验证入口，演进为一套本地优先的 liuAgent Runtime。核心解决的问题是：Agent 能在用户本机安全读写文件、执行命令、调用 MCP、处理部署，同时具备权限门、状态恢复、失败重试、验收验证和成功声明约束。

本周期相关提交共 16 个。以 `2026-06-09` 初始提交父节点到当前 `HEAD` 统计，`src-tauri` 相关变更覆盖 33 个文件，新增约 35,712 行。主要新增模块集中在：

- `src/liuagent_core/runtime.rs`：本地 Agent Loop、模型调用、状态机、验证门、恢复和事件。
- `src/liuagent_core/tools/`：文件、命令、网络、MCP 和部署工具。
- `src/liuagent_core/permission.rs`：本地权限门。
- `src/liuagent_core/state/mod.rs`：本地 requirement、checkpoint、outbox、runtime state。
- `src/liuagent_core/planning.rs`：任务树/计划节点状态。
- `src/main.rs`：Tauri command 暴露层。
- `README.md`：本地 Runtime 技术方案。

## 时间线

| 日期 | 提交 | 重点 |
| --- | --- | --- |
| 2026-06-09 | `32ca0e7` | 建立 Tauri shell、schema、基础入口，完成外部智能体基本验证。 |
| 2026-06-10 | `c4b1368` | 补充运行环境检测与基础记录能力。 |
| 2026-06-17 | `ebbf3c5` | 打通 AI 部署的手动路径。 |
| 2026-06-18 | `6361a2a` | 兼容 Claude 类外部 agent 入口。 |
| 2026-06-20 | `4ef1159` | 调整项目设计与核心架构文档入口。 |
| 2026-06-22 | `fddfd0c` | 落地 `liuagent_core` 主体：工具定义、权限、状态、Agent Loop、MCP、文件/命令/网络工具。 |
| 2026-06-23 | `e6a41a9` | 推进 Agent 1.0：协议、规划、命令和运行态收敛。 |
| 2026-06-24 | `2423a40` | 强化需求理解、文件工具和状态记录。 |
| 2026-06-26 | `fc3522f` | 基本框架定型，补充 workspace 和运行入口。 |
| 2026-06-26 | `a000daf` | 处理模型/工具超时问题。 |
| 2026-06-27 | `b94b070` | 增加离线版本相关状态和缓存能力。 |
| 2026-06-29 | `8230adf` | 进行状态数据迁移，增强权限和 runtime state。 |
| 2026-06-30 | `26ba39f` | 强化计划/验证/删除设计、命令任务和文件工具可靠性。 |
| 2026-07-01 | `ba245f9` | 部署能力基本走通，新增 `tools/deploy.rs`。 |
| 2026-07-02 | `b3f5f89` | MCP adapter 能力增强，补充 README 和 Tauri MCP 配置入口。 |
| 2026-07-06 | `8c8c1ec` | 强化循环、验证逻辑和大型项目循环执行能力。 |

## 已解决的 Agent 问题

### 1. 本地执行边界不清晰

问题：服务端、前端和本地执行边界容易混在一起，存在让服务端直接访问用户电脑 workspace 的风险。

已解决：

- 明确采用 `local-first`：文件读写、命令执行、patch、MCP 调用都在 Tauri/Rust 本机 runtime 执行。
- `workspace.rs` 做 workspace 路径校验，限制绝对路径逃逸和 `../` 逃逸。
- `definitions.rs` 为每个工具声明 `action`、`risk`、`scope` 和 `requires_approval`。
- `README.md` 明确禁止 Docker 服务端直接访问用户电脑 workspace。

主要证据：`README.md`、`workspace.rs`、`definitions.rs`、`permission.rs`。

### 2. 高风险工具缺少权限门

问题：写文件、执行命令、HTTP 写入、下载和 MCP 调用等高风险操作需要用户确认，否则 agent 容易越权执行。

已解决：

- `write_file`、`apply_patch`、`delete_file`、`run_command`、`http_post`、`download_file`、`call_mcp_tool` 等工具设置为需要授权。
- 权限决策支持 `approve_once` 与 `approve_session`。
- session 级授权绑定 action 和 request_id，避免无 request_id 的授权伪造绕过权限门。
- runtime 能记录 `waiting_approval`、待处理 tool call 和恢复后的继续执行状态。

主要验证用例：

- `agent_loop_stops_when_permission_is_required`
- `permission_continuation_replays_pending_tool_from_runtime_state`
- `agent_loop_reuses_session_permission_for_same_action`
- `agent_loop_session_permission_survives_replayed_tool_call_id_change`
- `agent_loop_approve_once_does_not_survive_replayed_tool_call_id_change`

### 3. `write_file` 缺 `content` 或参数错误导致循环失败

问题：模型调用 `write_file` 时可能缺 `content`、路径不完整、内容格式不符合 schema，之前容易进入无效循环或执行半成品写入。

已解决：

- `write_file` schema 明确 `path` 和 `content` 必填，并在描述中给出示例。
- Agent Loop 在执行前预检查写文件参数，缺内容时不执行写入。
- `write_file` 缺少 `path` 时返回 schema 错误，由模型重新生成完整结构化工具参数；Runtime 不再从自然语言猜测路径。
- 对批量写文件，任一写入参数无效时阻断整批有副作用操作。
- 当模型把 JSON 对象误当作内容时，支持编译为字符串内容；但非 JSON 的结构化内容仍保持严格。
- 对文件修改后的最终回复增加失败提示，避免 agent 声称已完成但文件未真正变更。

主要验证用例：

- `agent_loop_preflights_write_file_missing_content_before_execution`
- `agent_loop_compiles_json_object_content_for_batched_write_files`
- `agent_loop_keeps_non_json_write_file_structured_content_strict`
- `agent_loop_blocks_mutating_batch_when_one_write_file_schema_is_invalid`
- `successful_model_summary_gets_file_mutation_failure_footer`

### 4. Agent 修改后缺少验证闭环

问题：Agent 可能写完文件就结束，未运行项目验证；也可能验证失败后仍然输出“完成”。

已解决：

- 增加 acceptance gate：文件变更后必须有可接受验证证据。
- 能发现项目验证命令并在变更后执行。
- 验证命令非 0 时拒绝通过。
- 如果变更已验证，即使后续有可恢复失败，也允许最终总结。
- verification report 会记录被权限阻断的副作用目标。

主要验证用例：

- `agent_loop_acceptance_gate_reprompts_after_file_mutation_without_verification`
- `acceptance_gate_passes_when_project_verification_runs_after_mutation`
- `acceptance_gate_rejects_nonzero_project_verification_exit_code`
- `agent_loop_allows_final_after_verified_mutation_even_with_later_recoverable_failure`
- `verification_report_records_blocked_side_effect_targets`

### 5. 失败重试和循环策略不稳定

问题：大型项目中 agent 经常需要多轮搜索、读取、修复、验证。旧逻辑容易过早停止，或在相同失败策略上无意义循环。

已解决：

- 取消简单按 tool call 数量强制停止。
- 查询/探索类任务允许多轮读取和搜索。
- 实现类任务不会强制要求产生副作用才能给证据。
- 如果同一失败策略重复出现，会暂停并把失败签名反馈给模型。
- 模型尝试在失败后直接结束时，runtime 会 reprompt。
- 读取路径失败会路由到搜索策略。
- recoverable MCP 配置错误不会立即导致整轮停止。
- 模型超时支持最多 5 次重试，非超时错误不盲目重试。

主要验证用例：

- `agent_loop_does_not_stop_on_tool_call_count`
- `agent_loop_allows_many_exploration_rounds_for_non_implementation_tasks`
- `agent_loop_can_write_after_many_reads`
- `agent_loop_pauses_when_same_failed_strategy_repeats`
- `agent_loop_reprompts_when_model_tries_to_finish_after_failed_attempt`
- `retry_router_classifies_path_failures_as_search`
- `agent_loop_allows_recoverable_mcp_config_error_before_pausing`
- `model_timeout_retries_five_attempts_then_fails`
- `model_non_timeout_error_does_not_retry`

### 6. 长命令执行容易超时或不可观测

问题：构建、测试、打包和部署命令可能运行很久。短超时会误杀任务，且用户看不到命令进度。

已解决：

- `run_command` 的 `timeout_ms` 支持小时级，最大 21,600,000ms。
- 长运行命令默认进入更长超时策略。
- 命令输出可流式产生 command trace 和 chunk event。
- 后台命令 job 支持 refresh 和 cancel。
- 防止 refresh/cancel 读取 workspace 外的 state path。

主要验证用例：

- `long_running_commands_default_to_hours_not_seconds`
- `command_timeout_accepts_hour_level_values`
- `long_running_command_timeout_returns_background_job_no_signal`
- `run_command_emits_command_trace_events`
- `run_command_streams_distinct_output_chunk_events`
- `refresh_runtime_job_rejects_state_path_outside_workspace`
- `cancel_runtime_job_marks_running_state_cancelled`

### 7. MCP 调用链路不完整

问题：本地 agent 需要调用项目 MCP 工具和资源，但要兼容 registry 配置、stdio/http/SSE、JSON-RPC、工具列表和资源读取。

已解决：

- 内置工具增加 `list_mcp_tools`、`read_mcp_resource`、`call_mcp_tool`。
- `main.rs` 增加全局和项目 MCP 配置读写入口。
- `tools/mcp.rs` 支持统一配置解析、server/tool flatten、HTTP JSON-RPC、SSE JSON 解析、stdio content-length JSON-RPC。
- `call_mcp_tool` 作为中风险工具需要授权。

主要验证用例：

- `parses_content_length_json_rpc_frames`
- `writes_content_length_json_rpc_request_by_default`
- `resolves_http_server_from_unified_config`

### 8. 部署流程容易误报成功或绕过配置

问题：部署类任务高风险，容易在只上传 artifact 或后端返回 blocked 时，agent 误称“部署成功”；也容易让模型传自定义服务器凭据或自定义命令。

已解决：

- 新增 `get_project_deploy_options`，部署前只读取脱敏配置。
- 新增 `upload_deploy_artifact`，用于只上传部署产物。
- 新增 `deploy_workspace_files_to_target`，用于桌面端直连部署主流程。
- 部署工具只使用项目部署配置和服务端凭据，不接受自定义服务器凭据或自定义远端命令。
- 目录和多文件部署按原文件 multipart 上传，保留相对路径，不强制打 zip。
- 只有返回 `deployment_confirmed_success=true` 或部署状态成功时，才允许回复部署成功。
- 上传成功但未部署成功时，文案会区分 ready artifact 和 deployed。

主要验证用例：

- `deploy_upload_ready_does_not_allow_success_claim`
- `deploy_success_claim_allowed_when_deployment_succeeded`
- `direct_deploy_blocked_does_not_allow_success_claim`
- `deploy_upload_summary_distinguishes_ready_artifact_from_successful_deployment`
- `deploy_upload_summary_reports_success_only_for_successful_deployment`
- `direct_deploy_summary_reports_success_only_for_success`
- `directory_artifact_path_builds_directory_upload_manifest`
- `artifact_paths_preserve_relative_paths_from_artifact_root`

### 9. 状态恢复、离线缓存和 outbox 不完整

问题：桌面端 agent 中断、离线或等待授权后，需要恢复上下文；同时要把本地状态和服务端同步事件区分开。

已解决：

- Tauri command 暴露 `liuagent_recover_runtime_state`、`liuagent_refresh_runtime_job`、`liuagent_cancel_runtime_job`。
- 暴露 `liuagent_list_runtime_events`、`liuagent_list_runtime_outbox`、`liuagent_ack_runtime_outbox`。
- 暴露 `liuagent_save_offline_cache`、`liuagent_load_offline_cache`、`liuagent_cleanup_offline_cache`。
- 本地 requirement、runtime state、checkpoint、outbox 和 audit 摘要都有持久化路径。
- 恢复判断会包含后台 job、等待授权、失败状态和下一步建议。

主要证据：`runtime.rs` 中 recovery/outbox/offline cache 入口，`state/mod.rs` 的本地状态持久化结构，`main.rs` 的 Tauri command 注册。

### 10. 模型网关和 OpenAI-compatible 调用可观测性不足

问题：直接模型调用失败时容易被统一描述成连接超时；流式响应、tool calls、reasoning 内容和附件也容易丢失上下文。

已解决：

- 支持 OpenAI-compatible `/chat/completions` 和流式解析。
- 支持 Ollama 无 API key 模式。
- 支持文本和图片附件路由，并在 local extract 模式下降级图片 URL。
- 保留 assistant reasoning content 到工具观察 continuation。
- 模型网关诊断包含 payload size、工具完整性、错误 body 和 headers。
- 失败后不会把最终 assistant 内容包装成成功结果。

主要验证用例：

- `direct_model_runtime_calls_openai_compatible_chat_completions`
- `direct_model_runtime_streams_openai_compatible_response`
- `direct_agent_loop_continuation_request_preserves_reasoning_content`
- `permission_resume_continuation_request_preserves_original_reasoning_content`
- `local_chat_attachments_build_text_and_image_parts`
- `local_model_transport_failure_is_not_reported_as_connection_timeout`
- `model_gateway_diagnostic_reports_payload_size_and_tool_integrity`
- `model_failure_assistant_content_does_not_claim_success`

## 已落地的功能点清单

- 本地 liuAgent Runtime：多轮 Agent Loop、工具调用、observation 回传、最终回复。
- 本地工具体系：文件、命令、网络、MCP、部署。
- 权限门：一次授权、会话授权、等待授权恢复。
- 需求处理：清晰度判断、计划确认、任务树/计划节点生成。
- 状态持久化：requirement、transcript、runtime state、checkpoint、audit、outbox。
- 运行事件：message、model call、model step、tool call、tool result、approval required、state changed、progress update。
- 命令执行增强：风险识别、长命令、后台 job、输出流事件、取消/刷新。
- MCP adapter：配置读写、工具列表、资源读取、工具调用、HTTP/SSE/stdio JSON-RPC。
- 部署工具：读取部署配置、上传部署产物、直连目标部署、成功声明保护。
- 离线能力：本地 offline cache 保存、读取、清理。
- 模型调用：OpenAI-compatible、streaming、Ollama、附件和诊断。

## 主要修改文件与职责

| 文件 | 职责 |
| --- | --- |
| `src/liuagent_core/runtime.rs` | Agent Loop、模型调用、状态恢复、验证门、任务处理快照、事件和测试。 |
| `src/liuagent_core/definitions.rs` | 内置工具定义、风险等级、权限要求和 schema。 |
| `src/liuagent_core/tools/file.rs` | 文件读取、搜索、写入、patch、路径策略和 diff。 |
| `src/liuagent_core/tools/command.rs` | 命令风险识别、执行、长任务和输出流。 |
| `src/liuagent_core/tools/mcp.rs` | MCP registry、资源读取、工具调用和多 transport JSON-RPC。 |
| `src/liuagent_core/tools/deploy.rs` | 部署配置读取、部署产物上传、直连部署和部署状态摘要。 |
| `src/liuagent_core/permission.rs` | 权限请求、授权匹配和绕过防护。 |
| `src/liuagent_core/planning.rs` | 任务树节点、状态映射、阻塞恢复条件和文档/修复/部署类计划。 |
| `src/liuagent_core/state/mod.rs` | 本地状态、checkpoint、outbox 和 requirement 记录。 |
| `src/main.rs` | Tauri command 注册与前端桥接。 |
| `README.md` | 本地 runtime 技术方案和边界说明。 |

## 仍需关注的风险

- 文档基于 Git 历史与当前代码静态核对，未在本轮重新跑完整 Rust 测试套件。
- 多数能力已有单元测试名和代码路径支撑，但真实桌面端 E2E 仍依赖前端 UI、Tauri bridge、模型配置和本机权限环境。
- 部署工具已限制成功声明，但生产部署前仍必须走项目部署配置、用户确认和真实后端返回状态。
- MCP adapter 已覆盖多 transport，但具体外部 MCP 服务的鉴权、网络和工具 schema 仍需要按项目配置逐个验证。

## 推荐后续跟进

1. 为 `src-tauri` 增加一条固定回归命令，至少覆盖 `liuagent_core` 单元测试。
2. 将 `write_file` 缺 `content`、权限续跑、部署 blocked 不误报成功纳入桌面端 E2E 用例。
3. 在前端界面增加 runtime state、background job 和 outbox 的可视化入口，降低排查成本。
4. 对 MCP 配置错误、模型网关错误和权限阻塞做统一用户提示规范。
