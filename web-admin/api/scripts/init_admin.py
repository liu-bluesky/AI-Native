"""初始化管理员账户脚本。

用法: python scripts/init_admin.py [--username admin] [--password 123456]

默认写入 API_DATA_DIR，未设置时写入 ~/.ai-native/web-admin-api/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from core.config import get_api_data_dir
from stores.json.user_store import User, UserStore, hash_password

DATA_DIR = get_api_data_dir()


def main() -> None:
    parser = argparse.ArgumentParser(description="初始化管理员账户")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="123456")
    args = parser.parse_args()

    store = UserStore(DATA_DIR)
    if store.has_any():
        print(f"系统已初始化，跳过。如需重置请删除 {DATA_DIR / 'users'} 目录。")
        return

    user = User(
        username=args.username,
        password_hash=hash_password(args.password),
    )
    store.save(user)
    print(f"管理员账户已创建: {args.username}")


if __name__ == "__main__":
    main()
