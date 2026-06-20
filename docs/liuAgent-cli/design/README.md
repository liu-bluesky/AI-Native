# liuAgent CLI 详细设计目录

这个目录用于承接 `liuAgent CLI 项目设计` 的细化内容。上层文档说明为什么要做、整体怎么分层；本目录负责把每一层拆成可实现的数据结构、协议、状态和边界。

这里的文档面向后续实现，不写营销说明，也不只写概念。每个分类最终都应该回答三个问题：

- 这个模块负责什么。
- 它和其他模块用什么数据结构通信。
- 哪些行为必须经过权限、审计或状态记录。

## 阅读顺序

建议按下面顺序阅读和补全文档：

1. [README.md](./README.md)：目录索引、名词解释和设计边界。
2. [01-core-objects.md](./01-core-objects.md)：Agent、Session、Message、Step、RunState 等基础对象。
3. [02-tool-system.md](./02-tool-system.md)：工具注册、工具调用、工具结果和工具错误。
4. [03-event-protocol.md](./03-event-protocol.md)：CLI、Web、Desktop 共享的事件结构。
5. [04-permission-audit.md](./04-permission-audit.md)：审批请求、用户决策、审计日志和风险等级。
6. [05-adapter-protocol.md](./05-adapter-protocol.md)：CLI Adapter、Web Adapter、Desktop Adapter 的输入输出。
7. [06-state-storage.md](./06-state-storage.md)：会话状态、运行状态、持久化结构和恢复策略。
8. [07-runtime-schema.md](./07-runtime-schema.md)：运行时枚举、模型交互对象、事件 payload 联合类型。
9. [08-tool-contracts.md](./08-tool-contracts.md)：第一批内置工具的参数、结果、权限和错误契约。
10. [09-state-machine.md](./09-state-machine.md)：Run、工具调用、权限请求和恢复流程的状态机。
11. [10-transport-protocol.md](./10-transport-protocol.md)：Web、Desktop、CLI 连接 Agent Core 的传输协议。
12. [11-security-policy.md](./11-security-policy.md)：权限策略、授权作用域、策略存储和审计规则。
13. [12-test-fixtures.md](./12-test-fixtures.md)：事件回放、审批、恢复和多端一致性的测试夹具。
14. [13-agent-orchestration.md](./13-agent-orchestration.md)：智能体编排、运行时生命周期和规则执行分层。
15. [14-consistency-audit.md](./14-consistency-audit.md)：阶段、事件、审批和工具生命周期的一致性审查与修正记录。

## 当前目录结构

```text
docs/liuAgent-cli/
  README.md
  PROJECT_DESIGN.md
  design/
    README.md
    01-core-objects.md
    02-tool-system.md
    03-event-protocol.md
    04-permission-audit.md
    05-adapter-protocol.md
    06-state-storage.md
    07-runtime-schema.md
    08-tool-contracts.md
    09-state-machine.md
    10-transport-protocol.md
    11-security-policy.md
    12-test-fixtures.md
    13-agent-orchestration.md
    14-consistency-audit.md
```

## 文档分类

| 分类 | 说明 | 主要产物 |
| --- | --- | --- |
| 核心对象 | 描述 agent 运行时最基础的数据模型 | `AgentConfig`、`Session`、`Message`、`RunState` |
| 工具系统 | 描述模型如何调用工具，以及工具如何返回结果 | `ToolDefinition`、`ToolCall`、`ToolResult` |
| 事件协议 | 描述 Core 和不同 UI Adapter 之间如何通信 | `AgentEvent`、`AdapterCommand` |
| 权限审计 | 描述高风险动作如何被拦截、确认和记录 | `PermissionRequest`、`PermissionDecision`、`AuditLog` |
| 适配器协议 | 描述 CLI、Web、Desktop 如何接入同一个 Core | `AdapterInput`、`AdapterOutput` |
| 状态与存储 | 描述会话如何保存、恢复、回放和处理命令幂等 | `SessionState`、`Checkpoint`、`Transcript`、`CommandReceipt` |
| 运行时 Schema | 描述可直接落代码的枚举、模型对象、payload 联合类型和传输对象 | `RunStatus`、`ModelRequest`、`StepPayload`、`AgentEventPayload`、`TransportPayload` |
| 工具契约 | 描述内置工具的参数、结果、权限和错误码 | `FileToolArgs`、`CommandToolArgs`、`McpToolArgs` |
| 状态机 | 描述运行、工具、审批和恢复的状态转移 | Run 状态机、工具调用状态机、权限请求状态机 |
| 传输协议 | 描述 Web、Desktop、CLI 如何连接同一个 Core | `TransportEnvelope`、`ClientHello`、`StreamFrame` |
| 安全策略 | 描述授权作用域、策略命中、持久化和审计要求 | `PolicyRule`、`PermissionGrant`、`SecurityContext` |
| 测试夹具 | 描述可回放样例和跨端验收用例 | `EventFixture`、`ReplayCase`、`AcceptanceMatrix` |
| 智能体编排 | 描述提示词规则、固定流程、状态机和策略引擎如何组合成运行时控制层 | `Agent Orchestration`、`Agent Runtime Lifecycle`、`Policy Engine` |
| 一致性审查 | 描述不同设计阶段的数据结构是否对齐，以及已知逻辑风险 | `ConsistencyIssue`、canonical schema、修正清单 |

## 核心名词

### Agent

Agent 是智能体运行主体。它接收用户输入，调用模型，决定是否调用工具，并把工具结果继续交给模型推理。Agent 不等于 CLI，CLI 只是 Agent 的一种入口。

### Agent Core

