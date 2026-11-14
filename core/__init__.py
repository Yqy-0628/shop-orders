# -*- coding: utf-8 -*-
"""核心模块包。只依赖 sqlite + 标准库，不依赖 Streamlit。"""
import os
import shutil
import tempfile
from pathlib import Path
import sqlite3

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_SOURCE_DB = DATA_DIR / "shop.db"


def _is_cloud():
    """判断是否运行在 Streamlit Community Cloud。

    该容器的文件系统是临时的：重启后写入全部丢失，多个访问者共享同一份文件。
    所以在线演示时不直接写仓库里的 data/shop.db，而是复制一份到临时目录再用。
    本地可用环境变量 SHOP_DB_MODE=temp/file 手动覆盖。
    """
    mode = os.environ.get("SHOP_DB_MODE", "").strip().lower()
    if mode == "temp":
        return True
    if mode == "file":
        return False
    return Path("/home/appuser").exists()


def _effective_db_path():
    if not _is_cloud():
        return _SOURCE_DB
    tmp = Path(tempfile.gettempdir()) / "shop_orders.db"
    if not tmp.exists() and _SOURCE_DB.exists():
        shutil.copy2(_SOURCE_DB, tmp)
    return tmp


DB_PATH = _effective_db_path()


def connect(path=None):
    # Streamlit 每次重跑脚本都换线程，而连接是缓存在 session_state 里的，
    # 所以必须关掉同线程检查，否则切页就报 ProgrammingError。
    conn = sqlite3.connect(path or DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
