# MCP 服务开发规范

> 适用于所有 mcp-* 目录下的 FastMCP 服务。

## 服务目录结构

```
mcp-{name}/
├── server.py          # FastMCP 入口，定义 Tools/Resources/Prompts
├── store.py           # 数据模型 + Store 类
├── pyproject.toml     # 包定义
└── knowledge/         # 数据存储目录
    └── {items}/       # 按实体类型分子目录
```

## 服务注册

每个服务使用唯一的 FastMCP 名称：

```python
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("{name}-service")  # 如 "skills-service"
```

已注册服务名：

| 目录 | FastMCP 名称 |
|------|-------------|
| mcp-skills | `skills-service` |
| mcp-rules | `rules-service` |
| mcp-memory | `memory-service` |
| mcp-persona | `persona-service` |
| mcp-evolution | `evolution-engine` |
| mcp-sync | `sync-service` |

## Tool 定义规范

### 装饰器

```python
@mcp.tool()
def tool_name(param: str, optional_param: str = "") -> dict:
    """中文工具描述"""
    ...
```

### 返回值约定

- 成功：返回业务数据 dict（经 `_serialize_xxx()` 序列化）
- 失败：返回 `{"error": "描述信息"}`
- 禁止抛异常，所有错误通过 error dict 传递

### 参数验证

枚举参数统一用 `_parse_enum` 模式：

```python
def _parse_enum(cls, value: str, name: str) -> tuple:
    try:
        return cls(value), None
    except ValueError:
        valid = [e.value for e in cls]
        return None, {"error": f"Invalid {name}: {value}. Valid: {valid}"}

# 在 Tool 中使用
sev, err = _parse_enum(Severity, severity, "severity")
if err:
    return err
```

## Resource 定义规范

```python
@mcp.resource("skill://catalog")
def skill_catalog() -> str:
    """技能目录"""
    ...

@mcp.resource("skill://{skill_id}")
def skill_detail(skill_id: str) -> str:
    """技能详情"""
    ...
```

URI 命名约定：
- 目录型：`{domain}://catalog`、`{domain}://domains`
- 实体型：`{domain}://{id}`
- 子资源：`{domain}://{id}/{sub}`

## 服务间隔离

- 每个 MCP 服务独立运行，拥有独立的 `store.py` 和 `knowledge/` 目录
- 服务间禁止直接 import（唯一例外：`web-admin/api/server.py` 聚合层）
- 跨服务通信通过 `mcp-sync` 的 `push_update` 工具

## 进化引擎约束

`mcp-evolution` 有特殊的安全约束：

```python
THRESHOLD_BY_RISK = {
    "low": 0.85,      # 低风险：置信度 ≥ 0.85 可自动晋升
    "medium": 0.90,    # 中风险：置信度 ≥ 0.90 可自动晋升
    "high": None,      # 高风险：禁止自动晋升，必须人工审核
}
MAX_PER_DAY = 5        # 每日自动晋升上限
```

- `auto_evolve` 支持 `dry_run` 模式，预览不执行
- 高风险候选必须经 `review_candidate` 人工审批

## 新增 MCP 服务检查清单

- [ ] 创建 `mcp-{name}/` 目录，含 server.py、store.py、pyproject.toml
- [ ] 数据模型使用 `@dataclass(frozen=True)`
- [ ] 实现 `_serialize_xxx()` / `_deserialize_xxx()` 函数对
- [ ] Store 类继承统一模式（见 `rules/backend.md`）
- [ ] Tool 返回 dict，错误用 `{"error": "..."}` 格式
- [ ] Resource URI 遵循命名约定
- [ ] 在 `web-admin/api/server.py` 中添加代理路由
- [ ] 在 `docs/00-项目总览/PROJECT.md` 的 MCP 服务矩阵中注册
