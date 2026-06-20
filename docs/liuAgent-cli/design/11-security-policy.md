# 安全策略

安全策略负责判断动作能不能执行、是否需要用户确认、授权能持续多久，以及事后如何审计。它位于 Tool Runtime 和 Adapter 之间，不能只存在于 UI 层。

## SecurityContext

每次权限判断都需要上下文。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `session_id` | ID | 是 | 会话 ID。 |
| `run_id` | ID | 否 | 所属 Run。 |
| `client_id` | ID | 否 | 发起动作的客户端。 |
| `adapter` | `cli` \| `web` \| `desktop` | 是 | 当前入口。 |
| `workspace_root` | AbsolutePath | 否 | 工作区根目录。 |
| `user_id` | ID | 否 | 用户 ID。 |
| `policy_profile` | string | 是 | 策略档位，例如 `default`、`strict`、`trusted_local`。 |

`adapter=desktop` 不代表自动可信。它只能说明能力更强，因此审计更严格。

## PolicyRule

策略规则描述某类动作的默认处理。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `rule_id` | ID | 是 | 规则 ID。 |
| `action` | string | 是 | 动作名，例如 `file.write`、`command.run`、`url.open`。 |
| `risk` | RiskLevel | 是 | 风险等级。 |
| `match` | object | 是 | 路径、命令、域名、工具名等匹配条件。 |
| `decision` | `allow` \| `ask` \| `deny` | 是 | 默认决策。 |
| `grant_scope` | PolicyGrantScope[] | 是 | 允许的授权范围；`never` 只表示禁止授权记忆。 |
| `audit_required` | boolean | 是 | 是否必须审计。 |

示例：

```json
{
  "rule_id": "policy_workspace_write",
  "action": "file.write",
  "risk": "medium",
  "match": {
    "path_scope": "workspace"
  },
  "decision": "ask",
  "grant_scope": ["once", "session"],
  "audit_required": true
}
```

## PolicyRule.match 语义

`match` 是结构化匹配条件，不允许实现成任意脚本。所有字段默认是 AND 关系；同一字段内的数组默认是 OR 关系。

支持字段：

| 字段 | 类型 | 语义 |
| --- | --- | --- |
| `tool` | string \| string[] | 精确匹配工具名，例如 `read_file`。 |
| `action` | string \| string[] | 精确匹配动作名，例如 `file.write`。 |
| `path_scope` | `workspace` \| `outside_workspace` \| `system` | 按规范化后的绝对路径归类。 |
| `path_glob` | string \| string[] | 匹配 workspace 相对路径，禁止用它放行 `..` 逃逸路径。 |
| `command_prefix` | string \| string[] | 以 shell 解析后的 argv 前缀匹配，不按原始字符串前缀匹配。 |
| `domain` | string \| string[] | URL 主机名精确匹配或子域匹配。 |
| `method` | string \| string[] | HTTP 方法或动作方法。 |
| `risk_at_least` | RiskLevel | 匹配大于等于该风险等级的动作。 |

路径匹配必须先做规范化：

1. 展开为绝对路径。
2. 解析符号链接。
3. 判断是否仍在 `workspace_root` 内。
4. 再计算相对路径并匹配 `path_glob`。

命令匹配必须先做 argv 解析，`command_prefix=["npm", "install"]` 只匹配 argv 前两段，不匹配 `npm install-malicious`。

规则冲突处理：

1. `deny` 优先级最高。
2. 更高 `risk` 优先于更低 `risk`。
3. 更具体的 match 优先于更宽泛的 match。
4. 仍冲突时按 `rule_id` 字典序稳定排序，避免不同端结果不一致。

策略缺失或匹配异常时，默认按 `ask` 或 `deny` 处理，不能静默 `allow`。

## GrantScope / PolicyGrantScope

`GrantScope` 只用于批准类选项、用户决策和已经生成的 Grant，不包含 `never`。

| 值 | 含义 | 典型用途 |
| --- | --- | --- |
| `once` | 只允许当前请求 | 高风险命令、打开授权链接。 |
| `run` | 只允许当前 Run | 同一轮内重复读取同类信息。 |
| `session` | 允许当前 Session | 多次写同一工作区文件。 |
| `workspace` | 允许当前工作区 | 低风险重复操作。 |

