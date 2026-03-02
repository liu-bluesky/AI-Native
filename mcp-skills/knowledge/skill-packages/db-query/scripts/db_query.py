#!/usr/bin/env python3
"""Database query skill for Claude Code. Supports MySQL and PostgreSQL."""

import argparse
import json
import re
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, '..', '.db-config.json')


def load_config():
    path = os.path.normpath(CONFIG_PATH)
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return None


def save_config(cfg):
    path = os.path.normpath(CONFIG_PATH)
    with open(path, 'w') as f:
        json.dump(cfg, f, indent=2)
    print(f"Config saved to {path}")


def parse_env(env_path):
    result = {}
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                k, v = line.split('=', 1)
                result[k.strip()] = v.strip()
    return result


def parse_url(url):
    """Parse connection URL. Supports:
    - jdbc:mysql://host:port/db?user=x&password=y
    - mysql://user:pass@host:port/db
    - postgresql://user:pass@host:port/db
    - host:port/db (bare format)
    - host/db (no port)
    """
    url = url.strip()
    cfg = {}

    # Strip jdbc: prefix
    if url.startswith('jdbc:'):
        url = url[5:]

    # Detect type from scheme
    if url.startswith('mysql://'):
        cfg['type'] = 'mysql'
        url = url[8:]
    elif url.startswith(('postgresql://', 'postgres://')):
        cfg['type'] = 'postgres'
        url = url.split('://', 1)[1]
    else:
        cfg['type'] = 'mysql'

    # Extract query params (?user=x&password=y)
    params = {}
    if '?' in url:
        url, qs = url.split('?', 1)
        for pair in qs.split('&'):
            if '=' in pair:
                k, v = pair.split('=', 1)
                params[k] = v

    # Extract user:pass@ if present
    if '@' in url:
        userinfo, url = url.rsplit('@', 1)
        if ':' in userinfo:
            cfg['user'], cfg['password'] = userinfo.split(':', 1)
        else:
            cfg['user'] = userinfo

    # Extract host:port/database
    if '/' in url:
        hostport, cfg['database'] = url.split('/', 1)
    else:
        hostport = url

    if ':' in hostport:
        cfg['host'], port_str = hostport.split(':', 1)
        cfg['port'] = int(port_str)
    else:
        cfg['host'] = hostport

    # Query params override
    if 'user' in params:
        cfg['user'] = params['user']
    if 'password' in params:
        cfg['password'] = params['password']

    return cfg


def is_write_sql(sql):
    s = sql.strip().upper()
    return any(s.startswith(k) for k in (
        'INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'CREATE', 'TRUNCATE', 'RENAME'
    ))


def is_select(sql):
    s = sql.strip().upper()
    return s.startswith('SELECT') or s.startswith('WITH')


def add_limit(sql, limit):
    if is_select(sql) and 'LIMIT' not in sql.upper():
        return f"{sql.rstrip().rstrip(';')} LIMIT {limit}"
    return sql


def format_table(columns, rows):
    if not columns:
        return "No columns returned."
    if not rows:
        return f"Columns: {', '.join(columns)}\n(0 rows)"
    str_rows = [[str(v) if v is not None else 'NULL' for v in r] for r in rows]
    widths = [max(len(c), max((len(r[i]) for r in str_rows), default=0))
              for i, c in enumerate(columns)]
    sep = '+-' + '-+-'.join('-' * w for w in widths) + '-+'
    header = '| ' + ' | '.join(c.ljust(w) for c, w in zip(columns, widths)) + ' |'
    lines = [sep, header, sep]
    for r in str_rows:
        lines.append('| ' + ' | '.join(v.ljust(w) for v, w in zip(r, widths)) + ' |')
    lines.append(sep)
    lines.append(f"({len(rows)} rows)")
    return '\n'.join(lines)


def connect_db(cfg):
    db_type = cfg.get('type', 'mysql')
    if db_type == 'postgres':
        import psycopg2
        return psycopg2.connect(
            host=cfg['host'], port=int(cfg['port']), user=cfg['user'],
            password=cfg['password'], dbname=cfg['database'], connect_timeout=10
        )
    else:
        import pymysql
        return pymysql.connect(
            host=cfg['host'], port=int(cfg['port']), user=cfg['user'],
            password=cfg['password'], database=cfg['database'],
            charset='utf8mb4', connect_timeout=10
        )


