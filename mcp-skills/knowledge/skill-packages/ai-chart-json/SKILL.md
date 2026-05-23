---
name: ai-chart-json
description: Create import-ready BI Design chart component JSON from user chart requirements or data, especially when users ask AI to generate charts, dashboards, ECharts options, or reusable chart JSON that can be directly imported into the designer without creating new page components.
---

# AI Chart JSON

Use this skill to turn a user's chart intent and data into a BI Design component JSON object that renders through the existing `JsonChart` component.

## Output Goal

Return an import-ready component JSON object. Do not create Vue pages or new chart components unless the user explicitly asks for runtime code changes.

## Fixed Component Contract

Use these fields exactly:

- `key`: `JsonChart`
- `chartConfig.key`: `JsonChart`
- `chartConfig.chartKey`: `VJsonChart`
- `chartConfig.conKey`: `VCJsonChart`
- `chartConfig.title`: `JSON 通用图表`
- `chartConfig.category`: `Mores`
- `chartConfig.categoryName`: `更多`
- `chartConfig.package`: `Charts`
- `chartConfig.chartFrame`: `echarts`
- `option`: full ECharts option JSON

Runtime implementation paths:

- Renderer: `src/packages/components/Charts/Mores/JsonChart/index.vue`
- Default config class: `src/packages/components/Charts/Mores/JsonChart/config.ts`
- Metadata: `src/packages/components/Charts/Mores/JsonChart/index.ts`
- Registration: `src/packages/components/Charts/Mores/index.ts`

## Workflow

1. Identify chart type, dimensions, measures, labels, and visual constraints from the user request.
2. Choose an ECharts option shape that matches the requested chart.
3. Put all chart behavior under `option`; keep the component identity fields fixed.
4. Include `attr`, `styles`, `preview`, `status`, `request`, `filter`, and `events` only when the target import flow needs a full component object.
5. Generate a fresh system-style component `id` for every full component JSON.
6. Prefer `dataset.dimensions` and `dataset.source` for tabular data so later data replacement is simple.
7. Validate the JSON is parseable and contains no comments, trailing commas, functions, or expressions.
8. Return only JSON when the user asks for directly importable content.



## Designer Config Panel Compatibility

Generate JSON that stays editable in the current BI Design property panel.

- Keep `option.xAxis` and `option.yAxis` as plain objects, not arrays.
- Do not generate dual-axis `yAxis: [...]` by default. The current `GlobalSetting` panel binds `optionData.yAxis` as one object, so an array makes only part of the axis behavior controllable.
- When users ask for two Y axes, prefer one controllable `yAxis` object and use series names, legend, labels, colors, tooltip text, and normalized data to express mixed units.
- Only emit `yAxis` arrays when the user explicitly accepts that axis settings must be edited through the raw JSON textarea instead of the normal property controls.
- Do not generate `title.subtext` by default; visible subtitles consume top layout space and can make the canvas UI look crowded.
- Prefer either no `option.title`, or a single-line title with `show`, `text`, `left`, `top`, `textStyle`, and an empty `subtextStyle` object for property-panel compatibility. Do not set a visible `subtext` unless explicitly requested.

## Component ID Rules

For every full component JSON, generate a new ID before returning the result.

- Use system style: `id_<obfuscated>`.
- Match this pattern: `^id_[0-9a-z]{14}$`.
- Do not use readable IDs such as `id_ai_chart_json`, chart names, dates, or business names.
- Do not reuse IDs from templates, examples, source JSON, or earlier answers unless the user explicitly asks to preserve the original component identity.
- Generate the obfuscated suffix from high-entropy randomness plus time, encoded as lowercase base36.
- Prefer running `node skills/ai-chart-json/scripts/generate-component-id.js` when editing files locally.
- If a script cannot be run, manually create a fresh 14-character lowercase base36 suffix that is not semantically meaningful.

Example valid IDs:

- `id_2kckd58c3aw0x`
- `id_8m4qz1rp9v0na0`
- `id_p7x3cn9tq6b2d0`

## Chart Selection Defaults

- Comparison by category: bar or horizontal bar.
- Trend over time: line or area line.
- Part-to-whole: pie, donut, or stacked bar.
- Ranking: horizontal bar sorted descending.
- Distribution: histogram-like bar or scatter.
- Relationship: scatter or bubble.
- KPI card is not handled by this chart skill unless the project has a compatible component JSON contract.

## ECharts Rules

- Use plain JSON values only.
- Do not emit JavaScript callbacks in `formatter`, `color`, or event fields.
- Keep `backgroundColor` transparent unless the user requests a background.
- Use readable default text color `#B9B8CE` and label color `#fff` for dark dashboards.
- For horizontal bars, use `xAxis.type = "value"` and `yAxis.type = "category"`.
- For vertical bars and lines, use `xAxis.type = "category"` and `yAxis.type = "value"`.
- Keep axis config panel compatibility: `xAxis` and `yAxis` should be objects unless raw-JSON-only editing is explicitly acceptable.

## Minimal Import JSON

Use `references/minimal-json-chart.json` as the minimal skeleton.

## Full Component JSON

Use `references/full-component-json-chart.json` when the user needs a complete design-canvas component object with position, style, request, and event fields.