# -*- coding: utf-8 -*-
"""核心模块包。只依赖 sqlite + 标准库，不依赖 Streamlit。"""
from pathlib import Path
import sqlite3

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "shop.db"


def connect(path=None):
    # Streamlit 每次重跑脚本都换线程，而连接是缓存在 session_state 里的，
    # 所以必须关掉同线程检查，否则切页就报 ProgrammingError。
    conn = sqlite3.connect(path or DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
