# builtin-media-image

图片工具插件，使用项目标准 `SKILL.md` 描述 AI 使用规则。

## 目录约定

- `plugin.json`：插件唯一的公开 Manifest。
- `tools/`：Tool 契约和旧执行器映射。
- `skills/`：标准 Skill 正文，不嵌入 Rust。
- `rules/`：插件必须遵守的安全约束。
- `schemas/`：Tool 输入输出 JSON Schema。

Rust 代码只负责把 `plugin.json` 注册进 Plugin Registry；实际图片执行仍由现有 `tools/media.rs` 提供。
