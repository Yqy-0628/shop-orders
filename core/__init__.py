# -*- coding: utf-8 -*-
"""核心模块包。只依赖 sqlite + 标准库，不依赖 Streamlit。"""
from pathlib import Path
import sqlite3

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "shop.db"


def connect(path=None):
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
