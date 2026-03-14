# 后端编码规范

> 适用于 web-admin/api/ 和所有 mcp-* 服务。

## 语言与框架

- Python 3.10+，类型注解必须
- Web 框架：FastAPI（web-admin/api/）
- MCP 框架：FastMCP 3.0+（mcp-* 服务）
- 验证：Pydantic BaseModel（API 层）
- 认证：JWT HS256（PyJWT）

## 数据模型

### dataclass 使用约定

MCP 服务内的领域模型优先使用 `@dataclass(frozen=True)`；网关侧 Core Store 可以使用普通 `@dataclass` 以支持 patch/merge 型配置对象（如系统配置、项目配置、外部 MCP 模块）。

推荐模式：

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class Rule:
    id: str
    domain: str
    title: str
    content: str
    severity: Severity = Severity.RECOMMENDED
    version: SemanticVersion = field(default_factory=SemanticVersion)
    changelog: tuple[str, ...] = ()          # 用 tuple 不用 list
    created_at: str = field(default_factory=_now_iso)
```

关键约束：
- MCP 领域模型中的集合字段优先用 `tuple[T, ...]`
- 字典字段用 `field(default_factory=dict)`，避免共享默认值
- frozen dataclass 的修改使用 `dataclasses.replace(obj, field=new_value)`
- 时间戳统一用 `_now_iso()` 生成 ISO 8601 字符串
- 若使用普通 dataclass，必须保证 patch/save 路径清晰，禁止隐式共享可变默认值

### ID 生成

```python
def new_id(self) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"
```

前缀约定：`rule-`、`emp-`、`persona-`、`skill-`、`evo-`、`sync-`、`mem-`。

### 枚举

用 `str, Enum` 双继承，确保 JSON 序列化友好：

```python
class Severity(str, Enum):
    REQUIRED = "required"
    RECOMMENDED = "recommended"
    OPTIONAL = "optional"
