# db-query 数据库查询技能 - 使用文档

## 快速开始

### 1. 安装依赖

```bash
pip3 install pymysql psycopg2-binary
```

### 2. 首次配置（四选一）

**方式一：连接串（推荐，直接从项目配置复制）**
```bash
python3 skills/db-query/scripts/db_query.py \
  --url "jdbc:mysql://host:3306/mydb?user=root&password=123456" \
  --sql "SHOW TABLES"
```

**方式二：标准 URL**
```bash
python3 skills/db-query/scripts/db_query.py \
  --url "mysql://root:123456@host:3306/mydb" \
  --sql "SHOW TABLES"
```

**方式三：从 .env 导入**
```bash
python3 skills/db-query/scripts/db_query.py \
  --env server/.env \
  --sql "SHOW TABLES"
```

**方式四：手动参数**
```bash
python3 skills/db-query/scripts/db_query.py \
  --type mysql --host 127.0.0.1 --port 3306 \
  --user root --password 123456 --database mydb \
  --sql "SHOW TABLES"
```

首次执行成功后，配置会保存到技能目录下的对应文件：
- 默认：`.db-config.json`
- 传 `--employee-id`：`.db-config-{employee_id}.json`
- 传 `--api-key`：`.db-config-{api_key}.json`（优先级高于 `--employee-id`）

### 3. 日常使用

```bash
python3 skills/db-query/scripts/db_query.py --sql "SHOW TABLES"
```

配置已保存，后续只需 `--sql` 一个参数。

### 4. 隔离配置示例（多用户/多员工）

```bash
# 员工级隔离
python3 skills/db-query/scripts/db_query.py \
  --employee-id emp-8cd60aec \
  --sql "SHOW TABLES"

# 用户级隔离（优先级更高）
python3 skills/db-query/scripts/db_query.py \
  --api-key ak-xxxx \
  --sql "SHOW TABLES"
```

---

## 支持的连接串格式

| 格式 | 示例 |
|------|------|
| JDBC | `jdbc:mysql://host:3306/db?user=root&password=xxx` |
| 标准 URL | `mysql://root:xxx@host:3306/db` |
| PostgreSQL | `postgresql://user:xxx@host:5432/db` |
| 省略端口 | `mysql://root:xxx@host/db`（使用默认端口） |

端口可省略，MySQL 默认 3306，PostgreSQL 默认 5432。

---

## 参数一览

| 参数 | 说明 |
|------|------|
| `--cd` | 兼容参数，当前实现保留但不改变配置文件实际存储目录 |
| `--employee-id` | 员工级配置隔离 |
| `--api-key` | 用户级配置隔离（优先于 `--employee-id`） |
| `--sql` | SQL 语句（必填） |
| `--url` | 连接串，支持 JDBC / 标准 URL 格式 |
| `--env` | .env 文件路径 |
| `--type` | `mysql`（默认）/ `postgres` |
| `--host/port/user/password/database` | 手动指定 |
| `--save` | 兼容参数，当前版本无需显式使用（配置变更会自动保存） |
| `--allow-write` | 允许写操作（默认只读） |
| `--limit` | SELECT 最大行数（默认 50） |
| `--format` | `table`（默认）/ `json` / `csv` |
| `--reset` | 删除已保存的配置 |

---

## 常用操作

```bash
# 查看所有表
--sql "SHOW TABLES"

# 查看表结构
--sql "DESC table_name"

# 查看建表语句
--sql "SHOW CREATE TABLE table_name"

# 查询数据（自动限制 50 行）
--sql "SELECT * FROM table_name"

# JSON 格式输出
--format json --sql "SELECT * FROM table_name"

# 写操作（需显式允许）
--allow-write --sql "ALTER TABLE xxx ADD COLUMN yyy VARCHAR(50)"
```

---

## 配置管理

- 配置文件位置：`<db-query技能目录>/.db-config*.json`
- 命名规则：`--api-key` > `--employee-id` > 默认文件
- 配置优先级：显式 CLI 参数 > `--env` > `--url` > 已保存配置
- 首次传参后自动保存，后续免传
- 连接失败时脚本返回错误信息，更新参数重新执行即可覆盖
- 重置配置：`--reset --sql ""`
- **注意**：`.db-config*.json` 已加入 `.gitignore`，不会提交到仓库

---

## 移植到其他项目

1. 复制 `skills/db-query/` 目录（不含 `.db-config*.json`）
2. `pip3 install pymysql psycopg2-binary`
3. 首次运行时提供连接信息，自动保存