`PolicyGrantScope` 是策略配置层类型，取值为 `GrantScope | "never"`。

| 值 | 含义 | 典型用途 |
| --- | --- | --- |
| `never` | 禁止授权记忆 | 删除、部署、凭据外传。 |

`critical` 风险动作默认只允许 `"once"` 或 `"never"`，不能静默升级成长期授权。`never` 不能进入 `PermissionOption.grant_scope`、`PermissionDecision.grant_scope` 或 `PermissionGrant.scope`。

## PermissionGrant

授权决策可以被持久化为 Grant。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `grant_id` | ID | 是 | 授权 ID。 |
| `request_id` | ID | 是 | 来源权限请求。 |
| `action` | string | 是 | 授权动作。 |
| `scope` | GrantScope | 是 | 授权作用域。 |
| `constraints` | object | 是 | 路径、命令前缀、域名、工具名限制。 |
| `granted_by` | `user` \| `policy` | 是 | 授权来源。 |
| `expires_at` | Timestamp | 否 | 过期时间。 |
| `created_at` | Timestamp | 是 | 创建时间。 |

授权必须带约束。不能只保存“用户同意执行命令”这种宽泛结论。

只有批准类 `PermissionDecision` 可以生成 `PermissionGrant`。`deny`、`revise` 或策略命中 `PolicyGrantScope.never` 不能生成持久授权；批准类决策生成的 `PermissionGrant.scope` 必须等于 `PermissionDecision.grant_scope`，且不能是 `never`。

## 策略评估流程

```text
ToolCall / AdapterCommand
  -> build SecurityContext
  -> match PolicyRule
  -> lookup PermissionGrant
  -> allow / ask / deny
  -> write AuditLog
  -> execute or stop
```

规则：

- 命中 `deny` 时不得再发起用户确认，除非用户修改请求。
- 命中 `ask` 时必须发出 `approval_required` 事件。
- 命中已有 Grant 时仍要写审计摘要。
- 策略缺失时按更保守等级处理。

## 关键动作策略

| 动作 | 默认风险 | 默认策略 | 说明 |
| --- | --- | --- | --- |
| `file.read` | safe | allow | 限 workspace 内自动允许。 |
| `file.write` | medium | ask | 需要展示路径和 diff 摘要。 |
| `file.delete` | high | ask | 必须列出删除对象。 |
| `command.run` | high | ask | 必须展示命令、目录、影响范围。 |
| `url.open` | medium | ask | 授权链接必须说明原因。 |
| `network.post` | high | ask | 必须说明目标域名和数据类型。 |
| `credential.read` | critical | deny | 默认禁止。 |
| `deploy.run` | critical | ask | 必须单次授权，不能 session 授权。 |

## 策略存储

建议文件布局：

```text
.liuagent/
  security/
    policy.json
    grants.jsonl
    audit.jsonl
```

存储规则：

- `policy.json` 可以由用户配置或项目模板生成。
- `grants.jsonl` 追加记录授权，不静默改写历史。
- `audit.jsonl` 记录策略判断、用户决策和执行结果。
- Grant 失效不删除历史，只在读取时判定过期。

## 跨端授权一致性

CLI、Web、Desktop 必须使用同一个 `PermissionRequest` 和 `PermissionDecision`。

同一请求在不同端展示可以不同：

- CLI 展示文本确认。
- Web 展示按钮和差异预览。
- Desktop 展示原生弹窗。

但它们回传的结构必须一致，最终只产生一个有效决策。

## 审计最低要求

每条高风险动作必须写入 `AuditLog` canonical 结构，最低要求如下：

- `session_id`
- `run_id`
- `client_id`
- `adapter`
- `request.action`
- `request.risk`
- `request.preview`
- `decision.decision`
- `decision.idempotency_key`
- `result.executed`
- `result.ok`
- `result.summary`
- `created_at`

如果工具执行失败，也要记录失败结果，不能只记录授权成功。

## 禁止行为

- UI 自行绕过 Permission Gate 执行本地命令。
- Web 根据终端文本猜测用户已经授权。
- 将高风险授权默认保存为永久允许。
- 策略判断失败后静默降级为允许。
- 把凭据、token、cookie 写入普通 transcript。
