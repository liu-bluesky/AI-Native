# Claude Code 适配说明

在 Claude Code 中使用时：

1. 遵循项目根目录 `CLAUDE.md` 的 MCP、会话、权限和工作流规则。
2. 将 `harness-agent/AGENT.md` 作为项目级角色补充，而不是替换 `CLAUDE.md`。
3. 按需读取 `harness-agent/skills/` 下的技能文件。
4. 不把技能全文内联到宿主提示词；引用路径即可。
5. 发现 MCP 不可用时，继续执行本地分析，但明确记录未完成的远端闭环。
