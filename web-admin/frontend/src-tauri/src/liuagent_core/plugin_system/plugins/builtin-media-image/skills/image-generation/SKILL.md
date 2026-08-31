# generate_image

## 作用

根据用户明确的描述生成新的图片、插图、海报、图标或其他视觉素材。

## 选择时机

- 用户要求创作一张新的图片或视觉素材。
- 用户提供了新的主体、场景、风格、构图、比例或输出要求。

## 执行方式

- 提取用户的主体、场景、风格、构图、比例和输出要求。
- 使用 `builtin.media.image.generate` 能力调用 `generate_image`。
- `generate_image` 只允许传入文字 `prompt`，不得传入参考图、`input_asset_ids`、`reference_asset_ids`、文件路径、URL 或供应商 `file_id`。
- 生成完成后只根据真实工具结果反馈，不要假报成功。

## 边界

- 用户要求基于已有图片生成、重绘或修改时，一律使用图片编辑 Skill 和 `edit_image`，不要用 `generate_image` 模拟图生图。
- 不要用 `run_command`、脚本或图片库替代供应商图片生成能力。
- 如果供应商或模型配置不可用，应如实说明失败原因。
