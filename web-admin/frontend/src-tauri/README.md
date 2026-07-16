# 桌面端新开发者入门说明

这份文档写给第一次接触本项目桌面端的开发者。

你不需要提前会 Rust 或 Tauri。先记住一句话：

> 页面使用 Vue 开发，本地电脑能力使用 Rust 开发，Tauri 负责把两者组合成桌面应用。

## 1. 这个目录负责什么

`web-admin/frontend/src-tauri/` 是“AI 员工工厂”桌面应用的本地能力层。

它主要负责浏览器页面不能直接完成的事情，例如：

- 读取和修改用户电脑上的项目文件。
- 在用户电脑上执行命令。
- 调用本地 MCP 工具。
- 运行本地 AI 智能体。
- 弹出文件或目录选择窗口。
- 保存本地会话、权限和执行状态。
- 把本地执行过程通知给 Vue 页面。

页面、按钮、表格和业务交互不在这个目录开发，而是在上一级的 `web-admin/frontend/src/` 中开发。

## 2. 当前系统技术栈

### 2.1 一张表看懂

| 系统部分 | 技术 | 主要语言 | 负责什么 |
|---|---|---|---|
| Web 页面 | Vue 3、Vue Router、Element Plus | JavaScript / Vue | 页面、表单、按钮、项目聊天和管理界面 |
| 前端开发工具 | Vite 5 | JavaScript | 启动前端开发服务器和打包页面 |
| 桌面应用外壳 | Tauri 2 | Rust + JavaScript | 把 Vue 页面变成 macOS、Windows 等桌面应用 |
| 本地能力 | Rust（edition 2021） | Rust | 文件、命令、网络、本地 MCP、权限和状态恢复 |
| 后端 API | FastAPI、Uvicorn | Python 3.10+ | 账号、项目、员工、规则、技能、模型和服务端数据 |
| 服务端存储 | PostgreSQL、Redis | SQL / Python | 业务数据和缓存 |
| 前后端通信 | HTTP、WebSocket | JSON | Vue 页面访问 FastAPI 后端 |
| 页面与桌面通信 | Tauri Command、Tauri Event | JSON | Vue 调用 Rust，Rust 向 Vue 推送执行事件 |

### 2.2 为什么同时有三种语言

项目不是要求每个人同时精通三种语言，而是按职责拆分：

- 修改页面时，主要写 Vue 和 JavaScript。
- 修改后端接口时，主要写 Python。
- 修改本地文件、命令或桌面能力时，才需要写 Rust。

如果你的需求只是修改页面样式或业务展示，通常不需要进入 `src-tauri/`。

## 3. 系统是怎么连接起来的

```text
Vue 页面
  ├── HTTP / WebSocket ──> Python FastAPI 后端
  └── Tauri Command ─────> Rust 本地能力
                              ├── 读取和写入本机文件
                              ├── 执行本机命令
                              ├── 调用本地 MCP
                              └── 保存本地运行状态

Rust 本地能力
  └── Tauri Event ───────> Vue 页面展示进度、授权和结果
```

可以把它理解为：

- Vue 是用户看见和操作的界面。
- FastAPI 是系统的服务端业务中心。
- Rust 是桌面应用在用户电脑上的“手和脚”。
- Tauri 是 Vue 与 Rust 之间的桥梁，也是桌面应用外壳。

## 4. 先认识目录

```text
web-admin/
├── api/                         Python FastAPI 后端
└── frontend/
    ├── src/                     Vue 页面和前端业务
    ├── package.json             前端依赖与 npm 命令
    ├── vite.config.js           Vite 配置和 API 代理
    └── src-tauri/               Tauri 与 Rust 桌面端
        ├── Cargo.toml           Rust 依赖配置
        ├── tauri.conf.json      桌面窗口和构建配置
        ├── check-tauri-shell.mjs 桌面端契约检查脚本
        └── src/
            ├── main.rs          Tauri 启动入口和 Command 注册
            ├── bot/             本地机器人相关能力
            └── liuagent_core/   本地 AI 智能体核心
```

### `liuagent_core/` 主要目录

