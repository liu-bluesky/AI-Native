# /materials 路由降噪执行文档

## 1. 任务背景

- 目标入口：`/materials?project_id=proj-cc47efb1`
- 目标定位：把当前图片/视频生成相关能力放进一个新的“项目创作空间”，而不是塞进 `/ai/chat`
- 用户明确要求：
  - 不在 `ProjectChat` / `/ai/chat` 内集成“仿新境AI”工作流
  - `/materials` 需要套一层新的路由结构
  - 左侧菜单固定为：`素材库`、`短片制作`、`我的作品`
  - 页面风格必须遵守 [`ui-design.md`](/Users/liulantian/self/ai设计规范/rules/ui-design.md)

## 2. 当前路由结构

当前实现已经完成第一层路由拆分：

- 路由入口：[`router/index.js`](/Users/liulantian/self/ai设计规范/web-admin/frontend/src/router/index.js)
  - `/materials` -> [`ProjectCreationWorkspace.vue`](/Users/liulantian/self/ai设计规范/web-admin/frontend/src/views/projects/ProjectCreationWorkspace.vue)
  - `/materials` 默认子页 -> [`ProjectMaterialLibrary.vue`](/Users/liulantian/self/ai设计规范/web-admin/frontend/src/views/projects/ProjectMaterialLibrary.vue)
  - `/materials/studio` -> [`ProjectShortFilmStudio.vue`](/Users/liulantian/self/ai设计规范/web-admin/frontend/src/views/projects/ProjectShortFilmStudio.vue)
  - `/materials/works` -> [`ProjectWorksGallery.vue`](/Users/liulantian/self/ai设计规范/web-admin/frontend/src/views/projects/ProjectWorksGallery.vue)
- 主布局适配：[`Layout.vue`](/Users/liulantian/self/ai设计规范/web-admin/frontend/src/views/Layout.vue)
  - `route.path.startsWith("/materials")` 已按独立工作区布局处理

这说明“新页面入口不走 `/ai/chat`”的路由方向已经正确，当前问题主要在页面信息层级和视觉噪音。

## 3. 当前噪音来源

### 3.1 外层工作区噪音

[`ProjectCreationWorkspace.vue`](/Users/liulantian/self/ai设计规范/web-admin/frontend/src/views/projects/ProjectCreationWorkspace.vue) 当前仍包含：

- 品牌标题区
- 左侧导航
- 当前项目信息卡
- 底部动作按钮

问题：

- 外层侧边栏已经承担导航职责，却又额外承担品牌说明、项目信息、跳转入口，信息重复
- “当前项目”卡片属于额外容器层，容易形成 `导航壳 + 信息卡 + 内容卡` 的三层套壳
- `AI 对话` 按钮会把焦点从当前工作页拉回聊天，不符合“当前页承接创作流程”的目标

### 3.2 素材库页噪音

[`ProjectMaterialLibrary.vue`](/Users/liulantian/self/ai设计规范/web-admin/frontend/src/views/projects/ProjectMaterialLibrary.vue) 当前仍包含：

- 顶部上下文栏
- 页内第二层侧栏
- 搜索区
- 一级分组区
- 状态过滤区
- 来源过滤区
- 设计说明卡
- 主内容面板

问题：

- 外层已经有左侧菜单，页内再次放 `material-sidebar`，形成“双侧栏”
- 搜索、分类、状态、来源被拆成多个块，导致用户先读结构，再读内容
- “当前设计原则”说明卡属于帮助文案，不应占用主界面层级
- `material-shell > material-panel > material-panel--content` 仍是典型后台工作台套壳方式

## 4. 设计约束

依据 [`ui-design.md`](/Users/liulantian/self/ai设计规范/rules/ui-design.md)，本次执行必须满足：

- 保持 `/intro` 系的浅色渐变、空气感和轻玻璃感
- 产品工作页要强化任务路径，但不能退回老式后台系统风格
- 不再堆说明卡、入口卡、统计卡
- 一个屏幕只保留一个主焦点
- 卡片要轻，不能厚
- 主按钮只保留一个明确主操作

