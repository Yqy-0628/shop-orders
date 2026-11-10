# -*- coding: utf-8 -*-
"""一键重建 shop.db。删掉 db 后跑这一条命令即可。"""
import csv
import hashlib
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DB = DATA / "shop.db"

SCHEMA = ["sku_id", "name", "category", "cost", "price",
          "salvage", "shelf_life_days", "mu", "sigma"]
MOVE = ["sku_id", "day", "type", "qty", "unit_cost", "status"]
SALES = ["sku_id", "day", "hour", "weekday", "qty", "unit_price"]
STOCKOUT = ["sku_id", "day", "start_hour", "end_hour"]

CAST = {
    "cost": float, "price": float, "salvage": float, "mu": float, "sigma": float,
    "shelf_life_days": int, "hour": int, "weekday": int, "qty": int,
    "unit_cost": float, "unit_price": float, "start_hour": int, "end_hour": int,
}


def load(conn, filename, table, cols):
    path = DATA / filename
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    placeholders = ",".join("?" * len(cols))
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
    conn.executemany(sql, [tuple(CAST.get(c, str)(r[c]) for c in cols) for r in rows])
    return len(rows)


def main():
    if DB.exists():
        DB.unlink()
    conn = sqlite3.connect(DB)
    conn.executescript((DATA / "schema.sql").read_text(encoding="utf-8"))

    pwd = hashlib.sha256("123456".encode("utf-8")).hexdigest()
    conn.executemany(
        "INSERT INTO app_user (username, pwd_hash, role) VALUES (?,?,?)",
        [("boss", pwd, "owner"), ("clerk", pwd, "clerk")],
    )
    conn.commit()

    n1 = load(conn, "sku.csv", "sku", SCHEMA)
    n2 = load(conn, "stock_move.csv", "stock_move", MOVE)
    n3 = load(conn, "sales.csv", "sales", SALES)
    n4 = load(conn, "stockout.csv", "stockout_mark", STOCKOUT)

    conn.commit()
    print(f"sku {n1} / stock_move {n2} / sales {n3} / stockout {n4}")
    print(f"db -> {DB}  ({DB.stat().st_size/1024:.0f} KB)")
    print("账号 boss / clerk，密码 123456")
    conn.close()


if __name__ == "__main__":
    main()
