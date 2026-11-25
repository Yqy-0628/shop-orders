# -*- coding: utf-8 -*-
"""v2 迁移：商品档案加来源与备注、新增标签打印记录表。可重复执行。"""
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "shop.db"


def cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def main():
    conn = sqlite3.connect(DB)
    c = cols(conn, "sku")
    if "source" not in c:
        conn.execute("ALTER TABLE sku ADD COLUMN source TEXT NOT NULL DEFAULT '自制'")
    if "spec" not in c:
        conn.execute("ALTER TABLE sku ADD COLUMN spec TEXT")
    # 按品类给一个合理初值：现做的归自制，常温包装的归进货
    conn.execute("UPDATE sku SET source='进货' WHERE category IN ('日配','鲜食')")
    conn.execute("UPDATE sku SET source='自制' WHERE category IN ('烘焙','饮品')")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS label_print ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, "
        "sku_id TEXT NOT NULL, qty INTEGER NOT NULL)")
    conn.commit()
    print("source:", [dict(zip(("source", "n"), r)) for r in conn.execute(
        "SELECT source, COUNT(*) FROM sku GROUP BY source")])
    conn.close()


main()