## 5. 目标结构

### 5.1 外层工作区

外层 [`ProjectCreationWorkspace.vue`](/Users/liulantian/self/ai设计规范/web-admin/frontend/src/views/projects/ProjectCreationWorkspace.vue) 只保留：

- 左侧轻导航
- 一行轻量项目信息
- 内容区域 `router-view`

外层删除或弱化：

- 品牌式标题块
- 独立项目卡
- 底部动作按钮堆叠

### 5.2 素材库页

素材库页改成三段结构：

1. 轻量上下文条
   - 页面标题
   - 当前项目简述
   - 一个主操作：`新增素材`
2. 行内筛选条
   - 搜索
   - 分类切换
   - 状态筛选
   - 来源筛选
   - 刷新 / 视图切换作为次操作
3. 单一内容区
   - 直接承载卡片流或表格
   - 不再额外包第二层侧栏

### 5.3 其他子页

- `短片制作` 和 `我的作品` 先保持占位，但样式要与新的外层壳一致
- 不新增英雄区，不做营销化主视觉

## 6. 不执行的内容

本轮不做：

- 不把仿新境原型直接整块搬进 `/ai/chat`
- 不重做素材卡片的数据结构和接口
- 不新增复杂工作流状态机
- 不改素材增删改接口
- 不新增第二套深色或重科技风视觉

## 7. 三次检查

### 第一次检查：结构去重

检查目标：

- 外层导航是否已经承担主要导航职责
- 素材页是否还存在第二层左侧导航
- 页面是否还存在重复的项目信息块

检查结论：

- 当前存在外层导航与内层 `material-sidebar` 重复
- 当前存在外层项目卡与页内上下文重复
- 需要把筛选能力收束到素材页顶部横向区域

状态：通过，允许进入第二次检查

### 第二次检查：视觉降噪

检查目标：

- 是否还存在厚卡片、重面板、说明卡、入口卡
- 主按钮是否控制为一个主焦点
- 文案是否足够短，不再像后台帮助说明

检查结论：

- 当前素材页的说明卡和双面板结构应删除
- 当前外层侧栏信息量偏多，应缩减为导航 + 轻项目信息
- `新增素材` 保留为主按钮，其余回退为次按钮或文本操作

状态：通过，允许进入第三次检查

### 第三次检查：执行边界

检查目标：

- 是否只改路由壳和页面结构，不动后端接口
- 是否仍保留 `project_id` 驱动的项目上下文
- 是否保证 `素材库 / 短片制作 / 我的作品` 三个入口不变

检查结论：

- 本轮仅调整前端路由承载和页面布局
- 保留现有数据获取、素材操作、来源跳转逻辑
- 执行重点锁定在 [`ProjectCreationWorkspace.vue`](/Users/liulantian/self/ai设计规范/web-admin/frontend/src/views/projects/ProjectCreationWorkspace.vue) 与 [`ProjectMaterialLibrary.vue`](/Users/liulantian/self/ai设计规范/web-admin/frontend/src/views/projects/ProjectMaterialLibrary.vue)

状态：通过，允许开始执行

## 8. 执行计划

1. 收缩外层 [`ProjectCreationWorkspace.vue`](/Users/liulantian/self/ai设计规范/web-admin/frontend/src/views/projects/ProjectCreationWorkspace.vue)
2. 拆掉 [`ProjectMaterialLibrary.vue`](/Users/liulantian/self/ai设计规范/web-admin/frontend/src/views/projects/ProjectMaterialLibrary.vue) 的内层侧栏和说明卡
3. 把搜索与筛选并入顶部横向工具条
4. 让内容区只保留一个主容器
5. 复查 [`ProjectShortFilmStudio.vue`](/Users/liulantian/self/ai设计规范/web-admin/frontend/src/views/projects/ProjectShortFilmStudio.vue) 与 [`ProjectWorksGallery.vue`](/Users/liulantian/self/ai设计规范/web-admin/frontend/src/views/projects/ProjectWorksGallery.vue) 的语气和层级是否一致
6. 运行前端构建验证
