"""初始化管理员账户脚本。

用法: python scripts/init_admin.py [--username admin] [--password 123456]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from stores.json.user_store import User, UserStore, hash_password

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def main() -> None:
    parser = argparse.ArgumentParser(description="初始化管理员账户")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="123456")
    args = parser.parse_args()

    store = UserStore(DATA_DIR)
    if store.has_any():
        print("系统已初始化，跳过。如需重置请删除 data/users/ 目录。")
        return

    user = User(
        username=args.username,
        password_hash=hash_password(args.password),
    )
    store.save(user)
    print(f"管理员账户已创建: {args.username}")


if __name__ == "__main__":
    main()
