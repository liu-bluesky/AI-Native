---
name: db-query
description: 数据库直连查询技能。触发条件：需要查询表结构、验证数据、执行SQL、新增/修改模块时检查数据库状态。支持 MySQL 和 PostgreSQL。首次使用向用户索要配置后自动持久化，后续直接使用。连接失败时自动提示用户更新配置。
---

# 技能：数据库直连查询

> 触发条件：任何需要访问数据库的场景

---

## 配置机制

配置文件目录：`<db-query 技能目录>/`（即 `scripts/` 的上一级目录）

配置文件命名（按优先级匹配）：
1. 传 `--api-key`：`.db-config-{api_key}.json`
2. 未传 `--api-key` 但传 `--employee-id`：`.db-config-{employee_id}.json`
3. 两者都未传：`.db-config.json`

配置合并优先级（高 → 低）：
1. 显式 CLI 参数：`--host/--port/--user/--password/--database/--type`
2. `--env`
3. `--url`
4. 已保存配置文件

**首次使用流程：**
1. 脚本检测无配置 → 退出码 2，stderr 输出 `NO_CONFIG`
2. AI 助手向用户索要：数据库连接串（JDBC URL / 标准 URL）或分项参数
3. 用户提供后，通过 `--url` / `--env` / CLI 参数传入 → 脚本自动保存到当前作用域配置文件
4. 后续调用只需 `--sql` 即可，无需重复传参

**连接失败流程：**
1. 连接异常 → 退出码 3，stderr 输出 `CONNECTION_FAILED: ...`
2. AI 助手将错误信息反馈给用户，请求提供新配置
3. 用户提供新配置后重新执行，脚本自动覆盖旧配置

---

## 使用方式

### 日常使用（已有配置）

```bash
python3 skills/db-query/scripts/db_query.py --sql "SHOW TABLES"
```

### 首次配置 / 更新配置

```bash
# 方式一：连接串（推荐，用户直接粘贴即可）
python3 skills/db-query/scripts/db_query.py \
  --url "jdbc:mysql://host:3306/db?user=root&password=xxx" \
  --sql "SHOW TABLES"

# 方式二：标准 URL
python3 skills/db-query/scripts/db_query.py \
  --url "mysql://root:xxx@host:3306/db" \
  --sql "SHOW TABLES"

# 方式三：手动传参（自动保存）
python3 skills/db-query/scripts/db_query.py \
  --type mysql --host <HOST> --port <PORT> \
  --user <USER> --password <PASSWORD> --database <DB> \
  --sql "SHOW TABLES"

# 方式四：从 .env 导入（自动保存）
python3 skills/db-query/scripts/db_query.py \
  --env server/.env --sql "SHOW TABLES"

# 重置配置
python3 skills/db-query/scripts/db_query.py --reset --sql ""
```

### 常用操作

```bash
--sql "SHOW TABLES"
--sql "DESC table_name"
--sql "SHOW CREATE TABLE table_name"
--sql "SELECT * FROM table_name"
--allow-write --sql "ALTER TABLE xxx ADD COLUMN yyy VARCHAR(50)"
--allow-write --sql "INSERT INTO ..."
```

---

## 退出码

| 码 | 含义 | AI 应对 |
|----|------|-------------|
| 0 | 成功 | 正常输出结果 |
| 1 | SQL 错误或写操作被拦截 | 检查 SQL 语法 |
| 2 | 无配置 (`NO_CONFIG`) | 向用户索要数据库连接信息 |
| 3 | 连接失败 (`CONNECTION_FAILED`) | 反馈错误，请用户提供新配置 |

---

## 参数说明

| 参数 | 说明 |
|------|------|
| `--cd` | 兼容参数，当前实现保留但不影响配置文件实际存储目录 |
| `--employee-id` | 员工级配置隔离（对应 `.db-config-{employee_id}.json`） |
| `--api-key` | 用户级配置隔离（对应 `.db-config-{api_key}.json`，优先于 `--employee-id`） |
| `--sql` | 要执行的 SQL（必填） |
| `--url` | 连接串：JDBC / 标准 URL / PostgreSQL URL |
| `--env` | .env 文件路径，导入并保存配置 |
| `--type` | `mysql`(默认) / `postgres` |
| `--host/port/user/password/database` | 手动指定连接参数 |
| `--save` | 兼容参数，当前版本可不使用（配置变更会自动保存） |
| `--allow-write` | 允许写操作 |
| `--limit` | SELECT 最大行数，默认 50 |
| `--format` | `table`(默认) / `json` / `csv` |
| `--reset` | 删除已保存的配置 |

---

## 安全规则

1. 默认只读，写操作需 `--allow-write`
2. SELECT 自动限行 50
3. `.db-config*.json` 需加入 `.gitignore`，禁止提交

---

## 分享给其他项目

1. 复制 `skills/db-query/` 目录（不含 `.db-config*.json`）
2. 安装依赖：`pip3 install pymysql psycopg2-binary`
3. 首次使用时脚本会自动引导配置
