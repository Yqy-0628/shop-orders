# -*- coding: utf-8 -*-
"""v3 迁移：商品档案加供货商，进货清单按供货商分组。可重复执行。"""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "shop.db"

SEED = {"日配": "日配供应商", "鲜食": "鲜食供应商"}


def cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def main():
    conn = sqlite3.connect(DB)
    if "supplier" not in cols(conn, "sku"):
        conn.execute("ALTER TABLE sku ADD COLUMN supplier TEXT")
    # 进货类先给一个可读的默认供货商，店长在商品档案里改成真实的
    for cat, name in SEED.items():
        conn.execute(
            "UPDATE sku SET supplier=? WHERE source='进货' AND supplier IS NULL "
            "AND category=?", (name, cat))
    conn.execute(
        "UPDATE sku SET supplier='综合供应商' WHERE source='进货' AND supplier IS NULL")
    conn.commit()
    rows = [dict(zip(("supplier", "n"), r)) for r in conn.execute(
        "SELECT COALESCE(supplier,'(无)'), COUNT(*) FROM sku WHERE source='进货' "
        "GROUP BY supplier")]
    print("进货类供货商:", rows)
    conn.close()


main()
