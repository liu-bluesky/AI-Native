# docs 目录索引

## 当前推荐阅读顺序

如果你是第一次接触当前项目，建议按下面顺序阅读：

1. `docs/00-项目总览/PROJECT.md`
2. `docs/30-专项功能方案/项目模块MCP化设计.md`
3. `docs/30-专项功能方案/项目模块MCP联调示例.md`
4. `docs/30-专项功能方案/统一查询MCP联调示例.md`
5. `docs/30-专项功能方案/统一查询MCP升级规划.md`
6. `docs/30-专项功能方案/ClaudeCLI可借鉴能力与MCP升级映射.md`
7. `docs/30-专项功能方案/MCP优先下的Agent运行时补强方案.md`
8. `docs/30-专项功能方案/统一查询MCP开发实施骨架.md`
9. `docs/update/统一查询MCP升级前后对比.md`
10. `docs/总结文档.md`

说明：

- 当前项目默认按 `MCP-first` 理解：主入口是 `项目 MCP` 和 `统一查询 MCP`，AI 对话页面是次要入口。
- 做新功能前，先确认能力是否应沉淀为 MCP 工具、资源、提示词或项目级执行上下文；不要先按聊天框交互倒推平台能力。
- `PROJECT.md` 用于快速理解项目定位、目录结构和主要模块。
- `项目模块MCP化设计.md` 解释项目 MCP 的设计边界、能力范围和调用模型。
- `项目模块MCP联调示例.md` 面向直连项目 MCP 的接入方式。
- `统一查询MCP联调示例.md` 面向只接统一入口的宿主接入方式。
- `统一查询MCP升级规划.md` 面向后续把统一查询 MCP 升级为智能体能力入口的演进路线。
- `ClaudeCLI可借鉴能力与MCP升级映射.md` 用于说明 Claude CLI 哪些能力值得借鉴，以及如何映射到当前 MCP 升级路线。
- `MCP优先下的Agent运行时补强方案.md` 用于说明在当前项目 `MCP-first, Chat-second` 定位下，如何补齐统一运行时、Prompt 装配、Provider 解析、Tool Registry 四层。
- `统一查询MCP开发实施骨架.md` 用于固定阶段顺序、第一批交付范围与开发执行步骤。
- `docs/update/统一查询MCP升级前后对比.md` 用于快速看升级前后能力、页面和边界差异。
- `总结文档.md` 用于按轮次沉淀实际开发进展、验证结果与下一步计划。

## 分类目录

- `00-项目总览`：项目全局入口文档
- `10-平台架构设计`：平台基础设施与架构规范
- `20-产品应用设计`：AI 员工工厂应用层设计
- `30-专项功能方案`：专题方案与功能拆分设计
- `40-数据存储升级`：数据库与存储迁移规划
- `反馈驱动规则升级模块`：独立模块需求与 PRD

## Docker 与部署入口

当前 Docker 部署、镜像打包、服务器迁移统一看 `docker/` 目录，不再分散写在多个说明里：

- `docker/README.md`：完整 Docker 使用说明，包含仓库拉镜像部署和镜像 tar 离线部署
- `docker/README.quick.md`：最短命令速查
- `docker/README.migration.md`：旧服务器到新服务器的数据迁移清单

如果你是按“本地打包镜像 tar -> 上传服务器 -> `docker load` -> 启动”的路径部署，优先看：

- `docker/README.md`
- `docker/README.quick.md`

## 项目协作与 MCP 入口

当前与项目协作相关的对外口径统一如下：

- 当前项目以 MCP 为主入口，`web-admin` 对话框是辅助入口，不作为平台能力优先级的第一判断源。
- `execute_project_collaboration` 是统一协作编排入口，不是固定行业分工路由。
- 是否单人主责、是否需要多人协作以及如何拆分，仍由 AI 结合项目手册、员工手册、规则和工具自主判断。
- 若单个员工已能闭环，应保持单人主责，不为凑分工强拆多人。
- 若需要精细控制执行顺序或参数，应回退到 `list_project_members`、`get_project_runtime_context`、`list_project_proxy_tools`、`invoke_project_skill_tool` 手动编排。

推荐对应文档：

- `docs/30-专项功能方案/项目模块MCP化设计.md`
- `docs/30-专项功能方案/项目模块MCP联调示例.md`
- `docs/30-专项功能方案/统一查询MCP联调示例.md`
- `docs/30-专项功能方案/统一查询MCP升级规划.md`
- `docs/30-专项功能方案/ClaudeCLI可借鉴能力与MCP升级映射.md`
- `docs/30-专项功能方案/MCP优先下的Agent运行时补强方案.md`
- `docs/30-专项功能方案/统一查询MCP开发实施骨架.md`
- `docs/update/统一查询MCP升级前后对比.md`
- `docs/总结文档.md`

## 已迁移文档

- `docs/00-项目总览/PROJECT.md`
- `docs/10-平台架构设计/AI-Native开发平台设计规范.md`
- `docs/20-产品应用设计/AI-员工工厂设计规范.md`
- `docs/20-产品应用设计/官网介绍页面方案.md`
- `docs/30-专项功能方案/功能分割设计.md`
- `docs/30-专项功能方案/文件资产系统开发计划.md`
- `docs/30-专项功能方案/文件资产系统/README.md`
- `docs/30-专项功能方案/文件资产系统/阶段推进计划.md`
- `docs/30-专项功能方案/文件资产系统/短片导出与正式渲染方案.md`
- `docs/30-专项功能方案/文件资产系统/正式导出任务模型设计.md`
- `docs/30-专项功能方案/项目模块MCP化设计.md`
- `docs/30-专项功能方案/项目模块MCP联调示例.md`
- `docs/30-专项功能方案/统一查询MCP联调示例.md`
- `docs/30-专项功能方案/统一查询MCP升级规划.md`
- `docs/30-专项功能方案/ClaudeCLI可借鉴能力与MCP升级映射.md`
- `docs/30-专项功能方案/统一查询MCP开发实施骨架.md`
- `docs/update/统一查询MCP升级前后对比.md`
- `docs/总结文档.md`
- `docs/30-专项功能方案/项目类型与素材库方案.md`
- `docs/30-专项功能方案/外部Agent托管模式设计.md`
- `docs/40-数据存储升级/PostgreSQL升级规划.md`
