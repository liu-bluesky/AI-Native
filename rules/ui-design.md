# UI 设计规范

> 基于 Ant Design Design Token 体系，适配 Element Plus 组件库。
> 本规范是 AI 智能体生成/修改任何 UI 代码时的强制参考。

## 设计原则

| 原则 | 说明 |
|------|------|
| 一致性 | 相同功能、相同外观。操作反馈、视觉层次全局统一 |
| 即时反馈 | 每个操作都有明确的状态变化反馈 |
| 效率优先 | 减少用户操作步骤，合理使用默认值 |
| 可控性 | 用户可预期操作结果，危险操作必须二次确认 |

---

## 1. 色彩系统

### 1.1 品牌色（Primary）

基于 Element Plus 默认主色，采用 Ant Design 的 10 级色板生成算法：

```
--color-primary-1:  #e6f4ff    ← 最浅，用于背景高亮
--color-primary-2:  #bae0ff
--color-primary-3:  #91caff
--color-primary-4:  #69b1ff
--color-primary-5:  #4096ff
--color-primary-6:  #1677ff    ← 主色（对应 Element Plus --el-color-primary）
--color-primary-7:  #0958d9
--color-primary-8:  #003eb3
--color-primary-9:  #002c8c
--color-primary-10: #001d66    ← 最深
```

使用规则：
- 主操作按钮、链接、选中态：`primary-6`
- 悬停态：`primary-5`
- 点击态：`primary-7`
- 浅色背景（选中行、提示区）：`primary-1`

### 1.2 功能色（Functional）

| 语义 | 色值 | Element Plus 变量 | 用途 |
|------|------|------------------|------|
| 成功 | `#52c41a` | `--el-color-success` | 操作成功、低风险、已启用 |
| 警告 | `#faad14` | `--el-color-warning` | 注意、中风险、recommended 级别 |
| 危险 | `#ff4d4f` | `--el-color-danger` | 错误、高风险、required 级别、删除 |
| 信息 | `#1677ff` | `--el-color-info` | 提示、optional 级别、默认标签 |

使用规则：
- 功能色仅用于传达状态语义，禁止用作装饰
- 每种功能色同样有 light/dark 变体，用于背景和边框

### 1.3 中性色（Neutral）

```
--color-text-primary:     rgba(0, 0, 0, 0.88)    ← 标题、正文
--color-text-secondary:   rgba(0, 0, 0, 0.65)    ← 次要文字
--color-text-tertiary:    rgba(0, 0, 0, 0.45)    ← 占位符、禁用文字
--color-text-quaternary:  rgba(0, 0, 0, 0.25)    ← 禁用图标

--color-border:           #d9d9d9                 ← 默认边框
--color-border-secondary: #f0f0f0                 ← 分割线

--color-bg-container:     #ffffff                 ← 容器背景
--color-bg-layout:        #f5f5f5                 ← 页面背景（对应 #f0f2f5）
--color-bg-elevated:      #ffffff                 ← 弹出层背景
```

使用规则：
- 文字层级严格按 4 级透明度区分，禁止自定义灰度值
- 背景色仅使用上述 3 级，禁止使用其他灰色背景

---

## 2. 字体排版

### 2.1 字体族

```css
font-family:
  -apple-system, BlinkMacSystemFont,
  'Segoe UI', Roboto,
  'Helvetica Neue', Arial,
  'Noto Sans', 'PingFang SC', 'Microsoft YaHei',
  sans-serif,
  'Apple Color Emoji', 'Segoe UI Emoji';
```

中文优先 PingFang SC（macOS）和 Microsoft YaHei（Windows）。

### 2.2 字号与行高

| Token | 字号 | 行高 | 用途 |
|-------|------|------|------|
| `font-size-sm` | 12px | 20px | 辅助文字、标签、表格紧凑模式 |
| `font-size-base` | 14px | 22px | 正文、表格、表单（Element Plus 默认） |
| `font-size-lg` | 16px | 24px | 小标题、侧边栏 logo |
| `font-size-xl` | 20px | 28px | 页面标题（h3） |
| `font-size-2xl` | 24px | 32px | 一级标题（h2） |
| `font-size-3xl` | 30px | 38px | 大标题（h1，少用） |

行高公式：`line-height = font-size + 8px`（Ant Design 规范）。

### 2.3 字重

| Token | 值 | 用途 |
|-------|-----|------|
| `font-weight-normal` | 400 | 正文、描述 |
| `font-weight-medium` | 500 | 表头、标签、强调 |
| `font-weight-semibold` | 600 | 标题、按钮 |
| `font-weight-bold` | 700 | 大标题（少用） |

---

## 3. 间距系统

采用 4px 基准网格，8px 为主节奏：

| Token | 值 | 用途 |
|-------|-----|------|
| `spacing-xxs` | 4px | 图标与文字间距、紧凑元素内边距 |
| `spacing-xs` | 8px | 相关元素间距（标签组、按钮组） |
| `spacing-sm` | 12px | 表单项内间距、卡片内边距 |
| `spacing-md` | 16px | 区块间距、工具栏 margin-bottom |
| `spacing-lg` | 24px | 卡片间距、区域分隔 |
| `spacing-xl` | 32px | 页面级区块间距 |
| `spacing-xxl` | 48px | 大区域分隔（少用） |