```

## Store 层约定

当前后端有两类 Store：

1. `mcp-{name}/store.py`
2. `web-admin/api/stores/json/*.py` 与 `web-admin/api/stores/postgres/*.py`

MCP 服务的 `store.py` 通常包含：

1. 数据模型（frozen dataclass）
2. 序列化函数对：`_serialize_xxx()` / `_deserialize_xxx()`
3. Store 类：封装 CRUD 操作

Core Store 则按后端拆分为 JSON / PostgreSQL 两套实现，并由 `stores/factory.py` 暴露懒加载代理。

### JSON 文件存储

```python
class XxxStore:
    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "items"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, item_id: str) -> Path:
        return self._dir / f"{item_id}.json"

    def save(self, item: Xxx) -> None:
        self._path(item.id).write_text(
            json.dumps(_serialize_xxx(item), ensure_ascii=False, indent=2))

    def get(self, item_id: str) -> Optional[Xxx]:
        p = self._path(item_id)
        if not p.exists():
            return None
        return _deserialize_xxx(json.loads(p.read_text()))

    def list_all(self) -> list[Xxx]:
        return [_deserialize_xxx(json.loads(p.read_text()))
                for p in sorted(self._dir.glob("*.json"))]
```

### SQLite 存储

- 主要用于 `mcp-memory` 和部分 usage 数据
- 使用 `sqlite3.Row` 行工厂
- 写操作后立即 `commit()`
- 建索引加速查询：`employee_id`、`type`

### PostgreSQL 存储

- 网关侧 Core Store 优先通过 `web-admin/api/stores/postgres/*.py` 提供
- MCP Bridge 也支持 PostgreSQL 代理实现，见 `web-admin/api/stores/postgres/mcp_bridge.py`
- 驱动缺失时统一抛出带安装建议的错误信息

## FastAPI 路由规范

### 目录结构

路由按域拆分到 `routers/` 目录，每个文件一个 `APIRouter`：

```
web-admin/api/
├── server.py              ← 兼容入口，转发到 core.server
├── core/
│   ├── server.py          ← 真正的 FastAPI app 创建与 router 注册
│   ├── deps.py            ← 公共依赖（require_auth + store proxy）
│   ├── auth.py            ← JWT 认证
│   └── config.py          ← 环境配置
├── models/requests.py     ← Pydantic 请求模型
├── stores/
│   ├── factory.py         ← Core Store 懒加载代理
│   ├── mcp_bridge.py      ← MCP Store importlib 桥接
│   ├── json/              ← JSON Store 实现
│   └── postgres/          ← PostgreSQL Store 实现
├── services/              ← 业务编排 / 动态 MCP / LLM 服务
└── routers/
    ├── init_auth.py       ← /api/init/*, /api/auth/*
    ├── employees.py       ← /api/employees/*
    ├── projects.py        ← /api/projects/* 与项目聊天
    ├── skills.py          ← /api/skills/*, /api/employees/*/skills
    ├── rules.py           ← /api/rules/*
    ├── llm_providers.py   ← /api/llm-providers/*
    ├── memory.py          ← /api/memory/*
    ├── personas.py        ← /api/personas/*
    ├── evolution.py       ← /api/evolution/*
    ├── sync.py            ← /api/sync/*
    ├── system_config.py   ← /api/system-config/*
    ├── usage.py           ← /api/usage/*
    ├── users.py / roles.py
    └── mcp_modules.py     ← /api/mcp/modules/*
```

### Router 模板

```python
from fastapi import APIRouter, Depends
from core.deps import require_auth
from stores.factory import project_store

router = APIRouter(prefix="/api/xxx", dependencies=[Depends(require_auth)])

@router.get("")
async def list_items():
    ...
```

### Store 组织

- `stores/factory.py`：管理用户、角色、项目、系统配置、外部 MCP 模块等网关侧 Store
- `stores/mcp_bridge.py`：按路径加载各 `mcp-* / store.py`，向路由层暴露技能、规则、记忆、人设、进化、同步相关 Store 与序列化函数
- 路由文件按所属域从对应模块导入，不再统一从单个 `stores.py` 导入

### 认证依赖

受保护路由统一使用 `Depends(require_auth)`：

```python
async def require_auth(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid token")
    payload = decode_token(authorization[7:])
    if payload is None:
        raise HTTPException(401, "Token expired or invalid")
    return payload
```

### 请求/响应模型

- 请求体用 Pydantic `BaseModel`，可选字段用 `T | None = None`
- 响应直接返回 dict，无需 response_model
- 列表响应包裹在具名字段中：`{"employees": [...]}` 而非裸数组

## 错误处理

### MCP Tool 层

返回 `{"error": "描述"}` 字典，不抛异常：

```python
@mcp.tool()
def get_skill(skill_id: str) -> dict:
    s = skill_store.get(skill_id)
    if s is None:
        return {"error": f"Skill {skill_id} not found"}
    return _serialize_skill(s)
```

### 枚举解析

统一使用 `_parse_enum` 辅助函数：

```python
def _parse_enum(cls, value: str, name: str) -> tuple:
    try:
        return cls(value), None
    except ValueError:
        valid = [e.value for e in cls]
        return None, {"error": f"Invalid {name}: {value}. Valid: {valid}"}
```

### FastAPI 层

用 `HTTPException` 抛出标准 HTTP 错误码。

## 代码风格

- 文件头统一 `from __future__ import annotations`
- 私有辅助函数以 `_` 前缀命名：`_now_iso()`、`_serialize_rule()`
- 模块级常量大写：`THRESHOLD_BY_RISK`、`MAX_PER_DAY`
- 集合常量用 set：`_VALID_TONES = {"professional", "friendly", "strict"}`
- 导入顺序：标准库 → 第三方 → 本地模块，各组间空行分隔

## 禁止事项

- 禁止在 frozen dataclass 上通过 `__post_init__` 直接赋值修改字段
- 禁止在 Store 层引入业务逻辑，Store 只做数据存取
- 禁止跨 MCP 服务直接 import（`web-admin/api/stores/mcp_bridge.py` 聚合层除外）
- 禁止在 MCP Tool 中抛异常，统一返回 error dict
- 禁止硬编码密钥，JWT secret 从环境变量读取
