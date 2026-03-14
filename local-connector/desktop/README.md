# Local Connector Desktop

这个目录用于生成普通用户可直接安装的桌面包。

## 产物

- macOS: `dmg`
- Windows: `portable` 和 `nsis exe`

## 打包前准备

1. 先安装连接器运行依赖：

```bash
cd local-connector
npm install --omit=dev
```

2. 再安装 Electron 打包依赖：

```bash
cd local-connector/desktop
npm install
```

3. 构建前会自动同步连接器运行时到 `desktop/runtime/connector`，桌面安装包会直接内置这些依赖，不会在用户机器上执行 `npm install`。

## 打包命令

建议在目标系统上分别打包：

- macOS 包在 macOS 上构建
- Windows 包在 Windows 上构建

开发模式：

```bash
cd local-connector/desktop
npm run dev
```

仅生成目录：

```bash
cd local-connector/desktop
npm run pack
```

Windows 安装包：

```bash
cd local-connector/desktop
npm run dist:win
```

macOS 安装包：

```bash
cd local-connector/desktop
npm run dist:mac
```

同时构建：

```bash
cd local-connector/desktop
npm run dist:all
```

## 打包后目录

桌面包内部会把连接器运行时复制到：

- `resources/connector`

用户运行后产生的数据写到系统用户目录，而不是安装目录：

- 日志目录：`userData/connector-runtime/logs`
- 状态文件：`userData/connector-runtime/.connector-state.json`

## 说明

- 桌面包内置 Electron Runtime，普通用户不需要再安装 Node.js。
- 连接器原生 PTY 依赖会一并打进桌面包。
- 如果后续要做自动更新，再单独接 Electron autoUpdater，不要直接改连接器核心。
