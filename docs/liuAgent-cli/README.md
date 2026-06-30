# liuAgent CLI 智能体

liuAgent CLI 是一个面向本地执行的智能体运行时。它的重点不是把 CLI 做成唯一入口，而是沉淀一套可被 CLI、Web、Desktop 共同复用的 Agent Core、工具协议、权限协议、事件协议和状态恢复机制。

一句话概括：模型负责理解和决策，Core 负责编排执行，工具负责落地动作，权限和状态系统负责让执行过程可控、可审计、可恢复。

## 设计目标

- 让智能体能真正调用工具完成任务，而不只是聊天。
- 让同一套 Agent Core 可以接入终端、网页和桌面端。
- 让文件修改、命令执行、网络请求、MCP 调用等动作都有权限边界。
- 让运行过程可以通过事件、审计日志和状态快照追踪。
- 让长任务可以中断恢复，并保留任务树、上下文和执行进度。

## 整体运行逻辑

```text
User Input
  -> Agent Core
  -> Model Runtime
  -> Tool Call
  -> Permission Gate
  -> Tool Runtime
  -> Observation
  -> Model Continuation
  -> Final Answer / Next Tool Call
```

模型只产生意图，例如要读文件、搜索代码、执行命令或调用 MCP。真正的执行由运行时接管：先校验工具、参数和权限，再执行工具，并把结果转成 observation 回给模型继续推理。

## 功能节点设计逻辑

### Agent Core

Agent Core 是智能体主循环，负责接收用户输入、调用模型、解析 tool call、推进执行状态和生成最终输出。它不绑定 CLI、网页或桌面端，也不直接处理 UI 交互。

这样设计是为了把“智能体能力”从“展示形态”里拆出来，让不同入口共享同一套执行逻辑。

### Model Runtime

Model Runtime 负责和模型交互，包括上下文组织、工具定义注入、模型输出解析和多轮 continuation。模型决定下一步要不要调用工具，但不能绕过运行时直接执行动作。

它的边界是推理，不负责权限、状态持久化或本地系统调用。

### Tool Runtime

Tool Runtime 负责工具注册、参数校验、执行调度和结果封装。文件、命令、网络、MCP、插件工具都走同一条链路。

这样可以避免不同工具各自实现权限和返回格式，保证工具结果能被模型、UI 和审计系统一致消费。

### Permission Gate

Permission Gate 是所有高风险动作前的权限闸门。写文件、执行命令、删除、覆盖、网络写入、打开外部链接、部署、发送消息等操作都必须先经过它判断。

它的目标不是阻止智能体做事，而是让每次有影响的动作都有明确对象、风险、范围和用户决策记录。

### Event Bus

Event Bus 把 Core 内部状态变化转换成结构化事件，例如模型输出增量、工具开始、工具完成、需要审批、打开链接、状态变化等。

CLI 可以把事件打印到终端，Web 可以渲染成按钮和时间线，Desktop 可以弹窗或发系统通知。这样多端体验不同，但底层协议一致。

### Session State

Session State 记录会话、消息、运行状态、工具调用、审批请求、checkpoint 和 transcript。它让智能体知道当前执行到哪里，也支持中断后的恢复和回放。

对长任务来说，状态不是附属能力，而是保证可靠性的核心节点。

### Planning Mechanism

规划机制在执行前判断需求是否清晰，并按任务类型生成计划或任务树。查询类问题可以直接回答；涉及修改、部署、写入或高风险动作时，需要先形成计划和确认边界。

它解决的问题是：智能体不能机械套用“分析、实现、验证”，而应该根据真实任务对象拆出可执行、可验证的步骤。

### Adapter

Adapter 是入口适配层。CLI Adapter 负责终端输入输出，Web Adapter 负责浏览器交互，Desktop Adapter 负责本机能力和本地 Runner。

Adapter 不应该承载核心业务逻辑。它只负责把用户输入交给 Core，并把 Core 输出的事件转换成当前端可用的交互形式。

### Agent Gateway

Agent Gateway 是 ProjectChat、桌面端、CLI 和外部系统进入 Agent Core 的统一入口。它负责创建调用上下文，绑定项目、会话、智能体、workspace 和 MCP 需求记录。

它让外部系统可以标准化接入本地智能体，同时保持本地工具执行仍由用户机器或本地 Runner 承担。

## 为什么这样拆分

这套节点划分遵循三个原则：

1. 能力和入口分离：Core 负责智能体能力，CLI/Web/Desktop 只是不同入口。
2. 推理和执行分离：模型提出意图，运行时负责校验、授权、执行和审计。
3. 状态和事件优先：所有关键过程都要能被 UI 展示、被日志追踪、被中断恢复。

最终目标是让 liuAgent CLI 从一个终端工具演进成稳定的本地智能体内核：既能完成真实任务，也能在权限、安全、恢复和多端接入上保持可控。

## 相关文档

- [项目设计](./PROJECT_DESIGN.md)
- [详细设计目录](./design/README.md)
- [核心对象](./design/01-core-objects.md)
- [工具系统](./design/02-tool-system.md)
- [事件协议](./design/03-event-protocol.md)
- [权限审计](./design/04-permission-audit.md)
- [规划机制](./design/16-planning-mechanism.md)