Agent Core 是不绑定 UI 的核心运行层。它只关心推理、工具调用、事件输出和状态推进，不直接处理终端输入、网页按钮或桌面弹窗。

### Adapter

Adapter 是接入层。CLI、Web、Desktop 都是 Adapter。它们把用户输入转换成 Core 能理解的结构，也把 Core 输出的事件转换成各自的交互方式。

### CLI Adapter

CLI Adapter 负责终端交互，例如打印输出、读取输入、展示审批问题和显示授权链接。它不应该直接写死工具执行逻辑。

### Web Adapter

Web Adapter 负责浏览器交互，例如按钮审批、打开授权窗口、展示事件流和工具调用状态。它应优先消费事件协议，而不是强行复刻终端文本。

### Desktop Adapter

Desktop Adapter 负责本机能力，例如系统通知、原生弹窗、文件选择器、剪贴板和本地 Runner。因为权限更强，它必须有更严格的审计记录。

### Tool

Tool 是 Agent 可以调用的外部能力，例如读文件、搜索文本、执行命令、访问 HTTP、调用 MCP。Tool 必须声明参数 schema、风险等级和执行边界。

### Tool Registry

Tool Registry 是工具登记表。它告诉模型和运行时当前有哪些工具、每个工具怎么调用、参数格式是什么、是否需要权限确认。

### Tool Runtime

Tool Runtime 是工具执行层。它接收 `ToolCall`，做参数校验、权限检查、实际执行，然后生成 `ToolResult`。

### Tool Call

Tool Call 是模型发出的工具调用请求。它至少应该包含工具名、调用 ID、参数和来源上下文。

### Tool Result

Tool Result 是工具执行后的返回结果。它应该表达成功或失败、结构化数据、文本摘要、错误信息和可审计元数据。

### Event Bus

Event Bus 是 Core 和 Adapter 之间的事件通道。Core 不直接命令网页点按钮或终端打印文本，而是发出事件；Adapter 根据事件决定怎么展示和响应。

### Event

Event 是一次可被 UI 消费的运行时变化，例如需要审批、打开链接、工具开始执行、工具完成、模型输出增量、会话状态变化。

### Permission Gate

Permission Gate 是权限闸门。写文件、执行命令、打开外部链接、删除内容、发送消息、部署等行为都必须先经过它判断是否允许、拒绝或需要用户确认。

### Permission Request

Permission Request 是权限请求对象。它描述要执行什么动作、为什么执行、风险是什么、影响范围是什么、可选决策有哪些。

### Permission Decision

Permission Decision 是用户或策略对权限请求的决定，例如允许、拒绝、允许一次、允许本会话、要求修改后重试。

### Audit Log

Audit Log 是审计日志。它记录谁在什么时候触发了什么动作、用户如何确认、工具执行结果是什么。后续复盘和安全追踪依赖它。

### Session

Session 是一次连续对话和运行上下文。它包含消息、工具调用、事件、权限记录、状态快照和恢复信息。

### Run

Run 是 Session 内的一次 agent 执行过程。一次用户输入可能产生一个 Run；Run 内可能包含多轮模型输出、多个工具调用和多个事件。

### Message

Message 是对话消息。它可以来自用户、模型、工具或系统。Message 用于还原上下文，不等同于事件。

### Observation

Observation 是工具执行后回传给模型的观察结果。它通常由 `ToolResult` 转换而来，用于让模型继续推理。

### State

State 是当前运行状态，例如等待模型输出、等待工具结果、等待用户审批、已完成、失败、已取消。状态必须能被持久化和恢复。

### Checkpoint

Checkpoint 是状态检查点。它用于中断恢复，记录当前执行到哪里、已经产生哪些消息、哪些工具调用还在等待。

### Transcript

Transcript 是完整运行记录。它比普通聊天记录更细，包含消息、事件、工具调用、权限决策和关键状态变化。

### Schema

Schema 是结构定义。工具参数、事件、权限请求和存储对象都应该有明确 schema，避免不同 Adapter 自己猜字段。

### PTY 模式

PTY 模式是把 CLI 当成终端进程接入网页或桌面。它适合快速复原 CLI 交互，但不适合做精细的按钮审批和产品化状态展示。

### Event 模式

Event 模式是让 Core 输出结构化事件，CLI、Web、Desktop 分别渲染。长期主线应该是 Event 模式，因为它能保证多端共享能力。

### MCP

MCP 是外部工具和资源接入协议。liuAgent CLI 可以通过 MCP 获取工具、资源和上下文，但 MCP 只是工具来源之一，不应该侵入 Agent Core 的 UI 逻辑。

### Runner

Runner 是真实执行本地或远程动作的运行器。例如本地命令、文件操作、浏览器动作和桌面能力都可能由 Runner 执行。Runner 必须受 Tool Runtime 和 Permission Gate 约束。

## 数据结构设计原则

数据结构先按运行链路拆分，不按 UI 拆分：

```text
User Input
  -> AdapterInput
  -> Agent Core
  -> Model Request
  -> ToolCall
  -> PermissionRequest
  -> ToolResult
  -> AgentEvent
  -> AdapterOutput
```

这意味着 CLI、Web、Desktop 不应该各自定义一套工具调用结构。它们可以有不同 UI，但必须共用核心对象和事件协议。

## 后续补全文档的规则

新增细分文档时遵守这些规则：

- 每个对象先写用途，再写字段。
- 字段必须说明类型、是否必填、默认值和来源。
- 涉及权限的对象必须说明风险等级和审计字段。
- 涉及跨端展示的对象必须说明 CLI、Web、Desktop 如何消费。
- 涉及存储的对象必须说明是否进入 `SessionState`、`Transcript` 或 `AuditLog`。
