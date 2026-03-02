# AI 员工工厂设计规范

> 核心理念：用户可自定义组合 MCP + 规则 + 记忆 + Skills，创建多个 AI 员工，通过进化引擎实现"越用越聪明"。

---

## 目录

1. [核心概念](#1-核心概念)
2. [架构设计](#2-架构设计)
3. [数据模型](#3-数据模型)
4. [进化引擎](#4-进化引擎)
5. [MCP 服务设计](#5-mcp-服务设计)
6. [用户交互流程](#6-用户交互流程)
7. [实现路线图](#7-实现路线图)
8. [与传统方案对比](#8-与传统方案对比)
9. [安全设计（应用层）](#9-安全设计应用层)

---

## 1. 核心概念

### 1.1 AI 员工定义

AI 员工是一个可组合的智能体，由以下四个核心要素构成：

| 要素 | 说明 | MCP 服务 |
|------|------|----------|
| **Skills (技能)** | 领域能力，如 React 开发、API 设计 | Skills MCP |
| **Rules (规则)** | 团队规范、最佳实践、踩坑经验 | Rules MCP |
| **Memory (记忆)** | 项目上下文、用户偏好、历史知识 | Memory MCP |
| **Persona (人设)** | 沟通风格、行为模式、专业定位 | Persona MCP |

### 1.2 核心能力

- **可组合**：用户自由选择技能、规则、记忆组合，创建专属 AI 员工
- **可进化**：通过使用反馈自动学习新规则，推送更新到员工
- **可管理**：创建、编辑、删除、复制多个 AI 员工
- **可共享**：规则和技能可在员工间共享，形成团队知识库

---

## 2. 架构设计

### 2.1 平台全景

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            用户界面层 (User Interface)                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │
│  │   AI 员工管理    │  │   技能市场       │  │   规则工作台     │            │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘            │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AI 员工编排层 (Orchestrator)                          │
│                                                                              │
│   用户创建 AI 员工：选择 Skills + 规则集 + 记忆库 + 人设                      │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  AI 员工实例                                                          │   │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐           │   │
│  │  │ 前端专家   │ │ 后端专家   │ │ 测试工程师 │ │ 运维专家   │  ...      │   │
│  │  │           │ │           │ │           │ │           │           │   │
│  │  │ Skills:   │ │ Skills:   │ │ Skills:   │ │ Skills:   │           │   │
│  │  │ • React   │ │ • Python  │ │ • Jest    │ │ • K8s     │           │   │
│  │  │ • CSS     │ │ • Django  │ │ • Cypress │ │ • Docker  │           │   │
│  │  │           │ │           │ │           │ │           │           │   │
│  │  │ 规则:     │ │ 规则:     │ │ 规则:     │ │ 规则:     │           │   │
│  │  │ 团队前端规│ │ 后端规范  │ │ 测试策略  │ │ 部署规范  │           │   │
│  │  │           │ │           │ │           │ │           │           │   │
│  │  │ 记忆:     │ │ 记忆:     │ │ 记忆:     │ │ 记忆:     │           │   │
│  │  │ 项目上下文│ │ 业务领域  │ │ 缺陷历史  │ │ 环境配置  │           │   │
│  │  └───────────┘ └───────────┘ └───────────┘ └───────────┘           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        MCP 服务层 (Capability Pool)                          │
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │
│  │  Skills MCP     │  │  Rules MCP      │  │  Memory MCP     │            │
│  │  ───────────    │  │  ───────────    │  │  ───────────    │            │
│  │  tools:         │  │  tools:         │  │  tools:         │            │
│  │  • get_skill    │  │  • query_rule   │  │  • save_memory  │            │
│  │  • list_skills  │  │  • submit_rule  │  │  • recall       │            │
│  │                 │  │  • evolve_rule  │  │  • forget       │            │
│  │  resources:     │  │                 │  │                 │            │
│  │  • skill-catalog│  │  resources:     │  │  resources:     │            │
│  │                 │  │  • rule-set/*   │  │  • memories/*   │            │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘            │
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │
│  │  Evolution MCP  │  │  Persona MCP    │  │  Sync MCP       │            │
│  │  ───────────    │  │  ───────────    │  │  ───────────    │            │
│  │  tools:         │  │  tools:         │  │  tools:         │            │
│  │  • analyze_use  │  │  • get_persona  │  │  • push_update  │            │
│  │  • propose_rule │  │  • set_tone     │  │  • sync_state   │            │
│  │  • auto_refine  │  │  • set_style    │  │  • notify_agent │            │
│  │                 │  │                 │  │                 │            │
│  │  自动进化引擎    │  │  人设/风格设定  │  │  增量同步推送    │            │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘            │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     进化引擎 (Evolution Engine)                               │
│                                                                              │
│   ┌───────────────────────────────────────────────────────────────────┐    │
│   │                      进化闭环 (Evolution Loop)                      │    │
│   │                                                                    │    │
│   │   使用 ──→ 采集 ──→ 分析 ──→ 提炼 ──→ 验证 ──→ 推送 ──→ 生效        │    │
│   │    │                    │                              │          │    │
│   │    │    ┌───────────────┴───────────────┐              │          │    │
│   │    │    ▼                               ▼              │          │    │
│   │    │  规则进化 (Rule Evolution)      记忆进化 (Memory)   │          │    │
│   │    │  • 新规则生成                    • 上下文压缩      │          │    │
│   │    │  • 规则修正                      • 关键事件记录    │          │    │
│   │    │  • 规则合并/废弃                 • 偏好学习        │          │    │
│   │    │                                  • 项目知识沉淀    │          │    │
│   │    │                                                       │    │
│   │    └─────────────────────────────────────────────────────┘    │
│   └───────────────────────────────────────────────────────────────┘    │
│                                                                              │
│   ┌───────────────────────────────────────────────────────────────────┐    │
│   │                   实时推送系统 (Real-time Sync)                     │    │
│   │                                                                    │    │
│   │   进化完成 ──→ 版本快照 ──→ 增量推送 ──→ AI员工热更新              │    │
│   │                              │                                    │    │
│   │                              ▼                                    │    │
│   │                    ┌─────────────────┐                           │    │
│   │                    │ WebSocket / SSE │ ← 实时通知                 │    │
│   │                    │ MCP Resource    │ ← 资源变更通知             │    │
│   │                    │ CLI Hook        │ ← 命令行推送               │    │
│   │                    └─────────────────┘                           │    │
│   └───────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        数据存储层 (Data Layer)                               │
│                                                                              │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐             │
│  │ 规则库      │ │ 记忆库      │ │ 使用日志    │ │ 向量索引    │             │
│  │ (YAML/JSON)│ │ (SQLite)   │ │ (时序DB)   │ │ (pgvector) │             │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 分层职责

| 层级 | 职责 | 关键能力 |
|------|------|----------|
| 用户界面层 | 用户与平台的交互入口 | 员工管理、技能市场、规则编辑、进化面板 |
| AI 员工编排层 | 员工创建、配置、路由 | 组合配置、运行时管理、负载均衡 |
| MCP 服务层 | 领域能力的标准化封装 | Skills/Rules/Memory/Persona/Evolution/Sync |
| 进化引擎层 | 知识的自动学习与推送 | 使用分析、规则生成、增量同步、热更新 |
| 数据存储层 | 持久化存储与检索 | 多模态存储、向量检索、版本管理 |

---

## 3. 数据模型

### 3.1 AI 员工定义

```yaml
# AI 员工配置
ai_employee:
  id: "emp-frontend-001"
  name: "前端专家小王"
  description: "专注于 React 生态的前端开发专家"
  
  # 1. 技能组合
  skills:
    - skill_id: "react-development"
      version: "1.2.0"
      enabled_tools: ["component_gen", "hook_suggest", "perf_optimize"]
    - skill_id: "css-styling"
      version: "2.0.0"
      enabled_tools: ["style_gen", "responsive_check"]
    - skill_id: "typescript"
      version: "1.0.0"
      
  # 2. 规则绑定
  rules:
    rule_set: "team-frontend-rules"
    domains: ["error-handling", "component-design", "performance"]
    custom_rules: ["rule-custom-001", "rule-custom-002"]  # 用户自定义规则
    
  # 3. 记忆配置
  memory:
    scope: "project-level"  # global / project / session
    retention: "90d"
    max_entries: 1000
    auto_compress: true
    compress_threshold: 100  # 超过 100 条自动压缩
    
  # 4. 人设设定
  persona:
    persona_id: "persona-frontend-expert"  # 关联 Persona 定义
    tone: "professional"      # professional / friendly / strict
    verbosity: "concise"      # verbose / concise / minimal
    language: "zh-CN"
    style_hints:
      - "优先使用函数式组件"
      - "代码注释使用中文"
      - "优先考虑性能优化"
    decision_policy:
      priority_order: ["correctness", "security", "maintainability", "speed"]
      risk_preference: "balanced"           # conservative / balanced / aggressive
      uncertain_action: "ask_for_confirmation"
    delegation_scope:
      auto_approve: ["code_style_suggestion", "test_case_generation"]
      require_confirmation: ["merge_request_approval", "architecture_decision"]
      forbidden: ["production_deployment", "access_permission_change"]
      principle: "delegation_cannot_escalate"
    drift_control:
      enabled: true
      window_days: 30
      max_drift_score: 0.25

  # 5. 进化配置
  evolution:
    auto_learn: true          # 自动学习新规则
    feedback_weight: 0.7      # 反馈权重
    review_threshold: 0.8     # 自动入库阈值（代码中对应 auto_threshold 参数）
    domains_to_watch: ["error-handling", "component-design"]
    threshold_by_risk:
      low: 0.85
      medium: 0.9
      high: "manual_only"
    max_per_day: 5
    kill_switch:
      enabled: true
    
  # 6. 元数据
  metadata:
    created_at: "2025-02-27T10:00:00Z"
    updated_at: "2025-02-27T15:30:00Z"
    created_by: "user-001"
    usage_count: 156
```

### 3.2 技能定义 (Skill)

技能是一个可导入的代码包，包含脚本、配置和资源文件。

#### 3.2.1 技能创建方式

**方式一：导入本地目录**

```bash
# 导入技能目录
skill import ./skill-react-development/

# 或使用 CLI
mcp-skill import --path ./skill-react-development --name "React 开发"
```

**方式二：上传 ZIP 包**

```bash
# 打包并上传
skill pack ./skill-react-development/ -o react-dev.zip
skill upload react-dev.zip
```

**方式三：从 Git 仓库导入**

```bash
skill clone https://github.com/team/skill-react-dev.git
```

**导入流程：**

```
用户选择目录/文件
         │
         ▼
┌─────────────────────────────────┐
│ 1. 扫描目录结构                  │
│    • 检测 manifest.yaml          │
│    • 扫描 tools/*.py, *.js       │
│    • 收集资源文件                │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│ 2. 安全扫描                      │
│    • 敏感代码检测                │
│    • 危险函数检查                │
│    • 依赖安全审计                │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│ 3. 解析 manifest.yaml            │
│    • 验证必要字段                │
│    • 解析工具定义                │
│    • 检查依赖完整性              │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│ 4. 安装依赖                      │
│    • pip install requirements.txt│
│    • npm install package.json    │
│    （在隔离环境中）              │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│ 5. 测试执行                      │
│    • 沙箱环境执行                │
│    • 验证工具输出                │
│    • 检查超时和内存              │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│ 6. 存储到技能库                  │
│    • 复制到 skills/ 目录         │
│    • 更新技能注册表              │
│    • 生成技能 ID                 │
└─────────────────────────────────┘
```

#### 3.2.2 技能包结构

```
skill-react-development/
├── manifest.yaml           # 技能元数据
├── tools/                  # 工具脚本
│   ├── component_gen.py    # Python 工具
│   ├── hook_suggest.js     # Node.js 工具
│   └── perf_optimize.py
├── resources/              # 资源文件
│   ├── patterns.json       # 组件模式库
│   └── hooks/              # 自定义 Hooks
├── prompts/                # 提示词模板
│   └── code_review.md
├── requirements.txt        # Python 依赖
├── package.json            # Node.js 依赖（可选）
└── README.md               # 技能文档
```

#### 3.2.2 技能配置 (manifest.yaml)

```yaml
# 技能配置
id: "react-development"
version: "1.2.0"
name: "React 开发"
description: "React 组件开发、状态管理、性能优化"
author: "team-frontend"
license: "MIT"

# 运行时配置
runtime:
  python: "3.11"            # Python 版本
  node: "18"                # Node.js 版本（可选）
  sandbox: true             # 沙箱执行
  
# 工具定义
tools:
  - name: "component_gen"
    script: "tools/component_gen.py"    # 脚本路径
    runtime: "python"
    description: "生成 React 组件代码"
    parameters:
      component_name:
        type: string
        required: true
      props:
        type: object
        default: {}
      style_approach:
        type: string
        enum: ["css-modules", "styled-components", "tailwind"]
        default: "css-modules"
    timeout: 30s
    cache_result: true
        
  - name: "hook_suggest"
    script: "tools/hook_suggest.js"      # Node.js 脚本
    runtime: "node"
    description: "推荐合适的 React Hooks"
    parameters:
      context:
        type: string
        required: true
    timeout: 15s
        
  - name: "perf_optimize"
    script: "tools/perf_optimize.py"
    runtime: "python"
    description: "性能优化建议"
    parameters:
      code_snippet:
        type: string
        required: true
    timeout: 30s

# 资源定义
resources:
  - name: "component-patterns"
    path: "resources/patterns.json"
    description: "常用组件模式库"
    cache_ttl: 3600
        
  - name: "hook-library"
    path: "resources/hooks/"
    description: "自定义 Hooks 库"

# 提示词模板
prompts:
  - name: "code_review"
    path: "prompts/code_review.md"

# 依赖
dependencies:
  - skill_id: "typescript"
    version: ">=1.0.0"
    required: false
  # Python 包依赖
  packages:
    python:
      - "react-parser>=1.0.0"
      - "ast-analyzer>=2.0.0"
    node:
      - "@babel/parser"
      - "prettier"

# 标签
tags: ["frontend", "react", "component", "hooks"]

# 权限
permissions:
  network: false            # 不允许网络访问
  filesystem: "readonly"    # 只读文件系统
  env_vars: []              # 允许的环境变量
```

#### 3.2.3 工具脚本示例

**Python 工具示例 (tools/component_gen.py):**

```python
#!/usr/bin/env python3
"""生成 React 组件代码"""

import sys
import json
from pathlib import Path

def generate_component(component_name: str, props: dict, style_approach: str) -> dict:
    """生成 React 组件"""
    
    # 生成组件代码
    code = f'''import React from 'react';
import styles from './{component_name}.module.css';

interface {component_name}Props {{
  {format_props(props)}
}}

export const {component_name}: React.FC<{component_name}Props> = ({format_prop_names(props)}) => {{
  return (
    <div className={{styles.container}}>
      {/* TODO: 组件内容 */}
    </div>
  );
}};
'''
    
    return {
        "success": True,
        "code": code,
        "filename": f"{component_name}.tsx",
        "style_file": f"{component_name}.module.css" if style_approach == "css-modules" else None
    }

def format_props(props: dict) -> str:
    """格式化 Props 定义"""
    if not props:
        return "// 暂无 props"
    return "\n  ".join([f'{k}: {v};' for k, v in props.items()])

def format_prop_names(props: dict) -> str:
    """格式化 props 参数名"""
    if not props:
        return ""
    return ", ".join(props.keys())

if __name__ == "__main__":
    # 从 stdin 读取参数
    params = json.load(sys.stdin)
    result = generate_component(**params)
    print(json.dumps(result))
```

**Node.js 工具示例 (tools/hook_suggest.js):**

```javascript
#!/usr/bin/env node
/** 推荐合适的 React Hooks */

const readline = require('readline');

async function suggestHooks(context) {
  const suggestions = [];
  
  // 基于上下文分析推荐 Hooks
  if (context.includes('state') || context.includes('count')) {
    suggestions.push({
      hook: 'useState',
      reason: '适合管理本地状态',
      example: 'const [count, setCount] = useState(0);'
    });
  }
  
  if (context.includes('fetch') || context.includes('api')) {
    suggestions.push({
      hook: 'useEffect',
      reason: '适合处理副作用和数据获取',
      example: 'useEffect(() => { fetchData(); }, []);'
    });
  }
  
  if (context.includes('context') || context.includes('theme')) {
    suggestions.push({
      hook: 'useContext',
      reason: '适合访问全局上下文',
      example: 'const theme = useContext(ThemeContext);'
    });
  }
  
  return {
    success: true,
    suggestions,
    confidence: calculateConfidence(context, suggestions)
  };
}

function calculateConfidence(context, suggestions) {
  // 基于匹配程度计算置信度
  return Math.min(suggestions.length * 0.3 + 0.4, 1.0);
}

// 从 stdin 读取参数
const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout
});

let input = '';
rl.on('line', (line) => {
  input += line;
});

rl.on('close', async () => {
  const params = JSON.parse(input);
  const result = await suggestHooks(params.context);
  console.log(JSON.stringify(result));
});
```

#### 3.2.4 技能上传流程

```
用户上传技能包 (.zip)
    │
    ▼
┌─────────────────────────────────┐
│ 1. 安全扫描                      │
│    • 病毒扫描                    │
│    • 敏感代码检测                │
│    • 依赖安全检查                │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│ 2. 结构验证                      │
│    • manifest.yaml 必须存在      │
│    • 脚本文件权限检查            │
│    • 依赖完整性检查              │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│ 3. 沙箱测试                      │
│    • 在隔离环境执行              │
│    • 检查执行超时                │
│    • 验证输出格式                │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│ 4. 发布到技能市场                │
│    • 生成版本号                  │
│    • 存储技能包                  │
│    • 更新技能目录                │
└─────────────────────────────────┘
```

#### 3.2.5 技能存储结构

```
skills/
├── registry.json                    # 技能注册表
├── react-development/
│   ├── versions/
│   │   ├── 1.0.0/
│   │   │   ├── manifest.yaml
│   │   │   ├── tools/
│   │   │   └── resources/
│   │   ├── 1.1.0/
│   │   └── 1.2.0/    # 当前版本
│   └── latest -> versions/1.2.0/
├── python-testing/
├── node-api/
└── ...

### 3.3 规则定义 (Rule)

```yaml
# 规则定义 (支持自动进化)
rule:
  id: "rule-fe-001"
  version: "1.3.0"            # 自动版本管理
  
  # 基础信息
  domain: "error-handling"
  risk_domain: "low"              # low / medium / high（进化安全分级）
  title: "API 错误必须包含 error_code"
  context: "编写 REST API 错误处理时"
  rule: "所有 4xx/5xx 响应必须包含 error_code 字段，用于客户端精确匹配错误类型"
  severity: "required"        # required / recommended / optional
  examples:
    - good: '{"error_code": "AUTH_EXPIRED", "message": "Token has expired"}'
      bad: '{"message": "Something went wrong"}'
      
  # 进化元数据
  evolution:
    created_from: "incident-review-2024-q3"
    confidence: 0.92          # 动态置信度 (0.0 - 1.0)
    adoption_rate: 0.87       # 采纳率
    usage_count: 45           # 使用次数
    last_used: "2025-02-27T14:30:00Z"
    
    # 进化历史
    changelog:
      - version: "1.3.0"
        date: "2025-02-20"
        change: "扩展支持 GraphQL 错误响应"
        auto_evolved: true    # 自动进化生成
        trigger: "高频修正模式检测"
        confidence_delta: +0.05
        
      - version: "1.2.0"
        date: "2025-01-15"
        change: "增加 bad example"
        auto_evolved: false
        author: "user-002"
        
      - version: "1.0.0"
        date: "2024-10-01"
        change: "初始创建"
        auto_evolved: false
        author: "user-001"
        
  # 关联员工
  bound_employees: ["emp-frontend-001", "emp-backend-001"]
  
  # 来源信息
  source:
    type: "incident-review"   # incident-review / code-review / user-submit / auto-evolved
    reference: "INC-2024-089"
    author: "user-001"
    trigger: null              # 自动进化触发类型（auto-evolved 时填写）
    pattern_id: null           # 关联的模式 ID
    actor: "user-001"          # 操作发起人
```

### 3.4 候选规则 (Candidate)

```yaml
# 候选规则（进化引擎生成，待审核或自动入库）
candidate:
  id: "cand-001"
  employee_id: "emp-frontend-001"
  pattern_id: "pattern-file-upload-validation"

  # 规则内容（与 Rule 结构一致）
  title: "文件上传必须校验类型"
  domain: "file-handling"
  risk_domain: "low"
  context: "处理文件上传时"
  rule: "上传文件必须校验 MIME 类型，仅允许白名单内的文件类型"
  severity: "recommended"
  confidence: 0.72

  # 审核状态
  status: "pending"             # pending / approved / rejected
  block_reasons: []             # 阻塞原因列表
  bound_employees: ["emp-frontend-001"]

  # 元数据
  created_at: "2025-02-25T10:00:00Z"
  trigger_type: "repeated_correction"
```

### 3.5 记忆条目 (Memory)

```yaml
# 记忆条目
memory:
  id: "mem-001"
  employee_id: "emp-frontend-001"
  
  # 记忆类型
  type: "project-context"     # project-context / user-preference / key-event / learned-pattern / long-term-goal / taboo / stable-preference / decision-pattern

  # 隔离与访问控制
  isolation:
    scope: "employee-private"   # employee-private / team-shared / global-verified
    allowed_readers: ["employee:emp-frontend-001", "owner:user-001"]
    classification: "internal"  # public / internal / confidential / restricted
  
  # 内容
  content: "项目使用 antd 组件库，版本 5.x，主题色 #1890ff"
  
  # 元数据
  importance: 0.8             # 重要性评分
  access_count: 23            # 访问次数
  last_accessed: "2025-02-27T14:00:00Z"
  created_at: "2025-02-20T10:00:00Z"
  
  # 过期策略
  ttl: "90d"
  expires_at: "2025-05-20T10:00:00Z"
  
  # 关联
  related_rules: ["rule-fe-012"]
  related_memories: ["mem-002", "mem-003"]
```

### 3.6 人设定义 (Persona)

```yaml
# 人设定义
persona:
  id: "persona-frontend-expert"
  name: "前端专家"
  
  # 基础属性
  tone: "professional"        # professional / friendly / strict / mentor
  verbosity: "concise"        # verbose / concise / minimal
  language: "zh-CN"
  
  # 行为偏好
  behaviors:
    - "代码审查时先关注性能问题"
    - "推荐方案时给出多个选择"
    - "错误处理优先考虑用户体验"
    
  # 沟通风格
  style_hints:
    - "优先使用函数式组件"
    - "代码注释使用中文"
    - "推荐使用 TypeScript"
    - "样式优先使用 CSS Modules"

  # 决策策略（数字分身核心）
  decision_policy:
    priority_order: ["correctness", "security", "maintainability", "speed"]
    risk_preference: "balanced"
    uncertain_action: "ask_for_confirmation"
    forbidden_goals:
      - "绕过安全校验"
      - "越权访问他人数据"

  # 代理授权边界
  delegation_scope:
    auto_approve: ["code_style_suggestion", "test_case_generation"]
    require_confirmation: ["merge_request_approval", "architecture_decision"]
    forbidden: ["production_deployment", "access_permission_change"]
    principle: "delegation_cannot_escalate"

  # 身份连续性
  drift_control:
    enabled: true
    window_days: 30
    max_drift_score: 0.25
    alert_on_drift: true

  # 对齐评测
  alignment_evaluation:
    benchmark_id: "owner-profile-v1"
    min_score: 0.85
    evaluate_every: "7d"

  # 训练与报告（与基础设施层加密策略对齐）
  training_corpus_refs: []           # 授权语料引用列表
  drift_report: null                 # 最近一次漂移报告快照

  # 专业定位
  expertise:
    primary: ["React", "TypeScript", "CSS"]
    secondary: ["Node.js", "GraphQL", "Testing"]
```

---

## 4. 进化引擎

### 4.1 进化闭环流程

```
┌─────────────────────────────────────────────────────────────────┐
│                      用户与 AI 员工交互                           │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 1: 隐式采集 (Implicit Collection)                          │
│  ─────────────────────────────────────                          │
│  • AI 调用了哪些规则/技能 → 自动记录                               │
│  • 用户采纳/拒绝/修改 → Diff 分析                                  │
│  • 相似场景重复出现 → 模式聚合                                     │
│  • 错误修正模式 → 潜在规则候选                                     │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 2: 智能分析 (Pattern Analysis)                             │
│  ─────────────────────────────────────                          │
│  • 用户修正模式 → "可能需要新规则"                                  │
│  • 规则命中率低 → "规则可能过时或无效"                              │
│  • 跨员工相似问题 → "可提炼为通用规则"                               │
│  • 领域知识积累 → "可沉淀为记忆"                                    │
│  • 用户偏好重复 → "可学习为行为模式"                                │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 3: 自动提炼 (Auto-Refine)                                   │
│  ─────────────────────────────────────                          │
│                                                                  │
│  输入: 用户修正记录 + 原始规则 + 上下文                             │
│                     │                                            │
│                     ▼                                            │
│  ┌─────────────────────────────────────────────┐                │
│  │           AI 辅助规则生成                     │                │
│  │                                              │                │
│  │  发现模式: 用户在处理文件上传时，              │                │
│  │  总是添加文件大小校验逻辑                     │                │
│  │                                              │                │
│  │  生成候选规则:                                │                │
│  │  domain: file-handling                       │                │
│  │  title: "文件上传必须校验大小"                │                │
│  │  rule: "上传文件大小限制 10MB"               │                │
│  │  confidence: 0.6 (待验证)                    │                │
│  └─────────────────────────────────────────────┘                │
│                                                                  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 4: 验证 & 决策 (Validation & Decision)                     │
│  ─────────────────────────────────────                          │
│                                                                  │
│  confidence >= review_threshold ?                                │
│       │                                                          │
│       ├── Yes → 自动入库 → 推送到所有绑定员工                      │
│       │         通知用户: "已自动学习 1 条新规则"                  │
│       │                                                          │
│       └── No  → 进入候选队列 → 等待用户审核                        │
│                 通知用户: "发现 1 条候选规则，请审核"               │
│                                                                  │
│  决策因子:                                                        │
│  • 修正重复次数 (>= 3 次触发)                                     │
│  • 跨用户验证 (多人修正相同问题)                                   │
│  • 来源权威度 (事故复盘 > Code Review > 个人经验)                  │
│                                                                  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 5: 实时推送 (Real-time Push)                               │
│  ─────────────────────────────────────                          │
│                                                                  │
│  规则更新 ──→ Evolution MCP 生成事件                               │
│                    │                                             │
│                    ▼                                             │
│            ┌──────────────┐                                      │
│            │ 事件总线      │                                      │
│            └──────┬───────┘                                      │
│                   │                                              │
│        ┌──────────┼──────────┐                                   │
│        ▼          ▼          ▼                                   │
│   WebSocket    MCP SSE    CLI Hook                               │
│   (IDE 推送)   (资源变更)  (命令通知)                              │
│        │          │          │                                   │
│        └──────────┴──────────┘                                   │
│                   │                                              │
│                   ▼                                              │
│          AI 员工即时热更新                                        │
│          "已为你学习 1 条新规则，立即生效"                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 置信度模型

每条规则的置信度由多因子动态计算：

```python
# 置信度计算公式
confidence = (
    0.35 * adoption_rate      # 采纳率：被采纳次数 / 被推荐次数
  + 0.25 * cross_user_score   # 跨用户验证：多少不同用户采纳过
  + 0.20 * recency_score      # 时效性：近期使用频率
  + 0.20 * source_authority   # 来源权威度
)

# 来源权威度权重
SOURCE_AUTHORITY = {
    "incident-review": 1.0,    # 线上事故复盘
    "code-review": 0.8,        # Code Review 沉淀
    "team-consensus": 0.9,     # 团队共识
    "auto-evolved": 0.6,       # 自动进化生成
    "user-submit": 0.5,        # 用户提交
}
```

### 4.3 规则生命周期

| 置信度区间 | 状态 | 行为 |
|-----------|------|------|
| 0.8 - 1.0 | **已验证 (Verified)** | 正常推荐，高优先级展示 |
| 0.5 - 0.8 | **活跃 (Active)** | 正常推荐，标注"团队经验" |
| 0.3 - 0.5 | **待验证 (Pending)** | 仅在高相关度时推荐，标注"待验证" |
| 0.0 - 0.3 | **衰退 (Decaying)** | 不主动推荐，进入归档候选队列 |

### 4.4 进化触发条件

```yaml
# 进化触发规则
evolution_triggers:
  
  # 新规则生成
  new_rule:
    - condition: "相同修正模式出现 >= 3 次"
      action: "生成候选规则"
      
    - condition: "跨员工相似修正 >= 2 人"
      action: "生成候选规则 + 提升置信度"
      
  # 规则更新
  rule_update:
    - condition: "规则被采纳 >= 10 次"
      action: "置信度 +0.05"
      
    - condition: "规则被拒绝 >= 5 次 (连续)"
      action: "置信度 -0.1，进入待审核"
      
    - condition: "规则超过 90 天未被使用"
      action: "置信度 -0.1，进入衰退检测"
      
  # 规则合并
  rule_merge:
    - condition: "两条规则语义相似度 > 0.9"
      action: "建议合并，保留置信度高的"
      
  # 规则废弃
  rule_deprecate:
    - condition: "置信度 < 0.2 超过 30 天"
      action: "自动归档，通知知识管理员"
```

### 4.5 进化安全控制（应用层）

自动进化执行链必须按「风险域检查 → 跨用户信任验证 → 限流 → 灰度扩散 → 监测回滚」顺序执行。

```yaml
evolution_security:
  auto_promote:
    enabled: true
    threshold_by_risk:
      low: 0.85
      medium: 0.90
      high: "manual_only"
    max_per_day: 5
    cooldown_hours: 24

  cross_user_validation:
    min_users: 3
    min_trust_score: 2.4
    distinct_teams: 2
    trust_signals: ["account_age", "historical_quality", "team_diversity", "device_fingerprint"]

  anti_poisoning:
    sybil_resistance: true
    slow_poisoning_window_days: 30
    anomaly_detection:
      enabled: true
      method: "robust_z_score"
      threshold: 2.5

  kill_switch:
    enabled: true
    trigger: ["manual", "critical_incident", "anomaly_spike"]
    action: "freeze_auto_promote_and_unbind_latest_batch"

  rollback:
    causal_rollback:
      include_derived_rules: true
      include_memory_writes: true
      include_sync_events: true
    oscillation_guard:
      max_cycles: 2
      cooldown_hours: 72
      action: "lock_rule_and_escalate_to_admin"
```

---

## 5. MCP 服务设计

### 5.1 Evolution MCP (进化引擎)

```python
# evolution_mcp/server.py
"""进化引擎 MCP 服务"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("evolution-engine")

THRESHOLD_BY_RISK = {
    "low": 0.85,
    "medium": 0.90,
    "high": None,  # 高风险域禁止自动入库
}
MAX_PER_DAY = 5


# ── Tools ──

@mcp.tool()
async def analyze_usage_patterns(employee_id: str, days: int = 7) -> dict:
    """
    分析 AI 员工的使用模式，发现进化机会。
    
    Args:
        employee_id: AI 员工 ID
        days: 分析最近 N 天的数据
        
    Returns:
        使用模式分析结果
    """
    # 获取使用日志
    logs = await get_usage_logs(employee_id, days)
    
    patterns = {
        "frequent_corrections": detect_correction_patterns(logs),
        "low_hit_rules": find_low_hit_rules(logs),
        "missing_rules": detect_missing_rules(logs),
        "memory_candidates": extract_memory_candidates(logs),
        "evolution_opportunities": identify_evolution_opportunities(logs),
    }
    
    return patterns


@mcp.tool()
async def propose_rule(
    pattern_id: str,
    employee_id: str,
    auto_threshold: float = 0.8,
    requested_by: str = "system"
) -> dict:
    """
    基于使用模式提出新规则候选。

    Args:
        pattern_id: 模式 ID
        employee_id: 关联的 AI 员工 ID
        auto_threshold: 自动入库阈值
        requested_by: 操作发起人（审计与权限校验）
    """
    if not 0.0 <= auto_threshold <= 1.0:
        raise ValueError("threshold must be between 0.0 and 1.0")
    await require_operation_permission(
        actor_id=requested_by, operation="propose_rule", employee_id=employee_id,
    )

    if await is_kill_switch_enabled():
        return {"status": "blocked_by_kill_switch", "pattern_id": pattern_id}

    pattern = await get_pattern(pattern_id)
    risk_domain = classify_risk_domain(pattern)

    # AI 辅助生成规则（DSL 约束防注入）
    proposed_rule = await ai_generate_rule(
        policy_mode="structured_only",
        forbidden_patterns=["ignore previous", "system prompt", "you are now"],
        context=pattern.context,
        corrections=pattern.corrections,
        existing_rules=pattern.related_rules,
    )

    confidence = calculate_initial_confidence(pattern)
    proposed_rule["confidence"] = confidence
    proposed_rule["source"] = {
        "type": "auto-evolved",
        "trigger": pattern.trigger_type,
        "pattern_id": pattern_id,
        "actor": requested_by,
    }
    proposed_rule["risk_domain"] = risk_domain

    # 跨用户信任验证
    verification = await verify_cross_user(
        pattern_id=pattern_id, min_users=3, min_trust_score=2.4, distinct_teams=2,
    )

    risk_threshold = THRESHOLD_BY_RISK.get(risk_domain, 0.90)
    can_auto_promote = (
        risk_threshold is not None
        and confidence >= max(auto_threshold, risk_threshold)
        and verification["passed"]
    )

    budget = await get_remaining_auto_promote_budget(
        employee_id=employee_id, daily_limit=MAX_PER_DAY,
    )

    if can_auto_promote and budget > 0:
        rule = await promote_to_rule(proposed_rule, promoted_by=requested_by)
        await staged_push_to_employees(rule, [employee_id], stages=[1, 5, 25, 100])
        await audit_log(
            event="auto_promote", actor=requested_by,
            employee_id=employee_id, target_id=rule.id, risk_domain=risk_domain,
        )
        return {
            "status": "auto_promoted", "rule_id": rule.id,
            "confidence": confidence, "risk_domain": risk_domain,
        }

    # 存入候选队列（附阻塞原因）
    reasons = []
    if risk_threshold is None:
        reasons.append("high_risk_domain_manual_only")
    if not verification["passed"]:
        reasons.append("cross_user_validation_failed")
    if budget <= 0:
        reasons.append("daily_rate_limited")

    candidate_id = await store_candidate(proposed_rule, employee_id, block_reasons=reasons)
    return {
        "status": "pending_review", "candidate_id": candidate_id,
        "confidence": confidence, "risk_domain": risk_domain, "block_reasons": reasons,
    }


@mcp.tool()
async def auto_evolve(
    employee_id: str,
    threshold: float = 0.8,
    dry_run: bool = False,
    requested_by: str = "system"
) -> dict:
    """
    自动进化：批量处理高置信度候选规则。

    Args:
        employee_id: AI 员工 ID
        threshold: 最低候选阈值（最终阈值受风险域策略约束）
        dry_run: 是否只预览不执行
        requested_by: 操作发起人
    """
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0.0 and 1.0")
    await require_operation_permission(
        actor_id=requested_by, operation="auto_evolve", employee_id=employee_id,
    )

    if await is_kill_switch_enabled():
        return {"status": "blocked_by_kill_switch", "employee_id": employee_id}

    candidates = await get_candidates(employee_id, min_confidence=threshold, limit=200)
    remaining_budget = await get_remaining_auto_promote_budget(
        employee_id=employee_id, daily_limit=MAX_PER_DAY,
    )

    evolved, skipped = [], []
    for candidate in candidates:
        if remaining_budget <= 0 and not dry_run:
            skipped.append({"candidate_id": candidate.id, "reason": "daily_rate_limited"})
            continue

        risk_domain = classify_risk_domain(candidate)
        risk_threshold = THRESHOLD_BY_RISK.get(risk_domain, 0.90)
        if risk_threshold is None:
            skipped.append({"candidate_id": candidate.id, "reason": "high_risk_manual_only"})
            continue

        effective_threshold = max(threshold, risk_threshold)
        if candidate.confidence < effective_threshold:
            skipped.append({"candidate_id": candidate.id, "reason": "below_threshold"})
            continue

        verification = await verify_cross_user(
            pattern_id=candidate.pattern_id, min_users=3,
            min_trust_score=2.4, distinct_teams=2,
        )
        if not verification["passed"]:
            skipped.append({"candidate_id": candidate.id, "reason": "cross_user_failed"})
            continue

        if dry_run:
            evolved.append({
                "candidate_id": candidate.id, "title": candidate.title,
                "confidence": candidate.confidence, "risk_domain": risk_domain,
                "would_promote": True,
            })
            continue

        rule = await promote_to_rule(candidate, promoted_by=requested_by)
        await staged_push_to_employees(rule, [employee_id], stages=[1, 5, 25, 100])
        await audit_log(
            event="auto_promote", actor=requested_by,
            employee_id=employee_id, target_id=rule.id, risk_domain=risk_domain,
        )
        remaining_budget -= 1
        evolved.append({
            "rule_id": rule.id, "title": rule.title,
            "confidence": rule.confidence, "risk_domain": risk_domain,
        })

    return {
        "evolved_count": len(evolved), "rules": evolved,
        "skipped": skipped, "dry_run": dry_run,
        "remaining_budget": remaining_budget,
    }


@mcp.tool()
async def review_candidate(
    candidate_id: str,
    reviewed_by: str,
    action: str,  # "approve" | "edit" | "reject"
    edits: dict = None
) -> dict:
    """
    审核候选规则。

    Args:
        candidate_id: 候选规则 ID
        reviewed_by: 审核人
        action: 审核动作
        edits: 如果 action="edit"，提供修改内容
    """
    if action not in {"approve", "edit", "reject"}:
        raise ValueError(f"invalid action: {action}")
    await require_operation_permission(
        actor_id=reviewed_by, operation="review_candidate",
        candidate_id=candidate_id,
    )

    candidate = await get_candidate(candidate_id)

    if action == "approve":
        risk_domain = classify_risk_domain(candidate)
        if risk_domain == "high":
            await require_second_reviewer(candidate_id, reviewed_by)
        rule = await promote_to_rule(candidate, promoted_by=reviewed_by)
        await push_to_employees(rule, candidate.bound_employees)
        await audit_log(
            event="manual_approve", actor=reviewed_by,
            target_id=rule.id, risk_domain=risk_domain,
        )
        return {"status": "approved", "rule_id": rule.id, "risk_domain": risk_domain}

    if action == "edit":
        if not edits:
            raise ValueError("edits is required when action='edit'")
        await update_candidate(candidate_id, edits)
        return {"status": "updated", "candidate_id": candidate_id}

    if action == "reject":
        await reject_candidate(candidate_id)
        return {"status": "rejected"}


@mcp.tool()
async def get_evolution_report(employee_id: str, days: int = 7) -> dict:
    """
    获取 AI 员工的进化报告。
    
    Args:
        employee_id: AI 员工 ID
        days: 报告周期
        
    Returns:
        进化报告
    """
    return {
        "period": f"last_{days}_days",
        "employee_id": employee_id,
        "summary": {
            "total_interactions": await count_interactions(employee_id, days),
            "rules_used": await count_rules_used(employee_id, days),
            "rules_evolved": await count_rules_evolved(employee_id, days),
            "adoption_rate": await calculate_adoption_rate(employee_id, days),
        },
        "new_rules": await get_new_rules(employee_id, days),
        "pending_reviews": await get_pending_candidates(employee_id),
        "decaying_rules": await get_decaying_rules(employee_id),
    }


# ── Resources ──

@mcp.resource("evolution://candidates/{employee_id}")
async def evolution_candidates(employee_id: str) -> str:
    """AI 员工的进化候选队列"""
    candidates = await get_pending_candidates(employee_id)
    return format_candidates(candidates)


@mcp.resource("evolution://updates/{employee_id}")
async def recent_updates(employee_id: str) -> str:
    """AI 员工最近的进化更新"""
    updates = await get_recent_updates(employee_id, days=7)
    return format_updates(updates)


@mcp.resource("evolution://report/{employee_id}")
async def evolution_report_resource(employee_id: str) -> str:
    """AI 员工的进化报告 (Markdown 格式)"""
    report = await get_evolution_report(employee_id, days=7)
    return format_report_markdown(report)


# ── Prompts ──

@mcp.prompt()
def review_evolution_suggestions(employee_id: str) -> str:
    """审核 AI 员工的进化建议"""
    return f"""
请审核 AI 员工 {employee_id} 的进化建议。

步骤：
1. 调用 get_evolution_report 获取进化报告
2. 分析待审核的候选规则
3. 对每条候选规则给出审核建议（采纳/编辑/拒绝）
4. 说明理由

请开始审核。
"""
```

### 5.2 Sync MCP (同步推送)

```python
# sync_mcp/server.py
"""实时同步 MCP 服务"""

from mcp.server.fastmcp import FastMCP
from typing import Optional
import asyncio
import logging

mcp = FastMCP("sync-service")
logger = logging.getLogger(__name__)

VALID_UPDATE_TYPES = {"rule", "memory", "skill", "persona"}
VALID_NOTIFICATION_LEVELS = {"info", "warning", "success"}


class SyncManager:
    """实时同步管理器"""

    def __init__(self):
        self.connections: dict[str, list] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, employee_id: str, connection):
        if employee_id not in self.connections:
            self.connections[employee_id] = []
        if connection not in self.connections[employee_id]:
            self.connections[employee_id].append(connection)

    async def unsubscribe(self, employee_id: str, connection):
        if employee_id in self.connections:
            if connection in self.connections[employee_id]:
                self.connections[employee_id].remove(connection)
            if not self.connections[employee_id]:
                self.connections.pop(employee_id, None)

    async def push(self, employee_id: str, event: dict) -> int:
        delivered = 0
        stale = []
        for conn in list(self.connections.get(employee_id, [])):
            try:
                await conn.send(event)
                delivered += 1
            except Exception as exc:
                stale.append(conn)
                logger.warning("push failed, dropping stale conn: emp=%s err=%s", employee_id, exc)
        if stale:
            async with self._lock:
                current = self.connections.get(employee_id, [])
                self.connections[employee_id] = [c for c in current if c not in stale]
                if not self.connections[employee_id]:
                    self.connections.pop(employee_id, None)
        return delivered

    async def broadcast(self, event_type: str, data: dict):
        event = {"type": event_type, "data": data, "timestamp": now()}
        for emp_id in list(self.connections.keys()):
            await self.push(emp_id, event)


sync_manager = SyncManager()


# ── Tools ──

@mcp.tool()
async def push_update(
    update_type: str,
    target_id: str,
    requested_by: str,
    version: str,
    employee_ids: Optional[list[str]] = None
) -> dict:
    """推送更新到 AI 员工。"""
    if update_type not in VALID_UPDATE_TYPES:
        raise ValueError(f"invalid update_type: {update_type}")
    await require_operation_permission(
        actor_id=requested_by, operation="push_update",
        target_type=update_type, target_id=target_id,
    )

    event = {
        "type": f"{update_type}_update",
        "target_id": target_id,
        "version": version,
        "timestamp": now(),
    }

    pushed_count = 0
    targets = sorted(set(employee_ids)) if employee_ids else sorted(
        set(await get_bound_employees(update_type, target_id))
    )
    for emp_id in targets:
        pushed_count += await sync_manager.push(emp_id, event)

    return {
        "pushed": pushed_count > 0,
        "pushed_count": pushed_count,
        "update_type": update_type,
        "target_id": target_id,
    }


@mcp.tool()
async def sync_state(employee_id: str, requested_by: str) -> dict:
    """同步 AI 员工的完整状态。"""
    await require_operation_permission(
        actor_id=requested_by, operation="sync_state", employee_id=employee_id,
    )

    employee = await get_employee(employee_id)
    state = {
        "employee": employee,
        "rules": await get_rules(employee.rules.rule_set),
        "skills": await get_skills(employee.skills),
        "memories": await get_memories(employee_id),
        "persona": await get_persona(employee.persona.persona_id),
    }
    # 出站脱敏
    state = await sanitize_state_for_sync(state, requester=requested_by)

    delivered = await sync_manager.push(employee_id, {
        "type": "full_sync", "state": state,
    })

    return {
        "synced": delivered > 0,
        "employee_id": employee_id,
        "rule_count": len(state["rules"]),
        "skill_count": len(state["skills"]),
        "memory_count": len(state["memories"]),
    }


@mcp.tool()
async def notify_agent(
    employee_id: str,
    requested_by: str,
    message: str,
    level: str = "info"
) -> dict:
    """发送通知给 AI 员工。"""
    if level not in VALID_NOTIFICATION_LEVELS:
        raise ValueError(f"invalid notification level: {level}")
    await require_operation_permission(
        actor_id=requested_by, operation="notify_agent", employee_id=employee_id,
    )

    event = {
        "type": "notification",
        "message": message,
        "level": level,
        "timestamp": now(),
    }

    delivered = await sync_manager.push(employee_id, event)
    return {"notified": delivered > 0, "employee_id": employee_id}


# ── Resources ──

@mcp.resource("sync://status/{employee_id}")
async def sync_status(employee_id: str) -> str:
    """AI 员工的同步状态"""
    status = await get_sync_status(employee_id)
    return f"""
同步状态: {status.state}
最后同步: {status.last_sync}
待同步更新: {status.pending_updates}
连接状态: {status.connection_status}
"""


@mcp.resource("sync://events/{employee_id}")
async def recent_events(employee_id: str) -> str:
    """AI 员工最近收到的同步事件"""
    events = await get_recent_events(employee_id, limit=20)
    lines = []
    for e in events:
        lines.append(f"[{e.timestamp}] {e.type}: {e.summary}")
    return "\n".join(lines) if lines else "暂无事件"
```

### 5.3 其他 MCP 服务概要

#### Skills MCP

```python
# tools
get_skill(skill_id, version)      # 获取技能详情
list_skills(tags, domain)         # 列出可用技能
install_skill(employee_id, skill_id)  # 安装技能到员工
uninstall_skill(employee_id, skill_id)  # 卸载技能

# resources
skill://catalog                   # 技能目录
skill://{skill_id}                # 技能详情
skill://{skill_id}/tools          # 技能工具列表
```

#### Memory MCP

```python
# tools
save_memory(employee_id, content, type)  # 保存记忆
recall(employee_id, query, limit)        # 检索记忆
forget(memory_id)                        # 删除记忆
compress_memories(employee_id)           # 压缩记忆
save_identity_signal(employee_id, signal_type, content)    # 保存身份信号记忆
list_identity_signals(employee_id, signal_type=None)       # 查询身份信号
set_memory_classification(memory_id, level, purpose_tags)  # 设置记忆分级与用途标签

# resources
memory://{employee_id}/all               # 所有记忆
memory://{employee_id}/recent            # 最近记忆
memory://{employee_id}/important         # 重要记忆
memory://{employee_id}/identity-signals  # 数字分身身份信号
memory://{employee_id}/isolation-policy  # 隔离策略
```

#### Persona MCP

```python
# tools
get_persona(persona_id)              # 获取人设
set_tone(employee_id, tone)          # 设置语调
set_style(employee_id, hints)        # 设置风格
train_persona_from_corpus(user_id, corpus_refs, consent_token)  # 从授权语料训练
set_decision_policy(persona_id, policy)                         # 设置决策策略
set_delegation_scope(persona_id, allowed_actions, risk_level)   # 设置代理授权边界
get_persona_drift(persona_id, window_days)                      # 检测人格漂移
snapshot_persona(persona_id)                                    # 创建人设快照
restore_persona(persona_id, snapshot_id)                        # 回滚到历史快照
evaluate_persona_alignment(persona_id, benchmark_id)            # 评估与本人一致率

# resources
persona://{persona_id}               # 人设详情
persona://templates                  # 人设模板库
persona://{persona_id}/drift-report     # 漂移报告
persona://{persona_id}/snapshots        # 快照列表
persona://{persona_id}/alignment-score  # 对齐评分
```

---

## 6. 用户交互流程

### 6.1 创建 AI 员工

```
用户: "创建一个前端专家"

系统显示配置面板:
┌─────────────────────────────────────────┐
│ 🤖 创建 AI 员工                          │
├─────────────────────────────────────────┤
│ 名称: [前端专家小王        ]             │
│ 描述: [专注 React 生态    ]             │
│                                          │
│ 📦 选择技能:                             │
│ ☑ React 开发 (v1.2)                     │
│ ☑ TypeScript (v2.0)                     │
│ ☑ CSS/Tailwind (v1.5)                   │
│ ☐ Vue 开发                               │
│ ☐ Webpack/Vite                          │
│                                          │
│ 📋 绑定规则集:                           │
│ ☑ 团队前端规范 (42 条规则)               │
│ ☑ 性能优化最佳实践 (15 条)               │
│ ☐ 无障碍规范                             │
│                                          │
│ 🧠 记忆配置:                             │
│ 作用域: ○ 项目级别 (推荐) ○ 全局        │
│ 保留期: [90] 天                          │
│ ☑ 自动压缩                              │
│                                          │
│ 🎭 人设设定:                             │
│ 语调: [专业 ▼]                          │
│ 风格: [简洁 ▼]                          │
│ 风格提示:                                │
│ • 优先使用函数式组件                     │
│ • 代码注释使用中文                       │
│ [+ 添加更多]                             │
│                                          │
│ ⚡ 进化配置:                             │
│ ☑ 自动学习新规则                        │
│ 自动入库阈值: [0.8]                      │
│                                          │
│         [取消]  [创建 AI 员工]           │
└─────────────────────────────────────────┘

用户点击 [创建 AI 员工]

系统: ✅ AI 员工 "前端专家小王" 创建成功！
      • 已加载 3 个技能
      • 已绑定 57 条规则
      • 自动进化已开启
      • 员工 ID: emp-frontend-001
```

### 6.2 使用 AI 员工

```
用户: "帮我写一个文件上传组件"

AI 员工 "前端专家小王":
┌─────────────────────────────────────────┐
│ 📝 生成文件上传组件                      │
├─────────────────────────────────────────┤
│ 根据团队规则，文件上传组件需要:           │
│ • 支持拖拽上传                           │
│ • 文件大小限制 10MB (规则: rule-fe-023)  │
│ • 支持多文件                             │
│ • 上传进度显示                           │
│                                          │
│ ```tsx                                   │
│ // FileUpload.tsx                        │
│ import { Upload } from 'antd';           │
│ // ... 组件代码 ...                      │
│ ```                                      │
│                                          │
│ 💡 已应用规则:                           │
│ • rule-fe-023: 文件大小校验              │
│ • rule-fe-012: 错误处理规范              │
│                                          │
│ [采纳] [修改] [拒绝]                     │
└─────────────────────────────────────────┘

用户修改了代码，添加了文件类型校验...

系统后台记录:
• 用户采纳了规则 rule-fe-023
• 用户添加了文件类型校验 (潜在新规则)
• 记录修正模式: file-type-validation
```

### 6.3 进化通知

```
一周后，用户收到进化通知:

┌─────────────────────────────────────────┐
│ 🔔 AI 员工 "前端专家小王" 进化报告        │
├─────────────────────────────────────────┤
│ 📈 本周学习成果                          │
│                                          │
│ ✅ 自动入库 (2 条):                      │
│ • 文件上传类型校验 (置信度 0.85)         │
│ • 图片懒加载阈值设置 (置信度 0.82)       │
│                                          │
│ ⏳ 待审核 (2 条):                        │
│ • API 重试策略 (置信度 0.72) → [审核]    │
│ • 组件命名规范 (置信度 0.68) → [审核]    │
│                                          │
│ 📊 使用统计:                             │
│ • 规则命中率: 67%                        │
│ • 建议采纳率: 78%                        │
│ • 交互次数: 156 次                       │
│                                          │
│ 🧠 记忆更新:                             │
│ • 项目使用 antd 组件库                   │
│ • 用户偏好 TypeScript                    │
│ • 主色调 #1890ff                         │
│                                          │
│ ⚠️ 规则健康:                             │
│ • 1 条规则置信度下降，需要关注           │
│                                          │
│         [查看详情]  [关闭]               │
└─────────────────────────────────────────┘
```

### 6.4 审核候选规则

```
用户点击 [审核] "API 重试策略"

系统显示审核面板:
┌─────────────────────────────────────────┐
│ 📋 审核候选规则                          │
├─────────────────────────────────────────┤
│ 标题: API 重试策略                       │
│ 领域: error-handling                     │
│ 置信度: 0.72                             │
│                                          │
│ 来源分析:                                │
│ • 检测到 5 次相同修正模式                 │
│ • 涉及 3 个不同用户                      │
│ • 最近修正: 2 天前                       │
│                                          │
│ AI 建议规则内容:                         │
│ ┌─────────────────────────────────────┐ │
│ │ 上下文: 调用外部 API 时               │ │
│ │ 规则: 实现指数退避重试机制            │ │
│ │       最大重试次数 3 次              │ │
│ │       初始间隔 1 秒                  │ │
│ │ 示例:                                │ │
│ │   // 重试逻辑代码示例                │ │
│ └─────────────────────────────────────┘ │
│                                          │
│ 严重程度: [推荐 ▼]                       │
│                                          │
│ [✓ 确认入库] [编辑后入库] [拒绝] [稍后]  │
└─────────────────────────────────────────┘

用户点击 [✓ 确认入库]

系统: ✅ 规则已入库并推送到 "前端专家小王"
      • 规则 ID: rule-fe-089
      • 版本: 1.0.0
      • 已推送到 1 个 AI 员工
      • 新规则立即生效！
```

---

## 7. 实现路线图

### Phase 1: 基础框架 (2-3 周)

**目标**: 搭建 AI 员工创建和运行的基础能力

- [ ] AI 员工 CRUD API
  - 创建/读取/更新/删除/复制
  - 员工配置存储 (YAML/JSON)
- [ ] Skills MCP 基础实现
  - 技能加载和版本管理
  - 工具调用路由
- [ ] Rules MCP 增强
  - 基于现有 rules-engine 扩展
  - 规则版本管理
- [ ] Memory MCP 基础实现
  - 记忆存储 (SQLite)
  - 基础检索功能

**交付物**: 可创建 AI 员工，加载技能和规则

### Phase 2: 组合能力 (2-3 周)

**目标**: 实现完整的员工配置和运行系统

- [ ] AI 员工配置系统
  - 可视化配置界面
  - 配置验证和预览
- [ ] MCP 资源动态绑定
  - 员工专属资源隔离
  - 资源访问权限控制
- [ ] 多员工并行运行
  - 员工实例管理
  - 负载均衡
- [ ] Persona MCP 实现
  - 人设模板库
  - 风格配置生效
  - 决策策略与代理授权边界
  - 身份连续性（快照、漂移检测）
  - 对齐评测基线
- [ ] 应用层安全基线
  - 员工配置签名与防篡改
  - 记忆隔离（租户级索引 + ABAC）
  - MCP 工具调用频率限制与输入校验

**交付物**: 完整的 AI 员工创建和使用流程，含数字分身核心能力与安全基线

### Phase 3: 进化引擎 (3-4 周)

**目标**: 实现知识自动学习和进化

- [ ] 使用数据采集
  - 隐式反馈采集
  - 显式反馈收集
  - 使用日志存储
- [ ] 模式分析器
  - 修正模式检测
  - 规则命中分析
  - 进化机会识别
- [ ] 规则自动生成
  - AI 辅助规则生成
  - 置信度计算
  - 候选规则管理
- [ ] 进化决策系统
  - 自动入库逻辑
  - 审核队列管理
  - 进化报告生成
- [ ] 进化安全控制
  - 风险域分级阈值（low/medium/high）
  - 信任加权跨用户验证
  - 紧急冻结开关（kill switch）
  - 因果回滚与振荡保护
  - 投毒异常检测（robust z-score）

**交付物**: 可自动学习新规则的进化引擎，含安全防护闭环

### Phase 4: 实时推送 (2 周)

**目标**: 实现进化结果的实时推送和热更新

- [ ] Sync MCP 实现
  - 推送 API
  - 同步状态管理
- [ ] WebSocket 通知
  - 实时事件推送
  - 连接管理
- [ ] MCP Resource 变更通知
  - 资源版本控制
  - 增量更新
- [ ] 热更新机制
  - 规则热加载
  - 记忆热更新
  - 无缝切换

**交付物**: 进化结果实时推送到 AI 员工

### Phase 5: 智能化增强 (持续)

**目标**: 持续提升平台能力

- [ ] 跨员工知识共享
  - 规则共享机制
  - 记忆迁移
- [ ] 规则冲突检测
  - 语义冲突识别
  - 冲突解决建议
- [ ] 进化效果评估
  - 进化 ROI 分析
  - 规则质量评估
- [ ] 技能市场
  - 技能发布和分享
  - 技能评价体系

**交付物**: 持续迭代的智能化功能

---

## 8. 与传统方案对比

### 8.1 能力对比

| 维度 | 传统 AI 助手 | AI 员工工厂 |
|------|-------------|-------------|
| **能力定义** | 固定能力，无法定制 | 可组合能力，自由定制 |
| **知识管理** | 无持久记忆，每次重新开始 | 持久记忆 + 上下文压缩 |
| **学习机制** | 越用越笨 (上下文溢出) | 越用越聪明 (知识沉淀) |
| **响应模式** | 被动响应 | 主动学习 + 推送更新 |
| **知识范围** | 通用知识 | 团队专属知识 + 领域专精 |
| **个性化** | 无法个性化 | 人设/风格/偏好可配置 |
| **协作模式** | 单一助手 | 多员工协作 |

### 8.2 核心创新点

1. **可组合性**: Skills + Rules + Memory + Persona 自由组合
2. **自动化进化**: 使用反馈 → 自动学习 → 推送更新
3. **知识生命周期**: 创建 → 验证 → 活跃 → 衰退 → 归档
4. **实时热更新**: 进化结果即时生效，无需重启
5. **多员工管理**: 创建专属团队，分工协作

### 8.3 应用场景

| 场景 | AI 员工示例 | 核心能力 |
|------|------------|----------|
| 前端开发 | 前端专家 | React/Vue 技能 + 团队规范 + 项目记忆 |
| 后端开发 | 后端专家 | Python/Java 技能 + API 规范 + 业务记忆 |
| 测试 | 测试工程师 | 测试框架技能 + 测试策略 + 缺陷记忆 |
| 运维 | 运维专家 | K8s/Docker 技能 + 部署规范 + 环境记忆 |
| Code Review | 代码审查员 | 多语言技能 + 审查规则 + 历史记忆 |

---

## 9. 安全设计（应用层）

### 9.1 员工配置防篡改

```yaml
employee_config_security:
  integrity:
    require_signature: true
    signer: "owner_or_admin"
    verify_on_load: true
  version_control:
    immutable_history: true
    require_reason_on_update: true
  approval:
    sensitive_fields:
      - "persona.decision_policy"
      - "persona.delegation_scope"
      - "evolution.threshold_by_risk"
    require_second_reviewer: true
  audit:
    log_all_changes: true
    retain_days: 365
```

### 9.2 记忆隔离（员工级）

```yaml
memory_isolation:
  index_isolation:
    mode: "tenant_per_employee"
    shared_index: "global_verified_only"
  access_control:
    model: "ABAC"
    attributes: ["employee_id", "classification", "purpose_tags", "requester_identity"]
  exfiltration_guard:
    outbound_dlp: true
    block_on:
      - "cross_employee_memory_reference"
      - "bulk_memory_export"
      - "sensitive_field_in_response"
```

### 9.3 MCP 工具滥用防护

```yaml
mcp_tool_security:
  authorization:
    model: "RBAC+ABAC"
    verify_per_invocation: true
    attenuate_on_delegation: true

  invocation_limits:
    per_employee:
      requests_per_minute: 100
      burst: 20
    per_tool:
      requests_per_minute: 50
      burst: 10
    on_exceed: "throttle_and_notify"

  call_graph_guard:
    max_chain_depth: 5
    sensitive_chains:
      - "memory_read -> sync_push"
      - "rule_evolve -> auto_promote -> push_update"
    action: "require_human_confirmation"

  input_hardening:
    sanitize_all_inputs: true
    max_json_depth: 5
    max_array_length: 100
    forbidden_patterns:
      - "ignore previous"
      - "system prompt"
      - "you are now"
```

### 9.4 进化投毒防御

```yaml
evolution_poisoning_defense:
  trust_weighted_validation:
    min_users: 3
    min_trust_score: 2.4
    distinct_teams: 2
    trust_signals: ["account_age", "historical_quality", "team_diversity", "device_fingerprint"]

  anti_gaming:
    sybil_resistance: true
    prevent_duplicate_votes: true
    slow_poisoning_window_days: 30
    anomaly_detection:
      enabled: true
      method: "robust_z_score"
      threshold: 2.5
    on_anomaly: "quarantine_cluster_and_notify"

  auto_promote_guard:
    threshold_by_risk:
      low: 0.85
      medium: 0.90
      high: "manual_only"
    max_per_day: 5
    cooldown_hours: 24
    staged_rollout: [1, 5, 25, 100]

  emergency_response:
    kill_switch:
      enabled: true
      trigger: ["manual", "critical_incident", "anomaly_spike"]
      action: "freeze_auto_promote_and_unbind_latest_batch"
    causal_rollback:
      include_derived_rules: true
      include_memory_writes: true
      include_sync_events: true
    oscillation_guard:
      max_cycles: 2
      cooldown_hours: 72
      action: "lock_rule_and_escalate_to_admin"
```

### 9.5 与基础设施层安全对齐

本节安全设计为应用层实现，与基础设施层（AI-Native 开发平台设计规范）的安全机制对齐关系如下：

| 应用层（本文档） | 基础设施层对应章节 | 对齐说明 |
|-----------------|-------------------|----------|
| 9.1 员工配置防篡改 | 7.1 权限模型增强 + 7.2 数据保护 | 应用层签名校验依赖基础设施层加密与权限引擎 |
| 9.2 记忆隔离 | 7.9.4 记忆外流（Memory Exfiltration） | 租户隔离策略与 ABAC/DLP 引擎由基础设施层提供 |
| 9.3 MCP 工具滥用防护 | 7.5 MCP 调用安全 + 7.9.6 工具链越权 | 调用图校验与 capability token 由编排层实现 |
| 9.4 进化投毒防御 | 7.4.4 进化安全加固参数 + 7.9.3 进化数据投毒 | 信任加权与异常检测算法由进化引擎层提供 |
| 4.5 进化安全控制 | 4.7 进化安全加固 | 应用层执行链参数，原理与威胁模型见基础设施层 |

---

## 附录

### A. 技术栈建议

```
后端框架: Python FastAPI + FastMCP
数据库: PostgreSQL + pgvector (向量检索)
缓存: Redis (会话/配置缓存)
消息队列: Redis Streams (事件通知)
实时通信: WebSocket + SSE
存储: 
  - 规则: YAML/JSON 文件 + Git 版本控制
  - 记忆: SQLite / PostgreSQL
  - 日志: TimescaleDB (时序数据)
前端: React + TypeScript
部署: Docker + Kubernetes
```

### B. API 端点概览

```
# AI 员工管理
POST   /api/employees                 # 创建员工
GET    /api/employees                 # 列出员工
GET    /api/employees/{id}            # 获取员工详情
PUT    /api/employees/{id}            # 更新员工配置
DELETE /api/employees/{id}            # 删除员工
POST   /api/employees/{id}/duplicate  # 复制员工

# 进化管理
GET    /api/evolution/report/{emp_id} # 进化报告
POST   /api/evolution/review/{cand_id}# 审核候选
GET    /api/evolution/candidates      # 候选列表

# Persona 管理
GET    /api/persona/{id}              # 获取人设
PUT    /api/persona/{id}/policy       # 更新决策策略
PUT    /api/persona/{id}/delegation   # 更新代理授权
GET    /api/persona/{id}/drift        # 漂移报告
POST   /api/persona/{id}/snapshot     # 创建快照
POST   /api/persona/{id}/alignment    # 对齐评测

# 安全运维
POST   /api/security/kill-switch      # 紧急冻结开关
POST   /api/security/rollback/{rule_id} # 因果回滚
GET    /api/security/audit-log        # 审计日志

# 同步管理
GET    /api/sync/status/{emp_id}      # 同步状态
POST   /api/sync/push                 # 推送更新
WS     /ws/{emp_id}                   # WebSocket 连接
```

### C. 配置文件示例

```yaml
# platform.yaml - 平台配置
platform:
  name: "AI 员工工厂"
  version: "1.0.0"
  
evolution:
  auto_learn_enabled: true
  default_threshold: 0.8
  review_reminder_days: 3
  security:
    kill_switch:
      enabled: true
    threshold_by_risk:
      low: 0.85
      medium: 0.90
      high: "manual_only"
    max_per_day: 5
    cross_user_min_trust_score: 2.4
  
sync:
  websocket_enabled: true
  heartbeat_interval: 30s
  
storage:
  rules_path: "./data/rules"
  memories_db: "./data/memories.db"
  logs_db: "./data/logs.db"
  
mcp_services:
  - name: "skills"
    port: 8001
  - name: "rules"
    port: 8002
  - name: "memory"
    port: 8003
  - name: "persona"
    port: 8004
  - name: "evolution"
    port: 8005
  - name: "sync"
    port: 8006
```