| 路径 | 作用 |
|---|---|
| `runtime.rs` | 运行本地智能体会话，组织模型调用和工具调用 |
| `types.rs` | 定义前端与 Rust 之间传递的数据结构 |
| `definitions.rs` | 注册本地工具名称、参数和风险信息 |
| `permission.rs` | 处理需要用户确认的本地操作 |
| `workspace.rs` | 检查文件路径是否位于允许的工作区内 |
| `audit.rs` | 生成本地执行审计摘要 |
| `tools/file.rs` | 文件读取、搜索、写入和 patch |
| `tools/command.rs` | 命令识别和执行 |
| `tools/network.rs` | HTTP 请求和文件下载 |
| `tools/mcp.rs` | 本地 MCP 工具和资源调用 |
| `state/` | 保存会话、检查点和恢复状态 |

第一次看代码时，不建议从头阅读整个 `main.rs`。先根据需求找到对应工具文件，再查看它在 `main.rs` 中注册的 Tauri Command。

## 5. 第一次运行桌面端

### 5.1 需要准备的环境

- Node.js 和 npm：安装前端依赖、启动 Vue 和调用 Tauri CLI。
- Rust 工具链：编译 `src-tauri/` 下的 Rust 代码。
- 当前操作系统所需的 Tauri 编译环境。
- Python 3.10+：需要同时启动后端 API 时使用。

如果普通前端页面可以启动，但 `npm run tauri:dev` 失败，通常先检查 Rust 和操作系统编译环境，而不是检查 Vue 代码。

### 5.2 启动后端 API

桌面页面需要访问后端业务数据时，先启动 API。项目后端默认使用 `8000` 端口。

```bash
cd web-admin/api
uv sync
uv run python server.py
```

如果本地已经准备好 Python 虚拟环境，也可以按根目录 `README.md` 中的后端启动方式运行。

### 5.3 启动桌面应用

另开一个终端：

```bash
cd web-admin/frontend
npm install
npm run tauri:dev
```

这个命令会自动完成两件事：

1. 使用 Vite 在 `http://127.0.0.1:3000` 启动 Vue 页面。
2. 编译 Rust，并打开 Tauri 桌面窗口。

前端开发服务器会把 `/api` 和 `/mcp` 请求代理到后端，默认目标是 `http://127.0.0.1:8000`。

如果后端不在默认地址，可以设置：

```bash
VITE_API_PROXY_TARGET=http://127.0.0.1:8000 npm run tauri:dev
```

## 6. 常用开发命令

以下命令都从 `web-admin/frontend/` 开始执行，除非命令中另有说明。

### 只开发 Vue 页面

```bash
npm run dev
```

这个模式运行在浏览器中，适合页面布局和普通后端接口开发。依赖 Tauri 本地能力的功能可能无法使用。

### 开发完整桌面应用

```bash
npm run tauri:dev
```

### 检查桌面端前后端契约

```bash
npm run tauri:check
```

### 检查 Rust 是否可以编译

```bash
cd src-tauri
cargo check
```

### 检查 Rust 格式

```bash
cd src-tauri
cargo fmt --check
```

### 构建前端页面

```bash
npm run build
```

当前 `tauri.conf.json` 中的 `bundle.active` 为 `false`，因此 `npm run tauri:build` 是否生成安装包取决于后续打包配置；不要把它等同于当前已经配置好的正式发布流程。

## 7. 修改功能时应该去哪里

| 你要修改的内容 | 优先查看的位置 |
|---|---|
| 页面、按钮、表单、样式 | `web-admin/frontend/src/` |
| 前端调用后端 API | `web-admin/frontend/src/api/` 或对应页面模块 |
| 后端接口和业务数据 | `web-admin/api/` |
| 桌面窗口名称、大小、开发地址 | `src-tauri/tauri.conf.json` |
| Vue 调用的桌面 Command | `src-tauri/src/main.rs` |
| 本地文件操作 | `src-tauri/src/liuagent_core/tools/file.rs` |
| 本地命令执行 | `src-tauri/src/liuagent_core/tools/command.rs` |
| 本地网络请求或下载 | `src-tauri/src/liuagent_core/tools/network.rs` |
| 本地 MCP 调用 | `src-tauri/src/liuagent_core/tools/mcp.rs` |
| 本地操作授权 | `src-tauri/src/liuagent_core/permission.rs` |
| 本地状态恢复 | `src-tauri/src/liuagent_core/state/` 和 `runtime.rs` |
| Rust 依赖 | `src-tauri/Cargo.toml` |
| npm 依赖和脚本 | `web-admin/frontend/package.json` |