def resolve_config(args):
    """Priority: CLI args > --env > saved config. Save if new."""
    cfg = {}

    # 1. Try saved config as base
    saved = load_config()
    if saved:
        cfg = saved.copy()

    # 2. Override with --url
    if args.url:
        url_cfg = parse_url(args.url)
        cfg.update({k: v for k, v in url_cfg.items() if v})

    # 3. Override with --env
    if args.env:
        env = parse_env(args.env)
        cfg.update({
            'type': args.type or cfg.get('type', 'mysql'),
            'host': env.get('DB_HOST', cfg.get('host', 'localhost')),
            'port': int(env.get('DB_PORT', cfg.get('port', 3306))),
            'user': env.get('DB_USERNAME', cfg.get('user', 'root')),
            'password': env.get('DB_PASSWORD', cfg.get('password', '')),
            'database': env.get('DB_DATABASE', cfg.get('database', '')),
        })

    # 3. Override with explicit CLI args
    if args.host != 'localhost' or not cfg.get('host'):
        cfg['host'] = args.host
    if args.port:
        cfg['port'] = args.port
    if args.user != 'root' or not cfg.get('user'):
        cfg['user'] = args.user
    if args.password:
        cfg['password'] = args.password
    if args.database:
        cfg['database'] = args.database
    if args.type:
        cfg['type'] = args.type

    # Defaults
    cfg.setdefault('type', 'mysql')
    cfg.setdefault('port', 5432 if cfg['type'] == 'postgres' else 3306)

    # Validate
    if not cfg.get('host') or not cfg.get('database'):
        print("NO_CONFIG", file=sys.stderr)
        sys.exit(2)

    # Save if different from saved
    if cfg != saved:
        save_config(cfg)

    return cfg


def main():
    p = argparse.ArgumentParser(description='Database query tool')
    p.add_argument('--env', help='.env file path')
    p.add_argument('--url', help='Connection URL, e.g. jdbc:mysql://host:port/db or mysql://user:pass@host/db')
    p.add_argument('--type', default=None)
    p.add_argument('--host', default='localhost')
    p.add_argument('--port', type=int, default=None)
    p.add_argument('--user', default='root')
    p.add_argument('--password', default='')
    p.add_argument('--database', default='')
    p.add_argument('--sql', required=True)
    p.add_argument('--allow-write', action='store_true')
    p.add_argument('--limit', type=int, default=50)
    p.add_argument('--format', default='table', choices=['table', 'json', 'csv'])
    p.add_argument('--save', help='Save config from provided args/env', action='store_true')
    p.add_argument('--reset', help='Delete saved config', action='store_true')
    args = p.parse_args()

    if args.reset:
        path = os.path.normpath(CONFIG_PATH)
        if os.path.exists(path):
            os.remove(path)
            print(f"Config removed: {path}")
        return

    cfg = resolve_config(args)
    sql = args.sql.strip()

    # Safety check
    if is_write_sql(sql) and not args.allow_write:
        print("ERROR: Write operation blocked. Use --allow-write to permit.", file=sys.stderr)
        sys.exit(1)

    if is_select(sql):
        sql = add_limit(sql, args.limit)

    try:
        conn = connect_db(cfg)
    except Exception as e:
        print(f"CONNECTION_FAILED: {e}", file=sys.stderr)
        sys.exit(3)

    try:
        cur = conn.cursor()
        cur.execute(sql)
        if cur.description:
            columns = [d[0] for d in cur.description]
            rows = cur.fetchall()
            if args.format == 'json':
                print(json.dumps(
                    [dict(zip(columns, [str(v) if v is not None else None for v in r])) for r in rows],
                    ensure_ascii=False, indent=2))
            elif args.format == 'csv':
                print(','.join(columns))
                for r in rows:
                    print(','.join(str(v) if v is not None else '' for v in r))
            else:
                print(format_table(columns, rows))
        else:
            conn.commit()
            print(f"OK. Affected rows: {cur.rowcount}")
    except Exception as e:
        print(f"SQL Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
