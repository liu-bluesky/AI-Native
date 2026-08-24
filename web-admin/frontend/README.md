# LT code 桌面端打包

在 macOS 上分别执行以下两条命令，可构建同一版本的 macOS `.dmg` 与 Windows 64 位 `.exe` 安装包：

```bash
npm run release:lt-code:mac
npm run release:lt-code:windows
```

两个打包命令都会使用当前项目版本，不会自动递增或修改版本文件。`release:lt-code:mac` 构建三个 macOS `.dmg` 安装包；`release:lt-code:windows` 使用当前版本触发 GitHub Actions 的 Windows 构建、等待完成并下载 `.exe`。请先运行 macOS 命令，再运行 Windows 命令。

需要发布新版本时，请先手动更新版本号：

```bash
node ./scripts/set-desktop-version.mjs --version 0.1.5
```

`npm run release:lt-code` 保留原有行为，会连续构建 macOS 和 Windows 安装包。

安装包输出到 `发布包/LT code v<版本>/`，包含以下目录：

- `macOS · 通用`
- `macOS · Apple 芯片`
- `macOS · Intel`
- `Windows · 64 位`

根目录的 `SHA256SUMS.txt` 包含全部安装包的 SHA-256 校验值。

## 首次使用

1. 将 `.github/workflows/package-windows-exe.yml` 提交并推送到 GitHub 的当前分支。
2. 在 macOS 上执行 `gh auth login`，让本机可触发和下载 GitHub Actions 构建产物。
3. 确保本机已经安装 Node.js、npm、Rust 和 Xcode Command Line Tools。

Windows 包使用 NSIS 生成 `.exe`，当前流程未包含 macOS 或 Windows 代码签名。