## 8. 不会 Rust 时怎么开始

先掌握下面几个项目内概念即可，不需要先系统学习整门语言。

### Tauri Command

Rust 函数加上 `#[tauri::command]` 后，可以注册为前端可调用的桌面命令。

前端发起调用，Rust 完成本地操作，再把可序列化的结果返回给前端。

### Tauri Event

Rust 使用事件主动通知前端，例如：

- 工具开始执行。
- 需要用户授权。
- 执行成功或失败。
- 智能体产生新的进度。

### `serde`

Rust 使用 `Serialize` 和 `Deserialize` 把结构体转换为 JSON，或者从前端 JSON 读取参数。

### `Result` 和错误处理

Rust 经常使用 `Result<成功结果, 错误>` 表示操作可能失败。修改文件、命令和网络能力时，不要只处理成功情况。

建议的阅读顺序：

1. 从 Vue 代码找到调用的 Tauri Command 名称。
2. 在 `src-tauri/src/` 中搜索这个名称。
3. 查看 Command 的输入和返回类型。
4. 再进入 `liuagent_core/tools/` 查看实际执行逻辑。

## 9. 本地执行的安全边界

桌面端拥有读取文件和执行命令的能力，因此必须遵守以下边界：

- 用户电脑上的文件和命令由 Tauri/Rust 在本机执行。
- 服务端不能直接读取或修改用户的本地工作区。
- 文件操作必须限制在当前 workspace 内，不能使用路径逃逸访问其他位置。
- 写文件、执行命令、网络写入和 MCP 工具调用等高风险操作需要经过权限判断。
- 不要从 Vue 页面绕过 Rust 权限逻辑直接实现另一套本地执行入口。
- 不要把本地凭据、完整敏感文件或未过滤的命令输出上传到服务端。

遇到权限问题时，应修复权限判断或调用链，不要通过关闭校验来解决。

## 10. 常见问题

### 页面可以运行，但桌面功能不可用

确认你运行的是：

```bash
npm run tauri:dev
```

`npm run dev` 只启动浏览器页面，没有完整的 Tauri Rust 环境。

### 页面请求后端失败

检查：

- FastAPI 是否已启动。
- 后端是否监听 `8000` 端口。
- `VITE_API_PROXY_TARGET` 是否指向正确地址。
- `vite.config.js` 中 `/api` 和 `/mcp` 的代理配置是否生效。

### 修改 Rust 后编译失败

先运行：

```bash
cd web-admin/frontend/src-tauri
cargo check
```

从第一条 Rust 编译错误开始处理，后面的错误可能只是连带结果。

### 不知道一个桌面功能从哪里进入

先在 Vue 代码和 `src-tauri/src/main.rs` 中搜索功能名、事件名或 Command 名，再进入具体模块。

## 11. 深入阅读

当你已经能启动系统并准备修改底层能力时，再阅读：

- 项目根目录 `README.md`：了解整个系统、后端、前端和桌面端的关系。
- `web-admin/frontend/package.json`：查看真实 npm 依赖和可用命令。
- `web-admin/frontend/vite.config.js`：查看前端端口与 API 代理。
- `src-tauri/tauri.conf.json`：查看桌面窗口和构建配置。
- `src-tauri/Cargo.toml`：查看 Rust 版本和依赖。
- `src-tauri/src/main.rs`：查看 Tauri Command 注册和桌面入口。
- `src-tauri/src/liuagent_core/`：查看本地智能体、工具、权限和状态实现。

如果只是开发普通页面或后端业务，不需要先读完 `liuagent_core/`。