使用规则：
- 所有间距必须是 4px 的整数倍，禁止出现 5px、7px、15px 等非对齐值
- 同级元素间距一致，父子元素间距递减
- 工具栏统一 `margin-bottom: 16px`
- 标签/按钮组内间距统一 `6px ~ 8px`

---

## 4. 圆角与阴影

### 4.1 圆角

| Token | 值 | 用途 |
|-------|-----|------|
| `border-radius-sm` | 2px | 小型元素（标签、徽标） |
| `border-radius-base` | 4px | 按钮、输入框、卡片（Element Plus 默认） |
| `border-radius-lg` | 8px | 弹窗、抽屉、大卡片 |
| `border-radius-xl` | 12px | 特殊容器（少用） |

### 4.2 阴影

| Token | 值 | 用途 |
|-------|-----|------|
| `shadow-sm` | `0 1px 2px rgba(0,0,0,0.03)` | 卡片静态 |
| `shadow-base` | `0 2px 8px rgba(0,0,0,0.08)` | 卡片悬停、下拉菜单 |
| `shadow-lg` | `0 6px 16px rgba(0,0,0,0.12)` | 弹窗、抽屉 |

---

## 5. 布局系统

### 5.1 页面骨架

```
┌─────────────────────────────────────────┐
│  el-aside (200px)  │  el-header (60px)  │
│                    ├────────────────────│
│  侧边导航          │  el-main           │
│                    │  padding: 20px     │
│                    │                    │
└─────────────────────────────────────────┘
```

- 侧边栏固定 200px，不可折叠（当前阶段）
- 头部高度 60px，含用户名 + 退出按钮
- 主内容区 `el-main` 默认 padding 20px

### 5.2 工具栏模式

页面顶部统一工具栏：

```css
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.toolbar h3 { margin: 0; }
```

左侧放标题，右侧放操作按钮。

### 5.3 表格列宽参考

| 内容类型 | 建议宽度 |
|---------|---------|
| ID | 140px |
| 名称 | 140~160px |
| 短文本（语调/风格） | 80~100px |
| 数字（计数/分数） | 80~90px |
| 操作列 | 按按钮数量，每个约 60px |
| 描述/长文本 | 不设宽度，自动填充 |

操作列始终 `fixed="right"`。

---

## 6. 组件设计规范

### 6.1 按钮

| 类型 | 用途 | Element Plus 属性 |
|------|------|------------------|
| 主按钮 | 页面主操作（创建、提交） | `type="primary"` |
| 文字按钮 | 表格行内操作 | `text type="primary"` |
| 危险按钮 | 删除、不可逆操作 | `text type="danger"` |
| 默认按钮 | 次要操作（返回、取消） | 无 type |

规则：
- 同一区域最多 1 个主按钮
- 表格行内操作一律用 `text` 按钮
- 危险操作必须配合 `ElMessageBox.confirm()`

### 6.2 表单

- 标签位置：顶部对齐（`label-position="top"`）或右对齐
- 必填项标记红色星号（Element Plus 自动处理）
- 输入框宽度：短文本 200px，中文本 320px，长文本 100%
- 选择器/开关/滑块保持与输入框同行高度对齐

### 6.3 标签（Tag）

语义色映射（项目统一约定）：

```
success  → 低风险、已启用、已通过
warning  → 中风险、recommended、待审核
danger   → 高风险、required、已拒绝
info     → 默认、optional、普通标签
```

标签间距统一 `margin-right: 6px`。

### 6.4 空状态

无数据时统一使用 `el-empty`：

```vue
<el-empty v-if="!list.length" description="暂无数据" :image-size="60" />
```

### 6.5 详情展示

使用 `el-descriptions` 组件，双列布局：

```vue
<el-descriptions :column="2" border>
  <el-descriptions-item label="名称">{{ item.name }}</el-descriptions-item>
  <el-descriptions-item label="描述" :span="2">{{ item.description || '-' }}</el-descriptions-item>
</el-descriptions>
```

- 长文本字段用 `:span="2"` 占满整行
- 空值显示 `-`，不留空白

---

## 7. 交互规范

### 7.1 加载状态

- 数据请求期间必须显示加载指示器
- 表格/容器用 `v-loading="loading"` 指令
- 按钮用 `:loading="loading"` 属性

### 7.2 操作反馈

| 场景 | 方式 |
|------|------|
| 创建/更新成功 | `ElMessage.success('操作成功')` |
| 请求失败 | `ElMessage.error('加载失败')` |
| 删除确认 | `ElMessageBox.confirm('确定删除？', '确认')` |

### 7.3 导航反馈

- 创建成功后跳转列表页：`router.push('/xxx')`
- 返回按钮用 `router.back()`
- 登录成功后 `router.replace('/')`

---

## 8. 禁止事项

- 禁止使用行内样式（`style=""`）设置颜色/字号，必须使用 Token 变量或 Element Plus 类名
- 禁止自定义灰度值，所有中性色从 3.3 节取值
- 禁止间距出现非 4px 倍数的值
- 禁止在非语义场景使用功能色（如用红色做装饰）
- 禁止省略加载状态和空状态处理
- 禁止跳过危险操作的二次确认
